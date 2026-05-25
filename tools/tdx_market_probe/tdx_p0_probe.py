"""P0 验证：macOS 直连 mootdx 获取通达信普通行情/分时/K线.

用法:
  python tdx_p0_probe.py                      # 单次采样
  python tdx_p0_probe.py --loop-minutes 30    # 连续运行 30 分钟
  python tdx_p0_probe.py --symbols 002361,600000,000001  # 自定义股票列表

输出:
  tmp/tdx_market_probe/
    quote_sample_{symbol}.json
    minute_sample_{symbol}.json
    bars_sample_{symbol}.json
    tdx_p0_report.md
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── paths ──
PROBE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROBE_DIR.parents[1]
OUT_DIR = PROJECT_ROOT / "tmp" / "tdx_market_probe"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_CN = timezone(timedelta(hours=8))

# ── logging ──
logger = logging.getLogger("tdx_p0_probe")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.handlers.clear()
logger.addHandler(_handler)


# ── helpers ──
def _now() -> str:
    return datetime.now(TZ_CN).isoformat()


def _ts() -> str:
    return datetime.now(TZ_CN).strftime("%Y%m%d_%H%M%S")


def _safe_json(obj, max_str=2000):
    """Attempt to serialize anything, truncating long strings."""
    try:
        raw = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        if len(raw) > max_str * 2:
            raw = raw[:max_str] + f"\n...<truncated, total {len(raw)} chars>"
        return raw
    except Exception:
        return str(obj)[:max_str]


def _describe_fields(obj, prefix=""):
    """Recursively enumerate all field paths and their value types."""
    fields = {}

    def _walk(value, path):
        if isinstance(value, dict):
            for k, v in value.items():
                _walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(value, list):
            _walk(value[0] if value else None, f"{path}[0]")
        elif isinstance(value, (int, float)):
            fields[path] = type(value).__name__
        elif isinstance(value, str):
            fields[path] = "str"
        elif value is None:
            fields[path] = "None"
        else:
            fields[path] = type(value).__name__

    _walk(obj, prefix)
    return fields


# ── probe logic ──
class TdxP0Probe:
    """P0 验证器 — 只读不写 stock_processing_service."""

    def __init__(self, symbols: list[str], loop_minutes: float = 0):
        self.symbols = symbols
        self.loop_minutes = loop_minutes
        self.client = None

        # stats
        self.quote_ok: dict[str, int] = defaultdict(int)
        self.quote_fail: dict[str, int] = defaultdict(int)
        self.minute_ok: dict[str, int] = defaultdict(int)
        self.minute_fail: dict[str, int] = defaultdict(int)
        self.bars_ok: dict[str, int] = defaultdict(int)
        self.bars_fail: dict[str, int] = defaultdict(int)
        self.errors: list[dict] = []
        self.samples: dict[str, dict] = {}  # first success per symbol per type

    def _init_client(self):
        from mootdx.quotes import Quotes
        import json as _json

        # 尝试 1：默认自动选服
        try:
            self.client = Quotes.factory(market="std", multithread=True, heartbeat=True)
            logger.info("mootdx Quotes client initialized (auto server)")
            return
        except Exception as exc:
            logger.warning("auto server selection failed: %s, trying manual servers...", exc)

        # 尝试 2：从 mootdx 配置文件中读取服务器列表逐个尝试
        config_path = Path.home() / ".mootdx" / "config.json"
        servers = []
        if config_path.exists():
            try:
                cfg = _json.loads(config_path.read_text())
                servers = cfg.get("SERVER", {}).get("HQ", [])
            except Exception:
                pass

        if not servers:
            # 硬编码几个常用服务器兜底
            servers = [
                ["深圳双线主站1", "110.41.147.114", 7709],
                ["深圳双线主站2", "8.129.13.54", 7709],
                ["深圳双线主站4", "47.113.94.204", 7709],
                ["上海双线主站1", "124.70.176.52", 7709],
                ["广州双线主站1", "124.71.85.110", 7709],
            ]

        last_err = None
        for name, ip, port in servers:
            try:
                self.client = Quotes.factory(
                    market="std", server=(ip, int(port)),
                    multithread=True, heartbeat=True,
                )
                # 立即测试一次调用验证
                self.client.quotes(symbol=["000001"])
                logger.info("mootdx connected via %s (%s:%s)", name, ip, port)
                return
            except Exception as exc:
                last_err = exc
                logger.debug("server %s (%s:%s) failed: %s", name, ip, port, exc)
                continue

        raise RuntimeError(f"All TDX servers failed, last error: {last_err}")

    def _probe_quote(self, symbol: str) -> dict | None:
        """返回单只股票的 quote 原始 dict。"""
        try:
            df = self.client.quotes(symbol=[symbol])
            if df is None or len(df) == 0:
                return None
            return df.iloc[0].to_dict()
        except Exception as exc:
            logger.warning("quote(%s) failed: %s", symbol, exc)
            return None

    def _probe_minute(self, symbol: str) -> list | None:
        """返回分时数据原始 list-of-dict。"""
        try:
            df = self.client.minute(symbol=symbol)
            if df is None:
                return []
            return df.reset_index().to_dict(orient="records")
        except Exception as exc:
            logger.warning("minute(%s) failed: %s", symbol, exc)
            return None

    def _probe_bars(self, symbol: str, frequency: int = 9, offset: int = 100) -> list | None:
        """返回 K 线数据原始 list-of-dict。"""
        try:
            df = self.client.bars(symbol=symbol, frequency=frequency, offset=offset)
            if df is None:
                return []
            return df.reset_index().to_dict(orient="records")
        except Exception as exc:
            logger.warning("bars(%s, freq=%s, offset=%s) failed: %s", symbol, frequency, exc)
            return None

    def run_once(self, collect_samples: bool = True) -> dict:
        """Run one round of all probes against all symbols."""
        round_stat = {"ts": _now(), "symbols": {}}

        for sym in self.symbols:
            sym_stat = {}

            # quote
            q = self._probe_quote(sym)
            if q is not None:
                self.quote_ok[sym] += 1
                sym_stat["quote"] = "ok"
                if sym not in self.samples or "quote" not in self.samples[sym]:
                    if collect_samples:
                        self.samples.setdefault(sym, {})["quote"] = q
            else:
                self.quote_fail[sym] += 1
                sym_stat["quote"] = "fail"
                self.errors.append({"ts": _now(), "symbol": sym, "type": "quote", "msg": "no data"})

            # minute
            m = self._probe_minute(sym)
            if m is not None:
                self.minute_ok[sym] += 1
                sym_stat["minute"] = f"ok ({len(m)} rows)"
                if sym not in self.samples or "minute" not in self.samples[sym]:
                    if collect_samples:
                        self.samples.setdefault(sym, {})["minute"] = m
            else:
                self.minute_fail[sym] += 1
                sym_stat["minute"] = "fail"
                self.errors.append({"ts": _now(), "symbol": sym, "type": "minute", "msg": "no data"})

            # bars
            b = self._probe_bars(sym)
            if b is not None:
                self.bars_ok[sym] += 1
                sym_stat["bars"] = f"ok ({len(b)} rows)"
                if sym not in self.samples or "bars" not in self.samples[sym]:
                    if collect_samples:
                        self.samples.setdefault(sym, {})["bars"] = b
            else:
                self.bars_fail[sym] += 1
                sym_stat["bars"] = "fail"
                self.errors.append({"ts": _now(), "symbol": sym, "type": "bars", "msg": "no data"})

            round_stat["symbols"][sym] = sym_stat

        return round_stat

    def run(self) -> None:
        self._init_client()

        if self.loop_minutes <= 0:
            logger.info("single-shot mode")
            self.run_once(collect_samples=True)
            self._save_samples()
            self._write_report()
        else:
            logger.info("loop mode: %s minutes", self.loop_minutes)
            deadline = time.time() + self.loop_minutes * 60
            round_num = 0
            first = True

            while time.time() < deadline:
                round_num += 1
                stat = self.run_once(collect_samples=first)
                first = False

                ok_count = sum(1 for s in stat["symbols"].values() for v in s.values() if v.startswith("ok"))
                total_count = sum(len(s) for s in stat["symbols"].values()) * 1  # 3 calls per symbol
                logger.info("round %d: %d symbols, quote=%s, minute=%s, bars=%s | errors=%d",
                            round_num, len(self.symbols),
                            dict(self.quote_ok), dict(self.minute_ok), dict(self.bars_ok),
                            len(self.errors))

                time.sleep(5)

            self._save_samples()
            self._write_report()

    # ── output ──
    def _save_samples(self) -> None:
        for sym, data in self.samples.items():
            for data_type in ("quote", "minute", "bars"):
                if data_type in data:
                    fname = f"{data_type}_sample_{sym}.json"
                    fpath = OUT_DIR / fname
                    fpath.write_text(_safe_json(data[data_type], max_str=50000), encoding="utf-8")
                    logger.info("saved %s", fpath)

    def _write_report(self) -> None:
        lines = []
        lines.append("# TDX P0 探针报告")
        lines.append(f"生成时间：{_now()}")
        lines.append(f"探针版本：tdx_p0_probe.py")
        lines.append(f"运行模式：{'loop ' + str(self.loop_minutes) + 'min' if self.loop_minutes > 0 else 'single-shot'}")
        lines.append(f"测试股票：{', '.join(self.symbols)}")
        lines.append("")

        # ── 汇总表 ──
        lines.append("## 1. 汇总")
        lines.append("| 股票 | quote 成功 | quote 失败 | minute 成功 | minute 失败 | bars 成功 | bars 失败 |")
        lines.append("|------|-----------|-----------|-------------|-------------|----------|----------|")
        for sym in self.symbols:
            lines.append(f"| {sym} | {self.quote_ok[sym]} | {self.quote_fail[sym]} | "
                         f"{self.minute_ok[sym]} | {self.minute_fail[sym]} | "
                         f"{self.bars_ok[sym]} | {self.bars_fail[sym]} |")
        lines.append("")

        # ── 字段清单 ──
        for sym, data in self.samples.items():
            lines.append(f"## 2. `{sym}` 字段清单")
            for data_type in ("quote", "minute", "bars"):
                if data_type in data:
                    sample = data[data_type]
                    if isinstance(sample, list) and len(sample) > 0:
                        fields = _describe_fields(sample[0])
                    elif isinstance(sample, dict):
                        fields = _describe_fields(sample)
                    else:
                        fields = {}
                    lines.append(f"### {data_type}（{len(sample) if isinstance(sample, list) else 1} 条）")
                    lines.append("| 字段路径 | 类型 |")
                    lines.append("|----------|------|")
                    for path, ftype in sorted(fields.items()):
                        lines.append(f"| `{path}` | {ftype} |")
                    lines.append("")
            lines.append("")

        # ── L2 字段检测 ──
        lines.append("## 3. L2 字段检测")
        l2_keywords = [
            "bid2", "bid3", "bid4", "bid5", "bid6", "bid7", "bid8", "bid9", "bid10",
            "ask2", "ask3", "ask4", "ask5", "ask6", "ask7", "ask8", "ask9", "ask10",
            "bid2_vol", "ask2_vol", "buy_order", "sell_order", "entrust",
            "transaction", "tick", "detail", "queue",
        ]
        l2_found: dict[str, list[str]] = {}
        for sym, data in self.samples.items():
            for data_type in ("quote", "minute", "bars"):
                if data_type in data:
                    sample = data[data_type]
                    if isinstance(sample, list) and len(sample) > 0:
                        all_keys = set(_describe_fields(sample[0]).keys())
                    elif isinstance(sample, dict):
                        all_keys = set(_describe_fields(sample).keys())
                    else:
                        all_keys = set()
                    hits = [kw for kw in l2_keywords if any(kw in str(k).lower() for k in all_keys)]
                    if hits:
                        l2_found.setdefault(sym, []).extend([f"{data_type}:{h}" for h in hits])

        if l2_found:
            lines.append("**以下 L2 相关字段在返回数据中被发现：**")
            for sym, hits in sorted(l2_found.items()):
                lines.append(f"- {sym}: {', '.join(sorted(set(hits)))}")
        else:
            lines.append("**未发现任何 L2 相关字段（十档盘口、逐笔成交、委托队列等）。**")
            lines.append("结论：mootdx 标准接口不提供 L2 付费数据。")
        lines.append("")

        # ── 错误日志 ──
        if self.errors:
            lines.append("## 4. 错误记录")
            lines.append(f"共 {len(self.errors)} 条错误（最多展示 50 条）")
            lines.append("| 时间 | 股票 | 类型 | 信息 |")
            lines.append("|------|------|------|------|")
            for err in self.errors[:50]:
                lines.append(f"| {err['ts']} | {err['symbol']} | {err['type']} | {err.get('msg', '')[:80]} |")
            lines.append("")

        # ── 结论 ──
        lines.append("## 5. P0 判定")
        all_ok = all(
            self.quote_ok[s] > 0 and self.minute_ok[s] > 0 and self.bars_ok[s] > 0
            for s in self.symbols
        )
        if all_ok:
            lines.append("**P0 通过。** mootdx 可稳定获取普通行情、分时、K线数据。")
            lines.append("建议：进入 P1，按 jyhf_market 模式接入 stock_processing_service。")
        else:
            lines.append("**P0 未完全通过。** 部分接口存在失败，需排查。")
        lines.append("")

        report = "\n".join(lines)
        fpath = OUT_DIR / "tdx_p0_report.md"
        fpath.write_text(report, encoding="utf-8")
        logger.info("report written to %s", fpath)
        print("\n" + report)


# ── CLI ──
def main():
    p = argparse.ArgumentParser(description="TDX P0 Probe — mootdx 行情验证")
    p.add_argument("--symbols", default="002361,600000",
                   help="股票代码，逗号分隔 (default: 002361,600000)")
    p.add_argument("--loop-minutes", type=float, default=0,
                   help="连续运行分钟数（0=单次采样）")
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    # 尝试 import，给出友好提示
    try:
        from mootdx.quotes import Quotes  # noqa: F401
    except ImportError:
        logger.error("mootdx 未安装。请执行: pip install 'mootdx[all]'")
        logger.error("或: pip install -r tools/tdx_market_probe/requirements.txt")
        sys.exit(1)

    probe = TdxP0Probe(symbols=symbols, loop_minutes=args.loop_minutes)
    try:
        probe.run()
    except KeyboardInterrupt:
        logger.info("interrupted by user")
        probe._save_samples()
        probe._write_report()
    except Exception as exc:
        logger.exception("fatal error: %s", exc)
        probe._save_samples()
        probe._write_report()
        sys.exit(2)


if __name__ == "__main__":
    main()

"""只读探测：核查通达信个股 F10 中的资金动向 / 涨停分析 / 龙虎榜数据.

用途:
  - 枚举 F10 目录
  - 搜索 "资金动向" / "涨停分析" / "龙虎榜"
  - 尝试读取对应内容
  - 输出 JSON + Markdown 报告，便于人工核对

注意:
  - 这是合规的只读探测脚本，不涉及绕过权限或解密
  - 依赖通达信官方/标准行情链路可用

示例:
  python tools/tdx_market_probe/tdx_f10_probe.py --symbols 000001,600000
  python tools/tdx_market_probe/tdx_f10_probe.py --symbols 000001 --dump-json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.tdx_market_agent.tdx_client import TdxClient, parse_stock_id  # noqa: E402


TZ_CN = timezone(timedelta(hours=8))
OUT_DIR = PROJECT_ROOT / "tmp" / "tdx_market_probe"
OUT_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("tdx_f10_probe")


TARGET_KEYWORDS = (
    "资金动向",
    "涨停分析",
    "龙虎榜",
    "龙虎榜机构",
    "龙虎榜营业部",
    "龙虎榜沪深股通",
)


@dataclass
class SectionHit:
    keyword: str
    source: str
    name: str
    summary: str
    raw_type: str


@dataclass
class SymbolReport:
    symbol: str
    system_symbol: str
    ts: str
    connected_server: str
    catalog_count: int
    catalog_names: list[str]
    catalog_hits: list[SectionHit]
    content_keys: list[str]
    content_hits: list[SectionHit]
    content_text_hits: list[SectionHit]
    split_sections: list[dict[str, Any]]
    notes: list[str]


def _now() -> str:
    return datetime.now(TZ_CN).isoformat()


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _strip_text(text: str, limit: int = 800) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<truncated {len(text) - limit} chars>"


def _df_to_rows(obj: Any) -> list[dict]:
    if obj is None:
        return []
    if hasattr(obj, "to_dict") and hasattr(obj, "columns"):
        try:
            return obj.to_dict(orient="records")
        except Exception:
            pass
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        if {"name", "filename", "start", "length"} & set(obj.keys()):
            return [obj]
        rows = []
        for key, value in obj.items():
            if isinstance(value, dict):
                row = {"name": key, **value}
                rows.append(row)
            else:
                rows.append({"name": key, "value": value})
        return rows
    return []


def _row_name(row: dict) -> str:
    for key in ("name", "title", "field", "label", "section"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _summarize_value(value: Any, limit: int = 240) -> tuple[str, str]:
    if value is None:
        return "None", "empty"
    if isinstance(value, str):
        text = _strip_text(value, limit=limit)
        return text, "str"
    if isinstance(value, list):
        sample = value[:3]
        return _strip_text(_safe_json(sample), limit=limit), "list"
    if isinstance(value, dict):
        keys = list(value.keys())
        return _strip_text(_safe_json({"keys": keys[:20]}), limit=limit), "dict"
    if hasattr(value, "to_dict"):
        try:
            sample = value.head(3).to_dict(orient="records")  # type: ignore[attr-defined]
            return _strip_text(_safe_json(sample), limit=limit), type(value).__name__
        except Exception:
            pass
    return _strip_text(str(value), limit=limit), type(value).__name__


def _match_keyword(name: str, keywords: tuple[str, ...]) -> str | None:
    if not name:
        return None
    for kw in keywords:
        if kw == name or kw in name or name in kw:
            return kw
    return None


def _collect_catalog_hits(rows: list[dict]) -> list[SectionHit]:
    hits: list[SectionHit] = []
    for row in rows:
        name = _row_name(row)
        kw = _match_keyword(name, TARGET_KEYWORDS)
        if not kw:
            continue
        summary, raw_type = _summarize_value(row)
        hits.append(SectionHit(keyword=kw, source="F10C", name=name, summary=summary, raw_type=raw_type))
    return hits


def _collect_content_hits(content: Any) -> list[SectionHit]:
    hits: list[SectionHit] = []
    if isinstance(content, dict):
        items = content.items()
    elif hasattr(content, "to_dict") and hasattr(content, "columns"):
        try:
            items = content.to_dict(orient="records")[0].items()  # type: ignore[assignment]
        except Exception:
            items = []
    else:
        items = []

    for key, value in items:
        if not isinstance(key, str):
            continue
        kw = _match_keyword(key, TARGET_KEYWORDS)
        if not kw:
            continue
        summary, raw_type = _summarize_value(value)
        hits.append(SectionHit(keyword=kw, source="F10", name=key, summary=summary, raw_type=raw_type))
    return hits


def _collect_text_hits(text: str) -> list[SectionHit]:
    hits: list[SectionHit] = []
    if not text:
        return hits

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for kw in TARGET_KEYWORDS:
        for idx, line in enumerate(lines):
            if kw in line:
                start = max(0, idx - 1)
                end = min(len(lines), idx + 2)
                context = " | ".join(lines[start:end])
                hits.append(
                    SectionHit(
                        keyword=kw,
                        source="F10_TEXT",
                        name=line[:120],
                        summary=_strip_text(context, 260),
                        raw_type="str",
                    )
                )
                break
    return hits


def _split_f10_text_sections(text: str) -> list[dict[str, Any]]:
    """粗切 F10 正文中的子标题，便于人工查看资金动向明细。"""
    if not text:
        return []

    markers = list(re.finditer(r"(?m)^【([^】]+)】", text))
    if not markers:
        return []

    sections: list[dict[str, Any]] = []
    for idx, match in enumerate(markers):
        title = match.group(1).strip()
        start = match.end()
        end = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
        body = text[start:end].strip()
        sections.append({
            "title": title,
            "body": _strip_text(body, 500),
        })
    return sections


def _print_report(report: SymbolReport) -> str:
    lines = [
        f"symbol: {report.symbol} ({report.system_symbol})",
        f"server: {report.connected_server}",
        f"catalog_count: {report.catalog_count}",
        "catalog_names:",
    ]
    lines.extend([f"  - {name}" for name in report.catalog_names[:80]])
    if len(report.catalog_names) > 80:
        lines.append(f"  - ...<{len(report.catalog_names) - 80} more>")

    lines.append("catalog_hits:")
    if report.catalog_hits:
        for hit in report.catalog_hits:
            lines.append(f"  - [{hit.keyword}] {hit.name} ({hit.raw_type})")
            lines.append(f"    {hit.summary}")
    else:
        lines.append("  - none")

    lines.append("content_keys:")
    if report.content_keys:
        for key in report.content_keys[:80]:
            lines.append(f"  - {key}")
    else:
        lines.append("  - none")

    lines.append("content_hits:")
    if report.content_hits:
        for hit in report.content_hits:
            lines.append(f"  - [{hit.keyword}] {hit.name} ({hit.raw_type})")
            lines.append(f"    {hit.summary}")
    else:
        lines.append("  - none")

    lines.append("content_text_hits:")
    if report.content_text_hits:
        for hit in report.content_text_hits:
            lines.append(f"  - [{hit.keyword}] {hit.name} ({hit.raw_type})")
            lines.append(f"    {hit.summary}")
    else:
        lines.append("  - none")

    lines.append("split_sections:")
    if report.split_sections:
        for sec in report.split_sections[:40]:
            title = sec.get("title", "")
            body = sec.get("body", "")
            lines.append(f"  - {title}")
            if body:
                lines.append(f"    {body}")
    else:
        lines.append("  - none")

    if report.notes:
        lines.append("notes:")
        lines.extend([f"  - {note}" for note in report.notes])

    return "\n".join(lines)


def _write_outputs(report: SymbolReport, dump_json: bool) -> None:
    stem = f"f10_probe_{report.symbol}_{datetime.now(TZ_CN).strftime('%Y%m%d_%H%M%S')}"
    md_path = OUT_DIR / f"{stem}.md"
    json_path = OUT_DIR / f"{stem}.json"
    md_path.write_text(_print_report(report), encoding="utf-8")
    if dump_json:
        json_path.write_text(_safe_json(asdict(report)), encoding="utf-8")
    logger.info("wrote report: %s", md_path)
    if dump_json:
        logger.info("wrote json: %s", json_path)


def probe_symbol(client: TdxClient, raw_symbol: str, section: str = "") -> SymbolReport:
    numeric_symbol, system_symbol = parse_stock_id(raw_symbol)

    catalog = client.get_f10_catalog(numeric_symbol)
    catalog_rows = _df_to_rows(catalog)
    catalog_names = [_row_name(row) for row in catalog_rows if _row_name(row)]
    catalog_hits = _collect_catalog_hits(catalog_rows)

    content = client.get_f10_content(numeric_symbol, name=section)

    if isinstance(content, dict):
        content_keys = list(content.keys())
        content_hits = _collect_content_hits(content)
    elif isinstance(content, str) and content.strip() and section:
        # 定向读取单个 section → 返回 str，构造单 key 视图
        content_keys = [section]
        content_hits = _collect_content_hits({section: content})
    else:
        content_keys = []
        content_hits = []

    content_text_hits: list[SectionHit] = []
    split_sections: list[dict[str, Any]] = []

    if isinstance(content, dict):
        # 从全量 dict 中筛选目标章节做正文搜索 + 子标题切分
        target_sections = (section,) if section else TARGET_KEYWORDS
        for key in target_sections:
            value = content.get(key)
            if isinstance(value, str):
                content_text_hits.extend(_collect_text_hits(value))
                split_sections.extend(_split_f10_text_sections(value))
    elif isinstance(content, str) and content.strip():
        # 单 section 返回的 str
        content_text_hits.extend(_collect_text_hits(content))
        split_sections.extend(_split_f10_text_sections(content))

    notes: list[str] = []
    if not catalog_rows:
        notes.append("F10C 返回为空或无法解析为目录表")
    if not catalog_hits:
        notes.append("F10C 目录里未直接命中 资金动向 / 涨停分析 / 龙虎榜 关键词")
    if not content_hits and not content_text_hits:
        notes.append("F10 内容里未直接命中 资金动向 / 涨停分析 / 龙虎榜 关键词")
    if content_hits:
        notes.append("F10 返回的 dict key 命中关键字")
    if content_text_hits:
        notes.append("已从 F10 正文中命中关键字")
    if split_sections:
        notes.append("已解析 F10 正文子标题")
    if section:
        notes.append(f"已启用定向章节读取: {section}")

    return SymbolReport(
        symbol=numeric_symbol,
        system_symbol=system_symbol,
        ts=_now(),
        connected_server=client.server_info,
        catalog_count=len(catalog_rows),
        catalog_names=catalog_names,
        catalog_hits=catalog_hits,
        content_keys=content_keys,
        content_hits=content_hits,
        content_text_hits=content_text_hits,
        split_sections=split_sections,
        notes=notes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只读探测通达信 F10 的资金动向 / 涨停分析 / 龙虎榜")
    parser.add_argument(
        "--symbols",
        default="000001,600000",
        help="逗号分隔股票代码，如 000001,600000,002361",
    )
    parser.add_argument(
        "--dump-json",
        action="store_true",
        help="同时写出 JSON 报告到 tmp/tdx_market_probe",
    )
    parser.add_argument(
        "--section",
        default="",
        help="可选：仅定向读取某个 F10 章节，如 资金动向。为空则读取全部目录项",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="TDX 连接超时秒数",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="日志级别",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        parser.error("至少提供一个股票代码")

    client = TdxClient(timeout=args.timeout)
    try:
        client.connect()
    except ModuleNotFoundError as exc:
        logger.error(
            "依赖缺失：%s。请先在当前环境安装 tools/tdx_market_agent/requirements.txt 里的依赖，"
            "至少需要 mootdx[all]。",
            exc,
        )
        return 2
    except Exception as exc:
        logger.error("TDX 连接失败: %s", exc)
        return 2

    logger.info("connected: %s", client.server_info)

    for raw_symbol in symbols:
        report = probe_symbol(client, raw_symbol, section=args.section.strip())
        print(_print_report(report))
        print("\n---")
        _write_outputs(report, dump_json=args.dump_json)

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

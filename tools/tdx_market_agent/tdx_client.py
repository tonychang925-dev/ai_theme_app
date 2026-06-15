"""mootdx 封装 — 多服务器 fallback + stock_id 规范化.

不依赖 stock_processing_service，不引入主链依赖。
"""
from __future__ import annotations

import json
import logging
import socket
from pathlib import Path
from typing import Tuple

import pandas as pd

logger = logging.getLogger("tdx_market_agent.client")

# ── stock_id 规范化 ──
_SZ_PREFIXES = ("002", "000", "300", "001", "003", "004")
_SH_PREFIXES = ("600", "601", "603", "605", "688", "689")


def parse_stock_id(raw: str) -> Tuple[str, str]:
    """解析输入，返回 (数字ID, 系统ID).

    >>> parse_stock_id("002361")
    ("002361", "002361.SZ")
    >>> parse_stock_id("002361.SZ")
    ("002361", "002361.SZ")
    >>> parse_stock_id("600000.SH")
    ("600000", "600000.SH")
    """
    raw = raw.strip().upper()
    # 去掉后缀
    numeric = raw.replace(".SZ", "").replace(".SH", "").replace(".BJ", "")

    if numeric.startswith(_SH_PREFIXES):
        system = f"{numeric}.SH"
    elif numeric.startswith(_SZ_PREFIXES):
        system = f"{numeric}.SZ"
    elif len(numeric) == 6 and numeric.isdigit():
        # 兜底：4/8 开头当 BJ，其余当 SZ
        if numeric.startswith(("4", "8")):
            system = f"{numeric}.BJ"
        else:
            system = f"{numeric}.SZ"
    else:
        system = f"{numeric}.SZ"

    return numeric, system


# ── 服务器发现 ──
def _load_servers() -> list[Tuple[str, str, int]]:
    """从 mootdx 配置文件读取 HQ 服务器列表."""
    config_path = Path.home() / ".mootdx" / "config.json"
    servers = []
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
            servers = cfg.get("SERVER", {}).get("HQ", [])
        except Exception:
            pass
    if not servers:
        servers = [
            ["深圳双线主站1", "110.41.147.114", 7709],
            ["深圳双线主站2", "8.129.13.54", 7709],
            ["上海双线主站1", "124.70.176.52", 7709],
            ["广州双线主站1", "124.71.85.110", 7709],
        ]
    return [(s[0], s[1], int(s[2])) for s in servers]


def _find_reachable(servers: list, timeout: float = 1.5) -> list[Tuple[str, str, int]]:
    """socket 预检，返回可达服务器列表."""
    reachable = []
    for name, ip, port in servers:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((ip, port))
            s.close()
            reachable.append((name, ip, port))
        except Exception:
            pass
    return reachable


# ── TDX Client ──
class TdxClient:
    """mootdx 行情客户端封装."""

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout
        self._client = None
        self._server_info: str = ""

    @property
    def server_info(self) -> str:
        return self._server_info

    def connect(self) -> None:
        """连接 mootdx，socket 预检后直连第一个可用服务器."""
        from mootdx.quotes import Quotes

        all_servers = _load_servers()
        reachable = _find_reachable(all_servers)
        logger.info("reachable: %d/%d servers", len(reachable), len(all_servers))

        if not reachable:
            raise RuntimeError("No reachable TDX servers (check network)")

        last_err = None
        for name, ip, port in reachable:
            try:
                # 不传 bestip=True，避免触发慢速全网探测
                self._client = Quotes.factory(
                    market="std", server=(ip, port), timeout=self._timeout,
                )
                self._server_info = f"{name} ({ip}:{port})"
                logger.info("connected via %s", self._server_info)
                return
            except Exception as exc:
                last_err = exc
                logger.debug("%s failed: %s", name, exc)
                continue

        raise RuntimeError(f"All {len(reachable)} reachable servers failed: {last_err}")

    def get_quote(self, numeric_id: str) -> dict:
        """获取单只股票实时行情."""
        self._ensure_connected()
        df = self._client.quotes(symbol=[numeric_id])
        if df is None or len(df) == 0:
            raise ValueError(f"no quote data for {numeric_id}")
        raw = df.iloc[0].to_dict()
        # 将 numpy/非标准类型转换
        return _clean_dict(raw)

    def get_minute(self, numeric_id: str) -> list[dict]:
        """获取分时数据."""
        self._ensure_connected()
        df = self._client.minute(symbol=numeric_id)
        if df is None:
            return []
        rows = df.reset_index().to_dict(orient="records")
        return [_clean_dict(r) for r in rows]

    def get_bars(self, numeric_id: str, frequency: int = 9, offset: int = 100) -> list[dict]:
        """获取 K 线数据."""
        self._ensure_connected()
        df = self._client.bars(symbol=numeric_id, frequency=frequency, offset=offset)
        if df is None:
            return []

        # DatetimeIndex 列名冲突处理
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.insert(0, "dt", df.index.astype(str))

        rows = df.to_dict(orient="records")
        return [_clean_dict(r) for r in rows]

    def get_f10_catalog(self, numeric_id: str) -> list[dict]:
        """获取 F10 公司信息目录."""
        self._ensure_connected()
        result = self._client.F10C(symbol=numeric_id)
        return _normalize_payload(result)

    def get_f10_content(self, numeric_id: str, name: str = "") -> dict | list | str:
        """获取 F10 公司信息详情，name 为空则返回全部目录项."""
        self._ensure_connected()
        if name.strip():
            result = self._client.F10(symbol=numeric_id, name=name.strip())
        else:
            result = self._client.F10(symbol=numeric_id)
        return _normalize_payload(result)

    def _ensure_connected(self) -> None:
        if self._client is None:
            self.connect()

    def close(self) -> None:
        if self._client:
            try:
                self._client.client.close()
            except Exception:
                pass
            self._client = None


def _clean_dict(d: dict) -> dict:
    """将 dict 中的非 JSON 兼容类型转换."""
    import numpy as np
    result = {}
    for k, v in d.items():
        if isinstance(v, (np.integer,)):
            result[k] = int(v)
        elif isinstance(v, (np.floating,)):
            result[k] = float(v)
        elif isinstance(v, np.ndarray):
            result[k] = v.tolist()
        elif isinstance(v, tuple):
            result[k] = list(v)
        else:
            # 尝试 JSON 序列化
            try:
                json.dumps(v)
                result[k] = v
            except (TypeError, ValueError):
                result[k] = str(v)
    return result


def _normalize_payload(value):
    """将 F10 / 目录返回值递归规整成 JSON 兼容结构."""
    if value is None:
        return None

    if hasattr(value, "to_dict") and hasattr(value, "columns"):
        try:
            return [_clean_dict(r) for r in value.to_dict(orient="records")]
        except Exception:
            return str(value)

    if isinstance(value, dict):
        return {str(k): _normalize_payload(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_normalize_payload(v) for v in value]

    if isinstance(value, tuple):
        return [_normalize_payload(v) for v in value]

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)

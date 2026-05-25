"""TDX 股票池 — stock_id=XXXX.SZ (系统格式), api_stock_id=XXXX (Agent 用).

与 JYHF universe 对齐：内部统一使用系统格式 stock_id.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("sps.tdx_market.universe")


class TdxMarketUniverse:
    def __init__(self, watchlist_path: str):
        self._path = Path(watchlist_path)
        self._data: dict = {"watch_stocks": [], "watch_subjects": []}

    def load(self) -> dict:
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text())
            else:
                self._ensure_default()
        except Exception:
            self._ensure_default()

        # 统一化为系统格式：002361.SZ / 600000.SH
        cleaned = []
        for s in self._data.get("watch_stocks", []):
            sid = _normalize_stock_id(str(s))
            if sid:
                cleaned.append(sid)

        self._data["watch_stocks"] = cleaned
        logger.info("TDX watchlist: %d stocks (system format)", len(cleaned))
        return self._data

    def get_stocks(self) -> list[str]:
        """返回系统格式 stock_id，如 002361.SZ."""
        return list(self._data.get("watch_stocks", []))

    def get_api_stock_ids(self) -> list[str]:
        """返回 Agent API 格式，纯数字."""
        return [_to_api(s) for s in self.get_stocks()]

    def _ensure_default(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        default = {"watch_stocks": ["002361.SZ", "600000.SH"]}
        self._path.write_text(json.dumps(default, ensure_ascii=False, indent=2))
        self._data = default


def _normalize_stock_id(raw: str) -> str:
    """输入 002361 / 002361.SZ → 输出 002361.SZ."""
    s = raw.strip().upper()
    if "." in s:
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        elif s.startswith(("0", "3")):
            return f"{s}.SZ"
        elif s.startswith(("4", "8")):
            return f"{s}.BJ"
        return f"{s}.SZ"
    return s


def _to_api(stock_id: str) -> str:
    """002361.SZ → 002361."""
    return stock_id.replace(".SZ", "").replace(".SH", "").replace(".BJ", "").replace(".sz", "").replace(".sh", "")

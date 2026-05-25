"""TDX 股票池 — 配置文件驱动，与 jyhf 共享或独立."""
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

        stocks = self._data.get("watch_stocks", [])
        # 清理 .SZ/.SH 后缀：mootdx agent 只需要数字部分
        cleaned = []
        for s in stocks:
            raw = str(s).strip().upper()
            numeric = raw.replace(".SZ", "").replace(".SH", "").replace(".BJ", "")
            if numeric.isdigit() and len(numeric) == 6:
                cleaned.append(numeric)

        self._data["watch_stocks"] = cleaned
        logger.info("TDX watchlist: %d stocks", len(cleaned))
        return self._data

    def get_stocks(self) -> list[str]:
        return list(self._data.get("watch_stocks", []))

    def _ensure_default(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        default = {"watch_stocks": ["002361", "600000"]}
        self._path.write_text(json.dumps(default, ensure_ascii=False, indent=2))
        self._data = default

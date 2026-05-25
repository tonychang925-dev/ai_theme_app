"""P1-A 股票池 — 配置文件驱动."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("sps.jyhf_market.universe")


class JyhfMarketUniverse:
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
        logger.info("Watchlist: %d stocks, %d subjects",
                     len(self._data.get("watch_stocks", [])),
                     len(self._data.get("watch_subjects", [])))
        return self._data

    def get_stocks(self) -> list[str]:
        return list(self._data.get("watch_stocks", []))

    def get_subjects(self) -> list[str]:
        return list(self._data.get("watch_subjects", []))

    def _ensure_default(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        default = {"watch_stocks": ["002361.SZ"], "watch_subjects": ["9019807"]}
        self._path.write_text(json.dumps(default, ensure_ascii=False, indent=2))
        self._data = default

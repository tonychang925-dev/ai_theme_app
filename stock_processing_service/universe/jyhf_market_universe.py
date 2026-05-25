"""P1-B+ 多来源候选池 — stock_id 内部=XXXX.SZ, API=纯数字.

接口隔离:
  - stock_id:   XXXX.SZ / XXXX.SH (系统内部/DB/Redis)
  - api_stock_id: XXXX         (JYHF API 请求用)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("sps.jyhf_market.universe")


@dataclass
class UniverseStock:
    stock_id: str          # 002795.SZ
    stock_name: str = ""
    sources: set[str] = field(default_factory=set)
    subject_ids: set[str] = field(default_factory=set)
    priority: int = 0

    @property
    def api_stock_id(self) -> str:
        return self.stock_id.replace(".SZ", "").replace(".SH", "").replace(".sz", "").replace(".sh", "")


class JyhfMarketUniverse:
    """P1-B+: merged pool — manual + strong_watch + w2s + subject_pool."""

    def __init__(self, watchlist_path: str):
        self._path = Path(watchlist_path)
        self._manual: dict = {"watch_stocks": [], "watch_subjects": []}
        self._stocks: dict[str, UniverseStock] = {}
        self._subjects: set[str] = set()
        self._breakdown: dict[str, int] = {}

    # ── public ──

    def load_manual(self) -> dict:
        try:
            if self._path.exists():
                self._manual = json.loads(self._path.read_text())
            else:
                self._ensure_default_manual()
        except Exception:
            self._ensure_default_manual()
        logger.info("Manual watchlist: %d stocks, %d subjects",
                     len(self._manual.get("watch_stocks", [])),
                     len(self._manual.get("watch_subjects", [])))
        return self._manual

    def merge(
        self,
        strong_watch_stocks: list[dict[str, Any]] | None = None,
        w2s_stocks: list[dict[str, Any]] | None = None,
        hot_subjects: list[str] | None = None,
    ) -> dict:
        """合并所有来源。"""
        self._stocks.clear()
        self._subjects = set()

        # default_subjects (env var, 生产态应为空)
        ds = os.getenv("JYHF_MARKET_DEFAULT_SUBJECTS", "")
        if ds:
            for s in ds.split(","):
                self._subjects.add(s.strip())

        # 1. manual (最优先)
        for sid in self._manual.get("watch_stocks", []):
            self._add_stock(_normalize_stock_id(sid), source="manual", priority=100)
        for sid in self._manual.get("watch_subjects", []):
            self._subjects.add(str(sid))

        # 2. w2s
        if w2s_stocks:
            for s in w2s_stocks:
                sid = _normalize_stock_id(str(s.get("stock_id", "")))
                self._add_stock(sid, name=str(s.get("stock_name", "")),
                                source="w2s", priority=80,
                                subject_id=s.get("subject_id") or s.get("subject_key"))

        # 3. strong_watch (保留 subject/theme 信息)
        if strong_watch_stocks:
            for s in strong_watch_stocks:
                sid = _normalize_stock_id(str(s.get("stock_id", "")))
                self._add_stock(sid, name=str(s.get("stock_name", "")),
                                source="strong_watch", priority=60,
                                subject_id=s.get("subject_id") or s.get("subject_key"))

        # 4. hot subjects
        if hot_subjects:
            for sid in hot_subjects:
                self._subjects.add(str(sid))

        # 构建输出
        stock_list = sorted(self._stocks.values(), key=lambda x: (-x.priority, x.stock_id))
        self._breakdown = {
            "manual": sum(1 for s in stock_list if "manual" in s.sources),
            "w2s": sum(1 for s in stock_list if "w2s" in s.sources),
            "strong_watch": sum(1 for s in stock_list if "strong_watch" in s.sources),
            "hot_subject": 0,
            "total_unique": len(stock_list),
        }

        return {
            "watch_stocks": [s.stock_id for s in stock_list],
            "watch_subjects": sorted(self._subjects),
            "source_breakdown": dict(self._breakdown),
            "detail": {
                s.stock_id: {
                    "api_stock_id": s.api_stock_id,
                    "name": s.stock_name,
                    "sources": sorted(s.sources),
                    "subject_ids": sorted(s.subject_ids),
                    "priority": s.priority,
                }
                for s in stock_list
            },
        }

    # ── P1-B+: 结构化 items ──

    def get_stock_items(self) -> list[dict]:
        """返回结构化 stock items，确保 stock_id (系统格式) 和 api_stock_id (API 格式) 分离。"""
        return [
            {
                "stock_id": s.stock_id,
                "api_stock_id": s.api_stock_id,
                "stock_name": s.stock_name,
                "sources": sorted(s.sources),
                "subject_ids": sorted(s.subject_ids),
                "priority": s.priority,
            }
            for s in sorted(self._stocks.values(), key=lambda x: (-x.priority, x.stock_id))
        ]

    def get_api_stock_ids(self) -> list[str]:
        return [s.api_stock_id for s in self._stocks.values()]

    def get_subjects(self) -> list[str]:
        return sorted(self._subjects)

    @property
    def breakdown(self) -> dict[str, int]:
        return dict(self._breakdown)

    # ── private ──

    def _add_stock(self, stock_id: str, name: str = "", source: str = "",
                   priority: int = 0, subject_id: str | None = None) -> None:
        if not stock_id:
            return
        if stock_id not in self._stocks:
            self._stocks[stock_id] = UniverseStock(stock_id=stock_id, stock_name=name)
        s = self._stocks[stock_id]
        if name:
            s.stock_name = name
        if source:
            s.sources.add(source)
        s.priority = max(s.priority, priority)
        if subject_id:
            s.subject_ids.add(str(subject_id))
            self._subjects.add(str(subject_id))

    def _ensure_default_manual(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        default = {"watch_stocks": [], "watch_subjects": []}
        self._path.write_text(json.dumps(default, ensure_ascii=False, indent=2))
        self._manual = default


def _normalize_stock_id(raw: str) -> str:
    s = raw.strip().upper()
    if "." in s:
        return s
    if len(s) == 6:
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        elif s.startswith(("0", "3")):
            return f"{s}.SZ"
    return s

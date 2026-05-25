"""P1-B 多来源候选池 — manual + strong_watch + w2s + subject_pool.

stock_id 内部统一为 XXXX.SZ / XXXX.SH 格式。
请求 JYHF API 时去掉后缀转为纯数字。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("sps.jyhf_market.universe")

# 金斧头 - 默认最低 subjects
_DEFAULT_SUBJECTS = ["9019807"]


@dataclass
class UniverseStock:
    stock_id: str          # 002361.SZ 格式
    stock_name: str = ""
    sources: set[str] = field(default_factory=set)
    subject_ids: set[str] = field(default_factory=set)
    priority: int = 0      # manual=100, w2s=80, strong_watch=60, subject_pool=40

    @property
    def api_stock_id(self) -> str:
        """去掉 .SZ/.SH 后缀，供 JYHF API 使用。"""
        return self.stock_id.replace(".SZ", "").replace(".SH", "").replace(".sz", "").replace(".sh", "")


class JyhfMarketUniverse:
    """P1-B: 合并 manual watchlist + strong_watch_pool + w2s_candidates + subject_pool。"""

    def __init__(self, watchlist_path: str):
        self._path = Path(watchlist_path)
        self._manual: dict = {"watch_stocks": [], "watch_subjects": []}

        # 多来源合并结果
        self._stocks: dict[str, UniverseStock] = {}
        self._subjects: set[str] = set()
        self._breakdown: dict[str, int] = {}

    # ── public ──

    def load_manual(self) -> dict:
        """加载手动 watchlist。返回 raw dict。"""
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
        """合并所有来源，构建统一候选池。

        Returns:
            {"watch_stocks": [...], "watch_subjects": [...],
             "api_stock_ids": [...], "source_breakdown": {...}}
        """
        self._stocks.clear()
        self._subjects = set(_DEFAULT_SUBJECTS)

        # 1. manual (最高优先级)
        for sid in self._manual.get("watch_stocks", []):
            norm = _normalize_stock_id(sid)
            self._add_stock(norm, source="manual", priority=100)

        for sid in self._manual.get("watch_subjects", []):
            self._subjects.add(str(sid))

        # 2. w2s candidates
        if w2s_stocks:
            for s in w2s_stocks:
                sid = _normalize_stock_id(str(s.get("stock_id", "")))
                name = str(s.get("stock_name", ""))
                self._add_stock(sid, name=name, source="w2s", priority=80)

        # 3. strong_watch pool
        if strong_watch_stocks:
            for s in strong_watch_stocks:
                sid = _normalize_stock_id(str(s.get("stock_id", "")))
                name = str(s.get("stock_name", ""))
                self._add_stock(sid, name=name, source="strong_watch", priority=60)

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

        result = {
            "watch_stocks": [s.stock_id for s in stock_list],
            "watch_subjects": sorted(self._subjects),
            "api_stock_ids": [s.api_stock_id for s in stock_list],
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

        logger.info("Universe merged: %d stocks (%s)", len(stock_list), self._breakdown)
        return result

    def get_stocks(self) -> list[str]:
        """获取内部格式 stock_id 列表。"""
        return [s.stock_id for s in self._stocks.values()]

    def get_api_stock_ids(self) -> list[str]:
        """获取 JYHF API 格式 stock_id（纯数字）。"""
        return [s.api_stock_id for s in self._stocks.values()]

    def get_subjects(self) -> list[str]:
        return sorted(self._subjects)

    @property
    def breakdown(self) -> dict[str, int]:
        return dict(self._breakdown)

    # ── private ──

    def _add_stock(self, stock_id: str, name: str = "", source: str = "", priority: int = 0) -> None:
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

    def _ensure_default_manual(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        default = {"watch_stocks": ["002795"], "watch_subjects": ["9019807"]}
        self._path.write_text(json.dumps(default, ensure_ascii=False, indent=2))
        self._manual = default


def _normalize_stock_id(raw: str) -> str:
    """统一为 XXXX.SZ / XXXX.SH 格式。"""
    s = raw.strip().upper()
    if "." in s:
        return s
    if len(s) == 6:
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        elif s.startswith(("0", "3")):
            return f"{s}.SZ"
    return s

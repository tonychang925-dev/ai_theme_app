"""题材热度排名 — 统一 Producer 协议.

SubjectRankProducer: 可插拔数据源抽象
  - JyhfSubjectRankProducer (默认)
  - SnapshotAggSubjectRankProducer

force 与 on_existing 优先级:
  force=false + on_existing=skip     → 已有则跳过
  force=false + on_existing=upsert   → ON CONFLICT DO UPDATE
  force=false + on_existing=replace  → 先删再重建
  force=true                         → 等价于 on_existing=replace
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


OnExistingMode = Literal["skip", "upsert", "replace"]


@dataclass
class SubjectRankBuildRequest:
    trade_date: date
    force: bool = False
    batch_id: str | None = None
    provider: str = "jyhf"
    on_existing: OnExistingMode = "skip"

    def resolved_on_existing(self) -> OnExistingMode:
        """force=true 等价于 replace."""
        return "replace" if self.force else self.on_existing


@dataclass
class SubjectRankBuildResult:
    provider: str
    trade_date: str
    status: str                          # ok / ok_existing / ok_no_data / failed
    affected_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class SubjectRankProducer(ABC):
    """题材热度排名 Producer — 可插拔数据源."""

    @abstractmethod
    async def build(
        self,
        request: SubjectRankBuildRequest,
    ) -> SubjectRankBuildResult:
        ...

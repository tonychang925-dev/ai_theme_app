"""Producer 工厂 — 按 provider 名称返回 Producer 实例."""
from __future__ import annotations

from stock_processing_service.application.jobs.subject_stock_snapshot.base import (
    SubjectStockDailySnapshotProducer,
)


class SubjectStockSnapshotProducerFactory:
    def __init__(
        self,
        jyhf_producer: SubjectStockDailySnapshotProducer | None = None,
        tushare_join_producer: SubjectStockDailySnapshotProducer | None = None,
    ):
        self._producers: dict[str, SubjectStockDailySnapshotProducer] = {}
        if jyhf_producer is not None:
            self._producers[jyhf_producer.provider] = jyhf_producer
        if tushare_join_producer is not None:
            self._producers[tushare_join_producer.provider] = tushare_join_producer

    def get(self, provider: str) -> SubjectStockDailySnapshotProducer:
        if provider not in self._producers:
            raise ValueError(
                f"unsupported subject_stock_daily_snapshot provider: {provider!r}. "
                f"available: {sorted(self._producers)}"
            )
        return self._producers[provider]

    @property
    def available_providers(self) -> list[str]:
        return sorted(self._producers)

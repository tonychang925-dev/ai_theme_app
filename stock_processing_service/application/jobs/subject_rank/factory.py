"""Producer 工厂 — 按 provider 名称返回 Producer 实例."""
from __future__ import annotations

from stock_processing_service.application.jobs.subject_rank.base import (
    SubjectRankProducer,
)


class SubjectRankProducerFactory:
    def __init__(
        self,
        jyhf_producer: SubjectRankProducer | None = None,
        snapshot_agg_producer: SubjectRankProducer | None = None,
    ):
        self._producers: dict[str, SubjectRankProducer] = {}
        if jyhf_producer is not None:
            self._producers[jyhf_producer.provider] = jyhf_producer
        if snapshot_agg_producer is not None:
            self._producers[snapshot_agg_producer.provider] = snapshot_agg_producer

    def get(self, provider: str) -> SubjectRankProducer:
        if provider not in self._producers:
            raise ValueError(
                f"unsupported subject_rank provider: {provider!r}. "
                f"available: {sorted(self._producers)}"
            )
        return self._producers[provider]

    @property
    def available_providers(self) -> list[str]:
        return sorted(self._producers)

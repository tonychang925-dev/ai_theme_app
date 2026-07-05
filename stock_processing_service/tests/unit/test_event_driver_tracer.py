from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from stock_processing_service.application.services.event_driver_tracer import (
    EventDriverTracer,
)


class _MatrixThemeTracer(EventDriverTracer):
    def __init__(self) -> None:
        super().__init__(pool=None)
        self.traced_subject_keys: list[str] = []

    async def _resolve_subject_keys_by_theme_names(
        self,
        theme_names: list[str],
    ) -> dict[str, list[str]]:
        assert "创新药/医疗" in theme_names
        return {
            "创新药/医疗": ["9025631"],
            "芯片产业链/半导体": ["9013944"],
        }

    async def trace(
        self,
        subject_keys: list[str],
        trade_date: date,
        *,
        lookback_days: int = 3,
        per_theme_limit: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        del trade_date, lookback_days, per_theme_limit
        self.traced_subject_keys = subject_keys
        return {
            "9014636": [
                {
                    "event_id": 1,
                    "summary": "机器人事件",
                    "event_time": "2026-07-02T09:00:00",
                    "confidence": 0.9,
                    "match_reason": "机器人",
                }
            ],
            "9025631": [
                {
                    "event_id": 2,
                    "summary": "创新药事件",
                    "event_time": "2026-07-02T10:00:00",
                    "confidence": 0.95,
                    "match_reason": "创新药",
                }
            ],
            "9013944": [
                {
                    "event_id": 3,
                    "summary": "半导体事件",
                    "event_time": "2026-07-01T10:00:00",
                    "confidence": 0.85,
                    "match_reason": "半导体",
                }
            ],
        }


@pytest.mark.asyncio
async def test_tc_recap_coverage_001_traces_every_matrix_theme_and_maps_reason_keys() -> None:
    tracer = _MatrixThemeTracer()
    rows = [
        {"subject_key": "9014636", "theme_name": "机器人"},
        {
            "subject_key": "reason:创新药/医疗",
            "theme_name": "创新药/医疗",
        },
        {
            "subject_key": "reason:芯片产业链/半导体",
            "theme_name": "芯片产业链/半导体",
        },
        {"subject_key": "other", "theme_name": "其他"},
    ]

    result = await tracer.trace_theme_rows(
        rows,
        date(2026, 7, 2),
        per_theme_limit=2,
    )

    assert set(tracer.traced_subject_keys) == {"9014636", "9025631", "9013944"}
    by_key = {row["subject_key"]: row for row in result}
    assert by_key["9014636"]["driver_events"][0]["summary"] == "机器人事件"
    assert (
        by_key["reason:创新药/医疗"]["driver_events"][0]["summary"]
        == "创新药事件"
    )
    assert (
        by_key["reason:芯片产业链/半导体"]["driver_events"][0]["summary"]
        == "半导体事件"
    )
    assert by_key["other"]["driver_events"] == []

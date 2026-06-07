from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.mainline_lifecycle.mainline_lifecycle_fact_context_builder import (
    MainlineLifecycleFactContextBuilder,
)


class _ReadPort:
    async def get_active_confirmed_mainlines(self, trade_date: date, limit: int = 100):
        assert trade_date == date(2026, 5, 6)
        return [
            {
                "mainline_id": "ml_AI光纤_202606",
                "mainline_name": "AI光纤",
                "canonical_subject_key": "9064103",
                "related_subject_keys_json": ["9064103"],
                "branch_subject_keys_json": [],
                "identity_status": "confirmed",
            }
        ]

    async def get_confirmed_mainlines(self, *args, **kwargs):  # pragma: no cover - guard rail
        raise AssertionError("builder must prefer get_active_confirmed_mainlines")

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        assert subject_keys == ["9064103"]
        return [
            {
                "subject_key": "9064103",
                "final_cycle_state": "divergence",
                "final_mainline_alive": True,
            }
        ]

    async def get_subject_cycle_evidence_daily(self, trade_date: date, subject_keys: list[str] | None = None):
        assert subject_keys == ["9064103"]
        return [
            {
                "subject_key": "9064103",
                "event_continuity_score": 88,
            }
        ]


@pytest.mark.asyncio
async def test_mainline_lifecycle_fact_context_prefers_active_confirmed_mainlines() -> None:
    builder = MainlineLifecycleFactContextBuilder(_ReadPort())
    ctx = await builder.build(trade_date=date(2026, 5, 6))

    assert ctx.diagnostics["confirmed_count"] == 1
    assert ctx.diagnostics["layer_b_judgement_count"] == 1
    assert ctx.diagnostics["layer_b_evidence_count"] == 1
    assert ctx.confirmed_mainlines[0]["canonical_subject_key"] == "9064103"

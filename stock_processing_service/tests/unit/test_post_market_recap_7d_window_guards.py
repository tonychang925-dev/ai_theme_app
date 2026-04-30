from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from stock_processing_service.application.jobs.build_post_market_recap_job import BuildPostMarketRecapJob


class _Dummy:
    pass


def _mk_row(stock_id: str, d: date, support: str = "70") -> SimpleNamespace:
    return SimpleNamespace(
        trade_date=d,
        stock_id=stock_id,
        stock_name="S",
        subject_key="K",
        subject_name="N",
        watch_status="active",
        strong_grade="A",
        watch_score="80",
        support_type="previous_low",
        support_level="10",
        support_score=support,
        support_refs=["x"],
        support_count=1,
        support_combined_strength="70",
        role_tags={"final_cycle_state": "repair", "transition_type": "upgrade", "transition_confidence": "0.8"},
        mainline_context_score="80",
        strong_gene_score="75",
        weakness_tolerance_score="70",
        prior7_limitup_days=2,
        prior7_strong_days=3,
        prior7_best_watch_score="85",
        prior7_peak_rank=1,
        pool_rank=1,
        kept_because="",
        admission_status="formal",
        pool_entry_type="formal",
        metadata={"candidate_source": "strong_watch_pool"},
    )


def test_build_candidate_input_rows_prefers_same_day_row_over_prior_history() -> None:
    job = BuildPostMarketRecapJob(read_port=_Dummy(), write_port=_Dummy(), event_port=_Dummy(), idempotency_port=_Dummy())
    td = date(2026, 4, 22)

    prior = [_mk_row("A", date(2026, 4, 21), support="78")]
    current = [_mk_row("A", td, support="65")]

    rows = job._build_candidate_input_rows(trade_date=td, strong_watch_rows=current, prior_watch_rows=prior)
    assert len(rows) == 1
    assert str(rows[0].metadata.get("support_score")) == "65"


def test_get_prior_rows_blocks_time_travel() -> None:
    class _Read:
        async def get_prior_strong_watch_pool_rows(self, *, trade_date, lookback_days):
            return [
                _mk_row("A", date(2026, 4, 21)),
                _mk_row("B", date(2026, 4, 22)),
                _mk_row("C", date(2026, 4, 23)),
            ]

    job = BuildPostMarketRecapJob(read_port=_Read(), write_port=_Dummy(), event_port=_Dummy(), idempotency_port=_Dummy())

    import asyncio

    out = asyncio.run(job._get_prior_strong_watch_rows(trade_date=date(2026, 4, 22), lookback_days=7))
    assert len(out) == 1
    assert out[0].stock_id == "A"

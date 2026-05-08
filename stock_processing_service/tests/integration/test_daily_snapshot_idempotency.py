from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.application.jobs import BuildDailySnapshotJob
from stock_processing_service.contracts.dto import (
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectStockPoolDTO,
    TradeCalendarDTO,
)


class _ReadPort:
    async def get_trade_calendar(self, trade_date: date):
        return TradeCalendarDTO(trade_date=trade_date, calendar_is_open=True)

    async def get_stock_daily_bars(self, trade_date: date, stock_ids=None):
        return [
            StockBarDTO(
                trade_date=trade_date,
                stock_id="000001.SZ",
                stock_name="PingAn",
                open_price=Decimal("10"),
                high_price=Decimal("11"),
                low_price=Decimal("9.8"),
                close_price=Decimal("10.8"),
                pre_close=Decimal("10"),
                pct_chg=Decimal("8"),
                volume=Decimal("100000"),
                amount=Decimal("1000000"),
                limit_up_price=Decimal("11"),
                limit_down_price=Decimal("9"),
            )
        ]

    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids=None):
        return []

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
        return [
            SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key="robotics",
                subject_name="Robotics",
                stock_id="000001.SZ",
                stock_name="PingAn",
                pool_rank=1,
            )
        ]

    async def get_subject_context_by_subject_keys(self, subject_keys, trade_date: date):
        return [
            SubjectContextDTO(
                trade_date=trade_date,
                subject_key="robotics",
                subject_name="Robotics",
                theme_context_tags=["policy"],
            )
        ]

    async def get_prior_stock_daily_snapshots(self, trade_date: date, lookback_days: int, stock_ids=None):
        return [
            PriorSnapshotDTO(
                trade_date=date(2026, 4, 22),
                stock_id="000001.SZ",
                snapshot_version="v-prev",
                payload={"final_cycle_state": "divergence"},
            )
        ]

    async def get_subject_cycle_evidence_daily(self, trade_date: date, subject_keys=None):
        return [
            {
                "subject_key": "robotics",
                "trade_date": trade_date,
                "theme_name": "Robotics",
                "event_strength_score": Decimal("80"),
                "event_continuity_score": Decimal("70"),
                "strong_event_count_7d": 1,
                "event_recency_days": 1,
                "leader_alive_score": Decimal("90"),
                "leader_breakdown_flag": False,
                "relay_strength_score": Decimal("70"),
                "front_row_survival_ratio": Decimal("1"),
                "limit_up_count": 1,
                "limit_down_count": 0,
                "red_ratio": Decimal("0.80"),
                "big_drop_ratio": Decimal("0.00"),
                "front_row_strength_score": Decimal("75"),
                "theme_support_score": Decimal("72"),
                "break_start_pivot": False,
                "evidence_json": {"previous_cycle_state": "divergence"},
            }
        ]


class _WritePort:
    def __init__(self):
        self.daily_calls = 0

    async def upsert_theme_cycle_judgement_v2_rows(self, rows):
        return len(rows)

    async def upsert_stock_daily_strategy_snapshot_rows(self, rows):
        self.daily_calls += 1
        return len(rows)

    async def upsert_subject_stock_daily_snapshot_rows(self, rows):
        return len(rows)

    async def upsert_stock_abnormal_event_rows(self, rows):
        return len(rows)

    async def upsert_theme_stock_leaderboard_rows(self, rows):
        return len(rows)

    async def upsert_pre_market_brief_snapshot(self, doc):
        return 1

    async def upsert_post_market_recap_snapshot(self, doc):
        return 1


class _EventPort:
    async def publish_stock_processing_event(self, event):
        return "ok"

    async def record_dead_letter(self, event_name, payload, reason):
        return "ok"


class _IdempotencyPort:
    def __init__(self):
        self._seen = False

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int):
        if self._seen:
            return False
        self._seen = True
        return True

    async def mark_job_completed(self, job_key: str, metadata=None):
        return None


async def _run_job_twice():
    write_port = _WritePort()
    job = BuildDailySnapshotJob(
        read_port=_ReadPort(),
        write_port=write_port,
        event_port=_EventPort(),
        idempotency_port=_IdempotencyPort(),
        cache_port=None,
    )

    first = await job.execute(
        trade_date=date(2026, 4, 23),
        snapshot_version="v1",
        batch_id="b1",
        trace_id="t1",
    )
    second = await job.execute(
        trade_date=date(2026, 4, 23),
        snapshot_version="v1",
        batch_id="b1",
        trace_id="t1",
    )
    return first, second, write_port.daily_calls


def test_daily_snapshot_idempotency() -> None:
    import asyncio

    first, second, daily_calls = asyncio.run(_run_job_twice())
    assert first.status == "ok"
    assert second.status == "skipped_idempotent"
    assert daily_calls == 1

"""Integration test for BuildPostMarketRecapJob — v2 seed-query architecture."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.application.jobs import BuildPostMarketRecapJob
from stock_processing_service.application.use_cases.build_strong_stock_tracking import (
    LAYER_C_INPUT_MODE,
    BuildStrongStockTrackingUseCase,
)
from stock_processing_service.application.use_cases.build_weak_to_strong_candidate import (
    BuildWeakToStrongCandidateUseCase,
)
from stock_processing_service.contracts.dto import (
    MainlineCycleDTO,
    MainlineIdentityDTO,
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectStockPoolDTO,
)
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidate


# ── Fake Read Port (with new Layer C gateway methods) ──

class _FakeReadPort:
    async def get_trade_calendar(self, trade_date: date):
        return None

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        return [
            StockBarDTO(
                trade_date=trade_date, stock_id="002000.SZ", stock_name="SampleA",
                open_price=Decimal("12"), high_price=Decimal("13"), low_price=Decimal("11.8"),
                close_price=Decimal("12.9"), pre_close=Decimal("12"), pct_chg=Decimal("7.5"),
                volume=Decimal("30000"), amount=Decimal("350000"),
                limit_up_price=Decimal("13.2"), limit_down_price=Decimal("10.8"),
            )
        ]

    async def get_stock_daily_bars_range(self, start_date: date, end_date: date, stock_ids=None):
        bars = await self.get_stock_daily_bars(end_date, stock_ids=stock_ids)
        return [bar for bar in bars if start_date <= bar.trade_date <= end_date]

    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids=None):
        return []

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
        return []

    async def get_legacy_strong_watch_candidate_inputs(self, trade_date: date, lookback_days: int = 7):
        return []

    async def get_w2s_candidate_inputs(self, trade_date: date):
        return []

    # ── New Layer C gateway methods ──

    async def get_strong_watch_seed_rows(self, trade_date: date, lookback_days: int = 7) -> list[dict[str, Any]]:
        """Return one seed candidate matching old-chain _fetch_seed_rows output format."""
        return [
            {
                "stock_id": "002000.SZ",
                "stock_name": "SampleA",
                "subject_key": "ai_chip",
                "theme_name": "AI Chip",
                "recent_limit_up_count": 2,
                "is_leader_flag": 1,
                "best_rank": 1,
                "current_flag_today": 2,
                "is_main_theme": True,
                "identity_status": "confirmed",
                "final_mainline_alive": True,
                "mainline_strength_score": 72.0,
                "subject_limit_up_count": 2,
                "subject_strong_count": 3,
                "cond_gene": 1,
                "cond_volume": 1,
                "cond_structure": 1,
            }
        ]

    async def get_strong_watch_refresh_rows(self, trade_date: date) -> list[dict[str, Any]]:
        return []

    async def get_subject_board_stats(self, trade_date: date) -> list[dict[str, Any]]:
        return [
            {"subject_key": "ai_chip", "subject_limit_up_count": 2, "subject_strong_count": 3},
        ]

    async def get_stock_position_judgement(self, trade_date: date, stock_ids=None) -> list[dict[str, Any]]:
        return [
            {"stock_id": "002000.SZ", "position_label": "突破前高",
             "ma_alignment_status": "均线多头", "trend_strength_score": 75.0},
        ]

    async def get_stock_pattern_judgement(self, trade_date: date, stock_ids=None) -> list[dict[str, Any]]:
        return [
            {"stock_id": "002000.SZ",
             "pattern_labels": ["高量不破"],
             "volume_pattern_status": "放量上涨",
             "breakout_status": "放量突破",
             "pullback_status": "缩量回踩",
             "risk_pattern_status": ""},
        ]

    async def get_subject_context_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return []

    async def get_prior_stock_daily_snapshots(self, trade_date: date, lookback_days: int, stock_ids=None):
        return [
            PriorSnapshotDTO(trade_date=trade_date, stock_id="002000.SZ",
                             snapshot_version="v-prev", payload={"pct_chg": "3.0"}),
        ]

    async def get_existing_pre_market_brief_snapshot(self, trade_date: date):
        return None

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return None

    async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return [
            MainlineIdentityDTO(subject_key="ai_chip", identity_status="confirmed",
                                is_main_theme=True, first_confirmed_date=trade_date,
                                last_review_date=trade_date, rule_version="test"),
        ]

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return [
            MainlineCycleDTO(trade_date=trade_date, subject_key="ai_chip",
                             final_cycle_state="repair", final_mainline_alive=True),
        ]

    async def get_mainline_identity_rule_inputs(self, trade_date: date, subject_keys: list[str]):
        return []

    async def get_prior_strong_watch_pool_rows(self, trade_date: date, lookback_days: int):
        return []

    async def get_subject_event_stats(self, trade_date: date, subject_keys=None):
        return []

    async def get_subject_cycle_evidence_daily(self, trade_date: date, subject_keys=None):
        return [
            {
                "subject_key": "ai_chip",
                "event_continuity_score": 70,
            }
        ]


# ── Fake ports ──

class _FakeWritePort:
    def __init__(self) -> None:
        self.recap_docs: list[Any] = []
        self.strong_watch_pool_rows: list[dict[str, Any]] = []
        self.strong_watch_history_rows: list[dict[str, Any]] = []
        self.w2s_candidate_pool_rows: list[dict[str, Any]] = []

    async def upsert_stock_daily_snapshot_rows(self, rows): return len(rows)
    async def upsert_subject_stock_daily_snapshot_rows(self, rows): return len(rows)
    async def upsert_stock_abnormal_event_rows(self, rows): return len(rows)
    async def upsert_theme_stock_leaderboard_rows(self, rows): return len(rows)
    async def upsert_pre_market_brief_snapshot(self, doc): return 1

    async def upsert_post_market_recap_snapshot(self, doc):
        self.recap_docs.append(doc)
        return 1

    async def upsert_strong_watch_pool_rows(self, rows, **kwargs):
        self.strong_watch_pool_rows.extend(rows)
        return len(rows)

    async def promote_strong_watch_candidates(self, trade_date):
        return 0

    async def prune_strong_watch_pool(self, trade_date, weakening_min_score=62.0):
        return 0

    async def recompute_strong_watch_window_days(self, stock_ids):
        return len(stock_ids)

    async def upsert_strong_watch_history_rows(self, rows):
        self.strong_watch_history_rows.extend(rows)
        return len(rows)

    async def upsert_theme_mainline_identity_registry_rows(self, rows): return len(rows)
    async def upsert_mainline_identity_review_queue_rows(self, rows): return len(rows)
    async def upsert_theme_cycle_evidence_daily_rows(self, rows): return len(rows)
    async def upsert_weak_to_strong_candidate_pool_rows(self, rows):
        self.w2s_candidate_pool_rows.extend(rows)
        return len(rows)


class _FakeEventPort:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish_stock_processing_event(self, event):
        self.events.append(asdict(event))
        return "msg-1"

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str):
        return "dlq"


class _FakeIdempotencyPort:
    def __init__(self) -> None:
        self.once = False

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        if self.once:
            return False
        self.once = True
        return True

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None:
        return None


class _FakeCachePort:
    def __init__(self) -> None:
        self.cache: dict[str, Any] = {}

    async def get(self, key: str):
        return self.cache.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None):
        self.cache[key] = {"value": value, "ttl": ttl_seconds}

    async def delete(self, key: str):
        self.cache.pop(key, None)
        return 1

    async def invalidate_pattern(self, pattern: str):
        return 0


# ── Tests ──

def test_build_post_market_recap_job_strong_watch_pool_flow() -> None:
    """Smoke test: job runs successfully with seed-query architecture."""

    async def _run() -> None:
        read_port = _FakeReadPort()
        write_port = _FakeWritePort()
        event_port = _FakeEventPort()
        idempotency_port = _FakeIdempotencyPort()
        cache_port = _FakeCachePort()

        job = BuildPostMarketRecapJob(
            read_port=read_port,
            write_port=write_port,
            event_port=event_port,
            idempotency_port=idempotency_port,
            cache_port=cache_port,
        )

        result = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="pm-v2",
            batch_id="bpm2",
            trace_id="tpm2",
        )
        assert result.status == "ok"
        assert result.affected_rows == 1
        assert len(write_port.recap_docs) == 1
        recap_doc = write_port.recap_docs[0].recap_doc
        assert recap_doc["candidate_source"] == "strong_watch_pool"
        assert recap_doc["layer_c_input_mode"] == LAYER_C_INPUT_MODE
        assert recap_doc["layer_a_identity_hit_count"] >= 1
        assert recap_doc["layer_b_cycle_hit_count"] >= 1
        report = recap_doc["report"]
        assert set(report) == {
            "report_type",
            "trade_date",
            "title",
            "summary",
            "highlights",
            "sections",
            "metadata",
        }
        assert report["report_type"] == "post_market"
        assert report["trade_date"] == "2026-04-23"
        assert report["metadata"]["source"] == "stock_processing_service.new_chain"
        assert "theme_environment_judgement" not in str(report)
        assert "theme_leader_candidate" not in str(report)

        # Idempotency check
        skipped = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="pm-v2",
            batch_id="bpm2",
            trace_id="tpm2",
        )
        assert skipped.status == "skipped_idempotent"

    asyncio.run(_run())


def test_build_post_market_recap_job_no_longer_owns_layer_c_or_d_writes() -> None:
    from pathlib import Path
    import stock_processing_service.application.jobs.build_post_market_recap_job as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden_fragments = (
        "build_seed_candidates(",
        "score_watch_row(",
        "watch_pool_results",
        "upsert_strong_watch_pool_rows(",
        "upsert_strong_watch_history_rows(",
        "get_w2s_candidate_inputs(",
        "upsert_weak_to_strong_candidate_pool_rows(",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_build_post_market_recap_job_does_not_call_legacy_recap_service() -> None:
    from pathlib import Path
    import stock_processing_service.application.jobs.build_post_market_recap_job as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden_fragments = (
        "stock_service.repositories.report_repository",
        "stock_service.services.recap_service",
        "ReportRepository",
        "RecapService",
        "build_post_market_report(",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_build_strong_stock_tracking_use_case_writes_layer_c_objects() -> None:
    async def _run() -> None:
        read_port = _FakeReadPort()
        write_port = _FakeWritePort()
        use_case = BuildStrongStockTrackingUseCase(
            read_ports=read_port,
            write_ports=write_port,
            cache_ports=None,
        )

        result = await use_case.execute(trade_date=date(2026, 4, 23), window_days=7)
        assert result.status == "ok"
        assert result.metrics["layer_c_input_mode"] == LAYER_C_INPUT_MODE
        assert result.metrics["history_written"] == 1
        assert len(write_port.strong_watch_pool_rows) == 1
        assert len(write_port.strong_watch_history_rows) == 1

    asyncio.run(_run())


def test_build_weak_to_strong_candidate_use_case_writes_d1_pool() -> None:
    class _D1ReadPort(_FakeReadPort):
        async def get_w2s_candidate_inputs(self, trade_date: date):
            return [
                {
                    "trade_date": trade_date,
                    "stock_id": "002000.SZ",
                    "stock_name": "SampleA",
                    "subject_key": "ai_chip",
                    "theme_name": "AI Chip",
                    "pct_chg": -3.0,
                    "limit_up": False,
                    "is_leader": True,
                    "rank_order": 1,
                    "recent_limit_up_count": 2,
                    "prior7_limitup_days": 2,
                    "prior7_strong_days": 3,
                    "prev_day_pct_chg": 5.0,
                    "prev_day_limit_up": True,
                    "fade_watch": False,
                    "fade_confirmed": False,
                    "mainline_strength_score": 72.0,
                    "watch_score": 80.0,
                    "watch_pool_entry_type": "formal",
                    "watch_labels_json": {"strong_grade": "A", "support_type": "ma_support", "support_score": 66},
                    "support_level": "12.0",
                    "final_cycle_state": "repair",
                }
            ]

    async def _run() -> None:
        read_port = _D1ReadPort()
        write_port = _FakeWritePort()
        use_case = BuildWeakToStrongCandidateUseCase(
            read_ports=read_port,
            write_ports=write_port,
        )

        result = await use_case.execute(trade_date=date(2026, 4, 23))
        assert result.status == "ok"
        assert result.metrics["d1_total_in"] == 1
        assert len(write_port.w2s_candidate_pool_rows) == result.affected_rows

    asyncio.run(_run())


def test_build_post_market_recap_job_idempotency() -> None:
    """Verify idempotency blocks duplicate runs."""

    async def _run() -> None:
        read_port = _FakeReadPort()
        write_port = _FakeWritePort()
        event_port = _FakeEventPort()
        idempotency_port = _FakeIdempotencyPort()
        cache_port = _FakeCachePort()

        job = BuildPostMarketRecapJob(
            read_port=read_port,
            write_port=write_port,
            event_port=event_port,
            idempotency_port=idempotency_port,
            cache_port=cache_port,
        )

        r1 = await job.execute(trade_date=date(2026, 4, 23), snapshot_version="pm-v3",
                                batch_id="bpm3", trace_id="tpm3")
        assert r1.status == "ok"

        r2 = await job.execute(trade_date=date(2026, 4, 23), snapshot_version="pm-v3",
                                batch_id="bpm3", trace_id="tpm3")
        assert r2.status == "skipped_idempotent"
        assert r2.batch_id == "bpm3"

    asyncio.run(_run())


def test_build_post_market_recap_job_missing_layer_b_cycle_fail_fast() -> None:
    class _MissingCycleReadPort(_FakeReadPort):
        async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
            return []

    async def _run() -> None:
        read_port = _MissingCycleReadPort()
        write_port = _FakeWritePort()
        job = BuildPostMarketRecapJob(
            read_port=read_port,
            write_port=write_port,
            event_port=_FakeEventPort(),
            idempotency_port=_FakeIdempotencyPort(),
            cache_port=_FakeCachePort(),
        )

        try:
            await job.execute(
                trade_date=date(2026, 4, 23),
                snapshot_version="pm-missing-cycle",
                batch_id="bpm-missing",
                trace_id="tpm-missing",
            )
        except RuntimeError as exc:
            assert "missing Layer B cycle truth" in str(exc)
        else:
            raise AssertionError("expected fail-fast when Layer B cycle truth is missing")
        assert write_port.recap_docs == []

    asyncio.run(_run())


def test_layer_c_contract_multi_limitup_still_requires_layer_a_b() -> None:
    """Contract: multi-limit-up strong signals are not independent leaders without A/B truth."""
    class _MultiLimitupMissingCycleReadPort(_FakeReadPort):
        async def get_strong_watch_seed_rows(self, trade_date: date, lookback_days: int = 7) -> list[dict[str, Any]]:
            rows = await super().get_strong_watch_seed_rows(trade_date, lookback_days)
            rows[0]["recent_limit_up_count"] = 3
            rows[0]["has_two_board"] = False
            rows[0]["three_days_two_boards"] = True
            rows[0]["recent_multi_limitup"] = True
            return rows

        async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date):
            return []

        async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
            return []

    async def _run() -> None:
        read_port = _MultiLimitupMissingCycleReadPort()
        write_port = _FakeWritePort()
        job = BuildPostMarketRecapJob(
            read_port=read_port,
            write_port=write_port,
            event_port=_FakeEventPort(),
            idempotency_port=_FakeIdempotencyPort(),
            cache_port=_FakeCachePort(),
        )

        try:
            await job.execute(
                trade_date=date(2026, 4, 23),
                snapshot_version="pm-multi-limitup",
                batch_id="bpm-multi-limitup",
                trace_id="tpm-multi-limitup",
            )
        except RuntimeError as exc:
            assert "missing Layer B cycle truth" in str(exc)
        else:
            raise AssertionError("expected multi-limit-up strong signal to require Layer A/B truth")
        assert write_port.strong_watch_history_rows == []
        assert write_port.recap_docs == []

    asyncio.run(_run())


def test_layer_c_contract_two_board_enters_pool_without_layer_a_b_state() -> None:
    """Contract: docs §13.3.3 requires two-board stocks to enter via independent_leader."""
    class _TwoBoardMissingCycleReadPort(_FakeReadPort):
        async def get_strong_watch_seed_rows(self, trade_date: date, lookback_days: int = 7) -> list[dict[str, Any]]:
            rows = await super().get_strong_watch_seed_rows(trade_date, lookback_days)
            rows[0]["has_two_board"] = True
            rows[0]["is_main_theme"] = False
            rows[0]["identity_status"] = "observed"
            return rows

        async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date):
            return []

        async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
            return []

    async def _run() -> None:
        read_port = _TwoBoardMissingCycleReadPort()
        write_port = _FakeWritePort()
        job = BuildPostMarketRecapJob(
            read_port=read_port,
            write_port=write_port,
            event_port=_FakeEventPort(),
            idempotency_port=_FakeIdempotencyPort(),
            cache_port=_FakeCachePort(),
        )

        result = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="pm-two-board",
            batch_id="bpm-two-board",
            trace_id="tpm-two-board",
        )
        assert result.status == "ok"
        assert len(write_port.strong_watch_history_rows) == 1
        labels = write_port.strong_watch_history_rows[0]["labels_json"]
        assert labels["entry_path"] == "independent_leader"
        assert labels["identity_scope"] == "independent_stock_signal"
        assert labels["strong_gene_seed"] is True
        for forbidden_key in (
            "mainline_identity_confirmed",
            "final_mainline_alive",
            "cycle_state",
            "fade_watch",
            "fade_confirmed",
            "mainline_strength_score",
        ):
            assert forbidden_key not in labels
        evidence = write_port.strong_watch_history_rows[0]["evidence_json"]
        assert evidence["entry_path"] == "independent_leader"
        assert evidence["identity_scope"] == "independent_stock_signal"
        assert evidence["strong_gene_seed"] is True
        for forbidden_key in (
            "final_mainline_alive",
            "cycle_state",
            "mainline_strength_score",
        ):
            assert forbidden_key not in evidence

    asyncio.run(_run())

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
from stock_processing_service.application.services.new_chain_post_market_report_builder import (
    NewChainPostMarketReportBuilder,
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
        assert [section["heading"] for section in report["sections"]] == [
            "大盘环境总结",
            "板块环境总结",
            "主线与支线",
            "主线资金流入前10",
            "周期与动作",
            "主线迁移监控",
            "强势股分层",
            "次日观察清单",
            "主线股票资金流入前20",
            "当日异动股与资金行为",
            "资金行为增强",
            "龙虎榜",
        ]

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
        "upsert_weak_to_strong_candidate_pool_rows(",
        "BuildWeakToStrongCandidateUseCase(",
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


def test_new_chain_report_builder_groups_dragon_tiger_by_hot_money_seat() -> None:
    report = NewChainPostMarketReportBuilder().build(
        {
            "trade_date": "2026-05-19",
            "candidate_count": 1,
            "candidate_count_formal": 1,
            "top_candidates": [
                {
                    "stock_id": "002000.SZ",
                    "stock_name": "SampleA",
                    "subject_key": "ai_chip",
                    "theme_name": "AI Chip",
                    "candidate_score": 99,
                }
            ],
            "report_context": {
                "theme_name_map": {"ai_chip": "AI Chip"},
                "dragon_tiger": [
                    {
                        "stock_id": "002000.SZ",
                        "stock_name": "SampleA",
                        "subject_key": "ai_chip",
                        "theme_name": "AI Chip",
                        "net_amount": 200000000,
                        "seat_summary": [
                            "买入席位 上海分公司 净额 200000000",
                        ],
                    }
                ],
            },
        }
    )

    dragon_section = next(section for section in report["sections"] if section["heading"] == "龙虎榜")
    assert dragon_section["items"] == [
        "章盟主系：AI Chip / SampleA(002000) / 买入2.00亿",
    ]


def test_new_chain_report_builder_dragon_tiger_does_not_fallback_to_watch_rows() -> None:
    report = NewChainPostMarketReportBuilder().build(
        {
            "trade_date": "2026-05-21",
            "strong_watch_history": [
                {
                    "stock_id": "002000.SZ",
                    "stock_name": "SampleA",
                    "subject_key": "ai_chip",
                    "subject_name": "AI Chip",
                }
            ],
            "report_context": {"dragon_tiger": []},
        }
    )

    dragon_section = next(section for section in report["sections"] if section["heading"] == "龙虎榜")
    assert dragon_section["items"] == ["暂无龙虎榜新链数据"]


def test_new_chain_report_builder_uses_theme_capital_in_mainline_section() -> None:
    report = NewChainPostMarketReportBuilder().build(
        {
            "trade_date": "2026-05-20",
            "candidate_count": 1,
            "candidate_count_formal": 1,
            "top_candidates": [
                {
                    "stock_id": "002000.SZ",
                    "stock_name": "SampleA",
                    "subject_key": "ai_chip",
                    "theme_name": "AI Chip",
                    "candidate_score": 99,
                }
            ],
            "report_context": {
                "theme_name_map": {"ai_chip": "AI Chip"},
                "theme_capital_flow": [
                    {
                        "subject_key": "ai_chip",
                        "resolved_theme_name": "AI Chip",
                        "main_net_inflow_sum": 320000000,
                        "leader_main_net_inflow": 120000000,
                        "top3_main_net_inflow_sum": 260000000,
                    }
                ],
                "stock_facts": [
                    {
                        "stock_id": "002000",
                        "stock_name": "SampleA",
                        "subject_key": "ai_chip",
                        "main_net_inflow": 88000000,
                        "money_flow_score": 99,
                        "leader_composite_score": 88,
                        "leader_capital_score": 77,
                        "leader_candidate_rank": 1,
                        "rank_order": 1,
                    }
                ],
            },
        }
    )

    mainline_section = next(section for section in report["sections"] if section["heading"] == "主线与支线")
    assert "总净流入 3.20亿" in mainline_section["items"][0]
    assert "龙头净流入 1.20亿" in mainline_section["items"][0]

    strong_section = next(section for section in report["sections"] if section["heading"] == "强势股分层")
    assert "综合分 88" in strong_section["items"][0]
    assert "资金量能 77.00" in strong_section["items"][0]

    stock_capital_section = next(section for section in report["sections"] if section["heading"] == "主线股票资金流入前20")
    assert "主力净流入 0.88亿" in stock_capital_section["items"][0]


def test_new_chain_report_builder_recap_sections_use_facts_without_d1_candidates() -> None:
    report = NewChainPostMarketReportBuilder().build(
        {
            "trade_date": "2026-05-21",
            "candidate_count": 0,
            "candidate_count_formal": 0,
            "candidate_count_observe": 0,
            "top_candidates": [],
            "formal_top_candidates": [],
            "observe_candidates": [],
            "report_context": {
                "theme_name_map": {"ai_chip": "AI Chip"},
                "cycles": [
                    {
                        "subject_key": "ai_chip",
                        "theme_name": "AI Chip",
                        "final_cycle_state": "repair",
                        "final_mainline_alive": True,
                        "mainline_strength_score": 82,
                        "fade_risk_score": 18,
                    }
                ],
                "theme_capital_flow": [
                    {
                        "subject_key": "ai_chip",
                        "resolved_theme_name": "AI Chip",
                        "final_cycle_state": "repair",
                        "main_net_inflow_sum": 320000000,
                        "leader_main_net_inflow": 120000000,
                        "top3_main_net_inflow_sum": 260000000,
                    }
                ],
                "stock_facts": [
                    {
                        "stock_id": "002000.SZ",
                        "stock_name": "SampleA",
                        "subject_key": "ai_chip",
                        "theme_name": "AI Chip",
                        "rank_order": 1,
                        "pct_chg": 7.5,
                        "is_leader": True,
                        "main_net_inflow": 88000000,
                        "money_flow_score": 96,
                        "trend_strength_score": 75,
                        "position_label": "突破前高",
                        "pattern_labels": ["高量不破"],
                        "volume_ratio": 2.1,
                        "turnover_rate": 11.2,
                        "current_flag": 2,
                    }
                ],
            },
        }
    )

    mainline_section = next(section for section in report["sections"] if section["heading"] == "主线与支线")
    strong_section = next(section for section in report["sections"] if section["heading"] == "强势股分层")
    watch_section = next(section for section in report["sections"] if section["heading"] == "次日观察清单")
    stock_capital_section = next(section for section in report["sections"] if section["heading"] == "主线股票资金流入前20")

    assert "AI Chip" in mainline_section["items"][0]
    assert "SampleA" in strong_section["items"][0]
    assert "SampleA" in watch_section["items"][0]
    assert "主力净流入 0.88亿" in stock_capital_section["items"][0]


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


def test_theme_lines_event_and_market_scores():
    """验证 主线与支线 section 的事件分/市场分 来自 cycle 数据且正确输出到文本。

    对应设计文档 §13.3.4：复盘主体不依赖 D1 candidate_score，
    事件分 = mainline_strength_score，市场分 = fade_risk_score。
    """
    builder = NewChainPostMarketReportBuilder()

    recap_doc = {
        "trade_date": "2026-05-22",
        "snapshot_version": "test.v1",
        "candidate_count": 5,
        "candidate_count_formal": 3,
        "candidate_count_observe": 2,
        "strong_watch_history_count": 10,
        "strong_watch_pool_written": 10,
        "promoted_pool_preview": [],
        "strong_watch_history": [],
        "top_candidates": [],
        "formal_top_candidates": [],
        "observe_candidates": [],
        "candidate_diagnostics": [],
        "layer_b_cycle_hit_count": 2,
        "layer_a_identity_hit_count": 2,
        "report_context": {
            "theme_name_map": {},
            "market": None,
            "cycles": [
                {
                    "subject_key": "S001",
                    "theme_name": "国产算力",
                    "final_cycle_state": "rebound",
                    "final_mainline_alive": True,
                    "fade_watch": False,
                    "fade_confirmed": False,
                    "mainline_strength_score": 83.20,
                    "fade_risk_score": 12.50,
                },
                {
                    "subject_key": "S002",
                    "theme_name": "AI应用",
                    "final_cycle_state": "divergence",
                    "final_mainline_alive": True,
                    "fade_watch": False,
                    "fade_confirmed": False,
                    "mainline_strength_score": 67.80,
                    "fade_risk_score": 28.00,
                },
            ],
            "stock_facts": [
                {
                    "subject_key": "S001",
                    "stock_id": "000001",
                    "stock_name": "测试股A",
                    "theme_name": "国产算力",
                    "rank_order": 1,
                    "pct_chg": 9.8,
                    "is_leader": True,
                    "leader_composite_score": 85.0,
                    "leader_capital_score": 60.0,
                },
                {
                    "subject_key": "S002",
                    "stock_id": "000002",
                    "stock_name": "测试股B",
                    "theme_name": "AI应用",
                    "rank_order": 1,
                    "pct_chg": 5.2,
                    "is_leader": False,
                    "leader_composite_score": 70.0,
                    "leader_capital_score": 50.0,
                },
            ],
            "theme_capital_flow": [],
            "money_flow": [],
            "abnormal_signals": [],
            "dragon_tiger": [],
        },
    }

    report = builder.build(recap_doc)

    # 验证 section 存在
    sections_by_heading = {sec["heading"]: sec for sec in report["sections"]}
    assert "主线与支线" in sections_by_heading, f"headings: {list(sections_by_heading)}"

    theme_section = sections_by_heading["主线与支线"]
    items = theme_section["items"]
    assert len(items) == 2, f"expected 2 theme lines, got {len(items)}: {items}"

    # 验证每行包含正确的 事件/市场 数值
    # 国产算力：事件=83.20，市场=12.50
    item0 = items[0]
    assert "国产算力" in item0, item0
    assert "事件 83.20" in item0, f"missing '事件 83.20' in: {item0}"
    assert "市场 12.50" in item0, f"missing '市场 12.50' in: {item0}"

    # AI应用：事件=67.80，市场=28.00
    item1 = items[1]
    assert "AI应用" in item1, item1
    assert "事件 67.80" in item1, f"missing '事件 67.80' in: {item1}"
    assert "市场 28.00" in item1, f"missing '市场 28.00' in: {item1}"

    # 验证 debug metadata
    debug = report["metadata"].get("theme_line_debug")
    assert debug is not None, "metadata missing theme_line_debug"
    assert len(debug) == 2, f"expected 2 debug entries, got {len(debug)}"

    d0 = debug[0]
    assert d0["theme"] == "国产算力"
    assert d0["subject_key"] == "S001"
    assert d0["cycle_found"] is True
    assert d0["event_score_resolved"] == 83.20
    assert d0["market_score_resolved"] == 12.50
    assert d0["event_score_source"] == "cycle"
    assert d0["market_score_source"] == "cycle"

    d1 = debug[1]
    assert d1["theme"] == "AI应用"
    assert d1["subject_key"] == "S002"
    assert d1["cycle_found"] is True
    assert d1["event_score_resolved"] == 67.80
    assert d1["market_score_resolved"] == 28.00
    assert d1["event_score_source"] == "cycle"
    assert d1["market_score_source"] == "cycle"


def test_theme_lines_missing_cycle_falls_back_to_other_sources():
    """当 cycle 数据缺失时，事件分/市场分从其他数据源兜底。"""
    builder = NewChainPostMarketReportBuilder()

    recap_doc = {
        "trade_date": "2026-05-22",
        "snapshot_version": "test.v1",
        "candidate_count": 0,
        "candidate_count_formal": 0,
        "candidate_count_observe": 0,
        "strong_watch_history_count": 0,
        "strong_watch_pool_written": 0,
        "promoted_pool_preview": [],
        "strong_watch_history": [],
        "top_candidates": [],
        "formal_top_candidates": [],
        "observe_candidates": [],
        "candidate_diagnostics": [],
        "layer_b_cycle_hit_count": 0,
        "layer_a_identity_hit_count": 0,
        "report_context": {
            "theme_name_map": {},
            # cycles 为空 —— 模拟 get_post_market_report_context 返回空的情况
            "cycles": [],
            "stock_facts": [
                {
                    "subject_key": "S001",
                    "stock_id": "000001",
                    "stock_name": "测试股A",
                    "theme_name": "国产算力",
                    "rank_order": 1,
                    "pct_chg": 9.8,
                    "is_leader": True,
                    "leader_composite_score": 85.0,
                    "leader_capital_score": 60.0,
                },
            ],
            "theme_capital_flow": [
                {
                    "subject_key": "S001",
                    "mainline_strength_score": 55.0,
                    "fade_risk_score": 18.0,
                },
            ],
            "money_flow": [],
            "abnormal_signals": [],
            "dragon_tiger": [],
        },
    }

    report = builder.build(recap_doc)
    sections_by_heading = {sec["heading"]: sec for sec in report["sections"]}
    theme_items = sections_by_heading["主线与支线"]["items"]

    # cycle 为空，应从 theme_capital_flow 兜底
    item0 = theme_items[0]
    assert "事件 55.00" in item0, f"missing fallback event score: {item0}"
    assert "市场 18.00" in item0, f"missing fallback market score: {item0}"

    debug = report["metadata"]["theme_line_debug"]
    d0 = debug[0]
    assert d0["cycle_found"] is False
    assert d0["event_score_source"] == "capital"
    assert d0["market_score_source"] == "capital"

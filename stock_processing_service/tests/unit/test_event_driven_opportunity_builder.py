from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.event_driven_opportunity_builder import (
    EventDrivenOpportunityBuilder,
)


class _Gateway:
    def __init__(self, *, subject_rows=None, leaderboard_rows=None, strong_rows=None, w2s_rows=None):
        self.calls: list[str] = []
        self.subject_rows = subject_rows or []
        self.leaderboard_rows = leaderboard_rows or []
        self.strong_rows = strong_rows or []
        self.w2s_rows = w2s_rows or []

    async def get_subject_stock_pool_by_trade_date(self, trade_date):
        self.calls.append("get_subject_stock_pool_by_trade_date")
        return self.subject_rows

    async def get_theme_stock_leaderboard_by_trade_date(self, trade_date, subject_keys=None):
        self.calls.append("get_theme_stock_leaderboard_by_trade_date")
        keys = set(subject_keys or [])
        return [row for row in self.leaderboard_rows if not keys or row.get("subject_key") in keys]

    async def get_strong_stock_watch_view_rows(
        self,
        end_date,
        window_days=7,
        include_removed=False,
        latest_per_stock=True,
        limit=1000,
    ):
        self.calls.append("get_strong_stock_watch_view_rows")
        return self.strong_rows[:limit]

    async def get_w2s_candidates_for_confirm_date(self, confirm_trade_date, limit=1000):
        self.calls.append("get_w2s_candidates_for_confirm_date")
        return self.w2s_rows[:limit]

    async def get_mainline_identity_by_subject_keys(self, subject_keys, trade_date):
        self.calls.append("get_mainline_identity_by_subject_keys")
        return [
            {
                "subject_key": "theme-a",
                "identity_status": "confirmed",
                "is_main_theme": True,
            }
        ]

    async def get_mainline_cycle_by_subject_keys(self, subject_keys, trade_date):
        self.calls.append("get_mainline_cycle_by_subject_keys")
        return [
            {
                "subject_key": "theme-a",
                "final_cycle_state": "acceleration",
                "final_mainline_alive": True,
            }
        ]


@pytest.mark.asyncio
async def test_event_driven_opportunity_builder_returns_empty_without_stock_data():
    gateway = _Gateway()
    builder = EventDrivenOpportunityBuilder(gateway)

    result = await builder.build(
        trade_date=date(2026, 5, 16),
        matched_themes=[{"subject_key": "theme-a", "theme_name": "机器人", "confidence": 0.82}],
        matched_events=[],
    )

    assert result == []
    assert gateway.calls == ["get_subject_stock_pool_by_trade_date"]


@pytest.mark.asyncio
async def test_event_driven_opportunity_builder_scores_existing_candidate_pools_only():
    gateway = _Gateway(
        subject_rows=[
            {
                "subject_key": "theme-a",
                "stock_id": "000001.SZ",
                "stock_name": "核心股份",
                "rank_order": 1,
                "is_leader": True,
            },
            {
                "subject_key": "theme-a",
                "stock_id": "000002.SZ",
                "stock_name": "跟随股份",
                "rank_order": 8,
                "is_leader": False,
            },
        ],
        leaderboard_rows=[
            {
                "subject_key": "theme-a",
                "stock_id": "000001.SZ",
                "leaderboard_rank": 1,
                "leader_score": 92,
            },
            {
                "subject_key": "theme-a",
                "stock_id": "000002.SZ",
                "leaderboard_rank": 8,
                "leader_score": 55,
            },
        ],
        strong_rows=[
            {
                "subject_key": "theme-a",
                "stock_id": "000001.SZ",
                "stock_name": "核心股份",
                "watch_score": 86,
                "cycle_state": "acceleration",
            }
        ],
        w2s_rows=[
            {
                "subject_key": "theme-a",
                "stock_id": "000001.SZ",
                "stock_name": "核心股份",
                "candidate_score": 80,
            }
        ],
    )
    builder = EventDrivenOpportunityBuilder(gateway, max_stocks_per_theme=3)

    result = await builder.build(
        trade_date=date(2026, 5, 16),
        matched_themes=[
            {
                "subject_key": "theme-a",
                "theme_name": "机器人",
                "confidence": 0.86,
                "event_count": 2,
                "latest_event_title": "机器人催化事件",
            }
        ],
        matched_events=[],
    )

    assert len(result) == 1
    assert result[0]["subject_key"] == "theme-a"
    assert result[0]["theme_name"] == "机器人"
    assert result[0]["stocks"][0]["stock_id"] == "000001.SZ"
    assert result[0]["stocks"][0]["level"] == "A"
    assert result[0]["tiers"]["A"][0]["stock_id"] == "000001.SZ"
    assert result[0]["stocks"][0]["evidence"]["weak_to_strong"] is True
    assert result[0]["stocks"][1]["level"] in {"B", "C"}
    assert "get_w2s_candidates_for_confirm_date" in gateway.calls
    assert not any("StockMatchEngine" in call for call in gateway.calls)
    assert not any(call.startswith("build_weak_to_strong") for call in gateway.calls)

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from stock_processing_service import api_app


class _Gateway:
    def __init__(self) -> None:
        self.row: dict | None = None
        self.upserts: list[dict] = []

    async def get_pre_market_brief_snapshot(self, trade_date: date):
        return self.row

    async def get_trade_calendar(self, trade_date: date):
        return {
            "trade_date": trade_date,
            "calendar_is_open": True,
            "prev_trade_date": date(2026, 5, 15),
            "next_trade_date": date(2026, 5, 18),
            "source": "unit_test",
        }

    async def get_intel_news_events(self, feed_date: date):
        return [
            {
                "item_id": "event:101:theme-a",
                "title": "事件",
                "theme_subject_keys": ["theme-a"],
                "theme_names": ["机器人"],
                "confidence": 0.8,
                "impact_score": 88,
            }
        ]

    async def get_pre_market_review_events(self, feed_date: date, limit: int = 200):
        return []

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
        return []

    async def get_theme_stock_leaderboard_by_trade_date(self, trade_date: date, subject_keys=None):
        return []

    async def get_strong_stock_watch_view_rows(
        self,
        end_date: date,
        window_days: int = 7,
        include_removed: bool = False,
        latest_per_stock: bool = True,
        limit: int = 1000,
    ):
        return []

    async def get_w2s_candidates_for_confirm_date(self, confirm_trade_date: date, limit: int = 1000):
        return []

    async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return []

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return []

    async def upsert_pre_market_brief_snapshot(self, doc, force: bool = False):
        if self.row and self.row.get("status") == "final" and not force:
            return 0
        payload = doc["payload"]
        self.row = {
            "trade_date": doc["trade_date"],
            "snapshot_version": doc["snapshot_version"],
            "status": doc.get("status", payload.get("status", "draft")),
            "payload": payload,
            "generated_at": doc.get("generated_at"),
            "finalized_at": doc.get("finalized_at"),
            "updated_at": "now",
        }
        self.upserts.append({"doc": doc, "force": force})
        return 1

    async def finalize_pre_market_brief_snapshot(self, trade_date: date, force: bool = False):
        if not self.row:
            return 0
        if self.row.get("status") == "final" and not force:
            return 0
        self.row["status"] = "final"
        self.row["finalized_at"] = "now"
        return 1


@pytest.mark.asyncio
async def test_get_pre_market_brief_missing_returns_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=gateway), raising=False)

    payload = await api_app.get_pre_market_brief("2026-05-16")

    assert payload == {
        "trade_date": "2026-05-16",
        "snapshot_version": "missing",
        "status": "missing",
        "payload": {},
    }


@pytest.mark.asyncio
async def test_get_trade_calendar_exposes_next_trade_date(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=gateway), raising=False)

    payload = await api_app.get_trade_calendar("2026-05-16")

    assert payload["trade_date"] == date(2026, 5, 16)
    assert payload["next_trade_date"] == date(2026, 5, 18)
    assert payload["source"] == "unit_test"


@pytest.mark.asyncio
async def test_rebuild_pre_market_brief_writes_draft_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=gateway), raising=False)

    payload = await api_app.rebuild_pre_market_brief(
        api_app.PreMarketBriefRebuildPayload(trade_date="2026-05-16")
    )

    assert payload["ok"] is True
    assert payload["status"] == "draft"
    assert payload["payload"]["sections"]["matched_themes"][0]["theme_name"] == "机器人"
    assert gateway.row is not None
    assert gateway.row["status"] == "draft"
    assert payload["payload"]["sections"]["event_driven_opportunities"] == []


@pytest.mark.asyncio
async def test_rebuild_pre_market_brief_includes_read_only_opportunities(monkeypatch: pytest.MonkeyPatch) -> None:
    class GatewayWithStocks(_Gateway):
        async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
            return [
                {
                    "subject_key": "theme-a",
                    "stock_id": "000001.SZ",
                    "stock_name": "核心股份",
                    "rank_order": 1,
                    "is_leader": True,
                }
            ]

        async def get_theme_stock_leaderboard_by_trade_date(self, trade_date: date, subject_keys=None):
            return [
                {
                    "subject_key": "theme-a",
                    "stock_id": "000001.SZ",
                    "leaderboard_rank": 1,
                    "leader_score": 90,
                }
            ]

        async def get_strong_stock_watch_view_rows(
            self,
            end_date: date,
            window_days: int = 7,
            include_removed: bool = False,
            latest_per_stock: bool = True,
            limit: int = 1000,
        ):
            return [
                {
                    "subject_key": "theme-a",
                    "stock_id": "000001.SZ",
                    "watch_score": 80,
                    "cycle_state": "acceleration",
                }
            ]

        async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date):
            return [{"subject_key": "theme-a", "identity_status": "confirmed", "is_main_theme": True}]

        async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
            return [{"subject_key": "theme-a", "final_cycle_state": "acceleration", "final_mainline_alive": True}]

    gateway = GatewayWithStocks()
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=gateway), raising=False)

    payload = await api_app.rebuild_pre_market_brief(
        api_app.PreMarketBriefRebuildPayload(trade_date="2026-05-16")
    )

    opportunities = payload["payload"]["sections"]["event_driven_opportunities"]
    assert opportunities[0]["subject_key"] == "theme-a"
    assert opportunities[0]["stocks"][0]["stock_id"] == "000001.SZ"


@pytest.mark.asyncio
async def test_finalize_blocks_normal_rebuild_after_final(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=gateway), raising=False)

    await api_app.rebuild_pre_market_brief(api_app.PreMarketBriefRebuildPayload(trade_date="2026-05-16"))
    finalized = await api_app.finalize_pre_market_brief(
        api_app.PreMarketBriefFinalizePayload(trade_date="2026-05-16")
    )
    before = gateway.row
    await api_app.rebuild_pre_market_brief(
        api_app.PreMarketBriefRebuildPayload(trade_date="2026-05-16", force=False)
    )

    assert finalized["ok"] is True
    assert gateway.row == before
    assert gateway.row["status"] == "final"


@pytest.mark.asyncio
async def test_force_rebuild_can_overwrite_final(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=gateway), raising=False)

    await api_app.rebuild_pre_market_brief(api_app.PreMarketBriefRebuildPayload(trade_date="2026-05-16"))
    await api_app.finalize_pre_market_brief(api_app.PreMarketBriefFinalizePayload(trade_date="2026-05-16"))
    payload = await api_app.rebuild_pre_market_brief(
        api_app.PreMarketBriefRebuildPayload(trade_date="2026-05-16", force=True)
    )

    assert payload["ok"] is True
    assert gateway.upserts[-1]["force"] is True
    assert gateway.row["payload"]["diagnostics"]["matched_event_count"] == 1

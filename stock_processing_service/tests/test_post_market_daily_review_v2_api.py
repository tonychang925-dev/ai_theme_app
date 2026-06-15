from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from stock_processing_service import api_app


class _Gateway:
    def __init__(self) -> None:
        self.row = {
            "trade_date": date(2026, 6, 12),
            "snapshot_version": "snapshot.v1",
            "batch_id": "batch.v1",
            "trace_id": "trace.v1",
            "payload": {
                "recap_doc": {
                    "trade_date": "2026-06-12",
                    "daily_review_v2": {
                        "schema_version": "daily_review_v2",
                        "snapshot_version": "daily_review_v2.old",
                        "engine_summary": {"allow_trade": False},
                        "mainline_daily_states": [],
                        "market_regime_review": {"trade_mode": "no_trade"},
                        "post_market_decision_v2": {},
                        "diagnostics": {"module_coverage": {}},
                    },
                }
            },
        }
        self.upserts: list[dict[str, object]] = []

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return self.row

    async def upsert_post_market_recap_snapshot(self, doc):
        self.upserts.append(doc)
        self.row = dict(self.row)
        self.row["payload"] = doc["payload"]
        return 1


@pytest.mark.asyncio
async def test_generate_daily_review_v2_force_rebuilds_existing_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=gateway), raising=False)

    build_calls: list[dict[str, object]] = []

    def fake_build(self, *, trade_date, recap_doc, recap_snapshot_version=None, snapshot_id=None, generated_at=None, snapshot_version=None):
        build_calls.append(
            {
                "trade_date": trade_date,
                "recap_snapshot_version": recap_snapshot_version,
                "recap_doc_has_existing_v2": bool((recap_doc or {}).get("daily_review_v2")),
            }
        )
        return {
            "schema_version": "daily_review_v2",
            "trade_date": trade_date.isoformat(),
            "snapshot_version": "daily_review_v2.new",
            "engine_summary": {"allow_trade": True},
            "mainline_daily_states": [{"mainline_id": "pcb"}],
            "market_regime_review": {"trade_mode": "no_trade"},
            "post_market_decision_v2": {},
            "diagnostics": {"module_coverage": {"stock_capital_reviews": {"status": "ready"}}},
        }

    async def fake_watchlists(trade_date):
        return {}

    monkeypatch.setattr(
        "stock_processing_service.application.services.post_market_daily_review_v2_builder.PostMarketDailyReviewV2Builder.build",
        fake_build,
        raising=True,
    )
    monkeypatch.setattr(api_app, "_build_one_to_two_watchlists", fake_watchlists, raising=True)
    monkeypatch.setattr(
        "stock_processing_service.application.services.post_market_engine_report_composer.PostMarketEngineReportComposer.compose",
        lambda self, recap_doc: {},
        raising=True,
    )

    payload = await api_app.generate_daily_review_v2({"trade_date": "2026-06-12", "force": True})

    assert payload["ok"] is True
    assert build_calls and build_calls[0]["recap_doc_has_existing_v2"] is True
    assert gateway.upserts[-1]["payload"]["recap_doc"]["daily_review_v2"]["snapshot_version"] == "daily_review_v2.new"
    assert gateway.upserts[-1]["payload"]["recap_doc"]["daily_review_v2"]["engine_summary"]["allow_trade"] is True

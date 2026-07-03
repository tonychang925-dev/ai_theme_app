from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from stock_processing_service import api_app


class _Gateway:
    def __init__(self) -> None:
        self._client = SimpleNamespace(pool=object())
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
    traced_theme_rows: list[dict[str, object]] = []

    def fake_build(
        self,
        *,
        trade_date,
        recap_doc,
        recap_snapshot_version=None,
        snapshot_id=None,
        generated_at=None,
        snapshot_version=None,
        theme_driver_events=None,
    ):
        catalyst_events = (
            theme_driver_events[0]["driver_events"]
            if theme_driver_events
            else []
        )
        build_calls.append(
            {
                "trade_date": trade_date,
                "recap_snapshot_version": recap_snapshot_version,
                "recap_doc_has_existing_v2": bool((recap_doc or {}).get("daily_review_v2")),
                "theme_driver_events": theme_driver_events,
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
            "theme_capital_reviews": [],
            "limit_up_theme_matrix": {
                "source": "limit_up_theme_matrix_builder",
                "columns": [
                    {
                        "subject_key": "reason:创新药/医疗",
                        "theme_name": "创新药/医疗",
                        "catalyst_events": catalyst_events,
                    }
                ],
                "board_totals": {},
            },
            "diagnostics": {"module_coverage": {"stock_capital_reviews": {"status": "ready"}}},
        }

    async def fake_watchlists(trade_date):
        return {}

    async def fake_latest_snapshot(trade_date):
        return gateway.row

    async def fake_enrich_theme_names(v2, trade_date):
        return v2

    async def fake_trace_theme_rows(self, theme_rows, trade_date, **kwargs):
        del self, trade_date, kwargs
        traced_theme_rows.extend(theme_rows)
        return [
            {
                "subject_key": "reason:创新药/医疗",
                "theme_name": "创新药/医疗",
                "driver_events": [
                    {
                        "event_id": 101,
                        "summary": "创新药获批事件",
                        "event_time": "2026-06-12T10:00:00",
                        "confidence": 0.9,
                        "match_reason": "创新药",
                    }
                ],
            }
        ]

    monkeypatch.setattr(api_app, "_fetch_latest_post_market_recap_snapshot_row", fake_latest_snapshot, raising=True)
    monkeypatch.setattr(api_app, "_enrich_v2_theme_names", fake_enrich_theme_names, raising=True)
    monkeypatch.setattr(
        "stock_processing_service.application.services.post_market_daily_review_v2_builder.PostMarketDailyReviewV2Builder.build",
        fake_build,
        raising=True,
    )
    monkeypatch.setattr(
        "stock_processing_service.application.services.event_driver_tracer.EventDriverTracer.trace_theme_rows",
        fake_trace_theme_rows,
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
    assert traced_theme_rows[0]["subject_key"] == "reason:创新药/医疗"
    assert gateway.upserts[-1]["payload"]["recap_doc"]["daily_review_v2"]["snapshot_version"] == "daily_review_v2.new"
    assert gateway.upserts[-1]["payload"]["recap_doc"]["daily_review_v2"]["engine_summary"]["allow_trade"] is True
    assert (
        gateway.upserts[-1]["payload"]["recap_doc"]["limit_up_theme_matrix"]["columns"][0][
            "catalyst_events"
        ][0]["summary"]
        == "创新药获批事件"
    )

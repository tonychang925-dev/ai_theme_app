from fastapi.testclient import TestClient
import json

from web_app_service.main import app
import web_app_service.api.routes as routes


client = TestClient(app)


def test_intel_feed_contract_shape(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [{"item_id": "x1", "title": "t"}],
            "count": 1,
            "diagnostics": {"partial": False},
        }

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    resp = client.get("/api/v2/intel/feed", params={"date": "2026-04-29", "limit": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "count" in data


def test_intel_feed_does_not_fallback_to_old_intel_proxy(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [],
            "count": 0,
            "diagnostics": {"partial": True, "source": "stock_processing_read_api_unavailable"},
        }

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    resp = client.get("/api/v2/intel/feed", params={"date": "2026-04-29", "limit": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["items"] == []
    assert data["diagnostics"]["source"] == "stock_processing_read_api_unavailable"


def test_workspace_theme_radar_contract_shape(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [
                {
                    "subject_key": "9035101",
                    "theme_names": ["钠离子电池"],
                    "stock_ids": ["600152.SH", "002000.SZ"],
                }
            ],
            "count": 1,
            "diagnostics": {"partial": False},
        }

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    resp = client.get("/api/v2/workspace/theme-radar", params={"date": "2026-04-29"})
    assert resp.status_code == 200
    data = resp.json()
    assert "themes" in data
    assert isinstance(data["themes"], list)
    if data["themes"]:
        row = data["themes"][0]
        for k in ("theme_id", "theme_name", "heat", "stage", "stock_count"):
            assert k in row


def test_workspace_theme_radar_stage_mapping(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [
                {
                    "subject_key": "S1",
                    "theme_names": ["空间科技"],
                    "stock_ids": ["A", "B"],
                    "cycle_state": "confirmed",
                }
            ],
            "count": 1,
            "diagnostics": {"partial": False},
        }

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    resp = client.get("/api/v2/workspace/theme-radar", params={"date": "2026-04-29"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["themes"][0]["stage"] == "CONFIRMED"


def test_workspace_theme_radar_stage_enriched_from_strong_watch(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [
                {
                    "subject_key": "S2",
                    "theme_names": ["可回收火箭"],
                    "stock_ids": ["A", "B", "C"],
                }
            ],
            "count": 1,
            "diagnostics": {"partial": False},
        }

    async def _fake_strong_watch(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "stocks": [{"subject_key": "S2", "final_cycle_state": "confirmed"}]
                }
            },
        )()

    async def _fake_w2s(trade_date):
        return type("R", (), {"model_dump": lambda self: {"candidates": []}})()

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    monkeypatch.setattr(routes.client, "get_w2s_candidates", _fake_w2s)

    resp = client.get("/api/v2/workspace/theme-radar", params={"date": "2026-04-29"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["themes"][0]["stage"] == "CONFIRMED"


def test_workspace_theme_radar_stage_enriched_from_theme_name(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [
                {
                    "subject_key": "",
                    "theme_names": ["SpaceX"],
                    "stock_ids": ["A", "B", "C"],
                }
            ],
            "count": 1,
            "diagnostics": {"partial": False},
        }

    async def _fake_strong_watch(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "stocks": [{"subject_name": "SpaceX", "final_cycle_state": "confirmed"}]
                }
            },
        )()

    async def _fake_w2s(trade_date):
        return type("R", (), {"model_dump": lambda self: {"candidates": []}})()

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    monkeypatch.setattr(routes.client, "get_w2s_candidates", _fake_w2s)

    resp = client.get("/api/v2/workspace/theme-radar", params={"date": "2026-04-29"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["themes"][0]["stage"] == "CONFIRMED"


def test_workspace_theme_radar_stage_enriched_from_recap_snapshot(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [
                {"subject_key": "S9", "theme_names": ["氦气"], "stock_ids": ["A"]},
            ],
            "count": 1,
            "diagnostics": {"partial": False},
        }

    async def _fake_snapshot(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "trade_date": trade_date,
                    "snapshot_version": "v2",
                    "payload": {
                        "recap_doc": {
                            "strong_watch_history": [{"subject_key": "S9", "final_cycle_state": "confirmed"}],
                            "top_candidates": [],
                        }
                    },
                }
            },
        )()

    async def _fake_strong_watch(trade_date):
        return type("R", (), {"model_dump": lambda self: {"stocks": []}})()

    async def _fake_w2s(trade_date):
        return type("R", (), {"model_dump": lambda self: {"candidates": []}})()

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    monkeypatch.setattr(routes.client, "get_post_market_snapshot", _fake_snapshot)
    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    monkeypatch.setattr(routes.client, "get_w2s_candidates", _fake_w2s)
    resp = client.get("/api/v2/workspace/theme-radar", params={"date": "2026-04-30"})
    assert resp.status_code == 200
    assert resp.json()["themes"][0]["stage"] == "CONFIRMED"


def test_workspace_market_validation_contract_shape(monkeypatch):
    async def _fake_strong_watch(trade_date):
        return type("R", (), {"model_dump": lambda self: {"stocks": [{"stock_id": "600152.SH"}]}})()

    async def _fake_w2s(trade_date):
        return type("R", (), {"model_dump": lambda self: {"candidates": [{"stock_id": "600152.SH"}]}})()

    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    monkeypatch.setattr(routes.client, "get_w2s_candidates", _fake_w2s)

    resp = client.get(
        "/api/v2/workspace/market-validation",
        params={"trade_date": "2026-04-29", "stock_id": "600152.SH"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for k in (
        "trade_date",
        "candidate_level",
        "support_type",
        "support_score",
        "reject_reasons",
        "strong_watch_count",
        "w2s_candidate_count",
    ):
        assert k in data


def test_workspace_market_validation_uses_candidate_fields(monkeypatch):
    async def _fake_strong_watch(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "stocks": [{"stock_id": "600152.SH", "support_type": "ma_support", "support_score": "66"}]
                }
            },
        )()

    async def _fake_w2s(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "candidates": [
                        {
                            "stock_id": "600152.SH",
                            "candidate_level": "formal",
                            "support_type": "gap_support",
                            "support_score": "78",
                            "reject_reasons": [],
                        }
                    ]
                }
            },
        )()

    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    monkeypatch.setattr(routes.client, "get_w2s_candidates", _fake_w2s)

    resp = client.get(
        "/api/v2/workspace/market-validation",
        params={"trade_date": "2026-04-29", "stock_id": "600152.SH"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_level"] == "formal"
    assert data["support_type"] == "gap_support"
    assert data["support_score"] == 78.0


def test_workspace_market_validation_observe_when_only_strong_watch(monkeypatch):
    async def _fake_strong_watch(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "stocks": [{"stock_id": "300001.SZ", "support_type": "ma_support", "support_score": "66"}]
                }
            },
        )()

    async def _fake_w2s(trade_date):
        return type("R", (), {"model_dump": lambda self: {"candidates": []}})()

    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    monkeypatch.setattr(routes.client, "get_w2s_candidates", _fake_w2s)
    resp = client.get(
        "/api/v2/workspace/market-validation",
        params={"trade_date": "2026-04-29"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_level"] == "observe"
    assert data["support_type"] == "ma_support"
    assert data["support_score"] == 66.0


def test_workspace_intel_context_contract_shape(monkeypatch):
    async def _fake_get_intel_feed(**kwargs):
        return {
            "items": [{"item_id": "x1", "title": "hello"}],
            "count": 1,
            "diagnostics": {"partial": False},
        }

    monkeypatch.setattr(routes.client, "get_intel_feed", _fake_get_intel_feed)
    resp = client.get(
        "/api/v2/workspace/intel-context",
        params={"date": "2026-04-29", "subject_key": "9035101", "limit": 20},
    )
    assert resp.status_code == 200
    data = resp.json()
    for k in ("date", "subject_key", "stock_id", "items", "count", "source", "diagnostics"):
        assert k in data


def test_intel_stream_contract_headers(monkeypatch):
    monkeypatch.setattr(routes, "STOCK_PROCESSING_BASE_URL", "http://127.0.0.1:65535")

    resp = client.get("/api/v2/intel/stream", params={"date": "2026-04-29", "limit": 5})
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/event-stream")
    assert resp.headers.get("cache-control") == "no-cache"


def test_recap_contract_shape(monkeypatch):
    async def _fake_post_market_snapshot(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "trade_date": trade_date,
                    "snapshot_version": "v2-test",
                    "payload": {
                        "report": {
                            "trade_date": trade_date,
                            "title": "盘后复盘",
                            "summary": "测试摘要",
                            "highlights": ["h1"],
                            "sections": [{"heading": "主线与支线", "items": ["i1"]}],
                        }
                    },
                }
            },
        )()

    monkeypatch.setattr(routes.client, "get_post_market_snapshot", _fake_post_market_snapshot)
    resp = client.get("/api/v2/recap", params={"date": "2026-04-29", "report_type": "post_market"})
    assert resp.status_code == 200
    data = resp.json()
    for k in ("report_type", "trade_date", "title", "summary", "highlights", "sections", "source", "diagnostics"):
        assert k in data
    assert data["report_type"] == "post_market"
    assert data["source"] in ("recap_v2_report", "recap_v2_snapshot")


def test_recap_defaults_contract_shape():
    resp = client.get("/api/v2/recap/defaults")
    assert resp.status_code == 200
    data = resp.json()
    assert "latest_post_market_date" in data
    assert "latest_pre_market_date" in data


def test_strong_watch_new_alias_contract_shape(monkeypatch):
    async def _fake_strong_watch(trade_date, **_kwargs):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "trade_date": trade_date,
                    "stocks": [
                        {
                            "stock_id": "600152.SH",
                            "stock_name": "样例",
                            "watch_status": "active",
                            "trade_date": "2026-04-29",
                        }
                    ],
                }
            },
        )()

    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    resp = client.get("/api/v2/strong_watch/watch", params={"date": "2026-04-29", "window_days": 7})
    assert resp.status_code == 200
    data = resp.json()
    for k in ("count", "items"):
        assert k in data


def test_strong_watch_bff_forwards_window_params(monkeypatch):
    seen = {}

    async def _fake_strong_watch(
        trade_date,
        *,
        window_days=None,
        include_removed=None,
        latest_per_stock=None,
        stock_id=None,
        limit=None,
    ):
        seen.update(
            {
                "trade_date": trade_date,
                "window_days": window_days,
                "include_removed": include_removed,
                "latest_per_stock": latest_per_stock,
                "stock_id": stock_id,
                "limit": limit,
            }
        )
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "trade_date": trade_date,
                    "stocks": [
                        {"trade_date": "2026-04-24", "stock_id": "000001.SZ", "watch_status": "active"},
                        {"trade_date": "2026-04-30", "stock_id": "000001.SZ", "watch_status": "active"},
                        {"trade_date": "2026-04-29", "stock_id": "000002.SZ", "watch_status": "weakening"},
                    ],
                }
            },
        )()

    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    resp = client.get(
        "/api/v2/strong_watch/watch",
        params={
            "date": "2026-04-30",
            "window_days": 7,
            "include_removed": "false",
            "latest_per_stock": "false",
            "stock_id": "000001.SZ",
            "limit": 200,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert seen == {
        "trade_date": "2026-04-30",
        "window_days": 7,
        "include_removed": False,
        "latest_per_stock": False,
        "stock_id": "000001.SZ",
        "limit": 200,
    }
    assert data["count"] == 3
    assert data["date_from"] == "2026-04-24"
    assert data["date_to"] == "2026-04-30"
    assert data["diagnostics"]["mode"] == "windowed_history"


def test_sse_payload_validation_stream_state_ok():
    ok, reason = routes._validate_sse_payload("stream_state", {"status": "connected"})
    assert ok is True
    assert reason is None


def test_sse_payload_validation_heartbeat_ok():
    ok, reason = routes._validate_sse_payload("heartbeat", {"ts": "2026-05-01T00:00:00Z"})
    assert ok is True
    assert reason is None


def test_sse_payload_validation_intel_item_nested_ok():
    ok, reason = routes._validate_sse_payload(
        "intel_item",
        {
            "event_id": "evt-1",
            "item": {
                "item_id": "x1",
                "item_type": "event",
                "occurred_at": "2026-05-01T00:00:00",
                "title": "t",
            },
        },
    )
    assert ok is True
    assert reason is None


def test_sse_payload_validation_invalid_payload_to_error_event():
    payload = routes._emit_sse("error", {"code": "INVALID_EVENT_PAYLOAD", "message": "x", "retryable": True}).decode("utf-8")
    assert "event: error" in payload
    assert "data:" in payload
    data_line = [line for line in payload.splitlines() if line.startswith("data:")][0]
    obj = json.loads(data_line.split("data:", 1)[1].strip())
    assert obj["code"] == "INVALID_EVENT_PAYLOAD"

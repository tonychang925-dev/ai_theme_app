import asyncio
from fastapi.testclient import TestClient
import json
from pathlib import Path

from web_app_service.main import app
import web_app_service.api.routes as routes
from web_app_service.services.realtime_stack_manager import RealtimeStackManager


client = TestClient(app)


def test_realtime_collector_routes_do_not_proxy_frontend_bff():
    source = Path(routes.__file__).read_text(encoding="utf-8")
    forbidden_fragments = (
        "FRONTEND_BFF_BASE",
        "_proxy_bff",
        "frontend_bff (8003)",
        "/api/v2/realtime/collector/status",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_realtime_collector_status_uses_web_app_manager(monkeypatch):
    class FakeRealtimeStackManager:
        async def status(self):
            return {
                "ok": True,
                "return_code": 0,
                "stdout": "[up]   web_app_service:8000\n[up]   stock_processing_service:8090\n",
                "stderr": "",
                "command": ["web_app_service:realtime_stack", "status"],
            }

    app.state.realtime_stack_manager = FakeRealtimeStackManager()

    resp = client.get("/api/v2/realtime/collector/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["command"] == ["web_app_service:realtime_stack", "status"]


def test_realtime_collector_logs_include_realtime_run_files(tmp_path):
    log_dir = tmp_path / "logs" / "realtime"
    runtime_dir = log_dir / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "realtime_stack.json").write_text(
        json.dumps({"run_id": "realtime_20260530_230540"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (log_dir / "raw_news_realtime_20260530_230540.log").write_text(
        "2026-05-31 08:13:44,865 INFO database_service.streams.handlers.news_stream_processor: 📥 收到 1 条原始消息\n"
        "2026-05-31 08:13:59,150 INFO database_service.streams.handlers.news_stream_processor: ⏭️ 重要性预筛选停在结构化前: d215375c0da779ac9ed73c2bbf780db8, decision=REVIEW, reason=embedding_importance_review\n",
        encoding="utf-8",
    )
    (log_dir / "db_collector_realtime_20260530_230540.log").write_text(
        "2026-05-31 08:24:45,838 WARNING database_service.streams.services.real_time_news_collector: CLS fetch failed: 真实新闻源不可用\n"
        "2026-05-31 08:25:30,843 INFO database_service.streams.services.real_time_news_collector: 多源采集完成: 62 条 (CLS+akshare)\n",
        encoding="utf-8",
    )

    manager = RealtimeStackManager(str(tmp_path))
    data = asyncio.run(manager.logs(lines=20, max_age_minutes=180))

    assert data["run_id"] == "realtime_20260530_230540"
    assert "raw_news_realtime_20260530_230540.log" in data["files"]
    assert "db_collector_realtime_20260530_230540.log" in data["files"]
    assert any("CLS fetch failed" in line for line in data["files"]["db_collector_realtime_20260530_230540.log"])
    assert any("重要性预筛选" in line for line in data["files"]["raw_news_realtime_20260530_230540.log"])


def test_realtime_new_chain_routes_proxy_sps_v1(monkeypatch):
    calls = []

    async def _fake_proxy(method, path, **kwargs):
        calls.append((method, path, kwargs.get("timeout")))
        return {"ok": True, "running": True, "path": path}

    monkeypatch.setattr(routes, "_proxy_stock_processing_request_json", _fake_proxy)

    status_resp = client.get("/api/v2/realtime/new-chain/status")
    start_resp = client.post("/api/v2/realtime/new-chain/start")
    stop_resp = client.post("/api/v2/realtime/new-chain/stop")

    assert status_resp.status_code == 200
    assert start_resp.status_code == 200
    assert stop_resp.status_code == 200
    assert calls == [
        ("GET", "/api/v1/realtime/status", 15.0),
        ("GET", "/api/v1/realtime/start", 60.0),
        ("GET", "/api/v1/realtime/stop", 30.0),
    ]


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
        params={"trade_date": "2026-04-30", "stock_id": "600152.SH"},
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
        params={"trade_date": "2026-04-28"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_level"] == "observe"
    assert data["support_type"] == "ma_support"
    assert data["support_score"] == 66.0


def test_workspace_market_validation_falls_back_to_recap_strong_reviews(monkeypatch):
    async def _fake_strong_watch(trade_date):
        return type("R", (), {"model_dump": lambda self: {"stocks": []}})()

    async def _fake_w2s(trade_date):
        return type("R", (), {"model_dump": lambda self: {"candidates": []}})()

    async def _fake_snapshot(trade_date):
        return type(
            "R",
            (),
            {
                "model_dump": lambda self: {
                    "trade_date": trade_date,
                    "payload": {
                        "recap_doc": {
                            "strong_stock_reviews": [{"stock_id": "002000.SZ"}],
                            "strong_stock_reviews_count": 1,
                            "strong_watch_history_count": 0,
                        }
                    },
                }
            },
        )()

    monkeypatch.setattr(routes.client, "get_strong_watch", _fake_strong_watch)
    monkeypatch.setattr(routes.client, "get_w2s_candidates", _fake_w2s)
    monkeypatch.setattr(routes.client, "get_post_market_snapshot", _fake_snapshot)

    resp = client.get(
        "/api/v2/workspace/market-validation",
        params={"trade_date": "2026-04-27"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["strong_watch_count"] == 1


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


def test_intel_stream_streams_upstream_events(monkeypatch):
    monkeypatch.setattr(routes, "STOCK_PROCESSING_BASE_URL", "http://127.0.0.1:65535")

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params=None):
            assert url == "http://127.0.0.1:65535/api/v1/intel_feed"
            self.calls += 1
            if self.calls == 1:
                payload = {
                    "items": [
                        {
                            "item_id": "evt-1",
                            "item_type": "event",
                            "occurred_at": "2026-06-03T10:00:00Z",
                            "title": "sample",
                        }
                    ],
                    "count": 1,
                }
            else:
                payload = {"items": [], "count": 0}
            return type(
                "R",
                (),
                {
                    "raise_for_status": lambda self: None,
                    "json": lambda self, payload=payload: payload,
                },
            )()

    class FakeRequest:
        async def is_disconnected(self):
            return False

    monkeypatch.setattr(routes.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())

    async def _collect():
        gen = routes._intel_stream_proxy(
            FakeRequest(),
            url="http://127.0.0.1:65535/api/intel/stream",
            query={"limit": "5"},
        )
        first = (await gen.__anext__()).decode("utf-8")
        await gen.aclose()
        return [first]

    chunks = asyncio.run(_collect())
    assert len(chunks) == 1
    assert chunks[0].startswith("event:") and "\ndata:" in chunks[0]


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


def test_recap_defaults_contract_shape(monkeypatch):
    async def _fake_proxy_stock_processing_json(path, params):
        assert path == "/api/v1/recap/defaults"
        assert params == {}
        return {"latest_post_market_date": "2026-04-30", "latest_pre_market_date": "2026-05-01"}

    monkeypatch.setattr(routes, "_proxy_stock_processing_json", _fake_proxy_stock_processing_json)
    resp = client.get("/api/v2/recap/defaults")
    assert resp.status_code == 200
    data = resp.json()
    assert "latest_post_market_date" in data
    assert "latest_pre_market_date" in data


def test_post_market_generate_routes_use_long_proxy_timeouts(monkeypatch):
    calls = []

    async def _fake_proxy_stock_processing_post_json(path, payload, timeout=120.0):
        calls.append((path, payload, timeout))
        return {"ok": True, "path": path}

    monkeypatch.setattr(routes, "_proxy_stock_processing_post_json", _fake_proxy_stock_processing_post_json)

    payload = {"trade_date": "2026-05-29", "force": True}
    assert client.post("/api/v2/post-market/derived-data/generate", json=payload).status_code == 200
    assert client.post("/api/v2/post-market/recap/generate", json=payload).status_code == 200
    assert client.post("/api/v2/post-market/daily-review-v2/generate", json=payload).status_code == 200

    assert calls == [
        ("/api/v1/post-market/derived-data/generate", payload, 600.0),
        ("/api/v1/post-market/recap/generate", payload, 300.0),
        ("/api/v2/post-market/daily-review-v2/generate", payload, 180.0),
    ]


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

import os

from fastapi.testclient import TestClient


os.environ.setdefault("POSTGRES_DATABASE", "stock_data_test")

from theme_service.app import app


def test_phase1_rank_api_real_db():
    with TestClient(app) as client:
        response = client.get("/themes/rank", params={"limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert len(payload["items"]) >= 1
    first = payload["items"][0]
    assert first["subject_key"]
    assert "rank_date" in first


def test_phase1_children_api_real_db():
    with TestClient(app) as client:
        response = client.get("/themes/1/children", params={"limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject_key"] == "1"
    assert payload["count"] >= 1
    first = payload["items"][0]
    assert first["parent_subject_key"] == "1"
    assert first["child_subject_key"]
    assert first["child_name"]


def test_phase1_history_api_real_db():
    with TestClient(app) as client:
        response = client.get("/themes/9010074/history", params={"limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject_key"] == "9010074"
    assert payload["count"] >= 1
    first = payload["items"][0]
    assert first["subject_key"] == "9010074"
    assert first["source_type"] in {"jyhf_history", "jyhf_rank_daily", "event_theme_map"}


def test_phase1_theme_detail_api_real_db():
    with TestClient(app) as client:
        response = client.get("/themes/9010074")
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject_key"] == "9010074"
    assert payload["theme_name"]
    assert "history_count" in payload
    assert "children_count" in payload
    assert "stock_count" in payload


def test_phase1_theme_list_api_real_db():
    with TestClient(app) as client:
        response = client.get("/themes", params={"limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert len(payload["items"]) >= 1
    first = payload["items"][0]
    assert first["subject_key"]
    assert first["theme_name"]
    assert first["binding_status"] in {"active_binding", "staging_only", "theme_master_only"}


def test_phase1_theme_stocks_api_real_db():
    with TestClient(app) as client:
        response = client.get("/themes/9010317/stocks", params={"limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject_key"] == "9010317"
    assert payload["count"] >= 1
    first = payload["items"][0]
    assert first["subject_key"] == "9010317"
    assert first["stock_id"]
    assert first["relation_type_candidate"] in {"leader", "core", "member"}
    assert first["mapping_scope"] == "pool"


def test_phase1_stock_themes_api_real_db():
    with TestClient(app) as client:
        response = client.get("/stocks/300122/themes", params={"limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_id"] == "300122"
    assert payload["count"] >= 1
    first = payload["items"][0]
    assert first["stock_id"] == "300122"
    assert first["subject_key"]


def test_phase4_phasea_intel_feed_api_real_db():
    with TestClient(app) as client:
        response = client.get(
            "/intel/feed",
            params={
                "date": "2026-03-31",
                "type": "new_theme",
                "limit": 10,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["date"] == "2026-03-31"
    assert payload["type"] == "new_theme"
    assert payload["count"] >= 1
    assert len(payload["items"]) >= 1
    first = payload["items"][0]
    assert first["item_id"]
    assert first["item_type"] == "new_theme"
    assert first["occurred_at"]
    assert first["title"]
    assert isinstance(first["theme_subject_keys"], list)
    assert isinstance(first["theme_names"], list)
    assert isinstance(first["stock_ids"], list)
    assert isinstance(first["stock_names"], list)
    assert first["source_type"] in {"subject_node_staging", "jyhf_full_theme_list"}


def test_phase4_phasea_intel_feed_event_api_real_db():
    with TestClient(app) as client:
        response = client.get(
            "/intel/feed",
            params={
                "date": "2026-06-04",
                "type": "event",
                "session": "all",
                "limit": 10,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["date"] == "2026-06-04"
    assert payload["type"] == "event"
    assert payload["count"] >= 1
    assert len(payload["items"]) >= 1
    first = payload["items"][0]
    assert first["item_id"]
    assert first["item_type"] == "event"
    assert first["occurred_at"]
    assert first["title"]

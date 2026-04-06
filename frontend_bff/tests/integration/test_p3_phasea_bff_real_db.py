import os

from fastapi.testclient import TestClient


os.environ.setdefault("POSTGRES_DATABASE", "stock_data_test")

from frontend_bff.app import app


def test_p3_phasea_intel_feed_bff_real_db():
    with TestClient(app) as client:
        response = client.get(
            "/api/intel/feed",
            params={"date": "2026-04-01", "type": "all", "limit": 5},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "all"
    assert payload["count"] >= 1
    assert isinstance(payload["diagnostics"]["sources"], list)
    first = payload["items"][0]
    assert first["item_type"] in {"event", "theme_move", "new_theme", "stock_move"}
    assert first["theme_subject_keys"]


def test_p3_phasea_theme_workspace_bff_real_db():
    with TestClient(app) as client:
        response = client.get(
            "/api/theme-workspace/9010074",
            params={"include_stocks": "false", "history_limit": 3, "children_limit": 3},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject_key"] == "9010074"
    assert payload["detail"]["subject_key"] == "9010074"
    assert payload["detail"]["theme_name"]
    assert isinstance(payload["diagnostics"]["missing_sections"], list)


def test_p3_phasea_stock_workspace_bff_real_db():
    with TestClient(app) as client:
        response = client.get(
            "/api/stock-workspace/300436",
            params={"themes_limit": 5},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_id"] == "300436"
    assert payload["stock_detail"]["stock_id"] == "300436"
    assert len(payload["themes"]) >= 1
    assert "money_flow" in payload
    assert "dragon_tiger" in payload
    assert "auction_validation" in payload


def test_p3_phasea_recap_bff_real_db():
    with TestClient(app) as client:
        response = client.get(
            "/api/recap",
            params={"date": "2026-04-01", "report_type": "post_market"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "post_market"
    assert payload["trade_date"] == "2026-04-01"
    assert isinstance(payload["highlights"], list)
    assert len(payload["sections"]) >= 3
    assert payload["sections"][0]["heading"]


def test_p3_phasea_recap_defaults_bff_real_db():
    with TestClient(app) as client:
        response = client.get("/api/recap/defaults")
    assert response.status_code == 200
    payload = response.json()
    assert "latest_post_market_date" in payload
    assert "latest_pre_market_date" in payload

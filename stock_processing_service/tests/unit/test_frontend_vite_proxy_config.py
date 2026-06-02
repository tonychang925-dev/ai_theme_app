from pathlib import Path


def test_vite_js_config_routes_new_chain_realtime_through_web_app_bff() -> None:
    config = Path("frontend/vite.config.js").read_text(encoding="utf-8")

    assert '"/api/v1": "http://127.0.0.1:8000"' in config
    assert '"/api/v1/realtime"' not in config
    assert '"/api/v2": "http://127.0.0.1:8000"' in config

from pathlib import Path


def test_vite_js_config_routes_realtime_to_sps_before_api_fallback() -> None:
    config = Path("frontend/vite.config.js").read_text(encoding="utf-8")

    realtime_index = config.index('"/api/v1/realtime"')
    fallback_index = config.index('"/api"')

    assert realtime_index < fallback_index
    assert 'target: "http://127.0.0.1:8090"' in config[realtime_index:fallback_index]

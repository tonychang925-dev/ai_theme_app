from __future__ import annotations

try:
    from stock_processing_service.application.services.market_cognition.replay import (
        MarketCognitionReplay,
    )
except ModuleNotFoundError:
    MarketCognitionReplay = None
from stock_processing_service.publishers.notion_post_market_recap_publisher import (
    NotionPostMarketRecapPublisher,
)


def _payload() -> dict:
    return {
        "recap_doc": {
            "schema_version": "post_market_recap.v2",
            "engine_summary": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "blocking_rule": "short_term_sentiment_dead",
            },
            "market_regime_review": {
                "broad_market_regime": "downtrend_rebound",
                "short_term_sentiment": "dead",
                "mainline_environment": "mainline_tradable",
            },
            "mainline_states": [
                {"theme_name": "机器人", "lifecycle": "divergence", "strong_stock_count": 4}
            ],
        }
    }


def _text(block: dict) -> str:
    block_type = block.get("type", "")
    rich = block.get(block_type, {}).get("rich_text", [])
    return "".join(item.get("text", {}).get("content", "") for item in rich)


# TC-M8P0-T04-01
def test_render_modes_when_thesis_is_ready_then_only_dual_layer_publishes_cognition_homepage() -> None:
    assert MarketCognitionReplay is not None, "replay implementation is missing"
    payload = _payload()
    replay = MarketCognitionReplay.run(payload, "2026-07-03")
    assert replay.thesis is not None
    payload["market_cognition"] = replay.thesis.to_dict()

    legacy = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="legacy_only"
    )
    shadow = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="cognition_shadow"
    )
    dual = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="dual_layer"
    )

    assert shadow == legacy
    assert all(_text(block) != "市场认知首页" for block in legacy)
    assert any(_text(block) == "市场认知首页" for block in dual)
    assert len(dual) > len(legacy)
    legacy_title_index = next(i for i, block in enumerate(dual) if _text(block) == "2026-07-03 盘后复盘")
    cognition_index = next(i for i, block in enumerate(dual) if _text(block) == "市场认知首页")
    assert legacy_title_index < cognition_index


# TC-M8P0-T04-02
def test_invalid_cognition_when_dual_layer_requested_then_output_falls_back_to_legacy() -> None:
    payload = _payload()
    payload["market_cognition"] = {
        "schema_version": "market_thesis.v1",
        "status": "ready",
        "primary_thesis": {"statement": "无引用结论", "evidence_refs": []},
    }

    legacy = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="legacy_only"
    )
    dual = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="dual_layer"
    )

    assert dual == legacy
    assert all(_text(block) != "市场认知首页" for block in dual)


# TC-M8P0-T04-02
def test_invalid_render_mode_when_requested_then_it_fails_closed_to_legacy() -> None:
    payload = _payload()
    legacy = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="legacy_only"
    )
    invalid = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="cognition_primary"
    )

    assert invalid == legacy


# TC-M8P0-T04-01
def test_dual_layer_without_injected_thesis_when_payload_is_valid_then_preview_is_built() -> None:
    payload = _payload()

    dual = NotionPostMarketRecapPublisher.build_blocks(
        payload, "2026-07-03", render_mode="dual_layer"
    )

    assert any(_text(block) == "市场认知首页" for block in dual)
    assert "market_cognition" not in payload

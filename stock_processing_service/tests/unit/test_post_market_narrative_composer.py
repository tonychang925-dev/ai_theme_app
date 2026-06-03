from __future__ import annotations

from stock_processing_service.application.services.post_market_engine_report_composer import (
    PostMarketEngineReportComposer,
)
from stock_processing_service.application.services.post_market_hotspot_overview_composer import (
    PostMarketHotspotOverviewComposer,
)
from stock_processing_service.application.services.post_market_narrative_composer import (
    PostMarketNarrativeComposer,
)


def _sample_engine_report_doc() -> dict[str, object]:
    return {
        "market_summary": {
            "market_bias": "弱势",
            "action_bias": "防守",
            "breadth_status": "偏弱",
            "short_term_sentiment_status": "中性偏弱",
            "relay_sentiment_status": "谨慎",
            "intraday_fade_status": "分歧",
            "conclusion": "观察为主",
            "highlights": ["热点轮动明显", "主线分歧仍在"],
            "risk_flags": ["指数偏弱", "情绪回落"],
        },
        "engine_summary": {
            "allow_trade": False,
            "trade_mode": "no_trade",
            "position_limit": 0,
            "no_trade_blocking_rule": "broad_market_regime_bearish_adverse",
            "no_trade_reasons": ["大盘弱势不利"],
            "action_bias": "防守",
            "conclusion": "市场环境偏弱，当前不支持主动交易，以观察为主。",
            "next_day_strategy": "不做新开仓，只观察主线是否修复",
            "risk_notes": ["指数承压", "情绪分歧"],
        },
        "market_regime_review": {
            "broad_market_regime": "bearish_adverse",
            "short_term_sentiment": "weak",
            "mainline_environment": "observe_only",
            "allow_trade": False,
            "trade_mode": "no_trade",
            "position_limit": 0,
            "no_trade_blocking_rule": "broad_market_regime_bearish_adverse",
            "no_trade_reasons": ["大盘弱势不利"],
            "index_data_ready": True,
            "index_technical_reviews": [
                {
                    "index_code": "000001.SH",
                    "index_name": "上证指数",
                    "trend_state": "bearish_trend",
                    "support_level": 3100,
                    "resistance_level": 3200,
                    "index_trade_hint": "关注支撑是否失守",
                }
            ],
        },
        "index_technical_reviews": [
            {
                "index_code": "000001.SH",
                "index_name": "上证指数",
                "trend_state": "bearish_trend",
                "support_level": 3100,
                "resistance_level": 3200,
                "index_trade_hint": "关注支撑是否失守",
            }
        ],
        "mainline_daily_states": [
            {
                "mainline_id": "pcb",
                "mainline_name": "PCB",
                "canonical_subject_key": "pcb",
                "lifecycle_state": "divergence",
                "mainline_strength_score": 86.2,
                "fade_risk_score": 27.5,
                "strong_pool_count": 8,
                "d1_count": 3,
                "focus_count": 0,
                "action_advice": "观察分歧修复",
                "conclusion": "主线仍有资金，但处于分歧阶段",
            },
            {
                "mainline_id": "power",
                "mainline_name": "电力运营",
                "canonical_subject_key": "power",
                "lifecycle_state": "fade_watch",
                "mainline_strength_score": 83.0,
                "fade_risk_score": 38.0,
                "strong_pool_count": 4,
                "d1_count": 0,
                "focus_count": 0,
                "action_advice": "观察",
                "conclusion": "资金活跃但确认不足",
            },
            {
                "mainline_id": "sat",
                "mainline_name": "卫星互联网",
                "canonical_subject_key": "sat",
                "lifecycle_state": "watch",
                "mainline_strength_score": 79.0,
                "fade_risk_score": 33.0,
                "strong_pool_count": 3,
                "d1_count": 0,
                "focus_count": 0,
                "action_advice": "观察",
                "conclusion": "轮动观察",
            },
        ],
        "theme_capital_reviews": [
            {
                "subject_key": "pcb",
                "theme_name": "PCB",
                "total_inflow": 513_040_000.0,
                "top3_inflow": 85_900_000.0,
                "leader_inflow": 4_094_470.0,
                "inflow_stock_count": 83,
                "theme_kline": "强度 86.20",
                "cycle_stage": "divergence",
                "action": "观察",
                "rank_order": 1,
            },
            {
                "subject_key": "power",
                "theme_name": "电力运营",
                "total_inflow": 4_644_680_000.0,
                "top3_inflow": 196_900_000.0,
                "leader_inflow": 105_000_000.0,
                "inflow_stock_count": 129,
                "theme_kline": "强度 86.07",
                "cycle_stage": "fade_watch",
                "action": "谨慎",
                "rank_order": 2,
            },
            {
                "subject_key": "sat",
                "theme_name": "卫星互联网",
                "total_inflow": 2_805_450_000.0,
                "top3_inflow": 25_660_000.0,
                "leader_inflow": 22_190_000.0,
                "inflow_stock_count": 158,
                "theme_kline": "强度 83.82",
                "cycle_stage": "watch",
                "action": "轮动观察",
                "rank_order": 3,
            },
        ],
        "post_market_decision_v2": {
            "weak_to_strong_d1_reviews": [
                {"stock_id": "1", "stock_name": "A"},
                {"stock_id": "2", "stock_name": "B"},
                {"stock_id": "3", "stock_name": "C"},
            ],
            "next_day_focus_stocks": [],
            "strong_stock_pool_reviews": [
                {"stock_id": "1", "stock_name": "A", "mainline_name": "PCB", "relay_role": "leader", "watch_score": 88, "support_score": 70, "watch_priority": 1, "main_net_inflow": 1200000},
                {"stock_id": "2", "stock_name": "B", "mainline_name": "电力运营", "relay_role": "runner", "watch_score": 84, "support_score": 66, "watch_priority": 2, "main_net_inflow": 800000},
            ],
            "diagnostics": {"d1_algorithm": "BuildWeakToStrongCandidateUseCase"},
        },
        "market_overview_review": {
            "theme_limitup_matrix": {
                "columns": [
                    {
                        "subject_key": "pcb",
                        "theme_name": "PCB",
                        "limit_up_count": 8,
                        "active_mainline": True,
                        "lifecycle_state": "divergence",
                        "trade_action": "主线分歧",
                        "focus_stocks": [
                            {"stock_id": "1", "stock_name": "A", "board_count": 3, "role_label": "leader", "trade_action": "主线参与"},
                            {"stock_id": "4", "stock_name": "D", "board_count": 2, "role_label": "runner", "trade_action": "主线分歧"},
                        ],
                    },
                    {
                        "subject_key": "power",
                        "theme_name": "电力运营",
                        "limit_up_count": 5,
                        "active_mainline": True,
                        "lifecycle_state": "fade_watch",
                        "trade_action": "观察",
                        "focus_stocks": [
                            {"stock_id": "2", "stock_name": "B", "board_count": 2, "role_label": "runner", "trade_action": "观察"},
                        ],
                    },
                    {
                        "subject_key": "sat",
                        "theme_name": "卫星互联网",
                        "limit_up_count": 4,
                        "active_mainline": False,
                        "lifecycle_state": "watch",
                        "trade_action": "轮动观察",
                        "focus_stocks": [
                            {"stock_id": "3", "stock_name": "C", "board_count": 1, "role_label": "watch", "trade_action": "轮动观察"},
                        ],
                    },
                ],
                "max_rows": 0,
                "count_method": "display_by_theme",
            },
            "limit_up_total": 17,
            "limit_down_total": 0,
            "up_count": 2860,
            "down_count": 1220,
            "total_amount": 123456789012,
            "diagnostics": {"theme_count": 3, "stock_count": 12},
        },
    }


def test_post_market_narrative_composer_generates_market_overview() -> None:
    doc = _sample_engine_report_doc()
    narrative = PostMarketNarrativeComposer().compose_market_overview(
        engine_summary=doc["engine_summary"],  # type: ignore[arg-type]
        market_regime_review=doc["market_regime_review"],  # type: ignore[arg-type]
        index_technical_reviews=doc["index_technical_reviews"],  # type: ignore[arg-type]
        mainline_daily_states=doc["mainline_daily_states"],  # type: ignore[arg-type]
        post_market_decision_v2=doc["post_market_decision_v2"],  # type: ignore[arg-type]
        market_overview_review=doc["market_overview_review"],  # type: ignore[arg-type]
        market_summary=doc["market_summary"],  # type: ignore[arg-type]
    )

    assert narrative["source"] == "engine_template"
    assert narrative["headline"]
    assert len(narrative["core_points"]) >= 3
    assert "观察" in narrative["next_day_strategy"]
    assert narrative["risk_warning"]
    assert "PCB" in narrative["hotspot_summary"]
    assert "上证指数" in narrative["index_summary"]


def test_post_market_narrative_composer_generates_market_hotspot() -> None:
    doc = _sample_engine_report_doc()
    narrative = PostMarketNarrativeComposer().compose_market_hotspot(
        market_overview_review=doc["market_overview_review"],  # type: ignore[arg-type]
        market_summary=doc["market_summary"],  # type: ignore[arg-type]
        market_regime_review=doc["market_regime_review"],  # type: ignore[arg-type]
        mainline_daily_states=doc["mainline_daily_states"],  # type: ignore[arg-type]
        engine_summary=doc["engine_summary"],  # type: ignore[arg-type]
        post_market_decision_v2=doc["post_market_decision_v2"],  # type: ignore[arg-type]
    )

    assert narrative["source"] == "engine_template"
    assert narrative["headline"]
    assert len(narrative["core_points"]) >= 3
    assert narrative["strongest_themes"][0]["theme_name"] == "PCB"
    assert "电力运营" in narrative["rotation_themes"] or "卫星互联网" in narrative["rotation_themes"]
    assert narrative["market_heat_summary"]
    assert narrative["next_day_focus"]


def test_post_market_hotspot_overview_composer_generates_rows() -> None:
    doc = _sample_engine_report_doc()
    hotspot = PostMarketHotspotOverviewComposer().compose(doc)

    assert hotspot["source"] == "structured"
    assert hotspot["summary"]
    assert len(hotspot["hotspot_rows"]) >= 3
    assert hotspot["strongest_themes"][0] == "PCB"
    assert "PCB" in hotspot["mainline_related_themes"]
    assert "卫星互联网" in hotspot["rotation_themes"]
    assert "电力运营" in hotspot["risk_themes"]
    first = hotspot["hotspot_rows"][0]
    assert first["theme_name"]
    assert first["rank_order"] == 1
    assert first["representative_stocks"]
    assert first["is_confirmed_mainline"] is True


def test_post_market_engine_report_composer_includes_market_overview_narrative() -> None:
    doc = _sample_engine_report_doc()
    report = PostMarketEngineReportComposer().compose(doc)  # type: ignore[arg-type]

    assert "market_overview_narrative" in report
    assert "market_hotspot_narrative" in report
    assert "market_hotspot_overview" in report
    narrative = report["market_overview_narrative"]
    assert narrative["headline"]
    assert len(narrative["core_points"]) >= 3
    assert narrative["diagnostics"]["d1_count"] == 3
    assert narrative["diagnostics"]["focus_count"] == 0
    hotspot = report["market_hotspot_narrative"]
    assert hotspot["headline"]
    assert hotspot["strongest_themes"][0]["theme_name"] == "PCB"
    overview = report["market_hotspot_overview"]
    assert overview["summary"]
    assert len(overview["hotspot_rows"]) >= 3
    assert overview["hotspot_rows"][0]["theme_name"] == "PCB"

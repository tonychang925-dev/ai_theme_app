from stock_processing_service.application.services.analyst_charts.chart_engine import (
    ChartReproductionEngine,
)
from stock_processing_service.application.services.analyst_workbench.draft_context_builder import (
    DraftContextBuilder,
)


def test_limitup_categories_use_strong_hotspot_subjects_contract() -> None:
    chart = ChartReproductionEngine._build_limitup(
        {
            "strong_hotspot_subjects": [
                {
                    "subject_key": "9066740",
                    "theme_name": "磷化铟",
                    "stock_id": "600206.SH",
                    "stock_name": "有研新材",
                    "source": "confirmed_mainline",
                },
                {
                    "subject_key": "9066740",
                    "theme_name": "磷化铟",
                    "stock_id": "300123.SZ",
                    "stock_name": "测试股份",
                    "source": "confirmed_mainline",
                },
                {"subject_key": "bad", "theme_name": "【驱动事件：长文本】"},
            ]
        },
        75,
    )

    categories = chart["data"]["categories"]
    assert categories["9066740"]["theme_name"] == "磷化铟"
    assert categories["9066740"]["count"] == 2
    assert categories["9066740"]["source"] == "post_market_recap_snapshot.strong_hotspot_subjects"
    assert categories["9066740"]["stocks"][0] == {"code": "600206.SH", "name": "有研新材"}
    assert "bad" not in categories

    ctx = DraftContextBuilder().build(
        trade_date="2026-07-09",
        chart_json=[chart],
        emotion_json={"emotion_node": "CHAOS", "emotion_score": 39},
        derived_context={"themes": [{"subject_key": "9066740", "theme_name": "磷化铟"}]},
    )

    assert ctx.limit_up["total"] == 75
    assert ctx.limit_up["source"] == "chart.limitup_classification"
    assert ctx.limit_up["categories"][0]["theme_key"] == "9066740"
    assert ctx.limit_up["categories"][0]["theme_name"] == "磷化铟"
    assert ctx.limit_up["categories"][0]["count"] == 2

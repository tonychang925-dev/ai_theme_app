from stock_service.services.stock_screener_llm_review_service import StockScreenerLlmReviewService
from stock_service.services.theme_leader_llm_judgement_service import ThemeLeaderLlmJudgementService
from stock_service.stock_screener_models import DimensionScores, ScreeningResult


class _DummyRepo:
    async def save_llm_reviews(self, **kwargs):
        return None


def test_normalize_response_reuses_theme_leader_json_extractor():
    service = StockScreenerLlmReviewService(_DummyRepo())  # type: ignore[arg-type]
    parsed = service._normalize_response(  # noqa: SLF001
        {
            "response": '```json\n{"decision":"pass","score":82,"confidence":0.88}\n```'
        }
    )
    assert parsed["decision"] == "pass"
    assert parsed["score"] == 82
    assert parsed["confidence"] == 0.88


def test_prompt_version_and_template_are_shared_with_theme_leader_module():
    service = StockScreenerLlmReviewService(_DummyRepo())  # type: ignore[arg-type]
    assert service.prompt_version == ThemeLeaderLlmJudgementService.screener_prompt_version

    item = ScreeningResult(
        stock_id="000001.SZ",
        stock_name="平安银行",
        composite_score=78.5,
        dimension_scores=DimensionScores(mainline=80, cycle=75, leader=70, technical=72),
        trade_date=None,
        screening_reason="主线与周期共振，技术结构完整",
        theme_info={"theme_name": "金融科技"},
    )
    prompt = service._build_prompt(item)  # noqa: SLF001
    assert "你是A股短线交易复核裁决器" in prompt
    assert "JSON字段：decision(pass/watch/reject/failed)" in prompt
    assert "股票: 000001.SZ 平安银行" in prompt

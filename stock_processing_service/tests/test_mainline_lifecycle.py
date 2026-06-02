"""Tests for PR-10: MainlineLifecycleLayerBAdapter."""
import pytest
from stock_processing_service.domain.services.mainline_lifecycle.models import (
    MainlineLifecycleReview, MainlineLifecycleFactContext,
)
from stock_processing_service.domain.services.mainline_lifecycle.layer_b_lifecycle_adapter import (
    MainlineLifecycleLayerBAdapter,
    _playability,
)


def _cml(ml_id="ml_test", csk="sk_a", name="测试主线", **kw):
    return {
        "mainline_id": ml_id,
        "mainline_name": name,
        "canonical_subject_key": csk,
        "related_subject_keys_json": kw.pop("related", []),
        **kw,
    }


def _jd(state="fermentation", alive=True, strength=72, fade_risk=25, fade_watch=30, fade_confirmed=15, support_break=False):
    return {
        "subject_key": "sk_a",
        "final_cycle_state": state,
        "final_mainline_alive": alive,
        "mainline_strength_score": strength,
        "fade_risk_score": fade_risk,
        "fade_watch_score": fade_watch,
        "fade_confirmed_score": fade_confirmed,
        "support_break": support_break,
        "fade_reason_codes": [],
    }


class TestLayerBAdapter:

    def test_confirmed_mainline_with_judgement(self):
        fc = MainlineLifecycleFactContext(
            trade_date="2026-04-29",
            confirmed_mainlines=[_cml()],
            cycle_judgement_by_sk={"sk_a": _jd(state="fermentation", strength=72)},
        )
        adapter = MainlineLifecycleLayerBAdapter()
        reviews, _diag = adapter.build(trade_date="2026-04-29", fact_ctx=fc)
        assert len(reviews) == 1
        r = reviews[0]
        assert r.lifecycle_state == "fermentation"
        assert r.mainline_alive is True
        assert r.mainline_trade_alive is True
        assert r.diagnostics["layer_b_reused"] is True

    def test_missing_layer_b_judgement(self):
        fc = MainlineLifecycleFactContext(
            trade_date="2026-04-29",
            confirmed_mainlines=[_cml(csk="missing_sk")],
            cycle_judgement_by_sk={},
        )
        adapter = MainlineLifecycleLayerBAdapter()
        reviews, _diag = adapter.build(trade_date="2026-04-29", fact_ctx=fc)
        assert len(reviews) == 1
        r = reviews[0]
        assert r.lifecycle_state == "unknown"
        assert r.mainline_alive is False
        assert r.diagnostics["missing_layer_b_judgement"] is True

    def test_fade_confirmed_not_trade_alive(self):
        fc = MainlineLifecycleFactContext(
            trade_date="2026-04-29",
            confirmed_mainlines=[_cml()],
            cycle_judgement_by_sk={"sk_a": _jd(state="fade_confirmed", alive=True, fade_confirmed=60)},
        )
        adapter = MainlineLifecycleLayerBAdapter()
        reviews, _diag = adapter.build(trade_date="2026-04-29", fact_ctx=fc)
        r = reviews[0]
        assert r.lifecycle_state == "fade_confirmed"
        assert r.mainline_trade_alive is False
        assert r.risk_state == "inactive"

    def test_related_subjects_included(self):
        fc = MainlineLifecycleFactContext(
            trade_date="2026-04-29",
            confirmed_mainlines=[_cml(related=["sk_b"])],
            cycle_judgement_by_sk={
                "sk_a": _jd(state="divergence"),
                "sk_b": {"subject_key": "sk_b", "final_cycle_state": "fermentation", "mainline_strength_score": 65},
            },
        )
        adapter = MainlineLifecycleLayerBAdapter()
        reviews, _diag = adapter.build(trade_date="2026-04-29", fact_ctx=fc)
        r = reviews[0]
        assert len(r.related_subject_states) == 1
        assert r.related_subject_states[0]["subject_key"] == "sk_b"

    def test_empty_registry_returns_empty(self):
        fc = MainlineLifecycleFactContext(trade_date="2026-04-29", confirmed_mainlines=[])
        adapter = MainlineLifecycleLayerBAdapter()
        reviews, _diag = adapter.build(trade_date="2026-04-29", fact_ctx=fc)
        assert len(reviews) == 0

    def test_playability_divergence(self):
        p = _playability("divergence", True, 30, 15)
        assert p["can_trade_if_market_safe"] is True
        assert "core_weak_to_strong_or_divergence_repair" in p["preferred_setup"]

    def test_playability_fade_confirmed(self):
        p = _playability("fade_confirmed", True, 70, 55)
        assert p["can_trade_if_market_safe"] is False
        assert "chase" in str(p["forbidden_setup"])

    def test_playability_dead(self):
        p = _playability("dead", False, 90, 80)
        assert p["can_trade_if_market_safe"] is False
        assert "all" in p["forbidden_setup"]

    def test_model_to_dict(self):
        r = MainlineLifecycleReview(
            trade_date="2026-04-29", mainline_id="ml_test", mainline_name="测试",
            canonical_subject_key="sk_a", lifecycle_state="fermentation",
            mainline_alive=True, mainline_trade_alive=True,
        )
        d = r.to_dict()
        assert d["lifecycle_state"] == "fermentation"
        assert d["mainline_alive"] is True

    def test_fact_context_to_dict(self):
        fc = MainlineLifecycleFactContext(
            trade_date="2026-04-29",
            confirmed_mainlines=[{"mainline_id": "ml_test"}],
            diagnostics={"confirmed_count": 1},
        )
        d = fc.to_dict()
        assert d["diagnostics"]["confirmed_count"] == 1

    def test_review_message_no_trading_principle(self):
        """CRITICAL: lifecycle review must not modify trading_principle."""
        fc = MainlineLifecycleFactContext(
            trade_date="2026-04-29", confirmed_mainlines=[_cml()],
            cycle_judgement_by_sk={"sk_a": _jd(state="start")},
        )
        adapter = MainlineLifecycleLayerBAdapter()
        reviews, _diag = adapter.build(trade_date="2026-04-29", fact_ctx=fc)
        r = reviews[0]
        # Verify the review dict does NOT contain trading fields
        d = r.to_dict()
        assert "trading_principle" not in d
        assert "watchlist" not in d
        assert "position_limit" not in d

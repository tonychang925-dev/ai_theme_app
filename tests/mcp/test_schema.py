"""Contract tests for DecisionEnvelope v1.1 — the neural interface between Market Brain and Julia.

These tests protect the shared language. If they break, Julia loses her eyes.
"""
import pytest
from datetime import datetime, timezone, timedelta

from core.contracts.decision_envelope import (
    AlertLevel,
    Lifecycle,
    Evidence,
    CausalLink,
    ThemeContext,
    DecisionEnvelope,
    ThemeStatusSnapshot,
    MarketSnapshot,
    DecisionExplanation,
    ChannelState,
)

CST = timezone(timedelta(hours=8))


class TestAlertLevel:
    def test_rank_ordering(self):
        """L0 noise < L1 observation < L2 watch < L3 alert < L4 decision."""
        ranks = AlertLevel.RANK
        assert ranks[AlertLevel.NOISE] == 0
        assert ranks[AlertLevel.OBSERVATION] == 1
        assert ranks[AlertLevel.WATCH] == 2
        assert ranks[AlertLevel.ALERT] == 3
        assert ranks[AlertLevel.DECISION] == 4


class TestEvidence:
    def test_create_minimal(self):
        ev = Evidence(type="news", text="OpenAI发布Agent能力")
        assert ev.type == "news"
        assert ev.text == "OpenAI发布Agent能力"

    def test_create_with_source(self):
        ev = Evidence(type="news", text="test", source="cls_api", ref_id="article_001", authority=0.9)
        assert ev.source == "cls_api"
        assert ev.ref_id == "article_001"
        assert ev.authority == 0.9


class TestCausalLink:
    def test_create(self):
        link = CausalLink(
            cause="OpenAI发布Agent能力",
            effect="AI Agent产业关注度提升",
            market_response="相关概念股上涨",
            confidence=0.85,
        )
        assert link.cause
        assert link.effect
        assert link.market_response
        assert 0 <= link.confidence <= 1


class TestThemeContext:
    def test_create(self):
        ctx = ThemeContext(
            theme_id="9019807",
            lifecycle=Lifecycle.DIFFUSION,
            previous_state=Lifecycle.START,
            change="heat increasing",
            first_signal_date="2026-07-30",
            days_active=7,
        )
        assert ctx.lifecycle == Lifecycle.DIFFUSION
        assert ctx.days_active == 7


class TestDecisionEnvelope:
    def test_create_minimal(self):
        dec = DecisionEnvelope(source="news", type="event_news")
        assert dec.id.startswith("dec_")
        assert dec.level == AlertLevel.OBSERVATION
        assert dec.confidence == 0.0
        assert dec.is_active

    def test_create_full_v1_1(self):
        ev = Evidence(type="news", text="AI Agent政策催化")
        link = CausalLink(
            cause="政策催化",
            effect="产业预期升温",
            market_response="AI板块上涨",
            confidence=0.82,
        )
        ctx = ThemeContext(
            theme_id="9019807",
            lifecycle=Lifecycle.DIFFUSION,
            change="heat increasing",
            days_active=5,
        )
        dec = DecisionEnvelope(
            source="news",
            type="theme_match",
            level=AlertLevel.DECISION,
            evidence=(ev,),
            causal_chain=(link,),
            theme_context=ctx,
            prediction_id="pred_20260806_001",
            confidence=0.82,
            impact="positive",
        )
        assert dec.is_high_confidence
        assert dec.level == AlertLevel.DECISION
        assert dec.theme_context is not None
        assert dec.theme_context.theme_id == "9019807"
        assert len(dec.causal_chain) == 1
        assert dec.prediction_id == "pred_20260806_001"

    def test_expired_signal(self):
        past = (datetime.now(CST) - timedelta(hours=1)).isoformat()
        dec = DecisionEnvelope(source="news", expiry=past)
        assert not dec.is_active

    def test_confidence_bounds(self):
        with pytest.raises(ValueError):
            DecisionEnvelope(source="test", confidence=1.5)

    def test_invalid_level(self):
        with pytest.raises(ValueError):
            DecisionEnvelope(source="test", level="INVALID")


class TestThemeStatusSnapshot:
    def test_create(self):
        snap = ThemeStatusSnapshot(
            theme="机器人",
            lifecycle=Lifecycle.DIFFUSION,
            heat_score=87,
            leaders=("拓斯达", "绿的谐波"),
            money_flow="increase",
            risk="medium",
        )
        assert snap.heat_score == 87
        assert len(snap.leaders) == 2


class TestMarketSnapshot:
    def test_create(self):
        dec = DecisionEnvelope(source="test")
        snap = MarketSnapshot(
            market_sentiment="偏强",
            active_themes=("AI Agent", "半导体"),
            top_signals=(dec,),
            risk_alerts=("外围市场波动",),
        )
        assert snap.market_sentiment == "偏强"
        assert len(snap.active_themes) == 2


class TestDecisionExplanation:
    def test_create(self):
        link = CausalLink(
            cause="政策催化",
            effect="产业预期升温",
            market_response="板块上涨",
            confidence=0.85,
        )
        exp = DecisionExplanation(
            decision_id="dec_test_001",
            summary="AI Agent板块出现扩散信号",
            causal_chain=(link,),
            supporting_evidence=4,
            opposing_evidence=1,
            confidence=0.82,
            risk_factors=("市场情绪偏弱", "成交量未能放大"),
            alternatives=("短期情绪炒作",),
        )
        assert exp.supporting_evidence == 4
        assert exp.opposing_evidence == 1
        assert len(exp.risk_factors) == 2


class TestChannelState:
    def test_create(self):
        cs = ChannelState(subscribed=("AI_AGENT", "SEMICONDUCTOR"), active=True)
        assert len(cs.subscribed) == 2
        assert cs.active

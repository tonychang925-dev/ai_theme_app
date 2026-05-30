"""P0 unit tests for PostMarketDecisionEngine and its sub-engines."""

import pytest

from stock_processing_service.domain.services.post_market_decision.market_environment_engine import (
    MarketEnvironmentEngine,
)
from stock_processing_service.domain.services.post_market_decision.theme_decision_engine import (
    ThemeDecisionEngine,
)
from stock_processing_service.domain.services.post_market_decision.leader_core_engine import (
    LeaderCoreEngine,
)
from stock_processing_service.domain.services.post_market_decision.next_day_watchlist_engine import (
    NextDayWatchlistEngine,
)
from stock_processing_service.domain.services.post_market_decision.trading_principle_engine import (
    TradingPrincipleEngine,
)
from stock_processing_service.domain.services.post_market_decision.post_market_decision_engine import (
    PostMarketDecisionEngine,
)


# ── MarketEnvironmentEngine ──

class TestMarketEnvironmentEngine:

    def test_defense_mode_with_moderate_market(self):
        engine = MarketEnvironmentEngine()
        result = engine.build(
            trade_date="2026-05-22",
            report_context={
                "market": {
                    "market_health_score": 42,
                    "limit_up_count": 38,
                    "limit_down_count": 8,
                },
            },
        )
        assert result["market_mode"] == "defense"
        assert result["position_limit"] == 0.3
        assert result["allow_trade"] is True
        assert "非主线追涨" in result["forbidden_actions"]

    def test_attack_mode_with_strong_market(self):
        engine = MarketEnvironmentEngine()
        result = engine.build(
            trade_date="2026-05-22",
            report_context={
                "market": {
                    "market_health_score": 80,
                    "limit_up_count": 75,
                    "limit_down_count": 3,
                },
            },
        )
        assert result["market_mode"] == "attack"
        assert result["position_limit"] == 1.0
        assert result["allow_trade"] is True

    def test_wait_mode_with_weak_market(self):
        engine = MarketEnvironmentEngine()
        result = engine.build(
            trade_date="2026-05-22",
            report_context={
                "market": {
                    "market_health_score": 20,
                    "limit_up_count": 10,
                    "limit_down_count": 80,
                },
            },
        )
        assert result["market_mode"] == "wait"
        assert result["position_limit"] == 0.0
        assert result["allow_trade"] is False

    def test_fallback_score_from_counts_when_missing(self):
        engine = MarketEnvironmentEngine()
        result = engine.build(
            trade_date="2026-05-22",
            report_context={
                "market": {
                    "limit_up_count": 50,
                    "limit_down_count": 30,
                },
            },
        )
        assert "market_score.from_limit_counts" in result["diagnostics"]["fallback_used"]
        assert result["market_mode"] == "wait"

    def test_missing_market_context(self):
        engine = MarketEnvironmentEngine()
        result = engine.build(
            trade_date="2026-05-22",
            report_context={},
        )
        assert result["diagnostics"]["data_quality"] == "missing_market_context"
        assert result["position_limit"] == 0.0

    def test_risk_flags_on_defense(self):
        engine = MarketEnvironmentEngine()
        result = engine.build(
            trade_date="2026-05-22",
            report_context={
                "market": {
                    "market_health_score": 42,
                    "limit_up_count": 38,
                    "limit_down_count": 15,
                },
            },
        )
        assert any("偏弱" in f for f in result["risk_flags"])
        assert any("跌停家数偏多" in f for f in result["risk_flags"])

    def test_normal_mode(self):
        engine = MarketEnvironmentEngine()
        result = engine.build(
            trade_date="2026-05-22",
            report_context={
                "market": {
                    "market_health_score": 60,
                    "limit_up_count": 50,
                    "limit_down_count": 6,
                },
            },
        )
        assert result["market_mode"] == "normal"
        assert result["position_limit"] == 0.5


# ── ThemeDecisionEngine ──

class TestThemeDecisionEngine:

    def _theme_context(self, theme_name="卫星互联网", mainline_strength=75, fade_risk=20,
                       alive=True, final_state="divergence",
                       total_inflow=10_000_000, leader_inflow=5_000_000,
                       stock_facts=None):
        return {
            "9019807": {
                "cycle": {
                    "theme_name": theme_name,
                    "mainline_strength_score": mainline_strength,
                    "fade_risk_score": fade_risk,
                    "final_mainline_alive": alive,
                    "final_cycle_state": final_state,
                },
                "capital": {
                    "main_net_inflow_sum": total_inflow,
                    "leader_main_net_inflow": leader_inflow,
                },
                "stock_facts": stock_facts or [],
            },
        }

    def test_action_advice_not_empty(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map=self._theme_context(),
            market_environment={"market_mode": "defense", "market_score": 42, "position_limit": 0.3},
        )
        assert rows
        row = rows[0]
        assert row["capital_validation"] == "positive"
        assert row["action_advice"], "action_advice must not be empty"
        assert row["conclusion"], "conclusion must not be empty"

    def test_capital_validation_positive(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map=self._theme_context(total_inflow=50_000_000, leader_inflow=20_000_000),
            market_environment={"market_mode": "normal", "market_score": 65, "position_limit": 0.5},
        )
        assert rows[0]["capital_validation"] == "positive"

    def test_capital_validation_negative(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map=self._theme_context(total_inflow=-10_000_000, leader_inflow=-5_000_000),
            market_environment={"market_mode": "defense", "market_score": 42, "position_limit": 0.3},
        )
        assert rows[0]["capital_validation"] == "negative"

    def test_capital_validation_unknown_for_no_capital(self):
        engine = ThemeDecisionEngine()
        ctx = self._theme_context()
        ctx["9019807"].pop("capital")
        rows = engine.build(
            theme_context_map=ctx,
            market_environment={"market_mode": "defense", "market_score": 42, "position_limit": 0.3},
        )
        assert rows[0]["capital_validation"] == "unknown"

    def test_fade_avoid_when_not_alive_and_weak(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map=self._theme_context(alive=False, mainline_strength=30, fade_risk=80),
            market_environment={"market_mode": "defense", "market_score": 42, "position_limit": 0.3},
        )
        assert rows[0]["decision"] == "fade_avoid"

    def test_risk_watch_when_high_fade_risk(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map=self._theme_context(fade_risk=75),
            market_environment={"market_mode": "normal", "market_score": 60, "position_limit": 0.5},
        )
        assert rows[0]["decision"] == "risk_watch"

    def test_mainline_focus_in_attack_mode(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map=self._theme_context(mainline_strength=80, fade_risk=10),
            market_environment={"market_mode": "attack", "market_score": 85, "position_limit": 1.0},
        )
        assert rows[0]["decision"] == "mainline_focus"

    def test_watch_weak_to_strong_in_defense(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map=self._theme_context(mainline_strength=75),
            market_environment={"market_mode": "defense", "market_score": 42, "position_limit": 0.3},
        )
        assert rows[0]["decision"] == "watch_weak_to_strong"

    def test_reject_for_weak_theme(self):
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map={
                "weak_theme": {
                    "cycle": {"theme_name": "弱题材", "mainline_strength_score": 40, "fade_risk_score": 30,
                              "final_mainline_alive": True, "final_cycle_state": "unknown"},
                    "capital": {},
                    "stock_facts": [],
                }
            },
            market_environment={"market_mode": "defense", "market_score": 42, "position_limit": 0.3},
        )
        assert rows[0]["decision"] == "reject"

    def test_reject_reason_populated(self):
        """P1-2: rejected themes must have reject_reason."""
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map={
                "weak_theme": {
                    "cycle": {"theme_name": "弱题材", "mainline_strength_score": 40, "fade_risk_score": 30,
                              "final_mainline_alive": True, "final_cycle_state": "unknown"},
                    "capital": {},
                    "stock_facts": [],
                }
            },
            market_environment={"market_mode": "defense", "market_score": 42, "position_limit": 0.3},
        )
        assert rows
        assert rows[0]["decision"] == "reject"
        assert rows[0]["reject_reason"] is not None
        assert "tier_below_strong_branch" in rows[0]["reject_reason"]

    def test_logic_score_from_events(self):
        """P1-2: logic_score computed from event_context."""
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map={
                "t1": {
                    "cycle": {"theme_name": "主线A", "mainline_strength_score": 80, "fade_risk_score": 10,
                              "final_mainline_alive": True, "final_cycle_state": "fermentation"},
                    "capital": {"main_net_inflow_sum": 5e7, "leader_main_net_inflow": 2e7},
                    "stock_facts": [],
                }
            },
            market_environment={"market_mode": "normal", "market_score": 65, "position_limit": 0.5},
            event_context={
                "t1": [
                    {"event_id": "e1", "title": "政策利好", "event_type": "policy",
                     "impact_score": 0.9, "confidence": 0.95, "source_channel": "news"},
                ]
            },
        )
        assert rows
        row = rows[0]
        assert row["logic_score"] is not None
        assert row["logic_score"] > 0
        assert row["event_chain"]
        assert row["event_chain"][0]["event_type"] == "policy"

    def test_logic_upgrade_reject_to_strong_branch(self):
        """P1-2: high logic_score upgrades reject → strong_branch_watch."""
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map={
                "t1": {
                    "cycle": {"theme_name": "弱题材", "mainline_strength_score": 40, "fade_risk_score": 30,
                              "final_mainline_alive": True, "final_cycle_state": "start"},
                    "capital": {},
                    "stock_facts": [],
                }
            },
            market_environment={"market_mode": "normal", "market_score": 65, "position_limit": 0.5},
            event_context={
                "t1": [
                    {"event_id": "e1", "title": "重大政策", "event_type": "policy",
                     "impact_score": 0.95, "confidence": 0.90, "source_channel": "news"},
                ]
            },
        )
        assert rows
        row = rows[0]
        assert row["original_decision"] == "reject"
        assert row["decision"] == "strong_branch_watch"
        assert row["action_advice"] != "证据不足，观察"

    def test_logic_never_upgrades_to_mainline(self):
        """P1-2: logic_score must never upgrade to mainline_focus."""
        engine = ThemeDecisionEngine()
        rows = engine.build(
            theme_context_map={
                "t1": {
                    "cycle": {"theme_name": "弱题材", "mainline_strength_score": 40, "fade_risk_score": 30,
                              "final_mainline_alive": True, "final_cycle_state": "start"},
                    "capital": {},
                    "stock_facts": [],
                }
            },
            market_environment={"market_mode": "attack", "market_score": 85, "position_limit": 1.0},
            event_context={
                "t1": [
                    {"event_id": "e1", "title": "超级政策", "event_type": "policy",
                     "impact_score": 1.0, "confidence": 1.0, "source_channel": "gov"},
                ]
            },
        )
        assert rows
        assert rows[0]["decision"] != "mainline_focus"   # never skips market confirmation

    def test_all_rows_have_action_advice_and_conclusion(self):
        engine = ThemeDecisionEngine()
        ctx = {
            "mainline_1": {
                "cycle": {"theme_name": "主线A", "mainline_strength_score": 80, "fade_risk_score": 10,
                          "final_mainline_alive": True, "final_cycle_state": "fermentation"},
                "capital": {"main_net_inflow_sum": 5e7, "leader_main_net_inflow": 2e7},
                "stock_facts": [],
            },
            "branch_1": {
                "cycle": {"theme_name": "分支B", "mainline_strength_score": 55, "fade_risk_score": 30,
                          "final_mainline_alive": True, "final_cycle_state": "start"},
                "capital": {},
                "stock_facts": [],
            },
        }
        rows = engine.build(
            theme_context_map=ctx,
            market_environment={"market_mode": "normal", "market_score": 65, "position_limit": 0.5},
        )
        assert len(rows) == 2
        for row in rows:
            assert row["action_advice"], f"action_advice empty for {row['theme_name']}"
            assert row["conclusion"], f"conclusion empty for {row['theme_name']}"


# ── LeaderCoreEngine ──

class TestLeaderCoreEngine:

    def test_leader_role_from_watch_score(self):
        engine = LeaderCoreEngine()
        rows = engine.build(
            report_context={},
            strong_stock_reviews=[
                {
                    "stock_id": "000001.SZ",
                    "stock_name": "龙头股",
                    "subject_key": "theme_1",
                    "theme_name": "主线A",
                    "watch_score": 85,
                    "support_score": 80,
                    "main_net_inflow": 50_000_000,
                },
            ],
        )
        assert rows
        assert rows[0]["role"] == "leader"
        assert rows[0]["role_label"] == "龙头"
        assert rows[0]["core_score"] > 0

    def test_sub_leader_role(self):
        engine = LeaderCoreEngine()
        rows = engine.build(
            report_context={},
            strong_stock_reviews=[
                {
                    "stock_id": "000002.SZ",
                    "stock_name": "龙二股",
                    "watch_score": 72,
                    "support_score": 65,
                    "main_net_inflow": 15_000_000,
                },
            ],
        )
        assert rows[0]["role"] == "sub_leader"
        assert rows[0]["buy_condition"]
        assert rows[0]["invalid_condition"]

    def test_all_rows_have_buy_and_invalid_conditions(self):
        engine = LeaderCoreEngine()
        rows = engine.build(
            report_context={},
            strong_stock_reviews=[
                {"stock_id": f"00000{i}.SZ", "stock_name": f"股票{i}", "watch_score": 60 + i * 5,
                 "support_score": 50, "main_net_inflow": 10_000_000}
                for i in range(5)
            ],
        )
        for row in rows:
            assert row["buy_condition"], f"buy_condition empty for {row['stock_name']}"
            assert row["invalid_condition"], f"invalid_condition empty for {row['stock_name']}"


# ── NextDayWatchlistEngine ──

class TestNextDayWatchlistEngine:

    def test_watchlist_has_conditions(self):
        engine = NextDayWatchlistEngine()
        rows, _diag = engine.build(
            theme_decisions=[
                {
                    "subject_key": "9019807",
                    "theme_name": "卫星互联网",
                    "decision": "watch_weak_to_strong",
                    "cycle_stage": "divergence",
                    "action_advice": "只看核心弱转强",
                },
            ],
            stock_decisions=[
                {
                    "stock_id": "002361.SZ",
                    "stock_code": "002361.SZ",
                    "stock_name": "神剑股份",
                    "subject_key": "9019807",
                    "theme_name": "卫星互联网",
                    "role": "sub_leader",
                    "role_label": "龙二",
                    "support_score": 80,
                    "buy_condition": ["竞价确认"],
                    "invalid_condition": ["跌破支撑"],
                    "core_score": 78,
                },
            ],
            market_environment={"market_mode": "defense", "position_limit": 0.3},
        )
        assert rows
        assert rows[0]["buy_condition"]
        assert rows[0]["invalid_condition"]
        assert rows[0]["category"] == "弱转强观察"

    def test_excludes_wait_market_mode(self):
        engine = NextDayWatchlistEngine()
        rows, _diag = engine.build(
            theme_decisions=[
                {"subject_key": "t1", "theme_name": "测试", "decision": "mainline_focus",
                 "cycle_stage": "fermentation", "action_advice": "测试"},
            ],
            stock_decisions=[
                {"stock_id": "000001.SZ", "stock_name": "测试股", "subject_key": "t1",
                 "theme_name": "测试", "role": "leader", "role_label": "龙头",
                 "support_score": 80, "buy_condition": ["条件"], "invalid_condition": ["失效"],
                 "core_score": 85},
            ],
            market_environment={"market_mode": "wait", "position_limit": 0.0},
        )
        assert len(rows) == 0

    def test_key_observation_category(self):
        engine = NextDayWatchlistEngine()
        rows, _diag = engine.build(
            theme_decisions=[
                {"subject_key": "t1", "theme_name": "主线", "decision": "mainline_focus",
                 "cycle_stage": "fermentation", "action_advice": "主线重点"},
            ],
            stock_decisions=[
                {"stock_id": "000001.SZ", "stock_name": "龙头", "subject_key": "t1",
                 "theme_name": "主线", "role": "leader", "role_label": "龙头",
                 "support_score": 90, "buy_condition": ["竞价"], "invalid_condition": ["失效"],
                 "core_score": 90},
            ],
            market_environment={"market_mode": "attack", "position_limit": 1.0},
        )
        assert rows
        assert rows[0]["category"] == "重点观察"


# ── TradingPrincipleEngine ──

class TestTradingPrincipleEngine:

    def test_no_trade_without_mainline(self):
        engine = TradingPrincipleEngine()
        result = engine.build(
            trade_date="2026-05-22",
            market_environment={"market_mode": "wait", "position_limit": 0.0, "risk_flags": ["市场退潮"]},
            theme_decisions=[],
            watchlist_reviews=[],
        )
        assert result["allow_trade"] is False
        assert result["position_limit"] == 0.0
        assert result["no_trade_reasons"]

    def test_no_trade_when_no_mainline_themes(self):
        engine = TradingPrincipleEngine()
        result = engine.build(
            trade_date="2026-05-22",
            market_environment={"market_mode": "normal", "position_limit": 0.5, "risk_flags": []},
            theme_decisions=[
                {"subject_key": "t1", "theme_name": "弱题材", "decision": "reject"},
            ],
            watchlist_reviews=[],
        )
        assert result["allow_trade"] is False
        assert "无明确主线方向" in result["no_trade_reasons"]

    def test_defense_mode_strategy(self):
        engine = TradingPrincipleEngine()
        result = engine.build(
            trade_date="2026-05-22",
            market_environment={"market_mode": "defense", "position_limit": 0.3,
                              "risk_flags": ["偏弱"], "allowed_actions": ["主线核心弱转强"],
                              "forbidden_actions": ["追涨"]},
            theme_decisions=[
                {"subject_key": "t1", "theme_name": "主线A", "decision": "watch_weak_to_strong"},
            ],
            watchlist_reviews=[{"stock_id": "000001.SZ"}],
        )
        assert result["allow_trade"] is True
        assert result["position_limit"] == 0.3
        assert result["main_strategy"] == "只做主线核心弱转强"
        assert "主线A" in result["focus_themes"]

    def test_attack_mode_strategy(self):
        engine = TradingPrincipleEngine()
        result = engine.build(
            trade_date="2026-05-22",
            market_environment={"market_mode": "attack", "position_limit": 1.0,
                              "risk_flags": [], "allowed_actions": ["主线龙头"],
                              "forbidden_actions": []},
            theme_decisions=[
                {"subject_key": "t1", "theme_name": "主线A", "decision": "mainline_focus"},
            ],
            watchlist_reviews=[{"stock_id": "000001.SZ"}],
        )
        assert result["position_limit"] == 1.0
        assert result["main_strategy"] == "主线龙头优先"


# ── PostMarketDecisionEngine (integration) ──

class TestPostMarketDecisionEngine:

    def test_full_pipeline_outputs_all_keys(self):
        engine = PostMarketDecisionEngine()
        result = engine.execute(
            trade_date="2026-05-22",
            report_context={
                "market": {
                    "market_health_score": 60,
                    "limit_up_count": 50,
                    "limit_down_count": 5,
                },
            },
            theme_context_map={
                "9019807": {
                    "cycle": {
                        "theme_name": "卫星互联网",
                        "mainline_strength_score": 75,
                        "fade_risk_score": 20,
                        "final_mainline_alive": True,
                        "final_cycle_state": "divergence",
                    },
                    "capital": {
                        "main_net_inflow_sum": 10_000_000,
                        "leader_main_net_inflow": 5_000_000,
                    },
                    "stock_facts": [],
                },
            },
            strong_stock_reviews=[
                {
                    "stock_id": "002361.SZ",
                    "stock_name": "神剑股份",
                    "subject_key": "9019807",
                    "theme_name": "卫星互联网",
                    "watch_score": 82,
                    "support_score": 80,
                    "main_net_inflow": 35_000_000,
                },
            ],
        )
        assert "market_environment_review" in result
        assert "theme_decision_reviews" in result
        assert "strong_stock_decision_reviews" in result
        assert "watchlist_reviews" in result
        assert "trading_principle" in result
        assert "decision_diagnostics" in result

        for row in result["theme_decision_reviews"]:
            assert row["action_advice"], f"action_advice empty for {row.get('theme_name')}"
            assert row["conclusion"], f"conclusion empty for {row.get('theme_name')}"

        for row in result["watchlist_reviews"]:
            assert row["buy_condition"], "buy_condition empty"
            assert row["invalid_condition"], "invalid_condition empty"

    def test_full_pipeline_with_empty_data(self):
        """Smoke test: engine should not crash with minimal input."""
        engine = PostMarketDecisionEngine()
        result = engine.execute(
            trade_date="2026-05-22",
            report_context={},
            theme_context_map={},
            strong_stock_reviews=[],
        )
        assert result["market_environment_review"]
        assert result["theme_decision_reviews"] == []
        assert result["trading_principle"]
        assert result["trading_principle"]["allow_trade"] is False

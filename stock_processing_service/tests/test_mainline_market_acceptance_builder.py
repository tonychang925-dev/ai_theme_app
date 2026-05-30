"""Tests for MainlineMarketAcceptanceBuilder — Phase 1 PR-3."""
import pytest
from stock_processing_service.domain.services.mainline_discovery.mainline_market_acceptance_builder import (
    MainlineMarketAcceptanceBuilder,
)


class TestMarketAcceptanceBuilder:

    def test_strong_leader_plus_breadth_plus_capital_high_score(self):
        """Leader alive + board breadth + positive capital → high score."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[{"subject_key": "sk_a", "theme_name": "主线A"}],
            event_rows_by_subject={
                "sk_a": [
                    {"event_date": "2026-04-28", "title": "e1"},
                    {"event_date": "2026-04-27", "title": "e2"},
                    {"event_date": "2026-04-25", "title": "e3"},
                    {"event_date": "2026-04-24", "title": "e4"},
                ]
            },
            cycle_evidence_by_subject={
                "sk_a": {"leader_alive_score": 82, "final_mainline_alive": True},
            },
            cycle_judgement_by_subject={
                "sk_a": {"mainline_strength_score": 80, "fade_risk_score": 15},
            },
            capital_by_subject={
                "sk_a": {"main_net_inflow_sum": 5e7, "leader_main_net_inflow": 2e7},
            },
            stock_facts_by_subject={
                "sk_a": [
                    {"leader_composite_score": 80, "pct_chg": 10.0},
                    {"leader_composite_score": 72, "pct_chg": 9.8},
                    {"leader_composite_score": 68, "pct_chg": 5.0},
                ],
            },
        )
        ma = result["sk_a"]
        assert ma.market_acceptance_score is not None
        assert ma.market_acceptance_score >= 65
        assert ma.leader_alive is True
        assert not ma.diagnostics["hard_veto_flags"]

    def test_no_leader_no_trade(self):
        """No leader → leader_alive=False, cannot confirm."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[{"subject_key": "sk_b", "theme_name": "弱题材"}],
            cycle_judgement_by_subject={"sk_b": {"mainline_strength_score": 30}},
            capital_by_subject={"sk_b": {"main_net_inflow_sum": 1e6}},
            stock_facts_by_subject={"sk_b": []},
        )
        ma = result["sk_b"]
        assert ma.leader_alive is False
        assert "leader_not_alive" in ma.diagnostics["hard_veto_flags"]

    def test_fade_risk_high_hard_veto(self):
        """High fade_risk → hard_veto."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[{"subject_key": "sk_c", "theme_name": "退潮题材"}],
            cycle_judgement_by_subject={
                "sk_c": {"mainline_strength_score": 75, "fade_risk_score": 85,
                         "final_mainline_alive": True},
            },
            stock_facts_by_subject={
                "sk_c": [{"leader_composite_score": 70, "pct_chg": 5.0}],
            },
        )
        ma = result["sk_c"]
        assert "fade_risk_high" in ma.diagnostics["hard_veto_flags"]

    def test_capital_negative_downgrade(self):
        """Negative capital → low score, capital_negative flag."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[{"subject_key": "sk_d", "theme_name": "资金流出题"}],
            cycle_judgement_by_subject={
                "sk_d": {"mainline_strength_score": 70, "fade_risk_score": 20,
                         "final_mainline_alive": True},
            },
            capital_by_subject={
                "sk_d": {"main_net_inflow_sum": -1e7, "leader_main_net_inflow": -5e6},
            },
            stock_facts_by_subject={
                "sk_d": [{"leader_composite_score": 65, "pct_chg": 3.0}],
            },
        )
        ma = result["sk_d"]
        assert ma.capital_confirmation_score is not None
        assert ma.capital_confirmation_score <= 30
        assert "capital_negative" in ma.diagnostics["hard_veto_flags"]

    def test_missing_data_conservative(self):
        """Missing data → conservative defaults, no high score."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[{"subject_key": "sk_e", "theme_name": "无数据"}],
        )
        ma = result["sk_e"]
        assert ma.market_acceptance_score is None
        assert ma.leader_alive is False
        assert "cycle_evidence" in ma.diagnostics["missing_fields"]

    def test_single_stock_no_breadth(self):
        """Single strong stock without board breadth → low board_breadth."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[{"subject_key": "sk_f", "theme_name": "孤股"}],
            event_rows_by_subject={
                "sk_f": [{"event_date": "2026-04-28", "title": "e1"}],
            },
            cycle_judgement_by_subject={
                "sk_f": {"mainline_strength_score": 50, "fade_risk_score": 30},
            },
            stock_facts_by_subject={
                "sk_f": [{"leader_composite_score": 75, "pct_chg": 9.9}],
            },
        )
        ma = result["sk_f"]
        assert ma.board_breadth_score is not None
        assert ma.board_breadth_score < 60  # single stock should be low

    def test_heat_persistence_from_event_rows(self):
        """4 days of events → heat_persistence >= 85."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[{"subject_key": "sk_g", "theme_name": "持续热点"}],
            event_rows_by_subject={
                "sk_g": [
                    {"event_date": "2026-04-28", "title": "e1"},
                    {"event_date": "2026-04-27", "title": "e2"},
                    {"event_date": "2026-04-25", "title": "e3"},
                    {"event_date": "2026-04-24", "title": "e4"},
                ]
            },
            cycle_judgement_by_subject={
                "sk_g": {"mainline_strength_score": 50, "fade_risk_score": 20},
            },
            stock_facts_by_subject={
                "sk_g": [{"leader_composite_score": 60}],
            },
        )
        ma = result["sk_g"]
        assert ma.heat_persistence_score == 85.0

    def test_integration_with_fact_context_data(self):
        """Integrated test: feed realistic-looking fact context data through builder."""
        b = MainlineMarketAcceptanceBuilder()
        result = b.build(
            trade_date="2026-04-28",
            candidate_subjects=[
                {"subject_key": "sk_1", "theme_name": "强主线"},
                {"subject_key": "sk_2", "theme_name": "弱轮动"},
            ],
            event_rows_by_subject={
                "sk_1": [
                    {"event_date": f"2026-04-{d}", "title": f"e{d}"}
                    for d in [28, 27, 25, 24]
                ],
                "sk_2": [
                    {"event_date": "2026-04-28", "title": "single"},
                ],
            },
            cycle_judgement_by_subject={
                "sk_1": {"mainline_strength_score": 78, "fade_risk_score": 15,
                         "final_mainline_alive": True},
                "sk_2": {"mainline_strength_score": 35, "fade_risk_score": 40,
                         "final_mainline_alive": False},
            },
            capital_by_subject={
                "sk_1": {"main_net_inflow_sum": 3e7, "leader_main_net_inflow": 1e7},
                "sk_2": {"main_net_inflow_sum": 0, "leader_main_net_inflow": 0},
            },
            stock_facts_by_subject={
                "sk_1": [
                    {"leader_composite_score": 82, "pct_chg": 10.0},
                    {"leader_composite_score": 75, "pct_chg": 9.0},
                    {"leader_composite_score": 70, "pct_chg": 7.0},
                ],
                "sk_2": [{"leader_composite_score": 45, "pct_chg": 2.0}],
            },
        )
        # sk_1 should be strong
        assert result["sk_1"].market_acceptance_score is not None
        assert result["sk_1"].market_acceptance_score >= 65
        assert result["sk_1"].leader_alive is True
        assert not result["sk_1"].diagnostics["hard_veto_flags"]
        # sk_2 should be weak
        assert result["sk_2"].market_acceptance_score is not None
        assert result["sk_2"].market_acceptance_score < 65
        assert result["sk_2"].leader_alive is False

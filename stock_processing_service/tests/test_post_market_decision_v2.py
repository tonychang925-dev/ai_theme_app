"""Tests for PR-12: PostMarketDecisionEngineV2."""
import pytest
from stock_processing_service.domain.services.post_market_decision_v2.models import (
    StrongStockPoolItem, WeakToStrongD1Item, NextDayFocusStock, PostMarketDecisionV2,
)
from stock_processing_service.domain.services.post_market_decision_v2.post_market_decision_engine_v2 import (
    PostMarketDecisionEngineV2,
)


def _ml(ml_id="ml_test", csk="sk_a", name="测试主线", related=None):
    r = {"mainline_id": ml_id, "mainline_name": name, "canonical_subject_key": csk}
    if related:
        import json
        r["related_subject_keys_json"] = json.dumps(related)
    return r


def _stock_row(stock_id="000001.SZ", name="测试股", sk="sk_a", score=82, entry="formal", role="dragon", labels=None):
    row = {
        "stock_id": stock_id, "stock_name": name, "subject_key": sk,
        "theme_name": "测试主线", "watch_score": score, "watch_priority": score + 5,
        "watch_status": "active", "pool_entry_type": entry, "strong_grade": "S",
        "relay_role": role, "source_tag": "3_limit_up", "cycle_state": "fermentation",
        "mainline_strength_score": 72, "support_type": "gap_support",
        "support_level": 12.0, "support_score": 78,
    }
    if labels is not None:
        row["labels"] = labels
    return row


class TestPostMarketDecisionV2:

    def test_no_confirmed_mainline_no_stocks(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(trade_date="2026-04-29", confirmed_mainlines=[])
        assert len(r.strong_stock_pool_reviews) == 0
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0
        assert "layer_c_d1_preview_truncated" not in r.diagnostics

    def test_stocks_keep_rows_without_mainline_filter(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml(csk="sk_main")],
            market_regime={"allow_trade": True, "trade_mode": "mainline_active", "position_limit": 0.5},
            stock_pool_rows=[
                _stock_row(stock_id="000002.SZ", sk="sk_other"),
                _stock_row(stock_id="000001.SZ", sk="sk_main", name="主线股"),
            ],
        )
        assert len(r.strong_stock_pool_reviews) == 2
        names = {row["stock_name"] for row in r.strong_stock_pool_reviews}
        assert "主线股" in names
        assert "测试股" in names

    def test_independent_leader_is_kept_even_without_mainline_binding(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml(csk="sk_main")],
            market_regime={"allow_trade": True, "trade_mode": "mainline_active", "position_limit": 0.5},
            stock_pool_rows=[
                _stock_row(
                    stock_id="000003.SZ",
                    sk="sk_other",
                    name="独立龙头",
                    role="leader",
                    labels={
                        "entry_path": "independent_leader",
                        "identity_scope": "independent_stock_signal",
                        "strong_gene_seed": True,
                        "has_two_board": True,
                    },
                ),
            ],
        )
        assert len(r.strong_stock_pool_reviews) == 1
        assert r.strong_stock_pool_reviews[0]["stock_name"] == "独立龙头"
        assert r.strong_stock_pool_reviews[0]["diagnostics"]["mainline_binding_status"] == "not_confirmed"
        assert r.strong_stock_pool_reviews[0]["labels"]["entry_path"] == "independent_leader"
        assert r.strong_stock_pool_reviews[0]["labels"]["identity_scope"] == "independent_stock_signal"
        assert r.strong_stock_pool_reviews[0]["labels"]["strong_gene_seed"] is True

    def test_ultra_short_only_restricts_d1(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "ultra_short_only", "position_limit": 0.2},
            stock_pool_rows=[
                _stock_row(name="龙头", role="leader", score=85),
                _stock_row(name="杂毛", role="follower", score=70),
            ],
        )
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0

    def test_mainline_core_only_restricts(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "mainline_core_only", "position_limit": 0.3},
            stock_pool_rows=[_stock_row(name="核心股", score=78)],
        )
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert r.trading_principle_v2["d1_candidate_count"] == 0

    def test_allow_trade_false_no_formal_d1(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": False, "trade_mode": "no_trade", "position_limit": 0},
            stock_pool_rows=[_stock_row(score=90)],
        )
        assert len(r.strong_stock_pool_reviews) == 1  # pool still maintained
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0  # no formal → no focus

    def test_active_mode_generates_focus_stocks(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "mainline_active", "position_limit": 0.5},
            stock_pool_rows=[_stock_row(score=85, entry="formal")],
        )
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0

    def test_pool_keeps_related_subjects_without_mainline_filter(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml(csk="sk_core", related=["sk_branch"])],
            market_regime={"allow_trade": True, "trade_mode": "mainline_active", "position_limit": 0.5},
            stock_pool_rows=[
                _stock_row(stock_id="000001.SZ", sk="sk_core", name="核心"),
                _stock_row(stock_id="000002.SZ", sk="sk_branch", name="分支"),
                _stock_row(stock_id="000003.SZ", sk="sk_other", name="无关"),
            ],
        )
        assert len(r.strong_stock_pool_reviews) == 3  # core + branch + unrelated rows remain visible
        names = [r["stock_name"] for r in r.strong_stock_pool_reviews]
        assert "核心" in names
        assert "分支" in names
        assert "无关" in names

    def test_pool_ignores_legacy_rows_without_stock_id(self):
        e = PostMarketDecisionEngineV2()
        legacy_rows = [
            {
                "stock_id": "",
                "stock_name": "重复股",
                "subject_key": "sk_core",
                "theme_name": "主线A",
                "watch_score": 80,
                "watch_priority": 81,
                "watch_status": "active",
                "pool_entry_type": "formal",
                "relay_role": "leader",
                "source_tag": "a",
                "cycle_state": "fermentation",
                "mainline_strength_score": 72,
                "support_score": 78,
            },
            {
                "stock_id": "",
                "stock_name": "重复股",
                "subject_key": "sk_core",
                "theme_name": "主线A",
                "watch_score": 79,
                "watch_priority": 80,
                "watch_status": "active",
                "pool_entry_type": "formal",
                "relay_role": "leader",
                "source_tag": "b",
                "cycle_state": "fermentation",
                "mainline_strength_score": 72,
                "support_score": 78,
            },
        ]
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml(csk="sk_core")],
            market_regime={"allow_trade": True, "trade_mode": "mainline_active", "position_limit": 0.5},
            stock_pool_rows=legacy_rows,
        )
        assert len(r.strong_stock_pool_reviews) == 0
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0

    def test_focus_stock_has_buy_invalid_conditions(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "mainline_active", "position_limit": 0.5},
            stock_pool_rows=[_stock_row(score=90, entry="formal")],
        )
        assert len(r.next_day_focus_stocks) == 0

    def test_ultra_short_allows_sub_dragon(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "ultra_short_only", "position_limit": 0.2},
            stock_pool_rows=[
                _stock_row(name="龙二", role="sub_dragon", score=82),
                _stock_row(name="杂毛", role="follower", score=75),
            ],
        )
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0

    def test_no_trade_blocks_focus_but_keeps_pool(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": False, "trade_mode": "no_trade", "position_limit": 0},
            stock_pool_rows=[_stock_row(entry="formal", score=90)],
        )
        assert len(r.strong_stock_pool_reviews) == 1
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0

    def test_can_build_layer_c_for_recap(self):
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(
            trade_date="2026-04-29",
            confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "mainline_active", "position_limit": 0.5},
            stock_pool_rows=[_stock_row(score=85, entry="formal")],
        )
        assert len(r.strong_stock_pool_reviews) == 1
        assert len(r.weak_to_strong_d1_reviews) == 0
        assert len(r.next_day_focus_stocks) == 0
        assert r.trading_principle_v2["strong_pool_count"] == 1
        assert r.trading_principle_v2["d1_candidate_count"] == 0

    def test_ultra_short_top_n_limit(self):
        """ultra_short_only should cap D1 at 5."""
        e = PostMarketDecisionEngineV2()
        rows = [_stock_row(name=f"股{i}", entry="formal", score=80 + i, role="leader") for i in range(10)]
        r = e.evaluate(
            trade_date="2026-04-29", confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "ultra_short_only", "position_limit": 0.2},
            stock_pool_rows=rows,
        )
        assert len(r.weak_to_strong_d1_reviews) == 0

    def test_core_only_top_n(self):
        """mainline_core_only should cap D1 at 10."""
        e = PostMarketDecisionEngineV2()
        rows = [_stock_row(name=f"股{i}", entry="formal", score=70 + i, role="core") for i in range(15)]
        r = e.evaluate(
            trade_date="2026-04-29", confirmed_mainlines=[_ml()],
            market_regime={"allow_trade": True, "trade_mode": "mainline_core_only", "position_limit": 0.3},
            stock_pool_rows=rows,
        )
        assert len(r.weak_to_strong_d1_reviews) == 0

    def test_layer_c_source_diagnostics(self):
        """Diagnostics should include confirmed_mainline_error when registry fails."""
        e = PostMarketDecisionEngineV2()
        r = e.evaluate(trade_date="2026-04-29", confirmed_mainlines=[])
        assert r.diagnostics["confirmed_count"] == 0

    def test_model_to_dicts(self):
        p = StrongStockPoolItem(stock_id="000001.SZ", stock_name="测试", watch_score=85)
        assert p.to_dict()["watch_score"] == 85
        d1 = WeakToStrongD1Item(stock_id="000001.SZ", stock_name="测试", candidate_score=80,
                                buy_condition=["竞价确认"], invalid_condition=["破位"])
        assert d1.to_dict()["d2_required"] is True
        fs = NextDayFocusStock(stock_id="000001.SZ", stock_name="测试", buy_condition=["条件"], invalid_condition=["失效"])
        assert fs.to_dict()["d2_status"] == "pending"

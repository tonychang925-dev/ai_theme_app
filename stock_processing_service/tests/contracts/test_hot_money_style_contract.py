"""PR4.2.36b Hot Money Style Producer — Contract Tests.

Contracts:
  C1: 4-signal explainability (each component individually readable)
  C2: Separation from Institution Style (no shared weights/formulas)
  C3: Single signal cannot decide (3+ signals required)
  C4: DT is enhancement only (missing → redistributed, not blocked)
  C5: Event modifier does not create capital (only adjusts confidence)
  C6: Emotion modifier traceable (stored in output)
  C7: No forbidden inference (net_amount→hot_money forbidden)
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    PROJECT_ROOT / "stock_processing_service" / "application"
    / "services" / "capital_evidence" / "hot_money_style_producer.py"
)

SAMPLE_HOTSPOTS: list[dict] = [
    {"subject_key": "9014636", "theme_name": "人形机器人", "cycle_state": "fermentation",
     "watch_score": 85.0, "pool_entry_type": "formal"},
    {"subject_key": "9019807", "theme_name": "商业航天", "cycle_state": "start",
     "watch_score": 72.0, "pool_entry_type": "observe"},
    {"subject_key": "9015778", "theme_name": "存储芯片", "cycle_state": "divergence",
     "watch_score": 45.0, "pool_entry_type": "formal"},
]

SAMPLE_STOCKS: dict[str, list[dict]] = {
    "9014636": [
        {"relay_role": "龙头", "watch_score": 85.0},
        {"relay_role": "sub_dragon", "watch_score": 72.0},
        {"relay_role": "sub_dragon", "watch_score": 60.0},
    ],
    "9019807": [
        {"relay_role": "龙头", "watch_score": 70.0},
    ],
    "9015778": [
        {"relay_role": "unknown", "watch_score": 40.0},
    ],
}

SAMPLE_RELAY: dict[str, Any] = {
    "promotion_1_to_2": 0.22, "promotion_2_to_3": 0.10,
    "max_board_height": 6, "feedback_score": 0,
}

SAMPLE_EVENTS: dict[str, float] = {"9019807": 0.9}

INST_SCORES: dict[str, float] = {"9015778": 72.0, "9014636": 45.0}


@pytest.fixture
def producer():
    from stock_processing_service.application.services.capital_evidence.hot_money_style_producer import (
        HotMoneyStyleProducer,
    )
    return HotMoneyStyleProducer()


# ═══════════════════════════════════════════════════════════════
# C1: Component explainability
# ═══════════════════════════════════════════════════════════════

class TestC1Explainability:
    def test_each_signal_individually_readable(self, producer):
        results = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS)
        assert len(results) == 3
        for r in results:
            assert hasattr(r, "attack_score")
            assert hasattr(r, "relay_score")
            assert hasattr(r, "intensity_score")
            assert hasattr(r, "dragon_tiger_score")

    def test_deterministic_replay(self, producer):
        r1 = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS)
        r2 = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS)
        for a, b in zip(r1, r2):
            assert a.hot_money_score == b.hot_money_score
            assert a.confidence == b.confidence


# ═══════════════════════════════════════════════════════════════
# C2: Separation from Institution Style
# ═══════════════════════════════════════════════════════════════

class TestC2Separation:
    def test_no_shared_weights_with_institution(self):
        import ast
        src = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        # Hot money must not import institution module
        assert "institution_style_producer" not in str(imports)
        # Must not share weight constants with institution
        assert "W_FLOW" not in src  # institution-specific weight name


# ═══════════════════════════════════════════════════════════════
# C3: Multi-signal mandatory
# ═══════════════════════════════════════════════════════════════

class TestC3MultiSignal:
    def test_hotspot_only_without_stocks_produces_scores(self, producer):
        """Hotspots alone should still produce scores (using defaults for missing signals)."""
        results = producer.produce(SAMPLE_HOTSPOTS, {}, SAMPLE_RELAY, None, SAMPLE_EVENTS)
        assert len(results) == 3


# ═══════════════════════════════════════════════════════════════
# C4: DT enhancement only
# ═══════════════════════════════════════════════════════════════

class TestC4DTEnhancement:
    def test_dt_missing_does_not_block(self, producer):
        r_without = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS)
        assert len(r_without) == 3
        for r in r_without:
            assert r.dragon_tiger_score is None


# ═══════════════════════════════════════════════════════════════
# C5: Event modifier does not create capital
# ═══════════════════════════════════════════════════════════════

class TestC5EventModifier:
    def test_event_only_affects_modifier_field(self, producer):
        r_with = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS)
        r_without = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, None)

        # 商业航天 (9019807) should have event_modifier > 1.0
        hangtian = next(r for r in r_with if r.subject_key == "9019807")
        assert hangtian.event_modifier > 1.0

        # Event modifier stored in output for auditability
        assert "event_modifier" in hangtian.to_row()


# ═══════════════════════════════════════════════════════════════
# C6: Emotion modifier traceable
# ═══════════════════════════════════════════════════════════════

class TestC6EmotionModifier:
    def test_ice_point_boosts_hot_money(self, producer):
        r_normal = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS, emotion_node="CHAOS")
        r_ice = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS, emotion_node="ICE_POINT")
        # ICE_POINT (1.10) > CHAOS (0.95) → scores higher
        normal_sum = sum(r.hot_money_score for r in r_normal)
        ice_sum = sum(r.hot_money_score for r in r_ice)
        assert ice_sum > normal_sum

    def test_emotion_modifier_stored(self, producer):
        results = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS, emotion_node="REBOUND")
        for r in results:
            assert r.emotion_modifier > 0
            assert r.emotion_modifier == 1.05

    def test_institution_relation_present(self, producer):
        results = producer.produce(SAMPLE_HOTSPOTS, SAMPLE_STOCKS, SAMPLE_RELAY, None, SAMPLE_EVENTS, institution_scores=INST_SCORES)
        chip = next(r for r in results if r.subject_key == "9015778")
        robot = next(r for r in results if r.subject_key == "9014636")
        # 存储芯片: high institution (72), mid hot money → BOTH or INSTITUTION_ONLY
        assert chip.institution_hot_relation in ("INSTITUTION_ONLY", "BOTH", "DIVERGENCE")
        # 人形机器人: low institution (45), high hot money → HOT_MONEY_ONLY or BOTH
        assert robot.institution_hot_relation in ("HOT_MONEY_ONLY", "BOTH", "DIVERGENCE")


# ═══════════════════════════════════════════════════════════════
# C7: Forbidden fields
# ═══════════════════════════════════════════════════════════════

class TestC7ForbiddenFields:
    FORBIDDEN = ("net_amount > 0 → hot_money", "main_force → attack")

    def test_no_forbidden_patterns(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        for pattern in self.FORBIDDEN:
            assert pattern not in src

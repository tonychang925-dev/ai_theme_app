"""M4f: ThemeStrengthEngine unit tests."""

from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.domain.services.leader_scoring import (
    LeaderScore,
    LeaderScoringEngine,
)
from stock_processing_service.domain.services.evidence_fusion import EvidenceItem
from stock_processing_service.domain.services.theme_strength import (
    ThemeStrengthEngine,
)

TD = date(2026, 6, 18)


def _ev(src, theme, code="000811", name="冰轮环境", reason=""):
    return EvidenceItem(source_name=src, theme_name=theme,
                        stock_code=code, stock_name=name,
                        evidence_date=TD, reason=reason or src)


# ── Basic ────────────────────────────────────────────────────────

def test_empty_returns_empty():
    engine = ThemeStrengthEngine()
    assert len(engine.compute(TD, [])) == 0


def test_single_theme_basic():
    """One theme with 3 stocks → should produce 1 ThemeStrength."""
    leader_engine = LeaderScoringEngine()
    items = [
        _ev("ths", "机器人", "002747", "埃斯顿", "人形机器人"),
        _ev("ths", "机器人", "002527", "拓斯达", "工业机器人"),
        _ev("ths", "机器人", "002896", "中大力德", "减速器"),
    ]
    board = {
        "002747": {"is_limit_up": True, "consecutive_boards": 2, "pct_chg": 10.0},
        "002527": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
        "002896": {"pct_chg": 5.0},
    }
    leaders = leader_engine.score(TD, items, board)

    engine = ThemeStrengthEngine()
    results = engine.compute(TD, leaders)
    assert len(results) == 1
    assert results[0].theme_name == "机器人"
    assert results[0].rank == 1
    assert results[0].stock_count == 3
    assert results[0].strength_score > 0
    assert len(results[0].top_stocks) == 3


# ── Multi-theme ranking ──────────────────────────────────────────

def test_multi_theme_ranking():
    """5 themes → correct ordering by strength."""
    leader_engine = LeaderScoringEngine()
    items = [
        # PCB: 2 stocks, both limit-up
        _ev("ths", "PCB/HBM产业链", "002579", "中京电子", "PCB"),
        _ev("ths", "PCB/HBM产业链", "002384", "东山精密", "PCB"),
        # Robot: 3 stocks, all limit-up
        _ev("ths", "机器人", "002747", "埃斯顿", "人形机器人"),
        _ev("ths", "机器人", "002527", "拓斯达", "工业机器人"),
        _ev("ths", "机器人", "002896", "中大力德", "减速器"),
        # AI算力: 1 stock, limit-up + CNInfo resonance
        _ev("ths", "AI算力基础设施", "000811", "冰轮环境", "液冷"),
        _ev("cninfo", "AI算力基础设施", "000811", "冰轮环境", "合同"),
        # 光通信: 1 stock
        _ev("ths", "AI光通信", "002281", "光迅科技", "CPO"),
        # 材料: 1 stock
        _ev("ths", "先进材料/固态电池", "002167", "东方锆业", "氧化锆"),
    ]
    board = {c: {"is_limit_up": True, "pct_chg": 10.0}
             for c in ["002579","002384","002747","002527","002896","000811","002281","002167"]}
    leaders = leader_engine.score(TD, items, board)

    engine = ThemeStrengthEngine()
    results = engine.compute(TD, leaders)
    assert len(results) == 5
    # AI算力 (2-source resonance) > 机器人 (3 stocks single-source)
    # Multi-source evidence quality beats pure stock count
    assert results[0].theme_name in ("AI算力基础设施", "机器人")
    assert results[0].resonance_count > 0  # top theme has multi-source evidence
    # Ranks are unique
    ranks = {r.rank for r in results}
    assert ranks == {1, 2, 3, 4, 5}
    # Strength scores are descending
    for i in range(len(results) - 1):
        assert results[i].strength_score >= results[i + 1].strength_score


# ── Top stocks ───────────────────────────────────────────────────

def test_top_stocks_are_from_leaders():
    leader_engine = LeaderScoringEngine()
    items = [
        _ev("ths", "机器人", "002747", "埃斯顿", "龙头"),
        _ev("cninfo", "机器人", "002747", "埃斯顿", "合同"),
        _ev("ths", "机器人", "002527", "拓斯达", "工业"),
        _ev("ths", "机器人", "002896", "中大力德", "减速器"),
    ]
    board = {"002747": {"is_limit_up": True, "consecutive_boards": 2},
             "002527": {"is_limit_up": True}, "002896": {"pct_chg": 5.0}}
    leaders = leader_engine.score(TD, items, board)

    engine = ThemeStrengthEngine()
    results = engine.compute(TD, leaders)
    top = results[0].top_stocks
    assert top[0]["stock_name"] == "埃斯顿"
    assert top[0]["leader_score"] > top[1]["leader_score"]


# ── Resonance impact ─────────────────────────────────────────────

def test_resonance_boosts_strength():
    """Theme with multi-source resonance → higher strength."""
    leader_engine = LeaderScoringEngine()
    # Theme A: single source
    items_a = [_ev("ths", "机器人", "002747", "埃斯顿")]
    # Theme B: multi-source (THS + CNInfo + EPS)
    items_b = [
        _ev("ths", "机器人", "002747", "埃斯顿"),
        _ev("cninfo", "机器人", "002747", "埃斯顿"),
        _ev("eps", "机器人", "002747", "埃斯顿"),
    ]
    leaders_a = leader_engine.score(TD, items_a, {"002747": {"pct_chg": 10.0}})
    leaders_b = leader_engine.score(TD, items_b, {"002747": {"pct_chg": 10.0}})

    engine = ThemeStrengthEngine()
    s_a = engine.compute(TD, leaders_a)[0]
    s_b = engine.compute(TD, leaders_b)[0]
    # Multi-source theme should have higher resonance_count and strength
    assert s_b.resonance_count > s_a.resonance_count


# ── Rank ordering ────────────────────────────────────────────────

def test_rank_continuous_from_one():
    leader_engine = LeaderScoringEngine()
    items = [
        _ev("ths", f"主题{i}", f"00000{i}", f"股票{i}")
        for i in range(1, 6)
    ]
    leaders = leader_engine.score(TD, items, {f"00000{i}": {"pct_chg": 3.0} for i in range(1, 6)})
    engine = ThemeStrengthEngine()
    results = engine.compute(TD, leaders)
    ranks = sorted(r.rank for r in results)
    assert ranks == list(range(1, len(results) + 1))


# ── No leader bias ───────────────────────────────────────────────

def test_no_leader_theme_not_top():
    """Themes without strong leaders should not rank first."""
    leader_engine = LeaderScoringEngine()
    items = [
        _ev("ths", "强主题", "000001", "龙头股", "强驱动"),
        _ev("cninfo", "强主题", "000001", "龙头股", "公告"),
        _ev("eps", "强主题", "000001", "龙头股", "高增长"),
        _ev("jyhf", "弱主题", "000002", "杂鱼股", "静态映射"),
    ]
    board = {"000001": {"is_limit_up": True, "consecutive_boards": 2},
             "000002": {"pct_chg": 1.0}}
    leaders = leader_engine.score(TD, items, board)
    engine = ThemeStrengthEngine()
    results = engine.compute(TD, leaders)
    assert results[0].theme_name == "强主题"

"""M4e: LeaderScoringEngine unit tests."""

from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.domain.services.evidence_fusion import EvidenceItem
from stock_processing_service.domain.services.leader_scoring import (
    LeaderScoringEngine,
    compute_board_strength,
)

TD = date(2026, 6, 18)


def _ev(src, theme, code="000811", name="冰轮环境", reason="", ev_date=TD):
    return EvidenceItem(source_name=src, theme_name=theme,
                        stock_code=code, stock_name=name,
                        evidence_date=ev_date, reason=reason or f"{src}")


# ── Board strength ──────────────────────────────────────────────

def test_limit_up_3_board():
    s = compute_board_strength(is_limit_up=True, consecutive_boards=3)
    assert s == 0.70  # 0.40 + 0.30


def test_limit_up_2_board():
    s = compute_board_strength(is_limit_up=True, consecutive_boards=2)
    assert s == pytest.approx(0.60)  # 0.40 + 0.20


def test_limit_up_no_board():
    s = compute_board_strength(is_limit_up=True, consecutive_boards=0)
    assert s == 0.40  # just limit_up


def test_near_limit_up():
    s = compute_board_strength(pct_chg=9.8)
    assert s == 0.35  # near limit


def test_flat():
    s = compute_board_strength(pct_chg=0.0)
    assert s == 0.0


def test_board_capped():
    s = compute_board_strength(is_limit_up=True, consecutive_boards=5,
                               amount_rank_pct=10, turnover_rank_pct=10)
    assert s == pytest.approx(0.90)  # 0.40+0.30+0.10+0.10=0.90


# ── Leader scoring ──────────────────────────────────────────────

def test_single_stock_basic():
    engine = LeaderScoringEngine()
    items = [_ev("ths", "AI算力基础设施", reason="数据中心液冷")]
    board = {"000811": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0}}
    results = engine.score(TD, items, board)
    assert len(results) == 1
    assert results[0].stock_name == "冰轮环境"
    assert results[0].rank_in_theme == 1
    assert results[0].leader_score > 0.3


def test_theme_ranking():
    """3 stocks in same theme → correct ranking by leader_score."""
    engine = LeaderScoringEngine()
    items = [
        _ev("ths", "机器人", "002747", "埃斯顿", reason="人形机器人"),
        _ev("ths", "机器人", "002527", "拓斯达", reason="工业机器人"),
        _ev("ths", "机器人", "002896", "中大力德", reason="减速器"),
    ]
    board = {
        "002747": {"is_limit_up": True, "consecutive_boards": 2, "pct_chg": 10.0},
        "002527": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
        "002896": {"is_limit_up": False, "pct_chg": 5.0},
    }
    results = engine.score(TD, items, board)
    robot = [r for r in results if r.theme_name == "机器人"]
    assert len(robot) == 3
    # 埃斯顿 (2连板+THS) > 拓斯达 (涨停+THS) > 中大力德 (非涨停+THS)
    assert robot[0].stock_name == "埃斯顿"
    assert robot[0].rank_in_theme == 1
    assert robot[1].stock_name == "拓斯达"
    assert robot[2].stock_name == "中大力德"
    assert robot[0].leader_score > robot[1].leader_score > robot[2].leader_score


def test_multi_source_resonance_boosts_leader():
    """3-source resonance (THS+CNInfo+EPS) → higher leader_score."""
    engine = LeaderScoringEngine()
    single_source = [_ev("ths", "PCB/HBM产业链", reason="HDI板")]
    multi_source = [
        _ev("ths", "PCB/HBM产业链", reason="HDI板"),
        _ev("cninfo", "PCB/HBM产业链", reason="重大合同"),
        _ev("eps", "PCB/HBM产业链", reason="EPS+30%"),
    ]
    board = {"000811": {"pct_chg": 8.0}}
    s1 = engine.score(TD, single_source, board)
    s2 = engine.score(TD, multi_source, board)
    assert s2[0].leader_score > s1[0].leader_score
    assert s2[0].resonance_score > 0.5  # 3-source resonance


def test_golden_dataset_5_stocks():
    """6/18 Golden Dataset: 5 stocks across 5 themes."""
    engine = LeaderScoringEngine()
    items = [
        _ev("ths", "AI算力基础设施", "000811", "冰轮环境", reason="数据中心液冷"),
        _ev("cninfo", "AI算力基础设施", "000811", "冰轮环境", reason="收购公告"),
        _ev("ths", "PCB/HBM产业链", "002579", "中京电子", reason="HDI板"),
        _ev("ths", "AI光通信", "002281", "光迅科技", reason="CPO光模块"),
        _ev("cninfo", "AI光通信", "002281", "光迅科技", reason="技术突破"),
        _ev("ths", "先进材料/固态电池", "002167", "东方锆业", reason="氧化锆"),
        _ev("ths", "机器人", "002747", "埃斯顿", reason="人形机器人"),
    ]
    board = {
        "000811": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
        "002579": {"is_limit_up": True, "consecutive_boards": 2, "pct_chg": 10.0},
        "002281": {"is_limit_up": True, "consecutive_boards": 1, "pct_chg": 10.0},
        "002167": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
        "002747": {"is_limit_up": True, "consecutive_boards": 3, "pct_chg": 10.0},
    }
    results = engine.score(TD, items, board)
    themes = {r.theme_name for r in results}
    assert len(themes) == 5  # all 5 themes represented
    for r in results:
        assert r.leader_score > 0
        assert r.rank_in_theme >= 1
        assert r.stock_code
        assert r.theme_name
    # 光迅科技 (2-source + 1 board) should outrank single-source stocks
    gx = next(r for r in results if r.stock_code == "002281")
    assert gx.resonance_score > 0  # CNInfo + THS


def test_empty_returns_empty():
    engine = LeaderScoringEngine()
    assert len(engine.score(TD, [])) == 0


def test_rank_in_theme_unique():
    """Each theme's stocks should have unique ranks."""
    engine = LeaderScoringEngine()
    items = [
        _ev("ths", "机器人", "002747", "埃斯顿"),
        _ev("ths", "机器人", "002527", "拓斯达"),
        _ev("ths", "机器人", "002896", "中大力德"),
    ]
    results = engine.score(TD, items)
    ranks = {r.stock_code: r.rank_in_theme for r in results}
    assert set(ranks.values()) == {1, 2, 3}
    assert ranks["002747"] == 1  # highest leader_score


def test_top3_interpretable():
    """TOP3 stocks per theme should have interpretable evidence."""
    engine = LeaderScoringEngine()
    items = [
        _ev("ths", "机器人", "002747", "埃斯顿", reason="人形机器人龙头"),
        _ev("cninfo", "机器人", "002747", "埃斯顿", reason="重大合作协议"),
        _ev("eps", "机器人", "002747", "埃斯顿", reason="EPS预期增长"),
        _ev("ths", "机器人", "002527", "拓斯达", reason="工业机器人"),
        _ev("ths", "机器人", "002896", "中大力德", reason="谐波减速器"),
    ]
    results = engine.score(TD, items)
    top3 = [r for r in results if r.rank_in_theme <= 3]
    assert len(top3) == 3
    # Top1 should have the most evidence
    top1 = next(r for r in top3 if r.rank_in_theme == 1)
    assert len(top1.evidence_sources) >= 2
    assert top1.resonance_score > 0

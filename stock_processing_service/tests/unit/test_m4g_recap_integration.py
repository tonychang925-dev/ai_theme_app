"""M4g: End-to-end recap integration test using 6/18 Golden Dataset."""

from __future__ import annotations

import json
from datetime import date

import pytest

from stock_processing_service.domain.services.evidence_fusion import (
    EvidenceFusionEngine,
    EvidenceItem,
)
from stock_processing_service.domain.services.leader_scoring import LeaderScoringEngine
from stock_processing_service.domain.services.theme_strength import ThemeStrengthEngine
from stock_processing_service.domain.services.recap_aggregation import (
    RecapAggregationService,
)

TD = date(2026, 6, 18)


# ── 6/18 Golden Dataset ─────────────────────────────────────────

GOLDEN_EVIDENCE = [
    # AI算力基础设施
    EvidenceItem("ths", "AI算力基础设施", "000811", "冰轮环境", TD, "数据中心液冷"),
    EvidenceItem("cninfo", "AI算力基础设施", "000811", "冰轮环境", TD, "收购公告"),
    # PCB/HBM产业链
    EvidenceItem("ths", "PCB/HBM产业链", "002579", "中京电子", TD, "HDI板+PCB"),
    EvidenceItem("ths", "PCB/HBM产业链", "002384", "东山精密", TD, "PCB印制电路板"),
    EvidenceItem("eastmoney", "PCB/HBM产业链", "002579", "中京电子", TD, "PCB概念"),
    # 机器人
    EvidenceItem("ths", "机器人", "002747", "埃斯顿", TD, "人形机器人"),
    EvidenceItem("ths", "机器人", "002527", "拓斯达", TD, "工业机器人"),
    EvidenceItem("ths", "机器人", "002896", "中大力德", TD, "谐波减速器"),
    EvidenceItem("cninfo", "机器人", "002747", "埃斯顿", TD, "合作协议"),
    # AI光通信
    EvidenceItem("ths", "AI光通信", "002281", "光迅科技", TD, "CPO光模块"),
    EvidenceItem("cninfo", "AI光通信", "002281", "光迅科技", TD, "技术突破"),
    # 先进材料/固态电池
    EvidenceItem("ths", "先进材料/固态电池", "002167", "东方锆业", TD, "氧化锆"),
    EvidenceItem("ths", "先进材料/固态电池", "002460", "赣锋锂业", TD, "固态电池"),
    # 有色资源
    EvidenceItem("ths", "有色资源/小金属", "000960", "锡业股份", TD, "锡价上涨"),
    # 创新药
    EvidenceItem("ths", "创新药/医疗", "300725", "药石科技", TD, "新药获批"),
]

GOLDEN_BOARD = {
    "000811": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
    "002579": {"is_limit_up": True, "consecutive_boards": 2, "pct_chg": 10.0},
    "002384": {"is_limit_up": True, "consecutive_boards": 1, "pct_chg": 10.0},
    "002747": {"is_limit_up": True, "consecutive_boards": 3, "pct_chg": 10.0},
    "002527": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
    "002896": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
    "002281": {"is_limit_up": True, "consecutive_boards": 1, "pct_chg": 10.0},
    "002167": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
    "002460": {"is_limit_up": False, "pct_chg": 7.0},
    "000960": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
    "300725": {"is_limit_up": True, "consecutive_boards": 0, "pct_chg": 10.0},
}


# ── Full pipeline test ───────────────────────────────────────────

def test_full_pipeline_golden():
    """Evidence → Fusion → Leader → Theme → Recap."""
    fusion = EvidenceFusionEngine()
    leader_engine = LeaderScoringEngine(fusion)
    theme_engine = ThemeStrengthEngine()
    recap_service = RecapAggregationService()

    leaders = leader_engine.score(TD, GOLDEN_EVIDENCE, GOLDEN_BOARD)
    themes = theme_engine.compute(TD, leaders)
    recap = recap_service.aggregate(TD, themes, leaders, top_n=8)

    # Assertions
    assert len(themes) >= 5, f"expected >=5 themes, got {len(themes)}"
    assert len(leaders) >= 8, f"expected >=8 leaders, got {len(leaders)}"
    assert len(recap.top_themes) > 0
    assert recap.market_summary["theme_count"] >= 5

    # Top themes have valid structure
    for tt in recap.top_themes[:5]:
        assert tt["theme_name"]
        assert tt["strength_score"] > 0
        assert tt["rank"] >= 1
        assert len(tt["leaders"]) >= 1
        for ld in tt["leaders"]:
            assert ld["stock_code"]
            assert ld["leader_score"] > 0

    # Market summary
    assert recap.market_summary["top_theme"]


def test_recap_json_serializable():
    """Recap output must be JSON-serializable."""
    fusion = EvidenceFusionEngine()
    leader_engine = LeaderScoringEngine(fusion)
    theme_engine = ThemeStrengthEngine()
    recap_service = RecapAggregationService()

    leaders = leader_engine.score(TD, GOLDEN_EVIDENCE, GOLDEN_BOARD)
    themes = theme_engine.compute(TD, leaders)
    recap = recap_service.aggregate(TD, themes, leaders)

    row = recap_service.to_snapshot_row(recap)
    # recap_json is a string (json.dumps output)
    recap_data = row["recap_json"]
    if isinstance(recap_data, str):
        recap_data = json.loads(recap_data)
    assert recap_data["trade_date"] == "2026-06-18"
    assert len(recap_data["top_themes"]) > 0


def test_theme_rank_ordering():
    """Top theme should have highest strength_score."""
    fusion = EvidenceFusionEngine()
    leader_engine = LeaderScoringEngine(fusion)
    theme_engine = ThemeStrengthEngine()
    recap_service = RecapAggregationService()

    leaders = leader_engine.score(TD, GOLDEN_EVIDENCE, GOLDEN_BOARD)
    themes = theme_engine.compute(TD, leaders)

    for i in range(len(themes) - 1):
        assert themes[i].strength_score >= themes[i + 1].strength_score
        assert themes[i].rank < themes[i + 1].rank


def test_multi_source_themes_rank_higher():
    """Themes with multi-source evidence should rank above single-source."""
    fusion = EvidenceFusionEngine()
    leader_engine = LeaderScoringEngine(fusion)
    theme_engine = ThemeStrengthEngine()

    # Theme A: 1 stock, 2 sources
    items_a = [
        EvidenceItem("ths", "多源主题", "000001", "测试A", TD, "test"),
        EvidenceItem("cninfo", "多源主题", "000001", "测试A", TD, "test"),
    ]
    # Theme B: 2 stocks, 1 source each
    items_b = [
        EvidenceItem("ths", "单源主题", "000002", "测试B1", TD, "test"),
        EvidenceItem("ths", "单源主题", "000003", "测试B2", TD, "test"),
    ]
    board = {c: {"pct_chg": 10.0} for c in ["000001","000002","000003"]}

    leaders_a = leader_engine.score(TD, items_a, board)
    leaders_b = leader_engine.score(TD, items_b, board)
    all_leaders = leaders_a + leaders_b

    themes = theme_engine.compute(TD, all_leaders)
    multi = next(t for t in themes if t.theme_name == "多源主题")
    single = next(t for t in themes if t.theme_name == "单源主题")
    # Multi-source should have higher avg_leader_score
    assert multi.avg_leader_score > single.avg_leader_score


# ── DB integration ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_insert_and_read():
    """Insert recap into market_recap_snapshot and read back."""
    import asyncpg

    fusion = EvidenceFusionEngine()
    leader_engine = LeaderScoringEngine(fusion)
    theme_engine = ThemeStrengthEngine()
    recap_service = RecapAggregationService()

    leaders = leader_engine.score(TD, GOLDEN_EVIDENCE, GOLDEN_BOARD)
    themes = theme_engine.compute(TD, leaders)
    recap = recap_service.aggregate(TD, themes, leaders)
    row = recap_service.to_snapshot_row(recap)

    conn = await asyncpg.connect(
        host="localhost", port=5432, database="stock_data_test",
        user="postgres", password="postgres", timeout=5,
    )
    try:
        recap_json_str = json.dumps(row["recap_json"], ensure_ascii=False, default=str)
        await conn.execute(
            """INSERT INTO market_recap_snapshot (trade_date, recap_json, source_trace_id)
               VALUES ($1, $2::jsonb, $3)
               ON CONFLICT (trade_date) DO UPDATE SET
                 recap_json = EXCLUDED.recap_json,
                 source_trace_id = EXCLUDED.source_trace_id""",
            row["trade_date"], recap_json_str, row["source_trace_id"],
        )

        # Read back
        read = await conn.fetchrow(
            "SELECT recap_json FROM market_recap_snapshot WHERE trade_date = $1",
            row["trade_date"],
        )
        assert read is not None
        data = read["recap_json"] if isinstance(read["recap_json"], dict) else json.loads(read["recap_json"])
        assert data["trade_date"] == "2026-06-18"
        assert len(data["top_themes"]) > 0
    finally:
        await conn.close()

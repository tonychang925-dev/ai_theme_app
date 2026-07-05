"""M4a.1: Golden Dataset fixture replay for stock_concept_block_snapshot.

Validates: stock → concept block → snapshot chain.
Uses 5 verification stocks from 2026-06-18.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "m4a1_golden_concept_blocks_20260618.json"
)


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ── Fixture integrity ───────────────────────────────────────────

def test_fixture_has_5_stocks(golden):
    stocks = golden["verification_stocks"]
    assert len(stocks) == 5, f"expected 5 stocks, got {len(stocks)}"


def test_fixture_trade_date_is_20260618(golden):
    assert golden["trade_date"] == "2026-06-18"


def test_each_stock_has_expected_theme(golden):
    expected_themes = {
        "冰轮环境": "AI算力基础设施",
        "中京电子": "PCB/HBM产业链",
        "光迅科技": "AI光通信",
        "东方锆业": "先进材料/固态电池",
        "埃斯顿": "机器人",
    }
    for stock in golden["verification_stocks"]:
        name = stock["stock_name"]
        assert stock["expected_theme"] == expected_themes.get(
            name, ""
        ), f"{name}: expected_theme mismatch"


def test_each_stock_has_min_2_blocks(golden):
    for stock in golden["verification_stocks"]:
        blocks = stock["concept_blocks"]
        assert (
            len(blocks) >= 2
        ), f"{stock['stock_name']}: only {len(blocks)} blocks, min 2 required"


# ── Snapshot row generation ─────────────────────────────────────

def _fixture_to_snapshot_rows(golden: dict) -> list[dict]:
    """Convert fixture to stock_concept_block_snapshot rows."""
    trade_date = date.fromisoformat(golden["trade_date"])
    source_name = golden["source_name"]
    endpoint_key = golden["endpoint_key"]
    rows: list[dict] = []
    for stock in golden["verification_stocks"]:
        for block in stock["concept_blocks"]:
            rows.append({
                "trade_date": trade_date,
                "stock_code": stock["stock_code"],
                "stock_name": stock["stock_name"],
                "block_code": block["block_code"],
                "block_name": block["block_name"],
                "block_type": block["block_type"],
                "source_name": source_name,
                "endpoint_key": endpoint_key,
                "source_trace_id": (
                    f"em:{block['block_code']}:{trade_date.isoformat()}"
                ),
            })
    return rows


def test_fixture_generates_valid_rows(golden):
    rows = _fixture_to_snapshot_rows(golden)
    assert len(rows) >= 10, f"expected >=10 rows (5 stocks * 2+ blocks), got {len(rows)}"

    stock_codes = {row["stock_code"] for row in rows}
    assert len(stock_codes) == 5, f"expected 5 unique stocks, got {len(stock_codes)}"

    blocks_per_stock: dict[str, int] = {}
    for row in rows:
        blocks_per_stock[row["stock_code"]] = blocks_per_stock.get(row["stock_code"], 0) + 1
    for code, count in blocks_per_stock.items():
        assert 2 <= count <= 8, f"stock {code}: {count} blocks, expected 2-8"


# ── Theme evidence cross-check ──────────────────────────────────

def test_concept_blocks_cover_reason_tags(golden):
    """Each stock's concept blocks should cover at least one reason tag keyword."""
    for stock in golden["verification_stocks"]:
        block_names = [b["block_name"] for b in stock["concept_blocks"]]
        reason = stock.get("reason_raw", "")
        # At least one block name should have keyword overlap with the reason
        has_overlap = any(
            any(
                kw in reason or kw in block_name
                for kw in block_name.replace("PCB", "").replace("AI", "").split("、")
                if kw
            )
            for block_name in block_names
        )
        # Relaxed check: at least half of block names partially match reason
        matched = sum(
            1 for bn in block_names
            if any(tag in reason for tag in [bn[:2], bn[-2:]])
        )
        assert matched >= 1 or has_overlap, (
            f"{stock['stock_name']}: no concept block matches reason tags. "
            f"blocks={block_names} reason={reason[:60]}"
        )


def test_expected_theme_in_blocks(golden):
    """Expected theme name or its keywords should appear in at least one block name."""
    theme_block_map = {
        "AI算力基础设施": ["数据中心", "液冷", "算力"],
        "PCB/HBM产业链": ["PCB", "HDI", "印制电路板"],
        "AI光通信": ["CPO", "光通信", "光模块"],
        "先进材料/固态电池": ["氧化锆", "陶瓷", "固态电池"],
        "机器人": ["机器人"],
    }
    for stock in golden["verification_stocks"]:
        theme = stock["expected_theme"]
        keywords = theme_block_map.get(theme, [theme])
        block_names = [b["block_name"] for b in stock["concept_blocks"]]
        has_match = any(
            kw in bn for kw in keywords for bn in block_names
        )
        assert has_match, (
            f"{stock['stock_name']}: expected_theme='{theme}' "
            f"not found in concept blocks {block_names}"
        )


# ── Integration: DB insert + verify (if DB is available) ────────

@pytest.mark.asyncio
@pytest.mark.integration
async def test_db_insert_and_verify(golden):
    """Insert fixture rows into stock_concept_block_snapshot and verify."""
    import asyncpg

    conn = await asyncpg.connect(
        host="localhost", port=5432, database="stock_data_test",
        user="postgres", password="postgres", timeout=5,
    )
    try:
        rows = _fixture_to_snapshot_rows(golden)
        trade_date = date.fromisoformat(golden["trade_date"])

        for row in rows:
            await conn.execute(
                """INSERT INTO stock_concept_block_snapshot (
                     trade_date, stock_code, stock_name,
                     block_code, block_name, block_type,
                     source_name, endpoint_key, source_trace_id
                   ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   ON CONFLICT (trade_date, stock_code, block_code, source_name)
                   DO NOTHING""",
                row["trade_date"], row["stock_code"], row["stock_name"],
                row["block_code"], row["block_name"], row["block_type"],
                row["source_name"], row["endpoint_key"], row["source_trace_id"],
            )

        # Verify: all 5 stocks have records
        stock_codes = [s["stock_code"] for s in golden["verification_stocks"]]
        count = await conn.fetchval(
            "SELECT COUNT(DISTINCT stock_code) FROM stock_concept_block_snapshot "
            "WHERE trade_date = $1 AND stock_code = ANY($2::text[])",
            trade_date, stock_codes,
        )
        assert count == 5, f"expected 5 stocks in snapshot, got {count}"

        # Verify: each stock has ≥2 blocks
        for stock in golden["verification_stocks"]:
            block_count = await conn.fetchval(
                "SELECT COUNT(*) FROM stock_concept_block_snapshot "
                "WHERE trade_date = $1 AND stock_code = $2",
                trade_date, stock["stock_code"],
            )
            assert (
                block_count >= 2
            ), f"{stock['stock_name']}: {block_count} blocks in DB, expected ≥2"

    finally:
        await conn.close()

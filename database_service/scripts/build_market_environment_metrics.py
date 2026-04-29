#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta
from dataclasses import replace
from statistics import median
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import ConnectionPoolConfig, DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.models import MarketEnvironmentMetrics
from stock_service.services.market_environment_intraday_service import MarketEnvironmentIntradayService


def get_postgres_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5,
        connection_pool=ConnectionPoolConfig(
            min_size=1,
            max_size=5,
            command_timeout=180,
        ),
    )


def parse_args():
    parser = argparse.ArgumentParser(description="构建 market_environment_metrics")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--intraday-json", default="", help="可选分钟级序列 JSON 文件")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _safe_div(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _load_intraday_map(path: str) -> dict[str, list[dict]]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    result: dict[str, list[dict]] = {}
    for item in payload.get("items", []):
        stock_id = str(item.get("stock_id") or "").strip().upper()
        if not stock_id:
            continue
        result[stock_id.split(".", 1)[0]] = list(item.get("points") or [])
    return result


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS market_environment_metrics (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL UNIQUE,
        up_count INTEGER NOT NULL DEFAULT 0,
        down_count INTEGER NOT NULL DEFAULT 0,
        flat_count INTEGER NOT NULL DEFAULT 0,
        advance_decline_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        limit_up_count INTEGER NOT NULL DEFAULT 0,
        limit_down_count INTEGER NOT NULL DEFAULT 0,
        limit_up_down_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        yesterday_limit_up_open_strength NUMERIC(10,4) NOT NULL DEFAULT 0,
        yesterday_limit_up_open_red_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        yesterday_limit_up_premium_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        yesterday_limit_up_fade_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        yesterday_limit_up_fail_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        morning_high_then_fall_count INTEGER NOT NULL DEFAULT 0,
        morning_high_then_fall_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        intraday_fade_count INTEGER NOT NULL DEFAULT 0,
        intraday_fade_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        open_close_pullback_count INTEGER NOT NULL DEFAULT 0,
        open_close_pullback_ratio NUMERIC(10,4) NOT NULL DEFAULT 0,
        high_mark_strong_count INTEGER NOT NULL DEFAULT 0,
        high_mark_weak_count INTEGER NOT NULL DEFAULT 0,
        market_total_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        market_volume_change_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
        market_avg_open_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
        market_avg_close_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
        shanghai_index_pct_chg NUMERIC(10,4) NOT NULL DEFAULT 0,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.market_environment_metrics',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_market_environment_metrics_trade_date
      ON market_environment_metrics(trade_date DESC);
    ALTER TABLE market_environment_metrics
      ADD COLUMN IF NOT EXISTS open_close_pullback_count INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE market_environment_metrics
      ADD COLUMN IF NOT EXISTS open_close_pullback_ratio NUMERIC(10,4) NOT NULL DEFAULT 0;
    ALTER TABLE market_environment_metrics
      ADD COLUMN IF NOT EXISTS market_total_amount NUMERIC(20,2) NOT NULL DEFAULT 0;
    ALTER TABLE market_environment_metrics
      ADD COLUMN IF NOT EXISTS shanghai_index_pct_chg NUMERIC(10,4) NOT NULL DEFAULT 0;
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def fetch_dedup_rows(manager: PostgresDatabaseManager, trade_date_value: date) -> list[dict]:
    sql = """
    WITH ranked AS (
        SELECT
            trade_date,
            stock_id,
            stock_name,
            open_price,
            high_price,
            close_price,
            pre_close,
            pct_chg,
            amount,
            limit_up,
            is_leader,
            rank_order,
            ROW_NUMBER() OVER (
                PARTITION BY trade_date, stock_id
                ORDER BY is_leader DESC, limit_up DESC, rank_order ASC, amount DESC NULLS LAST, subject_key ASC
            ) AS rn
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1
    )
    SELECT
        trade_date, stock_id, stock_name, open_price, high_price,
        close_price, pre_close, pct_chg, amount, limit_up, is_leader, rank_order
    FROM ranked
    WHERE rn = 1
    ORDER BY stock_id
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_recent_pullback_context(
    manager: PostgresDatabaseManager,
    trade_date_value: date,
    lookback_days: int = 7,
) -> dict[str, object]:
    sql = """
    SELECT trade_date, open_close_pullback_ratio
    FROM market_environment_metrics
    WHERE trade_date < $1::date
    ORDER BY trade_date DESC
    LIMIT $2
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value, lookback_days)
    ratios = [round(float(row["open_close_pullback_ratio"] or 0.0), 4) for row in rows]
    return {
        "open_close_pullback_recent_7d": ratios[::-1],
        "open_close_pullback_recent_7d_count": len(ratios),
        "open_close_pullback_recent_7d_avg": round(sum(ratios) / len(ratios), 4) if ratios else 0.0,
        "open_close_pullback_recent_7d_median": round(median(ratios), 4) if ratios else 0.0,
        "open_close_pullback_recent_7d_max": round(max(ratios), 4) if ratios else 0.0,
        "open_close_pullback_recent_7d_min": round(min(ratios), 4) if ratios else 0.0,
    }


async def fetch_shanghai_index_context(
    manager: PostgresDatabaseManager,
    trade_date_value: date,
) -> dict[str, object]:
    sql = """
    SELECT pct_chg
    FROM stock_daily_snapshot
    WHERE trade_date = $1::date
      AND stock_id = '000001.SH'
    ORDER BY updated_at DESC
    LIMIT 1
    """
    async with manager.pool.acquire() as conn:
        row = await conn.fetchrow(sql, trade_date_value)
    if row and row["pct_chg"] is not None:
        return {
            "shanghai_index_pct_chg": round(float(row["pct_chg"]), 4),
            "shanghai_index_available": True,
            "shanghai_index_source": "stock_daily_snapshot",
        }

    local_path = PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar" / "000001.SH.jsonl"
    if local_path.exists():
        try:
            for line in local_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                raw = line.strip()
                if not raw:
                    continue
                item = json.loads(raw)
                if str(item.get("trade_date") or "") != trade_date_value.isoformat():
                    continue
                pct_chg = item.get("pct_chg")
                if pct_chg is None:
                    break
                return {
                    "shanghai_index_pct_chg": round(float(pct_chg), 4),
                    "shanghai_index_available": True,
                    "shanghai_index_source": "local_tushare_daily_bar",
                }
        except Exception:
            pass

    return {
        "shanghai_index_pct_chg": 0.0,
        "shanghai_index_available": False,
        "shanghai_index_source": "",
    }


def _pct(base: float, target: float) -> float:
    if not base:
        return 0.0
    return round((float(target) - float(base)) / float(base) * 100.0, 4)


def build_metrics(
    trade_date_value: date,
    today_rows: list[dict],
    previous_rows: list[dict],
    intraday_map: dict[str, list[dict]] | None = None,
) -> MarketEnvironmentMetrics:
    today_by_stock = {str(row["stock_id"]): row for row in today_rows}
    intraday_map = intraday_map or {}
    intraday_service = MarketEnvironmentIntradayService()

    up_count = 0
    down_count = 0
    flat_count = 0
    limit_up_count = 0
    limit_down_count = 0
    open_pct_values: list[float] = []
    close_pct_values: list[float] = []
    today_total_amount = 0.0
    prev_total_amount = 0.0
    morning_high_then_fall_count = 0
    intraday_fade_count = 0
    open_close_pullback_count = 0

    for row in today_rows:
        pct_chg = float(row.get("pct_chg") or 0.0)
        pre_close = float(row.get("pre_close") or 0.0)
        open_price = float(row.get("open_price") or 0.0)
        high_price = float(row.get("high_price") or 0.0)
        close_price = float(row.get("close_price") or 0.0)
        amount = float(row.get("amount") or 0.0)
        open_pct = _pct(pre_close, open_price) if pre_close and open_price else 0.0
        high_pct = _pct(pre_close, high_price) if pre_close and high_price else 0.0

        open_pct_values.append(open_pct)
        close_pct_values.append(pct_chg)
        today_total_amount += amount

        if pct_chg > 0:
            up_count += 1
        elif pct_chg < 0:
            down_count += 1
        else:
            flat_count += 1

        if bool(row.get("limit_up")):
            limit_up_count += 1
        if pct_chg <= -9.8:
            limit_down_count += 1

        points = intraday_service.parse_points(intraday_map.get(str(row["stock_id"])))
        if points:
            if intraday_service.is_morning_high_then_fall(points):
                morning_high_then_fall_count += 1
            if intraday_service.is_intraday_fade(points):
                intraday_fade_count += 1
        else:
            if high_pct >= 3.0 and (high_pct - pct_chg) >= 2.0:
                morning_high_then_fall_count += 1
            if open_pct >= 1.0 and (open_pct - pct_chg) >= 1.5:
                intraday_fade_count += 1

        open_close_delta = pct_chg - open_pct
        if open_close_delta <= 1.5:
            open_close_pullback_count += 1

    for row in previous_rows:
        prev_total_amount += float(row.get("amount") or 0.0)

    yesterday_limit_up_cohort = [row for row in previous_rows if bool(row.get("limit_up"))]
    open_strength_values: list[float] = []
    open_red_count = 0
    premium_count = 0
    fade_count = 0
    fail_count = 0

    yesterday_high_mark = sorted(
        yesterday_limit_up_cohort,
        key=lambda row: (
            0 if bool(row.get("is_leader")) else 1,
            int(row.get("rank_order") or 9999),
            -float(row.get("amount") or 0.0),
        ),
    )[:10]
    high_mark_strong_count = 0
    high_mark_weak_count = 0

    for prev_row in yesterday_limit_up_cohort:
        stock_id = str(prev_row["stock_id"])
        today_row = today_by_stock.get(stock_id)
        if not today_row:
            continue
        pre_close = float(today_row.get("pre_close") or 0.0)
        open_price = float(today_row.get("open_price") or 0.0)
        high_price = float(today_row.get("high_price") or 0.0)
        close_pct = float(today_row.get("pct_chg") or 0.0)
        open_pct = _pct(pre_close, open_price) if pre_close and open_price else 0.0
        high_pct = _pct(pre_close, high_price) if pre_close and high_price else 0.0

        open_strength_values.append(open_pct)
        if open_pct > 0:
            open_red_count += 1
        if close_pct > 0:
            premium_count += 1
        if open_pct > 0 and close_pct < (open_pct - 2.0):
            fade_count += 1
        if close_pct < 0:
            fail_count += 1

    for prev_row in yesterday_high_mark:
        stock_id = str(prev_row["stock_id"])
        today_row = today_by_stock.get(stock_id)
        if not today_row:
            continue
        close_pct = float(today_row.get("pct_chg") or 0.0)
        if bool(today_row.get("limit_up")) or close_pct >= 3.0:
            high_mark_strong_count += 1
        elif close_pct < 0:
            high_mark_weak_count += 1

    cohort_size = len(yesterday_limit_up_cohort)
    total_today = len(today_rows)
    avg_open_pct = round(sum(open_pct_values) / len(open_pct_values), 4) if open_pct_values else 0.0
    avg_close_pct = round(sum(close_pct_values) / len(close_pct_values), 4) if close_pct_values else 0.0
    intraday_coverage = sum(1 for row in today_rows if str(row["stock_id"]) in intraday_map)
    source_trace = {
        "total_today_stocks": total_today,
        "yesterday_limit_up_cohort": cohort_size,
        "yesterday_high_mark_cohort": len(yesterday_high_mark),
        "intraday_coverage": intraday_coverage,
        "open_close_pullback_count": open_close_pullback_count,
        "open_close_pullback_ratio": _safe_div(open_close_pullback_count, total_today),
        "market_total_amount": round(today_total_amount, 2),
        "daily_proxy_fallback": intraday_coverage < total_today,
    }
    trace_seed = json.dumps(
        {
            "trade_date": trade_date_value.isoformat(),
            "today": total_today,
            "yesterday_limit_up": cohort_size,
            "yesterday_high_mark": len(yesterday_high_mark),
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    return MarketEnvironmentMetrics(
        trade_date=trade_date_value.isoformat(),
        up_count=up_count,
        down_count=down_count,
        flat_count=flat_count,
        advance_decline_ratio=_safe_div(up_count, down_count),
        limit_up_count=limit_up_count,
        limit_down_count=limit_down_count,
        limit_up_down_ratio=_safe_div(limit_up_count, limit_down_count),
        yesterday_limit_up_open_strength=round(sum(open_strength_values) / len(open_strength_values), 4)
        if open_strength_values else 0.0,
        yesterday_limit_up_open_red_ratio=_safe_div(open_red_count, cohort_size),
        yesterday_limit_up_premium_ratio=_safe_div(premium_count, cohort_size),
        yesterday_limit_up_fade_ratio=_safe_div(fade_count, cohort_size),
        yesterday_limit_up_fail_ratio=_safe_div(fail_count, cohort_size),
        morning_high_then_fall_count=morning_high_then_fall_count,
        morning_high_then_fall_ratio=_safe_div(morning_high_then_fall_count, total_today),
        intraday_fade_count=intraday_fade_count,
        intraday_fade_ratio=_safe_div(intraday_fade_count, total_today),
        open_close_pullback_count=open_close_pullback_count,
        open_close_pullback_ratio=_safe_div(open_close_pullback_count, total_today),
        high_mark_strong_count=high_mark_strong_count,
        high_mark_weak_count=high_mark_weak_count,
        market_total_amount=round(today_total_amount, 2),
        market_volume_change_pct=_pct(prev_total_amount, today_total_amount) if prev_total_amount else 0.0,
        market_avg_open_pct=avg_open_pct,
        market_avg_close_pct=avg_close_pct,
        shanghai_index_pct_chg=0.0,
        source_trace_id=hashlib.sha1(trace_seed.encode("utf-8")).hexdigest()[:16],
        source_trace=source_trace,
        source_version="market_environment_metrics.v2.intraday_mixed" if intraday_coverage else "market_environment_metrics.v1.daily_proxy",
        rule_version="market_environment_metrics.v2.intraday_mixed" if intraday_coverage else "market_environment_metrics.v1.daily_proxy",
    )


async def upsert_row(manager: PostgresDatabaseManager, item: MarketEnvironmentMetrics) -> None:
    sql = """
    INSERT INTO market_environment_metrics (
        trade_date, up_count, down_count, flat_count, advance_decline_ratio,
        limit_up_count, limit_down_count, limit_up_down_ratio,
        yesterday_limit_up_open_strength, yesterday_limit_up_open_red_ratio,
        yesterday_limit_up_premium_ratio, yesterday_limit_up_fade_ratio, yesterday_limit_up_fail_ratio,
        morning_high_then_fall_count, morning_high_then_fall_ratio,
        intraday_fade_count, intraday_fade_ratio,
        open_close_pullback_count, open_close_pullback_ratio,
        high_mark_strong_count, high_mark_weak_count,
        market_total_amount, market_volume_change_pct, market_avg_open_pct, market_avg_close_pct,
        shanghai_index_pct_chg,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8,
        $9, $10,
        $11, $12, $13,
        $14, $15,
        $16, $17,
        $18, $19,
        $20, $21,
        $22, $23, $24, $25,
        $26, $27, $28, $29::jsonb, $30, $31
    )
    ON CONFLICT (trade_date)
    DO UPDATE SET
        up_count = EXCLUDED.up_count,
        down_count = EXCLUDED.down_count,
        flat_count = EXCLUDED.flat_count,
        advance_decline_ratio = EXCLUDED.advance_decline_ratio,
        limit_up_count = EXCLUDED.limit_up_count,
        limit_down_count = EXCLUDED.limit_down_count,
        limit_up_down_ratio = EXCLUDED.limit_up_down_ratio,
        yesterday_limit_up_open_strength = EXCLUDED.yesterday_limit_up_open_strength,
        yesterday_limit_up_open_red_ratio = EXCLUDED.yesterday_limit_up_open_red_ratio,
        yesterday_limit_up_premium_ratio = EXCLUDED.yesterday_limit_up_premium_ratio,
        yesterday_limit_up_fade_ratio = EXCLUDED.yesterday_limit_up_fade_ratio,
        yesterday_limit_up_fail_ratio = EXCLUDED.yesterday_limit_up_fail_ratio,
        morning_high_then_fall_count = EXCLUDED.morning_high_then_fall_count,
        morning_high_then_fall_ratio = EXCLUDED.morning_high_then_fall_ratio,
        intraday_fade_count = EXCLUDED.intraday_fade_count,
        intraday_fade_ratio = EXCLUDED.intraday_fade_ratio,
        open_close_pullback_count = EXCLUDED.open_close_pullback_count,
        open_close_pullback_ratio = EXCLUDED.open_close_pullback_ratio,
        high_mark_strong_count = EXCLUDED.high_mark_strong_count,
        high_mark_weak_count = EXCLUDED.high_mark_weak_count,
        market_total_amount = EXCLUDED.market_total_amount,
        market_volume_change_pct = EXCLUDED.market_volume_change_pct,
        market_avg_open_pct = EXCLUDED.market_avg_open_pct,
        market_avg_close_pct = EXCLUDED.market_avg_close_pct,
        shanghai_index_pct_chg = EXCLUDED.shanghai_index_pct_chg,
        source_type = EXCLUDED.source_type,
        source_trace_id = EXCLUDED.source_trace_id,
        source_trace = EXCLUDED.source_trace,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(
            sql,
            _parse_trade_date(item.trade_date),
            item.up_count,
            item.down_count,
            item.flat_count,
            item.advance_decline_ratio,
            item.limit_up_count,
            item.limit_down_count,
            item.limit_up_down_ratio,
            item.yesterday_limit_up_open_strength,
            item.yesterday_limit_up_open_red_ratio,
            item.yesterday_limit_up_premium_ratio,
            item.yesterday_limit_up_fade_ratio,
            item.yesterday_limit_up_fail_ratio,
            item.morning_high_then_fall_count,
            item.morning_high_then_fall_ratio,
            item.intraday_fade_count,
            item.intraday_fade_ratio,
            item.open_close_pullback_count,
            item.open_close_pullback_ratio,
            item.high_mark_strong_count,
            item.high_mark_weak_count,
            item.market_total_amount,
            item.market_volume_change_pct,
            item.market_avg_open_pct,
            item.market_avg_close_pct,
            item.shanghai_index_pct_chg,
            item.source_type,
            item.source_trace_id,
            json.dumps(item.source_trace, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )


async def main_async() -> int:
    args = parse_args()
    trade_date_value = _parse_trade_date(args.trade_date)
    intraday_map = _load_intraday_map(args.intraday_json)

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        previous_trade_date = await fetch_prev_trade_date(manager, trade_date_value)
        if previous_trade_date is None:
            raise RuntimeError(f"无法找到 {trade_date_value} 的上一交易日，终止计算")
        today_rows = await fetch_dedup_rows(manager, trade_date_value)
        previous_rows = await fetch_dedup_rows(manager, previous_trade_date)
        metrics = build_metrics(trade_date_value, today_rows, previous_rows, intraday_map=intraday_map)
        recent_context = await fetch_recent_pullback_context(manager, trade_date_value)
        index_context = await fetch_shanghai_index_context(manager, trade_date_value)
        metrics = replace(
            metrics,
            source_trace={
                **metrics.source_trace,
                **recent_context,
                **index_context,
            },
            shanghai_index_pct_chg=float(index_context.get("shanghai_index_pct_chg") or 0.0),
        )
        await upsert_row(manager, metrics)

        print(f"[OK] trade_date={metrics.trade_date}")
        print(f"[OK] total={metrics.up_count + metrics.down_count + metrics.flat_count}")
        print(f"[OK] up={metrics.up_count} down={metrics.down_count} flat={metrics.flat_count}")
        print(f"[OK] limit_up={metrics.limit_up_count} limit_down={metrics.limit_down_count}")
        print(f"[OK] breadth={metrics.advance_decline_ratio:.2f}")
        print(f"[OK] relay_open_red={metrics.yesterday_limit_up_open_red_ratio:.2%}")
        print(f"[OK] open_close_pullback={metrics.open_close_pullback_ratio:.2%}")
        print(f"[OK] market_total_amount={metrics.market_total_amount / 1e12:.2f}万亿")
        print(f"[OK] shanghai_index_pct_chg={metrics.shanghai_index_pct_chg:.2%}")
        print(f"[OK] intraday_coverage={metrics.source_trace.get('intraday_coverage', 0)}")
        print(f"[OK] source_trace_id={metrics.source_trace_id}")
        return 0
    finally:
        await manager.disconnect()


async def fetch_prev_trade_date(manager: PostgresDatabaseManager, trade_date_value: date) -> date | None:
    sql = """
    SELECT MAX(trade_date) AS prev_trade_date
    FROM stock_daily_snapshot
    WHERE trade_date < $1::date
    """
    async with manager.pool.acquire() as conn:
        row = await conn.fetchrow(sql, trade_date_value)
    return row.get("prev_trade_date") if row else None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.adapters.jyhf_adapter import JyhfAdapter
from stock_service.models import StockDailySnapshot
from stock_service.services.stock_kline_judgement_service import StockKlineJudgementService


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
    )


def parse_args():
    parser = argparse.ArgumentParser(description="读取 DB stock_daily_snapshot 构建个股位置/形态判断")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 只")
    parser.add_argument("--universe", default="seed_candidates+strong_watch",
                        choices=["all", "seed_candidates+strong_watch", "strong_watch", "candidates"],
                        help="股票范围: all=全市场, seed_candidates+strong_watch=seed候选+强股池(推荐)")
    parser.add_argument("--allow-lag-days", type=int, default=0,
                        help="宽容模式下，允许 latest bar 距 trade_date 不超过 N 天（0=严格）")
    parser.add_argument("--enable-jyhf-fallback", action="store_true", default=False,
                        help="启用 JYHF adapter 本地文件兜底（默认关闭，Tushare 为主数据源）")
    return parser.parse_args()


def _to_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


async def _load_universe_stock_ids(db_config: DatabaseConfig, universe: str, trade_date: str) -> set[str]:
    """从 seed 候选 + 强股池加载 stock_id 集合，去重并统一格式。"""
    if universe == "all":
        return set()

    stock_ids: set[str] = set()
    td = _to_date(trade_date)
    manager = PostgresDatabaseManager(db_config)
    await manager.connect()
    try:
        async with manager.pool.acquire() as conn:
            if "seed_candidates" in universe:
                # seed candidates: subject_stock_daily_snapshot 中满足条件的股票
                rows = await conn.fetch(
                    """SELECT DISTINCT stock_id FROM subject_stock_daily_snapshot
                       WHERE trade_date = $1
                         AND (COALESCE(limit_up, FALSE)
                              OR COALESCE(pct_chg, 0) >= 7.0
                              OR COALESCE(rank_order, 999) <= 3)""",
                    td,
                )
                for r in rows:
                    stock_ids.add(_normalize_stock_id(str(r["stock_id"])))

            if "strong_watch" in universe:
                # 7日窗口强股池
                rows = await conn.fetch(
                    """SELECT DISTINCT stock_id FROM strong_stock_watch_pool
                       WHERE last_trade_date >= ($1::date - INTERVAL '7 days')""",
                    td,
                )
                for r in rows:
                    stock_ids.add(_normalize_stock_id(str(r["stock_id"])))

            if "candidates" in universe:
                rows = await conn.fetch(
                    "SELECT DISTINCT stock_id FROM weak_to_strong_candidate_pool WHERE trade_date <= $1",
                    td,
                )
                for r in rows:
                    stock_ids.add(_normalize_stock_id(str(r["stock_id"])))
    finally:
        await manager.disconnect()
    return stock_ids


def _normalize_stock_id(raw: str) -> str:
    s = raw.strip().upper()
    if "." in s:
        return s
    if len(s) == 6:
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        elif s.startswith(("0", "3")):
            return f"{s}.SZ"
    return s


def _db_row_to_snapshot(row: dict, stock_id: str) -> StockDailySnapshot | None:
    """将 DB stock_daily_snapshot 行转换为 StockDailySnapshot。

    DB 返回: trade_date (date), open_price (Decimal), ...
    StockDailySnapshot 期望: trade_date (str), open_price (Optional[float]), ...
    """
    try:
        td = row.get("trade_date")
        if td is None:
            return None
        return StockDailySnapshot(
            trade_date=str(td)[:10],
            stock_id=stock_id,
            stock_name=row.get("stock_name") or "",
            open_price=_safe_float(row.get("open_price")),
            high_price=_safe_float(row.get("high_price")),
            low_price=_safe_float(row.get("low_price")),
            close_price=_safe_float(row.get("close_price")),
            pre_close=_safe_float(row.get("pre_close")),
            pct_chg=_safe_float(row.get("pct_chg")),
            volume=_safe_float(row.get("volume")),
            amount=_safe_float(row.get("amount")),
            source_name=str(row.get("source_name") or "tushare"),
        )
    except Exception:
        return None


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def build_jyhf_current_bar_map(trade_date: str) -> dict[str, StockDailySnapshot]:
    adapter = JyhfAdapter(PROJECT_ROOT)
    result: dict[str, StockDailySnapshot] = {}
    for row in adapter.iter_stock_daily_rows(trade_date):
        stock_id = str(row.get("stock_id") or "").strip().upper()
        if not stock_id or stock_id in result:
            continue
        result[stock_id] = StockDailySnapshot(
            trade_date=trade_date,
            stock_id=stock_id,
            stock_name=row.get("stock_name"),
            open_price=row.get("open_price"),
            high_price=row.get("high_price"),
            low_price=row.get("low_price"),
            close_price=row.get("close_price"),
            pre_close=row.get("pre_close"),
            pct_chg=row.get("pct_chg"),
            volume=row.get("volume"),
            amount=row.get("amount"),
            source_name="jyhf",
        )
    return result


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS stock_position_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL,
        position_label VARCHAR(40) NOT NULL,
        distance_to_20d_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        distance_to_60d_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        distance_to_120d_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        distance_to_all_time_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        ma_alignment_status VARCHAR(40) NOT NULL DEFAULT '',
        trend_strength_score NUMERIC(12,4) NOT NULL DEFAULT 0,
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.stock_position',
        source_trace_id VARCHAR(80) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT 'stock_position_judgement.v1',
        rule_version VARCHAR(80) NOT NULL DEFAULT 'stock_position_judgement.v1',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_stock_position_judgement UNIQUE (trade_date, stock_id)
    );
    CREATE TABLE IF NOT EXISTS stock_pattern_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL,
        pattern_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
        volume_pattern_status VARCHAR(40) NOT NULL DEFAULT '',
        breakout_status VARCHAR(40) NOT NULL DEFAULT '',
        pullback_status VARCHAR(40) NOT NULL DEFAULT '',
        risk_pattern_status VARCHAR(40) NOT NULL DEFAULT '',
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.stock_pattern',
        source_trace_id VARCHAR(80) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT 'stock_pattern_judgement.v1',
        rule_version VARCHAR(80) NOT NULL DEFAULT 'stock_pattern_judgement.v1',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_stock_pattern_judgement UNIQUE (trade_date, stock_id)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql)


async def main_async() -> int:
    args = parse_args()
    service = StockKlineJudgementService()
    logger = logging.getLogger("build_stock_kline_judgements")

    # P1-D: universe 过滤
    pg_config = get_postgres_config()
    universe_ids = await _load_universe_stock_ids(pg_config, args.universe, args.trade_date)
    universe_count = len(universe_ids) if universe_ids else 0
    if universe_ids:
        logger.warning("universe=%s stock_count=%d", args.universe, universe_count)

    # P1-F-2: 从 DB stock_daily_snapshot 读取日K
    manager = PostgresDatabaseManager(pg_config)
    await manager.connect()
    try:
        td = _to_date(args.trade_date)
        # 修复: 使用 timedelta 避免 2/29 的 replace(year=...) 错误
        lookback_start = td - timedelta(days=370)
        universe_list = sorted(universe_ids) if universe_ids else None

        logger.warning("Loading daily bars from DB (start=%s end=%s stock_ids=%s)...",
                       lookback_start, td,
                       len(universe_list) if universe_list else "all")
        raw_rows = await manager.get_stock_daily_bars_range(
            lookback_start, td, stock_ids=universe_list,
        )
        logger.warning("Loaded %d daily bar rows from DB", len(raw_rows))
    finally:
        await manager.disconnect()

    # 按 stock_id 分组
    bars_by_stock: dict[str, list[StockDailySnapshot]] = {}
    db_stock_ids: set[str] = set()
    for row in raw_rows:
        sid = _normalize_stock_id(str(row["stock_id"]))
        db_stock_ids.add(sid)
        snapshot = _db_row_to_snapshot(row, sid)
        if snapshot is None:
            continue
        bars_by_stock.setdefault(sid, []).append(snapshot)

    for sid in bars_by_stock:
        bars_by_stock[sid].sort(key=lambda b: b.trade_date)

    db_stock_count = len(bars_by_stock)
    logger.warning("Grouped into %d stocks with DB bars", db_stock_count)

    # ── P1-F-2a: 覆盖率诊断 ──
    latest_dist: Counter = Counter()
    for sid in db_stock_ids:
        bars = bars_by_stock.get(sid)
        latest = bars[-1].trade_date if bars else "missing"
        latest_dist[latest] += 1
    for sid in (universe_ids or set()):
        if sid not in db_stock_ids:
            latest_dist["missing_all"] += 1

    missing_target_count = universe_count - latest_dist.get(args.trade_date, 0)
    coverage_pct = round((latest_dist.get(args.trade_date, 0) / universe_count * 100), 1) if universe_count else 0.0

    logger.warning("── 覆盖率诊断 ──")
    logger.warning("universe_count=%d  db_stock_count=%d  db_rows=%d",
                   universe_count, db_stock_count, len(raw_rows))
    logger.warning("latest=%s matched=%d (%.1f%%)  missing_target=%d  missing_all=%d",
                   args.trade_date, latest_dist.get(args.trade_date, 0),
                   coverage_pct, missing_target_count, latest_dist.get("missing_all", 0))
    logger.warning("── latest_trade_date 分布 ──")
    for dt, cnt in sorted(latest_dist.items(), key=lambda x: str(x[0]), reverse=True):
        logger.warning("  %s: %d stocks", dt, cnt)

    # 抽样缺失详情
    missing_samples = [sid for sid in (sorted(universe_ids) if universe_ids else [])
                       if sid not in db_stock_ids or (bars_by_stock.get(sid) or [None])[-1].trade_date != args.trade_date]
    if missing_samples:
        logger.warning("── 缺失目标日期样本 (前 20) ──")
        for sid in missing_samples[:20]:
            bars = bars_by_stock.get(sid)
            latest_str = bars[-1].trade_date if bars else "missing_all"
            logger.warning("  %s: latest=%s", sid, latest_str)

    # ── 质量门禁判定 ──
    gap_days = args.allow_lag_days
    status = "OK"
    if coverage_pct < 30:
        status = "FAILED"
        logger.error("COVERAGE_CHECK FAILED: %.1f%% < 30%% threshold", coverage_pct)
    elif coverage_pct < 80:
        if gap_days > 0:
            status = "WARNING"
            logger.warning("COVERAGE_CHECK WARNING: %.1f%% < 80%% (allow_lag=%d)", coverage_pct, gap_days)
        else:
            status = "DEGRADED"
            logger.warning("COVERAGE_CHECK DEGRADED: %.1f%% < 80%% (strict mode)", coverage_pct)

    # ── JYHF fallback (可选) ──
    jyhf_current_bar_map: dict[str, StockDailySnapshot] = {}
    if args.enable_jyhf_fallback:
        logger.warning("JYHF fallback enabled, loading current bar map...")
        jyhf_current_bar_map = build_jyhf_current_bar_map(args.trade_date)
        logger.warning("JYHF fallback: %d stocks available", len(jyhf_current_bar_map))

    # ── 判定截止日 ──
    from datetime import date as date_cls
    cutoff_date = td
    if gap_days > 0:
        cutoff_date = td - timedelta(days=gap_days)
        logger.warning("Using cutoff_date=%s (allow_lag=%d)", cutoff_date, gap_days)

    # ── 形态判断循环 ──
    position_rows = []
    pattern_rows = []
    matched_count = 0
    skipped_no_match = 0

    # Debug: 抽样检查匹配失败原因
    _skip_samples: list[str] = []

    for stock_id, rows in sorted(bars_by_stock.items()):
        if not rows:
            _skip_samples.append(f"{stock_id}: empty bars")
            continue

        latest = rows[-1]
        if latest.trade_date < str(cutoff_date):
            # JYHF fallback
            if jyhf_current_bar_map:
                fallback_row = jyhf_current_bar_map.get(stock_id)
                if fallback_row:
                    rows.append(fallback_row)
                    rows = sorted(rows, key=lambda item: item.trade_date)
            if rows[-1].trade_date < str(cutoff_date):
                if skipped_no_match < 10:
                    _skip_samples.append(f"{stock_id}: latest={rows[-1].trade_date} < cutoff={str(cutoff_date)}")
                skipped_no_match += 1
                continue

        matched_count += 1
        if args.limit and matched_count > args.limit:
            break

        position = service.build_position_judgement(rows)
        pattern = service.build_pattern_judgement(rows)
        if position:
            position_rows.append(position)
        if pattern:
            pattern_rows.append(pattern)

    logger.warning("Judgement: matched=%d skipped=%d position=%d pattern=%d",
                   matched_count, skipped_no_match, len(position_rows), len(pattern_rows))
    if _skip_samples:
        logger.warning("── 跳过样本 (前 10) ──")
        for s in _skip_samples[:10]:
            logger.warning("  %s", s)

    # ── 写入 DB ──
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        async with manager.pool.acquire() as conn:
            if position_rows:
                await conn.executemany(
                    """
                    INSERT INTO stock_position_judgement (
                        trade_date, stock_id, stock_name, position_label,
                        distance_to_20d_high, distance_to_60d_high, distance_to_120d_high, distance_to_all_time_high,
                        ma_alignment_status, trend_strength_score, conclusion, evidence,
                        source_type, source_trace_id, source_trace, source_version, rule_version
                    ) VALUES (
                        $1, $2, $3, $4,
                        $5, $6, $7, $8,
                        $9, $10, $11, $12::jsonb,
                        $13, $14, $15::jsonb, $16, $17
                    )
                    ON CONFLICT (trade_date, stock_id) DO UPDATE SET
                        stock_name=EXCLUDED.stock_name,
                        position_label=EXCLUDED.position_label,
                        distance_to_20d_high=EXCLUDED.distance_to_20d_high,
                        distance_to_60d_high=EXCLUDED.distance_to_60d_high,
                        distance_to_120d_high=EXCLUDED.distance_to_120d_high,
                        distance_to_all_time_high=EXCLUDED.distance_to_all_time_high,
                        ma_alignment_status=EXCLUDED.ma_alignment_status,
                        trend_strength_score=EXCLUDED.trend_strength_score,
                        conclusion=EXCLUDED.conclusion,
                        evidence=EXCLUDED.evidence,
                        source_type=EXCLUDED.source_type,
                        source_trace_id=EXCLUDED.source_trace_id,
                        source_trace=EXCLUDED.source_trace,
                        source_version=EXCLUDED.source_version,
                        rule_version=EXCLUDED.rule_version,
                        updated_at=NOW()
                    """,
                    [
                        (
                            _to_date(item.trade_date),
                            item.stock_id,
                            item.stock_name,
                            item.position_label,
                            item.distance_to_20d_high,
                            item.distance_to_60d_high,
                            item.distance_to_120d_high,
                            item.distance_to_all_time_high,
                            item.ma_alignment_status,
                            item.trend_strength_score,
                            item.conclusion,
                            json.dumps(item.evidence, ensure_ascii=False),
                            item.source_type,
                            item.source_trace_id,
                            json.dumps(item.source_trace, ensure_ascii=False),
                            item.source_version,
                            item.rule_version,
                        )
                        for item in position_rows
                    ],
                )
            if pattern_rows:
                await conn.executemany(
                    """
                    INSERT INTO stock_pattern_judgement (
                        trade_date, stock_id, stock_name, pattern_labels,
                        volume_pattern_status, breakout_status, pullback_status, risk_pattern_status,
                        conclusion, evidence, source_type, source_trace_id, source_trace, source_version, rule_version
                    ) VALUES (
                        $1, $2, $3, $4::jsonb,
                        $5, $6, $7, $8,
                        $9, $10::jsonb, $11, $12, $13::jsonb, $14, $15
                    )
                    ON CONFLICT (trade_date, stock_id) DO UPDATE SET
                        stock_name=EXCLUDED.stock_name,
                        pattern_labels=EXCLUDED.pattern_labels,
                        volume_pattern_status=EXCLUDED.volume_pattern_status,
                        breakout_status=EXCLUDED.breakout_status,
                        pullback_status=EXCLUDED.pullback_status,
                        risk_pattern_status=EXCLUDED.risk_pattern_status,
                        conclusion=EXCLUDED.conclusion,
                        evidence=EXCLUDED.evidence,
                        source_type=EXCLUDED.source_type,
                        source_trace_id=EXCLUDED.source_trace_id,
                        source_trace=EXCLUDED.source_trace,
                        source_version=EXCLUDED.source_version,
                        rule_version=EXCLUDED.rule_version,
                        updated_at=NOW()
                    """,
                    [
                        (
                            _to_date(item.trade_date),
                            item.stock_id,
                            item.stock_name,
                            json.dumps(item.pattern_labels, ensure_ascii=False),
                            item.volume_pattern_status,
                            item.breakout_status,
                            item.pullback_status,
                            item.risk_pattern_status,
                            item.conclusion,
                            json.dumps(item.evidence, ensure_ascii=False),
                            item.source_type,
                            item.source_trace_id,
                            json.dumps(item.source_trace, ensure_ascii=False),
                            item.source_version,
                            item.rule_version,
                        )
                        for item in pattern_rows
                    ],
                )
    finally:
        await manager.disconnect()

    print(f"[{status}] trade_date={args.trade_date}")
    print(f"[{status}] universe={universe_count} db_rows={len(raw_rows)} db_stocks={db_stock_count}")
    print(f"[{status}] coverage={coverage_pct}% matched_trade_date={matched_count} allow_lag={gap_days}")
    print(f"[{status}] position={len(position_rows)} pattern={len(pattern_rows)}")
    print(json.dumps({
        "status": status,
        "trade_date": args.trade_date,
        "universe": args.universe,
        "universe_count": universe_count,
        "db_row_count": len(raw_rows),
        "db_stock_count": db_stock_count,
        "coverage_pct": coverage_pct,
        "matched_trade_date_count": matched_count,
        "allow_lag_days": gap_days,
        "jyhf_fallback_enabled": args.enable_jyhf_fallback,
        "position_judgements": len(position_rows),
        "pattern_judgements": len(pattern_rows),
        "latest_trade_date_distribution": dict(latest_dist.most_common(20)),
        "missing_target_count": missing_target_count,
        "missing_all_count": latest_dist.get("missing_all", 0),
    }, ensure_ascii=False, indent=2))

    # 质量门禁 → exit code
    if status == "FAILED":
        return 2
    if status == "DEGRADED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

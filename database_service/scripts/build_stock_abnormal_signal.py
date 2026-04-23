#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.config import StockServiceConfig
from stock_service.services.stock_abnormal_signal_service import (
    StockAbnormalInput,
    StockAbnormalSignalService,
)
from stock_service.services.tushare_auction_snapshot_service import TushareAuctionSnapshotService


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
    parser = argparse.ArgumentParser(description="构建异动股票复盘真源表 stock_abnormal_signal")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=0, help="最多处理前 N 条")
    parser.add_argument("--min-turnover-rate", type=float, default=3.0, help="最低日换手率过滤，默认 3.0")
    parser.add_argument("--min-composite-score", type=float, default=40.0, help="最低异动综合分过滤，默认 40.0")
    parser.add_argument("--max-main-net-rank", type=int, default=3, help="主力净流入题材内排名阈值，默认 3")
    parser.add_argument("--require-turnover", action="store_true", help="要求满足高换手/极端换手异动")
    parser.add_argument("--require-main-net-inflow", action="store_true", help="要求满足主力净流入前排")
    parser.add_argument("--require-hot-money-buy", action="store_true", help="要求存在游资买入")
    parser.add_argument("--require-institution-buy", action="store_true", help="要求存在机构净买")
    parser.add_argument("--require-tail-rush", action="store_true", help="要求存在尾盘抢筹")
    parser.add_argument("--token", default=os.getenv("TUSHARE_TOKEN", ""), help="可选：Tushare token，用于自动抓取尾盘竞价缓存")
    parser.add_argument("--force-refresh-tail-auction", action="store_true", help="强制刷新 stk_auction_c 原始缓存")
    parser.add_argument("--details-root", default=str(PROJECT_ROOT / "theme_data_complete" / "stock_details"))
    parser.add_argument("--kline-root", default=str(PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"))
    return parser.parse_args()


def _to_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _to_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _is_st_stock(stock_name: str) -> bool:
    name = str(stock_name or "").strip().upper()
    if not name:
        return False
    return name.startswith("ST") or name.startswith("*ST") or "ST" in name[:4]


def _canonical_stock_id(value: str) -> str:
    raw = str(value or "").strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw


def _theme_name_from_links(subject_key: str, links) -> str:
    for item in links or []:
        if str(item[0]) == str(subject_key):
            return str(item[1])
    return str(subject_key)


def load_current_inputs(trade_date: str, details_root: Path, min_turnover_rate: float = 3.0, limit: int = 0) -> list[StockAbnormalInput]:
    month_token = trade_date[:7]
    result: list[StockAbnormalInput] = []
    for path in sorted(details_root.glob(f"*_{month_token}_stocks.jsonl")):
        subject_key = path.name.split("_", 1)[0]
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, list) or len(row) < 19:
                    continue
                row_trade_date = str(row[0]).split(" ")[0]
                if row_trade_date != trade_date:
                    continue
                stock_name = str(row[3] or "").strip()
                if _is_st_stock(stock_name):
                    continue
                turnover_rate = _to_float(row[18] if len(row) > 18 else None)
                if turnover_rate < min_turnover_rate:
                    continue
                theme_name = _theme_name_from_links(subject_key, row[16] if len(row) > 16 else [])
                result.append(
                    StockAbnormalInput(
                        trade_date=trade_date,
                        subject_key=str(subject_key),
                        theme_name=theme_name,
                        stock_id=str(row[2]).strip().upper(),
                        stock_name=stock_name or str(row[2]).strip().upper(),
                        open_price=_to_float(row[4] if len(row) > 4 else None),
                        high_price=_to_float(row[5] if len(row) > 5 else None),
                        low_price=_to_float(row[6] if len(row) > 6 else None),
                        close_price=_to_float(row[7] if len(row) > 7 else None),
                        pre_close=_to_float(row[8] if len(row) > 8 else None),
                        pct_chg=_to_float(row[10] if len(row) > 10 else None),
                        volume=_to_float(row[12] if len(row) > 12 else None),
                        amount=_to_float(row[13] if len(row) > 13 else None),
                        volume_ratio=_to_float(row[17] if len(row) > 17 else None),
                        turnover_rate=turnover_rate,
                        main_net_inflow=_to_float(row[35] if len(row) > 35 else None),
                    )
                )
                if limit and len(result) >= limit:
                    return result
    return result


def apply_turnover_rank(rows: list[StockAbnormalInput]) -> list[StockAbnormalInput]:
    by_theme: dict[str, list[StockAbnormalInput]] = {}
    for row in rows:
        by_theme.setdefault(row.subject_key, []).append(row)
    ranked: list[StockAbnormalInput] = []
    for subject_key, items in by_theme.items():
        for idx, item in enumerate(sorted(items, key=lambda x: x.turnover_rate, reverse=True), start=1):
            ranked.append(
                StockAbnormalInput(
                    trade_date=item.trade_date,
                    subject_key=item.subject_key,
                    theme_name=item.theme_name,
                    stock_id=item.stock_id,
                    stock_name=item.stock_name,
                    open_price=item.open_price,
                    high_price=item.high_price,
                    low_price=item.low_price,
                    close_price=item.close_price,
                    pre_close=item.pre_close,
                    pct_chg=item.pct_chg,
                    volume=item.volume,
                    amount=item.amount,
                    volume_ratio=item.volume_ratio,
                    turnover_rate=item.turnover_rate,
                    main_net_inflow=item.main_net_inflow,
                    rank_order=item.rank_order,
                    turnover_rank_in_theme=idx,
                )
            )
    return ranked


def apply_main_net_inflow_rank(rows: list[StockAbnormalInput]) -> list[StockAbnormalInput]:
    by_theme: dict[str, list[StockAbnormalInput]] = {}
    for row in rows:
        by_theme.setdefault(row.subject_key, []).append(row)
    ranked: list[StockAbnormalInput] = []
    for _, items in by_theme.items():
        positive = [item for item in items if item.main_net_inflow > 0]
        positive_sorted = sorted(positive, key=lambda x: x.main_net_inflow, reverse=True)
        rank_map = {_canonical_stock_id(item.stock_id): idx for idx, item in enumerate(positive_sorted, start=1)}
        for item in items:
            ranked.append(
                StockAbnormalInput(
                    trade_date=item.trade_date,
                    subject_key=item.subject_key,
                    theme_name=item.theme_name,
                    stock_id=item.stock_id,
                    stock_name=item.stock_name,
                    open_price=item.open_price,
                    high_price=item.high_price,
                    low_price=item.low_price,
                    close_price=item.close_price,
                    pre_close=item.pre_close,
                    pct_chg=item.pct_chg,
                    volume=item.volume,
                    amount=item.amount,
                    volume_ratio=item.volume_ratio,
                    turnover_rate=item.turnover_rate,
                    main_net_inflow=item.main_net_inflow,
                    rank_order=item.rank_order,
                    turnover_rank_in_theme=item.turnover_rank_in_theme,
                    main_net_inflow_rank_in_theme=rank_map.get(_canonical_stock_id(item.stock_id), 0),
                    hot_money_buy_names=item.hot_money_buy_names,
                    institution_net_buy=item.institution_net_buy,
                    institution_seat_count=item.institution_seat_count,
                )
            )
    return ranked


def dedupe_by_stock(rows: list[StockAbnormalInput]) -> list[StockAbnormalInput]:
    best_by_stock: dict[str, StockAbnormalInput] = {}
    for row in rows:
        current = best_by_stock.get(row.stock_id)
        if current is None:
            best_by_stock[row.stock_id] = row
            continue
        current_key = (
            current.turnover_rank_in_theme or 9999,
            current.main_net_inflow_rank_in_theme or 9999,
            -(current.turnover_rate or 0.0),
            -(current.main_net_inflow or 0.0),
            -(current.volume_ratio or 0.0),
            current.subject_key,
        )
        new_key = (
            row.turnover_rank_in_theme or 9999,
            row.main_net_inflow_rank_in_theme or 9999,
            -(row.turnover_rate or 0.0),
            -(row.main_net_inflow or 0.0),
            -(row.volume_ratio or 0.0),
            row.subject_key,
        )
        if new_key < current_key:
            best_by_stock[row.stock_id] = row
    return list(best_by_stock.values())


async def fetch_dragon_tiger_fact_map(manager: PostgresDatabaseManager, trade_date: str) -> dict[str, dict]:
    sql = """
    SELECT
        split_part(stock_id, '.', 1) AS stock_code,
        SUM(COALESCE(institution_net_buy, 0)) AS institution_net_buy,
        MAX(COALESCE(institution_seat_count, 0)) AS institution_seat_count
    FROM dragon_tiger_object
    WHERE trade_date = $1::date
    GROUP BY split_part(stock_id, '.', 1)
    """
    async with manager.pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql, _to_date(trade_date))
        except Exception:
            return {}
    return {
        str(row["stock_code"]): {
            "institution_net_buy": float(row["institution_net_buy"] or 0.0),
            "institution_seat_count": int(row["institution_seat_count"] or 0),
        }
        for row in rows
    }


async def fetch_hot_money_buy_map(manager: PostgresDatabaseManager, trade_date: str) -> dict[str, tuple[str, ...]]:
    sql = """
    SELECT
        stock_id,
        hot_money_name,
        SUM(COALESCE(net_amount, 0)) AS net_amount
    FROM hot_money_trading_activity
    WHERE trade_date = $1::date
      AND side = '买入'
    GROUP BY stock_id, hot_money_name
    ORDER BY stock_id ASC, net_amount DESC
    """
    async with manager.pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql, _to_date(trade_date))
        except Exception:
            return {}
    result: dict[str, list[str]] = {}
    for row in rows:
        stock_id = _canonical_stock_id(row["stock_id"])
        names = result.setdefault(stock_id, [])
        hot_money_name = str(row["hot_money_name"] or "").strip()
        if hot_money_name and hot_money_name not in names:
            names.append(hot_money_name)
    return {key: tuple(value[:3]) for key, value in result.items()}


def attach_capital_facts(
    rows: list[StockAbnormalInput],
    dragon_tiger_map: dict[str, dict],
    hot_money_buy_map: dict[str, tuple[str, ...]],
    tail_auction_map: dict[str, dict] | None = None,
) -> list[StockAbnormalInput]:
    attached: list[StockAbnormalInput] = []
    for item in rows:
        stock_key = _canonical_stock_id(item.stock_id)
        dragon = dragon_tiger_map.get(stock_key, {})
        tail = (tail_auction_map or {}).get(stock_key, {})
        attached.append(
            StockAbnormalInput(
                trade_date=item.trade_date,
                subject_key=item.subject_key,
                theme_name=item.theme_name,
                stock_id=item.stock_id,
                stock_name=item.stock_name,
                open_price=item.open_price,
                high_price=item.high_price,
                low_price=item.low_price,
                close_price=item.close_price,
                pre_close=item.pre_close,
                pct_chg=item.pct_chg,
                volume=item.volume,
                amount=item.amount,
                volume_ratio=item.volume_ratio,
                turnover_rate=item.turnover_rate,
                main_net_inflow=item.main_net_inflow,
                rank_order=item.rank_order,
                turnover_rank_in_theme=item.turnover_rank_in_theme,
                main_net_inflow_rank_in_theme=item.main_net_inflow_rank_in_theme,
                hot_money_buy_names=hot_money_buy_map.get(stock_key, ()),
                institution_net_buy=float(dragon.get("institution_net_buy") or 0.0),
                institution_seat_count=int(dragon.get("institution_seat_count") or 0),
                tail_auction_amount=float(tail.get("tail_auction_amount") or 0.0),
                tail_auction_volume=float(tail.get("tail_auction_volume") or 0.0),
                tail_auction_vwap=float(tail.get("tail_auction_vwap") or 0.0),
            )
        )
    return attached


def load_tail_auction_map(trade_date: str) -> dict[str, dict]:
    config = StockServiceConfig(project_root=PROJECT_ROOT)
    service = TushareAuctionSnapshotService(config)
    cached = service.load_cached_stk_auction_c(trade_date)
    if cached is None:
        return {}
    result: dict[str, dict] = {}
    for record in cached.records:
        stock_code = _canonical_stock_id(record.get("ts_code") or record.get("stock_id") or "")
        if not stock_code:
            continue
        result[stock_code] = {
            "tail_auction_amount": _to_float(record.get("amount")),
            "tail_auction_volume": _to_float(record.get("vol")),
            "tail_auction_vwap": _to_float(record.get("vwap")),
        }
    return result


def passes_abnormal_filters(signal, args) -> bool:
    if signal is None or not signal.abnormal_labels or signal.abnormal_composite_score < args.min_composite_score:
        return False

    has_main_net_focus = (
        signal.main_net_inflow > 0
        and signal.main_net_inflow_rank_in_theme
        and signal.main_net_inflow_rank_in_theme <= args.max_main_net_rank
    )
    has_turnover_focus = bool(signal.is_high_turnover or signal.is_extreme_turnover)

    selected_checks = []
    if args.require_turnover:
        selected_checks.append(has_turnover_focus)
    if args.require_main_net_inflow:
        selected_checks.append(has_main_net_focus)
    if args.require_hot_money_buy:
        selected_checks.append(bool(signal.has_hot_money_buy))
    if args.require_institution_buy:
        selected_checks.append(bool(signal.has_institution_buy))
    if args.require_tail_rush:
        selected_checks.append(bool(signal.has_tail_rush_buy))

    if selected_checks:
        return all(selected_checks)

    # 默认兼容旧口径：需要至少有一类资金聚焦证据。
    return has_main_net_focus or signal.has_hot_money_buy or signal.has_institution_buy


def fetch_or_cache_tail_auction_snapshot(trade_date: str, stock_ids: list[str], token: str, force_refresh: bool) -> int:
    if not token:
        return 0
    config = StockServiceConfig(project_root=PROJECT_ROOT, tushare_token=token)
    service = TushareAuctionSnapshotService(config)
    try:
        result = service.fetch_or_cache_stk_auction_c(
            trade_date,
            stock_ids,
            force_refresh=force_refresh,
        )
        return int(result.row_count)
    except Exception as exc:
        print(f"[WARN] stk_auction_c unavailable, fallback to cache/daily_proxy: {exc}")
        return 0


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS stock_abnormal_signal (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(64) NOT NULL,
        theme_name VARCHAR(120) NOT NULL DEFAULT '',
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL DEFAULT '',
        turnover_rate NUMERIC(12,4) NOT NULL DEFAULT 0,
        turnover_rank_in_theme INTEGER NOT NULL DEFAULT 0,
        turnover_abnormal_score NUMERIC(12,4) NOT NULL DEFAULT 0,
        main_net_inflow NUMERIC(18,2) NOT NULL DEFAULT 0,
        main_net_inflow_rank_in_theme INTEGER NOT NULL DEFAULT 0,
        capital_focus_score NUMERIC(12,4) NOT NULL DEFAULT 0,
        is_high_turnover BOOLEAN NOT NULL DEFAULT FALSE,
        is_extreme_turnover BOOLEAN NOT NULL DEFAULT FALSE,
        volume_ratio_to_ma50 NUMERIC(12,4) NOT NULL DEFAULT 0,
        volume_abnormal_score NUMERIC(12,4) NOT NULL DEFAULT 0,
        is_volume_breakout BOOLEAN NOT NULL DEFAULT FALSE,
        is_double_volume BOOLEAN NOT NULL DEFAULT FALSE,
        is_high_volume_bar BOOLEAN NOT NULL DEFAULT FALSE,
        tail_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
        tail_amount_ratio NUMERIC(12,4) NOT NULL DEFAULT 0,
        tail_unmatched_buy_order NUMERIC(18,2) NOT NULL DEFAULT 0,
        tail_abnormal_score NUMERIC(12,4) NOT NULL DEFAULT 0,
        has_tail_rush_buy BOOLEAN NOT NULL DEFAULT FALSE,
        has_tail_large_unmatched_bid BOOLEAN NOT NULL DEFAULT FALSE,
        hot_money_buy_names JSONB NOT NULL DEFAULT '[]'::jsonb,
        institution_net_buy NUMERIC(18,2) NOT NULL DEFAULT 0,
        institution_seat_count INTEGER NOT NULL DEFAULT 0,
        has_hot_money_buy BOOLEAN NOT NULL DEFAULT FALSE,
        has_institution_buy BOOLEAN NOT NULL DEFAULT FALSE,
        abnormal_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
        abnormal_composite_score NUMERIC(12,4) NOT NULL DEFAULT 0,
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.stock_abnormal_signal',
        source_trace_id VARCHAR(80) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT 'stock_abnormal_signal.v1.auction_c_mixed',
        rule_version VARCHAR(80) NOT NULL DEFAULT 'stock_abnormal_signal.v1.auction_c_mixed',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_stock_abnormal_signal UNIQUE (trade_date, stock_id)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql)
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS main_net_inflow NUMERIC(18,2) NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS main_net_inflow_rank_in_theme INTEGER NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS capital_focus_score NUMERIC(12,4) NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS hot_money_buy_names JSONB NOT NULL DEFAULT '[]'::jsonb")
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS institution_net_buy NUMERIC(18,2) NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS institution_seat_count INTEGER NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS has_hot_money_buy BOOLEAN NOT NULL DEFAULT FALSE")
        await conn.execute("ALTER TABLE stock_abnormal_signal ADD COLUMN IF NOT EXISTS has_institution_buy BOOLEAN NOT NULL DEFAULT FALSE")
        await conn.execute(
            """
            DELETE FROM stock_abnormal_signal a
            USING stock_abnormal_signal b
            WHERE a.id < b.id
              AND a.trade_date = b.trade_date
              AND a.stock_id = b.stock_id
            """
        )
        await conn.execute(
            "ALTER TABLE stock_abnormal_signal DROP CONSTRAINT IF EXISTS uq_stock_abnormal_signal;"
        )
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_abnormal_signal_trade_stock ON stock_abnormal_signal (trade_date, stock_id);"
        )


async def upsert_rows(manager: PostgresDatabaseManager, rows):
    sql = """
    INSERT INTO stock_abnormal_signal (
        trade_date, subject_key, theme_name, stock_id, stock_name,
        turnover_rate, turnover_rank_in_theme, main_net_inflow, main_net_inflow_rank_in_theme, turnover_abnormal_score, capital_focus_score, is_high_turnover, is_extreme_turnover,
        volume_ratio_to_ma50, volume_abnormal_score, is_volume_breakout, is_double_volume, is_high_volume_bar,
        tail_amount, tail_amount_ratio, tail_unmatched_buy_order, tail_abnormal_score, has_tail_rush_buy, has_tail_large_unmatched_bid,
        hot_money_buy_names, institution_net_buy, institution_seat_count, has_hot_money_buy, has_institution_buy,
        abnormal_labels, abnormal_composite_score, conclusion, evidence,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8, $9, $10, $11, $12, $13,
        $14, $15, $16, $17, $18,
        $19, $20, $21, $22, $23, $24,
        $25::jsonb, $26, $27, $28, $29,
        $30::jsonb, $31, $32, $33::jsonb,
        $34, $35, $36::jsonb, $37, $38
    )
    ON CONFLICT (trade_date, stock_id) DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        subject_key = EXCLUDED.subject_key,
        stock_name = EXCLUDED.stock_name,
        turnover_rate = EXCLUDED.turnover_rate,
        turnover_rank_in_theme = EXCLUDED.turnover_rank_in_theme,
        main_net_inflow = EXCLUDED.main_net_inflow,
        main_net_inflow_rank_in_theme = EXCLUDED.main_net_inflow_rank_in_theme,
        turnover_abnormal_score = EXCLUDED.turnover_abnormal_score,
        capital_focus_score = EXCLUDED.capital_focus_score,
        is_high_turnover = EXCLUDED.is_high_turnover,
        is_extreme_turnover = EXCLUDED.is_extreme_turnover,
        volume_ratio_to_ma50 = EXCLUDED.volume_ratio_to_ma50,
        volume_abnormal_score = EXCLUDED.volume_abnormal_score,
        is_volume_breakout = EXCLUDED.is_volume_breakout,
        is_double_volume = EXCLUDED.is_double_volume,
        is_high_volume_bar = EXCLUDED.is_high_volume_bar,
        tail_amount = EXCLUDED.tail_amount,
        tail_amount_ratio = EXCLUDED.tail_amount_ratio,
        tail_unmatched_buy_order = EXCLUDED.tail_unmatched_buy_order,
        tail_abnormal_score = EXCLUDED.tail_abnormal_score,
        has_tail_rush_buy = EXCLUDED.has_tail_rush_buy,
        has_tail_large_unmatched_bid = EXCLUDED.has_tail_large_unmatched_bid,
        hot_money_buy_names = EXCLUDED.hot_money_buy_names,
        institution_net_buy = EXCLUDED.institution_net_buy,
        institution_seat_count = EXCLUDED.institution_seat_count,
        has_hot_money_buy = EXCLUDED.has_hot_money_buy,
        has_institution_buy = EXCLUDED.has_institution_buy,
        abnormal_labels = EXCLUDED.abnormal_labels,
        abnormal_composite_score = EXCLUDED.abnormal_composite_score,
        conclusion = EXCLUDED.conclusion,
        evidence = EXCLUDED.evidence,
        source_type = EXCLUDED.source_type,
        source_trace_id = EXCLUDED.source_trace_id,
        source_trace = EXCLUDED.source_trace,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.executemany(
            sql,
            [
                (
                    _to_date(item.trade_date),
                    item.subject_key,
                    item.theme_name,
                    item.stock_id,
                    item.stock_name,
                    item.turnover_rate,
                    item.turnover_rank_in_theme,
                    item.main_net_inflow,
                    item.main_net_inflow_rank_in_theme,
                    item.turnover_abnormal_score,
                    item.capital_focus_score,
                    item.is_high_turnover,
                    item.is_extreme_turnover,
                    item.volume_ratio_to_ma50,
                    item.volume_abnormal_score,
                    item.is_volume_breakout,
                    item.is_double_volume,
                    item.is_high_volume_bar,
                    item.tail_amount,
                    item.tail_amount_ratio,
                    item.tail_unmatched_buy_order,
                    item.tail_abnormal_score,
                    item.has_tail_rush_buy,
                    item.has_tail_large_unmatched_bid,
                    json.dumps(item.hot_money_buy_names, ensure_ascii=False),
                    item.institution_net_buy,
                    item.institution_seat_count,
                    item.has_hot_money_buy,
                    item.has_institution_buy,
                    json.dumps(item.abnormal_labels, ensure_ascii=False),
                    item.abnormal_composite_score,
                    item.conclusion,
                    json.dumps(item.evidence, ensure_ascii=False),
                    item.source_type,
                    item.source_trace_id,
                    json.dumps(item.source_trace, ensure_ascii=False),
                    item.source_version,
                    item.rule_version,
                )
                for item in rows
            ],
        )


async def main_async() -> int:
    args = parse_args()
    service = StockAbnormalSignalService()
    raw_inputs = load_current_inputs(
        args.trade_date,
        Path(args.details_root),
        min_turnover_rate=args.min_turnover_rate,
        limit=args.limit,
    )
    ranked_inputs = apply_main_net_inflow_rank(apply_turnover_rank(raw_inputs))
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        dragon_tiger_map = await fetch_dragon_tiger_fact_map(manager, args.trade_date)
        hot_money_buy_map = await fetch_hot_money_buy_map(manager, args.trade_date)
        if args.token:
            fetch_or_cache_tail_auction_snapshot(
                args.trade_date,
                sorted({_canonical_stock_id(item.stock_id) for item in ranked_inputs}),
                token=args.token,
                force_refresh=args.force_refresh_tail_auction,
            )
        tail_auction_map = load_tail_auction_map(args.trade_date)
        inputs = dedupe_by_stock(
            attach_capital_facts(
                ranked_inputs,
                dragon_tiger_map=dragon_tiger_map,
                hot_money_buy_map=hot_money_buy_map,
                tail_auction_map=tail_auction_map,
            )
        )
        signals = []
        matched_files = 0
        for item in inputs:
            kline_candidates = sorted(Path(args.kline_root).glob(f"{item.stock_id}.*.jsonl"))
            if not kline_candidates:
                continue
            matched_files += 1
            rows = service.load_stock_bars(kline_candidates[0])
            signal = service.build_signal(item, rows)
            if passes_abnormal_filters(signal, args):
                signals.append(signal)
        if signals:
            await upsert_rows(manager, signals)
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] min_turnover_rate={args.min_turnover_rate:.2f}")
        print(f"[OK] min_composite_score={args.min_composite_score:.2f}")
        print(f"[OK] max_main_net_rank={args.max_main_net_rank}")
        print(
            "[OK] active_filters="
            f"turnover={int(args.require_turnover)} "
            f"main_net={int(args.require_main_net_inflow)} "
            f"hot_money={int(args.require_hot_money_buy)} "
            f"institution={int(args.require_institution_buy)} "
            f"tail_rush={int(args.require_tail_rush)}"
        )
        print(f"[OK] inputs={len(inputs)}")
        print(f"[OK] matched_files={matched_files}")
        print(f"[OK] tail_auction_cached={len(tail_auction_map)}")
        print(f"[OK] signal_rows={len(signals)}")
        for item in signals[:10]:
            print(
                f"[ROW] theme={item.theme_name} stock={item.stock_name} "
                f"turn={item.turnover_rate:.2f} vol_ma50={item.volume_ratio_to_ma50:.2f} "
                f"net_rank={item.main_net_inflow_rank_in_theme or '--'} hot={'/'.join(item.hot_money_buy_names[:2]) or '--'} "
                f"inst={item.institution_seat_count} tail={item.has_tail_rush_buy} labels={','.join(item.abnormal_labels) or '--'}"
            )
        return 0
    finally:
        await manager.disconnect()


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

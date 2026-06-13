#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from typing import Any
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.config import StockServiceConfig
from stock_service.services.auction_signal_service import AuctionCandidateInput
from stock_service.services.auction_snapshot_builder_service import AuctionSnapshotBuilderService
from stock_service.services.tushare_auction_snapshot_service import TushareAuctionSnapshotService


def _normalize_stock_id(value: str) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    if "." in raw:
        return raw
    if raw.startswith(("6", "9")):
        return f"{raw}.SH"
    if raw.startswith(("4", "8")):
        return f"{raw}.BJ"
    return f"{raw}.SZ"


def _stock_id_aliases(value: str) -> set[str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return set()
    normalized = _normalize_stock_id(raw)
    aliases = {raw, normalized}
    if "." in normalized:
        aliases.add(normalized.split(".", 1)[0])
    return {alias for alias in aliases if alias}


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
    parser = argparse.ArgumentParser(description="构建 pre_market_auction_snapshot")
    parser.add_argument("--trade-date", required=True, help="目标交易日 YYYY-MM-DD")
    parser.add_argument(
        "--universe-source",
        default="auction_watch_universe",
        choices=["auction_watch_universe", "weak_to_strong_candidates"],
        help="候选来源：auction_watch_universe 或 weak_to_strong_candidates",
    )
    parser.add_argument("--proxy-ratio", type=float, default=0.08, help="前一日最大分时成交额代理系数")
    parser.add_argument("--token", default=os.getenv("TUSHARE_TOKEN", ""), help="Tushare token，可选")
    parser.add_argument("--timeline-json", default="", help="可选：竞价时间序列 JSON 文件")
    parser.add_argument("--force-refresh", action="store_true", help="强制刷新竞价快照")
    parser.add_argument(
        "--allow-online-fetch",
        action="store_true",
        help="允许在本地无缓存时在线拉取 Tushare；默认关闭（离线优先）",
    )
    parser.add_argument("--max-stocks", type=int, default=0, help="可选：仅处理前N只（按候选优先级），0表示不限制")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _load_timeline_map(path_value: str) -> dict[str, tuple[dict, ...]]:
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"timeline json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, tuple[dict, ...]] = {}
    rows = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stock_id = str(row.get("stock_id") or row.get("ts_code") or "").strip().upper()
        points = row.get("points")
        if not stock_id or not isinstance(points, list):
            continue
        for alias in _stock_id_aliases(stock_id):
            result[alias] = tuple(point for point in points if isinstance(point, dict))
    return result


async def fetch_watch_universe(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        stock_id, stock_name, subject_key, theme_name, role_label,
        mainline_alive, primary_cycle_stage, action_bias, is_reversal_watch
    FROM auction_watch_universe
    WHERE trade_date = $1
    ORDER BY candidate_priority, theme_name, candidate_rank, stock_id
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


def _role_label_from_candidate_type(candidate_type: str) -> str:
    mapping = {
        "dragon_repair": "龙头",
        "subdragon_repair": "龙二",
        "strong_trend_repair": "强趋势",
        "bad_limit_repair": "强趋势",
        "upper_shadow_repair": "强趋势",
        "generic_repair": "强趋势",
    }
    return mapping.get(str(candidate_type or "").strip(), "强趋势")


async def fetch_weak_to_strong_universe(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        stock_id,
        stock_name,
        subject_key,
        theme_name,
        candidate_type,
        candidate_score
    FROM weak_to_strong_candidate_pool
    WHERE next_trade_date = $1
    ORDER BY candidate_score DESC, id ASC
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    payload = []
    for row in rows:
        payload.append(
            {
                "stock_id": row["stock_id"],
                "stock_name": row["stock_name"],
                "subject_key": row["subject_key"],
                "theme_name": row["theme_name"] or row["subject_key"] or "",
                "role_label": _role_label_from_candidate_type(str(row["candidate_type"] or "")),
                "mainline_alive": True,
                "action_bias": "watch_open",
                "is_reversal_watch": True,
            }
        )
    return payload


async def fetch_prev_day_context(manager: PostgresDatabaseManager, trade_date_value: date, stock_ids: list[str]):
    sql = """
    SELECT
        stock_id,
        MAX(COALESCE(close_price, 0)) AS prev_close,
        MAX(COALESCE(amount, 0)) AS prev_day_amount
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1
      AND stock_id = ANY($2::varchar[])
    GROUP BY stock_id
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value, stock_ids)
    result = {}
    for row in rows:
        payload = dict(row)
        for alias in _stock_id_aliases(str(row["stock_id"])):
            result[alias] = payload
    return result


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS pre_market_auction_snapshot (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id TEXT NOT NULL,
        stock_name TEXT NOT NULL DEFAULT '',
        subject_key TEXT NOT NULL DEFAULT '',
        theme_name TEXT NOT NULL DEFAULT '',
        role_label TEXT NOT NULL DEFAULT '',
        window_start_time TEXT NOT NULL DEFAULT '09:20:00',
        window_end_time TEXT NOT NULL DEFAULT '09:25:00',
        last_minute_start_time TEXT NOT NULL DEFAULT '09:24:00',
        last_30s_start_time TEXT NOT NULL DEFAULT '09:24:30',
        auction_open_price NUMERIC(12,4) NOT NULL DEFAULT 0,
        pre_close NUMERIC(12,4) NOT NULL DEFAULT 0,
        auction_open_pct NUMERIC(8,4) NOT NULL DEFAULT 0,
        auction_volume NUMERIC(18,2) NOT NULL DEFAULT 0,
        auction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
        last_minute_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
        last_minute_ratio NUMERIC(8,4) NOT NULL DEFAULT 0,
        prev_day_max_intraday_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
        carry_ratio NUMERIC(8,4) NOT NULL DEFAULT 0,
        price_path_stability_score NUMERIC(8,4) NOT NULL DEFAULT 0,
        is_red_zone BOOLEAN NOT NULL DEFAULT FALSE,
        has_end_spike BOOLEAN NOT NULL DEFAULT FALSE,
        has_end_drop BOOLEAN NOT NULL DEFAULT FALSE,
        shape_features JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type TEXT NOT NULL DEFAULT 'p3.phase3.auction_snapshot',
        source_trace_id TEXT NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version TEXT NOT NULL DEFAULT 'auction_snapshot.v1',
        rule_version TEXT NOT NULL DEFAULT 'auction_snapshot.v1',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_pre_market_auction_snapshot UNIQUE (trade_date, stock_id)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute(
            "ALTER TABLE pre_market_auction_snapshot ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        )


async def upsert_rows(manager: PostgresDatabaseManager, items):
    sql = """
    INSERT INTO pre_market_auction_snapshot (
        trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
        window_start_time, window_end_time, last_minute_start_time, last_30s_start_time,
        auction_open_price, pre_close, auction_open_pct, auction_volume, auction_amount,
        last_minute_amount, last_minute_ratio, prev_day_max_intraday_amount, carry_ratio,
        price_path_stability_score, is_red_zone, has_end_spike, has_end_drop, shape_features,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5, $6,
        $7, $8, $9, $10,
        $11, $12, $13, $14, $15,
        $16, $17, $18, $19,
        $20, $21, $22, $23, $24::jsonb,
        $25, $26, $27::jsonb, $28, $29
    )
    ON CONFLICT (trade_date, stock_id)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        subject_key = EXCLUDED.subject_key,
        theme_name = EXCLUDED.theme_name,
        role_label = EXCLUDED.role_label,
        window_start_time = EXCLUDED.window_start_time,
        window_end_time = EXCLUDED.window_end_time,
        last_minute_start_time = EXCLUDED.last_minute_start_time,
        last_30s_start_time = EXCLUDED.last_30s_start_time,
        auction_open_price = EXCLUDED.auction_open_price,
        pre_close = EXCLUDED.pre_close,
        auction_open_pct = EXCLUDED.auction_open_pct,
        auction_volume = EXCLUDED.auction_volume,
        auction_amount = EXCLUDED.auction_amount,
        last_minute_amount = EXCLUDED.last_minute_amount,
        last_minute_ratio = EXCLUDED.last_minute_ratio,
        prev_day_max_intraday_amount = EXCLUDED.prev_day_max_intraday_amount,
        carry_ratio = EXCLUDED.carry_ratio,
        price_path_stability_score = EXCLUDED.price_path_stability_score,
        is_red_zone = EXCLUDED.is_red_zone,
        has_end_spike = EXCLUDED.has_end_spike,
        has_end_drop = EXCLUDED.has_end_drop,
        shape_features = EXCLUDED.shape_features,
        source_type = EXCLUDED.source_type,
        source_trace_id = EXCLUDED.source_trace_id,
        source_trace = EXCLUDED.source_trace,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    payload = [
        (
            _parse_trade_date(item.trade_date),
            item.stock_id,
            item.stock_name,
            item.subject_key,
            item.theme_name,
            item.role_label,
            item.window_start_time,
            item.window_end_time,
            item.last_minute_start_time,
            item.last_30s_start_time,
            item.auction_open_price,
            item.pre_close,
            item.auction_open_pct,
            item.auction_volume,
            item.auction_amount,
            item.last_minute_amount,
            item.last_minute_ratio,
            item.prev_day_max_intraday_amount,
            item.carry_ratio,
            item.price_path_stability_score,
            item.is_red_zone,
            item.has_end_spike,
            item.has_end_drop,
            json.dumps(item.shape_features, ensure_ascii=False),
            item.source_type,
            item.source_trace_id,
            json.dumps(item.source_trace, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )
        for item in items
    ]
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, payload)


async def main_async(args: argparse.Namespace | None = None, *, db_manager: Any = None) -> int:
    if args is None:
        args = parse_args()
    trade_date_value = _parse_trade_date(args.trade_date)
    manager = db_manager if db_manager else PostgresDatabaseManager(get_postgres_config())
    if not db_manager:
        await manager.connect()
    try:
        await ensure_tables(manager)
        timeline_map = _load_timeline_map(args.timeline_json)
        if args.universe_source == "weak_to_strong_candidates":
            universe = await fetch_weak_to_strong_universe(manager, trade_date_value)
        else:
            universe = await fetch_watch_universe(manager, trade_date_value)
        if int(args.max_stocks or 0) > 0:
            universe = universe[: max(int(args.max_stocks), 1)]
        if not universe:
            print(f"[WARN] no universe rows for trade_date={args.trade_date} source={args.universe_source}")
            return 0

        stock_ids = sorted({str(row["stock_id"]).upper() for row in universe})
        raw_service = TushareAuctionSnapshotService(StockServiceConfig(tushare_token=args.token))
        # 离线优先：先读本地缓存；仅在显式允许时才在线拉取。
        raw_result = raw_service.load_cached_stk_auction(args.trade_date)
        raw_fetch_mode = "local_cache"
        raw_warn = ""
        if raw_result is None:
            if args.allow_online_fetch:
                raw_fetch_mode = "online_fetch"
                try:
                    raw_result = raw_service.fetch_or_cache_stk_auction(
                        args.trade_date,
                        stock_ids,
                        force_refresh=args.force_refresh,
                    )
                except Exception as exc:
                    raw_warn = f"online_fetch_failed:{type(exc).__name__}"
                    raw_result = None
            else:
                raw_warn = "no_local_cache_and_online_fetch_disabled"
        if raw_result is None:
            print(f"[WARN] no raw auction data for trade_date={args.trade_date}; snapshot_rows=0")
            if raw_warn:
                print(f"[WARN] raw_warn={raw_warn}")
            return 2
        raw_map = {}
        builder = AuctionSnapshotBuilderService()
        for record in raw_result.records:
            parsed = builder.parse_tushare_auction_record(record)
            for alias in _stock_id_aliases(parsed.stock_id):
                raw_map[alias] = parsed

        prev_trade_date = await fetch_prev_trade_date(manager, trade_date_value)
        if prev_trade_date is None:
            raise RuntimeError(f"无法找到 {trade_date_value} 的上一交易日，终止构建 pre_market_auction_snapshot")
        prev_day_context = await fetch_prev_day_context(manager, prev_trade_date, stock_ids)
        items = []
        for row in universe:
            stock_id = str(row["stock_id"]).upper()
            parsed = None
            for alias in _stock_id_aliases(stock_id):
                parsed = raw_map.get(alias)
                if parsed:
                    break
            if not parsed:
                continue
            prev = {}
            for alias in _stock_id_aliases(stock_id):
                prev = prev_day_context.get(alias, {})
                if prev:
                    break
            prev_day_amount = float(prev.get("prev_day_amount") or 0.0)
            prev_day_proxy = round(prev_day_amount * float(args.proxy_ratio), 2)
            candidate = AuctionCandidateInput(
                trade_date=args.trade_date,
                stock_id=stock_id,
                stock_name=row["stock_name"],
                subject_key=str(row["subject_key"]),
                theme_name=row["theme_name"],
                role_label=row["role_label"],
                mainline_alive=bool(row.get("mainline_alive")),
                action_bias=row["action_bias"],
                is_reversal_watch=bool(row["is_reversal_watch"]),
            )
            timeline_points = None
            for alias in _stock_id_aliases(stock_id):
                timeline_rows = timeline_map.get(alias)
                if timeline_rows:
                    timeline_points = builder.parse_timeline_points(list(timeline_rows))
                    if timeline_points:
                        break
            if timeline_points:
                items.append(
                    builder.build_timeline_enhanced_snapshot(
                        candidate,
                        parsed,
                        timeline_points=timeline_points,
                        prev_day_close=float(prev.get("prev_close") or 0.0),
                        prev_day_max_intraday_amount_proxy=prev_day_proxy,
                    )
                )
            else:
                items.append(
                    builder.build_single_point_snapshot(
                        candidate,
                        parsed,
                        prev_day_close=float(prev.get("prev_close") or 0.0),
                        prev_day_max_intraday_amount_proxy=prev_day_proxy,
                    )
                )

        await upsert_rows(manager, items)
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] universe_source={args.universe_source}")
        print(f"[OK] max_stocks={int(args.max_stocks or 0)}")
        print(f"[OK] raw_fetch_mode={raw_fetch_mode}")
        print(f"[OK] raw_cache_hit={raw_result.cache_hit}")
        print(f"[OK] raw_snapshot_path={raw_result.snapshot_path}")
        print(f"[OK] raw_row_count={raw_result.row_count}")
        if raw_warn:
            print(f"[WARN] {raw_warn}")
        print(f"[OK] timeline_matches={sum(1 for item in items if 'timeline_enhanced' in item.shape_features)}")
        print(f"[OK] snapshot_rows={len(items)}")
        for item in items[: args.top_k]:
            print(
                f"[ROW] theme={item.theme_name} stock={item.stock_name} role={item.role_label} "
                f"open_pct={item.auction_open_pct:.2f} carry={item.carry_ratio:.2f} "
                f"stability={item.price_path_stability_score:.2f}"
            )
        return 0
    finally:
        if not db_manager:
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

"""Diagnostic: verify tables/columns/data for get_subject_event_stats and dual-run test.

Usage:
  RUN_REPLAY_DB=1 python -m stock_processing_service.tests.replay._diag_event_stats \
    --trade-dates 2026-04-07,2026-04-15
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway


async def _get_test_gateway() -> DatabaseGateway:
    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.postgres_ssl_mode = os.getenv("PG_SSL_MODE", "prefer")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    old = DatabaseGateway._instance
    if old is not None and getattr(old, "_client", None) is not None:
        try:
            await old._client.close()
        except Exception:
            pass
    DatabaseGateway._instance = None
    DatabaseGateway._client = None
    DatabaseGateway._initialized = False
    return await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)


async def main() -> None:
    trade_dates_str = "2026-04-07,2026-04-15"
    for arg in sys.argv[1:]:
        if arg.startswith("--trade-dates="):
            trade_dates_str = arg.split("=", 1)[1]
    trade_dates = [date.fromisoformat(s.strip()) for s in trade_dates_str.split(",")]

    print("Connecting to database...")
    gateway = await _get_test_gateway()
    client = gateway._client
    print("Connected.\n")

    async with client.pool.acquire() as conn:
        # 1. Check tables exist
        print("=== Table existence ===")
        for tbl in ["news_event", "event_theme_map", "theme_master",
                     "subject_stock_daily_snapshot", "theme_mainline_identity_registry"]:
            row = await conn.fetchrow(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1) AS exists",
                tbl,
            )
            print(f"  {tbl}: {'EXISTS' if row and row['exists'] else 'MISSING'}")

        # 2. Column check on news_event
        print("\n=== news_event columns ===")
        cols = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'news_event' ORDER BY ordinal_position"
        )
        for c in cols:
            print(f"  {c['column_name']}: {c['data_type']}")

        # 3. Column check on event_theme_map
        print("\n=== event_theme_map columns ===")
        cols = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'event_theme_map' ORDER BY ordinal_position"
        )
        for c in cols:
            print(f"  {c['column_name']}: {c['data_type']}")

        # 4. Column check on theme_master
        print("\n=== theme_master columns ===")
        cols = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'theme_master' ORDER BY ordinal_position"
        )
        for c in cols:
            print(f"  {c['column_name']}: {c['data_type']}")

        # 5. Row counts
        print("\n=== Row counts ===")
        for tbl in ["news_event", "event_theme_map", "theme_master",
                     "subject_stock_daily_snapshot"]:
            row = await conn.fetchrow(f"SELECT COUNT(*) AS cnt FROM {tbl}")
            print(f"  {tbl}: {row['cnt'] if row else 'ERROR'}")

        # 6. Check news_event jyhf_history data
        print("\n=== news_event jyhf_history sample ===")
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM news_event WHERE theme_directive->>'jyhf_source_type' = 'jyhf_history'"
            )
            print(f"  jyhf_history events: {row['cnt'] if row else 'ERROR'}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 7. Check event_theme_map joinable data
        print("\n=== event_theme_map + theme_master join test ===")
        try:
            row = await conn.fetchrow("""
                SELECT COUNT(*) AS cnt
                FROM news_event ne
                JOIN event_theme_map etm ON etm.event_id = ne.id
                JOIN theme_master tm ON tm.id = etm.theme_id
                WHERE ne.theme_directive->>'jyhf_source_type' = 'jyhf_history'
                  AND tm.source_system = 'jyhf'
                  AND tm.source_id IS NOT NULL
            """)
            print(f"  Joinable events: {row['cnt'] if row else 'ERROR'}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 8. Check data for target dates
        print("\n=== Data availability for target dates ===")
        for td in trade_dates:
            print(f"\n--- {td.isoformat()} ---")

            # Pool data
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM subject_stock_daily_snapshot WHERE trade_date = $1::date",
                td,
            )
            pool_cnt = row['cnt'] if row else 0
            print(f"  subject_stock_daily_snapshot rows: {pool_cnt}")

            # Subject keys for this date
            if pool_cnt > 0:
                subjects = await conn.fetch(
                    "SELECT DISTINCT subject_key FROM subject_stock_daily_snapshot WHERE trade_date = $1::date ORDER BY subject_key",
                    td,
                )
                subject_keys = [s['subject_key'] for s in subjects]
                print(f"  Unique subject_keys ({len(subject_keys)}): {subject_keys}")

                # Event stats for these subjects
                from datetime import timedelta
                start_date = td - timedelta(days=6)
                try:
                    event_rows = await conn.fetch("""
                        SELECT
                            tm.source_id AS subject_key,
                            MAX(tm.name) AS theme_name,
                            COUNT(*) FILTER (WHERE ne.event_time::date = $1::date) AS today_event_count,
                            COUNT(*) AS recent_event_count,
                            COUNT(DISTINCT ne.event_time::date) AS distinct_event_days
                        FROM news_event ne
                        JOIN event_theme_map etm ON etm.event_id = ne.id
                        JOIN theme_master tm ON tm.id = etm.theme_id
                        WHERE ne.theme_directive->>'jyhf_source_type' = 'jyhf_history'
                          AND tm.source_system = 'jyhf'
                          AND tm.source_id IS NOT NULL
                          AND tm.source_id = ANY($2::text[])
                          AND ne.event_time::date BETWEEN $3::date AND $1::date
                        GROUP BY tm.source_id
                        ORDER BY tm.source_id
                    """, td, subject_keys, start_date)
                    print(f"  Event stats rows: {len(event_rows)}")
                    for er in event_rows:
                        print(f"    {dict(er)}")
                except Exception as e:
                    print(f"  Event stats ERROR: {e}")

            # Existing identity data
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM theme_mainline_identity_registry WHERE trade_date = $1",
                td.isoformat(),
            )
            print(f"  Existing identity_registry rows: {row['cnt'] if row else 0}")

    await gateway.close()
    print("\nDone.")


if __name__ == "__main__":
    if os.getenv("RUN_REPLAY_DB", "0") != "1":
        print("Set RUN_REPLAY_DB=1 to enable real DB access.")
        sys.exit(1)
    asyncio.run(main())

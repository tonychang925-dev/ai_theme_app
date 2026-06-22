#!/usr/bin/env python3
"""M3b: Seed / update market_data_source_registry with governance config.

Usage:
    python -m stock_processing_service.scripts.seed_market_data_source_registry
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import asyncpg

REGISTRY_SEEDS = [
    {
        "source_name": "ths",
        "endpoint_key": "ths_hot_reason",
        "domain": "hot_reason",
        "owned_fields": ["reason_raw", "reason_tags", "hot_stock_list"],
        "usage": "盘后热点归因：涨停股题材reason标签，用于热点矩阵归因和主题解释",
        "fallback_order": 20,
        "rate_limit_policy": {
            "type": "simple",
            "min_interval_ms": 500,
            "jitter_ms": 100,
            "max_retries": 2,
            "backoff": "linear",
            "timeout_ms": 10000,
        },
        "auth_type": "none",
        "freshness_sla": "T+0 post-market after 15:30 CN",
        "raw_snapshot_required": True,
        "enabled": True,
    },
    {
        "source_name": "eastmoney",
        "endpoint_key": "eastmoney_concept_blocks",
        "domain": "concept_blocks",
        "owned_fields": ["concept_blocks", "industry_blocks", "region_blocks"],
        "usage": "股票-题材静态/半动态补证据：概念/行业/地域板块归属",
        "fallback_order": 40,
        "rate_limit_policy": {
            "type": "conservative",
            "min_interval_ms": 1000,
            "jitter_ms": 300,
            "max_retries": 1,
            "backoff": "linear",
            "timeout_ms": 15000,
            "session_reuse": True,
        },
        "auth_type": "none",
        "freshness_sla": "T+0 post-market after 16:00 CN",
        "raw_snapshot_required": True,
        "enabled": False,  # enable after API connectivity confirmed
    },
    {
        "source_name": "cninfo",
        "endpoint_key": "cninfo_announcements",
        "domain": "announcements",
        "owned_fields": ["announcement_title", "announcement_type", "pdf_url"],
        "usage": "事件驱动公告证据：重大合同/业绩预告/资产重组等，服务 event_theme_map 与主题发现",
        "fallback_order": 30,
        "rate_limit_policy": {
            "type": "conservative",
            "min_interval_ms": 1000,
            "jitter_ms": 300,
            "max_retries": 1,
            "backoff": "linear",
            "timeout_ms": 20000,
        },
        "auth_type": "none",
        "freshness_sla": "T+0 post-market after 16:00 CN",
        "raw_snapshot_required": True,
        "enabled": True,
    },
]

UPSERT_SQL = """
INSERT INTO market_data_source_registry (
    source_name, endpoint_key, domain, owned_fields, usage,
    fallback_order, rate_limit_policy, auth_type, freshness_sla,
    raw_snapshot_required, enabled, updated_at
) VALUES (
    $1, $2, $3, $4::jsonb, $5,
    $6, $7::jsonb, $8, $9,
    $10, $11, NOW()
)
ON CONFLICT (source_name, endpoint_key) DO UPDATE SET
    domain = EXCLUDED.domain,
    owned_fields = EXCLUDED.owned_fields,
    usage = EXCLUDED.usage,
    fallback_order = EXCLUDED.fallback_order,
    rate_limit_policy = EXCLUDED.rate_limit_policy,
    auth_type = EXCLUDED.auth_type,
    freshness_sla = EXCLUDED.freshness_sla,
    raw_snapshot_required = EXCLUDED.raw_snapshot_required,
    enabled = EXCLUDED.enabled,
    updated_at = NOW()
"""


async def main() -> None:
    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/stock_data_test",
    )
    conn = await asyncpg.connect(dsn)
    try:
        # Ensure table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS market_data_source_registry (
                source_name VARCHAR(64) NOT NULL,
                endpoint_key VARCHAR(128) NOT NULL,
                domain VARCHAR(64) NOT NULL,
                owned_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
                fallback_order INTEGER NOT NULL DEFAULT 100,
                rate_limit_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
                auth_type VARCHAR(32) NOT NULL DEFAULT 'none',
                freshness_sla VARCHAR(64),
                raw_snapshot_required BOOLEAN NOT NULL DEFAULT true,
                enabled BOOLEAN NOT NULL DEFAULT true,
                usage TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (source_name, endpoint_key)
            )
        """)
        import json as _json

        for seed in REGISTRY_SEEDS:
            await conn.execute(
                UPSERT_SQL,
                seed["source_name"],
                seed["endpoint_key"],
                seed["domain"],
                _json.dumps(seed["owned_fields"]),
                seed.get("usage"),
                seed.get("fallback_order", 100),
                _json.dumps(seed["rate_limit_policy"]),
                seed.get("auth_type", "none"),
                seed.get("freshness_sla"),
                seed.get("raw_snapshot_required", True),
                seed.get("enabled", True),
            )
            print(f"✅ {seed['source_name']}/{seed['endpoint_key']} seeded")

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM market_data_source_registry"
        )
        print(f"Registry: {count} total entries")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
导入 JYHF 子题材个股入选理由到数据库。

数据来源: cdp_jyhf_collector.py 的 extract_child_stock_reasons() 输出。
表: subject_child_stock_reason
用法:
  python import_child_stock_reasons.py --jsonl child_reasons.jsonl
  python import_child_stock_reasons.py --cdp --subject 9035331
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncpg


DDL = """
CREATE TABLE IF NOT EXISTS subject_child_stock_reason (
    id BIGSERIAL PRIMARY KEY,
    subject_key VARCHAR(80) NOT NULL,
    child_name VARCHAR(50),
    child_full_name VARCHAR(200),
    stock_id VARCHAR(10) NOT NULL,
    stock_name VARCHAR(100),
    reason TEXT,
    sort_order INTEGER DEFAULT 0,
    source_type VARCHAR(50) DEFAULT 'cdp_dom',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_child_stock UNIQUE (subject_key, child_name, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_scsr_subject ON subject_child_stock_reason(subject_key);
CREATE INDEX IF NOT EXISTS idx_scsr_stock ON subject_child_stock_reason(stock_id);
"""


async def ensure_table():
    conn = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        await conn.execute(DDL)
        print("[OK] Table subject_child_stock_reason ensured")
    finally:
        await conn.close()


async def import_jsonl(jsonl_path: str) -> int:
    """Import child stock reasons from JSONL file."""
    path = Path(jsonl_path)
    if not path.exists():
        print(f"[ERROR] File not found: {jsonl_path}")
        return 0

    conn = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        await conn.execute(DDL)

        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        count = 0
        for r in rows:
            await conn.execute("""
                INSERT INTO subject_child_stock_reason
                    (subject_key, child_name, child_full_name, stock_id, stock_name, reason, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (subject_key, child_name, stock_id)
                DO UPDATE SET
                    reason = EXCLUDED.reason,
                    sort_order = EXCLUDED.sort_order,
                    updated_at = NOW()
            """,
                r.get("subject_key", ""),
                r.get("child_name", ""),
                r.get("child_full_name", ""),
                r.get("stock_id", ""),
                r.get("stock_name", ""),
                r.get("reason", ""),
                r.get("sort_order", 0),
            )
            count += 1

        print(f"[OK] Imported {count} child-stock reasons")
        return count
    finally:
        await conn.close()


async def import_from_cdp(subject_id: str):
    """Use CDP collector to extract and import child stock reasons."""
    # This requires JYHF app to be running with CDP enabled
    from cdp_jyhf_collector import CDPClient, extract_child_stock_reasons

    cdp = CDPClient()
    try:
        cdp.connect()
        print(f"[CDP] Connected to JYHF app")

        items = extract_child_stock_reasons(cdp, subject_id)
        if not items:
            print("[WARN] No child-stock reasons extracted")
            return

        # Save to JSONL first
        output_dir = PROJECT_ROOT / "theme_data_complete" / "child_stock_reasons"
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = output_dir / f"{subject_id}_child_stock_reasons.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"[SAVE] {len(items)} items -> {jsonl_path}")

        # Import to DB
        await import_jsonl(str(jsonl_path))
    finally:
        cdp.close()


async def main():
    parser = argparse.ArgumentParser(description="Import JYHF child stock reasons to DB")
    parser.add_argument("--jsonl", help="JSONL file with child stock reasons")
    parser.add_argument("--cdp", action="store_true", help="Use CDP to extract live data")
    parser.add_argument("--subject", help="Subject ID for CDP extraction")
    args = parser.parse_args()

    await ensure_table()

    if args.cdp and args.subject:
        await import_from_cdp(args.subject)
    elif args.jsonl:
        await import_jsonl(args.jsonl)
    else:
        print("Usage: --jsonl <file> | --cdp --subject <id>")
        # Demo: show example data
        print("\nExample JSONL format:")
        print(json.dumps({
            "subject_key": "9035331",
            "child_name": "参股",
            "child_full_name": "本源量子-参股",
            "stock_id": "002029",
            "stock_name": "七匹狼",
            "reason": "持股第7",
            "sort_order": 1
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
CDP 批量抓取 JYHF 所有题材的子题材个股入选理由。

从 subject_children_staging 获取所有有 children 的 subject，
逐个导航到详情页，提取 children + per-stock reasons，
存储到 subject_child_stock_reason 表。

用法:
  python batch_extract_child_stock_reasons.py
  python batch_extract_child_stock_reasons.py --start-from 9035331   # 断点续跑
  python batch_extract_child_stock_reasons.py --limit 10              # 测试模式
  python batch_extract_child_stock_reasons.py --import-db             # 逐条入库
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncpg
from cdp_jyhf_collector import (
    CDPClient, ensure_app_running, extract_child_stock_reasons
)

OUTPUT_DIR = PROJECT_ROOT / "theme_data_complete" / "child_stock_reasons"
STATE_FILE = OUTPUT_DIR / "_batch_state.json"
BATCH_SIZE = 20  # 每20个暂停一下，避免内存问题


async def load_subject_queue(start_from: Optional[str] = None) -> list[str]:
    """从 subject_children_staging 表加载待处理的 subject_key 列表。"""
    conn = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        # 从数据库获取有 children 的 subject
        rows = await conn.fetch("""
            SELECT DISTINCT scs.parent_subject_key,
                   tgp.concept AS subject_name,
                   COUNT(*) AS child_count
            FROM subject_children_staging scs
            LEFT JOIN theme_gate_profile tgp ON tgp.subject_key = scs.parent_subject_key
            WHERE scs.lead_stock_id IS NOT NULL AND scs.lead_stock_id != ''
            GROUP BY scs.parent_subject_key, tgp.concept
            ORDER BY scs.parent_subject_key
        """)
        subjects = [r['parent_subject_key'] for r in rows]
        print(f"[QUEUE] {len(subjects)} subjects with children loaded from DB")

        if start_from and start_from in subjects:
            idx = subjects.index(start_from)
            subjects = subjects[idx:]
            print(f"[QUEUE] Resuming from {start_from}, {len(subjects)} remaining")

        return subjects
    finally:
        await conn.close()


def load_state() -> dict:
    """Load batch processing state (for resume)."""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"completed": [], "last_subject": None, "total": 0, "errors": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


async def import_to_db(items: list[dict]) -> int:
    """Import extracted items into subject_child_stock_reason table."""
    if not items:
        return 0
    conn = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        count = 0
        for item in items:
            await conn.execute("""
                INSERT INTO subject_child_stock_reason
                    (subject_key, child_name, child_full_name, stock_id, stock_name, reason, sort_order, source_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'cdp_dom_batch')
                ON CONFLICT (subject_key, child_name, stock_id)
                DO UPDATE SET
                    reason = EXCLUDED.reason,
                    sort_order = EXCLUDED.sort_order,
                    source_type = 'cdp_dom_batch',
                    updated_at = NOW()
            """,
                item.get("subject_key", ""),
                item.get("child_name", ""),
                item.get("child_full_name", ""),
                item.get("stock_id", ""),
                item.get("stock_name", ""),
                item.get("reason", ""),
                item.get("sort_order", 0),
            )
            count += 1
        return count
    finally:
        await conn.close()


async def process_subject(cdp: CDPClient, subject_key: str, import_db: bool = False) -> dict:
    """Process a single subject: extract child stock reasons and optionally import."""
    result = {"subject_key": subject_key, "status": "ok", "items": 0}
    try:
        items = extract_child_stock_reasons(cdp, subject_key)
        if items:
            # Save to JSONL
            jsonl_path = OUTPUT_DIR / f"{subject_key}_child_stock_reasons.jsonl"
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

            if import_db:
                imported = await import_to_db(items)
                print(f"     [DB] {imported} rows imported")

            result["items"] = len(items)
            print(f"     [OK] {len(items)} child-stock reasons")
        else:
            print(f"     [EMPTY] No child-stock reasons found")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        print(f"     [ERROR] {e}")
    return result


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch extract JYHF child stock reasons")
    parser.add_argument("--start-from", help="Resume from a specific subject_key")
    parser.add_argument("--limit", type=int, default=0, help="Limit subjects (0=all)")
    parser.add_argument("--import-db", action="store_true", help="Import to DB as we go")
    parser.add_argument("--skip-launch", action="store_true", help="Assume JYHF app already running")
    args = parser.parse_args()

    # Step 1: Load queue from DB
    queue = await load_subject_queue(args.start_from)
    if args.limit > 0:
        queue = queue[:args.limit]

    state = load_state()
    # Remove already-completed subjects from queue
    completed_set = set(state.get("completed", []))
    queue = [s for s in queue if s not in completed_set]

    if not queue:
        print("[DONE] All subjects already processed")
        return

    print(f"[START] {len(queue)} subjects to process")
    print(f"[STATE] {len(completed_set)} already completed")

    # Step 2: Ensure JYHF app is running
    if not args.skip_launch:
        ensure_app_running()

    # Step 3: Connect CDP
    cdp = CDPClient()
    cdp.connect()
    print(f"[CDP] Connected to JYHF app")

    # Step 4: Batch process
    total_processed = 0
    total_items = 0
    errors = []
    start_time = time.time()

    try:
        for i, subject_key in enumerate(queue):
            elapsed = time.time() - start_time
            rate = (i + 1) / (elapsed / 60) if elapsed > 0 else 0
            eta = (len(queue) - i - 1) / rate if rate > 0 else 0
            print(f"\n[{i+1}/{len(queue)}] {subject_key} "
                  f"(rate={rate:.1f}/min ETA={eta:.0f}min)")

            result = await process_subject(cdp, subject_key, import_db=args.import_db)

            total_processed += 1
            total_items += result.get("items", 0)
            state["completed"].append(subject_key)
            state["last_subject"] = subject_key
            state["total"] = total_processed

            if result["status"] == "error":
                errors.append(subject_key)
                state["errors"].append({"subject_key": subject_key, "error": result.get("error", "")})

            # Save state periodically
            if (i + 1) % BATCH_SIZE == 0:
                save_state(state)
                print(f"\n[CHECKPOINT] {total_processed} done, {total_items} total items, "
                      f"{len(errors)} errors")

            # Small delay to avoid overwhelming the app
            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n[INTERRUPT] Progress saved. Resume with --start-from {state['last_subject']}")
    finally:
        cdp.close()
        save_state(state)

    # Final summary
    total_elapsed = (time.time() - start_time) / 60
    print(f"\n{'='*60}")
    print(f"[DONE] {total_processed} subjects processed in {total_elapsed:.1f}min")
    print(f"       {total_items} total child-stock reasons extracted")
    print(f"       {len(errors)} errors: {errors[:10]}")
    print(f"       State saved to {STATE_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

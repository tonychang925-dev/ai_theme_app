"""一次性将旧架构中的存量主线批量注册到 mainline_registry。

数据来源：
  - theme_mainline_identity_registry (旧架构已确认真源)
  - subject_history_staging (CDP DOM 管线)
  - strong_stock_watch_history (强势池实盘验证)

写入策略：UPSERT（mainline_id 冲突时更新 related/branch keys）。

用法：
  python scripts/legacy_mainline_registry_backfill.py [--dry-run] [--trade-date 2026-05-29]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg

logger = logging.getLogger(__name__)

# ── 存量主线定义 ──
# 每个条目：canonical_subject_key + mainline_name + 关联/分支题材。
# related_subject_keys: 同主线不同名称/子领域的题材
# branch_subject_keys: 更细分的分支题材

LEGACY_MAINLINES: list[dict] = [
    {
        "canonical_subject_key": "9019807",
        "mainline_name": "商业航天",
        "mainline_type": "commercial_aerospace",
        "confirmation_path": "legacy_backfill",
        "trigger_mode": "legacy_inheritance",
        "valid_from": "2026-05-01",
        "related_subject_keys": [
            "9061851",  # 商业航天8大IPO
            "9062419",  # 广州商业航天
        ],
        "branch_subject_keys": [],
        "human_notes": "旧架构 Layer B 长期确认主线；5月前已形成完整产业链叙事。从 theme_mainline_identity_registry + staging 继承注册。",
    },
    {
        "canonical_subject_key": "9013933",
        "mainline_name": "AI算力",
        "mainline_type": "ai_infrastructure",
        "confirmation_path": "legacy_backfill",
        "trigger_mode": "legacy_inheritance",
        "valid_from": "2026-05-01",
        "related_subject_keys": [
            "9017846",  # 算力租赁
            "9043938",  # AIDC绿电供应
            "9040555",  # AI一体机
        ],
        "branch_subject_keys": [
            "9014715",  # AI软件
            "9034859",  # AI智能体
            "9022152",  # AI十大应用
            "AI光纤",    # AI光纤
            "英伟达电源方案",  # 英伟达电源方案
        ],
        "human_notes": "旧架构 Layer B 长期确认主线；strong_watch 中 661 条记录。AI算力是当前最活跃的主线之一，分支涵盖算力基础设施到应用层。",
    },
    {
        "canonical_subject_key": "9015778",
        "mainline_name": "低空经济",
        "mainline_type": "low_altitude_economy",
        "confirmation_path": "legacy_backfill",
        "trigger_mode": "legacy_inheritance",
        "valid_from": "2026-05-01",
        "related_subject_keys": [
            "9025720",  # 低空经济
        ],
        "branch_subject_keys": [],
        "human_notes": "旧架构 Layer B 长期确认主线；产业政策密集，已形成完整产业链。",
    },
    {
        "canonical_subject_key": "9014636",
        "mainline_name": "机器人",
        "mainline_type": "robotics",
        "confirmation_path": "legacy_backfill",
        "trigger_mode": "legacy_inheritance",
        "valid_from": "2026-05-01",
        "related_subject_keys": [
            "9027744",  # 国内机器人
            "9036191",  # 宇树机器人
            "9041982",  # 深圳机器人
        ],
        "branch_subject_keys": [
            "9034824",  # 华为机器人
            "9036026",  # 机器人材料
            "9039041",  # 特斯拉机器人
            "9039325",  # 机器人丝杠
            "9039983",  # 云深处机器人
            "9040224",  # Figure机器人
        ],
        "human_notes": "旧架构 strong_watch 中 9 个机器人分支大量强势股。人形机器人产业在 2026 年形成主线级叙事，从 key parts 到整机全覆盖。",
    },
    {
        "canonical_subject_key": "9018144",
        "mainline_name": "PCB印制电路板",
        "mainline_type": "pcb_manufacturing",
        "confirmation_path": "legacy_backfill",
        "trigger_mode": "legacy_inheritance",
        "valid_from": "2026-05-01",
        "related_subject_keys": [
            "AI六大短缺硬件-PCB钻针",
            "英伟达PCB核心_Rubin_",
        ],
        "branch_subject_keys": [],
        "human_notes": "5/29 主线发现 Fast Line 候选（major_event=92）。PCB/电子布 Low-DK 在 AI 算力建设驱动下已成事实主线。",
    },
    {
        "canonical_subject_key": "9013416",
        "mainline_name": "电力运营",
        "mainline_type": "power_utility",
        "confirmation_path": "legacy_backfill",
        "trigger_mode": "legacy_inheritance",
        "valid_from": "2026-05-01",
        "related_subject_keys": [
            "电力运营-火电",
        ],
        "branch_subject_keys": [],
        "human_notes": "5/29 主线发现 Fast Line 候选（major_event=97）。电力行业利润增长 347.6%，是典型的政策+基本面双驱动主线。",
    },
]


def _build_mainline_id(canonical_sk: str, valid_from: str) -> str:
    """生成 mainline_id：ml_{canonical_sk}_{yyyymm}"""
    yyyymm = valid_from.replace("-", "")[:6]
    return f"ml_{canonical_sk}_{yyyymm}"


async def _read_existing_mainline_ids(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT mainline_id FROM mainline_registry")
    return {r["mainline_id"] for r in rows}


async def _upsert_mainline(conn: asyncpg.Connection, entry: dict, dry_run: bool = False) -> str:
    """写入或更新一条主线到 mainline_registry。"""
    mainline_id = _build_mainline_id(
        entry["canonical_subject_key"], entry["valid_from"]
    )
    source_review_id = "legacy_backfill_20260529"

    if dry_run:
        return f"[DRY RUN] {mainline_id} ({entry['mainline_name']})"

    from datetime import date as _date
    valid_from_d = _date.fromisoformat(entry["valid_from"])

    await conn.execute(
        """INSERT INTO mainline_registry (
               mainline_id, mainline_name, canonical_subject_key,
               mainline_type, confirmation_path, trigger_mode,
               identity_status, tracking_status,
               valid_from, valid_to, source_review_id,
               core_subject_keys_json, branch_subject_keys_json,
               related_subject_keys_json,
               human_reviewer, human_notes,
               last_active_date, last_review_date
           ) VALUES (
               $1, $2, $3,
               $4, $5, $6,
               'confirmed', 'active',
               $7::date, NULL, $8,
               $9::jsonb, $10::jsonb,
               $11::jsonb,
               'legacy_backfill', $12,
               CURRENT_DATE, CURRENT_DATE
           )
           ON CONFLICT (mainline_id) DO UPDATE SET
               core_subject_keys_json = EXCLUDED.core_subject_keys_json,
               branch_subject_keys_json = EXCLUDED.branch_subject_keys_json,
               related_subject_keys_json = EXCLUDED.related_subject_keys_json,
               human_notes = mainline_registry.human_notes || '; ' || EXCLUDED.human_notes,
               last_review_date = CURRENT_DATE,
               updated_at = NOW()""",
        mainline_id,
        entry["mainline_name"],
        entry["canonical_subject_key"],
        entry.get("mainline_type", "unknown"),
        entry.get("confirmation_path", "legacy_backfill"),
        entry.get("trigger_mode", "legacy_inheritance"),
        valid_from_d,
        source_review_id,
        json.dumps([entry["canonical_subject_key"]]),
        json.dumps(entry.get("branch_subject_keys", [])),
        json.dumps(entry.get("related_subject_keys", [])),
        entry.get("human_notes", ""),
    )
    return f"[OK] {mainline_id} ({entry['mainline_name']})"


async def run_backfill(trade_date_str: str, dry_run: bool = False):
    conn = await asyncpg.connect("postgresql://localhost/stock_data_test")

    # Validate all subjects exist in at least one source table
    all_sks: set[str] = set()
    for entry in LEGACY_MAINLINES:
        all_sks.add(entry["canonical_subject_key"])
        all_sks.update(entry.get("related_subject_keys", []))
        all_sks.update(entry.get("branch_subject_keys", []))

    # Check staging coverage
    staging_rows = await conn.fetch(
        """SELECT DISTINCT subject_key FROM subject_history_staging
           WHERE subject_key = ANY($1::text[])
             AND rank_date >= $2::date - 60 AND rank_date <= $2::date""",
        list(all_sks), date.fromisoformat(trade_date_str),
    )
    staging_sks = {r["subject_key"] for r in staging_rows}

    # Check strong_watch coverage
    sw_rows = await conn.fetch(
        """SELECT DISTINCT subject_key FROM strong_stock_watch_history
           WHERE subject_key = ANY($1::text[])""",
        list(all_sks),
    )
    sw_sks = {r["subject_key"] for r in sw_rows}

    print(f"Backfill {'DRY RUN' if dry_run else 'LIVE'} — {len(LEGACY_MAINLINES)} mainlines, {len(all_sks)} unique subject_keys")
    print(f"  staging coverage: {len(staging_sks)}/{len(all_sks)}")
    print(f"  strong_watch coverage: {len(sw_sks)}/{len(all_sks)}")
    print()

    existing_ids = await _read_existing_mainline_ids(conn)

    for entry in LEGACY_MAINLINES:
        mid = _build_mainline_id(entry["canonical_subject_key"], entry["valid_from"])
        status = "(exists, will update)" if mid in existing_ids else "(new)"
        print(f"  {status} {mid} canonical={entry['canonical_subject_key']} name={entry['mainline_name']}")

        # Coverage check
        csk = entry["canonical_subject_key"]
        if csk not in staging_sks and csk not in sw_sks:
            print(f"    ⚠ canonical key '{csk}' NOT found in staging or strong_watch — may be orphan")
        for rsk in entry.get("related_subject_keys", []):
            if rsk not in staging_sks and rsk not in sw_sks:
                print(f"    ⚠ related key '{rsk}' NOT found in staging or strong_watch")
        for bsk in entry.get("branch_subject_keys", []):
            if bsk not in staging_sks and bsk not in sw_sks:
                print(f"    ⚠ branch key '{bsk}' NOT found in staging or strong_watch")

        result = await _upsert_mainline(conn, entry, dry_run=dry_run)
        if not dry_run:
            print(f"    {result}")

    if not dry_run:
        # Verify
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM mainline_registry WHERE source_review_id = 'legacy_backfill_20260529'"
        )
        total_active = await conn.fetchval(
            f"""SELECT COUNT(*) FROM mainline_registry
                WHERE identity_status = 'confirmed'
                  AND tracking_status = 'active'
                  AND valid_from <= $1::date
                  AND (valid_to IS NULL OR valid_to >= $1::date)""",
            date.fromisoformat(trade_date_str),
        )
        print(f"\nBackfill complete. {count} legacy entries written. Total active mainlines for {trade_date_str}: {total_active}")

    await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Legacy Mainline Registry Backfill")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入")
    parser.add_argument("--trade-date", default="2026-05-29", help="基准交易日（默认 2026-05-29）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(run_backfill(args.trade_date, dry_run=args.dry_run))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
JYHF 日常同步编排脚本。

目标：
- 每天先拉取最新题材列表
- 若发现新增题材，按现有增量链补采并导库
- 无论题材是否新增，都刷新当前题材集合的 top-history 并导入数据库
- 最后将 cursor 固定到本次 lists 批次，便于下一次继续比较
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


PROJECT_ROOT = Path(__file__).resolve().parent
TMP_DIR = PROJECT_ROOT / "tmp"
LIST_FILE = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"
MANIFEST_DIR = PROJECT_ROOT / "theme_data_complete" / "_manifests"
STATE_CURSOR = PROJECT_ROOT / "theme_data_complete" / "_state" / "sync_cursor.json"
DEFAULT_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JYHF 日常同步：新题材增量 + top-history 每日刷新")
    parser.add_argument(
        "--batch-suffix",
        default=datetime.now().strftime("%Y%m%d%H%M%S"),
        help="批次后缀，默认当前时间戳",
    )
    parser.add_argument(
        "--history-subject-limit",
        type=int,
        default=0,
        help="仅处理前 N 个题材 history，0 表示处理全部；仅用于调试或压测分批",
    )
    parser.add_argument(
        "--skip-history-refresh",
        action="store_true",
        help="跳过 top-history 刷新链，仅执行新题材增量导库",
    )
    parser.add_argument(
        "--skip-stock-refresh",
        action="store_true",
        help="跳过股票日增量采集与导库",
    )
    parser.add_argument(
        "--trade-date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="股票快照交易日，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--history-max-pages",
        type=int,
        default=20,
        help="全局 history(type=3) 增量采集最大翻页数",
    )
    parser.add_argument(
        "--backfill-history-date",
        help="按指定日期回补 history(type=3) 事件，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="只生成增量清单，不执行采集与导库",
    )
    return parser.parse_args()


def load_subject_ids_from_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    subject_ids: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            subject_id = obj.get("subjectId") or obj.get("id") or obj.get("bizKey")
            if subject_id in (None, ""):
                continue
            subject_ids.append(str(subject_id))
    return sorted(set(subject_ids))


def write_subject_file(path: Path, subject_ids: Iterable[str]) -> Path:
    values = [str(x).strip() for x in subject_ids if str(x).strip()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{x}\n" for x in values), encoding="utf-8")
    return path


def manifest_path(batch_id: str) -> Path:
    return MANIFEST_DIR / f"{batch_id}.json"


def run_command(args: list[str], env: dict[str, str] | None = None) -> None:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    cmd_str = " ".join(args)
    print(f"[RUN] {cmd_str}")
    subprocess.run(args, cwd=PROJECT_ROOT, env=merged_env, check=True)


def _to_dt(value: object) -> Optional[datetime]:
    if value in (None, "", "null"):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def latest_local_history_event_time() -> Optional[datetime]:
    latest: Optional[datetime] = None
    for path in HISTORY_DIR.glob("*_history.jsonl"):
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_dt = _to_dt(row.get("createTime")) or _to_dt(row.get("updateTime")) or _to_dt(row.get("rankDate"))
                if event_dt and (latest is None or event_dt > latest):
                    latest = event_dt
    return latest


def detect_missing_stock_subject_ids(subject_ids: list[str], trade_date: str) -> list[str]:
    missing: list[str] = []
    for subject_id in subject_ids:
        path = STOCK_DAILY_DIR / f"{subject_id}_{trade_date}_stocks.jsonl"
        if not path.exists() or path.stat().st_size == 0:
            missing.append(subject_id)
    return missing


@dataclass
class BatchNames:
    lists: str
    subjects: str
    history: str


@dataclass
class SyncPlan:
    previous_subject_count: int
    current_subject_count: int
    new_subject_ids: list[str]
    history_since_event_time: Optional[str]
    history_should_sync: bool
    stock_trade_date: str
    stock_missing_subject_ids: list[str]


def main() -> int:
    args = parse_args()
    python_bin = str(DEFAULT_PYTHON if DEFAULT_PYTHON.exists() else Path(sys.executable))
    suffix = args.batch_suffix
    batch = BatchNames(
        lists=f"jyhf_lists_{suffix}",
        subjects=f"jyhf_subjects_{suffix}",
        history=f"jyhf_history_{suffix}",
    )
    stock_batch_id = f"jyhf_stock_daily_{suffix}"
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    previous_subject_ids = load_subject_ids_from_list(LIST_FILE)
    print(f"[INFO] previous subjects={len(previous_subject_ids)}")

    run_command([python_bin, "sync_jyhf_to_local.py", "--batch-id", batch.lists])
    current_subject_ids = load_subject_ids_from_list(LIST_FILE)
    print(f"[INFO] current subjects={len(current_subject_ids)}")
    if not current_subject_ids:
        raise RuntimeError(f"lists sync finished but no subject ids found in {LIST_FILE}")

    current_subjects_file = write_subject_file(TMP_DIR / f"jyhf_current_subject_keys_{suffix}.txt", current_subject_ids)
    new_subject_ids = sorted(set(current_subject_ids) - set(previous_subject_ids))
    new_subjects_file = write_subject_file(TMP_DIR / f"jyhf_new_subject_keys_{suffix}.txt", new_subject_ids)
    latest_history_dt = latest_local_history_event_time()
    stock_missing_subject_ids = detect_missing_stock_subject_ids(current_subject_ids, args.trade_date)
    stock_missing_subjects_file = write_subject_file(
        TMP_DIR / f"jyhf_stock_missing_subject_keys_{suffix}.txt",
        stock_missing_subject_ids,
    )

    plan = SyncPlan(
        previous_subject_count=len(previous_subject_ids),
        current_subject_count=len(current_subject_ids),
        new_subject_ids=new_subject_ids,
        history_since_event_time=latest_history_dt.strftime("%Y-%m-%d %H:%M:%S") if latest_history_dt else None,
        history_should_sync=not args.skip_history_refresh,
        stock_trade_date=args.trade_date,
        stock_missing_subject_ids=stock_missing_subject_ids,
    )
    plan_path = TMP_DIR / f"jyhf_incremental_plan_{suffix}.json"
    plan_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "previous_subject_count": plan.previous_subject_count,
                "current_subject_count": plan.current_subject_count,
                "new_subject_count": len(plan.new_subject_ids),
                "new_subject_ids": plan.new_subject_ids,
                "history_since_event_time": plan.history_since_event_time,
                "history_should_sync": plan.history_should_sync,
                "stock_trade_date": plan.stock_trade_date,
                "stock_missing_subject_count": len(plan.stock_missing_subject_ids),
                "stock_missing_subject_ids": plan.stock_missing_subject_ids,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[PLAN] new_subjects={len(plan.new_subject_ids)} history_since={plan.history_since_event_time} stock_missing={len(plan.stock_missing_subject_ids)}")
    print(f"[OK] incremental plan={plan_path}")
    if args.plan_only:
        return 0

    run_command(
        [
            python_bin,
            "database_service/scripts/register_jyhf_sync_manifest.py",
            "--manifest",
            str(manifest_path(batch.lists)),
        ]
    )

    if new_subject_ids:
        print(f"[INFO] new subjects detected={len(new_subject_ids)}")
        run_command(
            [
                python_bin,
                "sync_jyhf_to_local.py",
                "--batch-id",
                batch.subjects,
                "--subjects-file",
                str(new_subjects_file),
            ]
        )
        run_command(
            [
                python_bin,
                "database_service/scripts/register_jyhf_sync_manifest.py",
                "--manifest",
                str(manifest_path(batch.subjects)),
            ]
        )

        batch_env = {"PHASE1_BATCH_ID": batch.subjects}
        run_command([python_bin, "database_service/scripts/load_subject_node_staging.py"], env=batch_env)
        run_command([python_bin, "database_service/scripts/load_theme_hierarchy_staging.py"], env=batch_env)
        run_command([python_bin, "database_service/scripts/load_subject_children_staging.py"], env=batch_env)
        run_command(
            [
                python_bin,
                "import_jyhf_to_financial_and_theme.py",
                "--subjects-file",
                str(new_subjects_file),
                "--batch-id",
                batch.subjects,
            ]
        )
        run_command(
            [
                python_bin,
                "database_service/scripts/import_jyhf_detail_incremental.py",
                "--subjects-file",
                str(new_subjects_file),
                "--batch-id",
                batch.subjects,
            ]
        )
        run_command(
            [
                python_bin,
                "database_service/scripts/import_jyhf_stock_incremental.py",
                "--subjects-file",
                str(new_subjects_file),
                "--batch-id",
                batch.subjects,
            ]
        )
    else:
        print("[INFO] no new subjects detected")

    history_subject_ids = current_subject_ids
    if args.history_subject_limit and args.history_subject_limit > 0:
        history_subject_ids = history_subject_ids[: args.history_subject_limit]
    history_subjects_file = write_subject_file(TMP_DIR / f"jyhf_history_subject_keys_{suffix}.txt", history_subject_ids)

    if not args.skip_history_refresh:
        print(f"[INFO] refreshing incremental top-history subjects={len(history_subject_ids)}")
        run_command(
            [
                python_bin,
                "sync_jyhf_to_local.py",
                "--batch-id",
                batch.history,
                "--use-latest-list-subjects",
                "--types",
                "history",
                "--history-mode",
                "incremental",
                "--history-max-pages",
                str(args.history_max_pages),
                *(
                    ["--history-backfill-date", args.backfill_history_date]
                    if args.backfill_history_date
                    else []
                ),
            ]
        )
        run_command(
            [
                python_bin,
                "database_service/scripts/import_jyhf_history_incremental.py",
                "--subjects-file",
                str(history_subjects_file),
                "--batch-id",
                batch.history,
                "--mode",
                "append",
            ]
        )
    else:
        print("[INFO] history refresh skipped by flag")

    if not args.skip_stock_refresh:
        if stock_missing_subject_ids:
            print(f"[INFO] refreshing stock daily snapshot missing_subjects={len(stock_missing_subject_ids)} trade_date={args.trade_date}")
            run_command(
                [
                    python_bin,
                    "sync_jyhf_to_local.py",
                    "--batch-id",
                    stock_batch_id,
                    "--subjects-file",
                    str(stock_missing_subjects_file),
                    "--types",
                    "stock_details",
                    "--trade-date",
                    args.trade_date,
                ]
            )
            run_command(
                [
                    python_bin,
                    "database_service/scripts/import_jyhf_stock_daily_incremental.py",
                    "--subjects-file",
                    str(stock_missing_subjects_file),
                    "--batch-id",
                    stock_batch_id,
                    "--trade-date",
                    args.trade_date,
                ]
            )
        else:
            print(f"[INFO] stock daily snapshot already complete trade_date={args.trade_date}")
    else:
        print("[INFO] stock refresh skipped by flag")

    run_command(
        [
            python_bin,
            "database_service/scripts/build_jyhf_cursor_from_manifest.py",
            "--manifest",
            str(manifest_path(batch.lists)),
            "--output",
            str(STATE_CURSOR),
        ]
    )

    summary = {
        "finished_at": datetime.now().isoformat(),
        "lists_batch_id": batch.lists,
        "subjects_batch_id": batch.subjects if new_subject_ids else None,
        "history_batch_id": None if args.skip_history_refresh else batch.history,
        "stock_batch_id": None if args.skip_stock_refresh or not stock_missing_subject_ids else stock_batch_id,
        "current_subject_count": len(current_subject_ids),
        "new_subject_count": len(new_subject_ids),
        "history_subject_count": len(history_subject_ids),
        "history_since_event_time": plan.history_since_event_time,
        "trade_date": args.trade_date,
        "current_subjects_file": str(current_subjects_file),
        "new_subjects_file": str(new_subjects_file),
        "history_subjects_file": str(history_subjects_file),
        "stock_missing_subjects_file": str(stock_missing_subjects_file),
        "stock_missing_subject_count": len(stock_missing_subject_ids),
        "lists_manifest": str(manifest_path(batch.lists)),
        "subjects_manifest": str(manifest_path(batch.subjects)) if new_subject_ids else None,
        "history_manifest": None,
        "incremental_plan": str(plan_path),
    }
    summary_path = TMP_DIR / f"jyhf_daily_sync_summary_{suffix}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] daily sync summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

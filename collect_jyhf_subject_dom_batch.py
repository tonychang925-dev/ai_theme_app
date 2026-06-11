#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SUBJECTS_FILE = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "tmp" / "jyhf_subject_dom_batch"
COLLECTOR_SCRIPT = PROJECT_ROOT / "collect_jyhf_subject_dom.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch validate JYHF subject DOM collection")
    parser.add_argument(
        "--subjects-file",
        default=str(DEFAULT_SUBJECTS_FILE),
        help="jsonl/json/txt file containing subject ids",
    )
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of subjects to collect")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N subject ids")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Directory used for the batch manifest and logs",
    )
    parser.add_argument(
        "--write-standard",
        action="store_true",
        help="Also write into theme_data_complete/details and history during each run",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately on the first failed subject",
    )
    return parser.parse_args()


def _load_subject_ids(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"subjects file not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    ids: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        sid = str(value or "").strip()
        if not sid or sid in seen:
            return
        seen.add(sid)
        ids.append(sid)

    if path.suffix.lower() == ".json":
        data = json.loads(content)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    add(item.get("subjectId") or item.get("subject_id") or item.get("id"))
                else:
                    add(item)
        return ids

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if path.suffix.lower() == ".jsonl":
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                add(line)
                continue
            if isinstance(obj, dict):
                add(obj.get("subjectId") or obj.get("subject_id") or obj.get("id"))
            else:
                add(obj)
        else:
            add(line)
    return ids


def main() -> int:
    args = parse_args()
    subjects_file = Path(args.subjects_file)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    subject_ids = _load_subject_ids(subjects_file)
    if args.offset:
        subject_ids = subject_ids[args.offset :]
    if args.limit >= 0:
        subject_ids = subject_ids[: args.limit]

    batch_id = datetime.now().strftime("jyhf_dom_batch_%Y%m%d_%H%M%S")
    manifest_path = output_root / f"{batch_id}.json"
    summary: dict[str, Any] = {
        "batch_id": batch_id,
        "subjects_file": str(subjects_file),
        "limit": args.limit,
        "offset": args.offset,
        "write_standard": args.write_standard,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "results": [],
    }

    print(f"[BATCH] subjects_file={subjects_file}")
    print(f"[BATCH] count={len(subject_ids)} output_root={output_root}")

    for index, subject_id in enumerate(subject_ids, start=1):
        print(f"[BATCH] ({index}/{len(subject_ids)}) subject_id={subject_id}")
        cmd = [
            sys.executable,
            str(COLLECTOR_SCRIPT),
            "--subject-id",
            subject_id,
        ]
        if args.write_standard:
            cmd.append("--write-standard")
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        result = {
            "subject_id": subject_id,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
        }
        summary["results"].append(result)
        if proc.returncode != 0:
            print(f"[BATCH] subject_id={subject_id} failed rc={proc.returncode}")
            if args.fail_fast:
                break

    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["ok_count"] = sum(1 for item in summary["results"] if item.get("ok"))
    summary["failed_count"] = sum(1 for item in summary["results"] if not item.get("ok"))
    manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[BATCH] manifest={manifest_path}")
    print(f"[BATCH] ok={summary['ok_count']} failed={summary['failed_count']}")
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

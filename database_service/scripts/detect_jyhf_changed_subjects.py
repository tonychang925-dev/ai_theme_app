#!/usr/bin/env python3
"""
根据本地 manifest 与 cursor，识别发生变化的 subject_key。
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CURSOR = PROJECT_ROOT / "theme_data_complete" / "_state" / "sync_cursor.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="识别久赢恒丰 changed subjects")
    parser.add_argument("--manifest", required=True, help="manifest json 路径")
    parser.add_argument("--cursor", default=str(DEFAULT_CURSOR), help="cursor json 路径")
    parser.add_argument("--output", required=True, help="输出 changed_subjects json 路径")
    return parser.parse_args()


def load_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    manifest = load_json(Path(args.manifest))
    cursor = load_json(Path(args.cursor))
    prev_files = cursor.get("files", {})

    changed_subjects: Set[str] = set()
    unchanged_subjects: Set[str] = set()
    changed_files: List[Dict] = []
    global_changed = False

    for row in manifest.get("files", []):
        file_path = row["file_path"]
        file_hash = row.get("file_hash")
        subject_key = row.get("subject_key")
        old = prev_files.get(file_path, {})
        changed = old.get("file_hash") != file_hash
        if changed:
            changed_files.append(row)
            if subject_key:
                changed_subjects.add(str(subject_key))
            else:
                global_changed = True
        elif subject_key:
            unchanged_subjects.add(str(subject_key))

    out = {
        "batch_id": manifest.get("batch_id"),
        "global_changed": global_changed,
        "changed_subjects": sorted(changed_subjects),
        "unchanged_subjects": sorted(unchanged_subjects - changed_subjects),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] changed_subjects={len(out['changed_subjects'])} global_changed={global_changed}")
    print(f"[OK] output={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

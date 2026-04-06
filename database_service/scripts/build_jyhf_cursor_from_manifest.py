#!/usr/bin/env python3
"""
从已有 manifest 回填本地 sync_cursor.json。

用途：
- 当早期批次已生成 manifest 但未成功写 cursor 时，补建 cursor
- 便于后续直接进入 changed_subjects 增量模式
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STATE_DIR = PROJECT_ROOT / "theme_data_complete" / "_state"
DEFAULT_CURSOR = DEFAULT_STATE_DIR / "sync_cursor.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 manifest 回填 JYHF cursor")
    parser.add_argument("--manifest", required=True, help="manifest json 路径")
    parser.add_argument("--output", default=str(DEFAULT_CURSOR), help="cursor 输出路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    output_path = Path(args.output)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cursor = {
        "last_batch_id": manifest.get("batch_id"),
        "updated_at": datetime.now().isoformat(),
        "files": {
            row["file_path"]: {
                "file_hash": row.get("file_hash"),
                "data_type": row.get("data_type"),
                "subject_key": row.get("subject_key"),
            }
            for row in manifest.get("files", [])
        },
    }
    output_path.write_text(json.dumps(cursor, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] cursor rebuilt from manifest: {output_path}")
    print(f"[OK] tracked_files={len(cursor['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

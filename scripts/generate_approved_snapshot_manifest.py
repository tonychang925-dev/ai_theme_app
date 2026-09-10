#!/usr/bin/env python3
"""Regenerate the Approved Snapshot runtime integrity manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_processing_service.application.services.analyst_workbench.approval_contract import (
    build_runtime_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    manifest = build_runtime_manifest(root)
    output = root / (
        "stock_processing_service/application/services/analyst_workbench/"
        "approved_snapshot_runtime_manifest.json"
    )
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

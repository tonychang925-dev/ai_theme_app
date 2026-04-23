#!/usr/bin/env python3
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGET = Path(__file__).resolve().parent / "legacy" / "analyze_shenjian_themes_0407.py"
print("[LEGACY] 脚本已迁移: scripts/legacy/analyze_shenjian_themes_0407.py")
if not TARGET.exists():
    raise SystemExit(f"legacy script missing: {TARGET}")
runpy.run_path(str(TARGET), run_name="__main__")

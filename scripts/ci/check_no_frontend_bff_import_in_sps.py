from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
SPS = ROOT / "stock_processing_service"
PATTERN = re.compile(r"^\s*(from|import)\s+frontend_bff(\.|$)")


def main() -> int:
    violations: list[str] = []
    for path in SPS.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line):
                violations.append(f"{path}:{i}: {line.strip()}")
    if violations:
        print("[FAIL] stock_processing_service must not import frontend_bff")
        for v in violations:
            print(v)
        return 1
    print("[OK] no frontend_bff imports in stock_processing_service")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

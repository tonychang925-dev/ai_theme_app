#!/usr/bin/env python3
"""Guard online command shape for dev-orchestrator.

Rejects commands that can break approval-prefix matching and channel locking.
"""

from __future__ import annotations

import argparse
import sys


FORBIDDEN_TOKENS = ("&&", "||", ";", "|", "if ", "bash -lc", "$(", "`")
ALLOWED_PREFIXES = (
    ".venv/bin/python sync_pm_status.py ",
    ".venv/bin/python scripts/accept_online_locked.py ",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", required=True, help="Command string to validate")
    args = parser.parse_args()

    cmd = args.cmd.strip()
    errors: list[str] = []

    if not any(cmd.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        errors.append(
            "command must start with one of: "
            + ", ".join(repr(p.strip()) for p in ALLOWED_PREFIXES)
        )
    for token in FORBIDDEN_TOKENS:
        if token in cmd:
            errors.append(f"forbidden token detected: {token!r}")

    if errors:
        print("❌ online command guard failed")
        for err in errors:
            print(f"- {err}")
        return 1

    print("✅ online command guard passed")
    print(f"- cmd: {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

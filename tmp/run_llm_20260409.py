import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.scripts.call_theme_leader_llm import main_async


def load_deepseek_key() -> str:
    env_path = Path("/Users/admin/Desktop/ai_theme_app/.env.theme")
    if not env_path.exists():
        return ""
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "DEEPSEEK_API_KEY":
            return value.strip().strip("\"'")
    return ""


if __name__ == "__main__":
    key = load_deepseek_key()
    if key:
        os.environ["DEEPSEEK_API_KEY"] = key
    sys.argv = [
        "call_theme_leader_llm.py",
        "--trade-date",
        "2026-04-09",
        "--limit",
        "6",
        "--limit-themes",
        "6",
        "--only-queued",
        "--only-pending",
    ]
    raise SystemExit(asyncio.run(main_async()))

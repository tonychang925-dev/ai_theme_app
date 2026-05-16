from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

FORBIDDEN_INPUT_KEYS = {
    "gold_theme_name",
    "gold_label",
    "theme_name",
    "subject_key",
    "matched_subject_key",
    "测试集题材名称",
}


def repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "evaluate_service").is_dir() and (parent / ".git").exists():
            return parent
    return current.parents[3]


def default_output_dir(run_id: str) -> Path:
    return repo_root() / "evaluate_service" / "output" / "pre_market_e2e" / run_id


def parse_trade_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} 不是合法 JSONL: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no} 必须是 JSON object")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def require_safe_db(db_name: str, allow_production: bool = False) -> None:
    if db_name == "stock_data_test" and not allow_production:
        raise SystemExit(
            "拒绝连接 DB_NAME=stock_data_test；本次 E2E 只能使用 stock_data。"
            " 如确需放行，请显式传 --allow-production。"
        )


def db_connect_kwargs(db_name: str) -> dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")),
        "port": int(os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))),
        "user": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
        "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "postgres")),
        "database": db_name,
    }


def ensure_no_gold_leak(payload: dict[str, Any], *, context: str = "payload") -> None:
    leaked = sorted(key for key in payload if key in FORBIDDEN_INPUT_KEYS)
    if leaked:
        raise ValueError(f"{context} 含离线评估字段，禁止进入程序链路: {leaked}")


def strip_for_redis(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


async def table_exists(conn: Any, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)::text", f"public.{table_name}"))


async def column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = $1
              AND column_name = $2
            LIMIT 1
            """,
            table_name,
            column_name,
        )
    )

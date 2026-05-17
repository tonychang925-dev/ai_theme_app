from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

GENERIC_TERMS = {
    "AI",
    "AR",
    "VR",
    "XR",
    "IPO",
    "APP",
    "GPT",
    "AIGC",
    "产品",
    "设备",
    "公司",
    "合作",
    "美国",
    "动力系统",
    "应用",
    "金融",
    "供应链",
    "供应商",
    "产业链",
    "参股",
    "制造",
    "生产",
    "上游",
    "下游",
    "上游合作",
    "包装",
    "包装及物流",
    "物流",
    "客户",
    "订单",
    "合作伙伴",
    "民企",
    "国企",
}

EXACT_GENERIC_TERMS = {"AI", "AR", "VR", "XR", "IPO", "APP", "GPT", "AIGC", "产品", "设备", "应用", "金融"}
CONTAINED_GENERIC_TERMS = {
    "供应链",
    "供应商",
    "产业链",
    "参股",
    "制造",
    "生产",
    "上游",
    "下游",
    "上游合作",
    "包装及物流",
    "物流",
    "客户",
    "订单",
    "合作伙伴",
    "民企",
    "国企",
    "公司",
    "合作",
}


def repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() and (parent / "theme_service").is_dir():
            return parent
    return current.parents[2]


def default_output_dir(run_id: str) -> Path:
    return repo_root() / "theme_service" / "output" / "profile_quality" / run_id


def db_connect_kwargs(db_name: str) -> dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")),
        "port": int(os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))),
        "user": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
        "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "postgres")),
        "database": db_name,
    }


def add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--read-db-name", default=os.getenv("READ_DB_NAME", os.getenv("READ_PG_DATABASE", "stock_data_test")))
    parser.add_argument("--write-db-name", default=os.getenv("WRITE_DB_NAME", os.getenv("PG_DATABASE", "stock_data")))


def safe_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def load_json(value: Any, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        parsed = load_json(stripped, None)
        if isinstance(parsed, list):
            return unique(safe_str(item) for item in parsed)
        return unique(part.strip() for part in re.split(r"[,，、\n]", stripped) if part.strip())
    if isinstance(value, dict):
        return unique(safe_str(v) for v in value.values() if safe_str(v))
    if isinstance(value, Iterable):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                out.append(safe_str(item.get("name") or item.get("text") or item.get("normalized") or item.get("claim")))
            else:
                out.append(safe_str(item))
        return unique(out)
    return []


def unique(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = safe_str(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def is_generic_term(term: str) -> bool:
    value = safe_str(term)
    if not value:
        return False
    upper = value.upper()
    if upper in EXACT_GENERIC_TERMS or value in EXACT_GENERIC_TERMS or value in CONTAINED_GENERIC_TERMS:
        return True
    return any(generic in value for generic in CONTAINED_GENERIC_TERMS if len(generic) >= 2)


def split_generic(terms: Iterable[str]) -> tuple[list[str], list[str]]:
    anchors: list[str] = []
    generic: list[str] = []
    for term in unique(terms):
        if is_generic_term(term):
            generic.append(term)
        else:
            anchors.append(term)
    return anchors, generic


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    lset = set(left)
    rset = set(right)
    if not lset or not rset:
        return 0.0
    return len(lset & rset) / len(lset | rset)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})


async def connect(db_name: str):
    import asyncpg

    return await asyncpg.connect(**db_connect_kwargs(db_name))


async def table_exists(conn: Any, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)::text", f"public.{table_name}"))


def run_async(coro):
    return asyncio.run(coro)


@dataclass
class ProfileSource:
    subject_key: str
    subject_name: str
    concept: str
    semantic_type: str
    strategy_type: str
    aliases: list[str]
    must_terms: list[str]
    strong_terms: list[str]
    should_terms: list[str]
    weak_terms: list[str]
    negative_terms: list[str]
    not_terms: list[str]
    core_anchors: list[str]
    supporting_entities: list[str]
    representative_events: list[str]
    search_text: str
    rerank_text: str
    quality: str
    stock_pool_size: int = 0
    latest_stock_trade_date: str = ""
    leaderboard_count: int = 0
    latest_leaderboard_trade_date: str = ""
    recent_event_count: int = 0

    def anchor_terms(self) -> list[str]:
        terms = [
            self.subject_name,
            self.concept,
            *self.aliases,
            *self.must_terms,
            *self.strong_terms,
            *self.core_anchors,
            *self.supporting_entities,
        ]
        anchors, _ = split_generic(terms)
        return unique(anchors)


def profile_from_row(row: dict[str, Any]) -> ProfileSource:
    ontology = load_json(row.get("ontology_json"), {})
    gate = load_json(row.get("gate_json"), {})
    aliases: list[str] = []
    for key in ("aliases", "synonyms", "alias", "same_as"):
        aliases.extend(normalize_list(ontology.get(key)))
        aliases.extend(normalize_list(gate.get(key)))
    aliases.extend([safe_str(row.get("subject_name")), safe_str(row.get("concept"))])
    return ProfileSource(
        subject_key=safe_str(row.get("subject_key")),
        subject_name=safe_str(row.get("subject_name") or row.get("concept") or row.get("subject_key")),
        concept=safe_str(row.get("concept")),
        semantic_type=safe_str(row.get("semantic_type")),
        strategy_type=safe_str(row.get("strategy_type")),
        aliases=unique(aliases),
        must_terms=normalize_list(row.get("must_terms")),
        strong_terms=normalize_list(row.get("strong_terms")),
        should_terms=normalize_list(row.get("should_terms")),
        weak_terms=normalize_list(row.get("weak_terms")),
        negative_terms=normalize_list(row.get("negative_terms")),
        not_terms=normalize_list(row.get("not_terms")),
        core_anchors=normalize_list(row.get("core_anchors")),
        supporting_entities=normalize_list(row.get("supporting_entities")),
        representative_events=normalize_list(row.get("representative_events")),
        search_text=safe_str(row.get("search_text")),
        rerank_text=safe_str(row.get("rerank_text") or row.get("embedding_text") or row.get("summary")),
        quality=safe_str(row.get("quality")),
    )

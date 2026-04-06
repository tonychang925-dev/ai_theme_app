#!/usr/bin/env python3
"""
按 subject_key 增量/精确同步久赢 detail/profile 到数据库。

处理链：
- theme_data_complete/details/*_details.jsonl -> subject_detail
- theme_data_complete/gate_cache/* -> theme_profile_ext 文本画像字段
- theme_data_complete/knowledge_from_events/* -> theme_profile_ext.representative_events
- 刷新对应 subject_key 的 theme_detail_snapshot
"""

import argparse
import asyncio
import json
import os
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.scripts.materialize_phase1_serving import ensure_tables as ensure_serving_tables

DETAILS_DIR = PROJECT_ROOT / "theme_data_complete" / "details"
GATE_CACHE_DIR = PROJECT_ROOT / "theme_data_complete" / "gate_cache"
KNOWLEDGE_EVENTS_DIR = PROJECT_ROOT / "theme_data_complete" / "knowledge_from_events"


def get_postgres_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="增量同步久赢 detail/profile -> subject_detail/theme_profile_ext/theme_detail_snapshot")
    parser.add_argument("--subjects-file", help="txt/json 文件，每行一个 subject_key；不传则处理全部 details 文件")
    parser.add_argument("--batch-id", default=None, help="同步批次 ID")
    return parser.parse_args()


def _load_subject_keys(subjects_file: Optional[str]) -> Optional[List[str]]:
    if not subjects_file:
        return None
    content = Path(subjects_file).read_text(encoding="utf-8").strip()
    if not content:
        return []
    if subjects_file.endswith(".json"):
        return [str(x) for x in json.loads(content)]
    return [line.strip() for line in content.splitlines() if line.strip()]


def _strip_html(html: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", html or ""))
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text[:n] if len(text) > n else text


def _dedup_keep_order(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _extract_detail_record(subject_key: str, path: Path) -> Dict[str, Any]:
    sid = str(subject_key)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            candidate = obj.get("data") if isinstance(obj, dict) and isinstance(obj.get("data"), dict) else obj
            if not isinstance(candidate, dict):
                continue
            maybe_id = candidate.get("subjectId") or candidate.get("subject_id") or candidate.get("bizKey") or candidate.get("id")
            if str(maybe_id) != sid:
                continue
            detail_html = candidate.get("detail") or candidate.get("detail_html") or candidate.get("content") or ""
            text = _strip_html(detail_html)
            reason_short = str(candidate.get("reason") or "").strip()
            summary = reason_short or _truncate(text, 200)
            return {
                "subject_key": sid,
                "subject_name": str(candidate.get("name") or candidate.get("subjectName") or sid).strip(),
                "detail_html": detail_html,
                "reason_short": reason_short,
                "summary": summary,
                "plain_text": text,
                "source_updated_at": candidate.get("updateTime") or candidate.get("createTime"),
                "raw": candidate,
            }
    return {
        "subject_key": sid,
        "subject_name": sid,
        "detail_html": "",
        "reason_short": "",
        "summary": "",
        "plain_text": "",
        "source_updated_at": None,
        "raw": {},
    }


def _load_gate_cache(subject_key: str) -> Tuple[List[str], List[str]]:
    core_terms: List[str] = []
    support_terms: List[str] = []
    for path in GATE_CACHE_DIR.glob(f"{subject_key}_*.json"):
        try:
            obj = json.load(path.open("r", encoding="utf-8"))
        except Exception:
            continue
        result = obj.get("result")
        if path.name.startswith(f"{subject_key}_core_anchor_") and isinstance(result, dict):
            for group in ("primary_anchor", "secondary_anchor"):
                values = result.get(group, [])
                if isinstance(values, list):
                    core_terms.extend([str(x.get("term")).strip() for x in values if isinstance(x, dict) and str(x.get("term") or "").strip()])
        elif path.name.startswith(f"{subject_key}_ontology_") and isinstance(result, dict):
            concept = str(result.get("concept") or "").strip()
            semantic_type = str(result.get("semantic_type") or "").strip()
            strategy_type = str(result.get("strategy_type") or "").strip()
            if concept:
                support_terms.append(concept)
            if semantic_type:
                support_terms.append(semantic_type)
            if strategy_type:
                support_terms.append(strategy_type)
            dimensions = result.get("dimensions") or {}
            if isinstance(dimensions, dict):
                for vals in dimensions.values():
                    if isinstance(vals, list):
                        support_terms.extend([str(v).strip() for v in vals if str(v or "").strip()])
        elif path.name.startswith(f"{subject_key}_merge_must_") and isinstance(result, list):
            core_terms.extend([str(x).strip() for x in result if str(x or "").strip()])
    return _dedup_keep_order(core_terms), _dedup_keep_order(support_terms)


def _load_representative_events(subject_key: str) -> List[Dict[str, Any]]:
    path = KNOWLEDGE_EVENTS_DIR / f"{subject_key}_knowledge_from_events.jsonl"
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            events.append(
                {
                    "title": _truncate(str(obj.get("title") or "").strip(), 200),
                    "text": _truncate(str(obj.get("text") or "").strip(), 500),
                    "source": str(obj.get("source") or "").strip(),
                    "created_at": obj.get("created_at"),
                    "uid": str(obj.get("uid") or "").strip(),
                    "order": obj.get("order"),
                }
            )
            if len(events) >= 5:
                break
    return events


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    ALTER TABLE subject_detail
    ADD COLUMN IF NOT EXISTS reason_short text;

    ALTER TABLE subject_detail
    ADD COLUMN IF NOT EXISTS is_current boolean DEFAULT true;

    CREATE TABLE IF NOT EXISTS theme_profile_ext (
        subject_key varchar(80) PRIMARY KEY,
        summary text,
        core_anchors jsonb NOT NULL DEFAULT '[]'::jsonb,
        supporting_entities jsonb NOT NULL DEFAULT '[]'::jsonb,
        representative_events jsonb NOT NULL DEFAULT '[]'::jsonb,
        embedding_text text,
        rerank_text text,
        updated_at timestamp without time zone DEFAULT now(),
        embedding vector(768)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
    await ensure_serving_tables(manager)


def iter_detail_files(subject_keys: Optional[Sequence[str]]) -> Iterable[Path]:
    if subject_keys is None:
        yield from sorted(DETAILS_DIR.glob("*_details.jsonl"))
        return
    for subject_key in subject_keys:
        path = DETAILS_DIR / f"{subject_key}_details.jsonl"
        if path.exists():
            yield path


async def sync_subjects(manager: PostgresDatabaseManager, subject_keys: Sequence[str]) -> Tuple[int, int]:
    detail_rows = []
    profile_rows = []

    for path in iter_detail_files(subject_keys):
        subject_key = path.stem.replace("_details", "")
        detail = _extract_detail_record(subject_key, path)
        core_terms, support_terms = _load_gate_cache(subject_key)
        rep_events = _load_representative_events(subject_key)

        rerank_parts = _dedup_keep_order(
            [
                detail["subject_name"],
                detail["summary"],
                *core_terms[:10],
                *support_terms[:20],
                *[evt.get("title", "") for evt in rep_events[:3]],
            ]
        )
        rerank_text = " ".join([x for x in rerank_parts if x])
        embedding_parts = _dedup_keep_order(
            [
                detail["subject_name"],
                detail["summary"],
                detail["plain_text"][:1000],
                *core_terms[:20],
                *support_terms[:40],
                *[evt.get("text", "") for evt in rep_events[:3]],
            ]
        )
        embedding_text = " ".join([x for x in embedding_parts if x])

        detail_rows.append(
            (
                detail["subject_key"],
                detail["detail_html"],
                detail["reason_short"],
            )
        )
        profile_rows.append(
            (
                detail["subject_key"],
                detail["summary"],
                json.dumps(core_terms, ensure_ascii=False),
                json.dumps(support_terms, ensure_ascii=False),
                json.dumps(rep_events, ensure_ascii=False),
                embedding_text,
                rerank_text,
            )
        )

    detail_sql = """
    INSERT INTO subject_detail (
        subject_key, detail_html, reason_short, detail_version, is_current, created_at, updated_at
    ) VALUES (
        $1, $2, $3, 1, true, NOW(), NOW()
    )
    ON CONFLICT (subject_key) DO UPDATE SET
        detail_html = EXCLUDED.detail_html,
        reason_short = EXCLUDED.reason_short,
        is_current = true,
        updated_at = NOW()
    """
    profile_sql = """
    INSERT INTO theme_profile_ext (
        subject_key, summary, core_anchors, supporting_entities,
        representative_events, embedding_text, rerank_text, updated_at
    ) VALUES (
        $1, $2, $3::jsonb, $4::jsonb,
        $5::jsonb, $6, $7, NOW()
    )
    ON CONFLICT (subject_key) DO UPDATE SET
        summary = EXCLUDED.summary,
        core_anchors = EXCLUDED.core_anchors,
        supporting_entities = EXCLUDED.supporting_entities,
        representative_events = EXCLUDED.representative_events,
        embedding_text = EXCLUDED.embedding_text,
        rerank_text = EXCLUDED.rerank_text,
        updated_at = NOW()
    """
    refresh_sql = """
    INSERT INTO theme_detail_snapshot (
        subject_key, theme_id, theme_name, snapshot_version, summary,
        detail_html, reason_short, detail_version, is_current,
        source_type, source_ref, snapshot_at
    )
    SELECT
        subject_key,
        theme_id,
        theme_name,
        COALESCE(detail_version, 1),
        summary,
        detail_html,
        reason_short,
        detail_version,
        COALESCE(is_current, TRUE),
        'subject_detail',
        ('subject_detail:' || subject_key || ':' || COALESCE(detail_version, 1)::text),
        COALESCE(detail_updated_at, NOW())
    FROM vw_theme_detail_joined
    WHERE subject_key = ANY($1::varchar[])
      AND (detail_html IS NOT NULL OR summary IS NOT NULL OR reason_short IS NOT NULL)
    ON CONFLICT (subject_key, snapshot_version)
    DO UPDATE SET
        theme_id = EXCLUDED.theme_id,
        theme_name = EXCLUDED.theme_name,
        summary = EXCLUDED.summary,
        detail_html = EXCLUDED.detail_html,
        reason_short = EXCLUDED.reason_short,
        detail_version = EXCLUDED.detail_version,
        is_current = EXCLUDED.is_current,
        source_type = EXCLUDED.source_type,
        source_ref = EXCLUDED.source_ref,
        snapshot_at = EXCLUDED.snapshot_at,
        updated_at = NOW()
    """

    async with manager.pool.acquire() as conn:
        async with conn.transaction():
            if detail_rows:
                await conn.executemany(detail_sql, detail_rows)
            if profile_rows:
                await conn.executemany(profile_sql, profile_rows)
            await conn.execute(refresh_sql, list(subject_keys))
    return len(detail_rows), len(profile_rows)


async def main() -> int:
    if not DETAILS_DIR.exists():
        print(f"[ERROR] details dir not found: {DETAILS_DIR}")
        return 1

    args = parse_args()
    batch_id = args.batch_id or "jyhf_detail_incremental"
    subject_keys = _load_subject_keys(args.subjects_file)
    if subject_keys is None:
        subject_keys = sorted({path.stem.replace("_details", "") for path in DETAILS_DIR.glob("*_details.jsonl")})

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        detail_count, profile_count = await sync_subjects(manager, subject_keys)
        print(
            f"[OK] synced detail incrementally subjects={len(subject_keys)} "
            f"detail_rows={detail_count} profile_rows={profile_count} batch_id={batch_id}"
        )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.profile_quality_common import (
    add_db_args,
    connect,
    default_output_dir,
    is_generic_term,
    jaccard,
    profile_from_row,
    run_async,
    safe_str,
    split_generic,
    table_exists,
    unique,
    write_csv,
    write_jsonl,
)


async def _load_profiles(conn: Any) -> list:
    rows = await conn.fetch(
        """
        WITH fc AS (
            SELECT DISTINCT source_id::text AS subject_key, category_name AS subject_name
            FROM financial_categories
            WHERE source_system = 'jyhf' AND source_id IS NOT NULL
        )
        SELECT
            t.subject_key,
            COALESCE(fc.subject_name, t.concept, t.subject_key) AS subject_name,
            t.concept,
            t.semantic_type,
            t.strategy_type,
            t.ontology_json,
            t.gate_json,
            t.must_terms,
            t.should_terms,
            t.not_terms,
            t.strong_terms,
            t.weak_terms,
            t.negative_terms,
            t.search_text,
            t.quality,
            e.summary,
            e.core_anchors,
            e.supporting_entities,
            e.representative_events,
            e.embedding_text,
            e.rerank_text
        FROM theme_gate_profile t
        LEFT JOIN fc ON fc.subject_key = t.subject_key
        LEFT JOIN theme_profile_ext e ON e.subject_key = t.subject_key
        ORDER BY t.subject_key
        """
    )
    return [profile_from_row(dict(row)) for row in rows]


async def _enrich_stock_metrics(conn: Any, profiles: list) -> None:
    if await table_exists(conn, "subject_stock_daily_snapshot"):
        rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT subject_key, max(trade_date) AS trade_date
                FROM subject_stock_daily_snapshot
                GROUP BY subject_key
            )
            SELECT s.subject_key, l.trade_date::text AS latest_date, count(DISTINCT s.stock_id) AS stock_pool_size
            FROM subject_stock_daily_snapshot s
            JOIN latest l ON l.subject_key = s.subject_key AND l.trade_date = s.trade_date
            GROUP BY s.subject_key, l.trade_date
            """
        )
        by_key = {safe_str(row["subject_key"]): row for row in rows}
        for profile in profiles:
            row = by_key.get(profile.subject_key)
            if row:
                profile.stock_pool_size = int(row["stock_pool_size"] or 0)
                profile.latest_stock_trade_date = safe_str(row["latest_date"])
    if await table_exists(conn, "theme_stock_leaderboard"):
        rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT subject_key, max(trade_date) AS trade_date
                FROM theme_stock_leaderboard
                GROUP BY subject_key
            )
            SELECT l.subject_key, l.trade_date::text AS latest_date, count(*) AS leaderboard_count
            FROM theme_stock_leaderboard l
            JOIN latest x ON x.subject_key = l.subject_key AND x.trade_date = l.trade_date
            GROUP BY l.subject_key, l.trade_date
            """
        )
        by_key = {safe_str(row["subject_key"]): row for row in rows}
        for profile in profiles:
            row = by_key.get(profile.subject_key)
            if row:
                profile.leaderboard_count = int(row["leaderboard_count"] or 0)
                profile.latest_leaderboard_trade_date = safe_str(row["latest_date"])


async def _load_recent_event_counts(conn: Any, since_days: int) -> dict[str, int]:
    if not await table_exists(conn, "event_subject_map"):
        return {}
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    rows = await conn.fetch(
        """
        SELECT subject_key, count(*) AS event_count
        FROM event_subject_map
        WHERE created_at >= $1
        GROUP BY subject_key
        """,
        since,
    )
    return {safe_str(row["subject_key"]): int(row["event_count"] or 0) for row in rows}


def _risk_metrics(profile, overlap_score: float, heat_score: float) -> dict[str, Any]:
    anchor_terms = unique([profile.subject_name, profile.concept, *profile.aliases, *profile.must_terms, *profile.strong_terms, *profile.core_anchors])
    anchors, generic = split_generic(anchor_terms)
    alias_generic_count = sum(1 for term in profile.aliases if is_generic_term(term))
    generic_anchor_ratio = round(len(generic) / max(1, len(anchor_terms)), 4)
    negative_terms_count = len(unique([*profile.negative_terms, *profile.not_terms]))
    anchor_count = len(anchors)
    false_positive_risk = round(
        min(
            1.0,
            generic_anchor_ratio * 0.45
            + min(alias_generic_count / 5, 1.0) * 0.20
            + overlap_score * 0.25
            + (0.10 if negative_terms_count == 0 else 0.0)
            + (0.15 if anchor_count < 3 else 0.0),
        ),
        4,
    )
    priority_score = round(
        min(
            100.0,
            false_positive_risk * 60
            + heat_score * 25
            + (15 if profile.stock_pool_size > 0 else 0)
            + (10 if profile.quality == "weak" else 0),
        ),
        2,
    )
    return {
        "generic_anchor_ratio": generic_anchor_ratio,
        "anchor_count": anchor_count,
        "alias_generic_count": alias_generic_count,
        "negative_terms_count": negative_terms_count,
        "confusion_overlap_score": round(overlap_score, 4),
        "stock_pool_size": profile.stock_pool_size,
        "recent_heat_score": round(heat_score, 4),
        "false_positive_risk": false_positive_risk,
        "priority_score": priority_score,
        "generic_terms": generic[:20],
    }


def _compute_overlap(profiles: list) -> dict[str, tuple[float, list[str]]]:
    anchors = {profile.subject_key: set(profile.anchor_terms()) for profile in profiles}
    result: dict[str, tuple[float, list[str]]] = {}
    for profile in profiles:
        scored: list[tuple[float, str]] = []
        for other in profiles:
            if other.subject_key == profile.subject_key:
                continue
            score = jaccard(anchors[profile.subject_key], anchors[other.subject_key])
            if score > 0:
                scored.append((score, other.subject_key))
        scored.sort(reverse=True)
        result[profile.subject_key] = (scored[0][0] if scored else 0.0, [key for _, key in scored[:8]])
    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit JYHF theme gate/profile quality without overwriting old tables.")
    add_db_args(parser)
    parser.add_argument("--run-id", default=datetime.now().strftime("profile_audit_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--recent-days", type=int, default=30)
    args = parser.parse_args()

    out_dir = args.output_dir or default_output_dir(args.run_id)
    read_conn = await connect(args.read_db_name)
    write_conn = None
    try:
        profiles = await _load_profiles(read_conn)
        await _enrich_stock_metrics(read_conn, profiles)
        if args.write_db_name != args.read_db_name:
            write_conn = await connect(args.write_db_name)
            event_counts = await _load_recent_event_counts(write_conn, args.recent_days)
        else:
            event_counts = await _load_recent_event_counts(read_conn, args.recent_days)
        max_event_count = max(event_counts.values() or [0])
        max_stock_pool = max([p.stock_pool_size for p in profiles] or [0])
        overlaps = _compute_overlap(profiles)
        rows: list[dict[str, Any]] = []
        for profile in profiles:
            event_heat = event_counts.get(profile.subject_key, 0) / max(1, max_event_count)
            stock_heat = profile.stock_pool_size / max(1, max_stock_pool)
            heat_score = min(1.0, event_heat * 0.7 + stock_heat * 0.3)
            overlap_score, confusion_keys = overlaps.get(profile.subject_key, (0.0, []))
            metrics = _risk_metrics(profile, overlap_score, heat_score)
            rows.append(
                {
                    "subject_key": profile.subject_key,
                    "subject_name": profile.subject_name,
                    "concept": profile.concept,
                    "semantic_type": profile.semantic_type,
                    "strategy_type": profile.strategy_type,
                    "quality": profile.quality,
                    "latest_stock_trade_date": profile.latest_stock_trade_date,
                    "latest_leaderboard_trade_date": profile.latest_leaderboard_trade_date,
                    "leaderboard_count": profile.leaderboard_count,
                    "recent_event_count": event_counts.get(profile.subject_key, 0),
                    "confusion_subject_keys": confusion_keys,
                    **metrics,
                }
            )
        rows.sort(key=lambda row: (-float(row["priority_score"]), -float(row["false_positive_risk"]), row["subject_key"]))
        top_rows = rows[: args.top_n]
        write_jsonl(out_dir / "theme_profile_audit_report.jsonl", rows)
        write_csv(out_dir / "theme_profile_audit_report.csv", rows)
        write_jsonl(out_dir / "theme_profile_rebuild_top50.jsonl", top_rows)
        write_csv(out_dir / "theme_profile_rebuild_top50.csv", top_rows)
        print(
            {
                "read_db": args.read_db_name,
                "write_db_for_history": args.write_db_name,
                "profile_count": len(rows),
                "top_n": len(top_rows),
                "out_dir": str(out_dir),
            }
        )
    finally:
        await read_conn.close()
        if write_conn:
            await write_conn.close()


if __name__ == "__main__":
    run_async(main())

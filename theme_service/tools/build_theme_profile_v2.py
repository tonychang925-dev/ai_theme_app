from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.profile_quality_common import (
    GENERIC_TERMS,
    add_db_args,
    connect,
    default_output_dir,
    is_generic_term,
    normalize_list,
    read_jsonl,
    run_async,
    safe_str,
    split_generic,
    table_exists,
    unique,
    write_jsonl,
)

PROFILE_FIELDS = [
    "aliases",
    "entity_anchors",
    "domain_anchors",
    "product_anchors",
    "technology_anchors",
    "event_action_terms",
    "must_terms",
    "strong_terms",
    "should_terms",
    "support_terms",
    "weak_terms",
    "no_anchor_terms",
    "negative_terms",
    "confusion_subject_keys",
]


async def _load_subject_keys(path: Path, limit: int) -> list[str]:
    if path.suffix.lower() == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and isinstance(obj.get("subjects"), list):
            rows = obj["subjects"]
        elif isinstance(obj, list):
            rows = obj
        else:
            rows = []
    else:
        rows = read_jsonl(path)
    keys = [safe_str(row.get("subject_key")) for row in rows if safe_str(row.get("subject_key"))]
    return keys[:limit]


async def _load_materials(conn: Any, subject_keys: list[str]) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            t.subject_key,
            COALESCE(fc.category_name, t.concept, t.subject_key) AS subject_name,
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
            e.rerank_text,
            sd.detail_html,
            sd.reason_short
        FROM theme_gate_profile t
        LEFT JOIN financial_categories fc
          ON fc.source_system = 'jyhf' AND fc.source_id::text = t.subject_key
        LEFT JOIN theme_profile_ext e ON e.subject_key = t.subject_key
        LEFT JOIN subject_detail sd ON sd.subject_key = t.subject_key AND COALESCE(sd.is_current, true)
        WHERE t.subject_key = ANY($1::text[])
        """,
        subject_keys,
    )
    materials = {safe_str(row["subject_key"]): dict(row) for row in rows}
    if await table_exists(conn, "subject_stock_daily_snapshot"):
        stock_rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT subject_key, max(trade_date) AS trade_date
                FROM subject_stock_daily_snapshot
                WHERE subject_key = ANY($1::text[])
                GROUP BY subject_key
            )
            SELECT s.subject_key, l.trade_date::text AS trade_date, count(DISTINCT s.stock_id) AS stock_count,
                   jsonb_agg(jsonb_build_object('stock_id', s.stock_id, 'stock_name', s.stock_name, 'rank_order', s.rank_order)
                             ORDER BY s.rank_order NULLS LAST, s.stock_id) FILTER (WHERE s.stock_id IS NOT NULL) AS stocks
            FROM subject_stock_daily_snapshot s
            JOIN latest l ON l.subject_key = s.subject_key AND l.trade_date = s.trade_date
            GROUP BY s.subject_key, l.trade_date
            """,
            subject_keys,
        )
        for row in stock_rows:
            material = materials.setdefault(safe_str(row["subject_key"]), {"subject_key": safe_str(row["subject_key"])})
            material["stock_pool_summary"] = {
                "trade_date": safe_str(row["trade_date"]),
                "stock_count": int(row["stock_count"] or 0),
                "top_stocks": row["stocks"] or [],
            }
    if await table_exists(conn, "theme_stock_leaderboard"):
        leaderboard_rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT subject_key, max(trade_date) AS trade_date
                FROM theme_stock_leaderboard
                WHERE subject_key = ANY($1::text[])
                GROUP BY subject_key
            )
            SELECT l.subject_key, l.trade_date::text AS trade_date, count(*) AS row_count,
                   jsonb_agg(jsonb_build_object('stock_id', l.stock_id, 'rank', l.leaderboard_rank, 'score', l.leader_score, 'role', l.role_name)
                             ORDER BY l.leaderboard_rank, l.stock_id) AS leaders
            FROM theme_stock_leaderboard l
            JOIN latest x ON x.subject_key = l.subject_key AND x.trade_date = l.trade_date
            GROUP BY l.subject_key, l.trade_date
            """,
            subject_keys,
        )
        for row in leaderboard_rows:
            material = materials.setdefault(safe_str(row["subject_key"]), {"subject_key": safe_str(row["subject_key"])})
            material["leaderboard_summary"] = {
                "trade_date": safe_str(row["trade_date"]),
                "row_count": int(row["row_count"] or 0),
                "leaders": row["leaders"] or [],
            }
    return materials


async def _load_recent_events(conn: Any, subject_keys: list[str], limit_per_subject: int = 5) -> dict[str, list[dict[str, Any]]]:
    if not await table_exists(conn, "event_subject_map"):
        return {}
    rows = await conn.fetch(
        """
        SELECT *
        FROM (
            SELECT esm.subject_key, esm.subject_name, esm.relation_type, esm.confidence, esm.match_reason,
                   ne.id AS event_id, ne.title, ne.summary, ne.event_type, ne.occurred_at,
                   row_number() OVER (PARTITION BY esm.subject_key ORDER BY esm.created_at DESC) AS rn
            FROM event_subject_map esm
            JOIN news_event ne ON ne.id = esm.event_id
            WHERE esm.subject_key = ANY($1::text[])
        ) x
        WHERE rn <= $2
        ORDER BY subject_key, rn
        """,
        subject_keys,
        limit_per_subject,
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(safe_str(row["subject_key"]), []).append(dict(row))
    return out


def _extract_text_terms(text: str) -> list[str]:
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9._/-]{1,}|[\u4e00-\u9fffA-Za-z0-9]{2,12}", safe_str(text))
    return unique(candidates)[:80]


def _fallback_profile(material: dict[str, Any], recent_events: list[dict[str, Any]], confusion_keys: list[str]) -> dict[str, Any]:
    subject_name = safe_str(material.get("subject_name") or material.get("concept") or material.get("subject_key"))
    old_must = normalize_list(material.get("must_terms"))
    old_strong = normalize_list(material.get("strong_terms"))
    old_should = normalize_list(material.get("should_terms"))
    ext_anchors = normalize_list(material.get("core_anchors"))
    supporting = normalize_list(material.get("supporting_entities"))
    text_terms = _extract_text_terms(" ".join([safe_str(material.get("summary")), safe_str(material.get("rerank_text")), safe_str(material.get("reason_short"))]))
    anchors, generic = split_generic([subject_name, safe_str(material.get("concept")), *ext_anchors, *old_must, *old_strong, *supporting, *text_terms])
    no_anchor = unique([term for term in [*generic, *old_should] if is_generic_term(term)])
    strong_terms = unique([term for term in [*anchors, *old_strong] if not is_generic_term(term)])[:16]
    must_terms = unique([subject_name, *ext_anchors, *old_must])
    must_terms = [term for term in must_terms if not is_generic_term(term)][:10]
    aliases = [term for term in unique([subject_name, safe_str(material.get("concept")), *ext_anchors]) if not is_generic_term(term)][:10]
    negative_terms = unique(normalize_list(material.get("negative_terms")) + normalize_list(material.get("not_terms")) + [f"非{subject_name}"])[:12]
    evidence_refs = [
        {"source": "theme_gate_profile", "subject_key": material.get("subject_key")},
        {"source": "theme_profile_ext", "subject_key": material.get("subject_key")},
    ]
    if material.get("detail_html"):
        evidence_refs.append({"source": "subject_detail", "subject_key": material.get("subject_key")})
    for event in recent_events[:3]:
        evidence_refs.append({"source": "event_subject_map", "event_id": event.get("event_id"), "title": event.get("title")})
    return {
        "subject_key": safe_str(material.get("subject_key")),
        "subject_name": subject_name,
        "aliases": aliases,
        "entity_anchors": unique([*ext_anchors, *supporting])[:16],
        "domain_anchors": unique([term for term in anchors if len(term) >= 3])[:12],
        "product_anchors": [],
        "technology_anchors": [],
        "event_action_terms": unique([term for term in ["发布", "发射", "上市", "订单", "投产", "中标"] if term in safe_str(material)])[:8],
        "must_terms": must_terms,
        "strong_terms": strong_terms,
        "should_terms": [term for term in unique(old_should + anchors) if not is_generic_term(term)][:20],
        "support_terms": unique([*no_anchor, *[term for term in old_should if is_generic_term(term)]])[:20],
        "weak_terms": unique(normalize_list(material.get("weak_terms")))[:20],
        "no_anchor_terms": no_anchor[:30],
        "negative_terms": negative_terms,
        "confusion_subject_keys": confusion_keys[:8],
        "boundary_rules": {
            "generic_terms_not_anchor": True,
            "requires_subject_or_entity_anchor": True,
        },
        "stock_pool_summary": material.get("stock_pool_summary") or {},
        "evidence_refs": evidence_refs,
        "source_blocks": {
            "gate_profile": {
                "must_terms": old_must,
                "strong_terms": old_strong,
                "should_terms": old_should,
                "quality": material.get("quality"),
            },
            "profile_ext": {
                "summary": material.get("summary"),
                "core_anchors": material.get("core_anchors"),
                "supporting_entities": material.get("supporting_entities"),
            },
            "recent_events": recent_events,
            "leaderboard_summary": material.get("leaderboard_summary") or {},
        },
        "version": 1,
        "status": "draft",
    }


def _llm_json(prompt: str, *, model: str, timeout: int = 45) -> dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("THEME_PROFILE_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("missing LLM API key")
    response = requests.post(
        os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def _llm_profile(material: dict[str, Any], recent_events: list[dict[str, Any]], confusion_keys: list[str], *, model: str) -> dict[str, Any]:
    material_block = json.dumps(
        {
            "material": material,
            "recent_events": recent_events,
            "confusion_subject_keys": confusion_keys,
            "generic_terms": sorted(GENERIC_TERMS),
        },
        ensure_ascii=False,
        default=str,
    )[:18000]
    step1 = _llm_json(
        "你是A股题材画像质量工程师。请先做术语角色分类，输出JSON。"
        "泛词如供应链/供应商/产业链/制造/生产/合作/参股/包装/物流/上游/下游只能进入support_terms或no_anchor_terms，"
        "不得进入anchors、must_terms、strong_terms、aliases。\n材料："
        + material_block,
        model=model,
    )
    step2 = _llm_json(
        "基于术语分类和材料生成 theme_profile_v2 JSON。字段必须包含："
        + ",".join(PROFILE_FIELDS)
        + ",boundary_rules,stock_pool_summary,evidence_refs,source_blocks,quality_score,quality_flags,eval_metrics,version,status。"
        "每条profile必须包含evidence_refs。quality_score按0-100评分。\n术语分类："
        + json.dumps(step1, ensure_ascii=False)
        + "\n材料："
        + material_block,
        model=model,
    )
    return step2


def _quality_score(profile: dict[str, Any]) -> tuple[float, list[str]]:
    flags: list[str] = []
    must_generic = [term for term in normalize_list(profile.get("must_terms")) if is_generic_term(term)]
    strong_terms = normalize_list(profile.get("strong_terms"))
    strong_generic_ratio = len([term for term in strong_terms if is_generic_term(term)]) / max(1, len(strong_terms))
    alias_generic = [term for term in normalize_list(profile.get("aliases")) if is_generic_term(term)]
    anchor_count = len(
        unique(
            normalize_list(profile.get("entity_anchors"))
            + normalize_list(profile.get("domain_anchors"))
            + normalize_list(profile.get("product_anchors"))
            + normalize_list(profile.get("technology_anchors"))
        )
    )
    if must_generic:
        flags.append("must_terms_contain_generic")
    if strong_generic_ratio >= 0.10:
        flags.append("strong_terms_generic_ratio_high")
    if alias_generic:
        flags.append("aliases_contain_generic")
    if anchor_count < 3:
        flags.append("anchor_count_lt_3")
    if not normalize_list(profile.get("negative_terms")) and not normalize_list(profile.get("confusion_subject_keys")):
        flags.append("missing_negative_or_confusion")
    if not profile.get("evidence_refs"):
        flags.append("missing_evidence_refs")
    score = 100.0 - len(flags) * 12.0 - min(20.0, strong_generic_ratio * 40.0)
    return max(0.0, round(score, 2)), flags


def _sanitize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    no_anchor = normalize_list(profile.get("no_anchor_terms")) + normalize_list(profile.get("support_terms"))
    for key in ("must_terms", "strong_terms", "aliases", "entity_anchors", "domain_anchors", "product_anchors", "technology_anchors"):
        anchors, generic = split_generic(normalize_list(profile.get(key)))
        profile[key] = anchors
        no_anchor.extend(generic)
    profile["no_anchor_terms"] = unique(no_anchor)
    for key in PROFILE_FIELDS:
        profile[key] = normalize_list(profile.get(key))
    score, flags = _quality_score(profile)
    profile["quality_score"] = float(profile.get("quality_score") or score)
    if profile["quality_score"] > score:
        profile["quality_score"] = score
    profile["quality_flags"] = unique(normalize_list(profile.get("quality_flags")) + flags)
    profile["eval_metrics"] = profile.get("eval_metrics") if isinstance(profile.get("eval_metrics"), dict) else {}
    profile["boundary_rules"] = profile.get("boundary_rules") if isinstance(profile.get("boundary_rules"), dict) else {}
    profile["stock_pool_summary"] = profile.get("stock_pool_summary") if isinstance(profile.get("stock_pool_summary"), dict) else {}
    profile["source_blocks"] = profile.get("source_blocks") if isinstance(profile.get("source_blocks"), dict) else {}
    profile["evidence_refs"] = profile.get("evidence_refs") if isinstance(profile.get("evidence_refs"), list) else []
    profile["version"] = int(profile.get("version") or 1)
    profile["status"] = safe_str(profile.get("status") or "draft")
    return profile


def _attach_audit_metrics(profile: dict[str, Any], audit_row: dict[str, Any]) -> dict[str, Any]:
    metrics = profile.get("eval_metrics") if isinstance(profile.get("eval_metrics"), dict) else {}
    for key in (
        "generic_anchor_ratio",
        "must_generic_count",
        "alias_generic_count",
        "anchor_count",
        "negative_count",
        "nearby_overlap_score",
        "false_positive_risk",
        "priority_score",
        "stock_pool_size",
        "recent_heat_score",
    ):
        if key in audit_row:
            metrics[key] = audit_row.get(key)
    metrics.setdefault("hard_negative_reject_rate", None)
    profile["eval_metrics"] = metrics
    return profile


async def _upsert_profiles(conn: Any, profiles: list[dict[str, Any]]) -> int:
    sql = """
    INSERT INTO theme_profile_v2 (
        subject_key, subject_name, aliases, entity_anchors, domain_anchors, product_anchors, technology_anchors,
        event_action_terms, must_terms, strong_terms, should_terms, support_terms, weak_terms, no_anchor_terms,
        negative_terms, confusion_subject_keys, boundary_rules, stock_pool_summary, evidence_refs, source_blocks,
        quality_score, quality_flags, eval_metrics, version, status, updated_at
    ) VALUES (
        $1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
        $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb,
        $15::jsonb, $16::jsonb, $17::jsonb, $18::jsonb, $19::jsonb, $20::jsonb,
        $21, $22::jsonb, $23::jsonb, $24, $25, now()
    )
    ON CONFLICT (subject_key) DO UPDATE SET
        subject_name = EXCLUDED.subject_name,
        aliases = EXCLUDED.aliases,
        entity_anchors = EXCLUDED.entity_anchors,
        domain_anchors = EXCLUDED.domain_anchors,
        product_anchors = EXCLUDED.product_anchors,
        technology_anchors = EXCLUDED.technology_anchors,
        event_action_terms = EXCLUDED.event_action_terms,
        must_terms = EXCLUDED.must_terms,
        strong_terms = EXCLUDED.strong_terms,
        should_terms = EXCLUDED.should_terms,
        support_terms = EXCLUDED.support_terms,
        weak_terms = EXCLUDED.weak_terms,
        no_anchor_terms = EXCLUDED.no_anchor_terms,
        negative_terms = EXCLUDED.negative_terms,
        confusion_subject_keys = EXCLUDED.confusion_subject_keys,
        boundary_rules = EXCLUDED.boundary_rules,
        stock_pool_summary = EXCLUDED.stock_pool_summary,
        evidence_refs = EXCLUDED.evidence_refs,
        source_blocks = EXCLUDED.source_blocks,
        quality_score = EXCLUDED.quality_score,
        quality_flags = EXCLUDED.quality_flags,
        eval_metrics = EXCLUDED.eval_metrics,
        version = theme_profile_v2.version + 1,
        status = EXCLUDED.status,
        updated_at = now()
    """
    count = 0
    for profile in profiles:
        await conn.execute(
            sql,
            profile["subject_key"],
            profile["subject_name"],
            json.dumps(profile["aliases"], ensure_ascii=False),
            json.dumps(profile["entity_anchors"], ensure_ascii=False),
            json.dumps(profile["domain_anchors"], ensure_ascii=False),
            json.dumps(profile["product_anchors"], ensure_ascii=False),
            json.dumps(profile["technology_anchors"], ensure_ascii=False),
            json.dumps(profile["event_action_terms"], ensure_ascii=False),
            json.dumps(profile["must_terms"], ensure_ascii=False),
            json.dumps(profile["strong_terms"], ensure_ascii=False),
            json.dumps(profile["should_terms"], ensure_ascii=False),
            json.dumps(profile["support_terms"], ensure_ascii=False),
            json.dumps(profile["weak_terms"], ensure_ascii=False),
            json.dumps(profile["no_anchor_terms"], ensure_ascii=False),
            json.dumps(profile["negative_terms"], ensure_ascii=False),
            json.dumps(profile["confusion_subject_keys"], ensure_ascii=False),
            json.dumps(profile["boundary_rules"], ensure_ascii=False),
            json.dumps(profile["stock_pool_summary"], ensure_ascii=False),
            json.dumps(profile["evidence_refs"], ensure_ascii=False, default=str),
            json.dumps(profile["source_blocks"], ensure_ascii=False, default=str),
            float(profile["quality_score"]),
            json.dumps(profile["quality_flags"], ensure_ascii=False),
            json.dumps(profile["eval_metrics"], ensure_ascii=False),
            int(profile["version"]),
            profile["status"],
        )
        count += 1
    return count


async def _supersede_other_drafts(conn: Any, subject_keys: list[str]) -> None:
    if not subject_keys:
        return
    await conn.execute(
        """
        UPDATE theme_profile_v2
        SET status = 'superseded', updated_at = now()
        WHERE status = 'draft'
          AND NOT (subject_key = ANY($1::text[]))
        """,
        subject_keys,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Build theme_profile_v2 for TopN subject_keys.")
    add_db_args(parser)
    parser.add_argument("--input", type=Path, required=True, help="TopN JSONL from audit_theme_profiles.py")
    parser.add_argument("--run-id", default=datetime.now().strftime("profile_v2_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--model", default=os.getenv("THEME_PROFILE_LLM_MODEL", "deepseek-chat"))
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--supersede-other-drafts", action="store_true")
    args = parser.parse_args()
    out_dir = args.output_dir or default_output_dir(args.run_id)
    subject_keys = await _load_subject_keys(args.input, args.limit)
    read_conn = await connect(args.read_db_name)
    write_conn = None
    try:
        materials = await _load_materials(read_conn, subject_keys)
        write_conn = await connect(args.write_db_name)
        recent_events = await _load_recent_events(write_conn, subject_keys)
        if args.input.suffix.lower() == ".json":
            raw_top = json.loads(args.input.read_text(encoding="utf-8"))
            top_source_rows = raw_top.get("subjects", []) if isinstance(raw_top, dict) else raw_top
        else:
            top_source_rows = read_jsonl(args.input)
        top_rows = {safe_str(row.get("subject_key")): row for row in top_source_rows if isinstance(row, dict)}
        profiles: list[dict[str, Any]] = []
        for subject_key in subject_keys:
            material = materials.get(subject_key)
            if not material:
                continue
            confusion_keys = normalize_list(top_rows.get(subject_key, {}).get("confusion_subject_keys"))
            events = recent_events.get(subject_key, [])
            if args.use_llm:
                try:
                    profile = _llm_profile(material, events, confusion_keys, model=args.model)
                except Exception as exc:
                    profile = _fallback_profile(material, events, confusion_keys)
                    profile.setdefault("quality_flags", []).append(f"llm_fallback:{type(exc).__name__}")
            else:
                profile = _fallback_profile(material, events, confusion_keys)
            profile["subject_key"] = subject_key
            profile["subject_name"] = safe_str(profile.get("subject_name") or material.get("subject_name"))
            profiles.append(_sanitize_profile(_attach_audit_metrics(profile, top_rows.get(subject_key, {}))))
        write_jsonl(out_dir / "theme_profile_v2_top50.jsonl", profiles)
        written = 0
        if args.write_db:
            written = await _upsert_profiles(write_conn, profiles)
            if args.supersede_other_drafts:
                await _supersede_other_drafts(write_conn, [profile["subject_key"] for profile in profiles])
        print({"subject_keys": len(subject_keys), "profiles": len(profiles), "written": written, "out_dir": str(out_dir)})
    finally:
        await read_conn.close()
        if write_conn:
            await write_conn.close()


if __name__ == "__main__":
    run_async(main())

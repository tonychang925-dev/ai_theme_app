from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.profile_quality_common import add_db_args, connect, default_output_dir, normalize_list, safe_str


def _load_top_subjects(path: Path, limit: int) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        rows = obj.get("subjects", []) if isinstance(obj, dict) else obj
    else:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if isinstance(row, dict) and safe_str(row.get("subject_key"))][:limit]


async def _load_material(conn: Any, subject_key: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT
            t.subject_key,
            COALESCE(fc.category_name, t.concept, t.subject_key) AS subject_name,
            t.concept,
            t.semantic_type,
            t.strategy_type,
            t.must_terms,
            t.should_terms,
            t.not_terms,
            t.strong_terms,
            t.weak_terms,
            t.negative_terms,
            t.ontology_json,
            t.gate_json,
            t.search_text,
            t.quality,
            e.summary,
            e.core_anchors,
            e.supporting_entities,
            e.representative_events,
            e.embedding_text,
            e.rerank_text,
            sd.reason_short,
            sd.detail_html
        FROM theme_gate_profile t
        LEFT JOIN financial_categories fc
          ON fc.source_system = 'jyhf' AND fc.source_id::text = t.subject_key
        LEFT JOIN theme_profile_ext e ON e.subject_key = t.subject_key
        LEFT JOIN subject_detail sd ON sd.subject_key = t.subject_key AND COALESCE(sd.is_current, true)
        WHERE t.subject_key = $1
        """,
        subject_key,
    )
    return dict(row) if row else {"subject_key": subject_key}


async def _load_stock_pool(conn: Any, subject_key: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        WITH latest AS (
            SELECT max(trade_date) AS trade_date
            FROM subject_stock_daily_snapshot
            WHERE subject_key = $1
        )
        SELECT s.trade_date, s.stock_id, s.stock_name, s.rank_order, s.pct_chg, s.is_leader
        FROM subject_stock_daily_snapshot s, latest l
        WHERE s.subject_key = $1 AND s.trade_date = l.trade_date
        ORDER BY s.rank_order NULLS LAST, s.stock_id
        LIMIT 30
        """,
        subject_key,
    )
    return [dict(row) for row in rows]


async def _load_recent_events(conn: Any, subject_key: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT esm.relation_type, esm.confidence, esm.match_reason,
               ne.id AS event_id,
               COALESCE(nr.title, '') AS title,
               ne.summary,
               nr.content,
               ne.event_type,
               COALESCE(nr.publish_date::text, ne.created_at::date::text) AS occurred_at
        FROM event_subject_map esm
        JOIN news_event ne ON ne.id = esm.event_id
        LEFT JOIN news_raw nr ON nr.id = ne.news_id
        WHERE esm.subject_key = $1
        ORDER BY esm.created_at DESC
        LIMIT 10
        """,
        subject_key,
    )
    return [dict(row) for row in rows]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _packet_text(row: dict[str, Any], material: dict[str, Any], stock_pool: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    subject_key = safe_str(row.get("subject_key"))
    subject_name = safe_str(row.get("subject_name") or material.get("subject_name"))
    nearby = normalize_list(row.get("nearby_subject_keys"))
    return f"""# Theme Profile V2 Manual Review Packet

## Subject
- subject_key: `{subject_key}`
- subject_name: `{subject_name}`
- priority_score: `{row.get('priority_score')}`
- false_positive_risk: `{row.get('false_positive_risk')}`
- nearby_overlap_score: `{row.get('nearby_overlap_score')}`
- nearby_subject_keys: `{', '.join(nearby)}`

## Required Review Goal
请精读资料，为该题材生成高质量 `theme_profile_v2`。不要直接复用旧 `must/should/not`。

### Hard Rules
1. 供应链、供应商、产业链、制造、生产、合作、参股、订单、客户、物流、包装、上游、下游等泛词不能进入 `must_terms`、`aliases`、`entity_anchors`、`domain_anchors`。
2. 泛词只能进入 `support_terms`、`weak_terms` 或 `no_anchor_terms`。
3. 必须给出 `negative_terms` 或 `confusion_subject_keys`。
4. 必须写 `boundary_rules`，明确哪些情况不得匹配本题材。
5. 如果资料不足，输出 `status=needs_review`。

## Old Gate / Profile
```json
{_json({
  'concept': material.get('concept'),
  'semantic_type': material.get('semantic_type'),
  'strategy_type': material.get('strategy_type'),
  'quality': material.get('quality'),
  'must_terms': material.get('must_terms'),
  'strong_terms': material.get('strong_terms'),
  'should_terms': material.get('should_terms'),
  'not_terms': material.get('not_terms'),
  'negative_terms': material.get('negative_terms'),
  'core_anchors': material.get('core_anchors'),
  'supporting_entities': material.get('supporting_entities'),
})}
```

## Audit Signals
```json
{_json({
  'generic_anchor_ratio': row.get('generic_anchor_ratio'),
  'must_generic_count': row.get('must_generic_count'),
  'alias_generic_count': row.get('alias_generic_count'),
  'anchor_count': row.get('anchor_count'),
  'negative_count': row.get('negative_count'),
  'must_generic_terms': row.get('must_generic_terms'),
  'alias_generic_terms': row.get('alias_generic_terms'),
  'no_anchor_candidates': row.get('no_anchor_candidates'),
})}
```

## Detail / Summary
reason_short:
{safe_str(material.get('reason_short'))[:2000]}

summary:
{safe_str(material.get('summary'))[:2000]}

rerank_text:
{safe_str(material.get('rerank_text'))[:3000]}

detail_html excerpt:
{safe_str(material.get('detail_html'))[:5000]}

## Stock Pool Top30
```json
{_json(stock_pool)}
```

## Recent Matched Events
```json
{_json(events)}
```

## Output Schema
请按三步输出：

1. 题材理解报告
2. 术语分层
3. 标准 `theme_profile_v2` JSON

标准 JSON 字段：
`subject_key, subject_name, aliases, entity_anchors, domain_anchors, product_anchors, technology_anchors, event_action_terms, must_terms, strong_terms, should_terms, support_terms, weak_terms, no_anchor_terms, negative_terms, confusion_subject_keys, boundary_rules, evidence_refs, source_blocks, quality_score, quality_flags, eval_metrics, version, status`
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate manual AI review packets for TopN theme_profile_v2 rebuild.")
    add_db_args(parser)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--run-id", default=datetime.now().strftime("theme_profile_manual_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    out_root = args.output_dir or default_output_dir(args.run_id) / "theme_profile_manual_review"
    packet_dir = out_root / "input_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    for stale in packet_dir.glob("*.md"):
        stale.unlink()
    subjects = _load_top_subjects(args.input, args.limit)
    read_conn = await connect(args.read_db_name)
    write_conn = await connect(args.write_db_name)
    try:
        manifest = []
        for row in subjects:
            subject_key = safe_str(row.get("subject_key"))
            material = await _load_material(read_conn, subject_key)
            stock_pool = await _load_stock_pool(read_conn, subject_key)
            events = await _load_recent_events(write_conn, subject_key)
            subject_name = safe_str(row.get("subject_name") or material.get("subject_name") or subject_key)
            safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in subject_name)[:40]
            path = packet_dir / f"{subject_key}_{safe_name}.md"
            path.write_text(_packet_text(row, material, stock_pool, events), encoding="utf-8")
            manifest.append({"subject_key": subject_key, "subject_name": subject_name, "packet": str(path)})
        (out_root / "manifest.json").write_text(_json({"count": len(manifest), "packets": manifest}), encoding="utf-8")
        print({"packet_count": len(manifest), "out_dir": str(out_root)})
    finally:
        await read_conn.close()
        await write_conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

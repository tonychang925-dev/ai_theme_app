from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.profile_quality_common import connect, run_async


PROFILES: list[dict[str, Any]] = [
    {
        "subject_key": "9051960",
        "subject_name": "充电宝",
        "aliases": ["充电宝", "移动电源"],
        "entity_anchors": ["充电宝企业", "移动电源企业"],
        "domain_anchors": ["移动电源新国家标准", "充电宝安全标准", "移动电源安全监管"],
        "product_anchors": ["充电宝", "移动电源", "电池本质安全指标"],
        "technology_anchors": ["过充电保护", "过放电保护", "短路保护", "过载保护", "电芯安全"],
        "must_terms": ["充电宝", "移动电源", "移动电源新国家标准", "电池本质安全指标"],
        "strong_terms": ["充电宝企业", "移动电源企业", "充电宝安全标准", "过充电保护", "过放电保护", "短路保护"],
        "should_terms": ["产品标识", "循环后跌落测试", "智能化电量管理与保护", "电芯生产过程关键管控"],
        "support_terms": ["工业和信息化部", "市场监管总局", "国家标准", "强制性国家标准", "行业监管"],
        "no_anchor_terms": ["工业和信息化部", "市场监管总局", "证监会", "证券", "期货", "基金", "跨境", "综合整治", "非法经营", "监管部门", "八部门"],
        "negative_terms": ["证券期货基金", "跨境证券", "非法跨境证券", "非法证券期货基金", "证券监管", "基金经营活动", "金融监管"],
        "boundary_rules": {
            "accept_requires_any": ["充电宝", "移动电源", "移动电源新国家标准", "电池本质安全指标", "过充电保护", "过放电保护", "短路保护"],
            "reject_if_only_hits": ["工业和信息化部", "市场监管总局", "证监会", "证券", "期货", "基金", "跨境", "综合整治", "监管部门"],
            "reject_domains": ["证券期货基金监管", "非法跨境证券", "基金经营活动整治", "金融监管"],
            "nearby_confusions": ["证券", "基金", "跨境证券", "金融监管"],
        },
        "evidence_refs": [{"term": "充电宝/移动电源安全标准", "source": "product_runtime_phase3a"}],
        "source_blocks": {"repair_reason": "remove regulator-only hard anchors that caused securities policy to match power-bank theme"},
        "quality_flags": ["product_runtime_phase3a", "accepted_candidate", "regulator_terms_no_anchor"],
        "eval_metrics": {"hard_negative_case": "phase3a_cs_rc_illegal_cross_border_securities_not_powerbank"},
    }
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


async def _upsert(db_name: str) -> int:
    conn = await connect(db_name)
    sql = """
    INSERT INTO theme_profile_v2 (
        subject_key, subject_name, aliases, entity_anchors, domain_anchors, product_anchors, technology_anchors,
        event_action_terms, must_terms, strong_terms, should_terms, support_terms, weak_terms, no_anchor_terms,
        negative_terms, confusion_subject_keys, boundary_rules, stock_pool_summary, evidence_refs, source_blocks,
        quality_score, quality_flags, eval_metrics, status, generated_by, updated_at
    ) VALUES (
        $1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
        '[]'::jsonb, $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, '[]'::jsonb, $12::jsonb,
        $13::jsonb, '[]'::jsonb, $14::jsonb, '{}'::jsonb, $15::jsonb, $16::jsonb,
        95.0, $17::jsonb, $18::jsonb, 'accepted_candidate', 'product_runtime_phase3a', now()
    )
    ON CONFLICT (subject_key) DO UPDATE SET
        subject_name = EXCLUDED.subject_name,
        aliases = EXCLUDED.aliases,
        entity_anchors = EXCLUDED.entity_anchors,
        domain_anchors = EXCLUDED.domain_anchors,
        product_anchors = EXCLUDED.product_anchors,
        technology_anchors = EXCLUDED.technology_anchors,
        must_terms = EXCLUDED.must_terms,
        strong_terms = EXCLUDED.strong_terms,
        should_terms = EXCLUDED.should_terms,
        support_terms = EXCLUDED.support_terms,
        no_anchor_terms = EXCLUDED.no_anchor_terms,
        negative_terms = EXCLUDED.negative_terms,
        boundary_rules = EXCLUDED.boundary_rules,
        evidence_refs = EXCLUDED.evidence_refs,
        source_blocks = EXCLUDED.source_blocks,
        quality_score = EXCLUDED.quality_score,
        quality_flags = EXCLUDED.quality_flags,
        eval_metrics = EXCLUDED.eval_metrics,
        status = 'accepted_candidate',
        generated_by = 'product_runtime_phase3a',
        version = theme_profile_v2.version + 1,
        updated_at = now()
    """
    try:
        count = 0
        for profile in PROFILES:
            await conn.execute(
                sql,
                profile["subject_key"],
                profile["subject_name"],
                _json(profile["aliases"]),
                _json(profile["entity_anchors"]),
                _json(profile["domain_anchors"]),
                _json(profile["product_anchors"]),
                _json(profile["technology_anchors"]),
                _json(profile["must_terms"]),
                _json(profile["strong_terms"]),
                _json(profile["should_terms"]),
                _json(profile["support_terms"]),
                _json(profile["no_anchor_terms"]),
                _json(profile["negative_terms"]),
                _json(profile["boundary_rules"]),
                _json(profile["evidence_refs"]),
                _json(profile["source_blocks"]),
                _json(profile["quality_flags"]),
                _json(profile["eval_metrics"]),
            )
            count += 1
        return count
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Product Runtime Phase 3A theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    count = run_async(_upsert(args.db_name))
    print(json.dumps({"upserted": count, "db_name": args.db_name}, ensure_ascii=False))


if __name__ == "__main__":
    main()

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
        "subject_key": "9063773",
        "subject_name": "字节Seedance",
        "aliases": ["字节Seedance", "Seedance"],
        "entity_anchors": ["字节Seedance", "Seedance", "字节跳动Seedance"],
        "domain_anchors": ["字节跳动视频生成模型", "AI视频生成", "视频生成模型"],
        "product_anchors": ["豆包视频生成", "即梦", "Dreamina", "Seedance2.0"],
        "technology_anchors": ["文生视频", "图生视频", "多模态视频生成"],
        "must_terms": ["字节Seedance", "Seedance", "字节跳动视频生成模型", "AI视频生成"],
        "strong_terms": ["视频生成模型", "豆包视频生成", "即梦", "Dreamina", "Seedance2.0"],
        "should_terms": ["导演级视频生成", "多模态视频生成", "文生视频", "图生视频"],
        "support_terms": ["字节跳动", "视频模型", "生成式AI"],
        "no_anchor_terms": ["IPO", "创业板", "上市", "上会", "生物", "融资", "普通公司名", "于2026", "广告代理", "AIDC", "合作", "接入"],
        "negative_terms": ["普通IPO", "创业板IPO", "普通公司上市", "生物公司IPO", "非字节Seedance"],
        "boundary_rules": {
            "accept_requires_any": ["字节Seedance", "Seedance", "字节跳动视频生成模型", "AI视频生成", "视频生成模型", "豆包视频生成"],
            "reject_if_only_hits": ["IPO", "创业板", "上市", "上会", "生物", "融资", "于2026", "广告代理", "AIDC", "合作", "接入"],
            "reject_domains": ["普通IPO", "普通公司上市", "生物公司IPO"],
            "nearby_confusions": ["字节跳动", "著名IP", "普通创业板IPO"],
        },
    },
    {
        "subject_key": "9041906",
        "subject_name": "杭州七小龙",
        "aliases": ["杭州七小龙", "杭州六小龙", "杭州AI六小龙", "杭州AI七小龙"],
        "entity_anchors": ["深度求索", "DeepSeek", "宇树科技", "云深处", "游戏科学", "强脑科技", "群核科技"],
        "domain_anchors": ["杭州本地AI公司群", "杭州科技企业集群", "杭州人工智能企业集群"],
        "product_anchors": [],
        "technology_anchors": [],
        "must_terms": ["杭州七小龙", "杭州六小龙", "杭州AI六小龙", "杭州AI七小龙", "深度求索", "DeepSeek", "宇树科技", "云深处", "游戏科学", "强脑科技", "群核科技"],
        "strong_terms": ["杭州本地AI公司群", "杭州科技企业集群", "杭州人工智能企业集群", "杭州AI企业集群"],
        "should_terms": ["人才流动", "技术合作", "浙江本地其他企业", "科技创新生态系统", "杭州AI产业"],
        "support_terms": ["人工智能", "机器人", "脑机接口", "产业集群", "产业链"],
        "no_anchor_terms": ["人工智能", "AI", "机器人", "尖端模型", "模型审查", "白宫", "美国政策", "监管", "审查", "产业链", "产业集群"],
        "negative_terms": ["第七龙", "又一条龙", "白宫", "美国政策", "AI模型审查", "尖端模型监管", "出口管制", "国家安全审查"],
        "boundary_rules": {
            "accept_requires_any": ["杭州七小龙", "杭州六小龙", "杭州AI六小龙", "杭州AI七小龙", "深度求索", "DeepSeek", "宇树科技", "云深处", "游戏科学", "强脑科技", "群核科技"],
            "reject_if_only_hits": ["人工智能", "AI", "机器人", "尖端模型", "模型审查", "产业链", "产业集群"],
            "reject_domains": ["美国政策", "AI模型监管", "出口管制", "国家安全审查"],
            "nearby_confusions": ["人工智能", "AI模型", "机器人"],
        },
    },
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
        96.0, $17::jsonb, $18::jsonb, 'accepted_candidate', 'product_runtime_phase2e', now()
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
        status = EXCLUDED.status,
        generated_by = EXCLUDED.generated_by,
        version = theme_profile_v2.version + 1,
        updated_at = now()
    """
    try:
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
                _json([{"source": "product_runtime_phase2e", "subject_key": profile["subject_key"]}]),
                _json({"phase": "product_runtime_phase2e", "manual_reason": "0522_replay_residual_delta_repair"}),
                _json(["product_runtime_phase2e", "accepted_replay_residual_repair"]),
                _json({"phase": "product_runtime_phase2e", "requires_specific_anchor": True}),
            )
        return len(PROFILES)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Product Runtime Phase 2E accepted theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    print(json.dumps({"db_name": args.db_name, "upserted": run_async(_upsert(args.db_name))}, ensure_ascii=False))


if __name__ == "__main__":
    main()

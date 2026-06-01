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


def _profile(
    *,
    subject_key: str,
    subject_name: str,
    aliases: list[str],
    entity_anchors: list[str],
    domain_anchors: list[str],
    product_anchors: list[str],
    technology_anchors: list[str],
    must_terms: list[str],
    strong_terms: list[str],
    should_terms: list[str],
    support_terms: list[str],
    no_anchor_terms: list[str],
    negative_terms: list[str],
    boundary_rules: dict[str, Any],
    stock_pool_summary: str,
    evidence_note: str,
    quality_score: float = 96.0,
) -> dict[str, Any]:
    return {
        "subject_key": subject_key,
        "subject_name": subject_name,
        "aliases": aliases,
        "entity_anchors": entity_anchors,
        "domain_anchors": domain_anchors,
        "product_anchors": product_anchors,
        "technology_anchors": technology_anchors,
        "event_action_terms": [],
        "must_terms": must_terms,
        "strong_terms": strong_terms,
        "should_terms": should_terms,
        "support_terms": support_terms,
        "weak_terms": [],
        "no_anchor_terms": no_anchor_terms,
        "negative_terms": negative_terms,
        "confusion_subject_keys": [],
        "boundary_rules": boundary_rules,
        "stock_pool_summary": stock_pool_summary,
        "evidence_refs": [{"source": "2026-05-31 runtime attribution", "note": evidence_note}],
        "source_blocks": {
            "repair_reason": evidence_note,
            "generation_mode": "product_runtime_phase3b_20260601",
        },
        "quality_score": quality_score,
        "quality_flags": ["product_runtime_phase3b", "accepted_candidate", "runtime_quarantine_followup"],
        "eval_metrics": {
            "repair_case": subject_key,
            "hard_negative_covered": True,
        },
        "version": 1,
        "status": "accepted_candidate",
    }


PROFILES: list[dict[str, Any]] = [
    _profile(
        subject_key="9054404",
        subject_name="A股全球第一",
        aliases=["A股全球第一", "中国核心资产"],
        entity_anchors=["A股全球第一", "中国核心资产"],
        domain_anchors=["核心资产", "行业龙头"],
        product_anchors=[],
        technology_anchors=[],
        must_terms=["A股全球第一", "中国核心资产"],
        strong_terms=["核心资产", "行业龙头"],
        should_terms=["A股核心资产"],
        support_terms=["A股", "核心资产", "龙头企业"],
        no_anchor_terms=[
            "全球第一",
            "第一",
            "关键地位",
            "强大竞争力",
            "持续创造价值",
            "重要影响力",
            "领先地位",
            "家电第一",
            "军工第一",
            "稀土第一",
            "金融第一",
            "医疗第一",
            "科技第一",
            "新能源第一",
        ],
        negative_terms=["核聚变", "聚变能源", "能源企业合并", "人工智能产业能源", "普通产业介绍"],
        boundary_rules={
            "accept_requires_any": ["A股全球第一", "中国核心资产", "A股核心资产"],
            "reject_if_only_hits": ["全球第一", "第一", "关键地位", "强大竞争力"],
            "reject_domains": ["核聚变", "聚变能源", "能源企业合并", "人工智能产业能源"],
            "nearby_confusions": ["全球第一", "家电第一", "军工第一", "稀土第一"],
        },
        stock_pool_summary="A股核心资产与行业龙头集合，聚焦明确的中国核心资产口径。",
        evidence_note="remove generic first-place anchors and keep only explicit A股核心资产 signals",
    ),
    _profile(
        subject_key="9012396",
        subject_name="新疆自贸区",
        aliases=["新疆自贸区", "中国（新疆）自由贸易试验区", "新疆自由贸易试验区"],
        entity_anchors=["新疆自贸区", "中国（新疆）自由贸易试验区"],
        domain_anchors=["自贸试验区", "自贸区政策", "口岸经济", "跨境贸易"],
        product_anchors=[],
        technology_anchors=[],
        must_terms=["新疆自贸区", "中国（新疆）自由贸易试验区"],
        strong_terms=["自贸试验区", "口岸经济", "跨境贸易"],
        should_terms=["边疆开放", "自由贸易区"],
        support_terms=["开放通道", "中欧班列", "口岸", "跨境物流"],
        no_anchor_terms=[
            "新质生产力",
            "战略性新兴产业",
            "未来产业",
            "国资企业",
            "基建",
            "高科技",
            "绿色能源",
            "绿色环保",
            "数字经济",
            "人工智能",
            "生物制造",
            "商业航天",
            "低空经济",
            "新材料",
            "量子技术",
        ],
        negative_terms=["地方招商项目", "普通产业规划", "新质生产力", "战略性新兴产业"],
        boundary_rules={
            "accept_requires_any": ["新疆自贸区", "中国（新疆）自由贸易试验区", "新疆自由贸易试验区", "自贸试验区"],
            "reject_if_only_hits": ["新质生产力", "战略性新兴产业", "未来产业", "国资企业", "基建"],
            "reject_domains": ["地方招商项目", "普通产业规划"],
            "nearby_confusions": ["新疆", "边疆治理", "自贸区"],
        },
        stock_pool_summary="新疆自贸区及其口岸经济、自贸试验区政策相关口径。",
        evidence_note="remove generic growth anchors that previously polluted the Xinjiang FTZ match",
    ),
    _profile(
        subject_key="9043698",
        subject_name="深海经济",
        aliases=["深海经济", "海洋经济高质量发展", "海洋强国建设"],
        entity_anchors=["深海经济", "海洋经济高质量发展"],
        domain_anchors=["海洋强国建设", "深海资源勘探", "深海资源开发", "海洋工程装备", "深海探测与感知技术"],
        product_anchors=[],
        technology_anchors=[],
        must_terms=["深海经济", "海洋经济高质量发展"],
        strong_terms=["海洋强国建设", "深海资源勘探", "深海资源开发", "海洋工程装备", "深海探测与感知技术"],
        should_terms=["海洋经济发展规划", "海洋产业升级", "海洋开发利用保护"],
        support_terms=["海洋新兴产业", "海洋未来产业", "海洋高端装备", "深海"],
        no_anchor_terms=[
            "全国统一大市场",
            "政府工作报告",
            "全国两会",
            "普通海洋政策",
            "普通港口航运新闻",
            "海洋旅游",
            "海洋渔业",
        ],
        negative_terms=["全国统一大市场", "政府工作报告", "全国两会", "普通海洋政策", "普通港口航运新闻"],
        boundary_rules={
            "accept_requires_any": ["深海经济", "海洋经济高质量发展", "深海资源勘探", "深海资源开发", "海洋工程装备", "深海探测与感知技术"],
            "reject_if_only_hits": ["全国统一大市场", "政府工作报告", "全国两会", "海洋", "航运"],
            "reject_domains": ["普通海洋政策", "普通港口航运新闻"],
            "nearby_confusions": ["海洋经济", "海洋产业", "航运服务"],
        },
        stock_pool_summary="深海经济与海洋强国建设、深海资源开发和海工装备相关口径。",
        evidence_note="remove broad policy-only and generic maritime anchors from the deepsea profile",
    ),
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
        quality_score, quality_flags, eval_metrics, version, status, generated_by, updated_at
    ) VALUES (
        $1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
        $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb,
        $15::jsonb, $16::jsonb, $17::jsonb, $18::jsonb, $19::jsonb, $20::jsonb,
        $21, $22::jsonb, $23::jsonb, $24, $25, $26, now()
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
        generated_by = EXCLUDED.generated_by,
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
                _json(profile["event_action_terms"]),
                _json(profile["must_terms"]),
                _json(profile["strong_terms"]),
                _json(profile["should_terms"]),
                _json(profile["support_terms"]),
                _json(profile["weak_terms"]),
                _json(profile["no_anchor_terms"]),
                _json(profile["negative_terms"]),
                _json(profile["confusion_subject_keys"]),
                _json(profile["boundary_rules"]),
                _json(profile["stock_pool_summary"]),
                _json(profile["evidence_refs"]),
                _json(profile["source_blocks"]),
                float(profile["quality_score"]),
                _json(profile["quality_flags"]),
                _json(profile["eval_metrics"]),
                int(profile["version"]),
                profile["status"],
                "product_runtime_phase3b_20260601",
            )
            count += 1
        return count
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Product Runtime Phase 3B theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    count = run_async(_upsert(args.db_name))
    print(json.dumps({"upserted": count, "db_name": args.db_name}, ensure_ascii=False))


if __name__ == "__main__":
    main()

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


PHASE43_PROFILES: list[dict[str, Any]] = [
    {
        "subject_key": "9028694",
        "subject_name": "高温",
        "aliases": ["高温天气", "极端高温", "热浪"],
        "entity_anchors": [],
        "domain_anchors": ["高温天气", "极端高温", "热浪", "气象灾害"],
        "product_anchors": [],
        "technology_anchors": [],
        "event_action_terms": ["高温预警", "用电负荷上升", "防暑降温"],
        "must_terms": ["高温天气", "极端高温", "热浪"],
        "strong_terms": ["高温预警", "气温突破", "持续高温", "夏季用电"],
        "should_terms": ["防暑降温", "空调负荷", "电力负荷"],
        "support_terms": ["升温", "降温", "温度", "用电"],
        "weak_terms": ["最高温", "温升", "热管理"],
        "no_anchor_terms": ["高温", "最高温", "温升", "芯片温升", "散热", "冷却", "液冷", "微流体冷却"],
        "negative_terms": ["微软", "Corintis", "芯片散热", "服务器液冷", "液冷数据中心", "微流体冷却"],
        "confusion_subject_keys": ["9013689"],
        "boundary_rules": [
            "只有天气、气温、热浪、高温预警、夏季用电负荷等语境才能匹配高温题材。",
            "芯片温升、服务器散热、液冷、微流体冷却属于热管理或液冷技术，不得匹配高温题材。",
            "仅出现“高温/最高温/温升”短词不得作为题材锚点。",
        ],
    },
    {
        "subject_key": "9016841",
        "subject_name": "证券",
        "aliases": ["券商", "券商业"],
        "entity_anchors": ["券商", "投行机构"],
        "domain_anchors": ["资本市场", "证券经纪", "投行业务", "财富管理"],
        "product_anchors": ["证券牌照", "两融业务", "经纪业务"],
        "technology_anchors": [],
        "event_action_terms": ["佣金率变化", "券商业绩", "证券交易活跃"],
        "must_terms": ["券商", "证券经纪", "经纪业务"],
        "strong_terms": ["资本市场", "券商业绩", "证券牌照", "投行业务"],
        "should_terms": ["两融余额", "投行业务", "财富管理"],
        "support_terms": ["研报", "预测", "测算", "指出"],
        "weak_terms": ["证券", "东方证券", "中信证券", "券商研报"],
        "no_anchor_terms": ["证券", "东方证券", "中信证券", "华泰证券", "招商证券", "证券预测", "证券研报", "券商研报"],
        "negative_terms": ["服务器液冷", "液冷数据中心", "谷歌服务器", "东方证券预测", "英伟达", "数据中心"],
        "confusion_subject_keys": ["9013689"],
        "boundary_rules": [
            "研报来源机构中的“证券”不得作为证券题材锚点。",
            "必须出现券商业绩、证券经纪、证券交易、资本市场或证券牌照等证券行业主叙事。",
            "如果新闻主体是服务器液冷、算力、谷歌、微软等产业预测，不得匹配证券题材。",
        ],
    },
    {
        "subject_key": "9011782",
        "subject_name": "一带一路",
        "aliases": ["一带一路", "丝路", "沿线国家"],
        "entity_anchors": ["一带一路", "丝绸之路"],
        "domain_anchors": ["沿线国家", "海外基建", "国际工程", "中欧班列"],
        "product_anchors": ["海外工程项目", "港口铁路项目"],
        "technology_anchors": [],
        "event_action_terms": ["签署合作协议", "海外工程中标", "中欧班列开行"],
        "must_terms": ["一带一路", "沿线国家", "中欧班列"],
        "strong_terms": ["海外基建", "国际工程", "丝绸之路", "互联互通项目"],
        "should_terms": ["港口铁路", "海外项目", "互联互通"],
        "support_terms": ["中国", "海外", "国际", "合作"],
        "weak_terms": ["中国", "商业发射", "航天发射"],
        "no_anchor_terms": ["中国", "中国航天", "商业发射", "航天发射", "发射纪录", "海外", "国际"],
        "negative_terms": ["商业航天", "卫星互联网", "火箭发射", "蓝箭航天", "中国航天", "星链"],
        "confusion_subject_keys": ["9061851", "9062142"],
        "boundary_rules": [
            "必须出现一带一路、沿线国家、中欧班列、海外基建、国际工程等真实政策/项目锚点。",
            "仅出现中国、海外、国际、合作等宽泛词不得匹配一带一路。",
            "中国航天发射、商业发射纪录属于航天/商业航天，不得匹配一带一路。",
        ],
    },
    {
        "subject_key": "9033923",
        "subject_name": "深圳",
        "aliases": ["深圳本地股", "深圳国资", "深圳改革"],
        "entity_anchors": ["深圳国资", "深圳本地股"],
        "domain_anchors": ["深圳先行示范区", "粤港澳大湾区深圳", "深圳改革"],
        "product_anchors": ["深圳国企改革"],
        "technology_anchors": [],
        "event_action_terms": ["深圳政策发布", "深圳国资改革", "深圳本地项目落地"],
        "must_terms": ["深圳本地股", "深圳国资", "深圳先行示范区"],
        "strong_terms": ["深圳改革", "粤港澳大湾区深圳", "先行示范区改革"],
        "should_terms": ["深圳政策", "本地项目", "地方国资"],
        "support_terms": ["深圳", "举办", "召开", "论坛", "峰会"],
        "weak_terms": ["深圳举办", "深圳召开", "会议地点"],
        "no_anchor_terms": ["深圳", "深圳举办", "深圳召开", "深圳论坛", "深圳会议", "深圳峰会", "会议地点"],
        "negative_terms": ["AI智能眼镜", "AR眼镜", "智能眼镜", "投融资论坛", "高峰论坛", "闭门会"],
        "confusion_subject_keys": ["9030409"],
        "boundary_rules": [
            "深圳作为会议地点、活动举办地不得匹配深圳题材。",
            "必须出现深圳本地股、深圳国资、深圳改革、先行示范区或本地政策项目等主叙事。",
            "AI智能眼镜论坛、投融资闭门会等行业会议即使在深圳举办，也不得匹配深圳题材。",
        ],
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
        status = EXCLUDED.status,
        generated_by = EXCLUDED.generated_by,
        version = theme_profile_v2.version + 1,
        updated_at = now()
    """
    try:
        for profile in PHASE43_PROFILES:
            eval_metrics = {
                "generation_mode": "manual_ai",
                "phase": "phase4.3",
                "hard_negative_case_count": 4,
                "role_guard_required": True,
            }
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
                _json({}),
                _json([{"source": "phase4.3_wrong_related_attribution", "subject_key": profile["subject_key"]}]),
                _json({"phase": "phase4.3", "manual_reason": "wrong_related_noise_guard"}),
                88.0,
                _json(["phase4_3_manual_ai"]),
                _json(eval_metrics),
                "draft",
                "phase4_3_role_aware_guard",
            )
        return len(PHASE43_PROFILES)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Phase 4.3 high-risk theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    count = run_async(_upsert(args.db_name))
    print(json.dumps({"db_name": args.db_name, "upserted": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()

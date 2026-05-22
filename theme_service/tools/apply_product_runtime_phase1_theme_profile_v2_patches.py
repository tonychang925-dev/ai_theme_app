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
        "subject_key": "9053827",
        "subject_name": "雅江水电最新互动",
        "aliases": ["雅江水电最新互动", "雅江水电互动易", "雅江水电e互动"],
        "entity_anchors": ["雅江水电"],
        "domain_anchors": ["雅江水电投资者互动", "雅江水电投资者关系"],
        "product_anchors": [],
        "technology_anchors": [],
        "must_terms": ["雅江水电最新互动", "雅江水电互动易", "雅江水电e互动"],
        "strong_terms": ["雅江水电投资者互动", "雅江水电投资者关系"],
        "should_terms": ["雅江水电", "互动易", "e互动", "投资者问答"],
        "support_terms": ["公告", "发布财报", "管理层解读", "路演"],
        "no_anchor_terms": ["公告", "发布财报", "管理层解读", "投资者互动", "互动易", "e互动", "路演"],
        "negative_terms": ["减持公告", "回购公告", "交易所监管公告", "普通公司公告"],
        "boundary_rules": {
            "accept_requires_any": ["雅江水电最新互动", "雅江水电互动易", "雅江水电e互动", "雅江水电投资者互动"],
            "reject_if_only_hits": ["公告", "发布财报", "管理层解读", "投资者互动", "互动易", "e互动"],
            "reject_domains": ["减持公告", "回购公告", "交易监管", "普通公司公告"],
            "nearby_confusions": ["雅江水电站", "投资者关系"],
        },
    },
    {
        "subject_key": "9050084",
        "subject_name": "精酿啤酒",
        "aliases": ["精酿啤酒", "精酿酒馆", "精酿啤酒馆"],
        "entity_anchors": [],
        "domain_anchors": ["精酿啤酒消费", "精酿酒馆"],
        "product_anchors": ["IPA精酿", "精酿IPA", "世涛精酿"],
        "technology_anchors": [],
        "must_terms": ["精酿啤酒", "精酿酒馆", "精酿啤酒馆"],
        "strong_terms": ["IPA精酿", "精酿IPA", "世涛精酿", "精酿啤酒消费"],
        "should_terms": ["啤酒花", "麦芽", "IPA", "世涛", "小酒馆"],
        "support_terms": ["发酵", "酵母", "果啤", "酸啤", "水"],
        "no_anchor_terms": ["水", "麦芽", "酵母", "发酵", "德国", "韩国", "投资"],
        "negative_terms": ["国际政治新闻", "天气灾害新闻", "成品油价格", "普通海外投资"],
        "boundary_rules": {
            "accept_requires_any": ["精酿啤酒", "精酿酒馆", "精酿啤酒馆", "IPA精酿", "世涛精酿"],
            "reject_if_only_hits": ["水", "麦芽", "酵母", "IPA", "世涛"],
            "reject_domains": ["国际政治", "天气灾害", "油价", "海外投资"],
            "nearby_confusions": ["酒", "啤酒"],
        },
    },
    {
        "subject_key": "9022889",
        "subject_name": "著名IP",
        "aliases": ["著名IP", "知名IP"],
        "entity_anchors": [],
        "domain_anchors": ["版权运营", "IP改编", "IP授权"],
        "product_anchors": ["IP衍生品", "影视IP", "动漫IP", "游戏IP"],
        "technology_anchors": [],
        "must_terms": ["著名IP", "知名IP", "IP授权", "IP衍生品"],
        "strong_terms": ["影视IP", "动漫IP", "游戏IP", "版权运营", "IP改编"],
        "should_terms": ["文创作品", "文学版权", "授权", "衍生品", "跨界联名"],
        "support_terms": ["影视", "动漫", "游戏", "版权", "财报", "IPO"],
        "no_anchor_terms": ["IP", "知识产权", "影视", "动漫", "游戏", "财报", "IPO", "递表"],
        "negative_terms": ["普通公司IPO", "普通季度财报", "品牌财报", "知识产权会议"],
        "boundary_rules": {
            "accept_requires_any": ["著名IP", "知名IP", "IP授权", "IP衍生品", "影视IP", "动漫IP", "游戏IP", "IP改编"],
            "reject_if_only_hits": ["IP", "知识产权", "影视", "动漫", "游戏", "财报", "IPO"],
            "reject_domains": ["普通IPO", "普通财报", "知识产权会议"],
            "nearby_confusions": ["短剧", "游戏", "卡牌"],
        },
    },
    {
        "subject_key": "9034920",
        "subject_name": "东方头",
        "aliases": ["东方头", "东方头题材"],
        "entity_anchors": ["东方头"],
        "domain_anchors": [],
        "product_anchors": [],
        "technology_anchors": [],
        "must_terms": ["东方头"],
        "strong_terms": ["东方头题材"],
        "should_terms": [],
        "support_terms": ["金融", "医药医疗", "科技", "能源资源"],
        "no_anchor_terms": ["金融", "医药医疗", "科技", "能源资源", "上市聆讯", "并购基金"],
        "negative_terms": ["普通金融新闻", "普通医药新闻", "普通科技新闻", "上市聆讯", "并购基金"],
        "boundary_rules": {
            "accept_requires_any": ["东方头", "东方头题材"],
            "reject_if_only_hits": ["金融", "医药医疗", "科技", "能源资源"],
            "reject_domains": ["上市聆讯", "并购基金", "泛行业新闻"],
            "nearby_confusions": ["金融", "科技"],
        },
    },
    {
        "subject_key": "9024042",
        "subject_name": "全国文旅",
        "aliases": ["全国文旅", "文旅消费", "文旅项目", "文旅政策"],
        "entity_anchors": [],
        "domain_anchors": ["景区运营", "旅游度假区", "旅游休闲街区", "夜间文旅经济"],
        "product_anchors": [],
        "technology_anchors": [],
        "must_terms": ["全国文旅", "文旅消费", "文旅项目", "文旅政策"],
        "strong_terms": ["景区运营", "旅游度假区", "旅游休闲街区", "夜间文旅经济"],
        "should_terms": ["红色旅游", "乡村旅游", "旅游产品", "景区", "度假区"],
        "support_terms": ["广西", "云南", "福建", "重庆", "低空飞行"],
        "no_anchor_terms": ["广西", "云南", "福建", "重庆", "旅游", "出行"],
        "negative_terms": ["地方灾害新闻", "天气灾害预警", "交通停运", "普通地名新闻"],
        "boundary_rules": {
            "accept_requires_any": ["全国文旅", "文旅消费", "文旅项目", "文旅政策", "景区运营", "旅游度假区", "夜间文旅经济"],
            "reject_if_only_hits": ["广西", "云南", "福建", "重庆", "旅游", "出行"],
            "reject_domains": ["天气灾害", "地震救灾", "列车停运", "普通地方新闻"],
            "nearby_confusions": ["旅游", "地方区域"],
        },
    },
    {
        "subject_key": "9034544",
        "subject_name": "乌克兰重建",
        "aliases": ["乌克兰重建", "乌克兰战后重建", "乌克兰恢复重建"],
        "entity_anchors": ["乌克兰"],
        "domain_anchors": ["乌克兰重建基金", "乌克兰重建项目", "乌克兰基础设施重建"],
        "product_anchors": [],
        "technology_anchors": [],
        "must_terms": ["乌克兰重建", "乌克兰战后重建", "乌克兰恢复重建"],
        "strong_terms": ["乌克兰重建基金", "乌克兰重建项目", "乌克兰基础设施重建"],
        "should_terms": ["排雷", "住房修复", "交通修复", "电力修复"],
        "support_terms": ["能源", "住房", "交通", "电力", "基建"],
        "no_anchor_terms": ["能源", "住房", "交通", "电力", "基建", "欧盟", "俄罗斯"],
        "negative_terms": ["普通能源项目", "普通经济预测", "普通国际政治新闻", "夏令时法案"],
        "boundary_rules": {
            "accept_requires_any": ["乌克兰重建", "乌克兰战后重建", "乌克兰恢复重建", "乌克兰重建基金", "乌克兰重建项目"],
            "reject_if_only_hits": ["能源", "住房", "交通", "电力", "基建", "欧盟", "俄罗斯"],
            "reject_domains": ["普通能源项目", "经济预测", "普通国际政治"],
            "nearby_confusions": ["伊以重建", "地缘政治"],
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
        95.0, $17::jsonb, $18::jsonb, 'accepted_candidate', 'product_runtime_phase1', now()
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
                _json([{"source": "product_runtime_phase1", "subject_key": profile["subject_key"]}]),
                _json({"phase": "product_runtime_phase1", "manual_reason": "high_noise_fallback_repair"}),
                _json(["product_runtime_phase1", "accepted_high_noise_repair"]),
                _json({"phase": "product_runtime_phase1", "requires_main_subject_anchor": True}),
            )
        return len(PROFILES)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Product Runtime Phase 1 accepted theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    print(json.dumps({"db_name": args.db_name, "upserted": run_async(_upsert(args.db_name))}, ensure_ascii=False))


if __name__ == "__main__":
    main()

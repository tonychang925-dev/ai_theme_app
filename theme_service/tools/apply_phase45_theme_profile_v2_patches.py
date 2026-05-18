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


PHASE45_PROFILES: list[dict[str, Any]] = [
    {
        "subject_key": "9064628",
        "subject_name": "Micro LED CPO",
        "aliases": ["Micro LED CPO", "MicroLED CPO", "CPO共封装光学"],
        "entity_anchors": ["CPO", "共封装光学", "MicroLED CPO"],
        "domain_anchors": ["光通信", "光模块", "硅光", "共封装光学"],
        "product_anchors": ["CPO光模块", "光电共封装模块", "硅光模块"],
        "technology_anchors": ["共封装光学", "光电共封装", "硅光集成", "光引擎"],
        "event_action_terms": ["CPO方案发布", "光模块量产", "硅光平台升级", "共封装光学导入"],
        "must_terms": ["CPO", "共封装光学", "光电共封装"],
        "strong_terms": ["硅光", "光模块", "CPO光模块", "硅光模块", "光引擎"],
        "should_terms": ["数据中心光互联", "光通信", "高速光模块"],
        "support_terms": ["Micro LED", "MicroLED", "LED", "产线", "量产", "显示"],
        "weak_terms": ["Micro", "LED", "晶圆制程", "AR显示", "显示屏"],
        "no_anchor_terms": [
            "Micro",
            "LED",
            "Micro LED",
            "MicroLED",
            "MicroLED显示",
            "Micro LED显示",
            "AR眼镜",
            "AI眼镜",
            "智能眼镜",
            "显示屏",
            "产线",
            "量产",
            "晶圆制程",
        ],
        "negative_terms": ["AR眼镜", "AI智能眼镜", "智能眼镜", "MicroLED显示", "Porotech", "鸿海", "显示面板"],
        "confusion_subject_keys": ["9030409", "9037499", "9038540"],
        "boundary_rules": [
            "必须出现CPO、共封装光学、光电共封装、硅光、光模块等光通信锚点，才能匹配本题材。",
            "仅出现Micro、LED、MicroLED显示、AR眼镜显示方案，不得匹配Micro LED CPO。",
            "AR/AI智能眼镜新闻中的MicroLED产线或显示屏描述，默认归属眼镜/显示题材，不作为CPO锚点。",
        ],
    },
    {
        "subject_key": "9032675",
        "subject_name": "金融IT",
        "aliases": ["金融IT", "金融信息化", "金融科技IT"],
        "entity_anchors": ["证券IT", "银行IT", "金融信创"],
        "domain_anchors": ["金融信息化", "证券信息化", "银行信息系统", "金融科技基础设施"],
        "product_anchors": ["核心交易系统", "柜面系统", "财富管理系统", "银行核心系统", "证券交易系统"],
        "technology_anchors": ["金融信创", "分布式核心系统", "交易清算系统"],
        "event_action_terms": ["核心系统替换", "交易系统升级", "金融信创招标", "银行IT改造"],
        "must_terms": ["金融IT", "金融信息化", "证券IT", "银行IT", "金融信创"],
        "strong_terms": ["核心交易系统", "证券交易系统", "银行核心系统", "财富管理系统", "金融科技基础设施"],
        "should_terms": ["清算系统", "柜面系统", "信创改造", "金融机构IT投入"],
        "support_terms": ["投融资", "融资", "金融", "投资", "IT", "科技", "会议", "论坛"],
        "weak_terms": ["投融资闭门会", "融资活动", "金融机构观点", "投资人", "路演"],
        "no_anchor_terms": [
            "金融",
            "IT",
            "投融资",
            "融资",
            "投资",
            "闭门对接",
            "会议",
            "论坛",
            "高峰论坛",
            "科技",
        ],
        "negative_terms": ["AI智能眼镜", "AR眼镜", "智能眼镜", "消费电子", "发布会", "投融资闭门对接"],
        "confusion_subject_keys": ["9030409", "9037499", "9038540"],
        "boundary_rules": [
            "必须出现银行IT、证券IT、金融信创、核心交易系统、金融信息化等行业系统锚点。",
            "论坛、投融资、闭门对接、投资人、金融机构观点不能作为金融IT锚点。",
            "AI/AR智能眼镜投融资会议或消费电子发布会，即使含投融资/金融词，也不得匹配金融IT。",
        ],
    },
    {
        "subject_key": "9022064",
        "subject_name": "碳化硅",
        "aliases": ["碳化硅", "SiC", "碳化硅半导体"],
        "entity_anchors": ["碳化硅", "SiC"],
        "domain_anchors": ["第三代半导体", "碳化硅材料", "碳化硅功率半导体"],
        "product_anchors": ["碳化硅衬底", "碳化硅外延", "碳化硅晶圆", "SiC MOSFET", "碳化硅功率器件"],
        "technology_anchors": ["SiC MOSFET", "碳化硅外延", "碳化硅单晶生长", "高压功率器件"],
        "event_action_terms": ["碳化硅产能投产", "SiC器件量产", "衬底扩产", "外延片认证"],
        "must_terms": ["碳化硅衬底", "碳化硅外延", "SiC MOSFET", "碳化硅功率器件"],
        "strong_terms": ["第三代半导体", "碳化硅晶圆", "碳化硅材料", "SiC器件", "高压功率器件"],
        "should_terms": ["车规级SiC", "功率半导体", "外延片", "衬底扩产"],
        "support_terms": ["碳化硅", "SiC", "材料", "镜片", "显示", "超轻薄"],
        "weak_terms": ["AR眼镜", "AI眼镜", "显示材料", "全彩显示", "镜片极薄"],
        "no_anchor_terms": [
            "碳化硅AR眼镜",
            "碳化硅镜片",
            "AR眼镜",
            "AI眼镜",
            "智能眼镜",
            "超轻薄",
            "全彩显示",
            "显示",
            "镜片",
            "材料展示",
        ],
        "negative_terms": ["AR眼镜", "AI智能眼镜", "智能眼镜", "MicroLED", "Micro LED", "显示面板", "慕德微纳"],
        "confusion_subject_keys": ["9030409", "9037499", "9038540", "9064628"],
        "boundary_rules": [
            "必须出现碳化硅衬底、外延、晶圆、SiC MOSFET、功率器件、第三代半导体等半导体产业锚点。",
            "AR眼镜新闻中“碳化硅镜片/碳化硅AR眼镜/超轻薄显示材料”不得匹配碳化硅半导体题材。",
            "仅出现碳化硅作为消费电子显示材料，不足以进入本题材 related。",
        ],
    },
    {
        "subject_key": "9058849",
        "subject_name": "高通",
        "aliases": ["高通", "Qualcomm"],
        "entity_anchors": ["高通", "Qualcomm", "骁龙", "Snapdragon"],
        "domain_anchors": ["移动芯片", "XR芯片", "智能终端SoC", "基带芯片"],
        "product_anchors": ["骁龙芯片", "Snapdragon平台", "XR芯片平台", "高通SoC", "骁龙XR"],
        "technology_anchors": ["移动SoC", "基带", "AI端侧芯片", "XR芯片"],
        "event_action_terms": ["芯片发布", "平台升级", "芯片供货", "授权合作", "终端搭载骁龙"],
        "must_terms": ["骁龙", "Snapdragon", "高通芯片", "Qualcomm芯片"],
        "strong_terms": ["XR芯片", "移动SoC", "基带芯片", "骁龙XR", "Snapdragon平台"],
        "should_terms": ["终端搭载", "芯片平台", "芯片供货", "移动平台"],
        "support_terms": ["高通", "Qualcomm", "合作", "联手", "参与研发", "合作伙伴"],
        "weak_terms": ["三星谷歌高通", "强强联手", "混合现实", "智能眼镜", "原型产品"],
        "no_anchor_terms": [
            "高通强强联手",
            "三星谷歌高通",
            "合作",
            "联手",
            "参与研发",
            "合作伙伴",
            "混合现实智能眼镜",
            "AR眼镜",
            "AI眼镜",
            "智能眼镜",
        ],
        "negative_terms": ["AR眼镜", "AI智能眼镜", "智能眼镜", "三星", "谷歌", "Meta", "消费电子发布会"],
        "confusion_subject_keys": ["9030409", "9037499", "9031543", "9038540"],
        "boundary_rules": [
            "高通题材必须以高通芯片、骁龙/Snapdragon平台、XR芯片、移动SoC或基带为主叙事。",
            "如果高通只是AR/AI智能眼镜合作方之一，且未出现骁龙/XR芯片/芯片平台等证据，不得进入related。",
            "三星、谷歌、高通联手研发智能眼镜的主题材应优先归入智能穿戴/AR眼镜。",
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
        for profile in PHASE45_PROFILES:
            eval_metrics = {
                "generation_mode": "manual_ai",
                "phase": "phase4.5",
                "hard_negative_case_count": 4,
                "wrong_related_source": True,
                "requires_main_subject_anchor": True,
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
                _json([{"source": "phase4.5_wrong_related_attribution", "subject_key": profile["subject_key"]}]),
                _json({"phase": "phase4.5", "manual_reason": "fallback_wrong_related_noise_guard"}),
                90.0,
                _json(["phase4_5_manual_ai", "wrong_related_source"]),
                _json(eval_metrics),
                "draft",
                "phase4_5_wrong_related_profile_patch",
            )
        return len(PHASE45_PROFILES)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Phase 4.5 wrong-related theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    count = run_async(_upsert(args.db_name))
    print(json.dumps({"db_name": args.db_name, "upserted": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()

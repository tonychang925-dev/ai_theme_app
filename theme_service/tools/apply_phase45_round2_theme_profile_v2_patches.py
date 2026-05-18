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


PHASE45_ROUND2_PROFILES: list[dict[str, Any]] = [
    {
        "subject_key": "9013944",
        "subject_name": "半导体",
        "aliases": ["半导体行业", "半导体板块"],
        "entity_anchors": ["半导体行业", "半导体产业链", "半导体板块"],
        "domain_anchors": ["半导体产业", "集成电路产业"],
        "product_anchors": ["芯片制造", "晶圆制造", "集成电路"],
        "technology_anchors": ["晶圆制造", "集成电路制造", "半导体工艺"],
        "event_action_terms": ["半导体行业景气", "半导体板块上涨", "半导体产业政策"],
        "must_terms": ["半导体行业", "半导体板块"],
        "strong_terms": ["集成电路产业", "半导体景气"],
        "should_terms": ["芯片", "晶圆", "材料", "设备", "封装"],
        "support_terms": ["芯片", "晶圆", "晶圆制造", "材料", "设备", "光刻胶", "封装", "CPO", "ASIC", "存储芯片"],
        "weak_terms": ["国产化", "验证", "扩产", "订单", "客户认证"],
        "no_anchor_terms": ["芯片", "晶圆", "材料", "设备", "半导体设备", "光刻胶", "封装", "CPO", "ASIC", "存储芯片"],
        "negative_terms": ["光刻胶", "半导体设备", "刻蚀机", "薄膜沉积", "先进封装", "CPO", "ASIC芯片", "存储芯片", "服务器液冷"],
        "confusion_subject_keys": ["9018411", "9018472", "9013933", "9036559", "9015778", "9064628"],
        "boundary_rules": [
            "半导体大类只在新闻明确指向半导体行业、半导体产业链或半导体板块时匹配。",
            "如果事件已有光刻胶、半导体设备、先进封装、CPO、ASIC、存储芯片等更具体题材，不得自动 related 到半导体大类。",
            "芯片、晶圆、材料、设备、封装等单词只能作为支持词，不能单独触发 related。",
        ],
    },
    {
        "subject_key": "9036559",
        "subject_name": "ASIC芯片",
        "aliases": ["ASIC芯片", "专用集成电路", "定制ASIC"],
        "entity_anchors": ["ASIC", "专用集成电路", "定制芯片"],
        "domain_anchors": ["AI推理芯片", "专用芯片设计", "ASIC设计"],
        "product_anchors": ["ASIC加速器", "AI ASIC", "TPU", "推理芯片"],
        "technology_anchors": ["专用集成电路设计", "推理加速", "定制芯片架构"],
        "event_action_terms": ["ASIC流片", "ASIC量产", "推理芯片发布", "专用芯片设计"],
        "must_terms": ["ASIC", "专用集成电路", "AI ASIC", "推理芯片"],
        "strong_terms": ["定制芯片", "TPU", "ASIC设计", "AI推理芯片", "专用芯片"],
        "should_terms": ["芯片功耗", "加速器", "数据中心芯片"],
        "support_terms": ["芯片", "AI硬件", "服务器", "功耗", "定制", "可穿戴"],
        "weak_terms": ["服务器液冷", "AR眼镜", "智能眼镜", "散热", "成本控制"],
        "no_anchor_terms": ["芯片", "定制芯片计划", "AI硬件", "服务器", "液冷", "散热", "AR眼镜", "智能眼镜"],
        "negative_terms": ["AR眼镜", "智能眼镜", "液冷", "服务器液冷", "数据中心液冷", "微流体冷却", "散热"],
        "confusion_subject_keys": ["9030409", "9013689", "9016139", "9037857"],
        "boundary_rules": [
            "只有事件主对象是ASIC、专用集成电路、AI推理芯片、TPU或专用芯片设计时，才可匹配ASIC芯片。",
            "仅出现芯片、AI硬件、服务器、液冷、散热、AR眼镜，不得匹配ASIC芯片。",
            "可穿戴设备中的定制芯片计划如果主线是AR/AI眼镜，应优先归入眼镜题材。",
        ],
    },
    {
        "subject_key": "9016139",
        "subject_name": "服务器",
        "aliases": ["服务器", "AI服务器", "服务器整机"],
        "entity_anchors": ["AI服务器", "服务器整机", "服务器出货"],
        "domain_anchors": ["服务器产业链", "AI服务器产业链", "服务器供应链"],
        "product_anchors": ["服务器整机", "AI服务器", "GPU服务器", "机架式服务器"],
        "technology_anchors": ["服务器架构", "整机集成", "服务器主板"],
        "event_action_terms": ["服务器出货", "服务器订单", "服务器供应链扩产"],
        "must_terms": ["AI服务器", "服务器整机", "服务器出货"],
        "strong_terms": ["GPU服务器", "整机集成", "服务器主板"],
        "should_terms": ["机柜", "云厂商采购", "服务器需求"],
        "support_terms": ["服务器", "机柜", "液冷", "数据中心", "芯片", "功耗"],
        "weak_terms": ["服务器液冷", "机柜液冷", "散热", "价值量"],
        "no_anchor_terms": ["服务器", "服务器液冷", "机柜液冷", "液冷", "散热", "芯片功耗", "数据中心芯片"],
        "negative_terms": ["液冷数据中心", "微流体冷却", "ASIC芯片", "存储芯片", "AI芯片", "数据中心"],
        "confusion_subject_keys": ["9013689", "9036559", "9015778", "9037857"],
        "boundary_rules": [
            "服务器题材必须以服务器整机、AI服务器出货、服务器订单或服务器供应链为主叙事。",
            "液冷只是服务器散热技术，不能单独触发服务器 related。",
            "AI芯片、TPU、GPU需求事件没有服务器整机证据时，不得匹配服务器。",
        ],
    },
    {
        "subject_key": "9037857",
        "subject_name": "数据中心",
        "aliases": ["数据中心", "IDC", "算力中心"],
        "entity_anchors": ["数据中心", "IDC", "算力中心"],
        "domain_anchors": ["数据中心建设", "IDC建设", "云基础设施"],
        "product_anchors": ["数据中心园区", "IDC机房", "算力中心项目"],
        "technology_anchors": ["机房基础设施", "云计算基础设施", "算力基础设施"],
        "event_action_terms": ["数据中心建设", "IDC扩建", "算力中心开工", "云厂商资本开支"],
        "must_terms": ["数据中心建设", "IDC", "算力中心", "数据中心项目"],
        "strong_terms": ["云基础设施", "机房建设", "算力中心建设", "数据中心园区"],
        "should_terms": ["云厂商资本开支", "机柜", "PUE", "液冷机房"],
        "support_terms": ["数据中心", "服务器", "芯片", "液冷", "算力", "机柜"],
        "weak_terms": ["太空数据中心", "芯片散热", "服务器液冷", "AI芯片需求"],
        "no_anchor_terms": ["数据中心芯片", "服务器液冷", "芯片散热", "微流体冷却", "太空数据中心", "AI芯片需求"],
        "negative_terms": ["液冷数据中心", "微流体冷却", "卫星互联网", "商业航天", "太空数据中心", "ASIC芯片"],
        "confusion_subject_keys": ["9013689", "9062142", "9019807", "9036559"],
        "boundary_rules": [
            "数据中心题材只在数据中心建设、IDC、算力中心、云厂商资本开支为主叙事时匹配。",
            "芯片散热、服务器液冷、微流体冷却不能单独 related 到数据中心。",
            "太空数据中心若主线是卫星/商业航天，应优先归入航天族群。",
        ],
    },
    {
        "subject_key": "9015778",
        "subject_name": "存储芯片",
        "aliases": ["存储芯片", "存储器", "DRAM", "NAND", "HBM"],
        "entity_anchors": ["DRAM", "NAND", "HBM", "存储器", "存储芯片"],
        "domain_anchors": ["存储半导体", "存储器产业链", "半导体存储"],
        "product_anchors": ["DRAM芯片", "NAND Flash", "HBM内存", "SSD主控", "存储颗粒"],
        "technology_anchors": ["3D NAND", "DRAM制程", "HBM堆叠", "混合键合"],
        "event_action_terms": ["存储芯片涨价", "存储器扩产", "HBM供货", "NAND涨价"],
        "must_terms": ["DRAM", "NAND", "HBM", "存储芯片", "存储器"],
        "strong_terms": ["3D NAND", "HBM内存", "存储颗粒", "NAND Flash", "DRAM芯片"],
        "should_terms": ["SSD", "内存", "闪存", "存储涨价"],
        "support_terms": ["芯片", "服务器", "数据中心", "AI", "电脑", "手机"],
        "weak_terms": ["数据中心芯片", "服务器芯片", "AI芯片需求", "移动设备"],
        "no_anchor_terms": ["芯片", "服务器", "数据中心芯片", "AI芯片", "移动设备", "手机", "个人电脑"],
        "negative_terms": ["液冷", "服务器液冷", "ASIC芯片", "AI芯片", "GPU", "数据中心建设"],
        "confusion_subject_keys": ["9013689", "9036559", "9016139", "9037857"],
        "boundary_rules": [
            "存储芯片必须出现DRAM、NAND、HBM、存储器、存储颗粒或存储涨价等锚点。",
            "服务器、数据中心、AI芯片、芯片需求不能单独触发存储芯片。",
            "液冷机柜、TPU/GPU需求和服务器散热事件不得 related 到存储芯片。",
        ],
    },
    {
        "subject_key": "9022415",
        "subject_name": "多模态大模型",
        "aliases": ["多模态大模型", "多模态模型", "文生视频模型", "视觉语言模型"],
        "entity_anchors": ["多模态大模型", "多模态模型", "视觉语言模型"],
        "domain_anchors": ["大模型", "生成式AI", "AI模型能力"],
        "product_anchors": ["文生视频模型", "图文多模态模型", "语音多模态模型", "视频生成模型"],
        "technology_anchors": ["图文理解", "视频生成", "语音识别", "跨模态推理"],
        "event_action_terms": ["模型发布", "模型升级", "多模态能力开放", "视频生成能力上线"],
        "must_terms": ["多模态大模型", "多模态模型", "视觉语言模型", "文生视频模型"],
        "strong_terms": ["视频生成模型", "图文理解", "跨模态推理", "语音多模态", "模型发布"],
        "should_terms": ["文本转视频", "图像理解", "语音交互", "模型能力"],
        "support_terms": ["文本", "视频", "AI", "生成", "智能体", "眼镜", "论坛"],
        "weak_terms": ["AI智能体", "AI眼镜", "端侧AI", "高峰论坛", "投融资"],
        "no_anchor_terms": ["文本", "视频", "AI", "智能体", "端侧AI", "AI眼镜", "智能眼镜", "论坛", "投融资"],
        "negative_terms": ["AI智能体Manus", "Manus", "AI眼镜", "智能眼镜", "数据中心", "融资", "论坛"],
        "confusion_subject_keys": ["9062682", "9030409", "9037857"],
        "boundary_rules": [
            "多模态大模型必须以模型发布、模型训练/推理、多模态能力升级或视频/图像/语音模型为主叙事。",
            "Manus/AI智能体产品功能如果主线是任务执行或Agent，不得仅因文生视频 related 到多模态大模型。",
            "AI硬件、智能眼镜、数据中心建设、融资论坛不能仅因AI或视频词匹配多模态大模型。",
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
        for profile in PHASE45_ROUND2_PROFILES:
            eval_metrics = {
                "generation_mode": "manual_ai",
                "phase": "phase4.5_round2",
                "hard_negative_case_count": 12,
                "wrong_related_source": True,
                "related_policy": "broad_category_strict",
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
                _json([{"source": "phase4.5_round2_wrong_related_attribution", "subject_key": profile["subject_key"]}]),
                _json({"phase": "phase4.5_round2", "manual_reason": "broad_category_related_noise_guard"}),
                90.0,
                _json(["phase4_5_round2_manual_ai", "broad_category_strict"]),
                _json(eval_metrics),
                "draft",
                "phase4_5_round2_profile_patch",
            )
        return len(PHASE45_ROUND2_PROFILES)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Phase 4.5 round2 broad-category theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    count = run_async(_upsert(args.db_name))
    print(json.dumps({"db_name": args.db_name, "upserted": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()

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


PHASE2_ACCEPTED_PROFILES: list[dict[str, Any]] = [
    {
        "subject_key": "9062416",
        "subject_name": "中石化重组",
        "aliases": ["中石化重组", "中国石化重组"],
        "entity_anchors": ["中国石化", "中国石油化工集团", "中国航油"],
        "domain_anchors": ["央企重组", "能源央企整合"],
        "product_anchors": [],
        "technology_anchors": [],
        "event_action_terms": ["中石化重组", "中国石化重组", "中国航油重组"],
        "must_terms": ["中石化重组", "中国石化重组", "中国航油重组"],
        "strong_terms": ["中国石化", "中国石油化工集团", "中国航油", "央企重组"],
        "should_terms": ["能源央企整合", "重组获批"],
        "support_terms": ["重组", "批准", "集团", "能源"],
        "weak_terms": ["央企", "整合"],
        "no_anchor_terms": ["重组", "批准", "集团", "能源", "央企", "整合"],
        "negative_terms": ["并购重组泛新闻", "地方国企重组", "石油价格"],
        "confusion_subject_keys": [],
        "boundary_rules": {
            "accept_requires_any": ["中石化重组", "中国石化重组", "中国航油重组"],
            "reject_if_only_hits": ["重组", "批准", "集团", "能源"],
            "reject_domains": ["泛并购重组", "石油价格"],
            "nearby_confusions": ["央企重组"],
        },
    },
    {
        "subject_key": "9057205",
        "subject_name": "哪吒汽车重组",
        "aliases": ["哪吒汽车重组", "哪吒汽车", "合众新能源"],
        "entity_anchors": ["哪吒汽车", "合众新能源"],
        "domain_anchors": ["汽车破产重整", "新能源汽车重整"],
        "product_anchors": ["哪吒汽车"],
        "technology_anchors": [],
        "event_action_terms": ["破产重整", "重整投资人招募", "战略投资人进场"],
        "must_terms": ["哪吒汽车重组", "哪吒汽车", "合众新能源"],
        "strong_terms": ["破产重整", "重整投资人", "战略投资人"],
        "should_terms": ["山子高科", "交接清退", "投资人预招募"],
        "support_terms": ["重组", "合作", "供应商", "参股"],
        "weak_terms": ["汽车公司", "新能源车"],
        "no_anchor_terms": ["重组", "合作", "供应商", "参股", "汽车公司", "新能源车"],
        "negative_terms": ["普通汽车合作", "供应商合作", "零部件参股"],
        "confusion_subject_keys": [],
        "boundary_rules": {
            "accept_requires_any": ["哪吒汽车重组", "哪吒汽车", "合众新能源"],
            "reject_if_only_hits": ["重组", "合作", "供应商", "参股"],
            "reject_domains": ["汽车零部件合作"],
            "nearby_confusions": ["新能源汽车产业链"],
        },
    },
    {
        "subject_key": "9062142",
        "subject_name": "蓝箭航天IPO",
        "aliases": ["蓝箭航天IPO", "蓝箭航天上市", "蓝箭航天递表", "蓝箭航天招股书"],
        "entity_anchors": ["蓝箭航天", "朱雀火箭", "朱雀三号"],
        "domain_anchors": ["民营火箭", "商业航天上市"],
        "product_anchors": ["朱雀三号", "液氧甲烷火箭"],
        "technology_anchors": ["液氧甲烷运载火箭"],
        "event_action_terms": ["蓝箭航天IPO", "蓝箭航天上市", "蓝箭航天递表", "蓝箭航天招股书", "蓝箭航天IPO申报"],
        "must_terms": ["蓝箭航天IPO", "蓝箭航天上市", "蓝箭航天递表", "蓝箭航天招股书", "蓝箭航天IPO申报"],
        "strong_terms": ["商业航天上市", "招股说明书披露"],
        "should_terms": ["民营火箭", "招股说明书", "上交所披露"],
        "support_terms": ["IPO", "供货", "参股", "公司", "商业航天"],
        "weak_terms": ["供应商", "发射链路"],
        "no_anchor_terms": ["IPO", "供货", "参股", "公司", "商业航天", "供应商", "发射链路", "蓝箭航天", "朱雀火箭", "朱雀三号", "运载火箭"],
        "negative_terms": ["太空数据中心", "卫星互联网泛新闻", "供应商参股", "可回收火箭", "火箭回收", "海上回收平台", "首飞计划"],
        "confusion_subject_keys": [],
        "boundary_rules": {
            "accept_requires_any": ["蓝箭航天IPO", "蓝箭航天上市", "蓝箭航天递表", "蓝箭航天招股书", "蓝箭航天IPO申报"],
            "reject_if_only_hits": ["IPO", "供货", "参股", "公司", "商业航天", "蓝箭航天", "朱雀火箭", "朱雀三号", "运载火箭"],
            "reject_domains": ["卫星互联网泛新闻", "太空数据中心", "可回收火箭试验", "火箭回收验证"],
            "nearby_confusions": ["商业航天", "可回收火箭"],
        },
    },
    {
        "subject_key": "9026444",
        "subject_name": "染料",
        "aliases": ["染料", "分散染料", "活性染料"],
        "entity_anchors": ["染料", "分散染料", "活性染料"],
        "domain_anchors": ["染料产业", "染料中间体", "印染化工"],
        "product_anchors": ["间苯二胺", "染料中间体"],
        "technology_anchors": [],
        "event_action_terms": ["染料涨价", "染料中间体涨价", "分散染料供给收缩"],
        "must_terms": ["染料", "分散染料", "染料中间体"],
        "strong_terms": ["活性染料", "染料涨价", "间苯二胺"],
        "should_terms": ["印染", "助剂", "化工"],
        "support_terms": ["产品", "原料", "助剂"],
        "weak_terms": ["化工原料"],
        "no_anchor_terms": ["产品", "原料", "助剂", "化工原料"],
        "negative_terms": ["医药原料", "食品原料", "电池原料"],
        "confusion_subject_keys": [],
        "boundary_rules": {
            "accept_requires_any": ["染料", "分散染料", "活性染料", "染料中间体"],
            "reject_if_only_hits": ["产品", "原料", "助剂"],
            "reject_domains": ["医药原料", "食品原料", "电池原料"],
            "nearby_confusions": ["化工原料"],
        },
    },
    {
        "subject_key": "9047066",
        "subject_name": "淘宝",
        "aliases": ["淘宝", "淘宝出海", "淘宝跨境"],
        "entity_anchors": ["淘宝", "阿里淘宝"],
        "domain_anchors": ["淘宝跨境电商", "淘宝海外业务"],
        "product_anchors": ["淘宝App", "淘宝海外站"],
        "technology_anchors": [],
        "event_action_terms": ["淘宝海外下载量提升", "淘宝跨境服务调整", "淘宝出海"],
        "must_terms": ["淘宝", "淘宝出海", "淘宝跨境"],
        "strong_terms": ["淘宝App", "淘宝海外站", "淘宝海外下载量"],
        "should_terms": ["跨境电商", "多语言适配", "海外消费者"],
        "support_terms": ["跨境电商", "服务", "物流", "支付", "供应链"],
        "weak_terms": ["跨境物流", "海外流量"],
        "no_anchor_terms": ["跨境电商", "服务", "物流", "支付", "供应链", "海外流量"],
        "negative_terms": ["跨境电商泛行业", "物流服务商", "支付服务商"],
        "confusion_subject_keys": [],
        "boundary_rules": {
            "accept_requires_any": ["淘宝", "淘宝出海", "淘宝跨境"],
            "reject_if_only_hits": ["跨境电商", "服务", "物流", "支付", "供应链"],
            "reject_domains": ["跨境电商泛行业"],
            "nearby_confusions": ["跨境电商"],
        },
    },
    {
        "subject_key": "9059060",
        "subject_name": "乐聚IPO",
        "aliases": ["乐聚IPO", "乐聚机器人IPO", "Leju Robotics IPO", "深圳乐聚IPO"],
        "entity_anchors": ["乐聚", "乐聚机器人", "Leju Robotics", "深圳乐聚"],
        "domain_anchors": ["人形机器人上市", "机器人IPO"],
        "product_anchors": ["乐聚人形机器人"],
        "technology_anchors": [],
        "event_action_terms": ["乐聚机器人IPO", "乐聚机器人上市", "乐聚机器人递表", "乐聚机器人辅导备案", "乐聚机器人招股书"],
        "must_terms": ["乐聚IPO", "乐聚机器人IPO", "乐聚机器人上市", "乐聚机器人递表", "乐聚机器人辅导备案", "乐聚机器人招股书", "Leju Robotics IPO", "深圳乐聚IPO"],
        "strong_terms": ["乐聚机器人辅导", "乐聚人形机器人IPO", "乐聚港股上市", "乐聚科创板上市", "乐聚创业板上市"],
        "should_terms": ["招股", "上市辅导", "上市申请", "人形机器人"],
        "support_terms": ["乐聚", "乐聚机器人", "Leju Robotics", "深圳乐聚", "合作商", "参股", "公司", "IPO", "上市", "递表", "招股书", "辅导备案", "港股上市", "科创板上市", "创业板上市", "上市申请", "机器人", "人形机器人", "融资", "产业链"],
        "weak_terms": ["机器人", "人形机器人"],
        "no_anchor_terms": ["乐聚", "乐聚机器人", "Leju Robotics", "深圳乐聚", "合作商", "参股", "公司", "IPO", "上市", "递表", "招股书", "辅导备案", "港股上市", "科创板上市", "创业板上市", "上市申请", "机器人", "人形机器人", "融资", "产业链"],
        "negative_terms": ["普通合作商", "参股公告", "供应商合作", "机器人展会", "普通IPO", "其他公司IPO", "宇树机器人", "云深处机器人", "优必选", "特斯拉机器人", "机器人泛行业", "乐居", "乐居控股", "房地产平台"],
        "confusion_subject_keys": [],
        "boundary_rules": {
            "accept_requires_any": ["乐聚IPO", "乐聚机器人IPO", "乐聚机器人上市", "乐聚机器人递表", "乐聚机器人辅导备案", "乐聚机器人招股书", "Leju Robotics IPO", "深圳乐聚IPO"],
            "reject_if_only_hits": ["乐聚", "乐聚机器人", "IPO", "上市", "机器人", "人形机器人", "合作商", "参股", "公司"],
            "reject_domains": ["普通合作", "参股公告", "机器人展会", "普通IPO", "其他公司IPO", "乐居控股", "房地产平台"],
            "nearby_confusions": ["宇树机器人", "云深处机器人", "优必选", "特斯拉机器人", "机器人", "IPO", "乐居"],
        },
    },
    {
        "subject_key": "9061242",
        "subject_name": "太空光伏",
        "aliases": ["太空光伏", "空间光伏", "天基太阳能"],
        "entity_anchors": ["太空光伏", "空间光伏"],
        "domain_anchors": ["空间太阳能", "航天器供能", "天基太阳能"],
        "product_anchors": ["空间太阳能电站", "太空太阳能电站", "卫星太阳能电站", "空间电站"],
        "technology_anchors": ["空间太阳能发电", "在轨发电", "微波输电", "无线能量传输"],
        "event_action_terms": ["太空光伏在轨供能", "空间太阳能发电", "空间电站建设"],
        "must_terms": ["太空光伏", "空间光伏", "空间太阳能电站", "天基太阳能", "太空太阳能电站", "空间太阳能发电", "在轨发电", "卫星太阳能电站", "微波输电", "无线能量传输", "空间电站"],
        "strong_terms": ["空间太阳能电池", "太空光伏组件", "钙钛矿太空光伏", "卫星光伏电池"],
        "should_terms": ["卫星供电", "在轨供能", "航天器能源", "太阳能", "电站", "发电", "储能"],
        "support_terms": ["SpaceX", "总成", "部件与材料", "设备", "产品", "光伏", "太阳能", "电站", "发电", "储能"],
        "weak_terms": ["光伏组件", "普通太阳能发电"],
        "no_anchor_terms": ["SpaceX", "总成", "部件与材料", "设备", "产品", "光伏", "太阳能", "电站", "发电", "储能"],
        "negative_terms": ["SpaceX供应链", "地面光伏电站", "户用光伏", "普通光伏装机", "地面光伏", "分布式光伏", "集中式光伏", "光伏组件", "光伏玻璃", "硅片", "电池片", "逆变器", "TOPCon", "HJT", "BC电池", "钙钛矿", "光伏装机", "光伏电站运营", "普通太阳能发电"],
        "confusion_subject_keys": [],
        "boundary_rules": {
            "accept_requires_any": ["太空光伏", "空间光伏", "空间太阳能电站", "天基太阳能", "太空太阳能电站", "空间太阳能发电", "在轨发电", "卫星太阳能电站", "微波输电", "无线能量传输", "空间电站"],
            "reject_if_only_hits": ["SpaceX", "总成", "部件与材料", "设备", "产品", "光伏", "太阳能", "电站", "发电", "储能"],
            "reject_domains": ["地面光伏电站", "户用光伏", "普通光伏装机", "地面光伏", "分布式光伏", "集中式光伏", "光伏组件", "光伏玻璃", "逆变器", "TOPCon", "HJT", "BC电池", "钙钛矿", "光伏电站运营", "普通太阳能发电"],
            "nearby_confusions": ["SpaceX供应链", "地面光伏", "光伏组件", "光伏电站运营"],
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
        $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb,
        $15::jsonb, $16::jsonb, $17::jsonb, '{}'::jsonb, $18::jsonb, $19::jsonb,
        95.0, $20::jsonb, $21::jsonb, 'accepted_candidate', 'gate_repair_phase2', now()
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
        for profile in PHASE2_ACCEPTED_PROFILES:
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
                _json([{"source": "gate_repair_phase2", "subject_key": profile["subject_key"]}]),
                _json({"phase": "gate_repair_phase2", "manual_reason": "accepted_a_gate_rebuild"}),
                _json(["gate_repair_phase2", "accepted_a_rebuild"]),
                _json(
                    {
                        "generation_mode": "manual_ai",
                        "phase": "gate_repair_phase2",
                        "requires_main_subject_anchor": True,
                    }
                ),
            )
        return len(PHASE2_ACCEPTED_PROFILES)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Gate Repair Phase 2 accepted theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    print(json.dumps({"db_name": args.db_name, "upserted": run_async(_upsert(args.db_name))}, ensure_ascii=False))


if __name__ == "__main__":
    main()

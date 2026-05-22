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
    {
        "subject_key": "9051378",
        "subject_name": "陆军",
        "aliases": ["陆军装备", "陆军现代化", "陆战装备"],
        "entity_anchors": [],
        "domain_anchors": ["陆军装备采购", "地面无人作战", "陆战装备体系"],
        "product_anchors": ["地面作战装备", "机器狼群协同作战", "无人机蜂群陆战"],
        "technology_anchors": [],
        "must_terms": ["陆军装备", "陆军现代化", "地面作战装备"],
        "strong_terms": ["陆军装备采购", "地面无人作战", "陆战装备体系"],
        "should_terms": ["装甲装备", "地面火力", "陆军演训", "无人地面平台", "野战防空"],
        "support_terms": ["军工装备", "作战体系", "装备采购", "军队", "军方"],
        "no_anchor_terms": ["陆军", "军方", "军队", "军事", "谈判", "外交", "伊朗", "以色列", "回应", "声明"],
        "negative_terms": ["外交谈判", "地缘政治表态", "国际冲突表态", "军方外交声明", "非陆军装备采购"],
        "boundary_rules": {
            "accept_requires_any": ["陆军装备", "陆军现代化", "地面作战装备", "陆军装备采购", "地面无人作战", "陆战装备体系"],
            "reject_if_only_hits": ["陆军", "军方", "军队", "军事", "回应", "声明"],
            "reject_domains": ["外交谈判", "地缘政治表态", "国际冲突表态", "非装备采购"],
            "nearby_confusions": ["导弹", "无人机", "国际军事新闻"],
        },
    },
    {
        "subject_key": "9059230",
        "subject_name": "美国缺电",
        "aliases": ["美国缺电", "美国电力短缺", "美国电力供应不足"],
        "entity_anchors": ["美国"],
        "domain_anchors": ["美国电网压力", "美国数据中心用电激增", "美国AI算力用电"],
        "product_anchors": [],
        "technology_anchors": [],
        "must_terms": ["美国缺电", "美国电力短缺", "美国电力供应不足"],
        "strong_terms": ["美国电网压力", "美国数据中心用电激增", "AI数据中心用电", "美国AI算力用电"],
        "should_terms": ["美国电网", "数据中心负荷", "电力供应缺口", "算力中心用电", "电网扩容"],
        "support_terms": ["电力", "电力设备", "能源", "用电", "电力生产"],
        "no_anchor_terms": ["电力", "电力设备", "能源", "用电", "电费", "数据中心", "股东减持"],
        "negative_terms": ["公司股东减持", "普通电力设备新闻", "普通能源项目", "非美国电网压力"],
        "boundary_rules": {
            "accept_requires_any": ["美国缺电", "美国电力短缺", "美国电力供应不足", "美国电网压力", "美国数据中心用电激增", "美国AI算力用电"],
            "reject_if_only_hits": ["电力", "电力设备", "能源", "用电", "数据中心"],
            "reject_domains": ["股东减持", "普通电力设备", "普通能源项目", "非美国电力新闻"],
            "nearby_confusions": ["电力运营", "电网设备", "AI算力"],
        },
    },
    {
        "subject_key": "9020124",
        "subject_name": "天然气重卡",
        "aliases": ["天然气重卡", "LNG重卡", "燃气重卡", "CNG重卡"],
        "entity_anchors": [],
        "domain_anchors": ["天然气商用车", "LNG商用车", "重卡运输"],
        "product_anchors": ["燃气发动机", "重卡气瓶系统"],
        "technology_anchors": [],
        "must_terms": ["天然气重卡", "LNG重卡", "燃气重卡"],
        "strong_terms": ["CNG重卡", "天然气商用车", "LNG商用车", "燃气重卡销量"],
        "should_terms": ["重卡运输", "物流卡车", "气瓶系统", "燃气发动机", "重卡渗透率"],
        "support_terms": ["天然气", "LNG", "CNG", "重卡", "商用车"],
        "no_anchor_terms": ["天然气", "LNG", "CNG", "重卡", "商用车", "新能源汽车", "汽车财报", "蔚来", "理想", "小鹏"],
        "negative_terms": ["乘用车季度财报", "新能源汽车销量", "普通LNG项目", "LNG接收站", "燃气发电"],
        "boundary_rules": {
            "accept_requires_any": ["天然气重卡", "LNG重卡", "燃气重卡", "CNG重卡", "天然气商用车", "LNG商用车"],
            "reject_if_only_hits": ["天然气", "LNG", "CNG", "重卡", "商用车"],
            "reject_domains": ["乘用车财报", "新能源汽车", "普通天然气项目", "燃气发电"],
            "nearby_confusions": ["天然气", "商用车", "乘用车"],
        },
    },
    {
        "subject_key": "9023110",
        "subject_name": "AI手机",
        "aliases": ["AI手机", "端侧AI手机", "手机大模型"],
        "entity_anchors": [],
        "domain_anchors": ["手机端侧AI", "手机厂商AI功能", "AI手机终端"],
        "product_anchors": ["AI OS手机", "手机AI助手"],
        "technology_anchors": ["端侧大模型"],
        "must_terms": ["AI手机", "手机大模型", "端侧AI手机"],
        "strong_terms": ["手机端侧AI", "AI OS手机", "AI手机终端", "手机厂商AI功能"],
        "should_terms": ["手机智能体", "端侧大模型", "手机AI助手", "AI影像手机", "手机操作系统AI"],
        "support_terms": ["AI", "手机", "终端", "消费电子", "算力"],
        "no_anchor_terms": ["AI", "手机", "终端", "消费电子", "投资机会", "重庆", "产业清单", "地方招商"],
        "negative_terms": ["重庆投资机会清单", "普通手机出货", "普通消费电子新闻", "非手机AI应用", "地方招商项目"],
        "boundary_rules": {
            "accept_requires_any": ["AI手机", "手机大模型", "端侧AI手机", "手机端侧AI", "AI OS手机", "手机厂商AI功能"],
            "reject_if_only_hits": ["AI", "手机", "终端", "消费电子", "算力"],
            "reject_domains": ["地方招商", "投资机会清单", "普通手机出货", "非手机AI应用"],
            "nearby_confusions": ["AI PC", "AI眼镜", "消费电子"],
        },
    },
    {
        "subject_key": "9013587",
        "subject_name": "传媒",
        "aliases": ["影视传媒", "传媒内容平台", "广告营销传媒"],
        "entity_anchors": [],
        "domain_anchors": ["短剧内容平台", "院线传媒", "出版传媒", "IP运营传媒"],
        "product_anchors": ["影视制作", "游戏发行", "广告营销"],
        "technology_anchors": [],
        "must_terms": ["影视传媒", "传媒内容平台", "广告营销传媒"],
        "strong_terms": ["短剧内容平台", "院线传媒", "出版传媒", "游戏传媒", "IP运营传媒"],
        "should_terms": ["影视制作", "游戏发行", "广告营销", "内容平台", "院线", "出版", "短剧", "IP运营"],
        "support_terms": ["媒体", "宣传", "内容", "平台", "政策"],
        "no_anchor_terms": ["媒体", "发布", "宣传", "内容", "平台", "政策", "商务部", "乡村振兴"],
        "negative_terms": ["商务部乡村振兴", "政府宣传报道", "普通政策发布", "非传媒行业政策"],
        "boundary_rules": {
            "accept_requires_any": ["影视传媒", "传媒内容平台", "广告营销传媒", "短剧内容平台", "院线传媒", "出版传媒", "IP运营传媒"],
            "reject_if_only_hits": ["媒体", "发布", "宣传", "内容", "平台", "政策"],
            "reject_domains": ["政府宣传", "政策发布", "乡村振兴", "普通公告"],
            "nearby_confusions": ["著名IP", "游戏", "政府宣传"],
        },
    },
    {
        "subject_key": "9046378",
        "subject_name": "东盟自贸区",
        "aliases": ["东盟自贸区", "中国东盟自贸区", "中国东盟自由贸易区"],
        "entity_anchors": ["东盟"],
        "domain_anchors": ["东盟自由贸易区", "东盟贸易协定", "中国东盟经贸合作"],
        "product_anchors": [],
        "technology_anchors": [],
        "must_terms": ["东盟自贸区", "中国东盟自贸区", "中国东盟自由贸易区"],
        "strong_terms": ["东盟自由贸易区", "东盟贸易协定", "中国东盟经贸合作"],
        "should_terms": ["东盟", "自贸区升级", "区域贸易", "关税安排", "经贸往来"],
        "support_terms": ["消费", "交通", "贸易", "进口", "出口"],
        "no_anchor_terms": ["消费", "交通", "英国", "消费者信心", "零售", "宏观数据"],
        "negative_terms": ["英国消费者信心指数", "非东盟消费数据", "普通宏观经济数据"],
        "boundary_rules": {
            "accept_requires_any": ["东盟自贸区", "中国东盟自贸区", "中国东盟自由贸易区", "东盟自由贸易区", "东盟贸易协定"],
            "reject_if_only_hits": ["消费", "交通", "零售", "贸易"],
            "reject_domains": ["英国宏观数据", "普通消费数据", "非东盟经济新闻"],
            "nearby_confusions": ["消费", "宏观数据", "其他自贸区"],
        },
    },
    {
        "subject_key": "9050371",
        "subject_name": "工业智能体",
        "aliases": ["工业智能体", "工业AI智能体", "工业软件智能体"],
        "entity_anchors": [],
        "domain_anchors": ["工业自动化智能体", "工业物联网智能体", "制造业智能体"],
        "product_anchors": ["工业软件智能体"],
        "technology_anchors": ["工业边缘AI"],
        "must_terms": ["工业智能体", "工业AI智能体", "工业软件智能体"],
        "strong_terms": ["工业自动化智能体", "工业边缘AI", "工业物联网智能体", "制造业智能体"],
        "should_terms": ["工业软件", "工业自动化", "工业物联网", "边缘计算", "制造执行"],
        "support_terms": ["人工智能", "AI系统", "智能体", "平台", "软件"],
        "no_anchor_terms": ["人工智能", "AI", "AI系统", "医疗", "肥胖", "医学", "图灵测试", "尖端模型"],
        "negative_terms": ["医学AI研究", "医疗AI系统", "肥胖医学评估", "通用AI模型新闻"],
        "boundary_rules": {
            "accept_requires_any": ["工业智能体", "工业AI智能体", "工业软件智能体", "工业自动化智能体", "工业物联网智能体", "制造业智能体"],
            "reject_if_only_hits": ["人工智能", "AI", "AI系统", "智能体", "工业软件"],
            "reject_domains": ["医学AI", "通用AI研究", "模型治理", "医疗评估"],
            "nearby_confusions": ["人工智能硬件", "医疗AI", "通用AI智能体"],
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
        95.0, $17::jsonb, $18::jsonb, 'accepted_candidate', 'product_runtime_phase2', now()
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
                _json([{"source": "product_runtime_phase2", "subject_key": profile["subject_key"]}]),
                _json({"phase": "product_runtime_phase2", "manual_reason": "product_runtime_delta_repair"}),
                _json(["product_runtime_phase2", "accepted_high_noise_repair"]),
                _json({"phase": "product_runtime_phase2", "requires_main_subject_anchor": True}),
            )
        return len(PROFILES)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert Product Runtime Phase 2 accepted theme_profile_v2 patches.")
    parser.add_argument("--db-name", default="stock_data_test")
    args = parser.parse_args()
    print(json.dumps({"db_name": args.db_name, "upserted": run_async(_upsert(args.db_name))}, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Rule-based stock fact extraction from lightspots (亮点句).
Uses regex patterns + keyword matching to extract facts without LLM API calls.

Design:
- Primary input: stock_lightspots table (51,686 rows / 4,288 stocks)
- Secondary input: stock detail JSON (for remark + detail text as supplement)
- Output: stock_facts compatible with existing schema

Strategy per fact_type:
- industry_role: High-recall regex patterns (龙头, 领军者, etc.)
- benefit_logic: Regex patterns (受益, 国产替代, 卡位, etc.)
- main_business: Keyword + pattern extraction from lightspots
- technology: Technology keyword matching
- product: Product keyword matching + lightspot parsing
- customer: Brand/company name extraction (hardest, lower recall)
"""

import os
import sys
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# Extraction patterns
# ==========================================

# --- industry_role patterns ---
INDUSTRY_ROLE_PATTERNS = [
    # "XX龙头" / "XX龙头标的" / "XX绝对龙头"
    (r'(?:全球|国内|国产|中国|行业|区域|细分|A股)?'
     r'(?:[\u4e00-\u9fff]{2,20}?'
     r'(?:龙头|领军者|领军企业|领先者|领先企业|标杆|翘楚|领跑者|排头兵|先锋|之王|巨头|佼佼者|引领者))',
     'industry_role'),

    # "龙头XX" (e.g., "龙头地位稳固")
    (r'龙头(?:地位|优势|标的|企业|公司|厂商|供应商|制造商)',
     'industry_role'),

    # "全球/国内最大的XX"
    (r'(?:全球|国内|国产|亚洲|中国)最大的[\u4e00-\u9fff]{2,25}',
     'industry_role'),

    # "全球/国内XX领先/一流"
    (r'(?:全球|国内|国产|行业)[\u4e00-\u9fff]{2,20}(?:领先|一流|知名|优秀|卓越|顶级)',
     'industry_role'),

    # "XX企业/制造商/供应商/服务商" at end of sentence
    (r'[\u4e00-\u9fff]{2,30}?(?:企业|制造商|供应商|服务商|方案提供商|平台|集团)(?:$|，|。)',
     'industry_role'),

    # "XX之王" "XX皇冠" 等比喻
    (r'[\u4e00-\u9fff]{2,15}之(?:王|皇冠|明珠|巅|最)',
     'industry_role'),

    # "被忽视的XX龙头" / "XX稀缺标的"
    (r'(?:被忽视的|稀缺的?|隐形)?[\u4e00-\u9fff]{2,20}(?:龙头|稀缺标的|冠军|第一股|第一品牌)',
     'industry_role'),
]

# --- benefit_logic patterns ---
BENEFIT_LOGIC_PATTERNS = [
    # "受益XX" / "受益于XX"
    (r'受益(?:于)?[\u4e00-\u9fff]{2,20}?(?:红利|趋势|进程|加速|发展|推进|释放|爆发)?',
     'benefit_logic'),

    # "XX国产化" / "XX国产替代"
    (r'[\u4e00-\u9fff]{2,20}?(?:国产化|国产替代|进口替代|自主可控|自主创新)',
     'benefit_logic'),

    # "卡位XX" / "布局XX赛道"
    (r'卡位[\u4e00-\u9fff]{2,20}?',
     'benefit_logic'),
    (r'布局[\u4e00-\u9fff]{2,15}?(?:赛道|领域|市场)',
     'benefit_logic'),

    # "享XX红利" / "享XX高景气"
    (r'享[\u4e00-\u9fff]{2,20}(?:红利|景气|成长)',
     'benefit_logic'),

    # "XX受益标的"
    (r'[\u4e00-\u9fff]{2,25}受益标的',
     'benefit_logic'),

    # "迎XX机遇/契机/拐点"
    (r'迎[\u4e00-\u9fff]{2,20}(?:机遇|契机|拐点|复苏|爆发)',
     'benefit_logic'),

    # 政策驱动 pattern
    (r'(?:政策|新基建|注册制|电改|军改|医改|国企改革|央企改革)[\u4e00-\u9fff]{0,15}(?:红利|受益|驱动|助力)',
     'benefit_logic'),

    # 景气周期
    (r'[\u4e00-\u9fff]{2,20}(?:高景气|景气上行|景气回升|景气周期|需求复苏|量价齐升)',
     'benefit_logic'),
]

# --- technology patterns ---
TECHNOLOGY_KEYWORDS = [
    # Specific technology terms
    r'(?:3D|5G|AI|IGBT|MEMS|LED|OLED|MiniLED|MicroLED|DRAM|NAND|SSD|HBM|RDMA|SR-IOV|SPDK|NVMe)',
    r'(?:云计算|大数据|人工智能|机器学习|深度学习|物联网|区块链|边缘计算|数字孪生)',
    r'[\u4e00-\u9fff]{2,10}(?:技术|工艺|平台|系统|方案|架构)',
    r'(?:封测|封装|测试|制造|量产|研发|设计|生产)(?:技术|工艺|能力|平台|服务|线)',
    r'(?:芯片|半导体|集成电路|晶圆|光刻|蚀刻|薄膜|沉积|外延|掺杂)',
    r'(?:纳米|微米|毫米波|太赫兹|光子|量子|激光|雷达|传感器|探测器)',
    r'(?:智能|自动|数字|信息|网络|软件|硬件)(?:化|技术|平台|系统|方案)',
    r'(?:高频|高速|高精度|高功率|高密度|低功耗|小型化|集成化)',
    r'\d+层(?:堆叠|封装|集成)',
    r'(?:柔性|刚性|挠性|刚挠结合|HDI|FPC|PCB|IC载板)',
    r'(?:锂电|钠电|固态电池|燃料电池|储能|光伏|风电|氢能)',
    r'(?:基因|细胞|生物|制药|制剂|药物|疫苗|抗体|蛋白|酶|核酸)',
    r'(?:配方|专利|独家|首创|首款|原创|自研|国产)',
    r'(?:工艺|制程|流程|方法|模型|算法)',
    r'(?:产线|产能|量产|中试|小试|放大)',
    r'(?:智能驾驶|自动驾驶|辅助驾驶|车联网|V2X)',
]

# --- product patterns ---
PRODUCT_PATTERNS = [
    # From lightspots: "XX产品/服务/业务"
    (r'[\u4e00-\u9fff\w]{2,25}(?:产品|服务|业务|平台|系统|设备|器件|材料|组件|模块|芯片|仪器|仪表|装备)',
     'product'),

    # Specific product indicators
    (r'(?:推出|发布|量产|交付|供货|销售|提供|打造|发力|加码|进军|布局|拓展|深耕)[\u4e00-\u9fff\w]{2,20}',
     'product'),

    # Brand/product names in quotes
    (r'[「""]([\u4e00-\u9fff\w]{2,20})[」""]',
     'product'),

    # "XX系列" products
    (r'[\u4e00-\u9fff\w]{2,20}系列',
     'product'),

    # Drug/chemical names
    (r'[\u4e00-\u9fff]{2,15}(?:注射液|片|胶囊|颗粒|口服液|滴丸|软膏|喷雾|贴剂)',
     'product'),

    # Specific product types
    (r'(?:手机|汽车|电池|电机|电控|减速器|机器人|无人机|服务器|交换机|路由器)',
     'product'),
]

# --- customer patterns ---
CUSTOMER_PATTERNS = [
    # "与XX合作" / "客户包括XX"
    (r'(?:与|和|同)([\u4e00-\u9fff\w]{2,15})(?:合作|签订|达成|建立)',
     'customer'),

    # Named companies as customers
    (r'(?:客户|供应|服务|配套|进入|导入)(?:包括|涵盖|覆盖|面向|主要为)?[\u4e00-\u9fff\w]{2,20}',
     'customer'),

    # Well-known brand names (can expand this list)
    (r'(?:苹果|华为|小米|OPPO|vivo|三星|比亚迪|特斯拉|蔚来|理想|小鹏|吉利|长城|长安|'
     r'大众|丰田|本田|宝马|奔驰|奥迪|谷歌|微软|亚马逊|Meta|英伟达|英特尔|AMD|'
     r'京东|阿里|腾讯|百度|字节|美团|拼多多|'
     r'中移动|中电信|中联通|国家电网|南方电网|中石油|中石化|中海油)',
     'customer'),
]

# --- main_business patterns ---
MAIN_BUSINESS_PATTERNS = [
    # "主营XX" / "主业XX"
    (r'(?:主营|主业|核心业务|主要业务)[\u4e00-\u9fff]{2,25}',
     'main_business'),

    # Common business domains (extracted from lightspot context)
    (r'(?:化工|医药|地产|金融|保险|证券|银行|钢铁|煤炭|有色|电力|'
     r'新能源|光伏|风电|储能|锂电|半导体|芯片|软件|互联网|电商|'
     r'汽车|机械|军工|航空|航天|船舶|轨交|基建|建材|水泥|'
     r'农业|食品|饮料|白酒|啤酒|乳业|调味品|养殖|种植|'
     r'服装|纺织|家电|家居|教育|医疗|养老|旅游|酒店|餐饮|'
     r'传媒|游戏|影视|出版|广告|物流|快递|环保|水务|燃气)',
     'main_business'),
]


def clean_lightspot(text: str) -> str:
    """Basic cleaning of a lightspot text."""
    text = text.strip()
    # Remove leading/trailing punctuation
    text = re.sub(r'^[,，。；;：:、\s]+', '', text)
    text = re.sub(r'[,，。；;：:、\s]+$', '', text)
    return text


def extract_industry_role(text: str) -> List[Dict]:
    """Extract industry_role facts from lightspot text."""
    facts = []
    for pattern, fact_type in INDUSTRY_ROLE_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(0).strip()
            # Clean up common suffixes
            value = re.sub(r'[，。；;：:、\s]+$', '', value)
            if len(value) >= 2 and len(value) <= 50:
                facts.append({
                    "fact_type": "industry_role",
                    "fact_value": value,
                    "evidence_span": text[:100],
                })
    return facts


def extract_benefit_logic(text: str) -> List[Dict]:
    """Extract benefit_logic facts from lightspot text."""
    facts = []
    for pattern, fact_type in BENEFIT_LOGIC_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(0).strip()
            value = re.sub(r'[，。；;：:、\s]+$', '', value)
            if len(value) >= 2 and len(value) <= 60:
                facts.append({
                    "fact_type": "benefit_logic",
                    "fact_value": value,
                    "evidence_span": text[:100],
                })
    return facts


def extract_technology(text: str) -> List[Dict]:
    """Extract technology facts from lightspot text."""
    facts = []
    for pattern in TECHNOLOGY_KEYWORDS:
        for match in re.finditer(pattern, text):
            value = match.group(0).strip()
            if len(value) >= 2 and len(value) <= 60:
                facts.append({
                    "fact_type": "technology",
                    "fact_value": value,
                    "evidence_span": text[:100],
                })
    return facts


def extract_product(text: str) -> List[Dict]:
    """Extract product facts from lightspot text."""
    facts = []
    for pattern, fact_type in PRODUCT_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(0).strip()
            if isinstance(value, tuple):
                value = match.group(1).strip() if match.lastindex else match.group(0).strip()
            value = re.sub(r'^[推出|发布|量产|交付|供货|销售|提供|打造|发力|加码|进军|布局|拓展|深耕]+', '', value)
            value = re.sub(r'[，。；;：:、\s]+$', '', value)
            if len(value) >= 2 and len(value) <= 60:
                facts.append({
                    "fact_type": "product",
                    "fact_value": value,
                    "evidence_span": text[:100],
                })
    return facts


def extract_customer(text: str) -> List[Dict]:
    """Extract customer facts from lightspot text."""
    facts = []
    for pattern, fact_type in CUSTOMER_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(0).strip()
            # For patterns with capture groups, use the captured group
            if match.lastindex and match.lastindex >= 1:
                value = match.group(1).strip()
            # Remove relationship words
            value = re.sub(r'^(?:与|和|同|客户|供应|服务|配套|进入|导入)', '', value)
            value = re.sub(r'(?:合作|签订|达成|建立|包括|涵盖|覆盖|面向|主要)$', '', value)
            value = re.sub(r'[，。；;：:、\s]+$', '', value)
            if len(value) >= 2 and len(value) <= 40:
                facts.append({
                    "fact_type": "customer",
                    "fact_value": value,
                    "evidence_span": text[:100],
                })
    return facts


def extract_main_business(text: str) -> List[Dict]:
    """Extract main_business facts from lightspot text."""
    facts = []
    for pattern, fact_type in MAIN_BUSINESS_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(0).strip()
            value = re.sub(r'[，。；;：:、\s]+$', '', value)
            if len(value) >= 2 and len(value) <= 40:
                facts.append({
                    "fact_type": "main_business",
                    "fact_value": value,
                    "evidence_span": text[:100],
                })
    return facts


def extract_facts_from_lightspots(lightspots: List[str]) -> List[Dict]:
    """Extract all facts from a list of lightspot texts."""
    all_facts = []
    for ls in lightspots:
        text = clean_lightspot(ls)
        if len(text) < 4:
            continue

        all_facts.extend(extract_industry_role(text))
        all_facts.extend(extract_benefit_logic(text))
        all_facts.extend(extract_technology(text))
        all_facts.extend(extract_product(text))
        all_facts.extend(extract_customer(text))
        all_facts.extend(extract_main_business(text))

    return all_facts


def normalize_facts(facts: List[Dict]) -> List[Dict]:
    """Deduplicate and normalize facts (mirrors normalize_llm_facts logic)."""
    VALID_TYPES = {
        "main_business", "industry_role", "product",
        "technology", "customer", "benefit_logic"
    }

    seen = set()
    normalized = []
    for f in facts:
        ft = f.get("fact_type", "")
        fv = f.get("fact_value", "").strip()
        es = f.get("evidence_span", "").strip()

        # Validate
        if ft not in VALID_TYPES:
            continue
        if not fv or len(fv) > 80:
            continue
        if not es:
            continue

        # Deduplicate
        key = (ft, fv)
        if key in seen:
            continue
        seen.add(key)

        normalized.append({
            "fact_type": ft,
            "fact_value": fv,
            "evidence_span": es[:200],
        })

    return normalized


def split_main_business_facts(facts: List[Dict]) -> List[Dict]:
    """Split main_business facts on Chinese/English separators (mirrors LLM script)."""
    result = []
    for f in facts:
        if f["fact_type"] == "main_business":
            parts = re.split(r'[、，,和及与/]+', f["fact_value"])
            for part in parts:
                part = part.strip()
                if part and len(part) <= 30:
                    result.append({
                        "fact_type": "main_business",
                        "fact_value": part,
                        "evidence_span": f["evidence_span"],
                    })
        else:
            result.append(f)
    return result


# ==========================================
# DB operations
# ==========================================

async def get_db_pool():
    import asyncpg
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRES_DATABASE", "stock_data_test")

    pool = await asyncpg.create_pool(
        user=user, password=password, host=host, port=port, database=database,
        min_size=1, max_size=4
    )
    return pool


async def get_stocks_without_facts(pool) -> List[Tuple[str, str]]:
    """Get stocks that have lightspots but no facts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT s.stock_id, s.name
            FROM stocks s
            INNER JOIN stock_lightspots sl ON s.stock_id = sl.stock_id
            LEFT JOIN stock_facts sf ON s.stock_id = sf.stock_id
            WHERE sf.stock_id IS NULL
            ORDER BY s.stock_id
        """)
        return [(r['stock_id'], r['name']) for r in rows]


async def get_stock_lightspots(pool, stock_id: str) -> List[str]:
    """Get all lightspots for a stock."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT content FROM stock_lightspots
            WHERE stock_id = $1
            ORDER BY lightspot_id
        """, stock_id)
        return [r['content'] for r in rows]


async def insert_stock_facts(pool, stock_id: str, facts: List[Dict]) -> int:
    """Insert facts into stock_facts table. Returns count inserted."""
    if not facts:
        return 0

    async with pool.acquire() as conn:
        inserted = 0
        for f in facts:
            try:
                await conn.execute("""
                    INSERT INTO stock_facts (stock_id, fact_type, fact_value, source, confidence, source_id, evidence_span, created_at)
                    VALUES ($1, $2, $3, 'jyhf_lightspot_rules', 0.85, $4, $5, NOW())
                    ON CONFLICT (stock_id, fact_type, fact_value) DO NOTHING
                """, stock_id, f['fact_type'], f['fact_value'],
                   f"{stock_id}_lightspot", f['evidence_span'])
                inserted += 1
            except Exception:
                pass
        return inserted


# ==========================================
# Evaluation (against existing DeepSeek facts)
# ==========================================

async def evaluate_against_deepseek(pool, sample_size: int = 100):
    """Compare rule extraction from lightspots against existing DeepSeek facts."""
    async with pool.acquire() as conn:
        # Get stocks that have BOTH lightspots and DeepSeek facts
        rows = await conn.fetch("""
            SELECT sf.stock_id
            FROM stock_facts sf
            INNER JOIN stock_lightspots sl ON sf.stock_id = sl.stock_id
            WHERE sf.source = 'jyhf_stock_detail'
            GROUP BY sf.stock_id
            ORDER BY RANDOM()
            LIMIT $1
        """, sample_size)

    total_deepseek = 0
    total_rule = 0
    total_overlap = 0
    type_stats = defaultdict(lambda: {"deepseek": 0, "rule": 0, "overlap": 0})

    for row in rows:
        stock_id = row['stock_id']

        # Get DeepSeek facts
        async with pool.acquire() as conn:
            ds_facts = await conn.fetch("""
                SELECT fact_type, fact_value FROM stock_facts
                WHERE stock_id = $1 AND source = 'jyhf_stock_detail'
            """, stock_id)
        ds_set = set((r['fact_type'], r['fact_value']) for r in ds_facts)

        # Get lightspots and extract rule-based facts
        lightspots = await get_stock_lightspots(pool, stock_id)
        raw_facts = extract_facts_from_lightspots(lightspots)
        rule_facts = normalize_facts(raw_facts)
        rule_facts = split_main_business_facts(rule_facts)
        rule_set = set((f['fact_type'], f['fact_value']) for f in rule_facts)

        total_deepseek += len(ds_set)
        total_rule += len(rule_set)
        total_overlap += len(ds_set & rule_set)

        for ft, fv in ds_set:
            type_stats[ft]["deepseek"] += 1
        for ft, fv in rule_set:
            type_stats[ft]["rule"] += 1
        for ft, fv in (ds_set & rule_set):
            type_stats[ft]["overlap"] += 1

    print("\n" + "=" * 70)
    print("Rule Extraction vs DeepSeek Evaluation (lightspots only)")
    print("=" * 70)
    print(f"Sample size: {len(rows)} stocks")
    print(f"DeepSeek facts: {total_deepseek}")
    print(f"Rule facts: {total_rule}")
    print(f"Overlap: {total_overlap}")
    print(f"Rule recall: {total_overlap/max(total_deepseek,1)*100:.1f}%")
    print(f"Rule precision (of what DeepSeek also found): {total_overlap/max(total_rule,1)*100:.1f}%")
    print()
    print("--- Per fact_type ---")
    for ft in ["main_business", "industry_role", "product", "technology", "customer", "benefit_logic"]:
        ds = type_stats[ft]["deepseek"]
        ru = type_stats[ft]["rule"]
        ov = type_stats[ft]["overlap"]
        rec = ov / max(ds, 1) * 100
        prec = ov / max(ru, 1) * 100
        print(f"  {ft:20s} | DeepSeek: {ds:5d} | Rule: {ru:5d} | Overlap: {ov:5d} | Recall: {rec:5.1f}% | Precision: {prec:5.1f}%")


# ==========================================
# Main
# ==========================================

if __name__ == "__main__":
    import asyncio

    mode = sys.argv[1] if len(sys.argv) > 1 else "eval"

    async def main():
        pool = await get_db_pool()
        try:
            if mode == "eval":
                # Evaluate against existing DeepSeek facts
                await evaluate_against_deepseek(pool, sample_size=200)

            elif mode == "extract":
                # Extract facts for stocks missing them
                stocks = await get_stocks_without_facts(pool)
                print(f"Found {len(stocks)} stocks with lightspots but no facts")

                total_inserted = 0
                for i, (stock_id, name) in enumerate(stocks):
                    if i % 100 == 0:
                        print(f"\rProcessing {i}/{len(stocks)}... ({total_inserted} facts inserted)", end="", flush=True)

                    lightspots = await get_stock_lightspots(pool, stock_id)
                    raw_facts = extract_facts_from_lightspots(lightspots)
                    facts = normalize_facts(raw_facts)
                    facts = split_main_business_facts(facts)
                    n = await insert_stock_facts(pool, stock_id, facts)
                    total_inserted += n

                print(f"\nDone! Inserted {total_inserted} facts for {len(stocks)} stocks")

            elif mode == "test":
                # Test on a single stock
                test_id = sys.argv[2] if len(sys.argv) > 2 else "000021"
                lightspots = await get_stock_lightspots(pool, test_id)
                print(f"Stock {test_id}: {len(lightspots)} lightspots")
                for ls in lightspots[:5]:
                    print(f"  - {ls}")
                raw = extract_facts_from_lightspots(lightspots)
                facts = normalize_facts(raw)
                facts = split_main_business_facts(facts)
                print(f"\nExtracted {len(facts)} facts:")
                for f in facts:
                    print(f"  [{f['fact_type']}] {f['fact_value']}")
                    print(f"    evidence: {f['evidence_span'][:80]}")
        finally:
            await pool.close()

    asyncio.run(main())

"""
validate_stock_recommend.py — 研选荐股 端到端验证

用法:
  python validate_stock_recommend.py                         # 默认研选范例
  python validate_stock_recommend.py "自定义研报文本"

全链路:
  研报文本 → 关键词提取 → 主题匹配(theme_gate_profile) → 股票查表(theme_stock_map) → 荐股输出
"""
import asyncio, asyncpg, os, re, sys, json
from collections import defaultdict, OrderedDict

DB_CONFIG = dict(
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
)

EXAMPLE_RESEARCH = (
    "【研选】公司多项AI算力光纤光缆产品取得突破性进展，"
    "并已完成800G高速光模块批量出货；"
    "光纤行业进入量价齐升的历史大周期，"
    "公司一季度实现业绩与盈利能力显著改善"
)

EXAMPLE_POINTS = [
    "公司多项AI算力光纤光缆产品取得突破性进展，并已完成800G高速光模块批量出货",
    "公司重磅新品4月全球上线，有望成为新一代头部二次元开放世界游戏",
    "光纤行业进入量价齐升的历史大周期，公司一季度实现业绩与盈利能力显著改善",
]


# ============================================================
# 关键词提取
# ============================================================

def extract_keywords(text: str) -> list:
    """从研报文本中提取关键主题词。"""
    kw = OrderedDict()  # keyword -> weight

    # 1. 特定模式匹配（产品/技术名）
    patterns = [
        (r'800G\s*(?:高速)?\s*光模块', 8),
        (r'(?:1\.6T|3\.2T|400G|200G|100G)\s*光模块', 8),
        (r'AI\s*(?:算力|服务器|芯片|模型|应用|平台)', 6),
        (r'(?:AI\s*)?(?:高速)?光(?:纤|缆|模块|器件|芯片|通信)', 7),
        (r'(?:共封装光学|CPO|LPO|硅光)', 8),
        (r'(?:二次元|动漫|游戏|电竞|元宇宙|VR|AR)', 5),
        (r'(?:光纤|光缆|光模块|光器件|光芯片)', 6),
        (r'(?:算力|数据中心|云计算|智算)', 5),
        (r'(?:新能源|光伏|锂电|储能|风电|氢能)', 5),
        (r'(?:半导体|芯片|集成电路|封测|晶圆)', 5),
        (r'(?:机器人|无人机|自动驾驶|智能驾驶|具身智能)', 5),
        (r'(?:创新药|生物制药|疫苗|医疗器械|CXO)', 5),
        (r'(?:白酒|食品|饮料|乳业|调味品)', 4),
        (r'(?:量价齐升|景气周期|需求复苏|供不应求)', 3),
    ]
    for pat, weight in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            kw[m.group(0).strip()] = max(kw.get(m.group(0).strip(), 0), weight)

    # 2. 中文分词（按标点切分，提取 2-6 字短语）
    segments = re.split(r'[，。,\.、；;：:\s（）()【】\[\]""\'\'！!\?？…—\-/]+', text)
    for seg in segments:
        seg = seg.strip()
        if 2 <= len(seg) <= 6:
            # 过滤掉纯数字/标点/英文单词
            if not re.match(r'^[\da-zA-Z]+$', seg):
                kw.setdefault(seg, 1)

    return list(kw.keys()), kw


# ============================================================
# 主题匹配
# ============================================================

async def match_themes(conn, text: str) -> list:
    """关键词匹配 theme_gate_profile，返回候选主题列表。"""
    keywords, weights = extract_keywords(text)
    if not keywords:
        return []

    # ILIKE 匹配：concept 精确命中权重高，search_text 命中权重低
    conditions = []
    params = []
    for kw in list(keywords)[:15]:
        conditions.append(f"concept ILIKE ${len(params)+1}")
        params.append(f"%{kw}%")
        conditions.append(f"search_text ILIKE ${len(params)+1}")
        params.append(f"%{kw}%")

    where = " OR ".join(conditions)
    rows = await conn.fetch(f"""
        SELECT subject_key, concept, search_text, semantic_type,
               must_terms, strong_terms, quality
        FROM theme_gate_profile
        WHERE {where}
        ORDER BY CASE quality WHEN 'strong' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END
        LIMIT 40
    """, *params)

    # 计算匹配得分：concept 命中权重高
    results = []
    for r in rows:
        concept = (r["concept"] or "")
        search_text = (r["search_text"] or "")

        score = 0
        matched = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in concept.lower():
                score += weights.get(kw, 2) * 3
                matched.append(kw)
            elif kw_lower in search_text.lower():
                score += weights.get(kw, 2) * 1
                matched.append(kw)

        # must_terms / strong_terms 命中加分
        for field in ["must_terms", "strong_terms"]:
            terms = r.get(field) or []
            if isinstance(terms, str):
                try: terms = json.loads(terms)
                except Exception: terms = []
            for term in (terms or []):
                if isinstance(term, str) and term.lower() in text.lower():
                    score += 5

        if score >= 2:  # 至少 2 分才保留
            results.append({
                "subject_key": r["subject_key"],
                "concept": concept,
                "quality": r.get("quality", "weak"),
                "semantic_type": r.get("semantic_type", ""),
                "match_score": score,
                "matched_keywords": list(set(matched)),
            })

    results.sort(key=lambda x: (x["match_score"]), reverse=True)
    return results[:8]


# ============================================================
# 股票查表
# ============================================================

async def lookup_stocks(conn, subject_keys: list) -> dict:
    """批量查 theme_stock_map，返回 {subject_key: {leader:[], core:[], member:[]}}"""
    result = {}
    for sk in subject_keys:
        rows = await conn.fetch("""
            SELECT stock_id, stock_name, relation_type, reason, confidence
            FROM theme_stock_map
            WHERE subject_key = $1
            ORDER BY CASE relation_type
                WHEN 'leader' THEN 1 WHEN 'core' THEN 2 ELSE 3 END
        """, sk)
        groups = {"leader": [], "core": [], "member": []}
        for r in rows:
            groups[r["relation_type"]].append(dict(r))
        result[sk] = groups
    return result


async def enrich_stocks(conn, stocks: list) -> dict:
    """批量补充 lightspots 和 remark。"""
    stock_ids = [s["stock_id"] for s in stocks]
    if not stock_ids:
        return {}, {}

    # lightspots map
    ls_map = defaultdict(list)
    ls_rows = await conn.fetch("""
        SELECT stock_id, content FROM stock_lightspots
        WHERE stock_id = ANY($1::varchar[])
        ORDER BY stock_id, lightspot_id
    """, stock_ids)
    for r in ls_rows:
        ls_map[r["stock_id"]].append(r["content"])

    # remarks map
    rm_map = {}
    try:
        rm_rows = await conn.fetch("""
            SELECT stock_id, remark FROM subject_stock_detail_staging
            WHERE stock_id = ANY($1::varchar[])
        """, stock_ids)
        rm_map = {r["stock_id"]: (r["remark"] or "") for r in rm_rows}
    except Exception:
        pass

    return ls_map, rm_map


# ============================================================
# 主流程
# ============================================================

async def main(text=None, points=None):
    text = text or EXAMPLE_RESEARCH
    points = points or EXAMPLE_POINTS

    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        print("=" * 80)
        print("📊  研选荐股 — 端到端验证")
        print("=" * 80)

        # ----- 输入 -----
        print(f"\n📰 输入文本:")
        print(f"   {text}")
        if points:
            print(f"\n   📋 {len(points)} 个要点:")
            for i, p in enumerate(points, 1):
                print(f"      {i}. {p[:120]}")

        # ----- Step 1: 关键词+主题匹配 -----
        print(f"\n{'─' * 60}")
        print("🔍 Step 1: 提取关键词 → 匹配主题 (theme_gate_profile)")
        print("─" * 60)

        keywords, weights = extract_keywords(text)
        high_kw = sorted(weights.items(), key=lambda x: -x[1])[:12]
        print(f"   关键词({len(keywords)}个): "
              f"{', '.join(f'{k}({w})' for k,w in high_kw)}")

        themes = await match_themes(conn, text)
        if not themes:
            print("\n   ❌ 未匹配到主题")
            return

        print(f"\n   匹配到 {len(themes)} 个候选主题:")
        for t in themes:
            flag = {"strong": "⭐", "moderate": "●", "weak": "○"}.get(t["quality"], " ")
            print(f"   {flag} [{t['subject_key']}] {t['concept']:20s} "
                  f"score={t['match_score']:<4d} "
                  f"— {', '.join(t['matched_keywords'][:4])}")

        # ----- Step 2: 查股票 -----
        print(f"\n{'─' * 60}")
        print("📈 Step 2: 查表 (theme_stock_map) → 荐股")
        print("─" * 60)

        subject_keys = [t["subject_key"] for t in themes]
        theme_stocks = await lookup_stocks(conn, subject_keys)

        # 汇总股票，去重（优先 leader > core > member）
        all_stocks = OrderedDict()  # stock_id -> stock info
        stock_theme_sources = defaultdict(list)

        for t in themes:
            sk = t["subject_key"]
            groups = theme_stocks.get(sk, {})
            for rel_type in ["leader", "core", "member"]:
                for s in groups.get(rel_type, []):
                    sid = s["stock_id"]
                    if sid not in all_stocks:
                        all_stocks[sid] = {
                            **s,
                            "best_relation": rel_type,
                            "theme_concept": t["concept"],
                        }
                    elif rel_type == "leader" and all_stocks[sid]["best_relation"] != "leader":
                        all_stocks[sid]["best_relation"] = "leader"
                    stock_theme_sources[sid].append(t["concept"])

        # 按 relation_type 分组
        leaders = [s for s in all_stocks.values() if s["best_relation"] == "leader"]
        cores = [s for s in all_stocks.values() if s["best_relation"] == "core"]
        members = [s for s in all_stocks.values() if s["best_relation"] == "member"]

        # 批量补充 lightspots + remark
        all_stock_list = list(all_stocks.values())
        ls_map, rm_map = await enrich_stocks(conn, all_stock_list)

        # ----- Step 3: 输出研选结果 -----
        print(f"\n{'─' * 60}")
        print("🎯 研选荐股结果")
        print("─" * 60)

        # 主题→股票汇总
        print(f"\n  📊 主题→股票总览:")
        for t in themes:
            sk = t["subject_key"]
            groups = theme_stocks.get(sk, {})
            total = sum(len(v) for v in groups.values())
            if total == 0:
                continue
            parts = []
            if groups["leader"]:
                parts.append(f"{len(groups['leader'])}龙头")
            if groups["core"]:
                parts.append(f"{len(groups['core'])}核心")
            if groups["member"]:
                parts.append(f"{len(groups['member'])}关联")
            stock_names = ", ".join(
                s["stock_name"] for s in (groups["leader"] + groups["core"])[:4]
            )
            print(f"  {t['concept']:20s} → {' + '.join(parts):20s} | {stock_names}")

        # 龙头股详情
        if leaders:
            print(f"\n  🥇 龙头股 ({len(leaders)}):")
            for s in leaders[:5]:
                themes_str = "、".join(stock_theme_sources.get(s["stock_id"], [])[:3])
                remark = rm_map.get(s["stock_id"], "")
                spots = ls_map.get(s["stock_id"], [])[:2]
                print(f"     {s['stock_id']} {s['stock_name']}")
                if remark:
                    print(f"         📍 {remark[:100]}")
                print(f"         🔗 关联主题: {themes_str}")
                for spot in spots:
                    print(f"         💡 {spot[:90]}")

        # 核心股
        if cores:
            print(f"\n  🥈 核心股 ({len(cores)}):")
            for s in cores[:5]:
                themes_str = "、".join(stock_theme_sources.get(s["stock_id"], [])[:2])
                remark = rm_map.get(s["stock_id"], "")
                print(f"     {s['stock_id']} {s['stock_name']:8s} — {themes_str}")
                if remark:
                    print(f"         📍 {remark[:100]}")

        # 关联股
        if members:
            print(f"\n  🥉 关联股 ({len(members)}):")
            for s in members[:10]:
                print(f"     {s['stock_id']} {s['stock_name']:8s} — "
                      f"{'、'.join(stock_theme_sources[s['stock_id']][:2])}")

        print(f"\n  ✅ 总计: {len(leaders)}龙头 + {len(cores)}核心 + {len(members)}关联 = {len(all_stocks)}只候选")
        print(f"  ✅ 覆盖主题: {len(themes)} 个 → {len(subject_keys)} 个 subject_key")

    finally:
        await conn.close()


if __name__ == "__main__":
    text_arg = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(text=text_arg))

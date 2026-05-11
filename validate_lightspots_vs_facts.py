"""
验证：同一只股票，stock_facts vs lightspots 生成的 profile_text 和 embedding 差异。
结论：如果两种 embedding 余弦相似度高，说明 lightspots 可以替代 stock_facts。
"""
import json, sys, os
import numpy as np
from text2vec import SentenceModel

# --- 1. 加载 text2vec 模型 ---
print("Loading text2vec model...")
model = SentenceModel()  # 默认用 shibing624/text2vec-base-chinese
print(f"Model loaded. Embedding dim: {model.get_sentence_embedding_dimension()}")

# --- 2. 从 DB 取同时有 facts 和 lightspots 的股票 ---
import psycopg2
import psycopg2.extras

conn = psycopg2.connect(
    host="localhost", port=5432, user="postgres", password="postgres",
    database="stock_data_test"
)

# 取 5 只有 facts 的股票，覆盖不同行业
stocks = ["000021", "002230", "600519", "002365", "601968", "603196"]
stock_names = {}

for sid in stocks:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT name FROM stocks WHERE stock_id = %s", (sid,))
        row = cur.fetchone()
        stock_names[sid] = row['name'] if row else sid

# --- 3. 按 stock_facts 方式生成 profile_text ---
def get_stock_facts(conn, stock_id):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT fact_type, fact_value, evidence_span
            FROM stock_facts WHERE stock_id = %s AND source = 'jyhf_stock_detail'
            ORDER BY id
        """, (stock_id,))
        return list(cur.fetchall())

def get_stock_lightspots(conn, stock_id):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT content FROM stock_lightspots
            WHERE stock_id = %s ORDER BY lightspot_id LIMIT 15
        """, (stock_id,))
        return [r[0] for r in cur.fetchall()]

def build_facts_profile(name, facts):
    """模拟 rebuild_stock_profile_ext 的 build_profile_text 逻辑"""
    from collections import defaultdict
    GROUP_MAP = {
        "main_business": "main_business",
        "product": "product", "technology": "product",
        "capacity": "product", "market_share": "product",
        "order_contract": "order", "investment": "order",
        "customer_supplier": "relation", "customer": "relation",
        "benefit_logic": "logic", "industry_role": "logic",
    }
    GROUPS = {
        "main_business": [], "product": [], "order": [], "relation": [], "logic": []
    }

    for f in facts:
        group = GROUP_MAP.get(f['fact_type'])
        if group and group in GROUPS:
            GROUPS[group].append(f['fact_value'])

    lines = [f"股票: {name}"]
    if GROUPS["main_business"]:
        lines.append(f"主营业务: {'; '.join(GROUPS['main_business'][:8])}")
    if GROUPS["product"]:
        lines.append(f"核心产品与技术: {'; '.join(GROUPS['product'][:10])}")
    if GROUPS["logic"]:
        lines.append(f"受益逻辑与行业角色: {'; '.join(GROUPS['logic'][:8])}")
    return "\n".join(lines)

def build_lightspots_profile(name, lightspots):
    """用 lightspots 直接拼接 profile_text"""
    lines = [f"股票: {name}"]
    lines.append("公司亮点:")
    for ls in lightspots[:15]:
        lines.append(f"- {ls}")
    return "\n".join(lines)

# --- 4. 对比 ---
print("\n" + "=" * 80)
print("Embedding 对比: stock_facts vs lightspots")
print("=" * 80)

for sid in stocks:
    name = stock_names[sid]
    facts = get_stock_facts(conn, sid)
    lightspots = get_stock_lightspots(conn, sid)

    if not facts:
        print(f"\n{sid} {name}: 无 stock_facts，跳过")
        continue

    facts_text = build_facts_profile(name, facts)
    ls_text = build_lightspots_profile(name, lightspots)

    # 生成 embedding
    facts_emb = model.encode(facts_text)
    ls_emb = model.encode(ls_text)

    # 余弦相似度
    sim = np.dot(facts_emb, ls_emb) / (np.linalg.norm(facts_emb) * np.linalg.norm(ls_emb))

    print(f"\n--- {sid} {name} ---")
    print(f"  Facts: {len(facts)} 条, Lightspots: {len(lightspots)} 条")
    print(f"  Facts profile 长度: {len(facts_text)} chars")
    print(f"  Lightspots profile 长度: {len(ls_text)} chars")
    print(f"  Embedding 余弦相似度: {sim:.4f}")

    # 显示部分文本
    print(f"  [Facts text 前200字]: {facts_text[:200].replace(chr(10), ' ')}")
    print(f"  [Lightspots text 前200字]: {ls_text[:200].replace(chr(10), ' ')}")

# --- 5. 主题匹配对比 ---
print("\n" + "=" * 80)
print("主题匹配对比: 看两个 embedding 找出的最近邻股票是否一致")
print("=" * 80)

# 随机选 50 只有 facts 的股票，计算 embedding，然后检查 nearest neighbors
import random
with conn.cursor() as cur:
    cur.execute("""
        SELECT DISTINCT sf.stock_id, s.name
        FROM stock_facts sf JOIN stocks s ON sf.stock_id = s.stock_id
        WHERE sf.source = 'jyhf_stock_detail'
        LIMIT 100
    """)
    candidates = list(cur.fetchall())

sample = random.sample(candidates, min(30, len(candidates)))

results = []
for sid, name in sample:
    facts = get_stock_facts(conn, sid)
    lightspots = get_stock_lightspots(conn, sid)
    if not facts or not lightspots:
        continue

    f_text = build_facts_profile(name, facts)
    l_text = build_lightspots_profile(name, lightspots)
    f_emb = model.encode(f_text)
    l_emb = model.encode(l_text)
    results.append((sid, name, f_emb, l_emb, f_text, l_text))

# 计算事实方案中每只股票的 top-5 最近邻，再看 lightspots 方案的排名
print(f"\n基于 {len(results)} 只股票的交叉验证:")
print()

agreements_top1 = 0
agreements_top3 = 0
agreements_top5 = 0
total = 0

# 预计算所有 embedding
f_embs = np.array([r[2] for r in results])
l_embs = np.array([r[3] for r in results])

for i, (sid, name, f_emb, l_emb, f_text, l_text) in enumerate(results):
    # facts 空间的最近邻（排除自己）
    f_sims = np.dot(f_embs, f_emb) / (np.linalg.norm(f_embs, axis=1) * np.linalg.norm(f_emb))
    f_sims[i] = -1  # 排除自己
    facts_top5 = set(np.argsort(f_sims)[-5:])

    # lightspots embedding 在 facts 空间中的最近邻
    l_sims = np.dot(f_embs, l_emb) / (np.linalg.norm(f_embs, axis=1) * np.linalg.norm(l_emb))
    l_sims[i] = -1
    ls_top5 = set(np.argsort(l_sims)[-5:])

    overlap = len(facts_top5 & ls_top5)
    if overlap >= 1:
        agreements_top1 += 1
    if overlap >= 3:
        agreements_top3 += 1
    if overlap >= 5:
        agreements_top5 += 1
    total += 1

print(f"  Top-5 完全一致: {agreements_top5}/{total} ({agreements_top5/total*100:.0f}%)")
print(f"  Top-5 至少 3 个重合: {agreements_top3}/{total} ({agreements_top3/total*100:.0f}%)")
print(f"  Top-5 至少 1 个重合: {agreements_top1}/{total} ({agreements_top1/total*100:.0f}%)")

# --- 6. 展示一个具体例子 ---
print("\n" + "=" * 80)
print("具体例子：以 000021 深科技 为中心，看两种方案的 Top-5 最近邻")
print("=" * 80)

# 找到深科技在 results 中的索引
for i, (sid, name, f_emb, l_emb, f_text, l_text) in enumerate(results):
    if sid == "000021":
        f_sims = np.dot(f_embs, f_emb) / (np.linalg.norm(f_embs, axis=1) * np.linalg.norm(f_emb))
        f_sims[i] = -1
        l_sims = np.dot(f_embs, l_emb) / (np.linalg.norm(f_embs, axis=1) * np.linalg.norm(l_emb))
        l_sims[i] = -1

        f_top5 = np.argsort(f_sims)[-5:]
        l_top5 = np.argsort(l_sims)[-5:]

        print("\nFacts 方案的 Top-5 最近邻:")
        for j in reversed(f_top5):
            print(f"  {results[j][0]} {results[j][1]} (sim={f_sims[j]:.4f})")

        print("\nLightspots 方案的 Top-5 最近邻:")
        for j in reversed(l_top5):
            print(f"  {results[j][0]} {results[j][1]} (sim={l_sims[j]:.4f})")
        break

conn.close()
print("\nDone.")

"""
extract_stock_gate.py — 单只股票 Gate 提炼（简化版，复刻题材 gate 提炼思路）

流水线：
  1. detail_html → 纯文本 → 分段为知识块
  2. lightspots → 事件证据
  3. LLM 生成本体 (concept/strategy_type/dimensions)
  4. LLM 术语角色判定 (anchor/descriptive/event/drop)
  5. LLM 核心锚点判定 (primary/secondary anchor)
  6. LLM 生成 gate (must/should/not)
  7. 后处理 + 校验

用法: python extract_stock_gate.py --stock 301308
"""
import argparse, asyncio, asyncpg, json, os, re, sys, time, hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

DB = dict(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

OUT_DIR = Path("stock_gates")
CACHE_DIR = Path("stock_gate_cache")

# ==================== HTML → 文本 ====================
def strip_html(html: str) -> str:
    if not html: return ""
    t = re.sub(r'</p>|<br\s*/?>|</li>', '\n', html, flags=re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{2,}', '\n\n', t).strip()
    return t

# ==================== DeepSeek Client ====================
class DS:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base = DEEPSEEK_BASE

    async def call(self, system: str, prompt: str, max_tokens=2000, temp=0.1) -> dict:
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temp, "max_tokens": max_tokens, "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{self.base}/v1/chat/completions", headers=headers, json=payload,
                              timeout=aiohttp.ClientTimeout(total=120)) as r:
                data = await r.json()
                content = data["choices"][0]["message"]["content"]
                # Extract JSON
                m = re.search(r'\{[\s\S]*\}', content)
                if m: return json.loads(m.group())
                raise RuntimeError(f"No JSON: {content[:200]}")

# ==================== Prompt Templates ====================
ONTOLOGY_SYSTEM = """你是股票业务本体生成器。根据个股详情和亮点信息，输出合法JSON。

任务：
1. concept: 用2-6字概括公司核心业务定位
2. strategy_type: "industry_chain"（产业/供应链类）
3. dimensions: 从详情中提取维度化术语，维度名自定。例如：
   - "核心产品": ["嵌入式存储","固态硬盘SSD","移动存储","内存条"]
   - "核心技术": ["主控芯片设计","固件开发","NAND颗粒分析","封装测试"]
   - "下游应用": ["智能手机","计算机","汽车电子","物联网"]
   所有术语必须来自原文，不要编造。

{
  "concept": "半导体存储",
  "strategy_type": "industry_chain",
  "dimensions": {"核心产品":[...], "核心技术":[...], "下游应用":[...]}
}
"""

TERM_ROLE_SYSTEM = """你是术语角色判定器。对候选术语判定：anchor_term/descriptive_term/event_term/meta_label/drop。

- anchor_term: 能脱离上下文仍稳定指向公司核心业务对象的术语→可进must
- descriptive_term: 描述性质、作用、特点的术语→只能进should
- event_term: 来自事件或短期变化的术语→只能进should/not
- meta_label: 维度名、分类标签→禁止进gate
- drop: 噪音、不稳定

输出: {"items":[{"term":"术语","role":"anchor_term","confidence":0.8,"reason":"..."}]}
"""

ANCHOR_SYSTEM = """你是核心锚点判定器。对anchor_term判断primary_anchor还是secondary_anchor。

- primary_anchor: 最符合公司核心业务定义，最适合做最终gate的must → 2-6条
- secondary_anchor: 相关但与核心业务不够直接 → 进should

输出: {"items":[{"term":"术语","anchor_level":"primary_anchor","confidence":0.8,"reason":"..."}]}
"""

GATE_SYSTEM = """你是gate规则生成器。从已分类术语生成must/should/not。

规则：
1. must只能从primary_anchor逐字拷贝（2-6条）
2. should从secondary_anchor+descriptive_term+event_term选择（≤12条）
3. not从event_term中选择容易误判但不属于公司主线的词（≤6条，可为空）
4. 不要放维度名、概念标签

输出: {"must":["..."],"should":["..."],"not":["..."]}
"""

# ==================== 主流程 ====================
async def extract_stock_gate(stock_id: str):
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key: raise RuntimeError("DEEPSEEK_API_KEY not set")
    ds = DS(api_key)

    # 1. 加载数据
    conn = await asyncpg.connect(**DB)
    row = await conn.fetchrow(
        "SELECT stock_id, stock_name, detail_html, remark FROM subject_stock_detail_staging WHERE stock_id = $1", stock_id)
    spots = await conn.fetch("SELECT content FROM stock_lightspots WHERE stock_id = $1 ORDER BY lightspot_id", stock_id)
    await conn.close()

    if not row: raise RuntimeError(f"Stock {stock_id} not found")
    name = row['stock_name']
    remark = row['remark'] or ""
    detail_text = strip_html(row['detail_html'] or "")

    lightspots = [r['content'] for r in spots]
    print(f"=== {stock_id} {name} ===")
    print(f"  detail: {len(detail_text)} chars, lightspots: {len(lightspots)}, remark: {remark[:80]}")

    # 2. 构建知识文本
    knowledge_texts = [detail_text[:3000]]
    if remark: knowledge_texts.insert(0, remark)

    # 3. LLM 生成本体
    print("\n[Step 1] 生成本体...")
    prompt = f"公司名称：{name}\n定位：{remark}\n\n详情：\n{detail_text[:2500]}"
    ontology = await ds.call(ONTOLOGY_SYSTEM, prompt, max_tokens=2000)
    print(f"  concept={ontology.get('concept','?')} strategy={ontology.get('strategy_type','?')}")
    dims = ontology.get('dimensions', {})
    for k, v in dims.items():
        print(f"  {k}: {v[:5]}...")

    # 4. 展开候选术语
    candidates = []
    concept = ontology.get('concept', '')
    if concept: candidates.append({'term': concept, 'source': 'concept'})
    for dim_name, terms in dims.items():
        if isinstance(terms, list):
            for t in terms:
                candidates.append({'term': str(t).strip(), 'source': f'dim:{dim_name}'})
    # 去重
    seen = set(); unique = []
    for c in candidates:
        if c['term'] and c['term'] not in seen:
            seen.add(c['term']); unique.append(c)

    print(f"\n[Step 2] 术语角色判定 ({len(unique)}个候选)...")
    judged = {'anchor_term': [], 'descriptive_term': [], 'event_term': [], 'meta_label': [], 'drop': []}
    batch_size = 20
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i+batch_size]
        role_prompt = f"公司定位：{remark}\n知识文本摘要：{detail_text[:800]}\n候选术语：{json.dumps(batch, ensure_ascii=False)}\n请判定每个术语的角色。"
        resp = await ds.call(TERM_ROLE_SYSTEM, role_prompt, max_tokens=2000)
        for item in resp.get('items', []):
            role = item.get('role', 'drop')
            if role in judged:
                judged[role].append({'term': item['term'], 'confidence': item.get('confidence', 0.5), 'reason': item.get('reason', '')})
    print(f"  anchor={len(judged['anchor_term'])} desc={len(judged['descriptive_term'])} event={len(judged['event_term'])} meta={len(judged['meta_label'])} drop={len(judged['drop'])}")

    # 5. 核心锚点判定
    print(f"\n[Step 3] 核心锚点判定...")
    anchors = [x['term'] for x in judged['anchor_term']]
    anchor_resp = await ds.call(ANCHOR_SYSTEM,
        f"公司名称：{name}\n定位：{remark}\n知识文本：{detail_text[:1000]}\n候选anchor_term：{json.dumps(anchors, ensure_ascii=False)}\n请判定primary/secondary。",
        max_tokens=2000)
    primary = [x['term'] for x in anchor_resp.get('items', []) if x.get('anchor_level') == 'primary_anchor']
    secondary = [x['term'] for x in anchor_resp.get('items', []) if x.get('anchor_level') == 'secondary_anchor']
    print(f"  primary={len(primary)}: {primary}")
    print(f"  secondary={len(secondary)}: {secondary[:5]}...")

    # 6. 生成 gate
    print(f"\n[Step 4] 生成gate...")
    desc_terms = [x['term'] for x in judged['descriptive_term']]
    event_terms = [x['term'] for x in judged['event_term']]
    gate_prompt = f"""公司：{name}
定位：{remark}
primary_anchor（只能从这里面选must）：{json.dumps(primary, ensure_ascii=False)}
secondary_anchor（只能进should）：{json.dumps(secondary, ensure_ascii=False)}
descriptive_term（只能进should）：{json.dumps(desc_terms[:20], ensure_ascii=False)}
event_term（只能进should/not）：{json.dumps(event_terms[:20], ensure_ascii=False)}
请生成must/should/not。"""
    gate = await ds.call(GATE_SYSTEM, gate_prompt, max_tokens=1500)

    # 7. 后处理
    must = gate.get('must', [])[:6]
    should = gate.get('should', [])[:12]
    not_terms = gate.get('not', [])[:6]

    gate_out = {
        "stock_id": stock_id,
        "stock_name": name,
        "concept": concept,
        "strategy_type": ontology.get('strategy_type', 'industry_chain'),
        "must": must,
        "should": should,
        "not": not_terms,
        "evidence_refs": [{"term": t, "source": "primary_anchor"} for t in must],
        "quality": "medium" if len(must) >= 3 else "weak",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{stock_id}_gate.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(gate_out, f, ensure_ascii=False, indent=2)

    print(f"\n=== 结果 ===")
    print(f"  must({len(must)}): {must}")
    print(f"  should({len(should)}): {should[:8]}...")
    print(f"  not({len(not_terms)}): {not_terms}")
    print(f"  已保存: {out_path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", default="301308")
    args = ap.parse_args()
    asyncio.run(extract_stock_gate(args.stock))

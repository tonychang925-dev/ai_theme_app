"""
extract_stock_gates_batch.py — 批量个股 Gate 提炼

流水线（每只股票4次LLM调用）:
  1. detail_html → 纯文本
  2. LLM本体生成 (concept/strategy_type/dimensions)
  3. LLM术语角色判定 (anchor/descriptive/event/meta/drop)
  4. LLM核心锚点判定 (primary/secondary)
  5. LLM gate生成 (must/should/not)
  6. 质量控制 + 入库

用法:
  python extract_stock_gates_batch.py --limit 10          # 先跑10只验证
  python extract_stock_gates_batch.py --limit 0 --batch   # 全量
"""
import argparse, asyncio, asyncpg, json, os, re, sys, time, hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from tqdm import tqdm

DB = dict(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

OUT_DIR = Path("stock_gates")
CACHE_DIR = Path("stock_gate_cache")

# ==================== Utils ====================
def strip_html(html: str) -> str:
    if not html: return ""
    t = re.sub(r'</p>|<br\s*/?>|</li>', '\n', html, flags=re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{2,}', '\n\n', t).strip()
    return t

def compute_hash(*args) -> str:
    h = hashlib.md5()
    for a in args:
        h.update(str(a).encode("utf-8"))
    return h.hexdigest()[:16]

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
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(f"{self.base}/v1/chat/completions", headers=headers, json=payload,
                                      timeout=aiohttp.ClientTimeout(total=90)) as r:
                        data = await r.json()
                        content = data["choices"][0]["message"]["content"]
                        m = re.search(r'\{[\s\S]*\}', content)
                        if m: return json.loads(m.group())
                        if attempt < 2: await asyncio.sleep(1.5); continue
            except Exception as e:
                if attempt < 2: await asyncio.sleep(2); continue
                raise
        raise RuntimeError(f"No JSON after retries: {content[:200]}")

# ==================== Prompts ====================
ONTOLOGY_SYSTEM = """你是股票业务本体生成器。根据个股详情，输出合法JSON。

1. concept: 2-6字概括公司核心业务定位
2. strategy_type: 固定 "industry_chain"
3. dimensions: 从详情提取维度化术语（来源原文）。例如：
   - "核心产品":[...], "核心技术":[...], "下游应用":[...], "供应链地位":[...]
   维度名自定，术语必须来自原文，不编造。

{"concept":"半导体存储","strategy_type":"industry_chain","dimensions":{"核心产品":["嵌入式存储","SSD"],"核心技术":["主控芯片","固件开发"]}}
"""

TERM_ROLE_SYSTEM = """术语角色判定器。对候选术语判定：anchor_term/descriptive_term/event_term/meta_label/drop。

- anchor_term: 稳定指向公司核心业务对象（产品、技术、服务名）→可进must
- descriptive_term: 描述性质、作用、特点 →只能进should
- meta_label: 维度名、分类标签 →禁止进gate
- drop: 噪音、过泛

输出: {"items":[{"term":"...","role":"anchor_term","confidence":0.8}]}
"""

ANCHOR_SYSTEM = """核心锚点判定器。对anchor_term判断primary_anchor还是secondary_anchor。

- primary_anchor: 最体现公司核心业务定义，最适合做gate must → 2-5条
- secondary_anchor: 相关但非核心 → 进should

输出: {"items":[{"term":"...","anchor_level":"primary_anchor","confidence":0.8}]}
"""

GATE_SYSTEM = """gate规则生成器。从已分类术语生成must/should/not。

规则：
1. must只从primary_anchor逐字拷贝（2-5条）
2. should从secondary_anchor+descriptive_term选择（≤10条）
3. not从event_term或易误判词选择（≤5条，可空）
4. 不放维度名、概念标签

输出: {"must":["..."],"should":["..."],"not":["..."]}
"""

# ==================== Main ====================
async def extract_one(ds: DS, stock_id: str, name: str, remark: str, detail_text: str) -> dict:
    # 1. Ontology
    prompt = f"公司名称：{name}\n定位：{remark}\n\n详情：\n{detail_text[:2500]}"
    ontology = await ds.call(ONTOLOGY_SYSTEM, prompt, max_tokens=2000)
    concept = ontology.get('concept', '')
    dims = ontology.get('dimensions', {})

    # 2. Collect candidates
    candidates = []
    if concept: candidates.append({'term': concept, 'source': 'concept'})
    for dim_name, terms in dims.items():
        if isinstance(terms, list):
            for t in terms:
                t = str(t).strip()
                if t: candidates.append({'term': t, 'source': f'dim:{dim_name}'})
    seen = set(); unique = []
    for c in candidates:
        if c['term'] not in seen: seen.add(c['term']); unique.append(c)

    # 3. Term Role
    judged = {'anchor_term': [], 'descriptive_term': [], 'event_term': [], 'meta_label': [], 'drop': []}
    for i in range(0, len(unique), 15):
        batch = unique[i:i+15]
        rp = f"公司定位：{remark}\n知识文本：{detail_text[:800]}\n候选术语：{json.dumps(batch, ensure_ascii=False)}"
        resp = await ds.call(TERM_ROLE_SYSTEM, rp, max_tokens=2000)
        for item in resp.get('items', []):
            role = item.get('role', 'drop')
            if role in judged:
                judged[role].append({'term': item['term'], 'confidence': item.get('confidence', 0.5)})

    # 4. Core Anchor
    anchors = [x['term'] for x in judged['anchor_term']]
    if not anchors:
        primary, secondary = [], []
    else:
        ap = f"公司名称：{name}\n定位：{remark}\n知识文本：{detail_text[:1000]}\n候选anchor_term：{json.dumps(anchors, ensure_ascii=False)}"
        anchor_resp = await ds.call(ANCHOR_SYSTEM, ap, max_tokens=2000)
        primary = [x['term'] for x in anchor_resp.get('items', []) if x.get('anchor_level') == 'primary_anchor']
        secondary = [x['term'] for x in anchor_resp.get('items', []) if x.get('anchor_level') == 'secondary_anchor']

    # 5. Gate
    desc_terms = [x['term'] for x in judged['descriptive_term']]
    event_terms = [x['term'] for x in judged['event_term']]
    gp = f"""公司：{name}\n定位：{remark}
primary_anchor（只从这选must）：{json.dumps(primary, ensure_ascii=False)}
secondary_anchor（进should）：{json.dumps(secondary, ensure_ascii=False)}
descriptive_term（进should）：{json.dumps(desc_terms[:15], ensure_ascii=False)}
event_term（进should/not）：{json.dumps(event_terms[:15], ensure_ascii=False)}"""
    gate = await ds.call(GATE_SYSTEM, gp, max_tokens=1500)

    # 6. Post-process & QC
    MAX_MUST_LEN = 12
    must = [t for t in gate.get('must', []) if t in set(primary) and len(t) <= MAX_MUST_LEN][:5]
    should = [t for t in gate.get('should', []) if len(t) <= 16][:10]
    not_terms = [t for t in gate.get('not', []) if len(t) <= 16][:5]

    quality = "strong" if len(must) >= 3 else ("medium" if len(must) >= 2 else "weak")

    return {
        "stock_id": stock_id, "stock_name": name, "concept": concept,
        "strategy_type": ontology.get('strategy_type', 'industry_chain'),
        "must": must, "should": should, "not": not_terms,
        "evidence_refs": [{"term": t, "source": "primary_anchor"} for t in must],
        "quality": quality,
        "must_count": len(must),
    }

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="0=all")
    ap.add_argument("--start", type=int, default=0, help="Offset")
    ap.add_argument("--min-detail", type=int, default=500, help="Min detail_html chars")
    ap.add_argument("--concurrency", type=int, default=5, help="Concurrent LLM calls")
    args = ap.parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key: raise RuntimeError("DEEPSEEK_API_KEY not set")
    ds = DS(api_key)

    conn = await asyncpg.connect(**DB)
    rows = await conn.fetch("""
        SELECT ssds.stock_id, ssds.stock_name, ssds.remark,
               ssds.detail_html, array_agg(sl.content ORDER BY sl.lightspot_id) as spots
        FROM subject_stock_detail_staging ssds
        LEFT JOIN stock_lightspots sl ON ssds.stock_id = sl.stock_id
        WHERE char_length(ssds.detail_html) >= $1
          AND ssds.stock_name NOT LIKE '%*ST%'
          AND ssds.stock_name NOT LIKE '%ST%'
        GROUP BY ssds.stock_id, ssds.stock_name, ssds.remark, ssds.detail_html
        ORDER BY ssds.stock_id
    """, args.min_detail)
    await conn.close()

    if args.limit > 0:
        rows = rows[args.start:args.start + args.limit]

    OUT_DIR.mkdir(exist_ok=True)

    sem = asyncio.Semaphore(args.concurrency)
    stats = {"total": len(rows), "ok": 0, "fail": 0, "by_quality": defaultdict(int)}
    t0 = time.time()
    lock = asyncio.Lock()
    pbar = tqdm(total=len(rows))

    async def process_one(r):
        sid, name, remark = r['stock_id'], r['stock_name'], (r['remark'] or '')
        out_path = OUT_DIR / f"{sid}_gate.json"

        # 断点续跑：已存在且有效的跳过
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text())
                if existing.get("must_count", 0) >= 2:
                    async with lock:
                        stats["ok"] += 1; stats["by_quality"][existing.get("quality","unknown")] += 1
                        pbar.update(1)
                    return existing
            except Exception: pass

        detail_text = strip_html(r['detail_html'] or '')
        async with sem:
            gate = await extract_one(ds, sid, name, remark, detail_text)
            gate['generated_at'] = time.strftime("%Y-%m-%dT%H:%M:%S")

            with out_path.open("w", encoding="utf-8") as f:
                json.dump(gate, f, ensure_ascii=False, indent=2)

            async with lock:
                stats["ok"] += 1
                stats["by_quality"][gate["quality"]] += 1
                pbar.update(1)
            return gate

    tasks = [asyncio.create_task(process_one(r)) for r in rows]
    for task in asyncio.as_completed(tasks):
        try:
            await task
        except Exception as e:
            async with lock:
                stats["fail"] += 1
                pbar.update(1)

    pbar.close()

    print(f"\n=== DONE ===")
    print(json.dumps(dict(stats), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

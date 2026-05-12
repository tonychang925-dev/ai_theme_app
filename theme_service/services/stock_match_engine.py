"""
stock_match_engine.py — 个股匹配引擎（复刻 final_theme_matcher 架构）

流水线:
  研报原文 → Dense Recall → Gate Evidence → Rerank → Dynamic TopK → LLM Judge

不修改已有组件。
"""
from __future__ import annotations

import asyncio, json, logging, math, os, re, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import asyncpg
from text2vec import SentenceModel

logger = logging.getLogger(__name__)

# ==================== Data ====================
@dataclass
class StockGate:
    stock_id: str
    stock_name: str
    concept: str
    must_terms: List[str]
    should_terms: List[str]
    not_terms: List[str]
    quality: str

@dataclass
class StockCandidate:
    stock_id: str
    stock_name: str
    dense_score: float
    rerank_score: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MatchResult:
    event_id: int
    matched: bool
    verdict: str
    candidates: List[Dict] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)

# ==================== DB ====================
async def load_gates() -> Dict[str, StockGate]:
    conn = await asyncpg.connect(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
    try:
        rows = await conn.fetch("""
            SELECT stock_id, stock_name, concept, must_terms, should_terms, not_terms, quality
            FROM stock_gate_profile WHERE must_count >= 1
        """)
        gates = {}
        for r in rows:
            gates[r['stock_id']] = StockGate(
                stock_id=r['stock_id'], stock_name=r['stock_name'],
                concept=r['concept'] or '',
                must_terms=_ensure_list(r['must_terms']),
                should_terms=_ensure_list(r['should_terms']),
                not_terms=_ensure_list(r['not_terms']),
                quality=r['quality'] or 'weak',
            )
        return gates
    finally:
        await conn.close()

def _ensure_list(v: Any) -> List[str]:
    if isinstance(v, list): return [str(x) for x in v if x]
    if isinstance(v, str):
        try: return [str(x) for x in json.loads(v) if x]
        except: return [v] if v else []
    return []

# ==================== Dense Recall ====================
class DenseRecall:
    def __init__(self, model: SentenceModel):
        self.model = model

    async def recall(self, query_text: str, top_k: int = 30) -> List[Dict]:
        vec = self.model.encode(query_text)
        vec_str = f"[{','.join(f'{v:.6f}' for v in vec)}]"
        conn = await asyncpg.connect(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
        try:
            rows = await conn.fetch("""
                SELECT stock_id, stock_name, profile_text,
                       1 - (embedding <=> $1::vector) as dense_score
                FROM stock_profile_ext
                WHERE embedding IS NOT NULL AND stock_name NOT LIKE '%ST%'
                ORDER BY embedding <=> $1::vector LIMIT $2
            """, vec_str, top_k)
            return [dict(r) for r in rows]
        finally:
            await conn.close()

# ==================== Gate Evidence ====================
def build_gate_evidence(event_text: str, gate: StockGate, profile_text: str = "") -> Dict:
    """匹配事件原文与个股 gate 术语。只对事件原文做匹配。"""
    must_hits = [t for t in gate.must_terms if t and t in event_text]
    should_hits = [t for t in gate.should_terms if t and t in event_text]
    not_hits = [t for t in gate.not_terms if t and t in event_text]

    concept_hit = gate.concept and len(gate.concept) >= 2 and gate.concept in event_text

    positive = len(must_hits) * 5 + len(should_hits) * 2 + (10 if concept_hit else 0)
    conflict = len(not_hits) * 3

    return {
        "concept_hit": concept_hit,
        "must_hits": must_hits,
        "should_hits": should_hits,
        "not_hits": not_hits,
        "positive_score": positive,
        "conflict_score": conflict,
    }

# ==================== Rerank ====================
def rerank(candidates: List[Dict], gates: Dict[str, StockGate], event_text: str) -> List[StockCandidate]:
    """融合式 rerank：semantic + gate evidence。复刻 Fused Rerank。"""
    out = []
    for c in candidates:
        sid = c['stock_id']
        profile_text = c.get('profile_text', '') or ''
        gate = gates.get(sid)
        evidence = build_gate_evidence(event_text, gate, profile_text) if gate else {}
        rerank_score = c.get('dense_score', 0) + evidence.get('positive_score', 0) * 0.01
        out.append(StockCandidate(
            stock_id=sid, stock_name=c.get('stock_name', ''),
            dense_score=c.get('dense_score', 0), rerank_score=rerank_score,
            evidence=evidence,
        ))
    out.sort(key=lambda x: (-x.rerank_score, -x.dense_score))
    return out

# ==================== Dynamic TopK ====================
def compute_dynamic_topk(candidates: List[StockCandidate], min_k=8, max_k=15) -> int:
    """根据 rerank_score 分布决定 LLM 候选数。复刻 compute_dynamic_topk。"""
    if not candidates: return min_k
    best = candidates[0].rerank_score
    keep = sum(1 for c in candidates[:max_k] if c.rerank_score >= best * 0.88)
    return max(min_k, min(keep, max_k))

# ==================== LLM Judge ====================
LLM_SYSTEM = """你是A股研选荐股最终裁决器。在候选股票中做排他式比较，选出最匹配研报的股票。

判定规则（按优先级）：
1. 研报说"公司加码/布局/深耕XX" → 找核心业务是XX的股票。这是最强信号
2. must命中 = 强证据。must命中越多越优先。must命中+概念命中=几乎确定
3. 如果候选定位/亮点明确描述了研报提到的业务，即使没有must命中也可判MATCH
4. 仅"行业沾边"或"同属大类" → PARTIAL
5. 明显不相关 → MISMATCH
6. Gate证据是辅助参考，不是决定性因素
7. 每只股票必须给出判定，只输出JSON

输出JSON数组：
[{"stock_id":"000001","verdict":"MATCH|PARTIAL|MISMATCH","confidence":0.85,"reason":"15字内"}]"""

async def llm_judge(llm_client, event_text: str, candidates: List[StockCandidate],
                     gates: Dict[str, StockGate]) -> None:
    """LLM最终裁决。复刻 FinalLLMJudge。"""
    if not llm_client or not candidates: return

    lines = ["## 研报原文", event_text[:3000], "", "## 候选股票"]
    for i, c in enumerate(candidates, 1):
        gate = gates.get(c.stock_id)
        ev = c.evidence
        profile_text = ""
        if gate:
            profile_text = f"{gate.concept} | {' '.join(gate.must_terms[:5])}"
        lines.append(f"C{i}. {c.stock_id} {c.stock_name} sim={c.dense_score:.3f}")
        if profile_text:
            lines.append(f"   {profile_text[:180]}")
        if ev.get('must_hits'):
            lines.append(f"   ★ must命中: {', '.join(ev['must_hits'][:6])}")
        if ev.get('should_hits'):
            lines.append(f"   · should: {', '.join(ev['should_hits'][:4])}")
        if ev.get('not_hits'):
            lines.append(f"   ⚠ 冲突: {', '.join(ev['not_hits'][:3])}")
        if ev.get('concept_hit'):
            lines.append(f"   ★ 概念命中")
        lines.append("")

    resp = await llm_client.chat_completion(
        messages=[{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": "\n".join(lines)}],
        temperature=0, max_tokens=6000,
    )
    raw = resp.get("content", "")
    m = re.search(r'\[[\s\S]*\]', raw)
    if not m:
        logger.warning(f"LLM Judge no JSON: {raw[:200]}")
        return
    json_str = m.group()
    # 修复截断的JSON
    if not json_str.rstrip().endswith(']'):
        last_comma = json_str.rfind(',')
        if last_comma > 0:
            json_str = json_str[:last_comma] + ']'
        else:
            json_str = json_str.rstrip().rstrip(',') + ']'
    try:
        verified = json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试逐行解析
        try:
            verified = []
            for line in json_str.strip('[]').split('},{'):
                line = '{' + line.strip('{').strip('}') + '}'
                verified.append(json.loads(line))
        except:
            logger.warning(f"LLM JSON unrecoverable: {json_str[:200]}")
            return
    vmap = {v["stock_id"]: v for v in verified if isinstance(v, dict)}
    for c in candidates:
        v = vmap.get(c.stock_id)
        if v:
            c.llm_verdict = v.get("verdict", "")
            c.llm_confidence = float(v.get("confidence", 0))
            c.llm_reason = v.get("reason", "")

# ==================== Theme Lookup (兜底) ====================
async def theme_lookup(event_text: str) -> Dict[str, Dict]:
    """匹配 JYHF 主题 → 查 theme_stock_map → 兜底候选。"""
    stocks: Dict[str, Dict] = {}
    conn = await asyncpg.connect(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
    try:
        # 用原文直接匹配主题名
        # 滑动窗口 2-4 字，确保短词不被长词吞掉
        raw_terms = set()
        for w in (2, 3, 4):
            for i in range(len(event_text) - w + 1):
                seg = event_text[i:i+w]
                if re.match(r'^[\u4e00-\u9fff\w]+$', seg):
                    raw_terms.add(seg)
        terms = sorted(raw_terms, key=lambda t: -len(t))[:40]
        conds, params = [], []
        for t in set(terms):
            conds.append(f"concept ILIKE ${len(params)+1}")
            params.append(f"%{t}%")
        if not conds: return stocks

        rows = await conn.fetch(f"""
            SELECT subject_key, concept FROM theme_gate_profile
            WHERE char_length(coalesce(concept,'')) >= 2 AND ({' OR '.join(conds)}) LIMIT 5
        """, *params)
        sks = [r['subject_key'] for r in rows]
        if sks:
            tsm = await conn.fetch("""
                SELECT DISTINCT tsm.stock_id, tsm.stock_name, tsm.relation_type, spe.profile_text
                FROM theme_stock_map tsm
                LEFT JOIN stock_profile_ext spe ON tsm.stock_id = spe.stock_id
                WHERE tsm.subject_key = ANY($1::varchar[])
            """, sks)
            for r in tsm:
                sid = r['stock_id']
                if sid not in stocks:
                    stocks[sid] = {"stock_id": sid, "stock_name": r['stock_name'],
                                   "dense_score": 0.5, "profile_text": r.get('profile_text','') or ''}
    finally:
        await conn.close()
    return stocks

# ==================== Engine ====================
class StockMatchEngine:
    """个股匹配引擎。"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.model = SentenceModel()
        self.recall = DenseRecall(self.model)
        self._gates: Dict[str, StockGate] = {}

    async def initialize(self):
        self._gates = await load_gates()
        logger.info(f"StockMatchEngine: {len(self._gates)} gates loaded")

    async def _llm_extract_themes(self, text: str) -> List[str]:
        """LLM 结构化提取：读事件 → 输出 JYHF 主题名列表。"""
        if not self.llm:
            raise RuntimeError("LLM required")
        system = """你是新闻事件主题提取器。读完新闻后，列出该事件涉及的JYHF题材库主题名。

规则：
1. 输出主题的简洁名称（2-6字），如"绿电""算力租赁""存储芯片""AI光互连"
2. 从产业链角度推理：政策利好→哪些环节受益→对应什么主题
3. 输出JSON: {"themes": ["绿电","新能源发电","碳排放交易"]}
4. 3-6个主题，不输出解释"""
        resp = await self.llm.chat_completion(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": f"新闻:\n{text[:3000]}"}],
            temperature=0.1, max_tokens=300,
        )
        m = re.search(r'\{[\s\S]*\}', resp.get("content", ""))
        if not m: return []
        return json.loads(m.group()).get("themes", [])

    async def _theme_to_stocks(self, theme_names: List[str]) -> Dict[str, Dict]:
        """JYHF 主题名 → subject_key → theme_stock_map → 股票列表。"""
        stocks: Dict[str, Dict] = {}
        if not theme_names: return stocks
        conn = await asyncpg.connect(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
        try:
            conds, params = [], []
            for t in theme_names:
                if len(t) < 2: continue
                conds.append(f"concept ILIKE ${len(params)+1}")
                params.append(f"%{t}%")
            if not conds: return stocks
            rows = await conn.fetch(f"""
                SELECT subject_key, concept FROM theme_gate_profile
                WHERE char_length(coalesce(concept,'')) >= 2 AND ({' OR '.join(conds)})
                LIMIT 10
            """, *params)
            sks = [r['subject_key'] for r in rows]
            if sks:
                tsm = await conn.fetch("""
                    SELECT DISTINCT tsm.stock_id, tsm.stock_name, tsm.relation_type, spe.profile_text
                    FROM theme_stock_map tsm
                    LEFT JOIN stock_profile_ext spe ON tsm.stock_id = spe.stock_id
                    WHERE tsm.subject_key = ANY($1::varchar[])
                """, sks)
                score = {'leader': 0.85, 'core': 0.75, 'member': 0.65}
                for r in tsm:
                    sid = r['stock_id']
                    if sid not in stocks or r['relation_type'] == 'leader':
                        stocks[sid] = {
                            "stock_id": sid, "stock_name": r['stock_name'],
                            "dense_score": score.get(r['relation_type'], 0.65),
                            "profile_text": r.get('profile_text','') or '',
                        }
        finally:
            await conn.close()
        return stocks

    async def match(self, research_text: str, max_candidates: int = 5) -> MatchResult:
        if not self._gates: await self.initialize()

        # 1. LLM 结构化提取：事件语义 → JYHF 主题名
        theme_names = await self._llm_extract_themes(research_text)

        # 2. 主题名 → JYHF subject_key → theme_stock_map 查表
        theme_stocks = await self._theme_to_stocks(theme_names)

        # 3. Dense Recall 补充
        dense_rows = await self.recall.recall(research_text, top_k=100)

        # 4. 合并（JYHF curated 映射为核心路径）
        existing = {r['stock_id'] for r in dense_rows}
        for sid, s in theme_stocks.items():
            if sid not in existing:
                dense_rows.append(s)

        # 3. Gate Evidence + Rerank
        candidates = rerank(dense_rows, self._gates, research_text)

        # 4. Dynamic TopK + JYHF主题股优先 + Direct-Hit Reserve
        topk = compute_dynamic_topk(candidates, min_k=8, max_k=18)
        theme_hits = [c for c in candidates if c.stock_id in theme_stocks]
        gate_hits = [c for c in candidates if c not in theme_hits and c.evidence.get('must_hits')]
        others = [c for c in candidates if c not in theme_hits and c not in gate_hits]
        llm_pool = (theme_hits + gate_hits + others)[:topk]

        # 5. LLM Judge
        if self.llm:
            await llm_judge(self.llm, research_text, llm_pool, self._gates)

        # 6. Select
        matched = [c for c in llm_pool if getattr(c, 'llm_verdict', '') == 'MATCH']
        partial = [c for c in llm_pool if getattr(c, 'llm_verdict', '') == 'PARTIAL']
        matched.sort(key=lambda c: getattr(c, 'llm_confidence', 0), reverse=True)
        partial.sort(key=lambda c: getattr(c, 'llm_confidence', 0), reverse=True)
        picks = (matched + partial)[:max_candidates]

        return MatchResult(
            event_id=0, matched=len(matched) > 0, verdict="MATCH" if matched else "PARTIAL",
            candidates=[{
                "stock_id": c.stock_id, "stock_name": c.stock_name,
                "dense_score": c.dense_score, "rerank_score": c.rerank_score,
                "llm_verdict": getattr(c, 'llm_verdict', ''),
                "llm_confidence": getattr(c, 'llm_confidence', 0),
                "llm_reason": getattr(c, 'llm_reason', ''),
                "evidence": c.evidence,
            } for c in picks],
            audit={"dense_count": len(dense_rows), "topk": topk, "llm_calls": 1},
        )

# ==================== Test ====================
GREEN_CERT_TEXT = """【国家能源局：将持续完善绿证价格形成机制 研究制定绿证价格指数并适时向社会公布】财联社4月27日电，国家能源局4月27日举行新闻发布会，国家能源局新能源司副司长潘慧敏表示，下一步，将重点开展以下工作：一是完善市场交易机制。持续完善绿证价格形成机制，研究制定绿证价格指数并适时向社会公布，稳定企业对绿证价格的预期。二是强化机制协同衔接。印发非化石能源电力消费核算指南，明确绿证纳入碳排放双控和碳排放核算的具体办法，让绿证成为行业企业降碳减排的基本核算工具。三是扩大绿证消费规模。建立可再生能源消费最低比重目标制度，引导更多重点用能行业发挥绿色电力消费"领头羊"作用。推广"绿车充绿电"、居民绿电零售套餐，营造全社会主动绿色消费良好氛围。四是构建认证机制和标准体系。"""


async def quick_test():
    import aiohttp

    class QuickLLM:
        async def chat_completion(self, messages, temperature=0.1, max_tokens=512):
            headers = {"Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY')}",
                       "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat", "messages": messages,
                       "temperature": temperature, "max_tokens": max_tokens, "stream": False}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions",
                                  headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    data = await r.json()
                    return {"content": data["choices"][0]["message"]["content"]}

    engine = StockMatchEngine(llm_client=QuickLLM())
    await engine.initialize()

    tests = [
        ("Micro LED/存储", '【研选】"光进铜退"趋势下Micro LED迎发展机遇，中长期国产化替代与产业放量空间广阔，是AI光互连赛道核心优质方向；公司持续加码新型嵌入式存储、SiP封装mSSD、企业级存储等高景气赛道'),
        ("算力/国产算力", "我国日均词元调用量飙涨超千倍 算力租赁千亿大市场来了。机构建议关注国产算力基础设施产业链4大细分领域，这家公司积极参与了全国多个算力中心建设，另一家为智谱AI提供底层算力支持。"),
        ("绿证政策/绿电", GREEN_CERT_TEXT),
    ]

    targets_by_label = {
        "Micro LED/存储": {'301308'},
        "算力/国产算力": {'688158','000938'},
        "绿证政策/绿电": {'000027','600098','000875'},
    }
    for label, text in tests:
        result = await engine.match(text, max_candidates=5)
        print(f"\n{'='*60}\n📰 {label}\n{'='*60}")
        print(f"dense={result.audit['dense_count']} topk={result.audit['topk']} → {len(result.candidates)}")
        targets = targets_by_label.get(label, set())
        found = set()
        for s in result.candidates:
            sid = s['stock_id']; v = s.get('llm_verdict','?')
            flag = {'MATCH':'✅','PARTIAL':'⚠️'}.get(v,' ')
            if sid in targets: found.add(sid)
            m = ' ★' if sid in targets else '  '
            ev = s.get('evidence',{})
            print(f"  {flag}{m} {sid} {s['stock_name']:8s} must={ev.get('must_hits',[])} {s.get('llm_reason','')[:80]}")
        print(f"  → 命中: {found or '❌'}")

if __name__ == "__main__":
    asyncio.run(quick_test())

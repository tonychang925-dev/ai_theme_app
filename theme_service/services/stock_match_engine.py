"""
stock_match_engine.py — 个股匹配引擎（复刻 final_theme_matcher 架构）

流水线:
  研报原文 → LLM提取术语 → JYHF Theme Gate匹配 → theme_stock_map
          → Dense Recall → Stock Gate Evidence → Rerank → Dynamic TopK → LLM Judge

两步互补:
  Step 1 — JYHF Theme Gate: LLM提取可检索术语 → Gate-match theme_gate_profile
          → 命中subject_key → theme_stock_map → JYHF候选
  Step 2 — Stock Gate: embedding召回 + stock_gate_profile Gate Evidence
          → 覆盖JYHF未收录的题材

不修改已有组件。
"""
from __future__ import annotations

import asyncio, json, logging, math, os, re, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import asyncpg
import jieba
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
class ThemeGateMatch:
    """JYHF主题Gate匹配结果。"""
    subject_key: str
    concept: str
    must_hits: List[str]
    strong_hits: List[str]
    should_hits: List[str]
    score: int

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

async def load_theme_gates() -> List[Dict]:
    """加载 theme_gate_profile 到内存（635条），用于术语Gate匹配。"""
    conn = await asyncpg.connect(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
    try:
        rows = await conn.fetch("""
            SELECT subject_key, concept, must_terms, strong_terms, should_terms, quality
            FROM theme_gate_profile
            WHERE must_terms IS NOT NULL
        """)
        gates = []
        for r in rows:
            gates.append({
                'subject_key': r['subject_key'],
                'concept': r['concept'] or '',
                'must_terms': _ensure_list(r['must_terms']),
                'strong_terms': _ensure_list(r['strong_terms']),
                'should_terms': _ensure_list(r['should_terms']),
                'quality': r['quality'] or 'weak',
            })
        return gates
    finally:
        await conn.close()

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
def _term_in_text(term: str, text: str) -> bool:
    """词边界匹配：term必须作为独立分词单元出现在text中。

    中文使用 jieba 分词后做集合匹配，避免子串假阳性（如"水"命中"水平"）。
    term长度不足2字符时直接拒绝，防止单字符噪声。
    """
    if not term or not text:
        return False
    if len(term) < 2:
        return False
    tokens = set(jieba.lcut(text))
    return term in tokens


def build_gate_evidence(event_text: str, gate: StockGate, profile_text: str = "") -> Dict:
    """匹配事件原文与个股 gate 术语。只对事件原文做匹配。"""
    must_hits = [t for t in gate.must_terms if _term_in_text(t, event_text)]
    should_hits = [t for t in gate.should_terms if _term_in_text(t, event_text)]
    not_hits = [t for t in gate.not_terms if _term_in_text(t, event_text)]

    concept_hit = gate.concept and len(gate.concept) >= 2 and _term_in_text(gate.concept, event_text)

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
    """融合式 rerank：semantic + gate evidence。JYHF主题分已在 dense_score 中体现。"""
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
                     gates: Dict[str, StockGate], jyhf_stocks: Dict[str, Dict] = None) -> None:
    """LLM最终裁决。复刻 FinalLLMJudge。"""
    if not llm_client or not candidates: return

    lines = ["## 研报原文", event_text[:1200], "", "## 候选股票"]
    for i, c in enumerate(candidates, 1):
        gate = gates.get(c.stock_id)
        ev = c.evidence
        lines.append(f"C{i}. {c.stock_id} {c.stock_name}")
        if gate:
            lines.append(f"   概念: {gate.concept}")
        if ev.get('must_hits'):
            lines.append(f"   must: {', '.join(ev['must_hits'][:5])}")
        if jyhf_stocks and c.stock_id in jyhf_stocks:
            js = jyhf_stocks[c.stock_id]
            reason = js.get('jyhf_reason','')
            if reason and 'derived from' not in reason:
                lines.append(f"   入选: {reason[:120]}")

    resp = await llm_client.chat_completion(
        messages=[{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": "\n".join(lines)}],
        temperature=0, max_tokens=8000,
    )
    raw = resp.get("content", "")
    # 尝试匹配完整JSON数组，或截断的JSON
    m = re.search(r'\[[\s\S]*\]', raw)
    json_str = None
    if m:
        json_str = m.group()
    else:
        # 截断场景：提取所有完整JSON对象
        m = re.search(r'\[[\s\S]*', raw)
        if not m:
            logger.warning(f"LLM Judge no JSON: {raw[:200]}")
            return
        json_str = m.group()
        # 找最后一个完整的 "} 并截断
        last = json_str.rfind('"}')
        if last > 0:
            json_str = json_str[:last + 2] + ']'
        else:
            last_comma = json_str.rfind(',')
            if last_comma > 0:
                json_str = json_str[:last_comma] + ']'

    # 解析：先尝试标准解析，再逐对象解析
    try:
        verified = json.loads(json_str)
    except json.JSONDecodeError:
        verified = []
        # 从原始文本中逐个提取完整JSON对象（包含verdict的才算）
        for m in re.finditer(r'\{\s*"stock_id"\s*:\s*"[^"]*"[^}]*"verdict"[^}]*\}', raw):
            try:
                verified.append(json.loads(m.group()))
            except json.JSONDecodeError:
                continue
        if not verified:
            logger.warning(f"LLM JSON unrecoverable: {raw[:200]}")
            return
    vmap = {v["stock_id"]: v for v in verified if isinstance(v, dict)}
    for c in candidates:
        v = vmap.get(c.stock_id)
        if v:
            c.llm_verdict = v.get("verdict", "")
            c.llm_confidence = float(v.get("confidence", 0))
            c.llm_reason = v.get("reason", "")

# ==================== Engine ====================
class StockMatchEngine:
    """个股匹配引擎 — 两步互补：JYHF Theme Gate + Stock Gate。"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.model = SentenceModel()
        self.recall = DenseRecall(self.model)
        self._gates: Dict[str, StockGate] = {}
        self._theme_gates: List[Dict] = []

    async def initialize(self):
        self._gates = await load_gates()
        self._theme_gates = await load_theme_gates()
        logger.info(f"StockMatchEngine: {len(self._gates)} stock gates + {len(self._theme_gates)} theme gates loaded")

    async def _llm_extract_search_terms(self, text: str) -> List[str]:
        """LLM 结构化提取：读事件 → 输出可检索术语列表（用于 Gate 匹配 theme_gate_profile）。"""
        if not self.llm:
            raise RuntimeError("LLM required")
        system = """你是新闻事件投资术语提取器。你的任务是提取"在A股市场中可用于检索投资题材的关键术语"。

规则：
1. 提取新闻中涉及的产业链、技术、产品、政策等可投资方向词（2-6字优先）
2. 禁止提取：公司名、人名、地名、纯数字、股东/人事/管理等非投资概念
3. 如果新闻是关于某个具体公司的（非行业/政策事件），从该公司所处行业提取术语
4. 避免过于宽泛的通用词（单字词、AI/芯片等无区分度的词）
5. 每个术语必须是A股研报中会用到的行业/题材分类词
6. 输出JSON: {"search_terms":["术语1","术语2",...]}
7. 如果新闻内容与A股投资完全无关（如纯公司人事、海外公司动态），返回空列表
8. 6-10个术语"""
        resp = await self.llm.chat_completion(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": f"新闻:\n{text[:3000]}"}],
            temperature=0.1, max_tokens=350,
        )
        m = re.search(r'\{[\s\S]*\}', resp.get("content", ""))
        if not m: return []
        return json.loads(m.group()).get("search_terms", [])

    async def _match_theme_gates(self, search_terms: List[str], event_text: str = "") -> List[ThemeGateMatch]:
        """双向 Gate-match theme_gate_profile：LLM提取词 ∪ 事件原文 做匹配面。"""
        if not self._theme_gates:
            self._theme_gates = await load_theme_gates()
            logger.info(f"Theme gates loaded: {len(self._theme_gates)}")

        # 原文也作为匹配面（和 Stock Gate 一致：Gate term 在原文出现？）
        matches = []
        for tg in self._theme_gates:
            # LLM提取词命中 = 高分; 原文命中(LLM未提取) = 低分, 防止泛词泛滥
            must_hits_llm = [t for t in tg['must_terms'] if t in search_terms]
            must_hits_text = [t for t in tg['must_terms'] if t not in search_terms and _term_in_text(t, event_text)]
            strong_hits_llm = [t for t in tg['strong_terms'] if t in search_terms]
            strong_hits_text = [t for t in tg['strong_terms'] if t not in search_terms and _term_in_text(t, event_text)]
            should_hits = [t for t in tg['should_terms'] if t in search_terms or _term_in_text(t, event_text)]
            if not must_hits_llm and not must_hits_text and not strong_hits_llm and not strong_hits_text:
                continue
            # LLM提取命中: must=5, strong=3; 原文兜底命中: must=2, strong=1
            score = (len(must_hits_llm) * 5 + len(must_hits_text) * 2
                     + len(strong_hits_llm) * 3 + len(strong_hits_text) * 1
                     + len(should_hits) * 1)
            # 最低分阈值：过滤单弱词/单字符噪声命中
            if score < 5:
                continue
            must_hits = must_hits_llm + must_hits_text
            strong_hits = strong_hits_llm + strong_hits_text
            matches.append(ThemeGateMatch(
                subject_key=tg['subject_key'],
                concept=tg['concept'],
                must_hits=must_hits,
                strong_hits=strong_hits,
                should_hits=should_hits[:5],
                score=score,
            ))
        matches.sort(key=lambda m: (-m.score, -len(m.must_hits), -len(m.strong_hits)))
        return matches[:10]

    async def _theme_to_stocks(self, subject_keys: List[str],
                               theme_scores: Dict[str, int] = None) -> Dict[str, Dict]:
        """subject_key → theme_stock_map → 股票列表（含映射理由 + 主题分加成）。"""
        stocks: Dict[str, Dict] = {}
        if not subject_keys: return stocks
        if theme_scores is None:
            theme_scores = {}
        conn = await asyncpg.connect(user="postgres", password="postgres", host="localhost", port=5432, database="stock_data_test")
        try:
            tsm = await conn.fetch("""
                SELECT DISTINCT ON (tsm.stock_id)
                    tsm.stock_id, tsm.stock_name, tsm.relation_type,
                    tsm.reason, tsm.remark, tsm.confidence,
                    tsm.subject_key AS stock_subject_key,
                    tgp.concept AS theme_concept,
                    scs.child_name, scs.full_name AS child_full_name,
                    scsr.reason AS child_stock_reason,
                    spe.profile_text
                FROM theme_stock_map tsm
                LEFT JOIN theme_gate_profile tgp ON tsm.subject_key = tgp.subject_key
                LEFT JOIN subject_children_staging scs
                    ON scs.parent_subject_key = tsm.subject_key
                    AND scs.lead_stock_id = tsm.stock_id
                LEFT JOIN subject_child_stock_reason scsr
                    ON scsr.subject_key = tsm.subject_key
                    AND scsr.stock_id = tsm.stock_id
                    AND scsr.source_type = 'cdp_dom_detailed'  -- 优先CDP提取的详细理由
                LEFT JOIN stock_profile_ext spe ON tsm.stock_id = spe.stock_id
                WHERE tsm.subject_key = ANY($1::varchar[])
                ORDER BY tsm.stock_id, CASE tsm.relation_type
                    WHEN 'leader' THEN 1 WHEN 'core' THEN 2 ELSE 3 END
            """, subject_keys)
            score = {'leader': 0.85, 'core': 0.75, 'member': 0.65}
            for r in tsm:
                sid = r['stock_id']
                # 构造 JYHF 映射理由：题材→子类→个股 + 入选理由
                theme_concept = r.get('theme_concept','') or ''
                child_name = r.get('child_name','') or ''
                child_full = r.get('child_full_name','') or ''
                child_reason = r.get('child_stock_reason','') or ''
                jyhf_reason_parts = []
                if child_full:
                    jyhf_reason_parts.append(child_full)
                elif child_name:
                    jyhf_reason_parts.append(f"{theme_concept}-{child_name}" if theme_concept else child_name)
                elif theme_concept:
                    jyhf_reason_parts.append(theme_concept)
                if child_reason and 'lead_stock' not in child_reason.lower():
                    jyhf_reason_parts.append(child_reason)
                db_reason = r.get('reason','') or ''
                if db_reason and 'derived from' not in db_reason.lower():
                    jyhf_reason_parts.append(db_reason)
                jyhf_reason = ' | '.join(jyhf_reason_parts) if jyhf_reason_parts else db_reason

                # dense_score = relation_type基础分 + 主题Gate分加成
                stock_score = score.get(r['relation_type'], 0.65)
                sk = r.get('stock_subject_key', '') or ''
                ts = theme_scores.get(sk, 0)
                # CDP详细理由股票：主题分×0.02，保底0.85
                has_cdp = child_reason and 'lead_stock' not in child_reason.lower()
                stock_score += ts * (0.02 if has_cdp else 0.004)
                if has_cdp:
                    stock_score = max(stock_score, 0.85)

                if sid not in stocks or r['relation_type'] == 'leader':
                    stocks[sid] = {
                        "stock_id": sid, "stock_name": r['stock_name'],
                        "dense_score": stock_score,
                        "profile_text": r.get('profile_text','') or '',
                        "relation_type": r['relation_type'],
                        "subject_key": r.get('stock_subject_key', '') or '',
                        "jyhf_reason": jyhf_reason,
                        "jyhf_remark": r.get('remark','') or '',
                        "jyhf_confidence": float(r.get('confidence', 0)),
                    }
        finally:
            await conn.close()
        return stocks

    async def match(self, research_text: str, max_candidates: int = 5) -> MatchResult:
        if not self._gates: await self.initialize()

        # ===== Step 1: LLM 提取可检索术语 + JYHF Theme Gate 匹配 =====
        search_terms = await self._llm_extract_search_terms(research_text)

        # 术语 → Gate-match theme_gate_profile → subject_keys
        theme_matches = await self._match_theme_gates(search_terms, research_text)
        subject_keys = [m.subject_key for m in theme_matches]

        # subject_keys → theme_stock_map → JYHF候选股票
        theme_score_map = {m.subject_key: m.score for m in theme_matches}
        jyhf_stocks = await self._theme_to_stocks(subject_keys, theme_score_map)

        # ===== Step 2: Dense Recall（补充 JYHF 未覆盖的股票）=====
        dense_rows = await self.recall.recall(research_text, top_k=100)

        # ===== Step 3: 合并（JYHF主题股优先）=====
        existing = {r['stock_id'] for r in dense_rows}
        for sid, s in jyhf_stocks.items():
            if sid not in existing:
                dense_rows.append(s)

        # ===== Step 4: Stock Gate Evidence + Rerank =====
        candidates = rerank(dense_rows, self._gates, research_text)

        # ===== Step 5: Dynamic TopK — 高分主题股票优先，三路保留最低槽位 =====
        topk = compute_dynamic_topk(candidates, min_k=8, max_k=20)
        # JYHF股票按所属主题分降序排列
        jyhf_hits = [c for c in candidates if c.stock_id in jyhf_stocks]
        jyhf_hits.sort(key=lambda c: -theme_score_map.get(
            jyhf_stocks.get(c.stock_id, {}).get('subject_key', ''), 0))
        gate_hits = [c for c in candidates if c not in jyhf_hits and c.evidence.get('must_hits')]
        others = [c for c in candidates if c not in jyhf_hits and c not in gate_hits]
        # JYHF最多占一半，Gate至少5，Others至少3，创业板至少2
        jyhf_slots = min(len(jyhf_hits), max(topk // 2, topk - len(gate_hits) - len(others)))
        gate_slots = min(len(gate_hits), max(5, (topk - jyhf_slots) // 2))
        others_slots = min(len(others), max(3, topk - jyhf_slots - gate_slots))
        # 创业板(300xxx)保留槽位：在jyhf_hits中把前N只创业板提前
        chinext_jyhf = [c for c in jyhf_hits if c.stock_id.startswith('300')]
        other_jyhf = [c for c in jyhf_hits if not c.stock_id.startswith('300')]
        chinext_slots = min(len(chinext_jyhf), max(2, jyhf_slots // 3))
        other_slots = jyhf_slots - chinext_slots
        llm_pool = (chinext_jyhf[:chinext_slots] + other_jyhf[:other_slots]
                    + gate_hits[:gate_slots] + others[:others_slots])[:topk]

        # ===== Step 6: LLM Judge =====
        if self.llm:
            await llm_judge(self.llm, research_text, llm_pool, self._gates, jyhf_stocks)

        # ===== Step 7: Select =====
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
            audit={
                "search_terms": search_terms,
                "theme_matches": [{"subject_key": m.subject_key, "concept": m.concept,
                                   "score": m.score, "must_hits": m.must_hits}
                                  for m in theme_matches],
                "jyhf_stocks": len(jyhf_stocks),
                "dense_count": len(dense_rows),
                "topk": topk,
                "llm_calls": 2,
            },
        )

# ==================== Test ====================
QUANTUM_TEXT = """我国第四代自主超导量子计算机"本源悟空-180"上线】财联社5月9日电，记者今天（9日）从安徽省量子计算芯片重点实验室获悉，搭载单核180个计算比特自主超导量子芯片的"本源悟空-180"量子计算机已上线运行，今日起开始接收全球量子计算任务。第四代自主超导量子计算机"本源悟空-180"主要技术参数为：搭载单核180个计算比特超导量子芯片，在单芯片架构上实现百比特级量子计算，具备180个可直接投入实际运算的计算量子比特，单比特逻辑门保真度99.9%，双比特逻辑门保真度99%，读取保真度99%，另有251个耦合量子比特。第四代自主超导量子计算机"本源悟空-180"由我国自主研发，全链条自主可控。其搭载的量子计算芯片系统、量子计算测控系统、量子计算环境支撑系统及量子计算机操作系统等4个关键核心体系，均由本源量子全栈自主研制。 (央视新闻)

我国第四代自主超导量子计算机"本源悟空-180"上线，机构称量子计算产业已进入技术、产业、政策共振期，这家公司间接持有本源量子股权，另一家相关产品已交付下游科研和产业客户。"""

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
        ("量子计算/本源悟空", QUANTUM_TEXT),
        ("算力期货/芝商所", '【驱动事件：芝商所和GPU市场情报及基准数据行业领导者Silicon Data宣布，将于今年晚些时候推出算力期货市场】芝商所和GPU市场情报及基准数据行业领导者Silicon Data宣布，将于今年晚些时候推出算力期货市场，目前正在等待监管部门的审查。（新闻来源：财联社）'),
    ]

    targets_by_label = {
        "Micro LED/存储": {'301308'},
        "算力/国产算力": {'688158','000938'},
        "绿证政策/绿电": {'000027','600098','000875'},
        "量子计算/本源悟空": set(),
        "算力期货/芝商所": set(),
    }
    for label, text in tests:
        result = await engine.match(text, max_candidates=5)
        print(f"\n{'='*60}\n📰 {label}\n{'='*60}")
        print(f"search_terms={result.audit.get('search_terms',[])}")
        print(f"theme_matches={len(result.audit.get('theme_matches',[]))} jyhf_stocks={result.audit.get('jyhf_stocks',0)}")
        print(f"dense={result.audit['dense_count']} topk={result.audit['topk']} → {len(result.candidates)}")
        if result.audit.get('theme_matches'):
            for tm in result.audit['theme_matches'][:5]:
                print(f"  🏷 JYHF: {tm['concept']}({tm['subject_key']}) score={tm['score']} must={tm['must_hits']}")
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

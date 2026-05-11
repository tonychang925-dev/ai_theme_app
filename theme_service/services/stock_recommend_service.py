"""
stock_recommend_service.py — 研选荐股服务

全链路（Phase 2: 双路召回）:
  1次LLM提取 → 主题查表(池A) + embedding召回(池B) → 合并A∪B → Gate → LLM核查 → 精选

不修改任何已有组件。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# Prompt
# ============================================================
RESEARCH_EXTRACT_SYSTEM = """分析以下研报文本。提取所有可用于搜索匹配的意图短语。输出合法JSON。

{
  "search_intents": [
    "国产算力",
    "国产算力芯片",
    "IDC算力租赁",
    "云服务CDN",
    "AI服务器",
    "算力中心建设",
    "为智谱AI提供算力支持",
    "参与全国算力中心建设"
  ],
  "summary": "一句话核心观点"
}

要求：
- search_intents: 把文中所有投资主题、细分方向、产品技术、公司特征描述，全部展开为简短搜索短语（2-15字）
  展开要具体，不要笼统。例如"4大细分领域"→展开为每个领域的具体短语
- 不要输出标题噱头，要输出实质内容
- 不要重复
"""

STOCK_VERIFY_BATCH_SYSTEM = """你是资深股票分析师。阅读完整研报，推理每只候选股票与研报的相关性。**每只股票必须给出判定**。

你拿到的信息：
1. 研报全文（含具体公司描述、业务特征、产品突破、行业趋势）
2. 候选股票列表（含定位、亮点、关键事实）

请对每只股票判断：
- MATCH: 研报中明确描述/暗示的公司，或主营业务与研报核心议题高度吻合
- PARTIAL: 部分相关，非核心
- MISMATCH: 不相关

关键要求：注意研报中具体公司的特征描述（如"为XX提供底层算力"、"参与XX算力中心建设"），
需要推理哪些候选股票符合这些特征，而不是简单关键词匹配。

输出JSON数组：
[
  {"stock_id":"000001","verdict":"MATCH|PARTIAL|MISMATCH","confidence":0.85,"reason":"20字内"},
  ...
]
"""

# ============================================================
# 数据结构
# ============================================================
@dataclass
class StockRecommendResult:
    event_id: int
    matched: bool
    matched_theme_name: str
    extracted_info: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[Dict] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "matched": self.matched,
            "matched_theme_name": self.matched_theme_name,
            "extracted": self.extracted_info,
            "recommendations": [
                {
                    "stock_id": s["stock_id"],
                    "stock_name": s["stock_name"],
                    "relation_type": s.get("relation_type", ""),
                    "remark": s.get("remark", "")[:120],
                    "lightspots": s.get("lightspots", [])[:3],
                    "gate_score": s.get("gate_score", 0),
                    "llm_verdict": s.get("llm_verdict", ""),
                    "llm_reason": s.get("llm_reason", ""),
                }
                for s in self.recommendations
            ],
            "stock_count": len(self.recommendations),
            "audit": self.audit,
        }


# ============================================================
# 服务
# ============================================================
class StockRecommendService:
    """研选荐股服务 — 最少LLM调用。"""

    def __init__(self, db_gateway=None, llm_client=None):
        self._db = db_gateway
        self._llm = llm_client

    def set_database_gateway(self, gateway):
        self._db = gateway

    def set_llm_client(self, llm_client):
        self._llm = llm_client

    # ----------------------------------------------------------
    # 主入口：从研报文本推荐股票（2次LLM）
    # ----------------------------------------------------------
    async def recommend_from_text(
        self,
        research_text: str,
        max_candidates: int = 7,
        use_llm_verify: bool = True,
    ) -> StockRecommendResult:
        """全链路: 提取→匹配→查表→评分→(可选LLM批量核查)→输出"""
        # Step 1: LLM 结构化提取（1次调用）
        extracted = await self._extract_research(research_text)
        result = StockRecommendResult(
            event_id=0, matched=False, matched_theme_name="",
            extracted_info=extracted,
        )

        intents = extracted.get("search_intents", [])
        if not intents:
            return result

        # Step 2: 匹配主题（全部 intents）
        matched = await self._match_themes(intents)
        if not matched:
            return result

        result.matched = True
        result.matched_theme_name = matched[0]["concept"]

        # Step 3a: 池A — 主题查表
        stocks_a = await self._fetch_and_enrich(matched)

        # Step 3b: 池B — embedding 语义召回（intents + 主题概念）
        theme_concepts = [t["concept"] for t in matched]
        stocks_b = await self._embedding_recall(intents, theme_concepts)

        # Step 3c: 池C — ILIKE hinted 搜索
        stocks_c = {}
        long = [t for t in intents if len(t) >= 6]
        if long:
            stocks_c = await self._search_stocks_by_hints(long)

        # 合并 A ∪ B ∪ C（A的relation_type优先保留）
        stocks = dict(stocks_a)
        for pool in (stocks_b, stocks_c):
            for sid, s in pool.items():
                if sid not in stocks:
                    stocks[sid] = s

        # 规则粗筛
        stocks = self._rule_filter(stocks)

        # Step 4: Gate 排序
        for s in stocks.values():
            s["gate_score"] = self._gate_score(intents, extracted, s)

        sorted_stocks = sorted(stocks.values(), key=lambda s: s["gate_score"], reverse=True)

        # Step 5: LLM 批量核查
        if use_llm_verify and self._llm:
            top_pool = sorted_stocks[: min(max_candidates * 3, 20)]
            if top_pool:
                verified = await self._llm_verify_batch(research_text, extracted, top_pool)
                if verified:
                    confirmed = [s for s in verified
                                 if s.get("llm_verdict") in ("MATCH", "PARTIAL")]
                    sorted_stocks = confirmed + [s for s in sorted_stocks
                        if s.get("llm_verdict") not in ("MATCH", "PARTIAL")]

        result.recommendations = [
            s for s in sorted_stocks
            if s.get("llm_verdict") not in ("MISMATCH",)
        ][:max_candidates]
        result.audit = {
            "intents": intents,
            "matched_themes": [t["concept"] for t in matched],
            "pool_a": len(stocks_a), "pool_b": len(stocks_b), "pool_c": len(stocks_c),
            "merged": len(stocks), "llm_calls": 2 if use_llm_verify else 1,
        }
        return result

    # ----------------------------------------------------------
    # Step 1: LLM 提取
    # ----------------------------------------------------------
    async def _extract_research(self, text: str) -> Dict[str, Any]:
        if not self._llm:
            raise RuntimeError("StockRecommendService: LLM客户端未注入，无法提取。请调用 set_llm_client()")
        resp = await self._llm.chat_completion(
            messages=[
                {"role": "system", "content": RESEARCH_EXTRACT_SYSTEM},
                {"role": "user", "content": f"提取下列文本:\n\n{text[:3000]}"},
            ],
            temperature=0.1, max_tokens=400,
        )
        m = re.search(r'\{[\s\S]*\}', resp.get("content", ""))
        if not m:
            raise RuntimeError(f"LLM提取未返回合法JSON: {resp.get('content','')[:200]}")
        return json.loads(m.group())

    # ----------------------------------------------------------
    # Step 2: 主题匹配
    # ----------------------------------------------------------
    async def _match_themes(self, terms: List[str]) -> List[Dict]:
        """纯 ILIKE 匹配：intent 短语 vs theme concept/search_text。"""
        conn = await self._get_conn()
        if not conn: return []
        try:
            conds, params = [], []
            for t in terms:
                if len(t) < 2: continue
                conds.append(f"(concept ILIKE ${len(params)+1})")
                params.append(f"%{t}%")

            if not conds: return []
            rows = await conn.fetch(f"""
                SELECT subject_key, concept, quality
                FROM theme_gate_profile
                WHERE char_length(coalesce(concept,'')) >= 2
                  AND ({' OR '.join(conds)})
                ORDER BY CASE quality WHEN 'strong' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END
                LIMIT 10
            """, *params)
        except Exception as e:
            logger.error(f"_match_themes: {e}")
            return []
        finally:
            await conn.close()

        results = []
        for r in rows:
            concept = (r["concept"] or "").strip()
            if len(concept) < 2: continue
            score = 1
            for t in terms:
                if t in concept: score += 10
            results.append({"subject_key": r["subject_key"], "concept": concept,
                            "quality": r.get("quality","weak"), "match_score": score})
        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results[:8]

    # ----------------------------------------------------------
    # Step 3+4: 查表 + 证据
    # ----------------------------------------------------------
    async def _fetch_and_enrich(self, matched_themes: List[Dict]) -> Dict[str, Dict]:
        stocks: Dict[str, Dict] = {}
        conn = await self._get_conn()
        if not conn: return stocks
        try:
            seen = set()
            for t in matched_themes:
                sk = t["subject_key"]
                if sk in seen: continue
                seen.add(sk)
                rows = await conn.fetch("""
                    SELECT stock_id, stock_name, relation_type, reason, confidence
                    FROM theme_stock_map WHERE subject_key = $1
                    ORDER BY CASE relation_type
                        WHEN 'leader' THEN 1 WHEN 'core' THEN 2 ELSE 3 END
                """, sk)
                for r in rows:
                    sid, rt = r["stock_id"], r["relation_type"]
                    if sid not in stocks or (
                        rt == "leader" and stocks[sid].get("relation_type") != "leader"
                    ):
                        stocks[sid] = {
                            "stock_id": sid, "stock_name": r["stock_name"],
                            "relation_type": rt, "confidence": float(r["confidence"]),
                            "reason": r["reason"] or "", "theme_matches": [t["concept"]],
                        }
                    else:
                        stocks[sid].setdefault("theme_matches", []).append(t["concept"])

            # 批量证据
            if not stocks: return stocks
            sids = list(stocks.keys())

            ls_rows = await conn.fetch(
                "SELECT stock_id, content FROM stock_lightspots "
                "WHERE stock_id = ANY($1::varchar[]) ORDER BY stock_id, lightspot_id", sids)
            for r in ls_rows:
                stocks.setdefault(r["stock_id"], {}).setdefault("lightspots", []).append(r["content"])

            try:
                f_rows = await conn.fetch(
                    "SELECT stock_id, fact_type, fact_value FROM stock_facts "
                    "WHERE stock_id = ANY($1::varchar[]) ORDER BY stock_id, id", sids)
                for r in f_rows:
                    stocks.setdefault(r["stock_id"], {}).setdefault("facts", []).append(
                        {"fact_type": r["fact_type"], "fact_value": r["fact_value"]})
            except Exception: pass

            try:
                rm_rows = await conn.fetch(
                    "SELECT stock_id, remark FROM subject_stock_detail_staging "
                    "WHERE stock_id = ANY($1::varchar[])", sids)
                for r in rm_rows:
                    if r["remark"]:
                        stocks.setdefault(r["stock_id"], {})["remark"] = r["remark"]
            except Exception: pass
        finally:
            await conn.close()
        return stocks

    # ----------------------------------------------------------
    # Step 5: 规则评分
    # ----------------------------------------------------------
    def _gate_score(self, terms: List[str], extracted: Dict, stock: Dict) -> float:
        """
        极简Gate：只做排序方向，不做内容判断。
        - relation_type 确定优先级方向
        - 关键词命中加分（相关性信号）
        - ST 过滤
        真正的质量把关交给 LLM 批量核查。
        """
        score = {"leader": 10, "core": 5, "member": 0}.get(
            stock.get("relation_type", "member"), 0)

        # 关键词命中：搜词在股票证据中的出现次数
        all_text = (
            stock.get("remark", "") + " " +
            " ".join(stock.get("lightspots", [])[:5]) + " " +
            " ".join(f.get("fact_value","") for f in stock.get("facts",[])[:10])
        )
        for t in set(extracted.get("search_intents", [])):
            if t in all_text:
                score += 3

        # ST 过滤
        name = stock.get("stock_name", "")
        if "ST" in name or "*ST" in name:
            score -= 50

        return score

    # ----------------------------------------------------------
    # Step 6 (可选): 1次 LLM 批量核查
    # ----------------------------------------------------------
    async def _llm_verify_batch(
        self, research_text: str, extracted: Dict, candidates: List[Dict]
    ) -> Optional[List[Dict]]:
        """1次LLM调用，批量核查top candidates。传入完整原文让LLM推理匹配。"""
        if not self._llm or not candidates:
            return None

        # 传入完整原文 + 所有候选股票证据，让LLM推理
        lines = [
            "## 研报全文",
            research_text[:3000],
            "",
            "## 候选股票（含定位、亮点、关键事实）",
        ]
        for i, s in enumerate(candidates, 1):
            remark = s.get("remark", "")[:120]
            spots = " | ".join(s.get("lightspots", [])[:4])
            facts = " | ".join(
                f"{f.get('fact_type','')}:{f.get('fact_value','')}"
                for f in s.get("facts", [])[:8]
            )
            lines.append(
                f"{i}. {s['stock_id']} {s['stock_name']} [{s.get('relation_type','')}]\n"
                f"   定位: {remark}\n"
                f"   亮点: {spots}\n"
                f"   事实: {facts}"
            )

        prompt = "\n".join(lines)
        try:
            resp = await self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": STOCK_VERIFY_BATCH_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1, max_tokens=2000,
            )
            raw = resp.get("content", "")
            m = re.search(r'\[[\s\S]*\]', raw)
            if not m:
                logger.warning(f"LLM批量核查未返回JSON数组: {raw[:200]}")
                return None
            verified = json.loads(m.group())

            # 构建重排映射
            vmap = {v["stock_id"]: v for v in verified if isinstance(v, dict)}
            for s in candidates:
                v = vmap.get(s["stock_id"])
                if v:
                    s["llm_verdict"] = v.get("verdict", "")
                    s["llm_confidence"] = float(v.get("confidence", 0))
                    s["llm_reason"] = v.get("reason", "")

            # MATCH优先，已按LLM排序
            matched = [s for s in candidates if s.get("llm_verdict") == "MATCH"]
            others = [s for s in candidates if s.get("llm_verdict") != "MATCH"]
            matched.sort(key=lambda s: s.get("llm_confidence", 0), reverse=True)
            return matched + others
        except Exception as e:
            logger.warning(f"LLM批量核查失败: {e}")
            return None

    async def _search_stocks_by_hints(self, hints: List[str]) -> Dict[str, Dict]:
        """用 hinted 短语搜索股票证据（手动分词 + ILIKE 多路匹配）。"""
        stocks: Dict[str, Dict] = {}
        conn = await self._get_conn()
        if not conn or not hints:
            return stocks
        try:
            for hint in hints[:4]:
                if len(hint) < 4:
                    continue
                # 拆分短语为2-3字中文词元
                tokens = [tok for tok in re.findall(r'[\u4e00-\u9fff\w]{2,3}', hint)
                          if len(tok) >= 3 or re.search(r'[\u4e00-\u9fff]', tok)]
                if not tokens:
                    tokens = [hint]
                token_conds, token_params = [], []
                for tok in tokens:
                    token_conds.append(f"sl.content ILIKE ${len(token_params)+1}")
                    token_params.append(f"%{tok}%")
                where_clause = " OR ".join(token_conds)

                rows = await conn.fetch(f"""
                    SELECT DISTINCT sl.stock_id, s.name as stock_name,
                           'hinted_match' as relation_type, 0.85 as confidence
                    FROM stock_lightspots sl
                    JOIN stocks s ON sl.stock_id = s.stock_id
                    WHERE ({where_clause})
                    LIMIT 10
                """, *token_params)
                if not rows:
                    token_conds2, token_params2 = [], []
                    for tok in tokens:
                        token_conds2.append(f"ssds.remark ILIKE ${len(token_params2)+1}")
                        token_params2.append(f"%{tok}%")
                    rows = await conn.fetch(f"""
                        SELECT DISTINCT ssds.stock_id, ssds.stock_name,
                               'hinted_match' as relation_type, 0.85 as confidence
                        FROM subject_stock_detail_staging ssds
                        WHERE ({' OR '.join(token_conds2)})
                        LIMIT 10
                    """, *token_params2)
                for r in rows:
                    sid = r["stock_id"]
                    if sid not in stocks:
                        stocks[sid] = {
                            "stock_id": sid,
                            "stock_name": r["stock_name"],
                            "relation_type": r["relation_type"],
                            "confidence": float(r["confidence"]),
                            "reason": f"命中: {hint[:60]}",
                            "theme_matches": ["hinted_match"],
                        }
        finally:
            await conn.close()
        return stocks

    # ----------------------------------------------------------
    # Embedding 语义召回（池B）
    # ----------------------------------------------------------

    _embedding_model = None

    @classmethod
    def _get_embedding_model(cls):
        if cls._embedding_model is None:
            from text2vec import SentenceModel
            cls._embedding_model = SentenceModel()
        return cls._embedding_model

    async def _embedding_recall(self, intents: List[str], theme_concepts: List[str] = None, top_k: int = 50) -> Dict[str, Dict]:
        """用 intents + 匹配主题名 联合做 embedding 语义召回。"""
        stocks: Dict[str, Dict] = {}
        if not intents:
            return stocks

        try:
            model = self._get_embedding_model()
            # 组合 intents + 匹配到的主题概念（更精准的语义锚点）
            query_parts = list(intents)
            if theme_concepts:
                query_parts.extend(theme_concepts)
            query_text = " ".join(query_parts)
            query_emb = model.encode(query_text)
            vec_str = f"[{','.join(f'{v:.6f}' for v in query_emb)}]"

            conn = await self._get_conn()
            if not conn:
                return stocks
            try:
                # 提高 IVFFlat probes 确保召回完整（避免近似索引遗漏）
                await conn.execute("SET LOCAL ivfflat.probes = 100")
                rows = await conn.fetch("""
                    SELECT spe.stock_id, spe.stock_name, spe.profile_text,
                           1 - (spe.embedding <=> $1::vector) AS similarity
                    FROM stock_profile_ext spe
                    WHERE spe.embedding IS NOT NULL
                      AND spe.stock_name NOT LIKE '%ST%'
                      AND spe.stock_name NOT LIKE '%*ST%'
                    ORDER BY spe.embedding <=> $1::vector
                    LIMIT $2
                """, vec_str, top_k)
                for r in rows:
                    sid = r['stock_id']
                    sim = float(r['similarity'])
                    if sim < 0.5:  # 最低相似度阈值
                        continue
                    stocks[sid] = {
                        "stock_id": sid,
                        "stock_name": r['stock_name'],
                        "relation_type": "semantic_match",
                        "confidence": round(sim, 2),
                        "reason": f"embedding召回(sim={sim:.2f})",
                        "theme_matches": ["semantic_match"],
                    }
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(f"embedding召回失败: {e}")
        return stocks

    # ----------------------------------------------------------
    # 规则粗筛
    # ----------------------------------------------------------
    @staticmethod
    def _rule_filter(stocks: Dict[str, Dict]) -> Dict[str, Dict]:
        """规则粗筛：过滤ST、退市等明显不合适的股票。"""
        return {
            sid: s for sid, s in stocks.items()
            if "ST" not in s.get("stock_name", "")
            and "*ST" not in s.get("stock_name", "")
        }

    async def _get_conn(self):
        import asyncpg
        try:
            return await asyncpg.connect(
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "postgres"),
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
            )
        except Exception as e:
            logger.error(f"DB连接失败: {e}")
            return None


_stock_recommend_service: Optional[StockRecommendService] = None

def get_stock_recommend_service(db_gateway=None, llm_client=None) -> StockRecommendService:
    global _stock_recommend_service
    if _stock_recommend_service is None:
        _stock_recommend_service = StockRecommendService(db_gateway, llm_client)
    else:
        if db_gateway: _stock_recommend_service.set_database_gateway(db_gateway)
        if llm_client: _stock_recommend_service.set_llm_client(llm_client)
    return _stock_recommend_service

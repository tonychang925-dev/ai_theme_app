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
RESEARCH_EXTRACT_SYSTEM = """从研报中提取结构化信息。输出合法JSON。

{
  "search_intents": ["国产算力","算力基础设施","算力中心建设"],
  "company_descriptions": ["持续加码嵌入式存储、SiP封装mSSD、企业级存储"],
  "logic_chain": "宏观趋势→行业方向→技术路线→供应链环节",
  "summary": "一句话核心观点"
}

要求：
1. search_intents: 投资主题/产品技术短语（2-15字），展开具体、不要统计数字
2. company_descriptions: 文中"公司持续加码/深耕/布局XX"等未点名但描述了的公司特征。
   注意拆开：如果描述了两家不同公司（光互连 vs 存储），要分别提取
   例如"公司加码嵌入式存储和SiP"→["加码嵌入式存储和SiP封装mSSD"]
3. logic_chain: 宏观→行业→技术→供应链 的推理链（用于后续匹配时提供上下文）
"""

STOCK_VERIFY_BATCH_SYSTEM = """你是A股研选荐股最终裁决器。

任务：在候选股票中做排他式比较，选出与研报最匹配的股票。研报可能含多个投资方向，每个方向对应不同公司。

每只候选股提供：
- stock_id / stock_name
- 定位(remark)：公司最精准的业务描述
- 证据命中(intent_hits)：研报关键短语在个股信息中的命中情况
- 亮点片段(matched_spots)：与研报相关的亮点句
- 关联类型(relation_type)：leader/core/member/semantic_match
- 评分(gate_score)

判定标准：
1. 优先选出研报"公司持续加码/深耕/布局XX"等描述直接对应的股票
2. 不要仅靠关键词匹配。例如研报提"Micro LED"，光学元件/镜头/封装/检测都可能是产业链核心
3. 注意区分不同投资方向（如AI光互连 vs 嵌入式存储），分别选出最佳匹配
4. 如果股票业务与研报方向一致但非核心角色，判为PARTIAL

输出JSON数组（每只必须有判定）：
[
  {"stock_id":"000001","verdict":"MATCH|PARTIAL|MISMATCH","confidence":0.85,"reason":"15字内"},
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
            result.audit = {"error": "no intents extracted", "llm_calls": 1}
            return result

        # Step 2: 匹配主题（全部 intents）
        matched = await self._match_themes(intents)
        if not matched:
            result.audit = {"error": "no themes matched", "intents": intents, "llm_calls": 1}
            return result

        result.matched = True
        result.matched_theme_name = matched[0]["concept"]

        # Step 3a: 池A(主) — embedding 语义召回（intents + 主题概念）
        theme_concepts = [t["concept"] for t in matched]
        stocks_a = await self._embedding_recall(intents, theme_concepts, top_k=200)

        # Step 3b: 池B(辅) — 主题查表（JYHF映射兜底）
        stocks_b = await self._fetch_and_enrich(matched)

        # Step 3c: 池C — 公司特征描述搜索（LLM推理的公司线索）
        company_descs = extracted.get("company_descriptions", [])
        stocks_c = await self._search_stocks_by_hints(company_descs) if company_descs else {}

        # Step 3d: 池D — 长intents ILIKE 搜索
        long = [t for t in intents if len(t) >= 6]
        stocks_d = await self._search_stocks_by_hints(long) if long else {}

        # 合并（embedding为主，theme_stock_map兜底补充relation_type）
        stocks = dict(stocks_a)
        new_sids = []
        for pool in (stocks_b, stocks_c, stocks_d):
            for sid, s in pool.items():
                if sid not in stocks:
                    stocks[sid] = s
                    new_sids.append(sid)

        # 为新合并的股票补证据（pool B/C 之前没填充 lightspots/facts/remark）
        if new_sids:
            await self._enrich_evidence(new_sids, stocks)

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
            "logic_chain": extracted.get("logic_chain", ""),
            "pool_emb": len(stocks_a), "pool_theme": len(stocks_b),
            "pool_company": len(stocks_c), "pool_hint": len(stocks_d),
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
        base = {"leader": 10, "core": 5, "member": 0,
                "semantic_match": 2, "hinted_match": 2}.get(
            stock.get("relation_type", "member"), 0)

        # embedding 相似度加分（semantic_match/hinted_match用confidence）
        emb_bonus = 0
        if stock.get("relation_type") in ("semantic_match", "hinted_match"):
            emb_bonus = int(float(stock.get("confidence", 0)) * 20)  # 0.70 → 14分

        # 关键词命中
        all_text = (
            stock.get("remark", "") + " " +
            " ".join(stock.get("lightspots", [])[:5]) + " " +
            " ".join(f.get("fact_value","") for f in stock.get("facts",[])[:10])
        )
        kw_hits = sum(1 for t in set(extracted.get("search_intents", [])) if t in all_text)

        score = base + emb_bonus + kw_hits * 3

        # ST 过滤
        if "ST" in stock.get("stock_name", "") or "*ST" in stock.get("stock_name", ""):
            score -= 50

        return score

    # ----------------------------------------------------------
    # Step 6 (可选): 1次 LLM 批量核查
    # ----------------------------------------------------------
    @staticmethod
    def _build_stock_evidence(intents: List[str], stock: Dict) -> Dict:
        """为单只候选股构建 Gate Evidence（参考 final_theme_matcher 模式）。"""
        remark = stock.get("remark", "") or ""
        spots = stock.get("lightspots", [])[:5]
        spots_text = " ".join(spots)
        all_text = f"{remark} {spots_text}"

        # intent_hits: 哪些搜索意图在个股证据中命中了
        intent_hits = []
        for t in intents:
            if len(t) >= 2 and t in all_text:
                intent_hits.append(t)

        # matched_spots: 包含命中的亮点句片段
        matched_spots = []
        for ls in spots:
            for t in intents:
                if len(t) >= 2 and t in ls:
                    matched_spots.append(ls[:120])
                    break

        # matched_remark: remark中命中的部分
        matched_remark = ""
        if remark:
            for t in intents:
                if len(t) >= 2 and t in remark:
                    matched_remark = remark[:150]
                    break

        return {
            "intent_hits": intent_hits,
            "matched_spots": matched_spots[:3],
            "matched_remark": matched_remark,
            "total_hits": len(intent_hits),
        }

    async def _llm_verify_batch(
        self, research_text: str, extracted: Dict, candidates: List[Dict]
    ) -> Optional[List[Dict]]:
        """1次LLM调用，批量核查。每只候选股附带 Gate Evidence。"""
        if not self._llm or not candidates:
            return None

        intents = extracted.get("search_intents", [])
        company_descs = extracted.get("company_descriptions", [])

        lines = [
            "## 研报全文",
            research_text[:2500],
            "",
        ]
        # 公司特征描述（LLM推理的未点名公司线索）
        if company_descs:
            lines.append("## 公司特征描述（需匹配的未点名公司）")
            for d in company_descs:
                lines.append(f"  - {d}")
            lines.append("")

        lines.append("## 候选股票")
        for i, s in enumerate(candidates, 1):
            ev = StockRecommendService._build_stock_evidence(intents, s)
            s["_evidence"] = ev

            remark = s.get("remark", "") or ""
            spots = s.get("lightspots", [])[:3]

            lines.append(
                f"C{i}. {s['stock_id']} {s['stock_name']} "
                f"[{s.get('relation_type','')}] gate={s.get('gate_score',0):.0f}"
            )
            # 定位（最优先）
            if remark:
                lines.append(f"   定位: {remark[:150]}")
            # 如果有直接命中，高亮展示
            if ev["intent_hits"]:
                lines.append(f"   ★ 命中({ev['total_hits']}): {', '.join(ev['intent_hits'][:8])}")
            # 亮点（始终展示，让LLM自己推理）
            if spots:
                for sp in spots[:2]:
                    lines.append(f"   亮点: {sp[:120]}")
            # 冲突信号
            if ev["total_hits"] == 0 and not remark:
                lines.append(f"   ⚠ 无直接命中，请根据定位和亮点推理相关性")
            lines.append("")

        prompt = "\n".join(lines)
        try:
            resp = await self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": STOCK_VERIFY_BATCH_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1, max_tokens=2500,
            )
            raw = resp.get("content", "")
            m = re.search(r'\[[\s\S]*\]', raw)
            if not m:
                logger.warning(f"LLM批量核查未返回JSON数组: {raw[:200]}")
                return None
            verified = json.loads(m.group())

            vmap = {v["stock_id"]: v for v in verified if isinstance(v, dict)}
            for s in candidates:
                v = vmap.get(s["stock_id"])
                if v:
                    s["llm_verdict"] = v.get("verdict", "")
                    s["llm_confidence"] = float(v.get("confidence", 0))
                    s["llm_reason"] = v.get("reason", "")

            matched = [s for s in candidates if s.get("llm_verdict") == "MATCH"]
            others = [s for s in candidates if s.get("llm_verdict") != "MATCH"]
            matched.sort(key=lambda s: s.get("llm_confidence", 0), reverse=True)
            return matched + others
        except Exception as e:
            logger.warning(f"LLM批量核查失败: {e}")
            return None

    async def _search_stocks_by_hints(self, hints: List[str]) -> Dict[str, Dict]:
        """用 hinted 短语直接搜索个股证据（lightspots + remark）。"""
        stocks: Dict[str, Dict] = {}
        conn = await self._get_conn()
        if not conn or not hints: return stocks
        try:
            for hint in hints[:8]:
                if len(hint) < 4: continue
                seen = set()
                # 全文 ILIKE 搜 lightspots
                for r in await conn.fetch("""
                    SELECT DISTINCT sl.stock_id, s.name
                    FROM stock_lightspots sl JOIN stocks s ON sl.stock_id = s.stock_id
                    WHERE sl.content ILIKE $1 LIMIT 10
                """, f"%{hint}%"):
                    if r["stock_id"] not in seen:
                        seen.add(r["stock_id"])
                        stocks[r["stock_id"]] = {"stock_id": r["stock_id"], "stock_name": r["name"],
                            "relation_type": "hinted_match", "confidence": 0.85,
                            "reason": f"命中: {hint[:60]}", "theme_matches": ["hinted_match"]}
                # 全文 ILIKE 搜 remark
                for r in await conn.fetch("""
                    SELECT DISTINCT stock_id, stock_name
                    FROM subject_stock_detail_staging WHERE remark ILIKE $1 LIMIT 10
                """, f"%{hint}%"):
                    if r["stock_id"] not in seen:
                        seen.add(r["stock_id"])
                        stocks[r["stock_id"]] = {"stock_id": r["stock_id"], "stock_name": r["stock_name"],
                            "relation_type": "hinted_match", "confidence": 0.85,
                            "reason": f"命中: {hint[:60]}", "theme_matches": ["hinted_match"]}
                # 标点拆分兜底 + 关键业务词提取
                if not seen:
                    segments = [s.strip() for s in re.split(r'[、，,；;]', hint) if len(s.strip()) >= 3]
                    # 从每段中提取关键名词短语（2-6字）
                    terms = set()
                    for seg in segments:
                        terms.add(seg[:15])  # 前15字作为搜索词
                        terms.update(re.findall(r'[\u4e00-\u9fff]{2,6}', seg))
                    for term in list(terms)[:8]:
                        if len(term) < 2: continue
                        for r in await conn.fetch("""
                            SELECT DISTINCT sl.stock_id, s.name FROM stock_lightspots sl
                            JOIN stocks s ON sl.stock_id = s.stock_id
                            WHERE sl.content ILIKE $1 LIMIT 3
                        """, f"%{term}%"):
                            if r["stock_id"] not in seen:
                                seen.add(r["stock_id"])
                                stocks[r["stock_id"]] = {"stock_id": r["stock_id"], "stock_name": r["name"],
                                    "relation_type": "hinted_match", "confidence": 0.85,
                                    "reason": f"命中: {term}", "theme_matches": ["hinted_match"]}
                        for r in await conn.fetch("""
                            SELECT DISTINCT stock_id, stock_name FROM subject_stock_detail_staging
                            WHERE remark ILIKE $1 LIMIT 3
                        """, f"%{term}%"):
                            if r["stock_id"] not in seen:
                                seen.add(r["stock_id"])
                                stocks[r["stock_id"]] = {"stock_id": r["stock_id"], "stock_name": r["stock_name"],
                                    "relation_type": "hinted_match", "confidence": 0.85,
                                    "reason": f"命中: {term}", "theme_matches": ["hinted_match"]}
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
                await conn.execute("SET LOCAL ivfflat.probes = 200")
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
                    if sim < 0.4:
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
    # 证据补充（为 pool B/C 合并后的股票补 lightspots/facts/remark）
    # ----------------------------------------------------------

    async def _enrich_evidence(self, stock_ids: List[str], stocks: Dict[str, Dict]) -> None:
        if not stock_ids: return
        conn = await self._get_conn()
        if not conn: return
        try:
            # lightspots
            ls_rows = await conn.fetch(
                "SELECT stock_id, content FROM stock_lightspots "
                "WHERE stock_id = ANY($1::varchar[]) ORDER BY stock_id, lightspot_id", stock_ids)
            for r in ls_rows:
                stocks.setdefault(r["stock_id"], {}).setdefault("lightspots", []).append(r["content"])

            # facts
            try:
                f_rows = await conn.fetch(
                    "SELECT stock_id, fact_type, fact_value FROM stock_facts "
                    "WHERE stock_id = ANY($1::varchar[]) ORDER BY stock_id, id", stock_ids)
                for r in f_rows:
                    stocks.setdefault(r["stock_id"], {}).setdefault("facts", []).append(
                        {"fact_type": r["fact_type"], "fact_value": r["fact_value"]})
            except Exception: pass

            # remark
            try:
                rm_rows = await conn.fetch(
                    "SELECT stock_id, remark FROM subject_stock_detail_staging "
                    "WHERE stock_id = ANY($1::varchar[])", stock_ids)
                for r in rm_rows:
                    if r["remark"]:
                        stocks.setdefault(r["stock_id"], {})["remark"] = r["remark"]
            except Exception: pass
        finally:
            await conn.close()

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

"""
stock_recommend_service.py — 研选荐股服务（精简版）

极简链路，最少LLM调用:
  1次LLM结构化提取 → 主题匹配(DB) → 查表(theme_stock_map) → 规则评分 → 精选输出

不修改任何已有组件。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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

        # Step 3a: 查表（主题映射）
        stocks = await self._fetch_and_enrich(matched)

        # Step 3b: 用较长短语直接搜股票证据（补齐JYHF映射遗漏）
        long = [t for t in intents if len(t) >= 6]
        if long:
            extra = await self._search_stocks_by_hints(long)
            for sid, s in extra.items():
                if sid not in stocks:
                    stocks[sid] = s

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
            "total_candidates": len(stocks),
            "llm_calls": 2 if use_llm_verify else 1,
        }
        return result

    # ----------------------------------------------------------
    # Step 1: LLM 提取
    # ----------------------------------------------------------
    async def _extract_research(self, text: str) -> Dict[str, Any]:
        if not self._llm:
            return self._fallback_extract(text)
        try:
            resp = await self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": RESEARCH_EXTRACT_SYSTEM},
                    {"role": "user", "content": f"提取下列文本:\n\n{text[:3000]}"},
                ],
                temperature=0.1, max_tokens=400,
            )
            m = re.search(r'\{[\s\S]*\}', resp.get("content", ""))
            if m: return json.loads(m.group())
        except Exception as e:
            logger.warning(f"LLM提取失败: {e}")
        return self._fallback_extract(text)

    def _fallback_extract(self, text: str) -> Dict[str, Any]:
        intents = []
        kw_map = [
            (["国产算力", "算力基础设施", "算力中心"], ["国产算力", "算力基础设施"]),
            (["AI光纤", "AI算力光纤", "AI光通信"], ["AI光纤", "光通信"]),
            (["光纤", "光缆", "光纤光缆"], ["光纤光缆"]),
            (["光模块", "800G", "1.6T", "CPO", "硅光"], ["光模块", "800G光模块"]),
            (["算力租赁", "GPU出租"], ["算力租赁"]),
            (["游戏", "二次元", "动漫", "电竞"], ["游戏"]),
        ]
        for triggers, terms in kw_map:
            if any(t in text for t in triggers):
                intents.extend(terms)
        for pat in [r'(\d+G\s*(?:高速)?\s*光模块)', r'(\S*(?:光纤|光缆|光器件|光芯片))',
                    r'((?:AI|人工智能)\S{0,8}(?:算力|服务器))']:
            intents.extend(m.group(1) for m in re.finditer(pat, text))
        return {"search_intents": intents[:10], "summary": text[:60]}

    # ----------------------------------------------------------
    # Step 2: 主题匹配
    # ----------------------------------------------------------
    async def _match_themes(self, terms: List[str]) -> List[Dict]:
        conn = await self._get_conn()
        if not conn: return []
        try:
            conds, params = [], []
            for t in terms[:10]:
                # 1. 整词 ILIKE + 反向匹配
                conds.append(f"(concept ILIKE ${len(params)+1} OR search_text ILIKE ${len(params)+2})")
                params.extend([f"%{t}%", f"%{t}%"])
                conds.append(
                    f"(char_length(concept) >= 2 AND ${len(params)+1} ILIKE '%' || concept || '%')"
                )
                params.append(t)
                # 2. 手动分词：对长短语拆2-3字中文token（过滤短英文/数字）
                tokens = [tok for tok in re.findall(r'[\u4e00-\u9fff\w]{2,3}', t)
                          if len(tok) >= 3 or re.search(r'[\u4e00-\u9fff]', tok)]
                # 同时过滤过于通用的token
                STOP_TOKENS = {'日均','调用','用量','排行','第一','十大','唯一','市场','行业'}
                tokens = [tok for tok in tokens if tok not in STOP_TOKENS]
                if len(tokens) >= 2:
                    token_conds = []
                    for tok in tokens:
                        token_conds.append(f"concept ILIKE ${len(params)+1}")
                        params.append(f"%{tok}%")
                        token_conds.append(f"search_text ILIKE ${len(params)+1}")
                        params.append(f"%{tok}%")
                    conds.append(f"({' OR '.join(token_conds)})")

            where_clause = ' OR '.join(conds)
            try:
                rows = await conn.fetch(f"""
                    SELECT subject_key, concept, quality, semantic_type
                    FROM theme_gate_profile
                    WHERE char_length(coalesce(concept,'')) >= 1
                      AND ({where_clause})
                    ORDER BY CASE quality WHEN 'strong' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END
                    LIMIT 15
                """, *params)
            except Exception as e:
                logger.error(f"_match_themes SQL({len(params)}p): {e}")
                rows = []

            results = []
            for r in rows:
                concept = (r["concept"] or "").strip()
                if len(concept) < 2:
                    continue
                # 能通过ILIKE筛选至少得1分；精确命中额外加分
                score = 1
                for t in terms:
                    if t in concept:
                        score += 10
                    elif len(concept) >= 2 and concept in t:
                        score += 10
                results.append({"subject_key": r["subject_key"],
                                "concept": concept,
                                "quality": r.get("quality","weak"),
                                "match_score": score})
            results.sort(key=lambda x: x["match_score"], reverse=True)
            return results[:6]
        finally:
            await conn.close()

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

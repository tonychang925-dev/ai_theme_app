# ai_theme_app/stock_processing_service/domain/services/intel_event_extractor.py
"""
Phase 6A: 一手信息事件 LLM 结构化提取器

严格与新闻 parser 分开，不复用新闻结构化 prompt。

核心原则:
  - 公告 ≠ 新闻: 公告结构固定、法律语言、信息密度高、可精确抽取
  - 不直接输出 theme_candidates —— 只输出 entity/product/technology anchors
  - 题材匹配由 ThemeMatchEngine 基于 anchors 生成 recall query，不由 extractor 写死
  - 券商/研究机构/律所/会所 名称永不出现在 entity_anchors 中

Phase 6A 只实现 extract_announcement()。
extract_performance / extract_research / extract_survey 预留在后续 Phase。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 防污染：不得进入 entity_anchors 的机构类型关键词
# ---------------------------------------------------------------------------

_NO_THEME_ENTITY_PATTERNS: List[str] = [
    # 券商/投行
    "证券", "券商", "投行",
    # 研报发布机构
    "研究所", "研究院",
    # 法律服务
    "律师事务所", "律所",
    # 审计/会计
    "会计师事务所", "会所",
    # 交易所/监管
    "上交所", "深交所", "北交所", "证监会", "交易所",
    # 评级
    "评级机构",
]

# 具体券商/机构名称（公告中出现时只作为 source_org，不进入 anchor）
_NO_THEME_ENTITY_NAMES: set[str] = {
    "东方证券", "中信证券", "华泰证券", "国泰君安", "招商证券",
    "海通证券", "广发证券", "中金公司", "申万宏源", "银河证券",
    "国信证券", "兴业证券", "安信证券", "方正证券", "长江证券",
    "光大证券", "平安证券", "中泰证券", "国金证券", "东吴证券",
    "天风证券", "民生证券", "浙商证券", "华创证券", "国盛证券",
    "东北证券", "西南证券", "西部证券",
    "立信会计师事务所", "天健会计师事务所", "大华会计师事务所",
    "信永中和会计师事务所", "致同会计师事务所", "普华永道",
    "德勤", "安永", "毕马威",
    "金杜律师事务所", "中伦律师事务所", "君合律师事务所",
    "国浩律师事务所", "锦天城律师事务所",
}

# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

_ANNOUNCEMENT_SYSTEM_PROMPT = """\
你是一个A股上市公司公告结构化分析专家。你的任务是从公告标题中提取结构化信息。

重要规则:
1. 仅基于公告标题推断，不臆测内容
2. 如果信息不足以判断，降低 confidence，event_level 设为 "normal"
3. entity_anchors 中不得出现券商、律所、会所、交易所、评级机构名称
4. source_org（公告来源机构）与业务实体严格区分
5. 输出必须是合法 JSON，不要包含 markdown 代码块标记"""

_ANNOUNCEMENT_EXTRACT_PROMPT = """\
请分析以下A股上市公司公告，提取结构化信息。

股票代码: {stock_code}
股票名称: {stock_name}
公告标题: {title}
公告类型码: {announcement_type}

请严格按以下 JSON Schema 输出（不要输出其他内容）:

{{
  "event_type": "字符串，从以下类型中选择:
    major_contract       - 重大合同（签署/中标/获得订单）
    capex_expansion      - 投资扩产/产能建设/项目投资
    mna_restructuring    - 并购重组/资产收购出售
    shareholder_change   - 股权变动（增持/减持/转让/质押/解押）
    equity_financing     - 定增/配股/可转债/IPO相关
    share_repurchase     - 回购/股份注销
    dividend_plan        - 分红派息/权益分派
    regulatory_penalty   - 监管处罚/立案/问询/整改
    management_change    - 高管变更/董事会监事会换届
    guarantee_pledge     - 担保/质押/抵押
    lawsuit_arbitration  - 诉讼/仲裁
    goodwill_impairment  - 商誉减值/资产减值
    delisting_risk       - 退市风险/ST相关
    related_party_trade  - 关联交易
    patent_license       - 专利/知识产权/药品注册/认证
    corporate_governance - 公司治理/章程/制度
    periodic_report      - 定期报告/年报/季报/业绩预告/业绩快报
    other                - 其他公告",

  "event_level": "normal / important / critical。判断标准:
    - critical: 涉及退市风险、监管立案、实控人变更、大额减值、重大合同终止
    - important: 重大合同(金额大)、并购重组、大额增减持(>5%)、业绩预告大幅变动、高管重大变更
    - normal: 例行公告、程序性通知、一般性说明",

  "summary": "一句话摘要(30字以内)",

  "entity_anchors": ["业务相关实体名称列表。注意:
    - 仅包含: 公司客户、供应商、合作伙伴、收购标的、合资方
    - 绝对不包含: 券商、律所、会所、交易所、评级机构名称
    - 如果公告只涉及券商/律所等服务机构，entity_anchors 为空数组"],

  "product_anchors": ["涉及的产品/服务名称"],
  "technology_anchors": ["涉及的技术/工艺名称"],
  "business_actions": ["业务动作关键词: 如 产能扩张、新产线投产、中标、签署合同、获得认证"],
  "amount": "涉及金额及单位(如有)，如 10亿元、5000万元",
  "counterparty": "交易对手方/合作方(如有)",
  "impact_assessment": "对公司影响评估: 正面/负面/中性/不确定，一句话说明",
  "catalyst_tags": ["个股催化标签"],
  "risk_tags": ["风险标签，如 减持风险、退市风险、监管风险、商誉风险"],
  "confidence": 0.0-1.0,
  "evidence": ["公告标题关键表述原文片段"]
}}

注意:
- 如果公告标题模糊，无法判断具体类型，event_type 设为 "other"，confidence 控制在 0.5 以下
- entity_anchors 必须经过券商/律所/会所过滤，出现任何一个服务机构名称即为不合格
- 只输出 JSON，不要输出解释文字
"""

_FULL_TEXT_PROMPT = """\
请分析以下A股上市公司公告全文，提取结构化信息。

股票代码: {stock_code}
股票名称: {stock_name}
公告标题: {title}
公告类型码: {announcement_type}

公告正文:
{content_text}

请严格按以下 JSON Schema 输出（不要输出其他内容）:

{{
  "event_type": "字符串，从以下类型中选择:
    major_contract       - 重大合同（签署/中标/获得订单）
    capex_expansion      - 投资扩产/产能建设/项目投资
    mna_restructuring    - 并购重组/资产收购出售
    shareholder_change   - 股权变动（增持/减持/转让/质押/解押）
    equity_financing     - 定增/配股/可转债/IPO相关
    share_repurchase     - 回购/股份注销
    dividend_plan        - 分红派息/权益分派
    regulatory_penalty   - 监管处罚/立案/问询/整改
    management_change    - 高管变更/董事会监事会换届
    guarantee_pledge     - 担保/质押/抵押
    lawsuit_arbitration  - 诉讼/仲裁
    goodwill_impairment  - 商誉减值/资产减值
    delisting_risk       - 退市风险/ST相关
    related_party_trade  - 关联交易
    patent_license       - 专利/知识产权/药品注册/认证
    corporate_governance - 公司治理/章程/制度
    periodic_report      - 定期报告/年报/季报/业绩预告/业绩快报
    other                - 其他公告",

  "event_level": "normal / important / critical",

  "summary": "一句话摘要(30字以内)",

  "entity_anchors": ["业务相关实体名称。不含券商/律所/会所/评级机构"],
  "product_anchors": ["涉及的产品/服务名称"],
  "technology_anchors": ["涉及的技术/工艺名称"],
  "business_actions": ["业务动作关键词"],
  "amount": "涉及金额及单位(如有)",
  "counterparty": "交易对手方/合作方(如有)",
  "impact_assessment": "正面/负面/中性/不确定，一句话说明",
  "catalyst_tags": ["个股催化标签"],
  "risk_tags": ["风险标签"],
  "confidence": 0.0-1.0,
  "evidence": ["公告正文关键表述原文片段(至少2条)"]
}}

注意:
- 充分利用公告正文内容，提取具体金额、合同细节、业绩数据、风险提示
- 金额必须包含单位（如 8.5亿元、5000万元）
- evidence 必须从正文中摘录原文
- 只输出 JSON，不要输出解释文字
"""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class IntelEventExtractor:
    """一手信息事件 LLM 结构化提取器。

    Phase 6A 只实现 extract_announcement()。
    """

    def __init__(self, model_name: str = "deepseek-chat", timeout: int = 45) -> None:
        self._model_name = model_name
        self._timeout = timeout
        self._parser: Any = None

    # ------------------------------------------------------------------
    # Phase 6A: 公告提取
    # ------------------------------------------------------------------

    async def extract_announcement(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """对单条 raw_intel_document 公告进行结构化提取。

        Args:
            doc: raw_intel_document dict，至少包含 title, stock_code, stock_name,
                 announcement_type。

        Returns:
            structured_intel_event dict，可直接 insert_structured_intel_event()。
            如果 LLM 调用失败，返回 fallback 结构。
        """
        title = str(doc.get("title") or "").strip()
        stock_code = str(doc.get("stock_code") or "").strip()
        stock_name = str(doc.get("stock_name") or "").strip()
        ann_type = str(doc.get("announcement_type") or "").strip()
        content_text = str(doc.get("content_text") or "").strip()

        if not title:
            raise ValueError(
                f"extract_announcement: 标题为空，doc_id={doc.get('id')}"
            )

        # P1-D: full_text 模式 — content_text >= 300 字符时使用正文
        if content_text and len(content_text) >= 300:
            prompt = _FULL_TEXT_PROMPT.format(
                stock_code=stock_code,
                stock_name=stock_name,
                title=title,
                announcement_type=ann_type,
                content_text=content_text[:12000],
            )
            extraction_mode = "full_text"
            prompt_version = "phase6d_announcement_full_text.v1"
        else:
            prompt = _ANNOUNCEMENT_EXTRACT_PROMPT.format(
                stock_code=stock_code,
                stock_name=stock_name,
                title=title,
                announcement_type=ann_type,
            )
            extraction_mode = "title_only"
            prompt_version = "phase6a_announcement.v1"

        llm_output = await self._call_llm(prompt)
        if llm_output is None:
            raise RuntimeError(
                f"extract_announcement: LLM 返回空结果 "
                f"stock={stock_code} title={title[:60]}"
            )

        # 后处理: 过滤污染实体
        llm_output = self._sanitize_anchors(llm_output)

        return self._assemble_intel_event(doc, llm_output, extraction_mode, prompt_version)

    async def extract_announcement_batch(
        self,
        docs: List[Dict[str, Any]],
        *,
        stop_on_error: bool = True,
    ) -> List[Dict[str, Any]]:
        """批量提取公告。

        Args:
            docs: raw_intel_document dict list。
            stop_on_error: True 时第一条失败即抛出异常（默认）；
                           False 时记录错误并继续（谨慎使用）。

        Returns:
            list[structured_intel_event dict]，顺序与输入一致。
        """
        results: List[Dict[str, Any]] = []
        for i, doc in enumerate(docs):
            try:
                result = await self.extract_announcement(doc)
                results.append(result)
            except Exception:
                if stop_on_error:
                    raise
                logger.exception(
                    "extract_announcement_batch: 第 %s 条失败, stock=%s title=%s",
                    i,
                    doc.get("stock_code"),
                    str(doc.get("title", ""))[:60],
                )
        return results

    async def close(self) -> None:
        """关闭底层 LLM parser 连接。"""
        if self._parser is not None:
            try:
                await self._parser.close()
            except Exception:
                pass
            self._parser = None

    # ------------------------------------------------------------------
    # Phase 6D/E 预留接口
    # ------------------------------------------------------------------

    async def extract_performance(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """业绩预告/快报/财报结构化（Phase 6D 实现）。"""
        raise NotImplementedError("Phase 6D")

    async def extract_research(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """券商研报结构化（Phase 6E 实现）。"""
        raise NotImplementedError("Phase 6E")

    async def extract_survey(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """机构调研纪要结构化（Phase 6E 实现）。"""
        raise NotImplementedError("Phase 6E")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用 LLM 并返回解析后的 dict。"""
        parser = await self._get_parser()
        result = await parser.parse_content(prompt)
        return result

    async def _get_parser(self) -> Any:
        """懒加载 parser（避免初始化时即创建连接）。"""
        if self._parser is None:
            # 延迟导入，避免模块加载时触发 HTTP 连接
            from model_service.llm_parser.reliable_deepseek_parser import (
                ReliableDeepSeekParser,
            )
            self._parser = ReliableDeepSeekParser(
                model_name=self._model_name,
                config={
                    "max_retries": 3,
                    "timeout": self._timeout,
                    "enable_cache": True,
                    "cache_ttl": 300,
                    "failure_threshold": 5,
                    "recovery_timeout": 60,
                },
            )
        return self._parser

    @staticmethod
    def _sanitize_anchors(output: Dict[str, Any]) -> Dict[str, Any]:
        """后处理：过滤 entity_anchors 中的污染实体。

        券商、律所、会所、交易所、评级机构名称永不出现在 entity_anchors 中。
        """
        anchors: List[str] = output.get("entity_anchors") or []
        if not anchors:
            return output

        cleaned: List[str] = []
        for name in anchors:
            name_str = str(name).strip()
            if not name_str:
                continue
            # 精确匹配已知污染名单
            if name_str in _NO_THEME_ENTITY_NAMES:
                logger.info("sanitize: 移除已知污染实体 %s", name_str)
                continue
            # 模糊匹配污染模式
            is_polluted = False
            for pattern in _NO_THEME_ENTITY_PATTERNS:
                if pattern in name_str:
                    is_polluted = True
                    logger.info("sanitize: 移除含污染模式 %r 的实体 %s", pattern, name_str)
                    break
            if not is_polluted:
                cleaned.append(name_str)

        output["entity_anchors"] = cleaned
        return output

    def _assemble_intel_event(
        self,
        doc: Dict[str, Any],
        llm_output: Dict[str, Any],
        extraction_mode: str = "title_only",
        prompt_version: str = "phase6a_announcement.v1",
    ) -> Dict[str, Any]:
        """将原始文档 + LLM 输出组装为 structured_intel_event dict。

        映射关系:
          llm_output entities → structured_intel_event.entities (JSONB)
          llm_output catalyst_tags → structured_intel_event.catalyst_tags (TEXT[])
          llm_output risk_tags → structured_intel_event.risk_tags (TEXT[])
          llm_output amount/counterparty/impact_assessment → business_metrics (JSONB)
          llm_output evidence + extraction_mode → evidence_json (JSONB)
        """
        entities = {
            "entity_anchors": llm_output.get("entity_anchors") or [],
            "product_anchors": llm_output.get("product_anchors") or [],
            "technology_anchors": llm_output.get("technology_anchors") or [],
            "business_actions": llm_output.get("business_actions") or [],
        }

        business_metrics = {
            "amount": llm_output.get("amount", ""),
            "counterparty": llm_output.get("counterparty", ""),
            "impact_assessment": llm_output.get("impact_assessment", ""),
        }

        evidence_json = {
            "evidence": llm_output.get("evidence") or [],
            "extraction_mode": extraction_mode,
            "llm_prompt_version": prompt_version,
        }
        if extraction_mode == "full_text":
            ct = str(doc.get("content_text") or "")
            evidence_json["content_text_chars"] = len(ct)

        return {
            "raw_doc_id": int(doc["id"]),
            "event_type": str(llm_output.get("event_type") or "other"),
            "event_subtype": "",
            "event_level": str(llm_output.get("event_level") or "normal"),
            "stock_code": doc.get("stock_code"),
            "stock_name": doc.get("stock_name"),
            "subject_keys": [],  # 不直接输出题材，由 IntelStreamProducer 构建
            "title": doc.get("title"),
            "summary": str(llm_output.get("summary") or "")[:500],
            "event_date": None,
            "publish_time": doc.get("publish_time"),
            "entities": entities,
            "financial_metrics": {},
            "business_metrics": business_metrics,
            "catalyst_tags": llm_output.get("catalyst_tags") or [],
            "risk_tags": llm_output.get("risk_tags") or [],
            "confidence": float(llm_output.get("confidence", 0.5)),
            "impact_score": self._derive_impact_score(llm_output),
            "urgency_score": 0.0,
            "evidence_json": evidence_json,
            "llm_model": self._model_name,
            "stream_status": "pending",
        }

    @staticmethod
    def _derive_impact_score(llm_output: Dict[str, Any]) -> float:
        """根据 event_level 和 confidence 估算 impact_score (0-100)。"""
        level = str(llm_output.get("event_level") or "normal")
        confidence = float(llm_output.get("confidence", 0.5))

        base = {"critical": 90.0, "important": 65.0, "normal": 30.0}.get(level, 30.0)
        # confidence 调整: ±15
        adjusted = base + (confidence - 0.5) * 30.0
        return max(0.0, min(100.0, round(adjusted, 1)))

    # _fallback_result 已移除：LLM 失败必须直接报错，不允许静默降级

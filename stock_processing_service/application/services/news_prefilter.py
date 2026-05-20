"""P1-A: AkShare 新闻预过滤适配层。

包装 LocalQwenNewsTriageService，提供与 AkShareRealtimeNewsCollector 兼容的接口。
第一版默认 rule-only，prompt 模式预留后续灰度。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from database_service.streams.services.local_qwen_triage_service import (
        LocalQwenNewsTriageService,
    )
    HAS_LOCAL_TRIAGE = True
except ImportError:
    LocalQwenNewsTriageService = None  # type: ignore
    HAS_LOCAL_TRIAGE = False


@dataclass
class NewsTriageResult:
    pass_: bool
    decision: str       # PASS | SKIP | REVIEW
    reason: str
    mode: str           # rule | prompt | embedding
    score: float | None


class NewsPreFilterAdapter:
    """预过滤适配层 — 规则优先，模型可选，fail-open。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        mode: str = "rule",          # rule | prompt | embedding | off
        model_path: str = "",
        min_importance: int = 40,
        timeout_seconds: float = 2.0,
        fail_open: bool = True,
    ):
        self.enabled = enabled
        self.mode = mode if enabled else "off"
        self.min_importance = min_importance
        self.timeout_seconds = timeout_seconds
        self.fail_open = fail_open

        self._triage: Optional[LocalQwenNewsTriageService] = None
        self._use_prompt = (self.mode in {"prompt", "hybrid"})

        if self.mode == "off":
            return

        # rule-only 模式不需要初始化 LocalQwenNewsTriageService
        if not self._use_prompt:
            logger.info("NewsPreFilter initialized: mode=rule (embedded rules only)")
            return

        if not HAS_LOCAL_TRIAGE:
            logger.warning(
                "NewsPreFilter: LocalQwenNewsTriageService 不可用，"
                "降级为 rule-only（内嵌规则）"
            )
            self.mode = "rule"
            self._use_prompt = False
            return

        triage_cfg: Dict[str, Any] = {
            "enable_local_triage": True,
            "triage_mode": "prompt",
            "local_qwen_model_path": model_path,
        }
        self._triage = LocalQwenNewsTriageService(triage_cfg)
        logger.info(
            "NewsPreFilter initialized: mode=prompt model=%s",
            model_path or "auto-detect",
        )

    def evaluate(self, payload: Dict[str, Any]) -> NewsTriageResult:
        """评估单条新闻是否应通过预过滤。

        rule-only 模式：只用内嵌保守规则（不调用 LocalQwenNewsTriageService 的严格规则）。
        prompt 模式：走 LocalQwenNewsTriageService 的 prompt 判定。
        fail-open：异常时一律 PASS。
        """
        if not self.enabled or self.mode == "off":
            return NewsTriageResult(
                pass_=True, decision="PASS",
                reason="prefilter_disabled", mode="off", score=None,
            )

        try:
            # rule-only: 优先用内嵌保守规则（避免 LocalQwenNewsTriageService 严格规则误杀）
            if self.mode == "rule":
                raw = _embedded_rule_evaluate(payload)
            elif self._triage is not None and self._use_prompt:
                # prompt 模式：走 LocalQwenNewsTriageService.evaluate（含 prompt+rule fallback）
                raw = self._triage.evaluate(_payload_to_triage(payload))
            else:
                # fallback: 内嵌规则
                raw = _embedded_rule_evaluate(payload)

            decision = str(raw.get("decision") or "PASS").upper()
            # REVIEW 也放行（保守），只有 SKIP 才拦截
            return NewsTriageResult(
                pass_=decision in {"PASS", "REVIEW"},
                decision=decision,
                reason=str(raw.get("reason", "")),
                mode=str(raw.get("mode", "rule")),
                score=raw.get("score"),
            )
        except Exception as exc:
            logger.warning("NewsPreFilter evaluate exception: %s", exc)
            if self.fail_open:
                return NewsTriageResult(
                    pass_=True, decision="PASS",
                    reason=f"filter_exception_fail_open:{exc}",
                    mode="error", score=None,
                )
            return NewsTriageResult(
                pass_=False, decision="SKIP",
                reason=f"filter_exception:{exc}",
                mode="error", score=None,
            )

    def to_payload_fields(self, result: NewsTriageResult) -> Dict[str, str]:
        """将预过滤结果转换为可写入 stream payload 的字段。"""
        return {
            "prefilter_pass": "true" if result.pass_ else "false",
            "prefilter_mode": result.mode,
            "prefilter_decision": result.decision,
            "prefilter_reason": result.reason[:120] if result.reason else "",
        }


def _payload_to_triage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """将 collector 标准化 payload 转换为 triage 接口格式。"""
    return {
        "news_id": str(payload.get("news_id", "")),
        "title": str(payload.get("title", "")),
        "content": str(payload.get("content", "")),
        "source": str(payload.get("source", "")),
    }


# ── 内嵌规则（LocalQwenNewsTriageService 不可用时的最小 fallback）──────

_EMBEDDED_CATALYST_KEYWORDS = {
    "政策", "业绩", "预增", "预亏", "并购", "重组", "收购", "订单", "中标",
    "回购", "减持", "停牌", "复牌", "监管", "降息", "加息",
    "关税", "出口", "制裁", "突破", "新品", "扩产", "事故", "诉讼",
    "公告", "净利润", "营收", "增持", "分红", "问询函", "产能",
    "投产", "处罚", "获批", "补贴", "财政",
    "算力", "合同", "签约", "投资", "研发",
}

_EMBEDDED_TRIVIAL_PATTERNS = {
    "该股今日上涨", "该股今日下跌", "股价回调", "股价震荡",
    "市场分析认为与政策面变化有关", "机构分析认为与资金流向有关",
    "但后市可期", "股价今日上涨",
}

_EMBEDDED_SIGNAL_KEYWORDS = {
    "涨停", "跌停", "题材", "板块", "主力", "资金",
    "龙虎榜", "北向", "公告", "回购", "减持",
}


def _embedded_rule_evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """内嵌规则评估（最小实现，不依赖外部类）。

    规则顺序：硬过滤 → 硬模板 → 催化剂 → 股票代码 → 信号词 → 保守放行。
    """
    title = str(payload.get("title", ""))
    content = str(payload.get("content", ""))
    text = f"{title}\n{content}"

    # 1. 硬过滤：过短文本
    if len(text.strip()) < 15:
        return {"decision": "SKIP", "reason": "rule:too_short", "score": None, "mode": "embedded_rule"}

    # 2. 硬模板过滤：纯价格波动 + 通用分析语
    #    模板命中时需 >= 2 个催化词才能放行，避免"政策面变化"等弱词误触发
    for pattern in _EMBEDDED_TRIVIAL_PATTERNS:
        if pattern in text:
            catalyst_count = sum(1 for k in _EMBEDDED_CATALYST_KEYWORDS if k in text)
            import re
            has_stock = bool(re.search(r"[036]\d{5}", text))
            if catalyst_count < 2 and not has_stock:
                return {"decision": "SKIP", "reason": f"rule:trivial_price_move:{pattern[:15]}", "score": None, "mode": "embedded_rule"}

    # 3. 明确催化 → PASS
    catalyst_hits = sum(1 for k in _EMBEDDED_CATALYST_KEYWORDS if k in text)
    if catalyst_hits >= 1:
        return {"decision": "PASS", "reason": f"rule:catalyst_hits={catalyst_hits}", "score": None, "mode": "embedded_rule"}

    # 4. 股票代码 → PASS（个股相关）
    import re
    if re.search(r"[036]\d{5}", text):
        return {"decision": "PASS", "reason": "rule:stock_code_hit", "score": None, "mode": "embedded_rule"}

    # 5. 题材信号 ≥ 2 → PASS
    signal_hits = sum(1 for k in _EMBEDDED_SIGNAL_KEYWORDS if k in text)
    if signal_hits >= 2:
        return {"decision": "PASS", "reason": f"rule:signal_hits={signal_hits}", "score": None, "mode": "embedded_rule"}

    # 6. 保守放行
    return {"decision": "PASS", "reason": "rule:conservative_pass", "score": None, "mode": "embedded_rule"}

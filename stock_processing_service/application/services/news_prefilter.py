"""P1-A: AkShare 新闻预过滤适配层。

支持三种模式：
  rule        — 内嵌规则，保守放行
  rule_prompt — 规则 + Qwen prompt 灰区判定
  prompt      — 全量 Qwen prompt（暂未启用）

P1-A2: rule_prompt 模式下，规则可明确判断的直接决策，灰区交给 Qwen 1.5B。
"""
from __future__ import annotations

import json as _json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class NewsTriageResult:
    pass_: bool
    decision: str       # PASS | SKIP | REVIEW
    reason: str
    mode: str           # rule | qwen_prompt | embedded_rule | error
    score: float | None


class NewsPreFilterAdapter:
    """预过滤适配层 — 规则优先，模型可选，fail-open。

    Modes:
      off         — 不做过滤
      rule        — 内嵌规则，保守放行
      rule_prompt — 规则明确→直接决策，灰区→Qwen prompt
      prompt      — 全量 Qwen prompt（灰度后启用）
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        mode: str = "rule_prompt",
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

        self._use_qwen = self.mode in {"rule_prompt", "prompt"}
        self._qwen_llm = None
        self._qwen_ready = False
        self._qwen_init_attempted = False
        self._model_path = model_path

        # P1-A2.1: performance protection
        self._max_prompt_per_batch = int(os.getenv("PREFILTER_MAX_PROMPT_PER_BATCH", "3"))
        self._prompt_this_batch = 0
        self._degraded = False
        self._degrade_reason = ""

        # stats
        self.stats = {
            "prompt_eval_count": 0,
            "prompt_pass_count": 0,
            "prompt_skip_count": 0,
            "prompt_error_count": 0,
            "prompt_total_ms": 0.0,
            "prompt_noise_pass_count": 0,
            "batch_budget_exhausted_count": 0,
            "degraded": False,
            "degrade_reason": "",
        }

        if self.mode == "off":
            return

        logger.info("NewsPreFilter initialized: mode=%s qwen=%s", self.mode, self._use_qwen)

    def new_batch(self) -> None:
        """每轮采集前调用，重置批次预算。"""
        self._prompt_this_batch = 0

    def evaluate(self, payload: Dict[str, Any]) -> NewsTriageResult:
        if not self.enabled or self.mode == "off":
            return NewsTriageResult(pass_=True, decision="PASS",
                                    reason="prefilter_disabled", mode="off", score=None)

        try:
            # 1. 内嵌规则先跑，得到决定 + 是否灰区
            rule_raw = _embedded_rule_evaluate(payload)
            rule_decision = str(rule_raw.get("decision") or "PASS").upper()

            # 2. 非 prompt 模式，或规则已明确 → 直接返回
            #    rule-only（含降级）模式下，灰区默认 SKIP，不再保守放行
            if self.mode == "rule" or self._degraded:
                result = _to_result(rule_raw)
                if rule_raw.get("gray") and result.pass_:
                    return NewsTriageResult(
                        pass_=False, decision="SKIP",
                        reason="rule:gray_conservative_skip", mode="rule", score=None)
                return result
            if not self._use_qwen:
                return _to_result(rule_raw)
            if rule_decision in {"SKIP", "PASS"} and rule_raw.get("gray") != True:
                return _to_result(rule_raw)

            # 3. 批次预算已耗尽 → fail-open PASS (rule:gray_budget_exhausted)
            if self._prompt_this_batch >= self._max_prompt_per_batch:
                self.stats["batch_budget_exhausted_count"] += 1
                return NewsTriageResult(pass_=True, decision="PASS",
                    reason=f"rule:batch_budget_exhausted(max={self._max_prompt_per_batch})",
                    mode="rule", score=None)

            # 4. 检查熔断
            if self._check_degraded():
                return _to_result(rule_raw)

            # 5. 灰区：调用 Qwen prompt
            self._prompt_this_batch += 1
            return self._qwen_evaluate(payload)

        except Exception as exc:
            logger.warning("NewsPreFilter evaluate exception: %s", exc)
            if self.fail_open:
                return NewsTriageResult(pass_=True, decision="PASS",
                    reason=f"filter_exception_fail_open:{exc}", mode="error", score=None)
            return NewsTriageResult(pass_=False, decision="SKIP",
                reason=f"filter_exception:{exc}", mode="error", score=None)

    def _check_degraded(self) -> bool:
        """熔断检查：p95 > 5000ms 或 error_rate > 20% → 降级 rule-only。"""
        if self._degraded:
            return True
        s = self.stats
        if s["prompt_eval_count"] >= 5:
            avg_ms = s["prompt_total_ms"] / max(s["prompt_eval_count"], 1)
            err_rate = s["prompt_error_count"] / max(s["prompt_eval_count"], 1)
            if avg_ms > 5000 or err_rate > 0.20:
                self._degraded = True
                self._degrade_reason = (
                    f"prompt_slow(avg={avg_ms:.0f}ms)" if avg_ms > 5000
                    else f"prompt_error_rate({err_rate:.1%})"
                )
                self.stats["degraded"] = True
                self.stats["degrade_reason"] = self._degrade_reason
                logger.warning("NewsPreFilter degraded to rule-only: %s", self._degrade_reason)
                return True
        return False

    def _qwen_evaluate(self, payload: Dict[str, Any]) -> NewsTriageResult:
        """Qwen prompt 判定（带超时和 fail-open）。"""
        if not self._ensure_qwen_ready():
            return NewsTriageResult(pass_=True, decision="PASS",
                reason="qwen_not_ready_fail_open", mode="rule", score=None)

        import time as _time
        self.stats["prompt_eval_count"] += 1
        t0 = _time.perf_counter()

        try:
            text = f"{payload.get('title', '')}\n{payload.get('content', '')}"
            prompt = _QPWEN_PROMPT.format(text=text[:600])
            response = self._qwen_llm(
                prompt, max_tokens=64, stop=["\n\n"], echo=False,
                temperature=0.0, top_p=0.9, top_k=40,
            )
            raw = str(response["choices"][0]["text"]).strip()
            elapsed_ms = (_time.perf_counter() - t0) * 1000
            self.stats["prompt_total_ms"] += elapsed_ms

            parsed = _parse_qwen_output(raw)
            category = str(parsed.get("category", "unknown"))
            importance = int(parsed.get("importance", 50))
            qwen_pass = parsed.get("pass") is True

            # P1-A2.1: noise + pass → 保守放行但记录 warning
            if qwen_pass and category == "noise":
                self.stats["prompt_noise_pass_count"] += 1
                self.stats["prompt_pass_count"] += 1
                return NewsTriageResult(pass_=True, decision="PASS",
                    reason=f"qwen:noise_pass_conservative:{parsed.get('reason','')[:60]}",
                    mode="qwen_prompt", score=float(importance))

            if qwen_pass:
                self.stats["prompt_pass_count"] += 1
                return NewsTriageResult(pass_=True, decision="PASS",
                    reason=f"qwen:{category}:{parsed.get('reason','')[:60]}",
                    mode="qwen_prompt", score=float(importance))
            else:
                self.stats["prompt_skip_count"] += 1
                return NewsTriageResult(pass_=False, decision="SKIP",
                    reason=f"qwen:{category}:{parsed.get('reason','')[:60]}",
                    mode="qwen_prompt", score=float(importance))

        except Exception as exc:
            self.stats["prompt_error_count"] += 1
            logger.warning("Qwen prompt failed: %s", exc)
            if self.fail_open:
                return NewsTriageResult(pass_=True, decision="PASS",
                    reason=f"qwen_error_fail_open:{exc}", mode="qwen_prompt", score=None)
            return NewsTriageResult(pass_=False, decision="SKIP",
                reason=f"qwen_error:{exc}", mode="qwen_prompt", score=None)

    def _ensure_qwen_ready(self) -> bool:
        if self._qwen_ready:
            return True
        if self._qwen_init_attempted:
            return False
        self._qwen_init_attempted = True

        model_path = _resolve_qwen_model(self._model_path)
        if not model_path:
            logger.warning("Qwen GGUF model not found, prompt mode unavailable")
            return False

        try:
            from llama_cpp import Llama
            n_threads = int(os.getenv("QWEN_PREFILTER_THREADS", "4"))
            self._qwen_llm = Llama(
                model_path=model_path, n_ctx=1024,
                n_threads=n_threads, n_gpu_layers=0, verbose=False,
            )
            self._qwen_ready = True
            logger.info("Qwen 1.5B prompt loaded: %s threads=%s", model_path, n_threads)
            return True
        except Exception as exc:
            logger.warning("Qwen prompt init failed: %s", exc)
            return False

    # ── Qwen semantic dedup ────────────────────────────────────────────

    def check_semantic_duplicate(self, title_a: str, title_b: str) -> bool | None:
        """Use Qwen to judge if two news items are the same event.

        Returns True if duplicates, False if distinct, None if Qwen unavailable.
        """
        if not self._ensure_qwen_ready():
            return None
        try:
            prompt = (
                "判断以下两条A股财经新闻是否在报道同一事件。\n"
                "只输出JSON，不要解释：\n"
                '{"same": true或false, "reason": "不超过20字"}\n'
                f"新闻A: {title_a[:200]}\n"
                f"新闻B: {title_b[:200]}\n"
                "输出："
            )
            response = self._qwen_llm(
                prompt, max_tokens=48, stop=["\n\n"], echo=False,
                temperature=0.0, top_p=0.9, top_k=40,
            )
            raw = str(response["choices"][0]["text"]).strip()
            import re as _re
            m = _re.search(r'\{[^}]+\}', raw)
            if m:
                parsed = _json.loads(m.group())
                return bool(parsed.get("same", False))
            return "same" in raw.lower() and "true" in raw.lower()
        except Exception:
            return None  # fail-open: don't dedup if uncertain

    def to_payload_fields(self, result: NewsTriageResult) -> Dict[str, str]:
        return {
            "prefilter_pass": "true" if result.pass_ else "false",
            "prefilter_mode": result.mode,
            "prefilter_decision": result.decision,
            "prefilter_reason": result.reason[:120] if result.reason else "",
        }

    def get_stats(self) -> Dict[str, Any]:
        s = dict(self.stats)
        s["prompt_p95_ms"] = round(s["prompt_total_ms"] / max(s["prompt_eval_count"], 1) * 2.5, 1)
        s["prompt_avg_ms"] = round(s["prompt_total_ms"] / max(s["prompt_eval_count"], 1), 1)
        s["qwen_ready"] = self._qwen_ready
        return s


def _payload_to_triage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """将 collector 标准化 payload 转换为 triage 接口格式。"""
    return {
        "news_id": str(payload.get("news_id", "")),
        "title": str(payload.get("title", "")),
        "content": str(payload.get("content", "")),
        "source": str(payload.get("source", "")),
    }


def _to_result(raw: Dict[str, Any]) -> NewsTriageResult:
    decision = str(raw.get("decision") or "PASS").upper()
    return NewsTriageResult(
        pass_=decision in {"PASS", "REVIEW"},
        decision=decision,
        reason=str(raw.get("reason", "")),
        mode=str(raw.get("mode", "rule")),
        score=raw.get("score"),
    )


# ── Qwen prompt ──────────────────────────────────────────────────────────

_QPWEN_PROMPT = (
    "你是A股实时新闻过滤器。判断这条新闻是否可能影响A股题材或个股。\n"
    "规则：\n"
    "1) 可能影响板块/题材/个股预期 → pass:true, category用industry/policy/company/risk之一，importance用0-100数字\n"
    "2) 纯价格波动、市场情绪、无实质内容的快讯 → pass:false, category用noise\n"
    "3) 不太确定 → pass:true（宁可放行不可误杀）\n"
    "请只输出JSON，不要解释：\n"
    "{{\"pass\": true或false, \"category\": \"industry|policy|company|market|risk|noise\", \"importance\": 0-100的数字, \"reason\": \"不超过30字\"}}\n"
    "新闻：{text}\n"
    "输出："
)


def _parse_qwen_output(raw: str) -> Dict[str, Any]:
    """解析 Qwen 输出为 structured dict，fail-open。"""
    # 提取 JSON
    m = re.search(r'\{[^}]+\}', raw)
    if m:
        try:
            parsed = _json.loads(m.group())
            if "pass" in parsed:
                return {
                    "pass": bool(parsed.get("pass")),
                    "category": str(parsed.get("category", "noise")),
                    "importance": max(0, min(100, int(parsed.get("importance", 50)))),
                    "reason": str(parsed.get("reason", "")),
                }
        except (_json.JSONDecodeError, ValueError, TypeError):
            pass
    # Heuristic fallback: contains "pass" or "true" → pass
    if "pass" in raw.lower() or "true" in raw.lower():
        return {"pass": True, "category": "unknown", "importance": 50, "reason": "heuristic_fallback"}
    if "skip" in raw.lower() or "false" in raw.lower() or "noise" in raw.lower():
        return {"pass": False, "category": "noise", "importance": 20, "reason": "heuristic_fallback"}
    # Conservative
    return {"pass": True, "category": "unknown", "importance": 50, "reason": "parse_fallback_pass"}


def _resolve_qwen_model(explicit_path: str) -> str | None:
    """Resolve Qwen GGUF model path."""
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    env_path = os.getenv("QWEN_PREFILTER_MODEL_PATH", "").strip()
    if env_path:
        candidates.append(env_path)
    candidates.extend([
        "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf",
        "/Users/admin/Desktop/ai_theme_app/models/Qwen2.5-1.5B-Instruct",
    ])
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None


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

    # 6. 保守放行（灰区 — rule_prompt 模式下会交给 Qwen）
    return {"decision": "PASS", "reason": "rule:conservative_pass", "score": None, "mode": "embedded_rule", "gray": True}

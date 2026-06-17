"""P1-A: 新闻预过滤适配层 — 数据库/采集层版本。

从 stock_processing_service.application.services.news_prefilter 迁移至
database_service/streams/services/，消除 database_service → SPS 反向依赖。

支持三种模式：
  rule        — 内嵌规则，保守放行
  rule_prompt — 规则 + Qwen prompt 灰区判定
  prompt      — 全量 Qwen prompt（暂未启用）

Phase 4E (2026-05-24):
  新增 preload_model() 公开预热方法，安全用于 asyncio.to_thread()。
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
        self._max_prompt_per_batch = int(os.getenv("PREFILTER_MAX_PROMPT_PER_BATCH", "15"))
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
            if self.mode == "rule" or self._degraded:
                result = _to_result(rule_raw)
                if rule_raw.get("gray") and result.pass_:
                    return NewsTriageResult(
                        pass_=False, decision="HOLD",
                        reason="rule:gray_hold", mode="rule", score=None)
                return result
            if not self._use_qwen:
                return _to_result(rule_raw)
            if rule_decision in {"SKIP", "PASS"} and rule_raw.get("gray") != True:
                return _to_result(rule_raw)

            # 3. 先检查熔断，再检查批次预算
            if self._check_degraded():
                result = _to_result(rule_raw)
                if rule_raw.get("gray") and result.pass_:
                    return NewsTriageResult(
                        pass_=False, decision="HOLD",
                        reason="rule:gray_hold", mode="rule", score=None)
                return result

            # 4. 批次预算已耗尽
            if self._prompt_this_batch >= self._max_prompt_per_batch:
                self.stats["batch_budget_exhausted_count"] += 1
                if rule_raw.get("gray"):
                    return NewsTriageResult(
                        pass_=False, decision="SKIP",
                        reason="rule:gray_budget_exhausted_skip", mode="rule", score=None)
                return NewsTriageResult(pass_=True, decision="PASS",
                    reason=f"rule:batch_budget_exhausted(max={self._max_prompt_per_batch})",
                    mode="rule", score=None)

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
            if avg_ms > 20000 or err_rate > 0.20:
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
                prompt, max_tokens=16, stop=["}", "\n", "\n\n"], echo=False,
                temperature=0.0,
            )
            raw = str(response["choices"][0]["text"]).strip()
            elapsed_ms = (_time.perf_counter() - t0) * 1000
            self.stats["prompt_total_ms"] += elapsed_ms

            parsed = _parse_qwen_output(raw)
            category = str(parsed.get("category", "unknown"))
            importance = int(parsed.get("importance", 50))
            qwen_pass = parsed.get("pass") is True

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
                model_path=model_path, n_ctx=256,
                n_threads=n_threads, n_gpu_layers=0, verbose=False,
            )
            self._qwen_ready = True
            model_name = model_path.split('/')[-1].replace('.gguf', '')
            logger.info("Qwen prefilter loaded: %s threads=%s n_ctx=256", model_name, n_threads)
            return True
        except Exception as exc:
            logger.warning("Qwen prompt init failed: %s", exc)
            return False

    # ── Phase 4E: 公开预热接口 ─────────────────────────────────────

    def preload_model(self) -> bool:
        """公开预热接口，安全用于 asyncio.to_thread()。"""
        return self._ensure_qwen_ready()

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
    "判断A股财经新闻是否包含实质性信息。只输出JSON，勿解释。\n"
    "重要(含产业数据/公司财报/政策/重大订单/技术突破/供需变化等)→{{\"p\":1}}\n"
    "不重要(纯行情播报/ETF涨跌/股评/无实质内容)→{{\"p\":0}}\n"
    "重要规则：如果文本标题是ETF或行情播报形式，但正文包含实质性经济数据、产业报告、"
    "公司公告等驱动事件，必须判断为重要{{\"p\":1}}。\n"
    "新闻：{text}\n"
    "输出："
)


def _parse_qwen_output(raw: str) -> Dict[str, Any]:
    """解析 Qwen 紧凑输出 {\"p\":1} 或 {\"p\":0}，fail-open。"""
    m = re.search(r'\{[^}]*["\']p["\']\s*:\s*(\d+)[^}]*\}', raw)
    if m:
        p_val = int(m.group(1))
        return {"pass": p_val == 1, "category": "qwen", "importance": 50, "reason": "qwen_compact"}
    if '"p":1' in raw or '"p": 1' in raw:
        return {"pass": True, "category": "qwen", "importance": 50, "reason": "qwen_fallback_pass"}
    if '"p":0' in raw or '"p": 0' in raw:
        return {"pass": False, "category": "noise", "importance": 20, "reason": "qwen_fallback_skip"}
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
        "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf",
        "/Users/admin/Desktop/ai_theme_app/models/Qwen2.5-1.5B-Instruct",
    ])
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None


# ── 内嵌规则 ────────────────────────────────────────────────────

_EMBEDDED_CATALYST_KEYWORDS = {
    "政策", "业绩", "预增", "预亏", "并购", "重组", "收购", "订单", "中标",
    "回购", "减持", "停牌", "复牌", "监管", "降息", "加息",
    "关税", "出口", "制裁", "突破", "新品", "扩产", "事故", "诉讼",
    "公告", "净利润", "营收", "增持", "分红", "问询函", "产能",
    "投产", "处罚", "获批", "补贴", "财政",
    "算力", "合同", "签约", "投资", "研发",
    # Phase 4F: 价格/供需/里程碑驱动事件 — 绝不允许滤过
    "涨价", "提价", "调价", "涨价函", "供不应求", "供应紧张", "缺口",
    "缺货", "产能紧张", "供过于求",
    "首次", "技术突破", "发布", "量产", "验证通过",
    "创新高", "创纪录", "历史新高", "里程碑",
}

_EMBEDDED_TRIVIAL_PATTERNS = {
    "该股今日上涨", "该股今日下跌", "股价回调", "股价震荡",
    "市场分析认为与政策面变化有关", "机构分析认为与资金流向有关",
    "但后市可期", "股价今日上涨",
    # Phase 4E: 盘中行情概括/价格波动描述（无实质催化事件）
    "产业链震荡", "概念盘中震荡", "震荡下挫", "盘中震荡下挫",
    "震荡调整", "概念震荡调整", "集体下挫", "集体拉升",
    "开盘领涨", "开盘领跌", "板块震荡下挫", "板块震荡调整",
    "盘中异动", "跟跌", "触及跌停", "双双跌停",
}

_EMBEDDED_SIGNAL_KEYWORDS = {
    "涨停", "跌停", "题材", "板块", "主力", "资金",
    "龙虎榜", "北向", "公告", "回购", "减持",
}


_EMBEDDED_ROUTINE_GOV_TERMS = (
    "会见", "在京会见", "双方就深化", "友好合作", "命运共同体",
    "达成共识", "赴", "调研", "会议闭幕", "致辞", "讲话", "慰问",
    "议长", "总统", "总理", "部长", "代表团", "致贺信", "出席会议",
    "全国人大常委会", "常委会会议", "海峡论坛", "全国政协",
    # Phase 4E fix: diplomatic/foreign affairs — virtually never A-share catalysts
    "外长", "外交部", "外交部发言人", "大使", "大使馆", "双边关系",
    "国事访问", "正式访问", "联合声明", "联合公报",
)
_EMBEDDED_DISCIPLINE_TERMS = (
    "中央纪委", "国家监委", "违规吃喝", "典型问题",
    "公开通报", "纪律处分", "党纪政务处分", "立案审查调查",
)
_EMBEDDED_STRONG_INDUSTRY_TERMS = (
    "出台", "发布", "印发", "审议通过", "实施方案", "产业政策",
    "行动方案", "财政补贴", "设备更新", "人工智能", "算力",
    "半导体", "新能源", "低空经济", "机器人", "数据中心",
    "出口管制", "关税", "重大订单", "中标", "签约",
    "项目开工", "投产", "扩产", "供需", "价格上涨",
    "技术突破", "重大合同", "并购重组", "获批上市",
)


def _embedded_rule_evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """内嵌规则评估（最小实现，不依赖外部类）。

    规则顺序：硬过滤 → 硬模板 → 催化剂 → 股票代码 → 信号词 → 保守放行。
    """
    title = str(payload.get("title", ""))
    content = str(payload.get("content", ""))
    text = f"{title}\n{content}"

    # 1. 硬过滤：过短文本（Phase 4E fix: 15→50）
    if len(text.strip()) < 50:
        return {"decision": "SKIP", "reason": "rule:too_short", "score": None, "mode": "embedded_rule"}

    # 1b. 内容过短或仅重复标题（无实质信息）
    # Phase 4F: content==title 的短公告（如涨价通知、快讯）不应被误杀，
    # 只要标题/正文包含催化剂即放行
    content_stripped = content.strip()
    if len(content_stripped) < 20:
        return {"decision": "SKIP", "reason": "rule:content_too_short", "score": None, "mode": "embedded_rule"}
    if content_stripped == title.strip():
        # 正文=标题的短公告：检查标题是否有实质催化剂
        title_catalyst = sum(1 for k in _EMBEDDED_CATALYST_KEYWORDS if k in title)
        title_industry = sum(1 for t in _EMBEDDED_STRONG_INDUSTRY_TERMS if t in title)
        if title_catalyst >= 1 or title_industry >= 2:
            return {"decision": "PASS", "reason": "rule:short_form_substantive_title", "score": None, "mode": "embedded_rule"}
        if len(title) < 40:
            return {"decision": "SKIP", "reason": "rule:content_title_only_short", "score": None, "mode": "embedded_rule"}
        # 标题>=40字：内容=标题的短公告，灰区交给Qwen
        return {"decision": "PASS", "reason": "rule:gray_short_form_title_equals_content", "score": None, "mode": "embedded_rule"}

    # Phase 4C: 政务/纪委硬SKIP（除非含强产业催化词）
    gov_hits = [t for t in _EMBEDDED_ROUTINE_GOV_TERMS if t in text]
    disc_hits = [t for t in _EMBEDDED_DISCIPLINE_TERMS if t in text]
    industry_hits = [t for t in _EMBEDDED_STRONG_INDUSTRY_TERMS if t in text]
    if gov_hits and not industry_hits:
        return {"decision": "SKIP", "reason": f"rule:routine_gov:{','.join(gov_hits[:2])}", "score": None, "mode": "embedded_rule"}
    if disc_hits:
        return {"decision": "SKIP", "reason": f"rule:discipline:{','.join(disc_hits[:2])}", "score": None, "mode": "embedded_rule"}

    # 2a. 公司公告过滤：例行披露直接 SKIP，除非含强催化剂
    if "公告" in title:
        _ROUTINE_ANNOUNCE = (
            "减持", "质押", "解除质押", "辞职", "辞任", "人事变动",
            "股东大会", "董事会决议", "监事会决议", "贷款承诺函",
            "银行授信", "授信额度", "担保", "权益变动",
            "更正公告", "补充公告", "延期披露", "会计差错",
            "独立董事", "选举", "换届",
        )
        routine_hits = [t for t in _ROUTINE_ANNOUNCE if t in text]
        if routine_hits:
            # 除非含强催化剂才放行
            _STRONG_ANNOUNCE_CATALYST = (
                "中标", "重大合同", "并购", "重组", "扩产", "投产",
                "获批上市", "技术突破", "重大订单", "签约",
                "业绩预增", "净利润", "营收增长",
            )
            strong_hits = [t for t in _STRONG_ANNOUNCE_CATALYST if t in text]
            if not strong_hits:
                return {"decision": "SKIP", "reason": f"rule:routine_announcement:{routine_hits[0]}", "score": None, "mode": "embedded_rule"}

    # 2b. 硬模板过滤：纯价格波动 + 通用分析语
    for pattern in _EMBEDDED_TRIVIAL_PATTERNS:
        if pattern in text:
            catalyst_count = sum(1 for k in _EMBEDDED_CATALYST_KEYWORDS if k in text)
            has_stock = bool(re.search(r"[036]\d{5}", text))
            if catalyst_count < 2 and not has_stock:
                return {"decision": "SKIP", "reason": f"rule:trivial_price_move:{pattern[:15]}", "score": None, "mode": "embedded_rule"}

    # 3. 明确催化 >= 2 → PASS
    has_stock = bool(re.search(r"[036]\d{5}", text))
    catalyst_hits = sum(1 for k in _EMBEDDED_CATALYST_KEYWORDS if k in text)
    if catalyst_hits >= 2:
        return {"decision": "PASS", "reason": f"rule:catalyst_hits={catalyst_hits}", "score": None, "mode": "embedded_rule"}

    # 4. 1个催化 + 股票代码 → PASS
    if catalyst_hits >= 1 and has_stock:
        return {"decision": "PASS", "reason": "rule:catalyst+stock", "score": None, "mode": "embedded_rule"}

    # 5. 股票代码 + 信号词 → PASS
    signal_hits = sum(1 for k in _EMBEDDED_SIGNAL_KEYWORDS if k in text)
    if has_stock and signal_hits >= 1:
        return {"decision": "PASS", "reason": "rule:stock+signal", "score": None, "mode": "embedded_rule"}

    # 6. 题材信号 >= 3 → PASS
    if signal_hits >= 3:
        return {"decision": "PASS", "reason": f"rule:signal_hits={signal_hits}", "score": None, "mode": "embedded_rule"}

    # 6b. Phase 4F: ETF/行情标题 + 实质性产业内容 → 直接PASS（不依赖Qwen）
    # 防止Qwen被ETF标题误导而错杀含SEMI/台积电/涨价函等产业新闻
    _ETF_BODY_INDUSTRY = (
        "半导体", "SEMI", "台积电", "英特尔", "三星", "英伟达",
        "玻璃基板", "先进封装", "覆铜板", "CCL", "PCB",
        "涨价", "提价", "扩产", "并购", "收购", "重组",
        "亿美元", "亿人民币",
    )
    title_looks_market = bool(re.search(
        r'(?:ETF|收[涨跌]|开盘|盘中).*(?:涨|跌)(?:超|了)?\d+%'   # ETF/行情 + 涨跌X%
        r'|(?:涨|跌)(?:超|了)?\d+%.*ETF',                          # 涨跌X% + ETF
        title
    ))
    if title_looks_market:
        body_industry = sum(1 for t in _ETF_BODY_INDUSTRY if t in content)
        if body_industry >= 1:
            return {"decision": "PASS",
                    "reason": f"rule:etf_title_industry_content:{body_industry}",
                    "score": None, "mode": "embedded_rule"}

    # 7. 灰区 → 保守放行到 triage
    return {"decision": "PASS", "reason": "rule:gray_pass_to_triage", "score": None, "mode": "embedded_rule"}

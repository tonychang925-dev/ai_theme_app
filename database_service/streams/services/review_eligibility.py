"""Review eligibility gate for product runtime event review queues.

HUMAN_REVIEW is reserved for high-value events whose theme is uncertain.
Weak evidence, ordinary disclosures and low-value news should be archived
instead of entering product-facing review queues.
"""

from __future__ import annotations

import json
import re
from typing import Any


HIGH_VALUE_IMPORTANCE_LEVELS = {"S", "A", "B"}
HIGH_VALUE_EVENT_TYPES = {
    "theme_catalyst",
    "company_catalyst",
    "macro_policy",
    "sector_supply_demand",
    "major_risk_alert",
}

LOW_VALUE_EVENT_TYPES = {
    "low_value_disclosure",
    "market_noise",
    "duplicate",
    "ordinary_disclosure",
    "ordinary_earnings",
    "regulatory_notice",
    "clarification_risk_notice",
    "weather_disaster",
    "ordinary_ipo",
    "ordinary_personnel_change",
    "ordinary_ir_activity",
}

LOW_VALUE_REASON_CODES = {
    "low_value_event_match_blocked",
    "low_value_regulatory_event_blocked",
    "ordinary_earnings_low_value",
    "clarification_risk_notice_low_value",
    "weather_disaster_low_value",
    "ordinary_ipo_low_value",
    "duplicate_news_low_value",
    "low_value_event_dropped",
    "rule_low_value_regulatory",
    "rule_low_value_clarification",
    "rule_low_value_disaster",
    "rule_low_value_earnings",
    "rule_low_value_disclosure",
    "rule_low_value_rights_change",
    "rule_low_value_investor_event",
    "rule_low_value_ordinary_personnel",
    "rule_low_value_ordinary_ipo",
}

WEAK_REVIEW_REASON_CODES = {
    "weak_v1_direct_hit_review",
    "weak_v1_llm_accept_review",
    "llm_accept_without_hard_evidence",
    "llm_accept_without_anchor_evidence",
    "llm_accept_generic_only_review",
    "low_conf_llm_accept_review",
    "role_guard_blocked",
    "llm_accept_role_guard_blocked",
    "ambiguous_top_candidate",
}

LOW_VALUE_TERMS = (
    "行政监管措施",
    "行政监管",
    "监管措施决定书",
    "监管函",
    "警示函",
    "责令改正",
    "问询函",
    "关注函",
    "审核问询函",
    "澄清",
    "风险提示",
    "交易异动",
    "异常波动",
    "连续涨停",
    "连板",
    "无注入",
    "不涉及",
    "无算力计划",
    "不存在",
    "未开展",
    "天气预警",
    "山洪",
    "暴雨",
    "地震",
    "列车停运",
    "旅客列车停",
    "第一季度",
    "一季度",
    "Q1",
    "财报",
    "营收",
    "净利润",
    "业绩说明会",
    "回购",
    "减持",
    "权益变动",
    "触及1%整数倍",
    "投资者接待日",
    "集体接待日",
    "任命",
    "辞任",
    "选举",
    "IPO",
    "上市聆讯",
    "递表",
    "招股书",
)

LOW_VALUE_BUCKETS = {
    "low_value_regulatory": ("行政监管", "监管措施", "监管函", "警示函", "责令改正", "问询函", "关注函"),
    "ordinary_earnings": ("第一季度", "一季度", "Q1", "财报", "营收", "净利润", "业绩说明会"),
    "clarification_risk_notice": ("澄清", "风险提示", "交易异动", "异常波动", "连续涨停", "连板", "无注入", "不涉及", "不存在", "未开展"),
    "weather_disaster": ("天气预警", "山洪", "暴雨", "地震", "列车停运", "旅客列车停"),
    "ordinary_disclosure": ("回购", "减持", "权益变动", "触及1%整数倍", "投资者接待日", "集体接待日"),
    "ordinary_personnel_change": ("任命", "辞任", "选举"),
    "ordinary_ipo": ("IPO", "上市聆讯", "递表", "招股书"),
}

STRONG_CATALYST_TERMS = (
    "重大订单",
    "重大合同",
    "中标",
    "签署合同",
    "重大并购",
    "重大资产重组",
    "并购重组",
    "产业政策",
    "技术突破",
    "首次突破",
    "供给短缺",
    "价格上涨",
    "价格大涨",
    "需求激增",
    "出口管制",
    "获批上市",
    "投产",
    "扩产",
    "产能释放",
    "国家级规划",
    "部委联合印发",
    "联合印发",
    "专项方案",
    "新题材",
    "映射A股",
    "产业影响",
    "新规",
)


def should_enter_human_review(
    event: dict[str, Any] | None,
    match_result: dict[str, Any] | None = None,
    triage_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return whether an event is eligible for product-facing HUMAN_REVIEW."""

    event = event or {}
    match_result = match_result or {}
    triage_result = triage_result or {}
    text = _event_text(event, match_result, triage_result)
    reason_code = _first_non_empty(
        match_result.get("reason_code"),
        match_result.get("reason"),
        event.get("reason_code"),
        event.get("reason"),
        triage_result.get("reason_code"),
    )
    runtime_source = str(match_result.get("runtime_source") or event.get("runtime_source") or "")
    match_reason = str(match_result.get("match_reason") or event.get("match_reason") or "")
    importance = str(triage_result.get("importance_level") or event.get("importance_level") or "").upper()
    value_type = str(triage_result.get("event_value_type") or event.get("event_value_type") or "").strip()
    decision = str(triage_result.get("decision") or event.get("triage_decision") or "").upper()

    low_bucket = classify_low_value_text(text)
    if reason_code in LOW_VALUE_REASON_CODES or value_type in LOW_VALUE_EVENT_TYPES or low_bucket:
        return _reject(
            "low_value_review_dropped",
            "drop_low_value",
            reason_code or low_bucket or value_type or "low_value",
        )
    if decision == "DUPLICATE" or value_type == "duplicate":
        return _reject("duplicate_review_dropped", "drop_duplicate", "duplicate")

    has_strong_catalyst = any(term in text for term in STRONG_CATALYST_TERMS)
    has_hard_evidence = _has_hard_evidence(match_result)
    high_triage = importance in HIGH_VALUE_IMPORTANCE_LEVELS and value_type in HIGH_VALUE_EVENT_TYPES
    possible_new_theme = any(term in text for term in ("新题材", "首次", "突破", "产业链催化", "映射A股"))

    if reason_code in WEAK_REVIEW_REASON_CODES:
        if not (high_triage and (has_strong_catalyst or has_hard_evidence or possible_new_theme)):
            return _reject("weak_evidence_review_dropped", "drop_weak_evidence", reason_code)

    if runtime_source == "v1_fallback" and not (high_triage and (has_hard_evidence or has_strong_catalyst)):
        return _reject("weak_v1_fallback_review_dropped", "drop_weak_evidence", "weak_v1_fallback")

    generic_only = bool(
        match_result.get("generic_only_evidence")
        or match_result.get("generic_only")
        or reason_code in {"llm_accept_generic_only_review"}
    )
    if generic_only and not has_hard_evidence:
        return _reject("generic_only_review_dropped", "drop_weak_evidence", "generic_only_evidence")

    if high_triage and (has_strong_catalyst or has_hard_evidence or possible_new_theme):
        return {
            "should_keep_review": True,
            "review_required": True,
            "drop_reason": "",
            "suggested_action": "keep_review",
            "reason_code": "review_eligible_high_value_uncertain",
            "importance_level": importance,
            "event_value_type": value_type,
        }

    return _reject("review_ineligible_dropped", "unknown_watch", reason_code or "not_high_value_review")


def classify_low_value_text(text: str) -> str:
    for bucket, terms in LOW_VALUE_BUCKETS.items():
        if any(term in text for term in terms):
            return bucket
    return ""


def _has_hard_evidence(match_result: dict[str, Any]) -> bool:
    evidence = match_result.get("best_evidence")
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = {}
    evidence = evidence if isinstance(evidence, dict) else {}
    candidate_lists = [
        match_result.get("accepted_anchor_hits"),
        match_result.get("hard_anchor_hits"),
        match_result.get("must_hits"),
        match_result.get("strong_hits"),
        evidence.get("accepted_anchor_hits"),
        evidence.get("hard_anchor_hits"),
        evidence.get("must_hits"),
        evidence.get("strong_hits"),
        evidence.get("accept_requires_any_hits"),
        evidence.get("accepted_terms"),
    ]
    for value in candidate_lists:
        if isinstance(value, (list, tuple, set)) and any(str(item).strip() for item in value):
            return True
    return False


def _event_text(*objects: dict[str, Any]) -> str:
    parts: list[str] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        for key in ("title", "summary", "content", "event_title", "reason", "reason_code"):
            value = obj.get(key)
            if value:
                parts.append(str(value))
        event_data = obj.get("event_data")
        if isinstance(event_data, dict):
            for key in ("title", "summary", "content"):
                if event_data.get(key):
                    parts.append(str(event_data.get(key)))
        evidence = obj.get("evidence")
        if isinstance(evidence, list):
            parts.extend(str(item) for item in evidence)
    return re.sub(r"\s+", " ", " ".join(parts))


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _reject(reason_code: str, suggested_action: str, drop_reason: str) -> dict[str, Any]:
    return {
        "should_keep_review": False,
        "review_required": False,
        "drop_reason": drop_reason,
        "suggested_action": suggested_action,
        "reason_code": reason_code,
        "action": "drop_event",
    }

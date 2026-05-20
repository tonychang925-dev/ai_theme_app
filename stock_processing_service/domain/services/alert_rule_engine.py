"""P1-E1: 公告级风险预警与机会提醒规则引擎（带评分、去重、分级）。

纯规则引擎，不调用 LLM。
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

# 主线题材关键词（命中加分）
MAINLINE_THEME_KEYWORDS = {
    "算力", "液冷", "数据中心", "AI芯片", "AI服务器", "光模块", "HBM",
    "机器人", "人形机器人", "具身智能",
    "商业航天", "卫星互联网", "低轨星座", "可回收火箭",
    "半导体", "先进封装", "光刻", "EDA", "chiplet",
    "自动驾驶", "智能驾驶", "激光雷达",
    "固态电池", "钠电池", "钙钛矿",
    "可控核聚变", "量子计算",
}


class AlertRuleEngine:
    """基于 structured_intel_event 字段的规则引擎（P1-E1: 评分+去重）。"""

    @staticmethod
    def evaluate(intel_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        alerts.extend(_risk_rules(intel_event))
        alerts.extend(_opportunity_rules(intel_event))
        for a in alerts:
            a["alert_score"] = _compute_score(a, intel_event)
            a["dedupe_key"] = _dedupe_key(a)
        return alerts

    @staticmethod
    def evaluate_batch(intel_events: List[Dict[str, Any]],
                       risk_top_n: int = 5,
                       opportunity_top_n: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """批量评估并去重/排序/截断。返回 {"risk_alerts": [...], "opportunity_alerts": [...]}"""
        all_alerts: List[Dict[str, Any]] = []
        for ev in intel_events:
            all_alerts.extend(AlertRuleEngine.evaluate(ev))

        risk = [a for a in all_alerts if a["alert_type"] == "risk"]
        opportunity = [a for a in all_alerts if a["alert_type"] == "opportunity"]

        return {
            "risk_alerts": _dedupe_and_sort(risk)[:risk_top_n],
            "opportunity_alerts": _dedupe_and_sort(opportunity)[:opportunity_top_n],
        }


def _dedupe_and_sort(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 dedupe_key 去重，保留最高分。按 score desc 排序。"""
    seen: Dict[str, Dict[str, Any]] = {}
    for a in alerts:
        key = a.get("dedupe_key", "")
        if key not in seen or a.get("alert_score", 0) > seen[key].get("alert_score", 0):
            seen[key] = a
    result = list(seen.values())
    result.sort(key=lambda a: (-a.get("alert_score", 0), -(a.get("impact_score") or 0)))
    return result


def _dedupe_key(alert: Dict[str, Any]) -> str:
    stock = alert.get("stock_code", "")
    subtype = alert.get("risk_subtype") or alert.get("opportunity_subtype") or ""
    title = alert.get("title", "")
    raw = f"{stock}:{subtype}:{title[:30]}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _compute_score(alert: Dict[str, Any], ev: Dict[str, Any]) -> int:
    """0-100 评分：基础分 + 级别分 + 金额分 + 题材分。"""
    score = 50  # 基础
    level = alert.get("alert_level", "normal")
    if level == "critical": score += 30
    elif level == "important": score += 15
    # 金额分
    amount = alert.get("amount", "") or ""
    if "亿" in amount: score += 15
    elif "千万" in amount: score += 8
    elif "百万" in amount: score += 3
    # 主线题材
    title = (alert.get("title") or "").lower()
    summary = (alert.get("summary") or "").lower()
    text = title + summary
    mainline_hits = sum(1 for kw in MAINLINE_THEME_KEYWORDS if kw in text)
    if mainline_hits >= 3: score += 15
    elif mainline_hits >= 1: score += 8
    # doc_value_level
    doc_level = str(ev.get("doc_value_level") or "")
    if doc_level == "A": score += 5
    return min(100, max(0, score))


# ── Risk rules ──────────────────────────────────────────────────────

def _risk_rules(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    event_type = str(ev.get("event_type") or "").lower()
    risk_tags = list(ev.get("risk_tags") or [])
    title = str(ev.get("title") or "")
    summary = str(ev.get("summary") or "")
    impact = str(ev.get("impact_assessment") or
                 (ev.get("business_metrics") or {}).get("impact_assessment", ""))

    stock = ev.get("stock_code", "")
    sname = ev.get("stock_name", "")

    def _a(subtype: str, level: str, reason: str, reason_code: str, **kw) -> Dict[str, Any]:
        return {
            "alert_type": "risk", "alert_level": level, "alert_score": 0,
            "title": title, "summary": summary, "reason": reason,
            "reason_code": reason_code, "risk_subtype": subtype,
            "source_event_id": ev.get("event_id") or ev.get("id"),
            "source_doc_id": ev.get("raw_doc_id"),
            "stock_code": stock, "stock_name": sname,
            "publish_time": ev.get("publish_time"),
            "impact_score": ev.get("impact_score") or 0,
            **kw,
        }

    if "delisting_risk" in event_type or "退市" in title:
        alerts.append(_a("delisting_risk", "critical", "公司涉及退市风险", "R01_DELISTING"))

    if "regulatory_penalty" in event_type or "立案" in title or "行政处罚" in title:
        level = "critical" if "立案" in title else "important"
        alerts.append(_a("regulatory_penalty", level, "监管处罚/立案调查", "R02_REGULATORY"))

    if "lawsuit_arbitration" in event_type or "诉讼" in title or "仲裁" in title:
        alerts.append(_a("lawsuit_arbitration", "important", "涉及诉讼/仲裁", "R03_LITIGATION"))

    if "goodwill_impairment" in event_type or "商誉" in title or "资产减值" in title:
        alerts.append(_a("goodwill_impairment", "important", "商誉/资产减值", "R04_IMPAIRMENT"))

    if "减持" in title:
        level = "important" if ("大额" in title or "5%" in title) else "normal"
        alerts.append(_a("shareholder_reduce", level, "股东减持", "R05_REDUCE"))

    if "债务" in title or "违约" in title or "项目终止" in title or "提前终止" in title:
        alerts.append(_a("debt_restructure", "critical" if "违约" in title else "important",
                         "债务重组/违约/项目终止", "R06_DEBT"))

    if "风险提示" in title or "trading_risk" in event_type:
        alerts.append(_a("trading_risk", "normal", "风险提示公告", "R07_RISK_ALERT"))

    if "负面" in impact and not alerts:
        alerts.append(_a("negative_impact", "normal", "负面影响评估", "R08_NEGATIVE"))

    return alerts


# ── Opportunity rules ───────────────────────────────────────────────

def _opportunity_rules(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    event_type = str(ev.get("event_type") or "").lower()
    title = str(ev.get("title") or "")
    business = ev.get("business_metrics") or {}
    amount = business.get("amount", "") if isinstance(business, dict) else ""

    stock = ev.get("stock_code", "")
    sname = ev.get("stock_name", "")

    def _a(subtype: str, level: str, reason: str, reason_code: str, **kw) -> Dict[str, Any]:
        return {
            "alert_type": "opportunity", "alert_level": level, "alert_score": 0,
            "title": title, "summary": ev.get("summary", ""), "reason": reason,
            "reason_code": reason_code, "opportunity_subtype": subtype,
            "source_event_id": ev.get("event_id") or ev.get("id"),
            "source_doc_id": ev.get("raw_doc_id"),
            "stock_code": stock, "stock_name": sname,
            "publish_time": ev.get("publish_time"),
            "impact_score": ev.get("impact_score") or 0,
            **kw,
        }

    # 重大合同（金额大 → important）
    if "major_contract" in event_type:
        level = "important" if ("亿" in amount or "重大" in title) else "normal"
        reason = "重大合同" + (f"，{amount}" if amount else "")
        alerts.append(_a("major_contract", level, reason, "O01_CONTRACT", amount=amount))

    if "中标" in title:
        level = "important" if "亿" in amount else "normal"
        reason = "中标" + (f"，{amount}" if amount else "")
        alerts.append(_a("project_win", level, reason, "O02_BID_WIN", amount=amount))

    if "share_repurchase" in event_type or "回购" in title:
        level = "important" if ("大额" in title or "亿" in amount) else "normal"
        alerts.append(_a("share_repurchase", level, "股份回购", "O03_REPURCHASE", amount=amount))

    if "capex_expansion" in event_type or "投资扩产" in title or "产能建设" in title:
        alerts.append(_a("capex_expansion", "important", "投资扩产/产能建设", "O04_CAPEX"))

    if "mna_restructuring" in event_type or "并购" in title:
        alerts.append(_a("mna_restructuring", "important", "并购重组", "O05_MNA"))

    if "dividend_plan" in event_type or "分红" in title or "权益分派" in title:
        alerts.append(_a("dividend", "normal", "分红/权益分派", "O06_DIVIDEND"))

    if "业绩" in title and ("预增" in title or "增长" in title):
        alerts.append(_a("performance_growth", "important", "业绩预增/增长", "O07_EARNINGS"))

    return alerts

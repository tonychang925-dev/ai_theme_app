"""P1-E: 公告级风险预警与机会提醒规则引擎。

纯规则引擎，不调用 LLM。
输入 structured_intel_event 风格 dict，输出 risk_alerts / opportunity_alerts。
"""
from __future__ import annotations

from typing import Any, Dict, List


class AlertRuleEngine:
    """基于 structured_intel_event 字段的规则引擎。"""

    @staticmethod
    def evaluate(intel_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """评估单条 Intel 事件，返回 alert list（可能为空）。"""
        alerts: List[Dict[str, Any]] = []
        alerts.extend(_risk_rules(intel_event))
        alerts.extend(_opportunity_rules(intel_event))
        return alerts

    @staticmethod
    def evaluate_batch(intel_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量评估。"""
        all_alerts: List[Dict[str, Any]] = []
        for ev in intel_events:
            all_alerts.extend(AlertRuleEngine.evaluate(ev))
        # 按 level 优先级 + publish_time 排序
        level_order = {"critical": 0, "important": 1, "normal": 2}
        all_alerts.sort(key=lambda a: (
            level_order.get(a.get("alert_level", "normal"), 2),
            -(a.get("impact_score") or 0),
        ))
        return all_alerts


def _risk_rules(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    """风险类规则。"""
    alerts: List[Dict[str, Any]] = []
    event_type = str(ev.get("event_type") or "").lower()
    event_level = str(ev.get("event_level") or "normal").lower()
    risk_tags = list(ev.get("risk_tags") or [])
    title = str(ev.get("title") or "")
    summary = str(ev.get("summary") or "")
    impact = str(ev.get("impact_assessment") or (ev.get("business_metrics") or {}).get("impact_assessment", ""))

    def _alert(alert_type: str, level: str, reason: str, **kw) -> Dict[str, Any]:
        base = {
            "alert_type": "risk",
            "alert_level": level,
            "title": title,
            "summary": summary,
            "reason": reason,
            "risk_subtype": alert_type,
            "source_event_id": ev.get("event_id") or ev.get("id"),
            "source_doc_id": ev.get("raw_doc_id"),
            "stock_code": ev.get("stock_code", ""),
            "stock_name": ev.get("stock_name", ""),
            "publish_time": ev.get("publish_time"),
            "impact_score": ev.get("impact_score") or 0,
        }
        base.update(kw)
        return base

    # 退市风险
    if "delisting_risk" in event_type or "退市" in title or "退市" in str(risk_tags):
        alerts.append(_alert("delisting_risk", "critical", "公司涉及退市风险，需紧急关注"))

    # 监管处罚
    if "regulatory_penalty" in event_type or "监管" in str(risk_tags) or "处罚" in title or "立案" in title:
        level = "critical" if ("立案" in title or "critical" in event_level) else "important"
        alerts.append(_alert("regulatory_penalty", level, "公司涉及监管处罚或立案调查"))

    # 诉讼仲裁
    if "lawsuit_arbitration" in event_type or "诉讼" in title or "仲裁" in title:
        alerts.append(_alert("lawsuit_arbitration", "important", "公司涉及诉讼或仲裁"))

    # 商誉减值
    if "goodwill_impairment" in event_type or "商誉" in title or "减值" in title:
        alerts.append(_alert("goodwill_impairment", "important", "公司涉及商誉或资产减值"))

    # 减持
    if "减持" in title or "shareholder_change" in event_type:
        alerts.append(_alert("shareholder_reduce", "important", "重要股东减持"))

    # 债务违约/重组/项目终止
    if "债务" in title or "违约" in title or "项目终止" in title or "提前终止" in title:
        alerts.append(_alert("debt_restructure", "important", "涉及债务重组/违约或项目终止"))

    # 风险提示
    if "风险提示" in title or "trading_risk" in event_type or "风险" in str(risk_tags):
        alerts.append(_alert("trading_risk", "normal", "公司发布风险提示公告"))

    # 负面影响评估
    if "负面" in impact:
        if not alerts:  # 没有更具体的风险时
            alerts.append(_alert("negative_impact", "normal", f"影响评估: {impact}"))

    return alerts


def _opportunity_rules(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    """机会类规则。"""
    alerts: List[Dict[str, Any]] = []
    event_type = str(ev.get("event_type") or "").lower()
    catalyst_tags = list(ev.get("catalyst_tags") or [])
    title = str(ev.get("title") or "")
    summary = str(ev.get("summary") or "")
    business = ev.get("business_metrics") or {}
    amount = business.get("amount", "") if isinstance(business, dict) else ""

    def _alert(alert_type: str, level: str, reason: str, **kw) -> Dict[str, Any]:
        base = {
            "alert_type": "opportunity",
            "alert_level": level,
            "title": title,
            "summary": summary,
            "reason": reason,
            "opportunity_subtype": alert_type,
            "source_event_id": ev.get("event_id") or ev.get("id"),
            "source_doc_id": ev.get("raw_doc_id"),
            "stock_code": ev.get("stock_code", ""),
            "stock_name": ev.get("stock_name", ""),
            "publish_time": ev.get("publish_time"),
            "impact_score": ev.get("impact_score") or 0,
        }
        base.update(kw)
        return base

    # 重大合同
    if "major_contract" in event_type:
        reason = "公司签署重大合同" + (f"，金额{amount}" if amount else "")
        alerts.append(_alert("major_contract", "important", reason, amount=amount))

    # 中标
    if "中标" in title:
        reason = "公司中标项目" + (f"，金额{amount}" if amount else "")
        alerts.append(_alert("project_win", "important", reason, amount=amount))

    # 回购
    if "share_repurchase" in event_type or "回购" in title:
        alerts.append(_alert("share_repurchase", "important", "公司发布回购公告"))

    # 投资扩产
    if "capex_expansion" in event_type or "投资" in title or "产能" in title or "扩产" in title:
        alerts.append(_alert("capex_expansion", "important", "投资扩产或产能建设"))

    # 并购重组
    if "mna_restructuring" in event_type or "重组" in title:
        alerts.append(_alert("mna_restructuring", "important", "并购重组"))

    # 分红
    if "dividend_plan" in event_type or "分红" in title or "权益分派" in title:
        alerts.append(_alert("dividend", "normal", "分红/权益分派"))

    return alerts

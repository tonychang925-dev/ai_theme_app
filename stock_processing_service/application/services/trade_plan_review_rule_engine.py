from __future__ import annotations

import re
from typing import Any


HIGH_RISK_PATTERNS = ("满仓", "梭哈", "一定买", "必须买", "无脑买", "重仓追")
EMOTION_PATTERNS = ("急于回本", "不能再错过", "必须抓住", "踏空焦虑", "报复性交易", "翻本")


class TradePlanReviewRuleEngine:
    def evaluate(self, *, plan_text: str, context: dict[str, Any]) -> dict[str, Any]:
        score = 100
        must_fix: list[str] = []
        checks: list[dict[str, str]] = []
        warnings: list[str] = []

        if not self._has_filled_line(plan_text, ("仓位上限", "仓位计划")):
            score -= 15
            must_fix.append("缺少明确仓位上限")
            checks.append({"name": "仓位纪律", "status": "fail", "comment": "未发现已填写的仓位上限"})
        else:
            checks.append({"name": "仓位纪律", "status": "pass", "comment": "已填写仓位约束"})

        if not self._has_filled_line(plan_text, ("止损", "止盈")):
            score -= 15
            must_fix.append("缺少明确止损或止盈条件")
            checks.append({"name": "退出条件", "status": "fail", "comment": "未发现已填写的止损/止盈条件"})
        else:
            checks.append({"name": "退出条件", "status": "pass", "comment": "已填写退出条件"})

        if not self._has_filled_line(plan_text, ("不买条件", "放弃条件", "不参与")):
            score -= 10
            must_fix.append("缺少必须放弃或不买条件")
            checks.append({"name": "放弃条件", "status": "fail", "comment": "未发现已填写的放弃条件"})
        else:
            checks.append({"name": "放弃条件", "status": "pass", "comment": "已填写不买或放弃条件"})

        high_risk_hits = [word for word in HIGH_RISK_PATTERNS if word in plan_text]
        if high_risk_hits:
            score -= 25
            must_fix.append(f"存在高风险交易表述：{'、'.join(high_risk_hits)}")
            checks.append({"name": "高风险表述", "status": "fail", "comment": "出现满仓/梭哈/必须买等表达"})
        else:
            checks.append({"name": "高风险表述", "status": "pass", "comment": "未发现明显高风险表述"})

        emotion_hits = [word for word in EMOTION_PATTERNS if word in plan_text]
        if emotion_hits:
            score -= 20
            warnings.append(f"存在情绪化交易倾向：{'、'.join(emotion_hits)}")
            checks.append({"name": "情绪纪律", "status": "watch", "comment": "出现情绪化交易关键词"})
        else:
            checks.append({"name": "情绪纪律", "status": "pass", "comment": "未发现明显情绪化表达"})

        theme_terms = [str(t) for t in context.get("theme_terms") or [] if str(t).strip()]
        if theme_terms:
            matched = [term for term in theme_terms if term in plan_text]
            if matched:
                checks.append({"name": "盘后主题一致性", "status": "pass", "comment": f"计划提及盘后主题：{'、'.join(matched[:5])}"})
            else:
                score -= 10
                warnings.append("计划未明显提及盘后复盘中的主题词，需确认是否脱离主线")
                checks.append({"name": "盘后主题一致性", "status": "watch", "comment": "未匹配到盘后复盘主题词"})
        else:
            checks.append({"name": "盘后主题一致性", "status": "watch", "comment": "盘后快照未提供可比对主题词"})

        score = max(0, min(100, score))
        risk_level = self._risk_level(score, must_fix)
        status = self._review_status(score, must_fix, high_risk_hits)
        return {
            "review_status": status,
            "risk_level": risk_level,
            "review_score": score,
            "summary": self._summary(status, risk_level, score),
            "must_fix": must_fix,
            "consistency_checks": checks,
            "executable_conditions": [
                "交易标的必须符合已填写的买入条件",
                "仓位不得超过计划中的上限",
                "盘中不得临时新增计划外标的",
            ],
            "abandon_conditions": [
                "触发计划中的不买或放弃条件",
                "目标股走势与盘后复盘方向明显背离",
                "出现情绪化追涨或扩大仓位冲动",
            ],
            "position_advice": {
                "max_position": "以计划中填写的仓位上限为准",
                "style": "先满足条件，再执行；不追高",
            },
            "discipline_warnings": warnings or ["禁止因踏空焦虑临盘追涨", "禁止在计划外加仓"],
            "disclaimer": "本结果为交易计划审核建议，不构成自动交易指令。",
        }

    @staticmethod
    def _has_filled_line(text: str, labels: tuple[str, ...]) -> bool:
        for line in text.splitlines():
            normalized = line.strip().lstrip("-0123456789.、 ").strip()
            for label in labels:
                if label not in normalized:
                    continue
                match = re.search(r"[：:]\s*(.+)$", normalized)
                if match and match.group(1).strip():
                    return True
                if "：" in normalized or ":" in normalized:
                    continue
                if re.search(r"(一成|二成|三成|四成|五成|半仓|轻仓|[0-9]+%|跌破|高开|低开|不及预期|退潮)", normalized):
                    return True
        return False

    @staticmethod
    def _risk_level(score: int, must_fix: list[str]) -> str:
        if score >= 85 and not must_fix:
            return "低"
        if score >= 70:
            return "中"
        if score >= 50:
            return "高"
        return "极高"

    @staticmethod
    def _review_status(score: int, must_fix: list[str], high_risk_hits: list[str]) -> str:
        if high_risk_hits or score < 50:
            return "高风险"
        if score < 70:
            return "不建议执行"
        if must_fix:
            return "有条件通过"
        return "通过"

    @staticmethod
    def _summary(status: str, risk_level: str, score: int) -> str:
        return f"审核结论：{status}；风险等级：{risk_level}；审核分：{score}。"

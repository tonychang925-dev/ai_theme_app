"""MajorEventClassifier — Phase 1 PR-4A.

Identifies fast-line trigger events: major policy, national projects,
geopolitical conflicts, technology breakthroughs, etc.

Pure rule-based (keyword matching). No LLM dependency.
Output: major_event_score, is_fast_line_trigger, trigger_type.

Constraint: supporting_event_ids must be non-empty for trigger=True.
Threshold: major_event_score >= 85.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── trigger types ──

FAST_LINE_TRIGGER_TYPES: dict[str, dict[str, Any]] = {
    "major_policy": {
        "level": "A", "base_score": 92, "impact_scope": "industry_chain",
        "keywords": ["国务院", "中共中央", "发改委", "工信部", "国家规划", "十四五", "十五五",
                      "专项债", "特别国债", "产业基金", "国家重点", "战略新兴产业"],
        "expected_duration": "multi_week",
    },
    "national_project": {
        "level": "A", "base_score": 90, "impact_scope": "industry_chain",
        "keywords": ["国家工程", "国家级项目", "雅江水电站", "航天工程", "卫星工程",
                      "大科学装置", "空间站", "深海", "探月"],
        "expected_duration": "1-2_weeks",
    },
    "geopolitical_conflict": {
        "level": "A", "base_score": 88, "impact_scope": "market_wide",
        "keywords": ["冲突", "战争", "制裁", "领海", "领土", "封锁", "军演",
                      "地缘", "以伊", "俄乌", "朝韩", "台海"],
        "expected_duration": "1-2_weeks",
    },
    "industry_rule_change": {
        "level": "B", "base_score": 86, "impact_scope": "industry_sector",
        "keywords": ["监管新规", "行业规范", "产业政策调整", "环保限产", "碳排放",
                      "双碳", "能耗双控", "出口管制", "进口许可"],
        "expected_duration": "1-2_weeks",
    },
    "major_institution_setup": {
        "level": "B", "base_score": 85, "impact_scope": "industry_chain",
        "keywords": ["航天司成立", "数据局成立", "总局成立", "国家局成立",
                      "国务院组建", "中央组建", "国家数据局", "航天局",
                      "领导小组", "央企重组", "国企改革"],
        "expected_duration": "multi_week",
        "negative_keywords": ["公司成立", "分公司成立", "子公司成立", "部门成立",
                              "事业部", "办公室成立", "党支部成立"],
    },
    "technology_breakthrough": {
        "level": "B", "base_score": 87, "impact_scope": "industry_chain",
        "keywords": ["突破", "首次", "纪录", "里程碑", "量产", "商用",
                      "试飞", "首飞", "首发", "刷新", "打破"],
        "expected_duration": "1-2_weeks",
    },
    "supply_demand_shock": {
        "level": "B", "base_score": 85, "impact_scope": "industry_sector",
        "keywords": ["减产", "停产", "限产", "供给紧张", "缺货", "涨价",
                      "供需", "短缺", "库存告急", "断供"],
        "expected_duration": "1-2_weeks",
    },
    "price_shock": {
        "level": "B", "base_score": 85, "impact_scope": "industry_sector",
        "keywords": ["暴涨", "暴跌", "价格新高", "历史新高", "大宗",
                      "期货涨停", "连续封板"],
        "expected_duration": "days_to_1_week",
    },
    "giant_product_or_order": {
        "level": "B", "base_score": 85, "impact_scope": "industry_chain",
        "keywords": ["超大订单", "百亿", "千亿", "万亿", "巨头发布",
                      "旗舰产品", "新品发布", "产业链订单"],
        "expected_duration": "1-2_weeks",
    },
}


@dataclass
class MajorEventClassification:
    major_event_score: float = 0.0
    major_event_level: str = "C"
    is_fast_line_trigger: bool = False
    trigger_type: str | None = None
    impact_scope: str = "unknown"
    expected_duration: str = "unknown"
    supporting_event_ids: list[str] = field(default_factory=list)
    reason: str = ""
    method: str = "rule_keyword_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "major_event_score": self.major_event_score,
            "major_event_level": self.major_event_level,
            "is_fast_line_trigger": self.is_fast_line_trigger,
            "trigger_type": self.trigger_type,
            "impact_scope": self.impact_scope,
            "expected_duration": self.expected_duration,
            "supporting_event_ids": self.supporting_event_ids,
            "reason": self.reason,
            "method": self.method,
        }


@dataclass
class MajorEventClassifier:
    """Classify whether event chains contain fast-line trigger events.

    Pure rule-based (keyword matching). LLM-free for T+0 safety.
    """

    def classify(
        self,
        event_chain: list[dict[str, Any]],
        event_series: list[dict[str, Any]] | None = None,
    ) -> MajorEventClassification:
        """Return MajorEventClassification for the given event chain."""
        series = event_series or []

        # Collect supporting event IDs
        all_ids = [str(ev.get("event_id") or "") for ev in event_chain if str(ev.get("event_id") or "")]
        all_ids = list(dict.fromkeys(all_ids))  # dedup, preserve order

        # ── score each trigger type ──
        best_score = 0.0
        best_type: str | None = None
        best_config: dict[str, Any] = {}
        matched_ids: list[str] = []

        for ttype, config in FAST_LINE_TRIGGER_TYPES.items():
            hit_count = 0
            hit_ids: list[str] = []
            neg_kws = config.get("negative_keywords", [])
            for ev in event_chain:
                title = str(ev.get("title") or "").lower()
                summary = str(ev.get("summary") or "").lower()
                text = title + " " + summary
                if neg_kws and any(nk.lower() in text for nk in neg_kws):
                    continue
                for kw in config["keywords"]:
                    if kw.lower() in text:
                        hit_count += 1
                        eid = str(ev.get("event_id") or "")
                        if eid and eid not in hit_ids:
                            hit_ids.append(eid)
                        break  # one match per event
            if hit_count > 0:
                score = min(98.0, config["base_score"] + min(hit_count * 2, 8))
                if score > best_score:
                    best_score = score
                    best_type = ttype
                    best_config = config
                    matched_ids = hit_ids

        # ── also check event_series for continuity bonus ──
        if series and best_score > 0:
            for s in series:
                if s.get("consistency_score", 0) >= 70:
                    best_score = min(98.0, best_score + 3)

        # ── build result ──
        if best_score >= 85 and matched_ids:
            reason_parts = []
            cn_type = best_type
            label = {
                "major_policy": "重大政策", "national_project": "国家级工程",
                "geopolitical_conflict": "地缘冲突", "industry_rule_change": "产业规则变化",
                "major_institution_setup": "重大机构成立", "technology_breakthrough": "技术突破",
                "supply_demand_shock": "供需冲击", "price_shock": "价格冲击",
                "giant_product_or_order": "巨头产品/订单",
            }.get(best_type, best_type)
            reason_parts.append(f"{label}事件触发")
            reason_parts.append(f"匹配 {len(matched_ids)} 条事件")
            if series:
                reason_parts.append("存在连续事件系列")
            return MajorEventClassification(
                major_event_score=best_score,
                major_event_level=best_config.get("level", "B"),
                is_fast_line_trigger=True,
                trigger_type=best_type,
                impact_scope=best_config.get("impact_scope", "unknown"),
                expected_duration=best_config.get("expected_duration", "1-2_weeks"),
                supporting_event_ids=matched_ids,
                reason="；".join(reason_parts),
                method="rule_keyword_v1",
            )

        # ── no trigger ──
        return MajorEventClassification(
            major_event_score=best_score,
            major_event_level="C",
            is_fast_line_trigger=False,
            trigger_type=None,
            supporting_event_ids=matched_ids if best_score >= 60 else [],
            reason="未达到快线触发阈值" if best_score < 85 else f"最佳匹配 {best_type} 但未达到阈值",
            method="rule_keyword_v1",
        )

"""主线聚类规则 — 1:1 复刻旧链 build_mainline_identity_registry.py 中的 cluster 逻辑。

包含:
  - _apply_cluster_compensation: 簇级一致性增强，满足簇条件则 rule_is_main_theme=True
  - _apply_cluster_bootstrap_direct_confirm: 历史回填直确认模式

所有规则纯业务逻辑，不依赖 I/O。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── 默认簇配置（等价于旧链 DEFAULT_CLUSTER_RULES）──
DEFAULT_CLUSTER_RULES: list[dict[str, Any]] = [
    {
        "name": "commercial_space",
        "keywords": [
            "商业航天", "卫星互联网", "卫星", "星链", "航天", "航天国家队",
            "航天材料", "太空", "太空机器人", "太空旅游", "太空算力", "太空光伏",
            "火箭", "火箭发射", "可回收火箭", "海上火箭回收", "蓝箭航天",
            "商业航天8大IPO", "广州商业航天", "SpaceX", "spacex", "安徽商业航天",
        ],
        "core_tokens": ["商业航天", "卫星互联网", "SpaceX", "spacex", "火箭发射", "安徽商业航天"],
        "min_members": 3,
        "min_strength_members": 3,
        "min_limit_up_sum": 6,
        "min_continuity": 70.0,
    },
    {
        "name": "data_center",
        "keywords": [
            "数据中心", "液冷数据中心", "数据中心电力设备", "算力", "算力租赁",
            "国产算力", "英伟达算力", "算力基建",
        ],
        "core_tokens": ["数据中心", "液冷数据中心"],
        "min_members": 2,
        "min_strength_members": 2,
        "min_limit_up_sum": 3,
        "min_continuity": 58.0,
    },
    {
        "name": "optical_comm",
        "keywords": [
            "光通信", "光模块", "共封装光学", "CPO", "AI光纤", "光纤光缆",
            "1.6T光模块", "硅光", "光芯片", "光互连",
        ],
        "core_tokens": ["光通信", "光模块", "共封装光学", "CPO", "AI光纤"],
        "min_members": 2,
        "min_strength_members": 2,
        "min_limit_up_sum": 3,
        "min_continuity": 56.0,
    },
]


@dataclass
class ClusterRule:
    name: str
    keywords: list[str] = field(default_factory=list)
    core_tokens: list[str] = field(default_factory=list)
    min_members: int = 2
    min_strength_members: int = 2
    min_limit_up_sum: int = 2
    min_continuity: float = 55.0


@dataclass
class ClusterDecisionInput:
    """聚类补偿所需的最小输入 — 等价于旧链 IdentityDecision 中被 cluster 使用的字段。"""
    subject_key: str
    theme_name: str
    rule_is_main_theme: bool = False
    is_main_theme: bool = False
    identity_status: str = "observed"
    llm_is_main_theme: bool | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def _theme_matcher(tokens: list[str]):
    """关键词匹配器 — 等价于旧链 _theme_matcher。"""
    def _match(theme_name: str) -> bool:
        normalized = (theme_name or "").strip()
        normalized_lower = normalized.lower()
        return any((k in normalized) or (k.lower() in normalized_lower) for k in tokens)
    return _match


class MainlineClusterRegistry:
    """主线聚类规则引擎 — Domain 纯业务逻辑，不依赖 I/O。"""

    def __init__(
        self,
        rules: list[ClusterRule] | None = None,
        bootstrap_enabled: bool = False,
    ) -> None:
        if rules is None:
            rules = [
                ClusterRule(
                    name=r["name"],
                    keywords=list(r.get("keywords") or []),
                    core_tokens=list(r.get("core_tokens") or []),
                    min_members=int(r.get("min_members") or 2),
                    min_strength_members=int(r.get("min_strength_members") or 2),
                    min_limit_up_sum=int(r.get("min_limit_up_sum") or 2),
                    min_continuity=float(r.get("min_continuity") or 55.0),
                )
                for r in DEFAULT_CLUSTER_RULES
            ]
        self._rules = rules
        self._bootstrap_enabled = bootstrap_enabled

    # ── cluster_compensation: 旧链 _apply_cluster_compensation ──

    def apply_cluster_compensation(
        self, decisions: list[ClusterDecisionInput]
    ) -> int:
        """簇级一致性增强。

        对同一簇内满足强度条件的题材，设置 rule_is_main_theme=True。
        等价于旧链 build_mainline_identity_registry.py::_apply_cluster_compensation (L505-571)。
        """
        tagged = 0
        for rule in self._rules:
            is_member = _theme_matcher(rule.keywords)
            is_core = _theme_matcher(rule.core_tokens)
            members = [d for d in decisions if is_member(d.theme_name)]
            if not members:
                continue

            hot_members = [
                d for d in members
                if int(d.evidence.get("active_days_10d") or 0) >= 2
            ]
            strength_members = [
                d for d in members
                if int(d.evidence.get("limit_up_count") or 0) >= 1
                and float(d.evidence.get("mainline_continuity_score") or 0.0) >= 45.0
            ]
            limit_up_sum = sum(
                int(d.evidence.get("limit_up_count") or 0) for d in members
            )
            max_continuity = max(
                float(d.evidence.get("mainline_continuity_score") or 0.0)
                for d in members
            )
            event_presence = any(
                int(d.evidence.get("event_count_3d") or 0) >= 1 for d in members
            )
            flow_presence = any(
                int(d.evidence.get("net_inflow_days_5d") or 0) >= 1 for d in members
            )

            cluster_pass = bool(
                len(members) >= int(rule.min_members)
                and len(hot_members) >= 1
                and len(strength_members) >= int(rule.min_strength_members)
                and limit_up_sum >= int(rule.min_limit_up_sum)
                and max_continuity >= float(rule.min_continuity)
                and event_presence
                and flow_presence
            )
            if not cluster_pass:
                continue

            for d in members:
                one_day_flag = bool(d.evidence.get("one_day_tour_flag"))
                if one_day_flag:
                    continue
                active10 = int(d.evidence.get("active_days_10d") or 0)
                limit_up_count = int(d.evidence.get("limit_up_count") or 0)
                continuity = float(d.evidence.get("mainline_continuity_score") or 0.0)
                core = bool(is_core(d.theme_name))
                if core:
                    member_pass = bool(
                        (active10 >= 1 or limit_up_count >= 1) and continuity >= 42.0
                    )
                else:
                    member_pass = bool(
                        (active10 >= 2 or limit_up_count >= 1) and continuity >= 50.0
                    )
                if not member_pass:
                    continue
                tagged += 1
                d.rule_is_main_theme = True
                d.evidence["cluster_compensation_mainline"] = True
                d.evidence["cluster_compensation_cluster"] = str(rule.name)
                d.evidence["cluster_core_theme"] = core
                d.evidence["cluster_member_count"] = len(members)
                d.evidence["cluster_member_pass"] = True

        return tagged

    # ── cluster_bootstrap_direct_confirm: 旧链 _apply_cluster_bootstrap_direct_confirm ──

    def apply_cluster_bootstrap_direct_confirm(
        self, decisions: list[ClusterDecisionInput]
    ) -> int:
        """历史回填直确认模式。

        对已命中簇规则的题材直接确认为主线。
        等价于旧链 build_mainline_identity_registry.py::_apply_cluster_bootstrap_direct_confirm (L574-607)。
        """
        if not self._bootstrap_enabled or not decisions:
            return 0

        promoted = 0
        for d in decisions:
            cluster_name = ""
            for rule in self._rules:
                if _theme_matcher(rule.keywords)(d.theme_name):
                    cluster_name = str(rule.name)
                    break
            if not cluster_name:
                continue
            d.rule_is_main_theme = True
            d.is_main_theme = True
            d.identity_status = "confirmed"
            if d.llm_is_main_theme is None:
                d.llm_is_main_theme = True
            d.evidence["cluster_bootstrap_direct_confirm"] = True
            d.evidence["cluster_bootstrap_cluster"] = cluster_name
            promoted += 1

        return promoted


__all__ = [
    "ClusterDecisionInput",
    "ClusterRule",
    "DEFAULT_CLUSTER_RULES",
    "MainlineClusterRegistry",
]


# ── Manual Override Config ──

def load_manual_override_config(
    config_path: str | None = None,
) -> dict[str, list[str]]:
    """加载人工覆写配置 — 等价于旧链 _load_manual_override_config (L385-410)。"""
    default = {"subject_keys": [], "theme_name_exact": [], "theme_name_contains": []}
    if not config_path:
        return default
    import json
    from pathlib import Path
    path = Path(config_path) if not isinstance(config_path, Path) else config_path
    if not path.exists():
        return default
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(raw, dict):
        return default
    return {
        "subject_keys": [str(x).strip() for x in (raw.get("subject_keys") or []) if str(x).strip()],
        "theme_name_exact": [str(x).strip() for x in (raw.get("theme_name_exact") or []) if str(x).strip()],
        "theme_name_contains": [str(x).strip() for x in (raw.get("theme_name_contains") or []) if str(x).strip()],
    }


def manual_override_match_reason(
    subject_key: str,
    theme_name: str,
    cfg: dict[str, list[str]],
) -> str | None:
    """匹配手工覆写规则 — 等价于旧链 _manual_override_match_reason (L413-429)。"""
    subject_keys = set(cfg.get("subject_keys") or [])
    exact_names = set(cfg.get("theme_name_exact") or [])
    contains_names = list(cfg.get("theme_name_contains") or [])
    name = (theme_name or "").strip()

    if subject_key in subject_keys:
        return f"subject_key:{subject_key}"
    if name in exact_names:
        return f"theme_name_exact:{name}"
    for token in contains_names:
        if token and token in name:
            return f"theme_name_contains:{token}"
    return None


def apply_manual_mainline_overrides(
    decisions: list[ClusterDecisionInput],
    config_path: str | None = None,
) -> int:
    """人工覆写：强制确认为主线 — 等价于旧链 _apply_manual_mainline_overrides (L432-458)。

    config_path: mainline_manual_overrides.json 的路径。如果为 None 则跳过。
    """
    if not decisions:
        return 0
    cfg = load_manual_override_config(config_path)
    applied = 0
    for d in decisions:
        reason = manual_override_match_reason(d.subject_key, d.theme_name, cfg)
        if not reason:
            continue
        applied += 1
        d.rule_is_main_theme = True
        d.is_main_theme = True
        d.identity_status = "confirmed"
        if d.llm_is_main_theme is None:
            d.llm_is_main_theme = True
        d.evidence["manual_override_mainline"] = True
        d.evidence["manual_override_reason"] = reason
        d.evidence["manual_override_config"] = str(config_path or "")
    return applied

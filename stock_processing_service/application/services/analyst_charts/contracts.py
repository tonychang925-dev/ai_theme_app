"""P2.7/M8.6 — Market Diagnosis Contracts.

Key shift: Score is the RESULT, not the CAUSE.
Analysts observe signals → diagnose → conclude.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ── MarketSignal — the atomic unit of analyst thinking ──

@dataclass(frozen=True, slots=True)
class MarketSignal:
    """A directional signal, not a number.

    Analysts think: "赚钱效应↓↓↓" not "score=-24".
    """
    signal_id: str
    name: str                    # e.g. "赚钱效应", "接力生态", "机构资金"
    direction: str               # UP / DOWN / FLAT
    strength: str                # VERY_STRONG / STRONG / NORMAL / WEAK / VERY_WEAK
    value: float                 # the underlying metric (for reference)
    threshold: float             # what value would flip this signal
    reason: str                  # one-line explanation
    evidence: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if self.direction == "UP":
            if self.strength == "VERY_STRONG": return "↑↑↑"
            if self.strength == "STRONG": return "↑↑"
            if self.strength == "NORMAL": return "↑"
            return "↗"
        if self.direction == "DOWN":
            if self.strength == "VERY_STRONG": return "↓↓↓"
            if self.strength == "STRONG": return "↓↓"
            if self.strength == "NORMAL": return "↓"
            return "↘"
        return "→"


# ── DiagnosisNode — one step in the diagnostic tree ──

@dataclass(frozen=True, slots=True)
class DiagnosisNode:
    """One node in the Market Diagnosis Tree.

    Tree structure: Market → Money → Theme → Leader → Emotion → Strategy.
    """
    step: int
    name: str                    # e.g. "赚钱效应", "接力生态"
    conclusion: str              # one-sentence diagnosis
    signals: tuple[MarketSignal, ...]  # supporting signals
    children: tuple[DiagnosisNode, ...] = ()

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0


# ── ExpectationGap — yesterday's expectation vs today's reality ──

@dataclass(frozen=True, slots=True)
class ExpectationGap:
    """The delta between what was expected and what happened."""
    dimension: str               # e.g. "机器人修复", "市场情绪"
    yesterday_expectation: str
    today_actual: str
    gap_type: str                # CONFIRMED / SURPRISE_POSITIVE / SURPRISE_NEGATIVE / MISSED
    learning: str                # what this gap teaches us


# ── MarketDiagnosis — the complete diagnostic output ──

@dataclass(frozen=True, slots=True)
class MarketDiagnosis:
    """Complete market diagnosis for one trading day.

    This is the root output — charts are just visualization of this.
    """
    trade_date: date

    # ── Diagnostic tree ──
    root: DiagnosisNode

    # ── Expectation gaps ──
    gaps: tuple[ExpectationGap, ...] = ()

    # ── Strategy ──
    trading_mode: str = ""       # 首板试错 / 右侧跟随 / 防守等待 / 回避
    allowed_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    risk_level: str = ""         # LOW / MEDIUM / HIGH / CRITICAL

    # ── Evidence ──
    evidence_summary: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        def _node_dict(n: DiagnosisNode) -> dict:
            return {
                "step": n.step, "name": n.name, "conclusion": n.conclusion,
                "signals": [{
                    "name": s.name, "direction": s.direction,
                    "strength": s.strength, "label": s.label,
                    "reason": s.reason, "value": s.value,
                } for s in n.signals],
                "children": [_node_dict(c) for c in n.children],
            }
        return {
            "trade_date": self.trade_date.isoformat(),
            "diagnosis": _node_dict(self.root),
            "gaps": [{
                "dimension": g.dimension,
                "yesterday_expectation": g.yesterday_expectation,
                "today_actual": g.today_actual,
                "gap_type": g.gap_type,
                "learning": g.learning,
            } for g in self.gaps],
            "trading_mode": self.trading_mode,
            "allowed_actions": list(self.allowed_actions),
            "forbidden_actions": list(self.forbidden_actions),
            "risk_level": self.risk_level,
            "evidence_summary": list(self.evidence_summary),
        }


# ── Direction Lifecycle — per-theme timeline ──

@dataclass(frozen=True, slots=True)
class ThemeLifecycleNode:
    """One observed state in a theme's lifecycle."""
    trade_date: date
    phase: str                   # 启动 / 加速 / 高潮 / 分歧 / 修复 / 退潮
    key_signal: str              # what signaled this phase change
    leader: str = ""             # who was the leader at this point


@dataclass
class ThemeTimeline:
    """A theme's lifecycle timeline across trading days."""
    subject_id: str
    subject_name: str
    nodes: list[ThemeLifecycleNode] = field(default_factory=list)

    @property
    def current_phase(self) -> str:
        return self.nodes[-1].phase if self.nodes else "未知"

    @property
    def phase_duration(self) -> int:
        """Days in current phase."""
        if not self.nodes:
            return 0
        current = self.nodes[-1].phase
        count = 0
        for n in reversed(self.nodes):
            if n.phase == current:
                count += 1
            else:
                break
        return count

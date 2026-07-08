"""M2.5 Phase 3.0 — Causal Narrative Engine.

Converts MarketMetricsSnapshot into analyst-style market narrative.
Rule-driven (not LLM) — every claim is bound to a specific metric.

Architecture:
  MarketMetricsSnapshot → NarrativeEngine → MarketStory
                                            ├── CausalChain
                                            ├── EvidenceNodes
                                            └── StrategyAdvice

Principle: facts before interpretation. Every "why" is backed by a "what".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .contracts import MarketMetricsSnapshot


# ── Narrative contracts ──

@dataclass(frozen=True, slots=True)
class EvidenceNode:
    """A single claim backed by a metric. Analysts can verify."""
    statement: str                   # natural language claim
    metric_name: str                 # registered metric key
    metric_value: float | int | str  # the actual value
    direction: str                   # UP | DOWN | FLAT
    confidence: float                # 0-1 from registry quality

    @property
    def as_dict(self) -> dict:
        return {
            "statement": self.statement,
            "metric": self.metric_name,
            "value": str(self.metric_value),
            "direction": self.direction,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class CausalStep:
    """One step in the market causal chain."""
    from_node: str                   # cause description
    to_node: str                     # effect description
    relation: str                    # causes | boosts | weakens | replaces
    evidence: tuple[EvidenceNode, ...]


@dataclass(frozen=True, slots=True)
class MarketStory:
    """Complete market narrative for one trading day."""
    trade_date: date

    # ── Headline ──
    headline: str                    # one-line summary
    market_phase: str                # 情绪阶段 label

    # ── Story body ──
    sections: tuple[dict, ...]       # ordered narrative sections
    # each: {"title": str, "body": str, "evidence": [EvidenceNode, ...]}

    # ── Causal chain ──
    causal_chain: tuple[CausalStep, ...]

    # ── Strategy ──
    strategy_summary: str
    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    risk_level: str

    # ── Key numbers ──
    key_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date.isoformat(),
            "headline": self.headline,
            "market_phase": self.market_phase,
            "sections": [{
                "title": s["title"],
                "body": s["body"],
                "evidence": [e.as_dict for e in s.get("evidence", [])],
            } for s in self.sections],
            "causal_chain": [{
                "from": cs.from_node,
                "to": cs.to_node,
                "relation": cs.relation,
                "evidence": [e.as_dict for e in cs.evidence],
            } for cs in self.causal_chain],
            "strategy": self.strategy_summary,
            "allowed": list(self.allowed_actions),
            "forbidden": list(self.forbidden_actions),
            "risk_level": self.risk_level,
            "key_metrics": self.key_metrics,
        }


# ── Narrative Engine ──

class NarrativeEngine:
    """Generate analyst-style market narrative from canonical metrics.

    Rules are deterministic and bound to registered metric names.
    This ensures every claim is traceable to its source.
    """

    def generate(self, snap: MarketMetricsSnapshot) -> MarketStory:
        b = snap.breadth
        l = snap.limitup
        r = snap.relay
        c = snap.capital
        m = snap.emotion_momentum
        loss = snap.loss_effect
        leader = snap.leader_evolution
        attr = snap.loss_attribution

        evidence: list[EvidenceNode] = []
        sections: list[dict] = []
        causal_steps: list[CausalStep] = []

        # ═══ Section 1: Market Breadth ═══
        breadth_body, breadth_ev = self._narrate_breadth(b, l)
        evidence.extend(breadth_ev)
        sections.append({"title": "市场环境", "body": breadth_body, "evidence": breadth_ev})

        # ═══ Section 2: Relay Ecology ═══
        relay_body, relay_ev = self._narrate_relay(r, l)
        evidence.extend(relay_ev)
        sections.append({"title": "接力生态", "body": relay_body, "evidence": relay_ev})

        # ═══ Section 3: Leader Status ═══
        leader_body, leader_ev = self._narrate_leader(leader, r)
        evidence.extend(leader_ev)
        sections.append({"title": "龙头状态", "body": leader_body, "evidence": leader_ev})

        # ═══ Section 4: Loss Effect ═══
        loss_body, loss_ev = self._narrate_loss(loss, attr, r)
        evidence.extend(loss_ev)
        sections.append({"title": "亏钱效应", "body": loss_body, "evidence": loss_ev})

        # ═══ Section 5: Capital ═══
        capital_body, capital_ev = self._narrate_capital(c, b)
        evidence.extend(capital_ev)
        sections.append({"title": "资金状态", "body": capital_body, "evidence": capital_ev})

        # ═══ Causal Chain ═══
        causal_steps = self._build_causal_chain(b, l, r, leader, loss, attr)

        # ═══ Headline ═══
        headline = self._build_headline(b, l, r, leader, loss)

        # ═══ Strategy ═══
        strategy, allowed, forbidden, risk = self._build_strategy(r, leader, loss)

        # ═══ Key Metrics ═══
        key_metrics = {
            "涨停": l.total_count,
            "封板": l.sealed_count,
            "炸板": l.fried_board_count,
            "封板率": f"{l.sealed_board_ratio:.0%}",
            "最高板": l.max_board_height,
            "连板": l.chain_board_count,
            "成交额_亿": b.turnover_yi,
            "接力反馈": f"{r.feedback_label}({r.feedback_score:.0f})",
            "龙头健康": f"{leader.leader_health_label}({leader.leader_health_score:.0f})" if leader else "N/A",
            "跌停": loss.limit_down_count if loss else 0,
            "大面": r.yesterday_big_loss_count,
            "情绪动能": f"{m.momentum_normalized:.0f}",
        }

        return MarketStory(
            trade_date=snap.trade_date,
            headline=headline,
            market_phase=self._phase_label(r, leader, loss),
            sections=tuple(sections),
            causal_chain=tuple(causal_steps),
            strategy_summary=strategy,
            allowed_actions=tuple(allowed),
            forbidden_actions=tuple(forbidden),
            risk_level=risk,
            key_metrics=key_metrics,
        )

    # ── Section narrators ──

    def _narrate_breadth(self, b, l) -> tuple[str, list[EvidenceNode]]:
        ev = [
            EvidenceNode(f"涨停{l.total_count}家，跌停{b.limit_down_count}家", "limit_up_total_count", l.total_count, "FLAT", 0.95),
            EvidenceNode(f"上涨{b.up_count}/下跌{b.down_count}，上涨比{b.up_ratio:.0%}", "market_up_ratio", b.up_ratio, "UP" if b.up_ratio > 0.5 else "DOWN", 0.75),
        ]
        if l.sealed_board_ratio >= 0.8:
            body = f"涨停{l.total_count}家，封板率{l.sealed_board_ratio:.0%}，封板质量良好。涨跌比{b.up_count}/{b.down_count}，市场赚钱效应尚可。"
        elif l.sealed_board_ratio >= 0.5:
            body = f"涨停{l.total_count}家，封板率{l.sealed_board_ratio:.0%}，封板质量一般，存在分歧。涨跌比{b.up_count}/{b.down_count}。"
        else:
            body = f"涨停仅{l.total_count}家，封板率低至{l.sealed_board_ratio:.0%}，炸板{l.fried_board_count}只。涨跌比{b.up_count}/{b.down_count}，市场赚钱效应弱。"
        return body, ev

    def _narrate_relay(self, r, l) -> tuple[str, list[EvidenceNode]]:
        ev = [
            EvidenceNode(f"接力反馈: {r.feedback_label}({r.feedback_score:.0f})", "limitup_feedback_score", r.feedback_score, "UP" if r.feedback_score > 0 else "DOWN", 0.75),
            EvidenceNode(f"一进二{r.promotion_1_to_2:.0%}，二进三{r.promotion_2_to_3:.0%}", "promotion_1_to_2", r.promotion_1_to_2, "FLAT", 0.85),
        ]
        if r.feedback_score >= 40:
            body = f"接力生态强劲。昨涨停{r.yesterday_limitup_count}只，今日继续涨停{r.today_continue_count}只（{r.continue_ratio:.0%}），反馈{r.feedback_label}。赚钱效应正向扩散。"
        elif r.feedback_score >= 0:
            body = f"接力正常。昨涨停反馈{r.feedback_label}，继续率{r.continue_ratio:.0%}。晋级率1→2={r.promotion_1_to_2:.0%}。"
        elif r.feedback_score >= -30:
            body = f"接力转弱。昨涨停反馈{r.feedback_label}，大面{r.yesterday_big_loss_count}只。接力资金开始亏钱，最高{r.max_board_height}板高度受限。"
        else:
            body = f"接力崩塌。昨涨停反馈{r.feedback_label}，大面{r.yesterday_big_loss_count}只，继续率仅{r.continue_ratio:.0%}。高度严重压制，应回避接力。"
        return body, ev

    def _narrate_leader(self, leader, r) -> tuple[str, list[EvidenceNode]]:
        if not leader or not leader.leaders:
            return "今日无明显龙头。连板生态薄弱，市场缺乏方向感。", []
        ev = [
            EvidenceNode(f"龙头健康: {leader.leader_health_label}({leader.leader_health_score:.0f})", "leader_health_score", leader.leader_health_score, "FLAT", 0.80),
            EvidenceNode(f"延续{leader.continue_count}/弱化{leader.weaken_expected_count + leader.weaken_unexpected_count}/断板{leader.break_count}", "leader_health_score", leader.continue_count, "FLAT", 0.80),
        ]
        top_leaders = [l for l in leader.leaders if l.status in ("SUPER_CONTINUE", "NORMAL_CONTINUE", "NEW")][:3]
        broken = [l for l in leader.leaders if l.status == "BREAK"][:2]
        weak = [l for l in leader.leaders if "WEAKEN" in l.status][:2]

        parts = []
        if top_leaders:
            names = "、".join(f"{l.stock_name}({l.board_height}板,{l.status})" for l in top_leaders)
            parts.append(f"强势龙头: {names}")
        if weak:
            names = "、".join(f"{l.stock_name}({l.reason})" for l in weak)
            parts.append(f"弱化龙头: {names}")
        if broken:
            names = "、".join(f"{l.stock_name}({l.reason})" for l in broken)
            parts.append(f"断板龙头: {names}")

        if leader.leader_health_label == "COLLAPSE":
            parts.append("龙头全面崩溃，市场进入无序状态。")
        elif leader.leader_break_alert:
            parts.append(f"龙头断板警报：{leader.break_count}/{leader.yesterday_leader_count}只高标断板。")

        return "。".join(parts) + "。", ev

    def _narrate_loss(self, loss, attr, r) -> tuple[str, list[EvidenceNode]]:
        if not loss or loss.limit_down_count == 0:
            return "今日无明显亏钱效应。", []
        ev = [
            EvidenceNode(f"跌停{loss.limit_down_count}家", "limit_down_count", loss.limit_down_count, "DOWN" if loss.limit_down_count > 20 else "FLAT", 0.85),
        ]
        parts = [f"跌停{loss.limit_down_count}家，亏钱效应{loss.loss_effect_label}。"]
        if attr:
            if attr.concentrated_leader:
                parts.append(f"亏损集中于高位龙头，龙头断板{attr.leader_loss_count}只。")
            if attr.concentrated_high_board:
                parts.append(f"高位连板股亏损{attr.high_board_loss_count}只，退潮扩散。")
            if attr.primary_loss_theme:
                parts.append(f"主要亏损方向: {attr.primary_loss_theme}({attr.primary_loss_count}只)。")
            if attr.loss_conclusion:
                parts.append(attr.loss_conclusion)
        return "".join(parts), ev

    def _narrate_capital(self, c, b) -> tuple[str, list[EvidenceNode]]:
        turnover_wan_yi = b.turnover_yi / 10000
        ev = [
            EvidenceNode(f"全市场成交{turnover_wan_yi:.2f}万亿", "market_turnover_yi", b.turnover_yi, "FLAT", 0.75),
            EvidenceNode(f"活跃资金占比{c.active_ratio:.1%}", "active_capital_ratio", c.active_ratio, "UP" if c.active_ratio > 0.04 else "DOWN", 0.80),
        ]
        if c.active_ratio > 0.05:
            body = f"成交{turnover_wan_yi:.2f}万亿，活跃资金占比{c.active_ratio:.1%}，资金充裕。"
        elif c.active_ratio > 0.03:
            body = f"成交{turnover_wan_yi:.2f}万亿，活跃资金{c.active_ratio:.1%}，资金正常。"
        else:
            body = f"成交{turnover_wan_yi:.2f}万亿，活跃资金仅{c.active_ratio:.1%}，资金收缩。"
        return body, ev

    # ── Causal chain builder ──

    def _build_causal_chain(self, b, l, r, leader, loss, attr) -> list[CausalStep]:
        chain: list[CausalStep] = []

        # 1: Leader → Relay
        if leader and leader.break_alert:
            chain.append(CausalStep(
                from_node=f"龙头断板({leader.break_count}/{leader.yesterday_leader_count}只高标断裂)",
                to_node=f"接力情绪下降(反馈{r.feedback_label})",
                relation="causes",
                evidence=(EvidenceNode(f"龙头断板{leader.break_count}只", "leader_break_alert", True, "DOWN", 0.80),),
            ))

        # 2: Relay → Sentiment
        if r.feedback_score < -20:
            chain.append(CausalStep(
                from_node=f"接力反馈{r.feedback_label}({r.feedback_score:.0f})",
                to_node="短线资金亏钱效应扩散" if (loss and loss.loss_effect_label in ("严重", "恐慌")) else "短线情绪转谨慎",
                relation="causes",
                evidence=(EvidenceNode(f"反馈分数{r.feedback_score:.0f}", "limitup_feedback_score", r.feedback_score, "DOWN", 0.75),),
            ))

        # 3: Loss → Risk
        if loss and loss.loss_effect_label in ("明显", "严重", "恐慌"):
            chain.append(CausalStep(
                from_node=f"亏钱效应{loss.loss_effect_label}(跌停{loss.limit_down_count})",
                to_node="市场风险升级，应降低仓位" if loss.loss_effect_label == "恐慌" else "警惕退潮扩散",
                relation="boosts",
                evidence=(EvidenceNode(f"跌停{loss.limit_down_count}家", "limit_down_count", loss.limit_down_count, "DOWN", 0.85),),
            ))

        # 4: Sealed → Confidence
        if l.sealed_board_ratio < 0.5:
            chain.append(CausalStep(
                from_node=f"封板率低({l.sealed_board_ratio:.0%})",
                to_node="市场分歧大，资金不认同当前方向",
                relation="weakens",
                evidence=(EvidenceNode(f"封板率{l.sealed_board_ratio:.0%}", "limit_up_sealed_ratio", l.sealed_board_ratio, "DOWN", 0.95),),
            ))

        # 5: Breadth → Environment
        if b.limit_up_count < 30:
            chain.append(CausalStep(
                from_node=f"涨停仅{b.limit_up_count}家",
                to_node="市场情绪处于低谷，缺乏做多方向",
                relation="causes",
                evidence=(EvidenceNode(f"涨停{b.limit_up_count}家", "limit_up_total_count", b.limit_up_count, "DOWN", 0.95),),
            ))

        return chain

    # ── Headline ──

    def _build_headline(self, b, l, r, leader, loss) -> str:
        phase = self._phase_label(r, leader, loss)
        if phase == "恐慌/冰点":
            return f"市场进入{phase}：跌停{(loss or _empty()).limit_down_count}家，应全面防守"
        elif phase == "退潮":
            return f"市场持续退潮：龙头松动，接力反馈{r.feedback_label}"
        elif phase == "分歧":
            return f"市场分歧加大：封板率{l.sealed_board_ratio:.0%}，需等待方向明确"
        elif phase == "修复":
            return f"市场进入修复：涨停{l.total_count}家，接力情绪回暖"
        elif phase == "强势":
            return f"市场强势：涨停{l.total_count}家，龙头{l.max_board_height}板延续"
        else:
            return f"市场混沌：涨停{l.total_count}家，方向分散"

    def _phase_label(self, r, leader, loss) -> str:
        fb = r.feedback_score
        if loss and loss.loss_effect_label == "恐慌":
            return "恐慌/冰点"
        if leader and leader.leader_health_label == "COLLAPSE":
            return "退潮"
        if fb < -40:
            return "退潮"
        if fb < -10:
            return "分歧"
        if fb < 20:
            return "混沌"
        if fb < 50:
            return "修复"
        return "强势"

    # ── Strategy ──

    def _build_strategy(self, r, leader, loss) -> tuple[str, tuple, tuple, str]:
        fb = r.feedback_score
        if (loss and loss.loss_effect_label == "恐慌") or fb < -60:
            return ("全面防守。不买任何短线品种，只观察不操作。",
                    ("观察",), ("接力", "追高", "打板", "低吸", "重仓"), "CRITICAL")
        if fb < -30 or (leader and leader.leader_health_label == "COLLAPSE"):
            return ("防守等待。耐心等待龙头修复或新周期启动，不做后排。",
                    ("首板", "新题材观察"), ("接力", "追龙头", "重仓"), "HIGH")
        if fb < 0:
            return ("谨慎参与。只做主线首板试错，回避高标接力。",
                    ("首板", "龙头低吸", "趋势"), ("接力", "追高"), "MEDIUM")
        if fb < 30:
            return ("正常参与。关注龙头晋级和主线延续，控制仓位。",
                    ("龙头", "首板", "趋势", "补涨"), ("追高",), "MEDIUM")
        return ("积极参与。接力生态良好，可做龙头接力+低位补涨。",
                ("龙头接力", "首板", "趋势", "补涨"), (), "LOW")


def _empty():
    return type("_E", (), {"limit_down_count": 0})()

"""M8.6 — Market Diagnosis Engine.

Replaces flat chart builders with a diagnostic tree:
  Market → Money → Theme → Leader → Emotion → Strategy

Key principle: Signals before scores. Score is the RESULT, not the CAUSE.
Analysts observe signals ("赚钱效应↓↓↓") not numbers ("score=-24").

Output: MarketDiagnosis (facts → reasons → evidence → gaps → strategy).
Charts are just visualization of the diagnosis.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from .contracts import (
    DiagnosisNode,
    ExpectationGap,
    MarketDiagnosis,
    MarketSignal,
)


# ── Signal strength thresholds ──

def _signal_strength(value: float, thresholds: dict[str, float], direction: str) -> tuple[str, str]:
    """Map a value to (direction, strength) using thresholds.

    thresholds: {VERY_STRONG: cutoff, STRONG: cutoff, ...} with higher = stronger.
    """
    if direction == "UP":
        if value >= thresholds.get("VERY_STRONG", 80): return ("UP", "VERY_STRONG")
        if value >= thresholds.get("STRONG", 60): return ("UP", "STRONG")
        if value >= thresholds.get("NORMAL", 40): return ("UP", "NORMAL")
        if value >= thresholds.get("WEAK", 20): return ("UP", "WEAK")
        return ("FLAT", "NORMAL")
    else:  # DOWN
        if value <= thresholds.get("VERY_STRONG", -60): return ("DOWN", "VERY_STRONG")
        if value <= thresholds.get("STRONG", -40): return ("DOWN", "STRONG")
        if value <= thresholds.get("NORMAL", -20): return ("DOWN", "NORMAL")
        if value <= thresholds.get("WEAK", -5): return ("DOWN", "WEAK")
        return ("FLAT", "NORMAL")


class DiagnosisEngine:
    """Produce a MarketDiagnosis tree from DB data.

    The diagnostic tree follows analyst thinking:
      Step 1: Market Breadth (市场环境) → 赚钱效应 direction
      Step 2: Money Flow (资金偏好) → 活跃资金 direction
      Step 3: Relay Ecology (接力生态) → 连板 direction
      Step 4: Leader Status (龙头状态) → 龙头 health
      Step 5: Theme Rhythm (板块节奏) → 方向 lifecycle
      Step 6: Emotion Phase (情绪阶段) → ICE_POINT/REPAIR/etc.
      Step 7: Strategy (交易模式) → what to do
    """

    def run(self, trade_date: date) -> MarketDiagnosis:
        return asyncio.run(self._run_async(trade_date))

    async def run_async(self, trade_date: date) -> MarketDiagnosis:
        from stock_processing_service.application.services.market_metrics.service import (
            MarketMetricsService,
        )
        from stock_processing_service.application.services.market_metrics.contracts import display_amount

        # ── Load canonical facts (single source of truth) ──
        snap = await MarketMetricsService().get_async(trade_date)
        b = snap.breadth; l = snap.limitup; c = snap.capital; m = snap.emotion_momentum; r = snap.relay

        # ── Step 1: Market Breadth ──
        breadth_value = int((b.up_ratio - 0.5) * 200 + (b.limit_up_count - 50) * 0.5 - (b.limit_down_count - 20) * 1.0)
        b_dir, b_str = _signal_strength(breadth_value,
            {"VERY_STRONG":60,"STRONG":30,"NORMAL":0,"WEAK":-30}, "UP" if breadth_value >= 0 else "DOWN")
        breadth_signal = MarketSignal(
            signal_id=f"breadth_{trade_date.isoformat()}", name="赚钱效应",
            direction=b_dir, strength=b_str, value=breadth_value, threshold=0,
            reason=f"涨停{b.limit_up_count}家，涨跌比{b.up_count}/{b.down_count}({b.up_ratio:.0%})",
        )

        # ── Step 2: Money Flow ──
        money_value = int((c.active_ratio - 0.03) * 500 + (b.limit_up_count - 80) * 0.3)
        m_dir, m_str = _signal_strength(money_value,
            {"VERY_STRONG":40,"STRONG":15,"NORMAL":-10,"WEAK":-30}, "UP" if money_value >= 0 else "DOWN")
        money_signal = MarketSignal(
            signal_id=f"money_{trade_date.isoformat()}", name="活跃资金",
            direction=m_dir, strength=m_str, value=money_value, threshold=0,
            reason=f"全市场{display_amount(c.total_turnover_yi)}，活跃资金{display_amount(c.active_limitup_amount_yi)}",
        )

        # ── Step 3: Relay Ecology ──
        relay_value = int((l.max_board_height - 3) * 30 + (b.limit_up_count - 80) * 0.2)
        r_dir, r_str = _signal_strength(relay_value,
            {"VERY_STRONG":40,"STRONG":10,"NORMAL":-20,"WEAK":-40}, "UP" if relay_value >= 0 else "DOWN")
        relay_signal = MarketSignal(
            signal_id=f"relay_{trade_date.isoformat()}", name="接力生态",
            direction=r_dir, strength=r_str, value=relay_value, threshold=0,
            reason=f"最高{l.max_board_height}板，连板{l.chain_board_count}只，涨停{b.limit_up_count}家",
        )

        # ── Step 4: Leader Status ──
        has_leader = l.chain_board_count >= 2  # 连板 >= 2 implies leader exists
        leader_value = 30 if has_leader else -30
        l_dir, l_str = ("UP", "STRONG") if has_leader else ("DOWN", "WEAK")
        leader_signal = MarketSignal(
            signal_id=f"leader_{trade_date.isoformat()}", name="龙头状态",
            direction=l_dir, strength=l_str, value=leader_value, threshold=0,
            reason=f"连板{l.chain_board_count}只，最高{l.max_board_height}板" if has_leader else "无明显龙头",
        )

        # ── Step 5: Theme Rhythm ──
        theme_value = 20 if b.limit_up_count > 30 else -10
        t_dir, t_str = ("UP", "NORMAL") if b.limit_up_count > 30 else ("FLAT", "NORMAL")
        theme_signal = MarketSignal(
            signal_id=f"theme_{trade_date.isoformat()}", name="板块节奏",
            direction=t_dir, strength=t_str, value=theme_value, threshold=0,
            reason=f"涨停{b.limit_up_count}家，连板{l.chain_board_count}只",
        )

        # ── Step 6: Emotion Phase ──
        # Emotion = breadth (40%) + momentum (25%) + relay (20%) + capital (15%)
        # Breadth dominates because 赚钱效应 is the primary driver of market emotion
        capital_value = int((c.active_ratio - 0.03) * 500)
        composite = int(m.momentum_normalized * 0.25 + breadth_value * 0.40 + relay_value * 0.20 + capital_value * 0.15)

        if composite >= 50:      node, node_desc = "CLIMAX", "情绪高潮"
        elif composite >= 20:    node, node_desc = "ACCELERATION", "情绪加速"
        elif composite >= 0:     node, node_desc = "FERMENTATION", "情绪发酵"
        elif composite >= -20:   node, node_desc = "REPAIR", "情绪修复"
        elif composite >= -40:   node, node_desc = "DIVERGENCE", "情绪分歧"
        elif composite >= -60:   node, node_desc = "FADE", "情绪退潮"
        else:                    node, node_desc = "ICE_POINT", "情绪冰点"

        e_dir, e_str = _signal_strength(composite,
            {"VERY_STRONG":50,"STRONG":20,"NORMAL":-10,"WEAK":-40}, "UP" if composite >= 0 else "DOWN")
        emotion_signal = MarketSignal(
            signal_id=f"emotion_{trade_date.isoformat()}", name="情绪阶段",
            direction=e_dir, strength=e_str, value=composite, threshold=0,
            reason=f"{node_desc}（{node}）",
            evidence=tuple([
                f"赚钱效应: {breadth_signal.label} ({breadth_signal.reason})",
                f"活跃资金: {money_signal.label} ({money_signal.reason})",
                f"接力生态: {relay_signal.label} ({relay_signal.reason})",
                f"龙头状态: {leader_signal.label} ({leader_signal.reason})",
                f"板块节奏: {theme_signal.label} ({theme_signal.reason})",
            ]),
        )

        # ── Step 7: Strategy ──
        if node in ("ICE_POINT",):
            mode = "首板试错"; allowed = ("首板", "新题材观察", "低吸"); forbidden = ("高位接力", "追龙头", "打连板"); risk = "HIGH"
        elif node in ("REPAIR", "FERMENTATION"):
            mode = "右侧跟随"; allowed = ("龙头", "趋势", "首板"); forbidden = ("追高",); risk = "MEDIUM"
        elif node in ("ACCELERATION", "CLIMAX"):
            mode = "防守等分歧"; allowed = ("低位补涨", "趋势"); forbidden = ("追龙头", "高位接力"); risk = "MEDIUM"
        elif node in ("DIVERGENCE", "FADE"):
            mode = "防守观望"; allowed = ("首板", "观察"); forbidden = ("接力", "追高", "重仓"); risk = "HIGH"
        else:
            mode = "轻仓等待"; allowed = ("观察",); forbidden = ("重仓",); risk = "HIGH"

        # ── Build diagnostic tree ──
        step6 = DiagnosisNode(step=6, name="情绪阶段", conclusion=f"{node_desc}（{node}）", signals=(emotion_signal,))
        step5 = DiagnosisNode(step=5, name="板块节奏", conclusion=f"涨停{b.limit_up_count}家，{t_dir}", signals=(theme_signal,), children=(step6,))
        step4 = DiagnosisNode(step=4, name="龙头状态", conclusion="有明确龙头" if has_leader else "无明显龙头", signals=(leader_signal,), children=(step5,))
        step3 = DiagnosisNode(step=3, name="接力生态", conclusion=f"最高{l.max_board_height}板，{r_dir}", signals=(relay_signal,), children=(step4,))
        step2 = DiagnosisNode(step=2, name="资金偏好", conclusion=f"全市场{display_amount(c.total_turnover_yi)}", signals=(money_signal,), children=(step3,))
        step1 = DiagnosisNode(step=1, name="市场环境", conclusion=f"赚钱效应{b_dir}（涨停{b.limit_up_count}家）", signals=(breadth_signal,), children=(step2,))

        evidence = tuple(s.reason for s in (breadth_signal, money_signal, relay_signal, leader_signal, theme_signal, emotion_signal))

        return MarketDiagnosis(
            trade_date=trade_date,
            root=step1,
            trading_mode=mode, allowed_actions=allowed, forbidden_actions=forbidden,
            risk_level=risk, evidence_summary=evidence,
        )


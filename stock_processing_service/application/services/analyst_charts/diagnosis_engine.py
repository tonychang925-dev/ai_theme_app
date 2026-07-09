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
        # v2: feedback_score (接力反馈分数) weights more than board height alone
        fb = snap.relay.feedback_score
        relay_value = int((l.max_board_height - 3) * 20 + fb * 0.4 + (b.limit_up_count - 80) * 0.2)
        r_dir, r_str = _signal_strength(relay_value,
            {"VERY_STRONG":40,"STRONG":10,"NORMAL":-20,"WEAK":-40}, "UP" if relay_value >= 0 else "DOWN")
        fb_reason = f"，反馈{snap.relay.feedback_label}({fb:.0f})" if fb != 0 else ""
        relay_signal = MarketSignal(
            signal_id=f"relay_{trade_date.isoformat()}", name="接力生态",
            direction=r_dir, strength=r_str, value=relay_value, threshold=0,
            reason=f"最高{l.max_board_height}板，连板{l.chain_board_count}只{fb_reason}",
            evidence=tuple([
                f"晋级率: 1→2={snap.relay.promotion_1_to_2:.0%}, 2→3={snap.relay.promotion_2_to_3:.0%}",
                f"昨涨停{snap.relay.yesterday_limitup_count}只，今继续{snap.relay.continue_ratio:.0%}",
                f"大面{snap.relay.yesterday_big_loss_count}只，反馈{snap.relay.feedback_label}",
            ]),
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

        # ── Step 6: Emotion Phase (v4: short-term trading ecology) ──
        # Recalibrated: analyst focus is 接力>龙头>亏钱>质量>宽度
        # NOT market breadth dominated
        loss = snap.loss_effect
        loss_penalty = int(loss.loss_effect_score * 0.8) if loss else 0
        leader = snap.leader_evolution
        leader_contribution = int((leader.leader_health_score - 50) * 0.8) if leader else 0
        death = snap.high_position_death
        death_penalty = int(death.death_index * 0.6) if death else 0

        # Board quality: penalize low sealed ratio, reward high quality
        sealed_quality = int((l.sealed_board_ratio - 0.5) * 200)  # -100 to +100

        composite = int(
            relay_value * 0.30                    # 接力生态 30%
            + leader_contribution * 0.25          # 龙头状态 25%
            - loss_penalty * 0.20                 # 亏钱效应 20%
            + sealed_quality * 0.15               # 涨停质量 15%
            + breadth_value * 0.10                # 市场宽度 10%
            - death_penalty * 0.10                # 高位死亡惩罚
        )

        # ── 10-phase ontology v2 ──
        if composite >= 60 and (loss is None or loss.loss_effect_label == "安全"):
            node, node_desc = "CLIMAX", "情绪高潮"
        elif composite >= 35:
            node, node_desc = "ACCELERATION", "情绪加速"
        elif composite >= 15:
            node, node_desc = "FERMENTATION", "情绪发酵"
        elif composite >= 5:
            node, node_desc = "START", "情绪启动"
        elif composite >= -10:
            node, node_desc = "REPAIR", "情绪修复"
        elif composite >= -25:
            node, node_desc = "FIRST_DIVERGENCE", "第一次分歧"
        elif composite >= -45:
            node, node_desc = "DISTRIBUTION", "高位派发/退潮"
        elif composite >= -65:
            # Distinguish PANIC from FREEZE
            if death and death.death_label == "CRITICAL":
                node, node_desc = "PANIC", "恐慌释放"
            else:
                node, node_desc = "FREEZE", "情绪冰点"
        else:
            node, node_desc = "PANIC", "恐慌"

        # SECOND_WAVE detection: repair followed by re-breaking
        # (requires historical state; stub for now)

        e_dir, e_str = _signal_strength(composite,
            {"VERY_STRONG":50,"STRONG":20,"NORMAL":-10,"WEAK":-40}, "UP" if composite >= 0 else "DOWN")
        loss_desc = ""
        if loss and loss.loss_effect_label != "安全":
            loss_desc = f"，亏钱{loss.loss_effect_label}(跌停{loss.limit_down_count}，大面{loss.big_loss_count})"
        if leader and leader.avg_surprise_score < -20:
            loss_desc += f"，龙头低于预期(avg_surprise={leader.avg_surprise_score:.0f})"

        attr = snap.loss_attribution
        att_desc = attr.loss_conclusion if attr else ""

        emotion_signal = MarketSignal(
            signal_id=f"emotion_{trade_date.isoformat()}", name="情绪阶段",
            direction=e_dir, strength=e_str, value=composite, threshold=0,
            reason=f"{node_desc}（{node}）{loss_desc}",
            evidence=tuple([
                f"赚钱效应: {breadth_signal.label} ({breadth_signal.reason})",
                f"接力生态: {relay_signal.label} ({relay_signal.reason})",
                f"龙头状态: {leader_signal.label} ({leader_signal.reason})",
                f"龙头预期差: avg_surprise={leader.avg_surprise_score:.0f}" if leader else "龙头预期差: 无数据",
                f"亏钱效应: {loss.loss_effect_label}(跌停{loss.limit_down_count},大面{loss.big_loss_count})" if loss else "亏钱效应: 无数据",
                f"亏钱归因: {att_desc}" if att_desc else "亏钱归因: 无数据",
            ]),
        )

        # ── Step 7: Strategy ──
        # Death index escalation: override to PANIC when high position death is CRITICAL
        if death and death.risk_escalation and node not in ("PANIC", "FREEZE"):
            node = "PANIC"
            node_desc = "恐慌（高位核心死亡驱动）"

        if node in ("PANIC", "FREEZE"):
            mode = "全面防守"; allowed = ("观察",); forbidden = ("接力", "追高", "打板", "低吸", "重仓"); risk = "CRITICAL"
        elif node in ("ICE_POINT",):
            mode = "首板试错"; allowed = ("首板", "新题材观察", "低吸"); forbidden = ("高位接力", "追龙头", "打连板"); risk = "HIGH"
        elif node in ("REPAIR", "FERMENTATION", "START"):
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


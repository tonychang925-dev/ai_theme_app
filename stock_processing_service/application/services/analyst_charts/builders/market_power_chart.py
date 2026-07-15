"""Chart 1: Market Power 大盘势能 — PDF page 4.

Calibrated against analyst 7/1-7/9 data. Score range: -10 to +10.

Analyst methodology (from 7月9日复盘_DeepSeek完整结构版.md §4):
  Indicators: 涨停数, 连板股, 大盘上涨比, 亏钱效应比(在-5下个股数/涨停数)
  The loss_effect_ratio is the dominant signal — it captures asymmetric punishment.

Our adaptation:
  - Use existing LossEffectMetrics (damage_ratio, loss_effect_score) as proxy
  - loss_effect_score is a 0-100 composite (higher=worse)
  - When loss_effect unavailable, fall back to down_ratio penalty
"""

from __future__ import annotations

from typing import Any


def build(up_count: int, down_count: int, limit_up: int, limit_down: int,
          turnover_yi: float, chain_board_count: int = 0,
          calibrated_lu: int | None = None, calibrated_turnover: float | None = None,
          calibrated_emotion: str | None = None,
          loss_effect: Any = None) -> dict[str, Any]:
    """Build market breadth chart data.

    Args:
        loss_effect: Optional LossEffectMetrics with loss_effect_score (0-100, higher=worse),
                     total_damage_count, damage_ratio.

    Formula (range -10 to +10):
      score = limit_up_bonus + up_ratio_bonus + chain_bonus - loss_penalty
    """
    limit_up_final = calibrated_lu if calibrated_lu else limit_up
    turnover_final = calibrated_turnover if calibrated_turnover else turnover_yi

    if turnover_final >= 10000:
        turnover_display = f"{turnover_final / 10000:.2f}万亿"
    else:
        turnover_display = f"{turnover_final:.0f}亿"

    total = up_count + down_count or 1
    up_ratio = round(up_count / total, 3)

    # ── Positive components ──
    limit_up_bonus = round((limit_up_final - 50) / 20, 1)        # neutral=50
    up_ratio_bonus = round((up_ratio - 0.40) * 15, 1)           # neutral=40%
    chain_bonus = round((chain_board_count - 8) / 4, 1)          # neutral=8

    # ── Negative: 亏钱效应 penalty ──
    # Analyst methodology (§4): 亏钱效应比 = stocks_below_neg5 / limit_up_count
    # Our proxy: damage_ratio = total_damage_count / limit_up_count
    # The loss_ratio is the dominant signal — it modulates the positive bonuses
    # and adds a base penalty proportionate to market damage.
    if loss_effect is not None:
        damage_count = getattr(loss_effect, 'total_damage_count', 0) or 0
        damage_ratio = damage_count / max(limit_up_final, 1)

        # Multiplicative discount: healthy market gets full credit,
        # damaged market discounts positive signals heavily
        if damage_ratio <= 1.5:
            discount = 1.0
        elif damage_ratio <= 3.0:
            discount = 0.7
        elif damage_ratio <= 6.0:
            discount = 0.35
        else:
            discount = 0.0

        # Base loss penalty: damage_proportion drives the penalty
        loss_penalty = round(min(8.0, max(0, (damage_ratio - 1.0)) * 0.6), 1)

        positives = (limit_up_bonus + up_ratio_bonus + chain_bonus) * discount
    else:
        # Fallback: simple down_ratio penalty when loss_effect unavailable
        down_ratio = down_count / total
        loss_penalty = round(max(0, (down_ratio - 0.50) * 10), 1)
        positives = limit_up_bonus + up_ratio_bonus + chain_bonus

    score = int(positives - loss_penalty)
    score = max(-10, min(10, score))  # clamp to -10..10

    if score >= 6:    label = "强势"
    elif score >= 2:  label = "修复"
    elif score >= -1: label = "混沌"
    elif score >= -5: label = "分歧"
    else:             label = "退潮/冰点"

    # Build evidence
    evidence = [
        f"涨停{limit_up_final}家，跌停{limit_down}家",
        f"上涨{up_count}/下跌{down_count}，上涨比{up_ratio:.1%}",
        f"成交额{turnover_display}",
        f"连板{chain_board_count}只",
    ]
    if loss_effect is not None:
        evidence.append(
            f"亏钱效应比{damage_ratio:.1f} "
            f"(跌停{getattr(loss_effect, 'limit_down_count', 0)}"
            f"+大面{getattr(loss_effect, 'big_loss_count', 0)})"
        )

    interpretation = (
        f"大盘势能：{label}（评分{score}）。"
        + (f"涨停{limit_up_final}家，赚钱效应强。" if score >= 2
           else f"涨停仅{limit_up_final}家，亏钱效应扩散，市场偏弱。" if score <= -2
           else "市场混沌，方向不明。")
    )

    return {
        "chart_type": "market_breadth",
        "title": "大盘势能",
        "module": "emotion",
        "data": {
            "up_count": up_count, "down_count": down_count,
            "up_ratio": up_ratio,
            "limit_up_count": limit_up_final,
            "limit_down_count": limit_down,
            "chain_board_count": chain_board_count,
            "turnover_yi": turnover_final,
            "turnover_display": turnover_display,
            "turnover_wan_yi": round(turnover_final / 10_000, 2),
            "composite_score": score,
            "components": {
                "limit_up_bonus": limit_up_bonus,
                "up_ratio_bonus": up_ratio_bonus,
                "chain_bonus": chain_bonus,
                "loss_penalty": -loss_penalty,
            },
            "label": label,
            "calibrated": calibrated_lu is not None or calibrated_emotion is not None,
        },
        "interpretation": interpretation,
        "evidence_refs": tuple(evidence),
    }

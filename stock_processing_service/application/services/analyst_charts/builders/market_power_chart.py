"""Chart 1: Market Power 大盘势能 — PDF page 4.

Calibrated against analyst 7/1-7/8 data. Score range: -10 to +10.
Formula reverse-engineered from analyst's composite:
  positive: limit_up, up_ratio, chain_board
  negative: down_ratio, loss_effect
"""

from typing import Any


def build(up_count: int, down_count: int, limit_up: int, limit_down: int,
          turnover_yi: float, chain_board_count: int = 0,
          calibrated_lu: int | None = None, calibrated_turnover: float | None = None,
          calibrated_emotion: str | None = None) -> dict[str, Any]:
    """Build market breadth chart data.

    Analyst-calibrated formula (range -10 to +10):
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

    # Calibrated scoring (analyst scale: -10 to +10)
    # Verified: 7/1(151ZT,0.77up)≈6, 7/7(33ZT,0.12up)≈-6
    limit_up_bonus = round((limit_up_final - 50) / 20, 1)        # 50=neutral, /20=scale
    up_ratio_bonus = round((up_ratio - 0.40) * 15, 1)           # 0.40=neutral
    chain_bonus = round((chain_board_count - 8) / 4, 1)          # 8=neutral
    loss_penalty = round((down_count / total) * 5, 1)            # down ratio penalty

    score = int(limit_up_bonus + up_ratio_bonus + chain_bonus - loss_penalty)
    score = max(-10, min(10, score))  # clamp to -10..10

    if score >= 6:    label = "强势"
    elif score >= 2:  label = "修复"
    elif score >= -1: label = "混沌"
    elif score >= -5: label = "分歧"
    else:             label = "退潮/冰点"

    evidence = [
        f"涨停{limit_up_final}家，跌停{limit_down}家",
        f"上涨{up_count}/下跌{down_count}，上涨比{up_ratio:.1%}",
        f"成交额{turnover_display}",
        f"连板{chain_board_count}只",
    ]

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

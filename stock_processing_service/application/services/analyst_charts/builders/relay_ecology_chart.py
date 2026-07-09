"""Chart 4: Relay Ecology 核心板块节律 — PDF page 6.

v2: includes LimitUp Feedback Score from yesterday cross-reference.
"""

from typing import Any


def build(max_board_height: int, first_board_success_rate: float,
          promotion_1_to_2: float, promotion_2_to_3: float, promotion_3_to_4: float,
          feedback_score: float = 0.0, feedback_label: str = "",
          continue_ratio: float = 0.0, yesterday_count: int = 0,
          big_loss_count: int = 0,
          board_groups: list[dict] | None = None) -> dict[str, Any]:
    """Build relay ecology chart with promotion rates + feedback score."""

    # Multi-condition label: feedback_score + promotion + max_height
    if feedback_score < -30:
        r_label = "接力崩塌"
    elif promotion_1_to_2 < 0.10:
        r_label = "接力冻结"
    elif promotion_1_to_2 < 0.20:
        r_label = "接力退潮"
    elif max_board_height >= 5 and promotion_1_to_2 > 0.40:
        r_label = "接力活跃"
    elif max_board_height >= 3:
        r_label = "接力正常"
    elif max_board_height >= 2:
        r_label = "高度压制"
    else:
        r_label = "接力缺失"

    evidence = [
        f"最高{max_board_height}板",
        f"一进二{promotion_1_to_2:.0%}，二进三{promotion_2_to_3:.0%}，三进四{promotion_3_to_4:.0%}",
        f"首板封板率{first_board_success_rate:.0%}",
    ]

    # v2: add feedback evidence
    if yesterday_count > 0:
        evidence.append(
            f"昨涨停{yesterday_count}只→今继续{continue_ratio:.0%}，大面{big_loss_count}只"
        )
        evidence.append(f"接力反馈: {feedback_label}({feedback_score:.0f})")

    interpretation = (
        f"核心板块节律：{r_label}。"
        + f"最高{max_board_height}板。"
        + (f" 反馈{feedback_label}。" if feedback_label else "")
        + ("接力活跃，高度打开。" if r_label == "接力活跃"
           else "接力崩塌，全面退潮，停止接力。" if r_label == "接力崩塌"
           else "接力冻结，谨慎观望。" if r_label == "接力冻结"
           else "接力退潮，高度压制，慎打高位。" if r_label in ("接力退潮", "高度压制")
           else "接力缺失，市场无方向。" if r_label == "接力缺失"
           else "接力正常。")
    )

    return {
        "chart_type": "relay_ecology",
        "title": "核心板块节律",
        "module": "relay",
        "data": {
            "max_board_height": max_board_height,
            "first_board_success_rate": round(first_board_success_rate, 2),
            "promotion_1_to_2": round(promotion_1_to_2, 2),
            "promotion_2_to_3": round(promotion_2_to_3, 2),
            "promotion_3_to_4": round(promotion_3_to_4, 2),
            "feedback_score": round(feedback_score, 1),
            "feedback_label": feedback_label,
            "continue_ratio": round(continue_ratio, 2),
            "yesterday_limitup_count": yesterday_count,
            "yesterday_big_loss_count": big_loss_count,
            "board_groups": board_groups or [],
            "label": r_label,
        },
        "interpretation": interpretation,
        "evidence_refs": tuple(evidence),
    }

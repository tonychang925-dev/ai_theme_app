"""Chart 4: Relay Ecology 核心板块节律 — PDF page 6."""

from typing import Any


def build(max_board_height: int, first_board_success_rate: float,
          promotion_1_to_2: float, promotion_2_to_3: float, promotion_3_to_4: float,
          board_groups: list[dict] | None = None) -> dict[str, Any]:
    """Build relay ecology chart with promotion rates."""

    if max_board_height >= 5 and promotion_1_to_2 > 0.4:
        r_label = "接力活跃"
    elif max_board_height >= 3:
        r_label = "接力正常"
    elif max_board_height >= 2:
        r_label = "接力退潮"
    else:
        r_label = "高度压制"

    evidence = [
        f"最高{max_board_height}板",
        f"一进二{promotion_1_to_2:.0%}，二进三{promotion_2_to_3:.0%}，三进四{promotion_3_to_4:.0%}",
        f"首板封板率{first_board_success_rate:.0%}",
    ]

    interpretation = (
        f"核心板块节律：{r_label}。"
        + f"最高{max_board_height}板。"
        + ("接力活跃，高度打开。" if r_label == "接力活跃"
           else "接力退潮，高度压制，慎打高位。" if r_label in ("接力退潮", "高度压制")
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
            "board_groups": board_groups or [],
            "label": r_label,
        },
        "interpretation": interpretation,
        "evidence_refs": tuple(evidence),
    }

"""Chart 1: Market Power 大盘势能 — PDF page 4."""

from typing import Any


def build(up_count: int, down_count: int, limit_up: int, limit_down: int,
          turnover_yi: float, chain_board_count: int = 0,
          calibrated_lu: int | None = None, calibrated_turnover: float | None = None,
          calibrated_emotion: str | None = None) -> dict[str, Any]:
    """Build market breadth chart data.

    Scoring: z-score weighted composite across 6 dimensions.
    """
    # Apply analyst calibration overrides
    limit_up_final = calibrated_lu if calibrated_lu else limit_up
    turnover_final = calibrated_turnover if calibrated_turnover else turnover_yi

    total = up_count + down_count or 1
    up_ratio = round(up_count / total, 3)
    loss_ratio = round(down_count * 0.15 / total, 3)  # estimate -5% count as 15% of down

    # Z-score normalization with market-appropriate means
    def _z(val: float, mu: float, sigma: float) -> float:
        return (val - mu) / sigma if sigma > 0 else 0

    score = int(
        _z(limit_up_final, 80, 40) * 2
        + _z(chain_board_count, 15, 8) * 2
        - _z(limit_down, 30, 20) * 2
        - _z(loss_ratio * total, 200, 150) * 2
        + _z(up_ratio, 0.50, 0.15) * 2
        - _z(loss_ratio, 0.05, 0.05) * 2
    )

    if score >= 6:    label = "强势"
    elif score >= 2:  label = "修复"
    elif score >= -1: label = "混沌"
    elif score >= -5: label = "分歧"
    else:             label = "退潮/冰点"

    evidence = [
        f"涨停{limit_up_final}家，跌停{limit_down}家",
        f"上涨{up_count}/下跌{down_count}，上涨比{up_ratio:.1%}",
        f"成交额{turnover_final}万亿",
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
            "composite_score": score,
            "label": label,
            "calibrated": calibrated_lu is not None or calibrated_emotion is not None,
        },
        "interpretation": interpretation,
        "evidence_refs": tuple(evidence),
    }

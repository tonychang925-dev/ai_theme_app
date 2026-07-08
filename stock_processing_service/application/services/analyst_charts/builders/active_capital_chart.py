"""Chart 3: Active Capital 活跃资金成交量 — PDF page 5.

All amounts in 亿元 (100M CNY). Display layer formats to 万亿.
"""

from typing import Any


def build(total_amount_yi: float, active_amount_yi: float,
          limit_up_count: int) -> dict[str, Any]:
    """Build active capital chart.

    Args:
        total_amount_yi: 全市场成交额（亿元）
        active_amount_yi: 涨停/触板活跃资金成交额（亿元）
    """

    # Thresholds in 亿元 (1.5万亿=15000亿, 0.8万亿=8000亿, 0.4万亿=4000亿)
    if active_amount_yi > 15000:        c_label = "资金扩张"
    elif active_amount_yi > 8000:       c_label = "资金正常"
    elif active_amount_yi > 4000:       c_label = "资金收缩"
    else:                               c_label = "冰点低量"

    # Display formatting
    total_display = f"{total_amount_yi / 10000:.1f}万亿" if total_amount_yi >= 10000 else f"{total_amount_yi:.0f}亿"
    active_display = f"{active_amount_yi / 10000:.2f}万亿" if active_amount_yi >= 10000 else f"{active_amount_yi:.0f}亿"

    evidence = [
        f"全市场成交{total_display}",
        f"活跃资金约{active_display}",
        f"涨停{limit_up_count}家",
    ]

    active_wan_yi = active_amount_yi / 10000  # for threshold comparisons
    interpretation = (
        f"活跃资金：{c_label}。"
        + ("短线资金充裕，市场活跃。" if active_wan_yi > 0.8
           else "短线资金收缩，参与度下降。" if active_wan_yi <= 0.6
           else "资金正常。")
    )

    return {
        "chart_type": "active_capital",
        "title": "活跃资金成交量",
        "module": "emotion",
        "data": {
            "total_amount_yi": total_amount_yi,         # 亿元
            "total_amount_display": total_display,      # 格式化
            "active_amount_yi": active_amount_yi,       # 亿元
            "active_amount_display": active_display,    # 格式化
            "limit_up_count": limit_up_count,
            "label": c_label,
        },
        "interpretation": interpretation,
        "evidence_refs": tuple(evidence),
    }

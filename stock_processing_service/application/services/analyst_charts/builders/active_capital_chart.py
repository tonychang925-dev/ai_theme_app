"""Chart 3: Active Capital 活跃资金成交量 — PDF page 5."""

from typing import Any


def build(total_amount_yi: float, active_amount_yi: float,
          limit_up_count: int) -> dict[str, Any]:

    if active_amount_yi > 1.5:      c_label = "资金扩张"
    elif active_amount_yi > 0.8:    c_label = "资金正常"
    elif active_amount_yi > 0.4:    c_label = "资金收缩"
    else:                           c_label = "冰点低量"

    evidence = [
        f"全市场成交{total_amount_yi:.1f}万亿",
        f"活跃资金约{active_amount_yi:.1f}万亿",
        f"涨停{limit_up_count}家",
    ]

    interpretation = (
        f"活跃资金：{c_label}。"
        + ("短线资金充裕，市场活跃。" if active_amount_yi > 0.8
           else "短线资金收缩，参与度下降。" if active_amount_yi <= 0.6
           else "资金正常。")
    )

    return {
        "chart_type": "active_capital",
        "title": "活跃资金成交量",
        "module": "emotion",
        "data": {
            "total_amount_yi": total_amount_yi,
            "active_amount_yi": active_amount_yi,
            "limit_up_count": limit_up_count,
            "label": c_label,
        },
        "interpretation": interpretation,
        "evidence_refs": tuple(evidence),
    }

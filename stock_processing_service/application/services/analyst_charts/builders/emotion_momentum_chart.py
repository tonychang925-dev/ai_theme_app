"""Chart 2: Emotion Momentum 情绪动能 — PDF page 4-5."""

from typing import Any


def build(first_board_red_ratio: float, first_board_big_loss_ratio: float,
          chain_board_red_ratio: float, chain_board_ratio: float,
          chain_board_big_loss_ratio: float, yesterday_chain_not_limit_red_ratio: float,
          limit_up_count: int, chain_board_count: int,
          momentum_raw: float | None = None) -> dict[str, Any]:
    """Build emotion momentum chart. Score range: roughly -18 to +10."""

    # Use service-computed momentum_raw when available (v3 relay-based formula)
    if momentum_raw is not None:
        momentum = round(momentum_raw, 1)
    else:
        momentum = round(
            first_board_red_ratio * 2 - first_board_big_loss_ratio * 2
            + chain_board_red_ratio * 2 + min(1.0, chain_board_ratio) * 2
            - chain_board_big_loss_ratio * 2 - yesterday_chain_not_limit_red_ratio * 2, 1)

    if momentum >= 5:       m_label = "情绪高涨"
    elif momentum >= 0:     m_label = "情绪正常"
    elif momentum >= -5:    m_label = "情绪分歧"
    elif momentum >= -10:   m_label = "情绪退潮"
    else:                   m_label = "情绪冰点"

    evidence = [
        f"首板红盘比{first_board_red_ratio:.0%}，大面比{first_board_big_loss_ratio:.0%}",
        f"连板红盘比{chain_board_red_ratio:.0%}，涨停{limit_up_count}家，连板{chain_board_count}只",
        f"情绪动能{momentum:.1f}（范围-18~+10）",
    ]

    interpretation = (
        f"情绪动能：{m_label}（{momentum:.1f}）。"
        + ("短线情绪活跃，接力可做。" if momentum >= 0 else "情绪退潮，谨慎接力。")
    )

    return {
        "chart_type": "emotion_momentum",
        "title": "情绪动能",
        "module": "emotion",
        "data": {
            "first_board_red_ratio": round(first_board_red_ratio, 2),
            "first_board_big_loss_ratio": round(first_board_big_loss_ratio, 2),
            "chain_board_red_ratio": round(chain_board_red_ratio, 2),
            "chain_board_ratio": round(chain_board_ratio, 2),
            "chain_board_big_loss_ratio": round(chain_board_big_loss_ratio, 2),
            "yesterday_chain_not_limit_red_ratio": round(yesterday_chain_not_limit_red_ratio, 2),
            "emotion_momentum_score": momentum,
            "limit_up_count": limit_up_count,
            "chain_board_count": chain_board_count,
            "label": m_label,
        },
        "interpretation": interpretation,
        "evidence_refs": tuple(evidence),
    }

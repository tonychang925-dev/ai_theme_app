from __future__ import annotations

from decimal import Decimal

from stock_processing_service.domain.services.first_board_classifier import (
    FIRST_BOARD_CHAIN,
    FIRST_BOARD_NOT,
    FIRST_BOARD_OVERSOLD,
    FIRST_BOARD_RELAUNCH,
    FIRST_BOARD_QUALITY_STRICT,
    FirstBoardClassifier,
)


def _row(
    trade_date: str,
    *,
    pct_chg: str | None = None,
    close_price: str | None = None,
    pre_close: str | None = None,
    limit_up_price: str | None = None,
    limit_up: bool = False,
) -> dict[str, object]:
    row: dict[str, object] = {"trade_date": trade_date}
    if pct_chg is not None:
        row["pct_chg"] = Decimal(pct_chg)
    if close_price is not None:
        row["close_price"] = Decimal(close_price)
    if pre_close is not None:
        row["pre_close"] = Decimal(pre_close)
    if limit_up_price is not None:
        row["limit_up_price"] = Decimal(limit_up_price)
    row["limit_up"] = limit_up
    return row


def test_chain_first_board_when_no_prior_limit_up() -> None:
    classifier = FirstBoardClassifier()
    result = classifier.classify(
        rows=[
            _row("2026-05-06", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        ],
        current_trade_date="2026-05-06",
        current_row=_row("2026-05-06", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        subject_row={"is_downtrend": False, "near_pressure": False, "one_word_board": False},
    )

    assert result.first_board_type == FIRST_BOARD_CHAIN
    assert result.is_first_limit_up is True
    assert result.first_board_trace["previous_trade_date_limit_up"] is False
    assert result.first_board_trace["limit_streak_count"] == 1
    assert result.first_board_quality_tags == [FIRST_BOARD_QUALITY_STRICT]


def test_chain_first_board_relaunch_quality_tag_after_cooldown_and_pullback() -> None:
    classifier = FirstBoardClassifier()
    rows = [
        _row("2026-04-17", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        _row("2026-04-18", pct_chg="-3.00", close_price="9.70", pre_close="10.00", limit_up_price="10.90", limit_up=False),
        _row("2026-04-19", pct_chg="-1.50", close_price="9.55", pre_close="9.70", limit_up_price="10.70", limit_up=False),
        _row("2026-04-20", pct_chg="0.50", close_price="9.60", pre_close="9.55", limit_up_price="10.56", limit_up=False),
        _row("2026-04-21", pct_chg="1.00", close_price="9.70", pre_close="9.60", limit_up_price="10.67", limit_up=False),
        _row("2026-04-22", pct_chg="0.20", close_price="9.72", pre_close="9.70", limit_up_price="10.69", limit_up=False),
        _row("2026-05-06", pct_chg="10.00", close_price="10.69", pre_close="9.72", limit_up_price="10.69", limit_up=True),
    ]
    result = classifier.classify(
        rows=rows,
        current_trade_date="2026-05-06",
        current_row=_row("2026-05-06", pct_chg="10.00", close_price="10.69", pre_close="9.72", limit_up_price="10.69", limit_up=True),
        subject_row={"position_120": Decimal("0.28"), "is_downtrend": False, "near_pressure": False, "one_word_board": False},
    )

    assert result.first_board_type == FIRST_BOARD_CHAIN
    assert result.is_first_limit_up is True
    assert result.first_board_trace["previous_trade_date_limit_up"] is False
    assert result.first_board_trace["limit_streak_count"] == 1
    assert FIRST_BOARD_RELAUNCH in result.first_board_quality_tags
    assert result.first_board_trace["first_board_quality_tags"] == result.first_board_quality_tags


def test_not_first_board_when_previous_trade_day_limit_up() -> None:
    classifier = FirstBoardClassifier()
    rows = [
        _row("2026-05-05", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        _row("2026-05-06", pct_chg="10.00", close_price="11.00", pre_close="10.00", limit_up_price="11.00", limit_up=True),
    ]
    result = classifier.classify(
        rows=rows,
        current_trade_date="2026-05-06",
        current_row=_row("2026-05-06", pct_chg="10.00", close_price="11.00", pre_close="10.00", limit_up_price="11.00", limit_up=True),
        subject_row={"position_120": Decimal("0.30"), "is_downtrend": False, "near_pressure": False, "one_word_board": False},
    )

    assert result.first_board_type == FIRST_BOARD_NOT
    assert result.is_first_limit_up is False
    assert result.first_board_trace["previous_trade_date_limit_up"] is True
    assert result.first_board_trace["limit_streak_count"] == 2


def test_chain_first_board_high_position_gets_strict_quality_tag() -> None:
    classifier = FirstBoardClassifier()
    result = classifier.classify(
        rows=[
            _row("2026-05-06", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        ],
        current_trade_date="2026-05-06",
        current_row=_row("2026-05-06", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        subject_row={"position_120": Decimal("0.82"), "is_downtrend": False, "near_pressure": False, "one_word_board": False},
    )

    assert result.first_board_type == FIRST_BOARD_CHAIN
    assert result.first_board_trace["position_label"] == "high"
    assert result.first_board_quality_tags == [FIRST_BOARD_QUALITY_STRICT]


def test_chain_first_board_oversold_quality_tag_when_low_position() -> None:
    classifier = FirstBoardClassifier()
    result = classifier.classify(
        rows=[
            _row("2026-05-06", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        ],
        current_trade_date="2026-05-06",
        current_row=_row("2026-05-06", pct_chg="10.00", close_price="10.00", pre_close="9.09", limit_up_price="10.00", limit_up=True),
        subject_row={"position_120": Decimal("0.20"), "is_downtrend": False, "near_pressure": False, "one_word_board": False},
    )

    assert result.first_board_type == FIRST_BOARD_CHAIN
    assert result.is_first_limit_up is True
    assert result.first_board_trace["position_label"] == "low"
    assert FIRST_BOARD_OVERSOLD in result.first_board_quality_tags

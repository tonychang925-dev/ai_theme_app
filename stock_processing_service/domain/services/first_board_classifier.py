from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


FIRST_BOARD_STRICT = "strict_first_board"
FIRST_BOARD_RELAUNCH = "relaunch_first_board"
FIRST_BOARD_TREND = "trend_first_board"
FIRST_BOARD_OVERSOLD = "oversold_first_board"
FIRST_BOARD_NOT = "not_first_board"
FIRST_BOARD_ALLOWED = {
    FIRST_BOARD_STRICT,
    FIRST_BOARD_RELAUNCH,
    FIRST_BOARD_TREND,
    FIRST_BOARD_OVERSOLD,
}


@dataclass(frozen=True, slots=True)
class FirstBoardClassification:
    first_board_type: str
    first_board_trace: dict[str, Any]

    @property
    def is_first_limit_up(self) -> bool:
        return self.first_board_type in FIRST_BOARD_ALLOWED


class FirstBoardClassifier:
    """Classify board type from historical first-board facts.

    The classifier stays conservative:
    - strict_first_board: no prior limit-up in the lookback window
    - relaunch_first_board: prior limit-up exists, but after cooldown and pullback
    - trend_first_board: low/mid position, no high-position acceleration
    - oversold_first_board: low-position / oversold recovery board
    - not_first_board: consecutive board, second/third board, or high-risk rejection
    """

    def classify(
        self,
        *,
        rows: list[dict[str, Any]],
        current_trade_date: str,
        current_row: dict[str, Any],
        subject_row: dict[str, Any] | None = None,
    ) -> FirstBoardClassification:
        current_date = self._date_str(current_trade_date)
        current = dict(current_row or {})
        ordered_rows = self._ordered_rows(rows)
        current_limit_up = self._is_limit_up(current)
        position_120 = self._decimal_or_none(
            self._first_present(current, subject_row or {}, ("position_120", "position_ratio_120"))
        )
        position_label = self._position_label(position_120)
        is_downtrend = self._bool(
            self._first_present(current, subject_row or {}, ("is_downtrend", "downtrend"))
        )
        near_pressure = self._bool(
            self._first_present(current, subject_row or {}, ("near_pressure", "pressure_near"))
        )
        one_word_board = self._bool(
            self._first_present(current, subject_row or {}, ("one_word_board", "is_one_word_board"))
        )

        trace: dict[str, Any] = {
            "current_limit_up": current_limit_up,
            "last_limit_up_date": None,
            "cooldown_trade_days": None,
            "had_consecutive_limit_up": False,
            "pullback_after_last_limit_up": False,
            "reclaimed_ma_cluster": False,
            "position_label": position_label,
            "first_board_type_reason": "current_day_not_limit_up" if not current_limit_up else "pending",
        }

        if not current_limit_up:
            return FirstBoardClassification(FIRST_BOARD_NOT, trace)

        prior_rows = [row for row in ordered_rows if self._date_str(row.get("trade_date")) < current_date]
        if not prior_rows:
            return self._classify_no_prior_board(
                position_label=position_label,
                is_downtrend=is_downtrend,
                near_pressure=near_pressure,
                one_word_board=one_word_board,
                trace=trace,
            )

        previous_trade_date = self._previous_trade_date(ordered_rows, current_date)
        if previous_trade_date is not None:
            previous_row = self._row_by_date(ordered_rows, previous_trade_date)
            trace["had_consecutive_limit_up"] = bool(previous_row and self._is_limit_up(previous_row))

        prior_limit_rows = [row for row in prior_rows if self._is_limit_up(row)]
        last_limit_row = prior_limit_rows[-1] if prior_limit_rows else None
        if last_limit_row is None:
            return self._classify_no_prior_board(
                position_label=position_label,
                is_downtrend=is_downtrend,
                near_pressure=near_pressure,
                one_word_board=one_word_board,
                trace=trace,
            )

        last_limit_date = self._date_str(last_limit_row.get("trade_date"))
        trace["last_limit_up_date"] = last_limit_date
        trace["cooldown_trade_days"] = self._cooldown_trade_days(ordered_rows, last_limit_date, current_date)
        trace["pullback_after_last_limit_up"] = self._has_pullback_after_last_limit_up(
            ordered_rows,
            last_limit_date,
            current_date,
            last_limit_row,
        )
        trace["reclaimed_ma_cluster"] = position_label in {"low", "mid"} and not is_downtrend and not near_pressure

        if trace["had_consecutive_limit_up"]:
            trace["first_board_type_reason"] = "consecutive_board_excluded"
            return FirstBoardClassification(FIRST_BOARD_NOT, trace)

        cooldown_trade_days = int(trace["cooldown_trade_days"] or 0)
        if (
            cooldown_trade_days >= 5
            and trace["pullback_after_last_limit_up"]
            and trace["reclaimed_ma_cluster"]
            and position_label != "high"
            and not one_word_board
        ):
            trace["first_board_type_reason"] = "relaunch_after_cooldown"
            return FirstBoardClassification(FIRST_BOARD_RELAUNCH, trace)

        if position_label == "low" and not one_word_board:
            trace["first_board_type_reason"] = "oversold_low_position"
            return FirstBoardClassification(FIRST_BOARD_OVERSOLD, trace)

        if position_label in {"low", "mid"} and not is_downtrend and not near_pressure and not one_word_board:
            trace["first_board_type_reason"] = "trend_breakout"
            return FirstBoardClassification(FIRST_BOARD_TREND, trace)

        trace["first_board_type_reason"] = "strict_first_board"
        return FirstBoardClassification(FIRST_BOARD_STRICT, trace)

    def _classify_no_prior_board(
        self,
        *,
        position_label: str,
        is_downtrend: bool | None,
        near_pressure: bool | None,
        one_word_board: bool,
        trace: dict[str, Any],
    ) -> FirstBoardClassification:
        if one_word_board or position_label == "high" or near_pressure is True:
            trace["first_board_type_reason"] = "high_position_or_one_word_excluded"
            return FirstBoardClassification(FIRST_BOARD_NOT, trace)
        if position_label == "low" or is_downtrend is True:
            trace["reclaimed_ma_cluster"] = True
            trace["first_board_type_reason"] = "oversold_low_position"
            return FirstBoardClassification(FIRST_BOARD_OVERSOLD, trace)
        if position_label == "mid" and not is_downtrend and not near_pressure:
            trace["reclaimed_ma_cluster"] = True
            trace["first_board_type_reason"] = "trend_breakout"
            return FirstBoardClassification(FIRST_BOARD_TREND, trace)
        trace["first_board_type_reason"] = "strict_first_board"
        return FirstBoardClassification(FIRST_BOARD_STRICT, trace)

    def _ordered_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keyed: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for row in rows:
            trade_date = self._date_str(row.get("trade_date"))
            if not trade_date:
                continue
            keyed[trade_date] = dict(row)
        return [keyed[key] for key in sorted(keyed)]

    def _previous_trade_date(self, rows: list[dict[str, Any]], current_date: str) -> str | None:
        dates = [self._date_str(row.get("trade_date")) for row in rows if self._date_str(row.get("trade_date")) < current_date]
        return max(dates) if dates else None

    def _row_by_date(self, rows: list[dict[str, Any]], target_date: str) -> dict[str, Any] | None:
        for row in rows:
            if self._date_str(row.get("trade_date")) == target_date:
                return dict(row)
        return None

    def _cooldown_trade_days(self, rows: list[dict[str, Any]], last_limit_date: str, current_date: str) -> int:
        dates = [self._date_str(row.get("trade_date")) for row in rows]
        trade_dates = [d for d in dates if last_limit_date < d < current_date]
        return len(sorted(set(trade_dates)))

    def _has_pullback_after_last_limit_up(
        self,
        rows: list[dict[str, Any]],
        last_limit_date: str,
        current_date: str,
        last_limit_row: dict[str, Any],
    ) -> bool:
        last_close = self._decimal_or_none(last_limit_row.get("close_price"))
        last_pre_close = self._decimal_or_none(last_limit_row.get("pre_close"))
        pivot_close = last_close or last_pre_close
        if pivot_close is None:
            return True
        for row in rows:
            trade_date = self._date_str(row.get("trade_date"))
            if not (last_limit_date < trade_date < current_date):
                continue
            close_price = self._decimal_or_none(row.get("close_price"))
            pct = self._decimal_or_none(row.get("pct_chg"))
            if pct is not None and pct < Decimal("0"):
                return True
            if close_price is not None and close_price < pivot_close:
                return True
        return False

    def _position_label(self, position_120: Decimal | None) -> str:
        if position_120 is None:
            return "unknown"
        if position_120 <= Decimal("0.35"):
            return "low"
        if position_120 <= Decimal("0.65"):
            return "mid"
        return "high"

    def _is_limit_up(self, row: dict[str, Any]) -> bool:
        pct = self._decimal_or_none(row.get("pct_chg"))
        close_price = self._decimal_or_none(row.get("close_price"))
        limit_up_price = self._decimal_or_none(row.get("limit_up_price"))
        if pct is not None and pct >= Decimal("9.8"):
            return True
        if (
            close_price is not None
            and limit_up_price is not None
            and limit_up_price > Decimal("0")
            and close_price >= limit_up_price
        ):
            return True
        return bool(row.get("limit_up"))

    def _first_present(self, *rows_and_keys: Any) -> Any:
        keys = rows_and_keys[-1]
        for row in rows_and_keys[:-1]:
            if not isinstance(row, dict):
                continue
            for key in keys:
                value = row.get(key)
                if value not in (None, ""):
                    return value
        return None

    def _bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        return text in {"1", "true", "t", "yes", "y"}

    def _decimal_or_none(self, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _date_str(self, value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return str(value.isoformat())
        return str(value)

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


FIRST_BOARD_CHAIN = "chain_first_board"
FIRST_BOARD_NOT = "not_first_board"

FIRST_BOARD_QUALITY_RELAUNCH = "relaunch_first_board"
FIRST_BOARD_QUALITY_TREND = "trend_first_board"
FIRST_BOARD_QUALITY_OVERSOLD = "oversold_first_board"
FIRST_BOARD_QUALITY_STRICT = "strict_first_board"

# Backward-compatible aliases for quality tags.
FIRST_BOARD_RELAUNCH = FIRST_BOARD_QUALITY_RELAUNCH
FIRST_BOARD_TREND = FIRST_BOARD_QUALITY_TREND
FIRST_BOARD_OVERSOLD = FIRST_BOARD_QUALITY_OVERSOLD
FIRST_BOARD_STRICT = FIRST_BOARD_QUALITY_STRICT

FIRST_BOARD_QUALITY_TAGS = {
    FIRST_BOARD_QUALITY_RELAUNCH,
    FIRST_BOARD_QUALITY_TREND,
    FIRST_BOARD_QUALITY_OVERSOLD,
    FIRST_BOARD_QUALITY_STRICT,
}


@dataclass(frozen=True, slots=True)
class FirstBoardClassification:
    first_board_type: str
    first_board_quality_tags: list[str]
    first_board_trace: dict[str, Any]

    @property
    def is_first_limit_up(self) -> bool:
        return self.first_board_type == FIRST_BOARD_CHAIN


class FirstBoardClassifier:
    """Classify chain first-board facts from historical bars.

    Base definition:
    - current day limit-up
    - previous trade day not limit-up

    Quality tags:
    - relaunch_first_board
    - trend_first_board
    - oversold_first_board
    - strict_first_board
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
        row_by_date = {self._date_str(row.get("trade_date")): dict(row) for row in ordered_rows if self._date_str(row.get("trade_date"))}
        current_limit_up = self._is_limit_up(current)
        previous_trade_date = self._previous_trade_date(ordered_rows, current_date)
        previous_row = row_by_date.get(previous_trade_date) if previous_trade_date else None
        previous_trade_day_limit_up = bool(previous_row and self._is_limit_up(previous_row))
        limit_streak_count = self._limit_streak_count(ordered_rows, current_date)
        previous_limit_streak_count = self._limit_streak_count(ordered_rows, previous_trade_date) if previous_trade_date else 0

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
            "previous_trade_date": previous_trade_date,
            "previous_trade_date_limit_up": previous_trade_day_limit_up,
            "limit_streak_count": limit_streak_count,
            "previous_limit_streak_count": previous_limit_streak_count,
            "position_label": position_label,
            "first_board_type_reason": "current_day_not_limit_up" if not current_limit_up else "pending",
            "first_board_quality_tags": [],
        }

        if not current_limit_up:
            return FirstBoardClassification(FIRST_BOARD_NOT, [], trace)

        if previous_trade_day_limit_up:
            trace["first_board_type_reason"] = "previous_trade_day_limit_up"
            quality_tags = self._quality_tags(
                rows=ordered_rows,
                current_date=current_date,
                current=current,
                subject_row=subject_row or {},
            )
            trace["first_board_quality_tags"] = list(quality_tags)
            return FirstBoardClassification(FIRST_BOARD_NOT, quality_tags, trace)

        quality_tags = self._quality_tags(
            rows=ordered_rows,
            current_date=current_date,
            current=current,
            subject_row=subject_row or {},
        )
        trace["first_board_quality_tags"] = list(quality_tags)
        trace["first_board_type_reason"] = "previous_trade_day_not_limit_up"
        return FirstBoardClassification(FIRST_BOARD_CHAIN, quality_tags, trace)

    def _quality_tags(
        self,
        *,
        rows: list[dict[str, Any]],
        current_date: str,
        current: dict[str, Any],
        subject_row: dict[str, Any],
    ) -> list[str]:
        position_120 = self._decimal_or_none(
            self._first_present(current, subject_row, ("position_120", "position_ratio_120"))
        )
        position_label = self._position_label(position_120)
        is_downtrend = self._bool(self._first_present(current, subject_row, ("is_downtrend", "downtrend")))
        near_pressure = self._bool(self._first_present(current, subject_row, ("near_pressure", "pressure_near")))
        one_word_board = self._bool(self._first_present(current, subject_row, ("one_word_board", "is_one_word_board")))

        prior_limit_rows = [row for row in rows if self._date_str(row.get("trade_date")) < current_date and self._is_limit_up(row)]
        last_limit_row = prior_limit_rows[-1] if prior_limit_rows else None
        cooldown_trade_days = 0
        pullback_after_last_limit_up = False
        reclaimed_ma_cluster = False

        if last_limit_row is not None:
            last_limit_date = self._date_str(last_limit_row.get("trade_date"))
            if last_limit_date and current_date and last_limit_date < current_date:
                cooldown_trade_days = len(
                    {
                        self._date_str(row.get("trade_date"))
                        for row in rows
                        if last_limit_date < self._date_str(row.get("trade_date")) < current_date
                    }
                )
                pullback_after_last_limit_up = self._has_pullback_after_last_limit_up(
                    rows,
                    last_limit_date,
                    current_date,
                    last_limit_row,
                )
        reclaimed_ma_cluster = position_label in {"low", "mid"} and not is_downtrend and not near_pressure

        quality_tags: list[str] = []
        if (
            cooldown_trade_days >= 5
            and pullback_after_last_limit_up
            and reclaimed_ma_cluster
            and position_label != "high"
            and not one_word_board
        ):
            quality_tags.append(FIRST_BOARD_QUALITY_RELAUNCH)
        elif position_label == "low" and not one_word_board and not near_pressure:
            quality_tags.append(FIRST_BOARD_QUALITY_OVERSOLD)
        elif position_label in {"low", "mid"} and not is_downtrend and not near_pressure and not one_word_board:
            quality_tags.append(FIRST_BOARD_QUALITY_TREND)
        else:
            quality_tags.append(FIRST_BOARD_QUALITY_STRICT)
        return quality_tags

    def _ordered_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keyed: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for row in rows:
            trade_date = self._date_str(row.get("trade_date"))
            if not trade_date:
                continue
            keyed[trade_date] = dict(row)
        return [keyed[key] for key in sorted(keyed)]

    def _limit_streak_count(self, rows: list[dict[str, Any]], current_date: str | None) -> int:
        if not current_date:
            return 0
        streak = 0
        for row in self._ordered_rows(rows):
            trade_date = self._date_str(row.get("trade_date"))
            if not trade_date or trade_date > current_date:
                break
            if self._is_limit_up(row):
                streak = streak + 1 if streak else 1
            else:
                streak = 0
        return streak

    def _previous_trade_date(self, rows: list[dict[str, Any]], current_date: str) -> str | None:
        dates = [self._date_str(row.get("trade_date")) for row in rows if self._date_str(row.get("trade_date")) < current_date]
        return max(dates) if dates else None

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

    @staticmethod
    def _limit_up_threshold(stock_id: str, stock_name: str = "") -> Decimal:
        bare = str(stock_id or "").strip().upper().split(".")[0]
        if bare.startswith(("300", "301", "688")):
            return Decimal("19.8")  # ChiNext/STAR 20%
        if bare.startswith(("4", "8")):
            return Decimal("29.8")  # Beijing 30%
        if "ST" in str(stock_name or "").upper():
            return Decimal("4.95")  # ST 5%
        return Decimal("9.8")  # Main board 10%

    def _is_limit_up(self, row: dict[str, Any]) -> bool:
        # 1. Primary: close >= limit_up_price (board-agnostic, most reliable)
        close_price = self._decimal_or_none(row.get("close_price"))
        limit_up_price = self._decimal_or_none(row.get("limit_up_price"))
        if (
            close_price is not None
            and limit_up_price is not None
            and limit_up_price > Decimal("0")
            and close_price >= limit_up_price
        ):
            return True

        # 2. Explicit limit_up flag — if False, do NOT override with pct
        if "limit_up" in row:
            return bool(row.get("limit_up"))

        # 3. Board-aware pct threshold (last resort)
        pct = self._decimal_or_none(row.get("pct_chg"))
        if pct is not None:
            threshold = self._limit_up_threshold(
                str(row.get("stock_id") or ""),
                str(row.get("stock_name") or ""),
            )
            if pct >= threshold:
                return True

        return False

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

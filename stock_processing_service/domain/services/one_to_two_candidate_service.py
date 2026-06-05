from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures
from stock_processing_service.contracts.dto.post_market_setup_context_dto import PostMarketSetupFactContext


class OneToTwoCandidateService:
    """Builds the mainline first-board fact pool.

    It must not read Layer C strong pool.
    It must not call weak-to-strong candidate builder.
    It must not read DailyReviewV2 output.
    """

    def build_fact_pool(self, ctx: PostMarketSetupFactContext) -> list[OneToTwoFeatures]:
        current_trade_date = ctx.trade_date
        current_bars = [
            r for r in ctx.stock_daily_bars
            if self._date_str(r.get("trade_date")) == current_trade_date
        ]
        if not current_bars:
            return []

        bars_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in ctx.stock_daily_bars:
            stock_id = self._stock_id(row)
            if stock_id:
                bars_by_stock[stock_id].append(row)

        subject_rows_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in ctx.subject_stock_rows:
            stock_id = self._stock_id(row)
            if stock_id:
                subject_rows_by_stock[stock_id].append(row)

        strong_hotspot_keys = {
            str(r.get("subject_key"))
            for r in ctx.strong_hotspot_subjects
            if str(r.get("subject_key") or "").strip()
        }

        candidates: list[OneToTwoFeatures] = []
        for bar in current_bars:
            stock_id = self._stock_id(bar)
            if not stock_id:
                continue
            if not self._is_limit_up(bar):
                continue

            current_subject_row = self._choose_subject_row(subject_rows_by_stock.get(stock_id, []), current_trade_date)
            if not current_subject_row:
                continue

            subject_key = str(current_subject_row.get("subject_key") or "").strip()
            if not subject_key:
                continue

            history_rows = bars_by_stock.get(stock_id, [])
            is_first_limit_up = self._is_first_limit_up(history_rows, current_trade_date)

            is_confirmed = subject_key in ctx.active_subject_keys
            is_strong_hotspot = subject_key in strong_hotspot_keys
            lifecycle_row = ctx.lifecycle_by_subject.get(subject_key, {})
            board_row = ctx.subject_market_breadth.get(subject_key, {})
            pressure_row = ctx.pressure_by_stock.get(stock_id, {})
            ma_row = ctx.ma_pattern_by_stock.get(stock_id, {})

            first_limit_time = self._text(
                bar.get("first_limit_time")
                or current_subject_row.get("first_limit_time")
                or current_subject_row.get("limit_time")
            )
            open_board_count = self._int_or_none(
                bar.get("open_board_count")
                or current_subject_row.get("open_board_count")
            )

            features = OneToTwoFeatures(
                trade_date=current_trade_date,
                watch_date=ctx.watch_date,
                stock_id=stock_id,
                stock_name=self._text(bar.get("stock_name") or current_subject_row.get("stock_name") or stock_id),
                subject_key=subject_key,
                subject_name=self._text(
                    current_subject_row.get("subject_name")
                    or current_subject_row.get("theme_name")
                    or subject_key
                ),
                is_confirmed_mainline=is_confirmed,
                is_strong_hotspot=is_strong_hotspot,
                mainline_or_hotspot_state=(
                    "confirmed_mainline"
                    if is_confirmed
                    else "strong_hotspot"
                    if is_strong_hotspot
                    else "pending_review"
                ),
                lifecycle_state=self._text(lifecycle_row.get("lifecycle_state") or lifecycle_row.get("final_cycle_state") or "unknown"),
                market_trade_mode=self._text(ctx.market_regime.get("trade_mode") or "no_trade"),
                allow_trade=bool(ctx.market_regime.get("allow_trade", False)),
                is_first_limit_up=is_first_limit_up,
                is_one_word_board=self._is_one_word_board(bar),
                is_late_seal=bool(
                    bar.get("is_late_seal")
                    or current_subject_row.get("is_late_seal")
                    or current_subject_row.get("late_seal")
                    or False
                ),
                first_limit_time=first_limit_time,
                open_board_count=open_board_count,
                turnover_rate=self._decimal_or_none(
                    bar.get("turnover_rate")
                    or current_subject_row.get("turnover_rate")
                    or current_subject_row.get("turnover")
                ),
                amount=self._decimal_or_none(bar.get("amount") or current_subject_row.get("amount")),
                close_seal_amount=self._decimal_or_none(
                    current_subject_row.get("close_seal_amount")
                    or current_subject_row.get("seal_amount")
                ),
                seal_ratio=self._decimal_or_none(
                    current_subject_row.get("seal_ratio")
                    or current_subject_row.get("close_seal_ratio")
                ),
                float_mcap=self._decimal_or_none(
                    current_subject_row.get("float_mcap")
                    or current_subject_row.get("float_market_cap")
                ),
                position_120=self._decimal_or_none(
                    current_subject_row.get("position_120")
                    or current_subject_row.get("position_ratio_120")
                ),
                is_downtrend=self._bool_or_none(
                    current_subject_row.get("is_downtrend")
                    or pressure_row.get("is_downtrend")
                ),
                near_pressure=self._bool_or_none(
                    current_subject_row.get("near_pressure")
                    or pressure_row.get("near_pressure")
                ),
                same_subject_limit_count=self._int_or_none(
                    board_row.get("subject_limit_up_count")
                    or board_row.get("limit_up_count")
                ),
                same_subject_strong_count=self._int_or_none(
                    board_row.get("subject_strong_count")
                    or board_row.get("strong_count")
                ),
                data_quality={
                    "missing_required": self._missing_required(
                        bar=bar,
                        current_subject_row=current_subject_row,
                        board_row=board_row,
                        lifecycle_row=lifecycle_row,
                    ),
                    "has_current_bar": True,
                    "has_subject_mapping": True,
                    "has_breadth": bool(board_row),
                    "has_lifecycle": bool(lifecycle_row),
                    "has_market_regime": bool(ctx.market_regime),
                },
                source_trace={
                    "fact_pool_source": "mainline_first_board_fact_pool",
                    "stock_id": stock_id,
                    "subject_key": subject_key,
                    "trade_date": current_trade_date,
                    "bar_trade_date": self._date_str(bar.get("trade_date")),
                },
            )
            candidates.append(features)

        return candidates

    def _missing_required(
        self,
        *,
        bar: dict[str, Any],
        current_subject_row: dict[str, Any],
        board_row: dict[str, Any],
        lifecycle_row: dict[str, Any],
    ) -> list[str]:
        missing: list[str] = []
        if self._decimal_or_none(bar.get("amount")) is None and self._decimal_or_none(current_subject_row.get("amount")) is None:
            missing.append("amount")
        if not board_row:
            missing.append("board_breadth")
        if not lifecycle_row:
            missing.append("lifecycle")
        return missing

    def _choose_subject_row(self, rows: list[dict[str, Any]], trade_date: str) -> dict[str, Any] | None:
        if not rows:
            return None
        matched = [r for r in rows if self._date_str(r.get("trade_date")) == trade_date]
        if matched:
            return matched[0]
        return rows[0]

    def _is_first_limit_up(self, rows: list[dict[str, Any]], current_trade_date: str) -> bool:
        current = [r for r in rows if self._date_str(r.get("trade_date")) == current_trade_date]
        if not current:
            return False
        prior = [r for r in rows if self._date_str(r.get("trade_date")) != current_trade_date]
        return self._is_limit_up(current[0]) and not any(self._is_limit_up(r) for r in prior)

    def _is_limit_up(self, row: dict[str, Any]) -> bool:
        pct = self._decimal_or_none(row.get("pct_chg"))
        close_price = self._decimal_or_none(row.get("close_price"))
        limit_up_price = self._decimal_or_none(row.get("limit_up_price"))
        if pct is not None and pct >= Decimal("9.8"):
            return True
        if close_price is not None and limit_up_price is not None and close_price >= limit_up_price:
            return True
        return bool(row.get("limit_up"))

    def _is_one_word_board(self, row: dict[str, Any]) -> bool:
        open_price = self._decimal_or_none(row.get("open_price"))
        high_price = self._decimal_or_none(row.get("high_price"))
        low_price = self._decimal_or_none(row.get("low_price"))
        close_price = self._decimal_or_none(row.get("close_price"))
        limit_up_price = self._decimal_or_none(row.get("limit_up_price"))
        if None in {open_price, high_price, low_price, close_price}:
            return bool(row.get("one_word_board") or row.get("is_one_word_board"))
        return (
            open_price == high_price == low_price == close_price
            and (limit_up_price is None or close_price >= limit_up_price)
        )

    def _stock_id(self, row: dict[str, Any]) -> str:
        return self._text(row.get("stock_id") or row.get("stock_code") or row.get("code") or "")

    def _date_str(self, value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return str(value.isoformat())
        return str(value)

    def _text(self, value: Any) -> str:
        return str(value or "").strip()

    def _int_or_none(self, value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except Exception:
            return None

    def _bool_or_none(self, value: Any) -> bool | None:
        if value is None or value == "":
            return None
        return bool(value)

    def _decimal_or_none(self, value: Any) -> Decimal | None:
        try:
            if value is None or value == "":
                return None
            return Decimal(str(value))
        except Exception:
            return None

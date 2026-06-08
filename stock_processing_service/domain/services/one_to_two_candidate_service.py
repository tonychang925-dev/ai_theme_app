from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures
from stock_processing_service.contracts.dto.post_market_setup_context_dto import PostMarketSetupFactContext
from stock_processing_service.domain.services.first_board_classifier import FirstBoardClassifier


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
                bare = stock_id.split(".", 1)[0]
                if bare != stock_id:
                    bars_by_stock[bare].append(row)

        subject_rows_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in ctx.subject_stock_rows:
            stock_id = self._stock_id(row)
            if stock_id:
                subject_rows_by_stock[stock_id].append(row)
                bare = stock_id.split(".", 1)[0]
                if bare != stock_id:
                    subject_rows_by_stock[bare].append(row)

        strong_hotspot_keys: set[str] = set()
        for r in ctx.strong_hotspot_subjects:
            sk = self._subject_key(r.get("subject_key"))
            if sk:
                strong_hotspot_keys.add(sk)
        confirmed_hotspot_keys: set[str] = set()
        for sk in ctx.confirmed_hotspot_keys:
            stripped = self._subject_key(sk)
            if stripped:
                confirmed_hotspot_keys.add(stripped)
        subject_priority_rank = dict(ctx.subject_priority_rank or {})
        subject_authenticity_by_subject = dict(ctx.subject_authenticity_by_subject or {})
        stock_subject_authenticity_by_pair = dict(ctx.stock_subject_authenticity_by_pair or {})
        kline_pattern_quality_by_stock = dict(ctx.kline_pattern_quality_by_stock or {})
        turnover_rate_by_stock = dict(getattr(ctx, "turnover_rate_by_stock", {}) or {})
        first_board_classifier = FirstBoardClassifier()

        candidates: list[OneToTwoFeatures] = []
        for bar in current_bars:
            stock_id = self._stock_id(bar)
            if not stock_id:
                continue
            stock_key = stock_id.split(".", 1)[0]
            if not self._is_limit_up(bar):
                continue

            current_subject_row = self._choose_subject_row(
                subject_rows_by_stock.get(stock_id, []),
                current_trade_date,
                active_subject_keys=ctx.active_subject_keys,
                strong_hotspot_keys=strong_hotspot_keys,
                confirmed_hotspot_keys=confirmed_hotspot_keys,
                subject_priority_rank=subject_priority_rank,
                subject_authenticity_by_subject=subject_authenticity_by_subject,
                stock_subject_authenticity_by_pair=stock_subject_authenticity_by_pair,
                stock_pattern_quality=kline_pattern_quality_by_stock.get(stock_id, {}),
                turnover_rate_by_stock=turnover_rate_by_stock,
            )
            if not current_subject_row:
                continue

            subject_key = str(current_subject_row.get("subject_key") or "").strip()
            if not subject_key:
                continue
            pair_key = self._stock_subject_key(stock_id, subject_key)

            history_rows = bars_by_stock.get(stock_id, [])
            first_board = first_board_classifier.classify(
                rows=history_rows,
                current_trade_date=current_trade_date,
                current_row=bar,
                subject_row=current_subject_row,
            )
            first_board_type = first_board.first_board_type
            first_board_quality_tags = list(first_board.first_board_quality_tags or [])
            first_board_trace = dict(first_board.first_board_trace)
            is_first_limit_up = first_board.is_first_limit_up

            is_confirmed = subject_key in ctx.active_subject_keys
            is_strong_hotspot = subject_key in strong_hotspot_keys
            # Design doc §4.2: candidate source is mainline first-board fact pool;
            # exclude non-mainline, non-hotspot subjects.
            if not is_confirmed and not is_strong_hotspot:
                continue
            lifecycle_row = ctx.lifecycle_by_subject.get(subject_key, {})
            board_row = ctx.subject_market_breadth.get(subject_key, {})
            pressure_row = ctx.pressure_by_stock.get(stock_id, {})
            ma_row = ctx.ma_pattern_by_stock.get(stock_id, {})
            stock_subject_authenticity = dict(stock_subject_authenticity_by_pair.get(pair_key, {}) or {})
            subject_authenticity = stock_subject_authenticity or dict(subject_authenticity_by_subject.get(subject_key, {}) or {})
            kline_pattern_quality = dict(kline_pattern_quality_by_stock.get(stock_id, {}) or {})

            first_limit_time = self._text(
                bar.get("first_limit_time")
                or current_subject_row.get("first_limit_time")
                or current_subject_row.get("limit_time")
            )
            open_board_count = self._int_or_none(
                bar.get("open_board_count")
                or current_subject_row.get("open_board_count")
            )
            candidate_rows = [
                r for r in subject_rows_by_stock.get(stock_id, [])
                if self._date_str(r.get("trade_date")) == current_trade_date
            ] or list(subject_rows_by_stock.get(stock_id, []))
            candidate_subject_keys = [
                str(r.get("subject_key") or "").strip()
                for r in candidate_rows
                if str(r.get("subject_key") or "").strip()
            ]
            selected_reason = self._selection_reason(
                subject_key=subject_key,
                active_subject_keys=ctx.active_subject_keys,
                strong_hotspot_keys=strong_hotspot_keys,
                subject_priority_rank=subject_priority_rank,
                row=current_subject_row,
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
                lifecycle_state=self._text(lifecycle_row.get("state") or lifecycle_row.get("lifecycle_state") or lifecycle_row.get("final_cycle_state") or "unknown"),
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
                    or turnover_rate_by_stock.get(stock_key)
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
                previous_trade_date=first_board_trace.get("previous_trade_date"),
                previous_trade_date_limit_up=self._bool_or_none(first_board_trace.get("previous_trade_date_limit_up")),
                limit_streak_count=self._int_or_none(first_board_trace.get("limit_streak_count")) or 0,
                subject_authenticity=subject_authenticity,
                kline_pattern_quality=kline_pattern_quality,
                first_board_quality_tags=first_board_quality_tags,
                first_board_type=first_board_type,
                first_board_trace=first_board_trace,
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
                        "first_board_type": first_board_type,
                        "first_board_quality_tags": first_board_quality_tags,
                        "first_board_trace": first_board_trace,
                        "subject_selection": {
                        "selected_subject_key": subject_key,
                        "selected_subject_name": self._text(
                            current_subject_row.get("subject_name")
                            or current_subject_row.get("theme_name")
                            or subject_key
                        ),
                        "candidate_subject_keys": candidate_subject_keys,
                        "active_subject_keys_hit": sorted(set(candidate_subject_keys) & set(ctx.active_subject_keys)),
                        "strong_hotspot_keys_hit": sorted(set(candidate_subject_keys) & strong_hotspot_keys),
                        "subject_authenticity": {
                            "score": subject_authenticity.get("score"),
                            "level": subject_authenticity.get("level"),
                            "purity_score": subject_authenticity.get("purity_score"),
                            "theme_tier": subject_authenticity.get("theme_tier"),
                            "authenticity_scope": subject_authenticity.get("authenticity_scope"),
                            "stock_subject_key": subject_authenticity.get("stock_subject_key"),
                        },
                        "first_board_type": first_board_type,
                        "first_board_quality_tags": first_board_quality_tags,
                        "first_board_trace": first_board_trace,
                        "kline_pattern_quality": {
                            "has_golden_spider": kline_pattern_quality.get("has_golden_spider"),
                            "score": kline_pattern_quality.get("score"),
                            "level": kline_pattern_quality.get("level"),
                            "pattern_reasons": list(kline_pattern_quality.get("pattern_reasons") or []),
                        },
                        "subject_priority_rank": {
                            key: subject_priority_rank[key]
                            for key in candidate_subject_keys
                            if key in subject_priority_rank
                        },
                        "subject_authenticity": subject_authenticity,
                        "stock_subject_authenticity": stock_subject_authenticity,
                        "kline_pattern_quality": kline_pattern_quality,
                        "selection_rank_components": {
                            "band": 0 if subject_key in confirmed_hotspot_keys else 1 if subject_key in strong_hotspot_keys else 2 if subject_key in ctx.active_subject_keys else 3 if bool(current_subject_row.get("is_leader")) else 4,
                            "authenticity_score": subject_authenticity.get("score"),
                            "business_rank": subject_priority_rank.get(subject_key),
                            "subject_limit_up_count": board_row.get("subject_limit_up_count") or board_row.get("limit_up_count"),
                            "pool_rank": current_subject_row.get("pool_rank") or current_subject_row.get("rank_order"),
                            "first_board_type": first_board_type,
                        },
                        "selection_reason": selected_reason,
                    },
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

    def _choose_subject_row(
        self,
        rows: list[dict[str, Any]],
        trade_date: str,
        *,
        active_subject_keys: set[str],
        strong_hotspot_keys: set[str],
        confirmed_hotspot_keys: set[str] | None = None,
        subject_priority_rank: dict[str, int] | None = None,
        subject_authenticity_by_subject: dict[str, dict[str, Any]] | None = None,
        stock_subject_authenticity_by_pair: dict[str, dict[str, Any]] | None = None,
        stock_pattern_quality: dict[str, Any] | None = None,
        turnover_rate_by_stock: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not rows:
            return None
        matched = [r for r in rows if self._date_str(r.get("trade_date")) == trade_date]
        candidates = matched or rows
        confirmed_hotspot_keys = confirmed_hotspot_keys or set()
        subject_priority_rank = subject_priority_rank or {}
        subject_authenticity_by_subject = subject_authenticity_by_subject or {}
        stock_subject_authenticity_by_pair = stock_subject_authenticity_by_pair or {}
        stock_pattern_quality = stock_pattern_quality or {}
        turnover_rate_by_stock = turnover_rate_by_stock or {}
        stock_id = self._stock_id(candidates[0]) if candidates else ""

        def _priority(row: dict[str, Any]) -> tuple[int, float, float, int, int, int, str]:
            subject_key = str(row.get("subject_key") or "").strip()
            pair_key = self._stock_subject_key(stock_id, subject_key)
            authenticity = stock_subject_authenticity_by_pair.get(pair_key) or subject_authenticity_by_subject.get(subject_key) or {}
            authenticity_score = self._float_or_none(authenticity.get("score")) or 0.0
            pattern_score = self._float_or_none(stock_pattern_quality.get("score")) or 0.0
            turnover_rate = self._decimal_or_none(
                row.get("turnover_rate")
                or turnover_rate_by_stock.get(stock_id.split(".", 1)[0] if stock_id else "")
            )
            if subject_key in confirmed_hotspot_keys:
                band = 0
            elif subject_key in strong_hotspot_keys:
                band = 1
            elif subject_key in active_subject_keys:
                band = 2
            elif bool(row.get("is_leader")):
                band = 3
            else:
                band = 4
            business_rank = subject_priority_rank.get(subject_key, 999999)
            subject_limit_up_count = self._int_or_none(row.get("subject_limit_up_count") or row.get("limit_up_count")) or 0
            pool_rank = self._int_or_none(row.get("pool_rank") or row.get("rank_order")) or 9999
            turnover_rank = float(turnover_rate) if turnover_rate is not None else 999.0
            return (band, -authenticity_score, -pattern_score, business_rank, -subject_limit_up_count, turnover_rank, pool_rank, subject_key)

        return sorted(candidates, key=_priority)[0]

    def _selection_reason(
        self,
        *,
        subject_key: str,
        active_subject_keys: set[str],
        strong_hotspot_keys: set[str],
        subject_priority_rank: dict[str, int],
        row: dict[str, Any],
    ) -> str:
        if subject_key in subject_priority_rank and subject_key in active_subject_keys:
            return "confirmed_hotspot_rank"
        if subject_key in subject_priority_rank and subject_key in strong_hotspot_keys:
            return "strong_hotspot_rank"
        if subject_key in active_subject_keys:
            return "active_mainline"
        if subject_key in strong_hotspot_keys:
            return "strong_hotspot"
        if bool(row.get("is_leader")):
            return "leader"
        return "fallback"

    @staticmethod
    def _stock_subject_key(stock_id: str, subject_key: str) -> str:
        stock_key = str(stock_id or "").strip().split(".")[0]
        subject_key = str(subject_key or "").strip()
        if not stock_key or not subject_key:
            return ""
        return f"{stock_key}|{subject_key}"

    @staticmethod
    def _is_limit_up(row: dict[str, Any]) -> bool:
        from stock_processing_service.domain.services.limit_up_detector import LimitUpDetector
        return LimitUpDetector.is_limit_up(row)

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

    @staticmethod
    def _subject_key(value: Any) -> str:
        return str(value or "").strip()

    def _stock_id(self, row: dict[str, Any]) -> str:
        raw = self._text(row.get("stock_id") or row.get("stock_code") or row.get("code") or "")
        if not raw:
            return ""
        stock_id = raw.upper()
        if "." in stock_id:
            return stock_id
        if len(stock_id) == 6 and stock_id.isdigit():
            if stock_id.startswith(("6", "9")):
                return f"{stock_id}.SH"
            if stock_id.startswith(("0", "2", "3")):
                return f"{stock_id}.SZ"
            if stock_id.startswith(("4", "8")):
                return f"{stock_id}.BJ"
        return stock_id

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

    def _float_or_none(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    def _decimal_or_none(self, value: Any) -> Decimal | None:
        try:
            if value is None or value == "":
                return None
            return Decimal(str(value))
        except Exception:
            return None

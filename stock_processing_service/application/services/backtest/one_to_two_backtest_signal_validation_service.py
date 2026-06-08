from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from stock_processing_service.domain.services.one_to_two_rule_config import DEFAULT_RULE_VERSION

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_ID = "one_to_two"
DEFAULT_STRATEGY_VERSION = DEFAULT_RULE_VERSION
OUTCOME_A_PROXY = "A_SEALED_SECOND_BOARD_PROXY"
OUTCOME_B_BROKEN = "B_TOUCHED_BUT_BROKEN"
OUTCOME_C_NO_TOUCH = "C_FAILED_NO_TOUCH"
OUTCOME_D_NO_DATA = "D_NO_DATA"


class OneToTwoBacktestSignalValidationService:
    """Validate OneToTwo watch signals against T+1 daily bars."""

    def __init__(self, read_port: Any, gateway: Any) -> None:
        self._read = read_port
        self._gw = gateway

    async def validate(
        self,
        run_id: str,
        *,
        strategy_id: str = DEFAULT_STRATEGY_ID,
        strategy_version: str = DEFAULT_STRATEGY_VERSION,
    ) -> dict[str, Any]:
        if strategy_id != DEFAULT_STRATEGY_ID:
            raise ValueError("strategy_id must be one_to_two")
        if strategy_version != DEFAULT_STRATEGY_VERSION:
            raise ValueError(f"strategy_version must be {DEFAULT_STRATEGY_VERSION}")

        await self._delete_run_validations(run_id, strategy_id, strategy_version)
        signals = await self._load_signals(run_id, strategy_id, strategy_version)
        if not signals:
            return {"run_id": run_id, "validated_count": 0, "written": 0, "warning": "No signals found"}

        validations: list[dict[str, Any]] = []
        for signal in signals:
            validations.append(await self._validate_one_signal(signal, strategy_id=strategy_id, strategy_version=strategy_version))

        written = await self._write_validations(validations)
        if written != len(validations):
            raise RuntimeError("failed to write one_to_two signal validations")

        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "validated_count": len(validations),
            "written": written,
        }

    async def _validate_one_signal(
        self,
        signal: dict[str, Any],
        *,
        strategy_id: str,
        strategy_version: str,
    ) -> dict[str, Any]:
        signal_id = str(signal.get("signal_id") or "")
        rule_version = str(signal.get("rule_version") or strategy_version)
        trade_date = _parse_date(signal.get("trade_date"))
        stock_id = str(signal.get("stock_id") or "").strip()
        if not signal_id:
            raise RuntimeError("missing signal_id")
        if trade_date is None:
            raise RuntimeError(f"missing trade_date for signal {signal_id}")
        if not stock_id:
            raise RuntimeError(f"missing stock_id for signal {signal_id}")

        buy_ref_date = await self._get_next_trade_date(trade_date)
        if buy_ref_date is None:
            return self._missing_validation(
                signal,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                rule_version=rule_version,
                reason="no_next_trade_date",
            )

        bars = await self._load_t1_bars(buy_ref_date, stock_id)
        if not bars:
            return self._missing_validation(
                signal,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                rule_version=rule_version,
                reason="no_t1_bars",
                buy_ref_date=buy_ref_date,
            )

        bar = self._select_bar_for_stock(bars, stock_id)
        if bar is None:
            return self._missing_validation(
                signal,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                rule_version=rule_version,
                reason="no_matching_t1_bar",
                buy_ref_date=buy_ref_date,
            )

        limit_up_price = _to_decimal(getattr(bar, "limit_up_price", None) or getattr(bar, "limit_up", None))
        high_price = _to_decimal(getattr(bar, "high_price", None))
        close_price = _to_decimal(getattr(bar, "close_price", None))
        open_price = _to_decimal(getattr(bar, "open_price", None))
        if limit_up_price is None or high_price is None or close_price is None:
            return self._missing_validation(
                signal,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                rule_version=rule_version,
                reason="missing_t1_prices",
                buy_ref_date=buy_ref_date,
            )

        touched = high_price >= limit_up_price
        sealed = close_price >= limit_up_price
        if sealed:
            outcome_label = OUTCOME_A_PROXY
            outcome_source = "daily_close_proxy"
        elif touched:
            outcome_label = OUTCOME_B_BROKEN
            outcome_source = "daily_high_proxy"
        else:
            outcome_label = OUTCOME_C_NO_TOUCH
            outcome_source = "daily_close_proxy"

        next_day_open_pct = _pct(open_price, limit_up_price) if open_price is not None else None
        next_day_high_pct = _pct(high_price, limit_up_price)
        next_day_close_pct = _pct(close_price, limit_up_price)
        next_day_open_board_count = int(getattr(bar, "open_board_count", 0) or 0) if sealed else 0
        next_day_max_drawdown = _pct(_to_decimal(getattr(bar, "low_price", None)), limit_up_price)

        return {
            "signal_id": signal_id,
            "run_id": signal.get("run_id"),
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "rule_version": rule_version,
            "trade_date": trade_date,
            "stock_id": stock_id,
            "signal_level": str(signal.get("signal_level") or ""),
            "score": _safe_float(signal.get("score")),
            "buy_ref_date": buy_ref_date,
            "buy_ref_price": _safe_float(limit_up_price),
            "next_day_touch_limit_up": touched,
            "next_day_sealed_limit_up": sealed,
            "next_day_open_pct": next_day_open_pct,
            "next_day_high_pct": next_day_high_pct,
            "next_day_close_pct": next_day_close_pct,
            "next_day_open_board_count": next_day_open_board_count,
            "next_day_max_drawdown": next_day_max_drawdown,
            "outcome_label": outcome_label,
            "outcome_source": outcome_source,
            "next_1d_return": _pct(close_price, limit_up_price),
            "next_2d_return": None,
            "next_3d_return": None,
            "next_5d_return": None,
            "max_return_3d": None,
            "max_return_5d": None,
            "max_drawdown_3d": None,
            "max_drawdown_5d": None,
            "hit_limit_up_3d": touched,
            "hit_limit_up_5d": touched,
            "is_win_1d": sealed,
            "is_win_3d": None,
            "is_win_5d": None,
            "loss_over_5pct": bool(next_day_max_drawdown is not None and next_day_max_drawdown < Decimal("-0.05")),
            "validation_status": "ok",
            "validation_error": None,
        }

    def _missing_validation(
        self,
        signal: dict[str, Any],
        *,
        strategy_id: str,
        strategy_version: str,
        rule_version: str,
        reason: str,
        buy_ref_date: date | None = None,
    ) -> dict[str, Any]:
        trade_date = _parse_date(signal.get("trade_date"))
        return {
            "signal_id": str(signal.get("signal_id") or ""),
            "run_id": signal.get("run_id"),
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "rule_version": rule_version,
            "trade_date": trade_date,
            "stock_id": str(signal.get("stock_id") or ""),
            "signal_level": str(signal.get("signal_level") or ""),
            "score": _safe_float(signal.get("score")),
            "buy_ref_date": buy_ref_date,
            "buy_ref_price": None,
            "next_day_touch_limit_up": None,
            "next_day_sealed_limit_up": None,
            "next_day_open_pct": None,
            "next_day_high_pct": None,
            "next_day_close_pct": None,
            "next_day_open_board_count": None,
            "next_day_max_drawdown": None,
            "outcome_label": OUTCOME_D_NO_DATA,
            "outcome_source": "missing",
            "next_1d_return": None,
            "next_2d_return": None,
            "next_3d_return": None,
            "next_5d_return": None,
            "max_return_3d": None,
            "max_return_5d": None,
            "max_drawdown_3d": None,
            "max_drawdown_5d": None,
            "hit_limit_up_3d": None,
            "hit_limit_up_5d": None,
            "is_win_1d": None,
            "is_win_3d": None,
            "is_win_5d": None,
            "loss_over_5pct": None,
            "validation_status": "missing_bar",
            "validation_error": reason,
        }

    async def _load_signals(self, run_id: str, strategy_id: str, strategy_version: str) -> list[dict[str, Any]]:
        try:
            rows = await self._gw._client.execute_query(
                "SELECT * FROM strategy_signal_daily WHERE run_id = $1 AND strategy_id = $2 AND strategy_version = $3 ORDER BY trade_date ASC, stock_id ASC, source_id ASC",
                [run_id, strategy_id, strategy_version],
            )
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:
            raise RuntimeError(f"failed to load one_to_two signals for run_id={run_id}") from exc

    async def _write_validations(self, validations: list[dict[str, Any]]) -> int:
        if not validations:
            return 0
        fn = getattr(self._gw, "upsert_strategy_signal_validation_rows", None)
        if callable(fn):
            written = await fn(validations)
            if written != len(validations):
                raise RuntimeError("failed to write one_to_two signal validations")
            return written
        return await self._write_via_raw_sql(validations)

    async def _write_via_raw_sql(self, validations: list[dict[str, Any]]) -> int:
        written = 0
        for v in validations:
            try:
                await self._gw._client.execute_query(
                    """
                    INSERT INTO strategy_signal_validation (
                        signal_id, run_id, strategy_id, strategy_version,
                        trade_date, stock_id, signal_level, score,
                        buy_ref_date, buy_ref_price,
                        next_day_touch_limit_up, next_day_sealed_limit_up,
                        next_day_open_pct, next_day_high_pct, next_day_close_pct,
                        next_day_open_board_count, next_day_max_drawdown,
                        outcome_label, outcome_source,
                        next_1d_return, next_2d_return, next_3d_return, next_5d_return,
                        max_return_3d, max_return_5d, max_drawdown_3d, max_drawdown_5d,
                        hit_limit_up_3d, hit_limit_up_5d,
                        is_win_1d, is_win_3d, is_win_5d,
                        loss_over_5pct,
                        validation_status, validation_error
                    ) VALUES (
                        $1, $2, $3, $4,
                        $5, $6, $7, $8,
                        $9, $10,
                        $11, $12,
                        $13, $14, $15,
                        $16, $17,
                        $18, $19,
                        $20, $21, $22, $23,
                        $24, $25, $26, $27,
                        $28, $29,
                        $30, $31, $32,
                        $33,
                        $34, $35
                    )
                    ON CONFLICT (signal_id) DO UPDATE SET
                        buy_ref_date = EXCLUDED.buy_ref_date,
                        buy_ref_price = EXCLUDED.buy_ref_price,
                        next_day_touch_limit_up = EXCLUDED.next_day_touch_limit_up,
                        next_day_sealed_limit_up = EXCLUDED.next_day_sealed_limit_up,
                        next_day_open_pct = EXCLUDED.next_day_open_pct,
                        next_day_high_pct = EXCLUDED.next_day_high_pct,
                        next_day_close_pct = EXCLUDED.next_day_close_pct,
                        next_day_open_board_count = EXCLUDED.next_day_open_board_count,
                        next_day_max_drawdown = EXCLUDED.next_day_max_drawdown,
                        outcome_label = EXCLUDED.outcome_label,
                        outcome_source = EXCLUDED.outcome_source,
                        next_1d_return = EXCLUDED.next_1d_return,
                        next_2d_return = EXCLUDED.next_2d_return,
                        next_3d_return = EXCLUDED.next_3d_return,
                        next_5d_return = EXCLUDED.next_5d_return,
                        max_return_3d = EXCLUDED.max_return_3d,
                        max_return_5d = EXCLUDED.max_return_5d,
                        max_drawdown_3d = EXCLUDED.max_drawdown_3d,
                        max_drawdown_5d = EXCLUDED.max_drawdown_5d,
                        hit_limit_up_3d = EXCLUDED.hit_limit_up_3d,
                        hit_limit_up_5d = EXCLUDED.hit_limit_up_5d,
                        is_win_1d = EXCLUDED.is_win_1d,
                        is_win_3d = EXCLUDED.is_win_3d,
                        is_win_5d = EXCLUDED.is_win_5d,
                        loss_over_5pct = EXCLUDED.loss_over_5pct,
                        validation_status = EXCLUDED.validation_status,
                        validation_error = EXCLUDED.validation_error,
                        validated_at = NOW()
                    """,
                    [
                        str(v["signal_id"]), str(v["run_id"]), str(v["strategy_id"]), str(v["strategy_version"]),
                        v["trade_date"], str(v["stock_id"]), str(v.get("signal_level") or ""), _safe_float(v.get("score")),
                        v.get("buy_ref_date"), _safe_float(v.get("buy_ref_price")),
                        v.get("next_day_touch_limit_up"), v.get("next_day_sealed_limit_up"),
                        _safe_float(v.get("next_day_open_pct")), _safe_float(v.get("next_day_high_pct")), _safe_float(v.get("next_day_close_pct")),
                        int(v.get("next_day_open_board_count")) if v.get("next_day_open_board_count") is not None else None,
                        _safe_float(v.get("next_day_max_drawdown")),
                        str(v.get("outcome_label") or OUTCOME_D_NO_DATA), str(v.get("outcome_source") or "missing"),
                        _safe_float(v.get("next_1d_return")), _safe_float(v.get("next_2d_return")), _safe_float(v.get("next_3d_return")), _safe_float(v.get("next_5d_return")),
                        _safe_float(v.get("max_return_3d")), _safe_float(v.get("max_return_5d")), _safe_float(v.get("max_drawdown_3d")), _safe_float(v.get("max_drawdown_5d")),
                        v.get("hit_limit_up_3d"), v.get("hit_limit_up_5d"),
                        v.get("is_win_1d"), v.get("is_win_3d"), v.get("is_win_5d"),
                        v.get("loss_over_5pct"),
                        str(v.get("validation_status", "ok")), v.get("validation_error"),
                    ],
                )
                written += 1
            except Exception as exc:
                logger.exception("Failed to write one_to_two validation for %s", v.get("signal_id"))
                raise RuntimeError("failed to write one_to_two signal validations") from exc
        if written != len(validations):
            raise RuntimeError("failed to write one_to_two signal validations")
        return written

    async def _delete_run_validations(self, run_id: str, strategy_id: str, strategy_version: str) -> None:
        try:
            await self._gw._client.execute_query(
                "DELETE FROM strategy_signal_validation WHERE run_id = $1 AND strategy_id = $2 AND strategy_version = $3",
                [run_id, strategy_id, strategy_version],
            )
        except Exception as exc:
            logger.exception("Failed to delete OneToTwo validations for run_id=%s", run_id)
            raise RuntimeError("failed to delete existing one_to_two validations") from exc

    async def _get_next_trade_date(self, candidate_trade_date: date) -> date | None:
        next_date = candidate_trade_date + timedelta(days=1)
        for _ in range(10):
            cal = await self._read.get_trade_calendar(next_date)
            if cal and getattr(cal, "calendar_is_open", False):
                return next_date
            next_date += timedelta(days=1)
        return None

    async def _load_t1_bars(self, trade_date: date, stock_id: str) -> list[Any]:
        try:
            return await self._read.get_stock_daily_bars(trade_date, stock_ids=[stock_id])
        except Exception:
            return []

    def _select_bar_for_stock(self, bars: list[Any], stock_id: str) -> Any | None:
        prefix = stock_id.split(".")[0]
        for bar in bars:
            bar_stock_id = str(getattr(bar, "stock_id", "") or "")
            if bar_stock_id == stock_id or bar_stock_id.startswith(prefix):
                return bar
        return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _pct(value: Decimal | None, base: Decimal | None) -> float | None:
    if value is None or base is None or base == Decimal("0"):
        return None
    try:
        return float((value - base) / base)
    except Exception:
        return None


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "_asdict"):
        return dict(row._asdict())
    if hasattr(row, "__dict__"):
        return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
    return dict(row)

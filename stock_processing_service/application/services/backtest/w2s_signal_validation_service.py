"""Signal validation service for W2S backtest.

Computes forward returns (1/3/5 day), max drawdown, hit_limit_up,
loss_over_5pct for each signal. Writes to strategy_signal_validation.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class W2SSignalValidationService:
    """Compute forward returns for strategy signals."""

    def __init__(self, read_ports: Any, gateway: Any) -> None:
        self._read = read_ports
        self._gw = gateway

    async def validate(
        self,
        run_id: str,
        *,
        look_forward_days: tuple[int, ...] = (1, 2, 3, 5),
    ) -> dict[str, Any]:
        """Validate all signals for a run_id against future daily bars."""

        # Delete existing validations for this run (idempotent)
        await self._delete_run_validations(run_id)

        signals = await self._load_signals(run_id)
        if not signals:
            return {"run_id": run_id, "validated_count": 0, "written": 0, "warning": "No signals found"}

        max_fwd = max(look_forward_days)
        validations: list[dict[str, Any]] = []
        errors = 0

        for signal in signals:
            try:
                val = await self._validate_one_signal(
                    signal=signal,
                    look_forward_days=look_forward_days,
                    max_forward_days=max_fwd,
                )
                if val:
                    validations.append(val)
            except Exception as exc:
                errors += 1
                logger.warning("Failed to validate signal %s: %s", signal.get("signal_id"), exc)

        written = await self._write_validations(validations)
        logger.info("Signal validation: %d written (errors=%d) for run_id=%s", written, errors, run_id)

        await self._update_run_validated_count(run_id, len(validations), written)

        return {
            "run_id": run_id,
            "validated_count": len(validations),
            "written": written,
            "errors": errors,
        }

    async def _validate_one_signal(
        self,
        signal: dict[str, Any],
        look_forward_days: tuple[int, ...],
        max_forward_days: int,
    ) -> dict[str, Any] | None:
        signal_id = str(signal.get("signal_id") or "")
        stock_id = str(signal.get("stock_id") or "")
        trade_date = _parse_date(signal.get("trade_date"))

        if not stock_id or not trade_date:
            return None

        # Buy reference: T+1 open (next trade day)
        buy_ref_date, buy_ref_price = await self._get_buy_reference(stock_id, trade_date)
        if buy_ref_date is None or buy_ref_price is None:
            return {
                "signal_id": signal_id,
                "run_id": signal.get("run_id"),
                "strategy_id": signal.get("strategy_id", "weak_to_strong"),
                "strategy_version": signal.get("strategy_version", "w2s_v0.1"),
                "trade_date": trade_date,
                "stock_id": stock_id,
                "signal_level": str(signal.get("signal_level") or ""),
                "score": _safe_float(signal.get("score")),
                "buy_ref_date": trade_date + timedelta(days=1),
                "buy_ref_price": None,
                "next_1d_return": None, "next_2d_return": None,
                "next_3d_return": None, "next_5d_return": None,
                "max_return_3d": None, "max_return_5d": None,
                "max_drawdown_3d": None, "max_drawdown_5d": None,
                "hit_limit_up_3d": None, "hit_limit_up_5d": None,
                "is_win_1d": None, "is_win_3d": None, "is_win_5d": None,
                "loss_over_5pct": None,
                "validation_status": "skipped",
                "validation_error": "no_buy_reference",
            }

        # Load forward bars
        end_date = buy_ref_date + timedelta(days=max_forward_days * 2)
        try:
            bars = await self._read.get_stock_daily_bars_range(
                buy_ref_date, end_date, stock_ids=[stock_id]
            )
        except Exception:
            bars = []

        if not bars:
            return {
                "signal_id": signal_id,
                "run_id": signal.get("run_id"),
                "strategy_id": signal.get("strategy_id", "weak_to_strong"),
                "strategy_version": signal.get("strategy_version", "w2s_v0.1"),
                "trade_date": trade_date,
                "stock_id": stock_id,
                "signal_level": str(signal.get("signal_level") or ""),
                "score": _safe_float(signal.get("score")),
                "buy_ref_date": buy_ref_date,
                "buy_ref_price": float(buy_ref_price),
                "next_1d_return": None, "next_2d_return": None,
                "next_3d_return": None, "next_5d_return": None,
                "max_return_3d": None, "max_return_5d": None,
                "max_drawdown_3d": None, "max_drawdown_5d": None,
                "hit_limit_up_3d": None, "hit_limit_up_5d": None,
                "is_win_1d": None, "is_win_3d": None, "is_win_5d": None,
                "loss_over_5pct": None,
                "validation_status": "skipped",
                "validation_error": "no_forward_bars",
            }

        # Sort bars by date
        bars_sorted = sorted(bars, key=lambda b: b.trade_date)

        returns = self._compute_forward_returns(bars_sorted, buy_ref_price, look_forward_days)

        return {
            "signal_id": signal_id,
            "run_id": signal.get("run_id"),
            "strategy_id": signal.get("strategy_id", "weak_to_strong"),
            "strategy_version": signal.get("strategy_version", "w2s_v0.1"),
            "trade_date": trade_date,
            "stock_id": stock_id,
            "signal_level": str(signal.get("signal_level") or ""),
            "score": _safe_float(signal.get("score")),
            "buy_ref_date": buy_ref_date,
            "buy_ref_price": float(buy_ref_price),
            **{f"next_{d}d_return": returns.get(f"next_{d}d_return") for d in look_forward_days},
            "max_return_3d": returns.get("max_return_3d"),
            "max_return_5d": returns.get("max_return_5d"),
            "max_drawdown_3d": returns.get("max_drawdown_3d"),
            "max_drawdown_5d": returns.get("max_drawdown_5d"),
            "hit_limit_up_3d": returns.get("hit_limit_up_3d"),
            "hit_limit_up_5d": returns.get("hit_limit_up_5d"),
            **{f"is_win_{d}d": returns.get(f"is_win_{d}d") for d in look_forward_days},
            "loss_over_5pct": returns.get("loss_over_5pct"),
            "validation_status": "ok",
            "validation_error": None,
        }

    def _compute_forward_returns(
        self,
        bars: list[Any],
        buy_ref_price: Decimal,
        look_forward_days: tuple[int, ...],
    ) -> dict[str, Any]:
        """Compute forward returns from a list of bars using buy_ref_price as entry."""
        result: dict[str, Any] = {
            f"next_{d}d_return": None for d in look_forward_days
        }
        result.update({
            "max_return_3d": None,
            "max_return_5d": None,
            "max_drawdown_3d": None,
            "max_drawdown_5d": None,
            "hit_limit_up_3d": False,
            "hit_limit_up_5d": False,
            "is_win_1d": False,
            "is_win_3d": False,
            "is_win_5d": False,
            "loss_over_5pct": False,
        })

        if not bars or buy_ref_price is None or buy_ref_price == Decimal("0"):
            return result

        bp = float(buy_ref_price)

        for i, bar in enumerate(bars):
            close = float(getattr(bar, "close_price", 0) or 0)
            high = float(getattr(bar, "high_price", 0) or 0)
            low = float(getattr(bar, "low_price", 0) or 0)
            limit_up_price = float(getattr(bar, "limit_up_price", 999999) or 999999)

            if close <= 0:
                continue

            day_return = (close - bp) / bp

            day_index = i + 1
            if day_index == 1 and "next_1d_return" in result:
                result["next_1d_return"] = day_return
            if day_index == 2 and "next_2d_return" in result:
                result["next_2d_return"] = day_return
            if day_index == 3 and "next_3d_return" in result:
                result["next_3d_return"] = day_return
            if day_index == 5 and "next_5d_return" in result:
                result["next_5d_return"] = day_return

            # Track cumulative max return and drawdown
            if day_index <= 3:
                if result.get("max_return_3d") is None or day_return > result["max_return_3d"]:
                    result["max_return_3d"] = day_return
                dd = (low - bp) / bp
                if result.get("max_drawdown_3d") is None or dd < result["max_drawdown_3d"]:
                    result["max_drawdown_3d"] = dd
                if high >= limit_up_price:
                    result["hit_limit_up_3d"] = True

            if day_index <= 5:
                if result.get("max_return_5d") is None or day_return > result["max_return_5d"]:
                    result["max_return_5d"] = day_return
                dd = (low - bp) / bp
                if result.get("max_drawdown_5d") is None or dd < result["max_drawdown_5d"]:
                    result["max_drawdown_5d"] = dd
                if high >= limit_up_price:
                    result["hit_limit_up_5d"] = True

        # Win/loss flags
        if result.get("next_1d_return") is not None and result["next_1d_return"] > 0:
            result["is_win_1d"] = True
        if result.get("next_3d_return") is not None and result["next_3d_return"] > 0:
            result["is_win_3d"] = True
        if result.get("next_5d_return") is not None and result["next_5d_return"] > 0:
            result["is_win_5d"] = True
        if result.get("max_drawdown_5d") is not None and result["max_drawdown_5d"] < -0.05:
            result["loss_over_5pct"] = True

        return result

    async def _get_buy_reference(
        self,
        stock_id: str,
        candidate_trade_date: date,
    ) -> tuple[date | None, Decimal | None]:
        """Get T+1 open price as buy reference."""
        # Find next trade day
        next_date = candidate_trade_date + timedelta(days=1)
        for _ in range(10):
            cal = await self._read.get_trade_calendar(next_date)
            if cal and cal.calendar_is_open:
                break
            next_date += timedelta(days=1)
        else:
            return None, None

        try:
            bars = await self._read.get_stock_daily_bars(next_date, stock_ids=[stock_id])
        except Exception:
            return next_date, None

        for bar in bars:
            if bar.stock_id == stock_id or bar.stock_id.startswith(stock_id.split(".")[0]):
                open_price = getattr(bar, "open_price", None)
                limit_up_price = getattr(bar, "limit_up_price", None)
                if open_price is not None and limit_up_price is not None and open_price >= limit_up_price:
                    # 一字涨停 → buy reference exists but may be unfillable
                    return next_date, open_price
                if open_price is not None:
                    return next_date, open_price

        return next_date, None

    async def _load_signals(self, run_id: str) -> list[dict[str, Any]]:
        fn = getattr(self._gw, "get_strategy_signal_daily_by_run", None)
        if callable(fn):
            return await fn(run_id)
        try:
            rows = await self._gw.query(
                "SELECT * FROM strategy_signal_daily WHERE run_id = $1",
                [run_id],
            )
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.error("Failed to load signals for run_id=%s: %s", run_id, exc)
            return []

    async def _write_validations(self, validations: list[dict[str, Any]]) -> int:
        if not validations:
            return 0
        fn = getattr(self._gw, "upsert_strategy_signal_validation_rows", None)
        if callable(fn):
            return await fn(validations)
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
                        $11, $12, $13, $14,
                        $15, $16, $17, $18,
                        $19, $20,
                        $21, $22, $23,
                        $24,
                        $25, $26
                    )
                    ON CONFLICT (signal_id) DO UPDATE SET
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
                        _safe_float(v.get("next_1d_return")), _safe_float(v.get("next_2d_return")),
                        _safe_float(v.get("next_3d_return")), _safe_float(v.get("next_5d_return")),
                        _safe_float(v.get("max_return_3d")), _safe_float(v.get("max_return_5d")),
                        _safe_float(v.get("max_drawdown_3d")), _safe_float(v.get("max_drawdown_5d")),
                        bool(v.get("hit_limit_up_3d")), bool(v.get("hit_limit_up_5d")),
                        bool(v.get("is_win_1d")), bool(v.get("is_win_3d")), bool(v.get("is_win_5d")),
                        bool(v.get("loss_over_5pct")),
                        str(v.get("validation_status", "ok")), v.get("validation_error"),
                    ],
                )
                written += 1
            except Exception as exc:
                logger.error("Failed to write validation for %s: %s", v.get("signal_id"), exc)
        return written

    async def _delete_run_validations(self, run_id: str) -> None:
        try:
            await self._gw._client.execute_query(
                "DELETE FROM strategy_signal_validation WHERE run_id = $1",
                [run_id],
            )
        except Exception as exc:
            logger.warning("Failed to delete validations for run_id=%s: %s", run_id, exc)

    async def _update_run_validated_count(self, run_id: str, validated: int, written: int) -> None:
        try:
            await self._gw._client.execute_query(
                "UPDATE w2s_backtest_run SET validated_count = $1, status = 'completed', completed_at = NOW() WHERE run_id = $2",
                [validated, run_id],
            )
        except Exception:
            pass


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
    except (ValueError, TypeError):
        return None


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "_asdict"):
        return dict(row._asdict())
    if hasattr(row, "__dict__"):
        return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
    return dict(row)

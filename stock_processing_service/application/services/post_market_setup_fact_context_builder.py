from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from typing import Any

from stock_processing_service.contracts.dto.post_market_setup_context_dto import (
    PostMarketSetupFactContext,
    SetupFactContextBuildError,
    SourceStatus,
)


class PostMarketSetupFactContextBuilder:
    """Build post-market setup facts from canonical read sources only."""

    def __init__(self, read_port: Any) -> None:
        self._read = read_port

    async def build(self, trade_date: date, source_doc: dict[str, Any] | None = None) -> PostMarketSetupFactContext:
        calendar = await self._call_required(
            "trade_calendar",
            self._read.get_trade_calendar(trade_date),
            allow_empty=False,
        )
        if not calendar or not getattr(calendar, "next_trade_date", None):
            raise SetupFactContextBuildError("trade_calendar missing next_trade_date")
        watch_date = calendar.next_trade_date

        source_doc = dict(source_doc or {})
        market_regime = self._extract_required_dict(source_doc, ("market_regime_review", "market_regime"))
        trading_principle = self._extract_required_dict(source_doc, ("trading_principle", "trading_principle_review"))
        if not market_regime:
            raise SetupFactContextBuildError("setup_source missing market_regime")
        if not trading_principle:
            raise SetupFactContextBuildError("setup_source missing trading_principle")

        active_mainlines = self._normalize_rows(
            await self._call_optional(
                "active_mainlines",
                self._read.get_active_confirmed_mainlines(trade_date=trade_date, limit=100),
            )
        )
        active_subject_keys = self._expand_active_subject_keys(active_mainlines)

        subject_board_stats = self._normalize_rows(
            await self._call_optional(
                "subject_board_stats",
                self._read.get_subject_board_stats(trade_date=trade_date),
            )
        )
        subject_market_breadth = {
            str(r.get("subject_key") or ""): dict(r)
            for r in subject_board_stats
            if str(r.get("subject_key") or "").strip()
        }

        lookback_start = trade_date - timedelta(days=10)
        stock_daily_bars = self._normalize_rows(
            await self._call_optional(
                "stock_daily_bars_range",
                self._read.get_stock_daily_bars_range(start_date=lookback_start, end_date=trade_date, stock_ids=None),
            )
        )
        subject_stock_rows = self._normalize_rows(
            await self._call_optional(
                "subject_stock_daily_bars_range",
                self._read.get_subject_stock_daily_bars_range(
                    start_date=lookback_start,
                    end_date=trade_date,
                    stock_ids=None,
                    subject_keys=None,
                ),
            )
        )

        mainline_state_rows = self._normalize_rows(
            await self._call_optional(
                "mainline_state_daily",
                self._read.get_mainline_state_daily(trade_date, list(active_subject_keys) or []),
            )
        )
        lifecycle_by_subject = {
            str(r.get("subject_key") or ""): dict(r)
            for r in mainline_state_rows
            if str(r.get("subject_key") or "").strip()
        }

        strong_hotspot_subjects = self._extract_hotspot_subjects(source_doc)
        pressure_by_stock = self._extract_map(source_doc, "pressure_by_stock")
        ma_pattern_by_stock = self._extract_map(source_doc, "ma_pattern_by_stock")

        limit_up_rows = [
            row for row in stock_daily_bars
            if self._date_str(row.get("trade_date")) == trade_date.isoformat()
            and self._is_limit_up(row)
        ]

        return PostMarketSetupFactContext(
            trade_date=trade_date.isoformat(),
            watch_date=watch_date.isoformat(),
            active_mainlines=active_mainlines,
            strong_hotspot_subjects=strong_hotspot_subjects,
            active_subject_keys=active_subject_keys,
            lifecycle_by_subject=lifecycle_by_subject,
            market_regime=market_regime,
            trading_principle=trading_principle,
            subject_stock_rows=subject_stock_rows,
            stock_daily_bars=stock_daily_bars,
            limit_up_rows=limit_up_rows,
            subject_market_breadth=subject_market_breadth,
            prior_daily_bars={},
            pressure_by_stock=pressure_by_stock,
            ma_pattern_by_stock=ma_pattern_by_stock,
            diagnostics=SourceStatus(
                source_status={
                    "trade_calendar": "ready",
                    "market_regime": "ready_non_empty" if market_regime else "missing",
                    "trading_principle": "ready_non_empty" if trading_principle else "missing",
                    "active_mainlines": "ready_non_empty" if active_mainlines else "ready_empty",
                    "subject_board_stats": "ready_non_empty" if subject_board_stats else "ready_empty",
                    "stock_daily_bars_range": "ready_non_empty" if stock_daily_bars else "ready_empty",
                    "subject_stock_daily_bars_range": "ready_non_empty" if subject_stock_rows else "ready_empty",
                    "mainline_state_daily": "ready_non_empty" if mainline_state_rows else "ready_empty",
                    "strong_hotspot_subjects": "derived_non_empty" if strong_hotspot_subjects else "derived_empty",
                },
                blocking_errors=[],
                non_blocking_warnings=[],
            ),
        )

    async def _call_required(self, name: str, awaitable: Any, *, allow_empty: bool = True) -> Any:
        try:
            value = await awaitable
        except Exception as exc:
            raise SetupFactContextBuildError(f"{name}: {exc}") from exc
        if value is None and not allow_empty:
            raise SetupFactContextBuildError(f"{name}: missing required source")
        return value

    async def _call_optional(self, name: str, awaitable: Any) -> Any:
        try:
            return await awaitable
        except Exception as exc:
            raise SetupFactContextBuildError(f"{name}: {exc}") from exc

    def _normalize_rows(self, rows: Any) -> list[dict[str, Any]]:
        if not rows:
            return []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if row is None:
                continue
            if isinstance(row, dict):
                normalized.append(dict(row))
            elif is_dataclass(row):
                normalized.append(asdict(row))
            else:
                normalized.append(dict(getattr(row, "__dict__", {})))
        return normalized

    def _extract_required_dict(self, source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        for key in keys:
            value = source.get(key)
            if isinstance(value, dict) and value:
                return dict(value)
        return {}

    def _extract_map(self, source: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
        value = source.get(key)
        if isinstance(value, dict):
            return {str(k): dict(v) for k, v in value.items() if isinstance(v, dict)}
        return {}

    def _extract_hotspot_subjects(self, report_context: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("strong_hotspot_subjects", "hotspot_subjects", "mainline_hotspots"):
            value = report_context.get(key)
            if isinstance(value, list):
                rows = []
                for item in value:
                    if isinstance(item, dict):
                        rows.append(dict(item))
                if rows:
                    return rows
        return []

    def _expand_active_subject_keys(self, active_mainlines: list[dict[str, Any]]) -> set[str]:
        result: set[str] = set()
        for row in active_mainlines:
            for key_name in ("canonical_subject_key", "subject_key"):
                if row.get(key_name):
                    result.add(str(row[key_name]))
            for key_name in ("related_subject_keys_json", "branch_subject_keys_json"):
                values = row.get(key_name) or []
                if isinstance(values, list):
                    result.update(str(v) for v in values if v)
        return result

    def _is_limit_up(self, row: dict[str, Any]) -> bool:
        pct = row.get("pct_chg")
        try:
            if pct is not None and float(pct) >= 9.8:
                return True
        except Exception:
            pass
        close_price = row.get("close_price")
        limit_up_price = row.get("limit_up_price")
        try:
            if close_price is not None and limit_up_price is not None and float(close_price) >= float(limit_up_price):
                return True
        except Exception:
            pass
        return bool(row.get("limit_up"))

    def _date_str(self, value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return str(value.isoformat())
        return str(value)

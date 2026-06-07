from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from typing import Any

from stock_processing_service.application.services.event_theme_stock_authenticity_service import (
    EventThemeStockAuthenticityService,
)
from stock_processing_service.application.services.golden_spider_pattern_service import (
    GoldenSpiderPatternService,
)
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

        lookback_start = trade_date - timedelta(days=30)
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
        confirmed_hotspot_keys = self._extract_confirmed_hotspot_keys(source_doc)
        strong_hotspot_rank = self._build_subject_rank(strong_hotspot_subjects)
        confirmed_hotspot_rank = self._build_confirmed_hotspot_rank(strong_hotspot_subjects)
        subject_priority_rank = self._build_subject_priority_rank(strong_hotspot_subjects, confirmed_hotspot_keys)
        pressure_by_stock = self._extract_map(source_doc, "pressure_by_stock")
        ma_pattern_by_stock = self._extract_map(source_doc, "ma_pattern_by_stock")

        subject_authenticity_by_subject = await self._build_subject_authenticity(
            trade_date=trade_date,
            source_doc=source_doc,
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
            strong_hotspot_subjects=strong_hotspot_subjects,
        )
        stock_subject_authenticity_by_pair = await self._build_stock_subject_authenticity(
            trade_date=trade_date,
            source_doc=source_doc,
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
            strong_hotspot_subjects=strong_hotspot_subjects,
        )
        kline_pattern_quality_by_stock = await self._build_kline_pattern_quality(
            trade_date=trade_date,
            stock_daily_bars=stock_daily_bars,
        )

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
            confirmed_hotspot_keys=confirmed_hotspot_keys,
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
            subject_authenticity_by_subject=subject_authenticity_by_subject,
            stock_subject_authenticity_by_pair=stock_subject_authenticity_by_pair,
            kline_pattern_quality_by_stock=kline_pattern_quality_by_stock,
            confirmed_hotspot_rank=confirmed_hotspot_rank,
            strong_hotspot_rank=strong_hotspot_rank,
            subject_priority_rank=subject_priority_rank,
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
                    "confirmed_hotspot_keys": "derived_non_empty" if confirmed_hotspot_keys else "derived_empty",
                    "subject_authenticity_by_subject": "derived_non_empty" if subject_authenticity_by_subject else "derived_empty",
                    "stock_subject_authenticity_by_pair": "derived_non_empty" if stock_subject_authenticity_by_pair else "derived_empty",
                    "kline_pattern_quality_by_stock": "derived_non_empty" if kline_pattern_quality_by_stock else "derived_empty",
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

    def _extract_confirmed_hotspot_keys(self, report_context: dict[str, Any]) -> set[str]:
        result: set[str] = set()
        for key in ("strong_hotspot_subjects", "hotspot_subjects", "mainline_hotspots"):
            value = report_context.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or item.get("watch_status") or "").strip()
                if source != "confirmed_mainline":
                    continue
                subject_key = str(item.get("subject_key") or "").strip()
                if subject_key:
                    result.add(subject_key)
        return result

    def _build_subject_rank(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        rank: dict[str, int] = {}
        for idx, row in enumerate(rows):
            subject_key = str(row.get("subject_key") or "").strip()
            if subject_key and subject_key not in rank:
                rank[subject_key] = idx
        return rank

    def _build_confirmed_hotspot_rank(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        rank: dict[str, int] = {}
        idx = 0
        for row in rows:
            subject_key = str(row.get("subject_key") or "").strip()
            if not subject_key:
                continue
            source = str(row.get("source") or row.get("watch_status") or "").strip()
            if source != "confirmed_mainline":
                continue
            if subject_key not in rank:
                rank[subject_key] = idx
                idx += 1
        return rank

    def _build_subject_priority_rank(self, rows: list[dict[str, Any]], confirmed_hotspot_keys: set[str]) -> dict[str, int]:
        confirmed_rank: dict[str, int] = {}
        fallback_rank: dict[str, int] = {}
        confirmed_idx = 0
        fallback_idx = 0
        for row in rows:
            subject_key = str(row.get("subject_key") or "").strip()
            if not subject_key:
                continue
            if subject_key in confirmed_hotspot_keys:
                if subject_key not in confirmed_rank:
                    confirmed_rank[subject_key] = confirmed_idx
                    confirmed_idx += 1
                continue
            if subject_key not in fallback_rank:
                fallback_rank[subject_key] = fallback_idx
                fallback_idx += 1
        base = len(confirmed_rank) + 1000
        result = dict(confirmed_rank)
        for subject_key, idx in fallback_rank.items():
            result[subject_key] = base + idx
        return result

    async def _build_subject_authenticity(
        self,
        *,
        trade_date: date,
        source_doc: dict[str, Any],
        subject_stock_rows: list[dict[str, Any]],
        subject_market_breadth: dict[str, dict[str, Any]],
        active_subject_keys: set[str],
        strong_hotspot_subjects: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        subject_keys = self._collect_subject_keys(
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
            strong_hotspot_subjects=strong_hotspot_subjects,
        )
        if not subject_keys:
            return {}
        service = EventThemeStockAuthenticityService(self._read)
        return await service.build(
            trade_date=trade_date,
            subject_keys=subject_keys,
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
        )

    async def _build_kline_pattern_quality(
        self,
        *,
        trade_date: date,
        stock_daily_bars: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        if not stock_daily_bars:
            return {}
        stock_ids = self._collect_stock_ids(stock_daily_bars)
        if not stock_ids:
            return {}
        bars_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in stock_daily_bars:
            stock_id = self._stock_key(row.get("stock_id"))
            if stock_id:
                bars_by_stock[stock_id].append(dict(row))
        service = GoldenSpiderPatternService(self._read)
        return await service.build(
            trade_date=trade_date,
            stock_ids=stock_ids,
            stock_bars_by_stock=bars_by_stock,
        )

    async def _build_stock_subject_authenticity(
        self,
        *,
        trade_date: date,
        source_doc: dict[str, Any],
        subject_stock_rows: list[dict[str, Any]],
        subject_market_breadth: dict[str, dict[str, Any]],
        active_subject_keys: set[str],
        strong_hotspot_subjects: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        subject_keys = self._collect_subject_keys(
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
            strong_hotspot_subjects=strong_hotspot_subjects,
        )
        if not subject_keys:
            return {}
        service = EventThemeStockAuthenticityService(self._read)
        return await service.build_stock_subject_authenticity(
            trade_date=trade_date,
            subject_keys=subject_keys,
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
        )

    def _collect_subject_keys(
        self,
        *,
        subject_stock_rows: list[dict[str, Any]],
        subject_market_breadth: dict[str, dict[str, Any]],
        active_subject_keys: set[str],
        strong_hotspot_subjects: list[dict[str, Any]],
    ) -> list[str]:
        keys: list[str] = []
        for sk in active_subject_keys:
            if sk and sk not in keys:
                keys.append(str(sk))
        for sk in subject_market_breadth.keys():
            if sk and sk not in keys:
                keys.append(str(sk))
        for row in subject_stock_rows:
            sk = self._stock_key(row.get("subject_key"))
            if sk and sk not in keys:
                keys.append(sk)
        for row in strong_hotspot_subjects:
            sk = self._stock_key(row.get("subject_key"))
            if sk and sk not in keys:
                keys.append(sk)
        return keys

    def _collect_stock_ids(self, rows: list[dict[str, Any]]) -> list[str]:
        stock_ids: list[str] = []
        for row in rows:
            sid = self._stock_key(row.get("stock_id"))
            if sid and sid not in stock_ids:
                stock_ids.append(sid)
        return stock_ids

    @staticmethod
    def _stock_key(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text.split(".")[0]

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

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.application.services.post_market_setup_fact_context_builder import (
    PostMarketSetupFactContextBuilder,
)
from stock_processing_service.contracts.dto.post_market_setup_context_dto import (
    SetupFactContextBuildError,
)


BLOCK_GENERATION_THRESHOLD = 0.95


@dataclass
class OneToTwoBacktestDataQualityReport:
    start_date: date
    end_date: date
    open_days_total: int = 0
    generation_ready_days: int = 0
    validation_ready_days: int = 0
    missing_outcome_days: int = 0
    daily_bar_coverage_ratio: float = 0.0
    subject_stock_coverage_ratio: float = 0.0
    mainline_context_coverage_ratio: float = 0.0
    limit_up_fact_coverage_ratio: float = 0.0
    next_day_bar_coverage_ratio: float = 0.0
    blocked: bool = False
    block_reason: str = ""
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "open_days_total": self.open_days_total,
            "generation_ready_days": self.generation_ready_days,
            "validation_ready_days": self.validation_ready_days,
            "missing_outcome_days": self.missing_outcome_days,
            "daily_bar_coverage_ratio": self.daily_bar_coverage_ratio,
            "subject_stock_coverage_ratio": self.subject_stock_coverage_ratio,
            "mainline_context_coverage_ratio": self.mainline_context_coverage_ratio,
            "limit_up_fact_coverage_ratio": self.limit_up_fact_coverage_ratio,
            "next_day_bar_coverage_ratio": self.next_day_bar_coverage_ratio,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "blocking_errors": list(self.blocking_errors),
            "warnings": list(self.warnings),
            "diagnostics": dict(self.diagnostics),
        }


class OneToTwoBacktestDataQualityService:
    """Fail-loud data quality gate for OneToTwo backtest."""

    def __init__(
        self,
        read_port: Any,
        context_builder: PostMarketSetupFactContextBuilder | None = None,
    ) -> None:
        self._read = read_port
        self._context_builder = context_builder or PostMarketSetupFactContextBuilder(read_port)

    async def check(self, start_date: date, end_date: date) -> dict[str, Any]:
        report = OneToTwoBacktestDataQualityReport(start_date=start_date, end_date=end_date)
        generation_pass = 0
        subject_stock_pass = 0
        mainline_pass = 0
        limit_up_pass = 0
        validation_pass = 0

        trade_dates = await self._load_trade_dates(start_date, end_date)
        report.open_days_total = len(trade_dates)
        for current in trade_dates:
            try:
                source_doc = await self._load_latest_report_context(current)
            except Exception as exc:
                report.blocking_errors.append(f"{current.isoformat()}: get_existing_post_market_recap_snapshot: {exc}")
                continue

            try:
                ctx = await self._context_builder.build(current, source_doc=source_doc)

                source_status = dict(ctx.diagnostics.source_status or {})
                if self._generation_ready(source_status):
                    generation_pass += 1
                else:
                    report.blocking_errors.append(
                        f"{current.isoformat()}: generation sources incomplete -> {source_status}"
                    )

                if source_status.get("subject_stock_daily_bars_range") in {"ready_non_empty", "ready"}:
                    subject_stock_pass += 1
                if bool(ctx.active_mainlines) and bool(ctx.lifecycle_by_subject):
                    mainline_pass += 1
                if bool(ctx.limit_up_rows):
                    limit_up_pass += 1

                watch_date = self._parse_date(getattr(ctx, "watch_date", None))
                if watch_date is None:
                    report.blocking_errors.append(f"{current.isoformat()}: missing watch_date in setup context")
                else:
                    watch_bars = await self._safe_get_stock_bars(watch_date, None)
                    if watch_bars:
                        validation_pass += 1
                    else:
                        report.missing_outcome_days += 1
            except SetupFactContextBuildError as exc:
                report.blocking_errors.append(f"{current.isoformat()}: context_build_failed: {exc}")
            except Exception as exc:
                report.blocking_errors.append(f"{current.isoformat()}: {exc}")

        report.generation_ready_days = generation_pass
        report.daily_bar_coverage_ratio = generation_pass / report.open_days_total if report.open_days_total else 0.0
        report.subject_stock_coverage_ratio = subject_stock_pass / report.open_days_total if report.open_days_total else 0.0
        report.mainline_context_coverage_ratio = mainline_pass / report.open_days_total if report.open_days_total else 0.0
        report.limit_up_fact_coverage_ratio = limit_up_pass / report.open_days_total if report.open_days_total else 0.0
        report.validation_ready_days = validation_pass
        report.next_day_bar_coverage_ratio = validation_pass / report.open_days_total if report.open_days_total else 0.0

        report.blocked = bool(report.blocking_errors) or report.daily_bar_coverage_ratio < BLOCK_GENERATION_THRESHOLD
        if report.blocked and not report.block_reason:
            if report.daily_bar_coverage_ratio < BLOCK_GENERATION_THRESHOLD:
                report.block_reason = (
                    f"generation daily bar coverage {report.daily_bar_coverage_ratio:.1%} "
                    f"below {BLOCK_GENERATION_THRESHOLD:.0%}"
                )
            else:
                report.block_reason = "generation blocking errors present"

        if report.open_days_total < 30:
            report.warnings.append(
                f"观测日仅 {report.open_days_total} 天，统计区分度可能不足。"
            )
        if report.missing_outcome_days > 0:
            report.warnings.append(
                f"{report.missing_outcome_days} 个候选日缺少验证侧行情，后续 outcome 需标记 D_NO_DATA。"
            )

        return {
            "generation_quality": {
                "blocking": report.blocked,
                "daily_bar_coverage_ratio": report.daily_bar_coverage_ratio,
                "subject_stock_coverage_ratio": report.subject_stock_coverage_ratio,
                "mainline_context_coverage_ratio": report.mainline_context_coverage_ratio,
                "limit_up_fact_coverage_ratio": report.limit_up_fact_coverage_ratio,
                "blocking_errors": list(report.blocking_errors),
            },
            "validation_quality": {
                "blocking": False,
                "next_day_bar_coverage_ratio": report.next_day_bar_coverage_ratio,
                "missing_outcome_days": report.missing_outcome_days,
                "open_days_total": report.open_days_total,
            },
            "open_days_total": report.open_days_total,
            "generation_ready_days": report.generation_ready_days,
            "warnings": list(report.warnings),
            "blocking_errors": list(report.blocking_errors),
            "blocked": report.blocked,
            "block_reason": report.block_reason,
            "diagnostics": dict(report.diagnostics),
        }

    async def _load_latest_report_context(self, trade_date: date) -> dict[str, Any]:
        snapshot_loader = getattr(self._read, "get_existing_post_market_recap_snapshot", None)
        if callable(snapshot_loader):
            snapshot = await snapshot_loader(trade_date)
            if snapshot:
                recap_doc = getattr(snapshot, "recap_doc", None)
                if isinstance(recap_doc, dict) and recap_doc:
                    inner = recap_doc.get("recap_doc")
                    if isinstance(inner, dict) and inner:
                        return dict(inner)
                    return dict(recap_doc)
                payload = snapshot.get("payload") or {}
                if isinstance(payload, dict):
                    recap_doc = payload.get("recap_doc")
                    if isinstance(recap_doc, dict) and recap_doc:
                        return dict(recap_doc)
                    raise RuntimeError("missing recap_doc in latest post_market_recap_snapshot")
            raise RuntimeError("missing latest post_market_recap_snapshot")
        raise RuntimeError("read_port missing get_existing_post_market_recap_snapshot")

    async def _safe_get_trade_calendar(self, trade_date: date) -> Any | None:
        try:
            return await self._read.get_trade_calendar(trade_date)
        except Exception:
            return None

    async def _load_trade_dates(self, start_date: date, end_date: date) -> list[date]:
        try:
            rows = await self._read.get_stock_daily_bars_range(start_date, end_date, stock_ids=None)
        except Exception:
            rows = []
        dates = {
            self._parse_date(self._row_value(row, "trade_date"))
            for row in rows
            if self._parse_date(self._row_value(row, "trade_date")) is not None
        }
        return sorted(d for d in dates if d is not None)

    async def _safe_get_stock_bars(self, trade_date: date, stock_ids: list[str]) -> list[Any]:
        try:
            return await self._read.get_stock_daily_bars(trade_date, stock_ids=stock_ids or None)
        except Exception:
            return []

    def _generation_ready(self, source_status: dict[str, Any]) -> bool:
        required = (
            "market_regime",
            "trading_principle",
            "subject_board_stats",
            "stock_daily_bars_range",
            "subject_stock_daily_bars_range",
            "mainline_state_daily",
        )
        return all(str(source_status.get(key) or "") == "ready_non_empty" for key in required)

    def _parse_date(self, value: Any) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        if hasattr(value, "date"):
            maybe = value.date()
            if isinstance(maybe, date):
                return maybe
        return None

    def _row_value(self, row: Any, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

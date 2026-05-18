"""Data quality service for W2S backtest (v2 — candidate-date-aware).

Checks coverage of daily bars, candidate pools, auction data,
mainline features, and leader identity features.
Blocks validation if daily bar coverage on candidate dates < 95%.

Phase 0 adaptation:
  - No trade_calendar table → derives trading days from stock_daily_snapshot.
  - Coverage is measured on candidate dates, not all calendar dates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from stock_processing_service.ports.read_ports import StockReadPorts

logger = logging.getLogger(__name__)

BLOCK_DAILY_BAR_THRESHOLD = 0.95
WARN_AUCTION_THRESHOLD = 0.30
WARN_SAMPLE_MINIMUM = 30


@dataclass
class DataQualityReport:
    start_date: date
    end_date: date
    candidate_dates_total: int
    candidate_dates_missing: int
    total_candidates: int
    daily_bar_coverage_ratio: float  # on candidate dates
    auction_coverage_ratio: float
    auction_series_coverage_ratio: float
    mainline_feature_coverage_ratio: float
    leader_feature_coverage_ratio: float
    confirm_source_distribution: dict[str, int] = field(default_factory=dict)
    proxy_sample_ratio: float = 0.0
    unverifiable_signal_count: int = 0
    blocked: bool = False
    block_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "candidate_dates_total": self.candidate_dates_total,
            "candidate_dates_missing": self.candidate_dates_missing,
            "total_candidates": self.total_candidates,
            "daily_bar_coverage_ratio": self.daily_bar_coverage_ratio,
            "auction_coverage_ratio": self.auction_coverage_ratio,
            "auction_series_coverage_ratio": self.auction_series_coverage_ratio,
            "mainline_feature_coverage_ratio": self.mainline_feature_coverage_ratio,
            "leader_feature_coverage_ratio": self.leader_feature_coverage_ratio,
            "confirm_source_distribution": self.confirm_source_distribution,
            "proxy_sample_ratio": self.proxy_sample_ratio,
            "unverifiable_signal_count": self.unverifiable_signal_count,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "warnings": self.warnings,
            "diagnostics": self.diagnostics,
        }


class W2SDataQualityService:
    """Check data quality before running backtest.

    Phase 0 adaptation: derives trade dates from the bars table directly
    since trade_calendar may not exist yet. Coverage is measured on
    candidate dates, not all market dates.
    """

    def __init__(self, read_ports: StockReadPorts) -> None:
        self._read = read_ports

    async def check(
        self,
        start_date: date,
        end_date: date,
    ) -> DataQualityReport:
        """Run full data quality check for the date range."""
        report = DataQualityReport(
            start_date=start_date,
            end_date=end_date,
            candidate_dates_total=0,
            candidate_dates_missing=0,
            total_candidates=0,
            daily_bar_coverage_ratio=0.0,
            auction_coverage_ratio=0.0,
            auction_series_coverage_ratio=0.0,
            mainline_feature_coverage_ratio=0.0,
            leader_feature_coverage_ratio=0.0,
        )

        # Phase 0: collect candidate dates directly from candidate pool
        candidate_dates, total_candidates = await self._collect_candidates_for_range(start_date, end_date)
        report.diagnostics["candidate_dates"] = [d.isoformat() for d in candidate_dates]

        if not candidate_dates:
            report.blocked = True
            report.block_reason = (
                f"在 {start_date} 到 {end_date} 范围内没有找到任何弱转强候选数据。"
            )
            return report

        report.candidate_dates_total = len(candidate_dates)
        report.total_candidates = total_candidates

        # Check coverages on candidate dates only
        await self._check_daily_bar_coverage_on_dates(report, candidate_dates)
        await self._check_auction_coverage_on_dates(report, candidate_dates)
        await self._check_mainline_feature_coverage(report, candidate_dates)
        await self._check_leader_feature_coverage(report, candidate_dates)
        await self._compute_confirm_source_distribution(report, candidate_dates)

        # Hard gate: daily bar coverage < 95% on CANDIDATE dates → block
        if report.daily_bar_coverage_ratio < BLOCK_DAILY_BAR_THRESHOLD:
            report.blocked = True
            report.block_reason = (
                f"候选日日K行情覆盖率 {report.daily_bar_coverage_ratio:.1%} "
                f"低于最小阈值 {BLOCK_DAILY_BAR_THRESHOLD:.0%}，无法进行信号验证。"
            )

        # Warnings
        if report.total_candidates < WARN_SAMPLE_MINIMUM:
            report.warnings.append(
                f"总候选数仅 {report.total_candidates}，少于 {WARN_SAMPLE_MINIMUM}，"
                "统计结果可能不具显著性。"
            )

        if report.auction_coverage_ratio < WARN_AUCTION_THRESHOLD:
            report.warnings.append(
                f"竞价覆盖率仅 {report.auction_coverage_ratio:.1%}，"
                f"低于 {WARN_AUCTION_THRESHOLD:.0%}。"
                f"本次结果主要基于 daily_open_proxy，不等同真实竞价回测。"
            )

        if report.proxy_sample_ratio > 0.5:
            report.warnings.append(
                f"proxy/daily_open_proxy 样本占比 {report.proxy_sample_ratio:.1%}，"
                "当前结论不等同真实竞价回测。"
            )

        return report

    async def _collect_candidates_for_range(self, start: date, end: date) -> tuple[list[date], int]:
        """Collect candidate dates and total row count."""
        dates: list[date] = []
        total = 0
        current = start
        while current <= end:
            try:
                candidates = await self._read.get_w2s_candidate_inputs(current)
            except Exception:
                candidates = []
            if candidates:
                dates.append(current)
                total += len(candidates)
            current += timedelta(days=1)
        return dates, total

    async def _check_daily_bar_coverage_on_dates(self, report: DataQualityReport, candidate_dates: list[date]) -> None:
        """Check daily bar coverage on candidate dates only."""
        dates_with_bars = 0
        dates_without_bars = 0
        for td in candidate_dates:
            try:
                bars = await self._read.get_stock_daily_bars(td)
            except Exception:
                bars = []
            if bars:
                dates_with_bars += 1
            else:
                dates_without_bars += 1

        total = dates_with_bars + dates_without_bars
        report.daily_bar_coverage_ratio = dates_with_bars / total if total > 0 else 0.0
        report.diagnostics["candidate_dates_with_bars"] = dates_with_bars
        report.diagnostics["candidate_dates_without_bars"] = dates_without_bars

    async def _check_auction_coverage_on_dates(self, report: DataQualityReport, candidate_dates: list[date]) -> None:
        """Check auction snapshot coverage on candidate confirm dates."""
        dates_with_auction = 0
        dates_with_series = 0
        total = 0
        for td in candidate_dates:
            total += 1
            try:
                auctions = await self._read.get_stock_auction_snapshot(td)
            except Exception:
                auctions = []
            if auctions:
                dates_with_auction += 1
            has_series = any(
                getattr(a, "tail_auction_vwap", None) is not None
                for a in auctions
            )
            if has_series:
                dates_with_series += 1

        report.auction_coverage_ratio = dates_with_auction / total if total > 0 else 0.0
        report.auction_series_coverage_ratio = dates_with_series / total if total > 0 else 0.0
        report.diagnostics["candidate_dates_with_auction"] = dates_with_auction
        report.diagnostics["candidate_dates_with_auction_series"] = dates_with_series

    async def _check_mainline_feature_coverage(self, report: DataQualityReport, candidate_dates: list[date]) -> None:
        """Check mainline state feature coverage on candidate dates."""
        dates_with_mainline = 0
        total = 0
        for td in candidate_dates:
            total += 1
            # Get candidates for this date to extract subject_keys
            try:
                candidates = await self._read.get_w2s_candidate_inputs(td)
            except Exception:
                candidates = []
            subject_keys = list({
                str(c.get("subject_key") or "")
                for c in candidates
                if str(c.get("subject_key") or "").strip()
            })
            if not subject_keys:
                continue

            try:
                states = await self._read.get_mainline_state_daily(td, subject_keys)
            except Exception:
                states = []

            if states:
                dates_with_mainline += 1

        report.mainline_feature_coverage_ratio = dates_with_mainline / total if total > 0 else 0.0
        report.diagnostics["candidate_dates_with_mainline"] = dates_with_mainline

    async def _check_leader_feature_coverage(self, report: DataQualityReport, candidate_dates: list[date]) -> None:
        """Check leader identity feature coverage on candidate rows."""
        dates_with_leader = 0
        total = 0
        for td in candidate_dates:
            total += 1
            try:
                candidates = await self._read.get_w2s_candidate_inputs(td)
            except Exception:
                candidates = []
            has_leader_field = any(
                isinstance(c, dict) and c.get("is_leader") is not None
                for c in candidates
            )
            if has_leader_field:
                dates_with_leader += 1

        report.leader_feature_coverage_ratio = dates_with_leader / total if total > 0 else 0.0
        report.diagnostics["candidate_dates_with_leader"] = dates_with_leader

    async def _compute_confirm_source_distribution(self, report: DataQualityReport, candidate_dates: list[date]) -> None:
        """Estimate confirm_source distribution across candidate confirm dates."""
        dist: dict[str, int] = {"real_auction": 0, "auction_snapshot": 0, "daily_open_proxy": 0, "missing": 0}
        total_signals = 0

        for td in candidate_dates:
            try:
                candidates = await self._read.get_w2s_candidate_inputs(td)
            except Exception:
                candidates = []

            try:
                auctions = await self._read.get_stock_auction_snapshot(td)
            except Exception:
                auctions = []

            auction_stock_ids = {a.stock_id for a in auctions}
            has_series = any(
                getattr(a, "tail_auction_vwap", None) is not None
                for a in auctions
            )

            for c in candidates:
                stock_id = str(c.get("stock_id") or "")
                total_signals += 1
                if stock_id in auction_stock_ids:
                    if has_series:
                        dist["real_auction"] += 1
                    else:
                        dist["auction_snapshot"] += 1
                else:
                    dist["daily_open_proxy"] += 1

        report.confirm_source_distribution = dist
        report.proxy_sample_ratio = (
            (dist["daily_open_proxy"]) / total_signals
            if total_signals > 0
            else 0.0
        )
        report.unverifiable_signal_count = dist["missing"]

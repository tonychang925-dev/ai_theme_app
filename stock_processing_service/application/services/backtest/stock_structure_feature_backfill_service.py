"""Phase -1.5a-refactor v0.3: Stock Structure Daily Feature Backfill Service.

THIN ORCHESTRATOR: reads data → calls domain services → writes cache.
  - weak_type / weak_type_quality → w2s_feature_rules (domain/backtest)
  - support / gap / ma → BarSupportAdapter → GapStructureDetector + SupportStructureResolver
No hardcoded trading rules.
"""

from __future__ import annotations

import json, logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from stock_processing_service.domain.backtest.w2s_feature_rules import (
    classify_weak_type,
    classify_weak_type_quality,
)
from stock_processing_service.domain.services.bar_support_adapter import (
    BarSupportAdapter,
)

logger = logging.getLogger(__name__)


class StockStructureFeatureBackfillService:
    """Build stock_structure_daily_feature from stock_daily_snapshot."""

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    async def backfill(
        self,
        start_date: date,
        end_date: date,
        rule_version: str = "stock_structure_feature_v0.1",
    ) -> dict[str, Any]:
        c = self._gw._client

        # Step 1: Load all trading days in range
        td_rows = await c.execute_query(
            "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date >= $1 AND trade_date <= $2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
            (start_date, end_date),
        )
        trade_dates = [r["trade_date"] for r in td_rows]
        logger.info("Trading days: %d", len(trade_dates))

        # Step 2: Preload bars — we need prior days for lookback
        lookback_start = trade_dates[0] - timedelta(days=14)
        all_bar_rows = await c.execute_query(
            "SELECT DISTINCT ON (trade_date, stock_id) trade_date, stock_id, stock_name, open_price, high_price, low_price, close_price, pre_close, pct_chg, volume, amount FROM stock_daily_snapshot WHERE trade_date >= $1 AND trade_date <= $2 AND source_name LIKE 'tushare%' ORDER BY trade_date, stock_id, source_name",
            (lookback_start, end_date),
        )
        bars_by_date: dict[date, dict[str, dict]] = {}
        for r in all_bar_rows:
            td = r["trade_date"]
            if td not in bars_by_date:
                bars_by_date[td] = {}
            bars_by_date[td][str(r["stock_id"])] = r
        logger.info("Preloaded bars for %d dates (from %s)", len(bars_by_date), lookback_start)

        # Step 3: Compute features per trading day
        total_written = 0
        future_leak_count = 0
        stats = {
            "dates": len(trade_dates),
            "stocks_processed": 0,
            "written": 0,
            "weak_type_filled": 0,
            "weak_type_quality_filled": 0,
            "support_type_filled": 0,
            "support_strength_filled": 0,
            "prior7_limitup_filled": 0,
            "prior7_strong_filled": 0,
            "future_leaks": 0,
            "weak_type_dist": {},
            "wtq_dist": {},
            "support_type_dist": {},
        }

        for td in trade_dates:
            today_bars = bars_by_date.get(td, {})
            if not today_bars:
                continue

            # Find prior trading day
            prior_dates = sorted([d for d in trade_dates if d < td], reverse=True)
            prior_td = prior_dates[0] if prior_dates else None
            prior_bars = bars_by_date.get(prior_td, {}) if prior_td else {}

            # Find prior 7 trading days
            prior7_dates = prior_dates[:7]

            for sid, bar in today_bars.items():
                stats["stocks_processed"] += 1

                pct = float(bar.get("pct_chg") or 0)
                open_price = float(bar.get("open_price") or 0)
                high = float(bar.get("high_price") or 0)
                low = float(bar.get("low_price") or 0)
                close = float(bar.get("close_price") or 0)
                pre_close = float(bar.get("pre_close") or 0)
                vol = float(bar.get("volume") or 0)
                amt = float(bar.get("amount") or 0)

                open_pct = ((open_price - pre_close) / pre_close * 100) if pre_close > 0 else 0
                limit_up = pct >= 9.5

                # prev_day_limit_up (from prior trading day)
                prev_bar = prior_bars.get(sid)
                prev_day_limit_up = False
                if prev_bar:
                    prev_pct = float(prev_bar.get("pct_chg") or 0)
                    prev_day_limit_up = prev_pct >= 9.5

                # prior7 features (strict: only prior dates)
                prior7_lim = 0
                prior7_str = 0
                for p7d in prior7_dates:
                    p7_bars = bars_by_date.get(p7d, {})
                    p7_bar = p7_bars.get(sid)
                    if p7_bar:
                        p7_pct = float(p7_bar.get("pct_chg") or 0)
                        if p7_pct >= 9.5:
                            prior7_lim += 1
                        if p7_pct >= 5.0:
                            prior7_str += 1

                # weak_type (from BuildWeakToStrongCandidateUseCase logic)
                prev_pct_val = float(prev_bar.get("pct_chg") or 0) if prev_bar else 0.0
                # Imported from w2s_feature_rules (single source of truth)
                weak_type = classify_weak_type(
                    pct_chg=pct, prev_day_pct=prev_pct_val,
                    prev_day_limit_up=prev_day_limit_up,
                )
                wtq = classify_weak_type_quality(weak_type)

                # ── Support resolution via domain services ──
                # Build prior bar list (most recent first, max 40 bars)
                prior_bar_list = []
                for p7d in prior7_dates:
                    p7_bars = bars_by_date.get(p7d, {})
                    p7_bar = p7_bars.get(sid)
                    if p7_bar:
                        prior_bar_list.append(dict(p7_bar))

                # Simple MA computation (lightweight, domain services accept pre-computed)
                ma5 = _compute_simple_ma(sid, prior7_dates[:5], bars_by_date)
                ma10 = _compute_simple_ma(sid, prior7_dates[:10], bars_by_date)

                adapter = _get_support_adapter()
                support_result = adapter.resolve(
                    current_bar=dict(bar),
                    prior_bars=prior_bar_list,
                    ma5=Decimal(str(ma5)) if ma5 else None,
                    ma10=Decimal(str(ma10)) if ma10 else None,
                )
                supp_type = support_result.support_type
                supp_str = float(support_result.support_strength) if support_result.support_strength else None
                gap_not_filled = support_result.gap_not_filled
                ma_support_hit = support_result.ma_support_hit

                # source_trace with rule versions
                trace = json.dumps({
                    "feature_date": td.isoformat(),
                    "lookback_start_date": prior7_dates[-1].isoformat() if prior7_dates else td.isoformat(),
                    "lookback_end_date": td.isoformat(),
                    "rule_version": rule_version,
                    "daily_bar_source": "stock_daily_snapshot",
                    "weak_type_rule_version": "w2s_feature_rules.v0.3",
                    "support_rule_version": support_result.rule_version,
                    "support_source": support_result.source,
                    "gap_source": "GapStructureDetector",
                    "ma_support_source": "KlineSupportScorer" if ma_support_hit else None,
                })

                try:
                    await c.execute_query("""
                        INSERT INTO stock_structure_daily_feature (
                            trade_date, stock_id, stock_name,
                            pct_chg, open_pct, close_price, pre_close, high_price, low_price, volume, amount,
                            limit_up, prev_day_limit_up,
                            prior7_limitup_days, prior7_strong_days,
                            weak_type, weak_type_quality,
                            support_type, support_strength,
                            gap_not_filled, ma_support_hit,
                            rule_version, source_trace
                        ) VALUES (
                            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                            $14,$15,$16,$17,$18,$19,$20,$21,$22,$23
                        )
                        ON CONFLICT (trade_date, stock_id, rule_version) DO UPDATE SET
                            pct_chg=EXCLUDED.pct_chg, open_pct=EXCLUDED.open_pct,
                            limit_up=EXCLUDED.limit_up, prev_day_limit_up=EXCLUDED.prev_day_limit_up,
                            prior7_limitup_days=EXCLUDED.prior7_limitup_days,
                            prior7_strong_days=EXCLUDED.prior7_strong_days,
                            weak_type=EXCLUDED.weak_type, weak_type_quality=EXCLUDED.weak_type_quality,
                            support_type=EXCLUDED.support_type, support_strength=EXCLUDED.support_strength,
                            gap_not_filled=EXCLUDED.gap_not_filled, ma_support_hit=EXCLUDED.ma_support_hit,
                            source_trace=EXCLUDED.source_trace
                    """, (
                        td, sid, str(bar.get("stock_name") or ""),
                        pct, open_pct, close, pre_close, high, low, vol, amt,
                        limit_up, prev_day_limit_up,
                        prior7_lim, prior7_str,
                        weak_type, wtq,
                        supp_type, supp_str,
                        gap_not_filled, ma_support_hit,
                        rule_version, trace,
                    ))
                    total_written += 1

                    # Stats
                    if weak_type: stats["weak_type_filled"] += 1
                    if wtq: stats["weak_type_quality_filled"] += 1
                    if supp_type: stats["support_type_filled"] += 1
                    if supp_str is not None: stats["support_strength_filled"] += 1
                    stats["prior7_limitup_filled"] += 1
                    stats["prior7_strong_filled"] += 1
                    stats["weak_type_dist"][weak_type] = stats["weak_type_dist"].get(weak_type, 0) + 1
                    stats["wtq_dist"][wtq] = stats["wtq_dist"].get(wtq, 0) + 1
                    stats["support_type_dist"][supp_type] = stats["support_type_dist"].get(supp_type, 0) + 1

                except Exception as e:
                    if total_written < 5:
                        logger.warning("Write failed for %s on %s: %s", sid, td, e)

        stats["written"] = total_written
        logger.info("C-layer backfill complete: %d rows written", total_written)
        return stats


# ═══════════════════════════════════════════════════════════════════
# Module-level helpers
# ═══════════════════════════════════════════════════════════════════

_support_adapter: BarSupportAdapter | None = None


def _get_support_adapter() -> BarSupportAdapter:
    global _support_adapter
    if _support_adapter is None:
        _support_adapter = BarSupportAdapter()
    return _support_adapter


def _compute_simple_ma(
    stock_id: str,
    lookback_dates: list[date],
    bars_by_date: dict[date, dict[str, dict]],
) -> float | None:
    """Compute simple moving average of close prices. Lightweight helper."""
    closes = []
    for d in lookback_dates:
        day_bars = bars_by_date.get(d, {})
        bar = day_bars.get(stock_id)
        if bar:
            c = float(bar.get("close_price") or 0)
            if c > 0:
                closes.append(c)
    if not closes:
        return None
    return sum(closes) / len(closes)

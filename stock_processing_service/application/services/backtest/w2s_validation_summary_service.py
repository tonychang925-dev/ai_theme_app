"""Validation summary service for W2S backtest.

Generates 6 experiment groups (underlying) with 3 visible in frontend.
Splits by confirm_source group and confirm_level.
Writes to w2s_validation_summary.
Phase 0 does NOT generate buy/sell recommendations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from stock_processing_service.domain.backtest.w2s_experiment_rules import (
    filter_for_experiment,
    get_all_experiments,
    get_visible_experiments,
)
from stock_processing_service.domain.backtest.w2s_metrics import (
    ValidationMetrics,
    compute_validation_metrics,
)

logger = logging.getLogger(__name__)

CONFIRM_SOURCE_GROUPS = ["real_auction", "auction_snapshot", "daily_open_proxy", "missing", "all"]


class W2SValidationSummaryService:
    """Aggregate validation results into experiment summaries."""

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    async def build(self, run_id: str) -> dict[str, Any]:
        """Build validation summary for all experiments.

        Phase 0 contract:
          - Outputs verification conclusions only.
          - Does NOT output buy/sell recommendations.
          - confirm_source is a primary grouping dimension.
          - proxy sample ratio warnings are included.
        """

        # Delete existing summaries for this run (idempotent)
        await self._delete_run_summaries(run_id)

        # Load all validations joined with snapshots
        rows = await self._load_joined_rows(run_id)
        if not rows:
            return {"run_id": run_id, "warning": "No validation data found", "summaries": []}

        # Compute proxy sample ratio
        total = len(rows)
        proxy_count = sum(1 for r in rows if str(r.get("confirm_source") or "").startswith("daily_open_proxy"))
        proxy_ratio = proxy_count / total if total > 0 else 0.0

        summaries: list[dict[str, Any]] = []
        all_experiments = get_all_experiments()

        for exp_id in all_experiments:
            filtered = filter_for_experiment(rows, exp_id)

            # Group by confirm_source
            for cs_group in CONFIRM_SOURCE_GROUPS:
                if cs_group == "all":
                    group_rows = filtered
                else:
                    group_rows = [r for r in filtered if str(r.get("confirm_source") or "") == cs_group]

                if not group_rows:
                    continue

                # Sub-group by confirm_level
                confirm_levels = sorted(set(
                    str(r.get("confirm_level") or "missing") for r in group_rows
                ))
                for level in confirm_levels:
                    level_rows = [r for r in group_rows if str(r.get("confirm_level") or "missing") == level]
                    metrics = compute_validation_metrics(level_rows)

                    summary = {
                        "run_id": run_id,
                        "experiment_id": exp_id,
                        "confirm_source_group": cs_group,
                        "confirm_level": level,
                        "sample_count": metrics.sample_count,
                        "win_rate_1d": float(metrics.win_rate_1d),
                        "win_rate_3d": float(metrics.win_rate_3d),
                        "win_rate_5d": float(metrics.win_rate_5d),
                        "avg_return_3d": float(metrics.avg_return_3d),
                        "avg_return_5d": float(metrics.avg_return_5d),
                        "max_drawdown_5d": float(metrics.max_drawdown_5d),
                        "hit_limit_up_pct": float(metrics.hit_limit_up_pct),
                        "loss_over_5pct_pct": float(metrics.loss_over_5pct_pct),
                    }
                    summaries.append(summary)

        # Also add overall (non-grouped) summaries per experiment
        for exp_id in all_experiments:
            filtered = filter_for_experiment(rows, exp_id)
            if not filtered:
                continue
            metrics = compute_validation_metrics(filtered)
            summaries.append({
                "run_id": run_id,
                "experiment_id": exp_id,
                "confirm_source_group": "all",
                "confirm_level": "all",
                "sample_count": metrics.sample_count,
                "win_rate_1d": float(metrics.win_rate_1d),
                "win_rate_3d": float(metrics.win_rate_3d),
                "win_rate_5d": float(metrics.win_rate_5d),
                "avg_return_3d": float(metrics.avg_return_3d),
                "avg_return_5d": float(metrics.avg_return_5d),
                "max_drawdown_5d": float(metrics.max_drawdown_5d),
                "hit_limit_up_pct": float(metrics.hit_limit_up_pct),
                "loss_over_5pct_pct": float(metrics.loss_over_5pct_pct),
            })

        written = await self._write_summaries(summaries)

        # Build report
        visible_summaries = [
            s for s in summaries
            if s["experiment_id"] in get_visible_experiments()
            and s["confirm_source_group"] == "all"
            and s["confirm_level"] == "all"
        ]

        result = {
            "run_id": run_id,
            "total_samples": total,
            "proxy_sample_ratio": proxy_ratio,
            "proxy_warning": (
                "当前结论主要基于日K代理确认，不等同真实竞价回测。"
                if proxy_ratio > 0.5 else None
            ),
            "written": written,
            "visible_summaries": [
                {
                    "experiment_id": s["experiment_id"],
                    "label": _experiment_label(s["experiment_id"]),
                    "sample_count": s["sample_count"],
                    "win_rate_3d": s["win_rate_3d"],
                    "win_rate_5d": s["win_rate_5d"],
                    "avg_return_5d": s["avg_return_5d"],
                    "max_drawdown_5d": s["max_drawdown_5d"],
                    "hit_limit_up_pct": s["hit_limit_up_pct"],
                }
                for s in visible_summaries
            ],
            "all_summaries_count": len(summaries),
            # Phase 0 contract: no buy/sell recommendations
            "recommendations": None,
        }

        return result

    async def _load_joined_rows(self, run_id: str) -> list[dict[str, Any]]:
        """Load validation rows joined with snapshot features."""
        try:
            rows = await self._gw.query(
                """
                SELECT
                    v.signal_id,
                    v.run_id,
                    v.trade_date,
                    v.stock_id,
                    v.signal_level,
                    v.score,
                    v.buy_ref_date,
                    v.buy_ref_price,
                    v.next_1d_return,
                    v.next_2d_return,
                    v.next_3d_return,
                    v.next_5d_return,
                    v.max_return_3d,
                    v.max_return_5d,
                    v.max_drawdown_3d,
                    v.max_drawdown_5d,
                    v.hit_limit_up_3d,
                    v.hit_limit_up_5d,
                    v.is_win_1d,
                    v.is_win_3d,
                    v.is_win_5d,
                    v.loss_over_5pct,
                    v.validation_status,
                    v.validation_error,
                    s.pool_entry_type,
                    s.mainline_strength_score,
                    s.fade_confirmed,
                    s.leader_role_proxy,
                    s.confirm_level,
                    s.confirm_source,
                    s.is_leader,
                    s.rank_order,
                    s.recent_limit_up_count,
                    s.board_type,
                    s.is_20cm
                FROM strategy_signal_validation v
                JOIN w2s_backtest_feature_snapshot s
                    ON v.stock_id = s.stock_id
                    AND v.trade_date = s.candidate_trade_date
                    AND v.run_id = s.run_id
                WHERE v.run_id = $1
                """,
                [run_id],
            )
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.error("Failed to load joined rows for run_id=%s: %s", run_id, exc)
            return []

    async def _write_summaries(self, summaries: list[dict[str, Any]]) -> int:
        if not summaries:
            return 0
        written = 0
        for s in summaries:
            try:
                await self._gw.execute_raw(
                    """
                    INSERT INTO w2s_validation_summary (
                        run_id, experiment_id, confirm_source_group, confirm_level,
                        sample_count, win_rate_1d, win_rate_3d, win_rate_5d,
                        avg_return_3d, avg_return_5d, max_drawdown_5d,
                        hit_limit_up_pct, loss_over_5pct_pct
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (run_id, experiment_id, confirm_source_group, confirm_level) DO UPDATE SET
                        sample_count = EXCLUDED.sample_count,
                        win_rate_1d = EXCLUDED.win_rate_1d,
                        win_rate_3d = EXCLUDED.win_rate_3d,
                        win_rate_5d = EXCLUDED.win_rate_5d,
                        avg_return_3d = EXCLUDED.avg_return_3d,
                        avg_return_5d = EXCLUDED.avg_return_5d,
                        max_drawdown_5d = EXCLUDED.max_drawdown_5d,
                        hit_limit_up_pct = EXCLUDED.hit_limit_up_pct,
                        loss_over_5pct_pct = EXCLUDED.loss_over_5pct_pct
                    """,
                    [
                        str(s["run_id"]), str(s["experiment_id"]),
                        str(s["confirm_source_group"]), str(s["confirm_level"]),
                        int(s.get("sample_count") or 0),
                        float(s.get("win_rate_1d") or 0), float(s.get("win_rate_3d") or 0),
                        float(s.get("win_rate_5d") or 0),
                        float(s.get("avg_return_3d") or 0), float(s.get("avg_return_5d") or 0),
                        float(s.get("max_drawdown_5d") or 0),
                        float(s.get("hit_limit_up_pct") or 0), float(s.get("loss_over_5pct_pct") or 0),
                    ],
                )
                written += 1
            except Exception as exc:
                logger.error("Failed to write summary: %s", exc)
        return written

    async def _delete_run_summaries(self, run_id: str) -> None:
        try:
            await self._gw.execute_raw(
                "DELETE FROM w2s_validation_summary WHERE run_id = $1",
                [run_id],
            )
        except Exception as exc:
            logger.warning("Failed to delete summaries for run_id=%s: %s", run_id, exc)


def _experiment_label(experiment_id: str) -> str:
    labels: dict[str, str] = {
        "EXP_A_BASELINE": "全量基准",
        "EXP_B_FORMAL_ONLY": "仅formal候选",
        "EXP_C_MAINLINE": "主线过滤",
        "EXP_D_LEADER": "龙头过滤",
        "EXP_E_MAINLINE_LEADER": "主线+龙头",
        "EXP_F_CONFIRMED_AB": "主线+龙头+A/B确认",
    }
    return labels.get(experiment_id, experiment_id)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "_asdict"):
        return dict(row._asdict())
    if hasattr(row, "__dict__"):
        return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
    return dict(row)

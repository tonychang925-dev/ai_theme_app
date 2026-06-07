from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_ID = "one_to_two"
DEFAULT_STRATEGY_VERSION = "one_to_two_v1.0_post_market_plan"
DEFAULT_SIGNAL_SESSION = "post_market"
SUCCESS_OUTCOME_PREFIX = "A_SEALED_SECOND_BOARD"
EXPECTED_OUTCOMES = {
    "A_SEALED_SECOND_BOARD_PROXY",
    "B_TOUCHED_BUT_BROKEN",
    "C_FAILED_NO_TOUCH",
    "D_NO_DATA",
    "A_SEALED_SECOND_BOARD_REAL",
}


class OneToTwoBacktestValidationSummaryService:
    """Summarize OneToTwo backtest outcomes from unified backtest tables."""

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    async def build(
        self,
        run_id: str,
        *,
        strategy_id: str = DEFAULT_STRATEGY_ID,
        strategy_version: str = DEFAULT_STRATEGY_VERSION,
    ) -> dict[str, Any]:
        if strategy_id != DEFAULT_STRATEGY_ID:
            raise ValueError("strategy_id must be one_to_two")
        if strategy_version != DEFAULT_STRATEGY_VERSION:
            raise ValueError("strategy_version must be one_to_two_v1.0_post_market_plan")

        run_row = await self._load_run_row(run_id)
        snapshots = await self._load_snapshots(run_id, strategy_id, strategy_version)
        signals = await self._load_signals(run_id, strategy_id, strategy_version)
        validations = await self._load_validations(run_id, strategy_id, strategy_version)

        snapshot_by_id = {str(row.get("snapshot_id") or ""): row for row in snapshots if str(row.get("snapshot_id") or "")}
        signal_by_source_id = {str(row.get("source_id") or ""): row for row in signals if str(row.get("source_id") or "")}
        validation_by_signal_id = {str(row.get("signal_id") or ""): row for row in validations if str(row.get("signal_id") or "")}
        rule_version_counts = Counter(
            str(row.get("rule_version") or "") for row in signals if str(row.get("rule_version") or "").strip()
        )

        trade_dates = sorted({self._parse_date(row.get("candidate_trade_date")) for row in snapshots if self._parse_date(row.get("candidate_trade_date"))})
        range_start = self._parse_date((run_row or {}).get("start_date")) if run_row else None
        range_end = self._parse_date((run_row or {}).get("end_date")) if run_row else None
        if range_start is None and trade_dates:
            range_start = trade_dates[0]
        if range_end is None and trade_dates:
            range_end = trade_dates[-1]

        total_days = await self._count_open_days(range_start, range_end)
        non_empty_days = len(trade_dates)
        empty_days = max(total_days - non_empty_days, 0)

        decision_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        outcome_label_counts: Counter[str] = Counter()
        outcome_source_counts: Counter[str] = Counter()
        authenticity_level_counts: Counter[str] = Counter()
        golden_spider_counts: Counter[str] = Counter()
        first_board_type_counts: Counter[str] = Counter()
        first_board_type_success_counts: Counter[str] = Counter()
        decision_success_counts: Counter[str] = Counter()
        decision_total_counts: Counter[str] = Counter()
        reject_reason_false_negative_counts: Counter[str] = Counter()
        reject_positive_count = 0

        for snap in snapshots:
            decision = self._extract_decision(snap)
            if not decision:
                continue
            decision_total_counts[decision] += 1
            resolved = await self._resolve_snapshot_outcome(
                snap,
                signal_by_source_id=signal_by_source_id,
                validation_by_signal_id=validation_by_signal_id,
            )
            if resolved is None:
                resolved = {
                    "outcome_label": "D_NO_DATA",
                    "outcome_source": "missing",
                    "validation_status": "missing_bar",
                }
            subject_authenticity = self._extract_subject_authenticity(snap)
            kline_pattern_quality = self._extract_kline_pattern_quality(snap)
            first_board_type = self._extract_first_board_type(snap)
            authenticity_level = str(subject_authenticity.get("level") or "unknown")
            has_golden_spider = bool(kline_pattern_quality.get("has_golden_spider"))
            first_board_type_counts[first_board_type] += 1
            outcome_label = str(resolved.get("outcome_label") or "D_NO_DATA")
            outcome_source = str(resolved.get("outcome_source") or "missing")
            outcome_label_counts[outcome_label] += 1
            outcome_source_counts[outcome_source] += 1
            authenticity_level_counts[authenticity_level] += 1
            golden_spider_counts["true" if has_golden_spider else "false"] += 1
            decision_rows[decision].append(
                {
                    "snapshot": snap,
                    "outcome_label": outcome_label,
                    "outcome_source": outcome_source,
                    "authenticity_level": authenticity_level,
                    "has_golden_spider": has_golden_spider,
                    "first_board_type": first_board_type,
                    "resolved": resolved,
                }
            )
            if outcome_label.startswith(SUCCESS_OUTCOME_PREFIX):
                decision_success_counts[decision] += 1
                first_board_type_success_counts[first_board_type] += 1
                if decision == "reject":
                    reject_positive_count += 1
                    for reason in self._extract_reject_reasons(snap):
                        reject_reason_false_negative_counts[reason] += 1

        focus_count = decision_total_counts.get("focus", 0)
        observe_count = decision_total_counts.get("observe_only", 0)
        pending_count = decision_total_counts.get("pending_review_only", 0)
        reject_count = decision_total_counts.get("reject", 0)

        focus_second_board_rate = self._rate(decision_success_counts.get("focus", 0), focus_count)
        observe_second_board_rate = self._rate(decision_success_counts.get("observe_only", 0), observe_count)
        pending_second_board_rate = self._rate(decision_success_counts.get("pending_review_only", 0), pending_count)
        reject_false_negative_rate = self._rate(reject_positive_count, reject_count)

        summary = {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "total_days": total_days,
            "empty_days": empty_days,
            "non_empty_days": non_empty_days,
            "empty_day_ratio": self._rate(empty_days, total_days),
            "focus_count": focus_count,
            "observe_count": observe_count,
            "pending_count": pending_count,
            "reject_count": reject_count,
            "focus_second_board_rate": focus_second_board_rate,
            "observe_second_board_rate": observe_second_board_rate,
            "pending_second_board_rate": pending_second_board_rate,
            "reject_false_negative_rate": reject_false_negative_rate,
            "avg_focus_count_per_day": self._rate(focus_count, non_empty_days),
            "avg_observe_count_per_day": self._rate(observe_count, non_empty_days),
            "avg_pending_count_per_day": self._rate(pending_count, non_empty_days),
            "outcome_label_counts": dict(outcome_label_counts),
            "outcome_source_counts": dict(outcome_source_counts),
            "authenticity_level_counts": dict(authenticity_level_counts),
            "golden_spider_counts": dict(golden_spider_counts),
            "first_board_type_counts": dict(first_board_type_counts),
            "decision_success_counts": dict(decision_success_counts),
            "decision_total_counts": dict(decision_total_counts),
            "rule_version_counts": dict(rule_version_counts),
            "decision_breakdown": {
                decision: {
                    "sample_count": len(rows),
                    "success_count": decision_success_counts.get(decision, 0),
                    "success_rate": self._rate(decision_success_counts.get(decision, 0), len(rows)),
                    "outcome_label_counts": dict(Counter(row["outcome_label"] for row in rows)),
                    "outcome_source_counts": dict(Counter(row["outcome_source"] for row in rows)),
                    "authenticity_level_counts": dict(Counter(row["authenticity_level"] for row in rows)),
                    "golden_spider_counts": dict(Counter("true" if row["has_golden_spider"] else "false" for row in rows)),
                    "first_board_type_counts": dict(Counter(row["first_board_type"] for row in rows)),
                }
                for decision, rows in decision_rows.items()
            },
            "first_board_type_breakdown": {
                board_type: {
                    "sample_count": count,
                    "success_count": first_board_type_success_counts.get(board_type, 0),
                    "success_rate": self._rate(first_board_type_success_counts.get(board_type, 0), count),
                }
                for board_type, count in first_board_type_counts.items()
            },
            "reject_reason_false_negative_distribution": dict(reject_reason_false_negative_counts),
            "summary_rows": [
                {
                    "run_id": run_id,
                    "experiment_id": "one_to_two_overall",
                    "confirm_source_group": "all",
                    "confirm_level": "all",
                    "sample_count": non_empty_days,
                    "strategy_id": strategy_id,
                    "strategy_version": strategy_version,
                }
            ],
            "warnings": self._warnings(total_days, non_empty_days),
        }

        return summary

    async def _load_run_row(self, run_id: str) -> dict[str, Any] | None:
        rows = await self._gw._client.execute_query(
            "SELECT * FROM w2s_backtest_run WHERE run_id = $1 LIMIT 1",
            [run_id],
        )
        if not rows:
            return None
        return _row_to_dict(rows[0])

    async def _load_snapshots(self, run_id: str, strategy_id: str, strategy_version: str) -> list[dict[str, Any]]:
        rows = await self._gw._client.execute_query(
            """
            SELECT *
            FROM w2s_backtest_feature_snapshot
            WHERE run_id = $1
              AND strategy_id = $2
              AND strategy_version = $3
            ORDER BY candidate_trade_date ASC, stock_id ASC, subject_key ASC
            """,
            [run_id, strategy_id, strategy_version],
        )
        return [_row_to_dict(row) for row in rows]

    async def _load_signals(self, run_id: str, strategy_id: str, strategy_version: str) -> list[dict[str, Any]]:
        rows = await self._gw._client.execute_query(
            """
            SELECT *
            FROM strategy_signal_daily
            WHERE run_id = $1
              AND strategy_id = $2
              AND strategy_version = $3
            ORDER BY trade_date ASC, stock_id ASC, source_id ASC
            """,
            [run_id, strategy_id, strategy_version],
        )
        return [_row_to_dict(row) for row in rows]

    async def _load_validations(self, run_id: str, strategy_id: str, strategy_version: str) -> list[dict[str, Any]]:
        rows = await self._gw._client.execute_query(
            """
            SELECT *
            FROM strategy_signal_validation
            WHERE run_id = $1
              AND strategy_id = $2
              AND strategy_version = $3
            ORDER BY trade_date ASC, stock_id ASC, signal_id ASC
            """,
            [run_id, strategy_id, strategy_version],
        )
        return [_row_to_dict(row) for row in rows]

    async def _resolve_snapshot_outcome(
        self,
        snapshot: dict[str, Any],
        *,
        signal_by_source_id: dict[str, dict[str, Any]],
        validation_by_signal_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        decision = self._extract_decision(snapshot)
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        if decision == "reject":
            return await self._evaluate_reject_snapshot(snapshot)

        signal = signal_by_source_id.get(snapshot_id)
        if signal is None:
            return None
        validation = validation_by_signal_id.get(str(signal.get("signal_id") or ""))
        if validation is None:
            return None
        return {
            "outcome_label": str(validation.get("outcome_label") or "D_NO_DATA"),
            "outcome_source": str(validation.get("outcome_source") or "missing"),
            "validation_status": str(validation.get("validation_status") or "ok"),
        }

    async def _evaluate_reject_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        trade_date = self._parse_date(snapshot.get("candidate_trade_date"))
        stock_id = str(snapshot.get("stock_id") or "").strip()
        if trade_date is None or not stock_id:
            return None
        next_trade_date = await self._get_next_open_trade_date(trade_date)
        if next_trade_date is None:
            return {
                "outcome_label": "D_NO_DATA",
                "outcome_source": "missing",
                "validation_status": "missing_bar",
            }
        bars = await self._load_stock_bars(next_trade_date, stock_id)
        if not bars:
            return {
                "outcome_label": "D_NO_DATA",
                "outcome_source": "missing",
                "validation_status": "missing_bar",
            }
        bar = bars[0]
        limit_up_price = self._compute_limit_up_price(bar, snapshot)
        high_price = _to_decimal(bar.get("high_price"))
        close_price = _to_decimal(bar.get("close_price"))
        if limit_up_price is None or high_price is None or close_price is None:
            return {
                "outcome_label": "D_NO_DATA",
                "outcome_source": "missing",
                "validation_status": "missing_bar",
            }
        touched = high_price >= limit_up_price
        sealed = close_price >= limit_up_price
        if sealed:
            return {
                "outcome_label": "A_SEALED_SECOND_BOARD_PROXY",
                "outcome_source": "daily_close_proxy",
                "validation_status": "ok",
            }
        if touched:
            return {
                "outcome_label": "B_TOUCHED_BUT_BROKEN",
                "outcome_source": "daily_high_proxy",
                "validation_status": "ok",
            }
        return {
            "outcome_label": "C_FAILED_NO_TOUCH",
            "outcome_source": "daily_close_proxy",
            "validation_status": "ok",
        }

    async def _count_open_days(self, start_date: date | None, end_date: date | None) -> int:
        if start_date is None or end_date is None or start_date > end_date:
            return 0
        rows = await self._gw._client.execute_query(
            """
            SELECT DISTINCT trade_date
            FROM stock_daily_snapshot
            WHERE trade_date >= $1
              AND trade_date <= $2
              AND source_name LIKE 'tushare%'
            ORDER BY trade_date
            """,
            [start_date, end_date],
        )
        return len(rows)

    async def _get_next_open_trade_date(self, trade_date: date) -> date | None:
        rows = await self._gw._client.execute_query(
            """
            SELECT DISTINCT trade_date
            FROM stock_daily_snapshot
            WHERE trade_date > $1
              AND source_name LIKE 'tushare%'
            ORDER BY trade_date
            LIMIT 1
            """,
            [trade_date],
        )
        if not rows:
            return None
        return self._parse_date(rows[0].get("trade_date"))

    async def _load_stock_bars(self, trade_date: date, stock_id: str) -> list[dict[str, Any]]:
        rows = await self._gw._client.execute_query(
            """
            SELECT
                trade_date, stock_id, stock_name,
                open_price, high_price, low_price, close_price, pre_close, pct_chg,
                volume, amount
            FROM stock_daily_snapshot
            WHERE trade_date = $1
              AND stock_id = $2
              AND source_name LIKE 'tushare%'
            ORDER BY stock_id
            LIMIT 1
            """,
            [trade_date, stock_id],
        )
        return [_row_to_dict(row) for row in rows]

    def _compute_limit_up_price(self, bar: dict[str, Any], snapshot: dict[str, Any]) -> Decimal | None:
        pre_close = _to_decimal(bar.get("pre_close"))
        if pre_close is None:
            return None
        is_20cm = bool(snapshot.get("is_20cm"))
        factor = Decimal("1.2") if is_20cm else Decimal("1.1")
        return pre_close * factor

    def _extract_decision(self, snapshot: dict[str, Any]) -> str:
        derived = _json_obj(snapshot.get("derived_feature_json"))
        decision = str(derived.get("decision") or snapshot.get("pool_entry_type") or "").strip()
        return decision

    def _extract_reject_reasons(self, snapshot: dict[str, Any]) -> list[str]:
        derived = _json_obj(snapshot.get("derived_feature_json"))
        raw = _json_obj(snapshot.get("raw_feature_json"))
        trace = _json_obj(snapshot.get("source_trace"))
        candidates: list[Any] = []
        for source in (derived, raw, trace):
            for key in ("veto_reasons", "reject_reason", "reject_reason_code"):
                value = source.get(key)
                if value:
                    candidates.append(value)
        reasons: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, list):
                reasons.extend(str(item).strip() for item in candidate if str(item).strip())
            else:
                text = str(candidate).strip()
                if text:
                    reasons.append(text)
        deduped: list[str] = []
        for reason in reasons:
            if reason not in deduped:
                deduped.append(reason)
        return deduped or ["unknown"]

    def _extract_subject_authenticity(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        for source in (_json_obj(snapshot.get("derived_feature_json")), _json_obj(snapshot.get("raw_feature_json")), _json_obj(snapshot.get("source_trace"))):
            value = source.get("subject_authenticity")
            if isinstance(value, dict):
                return dict(value)
        return {}

    def _extract_kline_pattern_quality(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        for source in (_json_obj(snapshot.get("derived_feature_json")), _json_obj(snapshot.get("raw_feature_json")), _json_obj(snapshot.get("source_trace"))):
            value = source.get("kline_pattern_quality")
            if isinstance(value, dict):
                return dict(value)
        return {}

    def _extract_first_board_type(self, snapshot: dict[str, Any]) -> str:
        for source in (_json_obj(snapshot.get("derived_feature_json")), _json_obj(snapshot.get("raw_feature_json")), _json_obj(snapshot.get("source_trace"))):
            value = source.get("first_board_type")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unknown"

    def _warnings(self, total_days: int, non_empty_days: int) -> list[str]:
        warnings: list[str] = []
        if total_days < 30:
            warnings.append(f"观测日仅 {total_days} 天，统计区分度可能不足。")
        if non_empty_days == 0:
            warnings.append("没有非空候选日，summary 无法评估策略分层效果。")
        return warnings

    def _rate(self, numerator: int | float, denominator: int | float) -> float:
        try:
            denom = float(denominator)
            if denom == 0:
                return 0.0
            return float(numerator) / denom
        except Exception:
            return 0.0

    def _parse_date(self, value: Any) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        text = str(value)
        try:
            return date.fromisoformat(text[:10])
        except Exception:
            return None


def _json_obj(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
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

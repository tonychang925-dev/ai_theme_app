"""Signal builder service for W2S backtest.

Reads from w2s_backtest_feature_snapshot, generates strategy_signal_daily rows.
Preserves all confirm levels: A/B/C/X/proxy_A/proxy_B/proxy_C/proxy_X/missing.
Writes direction / tradable / reject_reason_code / confirm_source.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from stock_processing_service.domain.backtest.w2s_models import (
    ConfirmLevel,
    ConfirmSource,
)

logger = logging.getLogger(__name__)

CONFIRM_LEVELS_ALL = {
    "A", "B", "C", "X",
    "proxy_A", "proxy_B", "proxy_C", "proxy_X",
    "missing",
}


class W2SSignalBuilderService:
    """Generate strategy_signal_daily rows from feature snapshots."""

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    async def build(self, run_id: str, strategy_id: str = "weak_to_strong") -> dict[str, Any]:
        """Build signals from all snapshots for a given run_id."""

        # Delete existing signals for this run (idempotent)
        await self._delete_run_signals(run_id)

        snapshots = await self._load_snapshots(run_id)
        if not snapshots:
            return {"run_id": run_id, "signal_count": 0, "written": 0, "warning": "No snapshots found"}

        signals: list[dict[str, Any]] = []
        for snap in snapshots:
            signal = self._build_one_signal(snap, run_id, strategy_id)
            if signal:
                signals.append(signal)

        written = await self._write_signals(signals)
        logger.info("Signal builder: %d signals written for run_id=%s", written, run_id)

        # Update run metadata
        await self._update_run_signal_count(run_id, len(signals), written)

        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "signal_count": len(signals),
            "written": written,
        }

    def _build_one_signal(
        self,
        snap: dict[str, Any],
        run_id: str,
        strategy_id: str,
    ) -> dict[str, Any] | None:
        """Build a single strategy_signal_daily row from a snapshot."""
        confirm_level = str(snap.get("confirm_level") or "missing")
        confirm_source = str(snap.get("confirm_source") or ConfirmSource.MISSING.value)

        # Determine direction
        if confirm_level in {"A", "B"}:
            direction = "buy"
            tradable = True
            reject_reason_code = None
        elif confirm_level in {"C"}:
            direction = "watch"
            tradable = False
            reject_reason_code = "low_confirm_level"
        elif confirm_level in {"X"}:
            direction = "reject"
            tradable = False
            reject_reason_code = "auction_reject"
        elif confirm_level.startswith("proxy_"):
            direction = "watch"
            tradable = False
            reject_reason_code = "proxy_confirm_not_tradable"
        else:
            direction = "reject"
            tradable = False
            reject_reason_code = "missing_auction"

        signal_level = confirm_level

        # Time attributes
        candidate_date = _parse_date(snap.get("candidate_trade_date"))
        confirm_date = _parse_date(snap.get("confirm_trade_date"))

        # post_market signal: available T日 15:30, tradable T+1 09:30
        available_at = f"{candidate_date}T15:30:00+08:00" if candidate_date else ""
        tradable_at = f"{confirm_date}T09:30:00+08:00" if confirm_date else ""

        evidence = {
            "candidate_trade_date": str(snap.get("candidate_trade_date")),
            "confirm_trade_date": str(snap.get("confirm_trade_date")),
            "confirm_level": confirm_level,
            "confirm_source": confirm_source,
            "confirm_score": snap.get("confirmation_score"),
            "leader_role_proxy": snap.get("leader_role_proxy"),
            "board_type": snap.get("board_type"),
        }

        return {
            "signal_id": str(uuid.uuid4()),
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": str(snap.get("strategy_version") or "w2s_v0.1"),
            "trade_date": candidate_date if candidate_date else date.today(),
            "signal_session": "post_market",
            "available_at": available_at,
            "tradable_at": tradable_at,
            "stock_id": str(snap.get("stock_id") or ""),
            "stock_name": str(snap.get("stock_name") or ""),
            "subject_key": str(snap.get("subject_key") or ""),
            "theme_name": str(snap.get("theme_name") or ""),
            "direction": direction,
            "tradable": tradable,
            "signal_level": signal_level,
            "score": _safe_float(snap.get("confirmation_score")),
            "confidence": _safe_float(snap.get("candidate_score")),
            "confirm_level": confirm_level,
            "confirm_source": confirm_source,
            "reject_reason_code": reject_reason_code,
            "entry_plan": json.dumps({}),
            "exit_plan": json.dumps({
                "max_holding_days": 3,
                "stop_loss_pct": -0.05,
                "take_profit_pct": 0.10,
            }),
            "risk_plan": json.dumps({}),
            "evidence_json": json.dumps(evidence, ensure_ascii=False, default=str),
            "source_chain": "stock_processing_service",
            "source_table": "w2s_backtest_feature_snapshot",
            "source_id": str(snap.get("snapshot_id") or ""),
            "source_snapshot_version": str(snap.get("strategy_version") or "w2s_v0.1"),
            "rule_version": str(snap.get("strategy_version") or "w2s_v0.1"),
        }

    async def _load_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        fn = getattr(self._gw, "get_w2s_backtest_feature_snapshots_by_run", None)
        if callable(fn):
            return await fn(run_id)

        # Fallback: raw SQL
        try:
            rows = await self._gw.query(
                "SELECT * FROM w2s_backtest_feature_snapshot WHERE run_id = $1",
                [run_id],
            )
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.error("Failed to load snapshots for run_id=%s: %s", run_id, exc)
            return []

    async def _write_signals(self, signals: list[dict[str, Any]]) -> int:
        if not signals:
            return 0
        fn = getattr(self._gw, "upsert_strategy_signal_daily_rows", None)
        if callable(fn):
            return await fn(signals)

        # Fallback: raw SQL
        return await self._write_via_raw_sql(signals)

    async def _write_via_raw_sql(self, signals: list[dict[str, Any]]) -> int:
        written = 0
        for s in signals:
            try:
                await self._gw.execute_raw(
                    """
                    INSERT INTO strategy_signal_daily (
                        signal_id, run_id, strategy_id, strategy_version,
                        trade_date, signal_session, available_at, tradable_at,
                        stock_id, stock_name, subject_key, theme_name,
                        direction, tradable, signal_level, score, confidence,
                        confirm_level, confirm_source, reject_reason_code,
                        entry_plan, exit_plan, risk_plan, evidence_json,
                        source_chain, source_table, source_id, source_snapshot_version, rule_version
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12,
                        $13, $14, $15, $16, $17,
                        $18, $19, $20,
                        $21, $22, $23, $24,
                        $25, $26, $27, $28, $29
                    )
                    ON CONFLICT (run_id, strategy_id, strategy_version, trade_date, signal_session, stock_id, source_id)
                    DO UPDATE SET
                        signal_id = EXCLUDED.signal_id,
                        direction = EXCLUDED.direction,
                        tradable = EXCLUDED.tradable,
                        signal_level = EXCLUDED.signal_level,
                        score = EXCLUDED.score,
                        confidence = EXCLUDED.confidence,
                        confirm_level = EXCLUDED.confirm_level,
                        confirm_source = EXCLUDED.confirm_source,
                        reject_reason_code = EXCLUDED.reject_reason_code,
                        entry_plan = EXCLUDED.entry_plan,
                        exit_plan = EXCLUDED.exit_plan,
                        risk_plan = EXCLUDED.risk_plan,
                        evidence_json = EXCLUDED.evidence_json,
                        source_table = EXCLUDED.source_table,
                        source_id = EXCLUDED.source_id,
                        source_snapshot_version = EXCLUDED.source_snapshot_version,
                        rule_version = EXCLUDED.rule_version
                    """,
                    [
                        str(s["signal_id"]), str(s["run_id"]), str(s["strategy_id"]), str(s["strategy_version"]),
                        s["trade_date"], str(s["signal_session"]), str(s["available_at"]), str(s["tradable_at"]),
                        str(s["stock_id"]), str(s["stock_name"]), str(s["subject_key"]), str(s["theme_name"]),
                        str(s["direction"]), bool(s["tradable"]), str(s["signal_level"]), float(s.get("score") or 0), float(s.get("confidence") or 0),
                        str(s["confirm_level"]), str(s["confirm_source"]), s["reject_reason_code"],
                        json.dumps(s["entry_plan"]) if isinstance(s["entry_plan"], dict) else str(s["entry_plan"]),
                        json.dumps(s["exit_plan"]) if isinstance(s["exit_plan"], dict) else str(s["exit_plan"]),
                        json.dumps(s["risk_plan"]) if isinstance(s["risk_plan"], dict) else str(s["risk_plan"]),
                        json.dumps(s["evidence_json"]) if isinstance(s["evidence_json"], dict) else str(s["evidence_json"]),
                        str(s["source_chain"]), str(s["source_table"]), str(s["source_id"]),
                        str(s["source_snapshot_version"]), str(s["rule_version"]),
                    ],
                )
                written += 1
            except Exception as exc:
                logger.error("Failed to write signal for %s: %s", s.get("stock_id"), exc)
        return written

    async def _delete_run_signals(self, run_id: str) -> None:
        try:
            await self._gw.execute_raw(
                "DELETE FROM strategy_signal_daily WHERE run_id = $1",
                [run_id],
            )
        except Exception as exc:
            logger.warning("Failed to delete signals for run_id=%s: %s", run_id, exc)

    async def _update_run_signal_count(self, run_id: str, signal_count: int, written: int) -> None:
        try:
            await self._gw.execute_raw(
                "UPDATE w2s_backtest_run SET signal_count = $1 WHERE run_id = $2",
                [signal_count, run_id],
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

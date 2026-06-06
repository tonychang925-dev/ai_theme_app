from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_ID = "one_to_two"
DEFAULT_STRATEGY_VERSION = "one_to_two_v1.0_post_market_plan"
DEFAULT_SIGNAL_SESSION = "post_market"
ALLOWED_DECISIONS = {"focus", "observe_only", "pending_review_only"}


class OneToTwoBacktestSignalBuilderService:
    """Build strategy_signal_daily rows from frozen OneToTwo snapshots."""

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

        await self._delete_run_signals(run_id)
        snapshots = await self._load_snapshots(run_id, strategy_id=strategy_id)
        if not snapshots:
            return {"run_id": run_id, "signal_count": 0, "written": 0, "warning": "No snapshots found"}

        signals: list[dict[str, Any]] = []
        for snap in snapshots:
            signal = self._build_one_signal(snap, run_id, strategy_id=strategy_id, strategy_version=strategy_version)
            if signal is not None:
                signals.append(signal)

        written = await self._write_signals(signals)
        if written != len(signals):
            raise RuntimeError("failed to write one_to_two strategy signals")

        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "signal_count": len(signals),
            "written": written,
        }

    def _build_one_signal(
        self,
        snap: dict[str, Any],
        run_id: str,
        *,
        strategy_id: str,
        strategy_version: str,
    ) -> dict[str, Any] | None:
        decision = str(_json_obj(snap.get("derived_feature_json")).get("decision") or snap.get("pool_entry_type") or "").strip()
        if decision not in ALLOWED_DECISIONS:
            return None

        candidate_date = _parse_date(snap.get("candidate_trade_date"))
        if candidate_date is None:
            raise RuntimeError(f"missing candidate_trade_date for snapshot {snap.get('snapshot_id')}")
        watch_date = _parse_date(snap.get("confirm_trade_date")) or (candidate_date + timedelta(days=1))
        if not str(snap.get("stock_id") or "").strip():
            raise RuntimeError(f"missing stock_id for snapshot {snap.get('snapshot_id')}")

        available_at = datetime.combine(candidate_date, time(15, 30))
        tradable_at = datetime.combine(watch_date, time(9, 30))
        snapshot_version = str(snap.get("strategy_version") or strategy_version)
        source_trace = _json_obj(snap.get("source_trace"))
        source_trace.update(
            {
                "run_type": "backtest",
                "signal_run_id": run_id,
                "signal_strategy_id": strategy_id,
                "signal_strategy_version": strategy_version,
            }
        )
        derived = _json_obj(snap.get("derived_feature_json"))
        raw = _json_obj(snap.get("raw_feature_json"))
        evidence = {
            "decision": decision,
            "veto_reasons": list(derived.get("veto_reasons") or raw.get("veto_reasons") or []),
            "risk_flags": list(derived.get("risk_flags") or raw.get("risk_flags") or []),
            "source_snapshot_version": snapshot_version,
            "source_trace": source_trace,
        }

        signal_level = decision
        return {
            "signal_id": str(uuid.uuid4()),
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "trade_date": candidate_date,
            "signal_session": DEFAULT_SIGNAL_SESSION,
            "available_at": available_at,
            "tradable_at": tradable_at,
            "stock_id": str(snap.get("stock_id") or ""),
            "stock_name": str(snap.get("stock_name") or ""),
            "subject_key": str(snap.get("subject_key") or ""),
            "theme_name": str(snap.get("theme_name") or ""),
            "direction": "long_watch",
            "tradable": False,
            "signal_level": signal_level,
            "score": _safe_float(snap.get("final_score") or derived.get("final_score") or snap.get("candidate_score")),
            "confidence": _safe_float(snap.get("final_score") or derived.get("final_score") or snap.get("candidate_score")),
            "confirm_level": signal_level,
            "confirm_source": "one_to_two_backtest",
            "reject_reason_code": None,
            "entry_plan": json.dumps({"decision": decision, "watch_level": snap.get("watch_level")}, ensure_ascii=False),
            "exit_plan": json.dumps({"hold_days": 1, "reason": "watch_only"}, ensure_ascii=False),
            "risk_plan": json.dumps({"run_type": "backtest", "decision": decision}, ensure_ascii=False),
            "evidence_json": json.dumps(evidence, ensure_ascii=False, default=str),
            "source_chain": "stock_processing_service.one_to_two_setup_plan",
            "source_table": "w2s_backtest_feature_snapshot",
            "source_id": str(snap.get("snapshot_id") or ""),
            "source_snapshot_version": snapshot_version,
            "rule_version": strategy_version,
        }

    async def _load_snapshots(self, run_id: str, *, strategy_id: str) -> list[dict[str, Any]]:
        fn = getattr(self._gw, "get_w2s_backtest_feature_snapshots_by_run", None)
        if callable(fn):
            rows = await fn(run_id)
            return [dict(row) for row in rows if str(row.get("strategy_id") or strategy_id) == strategy_id]

        try:
            rows = await self._gw._client.execute_query(
                "SELECT * FROM w2s_backtest_feature_snapshot WHERE run_id = $1 AND strategy_id = $2 ORDER BY candidate_trade_date ASC, stock_id ASC, subject_key ASC",
                [run_id, strategy_id],
            )
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:
            raise RuntimeError(f"failed to load one_to_two snapshots for run_id={run_id}") from exc

    async def _write_signals(self, signals: list[dict[str, Any]]) -> int:
        if not signals:
            return 0
        fn = getattr(self._gw, "upsert_strategy_signal_daily_rows", None)
        if callable(fn):
            written = await fn(signals)
            if written != len(signals):
                raise RuntimeError("failed to write one_to_two strategy signals")
            return written
        return await self._write_via_raw_sql(signals)

    async def _write_via_raw_sql(self, signals: list[dict[str, Any]]) -> int:
        written = 0
        for s in signals:
            try:
                await self._gw._client.execute_query(
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
                        s["trade_date"], str(s["signal_session"]), s["available_at"], s["tradable_at"],
                        str(s["stock_id"]), str(s["stock_name"]), str(s["subject_key"]), str(s["theme_name"]),
                        str(s["direction"]), bool(s["tradable"]), str(s["signal_level"]), s["score"], s["confidence"],
                        str(s["confirm_level"]), str(s["confirm_source"]), s["reject_reason_code"],
                        s["entry_plan"], s["exit_plan"], s["risk_plan"], s["evidence_json"],
                        str(s["source_chain"]), str(s["source_table"]), str(s["source_id"]),
                        str(s["source_snapshot_version"]), str(s["rule_version"]),
                    ],
                )
                written += 1
            except Exception as exc:
                logger.exception("Failed to write OneToTwo signal for %s", s.get("stock_id"))
                raise RuntimeError("failed to write one_to_two strategy signals") from exc
        if written != len(signals):
            raise RuntimeError("failed to write one_to_two strategy signals")
        return written

    async def _delete_run_signals(self, run_id: str) -> None:
        try:
            await self._gw._client.execute_query(
                "DELETE FROM strategy_signal_daily WHERE run_id = $1",
                [run_id],
            )
        except Exception as exc:
            logger.exception("Failed to delete OneToTwo signals for run_id=%s", run_id)
            raise RuntimeError("failed to delete existing one_to_two signals") from exc


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


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "_asdict"):
        return dict(row._asdict())
    if hasattr(row, "__dict__"):
        return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
    return dict(row)

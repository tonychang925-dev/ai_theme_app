from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from stock_processing_service.application.services.backtest.one_to_two_backtest_data_quality_service import (
    OneToTwoBacktestDataQualityService,
)
from stock_processing_service.application.services.one_to_two_setup_plan_engine import (
    OneToTwoSetupPlanEngine,
)
from stock_processing_service.domain.services.one_to_two_rule_config import (
    OneToTwoRuleConfig,
)

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_ID = "one_to_two"
DEFAULT_STRATEGY_VERSION = "one_to_two_v1.0_post_market_plan"


class OneToTwoBacktestFeatureSnapshotService:
    """Freeze OneToTwo setup-plan outputs into unified backtest snapshots."""

    def __init__(
        self,
        read_port: Any,
        gateway: Any,
        engine: OneToTwoSetupPlanEngine | None = None,
        rule_config: OneToTwoRuleConfig | None = None,
        data_quality_service: OneToTwoBacktestDataQualityService | None = None,
    ) -> None:
        self._read = read_port
        self._gw = gateway
        self._engine = engine or OneToTwoSetupPlanEngine(rule_config=rule_config)
        self._data_quality = data_quality_service or OneToTwoBacktestDataQualityService(read_port)

    async def build(
        self,
        *,
        run_id: str,
        strategy_id: str = DEFAULT_STRATEGY_ID,
        strategy_version: str = DEFAULT_STRATEGY_VERSION,
        start_date: date,
        end_date: date,
        rule_version: str | None = None,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        if strategy_id != DEFAULT_STRATEGY_ID:
            raise ValueError("strategy_id must be one_to_two")
        if strategy_version != DEFAULT_STRATEGY_VERSION:
            raise ValueError("strategy_version must be one_to_two_v1.0_post_market_plan")
        if start_date > end_date:
            raise ValueError("invalid date range")

        dq_report = await self._data_quality.check(start_date, end_date)
        if dq_report.get("blocked"):
            raise RuntimeError(str(dq_report.get("block_reason") or "OneToTwo data quality gate blocked"))

        if force_rebuild:
            await self._delete_run_snapshots(run_id)

        engine = self._engine
        if rule_version is not None:
            engine = OneToTwoSetupPlanEngine(rule_config=OneToTwoRuleConfig.from_version(rule_version))

        written = 0
        snapshot_count = 0
        empty_days = 0
        non_empty_days = 0
        focus_count = 0
        observe_count = 0
        pending_count = 0
        reject_count = 0
        trade_dates = await self._load_trade_dates(start_date, end_date)
        for current in trade_dates:
            source_doc = await self._get_report_context(current)
            plan = await engine.build(current, self._read, source_doc=source_doc)
            candidate_features = list(plan.candidate_features or [])
            if not candidate_features:
                empty_days += 1
                continue

            rows = [
                self._to_snapshot_row(
                    run_id=run_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    candidate_index=index,
                    candidate=row,
                    trade_date=current,
                )
                for index, row in enumerate(candidate_features, start=1)
            ]
            seen_keys: set[tuple[str, str]] = set()
            for row in rows:
                stock_id = str(row.get("stock_id") or "").strip()
                subject_key = str(row.get("subject_key") or "").strip()
                if not stock_id:
                    raise RuntimeError("one_to_two snapshot candidate missing stock_id")
                key = (stock_id, subject_key)
                if key in seen_keys:
                    raise RuntimeError(
                        f"duplicate one_to_two snapshot key for trade_date={current.isoformat()} "
                        f"stock_id={stock_id} subject_key={subject_key or '<empty>'}"
                    )
                seen_keys.add(key)
            written_batch = await self._write_snapshots(rows)
            if written_batch != len(rows):
                raise RuntimeError("failed to write one_to_two backtest feature snapshot")
            written += written_batch
            snapshot_count += len(rows)
            non_empty_days += 1
            for row in candidate_features:
                decision = str(row.get("decision") or "")
                if decision == "focus":
                    focus_count += 1
                elif decision == "observe_only":
                    observe_count += 1
                elif decision == "pending_review_only":
                    pending_count += 1
                elif decision == "reject":
                    reject_count += 1

        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "rule_version": rule_version or getattr(self._engine, "rule_version", strategy_version),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "snapshot_count": snapshot_count,
            "written": written,
            "empty_days": empty_days,
            "non_empty_days": non_empty_days,
            "focus_count": focus_count,
            "observe_count": observe_count,
            "pending_count": pending_count,
            "reject_count": reject_count,
            "data_quality_json": dq_report,
        }

    async def _write_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        if not snapshots:
            return 0
        fn = getattr(self._gw, "upsert_w2s_backtest_feature_snapshots", None)
        if callable(fn):
            written = await fn(snapshots)
            if written != len(snapshots):
                raise RuntimeError("failed to write one_to_two backtest feature snapshot")
            return written
        return await self._write_via_raw_sql(snapshots)

    async def _write_via_raw_sql(self, snapshots: list[dict[str, Any]]) -> int:
        written = 0
        for row in snapshots:
            try:
                await self._gw._client.execute_query(
                    """
                    INSERT INTO w2s_backtest_feature_snapshot (
                        snapshot_id, run_id, strategy_id, strategy_version,
                        candidate_trade_date, confirm_trade_date,
                        stock_id, stock_name, subject_key, theme_name,
                        candidate_id, pool_entry_type, candidate_score, candidate_type, weak_type,
                        support_type, support_strength,
                        is_leader, rank_order, recent_limit_up_count, prior7_limitup_days, prior7_strong_days,
                        leader_role_proxy, leader_score_proxy, two_board_quality_score,
                        board_type, is_20cm,
                        mainline_strength_score, fade_watch, fade_confirmed, cycle_state,
                        auction_feature_mode, auction_open_pct, auction_amount,
                        auction_score, confirm_level, confirmation_score,
                        auction_feature_quality, missing_features,
                        bull_stock_score,
                        raw_feature_json, derived_feature_json, source_trace
                    ) VALUES (
                        $1, $2, $3, $4,
                        $5, $6,
                        $7, $8, $9, $10,
                        $11, $12, $13, $14, $15,
                        $16, $17,
                        $18, $19, $20, $21, $22,
                        $23, $24, $25,
                        $26, $27,
                        $28, $29, $30, $31,
                        $32, $33, $34,
                        $35, $36, $37,
                        $38, $39,
                        $40,
                        $41, $42, $43
                    )
                    ON CONFLICT (run_id, strategy_id, strategy_version, candidate_trade_date, confirm_trade_date, stock_id, subject_key)
                    DO UPDATE SET
                        snapshot_id = EXCLUDED.snapshot_id,
                        pool_entry_type = EXCLUDED.pool_entry_type,
                        candidate_score = EXCLUDED.candidate_score,
                        candidate_type = EXCLUDED.candidate_type,
                        weak_type = EXCLUDED.weak_type,
                        support_type = EXCLUDED.support_type,
                        support_strength = EXCLUDED.support_strength,
                        is_leader = EXCLUDED.is_leader,
                        rank_order = EXCLUDED.rank_order,
                        recent_limit_up_count = EXCLUDED.recent_limit_up_count,
                        prior7_limitup_days = EXCLUDED.prior7_limitup_days,
                        prior7_strong_days = EXCLUDED.prior7_strong_days,
                        leader_role_proxy = EXCLUDED.leader_role_proxy,
                        leader_score_proxy = EXCLUDED.leader_score_proxy,
                        two_board_quality_score = EXCLUDED.two_board_quality_score,
                        board_type = EXCLUDED.board_type,
                        is_20cm = EXCLUDED.is_20cm,
                        mainline_strength_score = EXCLUDED.mainline_strength_score,
                        fade_watch = EXCLUDED.fade_watch,
                        fade_confirmed = EXCLUDED.fade_confirmed,
                        cycle_state = EXCLUDED.cycle_state,
                        auction_feature_mode = EXCLUDED.auction_feature_mode,
                        auction_open_pct = EXCLUDED.auction_open_pct,
                        auction_amount = EXCLUDED.auction_amount,
                        auction_score = EXCLUDED.auction_score,
                        confirm_level = EXCLUDED.confirm_level,
                        confirmation_score = EXCLUDED.confirmation_score,
                        auction_feature_quality = EXCLUDED.auction_feature_quality,
                        missing_features = EXCLUDED.missing_features,
                        bull_stock_score = EXCLUDED.bull_stock_score,
                        raw_feature_json = EXCLUDED.raw_feature_json,
                        derived_feature_json = EXCLUDED.derived_feature_json,
                        source_trace = EXCLUDED.source_trace
                    """,
                    [
                        row["snapshot_id"],
                        row["run_id"],
                        row["strategy_id"],
                        row["strategy_version"],
                        row["candidate_trade_date"],
                        row["confirm_trade_date"],
                        row["stock_id"],
                        row["stock_name"],
                        row["subject_key"],
                        row["theme_name"],
                        row["candidate_id"],
                        row["pool_entry_type"],
                        row["candidate_score"],
                        row["candidate_type"],
                        row["weak_type"],
                        row["support_type"],
                        row["support_strength"],
                        row["is_leader"],
                        row["rank_order"],
                        row["recent_limit_up_count"],
                        row["prior7_limitup_days"],
                        row["prior7_strong_days"],
                        row["leader_role_proxy"],
                        row["leader_score_proxy"],
                        row["two_board_quality_score"],
                        row["board_type"],
                        row["is_20cm"],
                        row["mainline_strength_score"],
                        row["fade_watch"],
                        row["fade_confirmed"],
                        row["cycle_state"],
                        row["auction_feature_mode"],
                        row["auction_open_pct"],
                        row["auction_amount"],
                        row["auction_score"],
                        row["confirm_level"],
                        row["confirmation_score"],
                        row["auction_feature_quality"],
                        row["missing_features"],
                        row["bull_stock_score"],
                        row["raw_feature_json"],
                        row["derived_feature_json"],
                        row["source_trace"],
                    ],
                )
                written += 1
            except Exception as exc:
                logger.exception("Failed to write OneToTwo snapshot for %s", row.get("stock_id"))
                raise RuntimeError("failed to write one_to_two backtest feature snapshot") from exc
        if written != len(snapshots):
            raise RuntimeError("failed to write one_to_two backtest feature snapshot")
        return written

    def _to_snapshot_row(
        self,
        *,
        run_id: str,
        strategy_id: str,
        strategy_version: str,
        candidate_index: int,
        candidate: dict[str, Any],
        trade_date: date,
    ) -> dict[str, Any]:
        rule_version = str(candidate.get("rule_version") or strategy_version)
        confirm_trade_date = self._parse_date(candidate.get("watch_date"))
        if confirm_trade_date is None:
            raise RuntimeError(
                f"missing watch_date for one_to_two snapshot row: {candidate.get('stock_id')} {candidate.get('subject_key')}"
            )
        final_score = candidate.get("final_score")
        decision = str(candidate.get("decision") or "")
        raw_feature_json = {
            "rule_version": rule_version,
            "trade_date": candidate.get("trade_date"),
            "watch_date": candidate.get("watch_date"),
            "stock_id": candidate.get("stock_id"),
            "stock_name": candidate.get("stock_name"),
            "subject_key": candidate.get("subject_key"),
            "subject_name": candidate.get("subject_name"),
            "is_confirmed_mainline": candidate.get("is_confirmed_mainline"),
            "is_strong_hotspot": candidate.get("is_strong_hotspot"),
            "mainline_or_hotspot_state": candidate.get("mainline_or_hotspot_state"),
            "lifecycle_state": candidate.get("lifecycle_state"),
            "market_trade_mode": candidate.get("market_trade_mode"),
            "allow_trade": candidate.get("allow_trade"),
            "is_first_limit_up": candidate.get("is_first_limit_up"),
            "is_one_word_board": candidate.get("is_one_word_board"),
            "is_late_seal": candidate.get("is_late_seal"),
            "first_limit_time": candidate.get("first_limit_time"),
            "open_board_count": candidate.get("open_board_count"),
            "turnover_rate": str(candidate.get("turnover_rate")) if candidate.get("turnover_rate") is not None else None,
            "amount": str(candidate.get("amount")) if candidate.get("amount") is not None else None,
            "close_seal_amount": str(candidate.get("close_seal_amount")) if candidate.get("close_seal_amount") is not None else None,
            "seal_ratio": str(candidate.get("seal_ratio")) if candidate.get("seal_ratio") is not None else None,
            "float_mcap": str(candidate.get("float_mcap")) if candidate.get("float_mcap") is not None else None,
            "position_120": str(candidate.get("position_120")) if candidate.get("position_120") is not None else None,
            "is_downtrend": candidate.get("is_downtrend"),
            "near_pressure": candidate.get("near_pressure"),
            "same_subject_limit_count": candidate.get("same_subject_limit_count"),
            "same_subject_strong_count": candidate.get("same_subject_strong_count"),
            "subject_authenticity": candidate.get("subject_authenticity") or {},
            "stock_subject_authenticity": candidate.get("stock_subject_authenticity") or candidate.get("subject_authenticity") or {},
            "stock_subject_authenticity_scope": candidate.get("stock_subject_authenticity_scope")
            or str((candidate.get("stock_subject_authenticity") or candidate.get("subject_authenticity") or {}).get("authenticity_scope") or "subject_fallback"),
            "kline_pattern_quality": candidate.get("kline_pattern_quality") or {},
            "decision": decision,
            "veto_reasons": list(candidate.get("veto_reasons") or []),
            "risk_flags": list(candidate.get("risk_flags") or []),
            "first_board_quality_score": candidate.get("first_board_quality_score"),
            "mainline_context_score": candidate.get("mainline_context_score"),
            "technical_structure_score": candidate.get("technical_structure_score"),
            "risk_control_score": candidate.get("risk_control_score"),
            "final_score": candidate.get("final_score"),
            "watch_level": candidate.get("watch_level"),
            "summary": candidate.get("summary"),
            "evidence_rules": list(candidate.get("evidence_rules") or []),
            "data_quality_json": candidate.get("data_quality_json") or {},
            "source_trace_json": candidate.get("source_trace_json") or {},
            "rule_version": rule_version,
        }
        derived_feature_json = {
            "rule_version": rule_version,
            "decision": decision,
            "final_score": str(final_score) if final_score is not None else None,
            "watch_level": candidate.get("watch_level"),
            "veto_reasons": list(candidate.get("veto_reasons") or []),
            "risk_flags": list(candidate.get("risk_flags") or []),
            "summary": candidate.get("summary"),
            "source_trace": candidate.get("source_trace_json") or {},
            "data_quality": candidate.get("data_quality_json") or {},
            "subject_authenticity": candidate.get("subject_authenticity") or {},
            "stock_subject_authenticity": candidate.get("stock_subject_authenticity") or candidate.get("subject_authenticity") or {},
            "stock_subject_authenticity_scope": candidate.get("stock_subject_authenticity_scope")
            or str((candidate.get("stock_subject_authenticity") or candidate.get("subject_authenticity") or {}).get("authenticity_scope") or "subject_fallback"),
            "kline_pattern_quality": candidate.get("kline_pattern_quality") or {},
            "signal_level": decision,
            "source_chain": "stock_processing_service.one_to_two_setup_plan",
            "source_table": "w2s_backtest_feature_snapshot",
            "source_snapshot_version": strategy_version,
            "run_type": "backtest",
        }
        source_trace = {
            "source_chain": "stock_processing_service.one_to_two_setup_plan",
            "source_table": "w2s_backtest_feature_snapshot",
            "source_snapshot_version": strategy_version,
            "source_strategy_id": strategy_id,
            "source_run_id": run_id,
            "source_trade_date": trade_date.isoformat(),
            "run_type": "backtest",
            "rule_version": rule_version,
            "missing_subject_key": not bool(str(candidate.get("subject_key") or "").strip()),
            "candidate_index": candidate_index,
        }

        return {
            "snapshot_id": str(uuid.uuid4()),
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "rule_version": rule_version,
            "candidate_trade_date": self._parse_date(candidate.get("trade_date")) or trade_date,
            "confirm_trade_date": confirm_trade_date,
            "stock_id": str(candidate.get("stock_id") or ""),
            "stock_name": str(candidate.get("stock_name") or ""),
            "subject_key": str(candidate.get("subject_key") or ""),
            "theme_name": str(candidate.get("subject_name") or ""),
            "candidate_id": None,
            "pool_entry_type": decision,
            "candidate_score": self._to_decimal(candidate.get("final_score")),
            "candidate_type": "one_to_two",
            "weak_type": "",
            "support_type": "",
            "support_strength": None,
            "is_leader": bool(candidate.get("decision") == "focus"),
            "rank_order": candidate_index,
            "recent_limit_up_count": None,
            "prior7_limitup_days": None,
            "prior7_strong_days": None,
            "leader_role_proxy": str(candidate.get("watch_level") or ""),
            "leader_score_proxy": self._to_decimal(candidate.get("final_score")),
            "two_board_quality_score": self._to_decimal(candidate.get("first_board_quality_score")),
            "board_type": str(candidate.get("lifecycle_state") or ""),
            "is_20cm": False,
            "mainline_strength_score": self._to_decimal(candidate.get("mainline_context_score")),
            "fade_watch": False,
            "fade_confirmed": False,
            "cycle_state": str(candidate.get("lifecycle_state") or ""),
            "auction_feature_mode": "one_to_two_backtest",
            "auction_open_pct": None,
            "auction_amount": None,
            "auction_score": self._to_decimal(candidate.get("final_score")),
            "confirm_level": decision,
            "confirmation_score": self._to_decimal(candidate.get("final_score")),
            "auction_feature_quality": "complete" if not candidate.get("veto_reasons") else "partial",
            "missing_features": json.dumps(list(candidate.get("missing_features") or []), ensure_ascii=False),
            "bull_stock_score": None,
            "raw_feature_json": json.dumps(raw_feature_json, ensure_ascii=False, default=str),
            "derived_feature_json": json.dumps(derived_feature_json, ensure_ascii=False, default=str),
            "source_trace": json.dumps(source_trace, ensure_ascii=False, default=str),
        }

    async def _delete_run_snapshots(self, run_id: str) -> None:
        try:
            await self._gw._client.execute_query(
                "DELETE FROM w2s_backtest_feature_snapshot WHERE run_id = $1",
                [run_id],
            )
        except Exception as exc:
            logger.exception("Failed to delete OneToTwo snapshots for run_id=%s", run_id)
            raise RuntimeError("failed to delete existing one_to_two snapshots") from exc

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

    async def _get_report_context(self, trade_date: date) -> dict[str, Any]:
        try:
            return dict(await self._read.get_post_market_report_context(trade_date) or {})
        except Exception as exc:
            raise RuntimeError(
                f"failed to load post_market_report_context for one_to_two snapshot: {trade_date.isoformat()}"
            ) from exc

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

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _row_value(self, row: Any, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

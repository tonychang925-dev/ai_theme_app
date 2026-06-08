"""Feature snapshot service for W2S backtest.

Reads weak_to_strong_candidate_pool, supplements with mainline/leader/auction/daily
bar features, builds raw_feature_json and derived_feature_json, writes to
w2s_backtest_feature_snapshot table.

All features from existing SPS tables — no old-chain dependencies.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from stock_processing_service.domain.backtest.w2s_feature_rules import (
    apply_weak_type_downgrade,
    build_missing_features,
    classify_board_type,
    classify_leader_role_proxy,
    classify_proxy_level,
    classify_weak_type_quality,
    compute_auction_score,
    compute_bull_stock_score,
    compute_confirm_level_from_score,
    compute_leader_score_proxy,
    compute_proxy_confirm_score,
    compute_two_board_quality_score,
    determine_auction_feature_mode,
    determine_confirm_source,
    weak_type_score_bonus,
)

logger = logging.getLogger(__name__)


class W2SFeatureSnapshotService:
    """Generate frozen feature snapshots for W2S candidates."""

    def __init__(
        self,
        read_ports: Any,
        gateway: Any,
    ) -> None:
        self._read = read_ports
        self._gw = gateway

    async def build(
        self,
        *,
        run_id: str,
        strategy_id: str = "weak_to_strong",
        strategy_version: str,
        start_date: date,
        end_date: date,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        """Build feature snapshots for all candidates in the date range.

        Idempotent: if force_rebuild, deletes existing rows for this run_id first.
        """
        # Idempotent rebuild
        if force_rebuild:
            await self._delete_run_snapshots(run_id)

        snapshots: list[dict[str, Any]] = []
        current = start_date

        while current <= end_date:
            cal = await self._read.get_trade_calendar(current)
            if not cal or not cal.calendar_is_open:
                current += timedelta(days=1)
                continue

            # Phase 0: try direct pool read first, fall back to complex join
            try:
                candidates = await self._get_candidates_for_date(current)
            except Exception as exc:
                logger.warning("Failed to read candidates for %s: %s", current, exc)
                candidates = []

            if not candidates:
                current += timedelta(days=1)
                continue

            # Determine confirm_trade_date (next trade day)
            next_date = current + timedelta(days=1)
            while next_date <= end_date + timedelta(days=5):
                next_cal = await self._read.get_trade_calendar(next_date)
                if next_cal and next_cal.calendar_is_open:
                    break
                next_date += timedelta(days=1)
            else:
                next_date = current + timedelta(days=1)

            confirm_trade_date = next_date

            # Load auxiliary data for this candidate date
            auctions = await self._load_auctions(confirm_trade_date)
            auction_stock_ids = {a.stock_id for a in auctions}
            has_auction_series = any(
                getattr(a, "tail_auction_vwap", None) is not None
                for a in auctions
            )

            # Mainline states
            subject_keys = list({
                str(c.get("subject_key") or "")
                for c in candidates
                if str(c.get("subject_key") or "").strip()
            })
            mainline_states = await self._load_mainline_states(current, subject_keys)

            # Daily bars
            bars = await self._load_bars(current)

            for candidate in candidates:
                stock_id = str(candidate.get("stock_id") or "")
                if not stock_id:
                    continue

                snapshot = await self._build_one_snapshot(
                    candidate=candidate,
                    candidate_trade_date=current,
                    confirm_trade_date=confirm_trade_date,
                    auctions=auctions,
                    auction_stock_ids=auction_stock_ids,
                    has_auction_series=has_auction_series,
                    mainline_states=mainline_states,
                    bars=bars,
                    run_id=run_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                )
                snapshots.append(snapshot)

            current += timedelta(days=1)

        # Write snapshots
        written = await self._write_snapshots(snapshots)
        logger.info("Feature snapshot built: %d rows written for run_id=%s", written, run_id)

        return {
            "run_id": run_id,
            "strategy_version": strategy_version,
            "snapshot_count": len(snapshots),
            "written": written,
        }

    async def _build_one_snapshot(
        self,
        *,
        candidate: dict[str, Any],
        candidate_trade_date: date,
        confirm_trade_date: date,
        auctions: list[Any],
        auction_stock_ids: set[str],
        has_auction_series: bool,
        mainline_states: dict[str, dict[str, Any]],
        bars: dict[str, Any],
        run_id: str,
        strategy_id: str,
        strategy_version: str,
    ) -> dict[str, Any]:
        stock_id = str(candidate.get("stock_id") or "")
        subject_key = str(candidate.get("subject_key") or "")

        # ── Raw features (from existing tables, no processing) ──
        raw_feature_json = {
            "candidate_score": candidate.get("candidate_score"),
            "pool_entry_type": candidate.get("pool_entry_type"),
            "candidate_type": candidate.get("candidate_type"),
            "weak_type": candidate.get("weak_type"),
            "support_type": candidate.get("support_type"),
            "support_strength": candidate.get("support_strength"),
            "is_leader": candidate.get("is_leader"),
            "rank_order": candidate.get("rank_order"),
            "recent_limit_up_count": candidate.get("recent_limit_up_count"),
            "prior7_limitup_days": candidate.get("prior7_limitup_days"),
            "prior7_strong_days": candidate.get("prior7_strong_days"),
            "mainline_strength_score": candidate.get("mainline_strength_score"),
            "fade_watch": candidate.get("fade_watch"),
            "fade_confirmed": candidate.get("fade_confirmed"),
            "cycle_state": candidate.get("cycle_state"),
        }

        # ── Auction features ──
        auction = _find_auction(auctions, stock_id)
        auction_open_pct = None
        auction_amount = None
        tail_vwap = None
        if auction is not None:
            auction_open_pct = getattr(auction, "auction_open_pct", None)
            auction_amount = getattr(auction, "auction_amount", None)
            tail_vwap = getattr(auction, "tail_auction_vwap", None)

        # Auction scoring
        open_strength = _to_decimal(auction_open_pct)
        amount_strength = _compute_amount_strength(auction_amount)
        tail_strength = _compute_tail_strength(tail_vwap, candidate)

        has_auction_snapshot = stock_id in auction_stock_ids
        has_daily_bar = stock_id in bars

        confirm_source = determine_confirm_source(
            has_auction_snapshot=has_auction_snapshot,
            has_auction_series=has_auction_series,
            has_daily_bar=has_daily_bar,
        )
        auction_feature_mode = determine_auction_feature_mode(has_auction_series)

        auction_score = compute_auction_score(
            open_strength=open_strength,
            amount_strength=amount_strength,
            tail_strength=tail_strength,
            stability_score=None,  # First version: no stability data
            last_minute_grab_score=None,  # First version: no minute data
        )

        # v0.2: classify confirm_level differently for auction vs proxy
        if confirm_source in ("real_auction", "auction_snapshot"):
            # Real auction data: use auction score for A/B/C/X
            confirm_level = compute_confirm_level_from_score(auction_score)
        elif confirm_source == "daily_open_proxy":
            # Proxy: classify independently. proxy_X only for explicit negatives.
            bar = bars.get(stock_id)
            daily_pct = _to_decimal(getattr(bar, "pct_chg", None)) if bar else None
            confirm_level = classify_proxy_level(
                auction_open_pct=open_strength,
                has_auction_snapshot=False,
                daily_pct_chg=daily_pct,
            )
            # Use proxy-specific scoring for confirmation_score
            proxy_score = compute_proxy_confirm_score(
                auction_open_pct=open_strength,
                daily_pct_chg=daily_pct,
                candidate_score=_to_decimal(candidate.get("candidate_score")),
            )
            auction_score = proxy_score
        else:
            # missing data
            confirm_level = "proxy_unconfirmed"

        # ── Mainline features (v0.4: feature store first, dynamic fallback) ──
        subj_feat = await self._read_subject_feature(candidate_trade_date, subject_key) if subject_key else None
        ml_state = mainline_states.get(subject_key, {})

        if subj_feat:
            mainline_strength_score = _to_decimal(subj_feat.get("mainline_strength_score"))
            cycle_state_from_fs = str(subj_feat.get("cycle_state") or "unknown")
            fade_watch = bool(subj_feat.get("fade_watch") or False)
            fade_confirmed = bool(subj_feat.get("fade_confirmed") or False)
        else:
            mainline_strength_score = _to_decimal(
                candidate.get("mainline_strength_score")
                or ml_state.get("mainline_strength_score")
            )
            cycle_state_from_fs = candidate.get("cycle_state") or ml_state.get("state") or "unknown"
            fade_watch = bool(candidate.get("fade_watch") or False)
            fade_confirmed = bool(candidate.get("fade_confirmed") or False)

        # ── Leader features (v0.4: feature store first, dynamic fallback) ──
        stock_feat = await self._read_strong_stock_feature(candidate_trade_date, stock_id)

        if stock_feat:
            # Use feature store data
            leader_role_proxy = str(stock_feat.get("leader_role_proxy") or "unknown")
            # Also enrich candidate with feature store fields for classify_leader_role_proxy fallback
            enriched = dict(candidate)
            enriched["is_leader"] = stock_feat.get("is_leader", candidate.get("is_leader"))
            enriched["rank_order"] = stock_feat.get("rank_order", candidate.get("rank_order"))
            enriched["recent_limit_up_count"] = stock_feat.get("recent_limit_up_count", candidate.get("recent_limit_up_count"))
            enriched["prior7_limitup_days"] = stock_feat.get("prior7_limitup_days", candidate.get("prior7_limitup_days"))
            enriched["prior7_strong_days"] = stock_feat.get("prior7_strong_days", candidate.get("prior7_strong_days"))
            enriched["watch_score"] = stock_feat.get("watch_score", candidate.get("watch_score"))
            leader_score_proxy = compute_leader_score_proxy(enriched)
            two_board_quality_score = compute_two_board_quality_score(enriched)
        else:
            leader_role_proxy = classify_leader_role_proxy(candidate)
            leader_score_proxy = compute_leader_score_proxy(candidate)
            two_board_quality_score = compute_two_board_quality_score(candidate)

        board_type, is_20cm = classify_board_type(stock_id)

        # ── v0.3 weak type quality ──
        weak_type = str(candidate.get("weak_type") or "")
        weak_type_quality = classify_weak_type_quality(weak_type)

        # Apply weak type downgrade for v0.3
        original_pool_entry = str(candidate.get("pool_entry_type") or "observe_only")
        adjusted_pool_entry = apply_weak_type_downgrade(
            weak_type=weak_type,
            pool_entry_type=original_pool_entry,
            support_strength=_to_decimal(candidate.get("support_strength")),
            mainline_strength_score=mainline_strength_score,
            leader_role_proxy=leader_role_proxy,
        )
        candidate_score_adjusted = _to_decimal(candidate.get("candidate_score"))
        if candidate_score_adjusted is None:
            candidate_score_adjusted = Decimal("0")
        candidate_score_adjusted += weak_type_score_bonus(weak_type)

        # ── Bull stock score (placeholder for Phase 3) ──
        bull_stock_score = None

        # ── Missing features ──
        has_mainline_data = mainline_strength_score is not None
        has_leader_data = candidate.get("is_leader") is not None
        missing_features = build_missing_features(
            has_auction_series=has_auction_series,
            has_auction_snapshot=has_auction_snapshot,
            has_daily_bar=has_daily_bar,
            has_mainline_data=has_mainline_data,
            has_leader_data=has_leader_data,
        )

        # ── Derived features (computed by this service) ──
        auction_feature_quality_val = "complete" if confirm_source == "real_auction" else "partial"
        derived_feature_json = {
            "leader_role_proxy": leader_role_proxy,
            "leader_score_proxy": str(leader_score_proxy),
            "two_board_quality_score": str(two_board_quality_score),
            "board_type": board_type,
            "is_20cm": is_20cm,
            "auction_score": str(auction_score),
            "confirm_level": confirm_level,
            "confirmation_score": str(auction_score),
            "auction_feature_mode": auction_feature_mode,
            "auction_feature_quality": auction_feature_quality_val,
            "confirm_source": confirm_source,
            "weak_type_quality": weak_type_quality,
            "bull_stock_score": str(bull_stock_score) if bull_stock_score is not None else None,
        }

        # ── Source trace (with feature dates for audit) ──
        source_trace = {
            "candidate_source": "weak_to_strong_candidate_pool",
            "candidate_input_fn": "get_w2s_candidates_by_trade_date",
            "subject_feature_date": str(candidate_trade_date),
            "subject_feature_source": "subject_daily_feature" if subj_feat else ("mainline_state_daily" if ml_state else "candidate_row"),
            "strong_stock_feature_date": str(candidate_trade_date) if stock_feat else None,
            "strong_stock_feature_source": "strong_stock_daily_feature" if stock_feat else "candidate_row_fields",
            "auction_source": "stock_auction_snapshot" if auction is not None else "missing",
            "daily_bar_source": "stock_daily_bars" if has_daily_bar else "missing",
            "confirm_source": confirm_source,
            "feature_rule_version": "w2s_feature_rules_v0.3",
        }

        return {
            "snapshot_id": str(uuid.uuid4()),
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "candidate_trade_date": candidate_trade_date,
            "confirm_trade_date": confirm_trade_date,
            "stock_id": stock_id,
            "stock_name": str(candidate.get("stock_name") or ""),
            "subject_key": subject_key,
            "theme_name": str(candidate.get("theme_name") or ""),
            "candidate_id": candidate.get("candidate_id"),
            "pool_entry_type": candidate.get("pool_entry_type"),
            "candidate_score": _to_float_str(candidate.get("candidate_score")),
            "candidate_type": candidate.get("candidate_type"),
            "weak_type": candidate.get("weak_type"),
            "support_type": candidate.get("support_type"),
            "support_strength": _to_float_str(candidate.get("support_strength")),
            "is_leader": bool(
                (stock_feat.get("is_leader") if stock_feat else None)
                or candidate.get("is_leader")
            ),
            "rank_order": int(
                (stock_feat.get("rank_order") if stock_feat else None)
                or candidate.get("rank_order") or 999
            ),
            "recent_limit_up_count": int(
                (stock_feat.get("recent_limit_up_count") if stock_feat else None)
                or candidate.get("recent_limit_up_count") or 0
            ),
            "prior7_limitup_days": int(
                (stock_feat.get("prior7_limitup_days") if stock_feat else None)
                or candidate.get("prior7_limitup_days") or 0
            ),
            "prior7_strong_days": int(
                (stock_feat.get("prior7_strong_days") if stock_feat else None)
                or candidate.get("prior7_strong_days") or 0
            ),
            "leader_role_proxy": leader_role_proxy,
            "leader_score_proxy": str(leader_score_proxy),
            "two_board_quality_score": str(two_board_quality_score),
            "board_type": board_type,
            "is_20cm": is_20cm,
            "mainline_strength_score": str(mainline_strength_score) if mainline_strength_score is not None else None,
            "fade_watch": fade_watch,
            "fade_confirmed": fade_confirmed,
            "cycle_state": cycle_state_from_fs,
            "auction_feature_mode": auction_feature_mode,
            "auction_open_pct": str(auction_open_pct) if auction_open_pct is not None else None,
            "auction_amount": str(auction_amount) if auction_amount is not None else None,
            "auction_score": str(auction_score),
            "confirm_level": confirm_level,
            "confirm_level_detail": confirm_level,
            "confirmation_score": str(auction_score),
            "auction_feature_quality": auction_feature_quality_val,
            "confirm_source": confirm_source,
            "weak_type_quality": weak_type_quality,
            "missing_features": json.dumps(missing_features, ensure_ascii=False),
            "bull_stock_score": str(bull_stock_score) if bull_stock_score is not None else None,
            "raw_feature_json": json.dumps(raw_feature_json, ensure_ascii=False, default=str),
            "derived_feature_json": json.dumps(derived_feature_json, ensure_ascii=False, default=str),
            "source_trace": json.dumps(source_trace, ensure_ascii=False),
        }

    async def _get_candidates_for_date(self, trade_date: date) -> list[dict[str, Any]]:
        """Phase 0: read candidates directly from weak_to_strong_candidate_pool.

        Falls back to get_w2s_candidate_inputs if pool is empty.
        """
        # Try direct pool read first (faster, reads actual candidates)
        fn = getattr(self._gw, "get_w2s_candidates_by_trade_date", None)
        if callable(fn):
            try:
                rows = await fn(trade_date, limit=200)
                if rows:
                    return [_row_dict(r) for r in rows]
            except Exception:
                pass

        # Fallback: use ReadPort (complex join from strong_watch_pool)
        try:
            return await self._read.get_w2s_candidate_inputs(trade_date)
        except Exception:
            return []

    async def _load_auctions(self, trade_date: date) -> list[Any]:
        try:
            return await self._read.get_stock_auction_snapshot(trade_date)
        except Exception:
            return []

    async def _load_mainline_states(
        self,
        trade_date: date,
        subject_keys: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not subject_keys:
            return {}
        try:
            rows = await self._read.get_mainline_state_daily(trade_date, subject_keys)
        except Exception:
            return {}
        return {str(r.get("subject_key", "")): r for r in rows if isinstance(r, dict)}

    async def _load_bars(self, trade_date: date) -> dict[str, Any]:
        try:
            bars = await self._read.get_stock_daily_bars(trade_date)
        except Exception:
            return {}
        return {b.stock_id: b for b in bars}

    async def _write_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        if not snapshots:
            return 0
        fn = getattr(self._gw, "upsert_w2s_backtest_feature_snapshots", None)
        if callable(fn):
            return await fn(snapshots)
        logger.warning("Gateway missing upsert_w2s_backtest_feature_snapshots — using raw SQL")
        return await self._write_via_raw_sql(snapshots)

    async def _write_via_raw_sql(self, snapshots: list[dict[str, Any]]) -> int:
        """Fallback: write snapshots via raw SQL if gateway method not available."""
        written = 0
        for s in snapshots:
            try:
                confirm_trade_date = s.get("confirm_trade_date") or date(1900, 1, 1)
                subject_key = str(s.get("subject_key") or "")
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
                        raw_feature_json, derived_feature_json, source_trace,
                        confirm_source, confirm_level_detail, weak_type_quality
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14, $15, $16, $17, $18, $19, $20, $21,
                        $22, $23, $24, $25, $26, $27, $28, $29, $30, $31,
                        $32, $33, $34, $35, $36, $37, $38, $39, $40, $41,
                        $42, $43, $44, $45, $46
                    )
                    ON CONFLICT (run_id, strategy_id, strategy_version, candidate_trade_date, confirm_trade_date, stock_id, subject_key)
                    DO UPDATE SET
                        snapshot_id = EXCLUDED.snapshot_id,
                        strategy_id = EXCLUDED.strategy_id,
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
                        confirm_level_detail = EXCLUDED.confirm_level_detail,
                        confirmation_score = EXCLUDED.confirmation_score,
                        auction_feature_quality = EXCLUDED.auction_feature_quality,
                        confirm_source = EXCLUDED.confirm_source,
                        weak_type_quality = EXCLUDED.weak_type_quality,
                        missing_features = EXCLUDED.missing_features,
                        bull_stock_score = EXCLUDED.bull_stock_score,
                        raw_feature_json = EXCLUDED.raw_feature_json,
                        derived_feature_json = EXCLUDED.derived_feature_json,
                        source_trace = EXCLUDED.source_trace
                    """,
                    [
                        s["snapshot_id"], s["run_id"], s["strategy_id"], s["strategy_version"],
                        s["candidate_trade_date"], confirm_trade_date,
                        s["stock_id"], s["stock_name"], subject_key, s["theme_name"],
                        s["candidate_id"], s["pool_entry_type"], s["candidate_score"], s["candidate_type"], s["weak_type"],
                        s["support_type"], s["support_strength"],
                        s["is_leader"], s["rank_order"], s["recent_limit_up_count"], s["prior7_limitup_days"], s["prior7_strong_days"],
                        s["leader_role_proxy"], s["leader_score_proxy"], s["two_board_quality_score"],
                        s["board_type"], s["is_20cm"],
                        s["mainline_strength_score"], s["fade_watch"], s["fade_confirmed"], s["cycle_state"],
                        s["auction_feature_mode"], s["auction_open_pct"], s["auction_amount"],
                        s["auction_score"], s["confirm_level"], s["confirmation_score"],
                        s["auction_feature_quality"], s["missing_features"],
                        s["bull_stock_score"],
                        s["raw_feature_json"], s["derived_feature_json"], s["source_trace"],
                        s.get("confirm_source", "missing"), s["confirm_level_detail"], s["weak_type_quality"],
                    ],
                )
                written += 1
            except Exception as exc:
                logger.error("Failed to write snapshot for %s: %s", s.get("stock_id"), exc)
        return written

    async def _read_subject_feature(self, trade_date: date, subject_key: str) -> dict[str, Any] | None:
        """Phase -1: read A-layer subject features from feature store."""
        try:
            rows = await self._gw._client.execute_query(
                "SELECT * FROM subject_daily_feature WHERE trade_date = $1 AND subject_key = $2 AND rule_version = 'subject_feature_v0.1' LIMIT 1",
                (trade_date, subject_key),
            )
            return _row_dict(rows[0]) if rows else None
        except Exception:
            return None

    async def _read_strong_stock_feature(self, trade_date: date, stock_id: str) -> dict[str, Any] | None:
        """Phase -1: read B-layer strong stock features from feature store.

        STRICT MODE: only exact date or most recent <= trade_date.
        NO any-date fallback (future leak prevention).
        Returns None if no valid feature found.
        """
        try:
            sid = _normalize(str(stock_id))
            # Try exact date match first
            rows = await self._gw._client.execute_query(
                "SELECT * FROM strong_stock_daily_feature WHERE trade_date = $1 AND stock_id = $2 AND rule_version = 'strong_stock_feature_v0.1' LIMIT 1",
                (trade_date, sid),
            )
            if rows:
                return _row_dict(rows[0])
            # Fallback: most recent row before or on this date
            rows = await self._gw._client.execute_query(
                "SELECT * FROM strong_stock_daily_feature WHERE trade_date <= $1 AND stock_id = $2 AND rule_version = 'strong_stock_feature_v0.1' ORDER BY trade_date DESC LIMIT 1",
                (trade_date, sid),
            )
            if rows:
                return _row_dict(rows[0])
            # STRICT: no any-date fallback. Missing feature = marked as missing.
            return None
        except Exception:
            return None

    async def _delete_run_snapshots(self, run_id: str) -> None:
        """Delete existing snapshots for a run_id (idempotent rebuild)."""
        try:
            fn = getattr(self._gw, "delete_w2s_backtest_snapshots_by_run", None)
            if callable(fn):
                await fn(run_id)
            else:
                await self._gw._client.execute_query(
                    "DELETE FROM w2s_backtest_feature_snapshot WHERE run_id = $1",
                    [run_id],
                )
        except Exception as exc:
            logger.warning("Failed to delete snapshots for run_id=%s: %s", run_id, exc)


# ── Module-level helpers ──

def _find_auction(auctions: list[Any], stock_id: str) -> Any:
    for a in auctions:
        sid = getattr(a, "stock_id", "")
        if _normalize(sid) == _normalize(stock_id):
            return a
    return None


def _normalize(s: str) -> str:
    s = str(s or "").strip().upper()
    if "." in s:
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        if s.startswith(("0", "2", "3")):
            return f"{s}.SZ"
        if s.startswith(("4", "8")):
            return f"{s}.BJ"
    return s


def _row_dict(row: Any) -> dict[str, Any]:
    """Convert any row-like object to dict, with field name mapping."""
    if isinstance(row, dict):
        d = dict(row)
    elif hasattr(row, "_asdict"):
        d = dict(row._asdict())
    elif hasattr(row, "__dict__"):
        d = {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
    else:
        d = dict(row)

    # Field name mapping from weak_to_strong_candidate_pool to snapshot fields
    _map(d, "prev_limit_up_count", "recent_limit_up_count")
    _map(d, "is_dragon_head", "is_leader")
    _map(d, "pool_entry_type_orig", "pool_entry_type")
    # Ensure stock_id is normalized
    if d.get("stock_id"):
        d["stock_id"] = _normalize(str(d["stock_id"]))
    return d


def _map(d: dict[str, Any], src: str, dst: str) -> None:
    if dst not in d and src in d:
        d[dst] = d[src]


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_float_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(float(value))
    except (ValueError, TypeError):
        return None


def _compute_amount_strength(auction_amount: Any) -> Decimal | None:
    """Normalize auction amount to a strength score."""
    if auction_amount is None:
        return None
    amount = float(auction_amount)
    if amount <= 0:
        return Decimal("0")
    # log-normal approach: map [100k, 50M] to [0, 100]
    import math
    raw = math.log(max(amount, 1)) * 8
    return Decimal(str(min(100, max(0, raw))))


def _compute_tail_strength(tail_vwap: Any, candidate: dict[str, Any]) -> Decimal | None:
    """Compute tail auction VWAP strength as percentage of pre_close.

    Refactored from old tail_vwap * 5 which was biased to high-price stocks.
    tail_strength = (tail_vwap - pre_close) / pre_close * 100
    """
    if tail_vwap is None:
        return None
    pre_close_raw = candidate.get("pre_close") or candidate.get("prev_close")
    if pre_close_raw is None:
        return None
    try:
        tv = float(tail_vwap)
        pc = float(pre_close_raw)
        if pc <= 0:
            return None
        pct = (tv - pc) / pc * 100
        return Decimal(str(max(-10, min(10, pct))))
    except (ValueError, TypeError):
        return None

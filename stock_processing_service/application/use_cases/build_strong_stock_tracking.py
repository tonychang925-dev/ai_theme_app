from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import BuildResult, MainlineCycleDTO, MainlineIdentityDTO, PriorSnapshotDTO, StockBarDTO
from stock_processing_service.domain.services.kline_support_scorer import KlineSupportScorer
from stock_processing_service.domain.services.strong_stock_tracking_service import (
    BoardSnapshot,
    CycleSnapshot,
    PatternSnapshot,
    PositionSnapshot,
    StrongStockTrackingService,
    WatchScoreResult,
    WatchSeedRow,
)
from stock_processing_service.ports.cache_ports import CachePorts
from stock_processing_service.ports.read_ports import StockReadPorts
from stock_processing_service.ports.write_ports import StockWritePorts


LAYER_C_INPUT_MODE = "strong_watch_pool_7d_union"


@dataclass(slots=True)
class BuildStrongStockTrackingUseCase:
    """Build Layer C strong-stock tracking pool from design-defined seed inputs.

    This use case owns Layer C scoring and writes only Layer C object tables:
    strong watch pool + strong watch history. It does not write daily snapshots
    and does not invent Layer A/B truth when cycle evidence is absent.
    """

    read_ports: StockReadPorts
    write_ports: StockWritePorts
    cache_ports: CachePorts | None = None
    tracking_service: StrongStockTrackingService | None = None

    async def execute(self, trade_date: date, window_days: int = 7, lookback_days: int = 8) -> BuildResult:
        if window_days != 7:
            raise ValueError("Layer C contract currently supports only the 7-day strong watch window")

        service = self.tracking_service or StrongStockTrackingService()

        seed_rows_raw = await self.read_ports.get_strong_watch_seed_rows(trade_date, lookback_days=lookback_days)
        seed_candidates = service.build_seed_candidates(seed_rows_raw)
        refresh_rows_raw = await self.read_ports.get_strong_watch_refresh_rows(trade_date)

        refresh_stock_ids: set[str] = set()
        for row in refresh_rows_raw:
            sid = self._normalize_stock_id(str(row.get("stock_id") or ""))
            if sid:
                refresh_stock_ids.add(sid)
        seed_stock_ids = {s.stock_id for s in seed_candidates}
        all_stock_ids = sorted(seed_stock_ids | refresh_stock_ids)
        all_subject_keys = sorted(
            {s.subject_key for s in seed_candidates if s.subject_key}
            | {str(row.get("subject_key") or "") for row in refresh_rows_raw if str(row.get("subject_key") or "")}
        )

        identities_raw = await self.read_ports.get_mainline_identity_by_subject_keys(
            subject_keys=all_subject_keys, trade_date=trade_date,
        )
        cycles_raw = await self.read_ports.get_mainline_cycle_by_subject_keys(
            subject_keys=all_subject_keys, trade_date=trade_date,
        )
        evidence_raw = await self.read_ports.get_subject_cycle_evidence_daily(
            trade_date, subject_keys=all_subject_keys,
        )
        board_stats_raw = await self.read_ports.get_subject_board_stats(trade_date)
        positions_raw = await self.read_ports.get_stock_position_judgement(trade_date, all_stock_ids)
        patterns_raw = await self.read_ports.get_stock_pattern_judgement(trade_date, all_stock_ids)
        bars_raw = await self.read_ports.get_stock_daily_bars(trade_date, all_stock_ids)

        prev_trade_date = trade_date
        cal = await self.read_ports.get_trade_calendar(trade_date)
        if cal is not None:
            prev_td = cal.prev_trade_date if hasattr(cal, "prev_trade_date") else (cal.get("prev_trade_date") if isinstance(cal, dict) else None)
            if prev_td is not None:
                prev_trade_date = date.fromisoformat(prev_td) if isinstance(prev_td, str) else prev_td

        prev_day_bars_raw = await self.read_ports.get_stock_daily_bars(prev_trade_date, all_stock_ids)
        prior_rows_raw = await self.read_ports.get_prior_stock_daily_snapshots(
            trade_date=trade_date, lookback_days=lookback_days, stock_ids=all_stock_ids,
        )
        history_start = trade_date - timedelta(days=90)
        history_bars_raw = await self.read_ports.get_stock_daily_bars_range(
            start_date=history_start, end_date=trade_date, stock_ids=all_stock_ids,
        )

        bars = [self._to_stock_bar(row, trade_date) for row in bars_raw]
        prev_day_bars = [self._to_stock_bar(row, prev_trade_date) for row in prev_day_bars_raw]
        prior_rows = [self._to_prior_row(row, trade_date) for row in prior_rows_raw]
        history_bars = [self._to_stock_bar(row, history_start) for row in history_bars_raw]
        identities = [self._to_identity(row) for row in identities_raw]
        cycles = [self._to_cycle(row, trade_date) for row in cycles_raw]

        identities_by_subject = {x.subject_key: x for x in identities}
        cycles_by_subject = {x.subject_key: x for x in cycles}
        evidence_by_subject = {str(row.get("subject_key") or ""): dict(row) for row in evidence_raw}
        board_by_subject = {str(row.get("subject_key") or ""): dict(row) for row in board_stats_raw}
        pos_by_stock = {self._normalize_stock_id(str(row.get("stock_id") or "")): dict(row) for row in positions_raw}
        pattern_by_stock = {self._normalize_stock_id(str(row.get("stock_id") or "")): dict(row) for row in patterns_raw}

        support_scorer = KlineSupportScorer()
        bars_by_stock = {b.stock_id: b for b in bars}
        prior_by_stock: dict[str, list[PriorSnapshotDTO]] = {}
        for pr in prior_rows:
            prior_by_stock.setdefault(pr.stock_id, []).append(pr)
        history_bars_by_stock: dict[str, list[StockBarDTO]] = {}
        for hb in history_bars:
            history_bars_by_stock.setdefault(hb.stock_id, []).append(hb)

        watch_pool_results: list[WatchScoreResult] = []
        seed_stock_id_set = {s.stock_id for s in seed_candidates}

        def score_all(candidates: list[WatchSeedRow], current_flag_map: dict[str, int] | None = None) -> None:
            for candidate in candidates:
                stock_id = candidate.stock_id
                flag_today = (current_flag_map or {}).get(stock_id, candidate.current_flag_today)
                cyc = cycles_by_subject.get(candidate.subject_key)
                has_two_board = bool(candidate.labels.get("has_two_board") or False)
                if cyc is None and not has_two_board:
                    raise RuntimeError(
                        "build_strong_stock_tracking failed: missing Layer B cycle truth for Layer C scoring; "
                        f"trade_date={trade_date.isoformat()}; subject_key={candidate.subject_key}; stock_id={stock_id}"
                    )
                identity = identities_by_subject.get(candidate.subject_key)
                cycle_snap = CycleSnapshot(
                    final_cycle_state=str(getattr(cyc, "final_cycle_state", "") or "") if cyc else "",
                    effective_mainline_alive=bool(
                        cyc
                        and identity
                        and getattr(identity, "is_main_theme", False)
                        and getattr(identity, "identity_status", "") == "confirmed"
                        and getattr(cyc, "final_mainline_alive", False)
                    ),
                    fade_watch=bool(getattr(cyc, "fade_watch", False)) if cyc else False,
                    fade_confirmed=bool(getattr(cyc, "fade_confirmed", False)) if cyc else False,
                    mainline_strength_score=float(getattr(cyc, "mainline_strength_score", 0) or 0) if cyc else 0.0,
                    event_continuity_score=float(
                        (evidence_by_subject.get(candidate.subject_key, {})).get("event_continuity_score", 0) or 0
                    ),
                )
                bd = board_by_subject.get(candidate.subject_key, {})
                board_snap = BoardSnapshot(
                    subject_limit_up_count=int(bd.get("subject_limit_up_count") or 0),
                    subject_strong_count=int(bd.get("subject_strong_count") or 0),
                )
                pos_raw = pos_by_stock.get(stock_id, {})
                pos_snap = PositionSnapshot(
                    position_label=str(pos_raw.get("position_label") or ""),
                    ma_alignment_status=str(pos_raw.get("ma_alignment_status") or ""),
                    trend_strength_score=float(pos_raw.get("trend_strength_score") or 0.0),
                )
                pat_raw = pattern_by_stock.get(stock_id, {})
                pattern_labels_raw = pat_raw.get("pattern_labels")
                if isinstance(pattern_labels_raw, str):
                    try:
                        pattern_labels_raw = json.loads(pattern_labels_raw)
                    except Exception:
                        pattern_labels_raw = []
                elif not isinstance(pattern_labels_raw, list):
                    pattern_labels_raw = []
                pattern_snap = PatternSnapshot(
                    pattern_labels=[str(x) for x in pattern_labels_raw],
                    volume_pattern_status=str(pat_raw.get("volume_pattern_status") or ""),
                    breakout_status=str(pat_raw.get("breakout_status") or ""),
                    pullback_status=str(pat_raw.get("pullback_status") or ""),
                    risk_pattern_status=str(pat_raw.get("risk_pattern_status") or ""),
                )
                bar = bars_by_stock.get(stock_id) or StockBarDTO(
                    trade_date=trade_date, stock_id=stock_id, stock_name="",
                    open_price=Decimal("0"), high_price=Decimal("0"),
                    low_price=Decimal("0"), close_price=Decimal("0"),
                    pre_close=Decimal("0"), pct_chg=Decimal("0"),
                    volume=Decimal("0"), amount=Decimal("0"),
                    limit_up_price=Decimal("0"), limit_down_price=Decimal("0"),
                )
                support_result = support_scorer.score(
                    stock_id=stock_id,
                    current_bar=bar,
                    prior_rows=prior_by_stock.get(stock_id, []),
                    history_bars=history_bars_by_stock.get(stock_id, []),
                )
                result = service.score_watch_row(
                    candidate,
                    current_flag_today=flag_today,
                    close_price=float(bar.close_price) if bar.close_price else None,
                    cycle=cycle_snap,
                    board=board_snap,
                    support_result=support_result,
                    pos=pos_snap,
                    pattern=pattern_snap,
                )
                watch_pool_results.append(result)

        score_all(seed_candidates)
        for row in refresh_rows_raw:
            sid = self._normalize_stock_id(str(row.get("stock_id") or ""))
            if not sid or sid in seed_stock_id_set:
                continue
            labels_json = self._json_obj(row.get("labels_json"))
            refresh_candidate = WatchSeedRow(
                stock_id=sid,
                stock_name=str(row.get("stock_name") or ""),
                subject_key=str(row.get("subject_key") or ""),
                theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
                source_tag=str(row.get("source_tag") or "refresh"),
                relay_role=str(row.get("relay_role") or "unknown"),
                recent_limit_up_count=int(labels_json.get("recent_limit_up_count") or 0),
                current_flag_today=int(row.get("current_flag_today") or 0),
                is_dragon_head=bool(labels_json.get("is_dragon_head") or False),
                is_front_row_core=bool(labels_json.get("is_front_row_core") or False),
                board_effect_confirmed=bool(labels_json.get("board_effect_confirmed") or False),
                subject_limit_up_count=int(labels_json.get("subject_limit_up_count") or 0),
                subject_strong_count=int(labels_json.get("subject_strong_count") or 0),
                labels=dict(labels_json),
                evidence=self._json_obj(row.get("evidence_json")),
            )
            score_all([refresh_candidate], {sid: int(row.get("current_flag_today") or 0)})

        pool_write_rows = [self._pool_row(trade_date, r) for r in watch_pool_results if r.stock_id]
        pool_written = await self.write_ports.upsert_strong_watch_pool_rows(pool_write_rows)

        written_ids = [str(r["stock_id"]) for r in pool_write_rows if r.get("stock_id")]
        if written_ids:
            await self.write_ports.recompute_strong_watch_window_days(written_ids)

        formal_ids = {
            r.stock_id for r in watch_pool_results
            if r.watch_status in {"active", "weakening"}
            and r.pool_entry_type in {"formal", "observe_only"}
            and not r.fade_confirmed
        }
        promote_count = await self.write_ports.promote_strong_watch_candidates(trade_date)
        prune_count = await self.write_ports.prune_strong_watch_pool(trade_date)

        history_rows = [self._history_row(trade_date, r, formal_ids) for r in watch_pool_results if r.stock_id]
        history_written = await self.write_ports.upsert_strong_watch_history_rows(history_rows)

        return BuildResult(
            name="build_strong_stock_tracking",
            trade_date=trade_date.isoformat(),
            affected_rows=history_written,
            status="ok",
            metrics={
                "layer_c_input_mode": LAYER_C_INPUT_MODE,
                "seed_count": len(seed_candidates),
                "refresh_count": len(refresh_rows_raw),
                "pool_written": pool_written,
                "promote_count": promote_count,
                "prune_count": prune_count,
                "history_written": history_written,
                "history_count": len(history_rows),
                "subject_key_count": len(all_subject_keys),
                "stock_id_count": len(all_stock_ids),
                "history_rows": history_rows,
                "pool_rows": pool_write_rows,
                "subject_keys": all_subject_keys,
                "stock_ids": all_stock_ids,
            },
        )

    @staticmethod
    def _pool_row(trade_date: date, result: WatchScoreResult) -> dict[str, Any]:
        return {
            "trade_date": trade_date,
            "stock_id": result.stock_id,
            "stock_name": result.stock_name,
            "subject_key": result.subject_key,
            "theme_name": result.theme_name,
            "watch_window_days": 1,
            "source_tag": result.source_tag,
            "relay_role": result.relay_role,
            "watch_status": result.watch_status,
            "watch_priority": str(result.watch_priority),
            "watch_score": str(result.watch_score),
            "pool_entry_type": result.pool_entry_type,
            "cycle_state": result.cycle_state,
            "mainline_strength_score": str(result.mainline_strength_score),
            "fade_watch": result.fade_watch,
            "fade_confirmed": result.fade_confirmed,
            "support_type": result.support_type,
            "support_level": str(result.support_level or "0"),
            "support_score": str(result.support_score),
            "labels": result.labels,
            "evidence": result.evidence,
        }

    @staticmethod
    def _history_row(trade_date: date, result: WatchScoreResult, formal_ids: set[str]) -> dict[str, Any]:
        return {
            "trade_date": trade_date,
            "stock_id": result.stock_id,
            "stock_name": result.stock_name,
            "subject_key": result.subject_key,
            "theme_name": result.theme_name,
            "watch_status": result.watch_status,
            "watch_score": str(result.watch_score),
            "watch_priority": str(result.watch_priority),
            "pool_entry_type": result.pool_entry_type,
            "relay_role": result.relay_role,
            "cycle_state": result.cycle_state,
            "mainline_strength_score": str(result.mainline_strength_score),
            "fade_watch": result.fade_watch,
            "fade_confirmed": result.fade_confirmed,
            "promoted_to_candidate": result.stock_id in formal_ids,
            "strong_grade": result.strong_grade,
            "removed_reason": result.removed_reason or "",
            "prune_mode": "immediate" if result.watch_status == "removed" else None,
            "prune_reason_code": result.removed_reason or "",
            "kept_because": None,
            "watch_window_days": 1,
            "support_type": result.support_type,
            "support_level": str(result.support_level or "0"),
            "support_score": str(result.support_score),
            "labels_json": result.labels,
            "evidence_json": result.evidence,
        }

    @staticmethod
    def _json_obj(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str) and raw:
            try:
                parsed = json.loads(raw)
                return dict(parsed) if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _d(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _normalize_stock_id(value: Any) -> str:
        stock_id = str(value or "").strip().upper()
        if not stock_id:
            return ""
        if "." in stock_id:
            return stock_id
        if len(stock_id) == 6 and stock_id.isdigit():
            if stock_id.startswith(("6", "9")):
                return f"{stock_id}.SH"
            if stock_id.startswith(("0", "2", "3")):
                return f"{stock_id}.SZ"
            if stock_id.startswith(("4", "8")):
                return f"{stock_id}.BJ"
        return stock_id

    @classmethod
    def _to_stock_bar(cls, row: Any, default_trade_date: date) -> StockBarDTO:
        if isinstance(row, StockBarDTO):
            return row
        p = dict(row or {})
        return StockBarDTO(
            trade_date=p.get("trade_date", default_trade_date),
            stock_id=cls._normalize_stock_id(p.get("stock_id", "")),
            stock_name=str(p.get("stock_name", "")),
            open_price=cls._d(p.get("open_price")),
            high_price=cls._d(p.get("high_price")),
            low_price=cls._d(p.get("low_price")),
            close_price=cls._d(p.get("close_price")),
            pre_close=cls._d(p.get("pre_close")),
            pct_chg=cls._d(p.get("pct_chg")),
            volume=cls._d(p.get("volume")),
            amount=cls._d(p.get("amount")),
            limit_up_price=cls._d(p.get("limit_up_price")),
            limit_down_price=cls._d(p.get("limit_down_price")),
        )

    @classmethod
    def _to_prior_row(cls, row: Any, default_trade_date: date) -> PriorSnapshotDTO:
        if isinstance(row, PriorSnapshotDTO):
            return row
        p = dict(row or {})
        payload = p.get("payload")
        if not isinstance(payload, dict):
            payload = {}
            for key in ("open_price", "high_price", "low_price", "close_price", "pre_close", "pct_chg", "watch_score"):
                if p.get(key) is not None:
                    payload[key] = str(p.get(key))
        return PriorSnapshotDTO(
            trade_date=p.get("trade_date", default_trade_date),
            stock_id=cls._normalize_stock_id(p.get("stock_id", "")),
            snapshot_version=str(p.get("snapshot_version", "")),
            payload=payload,
        )

    @staticmethod
    def _to_identity(row: Any) -> MainlineIdentityDTO:
        if isinstance(row, MainlineIdentityDTO):
            return row
        p = dict(row or {})
        return MainlineIdentityDTO(
            subject_key=str(p.get("subject_key", "")),
            identity_status=str(p.get("identity_status", "")),
            is_main_theme=bool(p.get("is_main_theme", False)),
            first_confirmed_date=p.get("first_confirmed_date"),
            last_review_date=p.get("last_review_date"),
            rule_version=str(p.get("rule_version", "")),
        )

    @classmethod
    def _to_cycle(cls, row: Any, default_trade_date: date) -> MainlineCycleDTO:
        if isinstance(row, MainlineCycleDTO):
            return row
        p = dict(row or {})
        if "final_mainline_alive" not in p:
            raise RuntimeError(
                "invalid Layer B cycle row: missing final_mainline_alive; "
                f"subject_key={p.get('subject_key', '')}; trade_date={p.get('trade_date', default_trade_date)}"
            )
        trigger_flags = p.get("trigger_flags")
        return MainlineCycleDTO(
            trade_date=p.get("trade_date", default_trade_date),
            subject_key=str(p.get("subject_key", "")),
            final_cycle_state=str(p.get("final_cycle_state", "")),
            final_mainline_alive=bool(p.get("final_mainline_alive")),
            transition_type=str(p.get("transition_type", "")),
            transition_confidence=cls._d(p.get("transition_confidence")),
            trigger_flags=list(trigger_flags) if isinstance(trigger_flags, list) else [],
            mainline_strength_score=cls._d(p.get("mainline_strength_score")),
            repair_score=cls._d(p.get("repair_score")),
            divergence_score=cls._d(p.get("divergence_score")),
            fade_watch_score=cls._d(p.get("fade_watch_score")),
            fade_confirmed_score=cls._d(p.get("fade_confirmed_score")),
        )

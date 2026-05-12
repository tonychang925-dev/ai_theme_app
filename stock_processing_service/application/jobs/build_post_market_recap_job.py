from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import uuid4

from stock_processing_service.application.cache import SnapshotCacheWriter
from stock_processing_service.contracts.dto import (
    BuildResult,
    MainlineCycleDTO,
    MainlineIdentityDTO,
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectStockPoolDTO,
)
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.contracts.snapshots import PostMarketRecapSnapshot
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
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService
from stock_processing_service.ports import (
    IdempotencyPort,
    StockCachePort,
    StockEventPort,
    StockReadPort,
    StockWritePort,
)


class BuildPostMarketRecapJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: StockWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        cache_port: StockCachePort | None = None,
        candidate_service: W2SCandidateService | None = None,
        tracking_service: StrongStockTrackingService | None = None,
        identity_job: Any | None = None,  # BuildIdentityJob — Layer A 前置
        mainline_state_job: Any | None = None,  # BuildMainlineStateJob — Layer B 前置
        cycle_judgement_job: Any | None = None,  # BuildCycleJudgementJob — Layer B 前置
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._cache_port = cache_port
        self._cache_writer = SnapshotCacheWriter(cache_port)
        self._candidate_service = candidate_service or W2SCandidateService()
        self._tracking_service = tracking_service or StrongStockTrackingService()
        self._identity_job = identity_job
        self._mainline_state_job = mainline_state_job
        self._cycle_judgement_job = cycle_judgement_job

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

    @staticmethod
    def _to_stock_bar(row: Any, default_trade_date: date) -> StockBarDTO:
        if isinstance(row, StockBarDTO):
            return row
        p = dict(row or {})
        return StockBarDTO(
            trade_date=p.get("trade_date", default_trade_date),
            stock_id=BuildPostMarketRecapJob._normalize_stock_id(p.get("stock_id", "")),
            stock_name=str(p.get("stock_name", "")),
            open_price=BuildPostMarketRecapJob._d(p.get("open_price")),
            high_price=BuildPostMarketRecapJob._d(p.get("high_price")),
            low_price=BuildPostMarketRecapJob._d(p.get("low_price")),
            close_price=BuildPostMarketRecapJob._d(p.get("close_price")),
            pre_close=BuildPostMarketRecapJob._d(p.get("pre_close")),
            pct_chg=BuildPostMarketRecapJob._d(p.get("pct_chg")),
            volume=BuildPostMarketRecapJob._d(p.get("volume")),
            amount=BuildPostMarketRecapJob._d(p.get("amount")),
            limit_up_price=BuildPostMarketRecapJob._d(p.get("limit_up_price")),
            limit_down_price=BuildPostMarketRecapJob._d(p.get("limit_down_price")),
        )

    @staticmethod
    def _to_pool_row(row: Any, default_trade_date: date) -> SubjectStockPoolDTO:
        if isinstance(row, SubjectStockPoolDTO):
            return row
        p = dict(row or {})
        metadata = p.get("metadata")
        return SubjectStockPoolDTO(
            trade_date=p.get("trade_date", default_trade_date),
            subject_key=str(p.get("subject_key", "")),
            subject_name=str(p.get("subject_name") or p.get("theme_name") or p.get("subject_key") or ""),
            stock_id=BuildPostMarketRecapJob._normalize_stock_id(p.get("stock_id", "")),
            stock_name=p.get("stock_name"),
            pool_rank=p.get("pool_rank", p.get("rank_order")),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    @staticmethod
    def _to_prior_row(row: Any, default_trade_date: date) -> PriorSnapshotDTO:
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
            stock_id=BuildPostMarketRecapJob._normalize_stock_id(p.get("stock_id", "")),
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

    @staticmethod
    def _to_cycle(row: Any, default_trade_date: date) -> MainlineCycleDTO:
        if isinstance(row, MainlineCycleDTO):
            return row
        p = dict(row or {})
        trigger_flags = p.get("trigger_flags")
        return MainlineCycleDTO(
            trade_date=p.get("trade_date", default_trade_date),
            subject_key=str(p.get("subject_key", "")),
            final_cycle_state=str(p.get("final_cycle_state", "")),
            final_mainline_alive=bool(p.get("final_mainline_alive", False)),
            transition_type=str(p.get("transition_type", "")),
            transition_confidence=BuildPostMarketRecapJob._d(p.get("transition_confidence")),
            trigger_flags=list(trigger_flags) if isinstance(trigger_flags, list) else [],
            mainline_strength_score=BuildPostMarketRecapJob._d(p.get("mainline_strength_score")),
            repair_score=BuildPostMarketRecapJob._d(p.get("repair_score")),
            divergence_score=BuildPostMarketRecapJob._d(p.get("divergence_score")),
            fade_watch_score=BuildPostMarketRecapJob._d(p.get("fade_watch_score")),
            fade_confirmed_score=BuildPostMarketRecapJob._d(p.get("fade_confirmed_score")),
        )

    @staticmethod
    def _grade_from_watch_score(score: Decimal) -> str:
        if score >= Decimal("78"):
            return "S"
        if score >= Decimal("66"):
            return "A"
        if score >= Decimal("54"):
            return "B"
        return "REJECT"

    @staticmethod
    def _build_prior_active_strong_watch_records(prior_watch_rows: list[Any]) -> list[StrongWatchRecord]:
        grouped: dict[str, list[Any]] = {}
        for row in prior_watch_rows:
            stock_id = str(getattr(row, "stock_id", "") or "")
            if not stock_id:
                continue
            grouped.setdefault(stock_id, []).append(row)

        records: list[StrongWatchRecord] = []
        for stock_id, rows in grouped.items():
            latest = rows[0]
            md = getattr(latest, "metadata", {}) or {}
            watch_status = str(md.get("watch_status") or "")
            pool_entry_type = str(md.get("pool_entry_type") or "")
            if not StrongStockTrackingService.is_candidate_eligible(
                watch_status=watch_status,
                pool_entry_type=pool_entry_type,
                candidate_source=str(md.get("candidate_source") or "strong_watch_pool"),
            ):
                continue
            watch_score = BuildPostMarketRecapJob._d(md.get("watch_score"))
            support_score = BuildPostMarketRecapJob._d(md.get("support_score"))
            strong_grade = str(md.get("strong_grade") or "") or BuildPostMarketRecapJob._grade_from_watch_score(watch_score)
            role_tags = dict(md.get("role_tags") or {})
            for key in (
                "final_cycle_state",
                "transition_type",
                "transition_confidence",
                "trigger_flags",
            ):
                if key in md and key not in role_tags:
                    role_tags[key] = md[key]
            if "final_mainline_alive" not in role_tags:
                final_state = str(role_tags.get("final_cycle_state") or "")
                role_tags["final_mainline_alive"] = final_state not in {"fade_watch", "fade_confirmed", ""}
            watch_age_days = int(md.get("watch_age_days") or len({getattr(r, "trade_date", None) for r in rows if getattr(r, "trade_date", None)}) or 1)
            records.append(
                StrongWatchRecord(
                    stock_id=stock_id,
                    stock_name=str(getattr(latest, "stock_name", "") or ""),
                    subject_key=str(getattr(latest, "subject_key", "") or ""),
                    subject_name=str(getattr(latest, "subject_name", "") or ""),
                    pool_rank=getattr(latest, "pool_rank", None),
                    watch_score=watch_score,
                    strong_grade=strong_grade,
                    support_type=str(md.get("support_type") or ""),
                    support_level=BuildPostMarketRecapJob._d(md.get("support_level")),
                    support_score=support_score,
                    role_tags=role_tags,
                    watch_status=watch_status,
                    watch_age_days=watch_age_days,
                    weak_days=int(md.get("weak_days") or 0),
                    mainline_context_score=BuildPostMarketRecapJob._d(md.get("mainline_context_score")),
                    strong_gene_score=BuildPostMarketRecapJob._d(md.get("strong_gene_score")),
                    weakness_tolerance_score=BuildPostMarketRecapJob._d(md.get("weakness_tolerance_score")),
                    prior7_limitup_days=int(md.get("prior7_limitup_days") or 0),
                    prior7_strong_days=int(md.get("prior7_strong_days") or 0),
                    prior7_best_watch_score=BuildPostMarketRecapJob._d(md.get("prior7_best_watch_score")),
                    prior7_peak_rank=int(md.get("prior7_peak_rank") or 99),
                    admission_status=pool_entry_type if pool_entry_type in {"formal", "observe_only"} else "formal",
                )
            )
        return records

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        lookback_days: int = 8,
    ) -> BuildResult:
        job_key = f"build_post_market_recap:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_post_market_recap",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
                batch_id=batch_id,
                trace_id=trace_id,
                warnings=["idempotency_key_already_completed"],
                metrics={"job_key": job_key},
            )

        # ═══ Layer C: 强势股观察池 — 旧链 StrongStockTrackingService 逻辑的新架构实现 ═══
        # Step 1: 种子查询（Gateways → 等价旧链 _fetch_seed_rows SQL）→ 30-80 只
        seed_rows_raw = await self._read_port.get_strong_watch_seed_rows(trade_date, lookback_days=lookback_days)
        seed_candidates = self._tracking_service.build_seed_candidates(seed_rows_raw)

        # Step 2: 已有池 refresh（Gateways → 等价旧链 _fetch_refresh_watch_pool）
        refresh_rows_raw = await self._read_port.get_strong_watch_refresh_rows(trade_date)

        # Step 3: 收集所有需评分的 stock_ids 和 subject_keys
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

        # ── Step 3.5: Layer A/B 前置（新链自闭环）──
        # 执行顺序: Cycle → Identity → MainlineState
        if self._cycle_judgement_job is not None:
            await self._cycle_judgement_job.execute(
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
            )
        if self._identity_job is not None:
            await self._identity_job.execute(
                trade_date=trade_date,
                snapshot_version="recap_identity.v1",
                batch_id=batch_id,
                trace_id=trace_id,
            )
        if self._mainline_state_job is not None:
            await self._mainline_state_job.execute(
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
            )

        # Step 4: 预取评分所需的外部数据
        identities_raw = await self._read_port.get_mainline_identity_by_subject_keys(
            subject_keys=all_subject_keys, trade_date=trade_date,
        )
        cycles_raw = await self._read_port.get_mainline_cycle_by_subject_keys(
            subject_keys=all_subject_keys, trade_date=trade_date,
        )
        evidence_raw = await self._read_port.get_subject_cycle_evidence_daily(
            trade_date, subject_keys=all_subject_keys,
        )
        board_stats_raw = await self._read_port.get_subject_board_stats(trade_date)
        positions_raw = await self._read_port.get_stock_position_judgement(trade_date, all_stock_ids)
        patterns_raw = await self._read_port.get_stock_pattern_judgement(trade_date, all_stock_ids)
        bars_raw = await self._read_port.get_stock_daily_bars(trade_date, all_stock_ids)
        # ── 前一交易日数据（等价旧链 prev_day_pct_chg / prev_day_limit_up 来源）──
        prev_trade_date = trade_date
        cal = await self._read_port.get_trade_calendar(trade_date)
        if cal is not None:
            prev_td = cal.prev_trade_date if hasattr(cal, "prev_trade_date") else (cal.get("prev_trade_date") if isinstance(cal, dict) else None)
            if prev_td is not None:
                if isinstance(prev_td, str):
                    prev_td = date.fromisoformat(prev_td)
                prev_trade_date = prev_td
        prev_day_bars_raw = await self._read_port.get_stock_daily_bars(prev_trade_date, all_stock_ids)
        prior_rows_raw = await self._read_port.get_prior_stock_daily_snapshots(
            trade_date=trade_date, lookback_days=lookback_days, stock_ids=all_stock_ids,
        )
        history_start = trade_date - timedelta(days=90)
        history_bars_raw = await self._read_port.get_stock_daily_bars_range(
            start_date=history_start, end_date=trade_date, stock_ids=all_stock_ids,
        )

        # Step 5: 转换为 Domain DTOs
        bars = [self._to_stock_bar(row, trade_date) for row in bars_raw]
        prev_day_bars = [self._to_stock_bar(row, prev_trade_date) for row in prev_day_bars_raw]
        prior_rows = [self._to_prior_row(row, trade_date) for row in prior_rows_raw]
        history_bars = [self._to_stock_bar(row, history_start) for row in history_bars_raw]

        identities = [self._to_identity(row) for row in identities_raw]
        cycles = [self._to_cycle(row, trade_date) for row in cycles_raw]
        identities_by_subject = {x.subject_key: x for x in identities}
        cycles_by_subject = {x.subject_key: x for x in cycles}

        evidence_by_subject: dict[str, dict[str, Any]] = {
            str(row.get("subject_key") or ""): dict(row) for row in evidence_raw
        }
        board_by_subject: dict[str, dict[str, Any]] = {
            str(row.get("subject_key") or ""): dict(row) for row in board_stats_raw
        }
        pos_by_stock: dict[str, dict[str, Any]] = {
            self._normalize_stock_id(str(row.get("stock_id") or "")): dict(row)
            for row in positions_raw
        }
        pattern_by_stock: dict[str, dict[str, Any]] = {
            self._normalize_stock_id(str(row.get("stock_id") or "")): dict(row)
            for row in patterns_raw
        }

        # Step 6: Domain 层评分（等价旧链 _score_watch_row × N）
        support_scorer = KlineSupportScorer()
        bars_by_stock = {b.stock_id: b for b in bars}
        prev_day_bars_by_stock = {b.stock_id: b for b in prev_day_bars}
        prior_by_stock: dict[str, list[PriorSnapshotDTO]] = {}
        for pr in prior_rows:
            prior_by_stock.setdefault(pr.stock_id, []).append(pr)
        history_bars_by_stock: dict[str, list[StockBarDTO]] = {}
        for hb in history_bars:
            history_bars_by_stock.setdefault(hb.stock_id, []).append(hb)

        watch_pool_results: list[WatchScoreResult] = []

        def _score_all(candidates: list, current_flag_map: dict[str, int] | None = None):
            for candidate in candidates:
                stock_id = candidate.stock_id
                flag_today = (current_flag_map or {}).get(stock_id, candidate.current_flag_today)

                # 构建周期快照
                cyc = cycles_by_subject.get(candidate.subject_key)
                cycle_snap = CycleSnapshot(
                    final_cycle_state=str(getattr(cyc, "final_cycle_state", "") or ""),
                    effective_mainline_alive=bool(
                        (identities_by_subject.get(candidate.subject_key) and
                         getattr(identities_by_subject[candidate.subject_key], "is_main_theme", False) and
                         getattr(identities_by_subject[candidate.subject_key], "identity_status", "") == "confirmed" and
                         getattr(cyc, "final_cycle_state", "") != "fade_confirmed")
                        if cyc else candidate.labels.get("board_effect_confirmed", False)
                    ),
                    fade_watch=bool(getattr(cyc, "fade_watch", False)) if cyc else False,
                    fade_confirmed=bool(getattr(cyc, "fade_confirmed", False)) if cyc else False,
                    mainline_strength_score=float(getattr(cyc, "mainline_strength_score", 0) or 0) if cyc else 0.0,
                    event_continuity_score=float(
                        (evidence_by_subject.get(candidate.subject_key, {})).get("event_continuity_score", 0) or 0
                    ),
                )

                # 构建板块快照
                bd = board_by_subject.get(candidate.subject_key, {})
                board_snap = BoardSnapshot(
                    subject_limit_up_count=int(bd.get("subject_limit_up_count") or 0),
                    subject_strong_count=int(bd.get("subject_strong_count") or 0),
                )

                # 构建位置快照
                pos_raw = pos_by_stock.get(stock_id, {})
                pos_snap = PositionSnapshot(
                    position_label=str(pos_raw.get("position_label") or ""),
                    ma_alignment_status=str(pos_raw.get("ma_alignment_status") or ""),
                    trend_strength_score=float(pos_raw.get("trend_strength_score") or 0.0),
                )

                # 构建形态快照
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

                # 计算支撑位（current_bar 可能为空，使用空 bar 兜底）
                bar = bars_by_stock.get(stock_id) or StockBarDTO(
                    trade_date=trade_date, stock_id=stock_id, stock_name="",
                    open_price=Decimal("0"), high_price=Decimal("0"),
                    low_price=Decimal("0"), close_price=Decimal("0"),
                    pre_close=Decimal("0"), pct_chg=Decimal("0"),
                    volume=Decimal("0"), amount=Decimal("0"),
                    limit_up_price=Decimal("0"), limit_down_price=Decimal("0"),
                )
                stock_prior = prior_by_stock.get(stock_id, [])
                stock_history = history_bars_by_stock.get(stock_id, [])
                support_result = support_scorer.score(
                    stock_id=stock_id,
                    current_bar=bar,
                    prior_rows=stock_prior,
                    history_bars=stock_history,
                )

                result = self._tracking_service.score_watch_row(
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

        # 评分种子 + refresh 行
        _score_all(seed_candidates)
        for row in refresh_rows_raw:
            sid = self._normalize_stock_id(str(row.get("stock_id") or ""))
            if not sid or sid in {s.stock_id for s in seed_candidates}:
                continue
            labels_json = row.get("labels_json")
            if isinstance(labels_json, str):
                try:
                    labels_json = json.loads(labels_json)
                except Exception:
                    labels_json = {}
            elif not isinstance(labels_json, dict):
                labels_json = {}
            # 解析 evidence_json（可能是 JSON 字符串，与 labels_json 同样的处理）
            ev_raw = row.get("evidence_json") or {}
            if isinstance(ev_raw, str):
                try:
                    ev_raw = json.loads(ev_raw)
                except Exception:
                    ev_raw = {}
            elif not isinstance(ev_raw, dict):
                ev_raw = {}
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
                evidence=ev_raw,
            )
            _score_all([refresh_candidate], {sid: int(row.get("current_flag_today") or 0)})

        # Step 7: 构建 D1 候选 — 等价旧链 _fetch_watch_candidate_inputs + _to_candidate + _apply_watch_context
        d1_input_rows = await self._read_port.get_w2s_candidate_inputs(trade_date)
        d1_candidates_for_pool: list[dict[str, Any]] = []
        _d1_total_in = len(d1_input_rows)
        _d1_pass = 0
        _d1_fail_pct = 0
        _d1_fail_history = 0
        _d1_fail_gene = 0
        _d1_fail_strong = 0
        _d1_fail_support = 0

        for row in d1_input_rows:
            # ── 旧链 _to_candidate 硬约束（使用旧链同名字段）──
            pct_chg = float(row.get("pct_chg") or 0)
            limit_up = bool(row.get("limit_up") or False)
            is_leader = bool(row.get("is_leader") or False)
            rank_order = int(row.get("rank_order") or 999)
            recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
            prior7_limitup_days = int(row.get("prior7_limitup_days") or 0)
            prior7_strong_days = int(row.get("prior7_strong_days") or 0)
            prev_day_pct = float(row.get("prev_day_pct_chg") or 0.0)
            prev_day_limit_up = bool(row.get("prev_day_limit_up") or False)
            fade_watch = bool(row.get("fade_watch") or False)
            fade_confirmed = bool(row.get("fade_confirmed") or False)
            mainline_strength_score = float(row.get("mainline_strength_score") or 0.0)
            watch_score = float(row.get("watch_score") or 0.0)
            watch_pool_entry_type = str(row.get("watch_pool_entry_type") or "observe_only")
            watch_labels = row.get("watch_labels_json") or {}
            if isinstance(watch_labels, str):
                watch_labels = json.loads(watch_labels) if watch_labels else {}
            strong_grade = str(watch_labels.get("strong_grade") or "").upper()
            support_type = str(watch_labels.get("support_type") or "")
            support_strength = float(watch_labels.get("support_score") or 0)

            # 1) pct_chg >= 0 或 limit_up → 必须弱势日
            if pct_chg >= 0.0 or limit_up:
                _d1_fail_pct += 1; continue
            # 2) 跌幅不足 -1.0%
            if pct_chg > -1.0:
                _d1_fail_pct += 1; continue
            # 3) strong_history
            strong_history = (is_leader or prev_day_limit_up or recent_limit_up_count >= 1 or rank_order <= 5)
            if not strong_history:
                _d1_fail_history += 1; continue
            # 4) has_limitup_gene
            if prior7_limitup_days < 1:
                _d1_fail_gene += 1; continue
            # 5) recent_strong_history
            if prior7_strong_days < 1:
                _d1_fail_strong += 1; continue
            # 6) support_available
            if support_type in {"", "none"} or support_strength < 45.0:
                _d1_fail_support += 1; continue
            _d1_pass += 1

            # ── 旧链 _classify_weak_type ──
            if prev_day_limit_up and pct_chg < 0:
                weak_type = "bad_limit_up"
                weak_intensity = min(100.0, abs(pct_chg) * 12.0 + 20.0)
            elif pct_chg <= -5.0:
                weak_type = "big_negative_line"
                weak_intensity = min(100.0, abs(pct_chg) * 10.0)
            elif -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
                weak_type = "upper_shadow"
                weak_intensity = 55.0
            elif pct_chg <= -1.0:
                weak_type = "high_open_low_close"
                weak_intensity = min(100.0, abs(pct_chg) * 8.0 + 10.0)
            else:
                weak_type = "fake_break"
                weak_intensity = 40.0

            # ── 旧链 _day_weak_score / _prev_day_weak_score ──
            if pct_chg < -4.0: day_weak_score = 20.0
            elif pct_chg < -2.0: day_weak_score = 16.0
            elif pct_chg < -1.0: day_weak_score = 10.0
            else: day_weak_score = 6.0

            if prev_day_pct < -3.0: prev_day_weak_score = 10.0
            elif prev_day_pct < -1.5: prev_day_weak_score = 8.0
            elif prev_day_pct < 0: prev_day_weak_score = 5.0
            else: prev_day_weak_score = 0.0

            # ── 旧链 _candidate_score ──
            candidate_score = 45.0
            if is_leader: candidate_score += 18.0
            if limit_up: candidate_score += 10.0
            candidate_score += min(recent_limit_up_count * 4.0, 12.0)
            if rank_order <= 3: candidate_score += 8.0
            candidate_score += min(weak_intensity * 0.08, 8.0)
            candidate_score += min(support_strength * 0.1, 9.0)
            candidate_score += day_weak_score + prev_day_weak_score
            candidate_score += min(mainline_strength_score * 0.08, 8.0)
            if fade_watch:
                if mainline_strength_score >= 75.0: candidate_score -= 4.0
                elif mainline_strength_score >= 60.0: candidate_score -= 8.0
                else: candidate_score -= 12.0
            # ── 旧链 classify_pool_entry（严格复刻，含 prev_day_weak>=2）──
            strong_background = (is_leader or recent_limit_up_count >= 2 or rank_order <= 3)
            d1_pool_entry = "reject"
            if support_strength >= 45 and strong_background and day_weak_score >= 4 and prev_day_weak_score >= 2:
                d1_pool_entry = "formal"
            elif support_strength >= 60 and day_weak_score >= 3 and prev_day_weak_score >= 2:
                d1_pool_entry = "observe_only"
            if d1_pool_entry == "reject":
                continue

            candidate_score = max(0.0, min(candidate_score, 100.0))

            # ── _classify_candidate_type ──
            if is_leader and recent_limit_up_count >= 3:
                candidate_type = "dragon_repair"
            elif is_leader:
                candidate_type = "subdragon_repair"
            elif weak_type == "bad_limit_up":
                candidate_type = "bad_limit_repair"
            elif weak_type == "upper_shadow":
                candidate_type = "upper_shadow_repair"
            elif recent_limit_up_count >= 1:
                candidate_type = "strong_trend_repair"
            else:
                candidate_type = "generic_repair"

            # ── 用 D 层 classify_pool_entry 结果（非 C 层 pool_entry_type）──
            watch_pool_entry_type = d1_pool_entry

            # ── _apply_watch_context（旧链精确复刻）──
            if watch_pool_entry_type == "observe_only":
                candidate_score = min(candidate_score, 69.0)
            if watch_pool_entry_type == "formal":
                candidate_score = min(100.0, max(candidate_score, 70.0))
            if strong_grade == "B":
                candidate_score = min(69.0, candidate_score)
            elif strong_grade in {"S", "A"}:
                candidate_score = min(100.0, max(candidate_score, 72.0))
            score_boost = min(max(watch_score * 0.08, 0.0), 8.0)
            if strong_grade in {"S", "A"}:
                score_boost = min(12.0, score_boost + 3.0)
            candidate_score = round(min(100.0, candidate_score + score_boost), 2)

            d1_candidates_for_pool.append({
                "trade_date": trade_date,
                "next_trade_date": trade_date,
                "stock_id": str(row.get("stock_id") or ""),
                "stock_name": str(row.get("stock_name") or ""),
                "subject_key": str(row.get("subject_key") or ""),
                "theme_name": str(row.get("theme_name") or ""),
                "candidate_score": str(candidate_score),
                "candidate_type": candidate_type,
                "rule_version": "weak_to_strong_candidate.v2",
                "weak_type": weak_type,
                "weak_intensity": str(weak_intensity),
                "is_dragon_head": is_leader,
                "dragon_head_level": "dragon" if is_leader else "",
                "prev_limit_up_count": recent_limit_up_count,
                "max_consecutive_limit_up_days": 0,
                "support_type": support_type,
                "support_level": str(row.get("support_level") or "0"),
                "support_strength": str(support_strength),
                "expected_open_low": "0",
                "expected_open_high": "0",
                "expected_auction_pattern": "",
                "need_last_minute_grab": False,
                "need_plate_follow": False,
                "evidence_json": json.dumps({
                    "source": "strong_watch_pool",
                    "pct_chg": str(pct_chg),
                    "prev_day_pct": str(prev_day_pct),
                    "weak_type": weak_type,
                    "support_type": support_type,
                    "support_strength": str(support_strength),
                }),
                "pool_entry_type": watch_pool_entry_type,
                "cycle_state": str(row.get("final_cycle_state") or ""),
                "mainline_strength_score": str(mainline_strength_score),
                "fade_watch": fade_watch,
                "fade_confirmed": fade_confirmed,
            })

        # ── Step 7b: 持久池写入（等价旧链 _upsert_watch_pool_seed + _update_watch_pool_row）──
        pool_write_rows: list[dict[str, Any]] = []
        for result in watch_pool_results:
            if not result.stock_id:
                continue
            pool_write_rows.append({
                "trade_date": trade_date,
                "stock_id": result.stock_id,
                "stock_name": result.stock_name,
                "subject_key": result.subject_key,
                "theme_name": result.theme_name,
                "watch_window_days": 1,  # 初始值，后续由 recompute_strong_watch_window_days 修正
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
            })
        pool_written = await self._write_port.upsert_strong_watch_pool_rows(pool_write_rows)

        # ── Step 7b.5: 重算 watch_window_days（等价旧链 _recompute_watch_window_days）──
        all_written_ids = [str(r["stock_id"]) for r in pool_write_rows if r.get("stock_id")]
        if all_written_ids:
            await self._write_port.recompute_strong_watch_window_days(all_written_ids)

        # ── Step 7c: 旧链等价 promote（DB UPDATE candidate_promoted=TRUE）──
        formal_ids = {r.stock_id for r in watch_pool_results
                      if r.watch_status in {"active", "weakening"}
                      and r.pool_entry_type in {"formal", "observe_only"}
                      and not r.fade_confirmed}
        promote_count = await self._write_port.promote_strong_watch_candidates(trade_date)

        # ── Step 7d: 旧链等价 prune（DB UPDATE removed/reject）──
        prune_count = await self._write_port.prune_strong_watch_pool(trade_date)

        # ── Step 7e: 旧链等价 history snapshot（写入 strong_stock_watch_history）──
        history_rows = [
            {
                "trade_date": trade_date,
                "stock_id": r.stock_id,
                "stock_name": r.stock_name,
                "subject_key": r.subject_key,
                "theme_name": r.theme_name,
                "watch_status": r.watch_status,
                "watch_score": str(r.watch_score),
                "watch_priority": str(r.watch_priority),
                "pool_entry_type": r.pool_entry_type,
                "relay_role": r.relay_role,
                "cycle_state": r.cycle_state,
                "mainline_strength_score": str(r.mainline_strength_score),
                "fade_watch": r.fade_watch,
                "fade_confirmed": r.fade_confirmed,
                "promoted_to_candidate": r.stock_id in formal_ids,
                "strong_grade": r.strong_grade,
                "removed_reason": r.removed_reason or "",
                "prune_mode": "immediate" if r.watch_status == "removed" else None,
                "prune_reason_code": r.removed_reason or "",
                "kept_because": None,
                "watch_window_days": 1,  # 初始值，后续由 recompute_strong_watch_window_days 修正
                "support_type": r.support_type,
                "support_level": str(r.support_level or "0"),
                "support_score": str(r.support_score),
                "labels_json": r.labels,
                "evidence_json": r.evidence,
            }
            for r in watch_pool_results if r.stock_id
        ]
        history_written = await self._write_port.upsert_strong_watch_history_rows(history_rows)

        # 构建 recap_doc 所需元数据
        pool_rows: list[Any] = []  # 保留兼容性
        stock_ids = all_stock_ids
        subject_keys = all_subject_keys
        strong_watch_rows: list[Any] = []
        strong_watch_history: list[Any] = history_rows if history_written else []
        promoted_pool_rows: list[Any] = d1_input_rows
        shadow_summary: dict[str, Any] = {}
        legacy_watch_input_count = 0
        strong_watch_pool_written = pool_written
        strong_watch_promote_count = promote_count
        strong_watch_prune_count = prune_count
        strong_watch_history_written = history_written
        layer_c_input_mode = "seed_query"
        layer_c_shadow_enabled = False
        layer_a_identity_source = "theme_mainline_identity_registry"
        layer_b_cycle_source = "theme_cycle_judgement_v2"
        layer_a_identity_hit_count = len(identities_by_subject)
        layer_b_cycle_hit_count = len(cycles_by_subject)
        input_fingerprint = "v2_seed_query"
        # ── 旧链等价 D1 候选：排序 + top 10 + 写入 weak_to_strong_candidate_pool ──
        # ── 去重：同一 stock_id 只保留最高分 ──
        _dedup: dict[str, dict[str, Any]] = {}
        for c in d1_candidates_for_pool:
            sid = str(c.get("stock_id") or "")
            if sid not in _dedup or float(c.get("candidate_score") or 0) > float(_dedup[sid].get("candidate_score") or 0):
                _dedup[sid] = c
        d1_candidates_for_pool = sorted(_dedup.values(), key=lambda x: float(x.get("candidate_score") or 0), reverse=True)
        d1_candidates_for_pool = d1_candidates_for_pool[:10]  # HARD_MAX_CANDIDATES = 10
        d1_written = await self._write_port.upsert_weak_to_strong_candidate_pool_rows(d1_candidates_for_pool) if d1_candidates_for_pool else 0

        # 构建兼容 recap_doc 的 candidates 列表
        candidates = [
            {
                "stock_id": c["stock_id"],
                "stock_name": c["stock_name"],
                "subject_key": c["subject_key"],
                "subject_name": c["theme_name"],
                "candidate_score": c["candidate_score"],
                "candidate_level": c["pool_entry_type"],
                "candidate_type": c["candidate_type"],
                "transition_type": c["weak_type"],
                "transition_confidence": "50",
                "trigger_flags": [],
                "evidence_rules": [],
                "support_type": c["support_type"],
            }
            for c in d1_candidates_for_pool
        ]
        formal_candidates = [c for c in candidates if str(c.get("candidate_level", "")).lower() in {"formal", "s", "a", "b"}]
        observe_candidates = [c for c in candidates if str(c.get("candidate_level", "")).lower() == "observe_only"]
        candidate_service_observe_candidates = observe_candidates

        recap_doc = {
            "trade_date": trade_date.isoformat(),
            "snapshot_version": snapshot_version,
            "identity_gate_mode": str(os.getenv("SPS_IDENTITY_GATE_MODE", "asof")).strip().lower(),
            "candidate_source": "strong_watch_pool",
            "layer_c_input_mode": layer_c_input_mode,
            "layer_c_shadow_enabled": layer_c_shadow_enabled,
            "legacy_watch_input_count": legacy_watch_input_count,
            "strong_watch_input_count": len(d1_input_rows),
            "strong_watch_input_7d_count": len(d1_input_rows),
            "strong_watch_promoted_count": len(promoted_pool_rows),
            "strong_watch_history_count": len(strong_watch_history),
            "strong_watch_pool_written": strong_watch_pool_written,
            "strong_watch_promote_count": strong_watch_promote_count,
            "strong_watch_prune_count": strong_watch_prune_count,
            "strong_watch_history_written": strong_watch_history_written,
            "strong_watch_shadow_summary": shadow_summary,
            "shadow_layer_c_formal_count": int(shadow_summary.get("admission_formal_count") or 0),
            "shadow_layer_c_observe_count": int(shadow_summary.get("admission_observe_count") or 0),
            "shadow_layer_c_reject_count": int(shadow_summary.get("admission_reject_count") or 0),
            "shadow_layer_c_pass_4of3_fail_count": int(shadow_summary.get("admission_pass_4of3_fail_count") or 0),
            "shadow_layer_c_hard_reject_count": int(shadow_summary.get("admission_hard_reject_count") or 0),
            "layer_a_identity_source": layer_a_identity_source,
            "layer_b_cycle_source": layer_b_cycle_source,
            "layer_a_identity_hit_count": layer_a_identity_hit_count,
            "layer_b_cycle_hit_count": layer_b_cycle_hit_count,
            "layer_ab_subject_key_count": len(subject_keys),
            "input_fingerprint": input_fingerprint,
            "strong_watch_history": [
                {
                    "stock_id": (row.get("stock_id") if isinstance(row, dict) else getattr(row, "stock_id", "")),
                    "subject_key": (row.get("subject_key") if isinstance(row, dict) else getattr(row, "subject_key", "")),
                    "watch_status": (row.get("watch_status") if isinstance(row, dict) else getattr(row, "watch_status", "")),
                    "strong_grade": str(row.get("strong_grade", "") if isinstance(row, dict) else getattr(row, "strong_grade", "")),
                    "watch_score": str(row.get("watch_score", 0) if isinstance(row, dict) else getattr(row, "watch_score", 0)),
                    "support_score": str(row.get("support_score", "0") if isinstance(row, dict) else getattr(row, "support_score", "0")),
                    "support_type": (row.get("support_type") if isinstance(row, dict) else getattr(row, "support_type", "")),
                    "final_cycle_state": "",
                    "transition_type": "",
                    "transition_confidence": "0",
                    "trigger_flags": [],
                    "prune_mode": None,
                    "prune_reason_code": None,
                    "removed_reason": (row.get("removed_reason") if isinstance(row, dict) else getattr(row, "removed_reason", None)),
                    "kept_because": None,
                }
                for row in strong_watch_history[:100]
            ],
            # Primary count follows the actual candidate list, with formal/observe split preserved separately.
            "candidate_count": len(candidates),
            "candidate_count_total": len(candidates),
            "candidate_count_all": len(candidates),
            "candidate_count_formal": len(formal_candidates),
            "candidate_count_observe": len(observe_candidates),
            "observe_candidates_count": len(candidate_service_observe_candidates),
            "top_candidates_scope": "formal_plus_observe_ranked",
            "formal_top_candidates": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "candidate_score": str(c["candidate_score"]),
                    "support_type": c.get("support_type", ""),
                }
                for c in formal_candidates[:15]
            ],
            "observe_candidates": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "subject_name": c["subject_name"],
                    "candidate_score": str(c["candidate_score"]),
                    "candidate_level": c["candidate_level"],
                    "support_type": c.get("support_type", ""),
                    "support_score": str(c.get("support_score", "0")),
                    "gap_hit": c.get("gap_hit", False),
                    "gap_hit_mode": c.get("gap_hit_mode", "miss"),
                    "evidence_rules": c.get("evidence_rules", [])[:30],
                }
                for c in candidate_service_observe_candidates[:20]
            ],
            "candidate_diagnostics": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "subject_name": c["subject_name"],
                    "candidate_score": str(c["candidate_score"]),
                    "candidate_level": c["candidate_level"],
                    "support_type": c.get("support_type", ""),
                    "support_score": str(c.get("support_score", "0")),
                    "weakness_valid_score": str(c.get("weakness_valid_score", "0")),
                    "repair_or_takeover_score": str(c.get("repair_or_takeover_score", "0")),
                    "gap_hit": c.get("gap_hit", False),
                    "gap_hit_mode": c.get("gap_hit_mode", "miss"),
                    "candidate_rank": idx,
                }
                for idx, c in enumerate(candidates, start=1)
            ],
            "strong_watch_input_7d_preview": [
                {
                    "stock_id": str(r.get("stock_id", "")),
                    "stock_name": str(r.get("stock_name", "")),
                    "subject_key": str(r.get("subject_key", "")),
                    "subject_name": str(r.get("theme_name", "")),
                    "watch_score": str(r.get("watch_score", "")),
                    "watch_status": str(r.get("watch_status", "")),
                    "pool_entry_type": str(r.get("watch_pool_entry_type", "")),
                    "support_type": "",
                }
                for r in d1_input_rows[:100]
            ],
            "strong_watch_input_7d_stock_ids": sorted(
                {str(r.get("stock_id", "")) for r in d1_input_rows if str(r.get("stock_id", "") or "")}
            ),
            "strong_watch_input_7d_source": (
                "legacy_strong_watch_pool_or_history"
                if layer_c_input_mode == "legacy_watch_pool"
                else "strong_watch_pool_history_single_source"
            ),
            "promoted_pool_stock_ids": sorted(
                {str(r.get("stock_id", "")) for r in promoted_pool_rows if str(r.get("stock_id", "") or "")}
            ),
            "promoted_pool_preview": [
                {
                    "stock_id": str(r.get("stock_id", "")),
                    "stock_name": str(r.get("stock_name", "")),
                    "subject_key": str(r.get("subject_key", "")),
                    "subject_name": str(r.get("theme_name", "")),
                    "pool_rank": None,
                    "watch_status": str(r.get("watch_status", "")),
                    "watch_score": str(r.get("watch_score", "")),
                    "support_type": "",
                    "prior7_limitup_days": int(r.get("prior7_limitup_days") or 0),
                    "recent_limit_up_count": int(r.get("recent_limit_up_count") or 0),
                    "final_cycle_state": str(r.get("final_cycle_state") or ""),
                }
                for r in promoted_pool_rows[:200]
            ],
            "top_candidates": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "subject_name": c["subject_name"],
                    "candidate_score": str(c["candidate_score"]),
                    "candidate_level": c["candidate_level"],
                    "transition_type": str(getattr(c, "transition_type", "") or ""),
                    "transition_confidence": str(getattr(c, "transition_confidence", "0")),
                    "trigger_flags": list(getattr(c, "trigger_flags", []) or []),
                    "evidence_rules": c.get("evidence_rules", []),
                }
                for c in candidates[:30]
            ],
        }

        # Convert Decimal values to float for JSON serialization
        def _serialize(obj):
            if isinstance(obj, dict): return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list): return [_serialize(i) for i in obj]
            from decimal import Decimal
            if isinstance(obj, Decimal): return float(obj)
            return obj

        snapshot = PostMarketRecapSnapshot(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            source_trace_id=trace_id,
            recap_doc=_serialize(recap_doc),
        )

        affected = await self._write_port.upsert_post_market_recap_snapshot(snapshot)
        # history already written in Step 7e above; strong_watch_history_written tracks the count

        if self._cache_port is not None:
            await self._cache_writer.write_value_cache(
                f"sps:post_market_recap:{trade_date}",
                asdict(snapshot),
                ttl_seconds=SnapshotCacheWriter.TTL_24H,
            )
            await self._cache_writer.write_grouped_cache(
                f"sps:strong_watch_history:{trade_date}",
                [
                    {
                        "stock_id": row["stock_id"] if isinstance(row, dict) else row.stock_id,
                        "subject_key": row["subject_key"] if isinstance(row, dict) else row.subject_key,
                        "watch_status": row["watch_status"] if isinstance(row, dict) else row.watch_status,
                        "strong_grade": str(row["strong_grade"]) if isinstance(row, dict) else row.strong_grade,
                        "watch_score": str(row["watch_score"]) if isinstance(row, dict) else str(row.watch_score),
                        "support_score": str(row["support_score"]) if isinstance(row, dict) else str(row.support_score),
                        "support_type": row["support_type"] if isinstance(row, dict) else row.support_type,
                        "prune_mode": row.get("prune_mode") if isinstance(row, dict) else getattr(row, "prune_mode", None),
                        "prune_reason_code": row.get("prune_reason_code") if isinstance(row, dict) else getattr(row, "prune_reason_code", None),
                        "removed_reason": row.get("removed_reason") if isinstance(row, dict) else getattr(row, "removed_reason", None),
                        "kept_because": row.get("kept_because") if isinstance(row, dict) else getattr(row, "kept_because", None),
                    }
                    for row in strong_watch_history[:100]
                ],
                ttl_seconds=SnapshotCacheWriter.TTL_24H,
            )
            await self._cache_writer.write_current_version(
                "sps:post_market_recap",
                trade_date,
                snapshot_version,
            )

        await self._event_port.publish_stock_processing_event(
            EventEnvelope(
                event_id=str(uuid4()),
                event_name="snapshot_built",
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
                producer="stock_processing_service",
                occurred_at=datetime.now(timezone.utc),
                payload_version="v1",
                payload=SnapshotBuiltPayload(
                    domain="post_market",
                    snapshot_version=snapshot_version,
                    object_name="post_market_recap_snapshot",
                    row_count=1,
                    success=True,
                ),
            )
        )

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "candidate_count": len(candidates),
                "strong_watch_history_rows": history_written,
            },
        )

        return BuildResult(
            name="build_post_market_recap",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "strong_watch_input_count": len(d1_input_rows),
                "strong_watch_promoted_count": len(promoted_pool_rows),
                "strong_watch_history_count": len(strong_watch_history),
                "strong_watch_history_written": history_written,
                "strong_watch_shadow_universe_formal_count": int(shadow_summary.get("universe_formal_count") or 0),
                "strong_watch_shadow_universe_observe_count": int(shadow_summary.get("universe_observe_count") or 0),
                "strong_watch_shadow_universe_blocked_count": int(shadow_summary.get("universe_blocked_count") or 0),
                "strong_watch_shadow_admission_formal_count": int(shadow_summary.get("admission_formal_count") or 0),
                "strong_watch_shadow_admission_observe_count": int(shadow_summary.get("admission_observe_count") or 0),
                "strong_watch_shadow_admission_reject_count": int(shadow_summary.get("admission_reject_count") or 0),
                "strong_watch_shadow_admission_pass_4of3_fail_count": int(
                    shadow_summary.get("admission_pass_4of3_fail_count") or 0
                ),
                "strong_watch_shadow_admission_hard_reject_count": int(
                    shadow_summary.get("admission_hard_reject_count") or 0
                ),
                "layer_c_input_mode": layer_c_input_mode,
                "legacy_watch_input_count": legacy_watch_input_count,
                "candidate_count": len(candidates),
                "candidate_count_formal": len(formal_candidates),
                "candidate_count_observe": len(observe_candidates),
                "observe_candidates_count": len(candidate_service_observe_candidates),
            },
            published_events=["snapshot_built"],
            cache_writes=3 if self._cache_port is not None else 0,
        )

    @staticmethod
    def _build_input_fingerprint(
        *,
        trade_date: date,
        bars: list[Any],
        pool_rows: list[Any],
        prior_rows: list[Any],
        history_bars: list[Any],
        subject_keys: list[str],
        stock_ids: list[str],
    ) -> dict[str, Any]:
        payload = {
            "trade_date": trade_date.isoformat(),
            "bars_count": len(bars),
            "pool_rows_count": len(pool_rows),
            "prior_rows_count": len(prior_rows),
            "history_bars_count": len(history_bars),
            "subject_key_count": len(subject_keys),
            "stock_id_count": len(stock_ids),
            "subject_keys_sample": subject_keys[:50],
            "stock_ids_sample": stock_ids[:100],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload["fingerprint_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return payload

    async def _upsert_strong_watch_history(self, strong_watch_history: list[Any]) -> int:
        fn = getattr(self._write_port, "upsert_strong_watch_history_rows", None)
        if not callable(fn):
            return 0
        rows = [
            {
                "trade_date": row.trade_date.isoformat() if hasattr(row.trade_date, "isoformat") else row.trade_date,
                "stock_id": row.stock_id,
                "stock_name": row.stock_name,
                "subject_key": row.subject_key,
                "theme_name": row.theme_name,
                "watch_status": row.watch_status,
                "pool_entry_type": row.pool_entry_type,
                "relay_role": row.relay_role,
                "strong_grade": row.strong_grade,
                "watch_score": str(row.watch_score),
                "watch_priority": str(row.watch_priority),
                "cycle_state": row.cycle_state,
                "mainline_strength_score": str(row.mainline_strength_score),
                "fade_watch": bool(row.fade_watch),
                "fade_confirmed": bool(row.fade_confirmed),
                "promoted_to_candidate": bool(row.promoted_to_candidate),
                "support_score": str(row.support_score),
                "support_type": row.support_type,
                "support_level": str(row.support_level),
                "prune_mode": row.prune_mode,
                "prune_reason_code": row.prune_reason_code,
                "removed_reason": row.removed_reason,
                "kept_because": row.kept_because,
                "labels_json": dict(row.labels_json or {}),
                "evidence_json": dict(row.evidence_json or {}),
            }
            for row in strong_watch_history
        ]
        return int(await fn(rows) or 0)

    @staticmethod
    def _build_d1_input_rows(
        *,
        trade_date: date,
        strong_watch_rows: list[Any],
        promoted_pool_rows: list[Any],
        prior_watch_rows: list[Any],
    ) -> list[Any]:
        by_stock: dict[str, SubjectStockPoolDTO] = {}

        def _is_valid_prior_watch_row(row: Any) -> bool:
            md = getattr(row, "metadata", {}) or {}
            source = str(md.get("candidate_source") or "")
            watch_status = str(md.get("watch_status") or "")
            pool_entry_type = str(md.get("pool_entry_type") or "")
            eligible_for_candidate = md.get("eligible_for_candidate")
            subject_key = str(getattr(row, "subject_key", "") or "")
            stock_id = str(getattr(row, "stock_id", "") or "")
            if not stock_id or not subject_key:
                return False
            if eligible_for_candidate is not None:
                return bool(eligible_for_candidate)
            return StrongStockTrackingService.is_candidate_eligible(
                watch_status=watch_status,
                pool_entry_type=pool_entry_type,
                candidate_source=source,
            )

        for row in strong_watch_rows:
            watch_status = str(getattr(row, "watch_status", ""))
            pool_entry_type = str(getattr(row, "admission_status", "") or getattr(row, "pool_entry_type", ""))
            if not StrongStockTrackingService.is_candidate_eligible(
                watch_status=watch_status,
                pool_entry_type=pool_entry_type,
                candidate_source="strong_watch_pool",
            ):
                continue
            stock_id = str(getattr(row, "stock_id", "") or "")
            subject_key = str(getattr(row, "subject_key", "") or "")
            if not stock_id:
                continue
            if not subject_key:
                continue
            watch_score = BuildPostMarketRecapJob._d(getattr(row, "watch_score", "0"))
            strong_grade = str(getattr(row, "strong_grade", "") or BuildPostMarketRecapJob._grade_from_watch_score(watch_score))
            by_stock[stock_id] = SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key=subject_key,
                subject_name=getattr(row, "subject_name", ""),
                stock_id=stock_id,
                stock_name=getattr(row, "stock_name", ""),
                pool_rank=getattr(row, "pool_rank", None),
                metadata={
                    # D1 入参统一标记为 strong_watch_pool，避免被 source=seed_proxy 等过滤掉。
                    "candidate_source": "strong_watch_pool",
                    "watch_score": str(watch_score),
                    "strong_grade": strong_grade,
                    "support_type": getattr(row, "support_type", ""),
                    "support_level": str(getattr(row, "support_level", "0")),
                    "support_score": str(getattr(row, "support_score", "0")),
                    "support_refs": list(getattr(row, "support_refs", []) or []),
                    "support_count": int(getattr(row, "support_count", 0) or 0),
                    "support_combined_strength": str(getattr(row, "support_combined_strength", "0")),
                    "gap_hit": bool(getattr(row, "gap_hit", False)),
                    "gap_hit_mode": getattr(row, "gap_hit_mode", "miss"),
                    "gap_source": getattr(row, "gap_source", ""),
                    "gap_level": str(getattr(row, "gap_level", "0")),
                    "gap_distance_pct": str(getattr(row, "gap_distance_pct", "999")),
                    "role_tags": dict(getattr(row, "role_tags", {}) or {}),
                    "mainline_context_score": str(getattr(row, "mainline_context_score", "0")),
                    "strong_gene_score": str(getattr(row, "strong_gene_score", "0")),
                    "weakness_tolerance_score": str(getattr(row, "weakness_tolerance_score", "0")),
                    "prior7_limitup_days": int(getattr(row, "prior7_limitup_days", 0) or 0),
                    "prior7_strong_days": int(getattr(row, "prior7_strong_days", 0) or 0),
                    "prior7_best_watch_score": str(getattr(row, "prior7_best_watch_score", "0")),
                    "prior7_peak_rank": int(getattr(row, "prior7_peak_rank", 99) or 99),
                    "watch_status": getattr(row, "watch_status", ""),
                    "pool_entry_type": pool_entry_type,
                    "eligible_for_candidate": True,
                    "final_cycle_state": str((getattr(row, "role_tags", {}) or {}).get("final_cycle_state", "")),
                    "transition_type": str((getattr(row, "role_tags", {}) or {}).get("transition_type", "")),
                    "transition_confidence": str((getattr(row, "role_tags", {}) or {}).get("transition_confidence", "0")),
                    "trigger_flags": list((getattr(row, "role_tags", {}) or {}).get("trigger_flags", []) or []),
                    "kept_because": getattr(row, "kept_because", ""),
                },
            )
        for row in promoted_pool_rows:
            stock_id = str(getattr(row, "stock_id", "") or "")
            subject_key = str(getattr(row, "subject_key", "") or "")
            if not stock_id or not subject_key or stock_id in by_stock:
                continue
            md = dict(getattr(row, "metadata", {}) or {})
            strong_grade = str(md.get("strong_grade") or "")
            if not strong_grade:
                watch_score = BuildPostMarketRecapJob._d(md.get("watch_score"))
                strong_grade = BuildPostMarketRecapJob._grade_from_watch_score(watch_score)
                md["strong_grade"] = strong_grade
            md.setdefault("candidate_source", "strong_watch_pool")
            md.setdefault("watch_status", "active")
            md.setdefault("pool_entry_type", "formal")
            md.setdefault("eligible_for_candidate", True)
            by_stock[stock_id] = SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key=subject_key,
                subject_name=str(getattr(row, "subject_name", "") or ""),
                stock_id=stock_id,
                stock_name=getattr(row, "stock_name", ""),
                pool_rank=getattr(row, "pool_rank", None),
                metadata=md,
            )
        # 再装入近7日历史跟踪池，仅补充当日 refresh/promote 未覆盖的对象。
        for row in prior_watch_rows:
            if not _is_valid_prior_watch_row(row):
                continue
            stock_id = str(getattr(row, "stock_id", "") or "")
            if not stock_id or stock_id in by_stock:
                continue
            by_stock[stock_id] = row
        rows: list[SubjectStockPoolDTO] = []
        rows.extend(by_stock.values())
        return rows

    async def _get_prior_strong_watch_rows(self, *, trade_date: date, lookback_days: int) -> list[Any]:
        fn = getattr(self._read_port, "get_prior_strong_watch_pool_rows", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date=trade_date, lookback_days=lookback_days)
        filtered: list[Any] = []
        for row in list(rows or []):
            row_date = getattr(row, "trade_date", None)
            if row_date is None and isinstance(row, dict):
                row_date = row.get("trade_date")
            # Time-travel guard: candidate window must only consume strictly prior rows.
            if row_date is not None and row_date >= trade_date:
                continue
            filtered.append(row)
        return filtered

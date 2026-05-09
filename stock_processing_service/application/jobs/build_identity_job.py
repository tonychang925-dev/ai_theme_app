from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.domain.services.identity_decider import IdentityDecider, IdentityDecision
from stock_processing_service.domain.services.identity_llm_review_service import (
    IdentityLLMReviewService,
    IdentityLLMReviewVerdict,
)
from stock_processing_service.domain.services.identity_rule_engine import IdentityRuleEngine, IdentityRuleInput
from stock_processing_service.domain.services.mainline_cluster_rules import (
    ClusterDecisionInput,
    MainlineClusterRegistry,
    apply_manual_mainline_overrides,
)
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    IdempotencyPort,
    StockEventPort,
    StockReadPort,
)


class BuildIdentityJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: AlgorithmStateWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        llm_review_service: IdentityLLMReviewService | None = None,
        decider: IdentityDecider | None = None,
        rule_engine: IdentityRuleEngine | None = None,
        cluster_registry: MainlineClusterRegistry | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._llm_review_service = llm_review_service or IdentityLLMReviewService()
        self._decider = decider or IdentityDecider()
        self._rule_engine = rule_engine or IdentityRuleEngine()
        bootstrap_enabled = os.environ.get("IDENTITY_CLUSTER_BOOTSTRAP", "0") in {"1", "true", "yes"}
        self._cluster_registry = cluster_registry or MainlineClusterRegistry(
            bootstrap_enabled=bootstrap_enabled,
        )
        self._manual_override_config_path = os.environ.get(
            "IDENTITY_MANUAL_OVERRIDE_CONFIG", ""
        )
        self._deactivate_fade_days = int(os.environ.get("IDENTITY_DEACTIVATE_FADE_DAYS", "2"))

    @staticmethod
    def _d(value: Any, default: str = "0") -> Decimal:
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _normalize_rows(rows: list[dict[str, Any]]) -> list[Any]:
        """Convert dict rows to SimpleNamespace so attribute access works.
        
        Fills in missing keys that the DB may not return but the Job expects:
        - subject_name: falls back to subject_key (pool rows lack this column)
        - metadata: defaults to {}
        - theme_context_tags: defaults to []
        """
        result: list[Any] = []
        for r in rows:
            if isinstance(r, dict):
                r_filled = dict(r)
                if "subject_name" not in r_filled:
                    r_filled["subject_name"] = r_filled.get("subject_key", "")
                if "metadata" not in r_filled:
                    r_filled["metadata"] = {}
                if "theme_context_tags" not in r_filled:
                    r_filled["theme_context_tags"] = []
                result.append(SimpleNamespace(**r_filled))
            else:
                result.append(r)
        return result

    @classmethod
    def _identity_rule_input_from_row(cls, row: dict[str, Any]) -> IdentityRuleInput:
        return IdentityRuleInput(
            subject_key=str(row.get("subject_key") or ""),
            subject_name=str(row.get("theme_name") or row.get("subject_name") or row.get("subject_key") or ""),
            heat_latest=cls._d(row.get("heat_latest")),
            avg_heat_5d=cls._d(row.get("avg_heat_5d")),
            hot_days_5d=int(row.get("hot_days_5d") or 0),
            active_days_10d=int(row.get("active_days_10d") or 0),
            active_days_20d=int(row.get("active_days_20d") or 0),
            his_pct_chg_30d=list(row.get("his_pct_chg_30d") or []),
            his_pct_chg_latest=cls._d(row.get("his_pct_chg_latest")),
            strong_event_count_7d=int(row.get("strong_event_count_7d") or 0),
            event_count_3d=int(row.get("event_count_3d") or 0),
            event_count_7d=int(row.get("event_count_7d") or 0),
            event_recency_days=int(row.get("event_recency_days") or 99),
            event_strength_score=cls._d(row.get("event_strength_score")),
            event_continuity_score=cls._d(row.get("event_continuity_score")),
            board_stock_count=int(row.get("board_stock_count") or 0),
            limit_up_count=int(row.get("limit_up_count") or 0),
            front_row_strength_score=cls._d(row.get("front_row_strength_score")),
            front_row_alive_ratio=cls._d(row.get("front_row_alive_ratio")),
            above_ma10=bool(row.get("above_ma10") or False),
            above_ma20=bool(row.get("above_ma20") or False),
            theme_support_score=cls._d(row.get("theme_support_score")),
            theme_ret_10d=cls._d(row.get("theme_ret_10d")),
            board_boom_days_5d=int(row.get("board_boom_days_5d") or 0),
            net_inflow_sum_5d=cls._d(row.get("net_inflow_sum_5d")),
            net_inflow_days_5d=int(row.get("net_inflow_days_5d") or 0),
        )


    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
    ) -> BuildResult:
        job_key = f"build_identity:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_identity",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
                batch_id=batch_id,
                trace_id=trace_id,
            )

        # ── Phase 1: 构建 Identity Universe（主线 + 异动 + 新题材）──
        # 不扫全量 600+ subject，只评估：
        #   1. prior confirmed + cycle alive（存续主线）
        #   2. subject_rank_daily 当日强热度（异动题材）
        #   3. 已有 cycle 记录的活跃 subject

        universe_keys: set[str] = set()

        # 1. 当日排名热点（subject_rank_daily）
        try:
            rank_hot = await self._read_port.get_subject_rank_daily(trade_date, limit=50)
            for r in (rank_hot or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk:
                    universe_keys.add(sk)
        except Exception:
            pass

        # 2. 存续主线：prior confirmed + prior cycle alive
        prior_confirmed = set()
        prior_cycle_alive = set()
        try:
            prior_ids = await self._read_port.get_mainline_identity_by_subject_keys([], trade_date)
            for r in (prior_ids or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk and bool(r.get("is_main_theme")) and str(r.get("identity_status") or "") == "confirmed":
                    prior_confirmed.add(sk)
        except Exception:
            pass
        try:
            prior_cycles = await self._read_port.get_mainline_cycle_by_subject_keys([], trade_date)
            for r in (prior_cycles or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk and bool(r.get("final_mainline_alive")):
                    prior_cycle_alive.add(sk)
        except Exception:
            pass
        universe_keys.update(prior_confirmed)
        universe_keys.update(prior_cycle_alive)

        # 3. 如果 universe 太小，补充 subject_stock_pool 中的 leader subjects
        if len(universe_keys) < 20:
            try:
                pool_rows_raw = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
                for row in (pool_rows_raw or []):
                    sk = str(getattr(row, "subject_key", ""))
                    if sk and (getattr(row, "is_leader", False) or getattr(row, "limit_up", False)):
                        universe_keys.add(sk)
            except Exception:
                pass

        subject_keys = sorted(universe_keys)
        if not subject_keys:
            return BuildResult(
                name="build_identity", trade_date=trade_date.isoformat(),
                affected_rows=0, status="ok_no_data",
                batch_id=batch_id, trace_id=trace_id,
            )

        raw_rule_inputs = await self._read_port.get_mainline_identity_rule_inputs(
            trade_date=trade_date, subject_keys=subject_keys,
        ) if subject_keys else []
        rule_inputs_by_subject = {
            str(row.get("subject_key") or ""): dict(row)
            for row in raw_rule_inputs
            if str(row.get("subject_key") or "").strip()
        }

        identity_registry_rows: list[dict[str, Any]] = []
        review_queue_rows: list[dict[str, Any]] = []

        # Step 1: 所有 universe subject 跑 rule engine → 收集 IdentityRuleResult
        rule_results: dict[str, Any] = {}  # subject_key → IdentityRuleResult
        subject_name_map: dict[str, str] = {}
        cluster_inputs: list[ClusterDecisionInput] = []

        for subject_key in subject_keys:
            rule_row = rule_inputs_by_subject.get(subject_key)
            if not rule_row:
                raise RuntimeError(
                    f"Layer A missing rule input: trade_date={trade_date}, subject_key={subject_key}"
                )
            rule_input = self._identity_rule_input_from_row(rule_row)
            subject_name = rule_input.subject_name
            subject_name_map[subject_key] = subject_name
            rule = self._rule_engine.evaluate(rule_input)
            rule_results[subject_key] = rule

            # 构建 cluster 输入（证据从 rule_input 提取）
            cluster_inputs.append(
                ClusterDecisionInput(
                    subject_key=subject_key,
                    theme_name=subject_name,
                    rule_is_main_theme=rule.rule_is_main_theme,
                    evidence={
                        "active_days_10d": int(rule_row.get("active_days_10d") or 0),
                        "limit_up_count": int(rule_row.get("limit_up_count") or 0),
                        "mainline_continuity_score": float(rule.mainline_continuity_score),
                        "event_count_3d": int(rule_row.get("event_count_3d") or 0),
                        "net_inflow_days_5d": int(rule_row.get("net_inflow_days_5d") or 0),
                        "one_day_tour_flag": rule.one_day_tour_flag,
                    },
                )
            )

        # Step 2: 旧链等价 — cluster compensation → bootstrap → manual overrides
        cluster_comp_count = self._cluster_registry.apply_cluster_compensation(cluster_inputs)
        cluster_bootstrap_count = self._cluster_registry.apply_cluster_bootstrap_direct_confirm(
            cluster_inputs
        )
        manual_override_count = apply_manual_mainline_overrides(
            cluster_inputs,
            config_path=self._manual_override_config_path or None,
        ) if self._manual_override_config_path else 0

        # 将 cluster 结果回写到 rule_results 的 rule_is_main_theme
        cluster_by_subject = {ci.subject_key: ci for ci in cluster_inputs}
        for subject_key, rule in rule_results.items():
            ci = cluster_by_subject.get(subject_key)
            if ci and ci.rule_is_main_theme and not rule.rule_is_main_theme:
                # cluster 补偿修改了 rule_is_main_theme，记录原因
                rule.reasons.append(
                    f"cluster_compensation:{ci.evidence.get('cluster_compensation_cluster', 'unknown')}"
                )

        # Step 3: LLM review + decider + upgrade trigger（使用 cluster 修正后的 rule_is_main_theme）

        # ── 预取主线存续继承所需的状态 ──
        # 设计文档 §25.3：已确认主线只受生命周期降级管理（连续 fade_confirmed），
        # 不因市场热度短期波动而降级。
        prior_identity_map: dict[str, bool] = {}
        prior_confirmed_map: dict[str, bool] = {}
        if subject_keys:
            raw_prior = await self._read_port.get_mainline_identity_by_subject_keys(
                subject_keys, trade_date
            )
            for pr in (raw_prior or []):
                sk = str(pr.get("subject_key") or "").strip()
                if sk:
                    prior_identity_map[sk] = bool(pr.get("is_main_theme"))
                    prior_confirmed_map[sk] = (
                        bool(pr.get("is_main_theme"))
                        and str(pr.get("identity_status") or "") == "confirmed"
                    )
        cycle_alive_map: dict[str, bool] = {}
        cycle_fade_map: dict[str, bool] = {}
        if subject_keys:
            raw_cycles = await self._read_port.get_mainline_cycle_by_subject_keys(
                subject_keys, trade_date
            )
            for cy in (raw_cycles or []):
                sk = str(cy.get("subject_key") or "").strip()
                if sk:
                    cycle_alive_map[sk] = bool(cy.get("final_mainline_alive"))
                    cycle_fade_map[sk] = bool(cy.get("fade_confirmed"))

        # ── 预取 upgrade_trigger 所需的 prev_candidate 状态（等价旧链 DB 查询）──
        prev_candidate_map: dict[str, bool] = {}
        for subject_key in subject_keys:
            rule_row = rule_inputs_by_subject.get(subject_key, {})
            ev_raw = rule_row.get("evidence_json")
            if isinstance(ev_raw, str):
                try:
                    import json as _json
                    ev = _json.loads(ev_raw)
                except Exception:
                    ev = {}
            elif isinstance(ev_raw, dict):
                ev = ev_raw
            else:
                ev = {}
            prev_candidate_map[subject_key] = bool(ev.get("upgrade_candidate"))

        for subject_key in subject_keys:
            rule = rule_results[subject_key]
            subject_name = subject_name_map[subject_key]
            ci = cluster_by_subject.get(subject_key)
            # P0-1 FIX: 重新绑定当前 subject 的 rule_row（第一轮循环的变量不能跨subject泄漏）
            rule_row = rule_inputs_by_subject.get(subject_key)

            # ── 主线存续继承（§25.3）──
            # 已确认主线 + 当前未硬退潮 → rule_is_main_theme 强制为 True
            # 后续 LLM + decider 路径正常流转
            inherited = (
                prior_confirmed_map.get(subject_key, False)
                and cycle_alive_map.get(subject_key, False)
                and not cycle_fade_map.get(subject_key, False)
            )

            # 若 cluster bootstrap 已直确认为 confirmed，跳过 LLM
            if ci and ci.identity_status == "confirmed":
                llm_verdict = self._llm_review_service.review_with_rule(
                    composite_score=rule.composite_score,
                    one_day_tour_flag=rule.one_day_tour_flag,
                    logic_ok=rule.logic_ok,
                    market_ok=rule.market_ok,
                    rule_is_main_theme=True,
                )
                decision = self._decider.decide(
                    composite_score=rule.composite_score,
                    llm_verdict="confirmed",
                    one_day_tour_flag=rule.one_day_tour_flag,
                    logic_ok=rule.logic_ok,
                    rule_is_main_theme=True,
                    platform_breakout_flag=rule.platform_breakout_flag,
                )
            else:
                # 正常路径：rule_is_main_theme 可能已被 cluster compensation 修改
                # 若主线存续继承触发，强制 rule_is_main_theme=True
                rule_is_mt = True if inherited else (ci.rule_is_main_theme if ci else rule.rule_is_main_theme)
                llm_verdict = self._llm_review_service.review_with_rule(
                    composite_score=rule.composite_score,
                    one_day_tour_flag=rule.one_day_tour_flag,
                    logic_ok=rule.logic_ok,
                    market_ok=rule.market_ok,
                    rule_is_main_theme=rule_is_mt,
                )
                decision = self._decider.decide(
                    composite_score=rule.composite_score,
                    llm_verdict=llm_verdict.verdict,
                    one_day_tour_flag=rule.one_day_tour_flag,
                    logic_ok=rule.logic_ok,
                    rule_is_main_theme=rule_is_mt,
                    platform_breakout_flag=rule.platform_breakout_flag,
                )

            # ── Upgrade trigger: 6条件检查 + super_strong 路径（旧链 _apply_upgrade_trigger）──
            if decision.identity_status != "confirmed" and rule_row:
                ev = rule_row
                board_ok = bool(
                    int(ev.get("board_boom_days_5d") or 0) >= 2
                    and int(ev.get("limit_up_count") or 0) >= 2
                    and float(ev.get("limit_up_ratio_today") or 0.0) >= 0.02
                )
                event_ok = bool(
                    int(ev.get("event_count_3d") or 0) >= 1
                    and int(ev.get("event_recency_days") or 99) <= 3
                    and int(ev.get("strong_event_count_7d") or 0) >= 1
                )
                flow_ok = bool(
                    int(ev.get("net_inflow_days_5d") or 0) >= 3
                    and float(ev.get("net_inflow_sum_5d") or 0.0) > 0.0
                )
                logic_hard = bool(
                    float(ev.get("novelty_score") or 0.0) >= 55.0
                    or float(rule.logic_score) >= 65.0
                )
                continuity_ok = bool(
                    float(getattr(rule, "mainline_continuity_score", 0)) >= 70.0
                )
                risk_ok = bool(
                    float(getattr(rule, "one_day_tour_risk_score", 100.0)) < 70.0
                )
                base_candidate = bool(
                    board_ok and event_ok and flow_ok and logic_hard and continuity_ok and risk_ok
                )
                if base_candidate:
                    # super_strong 路径：limit_up>=4 AND net_inflow_days>=4 AND continuity>=80 — 豁免2日等待
                    super_strong = bool(
                        int(ev.get("limit_up_count") or 0) >= 4
                        and int(ev.get("net_inflow_days_5d") or 0) >= 4
                        and float(getattr(rule, "mainline_continuity_score", 0)) >= 80.0
                    )
                    # prev_candidate 标志从历史 identity_registry 读取（等价旧链 DB 查询）
                    was_upgrade_candidate = prev_candidate_map.get(subject_key, False)
                    if super_strong or was_upgrade_candidate:
                        decision = IdentityDecision(
                            identity_status="review_pending",
                            final_score=rule.composite_score,
                            reason="upgrade_trigger_review_pending",
                        )
                        # fail-closed: 不允许 LLM 旁路
                        llm_verdict = IdentityLLMReviewVerdict(
                            verdict="review_pending",
                            confidence=Decimal("0.72"),
                            reason="upgrade_trigger",
                        )

            # ── rule_version 溯源：按旧链优先级确定确认来源 ──
            if ci and ci.evidence.get("cluster_bootstrap_direct_confirm"):
                rule_version = "mainline_identity_registry.v8_cluster_bootstrap_direct_confirm"
            elif ci and ci.evidence.get("cluster_compensation_mainline"):
                rule_version = "mainline_identity_registry.v5_cluster_compensation"
            elif decision.identity_status == "review_pending" and decision.reason.startswith("upgrade"):
                rule_version = "mainline_identity_registry.v6_upgrade_trigger"
            elif llm_verdict.verdict == "confirmed":
                rule_version = "mainline_identity_registry.v7_open_source_kline_llm"
            else:
                rule_version = "mainline_identity_registry.v7_open_source_kline"

            identity_row = {
                "trade_date": trade_date.isoformat(),
                "subject_key": subject_key,
                "subject_name": subject_name,
                "logic_score": str(rule.logic_score),
                "market_score": str(rule.market_score),
                "composite_score": str(rule.composite_score),
                "one_day_tour_flag": rule.one_day_tour_flag,
                "continuity_signal": "weak_continuity" if rule.one_day_tour_flag else "normal",
                "logic_ok": rule.logic_ok,
                "market_ok": rule.market_ok,
                "rule_is_main_theme": rule.rule_is_main_theme,
                "is_main_theme": decision.identity_status == "confirmed",
                "rule_reasons": rule.reasons,
                "legacy_composite_score": str(rule.composite_score),
                "llm_verdict": llm_verdict.verdict,
                "llm_reason": llm_verdict.reason,
                "identity_status": decision.identity_status,
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
                "source_trace_id": trace_id,
                "cluster_comp_count": cluster_comp_count,
                "cluster_bootstrap_count": cluster_bootstrap_count,
                "rule_version": rule_version,
                "llm_applied": llm_verdict.verdict != "deterministic",
                "llm_is_main_theme": llm_verdict.verdict == "confirmed",
                "llm_confidence": int(llm_verdict.confidence) if llm_verdict.confidence else 0,
                "llm_reasons": [llm_verdict.reason] if llm_verdict.reason else [],
                "llm_risk_flags": [],
                "llm_model": "",
            }

            if ci and ci.evidence.get("cluster_compensation_mainline"):
                identity_row["rule_is_main_theme"] = True
            if ci and ci.evidence.get("cluster_bootstrap_direct_confirm"):
                identity_row["rule_is_main_theme"] = True

            identity_registry_rows.append(identity_row)

            if identity_row["identity_status"] == "review_pending":
                review_queue_rows.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "subject_key": subject_key,
                        "subject_name": subject_name,
                        "reason": decision.reason,
                        "llm_confidence": str(llm_verdict.confidence),
                        "llm_verdict": identity_row.get("llm_verdict", ""),
                        "rule_is_main_theme": identity_row["rule_is_main_theme"],
                        "rule_reasons": identity_row["rule_reasons"],
                        "snapshot_version": snapshot_version,
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    }
                )

        # 写入保护：backfill 模式允许历史覆盖；正常模式禁止非LLM降级
        allow_historical = os.environ.get("IDENTITY_ALLOW_HISTORICAL_OVERWRITE", "0") in {"1", "true", "yes"}
        allow_unsafe_demotion = os.environ.get("IDENTITY_ALLOW_UNSAFE_DEMOTION", "0") in {"1", "true", "yes"}
        written_registry = await self._write_port.upsert_theme_mainline_identity_registry_rows(
            identity_registry_rows,
            allow_historical_overwrite=allow_historical,
            allow_unsafe_demotion=allow_unsafe_demotion,
        )
        written_review = await self._write_port.upsert_mainline_identity_review_queue_rows(review_queue_rows)

        # ── 生命周期降级：连续 fade_confirmed → inactive ──
        lifecycle_downgrade_count = 0
        if hasattr(self._write_port, "apply_lifecycle_downgrade"):
            lifecycle_downgrade_count = await self._write_port.apply_lifecycle_downgrade(
                trade_date, deactivate_fade_days=2
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
                    domain="identity",
                    snapshot_version=snapshot_version,
                    object_name="theme_mainline_identity_registry",
                    row_count=written_registry,
                    success=True,
                ),
            )
        )
        published_events = ["snapshot_built"]

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "identity_rows": written_registry,
                "review_rows": written_review,
            },
        )

        return BuildResult(
            name="build_identity",
            trade_date=trade_date.isoformat(),
            affected_rows=written_registry + written_review,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "identity_registry_rows": written_registry,
                "identity_review_rows": written_review,
                "subject_count": len(grouped),
                "identity_engine": "identity_rule_engine",
                "dual_run_enabled": False,
            },
            published_events=published_events,
        )

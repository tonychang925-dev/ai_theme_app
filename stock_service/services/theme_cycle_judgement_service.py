from __future__ import annotations

import json
from datetime import date
from typing import Dict, List, Optional, Any, Tuple
import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.services.unified_cycle_scoring_service import CycleEvidenceInput
from stock_service.services.theme_cycle_evidence_builder import ThemeCycleEvidenceBuilder
from stock_service.services.theme_cycle_judgement_service_v2 import ThemeCycleJudgementServiceV2
from stock_service.services.llm_cycle_review_service import (
    CycleReviewInput,
    LlmCycleReviewService,
)


class ThemeCycleJudgementService:
    """主题周期判决服务

    整合 UnifiedCycleScoringService，实现状态机和LLM review
    严格按照用户骨架设计：规则引擎为主，LLM仅做证据归纳+状态复核
    """

    def __init__(self, config=None, *, allow_legacy: bool = False):
        self.config = config or StockServiceConfig()
        self.allow_legacy = bool(allow_legacy)
        self._pool: Optional[asyncpg.Pool] = None
        self.evidence_builder = ThemeCycleEvidenceBuilder(self.config)
        self.v2_service = ThemeCycleJudgementServiceV2()
        self.llm_review_service = LlmCycleReviewService(self.config)

    def _ensure_legacy_enabled(self) -> None:
        if self.allow_legacy:
            return
        raise RuntimeError(
            "ThemeCycleJudgementService (legacy) is disabled by default. "
            "Use theme_cycle_judgement_v2 + mainline_state_tracking pipeline, "
            "or initialize with allow_legacy=True for temporary diagnostics only."
        )

    async def _ensure_pool(self) -> asyncpg.Pool:
        """确保数据库连接池存在"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                database=self.config.postgres_database,
                min_size=1,
                max_size=5
            )
        return self._pool

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None
        await self.evidence_builder.close()
        await self.llm_review_service.close()

    async def judge_theme_cycle(self, trade_date: date,
                               subject_key: str,
                               theme_name: Optional[str] = None) -> Dict[str, Any]:
        """对指定主题进行周期判决

        流程：
        1. 从证据表读取证据
        2. 应用规则引擎（UnifiedCycleScoringService）
        3. 应用受控LLM复核（仅允许指定边界纠偏）
        4. 确定最终判决
        5. 保存到V2表

        返回：判决结果字典
        """
        self._ensure_legacy_enabled()
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 1. 读取证据
            evidence = await self._load_evidence_from_db(conn, trade_date, subject_key)
            if not evidence:
                # 证据缺失时先尝试构建单主题证据，再重读。
                try:
                    await self.evidence_builder.build(trade_date, subject_key, theme_name or subject_key)
                    evidence = await self._load_evidence_from_db(conn, trade_date, subject_key)
                except Exception as e:
                    print(f"❌ 主题 {subject_key} 证据构建失败，跳过判决: {e}")
                    return {}
                if not evidence:
                    print(f"❌ 主题 {subject_key} 无证据数据，跳过判决")
                    return {}

            # 2. 应用规则引擎
            rule_result = await self._apply_rule_engine(evidence)

            # 3. 应用受控LLM复核
            llm_result = await self._apply_llm_review(evidence, rule_result)

            # 4. 确定最终判决
            final_judgement = self._determine_final_judgement(rule_result, llm_result)

            # 5. 保存到V2表
            await self._save_judgement_to_db(
                conn, trade_date, subject_key, theme_name,
                evidence, rule_result, llm_result, final_judgement
            )

            print(f"✅ 主题 {subject_key} 周期判决完成: {final_judgement['final_cycle_state']}")
            return final_judgement

    async def judge_all_themes_for_date(self, trade_date: date) -> List[Dict[str, Any]]:
        """为指定交易日判决主线身份已确认主题。"""
        self._ensure_legacy_enabled()
        # 先构建当日证据，确保周期判定使用最新完整证据层。
        await self.evidence_builder.build_evidence_for_date(trade_date)
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 周期主链仅评估“身份已确认”的题材，避免口径漂移。
            sql = """
            SELECT DISTINCT e.subject_key, e.theme_name
            FROM theme_cycle_evidence_daily e
            JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = e.subject_key
            WHERE e.trade_date = $1::date
              AND COALESCE(mr.is_main_theme, FALSE) = TRUE
              AND COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') = 'confirmed'
            ORDER BY e.subject_key
            """
            rows = await conn.fetch(sql, trade_date)

            judgements = []
            for row in rows:
                subject_key = row["subject_key"]
                theme_name = row["theme_name"]

                try:
                    judgement = await self.judge_theme_cycle(
                        trade_date, subject_key, theme_name
                    )
                    if judgement:
                        judgements.append(judgement)
                except Exception as e:
                    print(f"❌ 主题 {subject_key} 判决失败: {e}")
                    continue

            print(f"📊 总计完成 {len(judgements)} 个主题的周期判决")
            return judgements

    async def _load_evidence_from_db(self, conn: asyncpg.Connection,
                                    trade_date: date,
                                    subject_key: str) -> Optional[CycleEvidenceInput]:
        """从证据表加载证据"""
        sql = """
        SELECT
            trade_date, subject_key, theme_name,
            event_strength_score, event_continuity_score,
            strong_event_count_7d, event_recency_days,
            leader_alive_score, leader_breakdown_flag,
            relay_strength_score, front_row_survival_ratio,
            limit_up_count, limit_down_count, red_ratio,
            big_drop_ratio, front_row_strength_score,
            theme_support_score, break_start_pivot
        FROM theme_cycle_evidence_daily
        WHERE trade_date = $1 AND subject_key = $2
        """
        row = await conn.fetchrow(sql, trade_date, subject_key)

        if not row:
            return None

        # 获取前一日状态
        previous_state = await self._fetch_previous_cycle_state(conn, trade_date, subject_key)

        return CycleEvidenceInput(
            trade_date=trade_date.isoformat(),
            subject_key=subject_key,
            theme_name=row["theme_name"],

            # 事件层
            event_strength_score=float(row["event_strength_score"]),
            event_continuity_score=float(row["event_continuity_score"]),
            strong_event_count_7d=int(row["strong_event_count_7d"]),
            event_recency_days=int(row["event_recency_days"]) if row["event_recency_days"] is not None else None,

            # 龙头/接力层
            leader_alive_score=float(row["leader_alive_score"]),
            leader_breakdown_flag=bool(row["leader_breakdown_flag"]),
            relay_strength_score=float(row["relay_strength_score"]),
            front_row_survival_ratio=float(row["front_row_survival_ratio"]),

            # 板块结构层
            limit_up_count=int(row["limit_up_count"]),
            limit_down_count=int(row["limit_down_count"]),
            red_ratio=float(row["red_ratio"]),
            big_drop_ratio=float(row["big_drop_ratio"]),
            front_row_strength_score=float(row["front_row_strength_score"]),

            # 板块K线技术层
            theme_support_score=float(row["theme_support_score"]),
            break_start_pivot=bool(row["break_start_pivot"]),

            # 前一日状态
            previous_cycle_state=previous_state
        )

    async def _fetch_previous_cycle_state(self, conn: asyncpg.Connection,
                                         trade_date: date,
                                         subject_key: str) -> Optional[str]:
        """获取上一交易日周期状态（非自然日-1）。"""
        sql_v2 = """
        SELECT final_cycle_state
        FROM theme_cycle_judgement_v2
        WHERE subject_key = $1
          AND trade_date < $2::date
        ORDER BY trade_date DESC
        LIMIT 1
        """
        row_v2 = await conn.fetchrow(sql_v2, subject_key, trade_date)
        if row_v2:
            return str(row_v2.get("final_cycle_state"))
        return None

    async def _apply_rule_engine(self, evidence: CycleEvidenceInput) -> Dict[str, Any]:
        """应用规则引擎（ThemeCycleJudgementServiceV2）"""
        evidence_payload = {
            "trade_date": evidence.trade_date,
            "subject_key": evidence.subject_key,
            "theme_name": evidence.theme_name,
            "event_strength_score": evidence.event_strength_score,
            "event_continuity_score": evidence.event_continuity_score,
            "strong_event_count_7d": evidence.strong_event_count_7d,
            "event_recency_days": evidence.event_recency_days,
            "leader_alive_score": evidence.leader_alive_score,
            "leader_breakdown_flag": evidence.leader_breakdown_flag,
            "relay_strength_score": evidence.relay_strength_score,
            "front_row_survival_ratio": evidence.front_row_survival_ratio,
            "limit_up_count": evidence.limit_up_count,
            "limit_down_count": evidence.limit_down_count,
            "red_ratio": evidence.red_ratio,
            "big_drop_ratio": evidence.big_drop_ratio,
            "front_row_strength_score": evidence.front_row_strength_score,
            "theme_support_score": evidence.theme_support_score,
            "break_start_pivot": evidence.break_start_pivot,
            "previous_cycle_state": evidence.previous_cycle_state,
        }
        v2 = self.v2_service.judge(evidence_payload, enable_llm_review=True)
        fade_risk_score = round(
            max(
                0.0,
                min(
                    100.0,
                    (100.0 - v2.mainline_strength_score) * 0.55 + v2.fade_watch_score * 0.45,
                ),
            ),
            3,
        )
        scores = {
            "mainline_strength_score": v2.mainline_strength_score,
            "fade_risk_score": fade_risk_score,
            "fade_watch_score": v2.fade_watch_score,
            "fade_confirmed_score": v2.fade_confirmed_score,
            "divergence_score": v2.divergence_score,
            "repair_score": v2.repair_score,
            "final_cycle_state": v2.final_cycle_state,
            "leader_alive_score": evidence.leader_alive_score,
        }
        return {
            "cycle_state_rule": v2.cycle_state_rule,
            "mainline_alive_rule": v2.mainline_alive_rule,
            "fade_watch": v2.fade_watch,
            "fade_confirmed": v2.fade_confirmed,
            "scores": scores,
            "can_transition_to_repair": v2.score_flags.get("repair_transition_allowed", False),
            "rule_reasons": list(v2.rule_reasons),
            "decision_path": list(v2.decision_path),
            "thresholds": dict(v2.thresholds),
        }

    def _generate_rule_reasons(self, evidence: CycleEvidenceInput,
                              scores: Dict[str, Any]) -> List[str]:
        """生成规则原因"""
        reasons = []

        # 主线强度评分原因
        mainline_score = scores.get("mainline_strength_score", 0)
        if mainline_score >= 75:
            reasons.append("主线强度评分≥75，进入高潮/加速状态")
        elif mainline_score >= 60:
            reasons.append("主线强度评分≥60，进入发酵状态")
        elif mainline_score >= 40:
            reasons.append("主线强度评分≥40，进入分歧/修复状态")
        else:
            reasons.append("主线强度评分<40，进入启动/观察状态")

        # 退潮状态原因
        fade_confirmed_score = scores.get("fade_confirmed_score", 0)
        fade_watch_score = scores.get("fade_watch_score", 0)

        if fade_confirmed_score >= 60:
            reasons.append("退潮确认评分≥60，满足退潮硬证据条件")
        elif fade_watch_score >= 50:
            reasons.append("退潮观察评分≥50，进入退潮观察状态")
        elif fade_watch_score >= 30:
            reasons.append("退潮观察评分≥30，有退潮风险但未确认")

        # 分歧状态原因
        divergence_score = scores.get("divergence_score", 0)
        if divergence_score >= 60:
            reasons.append("分歧评分≥60，进入分歧状态")

        # 修复状态原因
        repair_score = scores.get("repair_score", 0)
        if repair_score >= 65:
            reasons.append("修复评分≥65，具备修复条件")

        # 龙头状态原因
        leader_alive_score = scores.get("leader_alive_score", 0)
        if leader_alive_score >= 70:
            reasons.append("龙头存活评分≥70，龙头强势")
        elif leader_alive_score >= 40:
            reasons.append("龙头存活评分≥40，龙头存活")
        else:
            reasons.append("龙头存活评分<40，龙头走弱")

        return reasons

    async def _apply_llm_review(self, evidence: CycleEvidenceInput,
                               rule_result: Dict[str, Any]) -> Dict[str, Any]:
        """受控LLM复核：仅在指定触发条件下执行，其他场景沿用规则层。"""
        confidence = float(self._calculate_rule_confidence(evidence, rule_result["scores"]))

        if not self._should_trigger_llm_review(evidence, rule_result):
            return {
                "cycle_state_llm": rule_result["cycle_state_rule"],
                "mainline_alive_llm": rule_result["mainline_alive_rule"],
                "support_fade_confirmed": bool(rule_result.get("fade_confirmed", False)),
                "llm_reasons": ["llm_review_not_triggered"],
                "risk_flags": [],
                "confidence": confidence,
                "agreement_with_rule": True,
                "suggested_changes": [],
                "evidence_quality_score": 70.0,
                "llm_applied": False,
                "llm_prompt_version": None,
            }

        review_input = CycleReviewInput(**self._build_llm_review_input(evidence, rule_result))
        review_output = await self.llm_review_service.review_cycle_judgement(review_input)
        return {
            "cycle_state_llm": review_output.cycle_state_llm,
            "mainline_alive_llm": review_output.mainline_alive_llm,
            "support_fade_confirmed": review_output.support_fade_confirmed,
            "llm_reasons": list(review_output.reasons),
            "risk_flags": list(review_output.risk_flags),
            "confidence": float(review_output.confidence),
            "agreement_with_rule": bool(review_output.agreement_with_rule),
            "suggested_changes": list(review_output.suggested_changes),
            "evidence_quality_score": int(review_output.evidence_quality_score),
            "llm_applied": True,
            "llm_prompt_version": self.llm_review_service.PROMPT_VERSION,
        }

    def _should_trigger_llm_review(self, evidence: CycleEvidenceInput, rule_result: Dict[str, Any]) -> bool:
        """受控触发：
        1) 规则层判 fade_watch；
        2) 规则层判 fade_confirmed 且出现“强支撑核心”冲突证据。
        """
        if bool(rule_result.get("fade_watch", False)):
            return True
        if (
            bool(rule_result.get("fade_confirmed", False))
            and float(evidence.leader_alive_score) >= 55.0
            and float(evidence.theme_support_score) >= 70.0
            and float(evidence.event_continuity_score) >= 40.0
        ):
            return True
        return False

    def _build_llm_review_input(self, evidence: CycleEvidenceInput,
                               rule_result: Dict[str, Any]) -> Dict[str, Any]:
        """构建LLM复核输入数据

        将CycleEvidenceInput和规则结果转换为CycleReviewInput
        """
        scores = rule_result["scores"]

        # 构建四层证据字典
        event_layer = {
            "event_strength_score": evidence.event_strength_score,
            "event_continuity_score": evidence.event_continuity_score,
            "strong_event_count_7d": evidence.strong_event_count_7d,
            "event_recency_days": evidence.event_recency_days
        }

        leader_layer = {
            "leader_alive_score": evidence.leader_alive_score,
            "leader_breakdown_flag": evidence.leader_breakdown_flag,
            "relay_strength_score": evidence.relay_strength_score,
            "front_row_survival_ratio": evidence.front_row_survival_ratio
        }

        board_structure_layer = {
            "limit_up_count": evidence.limit_up_count,
            "limit_down_count": evidence.limit_down_count,
            "red_ratio": evidence.red_ratio,
            "big_drop_ratio": evidence.big_drop_ratio,
            "front_row_strength_score": evidence.front_row_strength_score
        }

        theme_kline_layer = {
            "theme_support_score": evidence.theme_support_score,
            "break_start_pivot": evidence.break_start_pivot
        }

        # 从评分中获取fade_risk_score
        fade_risk_score = scores.get("fade_risk_score", 0.0)
        # 计算规则层置信度（基于证据质量）
        confidence_score = self._calculate_rule_confidence(evidence, scores)

        return {
            "trade_date": evidence.trade_date,
            "subject_key": evidence.subject_key,
            "theme_name": evidence.theme_name,
            "cycle_state_rule": rule_result["cycle_state_rule"],
            "mainline_alive_rule": rule_result["mainline_alive_rule"],
            "fade_watch": rule_result.get("fade_watch", False),
            "fade_confirmed": rule_result.get("fade_confirmed", False),
            "mainline_strength_score": scores.get("mainline_strength_score", 0),
            "fade_watch_score": scores.get("fade_watch_score", 0),
            "fade_confirmed_score": scores.get("fade_confirmed_score", 0),
            "divergence_score": scores.get("divergence_score", 0),
            "repair_score": scores.get("repair_score", 0),
            "confidence_score": confidence_score,
            "event_layer": event_layer,
            "leader_layer": leader_layer,
            "board_structure_layer": board_structure_layer,
            "theme_kline_layer": theme_kline_layer,
            "previous_cycle_state": evidence.previous_cycle_state,
            "state_transition_reason": None,
            "evidence_refs": [],
        }

    def _determine_final_judgement(self,
                                  rule_result: Dict[str, Any],
                                  llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """确定最终判决

        规则引擎为主，LLM复核为辅
        如果LLM与规则引擎不一致，需要权衡判断
        """
        rule_cycle_state = rule_result["cycle_state_rule"]
        llm_cycle_state = llm_result["cycle_state_llm"]

        rule_mainline_alive = rule_result["mainline_alive_rule"]
        llm_mainline_alive = llm_result["mainline_alive_llm"]

        # 最终判决逻辑：规则引擎为主，LLM仅在受控边界内可纠偏。
        final_cycle_state = rule_cycle_state
        final_mainline_alive = rule_mainline_alive

        llm_applied = bool(llm_result.get("llm_applied", False))
        allowed_transitions = {
            "fade_watch": {"fade_watch", "divergence", "fade_confirmed"},
            "fade_confirmed": {"fade_confirmed", "fade_watch", "divergence"},
        }
        allowed_states = allowed_transitions.get(rule_cycle_state, {rule_cycle_state})

        if llm_applied and llm_cycle_state in allowed_states and rule_cycle_state != llm_cycle_state:
            llm_reasons = llm_result.get("llm_reasons", [])
            support_fade_confirmed = bool(llm_result.get("support_fade_confirmed", False))
            if llm_cycle_state == "fade_confirmed" and not support_fade_confirmed:
                llm_reasons = list(llm_reasons) + ["llm_override_rejected_no_fade_support"]
                llm_result["llm_reasons"] = llm_reasons
            elif len(llm_reasons) >= 1:
                print(f"  ⚠️ 规则引擎({rule_cycle_state})与LLM({llm_cycle_state})不一致，采纳LLM")
                final_cycle_state = llm_cycle_state
                final_mainline_alive = llm_mainline_alive
        elif llm_applied and llm_cycle_state not in allowed_states:
            llm_reasons = list(llm_result.get("llm_reasons", []))
            llm_reasons.append(f"llm_state_out_of_boundary:{rule_cycle_state}->{llm_cycle_state}")
            llm_result["llm_reasons"] = llm_reasons

        # 确定退潮状态细分
        fade_watch = rule_result["fade_watch"]
        fade_confirmed = rule_result["fade_confirmed"]

        # 如果最终状态不是退潮相关，重置退潮标志
        if not final_cycle_state.startswith("fade"):
            fade_watch = False
            fade_confirmed = False

        # 构建最终判决
        return {
            "final_cycle_state": final_cycle_state,
            "final_mainline_alive": final_mainline_alive,
            "fade_watch": fade_watch,
            "fade_confirmed": fade_confirmed,
            "scores": rule_result["scores"],
            "rule_reasons": rule_result["rule_reasons"],
            "llm_reasons": llm_result["llm_reasons"],
            "state_transition_reason": self._generate_transition_reason(
                rule_result, final_cycle_state
            )
        }

    def _generate_transition_reason(self, rule_result: Dict[str, Any],
                                   final_cycle_state: str) -> str:
        """生成状态转换原因"""
        scores = rule_result["scores"]
        mainline_score = scores.get("mainline_strength_score", 0)

        if final_cycle_state == "fade_confirmed":
            return "退潮确认评分≥60，满足退潮硬证据条件"
        elif final_cycle_state == "fade_watch":
            return "退潮观察评分≥50，进入退潮观察状态"
        elif final_cycle_state == "divergence":
            return "分歧评分≥60，进入分歧状态"
        elif final_cycle_state == "repair":
            return "修复评分≥65，且允许从分歧或退潮观察转入"
        elif final_cycle_state == "acceleration":
            return f"主线强度评分{mainline_score}≥75且涨停≥3家，进入加速状态"
        elif final_cycle_state == "fermentation":
            return f"主线强度评分{mainline_score}≥60，进入发酵状态"
        else:  # start
            return "默认启动状态"

    def _calculate_rule_confidence(self, evidence: CycleEvidenceInput, scores: Dict[str, float]) -> float:
        """计算规则层置信度（0-100）

        基于证据质量和评分一致性计算规则层判断的置信度
        """
        confidence = 70.0  # 基础置信度

        # 证据完整性加分（0-15分）
        evidence_score = 0.0
        if evidence.event_recency_days is not None:
            evidence_score += 5.0  # 事件时效性有数据
        if evidence.leader_alive_score > 0:
            evidence_score += 5.0  # 龙头数据有数据
        if evidence.theme_support_score > 0:
            evidence_score += 5.0  # K线数据有数据
        confidence += min(evidence_score, 15.0)

        # 评分一致性加分（0-15分）
        consistency_score = 0.0
        mainline_strength = scores.get("mainline_strength_score", 0)
        fade_risk = scores.get("fade_risk_score", 0)

        # 主线强度高且退潮风险低 -> 一致性高
        if mainline_strength >= 60 and fade_risk < 30:
            consistency_score += 10.0
        # 主线强度低且退潮风险高 -> 一致性高
        elif mainline_strength < 40 and fade_risk > 50:
            consistency_score += 10.0
        # 其他情况 -> 中等一致性
        else:
            consistency_score += 5.0

        confidence += consistency_score

        # 限制在0-100范围内
        return max(0.0, min(100.0, round(confidence, 2)))

    async def _save_judgement_to_db(self, conn: asyncpg.Connection,
                                   trade_date: date,
                                   subject_key: str,
                                   theme_name: Optional[str],
                                   evidence: CycleEvidenceInput,
                                   rule_result: Dict[str, Any],
                                   llm_result: Dict[str, Any],
                                   final_judgement: Dict[str, Any]) -> None:
        """将判决保存到V2表"""
        sql = """
        INSERT INTO theme_cycle_judgement_v2 (
            trade_date, subject_key, theme_name,
            cycle_state_rule, mainline_alive_rule,
            cycle_state_llm, mainline_alive_llm,
            final_cycle_state, final_mainline_alive,
            fade_watch, fade_confirmed,
            mainline_strength_score, fade_risk_score,
            fade_watch_score, fade_confirmed_score,
            divergence_score, repair_score, confidence_score,
            previous_cycle_state, state_transition_reason,
            rule_reasons, llm_reasons, risk_flags, evidence_refs,
            judgement_schema_version, state_machine_version,
            llm_prompt_version, source_version
        ) VALUES (
            $1, $2, $3,
            $4, $5,
            $6, $7,
            $8, $9,
            $10, $11,
            $12, $13,
            $14, $15,
            $16, $17, $18,
            $19, $20,
            $21, $22, $23, $24,
            $25, $26,
            $27, $28
        )
        ON CONFLICT (trade_date, subject_key) DO UPDATE SET
            cycle_state_rule = EXCLUDED.cycle_state_rule,
            mainline_alive_rule = EXCLUDED.mainline_alive_rule,
            cycle_state_llm = EXCLUDED.cycle_state_llm,
            mainline_alive_llm = EXCLUDED.mainline_alive_llm,
            final_cycle_state = EXCLUDED.final_cycle_state,
            final_mainline_alive = EXCLUDED.final_mainline_alive,
            fade_watch = EXCLUDED.fade_watch,
            fade_confirmed = EXCLUDED.fade_confirmed,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_risk_score = EXCLUDED.fade_risk_score,
            fade_watch_score = EXCLUDED.fade_watch_score,
            fade_confirmed_score = EXCLUDED.fade_confirmed_score,
            divergence_score = EXCLUDED.divergence_score,
            repair_score = EXCLUDED.repair_score,
            confidence_score = EXCLUDED.confidence_score,
            previous_cycle_state = EXCLUDED.previous_cycle_state,
            state_transition_reason = EXCLUDED.state_transition_reason,
            rule_reasons = EXCLUDED.rule_reasons,
            llm_reasons = EXCLUDED.llm_reasons,
            risk_flags = EXCLUDED.risk_flags,
            evidence_refs = EXCLUDED.evidence_refs,
            judgement_schema_version = EXCLUDED.judgement_schema_version,
            state_machine_version = EXCLUDED.state_machine_version,
            llm_prompt_version = EXCLUDED.llm_prompt_version,
            source_version = EXCLUDED.source_version,
            created_at = now()
        """

        scores = final_judgement["scores"]

        await conn.execute(
            sql,
            trade_date,
            subject_key,
            theme_name or evidence.theme_name,

            # 规则引擎输出
            rule_result["cycle_state_rule"],
            rule_result["mainline_alive_rule"],

            # LLM复核输出
            llm_result["cycle_state_llm"],
            llm_result["mainline_alive_llm"],

            # 最终判决
            final_judgement["final_cycle_state"],
            final_judgement["final_mainline_alive"],
            final_judgement["fade_watch"],
            final_judgement["fade_confirmed"],

            # 评分字段
            scores.get("mainline_strength_score", 0),
            scores.get("fade_risk_score", 0),  # 从unified_cycle_scoring_service获取
            scores.get("fade_watch_score", 0),
            scores.get("fade_confirmed_score", 0),
            scores.get("divergence_score", 0),
            scores.get("repair_score", 0),
            float(llm_result.get("confidence", 0)),  # 使用LLM复核的置信度

            # 状态转换
            evidence.previous_cycle_state,
            final_judgement["state_transition_reason"],

            # 解释字段
            json.dumps(rule_result["rule_reasons"], ensure_ascii=False),
            json.dumps(llm_result["llm_reasons"], ensure_ascii=False),
            json.dumps(llm_result.get("risk_flags", []), ensure_ascii=False),
            json.dumps([{"type": "evidence", "ref": f"theme_cycle_evidence_daily:{trade_date}:{subject_key}"}], ensure_ascii=False),

            # 版本控制
            "theme_cycle_judgement.v2",
            "state_machine.v1",
            llm_result.get("llm_prompt_version"),
            "theme_cycle_judgement.v2"
        )


async def main():
    """测试函数"""
    import sys
    from datetime import date

    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)

    service = ThemeCycleJudgementService()
    try:
        print(f"开始执行 {test_date} 的主题周期判决...")
        judgements = await service.judge_all_themes_for_date(test_date)
        print(f"完成 {len(judgements)} 个主题的判决")

        # 打印前几个结果
        for i, judgement in enumerate(judgements[:5], 1):
            print(f"{i}. {judgement.get('final_cycle_state', 'unknown')} "
                  f"(mainline: {judgement.get('final_mainline_alive', False)})")
    finally:
        await service.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

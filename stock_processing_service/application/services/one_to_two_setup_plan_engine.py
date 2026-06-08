from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from stock_processing_service.application.services.post_market_setup_fact_context_builder import (
    PostMarketSetupFactContextBuilder,
)
from stock_processing_service.contracts.dto.one_to_two_dto import (
    OneToTwoFeatures,
    OneToTwoSetupPlanDTO,
    RuleResult,
    ScoreResult,
)
from stock_processing_service.domain.services.one_to_two_technical_gate import (
    TECHNICAL_FOCUS_SCORE_THRESHOLD,
)
from stock_processing_service.contracts.dto.post_market_setup_context_dto import PostMarketSetupFactContext
from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService
from stock_processing_service.domain.services.one_to_two_risk_plan_builder import OneToTwoRiskPlanBuilder
from stock_processing_service.domain.services.one_to_two_rule_config import OneToTwoRuleConfig
from stock_processing_service.domain.services.one_to_two_rule_engine import OneToTwoRuleEngine
from stock_processing_service.domain.services.one_to_two_scorer import OneToTwoScorer


class OneToTwoSetupPlanEngine:
    """Build OneToTwo post-market setup observation plan.

    Does not read Layer C or D1.
    Does not mutate A/B/C/D.
    Does not emit buy signals.
    """

    def __init__(
        self,
        fact_context_builder: PostMarketSetupFactContextBuilder | None = None,
        candidate_service: OneToTwoCandidateService | None = None,
        rule_engine: OneToTwoRuleEngine | None = None,
        rule_config: OneToTwoRuleConfig | None = None,
        scorer: OneToTwoScorer | None = None,
        risk_plan_builder: OneToTwoRiskPlanBuilder | None = None,
    ) -> None:
        self.fact_context_builder = fact_context_builder
        self.candidate_service = candidate_service or OneToTwoCandidateService()
        self.rule_engine = rule_engine or OneToTwoRuleEngine(rule_config)
        self.scorer = scorer or OneToTwoScorer()
        self.risk_plan_builder = risk_plan_builder or OneToTwoRiskPlanBuilder()

    async def build(
        self,
        trade_date,
        read_port: Any,
        *,
        source_doc: dict[str, Any] | None = None,
    ) -> OneToTwoSetupPlanDTO:
        builder = self.fact_context_builder or PostMarketSetupFactContextBuilder(read_port)
        ctx = await builder.build(trade_date, source_doc=source_doc)
        return self.build_from_context(ctx)

    FOCUS_SCORE_THRESHOLD = Decimal("80")
    FOCUS_TECHNICAL_SCORE_THRESHOLD = TECHNICAL_FOCUS_SCORE_THRESHOLD  # 55

    def build_from_context(self, ctx: PostMarketSetupFactContext) -> OneToTwoSetupPlanDTO:
        fact_pool = self.candidate_service.build_fact_pool(ctx)

        items: list[dict[str, Any]] = []
        candidate_features: list[dict[str, Any]] = []
        reject_reasons: Counter[str] = Counter()
        reject_count = 0

        for features in fact_pool:
            rule = self.rule_engine.apply(features)
            score = self.scorer.score(features, rule)
            final_rule = self._apply_score_policy(features, rule, score)
            # Use final_rule for BOTH candidate_feature and plan item (consistency)
            candidate_features.append(self._to_candidate_feature_item(features, final_rule, score))
            if final_rule.decision == "reject":
                reject_count += 1
                reject_reasons.update(final_rule.veto_reasons)
                continue

            plan = self.risk_plan_builder.build(features, final_rule, score)
            items.append(self._to_plan_item(features, final_rule, score, plan))

        items = sorted(
            items,
            key=lambda x: (
                x.get("decision") != "focus",
                -(float(x.get("final_score") or 0.0)),
                str(x.get("stock_id") or ""),
            ),
        )
        summary = {
            "trade_date": ctx.trade_date,
            "watch_date": ctx.watch_date,
            "rule_version": self.rule_engine.rule_version,
            "focus_count": sum(1 for item in items if item["decision"] == "focus"),
            "observe_only_count": sum(1 for item in items if item["decision"] == "observe_only"),
            "pending_review_only_count": sum(1 for item in items if item["decision"] == "pending_review_only"),
            "reject_count": reject_count,
        }
        diagnostics = {
            "rule_version": self.rule_engine.rule_version,
            "empty_is_valid": True,
            "fact_pool_count": len(fact_pool),
            "top_reject_reasons": [reason for reason, _ in reject_reasons.most_common(10)],
            "source_status": ctx.diagnostics.to_dict().get("source_status", {}),
            "blocking_errors": list(ctx.diagnostics.blocking_errors),
            "non_blocking_warnings": list(ctx.diagnostics.non_blocking_warnings),
        }
        return OneToTwoSetupPlanDTO(
            summary=summary,
            items=items,
            diagnostics=diagnostics,
            candidate_features=candidate_features,
        )

    def _to_plan_item(
        self,
        f: OneToTwoFeatures,
        rule: RuleResult,
        score: ScoreResult,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "setup_type": "one_to_two",
            "trade_date": f.trade_date,
            "watch_date": f.watch_date,
            "stock_id": f.stock_id,
            "stock_name": f.stock_name,
            "subject_key": f.subject_key,
            "subject_name": f.subject_name,
            "decision": rule.decision,
            "plan_status": "planned",
            "watch_level": score.watch_level,
            "rule_version": self.rule_engine.rule_version,
            "final_score": float(score.final_score) if score.final_score is not None else None,
            "summary": self._summary(f, rule),
            "evidence_rules": self._evidence(f, rule, score),
            "risk_flags": list(rule.risk_flags),
            "trigger_plan": plan["trigger_plan"],
            "invalidation_plan": plan["invalidation_plan"],
            "exit_plan": plan["exit_plan"],
            "data_quality_json": dict(f.data_quality),
            "source_trace_json": dict(f.source_trace),
        }

    def _summary(self, f: OneToTwoFeatures, rule: RuleResult) -> str:
        if rule.decision == "reject":
            return "不符合1进2观察条件：%s" % "；".join(rule.veto_reasons[:3])
        return f"{f.subject_name} 首板事实入池，明日仅观察1进2晋级确认。"

    def _evidence(self, f: OneToTwoFeatures, rule: RuleResult, score: ScoreResult) -> list[str]:
        evidence = [
            f"mainline_or_hotspot_state={f.mainline_or_hotspot_state}",
            f"lifecycle_state={f.lifecycle_state}",
            f"market_trade_mode={f.market_trade_mode}",
            f"first_limit_up={f.is_first_limit_up}",
        ]
        if f.first_limit_time:
            evidence.append(f"first_limit_time={f.first_limit_time}")
        if f.turnover_rate is not None:
            evidence.append(f"turnover_rate={f.turnover_rate}")
        if f.same_subject_limit_count is not None:
            evidence.append(f"same_subject_limit_count={f.same_subject_limit_count}")
        if f.first_board_type:
            evidence.append(f"first_board_type={f.first_board_type}")
        if f.first_board_quality_tags:
            evidence.append(f"first_board_quality_tags={','.join(f.first_board_quality_tags)}")
        if f.subject_authenticity:
            evidence.append(f"subject_authenticity_scope={f.subject_authenticity.get('authenticity_scope', '')}")
            evidence.append(f"subject_authenticity_level={f.subject_authenticity.get('level', '')}")
            evidence.append(f"subject_authenticity_score={f.subject_authenticity.get('score', '')}")
        if f.kline_pattern_quality:
            evidence.append(f"has_golden_spider={f.kline_pattern_quality.get('has_golden_spider', False)}")
            evidence.append(f"kline_pattern_score={f.kline_pattern_quality.get('score', '')}")
        if score.watch_level:
            evidence.append(f"watch_level={score.watch_level}")
        evidence.extend(rule.risk_flags)
        return evidence

    @classmethod
    def _apply_score_policy(
        cls,
        f: OneToTwoFeatures,
        rule: RuleResult,
        score: ScoreResult,
    ) -> RuleResult:
        """Downgrade focus → observe_only if scores don't meet thresholds."""
        if rule.decision != "focus":
            return rule

        risk = list(rule.risk_flags)

        if score.final_score is None:
            risk.append("评分缺失，不得 focus")
            return RuleResult(decision="observe_only", veto_reasons=[], risk_flags=risk)

        technical_str = score.score_detail.get("technical_structure", "0")
        try:
            technical_score = Decimal(str(technical_str))
        except Exception:
            technical_score = Decimal("0")

        if technical_score < cls.FOCUS_TECHNICAL_SCORE_THRESHOLD:
            risk.append(f"技术形态评分{technical_score}<55，暂不 focus")
            return RuleResult(decision="observe_only", veto_reasons=[], risk_flags=risk)

        if score.final_score < cls.FOCUS_SCORE_THRESHOLD:
            risk.append(f"综合评分{score.final_score}<80，暂不 focus")
            return RuleResult(decision="observe_only", veto_reasons=[], risk_flags=risk)

        return rule

    def _to_candidate_feature_item(
        self,
        f: OneToTwoFeatures,
        rule: RuleResult,
        score: ScoreResult,
    ) -> dict[str, Any]:
        return {
            "setup_type": "one_to_two",
            "trade_date": f.trade_date,
            "watch_date": f.watch_date,
            "stock_id": f.stock_id,
            "stock_name": f.stock_name,
            "subject_key": f.subject_key,
            "subject_name": f.subject_name,
            "is_confirmed_mainline": f.is_confirmed_mainline,
            "is_strong_hotspot": f.is_strong_hotspot,
            "mainline_or_hotspot_state": f.mainline_or_hotspot_state,
            "lifecycle_state": f.lifecycle_state,
            "market_trade_mode": f.market_trade_mode,
            "allow_trade": f.allow_trade,
            "is_first_limit_up": f.is_first_limit_up,
            "first_board_type": f.first_board_type,
            "first_board_quality_tags": list(f.first_board_quality_tags or []),
            "first_board_trace": dict(f.first_board_trace or {}),
            "is_one_word_board": f.is_one_word_board,
            "is_late_seal": f.is_late_seal,
            "first_limit_time": f.first_limit_time,
            "open_board_count": f.open_board_count,
            "previous_trade_date": f.previous_trade_date,
            "previous_trade_date_limit_up": f.previous_trade_date_limit_up,
            "limit_streak_count": f.limit_streak_count,
            "turnover_rate": f.turnover_rate,
            "amount": f.amount,
            "close_seal_amount": f.close_seal_amount,
            "seal_ratio": f.seal_ratio,
            "float_mcap": f.float_mcap,
            "position_120": f.position_120,
            "is_downtrend": f.is_downtrend,
            "near_pressure": f.near_pressure,
            "same_subject_limit_count": f.same_subject_limit_count,
            "same_subject_strong_count": f.same_subject_strong_count,
            "subject_authenticity": dict(f.subject_authenticity),
            "stock_subject_authenticity": dict(f.subject_authenticity),
            "stock_subject_authenticity_scope": str(f.subject_authenticity.get("authenticity_scope") or "subject_fallback"),
            "kline_pattern_quality": dict(f.kline_pattern_quality),
            "decision": rule.decision,
            "veto_reasons": list(rule.veto_reasons),
            "risk_flags": list(rule.risk_flags),
            "first_board_quality_score": score.score_detail.get("first_board_quality"),
            "mainline_context_score": score.score_detail.get("board_breadth"),
            "technical_structure_score": score.score_detail.get("lifecycle"),
            "risk_control_score": score.score_detail.get("risk_control"),
            "final_score": float(score.final_score) if score.final_score is not None else None,
            "watch_level": score.watch_level,
            "rule_version": self.rule_engine.rule_version,
            "feature_json": {
                "trade_date": f.trade_date,
                "watch_date": f.watch_date,
                "stock_id": f.stock_id,
                "stock_name": f.stock_name,
                "subject_key": f.subject_key,
                "subject_name": f.subject_name,
                "subject_authenticity": dict(f.subject_authenticity),
                "stock_subject_authenticity": dict(f.subject_authenticity),
                "stock_subject_authenticity_scope": str(f.subject_authenticity.get("authenticity_scope") or "subject_fallback"),
                "kline_pattern_quality": dict(f.kline_pattern_quality),
                "first_board_type": f.first_board_type,
                "first_board_quality_tags": list(f.first_board_quality_tags or []),
                "first_board_trace": dict(f.first_board_trace or {}),
            },
            "data_quality_json": dict(f.data_quality),
            "source_trace_json": {
                **dict(f.source_trace),
                "rule_version": self.rule_engine.rule_version,
                "first_board_type": f.first_board_type,
                "first_board_quality_tags": list(f.first_board_quality_tags or []),
                "first_board_trace": dict(f.first_board_trace or {}),
            },
        }

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
from stock_processing_service.contracts.dto.post_market_setup_context_dto import PostMarketSetupFactContext
from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService
from stock_processing_service.domain.services.one_to_two_risk_plan_builder import OneToTwoRiskPlanBuilder
from stock_processing_service.domain.services.one_to_two_rule_engine import OneToTwoRuleEngine
from stock_processing_service.domain.services.one_to_two_scorer import OneToTwoScorer


class OneToTwoSetupPlanEngine:
    """Assemble Layer C post-market display facts for 1进2 setup planning."""

    def __init__(
        self,
        fact_context_builder: PostMarketSetupFactContextBuilder | None = None,
        candidate_service: OneToTwoCandidateService | None = None,
        rule_engine: OneToTwoRuleEngine | None = None,
        scorer: OneToTwoScorer | None = None,
        risk_plan_builder: OneToTwoRiskPlanBuilder | None = None,
    ) -> None:
        self.fact_context_builder = fact_context_builder
        self.candidate_service = candidate_service or OneToTwoCandidateService()
        self.rule_engine = rule_engine or OneToTwoRuleEngine()
        self.scorer = scorer or OneToTwoScorer()
        self.risk_plan_builder = risk_plan_builder or OneToTwoRiskPlanBuilder()

    async def build(self, trade_date, read_port: Any) -> OneToTwoSetupPlanDTO:
        builder = self.fact_context_builder or PostMarketSetupFactContextBuilder(read_port)
        ctx = await builder.build(trade_date)
        return self.build_from_context(ctx)

    def build_from_context(self, ctx: PostMarketSetupFactContext) -> OneToTwoSetupPlanDTO:
        fact_pool = self.candidate_service.build_fact_pool(ctx)

        items: list[dict[str, Any]] = []
        reject_reasons: Counter[str] = Counter()
        reject_count = 0

        for features in fact_pool:
            rule = self.rule_engine.apply(features)
            score = self.scorer.score(features, rule)
            if rule.decision == "reject":
                reject_count += 1
                reject_reasons.update(rule.veto_reasons)
                continue

            plan = self.risk_plan_builder.build(features, rule, score)
            items.append(self._to_plan_item(features, rule, score, plan))

        items = sorted(
            items,
            key=lambda x: (
                x.get("decision") != "focus",
                -(float(x.get("final_score") or 0.0)),
                str(x.get("stock_id") or ""),
            ),
        )
        summary = {
            "focus_count": sum(1 for item in items if item["decision"] == "focus"),
            "observe_only_count": sum(1 for item in items if item["decision"] == "observe_only"),
            "pending_review_only_count": sum(1 for item in items if item["decision"] == "pending_review_only"),
            "reject_count": reject_count,
        }
        diagnostics = {
            "empty_is_valid": True,
            "fact_pool_count": len(fact_pool),
            "top_reject_reasons": [reason for reason, _ in reject_reasons.most_common(10)],
            "source_status": ctx.diagnostics.to_dict().get("source_status", {}),
            "blocking_errors": list(ctx.diagnostics.blocking_errors),
            "non_blocking_warnings": list(ctx.diagnostics.non_blocking_warnings),
        }
        return OneToTwoSetupPlanDTO(summary=summary, items=items, diagnostics=diagnostics)

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
        if score.watch_level:
            evidence.append(f"watch_level={score.watch_level}")
        evidence.extend(rule.risk_flags)
        return evidence

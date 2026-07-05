from __future__ import annotations

from datetime import date

from stock_processing_service.contracts.market_cognition import (
    BeliefState,
    CognitionState,
    EvidenceItem,
    EvidenceRef,
    HypothesisState,
    MarketContextSnapshot,
    MarketEvidenceSnapshot,
    MarketThesisSnapshot,
    Phase0CognitionResult,
    QualityEnvelope,
    ScenarioView,
    ThesisStatement,
    canonical_hash,
)


def _item(snapshot: MarketEvidenceSnapshot, key: str) -> EvidenceItem | None:
    return snapshot.get(key)


def _unique_refs(items: list[EvidenceItem | None]) -> tuple[EvidenceRef, ...]:
    refs: list[EvidenceRef] = []
    seen: set[str] = set()
    for item in items:
        if item is None or item.ref.ref_id in seen:
            continue
        seen.add(item.ref.ref_id)
        refs.append(item.ref)
    return tuple(refs)


def _mainline_name(snapshot: MarketEvidenceSnapshot) -> EvidenceItem | None:
    return next(
        (
            item
            for item in snapshot.evidence
            if item.key.startswith("mainline.") and item.key.endswith(".name")
        ),
        None,
    )


class MarketContextBuilder:
    POLICY_VERSION = "m8_phase0_context.v1"

    @classmethod
    def build(cls, evidence: MarketEvidenceSnapshot) -> MarketContextSnapshot:
        blocking = _item(evidence, "decision.blocking_rule")
        sentiment = _item(evidence, "market.short_term_sentiment")
        mainline = _mainline_name(evidence)
        refs = _unique_refs([blocking, sentiment, mainline])
        status = "ready" if refs else "insufficient"
        tensions: list[str] = []
        if blocking is not None:
            tensions.append("交易权限受风险条件约束")
        if sentiment is not None and str(sentiment.value) == "dead":
            tensions.append("短线情绪处于冰点")
        if mainline is not None:
            tensions.append(f"主线观察聚焦{mainline.value}")
        transitions = (
            ("等待情绪与主线修复确认",)
            if blocking is not None
            else ()
        )
        quality = QualityEnvelope(
            status=status,
            score=evidence.quality.score if refs else 0.0,
            missing_modules=evidence.quality.missing_modules,
            issues=() if refs else ("insufficient_evidence",),
        )
        hash_input = {
            "schema_version": "market_context.v1",
            "context_version": 1,
            "context_type": "CLOSE",
            "trade_date": evidence.trade_date,
            "as_of": evidence.as_of,
            "status": status,
            "dominant_tensions": tensions,
            "active_transitions": transitions,
            "evidence_refs": refs,
            "policy_version": cls.POLICY_VERSION,
        }
        content_hash = canonical_hash(hash_input)
        return MarketContextSnapshot(
            context_id=f"mctx:{evidence.trade_date}:close:v1:{content_hash[:12]}",
            schema_version="market_context.v1",
            context_version=1,
            context_type="CLOSE",
            trade_date=evidence.trade_date,
            as_of=evidence.as_of,
            status=status,
            dominant_tensions=tuple(tensions),
            active_transitions=transitions,
            evidence_refs=refs,
            quality=quality,
            content_hash=content_hash,
        )


class FixedCognitionPolicy:
    POLICY_VERSION = "m8_phase0_cognition.v1"

    @classmethod
    def evaluate(
        cls,
        evidence: MarketEvidenceSnapshot,
        context: MarketContextSnapshot,
    ) -> CognitionState:
        allow_trade = _item(evidence, "decision.allow_trade")
        blocking = _item(evidence, "decision.blocking_rule")
        mainline = _mainline_name(evidence)
        next_trade_date = _item(evidence, "calendar.next_trade_date")
        beliefs: list[BeliefState] = []
        hypotheses: list[HypothesisState] = []

        if allow_trade is not None:
            permission_refs = _unique_refs([allow_trade, blocking])
            beliefs.append(
                BeliefState(
                    proposition_key="market.trade_permission",
                    score=1.0 if bool(allow_trade.value) else 0.0,
                    confidence=max(0.1, evidence.quality.score),
                    support_refs=permission_refs,
                )
            )

        deadline: str | None = None
        if next_trade_date is not None:
            try:
                candidate = date.fromisoformat(str(next_trade_date.value))
                if candidate > date.fromisoformat(evidence.trade_date):
                    deadline = candidate.isoformat()
            except ValueError:
                deadline = None

        if allow_trade is not None and not bool(allow_trade.value) and deadline:
            hypothesis_refs = _unique_refs(
                [allow_trade, blocking, mainline, next_trade_date]
            )
            hypotheses.append(
                HypothesisState(
                    hypothesis_id=f"hyp:{evidence.trade_date}:mainline_repair",
                    statement="主线修复后，交易权限才具备重新评估条件。",
                    status="VALIDATING",
                    probability=0.35,
                    deadline=deadline,
                    expected_observations=(
                        "短线情绪脱离冰点",
                        "主线强度与资金验证同步恢复",
                    ),
                    falsifiers=(
                        "短线情绪继续处于冰点",
                        "主线修复失败或资金继续分散",
                    ),
                    evidence_refs=hypothesis_refs,
                )
            )

        hash_input = {
            "schema_version": "cognition_state.v1",
            "trade_date": evidence.trade_date,
            "as_of": evidence.as_of,
            "context_id": context.context_id,
            "beliefs": beliefs,
            "hypotheses": hypotheses,
            "policy_version": cls.POLICY_VERSION,
        }
        content_hash = canonical_hash(hash_input)
        return CognitionState(
            state_id=f"cog:{evidence.trade_date}:{content_hash[:16]}",
            schema_version="cognition_state.v1",
            trade_date=evidence.trade_date,
            as_of=evidence.as_of,
            context_id=context.context_id,
            beliefs=tuple(beliefs),
            hypotheses=tuple(hypotheses),
            policy_version=cls.POLICY_VERSION,
            content_hash=content_hash,
        )


class MarketThesisBuilder:
    POLICY_VERSION = "m8_phase0_thesis.v1"

    @classmethod
    def build(
        cls,
        evidence: MarketEvidenceSnapshot,
        context: MarketContextSnapshot,
        cognition: CognitionState,
    ) -> MarketThesisSnapshot:
        allow_trade = _item(evidence, "decision.allow_trade")
        blocking = _item(evidence, "decision.blocking_rule")
        strategy = _item(evidence, "decision.next_day_strategy")
        mainline = _mainline_name(evidence)

        if allow_trade is None:
            return cls._unavailable(evidence, cognition)

        thesis_refs = _unique_refs([allow_trade, blocking, mainline])
        if bool(allow_trade.value):
            statement = "当前允许在既定风险约束内参与市场。"
            trading_permission = "允许交易"
        else:
            statement = "当前不支持主动交易，核心任务是观察主线能否修复。"
            trading_permission = "不交易"
        if mainline is not None:
            statement += f" 当前主线观察聚焦{mainline.value}。"

        scenarios: list[ScenarioView] = []
        if not bool(allow_trade.value):
            scenarios.append(
                ScenarioView(
                    condition="若短线情绪脱离冰点且主线获得资金确认",
                    expected_result="重新评估交易权限，不提前假定修复成功",
                    evidence_refs=thesis_refs,
                )
            )
        elif strategy is not None:
            scenarios.append(
                ScenarioView(
                    condition="若既定风险条件保持有效",
                    expected_result=str(strategy.value),
                    evidence_refs=_unique_refs([allow_trade, strategy]),
                )
            )

        all_refs = _unique_refs(
            [allow_trade, blocking, mainline, strategy]
        )
        invalidations = tuple(
            cognition.hypotheses[0].falsifiers
            if cognition.hypotheses
            else ("交易权限或主线证据发生反向变化",)
        )
        primary = ThesisStatement(
            statement=statement,
            evidence_refs=thesis_refs,
            confidence=max(0.1, evidence.quality.score),
        )
        hypothesis_results = (
            ("暂无可验证的昨日结构化假设",)
            if not cognition.hypotheses
            else ("昨日结构化假设尚未接入，当前假设进入验证中",)
        )
        changes = tuple(context.dominant_tensions[:3])
        ref_coverage = 1.0 if primary.evidence_refs else 0.0
        quality = QualityEnvelope(
            status="ready",
            score=min(evidence.quality.score, ref_coverage),
            missing_modules=evidence.quality.missing_modules,
        )
        hash_input = {
            "schema_version": "market_thesis.v1",
            "trade_date": evidence.trade_date,
            "as_of": evidence.as_of,
            "primary": primary,
            "hypothesis_results": hypothesis_results,
            "changes": changes,
            "scenarios": scenarios,
            "invalidations": invalidations,
            "trading_permission": trading_permission,
            "evidence_refs": all_refs,
            "cognition_state_id": cognition.state_id,
            "policy_version": cls.POLICY_VERSION,
        }
        content_hash = canonical_hash(hash_input)
        return MarketThesisSnapshot(
            thesis_id=f"thesis:{evidence.trade_date}:{content_hash[:16]}",
            schema_version="market_thesis.v1",
            trade_date=evidence.trade_date,
            as_of=evidence.as_of,
            status="ready",
            primary_thesis=primary,
            hypothesis_results=hypothesis_results,
            key_belief_changes=changes,
            scenarios=tuple(scenarios),
            invalidation_conditions=invalidations,
            trading_permission=trading_permission,
            evidence_refs=all_refs,
            cognition_state_id=cognition.state_id,
            quality=quality,
            unsupported_claim_count=0,
            evidence_ref_coverage=ref_coverage,
            content_hash=content_hash,
        )

    @classmethod
    def _unavailable(
        cls,
        evidence: MarketEvidenceSnapshot,
        cognition: CognitionState,
    ) -> MarketThesisSnapshot:
        hash_input = {
            "schema_version": "market_thesis.v1",
            "trade_date": evidence.trade_date,
            "as_of": evidence.as_of,
            "status": "unavailable",
            "reason": "insufficient_evidence",
            "cognition_state_id": cognition.state_id,
        }
        content_hash = canonical_hash(hash_input)
        return MarketThesisSnapshot(
            thesis_id=f"thesis:{evidence.trade_date}:{content_hash[:16]}",
            schema_version="market_thesis.v1",
            trade_date=evidence.trade_date,
            as_of=evidence.as_of,
            status="unavailable",
            primary_thesis=None,
            hypothesis_results=(),
            key_belief_changes=(),
            scenarios=(),
            invalidation_conditions=(),
            trading_permission="无法判定",
            evidence_refs=(),
            cognition_state_id=cognition.state_id,
            quality=QualityEnvelope(
                status="insufficient",
                score=0.0,
                missing_modules=evidence.quality.missing_modules,
                issues=("insufficient_evidence",),
            ),
            unsupported_claim_count=0,
            evidence_ref_coverage=1.0,
            content_hash=content_hash,
        )


class Phase0CognitionPipeline:
    @classmethod
    def build(cls, evidence: MarketEvidenceSnapshot) -> Phase0CognitionResult:
        context = MarketContextBuilder.build(evidence)
        cognition = FixedCognitionPolicy.evaluate(evidence, context)
        thesis = MarketThesisBuilder.build(evidence, context, cognition)
        diagnostics = (
            ("insufficient_evidence",)
            if thesis.status != "ready"
            else ()
        )
        return Phase0CognitionResult(
            context=context,
            cognition=cognition,
            thesis=thesis,
            diagnostics=diagnostics,
        )

from __future__ import annotations

from .phase0_harness_types import (
    ExecutionEvidence,
    NewsRawPersistenceEvidence,
    P2Phase0RunContext,
    PipelineAuditBundle,
    StructuredEventEvidence,
    ThemeDecisionEvidence,
)


def build_pipeline_audit_bundle(
    run_ctx: P2Phase0RunContext,
    news_raw: NewsRawPersistenceEvidence | None = None,
    structured: StructuredEventEvidence | None = None,
    decisions: ThemeDecisionEvidence | None = None,
    execution: ExecutionEvidence | None = None,
) -> PipelineAuditBundle:
    return PipelineAuditBundle(
        run_context=run_ctx,
        news_raw=news_raw or NewsRawPersistenceEvidence(),
        structured=structured or StructuredEventEvidence(),
        decisions=decisions or ThemeDecisionEvidence(),
        execution=execution or ExecutionEvidence(),
    )


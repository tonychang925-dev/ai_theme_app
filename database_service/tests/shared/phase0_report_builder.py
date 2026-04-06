from __future__ import annotations

from .phase0_harness_types import P2Phase0HarnessReport, PipelineAuditBundle


def build_phase0_harness_report(bundle: PipelineAuditBundle) -> P2Phase0HarnessReport:
    summary = {
        "run_id": bundle.run_context.run_id,
        "raw_news_count": bundle.news_raw.success_count,
        "structured_count": bundle.structured.success_count,
        "decision_count": bundle.decisions.success_count,
        "mapped_count": len(bundle.execution.mapped_event_ids),
    }
    return P2Phase0HarnessReport(run_id=bundle.run_context.run_id, summary=summary, bundle=bundle)


def render_phase0_harness_summary(report: P2Phase0HarnessReport) -> str:
    return (
        f"run_id={report.run_id} "
        f"raw={report.summary['raw_news_count']} "
        f"structured={report.summary['structured_count']} "
        f"decision={report.summary['decision_count']} "
        f"mapped={report.summary['mapped_count']}"
    )


"""Phase 4.5.3 — Workbench Report Composer.

Connects the ApprovalGate to the PostMarketEngineReportComposer,
ensuring only APPROVED/PUBLISHED snapshots produce formal reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from .approval_gate import ApprovalGate, ApprovalRequiredError, ReportApproval
from .formal_gate import FormalComposeGuard

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ComposedReport:
    """Result of composing a report from a workbench approval."""

    mode: str  # "preview" | "formal" | "published"
    trade_date: date
    report: dict[str, Any]  # composed report body (may be empty for blocked)
    approval: ReportApproval
    error: str | None = None


class WorkbenchReportComposer:
    """Orchestrate report composition through the approval gate.

    Usage:
        composer = WorkbenchReportComposer()
        result = composer.compose(trade_date, recap_doc)

    If no approved snapshot exists:
      - result.mode == "preview"
      - result.report contains a lightweight preview (engine report with
        workbench_approval metadata showing the gating status)

    If approved:
      - result.mode == "formal" or "published"
      - result.report contains the full engine report enriched with
        snapshot metadata
    """

    def __init__(self, workbench_base_dir: str = "tmp/analyst_workbench"):
        self._gate = ApprovalGate(base_dir=workbench_base_dir)
        self._formal_guard = FormalComposeGuard()

    def compose(
        self,
        trade_date: date,
        recap_doc: dict[str, Any] | None = None,
    ) -> ComposedReport:
        """Compose a report gated by workbench approval status.

        Args:
            trade_date: Trading date to compose for.
            recap_doc: Existing recap document from post_market_recap_snapshot.
                       Used as the evidence base. If None, only snapshot data
                       is used.

        Returns:
            ComposedReport with mode, report dict, and approval metadata.
        """
        approval = self._gate.check(trade_date)

        # ── Build report metadata always ──
        approval_meta = {
            "workbench_approval": {
                "mode": approval.mode,
                "session_status": approval.session_status,
                "can_generate_formal_report": approval.can_generate_report,
                "snapshot_version": approval.snapshot_version,
                "approved_at": approval.approved_at,
                "approved_by": approval.approved_by,
                "based_on_draft_version": (
                    approval.snapshot.based_on_draft_version
                    if approval.snapshot else 0
                ),
                "snapshot_hash": approval.snapshot.snapshot_hash if approval.snapshot else "",
                "approval_mode": approval.snapshot.approval_mode if approval.snapshot else "",
                "source_mode": approval.snapshot.source_mode if approval.snapshot else "",
                "composition_mode": approval.snapshot.composition_mode if approval.snapshot else "",
                "reason": approval.reason,
            }
        }

        # ── Compose engine report from recap_doc (existing evidence) ──
        engine_report: dict[str, Any] = {}
        if recap_doc:
            try:
                from stock_processing_service.application.services.post_market_engine_report_composer import (
                    PostMarketEngineReportComposer,
                )
                composer = PostMarketEngineReportComposer()
                engine_report = composer.compose(recap_doc)
            except Exception:
                logger.exception("Engine report composition failed")

        # ── Formal / Published: enrich with workbench snapshot data ──
        snap = approval.snapshot
        if approval.can_generate_report and snap:
            snap = self._formal_guard.validate(approval)
            # Phase 4.5.4: first-class sections from approved snapshot
            report = {
                **engine_report,
                **approval_meta,

                "emotion_review": snap.emotion_review,
                "market_chart_reviews": snap.chart_reviews,
                "attention_review": snap.attention_state,
                "cognition_reviews": snap.cognition_cards,
                "narrative_review": snap.narrative,
                "playbook_review": snap.playbook,
                "analyst_override_review": snap.override_summary,

            }
        else:
            report = {
                **engine_report,
                **approval_meta,

                "emotion_review": {},
                "market_chart_reviews": [],
                "attention_review": {},
                "cognition_reviews": [],
                "narrative_review": {},
                "playbook_review": {},
                "analyst_override_review": {},
            }

        return ComposedReport(
            mode=approval.mode,
            trade_date=trade_date,
            report=report,
            approval=approval,
        )

    def require_formal(self, trade_date: date) -> ReportApproval:
        """Raise ApprovalRequiredError unless approved snapshot exists."""
        approval = self._gate.require_formal(trade_date)
        self._formal_guard.validate(approval)
        return approval

    def check(self, trade_date: date) -> ReportApproval:
        """Non-throwing gate check."""
        return self._gate.check(trade_date)

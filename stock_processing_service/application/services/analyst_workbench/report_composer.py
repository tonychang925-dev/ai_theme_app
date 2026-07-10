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
        if approval.can_generate_report and approval.snapshot:
            workbench_data = {
                "attention_state": approval.snapshot.attention_state,
                "cognition_cards": approval.snapshot.cognition_cards,
                "narrative": approval.snapshot.narrative,
                "playbook": approval.snapshot.playbook,
                "override_summary": approval.snapshot.override_summary,
            }
        else:
            workbench_data = {
                "attention_state": {},
                "cognition_cards": [],
                "narrative": {},
                "playbook": {},
                "override_summary": {},
            }

        report = {
            **engine_report,
            **approval_meta,
            "workbench_data": workbench_data,
        }

        return ComposedReport(
            mode=approval.mode,
            trade_date=trade_date,
            report=report,
            approval=approval,
        )

    def require_formal(self, trade_date: date) -> ReportApproval:
        """Raise ApprovalRequiredError unless approved snapshot exists."""
        return self._gate.require_formal(trade_date)

    def check(self, trade_date: date) -> ReportApproval:
        """Non-throwing gate check."""
        return self._gate.check(trade_date)

"""Tool: market.workbench.review — real AIDraft or Approved Snapshot judgments.

opinion_mode: ai_draft / analyst_approved / not_ready.
No hardcoded sample data.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def market_workbench_review(trade_date: str | None = None) -> dict:
    td = trade_date or datetime.now(CST).strftime("%Y-%m-%d")

    result = _try_approved(td)
    if result:
        return result

    result = _try_draft(td)
    if result:
        return result

    return _not_ready(td)


def _try_approved(td: str) -> dict | None:
    import os, json
    from pathlib import Path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    wb_base = Path(project_root) / "tmp" / "analyst_workbench" / td
    if not (wb_base / "session.json").exists() or not (wb_base / "snapshot.json").exists():
        return None
    session = json.loads((wb_base / "session.json").read_text(encoding="utf-8"))
    from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot
    snap = ReviewSnapshot.from_dict(json.loads((wb_base / "snapshot.json").read_text(encoding="utf-8")))
    from stock_processing_service.application.services.analyst_workbench.snapshot_validator import ApprovedSnapshotValidator
    vr = ApprovedSnapshotValidator().validate(session.get("status", ""), snap)
    if not vr.valid:
        return None
    from stock_processing_service.application.services.analyst_workbench.intelligence_exporter import AnalystIntelligenceExporter
    data = AnalystIntelligenceExporter().export(snap).to_dict()
    data["opinion_mode"] = "analyst_approved"
    return data


def _try_draft(td: str) -> dict | None:
    import os, json
    from pathlib import Path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    drafts_dir = Path(project_root) / "tmp" / "analyst_workbench" / td / "drafts"
    if not drafts_dir.exists():
        return None
    files = sorted(drafts_dir.glob("*.json"), reverse=True)
    if not files:
        return None
    draft = json.loads(files[0].read_text(encoding="utf-8"))
    cards = draft.get("cognition_cards", [])
    claims = [{
        "claim_id": f"claim_draft_{td}_{c.get('subject_name','')}",
        "claim_type": "theme_stage",
        "subject": {"type": "theme", "name": c.get("subject_name", "")},
        "stage_judgement": str(c.get("stage_judgement", c.get("stage", ""))),
        "attention_level": str(c.get("attention_level", "LOW")),
        "attention_score": int(c.get("attention_score", 0)),
        "confidence": float(c.get("confidence", 0.5)),
        "analyst_reviewed": False,
        "analyst_override": False,
        "evidence_refs": list(c.get("evidence", []))[:5],
    } for c in cards if c.get("subject_name")]
    return {
        "schema_version": "analyst-workbench.review.v1",
        "provider": "ai_theme_app", "trade_date": td,
        "generated_at": datetime.now(CST).isoformat(),
        "opinion_mode": "ai_draft",
        "market_judgment": draft.get("narrative", {}),
        "claims": claims,
        "approval": {"mode": "ai_draft", "analyst_reviewed": False},
        "quality": {"source_quality": float(draft.get("source_quality", 0.5)), "claim_count": len(claims)},
    }


def _not_ready(td: str) -> dict:
    return {
        "schema_version": "analyst-workbench.review.v1", "provider": "ai_theme_app",
        "trade_date": td, "generated_at": datetime.now(CST).isoformat(),
        "opinion_mode": "not_ready", "reason": "no_workbench_data_for_date",
        "claims": [], "market_judgment": {},
        "approval": {"status": "not_ready"},
    }


__all__ = ["market_workbench_review"]

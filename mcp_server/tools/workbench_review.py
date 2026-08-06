"""Tool: market.workbench.review — unified analyst-workbench.review.v1 schema.

Both Draft and Approved paths output the SAME schema.
opinion_mode distinguishes: ai_draft / analyst_approved / not_ready.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def market_workbench_review(trade_date: str | None = None) -> dict:
    td = trade_date or datetime.now(CST).strftime("%Y-%m-%d")

    # Check approved first
    exists, result = _try_approved(td)
    if exists:
        return result  # either valid approved or rejected — no fallback

    # No approved snapshot → try draft
    return _try_draft(td) or _not_ready(td)


def _try_approved(td: str) -> tuple[bool, dict | None]:
    """Returns (snapshot_exists, result_or_None).

    If snapshot exists but validation fails → exists=True, result=rejected.
    """
    import os, json
    from pathlib import Path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    wb_base = Path(project_root) / "tmp" / "analyst_workbench" / td

    if not (wb_base / "session.json").exists() or not (wb_base / "snapshot.json").exists():
        return (False, None)  # no snapshot at all → draft fallback OK

    session = json.loads((wb_base / "session.json").read_text(encoding="utf-8"))
    from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot
    try:
        snap = ReviewSnapshot.from_dict(json.loads((wb_base / "snapshot.json").read_text(encoding="utf-8")))
    except Exception:
        return (True, _rejected(td, "snapshot_json_corrupted"))

    from stock_processing_service.application.services.analyst_workbench.snapshot_validator import ApprovedSnapshotValidator
    vr = ApprovedSnapshotValidator().validate(session.get("status", ""), snap)
    if not vr.valid:
        return (True, _rejected(td, "approved_snapshot_validation_failed",
                                [e.value for e in vr.errors]))

    # Build approved claims
    cards = snap.cognition_cards or []
    claims = []
    for c in cards:
        name = c.get("subject_name", "")
        if not name:
            continue
        stage = _resolve_final(c, "stage_judgement", "")
        claims.append({
            "claim_id": f"claim_approved_{td}_{name}",
            "claim_type": "theme_stage",
            "subject": {"type": "theme", "name": name},
            "stage_judgement": stage,
            "attention_level": str(c.get("attention_level", "LOW")),
            "attention_score": int(c.get("attention_score", 0)),
            "confidence": float(c.get("confidence", 0.5)),
            "analyst_reviewed": bool(c.get("analyst_reviewed", False)),
            "analyst_override": bool(c.get("analyst_added", False)),
            "evidence_refs": [str(e) for e in c.get("evidence", []) if e][:5],
        })

    return (True, _build_envelope(td, "analyst_approved", claims, {
        "snapshot_version": snap.snapshot_version,
        "snapshot_hash": snap.snapshot_hash,
        "approved_at": snap.approved_at,
        "approved_by": snap.approved_by,
        "approval_mode": snap.approval_mode,
        "analyst_reviewed": True,
    }, snap.narrative or {}, float(getattr(snap, 'source_quality', 0.8))))


def _try_draft(td: str) -> dict | None:
    import os, json
    from pathlib import Path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    drafts_dir = Path(project_root) / "tmp" / "analyst_workbench" / td / "drafts"
    if not drafts_dir.exists():
        return None
    files = sorted(drafts_dir.glob("*.json"), key=lambda p: int(p.stem.split("_v")[-1]) if "_v" in p.stem else 0, reverse=True)
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
        "analyst_reviewed": False, "analyst_override": False,
        "evidence_refs": list(c.get("evidence", []))[:5],
    } for c in cards if c.get("subject_name")]
    return _build_envelope(td, "ai_draft", claims, {
        "draft_version": int(draft.get("draft_version", 1)),
        "analyst_reviewed": False,
    }, draft.get("narrative", {}), float(draft.get("source_quality", 0.5)))


def _build_envelope(td, mode, claims, approval, narrative, quality) -> dict:
    return {
        "schema_version": "analyst-workbench.review.v1",
        "provider": "ai_theme_app",
        "trade_date": td,
        "generated_at": datetime.now(CST).isoformat(),
        "opinion_mode": mode,
        "claims": claims,
        "market_judgment": {
            "phase": str(narrative.get("phase", "")),
            "summary": str(narrative.get("summary", "")),
        } if narrative else {},
        "approval": approval,
        "quality": {"source_quality": quality, "claim_count": len(claims)},
    }


def _rejected(td: str, reason: str, errors: list | None = None) -> dict:
    return {
        "schema_version": "analyst-workbench.review.v1", "provider": "ai_theme_app",
        "trade_date": td, "generated_at": datetime.now(CST).isoformat(),
        "opinion_mode": "rejected", "reason": reason,
        "validation_errors": errors or [],
        "claims": [], "market_judgment": {}, "approval": {"status": "rejected"},
    }


def _not_ready(td: str) -> dict:
    return {
        "schema_version": "analyst-workbench.review.v1", "provider": "ai_theme_app",
        "trade_date": td, "generated_at": datetime.now(CST).isoformat(),
        "opinion_mode": "not_ready", "reason": "no_workbench_data_for_date",
        "claims": [], "market_judgment": {}, "approval": {"status": "not_ready"},
    }


def _resolve_final(card: dict, field: str, default: str = "") -> str:
    fd = card.get(field, {})
    if isinstance(fd, dict):
        return str(fd.get("final_value", fd.get("ai_value", default)))
    return str(fd) if fd else default


__all__ = ["market_workbench_review"]

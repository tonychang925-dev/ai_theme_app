#!/usr/bin/env python3
"""Phase 4.5.5-RA E2E replay with 2026-07-09 data.

The script uses real 2026-07-09 chart/emotion/workspace inputs but writes all
workbench outputs to tmp/phase455_e2e_20260709 so the production workbench
snapshot is not modified.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TRADE_DATE = date(2026, 7, 9)
TRADE_DATE_STR = TRADE_DATE.isoformat()
RUN_DIR = ROOT / "tmp" / "phase455_e2e_20260709"
WORKBENCH_BASE = RUN_DIR / "analyst_workbench"
WORKSPACE_BASE = RUN_DIR / "analyst_workspace"
SUMMARY_PATH = RUN_DIR / "summary.json"


def main() -> int:
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT))

    from stock_processing_service.application.services.analyst_workbench.draft import (
        AIDraft,
        DraftStore,
    )
    from stock_processing_service.application.services.analyst_workbench.formal_gate import (
        FormalComposeGuardError,
    )
    from stock_processing_service.application.services.analyst_workbench.report_composer import (
        WorkbenchReportComposer,
    )
    from stock_processing_service.application.services.analyst_workbench.review_merger import (
        AnalystReviewMerger,
    )
    from stock_processing_service.application.services.analyst_workbench.session import (
        SessionStore,
        WorkbenchStatus,
    )
    from stock_processing_service.application.services.analyst_workbench.snapshot import (
        ReviewSnapshot,
        SnapshotStore,
    )

    summary: dict[str, Any] = {
        "trade_date": TRADE_DATE_STR,
        "run_dir": str(RUN_DIR.relative_to(ROOT)),
        "inputs": _collect_inputs(),
    }

    summary["actual_legacy_snapshot_gate"] = _check_actual_snapshot_gate()

    generate_result = _run_draft_generate()
    summary["generate"] = generate_result
    if generate_result["returncode"] != 0:
        _write_summary(summary)
        return 1

    session_store = SessionStore(base_dir=str(WORKBENCH_BASE))
    draft_store = DraftStore(base_dir=str(WORKBENCH_BASE))
    snapshot_store = SnapshotStore(base_dir=str(WORKBENCH_BASE))

    session = session_store.get(TRADE_DATE)
    draft = draft_store.load(TRADE_DATE)
    if draft is None:
        raise RuntimeError("draft_v1 was not generated")
    summary["draft"] = {
        "session_status": session.status,
        "draft_version": draft.draft_version,
        "emotion_node": draft.emotion_review.get("emotion_node"),
        "chart_reviews_count": len(draft.chart_reviews),
        "cognition_cards_count": len(draft.cognition_cards),
        "source_quality": draft.source_quality,
        "missing_fields": draft.missing_fields,
    }

    workspace = _build_analyst_workspace()
    workspace_path = WORKSPACE_BASE / f"{TRADE_DATE_STR}.json"
    workspace_path.write_text(json.dumps(workspace, ensure_ascii=False, indent=2), encoding="utf-8")

    if session.status == WorkbenchStatus.DRAFT_READY:
        session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)

    merged = AnalystReviewMerger().merge(draft=draft, workspace=workspace, overrides={})
    snapshot = ReviewSnapshot.from_merged(
        trade_date=TRADE_DATE,
        draft=draft,
        merged=merged,
        snapshot_version=session.snapshot_version + 1,
        approved_by="phase455-e2e",
    )
    snapshot_store.save(snapshot)
    session = session_store.transition(
        session,
        WorkbenchStatus.APPROVED,
        snapshot_version=snapshot.snapshot_version,
        approved_by=snapshot.approved_by,
    )
    approved = snapshot_store.load(TRADE_DATE)
    if approved is None:
        raise RuntimeError("approved snapshot was not saved")

    changed = _find_target_override(approved.cognition_cards)
    summary["approve"] = {
        "session_status": session.status,
        "approved": approved.approved,
        "approved_by": approved.approved_by,
        "approval_mode": approved.approval_mode,
        "source_mode": approved.source_mode,
        "composition_mode": approved.composition_mode,
        "snapshot_hash": approved.snapshot_hash,
        "snapshot_hash_valid": approved.snapshot_hash == approved.compute_hash(),
        "override": changed,
    }

    composer = WorkbenchReportComposer(workbench_base_dir=str(WORKBENCH_BASE))
    composed = composer.compose(TRADE_DATE)
    report_override = _find_target_override(composed.report.get("cognition_reviews", []))
    summary["compose"] = {
        "mode": composed.mode,
        "snapshot_hash": composed.report["workbench_approval"]["snapshot_hash"],
        "approval_mode": composed.report["workbench_approval"]["approval_mode"],
        "source_mode": composed.report["workbench_approval"]["source_mode"],
        "composition_mode": composed.report["workbench_approval"]["composition_mode"],
        "emotion_node": composed.report.get("emotion_review", {}).get("emotion_node"),
        "chart_reviews_count": len(composed.report.get("market_chart_reviews", [])),
        "override": report_override,
    }

    _save_newer_ai_draft(draft_store)
    recomposed = composer.compose(TRADE_DATE)
    summary["draft_pollution_guard"] = {
        "newer_draft_version": 2,
        "mode": recomposed.mode,
        "snapshot_hash": recomposed.report["workbench_approval"]["snapshot_hash"],
        "override": _find_target_override(recomposed.report.get("cognition_reviews", [])),
    }

    blocked = _run_draft_generate()
    summary["generate_after_approve"] = {
        "returncode": blocked["returncode"],
        "stdout": blocked["stdout"],
        "stderr": blocked["stderr"],
    }

    summary["checks"] = _evaluate(summary)
    _write_summary(summary)
    return 0 if all(summary["checks"].values()) else 1


def _collect_inputs() -> dict[str, Any]:
    chart_path = ROOT / "frontend" / "public" / "api" / "analyst-charts" / f"{TRADE_DATE_STR}.json"
    emotion_path = ROOT / "frontend" / "public" / "api" / f"emotion-{TRADE_DATE_STR}.json"
    workspace_path = ROOT / "tmp" / "analyst_workspace" / f"{TRADE_DATE_STR}.json"
    charts = json.loads(chart_path.read_text(encoding="utf-8")) if chart_path.exists() else []
    emotion = json.loads(emotion_path.read_text(encoding="utf-8")) if emotion_path.exists() else {}
    workspace = json.loads(workspace_path.read_text(encoding="utf-8")) if workspace_path.exists() else {}
    return {
        "chart_path": str(chart_path.relative_to(ROOT)),
        "chart_count": len(charts),
        "emotion_path": str(emotion_path.relative_to(ROOT)),
        "emotion_node": emotion.get("emotion_node"),
        "workspace_path": str(workspace_path.relative_to(ROOT)),
        "workspace_theme_count": len(workspace.get("themes", [])) if isinstance(workspace, dict) else 0,
    }


def _check_actual_snapshot_gate() -> dict[str, str]:
    from stock_processing_service.application.services.analyst_workbench.formal_gate import (
        FormalComposeGuardError,
    )
    from stock_processing_service.application.services.analyst_workbench.report_composer import (
        WorkbenchReportComposer,
    )

    try:
        approval = WorkbenchReportComposer().require_formal(TRADE_DATE)
        return {
            "status": "accepted",
            "snapshot_hash": approval.snapshot.snapshot_hash if approval.snapshot else "",
        }
    except FormalComposeGuardError as exc:
        return {"status": "rejected", "reason": str(exc)}
    except Exception as exc:
        return {"status": "rejected", "reason": f"{type(exc).__name__}: {exc}"}


def _run_draft_generate() -> dict[str, Any]:
    env = {**os.environ, "SPS_SKIP_FETCH": "1"}
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_analyst_workbench.py"),
            "--date",
            TRADE_DATE_STR,
            "--base-dir",
            str(WORKBENCH_BASE),
        ],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _build_analyst_workspace() -> dict[str, Any]:
    workspace_path = ROOT / "tmp" / "analyst_workspace" / f"{TRADE_DATE_STR}.json"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    themes = workspace.get("themes", [])
    for theme in themes:
        if theme.get("subject_name") == "PCB印制电路板":
            theme["analyst_reviewed"] = True
            theme["stage_judgement"] = "PCB成为资金承接方向"
            theme["analyst_notes"] = "机器人高位分歧，资金切换PCB"
            theme["field_overrides"] = {
                **(theme.get("field_overrides") or {}),
                "stage_judgement": {
                    "ai_value": "人形机器人延续主线",
                    "analyst_value": "PCB成为资金承接方向",
                    "reason": "机器人高位分歧，资金切换PCB",
                },
            }
            break
    else:
        raise RuntimeError("PCB印制电路板 theme not found in 2026-07-09 workspace")
    workspace["analyst_finalized"] = True
    return workspace


def _save_newer_ai_draft(draft_store: Any) -> None:
    from stock_processing_service.application.services.analyst_workbench.draft import AIDraft

    draft = AIDraft(
        trade_date=TRADE_DATE,
        draft_version=2,
        cognition_cards=[
            {
                "subject_name": "人形机器人",
                "stage_judgement": "人形机器人重新成为主线",
            }
        ],
    )
    draft_store.save(draft)


def _find_target_override(cards: list[dict[str, Any]]) -> dict[str, Any]:
    for card in cards:
        subject_name = str(card.get("subject_name", ""))
        if subject_name != "PCB印制电路板":
            continue
        for key, value in card.items():
            if (
                key == "stage_judgement"
                and isinstance(value, dict)
                and value.get("override") is True
            ):
                return {
                    "subject_name": subject_name,
                    "field": key,
                    "ai_value": value.get("ai_value", ""),
                    "analyst_value": value.get("analyst_value", ""),
                    "final_value": value.get("final_value", ""),
                    "reason": value.get("reason", ""),
                }
    return {}


def _evaluate(summary: dict[str, Any]) -> dict[str, bool]:
    override = summary["compose"].get("override") or {}
    return {
        "input_7_9_data_available": summary["inputs"]["chart_count"] > 0
        and bool(summary["inputs"]["emotion_node"]),
        "draft_generated": summary["draft"]["session_status"] == "DRAFT_READY"
        and summary["draft"]["chart_reviews_count"] >= 1,
        "analyst_override_in_snapshot": summary["approve"]["override"].get("final_value")
        == "PCB成为资金承接方向",
        "formal_compose_snapshot_only": summary["compose"]["snapshot_hash"]
        == summary["approve"]["snapshot_hash"],
        "final_report_uses_analyst_value": override.get("final_value")
        == "PCB成为资金承接方向",
        "newer_draft_does_not_pollute_report": summary["draft_pollution_guard"]["snapshot_hash"]
        == summary["approve"]["snapshot_hash"]
        and summary["draft_pollution_guard"]["override"].get("final_value")
        == "PCB成为资金承接方向",
        "generate_after_approve_blocked": summary["generate_after_approve"]["returncode"] != 0,
    }


def _write_summary(summary: dict[str, Any]) -> None:
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())

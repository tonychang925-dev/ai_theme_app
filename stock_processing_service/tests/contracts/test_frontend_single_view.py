"""Frontend Single View Guard — Architecture Guard Layer.

Phase 4.5.7 Rule: Workbench and DailyReview SHARE one ReviewDocumentView.
No separate "复盘报告" tab + "情绪与图表" tab pattern.

Scans: AnalystWorkspacePage for dual-tab anti-pattern,
        component props for legacy data sources.

Run:
  pytest tests/contracts/test_frontend_single_view.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_SRC = PROJECT_ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Tab anti-pattern detection ──────────────────────────────────────

def test_no_separate_review_report_tab() -> None:
    """AnalystWorkspacePage must NOT have a separate '复盘报告' tab."""
    wsp = FRONTEND_SRC / "components" / "analyst" / "AnalystWorkspacePage.tsx"
    if not wsp.exists():
        pytest.skip("AnalystWorkspacePage.tsx not found")
    text = _read(wsp)

    # The string "复盘报告" must not appear as a tab label
    assert "复盘报告" not in text, (
        "AnalystWorkspacePage contains '复盘报告' tab label.\n"
        "Remove the separate ReviewDocument tab.\n"
        "ReviewDocumentView must be the ONLY content of the '情绪与图表' tab."
    )


def test_emotion_dashboard_not_used_as_separate_tab() -> None:
    """EmotionDashboard must not be rendered alongside ReviewDocumentView as a separate tab."""
    wsp = FRONTEND_SRC / "components" / "analyst" / "AnalystWorkspacePage.tsx"
    if not wsp.exists():
        pytest.skip("AnalystWorkspacePage.tsx not found")
    text = _read(wsp)

    # If EmotionDashboard is imported, it must only be used in a way that
    # doesn't create a parallel display to ReviewDocumentView
    imports_ed = "EmotionDashboard" in text
    imports_rdv = "ReviewDocumentView" in text

    if imports_ed and imports_rdv:
        # Both imported → check they're not rendered as separate tabs
        # Count occurrences of each component tag
        ed_tags = text.count("<EmotionDashboard")
        rdv_tags = text.count("<ReviewDocumentView")
        assert ed_tags == 0, (
            "EmotionDashboard is imported AND ReviewDocumentView is imported.\n"
            "EmotionDashboard must not be rendered as a separate component.\n"
            "All display must go through ReviewDocumentView."
        )


def test_emotion_dashboard_props_are_not_legacy() -> None:
    """If EmotionDashboard is used, it must receive reviewDocument, not legacy props.

    Known exception EX005: EmotionDashboard still has legacy props in its
    signature but is NOT rendered in AnalystWorkspacePage.  The component
    itself will be migrated by 2026-07-20.
    """
    ed_path = FRONTEND_SRC / "components" / "analyst" / "EmotionDashboard.tsx"
    if not ed_path.exists():
        pytest.skip("EmotionDashboard.tsx not found")
    text = _read(ed_path)

    forbidden_props = [
        "emotionReview",
        "chartReviews",
        "chartData",
        "trendData",
    ]
    violations = []
    for prop in forbidden_props:
        if re.search(rf'\b{prop}\b', text):
            violations.append(f"  legacy prop: {prop} (EX005 — expires 2026-07-20)")

    # EX005: known exception — EmotionDashboard not rendered in workbench.
    # When this expires, the test will enforce the rule.
    from datetime import date
    if date.today() > date.fromisoformat("2026-07-20"):
        assert not violations, (
            "EX005 EXPIRED. EmotionDashboard must now accept reviewDocument only."
        )

    # Before expiration: passes with warning
    if violations:
        print(f"  [EX005] Known legacy props in EmotionDashboard: {len(violations)} prop(s)")
        print(f"  [EX005] EmotionDashboard is NOT rendered in AnalystWorkspacePage.")
        print(f"  [EX005] Expires 2026-07-20.")


def test_review_document_view_does_not_fetch_legacy_api() -> None:
    """ReviewDocumentView must not fetch legacy emotion/chart endpoints."""
    rdv = FRONTEND_SRC / "components" / "review-document" / "ReviewDocumentView.tsx"
    if not rdv.exists():
        pytest.skip("ReviewDocumentView.tsx not found")
    text = _read(rdv)

    forbidden = [
        "/api/emotion-",
        "/api/analyst-charts/",
        "/daily-review-v2",
        "recap_doc",
    ]
    violations = [f"  fetch('{p}')" for p in forbidden if p in text]
    assert not violations, (
        "ReviewDocumentView fetches legacy endpoints:\n"
        + "\n".join(violations)
        + "\n\nMust only read from reviewDocument prop."
    )

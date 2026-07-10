#!/usr/bin/env python3
"""Phase 4.5 T02 — AI Draft Generator for Analyst Workbench.

Usage:
    PYTHONPATH=. python3 scripts/generate_analyst_workbench.py --date 2026-07-09
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_processing_service.application.services.analyst_workbench.session import (
    SessionStore, WorkbenchStatus,
)
from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft, DraftStore,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    SnapshotStore,
)


def main():
    parser = argparse.ArgumentParser(description="Generate AI draft for analyst workbench")
    parser.add_argument("--date", required=True, help="Trade date (YYYY-MM-DD)")
    parser.add_argument("--base-dir", default="tmp/analyst_workbench", help="Workbench storage dir")
    parser.add_argument("--chart-dir", default="frontend/public/api/analyst-charts",
                        help="AI chart JSON directory")
    parser.add_argument("--emotion-dir", default="frontend/public/api",
                        help="Emotion JSON directory")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.date)
    session_store = SessionStore(base_dir=args.base_dir)
    draft_store = DraftStore(base_dir=args.base_dir)
    snapshot_store = SnapshotStore(base_dir=args.base_dir)

    # Load or create session
    session = session_store.get(trade_date)

    # Cannot generate if approved snapshot exists (unless STALE)
    if session.status == WorkbenchStatus.APPROVED or session.status == WorkbenchStatus.PUBLISHED:
        existing_snapshot = snapshot_store.load(trade_date)
        if existing_snapshot:
            print(f"ERROR: Approved snapshot exists for {trade_date}. Mark STALE first to regenerate.")
            sys.exit(1)

    # Transition to GENERATING
    if session.status != WorkbenchStatus.GENERATING:
        session = session_store.transition(session, WorkbenchStatus.GENERATING)

    # ── Build AI Draft ──
    draft_version = draft_store.latest_version(trade_date) + 1
    draft = AIDraft(
        trade_date=trade_date,
        draft_version=draft_version,
        supersedes_version=draft_version - 1,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # ── Ensure chart + emotion data exists (call SPS API if needed) ──
    chart_path = Path(args.chart_dir) / f"{trade_date.isoformat()}.json"
    emotion_path = Path(args.emotion_dir) / f"emotion-{trade_date.isoformat()}.json"
    sps_url = "http://127.0.0.1:8090"

    if not chart_path.exists():
        print(f"Chart data not found, calling SPS API...")
        try:
            import urllib.request
            req = urllib.request.Request(f"{sps_url}/api/v1/analyst-charts/{args.date}", method='GET')
            r = urllib.request.urlopen(req, timeout=60)
            if r.status == 200:
                data = r.read()
                chart_path.parent.mkdir(parents=True, exist_ok=True)
                chart_path.write_bytes(data)
                print(f"  Chart generated: {len(data)} bytes")
            else:
                print(f"  Chart API returned {r.status}")
        except Exception as e:
            print(f"  Chart generation failed: {e}")

    if not emotion_path.exists():
        print(f"Emotion data not found, calling SPS API...")
        try:
            import urllib.request
            req = urllib.request.Request(f"{sps_url}/api/v1/emotion/{args.date}", method='GET')
            r = urllib.request.urlopen(req, timeout=30)
            if r.status == 200:
                data = r.read()
                emotion_path.parent.mkdir(parents=True, exist_ok=True)
                emotion_path.write_bytes(data)
                print(f"  Emotion generated: {len(data)} bytes")
            else:
                print(f"  Emotion API returned {r.status}")
        except Exception as e:
            print(f"  Emotion generation failed: {e}")

    missing: list[str] = []

    if chart_path.exists():
        try:
            charts = json.loads(chart_path.read_text())
            draft.attention_state = {"charts_available": len(charts)}
            draft.cognition_cards = _build_cognition_cards(charts)
        except (json.JSONDecodeError, OSError) as e:
            missing.append(f"chart_json_error: {e}")
    else:
        missing.append("charts_json")

    if emotion_path.exists():
        try:
            emo = json.loads(emotion_path.read_text())
            draft.narrative = {
                "emotion_node": emo.get("emotion_node", ""),
                "emotion_desc": emo.get("emotion_desc", ""),
                "strategy_bias": emo.get("strategy_bias", ""),
                "key_evidence": emo.get("key_evidence", []),
            }
            draft.playbook = {
                "strategy_bias": emo.get("strategy_bias", ""),
                "emotion_score": emo.get("emotion_score", 0),
                "confidence": emo.get("confidence", 0),
            }
        except (json.JSONDecodeError, OSError) as e:
            missing.append(f"emotion_json_error: {e}")
    else:
        missing.append("emotion_json")

    draft.missing_fields = missing
    draft.source_quality = max(0.50, 1.0 - len(missing) * 0.2)

    # Save draft
    path = draft_store.save(draft)

    # Update session
    session = session_store.transition(
        session, WorkbenchStatus.DRAFT_READY,
        draft_version=draft_version,
    )

    print(f"Draft v{draft_version} generated for {trade_date}")
    print(f"  Source quality: {draft.source_quality:.2f}")
    print(f"  Missing fields: {missing if missing else 'none'}")
    print(f"  Session: {session.status}")
    print(f"  Output: {path}")
    return 0


def _build_cognition_cards(charts: list[dict]) -> list[dict]:
    """Build minimal cognition cards from chart data."""
    cards = []
    for c in charts:
        ct = c.get("chart_type", "")
        if ct in ("institution_style", "hot_money_style"):
            directions = c.get("data", {}).get("directions", [])
            for d in directions:
                cards.append({
                    "subject_name": d.get("name", ""),
                    "state": d.get("state", ""),
                    "score": d.get("score", 0),
                    "source_chart": ct,
                })
    return cards


if __name__ == "__main__":
    sys.exit(main())

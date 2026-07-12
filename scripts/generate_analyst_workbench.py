#!/usr/bin/env python3
"""Phase 4.5 T02 — AI Draft Generator for Analyst Workbench.

Usage:
    PYTHONPATH=. python3 scripts/generate_analyst_workbench.py --date 2026-07-09
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

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
    parser.add_argument("--context-file", default=None,
                        help="Draft context JSON path (from DraftContextBuilder)")
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
    skip_fetch = os.environ.get("SPS_SKIP_FETCH") == "1"
    sps_url = "http://127.0.0.1:8090"

    if not chart_path.exists() and not skip_fetch:
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

    if not emotion_path.exists() and not skip_fetch:
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

    if skip_fetch:
        print("Chart/emotion fetch skipped (SPS_SKIP_FETCH=1), reading from disk")

    # ── PR1.1: Load draft context if available ──
    context: dict[str, Any] | None = None
    if args.context_file:
        ctx_path = Path(args.context_file)
        if ctx_path.exists():
            try:
                context = json.loads(ctx_path.read_text(encoding="utf-8"))
                print(f"Draft context loaded: {ctx_path} (sources: {context.get('missing_sources', [])})")
            except Exception as e:
                print(f"  Context load failed: {e}")

    missing: list[str] = []

    if chart_path.exists():
        try:
            charts = json.loads(chart_path.read_text())
            draft.attention_state = {"charts_available": len(charts)}
            draft.cognition_cards = _build_cognition_cards_from_context(context)
            if not draft.cognition_cards:
                print("  Draft context produced no cognition cards; refusing chart-derived fallback")
                return 2
            # Phase 4.5.4: structured chart reviews
            from stock_processing_service.application.services.analyst_workbench.chart_review_builder import (
                ChartReviewBuilder,
            )
            draft.chart_reviews = ChartReviewBuilder().build(charts)
        except (json.JSONDecodeError, OSError) as e:
            missing.append(f"chart_json_error: {e}")
    else:
        missing.append("charts_json")

    if emotion_path.exists():
        try:
            emo = json.loads(emotion_path.read_text())
            # Phase 4.5.4: structured emotion review
            from stock_processing_service.application.services.analyst_workbench.emotion_review_builder import (
                EmotionReviewBuilder,
            )
            draft.emotion_review = EmotionReviewBuilder().build(emo)
            # Keep old narrative/playbook for backward compat
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

    # ── AI tomorrow outlook (derived from chart + emotion) ──
    draft.emotion_review["tomorrow_outlook"] = _derive_tomorrow_outlook(draft.emotion_review, charts)
    draft.emotion_review["tomorrow_watchpoints"] = _derive_watchpoints(draft.emotion_review, charts)
    draft.emotion_review["tomorrow_forbidden"] = _derive_forbidden(draft.emotion_review)

    draft.missing_fields = missing
    draft.source_quality = max(0.50, 1.0 - len(missing) * 0.15)

    # ── PR1.1: context trace (what data the AI saw) ──
    if context:
        draft.attention_state["context_source"] = "draft_context_builder"
        draft.attention_state["context_quality"] = context.get("source_quality", 1.0)
        draft.attention_state["context_missing"] = context.get("missing_sources", [])
        draft.attention_state["context_theme_count"] = len(context.get("themes") or [])
        draft.attention_state["context_strong_stock_count"] = len(context.get("strong_stocks") or [])

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


def _derive_tomorrow_outlook(emo: dict, charts: list[dict]) -> str:
    """AI-derived tomorrow outlook based on current market state."""
    node = emo.get("emotion_node", "")
    score = emo.get("emotion_score", 0) or 0
    strategy = emo.get("strategy_bias", "")

    if node in ("ICE_POINT",):
        return "情绪冰点，明天关注修复信号。若有缩量企稳或深V反转，可左侧轻仓试错。"
    if node in ("DIVERGENCE", "FADE"):
        return "退潮/衰退中，明天继续等待。不抄底、不追高，观察核心是否止跌。"
    if node in ("REBOUND", "REPAIR"):
        return "修复进行中，明天关注持续性。若量能维持、核心不破位，可持有；若冲高回落则减仓。"
    if node in ("FERMENTATION", "ACCELERATION"):
        return "发酵/加速期，明天关注龙头晋级和板块扩散。龙头加速则持有，分歧则观察弱转强信号。"
    if node in ("CLIMAX",):
        return "情绪高潮，明天警惕分歧。不追高位，关注低位补涨方向，高位股只持有不新开。"
    return "市场混沌，明天以观察为主。等待方向明确后再决策。"


def _derive_watchpoints(emo: dict, charts: list[dict]) -> list[str]:
    """AI-derived watchpoints for tomorrow."""
    wps = []
    node = emo.get("emotion_node", "")
    score = emo.get("emotion_score", 0) or 0

    # From chart data
    for c in charts:
        ct = c.get("chart_type", "")
        data = c.get("data") or {}
        if ct == "relay_ecology":
            fb = data.get("feedback_score", 0) or 0
            if fb < -10:
                wps.append("连板反馈偏弱，关注接力生态是否改善")
            elif fb > 0:
                wps.append("连板反馈偏暖，关注龙头是否加速")
        if ct == "active_capital":
            active = data.get("active_amount_yi") or 0
            total = data.get("total_amount_yi") or 1
            if active / max(total, 1) < 0.05:
                wps.append("活跃资金不足，关注量能能否放大")
        if ct == "market_breadth":
            up = data.get("up_count") or 0
            down = data.get("down_count") or 0
            if up < down:
                wps.append("下跌家数多于上涨，关注宽度是否改善")

    if node in ("REBOUND", "REPAIR"):
        wps.append("关注修复能否持续（量能+核心守位）")
    if node in ("CLIMAX",):
        wps.append("关注龙头是否首次分歧")
    if node in ("CHAOS",):
        wps.append("等待市场方向明确")

    return wps[:5]


def _derive_forbidden(emo: dict) -> list[str]:
    """AI-derived forbidden actions for tomorrow."""
    fb = []
    node = emo.get("emotion_node", "")
    score = emo.get("emotion_score", 0) or 0

    if node in ("ICE_POINT", "DIVERGENCE", "FADE"):
        fb.extend(["不追高", "不打高位板", "不重仓"])
    elif node in ("CLIMAX",):
        fb.extend(["不追龙头", "不追高位板", "不新开高位仓位"])
    elif node in ("CHAOS",):
        fb.extend(["不重仓", "不追高"])
    else:
        fb.append("不追高")

    if score < -10:
        fb.append("不左侧抄底")
    return fb[:5]


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


def _build_cognition_cards_from_context(context: dict[str, Any] | None) -> list[dict]:
    """Build cognition cards from Workbench DraftContext.

    Charts are a visualization layer. The Workbench AI draft should prefer
    derived theme entities produced by the post-market derived data pipeline.
    """
    if not context:
        return []
    themes = context.get("themes") or []
    if not isinstance(themes, list):
        return []

    cards: list[dict[str, Any]] = []
    for item in themes:
        if not isinstance(item, dict):
            continue
        subject_key = str(item.get("subject_key") or "")
        subject_name = str(item.get("theme_name") or subject_key)
        if not subject_name:
            continue
        capital = item.get("capital") if isinstance(item.get("capital"), dict) else {}
        top_stocks = capital.get("top_stocks") if isinstance(capital, dict) else []
        evidence_refs = item.get("evidence_refs") or []
        if not isinstance(evidence_refs, list):
            evidence_refs = []
        cards.append({
            "subject_id": f"theme:{subject_key}" if subject_key else f"theme:{subject_name}",
            "subject_key": subject_key,
            "subject_name": subject_name,
            "state": item.get("stage") or item.get("final_cycle_state") or "",
            "role": item.get("role") or "WATCH",
            "score": item.get("mainline_strength_score") or item.get("confidence_score") or 0,
            "capital": capital,
            "drivers": evidence_refs[:5],
            "risk_flags": item.get("risk_flags") or [],
            "state_transition_reason": item.get("state_transition_reason") or "",
            "top_stocks": top_stocks[:5] if isinstance(top_stocks, list) else [],
            "source": "draft_context.derived",
        })
    return cards


if __name__ == "__main__":
    sys.exit(main())

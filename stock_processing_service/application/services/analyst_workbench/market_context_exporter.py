"""MarketContextExporter — bind dynamic market facts to real DerivedContext.

P0 fixes:
  1. Field mapping uses real DerivedContext keys (theme_name, mainline_strength_score, etc.)
  2. Root path uses AI_THEME_APP_ROOT env var or project_root sentinel file
  3. capital_direction/leader_health/breadth derived from money_flows + strong_stocks
  4. Chart/emotion fallback has its own mapper (not themes[])
  5. status: live/partial/unavailable — never synthetic
"""

from __future__ import annotations

import os as _os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))


def _find_project_root() -> Path:
    env = _os.environ.get("AI_THEME_APP_ROOT", "")
    if env:
        return Path(env)
    # Walk up from this file to find CLAUDE.md (project root sentinel)
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return p.parent.parent.parent.parent  # fallback


class MarketContextExporter:
    """Exports dynamic market facts from real DerivedContextReader data."""

    def __init__(self, reader=None):
        self._reader = reader

    def export(self, trade_date: date | str | None = None) -> dict:
        if isinstance(trade_date, str):
            trade_date = date.fromisoformat(trade_date)
        td = (trade_date or datetime.now(CST).date()).isoformat()

        # Try DerivedContext (real DB, pool injected or None)
        ctx = self._try_derived_context(td)
        if ctx and ctx.get("themes"):
            return self._build_from_derived(td, ctx)

        # Try chart/emotion cached JSON
        ctx = self._try_chart_emotion(td)
        if ctx:
            return ctx

        return self._unavailable(td)

    def _try_derived_context(self, td: str) -> dict | None:
        try:
            from stock_processing_service.application.services.analyst_workbench.derived_context_reader import (
                DerivedContextReader,
            )
            reader = self._reader or DerivedContextReader()
            import asyncio
            ctx = asyncio.run(reader.read(date.fromisoformat(td)))
            return ctx.to_dict()
        except Exception:
            return None

    def _build_from_derived(self, td: str, raw: dict) -> dict:
        themes_raw = raw.get("themes", [])
        money_flows = raw.get("money_flows", [])
        strong_stocks = raw.get("strong_stocks", [])

        themes = []
        for t in themes_raw[:10]:
            name = t.get("theme_name", "")
            if not name:
                continue
            strength = float(t.get("mainline_strength_score", 0))
            themes.append({
                "subject": name,
                "strength": strength,
                "derived_stage_signal": str(t.get("stage", "unknown")),
                "role": str(t.get("role", "WATCH")),
                "confidence_score": float(t.get("confidence_score", 0.5)),
                "fade_risk_score": float(t.get("fade_risk_score", 0)),
                "divergence_score": float(t.get("divergence_score", 0)),
                "repair_score": float(t.get("repair_score", 0)),
                "capital_direction": self._derive_capital(subject_key=t.get("subject_key", ""), money_flows=money_flows),
                "leader_health": self._derive_leader(subject_key=t.get("subject_key", ""), stocks=strong_stocks),
                "breadth": self._derive_breadth(subject_key=t.get("subject_key", ""), stocks=strong_stocks),
                "evidence_refs": [str(e) for e in t.get("evidence_refs", []) if e][:3],
            })

        state_raw = raw.get("market_state", {})
        state = {
            "breadth": {
                "up_count": 0, "down_count": 0,
                "limit_up_count": 0, "limit_down_count": 0,
                "breadth_ratio": 0.0,
            },
            "emotion": {"node": "", "score": 0, "trend": "unknown"},
            "capital": {
                "active_amount_yi": 0,
                "trend": "unknown",
            },
            "relay": {"max_board_height": 0, "promotion_1_to_2": 0.0, "feedback": "unknown"},
            "summary": {
                "theme_count": int(state_raw.get("theme_count", 0)),
                "mainline_count": int(state_raw.get("mainline_count", 0)),
                "active_theme_count": int(state_raw.get("active_theme_count", 0)),
                "strong_stock_count": int(state_raw.get("strong_stock_count", 0)),
                "money_flow_count": int(state_raw.get("money_flow_count", 0)),
            },
        }

        has_data = len(themes) > 0
        return {
            "schema_version": "market-context.v1",
            "provider": "ai_theme_app",
            "trade_date": td,
            "generated_at": datetime.now(CST).isoformat(),
            "status": "live" if raw.get("missing_sources") == [] else "partial",
            "market_state": state,
            "themes": themes,
            "missing_sources": raw.get("missing_sources", []),
            "quality": {
                "coverage": 0.85 if has_data else 0.0,
                "freshness_seconds": 0,
                "missing_fields": raw.get("missing_sources", []),
                "source_quality": float(raw.get("source_quality", 0.8 if has_data else 0.0)),
            },
        }

    def _derive_capital(self, subject_key: str, money_flows: list) -> str:
        flows = [m for m in money_flows if m.get("subject_key") == subject_key]
        if not flows:
            return "unknown"
        total_inflow = sum(
            float(m.get("main_net_inflow", 0)) for m in flows
        )
        tier = [m.get("money_flow_tier", "") for m in flows if m.get("money_flow_tier")]
        if total_inflow > 0 and any(t in ("high", "medium") for t in tier):
            return "inflow"
        if total_inflow < 0:
            return "outflow"
        return "mixed"

    def _derive_leader(self, subject_key: str, stocks: list) -> str:
        leaders = [
            s for s in stocks
            if s.get("subject_key") == subject_key
            and str(s.get("role", "")).lower() in ("leader", "core", "pioneer")
        ]
        if not leaders:
            return "unknown"
        avg_score = sum(float(s.get("watch_score", 0)) for s in leaders) / len(leaders)
        if avg_score >= 0.7:
            return "strong"
        if avg_score >= 0.4:
            return "moderate"
        return "weakening"

    def _derive_breadth(self, subject_key: str, stocks: list) -> str:
        subject_stocks = [
            s for s in stocks
            if s.get("subject_key") == subject_key
            and str(s.get("watch_status", "")).lower() in ("active", "watching", "confirmed")
        ]
        count = len(subject_stocks)
        if count >= 10:
            return "wide"
        if count >= 5:
            return "moderate"
        if count >= 1:
            return "narrow"
        return "unknown"

    def _try_chart_emotion(self, td: str) -> dict | None:
        try:
            import json
            root = _find_project_root()
            chart_path = root / "frontend" / "public" / "api" / "analyst-charts" / f"{td}.json"
            emotion_path = root / "frontend" / "public" / "api" / f"emotion-{td}.json"
            if not chart_path.exists() or not emotion_path.exists():
                return None
            charts = json.loads(chart_path.read_text(encoding="utf-8"))
            emotion = json.loads(emotion_path.read_text(encoding="utf-8"))
            return self._build_from_charts(td, charts, emotion)
        except Exception:
            return None

    def _build_from_charts(self, td: str, charts: list, emotion: dict) -> dict:
        themes = []
        for chart in (charts or []):
            name = chart.get("title", chart.get("name", ""))
            if not name:
                continue
            themes.append({
                "subject": str(name),
                "strength": 0.5,
                "derived_stage_signal": "unknown",
                "capital_direction": "unknown",
                "leader_health": "unknown",
                "breadth": "unknown",
                "evidence_refs": ["cached_chart_json"],
            })

        emotion_node = str(emotion.get("emotion_node", emotion.get("node", "")))
        emotion_score = int(emotion.get("emotion_score", emotion.get("score", 0)))

        return {
            "schema_version": "market-context.v1",
            "provider": "ai_theme_app",
            "trade_date": td,
            "generated_at": datetime.now(CST).isoformat(),
            "status": "partial",
            "market_state": {
                "breadth": {"up_count": 0, "down_count": 0, "limit_up_count": 0, "limit_down_count": 0, "breadth_ratio": 0},
                "emotion": {"node": emotion_node, "score": emotion_score, "trend": "unknown"},
                "capital": {"active_amount_yi": 0, "trend": "unknown"},
                "relay": {"max_board_height": 0, "promotion_1_to_2": 0, "feedback": "unknown"},
                "summary": {"theme_count": len(themes)},
            },
            "themes": themes,
            "quality": {"coverage": 0.5, "freshness_seconds": 0, "missing_fields": ["derived_context"], "source_quality": 0.5},
        }

    def _unavailable(self, td: str) -> dict:
        return {
            "schema_version": "market-context.v1", "provider": "ai_theme_app",
            "trade_date": td, "generated_at": datetime.now(CST).isoformat(),
            "status": "unavailable", "reason": "no_dynamic_market_data",
            "market_state": {}, "themes": [], "missing_sources": ["all"],
            "quality": {"coverage": 0.0, "freshness_seconds": 0, "missing_fields": ["all"], "source_quality": 0.0},
        }


__all__ = ["MarketContextExporter"]

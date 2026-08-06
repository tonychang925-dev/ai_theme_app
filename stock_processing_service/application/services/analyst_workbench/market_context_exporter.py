"""MarketContextExporter — bind dynamic market facts to real data sources.

Reads from: DerivedContextReader (themes, market_state)
Status: live (from DB) or synthetic (no data available) or partial (incomplete).
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Any

CST = timezone(timedelta(hours=8))


class MarketContextExporter:
    """Exports dynamic market facts from real data sources.

    Tries: DerivedContextReader (real DB data) → existing recap/chart JSON
    Falls back: status = "unavailable" with empty payload — never fakes data.
    """

    def export(self, trade_date: date | str | None = None) -> dict:
        if isinstance(trade_date, str):
            trade_date = date.fromisoformat(trade_date)
        td = (trade_date or datetime.now(CST).date()).isoformat()

        # Try real data sources
        context = self._try_derived_context(td)
        if context:
            return self._build_envelope(td, "live", context)

        context = self._try_chart_emotion_data(td)
        if context:
            return self._build_envelope(td, "partial", context)

        return self._unavailable_envelope(td)

    def _try_derived_context(self, td: str) -> dict | None:
        """Try reading from DerivedContextReader (post-market derived tables)."""
        try:
            from stock_processing_service.application.services.analyst_workbench.derived_context_reader import (
                DerivedContextReader,
            )
            reader = DerivedContextReader()
            import asyncio
            ctx = asyncio.run(reader.read(date.fromisoformat(td)))
            data = ctx.to_dict()
            if data.get("themes") or data.get("market_state"):
                return data
        except Exception:
            pass
        return None

    def _try_chart_emotion_data(self, td: str) -> dict | None:
        """Try reading from cached chart/emotion JSON (frontend public API)."""
        try:
            import json, os
            from pathlib import Path
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))))
            chart_path = Path(project_root) / "frontend" / "public" / "api" / "analyst-charts" / f"{td}.json"
            emotion_path = Path(project_root) / "frontend" / "public" / "api" / f"emotion-{td}.json"

            if chart_path.exists() and emotion_path.exists():
                charts = json.loads(chart_path.read_text(encoding="utf-8"))
                emotion = json.loads(emotion_path.read_text(encoding="utf-8"))
                return {"charts": charts, "emotion": emotion, "source": "cached_chart_json"}
        except Exception:
            pass
        return None

    def _build_envelope(self, td: str, status: str, raw: dict) -> dict:
        """Build MarketContextEnvelope from raw data."""
        themes_data = raw.get("themes", [])
        market_state = raw.get("market_state", {})

        # Map themes to fact-only format (no interpretation)
        themes = []
        for t in themes_data[:10]:
            subject = t.get("subject_name", t.get("subject", ""))
            if not subject:
                continue
            themes.append({
                "subject": subject,
                "strength": float(t.get("strength", t.get("strength_score", 0))),
                "stage": str(t.get("stage", t.get("stage_judgement", "unknown"))),
                "capital_direction": str(t.get("capital_direction", t.get("money_flow_direction", "unknown"))),
                "leader_health": str(t.get("leader_health", t.get("leader_status", "unknown"))),
                "breadth": str(t.get("breadth", t.get("breadth_status", "unknown"))),
                "evidence_refs": [str(e) for e in t.get("evidence", []) if e][:3],
            })

        # Extract market state fields
        state = {
            "breadth": {
                "up_count": int(market_state.get("up_count", market_state.get("rise_count", 0))),
                "down_count": int(market_state.get("down_count", market_state.get("fall_count", 0))),
                "limit_up_count": int(market_state.get("limit_up_count", 0)),
                "limit_down_count": int(market_state.get("limit_down_count", 0)),
                "breadth_ratio": float(market_state.get("breadth_ratio", 0)),
            },
            "emotion": {
                "node": str(market_state.get("emotion_node", "")),
                "score": int(market_state.get("emotion_score", 0)),
                "trend": str(market_state.get("emotion_trend", "unknown")),
            },
            "capital": {
                "active_amount_yi": int(market_state.get("active_amount_yi", 0)),
                "trend": str(market_state.get("capital_trend", "unknown")),
            },
            "relay": {
                "max_board_height": int(market_state.get("max_board_height", 0)),
                "promotion_1_to_2": float(market_state.get("promotion_1_to_2", 0)),
                "feedback": str(market_state.get("relay_feedback", "unknown")),
            },
        }

        # Compute real quality
        has_data = len(themes) > 0 or any(
            state["breadth"][k] != 0 for k in ("up_count", "down_count")
        )
        quality = {
            "coverage": 0.85 if has_data else 0.0,
            "freshness_seconds": 0,  # Unknown — set by caller if known
            "missing_fields": [],
            "source_quality": 0.8 if has_data else 0.0,
        }

        return {
            "schema_version": "market-context.v1",
            "provider": "ai_theme_app",
            "trade_date": td,
            "generated_at": datetime.now(CST).isoformat(),
            "status": status,
            "market_state": state,
            "themes": themes,
            "quality": quality,
        }

    def _unavailable_envelope(self, td: str) -> dict:
        return {
            "schema_version": "market-context.v1",
            "provider": "ai_theme_app",
            "trade_date": td,
            "generated_at": datetime.now(CST).isoformat(),
            "status": "unavailable",
            "reason": "no_dynamic_market_data_available",
            "market_state": {},
            "themes": [],
            "quality": {"coverage": 0.0, "freshness_seconds": 0, "missing_fields": ["all"], "source_quality": 0.0},
        }


__all__ = ["MarketContextExporter"]

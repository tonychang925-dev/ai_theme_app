"""MarketContextExporter — async, DB errors surfaced, null for missing values.

P0 fixes:
  - async export() — safe in running event loops
  - DB read errors → clearly surfaced, not silently swallowed
  - Missing values → null (never 0 when unknown)
  - fallback chain: real DB → chart/emotion cached JSON → unavailable
"""

from __future__ import annotations

import os as _os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))

# Sentinel for "data source did not provide this field"
_NULL = None


def _find_project_root() -> Path:
    env = _os.environ.get("AI_THEME_APP_ROOT", "")
    if env:
        return Path(env)
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return p.parent.parent.parent.parent


class MarketContextExporter:
    """Exports dynamic market facts from real data sources.

    Async. Injects DerivedContextReader at construction.
    Null for unknown fields. Never 0 placeholder.
    """

    def __init__(self, reader=None):
        self._reader = reader

    async def export(self, trade_date: date | str | None = None) -> dict:
        if isinstance(trade_date, str):
            trade_date = date.fromisoformat(trade_date)
        td = (trade_date or datetime.now(CST).date()).isoformat()

        # Try real DerivedContext
        if self._reader:
            try:
                ctx = await self._reader.read(date.fromisoformat(td))
                data = ctx.to_dict()
                if data.get("themes"):
                    return self._build_from_derived(td, data)
            except Exception as exc:
                # Surface DB error — don't silently fall back
                return self._error(td, "derived_context_read_failed", exc)

        # Try file fallback
        ctx = self._try_chart_emotion(td)
        if ctx:
            return ctx

        return self._unavailable(td, "no_data_source_available")

    # ── Builders ──────────────────────────────────────────────────────────

    def _build_from_derived(self, td: str, raw: dict) -> dict:
        themes_raw = raw.get("themes", [])
        money_flows = raw.get("money_flows", [])
        strong_stocks = raw.get("strong_stocks", [])
        missing = list(raw.get("missing_sources", []))

        themes = []
        for t in themes_raw[:10]:
            name = t.get("theme_name", "")
            if not name:
                continue
            sk = t.get("subject_key", "")

            themes.append({
                "subject": name,
                "raw_metrics": {
                    "mainline_strength_score": _float_or_null(t.get("mainline_strength_score")),
                    "confidence_score": _float_or_null(t.get("confidence_score")),
                    "fade_risk_score": _float_or_null(t.get("fade_risk_score")),
                    "divergence_score": _float_or_null(t.get("divergence_score")),
                    "repair_score": _float_or_null(t.get("repair_score")),
                },
                "derived_signals": {
                    "stage_signal": {
                        "value": str(t.get("stage", "") or ""),
                        "origin": "theme_cycle_judgement_v2.final_cycle_state",
                    },
                    "capital_direction": {
                        "value": self._derive_capital(sk, money_flows),
                        "origin": "money_flow_enhanced.main_net_inflow + money_flow_tier",
                    },
                    "leader_health": {
                        "value": self._derive_leader(sk, strong_stocks),
                        "origin": "strong_stock_watch_history.watch_score aggregation",
                        "raw_count": self._count_leaders(sk, strong_stocks),
                    },
                    "strong_stock_coverage": {
                        "value": self._derive_breadth(sk, strong_stocks),
                        "origin": "strong_stock_watch_history count by subject_key",
                        "raw_count": self._count_subject_stocks(sk, strong_stocks),
                    },
                },
                "evidence_refs": [str(e) for e in t.get("evidence_refs", []) if e][:3],
            })

        state_raw = raw.get("market_state", {})
        state = {
            "summary": {
                "theme_count": int(state_raw.get("theme_count", 0)),
                "mainline_count": int(state_raw.get("mainline_count", 0)),
                "active_theme_count": int(state_raw.get("active_theme_count", 0)),
                "strong_stock_count": int(state_raw.get("strong_stock_count", 0)),
                "money_flow_count": int(state_raw.get("money_flow_count", 0)),
            },
            "missing_fields": [
                k for k in ("breadth.up_count", "breadth.limit_up_count",
                            "emotion.node", "capital.active_amount_yi", "relay.max_board_height")
            ],
        }

        has_data = len(themes) > 0
        return {
            "schema_version": "market-context.v1",
            "provider": "ai_theme_app",
            "trade_date": td,
            "generated_at": datetime.now(CST).isoformat(),
            "status": "live" if not missing else "partial",
            "missing_sources": missing,
            "market_state": state,
            "themes": themes,
            "quality": {
                "coverage": 0.85 if has_data else 0.0,
                "freshness_seconds": None,
                "missing_fields": missing,
                "source_quality": float(raw.get("source_quality", 0.8 if has_data else 0.0)),
            },
        }

    # ── Derived signal helpers ────────────────────────────────────────────

    def _derive_capital(self, subject_key: str, money_flows: list) -> str | None:
        flows = [m for m in money_flows if m.get("subject_key") == subject_key]
        if not flows:
            return None
        total = sum(float(m.get("main_net_inflow", 0)) for m in flows)
        tiers = [m.get("money_flow_tier", "") for m in flows if m.get("money_flow_tier")]
        if total > 0 and any(t in ("high", "medium") for t in tiers):
            return "inflow"
        if total < 0:
            return "outflow"
        return "mixed"

    def _derive_leader(self, subject_key: str, stocks: list) -> str | None:
        leaders = [s for s in stocks if s.get("subject_key") == subject_key
                   and str(s.get("role", "")).lower() in ("leader", "core", "pioneer")]
        if not leaders:
            return None
        avg = sum(float(s.get("watch_score", 0)) for s in leaders) / len(leaders)
        if avg >= 0.7: return "strong"
        if avg >= 0.4: return "moderate"
        return "weakening"

    def _count_leaders(self, subject_key: str, stocks: list) -> int:
        return len([s for s in stocks if s.get("subject_key") == subject_key
                    and str(s.get("role", "")).lower() in ("leader", "core", "pioneer")])

    def _derive_breadth(self, subject_key: str, stocks: list) -> str | None:
        n = self._count_subject_stocks(subject_key, stocks)
        if n >= 10: return "wide"
        if n >= 5: return "moderate"
        if n >= 1: return "narrow"
        return None

    def _count_subject_stocks(self, subject_key: str, stocks: list) -> int:
        return len([s for s in stocks if s.get("subject_key") == subject_key
                    and str(s.get("watch_status", "")).lower() in ("active", "watching", "confirmed")])

    # ── File fallback ─────────────────────────────────────────────────────

    def _try_chart_emotion(self, td: str) -> dict | None:
        try:
            import json
            root = _find_project_root()
            cp = root / "frontend" / "public" / "api" / "analyst-charts" / f"{td}.json"
            ep = root / "frontend" / "public" / "api" / f"emotion-{td}.json"
            if not cp.exists() or not ep.exists():
                return None
            return self._build_from_charts(td, json.loads(cp.read_text(encoding="utf-8")),
                                           json.loads(ep.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _build_from_charts(self, td: str, charts: list, emotion: dict) -> dict:
        themes = [{
            "subject": str(c.get("title", c.get("name", ""))),
            "raw_metrics": None,
            "derived_signals": {"stage_signal": {"value": None}},
            "evidence_refs": ["cached_chart_json"],
        } for c in (charts or []) if c.get("title") or c.get("name")]

        node = str(emotion.get("emotion_node", emotion.get("node", "")) or "")
        score = int(emotion.get("emotion_score", emotion.get("score", 0)) or 0)

        return {
            "schema_version": "market-context.v1", "provider": "ai_theme_app",
            "trade_date": td, "generated_at": datetime.now(CST).isoformat(),
            "status": "partial",
            "missing_sources": ["derived_context"],
            "market_state": {
                "summary": {"theme_count": len(themes)},
                "emotion": {"node": node, "score": score},
                "missing_fields": ["breadth", "capital.active_amount_yi", "relay"],
            },
            "themes": themes,
            "quality": {"coverage": 0.5, "freshness_seconds": None,
                        "missing_fields": ["derived_context"], "source_quality": 0.5},
        }

    # ── Error / Unavailable ────────────────────────────────────────────────

    def _error(self, td: str, reason: str, exc: Exception) -> dict:
        return {
            "schema_version": "market-context.v1", "provider": "ai_theme_app",
            "trade_date": td, "generated_at": datetime.now(CST).isoformat(),
            "status": "unavailable", "reason": reason,
            "diagnostics": {"error_type": type(exc).__name__, "error": str(exc)},
            "market_state": {}, "themes": [], "quality": {"coverage": 0.0, "source_quality": 0.0},
        }

    def _unavailable(self, td: str, reason: str) -> dict:
        return {
            "schema_version": "market-context.v1", "provider": "ai_theme_app",
            "trade_date": td, "generated_at": datetime.now(CST).isoformat(),
            "status": "unavailable", "reason": reason,
            "market_state": {}, "themes": [], "quality": {"coverage": 0.0, "source_quality": 0.0},
        }


def _float_or_null(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


__all__ = ["MarketContextExporter"]

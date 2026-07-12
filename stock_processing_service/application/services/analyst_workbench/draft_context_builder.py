"""Phase 4.5.6 PR1.1 — DraftContextBuilder.

Packages derived data (market metrics, emotion, charts, themes, stocks)
into a structured AnalystDraftContext. This closes the gap where the AI
draft generator was reading chart/emotion JSON from disk without the full
derived data context.

The context JSON is written alongside the draft so the CLI can consume it
without re-querying the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .derived_context_reader import WorkbenchDerivedContext


@dataclass
class AnalystDraftContext:
    """Structured context for AI draft generation.

    Contains all the market data the AI needs to produce a meaningful draft.
    No DB access, no LLM calls, no recalculation — pure data packaging.
    """

    trade_date: str

    # ── Market state (from metrics + emotion) ──
    market_state: dict[str, Any] = field(default_factory=dict)

    # ── Emotion (from emotion JSON) ──
    emotion_state: dict[str, Any] = field(default_factory=dict)

    # ── Chart reviews (from chart JSON) ──
    chart_reviews: list[dict[str, Any]] = field(default_factory=list)

    # ── Evidence trend series (from snapshot adapter inputs) ──
    trend_data: dict[str, Any] = field(default_factory=dict)

    # ── Capital state (from metrics) ──
    capital_state: dict[str, Any] = field(default_factory=dict)

    # ── Themes (from chart directions + cognition) ──
    themes: list[dict[str, Any]] = field(default_factory=list)

    # ── Strong stocks (from chart leader data) ──
    strong_stocks: list[dict[str, Any]] = field(default_factory=list)

    # ── Limit-up classifications (from structured limit-up source) ──
    limit_up: dict[str, Any] = field(default_factory=dict)

    # ── Plan state (from PlanSnapshotProducer) ──
    plan_state: dict[str, Any] = field(default_factory=dict)

    # ── Risk signals ──
    risk_signals: list[str] = field(default_factory=list)

    # ── Source quality ──
    source_quality: float = 1.0
    missing_sources: list[str] = field(default_factory=list)
    quality: str = "GOOD"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "market_state": self.market_state,
            "emotion_state": self.emotion_state,
            "chart_reviews": self.chart_reviews,
            "trend_data": self.trend_data,
            "capital_state": self.capital_state,
            "themes": self.themes,
            "strong_stocks": self.strong_stocks,
            "limit_up": self.limit_up,
            "plan_state": self.plan_state,
            "risk_signals": self.risk_signals,
            "source_quality": self.source_quality,
            "missing_sources": self.missing_sources,
            "quality": self.quality,
            "warnings": self.warnings,
            "counts": {
                "themes": len(self.themes),
                "strong_stocks": len(self.strong_stocks),
                "money_flows": int((self.capital_state or {}).get("stock_count") or 0),
                "charts": len(self.chart_reviews),
            },
        }


class DraftContextBuilder:
    """Build AnalystDraftContext from already-generated data files.

    Reads chart JSON, emotion JSON, and optionally metrics snapshot to
    assemble a complete context for AI draft generation.

    This is NOT a data producer — it only assembles existing outputs.
    """

    def __init__(self, project_root: Path | str = "."):
        self._root = Path(project_root)

    def build(
        self,
        trade_date: date | str,
        chart_json: dict | None = None,
        emotion_json: dict | None = None,
        derived_context: WorkbenchDerivedContext | dict[str, Any] | None = None,
        trend_data: dict[str, Any] | None = None,
    ) -> AnalystDraftContext:
        """Build the draft context from available data.

        Args:
            trade_date: Trading date.
            chart_json: Pre-loaded chart data (avoids file re-read).
            emotion_json: Pre-loaded emotion data (avoids file re-read).

        Returns:
            AnalystDraftContext ready for AI draft generation.
        """
        td_str = trade_date.isoformat() if isinstance(trade_date, date) else trade_date
        missing: list[str] = []

        # ── Load chart data ──
        charts: list[dict[str, Any]] = []
        if chart_json is not None:
            charts = chart_json if isinstance(chart_json, list) else []
        else:
            chart_path = self._root / "frontend" / "public" / "api" / "analyst-charts" / f"{td_str}.json"
            if chart_path.exists():
                try:
                    charts = json.loads(chart_path.read_text(encoding="utf-8"))
                except Exception:
                    missing.append("charts_json")
            else:
                missing.append("charts_json")

        # ── Load emotion data ──
        emotion: dict[str, Any] = {}
        if emotion_json is not None:
            emotion = emotion_json if isinstance(emotion_json, dict) else {}
        else:
            emotion_path = self._root / "frontend" / "public" / "api" / f"emotion-{td_str}.json"
            if emotion_path.exists():
                try:
                    emotion = json.loads(emotion_path.read_text(encoding="utf-8"))
                except Exception:
                    missing.append("emotion_json")
            else:
                missing.append("emotion_json")

        derived = _derived_to_dict(derived_context)

        # ── Market state (from derived context + emotion + chart data) ──
        market_state = self._build_market_state(emotion, charts, derived)

        # ── Emotion state (from emotion JSON directly) ──
        emotion_state = self._build_emotion_state(emotion)

        # ── Chart reviews (pass-through from chart JSON) ──
        chart_reviews = charts

        # ── Trend data (snapshot-scoped evidence series) ──
        trend_data = self._build_trend_data(trend_data, derived)

        # ── Capital state (from derived money flow + chart active_capital) ──
        capital_state = self._build_capital_state(charts, emotion, derived)

        # ── Themes (derived tables only) ──
        themes = self._build_themes(charts, derived)

        # ── Strong stocks (derived tables only) ──
        strong_stocks = self._build_strong_stocks(charts, derived)

        # ── Limit-up categories (structured source only) ──
        limit_up = self._build_limit_up(charts, derived)

        # ── Plan state (from PlanSnapshotProducer, not derived inline) ──
        from .plan_snapshot_producer import PlanSnapshotProducer
        plan_state = PlanSnapshotProducer().produce(emotion_state, themes)

        # ── Risk signals ──
        risk_signals = self._build_risk_signals(emotion, charts)

        missing.extend(str(x) for x in derived.get("missing_sources", []) if x)
        derived_quality = float(derived.get("source_quality", 1.0) or 1.0)
        quality = min(derived_quality, max(0.50, 1.0 - len(missing) * 0.15))
        quality_label, warnings = self._quality_label(themes, strong_stocks)

        return AnalystDraftContext(
            trade_date=td_str,
            market_state=market_state,
            emotion_state=emotion_state,
            chart_reviews=chart_reviews,
            trend_data=trend_data,
            capital_state=capital_state,
            themes=themes,
            strong_stocks=strong_stocks,
            limit_up=limit_up,
            plan_state=plan_state,
            risk_signals=risk_signals,
            source_quality=quality,
            missing_sources=missing,
            quality=quality_label,
            warnings=warnings,
        )

    # ── private builders ──

    @staticmethod
    def _build_market_state(emotion: dict, charts: list[dict], derived: dict[str, Any]) -> dict[str, Any]:
        """Assemble market state from emotion + breadth/relay charts."""
        facts: dict[str, Any] = dict(derived.get("market_state") or {})
        for chart in charts:
            ct = chart.get("chart_type", "")
            metrics = chart.get("key_metrics") or chart.get("data") or {}
            if ct == "market_breadth":
                facts["up_count"] = _nullable_metric(metrics.get("up_count"))
                facts["down_count"] = _nullable_metric(metrics.get("down_count"))
                facts["limit_up_count"] = metrics.get("limit_up_count")
                facts["limit_down_count"] = metrics.get("limit_down_count")
            elif ct == "active_capital":
                facts["active_amount_yi"] = metrics.get("active_amount_yi")
                facts["total_amount_yi"] = metrics.get("total_amount_yi")
            elif ct == "relay_ecology":
                facts["max_board_height"] = metrics.get("max_board_height")
                facts["promotion_1_to_2"] = metrics.get("promotion_1_to_2")
                facts["feedback_score"] = metrics.get("feedback_score")

        return {
            "emotion_node": emotion.get("emotion_node", ""),
            "emotion_score": emotion.get("emotion_score", 0) or 0,
            "breadth_score": emotion.get("breadth_score", 0) or 0,
            "breadth_label": emotion.get("breadth_label", ""),
            "momentum_score": emotion.get("momentum_score", 0) or 0,
            "relay_score": emotion.get("relay_score", 0) or 0,
            "capital_score": emotion.get("capital_score", 0) or 0,
            "facts": facts,
            "key_evidence": emotion.get("key_evidence") or [],
        }

    @staticmethod
    def _build_emotion_state(emotion: dict) -> dict[str, Any]:
        """Extract emotion state from emotion JSON."""
        return {
            "emotion_node": emotion.get("emotion_node", ""),
            "emotion_label": emotion.get("emotion_desc", ""),
            "emotion_score": emotion.get("emotion_score", 0) or 0,
            "confidence": min(max(emotion.get("confidence", 0.5) or 0.5, 0.0), 1.0),
            "strategy_bias": emotion.get("strategy_bias", ""),
            "risk_level": emotion.get("risk_level", ""),
            "key_evidence": emotion.get("key_evidence") or [],
        }

    @staticmethod
    def _build_capital_state(charts: list[dict], emotion: dict, derived: dict[str, Any]) -> dict[str, Any]:
        """Extract capital state from active_capital chart + emotion."""
        capital_state: dict[str, Any] = {}
        for chart in charts:
            if chart.get("chart_type") == "active_capital":
                metrics = chart.get("key_metrics") or chart.get("data") or {}
                active_amount = metrics.get("active_amount_yi")
                capital_state.update({
                    "active_amount": active_amount,
                    "active_amount_yi": active_amount,
                    "total_amount_yi": metrics.get("total_amount_yi"),
                    "status": chart.get("status", ""),
                })
                break

        institution = DraftContextBuilder._style_directions(charts, "institution_style")
        hot_money = DraftContextBuilder._style_directions(charts, "hot_money_style")

        money_flows = derived.get("money_flows") or []

        # PR4.2.16: when chart directions are empty, build from money_flow role_label data.
        # This is not inference — money_flow rows are already annotated with institution/hot_money
        # labels by the derived data pipeline (money_flow_enhanced table).
        if not institution and money_flows:
            institution = _capital_direction_from_flows(money_flows, "institution")
        if not hot_money and money_flows:
            hot_money = _capital_direction_from_flows(money_flows, "hot_money")

        if institution:
            capital_state["institution"] = institution
        if hot_money:
            capital_state["hot_money"] = hot_money

        if money_flows:
            net = sum(float(item.get("main_net_inflow") or 0) for item in money_flows if isinstance(item, dict))
            capital_state.update({
                "main_net_inflow": net,
                "stock_count": len(money_flows),
                "status": "derived_money_flow",
                "top_stocks": money_flows[:10],
            })
            return capital_state

        if capital_state:
            return capital_state

        return {
            "active_amount": None,
            "active_amount_yi": None,
            "total_amount_yi": None,
            "status": "",
        }

    @staticmethod
    def _style_directions(charts: list[dict], chart_type: str) -> list[dict[str, Any]]:
        for chart in charts:
            if chart.get("chart_type") != chart_type:
                continue
            data = chart.get("key_metrics") or chart.get("data") or {}
            directions = data.get("directions") if isinstance(data, dict) else []
            if not isinstance(directions, list):
                return []
            rows: list[dict[str, Any]] = []
            for item in directions:
                if not isinstance(item, dict):
                    continue
                rows.append({
                    "theme_name": item.get("name") or item.get("theme_name") or "",
                    "state": item.get("state") or "",
                    "score": item.get("score"),
                    "source": chart_type,
                })
            return rows
        return []

    @staticmethod
    def _build_themes(charts: list[dict], derived: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract theme directions from derived tables only."""
        derived_themes = derived.get("themes") or []
        if derived_themes:
            money_by_subject: dict[str, list[dict[str, Any]]] = {}
            for flow in derived.get("money_flows") or []:
                if isinstance(flow, dict):
                    money_by_subject.setdefault(str(flow.get("subject_key") or ""), []).append(flow)
            themes = []
            for theme in derived_themes:
                if not isinstance(theme, dict):
                    continue
                subject_key = str(theme.get("subject_key") or "")
                capital_rows = money_by_subject.get(subject_key, [])
                themes.append({
                    **theme,
                    "source": "derived_context",
                    "capital": {
                        "stock_count": len(capital_rows),
                        "top_stocks": capital_rows[:5],
                    },
                })
            return themes

        return []

    @staticmethod
    def _build_strong_stocks(charts: list[dict], derived: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract strong stock data from derived tables only."""
        derived_stocks = derived.get("strong_stocks") or []
        if derived_stocks:
            return [item for item in derived_stocks if isinstance(item, dict)]
        return []

    @staticmethod
    def _build_trend_data(prebuilt_trend: dict[str, Any] | None, derived: dict[str, Any]) -> dict[str, Any]:
        """Pass through historical trend evidence from an upstream producer."""
        if isinstance(prebuilt_trend, dict) and prebuilt_trend:
            return prebuilt_trend
        existing = derived.get("trend_data")
        if isinstance(existing, dict) and existing:
            return existing
        return {}

    @staticmethod
    def _build_limit_up(charts: list[dict], derived: dict[str, Any]) -> dict[str, Any]:
        """Build limit-up categories from a structured limit-up source only."""
        existing = derived.get("limit_up")
        if isinstance(existing, dict) and existing:
            return existing

        for chart in charts:
            if chart.get("chart_type") != "limitup_classification":
                continue
            data = chart.get("key_metrics") or chart.get("data") or {}
            if not isinstance(data, dict):
                return {}
            return {
                "total": data.get("limit_up_count"),
                "categories": _limit_up_categories(data.get("categories")),
                "source": "chart.limitup_classification",
            }
        return {}

    @staticmethod
    def _build_risk_signals(emotion: dict, charts: list[dict]) -> list[str]:
        """Aggregate risk signals from emotion + charts."""
        signals: list[str] = []
        risk = emotion.get("risk_level", "")
        if risk in ("HIGH", "EXTREME"):
            signals.append(f"风险等级: {risk}")
        for chart in charts:
            status = chart.get("status", "")
            ct = chart.get("chart_type", "")
            if ct == "relay_ecology" and status in ("恶化",):
                signals.append(f"接力生态恶化")
            elif ct == "market_breadth" and status in ("收缩",):
                signals.append("市场宽度收缩")
        return signals

    @staticmethod
    def _quality_label(themes: list[dict[str, Any]], strong_stocks: list[dict[str, Any]]) -> tuple[str, list[str]]:
        warnings: list[str] = []
        if not themes:
            warnings.append("derived themes are empty")
        if not strong_stocks:
            warnings.append("derived strong stocks are empty")
        if not themes and not strong_stocks:
            return "FAILED", warnings
        if warnings:
            return "DEGRADED", warnings
        return "GOOD", warnings


def write_context_file(context: AnalystDraftContext, output_dir: Path | str) -> Path:
    """Write context JSON to the workbench directory for CLI consumption."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ctx_path = out / "draft_context.json"
    ctx_path.write_text(
        json.dumps(context.to_dict(), ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return ctx_path


def _derived_to_dict(value: WorkbenchDerivedContext | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, WorkbenchDerivedContext):
        return value.to_dict()
    return value if isinstance(value, dict) else {}


def _capital_direction_from_flows(
    money_flows: list[dict[str, Any]], direction_type: str
) -> list[dict[str, Any]]:
    """Build institution/hot_money direction from money_flow role_label annotations.

    The money_flow_enhanced table already carries role_label (机构/游资),
    institution_seat_count, and dragon_tiger_net_amount. This function filters
    and groups by theme — no inference, no guessing.
    """
    seen_themes: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in money_flows:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role_label") or "").strip()
        inst_seats = int(item.get("institution_seat_count") or 0)
        dt_amount = float(item.get("dragon_tiger_net_amount") or 0)

        if direction_type == "institution":
            if not (role == "机构" or inst_seats > 0):
                continue
        else:  # hot_money
            if not (role == "游资" or dt_amount != 0):
                continue

        theme = str(item.get("theme_name") or "")
        if not theme or theme in seen_themes:
            continue
        seen_themes.add(theme)
        rows.append({
            "theme_name": theme,
            "state": role,
            "score": float(item.get("composite_score") or 0),
            "source": "money_flow_enhanced",
        })
    return rows


def _nullable_metric(value: Any) -> Any:
    """Return None only for truly missing values, not for valid zeroes.

    In financial market data, 0 is a valid value (e.g. zero limit-downs,
    zero net flow). Only None and empty string indicate missing data.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _limit_up_categories(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []

    rows: list[dict[str, Any]] = []
    for key, raw in value.items():
        if isinstance(raw, dict):
            rows.append({
                "theme_key": raw.get("theme_key") or key,
                "theme_name": raw.get("theme_name") or raw.get("name") or key,
                "count": raw.get("count") or raw.get("limit_up_count"),
                "stocks": raw.get("stocks") or [],
            })
        else:
            rows.append({
                "theme_key": str(key),
                "theme_name": str(key),
                "count": raw,
                "stocks": [],
            })
    return rows

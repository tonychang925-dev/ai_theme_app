"""FormalReviewProjectionCompiler — PR2.1 (metadata + executive_summary + market_state).

Converts multiple cognitive sources into a single formal_review projection.

CRITICAL BOUNDARY — The compiler MUST NOT:
  - Query the database
  - Call LLM models
  - Recalculate indicators (emotion scores, breadth metrics, etc.)
  - Modify the ReviewSnapshot or engine_report inputs

It ONLY does:
  - Field merge (FACT/ASSESSMENT/PLAN/AUDIT rules)
  - Schema mapping & rename
  - Conflict resolution
  - Grouping & deduplication

Usage:
    compiler = FormalReviewProjectionCompiler()
    projection = compiler.compile(
        trade_date="2026-07-09",
        engine_report={...},
        snapshot=review_snapshot,
        snapshot_meta={...},
        source_info={...},
        theme_name_map={...},
    )
    # projection["formal_review"] contains the 6-chapter projection
    # projection["metadata"] contains metadata
    # projection["evidence_appendix"] contains raw evidence
    # projection["diagnostics"] contains diagnostics
    # Old fields are preserved via the caller (dual-track)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from .projections import (
    capital_evidence,
    evidence_charts,
    executive_summary,
    market_state,
    metadata,
    next_day_plan,
    stock_structure,
    theme_structure,
)


@dataclass(frozen=True, slots=True)
class FormalReviewProjection:
    """The compiled formal review projection.

    Contains exactly 5 top-level objects:
      - metadata
      - formal_review (6 chapters)
      - evidence_appendix
      - diagnostics
      - compatibility (legacy fields, managed by caller)
    """

    trade_date: str
    generated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
    formal_review: dict[str, Any] = field(default_factory=dict)
    evidence_appendix: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the 5-object top-level structure."""
        return {
            "metadata": self.metadata,
            "formal_review": self.formal_review,
            "evidence_appendix": self.evidence_appendix,
            "diagnostics": self.diagnostics,
        }


class FormalReviewProjectionCompiler:
    """Compile cognitive sources into a formal review projection.

    Does NOT query DB, call LLM, recalculate, or modify inputs.
    """

    def __init__(self) -> None:
        self._projection_version = "1.0"

    def compile(
        self,
        *,
        trade_date: date | str,
        engine_report: dict[str, Any] | None = None,
        snapshot: Any | None = None,  # ReviewSnapshot
        snapshot_meta: dict[str, Any] | None = None,
        source_info: dict[str, Any] | None = None,
        theme_name_map: dict[str, str] | None = None,
        generated_at: datetime | None = None,
        snapshot_version: str | None = None,
        # Builder theme fields (for Subject Union)
        builder_theme_reviews: list[dict[str, Any]] | None = None,
        builder_theme_capital_reviews: list[dict[str, Any]] | None = None,
        # Builder stock fields (for entity merge)
        builder_strong_stock_reviews: list[dict[str, Any]] | None = None,
        builder_watchlist_reviews: list[dict[str, Any]] | None = None,
        # Builder capital/plan fields (for PR2.3 projections)
        builder_stock_capital_reviews: list[dict[str, Any]] | None = None,
        builder_money_flow_reviews: list[dict[str, Any]] | None = None,
        builder_dragon_tiger_reviews: list[dict[str, Any]] | None = None,
        builder_abnormal_reviews: list[dict[str, Any]] | None = None,
        builder_post_market_setup_plan: dict[str, Any] | None = None,
        builder_trading_principle: dict[str, Any] | None = None,
    ) -> FormalReviewProjection:
        """Compile all sources into a FormalReviewProjection.

        Args:
            trade_date: Trading date.
            engine_report: Full engine report from PostMarketEngineReportComposer.
            snapshot: Approved ReviewSnapshot (or None for preview).
            snapshot_meta: Approval metadata dict.
            source_info: Source info from builder.
            theme_name_map: Subject key → display name map.
            generated_at: Optional generation timestamp.
            snapshot_version: Optional version string.

        Returns:
            FormalReviewProjection with all 5 top-level objects populated.
        """
        td_str = trade_date.isoformat() if isinstance(trade_date, date) else trade_date
        gen_at = generated_at or datetime.now(timezone.utc)
        gen_at_str = gen_at.isoformat()
        snap_ver = snapshot_version or f"formal_review.{td_str}.{uuid4().hex[:8]}"

        engine = engine_report or {}

        # ── Extract snapshot fields ──
        snap_emotion: dict[str, Any] = {}
        snap_narrative: dict[str, Any] = {}
        snap_playbook: dict[str, Any] = {}
        snap_cognition_cards: list[dict[str, Any]] = []
        snap_chart_reviews: list[dict[str, Any]] = []

        if snapshot is not None:
            snap_emotion = getattr(snapshot, "emotion_review", {}) or {}
            snap_narrative = getattr(snapshot, "narrative", {}) or {}
            snap_playbook = getattr(snapshot, "playbook", {}) or {}
            snap_cognition_cards = getattr(snapshot, "cognition_cards", []) or []
            snap_chart_reviews = getattr(snapshot, "chart_reviews", []) or []

        # ── Metadata ──
        meta = metadata.project_metadata(
            trade_date=td_str,
            engine_report=engine,
            snapshot_meta=snapshot_meta,
            source_info=source_info,
            theme_name_map=theme_name_map,
            generated_at=gen_at_str,
            snapshot_version=snap_ver,
        )

        # ── Formal Review (6 chapters) ──
        formal_review: dict[str, Any] = {
            "version": self._projection_version,
            "executive_summary": executive_summary.project_executive_summary(
                engine_report=engine,
                snapshot_emotion=snap_emotion,
                snapshot_narrative=snap_narrative,
                snapshot_cognition_cards=snap_cognition_cards,
                theme_reviews=builder_theme_reviews,
                name_map=theme_name_map,
            ),
            "market_state": market_state.project_market_state(
                engine_report=engine,
                snapshot_emotion=snap_emotion,
                snapshot_chart_reviews=snap_chart_reviews,
            ),
            "theme_structure": theme_structure.project_theme_structure(
                engine_report=engine,
                snapshot_cognition_cards=snap_cognition_cards,
                builder_theme_reviews=builder_theme_reviews,
                builder_theme_capital_reviews=builder_theme_capital_reviews,
                theme_name_map=theme_name_map,
            ),
            "stock_structure": stock_structure.project_stock_structure(
                engine_report=engine,
                builder_strong_stock_reviews=builder_strong_stock_reviews,
                builder_watchlist_reviews=builder_watchlist_reviews,
            ),
            "capital_evidence": capital_evidence.project_capital_evidence(
                engine_report=engine,
                builder_theme_capital_reviews=builder_theme_capital_reviews,
                builder_stock_capital_reviews=builder_stock_capital_reviews,
                builder_money_flow_reviews=builder_money_flow_reviews,
                builder_dragon_tiger_reviews=builder_dragon_tiger_reviews,
                builder_abnormal_reviews=builder_abnormal_reviews,
            ),
            "next_day_plan": next_day_plan.project_next_day_plan(
                engine_report=engine,
                snapshot_emotion=snap_emotion,
                snapshot_playbook=snap_playbook,
                builder_watchlist_reviews=builder_watchlist_reviews,
                builder_post_market_setup_plan=builder_post_market_setup_plan,
                builder_trading_principle=builder_trading_principle,
            ),
        }

        # ── Evidence Charts (PR-S2) ──
        formal_charts = evidence_charts.project_evidence_charts(
            engine_report=engine,
            snapshot_emotion=snap_emotion,
            snapshot_chart_reviews=snap_chart_reviews,
        )
        formal_review["evidence_charts"] = formal_charts

        # ── Evidence Appendix ──
        appendix = self._build_evidence_appendix(engine, snap_chart_reviews)

        # ── Diagnostics ──
        diagnostics = self._build_diagnostics(engine)

        return FormalReviewProjection(
            trade_date=td_str,
            generated_at=gen_at_str,
            metadata=meta,
            formal_review=formal_review,
            evidence_appendix=appendix,
            diagnostics=diagnostics,
        )

    # ── private ──

    @staticmethod
    def _build_evidence_appendix(
        engine: dict[str, Any],
        chart_reviews: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build evidence_appendix from engine report + chart details."""
        return {
            "limit_up_ladder": engine.get("limit_up_ladder") or {},
            "limit_up_theme_matrix": engine.get("limit_up_theme_matrix") or {},
            "limit_up_theme_events": engine.get("limit_up_theme_events") or {},
            "new_high_summary": engine.get("new_high_summary") or {},
            "chart_details": chart_reviews,
            "d1_narrative": engine.get("d1_narrative") or {},
        }

    @staticmethod
    def _build_diagnostics(engine: dict[str, Any]) -> dict[str, Any]:
        """Build diagnostics from engine report metadata."""
        engine_summary = engine.get("engine_summary") or {}
        regime = engine.get("market_regime_review") or {}
        index_tech = engine.get("index_technical_reviews") or []

        return {
            "allow_trade": engine_summary.get("allow_trade"),
            "trade_mode": engine_summary.get("trade_mode"),
            "index_data_ready": regime.get("index_data_ready", False),
            "index_data_source": regime.get("index_data_source", ""),
            "index_count": len(index_tech),
            "engine_report_available": bool(engine),
        }

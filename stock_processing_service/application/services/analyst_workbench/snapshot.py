"""Phase 4.5 T01 — Review Snapshot model + store."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ReviewSnapshot:
    trade_date: date
    snapshot_version: int = 1
    based_on_draft_version: int = 0
    approved: bool = False
    approved_at: str = ""
    approved_by: str = ""
    approval_mode: str = "preview"
    source_mode: str = "preview"
    composition_mode: str = "preview"
    snapshot_hash: str = ""

    attention_state: dict[str, Any] = field(default_factory=dict)
    cognition_cards: list[dict[str, Any]] = field(default_factory=list)
    narrative: dict[str, Any] = field(default_factory=dict)
    playbook: dict[str, Any] = field(default_factory=dict)
    override_summary: dict[str, Any] = field(default_factory=dict)

    # ── Workbench Sections (Phase 4.5.4) ──
    emotion_review: dict[str, Any] = field(default_factory=dict)
    chart_reviews: list[dict[str, Any]] = field(default_factory=list)

    # ── Canonical Fields (P0-C): Approved Facts frozen at approve time ──
    # Market facts: up/down, limit counts, turnover
    market_state: dict[str, Any] = field(default_factory=dict)
    # Capital: institution/hot_money directions, active amount, seat money
    capital_institution_style: list[dict[str, Any]] = field(default_factory=list)
    capital_hot_money_style: list[dict[str, Any]] = field(default_factory=list)
    capital_active_amount: float | None = None
    capital_seat_money: dict[str, Any] = field(default_factory=dict)
    # Themes: cognition cards enriched with derived context
    theme_structure: list[dict[str, Any]] = field(default_factory=list)
    # Stocks: strong_stock rows from derived context
    stock_structure: list[dict[str, Any]] = field(default_factory=list)
    # Plan: playbook + scenario from plan_state
    plan_state: dict[str, Any] = field(default_factory=dict)
    # Quality annotations: distinguish NO_DATA from MISSING for completeness checks
    capital_quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "snapshot_version": self.snapshot_version,
            "based_on_draft_version": self.based_on_draft_version,
            "approved": self.approved,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "approval_mode": self.approval_mode,
            "source_mode": self.source_mode,
            "composition_mode": self.composition_mode,
            "snapshot_hash": self.snapshot_hash,
            "attention_state": self.attention_state,
            "cognition_cards": self.cognition_cards,
            "narrative": self.narrative,
            "playbook": self.playbook,
            "override_summary": self.override_summary,
            "emotion_review": self.emotion_review,
            "chart_reviews": self.chart_reviews,
            # Canonical fields (P0-C)
            "market_state": self.market_state,
            "capital_institution_style": self.capital_institution_style,
            "capital_hot_money_style": self.capital_hot_money_style,
            "capital_active_amount": self.capital_active_amount,
            "capital_seat_money": self.capital_seat_money,
            "theme_structure": self.theme_structure,
            "stock_structure": self.stock_structure,
            "plan_state": self.plan_state,
            "capital_quality": self.capital_quality,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewSnapshot":
        return cls(
            trade_date=date.fromisoformat(d["trade_date"]),
            snapshot_version=d.get("snapshot_version", 1),
            based_on_draft_version=d.get("based_on_draft_version", 0),
            approved=d.get("approved", False),
            approved_at=d.get("approved_at", ""),
            approved_by=d.get("approved_by", ""),
            approval_mode=d.get("approval_mode", "analyst_approved" if d.get("approved", False) else "preview"),
            source_mode=d.get("source_mode", "analyst_workbench" if d.get("approved", False) else "preview"),
            composition_mode=d.get("composition_mode", "formal" if d.get("approved", False) else "preview"),
            snapshot_hash=d.get("snapshot_hash", ""),
            attention_state=d.get("attention_state", {}),
            cognition_cards=d.get("cognition_cards", []),
            narrative=d.get("narrative", {}),
            playbook=d.get("playbook", {}),
            override_summary=d.get("override_summary", {}),
            emotion_review=d.get("emotion_review", {}),
            chart_reviews=d.get("chart_reviews", []),
            # Canonical fields (P0-C) — backward compatible, defaults for old snapshots
            market_state=d.get("market_state", {}),
            capital_institution_style=d.get("capital_institution_style", []),
            capital_hot_money_style=d.get("capital_hot_money_style", []),
            capital_active_amount=d.get("capital_active_amount"),
            capital_seat_money=d.get("capital_seat_money", {}),
            theme_structure=d.get("theme_structure", []),
            stock_structure=d.get("stock_structure", []),
            plan_state=d.get("plan_state", {}),
            capital_quality=d.get("capital_quality", {}),
        )

    @classmethod
    def from_draft(cls, draft: "AIDraft", overrides: dict | None = None, draft_context: dict[str, Any] | None = None, **kwargs) -> "ReviewSnapshot":
        from datetime import datetime, timezone
        ctx = draft_context or {}
        return cls(
            trade_date=draft.trade_date,
            snapshot_version=kwargs.get("snapshot_version", 1),
            based_on_draft_version=draft.draft_version,
            approved=True,
            approved_at=datetime.now(timezone.utc).isoformat(),
            approved_by=kwargs.get("approved_by", ""),
            approval_mode=kwargs.get("approval_mode", "analyst_approved"),
            source_mode=kwargs.get("source_mode", "analyst_workbench"),
            composition_mode=kwargs.get("composition_mode", "formal"),
            attention_state=draft.attention_state,
            cognition_cards=draft.cognition_cards,
            narrative=draft.narrative,
            playbook=draft.playbook,
            override_summary=overrides or {},
            emotion_review=draft.emotion_review,
            chart_reviews=draft.chart_reviews,
            # Canonical fields from draft_context
            market_state=ctx.get("market_state", {}),
            capital_active_amount=ctx.get("capital_state", {}).get("active_amount"),
            capital_seat_money=ctx.get("seat_money_summary", {}),
            theme_structure=ctx.get("themes", []),
            stock_structure=ctx.get("strong_stocks", []),
            plan_state=ctx.get("plan_state", {}),
            capital_quality=ctx.get("capital_quality", {}),
        )

    @classmethod
    def from_merged(
        cls,
        *,
        trade_date: date,
        draft: "AIDraft",
        merged: dict[str, Any],
        snapshot_version: int = 1,
        approved_by: str = "",
        draft_context: dict[str, Any] | None = None,
    ) -> "ReviewSnapshot":
        ctx = draft_context or {}
        return cls(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            based_on_draft_version=draft.draft_version,
            approved=True,
            approved_at=datetime.now(timezone.utc).isoformat(),
            approved_by=approved_by,
            approval_mode="analyst_approved",
            source_mode="analyst_workbench",
            composition_mode="formal",
            attention_state=merged.get("attention_state", {}),
            cognition_cards=merged.get("cognition_cards", []),
            narrative=merged.get("narrative", {}),
            playbook=merged.get("playbook", {}),
            override_summary=merged.get("override_summary", {}),
            emotion_review=merged.get("emotion_review", {}),
            chart_reviews=merged.get("chart_reviews", []),
            # Canonical fields from draft_context (enriched by _enrich_draft_context_with_capital)
            market_state=ctx.get("market_state", {}),
            capital_active_amount=ctx.get("capital_state", {}).get("active_amount"),
            capital_institution_style=ctx.get("capital_institution_style", []),
            capital_hot_money_style=ctx.get("capital_hot_money_style", []),
            capital_seat_money=ctx.get("seat_money_summary", {}),
            theme_structure=ctx.get("themes", []),
            stock_structure=ctx.get("strong_stocks", []),
            plan_state=ctx.get("plan_state", {}),
            capital_quality=ctx.get("capital_quality", {}),
        )

    def compute_hash(self) -> str:
        payload = self.to_dict()
        payload["snapshot_hash"] = ""
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SnapshotStore:
    def __init__(self, base_dir: str = "tmp/analyst_workbench"):
        self.base_dir = Path(base_dir)

    def _snapshot_dir(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat()

    def _snapshot_path(self, trade_date: date) -> Path:
        return self._snapshot_dir(trade_date) / "snapshot.json"

    def save(self, snapshot: ReviewSnapshot) -> Path:
        d = self._snapshot_dir(snapshot.trade_date)
        d.mkdir(parents=True, exist_ok=True)

        snapshot.snapshot_hash = snapshot.compute_hash()
        payload = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2)

        # P0-E: Versioned snapshot (v1, v2, ... → Final)
        v_path = d / f"snapshot_v{snapshot.snapshot_version}.json"
        v_path.write_text(payload)

        # Latest snapshot (for fast reads)
        p = self._snapshot_path(snapshot.trade_date)
        p.write_text(payload)
        return p

    def load(self, trade_date: date) -> ReviewSnapshot | None:
        p = self._snapshot_path(trade_date)
        if not p.exists():
            return None
        return ReviewSnapshot.from_dict(json.loads(p.read_text()))

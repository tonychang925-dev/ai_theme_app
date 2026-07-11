"""Read Workbench derived context from post-market derived tables.

This is a read-only adapter for Phase 4.5.5-RB. It does not generate data and
does not call LLMs; it only packages rows already produced by
PostMarketDerivedDataGenerateUseCase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
from typing import Any


@dataclass
class WorkbenchDerivedContext:
    trade_date: str
    themes: list[dict[str, Any]] = field(default_factory=list)
    money_flows: list[dict[str, Any]] = field(default_factory=list)
    strong_stocks: list[dict[str, Any]] = field(default_factory=list)
    abnormal_signals: list[dict[str, Any]] = field(default_factory=list)
    market_state: dict[str, Any] = field(default_factory=dict)
    source_versions: dict[str, Any] = field(default_factory=dict)
    missing_sources: list[str] = field(default_factory=list)

    @property
    def source_quality(self) -> float:
        required = ("theme_cycle_judgement_v2", "money_flow_enhanced", "strong_stock_watch_history")
        missing_required = sum(1 for item in required if item in self.missing_sources)
        return max(0.5, 1.0 - missing_required * 0.2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "themes": self.themes,
            "money_flows": self.money_flows,
            "strong_stocks": self.strong_stocks,
            "abnormal_signals": self.abnormal_signals,
            "market_state": self.market_state,
            "source_versions": self.source_versions,
            "missing_sources": self.missing_sources,
            "source_quality": self.source_quality,
        }


class DerivedContextReader:
    """Read derived rows for Workbench AI draft context."""

    def __init__(self, pool: Any = None):
        self.pool = pool

    async def read(self, trade_date_value: date) -> WorkbenchDerivedContext:
        td = trade_date_value.isoformat()
        if self.pool is None:
            return WorkbenchDerivedContext(
                trade_date=td,
                missing_sources=[
                    "theme_cycle_judgement_v2",
                    "money_flow_enhanced",
                    "strong_stock_watch_history",
                ],
            )

        ctx = WorkbenchDerivedContext(trade_date=td)
        async with self.pool.acquire() as conn:
            ctx.themes = await self._fetch_themes(conn, trade_date_value, ctx)
            ctx.money_flows = await self._fetch_money_flows(conn, trade_date_value, ctx)
            ctx.strong_stocks = await self._fetch_strong_stocks(conn, trade_date_value, ctx)
            ctx.abnormal_signals = await self._fetch_abnormal_signals(conn, trade_date_value, ctx)

        self._resolve_theme_names(ctx)
        ctx.market_state = self._build_market_state(ctx)
        ctx.source_versions = {
            "theme_cycle_judgement_v2": len(ctx.themes),
            "money_flow_enhanced": len(ctx.money_flows),
            "strong_stock_watch_history": len(ctx.strong_stocks),
            "stock_abnormal_signal": len(ctx.abnormal_signals),
        }
        return ctx

    async def _fetch_themes(self, conn: Any, trade_date_value: date, ctx: WorkbenchDerivedContext) -> list[dict[str, Any]]:
        try:
            rows = await conn.fetch(
                """
                SELECT subject_key, theme_name, final_cycle_state, final_mainline_alive,
                       mainline_strength_score, fade_risk_score, fade_watch_score,
                       fade_confirmed_score, divergence_score, repair_score,
                       confidence_score, risk_flags, evidence_refs, state_transition_reason
                FROM theme_cycle_judgement_v2
                WHERE trade_date = $1::date
                ORDER BY COALESCE(mainline_strength_score, 0) DESC, subject_key
                """,
                trade_date_value,
            )
        except Exception as exc:
            ctx.missing_sources.append("theme_cycle_judgement_v2")
            return []

        items = []
        for row in rows:
            item = dict(row)
            items.append({
                "subject_key": str(item.get("subject_key") or ""),
                "theme_name": str(item.get("theme_name") or item.get("subject_key") or ""),
                "stage": str(item.get("final_cycle_state") or ""),
                "role": "MAINLINE" if bool(item.get("final_mainline_alive")) else "WATCH",
                "mainline_alive": bool(item.get("final_mainline_alive")),
                "mainline_strength_score": _float(item.get("mainline_strength_score")),
                "fade_risk_score": _float(item.get("fade_risk_score")),
                "fade_watch_score": _float(item.get("fade_watch_score")),
                "fade_confirmed_score": _float(item.get("fade_confirmed_score")),
                "divergence_score": _float(item.get("divergence_score")),
                "repair_score": _float(item.get("repair_score")),
                "confidence_score": _float(item.get("confidence_score")),
                "risk_flags": _jsonish(item.get("risk_flags"), []),
                "evidence_refs": _jsonish(item.get("evidence_refs"), []),
                "state_transition_reason": str(item.get("state_transition_reason") or ""),
            })
        if not items:
            ctx.missing_sources.append("theme_cycle_judgement_v2")
        return items

    async def _fetch_money_flows(self, conn: Any, trade_date_value: date, ctx: WorkbenchDerivedContext) -> list[dict[str, Any]]:
        try:
            rows = await conn.fetch(
                """
                SELECT subject_key, theme_name, stock_id, stock_name, role_label,
                       role_enhanced, candidate_rank, composite_score,
                       money_flow_score, money_flow_tier, main_net_inflow,
                       dragon_tiger_net_amount, institution_seat_count, explanation
                FROM money_flow_enhanced
                WHERE trade_date = $1::date
                ORDER BY COALESCE(composite_score, 0) DESC, subject_key, candidate_rank
                LIMIT 200
                """,
                trade_date_value,
            )
        except Exception as exc:
            ctx.missing_sources.append("money_flow_enhanced")
            return []

        items = [self._money_flow_row(dict(row)) for row in rows]
        if not items:
            ctx.missing_sources.append("money_flow_enhanced")
        return items

    async def _fetch_strong_stocks(self, conn: Any, trade_date_value: date, ctx: WorkbenchDerivedContext) -> list[dict[str, Any]]:
        try:
            rows = await conn.fetch(
                """
                SELECT stock_id, stock_name, subject_key, theme_name, watch_status,
                       watch_score, watch_priority, relay_role, pool_entry_type,
                       cycle_state, mainline_strength_score, fade_watch,
                       fade_confirmed, promoted_to_candidate, support_type,
                       support_level, support_score, labels_json, evidence_json
                FROM strong_stock_watch_history
                WHERE trade_date = $1::date
                ORDER BY COALESCE(watch_score, 0) DESC, stock_id
                LIMIT 200
                """,
                trade_date_value,
            )
        except Exception as exc:
            ctx.missing_sources.append("strong_stock_watch_history")
            return []

        items = []
        for row in rows:
            item = dict(row)
            items.append({
                "stock_code": str(item.get("stock_id") or ""),
                "stock_name": str(item.get("stock_name") or item.get("stock_id") or ""),
                "subject_key": str(item.get("subject_key") or ""),
                "theme_name": str(item.get("theme_name") or ""),
                "watch_status": str(item.get("watch_status") or ""),
                "watch_score": _float(item.get("watch_score")),
                "watch_priority": _float(item.get("watch_priority")),
                "role": str(item.get("relay_role") or item.get("pool_entry_type") or ""),
                "cycle_state": str(item.get("cycle_state") or ""),
                "mainline_strength_score": _float(item.get("mainline_strength_score")),
                "fade_watch": bool(item.get("fade_watch")),
                "fade_confirmed": bool(item.get("fade_confirmed")),
                "promoted_to_candidate": bool(item.get("promoted_to_candidate")),
                "support_type": str(item.get("support_type") or ""),
                "support_level": _float(item.get("support_level")),
                "support_score": _float(item.get("support_score")),
                "labels": _jsonish(item.get("labels_json"), {}),
                "evidence": _jsonish(item.get("evidence_json"), {}),
            })
        if not items:
            ctx.missing_sources.append("strong_stock_watch_history")
        return items

    async def _fetch_abnormal_signals(self, conn: Any, trade_date_value: date, ctx: WorkbenchDerivedContext) -> list[dict[str, Any]]:
        try:
            rows = await conn.fetch(
                """
                SELECT stock_id, stock_name, signal_type, signal_strength, signal_payload
                FROM stock_abnormal_signal
                WHERE trade_date = $1::date
                ORDER BY COALESCE(signal_strength, 0) DESC
                LIMIT 100
                """,
                trade_date_value,
            )
        except Exception:
            return []
        return [dict(row) for row in rows]

    @staticmethod
    def _resolve_theme_names(ctx: WorkbenchDerivedContext) -> None:
        name_by_subject: dict[str, str] = {}
        for source in (ctx.money_flows, ctx.strong_stocks):
            for row in source:
                key = str(row.get("subject_key") or "")
                name = str(row.get("theme_name") or "").strip()
                if key and name and name != key and not name.isdigit():
                    name_by_subject.setdefault(key, name)
        for theme in ctx.themes:
            key = str(theme.get("subject_key") or "")
            name = str(theme.get("theme_name") or "").strip()
            if key and (not name or name == key or name.isdigit()):
                resolved = name_by_subject.get(key)
                if resolved:
                    theme["theme_name"] = resolved

    @staticmethod
    def _money_flow_row(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "subject_key": str(item.get("subject_key") or ""),
            "theme_name": str(item.get("theme_name") or ""),
            "stock_code": str(item.get("stock_id") or ""),
            "stock_name": str(item.get("stock_name") or ""),
            "role_label": str(item.get("role_label") or ""),
            "role_enhanced": str(item.get("role_enhanced") or ""),
            "candidate_rank": int(item.get("candidate_rank") or 0),
            "composite_score": _float(item.get("composite_score")),
            "money_flow_score": _float(item.get("money_flow_score")),
            "money_flow_tier": str(item.get("money_flow_tier") or ""),
            "main_net_inflow": _float(item.get("main_net_inflow")),
            "dragon_tiger_net_amount": _float(item.get("dragon_tiger_net_amount")),
            "institution_seat_count": int(item.get("institution_seat_count") or 0),
            "explanation": _jsonish(item.get("explanation"), []),
        }

    @staticmethod
    def _build_market_state(ctx: WorkbenchDerivedContext) -> dict[str, Any]:
        mainline_count = sum(1 for item in ctx.themes if item.get("mainline_alive"))
        active_themes = [item for item in ctx.themes if item.get("stage")]
        return {
            "theme_count": len(ctx.themes),
            "mainline_count": mainline_count,
            "active_theme_count": len(active_themes),
            "strong_stock_count": len(ctx.strong_stocks),
            "money_flow_count": len(ctx.money_flows),
        }


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _jsonish(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                return json.loads(text)
            except Exception:
                return value
    return value

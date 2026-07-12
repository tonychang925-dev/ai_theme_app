"""Typed input contexts for ReviewDocumentAssembler.

The assembler must not receive a full ReviewSnapshot. This module defines the
allowed whitelist extracted from a snapshot-like object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class MarketContext:
    market_metrics: dict[str, Any] = field(default_factory=dict)
    chart_reviews: tuple[dict[str, Any], ...] = ()
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmotionContext:
    emotion_review: dict[str, Any] = field(default_factory=dict)
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ThemeContext:
    cognition_cards: tuple[dict[str, Any], ...] = ()
    theme_cycle_rows: tuple[dict[str, Any], ...] = ()
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapitalContext:
    money_flow_rows: tuple[dict[str, Any], ...] = ()
    institution_rows: tuple[dict[str, Any], ...] = ()
    hot_money_rows: tuple[dict[str, Any], ...] = ()
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StockContext:
    strong_stock_rows: tuple[dict[str, Any], ...] = ()
    abnormal_signal_rows: tuple[dict[str, Any], ...] = ()
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanContext:
    playbook: dict[str, Any] = field(default_factory=dict)
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OverrideContext:
    field_overrides: dict[str, Any] = field(default_factory=dict)
    explicit_overrides: tuple[dict[str, Any], ...] = ()
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceContext:
    chart_reviews: tuple[dict[str, Any], ...] = ()
    trend_data: dict[str, Any] = field(default_factory=dict)
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReviewDocumentContext:
    trade_date: str
    metadata: dict[str, Any]
    market_context: MarketContext
    emotion_context: EmotionContext
    evidence_context: EvidenceContext
    theme_context: ThemeContext
    capital_context: CapitalContext
    stock_context: StockContext
    plan_context: PlanContext
    override_context: OverrideContext
    approval: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReviewDocumentAssemblerInput:
    context: ReviewDocumentContext
    mode: Literal["draft", "review", "approved"] = "draft"


class ReviewDocumentContextFactory:
    """Whitelist extractor from snapshot-like objects to typed contexts."""

    def create(self, snapshot: Any) -> ReviewDocumentContext:
        trade_date = _trade_date(snapshot)
        attention_state = _dict_value(snapshot, "attention_state")
        derived = _dict_value(snapshot, "derived_context")
        if not derived:
            derived = _dict_value(attention_state, "derived_context")
        if not derived:
            derived = _dict_value(attention_state, "review_document_context")

        metadata = {
            "snapshot_hash": _value(snapshot, "snapshot_hash"),
            "snapshot_version": _value(snapshot, "snapshot_version"),
        }
        approval = {
            "approved": bool(_value(snapshot, "approved", False)),
            "approved_at": _value(snapshot, "approved_at"),
            "approval_mode": _value(snapshot, "approval_mode"),
            "source_mode": _value(snapshot, "source_mode"),
            "composition_mode": _value(snapshot, "composition_mode"),
        }

        market_state = _dict_value(derived, "market_state")
        market_metrics = _dict_value(derived, "market_metrics")
        market_facts = _dict_value(market_state, "facts")
        if market_facts:
            market_state = {**market_state, **market_facts}

        capital_state = _dict_value(derived, "capital_state")
        money_flow_rows = _list_value(capital_state, "money_flows")
        if not money_flow_rows:
            money_flow_rows = _list_value(derived, "money_flows")
        if not money_flow_rows:
            money_flow_rows = _list_value(capital_state, "top_stocks")

        return ReviewDocumentContext(
            trade_date=trade_date,
            metadata=metadata,
            market_context=MarketContext(
                market_metrics=market_state or market_metrics,
                chart_reviews=tuple(_list_value(snapshot, "chart_reviews")),
                source_meta=_source_meta(derived, "market_state", trade_date),
            ),
            emotion_context=EmotionContext(
                emotion_review=_dict_value(snapshot, "emotion_review"),
                source_meta=_source_meta(snapshot, "emotion_review", trade_date),
            ),
            evidence_context=EvidenceContext(
                chart_reviews=tuple(_list_value(derived, "chart_reviews")),
                trend_data=_dict_value(derived, "trend_data"),
                source_meta=_source_meta(derived, "chart_reviews", trade_date),
            ),
            theme_context=ThemeContext(
                cognition_cards=tuple(_list_value(snapshot, "cognition_cards")),
                theme_cycle_rows=tuple(_list_value(derived, "themes")),
                source_meta=_source_meta(derived, "themes", trade_date),
            ),
            capital_context=CapitalContext(
                money_flow_rows=tuple(money_flow_rows),
                institution_rows=tuple(_list_value(capital_state, "institution")),
                hot_money_rows=tuple(_list_value(capital_state, "hot_money")),
                source_meta=_source_meta(derived, "money_flows", trade_date),
            ),
            stock_context=StockContext(
                strong_stock_rows=tuple(_list_value(derived, "strong_stocks")),
                abnormal_signal_rows=tuple(_list_value(derived, "abnormal_signals")),
                source_meta=_source_meta(derived, "strong_stocks", trade_date),
            ),
            plan_context=PlanContext(
                playbook=_dict_value(snapshot, "playbook"),
                source_meta=_source_meta(snapshot, "playbook", trade_date),
            ),
            override_context=OverrideContext(
                field_overrides=_collect_field_overrides(_list_value(snapshot, "cognition_cards")),
                explicit_overrides=tuple(_explicit_overrides(_list_value(snapshot, "cognition_cards"))),
                source_meta=_source_meta(snapshot, "cognition_cards", trade_date),
            ),
            approval=approval,
        )


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _dict_value(obj: Any, key: str) -> dict[str, Any]:
    value = _value(obj, key, {})
    return value if isinstance(value, dict) else {}


def _list_value(obj: Any, key: str) -> list[dict[str, Any]]:
    value = _value(obj, key, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _trade_date(snapshot: Any) -> str:
    raw = _value(snapshot, "trade_date")
    if isinstance(raw, date):
        return raw.isoformat()
    return str(raw or "")


def _source_meta(obj: Any, source_name: str, trade_date: str) -> dict[str, Any]:
    generated_at = _value(obj, "generated_at") or _value(obj, "created_at")
    source_trade_date = _value(obj, "trade_date") or trade_date
    return {
        "source": source_name,
        "source_trade_date": str(source_trade_date),
        "source_generated_at": str(generated_at) if generated_at else "",
    }


def _collect_field_overrides(cards: list[dict[str, Any]]) -> dict[str, Any]:
    collected: dict[str, Any] = {}
    for card in cards:
        overrides = card.get("field_overrides")
        if isinstance(overrides, dict):
            key = str(card.get("subject_id") or card.get("subject_key") or card.get("subject_name") or "")
            if key:
                collected[key] = overrides
    return collected


def _explicit_overrides(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for card in cards:
        overrides = card.get("field_overrides")
        if not isinstance(overrides, dict):
            continue
        subject_key = str(card.get("subject_id") or card.get("subject_key") or card.get("subject_name") or "")
        for field_name, override in overrides.items():
            if not isinstance(override, dict):
                continue
            items.append({
                "entity_key": subject_key,
                "field": field_name,
                "ai_value": override.get("ai_value"),
                "analyst_value": override.get("analyst_value"),
                "final_value": override.get("final_value") or override.get("analyst_value"),
                "reason": override.get("reason", ""),
            })
    return items

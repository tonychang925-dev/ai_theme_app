"""ReviewDocumentAssembler.

Pure assembly only: no database reads, no LLM calls, no legacy fallback, and no
business inference beyond mapping typed context fields into the display schema.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from .context import ReviewDocumentAssemblerInput, ReviewDocumentContext
from .enums import DocumentStatus, FieldClass, SectionQualityStatus, TransformType, ValidationStatus
from .quality import FreshnessQuality, ReviewDocumentQuality, SectionQuality
from .schema import FieldProvenanceEntry, ReviewDocument, ReviewDocumentMetadata


class ReviewDocumentAssembler:
    """Assemble ReviewDocument from typed context only."""

    def assemble(self, assembler_input: ReviewDocumentAssemblerInput) -> ReviewDocument:
        ctx = assembler_input.context
        metadata = ReviewDocumentMetadata(
            trade_date=ctx.trade_date,
            status=_status_for_mode(assembler_input.mode),
            snapshot_hash=_text(ctx.metadata.get("snapshot_hash")),
            snapshot_version=_int_or_none(ctx.metadata.get("snapshot_version")),
            approved_at=_text(ctx.approval.get("approved_at")) or None,
        )

        field_provenance: dict[str, FieldProvenanceEntry] = {}
        market = self._assemble_market(ctx, field_provenance)
        emotion = self._assemble_emotion(ctx, field_provenance)
        themes = self._assemble_themes(ctx, field_provenance)
        summary = self._assemble_summary(ctx, themes, field_provenance)
        capital = self._assemble_capital(ctx)
        stocks = self._assemble_stocks(ctx)
        plan = self._assemble_plan(ctx)
        evidence = self._assemble_evidence(ctx)
        quality = self._quality(ctx, market, emotion, themes, capital, stocks, plan, field_provenance)

        document = ReviewDocument(
            metadata=metadata,
            summary=summary,
            market=market,
            emotion=emotion,
            evidence=evidence,
            themes=tuple(themes),
            stocks=tuple(stocks),
            capital=capital,
            limit_up=self._assemble_limit_up(ctx),
            plan=plan,
            risk=self._assemble_risk(ctx),
            quality=quality,
            field_provenance=field_provenance,
            audit={
                "explicit_overrides": list(ctx.override_context.explicit_overrides),
                "system_resolutions": [],
                "compatibility_mappings": [],
            },
        )
        return _with_final_document_hash(document)

    def _assemble_market(
        self,
        ctx: ReviewDocumentContext,
        provenance: dict[str, FieldProvenanceEntry],
    ) -> dict[str, Any]:
        source = ctx.market_context.market_metrics
        market = {
            "limit_up_count": _first(source, "limit_up_count", "limit_up", "limit_up_total"),
            "limit_down_count": _first(source, "limit_down_count", "limit_down", "limit_down_total"),
            "up_count": _first(source, "up_count", "up"),
            "down_count": _first(source, "down_count", "down"),
            "active_capital_yi": _first(source, "active_capital_yi", "active_amount_yi", "active_capital", "active_money"),
            "max_board_height": _first(source, "max_board_height", "max_board"),
        }
        market = {k: v for k, v in market.items() if v is not None and v != ""}
        for field_name in ("limit_up_count", "limit_down_count", "up_count", "down_count"):
            if field_name in market:
                provenance[f"market.{field_name}"] = _provenance(
                    source=f"snapshot.derived_context.market_state.{field_name}",
                    field_type=FieldClass.FACT,
                    transform=TransformType.DIRECT_MAPPING,
                    trade_date=ctx.trade_date,
                )
        return market

    def _assemble_emotion(
        self,
        ctx: ReviewDocumentContext,
        provenance: dict[str, FieldProvenanceEntry],
    ) -> dict[str, Any]:
        source = ctx.emotion_context.emotion_review
        emotion = {
            "phase": _first(source, "phase", "emotion_node", "state"),
            "score": _first(source, "score", "emotion_score"),
            "risk_level": _first(source, "risk_level", "risk"),
            "strategy": _first(source, "strategy", "strategy_bias"),
            "confidence": _first(source, "confidence"),
            "key_evidence": source.get("key_evidence") or [],
        }
        emotion = {k: v for k, v in emotion.items() if v is not None and v != ""}
        if "score" in emotion:
            provenance["emotion.score"] = _provenance(
                source="snapshot.emotion_review.score",
                field_type=FieldClass.ASSESSMENT,
                transform=TransformType.DIRECT_MAPPING,
                trade_date=ctx.trade_date,
            )
        return emotion

    def _assemble_themes(
        self,
        ctx: ReviewDocumentContext,
        provenance: dict[str, FieldProvenanceEntry],
    ) -> list[dict[str, Any]]:
        by_key: dict[str, dict[str, Any]] = {}
        for row in ctx.theme_context.theme_cycle_rows:
            key = _theme_key(row)
            if key:
                by_key[key] = {
                    "theme_key": key,
                    "name": _name_value(row.get("theme_name")) if row.get("theme_name") else None,
                    "role": row.get("role") or ("MAINLINE" if row.get("mainline_alive") else "WATCH"),
                    "stage": row.get("stage") or row.get("final_cycle_state"),
                    "strength_score": row.get("mainline_strength_score") or row.get("strength_score"),
                }

        for card in ctx.theme_context.cognition_cards:
            key = _theme_key(card)
            if key:
                entry = by_key.setdefault(key, {
                    "theme_key": key,
                    "name": _name_value(card.get("subject_name")) if card.get("subject_name") else None,
                    "role": _role_from_card(card),
                })
                subject_name_override = _subject_name_override(card)
                if subject_name_override:
                    entry["name"] = subject_name_override
                    provenance[f"themes[{key}].name.final_value"] = _provenance(
                        source=f"snapshot.cognition_cards[{key}].field_overrides.subject_name",
                        field_type=FieldClass.IDENTITY,
                        transform=TransformType.EXPLICIT_OVERRIDE,
                        trade_date=ctx.trade_date,
                    )
                    provenance.setdefault("themes.primary", provenance[f"themes[{key}].name.final_value"])
                elif "themes.primary" not in provenance:
                    provenance["themes.primary"] = _provenance(
                        source=f"snapshot.cognition_cards[{key}].subject_name",
                        field_type=FieldClass.IDENTITY,
                        transform=TransformType.DIRECT_MAPPING,
                        trade_date=ctx.trade_date,
                    )
        return list(by_key.values())

    def _assemble_summary(
        self,
        ctx: ReviewDocumentContext,
        themes: list[dict[str, Any]],
        provenance: dict[str, FieldProvenanceEntry],
    ) -> dict[str, Any]:
        primary_theme = next(
            (theme for theme in themes if isinstance(theme.get("name"), dict) and theme["name"].get("analyst_value")),
            themes[0] if themes else {},
        )
        primary = primary_theme.get("name", {}) if isinstance(primary_theme, dict) else {}
        summary = {
            "market_conclusion": _first(ctx.emotion_context.emotion_review, "summary", "strategy_bias"),
            "main_story": _first(ctx.metadata, "main_story"),
            "primary_theme": primary,
        }
        if primary and "themes.primary" in provenance:
            provenance["summary.primary_theme.final_value"] = provenance["themes.primary"]
        return {k: v for k, v in summary.items() if v not in (None, "", {}, [])}

    def _assemble_capital(self, ctx: ReviewDocumentContext) -> dict[str, Any]:
        institution = list(ctx.capital_context.institution_rows)
        hot_money = list(ctx.capital_context.hot_money_rows)
        capital = {
            "market": {},
            "institution": institution,
            "hot_money": hot_money,
        }
        if ctx.capital_context.active_amount not in (None, ""):
            capital["active_amount"] = ctx.capital_context.active_amount
        return capital

    def _assemble_stocks(self, ctx: ReviewDocumentContext) -> list[dict[str, Any]]:
        return [dict(row) for row in ctx.stock_context.strong_stock_rows]

    def _assemble_plan(self, ctx: ReviewDocumentContext) -> dict[str, Any]:
        playbook = ctx.plan_context.playbook
        return {
            "scenario": _first(playbook, "scenario"),
            "allowed_actions": playbook.get("allowed_actions") or playbook.get("allowed") or [],
            "forbidden_actions": playbook.get("forbidden_actions") or playbook.get("forbidden") or [],
            "watch_themes": playbook.get("watch_themes") or [],
            "watch_stocks": playbook.get("watch_stocks") or [],
            "confirmation_signals": playbook.get("confirmation_signals") or [],
            "invalidation_signals": playbook.get("invalidation_signals") or [],
        }

    def _assemble_limit_up(self, ctx: ReviewDocumentContext) -> dict[str, Any]:
        total = ctx.limit_up_context.total
        if total in (None, ""):
            total = ctx.market_context.market_metrics.get("limit_up_count")
        return {
            "total": total,
            "categories": [dict(row) for row in ctx.limit_up_context.categories],
        }

    def _assemble_evidence(self, ctx: ReviewDocumentContext) -> dict[str, Any]:
        return {
            "charts": list(ctx.evidence_context.chart_reviews),
            "trend_series": dict(ctx.evidence_context.trend_data),
        }

    def _assemble_risk(self, ctx: ReviewDocumentContext) -> dict[str, Any]:
        return {
            "risk_level": _first(ctx.emotion_context.emotion_review, "risk_level", "risk"),
            "top_risks": ctx.emotion_context.emotion_review.get("risk_flags") or [],
        }

    def _quality(
        self,
        ctx: ReviewDocumentContext,
        market: dict[str, Any],
        emotion: dict[str, Any],
        themes: list[dict[str, Any]],
        capital: dict[str, Any],
        stocks: list[dict[str, Any]],
        plan: dict[str, Any],
        provenance: dict[str, FieldProvenanceEntry],
    ) -> ReviewDocumentQuality:
        sections = {
            "summary": _section(bool(themes), "primary_theme"),
            "market": _section("limit_up_count" in market, "limit_up_count"),
            "emotion": _section(bool(emotion.get("phase") or emotion.get("score")), "phase_or_score"),
            "themes": _section(bool(themes), "themes"),
            "stocks": _section(bool(stocks), "stocks", allow_missing=True),
            "capital": _section(bool(capital.get("institution") or capital.get("hot_money")), "capital"),
            "limit_up": _section(bool(ctx.limit_up_context.categories), "limit_up_categories", allow_missing=True),
            "plan": _section(any(v for v in plan.values()), "plan", allow_missing=True),
            "risk": _section(True, "risk", allow_missing=True),
        }
        blocking = [
            f"{name}:{issue}"
            for name, section in sections.items()
            for issue in section.blocking_issues
        ]
        if any(item.validation_status == ValidationStatus.INVALID for item in provenance.values()):
            blocking.append("field_provenance_invalid")
        overall = SectionQualityStatus.READY if not blocking else SectionQualityStatus.BLOCKED
        return ReviewDocumentQuality(
            overall=overall,
            sections=sections,
            can_approve=not blocking,
            blocking_issues=tuple(blocking),
            freshness=FreshnessQuality(
                status=SectionQualityStatus.READY,
                trade_date_match=True,
            ),
        )


def _status_for_mode(mode: str) -> DocumentStatus:
    if mode == "approved":
        return DocumentStatus.APPROVED
    if mode == "review":
        return DocumentStatus.IN_REVIEW
    return DocumentStatus.DRAFT


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _text(value: Any) -> str:
    return str(value or "")


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _theme_key(row: dict[str, Any]) -> str:
    return _text(row.get("theme_key") or row.get("subject_key") or row.get("subject_id") or row.get("subject_name"))


def _name_value(value: Any) -> dict[str, Any]:
    text = _text(value)
    return {"ai_value": text, "analyst_value": None, "final_value": text, "reason": ""}


def _subject_name_override(card: dict[str, Any]) -> dict[str, Any] | None:
    overrides = card.get("field_overrides")
    if not isinstance(overrides, dict):
        return None
    subject_name = overrides.get("subject_name")
    if not isinstance(subject_name, dict):
        return None
    final = subject_name.get("final_value") or subject_name.get("analyst_value")
    if final in (None, ""):
        return None
    return {
        "ai_value": subject_name.get("ai_value") or card.get("subject_name") or "",
        "analyst_value": subject_name.get("analyst_value"),
        "final_value": final,
        "reason": subject_name.get("reason", ""),
    }


def _role_from_card(card: dict[str, Any]) -> str:
    level = _text(card.get("attention_level")).upper()
    if level == "CRITICAL":
        return "MAINLINE"
    if level == "HIGH":
        return "SECONDARY"
    return "WATCH"


def _provenance(
    *,
    source: str,
    field_type: FieldClass,
    transform: TransformType,
    trade_date: str,
    validation_status: ValidationStatus = ValidationStatus.VERIFIED,
) -> FieldProvenanceEntry:
    return FieldProvenanceEntry(
        source=source,
        field_type=field_type,
        confidence=1.0,
        transform=transform,
        validation_status=validation_status,
        source_trade_date=trade_date,
    )


def _section(is_ready: bool, field_name: str, *, allow_missing: bool = False) -> SectionQuality:
    if is_ready:
        return SectionQuality(status=SectionQualityStatus.READY)
    if allow_missing:
        return SectionQuality(status=SectionQualityStatus.MISSING, missing_fields=(field_name,))
    return SectionQuality(
        status=SectionQualityStatus.BLOCKED,
        missing_fields=(field_name,),
        blocking_issues=(f"{field_name}_missing",),
    )


def _with_final_document_hash(document: ReviewDocument) -> ReviewDocument:
    payload = document.to_dict()
    payload["metadata"].pop("final_document_hash", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return replace(
        document,
        metadata=replace(document.metadata, final_document_hash=digest),
    )

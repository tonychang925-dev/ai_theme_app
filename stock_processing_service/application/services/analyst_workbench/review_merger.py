"""Merge AI draft and analyst workspace state for approved snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .draft import AIDraft


@dataclass(frozen=True)
class AnalystReviewMerger:
    """Build the analyst-approved review payload without mutating draft data."""

    def merge(
        self,
        *,
        draft: AIDraft,
        workspace: dict[str, Any] | None,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workspace = workspace or {}
        body_overrides = overrides or {}

        cognition_cards = self._merge_cognition_cards(draft, workspace)
        override_summary = self._build_override_summary(
            workspace=workspace,
            body_overrides=body_overrides,
            cognition_cards=cognition_cards,
        )

        attention_state = dict(draft.attention_state or {})
        watch_groups = workspace.get("watch_groups")
        if isinstance(watch_groups, list):
            attention_state["watch_groups"] = watch_groups

        return {
            "attention_state": attention_state,
            "cognition_cards": cognition_cards,
            "narrative": dict(draft.narrative or {}),
            "playbook": dict(draft.playbook or {}),
            "emotion_review": dict(draft.emotion_review or {}),
            "chart_reviews": list(draft.chart_reviews or []),
            "override_summary": override_summary,
        }

    def _merge_cognition_cards(self, draft: AIDraft, workspace: dict[str, Any]) -> list[dict[str, Any]]:
        themes = workspace.get("themes")
        if not isinstance(themes, list) or not themes:
            return list(draft.cognition_cards or [])

        draft_by_subject = {
            self._subject_key(card): card
            for card in (draft.cognition_cards or [])
            if self._subject_key(card)
        }

        cards: list[dict[str, Any]] = []
        for theme in themes:
            if not isinstance(theme, dict):
                continue
            key = self._subject_key(theme)
            ai_card = draft_by_subject.get(key, {})
            cards.append(self._merge_theme(theme, ai_card))
        return cards

    def _merge_theme(self, theme: dict[str, Any], ai_card: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        field_overrides = theme.get("field_overrides")
        if not isinstance(field_overrides, dict):
            field_overrides = {}

        passthrough = {
            "subject_id",
            "subject_name",
            "attention_level",
            "attention_score",
            "attention_reasons",
            "ai_recommended",
            "analyst_added",
            "analyst_reviewed",
            "leaders",
            "bull_pool",
            "bear_pool",
            "event_stimuli",
        }
        for field in passthrough:
            if field in theme:
                merged[field] = theme.get(field)

        review_fields = [
            "trading_style",
            "long_identifiability",
            "short_identifiability",
            "old_leaders",
            "yesterday_view",
            "today_actual",
            "stage_judgement",
            "intraday_understanding",
            "trader_sentiment",
            "index_resonance",
            "tomorrow_view",
            "analyst_notes",
        ]
        for field in review_fields:
            merged[field] = self._dual_track_field(
                field=field,
                ai_value=ai_card.get(field, ""),
                analyst_value=theme.get(field),
                override=field_overrides.get(field),
            )

        merged["field_overrides"] = field_overrides
        merged["source"] = "analyst_review"
        return merged

    @staticmethod
    def _dual_track_field(
        *,
        field: str,
        ai_value: Any,
        analyst_value: Any,
        override: Any,
    ) -> dict[str, Any]:
        reason = ""
        override_flag = False
        override_ai = ai_value
        override_analyst = analyst_value

        if isinstance(override, dict):
            override_ai = override.get("ai_value", ai_value)
            override_analyst = override.get("analyst_value", analyst_value)
            reason = str(override.get("reason", "") or "")
            override_flag = override_analyst != override_ai

        final_value = override_analyst
        if _is_empty(final_value) and not override_flag:
            final_value = override_ai

        if not override_flag and final_value != ai_value and not _is_empty(final_value):
            override_flag = True

        return {
            "field": field,
            "ai_value": override_ai,
            "analyst_value": "" if _is_empty(override_analyst) else override_analyst,
            "final_value": final_value,
            "override": override_flag,
            "reason": reason,
        }

    def _build_override_summary(
        self,
        *,
        workspace: dict[str, Any],
        body_overrides: dict[str, Any],
        cognition_cards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        field_changes: list[dict[str, Any]] = []
        for card in cognition_cards:
            subject_id = str(card.get("subject_id", ""))
            subject_name = str(card.get("subject_name", ""))
            for value in card.values():
                if isinstance(value, dict) and value.get("override") is True:
                    field_changes.append({
                        "subject_id": subject_id,
                        "subject_name": subject_name,
                        "field": value.get("field", ""),
                        "ai_value": value.get("ai_value", ""),
                        "analyst_value": value.get("analyst_value", ""),
                        "final_value": value.get("final_value", ""),
                        "reason": value.get("reason", ""),
                    })

        stock_changes = self._stock_override_count(workspace)
        return {
            "total": len(field_changes) + stock_changes + len(body_overrides),
            "field_changes": field_changes,
            "stock_changes": stock_changes,
            "request_overrides": body_overrides,
        }

    @staticmethod
    def _stock_override_count(workspace: dict[str, Any]) -> int:
        count = 0
        themes = workspace.get("themes")
        if not isinstance(themes, list):
            return 0
        for theme in themes:
            if not isinstance(theme, dict):
                continue
            for pool_type in ("leaders", "bull_pool", "bear_pool"):
                stocks = theme.get(pool_type)
                if isinstance(stocks, list):
                    count += sum(1 for stock in stocks if isinstance(stock, dict) and stock.get("analyst_modified"))
        return count

    @staticmethod
    def _subject_key(obj: dict[str, Any]) -> str:
        return str(obj.get("subject_id") or obj.get("subject_name") or obj.get("name") or "")


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}

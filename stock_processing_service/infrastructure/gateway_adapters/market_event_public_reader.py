from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

from stock_processing_service.application.services.market_event_public_boundary import (
    EVENT_OBJECT_TYPE,
    MarketEventLineage,
    MarketEventRecord,
    MarketEventResolutionRecord,
    MarketGovernanceState,
    MarketObjectRef,
    validate_event_object_ref,
)


class MarketEventPublicReader:
    def __init__(
        self,
        database_gateway: Any,
        public_to_private_ids: Mapping[str | UUID, int],
        governance_state: MarketGovernanceState = MarketGovernanceState.PUBLISHED,
    ) -> None:
        self._database_gateway = database_gateway
        normalized_ids: list[str] = []
        self._public_to_private_ids: dict[str, int] = {}
        for public_id, private_id in public_to_private_ids.items():
            validate_event_object_ref(MarketObjectRef(EVENT_OBJECT_TYPE, public_id))
            normalized_id = _normalize_public_id(public_id)
            normalized_ids.append(normalized_id)
            self._public_to_private_ids[normalized_id] = private_id
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("public event identifiers contain duplicate normalized values")
        private_ids = list(self._public_to_private_ids.values())
        if any(isinstance(value, bool) or not isinstance(value, int) for value in private_ids):
            raise ValueError("private event identifiers must be integers")
        if len(set(private_ids)) != len(private_ids):
            raise ValueError("public event identifiers map ambiguously to private identifiers")
        self._governance_state = governance_state

    async def read_event(self, object_ref: MarketObjectRef) -> MarketEventRecord | None:
        private_id = self._private_id(object_ref)
        if private_id is None:
            return None

        event_row = _as_dict(await self._database_gateway.get_event(private_id))
        match_row = _as_dict(
            await self._database_gateway.get_news_event_for_match(private_id)
        )
        if not event_row or not match_row:
            return None

        title = _required_text(match_row, "title", private_id)
        summary = _required_text(event_row, "summary", private_id)
        content = _required_text(match_row, "content", private_id)
        event_type = _required_text(match_row, "event_type", private_id)
        source = _required_text(event_row, "source", private_id)
        occurred_at = _required_datetime(
            event_row.get("publish_time") or event_row.get("created_at"), private_id
        )
        data_cutoff = _required_datetime(event_row.get("updated_at"), private_id)
        source_trace_id = event_row.get("source_trace_id")

        return MarketEventRecord(
            object_ref=object_ref,
            title=title,
            summary=summary,
            content=content,
            event_type=event_type,
            source=source,
            occurred_at=occurred_at,
            data_cutoff=data_cutoff,
            governance_state=self._governance_state,
            lineage=MarketEventLineage(
                source_trace_id=source_trace_id
                if isinstance(source_trace_id, str) and source_trace_id.strip()
                else None
            ),
            source_refs=(source,),
            evidence_refs=(),
        )

    async def resolve_event(
        self, object_ref: MarketObjectRef
    ) -> MarketEventResolutionRecord | None:
        private_id = self._private_id(object_ref)
        if private_id is None:
            return None
        event_row = _as_dict(await self._database_gateway.get_event(private_id))
        if not event_row:
            return None
        source = event_row.get("source")
        updated_at = event_row.get("updated_at")
        return MarketEventResolutionRecord(
            object_ref=object_ref,
            governance_state=self._governance_state,
            source_refs=(source,) if isinstance(source, str) and source.strip() else (),
            data_cutoff=(
                _required_datetime(updated_at, private_id)
                if isinstance(updated_at, datetime)
                else None
            ),
        )

    def _private_id(self, object_ref: MarketObjectRef) -> int | None:
        valid_ref = validate_event_object_ref(object_ref)
        if valid_ref.object_type != EVENT_OBJECT_TYPE:
            raise ValueError("object_ref.object_type is not market.event")
        return self._public_to_private_ids.get(
            _normalize_public_id(valid_ref.object_id)
        )


def _normalize_public_id(public_id: str | UUID) -> str:
    if isinstance(public_id, UUID):
        return str(public_id)
    if isinstance(public_id, str) and public_id.strip():
        return public_id.strip()
    raise ValueError("public event identifiers must be non-empty strings or UUIDs")


def _as_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _required_text(
    row: Mapping[str, Any], field_name: str, private_id: int
) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"event {field_name} is unavailable for private identity {private_id}"
        )
    return value


def _required_datetime(value: Any, private_id: int) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(
            f"event timestamp is unavailable for private identity {private_id}"
        )
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

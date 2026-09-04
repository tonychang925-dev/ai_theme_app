"""M1B deterministic composition of market.event.read into a research request.

This module owns projection and admission only. It does not import Julia Core,
bind a provider, execute research, mint verification authority, or route text.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from stock_processing_service.application.services.julia_domain_adapter.contracts import (
    AdapterErrorCode,
    DomainObservationEnvelope,
    SourceFailure,
)

MARKET_EVENT_READ_OPERATION = "market.event.read"
RESEARCH_EVENT_ENRICH_CAPABILITY = "research.event.enrich"
RESEARCH_EVENT_ENRICH_SCOPE = "research.enrich"
MARKET_EVENT_CONTRACT_VERSION = "market.event.read.v1"

_EVENT_FIELDS = frozenset({
    "event_id", "event_type", "summary", "direction", "confidence", "occurred_at",
    "title", "source_category", "source_name", "source_url", "source_trace_id", "news_id",
})
_REQUIRED_EVENT_STRINGS = frozenset({"event_type", "summary", "source_trace_id"})
_NULLABLE_EVENT_STRINGS = frozenset({"occurred_at", "title", "source_name", "source_url"})
_RELATION_INPUT_FIELDS = frozenset({
    "subject_key", "subject_name", "relation_type", "confidence", "match_reason",
    "evidence", "source", "source_trace_id", "updated_at", "created_at", "run_id",
})
_RELATION_OUTPUT_FIELDS = frozenset(_RELATION_INPUT_FIELDS - {"created_at", "run_id"})
_REQUIRED_RELATION_STRINGS = frozenset({
    "subject_key", "subject_name", "relation_type", "match_reason", "source",
    "source_trace_id", "updated_at",
})


class MarketEventCompositionDecision(str, Enum):
    BUILD_C1_REQUEST = "BUILD_C1_REQUEST"
    BUILD_WITH_PARTIAL_CONTEXT = "BUILD_WITH_PARTIAL_CONTEXT"
    STOP_BEFORE_C1 = "STOP_BEFORE_C1"


@dataclass(frozen=True)
class MarketEventCompositionResult:
    decision: MarketEventCompositionDecision
    market_envelope: DomainObservationEnvelope
    projection_id: str = ""
    effective_correlation_id: str = ""
    market_context: dict[str, Any] | None = None
    capability_request: Any | None = None
    composition_failure: SourceFailure | None = None
    stop_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        request: Any | None = None
        if self.capability_request is not None:
            serialize = getattr(self.capability_request, "to_canonical_dict", None)
            if not callable(serialize):
                serialize = getattr(self.capability_request, "to_dict", None)
            request = serialize() if callable(serialize) else self.capability_request
        return {
            "decision": self.decision.value,
            "market_envelope": self.market_envelope.to_dict(),
            "projection_id": self.projection_id,
            "effective_correlation_id": self.effective_correlation_id,
            "market_context": self.market_context,
            "capability_request": request,
            "composition_failure": self.composition_failure.to_dict() if self.composition_failure else None,
            "stop_reason": self.stop_reason,
        }


class MarketEventResearchComposer:
    """Project one validated M1A envelope into one governed research request."""

    def compose(
        self,
        envelope: DomainObservationEnvelope,
        *,
        research_adapter: Any | None = None,
    ) -> MarketEventCompositionResult:
        if not isinstance(envelope, DomainObservationEnvelope):
            return self._stop(envelope, reason="market input must be a DomainObservationEnvelope")
        if envelope.operation != MARKET_EVENT_READ_OPERATION:
            return self._stop(envelope, reason=f"unsupported market operation: {envelope.operation}")
        if envelope.schema_version != "1.0":
            return self._stop(envelope, reason=f"unsupported market schema version: {envelope.schema_version}")
        if envelope.status in {"error", "unavailable"} or envelope.data_state == "empty":
            code = envelope.failures[0].code if envelope.failures else AdapterErrorCode.INTERNAL_ERROR.value
            return self._stop(envelope, reason=f"market read failed: {code}")
        if envelope.status not in {"success", "partial"} or envelope.data_state != "normal":
            return self._stop(envelope, reason=f"invalid market envelope state: {envelope.status}/{envelope.data_state}")

        payload = envelope.payload
        unknown_payload_fields = set(payload) - {"event", "theme_relations", "missing_fields"}
        if unknown_payload_fields:
            return self._schema_stop(envelope, f"market payload fields not in frozen contract: {sorted(unknown_payload_fields)}")
        if "event" not in payload or "theme_relations" not in payload:
            return self._schema_stop(envelope, "market payload requires event and theme_relations")
        event_value = payload["event"]
        relations_value = payload["theme_relations"]
        if not isinstance(event_value, Mapping):
            return self._schema_stop(envelope, "market payload.event must be an object")
        if not isinstance(relations_value, list):
            return self._schema_stop(envelope, "market payload.theme_relations must be an array")

        relation_state = str(envelope.diagnostics.get("relation_state") or "")
        relation_failed = relation_state == "source_failure" and any(
            record.source_name == "event_subject_map" and record.status == "failed"
            for record in envelope.source_records
        )
        if relation_state not in {"mapped", "empty_not_mapped", "source_failure"}:
            return self._schema_stop(envelope, "market relation_state is not proven")
        if relation_failed and relations_value:
            return self._schema_stop(envelope, "relation failure cannot coexist with retained relations")
        if not relations_value and not relation_failed and relation_state != "empty_not_mapped":
            return self._schema_stop(envelope, "empty relation truth is not proven")

        try:
            projected_event = self._project_event(event_value)
            projected_relations = [self._project_relation(item) for item in relations_value]
        except ValueError as exc:
            return self._schema_stop(envelope, str(exc))

        market_context = {"event": projected_event, "theme_relations": projected_relations}
        projection_id, effective_correlation = self._identities(envelope, market_context)
        if research_adapter is None:
            return MarketEventCompositionResult(
                decision=MarketEventCompositionDecision.STOP_BEFORE_C1,
                market_envelope=envelope,
                projection_id=projection_id,
                effective_correlation_id=effective_correlation,
                market_context=None,
                capability_request=None,
                composition_failure=SourceFailure(
                    code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
                    message="MarketEventResearchAdapter boundary not configured",
                    source_name="m1b_market_event_composition",
                    retryable=True,
                    details={"projection_id": projection_id},
                ),
                stop_reason="research_adapter_not_configured",
            )

        build_request = getattr(research_adapter, "build_request", None)
        if not callable(build_request):
            return self._schema_stop(envelope, "research adapter has no callable build_request")
        try:
            request = build_request(
                market_context,
                correlation_id=effective_correlation,
                capability_request_id=projection_id,
            )
        except Exception as exc:
            return MarketEventCompositionResult(
                decision=MarketEventCompositionDecision.STOP_BEFORE_C1,
                market_envelope=envelope,
                projection_id=projection_id,
                effective_correlation_id=effective_correlation,
                market_context=None,
                composition_failure=SourceFailure(
                    code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                    message=f"C1 request projection failed: {type(exc).__name__}: {exc}",
                    source_name="m1b_market_event_composition",
                    retryable=False,
                    details={"projection_id": projection_id},
                ),
                stop_reason="c1_build_request_failed",
            )

        request_error = self._validate_request(request, market_context, projection_id, effective_correlation)
        if request_error is not None:
            return MarketEventCompositionResult(
                decision=MarketEventCompositionDecision.STOP_BEFORE_C1,
                market_envelope=envelope,
                projection_id=projection_id,
                effective_correlation_id=effective_correlation,
                market_context=None,
                composition_failure=request_error,
                stop_reason="c1_request_contract_mismatch",
            )

        decision = (
            MarketEventCompositionDecision.BUILD_WITH_PARTIAL_CONTEXT
            if envelope.status == "partial" or envelope.failures or relation_failed
            else MarketEventCompositionDecision.BUILD_C1_REQUEST
        )
        return MarketEventCompositionResult(
            decision=decision,
            market_envelope=envelope,
            projection_id=projection_id,
            effective_correlation_id=effective_correlation,
            market_context=market_context,
            capability_request=request,
        )

    def _project_event(self, value: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(value) - _EVENT_FIELDS
        missing = _EVENT_FIELDS - set(value)
        if missing:
            raise ValueError(f"event fields missing: {sorted(missing)}")
        if unknown:
            raise ValueError(f"event fields not in frozen market contract: {sorted(unknown)}")
        for name in _REQUIRED_EVENT_STRINGS:
            self._required_string(value[name], f"event.{name}")
        for name in _NULLABLE_EVENT_STRINGS:
            if value[name] is not None and not isinstance(value[name], str):
                raise ValueError(f"event.{name} must be a string or null")
        event_id = value["event_id"]
        if isinstance(event_id, bool) or not isinstance(event_id, int):
            raise ValueError("event.event_id must be an integer")
        direction = value["direction"]
        if isinstance(direction, bool) or not isinstance(direction, int):
            raise ValueError("event.direction must be an integer")
        confidence = self._finite_float(value["confidence"], "event.confidence")
        news_id = value["news_id"]
        if news_id is not None and (isinstance(news_id, bool) or not isinstance(news_id, int)):
            raise ValueError("event.news_id must be an integer or null")
        if value["source_category"] not in {"news", "intel"}:
            raise ValueError("event.source_category must be news or intel")
        return {
            "event_id": event_id,
            "event_type": value["event_type"],
            "summary": value["summary"],
            "direction": str(direction),
            "confidence": confidence,
            "occurred_at": value["occurred_at"],
            "title": value["title"],
            "source_category": value["source_category"],
            "source_name": value["source_name"],
            "source_url": value["source_url"],
            "source_trace_id": value["source_trace_id"],
            "news_id": news_id,
        }

    def _project_relation(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError("each theme relation must be an object")
        missing = _RELATION_INPUT_FIELDS - set(value)
        unknown = set(value) - _RELATION_INPUT_FIELDS
        if missing:
            raise ValueError(f"theme relation fields missing: {sorted(missing)}")
        if unknown:
            raise ValueError(f"theme relation fields not in market contract: {sorted(unknown)}")
        for name in _REQUIRED_RELATION_STRINGS:
            self._required_string(value[name], f"theme_relation.{name}")
        evidence = value["evidence"]
        try:
            serialized_evidence = json.dumps(
                evidence,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("theme_relation.evidence must be a finite JSON value") from exc
        return {
            "subject_key": value["subject_key"],
            "subject_name": value["subject_name"],
            "relation_type": value["relation_type"],
            "confidence": self._finite_float(value["confidence"], "theme_relation.confidence"),
            "match_reason": value["match_reason"],
            "evidence": serialized_evidence,
            "source": value["source"],
            "source_trace_id": value["source_trace_id"],
            "updated_at": value["updated_at"],
        }

    @staticmethod
    def _required_string(value: Any, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-blank string")

    @staticmethod
    def _finite_float(value: Any, field_name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError(f"{field_name} must be numeric")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{field_name} must be finite")
        return result

    @staticmethod
    def _identities(
        envelope: DomainObservationEnvelope,
        market_context: Mapping[str, Any],
    ) -> tuple[str, str]:
        material = {
            "market_context": market_context,
            "correlation_id": envelope.correlation_id,
            "provider_request_id": envelope.provider_request_id,
            "observed_at": envelope.observed_at,
            "diagnostics": envelope.diagnostics,
            "missing_fields": envelope.payload.get("missing_fields", []),
            "failures": [item.to_dict() for item in envelope.failures],
            "source_records": [item.to_dict() for item in envelope.source_records],
        }
        canonical = json.dumps(
            material,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        correlation = envelope.correlation_id or f"m1b_corr_{digest}"
        return f"cap_req_m1b_{digest}", correlation

    @staticmethod
    def _validate_request(
        request: Any,
        market_context: Mapping[str, Any],
        projection_id: str,
        correlation_id: str,
    ) -> SourceFailure | None:
        capability_id = getattr(request, "capability_id", None)
        request_id = getattr(request, "capability_request_id", None)
        request_correlation = getattr(request, "correlation_id", None)
        scope = getattr(request, "requested_scope", None)
        arguments = getattr(request, "arguments", None)
        if capability_id != RESEARCH_EVENT_ENRICH_CAPABILITY:
            return SourceFailure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="C1 request capability mismatch",
                source_name="m1b_market_event_composition",
                details={"expected_capability": RESEARCH_EVENT_ENRICH_CAPABILITY},
            )
        if request_id != projection_id or request_correlation != correlation_id:
            return SourceFailure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="C1 request identity mismatch",
                source_name="m1b_market_event_composition",
                details={"projection_id": projection_id, "correlation_id": correlation_id},
            )
        if scope != RESEARCH_EVENT_ENRICH_SCOPE:
            return SourceFailure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="C1 request scope mismatch",
                source_name="m1b_market_event_composition",
                details={"expected_scope": RESEARCH_EVENT_ENRICH_SCOPE},
            )
        if arguments != dict(market_context):
            return SourceFailure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="C1 request arguments do not match projected MarketEventContext",
                source_name="m1b_market_event_composition",
                details={"projection_id": projection_id},
            )
        return None

    @staticmethod
    def _stop(
        envelope: DomainObservationEnvelope,
        *,
        reason: str,
    ) -> MarketEventCompositionResult:
        return MarketEventCompositionResult(
            decision=MarketEventCompositionDecision.STOP_BEFORE_C1,
            market_envelope=envelope,
            stop_reason=reason,
        )

    def _schema_stop(
        self,
        envelope: DomainObservationEnvelope,
        reason: str,
    ) -> MarketEventCompositionResult:
        return MarketEventCompositionResult(
            decision=MarketEventCompositionDecision.STOP_BEFORE_C1,
            market_envelope=envelope,
            composition_failure=SourceFailure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message=reason,
                source_name="m1b_market_event_composition",
                retryable=False,
            ),
            stop_reason=reason,
        )


__all__ = [
    "MarketEventCompositionDecision",
    "MarketEventCompositionResult",
    "MarketEventResearchComposer",
]

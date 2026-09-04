"""AT-R1 provider-native wire contracts for Julia Domain Adapter.

This module intentionally defines ai_theme_app-owned DTOs only. It does not
import Julia Core and does not execute market-domain logic. The live adapter
facade/transport belongs to later phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Mapping

ADAPTER_SCHEMA_VERSION = "1.0"
SUPPORTED_OPERATIONS = frozenset({"market.snapshot", "market.alerts", "market.event.read"})
REQUEST_REQUIRED_FIELDS = frozenset({"operation", "arguments", "schema_version"})
REQUEST_ALLOWED_FIELDS = frozenset({
    "operation",
    "arguments",
    "correlation_id",
    "idempotency_key",
    "requested_at",
    "schema_version",
    "trace_metadata",
})
ENVELOPE_REQUIRED_FIELDS = frozenset({
    "operation",
    "status",
    "data_state",
    "payload",
    "source_records",
    "failures",
    "schema_version",
})


class ValidationError(ValueError):
    """Raised when a wire DTO violates the provider-native contract."""


class AdapterStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class DataState(str, Enum):
    NORMAL = "normal"
    EMPTY = "empty"
    STALE = "stale"


class AdapterErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    OPERATION_NOT_SUPPORTED = "OPERATION_NOT_SUPPORTED"
    NOT_FOUND = "NOT_FOUND"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_SECRET_PATTERNS = (
    # URI authority password: postgresql://user:password@host/db
    (re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^\s:/@]+:)([^\s/@]+)(@)"), r"\1***\3"),
    # Redis password-only authority: redis://:password@host/db
    (re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://:)([^\s/@]+)(@)"), r"\1***\3"),
    # key=value style secrets
    (re.compile(r"(?i)\b(password|passwd|token|secret|api_key)\s*=\s*([^\s,;]+)"), r"\1=***"),
)


def redact_diagnostics(value: Any) -> Any:
    """Return a JSON-serializable copy with common secrets redacted.

    AT-R1 only defines redaction behavior for DTO output; it does not inspect
    live services or mutate source data.
    """
    if isinstance(value, str):
        redacted = value
        for pattern, repl in _SECRET_PATTERNS:
            redacted = pattern.sub(repl, redacted)
        return redacted
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if re.search(r"(?i)(password|passwd|token|secret|api_key)", key_str):
                result[key_str] = "***"
            else:
                result[key_str] = redact_diagnostics(item)
        return result
    if isinstance(value, list):
        return [redact_diagnostics(item) for item in value]
    if isinstance(value, tuple):
        return [redact_diagnostics(item) for item in value]
    return value


def _enum_value(enum_cls: type[Enum], value: Any, field_name: str) -> str:
    if isinstance(value, enum_cls):
        return str(value.value)
    try:
        return str(enum_cls(str(value)).value)
    except Exception as exc:
        allowed = ", ".join(item.value for item in enum_cls)  # type: ignore[attr-defined]
        raise ValidationError(f"invalid {field_name}: {value!r}; allowed={allowed}") from exc


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field_name} must be an object")
    return dict(value)


def _require_fields(data: Mapping[str, Any], required: frozenset[str], object_name: str) -> None:
    missing = sorted(field for field in required if field not in data)
    if missing:
        raise ValidationError(f"{object_name} missing required fields: {', '.join(missing)}")


@dataclass(frozen=True)
class AdapterRequest:
    operation: str
    arguments: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    idempotency_key: str = ""
    requested_at: str = ""
    schema_version: str = ADAPTER_SCHEMA_VERSION
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != ADAPTER_SCHEMA_VERSION:
            raise ValidationError(f"unsupported schema_version: {self.schema_version}")
        if self.operation not in SUPPORTED_OPERATIONS:
            raise ValidationError(f"unsupported operation: {self.operation}")
        object.__setattr__(self, "arguments", _require_mapping(self.arguments, "arguments"))
        object.__setattr__(self, "trace_metadata", _require_mapping(self.trace_metadata, "trace_metadata"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AdapterRequest":
        if not isinstance(data, Mapping):
            raise ValidationError("AdapterRequest must be an object")
        _require_fields(data, REQUEST_REQUIRED_FIELDS, "AdapterRequest")
        extra_fields = sorted(set(data) - REQUEST_ALLOWED_FIELDS)
        if extra_fields:
            raise ValidationError(f"AdapterRequest has unsupported fields: {', '.join(extra_fields)}")
        return cls(
            operation=str(data["operation"]),
            arguments=_require_mapping(data["arguments"], "arguments"),
            correlation_id=str(data.get("correlation_id", "")),
            idempotency_key=str(data.get("idempotency_key", "")),
            requested_at=str(data.get("requested_at", "")),
            schema_version=str(data["schema_version"]),
            trace_metadata=_require_mapping(data.get("trace_metadata", {}), "trace_metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "arguments": dict(self.arguments),
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "requested_at": self.requested_at,
            "schema_version": self.schema_version,
            "trace_metadata": dict(self.trace_metadata),
        }


@dataclass(frozen=True)
class SourceFailure:
    code: str
    message: str
    source_name: str = ""
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _enum_value(AdapterErrorCode, self.code, "failure.code")
        object.__setattr__(self, "code", str(AdapterErrorCode(self.code).value))
        object.__setattr__(self, "message", str(redact_diagnostics(self.message)))
        object.__setattr__(self, "details", _require_mapping(redact_diagnostics(self.details), "failure.details"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceFailure":
        if not isinstance(data, Mapping):
            raise ValidationError("SourceFailure must be an object")
        return cls(
            code=str(data.get("code", AdapterErrorCode.INTERNAL_ERROR.value)),
            message=str(data.get("message", "")),
            source_name=str(data.get("source_name", "")),
            retryable=bool(data.get("retryable", False)),
            details=_require_mapping(data.get("details", {}), "failure.details"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "source_name": self.source_name,
            "retryable": self.retryable,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SourceRecord:
    source_type: str
    source_name: str
    source_ref: str = ""
    as_of: str = ""
    observed_at: str = ""
    freshness: str = "fresh"
    status: str = "success"
    provenance: dict[str, Any] = field(default_factory=dict)
    failure: SourceFailure | None = None

    def __post_init__(self) -> None:
        if self.failure is not None and not isinstance(self.failure, SourceFailure):
            object.__setattr__(self, "failure", SourceFailure.from_dict(self.failure))  # type: ignore[arg-type]
        object.__setattr__(self, "provenance", _require_mapping(redact_diagnostics(self.provenance), "provenance"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceRecord":
        if not isinstance(data, Mapping):
            raise ValidationError("SourceRecord must be an object")
        failure = data.get("failure")
        return cls(
            source_type=str(data.get("source_type", "")),
            source_name=str(data.get("source_name", "")),
            source_ref=str(data.get("source_ref", "")),
            as_of=str(data.get("as_of", "")),
            observed_at=str(data.get("observed_at", "")),
            freshness=str(data.get("freshness", "fresh")),
            status=str(data.get("status", "success")),
            provenance=_require_mapping(data.get("provenance", {}), "provenance"),
            failure=SourceFailure.from_dict(failure) if isinstance(failure, Mapping) else None,
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_ref": self.source_ref,
            "as_of": self.as_of,
            "observed_at": self.observed_at,
            "freshness": self.freshness,
            "status": self.status,
            "provenance": dict(self.provenance),
        }
        if self.failure is not None:
            data["failure"] = self.failure.to_dict()
        return data


@dataclass(frozen=True)
class DomainObservationEnvelope:
    operation: str
    status: str
    data_state: str
    correlation_id: str = ""
    provider_request_id: str = ""
    observed_at: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    source_records: list[SourceRecord] = field(default_factory=list)
    failures: list[SourceFailure] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = ADAPTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ADAPTER_SCHEMA_VERSION:
            raise ValidationError(f"unsupported schema_version: {self.schema_version}")
        if self.operation not in SUPPORTED_OPERATIONS:
            raise ValidationError(f"unsupported operation: {self.operation}")
        status = _enum_value(AdapterStatus, self.status, "status")
        data_state = _enum_value(DataState, self.data_state, "data_state")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "data_state", data_state)
        object.__setattr__(self, "payload", _require_mapping(redact_diagnostics(self.payload), "payload"))
        object.__setattr__(self, "diagnostics", _require_mapping(redact_diagnostics(self.diagnostics), "diagnostics"))
        object.__setattr__(self, "source_records", [
            item if isinstance(item, SourceRecord) else SourceRecord.from_dict(item)  # type: ignore[arg-type]
            for item in self.source_records
        ])
        object.__setattr__(self, "failures", [
            item if isinstance(item, SourceFailure) else SourceFailure.from_dict(item)  # type: ignore[arg-type]
            for item in self.failures
        ])
        if status == AdapterStatus.SUCCESS.value and self.failures:
            raise ValidationError("status=success must not include failures; use partial/unavailable/error")
        if status == AdapterStatus.PARTIAL.value and not self.failures:
            raise ValidationError("status=partial requires at least one explicit failure")
        if status == AdapterStatus.PARTIAL.value and data_state == DataState.EMPTY.value:
            raise ValidationError("status=partial requires useful non-empty payload; use unavailable/error for failed empty results")
        if status in {AdapterStatus.UNAVAILABLE.value, AdapterStatus.ERROR.value} and not self.failures:
            raise ValidationError(f"status={status} requires at least one explicit failure")
        if status in {AdapterStatus.UNAVAILABLE.value, AdapterStatus.ERROR.value} and data_state != DataState.EMPTY.value:
            raise ValidationError(f"status={status} requires data_state=empty")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DomainObservationEnvelope":
        if not isinstance(data, Mapping):
            raise ValidationError("DomainObservationEnvelope must be an object")
        _require_fields(data, ENVELOPE_REQUIRED_FIELDS, "DomainObservationEnvelope")
        return cls(
            operation=str(data["operation"]),
            status=str(data["status"]),
            data_state=str(data["data_state"]),
            correlation_id=str(data.get("correlation_id", "")),
            provider_request_id=str(data.get("provider_request_id", "")),
            observed_at=str(data.get("observed_at", "")),
            payload=_require_mapping(data["payload"], "payload"),
            source_records=[SourceRecord.from_dict(item) for item in data["source_records"]],
            failures=[SourceFailure.from_dict(item) for item in data["failures"]],
            diagnostics=_require_mapping(data.get("diagnostics", {}), "diagnostics"),
            schema_version=str(data["schema_version"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "data_state": self.data_state,
            "correlation_id": self.correlation_id,
            "provider_request_id": self.provider_request_id,
            "observed_at": self.observed_at,
            "payload": dict(self.payload),
            "source_records": [item.to_dict() for item in self.source_records],
            "failures": [item.to_dict() for item in self.failures],
            "diagnostics": dict(self.diagnostics),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class HealthReport:
    ok: bool
    ready: bool
    status: str
    checked_at: str = ""
    dependencies: dict[str, Any] = field(default_factory=dict)
    failures: list[SourceFailure] = field(default_factory=list)
    schema_version: str = ADAPTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ADAPTER_SCHEMA_VERSION:
            raise ValidationError(f"unsupported schema_version: {self.schema_version}")
        object.__setattr__(self, "dependencies", _require_mapping(redact_diagnostics(self.dependencies), "dependencies"))
        object.__setattr__(self, "failures", [
            item if isinstance(item, SourceFailure) else SourceFailure.from_dict(item)  # type: ignore[arg-type]
            for item in self.failures
        ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ready": self.ready,
            "status": self.status,
            "checked_at": self.checked_at,
            "dependencies": dict(self.dependencies),
            "failures": [item.to_dict() for item in self.failures],
            "schema_version": self.schema_version,
        }

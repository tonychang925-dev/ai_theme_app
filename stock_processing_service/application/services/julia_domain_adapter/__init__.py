"""Provider-native Julia Domain Adapter wire contracts.

AT-R1 only: contracts/DTOs and schema semantics. No live adapter facade,
transport, MCP entrypoint, Julia Core import, or market algorithm execution.
"""

from .adapter import DomainIntelligenceAdapter
from .contracts import (
    ADAPTER_SCHEMA_VERSION,
    SUPPORTED_OPERATIONS,
    AdapterErrorCode,
    AdapterRequest,
    AdapterStatus,
    DataState,
    DomainObservationEnvelope,
    HealthReport,
    SourceFailure,
    SourceRecord,
    ValidationError,
)

__all__ = [
    "DomainIntelligenceAdapter",
    "ADAPTER_SCHEMA_VERSION",
    "SUPPORTED_OPERATIONS",
    "AdapterErrorCode",
    "AdapterRequest",
    "AdapterStatus",
    "DataState",
    "DomainObservationEnvelope",
    "HealthReport",
    "SourceFailure",
    "SourceRecord",
    "ValidationError",
]

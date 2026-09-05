from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database_service.managers.postgres_manager import PostgresDatabaseManager, _decode_json_array
from stock_processing_service.application.services.julia_domain_adapter import DomainIntelligenceAdapter
from stock_processing_service.application.services.julia_domain_adapter.contracts import AdapterRequest
from stock_processing_service.application.services.julia_domain_adapter.operations.event_resolve import (
    MarketEventResolveOperation,
)


CST = timezone(timedelta(hours=8))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([{"subject_key": "x"}], [{"subject_key": "x"}]),
        ('[{"subject_key":"x"}]', [{"subject_key": "x"}]),
        ("[]", []),
    ],
)
def test_json_array_representations_become_python_lists(value, expected):
    assert _decode_json_array(value, field="matched_subjects") == expected


@pytest.mark.parametrize(
    "value",
    [
        "{malformed",
        "{}",
        7,
        None,
    ],
)
def test_invalid_matched_subjects_representations_fail_closed(value):
    with pytest.raises((TypeError, json.JSONDecodeError)):
        _decode_json_array(value, field="matched_subjects")


@pytest.mark.asyncio
async def test_postgres_projection_returns_candidate_accepted_by_domain_adapter():
    class FakeConnection:
        async def fetch(self, *args, **kwargs):
            return [{
                "market_event_id": 215257,
                "title": "Token出海 canonical event",
                "summary": "",
                "occurred_at": datetime(2026, 7, 19, 18, 46, 35, tzinfo=CST),
                "matched_subjects": json.dumps([{
                    "subject_key": "token_going_global",
                    "subject_name": "Token出海",
                    "relation_type": "primary",
                    "confidence": 1.0,
                }]),
            }]

    class FakePool:
        def acquire(self):
            class Acquisition:
                async def __aenter__(self):
                    return FakeConnection()

                async def __aexit__(self, *args):
                    return None

            return Acquisition()

    manager = PostgresDatabaseManager(SimpleNamespace(postgres_schema="public"))
    manager.pool = FakePool()
    projected = await manager.resolve_market_event_candidates(
        query="Token出海",
        normalized_theme="Token出海",
        time_window={"date": "2026-07-19"},
        limit=20,
    )

    assert isinstance(projected[0]["matched_subjects"], list)
    candidate = MarketEventResolveOperation._candidate(projected[0])
    assert candidate["market_event_id"] == 215257
    assert candidate["matched_subjects"][0]["subject_name"] == "Token出海"


@pytest.mark.asyncio
async def test_candidate_conversion_failure_retains_bounded_diagnostics_without_raw_candidate():
    class FakeGateway:
        async def resolve_market_event_candidates(self, **kwargs):
            return [{
                "market_event_id": 215257,
                "title": "RAW_CANDIDATE_TITLE_MUST_NOT_LEAK",
                "summary": "RAW_CANDIDATE_SUMMARY_MUST_NOT_LEAK",
                "occurred_at": datetime(2026, 7, 19, tzinfo=CST),
                "matched_subjects": 7,
            }]

    class FixedClock:
        def now(self):
            return datetime(2026, 9, 5, 12, tzinfo=CST)

    request = AdapterRequest(
        operation="market.event.resolve",
        arguments={
            "query": "Token出海",
            "normalized_theme": "Token出海",
            "time_window": {"date": "2026-07-19"},
        },
        correlation_id="r9-d2b-correlation",
        idempotency_key="r9-d2b-idempotency",
        trace_metadata={"capability_request_id": "r9-d2b-capability-request"},
    )
    adapter = DomainIntelligenceAdapter(database_gateway=FakeGateway(), clock=FixedClock())

    result = await adapter.execute(request)
    diagnostics = result.failures[0].details["pre_collapse_failure"]

    assert result.status == "unavailable"
    assert result.failures[0].code == "SCHEMA_MISMATCH"
    assert diagnostics["operation_symbol"] == "event_resolve.py:MarketEventResolveOperation.execute"
    assert diagnostics["failure_layer"] == "MarketEventResolveOperation._candidate"
    assert diagnostics["exception_class"] == "TypeError"
    assert diagnostics["exception_message"] == "matched_subjects must be an array"
    assert diagnostics["process_pid"] > 0
    assert diagnostics["observed_at"] == result.observed_at
    assert diagnostics["resolver_query"] == "Token出海"
    assert diagnostics["normalized_theme"] == "Token出海"
    assert diagnostics["time_window"] == {"date": "2026-07-19"}
    assert diagnostics["correlation_id"] == "r9-d2b-correlation"
    assert diagnostics["idempotency_id"] == "r9-d2b-idempotency"
    assert diagnostics["capability_request_id"] == "r9-d2b-capability-request"
    assert diagnostics["candidate_index"] == 0
    assert diagnostics["raw_candidate_count"] == 1
    assert diagnostics["matched_subjects_type"] == "int"
    serialized = str(result.to_dict())
    assert "RAW_CANDIDATE_TITLE_MUST_NOT_LEAK" not in serialized
    assert "RAW_CANDIDATE_SUMMARY_MUST_NOT_LEAK" not in serialized
    assert "traceback" not in serialized.lower()

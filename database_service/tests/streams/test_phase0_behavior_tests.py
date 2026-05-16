"""P1.phase0 runtime behavior tests.

These tests are executable runtime guards for phase0 contract items.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from database_service.streams.handlers.DecisionExecutor import DecisionExecutor


class _DummyDbGateway:
    pass


def _executor() -> DecisionExecutor:
    redis = AsyncMock()
    return DecisionExecutor(redis_client=redis, db_gateway=_DummyDbGateway(), consumer_name="ut_phase0")


# TC-ID: TC-P1P0-001
@pytest.mark.asyncio
async def test_runtime_entry_uses_single_execute_chain():
    exe = _executor()
    exe._execute_action_fixed = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    message = {
        "decision": json.dumps(
            {
                "decision_id": "d-001",
                "event_id": "evt-001",
                "action": "update_theme",
                "payload_version": "v1",
                "trace_id": "trace-001",
                "idempotency_key": "evt-001:update_theme:sha256_abcd",
                "payload": {"k": "v"},
            },
            ensure_ascii=False,
        )
    }

    await exe._process_decision("mid-001", message)

    exe._execute_action_fixed.assert_awaited_once()
    exe.redis.xack.assert_awaited_once()


# TC-ID: TC-P1P0-002
def test_decision_envelope_v1_required_fields_validation():
    exe = _executor()

    # Missing required fields: must fail with explicit contract error.
    normalized, err = exe._normalize_and_validate_decision_envelope(
        {"action": "update_theme", "payload": {"k": "v"}},
        "mid-002",
    )
    assert normalized is None
    assert err is not None
    assert "ERR_CONTRACT_V1_MISSING_FIELDS" in err


# TC-ID: TC-P1P0-003
@pytest.mark.asyncio
async def test_processing_path_does_not_use_print_calls():
    exe = _executor()
    message = {
        "decision": json.dumps(
            {
                "decision_id": "d-003",
                "event_id": "evt-003",
                "action": "unknown_action",
                "payload_version": "v1",
                "trace_id": "trace-003",
                "idempotency_key": "evt-003:unknown_action:sha256_zzzz",
                "payload": {"x": 1},
            },
            ensure_ascii=False,
        )
    }

    with pytest.MonkeyPatch.context() as mp:
        called = {"print_called": False}

        def _fake_print(*_args, **_kwargs):
            called["print_called"] = True

        mp.setattr("builtins.print", _fake_print)
        await exe._process_decision("mid-003", message)

    assert called["print_called"] is False
    exe.redis.xadd.assert_awaited_once()  # dead-letter path


# TC-ID: TC-P1P0-004
def test_trace_id_and_payload_version_are_normalized_for_v0_input():
    exe = _executor()

    normalized, err = exe._normalize_and_validate_decision_envelope(
        {
            "event_id": "evt-004",
            "action": "update_theme",
            "payload": {"a": 1},
        },
        "mid-004",
    )

    assert err is None
    assert normalized is not None
    assert normalized["payload_version"] == "v0"
    assert normalized["trace_id"].startswith("trace_mid_004")
    assert normalized["idempotency_key"].startswith("evt-004:update_theme:sha256_")


# TC-ID: TC-P1P0-005
def test_realtime_auto_theme_creation_is_blocked_by_default():
    exe = _executor()
    decision = {
        "action": "create_new_theme",
        "source": "realtime_match",
        "event_type": "major",
    }
    assert exe._should_block_realtime_theme_creation(decision) is True


# TC-ID: TC-P1P0-006
@pytest.mark.asyncio
async def test_blocked_realtime_decision_enqueues_event_review_queue():
    class _Gateway:
        def __init__(self):
            self.enqueue_event_review = AsyncMock(return_value=True)

    redis = AsyncMock()
    gateway = _Gateway()
    exe = DecisionExecutor(redis_client=redis, db_gateway=gateway, consumer_name="ut_phase0")

    decision = {
        "decision_id": "d-006",
        "event_id": 6006,
        "event_data": {"event_id": 6006, "title": "t"},
        "reason": "blocked_auto_theme_create_for_realtime",
        "confidence": 0.73,
        "theme_data": {"name": "候选题材"},
    }

    await exe._execute_publish_clustering_fixed(decision)

    redis.xadd.assert_awaited_once()
    gateway.enqueue_event_review.assert_awaited_once()


# TC-ID: TC-P1P0-007
@pytest.mark.asyncio
async def test_human_review_action_enqueues_event_review_queue():
    class _Gateway:
        def __init__(self):
            self.enqueue_event_review = AsyncMock(return_value=True)

    redis = AsyncMock()
    gateway = _Gateway()
    exe = DecisionExecutor(redis_client=redis, db_gateway=gateway, consumer_name="ut_phase0")

    decision = {
        "decision_id": "d-007",
        "event_id": 7007,
        "event_data": {"event_id": 7007, "title": "待复核事件"},
        "action": "human_review",
        "reason": "theme_match_human_review",
        "source": "structured_theme_match",
        "confidence": 0.66,
        "theme_data": {"name": "候选题材"},
    }

    await exe._execute_action_fixed("human_review", decision, "mid-007", {})

    gateway.enqueue_event_review.assert_awaited_once_with(
        event_id=7007,
        reason="theme_match_human_review",
        source_channel="structured_theme_match",
        proposed_theme_name="候选题材",
        proposed_theme_confidence=0.66,
    )
    assert exe.stats["review_queue_enqueued"] == 1


# TC-ID: TC-P1P0-008
@pytest.mark.asyncio
async def test_unknown_action_still_uses_pending_not_human_review():
    class _Gateway:
        def __init__(self):
            self.enqueue_event_review = AsyncMock(return_value=True)

    redis = AsyncMock()
    gateway = _Gateway()
    exe = DecisionExecutor(redis_client=redis, db_gateway=gateway, consumer_name="ut_phase0")

    decision = {
        "decision_id": "d-008",
        "event_id": 8008,
        "event_data": {"event_id": 8008, "title": "unknown"},
        "action": "publish_clustering",
        "reason": "UNKNOWN",
    }

    await exe._execute_action_fixed("publish_clustering", decision, "mid-008", {})

    redis.xadd.assert_awaited_once()
    gateway.enqueue_event_review.assert_not_awaited()

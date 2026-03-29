"""P1.phase1 behavior tests on real stream architecture.

This suite uses the real pipeline:
- stream:events:normal/major -> ThemeProcessor
- stream:events:decision -> DecisionExecutor
- stream:events:pending / stream:themes:updates / stream:dead:letter

No mock/stub/fake for Redis/PostgreSQL.

TC-ID coverage tags:
- TC-P1P1-004C (phase-level stream regression suite coverage)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass

import asyncpg
import pytest
import pytest_asyncio
import redis.asyncio as aioredis

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import get_gateway
from database_service.streams.handlers.DecisionExecutor import DecisionExecutor
from database_service.streams.handlers.theme_processor import ThemeProcessor


STREAMS = [
    "stream:events:normal",
    "stream:events:major",
    "stream:events:pending",
    "stream:events:decision",
    "stream:themes:updates",
    "stream:dead:letter",
]


def _pg_connect_kwargs() -> dict:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    }


async def _cleanup_streams(redis_client):
    for stream in STREAMS:
        try:
            await redis_client.delete(stream)
        except Exception:
            pass


async def _wait_for_xlen(redis_client, stream_name: str, at_least: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if int(await redis_client.xlen(stream_name)) >= at_least:
            return True
        await asyncio.sleep(0.2)
    return False


async def _assert_required_schema_exists(conn: asyncpg.Connection) -> None:
    for table_name in ("financial_categories", "theme_master"):
        exists = await conn.fetchval(
            """
            SELECT EXISTS(
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema='public' AND table_name=$1
            )
            """,
            table_name,
        )
        assert exists is True, f"required table missing: public.{table_name}"


async def _assert_required_schema_exists_once() -> None:
    conn = await asyncpg.connect(**_pg_connect_kwargs())
    try:
        await _assert_required_schema_exists(conn)
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def redis_client():
    # ThemeProcessor uses host/port without db argument, so suite must use db0
    client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    try:
        if await client.ping() is not True:
            pytest.fail("Redis ping failed on localhost:6379/0")
    except Exception as exc:
        pytest.fail(f"Redis is required for phase1 behavior tests: {exc}")

    await _cleanup_streams(client)
    try:
        yield client
    finally:
        await _cleanup_streams(client)
        try:
            if hasattr(client, "aclose"):
                await client.aclose()
            else:
                await client.close()
        except RuntimeError:
            pass


@dataclass
class Runtime:
    processor: ThemeProcessor
    decision_executor: DecisionExecutor
    processor_tasks: list
    decision_tasks: list
    gateway: object


@pytest_asyncio.fixture
async def runtime(redis_client):
    # Force gateway to use real stock_data_test
    cfg = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
    )
    cfg.redis.enabled = False
    init_config(cfg)

    # Reset stream gateway singleton to avoid stale disconnected managers across tests
    try:
        import database_service.streams.gateway_integration as gateway_integration
        if getattr(gateway_integration, "_stream_enhanced_gateway", None) is not None:
            old_gateway = gateway_integration._stream_enhanced_gateway
            if hasattr(old_gateway, "close"):
                await old_gateway.close()
        gateway_integration._stream_enhanced_gateway = None
    except Exception:
        pass

    gateway = await get_gateway()
    processor = ThemeProcessor(
        redis_host="localhost",
        redis_port=6379,
        consumer_name=f"it_phase1_processor_{uuid.uuid4().hex[:8]}",
        enable_clustering=False,
        enable_classification_first=True,
        enable_decision_executor=True,
    )
    ok = await processor.initialize()
    if not ok:
        pytest.fail("ThemeProcessor initialize() failed")
    processor_tasks = await processor.start()

    decision_executor = DecisionExecutor(
        redis_client=redis_client,
        db_gateway=gateway,
        consumer_name=f"it_phase1_executor_{uuid.uuid4().hex[:8]}",
    )
    decision_tasks = await decision_executor.start()

    # wait background loops ready
    await asyncio.sleep(1.0)
    rt = Runtime(
        processor=processor,
        decision_executor=decision_executor,
        processor_tasks=processor_tasks,
        decision_tasks=decision_tasks,
        gateway=gateway,
    )
    try:
        yield rt
    finally:
        try:
            await processor.stop()
        except Exception:
            pass
        try:
            await decision_executor.stop()
        except Exception:
            pass
        for t in list(processor_tasks) + list(decision_tasks):
            if t and not t.done():
                t.cancel()
        try:
            await asyncio.gather(*(list(processor_tasks) + list(decision_tasks)), return_exceptions=True)
        except Exception:
            pass
        try:
            if hasattr(gateway, "close"):
                await gateway.close()
        except Exception:
            pass


def _normal_event(uid: str, title: str, concept: str) -> dict:
    return {
        "event_id": f"evt-{uid}",
        "event_type": "normal",
        "title": title,
        "content": f"{title}：{concept} 相关市场动态",
        "ai_analysis": {
            "core_concept": concept,
            "industry_keywords": [concept, "市场", "行业"],
            "concept_confidence": 0.82,
            "impact_level": "medium",
        },
        "source": "pytest_phase1",
        "publish_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "test_flag": True,
    }


async def _publish_normal_event(redis_client, event: dict):
    payload = {
        "event_data": json.dumps(event, ensure_ascii=False),
        "publisher": "pytest_phase1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return await redis_client.xadd("stream:events:normal", payload, maxlen=2000)


# TC-ID: TC-P1P1-004C
@pytest.mark.asyncio
async def test_normal_event_enters_real_stream_pipeline(redis_client, runtime):
    """Verify normal event is consumed by ThemeProcessor and produces decision stream output."""
    await _assert_required_schema_exists_once()
    uid = uuid.uuid4().hex[:8]
    event = _normal_event(uid, "半导体产业链新进展", "半导体")
    await _publish_normal_event(redis_client, event)

    ready = await _wait_for_xlen(redis_client, "stream:events:decision", at_least=1, timeout=20)
    assert ready is True, "no decision produced from normal stream event"

    decisions = await redis_client.xrange("stream:events:decision", "-", "+", count=10)
    assert len(decisions) >= 1
    latest = json.loads(decisions[-1][1]["decision"])
    assert latest.get("event_id") == event["event_id"]
    assert latest.get("action") in {"update_theme", "publish_clustering", "create_new_theme"}


# TC-ID: TC-P1P1-004
@pytest.mark.asyncio
async def test_normal_unmatched_event_flows_to_pending_via_decision_executor(redis_client, runtime):
    """ACC-P1-P1-03: normal未匹配时，必须publish_clustering并ACK后写入pending且具备trace_id/decision_id。"""
    await _assert_required_schema_exists_once()
    assert runtime.processor.enable_classification_first is True, "must run with classification-first framework"
    status_before = await runtime.processor.get_status()
    cls_before = status_before.get("classification_first", {}).get("stats", {})
    infer_before = int(cls_before.get("category_inferences", 0))
    matched_before = int(cls_before.get("category_matched", 0))
    not_matched_before = int(cls_before.get("category_not_matched", 0))

    uid = uuid.uuid4().hex[:8]
    # use an intentionally novel concept to maximize no-match path
    event = _normal_event(uid, "量子生物计算跨域事件", f"QBIO-{uid}")
    await _publish_normal_event(redis_client, event)

    decision_ready = await _wait_for_xlen(redis_client, "stream:events:decision", at_least=1, timeout=20)
    assert decision_ready is True, "no decision produced for unmatched normal event"

    decision_entries = await redis_client.xrange("stream:events:decision", "-", "+", count=20)
    matched_decision_id = None
    matched_decision_msg_id = None
    matched_trace_id = None
    for msg_id, fields in reversed(decision_entries):
        raw = fields.get("decision")
        if not raw:
            continue
        parsed = json.loads(raw)
        if parsed.get("event_id") != event["event_id"]:
            continue
        matched_decision_msg_id = msg_id
        assert parsed.get("decision_type") in {
            "category_no_match",
            "no_match_in_category",
            "no_match_after_fallback",
        }, "must be a real unmatched-flow decision type"
        reason = str(parsed.get("reason", ""))
        assert ("未匹配" in reason) or ("匹配失败" in reason), "unmatched flow must include failure reason"
        assert parsed.get("action") == "publish_clustering", "unmatched normal must publish_clustering"
        assert parsed.get("decision_id"), "decision_id is required in decision payload"
        assert parsed.get("trace_id"), "trace_id is required in decision payload"
        matched_decision_id = parsed.get("decision_id")
        matched_trace_id = parsed.get("trace_id")
        break

    assert matched_decision_id is not None, "cannot find matched decision for current event"
    assert matched_decision_msg_id is not None
    pending_ready = await _wait_for_xlen(redis_client, "stream:events:pending", at_least=1, timeout=20)
    assert pending_ready is True, "no pending event published by DecisionExecutor"

    pending_entries = await redis_client.xrange("stream:events:pending", "-", "+", count=20)
    assert len(pending_entries) >= 1
    matched_pending_payload = None
    matched_pending_decision_id = None
    for _, fields in reversed(pending_entries):
        event_data_raw = fields.get("event_data")
        if not event_data_raw:
            continue
        payload = json.loads(event_data_raw)
        if payload.get("event_id") != event["event_id"]:
            continue
        matched_pending_payload = payload
        matched_pending_decision_id = fields.get("decision_id")
        break

    assert matched_pending_payload is not None, "pending stream missing matched event_data"
    assert matched_pending_decision_id == matched_decision_id, "pending decision_id must match decision payload"
    assert matched_pending_payload.get("trace_id"), "pending event_data must include trace_id"
    assert matched_pending_payload.get("trace_id") == matched_trace_id

    # 原消息ACK验证：该decision消息不应再出现在consumer group pending列表中
    pending_meta = await redis_client.xpending("stream:events:decision", "decision_executors")
    if int(pending_meta.get("pending", 0)) > 0:
        pending_msgs = await redis_client.xpending_range(
            "stream:events:decision",
            "decision_executors",
            "-",
            "+",
            int(pending_meta["pending"]),
        )
        pending_ids = {m.get("message_id") for m in pending_msgs}
        assert matched_decision_msg_id not in pending_ids, "decision message should be ACKed"

    status_after = await runtime.processor.get_status()
    last_processed = status_after.get("stats", {}).get("last_processed", {})
    assert last_processed.get("mode") == "classification_first", "event must be processed by classification-first mode"
    assert last_processed.get("event_id") == event["event_id"], "last processed event should match current test event"

    cls_after = status_after.get("classification_first", {}).get("stats", {})
    infer_after = int(cls_after.get("category_inferences", 0))
    matched_after = int(cls_after.get("category_matched", 0))
    not_matched_after = int(cls_after.get("category_not_matched", 0))
    assert infer_after >= infer_before + 1, "classification-first inference process was not executed"
    assert (matched_after + not_matched_after) >= (matched_before + not_matched_before + 1), (
        "classification-first branch counters did not advance"
    )


# TC-ID: TC-P1P1-003
@pytest.mark.asyncio
async def test_duplicate_skip_for_same_idempotency_key(redis_client, runtime):
    """Real stream path for dedup: inject duplicate decisions into stream:events:decision."""
    await _assert_required_schema_exists_once()
    uid = uuid.uuid4().hex[:8]
    event_id = f"evt-dup-{uid}"
    decision = {
        "decision_id": f"decision-dup-{uid}",
        "event_id": event_id,
        "action": "publish_clustering",
        "payload_version": "v1",
        "trace_id": f"trace-dup-{uid}",
        "idempotency_key": f"{event_id}:publish_clustering:sha256_same",
        "payload": {"ok": True},
        "event_data": {"event_id": event_id, "trace_id": f"trace-dup-{uid}"},
    }
    message = {"decision": json.dumps(decision, ensure_ascii=False)}
    await redis_client.xadd("stream:events:decision", message, maxlen=2000)
    await redis_client.xadd("stream:events:decision", message, maxlen=2000)

    ready = await _wait_for_xlen(redis_client, "stream:events:pending", at_least=1, timeout=20)
    assert ready is True
    # dedup expected: only one pending output for same idempotency key
    pending_len = int(await redis_client.xlen("stream:events:pending"))
    assert pending_len == 1


# TC-ID: TC-P1P1-002
@pytest.mark.asyncio
async def test_strict_schema_missing_required_field_goes_dead_letter(redis_client, runtime):
    """Invalid v1 envelope should be moved to dead-letter by DecisionExecutor stream consumer."""
    await _assert_required_schema_exists_once()
    uid = uuid.uuid4().hex[:8]
    bad = {
        "decision": json.dumps(
            {
                "action": "update_theme",
                "payload": {"x": 1},
                "marker": uid,
            },
            ensure_ascii=False,
        )
    }
    await redis_client.xadd("stream:events:decision", bad, maxlen=2000)

    ready = await _wait_for_xlen(redis_client, "stream:dead:letter", at_least=1, timeout=20)
    assert ready is True
    dead = await redis_client.xrange("stream:dead:letter", "-", "+", count=5)
    assert len(dead) >= 1
    reason = dead[-1][1].get("reason", "")
    assert "ERR_CONTRACT_V1_MISSING_FIELDS" in reason or "ERR_CONTRACT" in reason


# TC-ID: TC-P1P1-001
@pytest.mark.asyncio
async def test_unknown_action_fail_fast_to_dead_letter_behavior(redis_client, runtime):
    """Unknown action from decision stream should fail-fast into dead-letter."""
    await _assert_required_schema_exists_once()
    uid = uuid.uuid4().hex[:8]
    event_id = f"evt-unknown-{uid}"
    decision = {
        "decision_id": f"decision-unknown-{uid}",
        "event_id": event_id,
        "action": "unknown_action",
        "payload_version": "v1",
        "trace_id": f"trace-unknown-{uid}",
        "idempotency_key": f"{event_id}:unknown_action:sha256_x",
        "payload": {"x": 1},
    }
    await redis_client.xadd("stream:events:decision", {"decision": json.dumps(decision, ensure_ascii=False)}, maxlen=2000)

    ready = await _wait_for_xlen(redis_client, "stream:dead:letter", at_least=1, timeout=20)
    assert ready is True
    dead = await redis_client.xrange("stream:dead:letter", "-", "+", count=5)
    assert len(dead) >= 1
    assert "未知决策类型" in dead[-1][1].get("reason", "")


# TC-ID: TC-P1P1-004B
@pytest.mark.asyncio
async def test_phase1_dataset_baseline_via_test_theme_processor():
    """Reuse project baseline RealIntegrationTester.test_new_architecture_with_dataset for real process validation."""
    from database_service.scripts.test_theme_processor import RealIntegrationTester
    import database_service.streams.gateway_integration as gateway_integration

    tester = RealIntegrationTester()
    try:
        # Avoid stale singleton from previous tests: baseline script must run on fresh real gateway
        old_gateway = getattr(gateway_integration, "_stream_enhanced_gateway", None)
        if old_gateway is not None and hasattr(old_gateway, "close"):
            await old_gateway.close()
        gateway_integration._stream_enhanced_gateway = None

        setup_ok = await tester.setup()
        assert setup_ok is True, "RealIntegrationTester setup failed"

        baseline_result = await tester.test_new_architecture_with_dataset(sample_size=6, return_details=True)
        assert isinstance(baseline_result, dict), "baseline must return structured details"
        assert baseline_result.get("success") is True, "dataset baseline process validation failed"

        t04 = baseline_result.get("t04_validation", {})
        assert t04.get("publish_clustering_decision") is True, "missing publish_clustering decision evidence"
        assert t04.get("pending_written") is True, "missing pending stream evidence"
        assert t04.get("pending_matches_publish_decision_id") is True, "pending decision_id does not match publish decision"
        assert t04.get("pending_trace_id_present") is True, "missing trace_id in pending payload"
        assert t04.get("decision_ack_verified") is True, "decision ACK verification failed"
    finally:
        await tester.cleanup()


# TC-ID: TC-P1P1-005
@pytest.mark.asyncio
async def test_failure_message_controlled_to_dead_letter_no_hang(redis_client, runtime):
    """Two consecutive failing decisions should both go dead-letter, proving failure path is controlled and not hanging."""
    await _assert_required_schema_exists_once()
    base_dead = int(await redis_client.xlen("stream:dead:letter"))

    async def _push_unknown(uid: str):
        event_id = f"evt-fail-{uid}"
        decision = {
            "decision_id": f"decision-fail-{uid}",
            "event_id": event_id,
            "action": "unknown_action",
            "payload_version": "v1",
            "trace_id": f"trace-fail-{uid}",
            "idempotency_key": f"{event_id}:unknown_action:sha256_x",
            "payload": {"x": 1},
        }
        await redis_client.xadd(
            "stream:events:decision",
            {"decision": json.dumps(decision, ensure_ascii=False)},
            maxlen=2000,
        )

    uid1 = uuid.uuid4().hex[:8]
    uid2 = uuid.uuid4().hex[:8]
    await _push_unknown(uid1)
    await _push_unknown(uid2)

    ready = await _wait_for_xlen(redis_client, "stream:dead:letter", at_least=base_dead + 2, timeout=20)
    assert ready is True, "failing decisions were not controlled into dead-letter in time"

    # No hang: after consecutive failures, consumer must continue processing new failing messages.
    uid3 = uuid.uuid4().hex[:8]
    await _push_unknown(uid3)
    ready3 = await _wait_for_xlen(redis_client, "stream:dead:letter", at_least=base_dead + 3, timeout=20)
    assert ready3 is True, "consumer appears stuck after failures; dead-letter did not continue growing"

    # Runtime liveness: decision executor tasks should still be running.
    assert any(t and (not t.done()) for t in runtime.decision_tasks), "decision executor tasks are not alive"

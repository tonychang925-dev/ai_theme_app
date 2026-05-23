import json
from pathlib import Path

import pytest

from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.services.local_qwen_triage_service import LocalQwenNewsTriageService
from database_service.streams.services.review_eligibility import should_enter_human_review


ROOT = Path(__file__).resolve().parents[3]
PHASE3_EVAL = ROOT / "theme_service" / "eval" / "product_runtime_phase3"
PHASE3B_EVAL = ROOT / "theme_service" / "eval" / "product_runtime_phase3b"


class _EventBus:
    def __init__(self):
        self.published = []

    async def publish_to_stream(self, stream_key, data):
        self.published.append((stream_key, data))
        return f"msg-{len(self.published)}"


class _Gateway:
    def __init__(self):
        self.events = []

    async def create_news_event(self, event_data):
        self.events.append(event_data)
        return len(self.events)


class _MustNotStructurize:
    def __init__(self):
        self.calls = 0

    async def extract_event(self, _news_data):
        self.calls += 1
        raise AssertionError("Phase 3 SKIP/REVIEW news must not enter structuring")


def _jsonl(name):
    path = PHASE3_EVAL / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _jsonl_phase3b(name):
    path = PHASE3B_EVAL / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("case", _jsonl("importance_triage_hard_negatives.jsonl"), ids=lambda row: row["case_id"])
def test_tc_phase3_low_value_cases_skip_before_structuring(case):
    service = LocalQwenNewsTriageService({"enable_local_triage": False})

    result = service.evaluate(case)

    assert result["decision"] == case["expected_decision"]
    assert result["should_structurize"] is False
    assert result["should_publish_structured_stream"] is False
    assert result["should_enter_theme_match"] is False
    assert result["should_enter_premarket_major_events"] is False
    assert result["event_value_type"] == "low_value_disclosure"
    assert result["dedupe_key"]


@pytest.mark.parametrize("case", _jsonl("review_queue_hygiene_hard_negatives.jsonl"), ids=lambda row: row["case_id"])
def test_tc_phase3a_low_value_cases_skip_and_must_not_enter_review(case):
    service = LocalQwenNewsTriageService({"enable_local_triage": False})

    result = service.evaluate(case)

    assert result["decision"] == "SKIP"
    assert result["should_structurize"] is False
    assert result["should_publish_structured_stream"] is False
    assert result["should_enter_theme_match"] is False
    assert result["should_enter_premarket_major_events"] is False
    assert result["event_value_type"] == "low_value_disclosure"
    assert result["should_enter_review"] is False


@pytest.mark.parametrize("case", _jsonl("importance_triage_positive_cases.jsonl"), ids=lambda row: row["case_id"])
def test_tc_phase3_important_cases_pass_to_structuring(case):
    service = LocalQwenNewsTriageService({"enable_local_triage": False})

    result = service.evaluate(case)

    assert result["decision"] == case["expected_decision"]
    assert result["should_structurize"] is True
    assert result["should_enter_theme_match"] is True
    assert result["importance_level"] in {"S", "A", "B"}


@pytest.mark.parametrize("case", _jsonl_phase3b("review_eligibility_hard_negatives.jsonl"), ids=lambda row: row["case_id"])
def test_tc_phase3b_low_value_and_weak_events_do_not_enter_review(case):
    result = should_enter_human_review(
        {"title": case["title"], "summary": case["summary"]},
        {"reason_code": case["reason_code"], "runtime_source": "v1_fallback"},
        case.get("triage_result") or {},
    )

    assert result["should_keep_review"] is case["expected_should_keep_review"]
    assert result["suggested_action"] == case["expected_suggested_action"]


@pytest.mark.parametrize("case", _jsonl_phase3b("review_eligibility_positive_cases.jsonl"), ids=lambda row: row["case_id"])
def test_tc_phase3b_high_value_uncertain_events_can_enter_review(case):
    result = should_enter_human_review(
        {"title": case["title"], "summary": case["summary"]},
        {"reason_code": case["reason_code"], "runtime_source": "v2_accepted"},
        case["triage_result"],
    )

    assert result["should_keep_review"] is case["expected_should_keep_review"]
    assert result["suggested_action"] == "keep_review"


@pytest.mark.asyncio
async def test_tc_phase3_processor_skip_persists_triage_audit_without_structuring():
    service = _MustNotStructurize()
    event_bus = _EventBus()
    gateway = _Gateway()
    processor = NewsStreamProcessor(
        event_bus=event_bus,
        config={"database_gateway": gateway, "enable_local_triage": False, "enable_ai_analysis": True},
        business_services={"model_service": service},
    )
    processor.local_triage_service = LocalQwenNewsTriageService({"enable_local_triage": False})

    result = await processor._process_news_stored_event(
        {
            "id": 1,
            "news_row_id": 1,
            "news_id": "phase3-low-value",
            "title": "智度股份：收到广东证监局行政监管措施决定书",
            "content": "行政监管措施决定书要求公司整改。",
            "publish_date": "2026-05-22",
        }
    )

    assert service.calls == 0
    assert result["results"]["local_triage"]["decision"] == "SKIP"
    assert result["results"]["news_event_persistence"]["structured_stream_published"] is False
    assert result["results"]["structured_event"]["theme_directive"]["triage_result"]["should_enter_theme_match"] is False
    assert event_bus.published == []
    stats = await processor.get_business_stats()
    assert stats["triage_skip_count"] == 1
    assert stats["triage_structuring_saved_count"] == 1
    assert stats["low_value_triage_skip_count"] == 1

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class P2Phase0RunContext:
    run_id: str
    sample_size: int
    source_tag: str = "validation_dataset"
    trace_prefix: str = "p2.phase0"
    test_flag: bool = True


@dataclass(slots=True)
class RawNewsEnvelope:
    raw_news_id: str
    trace_id: str
    payload: dict[str, Any]


@dataclass(slots=True)
class NewsRawPersistenceEvidence:
    raw_news_ids: list[str] = field(default_factory=list)
    persisted_news_ids: list[int] = field(default_factory=list)
    success_count: int = 0


@dataclass(slots=True)
class StructuredEventEvidence:
    news_event_ids: list[int] = field(default_factory=list)
    llm_request_ids: list[str] = field(default_factory=list)
    success_count: int = 0


@dataclass(slots=True)
class ThemeDecisionEvidence:
    decision_ids: list[str] = field(default_factory=list)
    final_decisions: list[str] = field(default_factory=list)
    success_count: int = 0


@dataclass(slots=True)
class ExecutionEvidence:
    mapped_event_ids: list[int] = field(default_factory=list)
    pending_event_ids: list[int] = field(default_factory=list)
    review_event_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class PipelineAuditBundle:
    run_context: P2Phase0RunContext
    news_raw: NewsRawPersistenceEvidence
    structured: StructuredEventEvidence
    decisions: ThemeDecisionEvidence
    execution: ExecutionEvidence
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class P2Phase0HarnessReport:
    run_id: str
    summary: dict[str, Any]
    bundle: PipelineAuditBundle


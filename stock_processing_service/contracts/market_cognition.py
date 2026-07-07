from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceCoverage:
    module: str
    status: str
    row_count: int
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QualityEnvelope:
    status: str
    score: float
    missing_modules: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    ref_id: str
    source_module: str
    source_path: str
    source_snapshot_id: str


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    key: str
    value: Any
    ref: EvidenceRef
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class MarketKnowledgeBundle:
    bundle_id: str
    schema_version: str
    trade_date: str
    as_of: datetime
    knowledge: Mapping[str, Any]
    source_snapshot_ids: tuple[str, ...]
    producer_versions: tuple[tuple[str, str], ...]
    module_coverage: tuple[SourceCoverage, ...]
    quality: QualityEnvelope
    content_hash: str

    def coverage_for(self, module: str) -> SourceCoverage:
        return next(
            (
                coverage
                for coverage in self.module_coverage
                if coverage.module == module
            ),
            SourceCoverage(module=module, status="missing", row_count=0),
        )


@dataclass(frozen=True, slots=True)
class MarketEvidenceSnapshot:
    snapshot_id: str
    schema_version: str
    trade_date: str
    as_of: datetime
    evidence: tuple[EvidenceItem, ...]
    module_coverage: tuple[SourceCoverage, ...]
    quality: QualityEnvelope
    source_bundle_id: str
    content_hash: str

    def get(self, key: str) -> EvidenceItem | None:
        return next((item for item in self.evidence if item.key == key), None)

    def coverage_for(self, module: str) -> SourceCoverage:
        return next(
            (
                coverage
                for coverage in self.module_coverage
                if coverage.module == module
            ),
            SourceCoverage(module=module, status="missing", row_count=0),
        )

    @property
    def evidence_ref_coverage(self) -> float:
        if not self.evidence:
            return 1.0
        referenced = sum(1 for item in self.evidence if item.ref.ref_id)
        return referenced / len(self.evidence)


@dataclass(frozen=True, slots=True)
class MarketContextSnapshot:
    context_id: str
    schema_version: str
    context_version: int
    context_type: str
    trade_date: str
    as_of: datetime
    status: str
    dominant_tensions: tuple[str, ...]
    active_transitions: tuple[str, ...]
    evidence_refs: tuple[EvidenceRef, ...]
    quality: QualityEnvelope
    content_hash: str


@dataclass(frozen=True, slots=True)
class BeliefState:
    proposition_key: str
    score: float
    confidence: float
    support_refs: tuple[EvidenceRef, ...]
    counter_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True, slots=True)
class HypothesisState:
    hypothesis_id: str
    statement: str
    status: str
    probability: float
    deadline: str
    expected_observations: tuple[str, ...]
    falsifiers: tuple[str, ...]
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class CognitionState:
    state_id: str
    schema_version: str
    trade_date: str
    as_of: datetime
    context_id: str
    beliefs: tuple[BeliefState, ...]
    hypotheses: tuple[HypothesisState, ...]
    policy_version: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ThesisStatement:
    statement: str
    evidence_refs: tuple[EvidenceRef, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class ScenarioView:
    condition: str
    expected_result: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class MarketThesisSnapshot:
    thesis_id: str
    schema_version: str
    trade_date: str
    as_of: datetime
    status: str
    primary_thesis: ThesisStatement | None
    hypothesis_results: tuple[str, ...]
    key_belief_changes: tuple[str, ...]
    scenarios: tuple[ScenarioView, ...]
    invalidation_conditions: tuple[str, ...]
    trading_permission: str
    evidence_refs: tuple[EvidenceRef, ...]
    cognition_state_id: str
    quality: QualityEnvelope
    unsupported_claim_count: int
    evidence_ref_coverage: float
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class Phase0CognitionResult:
    context: MarketContextSnapshot
    cognition: CognitionState
    thesis: MarketThesisSnapshot
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    status: str
    failed_stage: str | None
    layer_hashes: Mapping[str, str]
    thesis: MarketThesisSnapshot | None
    decision_unchanged: bool
    diagnostics: tuple[str, ...]

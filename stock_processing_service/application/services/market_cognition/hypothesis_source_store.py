from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stock_processing_service.application.services.market_cognition.verification import (
    FrozenHypothesisSource,
    MarketThesisVerificationService,
)
from stock_processing_service.contracts.market_cognition import (
    EvidenceRef,
    HypothesisState,
    canonical_hash,
)


class HypothesisSourceStoreError(RuntimeError):
    """Base error for frozen validation sources."""


class HypothesisSourceConflictError(HypothesisSourceStoreError):
    """Raised when a frozen hypothesis identity is changed after close."""


class HypothesisSourceCorruptionError(HypothesisSourceStoreError):
    """Raised when a persisted source cannot reproduce its source hash."""


@dataclass(frozen=True, slots=True)
class SourceAppendResult:
    status: str
    path: Path
    source_hash: str


class FrozenHypothesisSourceStore:
    """Create-only store that prevents next-day reconstruction of yesterday."""

    SCHEMA_VERSION = "frozen_hypothesis_source.v1"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def append(self, source: FrozenHypothesisSource) -> SourceAppendResult:
        MarketThesisVerificationService.check_eligibility(source)
        path = self._path_for(source)
        payload = self._serialize(source)
        source_hash = payload["source_hash"]
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(
                    payload,
                    stream,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                stream.write("\n")
        except FileExistsError:
            existing = self._read_payload(path)
            if existing["source_hash"] == source_hash:
                return SourceAppendResult("duplicate", path, source_hash)
            raise HypothesisSourceConflictError(
                "frozen hypothesis conflict for "
                f"{source.hypothesis.hypothesis_id} at {path}"
            )
        return SourceAppendResult("created", path, source_hash)

    def read(self, path: Path | str) -> FrozenHypothesisSource:
        return self._deserialize(self._read_payload(Path(path)))

    def list_sources(self) -> list[FrozenHypothesisSource]:
        return [self.read(path) for path in sorted(self.root.glob("*/*/*.json"))]

    def _path_for(self, source: FrozenHypothesisSource) -> Path:
        try:
            trade_date = date.fromisoformat(source.thesis_trade_date)
        except ValueError as exc:
            raise ValueError("thesis_trade_date must use valid YYYY-MM-DD") from exc
        identity_hash = canonical_hash(
            {
                "thesis_trade_date": source.thesis_trade_date,
                "hypothesis_id": source.hypothesis.hypothesis_id,
            }
        )[:24]
        return (
            self.root
            / str(trade_date.year)
            / f"{trade_date.month:02d}"
            / f"{trade_date.strftime('%Y%m%d')}_{identity_hash}.json"
        )

    @classmethod
    def _serialize(cls, source: FrozenHypothesisSource) -> dict[str, Any]:
        hypothesis = source.hypothesis
        core = {
            "schema_version": cls.SCHEMA_VERSION,
            "thesis_trade_date": source.thesis_trade_date,
            "source_snapshot_id": source.source_snapshot_id,
            "source_as_of": source.source_as_of.isoformat(),
            "source_knowledge_hash": source.source_knowledge_hash,
            "source_evidence_hash": source.source_evidence_hash,
            "source_context_hash": source.source_context_hash,
            "source_thesis_hash": source.source_thesis_hash,
            "source_quality_status": source.source_quality_status,
            "source_quality_score": source.source_quality_score,
            "source_policy_version": source.source_policy_version,
            "hypothesis": {
                "hypothesis_id": hypothesis.hypothesis_id,
                "statement": hypothesis.statement,
                "status": hypothesis.status,
                "probability": hypothesis.probability,
                "deadline": hypothesis.deadline,
                "expected_observations": list(hypothesis.expected_observations),
                "falsifiers": list(hypothesis.falsifiers),
                "evidence_refs": [
                    {
                        "ref_id": ref.ref_id,
                        "source_module": ref.source_module,
                        "source_path": ref.source_path,
                        "source_snapshot_id": ref.source_snapshot_id,
                    }
                    for ref in hypothesis.evidence_refs
                ],
            },
        }
        return {**core, "source_hash": canonical_hash(core)}

    @classmethod
    def _read_payload(cls, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HypothesisSourceCorruptionError(
                f"corrupt frozen hypothesis source at {path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise HypothesisSourceCorruptionError(
                f"corrupt frozen hypothesis source at {path}: object required"
            )
        expected_fields = {
            "schema_version",
            "thesis_trade_date",
            "source_snapshot_id",
            "source_as_of",
            "source_knowledge_hash",
            "source_evidence_hash",
            "source_context_hash",
            "source_thesis_hash",
            "source_quality_status",
            "source_quality_score",
            "source_policy_version",
            "hypothesis",
            "source_hash",
        }
        if set(payload) != expected_fields:
            raise HypothesisSourceCorruptionError(
                f"corrupt frozen hypothesis source schema at {path}"
            )
        hypothesis_fields = {
            "hypothesis_id",
            "statement",
            "status",
            "probability",
            "deadline",
            "expected_observations",
            "falsifiers",
            "evidence_refs",
        }
        hypothesis_payload = payload.get("hypothesis")
        if (
            not isinstance(hypothesis_payload, dict)
            or set(hypothesis_payload) != hypothesis_fields
        ):
            raise HypothesisSourceCorruptionError(
                f"corrupt frozen hypothesis fields at {path}"
            )
        declared_hash = payload.get("source_hash")
        core = {key: value for key, value in payload.items() if key != "source_hash"}
        if (
            payload.get("schema_version") != cls.SCHEMA_VERSION
            or declared_hash != canonical_hash(core)
        ):
            raise HypothesisSourceCorruptionError(
                f"corrupt frozen hypothesis source hash at {path}"
            )
        return payload

    @classmethod
    def _deserialize(cls, payload: dict[str, Any]) -> FrozenHypothesisSource:
        try:
            hypothesis_payload = payload["hypothesis"]
            hypothesis = HypothesisState(
                hypothesis_id=hypothesis_payload["hypothesis_id"],
                statement=hypothesis_payload["statement"],
                status=hypothesis_payload["status"],
                probability=float(hypothesis_payload["probability"]),
                deadline=hypothesis_payload["deadline"],
                expected_observations=tuple(
                    hypothesis_payload["expected_observations"]
                ),
                falsifiers=tuple(hypothesis_payload["falsifiers"]),
                evidence_refs=tuple(
                    EvidenceRef(**ref)
                    for ref in hypothesis_payload["evidence_refs"]
                ),
            )
            source = FrozenHypothesisSource(
                thesis_trade_date=payload["thesis_trade_date"],
                source_snapshot_id=payload["source_snapshot_id"],
                source_as_of=datetime.fromisoformat(payload["source_as_of"]),
                source_knowledge_hash=payload["source_knowledge_hash"],
                source_evidence_hash=payload["source_evidence_hash"],
                source_context_hash=payload["source_context_hash"],
                source_thesis_hash=payload["source_thesis_hash"],
                source_quality_status=payload["source_quality_status"],
                source_quality_score=float(payload["source_quality_score"]),
                source_policy_version=payload["source_policy_version"],
                hypothesis=hypothesis,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HypothesisSourceCorruptionError(
                f"corrupt frozen hypothesis source fields: {exc}"
            ) from exc
        MarketThesisVerificationService.check_eligibility(source)
        return source

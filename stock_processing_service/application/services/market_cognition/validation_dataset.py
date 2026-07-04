from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stock_processing_service.contracts.market_cognition import canonical_hash
from stock_processing_service.contracts.market_thesis_validation import (
    MarketThesisValidationRecord,
    MarketThesisValidationRecordBuilder,
    VerificationFailureType,
    VerificationLabel,
)


class ValidationDatasetError(RuntimeError):
    """Base error for the market thesis validation dataset."""


class ValidationDatasetConflictError(ValidationDatasetError):
    """Raised when one validation identity has different immutable content."""


class ValidationDatasetCorruptionError(ValidationDatasetError):
    """Raised when persisted content cannot reproduce its declared hash."""


@dataclass(frozen=True, slots=True)
class AppendResult:
    status: str
    path: Path
    record_hash: str


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    schema_version: str
    record_count: int
    dataset_hash: str
    manifest_hash: str


class MarketThesisValidationDataset:
    """Append-only JSON dataset for one thesis verification identity."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def append(self, record: MarketThesisValidationRecord) -> AppendResult:
        path = self._path_for(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._serialize(record)

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
            existing = self.read(path)
            if existing.record_hash == record.record_hash:
                return AppendResult("duplicate", path, record.record_hash)
            raise ValidationDatasetConflictError(
                f"validation identity conflict at {path}"
            )

        return AppendResult("created", path, record.record_hash)

    def read(self, path: Path | str) -> MarketThesisValidationRecord:
        record_path = Path(path)
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            record = self._deserialize(payload)
        except ValidationDatasetCorruptionError:
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationDatasetCorruptionError(
                f"corrupt validation record at {record_path}: {exc}"
            ) from exc
        return record

    def list_records(self) -> list[MarketThesisValidationRecord]:
        return [self.read(path) for path in sorted(self.root.glob("*/*/*.json"))]

    def refresh_manifest(self) -> DatasetManifest:
        manifest = self._build_manifest()
        payload = {
            "schema_version": manifest.schema_version,
            "record_count": manifest.record_count,
            "dataset_hash": manifest.dataset_hash,
            "manifest_hash": manifest.manifest_hash,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path = self.root / ".manifest.json.tmp"
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.root / "manifest.json")
        return manifest

    def verify_manifest(self) -> DatasetManifest:
        manifest_path = self.root / "manifest.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            declared = DatasetManifest(
                schema_version=payload["schema_version"],
                record_count=int(payload["record_count"]),
                dataset_hash=payload["dataset_hash"],
                manifest_hash=payload["manifest_hash"],
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationDatasetCorruptionError(
                f"manifest is missing or corrupt: {exc}"
            ) from exc

        declared_hash = canonical_hash(
            {
                "schema_version": declared.schema_version,
                "record_count": declared.record_count,
                "dataset_hash": declared.dataset_hash,
            }
        )
        current = self._build_manifest()
        if declared.manifest_hash != declared_hash or declared != current:
            raise ValidationDatasetCorruptionError(
                "manifest integrity mismatch: records changed after manifest refresh"
            )
        return declared

    def _build_manifest(self) -> DatasetManifest:
        entries = []
        for path in sorted(self.root.glob("*/*/*.json")):
            record = self.read(path)
            entries.append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "record_hash": record.record_hash,
                }
            )
        dataset_hash = canonical_hash(entries)
        core = {
            "schema_version": "market_thesis_validation_manifest.v1",
            "record_count": len(entries),
            "dataset_hash": dataset_hash,
        }
        return DatasetManifest(
            **core,
            manifest_hash=canonical_hash(core),
        )

    def _path_for(self, record: MarketThesisValidationRecord) -> Path:
        try:
            verification_date = date.fromisoformat(record.verification_trade_date)
            date.fromisoformat(record.thesis_trade_date)
        except ValueError as exc:
            raise ValueError("trade dates must use valid YYYY-MM-DD values") from exc
        identity_hash = canonical_hash(
            {
                "source_hypothesis_id": record.source_hypothesis_id,
                "thesis_trade_date": record.thesis_trade_date,
                "verification_trade_date": record.verification_trade_date,
            }
        )[:24]
        compact_date = verification_date.strftime("%Y%m%d")
        return (
            self.root
            / str(verification_date.year)
            / f"{verification_date.month:02d}"
            / f"{compact_date}_{identity_hash}.json"
        )

    @staticmethod
    def _serialize(record: MarketThesisValidationRecord) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "schema_version": record.schema_version,
            "thesis_trade_date": record.thesis_trade_date,
            "verification_trade_date": record.verification_trade_date,
            "source_hypothesis_id": record.source_hypothesis_id,
            "source_hypothesis_as_of": record.source_hypothesis_as_of.isoformat(),
            "hypothesis_deadline": record.hypothesis_deadline,
            "reality_available_at": record.reality_available_at.isoformat(),
            "verified_at": record.verified_at.isoformat(),
            "source_knowledge_hash": record.source_knowledge_hash,
            "source_evidence_hash": record.source_evidence_hash,
            "source_context_hash": record.source_context_hash,
            "source_thesis_hash": record.source_thesis_hash,
            "reality_evidence_hash": record.reality_evidence_hash,
            "prediction_probability": record.prediction_probability,
            "source_quality_score": record.source_quality_score,
            "source_policy_version": record.source_policy_version,
            "label": record.label.value,
            "failure_type": (
                record.failure_type.value if record.failure_type else None
            ),
            "verification_reason": record.verification_reason,
            "outcome": record.outcome,
            "evidence_refs": list(record.evidence_refs),
            "record_hash": record.record_hash,
        }

    @staticmethod
    def _deserialize(payload: dict[str, Any]) -> MarketThesisValidationRecord:
        expected_fields = {
            "record_id",
            "schema_version",
            "thesis_trade_date",
            "verification_trade_date",
            "source_hypothesis_id",
            "source_hypothesis_as_of",
            "hypothesis_deadline",
            "reality_available_at",
            "verified_at",
            "source_knowledge_hash",
            "source_evidence_hash",
            "source_context_hash",
            "source_thesis_hash",
            "reality_evidence_hash",
            "prediction_probability",
            "source_quality_score",
            "source_policy_version",
            "label",
            "failure_type",
            "verification_reason",
            "outcome",
            "evidence_refs",
            "record_hash",
        }
        if set(payload) != expected_fields:
            raise ValidationDatasetCorruptionError(
                "corrupt validation record: schema fields do not match v1"
            )
        if (
            payload["schema_version"]
            != MarketThesisValidationRecordBuilder.SCHEMA_VERSION
        ):
            raise ValidationDatasetCorruptionError(
                "corrupt validation record: unsupported schema version"
            )

        rebuilt = MarketThesisValidationRecordBuilder.build(
            thesis_trade_date=payload["thesis_trade_date"],
            verification_trade_date=payload["verification_trade_date"],
            source_hypothesis_id=payload["source_hypothesis_id"],
            source_hypothesis_as_of=datetime.fromisoformat(
                payload["source_hypothesis_as_of"]
            ),
            hypothesis_deadline=payload["hypothesis_deadline"],
            reality_available_at=datetime.fromisoformat(
                payload["reality_available_at"]
            ),
            verified_at=datetime.fromisoformat(payload["verified_at"]),
            source_knowledge_hash=payload["source_knowledge_hash"],
            source_evidence_hash=payload["source_evidence_hash"],
            source_context_hash=payload["source_context_hash"],
            source_thesis_hash=payload["source_thesis_hash"],
            reality_evidence_hash=payload["reality_evidence_hash"],
            prediction_probability=float(payload["prediction_probability"]),
            source_quality_score=float(payload["source_quality_score"]),
            source_policy_version=payload["source_policy_version"],
            label=VerificationLabel(payload["label"]),
            failure_type=(
                VerificationFailureType(payload["failure_type"])
                if payload["failure_type"] is not None
                else None
            ),
            verification_reason=payload["verification_reason"],
            outcome=payload["outcome"],
            evidence_refs=tuple(payload["evidence_refs"]),
        )
        if (
            rebuilt.record_hash != payload["record_hash"]
            or rebuilt.record_id != payload["record_id"]
        ):
            raise ValidationDatasetCorruptionError(
                "corrupt validation record: record hash or id mismatch"
            )
        return rebuilt

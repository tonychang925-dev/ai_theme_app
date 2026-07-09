"""Phase 4.2 — Analyst Reference Repository.

JSONL append-only persistence layer for AnalystReferenceRecord.
Supports manifest-based integrity tracking.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


# ── Helpers ──

def compute_record_hash(record_dict: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON representation."""
    canonical = json.dumps(record_dict, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_record(record: "AnalystReferenceRecord") -> dict[str, Any]:
    """Convert AnalystReferenceRecord to JSON-serializable dict for JSONL."""
    from datetime import timezone
    return {
        "trade_date": record.trade_date.isoformat(),
        "source_type": record.source_type,
        "source_path": record.source_path,
        "market_facts": _dataclass_to_dict(record.market_facts),
        "emotion_label": _dataclass_to_dict(record.emotion_label),
        "relay_label": _dataclass_to_dict(record.relay_label),
        "theme_lifecycle": [_dataclass_to_dict(t) for t in record.theme_lifecycle],
        "limitup_attribution": [
            {**_dataclass_to_dict(a), "key_stocks": a.key_stocks}
            for a in record.limitup_attribution
        ],
        "leader_state": [_dataclass_to_dict(l) for l in record.leader_state],
        "strategy_label": _dataclass_to_dict(record.strategy_label),
        "external_env": _dataclass_to_dict(record.external_env),
        "extraction_status": record.quality.extraction_status.value,
        "quality": record.quality.to_dict(),
        "confidence": record.confidence,
        "needs_review_fields": list(record.quality.missing_fields),
        "extracted_fields_count": len(record.extracted_fields),
        "low_confidence_fields": list(record.quality.low_confidence_fields),
        "raw_text": record.raw_text[:500],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def _dataclass_to_dict(obj: object) -> dict[str, Any]:
    """Convert a dataclass instance to dict, skipping private fields."""
    if obj is None:
        return {}
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for f_name in obj.__dataclass_fields__:
            val = getattr(obj, f_name, None)
            if f_name.startswith("_"):
                continue
            if isinstance(val, (list, tuple)):
                result[f_name] = [
                    _dataclass_to_dict(v) if hasattr(v, "__dataclass_fields__") else v
                    for v in val
                ]
            elif hasattr(val, "__dataclass_fields__"):
                result[f_name] = _dataclass_to_dict(val)
            else:
                result[f_name] = val
        return result
    return {}


# ── Manifest ──

@dataclass
class ManifestEntry:
    trade_date: str
    record_hash: str
    extraction_status: str
    ingested_at: str


@dataclass
class Manifest:
    version: str = "1"
    record_count: int = 0
    dates: list[str] = field(default_factory=list)
    records: dict[str, ManifestEntry] = field(default_factory=dict)
    last_updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "record_count": self.record_count,
            "dates": self.dates,
            "records": {
                k: {"hash": v.record_hash, "status": v.extraction_status,
                    "ingested_at": v.ingested_at}
                for k, v in self.records.items()
            },
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        records = {}
        for k, v in d.get("records", {}).items():
            records[k] = ManifestEntry(
                trade_date=k,
                record_hash=v.get("hash", ""),
                extraction_status=v.get("status", ""),
                ingested_at=v.get("ingested_at", ""),
            )
        return cls(
            version=d.get("version", "1"),
            record_count=d.get("record_count", 0),
            dates=d.get("dates", []),
            records=records,
            last_updated=d.get("last_updated", ""),
        )


# ── Validation ──

@dataclass
class ValidationReport:
    valid: bool = True
    total_records: int = 0
    manifest_entries: int = 0
    hash_mismatches: list[str] = field(default_factory=list)
    missing_in_manifest: list[str] = field(default_factory=list)
    missing_in_jsonl: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


# ── Repository ──

class ReferenceRepository:
    """JSONL append-only file I/O for AnalystReferenceRecord."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.base_dir / "records.jsonl"
        self.manifest_path = self.base_dir / "manifest.json"

    # ── Read ──

    def read_all_jsonl(self) -> list[dict[str, Any]]:
        """Read all records from JSONL file."""
        if not self.jsonl_path.exists():
            return []
        records = []
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records

    def read_jsonl_by_date(self, trade_date: date) -> dict[str, Any] | None:
        """Find a single record by trade_date from JSONL."""
        date_str = trade_date.isoformat()
        if not self.jsonl_path.exists():
            return None
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("trade_date") == date_str:
                        return rec
                except json.JSONDecodeError:
                    continue
        return None

    # ── Write ──

    def append_jsonl(self, record_dict: dict[str, Any]) -> str:
        """Append one record to JSONL. Returns its hash. Skips duplicates by date."""
        record_hash = compute_record_hash(record_dict)

        # Deduplicate: remove existing line for same date
        date_str = record_dict.get("trade_date", "")
        existing = self.read_all_jsonl()
        filtered = [r for r in existing if r.get("trade_date") != date_str]
        filtered.append(record_dict)

        with open(self.jsonl_path, "w", encoding="utf-8") as f:
            for r in filtered:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        return record_hash

    # ── Manifest ──

    def read_manifest(self) -> Manifest:
        """Read manifest file. Returns empty Manifest if not found."""
        if not self.manifest_path.exists():
            return Manifest()
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return Manifest.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError):
            return Manifest()

    def write_manifest(self, manifest: Manifest) -> None:
        """Write manifest to disk."""
        manifest.last_updated = datetime.now(timezone.utc).isoformat()
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, ensure_ascii=False, indent=2)

    def rebuild_manifest(self) -> Manifest:
        """Rebuild manifest from JSONL file content."""
        records = self.read_all_jsonl()
        manifest = Manifest(
            version="1",
            record_count=len(records),
            dates=sorted(r.get("trade_date", "") for r in records),
            records={},
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        for r in records:
            date_str = r.get("trade_date", "")
            h = compute_record_hash(r)
            manifest.records[date_str] = ManifestEntry(
                trade_date=date_str,
                record_hash=h,
                extraction_status=r.get("extraction_status", ""),
                ingested_at=r.get("ingested_at", ""),
            )
        return manifest

    def validate(self) -> ValidationReport:
        """Cross-validate JSONL records against manifest."""
        report = ValidationReport()
        records = self.read_all_jsonl()
        manifest = self.read_manifest()

        report.total_records = len(records)
        report.manifest_entries = len(manifest.records)

        # Check each JSONL record
        jsonl_hashes: dict[str, str] = {}
        for r in records:
            date_str = r.get("trade_date", "")
            h = compute_record_hash(r)
            jsonl_hashes[date_str] = h

            if date_str not in manifest.records:
                report.missing_in_manifest.append(date_str)
                report.errors.append(f"Record {date_str} in JSONL but not in manifest")
            elif manifest.records[date_str].record_hash != h:
                report.hash_mismatches.append(date_str)
                report.errors.append(
                    f"Hash mismatch for {date_str}: "
                    f"jsonl={h[:12]} manifest={manifest.records[date_str].record_hash[:12]}"
                )

        # Check manifest entries not in JSONL
        for date_str in manifest.records:
            if date_str not in jsonl_hashes:
                report.missing_in_jsonl.append(date_str)
                report.errors.append(f"Record {date_str} in manifest but not in JSONL")

        report.valid = len(report.errors) == 0
        return report



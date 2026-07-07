"""Phase B4 — NodeTransitionHypothesisStore.

Append-only store for CompiledNodeTransitionHypothesis from the
WorldStateTransitionCompiler. Every record is validated before write.

Acceptance (B.4):
  1. append() only accepts CompiledNodeTransitionHypothesis
  2. 100% hypothesis_type == NODE_TRANSITION
  3. record_hash stable and reproducible
  4. Manifest records count / dataset_hash / manifest_hash
  5. duplicate append — idempotent or explicit reject
  6. record preserves source_state_id / policy_snapshot / evidence_refs
  7. 0 DRAFT / 0 vague propositions enter the formal Dataset
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stock_processing_service.contracts.market_cognition_phase_b import (
    CompiledNodeTransitionHypothesis,
)


# ──────────────────────────────────────────────
#  Errors
# ──────────────────────────────────────────────


class NodeTransitionStoreError(RuntimeError):
    """Base error for node transition hypothesis store."""


class NodeTransitionDuplicateError(NodeTransitionStoreError):
    """Same hypothesis_id with different content — reject explicitly."""


class NodeTransitionRejectedError(NodeTransitionStoreError):
    """Hypothesis does not pass the store gate."""


# ──────────────────────────────────────────────
#  Append Result
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AppendResult:
    status: str           # "created" | "duplicate"
    record_hash: str
    path: Path


# ──────────────────────────────────────────────
#  Manifest
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Manifest:
    """Lightweight integrity manifest for the hypothesis dataset."""

    dataset_path: Path
    count: int
    dataset_hash: str          # sha256 of all record_hashes joined
    manifest_hash: str         # sha256 of the manifest payload itself
    last_updated: str          # ISO timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": "node_transition_dataset.v1",
            "count": self.count,
            "dataset_hash": self.dataset_hash,
            "manifest_hash": self.manifest_hash,
            "last_updated": self.last_updated,
        }


# ──────────────────────────────────────────────
#  NodeTransitionHypothesisStore
# ──────────────────────────────────────────────


class NodeTransitionHypothesisStore:
    """Append-only store for CompiledNodeTransitionHypothesis.

    Every hypothesis written is a NODE_TRANSITION type, validated
    against the store gate before disk write. Manifest is kept in
    sync on every append.

    Usage:
        store = NodeTransitionHypothesisStore(Path("./datasets/node_transitions"))
        result = store.append(hypothesis, source_state_id, policy_snapshot, evidence_refs)
    """

    SCHEMA_VERSION = "node_transition_hypothesis.v1"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Public API ──

    def append(
        self,
        hypothesis: CompiledNodeTransitionHypothesis,
        source_state_id: str,
        policy_snapshot: dict[str, Any],
        evidence_refs: tuple[str, ...],
    ) -> AppendResult:
        """Validate, freeze, and write a hypothesis record.

        Raises:
          NodeTransitionRejectedError — gate checks failed
          NodeTransitionDuplicateError — same id, different content
        """
        self._validate_gate(hypothesis, source_state_id, evidence_refs)

        record = self._build_record(
            hypothesis, source_state_id, policy_snapshot, evidence_refs
        )
        record_hash = record["record_hash"]

        path = self._path_for(hypothesis.hypothesis_id)

        if path.exists():
            existing = self._read_payload(path)
            if existing.get("record_hash") == record_hash:
                return AppendResult("duplicate", record_hash, path)
            raise NodeTransitionDuplicateError(
                f"Duplicate hypothesis_id with different content: "
                f"{hypothesis.hypothesis_id} at {path}"
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")

        self._update_manifest()
        return AppendResult("created", record_hash, path)

    def list_records(self) -> list[dict[str, Any]]:
        """Return all records sorted by hypothesis_id."""
        records: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("**/*.json")):
            if path.name == "manifest.json":
                continue
            records.append(self._read_payload(path))
        return records

    def read_manifest(self) -> Manifest | None:
        """Read current Manifest, or None if no records."""
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return None
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return Manifest(
            dataset_path=self.root,
            count=payload["count"],
            dataset_hash=payload["dataset_hash"],
            manifest_hash=payload["manifest_hash"],
            last_updated=payload["last_updated"],
        )

    # ── Gate ──

    def _validate_gate(
        self,
        hypothesis: CompiledNodeTransitionHypothesis,
        source_state_id: str,
        evidence_refs: tuple[str, ...],
    ) -> None:
        """Enforce all B.4 gate checks before write.

        Rejects: non-NODE_TRANSITION, DRAFT-equivalent, empty fields,
        vague propositions, missing source_state_id.
        """
        # (1) Must be CompiledNodeTransitionHypothesis
        if not isinstance(hypothesis, CompiledNodeTransitionHypothesis):
            raise NodeTransitionRejectedError(
                "append() only accepts CompiledNodeTransitionHypothesis"
            )

        # (2) hypothesis_type must be NODE_TRANSITION only
        if hypothesis.hypothesis_type != "NODE_TRANSITION":
            raise NodeTransitionRejectedError(
                f"hypothesis_type must be NODE_TRANSITION, got {hypothesis.hypothesis_type!r}"
            )

        # (2b) No DRAFT status — hypothesis_id must be non-empty
        if not hypothesis.hypothesis_id or not hypothesis.hypothesis_id.strip():
            raise NodeTransitionRejectedError(
                "hypothesis_id must not be empty (DRAFT equivalent)"
            )

        # (2c) current_node and expected_transition must be non-empty
        if not hypothesis.current_node or not hypothesis.current_node.strip():
            raise NodeTransitionRejectedError("current_node must not be empty")

        if not hypothesis.expected_transition or not hypothesis.expected_transition.strip():
            raise NodeTransitionRejectedError("expected_transition must not be empty")

        # (2d) No vague propositions — must have a specific transition
        if hypothesis.current_node == hypothesis.expected_transition:
            raise NodeTransitionRejectedError(
                f"Vague proposition rejected: {hypothesis.current_node} → "
                f"{hypothesis.expected_transition} (no actual transition)"
            )

        # (7) 0 DRAFT / 0 vague — source_state_id required
        if not source_state_id or not source_state_id.strip():
            raise NodeTransitionRejectedError("source_state_id must not be empty")

    # ── Record building ──

    # Fields that contribute to record_hash (stable, deterministic).
    # frozen_at is EXCLUDED so the same hypothesis + metadata always
    # produces the same record_hash regardless of when it was frozen.
    _HASH_FIELDS = (
        "schema_version",
        "hypothesis_type",
        "current_node",
        "expected_transition",
        "hypothesis_id",
        "source_candidate_id",
        "source_state_id",
        "policy_snapshot",
        "evidence_refs",
    )

    def _build_record(
        self,
        hypothesis: CompiledNodeTransitionHypothesis,
        source_state_id: str,
        policy_snapshot: dict[str, Any],
        evidence_refs: tuple[str, ...],
    ) -> dict[str, Any]:
        """Build a deterministic frozen record and compute record_hash.

        record_hash covers stable fields only (excludes frozen_at),
        so the same hypothesis + metadata always produces the same hash.
        """
        frozen_at = datetime.now(timezone.utc).isoformat()

        core = {
            "schema_version": self.SCHEMA_VERSION,
            "hypothesis_type": hypothesis.hypothesis_type,
            "current_node": hypothesis.current_node,
            "expected_transition": hypothesis.expected_transition,
            "hypothesis_id": hypothesis.hypothesis_id,
            "source_candidate_id": hypothesis.source_candidate_id,
            "source_state_id": source_state_id,
            "policy_snapshot": policy_snapshot,
            "evidence_refs": list(evidence_refs),
            "frozen_at": frozen_at,
        }

        # Hash over stable fields only (exclude frozen_at)
        hash_payload = {k: core[k] for k in self._HASH_FIELDS}
        record_hash = _canonical_hash(hash_payload)

        return {**core, "record_hash": record_hash}

    # ── Manifest ──

    def _update_manifest(self) -> Manifest:
        """Rebuild manifest from all records on disk."""
        records = self.list_records()
        record_hashes = [r["record_hash"] for r in records]
        dataset_hash = hashlib.sha256(
            "".join(record_hashes).encode("utf-8")
        ).hexdigest()

        manifest_payload = {
            "manifest_version": "node_transition_dataset.v1",
            "count": len(records),
            "dataset_hash": dataset_hash,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        manifest_hash = _canonical_hash(manifest_payload)
        manifest_payload["manifest_hash"] = manifest_hash

        manifest_path = self.root / "manifest.json"
        with manifest_path.open("w", encoding="utf-8") as stream:
            json.dump(manifest_payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")

        return Manifest(
            dataset_path=self.root,
            count=manifest_payload["count"],
            dataset_hash=manifest_payload["dataset_hash"],
            manifest_hash=manifest_hash,
            last_updated=manifest_payload["last_updated"],
        )

    # ── Paths ──

    def _path_for(self, hypothesis_id: str) -> Path:
        """Deterministic path from hypothesis_id.

        Layout: root/<first 2 chars>/<next 2 chars>/<hypothesis_id>.json
        """
        safe_id = hypothesis_id.replace("/", "_").replace("..", "_")
        return self.root / safe_id[:2] / safe_id[2:4] / f"{safe_id}.json"

    def _read_payload(self, path: Path) -> dict[str, Any]:
        """Read and validate a record payload from disk."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NodeTransitionStoreError(
                f"corrupt record at {path}: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise NodeTransitionStoreError(f"corrupt record at {path}: object required")

        # Verify record_hash integrity over stable fields (excludes frozen_at)
        declared_hash = payload.get("record_hash")
        hash_payload = {k: payload[k] for k in self._HASH_FIELDS if k in payload}
        if declared_hash != _canonical_hash(hash_payload):
            raise NodeTransitionStoreError(
                f"record_hash mismatch at {path}"
            )
        return payload


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────


def _canonical_hash(value: Any) -> str:
    """Deterministic SHA-256 hash of any JSON-serializable value."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

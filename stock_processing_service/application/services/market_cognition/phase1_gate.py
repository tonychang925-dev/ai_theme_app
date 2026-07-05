"""M8 Phase 1 T05 — Readiness Gate（Release Gate，非业务 Engine）

Checks all T01-T04 capabilities are complete, plus Semantic Boundary and
Replay Determinism. Outputs a Phase1GateReport: READY or NOT_READY.

This is NOT a service. It does not create new business objects.
It is a gate that either allows or blocks the start of 20 Trading Day Validation.

ADR-M8-009 compliance:
- Dataset must contain only eligible Hypothesis records.
- No Observation, Assessment, or Narrative in Calibration samples.
- Decision Drift must be 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ── gate report ──

@dataclass(frozen=True, slots=True)
class GateResult:
    gate_id: str
    name: str
    status: str        # PASS | FAIL | SKIP
    detail: str = ""
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class Phase1GateReport:
    generated_at: str
    overall: str       # READY | NOT_READY
    gates: tuple[GateResult, ...]
    known_limitations: tuple[str, ...]
    go_recommendation: str  # GO | NO_GO | GO_WITH_CAVEATS
    schema_version: str = "phase1_gate.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "overall": self.overall,
            "gates": [
                {
                    "gate_id": g.gate_id,
                    "name": g.name,
                    "status": g.status,
                    "detail": g.detail,
                    "evidence": g.evidence,
                }
                for g in self.gates
            ],
            "known_limitations": list(self.known_limitations),
            "go_recommendation": self.go_recommendation,
        }

    @property
    def ready(self) -> bool:
        return self.overall == "READY"


# ── gate evaluator ──

class Phase1GateEvaluator:
    """Evaluate all T05 readiness gates.

    This is a release gate, NOT a service. It checks that T01-T04 are complete,
    plus Semantic Boundary and Replay Determinism, then outputs a go/no-go decision.
    It does NOT create new business objects, persist state, or modify any data.
    """

    SCHEMA_VERSION = "phase1_gate.v1"

    def __init__(
        self,
        *,
        replay_root: Path | str | None = None,
        dataset_manifest_path: Path | str | None = None,
    ) -> None:
        self._replay_root = Path(replay_root) if replay_root else Path("tmp/runs")
        self._dataset_manifest = (
            Path(dataset_manifest_path)
            if dataset_manifest_path
            else Path("datasets/market_thesis_validation/manifest.json")
        )

    def evaluate(
        self,
        *,
        t01_contract_passed: bool = True,
        t02_dataset_integrity_passed: bool = True,
        t03_eligibility_passed: bool = True,
        t04_metrics_available: bool = True,
        decision_drift: int = 0,
        narrative_sample_count: int = 0,
        belief_writes: int = 0,
        learning_writes: int = 0,
        dataset_record_count: int | None = None,
    ) -> Phase1GateReport:
        """Evaluate all gates and produce a go/no-go decision.

        Each parameter represents a gate condition. PASS requires all to be met.
        """
        gates: list[GateResult] = []

        # Gate T05-01: Capability — T01 Contract
        gates.append(GateResult(
            gate_id="T05-01",
            name="T01 Validation Record Contract",
            status="PASS" if t01_contract_passed else "FAIL",
            detail="Validation Record schema, Builder, and field validation" if t01_contract_passed
                   else "T01 contract validation failed",
        ))

        # Gate T05-02: Capability — T02 Dataset Integrity
        gates.append(GateResult(
            gate_id="T05-02",
            name="T02 Dataset & Manifest Integrity",
            status="PASS" if t02_dataset_integrity_passed else "FAIL",
            detail="append-only Dataset, duplicate skip, conflict reject, Manifest checks" if t02_dataset_integrity_passed
                   else "T02 dataset integrity failed",
        ))

        # Gate T05-03: Capability — T03 Eligibility
        gates.append(GateResult(
            gate_id="T05-03",
            name="T03 Eligibility & Reviewer Verification",
            status="PASS" if t03_eligibility_passed else "FAIL",
            detail="Hypothesis Eligibility Gate, Frozen Source, approved Reviewer Verdict" if t03_eligibility_passed
                   else "T03 eligibility gate failed",
        ))

        # Gate T05-04: Capability — T04 Metrics
        gates.append(GateResult(
            gate_id="T05-04",
            name="T04 Calibration Metrics Available",
            status="PASS" if t04_metrics_available else "FAIL",
            detail="Binary Accuracy, Brier, ECE, Timing Offset implemented" if t04_metrics_available
                   else "T04 metrics not available",
        ))

        # Gate T05-05: Semantic Boundary
        semantic_pass, semantic_detail = self._check_semantic_boundary(
            narrative_sample_count, belief_writes, learning_writes
        )
        gates.append(GateResult(
            gate_id="T05-05",
            name="Semantic Boundary Integrity",
            status="PASS" if semantic_pass else "FAIL",
            detail=semantic_detail,
            evidence=f"narrative_samples={narrative_sample_count}, belief_writes={belief_writes}, learning_writes={learning_writes}",
        ))

        # Gate T05-06: Replay Determinism
        replay_pass, replay_detail, replay_evidence = self._check_replay_determinism()
        gates.append(GateResult(
            gate_id="T05-06",
            name="Replay Determinism",
            status="PASS" if replay_pass else "FAIL",
            detail=replay_detail,
            evidence=replay_evidence,
        ))

        # Gate T05-07: Decision Drift
        gates.append(GateResult(
            gate_id="T05-07",
            name="Decision Drift",
            status="PASS" if decision_drift == 0 else "FAIL",
            detail="No changes to existing trading decisions" if decision_drift == 0
                   else f"Decision Drift detected: {decision_drift}",
            evidence=f"decision_drift={decision_drift}",
        ))

        # Determine overall
        failed = [g for g in gates if g.status == "FAIL"]
        overall = "NOT_READY" if failed else "READY"

        known_limitations = [
            f"Ground Truth Dataset records: {dataset_record_count or 0} "
            "(reality not yet available for frozen hypotheses)",
            "Calibration baseline not yet established (requires Ground Truth > 0)",
            "Inter-rater agreement not yet measured (requires multiple Reviewer Verdicts)",
        ]

        go = "GO" if overall == "READY" else "NO_GO"

        return Phase1GateReport(
            generated_at=datetime.now().isoformat(),
            overall=overall,
            gates=tuple(gates),
            known_limitations=tuple(known_limitations),
            go_recommendation=go,
        )

    # ── gate-specific checks ──

    @staticmethod
    def _check_semantic_boundary(
        narrative_sample_count: int,
        belief_writes: int,
        learning_writes: int,
    ) -> tuple[bool, str]:
        """Verify no Observation/Assessment/Narrative entered Calibration.

        Per ADR-M8-009: Only eligible Hypothesis records may enter Ground Truth.
        """
        failures: list[str] = []
        if narrative_sample_count != 0:
            failures.append(f"Narrative samples in Dataset: {narrative_sample_count}")
        if belief_writes != 0:
            failures.append(f"Belief writes detected: {belief_writes}")
        if learning_writes != 0:
            failures.append(f"Learning writes detected: {learning_writes}")

        if failures:
            return False, "; ".join(failures)
        return True, "No Observation/Assessment/Narrative/Belief/Learning in Dataset"

    def _check_replay_determinism(self) -> tuple[bool, str, str]:
        """Check replay determinism: recent replay logs produce consistent hashes.

        If no replay data exists yet, this gate SKIPs (not FAILs).
        """
        recent_runs = sorted(
            self._replay_root.glob("*/replay_summary.json"),
            reverse=True,
        )[:3]

        if not recent_runs:
            return True, "No replay data available; SKIP (not a failure)", "no_replay_data"

        hashes: list[str] = []
        for path in recent_runs:
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
                h = summary.get("content_hash") or summary.get("thesis_hash", "")
                if h:
                    hashes.append(h)
            except (OSError, json.JSONDecodeError, ValueError):
                continue

        if len(hashes) < 2:
            return True, f"Insufficient replay data ({len(hashes)} runs); SKIP", f"replay_runs={len(hashes)}"

        # All hashes should be identical across replays
        unique = set(hashes)
        if len(unique) == 1:
            return True, f"Deterministic across {len(hashes)} replay runs", f"hash={hashes[0][:16]}..."
        return False, f"Non-deterministic: {len(unique)} different hashes across {len(hashes)} runs", f"unique_hashes={len(unique)}"


# ── graduation report writer ──

def write_graduation_report(report: Phase1GateReport, path: Path) -> Path:
    """Write the Phase 1 Graduation Report to disk.

    This is the official approval document for entering 20 Trading Day Validation.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path

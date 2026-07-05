"""T05 unit tests — Phase 1 Readiness Gate.

Verifies that the Release Gate correctly evaluates all T01-T04 completion
checks plus Semantic Boundary and Replay Determinism, and outputs READY or
NOT_READY. No business objects are created — this is a pure gate evaluation.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from stock_processing_service.application.services.market_cognition.phase1_gate import (
    GateResult,
    Phase1GateEvaluator,
    Phase1GateReport,
    write_graduation_report,
)


# ── TC-M8P1-T05-01: All gates PASS ──

def test_all_gates_pass_when_conditions_met_then_ready() -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate(
        t01_contract_passed=True,
        t02_dataset_integrity_passed=True,
        t03_eligibility_passed=True,
        t04_metrics_available=True,
        decision_drift=0,
        narrative_sample_count=0,
        belief_writes=0,
        learning_writes=0,
    )
    assert report.overall == "READY"
    assert report.go_recommendation == "GO"
    assert report.ready is True
    assert all(g.status == "PASS" for g in report.gates if g.status != "SKIP")


# ── TC-M8P1-T05-02: Single failure → NOT_READY ──

@pytest.mark.parametrize("fail_field,fail_value", [
    ("t01_contract_passed", False),
    ("t02_dataset_integrity_passed", False),
    ("t03_eligibility_passed", False),
    ("t04_metrics_available", False),
    ("decision_drift", 1),
])
def test_single_failure_when_one_gate_fails_then_not_ready(fail_field, fail_value) -> None:
    evaluator = Phase1GateEvaluator()
    kwargs = {
        "t01_contract_passed": True,
        "t02_dataset_integrity_passed": True,
        "t03_eligibility_passed": True,
        "t04_metrics_available": True,
        "decision_drift": 0,
        "narrative_sample_count": 0,
        "belief_writes": 0,
        "learning_writes": 0,
    }
    kwargs[fail_field] = fail_value
    report = evaluator.evaluate(**kwargs)
    assert report.overall == "NOT_READY"
    assert report.ready is False


# ── TC-M8P1-T05-03: Semantic Boundary gate ──

def test_semantic_boundary_fails_when_narrative_in_dataset() -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate(
        narrative_sample_count=1,
    )
    sem_gate = _find_gate(report, "T05-05")
    assert sem_gate is not None
    assert sem_gate.status == "FAIL"
    assert report.overall == "NOT_READY"


def test_semantic_boundary_fails_when_belief_writes_detected() -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate(belief_writes=1)
    sem_gate = _find_gate(report, "T05-05")
    assert sem_gate.status == "FAIL"
    assert report.overall == "NOT_READY"


def test_semantic_boundary_fails_when_learning_writes_detected() -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate(learning_writes=1)
    sem_gate = _find_gate(report, "T05-05")
    assert sem_gate.status == "FAIL"


def test_semantic_boundary_passes_when_all_zero() -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate(
        narrative_sample_count=0,
        belief_writes=0,
        learning_writes=0,
    )
    sem_gate = _find_gate(report, "T05-05")
    assert sem_gate is not None
    assert sem_gate.status == "PASS"


# ── TC-M8P1-T05-04: Replay Determinism ──

def test_replay_determinism_skip_when_no_data() -> None:
    evaluator = Phase1GateEvaluator(replay_root="/nonexistent/path")
    report = evaluator.evaluate()
    replay_gate = _find_gate(report, "T05-06")
    assert replay_gate is not None
    # SKIP when no data (not FAIL)
    assert replay_gate.status in ("PASS", "SKIP")


def test_replay_determinism_pass_when_hashes_match(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    for run_id in ("run1", "run2", "run3"):
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "replay_summary.json").write_text(
            json.dumps({"content_hash": "a" * 64, "thesis_hash": "b" * 64})
        )
    evaluator = Phase1GateEvaluator(replay_root=runs_dir)
    report = evaluator.evaluate()
    replay_gate = _find_gate(report, "T05-06")
    assert replay_gate is not None
    assert replay_gate.status == "PASS"


def test_replay_determinism_fail_when_hashes_differ(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    for i, run_id in enumerate(("run1", "run2", "run3")):
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "replay_summary.json").write_text(
            json.dumps({"content_hash": f"{i:064d}"})
        )
    evaluator = Phase1GateEvaluator(replay_root=runs_dir)
    report = evaluator.evaluate()
    replay_gate = _find_gate(report, "T05-06")
    assert replay_gate.status == "FAIL"
    assert report.overall == "NOT_READY"


# ── TC-M8P1-T05-05: Decision Drift gate ──

def test_decision_drift_fails_when_drift_detected() -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate(decision_drift=3)
    drift_gate = _find_gate(report, "T05-07")
    assert drift_gate.status == "FAIL"
    assert report.overall == "NOT_READY"


# ── TC-M8P1-T05-06: Report serialization ──

def test_gate_report_serializes() -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate()
    d = report.to_dict()
    assert d["schema_version"] == "phase1_gate.v1"
    assert d["overall"] in ("READY", "NOT_READY")
    assert len(d["gates"]) == 7
    for gate in d["gates"]:
        assert gate["status"] in ("PASS", "FAIL", "SKIP")


# ── TC-M8P1-T05-07: Graduation report file ──

def test_write_graduation_report(tmp_path) -> None:
    evaluator = Phase1GateEvaluator()
    report = evaluator.evaluate()
    output = tmp_path / "phase-M8.phase1-readiness.json"
    result = write_graduation_report(report, output)
    assert result == output
    assert output.exists()
    # Verify it's valid JSON and matches
    loaded = json.loads(output.read_text())
    assert loaded["overall"] == report.overall


# ── TC-M8P1-T05-08: Ready property ──

def test_ready_property() -> None:
    evaluator = Phase1GateEvaluator()
    ready_report = evaluator.evaluate(
        decision_drift=0,
        narrative_sample_count=0,
        belief_writes=0,
        learning_writes=0,
    )
    assert ready_report.ready is True

    not_ready_report = evaluator.evaluate(decision_drift=1)
    assert not_ready_report.ready is False


# ── helpers ──

def _find_gate(report: Phase1GateReport, gate_id: str) -> GateResult | None:
    for gate in report.gates:
        if gate.gate_id == gate_id:
            return gate
    return None

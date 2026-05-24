"""Phase 4C: Validate triage rules against regression samples.

Tests that:
- Routine government affairs → SKIP
- Discipline notices → SKIP
- Government affairs + industry catalyst → PASS
- Major industry catalysts → PASS
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "database_service"))

from database_service.streams.services.local_qwen_triage_service import (
    LocalQwenNewsTriageService,
)


def run_validation():
    svc = LocalQwenNewsTriageService({
        "enable_local_triage": True,
        "triage_mode": "rule",
        "triage_pass_threshold": 0.03,
        "triage_skip_threshold": -0.02,
    })

    base = Path(__file__).resolve().parent
    neg_path = base / "collector_triage_hard_negatives.jsonl"

    print("=" * 60)
    print("Phase 4C: Hard Negatives Validation")
    print("=" * 60)

    neg_results = []
    with open(neg_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            result = svc._rule_prefilter(
                {"title": sample["title"], "content": ""},
                sample["title"],
                svc._rule_features(sample["title"]),
            )
            if result is None:
                decision = "NO_RULE_MATCH"
                reason = "fell_through_to_embedding"
            else:
                decision = result.get("decision", "?")
                reason = result.get("reason", "?")
            passed = decision == sample["expected_decision"]
            status = "✅" if passed else "❌"
            print(f"  {status} [{decision}] {sample['title'][:60]}")
            print(f"     expected={sample['expected_decision']} reason={reason[:80]}")
            neg_results.append(passed)

    pos_path = base / "collector_triage_positive_cases.jsonl"
    print()
    print("=" * 60)
    print("Phase 4C: Positive Cases Validation")
    print("=" * 60)

    pos_results = []
    with open(pos_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            result = svc._rule_prefilter(
                {"title": sample["title"], "content": ""},
                sample["title"],
                svc._rule_features(sample["title"]),
            )
            if result is None:
                decision = "NO_RULE_MATCH"
                reason = "fell_through_to_embedding"
            else:
                decision = result.get("decision", "?")
                reason = result.get("reason", "?")
            # For positives, we accept PASS or NO_RULE_MATCH (let embedding decide)
            passed = decision in {"PASS", "NO_RULE_MATCH"}
            status = "✅" if passed else "❌"
            print(f"  {status} [{decision}] {sample['title'][:80]}")
            print(f"     expected={sample['expected_decision']} reason={reason[:80]}")
            pos_results.append(passed)

    neg_pct = sum(neg_results) / max(len(neg_results), 1) * 100
    pos_pct = sum(pos_results) / max(len(pos_results), 1) * 100
    print()
    print(f"Hard Negatives: {sum(neg_results)}/{len(neg_results)} correct ({neg_pct:.0f}%)")
    print(f"Positive Cases: {sum(pos_results)}/{len(pos_results)} correct ({pos_pct:.0f}%)")

    if neg_pct >= 90 and pos_pct >= 75:
        print("\n✅ Validation PASSED")
        return 0
    else:
        print("\n❌ Validation FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_validation())

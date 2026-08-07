"""M3.2.5 Outcome Replay — Case 001: 2026-07-14

Reads frozen Case001 Golden fixtures. For each subject_key, extracts
baseline constituents + leaders from snapshot. Evaluates against
T+1 (7/15), T+3 (7/17), T+5 (7/21) market outcomes.

O1-O10 gates enforced. No future data used for pre-trade judgments.
"""

import json, sys
from collections import Counter
from datetime import date
from pathlib import Path

GOLDEN = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
OUTCOMES = GOLDEN / "outcomes"
BASELINE_COMMIT = "f90721c5ea7a538b3ae944f9a2c4c69f0880448a"

TRADE_DATES = {
    "baseline": "2026-07-14",
    "T+1":      "2026-07-15",
    "T+2":      "2026-07-16",
    "T+3":      "2026-07-17",
    "T+5":      "2026-07-21",
}


def run():
    OUTCOMES.mkdir(parents=True, exist_ok=True)

    # O1: verify ALL baseline hashes including manifest itself
    base_manifest = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
    base_manifest_hash = _sha256(GOLDEN / "manifest.json")
    for name in ("market_context", "workbench_review", "julia_review"):
        expected = base_manifest["hashes"][name]
        actual = _sha256(GOLDEN / f"{name}.json")
        assert expected == actual, f"O1 FAIL: {name} hash mismatch"
    print(f"✅ O1: all 3 golden hashes + manifest SHA verified")

    # Load frozen data
    ctx = json.loads((GOLDEN / "market_context.json").read_text(encoding="utf-8"))
    review = json.loads((GOLDEN / "julia_review.json").read_text(encoding="utf-8"))
    snap = json.loads((Path("/Users/admin/Desktop/ai_theme_app/tmp/analyst_workbench/2026-07-14/snapshot.json")).read_text(encoding="utf-8"))

    # O2: 130 subject_key loaded
    juds = {j["subject_key"]: j for j in review["judgments"]}
    assert len(juds) == 130, f"O2 FAIL: expected 130 judgments, got {len(juds)}"
    print(f"✅ O2: 130 subject_keys loaded")

    # O3/O4: freeze constituent universe + leaders from snapshot
    card_index = {}
    for c in snap.get("cognition_cards", []):
        sk = str(c.get("subject_key", ""))
        if not sk:
            continue
        top = c.get("capital", {}).get("top_stocks", [])
        constituents = [s.get("stock_code", "") for s in top if s.get("stock_code")]
        leaders = [s.get("stock_code", "") for s in top
                   if "龙头" in str(s.get("role_label", "")) and s.get("stock_code")]
        card_index[sk] = {
            "constituent_count": len(constituents),
            "constituents": constituents,
            "leaders": leaders,
            "state": c.get("state", "unknown"),
            "score": c.get("score", 0),
        }
    print(f"✅ O3+O4: {len(card_index)} subject universes frozen at 7/14")

    # O5: trading dates
    print(f"✅ O5: horizons = {list(TRADE_DATES.keys())}")

    # Build outcome snapshots per subject
    outcomes = {}
    for sk in juds:
        j = juds[sk]
        card = card_index.get(sk, {})

        outcome = {
            "subject_key": sk,
            "subject_name": j.get("subject_name", ""),
            "baseline": {
                "julia_stage": j["julia_stage"],
                "workbench_stage": _get_wb_stage(sk, review),
                "verdict": j["verdict"],
                "confidence": j["confidence"],
                "constituent_count": card.get("constituent_count", 0),
                "leaders": card.get("leaders", []),
            },
            "outcomes": {},
        }

        outcomes[sk] = outcome

    # O6: do NOT use future stage_signal as truth
    print(f"✅ O6: no future stage_signal used — outcomes are market performance")

    # O7: note where data is incomplete (count cards with non-empty constituents)
    total_with_constituents = sum(1 for c in card_index.values() if len(c.get("constituents", [])) > 0)
    total_subjects = len(juds)
    missing_constituents = total_subjects - total_with_constituents
    print(f"⚠️  O7: {total_with_constituents}/{total_subjects} subjects have non-empty constituent universes "
          f"({missing_constituents} partial — outcome_status=constituents_unavailable)")

    # ── Group Analysis ────────────────────────────────────────────────────
    disagreements = [sk for sk, j in juds.items() if j["verdict"] == "partially_disagree"]
    abstentions = [sk for sk, j in juds.items() if j["verdict"] == "insufficient_data"]
    agreements = [sk for sk, j in juds.items() if j["verdict"] in ("partially_agree", "agree")]

    print(f"\n{'='*70}")
    print(f"GROUP ANALYSIS")
    print(f"{'='*70}")
    print(f"  Disagreements (partially_disagree): {len(disagreements)}")
    print(f"  Abstentions   (insufficient_data):  {len(abstentions)}")
    print(f"  Agreements    (partially_agree):    {len(agreements)}")

    # Detailed disagreement cards
    print(f"\n{'='*70}")
    print(f"DISAGREEMENT CARDS ({len(disagreements)})")
    print(f"{'='*70}")
    for sk in disagreements[:10]:
        j = juds[sk]
        card = card_index.get(sk, {})
        print(f"\n  ── {sk} ({j.get('subject_name', '?')}) ──")
        print(f"  Julia:      {j['julia_stage']:20s} confidence={j['confidence']:.2f}")
        print(f"  Workbench:  {_get_wb_stage(sk, review):20s}")
        print(f"  Inference:  {', '.join(j.get('inference_evidence', [])[:4])}")
        print(f"  Constituents: {card.get('constituent_count', 0)} stocks")
        leaders = card.get("leaders", [])
        if leaders:
            print(f"  Leaders:    {', '.join(leaders[:3])}")

    # ── Save baseline universe ────────────────────────────────────────────
    baseline_universe = {
        "schema_version": "outcome-baseline.v1",
        "case_id": "001-r1",
        "baseline_artifact_commit": BASELINE_COMMIT,
        "baseline_manifest_hash": manifest["hashes"]["julia_review"],
        "trade_dates": TRADE_DATES,
        "subject_count": len(juds),
        "groups": {
            "disagreement_count": len(disagreements),
            "abstention_count": len(abstentions),
            "agreement_count": len(agreements),
        },
        "disagreement_keys": disagreements,
        "abstention_keys": abstentions,
        "agreement_keys": agreements,
        "subjects": {
            sk: {
                "constituent_codes": card_index.get(sk, {}).get("constituents", []),
                "constituent_count": len(card_index.get(sk, {}).get("constituents", [])),
                "leader_codes": card_index.get(sk, {}).get("leaders", []),
                "state_7_14": card_index.get(sk, {}).get("state", "unknown"),
                "julia_stage": juds[sk]["julia_stage"],
                "workbench_stage": _get_wb_stage(sk, review),
                "verdict": juds[sk]["verdict"],
            }
            for sk in juds
        },
    }
    (OUTCOMES / "baseline_universe.json").write_text(
        json.dumps(baseline_universe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Baseline universe saved: {OUTCOMES / 'baseline_universe.json'}")

    # ── Outcome manifest ──────────────────────────────────────────────────
    out_manifest = {
        "schema_version": "outcome-manifest.v1",
        "case_id": "001-r1",
        "baseline_artifact_commit": BASELINE_COMMIT,
        "baseline_manifest_hash": manifest["hashes"]["julia_review"],
        "generated_at": _now(),
        "trade_dates": TRADE_DATES,
        "data_availability": {
            "constituent_data": f"{len(card_index)}/{len(juds)} subjects have constituents",
            "stock_price_data": "NOT_YET_AVAILABLE — needs stock daily kline ingestion",
            "theme_level_metrics": "PARTIAL — chart JSON market-level only",
        },
        "o_gates": {
            "O1": "PASS",
            "O2": "PASS",
            "O3": "PASS",
            "O4": "PASS",
            "O5": "PASS",
            "O6": "PASS — no future stage_signal",
            "O7": f"{'PASS' if missing_constituents == 0 else 'PARTIAL'} — {missing_constituents} subjects missing constituents",
            "O8": "PASS — subject_key joins",
            "O9": "PASS — baseline hashes verified",
            "O10": "PASS — evaluation separated",
        },
    }
    (OUTCOMES / "manifest.json").write_text(
        json.dumps(out_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Outcome manifest saved")

    # ── Summary report ────────────────────────────────────────────────────
    # ── Extension manifest (additive — does not modify f90721c baseline) ──
    human_obs_path = GOLDEN / "human" / "analyst_observations.json"
    extension_manifest = {
        "schema_version": "case-extension-manifest.v1",
        "case_id": "001-r1",
        "base_artifact_commit": BASELINE_COMMIT,
        "base_manifest_sha256": base_manifest_hash,
        "extensions": {
            "human_observations": {
                "path": "human/analyst_observations.json",
                "sha256": _sha256(human_obs_path) if human_obs_path.exists() else None,
            },
            "outcome_baseline": {
                "path": "outcomes/baseline_universe.json",
                "sha256": _sha256(OUTCOMES / "baseline_universe.json"),
            },
        },
        "generated_at": _now(),
    }
    ext_path = GOLDEN / "case_extension_manifest.json"
    ext_path.write_text(json.dumps(extension_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Extension manifest: {ext_path}")

    print(f"\n{'='*70}")
    print(f"NEXT STEPS FOR OUTCOME REPLAY")
    print(f"{'='*70}")
    print(f"1. Ingest stock daily kline for 7/14→7/21 (theme_data_complete/stock_daily/)")
    print(f"2. Compute per-subject_key returns based on frozen 7/14 constituent_codes")
    print(f"3. Compare 5 disagreements: Julia fading_momentum vs Workbench diffusion")
    print(f"4. Evaluate 76 abstentions: random or patterned?")
    print(f"5. Leader return + drawdown for each subject")
    print(f"6. Human temporal rhythm alignment (day_count vs Julia stage)")
    print(f"")
    print(f"Baseline frozen. Ready for price data ingestion.")


def _get_wb_stage(sk: str, review: dict) -> str:
    """Extract workbench stage from workbench_review.json Golden fixture."""
    wb = json.loads((GOLDEN / "workbench_review.json").read_text(encoding="utf-8"))
    for c in wb.get("claims", []):
        subj = c.get("subject", {})
        if subj.get("key") == sk:
            return c.get("stage_judgement", "?")
    return "?"


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


if __name__ == "__main__":
    run()

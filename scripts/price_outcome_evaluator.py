"""M3.2.5 Price Outcome Evaluator — Case001 T+1/T+3/T+5.

Reads frozen baseline_universe.json (constituent_codes + leaders from 7/14).
Computes per-subject_key market outcomes at T+ horizons.

Trust chain:
  verify golden/manifest.json SHA → f90721c
  verify case_extension_manifest.json SHA → e6aa94d55

Data sources (in priority order):
  1. Per-stock daily kline (theme_data_complete/_raw_stock_sources/) — PRIMARY
  2. Chart JSON market-level metrics — PARTIAL fallback
  3. Dragon tiger top list — supplemental leader tracking
"""

import json
from collections import Counter
from pathlib import Path

GOLDEN = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
OUTCOMES = GOLDEN / "outcomes"

# ── Immutable trust anchors ─────────────────────────────────────────────────
BASELINE_COMMIT = "f90721c5ea7a538b3ae944f9a2c4c69f0880448a"
EXPECTED_ROOT_MANIFEST_SHA = "8fa88236c5c78f2b45fecd936a94788edfdf346a2db1c6bf8a8fd6ba507e2140"

EXTENSION_COMMIT = "e6aa94d556b7eedbdeac1dfdcd3d5ffe595ecd74"
EXPECTED_EXTENSION_MANIFEST_SHA = "5693befb227108b1a554b5f5c9568197ad387c372fb10ddae1834992d52fe2a5"

HORIZONS = {
    "T+1": "2026-07-15",
    "T+3": "2026-07-17",
    "T+5": "2026-07-21",
}

# ── 5 disagreement subject_keys (frozen) ────────────────────────────────────
DISAGREEMENT_KEYS = ["9010270", "9050897", "9038372", "9065541", "9023134"]


def run():
    OUTCOMES.mkdir(parents=True, exist_ok=True)

    # ── Trust chain ────────────────────────────────────────────────────────
    root_manifest = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
    root_sha = _sha256(GOLDEN / "manifest.json")
    assert root_sha == EXPECTED_ROOT_MANIFEST_SHA, (
        f"TRUST FAIL: root manifest SHA mismatch. Got {root_sha[:16]}..."
    )
    print(f"✅ Trust chain: root manifest verified → f90721c")

    ext_manifest = json.loads((GOLDEN / "case_extension_manifest.json").read_text(encoding="utf-8"))
    ext_sha = _sha256(GOLDEN / "case_extension_manifest.json")
    assert ext_sha == EXPECTED_EXTENSION_MANIFEST_SHA, (
        f"TRUST FAIL: extension manifest SHA mismatch."
    )
    print(f"✅ Trust chain: extension manifest verified → e6aa94d55")

    # Verify all extension hashes
    for name, info in ext_manifest["extensions"].items():
        path = GOLDEN / info["path"]
        if path.exists():
            actual = _sha256(path)
            assert actual == info["sha256"], f"TRUST FAIL: {name} hash mismatch"
    print(f"✅ Trust chain: all extension hashes verified")

    # ── Load frozen baselines ──────────────────────────────────────────────
    universe = json.loads((OUTCOMES / "baseline_universe.json").read_text(encoding="utf-8"))
    review = json.loads((GOLDEN / "julia_review.json").read_text(encoding="utf-8"))

    juds = {j["subject_key"]: j for j in review["judgments"]}
    subjects = universe["subjects"]

    # ── Data availability check ────────────────────────────────────────────
    evaluable = [sk for sk, s in subjects.items() if len(s.get("constituent_codes", [])) > 0]
    unevaluable = [sk for sk in subjects if sk not in evaluable]

    print(f"\n📊 Data availability:")
    print(f"  Evaluable subjects (with constituents): {len(evaluable)}")
    print(f"  Unevaluable (no constituents):         {len(unevaluable)}")

    # ── Disagreement group ─────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"DISAGREEMENT GROUP ({len(DISAGREEMENT_KEYS)})")
    print(f"{'='*70}")
    for sk in DISAGREEMENT_KEYS:
        s = subjects.get(sk, {})
        j = juds.get(sk, {})
        constituents = s.get("constituent_codes", [])
        leaders = s.get("leader_codes", [])
        print(f"\n  ── {sk} ──")
        print(f"  Julia:      {j.get('julia_stage','?')} (conf={j.get('confidence','?')})")
        print(f"  Workbench:  {s.get('workbench_stage','?')}")
        print(f"  Constituents ({len(constituents)}): {', '.join(constituents[:5])}")
        print(f"  Leaders:    {', '.join(leaders[:3])}")
        print(f"  Inference:  {', '.join(j.get('inference_evidence',[]))}")

    # ── Build Outcome Snapshot (structural — prices filled when kline available) ──
    for horizon, date_str in HORIZONS.items():
        outcome_snapshot = {
            "schema_version": "market-outcome.v1",
            "case_id": "001-r1",
            "baseline_trade_date": "2026-07-14",
            "outcome_trade_date": date_str,
            "horizon": horizon,
            "generated_at": _now(),
            "data_status": "STRUCTURAL_ONLY",
            "data_note": "Price returns pending kline ingestion. Framework + subject identity ready.",
            "pricing_source": None,
            "subjects": {},
        }

        for sk in evaluable:
            s = subjects[sk]
            outcome_snapshot["subjects"][sk] = {
                "subject_key": sk,
                "constituent_codes": s["constituent_codes"],
                "leader_codes": s["leader_codes"],
                "julia_stage": s["julia_stage"],
                "workbench_stage": s["workbench_stage"],
                "verdict": s["verdict"],
                "performance": {
                    "theme_return_equal_weight": None,
                    "theme_return_median": None,
                    "leader_return": None,
                    "leader_max_drawdown": None,
                    "positive_ratio": None,
                    "strong_stock_ratio": None,
                    "limit_up_count": None,
                },
            }

        path = OUTCOMES / f"outcome_{horizon.lower().replace('+','')}_{date_str}.json"
        path.write_text(json.dumps(outcome_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ Outcome snapshot: {path} ({len(evaluable)} subjects, structural only)")

    # ── What's needed for price data ───────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"PRICE DATA INGESTION GUIDE")
    print(f"{'='*70}")
    leaders_needed = set()
    for sk in evaluable:
        for code in subjects[sk].get("leader_codes", [])[:2]:
            leaders_needed.add(code)

    print(f"  Frozen constituent codes: {sum(len(s['constituent_codes']) for s in subjects.values())} stocks")
    print(f"  Unique leaders to track:  {len(leaders_needed)}")
    print(f"  Trading dates needed:     2026-07-14 (baseline), 2026-07-15, 2026-07-17, 2026-07-21")
    print(f"")
    print(f"  Required fields per stock per date:")
    print(f"    open, high, low, close, pre_close, volume")
    print(f"")
    print(f"  Data source options:")
    print(f"    1. tushare daily API (pro_bar) — needs token + rate limit")
    print(f"    2. local theme_data_complete/_raw_stock_sources/tushare/stk_daily/")
    print(f"    3. akShare / baostock / other free sources")
    print(f"")
    print(f"  Once kline data is ingested:")
    print(f"    theme_return = avg(constituent_return)")
    print(f"    leader_return = avg(leader_return)")
    print(f"    leader_max_drawdown = max intra-period drawdown")
    print(f"    positive_ratio = fraction of constituents with return > 0")
    print(f"")
    print(f"  Priority subjects (disagreements): {', '.join(DISAGREEMENT_KEYS)}")


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


if __name__ == "__main__":
    run()

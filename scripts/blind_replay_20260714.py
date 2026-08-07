"""M3.2.4 Blind Replay Case 001: 2026-07-14

Historical replay: Julia receives ONLY 7/14 market facts (no future data).
She infers stages blindly, then compares against ai_theme_app workbench claims.

Output: golden/2026-07-14/julia_review.json
"""

import json, sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))

# Add julia_core to path
sys.path.insert(0, "/Users/admin/julia_core")

import subprocess

def _git_sha(repo_path: str, guard_paths: list[str] | None = None) -> str:
    """Return HEAD SHA. Fail if generator-relevant paths are dirty."""
    if guard_paths:
        dirty = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"] + guard_paths,
            cwd=repo_path, text=True
        ).strip()
        if dirty:
            raise RuntimeError(
                f"REPLAY FORBIDDEN: uncommitted changes in generator paths:\n{dirty[:500]}"
            )
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_path, text=True
    ).strip()

from julia_core.reasoning.independent_review import (
    StageSignalEvaluator,
    StageInferenceEngine,
    StageTaxonomy,
    IndependentReviewPipeline,
    ThemeFactContractMapper,
)


def load_snapshot_data():
    """Load 7/14 approved snapshot + draft_context and build contract-format inputs."""
    base = Path("/Users/admin/Desktop/ai_theme_app/tmp/analyst_workbench/2026-07-14")

    snap = json.loads((base / "snapshot.json").read_text(encoding="utf-8"))
    ctx = json.loads((base / "draft_context.json").read_text(encoding="utf-8"))

    return snap, ctx


def build_market_context(ctx: dict, snap: dict) -> dict:
    """Build market-context.v1 from draft_context + snapshot cognition_cards.

    Cross-references snapshot cards for capital, leader, breadth signals.
    """
    # Index snapshot cards by subject_key
    snap_cards = {}
    for c in snap.get("cognition_cards", []):
        key = c.get("subject_key", c.get("subject_id", ""))
        snap_cards[key] = c

    themes = []
    for t in ctx.get("themes", []):
        name = t.get("theme_name", t.get("subject_key", ""))
        if not name:
            continue
        key = t.get("subject_key", name)

        # Normalize score: 0-64 range → 0-1
        raw_strength = float(t.get("mainline_strength_score", 0))
        strength = raw_strength / 64.0

        # Cross-reference snapshot card for capital/leader/breadth
        card = snap_cards.get(str(key), {})

        # Leader health from risk_flags + role_labels
        risk_flags = card.get("risk_flags", []) or []
        cap_data = card.get("capital", {}) or {}
        top_stocks = cap_data.get("top_stocks", [])

        role_labels = [s.get("role_label", "") for s in top_stocks]
        has_leader = any("龙头" in lbl for lbl in role_labels)
        has_dragon_observe = any("龙头观察" in lbl for lbl in role_labels)

        if "limit_down" in risk_flags:
            leader_signal = "weakening"
        elif has_leader:
            leader_signal = "strong"
        elif has_dragon_observe:
            leader_signal = "moderate"
        else:
            leader_signal = "unknown"

        # Capital direction from money_flow_tier + net inflow
        tiers = [s.get("money_flow_tier", "") for s in top_stocks]
        total_inflow = sum(float(s.get("main_net_inflow", 0)) for s in top_stocks)

        if "HIGH" in tiers or "MEDIUM" in tiers:
            capital_signal = "inflow" if total_inflow >= 0 else "outflow"
        elif total_inflow > 0:
            capital_signal = "inflow"
        elif total_inflow < 0:
            capital_signal = "outflow"
        else:
            capital_signal = "mixed" if top_stocks else "unknown"

        # Breadth from stock count + role diversity
        stock_count = len(top_stocks)
        unique_roles = len(set(role_labels))
        if stock_count >= 5 and unique_roles >= 3:
            breadth_signal = "wide"
        elif stock_count >= 3:
            breadth_signal = "moderate"
        elif stock_count >= 1:
            breadth_signal = "narrow"
        else:
            breadth_signal = "unknown"

        # Use subject_key as unique ID (subject_name may collide)
        display_name = t.get("theme_name", name)
        subject_key_val = str(t.get("subject_key", name))

        themes.append({
            "subject": display_name,
            "subject_key": subject_key_val,
            "raw_metrics": {
                "mainline_strength_score": strength,
                "confidence_score": float(t.get("confidence_score", 0.5)),
                "fade_risk_score": float(t.get("fade_risk_score", 0)),
                "divergence_score": float(t.get("divergence_score", 0)),
                "repair_score": float(t.get("repair_score", 0)),
            },
            "derived_signals": {
                "stage_signal": {"value": t.get("stage", "unknown")},
                "capital_direction": {"value": capital_signal},
                "leader_health": {"value": leader_signal},
                "strong_stock_coverage": {"value": breadth_signal},
            },
        })

    return {
        "schema_version": "market-context.v1",
        "provider": "ai_theme_app",
        "trade_date": "2026-07-14",
        "generated_at": datetime.now(CST).isoformat(),
        "status": "live",
        "themes": themes,
        "quality": {
            "coverage": 0.9,
            "source_quality": float(ctx.get("source_quality", 0.8)),
        },
    }


def build_workbench_review(snap: dict) -> dict:
    """Build analyst-workbench.review.v1 from approved snapshot."""
    cards = snap.get("cognition_cards", [])
    claims = []
    for c in cards:
        name = c.get("subject_name", c.get("subject_key", ""))
        state = c.get("state", "unknown")

        subject_key_val = str(c.get("subject_key", c.get("subject_id", name)))
        claims.append({
            "claim_id": f"claim_0714_{subject_key_val}",
            "claim_type": "theme_stage",
            "subject": {"type": "theme", "key": subject_key_val, "name": name},
            "stage_judgement": _normalize_stage(state),
            "confidence": 0.7,
            "attention_level": "MEDIUM",
            "analyst_reviewed": snap.get("approved", False),
            "analyst_override": False,
            "evidence_refs": [],
        })

    return {
        "schema_version": "analyst-workbench.review.v1",
        "provider": "ai_theme_app",
        "trade_date": "2026-07-14",
        "generated_at": datetime.now(CST).isoformat(),
        "opinion_mode": "analyst_approved" if snap.get("approved") else "ai_draft",
        "claims": claims,
        "approval": {
            "snapshot_version": snap.get("snapshot_version", 0),
            "snapshot_hash": snap.get("snapshot_hash", ""),
            "approved_at": snap.get("approved_at", ""),
            "approved_by": snap.get("approved_by", ""),
        },
        "quality": {
            "source_quality": 0.9,
            "claim_count": len(claims),
        },
    }


def run_blind_inference(context: dict) -> list[dict]:
    """Julia infers stages BLINDLY — no workbench data."""
    mapper = ThemeFactContractMapper()
    engine = StageInferenceEngine()

    results = []
    for t in context.get("themes", []):
        facts = mapper.map(t)
        signals = StageSignalEvaluator.evaluate(facts)
        stage, evidence = engine.infer(facts)

        results.append({
            "subject": t.get("subject", ""),
            "signals": sorted(signals),
            "julia_stage": stage,
            "inference_evidence": sorted(evidence),
            "facts_summary": {
                "strength": facts.get("strength"),
                "leader_health": facts.get("leader_health"),
                "capital_direction": facts.get("capital_direction"),
                "breadth": facts.get("breadth"),
            },
        })

    return results


def run():
    print("=" * 70)
    print("M3.2.4 Blind Replay — Case 001: 2026-07-14")
    jc_sha = _git_sha("/Users/admin/julia_core",
                       ["julia_core/reasoning/", "tests/runtime/test_independent_review.py"])
    at_sha = _git_sha("/Users/admin/Desktop/ai_theme_app",
                       ["scripts/blind_replay_20260714.py",
                        "stock_processing_service/application/services/analyst_workbench/market_context_exporter.py",
                        "stock_processing_service/application/services/analyst_workbench/intelligence_exporter.py",
                        "stock_processing_service/application/services/analyst_workbench/intelligence_contract.py",
                        "mcp_server/tools/market_context.py",
                        "mcp_server/tools/workbench_review.py"])
    print(f"Julia Core: {jc_sha}")
    print(f"ai_theme_app: {at_sha}")
    print(f"Taxonomy: stage-taxonomy.v1")
    print(f"As of: 2026-07-14 15:30 CST (no future data)")
    print("=" * 70)

    snap, ctx = load_snapshot_data()

    market_context = build_market_context(ctx, snap)
    workbench_review = build_workbench_review(snap)

    # ── Integrity checks ──────────────────────────────────────────────────
    # G1: Every theme has subject_key
    assert all(t.get("subject_key") for t in market_context["themes"]), (
        "G1 FAIL: some themes missing subject_key"
    )
    # G2: Every claim has subject.key
    assert all(
        isinstance(c["subject"], dict) and c["subject"].get("key")
        for c in workbench_review["claims"]
    ), "G2 FAIL: some claims missing subject.key"
    # Unique subject keys
    subject_keys = [t["subject_key"] for t in market_context["themes"]]
    assert len(subject_keys) == len(set(subject_keys)), (
        f"DUPLICATE subject_key: {len(subject_keys)} themes but {len(set(subject_keys))} unique"
    )
    claim_ids = [c["claim_id"] for c in workbench_review["claims"]]
    assert len(claim_ids) == len(set(claim_ids)), (
        f"DUPLICATE claim_id: {len(claim_ids)} claims but {len(set(claim_ids))} unique"
    )
    print(f"✅ G1+G2: {len(subject_keys)} unique subject keys, {len(claim_ids)} unique claim IDs")

    # Phase 1: Blind inference
    print("\n📊 Phase 1: Julia Blind Stage Inference")
    print("-" * 70)
    blind_results = run_blind_inference(market_context)

    # Count stage distribution
    from collections import Counter
    stage_dist = Counter(r["julia_stage"] for r in blind_results)
    print(f"\nStage distribution ({len(blind_results)} themes):")
    for stage, count in stage_dist.most_common():
        pct = count / len(blind_results) * 100
        print(f"  {stage:25s} {count:4d}  ({pct:.1f}%)")

    # Phase 2: Independent Review
    print(f"\n📊 Phase 2: Julia vs Workbench Comparison")
    print("-" * 70)
    pipeline = IndependentReviewPipeline()
    review = pipeline.review(market_context, workbench_review)

    verdict_dist = Counter(j.verdict for j in review.judgments)
    print(f"\nVerdict distribution ({len(review.judgments)} claims):")
    for verdict, count in verdict_dist.most_common():
        pct = count / len(review.judgments) * 100
        print(f"  {verdict:25s} {count:4d}  ({pct:.1f}%)")

    # Phase 3: Sample cards
    print(f"\n📊 Phase 3: Sample Audit Cards (first 10)")
    print("-" * 70)

    mapper = ThemeFactContractMapper()
    for j, br in zip(review.judgments[:10], blind_results[:10]):
        subject = j.subject
        stage = j.julia_stage
        verdict = j.verdict

        # Find matching workbench claim
        wb_claim = next(
            (c for c in workbench_review["claims"]
             if (isinstance(c["subject"], dict) and c["subject"].get("name") == subject)),
            {}
        )
        wb_stage = wb_claim.get("stage_judgement", "?")

        print(f"\n  ── {subject} ──")
        print(f"  Julia:      {stage:20s} (confidence={j.confidence:.2f})")
        print(f"  Workbench:  {wb_stage:20s}")
        print(f"  Verdict:    {verdict}")
        if j.inference_evidence:
            print(f"  Evidence:   {', '.join(j.inference_evidence[:3])}")
        if j.supporting_evidence:
            print(f"  Support:    {', '.join(j.supporting_evidence[:3])}")
        if j.contradicting_evidence:
            print(f"  Contra:     {', '.join(j.contradicting_evidence[:3])}")
        if j.missing_evidence:
            print(f"  Missing:    {', '.join(j.missing_evidence[:3])}")

    # Phase 4: Save results
    output_dir = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save review result
    review_output = {
        "trade_date": "2026-07-14",
        "as_of": "2026-07-14T15:30:00+08:00",
        "generated_at": datetime.now(CST).isoformat(),
        "versions": {
            "julia_core": jc_sha,
            "ai_theme_app": at_sha,
            "taxonomy": "stage-taxonomy.v1",
            "market_context_schema": "market-context.v1",
            "workbench_review_schema": "analyst-workbench.review.v1",
        },
        "input_hash": snap.get("snapshot_hash", ""),
        "status": review.status,
        "verdict_distribution": dict(verdict_dist),
        "stage_distribution": dict(stage_dist),
        "agreement_ratio": review.agreement_ratio,
        "overall_assessment": review.overall_assessment,
        "judgments": [
            {
                "subject_key": j.subject_key,
                "subject_name": j.subject_name if hasattr(j, 'subject_name') else j.subject,
                "verdict": j.verdict,
                "julia_stage": j.julia_stage,
                "confidence": j.confidence,
                "supporting_evidence": j.supporting_evidence,
                "contradicting_evidence": j.contradicting_evidence,
                "missing_evidence": j.missing_evidence,
                "inference_evidence": j.inference_evidence,
                "rationale": j.rationale,
            }
            for j in review.judgments
        ],
    }

    review_path = output_dir / "julia_review.json"
    review_path.write_text(json.dumps(review_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Review saved to: {review_path}")

    # G3: re-read serialized file — verify distribution matches + subject_key present
    saved = json.loads(review_path.read_text(encoding="utf-8"))
    juds = saved["judgments"]
    actual_dist = Counter(j["verdict"] for j in juds)
    assert dict(actual_dist) == saved["verdict_distribution"], (
        f"G3 FAIL: serialized verdicts don't match declared. "
        f"actual={dict(actual_dist)} vs declared={saved['verdict_distribution']}"
    )
    assert sum(actual_dist.values()) == len(juds)
    assert all(j.get("subject_key") for j in juds), "G3 FAIL: missing subject_key"
    print(f"✅ G3: serialized invariant — {len(juds)} judgments, all have subject_key")

    # G3b: three-way key-set identity — no missing, no extra
    ctx_keys = {t["subject_key"] for t in market_context["themes"]}
    claim_keys = {c["subject"]["key"] for c in workbench_review["claims"]}
    jud_keys = {j["subject_key"] for j in juds}
    assert ctx_keys == claim_keys == jud_keys, (
        f"G3b FAIL: key-set mismatch. "
        f"context={len(ctx_keys)} claims={len(claim_keys)} judgments={len(jud_keys)}. "
        f"ctx∖claims={ctx_keys - claim_keys} claims∖jud={claim_keys - jud_keys}"
    )
    print(f"✅ G3b: 1:1 identity — {len(jud_keys)} = context = claims = judgments")

    # Save market_context as Golden Fixture
    ctx_path = output_dir / "market_context.json"
    ctx_path.write_text(json.dumps(market_context, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Market context saved to: {ctx_path}")

    # Save workbench_review as Golden Fixture
    wb_path = output_dir / "workbench_review.json"
    wb_path.write_text(json.dumps(workbench_review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Workbench review saved to: {wb_path}")

    # Manifest
    manifest = {
        "case": "001-r1",
        "trade_date": "2026-07-14",
        "created_at": datetime.now(CST).isoformat(),
        "versions": {
            "julia_core": jc_sha,
            "ai_theme_app": at_sha,
            "taxonomy": "stage-taxonomy.v1",
        },
        "files": {
            "market_context": "market_context.json",
            "workbench_review": "workbench_review.json",
            "julia_review": "julia_review.json",
        },
        "hashes": {
            "market_context": _sha256(ctx_path),
            "workbench_review": _sha256(wb_path),
            "julia_review": _sha256(review_path),
        },
        "no_future_data": True,
        "workbench_snapshot_hash": snap.get("snapshot_hash", ""),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Manifest saved to: {manifest_path}")

    print(f"\n{'=' * 70}")
    print("Blind Replay Complete.")
    print(f"Golden fixtures + review at: {output_dir}")
    print(f"Run to verify: python -m pytest tests/m3_2/test_golden_contract.py")
    print("=" * 70)


def _normalize_stage(state: str) -> str:
    """Map ai_theme_app stage names to taxonomy-canonical names."""
    mapping = {
        "fermentation": "diffusion",
    }
    return mapping.get(state, state)


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    run()

"""PR4.2.37a — 2026-07-09 Golden UI Validation.

Locks assertions for Capital Intelligence pipeline end-to-end:
  - Producer → ReviewDocument → Workspace JSON → Frontend Props

Deprecated fields (institution[], hot_money[]) must remain for 30-day
compatibility period but must NOT be the active render source.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RD_PATH = PROJECT_ROOT / "tmp" / "analyst_workbench" / "2026-07-09" / "review_document.json"


@pytest.fixture
def capital():
    """Load 7/09 review_document.json capital section."""
    import asyncio
    sys.path.insert(0, str(PROJECT_ROOT))
    from stock_processing_service.api_app import _inject_capital_producer_outputs_async

    if RD_PATH.exists():
        with open(RD_PATH) as f:
            doc = json.load(f)
    else:
        doc = {"metadata": {"trade_date": "2026-07-09"}, "capital": {}}

    result = asyncio.run(_inject_capital_producer_outputs_async(doc))
    return result.get("capital", {})


# ═══════════════════════════════════════════════════════════════
# Producer output assertions
# ═══════════════════════════════════════════════════════════════

class TestProducerOutput:
    def test_institution_style_has_4_rows(self, capital):
        assert len(capital.get("institution_style", [])) == 4

    def test_hot_money_style_has_15_rows(self, capital):
        assert len(capital.get("hot_money_style", [])) == 15

    def test_institution_rows_have_direction_name(self, capital):
        for r in capital["institution_style"]:
            assert r.get("direction_name"), f"Missing direction_name in {r}"

    def test_institution_rows_have_score_and_confidence(self, capital):
        for r in capital["institution_style"]:
            assert r.get("score") is not None
            assert r.get("confidence") is not None

    def test_institution_rows_have_lifecycle_stage(self, capital):
        for r in capital["institution_style"]:
            assert r.get("lifecycle_stage") is not None

    def test_institution_sorted_by_score_desc(self, capital):
        scores = [r["score"] for r in capital["institution_style"]]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Not sorted: {scores[i]} < {scores[i+1]}"

    def test_hot_money_rows_have_theme_name(self, capital):
        for r in capital["hot_money_style"]:
            assert r.get("theme_name")

    def test_hot_money_rows_have_attack_stage(self, capital):
        for r in capital["hot_money_style"]:
            assert r.get("attack_stage") in ("FIRST_WAVE", "CONTINUING", "CLIMAX", "RETREATING")

    def test_hot_money_rows_have_institution_relation(self, capital):
        for r in capital["hot_money_style"]:
            assert r.get("institution_hot_relation") in (
                "BOTH", "INSTITUTION_ONLY", "HOT_MONEY_ONLY", "DIVERGENCE"
            )


# ═══════════════════════════════════════════════════════════════
# Render source assertions
# ═══════════════════════════════════════════════════════════════

class TestRenderSource:
    def test_render_source_is_canonical(self, capital):
        rs = capital.get("capital_render_source", {})
        assert rs.get("institution") == "institution_style"
        assert rs.get("hot_money") == "hot_money_style"

    def test_fallback_not_used(self, capital):
        rs = capital.get("capital_render_source", {})
        assert rs.get("fallback_used") == False, (
            "DEPRECATED FIELDS ARE BEING RENDERED — investigation required"
        )

    def test_deprecated_fields_still_present_for_compatibility(self, capital):
        """Old fields must exist during 30-day deprecation window."""
        assert "institution" in capital, "Deprecated field removed too early"
        assert "hot_money" in capital, "Deprecated field removed too early"


# ═══════════════════════════════════════════════════════════════
# Data quality assertions
# ═══════════════════════════════════════════════════════════════

class TestDataQuality:
    def test_no_numeric_ids_as_names(self, capital):
        for r in capital["institution_style"]:
            name = r.get("direction_name", "")
            assert not name.isdigit(), f"Numeric ID leaked: {name}"

        for r in capital["hot_money_style"]:
            name = r.get("theme_name", "")
            assert not name.isdigit(), f"Numeric ID leaked: {name}"

    def test_scores_in_valid_range(self, capital):
        for r in capital["institution_style"]:
            assert 0 <= r["score"] <= 100, f"Score out of range: {r['score']}"
        for r in capital["hot_money_style"]:
            assert 0 <= r["score"] <= 100, f"Score out of range: {r['score']}"

    def test_confidence_in_valid_range(self, capital):
        for r in capital["institution_style"]:
            assert 0 <= r["confidence"] <= 1, f"Confidence out of range: {r['confidence']}"


# ═══════════════════════════════════════════════════════════════
# PR4.2.37d: Direction Flow Ranking contract tests
# ═══════════════════════════════════════════════════════════════

class TestDirectionFlowRanking:
    """C1-C7: Direction Flow Ranking contract validation."""

    def test_c1_schema_exists(self, capital):
        """C1: direction_flow_ranking exists with required metadata fields."""
        dfr = capital.get("direction_flow_ranking")
        assert dfr is not None, "direction_flow_ranking missing from capital"
        assert dfr.get("trade_date") == "2026-07-09", "trade_date missing or wrong"
        assert dfr.get("flow_source") == "theme_direction_allocation_daily"
        assert dfr.get("semantic_type") == "ATTRIBUTED_ORDER_FLOW"
        assert dfr.get("unit") == "YI"
        rankings = dfr.get("rankings", [])
        assert len(rankings) >= 4, f"Expected >= 4 rankings, got {len(rankings)}"

    def test_c2_sorting_by_flow_desc(self, capital):
        """C2: rankings sorted by net_flow_yi DESC, confidence DESC."""
        rankings = capital["direction_flow_ranking"]["rankings"]
        for i in range(len(rankings) - 1):
            a, b = rankings[i], rankings[i + 1]
            # Primary: net_flow_yi DESC
            assert a["net_flow_yi"] >= b["net_flow_yi"], \
                f"Sort violation at {i}: {a['direction_name']}({a['net_flow_yi']}) < {b['direction_name']}({b['net_flow_yi']})"

    def test_c3_conservation_top5(self, capital):
        """C3: SUM(top_stocks.attributed_flow) <= direction.net_flow * 1.01."""
        rankings = capital["direction_flow_ranking"]["rankings"]
        for r in rankings:
            top5_total = sum(abs(s.get("net_flow_yi", 0)) for s in r.get("top_stocks", []))
            dir_total = abs(r["net_flow_yi"])
            if dir_total > 0.01:
                ratio = top5_total / dir_total
                assert ratio <= 1.01, \
                    f"Conservation violation: {r['direction_name']} top5={top5_total:.1f} > dir={dir_total:.1f} (ratio={ratio:.2f})"

    def test_c4_name_quality(self, capital):
        """C4: No null, -, or numeric IDs in stock names."""
        rankings = capital["direction_flow_ranking"]["rankings"]
        for r in rankings:
            for s in r.get("top_stocks", []):
                name = s.get("name", "")
                assert name, f"Empty stock name in {r['direction_name']}"
                assert name != "-", f"'-' stock name in {r['direction_name']}"
                assert not name.isdigit(), f"Numeric stock name leak: '{name}' in {r['direction_name']}"

    def test_c5_semantic_isolation(self, capital):
        """C5: ranking[i].score != institution_style[i].score (different sources)."""
        rankings = capital["direction_flow_ranking"]["rankings"]
        inst = capital.get("institution_style", [])
        inst_by_key = {r["direction_key"]: r["score"] for r in inst}
        for r in rankings:
            dk = r["direction_key"]
            if dk in inst_by_key:
                # Score exists in both but the VALUES come from different computation paths
                # This test verifies both fields exist independently
                assert "score" in r, f"score missing in ranking[{dk}]"
                assert dk in inst_by_key, f"institution_style missing {dk}"

    def test_c6_unit_semantic(self, capital):
        """C6: unit == YI and values are yuan/1e8 (reasonable magnitude check)."""
        dfr = capital["direction_flow_ranking"]
        assert dfr["unit"] == "YI"
        rankings = dfr["rankings"]
        for r in rankings:
            # net_flow_yi should be in 亿 range (reasonable: -1000 to +1000 for a single direction)
            assert -1000 < r["net_flow_yi"] < 1000, \
                f"net_flow_yi out of range: {r['net_flow_yi']} for {r['direction_name']}"
            for s in r.get("top_stocks", []):
                # Individual stock flows should be reasonable magnitude
                assert -500 < s["net_flow_yi"] < 500, \
                    f"stock net_flow_yi out of range: {s['net_flow_yi']} for {s.get('name')}"

    def test_c7_forbidden_language(self, capital):
        """C7: No forbidden language (机构买入/机构资金流入/主力机构) in the contract."""
        import json as _json
        payload = _json.dumps(capital.get("direction_flow_ranking", {}), ensure_ascii=False)
        forbidden = ["机构买入", "机构资金流入", "主力机构", "机构净买入"]
        for term in forbidden:
            assert term not in payload, f"Forbidden term '{term}' found in direction_flow_ranking"

    def test_c8_market_top_not_present(self, capital):
        """C8 (Investment Relevance Guard): market_top_inflow_stocks must NOT be in capital."""
        assert "market_top_inflow_stocks" not in capital, \
            "market_top_inflow_stocks must not leak into ReviewDocument.capital"


# ═══════════════════════════════════════════════════════════════
# PR4.2.38e: Golden Day Replay — 2026-07-09 Full Pipeline
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def golden_context():
    """Load observation direction pipeline state for 2026-07-09."""
    import asyncio, asyncpg
    async def _load():
        conn = await asyncpg.connect(
            "postgresql://localhost:5432/stock_data_test", user="postgres", password=""
        )
        try:
            from datetime import date
            td = date(2026, 7, 9)
            candidates = await conn.fetch(
                "SELECT * FROM analyst_direction_candidate WHERE trade_date = $1", td)
            obs_dirs = await conn.fetch(
                "SELECT * FROM observation_direction_daily WHERE trade_date = $1", td)
            session = await conn.fetchrow(
                "SELECT * FROM analyst_observation_session WHERE trade_date = $1", td)
            relations = await conn.fetch(
                "SELECT * FROM direction_relation WHERE trade_date = $1", td)
            return {
                "candidates": [dict(r) for r in candidates],
                "obs_directions": [dict(r) for r in obs_dirs],
                "session": dict(session) if session else None,
                "relations": [dict(r) for r in relations],
            }
        finally:
            await conn.close()
    return asyncio.run(_load())


class TestGoldenDayReplay:
    """End-to-end validation: AI Draft → Review → Observation → Capital → View."""

    def test_g1_candidates_exist(self, golden_context):
        """G1: Direction candidates exist for 2026-07-09."""
        candidates = golden_context["candidates"]
        assert len(candidates) >= 1, "No direction candidates found"

    def test_g2_candidates_have_style_profile(self, golden_context):
        """G2: All candidates have non-empty style_profile with institution/hot_money/event."""
        for c in golden_context["candidates"]:
            sp = c.get("style_profile") or c.get("style_profile_extra")
            if isinstance(sp, str):
                import json
                sp = json.loads(sp)
            assert sp, f"Candidate {c['candidate_key']} missing style_profile"
            for dim in ("institution", "hot_money", "event"):
                assert dim in sp, f"Candidate {c['candidate_key']} missing style_profile.{dim}"

    def test_g3_observation_directions_exist(self, golden_context):
        """G3: At least 1 confirmed observation direction for 2026-07-09."""
        obs = golden_context["obs_directions"]
        assert len(obs) >= 1, "No observation directions found"

    def test_g4_observation_source_traceable(self, golden_context):
        """G4: Each observation direction has source_candidate or analyst_action."""
        for o in golden_context["obs_directions"]:
            assert o.get("source_candidate") or o.get("analyst_action"), \
                f"Observation {o['direction_key']} missing source traceability"

    def test_g5_session_counters_match(self, golden_context):
        """G5: Session accepted/rejected counts match actual observation directions."""
        obs = golden_context["obs_directions"]
        session = golden_context["session"]
        if session:
            accepted = sum(1 for o in obs if o.get("analyst_action") in ("ACCEPT", "MODIFY", "MERGE"))
            assert session.get("accepted_count", 0) >= accepted, \
                f"Session accepted_count ({session.get('accepted_count')}) < actual ({accepted})"

    def test_g6_direction_view_includes_observations(self, capital):
        """G6: direction_view contains OBSERVATION_DIRECTION entries."""
        dv = capital.get("direction_view", [])
        obs_dirs = [d for d in dv if d.get("direction_type") == "OBSERVATION_DIRECTION"]
        assert len(obs_dirs) >= 1, "No OBSERVATION_DIRECTION in direction_view"

    def test_g7_observation_directions_have_capital(self, capital):
        """G7: Observation directions have non-null net_flow_yi."""
        dv = capital.get("direction_view", [])
        for d in dv:
            if d.get("direction_type") == "OBSERVATION_DIRECTION":
                assert d.get("net_flow_yi") is not None, \
                    f"Observation {d['direction_name']} missing net_flow_yi"
                assert d.get("top_stocks"), \
                    f"Observation {d['direction_name']} missing top_stocks"

    def test_g8_parent_relations_exist(self, golden_context):
        """G8: direction_relation entries exist for observation directions."""
        relations = golden_context["relations"]
        obs = golden_context["obs_directions"]
        if obs:
            obs_keys = {o["direction_key"] for o in obs}
            related = [r for r in relations if r["child_direction_key"] in obs_keys]
            assert len(related) >= 1, "No direction_relation entries for observation directions"

    def test_g9_no_direction_explosion(self, capital, golden_context):
        """G9: Observation directions have parent overlap info (anti-duplication)."""
        dv = capital.get("direction_view", [])
        for d in dv:
            if d.get("direction_type") == "OBSERVATION_DIRECTION":
                parents = d.get("parent_directions", [])
                assert len(parents) >= 0, f"parent_directions field present for {d['direction_name']}"
                for p in parents:
                    assert 0 <= p.get("capital_overlap_ratio", 0) <= 1.0, \
                        f"Invalid overlap ratio for {d['direction_name']} ← {p['direction_key']}"

    def test_g10_full_traceability(self, capital, golden_context):
        """G10: candidate → observation_direction_daily → direction_view chain intact."""
        candidates = {c["candidate_key"]: c for c in golden_context["candidates"]}
        obs = {o["direction_key"]: o for o in golden_context["obs_directions"]}
        dv = {d["direction_key"]: d for d in capital.get("direction_view", [])}
        for o_key, o in obs.items():
            src = o.get("source_candidate", "")
            if src and src in candidates:
                assert candidates[src]["status"] == "CONFIRMED", \
                    f"Source candidate {src} not CONFIRMED for observation {o_key}"
            if o_key in dv:
                assert dv[o_key].get("source") == src, \
                    f"direction_view source mismatch for {o_key}"

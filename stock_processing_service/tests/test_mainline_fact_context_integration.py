"""Integration test for FactContextBuilder + event chain with real DB."""
import pytest
from datetime import date, timedelta


def _make_read_port(pool, trade_date, lookback_days):
    """Create a read_port that queries DB directly (test utility)."""
    start = trade_date - timedelta(days=max(lookback_days - 1, 0))

    class _RP:
        def __init__(self, p): self._p = p

        async def get_subject_event_chain_rows(self, trade_date, subject_keys=None, lookback_days=7):
            if not subject_keys:
                return []
            rows = await self._p.fetch(
                """SELECT 'the_' || id AS event_id, subject_key,
                          rank_date::text AS occurred_at,
                          to_char(rank_date, 'YYYY-MM-DD') AS event_date,
                          COALESCE(driver_summary, description, '') AS title,
                          COALESCE(description, driver_summary, '') AS summary,
                          heat, source_type AS source_channel,
                          'theme_history_event' AS source_table
                   FROM theme_history_event
                   WHERE source_type = 'jyhf_history'
                     AND subject_key = ANY($1::text[])
                     AND rank_date BETWEEN $2::date AND $3::date
                   ORDER BY rank_date DESC, heat DESC""",
                subject_keys, start, trade_date,
            )
            result = []
            for r in rows:
                d = dict(r)
                heat = int(d.get("heat") or 0)
                title = str(d.get("title") or "").lower()
                for kw, et in [("政策","policy"),("产业","industry"),("技术","technology"),
                               ("订单","order"),("海外","overseas_mapping"),("监管","regulation"),
                               ("发布","media"),("公告","company")]:
                    if kw in title: d["event_type"] = et; break
                else: d["event_type"] = "unknown"
                d["event_type_source"] = "keyword_fallback"
                d["impact_score"] = 0.9 if heat >= 90 else (0.75 if heat >= 70 else (0.6 if heat >= 50 else (0.45 if heat >= 30 else 0.3)))
                d["confidence"] = 0.7 if heat >= 50 else 0.5
                result.append(d)
            return result

        async def get_subject_event_stats(self, *a, **kw): return []
        async def get_subject_cycle_evidence_daily(self, *a, **kw): return []
        async def get_mainline_cycle_by_subject_keys(self, *a, **kw): return []

    return _RP(pool)


async def _verify(pool, td, label):
    from stock_processing_service.application.services.mainline_discovery_fact_context_builder import (
        MainlineDiscoveryFactContextBuilder,
    )
    from stock_processing_service.domain.services.mainline_discovery.mainline_logic_chain_builder import (
        MainlineLogicChainBuilder,
    )

    read_port = _make_read_port(pool, td, 7)
    builder = MainlineDiscoveryFactContextBuilder(read_port)

    sks = await pool.fetch(
        """SELECT DISTINCT subject_key FROM theme_history_event
           WHERE source_type = 'jyhf_history'
             AND rank_date >= $1::date - 7 AND rank_date <= $1::date
           ORDER BY subject_key""",
        td,
    )
    subject_keys = [str(r["subject_key"]) for r in sks]
    if not subject_keys:
        pytest.skip(f"No subjects with events near {label}")

    ctx = await builder.build(trade_date=td, subject_keys_override=subject_keys[:50], lookback_days=7)
    d = ctx.to_dict()
    diag = d["diagnostics"]

    print(f"\n=== {label} ===")
    print(f"  candidates={diag['candidate_subject_count']} rows={diag.get('event_chain_row_count','?')} subjects={diag.get('event_chain_subject_count','?')} sources={diag.get('source_counts',{})}")

    assert diag.get("event_chain_row_count", 0) > 0, f"No event rows on {label}"
    assert diag.get("event_chain_subject_count", 0) > 0
    assert diag.get("source_counts", {}).get("theme_history_event", 0) > 0

    logic_builder = MainlineLogicChainBuilder(pool=None)
    logic_count = 0
    for sk, rows in d["event_rows_by_subject"].items():
        ev = logic_builder._build_for_subject(sk, rows)
        if ev.logic_score is not None:
            logic_count += 1
    print(f"  logic_score_non_null={logic_count}")
    assert logic_count > 0, f"No subjects with logic_score on {label}"


@pytest.mark.asyncio
class TestFactContextBuilderIntegration:

    @pytest.fixture
    async def pool(self):
        try:
            import asyncpg
            conn = await asyncpg.connect("postgresql://localhost/stock_data_test", timeout=5)
            yield conn
            await conn.close()
        except Exception:
            pytest.skip("DB not available")

    async def test_fact_context_20260428(self, pool):
        await _verify(pool, date(2026, 4, 28), "2026-04-28")

    async def test_fact_context_20260429(self, pool):
        await _verify(pool, date(2026, 4, 29), "2026-04-29")

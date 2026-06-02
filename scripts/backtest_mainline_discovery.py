"""PR-8: Backtest Mainline Discovery pipeline over a date range.

Usage:
  python scripts/backtest_mainline_discovery.py \
    --start-date 2026-04-01 --end-date 2026-04-30 \
    --db-dsn "postgresql://localhost/stock_data_test" \
    --out-json reports/mainline_discovery_backtest.json \
    --out-md reports/mainline_discovery_backtest.md

Outputs: daily metrics, interval stats, top review items, markdown report.
Does NOT compute PnL or validate buy points.
LLM unavailable -> fallback gracefully.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import asyncpg


# ── helpers ──

def _d(days: int) -> timedelta:
    return timedelta(days=days)


def _cpd_impact(title: str, confidence: float | None) -> float:
    """Estimate impact score from CDP DOM event title keywords."""
    t = (title or "").lower()
    for kw in ["政策", "监管", "冲突", "制裁", "突破", "重大"]:
        if kw in t:
            return 0.85
    for kw in ["发布", "订单", "产业", "技术"]:
        if kw in t:
            return 0.70
    conf = float(confidence or 0.5)
    return max(0.3, min(0.9, conf * 0.8))


def _build_read_port(pool, td, lookback: int):
    """Build a read_port similar to integration tests."""
    start = td - _d(max(lookback - 1, 0))

    class _RP:
        def __init__(self, p): self._p = p

        async def get_subject_event_chain_rows(self, trade_date, subject_keys=None, lookback_days=None):
            if not subject_keys:
                return []
            all_rows: list[dict] = []

            # ── 1. theme_history_event (legacy) ──
            rows1 = await self._p.fetch(
                """SELECT 'the_' || id AS event_id, subject_key, rank_date::text AS occurred_at,
                          to_char(rank_date,'YYYY-MM-DD') AS event_date,
                          COALESCE(driver_summary,description,'') AS title,
                          COALESCE(description,driver_summary,'') AS summary,
                          heat, source_type AS source_channel, 'theme_history_event' AS source_table
                   FROM theme_history_event WHERE source_type='jyhf_history'
                     AND subject_key=ANY($1::text[]) AND rank_date BETWEEN $2::date AND $3::date
                   ORDER BY rank_date DESC, heat DESC""",
                subject_keys, start, td,
            )
            for r in rows1:
                d = dict(r)
                h = int(d.get("heat") or 0)
                t = str(d.get("title") or "").lower()
                for kw, et in [("政策","policy"),("产业","industry"),("技术","technology"),
                               ("订单","order"),("海外","overseas_mapping"),("监管","regulation"),
                               ("发布","media"),("公告","company")]:
                    if kw in t: d["event_type"] = et; break
                else: d["event_type"] = "unknown"
                d["event_type_source"] = "keyword_fallback"
                d["impact_score"] = 0.9 if h>=90 else (0.75 if h>=70 else (0.6 if h>=50 else (0.45 if h>=30 else 0.3)))
                d["confidence"] = 0.7 if h>=50 else 0.5
                all_rows.append(d)

            # ── 2. CDP DOM: subject_history_staging (primary CDP source) ──
            rows2a = await self._p.fetch(
                """SELECT 'cdp_' || ingest_batch_id || '_' || subject_rank_id::text AS event_id,
                          subject_key, COALESCE(subject_name,'') AS theme_name,
                          rank_date::text AS occurred_at,
                          to_char(rank_date,'YYYY-MM-DD') AS event_date,
                          COALESCE(description, subject_name || ' 驱动事件', '') AS title,
                          COALESCE(description, '') AS summary,
                          0 AS heat,
                          source_type AS source_channel,
                          'subject_history_staging' AS source_table
                   FROM subject_history_staging
                   WHERE subject_key = ANY($1::text[])
                     AND rank_date BETWEEN $2::date AND $3::date
                   ORDER BY rank_date DESC""",
                subject_keys, start, td,
            )
            for r in rows2a:
                d = dict(r)
                t = str(d.get("title") or "").lower()
                for kw, et in [("政策","policy"),("产业","industry"),("技术","technology"),
                               ("订单","order"),("海外","overseas_mapping"),("监管","regulation"),
                               ("发布","media"),("公告","company"),("涨价","price_shock")]:
                    if kw in t: d["event_type"] = et; break
                else: d["event_type"] = "unknown"
                d["event_type_source"] = "cdp_staging"
                d["impact_score"] = 0.6
                d["confidence"] = 0.6
                all_rows.append(d)

            # ── 3. CDP DOM: event_subject_map + news_event (supplementary) ──
            rows2 = await self._p.fetch(
                """SELECT 'cdp_' || ne.id::text AS event_id, esm.subject_key,
                          esm.subject_name AS theme_name,
                          ne.event_time::text AS occurred_at,
                          to_char(ne.event_time,'YYYY-MM-DD') AS event_date,
                          COALESCE(ne.summary,'') AS title,
                          COALESCE(ne.summary,'') AS summary,
                          0 AS heat,
                          COALESCE(esm.source, 'jyhf_cdp') AS source_channel,
                          'event_subject_map+news_event' AS source_table
                   FROM event_subject_map esm
                   JOIN news_event ne ON ne.id = esm.news_id
                   WHERE esm.subject_key = ANY($1::text[])
                     AND ne.event_time::date BETWEEN $2::date AND $3::date
                   ORDER BY ne.event_time DESC""",
                subject_keys, start, td,
            )
            for r in rows2:
                d = dict(r)
                h = int(d.get("heat") or 0)
                d["event_type"] = d.get("event_type") or "unknown"
                d["event_type_source"] = "cdp_dom"
                d["impact_score"] = _cpd_impact(d.get("title",""), d.get("confidence"))
                d["confidence"] = float(d.get("confidence") or 0.5)
                all_rows.append(d)

            # dedup by (subject_key, event_date, title[:80])
            seen: set = set()
            deduped = []
            for d in all_rows:
                key = (str(d.get("subject_key") or ""), str(d.get("event_date") or "")[:10],
                       str(d.get("title") or "").strip()[:80])
                if key not in seen:
                    seen.add(key)
                    deduped.append(d)
            all_rows.sort(key=lambda x: str(x.get("occurred_at") or ""), reverse=True)
            return all_rows

        async def get_subject_event_stats(self, trade_date, subject_keys=None, lookback_days=None):
            if not subject_keys: return []
            rows = await self._p.fetch(
                """SELECT subject_key, COUNT(*) as recent_event_count,
                          COUNT(DISTINCT rank_date) as distinct_event_days,
                          COUNT(*) FILTER(WHERE rank_date=$1::date) as today_event_count
                   FROM theme_history_event WHERE source_type='jyhf_history'
                     AND subject_key=ANY($2::text[]) AND rank_date BETWEEN $3::date AND $1::date
                   GROUP BY subject_key""", td, subject_keys, start)
            return [dict(r) for r in rows]

        async def get_subject_cycle_evidence_daily(self, *a, **kw): return []
        async def get_mainline_cycle_by_subject_keys(self, subject_keys=None, trade_date=None):
            if not subject_keys: return []
            rows = await self._p.fetch(
                """SELECT subject_key, mainline_strength_score, final_mainline_alive,
                          fade_risk_score, final_cycle_state FROM theme_cycle_judgement_v2
                   WHERE trade_date=$1::date AND subject_key=ANY($2::text[])""",
                trade_date or td, subject_keys)
            return [dict(r) for r in rows]

    return _RP(pool)


async def _run_day(pool, td, lookback: int = 7):
    """Run discovery pipeline for one day, return daily metrics dict."""
    rp = _build_read_port(pool, td, lookback)

    # ── imports ──
    from stock_processing_service.application.services.mainline_discovery_fact_context_builder import (
        MainlineDiscoveryFactContextBuilder,
    )
    from stock_processing_service.domain.services.mainline_discovery.mainline_logic_chain_builder import (
        MainlineLogicChainBuilder,
    )
    from stock_processing_service.domain.services.mainline_discovery.mainline_market_acceptance_builder import (
        MainlineMarketAcceptanceBuilder,
    )
    from stock_processing_service.domain.services.mainline_discovery.major_event_classifier import (
        MajorEventClassifier,
    )
    from stock_processing_service.domain.services.mainline_discovery.mainline_narrative_judge import (
        MainlineNarrativeJudge,
    )
    from stock_processing_service.domain.services.mainline_discovery.mainline_discovery_engine import (
        MainlineDiscoveryEngine,
    )
    from stock_processing_service.domain.services.mainline_discovery.analyst_review_queue_builder import (
        AnalystReviewQueueBuilder,
    )

    # ── candidates: merge theme_history_event + CDP DOM event_subject_map ──
    sks1 = await pool.fetch(
        """SELECT DISTINCT subject_key FROM theme_history_event
           WHERE source_type='jyhf_history' AND rank_date>=$1::date-7 AND rank_date<=$1::date""",
        td,
    )
    sks2 = await pool.fetch(
        """SELECT DISTINCT esm.subject_key FROM event_subject_map esm
           JOIN news_event ne ON ne.id = esm.news_id
           WHERE ne.event_time::date >= $1::date - 7 AND ne.event_time::date <= $1::date""",
        td,
    )
    sks3 = await pool.fetch(
        """SELECT DISTINCT subject_key FROM subject_history_staging
           WHERE rank_date >= $1::date - 7 AND rank_date <= $1::date""",
        td,
    )
    sks_all: set[str] = set()
    for r in sks1:
        sks_all.add(str(r["subject_key"]))
    for r in sks2:
        sks_all.add(str(r["subject_key"]))
    for r in sks3:
        sks_all.add(str(r["subject_key"]))
    subject_keys = sorted(sks_all)

    # ── fact context ──
    fact_builder = MainlineDiscoveryFactContextBuilder(rp)
    ctx = await fact_builder.build(trade_date=td, subject_keys_override=subject_keys[:80], lookback_days=lookback)
    fc = ctx.to_dict()

    # ── logic ──
    logic_builder = MainlineLogicChainBuilder()
    logic_result = await logic_builder.build(
        trade_date=td,
        candidate_subjects=[s["subject_key"] for s in fc["candidate_subjects"]],
        report_context={},
    )
    logic_by_sk = {sk: ev.to_dict() for sk, ev in logic_result.items()} if isinstance(logic_result, dict) else {}

    # ── market ──
    market_builder = MainlineMarketAcceptanceBuilder()
    market_result = market_builder.build(
        trade_date=td,
        candidate_subjects=fc["candidate_subjects"],
        event_rows_by_subject=fc["event_rows_by_subject"],
        cycle_evidence_by_subject=fc["cycle_evidence_by_subject"],
        cycle_judgement_by_subject=fc["cycle_judgement_by_subject"],
        capital_by_subject=fc["capital_by_subject"],
        stock_facts_by_subject=fc["stock_facts_by_subject"],
    )
    market_by_sk = {sk: r.to_dict() for sk, r in market_result.items()}

    # ── major event ──
    major_classifier = MajorEventClassifier()
    major_by_sk = {}
    for sk, lev in logic_by_sk.items():
        ec = lev.get("event_chain", [])
        if ec:
            major_by_sk[sk] = major_classifier.classify(event_chain=ec, event_series=lev.get("event_series", [])).to_dict()

    # ── narrative (LLM best-effort, will always fail in script = fallback to rule) ──
    narrative_by_sk = {}
    # Note: LLM unavailable in CLI → engine falls back to rule logic

    # ── discovery engine ──
    engine = MainlineDiscoveryEngine()
    decisions = engine.evaluate_all(
        candidate_subjects=fc["candidate_subjects"],
        logic_evidence_by_subject=logic_by_sk,
        market_acceptance_by_subject=market_by_sk,
        major_event_by_subject=major_by_sk,
        narrative_by_subject=narrative_by_sk,
    )

    # ── analyst review ──
    queue_builder = AnalystReviewQueueBuilder()
    review_items, review_diag = queue_builder.build(
        decisions=decisions, trade_date=td.isoformat(),
        event_evidence_by_subject=logic_by_sk,
        market_by_subject=market_by_sk,
    )

    # ── daily metrics ──
    sd = fc.get("diagnostics", {})
    top3 = sorted(review_items, key=lambda x: x.review_priority, reverse=True)[:3]
    return {
        "trade_date": td.isoformat(),
        "candidate_subject_count": sd.get("candidate_subject_count", 0),
        "event_chain_subject_count": sd.get("event_chain_subject_count", 0),
        "logic_score_non_null_count": sum(1 for v in logic_by_sk.values() if v.get("logic_score") is not None),
        "market_acceptance_non_null_count": sum(1 for v in market_by_sk.values() if v.get("market_acceptance_score") is not None),
        "machine_fast_candidate_count": sum(1 for d in decisions if d.machine_state == "machine_fast_candidate"),
        "machine_slow_candidate_count": sum(1 for d in decisions if d.machine_state == "machine_slow_candidate"),
        "logic_only_count": sum(1 for d in decisions if d.machine_state == "logic_only"),
        "market_noise_count": sum(1 for d in decisions if d.machine_state == "market_noise"),
        "rotation_hotspot_count": sum(1 for d in decisions if d.machine_state == "rotation_hotspot"),
        "rejected_count": sum(1 for d in decisions if d.machine_state == "rejected"),
        "analyst_review_item_count": len(review_items),
        "top_review_items": [
            {"subject_key": it.subject_key, "theme_name": it.theme_name,
             "machine_state": it.machine_state, "review_priority": it.review_priority,
             "review_reason": it.review_reason, "hybrid_logic_score": it.scores.get("hybrid_logic_score"),
             "market_acceptance_score": it.scores.get("market_acceptance_score"),
             "major_event_score": it.scores.get("major_event_score")}
            for it in top3
        ],
        "diagnostics": {
            "data_quality": sd.get("data_quality", "unknown"),
            "llm_unavailable_count": 0,
            "empty_event_subject_count": sd.get("empty_event_subject_count", 0),
        },
    }


async def run_backtest(start: date, end: date, dsn: str, lookback: int = 7) -> dict[str, Any]:
    pool = await asyncpg.connect(dsn)
    daily_results: list[dict] = []

    td = start
    while td <= end:
        try:
            result = await _run_day(pool, td, lookback)
            daily_results.append(result)
            print(f"  {td}: candidates={result['candidate_subject_count']} "
                  f"events={result['event_chain_subject_count']} "
                  f"fast={result['machine_fast_candidate_count']} "
                  f"slow={result['machine_slow_candidate_count']}")
        except Exception as exc:
            print(f"  {td}: ERROR — {exc}")
            daily_results.append({"trade_date": td.isoformat(), "error": str(exc)[:200]})
        td += _d(1)

    await pool.close()

    # ── interval stats ──
    review_days = [r for r in daily_results if r.get("analyst_review_item_count", 0) > 0]
    avg_review = sum(r.get("analyst_review_item_count", 0) for r in review_days) / max(len(review_days), 1)
    max_review = max((r.get("analyst_review_item_count", 0) for r in daily_results), default=0)

    # ── continuation: machine_candidate_3d_continuation_rate ──
    by_subject: dict[str, list[int]] = {}  # subject_key → [day_indices]
    for i, r in enumerate(daily_results):
        for item in r.get("top_review_items", []):
            sk = item.get("subject_key", "")
            if sk:
                by_subject.setdefault(sk, []).append(i)
    cont_count = 0
    total_cand = 0
    for sk, days in by_subject.items():
        for d in days:
            total_cand += 1
            # check if appears again within next 3 days
            if any(x in days for x in range(d + 1, min(d + 4, len(daily_results)))):
                cont_count += 1
    cont_rate = cont_count / max(total_cand, 1)

    # ── noise failure rate ──
    noise_subjects: dict[str, list[int]] = {}
    for i, r in enumerate(daily_results):
        if r.get("market_noise_count", 0) > 0:
            # find subjects classified as market_noise on this day
            items = r.get("top_review_items", [])
            for item in items:
                if item.get("machine_state") == "market_noise":
                    noise_subjects.setdefault(item.get("subject_key", ""), []).append(i)
    noise_total = sum(len(v) for v in noise_subjects.values())
    noise_fail = 0
    for sk, days in noise_subjects.items():
        for d in days:
            # check if upgraded to candidate in next 3 days
            upgraded = any(
                any(it.get("machine_state") in {"machine_fast_candidate", "machine_slow_candidate"}
                    for it in daily_results[x].get("top_review_items", []))
                for x in range(d + 1, min(d + 4, len(daily_results)))
            )
            if not upgraded:
                noise_fail += 1
    noise_rate = noise_fail / max(noise_total, 1)

    # ── logic_only upgrade rate ──
    logic_only_subjects: dict[str, list[int]] = {}
    for i, r in enumerate(daily_results):
        if r.get("logic_only_count", 0) > 0:
            for item in r.get("top_review_items", []):
                if item.get("machine_state") == "logic_only":
                    logic_only_subjects.setdefault(item.get("subject_key", ""), []).append(i)
    lo_total = sum(len(v) for v in logic_only_subjects.values())
    lo_upgrade = 0
    for sk, days in logic_only_subjects.items():
        for d in days:
            if any(
                any(it.get("machine_state") in {"machine_slow_candidate"}
                    for it in daily_results[x].get("top_review_items", []))
                for x in range(d + 1, min(d + 4, len(daily_results)))
            ):
                lo_upgrade += 1
    lo_rate = lo_upgrade / max(lo_total, 1)

    return {
        "config": {"start_date": start.isoformat(), "end_date": end.isoformat(), "lookback_days": lookback},
        "daily_results": daily_results,
        "interval_stats": {
            "total_days": len(daily_results),
            "candidate_days_count": len(review_days),
            "avg_review_items_per_day": round(avg_review, 1),
            "max_review_items_per_day": max_review,
            "machine_candidate_3d_continuation_rate": round(cont_rate, 3),
            "market_noise_failure_rate": round(noise_rate, 3),
            "logic_only_upgrade_rate": round(lo_rate, 3),
        },
    }


def write_markdown(report: dict, path: str) -> None:
    stats = report["interval_stats"]
    lines = [
        "# Mainline Discovery Backtest",
        f"**Range**: {report['config']['start_date']} → {report['config']['end_date']}",
        f"**Lookback**: {report['config']['lookback_days']} days",
        "",
        "## Interval Statistics",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total days | {stats['total_days']} |",
        f"| Days with candidates | {stats['candidate_days_count']} |",
        f"| Avg review items/day | {stats['avg_review_items_per_day']} |",
        f"| Max review items/day | {stats['max_review_items_per_day']} |",
        f"| Candidate 3d continuation | {stats['machine_candidate_3d_continuation_rate']:.1%} |",
        f"| Market noise failure rate | {stats['market_noise_failure_rate']:.1%} |",
        f"| Logic-only upgrade rate | {stats['logic_only_upgrade_rate']:.1%} |",
        "",
        "## Top Review Items (all days)",
    ]
    all_items = []
    for r in report["daily_results"]:
        for item in r.get("top_review_items", []):
            all_items.append({**item, "trade_date": r["trade_date"]})
    all_items.sort(key=lambda x: x.get("review_priority", 0), reverse=True)
    for item in all_items[:20]:
        lines.append(
            f"- `{item['trade_date']}` **{item['theme_name']}** "
            f"({item['machine_state']}) priority={item['review_priority']} "
            f"logic={item.get('hybrid_logic_score','?')} market={item.get('market_acceptance_score','?')}"
        )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Markdown written to {path}")


# ── CLI ──

def main():
    p = argparse.ArgumentParser(description="Mainline Discovery Backtest")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--db-dsn", default="postgresql://localhost/stock_data_test")
    p.add_argument("--lookback-days", type=int, default=7)
    p.add_argument("--out-json", default="reports/mainline_discovery_backtest.json")
    p.add_argument("--out-md", default="reports/mainline_discovery_backtest.md")
    args = p.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if start > end:
        print("Error: start_date must be <= end_date", file=sys.stderr)
        sys.exit(1)

    print(f"Backtesting {start} → {end}...")
    report = asyncio.run(run_backtest(start, end, args.db_dsn, args.lookback_days))

    # Write JSON
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"JSON written to {args.out_json}")

    # Write MD
    write_markdown(report, args.out_md)

    # Summary
    stats = report["interval_stats"]
    print(f"\nDone. {stats['total_days']} days, avg {stats['avg_review_items_per_day']} reviews/day, "
          f"cont={stats['machine_candidate_3d_continuation_rate']:.1%}, "
          f"noise_fail={stats['market_noise_failure_rate']:.1%}")


if __name__ == "__main__":
    main()

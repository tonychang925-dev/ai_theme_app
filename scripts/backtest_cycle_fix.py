"""Backtest: compare old vs new cycle_judgement classifications.

Reads all historical snapshots, extracts the old final_cycle_state,
simulates what the new logic would classify, and reports differences.
"""

import asyncio
import json
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal

import asyncpg

sys.path.insert(0, "/Users/admin/Desktop/ai_theme_app/stock_processing_service")

from stock_processing_service.domain.services.cycle_evidence_builder import (
    CycleEvidence,
)
from stock_processing_service.domain.services.cycle_judgement_service import (
    CycleJudgementService,
)

DSN = "postgresql://localhost:5432/stock_data_test"
TABLE = "post_market_recap_snapshot"


def _safe_decimal(value, default=Decimal("0")):
    try:
        if value is None or str(value).strip() == "":
            return default
        return Decimal(str(value))
    except Exception:
        return default


async def main():
    conn = await asyncpg.connect(DSN)

    # Load all snapshots sorted by date
    rows = await conn.fetch(
        f"SELECT trade_date, payload FROM {TABLE} ORDER BY trade_date ASC"
    )
    await conn.close()

    svc = CycleJudgementService()
    prev_state_by_subject: dict[str, str] = {}

    # Track changes
    changes: dict[str, list[dict]] = defaultdict(list)  # subject_key -> [{date, old, new}]
    all_dates: list[str] = []
    total_judgements = 0
    changed_judgements = 0

    for row in rows:
        trade_date_str = str(row["trade_date"])
        all_dates.append(trade_date_str)

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        doc = payload.get("recap_doc", payload)
        rc = doc.get("report_context", {})

        # Get old cycle data
        cycles = rc.get("cycles", []) or rc.get("theme_cycle_judgement_v2", [])
        if not isinstance(cycles, list):
            continue

        for c in cycles:
            if not isinstance(c, dict):
                continue
            sk = str(c.get("subject_key") or "").strip()
            if not sk:
                continue
            old_state = str(c.get("final_cycle_state") or c.get("mainline_state") or "").strip()
            if not old_state:
                continue

            # Build evidence for new judgement
            prev = prev_state_by_subject.get(sk, "unknown")
            try:
                evidence = CycleEvidence(
                    trade_date=date.fromisoformat(trade_date_str),
                    stock_id=sk,
                    subject_key=sk,
                    subject_name=str(c.get("theme_name") or sk),
                    close_price=Decimal("0"),
                    pct_chg=Decimal("0"),
                    previous_state=prev,
                    event_score=_safe_decimal(c.get("state_strength_score", 0)),
                    continuity_score=_safe_decimal(c.get("mainline_strength_score", 0)),
                    leader_score=Decimal("50"),
                    relay_score=Decimal("50"),
                    board_score=Decimal("50"),
                    support_score=_safe_decimal(c.get("theme_support_score", 50)),
                    leader_breakdown_flag=bool(c.get("fade_confirmed", False)),
                    red_ratio=_safe_decimal(c.get("red_ratio", 0.5)),
                    big_drop_ratio=_safe_decimal(c.get("big_drop_ratio", 0.1)),
                    limit_down_count=int(c.get("limit_down_count") or 0),
                    front_row_survival_ratio=_safe_decimal(c.get("front_row_survival_ratio", 0.5)),
                    break_start_pivot=bool(c.get("support_break", False)),
                    theme_support_score=_safe_decimal(c.get("theme_support_score", 50)),
                    strong_event_count_7d=int(c.get("strong_event_count_7d") or 0),
                )
            except (ValueError, TypeError, KeyError):
                continue

            result = svc.judge_one(evidence)
            new_state = result.final_cycle_state
            prev_state_by_subject[sk] = new_state

            total_judgements += 1
            if old_state != new_state:
                changed_judgements += 1
                changes[sk].append({
                    "date": trade_date_str,
                    "old": old_state,
                    "new": new_state,
                    "name": str(c.get("theme_name", sk))[:60],
                })

    # Report
    print(f"Dates processed: {len(all_dates)} ({all_dates[0]} → {all_dates[-1]})")
    print(f"Total judgements: {total_judgements}")
    print(f"Changed: {changed_judgements} ({100*changed_judgements/total_judgements:.1f}%)")
    print()

    # Group changes by subject
    for sk, entries in sorted(changes.items(), key=lambda x: -len(x[1])):
        names = {e["name"] for e in entries}
        print(f"\n### {', '.join(names)[:80]} ({sk}) — {len(entries)} changes")
        for e in entries[:10]:  # show first 10
            print(f"  {e['date']}  {e['old']:<16} → {e['new']:<16}")

    # State transition matrix
    print(f"\n\n=== State Transition Matrix ===")
    transitions: dict[tuple[str, str], int] = defaultdict(int)
    for entries in changes.values():
        for e in entries:
            transitions[(e["old"], e["new"])] += 1
    for (old, new), count in sorted(transitions.items(), key=lambda x: -x[1]):
        print(f"  {old:<16} → {new:<16}  {count:>4}")

    # Summary by new state
    print(f"\n=== New State Distribution (last day: {all_dates[-1]}) ===")
    new_counts: dict[str, int] = defaultdict(int)
    old_counts: dict[str, int] = defaultdict(int)
    for entries in changes.values():
        for e in entries:
            new_counts[e["new"]] += 1
            old_counts[e["old"]] += 1
    for state in sorted(set(list(new_counts) + list(old_counts))):
        print(f"  {state:<16}  old={old_counts.get(state,0):>4}  new={new_counts.get(state,0):>4}")


asyncio.run(main())

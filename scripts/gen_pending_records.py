"""Generate first 3 pending records for historical cognitive backtest.

Pairs: 7/1→7/2, 7/2→7/3, 7/3→7/6
Output: tmp/backtest/pending/
"""

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

import asyncpg

sys.path.insert(0, "/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, "/Users/admin/Desktop/ai_theme_app/stock_processing_service")

from stock_processing_service.application.services.market_cognition.replay import (
    MarketCognitionReplay,
)

DSN = os.getenv("DATABASE_URL", "postgresql://localhost:5432/stock_data_test")
TABLE = "post_market_recap_snapshot"
TARGET_DATES = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"]
OUTPUT = Path("/Users/admin/Desktop/ai_theme_app/tmp/backtest/pending")


async def main():
    conn = await asyncpg.connect(DSN)

    snapshots = []
    for trade_date in TARGET_DATES:
        d = date.fromisoformat(trade_date)
        row = await conn.fetchrow(
            f"SELECT payload FROM {TABLE} WHERE trade_date=$1::date ORDER BY created_at DESC LIMIT 1",
            d,
        )
        if row:
            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
            snapshots.append({"trade_date": trade_date, "payload": payload})
            print(f"Loaded: {trade_date}")
        else:
            print(f"MISSING: {trade_date}")

    await conn.close()

    # Build pairs from available snapshots (consecutive)
    pairs = [
        (snapshots[i], snapshots[i + 1])
        for i in range(len(snapshots) - 1)
    ]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    count = 0
    for day_d, day_d_next in pairs:
        record = MarketCognitionReplay.run_pair(day_d, day_d_next)
        if record is None:
            print(f"SKIP: {day_d['trade_date']}→{day_d_next['trade_date']} (no eligible hypothesis)")
            continue

        path = OUTPUT / f"{record.record_id}.json"
        path.write_text(
            json.dumps(
                {
                    "record_id": record.record_id,
                    "validation_mode": record.validation_mode,
                    "thesis_trade_date": record.thesis_trade_date,
                    "verification_trade_date": record.verification_trade_date,
                    "hypothesis_id": record.hypothesis_id,
                    "hypothesis_statement": record.hypothesis_statement,
                    "prediction_probability": record.prediction_probability,
                    "source_quality_score": record.source_quality_score,
                    "source_policy_version": record.source_policy_version,
                    "hypothesis_deadline": record.hypothesis_deadline,
                    "source_knowledge_hash": record.source_knowledge_hash,
                    "source_evidence_hash": record.source_evidence_hash,
                    "source_context_hash": record.source_context_hash,
                    "source_thesis_hash": record.source_thesis_hash,
                    "reality_evidence_hash": record.reality_evidence_hash,
                    "frozen_at": record.frozen_at,
                    "status": "pending_review",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Created: {record.record_id}")
        print(f"  Hypothesis: {record.hypothesis_statement[:120]}")
        print(f"  Deadline: {record.hypothesis_deadline}")
        print(f"  Probability: {record.prediction_probability}")
        count += 1

    print(f"\nDone. {count} pending records. Output: {OUTPUT}")


asyncio.run(main())

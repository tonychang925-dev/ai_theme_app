import asyncio
import json
import os
from datetime import datetime

import asyncpg


async def main() -> None:
    db = (
        f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'zxbzj~925')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DATABASE', 'stock_data_test')}"
    )
    conn = await asyncpg.connect(db)
    try:
        trade_date = datetime.strptime("2026-04-09", "%Y-%m-%d").date()
        judgements = await conn.fetch(
            """
            SELECT subject_key, theme_name, leader_status, model_name, reasoning_summary
            FROM theme_leader_llm_judgement
            WHERE trade_date = $1
            ORDER BY subject_key
            LIMIT 50
            """,
            trade_date,
        )
        queue = await conn.fetch(
            """
            SELECT subject_key, theme_name, need_llm_judgement, queue_priority, queue_reason
            FROM theme_leader_llm_queue
            WHERE trade_date = $1
            ORDER BY queue_priority DESC, subject_key
            LIMIT 50
            """,
            trade_date,
        )
        print(
            json.dumps(
                {
                    "judgement_count": len(judgements),
                    "judgements": [dict(r) for r in judgements],
                    "queue_count": len(queue),
                    "queue": [dict(r) for r in queue],
                },
                ensure_ascii=False,
                default=str,
                indent=2,
            )
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

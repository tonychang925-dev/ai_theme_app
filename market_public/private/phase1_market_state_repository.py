"""Market-owned exact-date post-market recap read port."""
from __future__ import annotations

from typing import Any, Dict, Optional

from theme_service.repositories.phase1_read_repository import Phase1ReadRepository


class Phase1MarketStateReadRepository(Phase1ReadRepository):
    """Extend Market's private Phase1 binding with the exact recap read port."""

    async def get_existing_post_market_recap_snapshot(
        self,
        trade_date: str,
    ) -> Optional[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT trade_date, snapshot_version, batch_id, trace_id, payload
        FROM post_market_recap_snapshot
        WHERE trade_date = $1::date
        LIMIT 1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, trade_date)
            return dict(row) if row else None

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.services.weak_to_strong_auction_data_adapter import (
    AuctionFeatureRow,
    WeakToStrongAuctionDataAdapter,
)
from stock_service.services.weak_to_strong_auction_scorer import (
    AuctionScoreBreakdown,
    WeakToStrongAuctionScorer,
)


@dataclass
class AuctionConfirmResult:
    trade_date: date
    total_candidates: int
    persisted_count: int
    level_count: Dict[str, int]


class WeakToStrongAuctionService:
    """盘前候选确认服务：只消费候选池并产出 A/B/C/X 信号。"""

    def __init__(
        self,
        config: Optional[StockServiceConfig] = None,
        adapter: Optional[WeakToStrongAuctionDataAdapter] = None,
        scorer: Optional[WeakToStrongAuctionScorer] = None,
    ):
        self.config = config or StockServiceConfig()
        self.adapter = adapter or WeakToStrongAuctionDataAdapter(self.config)
        self.scorer = scorer or WeakToStrongAuctionScorer()
        self.pool: Optional[asyncpg.Pool] = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_database,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                min_size=1,
                max_size=3,
            )
        return self.pool

    async def close(self) -> None:
        await self.adapter.close()
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def confirm(self, trade_date: date) -> AuctionConfirmResult:
        all_features = await self.adapter.load_features(trade_date)
        # Phase 3 收口：只有 formal 才进入正式盘前确认与信号落库。
        features = [f for f in all_features if (f.pool_entry_type or "formal") == "formal"]
        current_stock_ids = [f.stock_id for f in features]
        await self._delete_stale_rows(trade_date, current_stock_ids)
        rows = []
        level_count = {"A": 0, "B": 0, "C": 0, "X": 0}
        for f in features:
            breakdown = self.scorer.score(f)
            level_count[breakdown.signal_level] = level_count.get(breakdown.signal_level, 0) + 1
            evidence = self.scorer.to_evidence(f, breakdown)
            rows.append(self._to_row(f, breakdown, evidence))
        persisted = await self._upsert(rows)
        return AuctionConfirmResult(
            trade_date=trade_date,
            total_candidates=len(features),
            persisted_count=persisted,
            level_count=level_count,
        )

    async def _delete_stale_rows(self, trade_date: date, current_stock_ids: List[str]) -> None:
        pool = await self._ensure_pool()
        valid_stock_ids = [sid for sid in current_stock_ids if str(sid or "").strip()]
        async with pool.acquire() as conn:
            if not valid_stock_ids:
                await conn.execute(
                    """
                    DELETE FROM weak_to_strong_auction_signal
                    WHERE trade_date = $1::date
                    """,
                    trade_date,
                )
                return
            await conn.execute(
                """
                DELETE FROM weak_to_strong_auction_signal
                WHERE trade_date = $1::date
                  AND stock_id NOT IN (
                    SELECT sid
                    FROM unnest($2::text[]) AS t(sid)
                    WHERE sid IS NOT NULL AND sid <> ''
                  )
                """,
                trade_date,
                valid_stock_ids,
            )

    async def get_replay_by_candidate_id(self, candidate_id: int) -> Optional[Dict[str, object]]:
        pool = await self._ensure_pool()
        sql = """
        SELECT
            c.id AS candidate_id,
            c.trade_date AS candidate_trade_date,
            c.next_trade_date,
            c.stock_id,
            c.stock_name,
            c.subject_key,
            c.theme_name,
            c.candidate_type,
            c.candidate_score,
            c.support_type,
            c.support_strength,
            c.pool_entry_type,
            c.cycle_state,
            c.mainline_strength_score,
            c.fade_watch,
            c.fade_confirmed,
            c.evidence_json AS candidate_evidence,
            s.trade_date AS signal_trade_date,
            s.signal_level,
            s.decision,
            s.confirmation_score,
            s.data_status,
            s.evidence_json AS signal_evidence
        FROM weak_to_strong_candidate_pool c
        LEFT JOIN weak_to_strong_auction_signal s
          ON s.candidate_id = c.id
        WHERE c.id = $1
        LIMIT 1
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, candidate_id)
        if not row:
            return None
        candidate_evidence = self._parse_json_field(row["candidate_evidence"])
        signal_evidence = self._parse_json_field(row["signal_evidence"])
        return {
            "candidate_id": int(row["candidate_id"]),
            "candidate_trade_date": row["candidate_trade_date"].isoformat() if row["candidate_trade_date"] else "",
            "confirm_trade_date": row["next_trade_date"].isoformat() if row["next_trade_date"] else "",
            "stock_id": str(row["stock_id"]),
            "stock_name": str(row["stock_name"] or ""),
            "subject_key": str(row["subject_key"] or ""),
            "theme_name": str(row["theme_name"] or ""),
            "candidate_type": str(row["candidate_type"] or ""),
            "candidate_score": float(row["candidate_score"] or 0),
            "support_type": str(row["support_type"] or ""),
            "support_strength": float(row["support_strength"] or 0),
            "pool_entry_type": str(row["pool_entry_type"] or ""),
            "cycle_state": str(row["cycle_state"] or ""),
            "mainline_strength_score": float(row["mainline_strength_score"] or 0),
            "fade_watch": bool(row["fade_watch"]),
            "fade_confirmed": bool(row["fade_confirmed"]),
            "signal_level": str(row["signal_level"] or ""),
            "decision": str(row["decision"] or ""),
            "confirmation_score": float(row["confirmation_score"] or 0),
            "data_status": str(row["data_status"] or ""),
            "candidate_evidence": candidate_evidence,
            "signal_evidence": signal_evidence,
        }

    async def list_replay_by_trade_date(
        self,
        trade_date: date,
        *,
        signal_level: str = "",
        limit: int = 200,
    ) -> List[Dict[str, object]]:
        pool = await self._ensure_pool()
        sql = """
        SELECT
            c.id AS candidate_id,
            c.stock_id,
            c.stock_name,
            c.candidate_type,
            c.candidate_score,
            c.pool_entry_type,
            c.cycle_state,
            c.mainline_strength_score,
            c.fade_watch,
            c.fade_confirmed,
            s.signal_level,
            s.decision,
            s.confirmation_score,
            s.data_status,
            s.evidence_json
        FROM weak_to_strong_candidate_pool c
        LEFT JOIN weak_to_strong_auction_signal s
          ON s.candidate_id = c.id
         AND s.trade_date = $1::date
        WHERE c.next_trade_date = $1::date
          AND ($2::text = '' OR COALESCE(s.signal_level, '') = $2::text)
        ORDER BY c.candidate_score DESC, c.id ASC
        LIMIT $3
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, signal_level, max(int(limit), 1))
        payload: List[Dict[str, object]] = []
        for row in rows:
            payload.append(
                {
                    "candidate_id": int(row["candidate_id"]),
                    "stock_id": str(row["stock_id"]),
                    "stock_name": str(row["stock_name"] or ""),
                    "candidate_type": str(row["candidate_type"] or ""),
                    "candidate_score": float(row["candidate_score"] or 0),
                    "pool_entry_type": str(row["pool_entry_type"] or ""),
                    "cycle_state": str(row["cycle_state"] or ""),
                    "mainline_strength_score": float(row["mainline_strength_score"] or 0),
                    "fade_watch": bool(row["fade_watch"]),
                    "fade_confirmed": bool(row["fade_confirmed"]),
                    "signal_level": str(row["signal_level"] or ""),
                    "decision": str(row["decision"] or ""),
                    "confirmation_score": float(row["confirmation_score"] or 0),
                    "data_status": str(row["data_status"] or ""),
                    "signal_evidence": self._parse_json_field(row["evidence_json"]),
                }
            )
        return payload

    @staticmethod
    def _parse_json_field(value: object) -> Dict[str, object]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    def _to_row(
        self,
        f: AuctionFeatureRow,
        b: AuctionScoreBreakdown,
        evidence: Dict[str, object],
    ) -> Dict[str, object]:
        return {
            "trade_date": f.trade_date,
            "stock_id": f.stock_id,
            "stock_name": f.stock_name,
            "candidate_id": f.candidate_id,
            "auction_open_pct": f.auction_open_pct,
            "auction_high_pct": f.auction_high_pct,
            "auction_low_pct": f.auction_low_pct,
            "auction_close_pct": f.auction_close_pct,
            "auction_amount": float(f.raw_snapshot.get("auction_amount") or 0.0),
            "auction_volume": float(f.raw_snapshot.get("auction_volume") or 0.0),
            "auction_pattern": "tail_lift" if f.price_lift_last_minute else ("tail_drop" if f.tail_drop_flag else "stable"),
            "auction_pattern_score": b.pattern_stability,
            "auction_stability_score": max(0.0, 100.0 - f.auction_path_volatility),
            "last_minute_grab_score": b.last_minute_grab,
            "plate_follow_score": b.plate_follow,
            "risk_penalty": b.risk_penalty,
            "confirmation_score": b.confirmation_score,
            "signal_level": b.signal_level,
            "decision": b.decision,
            "data_status": f.data_status,
            "data_latency_ms": f.data_latency_ms,
            "source_snapshot_id": f.source_snapshot_id,
            "evidence_json": json.dumps(evidence, ensure_ascii=False),
        }

    async def _upsert(self, rows: List[Dict[str, object]]) -> int:
        if not rows:
            return 0
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO weak_to_strong_auction_signal (
            trade_date, stock_id, stock_name, candidate_id,
            auction_open_pct, auction_high_pct, auction_low_pct, auction_close_pct,
            auction_amount, auction_volume, auction_pattern, auction_pattern_score,
            auction_stability_score, last_minute_grab_score, plate_follow_score,
            risk_penalty, confirmation_score, signal_level, decision,
            data_status, data_latency_ms, source_snapshot_id, evidence_json, created_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7, $8,
            $9, $10, $11, $12,
            $13, $14, $15,
            $16, $17, $18, $19,
            $20, $21, $22, $23::jsonb, NOW()
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            candidate_id = EXCLUDED.candidate_id,
            auction_open_pct = EXCLUDED.auction_open_pct,
            auction_high_pct = EXCLUDED.auction_high_pct,
            auction_low_pct = EXCLUDED.auction_low_pct,
            auction_close_pct = EXCLUDED.auction_close_pct,
            auction_amount = EXCLUDED.auction_amount,
            auction_volume = EXCLUDED.auction_volume,
            auction_pattern = EXCLUDED.auction_pattern,
            auction_pattern_score = EXCLUDED.auction_pattern_score,
            auction_stability_score = EXCLUDED.auction_stability_score,
            last_minute_grab_score = EXCLUDED.last_minute_grab_score,
            plate_follow_score = EXCLUDED.plate_follow_score,
            risk_penalty = EXCLUDED.risk_penalty,
            confirmation_score = EXCLUDED.confirmation_score,
            signal_level = EXCLUDED.signal_level,
            decision = EXCLUDED.decision,
            data_status = EXCLUDED.data_status,
            data_latency_ms = EXCLUDED.data_latency_ms,
            source_snapshot_id = EXCLUDED.source_snapshot_id,
            evidence_json = EXCLUDED.evidence_json
        """
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for r in rows:
                    await conn.execute(
                        sql,
                        r["trade_date"],
                        r["stock_id"],
                        r["stock_name"],
                        r["candidate_id"],
                        r["auction_open_pct"],
                        r["auction_high_pct"],
                        r["auction_low_pct"],
                        r["auction_close_pct"],
                        r["auction_amount"],
                        r["auction_volume"],
                        r["auction_pattern"],
                        r["auction_pattern_score"],
                        r["auction_stability_score"],
                        r["last_minute_grab_score"],
                        r["plate_follow_score"],
                        r["risk_penalty"],
                        r["confirmation_score"],
                        r["signal_level"],
                        r["decision"],
                        r["data_status"],
                        r["data_latency_ms"],
                        r["source_snapshot_id"],
                        r["evidence_json"],
                    )
                    count += 1
        return count

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

from stock_service.config import StockServiceConfig


@dataclass
class AuctionFeatureRow:
    candidate_id: int
    trade_date: date
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    candidate_type: str
    expected_open_low: float
    expected_open_high: float
    need_last_minute_grab: bool
    need_plate_follow: bool
    support_level: float
    support_strength: float
    pool_entry_type: str
    cycle_state: str
    mainline_strength_score: float
    fade_watch: bool
    fade_confirmed: bool
    # 标准化特征
    auction_open_pct: float
    auction_close_pct: float
    auction_high_pct: float
    auction_low_pct: float
    auction_path_volatility: float
    last_minute_volume_ratio: float
    tail_drop_flag: bool
    price_lift_last_minute: bool
    plate_red_ratio: float
    plate_leader_strength: float
    data_status: str
    data_latency_ms: int
    source_snapshot_id: str
    raw_snapshot: Dict[str, Any]


class WeakToStrongAuctionDataAdapter:
    """将候选池和竞价快照转换为评分器可消费的标准特征。"""

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
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
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def load_features(self, trade_date: date) -> List[AuctionFeatureRow]:
        pool = await self._ensure_pool()
        candidate_rows = await self._load_candidates(pool, trade_date)
        if not candidate_rows:
            return []

        watch_ids = await self._load_watch_universe_stock_ids(pool, trade_date)
        if watch_ids:
            filtered_rows = self._filter_candidates_by_watch_universe(candidate_rows, watch_ids)
            # 弱转强阶段二的主输入应是候选池。
            # watch_universe 仅做可选收敛，不能导致候选被清空，否则会出现“突然0结果”。
            if filtered_rows:
                candidate_rows = filtered_rows
        if not candidate_rows:
            return []

        stock_ids = [str(r["stock_id"]) for r in candidate_rows]
        snapshots = await self._load_auction_snapshots(pool, trade_date, stock_ids)
        plate_ctx = await self._load_plate_context(pool, trade_date)
        fallback_plate_ctx: Dict[str, Dict[str, float]] = {}
        fallback_trade_date = candidate_rows[0].get("candidate_trade_date") if candidate_rows else None
        if isinstance(fallback_trade_date, date) and fallback_trade_date != trade_date:
            fallback_plate_ctx = await self._load_plate_context(pool, fallback_trade_date)

        now = datetime.now(timezone.utc)
        features: List[AuctionFeatureRow] = []
        for c in candidate_rows:
            stock_id = str(c["stock_id"])
            snap = snapshots.get(stock_id)
            subject_key = str(c.get("subject_key") or "")
            plate = plate_ctx.get(subject_key)
            if plate is None and fallback_plate_ctx:
                plate = fallback_plate_ctx.get(subject_key)
            if plate is None:
                plate = {"plate_red_ratio": 0.0, "plate_leader_strength": 0.0}

            data_status, latency_ms = self._calc_data_status(snap, now, trade_date)
            open_pct = float(snap.get("auction_open_pct") or 0.0) if snap else 0.0
            close_pct, high_pct, low_pct = self._derive_ohlc_pct(open_pct, snap)
            stability = float(snap.get("price_path_stability_score") or 0.0) if snap else 0.0
            volatility = max(0.0, 100.0 - stability)
            last_ratio = float(snap.get("last_minute_ratio") or 0.0) if snap else 0.0
            tail_drop = bool(snap.get("has_end_drop") or False) if snap else False
            tail_lift = bool(snap.get("has_end_spike") or False) if snap else False
            source_snapshot_id = str(snap.get("source_trace_id") or "") if snap else ""

            features.append(
                AuctionFeatureRow(
                    candidate_id=int(c["id"]),
                    trade_date=trade_date,
                    stock_id=stock_id,
                    stock_name=str(c.get("stock_name") or stock_id),
                    subject_key=subject_key,
                    theme_name=str(c.get("theme_name") or subject_key),
                    candidate_type=str(c.get("candidate_type") or "generic_repair"),
                    expected_open_low=float(c.get("expected_open_low") or 0.0),
                    expected_open_high=float(c.get("expected_open_high") or 0.0),
                    need_last_minute_grab=bool(c.get("need_last_minute_grab") or False),
                    need_plate_follow=bool(c.get("need_plate_follow") or False),
                    support_level=float(c.get("support_level") or 0.0),
                    support_strength=float(c.get("support_strength") or 0.0),
                    pool_entry_type=str(c.get("pool_entry_type") or "formal"),
                    cycle_state=str(c.get("cycle_state") or ""),
                    mainline_strength_score=float(c.get("mainline_strength_score") or 0.0),
                    fade_watch=bool(c.get("fade_watch") or False),
                    fade_confirmed=bool(c.get("fade_confirmed") or False),
                    auction_open_pct=open_pct,
                    auction_close_pct=close_pct,
                    auction_high_pct=high_pct,
                    auction_low_pct=low_pct,
                    auction_path_volatility=volatility,
                    last_minute_volume_ratio=last_ratio,
                    tail_drop_flag=tail_drop,
                    price_lift_last_minute=tail_lift,
                    plate_red_ratio=float(plate.get("plate_red_ratio") or 0.0),
                    plate_leader_strength=float(plate.get("plate_leader_strength") or 0.0),
                    data_status=data_status,
                    data_latency_ms=latency_ms,
                    source_snapshot_id=source_snapshot_id,
                    raw_snapshot=snap or {},
                )
            )
        return features

    async def _load_candidates(self, pool: asyncpg.Pool, trade_date: date) -> List[asyncpg.Record]:
        sql = """
        SELECT
            id, trade_date AS candidate_trade_date, stock_id, stock_name, subject_key, theme_name,
            candidate_type, expected_open_low, expected_open_high,
            need_last_minute_grab, need_plate_follow,
            support_level, support_strength,
            pool_entry_type, cycle_state, mainline_strength_score, fade_watch, fade_confirmed
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
        ORDER BY candidate_score DESC, id ASC
        """
        async with pool.acquire() as conn:
            return await conn.fetch(sql, trade_date)

    async def _load_watch_universe_stock_ids(self, pool: asyncpg.Pool, trade_date: date) -> List[str]:
        sql = """
        SELECT stock_id
        FROM auction_watch_universe
        WHERE trade_date = $1::date
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [str(r["stock_id"]) for r in rows if str(r["stock_id"] or "").strip()]

    def _filter_candidates_by_watch_universe(
        self,
        candidate_rows: List[asyncpg.Record],
        watch_ids: List[str],
    ) -> List[asyncpg.Record]:
        if not watch_ids:
            return candidate_rows
        allowed_aliases = set()
        for sid in watch_ids:
            allowed_aliases.update(self._stock_id_aliases(sid))
        filtered: List[asyncpg.Record] = []
        for row in candidate_rows:
            aliases = self._stock_id_aliases(str(row["stock_id"]))
            if aliases & allowed_aliases:
                filtered.append(row)
        return filtered

    async def _load_auction_snapshots(
        self,
        pool: asyncpg.Pool,
        trade_date: date,
        stock_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        if not stock_ids:
            return {}
        compact_ids = [sid.split(".", 1)[0] for sid in stock_ids]
        sql = """
        SELECT
            stock_id,
            auction_open_pct,
            last_minute_ratio,
            price_path_stability_score,
            has_end_spike,
            has_end_drop,
            source_type,
            source_trace_id,
            created_at
        FROM pre_market_auction_snapshot
        WHERE trade_date = $1::date
          AND (stock_id = ANY($2::text[]) OR split_part(stock_id, '.', 1) = ANY($3::text[]))
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, stock_ids, compact_ids)

        alias_index: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            row_dict = dict(row)
            for alias in self._stock_id_aliases(str(row["stock_id"])):
                alias_index.setdefault(alias, []).append(row_dict)

        payload: Dict[str, Dict[str, Any]] = {}
        for candidate_stock_id in stock_ids:
            matched: List[Dict[str, Any]] = []
            seen_ids = set()
            for alias in self._stock_id_aliases(candidate_stock_id):
                for row in alias_index.get(alias, []):
                    key = str(row.get("stock_id") or "")
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    matched.append(row)
            best = self._select_best_snapshot(matched)
            if best:
                payload[candidate_stock_id] = best
        return payload

    async def _load_plate_context(self, pool: asyncpg.Pool, trade_date: date) -> Dict[str, Dict[str, float]]:
        # 盘前确认优先使用竞价快照构建题材联动代理：
        # - plate_red_ratio: 题材内竞价红盘占比（auction_open_pct > 0）
        # - plate_leader_strength: 题材内强开比例（auction_open_pct >= 2 或红区）
        # 若竞价快照缺失，再回退到日频快照（仅作兜底）。
        auction_sql = """
        SELECT
            subject_key,
            AVG(CASE WHEN COALESCE(auction_open_pct, 0) > 0 THEN 1.0 ELSE 0.0 END) AS plate_red_ratio,
            AVG(
                CASE
                    WHEN COALESCE(auction_open_pct, 0) >= 2.0 OR COALESCE(is_red_zone, FALSE) THEN 1.0
                    ELSE 0.0
                END
            ) AS plate_leader_strength
        FROM pre_market_auction_snapshot
        WHERE trade_date = $1::date
          AND subject_key IS NOT NULL
          AND subject_key <> ''
        GROUP BY subject_key
        """
        async with pool.acquire() as conn:
            auction_rows = await conn.fetch(auction_sql, trade_date)
        if auction_rows:
            payload: Dict[str, Dict[str, float]] = {}
            for row in auction_rows:
                payload[str(row["subject_key"])] = {
                    "plate_red_ratio": float(row["plate_red_ratio"] or 0.0),
                    "plate_leader_strength": float(row["plate_leader_strength"] or 0.0),
                }
            return payload

        daily_sql = """
        SELECT
            subject_key,
            AVG(CASE WHEN COALESCE(pct_chg, 0) > 0 THEN 1.0 ELSE 0.0 END) AS plate_red_ratio,
            AVG(CASE WHEN COALESCE(rank_order, 999) <= 3 OR COALESCE(is_leader, FALSE) THEN 1.0 ELSE 0.0 END) AS plate_leader_strength
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND subject_key IS NOT NULL
          AND subject_key <> ''
        GROUP BY subject_key
        """
        async with pool.acquire() as conn:
            daily_rows = await conn.fetch(daily_sql, trade_date)
        payload: Dict[str, Dict[str, float]] = {}
        for row in daily_rows:
            payload[str(row["subject_key"])] = {
                "plate_red_ratio": float(row["plate_red_ratio"] or 0.0),
                "plate_leader_strength": float(row["plate_leader_strength"] or 0.0),
            }
        return payload

    @staticmethod
    def _calc_data_status(snapshot: Optional[Dict[str, Any]], now_utc: datetime, trade_date: date) -> tuple[str, int]:
        if not snapshot:
            return "missing", 0
        created_at = snapshot.get("created_at")
        if created_at is None:
            return "partial", 0
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        latency_ms = max(int((now_utc - created_at).total_seconds() * 1000), 0)
        source_type = str(snapshot.get("source_type") or "")
        if source_type.endswith(".proxy"):
            return "partial", latency_ms
        shape_features = snapshot.get("shape_features")
        if isinstance(shape_features, list):
            shape_tokens = {str(item) for item in shape_features}
            if "single_point_snapshot" in shape_tokens or "result_only_mode" in shape_tokens:
                return "partial", latency_ms
        source_trace = snapshot.get("source_trace")
        if isinstance(source_trace, dict):
            if str(source_trace.get("record_mode") or "").strip().lower() == "single_point":
                return "partial", latency_ms
        # 历史交易日不按实时延迟判定 delayed，避免回放场景全部降级为 X。
        # 同交易日仅在 9:20-9:30 竞价窗口才启用严格实时延迟门禁；盘后回放不应触发 delayed。
        now_cn = now_utc.astimezone()
        if trade_date == date.today() and now_cn.hour == 9 and now_cn.minute <= 30 and latency_ms > 2_000:
            return "delayed", latency_ms
        return "ok", latency_ms

    @staticmethod
    def _normalize_stock_id(value: str) -> str:
        raw = str(value or "").strip().upper()
        if not raw:
            return ""
        if "." in raw:
            return raw
        if raw.startswith(("6", "9")):
            return f"{raw}.SH"
        if raw.startswith(("4", "8")):
            return f"{raw}.BJ"
        return f"{raw}.SZ"

    @classmethod
    def _stock_id_aliases(cls, value: str) -> set[str]:
        raw = str(value or "").strip().upper()
        if not raw:
            return set()
        normalized = cls._normalize_stock_id(raw)
        aliases = {raw, normalized}
        if "." in normalized:
            aliases.add(normalized.split(".", 1)[0])
        return {alias for alias in aliases if alias}

    @staticmethod
    def _select_best_snapshot(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not rows:
            return None

        def _sort_key(row: Dict[str, Any]) -> tuple[int, float]:
            source_type = str(row.get("source_type") or "")
            proxy_rank = 1 if source_type.endswith(".proxy") else 0
            created_at = row.get("created_at")
            created_ts = created_at.timestamp() if created_at else 0.0
            return (proxy_rank, -created_ts)

        return sorted(rows, key=_sort_key)[0]

    @staticmethod
    def _derive_ohlc_pct(open_pct: float, snapshot: Optional[Dict[str, Any]]) -> tuple[float, float, float]:
        if not snapshot:
            return open_pct, open_pct, open_pct

        last_ratio = float(snapshot.get("last_minute_ratio") or 0.0)
        has_end_spike = bool(snapshot.get("has_end_spike") or False)
        has_end_drop = bool(snapshot.get("has_end_drop") or False)

        move = max(0.15, min(1.20, last_ratio * 8.0))
        if has_end_spike and not has_end_drop:
            close_pct = open_pct + move
        elif has_end_drop and not has_end_spike:
            close_pct = open_pct - move
        else:
            close_pct = open_pct
        high_pct = max(open_pct, close_pct)
        low_pct = min(open_pct, close_pct)
        return close_pct, high_pct, low_pct

"""P2-B-4: JYHF Auction Timeline Extractor.

从 jyhf_stock_quote_snapshot 提取 9:15-9:25 竞价过程数据，
构造 timeline_points，调用 AuctionSnapshotBuilderService
生成 timeline-enhanced PreMarketAuctionSnapshot。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any

import asyncpg

from stock_service.services.auction_signal_service import AuctionTimelinePoint
from stock_service.services.auction_snapshot_builder_service import (
    AuctionRecordParsed,
    AuctionSnapshotBuilderService,
)
from stock_service.services.auction_signal_service import AuctionCandidateInput

logger = logging.getLogger("sps.jyhf_market.auction_timeline")

TZ_CN = timezone(timedelta(hours=8))

# 9:15:00 ~ 9:25:59
_AUCTION_START = "09:15:00"
_AUCTION_END = "09:26:00"
_LAST_MINUTE_START = "09:24:00"


class JyhfAuctionTimelineExtractor:
    """从 JYHF quote 快照表提取竞价时间线。"""

    def __init__(self, dsn: str, builder: AuctionSnapshotBuilderService | None = None):
        self._dsn = dsn
        self._builder = builder or AuctionSnapshotBuilderService()
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    async def extract_timelines(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> dict[str, tuple[AuctionTimelinePoint, ...]]:
        """提取竞价时间线: stock_id -> timeline_points。"""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT stock_id, current, amount, ts::text AS ts_text
               FROM jyhf_stock_quote_snapshot
               WHERE trade_date = $1
                 AND ts::time BETWEEN $2::time AND $3::time
                 AND current IS NOT NULL
               ORDER BY stock_id, ts""",
            trade_date, _AUCTION_START, _AUCTION_END,
        )

        result: dict[str, list[AuctionTimelinePoint]] = {}
        for row in rows:
            sid = row["stock_id"]
            ts_raw = str(row["ts_text"] or "")
            if not ts_raw:
                continue
            # 提取 HH:MM:SS
            ts_time = ts_raw.split("T")[-1].split("+")[0].split("-")[0][:8]
            if sid not in result:
                result[sid] = []
            result[sid].append(AuctionTimelinePoint(
                ts=ts_time,
                price=float(row["current"]) if row["current"] is not None else 0.0,
                amount=float(row["amount"]) if row["amount"] is not None else 0.0,
            ))

        return {sid: tuple(sorted(pts, key=lambda p: p.ts)) for sid, pts in result.items()}

    async def extract_final_auction_data(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> dict[str, AuctionRecordParsed]:
        """提取 9:25 竞价终态数据（最后一笔 current = auction_open_price）。"""
        pool = await self._get_pool()

        # 取每个 stock 在竞价窗口最后一笔
        rows = await pool.fetch(
            """SELECT DISTINCT ON (stock_id)
                 stock_id, current AS auction_open_price,
                 amount AS auction_amount, vol AS auction_volume
               FROM jyhf_stock_quote_snapshot
               WHERE trade_date = $1
                 AND ts::time BETWEEN $2::time AND $3::time
                 AND current IS NOT NULL
               ORDER BY stock_id, ts DESC""",
            trade_date, _AUCTION_START, _AUCTION_END,
        )

        result: dict[str, AuctionRecordParsed] = {}
        for row in rows:
            sid = row["stock_id"]
            result[sid] = AuctionRecordParsed(
                stock_id=sid,
                auction_open_price=float(row["auction_open_price"] or 0),
                auction_volume=float(row["auction_volume"] or 0),
                auction_amount=float(row["auction_amount"] or 0),
                pre_close=None,
                raw_keys=("jyhf_current", "jyhf_amount", "jyhf_vol"),
            )
        return result

    async def get_previous_day_bars(
        self, prev_trade_date: date, stock_ids: list[str]
    ) -> dict[str, dict[str, float]]:
        """获取前一交易日的 close 和 amount_proxy (for carry_ratio)。"""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT stock_id, close, amount
               FROM jyhf_stock_quote_snapshot
               WHERE trade_date = $1
                 AND close IS NOT NULL
               ORDER BY ts DESC""",
            prev_trade_date,
        )
        result: dict[str, dict[str, float]] = {}
        seen = set()
        for row in rows:
            sid = row["stock_id"]
            if sid in seen:
                continue
            seen.add(sid)
            result[sid] = {
                "close": float(row["close"] or 0),
                "amount_proxy": float(row["amount"] or 0),
            }
        return result

    async def build_timeline_snapshots(
        self,
        trade_date: date,
        candidate_trade_date: date,
        candidates: list[dict[str, Any]],
        *,
        proxy_ratio: float = 0.08,
    ) -> list[dict[str, Any]]:
        """完整流程：提取时间线 → 构造 timeline-enhanced snapshot → 返回 snapshot rows。"""
        stock_ids = [str(c.get("stock_id") or "") for c in candidates if str(c.get("stock_id") or "").strip()]
        if not stock_ids:
            return []

        timelines = await self.extract_timelines(trade_date, stock_ids)
        finals = await self.extract_final_auction_data(trade_date, stock_ids)

        # 前一交易日
        prev_day = _prev_weekday(trade_date)
        prev_bars = await self.get_previous_day_bars(prev_day, stock_ids)
        # fallback: prev_close 用前一交易日的 close
        pre_close_map: dict[str, float] = {sid: bar["close"] for sid, bar in prev_bars.items()}

        snapshots: list[dict[str, Any]] = []
        for row in candidates:
            sid = str(row.get("stock_id") or "").strip().upper()
            final = finals.get(sid)
            if final is None:
                # 尝试去掉后缀再查
                for alias in _stock_aliases(sid):
                    final = finals.get(alias)
                    if final:
                        break
            if final is None:
                continue

            points = timelines.get(sid, ())
            if not points:
                # 无时间线 → fallback 到单点
                points = (
                    AuctionTimelinePoint("09:25:00", final.auction_open_price or 0, final.auction_amount or 0),
                )

            # 前一交易日 close
            pre_close = pre_close_map.get(sid, 0.0)
            if not pre_close:
                for alias in _stock_aliases(sid):
                    pre_close = pre_close_map.get(alias, 0.0)
                    if pre_close:
                        break

            final.pre_close = pre_close

            prev_bar = prev_bars.get(sid, {})
            prev_amount_proxy = round(prev_bar.get("amount_proxy", 0) * proxy_ratio, 2)

            candidate_input = AuctionCandidateInput(
                trade_date=trade_date.isoformat(),
                stock_id=sid,
                stock_name=str(row.get("stock_name") or ""),
                subject_key=str(row.get("subject_key") or ""),
                theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
                role_label=_candidate_role(str(row.get("candidate_type") or "")),
                mainline_alive=True,
                action_bias="watch_open",
                is_reversal_watch=True,
            )

            snapshot = self._builder.build_timeline_enhanced_snapshot(
                candidate_input,
                final,
                timeline_points=points,
                prev_day_close=pre_close,
                prev_day_max_intraday_amount_proxy=prev_amount_proxy,
            )

            snapshots.append(_snapshot_to_dict(snapshot, trade_date, candidate_trade_date))

        logger.info("Timeline snapshots built: %d/%d candidates", len(snapshots), len(candidates))
        return snapshots

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None


def _stock_aliases(sid: str) -> list[str]:
    """Generate possible stock_id aliases."""
    s = sid.strip().upper()
    result = [s]
    if "." in s:
        result.append(s.split(".")[0])
    else:
        result.append(s)
    return result


def _candidate_role(ctype: str) -> str:
    if "dragon" in ctype or "subdragon" in ctype:
        return "龙头"
    return "观察"


def _prev_weekday(d: date) -> date:
    """Return the previous weekday."""
    from datetime import timedelta
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def _snapshot_to_dict(snapshot, trade_date: date, candidate_trade_date: date) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "stock_id": snapshot.stock_id,
        "stock_name": snapshot.stock_name,
        "subject_key": snapshot.subject_key,
        "theme_name": snapshot.theme_name,
        "role_label": snapshot.role_label,
        "window_start_time": snapshot.window_start_time,
        "window_end_time": snapshot.window_end_time,
        "last_minute_start_time": snapshot.last_minute_start_time,
        "last_30s_start_time": snapshot.last_30s_start_time,
        "auction_open_price": snapshot.auction_open_price,
        "pre_close": snapshot.pre_close,
        "auction_open_pct": snapshot.auction_open_pct,
        "auction_volume": snapshot.auction_volume,
        "auction_amount": snapshot.auction_amount,
        "last_minute_amount": snapshot.last_minute_amount,
        "last_minute_ratio": snapshot.last_minute_ratio,
        "prev_day_max_intraday_amount": snapshot.prev_day_max_intraday_amount,
        "carry_ratio": snapshot.carry_ratio,
        "price_path_stability_score": snapshot.price_path_stability_score,
        "is_red_zone": snapshot.is_red_zone,
        "has_end_spike": snapshot.has_end_spike,
        "has_end_drop": snapshot.has_end_drop,
        "shape_features": list(snapshot.shape_features),
        "source_type": "jyhf_auction_timeline",
        "source_trace_id": snapshot.source_trace_id,
        "source_trace": dict(snapshot.source_trace or {}),
        "source_version": snapshot.source_version,
        "rule_version": snapshot.rule_version,
    }

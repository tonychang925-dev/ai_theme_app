from __future__ import annotations

import hashlib
from dataclasses import dataclass

from stock_service.models import PreMarketAuctionSnapshot
from stock_service.services.auction_signal_service import (
    AuctionCandidateInput,
    AuctionSignalService,
    AuctionSnapshotInput,
    AuctionTimelinePoint,
)


def _to_float(value) -> float:
    if value in (None, "", "null"):
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


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


@dataclass(frozen=True)
class AuctionRecordParsed:
    stock_id: str
    auction_open_price: float
    auction_volume: float
    auction_amount: float
    pre_close: float
    raw_keys: tuple[str, ...]


class AuctionSnapshotBuilderService:
    """
    第一版竞价快照构建器：
    - 优先兼容 Tushare stk_auction 单点结果
    - 明确记录 single-point / proxy 口径
    - 后续接入 Level2 时间序列时，只替换这里
    """

    def __init__(self, signal_service: AuctionSignalService | None = None):
        self.signal_service = signal_service or AuctionSignalService()

    def parse_tushare_auction_record(self, row: dict) -> AuctionRecordParsed:
        stock_id = _normalize_stock_id(row.get("ts_code") or row.get("stock_id") or row.get("code"))
        return AuctionRecordParsed(
            stock_id=stock_id,
            auction_open_price=_to_float(row.get("price") or row.get("auction_price") or row.get("open")),
            auction_volume=_to_float(row.get("vol") or row.get("auction_vol") or row.get("volume")),
            auction_amount=_to_float(row.get("amount") or row.get("auction_amount") or row.get("成交额")),
            pre_close=_to_float(row.get("pre_close") or row.get("prev_close") or row.get("昨收")),
            raw_keys=tuple(sorted(str(k) for k in row.keys())),
        )

    def parse_timeline_points(self, rows: list[dict] | tuple[dict, ...] | None) -> tuple[AuctionTimelinePoint, ...]:
        points: list[AuctionTimelinePoint] = []
        for row in rows or []:
            ts = str(row.get("ts") or row.get("time") or "").strip()
            if not ts:
                continue
            points.append(
                AuctionTimelinePoint(
                    ts=ts,
                    price=_to_float(row.get("price")),
                    amount=_to_float(row.get("amount")),
                )
            )
        points.sort(key=lambda item: item.ts)
        return tuple(points)

    def derive_last_minute_amount(
        self,
        points: tuple[AuctionTimelinePoint, ...],
        fallback_amount: float,
        *,
        last_minute_start: str = "09:24:00",
    ) -> float:
        if not points:
            return fallback_amount
        eligible = [point for point in points if point.ts >= last_minute_start]
        if not eligible:
            return fallback_amount
        first = eligible[0].amount
        last = eligible[-1].amount
        derived = max(0.0, last - first)
        return derived if derived > 0 else fallback_amount

    def build_single_point_snapshot(
        self,
        candidate: AuctionCandidateInput,
        parsed: AuctionRecordParsed,
        *,
        prev_day_close: float,
        prev_day_max_intraday_amount_proxy: float,
    ) -> PreMarketAuctionSnapshot:
        pre_close = parsed.pre_close or prev_day_close
        auction_amount = parsed.auction_amount
        payload = AuctionSnapshotInput(
            candidate=candidate,
            pre_close=pre_close,
            auction_open_price=parsed.auction_open_price,
            auction_volume=parsed.auction_volume,
            auction_amount=auction_amount,
            prev_day_max_intraday_amount=prev_day_max_intraday_amount_proxy,
            last_minute_amount=auction_amount,
            points=(AuctionTimelinePoint("09:25:00", parsed.auction_open_price, auction_amount),),
        )
        snapshot = self.signal_service.build_snapshot(payload)
        trace_id = hashlib.md5(
            f"{snapshot.trade_date}|{snapshot.stock_id}|{snapshot.subject_key}|{snapshot.auction_open_price:.4f}|{snapshot.auction_amount:.2f}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return PreMarketAuctionSnapshot(
            trade_date=snapshot.trade_date,
            stock_id=snapshot.stock_id,
            stock_name=snapshot.stock_name,
            subject_key=snapshot.subject_key,
            theme_name=snapshot.theme_name,
            role_label=snapshot.role_label,
            window_start_time=snapshot.window_start_time,
            window_end_time=snapshot.window_end_time,
            last_minute_start_time=snapshot.last_minute_start_time,
            last_30s_start_time=snapshot.last_30s_start_time,
            auction_open_price=snapshot.auction_open_price,
            pre_close=snapshot.pre_close,
            auction_open_pct=snapshot.auction_open_pct,
            auction_volume=snapshot.auction_volume,
            auction_amount=snapshot.auction_amount,
            last_minute_amount=snapshot.last_minute_amount,
            last_minute_ratio=snapshot.last_minute_ratio,
            prev_day_max_intraday_amount=snapshot.prev_day_max_intraday_amount,
            carry_ratio=snapshot.carry_ratio,
            price_path_stability_score=snapshot.price_path_stability_score,
            is_red_zone=snapshot.is_red_zone,
            has_end_spike=snapshot.has_end_spike,
            has_end_drop=snapshot.has_end_drop,
            shape_features=["result_only_mode", "single_point_snapshot", *snapshot.shape_features],
            source_trace_id=trace_id,
            source_trace={
                "record_mode": "single_point",
                "raw_keys": list(parsed.raw_keys),
                "prev_day_max_intraday_amount_proxy": prev_day_max_intraday_amount_proxy,
                "proxy_method": "subject_stock_daily_snapshot.amount * proxy_ratio",
            },
            source_version="auction_snapshot.v1",
            rule_version="auction_snapshot.v1.single_point_proxy",
        )

    def build_timeline_enhanced_snapshot(
        self,
        candidate: AuctionCandidateInput,
        parsed: AuctionRecordParsed,
        *,
        timeline_points: tuple[AuctionTimelinePoint, ...],
        prev_day_close: float,
        prev_day_max_intraday_amount_proxy: float,
    ) -> PreMarketAuctionSnapshot:
        pre_close = parsed.pre_close or prev_day_close
        auction_amount = parsed.auction_amount
        last_minute_amount = self.derive_last_minute_amount(timeline_points, auction_amount)
        payload = AuctionSnapshotInput(
            candidate=candidate,
            pre_close=pre_close,
            auction_open_price=parsed.auction_open_price,
            auction_volume=parsed.auction_volume,
            auction_amount=auction_amount,
            prev_day_max_intraday_amount=prev_day_max_intraday_amount_proxy,
            last_minute_amount=last_minute_amount,
            points=timeline_points,
        )
        snapshot = self.signal_service.build_snapshot(payload)
        trace_id = hashlib.md5(
            f"{snapshot.trade_date}|{snapshot.stock_id}|{snapshot.subject_key}|{snapshot.auction_open_price:.4f}|{snapshot.last_minute_amount:.2f}|timeline".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return PreMarketAuctionSnapshot(
            trade_date=snapshot.trade_date,
            stock_id=snapshot.stock_id,
            stock_name=snapshot.stock_name,
            subject_key=snapshot.subject_key,
            theme_name=snapshot.theme_name,
            role_label=snapshot.role_label,
            window_start_time=snapshot.window_start_time,
            window_end_time=snapshot.window_end_time,
            last_minute_start_time=snapshot.last_minute_start_time,
            last_30s_start_time=snapshot.last_30s_start_time,
            auction_open_price=snapshot.auction_open_price,
            pre_close=snapshot.pre_close,
            auction_open_pct=snapshot.auction_open_pct,
            auction_volume=snapshot.auction_volume,
            auction_amount=snapshot.auction_amount,
            last_minute_amount=snapshot.last_minute_amount,
            last_minute_ratio=snapshot.last_minute_ratio,
            prev_day_max_intraday_amount=snapshot.prev_day_max_intraday_amount,
            carry_ratio=snapshot.carry_ratio,
            price_path_stability_score=snapshot.price_path_stability_score,
            is_red_zone=snapshot.is_red_zone,
            has_end_spike=snapshot.has_end_spike,
            has_end_drop=snapshot.has_end_drop,
            shape_features=["timeline_enhanced", *snapshot.shape_features],
            source_trace_id=trace_id,
            source_trace={
                "record_mode": "timeline_enhanced",
                "timeline_point_count": len(timeline_points),
                "raw_keys": list(parsed.raw_keys),
                "prev_day_max_intraday_amount_proxy": prev_day_max_intraday_amount_proxy,
                "proxy_method": "subject_stock_daily_snapshot.amount * proxy_ratio",
            },
            source_version="auction_snapshot.v1.timeline",
            rule_version="auction_snapshot.v1.timeline",
        )

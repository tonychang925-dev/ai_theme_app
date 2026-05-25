"""P2-B-0: StockAuctionDTO — extended with rich auction features from PreMarketAuctionSnapshot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class StockAuctionDTO:
    trade_date: date
    stock_id: str

    # ── 基础竞价字段 ──
    auction_open_price: Decimal | None = None
    auction_open_pct: Decimal | None = None
    auction_volume: Decimal | None = None
    auction_amount: Decimal | None = None

    # ── 尾盘竞价 ──
    tail_auction_close_price: Decimal | None = None
    tail_auction_volume: Decimal | None = None
    tail_auction_amount: Decimal | None = None
    tail_auction_vwap: Decimal | None = None

    # ── P2-B-0: rich auction features (from PreMarketAuctionSnapshot) ──
    last_minute_ratio: Decimal | None = None
    carry_ratio: Decimal | None = None
    price_path_stability_score: Decimal | None = None
    has_end_spike: bool = False
    has_end_drop: bool = False
    shape_features: tuple[str, ...] = field(default_factory=tuple)
    source_snapshot_rule_version: str = ""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from stock_service.models import DragonTigerObject


def _to_float(value) -> float:
    if value in (None, "", "null"):
        return 0.0
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def _normalize_trade_date(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


@dataclass(frozen=True)
class DragonTigerListInput:
    trade_date: str
    stock_id: str
    stock_name: str
    reason: str
    close_price: float
    pct_change: float
    turnover_rate: float
    total_amount: float
    billboard_sell_amount: float
    billboard_buy_amount: float
    billboard_amount: float
    net_amount: float
    net_rate: float
    amount_rate: float
    float_market_value: float


@dataclass(frozen=True)
class DragonTigerInstInput:
    trade_date: str
    stock_id: str
    reason: str
    seat_name: str
    side: str
    buy_amount: float
    sell_amount: float
    net_buy: float


class DragonTigerObjectService:
    def _source_trace_id(self, trade_date: str, stock_id: str, reason: str) -> str:
        raw = f"{trade_date}|{stock_id}|{reason}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:16]

    def normalize_top_list(self, records: Iterable[dict]) -> list[DragonTigerListInput]:
        result: list[DragonTigerListInput] = []
        for row in records:
            stock_id = str(row.get("ts_code") or "").strip().upper()
            reason = str(row.get("reason") or "").strip()
            if not stock_id or not reason:
                continue
            result.append(
                DragonTigerListInput(
                    trade_date=_normalize_trade_date(row.get("trade_date")),
                    stock_id=stock_id,
                    stock_name=str(row.get("name") or stock_id),
                    reason=reason,
                    close_price=_to_float(row.get("close")),
                    pct_change=_to_float(row.get("pct_change")),
                    turnover_rate=_to_float(row.get("turnover_rate")),
                    total_amount=_to_float(row.get("amount")),
                    billboard_sell_amount=_to_float(row.get("l_sell")),
                    billboard_buy_amount=_to_float(row.get("l_buy")),
                    billboard_amount=_to_float(row.get("l_amount")),
                    net_amount=_to_float(row.get("net_amount")),
                    net_rate=_to_float(row.get("net_rate")),
                    amount_rate=_to_float(row.get("amount_rate")),
                    float_market_value=_to_float(row.get("float_values")),
                )
            )
        return result

    def normalize_top_inst(self, records: Iterable[dict]) -> list[DragonTigerInstInput]:
        result: list[DragonTigerInstInput] = []
        for row in records:
            stock_id = str(row.get("ts_code") or "").strip().upper()
            reason = str(row.get("reason") or "").strip()
            if not stock_id or not reason:
                continue
            result.append(
                DragonTigerInstInput(
                    trade_date=_normalize_trade_date(row.get("trade_date")),
                    stock_id=stock_id,
                    reason=reason,
                    seat_name=str(row.get("exalter") or "").strip(),
                    side=str(row.get("side") or "").strip(),
                    buy_amount=_to_float(row.get("buy")),
                    sell_amount=_to_float(row.get("sell")),
                    net_buy=_to_float(row.get("net_buy")),
                )
            )
        return result

    def build_objects(
        self,
        top_list_rows: Iterable[DragonTigerListInput],
        top_inst_rows: Iterable[DragonTigerInstInput],
    ) -> list[DragonTigerObject]:
        inst_map: dict[tuple[str, str, str], list[DragonTigerInstInput]] = {}
        for row in top_inst_rows:
            key = (row.trade_date, row.stock_id, row.reason)
            inst_map.setdefault(key, []).append(row)

        result: list[DragonTigerObject] = []
        for row in top_list_rows:
            key = (row.trade_date, row.stock_id, row.reason)
            seats = inst_map.get(key, [])
            seats_sorted = sorted(seats, key=lambda item: abs(item.net_buy), reverse=True)
            seat_summary: list[dict[str, object]] = []
            for seat in seats_sorted[:3]:
                direction = "买入席位" if str(seat.side) == "0" else "卖出席位"
                seat_summary.append(
                    {
                        "seat_name": seat.seat_name or "未知席位",
                        "side": str(seat.side or ""),
                        "side_label": direction,
                        "buy_amount": round(float(seat.buy_amount or 0.0), 2),
                        "sell_amount": round(float(seat.sell_amount or 0.0), 2),
                        "net_buy": round(float(seat.net_buy or 0.0), 2),
                    }
                )

            object_item = DragonTigerObject(
                trade_date=row.trade_date,
                stock_id=row.stock_id,
                stock_name=row.stock_name,
                reason=row.reason,
                close_price=row.close_price,
                pct_change=row.pct_change,
                turnover_rate=row.turnover_rate,
                total_amount=row.total_amount,
                billboard_buy_amount=row.billboard_buy_amount,
                billboard_sell_amount=row.billboard_sell_amount,
                billboard_amount=row.billboard_amount,
                net_amount=row.net_amount,
                net_rate=row.net_rate,
                amount_rate=row.amount_rate,
                float_market_value=row.float_market_value,
                institution_buy_amount=round(sum(item.buy_amount for item in seats), 2),
                institution_sell_amount=round(sum(item.sell_amount for item in seats), 2),
                institution_net_buy=round(sum(item.net_buy for item in seats), 2),
                institution_seat_count=len(seats),
                seat_summary=seat_summary,
                source_trace_id=self._source_trace_id(row.trade_date, row.stock_id, row.reason),
                source_trace={
                    "datasets": ["tushare.dragon_tiger_top_list", "tushare.dragon_tiger_top_inst"],
                    "trade_date": row.trade_date,
                    "stock_id": row.stock_id,
                    "reason": row.reason,
                    "top_inst_row_count": len(seats),
                },
            )
            result.append(object_item)
        return result

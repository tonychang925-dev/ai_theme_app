from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from stock_service.models import HotMoneySeatMaster, HotMoneyTradingActivity


@dataclass(frozen=True)
class HotMoneySeatRule:
    pattern: str
    seat_alias: str
    hot_money_name: str
    style_tags: list[str]
    confidence: float = 0.8


HOT_MONEY_SEAT_RULES: list[HotMoneySeatRule] = [
    HotMoneySeatRule("深圳益田路荣超商务中心", "荣超商务中心", "赵老哥", ["接力", "高标", "主线"]),
    HotMoneySeatRule("佛山季华六路", "季华六路", "佛山系", ["打板", "接力"]),
    HotMoneySeatRule("上海茅台路", "茅台路", "作手新一", ["趋势", "主线"]),
    HotMoneySeatRule("成都北一环路", "北一环路", "成都系", ["接力", "卡位"]),
    HotMoneySeatRule("上海浦东新区银城中路", "银城中路", "方新侠", ["主线", "容量"]),
    HotMoneySeatRule("上海分公司", "上海分公司", "章盟主系", ["趋势", "主线"]),
    HotMoneySeatRule("杭州五星路", "五星路", "孙哥", ["接力", "龙头"]),
    HotMoneySeatRule("湖里大道", "湖里大道", "厦门湖里大道", ["低位挖掘", "套利"]),
    HotMoneySeatRule("溧阳路", "溧阳路", "养家系", ["情绪", "接力"]),
    HotMoneySeatRule("劳动路", "劳动路", "小鳄鱼系", ["高标", "接力"]),
]


class HotMoneyActivityService:
    def match_seat(self, seat_name: str) -> HotMoneySeatMaster | None:
        raw = str(seat_name or "").strip()
        if not raw:
            return None
        for rule in HOT_MONEY_SEAT_RULES:
            if rule.pattern in raw:
                return HotMoneySeatMaster(
                    seat_name=raw,
                    seat_alias=rule.seat_alias,
                    hot_money_name=rule.hot_money_name,
                    style_tags=list(rule.style_tags),
                    confidence=rule.confidence,
                    is_active=True,
                )
        return None

    def build_seat_masters(self, top_inst_records: Iterable[dict]) -> list[HotMoneySeatMaster]:
        result: dict[str, HotMoneySeatMaster] = {}
        for row in top_inst_records:
            seat = self.match_seat(str(row.get("exalter") or ""))
            if seat is None:
                continue
            result.setdefault(seat.seat_name, seat)
        return list(result.values())

    def build_activities(
        self,
        *,
        trade_date: str,
        top_inst_records: Iterable[dict],
        top_list_records: Iterable[dict],
        subject_links: Iterable[dict],
    ) -> list[HotMoneyTradingActivity]:
        top_list_map: dict[tuple[str, str], dict] = {}
        for row in top_list_records:
            stock_id = str(row.get("ts_code") or "").strip().upper()
            reason = str(row.get("reason") or "").strip()
            if stock_id and reason:
                top_list_map[(stock_id, reason)] = row

        links_map: dict[str, list[dict]] = {}
        for row in subject_links:
            stock_id = str(row.get("stock_id") or "").split(".")[0]
            if stock_id:
                links_map.setdefault(stock_id, []).append(row)

        result: list[HotMoneyTradingActivity] = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in top_inst_records:
            seat = self.match_seat(str(row.get("exalter") or ""))
            if seat is None:
                continue
            ts_code = str(row.get("ts_code") or "").strip().upper()
            stock_key = ts_code.split(".")[0]
            reason = str(row.get("reason") or "").strip()
            top_row = top_list_map.get((ts_code, reason), {})
            stock_name = str(top_row.get("name") or ts_code)
            links = links_map.get(stock_key, [])
            if not links:
                continue
            side = "买入" if str(row.get("side") or "") == "0" else "卖出"
            for link in links:
                unique_key = (seat.hot_money_name, stock_key, str(link.get("subject_key") or ""), side)
                if unique_key in seen:
                    continue
                seen.add(unique_key)
                result.append(
                    HotMoneyTradingActivity(
                        trade_date=trade_date,
                        hot_money_name=seat.hot_money_name,
                        seat_name=seat.seat_name,
                        stock_id=stock_key,
                        stock_name=stock_name,
                        subject_key=str(link.get("subject_key") or ""),
                        theme_name=str(link.get("theme_name") or link.get("subject_key") or ""),
                        side=side,
                        buy_amount=float(row.get("buy") or 0.0),
                        sell_amount=float(row.get("sell") or 0.0),
                        net_amount=float(row.get("net_buy") or 0.0),
                        reason=reason,
                        rank_order=int(link.get("rank_order") or 0),
                        is_theme_leader=bool(link.get("is_leader")),
                        style_tags=list(seat.style_tags),
                    )
                )
        return result

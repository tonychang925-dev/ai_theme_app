from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable


@dataclass(frozen=True)
class SourceFieldRule:
    field_name: str
    owner: str
    domain: str
    description: str


class SourceOwnershipRegistry:
    """
    冻结 P3.phase1 首批双源字段所有权。

    规则非常保守：
    - Tushare 负责股票事实、交易日历、证券主数据
    - JYHF 负责题材事件、题材池和题材上下文
    """

    def __init__(self, rules: Iterable[SourceFieldRule]):
        self._rules: Dict[str, SourceFieldRule] = {rule.field_name: rule for rule in rules}

    def get_rule(self, field_name: str) -> SourceFieldRule:
        try:
            return self._rules[field_name]
        except KeyError as exc:
            raise KeyError(f"unknown source ownership field: {field_name}") from exc

    def owner_of(self, field_name: str) -> str:
        return self.get_rule(field_name).owner

    def validate_owner(self, field_name: str, source_name: str) -> None:
        expected = self.owner_of(field_name)
        if expected != source_name:
            raise ValueError(
                f"source ownership conflict for {field_name}: expected {expected}, got {source_name}"
            )

    def validate_payload(self, field_names: Iterable[str], source_name: str) -> None:
        for field_name in field_names:
            self.validate_owner(field_name, source_name)

    def as_dict(self) -> Dict[str, dict]:
        return {
            field_name: {
                "owner": rule.owner,
                "domain": rule.domain,
                "description": rule.description,
            }
            for field_name, rule in sorted(self._rules.items())
        }


DEFAULT_SOURCE_OWNERSHIP = SourceOwnershipRegistry(
    [
        SourceFieldRule("trade_date", "tushare", "stock_fact", "股票交易日事实口径"),
        SourceFieldRule("stock_id", "tushare", "stock_fact", "股票主标识"),
        SourceFieldRule("stock_name", "tushare", "stock_fact", "股票名称"),
        SourceFieldRule("open_price", "tushare", "stock_fact", "开盘价"),
        SourceFieldRule("high_price", "tushare", "stock_fact", "最高价"),
        SourceFieldRule("low_price", "tushare", "stock_fact", "最低价"),
        SourceFieldRule("close_price", "tushare", "stock_fact", "收盘价"),
        SourceFieldRule("pre_close", "tushare", "stock_fact", "昨收价"),
        SourceFieldRule("pct_chg", "tushare", "stock_fact", "涨跌幅"),
        SourceFieldRule("amount", "tushare", "stock_fact", "成交额"),
        SourceFieldRule("volume", "tushare", "stock_fact", "成交量"),
        SourceFieldRule("auction_open_price", "tushare", "auction_fact", "9:25 竞价价格"),
        SourceFieldRule("auction_open_pct", "tushare", "auction_fact", "9:25 相对昨收涨跌幅"),
        SourceFieldRule("auction_volume", "tushare", "auction_fact", "9:25 竞价成交量"),
        SourceFieldRule("auction_amount", "tushare", "auction_fact", "9:25 竞价成交额"),
        SourceFieldRule("tail_auction_close_price", "tushare", "auction_fact", "15:00 收盘竞价价格"),
        SourceFieldRule("tail_auction_volume", "tushare", "auction_fact", "15:00 收盘竞价成交量"),
        SourceFieldRule("tail_auction_amount", "tushare", "auction_fact", "15:00 收盘竞价成交额"),
        SourceFieldRule("tail_auction_vwap", "tushare", "auction_fact", "15:00 收盘竞价均价"),
        SourceFieldRule("limit_up_price", "tushare", "stock_fact", "涨停价"),
        SourceFieldRule("limit_down_price", "tushare", "stock_fact", "跌停价"),
        SourceFieldRule("dragon_tiger_reason", "tushare", "dragon_tiger", "龙虎榜上榜原因"),
        SourceFieldRule("dragon_tiger_buy_amount", "tushare", "dragon_tiger", "龙虎榜买入额"),
        SourceFieldRule("dragon_tiger_sell_amount", "tushare", "dragon_tiger", "龙虎榜卖出额"),
        SourceFieldRule("dragon_tiger_net_amount", "tushare", "dragon_tiger", "龙虎榜净买入额"),
        SourceFieldRule("dragon_tiger_amount_rate", "tushare", "dragon_tiger", "龙虎榜成交额占比"),
        SourceFieldRule("dragon_tiger_net_rate", "tushare", "dragon_tiger", "龙虎榜净买额占比"),
        SourceFieldRule("dragon_tiger_turnover_rate", "tushare", "dragon_tiger", "龙虎榜对应换手率"),
        SourceFieldRule("dragon_tiger_seat_name", "tushare", "dragon_tiger", "龙虎榜席位名称"),
        SourceFieldRule("dragon_tiger_seat_side", "tushare", "dragon_tiger", "龙虎榜席位买卖方向"),
        SourceFieldRule("dragon_tiger_seat_net_buy", "tushare", "dragon_tiger", "龙虎榜席位净买额"),
        SourceFieldRule("calendar_is_open", "tushare", "calendar", "交易日历口径"),
        SourceFieldRule("subject_key", "jyhf", "theme_context", "题材标识"),
        SourceFieldRule("subject_name", "jyhf", "theme_context", "题材名称"),
        SourceFieldRule("theme_event_summary", "jyhf", "theme_event", "题材事件摘要"),
        SourceFieldRule("theme_event_occurred_at", "jyhf", "theme_event", "题材事件发生时间"),
        SourceFieldRule("theme_stock_pool", "jyhf", "theme_context", "题材股票池"),
        SourceFieldRule("theme_stock_rank", "jyhf", "theme_context", "题材股票池排序"),
        SourceFieldRule("theme_context_tags", "jyhf", "theme_context", "题材上下文标签"),
    ]
)

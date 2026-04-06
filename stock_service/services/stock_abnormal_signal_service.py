from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stock_service.models import StockAbnormalSignal, StockDailySnapshot


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _to_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _canonical_stock_id(value: str) -> str:
    raw = str(value or "").strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw


@dataclass(frozen=True)
class StockAbnormalInput:
    trade_date: str
    subject_key: str
    theme_name: str
    stock_id: str
    stock_name: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    pre_close: float
    pct_chg: float
    volume: float
    amount: float
    volume_ratio: float
    turnover_rate: float
    main_net_inflow: float = 0.0
    rank_order: int = 0
    turnover_rank_in_theme: int = 0
    main_net_inflow_rank_in_theme: int = 0
    hot_money_buy_names: tuple[str, ...] = ()
    institution_net_buy: float = 0.0
    institution_seat_count: int = 0
    tail_auction_amount: float = 0.0
    tail_auction_volume: float = 0.0
    tail_auction_vwap: float = 0.0


class StockAbnormalSignalService:
    def load_stock_bars(self, path: Path) -> list[StockDailySnapshot]:
        rows: list[StockDailySnapshot] = []
        with Path(path).open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(StockDailySnapshot(**payload))
        return rows

    def build_signal(self, current: StockAbnormalInput, rows: list[StockDailySnapshot]) -> StockAbnormalSignal | None:
        rows = sorted([row for row in rows if row.trade_date <= current.trade_date], key=lambda item: item.trade_date)
        if not rows:
            return None
        if _canonical_stock_id(rows[-1].stock_id) != _canonical_stock_id(current.stock_id) or rows[-1].trade_date != current.trade_date:
            rows.append(
                StockDailySnapshot(
                    trade_date=current.trade_date,
                    stock_id=current.stock_id,
                    stock_name=current.stock_name,
                    open_price=current.open_price,
                    high_price=current.high_price,
                    low_price=current.low_price,
                    close_price=current.close_price,
                    pre_close=current.pre_close,
                    pct_chg=current.pct_chg,
                    volume=current.volume,
                    amount=current.amount,
                    source_name="jyhf",
                )
            )
            rows = sorted(rows, key=lambda item: item.trade_date)

        if len(rows) < 20:
            return None

        current_row = rows[-1]
        volumes = [float(item.volume or 0.0) for item in rows if item.volume is not None]
        amounts = [float(item.amount or 0.0) for item in rows if item.amount is not None]
        closes = [float(item.close_price or 0.0) for item in rows if item.close_price is not None]
        if not volumes or not amounts or not closes:
            return None

        volume_ma50 = _avg(volumes[-50:]) if len(volumes) >= 50 else _avg(volumes)
        amount_ma20 = _avg(amounts[-20:]) if len(amounts) >= 20 else _avg(amounts)
        current_volume = _to_float(current_row.volume)
        current_amount = _to_float(current_row.amount)
        close_price = _to_float(current_row.close_price)
        high_price = _to_float(current_row.high_price)
        low_price = _to_float(current_row.low_price)
        pct_chg = _to_float(current.pct_chg or current_row.pct_chg)
        tail_auction_amount = _to_float(current.tail_auction_amount)
        tail_auction_vwap = _to_float(current.tail_auction_vwap)

        turnover_score = 0.0
        is_high_turnover = current.turnover_rate >= 15.0
        is_extreme_turnover = current.turnover_rate >= 25.0
        if is_extreme_turnover:
            turnover_score = 100.0
        elif is_high_turnover:
            turnover_score = 75.0
        elif current.turnover_rate >= 8.0:
            turnover_score = 45.0
        else:
            turnover_score = 15.0
        if current.turnover_rank_in_theme and current.turnover_rank_in_theme <= 3:
            turnover_score = min(turnover_score + 10.0, 100.0)

        capital_score = 10.0
        if current.main_net_inflow > 0 and current.main_net_inflow_rank_in_theme == 1:
            capital_score = 100.0
        elif current.main_net_inflow > 0 and current.main_net_inflow_rank_in_theme and current.main_net_inflow_rank_in_theme <= 3:
            capital_score = 75.0
        elif current.main_net_inflow > 0:
            capital_score = 45.0
        if current.hot_money_buy_names:
            capital_score = min(capital_score + 20.0, 100.0)
        if current.institution_net_buy > 0 and current.institution_seat_count > 0:
            capital_score = min(capital_score + 15.0, 100.0)

        volume_ratio_to_ma50 = current_volume / volume_ma50 if volume_ma50 else 0.0
        is_double_volume = volume_ratio_to_ma50 >= 2.0
        is_volume_breakout = volume_ratio_to_ma50 >= 1.5
        is_high_volume_bar = volume_ratio_to_ma50 >= 1.8
        volume_score = 0.0
        if is_double_volume:
            volume_score = 100.0
        elif is_volume_breakout:
            volume_score = 70.0
        elif volume_ratio_to_ma50 >= 1.2:
            volume_score = 40.0
        else:
            volume_score = 10.0

        close_near_high = close_price > 0 and high_price > 0 and (high_price - close_price) / close_price <= 0.01
        range_strength = (close_price - low_price) / max(high_price - low_price, 1e-6) if high_price > low_price else 0.0
        tail_amount_ratio = tail_auction_amount / current_amount if current_amount > 0 else 0.0
        has_tail_auction_push = (
            tail_auction_amount > 0
            and tail_amount_ratio >= 0.05
            and close_near_high
            and pct_chg >= 2.0
        )
        has_tail_rush_buy = has_tail_auction_push or (
            close_near_high
            and pct_chg >= 5.0
            and current_amount >= amount_ma20 * 1.3
        )
        tail_score = 0.0
        if has_tail_auction_push:
            tail_score = 85.0
        elif has_tail_rush_buy:
            tail_score = 75.0
        elif close_near_high and pct_chg >= 2.0 and current_amount >= amount_ma20:
            tail_score = 40.0
        else:
            tail_score = 10.0

        abnormal_labels: list[str] = []
        if is_extreme_turnover:
            abnormal_labels.append("极高换手")
        elif is_high_turnover:
            abnormal_labels.append("高换手")
        if is_double_volume:
            abnormal_labels.append("倍量")
        elif is_volume_breakout:
            abnormal_labels.append("放量")
        if has_tail_auction_push:
            abnormal_labels.append("尾盘竞价抢筹")
        elif has_tail_rush_buy:
            abnormal_labels.append("尾盘抢筹(日频代理)")
        if current.main_net_inflow > 0 and current.main_net_inflow_rank_in_theme and current.main_net_inflow_rank_in_theme <= 3:
            abnormal_labels.append("主力净流入前排")
        if current.hot_money_buy_names:
            abnormal_labels.append("游资买入")
        if current.institution_net_buy > 0 and current.institution_seat_count > 0:
            abnormal_labels.append("机构净买")

        abnormal_composite_score = round(
            turnover_score * 0.30 + volume_score * 0.30 + tail_score * 0.20 + capital_score * 0.20,
            2,
        )
        conclusion = "；".join(abnormal_labels) if abnormal_labels else "无显著异动"
        evidence = [
            f"换手率 {current.turnover_rate:.2f}%",
            f"题材内换手排名 {current.turnover_rank_in_theme or '--'}",
            f"主力净流入 {_to_float(current.main_net_inflow) / 1e8:.2f}亿",
            f"主力题材内净流入排名 {current.main_net_inflow_rank_in_theme or '--'}",
            f"成交量/50日均量 {volume_ratio_to_ma50:.2f}",
            f"量比 {current.volume_ratio:.2f}",
            f"收盘接近高点 {'是' if close_near_high else '否'}",
            f"尾盘竞价成交额 {tail_auction_amount / 1e8:.2f}亿",
            f"尾盘竞价占全天成交额 {tail_amount_ratio:.2%}",
            f"尾盘信号 {'竞价抢筹' if has_tail_auction_push else ('日频代理强' if has_tail_rush_buy else '一般')}",
        ]
        if tail_auction_vwap > 0:
            evidence.append(f"尾盘竞价均价 {tail_auction_vwap:.2f}")
        if current.hot_money_buy_names:
            evidence.append(f"游资买入 {'/'.join(current.hot_money_buy_names[:3])}")
        if current.institution_net_buy > 0 and current.institution_seat_count > 0:
            evidence.append(
                f"机构净买 {current.institution_net_buy / 1e8:.2f}亿 / {current.institution_seat_count}席"
            )
        return StockAbnormalSignal(
            trade_date=current.trade_date,
            stock_id=current.stock_id,
            stock_name=current.stock_name,
            subject_key=current.subject_key,
            theme_name=current.theme_name,
            turnover_rate=current.turnover_rate,
            turnover_rank_in_theme=current.turnover_rank_in_theme,
            main_net_inflow=current.main_net_inflow,
            main_net_inflow_rank_in_theme=current.main_net_inflow_rank_in_theme,
            turnover_abnormal_score=round(turnover_score, 2),
            capital_focus_score=round(capital_score, 2),
            is_high_turnover=is_high_turnover,
            is_extreme_turnover=is_extreme_turnover,
            volume_ratio_to_ma50=round(volume_ratio_to_ma50, 4),
            volume_abnormal_score=round(volume_score, 2),
            is_volume_breakout=is_volume_breakout,
            is_double_volume=is_double_volume,
            is_high_volume_bar=is_high_volume_bar,
            tail_amount=round(tail_auction_amount, 2),
            tail_amount_ratio=round(tail_amount_ratio, 4),
            tail_unmatched_buy_order=0.0,
            tail_abnormal_score=round(tail_score, 2),
            has_tail_rush_buy=has_tail_rush_buy,
            has_tail_large_unmatched_bid=False,
            hot_money_buy_names=list(current.hot_money_buy_names),
            institution_net_buy=current.institution_net_buy,
            institution_seat_count=current.institution_seat_count,
            has_hot_money_buy=bool(current.hot_money_buy_names),
            has_institution_buy=bool(current.institution_net_buy > 0 and current.institution_seat_count > 0),
            abnormal_labels=abnormal_labels,
            abnormal_composite_score=abnormal_composite_score,
            conclusion=conclusion,
            evidence=evidence,
            source_trace={
                "bar_count": len(rows),
                "amount_ma20": round(amount_ma20, 2),
                "volume_ma50": round(volume_ma50, 2),
                "close_near_high": close_near_high,
                "range_strength": round(range_strength, 4),
                "tail_auction_push": has_tail_auction_push,
            },
            source_version="stock_abnormal_signal.v1.auction_c_mixed" if tail_auction_amount > 0 else "stock_abnormal_signal.v1.daily_proxy",
            rule_version="stock_abnormal_signal.v1.auction_c_mixed" if tail_auction_amount > 0 else "stock_abnormal_signal.v1.daily_proxy",
        )

    @staticmethod
    def to_payload(item):
        return asdict(item)

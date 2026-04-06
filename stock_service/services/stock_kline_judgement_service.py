from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from stock_service.models import StockDailySnapshot, StockPatternJudgement, StockPositionJudgement


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class StockKlineJudgementService:
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

    def build_position_judgement(self, rows: list[StockDailySnapshot]) -> StockPositionJudgement | None:
        if len(rows) < 20:
            return None
        rows = sorted(rows, key=lambda item: item.trade_date)
        current = rows[-1]
        closes = [float(item.close_price or 0.0) for item in rows if item.close_price is not None]
        if not closes or not current.close_price:
            return None

        close_now = float(current.close_price)
        high_20 = max(closes[-20:])
        high_60 = max(closes[-60:]) if len(closes) >= 60 else max(closes)
        high_120 = max(closes[-120:]) if len(closes) >= 120 else max(closes)
        high_all = max(closes)

        ma5 = _avg(closes[-5:])
        ma10 = _avg(closes[-10:])
        ma20 = _avg(closes[-20:])

        d20 = close_now / high_20 - 1.0 if high_20 else 0.0
        d60 = close_now / high_60 - 1.0 if high_60 else 0.0
        d120 = close_now / high_120 - 1.0 if high_120 else 0.0
        dall = close_now / high_all - 1.0 if high_all else 0.0

        ma_alignment = "均线走弱"
        trend_score = 35.0
        if ma5 >= ma10 >= ma20:
            ma_alignment = "均线多头"
            trend_score = 75.0
        elif ma5 >= ma10:
            ma_alignment = "短线转强"
            trend_score = 58.0

        if d60 >= 0:
            position_label = "突破前高"
        elif d60 >= -0.03:
            position_label = "接近前高"
        elif d120 <= -0.25 and ma5 >= ma10:
            position_label = "低位启动"
        elif dall >= -0.08:
            position_label = "高位分歧"
        else:
            position_label = "平台整理"

        evidence = [
            f"距20日高点 {d20 * 100:.2f}%",
            f"距60日高点 {d60 * 100:.2f}%",
            f"MA结构 {ma_alignment}",
        ]
        conclusion = f"{position_label}；{ma_alignment}"
        return StockPositionJudgement(
            trade_date=current.trade_date,
            stock_id=current.stock_id,
            stock_name=current.stock_name or current.stock_id,
            position_label=position_label,
            distance_to_20d_high=d20,
            distance_to_60d_high=d60,
            distance_to_120d_high=d120,
            distance_to_all_time_high=dall,
            ma_alignment_status=ma_alignment,
            trend_strength_score=trend_score,
            conclusion=conclusion,
            evidence=evidence,
            source_trace={"bar_count": len(rows)},
        )

    def build_pattern_judgement(self, rows: list[StockDailySnapshot]) -> StockPatternJudgement | None:
        if len(rows) < 20:
            return None
        rows = sorted(rows, key=lambda item: item.trade_date)
        current = rows[-1]
        closes = [float(item.close_price or 0.0) for item in rows if item.close_price is not None]
        volumes = [float(item.volume or 0.0) for item in rows if item.volume is not None]
        if not closes or not volumes or not current.close_price:
            return None

        labels: list[str] = []
        vol_ma10 = _avg(volumes[-10:]) if len(volumes) >= 10 else _avg(volumes)
        close_now = float(current.close_price)
        high_20 = max(closes[-20:])
        ma5 = _avg(closes[-5:])
        ma10 = _avg(closes[-10:])
        ma20 = _avg(closes[-20:])

        breakout_status = "未突破"
        if high_20 and close_now >= high_20 and float(current.volume or 0.0) > vol_ma10 * 1.5:
            labels.append("放量突破")
            breakout_status = "放量突破"

        if ma5 >= ma10 >= ma20:
            labels.append("均线多头")

        pullback_status = "无明显回踩"
        if len(closes) >= 5 and close_now >= ma10 and float(current.volume or 0.0) < vol_ma10:
            labels.append("缩量回踩")
            pullback_status = "缩量回踩"

        risk_pattern_status = "正常"
        if close_now / max(closes) - 1.0 >= -0.05 and float(current.volume or 0.0) > vol_ma10 * 1.8 and close_now < float(current.high_price or close_now):
            risk_pattern_status = "高位分歧"

        if len(rows) >= 6:
            anchor = rows[-6]
            if anchor.volume and current.low_price is not None and anchor.low_price is not None:
                if float(anchor.volume) > vol_ma10 * 1.5 and float(current.low_price) >= float(anchor.low_price):
                    labels.append("高量不破")

        volume_pattern_status = "量能一般"
        if "放量突破" in labels:
            volume_pattern_status = "放量上涨"
        elif "缩量回踩" in labels:
            volume_pattern_status = "缩量整理"

        conclusion = "；".join(labels) if labels else "无显著强势形态"
        evidence = [
            f"近20日高点 {high_20:.2f}",
            f"当前量能/10日均量 {(float(current.volume or 0.0) / vol_ma10) if vol_ma10 else 0.0:.2f}",
        ]
        return StockPatternJudgement(
            trade_date=current.trade_date,
            stock_id=current.stock_id,
            stock_name=current.stock_name or current.stock_id,
            pattern_labels=labels,
            volume_pattern_status=volume_pattern_status,
            breakout_status=breakout_status,
            pullback_status=pullback_status,
            risk_pattern_status=risk_pattern_status,
            conclusion=conclusion,
            evidence=evidence,
            source_trace={"bar_count": len(rows)},
        )

    @staticmethod
    def to_payload(item):
        return asdict(item)

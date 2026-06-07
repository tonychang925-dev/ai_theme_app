from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from stock_processing_service.domain.services.market_regime.kline_technical_analyzer import (
    KlineTechnicalAnalyzer,
)


class GoldenSpiderPatternService:
    """Detect explicit golden-spider-style K-line quality for OneToTwo.

    It reuses the existing k-line technical analysis kernel plus the
    stock_position_judgement / stock_pattern_judgement read-models.
    The detector is explainable and returns unknown when bars are
    insufficient rather than fabricating a positive signal.
    """

    DIRECT_LABELS = {"金蜘蛛", "golden_spider", "golden spider", "golden_spider_pattern"}

    def __init__(self, read_port: Any) -> None:
        self._read = read_port
        self._analyzer = KlineTechnicalAnalyzer()

    async def build(
        self,
        *,
        trade_date: date,
        stock_ids: list[str],
        stock_bars_by_stock: dict[str, list[dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        stock_ids = [str(stock_id).strip() for stock_id in dict.fromkeys(stock_ids or []) if str(stock_id).strip()]
        if not stock_ids:
            return {}

        position_rows = await self._safe_get_stock_position_judgement(trade_date, stock_ids)
        pattern_rows = await self._safe_get_stock_pattern_judgement(trade_date, stock_ids)
        position_by_stock = {self._normalize_stock_id(row.get("stock_id")): dict(row) for row in position_rows}
        pattern_by_stock = {self._normalize_stock_id(row.get("stock_id")): dict(row) for row in pattern_rows}

        result: dict[str, dict[str, Any]] = {}
        for stock_id in stock_ids:
            normalized_stock_id = self._normalize_stock_id(stock_id)
            bars = sorted(
                [dict(row or {}) for row in (stock_bars_by_stock.get(stock_id) or stock_bars_by_stock.get(normalized_stock_id) or [])],
                key=lambda row: self._date_key(row.get("trade_date")),
            )
            if not bars:
                result[stock_id] = self._unknown(
                    stock_id,
                    "missing_bars",
                    position_by_stock.get(normalized_stock_id, {}),
                    pattern_by_stock.get(normalized_stock_id, {}),
                )
                continue

            normalized_bars = [
                {
                    "close": row.get("close_price") or row.get("close"),
                    "high": row.get("high_price") or row.get("high"),
                    "low": row.get("low_price") or row.get("low"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                }
                for row in bars
            ]
            analysis = self._analyzer.analyze(normalized_bars)
            position = position_by_stock.get(normalized_stock_id, {})
            pattern = pattern_by_stock.get(normalized_stock_id, {})
            detected = self._detect(stock_id, bars, analysis, position, pattern)
            result[stock_id] = detected

        return result

    async def _safe_get_stock_position_judgement(self, trade_date: date, stock_ids: list[str]) -> list[dict[str, Any]]:
        try:
            rows = await self._read.get_stock_position_judgement(trade_date, stock_ids=stock_ids)
        except Exception:
            return []
        return [dict(row.__dict__) if hasattr(row, "__dict__") else dict(row or {}) for row in rows or []]

    async def _safe_get_stock_pattern_judgement(self, trade_date: date, stock_ids: list[str]) -> list[dict[str, Any]]:
        try:
            rows = await self._read.get_stock_pattern_judgement(trade_date, stock_ids=stock_ids)
        except Exception:
            return []
        return [dict(row.__dict__) if hasattr(row, "__dict__") else dict(row or {}) for row in rows or []]

    def _detect(
        self,
        stock_id: str,
        bars: list[dict[str, Any]],
        analysis: dict[str, Any],
        position: dict[str, Any],
        pattern: dict[str, Any],
    ) -> dict[str, Any]:
        ma = dict(analysis.get("ma") or {})
        support = dict(analysis.get("support_resistance") or {})
        volume = dict(analysis.get("volume") or {})
        trend = dict(analysis.get("trend") or {})
        pattern_labels = self._pattern_labels(pattern.get("pattern_labels"))
        position_label = str(position.get("position_label") or "").strip()
        ma_alignment_status = str(position.get("ma_alignment_status") or ma.get("ma_alignment") or "").strip()
        trend_strength_score = self._float(position.get("trend_strength_score"), trend.get("trend_score") or 0.0)

        ma5 = self._float(ma.get("ma5"))
        ma10 = self._float(ma.get("ma10"))
        ma20 = self._float(ma.get("ma20"))
        latest_close = self._float(
            ma.get("latest_close"),
            self._float(support.get("latest_close"), self._float(bars[-1].get("close_price") or bars[-1].get("close"))),
        )
        spread_ratio = self._cluster_spread_ratio(ma5, ma10, ma20, latest_close)
        volume_ratio = self._float(volume.get("volume_ratio_5d"), 1.0)
        amount_ratio = self._float(volume.get("amount_ratio_5d"), 1.0)
        support_floor = self._support_floor(support, ma)
        support_hold = bool(
            not support.get("support_broken")
            and (
                support.get("near_support")
                or (latest_close is not None and latest_close >= support_floor)
            )
        )

        reasons: list[str] = []
        score = 0.0
        has_golden_spider = False

        if len(bars) < 20 or ma20 is None:
            return self._unknown(stock_id, "insufficient_history", position, pattern, analysis=analysis)

        if pattern_labels and self._has_direct_label(pattern_labels):
            has_golden_spider = True
            reasons.append("pattern_label_hit")
            score += 50.0

        if ma.get("above_ma5") and ma.get("above_ma10") and ma.get("above_ma20"):
            score += 18.0
            reasons.append("price_above_ma_cluster")

        if self._is_bullish_alignment(ma):
            score += 18.0
            reasons.append("ma5_ma10_ma20_bullish_alignment")

        if spread_ratio is not None and spread_ratio <= 0.08:
            score += 15.0
            reasons.append("ma_cluster_converged")
        elif spread_ratio is not None and spread_ratio <= 0.12:
            score += 8.0
            reasons.append("ma_cluster_near_converged")

        if volume_ratio >= 1.2 or amount_ratio >= 1.2:
            score += 10.0
            reasons.append("volume_expanding")
        elif volume_ratio >= 1.05:
            score += 5.0
            reasons.append("volume_stable_with_bias")

        if position_label in {"突破前高", "接近前高", "强势", "平台整理", "均线多头"}:
            score += 10.0
            reasons.append(f"position_label={position_label}")

        if ma_alignment_status in {"均线多头", "bullish", "bullish_trend"}:
            score += 8.0
            reasons.append(f"ma_alignment_status={ma_alignment_status}")

        if trend_strength_score >= 60:
            score += 8.0
            reasons.append("trend_strength_high")
        elif trend_strength_score >= 45:
            score += 4.0
            reasons.append("trend_strength_medium")

        if support_hold:
            score += 5.0
            reasons.append("support_hold")

        if support.get("near_resistance"):
            score -= 6.0
            reasons.append("near_resistance")

        if latest_close and ma5 and latest_close >= ma5 * 1.18:
            score -= 8.0
            reasons.append("price_extended_above_ma5")

        score = max(0.0, min(100.0, score))
        if not has_golden_spider and score >= 68.0 and len(reasons) >= 3:
            has_golden_spider = True

        level = "golden" if has_golden_spider else ("near_golden" if score >= 55 else "unknown")
        if not has_golden_spider and score < 40:
            level = "unknown"

        return {
            "stock_id": stock_id,
            "has_golden_spider": has_golden_spider,
            "level": level,
            "score": round(score, 2),
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "latest_close": latest_close,
            "ma_spread_ratio": round(spread_ratio, 4) if spread_ratio is not None else None,
            "position_label": position_label,
            "ma_alignment_status": ma_alignment_status,
            "trend_strength_score": round(trend_strength_score, 2),
            "pattern_labels": pattern_labels,
            "volume_pattern_status": str(pattern.get("volume_pattern_status") or ""),
            "breakout_status": str(pattern.get("breakout_status") or ""),
            "pullback_status": str(pattern.get("pullback_status") or ""),
            "risk_pattern_status": str(pattern.get("risk_pattern_status") or ""),
            "support_hold": support_hold,
            "pattern_reasons": reasons,
            "analysis": {
                "ma": ma,
                "support_resistance": support,
                "volume": volume,
                "trend": trend,
            },
        }

    def _unknown(
        self,
        stock_id: str,
        reason: str,
        position: dict[str, Any],
        pattern: dict[str, Any],
        *,
        analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ma = dict((analysis or {}).get("ma") or {})
        support = dict((analysis or {}).get("support_resistance") or {})
        volume = dict((analysis or {}).get("volume") or {})
        trend = dict((analysis or {}).get("trend") or {})
        return {
            "stock_id": stock_id,
            "has_golden_spider": False,
            "level": "unknown",
            "score": 0.0,
            "ma5": self._float(ma.get("ma5")),
            "ma10": self._float(ma.get("ma10")),
            "ma20": self._float(ma.get("ma20")),
            "latest_close": self._float(ma.get("latest_close")),
            "ma_spread_ratio": None,
            "position_label": str(position.get("position_label") or "").strip(),
            "ma_alignment_status": str(position.get("ma_alignment_status") or ma.get("ma_alignment") or "").strip(),
            "trend_strength_score": self._float(position.get("trend_strength_score"), 0.0),
            "pattern_labels": self._pattern_labels(pattern.get("pattern_labels")),
            "volume_pattern_status": str(pattern.get("volume_pattern_status") or ""),
            "breakout_status": str(pattern.get("breakout_status") or ""),
            "pullback_status": str(pattern.get("pullback_status") or ""),
            "risk_pattern_status": str(pattern.get("risk_pattern_status") or ""),
            "support_hold": False,
            "pattern_reasons": [reason],
            "analysis": {
                "ma": ma,
                "support_resistance": support,
                "volume": volume,
                "trend": trend,
            },
        }

    @staticmethod
    def _pattern_labels(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return [str(value).strip()] if str(value).strip() else []

    def _has_direct_label(self, labels: list[str]) -> bool:
        return any(label in self.DIRECT_LABELS for label in labels)

    def _is_bullish_alignment(self, ma: dict[str, Any]) -> bool:
        ma5 = self._float(ma.get("ma5"))
        ma10 = self._float(ma.get("ma10"))
        ma20 = self._float(ma.get("ma20"))
        latest = self._float(ma.get("latest_close"))
        if None in {ma5, ma10, ma20, latest}:
            return False
        return latest > ma5 > ma10 > ma20

    @staticmethod
    def _cluster_spread_ratio(ma5: float | None, ma10: float | None, ma20: float | None, latest: float | None) -> float | None:
        values = [v for v in (ma5, ma10, ma20) if v is not None and v > 0]
        if len(values) < 3 or latest is None or latest <= 0:
            return None
        return (max(values) - min(values)) / latest

    @staticmethod
    def _support_floor(support: dict[str, Any], ma: dict[str, Any]) -> float:
        support_level = support.get("support_level") or support.get("nearest_support_level")
        try:
            return float(support_level)
        except Exception:
            ma20 = ma.get("ma20")
            try:
                return float(ma20) * 0.98 if ma20 is not None else 0.0
            except Exception:
                return 0.0

    async def _safe_get_stock_position_judgement(self, trade_date: date, stock_ids: list[str]) -> list[dict[str, Any]]:
        try:
            rows = await self._read.get_stock_position_judgement(trade_date, stock_ids=stock_ids)
        except Exception:
            return []
        return [dict(row.__dict__) if hasattr(row, "__dict__") else dict(row or {}) for row in rows or []]

    async def _safe_get_stock_pattern_judgement(self, trade_date: date, stock_ids: list[str]) -> list[dict[str, Any]]:
        try:
            rows = await self._read.get_stock_pattern_judgement(trade_date, stock_ids=stock_ids)
        except Exception:
            return []
        return [dict(row.__dict__) if hasattr(row, "__dict__") else dict(row or {}) for row in rows or []]

    @staticmethod
    def _normalize_stock_id(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text.split(".")[0]

    @staticmethod
    def _date_key(value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return str(value.isoformat())
        return str(value)

    @staticmethod
    def _float(value: Any, default: float | None = None) -> float | None:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

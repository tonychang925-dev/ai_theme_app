"""P1-J-4/J-2: 弱转强市场环境与题材联动过滤器。

大盘环境 (market_regime):
  strong / neutral / weak / panic
  基于 intraday_index_minute_state

题材联动 (subject_regime):
  hot / neutral / cooling / decline
  基于 jyhf_subject_stock_quote_snapshot

第一版只做 shadow filter，不直接改 v2.2 scorer。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

logger = logging.getLogger("sps.w2s_market_context")

TZ_CN = timezone(timedelta(hours=8))


@dataclass
class MarketContext:
    market_regime: str           # strong / neutral / weak / panic
    market_score: float          # -100 ~ +100
    index_pct_chg: float
    index_30m_trend: float       # 最近30分钟斜率
    market_filter_reason: str

    subject_regime: str          # hot / neutral / cooling / decline
    subject_strength_score: float
    subject_up_ratio: float
    subject_top5_avg_pct: float
    subject_filter_reason: str

    context_confidence: float    # 0.0 ~ 1.0
    context_risk: bool           # true = 高环境风险

    generated_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class W2SMarketContextService:
    """市场环境与题材联动上下文服务。"""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 大盘环境 ──

    async def get_market_regime(self, trade_date: str) -> dict:
        """从指数分钟状态获取大盘环境。"""
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)

        # 最新指数状态
        rows = await pool.fetch(
            """SELECT DISTINCT ON (index_code)
                 index_code, pct_chg, minute_ts
               FROM intraday_index_minute_state
               WHERE trade_date = $1::date
               ORDER BY index_code, minute_ts DESC""",
            td,
        )

        if not rows:
            return {"regime": "neutral", "score": 0, "pct_chg": 0,
                    "trend_30m": 0, "reason": "no_index_data"}

        # 综合判断：取主要指数均值
        pct_values = [float(r["pct_chg"] or 0) for r in rows]
        avg_pct = sum(pct_values) / len(pct_values) if pct_values else 0

        # 30m trend
        trend_rows = await pool.fetch(
            """SELECT pct_chg FROM intraday_index_minute_state
               WHERE trade_date = $1::date
               ORDER BY minute_ts DESC LIMIT 6""",
            td,
        )
        trend_30m = 0.0
        if len(trend_rows) >= 2:
            recent = [float(r["pct_chg"] or 0) for r in trend_rows]
            trend_30m = recent[0] - recent[-1]

        # 判定
        if avg_pct <= -1.0:
            regime, score = "panic", -80
            reason = f"index_pct={avg_pct:.2f}% panic"
        elif avg_pct <= -0.5:
            regime, score = "weak", -40
            reason = f"index_pct={avg_pct:.2f}% weak"
        elif avg_pct >= 0.5:
            regime, score = "strong", 60
            reason = f"index_pct={avg_pct:.2f}% strong"
        else:
            regime, score = "neutral", 0
            reason = f"index_pct={avg_pct:.2f}% neutral"

        # panic 时降级
        if regime == "weak" and trend_30m < -0.3:
            regime, score = "panic", -70
            reason += f" + trend_dn({trend_30m:.2f})"
        if regime == "panic" and trend_30m < -0.5:
            score = -95

        return {
            "regime": regime, "score": score,
            "pct_chg": round(avg_pct, 3),
            "trend_30m": round(trend_30m, 3),
            "reason": reason,
        }

    # ── 题材联动 ──

    async def get_subject_regime(self, trade_date: str, subject_keys: list[str]) -> dict:
        """从题材股票报价获取题材联动强度。"""
        if not subject_keys:
            return {"regime": "neutral", "score": 0, "up_ratio": 0,
                    "top5_avg": 0, "reason": "no_subjects"}

        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        subject_keys_clean = [s for s in subject_keys if s and s.strip()]

        if not subject_keys_clean:
            return {"regime": "neutral", "score": 0, "up_ratio": 0,
                    "top5_avg": 0, "reason": "empty_subjects"}

        rows = await pool.fetch(
            """SELECT subject_id, stock_id, pct_chg
               FROM jyhf_subject_stock_quote_snapshot
               WHERE trade_date = $1::date
                 AND subject_id = ANY($2::text[])""",
            td, subject_keys_clean,
        )

        if not rows:
            return {"regime": "neutral", "score": 0, "up_ratio": 0,
                    "top5_avg": 0, "reason": "no_subject_quote_data"}

        # 统计
        pct_values = [float(r["pct_chg"] or 0) for r in rows]
        total = len(pct_values)
        up_count = sum(1 for v in pct_values if v > 0)
        up_ratio = up_count / total if total > 0 else 0

        # Top5 平均
        top5 = sorted(pct_values, reverse=True)[:5]
        top5_avg = sum(top5) / len(top5) if top5 else 0

        # 判定
        if up_ratio >= 0.6 and top5_avg >= 3.0:
            regime, score = "hot", 70
            reason = f"up_ratio={up_ratio:.0%} top5={top5_avg:.1f}% hot"
        elif up_ratio < 0.4 or top5_avg < 1.0:
            if top5_avg < 0 and up_ratio < 0.3:
                regime, score = "decline", -60
                reason = f"up_ratio={up_ratio:.0%} top5={top5_avg:.1f}% decline"
            else:
                regime, score = "cooling", -20
                reason = f"up_ratio={up_ratio:.0%} top5={top5_avg:.1f}% cooling"
        else:
            regime, score = "neutral", 0
            reason = f"up_ratio={up_ratio:.0%} top5={top5_avg:.1f}% neutral"

        return {
            "regime": regime, "score": score,
            "up_ratio": round(up_ratio, 3),
            "top5_avg": round(top5_avg, 2),
            "total_stocks": total,
            "reason": reason,
        }

    # ── 综合 ──

    async def build_context(self, trade_date: str,
                            subject_keys: list[str] | None = None) -> MarketContext:
        """构建综合市场上下文。"""
        now_str = datetime.now(TZ_CN).isoformat()
        market = await self.get_market_regime(trade_date)
        subject = await self.get_subject_regime(trade_date, subject_keys or [])

        # 综合置信度
        confidence = 1.0
        risk = False

        if market["regime"] == "panic":
            confidence -= 0.4
            risk = True
        elif market["regime"] == "weak":
            confidence -= 0.15

        if subject["regime"] == "decline":
            confidence -= 0.3
            risk = True
        elif subject["regime"] == "cooling":
            confidence -= 0.1

        confidence = round(max(0.1, min(1.0, confidence)), 2)

        return MarketContext(
            market_regime=market["regime"],
            market_score=market["score"],
            index_pct_chg=market["pct_chg"],
            index_30m_trend=market["trend_30m"],
            market_filter_reason=market["reason"],

            subject_regime=subject["regime"],
            subject_strength_score=subject["score"],
            subject_up_ratio=subject.get("up_ratio", 0),
            subject_top5_avg_pct=subject.get("top5_avg", 0),
            subject_filter_reason=subject["reason"],

            context_confidence=confidence,
            context_risk=risk,
            generated_at=now_str,
            extra={"market": market, "subject": subject},
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

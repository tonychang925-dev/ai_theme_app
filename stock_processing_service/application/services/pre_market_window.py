"""统一盘前窗口解析器。

窗口定义：
  start_at = 上一交易日 15:00:00 Asia/Shanghai
  end_at   = trade_date     08:00:00 Asia/Shanghai

查询口径：start_at <= occurred_at < end_at
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreMarketWindow:
    trade_date: date
    prev_trade_date: date
    start_at: datetime
    end_at: datetime
    source: str  # "trade_calendar" | "weekday_fallback"


async def resolve_pre_market_window(
    trade_date: date,
    *,
    gateway: object | None = None,
    now: datetime | None = None,
) -> PreMarketWindow:
    """解析盘前必读统一时间窗口。

    优先从 trade calendar 取上一交易日；无日历或失败时使用工作日 fallback。
    """
    prev_trade_date = await _resolve_prev_trade_date(trade_date, gateway=gateway, now=now)
    source = "trade_calendar" if gateway else "weekday_fallback"

    start_at = datetime.combine(prev_trade_date, time(15, 0), tzinfo=CN_TZ)
    end_at = datetime.combine(trade_date, time(8, 0), tzinfo=CN_TZ)

    return PreMarketWindow(
        trade_date=trade_date,
        prev_trade_date=prev_trade_date,
        start_at=start_at,
        end_at=end_at,
        source=source,
    )


async def _resolve_prev_trade_date(
    trade_date: date,
    *,
    gateway: object | None = None,
    now: datetime | None = None,
) -> date:
    """获取上一交易日。"""
    if gateway is not None:
        fn = getattr(gateway, "get_trade_calendar", None)
        if callable(fn):
            try:
                calendar = await fn(trade_date)
                prev = (calendar or {}).get("prev_trade_date")
                if prev:
                    parsed = _parse_date(prev)
                    if parsed:
                        logger.info(
                            "pre_market_window resolved via trade_calendar: "
                            "trade_date=%s prev_trade_date=%s",
                            trade_date.isoformat(),
                            parsed.isoformat(),
                        )
                        return parsed
            except Exception as exc:
                logger.warning(
                    "pre_market_window trade_calendar lookup failed for %s: %s",
                    trade_date.isoformat(),
                    exc,
                )

    # Fallback: simple weekday rollback
    prev = _weekday_before(trade_date)
    logger.info(
        "pre_market_window fallback to weekday: trade_date=%s prev_trade_date=%s",
        trade_date.isoformat(),
        prev.isoformat(),
    )
    return prev


def _weekday_before(d: date) -> date:
    """Return the nearest weekday before d (Mon-Fri)."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # Saturday=5, Sunday=6
        prev -= timedelta(days=1)
    return prev


def _parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

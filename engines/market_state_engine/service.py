"""P2-1: MarketStateEngine — 行情状态层 facade。

包装现有 IntradayMinuteStateBuilder，不重写逻辑。
等接口稳定后，逐步内聚核心逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from typing import Any

TZ_CN = timezone(timedelta(hours=8))

logger = logging.getLogger("engines.market_state")


@dataclass
class MarketState:
    """单只股票当前状态快照。"""
    stock_code: str = ""
    stock_name: str = ""
    price: float = 0.0
    pct_chg: float = 0.0
    amount: float = 0.0
    volume_ratio: float = 0.0
    above_vwap: bool = False
    vwap: float = 0.0
    relative_strength: float = 0.0
    limit_status: str = ""
    session: str = "intraday"
    minute_ts: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class MarketStateEngine:
    """行情状态引擎 facade。

    第一阶段只做 facade 封装，内部委托给现有的
    IntradayMinuteStateBuilder 和 calc_vwap。
    """

    def __init__(self, dsn: str | None = None):
        self._dsn = dsn

    async def build_minute_bar(
        self, stock_code: str, stock_name: str, base_date: date,
    ) -> MarketState | None:
        """构建单只股票当前分钟状态。

        委托给现有的 IntradayMinuteStateBuilder。
        """
        try:
            from stock_processing_service.domain.services.intraday_minute_state_builder import (
                IntradayMinuteStateBuilder,
            )
            builder = IntradayMinuteStateBuilder(self._dsn)
            bar = await builder.build_single(stock_code, stock_name, base_date)
            if not bar:
                return None

            return MarketState(
                stock_code=bar.stock_code or stock_code,
                stock_name=bar.stock_name or stock_name,
                price=float(bar.close or 0),
                pct_chg=float(getattr(bar, "pct_chg", 0) or 0),
                amount=float(getattr(bar, "amount", 0) or 0),
                volume_ratio=float(getattr(bar, "volume_ratio", 0) or 0),
                above_vwap=bool(getattr(bar, "above_vwap", False)),
                vwap=float(getattr(bar, "vwap", 0) or 0),
                relative_strength=float(getattr(bar, "relative_strength", 0) or 0),
                limit_status=str(getattr(bar, "limit_status", "") or ""),
                session="intraday",
                minute_ts=datetime.now(TZ_CN).isoformat(),
                raw={"source": "IntradayMinuteStateBuilder"},
            )
        except ImportError:
            logger.warning("IntradayMinuteStateBuilder not available")
            return None
        except Exception as exc:
            logger.warning("MarketStateEngine.build_minute_bar failed: %s", exc)
            return None

    async def get_state(self, stock_code: str) -> MarketState | None:
        """查询单只股票当前行情状态。"""
        today = date.today()
        return await self.build_minute_bar(stock_code, "", today)

"""M2.5 — Eastmoney Board Pool Client (a-stock-data 打板层).

Fetches real-time/day-end board data from Eastmoney push2ex API.
Provides: 涨停池, 炸板池, 跌停池, 昨涨停池.

Key fields from API:
  - limit_days: 连板数 (no more streak backtracking!)
  - zt_stat: N天M板 string
  - y_limit_days: yesterday's 连板数 (for 晋级率 JOIN)
  - first_seal, last_seal: seal timing
  - break_times: 炸板次数
  - seal_fund: 封单资金

Source: a-stock-data SKILL.md Layer 8
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
import json


# ── DTOs ──

@dataclass
class LimitUpPoolStock:
    """A stock in today's limit-up pool (涨停池)."""
    code: str
    name: str
    price: float               # current price (元)
    pct: float                 # 涨跌幅%
    limit_days: int            # 连板数 ← KEY FIELD from API
    zt_stat: str = ""          # "3天3板"
    first_seal: str = ""       # "09:35:00"
    last_seal: str = ""        # "14:55:00"
    seal_fund: float = 0.0     # 封板资金(元)
    break_times: int = 0       # 炸板次数
    turnover: float = 0.0      # 换手率%
    amount: float = 0.0        # 成交额(元)
    float_cap: float = 0.0     # 流通市值(元)
    industry: str = ""         # 行业
    board_type: str = ""       # 换手板/一字板/T字板 (from THS)


@dataclass
class FriedBoardPoolStock:
    """A stock in the fried board pool (炸板池)."""
    code: str
    name: str
    price: float
    pct: float
    limit_price: float = 0.0   # 涨停价
    break_times: int = 0
    first_seal: str = ""
    amplitude: float = 0.0     # 振幅%
    turnover: float = 0.0
    industry: str = ""


@dataclass
class LimitDownPoolStock:
    """A stock in the limit-down pool (跌停池)."""
    code: str
    name: str
    price: float
    pct: float
    dt_days: int = 0           # 连续跌停天数
    seal_fund: float = 0.0
    turnover: float = 0.0
    open_times: int = 0        # 开板次数
    industry: str = ""


@dataclass
class YesterdayLimitUpPoolStock:
    """A stock from yesterday's limit-up pool, tracking today's performance.

    KEY for relay ecology — enables precise 晋级率 calculation
    without streak backtracking.
    """
    code: str
    name: str
    today_pct: float           # today's change%
    y_limit_days: int          # yesterday's 连板数
    y_first_seal: str = ""     # yesterday's seal time
    today_turnover: float = 0.0
    industry: str = ""


@dataclass
class BoardSentiment:
    """Aggregate board sentiment metrics."""
    trade_date: date
    zt_count: int = 0          # 涨停数
    zb_count: int = 0          # 炸板数
    dt_count: int = 0          # 跌停数
    break_rate: float = 0.0    # 炸板率%
    max_height: int = 0        # 最高连板
    ladder: dict[int, int] = field(default_factory=dict)  # {板数: 股票数}


# ── Eastmoney Board Client ──

EM_BASE = "https://push2ex.eastmoney.com"
EM_UT = "7eea3edcaed734bea9cbfc24409ed989"


class EastmoneyBoardClient:
    """Eastmoney push2ex board pool API client.

    Four endpoints:
      - getTopicZTPool:      涨停池 (today's limit-up)
      - getTopicZBPool:      炸板池 (fried boards)
      - getTopicDTPool:      跌停池 (limit-down)
      - getYesterdayZTPool:  昨涨停池 (yesterday's limit-up, today's performance)
    """

    def __init__(self, http_client=None):
        import httpx
        self._http = http_client or httpx.AsyncClient(timeout=15.0)

    async def fetch_zt_pool(self, trade_date: date) -> list[LimitUpPoolStock]:
        """Fetch today's limit-up pool (涨停池)."""
        params = {
            "ut": EM_UT, "dpt": "wz.ztzt", "sort": "fbt:asc",
            "date": trade_date.strftime("%Y%m%d"),
            "pageindex": 0, "pagesize": 300,
            "fields": "f12,f14,f2,f3,f4,f6,f7,f15,f16,f17,f18,f184,f127,f129,f191,f192",
        }
        return await self._fetch_pool(
            f"{EM_BASE}/getTopicZTPool", params,
            lambda item: LimitUpPoolStock(
                code=str(item.get("c", "")), name=str(item.get("n", "")),
                price=float(item.get("p", 0)) / 100 if item.get("p") else 0,
                pct=float(item.get("pct", 0)) / 100 if item.get("pct") else 0,
                limit_days=int(item.get("lbc", 0)), zt_stat=str(item.get("zttj", {}).get("s", "") if isinstance(item.get("zttj"), dict) else ""),
                first_seal=_fmt_time(item.get("fts", 0)), last_seal=_fmt_time(item.get("lts", 0)),
                seal_fund=float(item.get("fund", 0)), break_times=int(item.get("oc", 0)),
                turnover=float(item.get("hs", 0))/100 if item.get("hs") else 0,
                amount=float(item.get("amount", 0)), float_cap=float(item.get("f20", 0)),
                industry=str(item.get("hybk", "")),
            ))

    async def fetch_zb_pool(self, trade_date: date) -> list[FriedBoardPoolStock]:
        """Fetch fried board pool (炸板池)."""
        params = {
            "ut": EM_UT, "dpt": "wz.ztzt", "sort": "fbt:asc",
            "date": trade_date.strftime("%Y%m%d"),
            "pageindex": 0, "pagesize": 300,
            "fields": "f12,f14,f2,f3,f4,f7,f15,f16,f17,f184,f127",
        }
        return await self._fetch_pool(
            f"{EM_BASE}/getTopicZBPool", params,
            lambda item: FriedBoardPoolStock(
                code=str(item.get("c", "")), name=str(item.get("n", "")),
                price=float(item.get("p", 0)) / 100 if item.get("p") else 0,
                pct=float(item.get("pct", 0)) / 100 if item.get("pct") else 0,
                limit_price=float(item.get("limit_p", 0)) / 100 if item.get("limit_p") else 0,
                break_times=int(item.get("oc", 0)),
                first_seal=_fmt_time(item.get("fts", 0)), amplitude=float(item.get("zf", 0))/100 if item.get("zf") else 0,
                turnover=float(item.get("hs", 0))/100 if item.get("hs") else 0,
                industry=str(item.get("hybk", "")),
            ))

    async def fetch_dt_pool(self, trade_date: date) -> list[LimitDownPoolStock]:
        """Fetch limit-down pool (跌停池)."""
        params = {
            "ut": EM_UT, "dpt": "wz.ztzt", "sort": "fund:asc",
            "date": trade_date.strftime("%Y%m%d"),
            "pageindex": 0, "pagesize": 300,
            "fields": "f12,f14,f2,f3,f4,f7,f15,f16,f17,f184,f192",
        }
        return await self._fetch_pool(
            f"{EM_BASE}/getTopicDTPool", params,
            lambda item: LimitDownPoolStock(
                code=str(item.get("c", "")), name=str(item.get("n", "")),
                price=float(item.get("p", 0)) / 100 if item.get("p") else 0,
                pct=float(item.get("pct", 0)) / 100 if item.get("pct") else 0,
                dt_days=int(item.get("lbc", 0)), seal_fund=float(item.get("fund", 0)),
                turnover=float(item.get("hs", 0))/100 if item.get("hs") else 0,
                open_times=int(item.get("oc", 0)), industry=str(item.get("hybk", "")),
            ))

    async def fetch_yzt_pool(self, trade_date: date) -> list[YesterdayLimitUpPoolStock]:
        """Fetch yesterday's limit-up pool with today's performance (昨涨停池).

        KEY endpoint for relay ecology — yesterday's 连板数 + today's change%
        enables PRECISE 晋级率 calculation.
        """
        params = {
            "ut": EM_UT, "dpt": "wz.ztzt", "sort": "zs:desc",
            "date": trade_date.strftime("%Y%m%d"),
            "pageindex": 0, "pagesize": 500,
            "fields": "f12,f14,f2,f3,f4,f7,f15,f16,f17,f184,f127,f129",
        }
        return await self._fetch_pool(
            f"{EM_BASE}/getYesterdayZTPool", params,
            lambda item: YesterdayLimitUpPoolStock(
                code=str(item.get("c", "")), name=str(item.get("n", "")),
                today_pct=float(item.get("pct", 0)) / 100 if item.get("pct") else 0,
                y_limit_days=int(item.get("lbc", 0)),
                y_first_seal=_fmt_time(item.get("fts", 0)),
                today_turnover=float(item.get("hs", 0))/100 if item.get("hs") else 0,
                industry=str(item.get("hybk", "")),
            ))

    async def fetch_sentiment(self, trade_date: date) -> BoardSentiment:
        """Compute board sentiment from all 4 pools."""
        zt = await self.fetch_zt_pool(trade_date)
        zb = await self.fetch_zb_pool(trade_date)
        dt = await self.fetch_dt_pool(trade_date)

        total_touched = len(zt) + len(zb)
        break_rate = round(len(zb) / max(total_touched, 1) * 100, 1)
        max_h = max((s.limit_days for s in zt), default=0)

        ladder: dict[int, int] = {}
        for s in zt:
            h = s.limit_days
            if h > 0:
                ladder[h] = ladder.get(h, 0) + 1

        return BoardSentiment(
            trade_date=trade_date, zt_count=len(zt), zb_count=len(zb),
            dt_count=len(dt), break_rate=break_rate, max_height=max_h,
            ladder=ladder,
        )

    async def _fetch_pool(self, url: str, params: dict, mapper):
        """Generic pool fetcher with Eastmoney response parsing."""
        try:
            r = await self._http.get(url, params=params)
            data = r.json()
            if data.get("rc") != 0:
                print(f"[EM Board] API error: rc={data.get('rc')} msg={data.get('rt')}")
                return []
            items = data.get("data", [])
            if not isinstance(items, list):
                return []
            return [mapper(item) for item in items if isinstance(item, dict)]
        except Exception as e:
            print(f"[EM Board] fetch failed: {e}")
            return []

    async def close(self):
        await self._http.aclose()


def _fmt_time(ts: int) -> str:
    """Convert Unix ms timestamp to HH:MM:SS string."""
    if not ts or ts == 0:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S")
    except (ValueError, OSError):
        return ""

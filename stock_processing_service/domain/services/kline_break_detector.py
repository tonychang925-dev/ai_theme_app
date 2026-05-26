"""P1-G: 强势股支撑位突破/逼近/收复检测器。

基于 strong_stock_watch_pool 的支撑位数据 +
jyhf_stock_quote_snapshot 的最新 current 实时比对。

状态机:
  above → near_support → touch_support → break_support → strong_break
                                                         ↘ recover_support → above

去重: 同一 stock_id + support_type + alert_type，默认 60s 内不重复推送。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import asyncpg

logger = logging.getLogger("sps.kline_break_detector")

TZ_CN = timezone(timedelta(hours=8))

# ── 支撑状态枚举 ──


class AlertType(str, Enum):
    NEAR_SUPPORT = "near_support"
    TOUCH_SUPPORT = "touch_support"
    BREAK_SUPPORT = "break_support"
    STRONG_BREAK = "strong_break_support"
    RECOVER_SUPPORT = "recover_support"


SEVERITY_MAP = {
    AlertType.NEAR_SUPPORT: "info",
    AlertType.TOUCH_SUPPORT: "warning",
    AlertType.BREAK_SUPPORT: "error",
    AlertType.STRONG_BREAK: "critical",
    AlertType.RECOVER_SUPPORT: "info",
}


@dataclass
class SupportAlert:
    stock_id: str
    stock_name: str
    support_type: str
    support_level: float
    support_strength: float
    current: float
    distance_pct: float
    alert_type: AlertType
    severity: str
    quote_ts: str
    generated_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    alerts: list[SupportAlert]
    checked: int
    in_state_cache: int
    elapsed_ms: float


# ── 检测器 ──


class KlineBreakDetector:
    """支撑位突破/逼近/收复检测器。"""

    # 阈值常量
    NEAR_RATIO = 1.03       # current <= support_level * 1.03
    TOUCH_UPPER = 1.005     # current <= support_level * 1.005
    TOUCH_LOWER = 0.995     # current >= support_level * 0.995
    BREAK_RATIO = 0.995     # current < support_level * 0.995
    STRONG_BREAK_RATIO = 0.98   # current < support_level * 0.98
    RECOVER_RATIO = 1.005   # current > support_level * 1.005

    DEDUP_SECONDS = 60      # 同 stock+support_type+alert_type 冷却时间

    def __init__(self, dsn: str, dedup_seconds: int = 60):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._dedup_seconds = dedup_seconds
        # 内存状态缓存: key=(stock_id, support_type) → (alert_type, ts)
        self._state_cache: dict[tuple[str, str], tuple[AlertType, datetime]] = {}

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 加载数据 ──

    async def load_strong_watch_supports(self) -> list[dict[str, Any]]:
        """加载 strong_stock_watch_pool 中有支撑位的 active/weakening 股票。"""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT DISTINCT ON (stock_id)
                 stock_id, stock_name, support_type, support_level, support_score
               FROM strong_stock_watch_pool
               WHERE COALESCE(watch_status, '') != 'removed'
                 AND support_level IS NOT NULL
                 AND support_level > 0
               ORDER BY stock_id, watch_score DESC"""
        )
        return [
            {
                "stock_id": r["stock_id"],
                "stock_name": r["stock_name"] or "",
                "support_type": r["support_type"] or "unknown",
                "support_level": float(r["support_level"]),
                "support_strength": float(r["support_score"] or 0),
            }
            for r in rows
        ]

    async def load_latest_quotes(self, stock_ids: list[str]) -> dict[str, dict[str, Any]]:
        """加载最新一笔 quote（每个 stock 的 latest current）。"""
        if not stock_ids:
            return {}
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT DISTINCT ON (stock_id)
                 stock_id, current, pct_chg, ts
               FROM jyhf_stock_quote_snapshot
               WHERE stock_id = ANY($1::text[])
                 AND current IS NOT NULL
               ORDER BY stock_id, ts DESC""",
            stock_ids,
        )
        return {
            r["stock_id"]: {
                "current": float(r["current"]),
                "pct_chg": float(r["pct_chg"] or 0),
                "ts": str(r["ts"]),
            }
            for r in rows
        }

    # ── 状态判定 ──

    def classify(self, current: float, support_level: float) -> AlertType | None:
        """根据 current vs support_level 判定当前状态。"""
        if current < support_level * self.STRONG_BREAK_RATIO:
            return AlertType.STRONG_BREAK
        if current < support_level * self.BREAK_RATIO:
            return AlertType.BREAK_SUPPORT
        if current <= support_level * self.TOUCH_UPPER and current >= support_level * self.TOUCH_LOWER:
            return AlertType.TOUCH_SUPPORT
        if current <= support_level * self.NEAR_RATIO:
            return AlertType.NEAR_SUPPORT
        return None

    def check_recover(
        self, current: float, support_level: float, stock_id: str, support_type: str,
    ) -> AlertType | None:
        """检查是否从跌破状态收复。"""
        key = (stock_id, support_type)
        prev = self._state_cache.get(key)
        if prev is None:
            return None
        prev_alert, _ = prev
        if prev_alert in (AlertType.BREAK_SUPPORT, AlertType.STRONG_BREAK):
            if current > support_level * self.RECOVER_RATIO:
                return AlertType.RECOVER_SUPPORT
        return None

    def is_duplicate(self, stock_id: str, support_type: str, alert_type: AlertType) -> bool:
        """检查是否在冷却期内。"""
        key = (stock_id, support_type)
        prev = self._state_cache.get(key)
        if prev is None:
            return False
        prev_alert, prev_ts = prev
        if prev_alert == alert_type:
            elapsed = (datetime.now(TZ_CN) - prev_ts).total_seconds()
            if elapsed < self._dedup_seconds:
                return True
        return False

    def update_state(self, stock_id: str, support_type: str, alert_type: AlertType) -> None:
        """更新内存状态缓存。"""
        self._state_cache[(stock_id, support_type)] = (alert_type, datetime.now(TZ_CN))

    # ── 主流程 ──

    async def detect(self) -> DetectionResult:
        """执行一轮检测，返回告警列表。"""
        t0 = datetime.now(TZ_CN)
        now_str = t0.isoformat()
        alerts: list[SupportAlert] = []

        supports = await self.load_strong_watch_supports()
        if not supports:
            return DetectionResult(alerts=[], checked=0, in_state_cache=0, elapsed_ms=0)

        stock_ids = [s["stock_id"] for s in supports]
        quotes = await self.load_latest_quotes(stock_ids)

        in_cache = 0
        for s in supports:
            sid = s["stock_id"]
            q = quotes.get(sid)
            if q is None:
                continue

            current = q["current"]
            support_level = s["support_level"]
            support_type = s["support_type"]
            distance_pct = round((current - support_level) / support_level * 100, 2)

            # 1. 检查收复（优先级最高）
            recover = self.check_recover(current, support_level, sid, support_type)
            if recover:
                if not self.is_duplicate(sid, support_type, recover):
                    self.update_state(sid, support_type, recover)
                    alerts.append(SupportAlert(
                        stock_id=sid, stock_name=s["stock_name"],
                        support_type=support_type,
                        support_level=support_level,
                        support_strength=s["support_strength"],
                        current=current, distance_pct=distance_pct,
                        alert_type=recover, severity=SEVERITY_MAP[recover],
                        quote_ts=q["ts"], generated_at=now_str,
                        extra={"pct_chg": q["pct_chg"]},
                    ))
                else:
                    in_cache += 1
                continue

            # 2. 分类新的支撑状态
            alert_type = self.classify(current, support_level)
            if alert_type is None:
                # above support → 更新状态为 above (不推送)
                self._state_cache[(sid, support_type)] = (AlertType.NEAR_SUPPORT, t0)  # 占位
                continue

            if self.is_duplicate(sid, support_type, alert_type):
                in_cache += 1
                continue

            self.update_state(sid, support_type, alert_type)
            alerts.append(SupportAlert(
                stock_id=sid, stock_name=s["stock_name"],
                support_type=support_type,
                support_level=support_level,
                support_strength=s["support_strength"],
                current=current, distance_pct=distance_pct,
                alert_type=alert_type, severity=SEVERITY_MAP[alert_type],
                quote_ts=q["ts"], generated_at=now_str,
                extra={"pct_chg": q["pct_chg"]},
            ))

        elapsed_ms = round((datetime.now(TZ_CN) - t0).total_seconds() * 1000)
        return DetectionResult(
            alerts=alerts, checked=len(supports),
            in_state_cache=in_cache, elapsed_ms=elapsed_ms,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

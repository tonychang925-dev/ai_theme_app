"""P1-G+: 强势股支撑位突破/逼近/收复检测器 (质量加固版).

基于 strong_stock_watch_pool 的支撑位数据 +
jyhf_stock_quote_snapshot 的最新 current 实时比对.

增强:
  - Redis 状态持久化 (重启不丢)
  - 连续确认: break/strong_break 需连续 2 次 quote 确认
  - 分层冷却: critical 60s / error 120s / warning 300s / info 600s
  - 支撑位年龄诊断: support_level_age_days
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import asyncpg
import redis.asyncio as aioredis

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

# 分层冷却 (秒)
COOLDOWN_MAP = {
    "critical": 60,
    "error": 120,
    "warning": 300,
    "info": 600,
}

# 需要连续确认的告警类型
CONFIRM_REQUIRED = {AlertType.BREAK_SUPPORT, AlertType.STRONG_BREAK}
CONFIRM_COUNT = 2  # 连续 N 次确认

# Redis key 前缀
REDIS_KEY_PREFIX = "kline_alert_state"


@dataclass
class SupportAlert:
    stock_id: str
    stock_name: str
    support_type: str
    support_level: float
    support_strength: float
    support_level_age_days: int
    current: float
    distance_pct: float
    alert_type: AlertType
    severity: str
    previous_state: str
    confirm_count: int
    confidence: float        # 0.0 ~ 1.0
    quote_ts: str
    generated_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    alerts: list[SupportAlert]
    checked: int
    with_quotes: int
    suppressed_by_cooldown: int
    suppressed_by_confirm: int
    elapsed_ms: float


# ── Redis 状态管理 ──


class RedisStateStore:
    """Redis 持久化状态存储。"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0", key_prefix: str = REDIS_KEY_PREFIX):
        self._url = redis_url
        self._prefix = key_prefix
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis | None:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(self._url, decode_responses=True)
                await self._redis.ping()
            except Exception as exc:
                logger.warning("Redis unavailable for state store: %s", exc)
                self._redis = None
        return self._redis

    def _key(self, stock_id: str, support_type: str) -> str:
        return f"{self._prefix}:{stock_id}:{support_type}"

    async def get_state(self, stock_id: str, support_type: str) -> dict | None:
        r = await self._get_redis()
        if r is None:
            return None
        try:
            raw = await r.get(self._key(stock_id, support_type))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def set_state(self, stock_id: str, support_type: str, state: dict, ttl: int = 3600) -> None:
        r = await self._get_redis()
        if r is None:
            return
        try:
            await r.setex(self._key(stock_id, support_type), ttl, json.dumps(state, ensure_ascii=False))
        except Exception as exc:
            logger.debug("Redis set_state failed: %s", exc)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# ── 检测器 ──


class KlineBreakDetector:
    """支撑位突破/逼近/收复检测器 (质量加固版)。"""

    # 阈值常量
    NEAR_RATIO = 1.03
    TOUCH_UPPER = 1.005
    TOUCH_LOWER = 0.995
    BREAK_RATIO = 0.995
    STRONG_BREAK_RATIO = 0.98
    RECOVER_RATIO = 1.005

    def __init__(self, dsn: str, redis_url: str = "redis://localhost:6379/0"):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._state = RedisStateStore(redis_url)

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 加载数据 ──

    async def load_strong_watch_supports(self) -> list[dict[str, Any]]:
        """加载 strong_stock_watch_pool 中有支撑位的非移除股票，含最近交易日。"""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT DISTINCT ON (sw.stock_id)
                 sw.stock_id, sw.stock_name, sw.support_type, sw.support_level, sw.support_score,
                 sw.last_trade_date
               FROM strong_stock_watch_pool sw
               WHERE COALESCE(sw.watch_status, '') != 'removed'
                 AND sw.support_level IS NOT NULL
                 AND sw.support_level > 0
               ORDER BY sw.stock_id, sw.watch_score DESC"""
        )
        now_date = datetime.now(TZ_CN).date()
        result = []
        for r in rows:
            last_td = r.get("last_trade_date")
            age_days = 999
            if last_td:
                try:
                    if isinstance(last_td, str):
                        last_td = datetime.strptime(last_td[:10], "%Y-%m-%d").date()
                    age_days = (now_date - last_td).days
                except Exception:
                    pass
            result.append({
                "stock_id": r["stock_id"],
                "stock_name": r["stock_name"] or "",
                "support_type": r["support_type"] or "unknown",
                "support_level": float(r["support_level"]),
                "support_strength": float(r["support_score"] or 0),
                "last_trade_date": str(last_td)[:10] if last_td else "",
                "support_level_age_days": max(0, age_days),
            })
        return result

    async def load_latest_quotes(self, stock_ids: list[str]) -> dict[str, dict[str, Any]]:
        """加载最新一笔 quote。"""
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

    def _confidence(self, alert_type: AlertType, support_level_age_days: int, confirm_count: int) -> float:
        """计算告警置信度 0.0~1.0。"""
        base = 1.0
        # 支撑位越旧置信度越低
        if support_level_age_days > 30:
            base -= 0.3
        elif support_level_age_days > 14:
            base -= 0.15
        elif support_level_age_days > 7:
            base -= 0.05
        # 连续确认提升置信度
        if alert_type in CONFIRM_REQUIRED:
            base = min(base, 0.5 + 0.25 * confirm_count)
        return round(max(0.1, min(1.0, base)), 2)

    # ── 主流程 ──

    async def detect(self) -> DetectionResult:
        """执行一轮检测，返回告警列表。"""
        t0 = datetime.now(TZ_CN)
        now_str = t0.isoformat()
        alerts: list[SupportAlert] = []

        supports = await self.load_strong_watch_supports()
        if not supports:
            return DetectionResult(alerts=[], checked=0, with_quotes=0,
                                   suppressed_by_cooldown=0, suppressed_by_confirm=0, elapsed_ms=0)

        stock_ids = [s["stock_id"] for s in supports]
        quotes = await self.load_latest_quotes(stock_ids)

        suppressed_cooldown = 0
        suppressed_confirm = 0
        with_quotes = 0

        for s in supports:
            sid = s["stock_id"]
            q = quotes.get(sid)
            if q is None:
                continue
            with_quotes += 1

            current = q["current"]
            support_level = s["support_level"]
            support_type = s["support_type"]
            distance_pct = round((current - support_level) / support_level * 100, 2)
            age_days = s["support_level_age_days"]

            # 1. 分类当前状态
            current_alert = self.classify(current, support_level)
            prev_state_raw = await self._state.get_state(sid, support_type)
            prev_state = prev_state_raw or {
                "current_state": "above",
                "confirm_count": 0,
                "last_alert_type": "",
                "last_alert_at": "",
            }
            prev_alert_type = prev_state.get("last_alert_type", "")
            prev_current_state = prev_state.get("current_state", "above")

            # 2. 检查收复
            if prev_current_state in ("break_support", "strong_break_support"):
                if current > support_level * self.RECOVER_RATIO:
                    current_alert = AlertType.RECOVER_SUPPORT

            # 3. 状态未变化
            current_state_str = current_alert.value if current_alert else "above"
            if current_state_str == prev_current_state:
                # 更新确认计数
                if current_alert in CONFIRM_REQUIRED:
                    prev_state["confirm_count"] = prev_state.get("confirm_count", 0) + 1
                # 检查冷却
                if prev_alert_type:
                    sev = SEVERITY_MAP.get(AlertType(prev_alert_type), "info")
                    cooldown = COOLDOWN_MAP.get(sev, 300)
                    last_at = prev_state.get("last_alert_at", "")
                    if last_at:
                        try:
                            last_ts = datetime.fromisoformat(last_at)
                            elapsed = (datetime.now(TZ_CN) - last_ts).total_seconds()
                            if elapsed < cooldown:
                                suppressed_cooldown += 1
                                await self._state.set_state(sid, support_type, prev_state)
                                continue
                        except ValueError:
                            pass
                await self._state.set_state(sid, support_type, prev_state)
                continue

            # 4. 状态变化 → 检查是否需要连续确认
            if current_alert in CONFIRM_REQUIRED:
                confirm_count = prev_state.get("confirm_count", 0) + 1
                if confirm_count < CONFIRM_COUNT:
                    # 记录但不推送
                    await self._state.set_state(sid, support_type, {
                        "current_state": current_state_str,
                        "confirm_count": confirm_count,
                        "last_alert_type": prev_alert_type,
                        "last_alert_at": prev_state.get("last_alert_at", ""),
                        "support_level": support_level,
                        "last_current": current,
                        "last_updated": now_str,
                    })
                    suppressed_confirm += 1
                    continue
                confirm_count_out = confirm_count
            elif current_alert is None:
                # above → 清除状态
                await self._state.set_state(sid, support_type, {
                    "current_state": "above", "confirm_count": 0,
                    "last_alert_type": "", "last_alert_at": "",
                    "support_level": support_level, "last_current": current,
                    "last_updated": now_str,
                })
                continue
            else:
                confirm_count_out = 1

            # 5. 计算置信度并推送
            sev = SEVERITY_MAP.get(current_alert, "info")
            confidence = self._confidence(current_alert, age_days, confirm_count_out)

            await self._state.set_state(sid, support_type, {
                "current_state": current_state_str,
                "confirm_count": 0,  # 已触发，重置
                "last_alert_type": current_alert.value,
                "last_alert_at": now_str,
                "support_level": support_level,
                "last_current": current,
                "last_updated": now_str,
            })

            alerts.append(SupportAlert(
                stock_id=sid, stock_name=s["stock_name"],
                support_type=support_type,
                support_level=support_level,
                support_strength=s["support_strength"],
                support_level_age_days=age_days,
                current=current, distance_pct=distance_pct,
                alert_type=current_alert, severity=sev,
                previous_state=prev_current_state,
                confirm_count=confirm_count_out,
                confidence=confidence,
                quote_ts=q["ts"], generated_at=now_str,
                extra={
                    "pct_chg": q["pct_chg"],
                    "last_trade_date": s["last_trade_date"],
                },
            ))

        elapsed_ms = round((datetime.now(TZ_CN) - t0).total_seconds() * 1000)
        return DetectionResult(
            alerts=alerts, checked=len(supports), with_quotes=with_quotes,
            suppressed_by_cooldown=suppressed_cooldown,
            suppressed_by_confirm=suppressed_confirm,
            elapsed_ms=elapsed_ms,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
        await self._state.close()

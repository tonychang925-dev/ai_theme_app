"""P1-I-5: 弱转强统一告警服务。

竞价阶段 (9:25):
  W2SAuctionScorer → A/B/C/X + 五档盘口资金流向

盘中阶段 (9:30-15:00, 10s间隔):
  v2.2 intraday scorer → early_turn/turn_strong
  继承 D2 确认权重 + 资金流向约束

统一输出: stream:w2s:alerts
"""
from __future__ import annotations

import json, logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

logger = logging.getLogger("sps.w2s_unified")

TZ_CN = timezone(timedelta(hours=8))

# D2 确认权重继承
D2_BONUS = {"A": 1.15, "B": 1.05, "C": 0.85, "X": 0, "": 0.85}


@dataclass
class UnifiedW2SAlert:
    """统一弱转强告警。"""
    trade_date: str
    candidate_trade_date: str
    candidate_id: int
    stock_id: str
    stock_name: str
    theme_name: str
    candidate_type: str
    weak_type: str

    # 竞价确认
    d2_level: str              # A/B/C/X
    d2_score: float
    auction_open_pct: float
    carry_ratio: float

    # 资金流向
    capital_flow: str          # inflow / outflow / neutral / unknown
    capital_imbalance: float

    # 盘中转强
    intraday_level: str        # turn_strong / early_turn / observe
    intraday_score: float
    current: float
    vwap: float
    above_vwap_ratio: float
    relative_strength: float
    relative_strength_cross_zero: bool
    break_platform_30m: bool
    amount_acceleration: bool
    chase_risk_penalty: float

    # 支撑状态
    support_state: str

    # 统一结果
    unified_level: str         # high_confidence / turn_observe / early_observe / risk
    severity: str
    phase: str                 # auction / intraday
    generated_at: str

    evidence_rules: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class W2SUnifiedAlertService:
    """弱转强统一告警管线。"""

    def __init__(self, dsn: str, redis_url: str = "redis://localhost:6379/0"):
        self._dsn = dsn
        self._redis_url = redis_url
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 竞价阶段 ──

    async def build_auction_alerts(self, candidate_date: str,
                                   confirm_date: str) -> list[UnifiedW2SAlert]:
        """9:25 竞价确认阶段告警。"""
        from stock_processing_service.domain.services.w2s_alert_service import W2SAlertService

        svc = W2SAlertService(self._dsn)
        result = await svc.build_alerts(candidate_date, confirm_trade_date=confirm_date)
        now_str = datetime.now(TZ_CN).isoformat()

        alerts = []
        for a in result.alerts:
            ob = a.extra.get("order_book", {})
            flow = a.extra.get("capital_flow", "unknown")
            alerts.append(UnifiedW2SAlert(
                trade_date=confirm_date,
                candidate_trade_date=candidate_date,
                candidate_id=a.candidate_id,
                stock_id=a.stock_id, stock_name=a.stock_name,
                theme_name=a.theme_name,
                candidate_type=a.candidate_type, weak_type=a.weak_type,
                d2_level=a.confirm_level, d2_score=a.confirm_score,
                auction_open_pct=a.auction_open_pct, carry_ratio=a.carry_ratio,
                capital_flow=flow,
                capital_imbalance=float(ob.get("imbalance", 0)),
                intraday_level="", intraday_score=0,
                current=0, vwap=0, above_vwap_ratio=0,
                relative_strength=0, relative_strength_cross_zero=False,
                break_platform_30m=False, amount_acceleration=False,
                chase_risk_penalty=0, support_state="unknown",
                unified_level=f"auction_{a.confirm_level}",
                severity="important" if a.confirm_level == "A" else "warning",
                phase="auction", generated_at=now_str,
                evidence_rules=[f"d2={a.confirm_level}", f"score={a.confirm_score}", f"flow={flow}"],
                extra={"order_book": ob},
            ))
        await svc.close()
        return alerts

    # ── 盘中阶段 ──

    async def build_intraday_alerts(self, trade_date: str) -> list[UnifiedW2SAlert]:
        """盘中 v2.2 转强观察告警，继承 D2 确认。"""
        from stock_processing_service.domain.services.w2s_intraday_alert_service_v2 import W2SIntradayAlertServiceV2
        from stock_processing_service.domain.services.w2s_intraday_backtest import W2SIntradayBacktest
        from stock_processing_service.domain.services.intraday_minute_state_builder import calc_vwap

        bt = W2SIntradayBacktest(self._dsn)
        result = await bt.run(trade_date, limit_stocks=50)
        if not result.signals:
            await bt.close()
            return []

        # 加载 D2 确认结果 + 候选池元数据（股票名、题材名、候选类型等）
        # 候选池的 next_trade_date 可能滞后，取最新可用日期
        pool = await self._get_pool()
        latest_td = await pool.fetchval(
            "SELECT MAX(next_trade_date) FROM weak_to_strong_candidate_pool"
        )
        lookup_date = latest_td if latest_td else date.fromisoformat(trade_date)
        d2_rows = await pool.fetch(
            """SELECT c.stock_id, c.stock_name, c.theme_name,
                      c.candidate_type, c.weak_type,
                      s.signal_level, s.confirmation_score
               FROM weak_to_strong_candidate_pool c
               LEFT JOIN weak_to_strong_auction_signal s ON s.candidate_id = c.id
                 AND s.trade_date = c.next_trade_date
               WHERE c.next_trade_date = $1::date""",
            lookup_date,
        )
        d2_by_stock: dict[str, dict] = {}
        for r in d2_rows:
            sid = str(r["stock_id"])
            d2_by_stock[sid] = {
                "level": str(r.get("signal_level") or "B"),
                "score": float(r.get("confirmation_score") or 60),
                "stock_name": str(r.get("stock_name") or ""),
                "theme_name": str(r.get("theme_name") or ""),
                "candidate_type": str(r.get("candidate_type") or ""),
                "weak_type": str(r.get("weak_type") or ""),
            }

        stock_ids = list({s.stock_id for s in result.signals})
        series_map = await bt.load_minute_series(trade_date, stock_ids)
        now_str = datetime.now(TZ_CN).isoformat()

        alerts = []
        for sig in result.signals:
            series = series_map.get(sig.stock_id, [])
            ts = sig.minute_ts[:19]
            idx = next((i for i, r in enumerate(series) if str(r.get("minute_ts", ""))[:19] == ts), -1)
            if idx < 0:
                continue

            row = series[idx]
            c = float(row.get("current") or 0)
            amt_d = float(row.get("amount_delta") or 0)
            vol_d = float(row.get("vol_delta") or 0)
            vw, _, _, _ = calc_vwap(amt_d, vol_d, c)

            state = {
                "vwap": vw or sig.vwap, "relative_strength_vs_index": sig.relative_strength,
                "platform_high_30m": 0, "platform_low_30m": 0,
                "break_platform_30m": sig.break_platform,
                "amount_delta": amt_d, "current": c,
            }
            history = []
            for r in series[max(0, idx - 10):idx + 1]:
                cc = float(r.get("current") or 0)
                vv = float(r.get("vwap") or cc)
                history.append({
                    "minute_ts": str(r.get("minute_ts", "")), "above_vwap": cc > vv,
                    "relative_strength_vs_index": float(r.get("relative_strength_vs_index") or 0),
                    "close": float(r.get("close") or cc),
                    "amount_delta": float(r.get("amount_delta") or 0),
                })

            # 读取 D2 确认
            d2 = d2_by_stock.get(sig.stock_id, {"level": "B", "score": 60.0})
            d2_level = d2["level"]
            d2_score = d2["score"]

            # v2.2 评分
            score, level, bd, ev = W2SIntradayAlertServiceV2.score_v2_2(
                state, history, d2_level, c, 0)

            # 资金流向: 读取最新盘口
            capital_flow = "unknown"
            capital_imbalance = 0.0
            try:
                ob_row = await pool.fetchrow(
                    """SELECT raw_json FROM jyhf_stock_quote_snapshot
                       WHERE trade_date = $1::date AND stock_id = $2
                       ORDER BY ts DESC LIMIT 1""",
                    date.fromisoformat(trade_date), sig.stock_id,
                )
                if ob_row:
                    raw = ob_row["raw_json"]
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    ob = raw.get("order_book") if isinstance(raw, dict) else raw.get("_order_book")
                    if ob:
                        capital_flow = ob.get("direction", "unknown")
                        capital_imbalance = float(ob.get("imbalance", 0))
            except Exception:
                pass

            # 统一等级
            if level == "turn_strong" and d2_level in ("A", "B") and capital_flow != "outflow":
                unified = "high_confidence"
                sev = "warning"
            elif level == "early_turn" and d2_level in ("A", "B", "C"):
                unified = "turn_observe"
                sev = "observe"
            elif d2_level == "X" or capital_flow == "outflow":
                unified = "risk"
                sev = "observe"
            else:
                unified = "early_observe"
                sev = "observe"

            if sig.ret_30m is not None:
                # 从候选池 D2 元数据回填股票名、题材名（分钟表无这些字段）
                d2_meta = d2_by_stock.get(sig.stock_id, {})
                alerts.append(UnifiedW2SAlert(
                    trade_date=trade_date, candidate_trade_date="",
                    candidate_id=0, stock_id=sig.stock_id,
                    stock_name=d2_meta.get("stock_name") or sig.stock_name or sig.stock_id,
                    theme_name=d2_meta.get("theme_name") or "",
                    candidate_type=d2_meta.get("candidate_type") or "",
                    weak_type=d2_meta.get("weak_type") or "",
                    d2_level=d2_level, d2_score=d2_score,
                    auction_open_pct=0, carry_ratio=0,
                    capital_flow=capital_flow, capital_imbalance=capital_imbalance,
                    intraday_level=level, intraday_score=score,
                    current=c, vwap=vw or sig.vwap,
                    above_vwap_ratio=sig.above_vwap_ratio,
                    relative_strength=sig.relative_strength,
                    relative_strength_cross_zero=bd.get("relative_strength_cross_zero", False),
                    break_platform_30m=sig.break_platform,
                    amount_acceleration=bd.get("amount_acceleration", False),
                    chase_risk_penalty=bd.get("chase_risk_penalty", 0),
                    support_state="unknown",
                    unified_level=unified, severity=sev,
                    phase="intraday", generated_at=now_str,
                    evidence_rules=ev,
                ))

        await bt.close()
        return alerts

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

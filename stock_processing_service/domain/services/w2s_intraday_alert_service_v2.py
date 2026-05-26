"""P1-I-4b: 盘中弱转强 v2 experimental scorer.

核心思想:
  从 v1 的"越强越好" → v2 的"刚从弱转强，且尚未过度拉升"
  - platform_break 不再加分 (追高因子)
  - above_vwap 奖励"刚站上"，惩罚"远离"
  - amount_accel 必须伴随价格上行
  - relative_strength 奖励"由负转正"

与 v1 并行输出，不替换 v1。默认 observe 级。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

logger = logging.getLogger("sps.w2s_intraday_alert_v2")

TZ_CN = timezone(timedelta(hours=8))

# 评分权重
W_EARLY_TURN = 35
W_REL_TURN = 25
W_SUPPORT = 15
W_AUCTION = 10
W_VOLUME = 10
MAX_CHASE_PENALTY = 30


@dataclass
class W2SIntradayAlertV2:
    trade_date: str
    candidate_trade_date: str
    candidate_id: int
    stock_id: str
    stock_name: str
    theme_name: str
    candidate_type: str
    weak_type: str
    confirm_level: str
    confirm_score: float
    current: float
    vwap: float
    above_vwap_ratio_5m: float
    above_vwap_cross_up: bool
    distance_to_vwap_pct: float
    relative_strength_vs_index: float
    relative_strength_slope_5m: float
    relative_strength_cross_zero: bool
    signal_price_position_30m: float
    amount_acceleration: bool
    price_momentum_3m: float
    platform_break_30m: bool
    support_state: str

    v2_score: float
    v2_level: str                    # early_turn / turn_strong / observe
    early_turn_score: float
    relative_turn_score: float
    support_score: float
    auction_bonus: float
    volume_confirm_score: float
    chase_risk_penalty: float

    severity: str
    scoring_version: str
    evidence_rules: list[str]
    generated_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class V2AlertResult:
    alerts: list[W2SIntradayAlertV2]
    total_checked: int
    level_counts: dict[str, int]


class W2SIntradayAlertServiceV2:
    """v2 experimental scorer."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 评分 ──

    @staticmethod
    def score_v2(state: dict, history: list[dict], confirm_level: str,
                 current: float, support_level: float) -> tuple[float, str, dict, list[str]]:
        """v2 评分: 奖励刚转强，惩罚追高。"""
        evidence: list[str] = []
        breakdown: dict[str, float] = {}

        vwap_val = float(state.get("vwap") or 0)
        # 强制按 minute_ts 倒序 (最新在前)
        history_sorted = sorted(history, key=lambda x: str(x.get("minute_ts", "")), reverse=True)
        hist_5 = history_sorted[:5] if len(history_sorted) >= 5 else history_sorted
        hist_3 = history_sorted[:3] if len(history_sorted) >= 3 else history_sorted

        # ── 1. early_turn (0-35): 刚站上 VWAP ──
        above_count = sum(1 for h in hist_5 if h.get("above_vwap"))
        above_ratio = above_count / len(hist_5) if hist_5 else 0
        dist_vwap = abs(current - vwap_val) / current * 100 if current > 0 else 0

        # 检测刚站上 VWAP (之前 below → 现在 above)
        cross_up = False
        if len(hist_5) >= 2:
            prev_above = sum(1 for h in hist_5[1:3] if h.get("above_vwap"))
            now_above = hist_5[0].get("above_vwap") if hist_5 else False
            cross_up = not prev_above and now_above

        early_score = 0.0
        if cross_up:
            early_score = W_EARLY_TURN
            evidence.append(f"cross_up=true→{early_score:.0f}")
        elif above_ratio <= 0.2:
            early_score = 5  # 还没站上
            evidence.append(f"below_vwap→{early_score:.0f}")
        elif above_ratio <= 0.6:
            early_score = W_EARLY_TURN * 0.7  # 刚站稳
            evidence.append(f"early_hold→{early_score:.0f}")
        elif above_ratio <= 0.9:
            early_score = W_EARLY_TURN * 0.4  # 持续在上方
            evidence.append(f"sustained_above→{early_score:.0f}")
        else:
            early_score = W_EARLY_TURN * 0.1  # 一直在上方很久
            evidence.append(f"long_above→{early_score:.0f}")

        # VWAP 距离惩罚
        if dist_vwap > 3:
            early_score -= 15
            evidence.append(f"vwap_far(dist={dist_vwap:.1f}%)→-15")
        elif dist_vwap > 2:
            early_score -= 5
            evidence.append(f"vwap_moderate(dist={dist_vwap:.1f}%)→-5")

        early_score = max(0, min(W_EARLY_TURN, early_score))
        breakdown["early_turn"] = round(early_score, 1)

        # ── 2. relative_turn (0-25): 相对大盘转强 ──
        rel_now = float(state.get("relative_strength_vs_index") or 0)
        rel_slope_5m = 0.0
        rel_cross_zero = False
        if len(hist_5) >= 2:
            rel_values = [float(h.get("relative_strength_vs_index") or 0) for h in hist_5]
            # 5分钟斜率: 最新 - 最旧
            rel_slope_5m = rel_values[0] - rel_values[-1]
            # 由负转正: 过去分钟中有负值 且 当前>0
            rel_cross_zero = any(r < 0 for r in rel_values[1:]) and rel_values[0] > 0

        rel_score = 0.0
        if rel_cross_zero:
            rel_score = W_REL_TURN
            evidence.append(f"rel_cross_zero→{rel_score:.0f}")
        elif rel_slope_5m > 0.3:
            rel_score = W_REL_TURN * 0.8
            evidence.append(f"rel_improving(slope_5m={rel_slope_5m:.2f})→{rel_score:.0f}")
        elif rel_now > 0:
            rel_score = W_REL_TURN * 0.4
            evidence.append(f"rel_positive→{rel_score:.0f}")
        elif rel_now > -0.5:
            rel_score = W_REL_TURN * 0.15
            evidence.append(f"rel_slight_neg→{rel_score:.0f}")

        breakdown["relative_turn"] = round(rel_score, 1)

        # ── 3. support (0-15): 支撑安全 ──
        sup_score = 0.0
        if support_level > 0 and current > support_level * 1.02:
            sup_score = W_SUPPORT
        elif support_level > 0 and current > support_level:
            sup_score = W_SUPPORT * 0.6
        breakdown["support"] = round(sup_score, 1)
        evidence.append(f"support_score={sup_score:.1f}")

        # ── 4. volume_confirm (0-10): 放量 + 价格跟随 ──
        amt_delta = float(state.get("amount_delta") or 0)
        vol_score = 0.0
        amt_accel = False
        if hist_5:
            avg_amt = sum(float(h.get("amount_delta") or 0) for h in hist_5) / len(hist_5)
            if avg_amt > 0 and amt_delta > avg_amt * 1.2:
                amt_accel = True

        # 3min price momentum
        price_mom_3m = 0.0
        if len(hist_3) >= 2:
            c0 = float(hist_3[0].get("close") or hist_3[0].get("current") or 0)
            c2 = float(hist_3[-1].get("close") or hist_3[-1].get("current") or 0)
            if c2 > 0:
                price_mom_3m = (c0 - c2) / c2 * 100

        if amt_accel and price_mom_3m > 0 and dist_vwap <= 2:
            vol_score = W_VOLUME
            evidence.append(f"volume_ok(amt_accel={amt_accel} mom={price_mom_3m:.2f}%)→{vol_score:.0f}")
        elif amt_accel and price_mom_3m > 0:
            vol_score = W_VOLUME * 0.4
            evidence.append(f"volume_partial(mom_ok dist>2%)→{vol_score:.0f}")
        else:
            vol_score = 0
            evidence.append(f"volume_no(amt_accel={amt_accel} mom={price_mom_3m:.2f}%)→0")

        breakdown["volume_confirm"] = round(vol_score, 1)

        # ── 5. auction_bonus (加权) ──
        bonus = {"A": 1.15, "B": 1.05, "C": 0.9}.get(confirm_level, 0.85)
        score_before = round(early_score + rel_score + sup_score + vol_score, 1)
        breakdown["auction_bonus_factor"] = bonus

        # ── 6. chase_risk_penalty (0 ~ -30) ──
        chase_penalty = 0.0
        price_pos_30m = 0.5
        plat_hi = float(state.get("platform_high_30m") or 0)
        plat_lo = float(state.get("platform_low_30m") or 0)
        if plat_hi > plat_lo:
            price_pos_30m = (current - plat_lo) / (plat_hi - plat_lo)

        if dist_vwap > 3:
            chase_penalty -= 15
            evidence.append(f"chase:vwap_far({dist_vwap:.1f}%)→-15")
        if price_pos_30m > 0.85:
            chase_penalty -= 10
            evidence.append(f"chase:near_high(pos={price_pos_30m:.2f})→-10")
        if bool(state.get("break_platform_30m")):
            chase_penalty -= 5
            evidence.append(f"chase:break_plat→-5")

        chase_penalty = max(-MAX_CHASE_PENALTY, chase_penalty)
        breakdown["chase_risk_penalty"] = round(chase_penalty, 1)
        breakdown["distance_to_vwap_pct"] = round(dist_vwap, 2)
        breakdown["price_position_30m"] = round(price_pos_30m, 2)

        # ── 最终评分 ──
        final_score = max(0, min(100, score_before * bonus + chase_penalty))
        breakdown["total"] = round(final_score, 1)

        level = "early_turn"
        if final_score >= 70:
            level = "turn_strong"
        elif final_score >= 45:
            level = "early_turn"
        else:
            level = "observe"

        evidence.append(f"final_score={final_score:.1f} level={level}")

        # 透传所有诊断字段到 breakdown
        breakdown["above_vwap_ratio_5m"] = round(above_ratio, 2)
        breakdown["above_vwap_cross_up"] = cross_up
        breakdown["relative_strength_slope_5m"] = round(rel_slope_5m, 3)
        breakdown["relative_strength_cross_zero"] = rel_cross_zero
        breakdown["amount_acceleration"] = amt_accel
        breakdown["price_momentum_3m"] = round(price_mom_3m, 3)
        breakdown["distance_to_vwap_pct"] = round(dist_vwap, 2)
        breakdown["price_position_30m"] = round(price_pos_30m, 2)

        return round(final_score, 1), level, breakdown, evidence

    # ── 主流程 (复用 v1 数据加载) ──

    async def build_alerts(self, trade_date: str) -> V2AlertResult:
        from stock_processing_service.domain.services.w2s_intraday_alert_service import W2SIntradayAlertService
        v1_svc = W2SIntradayAlertService(self._dsn)
        candidates = await v1_svc.load_candidates_with_d2(trade_date)
        stock_ids = [str(r.get("stock_id") or "") for r in candidates if r.get("stock_id")]
        latest_states, histories = await v1_svc.load_latest_minute_state(trade_date, stock_ids)

        now_str = datetime.now(TZ_CN).isoformat()
        alerts: list[W2SIntradayAlertV2] = []
        level_counts: dict[str, int] = {}

        for r in candidates:
            cid = r.get("candidate_id")
            sid = str(r.get("stock_id") or "")
            confirm_level = str(r.get("confirm_level") or "")
            if not cid or not confirm_level or confirm_level == "X":
                continue

            state = latest_states.get(sid)
            if state is None:
                continue

            current = float(state.get("current") or 0)
            support_level = float(r.get("support_level") or 0)
            if support_level > 0 and current < support_level * 0.995:
                continue

            score, level, breakdown, evidence = self.score_v2(
                state, histories.get(sid, []), confirm_level, current, support_level,
            )

            level_counts[level] = level_counts.get(level, 0) + 1

            # observe 不推 Redis (仅 dry-run/日志)
            if level == "observe":
                continue

            vwap_val = float(state.get("vwap") or 0)

            # 从 breakdown 读取诊断字段
            alerts.append(W2SIntradayAlertV2(
                trade_date=trade_date,
                candidate_trade_date=str(r.get("candidate_trade_date") or "")[:10],
                candidate_id=int(cid),
                stock_id=sid,
                stock_name=str(r.get("stock_name") or ""),
                theme_name=str(r.get("theme_name") or ""),
                candidate_type=str(r.get("candidate_type") or ""),
                weak_type=str(r.get("weak_type") or ""),
                confirm_level=confirm_level,
                confirm_score=float(r.get("confirm_score") or 0),
                current=current,
                vwap=vwap_val,
                above_vwap_ratio_5m=round(breakdown.get("above_vwap_ratio_5m", 0), 2),
                above_vwap_cross_up=bool(breakdown.get("above_vwap_cross_up", False)),
                distance_to_vwap_pct=round(breakdown.get("distance_to_vwap_pct", 0), 2),
                relative_strength_vs_index=float(state.get("relative_strength_vs_index") or 0),
                relative_strength_slope_5m=round(breakdown.get("relative_strength_slope_5m", 0), 3),
                relative_strength_cross_zero=bool(breakdown.get("relative_strength_cross_zero", False)),
                signal_price_position_30m=round(breakdown.get("price_position_30m", 0.5), 2),
                amount_acceleration=bool(breakdown.get("amount_acceleration", False)),
                price_momentum_3m=round(breakdown.get("price_momentum_3m", 0), 3),
                platform_break_30m=bool(state.get("break_platform_30m")),
                support_state="above_support",
                v2_score=score,
                v2_level=level,
                early_turn_score=breakdown.get("early_turn", 0),
                relative_turn_score=breakdown.get("relative_turn", 0),
                support_score=breakdown.get("support", 0),
                auction_bonus=breakdown.get("auction_bonus_factor", 1.0),
                volume_confirm_score=breakdown.get("volume_confirm", 0),
                chase_risk_penalty=breakdown.get("chase_risk_penalty", 0),
                severity="observe",
                scoring_version="v2_experimental",
                evidence_rules=evidence,
                generated_at=now_str,
            ))

        await v1_svc.close()
        return V2AlertResult(alerts=alerts, total_checked=len(candidates), level_counts=level_counts)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

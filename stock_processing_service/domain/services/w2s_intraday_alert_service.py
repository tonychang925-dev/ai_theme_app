"""P1-I-4: 盘中弱转强买点观察告警。

基于 D1候选 + D2竞价确认 + 分钟状态层 综合评分。
不输出买卖建议，仅做观察提醒。

评分维度 (0-100):
  above_vwap_score       (0-25)  最近5分 above_vwap 占比
  relative_strength_score(0-25)  相对指数强度
  platform_break_score   (0-20)  30分钟平台突破
  amount_score           (0-15)  量能加速
  support_score          (0-15)  支撑位安全边际
  auction_bonus          加权    D2确认等级加权

alert_level: A(≥80) / B(≥65) / C(≥55) / X(<55不推)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

logger = logging.getLogger("sps.w2s_intraday_alert")

TZ_CN = timezone(timedelta(hours=8))

# 评分权重
W_ABOVE_VWAP = 25
W_REL_STRENGTH = 25
W_PLATFORM_BREAK = 20
W_AMOUNT = 15
W_SUPPORT = 15


@dataclass
class W2SIntradayAlert:
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
    relative_strength_vs_index: float
    relative_strength_turn_positive: bool
    break_platform_30m: bool
    platform_high_30m: float
    amount_acceleration: bool
    support_state: str
    position_label: str
    pattern_labels: list[str]
    intraday_score: float
    alert_level: str             # A / B / C
    severity: str
    evidence_rules: list[str]
    generated_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class W2SIntradayAlertResult:
    alerts: list[W2SIntradayAlert]
    total_candidates: int
    checked_with_state: int
    level_a: int
    level_b: int
    level_c: int


class W2SIntradayAlertService:
    """盘中弱转强买点观察告警服务。"""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 加载 ──

    async def load_candidates_with_d2(self, trade_date: str) -> list[dict]:
        """加载今日 D1 候选 + D2 确认 + 支撑位。"""
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        rows = await pool.fetch(
            """SELECT
                 c.id AS candidate_id,
                 c.stock_id,
                 c.stock_name,
                 COALESCE(c.theme_name, '') AS theme_name,
                 c.candidate_type,
                 c.weak_type,
                 c.candidate_score,
                 COALESCE(c.pool_entry_type, 'formal') AS pool_entry_type,
                 s.signal_level AS confirm_level,
                 s.confirmation_score AS confirm_score,
                 sw.support_type,
                 sw.support_level,
                 sw.support_score AS support_strength
               FROM weak_to_strong_candidate_pool c
               LEFT JOIN weak_to_strong_auction_signal s
                 ON s.candidate_id = c.id AND s.trade_date = c.next_trade_date
               LEFT JOIN strong_stock_watch_pool sw
                 ON split_part(sw.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
                 AND COALESCE(sw.watch_status, '') != 'removed'
               WHERE c.next_trade_date = $1::date
                 AND COALESCE(NULLIF(LOWER(c.pool_entry_type), ''), 'formal') = 'formal'
               ORDER BY c.candidate_score DESC""",
            td,
        )
        return [dict(r) for r in rows]

    async def load_latest_minute_state(self, trade_date: str, stock_ids: list[str]) -> dict[str, dict]:
        """加载每个 stock 最新分钟状态 + 最近 5 分钟历史。"""
        if not stock_ids:
            return {}, {}
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        codes = [sid.replace(".SZ", "").replace(".SH", "").replace(".BJ", "") for sid in stock_ids]
        code_to_sid = {c: s for c, s in zip(codes, stock_ids)}

        # 最新一条
        latest_rows = await pool.fetch(
            """SELECT DISTINCT ON (stock_id)
                 stock_id, current, vwap, above_vwap, pct_chg,
                 relative_strength_vs_index, break_platform_30m,
                 platform_high_30m, amount_delta, minute_ts
               FROM intraday_stock_minute_state
               WHERE trade_date = $1::date
                 AND stock_id = ANY($2::text[])
               ORDER BY stock_id, minute_ts DESC""",
            td, stock_ids,
        )
        latest = {r["stock_id"]: dict(r) for r in latest_rows}

        # 最近5分钟历史 (用于 above_vwap_ratio_5m 和 relative_strength_turn)
        history_by_stock: dict[str, list[dict]] = {}
        for r in await pool.fetch(
            """SELECT stock_id, above_vwap, relative_strength_vs_index, minute_ts
               FROM intraday_stock_minute_state
               WHERE trade_date = $1::date
                 AND stock_id = ANY($2::text[])
               ORDER BY minute_ts DESC""",
            td, stock_ids,
        ):
            sid = r["stock_id"]
            history_by_stock.setdefault(sid, []).append(dict(r))

        return latest, history_by_stock

    async def load_positions_patterns(self, trade_date: str, stock_ids: list[str]) -> dict[str, dict]:
        """加载位置/形态判断。"""
        if not stock_ids:
            return {}
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        result: dict[str, dict] = {}
        for r in await pool.fetch(
            "SELECT stock_id, position_label FROM stock_position_judgement WHERE trade_date=$1::date AND stock_id=ANY($2::text[])",
            td, stock_ids,
        ):
            result.setdefault(r["stock_id"], {})["position_label"] = str(r.get("position_label") or "")
        for r in await pool.fetch(
            "SELECT stock_id, pattern_labels FROM stock_pattern_judgement WHERE trade_date=$1::date AND stock_id=ANY($2::text[])",
            td, stock_ids,
        ):
            raw = r.get("pattern_labels")
            if isinstance(raw, list):
                labels = [str(s) for s in raw]
            elif isinstance(raw, str):
                try:
                    labels = list(json.loads(raw))
                except Exception:
                    labels = []
            else:
                labels = []
            result.setdefault(r["stock_id"], {})["pattern_labels"] = labels
        return result

    # ── 评分 ──

    def score(self, state: dict, history: list[dict], confirm_level: str,
              support_level: float, current: float) -> tuple[float, str, list[str]]:
        """综合评分 → (score, alert_level, evidence)。"""
        evidence: list[str] = []
        score = 0.0

        # 1. above_vwap (0-25)
        vwap = float(state.get("vwap") or 0)
        hist_5 = history[:5] if len(history) >= 5 else history
        above_count = sum(1 for h in hist_5 if h.get("above_vwap"))
        above_ratio = above_count / len(hist_5) if hist_5 else 0
        vwap_score = min(W_ABOVE_VWAP, above_ratio * W_ABOVE_VWAP)
        score += vwap_score
        evidence.append(f"above_vwap_ratio={above_ratio:.1%} score={vwap_score:.1f}")

        # 2. relative_strength (0-25)
        rel_str = float(state.get("relative_strength_vs_index") or 0)
        rel_score = 0.0
        if rel_str > 1.0:
            rel_score = W_REL_STRENGTH
        elif rel_str > 0.5:
            rel_score = 20
        elif rel_str > 0:
            rel_score = 12
        elif rel_str > -0.5:
            rel_score = 5
        score += rel_score
        evidence.append(f"rel_strength={rel_str:.2f} score={rel_score:.1f}")

        # 3. platform_break (0-20)
        break_plat = bool(state.get("break_platform_30m"))
        plat_score = W_PLATFORM_BREAK if break_plat else 0
        score += plat_score
        evidence.append(f"break_platform={break_plat} score={plat_score:.1f}")

        # 4. amount_acceleration (0-15)
        amt_delta = float(state.get("amount_delta") or 0)
        amt_accel = False
        amt_score = 0.0
        if hist_5:
            avg_amt = sum(float(h.get("amount_delta") or 0) for h in hist_5) / len(hist_5)
            if avg_amt > 0 and amt_delta > avg_amt * 1.2:
                amt_accel = True
                amt_score = W_AMOUNT
            elif amt_delta > 0:
                amt_score = W_AMOUNT * 0.4
        score += amt_score
        evidence.append(f"amount_delta={amt_delta:.0f} accel={amt_accel} score={amt_score:.1f}")

        # 5. support_safety (0-15)
        sup_score = 0.0
        if support_level > 0 and current > support_level * 1.01:
            sup_score = W_SUPPORT
        elif support_level > 0 and current > support_level:
            sup_score = W_SUPPORT * 0.6
        score += sup_score
        evidence.append(f"sup_safety={sup_score:.1f}")

        # 6. auction_bonus (加权至 100 上限)
        bonus = {"A": 1.1, "B": 1.0, "C": 0.85}.get(confirm_level, 0.85)
        score = min(100, score * bonus)
        evidence.append(f"auction_bonus={bonus} final={score:.1f}")

        level = "X"
        if score >= 80:
            level = "A"
        elif score >= 65:
            level = "B"
        elif score >= 55:
            level = "C"

        return round(score, 1), level, evidence

    # ── 主流程 ──

    async def build_alerts(self, trade_date: str) -> W2SIntradayAlertResult:
        now_str = datetime.now(TZ_CN).isoformat()
        candidates = await self.load_candidates_with_d2(trade_date)

        stock_ids = [str(r.get("stock_id") or "") for r in candidates if r.get("stock_id")]
        latest_states, histories = await self.load_latest_minute_state(trade_date, stock_ids)
        positions = await self.load_positions_patterns(trade_date, stock_ids)

        alerts: list[W2SIntradayAlert] = []
        checked = 0
        level_counts = {"A": 0, "B": 0, "C": 0}

        for r in candidates:
            cid = r.get("candidate_id")
            sid = str(r.get("stock_id") or "")
            confirm_level = str(r.get("confirm_level") or "")
            if not cid or not confirm_level or confirm_level == "X":
                continue

            state = latest_states.get(sid)
            if state is None:
                continue
            checked += 1

            current = float(state.get("current") or 0)
            support_level = float(r.get("support_level") or 0)

            # 支撑风险过滤
            if support_level > 0 and current < support_level * 0.995:
                continue

            score, level, evidence = self.score(
                state, histories.get(sid, []),
                confirm_level, support_level, current,
            )
            if level == "X":
                continue

            level_counts[level] = level_counts.get(level, 0) + 1

            pos = positions.get(sid, {})
            hist_5 = histories.get(sid, [])[:5]
            above_count = sum(1 for h in hist_5 if h.get("above_vwap"))
            above_ratio = above_count / len(hist_5) if hist_5 else 0

            # relative_strength_turn: 检查最近5分钟是否由负转正
            rel_turn_positive = False
            if len(hist_5) >= 2:
                rel_prev = [float(h.get("relative_strength_vs_index") or 0) for h in hist_5]
                if any(r < 0 for r in rel_prev[1:]) and rel_prev[0] > 0:
                    rel_turn_positive = True

            alerts.append(W2SIntradayAlert(
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
                vwap=float(state.get("vwap") or 0),
                above_vwap_ratio_5m=round(above_ratio, 2),
                relative_strength_vs_index=float(state.get("relative_strength_vs_index") or 0),
                relative_strength_turn_positive=rel_turn_positive,
                break_platform_30m=bool(state.get("break_platform_30m")),
                platform_high_30m=float(state.get("platform_high_30m") or 0),
                amount_acceleration=("accel=True" in " ".join(evidence)),
                support_state="above_support" if support_level > 0 and current > support_level else "unknown",
                position_label=pos.get("position_label", ""),
                pattern_labels=pos.get("pattern_labels", []),
                intraday_score=score,
                alert_level=level,
                severity="important" if level in ("A", "B") else "observe",
                evidence_rules=evidence,
                generated_at=now_str,
            ))

        return W2SIntradayAlertResult(
            alerts=alerts,
            total_candidates=len(candidates),
            checked_with_state=checked,
            level_a=level_counts.get("A", 0),
            level_b=level_counts.get("B", 0),
            level_c=level_counts.get("C", 0),
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

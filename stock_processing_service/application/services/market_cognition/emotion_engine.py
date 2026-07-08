"""P2.6 — Market Emotion Engine.

Reads market_environment_metrics + market_environment_judgement.
Computes 5-layer emotion scoring. Maps to FSM emotion node.
No LLM. Deterministic rule-based.

Five layers:
  L1 Market Breadth — 全市场赚钱效应
  L2 Short-Term Momentum — 短线情绪动能
  L3 Relay Ecology — 接力生态
  L4 Active Capital — 活跃资金
  L5 Style Rotation — 风格切换

Output: MarketEmotionState with emotion_node, scores, evidence, strategy.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

DB_DSN = "postgresql://localhost:5432/stock_data_test"

# ── Emotion node thresholds ──
# Map composite score to FSM emotion node
_EMOTION_NODE_MAP = [
    (75, "CLIMAX", "情绪高潮"),
    (50, "ACCELERATION", "情绪加速"),
    (25, "FERMENTATION", "情绪发酵"),
    (0, "REPAIR", "情绪修复"),
    (-25, "DIVERGENCE", "情绪分歧"),
    (-50, "FADE", "情绪退潮"),
    (-75, "ICE_POINT", "情绪冰点"),
    (-100, "CHAOS", "情绪混沌"),
]

# ── Breadth thresholds ──
def _breadth_status(up: int, down: int, limit_up: int, limit_down: int) -> tuple[str, int]:
    total = up + down or 1
    ratio = up / total
    if ratio > 0.65 and limit_up > 80 and limit_down < 30:
        return "强赚钱", 80
    elif ratio > 0.50 and limit_up > 50:
        return "弱赚钱", 50
    elif ratio > 0.40:
        return "中性", 0
    elif ratio > 0.30:
        return "弱亏钱", -40
    else:
        return "强亏钱", -70


class MarketEmotionEngine:
    """Compute MarketEmotionState from DB metrics.

    Usage:
        engine = MarketEmotionEngine()
        state = engine.run(date(2026, 7, 7))
    """

    def run(self, trade_date: date) -> dict[str, Any]:
        return asyncio.run(self._run_async(trade_date))

    async def run_async(self, trade_date: date) -> dict[str, Any]:
        import asyncpg

        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            # ── Load metrics ──
            row = await conn.fetchrow(
                "SELECT * FROM market_environment_metrics WHERE trade_date = $1::date LIMIT 1",
                trade_date,
            )
            if not row:
                # Fallback: use recap snapshot data for recent dates
                return await self._from_recap(trade_date, conn)

            up = int(row["up_count"] or 0)
            down = int(row["down_count"] or 0)
            limit_up = int(row["limit_up_count"] or 0)
            limit_down = int(row["limit_down_count"] or 0)
            amount = float(row["market_total_amount"] or 0)
            yesterday_red = float(row["yesterday_limit_up_open_red_ratio"] or 0) * 100
            yesterday_premium = float(row["yesterday_limit_up_premium_ratio"] or 0) * 100
            yesterday_fade = float(row["yesterday_limit_up_fade_ratio"] or 0) * 100
            yesterday_fail = float(row["yesterday_limit_up_fail_ratio"] or 0) * 100
            intraday_fade_ratio = float(row["intraday_fade_ratio"] or 0) * 100
            volume_change = float(row["market_volume_change_pct"] or 0)

            # ── Load judgement ──
            jrow = await conn.fetchrow(
                "SELECT breadth_status, short_term_sentiment_status, relay_sentiment_status, "
                "intraday_fade_status, market_health_score, action_bias, conclusion, evidence "
                "FROM market_environment_judgement WHERE trade_date = $1::date LIMIT 1",
                trade_date,
            )

            # ── L1: Breadth ──
            b_label, b_score = _breadth_status(up, down, limit_up, limit_down)

            # ── L2: Momentum ──
            m_score = int(50 + yesterday_premium * 0.4 - yesterday_fade * 0.3 - yesterday_fail * 0.5)
            m_score = max(-100, min(100, m_score))
            if m_score > 60:
                m_label = "情绪加速"
            elif m_score > 20:
                m_label = "情绪活跃"
            elif m_score > -20:
                m_label = "情绪钝化"
            elif m_score > -50:
                m_label = "情绪退潮"
            else:
                m_label = "情绪冰点"

            # ── L3: Relay Ecology ──
            if jrow and jrow["relay_sentiment_status"]:
                r_label = jrow["relay_sentiment_status"]
                if "活跃" in str(r_label):
                    r_score = 60
                elif "偏弱" in str(r_label):
                    r_score = -30
                elif "冰点" in str(r_label):
                    r_score = -70
                else:
                    r_score = 0
            else:
                r_label = "数据不足"
                r_score = 0

            # ── L4: Active Capital ──
            amount_yi = amount / 100_000_000  # 转亿
            if amount_yi > 30_000:
                c_score = 70
                c_label = "资金扩张"
            elif amount_yi > 20_000:
                c_score = 30
                c_label = "资金正常"
            elif amount_yi > 10_000:
                c_score = -20
                c_label = "资金收缩"
            else:
                c_score = -60
                c_label = "冰点低量"

            # ── L5: Style ──
            if jrow and jrow["breadth_status"]:
                bstat = str(jrow["breadth_status"])
                if "强" in bstat and limit_up > 80:
                    s_label = "机构趋势主导"
                    s_score = 50
                elif limit_up > 50:
                    s_label = "游资情绪主导"
                    s_score = 30
                else:
                    s_label = "防御轮动"
                    s_score = -20
            else:
                s_label = "混沌"
                s_score = -40

            # ── Composite emotion ──
            composite = int(
                b_score * 0.20 + m_score * 0.30 + r_score * 0.20
                + c_score * 0.15 + s_score * 0.15
            )
            node = "CHAOS"
            node_desc = "情绪混沌"
            for threshold, n, desc in _EMOTION_NODE_MAP:
                if composite >= threshold:
                    node = n
                    node_desc = desc
                    break

            # ── Evidence ──
            evidence = [
                f"涨停 {limit_up} 家，跌停 {limit_down} 家",
                f"上涨 {up} / 下跌 {down}，赚钱效应{'强' if b_score>0 else '弱'}",
                f"昨日涨停溢价率 {yesterday_premium:.0f}%，大面率 {yesterday_fail:.0f}%",
                f"成交额 {amount_yi/10000:.1f}万亿",
                f"接力生态: {r_label}",
            ]

            # ── Strategy bias ──
            if node == "ICE_POINT":
                strategy = "冰点试错：若出现新题材且有竞价/首板确认，可重点观察"
            elif node in ("REPAIR", "FERMENTATION"):
                strategy = "修复确认后可右侧跟随，重点做核心龙头"
            elif node in ("ACCELERATION", "CLIMAX"):
                strategy = "不追高，等分歧。只做低位补涨方向"
            elif node in ("DIVERGENCE", "FADE"):
                strategy = "谨慎观望，防范退潮。只做反弹不追趋势"
            else:
                strategy = "混沌期：轻仓等待方向确认"

            return {
                "trade_date": trade_date.isoformat(),
                "emotion_node": node,
                "emotion_desc": node_desc,
                "emotion_score": composite,
                "breadth_score": b_score,
                "breadth_label": b_label,
                "momentum_score": m_score,
                "momentum_label": m_label,
                "relay_score": r_score,
                "relay_label": r_label,
                "capital_score": c_score,
                "capital_label": c_label,
                "style_score": s_score,
                "style_label": s_label,
                "key_evidence": evidence,
                "strategy_bias": strategy,
                "raw": {
                    "limit_up": limit_up,
                    "limit_down": limit_down,
                    "chain_board": up,
                    "minus_5": down,
                    "up_count": up,
                    "down_count": down,
                    "turnover_yi": round(amount_yi / 10000, 2),
                    "yesterday_red_pct": round(yesterday_red, 1),
                    "yesterday_premium_pct": round(yesterday_premium, 1),
                    "yesterday_fade_pct": round(yesterday_fade, 1),
                    "yesterday_fail_pct": round(yesterday_fail, 1),
                    "intraday_fade_pct": round(intraday_fade_ratio, 1),
                    "volume_change_pct": round(volume_change, 1),
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        finally:
            await conn.close()

    async def _from_recap(self, trade_date: date, conn) -> dict[str, Any]:
        """Fallback: compute from recap snapshot when metrics table has no data."""
        import json
        row = await conn.fetchrow(
            "SELECT payload FROM post_market_recap_snapshot "
            "WHERE trade_date = $1::date ORDER BY created_at DESC LIMIT 1",
            trade_date,
        )
        if not row:
            return _empty_state(trade_date)

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        recap = payload.get("recap_doc", payload)

        overview = recap.get("market_overview_review", {})
        env = recap.get("market_environment_review", {})
        regime = recap.get("market_regime_review", {})

        up = int(overview.get("up_count", 0) or 0)
        down = int(overview.get("down_count", 0) or 0)
        limit_up = int(overview.get("limit_up_total", 0) or 0)
        limit_down = int(overview.get("limit_down_total", 0) or 0)
        amount = float(overview.get("total_amount", 0) or 0)
        # total_amount is in 万元; convert to 亿 for display
        amount_yi = amount / 10_000

        # Emotion stage from existing judgement
        emotion_stage = str(env.get("emotion_stage", ""))
        market_score = float(env.get("market_score", 0) or 0)
        market_mode = str(env.get("market_mode", "wait"))
        risk_flags = env.get("risk_flags", [])

        # Breadth
        b_label, b_score = _breadth_status(up, down, limit_up, limit_down)

        # Momentum — rough estimate from available data
        total = up + down or 1
        up_ratio = up / total
        m_score = int(up_ratio * 100 - 50 + (limit_up * 0.1))
        m_score = max(-100, min(100, m_score))
        if m_score > 50:
            m_label = "情绪活跃"
        elif m_score > 10:
            m_label = "情绪正常"
        elif m_score > -30:
            m_label = "情绪偏弱"
        elif m_score > -60:
            m_label = "情绪退潮"
        else:
            m_label = "情绪冰点"

        # Relay estimated from limit_up count
        if limit_up > 100:
            r_label, r_score = "接力活跃", 60
        elif limit_up > 60:
            r_label, r_score = "接力正常", 20
        elif limit_up > 30:
            r_label, r_score = "接力偏弱", -20
        else:
            r_label, r_score = "接力冰点", -60

        # Capital from amount (in 亿)
        if amount_yi > 250_000:
            c_label, c_score = "资金扩张", 60
        elif amount_yi > 200_000:
            c_label, c_score = "资金正常", 20
        elif amount_yi > 150_000:
            c_label, c_score = "资金收缩", -30
        else:
            c_label, c_score = "冰点低量", -60

        # Style from market mode
        if market_mode == "normal":
            s_label, s_score = "正常交易", 30
        elif market_mode == "defense":
            s_label, s_score = "防御为主", -20
        elif market_mode == "wait":
            s_label, s_score = "等待观望", -40
        else:
            s_label, s_score = "混沌", -50

        # Composite
        composite = int(
            b_score * 0.20 + m_score * 0.30 + r_score * 0.20
            + c_score * 0.15 + s_score * 0.15
        )
        node = "CHAOS"
        node_desc = "情绪混沌"
        for threshold, n, desc in _EMOTION_NODE_MAP:
            if composite >= threshold:
                node = n
                node_desc = desc
                break

        evidence = [
            f"涨停 {limit_up} 家，跌停 {limit_down} 家",
            f"上涨 {up} / 下跌 {down}",
            f"成交额 {amount_yi/10000:.1f}万亿",
            f"市场模式: {market_mode}",
        ]
        if risk_flags:
            evidence.append(f"风险: {', '.join(str(r) for r in risk_flags[:3])}")

        if node == "ICE_POINT":
            strategy = "冰点试错：若出现新题材且有竞价/首板确认，可重点观察"
        elif node in ("REPAIR", "FERMENTATION"):
            strategy = "修复确认后可右侧跟随"
        elif node in ("ACCELERATION", "CLIMAX"):
            strategy = "不追高，等分歧"
        elif node in ("DIVERGENCE", "FADE"):
            strategy = "谨慎观望，防范退潮"
        else:
            strategy = "混沌期：轻仓等待"

        return {
            "trade_date": trade_date.isoformat(),
            "emotion_node": node, "emotion_desc": node_desc,
            "emotion_score": composite,
            "breadth_score": b_score, "breadth_label": b_label,
            "momentum_score": m_score, "momentum_label": m_label,
            "relay_score": r_score, "relay_label": r_label,
            "capital_score": c_score, "capital_label": c_label,
            "style_score": s_score, "style_label": s_label,
            "key_evidence": evidence,
            "strategy_bias": strategy,
            "raw": {
                "limit_up": limit_up, "limit_down": limit_down,
                "up_count": up, "down_count": down,
                "turnover_yi": round(amount_yi / 10000, 2),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "recap_fallback",
        }


def _empty_state(trade_date: date) -> dict[str, Any]:
    return {
        "trade_date": trade_date.isoformat(),
        "emotion_node": "CHAOS",
        "emotion_desc": "数据不足",
        "emotion_score": 0,
        "breadth_score": 0, "breadth_label": "无数据",
        "momentum_score": 0, "momentum_label": "无数据",
        "relay_score": 0, "relay_label": "无数据",
        "capital_score": 0, "capital_label": "无数据",
        "style_score": 0, "style_label": "无数据",
        "key_evidence": [],
        "strategy_bias": "数据不足，无法判断",
        "raw": {},
    }

"""P2.2 — CognitionCardBuilder.

AI auto-fills CognitionCard from DB data for HIGH/CRITICAL subjects.
No LLM. Template-based. Does NOT write M8 DailyMarketState.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from typing import Any

DB_DSN = "postgresql://localhost:5432/stock_data_test"

# ── Phase mappings ──
_CYCLE_STATE_TO_PHASE: dict[str, str] = {
    "start": "启动阶段 — 新方向开始形成",
    "fermentation": "发酵阶段 — 方向确认，资金聚集",
    "divergence": "分歧阶段 — 首次显著分歧，检验方向质量",
    "repair": "修复阶段 — 分歧后资金回流确认",
    "fade_watch": "退潮观察 — 方向走弱迹象",
    "fade_confirmed": "退潮确认 — 资金撤离",
}

# ── Trading style heuristics ──
_STYLE_HEURISTICS: dict[str, str] = {
    "start": "趋势风格为主，机构试探性建仓",
    "fermentation": "趋势+游资混合，情绪开始升温",
    "divergence": "游资活跃，机构分歧加大",
    "repair": "机构回流确认，趋势修复",
    "fade_watch": "游资撤退，机构防御",
    "fade_confirmed": "游资+机构同步撤离",
}


class CognitionCardBuilder:
    """Build AI-generated CognitionCard draft from DB data.

    Usage:
        builder = CognitionCardBuilder()
        card = builder.build(date(2026, 7, 3), "theme:9014636")
    """

    def build(self, trade_date: date, subject_id: str) -> dict[str, Any]:
        return asyncio.run(self._build_async(trade_date, subject_id))

    async def build_async(self, trade_date: date, subject_id: str) -> dict[str, Any]:
        """Async-native entry point for FastAPI handlers."""
        return await self._build_async(trade_date, subject_id)

    async def _build_async(self, trade_date: date, subject_id: str) -> dict[str, Any]:
        import asyncpg

        subject_key = subject_id.replace("theme:", "")
        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            # ── Load theme data ──
            row = await conn.fetchrow(
                "SELECT subject_key, theme_name, final_cycle_state, "
                "final_mainline_alive, mainline_strength_score, "
                "fade_watch_score, fade_confirmed_score, "
                "divergence_score, repair_score "
                "FROM theme_cycle_judgement_v2 "
                "WHERE trade_date = $1::date AND subject_key = $2",
                trade_date, subject_key,
            )

            if row is None:
                return _empty_card(trade_date, subject_id)

            raw_state = row["final_cycle_state"] or "start"
            ms_score = float(row["mainline_strength_score"] or 50)
            fw_score = float(row["fade_watch_score"] or 0)
            fc_score = float(row["fade_confirmed_score"] or 0)
            rep_score = float(row["repair_score"] or 0)

            # ── Load leader data from theme_reviews in recap snapshot ──
            recap_row = await conn.fetchrow(
                "SELECT payload FROM post_market_recap_snapshot "
                "WHERE trade_date = $1::date ORDER BY created_at DESC LIMIT 1",
                trade_date,
            )
            events, leaders, real_name = self._extract_events_and_leaders(recap_row, subject_key)

            # Use the recap name if available (more reliable than cycle_judgement table)
            subject_name = real_name or row["theme_name"] or subject_key
            if subject_name and subject_name == subject_key:
                subject_name = await self._lookup_name(conn, subject_key)

            # ── Build card ──
            card = {
                "trade_date": trade_date.isoformat(),
                "subject_id": subject_id,
                "subject_name": subject_name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "ai_draft": True,
                "analyst_reviewed": False,

                # ── Fields ──
                "trading_style": _STYLE_HEURISTICS.get(raw_state, "趋势风格"),
                "market_phase": _CYCLE_STATE_TO_PHASE.get(raw_state, raw_state),
                "phase_raw": raw_state,
                "event_stimuli": events if events else ["[无显著事件 — 分析师补充]"],
                "current_leaders": leaders[:3] if leaders else ["[分析师填入]"],
                "potential_leaders": leaders[3:5] if len(leaders) > 3 else ["[分析师填入]"],
                "bull_pool": [l for l in leaders[:2]] if leaders else ["[分析师填入]"],
                "bear_pool": self._derive_bear_pool(fw_score, fc_score, leaders),
                "yesterday_view": self._derive_yesterday_view(raw_state, ms_score, rep_score),
                "today_actual": self._derive_today_actual(raw_state, ms_score),
                "tomorrow_view": self._derive_tomorrow_view(raw_state, fw_score, rep_score),
                "analyst_notes": "",
                "analyst_overrides": {},
                "evidence_refs": [f"ev:db:{trade_date.isoformat()}"],
            }

            return card

        finally:
            await conn.close()

    # ── Name lookup ──

    @staticmethod
    async def _lookup_name(conn, subject_key: str) -> str:
        """Try all sources to find a real theme name."""
        # Try recap snapshot
        row = await conn.fetchrow(
            "SELECT payload FROM post_market_recap_snapshot "
            "ORDER BY trade_date DESC LIMIT 1"
        )
        if row:
            try:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                recap = payload.get("recap_doc", payload)
                for t in recap.get("theme_reviews", []):
                    if str(t.get("subject_key", "")) == subject_key:
                        name = t.get("theme_name", "")
                        if name and name != subject_key:
                            return str(name)
            except Exception:
                pass
        return subject_key

    # ── Heuristic generators ──

    @staticmethod
    def _extract_events_and_leaders(
        recap_row: Any, subject_key: str
    ) -> tuple[list[str], list[str], str]:
        """Extract events, leaders, and real theme_name from recap snapshot."""
        events: list[str] = []
        leaders: list[str] = []
        real_name = ""
        if recap_row is None:
            return events, leaders, real_name
        try:
            payload = recap_row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            recap = payload.get("recap_doc", payload)
            themes = recap.get("theme_reviews", [])
            for t in themes:
                sk = str(t.get("subject_key", ""))
                if sk == subject_key:
                    real_name = str(t.get("theme_name", ""))
                    if t.get("event_chain"):
                        for e in t["event_chain"]:
                            if isinstance(e, dict) and e.get("description"):
                                events.append(str(e["description"])[:100])
                    if t.get("leader_stocks"):
                        for ls in t["leader_stocks"]:
                            if isinstance(ls, dict):
                                name = ls.get("stock_name", ls.get("stock_id", ""))
                                if name:
                                    leaders.append(str(name))
        except Exception:
            pass
        return events[:3], leaders[:5], real_name

    @staticmethod
    def _derive_bear_pool(
        fw_score: float, fc_score: float, leaders: list[str]
    ) -> list[str]:
        bear: list[str] = []
        if fw_score > 50:
            bear.append(f"退潮风险上升 (fade_watch={fw_score:.0f})")
        if fc_score > 40:
            bear.append(f"退潮确认信号 (fade_confirmed={fc_score:.0f})")
        if leaders:
            bear.append(f"关注龙头弱化: {leaders[0]}")
        if not bear:
            bear.append("未检测到显著空头信号 — 分析师补充")
        return bear

    @staticmethod
    def _derive_yesterday_view(state: str, ms: float, rep: float) -> str:
        if state == "repair":
            return f"昨日观点: 分歧后修复概率较高 (repair={rep:.0f})"
        elif state == "divergence":
            return f"昨日观点: 首次分歧需要缩量确认 (strength={ms:.0f})"
        else:
            return f"昨日观点: {_CYCLE_STATE_TO_PHASE.get(state, state)}"

    @staticmethod
    def _derive_today_actual(state: str, ms: float) -> str:
        if ms > 60:
            return f"今日实际: 主线强度维持 ({ms:.0f})，板块表现强于预期"
        elif ms > 45:
            return f"今日实际: 主线强度中等 ({ms:.0f})，符合预期"
        else:
            return f"今日实际: 主线强度偏弱 ({ms:.0f})，弱于预期"

    @staticmethod
    def _derive_tomorrow_view(state: str, fw: float, rep: float) -> str:
        if state == "repair" and rep > 60:
            return "隔日思考: 修复延续概率高，关注是否出现加速信号"
        elif state == "divergence" and fw < 40:
            return "隔日思考: 分歧缩量，关注是否转为修复"
        elif fw > 50:
            return "隔日思考: 退潮风险较高，谨慎观察"
        else:
            return "隔日思考: 等待方向确认，不急于操作"


def _empty_card(trade_date: date, subject_id: str) -> dict[str, Any]:
    return {
        "trade_date": trade_date.isoformat(),
        "subject_id": subject_id,
        "subject_name": subject_id,
        "ai_draft": False,
        "analyst_reviewed": False,
        "trading_style": "",
        "market_phase": "",
        "phase_raw": "",
        "event_stimuli": [],
        "current_leaders": [],
        "potential_leaders": [],
        "bull_pool": [],
        "bear_pool": [],
        "yesterday_view": "",
        "today_actual": "",
        "tomorrow_view": "",
        "analyst_notes": "",
        "analyst_overrides": {},
        "evidence_refs": [],
    }

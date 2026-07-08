"""P2.7 — Analyst Chart Reproduction Engine.

Orchestrates data loading → chart building → calibration.
Charts are built by individual builder modules under builders/.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .builders import market_power_chart, emotion_momentum_chart, relay_ecology_chart
from .builders import active_capital_chart

DB_DSN = "postgresql://localhost:5432/stock_data_test"

# PDF paths for analyst calibration
PDF_PATHS: dict[str, str] = {
    "2026-07-07": "/Users/admin/Desktop/7:7日复盘.pdf",
}

# ── Data source priority ──
# 1. market_environment_metrics (deterministic, up to May 2026)
# 2. post_market_recap_snapshot (for recent dates)
# 3. Analyst PDF calibration (authoritative override)
# 4. Estimates (last resort)


class ChartReproductionEngine:
    """Orchestrate chart generation with data source priority + calibration."""

    def run(self, trade_date: date) -> list[dict[str, Any]]:
        return asyncio.run(self._run_async(trade_date))

    async def run_async(self, trade_date: date) -> list[dict[str, Any]]:
        import asyncpg

        # ── Load PDF calibration data ──
        pdf_cal = await self._load_pdf_calibration(trade_date)

        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            recap = await self._load_recap(conn, trade_date)
            metrics = await self._load_metrics(conn, trade_date)

            # ── Extract raw data with priority ──
            data = self._extract_data(recap, metrics, pdf_cal)

            # ── Build charts using individual builders ──
            charts: list[dict[str, Any]] = []

            # Chart 1: Market Breadth
            charts.append(market_power_chart.build(
                up_count=data["up"], down_count=data["down"],
                limit_up=data["lu"], limit_down=data["ld"],
                turnover_yi=data["turnover_yi"],
                chain_board_count=data["chain_board"],
                calibrated_lu=pdf_cal.get("lu"),
                calibrated_turnover=pdf_cal.get("turnover"),
                calibrated_emotion=pdf_cal.get("emotion"),
            ))

            # Chart 2: Emotion Momentum
            charts.append(emotion_momentum_chart.build(
                first_board_red_ratio=data["first_red"],
                first_board_big_loss_ratio=data["first_loss"],
                chain_board_red_ratio=data["chain_red"],
                chain_board_ratio=data["chain_ratio"],
                chain_board_big_loss_ratio=data["chain_loss"],
                yesterday_chain_not_limit_red_ratio=data["yest_chain_red"],
                limit_up_count=data["lu"],
                chain_board_count=data["chain_board"],
            ))

            # Chart 3: Active Capital
            charts.append(active_capital_chart.build(
                total_amount_yi=data["turnover_yi"],
                active_amount_yi=data["active_amount"],
                limit_up_count=data["lu"],
            ))

            # Chart 4: Relay Ecology
            charts.append(await self._build_relay(trade_date, recap, conn, data))

            # Chart 5: Institution Style
            charts.append(self._build_institution(recap))

            # Chart 6: Hot Money
            charts.append(self._build_hot_money(recap, data["lu"]))

            # Chart 7: Limit-up Classification
            charts.append(self._build_limitup(recap, data["lu"]))

            # ── Apply PDF calibration to all charts ──
            if pdf_cal:
                for c in charts:
                    c["calibrated"] = True
                    c["calibration_source"] = "analyst_pdf"
                    c["source_priority"] = data.get("priority", "recap_snapshot")
                    if pdf_cal.get("emotion"):
                        c["data"]["pdf_emotion"] = pdf_cal["emotion"]

            return charts

        finally:
            await conn.close()

    async def run_trend_async(self, trade_date: date, days: int = 7) -> dict[str, Any]:
        """Generate multi-day trend data for line charts."""
        import asyncpg
        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            # Get last N trading days with recap data
            rows = await conn.fetch(
                "SELECT DISTINCT trade_date FROM post_market_recap_snapshot "
                "WHERE trade_date <= $1::date ORDER BY trade_date DESC LIMIT $2",
                trade_date, days,
            )
            dates = [r["trade_date"] for r in rows][::-1]  # oldest first

            trend = {
                "trade_date": trade_date.isoformat(),
                "dates": [d.isoformat() for d in dates],
                "breadth": [],
                "momentum": [],
                "capital": [],
                "relay": [],
            }

            for td in dates:
                recap = await self._load_recap(conn, td)
                if not recap:
                    continue
                overview = recap.get("market_overview_review", {})
                regime = recap.get("market_regime_review", {})

                up = int(overview.get("up_count", 0) or 0)
                down = int(overview.get("down_count", 0) or 0)
                lu = int(overview.get("limit_up_total", 0) or 0)
                ld = int(overview.get("limit_down_total", 0) or 0)
                amount = float(overview.get("total_amount", 0) or 0) / 10_000
                total = up + down or 1
                up_ratio = round(up / total, 3)

                # Breadth: composite score
                b_score = int((up_ratio - 0.5) * 200 + (lu - 50) * 0.5)

                # Momentum: estimated from up_ratio
                m_score = round(up_ratio * 100 - 50 + lu * 0.05, 1)

                # Capital: total in 万亿
                c_val = round(amount / 10_000, 1)

                # Relay: max board height estimate
                max_h = max(1, min(8, lu // 25))
                r_val = max_h

                trend["breadth"].append({"date": td.isoformat(), "up": up, "down": down, "limit_up": lu, "limit_down": ld, "score": b_score})
                trend["momentum"].append({"date": td.isoformat(), "score": m_score, "limit_up": lu})
                trend["capital"].append({"date": td.isoformat(), "amount": c_val, "limit_up": lu})
                trend["relay"].append({"date": td.isoformat(), "max_height": r_val, "limit_up": lu})

            return trend
        finally:
            await conn.close()

    def _apply_pdf_overrides(self, charts: list[dict], pdf_metrics: dict, pdf_text: str) -> None:
        """Override chart data with analyst-verified numbers from PDF."""
        for c in charts:
            ct = c["chart_type"]

            if ct == "market_breadth":
                if "limit_up_count" in pdf_metrics:
                    c["data"]["limit_up_count"] = pdf_metrics["limit_up_count"]
                if "turnover_wan_yi" in pdf_metrics:
                    c["data"]["turnover_yi"] = pdf_metrics["turnover_wan_yi"]
                # Recompute interpretation
                lu = c["data"]["limit_up_count"]
                c["interpretation"] = (
                    f"【分析师校准】涨停{lu}家（分析师PDF数据）。"
                    + c["interpretation"].split("。")[-1] if "。" in c["interpretation"] else ""
                )

            if "emotion_node_text" in pdf_metrics:
                c["data"]["pdf_emotion"] = pdf_metrics["emotion_node_text"]

            # Add PDF narrative reference
            if pdf_text:
                c["pdf_narrative"] = pdf_text[:200]

            # Mark PDF source
            c["source"] = "analyst_pdf_calibrated"

    # ── Data loaders + extraction ──

    async def _load_pdf_calibration(self, trade_date: date) -> dict[str, Any]:
        """Load analyst PDF calibration data if available."""
        date_str = trade_date.isoformat()
        if date_str not in PDF_PATHS:
            return {}
        path = Path(PDF_PATHS[date_str])
        if not path.exists():
            return {}
        try:
            from .pdf_parser import parse_analyst_pdf
            parsed = parse_analyst_pdf(str(path), trade_date)
            metrics = parsed.get("metrics", {})
            return {
                "lu": metrics.get("limit_up_count"),
                "turnover": metrics.get("turnover_wan_yi"),
                "emotion": metrics.get("emotion_node_text"),
                "risk": metrics.get("risk_signal"),
                "narrative": parsed.get("narrative", "")[:500],
            }
        except Exception:
            return {}

    def _extract_data(self, recap: dict, metrics: dict | None, pdf_cal: dict) -> dict[str, Any]:
        """Extract raw data with priority: metrics > recap > estimate."""
        overview = recap.get("market_overview_review", {})
        priority = "recap_snapshot"

        # Priority 1: metrics table
        if metrics:
            up = int(metrics.get("up_count", 0) or 0)
            down = int(metrics.get("down_count", 0) or 0)
            lu = int(metrics.get("limit_up_count", 0) or 0)
            ld = int(metrics.get("limit_down_count", 0) or 0)
            amount = float(metrics.get("market_total_amount", 0) or 0)
            amount_yi = amount / 100_000_000  # 元→亿
            first_red = float(metrics.get("yesterday_limit_up_open_red_ratio", 0) or 0)
            first_loss = float(metrics.get("yesterday_limit_up_fail_ratio", 0) or 0)
            chain_red = float(metrics.get("yesterday_limit_up_premium_ratio", 0) or 0) * 0.8
            chain_loss = first_loss * 0.6
            priority = "metrics_table"
        else:
            # Priority 2: recap snapshot
            up = int(overview.get("up_count", 0) or 0)
            down = int(overview.get("down_count", 0) or 0)
            lu = int(overview.get("limit_up_total", 0) or 0)
            ld = int(overview.get("limit_down_total", 0) or 0)
            raw_amount = float(overview.get("total_amount", 0) or 0)
            amount_yi = raw_amount / 10_000  # 万元→亿
            total = up + down or 1
            r = up / total
            first_red = min(0.8, r)
            first_loss = max(0.05, 1 - r - 0.3)
            chain_red = first_red * 0.8
            chain_loss = first_loss * 0.7

        # Priority 3: PDF calibration overrides
        if pdf_cal.get("lu"):
            lu = pdf_cal["lu"]
        if pdf_cal.get("turnover"):
            amount_yi = pdf_cal["turnover"] * 10_000  # 万亿→亿

        # Derived
        chain_board = max(1, lu // 15)
        chain_ratio = min(0.5, chain_board / max(lu, 1))
        yest_chain_red = 0.3
        active_amount = round(amount_yi * min(0.06, lu / 2000) / 10_000, 1)  # 亿→万亿

        return {
            "up": up, "down": down, "lu": lu, "ld": ld,
            "turnover_yi": round(amount_yi / 10_000, 1),  # 万亿
            "active_amount": active_amount,
            "chain_board": chain_board,
            "first_red": first_red, "first_loss": first_loss,
            "chain_red": chain_red, "chain_loss": chain_loss,
            "chain_ratio": chain_ratio, "yest_chain_red": yest_chain_red,
            "priority": priority,
        }

    # ── Builder methods (delegate to individual chart builders) ──

    async def _build_relay(self, td: date, recap: dict, conn, data: dict) -> dict[str, Any]:
        """Build relay ecology chart using LimitUpBoardRecalculator."""
        from stock_processing_service.application.services.limit_up_board_recalculator import (
            LimitUpBoardRecalculator,
        )
        try:
            recalc = LimitUpBoardRecalculator()
            enriched = await recalc.enrich_recap_doc(recap, td, conn)
            matrix = enriched.get("market_overview_review", {}).get("theme_limitup_matrix", {})
            columns = matrix.get("columns", []) if isinstance(matrix, dict) else []
            board_groups = []
            height_counts: dict[int, int] = {}
            for col in (columns or []):
                if isinstance(col, dict):
                    for bg in col.get("board_groups", []):
                        board_groups.append(bg)
                        h = bg.get("board_count", 0)
                        height_counts[h] = height_counts.get(h, 0) + bg.get("stock_count", 0)
            max_h = max(height_counts.keys()) if height_counts else 1
            t1 = height_counts.get(1, 0); t2 = height_counts.get(2, 0)
            t3 = height_counts.get(3, 0); t4 = height_counts.get(4, 0)
            p1to2 = round(t2 / max(t1, 1), 2)
            p2to3 = round(t3 / max(t2, 1), 2)
            p3to4 = round(t4 / max(t3, 1), 2)
            success = round(t1 / max(data["lu"], 1), 2)
            return relay_ecology_chart.build(max_h, success, p1to2, p2to3, p3to4, board_groups)
        except Exception:
            max_h = max(1, min(8, data["lu"] // 20))
            return relay_ecology_chart.build(max_h, 0.7,
                0.4 + (max_h - 3) * 0.08, 0.3 + (max_h - 3) * 0.06,
                0.2 + (max_h - 4) * 0.08)

    @staticmethod
    def _build_institution(recap: dict) -> dict[str, Any]:
        lifecycle = recap.get("mainline_lifecycle_reviews", [])
        regime = recap.get("market_regime_review", {})
        directions = []
        seen = set()
        for t in lifecycle:
            if not isinstance(t, dict): continue
            name = str(t.get("theme_name", t.get("subject_name", ""))).strip()
            if not name or name in seen: continue
            seen.add(name)
            state = str(t.get("cycle_state", "观察"))
            label = {"divergence":"调整中","repair":"修复中","fermentation":"启动观察","acceleration":"趋势向上","fade_watch":"退潮中","fade_confirmed":"退潮确认"}.get(state, "震荡")
            directions.append({"name": name, "state": label})
        mode = str(regime.get("trade_mode", "wait"))
        s_label = {"normal":"机构趋势主导","defense":"防御为主"}.get(mode, "等待观望")
        return {
            "chart_type": "institution_style", "title": "机构资金审美方向", "module": "style",
            "data": {"directions": directions[:12], "market_mode": mode, "label": s_label},
            "interpretation": f"机构资金风格：{s_label}。共{len(directions)}个方向。" + ("多数调整。" if s_label != "机构趋势主导" else "趋势确认。"),
        }

    @staticmethod
    def _build_hot_money(recap: dict, lu: int) -> dict[str, Any]:
        hotspots = recap.get("strong_hotspot_subjects", [])
        directions = []
        seen = set()
        for h in hotspots:
            if not isinstance(h, dict): continue
            sk = str(h.get("subject_key", ""))
            if sk in seen: continue
            seen.add(sk)
            name = str(h.get("theme_name", ""))
            cycle = str(h.get("cycle_state", ""))
            state = "游资关注" if "confirmed" in str(h.get("source", "")) else "观察中"
            directions.append({"name": name, "state": state, "cycle": cycle})
        h_label = "游资活跃" if lu > 80 else "游资正常" if lu > 40 else "游资退潮"
        return {
            "chart_type": "hot_money_style", "title": "游资情绪方向", "module": "style",
            "data": {"directions": directions[:12], "limit_up_count": lu, "label": h_label},
            "interpretation": f"游资：{h_label}（涨停{lu}家）。" + ("方向活跃。" if h_label == "游资活跃" else "新题材未成合力。"),
        }

    @staticmethod
    def _build_limitup(recap: dict, lu: int) -> dict[str, Any]:
        hotspots = recap.get("strong_hotspot_subjects", [])
        cats: dict[str, list] = {}
        for h in hotspots:
            if not isinstance(h, dict): continue
            name = str(h.get("theme_name", "")).strip()
            if not name or name.startswith("【"): continue
            source = str(h.get("source", "other"))
            cats.setdefault(source, []).append(name)
        return {
            "chart_type": "limitup_classification", "title": "涨停股分类", "module": "limitup",
            "data": {"limit_up_count": lu, "categories": {k: v[:5] for k, v in list(cats.items())[:5]}},
            "interpretation": f"涨停{lu}家。" + ("方向分散。" if lu < 60 else "主线明确。" if len(cats) <= 3 else "多线并行。"),
        }

    # ── Data loaders ──

    async def _load_recap(self, conn, trade_date: date) -> dict[str, Any]:
        row = await conn.fetchrow(
            "SELECT payload FROM post_market_recap_snapshot "
            "WHERE trade_date = $1::date ORDER BY created_at DESC LIMIT 1",
            trade_date,
        )
        if not row:
            return {}
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return payload.get("recap_doc", payload)

    async def _load_metrics(self, conn, trade_date: date) -> dict[str, Any] | None:
        row = await conn.fetchrow(
            "SELECT * FROM market_environment_metrics WHERE trade_date = $1::date LIMIT 1",
            trade_date,
        )
        return dict(row) if row else None

    # ── Chart builders ──

    def _chart_breadth(self, td: date, recap: dict, metrics: dict | None) -> dict[str, Any]:
        """Chart 1: Market Breadth (大盘势能) — PDF page 4."""
        overview = recap.get("market_overview_review", {})
        up = int(overview.get("up_count", 0) or 0)
        down = int(overview.get("down_count", 0) or 0)
        limit_up = int(overview.get("limit_up_total", 0) or 0)
        limit_down = int(overview.get("limit_down_total", 0) or 0)

        total = up + down or 1
        up_ratio = round(up / total, 3)
        minus_5 = int(down * 0.15)  # estimate if not available

        # Composite score
        def _z(v, mu, sigma):
            return (v - mu) / sigma if sigma > 0 else 0

        score = int(
            _z(limit_up, 80, 40) * 2
            + _z(limit_up * 0.3, 15, 8) * 2  # chain_board proxy
            - _z(minus_5, 200, 150) * 2
            + _z(up_ratio, 0.5, 0.15) * 2
            - _z(down / total, 0.4, 0.15) * 2
        )

        if score >= 6:
            label = "强势"
        elif score >= 2:
            label = "修复"
        elif score >= -1:
            label = "混沌"
        elif score >= -5:
            label = "分歧"
        else:
            label = "退潮/冰点"

        amount = float(overview.get("total_amount", 0) or 0) / 10_000  # 万元→亿

        return {
            "chart_id": f"breadth_{td.isoformat()}",
            "trade_date": td.isoformat(),
            "chart_type": "market_breadth",
            "title": "大盘势能",
            "module": "emotion",
            "data": {
                "limit_up_count": limit_up,
                "limit_down_count": limit_down,
                "up_count": up,
                "down_count": down,
                "up_ratio": up_ratio,
                "turnover_yi": round(amount / 10_000, 1),
                "composite_score": score,
                "label": label,
            },
            "interpretation": (
                f"涨停{limit_up}家，跌停{limit_down}家，上涨比{up_ratio:.1%}。"
                f"综合评分{score}，市场处于{label}状态。"
                + ("赚钱效应强。" if score >= 2 else "赚钱效应弱，亏钱效应扩散。" if score <= -2 else "")
            ),
        }

    def _chart_momentum(self, td: date, recap: dict, metrics: dict | None) -> dict[str, Any]:
        """Chart 2: Emotion Momentum (情绪动能) — PDF page 4-5."""
        if metrics:
            first_red = float(metrics.get("yesterday_limit_up_open_red_ratio", 0) or 0)
            first_fail = float(metrics.get("yesterday_limit_up_fail_ratio", 0) or 0)
            premium = float(metrics.get("yesterday_limit_up_premium_ratio", 0) or 0)
            fade = float(metrics.get("yesterday_limit_up_fade_ratio", 0) or 0)
            chain_red = first_red  # proxy
            chain_big_loss = first_fail * 0.5
            yesterday_chain_not_red = 0.3
        else:
            # Fallback: estimate from breadth
            overview = recap.get("market_overview_review", {})
            up = int(overview.get("up_count", 0) or 0)
            down = int(overview.get("down_count", 0) or 0)
            total = up + down or 1
            ratio = up / total
            first_red = min(0.8, ratio)
            first_fail = max(0.05, 1 - ratio - 0.3)
            premium = ratio * 0.6
            fade = max(0.05, 0.5 - ratio)
            chain_red = first_red * 0.8
            chain_big_loss = first_fail * 0.7
            yesterday_chain_not_red = 0.3

        # Composite momentum score (-18 to +10 scale, matching analyst chart)
        momentum = round(
            first_red * 2
            - first_fail * 2
            + chain_red * 2
            + min(1.0, first_red * 0.5) * 2  # chain_board_ratio proxy
            - chain_big_loss * 2
            + yesterday_chain_not_red * 1,
            1,
        )

        if momentum >= 5:
            m_label = "情绪高涨"
        elif momentum >= 0:
            m_label = "情绪正常"
        elif momentum >= -5:
            m_label = "情绪分歧"
        elif momentum >= -10:
            m_label = "情绪退潮"
        else:
            m_label = "情绪冰点"

        return {
            "chart_id": f"momentum_{td.isoformat()}",
            "trade_date": td.isoformat(),
            "chart_type": "emotion_momentum",
            "title": "情绪动能",
            "module": "emotion",
            "data": {
                "first_board_red_ratio": round(first_red, 2),
                "first_board_big_loss_ratio": round(first_fail, 2),
                "chain_board_red_ratio": round(chain_red, 2),
                "chain_big_loss_ratio": round(chain_big_loss, 2),
                "yesterday_chain_not_red_ratio": round(yesterday_chain_not_red, 2),
                "emotion_momentum_score": momentum,
                "label": m_label,
            },
            "interpretation": (
                f"首板红盘比{first_red:.0%}，大面比{first_fail:.0%}，"
                f"情绪动能{momentum:.1f}。{m_label}。"
                + ("短线情绪活跃，接力可做。" if momentum >= 0 else "情绪退潮，谨慎接力。")
            ),
        }

    def _chart_active_capital(self, td: date, recap: dict) -> dict[str, Any]:
        """Chart 3: Active Capital (活跃资金成交量) — PDF page 5."""
        overview = recap.get("market_overview_review", {})
        amount = float(overview.get("total_amount", 0) or 0)
        amount_yi = amount / 10_000  # 万元→亿
        amount_wan_yi = round(amount_yi / 10_000, 1)

        # Estimate active capital (涨停相关成交) as ~3-8% of total
        limit_up = int(overview.get("limit_up_total", 0) or 0)
        active_ratio = min(0.08, max(0.03, limit_up / 2000))
        active_amount = round(amount_yi * active_ratio / 10_000, 1)  # 万亿

        if active_amount > 1.5:
            c_label = "资金扩张"
        elif active_amount > 0.8:
            c_label = "资金正常"
        elif active_amount > 0.4:
            c_label = "资金收缩"
        else:
            c_label = "冰点低量"

        return {
            "chart_id": f"active_capital_{td.isoformat()}",
            "trade_date": td.isoformat(),
            "chart_type": "active_capital",
            "title": "活跃资金成交量",
            "module": "emotion",
            "data": {
                "total_amount_wan_yi": amount_wan_yi,
                "active_amount_wan_yi": active_amount,
                "limit_up_count": limit_up,
                "label": c_label,
            },
            "interpretation": (
                f"全市场成交额{amount_wan_yi}万亿，活跃资金约{active_amount}万亿。"
                + ("短线资金充裕。" if active_amount > 0.8 else "短线资金收缩。")
            ),
        }

    async def _chart_relay_ecology_async(self, td: date, recap: dict, conn) -> dict[str, Any]:
        """Chart 4: Relay Ecology (核心板块节律) — uses LimitUpBoardRecalculator."""
        from stock_processing_service.application.services.limit_up_board_recalculator import (
            LimitUpBoardRecalculator,
        )

        overview = recap.get("market_overview_review", {})
        limit_up = int(overview.get("limit_up_total", 0) or 0)

        # Use the existing chain board module to enrich recap data
        try:
            recalc = LimitUpBoardRecalculator()
            enriched = await recalc.enrich_recap_doc(recap, td, conn)
            matrix = enriched.get("market_overview_review", {}).get("theme_limitup_matrix", {})
            columns = matrix.get("columns", []) if isinstance(matrix, dict) else []

            # Collect board groups from enriched data
            board_groups: list[dict] = []
            for col in (columns or []):
                if isinstance(col, dict):
                    for bg in col.get("board_groups", []):
                        board_groups.append(bg)

            # Compute max height and promotion rates from board groups
            height_counts: dict[int, int] = {}
            for bg in board_groups:
                h = bg.get("board_count", 0)
                height_counts[h] = height_counts.get(h, 0) + bg.get("stock_count", 0)

            max_height = max(height_counts.keys()) if height_counts else 1
            total_1board = height_counts.get(1, 0)
            total_2board = height_counts.get(2, 0)
            total_3board = height_counts.get(3, 0)
            total_4board = height_counts.get(4, 0)

            p1to2 = round(total_2board / max(total_1board, 1), 2)
            p2to3 = round(total_3board / max(total_2board, 1), 2)
            p3to4 = round(total_4board / max(total_3board, 1), 2)
            first_board_success = round(total_1board / max(limit_up, 1), 2)

            # Log
            ladder_ctx = enriched.get("limit_up_ladder_context", {})
            print(f"Board recalc: {ladder_ctx.get('tracked_stock_count',0)} stocks, "
                  f"heights={height_counts}, 1→2={p1to2:.0%}, 2→3={p2to3:.0%}, 3→4={p3to4:.0%}")
        except Exception as e:
            print(f"Board recalc failed: {e}, using estimates")
            max_height = max(1, min(8, limit_up // 20))
            success_rate = min(0.95, max(0.3, 0.7 - (limit_up - 100) * 0.002))
            p1to2 = round(min(0.8, max(0.1, 0.4 + (max_height - 3) * 0.08)), 2)
            p2to3 = round(min(0.7, max(0.05, 0.3 + (max_height - 3) * 0.06)), 2)
            p3to4 = round(min(0.6, max(0.0, 0.2 + (max_height - 4) * 0.08)), 2)

        if max_height >= 5 and p1to2 > 0.4:
            r_label = "接力活跃"
        elif max_height >= 3:
            r_label = "接力正常"
        elif max_height >= 2:
            r_label = "接力退潮"
        else:
            r_label = "高度压制"

        return {
            "chart_id": f"relay_{td.isoformat()}",
            "trade_date": td.isoformat(),
            "chart_type": "relay_ecology",
            "title": "核心板块节律",
            "module": "emotion",
            "data": {
                "max_board_height": max_height,
                "first_board_success_rate": round(success_rate, 2),
                "promotion_1_to_2": p1to2,
                "promotion_2_to_3": p2to3,
                "promotion_3_to_4": p3to4,
                "label": r_label,
            },
            "interpretation": (
                f"最高板{max_height}，一进二{p1to2:.0%}，二进三{p2to3:.0%}，三进四{p3to4:.0%}。"
                + ("接力生态活跃，高度打开。" if r_label == "接力活跃"
                   else "接力退潮，高度压制，谨慎打高位。" if r_label in ("接力退潮", "高度压制")
                   else "接力正常。")
            ),
        }

    def _chart_institution_style(self, td: date, recap: dict) -> dict[str, Any]:
        """Chart 5: Institution Style (机构资金审美方向) — PDF page 7."""
        # Use mainline_lifecycle_reviews + theme_reviews for real institution data
        lifecycle_reviews = recap.get("mainline_lifecycle_reviews", [])
        theme_reviews = recap.get("theme_reviews", [])
        regime = recap.get("market_regime_review", {})

        directions: list[dict[str, Any]] = []
        seen_names = set()
        # First from lifecycle_reviews (has richer state data)
        for t in lifecycle_reviews:
            if not isinstance(t, dict):
                continue
            name = str(t.get("theme_name", t.get("subject_name", ""))).strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            state = str(t.get("cycle_state", t.get("state", "观察")))
            d_state = self._inst_state_label(state)
            if len(directions) < 12:
                directions.append({"name": name, "state": d_state})

        # Supplement from theme_reviews
        for t in theme_reviews:
            name = str(t.get("theme_name", "")).strip()
            if not name or name.startswith("【") or name in seen_names:
                continue
            seen_names.add(name)
            ms = float(t.get("mainline_strength_score", 50))
            fc = str(t.get("final_cycle_state", ""))
            d_state = self._inst_state_label(fc, ms)
            if len(directions) < 15:
                directions.append({"name": name, "state": d_state, "score": round(ms, 1)})

        market_mode = str(regime.get("trade_mode", "wait"))
        if market_mode == "normal":
            s_label = "机构趋势主导"
        elif market_mode == "defense":
            s_label = "防御为主"
        else:
            s_label = "等待观望"

        return {
            "chart_id": f"inst_style_{td.isoformat()}",
            "trade_date": td.isoformat(),
            "chart_type": "institution_style",
            "title": "机构资金审美方向",
            "module": "emotion",
            "data": {
                "directions": directions,
                "market_mode": market_mode,
                "label": s_label,
            },
            "interpretation": (
                f"机构资金风格：{s_label}（{market_mode}）。"
                + f"共跟踪{len(directions)}个方向。"
                + ("多数方向仍在调整。" if s_label != "机构趋势主导" else "趋势方向确认。")
            ),
        }

    @staticmethod
    def _inst_state_label(cycle_state: str, ms: float = 50) -> str:
        if cycle_state in ("divergence", "分歧"):
            return "调整中" if ms < 50 else "高位分歧"
        elif cycle_state in ("repair", "修复"):
            return "修复中"
        elif cycle_state in ("fermentation", "start", "启动", "发酵"):
            return "启动观察"
        elif cycle_state in ("acceleration", "加速", "高潮"):
            return "趋势向上"
        elif cycle_state in ("fade_watch", "退潮观察"):
            return "退潮中"
        elif cycle_state in ("fade_confirmed", "退潮确认"):
            return "退潮确认"
        return "震荡"

    def _chart_hot_money(self, td: date, recap: dict) -> dict[str, Any]:
        """Chart 6: Hot Money Direction (游资方向) — PDF page 8-9."""
        # Use strong_hotspot_subjects + mainline_hotspots for real hot money data
        strong_hotspots = recap.get("strong_hotspot_subjects", [])
        mainline_hotspots = recap.get("mainline_hotspots", [])
        overview = recap.get("market_overview_review", {})
        limit_up = int(overview.get("limit_up_total", 0) or 0)

        hot_directions: list[dict[str, Any]] = []
        seen = set()
        # Use strong_hotspot_subjects first (has proper theme names)
        for h in strong_hotspots:
            if not isinstance(h, dict):
                continue
            name = str(h.get("theme_name", "")).strip()
            sk = str(h.get("subject_key", ""))
            if not name or name.startswith("【") or sk in seen:
                continue
            seen.add(sk)
            cycle = str(h.get("cycle_state", ""))
            source = str(h.get("source", ""))

            if "mainline" in source:
                state = "游资关注" if cycle == "confirmed" else "观察中"
            else:
                state = "方向跟踪"

            if len(hot_directions) < 12:
                hot_directions.append({"name": name, "state": state, "cycle": cycle})

        # Fallback to mainline_hotspots
        if not hot_directions:
            for h in mainline_hotspots:
                if not isinstance(h, dict):
                    continue
                sk = str(h.get("subject_key", ""))
                if sk in seen:
                    continue
                seen.add(sk)
                name = str(h.get("theme_name", sk))
                if len(hot_directions) < 12:
                    hot_directions.append({"name": name, "state": "观察中"})

        if limit_up > 80:
            h_label = "游资活跃"
        elif limit_up > 40:
            h_label = "游资正常"
        else:
            h_label = "游资退潮"

        return {
            "chart_id": f"hot_money_{td.isoformat()}",
            "trade_date": td.isoformat(),
            "chart_type": "hot_money_style",
            "title": "游资情绪方向",
            "module": "emotion",
            "data": {
                "directions": hot_directions,
                "limit_up_count": limit_up,
                "label": h_label,
            },
            "interpretation": (
                f"游资风格：{h_label}（涨停{limit_up}家）。"
                + ("短线方向活跃。" if h_label == "游资活跃" else "游资退潮，新题材未形成合力。")
            ),
        }

    def _chart_limitup_classification(self, td: date, recap: dict) -> dict[str, Any]:
        """Chart 7: Limit-up Classification (涨停分类) — PDF page 10."""
        overview = recap.get("market_overview_review", {})
        theme_reviews = recap.get("theme_reviews", [])
        strong_hotspots = recap.get("strong_hotspot_subjects", [])

        categories: dict[str, list[str]] = {}
        for h in strong_hotspots:
            if not isinstance(h, dict):
                continue
            name = str(h.get("theme_name", "")).strip()
            if not name or name.startswith("【"):
                continue
            # Group by category (simple: use first 2 chars as proxy, or use source)
            source = str(h.get("source", "other"))
            if source not in categories:
                categories[source] = []
            if len(categories[source]) < 5:
                categories[source].append(name)

        top_stocks: list[dict[str, str]] = []
        # Extract from theme_reviews leader_stocks
        for t in theme_reviews[:10]:
            ls = t.get("leader_stocks", [])
            if isinstance(ls, list):
                for s in ls[:2]:
                    if isinstance(s, dict):
                        top_stocks.append({
                            "name": str(s.get("stock_name", s.get("stock_id", ""))),
                            "theme": str(t.get("theme_name", "")),
                            "role": "龙头" if ls.index(s) == 0 else "助攻",
                        })
            if len(top_stocks) >= 10:
                break

        limit_up = int(overview.get("limit_up_total", 0) or 0)

        return {
            "chart_id": f"limitup_{td.isoformat()}",
            "trade_date": td.isoformat(),
            "chart_type": "limitup_classification",
            "title": "涨停股分类",
            "module": "cognition",
            "data": {
                "limit_up_count": limit_up,
                "categories": {k: v[:5] for k, v in list(categories.items())[:5]},
                "top_stocks": top_stocks[:15],
            },
            "interpretation": (
                f"今日涨停{limit_up}家。"
                + ("涨停方向分散，无明确主线。" if limit_up < 60
                   else "涨停方向集中，主线明确。" if len(categories) <= 3
                   else "涨停方向较多，多线并行。")
            ),
        }

"""P2.7 — Analyst Chart Reproduction Engine.

Orchestrates chart building from MarketMetricsSnapshot (canonical facts).
Charts 1-4 are built from snapshot metrics.
Charts 5-7 use thematic/narrative data from recap.

Key principle: This engine NEVER connects to DB.
All data arrives pre-loaded via MarketMetricsSnapshot + optional recap dict.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .builders import market_power_chart, emotion_momentum_chart, relay_ecology_chart
from .builders import active_capital_chart

# PDF paths for analyst calibration
PDF_PATHS: dict[str, str] = {
    "2026-07-07": "/Users/admin/Desktop/7:7日复盘.pdf",
}


class ChartReproductionEngine:
    """Build analyst charts from canonical metrics.

    All data arrives from outside — zero DB connections.
    """

    def build(self, snapshot: Any, recap: dict[str, Any] | None = None,
              pdf_cal: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Build all 7 charts from a MarketMetricsSnapshot.

        Args:
            snapshot: MarketMetricsSnapshot from MarketMetricsService
            recap: pre-loaded recap payload (for thematic charts 5-7)
            pdf_cal: pre-loaded PDF calibration dict
        """
        b = snapshot.breadth
        l = snapshot.limitup
        c = snapshot.capital
        m = snapshot.emotion_momentum
        r = snapshot.relay

        # ── Load PDF calibration ──
        pdf_cal = pdf_cal or {}
        calibrated_lu = pdf_cal.get("lu")
        calibrated_turnover = pdf_cal.get("turnover")
        calibrated_emotion = pdf_cal.get("emotion")

        charts: list[dict[str, Any]] = []

        # ── Chart 1: Market Breadth (大盘势能) ──
        # PDF turnover is wan_yi (万亿); convert to yi (亿) for builder
        calibrated_turnover_yi = round(calibrated_turnover * 10_000) if calibrated_turnover else None
        charts.append(market_power_chart.build(
            up_count=b.up_count, down_count=b.down_count,
            limit_up=b.limit_up_count, limit_down=b.limit_down_count,
            turnover_yi=b.turnover_yi,
            chain_board_count=l.chain_board_count,
            calibrated_lu=calibrated_lu,
            calibrated_turnover=calibrated_turnover_yi,
            calibrated_emotion=calibrated_emotion,
        ))

        # ── Chart 2: Emotion Momentum (情绪动能) ──
        charts.append(emotion_momentum_chart.build(
            first_board_red_ratio=m.first_board_red_ratio,
            first_board_big_loss_ratio=m.first_board_big_loss_ratio,
            chain_board_red_ratio=m.chain_board_red_ratio,
            chain_board_ratio=m.chain_board_ratio,
            chain_board_big_loss_ratio=m.chain_board_big_loss_ratio,
            yesterday_chain_not_limit_red_ratio=m.yesterday_chain_not_limit_red_ratio,
            limit_up_count=b.limit_up_count,
            chain_board_count=l.chain_board_count,
            momentum_raw=m.momentum_raw,  # v3 relay-based formula
        ))

        # ── Chart 3: Active Capital (活跃资金) ──
        # Internal unit 亿 → builders receive 亿 values
        charts.append(active_capital_chart.build(
            total_amount_yi=c.total_turnover_yi,
            active_amount_yi=c.active_limitup_amount_yi,
            limit_up_count=b.limit_up_count,
        ))

        # ── Chart 4: Relay Ecology (核心板块节律) ──
        charts.append(relay_ecology_chart.build(
            max_board_height=r.max_board_height,
            first_board_success_rate=l.first_board_success_rate,
            promotion_1_to_2=r.promotion_1_to_2,
            promotion_2_to_3=r.promotion_2_to_3,
            promotion_3_to_4=r.promotion_3_to_4,
            feedback_score=r.feedback_score,
            feedback_label=r.feedback_label,
            continue_ratio=r.continue_ratio,
            yesterday_count=r.yesterday_limitup_count,
            big_loss_count=r.yesterday_big_loss_count,
            board_groups=[],  # thematic detail, not in snapshot
        ))

        # ── Charts 5-7: Thematic / narrative charts ──
        recap = recap or {}
        charts.append(self._build_institution(recap))
        charts.append(self._build_hot_money(recap, b.limit_up_count))
        charts.append(self._build_limitup(recap, b.limit_up_count))

        # ── Apply PDF calibration marker ──
        if pdf_cal:
            for c in charts:
                c["calibrated"] = True
                c["calibration_source"] = "analyst_pdf"
                if calibrated_emotion:
                    c.setdefault("data", {})["pdf_emotion"] = calibrated_emotion

        return charts

    # ── Trend ──

    @staticmethod
    def build_trend(snapshots: list[Any]) -> dict[str, Any]:
        """Build multi-day trend data from MarketMetricsSnapshot list.

        Args:
            snapshots: list of MarketMetricsSnapshot, oldest first
        """
        dates = [s.trade_date.isoformat() for s in snapshots]
        if not dates:
            return {"dates": [], "breadth": [], "momentum": [], "capital": [], "relay": []}

        trend = {
            "trade_date": dates[-1],
            "dates": dates,
            "breadth": [],
            "momentum": [],
            "capital": [],
            "relay": [],
        }

        for s in snapshots:
            b = s.breadth
            l = s.limitup
            c = s.capital
            m = s.emotion_momentum
            r = s.relay

            # Breadth: composite score
            up_ratio = b.up_ratio
            b_score = int((up_ratio - 0.5) * 200 + (b.limit_up_count - 50) * 0.5)

            trend["breadth"].append({
                "date": s.trade_date.isoformat(),
                "up": b.up_count, "down": b.down_count,
                "limit_up": b.limit_up_count, "limit_down": b.limit_down_count,
                "score": b_score,
            })
            trend["momentum"].append({
                "date": s.trade_date.isoformat(),
                "score": m.momentum_raw,
                "limit_up": b.limit_up_count,
            })
            trend["capital"].append({
                "date": s.trade_date.isoformat(),
                # 亿 → 万亿 for display
                "amount": round(c.total_turnover_yi / 10_000, 1),
                "limit_up": b.limit_up_count,
            })
            trend["relay"].append({
                "date": s.trade_date.isoformat(),
                "max_height": r.max_board_height,
                "promotion_1_to_2": r.promotion_1_to_2,
                "feedback_score": r.feedback_score,
                "feedback_label": r.feedback_label,
                "continue_ratio": r.continue_ratio,
                "limit_up": b.limit_up_count,
            })

        return trend

    # ── Thematic charts (data from recap) ──

    @staticmethod
    def _build_institution(recap: dict) -> dict[str, Any]:
        lifecycle = recap.get("mainline_lifecycle_reviews", [])
        theme_reviews = recap.get("theme_reviews", [])
        regime = recap.get("market_regime_review", {})
        directions, seen = [], set()
        for source in [lifecycle, theme_reviews]:
            for t in (source if isinstance(source, list) else []):
                if not isinstance(t, dict):
                    continue
                name = str(t.get("theme_name", t.get("subject_name", ""))).strip()
                if not name or name.startswith("【") or name in seen:
                    continue
                seen.add(name)
                state = str(t.get("cycle_state", t.get("final_cycle_state", t.get("theme_stage", "观察"))))
                ms = float(t.get("mainline_strength_score", 50))
                label = {"divergence": "调整中" if ms < 50 else "高位分歧", "repair": "修复中",
                         "fermentation": "启动观察", "start": "启动观察",
                         "acceleration": "趋势向上", "fade_watch": "退潮中",
                         "fade_confirmed": "退潮确认"}.get(state, "震荡")
                directions.append({"name": name, "state": label, "score": round(ms, 1)})
        mode = str(regime.get("trade_mode", "wait"))
        s_label = {"normal": "机构趋势主导", "defense": "防御为主"}.get(mode, "等待观望")
        return {
            "chart_type": "institution_style", "title": "机构资金审美方向", "module": "style",
            "data": {"directions": directions[:15], "market_mode": mode, "label": s_label},
            "interpretation": f"机构资金风格：{s_label}。共{len(directions)}个方向。" + ("多数调整。" if s_label != "机构趋势主导" else "趋势确认。"),
        }

    @staticmethod
    def _build_hot_money(recap: dict, lu: int) -> dict[str, Any]:
        hotspots = recap.get("strong_hotspot_subjects", [])
        directions = []
        seen = set()
        for h in hotspots:
            if not isinstance(h, dict):
                continue
            sk = str(h.get("subject_key", ""))
            if sk in seen:
                continue
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
            if not isinstance(h, dict):
                continue
            name = str(h.get("theme_name", "")).strip()
            if not name or name.startswith("【"):
                continue
            source = str(h.get("source", "other"))
            cats.setdefault(source, []).append(name)
        return {
            "chart_type": "limitup_classification", "title": "涨停股分类", "module": "limitup",
            "data": {"limit_up_count": lu, "categories": {k: v[:5] for k, v in list(cats.items())[:5]}},
            "interpretation": f"涨停{lu}家。" + ("方向分散。" if lu < 60 else "主线明确。" if len(cats) <= 3 else "多线并行。"),
        }

    # ── PDF calibration loader (no DB, file only) ──

    @staticmethod
    def load_pdf_calibration(trade_date: date) -> dict[str, Any]:
        """Load analyst PDF calibration data if available. Pure file I/O, no DB."""
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

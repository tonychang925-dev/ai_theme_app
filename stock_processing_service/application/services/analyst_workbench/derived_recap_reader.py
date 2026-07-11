"""DerivedRecapDocReader — builds recap_doc-compatible dict from derived tables.

Used when post_market_recap_snapshot is unavailable (clean replay).
This service reads from the derived data tables populated by Workbench
generate and produces the fields needed by PostMarketDailyReviewV2Builder
and PostMarketEngineReportComposer.

All DB access goes through the app connection pool. No raw connections.
"""

from __future__ import annotations

import json as _json
from datetime import date
from typing import Any


class DerivedRecapDocReader:
    """Read derived tables and build recap_doc-compatible dict."""

    def __init__(self, pool: Any):
        self._pool = pool

    async def read(self, trade_date: date) -> dict[str, Any]:
        """Build recap_doc from derived tables via the app pool.

        Returns a dict with the same shape the builder and engine composer
        expect from post_market_recap_snapshot.payload.recap_doc.
        """
        td = trade_date.isoformat()
        recap: dict[str, Any] = {"trade_date": td, "source": "derived_tables"}

        async with self._pool.acquire() as conn:
            # ── Resolve theme_name map (subject_key → Chinese display name) ──
            name_map = await self._build_name_map(conn)

            # ── theme_reviews ──
            rows = await conn.fetch("""
                SELECT subject_key, theme_name,
                       final_cycle_state AS cycle_state,
                       mainline_strength_score,
                       COALESCE(fade_risk_score, 0) AS fade_risk_score
                FROM theme_cycle_judgement_v2
                WHERE trade_date = $1
                ORDER BY mainline_strength_score DESC NULLS LAST
                LIMIT 20
            """, trade_date)
            theme_reviews = []
            for r in rows:
                item = dict(r)
                sk = str(item.get("subject_key", ""))
                item["theme_name"] = name_map.get(sk) or item.get("theme_name") or sk
                theme_reviews.append(item)
            recap["theme_reviews"] = theme_reviews

            # ── strong_hotspot_subjects ──
            recap["strong_hotspot_subjects"] = [
                {"subject_key": tr["subject_key"], "theme_name": tr["theme_name"],
                 "cycle_state": tr["cycle_state"], "source": "derived"}
                for tr in theme_reviews
            ]

            # ── theme_capital_reviews ──
            cap_rows = await conn.fetch("""
                SELECT subject_key,
                       SUM(COALESCE(main_net_inflow, 0)) AS total_inflow,
                       COUNT(*) AS inflow_stock_count
                FROM money_flow_enhanced
                WHERE trade_date = $1 AND subject_key IS NOT NULL
                GROUP BY subject_key
                ORDER BY total_inflow DESC NULLS LAST
                LIMIT 15
            """, trade_date)
            recap["theme_capital_reviews"] = [dict(r) for r in cap_rows]

            # ── strong_stock_reviews ──
            stock_rows = await conn.fetch("""
                SELECT stock_id, stock_name, subject_key, theme_name,
                       watch_score AS composite_score,
                       relay_role AS role,
                       support_score AS structure_score,
                       watch_score AS capital_score
                FROM strong_stock_watch_history
                WHERE trade_date = $1
                ORDER BY watch_score DESC NULLS LAST
                LIMIT 50
            """, trade_date)
            recap["strong_stock_reviews"] = [dict(r) for r in stock_rows]

            # ── limit_up_ladder ──
            lu_rows = await conn.fetch("""
                SELECT stock_code AS stock_id, stock_name, reason_tags
                FROM ths_hot_reason_snapshot
                WHERE trade_date = $1
                LIMIT 75
            """, trade_date)
            if lu_rows:
                recap["limit_up_ladder"] = self._build_ladder([dict(r) for r in lu_rows])

            # ── seat_money_summary ──
            dt_rows = await conn.fetch("""
                SELECT stock_id, stock_name,
                       institution_seat_count, institution_net_buy,
                       seat_summary
                FROM dragon_tiger_object
                WHERE trade_date = $1
                LIMIT 20
            """, trade_date)
            if dt_rows:
                recap["seat_money_summary"] = self._build_seat_summary([dict(r) for r in dt_rows])

            # ── market_regime_review ──
            recap["market_regime_review"] = {"trade_mode": "normal", "allow_trade": True}

        return recap

    # ── helpers ──

    async def _build_name_map(self, conn) -> dict[str, str]:
        """Resolve subject_key → Chinese display name from all available sources."""
        name_map: dict[str, str] = {}

        # Source A: theme_cycle_judgement_v2 (cross-date)
        rows = await conn.fetch("""
            SELECT DISTINCT ON (subject_key) subject_key, theme_name
            FROM theme_cycle_judgement_v2
            WHERE theme_name IS NOT NULL
              AND theme_name != subject_key
              AND theme_name !~ '^[0-9]+$'
            ORDER BY subject_key, trade_date DESC
        """)
        for r in rows:
            sk, tn = str(r["subject_key"]), str(r["theme_name"])
            if tn and tn != sk and tn not in name_map.values():
                name_map[sk] = tn

        # Source B: strong_stock_watch_history (fallback)
        rows = await conn.fetch("""
            SELECT DISTINCT ON (subject_key) subject_key, theme_name
            FROM strong_stock_watch_history
            WHERE theme_name IS NOT NULL AND theme_name != subject_key
            ORDER BY subject_key, trade_date DESC
        """)
        for r in rows:
            sk = str(r["subject_key"])
            if sk not in name_map:
                tn = str(r["theme_name"])
                if tn and tn != sk:
                    name_map[sk] = tn

        return name_map

    @staticmethod
    def _build_ladder(rows: list[dict]) -> dict[str, Any]:
        theme_map: dict[str, list] = {}
        for r in rows:
            tags = r.get("reason_tags")
            if isinstance(tags, str):
                try: tags = _json.loads(tags)
                except Exception: tags = [tags] if tags else []
            if isinstance(tags, list):
                for tag in tags:
                    tn = str(tag).strip().strip('"').strip("'")
                    if tn: theme_map.setdefault(tn, []).append(r)

        theme_rows = [
            {"theme_name": tn, "limit_up_count": len(stocks),
             "representative_stocks": [{"stock_name": s.get("stock_name", "")} for s in stocks[:3]]}
            for tn, stocks in sorted(theme_map.items(), key=lambda x: -len(x[1]))
        ]
        return {
            "summary": f"涨停{len(rows)}家，{len(theme_rows)}个方向",
            "board_rows": [],
            "theme_rows": theme_rows[:15],
        }

    @staticmethod
    def _build_seat_summary(rows: list[dict]) -> dict[str, Any]:
        institution_rows: list[dict] = []
        hot_money_rows: list[dict] = []
        for r in rows:
            inst = r.get("institution_seat_count", 0) or 0
            if inst > 0:
                institution_rows.append({
                    "stock_name": r.get("stock_name", ""),
                    "net_buy": r.get("institution_net_buy"),
                    "institution_seat_count": inst,
                })
            seat_raw = r.get("seat_summary")
            if isinstance(seat_raw, str):
                try: seat_raw = _json.loads(seat_raw)
                except Exception: seat_raw = None
            if isinstance(seat_raw, list):
                for seat in seat_raw:
                    if isinstance(seat, dict):
                        hm = seat.get("name") or seat.get("hot_money_name") or ""
                        if hm:
                            hot_money_rows.append({
                                "stock_name": r.get("stock_name", ""),
                                "hot_money_name": str(hm),
                            })
        return {
            "institution_buy_rows": institution_rows[:10],
            "hot_money_buy_rows": hot_money_rows[:10],
        }

from __future__ import annotations

from copy import deepcopy
from typing import Any


class LimitUpBoardRecalculator:
    """Recompute limit-up board counts from daily snapshots.

    This service materializes the board-count inputs required by the new
    DailyReview V2 layout without falling back to section-text parsing.
    """

    async def enrich_recap_doc(self, recap_doc: dict[str, Any], trade_date, conn) -> dict[str, Any]:
        source = deepcopy(recap_doc) if isinstance(recap_doc, dict) else {}
        enriched = deepcopy(source)
        targets = self._collect_stock_targets(enriched)
        if not targets:
            return enriched

        stock_ids = []
        for target in targets:
            sid = target["stock_key"]
            if sid and sid not in stock_ids:
                stock_ids.append(sid)

        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (split_part(stock_id, '.', 1), trade_date)
                split_part(stock_id, '.', 1) AS stock_key,
                trade_date,
                pct_chg
            FROM stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date >= $1::date - INTERVAL '10 days'
              AND split_part(stock_id, '.', 1) = ANY($2::text[])
              AND source_name LIKE 'tushare%'
            ORDER BY split_part(stock_id, '.', 1), trade_date DESC, source_name DESC
            """,
            trade_date,
            stock_ids,
        )

        by_stock: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            sid = self._text(row.get("stock_key") or row.get("stock_id"))
            if not sid:
                continue
            by_stock.setdefault(sid, []).append({
                "trade_date": row.get("trade_date"),
                "pct_chg": self._float(row.get("pct_chg")),
            })

        board_map: dict[str, int] = {}
        for stock_id, series in by_stock.items():
            series.sort(key=lambda item: item.get("trade_date"), reverse=True)
            board_count = self._recompute_board_count(series, trade_date)
            if board_count > 0:
                board_map[stock_id] = board_count

        if not board_map:
            return source

        update_counters: dict[str, int] = {}
        for target in targets:
            stock = target["stock"]
            stock_key = target["stock_key"]
            board_count = board_map.get(stock_key)
            if not board_count:
                continue
            stock["board_count"] = board_count
            stock["limit_up_days"] = board_count
            stock["max_consecutive_limit_up_days"] = board_count
            source_name = target["source"]
            update_counters[source_name] = update_counters.get(source_name, 0) + 1

        self._rebuild_market_overview_board_groups(enriched)

        print(
            "limit_up board recompute diagnostics:",
            f"targets={len(targets)}",
            f"board_map={len(board_map)}",
            f"updated={sum(update_counters.values())}",
            f"by_source={update_counters}",
        )

        enriched["limit_up_ladder_context"] = {
            "source": "recomputed_from_stock_daily_snapshot",
            "trade_date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
            "tracked_stock_count": len(stock_ids),
            "board_count_stock_count": len(board_map),
            "updated_focus_stock_count": sum(update_counters.values()),
            "updated_by_source": update_counters,
        }
        return enriched

    @staticmethod
    def _recompute_board_count(series: list[dict[str, Any]], trade_date) -> int:
        if not series:
            return 0

        target_pct = series[0].get("pct_chg")
        if target_pct is None or target_pct < 9.5:
            return 0

        streak = 0
        for idx, row in enumerate(series):
            pct = row.get("pct_chg")
            if pct is None or pct < 9.5:
                break
            streak += 1
            if idx == 0:
                continue
        return min(streak, 4)

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    def _collect_stock_targets(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_target(stock: dict[str, Any], source_name: str) -> None:
            stock_key = self._normalize_stock_key(
                self._first_text(stock, "stock_id", "stock_code", "stock_key")
            )
            if not stock_key:
                return
            stock_name = self._text(stock.get("stock_name"))
            dedupe_key = (source_name, stock_key if stock_name else stock_key)
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            targets.append({
                "source": source_name,
                "stock_key": stock_key,
                "stock": stock,
            })

        market_overview = self._dict(source.get("market_overview_review"))
        matrix = market_overview.get("theme_limitup_matrix")
        if isinstance(matrix, dict):
            for col in matrix.get("columns") or []:
                if not isinstance(col, dict):
                    continue
                for stock in col.get("focus_stocks") or []:
                    if isinstance(stock, dict):
                        add_target(stock, "market_overview_review.theme_limitup_matrix.columns.focus_stocks")

        report_context = source.get("report_context")
        if isinstance(report_context, dict):
            for stock in report_context.get("stock_facts") or []:
                if isinstance(stock, dict):
                    add_target(stock, "report_context.stock_facts")

        strong_rows = source.get("strong_stock_reviews")
        if isinstance(strong_rows, list):
            for stock in strong_rows:
                if isinstance(stock, dict):
                    add_target(stock, "strong_stock_reviews")

        decision = self._dict(source.get("post_market_decision_v2"))
        pool_rows = decision.get("strong_stock_pool_reviews")
        if isinstance(pool_rows, list):
            for stock in pool_rows:
                if isinstance(stock, dict):
                    add_target(stock, "post_market_decision_v2.strong_stock_pool_reviews")

        return targets

    def _rebuild_market_overview_board_groups(self, source: dict[str, Any]) -> None:
        report_context = source.get("report_context")
        if not isinstance(report_context, dict):
            return
        stock_facts = report_context.get("stock_facts")
        if not isinstance(stock_facts, list) or not stock_facts:
            return

        market_overview = source.get("market_overview_review")
        if not isinstance(market_overview, dict):
            return
        matrix = market_overview.get("theme_limitup_matrix")
        if not isinstance(matrix, dict):
            return
        columns = matrix.get("columns")
        if not isinstance(columns, list) or not columns:
            return

        facts_by_subject: dict[str, list[dict[str, Any]]] = {}
        facts_by_theme: dict[str, list[dict[str, Any]]] = {}
        for item in stock_facts:
            if not isinstance(item, dict):
                continue
            subject_key = self._text(item.get("subject_key"))
            theme_name = self._text(item.get("theme_name"))
            if subject_key:
                facts_by_subject.setdefault(subject_key, []).append(item)
            if theme_name:
                facts_by_theme.setdefault(theme_name, []).append(item)

        def _board_count(row: dict[str, Any]) -> int:
            raw = (
                row.get("board_count")
                or row.get("limit_up_days")
                or row.get("max_consecutive_limit_up_days")
            )
            try:
                board_count = int(float(raw))
            except Exception:
                board_count = 0
            return 4 if board_count >= 4 else max(board_count, 0)

        for col in columns:
            if not isinstance(col, dict):
                continue
            subject_key = self._text(col.get("subject_key"))
            theme_name = self._text(col.get("theme_name") or subject_key)
            rows = facts_by_subject.get(subject_key) or facts_by_theme.get(theme_name) or []
            buckets: dict[int, list[dict[str, Any]]] = {4: [], 3: [], 2: [], 1: []}
            seen: set[tuple[str, int]] = set()
            for row in rows:
                board_count = _board_count(row)
                if board_count <= 0:
                    continue
                stock_id = self._text(row.get("stock_id") or row.get("stock_code"))
                stock_name = self._text(row.get("stock_name"))
                dedupe_key = (stock_id or stock_name, board_count)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                buckets.setdefault(board_count, []).append({
                    "stock_id": stock_id,
                    "stock_name": stock_name,
                    "board_count": board_count,
                    "role_label": self._text(row.get("role_label") or row.get("role") or ""),
                    "in_layer_c": bool(row.get("in_layer_c")),
                    "is_d1_candidate": bool(row.get("is_d1_candidate")),
                    "trade_action": self._text(row.get("trade_action") or row.get("next_day_action") or "观察"),
                })

            board_groups: list[dict[str, Any]] = []
            for board_count in (4, 3, 2, 1):
                stocks = buckets.get(board_count, [])
                board_groups.append({
                    "board_count": board_count,
                    "board_label": "首板" if board_count == 1 else f"{board_count}板",
                    "stock_count": len(stocks),
                    "stocks": stocks[:8],
                })
            col["board_groups"] = board_groups

        matrix["max_rows"] = max(
            (
                max((len(group.get("stocks") or []) for group in (col.get("board_groups") or [])), default=0)
                for col in columns
            ),
            default=0,
        )

    @staticmethod
    def _normalize_stock_key(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if not raw:
            return ""
        return raw.split(".", 1)[0]

    @staticmethod
    def _first_text(stock: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = stock.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

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

        authoritative_theme_map = await self._resolve_authoritative_theme_map(
            conn=conn,
            stock_keys=stock_ids,
            stock_names=sorted({self._text(target["stock"].get("stock_name")) for target in targets if isinstance(target.get("stock"), dict)}),
            active_subject_keys=self._collect_active_subject_keys(enriched),
        )
        theme_mapping_updates = self._apply_authoritative_theme_map(
            targets=targets,
            authoritative_theme_map=authoritative_theme_map,
        )

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
            "theme_mapping_enriched_count": theme_mapping_updates,
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

    @staticmethod
    def _is_placeholder_theme_name(value: Any) -> bool:
        text = str(value or "").strip()
        return not text or text in {"__independent__", "未归类", "independent", "未分类"} or text.isdigit()

    def _collect_active_subject_keys(self, source: dict[str, Any]) -> list[str]:
        keys: list[str] = []
        mainlines = source.get("mainline_daily_states")
        if isinstance(mainlines, list):
            for row in mainlines:
                if not isinstance(row, dict):
                    continue
                for key in ("canonical_subject_key", "mainline_id", "subject_key"):
                    text = self._text(row.get(key))
                    if text and text not in keys:
                        keys.append(text)
        return keys

    async def _resolve_authoritative_theme_map(
        self,
        *,
        conn,
        stock_keys: list[str],
        stock_names: list[str],
        active_subject_keys: list[str],
    ) -> dict[str, dict[str, str]]:
        if not stock_keys and not stock_names:
            return {}
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (tsm.stock_id)
                split_part(tsm.stock_id, '.', 1) AS stock_key,
                tsm.subject_key,
                COALESCE(
                    NULLIF(tgp.concept, ''),
                    NULLIF(tsm.theme_name, ''),
                    tsm.subject_key
                ) AS theme_name
            FROM theme_stock_map tsm
            LEFT JOIN theme_gate_profile tgp
                ON tgp.subject_key = tsm.subject_key
            WHERE split_part(tsm.stock_id, '.', 1) = ANY($1::text[])
               OR tsm.stock_name = ANY($2::text[])
            ORDER BY
                split_part(tsm.stock_id, '.', 1),
                CASE WHEN tsm.subject_key = ANY($3::text[]) THEN 0 ELSE 1 END,
                CASE WHEN COALESCE(NULLIF(tgp.concept, ''), NULLIF(tsm.theme_name, ''), tsm.subject_key) ~ '^[0-9]+$' THEN 1 ELSE 0 END,
                tsm.subject_key
            """,
            stock_keys,
            stock_names,
            active_subject_keys,
        )
        mapping: dict[str, dict[str, str]] = {}
        for row in rows:
            stock_key = self._normalize_stock_key(self._text(row.get("stock_key")))
            subject_key = self._text(row.get("subject_key"))
            theme_name = self._text(row.get("theme_name"))
            if not stock_key or not subject_key or self._is_placeholder_theme_name(theme_name):
                continue
            mapping[stock_key] = {
                "stock_key": stock_key,
                "subject_key": subject_key,
                "theme_name": theme_name,
            }
        return mapping

    def _apply_authoritative_theme_map(
        self,
        *,
        targets: list[dict[str, Any]],
        authoritative_theme_map: dict[str, dict[str, str]],
    ) -> int:
        updated = 0
        for target in targets:
            stock = target.get("stock")
            if not isinstance(stock, dict):
                continue
            stock_key = self._normalize_stock_key(target.get("stock_key"))
            mapping = authoritative_theme_map.get(stock_key)
            if not mapping:
                continue
            if not self._is_placeholder_theme_name(stock.get("subject_key")) and not self._is_placeholder_theme_name(stock.get("theme_name")):
                continue
            if self._is_placeholder_theme_name(stock.get("subject_key")):
                stock["subject_key"] = mapping["subject_key"]
            if self._is_placeholder_theme_name(stock.get("theme_name")):
                stock["theme_name"] = mapping["theme_name"]
            if self._is_placeholder_theme_name(stock.get("mainline_name")):
                stock["mainline_name"] = mapping["theme_name"]
            updated += 1
        return updated

    def _rebuild_market_overview_board_groups(self, source: dict[str, Any]) -> None:
        market_overview = source.get("market_overview_review")
        if not isinstance(market_overview, dict):
            return
        matrix = market_overview.get("theme_limitup_matrix")
        if not isinstance(matrix, dict):
            return
        columns = matrix.get("columns")
        if not isinstance(columns, list) or not columns:
            return

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
            rows = col.get("focus_stocks")
            if not isinstance(rows, list):
                rows = []
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

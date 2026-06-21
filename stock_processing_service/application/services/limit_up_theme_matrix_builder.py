from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any


class LimitUpThemeMatrixBuilder:
    """Build the single deterministic limit-up theme matrix contract.

    Data sources are intentionally restricted to market snapshots and
    deterministic subject mappings. This builder must not read report_context,
    stock_facts, strong stock reviews, legacy market_overview matrices, or LLM
    narrative output.
    """

    source = "limit_up_theme_matrix_builder"
    count_method = "stock_daily_snapshot_continuous_limit_up"
    limit_up_threshold = 9.5

    async def build(self, *, trade_date: date, conn: Any) -> dict[str, Any]:
        limit_up_rows = await self._fetch_current_limit_up_rows(conn, trade_date)
        stock_keys = [row["stock_key"] for row in limit_up_rows if row.get("stock_key")]
        history_rows = await self._fetch_history_rows(conn, trade_date, stock_keys)
        board_by_stock = self._compute_board_counts(history_rows, trade_date)

        subject_rows = await self._fetch_subject_stock_rows(conn, stock_keys, trade_date)
        mainline_rows = await self._fetch_mainline_rows(conn, trade_date)
        subject_keys = sorted({self._text(row.get("subject_key")) for row in subject_rows if self._text(row.get("subject_key"))})
        ranked_subject_keys = await self._fetch_ranked_subject_keys(conn, trade_date, subject_keys)
        registry_names = await self._fetch_subject_registry_names(conn, subject_keys)

        mainline_index = self._build_mainline_index(mainline_rows)
        subject_rows_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in subject_rows:
            stock_key = self._stock_key(row.get("stock_id"))
            if stock_key:
                subject_rows_by_stock[stock_key].append(row)

        columns_map: dict[str, dict[str, Any]] = {}
        unmapped_stocks: list[dict[str, Any]] = []
        invalid_theme_rows: list[dict[str, Any]] = []
        mapped_stock_count = 0

        for row in limit_up_rows:
            stock_key = self._text(row.get("stock_key"))
            board_count = board_by_stock.get(stock_key, 0)
            if board_count <= 0:
                continue
            resolved = self._resolve_theme(
                stock_key=stock_key,
                subject_rows=subject_rows_by_stock.get(stock_key, []),
                mainline_index=mainline_index,
                ranked_subject_keys=ranked_subject_keys,
                registry_names=registry_names,
            )
            if resolved is None:
                unmapped_stocks.append(self._diagnostic_stock(row, board_count, "no_deterministic_theme_mapping"))
                continue
            if self._is_invalid_theme_name(resolved["theme_name"]):
                invalid_theme_rows.append({
                    **self._diagnostic_stock(row, board_count, "invalid_theme_name"),
                    "subject_key": resolved.get("subject_key", ""),
                    "theme_name": resolved.get("theme_name", ""),
                })
                continue

            theme_key = self._theme_bucket_key(resolved)
            bucket = columns_map.setdefault(
                theme_key,
                {
                    "subject_key": resolved.get("subject_key", ""),
                    "theme_name": resolved["theme_name"],
                    "mainline_name": resolved.get("mainline_name") or resolved["theme_name"],
                    "limit_up_count": 0,
                    "active_mainline": bool(resolved.get("active_mainline")),
                    "lifecycle_state": resolved.get("lifecycle_state", ""),
                    "trade_action": resolved.get("trade_action", ""),
                    "focus_stocks": [],
                    "catalyst_events": [],
                    "diagnostics": {"mapping_source": resolved.get("mapping_source", "")},
                    "_board_groups": {1: [], 2: [], 3: [], 4: []},
                    "_stock_keys": set(),
                },
            )
            stock_identity = stock_key or self._text(row.get("stock_name"))
            if stock_identity in bucket["_stock_keys"]:
                continue
            bucket["_stock_keys"].add(stock_identity)
            stock = {
                "stock_id": self._text(row.get("stock_id") or stock_key),
                "stock_name": self._text(row.get("stock_name")),
                "subject_key": resolved.get("subject_key", ""),
                "theme_name": resolved["theme_name"],
                "board_count": board_count,
                "pct_chg": self._float_or_none(row.get("pct_chg")),
                "close_price": self._float_or_none(row.get("close_price")),
                "amount": self._float_or_none(row.get("amount")),
            }
            bucket["_board_groups"][board_count].append(stock)
            bucket["focus_stocks"].append(stock)
            mapped_stock_count += 1

        columns = [self._finalize_column(bucket) for bucket in columns_map.values()]
        columns.sort(
            key=lambda col: (
                0 if col.get("active_mainline") else 1,
                -int(col.get("limit_up_count") or 0),
                str(col.get("theme_name") or ""),
            )
        )
        board_totals = self._visible_board_totals(columns)
        summary = self._summary(columns, board_totals)
        return {
            "source": self.source,
            "trade_date": trade_date.isoformat(),
            "summary": summary,
            "board_totals": board_totals,
            "columns": columns,
            "diagnostics": {
                "source": self.source,
                "limit_up_stock_count": len(limit_up_rows),
                "mapped_stock_count": mapped_stock_count,
                "unmapped_stock_count": len(unmapped_stocks),
                "unmapped_stocks": unmapped_stocks,
                "invalid_theme_rows": invalid_theme_rows,
                "invalid_theme_row_count": len(invalid_theme_rows),
                "theme_count": len(columns),
                "candidate_count": mapped_stock_count,
                "count_method": self.count_method,
            },
        }

    async def _fetch_current_limit_up_rows(self, conn: Any, trade_date: date) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (split_part(stock_id, '.', 1))
                split_part(stock_id, '.', 1) AS stock_key,
                stock_id,
                stock_name,
                close_price,
                pct_chg,
                amount
            FROM stock_daily_snapshot
            WHERE trade_date = $1::date
              AND source_name LIKE 'tushare%'
              AND COALESCE(pct_chg, 0) >= $2
            ORDER BY split_part(stock_id, '.', 1), source_name DESC
            """,
            trade_date,
            self.limit_up_threshold,
        )
        return [dict(row) for row in rows]

    async def _fetch_history_rows(self, conn: Any, trade_date: date, stock_keys: list[str]) -> list[dict[str, Any]]:
        if not stock_keys:
            return []
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (split_part(stock_id, '.', 1), trade_date)
                split_part(stock_id, '.', 1) AS stock_key,
                trade_date,
                pct_chg
            FROM stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date >= $1::date - INTERVAL '10 days'
              AND source_name LIKE 'tushare%'
              AND split_part(stock_id, '.', 1) = ANY($2::text[])
            ORDER BY split_part(stock_id, '.', 1), trade_date DESC, source_name DESC
            """,
            trade_date,
            stock_keys,
        )
        return [dict(row) for row in rows]

    async def _fetch_subject_stock_rows(self, conn: Any, stock_keys: list[str], trade_date: date) -> list[dict[str, Any]]:
        if not stock_keys:
            return []
        rows = await conn.fetch(
            """
            SELECT stock_id, subject_key, sort, top, source_type, confidence, reason
            FROM subject_stock_map
            WHERE stock_id = ANY($1::text[])
              AND (start_date IS NULL OR start_date <= $2::date)
              AND (end_date IS NULL OR end_date >= $2::date)
            ORDER BY stock_id, COALESCE(sort, 999999), COALESCE(confidence, 0) DESC, subject_key
            """,
            stock_keys,
            trade_date,
        )
        return [dict(row) for row in rows]

    async def _fetch_mainline_rows(self, conn: Any, trade_date: date) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT canonical_subject_key,
                   mainline_name,
                   active_subject_keys_json,
                   lifecycle_state,
                   mainline_alive,
                   mainline_trade_alive,
                   trade_mode,
                   allow_trade
            FROM mainline_daily_state
            WHERE trade_date = $1::date
            """,
            trade_date,
        )
        return [dict(row) for row in rows]

    async def _fetch_ranked_subject_keys(self, conn: Any, trade_date: date, subject_keys: list[str]) -> set[str]:
        if not subject_keys:
            return set()
        rows = await conn.fetch(
            """
            SELECT subject_key
            FROM subject_rank_daily
            WHERE rank_date = $1::date
              AND subject_key = ANY($2::text[])
            """,
            trade_date,
            subject_keys,
        )
        return {
            self._text(row.get("subject_key"))
            for row in (dict(item) for item in rows)
            if self._text(row.get("subject_key"))
        }

    async def _fetch_subject_registry_names(self, conn: Any, subject_keys: list[str]) -> dict[str, str]:
        if not subject_keys:
            return {}
        rows = await conn.fetch(
            """
            SELECT subject_key, theme_name
            FROM theme_mainline_identity_registry
            WHERE subject_key = ANY($1::text[])
            UNION ALL
            SELECT subject_key, theme_name
            FROM theme_detail_snapshot
            WHERE subject_key = ANY($1::text[])
              AND is_current = TRUE
            """,
            subject_keys,
        )
        names: dict[str, str] = {}
        for row in (dict(item) for item in rows):
            subject_key = self._text(row.get("subject_key"))
            theme_name = self._text(row.get("theme_name"))
            if subject_key and subject_key not in names and not self._is_invalid_theme_name(theme_name):
                names[subject_key] = theme_name
        return names

    def _compute_board_counts(self, rows: list[dict[str, Any]], trade_date: date) -> dict[str, int]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            stock_key = self._text(row.get("stock_key"))
            if stock_key:
                grouped[stock_key].append(row)

        counts: dict[str, int] = {}
        for stock_key, stock_rows in grouped.items():
            stock_rows.sort(key=lambda item: item.get("trade_date"), reverse=True)
            count = 0
            for idx, row in enumerate(stock_rows):
                if idx == 0 and str(row.get("trade_date")) != trade_date.isoformat():
                    break
                if self._float_or_none(row.get("pct_chg")) is not None and float(row.get("pct_chg")) >= self.limit_up_threshold:
                    count += 1
                else:
                    break
            if count > 0:
                counts[stock_key] = min(count, 4)
        return counts

    def _build_mainline_index(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for row in rows:
            mainline_name = self._text(row.get("mainline_name"))
            if self._is_invalid_theme_name(mainline_name):
                continue
            keys = {
                self._text(row.get("canonical_subject_key")),
                mainline_name,
            }
            active_keys = row.get("active_subject_keys_json")
            if isinstance(active_keys, list):
                keys.update(self._text(item) for item in active_keys)
            for key in keys:
                if key and not self._is_invalid_theme_name(key):
                    index[key] = row
        return index

    def _resolve_theme(
        self,
        *,
        stock_key: str,
        subject_rows: list[dict[str, Any]],
        mainline_index: dict[str, dict[str, Any]],
        ranked_subject_keys: set[str],
        registry_names: dict[str, str],
    ) -> dict[str, Any] | None:
        ranked_rows = sorted(
            subject_rows,
            key=lambda item: (
                0 if self._text(item.get("subject_key")) in ranked_subject_keys else 1,
                int(item.get("sort") or 999999),
                self._text(item.get("subject_key")),
            ),
        )
        for row in ranked_rows:
            subject_key = self._text(row.get("subject_key"))
            mainline = mainline_index.get(subject_key)
            if mainline:
                mainline_name = self._text(mainline.get("mainline_name"))
                if not self._is_invalid_theme_name(mainline_name):
                    return {
                        "subject_key": self._text(mainline.get("canonical_subject_key") or subject_key),
                        "theme_name": mainline_name,
                        "mainline_name": mainline_name,
                        "active_mainline": bool(mainline.get("mainline_alive") or mainline.get("mainline_trade_alive")),
                        "lifecycle_state": self._text(mainline.get("lifecycle_state")),
                        "trade_action": self._text(mainline.get("trade_mode")),
                        "mapping_source": "mainline_daily_state",
                    }

        for row in subject_rows:
            subject_key = self._text(row.get("subject_key"))
            theme_name = registry_names.get(subject_key)
            if not self._is_invalid_theme_name(theme_name):
                return {
                    "subject_key": subject_key,
                    "theme_name": theme_name,
                    "mainline_name": theme_name,
                    "active_mainline": False,
                    "lifecycle_state": "",
                    "trade_action": "",
                    "mapping_source": "subject_stock_map",
                }
        return None

    def _finalize_column(self, bucket: dict[str, Any]) -> dict[str, Any]:
        board_groups: list[dict[str, Any]] = []
        for board_count in (4, 3, 2, 1):
            stocks = list(bucket["_board_groups"].get(board_count, []))
            stocks.sort(key=lambda item: (str(item.get("stock_name") or item.get("stock_id") or "")))
            board_groups.append({
                "board_count": board_count,
                "board_label": "首板" if board_count == 1 else f"{board_count}板",
                "stock_count": len(stocks),
                "stocks": stocks,
            })
        limit_up_count = sum(group["stock_count"] for group in board_groups)
        result = {
            key: value
            for key, value in bucket.items()
            if not str(key).startswith("_")
        }
        result["board_groups"] = board_groups
        result["limit_up_count"] = limit_up_count
        result["focus_stocks"] = [stock for group in board_groups for stock in group["stocks"]]
        return result

    @staticmethod
    def _visible_board_totals(columns: list[dict[str, Any]]) -> dict[str, int]:
        totals = {"4": 0, "3": 0, "2": 0, "1": 0}
        for column in columns:
            for group in column.get("board_groups") or []:
                key = str(group.get("board_count") or "")
                if key in totals:
                    totals[key] += int(group.get("stock_count") or 0)
        return totals

    @staticmethod
    def _summary(columns: list[dict[str, Any]], board_totals: dict[str, int]) -> str:
        hot = "、".join([str(col.get("theme_name") or "") for col in columns[:3] if col.get("theme_name")]) or "暂无"
        return (
            f"涨停热点矩阵：4板 {board_totals.get('4', 0)} 只，"
            f"3板 {board_totals.get('3', 0)} 只，2板 {board_totals.get('2', 0)} 只，"
            f"首板 {board_totals.get('1', 0)} 只；热点题材：{hot}。"
        )

    @staticmethod
    def _theme_bucket_key(resolved: dict[str, Any]) -> str:
        subject_key = LimitUpThemeMatrixBuilder._text(resolved.get("subject_key"))
        theme_name = LimitUpThemeMatrixBuilder._text(resolved.get("theme_name"))
        return subject_key if subject_key and not subject_key.isdigit() else theme_name

    @staticmethod
    def _diagnostic_stock(row: dict[str, Any], board_count: int, reason: str) -> dict[str, Any]:
        return {
            "stock_id": LimitUpThemeMatrixBuilder._text(row.get("stock_id")),
            "stock_name": LimitUpThemeMatrixBuilder._text(row.get("stock_name")),
            "stock_key": LimitUpThemeMatrixBuilder._text(row.get("stock_key")),
            "board_count": board_count,
            "reason": reason,
        }

    @staticmethod
    def _stock_key(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if not raw:
            return ""
        return raw.split(".", 1)[0]

    @staticmethod
    def _text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        return str(value).strip()

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    @classmethod
    def _is_invalid_theme_name(cls, value: Any) -> bool:
        text = cls._text(value)
        lower = text.lower()
        return (
            not text
            or text.isdigit()
            or text in {"未归类", "未分类", "__independent__"}
            or lower == "independent"
            or text.startswith("__")
        )

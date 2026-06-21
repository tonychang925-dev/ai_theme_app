from __future__ import annotations

import json
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

        columns_map = self._build_mainline_columns(mainline_rows)
        mainline_index = self._build_mainline_index(mainline_rows)
        subject_rows_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in subject_rows:
            stock_key = self._stock_key(row.get("stock_id"))
            if stock_key:
                subject_rows_by_stock[stock_key].append(row)

        non_mainline_limit_up_stocks: list[dict[str, Any]] = []
        invalid_theme_rows: list[dict[str, Any]] = []
        assignment_audit_rows: list[dict[str, Any]] = []
        mapped_stock_count = 0

        for row in limit_up_rows:
            stock_key = self._text(row.get("stock_key"))
            board_count = board_by_stock.get(stock_key, 0)
            if board_count <= 0:
                continue
            stock_name = self._resolve_stock_name(row, subject_rows_by_stock.get(stock_key, []))
            resolved_items = self._resolve_themes(
                stock_key=stock_key,
                subject_rows=subject_rows_by_stock.get(stock_key, []),
                mainline_index=mainline_index,
                ranked_subject_keys=ranked_subject_keys,
            )
            audit_row = self._assignment_audit_row(
                row=row,
                stock_name=stock_name,
                board_count=board_count,
                subject_rows=subject_rows_by_stock.get(stock_key, []),
                ranked_subject_keys=ranked_subject_keys,
                mainline_index=mainline_index,
                resolved_items=resolved_items,
            )
            if not resolved_items:
                non_mainline_limit_up_stocks.append(self._diagnostic_stock(row, board_count, "no_mainline_mapping", stock_name))
                assignment_audit_rows.append(audit_row)
                continue

            chosen_subject_keys: list[str] = []
            chosen_theme_names: list[str] = []
            chosen_reasons: list[str] = []
            for resolved in resolved_items:
                if self._is_invalid_theme_name(resolved["theme_name"]):
                    invalid_theme_rows.append({
                        **self._diagnostic_stock(row, board_count, "invalid_theme_name", stock_name),
                        "subject_key": resolved.get("subject_key", ""),
                        "theme_name": resolved.get("theme_name", ""),
                    })
                    continue

                theme_key = self._theme_bucket_key(resolved)
                bucket = columns_map.get(theme_key)
                if bucket is None:
                    non_mainline_limit_up_stocks.append(self._diagnostic_stock(row, board_count, "mainline_column_missing", stock_name))
                    continue
                stock_identity = stock_key or stock_name
                if stock_identity in bucket["_stock_keys"]:
                    continue
                bucket["_stock_keys"].add(stock_identity)
                chosen_subject_keys.append(self._text(resolved.get("subject_key")))
                chosen_theme_names.append(self._text(resolved.get("theme_name")))
                chosen_reasons.append(self._text(resolved.get("mapping_source")))
                stock = {
                    "stock_id": self._text(row.get("stock_id") or stock_key),
                    "stock_name": stock_name,
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
            audit_row["chosen_subject_key"] = "、".join([item for item in chosen_subject_keys if item])
            audit_row["chosen_theme_name"] = "、".join([item for item in chosen_theme_names if item])
            audit_row["chosen_reason"] = "、".join([item for item in chosen_reasons if item]) or "not_assigned_to_column"
            assignment_audit_rows.append(audit_row)

        mainline_columns = [
            self._finalize_column(bucket)
            for bucket in sorted(columns_map.values(), key=lambda item: int(item.get("_order") or 0))
        ]
        visible_columns = [col for col in mainline_columns if int(col.get("limit_up_count") or 0) > 0]
        visible_columns.sort(
            key=lambda col: (
                -int(col.get("limit_up_count") or 0),
                str(col.get("theme_name") or ""),
            )
        )
        board_totals = self._visible_board_totals(visible_columns)
        summary = self._summary(visible_columns, board_totals)
        return {
            "source": self.source,
            "trade_date": trade_date.isoformat(),
            "summary": summary,
            "board_totals": board_totals,
            "columns": visible_columns,
            "visible_columns": visible_columns,
            "mainline_columns": mainline_columns,
            "non_mainline_columns": [],
            "diagnostics": {
                "source": self.source,
                "limit_up_stock_count": len(limit_up_rows),
                "mapped_stock_count": mapped_stock_count,
                "unmapped_stock_count": len(non_mainline_limit_up_stocks),
                "unmapped_stocks": non_mainline_limit_up_stocks,
                "non_mainline_limit_up_stock_count": len(non_mainline_limit_up_stocks),
                "non_mainline_limit_up_stocks": non_mainline_limit_up_stocks,
                "invalid_theme_rows": invalid_theme_rows,
                "invalid_theme_row_count": len(invalid_theme_rows),
                "assignment_audit_rows": assignment_audit_rows,
                "theme_count": len(visible_columns),
                "mainline_theme_count": len(mainline_columns),
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
            SELECT stock_id, subject_key, name AS stock_name, sort, top, source_type, confidence, reason
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
            SELECT id,
                   canonical_subject_key,
                   mainline_name,
                   active_subject_keys_json,
                   lifecycle_state,
                   mainline_alive,
                   mainline_trade_alive,
                   trade_mode,
                   allow_trade
            FROM mainline_daily_state
            WHERE trade_date = $1::date
            ORDER BY id
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

    def _build_mainline_columns(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        columns: dict[str, dict[str, Any]] = {}
        for idx, row in enumerate(rows):
            mainline_name = self._text(row.get("mainline_name"))
            if self._is_invalid_theme_name(mainline_name):
                continue
            subject_key = self._text(row.get("canonical_subject_key") or mainline_name)
            key = self._mainline_bucket_key(row, idx)
            if not key:
                continue
            columns[key] = {
                "subject_key": subject_key,
                "theme_name": mainline_name,
                "mainline_name": mainline_name,
                "limit_up_count": 0,
                "active_mainline": bool(row.get("mainline_alive") or row.get("mainline_trade_alive")),
                "lifecycle_state": self._text(row.get("lifecycle_state")),
                "trade_action": self._text(row.get("trade_mode")),
                "focus_stocks": [],
                "catalyst_events": [],
                "diagnostics": {"mapping_source": "mainline_daily_state"},
                "_board_groups": {1: [], 2: [], 3: [], 4: []},
                "_stock_keys": set(),
            "_order": idx,
            }
        return columns

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

    def _build_mainline_index(self, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        active_key_counts: dict[str, int] = defaultdict(int)
        for row in rows:
            mainline_name = self._text(row.get("mainline_name"))
            if self._is_invalid_theme_name(mainline_name):
                continue
            for key in {self._text(item) for item in self._json_list(row.get("active_subject_keys_json"))}:
                if self._is_valid_subject_key(key):
                    active_key_counts[key] += 1

        for row in rows:
            mainline_name = self._text(row.get("mainline_name"))
            if self._is_invalid_theme_name(mainline_name):
                continue
            keys = {
                self._text(row.get("canonical_subject_key")),
                mainline_name,
            }
            bucket_key = self._mainline_bucket_key(row, len(index))
            active_keys = self._json_list(row.get("active_subject_keys_json"))
            keys.update(
                self._text(item)
                for item in active_keys
                if active_key_counts.get(self._text(item), 0) == 1
            )
            for key in keys:
                if self._is_valid_subject_key(key):
                    indexed = dict(row)
                    indexed["_bucket_key"] = bucket_key
                    index.setdefault(key, []).append(indexed)
        return index

    def _resolve_themes(
        self,
        *,
        stock_key: str,
        subject_rows: list[dict[str, Any]],
        mainline_index: dict[str, list[dict[str, Any]]],
        ranked_subject_keys: set[str],
    ) -> list[dict[str, Any]]:
        ranked_rows = sorted(
            subject_rows,
            key=lambda item: (
                0 if self._text(item.get("subject_key")) in ranked_subject_keys else 1,
                int(item.get("sort") or 999999),
                self._text(item.get("subject_key")),
            ),
        )
        resolved: list[dict[str, Any]] = []
        seen_bucket_keys: set[str] = set()
        for row in ranked_rows:
            subject_key = self._text(row.get("subject_key"))
            for mainline in mainline_index.get(subject_key, []):
                mainline_name = self._text(mainline.get("mainline_name"))
                bucket_key = self._text(mainline.get("_bucket_key"))
                if self._is_invalid_theme_name(mainline_name) or not bucket_key or bucket_key in seen_bucket_keys:
                    continue
                seen_bucket_keys.add(bucket_key)
                resolved.append({
                    "subject_key": self._text(mainline.get("canonical_subject_key") or subject_key),
                    "theme_name": mainline_name,
                    "mainline_name": mainline_name,
                    "bucket_key": bucket_key,
                    "active_mainline": bool(mainline.get("mainline_alive") or mainline.get("mainline_trade_alive")),
                    "lifecycle_state": self._text(mainline.get("lifecycle_state")),
                    "trade_action": self._text(mainline.get("trade_mode")),
                    "mapping_source": "mainline_daily_state",
                })

        return resolved

    def _assignment_audit_row(
        self,
        *,
        row: dict[str, Any],
        stock_name: str,
        board_count: int,
        subject_rows: list[dict[str, Any]],
        ranked_subject_keys: set[str],
        mainline_index: dict[str, list[dict[str, Any]]],
        resolved_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        all_subject_keys: list[str] = []
        all_subject_names: list[str] = []
        ranked_hits: list[str] = []
        mainline_matches: list[str] = []
        for subject_row in subject_rows:
            subject_key = self._text(subject_row.get("subject_key"))
            if not subject_key:
                continue
            all_subject_keys.append(subject_key)
            mapped_name = self._text(subject_row.get("stock_name"))
            if mapped_name:
                all_subject_names.append(mapped_name)
            if subject_key in ranked_subject_keys:
                ranked_hits.append(subject_key)
            for mainline in mainline_index.get(subject_key, []):
                mainline_name = self._text(mainline.get("mainline_name"))
                if mainline_name:
                    mainline_matches.append(mainline_name)
        return {
            "stock_id": self._text(row.get("stock_id")),
            "stock_name": stock_name,
            "board_count": board_count,
            "all_subject_keys": self._unique_keep_order(all_subject_keys),
            "all_subject_names": self._unique_keep_order(all_subject_names),
            "ranked_subject_keys_hit": self._unique_keep_order(ranked_hits),
            "mainline_matches": self._unique_keep_order(mainline_matches),
            "chosen_subject_key": "、".join(
                self._unique_keep_order([self._text(item.get("subject_key")) for item in resolved_items])
            ),
            "chosen_theme_name": "、".join(
                self._unique_keep_order([self._text(item.get("theme_name")) for item in resolved_items])
            ),
            "chosen_reason": "、".join(
                self._unique_keep_order([self._text(item.get("mapping_source")) for item in resolved_items])
            ) or "no_mainline_mapping",
            "mainline_hit": bool(resolved_items),
        }

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
        bucket_key = LimitUpThemeMatrixBuilder._text(resolved.get("bucket_key"))
        if bucket_key:
            return bucket_key
        subject_key = LimitUpThemeMatrixBuilder._text(resolved.get("subject_key"))
        theme_name = LimitUpThemeMatrixBuilder._text(resolved.get("theme_name"))
        return subject_key or theme_name

    @staticmethod
    def _mainline_bucket_key(row: dict[str, Any], index: int) -> str:
        row_id = LimitUpThemeMatrixBuilder._text(row.get("id"))
        if row_id:
            return f"mainline:{row_id}"
        subject_key = LimitUpThemeMatrixBuilder._text(row.get("canonical_subject_key"))
        if subject_key:
            return f"mainline:{subject_key}:{index}"
        return f"mainline:{LimitUpThemeMatrixBuilder._text(row.get('mainline_name'))}:{index}"

    @staticmethod
    def _json_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            try:
                loaded = json.loads(value)
                return loaded if isinstance(loaded, list) else []
            except Exception:
                return []
        return []

    @staticmethod
    def _diagnostic_stock(row: dict[str, Any], board_count: int, reason: str, stock_name: str | None = None) -> dict[str, Any]:
        return {
            "stock_id": LimitUpThemeMatrixBuilder._text(row.get("stock_id")),
            "stock_name": LimitUpThemeMatrixBuilder._text(stock_name or row.get("stock_name")),
            "stock_key": LimitUpThemeMatrixBuilder._text(row.get("stock_key")),
            "board_count": board_count,
            "reason": reason,
        }

    @classmethod
    def _resolve_stock_name(cls, row: dict[str, Any], subject_rows: list[dict[str, Any]]) -> str:
        snapshot_name = cls._text(row.get("stock_name"))
        if snapshot_name and not snapshot_name.isdigit():
            return snapshot_name
        for subject_row in subject_rows:
            mapped_name = cls._text(subject_row.get("stock_name"))
            if mapped_name and not mapped_name.isdigit():
                return mapped_name
        return ""

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

    @classmethod
    def _is_valid_subject_key(cls, value: Any) -> bool:
        text = cls._text(value)
        lower = text.lower()
        return bool(text) and text not in {"未归类", "未分类", "__independent__"} and lower != "independent" and not text.startswith("__")

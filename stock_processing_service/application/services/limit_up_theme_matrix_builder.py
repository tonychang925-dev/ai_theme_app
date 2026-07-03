from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any

from stock_processing_service.integrations.a_stock_data.resolvers.reason_theme_resolver import RuleResolver


class LimitUpThemeMatrixBuilder:
    """Build the single deterministic limit-up theme matrix contract.

    Data sources are intentionally restricted to market snapshots and
    deterministic subject mappings. This builder must not read report_context,
    stock_facts, strong stock reviews, legacy market_overview matrices, or LLM
    narrative output.
    """

    source = "limit_up_theme_matrix_builder"
    count_method = "stock_daily_snapshot_continuous_limit_up"
    display_theme_aliases = {
        "PCB印制电路板": "PCB/HBM产业链",
        "PCB/HBM产业链": "PCB/HBM产业链",
        "AI光纤": "AI光通信",
        "AI光通信": "AI光通信",
        "人形机器人": "机器人",
        "工业机器人": "机器人",
        "机器人": "机器人",
        "算力": "AI算力基础设施",
        "算力租赁": "AI算力基础设施",
        "数据中心": "AI算力基础设施",
        "液冷": "AI算力基础设施",
        "AI算力基础设施": "AI算力基础设施",
        "全固态电池进度表": "先进材料/固态电池",
        "先进材料/固态电池": "先进材料/固态电池",
    }
    limit_up_threshold = 9.5

    def __init__(self, *, reason_theme_resolver: Any | None = None) -> None:
        self._reason_theme_resolver = reason_theme_resolver or RuleResolver()

    async def build(self, *, trade_date: date, conn: Any) -> dict[str, Any]:
        limit_up_rows = await self._fetch_current_limit_up_rows(conn, trade_date)
        stock_keys = [row["stock_key"] for row in limit_up_rows if row.get("stock_key")]
        history_rows = await self._fetch_history_rows(conn, trade_date, stock_keys)
        board_by_stock = self._compute_board_counts(history_rows, trade_date)

        subject_rows = await self._fetch_subject_stock_rows(conn, stock_keys, trade_date)
        mainline_rows = await self._fetch_mainline_rows(conn, trade_date)
        subject_keys = sorted({self._text(row.get("subject_key")) for row in subject_rows if self._text(row.get("subject_key"))})
        subject_name_by_key = await self._fetch_subject_names(conn, subject_keys)
        stock_name_by_key = await self._fetch_stock_names(conn, stock_keys)
        ranked_subject_keys = await self._fetch_ranked_subject_keys(conn, trade_date, subject_keys)
        reason_evidence_by_stock = self._build_reason_evidence_index(
            await self._fetch_theme_reason_evidence(conn, trade_date, stock_keys)
        )
        ths_reason_by_stock = self._build_ths_reason_index(
            await self._fetch_ths_hot_reason_rows(conn, trade_date, stock_keys)
        )

        columns_map = self._build_mainline_columns(mainline_rows)
        mainline_index = self._build_mainline_index(mainline_rows)
        non_mainline_columns_map: dict[str, dict[str, Any]] = {}
        subject_rows_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in subject_rows:
            stock_key = self._stock_key(row.get("stock_id"))
            if stock_key:
                subject_rows_by_stock[stock_key].append(row)
        effective_limit_up_rows: list[dict[str, Any]] = []
        for row in limit_up_rows:
            stock_key = self._text(row.get("stock_key"))
            stock_name = self._resolve_stock_name(row, subject_rows_by_stock.get(stock_key, []), stock_name_by_key)
            if not self._is_excluded_stock(stock_key, stock_name):
                effective_limit_up_rows.append(row)

        non_mainline_limit_up_stocks: list[dict[str, Any]] = []
        invalid_theme_rows: list[dict[str, Any]] = []
        assignment_audit_rows: list[dict[str, Any]] = []
        mapped_stock_count = 0

        for row in effective_limit_up_rows:
            stock_key = self._text(row.get("stock_key"))
            board_count = board_by_stock.get(stock_key, 0)
            if board_count <= 0:
                continue
            stock_name = self._resolve_stock_name(row, subject_rows_by_stock.get(stock_key, []), stock_name_by_key)
            resolution = self._resolve_primary_mainline(
                stock_key=stock_key,
                subject_rows=subject_rows_by_stock.get(stock_key, []),
                mainline_index=mainline_index,
                ranked_subject_keys=ranked_subject_keys,
            )
            resolved = resolution.get("resolved")
            ambiguous_matches = resolution.get("ambiguous_matches") or []
            audit_row = self._assignment_audit_row(
                row=row,
                stock_name=stock_name,
                board_count=board_count,
                subject_rows=subject_rows_by_stock.get(stock_key, []),
                ranked_subject_keys=ranked_subject_keys,
                mainline_index=mainline_index,
                resolved=resolved,
                ambiguous_matches=ambiguous_matches,
            )
            if ambiguous_matches:
                non_mainline_limit_up_stocks.append(self._diagnostic_stock(row, board_count, "ambiguous_mainline_mapping", stock_name))
                assignment_audit_rows.append(audit_row)
                continue
            if not resolved:
                reason_theme = self._resolve_primary_reason_evidence(reason_evidence_by_stock.get(stock_key, []))
                if reason_theme is None:
                    reason_theme = await self._resolve_ths_reason_theme(ths_reason_by_stock.get(stock_key))
                if reason_theme:
                    bucket = self._non_mainline_bucket(non_mainline_columns_map, reason_theme)
                    self._append_stock_to_bucket(
                        bucket=bucket,
                        row=row,
                        stock_key=stock_key,
                        stock_name=stock_name,
                        board_count=board_count,
                        subject_key=reason_theme["subject_key"],
                        theme_name=reason_theme["theme_name"],
                    )
                    mapped_stock_count += 1
                    audit_row.update(self._audit_resolution_fields(reason_theme, []))
                    assignment_audit_rows.append(audit_row)
                    continue
                non_mainline = self._resolve_primary_subject_theme(
                    subject_rows=subject_rows_by_stock.get(stock_key, []),
                    subject_name_by_key=subject_name_by_key,
                    ranked_subject_keys=ranked_subject_keys,
                )
                if non_mainline:
                    bucket = self._non_mainline_bucket(non_mainline_columns_map, non_mainline)
                    self._append_stock_to_bucket(
                        bucket=bucket,
                        row=row,
                        stock_key=stock_key,
                        stock_name=stock_name,
                        board_count=board_count,
                        subject_key=non_mainline["subject_key"],
                        theme_name=non_mainline["theme_name"],
                    )
                    mapped_stock_count += 1
                    audit_row.update(self._audit_resolution_fields(non_mainline, []))
                    assignment_audit_rows.append(audit_row)
                    continue
                non_mainline_limit_up_stocks.append(self._diagnostic_stock(row, board_count, "no_valid_subject_mapping", stock_name))
                assignment_audit_rows.append(audit_row)
                continue

            if self._is_invalid_theme_name(resolved["theme_name"]):
                invalid_theme_rows.append({
                    **self._diagnostic_stock(row, board_count, "invalid_theme_name", stock_name),
                    "subject_key": resolved.get("subject_key", ""),
                    "theme_name": resolved.get("theme_name", ""),
                })
                assignment_audit_rows.append(audit_row)
                continue

            theme_key = self._theme_bucket_key(resolved)
            bucket = columns_map.get(theme_key)
            if bucket is None:
                non_mainline_limit_up_stocks.append(self._diagnostic_stock(row, board_count, "mainline_column_missing", stock_name))
                assignment_audit_rows.append(audit_row)
                continue
            stock_identity = stock_key or stock_name
            if stock_identity in bucket["_stock_keys"]:
                assignment_audit_rows.append(audit_row)
                continue
            self._append_stock_to_bucket(
                bucket=bucket,
                row=row,
                stock_key=stock_key,
                stock_name=stock_name,
                board_count=board_count,
                subject_key=resolved.get("subject_key", ""),
                theme_name=resolved["theme_name"],
            )
            mapped_stock_count += 1
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
        non_mainline_columns = [
            self._finalize_column(bucket)
            for bucket in non_mainline_columns_map.values()
        ]
        non_mainline_columns.sort(
            key=lambda col: (
                -int(col.get("limit_up_count") or 0),
                str(col.get("theme_name") or ""),
            )
        )
        raw_market_columns = sorted(
            self._merge_market_columns_by_theme([*visible_columns, *non_mainline_columns]),
            key=self._market_column_sort_key,
        )
        collapse_result = self._collapse_tail_columns(
            columns=raw_market_columns,
            diagnostics=non_mainline_limit_up_stocks,
            max_columns=12,
        )
        market_columns = collapse_result["columns"]
        market_board_totals = self._market_board_totals(effective_limit_up_rows, board_by_stock)
        mainline_board_totals = self._visible_board_totals(mainline_columns)
        summary = self._summary(market_columns, market_board_totals, mainline_board_totals)
        return {
            "source": self.source,
            "trade_date": trade_date.isoformat(),
            "summary": summary,
            "board_totals": mainline_board_totals,
            "market_board_totals": market_board_totals,
            "mainline_board_totals": mainline_board_totals,
            "columns": market_columns,
            "visible_columns": market_columns,
            "mainline_columns": mainline_columns,
            "non_mainline_columns": non_mainline_columns,
            "diagnostics": {
                "source": self.source,
                "limit_up_stock_count": len(effective_limit_up_rows),
                "mapped_stock_count": mapped_stock_count,
                "unmapped_stock_count": len(non_mainline_limit_up_stocks),
                "true_other_count": len(non_mainline_limit_up_stocks),
                "collapsed_other_count": collapse_result["collapsed_other_count"],
                "display_other_count": collapse_result["display_other_count"],
                "collapsed_other_themes": collapse_result["collapsed_other_themes"],
                "unmapped_stocks": non_mainline_limit_up_stocks,
                "non_mainline_limit_up_stock_count": len(non_mainline_limit_up_stocks),
                "non_mainline_limit_up_stocks": non_mainline_limit_up_stocks,
                "ambiguous_mainline_stock_count": len([
                    row for row in assignment_audit_rows if row.get("chosen_reason") == "ambiguous_mainline_mapping"
                ]),
                "ambiguous_mainline_stocks": [
                    row for row in assignment_audit_rows if row.get("chosen_reason") == "ambiguous_mainline_mapping"
                ],
                "invalid_theme_rows": invalid_theme_rows,
                "invalid_theme_row_count": len(invalid_theme_rows),
                "assignment_audit_rows": assignment_audit_rows,
                "theme_count": len(market_columns),
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
              AND split_part(stock_id, '.', 1) NOT LIKE '688%'
              AND split_part(stock_id, '.', 1) NOT LIKE '920%'
              AND COALESCE(stock_name, '') NOT ILIKE '%ST%'
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

    async def _fetch_subject_names(self, conn: Any, subject_keys: list[str]) -> dict[str, str]:
        if not subject_keys:
            return {}
        rows = await conn.fetch(
            """
            SELECT subject_key, subject_name AS theme_name
            FROM subject_node_staging
            WHERE subject_key = ANY($1::text[])
            UNION ALL
            SELECT subject_key, name AS theme_name
            FROM jyhf_subject_node_staging
            WHERE subject_key = ANY($1::text[])
            UNION ALL
            SELECT subject_key, theme_name
            FROM theme_detail_snapshot
            WHERE subject_key = ANY($1::text[])
            UNION ALL
            SELECT subject_key, heat_name AS theme_name
            FROM subject_rank_daily
            WHERE subject_key = ANY($1::text[])
            """,
            subject_keys,
        )
        result: dict[str, str] = {}
        for row in (dict(item) for item in rows):
            subject_key = self._text(row.get("subject_key"))
            theme_name = self._text(row.get("theme_name"))
            if subject_key and not self._is_invalid_theme_name(theme_name) and subject_key not in result:
                result[subject_key] = theme_name
        return result

    async def _fetch_stock_names(self, conn: Any, stock_keys: list[str]) -> dict[str, str]:
        if not stock_keys:
            return {}
        rows = await conn.fetch(
            """
            SELECT split_part(stock_id, '.', 1) AS stock_key, name AS stock_name
            FROM stocks
            WHERE split_part(stock_id, '.', 1) = ANY($1::text[])
            UNION ALL
            SELECT split_part(stock_id, '.', 1) AS stock_key, stock_name
            FROM subject_stock_daily_snapshot
            WHERE split_part(stock_id, '.', 1) = ANY($1::text[])
            UNION ALL
            SELECT split_part(stock_id, '.', 1) AS stock_key, stock_name
            FROM jyhf_stock_quote_snapshot
            WHERE split_part(stock_id, '.', 1) = ANY($1::text[])
            UNION ALL
            SELECT split_part(stock_code, '.', 1) AS stock_key, stock_name
            FROM stock_theme_reason_evidence
            WHERE split_part(stock_code, '.', 1) = ANY($1::text[])
            UNION ALL
            SELECT split_part(stock_code, '.', 1) AS stock_key, stock_name
            FROM ths_hot_reason_snapshot
            WHERE split_part(stock_code, '.', 1) = ANY($1::text[])
            """,
            stock_keys,
        )
        result: dict[str, str] = {}
        for row in (dict(item) for item in rows):
            stock_key = self._stock_key(row.get("stock_key"))
            stock_name = self._text(row.get("stock_name"))
            if stock_key and self._is_valid_display_name(stock_name) and stock_key not in result:
                result[stock_key] = stock_name
        return result

    async def _fetch_theme_reason_evidence(self, conn: Any, trade_date: date, stock_keys: list[str]) -> list[dict[str, Any]]:
        if not stock_keys:
            return []
        rows = await conn.fetch(
            """
            SELECT trade_date,
                   stock_code,
                   stock_name,
                   theme_name,
                   source_name,
                   evidence_text,
                   reason_tags,
                   matched_reason_tags,
                   primary_theme,
                   confidence,
                   source_trace_id
            FROM stock_theme_reason_evidence
            WHERE trade_date = $1::date
              AND stock_code = ANY($2::text[])
            ORDER BY stock_code, primary_theme DESC, confidence DESC, theme_name
            """,
            trade_date,
            stock_keys,
        )
        return [dict(row) for row in rows]

    async def _fetch_ths_hot_reason_rows(self, conn: Any, trade_date: date, stock_keys: list[str]) -> list[dict[str, Any]]:
        if not stock_keys:
            return []
        rows = await conn.fetch(
            """
            SELECT trade_date,
                   stock_code,
                   stock_name,
                   reason_raw,
                   reason_tags,
                   source_name,
                   source_trace_id
            FROM ths_hot_reason_snapshot
            WHERE trade_date = $1::date
              AND stock_code = ANY($2::text[])
            ORDER BY stock_code, source_name
            """,
            trade_date,
            stock_keys,
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
        daily_rows = [dict(row) for row in rows]
        existing_keys = {
            self._text(row.get("canonical_subject_key"))
            for row in daily_rows
            if self._text(row.get("canonical_subject_key"))
        }
        existing_names = {
            self._text(row.get("mainline_name"))
            for row in daily_rows
            if self._text(row.get("mainline_name"))
        }

        registry_rows = await conn.fetch(
            """
            SELECT mainline_id,
                   mainline_name,
                   canonical_subject_key,
                   mainline_type,
                   core_subject_keys_json,
                   branch_subject_keys_json,
                   related_subject_keys_json
            FROM mainline_registry
            WHERE identity_status = 'confirmed'
              AND valid_from <= $1::date
              AND (valid_to IS NULL OR valid_to >= $1::date)
            ORDER BY valid_from DESC, mainline_id
            """,
            trade_date,
        )
        for raw in registry_rows:
            row = dict(raw)
            canonical_key = self._text(row.get("canonical_subject_key"))
            mainline_name = self._text(row.get("mainline_name"))
            if (
                self._is_invalid_theme_name(mainline_name)
                or not canonical_key
                or canonical_key in existing_keys
                or mainline_name in existing_names
            ):
                continue
            active_keys = self._unique_keep_order([
                canonical_key,
                mainline_name,
                *[self._text(item) for item in self._json_list(row.get("core_subject_keys_json"))],
                *[self._text(item) for item in self._json_list(row.get("branch_subject_keys_json"))],
                *[self._text(item) for item in self._json_list(row.get("related_subject_keys_json"))],
            ])
            daily_rows.append({
                "id": self._text(row.get("mainline_id")) or canonical_key,
                "canonical_subject_key": canonical_key,
                "mainline_name": mainline_name,
                "active_subject_keys_json": active_keys,
                "lifecycle_state": "",
                "mainline_alive": True,
                "mainline_trade_alive": True,
                "trade_mode": self._text(row.get("mainline_type")),
                "allow_trade": True,
                "_source": "mainline_registry",
            })
            existing_keys.add(canonical_key)
            existing_names.add(mainline_name)
        return daily_rows

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
            bucket_key = self._mainline_bucket_key(row, len(index))
            canonical_key = self._text(row.get("canonical_subject_key"))
            if self._is_valid_subject_key(canonical_key):
                indexed = dict(row)
                indexed["_bucket_key"] = bucket_key
                indexed["_match_type"] = "canonical_subject_key"
                index.setdefault(canonical_key, []).append(indexed)
            for key in {
                self._text(item)
                for item in self._json_list(row.get("active_subject_keys_json"))
                if active_key_counts.get(self._text(item), 0) == 1
            }:
                if self._is_valid_subject_key(key) and key != canonical_key:
                    indexed = dict(row)
                    indexed["_bucket_key"] = bucket_key
                    indexed["_match_type"] = "active_subject_keys_json"
                    index.setdefault(key, []).append(indexed)
        return index

    def _resolve_primary_mainline(
        self,
        *,
        stock_key: str,
        subject_rows: list[dict[str, Any]],
        mainline_index: dict[str, list[dict[str, Any]]],
        ranked_subject_keys: set[str],
    ) -> dict[str, Any]:
        ranked_rows = sorted(
            subject_rows,
            key=lambda item: (
                0 if self._text(item.get("subject_key")) in ranked_subject_keys else 1,
                int(item.get("sort") or 999999),
                self._text(item.get("subject_key")),
            ),
        )
        canonical_matches: dict[str, dict[str, Any]] = {}
        active_matches: dict[str, dict[str, Any]] = {}
        for row in ranked_rows:
            subject_key = self._text(row.get("subject_key"))
            for mainline in mainline_index.get(subject_key, []):
                mainline_name = self._text(mainline.get("mainline_name"))
                bucket_key = self._text(mainline.get("_bucket_key"))
                if self._is_invalid_theme_name(mainline_name) or not bucket_key:
                    continue
                resolved = {
                    "subject_key": self._text(mainline.get("canonical_subject_key") or subject_key),
                    "theme_name": mainline_name,
                    "mainline_name": mainline_name,
                    "bucket_key": bucket_key,
                    "active_mainline": bool(mainline.get("mainline_alive") or mainline.get("mainline_trade_alive")),
                    "lifecycle_state": self._text(mainline.get("lifecycle_state")),
                    "trade_action": self._text(mainline.get("trade_mode")),
                    "mapping_source": self._text(mainline.get("_match_type")) or "mainline_daily_state",
                }
                if self._text(mainline.get("_match_type")) == "canonical_subject_key":
                    canonical_matches.setdefault(bucket_key, resolved)
                else:
                    active_matches.setdefault(bucket_key, resolved)

        if len(canonical_matches) == 1:
            return {"resolved": next(iter(canonical_matches.values())), "ambiguous_matches": []}
        if len(canonical_matches) > 1:
            return {"resolved": None, "ambiguous_matches": list(canonical_matches.values())}
        if len(active_matches) == 1:
            return {"resolved": next(iter(active_matches.values())), "ambiguous_matches": []}
        if len(active_matches) > 1:
            return {"resolved": None, "ambiguous_matches": list(active_matches.values())}
        return {"resolved": None, "ambiguous_matches": []}

    def _resolve_primary_subject_theme(
        self,
        *,
        subject_rows: list[dict[str, Any]],
        subject_name_by_key: dict[str, str],
        ranked_subject_keys: set[str],
    ) -> dict[str, Any] | None:
        ranked_rows = sorted(
            subject_rows,
            key=lambda item: (
                0 if self._text(item.get("subject_key")) in ranked_subject_keys else 1,
                int(item.get("sort") or 999999),
                -float(item.get("confidence") or 0),
                self._text(item.get("subject_key")),
            ),
        )
        for row in ranked_rows:
            subject_key = self._text(row.get("subject_key"))
            theme_name = subject_name_by_key.get(subject_key, "")
            if self._is_valid_subject_key(subject_key) and not self._is_invalid_theme_name(theme_name):
                return {
                    "subject_key": subject_key,
                    "theme_name": theme_name,
                    "mainline_name": "",
                    "bucket_key": f"subject:{subject_key}",
                    "active_mainline": False,
                    "lifecycle_state": "",
                    "trade_action": "rotation_watch",
                    "mapping_source": "subject_stock_map",
                }
        return None

    def _build_reason_evidence_index(self, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            stock_key = self._stock_key(row.get("stock_code"))
            theme_name = self._text(row.get("theme_name"))
            if stock_key and not self._is_invalid_theme_name(theme_name):
                result[stock_key].append(row)
        for stock_key in list(result):
            result[stock_key].sort(
                key=lambda item: (
                    0 if bool(item.get("primary_theme")) else 1,
                    -float(item.get("confidence") or 0),
                    self._text(item.get("theme_name")),
                )
            )
        return result

    def _build_ths_reason_index(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            stock_key = self._stock_key(row.get("stock_code"))
            if stock_key and stock_key not in result:
                result[stock_key] = row
        return result

    def _resolve_primary_reason_evidence(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        primary = rows[0]
        theme_name = self._text(primary.get("theme_name"))
        if self._is_invalid_theme_name(theme_name):
            return None
        secondary_themes = self._unique_keep_order([
            self._text(row.get("theme_name"))
            for row in rows[1:]
            if not self._is_invalid_theme_name(row.get("theme_name"))
        ])
        return {
            "subject_key": f"reason:{theme_name}",
            "theme_name": theme_name,
            "mainline_name": "",
            "bucket_key": f"reason:{theme_name}",
            "active_mainline": False,
            "lifecycle_state": "",
            "trade_action": "rotation_watch",
            "mapping_source": "stock_theme_reason_evidence",
            "chosen_source": self._text(primary.get("source_name")) or "stock_theme_reason_evidence",
            "reason_raw": self._text(primary.get("evidence_text")),
            "matched_reason_tags": self._json_list(primary.get("matched_reason_tags")),
            "reason_tags": self._json_list(primary.get("reason_tags")),
            "primary_theme": theme_name,
            "secondary_themes": secondary_themes,
            "confidence": self._float_or_none(primary.get("confidence")),
            "source_trace_id": self._text(primary.get("source_trace_id")),
        }

    async def _resolve_ths_reason_theme(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        stock_code = self._stock_key(row.get("stock_code"))
        stock_name = self._text(row.get("stock_name"))
        reason_tags = self._json_list(row.get("reason_tags"))
        match = await self._reason_theme_resolver.resolve(reason_tags, stock_code, stock_name)
        theme_name = self._text(match.primary_theme)
        if self._is_invalid_theme_name(theme_name):
            return None
        matched_tags = match.matched_reason_tags.get(theme_name, []) if match.matched_reason_tags else []
        return {
            "subject_key": f"reason:{theme_name}",
            "theme_name": theme_name,
            "mainline_name": "",
            "bucket_key": f"reason:{theme_name}",
            "active_mainline": False,
            "lifecycle_state": "",
            "trade_action": "rotation_watch",
            "mapping_source": "ths_hot_reason_snapshot",
            "chosen_source": self._text(row.get("source_name")) or "ths",
            "reason_raw": self._text(row.get("reason_raw")),
            "matched_reason_tags": matched_tags,
            "reason_tags": reason_tags,
            "primary_theme": theme_name,
            "secondary_themes": list(match.secondary_themes or []),
            "confidence": self._float_or_none(match.confidence),
            "source_trace_id": self._text(row.get("source_trace_id")),
        }

    @staticmethod
    def _non_mainline_bucket(columns: dict[str, dict[str, Any]], resolved: dict[str, Any]) -> dict[str, Any]:
        subject_key = LimitUpThemeMatrixBuilder._text(resolved.get("subject_key"))
        theme_name = LimitUpThemeMatrixBuilder._text(resolved.get("theme_name"))
        bucket_key = LimitUpThemeMatrixBuilder._text(resolved.get("bucket_key")) or f"subject:{subject_key}"
        mapping_source = LimitUpThemeMatrixBuilder._text(resolved.get("mapping_source")) or "subject_stock_map"
        if bucket_key not in columns:
            columns[bucket_key] = {
                "subject_key": subject_key,
                "theme_name": theme_name,
                "mainline_name": "",
                "limit_up_count": 0,
                "active_mainline": False,
                "lifecycle_state": "",
                "trade_action": LimitUpThemeMatrixBuilder._text(resolved.get("trade_action")) or "rotation_watch",
                "focus_stocks": [],
                "catalyst_events": [],
                "diagnostics": {"mapping_source": mapping_source},
                "_board_groups": {1: [], 2: [], 3: [], 4: []},
                "_stock_keys": set(),
                "_order": 100000,
            }
        return columns[bucket_key]

    def _append_stock_to_bucket(
        self,
        *,
        bucket: dict[str, Any],
        row: dict[str, Any],
        stock_key: str,
        stock_name: str,
        board_count: int,
        subject_key: str,
        theme_name: str,
    ) -> None:
        stock_identity = stock_key or stock_name
        if stock_identity in bucket["_stock_keys"]:
            return
        bucket["_stock_keys"].add(stock_identity)
        stock = {
            "stock_id": self._text(row.get("stock_id") or stock_key),
            "stock_name": stock_name if self._is_valid_display_name(stock_name) else "",
            "subject_key": subject_key,
            "theme_name": theme_name,
            "board_count": board_count,
            "pct_chg": self._float_or_none(row.get("pct_chg")),
            "close_price": self._float_or_none(row.get("close_price")),
            "amount": self._float_or_none(row.get("amount")),
        }
        bucket["_board_groups"][board_count].append(stock)
        bucket["focus_stocks"].append(stock)

    def _assignment_audit_row(
        self,
        *,
        row: dict[str, Any],
        stock_name: str,
        board_count: int,
        subject_rows: list[dict[str, Any]],
        ranked_subject_keys: set[str],
        mainline_index: dict[str, list[dict[str, Any]]],
        resolved: dict[str, Any] | None,
        ambiguous_matches: list[dict[str, Any]],
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
        chosen_items = ambiguous_matches if ambiguous_matches else ([resolved] if resolved else [])
        result = {
            "stock_id": self._text(row.get("stock_id")),
            "stock_name": stock_name,
            "board_count": board_count,
            "all_subject_keys": self._unique_keep_order(all_subject_keys),
            "all_subject_names": self._unique_keep_order(all_subject_names),
            "ranked_subject_keys_hit": self._unique_keep_order(ranked_hits),
            "mainline_matches": self._unique_keep_order(mainline_matches),
            "mainline_hit": bool(resolved) and not ambiguous_matches,
        }
        result.update(self._audit_resolution_fields(resolved, ambiguous_matches))
        if not chosen_items:
            result["chosen_reason"] = "no_mainline_mapping"
            result["chosen_source"] = ""
        return result

    def _audit_resolution_fields(
        self,
        resolved: dict[str, Any] | None,
        ambiguous_matches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        chosen_items = ambiguous_matches if ambiguous_matches else ([resolved] if resolved else [])
        chosen_theme_names = self._unique_keep_order([self._text(item.get("theme_name")) for item in chosen_items])
        chosen_subject_keys = self._unique_keep_order([self._text(item.get("subject_key")) for item in chosen_items])
        primary_theme = self._text(resolved.get("primary_theme") if resolved else "") or (
            chosen_theme_names[0] if chosen_theme_names and not ambiguous_matches else ""
        )
        secondary_themes = list(resolved.get("secondary_themes") or []) if resolved else []
        return {
            "chosen_subject_key": "、".join(chosen_subject_keys),
            "chosen_theme_name": "、".join(chosen_theme_names),
            "chosen_reason": "ambiguous_mainline_mapping" if ambiguous_matches else (
                self._text(resolved.get("mapping_source")) if resolved else "no_mainline_mapping"
            ),
            "chosen_source": self._text(resolved.get("chosen_source") if resolved else "") or (
                self._text(resolved.get("mapping_source") if resolved else "")
            ),
            "reason_raw": self._text(resolved.get("reason_raw") if resolved else ""),
            "matched_reason_tags": list(resolved.get("matched_reason_tags") or []) if resolved else [],
            "reason_tags": list(resolved.get("reason_tags") or []) if resolved else [],
            "primary_theme": primary_theme,
            "secondary_themes": secondary_themes,
            "reason_confidence": self._float_or_none(resolved.get("confidence") if resolved else None),
            "source_trace_id": self._text(resolved.get("source_trace_id") if resolved else ""),
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

    def _collapse_tail_columns(
        self,
        *,
        columns: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
        max_columns: int,
    ) -> dict[str, Any]:
        if len(columns) <= max_columns and not diagnostics:
            return {
                "columns": columns,
                "true_other_count": 0,
                "collapsed_other_count": 0,
                "display_other_count": 0,
                "collapsed_other_themes": [],
            }
        keep: list[dict[str, Any]] = []
        tail: list[dict[str, Any]] = []
        keep_limit = max(1, max_columns - 1)
        for index, col in enumerate(columns):
            if index < keep_limit:
                keep.append(col)
            else:
                tail.append(col)
        other_stocks_by_board: dict[int, list[dict[str, Any]]] = {1: [], 2: [], 3: [], 4: []}
        seen: set[str] = set()
        collapsed_theme_stats: list[dict[str, Any]] = []
        for col in tail:
            collapsed_count = self._column_stock_count(col)
            if collapsed_count > 0:
                collapsed_theme_stats.append({
                    "theme_name": self._text(col.get("theme_name")),
                    "subject_key": self._text(col.get("subject_key")),
                    "limit_up_count": collapsed_count,
                    "mapping_source": self._text((col.get("diagnostics") or {}).get("mapping_source")),
                })
            for group in col.get("board_groups") or []:
                board_count = int(group.get("board_count") or 0)
                if board_count not in other_stocks_by_board:
                    continue
                for stock in group.get("stocks") or []:
                    stock_id = self._text(stock.get("stock_id"))
                    stock_name = self._text(stock.get("stock_name"))
                    identity = stock_id or stock_name
                    if not identity or identity in seen or not self._is_valid_display_name(stock_name):
                        continue
                    seen.add(identity)
                    other_stocks_by_board[board_count].append(dict(stock))
        collapsed_other_count = len(seen)
        for row in diagnostics:
            board_count = int(row.get("board_count") or 0)
            stock_name = self._text(row.get("stock_name"))
            stock_id = self._text(row.get("stock_id"))
            identity = stock_id or stock_name
            if board_count not in other_stocks_by_board or not identity or identity in seen or not self._is_valid_display_name(stock_name):
                continue
            seen.add(identity)
            other_stocks_by_board[board_count].append({
                "stock_id": stock_id,
                "stock_name": stock_name,
                "subject_key": "other",
                "theme_name": "其他",
                "board_count": board_count,
            })
        if not any(other_stocks_by_board.values()):
            return {
                "columns": keep,
                "true_other_count": len(diagnostics),
                "collapsed_other_count": collapsed_other_count,
                "display_other_count": 0,
                "collapsed_other_themes": collapsed_theme_stats,
            }
        display_other_count = sum(len(items) for items in other_stocks_by_board.values())
        other_bucket = {
            "subject_key": "other",
            "theme_name": "其他",
            "mainline_name": "",
            "limit_up_count": 0,
            "active_mainline": False,
            "lifecycle_state": "",
            "trade_action": "rotation_watch",
            "focus_stocks": [],
            "catalyst_events": [],
            "diagnostics": {
                "mapping_source": "collapsed_tail",
                "true_other_count": len(diagnostics),
                "collapsed_other_count": collapsed_other_count,
                "display_other_count": display_other_count,
                "collapsed_other_themes": collapsed_theme_stats,
            },
            "_board_groups": other_stocks_by_board,
            "_stock_keys": set(),
            "_order": 999999,
        }
        return {
            "columns": [*keep, self._finalize_column(other_bucket)],
            "true_other_count": len(diagnostics),
            "collapsed_other_count": collapsed_other_count,
            "display_other_count": display_other_count,
            "collapsed_other_themes": collapsed_theme_stats,
        }

    def _merge_market_columns_by_theme(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for column in columns:
            theme_name = self._text(column.get("theme_name"))
            if not theme_name:
                continue
            display_theme_name = self._display_theme_name(theme_name)
            target = merged.get(display_theme_name)
            if target is None:
                original_theme_names = [] if display_theme_name == theme_name else [theme_name]
                target = {
                    **column,
                    "theme_name": display_theme_name,
                    "focus_stocks": [],
                    "board_groups": [
                        {
                            "board_count": board_count,
                            "board_label": "首板" if board_count == 1 else f"{board_count}板",
                            "stock_count": 0,
                            "stocks": [],
                        }
                        for board_count in (4, 3, 2, 1)
                    ],
                    "_seen_stock_ids": set(),
                    "_merged_theme_aliases": original_theme_names,
                }
                target["diagnostics"] = self._with_display_theme_diagnostics(
                    target.get("diagnostics") or {},
                    display_theme_name=display_theme_name,
                    original_theme_name=theme_name,
                )
                merged[display_theme_name] = target
            else:
                target["active_mainline"] = bool(target.get("active_mainline")) or bool(column.get("active_mainline"))
                target["diagnostics"] = self._merge_column_diagnostics(
                    target.get("diagnostics") or {},
                    column.get("diagnostics") or {},
                )
                aliases = target.setdefault("_merged_theme_aliases", [])
                if theme_name != display_theme_name and theme_name not in aliases:
                    aliases.append(theme_name)
            group_by_board = {
                int(group.get("board_count") or 0): group
                for group in target.get("board_groups") or []
            }
            for group in column.get("board_groups") or []:
                board_count = int(group.get("board_count") or 0)
                target_group = group_by_board.get(board_count)
                if target_group is None:
                    continue
                for stock in group.get("stocks") or []:
                    stock_id = self._text(stock.get("stock_id"))
                    stock_name = self._text(stock.get("stock_name"))
                    identity = stock_id or stock_name
                    if not identity or identity in target["_seen_stock_ids"]:
                        continue
                    target["_seen_stock_ids"].add(identity)
                    display_stock = {
                        **dict(stock),
                        "theme_name": display_theme_name,
                    }
                    target_group["stocks"].append(display_stock)
                    target["focus_stocks"].append(display_stock)
        result: list[dict[str, Any]] = []
        for column in merged.values():
            limit_up_count = 0
            for group in column.get("board_groups") or []:
                stocks = group.get("stocks") or []
                group["stock_count"] = len(stocks)
                limit_up_count += len(stocks)
            column["limit_up_count"] = limit_up_count
            aliases = column.pop("_merged_theme_aliases", [])
            if aliases:
                diagnostics = column.get("diagnostics") or {}
                diagnostics["merged_theme_aliases"] = self._unique_keep_order(list(diagnostics.get("merged_theme_aliases") or []) + aliases)
                column["diagnostics"] = diagnostics
            column.pop("_seen_stock_ids", None)
            result.append(column)
        return result

    @staticmethod
    def _merge_column_diagnostics(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        left_source = LimitUpThemeMatrixBuilder._text(left.get("mapping_source"))
        right_source = LimitUpThemeMatrixBuilder._text(right.get("mapping_source"))
        sources = LimitUpThemeMatrixBuilder._unique_keep_order([left_source, right_source])
        aliases = LimitUpThemeMatrixBuilder._unique_keep_order(
            list(left.get("merged_theme_aliases") or []) + list(right.get("merged_theme_aliases") or [])
        )
        return {
            **left,
            **right,
            "mapping_source": sources[0] if len(sources) == 1 else "+".join(sources),
            "merged_mapping_sources": sources,
            "merged_theme_aliases": aliases,
        }

    @classmethod
    def _display_theme_name(cls, theme_name: str) -> str:
        return cls.display_theme_aliases.get(cls._text(theme_name), cls._text(theme_name))

    @classmethod
    def _with_display_theme_diagnostics(
        cls,
        diagnostics: dict[str, Any],
        *,
        display_theme_name: str,
        original_theme_name: str,
    ) -> dict[str, Any]:
        if display_theme_name == original_theme_name:
            return diagnostics
        aliases = cls._unique_keep_order(list(diagnostics.get("merged_theme_aliases") or []) + [original_theme_name])
        return {
            **diagnostics,
            "display_theme_name": display_theme_name,
            "merged_theme_aliases": aliases,
        }

    @staticmethod
    def _column_stock_count(column: dict[str, Any]) -> int:
        return sum(
            int(group.get("stock_count") or 0)
            for group in column.get("board_groups") or []
        )

    @staticmethod
    def _market_column_sort_key(column: dict[str, Any]) -> tuple[int, int, str]:
        source = LimitUpThemeMatrixBuilder._text((column.get("diagnostics") or {}).get("mapping_source"))
        sources = set(source.split("+")) if source else set()
        if "mainline_daily_state" in sources:
            source_priority = 0
        elif "stock_theme_reason_evidence" in sources:
            source_priority = 1
        elif "ths_hot_reason_snapshot" in sources:
            source_priority = 2
        elif "subject_stock_map" in sources:
            source_priority = 3
        else:
            source_priority = 9
        return (
            -LimitUpThemeMatrixBuilder._column_stock_count(column),
            source_priority,
            LimitUpThemeMatrixBuilder._text(column.get("theme_name")),
        )

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
    def _market_board_totals(limit_up_rows: list[dict[str, Any]], board_by_stock: dict[str, int]) -> dict[str, int]:
        totals = {"4": 0, "3": 0, "2": 0, "1": 0}
        for row in limit_up_rows:
            stock_key = LimitUpThemeMatrixBuilder._text(row.get("stock_key"))
            board_count = board_by_stock.get(stock_key, 0)
            key = str(board_count)
            if key in totals:
                totals[key] += 1
        return totals

    @staticmethod
    def _summary(columns: list[dict[str, Any]], market_board_totals: dict[str, int], mainline_board_totals: dict[str, int]) -> str:
        hot = "、".join([str(col.get("theme_name") or "") for col in columns[:3] if col.get("theme_name")]) or "暂无"
        return (
            f"全市场连板：4板 {market_board_totals.get('4', 0)} 只，"
            f"3板 {market_board_totals.get('3', 0)} 只，2板 {market_board_totals.get('2', 0)} 只，"
            f"首板 {market_board_totals.get('1', 0)} 只；"
            f"主线矩阵：4板 {mainline_board_totals.get('4', 0)} 只，"
            f"3板 {mainline_board_totals.get('3', 0)} 只，2板 {mainline_board_totals.get('2', 0)} 只，"
            f"首板 {mainline_board_totals.get('1', 0)} 只；热点题材：{hot}。"
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
    def _unique_keep_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

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
    def _resolve_stock_name(cls, row: dict[str, Any], subject_rows: list[dict[str, Any]], stock_name_by_key: dict[str, str] | None = None) -> str:
        stock_key = cls._stock_key(row.get("stock_key") or row.get("stock_id"))
        if stock_name_by_key and stock_key:
            mapped = cls._text(stock_name_by_key.get(stock_key))
            if cls._is_valid_display_name(mapped):
                return mapped
        snapshot_name = cls._text(row.get("stock_name"))
        if cls._is_valid_display_name(snapshot_name):
            return snapshot_name
        for subject_row in subject_rows:
            mapped_name = cls._text(subject_row.get("stock_name"))
            if cls._is_valid_display_name(mapped_name):
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

    @classmethod
    def _is_valid_display_name(cls, value: Any) -> bool:
        text = cls._text(value)
        if not text or text.isdigit():
            return False
        upper = text.upper()
        if "." in upper:
            left, right = upper.split(".", 1)
            if left.isdigit() and right in {"SH", "SZ", "BJ"}:
                return False
        return True

    @classmethod
    def _is_excluded_stock(cls, stock_key: Any, stock_name: Any) -> bool:
        key = cls._stock_key(stock_key)
        name = cls._text(stock_name).upper()
        return key.startswith("688") or key.startswith("920") or "ST" in name

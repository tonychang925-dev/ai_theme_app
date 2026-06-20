from __future__ import annotations

from typing import Any


class PostMarketHotspotOverviewComposer:
    """Compose structured hotspot overview rows from existing recap data.

    This only interprets already-computed engine outputs. It does not recalculate
    any trading signal, D1 state, or Layer C state.
    """

    def compose(self, recap_doc: dict[str, Any] | None) -> dict[str, Any]:
        recap_doc = recap_doc or {}

        market_overview_review = self._dict(recap_doc.get("market_overview_review"))
        market_summary = self._dict(recap_doc.get("market_summary"))
        theme_capital_reviews = self._list_of_dicts(recap_doc.get("theme_capital_reviews"))
        mainline_daily_states = self._list_of_dicts(recap_doc.get("mainline_daily_states"))
        post_market_decision_v2 = self._dict(recap_doc.get("post_market_decision_v2"))

        theme_limitup_matrix = self._dict(market_overview_review.get("theme_limitup_matrix"))
        matrix_columns = self._list_of_dicts(theme_limitup_matrix.get("columns"))
        strong_stock_pool_reviews = self._list_of_dicts(post_market_decision_v2.get("strong_stock_pool_reviews"))
        theme_count = len(matrix_columns) if matrix_columns else None

        buckets: dict[str, dict[str, Any]] = {}
        source_tables: set[str] = set()

        for row in theme_capital_reviews:
            key = self._theme_key(row.get("subject_key"), row.get("theme_name"))
            if not key:
                continue
            bucket = self._bucket(buckets, key)
            source_tables.add("theme_capital_reviews")
            bucket["subject_key"] = bucket["subject_key"] or self._clean_text(row.get("subject_key"), "")
            bucket["theme_name"] = bucket["theme_name"] or self._display_theme_name(row.get("theme_name"), bucket["subject_key"] or "题材")
            bucket["total_inflow"] = self._prefer_number(bucket["total_inflow"], self._float_or_none(row.get("total_inflow")))
            bucket["top3_inflow"] = self._prefer_number(bucket["top3_inflow"], self._float_or_none(row.get("top3_inflow")))
            bucket["leader_inflow"] = self._prefer_number(bucket["leader_inflow"], self._float_or_none(row.get("leader_inflow")))
            bucket["strong_stock_count"] = bucket["strong_stock_count"] or self._int_or_none(row.get("inflow_stock_count"))
            bucket["lifecycle_state"] = bucket["lifecycle_state"] or self._clean_text(row.get("cycle_stage"), "")
            bucket["action_advice"] = bucket["action_advice"] or self._clean_text(row.get("action"), "")
            bucket["theme_kline"] = bucket["theme_kline"] or self._clean_text(row.get("theme_kline"), "")
            bucket["rank_hint"] = min(bucket["rank_hint"], self._int_or_none(row.get("rank_order")) or 9999)
            bucket["source_flags"].add("theme_capital_reviews")

        for row in matrix_columns:
            key = self._theme_key(row.get("subject_key"), row.get("theme_name"))
            if not key:
                continue
            bucket = self._bucket(buckets, key)
            source_tables.add("market_overview_review")
            bucket["subject_key"] = bucket["subject_key"] or self._clean_text(row.get("subject_key"), "")
            bucket["theme_name"] = bucket["theme_name"] or self._display_theme_name(row.get("theme_name"), bucket["subject_key"] or "题材")
            bucket["limit_up_count"] = self._prefer_number(bucket["limit_up_count"], self._int_or_none(row.get("limit_up_count")))
            bucket["lifecycle_state"] = bucket["lifecycle_state"] or self._clean_text(row.get("lifecycle_state"), "")
            bucket["action_advice"] = bucket["action_advice"] or self._clean_text(row.get("trade_action"), "")
            bucket["is_confirmed_mainline"] = bucket["is_confirmed_mainline"] or bool(row.get("active_mainline"))
            bucket["matrix_focus_stocks"] = self._merge_focus_stocks(bucket["matrix_focus_stocks"], row.get("focus_stocks"))
            bucket["rank_hint"] = min(bucket["rank_hint"], self._int_or_none(row.get("rank_order")) or 9999)
            bucket["source_flags"].add("market_overview_review")

        for row in mainline_daily_states:
            key = self._theme_key(row.get("canonical_subject_key"), row.get("mainline_name"), row.get("mainline_id"))
            if not key:
                continue
            bucket = self._bucket(buckets, key)
            source_tables.add("mainline_daily_states")
            bucket["subject_key"] = bucket["subject_key"] or self._clean_text(row.get("canonical_subject_key"), "")
            bucket["theme_name"] = bucket["theme_name"] or self._display_theme_name(row.get("mainline_name"), bucket["subject_key"] or "主线")
            bucket["lifecycle_state"] = bucket["lifecycle_state"] or self._clean_text(row.get("lifecycle_state"), "")
            bucket["action_advice"] = bucket["action_advice"] or self._clean_text(row.get("action_advice"), "")
            bucket["mainline_name"] = bucket["mainline_name"] or self._clean_text(row.get("mainline_name"), "")
            bucket["is_confirmed_mainline"] = bool(bucket["is_confirmed_mainline"] or self._is_confirmed_mainline_state(row))
            bucket["mainline_strength_score"] = self._prefer_number(
                bucket["mainline_strength_score"],
                self._float_or_none(row.get("mainline_strength_score")),
            )
            bucket["fade_risk_score"] = self._prefer_number(bucket["fade_risk_score"], self._float_or_none(row.get("fade_risk_score")))
            bucket["strong_pool_count"] = bucket["strong_pool_count"] or self._int_or_none(row.get("strong_pool_count"))
            bucket["d1_count"] = bucket["d1_count"] or self._int_or_none(row.get("d1_count"))
            bucket["focus_count"] = bucket["focus_count"] or self._int_or_none(row.get("focus_count"))
            bucket["source_flags"].add("mainline_daily_states")

        for row in strong_stock_pool_reviews:
            key = self._resolve_bucket_key(
                buckets,
                row.get("subject_key"),
                row.get("theme_name"),
                row.get("mainline_name"),
                row.get("resolved_theme_name"),
            )
            if not key:
                continue
            bucket = self._bucket(buckets, key)
            source_tables.add("post_market_decision_v2.strong_stock_pool_reviews")
            bucket["subject_key"] = bucket["subject_key"] or self._clean_text(row.get("subject_key"), "")
            bucket["theme_name"] = bucket["theme_name"] or self._display_theme_name(
                row.get("theme_name") or row.get("mainline_name") or row.get("resolved_theme_name"),
                bucket["subject_key"] or "题材",
            )
            bucket["strong_stock_pool_rows"].append(row)
            bucket["source_flags"].add("post_market_decision_v2.strong_stock_pool_reviews")
            bucket["strong_stock_count"] = self._int_or_none(len(bucket["strong_stock_pool_rows"]))

        rows: list[dict[str, Any]] = []
        for key, bucket in buckets.items():
            theme_name = self._clean_text(bucket.get("theme_name"), self._clean_text(bucket.get("subject_key"), "题材"))
            subject_key = self._clean_text(bucket.get("subject_key"), self._clean_text(key, theme_name))
            mainline_name = self._clean_text(bucket.get("mainline_name"), "")
            is_confirmed_mainline = bool(bucket.get("is_confirmed_mainline"))
            lifecycle_state = self._clean_text(bucket.get("lifecycle_state"), "")
            limit_up_count = self._int_or_none(bucket.get("limit_up_count"))
            strong_stock_count = self._int_or_none(bucket.get("strong_stock_count"))
            representative_stocks = self._build_representative_stocks(
                matrix_focus_stocks=bucket.get("matrix_focus_stocks"),
                strong_stock_pool_rows=bucket.get("strong_stock_pool_rows"),
            )
            first_board_count, consecutive_board_count = self._board_counts(bucket.get("matrix_focus_stocks"))
            if strong_stock_count is None:
                strong_stock_count = len(representative_stocks) or None

            total_inflow = self._float_or_none(bucket.get("total_inflow"))
            top3_inflow = self._float_or_none(bucket.get("top3_inflow"))
            leader_inflow = self._float_or_none(bucket.get("leader_inflow"))
            action_advice = self._clean_text(bucket.get("action_advice"), "")
            if not action_advice:
                action_advice = self._action_from_lifecycle(lifecycle_state, is_confirmed_mainline)
            heat_score = self._heat_score(
                limit_up_count=limit_up_count,
                strong_stock_count=strong_stock_count,
                total_inflow=total_inflow,
                lifecycle_state=lifecycle_state,
                is_confirmed_mainline=is_confirmed_mainline,
            )
            rows.append({
                "subject_key": subject_key,
                "theme_name": theme_name,
                "limit_up_count": limit_up_count,
                "first_board_count": first_board_count,
                "consecutive_board_count": consecutive_board_count,
                "strong_stock_count": strong_stock_count,
                "representative_stocks": representative_stocks,
                "total_inflow": total_inflow,
                "top3_inflow": top3_inflow,
                "leader_inflow": leader_inflow,
                "lifecycle_state": lifecycle_state or None,
                "is_confirmed_mainline": is_confirmed_mainline,
                "mainline_name": mainline_name or None,
                "action_advice": action_advice or None,
                "heat_score": heat_score,
                "_rank_hint": int(bucket.get("rank_hint") or 9999),
                "_source_flags": sorted(bucket.get("source_flags") or []),
            })

        rows.sort(
            key=lambda row: (
                -float(row.get("heat_score") or 0),
                -float(row.get("total_inflow") or 0),
                -(int(row.get("strong_stock_count") or 0)),
                int(row.get("_rank_hint") or 9999),
                str(row.get("theme_name") or ""),
            )
        )

        ranked_rows = rows[:10]
        for idx, row in enumerate(ranked_rows, start=1):
            row["rank_order"] = idx

        strongest_themes = [str(row.get("theme_name") or "").strip() for row in ranked_rows[:3] if str(row.get("theme_name") or "").strip()]
        mainline_related_themes = self._unique_names(
            row.get("theme_name")
            for row in ranked_rows
            if bool(row.get("is_confirmed_mainline"))
        )
        rotation_themes = self._unique_names(
            row.get("theme_name")
            for row in ranked_rows
            if not bool(row.get("is_confirmed_mainline"))
            and self._is_rotation_candidate(row)
        )
        risk_themes = self._unique_names(
            row.get("theme_name")
            for row in ranked_rows
            if self._is_risk_theme(row)
        )

        summary = self._summary(
            strongest_themes=strongest_themes,
            mainline_related_themes=mainline_related_themes,
            rotation_themes=rotation_themes,
            risk_themes=risk_themes,
            market_overview_review=market_overview_review,
            market_summary=market_summary,
            theme_count=theme_count,
        )

        source = "structured" if ranked_rows else "fallback"
        diagnostics = {
            "theme_capital_count": len(theme_capital_reviews),
            "mainline_count": len(mainline_daily_states),
            "strong_stock_pool_count": len(strong_stock_pool_reviews),
            "matrix_column_count": len(matrix_columns),
            "row_count": len(ranked_rows),
            "source_tables": sorted(source_tables),
            "limit_up_total": self._int_or_none(market_overview_review.get("limit_up_total")),
            "limit_down_total": self._int_or_none(market_overview_review.get("limit_down_total")),
        }

        return {
            "summary": summary,
            "hotspot_rows": [
                {
                    key: value
                    for key, value in row.items()
                    if not str(key).startswith("_") and key not in {"rank_hint"}
                }
                for row in ranked_rows
            ],
            "strongest_themes": strongest_themes,
            "mainline_related_themes": mainline_related_themes,
            "rotation_themes": rotation_themes,
            "risk_themes": risk_themes,
            "source": source,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _bucket(buckets: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
        bucket = buckets.setdefault(
            key,
            {
                "subject_key": "",
                "theme_name": "",
                "limit_up_count": None,
                "first_board_count": None,
                "consecutive_board_count": None,
                "strong_stock_count": None,
                "representative_stocks": [],
                "matrix_focus_stocks": [],
                "strong_stock_pool_rows": [],
                "total_inflow": None,
                "top3_inflow": None,
                "leader_inflow": None,
                "lifecycle_state": "",
                "is_confirmed_mainline": False,
                "mainline_name": "",
                "action_advice": "",
                "heat_score": 0.0,
                "rank_hint": 9999,
                "mainline_strength_score": None,
                "fade_risk_score": None,
                "strong_pool_count": None,
                "d1_count": None,
                "focus_count": None,
                "theme_kline": "",
                "source_flags": set(),
            },
        )
        return bucket

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict)]

    @staticmethod
    def _clean_text(value: Any, default: str = "--") -> str:
        text = str(value or "").strip()
        return text or default

    @staticmethod
    def _display_theme_name(value: Any, default: str = "题材") -> str:
        text = str(value or "").strip()
        if not text:
            return default
        lowered = text.lower()
        if lowered in {"__independent__", "independent", "unknown"} or text.startswith("__"):
            return "未归类"
        return text

    @staticmethod
    def _theme_key(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip().lower()
            if text:
                return "".join(ch for ch in text if not ch.isspace())
        return ""

    def _resolve_bucket_key(self, buckets: dict[str, dict[str, Any]], *values: Any) -> str:
        candidates = [self._theme_key(value) for value in values if self._theme_key(value)]
        if not candidates:
            return ""
        for existing_key, bucket in buckets.items():
            bucket_keys = {
                self._theme_key(bucket.get("subject_key")),
                self._theme_key(bucket.get("theme_name")),
                self._theme_key(bucket.get("mainline_name")),
            }
            if any(candidate in bucket_keys for candidate in candidates):
                return existing_key
        return candidates[0]

    @staticmethod
    def _prefer_number(current: Any, candidate: Any) -> Any:
        return current if current not in (None, "") else candidate

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(float(value))
        except Exception:
            return None

    def _merge_focus_stocks(self, current: Any, value: Any) -> list[dict[str, Any]]:
        existing = self._list_of_dicts(current)
        incoming = self._list_of_dicts(value)
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in existing + incoming:
            stock_id = self._clean_text(row.get("stock_id"), "")
            stock_name = self._clean_text(row.get("stock_name"), stock_id or "股票")
            key = self._theme_key(stock_id, stock_name)
            if key in seen:
                continue
            seen.add(key)
            merged.append({
                "stock_id": stock_id,
                "stock_name": stock_name,
                "board_count": self._int_or_none(row.get("board_count") or row.get("limit_up_days") or row.get("max_consecutive_limit_up_days")),
                "role_label": self._clean_text(row.get("role_label") or row.get("role") or row.get("candidate_level"), ""),
                "trade_action": self._clean_text(row.get("trade_action") or row.get("next_day_action"), ""),
                "reason": self._clean_text(row.get("reason"), ""),
            })
        return merged

    def _build_representative_stocks(
        self,
        *,
        matrix_focus_stocks: Any,
        strong_stock_pool_rows: Any,
    ) -> list[dict[str, Any]]:
        rows = self._list_of_dicts(matrix_focus_stocks)
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            stock_id = self._clean_text(row.get("stock_id"), "")
            stock_name = self._clean_text(row.get("stock_name"), stock_id or "股票")
            key = self._theme_key(stock_id, stock_name)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "stock_id": stock_id,
                "stock_name": stock_name,
                "reason": self._clean_text(row.get("reason") or row.get("role_label") or row.get("trade_action"), ""),
            })
        if candidates:
            return candidates[:3]

        strong_rows = self._list_of_dicts(strong_stock_pool_rows)
        strong_rows.sort(
            key=lambda row: (
                -float(row.get("composite_score") or row.get("capital_score") or row.get("watch_score") or 0),
                -float(row.get("main_net_inflow") or 0),
                str(row.get("stock_name") or ""),
            )
        )
        for row in strong_rows[:3]:
            stock_id = self._clean_text(row.get("stock_id"), "")
            stock_name = self._clean_text(row.get("stock_name"), stock_id or "股票")
            key = self._theme_key(stock_id, stock_name)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "stock_id": stock_id,
                "stock_name": stock_name,
                "reason": self._clean_text(row.get("role_label") or row.get("candidate_level") or row.get("rationale"), ""),
            })
        return candidates[:3]

    def _board_counts(self, focus_stocks: Any) -> tuple[int | None, int | None]:
        rows = self._list_of_dicts(focus_stocks)
        if not rows:
            return None, None
        counts = [self._int_or_none(row.get("board_count") or row.get("limit_up_days") or row.get("max_consecutive_limit_up_days")) for row in rows]
        valid = [count for count in counts if count is not None and count > 0]
        if not valid:
            return None, None
        first_board = sum(1 for count in valid if count == 1)
        consecutive_board = max(valid) if valid else None
        return (first_board or None), consecutive_board

    def _heat_score(
        self,
        *,
        limit_up_count: int | None,
        strong_stock_count: int | None,
        total_inflow: float | None,
        lifecycle_state: str,
        is_confirmed_mainline: bool,
    ) -> float:
        score = 0.0
        if total_inflow is not None:
            score += min(abs(total_inflow) / 10_000_000.0, 40.0)
        if strong_stock_count is not None:
            score += min(float(strong_stock_count) * 5.0, 30.0)
        if limit_up_count is not None:
            score += min(float(limit_up_count), 10.0)
        if is_confirmed_mainline:
            score += 20.0
        lifecycle = lifecycle_state.lower()
        if lifecycle in {"divergence", "start", "fermentation"}:
            score += 10.0
        elif lifecycle in {"watch"}:
            score += 4.0
        elif lifecycle in {"fade_watch", "fade_confirmed", "fade"}:
            score += 0.0
        return round(score, 2)

    def _summary(
        self,
        *,
        strongest_themes: list[str],
        mainline_related_themes: list[str],
        rotation_themes: list[str],
        risk_themes: list[str],
        market_overview_review: dict[str, Any],
        market_summary: dict[str, Any],
        theme_count: int | None,
    ) -> str:
        limit_up_total = self._int_or_none(market_overview_review.get("limit_up_total"))
        strongest_text = self._join_names(strongest_themes[:3]) or "暂无明确热点"
        mainline_text = self._join_names(mainline_related_themes[:3])
        rotation_text = self._join_names(rotation_themes[:3]) or "暂无明显轮动主题"
        risk_text = self._join_names(risk_themes[:3]) or "暂无明显风险主题"

        market_bias = self._clean_text(market_summary.get("market_bias"), "")
        if limit_up_total is not None and theme_count is not None:
            base = f"今日涨停 {limit_up_total} 只，热点题材 {theme_count} 个，"
        elif limit_up_total is not None:
            base = f"今日涨停 {limit_up_total} 只，"
        else:
            base = "今日热点聚焦于"
        summary = f"{base}热点集中在 {strongest_text} 等方向。"
        if mainline_text:
            summary += f"主线相关包括 {mainline_text}。"
        summary += f"轮动观察 {rotation_text}，风险主题 {risk_text}。"
        if market_bias and market_bias != "--":
            summary += f"市场定性 {market_bias}。"
        summary += "次日重点观察资金回流和核心股修复。"
        return summary

    @staticmethod
    def _join_names(values: list[str], sep: str = "、") -> str:
        items = [str(item).strip() for item in values if str(item).strip()]
        return sep.join(items)

    @staticmethod
    def _unique_names(values: Any) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(text)
        return items

    @staticmethod
    def _is_rotation_candidate(row: dict[str, Any]) -> bool:
        if int(row.get("strong_stock_count") or 0) <= 0 and int(row.get("limit_up_count") or 0) <= 0:
            return False
        lifecycle = str(row.get("lifecycle_state") or "").lower()
        action = str(row.get("action_advice") or "").strip()
        return lifecycle not in {"fade", "fade_watch", "fade_confirmed"} and action not in {"回避", "谨慎"}

    @staticmethod
    def _is_risk_theme(row: dict[str, Any]) -> bool:
        lifecycle = str(row.get("lifecycle_state") or "").lower()
        action = str(row.get("action_advice") or "").strip()
        return lifecycle in {"fade", "fade_watch", "fade_confirmed"} or action in {"回避", "谨慎"}

    @staticmethod
    def _is_confirmed_mainline_state(row: dict[str, Any]) -> bool:
        if bool(row.get("mainline_trade_alive")) or bool(row.get("mainline_alive")):
            return True
        lifecycle = str(row.get("lifecycle_state") or "").strip().lower()
        if not lifecycle:
            return bool(row.get("active_mainline"))
        if lifecycle in {"fade", "fade_watch", "fade_confirmed", "watch"}:
            return bool(row.get("active_mainline"))
        return lifecycle in {"divergence", "start", "fermentation", "active", "confirmed", "hot", "up"} or bool(row.get("active_mainline"))

    @staticmethod
    def _action_from_lifecycle(lifecycle_state: str, is_confirmed_mainline: bool) -> str:
        lifecycle = lifecycle_state.lower()
        if lifecycle in {"fade", "fade_watch", "fade_confirmed"}:
            return "回避"
        if is_confirmed_mainline:
            return "主线参与"
        if lifecycle in {"divergence", "start", "fermentation"}:
            return "轮动跟随"
        return "观察"

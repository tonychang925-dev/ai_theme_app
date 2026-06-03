from __future__ import annotations

from typing import Any


class PostMarketEvidenceLayerComposer:
    """Compose evidence-layer review from existing structured recap data.

    This class only interprets already computed evidence rows and alignment
    metadata. It must not infer new trading decisions.
    """

    def compose(
        self,
        recap_doc: dict[str, Any] | None,
        *,
        evidence_alignment_index: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recap_doc = recap_doc or {}
        alignment_index = self._dict(evidence_alignment_index or recap_doc.get("evidence_alignment_index"))
        by_stock = alignment_index.get("by_stock") if isinstance(alignment_index.get("by_stock"), dict) else {}

        mainline_daily_states = self._list_of_dicts(recap_doc.get("mainline_daily_states"))
        abnormal_reviews = self._list_of_dicts(recap_doc.get("abnormal_reviews"))
        money_flow_reviews = self._list_of_dicts(recap_doc.get("money_flow_reviews"))
        dragon_tiger_reviews = self._list_of_dicts(recap_doc.get("dragon_tiger_reviews"))
        stock_capital_reviews = self._list_of_dicts(recap_doc.get("stock_capital_reviews"))
        pdv2 = self._dict(recap_doc.get("post_market_decision_v2"))

        abnormal_evidence = self._build_items("abnormal", abnormal_reviews, by_stock)
        money_flow_evidence = self._build_items("money_flow", money_flow_reviews, by_stock)
        dragon_tiger_evidence = self._build_items("dragon_tiger", dragon_tiger_reviews, by_stock)
        stock_capital_evidence = self._build_items("stock_capital", stock_capital_reviews, by_stock)

        all_items = (
            abnormal_evidence
            + money_flow_evidence
            + dragon_tiger_evidence
            + stock_capital_evidence
        )
        groups = self._build_groups(all_items)
        summary = self._build_summary(groups, abnormal_evidence, money_flow_evidence, dragon_tiger_evidence, stock_capital_evidence)

        source = "structured" if all_items else "fallback"
        diagnostics = {
            "abnormal_count": len(abnormal_evidence),
            "money_flow_count": len(money_flow_evidence),
            "dragon_tiger_count": len(dragon_tiger_evidence),
            "stock_capital_count": len(stock_capital_evidence),
            "group_count": len(groups),
            "indexed_stocks": int(alignment_index.get("indexed_stocks") or 0) if isinstance(alignment_index, dict) else 0,
            "indexed_subjects": int(alignment_index.get("indexed_subjects") or 0) if isinstance(alignment_index, dict) else 0,
            "mainline_state_count": len(mainline_daily_states),
            "d1_count": self._count_rows(pdv2.get("weak_to_strong_d1_reviews")),
            "focus_count": self._count_rows(pdv2.get("next_day_focus_stocks")),
        }
        return {
            "summary": summary,
            "evidence_groups": groups,
            "abnormal_evidence": abnormal_evidence,
            "money_flow_evidence": money_flow_evidence,
            "dragon_tiger_evidence": dragon_tiger_evidence,
            "stock_capital_evidence": stock_capital_evidence,
            "source": source,
            "diagnostics": diagnostics,
        }

    def _build_items(
        self,
        evidence_type: str,
        rows: list[dict[str, Any]],
        by_stock: dict[str, Any],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in rows:
            item = self._build_item(evidence_type, row, by_stock)
            if item:
                items.append(item)

        items.sort(
            key=lambda item: (
                int(item.get("rank_order") or 9999),
                -float(item.get("score") or 0),
                -float(item.get("amount") or 0),
                str(item.get("stock_name") or item.get("stock_id") or ""),
            )
        )
        return items

    def _build_item(
        self,
        evidence_type: str,
        row: dict[str, Any],
        by_stock: dict[str, Any],
    ) -> dict[str, Any] | None:
        stock_id = self._first_text(
            row.get("stock_id"),
            row.get("stock_code"),
            row.get("code"),
        )
        stock_name = self._first_text(row.get("stock_name"), row.get("name"))
        subject_key = self._first_text(row.get("subject_key"), row.get("theme_subject_key"))
        theme_name = self._first_text(row.get("theme_name"), row.get("subject_name"), row.get("resolved_theme_name"))
        title = self._build_title(evidence_type, row, stock_name, theme_name)
        description = self._build_description(evidence_type, row)
        if not title and not description and not stock_id and not stock_name:
            return None

        alignment = self._alignment_for_stock(stock_id, by_stock)
        active_mainline = bool(self._first_present(row, alignment, "active_mainline"))
        mainline_name = self._first_text(self._first_present(row, alignment, "mainline_name"), theme_name)
        lifecycle_state = self._first_text(self._first_present(row, alignment, "lifecycle_state"))
        in_layer_c = bool(self._first_present(row, alignment, "in_layer_c"))
        is_d1_candidate = bool(self._first_present(row, alignment, "is_d1_candidate"))
        is_focus_stock = bool(self._first_present(row, alignment, "is_focus_stock"))
        trade_action = self._first_text(self._first_present(row, alignment, "trade_action"), self._fallback_trade_action(evidence_type, row, alignment))
        score = self._float_or_none(self._first_present(row, "score", "abnormal_score", "watch_score", "mainline_strength_score"))
        if score is None:
            score = self._fallback_score(evidence_type, row, alignment)
        amount = self._float_or_none(self._first_present(row, "amount", "main_net_inflow", "net_buy", "total_inflow", "leader_inflow"))
        if amount is None:
            amount = self._fallback_amount(evidence_type, row)
        rank_order = self._int_or_none(self._first_present(row, "rank_order", "rank_overall", "rank_in_theme"))
        tags = self._build_tags(evidence_type, row, alignment, active_mainline, in_layer_c, is_d1_candidate, is_focus_stock, lifecycle_state, trade_action)

        return {
            "evidence_type": evidence_type,
            "stock_id": stock_id or None,
            "stock_code": stock_id or None,
            "stock_name": stock_name or None,
            "subject_key": subject_key or None,
            "theme_name": theme_name or None,
            "title": title,
            "description": description,
            "score": score,
            "amount": amount,
            "active_mainline": active_mainline,
            "mainline_name": mainline_name or None,
            "lifecycle_state": lifecycle_state or None,
            "in_layer_c": in_layer_c,
            "is_d1_candidate": is_d1_candidate,
            "is_focus_stock": is_focus_stock,
            "trade_action": trade_action or None,
            "tags": tags,
            "rank_order": rank_order,
        }

    def _build_groups(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {
            "d1": [],
            "layer_c": [],
            "mainline": [],
            "risk": [],
            "non_mainline": [],
        }
        for item in items:
            grouped[self._group_key(item)].append(item)

        order = ("d1", "layer_c", "mainline", "risk", "non_mainline")
        result: list[dict[str, Any]] = []
        for key in order:
            rows = grouped[key]
            if not rows:
                continue
            result.append({
                "group_key": key,
                "group_name": self._group_name(key),
                "summary": self._group_summary(key, rows),
                "item_count": len(rows),
                "top_stocks": self._unique_text([
                    str(item.get("stock_name") or item.get("stock_id") or "").strip()
                    for item in rows
                ])[:5],
                "related_mainlines": self._unique_text([
                    str(item.get("mainline_name") or "").strip()
                    for item in rows
                ])[:5],
            })
        return result

    def _build_summary(
        self,
        groups: list[dict[str, Any]],
        abnormal_evidence: list[dict[str, Any]],
        money_flow_evidence: list[dict[str, Any]],
        dragon_tiger_evidence: list[dict[str, Any]],
        stock_capital_evidence: list[dict[str, Any]],
    ) -> str:
        total_items = len(abnormal_evidence) + len(money_flow_evidence) + len(dragon_tiger_evidence) + len(stock_capital_evidence)
        if total_items == 0:
            return "当前证据层未形成可用的结构化异动、资金或龙虎榜证据，先按主线与 D1 结果继续观察。"

        group_map = {str(group.get("group_key")): int(group.get("item_count") or 0) for group in groups}
        parts: list[str] = [f"今日证据层共整理 {total_items} 条证据"]
        if group_map.get("d1"):
            parts.append(f"D1 候选证据 {group_map['d1']} 条")
        if group_map.get("layer_c"):
            parts.append(f"Layer C 证据 {group_map['layer_c']} 条")
        if group_map.get("mainline"):
            parts.append(f"主线证据 {group_map['mainline']} 条")
        if group_map.get("risk"):
            parts.append(f"风险/退潮证据 {group_map['risk']} 条")
        if group_map.get("non_mainline"):
            parts.append(f"非主线证据 {group_map['non_mainline']} 条")

        dragon_items = dragon_tiger_evidence
        if dragon_items and not any(item.get("active_mainline") for item in dragon_items):
            parts.append("龙虎榜未形成对核心主线的强确认")
        return "，".join(parts) + "。"

    def _build_title(self, evidence_type: str, row: dict[str, Any], stock_name: str, theme_name: str) -> str:
        if evidence_type == "abnormal":
            return self._first_text(row.get("title"), stock_name, theme_name, "异动证据")
        if evidence_type == "money_flow":
            return self._first_text(row.get("title"), stock_name, theme_name, "资金证据")
        if evidence_type == "dragon_tiger":
            return self._first_text(row.get("title"), stock_name, theme_name, "龙虎榜证据")
        if evidence_type == "stock_capital":
            return self._first_text(row.get("title"), stock_name, theme_name, "个股资金证据")
        return self._first_text(row.get("title"), stock_name, theme_name, "证据")

    def _build_description(self, evidence_type: str, row: dict[str, Any]) -> str:
        if evidence_type == "abnormal":
            pieces = [
                self._first_text(row.get("conclusion"), row.get("description"), row.get("reason")),
                self._join_non_empty([
                    self._format_amount(row.get("main_net_inflow") or row.get("capital", {}).get("main_net_inflow")),
                    self._first_text(row.get("volume_ratio"), row.get("turnover_rate")),
                ], "，"),
            ]
            return self._join_non_empty(pieces, "；")
        if evidence_type == "money_flow":
            kline = row.get("kline") if isinstance(row.get("kline"), dict) else {}
            pieces = [
                self._first_text(row.get("conclusion"), row.get("description"), row.get("reason")),
                self._join_non_empty([
                    self._first_text(row.get("money_flow_tier"), row.get("role_enhanced")),
                    self._first_text(kline.get("position_label"), self._join_list(kline.get("pattern_labels"))),
                ], "，"),
            ]
            return self._join_non_empty(pieces, "；")
        if evidence_type == "dragon_tiger":
            pieces = [
                self._first_text(row.get("side_summary"), row.get("description"), row.get("reason")),
                self._join_non_empty([
                    self._first_text(row.get("hot_money_name")),
                    self._format_amount(row.get("net_buy") or row.get("buy_amount")),
                ], "，"),
            ]
            return self._join_non_empty(pieces, "；")
        if evidence_type == "stock_capital":
            pieces = [
                self._first_text(row.get("description"), row.get("conclusion"), row.get("reason")),
                self._join_non_empty([
                    self._first_text(row.get("theme_name")),
                    self._format_amount(row.get("main_net_inflow")),
                ], "，"),
            ]
            return self._join_non_empty(pieces, "；")
        return self._first_text(row.get("description"), row.get("conclusion"), row.get("reason"))

    def _build_tags(
        self,
        evidence_type: str,
        row: dict[str, Any],
        alignment: dict[str, Any],
        active_mainline: bool,
        in_layer_c: bool,
        is_d1_candidate: bool,
        is_focus_stock: bool,
        lifecycle_state: str,
        trade_action: str,
    ) -> list[str]:
        tags: list[str] = [self._tag_name(evidence_type)]
        if active_mainline:
            tags.append("主线")
        if in_layer_c:
            tags.append("Layer C")
        if is_d1_candidate:
            tags.append("D1")
        if is_focus_stock:
            tags.append("Focus")
        lifecycle_tag = self._lifecycle_tag(lifecycle_state)
        if lifecycle_tag:
            tags.append(lifecycle_tag)
        if trade_action:
            tags.append(trade_action)
        for value in self._row_tags(row):
            if value not in tags:
                tags.append(value)
        for value in self._row_tags(alignment):
            if value not in tags:
                tags.append(value)
        return self._unique_text(tags)[:8]

    def _group_key(self, item: dict[str, Any]) -> str:
        if bool(item.get("is_focus_stock")) or bool(item.get("is_d1_candidate")):
            return "d1"
        if bool(item.get("in_layer_c")):
            return "layer_c"
        if self._is_risk_item(item):
            return "risk"
        if bool(item.get("active_mainline")):
            return "mainline"
        return "non_mainline"

    def _group_name(self, key: str) -> str:
        return {
            "d1": "D1 候选证据",
            "layer_c": "Layer C 证据",
            "mainline": "主线证据",
            "risk": "风险/退潮证据",
            "non_mainline": "非主线证据",
        }.get(key, "证据")

    def _group_summary(self, key: str, items: list[dict[str, Any]]) -> str:
        top_stocks = self._unique_text([
            str(item.get("stock_name") or item.get("stock_id") or "").strip()
            for item in items
        ])[:3]
        if key == "d1":
            return f"观察池中的 D1 证据集中在 {self._join_list(top_stocks)}。"
        if key == "layer_c":
            return f"Layer C 强势股证据集中在 {self._join_list(top_stocks)}。"
        if key == "mainline":
            return f"主线相关证据主要来自 {self._join_list(top_stocks)}。"
        if key == "risk":
            return f"风险/退潮信号主要来自 {self._join_list(top_stocks)}。"
        return f"非主线证据主要来自 {self._join_list(top_stocks)}。"

    def _alignment_for_stock(self, stock_id: str, by_stock: dict[str, Any]) -> dict[str, Any]:
        if not stock_id:
            return {}
        alignment = by_stock.get(str(stock_id))
        return alignment if isinstance(alignment, dict) else {}

    def _fallback_trade_action(self, evidence_type: str, row: dict[str, Any], alignment: dict[str, Any]) -> str:
        value = self._first_text(row.get("trade_action"), alignment.get("trade_action"))
        if value:
            return value
        lifecycle = self._first_text(row.get("lifecycle_state"), alignment.get("lifecycle_state"))
        if "fade" in lifecycle.lower():
            return "回避"
        if evidence_type == "dragon_tiger":
            return "观察"
        return "观察"

    def _fallback_score(self, evidence_type: str, row: dict[str, Any], alignment: dict[str, Any]) -> float | None:
        if evidence_type == "abnormal":
            return self._float_or_none(self._first_present(row, "abnormal_score", "watch_score"))
        if evidence_type == "money_flow":
            inflow = self._float_or_none(self._first_present(row, "main_net_inflow", "amount"))
            return abs(inflow) / 1e6 if inflow is not None else None
        if evidence_type == "dragon_tiger":
            net_buy = self._float_or_none(self._first_present(row, "net_buy", "buy_amount"))
            return abs(net_buy) / 1e6 if net_buy is not None else None
        if evidence_type == "stock_capital":
            inflow = self._float_or_none(self._first_present(row, "main_net_inflow", "total_inflow"))
            return abs(inflow) / 1e6 if inflow is not None else None
        return self._float_or_none(self._first_present(row, "score"))

    def _fallback_amount(self, evidence_type: str, row: dict[str, Any]) -> float | None:
        if evidence_type in {"money_flow", "stock_capital"}:
            return self._float_or_none(self._first_present(row, "main_net_inflow", "total_inflow", "amount"))
        if evidence_type == "dragon_tiger":
            net_buy = self._float_or_none(self._first_present(row, "net_buy", "buy_amount"))
            if net_buy is not None:
                return net_buy
            buy = self._float_or_none(row.get("buy_amount"))
            sell = self._float_or_none(row.get("sell_amount"))
            if buy is not None or sell is not None:
                return (buy or 0.0) - (sell or 0.0)
        return self._float_or_none(self._first_present(row, "amount"))

    def _is_risk_item(self, item: dict[str, Any]) -> bool:
        lifecycle = str(item.get("lifecycle_state") or "").strip().lower()
        action = str(item.get("trade_action") or "").strip()
        if any(key in lifecycle for key in ("fade", "down", "cooling")):
            return True
        if any(keyword in action for keyword in ("回避", "谨慎", "退潮")):
            return True
        return False

    @staticmethod
    def _tag_name(evidence_type: str) -> str:
        return {
            "abnormal": "异动",
            "money_flow": "资金",
            "dragon_tiger": "龙虎榜",
            "stock_capital": "个股资金",
        }.get(evidence_type, "证据")

    @staticmethod
    def _lifecycle_tag(lifecycle_state: str) -> str:
        lifecycle = lifecycle_state.strip().lower()
        mapping = {
            "divergence": "分歧",
            "repair": "修复",
            "start": "启动",
            "fermentation": "发酵",
            "watch": "观察",
            "fade_watch": "退潮观察",
            "fade_confirmed": "退潮确认",
            "fade": "退潮",
        }
        return mapping.get(lifecycle, "")

    @staticmethod
    def _first_present(*values: Any) -> Any:
        dict_sources: list[dict[str, Any]] = []
        for value in values:
            if isinstance(value, dict):
                dict_sources.append(value)
                continue
            if isinstance(value, str):
                for source in dict_sources:
                    if value in source and source.get(value) not in (None, ""):
                        return source.get(value)
                continue
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _row_tags(row: dict[str, Any]) -> list[str]:
        result: list[str] = []
        raw = row.get("tags") or row.get("labels") or row.get("flags") or row.get("pattern_labels")
        if isinstance(raw, list):
            for item in raw:
                text = str(item or "").strip()
                if text:
                    result.append(text)
        elif isinstance(raw, str) and raw.strip():
            result.append(raw.strip())
        return result

    @staticmethod
    def _unique_text(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _join_list(values: list[str], sep: str = "、") -> str:
        return sep.join([str(item).strip() for item in values if str(item).strip()])

    @staticmethod
    def _join_non_empty(values: list[str], sep: str = "；") -> str:
        parts = [str(item).strip() for item in values if str(item).strip()]
        return sep.join(parts)

    @staticmethod
    def _format_amount(value: Any) -> str:
        try:
            if value in (None, ""):
                return ""
            amount = float(value)
        except Exception:
            return str(value or "").strip()
        abs_amount = abs(amount)
        if abs_amount >= 1e8:
            return f"{amount / 1e8:.2f}亿"
        if abs_amount >= 1e4:
            return f"{amount / 1e4:.2f}万"
        return f"{amount:.0f}"

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []

    @staticmethod
    def _count_rows(value: Any) -> int:
        return len(value) if isinstance(value, list) else 0

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

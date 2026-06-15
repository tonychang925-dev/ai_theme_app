from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from typing import Any

from stock_processing_service.application.services.f10_capital_parser import (
    F10CapitalParser,
    _normalize_stock_id,
)


class F10CapitalEvidenceService:
    """Build and attach F10 资金动向 evidence without hitting live TDX in the recap path."""

    def __init__(self, parser: F10CapitalParser | None = None) -> None:
        self._parser = parser or F10CapitalParser()

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return date.fromisoformat(value.strip()[:10])
            except ValueError:
                return None
        return None

    def build_snapshot_row(
        self,
        *,
        trade_date: date | str,
        stock_id: str,
        stock_name: str | None = None,
        raw_text: str,
        source_updated_date: date | str | None = None,
    ) -> dict[str, Any]:
        trade_date_obj = self._to_date(trade_date) or date.today()
        source_updated_date_obj = self._to_date(source_updated_date)
        return self._parser.parse(
            stock_id=stock_id,
            stock_name=stock_name,
            trade_date=trade_date_obj,
            source_updated_date=source_updated_date_obj,
            raw_text=raw_text,
        )

    def snapshot_to_evidence(self, snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(snapshot, dict):
            return None
        if not snapshot:
            return None
        dragon_tiger = self._dict_or_json(snapshot.get("dragon_tiger_json"))
        block_trade = self._dict_or_json(snapshot.get("block_trade_json"))
        margin_trading = self._dict_or_json(snapshot.get("margin_trading_json"))
        capital_flow = self._dict_or_json(snapshot.get("capital_flow_json"))
        strategic_lending = self._dict_or_json(snapshot.get("strategic_lending_json"))
        trade_date_obj = self._to_date(snapshot.get("trade_date"))
        summary_parts = [
            capital_flow.get("summary"),
            self._same_day_dragon_tiger_summary(dragon_tiger, trade_date_obj),
            margin_trading.get("summary") and f"融资融券：{margin_trading.get('summary')}",
        ]
        summary = "；".join(str(item).strip() for item in summary_parts if item)
        return {
            "source": snapshot.get("source") or "tdx_f10",
            "section": snapshot.get("section") or "资金动向",
            "available": bool(snapshot.get("raw_text")),
            "source_updated_date": snapshot.get("source_updated_date"),
            "trade_date": snapshot.get("trade_date"),
            "stock_id": snapshot.get("stock_id"),
            "stock_name": snapshot.get("stock_name"),
            "dragon_tiger": dragon_tiger,
            "block_trade": block_trade,
            "margin_trading": margin_trading,
            "capital_flow": capital_flow,
            "strategic_lending": strategic_lending,
            "summary": summary or capital_flow.get("summary") or "暂无数据",
            "source_flags": self._build_source_flags(snapshot),
            "diagnostics": self._dict_or_json(snapshot.get("diagnostics")),
        }

    def collect_stock_ids(self, recap_doc: dict[str, Any], one_to_two_payload: dict[str, Any] | None = None) -> list[str]:
        stock_ids: set[str] = set()
        stock_ids.update(self._collect_from_rows(self._context_rows(recap_doc, "stock_facts")))
        stock_ids.update(self._collect_from_rows(self._context_rows(recap_doc, "money_flow")))
        stock_ids.update(self._collect_from_rows(self._context_rows(recap_doc, "stock_capital")))
        stock_ids.update(self._collect_from_rows(self._context_rows(recap_doc, "dragon_tiger")))
        stock_ids.update(self._collect_from_rows(recap_doc.get("money_flow_reviews")))
        stock_ids.update(self._collect_from_rows(recap_doc.get("stock_capital_reviews")))
        stock_ids.update(self._collect_from_rows(recap_doc.get("dragon_tiger_reviews")))
        stock_ids.update(self._collect_from_rows(recap_doc.get("watchlist_reviews")))
        stock_ids.update(self._collect_from_rows((one_to_two_payload or {}).get("items")))
        return sorted(stock_ids)

    def attach_to_recap_doc(
        self,
        recap_doc: dict[str, Any],
        snapshots_by_stock: dict[str, dict[str, Any]],
        one_to_two_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attached: dict[str, int] = {
            "money_flow_reviews": self._attach_rows(recap_doc.get("money_flow_reviews"), snapshots_by_stock),
            "stock_capital_reviews": self._attach_rows(recap_doc.get("stock_capital_reviews"), snapshots_by_stock),
            "dragon_tiger_reviews": self._attach_rows(recap_doc.get("dragon_tiger_reviews"), snapshots_by_stock),
            "watchlist_reviews": self._attach_rows(recap_doc.get("watchlist_reviews"), snapshots_by_stock),
            "report_context.money_flow": self._attach_rows(self._context_rows(recap_doc, "money_flow"), snapshots_by_stock),
            "report_context.money_flow_enhanced": self._attach_rows(self._context_rows(recap_doc, "money_flow_enhanced"), snapshots_by_stock),
            "one_to_two_items": 0,
        }
        daily_review_v2 = recap_doc.get("daily_review_v2")
        if isinstance(daily_review_v2, dict):
            attached["daily_review_v2.money_flow_reviews"] = self._attach_rows(daily_review_v2.get("money_flow_reviews"), snapshots_by_stock)
            attached["daily_review_v2.stock_capital_reviews"] = self._attach_rows(daily_review_v2.get("stock_capital_reviews"), snapshots_by_stock)
            attached["daily_review_v2.dragon_tiger_reviews"] = self._attach_rows(daily_review_v2.get("dragon_tiger_reviews"), snapshots_by_stock)
            attached["daily_review_v2.watchlist_reviews"] = self._attach_rows(daily_review_v2.get("watchlist_reviews"), snapshots_by_stock)
        if isinstance(one_to_two_payload, dict):
            attached["one_to_two_items"] = self._attach_rows(one_to_two_payload.get("items"), snapshots_by_stock)
        return attached

    def summarize_snapshot(self, snapshot: dict[str, Any] | None) -> str:
        evidence = self.snapshot_to_evidence(snapshot)
        if not evidence:
            return ""
        capital_flow = evidence.get("capital_flow") if isinstance(evidence.get("capital_flow"), dict) else {}
        dragon_tiger = evidence.get("dragon_tiger") if isinstance(evidence.get("dragon_tiger"), dict) else {}
        margin_trading = evidence.get("margin_trading") if isinstance(evidence.get("margin_trading"), dict) else {}
        parts = [capital_flow.get("summary") if isinstance(capital_flow, dict) else ""]
        same_day_dragon_tiger = self._same_day_dragon_tiger_summary(dragon_tiger, self._to_date(evidence.get("trade_date")))
        if same_day_dragon_tiger:
            parts.append(same_day_dragon_tiger)
        if isinstance(margin_trading, dict) and margin_trading.get("summary"):
            parts.append(f"融资融券：{margin_trading.get('summary')}")
        return "；".join(str(item).strip() for item in parts if item)

    @staticmethod
    def _context_rows(recap_doc: dict[str, Any], key: str) -> list[dict[str, Any]]:
        rows = recap_doc.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        context = recap_doc.get("report_context")
        if isinstance(context, dict):
            rows = context.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []

    @staticmethod
    def _collect_from_rows(rows: Any) -> set[str]:
        result: set[str] = set()
        if not isinstance(rows, list):
            return result
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("stock_id", "stock_code", "symbol"):
                value = row.get(key)
                normalized = _normalize_stock_id(value)
                if normalized:
                    result.add(normalized)
                    break
        return result

    @staticmethod
    def _build_source_flags(snapshot: dict[str, Any]) -> list[str]:
        flags = ["tdx_f10"]
        if snapshot.get("capital_flow_json"):
            flags.append("capital_flow")
        if snapshot.get("margin_trading_json"):
            flags.append("margin_trading")
        if snapshot.get("dragon_tiger_json"):
            flags.append("dragon_tiger")
        if snapshot.get("block_trade_json"):
            flags.append("block_trade")
        return flags

    @staticmethod
    def _dict_or_json(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                loaded = json.loads(text)
            except Exception:
                return {}
            if isinstance(loaded, dict):
                return loaded
            return {}
        return {}

    @staticmethod
    def _same_day_dragon_tiger_summary(dragon_tiger: dict[str, Any], trade_date_obj: date | None) -> str:
        if not isinstance(dragon_tiger, dict) or not trade_date_obj:
            return ""
        latest_date = dragon_tiger.get("latest_date")
        if isinstance(latest_date, date):
            latest_date_obj = latest_date
        elif isinstance(latest_date, str) and latest_date.strip():
            try:
                latest_date_obj = date.fromisoformat(latest_date.strip()[:10])
            except ValueError:
                latest_date_obj = None
        else:
            latest_date_obj = None
        if latest_date_obj != trade_date_obj:
            return ""
        summary = str(dragon_tiger.get("summary") or "").strip()
        return f"龙虎榜：{summary}" if summary else ""

    def _attach_rows(self, rows: Any, snapshots_by_stock: dict[str, dict[str, Any]]) -> int:
        if not isinstance(rows, list):
            return 0
        count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            stock_key = _normalize_stock_id(row.get("stock_id") or row.get("stock_code") or row.get("symbol"))
            if not stock_key:
                continue
            snapshot = snapshots_by_stock.get(stock_key)
            if not snapshot:
                continue
            evidence = self.snapshot_to_evidence(snapshot)
            if not evidence:
                continue
            row["f10_capital"] = evidence
            count += 1
        return count

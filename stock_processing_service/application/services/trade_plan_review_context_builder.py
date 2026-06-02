from __future__ import annotations

import json
from datetime import date
from typing import Any


class TradePlanReviewContextBuilder:
    async def build(self, *, gateway: Any, trade_date: date) -> dict[str, Any] | None:
        row = await gateway.get_existing_post_market_recap_snapshot(trade_date)
        if not row:
            return None
        payload = self._normalize_recap_payload(row)
        recap_doc = self._extract_recap_doc(payload)
        return {
            "trade_date": trade_date.isoformat(),
            "snapshot_version": str(row.get("snapshot_version") or "unknown"),
            "payload": payload,
            "recap_doc": recap_doc,
            "summary": self._summary(payload, recap_doc),
            "theme_terms": self._theme_terms(payload, recap_doc),
        }

    @staticmethod
    def _normalize_recap_payload(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("payload", "doc"):
            value = row.get(key)
            if isinstance(value, dict) and value:
                return value
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict) and parsed:
                        return parsed
                except Exception:
                    pass
        recap_doc = row.get("recap_doc")
        if isinstance(recap_doc, dict) and recap_doc:
            return {"recap_doc": recap_doc}
        if isinstance(recap_doc, str) and recap_doc.strip():
            try:
                parsed = json.loads(recap_doc)
                if isinstance(parsed, dict) and parsed:
                    return {"recap_doc": parsed}
            except Exception:
                pass
        return {}

    @staticmethod
    def _extract_recap_doc(payload: dict[str, Any]) -> dict[str, Any]:
        recap_doc = payload.get("recap_doc")
        if isinstance(recap_doc, dict):
            return recap_doc
        if payload.get("candidate_count") is not None or payload.get("top_candidates"):
            return payload
        return {}

    @classmethod
    def _summary(cls, payload: dict[str, Any], recap_doc: dict[str, Any]) -> str:
        report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
        if report.get("summary"):
            return str(report.get("summary"))
        candidate_count = recap_doc.get("candidate_count", 0)
        strong_watch_input_count = recap_doc.get("strong_watch_input_count") or recap_doc.get("strong_watch_input_7d_count") or 0
        return f"候选 {candidate_count} | 强势池输入 {strong_watch_input_count}"

    @classmethod
    def _theme_terms(cls, payload: dict[str, Any], recap_doc: dict[str, Any]) -> list[str]:
        terms: set[str] = set()
        for key in ("top_candidates", "formal_top_candidates", "observe_candidates", "candidate_diagnostics"):
            value = recap_doc.get(key)
            if not isinstance(value, list):
                continue
            for row in value:
                if not isinstance(row, dict):
                    continue
                for field in ("subject_name", "theme_name"):
                    text = str(row.get(field) or "").strip()
                    if text and not text.isdigit():
                        terms.add(text)
        report = payload.get("report")
        if isinstance(report, dict):
            for item in report.get("highlights") or []:
                text = str(item or "").strip()
                if 2 <= len(text) <= 20:
                    terms.add(text)
        return sorted(terms)


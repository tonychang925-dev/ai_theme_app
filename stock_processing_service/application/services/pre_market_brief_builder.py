from __future__ import annotations

import inspect
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable


DecisionStreamReader = Callable[[date, int], Awaitable[list[dict[str, Any]]] | list[dict[str, Any]]]


class PreMarketBriefBuilder:
    """Build the event/theme sections of pre_market_brief_snapshot.

    The stock opportunity section is optional and is delegated to a read-only
    builder. This class must not call StockMatchEngine.
    """

    SNAPSHOT_VERSION = "pre_market_brief.v1"

    def __init__(
        self,
        read_gateway: Any,
        write_gateway: Any,
        *,
        decision_stream_reader: DecisionStreamReader | None = None,
        opportunity_builder: Any | None = None,
    ) -> None:
        self._read_gateway = read_gateway
        self._write_gateway = write_gateway
        self._decision_stream_reader = decision_stream_reader
        self._opportunity_builder = opportunity_builder

    async def rebuild(
        self,
        trade_date: date,
        source: str = "db_first",
        limit: int = 200,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        source = source or "db_first"
        limit = max(1, int(limit or 200))

        matched_events = await self._load_matched_events_from_db(trade_date, limit)
        db_matched_count = len(matched_events)
        review_events = await self._load_review_events_from_db(trade_date, limit)
        unknown_events: list[dict[str, Any]] = []
        stream_decisions: list[dict[str, Any]] = []

        should_read_stream = source in {"db_first", "decision_stream", "stream"} and (
            self._decision_stream_reader is not None
        )
        if should_read_stream and (source in {"decision_stream", "stream"} or not matched_events):
            stream_decisions = await self._load_decision_stream(trade_date, limit)
            stream_sections = self._sections_from_decisions(stream_decisions, limit)
            if not matched_events:
                matched_events = stream_sections["matched_events"]
            review_events = self._dedupe_by_key(
                [*review_events, *stream_sections["review_events"]],
                key_fields=("event_id", "title"),
            )[:limit]
            unknown_events = stream_sections["unknown_events"][:limit]

        sections = self._build_sections(
            matched_events=matched_events,
            review_events=review_events,
            unknown_events=unknown_events,
            limit=limit,
        )
        if self._opportunity_builder is not None:
            sections["event_driven_opportunities"] = await self._opportunity_builder.build(
                trade_date=trade_date,
                matched_themes=sections["matched_themes"],
                matched_events=matched_events,
            )
        diagnostics = {
            "source": self._diagnostic_source(source, db_matched_count, stream_decisions),
            "event_count": len(matched_events) + len(review_events) + len(unknown_events),
            "matched_event_count": len(matched_events),
            "theme_count": len(sections["matched_themes"]),
            "opportunity_count": len(sections["event_driven_opportunities"]),
            "review_event_count": len(review_events),
            "unknown_event_count": len(unknown_events),
            "last_rebuild_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = {
            "version": self.SNAPSHOT_VERSION,
            "trade_date": trade_date.isoformat(),
            "status": "draft",
            "sections": sections,
            "diagnostics": diagnostics,
        }

        if not dry_run:
            await self._write_snapshot(trade_date=trade_date, payload=payload, force=force)

        return payload

    async def _load_matched_events_from_db(self, trade_date: date, limit: int) -> list[dict[str, Any]]:
        fn = getattr(self._read_gateway, "get_intel_news_events", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date)
        return [self._normalize_event_row(row, "db") for row in list(rows or [])[:limit]]

    async def _load_review_events_from_db(self, trade_date: date, limit: int) -> list[dict[str, Any]]:
        fn = getattr(self._read_gateway, "get_pre_market_review_events", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date, limit=limit)
        return [self._normalize_event_row(row, "event_review_queue") for row in list(rows or [])[:limit]]

    async def _load_decision_stream(self, trade_date: date, limit: int) -> list[dict[str, Any]]:
        if self._decision_stream_reader is None:
            return []
        rows = self._decision_stream_reader(trade_date, limit)
        if inspect.isawaitable(rows):
            rows = await rows
        return list(rows or [])[:limit]

    async def _write_snapshot(self, trade_date: date, payload: dict[str, Any], force: bool) -> None:
        doc = {
            "trade_date": trade_date,
            "snapshot_version": self.SNAPSHOT_VERSION,
            "batch_id": f"pre_market_brief:{trade_date.isoformat()}",
            "trace_id": f"pre_market_brief:{trade_date.isoformat()}:{diagnostic_ts(payload)}",
            "source_trace_id": payload["diagnostics"].get("source"),
            "status": payload.get("status", "draft"),
            "generated_at": payload["diagnostics"].get("last_rebuild_at"),
            "payload": payload,
            "source_name": "pre_market_brief_builder",
        }
        try:
            await self._write_gateway.upsert_pre_market_brief_snapshot(doc, force=force)
        except TypeError:
            if force:
                raise
            await self._write_gateway.upsert_pre_market_brief_snapshot(doc)

    def _sections_from_decisions(self, decisions: list[dict[str, Any]], limit: int) -> dict[str, list[dict[str, Any]]]:
        matched: list[dict[str, Any]] = []
        review: list[dict[str, Any]] = []
        unknown: list[dict[str, Any]] = []
        for decision in decisions[:limit]:
            match_result = decision.get("match_result") if isinstance(decision.get("match_result"), dict) else {}
            decision_type = str(match_result.get("decision") or decision.get("decision") or "").upper()
            action = str(decision.get("action") or "")
            row = self._normalize_decision(decision)
            if decision_type == "MATCH" or action == "update_theme":
                matched.append(row)
            elif decision_type == "HUMAN_REVIEW" or action == "human_review":
                review.append(row)
            elif decision_type == "UNKNOWN" or action == "publish_clustering":
                unknown.append(row)
        return {"matched_events": matched, "review_events": review, "unknown_events": unknown}

    def _build_sections(
        self,
        *,
        matched_events: list[dict[str, Any]],
        review_events: list[dict[str, Any]],
        unknown_events: list[dict[str, Any]],
        limit: int,
    ) -> dict[str, list[dict[str, Any]]]:
        matched_events = self._dedupe_by_key(matched_events, key_fields=("event_id", "subject_key", "title"))[:limit]
        review_events = self._dedupe_by_key(review_events, key_fields=("event_id", "title"))[:limit]
        unknown_events = self._dedupe_by_key(unknown_events, key_fields=("event_id", "title"))[:limit]
        return {
            "major_events": sorted(matched_events, key=lambda row: float(row.get("impact_score") or 0), reverse=True)[:limit],
            "matched_themes": self._build_matched_themes(matched_events),
            "review_events": review_events,
            "unknown_watch": unknown_events,
            "risk_alerts": self._build_risk_alerts(review_events, unknown_events),
            "event_driven_opportunities": [],
        }

    def _build_matched_themes(self, matched_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in matched_events:
            key = str(event.get("subject_key") or event.get("theme_name") or "unknown")
            grouped[key].append(event)

        themes: list[dict[str, Any]] = []
        for key, events in grouped.items():
            best = max(events, key=lambda row: float(row.get("confidence") or 0))
            latest = max(events, key=lambda row: str(row.get("occurred_at") or ""))
            themes.append(
                {
                    "subject_key": key,
                    "theme_name": best.get("theme_name") or key,
                    "event_count": len(events),
                    "latest_event_title": latest.get("title", ""),
                    "confidence": best.get("confidence"),
                    "impact_score": max(float(row.get("impact_score") or 0) for row in events),
                    "event_ids": [row.get("event_id") for row in events if row.get("event_id") is not None],
                }
            )
        return sorted(themes, key=lambda row: (-int(row["event_count"]), -float(row.get("impact_score") or 0))) 

    def _build_risk_alerts(
        self,
        review_events: list[dict[str, Any]],
        unknown_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if review_events:
            alerts.append(
                {
                    "risk_type": "human_review_pending",
                    "count": len(review_events),
                    "message": "存在待人工复核的高影响题材事件，暂不生成股票机会。",
                }
            )
        if unknown_events:
            alerts.append(
                {
                    "risk_type": "unknown_event_watch",
                    "count": len(unknown_events),
                    "message": "存在未匹配题材事件，仅进入观察区。",
                }
            )
        return alerts

    def _normalize_event_row(self, row: Any, source: str) -> dict[str, Any]:
        data = dict(row or {})
        theme_keys = list(data.get("theme_subject_keys") or [])
        theme_names = list(data.get("theme_names") or [])
        return {
            "event_id": data.get("event_id") or self._event_id_from_item_id(data.get("item_id")),
            "item_id": str(data.get("item_id") or ""),
            "occurred_at": str(data.get("occurred_at") or data.get("created_at") or ""),
            "title": str(data.get("title") or ""),
            "summary": str(data.get("summary") or ""),
            "subject_key": str(data.get("subject_key") or (theme_keys[0] if theme_keys else "")),
            "theme_name": str(data.get("theme_name") or (theme_names[0] if theme_names else "")),
            "confidence": self._float_or_none(data.get("confidence")),
            "impact_score": self._float_or_zero(data.get("impact_score")),
            "source_type": str(data.get("source_type") or source),
            "source_channel": str(data.get("source_channel") or source),
            "reason": str(data.get("reason") or ""),
        }

    def _normalize_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        event_data = decision.get("event_data") if isinstance(decision.get("event_data"), dict) else {}
        theme_data = decision.get("theme_data") if isinstance(decision.get("theme_data"), dict) else {}
        match_result = decision.get("match_result") if isinstance(decision.get("match_result"), dict) else {}
        return {
            "event_id": event_data.get("event_id") or decision.get("event_id"),
            "item_id": str(decision.get("decision_id") or ""),
            "occurred_at": str(decision.get("timestamp") or ""),
            "title": str(event_data.get("title") or decision.get("event_title") or ""),
            "summary": str(event_data.get("summary") or ""),
            "subject_key": str(theme_data.get("subject_key") or match_result.get("matched_subject_key") or ""),
            "theme_name": str(theme_data.get("name") or match_result.get("matched_theme_name") or ""),
            "confidence": self._float_or_none(decision.get("confidence") or match_result.get("confidence")),
            "impact_score": self._float_or_zero(decision.get("impact_score")),
            "source_type": str(decision.get("source") or "decision_stream"),
            "source_channel": "decision_stream",
            "reason": str(decision.get("reason") or match_result.get("reason_code") or ""),
        }

    def _diagnostic_source(
        self,
        requested_source: str,
        db_matched_count: int,
        stream_decisions: list[dict[str, Any]],
    ) -> str:
        if requested_source in {"decision_stream", "stream"}:
            return "decision_stream"
        if db_matched_count > 0:
            return "db"
        if stream_decisions:
            return "decision_stream_fallback"
        return "db_empty"

    @staticmethod
    def _event_id_from_item_id(value: Any) -> int | None:
        match = re.search(r"event:(\d+)", str(value or ""))
        return int(match.group(1)) if match else None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _float_or_zero(value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _dedupe_by_key(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        result: list[dict[str, Any]] = []
        for row in rows:
            key = tuple(row.get(field) for field in key_fields)
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result


def diagnostic_ts(payload: dict[str, Any]) -> str:
    value = ((payload.get("diagnostics") or {}).get("last_rebuild_at") or "").replace(":", "").replace("-", "")
    return value[:15] or "unknown"

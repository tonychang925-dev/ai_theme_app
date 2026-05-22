from __future__ import annotations

import inspect
import json as _json
import logging
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable

from stock_processing_service.application.services.pre_market_window import (
    PreMarketWindow,
    resolve_pre_market_window,
)
from stock_processing_service.domain.services.alert_rule_engine import AlertRuleEngine

logger = logging.getLogger(__name__)


DecisionStreamReader = Callable[[date, int], Awaitable[list[dict[str, Any]]] | list[dict[str, Any]]]

LOW_VALUE_DROP_REASON_CODES = {
    "low_value_event_match_blocked",
    "low_value_regulatory_event_blocked",
    "ordinary_earnings_low_value",
    "clarification_risk_notice_low_value",
    "weather_disaster_low_value",
    "ordinary_ipo_low_value",
    "duplicate_news_low_value",
    "low_value_event_dropped",
    "rule_low_value_regulatory",
    "rule_low_value_clarification",
    "rule_low_value_disaster",
    "rule_low_value_earnings",
    "rule_low_value_disclosure",
    "rule_low_value_ordinary_personnel",
    "rule_low_value_ordinary_ipo",
}


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

        # P0-B: 统一盘前窗口
        window: PreMarketWindow = await resolve_pre_market_window(
            trade_date, gateway=self._read_gateway
        )
        start_at = window.start_at
        end_at = window.end_at

        matched_events = await self._load_matched_events_from_db(
            trade_date, limit, start_at=start_at, end_at=end_at
        )
        db_matched_count = len(matched_events)
        review_events = await self._load_review_events_from_db(
            trade_date, limit, start_at=start_at, end_at=end_at
        )
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

        intel_announcements_raw = await self._load_intel_announcements(
            trade_date, limit, matched_only=False, start_at=start_at, end_at=end_at
        )
        intel_announcements_matched = await self._load_intel_announcements(
            trade_date, limit, matched_only=True, start_at=start_at, end_at=end_at
        )

        # P1-E1: AlertRuleEngine — 从 Intel 公告生成分级/去重/截断的风险+机会提醒
        intel_alerts = AlertRuleEngine.evaluate_batch(intel_announcements_raw,
                                                       risk_top_n=5, opportunity_top_n=10)
        risk_alerts = intel_alerts["risk_alerts"]
        opportunity_alerts = intel_alerts["opportunity_alerts"]

        sections = self._build_sections(
            matched_events=matched_events,
            review_events=review_events,
            unknown_events=unknown_events,
            intel_announcements_raw=intel_announcements_raw,
            intel_announcements_matched=intel_announcements_matched,
            risk_alerts=risk_alerts,
            opportunity_alerts=opportunity_alerts,
            limit=limit,
        )
        dropped_diagnostics = sections.pop("_dropped_diagnostics", {})
        if self._opportunity_builder is not None:
            sections["event_driven_opportunities"] = await self._opportunity_builder.build(
                trade_date=window.prev_trade_date,
                matched_themes=sections["matched_themes"],
                matched_events=matched_events,
            )
        # P1-B: 全源 source_breakdown
        source_breakdown = _build_source_breakdown(
            matched_events=matched_events,
            review_events=review_events,
            unknown_events=unknown_events,
            intel_raw=intel_announcements_raw,
            intel_matched=intel_announcements_matched,
        )
        diagnostics = {
            "source": self._diagnostic_source(source, db_matched_count, stream_decisions),
            "event_count": len(matched_events) + len(review_events) + len(unknown_events),
            "matched_event_count": len(matched_events),
            "theme_count": len(sections["matched_themes"]),
            "opportunity_count": len(sections["event_driven_opportunities"]),
            "review_event_count": len(review_events),
            "unknown_event_count": len(unknown_events),
            "intel_announcement_count": len(sections["company_announcements_raw"]),
            "intel_announcement_raw_count": len(sections["company_announcements_raw"]),
            "intel_announcement_matched_count": len(sections["company_announcements_matched"]),
            "last_rebuild_at": datetime.now(timezone.utc).isoformat(),
            "pre_market_window": {
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "trade_date": window.trade_date.isoformat(),
                "prev_trade_date": window.prev_trade_date.isoformat(),
                "source": window.source,
            },
            "source_breakdown": source_breakdown,
            **dropped_diagnostics,
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

    async def _load_matched_events_from_db(
        self, trade_date: date, limit: int,
        start_at: datetime | None = None, end_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        fn = getattr(self._read_gateway, "get_pre_market_subject_events", None)
        if callable(fn):
            rows = await fn(trade_date, limit=limit, start_at=start_at, end_at=end_at)
            normalized = [self._normalize_event_row(row, "event_subject_map") for row in list(rows or [])]
            return [
                row
                for row in normalized
                if not str(row.get("source_channel") or "").startswith("product_runtime_")
            ][:limit]
        fn = getattr(self._read_gateway, "get_intel_news_events", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date)
        return [self._normalize_event_row(row, "db") for row in list(rows or [])[:limit]]

    async def _load_review_events_from_db(
        self, trade_date: date, limit: int,
        start_at: datetime | None = None, end_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        fn = getattr(self._read_gateway, "get_pre_market_review_events", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date, limit=limit, start_at=start_at, end_at=end_at)
        return [self._normalize_event_row(row, "event_review_queue") for row in list(rows or [])[:limit]]

    async def _load_intel_announcements(
        self,
        trade_date: date,
        limit: int,
        *,
        matched_only: bool = False,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """读取 intel 公告事件（news_event JOIN structured_intel_event）。"""
        fn = getattr(self._read_gateway, "get_intel_announcement_events", None)
        if not callable(fn):
            return []
        try:
            rows = await fn(trade_date, limit=limit, matched_only=matched_only,
                           start_time=start_at, end_time=end_at)
        except TypeError:
            if matched_only:
                return []
            rows = await fn(trade_date, limit=limit)
        result: list[dict[str, Any]] = []
        for row in (rows or []):
            data = dict(row)
            entities = data.get("entities") or {}
            if isinstance(entities, str):
                try:
                    entities = _json.loads(entities)
                except Exception:
                    entities = {}
            matched_subjects = data.get("matched_subjects") or []
            if isinstance(matched_subjects, str):
                try:
                    matched_subjects = _json.loads(matched_subjects)
                except Exception:
                    matched_subjects = []
            result.append({
                "event_id": data.get("event_id"),
                "stock_code": data.get("stock_code", ""),
                "stock_name": data.get("stock_name", ""),
                "title": data.get("title", ""),
                "summary": data.get("summary", ""),
                "event_type": data.get("event_type", ""),
                "event_level": data.get("event_level", "normal"),
                "publish_time": str(data.get("publish_time") or ""),
                "confidence": self._float_or_none(data.get("confidence")),
                "impact_score": self._float_or_zero(data.get("impact_score")),
                "entities": entities,
                "catalyst_tags": list(data.get("catalyst_tags") or []),
                "risk_tags": list(data.get("risk_tags") or []),
                "theme_matched": bool(data.get("theme_matched")),
                "matched_subjects": list(matched_subjects or []),
                "pdf_url": data.get("pdf_url") or "",
                "source_trace_id": data.get("source_trace_id") or "",
                "source_stage": "matched_intel_join" if data.get("theme_matched") else "raw_intel_join",
            })
        return result

    @staticmethod
    def _build_company_announcements(
        intel_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """按 stock_code 分组公告事件，生成 company_announcements section。"""
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ev in intel_events:
            code = str(ev.get("stock_code") or "").strip()
            if not code:
                continue
            grouped[code].append(ev)

        result: list[dict[str, Any]] = []
        for code, events in grouped.items():
            events_sorted = sorted(
                events,
                key=lambda e: float(e.get("impact_score") or 0),
                reverse=True,
            )
            result.append({
                "stock_code": code,
                "stock_name": events_sorted[0].get("stock_name", ""),
                "announcement_count": len(events_sorted),
                "announcements": [
                    {
                        "event_id": e.get("event_id"),
                        "title": e.get("title", ""),
                        "summary": e.get("summary", ""),
                        "event_type": e.get("event_type", ""),
                        "event_level": e.get("event_level", "normal"),
                        "publish_time": e.get("publish_time", ""),
                        "confidence": e.get("confidence"),
                        "impact_score": e.get("impact_score"),
                        "catalyst_tags": e.get("catalyst_tags", []),
                        "risk_tags": e.get("risk_tags", []),
                        "theme_matched": bool(e.get("theme_matched")),
                        "matched_subjects": e.get("matched_subjects", []),
                        "pdf_url": e.get("pdf_url", ""),
                        "source_stage": e.get("source_stage", "raw_intel_join"),
                        "source_trace_id": e.get("source_trace_id", ""),
                    }
                    for e in events_sorted
                ],
            })
        # 按公告数量和最高 impact_score 排
        result.sort(
            key=lambda g: (-g["announcement_count"],
                          -max((a.get("impact_score") or 0) for a in g["announcements"]))
        )
        return result

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
            affected = await self._write_gateway.upsert_pre_market_brief_snapshot(doc, force=force)
        except TypeError:
            if force:
                raise
            affected = await self._write_gateway.upsert_pre_market_brief_snapshot(doc)
        get_snapshot = getattr(self._write_gateway, "get_pre_market_brief_snapshot", None)
        if int(affected or 0) <= 0:
            if not force and callable(get_snapshot):
                existing = await get_snapshot(trade_date)
                if str((existing or {}).get("status") or "").lower() == "final":
                    return
            raise RuntimeError(
                "pre_market_brief_snapshot write skipped or failed: "
                f"trade_date={trade_date.isoformat()}, "
                f"snapshot_version={self.SNAPSHOT_VERSION}, force={force}"
            )
        if callable(get_snapshot):
            saved = await get_snapshot(trade_date)
            if not saved:
                raise RuntimeError(
                    "pre_market_brief_snapshot write verification failed: "
                    f"trade_date={trade_date.isoformat()}, "
                    f"snapshot_version={self.SNAPSHOT_VERSION}"
                )

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
        intel_announcements_raw: list[dict[str, Any]],
        intel_announcements_matched: list[dict[str, Any]],
        risk_alerts: list[dict[str, Any]] | None = None,
        opportunity_alerts: list[dict[str, Any]] | None = None,
        limit: int = 200,
    ) -> dict[str, list[dict[str, Any]]]:
        matched_events = self._dedupe_by_key(matched_events, key_fields=("event_id", "subject_key", "title"))
        matched_events = self._select_primary_event_matches(matched_events)
        matched_events = self._dedupe_major_event_title_variants(matched_events)
        major_drop_rows = [row for row in matched_events if self._is_low_value_major_event(row)]
        major_events = [row for row in matched_events if row not in major_drop_rows][:limit]
        review_events_all = self._dedupe_by_key(review_events, key_fields=("event_id", "title"))
        unknown_events_all = self._dedupe_by_key(unknown_events, key_fields=("event_id", "title"))
        review_drop_rows = [row for row in review_events_all if self._is_dropped_or_low_value_event(row)]
        unknown_drop_rows = [row for row in unknown_events_all if self._is_dropped_or_low_value_event(row)]
        review_events = [row for row in review_events_all if row not in review_drop_rows][:limit]
        unknown_events = [row for row in unknown_events_all if row not in unknown_drop_rows][:limit]
        company_announcements_raw = self._build_company_announcements(intel_announcements_raw)
        company_announcements_matched = self._build_company_announcements(intel_announcements_matched)
        # P1-E: merge rule-based alerts with legacy review/unknown alerts
        legacy_risk = self._build_risk_alerts(review_events, unknown_events)
        all_risk = [
            row
            for row in legacy_risk + (risk_alerts or [])[:limit]
            if not self._is_dropped_or_low_value_alert(row)
        ]
        dropped_rows = [*major_drop_rows, *review_drop_rows, *unknown_drop_rows]
        dropped_diagnostics = self._build_dropped_diagnostics(dropped_rows)
        return {
            "major_events": sorted(major_events, key=lambda row: float(row.get("impact_score") or 0), reverse=True)[:limit],
            "matched_themes": self._build_matched_themes(major_events),
            "review_events": review_events,
            "unknown_watch": unknown_events,
            "risk_alerts": all_risk,
            "opportunity_alerts": (opportunity_alerts or [])[:limit],
            "event_driven_opportunities": [],
            "_dropped_diagnostics": dropped_diagnostics,
            # === Phase 6A: 一手信息 section ===
            "company_announcements": company_announcements_raw,
            "company_announcements_raw": company_announcements_raw,
            "company_announcements_matched": company_announcements_matched,
            "earnings_alerts": [],
            "research_highlights": [],
            "institutional_survey": [],
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

    @staticmethod
    def _select_primary_event_matches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        primary_by_event: dict[Any, dict[str, Any]] = {}
        passthrough: list[dict[str, Any]] = []
        for row in rows:
            event_id = row.get("event_id")
            if event_id in (None, ""):
                passthrough.append(row)
                continue
            previous = primary_by_event.get(event_id)
            if previous is None or PreMarketBriefBuilder._primary_rank_key(row) > PreMarketBriefBuilder._primary_rank_key(previous):
                primary_by_event[event_id] = row
        return [*primary_by_event.values(), *passthrough]

    @staticmethod
    def _primary_rank_key(row: dict[str, Any]) -> tuple[float, float, str]:
        return (
            float(row.get("confidence") or 0.0),
            float(row.get("impact_score") or 0.0),
            str(row.get("occurred_at") or ""),
        )

    @staticmethod
    def _dedupe_major_event_title_variants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best_by_story: dict[tuple[str, str], dict[str, Any]] = {}
        passthrough: list[dict[str, Any]] = []
        for row in rows:
            subject_key = str(row.get("subject_key") or "").strip()
            title_key = PreMarketBriefBuilder._canonical_major_event_title(row.get("title"))
            if not subject_key or not title_key:
                passthrough.append(row)
                continue
            story_key = (subject_key, title_key)
            previous = best_by_story.get(story_key)
            if previous is None or PreMarketBriefBuilder._primary_rank_key(row) > PreMarketBriefBuilder._primary_rank_key(previous):
                best_by_story[story_key] = row
        return [*best_by_story.values(), *passthrough]

    @staticmethod
    def _canonical_major_event_title(value: Any) -> str:
        title = str(value or "").strip()
        bracket_title = re.match(r"^【([^】]+)】", title)
        if bracket_title:
            title = bracket_title.group(1)
        return re.sub(r"[\s【】]+", "", title)

    @staticmethod
    def _is_low_value_major_event(row: dict[str, Any]) -> bool:
        text = " ".join(str(row.get(field) or "") for field in ("title", "summary"))
        low_value_terms = (
            "减持",
            "回购",
            "澄清",
            "交易监管",
            "问询函",
            "关注函",
            "限制开仓",
            "天气预警",
            "暴雨",
            "山洪",
            "地震灾害",
            "灾后应急",
            "列车停运",
            "旅客列车停",
            "任命",
            "选举",
            "权益变动",
            "投资者接待日",
            "集体接待日",
            "业绩说明会",
            "行政监管",
            "监管措施决定书",
            "警示函",
            "应诉通知书",
            "一季度财报",
            "季度财报",
            "发布财报",
        )
        return any(term in text for term in low_value_terms)

    @classmethod
    def _is_dropped_or_low_value_event(cls, row: dict[str, Any]) -> bool:
        reason = str(row.get("reason") or row.get("reason_code") or "")
        if reason in LOW_VALUE_DROP_REASON_CODES:
            return True
        action = str(row.get("action") or "")
        if action == "drop_event":
            return True
        decision = str(row.get("decision") or "").upper()
        if decision in {"DROPPED", "SKIPPED"}:
            return True
        return cls._is_low_value_major_event(row)

    @staticmethod
    def _is_dropped_or_low_value_alert(row: dict[str, Any]) -> bool:
        text = _json.dumps(row, ensure_ascii=False) if isinstance(row, dict) else str(row)
        return any(term in text for term in LOW_VALUE_DROP_REASON_CODES) or any(
            term in text
            for term in (
                "行政监管",
                "监管函",
                "警示函",
                "责令改正",
                "问询函",
                "关注函",
                "澄清",
                "风险提示",
                "交易异动",
                "连板",
                "天气预警",
                "山洪",
                "暴雨",
                "地震",
                "列车停运",
                "回购",
                "减持",
                "权益变动",
                "投资者接待日",
                "集体接待日",
                "业绩说明会",
                "第一季度",
                "一季度",
                "财报",
                "营收",
                "净利润",
                "上市聆讯",
            )
        )

    @staticmethod
    def _build_dropped_diagnostics(rows: list[dict[str, Any]]) -> dict[str, int]:
        diagnostics = {
            "dropped_event_count": len(rows),
            "low_value_dropped_count": len(rows),
            "duplicate_dropped_count": 0,
            "regulatory_notice_dropped_count": 0,
            "ordinary_earnings_dropped_count": 0,
        }
        for row in rows:
            reason = str(row.get("reason") or "")
            text = " ".join(str(row.get(field) or "") for field in ("title", "summary", "reason"))
            if "duplicate" in reason or "重复" in text:
                diagnostics["duplicate_dropped_count"] += 1
            if any(term in text for term in ("行政监管", "监管函", "警示函", "责令改正")):
                diagnostics["regulatory_notice_dropped_count"] += 1
            if any(term in text for term in ("第一季度", "一季度", "Q1", "财报", "营收", "净利润")):
                diagnostics["ordinary_earnings_dropped_count"] += 1
        return diagnostics

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
                    "events": [
                        {
                            "event_id": e.get("event_id"),
                            "title": e.get("title", ""),
                            "summary": e.get("summary", ""),
                            "theme_name": e.get("theme_name", ""),
                            "reason": e.get("reason", ""),
                        }
                        for e in review_events[:5]
                    ],
                }
            )
        if unknown_events:
            alerts.append(
                {
                    "risk_type": "unknown_event_watch",
                    "count": len(unknown_events),
                    "message": "存在未匹配题材事件，仅进入观察区。",
                    "events": [
                        {
                            "event_id": e.get("event_id"),
                            "title": e.get("title", ""),
                            "summary": e.get("summary", ""),
                        }
                        for e in unknown_events[:5]
                    ],
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


def _build_source_breakdown(
    *,
    matched_events: list[dict[str, Any]],
    review_events: list[dict[str, Any]],
    unknown_events: list[dict[str, Any]],
    intel_raw: list[dict[str, Any]],
    intel_matched: list[dict[str, Any]],
) -> dict[str, Any]:
    """P1-B: 按来源统计事件分布。"""
    from collections import defaultdict

    def _count_by_source(events: list[dict], key: str = "source_channel") -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for e in events:
            ch = str(e.get(key) or e.get("source_type") or "unknown")
            counts[ch] += 1
        return dict(counts)

    return {
        "matched_by_source": _count_by_source(matched_events),
        "review_by_source": _count_by_source(review_events),
        "unknown_by_source": _count_by_source(unknown_events),
        "intel_raw_announcements": len(intel_raw),
        "intel_matched_announcements": len(intel_matched),
        "total_events": len(matched_events) + len(review_events) + len(unknown_events),
    }


def diagnostic_ts(payload: dict[str, Any]) -> str:
    value = ((payload.get("diagnostics") or {}).get("last_rebuild_at") or "").replace(":", "").replace("-", "")
    return value[:15] or "unknown"

"""MainlineLogicChainBuilder — Phase 1 PR-2.

Computes logic_score from event chain and event series data.
Reads from DB tables: event_theme_map, news_event, theme_history_event.
Falls back to report_context if available.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .models import MainlineEvent, MainlineEventSeries, MainlineLogicEvidence

logger = logging.getLogger(__name__)

# ── event_type → base impact weight ──
EVENT_TYPE_WEIGHT: dict[str, float] = {
    "policy": 90, "政策": 90,
    "industry": 85, "产业": 85,
    "technology": 85, "技术": 85, "tech": 85,
    "order": 80, "订单": 80, "major_order": 80,
    "supply_demand": 80, "供需": 80,
    "overseas_mapping": 75, "海外": 75,
    "regulation": 75, "监管": 75,
    "company": 65, "公司": 65,
    "media": 50, "媒体": 50,
    "unknown": 40,
}

# subject_key field aliases
_SUBJECT_KEY_ALIASES = (
    "subject_key", "theme_subject_key", "matched_subject_key",
    "subject_id", "theme_id", "biz_key", "bizKey",
)


@dataclass
class MainlineLogicChainBuilder:
    """Build logic evidence from event data.

    Accepts optional DB pool. If pool is None, falls back to report_context.
    """

    pool: Any = None  # asyncpg pool

    async def build(
        self,
        *,
        trade_date: date,
        candidate_subjects: list[str] | None = None,
        report_context: dict[str, Any] | None = None,
    ) -> dict[str, MainlineLogicEvidence]:
        """Build logic evidence for each candidate subject.

        Returns dict[subject_key, MainlineLogicEvidence].
        """
        # ── 1. gather raw events from DB ──
        raw_by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)

        if self.pool is not None:
            await self._fetch_from_db(trade_date, raw_by_subject)

        # ── 2. also try report_context as fallback ──
        if report_context:
            self._extract_from_report_context(report_context, raw_by_subject)

        # ── 3. restrict to candidates if given ──
        if candidate_subjects:
            candidate_set = set(candidate_subjects)
            raw_by_subject = {
                k: v for k, v in raw_by_subject.items()
                if k in candidate_set
            }

        # ── 4. build evidence per subject ──
        result: dict[str, MainlineLogicEvidence] = {}
        for sk, raw_events in raw_by_subject.items():
            result[sk] = self._build_for_subject(sk, raw_events)

        # If no events at all, still populate candidates with empty evidence
        if candidate_subjects:
            for sk in candidate_subjects:
                if sk not in result:
                    result[sk] = _empty_evidence(sk)

        return result

    # ── DB fetch ──

    async def _fetch_from_db(
        self,
        td: date,
        out: dict[str, list[dict[str, Any]]],
        lookback_days: int = 7,
    ) -> None:
        """Fetch events from DB tables and group by subject_key."""
        start = td - timedelta(days=lookback_days)
        async with self.pool.acquire() as conn:
            # 1. theme_history_event — most direct
            rows = await conn.fetch(
                """SELECT subject_key, event_id, rank_date, driver_summary AS title,
                          description AS summary, heat, source_type AS source_channel,
                          evidence_json
                   FROM theme_history_event
                   WHERE rank_date BETWEEN $1::date AND $2::date
                   ORDER BY rank_date DESC""",
                start, td,
            )
            for r in rows:
                sk = str(r["subject_key"] or "").strip()
                if not sk:
                    continue
                ev = {
                    "event_id": str(r["event_id"] or ""),
                    "occurred_at": str(r["rank_date"] or ""),
                    "title": str(r["title"] or ""),
                    "summary": str(r["summary"] or "")[:200],
                    "event_type": self._classify_event_type(str(r["title"] or "")),
                    "impact_score": self._heat_to_impact(int(r["heat"] or 0) if r["heat"] else 0),
                    "confidence": 0.7,
                    "source_channel": str(r["source_channel"] or "theme_history_event"),
                    "subject_key": sk,
                }
                out[sk].append(ev)

            # 2. news_event via event_theme_map join
            rows2 = await conn.fetch(
                """SELECT etm.event_id, ne.event_type, ne.confidence, ne.summary,
                          ne.event_time, ne.severity_score, ne.source_weight,
                          ne.entities, t.subject_key AS theme_subject_key,
                          COALESCE(ne.summary, '') AS title
                   FROM event_theme_map etm
                   JOIN news_event ne ON ne.id = etm.event_id
                   JOIN theme_master t ON t.id = etm.theme_id
                   WHERE etm.created_at::date BETWEEN $1::date AND $2::date
                     AND ne.event_time::date BETWEEN $1::date AND $2::date
                   ORDER BY ne.event_time DESC
                   LIMIT 2000""",
                start, td,
            )
            for r in rows2:
                sk = str(r["theme_subject_key"] or "").strip()
                if not sk:
                    continue
                ev = {
                    "event_id": f"ne_{r['event_id']}",
                    "occurred_at": str(r["event_time"] or ""),
                    "title": str(r["summary"] or r["title"] or "")[:200],
                    "summary": str(r["summary"] or "")[:300],
                    "event_type": str(r["event_type"] or "unknown"),
                    "impact_score": self._float(r["severity_score"]) or self._float(r["confidence"]) or 0.5,
                    "confidence": self._float(r["confidence"]) or 0.5,
                    "source_channel": "news_event",
                    "subject_key": sk,
                }
                out[sk].append(ev)

    # ── report_context extraction ──

    def _extract_from_report_context(
        self,
        ctx: dict[str, Any],
        out: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Try extracting events from report_context if DB is not available."""
        sources = [
            ("event_theme_map", self._normalize_event_rows),
            ("news_event", self._normalize_event_rows),
            ("subject_history", self._normalize_event_rows),
            ("subject_event_stats", self._normalize_event_rows),
            ("theme_history_event", self._normalize_event_rows),
        ]
        for key, normalizer in sources:
            val = ctx.get(key)
            if not val:
                continue
            if isinstance(val, dict):
                for sk, events in val.items():
                    if isinstance(events, list):
                        normalized = normalizer(str(sk), events)
                        out.setdefault(str(sk), []).extend(normalized)
            elif isinstance(val, list):
                by_sk: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for item in val:
                    if not isinstance(item, dict):
                        continue
                    sk = self._resolve_subject_key(item)
                    if sk:
                        by_sk[sk].append(dict(item))
                for sk, events in by_sk.items():
                    out.setdefault(sk, []).extend(normalizer(sk, events))

    @staticmethod
    def _normalize_event_rows(sk: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in rows[:20]:
            if not isinstance(item, dict):
                continue
            result.append({
                "event_id": str(item.get("event_id") or item.get("id") or ""),
                "occurred_at": str(item.get("occurred_at") or item.get("event_time") or item.get("rank_date") or ""),
                "title": str(item.get("title") or item.get("name") or item.get("driver_summary") or ""),
                "summary": str(item.get("summary") or item.get("description") or "")[:200],
                "event_type": str(item.get("event_type") or item.get("source_type") or "unknown"),
                "impact_score": _to_float(item.get("impact_score") or item.get("severity_score") or item.get("confidence")),
                "confidence": _to_float(item.get("confidence") or item.get("impact_score")),
                "source_channel": str(item.get("source_channel") or item.get("source") or "report_context"),
                "subject_key": sk,
            })
        return result

    # ── per-subject scoring ──

    def _build_for_subject(
        self,
        subject_key: str,
        raw_events: list[dict[str, Any]],
    ) -> MainlineLogicEvidence:
        if not raw_events:
            return _empty_evidence(subject_key)

        # Deduplicate by event_id
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for ev in raw_events:
            eid = str(ev.get("event_id") or ev.get("title") or "")
            if eid and eid not in seen:
                seen.add(eid)
                unique.append(ev)

        # Sort by occurred_at desc
        unique.sort(key=lambda x: str(x.get("occurred_at") or ""), reverse=True)

        # ── 4a: event_impact_score ──
        impact_scores = []
        for ev in unique[:5]:
            etype = str(ev.get("event_type") or "unknown").lower()
            weight = EVENT_TYPE_WEIGHT.get(etype, 40)
            conf = _to_float(ev.get("confidence")) or 0.5
            impact_scores.append(weight * 0.7 + conf * 30)

        event_impact = round(sum(impact_scores) / len(impact_scores), 1) if impact_scores else None

        # ── 4b: event_continuity_score ──
        days: set[str] = set()
        for ev in unique:
            d = str(ev.get("occurred_at") or "")[:10]
            if d:
                days.add(d)

        active_days = len(days)
        if active_days >= 4:
            continuity = 90.0
        elif active_days == 3:
            continuity = 75.0
        elif active_days == 2:
            continuity = 60.0
        elif active_days == 1:
            continuity = 40.0
        else:
            continuity = 0.0

        # ── 4c: narrative_consistency ──
        series_list = self._build_event_series(subject_key, unique)
        if series_list and len(series_list) >= 1:
            best_cs = max(s.get("consistency_score", 0) for s in series_list)
            narrative = float(best_cs)
        elif len(unique) >= 3:
            narrative = 55.0
        elif len(unique) == 2:
            narrative = 45.0
        else:
            narrative = 40.0

        # ── 4d: novelty_score ──
        novelty = self._novelty_score(active_days, unique)

        # ── 4e: composite logic_score ──
        if any(x is not None for x in (event_impact, continuity, narrative, novelty)):
            logic_score = round(
                (event_impact or 0) * 0.35
                + continuity * 0.30
                + narrative * 0.20
                + (novelty or 50) * 0.15,
                1,
            )
        else:
            logic_score = None

        # ── event_chain (top 3) ──
        event_chain: list[dict[str, Any]] = []
        for ev in unique[:5]:
            event_chain.append({
                "event_id": str(ev.get("event_id") or ""),
                "occurred_at": str(ev.get("occurred_at") or ""),
                "title": str(ev.get("title") or ""),
                "summary": str(ev.get("summary") or ""),
                "event_type": str(ev.get("event_type") or "unknown"),
                "impact_score": _to_float(ev.get("impact_score")),
                "confidence": _to_float(ev.get("confidence")),
                "source_channel": str(ev.get("source_channel") or "unknown"),
                "subject_key": subject_key,
            })
        event_chain.sort(key=lambda x: _to_float(x.get("impact_score")) or 0, reverse=True)
        event_chain = event_chain[:3]

        return MainlineLogicEvidence(
            logic_score=logic_score,
            event_impact_score=event_impact,
            event_continuity_score=continuity,
            narrative_consistency_score=narrative,
            novelty_score=novelty,
            event_chain=event_chain,
            event_series=series_list,
            logic_summary=(
                f"近{lookback_days}日出现{len(unique)}条关键事件，"
                f"活跃{active_days}天，逻辑分{logic_score}"
                if logic_score else "无关键事件数据"
            ),
            diagnostics={
                "event_count": len(unique),
                "event_series_count": len(series_list),
                "active_days_7d": active_days,
                "event_sources": sorted(set(
                    ev.get("source_channel", "unknown") for ev in unique
                )),
                "missing_fields": [],
                "fallback_used": [],
                "logic_score_source": "event_chain_v1",
            },
        )

    # ── helpers ──

    @classmethod
    def _build_event_series(
        cls,
        subject_key: str,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build event series by grouping related events."""
        if len(events) < 2:
            return []

        # Simple grouping: same event_type + date proximity
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ev in events:
            etype = str(ev.get("event_type") or "unknown")
            groups[etype].append(ev)

        result: list[dict[str, Any]] = []
        for etype, group in groups.items():
            if len(group) < 2:
                continue
            days = sorted(set(
                str(e.get("occurred_at") or "")[:10]
                for e in group
                if str(e.get("occurred_at") or "")
            ))
            if len(days) < 1:
                continue

            result.append({
                "series_id": f"ml_{subject_key}_{etype}_{days[-1].replace('-','')}",
                "series_type": f"{etype}_chain",
                "event_count": len(group),
                "active_days_7d": len(days),
                "first_seen": days[0] if days else None,
                "last_seen": days[-1] if days else None,
                "key_events": [
                    {
                        "event_id": e.get("event_id"),
                        "title": e.get("title"),
                        "occurred_at": e.get("occurred_at"),
                    }
                    for e in group[:3]
                ],
                "logic_summary": f"近7日持续出现{etype}类事件",
                "consistency_score": min(95.0, 50.0 + len(group) * 10.0 + len(days) * 5.0),
            })

        result.sort(key=lambda x: x["consistency_score"], reverse=True)
        return result

    @classmethod
    def _novelty_score(cls, active_days: int, events: list[dict[str, Any]]) -> float:
        if len(events) >= 5 and active_days >= 3:
            return 75.0
        if active_days == 1 and len(events) >= 2:
            return 70.0
        if active_days <= 1:
            return 55.0
        return 50.0

    @staticmethod
    def _heat_to_impact(heat: int) -> float:
        if heat >= 90:
            return 0.90
        if heat >= 70:
            return 0.75
        if heat >= 50:
            return 0.60
        if heat >= 30:
            return 0.45
        return 0.30

    @staticmethod
    def _classify_event_type(title: str) -> str:
        t = (title or "").lower()
        keywords = [
            ("政策", "policy"), ("产业", "industry"), ("技术", "technology"),
            ("订单", "order"), ("海外", "overseas_mapping"), ("监管", "regulation"),
            ("发布", "media"), ("公告", "company"),
        ]
        for kw, etype in keywords:
            if kw in t:
                return etype
        return "unknown"

    @staticmethod
    def _resolve_subject_key(item: dict[str, Any]) -> str:
        for alias in _SUBJECT_KEY_ALIASES:
            val = item.get(alias)
            if val and str(val).strip():
                return str(val).strip()
        return ""

    @staticmethod
    def _float(val: Any) -> float | None:
        try:
            if val is None or val == "":
                return None
            return float(val)
        except Exception:
            return None


# ── helpers ──

lookback_days = 7  # module-level constant used in build


def _to_float(val: Any) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except Exception:
        return None


def _empty_evidence(subject_key: str = "") -> MainlineLogicEvidence:
    return MainlineLogicEvidence(
        logic_score=None,
        diagnostics={
            "event_count": 0,
            "event_series_count": 0,
            "active_days_7d": 0,
            "event_sources": [],
            "missing_fields": ["event_context"],
            "fallback_used": [],
            "logic_score_source": "none",
        },
    )

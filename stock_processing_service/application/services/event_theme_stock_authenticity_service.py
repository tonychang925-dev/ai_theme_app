from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from stock_processing_service.domain.services.enhanced_mainline_judgement_service import (
    MainlineJudgementService,
    ThemeEventStats,
    ThemeMarketStats,
)


class EventThemeStockAuthenticityService:
    """Build explicit topic authenticity features for OneToTwo.

    This service reuses the existing event-chain + market-recognition
    mainline judging kernel, then adds stock-side evidence from
    subject_stock_daily_snapshot / stock_facts. It is intentionally
    read-only and produces explainable feature JSON for ranking.
    """

    def __init__(self, read_port: Any, *, lookback_days: int = 7) -> None:
        self._read = read_port
        self._lookback_days = max(1, int(lookback_days))
        self._judger = MainlineJudgementService()

    async def build(
        self,
        *,
        trade_date: date,
        subject_keys: list[str],
        subject_stock_rows: list[dict[str, Any]] | None = None,
        subject_market_breadth: dict[str, dict[str, Any]] | None = None,
        active_subject_keys: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        return await self._build_authenticity_map(
            trade_date=trade_date,
            subject_keys=subject_keys,
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
            pair_level=False,
        )

    async def build_stock_subject_authenticity(
        self,
        *,
        trade_date: date,
        subject_keys: list[str],
        subject_stock_rows: list[dict[str, Any]] | None = None,
        subject_market_breadth: dict[str, dict[str, Any]] | None = None,
        active_subject_keys: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        current_trade_date = trade_date.isoformat()
        subject_stock_rows = [
            dict(row or {})
            for row in (subject_stock_rows or [])
            if self._date_str(row.get("trade_date")) == current_trade_date
        ]
        return await self._build_authenticity_map(
            trade_date=trade_date,
            subject_keys=subject_keys,
            subject_stock_rows=subject_stock_rows,
            subject_market_breadth=subject_market_breadth,
            active_subject_keys=active_subject_keys,
            pair_level=True,
        )

    async def _build_authenticity_map(
        self,
        *,
        trade_date: date,
        subject_keys: list[str],
        subject_stock_rows: list[dict[str, Any]] | None,
        subject_market_breadth: dict[str, dict[str, Any]] | None,
        active_subject_keys: set[str] | None,
        pair_level: bool,
    ) -> dict[str, dict[str, Any]]:
        subject_keys = [str(sk).strip() for sk in dict.fromkeys(subject_keys or []) if str(sk).strip()]
        if not subject_keys:
            return {}

        subject_market_breadth = subject_market_breadth or {}
        active_subject_keys = active_subject_keys or set()
        subject_stock_rows = [dict(row or {}) for row in (subject_stock_rows or [])]
        stock_rows_by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in subject_stock_rows:
            subject_key = str(row.get("subject_key") or "").strip()
            if subject_key:
                stock_rows_by_subject[subject_key].append(dict(row))

        event_rows = await self._safe_get_subject_event_stats(trade_date, subject_keys)
        result: dict[str, dict[str, Any]] = {}
        for subject_key in subject_keys:
            theme_name = self._resolve_theme_name(
                subject_key=subject_key,
                event_rows=event_rows,
                stock_rows=stock_rows_by_subject.get(subject_key, []),
                breadth_row=subject_market_breadth.get(subject_key, {}),
            )
            event_row = event_rows.get(subject_key, {})
            stock_rows = stock_rows_by_subject.get(subject_key, [])
            breadth_row = dict(subject_market_breadth.get(subject_key, {}) or {})

            if pair_level and stock_rows:
                for stock_row in stock_rows:
                    pair_key = self._pair_key(stock_row.get("stock_id"), subject_key)
                    if not pair_key:
                        continue
                    result[pair_key] = self._build_topic_authenticity(
                        subject_key=subject_key,
                        theme_name=theme_name,
                        event_row=event_row,
                        stock_rows=[dict(stock_row)],
                        breadth_row=breadth_row,
                        active_subject_keys=active_subject_keys,
                        pair_level=True,
                    )
            else:
                result[subject_key] = self._build_topic_authenticity(
                    subject_key=subject_key,
                    theme_name=theme_name,
                    event_row=event_row,
                    stock_rows=stock_rows,
                    breadth_row=breadth_row,
                    active_subject_keys=active_subject_keys,
                    pair_level=False,
                )

        return result

    def _build_topic_authenticity(
        self,
        *,
        subject_key: str,
        theme_name: str,
        event_row: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        breadth_row: dict[str, Any],
        active_subject_keys: set[str],
        pair_level: bool,
    ) -> dict[str, Any]:
        event_stats = self._to_event_stats(subject_key, theme_name, event_row)
        market_stats = self._to_market_stats(subject_key, theme_name, stock_rows, breadth_row)
        event_chain_score = self._judger.compute_event_chain_score(event_stats)
        continuity_score = self._judger.compute_event_chain_continuity_score(event_stats)
        market_score = self._judger.compute_market_recognition_score(market_stats)
        stability_score = self._judger.compute_mainline_stability_score(event_stats, market_stats)
        is_main_theme, theme_tier, conclusion = self._judger.classify_theme_tier(
            event_chain_score=event_chain_score,
            event_chain_continuity_score=continuity_score,
            market_recognition_score=market_score,
            mainline_stability_score=stability_score,
        )

        event_theme_score = min(100.0, event_chain_score * 0.5 + continuity_score * 0.3 + market_score * 0.2)
        event_stock_score = min(100.0, market_score * 0.65 + self._stock_depth_score(stock_rows) * 0.35)
        stock_theme_score = self._stock_theme_score(stock_rows, breadth_row, active_subject_keys, subject_key)
        freshness_score = self._freshness_score(event_stats)
        purity_score = min(
            100.0,
            event_theme_score * 0.35
            + event_stock_score * 0.25
            + stock_theme_score * 0.25
            + freshness_score * 0.15,
        )
        score = purity_score
        if is_main_theme:
            score += 5.0
        if market_stats.leader_limit_up:
            score += 5.0
        if subject_key in active_subject_keys:
            score += 3.0
        score = min(100.0, score)

        level = self._level(
            score=score,
            is_main_theme=is_main_theme,
            market_recognition_score=market_score,
            leader_limit_up=market_stats.leader_limit_up,
            has_stock_rows=bool(stock_rows),
            has_events=event_stats.recent_event_count > 0 or event_stats.today_event_count > 0,
        )

        evidence_events = [s for s in event_stats.sample_summaries[:3] if s]
        evidence_stock_facts = self._stock_evidence(stock_rows)
        matched_theme_anchors = [
            {
                "subject_key": subject_key,
                "theme_name": theme_name,
                "source": "subject_event_stats",
                "is_main_theme": is_main_theme,
                "theme_tier": theme_tier,
            }
        ]
        matched_stock_terms = self._matched_stock_terms(stock_rows)
        negative_reasons = self._negative_reasons(
            event_stats=event_stats,
            market_stats=market_stats,
            stock_rows=stock_rows,
            is_main_theme=is_main_theme,
            score=score,
        )

        payload = {
            "subject_key": subject_key,
            "theme_name": theme_name,
            "level": level,
            "score": round(score, 2),
            "purity_score": round(purity_score, 2),
            "event_theme_score": round(event_theme_score, 2),
            "event_stock_score": round(event_stock_score, 2),
            "stock_theme_score": round(stock_theme_score, 2),
            "freshness_score": round(freshness_score, 2),
            "event_chain_score": round(event_chain_score, 2),
            "event_chain_continuity_score": round(continuity_score, 2),
            "market_recognition_score": round(market_score, 2),
            "mainline_stability_score": round(stability_score, 2),
            "is_main_theme": is_main_theme,
            "theme_tier": theme_tier,
            "conclusion": conclusion,
            "evidence_events": evidence_events,
            "evidence_stock_facts": evidence_stock_facts,
            "matched_theme_anchors": matched_theme_anchors,
            "matched_stock_terms": matched_stock_terms,
            "negative_reasons": negative_reasons,
            "authenticity_scope": "stock_subject" if pair_level else "subject",
        }
        if pair_level and stock_rows:
            stock_row = stock_rows[0]
            payload["stock_id"] = self._stock_key(stock_row.get("stock_id") or stock_row.get("stock_code"))
            payload["stock_name"] = str(stock_row.get("stock_name") or "")
            payload["stock_subject_key"] = self._pair_key(stock_row.get("stock_id"), subject_key)
        return payload

    async def _safe_get_subject_event_stats(self, trade_date: date, subject_keys: list[str]) -> dict[str, dict[str, Any]]:
        try:
            rows = await self._read.get_subject_event_stats(
                trade_date=trade_date,
                subject_keys=subject_keys,
                lookback_days=self._lookback_days,
            )
        except Exception:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            data = dict(row.__dict__) if hasattr(row, "__dict__") else dict(row or {})
            subject_key = str(data.get("subject_key") or "").strip()
            if subject_key:
                result[subject_key] = data
        return result

    def _resolve_theme_name(
        self,
        *,
        subject_key: str,
        event_rows: dict[str, dict[str, Any]],
        stock_rows: list[dict[str, Any]],
        breadth_row: dict[str, Any],
    ) -> str:
        row = event_rows.get(subject_key, {})
        for key in ("theme_name", "subject_name", "name"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        for item in stock_rows:
            for key in ("subject_name", "theme_name"):
                value = str(item.get(key) or "").strip()
                if value:
                    return value
        for key in ("theme_name", "subject_name"):
            value = str(breadth_row.get(key) or "").strip()
            if value:
                return value
        return subject_key

    def _to_event_stats(self, subject_key: str, theme_name: str, row: dict[str, Any]) -> ThemeEventStats:
        today_event_count = self._int(row.get("today_event_count"))
        recent_event_count = self._int(row.get("recent_event_count"))
        distinct_event_days = self._int(row.get("distinct_event_days"))
        key_event_count = self._int(row.get("key_event_count"))
        sample_summaries = [str(item).strip() for item in (row.get("sample_summaries") or []) if str(item).strip()]
        return ThemeEventStats(
            subject_key=subject_key,
            theme_name=theme_name,
            today_event_count=today_event_count,
            recent_event_count=recent_event_count,
            distinct_event_days=distinct_event_days,
            key_event_count=key_event_count,
            sample_summaries=sample_summaries,
        )

    def _to_market_stats(
        self,
        subject_key: str,
        theme_name: str,
        stock_rows: list[dict[str, Any]],
        breadth_row: dict[str, Any],
    ) -> ThemeMarketStats:
        leader_row = self._leader_row(stock_rows)
        return ThemeMarketStats(
            subject_key=subject_key,
            theme_name=theme_name,
            limit_up_count=self._int(breadth_row.get("subject_limit_up_count") or breadth_row.get("limit_up_count")),
            strong_stock_count=self._int(breadth_row.get("subject_strong_count") or breadth_row.get("strong_count")),
            leader_pct_chg=self._float(leader_row.get("pct_chg") if leader_row else breadth_row.get("leader_pct_chg")),
            member_count=max(len({str(row.get("stock_id") or row.get("stock_code") or "") for row in stock_rows if str(row.get("stock_id") or row.get("stock_code") or "").strip()}), self._int(breadth_row.get("member_count"))),
            leader_limit_up=bool(
                (leader_row and (leader_row.get("limit_up") or self._float(leader_row.get("pct_chg")) >= 9.8))
                or breadth_row.get("leader_limit_up")
            ),
        )

    def _stock_depth_score(self, stock_rows: list[dict[str, Any]]) -> float:
        if not stock_rows:
            return 0.0
        score = 0.0
        leader_count = 0
        strong_count = 0
        for row in stock_rows:
            pct_chg = self._float(row.get("pct_chg"))
            rank_order = self._int(row.get("rank_order"), 999)
            if row.get("is_leader"):
                leader_count += 1
                score += 18.0
            if bool(row.get("limit_up")) or (pct_chg is not None and pct_chg >= 7.0):
                strong_count += 1
                score += 8.0
            if rank_order <= 3:
                score += 4.0
        if leader_count:
            score += 10.0
        if strong_count >= 3:
            score += 8.0
        return min(100.0, score)

    def _stock_theme_score(
        self,
        stock_rows: list[dict[str, Any]],
        breadth_row: dict[str, Any],
        active_subject_keys: set[str],
        subject_key: str,
    ) -> float:
        score = 20.0 if subject_key in active_subject_keys else 0.0
        if stock_rows:
            leaders = sum(1 for row in stock_rows if row.get("is_leader"))
            top_rank = min((self._int(row.get("rank_order"), 999) for row in stock_rows), default=999)
            score += min(40.0, leaders * 12.0)
            if top_rank <= 3:
                score += 15.0
            if len(stock_rows) >= 3:
                score += 10.0
        if self._int(breadth_row.get("subject_limit_up_count") or breadth_row.get("limit_up_count")) >= 2:
            score += 20.0
        elif self._int(breadth_row.get("subject_limit_up_count") or breadth_row.get("limit_up_count")) >= 1:
            score += 10.0
        return min(100.0, score)

    def _freshness_score(self, event_stats: ThemeEventStats) -> float:
        score = 0.0
        score += min(event_stats.today_event_count, 3) * 15.0
        score += min(event_stats.key_event_count, 4) * 8.0
        score += min(event_stats.distinct_event_days, 5) * 6.0
        return min(100.0, score)

    def _level(
        self,
        *,
        score: float,
        is_main_theme: bool,
        market_recognition_score: float,
        leader_limit_up: bool,
        has_stock_rows: bool,
        has_events: bool,
    ) -> str:
        if score >= 80 and is_main_theme and leader_limit_up:
            return "core"
        if score >= 65 and (is_main_theme or market_recognition_score >= 60.0):
            return "direct"
        if score >= 45 and (has_stock_rows or has_events):
            return "related"
        if score >= 25:
            return "weak"
        return "unknown"

    def _stock_evidence(self, stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for row in sorted(
            stock_rows,
            key=lambda item: (
                0 if item.get("is_leader") else 1,
                self._int(item.get("rank_order"), 999),
                -(self._float(item.get("pct_chg")) or 0.0),
            ),
        )[:5]:
            evidence.append(
                {
                    "stock_id": str(row.get("stock_id") or row.get("stock_code") or ""),
                    "stock_name": str(row.get("stock_name") or ""),
                    "is_leader": bool(row.get("is_leader")),
                    "rank_order": self._int(row.get("rank_order"), 999),
                    "pct_chg": self._float(row.get("pct_chg")),
                    "limit_up": bool(row.get("limit_up")),
                }
            )
        return evidence

    def _matched_stock_terms(self, stock_rows: list[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        for row in stock_rows:
            name = str(row.get("stock_name") or "").strip()
            if name and name not in names:
                names.append(name)
        return names[:5]

    def _negative_reasons(
        self,
        *,
        event_stats: ThemeEventStats,
        market_stats: ThemeMarketStats,
        stock_rows: list[dict[str, Any]],
        is_main_theme: bool,
        score: float,
    ) -> list[str]:
        reasons: list[str] = []
        if event_stats.recent_event_count == 0 and event_stats.today_event_count == 0:
            reasons.append("missing_subject_event_stats")
        if not stock_rows:
            reasons.append("missing_subject_stock_rows")
        if not is_main_theme:
            reasons.append("not_confirmed_main_theme")
        if market_stats.limit_up_count <= 0:
            reasons.append("no_subject_limit_up")
        if score < 45:
            reasons.append("topic_authenticity_low")
        return reasons

    @staticmethod
    def _pair_key(stock_id: Any, subject_key: str) -> str:
        stock_key = EventThemeStockAuthenticityService._stock_key(stock_id)
        subject_key = str(subject_key or "").strip()
        if not stock_key or not subject_key:
            return ""
        return f"{stock_key}|{subject_key}"

    @staticmethod
    def _stock_key(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text.split(".")[0]

    @staticmethod
    def _date_str(value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return str(value.isoformat())
        return str(value)

    @staticmethod
    def _leader_row(stock_rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not stock_rows:
            return {}
        sorted_rows = sorted(
            stock_rows,
            key=lambda row: (
                0 if row.get("is_leader") else 1,
                -(float(row.get("pct_chg") or 0.0)),
                int(row.get("rank_order") or 999),
            ),
        )
        return dict(sorted_rows[0] or {})

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

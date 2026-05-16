from __future__ import annotations

from datetime import date
from typing import Any


class EventDrivenOpportunityBuilder:
    """Build read-only event-driven stock opportunities for pre-market brief.

    This MVP consumes existing object/pool outputs only. It does not run news
    structuring, theme matching, weak-to-strong selection, or StockMatchEngine.
    """

    def __init__(self, read_gateway: Any, *, max_stocks_per_theme: int = 5) -> None:
        self._read_gateway = read_gateway
        self._max_stocks_per_theme = max(1, int(max_stocks_per_theme))

    async def build(
        self,
        *,
        trade_date: date,
        matched_themes: list[dict[str, Any]],
        matched_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        subject_keys = [str(row.get("subject_key") or "") for row in matched_themes if row.get("subject_key")]
        subject_keys = [key for key in dict.fromkeys(subject_keys) if key]
        if not subject_keys:
            return []

        subject_rows = await self._safe_call("get_subject_stock_pool_by_trade_date", trade_date)
        subject_rows = [self._as_dict(row) for row in subject_rows if str(self._as_dict(row).get("subject_key") or "") in subject_keys]
        if not subject_rows:
            return []

        leaderboard_rows = await self._safe_call("get_theme_stock_leaderboard_by_trade_date", trade_date, subject_keys=subject_keys)
        strong_rows = await self._safe_call(
            "get_strong_stock_watch_view_rows",
            end_date=trade_date,
            window_days=7,
            include_removed=False,
            latest_per_stock=True,
            limit=1000,
        )
        w2s_rows = await self._safe_call("get_w2s_candidates_for_confirm_date", trade_date, limit=1000)
        if not w2s_rows:
            w2s_rows = await self._safe_call("get_w2s_candidates_by_trade_date", trade_date, limit=1000)
        identity_rows = await self._safe_call("get_mainline_identity_by_subject_keys", subject_keys, trade_date)
        cycle_rows = await self._safe_call("get_mainline_cycle_by_subject_keys", subject_keys, trade_date)

        leaderboard = self._index_by_subject_stock(leaderboard_rows)
        strong = self._index_by_subject_stock(strong_rows)
        w2s = self._index_by_subject_stock(w2s_rows)
        identity = {str(row.get("subject_key") or ""): self._as_dict(row) for row in identity_rows}
        cycle = {str(row.get("subject_key") or ""): self._as_dict(row) for row in cycle_rows}
        theme_by_key = {str(row.get("subject_key") or ""): row for row in matched_themes}
        events_by_key = self._group_events(matched_events)

        opportunities: list[dict[str, Any]] = []
        for subject_key in subject_keys:
            theme = theme_by_key.get(subject_key, {})
            rows = [row for row in subject_rows if str(row.get("subject_key") or "") == subject_key]
            stock_items = []
            for row in rows:
                stock_id = self._stock_id(row)
                key = (subject_key, stock_id)
                scored = self._score_stock(
                    subject_key=subject_key,
                    stock=row,
                    event_theme=theme,
                    leaderboard=leaderboard.get(key, {}),
                    strong=strong.get(key, {}),
                    w2s=w2s.get(key, {}),
                    identity=identity.get(subject_key, {}),
                    cycle=cycle.get(subject_key, {}),
                )
                if scored:
                    stock_items.append(scored)

            stock_items.sort(key=lambda item: (-float(item.get("score") or 0), item.get("stock_id", "")))
            stock_items = stock_items[: self._max_stocks_per_theme]
            if not stock_items:
                continue

            events = events_by_key.get(subject_key, [])
            tiers = {
                "A": [item for item in stock_items if item.get("level") == "A"],
                "B": [item for item in stock_items if item.get("level") == "B"],
                "C": [item for item in stock_items if item.get("level") == "C"],
            }
            opportunities.append(
                {
                    "subject_key": subject_key,
                    "theme_name": theme.get("theme_name") or rows[0].get("subject_name") or subject_key,
                    "event_count": int(theme.get("event_count") or len(events) or 0),
                    "latest_event_title": theme.get("latest_event_title") or (events[0].get("title") if events else ""),
                    "theme_confidence": theme.get("confidence"),
                    "tiers": tiers,
                    "stocks": stock_items,
                }
            )

        opportunities.sort(key=lambda item: (-len(item.get("stocks") or []), item.get("theme_name", "")))
        return opportunities

    def _score_stock(
        self,
        *,
        subject_key: str,
        stock: dict[str, Any],
        event_theme: dict[str, Any],
        leaderboard: dict[str, Any],
        strong: dict[str, Any],
        w2s: dict[str, Any],
        identity: dict[str, Any],
        cycle: dict[str, Any],
    ) -> dict[str, Any]:
        confidence = self._float(event_theme.get("confidence"), 0.0)
        rank = self._int(stock.get("rank_order") or leaderboard.get("leaderboard_rank"), 99)
        is_leader = bool(stock.get("is_leader")) or self._int(leaderboard.get("leaderboard_rank"), 99) == 1
        watch_score = self._float(strong.get("watch_score"), 0.0)
        w2s_score = self._float(w2s.get("candidate_score"), 0.0)
        identity_confirmed = (
            str(identity.get("identity_status") or "").lower() == "confirmed"
            or bool(identity.get("is_main_theme"))
        )
        cycle_state = str(cycle.get("final_cycle_state") or strong.get("cycle_state") or "").lower()

        event_theme_score = min(max(confidence, 0.0), 1.0) * 20.0
        theme_mainline_score = 20.0 if identity_confirmed else (10.0 if identity else 0.0)
        theme_cycle_score = self._cycle_score(cycle_state, bool(cycle.get("final_mainline_alive")))
        jyhf_relation_score = self._relation_score(rank)
        leader_score = 10.0 if is_leader else min(self._float(leaderboard.get("leader_score"), 0.0) / 10.0, 8.0)
        strong_watch_score = min(watch_score / 10.0, 10.0)
        weak_to_strong_score = min(w2s_score / 20.0, 5.0)
        risk_penalty = self._risk_penalty(cycle_state, strong)

        score = max(
            0.0,
            min(
                100.0,
                event_theme_score
                + theme_mainline_score
                + theme_cycle_score
                + jyhf_relation_score
                + leader_score
                + strong_watch_score
                + weak_to_strong_score
                - risk_penalty,
            ),
        )
        level = self._level(
            score=score,
            confidence=confidence,
            identity_confirmed=identity_confirmed,
            is_leader=is_leader,
            has_strong=bool(strong),
        )

        stock_id = self._stock_id(stock)
        return {
            "stock_id": stock_id,
            "stock_name": str(stock.get("stock_name") or strong.get("stock_name") or w2s.get("stock_name") or ""),
            "level": level,
            "score": round(score, 1),
            "reason": self._reason(identity_confirmed, cycle_state, is_leader, bool(strong), bool(w2s), rank),
            "risk": self._risk_text(cycle_state, strong),
            "evidence": {
                "subject_key": subject_key,
                "rank_order": rank if rank != 99 else None,
                "is_leader": is_leader,
                "mainline_confirmed": identity_confirmed,
                "cycle_state": cycle_state,
                "strong_watch": bool(strong),
                "weak_to_strong": bool(w2s),
                "score_breakdown": {
                    "event_theme_score": round(event_theme_score, 1),
                    "theme_mainline_score": round(theme_mainline_score, 1),
                    "theme_cycle_score": round(theme_cycle_score, 1),
                    "jyhf_relation_score": round(jyhf_relation_score, 1),
                    "leader_score": round(leader_score, 1),
                    "strong_watch_score": round(strong_watch_score, 1),
                    "weak_to_strong_score": round(weak_to_strong_score, 1),
                    "risk_penalty": round(risk_penalty, 1),
                },
            },
        }

    @staticmethod
    def _cycle_score(cycle_state: str, alive: bool) -> float:
        if cycle_state in {"acceleration", "repair", "maintain", "start", "fermentation"}:
            return 15.0
        if cycle_state in {"divergence", "fade_watch"}:
            return 7.0
        if alive:
            return 10.0
        return 0.0

    @staticmethod
    def _relation_score(rank: int) -> float:
        if rank <= 1:
            return 20.0
        if rank <= 3:
            return 16.0
        if rank <= 10:
            return 12.0
        return 8.0

    @staticmethod
    def _risk_penalty(cycle_state: str, strong: dict[str, Any]) -> float:
        if cycle_state in {"fade_confirmed", "fade"} or bool(strong.get("fade_confirmed")):
            return 20.0
        if cycle_state == "fade_watch" or bool(strong.get("fade_watch")):
            return 10.0
        return 0.0

    @staticmethod
    def _level(*, score: float, confidence: float, identity_confirmed: bool, is_leader: bool, has_strong: bool) -> str:
        if score >= 75 and confidence >= 0.75 and identity_confirmed and (is_leader or has_strong):
            return "A"
        if score >= 60 and confidence >= 0.65:
            return "B"
        return "C"

    @staticmethod
    def _reason(identity_confirmed: bool, cycle_state: str, is_leader: bool, has_strong: bool, has_w2s: bool, rank: int) -> str:
        parts = []
        if identity_confirmed:
            parts.append("主线题材确认")
        if cycle_state:
            parts.append(f"周期状态 {cycle_state}")
        if rank != 99:
            parts.append(f"题材映射排名 {rank}")
        if is_leader:
            parts.append("龙头/核心映射")
        if has_strong:
            parts.append("强势池支撑")
        if has_w2s:
            parts.append("弱转强候选加分")
        return "；".join(parts) or "题材映射成立"

    @staticmethod
    def _risk_text(cycle_state: str, strong: dict[str, Any]) -> str:
        if cycle_state in {"fade_confirmed", "fade"} or bool(strong.get("fade_confirmed")):
            return "题材退潮确认，机会仅观察。"
        if cycle_state == "fade_watch" or bool(strong.get("fade_watch")):
            return "题材退潮预警，需降低仓位预期。"
        return "需观察竞价承接与题材持续性。"

    async def _safe_call(self, name: str, *args, **kwargs) -> list[dict[str, Any]]:
        fn = getattr(self._read_gateway, name, None)
        if not callable(fn):
            return []
        try:
            rows = await fn(*args, **kwargs)
            return [self._as_dict(row) for row in list(rows or [])]
        except TypeError:
            return []

    @staticmethod
    def _index_by_subject_stock(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            subject_key = str(row.get("subject_key") or "")
            stock_id = EventDrivenOpportunityBuilder._stock_id(row)
            if subject_key and stock_id:
                result.setdefault((subject_key, stock_id), row)
        return result

    @staticmethod
    def _group_events(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            key = str(event.get("subject_key") or "")
            if key:
                grouped.setdefault(key, []).append(event)
        return grouped

    @staticmethod
    def _as_dict(row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return dict(row)
        return dict(row or {})

    @staticmethod
    def _stock_id(row: dict[str, Any]) -> str:
        return str(row.get("stock_id") or "").strip().upper()

    @staticmethod
    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except Exception:
            return default

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(value if value is not None else default)
        except Exception:
            return default

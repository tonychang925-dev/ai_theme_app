"""P2.1 — AttentionEngine.

Deterministic scoring of theme attention from real market data.
No LLM. Does NOT modify M8 DailyMarketState.

Scoring formula:
  attention_score = event_signals*0.25 + price_signals*0.30
                  + capital_signals*0.25 + external_signals*0.10
                  + sentiment_signals*0.10
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from stock_processing_service.contracts.analyst_attention import (
    ExternalAnchor,
    MarketAttentionState,
    SubjectAttention,
)

DB_DSN = "postgresql://localhost:5432/stock_data_test"

# ── Percentile-based level assignment ──
# Real DB data distributions cluster at 40-60, not 0-100.
# Use relative ranking: top N% get each level.
LEVEL_PERCENTILES = {
    "CRITICAL": 0.10,   # top 10%
    "HIGH": 0.25,       # top 25%
    "MEDIUM": 0.50,     # top 50%
    "LOW": 0.80,        # top 80%
    # remaining = IGNORE
}


def _assign_levels(subjects: list) -> list:
    """Assign levels based on percentile rank with minimum score floors."""
    if not subjects:
        return subjects
    n = len(subjects)
    # Sort by score descending, assign levels by position
    sorted_subjects = sorted(subjects, key=lambda s: -s.attention_score)

    result = []
    for rank_idx, s in enumerate(sorted_subjects):
        pct = rank_idx / n  # 0.0 = top, 1.0 = bottom
        score = s.attention_score

        if pct <= LEVEL_PERCENTILES["CRITICAL"] and score >= 30:
            level = "CRITICAL"
        elif pct <= LEVEL_PERCENTILES["HIGH"] and score >= 25:
            level = "HIGH"
        elif pct <= LEVEL_PERCENTILES["MEDIUM"] and score >= 20:
            level = "MEDIUM"
        elif pct <= LEVEL_PERCENTILES["LOW"] and score >= 10:
            level = "LOW"
        else:
            level = "IGNORE"

        result.append(SubjectAttention(
            subject_id=s.subject_id,
            subject_name=s.subject_name,
            attention_score=s.attention_score,
            level=level,
            ai_level=level,
            event_signals=s.event_signals,
            price_signals=s.price_signals,
            capital_signals=s.capital_signals,
            external_signals=s.external_signals,
            sentiment_signals=s.sentiment_signals,
            reasons=s.reasons,
            evidence_refs=s.evidence_refs,
        ))
    return sorted(result, key=lambda s: -s.attention_score)


class AttentionEngine:
    """Score themes for attention allocation using real DB data.

    Usage:
        engine = AttentionEngine()
        state = engine.run(date(2026, 7, 7))
        print(state.to_dict())
    """

    def run(self, trade_date: date) -> MarketAttentionState:
        return asyncio.run(self._run_async(trade_date))

    async def run_async(self, trade_date: date) -> MarketAttentionState:
        """Async-native entry point for FastAPI handlers."""
        return await self._run_async(trade_date)

    async def _run_async(self, trade_date: date) -> MarketAttentionState:
        import asyncpg

        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            # ── 1. Load theme data ──
            rows = await conn.fetch(
                "SELECT subject_key, theme_name, final_cycle_state, "
                "final_mainline_alive, mainline_strength_score, "
                "fade_watch_score, fade_confirmed_score, "
                "divergence_score, repair_score "
                "FROM theme_cycle_judgement_v2 "
                "WHERE trade_date = $1::date",
                trade_date,
            )

            # ── 2. Load external anchors ──
            anchor_rows = await conn.fetchrow(
                "SELECT payload FROM post_market_recap_snapshot "
                "WHERE trade_date = $1::date ORDER BY created_at DESC LIMIT 1",
                trade_date,
            )
            external_anchors = self._extract_external_anchors(anchor_rows)

            # Build name lookup from both cycle_judgement and recap snapshot
            name_lookup = await self._build_name_lookup(conn, [str(r["subject_key"]) for r in rows])
            recap_name_lookup = await self._build_recap_name_lookup(conn, [str(r["subject_key"]) for r in rows])
            # Recap names take priority (they have real Chinese names)
            name_lookup.update(recap_name_lookup)

            subjects: list[SubjectAttention] = []
            for row in rows:
                subject_key = str(row["subject_key"])
                subject_id = f"theme:{subject_key}"
                theme_name = row["theme_name"] or ""
                if theme_name and len(theme_name) < 50 and not theme_name.startswith("【"):
                    pass  # good name
                else:
                    theme_name = name_lookup.get(subject_key, subject_key)

                # Skip event descriptions that got stored as theme names
                if theme_name.startswith("【") or len(theme_name) > 50:
                    continue
                raw_state = row["final_cycle_state"] or "start"
                is_mainline = row["final_mainline_alive"] or False
                ms_score = float(row["mainline_strength_score"] or 50)
                fw_score = float(row["fade_watch_score"] or 0)
                fc_score = float(row["fade_confirmed_score"] or 0)
                div_score = float(row["divergence_score"] or 0)
                rep_score = float(row["repair_score"] or 0)

                # ── 3. Compute 5 signal dimensions ──
                # event_signals: mainline + repair strength → event traction
                event_signals = self._score_event(ms_score, rep_score)

                # price_signals: mainline strength + (inverse of fade)
                price_signals = self._score_price(ms_score, fw_score, is_mainline)

                # capital_signals: repair score indicates capital return
                capital_signals = min(100, int(rep_score * 1.2 + 10))

                # external_signals: from external anchor mapping
                external_signals = self._score_external(subject_id, theme_name, external_anchors)

                # sentiment_signals: from divergence quality
                sentiment_signals = self._score_sentiment(div_score, fc_score)

                # ── 4. Composite score ──
                attention_score = int(
                    event_signals * 0.25
                    + price_signals * 0.30
                    + capital_signals * 0.25
                    + external_signals * 0.10
                    + sentiment_signals * 0.10
                )
                attention_score = max(0, min(100, attention_score))

                # ── 5. Build reasons ──
                reasons = self._build_reasons(
                    raw_state, is_mainline, ms_score, div_score, rep_score, fw_score
                )

                subjects.append(SubjectAttention(
                    subject_id=subject_id,
                    subject_name=theme_name,
                    attention_score=attention_score,
                    level="MEDIUM",  # placeholder, assigned by _assign_levels
                    ai_level="MEDIUM",
                    event_signals=event_signals,
                    price_signals=price_signals,
                    capital_signals=capital_signals,
                    external_signals=external_signals,
                    sentiment_signals=sentiment_signals,
                    reasons=tuple(reasons),
                    evidence_refs=(f"ev:db:{trade_date.isoformat()}",),
                ))

            # Sort by attention_score descending, then assign percentile-based levels
            subjects.sort(key=lambda s: -s.attention_score)
            subjects = _assign_levels(subjects)

            state = MarketAttentionState(
                trade_date=trade_date,
                generated_at=datetime.now(timezone.utc),
                subjects=subjects,
                external_anchors=external_anchors,
            )

            # Budget allocation
            for s in state.subjects:
                if s.level in ("CRITICAL", "HIGH"):
                    state.allocated_budget += 20
                elif s.level == "MEDIUM":
                    state.allocated_budget += 5

            return state

        finally:
            await conn.close()

    # ── Name lookup ──

    @staticmethod
    async def _build_name_lookup(conn, subject_keys: list[str]) -> dict[str, str]:
        """Find best available name for each subject_key from cycle_judgement table."""
        if not subject_keys:
            return {}
        lookup: dict[str, str] = {}
        rows = await conn.fetch(
            "SELECT DISTINCT ON (subject_key) subject_key, theme_name "
            "FROM theme_cycle_judgement_v2 "
            "WHERE subject_key = ANY($1::text[]) "
            "AND theme_name IS NOT NULL "
            "AND theme_name !~ '^[0-9]+$' "
            "AND length(theme_name) < 50 "
            "AND theme_name NOT LIKE '【%'",
            subject_keys,
        )
        for r in rows:
            lookup[str(r["subject_key"])] = r["theme_name"]
        return lookup

    @staticmethod
    async def _build_recap_name_lookup(conn, subject_keys: list[str]) -> dict[str, str]:
        """Find real Chinese theme names from post_market_recap_snapshot."""
        if not subject_keys:
            return {}
        lookup: dict[str, str] = {}
        try:
            row = await conn.fetchrow(
                "SELECT payload FROM post_market_recap_snapshot "
                "ORDER BY trade_date DESC LIMIT 1"
            )
            if row:
                payload = row["payload"]
                if isinstance(payload, str):
                    import json as _json
                    payload = _json.loads(payload)
                recap = payload.get("recap_doc", payload)
                for t in recap.get("theme_reviews", []):
                    sk = str(t.get("subject_key", ""))
                    name = str(t.get("theme_name", ""))
                    if sk in subject_keys and name and len(name) < 50 and name != sk:
                        lookup[sk] = name
        except Exception:
            pass
        return lookup

    # ── Signal dimension scorers ──

    @staticmethod
    def _score_event(ms_score: float, rep_score: float) -> int:
        """Event stimulus: mainline + repair → event traction."""
        raw = (ms_score * 0.5 + rep_score * 0.5)
        return min(100, int(raw * 1.2))

    @staticmethod
    def _score_price(ms_score: float, fw_score: float, is_mainline: bool) -> int:
        """Price signal: mainline strength is the dominant factor."""
        base = ms_score * 1.0  # scale 0-100 from 0-100 input
        if is_mainline:
            base += 10
        base -= fw_score * 0.2  # fade risk reduces price signal
        return max(5, min(100, int(base)))

    @staticmethod
    def _score_external(
        subject_id: str, theme_name: str, anchors: list[ExternalAnchor]
    ) -> int:
        """External anchor mapping — default baseline for mapped themes."""
        score = 30  # neutral baseline (was 0, too harsh)
        for anchor in anchors:
            if subject_id in anchor.mapped_subjects:
                score = max(score, anchor.strength)
        return max(10, min(100, score))

    @staticmethod
    def _score_sentiment(div_score: float, fc_score: float) -> int:
        """Sentiment: low divergence + low fade = healthy sentiment."""
        base = 50 + (60 - div_score) * 0.3 - fc_score * 0.3
        return max(10, min(90, int(base)))

    @staticmethod
    def _build_reasons(
        state: str, is_mainline: bool, ms: float, div: float, rep: float, fw: float
    ) -> list[str]:
        """Generate up to 3 concise reasons for attention."""
        reasons: list[str] = []

        if is_mainline and ms > 60:
            reasons.append(f"主线题材（强度 {ms:.0f}）")
        elif ms > 50:
            reasons.append(f"关注题材（强度 {ms:.0f}）")

        if rep > div and rep > 50:
            reasons.append("修复信号强于分歧")
        elif div > rep and div > 50:
            reasons.append("分歧压力较大")
        elif fw > 50:
            reasons.append("退潮风险上升")

        state_labels = {
            "start": "处于启动阶段",
            "fermentation": "处于发酵阶段",
            "divergence": "处于分歧阶段",
            "repair": "处于修复阶段",
            "fade_watch": "退潮观察中",
            "fade_confirmed": "退潮确认",
        }
        label = state_labels.get(state)
        if label:
            reasons.append(label)

        return reasons[:3]

    @staticmethod
    def _extract_external_anchors(row: Any) -> list[ExternalAnchor]:
        """Parse external anchors from post_market_recap_snapshot."""
        anchors: list[ExternalAnchor] = []
        if row is None:
            return anchors

        try:
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            recap = payload.get("recap_doc", payload)
            mrr = recap.get("market_regime_review", {})

            # Check for external anchor data in market_regime_review
            external_data = mrr.get("external", mrr.get("external_anchor", {}))
            if isinstance(external_data, dict):
                for key, val in external_data.items():
                    if isinstance(val, dict):
                        anchors.append(ExternalAnchor(
                            anchor_id=key,
                            anchor_name=val.get("name", key),
                            direction=val.get("direction", "neutral"),
                            strength=min(100, int(float(val.get("strength", 50)))),
                            mapped_subjects=tuple(val.get("subjects", [])),
                            note=val.get("note", ""),
                        ))
        except Exception:
            pass

        # Default anchors if none found
        if not anchors:
            anchors = [
                ExternalAnchor("KOSPI", "韩国综合指数", "neutral", 50, (), ""),
                ExternalAnchor("NASDAQ", "纳斯达克", "neutral", 50, (), ""),
            ]

        return anchors

"""MainlineMarketAcceptanceBuilder — Phase 1 PR-3.

Answers: does the market actually buy this logic?

Consumes MainlineDiscoveryFactContext (not report_context).
Outputs: dict[subject_key, MainlineMarketAcceptance].

Hard vetoes (any one = cannot be confirmed_mainline):
  - leader_not_alive
  - fade_risk_high (>= 70)
  - capital_negative
  - leader_breakdown
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import MainlineMarketAcceptance


@dataclass
class MainlineMarketAcceptanceBuilder:
    """Build market acceptance scores from fact context data.

    Six sub-scores composited into market_acceptance_score:
      heat_persistence 15%  — is the theme consistently hot?
      relative_strength 15% — is it among the strongest?
      board_breadth 20%     — is it a board-wide move, not single stock?
      leader_strength 25%   — is there a real leader?
      capital_confirmation 15% — is capital confirming?
      resilience_repair 10%  — can it withstand drawdowns?
    """

    def build(
        self,
        *,
        trade_date: Any,
        candidate_subjects: list[dict[str, Any]],
        event_rows_by_subject: dict[str, list[dict[str, Any]]] | None = None,
        cycle_evidence_by_subject: dict[str, dict[str, Any]] | None = None,
        cycle_judgement_by_subject: dict[str, dict[str, Any]] | None = None,
        capital_by_subject: dict[str, dict[str, Any]] | None = None,
        stock_facts_by_subject: dict[str, list[dict[str, Any]]] | None = None,
        rank_history_by_subject: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, MainlineMarketAcceptance]:
        event_rows = event_rows_by_subject or {}
        cycle_ev = cycle_evidence_by_subject or {}
        cycle_jd = cycle_judgement_by_subject or {}
        capital = capital_by_subject or {}
        stock_facts = stock_facts_by_subject or {}
        rank_hist = rank_history_by_subject or {}

        result: dict[str, MainlineMarketAcceptance] = {}

        for cand in candidate_subjects:
            sk = str(cand.get("subject_key") or "")
            if not sk:
                continue
            theme_name = str(cand.get("theme_name") or sk)

            ev_rows = event_rows.get(sk, [])
            ce = cycle_ev.get(sk, {})
            cj = cycle_jd.get(sk, {})
            cap = capital.get(sk, {})
            sf = stock_facts.get(sk, [])
            rh = rank_hist.get(sk, [])

            # ── sub-scores ──
            heat_persist = self._heat_persistence(ev_rows)
            rel_strength = self._relative_strength(cj, sf, heat_persist)
            board_breadth = self._board_breadth(cj, sf)
            leader_strength, leader_alive = self._leader_strength(ce, cj, sf)
            cap_score, cap_val = self._capital_confirmation(cap)
            resilience = self._resilience_repair(cj, sf)

            # ── composite ──
            parts = [
                (heat_persist, 0.15),
                (rel_strength, 0.15),
                (board_breadth, 0.20),
                (leader_strength, 0.25),
                (cap_score, 0.15),
                (resilience, 0.10),
            ]
            valid_parts = [(s, w) for s, w in parts if s is not None]
            if valid_parts:
                total_weight = sum(w for _, w in valid_parts)
                score = sum(s * w for s, w in valid_parts) / max(total_weight, 0.01)
                score = round(score, 1)
            else:
                score = None

            # ── hard veto flags ──
            veto_flags: list[str] = []
            if not leader_alive:
                veto_flags.append("leader_not_alive")
            fade_risk = _float(cj.get("fade_risk_score") or 0)
            if fade_risk >= 70:
                veto_flags.append("fade_risk_high")
            if cap_val == "negative":
                veto_flags.append("capital_negative")
            leader_bd = _bool(ce.get("leader_breakdown") or cj.get("leader_breakdown"))
            if leader_bd:
                veto_flags.append("leader_breakdown")

            missing: list[str] = []
            if not cycle_ev.get(sk):
                missing.append("cycle_evidence")
            if not cycle_jd.get(sk):
                missing.append("cycle_judgement")
            if not capital.get(sk):
                missing.append("capital")

            market_sources = [
                src for src, data in [
                    ("cycle_evidence", bool(ce)),
                    ("cycle_judgement", bool(cj)),
                    ("capital", bool(cap)),
                    ("stock_facts", bool(sf)),
                    ("rank_history", bool(rh)),
                ] if data
            ]

            result[sk] = MainlineMarketAcceptance(
                market_acceptance_score=score,
                heat_persistence_score=heat_persist,
                relative_strength_score=rel_strength,
                leader_strength_score=leader_strength,
                board_breadth_score=board_breadth,
                capital_confirmation_score=cap_score,
                lifecycle_health_score=resilience,
                resilience_repair_score=resilience,
                leader_alive=leader_alive,
                market_evidence={
                    "ranked_days_5d": _count_event_days(ev_rows, 5),
                    "front_row_count": _front_row_count(sf),
                    "limit_up_count": _limit_up_count(sf),
                    "mainline_strength_score": _float(cj.get("mainline_strength_score")),
                    "fade_risk_score": fade_risk,
                    "capital_validation": cap_val,
                },
                diagnostics={
                    "market_sources": market_sources,
                    "missing_fields": missing,
                    "fallback_used": [],
                    "hard_veto_flags": veto_flags,
                },
            )

        return result

    # ── sub-score methods ──

    @staticmethod
    def _heat_persistence(event_rows: list[dict[str, Any]]) -> float | None:
        if not event_rows:
            return None
        days: set[str] = set()
        for ev in event_rows:
            d = str(ev.get("event_date") or str(ev.get("occurred_at") or "")[:10])
            if d:
                days.add(d)
        n = len(days)
        if n >= 4:
            return 85.0
        if n == 3:
            return 70.0
        if n == 2:
            return 55.0
        if n == 1:
            return 35.0
        return None

    @staticmethod
    def _relative_strength(
        cj: dict[str, Any],
        sf: list[dict[str, Any]],
        fallback: float | None,
    ) -> float | None:
        ms = _float(cj.get("mainline_strength_score"))
        if ms is not None and ms > 0:
            return ms
        if fallback is not None:
            return max(fallback * 0.8, 30)
        return None

    @staticmethod
    def _board_breadth(
        cj: dict[str, Any],
        sf: list[dict[str, Any]],
    ) -> float | None:
        fc = _front_row_count(sf)
        lu = _limit_up_count(sf)
        if fc == 0 and lu == 0:
            return None
        score = min(95.0, fc * 15.0 + lu * 10.0)
        return max(30.0, score)

    @staticmethod
    def _leader_strength(
        ce: dict[str, Any],
        cj: dict[str, Any],
        sf: list[dict[str, Any]],
    ) -> tuple[float | None, bool]:
        """Returns (score, leader_alive)."""
        fc = _front_row_count(sf)
        leader_score = _float(ce.get("leader_alive_score") or cj.get("mainline_strength_score"))
        alive_flag = _bool(ce.get("final_mainline_alive") or cj.get("final_mainline_alive"))

        if not alive_flag and not sf:
            return None, False

        if leader_score is not None and leader_score > 0:
            score = leader_score
        elif fc >= 2:
            score = 75.0
        elif fc == 1:
            score = 55.0
        else:
            return None, bool(sf)

        return score, alive_flag if leader_score is not None else bool(sf)

    @staticmethod
    def _capital_confirmation(cap: dict[str, Any]) -> tuple[float | None, str]:
        if not cap:
            return None, "unknown"
        total = _float(cap.get("main_net_inflow_sum") or cap.get("total_inflow"))
        leader_inflow = _float(cap.get("leader_main_net_inflow") or cap.get("leader_inflow"))

        if total is None:
            return None, "unknown"
        if total > 0 and (leader_inflow or 0) > 0:
            return 80.0, "positive"
        if total < 0 and (leader_inflow or 0) < 0:
            return 25.0, "negative"
        if total > 0 and (leader_inflow or 0) <= 0:
            return 45.0, "divergent"
        return 55.0, "neutral"

    @staticmethod
    def _resilience_repair(
        cj: dict[str, Any],
        sf: list[dict[str, Any]],
    ) -> float | None:
        fade_risk = _float(cj.get("fade_risk_score"))
        repair = _float(cj.get("repair_score"))
        support = _float(cj.get("support_score"))
        if repair is not None:
            return repair
        if fade_risk is not None:
            return max(20.0, 80.0 - fade_risk * 0.8)
        if support is not None:
            return support
        return None


# ── helpers ──

def _float(val: Any) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except Exception:
        return None


def _bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    return str(val or "").strip().lower() in {"1", "true", "yes", "y", "是"}


def _count_event_days(rows: list[dict[str, Any]], window: int) -> int:
    days: set[str] = set()
    for r in rows:
        d = str(r.get("event_date") or str(r.get("occurred_at") or "")[:10])
        if d:
            days.add(d)
    return len(days)


def _front_row_count(sf: list[dict[str, Any]]) -> int:
    """Count stocks with leader_composite_score >= 60 as front row."""
    count = 0
    for s in sf:
        score = _float(s.get("leader_composite_score") or s.get("watch_score") or 0)
        if score and score >= 60:
            count += 1
    return count


def _limit_up_count(sf: list[dict[str, Any]]) -> int:
    """Count limit-up stocks in stock_facts."""
    count = 0
    for s in sf:
        pct = _float(s.get("pct_chg") or 0)
        if pct and pct >= 9.5:
            count += 1
    return count

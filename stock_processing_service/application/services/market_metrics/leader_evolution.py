"""M2.5 Phase 2.3 — Leader Evolution Engine.

Detects high-board leader stocks and tracks their state transitions
day-over-day. Answers the core analyst question:

  "Is yesterday's leader still holding, or is it breaking?"

State machine:
  NEW → CONTINUE → WEAKEN → BREAK
                    ↓
                  REPLACE (if new leader emerges in same theme)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .contracts import (
    LeaderEvolutionMetrics,
    LeaderSnapshot,
    MetricSource,
)


class LeaderEvolutionBuilder:
    """Detect and classify leader stocks from streak + quality data."""

    # Minimum board height to qualify as "leader"
    MIN_LEADER_HEIGHT = 2

    @staticmethod
    def _norm(code: str) -> str:
        return str(code or "").strip().upper().split(".")[0]

    def build(
        self,
        trade_date: date,
        today_limitup: dict[str, dict],       # code → {name, pct_chg, sealed, reason_tags, ...}
        today_streaks: dict[str, int],         # code → board_height
        yesterday_codes: set[str],             # yesterday's limit-up codes
        yesterday_high_boards: set[str],       # yesterday's codes with streak >= 2
    ) -> LeaderEvolutionMetrics:
        """Classify leaders and compute health score."""

        # ── Identify today's leaders ──
        leaders: list[LeaderSnapshot] = []
        for code, height in today_streaks.items():
            if height < self.MIN_LEADER_HEIGHT:
                continue
            info = today_limitup.get(code, {})
            stock_name = info.get("name", code)
            reason_tags = info.get("reason_tags", [])
            theme_hint = reason_tags[0] if reason_tags else ""
            sealed = info.get("sealed", True)
            pct = info.get("pct_chg", 0)
            turnover = info.get("turnover_rate", 0)

            # Determine status
            was_yesterday = code in yesterday_codes
            was_high = code in yesterday_high_boards

            if was_high and sealed:
                status = "CONTINUE"
                reason = f"龙头延续，{height}板封板"
            elif was_high and not sealed:
                status = "WEAKEN"
                reason = f"龙头弱化，{height}板但炸板未封"
            elif was_yesterday and not was_high:
                status = "NEW"
                reason = f"昨日首板，今日{height}板确认为新龙头"
            elif not was_yesterday:
                status = "NEW"
                reason = f"新晋{height}板龙头"
            else:
                status = "CONTINUE"
                reason = f"{height}板龙头"

            # Strength score: seal + height + turnover quality
            height_bonus = min(30, (height - 2) * 10)
            seal_bonus = 30 if sealed else 0
            turnover_bonus = min(20, turnover * 1.5) if 3 < turnover < 20 else 10
            strength = height_bonus + seal_bonus + turnover_bonus + 20  # base 20

            # Risk score: inverse of strength + penalize late/unsealed
            risk = max(5, 100 - strength + (30 if not sealed else 0))

            leaders.append(LeaderSnapshot(
                stock_code=code,
                stock_name=stock_name,
                board_height=height,
                status=status,
                strength_score=round(strength, 1),
                risk_score=round(min(100, risk), 1),
                sealed=sealed,
                theme_hint=theme_hint,
                reason=reason,
            ))

        # ── Count by status ──
        continue_count = sum(1 for l in leaders if l.status == "CONTINUE")
        weaken_count = sum(1 for l in leaders if l.status == "WEAKEN")
        break_count = sum(1 for code in yesterday_high_boards
                         if code not in today_limitup)
        new_count = sum(1 for l in leaders if l.status == "NEW")

        # ── Composite health score ──
        yest_high = len(yesterday_high_boards)
        if yest_high > 0 or leaders:
            total = len(leaders) + break_count
            if total > 0:
                avg_strength = sum(l.strength_score for l in leaders) / max(len(leaders), 1)
                # Penalize breaks heavily
                break_penalty = (break_count / max(yest_high, 1)) * 50
                health = max(0, avg_strength - break_penalty)
            else:
                health = 50  # neutral
        else:
            health = 50

        health = round(health, 1)
        if health >= 70:     health_label = "STRONG"
        elif health >= 45:   health_label = "NORMAL"
        elif health >= 20:   health_label = "WEAK"
        else:                health_label = "COLLAPSE"

        break_alert = yest_high > 0 and (break_count / max(yest_high, 1)) >= 0.3

        return LeaderEvolutionMetrics(
            trade_date=trade_date,
            leaders=tuple(leaders),
            yesterday_leader_count=yest_high,
            continue_count=continue_count,
            weaken_count=weaken_count,
            break_count=break_count,
            new_leader_count=new_count,
            leader_health_score=health,
            leader_health_label=health_label,
            leader_break_alert=break_alert,
            source=MetricSource("db_query", "ths_hot_reason_snapshot", confidence=0.85),
        )

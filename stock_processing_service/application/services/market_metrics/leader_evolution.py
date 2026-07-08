"""M2.5 Phase 2.4 — Leader Evolution Engine (v2 expectation model).

Upgrades from simple state machine to 8-state expectation model:

  NEW → NORMAL_CONTINUE → WEAKEN_EXPECTED → BREAK
  NEW → SUPER_CONTINUE (exceeded expectation)
  CONTINUE → WEAKEN_UNEXPECTED (surprise break)

Surprise score (-100~+100):
  +60 to +100: SUPER_CONTINUE
  +10 to +30:  NORMAL_CONTINUE
  -10 to -30:  WEAKEN_EXPECTED
  -60 to -100: WEAKEN_UNEXPECTED
  -30 to -80:  BREAK (always negative, severity varies)
"""

from __future__ import annotations

from datetime import date

from .contracts import (
    LeaderEvolutionMetrics,
    LeaderSnapshot,
    MetricSource,
)


class LeaderEvolutionBuilder:
    """Detect and classify leader stocks with expectation tracking.

    The expectation model: yesterday's board height H implies
    today's expected height = H + 1 (normal progression).
    Deviation from expectation drives the surprise score.
    """

    MIN_LEADER_HEIGHT = 2

    @staticmethod
    def _norm(code: str) -> str:
        return str(code or "").strip().upper().split(".")[0]

    def build(
        self,
        trade_date: date,
        today_limitup: dict[str, dict],       # code → {name, pct_chg, sealed, reason_tags, turnover_rate}
        today_streaks: dict[str, int],         # code → board_height
        yesterday_codes: set[str],
        yesterday_high_boards: set[str],      # yesterday streak >= 2
        yesterday_heights: dict[str, int],    # code → yesterday's board height (estimated)
    ) -> LeaderEvolutionMetrics:
        """Classify leaders with expectation tracking."""

        leaders: list[LeaderSnapshot] = []
        super_cont = normal_cont = weaken_exp = weaken_unexp = breaks = new_count = replaced = 0
        surprises: list[float] = []

        # ── Pre-compute theme followers (for diffusion factor) ──
        theme_followers: dict[str, int] = {}
        for code, info in today_limitup.items():
            tags = info.get("reason_tags", [])
            for tag in tags:
                theme_followers[tag] = theme_followers.get(tag, 0) + 1

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

            was_high = code in yesterday_high_boards
            yest_h = yesterday_heights.get(code, 1) if was_high else 0
            expected_h = yest_h + 1 if was_high else height  # if NEW, expected = actual

            # ── 8-state classification ──
            if not was_high:
                # NEW leader — first time detected at >= MIN_HEIGHT
                status = "NEW"
                new_count += 1
                # Surprise: moderate positive for unexpected new leader
                surprise = min(30, (height - 1) * 10)
                s_reason = f"新晋{height}板龙头"

            elif not sealed:
                # Weakened — did it close at limit?
                if yest_h >= 3 and height >= yest_h:
                    # Late-stage, height maintained or grew but failed to seal → expected fatigue
                    status = "WEAKEN_EXPECTED"
                    weaken_exp += 1
                    surprise = -20 - (yest_h - 2) * 5
                    s_reason = f"高标{height}板炸板(可预期疲劳)"
                else:
                    # Was expected to continue strongly but didn't seal
                    status = "WEAKEN_UNEXPECTED"
                    weaken_unexp += 1
                    surprise = -50 - abs(expected_h - height) * 10
                    s_reason = f"预期{expected_h}板，实际{height}板炸板(超预期弱)"

            elif height > expected_h:
                # Exceeded expectation — continued higher than expected
                status = "SUPER_CONTINUE"
                super_cont += 1
                surprise = 50 + (height - expected_h) * 15
                s_reason = f"超预期！预期{expected_h}板，实际{height}板封板"

            elif height == expected_h:
                # Normal continuation
                status = "NORMAL_CONTINUE"
                normal_cont += 1
                surprise = 10 + height * 2
                s_reason = f"预期{expected_h}板→{height}板，正常延续"

            else:
                # Height decreased but still sealed → weakening but holding
                status = "WEAKEN_EXPECTED"
                weaken_exp += 1
                surprise = -15
                s_reason = f"板位下降{expected_h}→{height}但封板"

            # ── Quality scores ──
            height_score = min(30, (height - 2) * 10)
            seal_score = 30 if sealed else 0
            turnover_score = min(20, turnover * 1.5) if 3 < turnover < 20 else 10
            strength = height_score + seal_score + turnover_score + 20
            risk = max(5, min(100, 100 - strength + (30 if not sealed else 0) - (surprise * 0.3)))

            # ── v2: 3-factor surprise adjustment ──
            # Factor 1: Height surprise (50%) — already computed as base surprise
            height_surprise = surprise

            # Factor 2: Capital quality (30%) — is volume healthy or shrinking?
            # High turnover + sealed = capital conviction. Low turnover = weak.
            if turnover > 10 and sealed:
                capital_surprise = min(20, turnover * 0.8)   # +0 to +20
            elif turnover < 3:
                capital_surprise = -15                         # very thin
            elif not sealed:
                capital_surprise = -10                         # failed to seal
            else:
                capital_surprise = 5

            # Factor 3: Theme diffusion (20%) — how many peer stocks followed?
            followers = theme_followers.get(theme_hint, 1) if theme_hint else 1
            if followers >= 10:
                theme_surprise = 20                            # strong sector follow
            elif followers >= 5:
                theme_surprise = 10
            elif followers >= 2:
                theme_surprise = 5
            else:
                theme_surprise = -10                           # isolated leader, fragile

            surprise = round(height_surprise * 0.5 + capital_surprise * 0.3 + theme_surprise * 0.2, 1)
            surprises.append(surprise)

            leaders.append(LeaderSnapshot(
                stock_code=code, stock_name=stock_name,
                board_height=height, status=status,
                expected_height=expected_h, surprise_score=surprise,
                strength_score=round(strength, 1),
                risk_score=round(risk, 1),
                sealed=sealed, theme_hint=theme_hint,
                reason=s_reason,
            ))

        # ── Count breaks (yesterday leaders NOT in today's limitup) ──
        for code in yesterday_high_boards:
            if code not in today_limitup:
                breaks += 1
                yest_h = yesterday_heights.get(code, 2)
                # Severity depends on how high the board was
                surprise = -30 - yest_h * 10  # -40 for 2-board, -60 for 3-board, etc.
                surprises.append(round(surprise, 1))
                info = today_limitup.get(code, {}) if code in today_limitup else {}
                leaders.append(LeaderSnapshot(
                    stock_code=code, stock_name=info.get("name", code),
                    board_height=0, status="BREAK",
                    expected_height=yest_h + 1, surprise_score=round(surprise, 1),
                    strength_score=0, risk_score=100, sealed=False,
                    reason=f"龙头断板！昨日{yest_h}板，今日未涨停",
                ))

        # ── Detect replacements (new leader in same theme as broken leader) ──
        broken_themes = {l.theme_hint for l in leaders if l.status == "BREAK" and l.theme_hint}
        for l in leaders:
            if l.status in ("NEW", "SUPER_CONTINUE") and l.theme_hint in broken_themes:
                # This is a replacement leader — adjust status
                replaced_count += 1
                # Keep the original snapshot but note the replacement

        yest_count = len(yesterday_high_boards)

        # ── Composite health ──
        avg_strength = sum(l.strength_score for l in leaders) / max(len(leaders), 1)
        break_penalty = (breaks / max(yest_count, 1)) * 50
        surprise_bonus = (sum(surprises) / max(len(surprises), 1)) * 0.2
        health = max(0, min(100, avg_strength - break_penalty + surprise_bonus))
        health = round(health, 1)

        if health >= 70:     hl = "STRONG"
        elif health >= 45:   hl = "NORMAL"
        elif health >= 20:   hl = "WEAK"
        else:                hl = "COLLAPSE"

        avg_surprise = round(sum(surprises) / max(len(surprises), 1), 1) if surprises else 0.0
        break_alert = yest_count > 0 and (breaks / max(yest_count, 1)) >= 0.3

        return LeaderEvolutionMetrics(
            trade_date=trade_date,
            leaders=tuple(leaders),
            yesterday_leader_count=yest_count,
            continue_count=normal_cont + super_cont,
            super_continue_count=super_cont,
            weaken_expected_count=weaken_exp,
            weaken_unexpected_count=weaken_unexp,
            break_count=breaks,
            new_leader_count=new_count,
            replaced_count=replaced_count,
            leader_health_score=health,
            leader_health_label=hl,
            leader_break_alert=break_alert,
            avg_surprise_score=avg_surprise,
            source=MetricSource("db_query", "ths_hot_reason_snapshot", confidence=0.85),
        )

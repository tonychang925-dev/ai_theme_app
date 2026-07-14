"""PR4.2.36b — Hot Money Style Producer.

Answers: "Where is short-term speculative capital attacking TODAY?"

4-signal model (completely separate from Institution Style):
  S1 Limit-up Expansion (35%): breadth growth + theme penetration + continuation
  S2 Relay Structure (25%): promotion quality + board height + feedback health
  S3 Strong Stock Attack (25%): leader sealed + sub-dragon quality + pool depth
  S4 Dragon Tiger (15%): hot money presence + seat continuity

Modifiers (not signals):
  event_modifier: confidence boost for event-driven themes (×1.00-1.15)
  emotion_modifier: market environment adjustment (×0.85-1.10)

Forbidden: INSTITUTION FORMULA REUSE. This model must never share weights
or logic with InstitutionStyleProducer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

MODEL_VERSION = "hot_money_style_v1"
SOURCE = "hot_money_style_producer"

# ── Signal weights ──
W_LIMITUP = 0.35
W_RELAY = 0.25
W_ATTACK = 0.25
W_DT = 0.15

# ── Emotion modifier ──
EMOTION_MODIFIER: dict[str, float] = {
    "ICE_POINT": 1.10,     # ice point → contrarian opportunity
    "REBOUND": 1.05,       # repair → hot money returns
    "REPAIR": 1.05,
    "CHAOS": 0.95,         # uncertain → slightly defensive
    "DIVERGENCE": 0.90,    # declining → hot money retreats
    "FADE": 0.85,          # fading → hot money exits
    "FERMENTATION": 1.00,  # normal
    "ACCELERATION": 1.00,
    "CLIMAX": 0.85,        # climax → hot money distributes
}

# ── DT missing redistribution ──
DT_MISSING_CONF_PENALTY = 0.90


@dataclass(frozen=True, slots=True)
class HotMoneyStyleOutput:
    trade_date: date
    subject_key: str
    theme_name: str

    hot_money_score: float
    confidence: float

    attack_score: float | None       # S1
    relay_score: float | None        # S2
    intensity_score: float | None    # S3
    dragon_tiger_score: float | None # S4

    attack_stage: str                # FIRST_WAVE | CONTINUING | CLIMAX | RETREATING
    attack_day: int

    # Modifiers
    event_modifier: float
    emotion_modifier: float

    # Relation to institution style
    institution_hot_relation: str    # INSTITUTION_ONLY | HOT_MONEY_ONLY | BOTH | DIVERGENCE

    evidence_quality: dict[str, str]
    evidence: dict[str, Any]
    top_signals: list[str]

    model_version: str = MODEL_VERSION
    source: str = SOURCE

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "hot_money_score": self.hot_money_score,
            "confidence": self.confidence,
            "attack_score": self.attack_score,
            "relay_score": self.relay_score,
            "intensity_score": self.intensity_score,
            "dragon_tiger_score": self.dragon_tiger_score,
            "attack_stage": self.attack_stage,
            "attack_day": self.attack_day,
            "event_modifier": self.event_modifier,
            "emotion_modifier": self.emotion_modifier,
            "institution_hot_relation": self.institution_hot_relation,
            "evidence_quality": self.evidence_quality,
            "evidence": self.evidence,
            "top_signals": list(self.top_signals),
            "model_version": self.model_version,
            "source": self.source,
        }


class HotMoneyStyleProducer:
    """Produce hot_money_style scores from short-term attack evidence.

    Completely separate from InstitutionStyleProducer. Theme-level granularity.
    1-3 day time window. Event + emotion modifiers applied as confidence adjusters.
    """

    def produce(
        self,
        limit_up_data: list[dict[str, Any]],
        strong_stocks: dict[str, list[dict[str, Any]]],
        relay_data: dict[str, Any] | None = None,
        dragon_tiger: dict[str, list[dict[str, Any]]] | None = None,
        events: dict[str, float] | None = None,
        *,
        emotion_node: str = "CHAOS",
        institution_scores: dict[str, float] | None = None,
    ) -> list[HotMoneyStyleOutput]:
        """Produce hot money style scores.

        Args:
            limit_up_data: Hotspot subjects from recap snapshot.
            strong_stocks: {subject_key: [stock rows]} from strong_stock_watch_history.
            relay_data: Optional relay ecology metrics.
            dragon_tiger: {subject_key: [seat rows]} or None.
            events: {subject_key: event_strength} or None.
            emotion_node: Market emotion node for environment modifier.
            institution_scores: {subject_key: institution_score} for relation detection.

        Returns:
            List of HotMoneyStyleOutput, one per theme with attack activity.
        """
        dt = dragon_tiger or {}
        ev = events or {}
        inst = institution_scores or {}

        # Index strong stocks by subject_key
        emotion_mod = EMOTION_MODIFIER.get(emotion_node, 1.0)
        td = _trade_date_from(limit_up_data)

        results: list[HotMoneyStyleOutput] = []

        for hotspot in limit_up_data:
            if not isinstance(hotspot, dict):
                continue
            key = str(hotspot.get("subject_key") or "").strip()
            if not key:
                continue
            name = str(hotspot.get("theme_name") or key)

            # S1: Limit-up expansion
            attack_score, attack_quality, attack_signals, attack_stage, attack_day = _compute_attack_score(hotspot)

            # S2: Relay structure
            relay = relay_data or {}
            relay_score, relay_quality, relay_signals = _compute_relay_score(relay)

            # S3: Strong stock attack
            stocks = strong_stocks.get(key, [])
            intensity_score, intensity_quality, intensity_signals = _compute_intensity_score(stocks)

            # S4: Dragon tiger
            seats = dt.get(key, [])
            dt_score, dt_quality, dt_signals = _compute_hot_dt_score(seats)
            dt_missing = dt_score is None

            # Weights with DT redistribution
            if dt_missing:
                w_l, w_r, w_a, w_d = W_LIMITUP + 0.06, W_RELAY + 0.05, W_ATTACK + 0.04, 0.0
                dt_eff = 0.0
            else:
                w_l, w_r, w_a, w_d = W_LIMITUP, W_RELAY, W_ATTACK, W_DT
                dt_eff = dt_score or 0.0

            base = (
                w_l * (attack_score or 0)
                + w_r * (relay_score or 0)
                + w_a * (intensity_score or 0)
                + w_d * dt_eff
            )

            # Event modifier: confidence boost for event-driven themes (not a 5th signal)
            event_strength = ev.get(key, 0.0)
            event_mod = 1.0
            if event_strength >= 0.8:   event_mod = 1.15
            elif event_strength >= 0.5: event_mod = 1.05

            final_score = round(base * emotion_mod, 2)

            # Confidence
            missing_count = sum(1 for s in [attack_score, relay_score, intensity_score] if s is None)
            conf = 0.80 * (1.0 - 0.05 * missing_count)
            if dt_missing:
                conf *= DT_MISSING_CONF_PENALTY
            conf = round(min(1.0, max(0.0, conf)), 4)

            # Institution relation
            inst_score = inst.get(key)
            relation = "HOT_MONEY_ONLY"
            if inst_score is not None and inst_score > 50:
                relation = "BOTH" if final_score > 40 else "INSTITUTION_ONLY"
            if inst_score is not None and inst_score > 50 and final_score > 50:
                relation = "BOTH"
            if (inst_score is None or inst_score < 30) and final_score > 50:
                relation = "HOT_MONEY_ONLY"
            if inst_score is not None and inst_score > 60 and final_score < 30:
                relation = "INSTITUTION_ONLY"
            if inst_score is not None and inst_score > 50 and final_score > 50 and abs(inst_score - final_score) > 30:
                relation = "DIVERGENCE"

            eq = {"attack": attack_quality, "relay": relay_quality, "intensity": intensity_quality, "dragon_tiger": dt_quality}
            signals = attack_signals + relay_signals + intensity_signals + dt_signals
            ev_dict = {"attack_stage": attack_stage, "attack_day": attack_day, "event_modifier": event_mod, "emotion_modifier": emotion_mod, "emotion_node": emotion_node}

            results.append(HotMoneyStyleOutput(
                trade_date=td, subject_key=key, theme_name=name,
                hot_money_score=final_score, confidence=conf,
                attack_score=round(attack_score, 2) if attack_score is not None else None,
                relay_score=round(relay_score, 2) if relay_score is not None else None,
                intensity_score=round(intensity_score, 2) if intensity_score is not None else None,
                dragon_tiger_score=round(dt_score, 2) if dt_score is not None else None,
                attack_stage=attack_stage, attack_day=attack_day,
                event_modifier=round(event_mod, 3), emotion_modifier=round(emotion_mod, 3),
                institution_hot_relation=relation,
                evidence_quality=eq, evidence=ev_dict, top_signals=signals[:6],
            ))

        return results


# ── S1: Limit-Up Expansion ──

def _compute_attack_score(hotspot: dict[str, Any]) -> tuple[float | None, str, list[str], str, int]:
    cycle = str(hotspot.get("cycle_state") or "").strip()
    score_val = float(hotspot.get("watch_score") or 0)
    entry = str(hotspot.get("pool_entry_type") or "")

    # Score from hotspot metadata
    attack = min(100, max(0, score_val)) if score_val else 50.0

    # Attack stage detection
    stage = "FIRST_WAVE"
    day = 1
    if cycle in ("fermentation", "acceleration"):
        stage = "CONTINUING"
        day = 3
    elif cycle in ("divergence", "fade_watch"):
        stage = "RETREATING"
        day = 5
    elif entry == "formal":
        stage = "CONTINUING"
        day = 2

    quality = "HIGH" if attack >= 70 else "MEDIUM" if attack >= 40 else "LOW"
    signals: list[str] = []
    if attack >= 60:
        signals.append("涨停扩散活跃")
    if stage == "FIRST_WAVE":
        signals.append("首波攻击")
    elif stage == "CONTINUING":
        signals.append("攻击持续中")

    return attack, quality, signals, stage, day


# ── S2: Relay Structure ──

def _compute_relay_score(relay: dict[str, Any]) -> tuple[float | None, str, list[str]]:
    if not relay:
        return 50.0, "LOW", ["连板数据缺失"]

    p1to2 = float(relay.get("promotion_1_to_2") or 0)
    p2to3 = float(relay.get("promotion_2_to_3") or 0)
    max_h = float(relay.get("max_board_height") or 0)
    feedback = float(relay.get("feedback_score") or 0)

    promotion = (p1to2 * 0.5 + p2to3 * 0.3) * 100
    height = min(100, max_h / 10 * 100)
    fb = min(100, max(0, 50 + feedback * 2))

    relay_score = round(promotion * 0.4 + height * 0.4 + fb * 0.2, 2)

    quality = "HIGH" if relay_score >= 70 else "MEDIUM" if relay_score >= 40 else "LOW"
    signals: list[str] = []
    if p1to2 > 0.15:
        signals.append("一进二晋级活跃")
    if max_h >= 5:
        signals.append(f"最高{int(max_h)}板")

    return relay_score, quality, signals


# ── S3: Strong Stock Attack ──

def _compute_intensity_score(stocks: list[dict[str, Any]]) -> tuple[float | None, str, list[str]]:
    if not stocks:
        return 40.0, "LOW", []

    total = len(stocks)
    leaders = [s for s in stocks if str(s.get("relay_role") or s.get("role") or "").strip() in ("龙头", "sub_dragon")]
    positive = [s for s in stocks if (float(s.get("watch_score") or 0)) > 0]

    leader_rate = len(leaders) / max(total, 1)
    positive_rate = len(positive) / max(total, 1)
    intensity = round((leader_rate * 0.40 + positive_rate * 0.30 + min(total / 10, 1.0) * 0.30) * 100, 2)

    quality = "HIGH" if intensity >= 70 else "MEDIUM" if intensity >= 40 else "LOW"
    signals: list[str] = []
    if leaders:
        signals.append(f"龙头{len(leaders)}只活跃")
    if positive_rate > 0.5:
        signals.append("强势股扩散")

    return intensity, quality, signals


# ── S4: Dragon Tiger (Hot Money) ──

def _compute_hot_dt_score(seats: list[dict[str, Any]]) -> tuple[float | None, str, list[str]]:
    if not seats:
        return None, "MISSING", []

    total = len(seats)
    hot_seats = [s for s in seats if str(s.get("seat_type") or "").strip() == "知名游资"]
    hm_rate = len(hot_seats) / max(total, 1)

    dt_score = round(hm_rate * 70 + min(total / 5, 1.0) * 30, 2)
    quality = "HIGH" if dt_score >= 60 else "MEDIUM" if dt_score >= 30 else "LOW"
    signals: list[str] = []
    if hot_seats:
        signals.append(f"知名游资{len(hot_seats)}席位")

    return dt_score, quality, signals


# ── Helpers ──

def _float(value: Any) -> float | None:
    if value in (None, ""): return None
    try: return float(value)
    except (TypeError, ValueError): return None

def _trade_date_from(rows: list[dict[str, Any]]) -> date:
    for r in rows:
        td = r.get("trade_date")
        if td:
            if isinstance(td, date): return td
            text = str(td).strip()
            if len(text) == 8 and text.isdigit():
                return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
            return date.fromisoformat(text[:10])
    return date.today()

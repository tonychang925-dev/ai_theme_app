"""M3.2.7 Strategy Research Compiler — Card → ResearchPlan (deterministic).

Bridge between StrategyCard and CapabilityManager.
Translates: strategy-level required_data → typed CapabilityRequests.
No LLM. Pure structured compilation.

Usage:
  compiler = StrategyResearchCompiler(requirement_registry)
  plan = compiler.compile(card, context)
  # plan.capability_requests can be executed by CapabilityManager
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

CST = timezone(timedelta(hours=8))


# ── Requirement Registry (maps required_data names → capability args) ───────

REQUIREMENT_REGISTRY: dict[str, dict] = {
    "leader_5d_return": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "total_return"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "leader_drawdown_from_peak": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "max_drawdown_from_peak"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "leader_volume_pattern": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "volume_trend"},
        "output": {"type": "categorical", "values": ["contracting", "normal", "elevated", "heavy_selling"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "key_level_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "key_level_status"},
        "output": {"type": "categorical", "values": ["intact", "testing", "broken"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "peer_relative_strength": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "relative_strength_rank"},
        "output": {"type": "list[dict]"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_breadth_change": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "breadth_change"},
        "output": {"type": "categorical", "values": ["contracting", "stable", "expanding"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "capital_persistence": {
        "capability": "market.theme.capital",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "capital_flow_trend"},
        "output": {"type": "categorical", "values": ["outflow", "persistent", "increasing"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "new_leader_candidates": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "emerging_leaders"},
        "output": {"type": "list[str]"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # weak_to_strong requirements
    "auction_strength": {
        "capability": "market.stock.auction",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "auction_trend"},
        "output": {"type": "categorical", "values": ["high_open_scramble", "flat", "weak"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "open_gap": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "open_gap_vs_prev_close"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "intraday_volume": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "intraday_volume_vs_prev"},
        "output": {"type": "categorical", "values": ["amplified", "normal", "contracting"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "limit_up_seal_quality": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "limit_up_seal"},
        "output": {"type": "categorical", "values": ["decisive", "weak", "no_seal"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "peer_follow_through": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "peer_limit_up_ratio"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # Backfill: legacy cards referenced these but they were never registered.
    "market_regime": {
        "capability": "market.regime.read",
        "arguments": {
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "market_regime"},
        "output": {"type": "categorical", "values": ["expansion", "rotation", "contraction", "chaos"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "leader_key_level": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 10,
        },
        "derive": {"metric": "key_level_status"},
        "output": {"type": "categorical", "values": ["intact", "intact_limit_up", "testing", "broken"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_age_days": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "theme_age_days"},
        "output": {"type": "number", "unit": "days"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "leader_board_height": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 10,
        },
        "derive": {"metric": "max_consecutive_limit_up"},
        "output": {"type": "number"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "breadth_trend": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "breadth_trend"},
        "output": {"type": "categorical", "values": ["expanding", "stable", "contracting"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "limit_up_count_trend": {
        "capability": "market.limit_up_count",
        "arguments": {
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "limit_up_count_trend"},
        "output": {"type": "categorical", "values": ["rising", "flat", "falling"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "capital_flow_trend": {
        "capability": "market.theme.capital",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "capital_flow_trend"},
        "output": {"type": "categorical", "values": ["increasing", "persistent", "outflow"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # mainline_identification requirements (L1: trading_system_v1 c01/c02)
    "theme_catalyst_events": {
        "capability": "market.intelligence.observe",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "catalyst_event_list"},
        "output": {"type": "list[dict]"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_logic_attributes": {
        "capability": "market.intelligence.observe",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "novelty_timing_breadth"},
        "output": {"type": "dict"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_capital_acceptance": {
        "capability": "market.theme.capital",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "sustained_inflow"},
        "output": {"type": "categorical", "values": ["accepted", "mixed", "rejected"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_mainline_environment": {
        "capability": "market.mainline_environment",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "mainline_environment"},
        "output": {"type": "categorical", "values": ["healthy", "neutral", "hostile"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # leader_identification requirements (L1: trading_system_v1 c10-c12)
    "board_position": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "sector_position"},
        "output": {"type": "categorical", "values": ["leader", "sub_leader", "follower", "outsider"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "leader_seal_profile": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 10,
        },
        "derive": {"metric": "seal_time_amount_turnover_volume_ratio"},
        "output": {"type": "dict"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_breadth_depth": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "breadth_depth"},
        "output": {"type": "categorical", "values": ["deep_wide", "moderate", "narrow"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "second_board_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 3,
        },
        "derive": {"metric": "consecutive_limit_up_boards"},
        "output": {"type": "number"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # entry_timing requirements (L1: trading_system_v1 c13-c15)
    "intraday_ma_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "intraday_vs_vwap"},
        "output": {"type": "categorical", "values": ["above", "testing", "below"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "intraday_volume_expansion": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "intraday_volume_vs_prev"},
        "output": {"type": "categorical", "values": ["expanding", "flat", "shrinking"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "intraday_platform_break": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "platform_breakout"},
        "output": {"type": "boolean"},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "macd_divergence_state": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "macd_divergence"},
        "output": {"type": "categorical", "values": ["top_divergence", "none", "bottom_divergence"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "premarket_market_checks": {
        "capability": "market.snapshot.read",
        "arguments": {
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "limit_up_count_sector_moves_theme_continuity"},
        "output": {"type": "dict"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # position_sizing requirements (L1: weak_to_strong_v1 c09)
    "support_strength": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 10,
        },
        "derive": {"metric": "support_strength_score"},
        "output": {"type": "number"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "auction_confirm_level": {
        "capability": "market.stock.auction",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "confirm_level"},
        "output": {"type": "categorical", "values": ["A", "B", "C", "X"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "theme_fade_watch": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "fade_watch_flag"},
        "output": {"type": "boolean"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # exit_rules requirements (L1: weak_to_strong_v1 c10)
    "reverse_package_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 3,
        },
        "derive": {"metric": "reverse_package_result"},
        "output": {"type": "categorical", "values": ["success", "failed", "pending"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "ma10_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 10,
        },
        "derive": {"metric": "price_vs_ma10"},
        "output": {"type": "categorical", "values": ["above", "testing", "below"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "previous_low_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 10,
        },
        "derive": {"metric": "price_vs_previous_low"},
        "output": {"type": "categorical", "values": ["above", "testing", "below"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_fade_status": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "theme_fade_state"},
        "output": {"type": "categorical", "values": ["healthy", "fade_watch", "fade_confirmed"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # auction_confirmation requirements (L1: auction_v1 c01-c05)
    "auction_stability": {
        "capability": "market.stock.auction",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "auction_path_volatility_9_20_to_9_25"},
        "output": {"type": "categorical", "values": ["stable", "volatile", "tail_crash"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "auction_last_minute_ratio": {
        "capability": "market.stock.auction",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "last_minute_order_growth_9_24_to_9_25"},
        "output": {"type": "categorical", "values": ["scramble", "flat", "withdraw"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "auction_volume_ratio": {
        "capability": "market.stock.auction",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "auction_volume_vs_prev_intraday_peak"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "sector_sync_strength": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "sector_auction_sync"},
        "output": {"type": "categorical", "values": ["synced_strong", "mixed", "synced_weak"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "peer_premium": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "sub_leader_auction_premium"},
        "output": {"type": "list[dict]"},
        "missing_policy": "DATA_UNAVAILABLE",
    },

    # bull_stock_patterns requirements (L1: find_ox_v1 c01-c05)
    "high_volume_bar_low": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "price_vs_high_volume_bar_low"},
        "output": {"type": "categorical", "values": ["holding_above", "testing", "broken"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "double_volume_base": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "double_volume_low_comparison"},
        "output": {"type": "categorical", "values": ["unbroken", "broken"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "gap_unfilled_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "gap_fill_status"},
        "output": {"type": "categorical", "values": ["gap_held", "gap_touched", "gap_filled", "no_gap"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "ma_bull_alignment": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "ma_alignment"},
        "output": {"type": "categorical", "values": ["bullish", "tangled", "bearish"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "volume_price_rhythm": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "rise_with_volume_fall_with_shrink"},
        "output": {"type": "categorical", "values": ["healthy", "mixed", "unhealthy"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "chip_peak_shape": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "chip_distribution_shape"},
        "output": {"type": "categorical", "values": ["dense_single_peak", "dense_multi_peak", "dispersed", "unavailable"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "price_new_high_streak": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "new_high_frequency"},
        "output": {"type": "number"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "prior_limit_up_gene": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 6,
        },
        "derive": {"metric": "prior_limit_up_count"},
        "output": {"type": "number"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # limit_up_judgment requirements (L1: limit_up_v1 c01-c03)
    "theme_hotness": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "theme_limit_up_wave_intensity"},
        "output": {"type": "categorical", "values": ["limit_up_wave", "warming", "cold"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "volume_vs_ma60": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 60,
        },
        "derive": {"metric": "volume_vs_ma60"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "intraday_limit_up_shape": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "intraday_limit_up_shape"},
        "output": {"type": "categorical", "values": ["impulse", "stepped", "sloped", "oscillating"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "price_position_in_trend": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 20,
        },
        "derive": {"metric": "position_in_trend"},
        "output": {"type": "categorical", "values": ["early", "mid", "late"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "short_term_sentiment": {
        "capability": "market.short_term_sentiment",
        "arguments": {
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "short_term_sentiment_regime"},
        "output": {"type": "categorical", "values": ["ice_point", "recovery", "diffusion", "climax", "fading"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # theme_screening requirements (L1: theme_tracking_v1 c02-c08)
    "theme_mainline_flag": {
        "capability": "market.mainline_environment",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "is_mainline"},
        "output": {"type": "boolean"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_stage_flags": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "stage_flags"},
        "output": {"type": "dict"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_limit_up_count": {
        "capability": "market.limit_up_count",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "theme_limit_up_count"},
        "output": {"type": "number"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "strong_stock_tracking_fields": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "tracking_row_fields"},
        "output": {"type": "list[dict]"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "market_emotion_ice_point": {
        "capability": "market.short_term_sentiment",
        "arguments": {
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "premarket_emotion_ice_point"},
        "output": {"type": "boolean"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
}


# ── Models ──────────────────────────────────────────────────────────────────

@dataclass
class ResearchPlan:
    research_case_id: str = field(default_factory=lambda: f"rc_{uuid4().hex}")
    subject_key: str = ""
    subject_name: str = ""
    trade_date: str = ""
    triggered_card: str = ""
    candidate_hypotheses: list[dict] = field(default_factory=list)
    capability_requests: list[dict] = field(default_factory=list)
    research_questions: list[dict] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(CST).isoformat())


# ── Compiler ────────────────────────────────────────────────────────────────

class StrategyResearchCompiler:
    """Compiles StrategyCard + SubjectContext → executable ResearchPlan.

    Deterministic. Zero LLM. Translates:
      card.required_data → requirement_registry → typed CapabilityRequests
      card.possible_states → candidate_hypotheses (all, untested)
      card.research_questions → included verbatim
    """

    def __init__(self, card_dir: str = ""):
        self.card_dir = Path(card_dir) if card_dir else Path(__file__).resolve().parent / "cards"

    def compile(self, card_id: str, subject: dict) -> ResearchPlan:
        """Compile a ResearchPlan for one subject from one StrategyCard.

        Args:
            card_id: "leader_divergence" | "weak_to_strong" | "theme_lifecycle"
            subject: {
                "subject_key": "9010270",
                "subject_name": "...",
                "trade_date": "2026-07-14",
                "leader_code": "601969",
                "julia_stage": "fading_momentum",
                "workbench_stage": "diffusion"
            }
        """
        card = json.loads((self.card_dir / f"{card_id}.json").read_text(encoding="utf-8"))

        plan = ResearchPlan(
            subject_key=subject["subject_key"],
            subject_name=subject.get("subject_name", ""),
            trade_date=subject.get("trade_date", ""),
            triggered_card=card_id,
        )

        # Step 1: All possible states → untested hypotheses
        for state in card.get("possible_states", []):
            plan.candidate_hypotheses.append({
                "state": f"{card_id}.{state['state']}",
                "canonical_state": state["state"],
                "evidence_pattern": state.get("evidence_pattern", {}),
                "strategy_guidance": {
                    "stance": state.get("action", "observe"),
                    "authority": "advisory_only",
                },
                "status": "untested",
            })

        # Step 2: required_data → CapabilityRequests via registry
        for req_name in card.get("required_data", []):
            spec = REQUIREMENT_REGISTRY.get(req_name)
            if spec is None:
                plan.missing_data.append(req_name)
                continue

            # Resolve template variables (only string templates)
            args = {}
            for k, v in spec.get("arguments", {}).items():
                args[k] = _resolve(str(v), subject) if isinstance(v, str) else v

            plan.capability_requests.append({
                "requirement_id": req_name,
                "capability": spec["capability"],
                "arguments": args,
                "derive": spec.get("derive", {}),
                "output": spec.get("output", {}),
                "missing_policy": spec.get("missing_policy", "INSUFFICIENT_EVIDENCE"),
            })

        # Step 3: Research questions (verbatim from card)
        plan.research_questions = card.get("research_questions", [])

        return plan


def _resolve(template: str, ctx: dict) -> str:
    """Resolve $subject.field references in capability argument templates."""
    result = template
    for k, v in ctx.items():
        result = result.replace(f"$subject.{k}", str(v))
    return result


def compile_for_case001():
    """Test: compile ResearchPlan for the 5 Case001 disagreement subjects."""
    base = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
    universe = json.loads((base / "outcomes/baseline_universe.json").read_text(encoding="utf-8"))

    disagreement_keys = universe["disagreement_keys"]
    compiler = StrategyResearchCompiler()

    print("=" * 70)
    print("M3.2.7 — 9010270 ResearchPlan Compilation (Leader Divergence)")
    print("=" * 70)

    for sk in disagreement_keys[:1]:  # First: just 9010270
        s = universe["subjects"].get(sk, {})
        subject = {
            "subject_key": sk,
            "subject_name": s.get("subject_name", ""),
            "trade_date": "2026-07-14",
            "leader_code": s.get("leader_codes", [""])[0] if s.get("leader_codes") else "",
            "julia_stage": s.get("julia_stage", ""),
            "workbench_stage": s.get("workbench_stage", ""),
        }

        plan = compiler.compile("leader_divergence", subject)

        print(f"\nSubject: {sk} ({subject['subject_name']})")
        print(f"  Leader: {subject['leader_code']}")
        print(f"  Julia: {subject['julia_stage']} | Workbench: {subject['workbench_stage']}")
        print(f"  Triggered Card: {plan.triggered_card}")
        print(f"\n  Candidate Hypotheses ({len(plan.candidate_hypotheses)}):")
        for h in plan.candidate_hypotheses:
            print(f"    [{h['status']:10s}] {h['state']:50s} stance={h['strategy_guidance']['stance']}")

        print(f"\n  Capability Requests ({len(plan.capability_requests)}):")
        for cr in plan.capability_requests:
            print(f"    {cr['requirement_id']:30s} → {cr['capability']}")
            print(f"      args: {cr['arguments']}")

        if plan.missing_data:
            print(f"\n  ⚠️  Missing requirements:{plan.missing_data}")

        print(f"\n  Research Questions ({len(plan.research_questions)}):")
        for rq in plan.research_questions:
            print(f"    Q: {rq['question']}")
            print(f"       probes: {', '.join(rq['probes'])}")

    print(f"\n{'=' * 70}")
    print(f"9010270 ResearchPlan compiled. {len(plan.capability_requests)} capability requests generated.")
    print(f"Next: execute via CapabilityManager → EvidenceBundle → Hypothesis Evaluation")
    print("=" * 70)


if __name__ == "__main__":
    compile_for_case001()

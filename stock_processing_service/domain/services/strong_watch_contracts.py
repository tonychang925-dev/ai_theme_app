from __future__ import annotations

UNIVERSE_REQUIRED_IDENTITY_FIELDS = ("identity_status", "is_main_theme")
UNIVERSE_REQUIRED_CYCLE_FIELDS = ("final_cycle_state", "final_mainline_alive")

ADMISSION_REQUIRED_FIELDS = (
    "prior7_limitup_days",
    "recent_limit_up_count",
    "subject_limit_up_count",
    "subject_strong_count",
    "final_mainline_alive",
    "board_effect_confirmed",
    "two_board_entry",
    "pct_chg",
    "support_type",
    "support_score",
    "is_leader",
    "rank_order",
)

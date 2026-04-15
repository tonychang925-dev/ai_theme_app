#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder, CycleFeatureInputs

def test_shenjian():
    # Create builder (no config needed)
    builder = EnhancedCandidateBuilder()

    # Create row data matching the database row
    row = {
        "stock_code": "002361",
        "stock_id": "002361",
        "stock_name": "神剑股份",
        "subject_key": "9062832",
        "theme_name": "安徽商业航天",
        "rank_order": 12,
        "pct_chg": -3.1100,
        "limit_up": False,
        "is_leader": False,
        "primary_cycle_stage": "fade",
        "action_bias": "放弃",
        "is_divergence": False,
        "is_rebound": False,
        "is_fermentation": False,
        "is_fade": True,
        "is_main_theme": False,
        "recent_limit_up_count": 4,
        "prev_day_pct_chg": -8.9647,
        "prev_day_limit_up": False
    }

    # Cycle features from v2 table
    cycle_features = CycleFeatureInputs(
        subject_key="9062832",
        trade_date=date(2026, 4, 7),
        mainline_alive=False,
        mainline_strength_score=18.0,
        cycle_state="fade_watch",
        fade_watch=True,
        fade_confirmed=False,
        previous_cycle_state=None
    )

    trade_date = date(2026, 4, 7)
    next_day = date(2026, 4, 8)  # placeholder

    # Call _to_enhanced_candidate
    candidate = builder._to_enhanced_candidate(row, trade_date, next_day, cycle_features)

    if candidate is None:
        print("❌ Enhanced candidate rejected")
        # Let's debug parent row transformation
        corrected_row = dict(row)
        corrected_row["is_fade"] = cycle_features.fade_confirmed  # False
        corrected_row["primary_cycle_stage"] = cycle_features.cycle_state  # "fade_watch"
        if cycle_features.cycle_state == "divergence" or cycle_features.cycle_state == "repair":
            corrected_row["action_bias"] = "关注弱转强"
        elif cycle_features.fade_confirmed:
            corrected_row["action_bias"] = "放弃"
        corrected_row["is_divergence"] = cycle_features.cycle_state == "divergence"
        corrected_row["is_rebound"] = cycle_features.cycle_state == "rebound"
        corrected_row["is_fermentation"] = cycle_features.cycle_state == "fermentation"

        parent_row = corrected_row.copy()
        if cycle_features.cycle_state == "fade_watch":
            parent_row["primary_cycle_stage"] = "divergence"
            parent_row["action_bias"] = "关注弱转强"
            parent_row["is_divergence"] = True
            parent_row["is_fade"] = False

        print("\nParent row for parent filtering:")
        for key in ['primary_cycle_stage', 'action_bias', 'is_divergence', 'is_fade', 'recent_limit_up_count', 'rank_order', 'is_leader', 'limit_up']:
            print(f"  {key}: {parent_row.get(key)}")

        # Simulate parent _to_candidate logic
        pct_chg = float(parent_row.get("pct_chg") or 0.0)
        is_leader = bool(parent_row.get("is_leader") or False)
        limit_up = bool(parent_row.get("limit_up") or False)
        rank_order = int(parent_row.get("rank_order") or 999)
        recent_limit_up_count = int(parent_row.get("recent_limit_up_count") or 0)
        stage = str(parent_row.get("primary_cycle_stage") or "").lower()
        action_bias = str(parent_row.get("action_bias") or "")
        is_divergence = bool(parent_row.get("is_divergence") or False)
        is_rebound = bool(parent_row.get("is_rebound") or False)
        is_fermentation = bool(parent_row.get("is_fermentation") or False)
        is_fade = bool(parent_row.get("is_fade") or False)

        strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
        print(f"\nstrong_background: is_leader={is_leader}, limit_up={limit_up}, recent_limit_up_count={recent_limit_up_count}, rank_order={rank_order} => {strong_background}")

        repair_window = (("弱转强" in action_bias) or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"} or is_divergence or is_rebound or is_fermentation)
        if is_fade:
            repair_window = False
        print(f"repair_window: action_bias='{action_bias}', stage='{stage}', is_divergence={is_divergence}, is_rebound={is_rebound}, is_fermentation={is_fermentation}, is_fade={is_fade} => {repair_window}")

        if not strong_background:
            print("❌ strong_background fails")
        if not repair_window:
            print("❌ repair_window fails")

        # Check scoring functions
        strong_bg_score = builder.calculate_strong_background_score(is_leader, limit_up, recent_limit_up_count, rank_order)
        repair_score = builder.calculate_repair_window_score(action_bias, stage, is_divergence, is_rebound, is_fermentation, is_fade, cycle_features.fade_confirmed)
        print(f"\nScoring: strong_bg_score={strong_bg_score}, repair_score={repair_score}")
        print(f"Thresholds: strong_background={builder.STRONG_BACKGROUND_THRESHOLD}, repair_window={builder.REPAIR_WINDOW_THRESHOLD}")

    else:
        print("✅ Enhanced candidate created!")
        print(f"  stock_id: {candidate.get('stock_id')}")
        print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")
        print(f"  candidate_score: {candidate.get('candidate_score')}")
        print(f"  cycle_state: {candidate.get('cycle_state')}")
        print(f"  fade_confirmed: {candidate.get('fade_confirmed')}")

if __name__ == "__main__":
    test_shenjian()
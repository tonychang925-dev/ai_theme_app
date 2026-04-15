#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def main():
    test_date = date(2026, 4, 7)
    builder = EnhancedCandidateBuilder()
    try:
        print(f"Fetching candidate inputs for {test_date}...")
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f"Total rows: {len(rows)}")
        shenjian_row = None
        for row in rows:
            stock_id = row.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                shenjian_row = row
                break
        if shenjian_row is None:
            print("❌ Shenjian not found in candidate inputs")
            # Print first few rows
            for i, row in enumerate(rows[:5]):
                print(f"Row {i}: stock_id={row.get('stock_id')}, rank_order={row.get('rank_order')}, limit_up={row.get('limit_up')}, is_leader={row.get('is_leader')}, subject_key={row.get('subject_key')}")
            return

        print("✅ Shenjian row found:")
        for key, value in shenjian_row.items():
            print(f"  {key}: {value}")

        # Get cycle features
        subject_key = str(shenjian_row.get("subject_key") or "")
        cycle_features = await builder.fetch_cycle_features(test_date, subject_key)
        print("\nCycle features:")
        for key, value in cycle_features.__dict__.items():
            print(f"  {key}: {value}")

        # Build corrected row
        corrected_row = dict(shenjian_row)
        corrected_row["is_fade"] = cycle_features.fade_confirmed
        corrected_row["primary_cycle_stage"] = cycle_features.cycle_state
        if cycle_features.cycle_state == "divergence" or cycle_features.cycle_state == "repair":
            corrected_row["action_bias"] = "关注弱转强"
        elif cycle_features.fade_confirmed:
            corrected_row["action_bias"] = "放弃"
        corrected_row["is_divergence"] = cycle_features.cycle_state == "divergence"
        corrected_row["is_rebound"] = cycle_features.cycle_state == "rebound"
        corrected_row["is_fermentation"] = cycle_features.cycle_state == "fermentation"
        print("\nCorrected row:")
        for key in ['primary_cycle_stage', 'action_bias', 'is_divergence', 'is_rebound', 'is_fermentation', 'is_fade']:
            print(f"  {key}: {corrected_row.get(key)}")

        # Parent row transformation
        parent_row = corrected_row.copy()
        if cycle_features.cycle_state == "fade_watch":
            parent_row["primary_cycle_stage"] = "divergence"
            parent_row["action_bias"] = "关注弱转强"
            parent_row["is_divergence"] = True
            parent_row["is_fade"] = False
        print("\nParent row (for parent filtering):")
        for key in ['primary_cycle_stage', 'action_bias', 'is_divergence', 'is_fade']:
            print(f"  {key}: {parent_row.get(key)}")

        # Call parent _to_candidate
        next_day = await builder.resolve_next_trade_date(test_date)
        parent_candidate = builder._to_candidate(parent_row, test_date, next_day)
        print(f"\nParent _to_candidate result: {parent_candidate}")
        if parent_candidate is None:
            print("Parent rejected. Checking conditions...")
            # Manual condition check
            pct_chg = float(parent_row.get("pct_chg") or 0.0)
            is_leader = bool(parent_row.get("is_leader") or False)
            limit_up = bool(parent_row.get("limit_up") or False)
            rank_order = int(parent_row.get("rank_order") or 999)
            recent_limit_up_count = int(parent_row.get("recent_limit_up_count") or 0)
            prev_day_pct = float(parent_row.get("prev_day_pct_chg") or 0.0)
            prev_day_limit_up = bool(parent_row.get("prev_day_limit_up") or False)
            stage = str(parent_row.get("primary_cycle_stage") or "").lower()
            action_bias = str(parent_row.get("action_bias") or "")
            is_divergence = bool(parent_row.get("is_divergence") or False)
            is_rebound = bool(parent_row.get("is_rebound") or False)
            is_fermentation = bool(parent_row.get("is_fermentation") or False)
            is_fade = bool(parent_row.get("is_fade") or False)

            strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
            print(f"strong_background: is_leader={is_leader}, limit_up={limit_up}, recent_limit_up_count={recent_limit_up_count}, rank_order={rank_order} => {strong_background}")

            repair_window = (("弱转强" in action_bias) or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"} or is_divergence or is_rebound or is_fermentation)
            if is_fade:
                repair_window = False
            print(f"repair_window: action_bias='{action_bias}', stage='{stage}', is_divergence={is_divergence}, is_rebound={is_rebound}, is_fermentation={is_fermentation}, is_fade={is_fade} => {repair_window}")

            if not strong_background:
                print("❌ strong_background fails")
            if not repair_window:
                print("❌ repair_window fails")
            if strong_background and repair_window:
                print("✅ Both conditions pass, parent should have passed.")
                # Check weak type classification
                if prev_day_limit_up and pct_chg < 0:
                    weak_type = "bad_limit_up"
                elif pct_chg <= -5.0:
                    weak_type = "big_negative_line"
                elif -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
                    weak_type = "upper_shadow"
                elif pct_chg <= -1.0:
                    weak_type = "high_open_low_close"
                else:
                    weak_type = "fake_break"
                print(f"weak_type classification: {weak_type}")

                # candidate type
                if is_leader and recent_limit_up_count >= 3:
                    candidate_type = "dragon_repair"
                elif is_leader or rank_order <= 3:
                    candidate_type = "subdragon_repair"
                elif weak_type == "bad_limit_up":
                    candidate_type = "bad_limit_repair"
                elif weak_type == "upper_shadow":
                    candidate_type = "upper_shadow_repair"
                elif recent_limit_up_count >= 1:
                    candidate_type = "strong_trend_repair"
                else:
                    candidate_type = "generic_repair"
                print(f"candidate_type: {candidate_type}")

        # Now try enhanced candidate
        enhanced_candidate = builder._to_enhanced_candidate(shenjian_row, test_date, next_day, cycle_features)
        print(f"\nEnhanced candidate result: {enhanced_candidate}")
        if enhanced_candidate is None:
            print("❌ Enhanced candidate rejected.")
        else:
            print("✅ Enhanced candidate created!")
            print(f"  stock_id: {enhanced_candidate.get('stock_id')}")
            print(f"  pool_entry_type: {enhanced_candidate.get('pool_entry_type')}")
            print(f"  candidate_score: {enhanced_candidate.get('candidate_score')}")

    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())
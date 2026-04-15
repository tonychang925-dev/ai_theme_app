#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

class DebugBuilder(EnhancedCandidateBuilder):
    async def debug_shenjian(self, trade_date):
        rows = await self._fetch_candidate_inputs(trade_date)
        for row in rows:
            stock_id = row.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                print("Found Shenjian row")
                # get cycle features
                subject_key = str(row.get("subject_key") or "")
                cycle_features = await self.fetch_cycle_features(trade_date, subject_key)
                print(f"cycle_features: {cycle_features}")
                # build corrected row
                corrected_row = dict(row)
                corrected_row["is_fade"] = cycle_features.fade_confirmed
                corrected_row["primary_cycle_stage"] = cycle_features.cycle_state
                if cycle_features.cycle_state == "divergence" or cycle_features.cycle_state == "repair":
                    corrected_row["action_bias"] = "关注弱转强"
                elif cycle_features.fade_confirmed:
                    corrected_row["action_bias"] = "放弃"
                corrected_row["is_divergence"] = cycle_features.cycle_state == "divergence"
                corrected_row["is_rebound"] = cycle_features.cycle_state == "rebound"
                corrected_row["is_fermentation"] = cycle_features.cycle_state == "fermentation"
                print("corrected_row:", corrected_row)
                # parent row
                parent_row = corrected_row.copy()
                if cycle_features.cycle_state == "fade_watch":
                    parent_row["primary_cycle_stage"] = "divergence"
                    parent_row["action_bias"] = "关注弱转强"
                    parent_row["is_divergence"] = True
                    parent_row["is_fade"] = False
                print("parent_row:", parent_row)
                # call parent _to_candidate
                next_day = await self.resolve_next_trade_date(trade_date)
                parent_candidate = super()._to_candidate(parent_row, trade_date, next_day)
                print(f"parent_candidate result: {parent_candidate}")
                if parent_candidate is None:
                    print("Parent rejected. Let's examine conditions.")
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

                    print("strong_background:", is_leader, limit_up, recent_limit_up_count, rank_order)
                    strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
                    print("strong_background result:", strong_background)
                    if not strong_background:
                        print("FAIL strong_background")

                    repair_window = (("弱转强" in action_bias) or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"} or is_divergence or is_rebound or is_fermentation)
                    if is_fade:
                        repair_window = False
                    print("repair_window conditions:", action_bias, stage, is_divergence, is_rebound, is_fermentation, is_fade)
                    print("repair_window result:", repair_window)
                    if not repair_window:
                        print("FAIL repair_window")
                break
        else:
            print("Shenjian not found in rows")

async def main():
    test_date = date(2026, 4, 7)
    builder = DebugBuilder()
    try:
        await builder.debug_shenjian(test_date)
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
import sys
from datetime import date

# Simulate row data from SQL query
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

# Simulate cycle features from theme_cycle_judgement_v2
class CycleFeatureInputs:
    def __init__(self, subject_key, trade_date, mainline_alive, mainline_strength_score, cycle_state, fade_watch, fade_confirmed, previous_cycle_state=None):
        self.subject_key = subject_key
        self.trade_date = trade_date
        self.mainline_alive = mainline_alive
        self.mainline_strength_score = mainline_strength_score
        self.cycle_state = cycle_state
        self.fade_watch = fade_watch
        self.fade_confirmed = fade_confirmed
        self.previous_cycle_state = previous_cycle_state

cycle_features = CycleFeatureInputs(
    subject_key="9062832",
    trade_date=date(2026, 4, 7),
    mainline_alive=False,
    mainline_strength_score=0.0,  # unknown
    cycle_state="fade_watch",
    fade_watch=True,
    fade_confirmed=False
)

print("原始row:", row)
print("cycle_features:", cycle_features.__dict__)

# Build corrected_row as in enhanced builder
corrected_row = dict(row)
corrected_row["is_fade"] = cycle_features.fade_confirmed  # False
corrected_row["primary_cycle_stage"] = cycle_features.cycle_state  # "fade_watch"
if cycle_features.cycle_state == "divergence" or cycle_features.cycle_state == "repair":
    corrected_row["action_bias"] = "关注弱转强"
elif cycle_features.fade_confirmed:
    corrected_row["action_bias"] = "放弃"
# else keep original
corrected_row["is_divergence"] = cycle_features.cycle_state == "divergence"
corrected_row["is_rebound"] = cycle_features.cycle_state == "rebound"
corrected_row["is_fermentation"] = cycle_features.cycle_state == "fermentation"
print("corrected_row:", corrected_row)

# Build parent_row
parent_row = corrected_row.copy()
if cycle_features.cycle_state == "fade_watch":
    parent_row["primary_cycle_stage"] = "divergence"
    parent_row["action_bias"] = "关注弱转强"
    parent_row["is_divergence"] = True
    parent_row["is_fade"] = False
print("parent_row:", parent_row)

# Simulate parent _to_candidate logic
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

print("\n--- 强背景条件 ---")
strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
print(f"is_leader={is_leader}, limit_up={limit_up}, recent_limit_up_count={recent_limit_up_count}, rank_order={rank_order}")
print(f"strong_background={strong_background}")

print("\n--- 修复窗口条件 ---")
repair_window = (("弱转强" in action_bias) or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"} or is_divergence or is_rebound or is_fermentation)
if is_fade:
    repair_window = False
print(f"action_bias='{action_bias}', stage='{stage}', is_divergence={is_divergence}, is_rebound={is_rebound}, is_fermentation={is_fermentation}, is_fade={is_fade}")
print(f"repair_window={repair_window}")

if not strong_background:
    print("❌ 强背景条件失败")
if not repair_window:
    print("❌ 修复窗口条件失败")

if strong_background and repair_window:
    print("✅ 通过父类基础过滤")
    # weak type classification
    if prev_day_limit_up and pct_chg < 0:
        weak_type = "bad_limit_up"
        weak_intensity = min(100.0, abs(pct_chg) * 12.0 + 20.0)
    elif pct_chg <= -5.0:
        weak_type = "big_negative_line"
        weak_intensity = min(100.0, abs(pct_chg) * 10.0)
    elif -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
        weak_type = "upper_shadow"
        weak_intensity = 55.0
    elif pct_chg <= -1.0:
        weak_type = "high_open_low_close"
        weak_intensity = min(100.0, abs(pct_chg) * 8.0 + 10.0)
    else:
        weak_type = "fake_break"
        weak_intensity = 40.0
    print(f"weak_type={weak_type}, weak_intensity={weak_intensity}")

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
    print(f"candidate_type={candidate_type}")

    print("✅ 应生成候选")
else:
    print("❌ 被过滤")
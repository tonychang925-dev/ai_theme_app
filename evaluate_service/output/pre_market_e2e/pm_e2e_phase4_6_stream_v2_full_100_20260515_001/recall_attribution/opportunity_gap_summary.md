# Phase 4.6 Opportunity Gap Report

**Run**: `2026-05-15`

## Overview

- **total_themes**: 25
- **total_opportunities**: 25
- **opportunity_generation_rate**: 25/25 = 100%

## Drop Reason Distribution

| Drop Reason | Count | Subjects |
|---|---|---|
| all_C_level_low_quality | 23 | AR眼镜, 深海经济, 可控核聚变, 液冷数据中心, SpaceX +18 more |
| ok | 2 | 半导体设备, 卫星互联网 |

## Stock Quality Distribution

| Level | Count | % |
|---|---|---|
| A (strong) | 2 | 1.6% |
| B (decent) | 4 | 3.2% |
| C (weak) | 119 | 95.2% |
| **Total** | **125** | |

## Top Themes by Avg Stock Score

| Subject Key | Subject Name | Avg Score | A | B | C | Stocks |
|---|---|---|---|---|---|---|
| 9011398 | 半导体设备 | 63.6 | 1 | 2 | 2 | 5 |
| 9019807 | 卫星互联网 | 63.2 | 1 | 2 | 2 | 5 |
| 9010367 | 稀土永磁 | 46.8 | 0 | 0 | 5 | 5 |
| 9034859 | AI智能体 | 46.8 | 0 | 0 | 5 | 5 |
| 9024880 | 液冷数据中心 | 46.7 | 0 | 0 | 5 | 5 |
| 9064166 | SpaceX | 46.7 | 0 | 0 | 5 | 5 |
| 9059919 | 对日制裁 | 46.7 | 0 | 0 | 5 | 5 |
| 9018411 | 光刻胶 | 46.4 | 0 | 0 | 5 | 5 |
| 9062142 | 蓝箭航天IPO | 45.6 | 0 | 0 | 5 | 5 |
| 9018144 | PCB印制电路板 | 45.6 | 0 | 0 | 5 | 5 |

## Root Cause Analysis

### Gap 1: Recall misses reduce theme count

The current E2E100 has 25 themes in the brief but only 57% primary hit rate.
With recall@5 at 0.60 target, we'd expect ~60 themes if wrong matches are fixed.
Current 25 themes include ~15 wrong-match themes (著名IP, 乌克兰重建, etc.) that 
don't represent real investment themes. After fixing recall, the valid theme count 
should increase to ~30-35 which would naturally boost opportunity count.

### Gap 2: Stock pool quality is uniformly low

Of 125 total stock recommendations:
- Only 2 are A-level (strong, with leaderboard/strong_pool support)
- 4 are B-level (moderate)
- 119 (95%) are C-level (weak, no pool support)

This suggests the `theme_stock_map` and `subject_stock_pool` tables have broad but 
shallow coverage — many subjects have stock entries, but few have leaderboard or 
strong_watch_pool support to elevate them to A/B level.

### Gap 3: 7 unnamed themes


## Recommendations

1. **Fix recall first**: The primary driver of low opportunity count is recall miss.
   Fixing even 5-8 high-frequency recall miss themes would add 10-15 opportunities.

2. **Improve stock pool quality**: For the top 10 themes by avg_confidence, verify
   that `subject_stock_pool` has recent entries and leaderboard data is available.
   Missing leaderboard data is the main reason for all-C-level recommendations.

3. **Filter out noise themes**: Themes like '著名IP', 'A股全球第一', '首发经济大全'
   should not generate stock opportunities. The builder should skip subjects where
   avg_confidence < 0.70 or subject is a broad category.

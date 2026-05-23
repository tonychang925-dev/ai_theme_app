# Product Runtime Repair Phase 3B Review Eligibility Summary

## 背景

5/25 盘前必读待复核事件一度升到 99 条以上。Phase 3A 已经把明确低价值硬噪声从 `major_events`、`review_queue` 和快照展示中移除，但 `HUMAN_REVIEW` 仍被当作弱匹配兜底：弱 v1 fallback、generic-only evidence、普通披露、普通监管和普通公告仍会进入产品待复核。

本阶段目标不是继续扩词表或盲修 gate，而是收紧复核入口：

- `HUMAN_REVIEW` 只保留高价值但题材不确定的事件。
- 中低价值、重复、普通披露和弱证据事件直接 `DROPPED/ARCHIVED`。
- 产品页不再展示低价值复核项。

## 修复设计

新增统一复核资格门：

- `database_service/streams/services/review_eligibility.py`
- 核心函数：`should_enter_human_review(event, match_result, triage_result)`

允许进入复核的条件：

- `importance_level in S/A/B`
- `event_value_type` 属于 `theme_catalyst`、`company_catalyst`、`macro_policy`、`sector_supply_demand`、`major_risk_alert`
- 有明确强催化证据，但题材不确定
- 可能是新题材

禁止进入复核的类型：

- 普通披露、普通监管、普通财报、普通 IPO
- 澄清、风险提示、交易异动、天气灾害、交通停运
- duplicate、market_noise、low_value_disclosure
- weak v1 fallback、generic-only evidence、低置信弱证据

接入位置：

- `ThemeProcessor`：`HUMAN_REVIEW` 发布前执行资格门，不合格转 `DROPPED`。
- `DecisionExecutor`：写入 `event_review_queue` 前再次兜底。
- `EventReviewWriter`：不再按“有题材/有置信度”无条件入队。
- `PreMarketBriefBuilder`：只展示 `should_keep_review=true` 的事件，默认最多 20 条；不合格复核只进入 diagnostics。

## 处理数据

5/25 当前快照中的 review 事件重新审计：

- 审计 review 事件：102 条
- 符合高价值复核资格：0 条
- 归档/丢弃：102 条
- 主要归因：`weak_evidence_review_dropped`

对 `event_review_queue` 中对应记录执行 dropped 标记：

- dropped rows：102
- backup 表：`event_review_queue_phase3b_backup`

随后重建 2026-05-25 盘前必读快照。

## 回归指标

- 单测：`82 passed`
- full hard negative active v2：`64/64`
- `v2_hard_negative_reject_rate = 1.0`
- new-chain health：
  - `web_app_service:8000` healthy
  - `stock_processing_service:8090` healthy

## 当前 Baseline

2026-05-25 快照重建后：

- `review_events = 0`
- `major_events = 11`
- `event_count = 11`
- `review_event_count = 0`
- `review_ineligible_dropped_count = 17`
- `high_value_review_count = 0`
- `low_value_major = 0`
- `duplicate_primary = 0`

该状态作为 Phase 3B baseline。当前阶段不继续扩低价值词表、不继续盲修 gate。

## Phase 3C 触发条件

进入观察窗口，只有真实新增数据触发以下任一条件时才进入 Phase 3C：

- `review_events_count > 20`
- `low_value_major_count > 0`
- `duplicate_primary_count > 0`
- `hard_negative_violation_count > 0`
- 某个题材吸入明显无关事件 `>= 2`
- 高价值事件被错误 dropped
- 页面出现明显错配


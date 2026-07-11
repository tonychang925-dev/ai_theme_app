# DailyReview Projection Diff - 2026-07-09

## 1. 基本信息

- Phase: `Phase 4.5.6`
- PR: `PR3 Projection Diff`
- 测试数据日期: `2026-07-09`
- 测试类型: Golden semantic diff
- 基线文件: `stock_processing_service/tests/unit/test_projection_diff_20260709.py`

## 2. 测试目标

验证 `FormalReviewProjectionCompiler` 将旧 `DailyReviewV2` 多字段结构压缩为 `formal_review` 六章模型时：

- FACT 不丢失、不被分析师覆盖。
- Theme / Stock 实体不丢失。
- AI/Analyst 冲突时使用分析师 `final_value`。
- 明日计划只消费分析师确认后的 watch universe。
- `workbench_data / confirmed_mainlines / pending_mainline_reviews` 不回流。

## 3. 结构对比

| 指标 | Old DailyReviewV2 | FormalReviewProjection |
|---|---:|---:|
| 顶级对象 | 63+ legacy fields | 4 projection objects |
| 正式业务章节 | 分散在多个字段 | 6 chapters |
| 主题来源 | 多字段分散 | `theme_structure.themes[]` |
| 股票来源 | 多列表分散 | `stock_structure.stocks[]` / `capital_evidence.stocks[]` |
| 明日计划 | `playbook/watchlist/tomorrow_*` 分散 | `next_day_plan` |

Formal Review 六章：

1. `executive_summary`
2. `market_state`
3. `theme_structure`
4. `stock_structure`
5. `capital_evidence`
6. `next_day_plan`

## 4. Diff 结果

| 分类 | 检查 | 结果 |
|---|---|---|
| FACT | `up_count/down_count/limit_up_total/limit_down_total/total_amount` 与 owner source 一致 | PASS |
| ENTITY | `theme_reviews.subject_key` 集合被 `theme_structure.themes[]` 覆盖 | PASS |
| ENTITY | `strong_stock_reviews.stock_code` 集合与 `stock_structure.stocks[]` 一致 | PASS |
| ASSESSMENT | AI=机器人，Analyst=PCB，最终 `stage_judgement.final_value=PCB成为资金承接方向` | PASS |
| CAPITAL | `main_net_inflow` 位于 `capital.fact`，`money_flow_tier` 位于 `capital.assessment` | PASS |
| PLAN | Analyst watch override 后，`watch_themes/watch_stocks` 只保留 PCB，不保留 AI/legacy 机器人 | PASS |
| SCHEMA | 六章模型固定，legacy removed fields 不回流 | PASS |

## 5. 关键业务样本

```json
{
  "ai_value": "人形机器人延续主线",
  "analyst_value": "PCB成为资金承接方向",
  "final_value": "PCB成为资金承接方向",
  "reason": "机器人高位分歧，资金切换PCB"
}
```

明日计划校验：

```json
{
  "watch_themes": ["pcb"],
  "watch_stocks": ["002384.SZ"]
}
```

AI/legacy 机器人 watch 仅保留在 `next_day_plan.playbook.watch_themes` 的 audit 数据中，不进入正式 `watch_themes[]`。

## 6. 验证命令

```bash
/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest \
  stock_processing_service/tests/unit/test_projection_formal_schema.py \
  stock_processing_service/tests/unit/test_projection_diff_20260709.py \
  stock_processing_service/tests/unit/test_projection_capital_plan.py \
  stock_processing_service/tests/unit/test_projection_theme_stock_merge.py -q
```

结果：

```text
12 passed
```

## 7. 结论

PR3 Projection Diff 通过。

`FormalReviewProjectionCompiler` 已证明可以在降低输出复杂度的同时保留核心市场认知价值：

- FACT 稳定；
- ENTITY 不丢；
- ASSESSMENT 尊重分析师校准；
- PLAN 消费最终确认结果；
- legacy 字段不会进入正式 projection。

下一步进入 PR4：`FormalReviewView` 双轨前端展示。

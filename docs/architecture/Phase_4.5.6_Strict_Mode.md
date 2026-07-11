# Phase 4.5.6 Strict Mode

> 版本：v1.0
> 日期：2026-07-11
> 状态：In Progress
> 分支：codex/bugfix/workbench-intelligence-binding

## 0. 原则

旧系统在迁移期可以通过 fallback 存活，但在迁移完成后必须切断。**只要旧链路还能跑，就无法验证新链路是否真正覆盖全部场景。**

```
正式模式唯一数据源：
  Approved Snapshot
      ↓
  FormalReviewProjectionCompiler
      ↓
  daily-review-v2 (formal_review only)
      ↓
  Frontend (no raw JSON, no legacy fields)
```

## 1. 禁止项

| 禁止 | 原因 |
|---|---|
| `_enrich_v2_with_workbench_sections()` 在 formal_review 存在时注入 legacy 字段 | 消费者无法判断真源 |
| `fetch(/api/emotion-{date}.json)` | 绕过 Approved Snapshot |
| `fetch(/api/analyst-charts/{date}.json)` | 绕过 Approved Snapshot |
| `recap_doc` 作为 GET daily-review-v2 的 fallback | 旧 DB read model |
| `compatibility` 字段在正式模式出现 | 污染 API schema |

## 2. 实施步骤

### PR-S1: API Strict Gate ✅/⏳

- [x] Workspace API 返回 `emotion_review` + `chart_reviews` from draft/snapshot
- [x] `_enrich_v2_with_formal_review()` 在 GET 端点注入 formal_review
- [ ] `_enrich_v2_with_workbench_sections()` 仅在没有 formal_review 时运行
- [ ] GET daily-review-v2：formal_review 存在时不再返回 `emotion_review` 等 legacy 顶级字段

### PR-S2: Frontend Strict Mode ✅/⏳

- [x] EmotionDashboard 删除 raw JSON fallback
- [x] EmotionDashboard 只从 props (workspace API) 获取数据
- [ ] RecapPage：`formal_review` 存在时不渲染 EnginePostMarketView（已完成）
- [ ] ChartRenderer 不直接 fetch analyst-charts JSON
- [ ] 删除 `fetchDailyReview` 死代码

### PR-S3: Legacy Field Removal

- [ ] 删除 `emotion_review` 顶级字段（已被 formal_review.market_state.emotion 替代）
- [ ] 删除 `market_chart_reviews` 顶级字段（已被 formal_review.evidence_appendix.chart_details 替代）
- [ ] 删除 `attention_review` 顶级字段
- [ ] 删除 `narrative_review` 顶级字段
- [ ] 删除 `playbook_review` 顶级字段
- [ ] 删除 `analyst_override_review` 顶级字段
- [ ] 删除 `cognition_reviews` 顶级字段

## 3. API Contract (v3)

```
GET /api/v2/daily-review-v2?date=2026-07-09

200:
{
  "metadata": {},
  "formal_review": {
    "version": "1.0",
    "executive_summary": {},
    "market_state": {},
    "theme_structure": {},
    "stock_structure": {},
    "capital_evidence": {},
    "next_day_plan": {}
  },
  "evidence_appendix": {},
  "diagnostics": {}
}

断言：
- "emotion_review" NOT in response
- "legacy_sections" NOT in response
- "workbench_data" NOT in response (PR1a)
- "confirmed_mainlines" NOT in response (PR1a)
```

## 4. 验证

- [ ] GET daily-review-v2 不包含 `emotion_review` 顶级字段
- [ ] GET daily-review-v2 不包含 `market_chart_reviews` 顶级字段
- [ ] Browser Network 无 `/api/emotion-{date}.json` 请求
- [ ] Browser Network 无 `/api/analyst-charts/{date}.json` 请求
- [ ] 后端回归测试全部通过
- [ ] 前端 build 通过
- [ ] npm run build 通过

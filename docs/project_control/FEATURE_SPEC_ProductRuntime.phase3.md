# Product Runtime Phase 3 Feature Spec

## Task `ProductRuntime.phase3-T01` - Pre-Structuring Importance Triage

### 1) 目标与边界
- 目标: 在 `NewsStreamProcessor` 调用 structuring LLM 前拦截低价值披露、灾害噪声和重复候选，减少无效结构化与后续题材错配。
- 非目标: 本阶段不继续批量修 gate，不把 triage 结果直接写成题材映射，不改 ThemeMatchEngine 的匹配真源。

### 2) 接口与契约
- 输入: `news_data.title/content/source/news_id`。
- 输出: importance triage JSON，包含 `decision`, `importance_level`, `event_value_type`, routing flags, `reason_code`, `confidence`, `evidence`, `dedupe_key`。
- 决策: `PASS` 进入 structuring；`REVIEW/SKIP/DUPLICATE` 只持久化 triage audit，不发布 structured stream。

### 3) 数据模型与状态变更
- `news_event.theme_directive.triage_result` 保存 triage 审计。
- `business_stats` 增加 PASS/REVIEW/SKIP/DUPLICATE、structuring saved、低价值和重复统计。
- 不新增数据库迁移。

### 子功能分解
- `F-ProductRuntime.phase3-T01-01` 低价值规则预筛
  - 输入: 原始新闻文本。
  - 处理: 在本地 Qwen 前识别监管、澄清、灾害、普通财报、回购减持；强催化例外 PASS。
  - 输出: `SKIP` 或 `PASS` importance JSON。
  - 失败处理: 退回既有 rule decision。
  - 可观测证据: `reason_code`, `evidence`, Phase 3 JSONL regression。
- `F-ProductRuntime.phase3-T01-02` Prompt/schema 升级
  - 输入: 灰区新闻。
  - 处理: 本地 Qwen 输出严格 JSON schema。
  - 输出: 归一化 triage routing flags。
  - 失败处理: 非法 JSON 降级 REVIEW/SKIP。
  - 可观测证据: `raw`, `mode`, `dedupe_key`。
- `F-ProductRuntime.phase3-T01-03` Processor 结构化门禁
  - 输入: triage 结果。
  - 处理: 非 PASS 停在 structuring 前，持久化 triage-only `news_event`。
  - 输出: 不发布 structured stream 的审计事件与统计。
  - 失败处理: 持久化失败沿原 processor 异常路径暴露。
  - 可观测证据: `triage_structuring_saved_count`, `structured_stream_published=false`。

### 4) 实现步骤
1. 升级 `LocalQwenNewsTriageService` 输出 schema、JSON prompt 和 rule prefilter。
2. 扩展 `NewsStreamProcessor` 的 triage routing 与统计。
3. 补 Phase 3 正负样本和 processor 回归。

### 5) 测试设计与命令
- `TC-PHASE3-TRIAGE-HN`: `pytest database_service/tests/unit/test_phase3_importance_triage.py`
- `TC-PHASE3-STRUCTURING-GUARD`: 同上 processor path。
- 兼容回归: Phase 6 structuring harness、盘前 builder、5/22 replay、active v2 hard-negative。

### 6) 风险与回滚
- 风险: 规则过严把有价值新闻降级。强催化词 PASS 和 positive case 防止静态误杀。
- 回滚: 回退 `LocalQwenNewsTriageService` schema/prefilter 与 `NewsStreamProcessor` routing；数据库无需迁移回滚。

### 7) 验收映射
- `ACPT-PRODUCT-RUNTIME-PHASE3-01`: 低价值事件不调用 structuring。
- `ACPT-PRODUCT-RUNTIME-PHASE3-02`: 重要正样本仍 PASS。
- `ACPT-PRODUCT-RUNTIME-PHASE3-03`: triage 审计和统计可见。

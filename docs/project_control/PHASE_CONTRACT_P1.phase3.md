# Phase Execution Contract

## 1. Phase Identity

- Phase Name: LLM 最终裁决落地（Qwen2.5 + llama.cpp）
- Phase Code: P1.phase3
- Parent Milestone: P1（第一阶段）
- Risk Level: High
- Source Documents:
  - `docs/project_control/PHASE_CONTRACT_P1.md`
  - `docs/project_control/PRD.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`

---

## 2. Phase Objective（可量化）

1. 最终落库链路强制经过 LLM 裁判。  
2. 10% 灰度下 `llm_final_judged_ratio >= 95%`。  
3. `arbiter_p95_latency < 800ms`。  
4. 模型调用证据完整：`model_name/request_id/timestamp`。

---

## 3. Acceptance Targets（门禁条件）

- [ ] 链路顺序固定为 `语义粗筛 -> LLM 最终裁决`。
- [ ] 灰度指标达到 `llm_final_judged_ratio >= 95%`。
- [ ] 延迟指标达到 `arbiter_p95_latency < 800ms`。
- [ ] 模型栈固定为 `Qwen2.5 + llama.cpp` 且证据齐全。

---

## 4. Required Commands（必须执行命令）

- `pytest -q database_service/tests`
- `pytest -q tests`
- `rg -n "Qwen2.5|llama.cpp|llm_final_judged_ratio|arbiter_p95_latency|request_id|model_name" database_service theme_service docs`

---

## 5. Deliverables

- LLM 裁判链路接入与顺序约束说明。
- 灰度分桶证据与性能指标报告。
- 模型调用审计证据与误判归因报告。
- `tmp/plan/wbs.md`（仅任务集合/依赖/顺序，不含实现细节）。
- `tmp/plan/test_traceability_P1.phase3.json`（任务 -> 测试用例 -> 验收映射）。
- `docs/project_control/FEATURE_SPEC.md`（任务级实现设计，How）。
- `tmp/feature_traceability_P1.phase3.json`（任务 -> 需求/验收/测试命令映射）。
- `tmp/feature_validation_report_P1.phase3.json`（feature 映射校验结果）。

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- |
| 模型调用不稳定导致链路降级 | High | Medium | 限流、重试、降级策略 |
| 灰度指标达不到门槛 | High | Medium | 分桶优化与样本回放 |
| 审计证据缺失导致不可验收 | High | Low | 强制记录 request_id/model_name/timestamp |

---

## 7. Rollback Plan

- 回滚方式：临时回切到前一稳定判定策略并保持审计记录。
- 数据恢复：保留灰度批次结果，支持按 request_id 追踪与重放。
- 兼容性：仅允许受控降级，禁止无证据绕过最终裁判。

---

## 8. Non-Goals

- 不覆盖发布门禁收口（P1.phase4）。

---

## 9. Execution Flow（与 dev-orchestrator 对齐）

### STEP 1 —— 计划（不写代码）
- 产出 `tmp/plan/wbs.md`。
- 约束：`wbs.md` 只定义 What（任务、依赖、顺序、优先级），禁止写接口字段/数据表细节/错误码/回滚操作。

### STEP 1.5 —— 测试用例设计（不写代码）
- 产出 `docs/project_control/TEST_CASE_SPEC_P1.phase3.md` 与 `tmp/plan/test_traceability_P1.phase3.json`。
- 门禁：存在未映射任务时，禁止进入 STEP 1.8/STEP 2。

### STEP 1.8 —— Feature 设计（不写业务代码）
- 调用 `feature` 技能，基于 `wbs.md + test_traceability + PRD + ACCEPTANCE + PHASE_CONTRACT` 产出：
  - `docs/project_control/FEATURE_SPEC.md`
  - `tmp/feature_traceability_P1.phase3.json`
  - `tmp/feature_validation_report_P1.phase3.json`
- 角色边界：WBS=What，Feature=How；两者禁止越界与重复表达。

### STEP 2 —— 任务实施（按任务循环）
- 进入前置条件（MUST）：
  - `test_traceability_P1.phase3.json` 与 `feature_traceability_P1.phase3.json` 均存在；
  - 两者对当前任务 `task_id` 均有映射；
  - 任一映射缺失时，阻断执行并回到修订。
- 执行顺序（MUST）：
  1. 先按 `TC-ID` 新增/更新测试脚本；
  2. 按 `feature_traceability` 中 `test_commands` 与实现约束执行最小改动；
  3. 执行 `qa-gate`；
  4. 写入 `--test-evidence`，并按规则更新任务状态。

### 阶段末门禁（MUST）
- `feature_validation_report_P1.phase3.json.gate_ready == true`
- `test_traceability_P1.phase3.json.gate_ready == true`
- 不允许存在：
  - WBS 中有任务但 feature 未映射；
  - feature 中有任务但不在 WBS 子集；
  - 已变更代码但缺少对应测试文件与证据。

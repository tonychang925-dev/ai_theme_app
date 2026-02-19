# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 回放安全与发布门禁收口
- Phase Code: P1.phase4
- Parent Milestone: P1（第一阶段）
- Risk Level: High
- Source Documents:
  - `docs/project_control/PHASE_CONTRACT_P1.md`
  - `docs/project_control/PRD.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`

---

## 2. Phase Objective（可量化）

1. 回放一致率 `replay_consistency_rate = 100%`。  
2. 发布门禁阻断有效，超阈值自动阻断。  
3. 问题闭环率 `issues_closed_ratio = 100%`（`P1-ISS-01..10`）。

---

## 3. Acceptance Targets（门禁条件）

- [ ] 回放一致率达到 100%。
- [ ] 发布门禁在超阈值场景可自动阻断。
- [ ] 问题闭环清单全部关闭并可审计。
- [ ] 发布/回滚演练证据完整。

---

## 4. Required Commands（必须执行命令）

- `pytest -q database_service/tests`
- `pytest -q tests`
- `rg -n "replay_consistency_rate|release gate|rollback|issues_closed_ratio|block" database_service theme_service docs`

---

## 5. Deliverables

- replay 一致性报告与样本证据。
- Release Gate 阻断报告与阈值配置说明。
- 问题闭环清单（`P1-ISS-01..10`）与审计记录。
- 回滚演练记录与恢复时序证据。
- `tmp/plan/wbs.md`（仅任务集合/依赖/顺序，不含实现细节）。
- `tmp/plan/test_traceability_P1.phase4.json`（任务 -> 测试用例 -> 验收映射）。
- `docs/project_control/FEATURE_SPEC.md`（任务级实现设计，How）。
- `tmp/feature_traceability_P1.phase4.json`（任务 -> 需求/验收/测试命令映射）。
- `tmp/feature_validation_report_P1.phase4.json`（feature 映射校验结果）。

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- |
| replay 不一致导致状态污染 | High | Medium | 强制重放校验与补偿机制 |
| 发布门禁规则缺陷导致误放行 | High | Medium | 双阈值校验与演练 |
| 回滚流程不完整导致恢复失败 | High | Low | 预演与审计留痕 |

---

## 7. Rollback Plan

- 回滚方式：触发门禁失败时自动阻断发布并回滚到上一个稳定版本。
- 数据恢复：按 replay 日志和补偿记录恢复，保证状态一致。
- 兼容性：发布与回滚路径均需保留审计证据。

---

## 8. Non-Goals

- 不新增下一阶段功能范围。

---

## 9. Execution Flow（与 dev-orchestrator 对齐）

### STEP 1 —— 计划（不写代码）
- 产出 `tmp/plan/wbs.md`。
- 约束：`wbs.md` 只定义 What（任务、依赖、顺序、优先级），禁止写接口字段/数据表细节/错误码/回滚操作。

### STEP 1.5 —— 测试用例设计（不写代码）
- 产出 `docs/project_control/TEST_CASE_SPEC_P1.phase4.md` 与 `tmp/plan/test_traceability_P1.phase4.json`。
- 门禁：存在未映射任务时，禁止进入 STEP 1.8/STEP 2。

### STEP 1.8 —— Feature 设计（不写业务代码）
- 调用 `feature` 技能，基于 `wbs.md + test_traceability + PRD + ACCEPTANCE + PHASE_CONTRACT` 产出：
  - `docs/project_control/FEATURE_SPEC.md`
  - `tmp/feature_traceability_P1.phase4.json`
  - `tmp/feature_validation_report_P1.phase4.json`
- 角色边界：WBS=What，Feature=How；两者禁止越界与重复表达。

### STEP 2 —— 任务实施（按任务循环）
- 进入前置条件（MUST）：
  - `test_traceability_P1.phase4.json` 与 `feature_traceability_P1.phase4.json` 均存在；
  - 两者对当前任务 `task_id` 均有映射；
  - 任一映射缺失时，阻断执行并回到修订。
- 执行顺序（MUST）：
  1. 先按 `TC-ID` 新增/更新测试脚本；
  2. 按 `feature_traceability` 中 `test_commands` 与实现约束执行最小改动；
  3. 执行 `qa-gate`；
  4. 写入 `--test-evidence`，并按规则更新任务状态。

### 阶段末门禁（MUST）
- `feature_validation_report_P1.phase4.json.gate_ready == true`
- `test_traceability_P1.phase4.json.gate_ready == true`
- 不允许存在：
  - WBS 中有任务但 feature 未映射；
  - feature 中有任务但不在 WBS 子集；
  - 已变更代码但缺少对应测试文件与证据。

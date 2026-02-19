# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 运行时收敛与契约冻结
- Phase Code: P1.phase0
- Parent Milestone: P1（第一阶段）
- Risk Level: High
- Source Documents:
  - `docs/architecture/overview.md`
  - `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`
  - `docs/project_control/PRD.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`

---

## 2. Phase Objective（可量化）

1. 固化第一阶段唯一运行时处理链：`ThemeProcessor -> DecisionExecutor -> ClusteringListener`，重复可执行入口数=0。  
2. 冻结 `DecisionEnvelope v1` 契约并启用必填字段校验，必填覆盖率=100%。  
3. 收敛消息解析策略为单一可解析契约，禁止无边界递归 payload 解析分支。  
4. 实现 `trace_id` 从 `news_stream_*` 到 `theme_processor` 到 `DecisionExecutor` 的全链路可追踪。  
5. 清理高风险重复定义与生产路径调试输出（`print/traceback.print_exc`）到 0。

---

## 3. Acceptance Targets（门禁条件）

- [ ] 仅保留一个有效决策路由实现路径（无重复入口可触发）。
- [ ] `DecisionEnvelope v1` 必填字段完整：`decision_id,event_id,action,payload_version,trace_id,idempotency_key,payload`。
- [ ] `news` 消息格式收敛到单一可解析契约，缺失必填字段消息被 reject+dead-letter。
- [ ] 运行时生产路径中 `print` 与 `traceback.print_exc` 清零。
- [ ] `trace_id` 可跨 `news_stream_* -> theme_processor -> DecisionExecutor` 链路检索。

---

## 4. Required Commands（必须执行命令）

- `pytest database_service/tests/streams -q`
- `rg -n "def _get_action_for_decision_type\\(|def initialize_with_categories_only\\(|def discover_category_only\\(|def _process_storage_batch\\(|def _update_storage_stats\\(" database_service/streams/handlers/theme_processor.py database_service/streams/handlers/news_stream_handler.py theme_service/services/theme_service.py`
- `! rg -n "print\\(|traceback\\.print_exc\\(" database_service/streams/handlers/theme_processor.py database_service/streams/handlers/news_stream_handler.py database_service/streams/handlers/DecisionExecutor.py database_service/streams/handlers/clustering_listener.py theme_service/services/theme_service.py`
- `rg -n "decision_id|event_id|action|payload_version|trace_id|idempotency_key|payload" docs/project_control/ACCEPTANCE.md docs/project_control/prd_p1.md`
- `pytest -q database_service/tests/streams/test_message_serializer.py`
- `pytest -q database_service/tests/streams/test_stream_config.py`

---

## 5. Deliverables

- 运行时单链路与入口清单（P1.phase0-T01 产物）。
- `DecisionEnvelope v1` 字段字典、版本规则、dual-read 兼容说明（P1.phase0-T02 产物）。
- 重复定义清理与静态扫描结果（P1.phase0-T03 产物）。
- `trace_id/payload_version` 全链路追踪证据（P1.phase0-T04 产物）。
- 文档更新：链路清单、契约规范、验收记录。
- `tmp/plan/wbs.md`（仅任务集合/依赖/顺序，不含实现细节）。
- `tmp/plan/test_traceability_P1.phase0.json`（任务 -> 测试用例 -> 验收映射）。
- `docs/project_control/FEATURE_SPEC.md`（任务级实现设计，How）。
- `tmp/feature_traceability_P1.phase0.json`（任务 -> 需求/验收/测试命令映射）。
- `tmp/feature_validation_report_P1.phase0.json`（feature 映射校验结果）。

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- |
| 重复函数定义导致运行时行为漂移 | High | High | 冻结单链路真源并执行重复定义扫描门禁 |
| 契约字段新增引发历史消息兼容失败 | Medium | Medium | 启用 dual-read（v0/v1）过渡，内部统一归一到 v1 |
| payload 解析分支复杂导致语义失真 | High | Medium | 强制必填与类型校验，reject+dead-letter，移除无界递归 |
| 缺失 trace 字段导致问题不可追踪 | Medium | Medium | 将 `trace_id/payload_version` 设为硬约束并做链路抽样验证 |
| 生产路径调试输出污染日志与门禁 | Medium | High | 清理 `print/traceback`，统一结构化日志字段 |

---

## 7. Rollback Plan

- 回滚方式：保留历史解析器的只读兼容分支（非默认），发生兼容故障时回切到兼容读取模式。  
- 数据恢复策略：拒绝消息全部写入 dead-letter，保留原始消息ID与错误码，支持补偿重放。  
- 兼容性说明：写入统一 `DecisionEnvelope v1`；读取允许 `v0/v1` 过渡，直至消费端全部完成升级。

---

## 8. Non-Goals

- 不进行动态阈值策略优化（P1.phase2）。
- 不引入或放量 LLM 最终裁决链路（P1.phase3）。
- 不做回放门禁收口与发布阻断策略上线（P1.phase4）。
- 不新增第二阶段（CQRS/状态机）或前端产品化需求。

---

## 9. Execution Flow（与 dev-orchestrator 对齐）

### 9.0 执行模式（推荐）

- 推荐：`dev-orchestrator --mode autopilot`
- 目标：尽量不中断执行，直到 `STEP 5.2` 验收决策点再停。
- 中断白名单：仅合同冲突不可裁决、破坏性操作需授权、凭据缺失且补偿失败、安全/合规越界。

Autopilot 建议参数：

```text
--mode autopilot
--max-retries 5
--retry-backoff 1,2,4,8,16
--auto-reconcile true
--stop-at step5.2
```

Run 状态与续跑（MUST）：

```bash
RUN_ID="$(date +%Y%m%d_%H%M%S)"
mkdir -p "tmp/runs/${RUN_ID}/checkpoints"
echo "${RUN_ID}" > tmp/current_run_id.txt

# 中断后续跑
RUN_ID="$(cat tmp/current_run_id.txt)"
# 约定：dev-orchestrator 使用 --mode autopilot --resume "${RUN_ID}"
```

### STEP 1 —— 计划（不写代码）
- 产出 `tmp/plan/wbs.md`。
- 约束：`wbs.md` 只定义 What（任务、依赖、顺序、优先级），禁止写接口字段/数据表细节/错误码/回滚操作。

### STEP 1.5 —— 测试用例设计（不写代码）
- 产出 `docs/project_control/TEST_CASE_SPEC_P1.phase0.md` 与 `tmp/plan/test_traceability_P1.phase0.json`。
- 门禁：存在未映射任务时，禁止进入 STEP 1.8/STEP 2。

### STEP 1.8 —— Feature 设计（不写业务代码）
- 调用 `feature` 技能，基于 `wbs.md + test_traceability + PRD + ACCEPTANCE + PHASE_CONTRACT` 产出：
  - `docs/project_control/FEATURE_SPEC.md`
  - `tmp/feature_traceability_P1.phase0.json`
  - `tmp/feature_validation_report_P1.phase0.json`
- 角色边界：WBS=What，Feature=How；两者禁止越界与重复表达。

### STEP 2 —— 任务实施（按任务循环）
- 进入前置条件（MUST）：
  - `test_traceability_P1.phase0.json` 与 `feature_traceability_P1.phase0.json` 均存在；
  - 两者对当前任务 `task_id` 均有映射；
  - 任一映射缺失时，阻断执行并回到修订。
- 执行顺序（MUST）：
  1. 先按 `TC-ID` 新增/更新测试脚本；
  2. 按 `feature_traceability` 中 `test_commands` 与实现约束执行最小改动；
  3. 执行 `qa-gate`；
  4. 写入 `--test-evidence`，并按规则更新任务状态。

### 阶段末门禁（MUST）
- `feature_validation_report_P1.phase0.json.gate_ready == true`
- `test_traceability_P1.phase0.json.gate_ready == true`
- 不允许存在：
  - WBS 中有任务但 feature 未映射；
  - feature 中有任务但不在 WBS 子集；
  - 已变更代码但缺少对应测试文件与证据。

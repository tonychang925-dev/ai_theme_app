# FEATURE SPEC - P1.phase1

## 任务总览（基于 WBS 的功能分解扩展）

- 阶段：`P1.phase1`
- 范围：路由统一与幂等执行
- 约束：不跨入 phase2/phase3/phase4 的策略/模型扩展

任务到功能块映射：
- `P1.phase1-T01`：未知动作 fail-fast + dead-letter
- `P1.phase1-T02`：严格 schema 解析与拒绝策略
- `P1.phase1-T03`：幂等门禁与 duplicate-skip
- `P1.phase1-T04`：normal 未匹配 -> publish_clustering -> pending + ACK
- `P1.phase1-T05`：失败消息受控处理（重试上限 + dead-letter）

---

## Task P1.phase1-T01 — unknown action fail-fast + dead-letter

### 1) 目标与边界
- 目标：任何未知 `action/operation` 必须在执行前被阻断，不能进入业务写路径。
- 非目标：不在本任务扩展 action 语义体系，仅做门禁与拒绝。

### 2) 子功能分解（新增）
- `F-T01-01` 动作白名单校验器：统一校验 `action` 合法性。
- `F-T01-02` 拒绝路由：未知动作写入 `stream:dead:letter`。
- `F-T01-03` 拒绝审计：记录 `decision_id/event_id/action/reason`。
- `F-T01-04` 统计指标：`unknown_action_count` 增量。

### 3) 接口与契约
- 输入：`stream:events:decision` 消息（必须含 `decision_id,event_id,action,payload,trace_id`）。
- 输出：合法动作继续执行；未知动作直接 reject + dead-letter。
- 失败码：`ERR_UNKNOWN_ACTION`。

### 4) 状态变更与数据影响
- 无新表；只新增拒绝流转与统计计数。
- 不允许出现“未知动作执行后落库成功”的状态。

### 5) 最小实现步骤
1. 在 `DecisionExecutor` 执行分派前增加 action 白名单判断。
2. 未命中白名单时调用 dead-letter 路径并结束执行。
3. 增加拒绝原因与计数埋点。

### 6) 测试设计与命令
- TC-ID: `TC-P1P1-001`
- 命令：`pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "unknown_action_fail_fast_to_dead_letter_behavior"`

### 7) 风险与回滚
- 风险：白名单误配置导致合法动作误杀。
- 回滚：恢复上一稳定白名单版本并保留拒绝审计。

### 8) 验收映射
- `ACC-P1-P1-02`

---

## Task P1.phase1-T02 — strict schema parser + reject strategy

### 1) 目标与边界
- 目标：消息必须严格符合 v1 契约，禁止 `str(value)` 等弱降级进入执行路径。
- 非目标：不做历史多版本自动修复，仅执行拒绝策略。

### 2) 子功能分解（新增）
- `F-T02-01` v1 必填字段校验器：`decision_id,event_id,action,payload_version,trace_id,idempotency_key,payload`。
- `F-T02-02` 类型约束校验器：关键字段类型与空值校验。
- `F-T02-03` 拒绝策略：不合规消息进入 dead-letter。
- `F-T02-04` 错误编码：`ERR_CONTRACT_V1_MISSING_FIELDS / ERR_CONTRACT_TYPE_INVALID`。

### 3) 接口与契约
- 输入：决策消息 JSON。
- 输出：合法消息执行，不合法 reject。
- 约束：严禁将解析失败字段转字符串后继续执行。

### 4) 状态变更与数据影响
- 无新表；新增契约拒绝路径与审计。

### 5) 最小实现步骤
1. 在决策入口添加 envelope 校验函数。
2. 失败时直接 dead-letter，禁止执行器继续。
3. 将拒绝原因写入 reason 字段。

### 6) 测试设计与命令
- TC-ID: `TC-P1P1-002`
- 命令：`pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "strict_schema_missing_required_field_goes_dead_letter"`

### 7) 风险与回滚
- 风险：历史脏消息大量被拒绝。
- 回滚：仅回滚阈值，不恢复弱降级。

### 8) 验收映射
- `ACC-P1-P1-02`

---

## Task P1.phase1-T03 — idempotency gate and duplicate guard

### 1) 目标与边界
- 目标：同一 `idempotency_key` 仅执行一次，重复执行必须 skip。
- 非目标：不引入跨服务全局幂等中心。

### 2) 子功能分解（新增）
- `F-T03-01` 幂等键读取与校验。
- `F-T03-02` duplicate-skip 路径（不写库、不重复下游发布）。
- `F-T03-03` 幂等命中审计（`duplicate_hit=true`）。
- `F-T03-04` 幂等统计指标（`duplicate_skip_count`）。

### 3) 接口与契约
- 输入：带 `idempotency_key` 的决策消息。
- 输出：首次执行成功；重复命中直接 skip。

### 4) 状态变更与数据影响
- 幂等命中时禁止产生新增业务写入。

### 5) 最小实现步骤
1. 执行前查询/设置幂等锁。
2. 命中时 ACK 并返回 skip。
3. 记录 duplicate 审计与指标。

### 6) 测试设计与命令
- TC-ID: `TC-P1P1-003`
- 命令：`pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "duplicate_skip_for_same_idempotency_key"`

### 7) 风险与回滚
- 风险：幂等键构造不稳定导致漏判。
- 回滚：恢复稳定键构造并重放冲突样本。

### 8) 验收映射
- `ACC-P1-P1-01`

---

## Task P1.phase1-T04 — normal unmatched -> pending + ack

### 1) 目标与边界
- 目标：`normal` 未匹配必须发布 `publish_clustering` 决策并进入 `stream:events:pending`，原消息 ACK。
- 非目标：不在本任务引入 phase2 候选治理策略。

### 2) 子功能分解（新增）
- `F-T04-01` 分类优先匹配失败过程可观测：必须能看到未匹配分支证据。
- `F-T04-02` 决策发布：未匹配时生成 `action=publish_clustering`。
- `F-T04-03` 执行转发：DecisionExecutor 将事件写入 pending。
- `F-T04-04` ACK 保障：decision 消息处理后不残留 pending。
- `F-T04-05` 链路字段透传：`trace_id/decision_id` 在 decision 与 pending 一致。
- `F-T04-06` 基线复用验证：必须复用 `test_theme_processor.py::test_new_architecture_with_dataset()` 的真实流程。

### 3) 接口与契约
- 输入：`stream:events:normal` 事件。
- 输出：未匹配场景生成 `publish_clustering` 决策并落 `stream:events:pending`。
- 过程约束：必须验证分类优先框架被真实触发，而非仅验证结果流。

### 4) 状态变更与数据影响
- pending 事件必须包含：`event_data(trace_id) + decision_id`。
- `decision_executors` 组中不应残留该 decision 消息 pending。

### 5) 最小实现步骤
1. ThemeProcessor 在分类优先路径产生未匹配决策。
2. 决策发布到 `stream:events:decision`。
3. DecisionExecutor 执行 `publish_clustering` -> pending。
4. decision 消息 ACK。
5. 输出分类统计与链路字段证据。

### 6) 测试设计与命令
- TC-ID: `TC-P1P1-004`
- 命令：
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "normal_unmatched_event_flows_to_pending_via_decision_executor"`
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "test_phase1_dataset_baseline_via_test_theme_processor"`
  - `pytest -q database_service/tests/streams`
  - `pytest -q tests`
- 断言要点（MUST）：
  - `decision_type` 属于未匹配分支；`reason` 含未匹配语义；`category_inferences` 递增。
  - `action=publish_clustering`。
  - pending 落库成功且 `decision_id` 对齐 decision。
  - pending payload 含 `trace_id` 且与 decision 一致。
  - publish_clustering 对应 decision 消息 ACK 成功。
  - 基线复用测试返回结构化 `t04_validation` 并全部通过。

### 7) 风险与回滚
- 风险：未匹配证据不足导致“看似通过、实则未走框架”。
- 回滚：保留结果路径，恢复过程证据采集与断言强度。

### 8) 验收映射
- `ACC-P1-P1-03`

---

## Task P1.phase1-T05 — failure control with retry cap + dead-letter

### 1) 目标与边界
- 目标：失败消息受控（重试上限 + dead-letter），禁止无限悬挂。
- 非目标：不做 phase4 发布策略。

### 2) 子功能分解（新增）
- `F-T05-01` 重试计数与上限门禁。
- `F-T05-02` 超限死信转移。
- `F-T05-03` 失败原因审计与可追溯字段。
- `F-T05-04` 队列健康观测（死信率/积压）。

### 3) 接口与契约
- 输入：执行失败消息。
- 输出：可重试则重试，超限死信并终止生命周期。

### 4) 状态变更与数据影响
- 死信消息应包含可定位的 reason 与原消息标识。

### 5) 最小实现步骤
1. 失败后更新重试计数。
2. 判断是否超过上限。
3. 超限进入 dead-letter。

### 6) 测试设计与命令
- TC-ID: `TC-P1P1-005`
- 命令：`pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "failure_message_controlled_to_dead_letter_no_hang"`

### 7) 风险与回滚
- 风险：上限配置过小导致过早死信。
- 回滚：恢复上个稳定阈值配置。

### 8) 验收映射
- `ACC-P1-P1-02`

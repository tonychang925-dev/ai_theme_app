# FEATURE SPEC - P1.phase0

## Task P1.phase0-T01 — 冻结第一阶段唯一运行时链路与入口清单

### 1) 目标与边界
- 目标：固定唯一生效链路 `ThemeProcessor -> DecisionExecutor -> ClusteringListener`。
- 非目标：不引入 phase1 的幂等落库改造。

### 2) 接口与契约
- 输入：news stream 消息（含 `event_id/action/payload`）。
- 输出：统一决策调用路径，不允许平行可触发入口。
- 约束：未匹配动作必须 fail-fast（阶段内先完成路由收敛，不做完整 dead-letter 接入）。

### 3) 数据模型与状态变更
- 不新增表结构。
- 仅允许通过单一路径触发执行，不允许旁路写入。

### 4) 实现步骤
1. 扫描并标记重复入口函数。
2. 收敛为单一生效入口并删除旁路调用。
3. 补充入口层回归测试。

### 5) 测试设计与命令
- TC: `TC-P1P0-001`
- 命令：`rg -n "def _get_action_for_decision_type\\(|def initialize_with_categories_only\\(|def discover_category_only\\(|def _process_storage_batch\\(|def _update_storage_stats\\(" database_service/streams/handlers/theme_processor.py database_service/streams/handlers/news_stream_handler.py theme_service/services/theme_service.py`

### 6) 风险与回滚
- 风险：误删入口导致链路中断。
- 回滚：恢复上一个稳定入口实现并保留审计日志。

### 7) 验收映射
- `ACPT-P1.phase0-001`

---

## Task P1.phase0-T02 — 定义 DecisionEnvelope v1 字段与 dual-read 兼容策略

### 1) 目标与边界
- 目标：冻结 `DecisionEnvelope v1` 必填字段，兼容读取 v0/v1。
- 非目标：不完成 phase3 的模型判定结构扩展。

### 2) 接口与契约
- 必填字段：`decision_id,event_id,action,payload_version,trace_id,idempotency_key,payload`。
- 兼容策略：读取支持 dual-read，写入统一 v1。

### 3) 数据模型与状态变更
- 不新增持久化表；更新消息契约校验逻辑。

### 4) 实现步骤
1. 定义字段字典与版本规则。
2. 实装 dual-read 解析器。
3. 补充契约一致性测试。

### 5) 测试设计与命令
- TC: `TC-P1P0-002`
- 命令：`rg -n "decision_id|event_id|action|payload_version|trace_id|idempotency_key|payload" docs/project_control/ACCEPTANCE.md docs/project_control/prd_p1.md`

### 6) 风险与回滚
- 风险：历史消息兼容失败。
- 回滚：临时开启兼容解析开关，继续统一写入 v1。

### 7) 验收映射
- `ACPT-P1.phase0-002`

---

## Task P1.phase0-T03 — 清理重复函数定义并建立静态扫描门禁

### 1) 目标与边界
- 目标：重复定义清零，生产路径 `print/traceback.print_exc` 清零。
- 非目标：不覆盖 phase4 的发布门禁阻断策略。

### 2) 接口与契约
- 输入：handlers/schedulers/theme_service 代码。
- 输出：静态扫描门禁规则和清理结果。

### 3) 数据模型与状态变更
- 无数据结构变更。

### 4) 实现步骤
1. 清理重复函数定义。
2. 清理生产路径调试输出。
3. 将扫描命令纳入门禁脚本。

### 5) 测试设计与命令
- TC: `TC-P1P0-003`
- 命令：`! rg -n "print\\(|traceback\\.print_exc\\(" database_service/streams/handlers/theme_processor.py database_service/streams/handlers/news_stream_handler.py database_service/streams/handlers/DecisionExecutor.py database_service/streams/handlers/clustering_listener.py theme_service/services/theme_service.py`

### 6) 风险与回滚
- 风险：清理日志导致定位信息不足。
- 回滚：保留结构化日志字段，不恢复 print/traceback。

### 7) 验收映射
- `ACPT-P1.phase0-003`

---

## Task P1.phase0-T04 — trace_id/payload_version 全链路贯通方案评审

### 1) 目标与边界
- 目标：`trace_id` 跨 `news_stream_* -> theme_processor -> DecisionExecutor` 可检索。
- 非目标：不在本阶段引入 LLM 裁判指标。

### 2) 接口与契约
- 消息头与日志必须保留 `trace_id/payload_version`。
- 链路节点日志字段统一。

### 3) 数据模型与状态变更
- 无新增表，仅日志字段与中间对象字段贯通。

### 4) 实现步骤
1. 统一链路字段透传。
2. 增加日志检索路径。
3. 补全链路集成测试。

### 5) 测试设计与命令
- TC: `TC-P1P0-004`
- 命令：
  - `pytest -q database_service/tests/streams/test_message_serializer.py`
  - `pytest -q database_service/tests/streams/test_stream_config.py`
  - `pytest database_service/tests/streams -q`

### 6) 风险与回滚
- 风险：字段透传不完整导致断链。
- 回滚：恢复上一稳定日志透传实现并保留兼容字段。

### 7) 验收映射
- `ACPT-P1.phase0-004`

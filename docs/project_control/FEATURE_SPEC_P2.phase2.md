# FEATURE SPEC - P2.phase2

## 0. Meta
- Phase: `P2.phase2`
- 目标: 建立可解释热度模型、生命周期状态机、榜单刷新链路与回放能力。
- 约束: 不做投资建议或交易决策；不回改前面 phases 的匹配和知识对象边界。
- 冲突裁决说明:
  - 本 phase 只实现可解释热度和状态机，不把“运营化”扩展成交易信号系统。
  - 榜单刷新异常时优先返回上次有效快照，不允许刷新窗口空榜。
- 真源文档:
  - `docs/architecture/个人投资助理-项目架构设计-第二阶段（题材匹配重构版）.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PHASE_CONTRACT_P2.phase2.md`
  - `docs/project_control/PLAN_WBS.md`

## Task P2.phase2-T01 — 设计热度因子模型与可解释输出字段

### 1) 目标与边界
- 目标:
  - 输出可解释热度模型
  - 热度构成字段完整率 `100%`
- 非目标:
  - 不输出交易建议

### 2) 接口与契约
- 输入:
  - 事件数量、事件质量、新鲜度、股票联动、扩散度
- 输出:
  - `heat_value`, `heat_level`, `heat_factors`
- 约束:
  - 每次热度计算必须带因子明细

### 3) 数据模型与状态变更
- `theme_heat_realtime`
- `theme_heat_daily`

### 4) 子功能分解
- `F-P2.phase2-T01-01` 因子采集器
  - 输入: 事件和对象层数据
  - 处理逻辑: 采集热度因子
  - 输出: 原始因子向量
  - 失败处理: 缺因子则阻断计算
  - 可观测证据: 因子完整率
- `F-P2.phase2-T01-02` 热度计算器
  - 输入: 因子向量
  - 处理逻辑: 计算 `heat_value/heat_level`
  - 输出: 热度记录
  - 失败处理: 公式异常回退上次有效值并审计
  - 可观测证据: 计算版本
- `F-P2.phase2-T01-03` 可解释输出器
  - 输入: 热度结果
  - 处理逻辑: 生成因子说明
  - 输出: `heat_factors`
  - 失败处理: 无解释字段则 gate fail
  - 可观测证据: 输出字段完整率

### 5) 实现步骤
- Step-1: 冻结热度因子清单。
- Step-2: 定义计算公式和版本。
- Step-3: 补充解释字段模板。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase2-01-heat-factor-complete`
  - `TC-P2.phase2-02-heat-formula-versioned`
  - `TC-P2.phase2-03-heat-explainable`
- 必跑命令:
  - `rg -n "heat_value|heat_level|heat_factors" .`
  - `.venv/bin/python -m pytest -q`

### 7) 风险与回滚
- 风险:
  - 热度不可解释
- 回滚:
  - 回切上一版公式和快照

### 8) 验收映射
- `ACPT-P2.phase2-001`

---

## Task P2.phase2-T02 — 设计生命周期状态机与迁移规则

### 1) 目标与边界
- 目标:
  - 冻结 `seed/emerging/hot/diffusing/cooling/archive`
  - 状态迁移显式配置
- 非目标:
  - 不做人工经验临时改状态

### 2) 接口与契约
- 输入:
  - 每日热度、联动数据
- 输出:
  - `lifecycle_state`, `state_transition_reason`
- 约束:
  - 状态迁移必须可回放

### 3) 数据模型与状态变更
- `theme_lifecycle`
- 状态机:
  - `seed -> emerging -> hot -> diffusing -> cooling -> archive`

### 4) 子功能分解
- `F-P2.phase2-T02-01` 状态判定器
  - 输入: 热度与联动指标
  - 处理逻辑: 选择目标状态
  - 输出: `lifecycle_state`
  - 失败处理: 指标不完整则保持旧状态并告警
  - 可观测证据: 状态迁移次数
- `F-P2.phase2-T02-02` 迁移规则配置器
  - 输入: 状态机配置
  - 处理逻辑: 加载显式迁移规则
  - 输出: 规则版本
  - 失败处理: 规则缺失则阻断批次
  - 可观测证据: 规则版本
- `F-P2.phase2-T02-03` 原因记录器
  - 输入: 迁移前后状态与指标
  - 处理逻辑: 写 `state_transition_reason`
  - 输出: 回放记录
  - 失败处理: 缺原因则不允许提交迁移
  - 可观测证据: 原因完整率

### 5) 实现步骤
- Step-1: 定义状态机与转移条件。
- Step-2: 产出配置化规则。
- Step-3: 绑定迁移原因记录。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase2-04-state-machine-config`
  - `TC-P2.phase2-05-state-transition-reason`
  - `TC-P2.phase2-06-state-replay`
- 必跑命令:
  - `rg -n "lifecycle_state|state_transition_reason" .`
  - `.venv/bin/python -m pytest -q`

### 7) 风险与回滚
- 风险:
  - 状态规则漂移
- 回滚:
  - 回切上一版状态机规则

### 8) 验收映射
- `ACPT-P2.phase2-002`
- `ACPT-P2.phase2-004`

---

## Task P2.phase2-T03 — 设计榜单刷新链路、批次回放与空榜保护

### 1) 目标与边界
- 目标:
  - 榜单刷新 P95 `< 5 分钟`
  - 刷新窗口内不空榜
- 非目标:
  - 不做实时交易信号

### 2) 接口与契约
- 输入:
  - 热度批次、生命周期批次
- 输出:
  - 榜单快照
- 约束:
  - 刷新失败时返回上次有效快照

### 3) 数据模型与状态变更
- `theme_rank_snapshot`
- `rank_refresh_batch`

### 4) 子功能分解
- `F-P2.phase2-T03-01` 榜单刷新器
  - 输入: 热度批次
  - 处理逻辑: 生成榜单快照
  - 输出: 新榜单
  - 失败处理: 刷新失败回退到上次快照
  - 可观测证据: 刷新耗时
- `F-P2.phase2-T03-02` 批次回放器
  - 输入: 批次号
  - 处理逻辑: 重放热度与榜单生成过程
  - 输出: 回放报告
  - 失败处理: 回放失败阻断发布
  - 可观测证据: 回放成功率
- `F-P2.phase2-T03-03` 空榜保护器
  - 输入: 刷新结果
  - 处理逻辑: 检查空榜并执行回退
  - 输出: 非空榜单响应
  - 失败处理: 空榜直接标为故障
  - 可观测证据: 空榜次数

### 5) 实现步骤
- Step-1: 设计刷新批次模型。
- Step-2: 定义快照回退与空榜保护。
- Step-3: 增加批次回放工具。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase2-07-rank-refresh-p95`
  - `TC-P2.phase2-08-rank-no-empty-window`
  - `TC-P2.phase2-09-rank-batch-replay`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "rank_refresh_latency_ms|theme_rank|empty_rank|snapshot" .`

### 7) 风险与回滚
- 风险:
  - 榜单空榜
  - 刷新超时
- 回滚:
  - 保留上次稳定榜单快照

### 8) 验收映射
- `ACPT-P2.phase2-003`
- `ACPT-P2.phase2-005`

---

## Task P2.phase2-T04 — 定义热度/状态审计协议与回放验证方法

### 1) 目标与边界
- 目标:
  - 建立热度和状态变更审计
  - 可按 `event_id/theme_id/trace_id` 回放
- 非目标:
  - 不做 phase 外的全局审计平台

### 2) 接口与契约
- 输入:
  - 热度计算结果、状态迁移结果
- 输出:
  - `heat_audit_log`, `lifecycle_audit_log`
- 约束:
  - 缺 `trace_id` 不得记为有效审计

### 3) 数据模型与状态变更
- `heat_audit_log`
- `lifecycle_audit_log`

### 4) 子功能分解
- `F-P2.phase2-T04-01` 热度审计记录器
  - 输入: 热度结果
  - 处理逻辑: 记录因子和批次信息
  - 输出: 热度审计日志
  - 失败处理: 写失败则阻断刷新批次
  - 可观测证据: 热度审计覆盖率
- `F-P2.phase2-T04-02` 状态审计记录器
  - 输入: 状态迁移结果
  - 处理逻辑: 记录状态前后值和原因
  - 输出: 生命周期审计日志
  - 失败处理: 缺原因则拒绝提交
  - 可观测证据: 状态审计覆盖率
- `F-P2.phase2-T04-03` 联合回放验证器
  - 输入: `theme_id/event_id/trace_id`
  - 处理逻辑: 联查热度和状态日志
  - 输出: 回放结果
  - 失败处理: 任一链断开则 gate fail
  - 可观测证据: 联合回放成功率

### 5) 实现步骤
- Step-1: 冻结审计字段。
- Step-2: 建立回放查询键。
- Step-3: 接入榜单刷新批次。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase2-10-heat-audit`
  - `TC-P2.phase2-11-lifecycle-audit`
  - `TC-P2.phase2-12-joined-replay`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "trace_id|theme_id|event_id|heat_audit|lifecycle_audit" .`

### 7) 风险与回滚
- 风险:
  - 审计链不完整
- 回滚:
  - 停止热榜发布，回到最近稳定快照

### 8) 验收映射
- `ACPT-P2.phase2-004`

---

## Task P2.phase2-T05 — 完成热度与榜单 phase2 门禁验证和归档

### 1) 目标与边界
- 目标:
  - 验证热度解释、状态回放、榜单刷新和空榜保护
  - 输出 phase3 归档
- 非目标:
  - 不新增跨阶段能力

### 2) 接口与契约
- 输入:
  - phase3 全量指标与日志
- 输出:
  - 门禁结论和归档记录

### 3) 数据模型与状态变更
- 指标:
  - `rank_refresh_p95_ms`
  - `empty_rank_count`
  - `heat_factor_complete_rate`
  - `replay_success_rate`

### 4) 子功能分解
- `F-P2.phase2-T05-01` phase 指标汇总器
  - 输入: phase3 指标
  - 处理逻辑: 汇总刷新时延、空榜次数等
  - 输出: 门禁指标报告
  - 失败处理: 指标缺失不允许结项
  - 可观测证据: 归档报告
- `F-P2.phase2-T05-02` 回放验收器
  - 输入: 审计日志与批次
  - 处理逻辑: 执行关键题材回放验证
  - 输出: 回放通过结论
  - 失败处理: 回放失败则 gate fail
  - 可观测证据: 回放成功率
- `F-P2.phase2-T05-03` phase 归档器
  - 输入: 门禁结果和残留风险
  - 处理逻辑: 生成最终 phase3 归档
  - 输出: 评审结论
  - 失败处理: 风险未裁决不归档
  - 可观测证据: 评审纪要

### 5) 实现步骤
- Step-1: 汇总 phase3 指标。
- Step-2: 执行关键榜单与回放验收。
- Step-3: 归档最终结论。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase2-13-phase2-gate`
  - `TC-P2.phase2-14-no-empty-rank-gate`
  - `TC-P2.phase2-15-phase2-archive`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "heat_value|lifecycle_state|rank_refresh_latency_ms|phase3" docs/project_control tmp`

### 7) 风险与回滚
- 风险:
  - 归档结论与真实运行不一致
- 回滚:
  - phase3 不结项，保留 phase2 产品化基线

### 8) 验收映射
- `ACPT-P2.phase2-005`

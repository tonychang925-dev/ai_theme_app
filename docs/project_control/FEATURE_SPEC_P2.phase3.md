# FEATURE SPEC - P2.phase3

## 0. Meta
- Phase: `P2.phase3`
- 目标: 建立 `UNKNOWN -> unknown_event_pool -> 聚类 -> new_theme_draft -> theme_merge_review` 的可执行闭环。
- 约束: 不允许任何草案直接创建正式题材；不进入知识对象和热度运营化范围。
- 冲突裁决说明:
  - `P2.phase0` 中“Unknown 只做事件级出口”的限制在本 phase 解除，但仍保留“不得直接正式建题材”。
  - 采用 [PHASE_CONTRACT_P2.phase3.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/PHASE_CONTRACT_P2.phase3.md) 的审核优先策略，而非自动上线愿景。
- 真源文档:
  - `docs/architecture/个人投资助理-项目架构设计-第二阶段（题材匹配重构版）.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PHASE_CONTRACT_P2.phase3.md`
  - `docs/project_control/PLAN_WBS.md`

## Task P2.phase3-T01 — 定义 `unknown_event_pool` 结构与 Unknown 入池协议

### 1) 目标与边界
- 目标:
  - 所有 `UNKNOWN` 统一入池
  - 保留事件、证据、trace
- 非目标:
  - 不做聚类

### 2) 接口与契约
- 输入:
  - `ThemeDecisionEnvelope(decision=UNKNOWN)`
- 输出:
  - `unknown_event_pool` 记录
- 约束:
  - 必填: `unknown_id,event_id,trace_id,reason,evidence_summary,created_at`
  - 入池失败不得吞掉事件

### 3) 数据模型与状态变更
- 对象: `unknown_event_pool`
- 状态:
  - `received -> persisted -> clustered(optional)`

### 4) 子功能分解
- `F-P2.phase3-T01-01` Unknown 记录标准化
  - 输入: `UNKNOWN` envelope
  - 处理逻辑: 归一化字段并生成 `unknown_id`
  - 输出: 标准 Unknown 记录
  - 失败处理: 缺字段则 dead-letter
  - 可观测证据: 入池成功率
- `F-P2.phase3-T01-02` 证据链保存器
  - 输入: `reason`, `evidence_summary`
  - 处理逻辑: 保留候选摘要和裁决原因
  - 输出: 可追溯记录
  - 失败处理: 证据缺失时拒绝入池
  - 可观测证据: 证据完整率
- `F-P2.phase3-T01-03` 重试与幂等守卫
  - 输入: 重复 `UNKNOWN`
  - 处理逻辑: 按 `event_id + trace_id` 去重
  - 输出: 唯一池记录
  - 失败处理: 重复写入报警
  - 可观测证据: 去重计数

### 5) 实现步骤
- Step-1: 冻结 Unknown 入池字段。
- Step-2: 设计幂等键与补偿重试。
- Step-3: 接通 `ThemeMatchEngine` 的 `UNKNOWN` 出口。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase3-01-unknown-ingest`
  - `TC-P2.phase3-02-unknown-idempotent`
  - `TC-P2.phase3-03-evidence-required`
- 必跑命令:
  - `rg -n "unknown_event_pool|UNKNOWN|trace_id|evidence" .`
  - `.venv/bin/python -m pytest -q`

### 7) 风险与回滚
- 风险:
  - Unknown 事件丢失
  - 证据断链
- 回滚:
  - 仅关闭入池消费，保留原始 `UNKNOWN` 流消息待补偿

### 8) 验收映射
- `ACPT-P2.phase3-001`
- `ACPT-P2.phase3-006`

---

## Task P2.phase3-T02 — 设计 Unknown 聚类时间窗、阈值与可调参策略

### 1) 目标与边界
- 目标:
  - 基于 `7天` 时间窗、相似度、对象词稳定性成团
  - 参数可配置
- 非目标:
  - 不直接输出正式题材

### 2) 接口与契约
- 输入:
  - `unknown_event_pool` 时间窗内事件
- 输出:
  - `cluster_id`, `member_events`, `cluster_summary`, `cluster_score`
- 约束:
  - 默认时间窗 `7 天`
  - 阈值配置必须外置

### 3) 数据模型与状态变更
- 对象:
  - `unknown_cluster`
- 状态:
  - `candidate -> stable -> draft_ready`

### 4) 子功能分解
- `F-P2.phase3-T02-01` 时间窗切片器
  - 输入: Unknown 事件池
  - 处理逻辑: 按 `7天` 滚动窗切片
  - 输出: 待聚类样本
  - 失败处理: 时间戳异常样本剔除并审计
  - 可观测证据: 窗口样本数
- `F-P2.phase3-T02-02` 相似度成团器
  - 输入: 事件文本、对象词、实体
  - 处理逻辑: 计算相似度并聚类
  - 输出: 簇结果
  - 失败处理: 低稳定性簇退回池中观察
  - 可观测证据: `cluster_score`, `cluster_size`
- `F-P2.phase3-T02-03` 参数治理器
  - 输入: 窗口、阈值、最小簇规模
  - 处理逻辑: 读取配置并记录版本
  - 输出: 可调参聚类策略
  - 失败处理: 配置缺失则阻断任务
  - 可观测证据: 参数版本与变更记录

### 5) 实现步骤
- Step-1: 定义聚类输入特征与阈值。
- Step-2: 设计保守阈值与观察态簇。
- Step-3: 输出聚类摘要与代表事件。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase3-04-cluster-window`
  - `TC-P2.phase3-05-cluster-threshold`
  - `TC-P2.phase3-06-cluster-observation-fallback`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "cluster|window|threshold|unknown" .`

### 7) 风险与回滚
- 风险:
  - 阈值过松导致草案爆炸
  - 阈值过严导致长期不成团
- 回滚:
  - 停止聚类任务，仅保留 Unknown 入池

### 8) 验收映射
- `ACPT-P2.phase3-002`
- `ACPT-P2.phase3-005`

---

## Task P2.phase3-T03 — 设计 `new_theme_draft` 草案结构与生成规则

### 1) 目标与边界
- 目标:
  - 稳定簇只生成草案
  - 草案包含命名、摘要、代表事件、重复候选
- 非目标:
  - 不写入正式题材主档

### 2) 接口与契约
- 输入:
  - `unknown_cluster(draft_ready)`
- 输出:
  - `new_theme_draft`
- 约束:
  - 不得直接写 `theme_master`

### 3) 数据模型与状态变更
- 对象:
  - `new_theme_draft`
- 状态:
  - `generated -> pending_review -> resolved`

### 4) 子功能分解
- `F-P2.phase3-T03-01` 草案命名器
  - 输入: 簇主题词、对象词、代表事件
  - 处理逻辑: 生成候选题材名称
  - 输出: `draft_name`
  - 失败处理: 命名不稳定时进入人工补录
  - 可观测证据: 命名来源
- `F-P2.phase3-T03-02` 草案摘要器
  - 输入: 聚类摘要与事件集合
  - 处理逻辑: 生成题材摘要、代表驱动
  - 输出: `draft_summary`
  - 失败处理: 摘要缺失时阻断草案落库
  - 可观测证据: 摘要长度、代表事件数
- `F-P2.phase3-T03-03` 重复题材候选器
  - 输入: 草案名、现有题材画像
  - 处理逻辑: 输出可能重复的题材候选
  - 输出: `dup_theme_candidates`
  - 失败处理: 查重失败时强制进审核
  - 可观测证据: 候选数量

### 5) 实现步骤
- Step-1: 定义草案 schema。
- Step-2: 提取代表事件与核心对象词。
- Step-3: 接入重复候选检索。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase3-07-draft-schema`
  - `TC-P2.phase3-08-draft-not-theme-master`
  - `TC-P2.phase3-09-dedup-candidates`
- 必跑命令:
  - `rg -n "new_theme_draft|theme_master|draft_name|draft_summary" .`
  - `.venv/bin/python -m pytest -q`

### 7) 风险与回滚
- 风险:
  - 草案质量差
  - 草案越权进入正式题材
- 回滚:
  - 停止草案生成，仅保留簇结果

### 8) 验收映射
- `ACPT-P2.phase3-003`

---

## Task P2.phase3-T04 — 设计 `theme_merge_review` 审核动作与审计协议

### 1) 目标与边界
- 目标:
  - 审核动作只允许 `create_theme / merge_to_existing_theme / defer_observation`
  - 全量审计可回放
- 非目标:
  - 不自动跳过人工审核

### 2) 接口与契约
- 输入:
  - `new_theme_draft`
  - 审核意见
- 输出:
  - 审核结果与动作日志
- 约束:
  - 每个动作必须带 `reviewer`, `review_reason`, `trace_id`

### 3) 数据模型与状态变更
- 对象:
  - `theme_merge_review`
- 状态:
  - `pending -> approved_create|approved_merge|deferred`

### 4) 子功能分解
- `F-P2.phase3-T04-01` 审核动作枚举器
  - 输入: 草案和审核意见
  - 处理逻辑: 只接受三类动作
  - 输出: 审核结果
  - 失败处理: 非法动作拒绝提交
  - 可观测证据: 动作分布
- `F-P2.phase3-T04-02` 合并证据记录器
  - 输入: 重复题材候选与审核理由
  - 处理逻辑: 保存合并原因与目标题材
  - 输出: 合并日志
  - 失败处理: 证据不足时不允许 merge
  - 可观测证据: 合并证据链
- `F-P2.phase3-T04-03` 审核回放器
  - 输入: `draft_id`
  - 处理逻辑: 重建审核全过程
  - 输出: 回放记录
  - 失败处理: 缺日志则 gate fail
  - 可观测证据: 回放成功率

### 5) 实现步骤
- Step-1: 冻结审核动作和状态机。
- Step-2: 设计审核记录表与回放字段。
- Step-3: 衔接 create/merge/defer 三类执行器。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase3-10-review-actions`
  - `TC-P2.phase3-11-merge-evidence-required`
  - `TC-P2.phase3-12-review-replay`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "theme_merge_review|create_theme|merge_to_existing_theme|defer_observation" .`

### 7) 风险与回滚
- 风险:
  - 审核动作不可回放
  - merge 无证据
- 回滚:
  - 停止 create/merge 执行，仅保留 `defer_observation`

### 8) 验收映射
- `ACPT-P2.phase3-004`
- `ACPT-P2.phase3-005`

---

## Task P2.phase3-T05 — 完成 Unknown 闭环门禁验证与 phase3 评审归档

### 1) 目标与边界
- 目标:
  - 完成入池、聚类、草案、审核的门禁验证
  - 形成 phase 归档
- 非目标:
  - 不进入知识对象阶段

### 2) 接口与契约
- 输入:
  - phase1 全链路证据
- 输出:
  - 通过/阻断结论
- 约束:
  - 正式自动建题材数必须为 `0`

### 3) 数据模型与状态变更
- 指标:
  - `unknown_ingest_rate`
  - `auto_theme_create_count`
  - `review_replay_success_rate`

### 4) 子功能分解
- `F-P2.phase3-T05-01` 门禁指标汇总器
  - 输入: phase1 指标
  - 处理逻辑: 计算入池率、自动建题材数
  - 输出: 门禁结论
  - 失败处理: 指标缺失则不允许结项
  - 可观测证据: 门禁报告
- `F-P2.phase3-T05-02` 全链路证据装配器
  - 输入: 入池、聚类、草案、审核日志
  - 处理逻辑: 归档同一批次 trace
  - 输出: phase 证据包
  - 失败处理: 证据不闭环则阻断
  - 可观测证据: 证据完整率
- `F-P2.phase3-T05-03` phase 评审归档器
  - 输入: 门禁结论与风险
  - 处理逻辑: 输出阶段评审
  - 输出: phase1 归档
  - 失败处理: 风险未裁决则不归档
  - 可观测证据: 评审纪要

### 5) 实现步骤
- Step-1: 绑定关键指标。
- Step-2: 执行 phase1 验收回放。
- Step-3: 形成归档与残留问题单。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase3-13-zero-auto-theme-create`
  - `TC-P2.phase3-14-e2e-review-chain`
  - `TC-P2.phase3-15-phase3-archive`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "unknown_event_pool|new_theme_draft|theme_merge_review|phase1" docs/project_control tmp`

### 7) 风险与回滚
- 风险:
  - 门禁只校验局部模块
- 回滚:
  - phase1 不结项，维持 `P2.phase0` 基线

### 8) 验收映射
- `ACPT-P2.phase3-006`

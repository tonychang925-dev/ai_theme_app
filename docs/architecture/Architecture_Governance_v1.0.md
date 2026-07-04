# AI Theme App Architecture Governance v1.0

> 版本：v1.0
> 日期：2026-07-04
> 状态：Stable Governance Baseline
> 适用基线：`AI_Theme_App_Overall_Architecture_v4.0.md`
> 核心原则：Governance must not become a delivery bottleneck
> 阶段定义：Architecture Graduation

---

## 0. 目的

本文件回答三个问题：

1. 谁对架构变更做最终裁决？
2. 什么类型的变更需要什么级别的审批？
3. 如何在保护 Stable Core 的同时，不拖慢 Phase 0 交付？

本文件不新增任何业务模块、Engine 或领域对象。

---

## 1. Architecture Graduation

### 1.1 定义

AI Theme App 已从“总体架构探索”进入“真实市场验证”阶段。

```text
Architecture Exploration
  -> Architecture Graduation
  -> Phase 0 Implementation
  -> Shadow
  -> Dual Layer
  -> 20 Trading-Day Validation
```

`Architecture Graduation` 表示：

- Overall Architecture v4.0 成为长期基线；
- 顶层设计停止扩展；
- 架构问题通过 ADR 处理；
- 设计质量转为由真实交易日、Replay 和 KPI 验证；
- 工作重点从“还能设计什么”转向“最小认知闭环是否有效”。

### 1.2 Graduation 与 Freeze 的关系

```text
Graduation = 项目阶段
Freeze     = 变更控制规则
```

Graduation 不取消 Freeze。Freeze 确保毕业后的架构不会重新进入无止境设计。

---

## 2. Architecture Review Board

### 2.1 定位

ARB 是轻量裁决机制，不是常设审批官僚层。

职责：

- 审核 P0 架构 ADR；
- 判断变更是否违反 Architecture Principles；
- 审核 Stable Core、Source of Truth 和 Baseline 变更；
- 决定新路径是否允许进入 Shadow/Migrating；
- 决定是否满足解除 Freeze 或发布 v5 的条件；
- 处理跨 Domain Owner 无法自行解决的冲突。

ARB 不负责：

- 审批普通代码重构；
- 审批不改变语义的 Adapter 映射；
- 审批 Notion 文案和模板微调；
- 替代 Domain Owner 做日常设计；
- 替代 QA、Risk 或 Release 门禁。

### 2.2 组成

| 角色 | 职责 | 是否常设 |
|---|---|---|
| Chief Architect | 主持裁决、维护 Principles/Baseline | 是 |
| Affected Domain Owner | 对业务语义、Source of Truth 负责 | 按范围 |
| QA / Risk | 验证回放、风险、质量与失败判定 | 是 |
| Release | 验证灰度、回滚、运行门禁 | 进入 Shadow/Migration 时 |
| Data/SRE/PM | 提供专项意见 | 按需观察 |

M4、M5、M7 等 Domain Owner 只在变更影响其 capability 时进入评审，不要求所有 Owner 参加所有决策。

### 2.3 决策权

| 决策 | 必需批准 |
|---|---|
| P0 ADR | Chief Architect + Affected Domain Owner + QA/Risk |
| Stable Core 修改 | ARB quorum，Chief Architect 必须同意 |
| Source of Truth 修改 | Chief Architect + 原/新 Domain Owner + QA/Risk |
| 进入 Shadow | Domain Owner + QA/Risk；P0 额外需要 Chief Architect |
| 进入 Migrating | Domain Owner + QA/Risk + Release |
| 解除 Freeze / 发布 v5 | 完整 ARB |
| 紧急 P0 修复 | Emergency path，事后补 ADR |

### 2.4 Quorum

普通 ARB 决策最小 quorum：

```text
Chief Architect
+ Affected Domain Owner
+ QA/Risk
```

涉及生产迁移时增加 Release。

任何角色不得由同一人在同一次 P0 变更中同时代表 Domain Owner 和 QA/Risk。

### 2.5 决策方式

默认异步：

1. ADR 提交；
2. Reviewer 在 SLA 内评论；
3. 无争议则异步批准；
4. 只有原则冲突、风险争议或 Source of Truth 争议才召开会议；
5. 结论写回 ADR。

禁止为所有 ADR 固定召开会议。

### 2.6 SLA

| 变更级别 | 首次响应 | 目标决策时间 |
|---|---:|---:|
| L0 文档勘误 | 4 工作小时 | 1 工作日 |
| L1 普通实现 | 1 工作日 | 2 工作日 |
| L2 Adapter/字段/Projection | 1 工作日 | 2 工作日 |
| L3 P0/Stable Core/SoT | 1 工作日 | 3 工作日 |
| Emergency | 30 分钟 | 按事故流程 |

Reviewer 超时自动通知备份 Reviewer，不自动视为批准。

### 2.7 Architecture Delegate

Chief Architect 可以指定临时或长期 `Architecture Delegate`，承担特定 Domain、变更类型或时间窗口内的审批职责。

授权必须书面记录：

```text
delegate
scope
allowed_decision_levels
affected_domains
valid_from
expires_at
constraints
appointed_by
```

约束：

- Delegate 只能在授权范围内审批；
- Delegate 不得再次转授权；
- Delegate 不得同时以变更作者、Domain Owner 和 Architecture Approver 三重身份批准自身变更；
- P0 变更仍需 QA/Risk 独立批准；
- Baseline 发布、Architecture Principles 修改和 Stable Core 重大变化仍由 Chief Architect 最终确认；
- Chief Architect 缺席时，可按预先登记的 Acting Chief 顺序处理 Emergency，但必须事后确认。

目的不是降低门禁，而是消除日常审批单点。

---

## 3. ADR Decision Matrix

### 3.1 风险分级

| Level | 变更类型 | 示例 |
|---|---|---|
| L0 | 无语义变化 | 拼写、链接、排版、注释 |
| L1 | 局部实现且不改契约 | 模板文案、内部重构、测试增强 |
| L2 | 兼容性扩展 | Adapter、可选字段、Projection、Evidence 映射 |
| L3 | 架构/关键语义变化 | Stable Core、Source of Truth、P0 contract、Baseline |
| Emergency | 生产 P0 事故 | 数据污染、风险门禁失效、核心链不可用 |

### 3.2 审批矩阵

| 变更 | ADR | 审批 | Shadow | Replay |
|---|---|---|---|---|
| 文档勘误 | 不需要 | Code Owner | 否 | 否 |
| 不改语义的模板调整 | 不需要 | Code Owner/Content Owner | 可选 | 内容回归 |
| 内部重构 | 简版记录 | Code Owner | 否 | 相关测试 |
| Adapter 映射扩展 | 简版 ADR/设计记录 | Domain Owner | 风险相关时 | 必须 |
| Evidence 映射修复 | Bug ADR 可选 | Domain Owner + QA | P0 时 | 必须 |
| 新增可选字段 | ADR | Domain Owner + QA | 建议 | 必须 |
| Quality Policy 调整 | ADR | Domain Owner + QA/Risk | 必须 | 必须 |
| Strategy Rule 调整 | ADR | Strategy Owner + Risk | 必须 | 必须 |
| P0 capability contract | ADR | ARB | 必须 | 必须 |
| Source of Truth 修改 | ADR | ARB | 必须 | 必须 |
| Stable Core 修改 | ADR | ARB | 必须 | 必须 |
| Baseline/Principle 修改 | ADR | Chief Architect + ARB | 必须 | 按影响 |
| 解除 Freeze / v5 | Architecture Review | 完整 ARB | 已完成 | 已完成 |

### 3.3 简版 ADR

L2 兼容性扩展可使用简版：

```text
Context
Affected Principle
Change
Compatibility
Validation
Rollback
Owner
```

不要求复制完整 P0 ADR 模板。

### 3.4 升级触发

原 L1/L2 变更满足任一条件时升级为 L3：

- 改变 Source of Truth；
- 影响 P0 capability；
- 改变 Risk Gate；
- 删除/重命名现有必填字段；
- 改变 Stable Core 生命周期；
- 无法保持向后兼容；
- 需要多个消费者同步切换；
- 回滚需要数据 migration；
- 违反或修改 Architecture Principle。

---

## 4. Governance must not become a delivery bottleneck

### 4.1 执行原则

> 严格治理结构性变化，轻量治理普通交付。

Phase 0 的唯一业务目标：

> 交付一个比当前复盘更清晰、更可解释、更有行动价值的 Notion 认知首页。

### 4.2 Phase 0 快速通道

以下变更默认不进 ARB：

- Adapter 字段映射；
- Evidence 单位/实体修复；
- Notion 模板与布局；
- EvidenceRef 展示；
- 测试、Replay 和 diagnostics；
- 不改变语义的内部重构。

它们由 Domain Owner/Code Owner 按 Decision Matrix 审批。

### 4.3 必须进入 ARB 的 Phase 0 变更

- 新增顶层 Core Object；
- 新增 Engine；
- 改变 Source of Truth；
- 让 M8 直接访问业务数据库；
- 让 M8 阻断旧复盘；
- 修改 Stable/Adaptive 边界；
- 修改 Risk Gate；
- 扩大 Phase 0 Consumer；
- 解除 Baseline Freeze。

### 4.4 WIP 限制

Phase 0 同时进行：

```text
最多 1 个 L3 Architecture ADR
最多 3 个 L2 Contract/Adapter 变更
```

超过限制时优先完成已有变更，不开启新架构讨论。

### 4.5 Governance KPI

| KPI | 目标 |
|---|---:|
| L2 平均决策时间 | `<=2 工作日` |
| L3 平均决策时间 | `<=3 工作日` |
| 因等待架构审批阻塞的 Phase 0 天数 | `<10%` |
| 无必要升级到 ARB 的变更比例 | `<10%` |
| ADR 返工次数 | 观察趋势 |
| 超时未响应 Review | `0` |

治理 SLA 连续两周期超限时，ARB 必须简化流程，而不是要求开发团队增加材料。

---

## 5. 文档分层与更新节奏

### 5.1 稳定文档

低频更新，原则上一年一次或总体版本升级时更新：

```text
Overall Architecture v4.0
Architecture Principles
Architecture Governance
ADR Index
```

### 5.2 演进文档

持续更新：

```text
ADR
Architecture Backlog
Capability Registry
Architecture KPI Report
Deprecation Register
Shadow/Migration Register
```

### 5.3 实现文档

快速迭代：

```text
Phase 0 / Phase 1 Design
M8 Implementation Detail
Notion Renderer Design
Replay Specification
Shadow Report
Test Report
Runbook
```

### 5.4 引用方向

```text
Implementation Docs
  -> reference ADR
  -> reference Stable Docs

Evolution Docs
  -> measure/record implementation

Stable Docs
  -> do not copy implementation detail
```

实现文档不得静默修改稳定语义；如发现冲突，提交 ADR。

---

## 6. ARB 运行记录

每次正式裁决记录：

```text
decision_id
adr_id
decision_date
review_level
participants
affected_principles
affected_capabilities
decision
conditions
follow_up_tasks
verification_deadline
```

建议存放：

```text
docs/project_control/reports/arb/
```

普通 L0/L1/L2 Review 不生成 ARB 会议记录，只保留 PR/ADR 审批证据。

---

## 7. Emergency Path

生产 P0 事故允许先止血：

```text
Incident Commander
+ Domain Owner
+ QA/Risk
-> temporary mitigation
```

约束：

- 不允许借紧急通道永久改变架构；
- 24 小时内补 incident record；
- 2 个工作日内补 ADR 或 rollback；
- 临时 feature flag 必须有到期时间；
- 事故结束后由 ARB 判断是否需要结构变更。

---

## 8. 下一阶段治理重点

ARB 不继续讨论新 Engine，只跟踪五件事：

1. Phase 0 是否按范围交付；
2. Replay 基准是否覆盖完整热点生命周期；
3. Architecture KPI 是否自动产出；
4. ADR-only Policy 是否进入 PR 流程；
5. 20 个真实交易日承诺是否完成。

热点生命周期基准至少包含：

```text
启动
-> 发酵
-> 加速/高潮
-> 首次分歧
-> 修复或失败
-> 退潮
-> 新方向切换
```

---

## 9. 最终治理结论

Architecture Graduation 后：

```text
Chief Architect 维护原则与基线
Domain Owner 维护业务语义
QA/Risk 维护质量与风险门禁
Release 维护灰度与回滚
ARB 只裁决高风险结构变化
```

治理的成功标准不是 ADR 数量，而是：

- P0 架构变更受控；
- 普通开发保持高效；
- Phase 0 不发生范围膨胀；
- 旧链路不被破坏；
- Market Thesis 经得起真实交易日检验。

---

## 10. Architecture Culture

团队以五句话执行架构原则：

```text
设计之前，先 Replay。
新增之前，先 Adapter。
结论之前，先 Evidence。
重构之前，先 Shadow。
修改 Baseline 之前，先 ADR。
```

Culture 用于日常判断；Principles 用于正式裁决；ADR 用于记录具体决策。

---

## 11. 治理可读性

长期治理通过两份页面保持可读：

- `Architecture_Decision_Log.md`：按时间解释项目为何演进成当前形态；
- `Governance_Health_Dashboard.md`：显示 Review、ADR、Replay、Evidence、Freeze 和 Scope 健康度。

Decision Log 只追加已生效决策；Dashboard 没有可复现数据时必须显示 `GRAY`，不得假设为健康。

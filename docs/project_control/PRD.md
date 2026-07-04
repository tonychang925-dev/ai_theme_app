# 项目需求文档（PRD）

- 项目：个人投资助理（AI Theme App）
- 文档版本：v1.0
- 状态：Draft for Review
- 编写日期：2026-02-13
- 依据文档：
  - `docs/architecture/overview.md  `
  - `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`
  - `docs/architecture/个人投资助理-项目架构设计-第二阶段.md`
  - `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
  - `docs/architecture/个人投资助理项目-前端技术设计（第四阶段）.md`
  - `docs/project_control/PLAN_WBS.md`

## 全局范围与约束

- 范围：覆盖四阶段能力闭环（题材发现 → 题材演化 → 股票融合与实时产品化 → 前端投研工作台）。
- 非范围：本 PRD 不包含具体代码实现方案与数据库迁移脚本细节。
- 全局约束：
  - 所有关键决策链路必须可追踪（`trace_id`/`decision_hash`/审计日志）。
  - 跨系统输出必须契约化并支持向后兼容（字段可增不可改语义）。
  - 阶段性发布必须经过质量门禁（测试、回放、一致性、性能指标）。
- 风险等级：整体 `High`（涉及 AI 判定、流式系统、实时行情、多端协同）。

## Change Log

- 2026-03-29
  - 新增 `Phase P2.phase0 — ThemeMatchEngine 入核与题材知识中台边界收敛`
  - 依据 `docs/architecture/个人投资助理-项目架构设计-题材匹配重构版.md` 与 `ARCH_REVIEW.md` 补充重构期需求草案
  - 明确该阶段为 Draft，当前缺少对应 `ACCEPTANCE/PHASE_CONTRACT/WBS` 正式配套，门禁状态暂不通过

## 冲突裁决说明

- 冲突 1：
  - 来源 A：重构架构文档将系统定位为“高精度裁决驱动的题材知识中台”
  - 来源 B：现有 `PLAN_WBS.md` 与 `PRD.md` 的 P1/M1-M2 约束为“不重构现有主链路前提下完成收敛”
  - 裁决：本次新增 PRD 阶段不并入 P1，单独定义为 `P2.phase0`，定位为重构首期草案

- 冲突 2：
  - 来源 A：`prd-doc` 协议要求完整映射 `PHASE_CONTRACT/ACCEPTANCE/WBS`
  - 来源 B：当前仓库中不存在 `P2.phase0` 对应的 `PHASE_CONTRACT`、`ACCEPTANCE`、`WBS`
  - 裁决：允许先形成 Draft PRD 与机器映射产物，但显式记录 gaps，并将 `gate_ready=false`

---

## 阶段 M1 — 基础认知流水线（第一阶段基线能力）

### 1. 目标（可衡量）
在不重构现有主链路前提下，建立稳定的“新闻 → 结构化事件 → 题材映射”生产链路，并满足：快速分类路径单条处理目标 <200ms、建立 76 案例测试基线、支持 major/normal/pending/decision/updates 流程闭环。

### 2. 需求（清单）
- [ ] `PRD-M1-R01` 系统必须将原始新闻写入 `news_raw`，并产出结构化 `news_event`（至少含 `event_type`、`summary`、`impact_industries`、`direction`、`confidence`）。
- [ ] `PRD-M1-R02` Model 服务必须支持“双级处理”：普通事件快速分类、重大事件深度分析；快速分类路径目标处理时延 <200ms。
- [ ] `PRD-M1-R03` Theme 服务必须消费 `stream:events:major` 与 `stream:events:normal`，并写出统一决策流 `stream:events:decision`。
- [ ] `PRD-M1-R04` normal 事件未匹配时必须进入 `stream:events:pending`，并由聚类监听流程处理。
- [ ] `PRD-M1-R05` major 事件未匹配时必须立即触发新题材创建（不得直接丢弃）。
- [ ] `PRD-M1-R06` 题材更新必须发布到 `stream:themes:updates`，并写入 `event_theme_map` 关系数据。
- [ ] `PRD-M1-R07` 新题材创建必须执行唯一性校验（分类编码+名称不可重复）。
- [ ] `PRD-M1-R08` 必须保留 76 案例评估集，并在既有 `test_theme_processor.py` 框架下可复现验证。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M1-UC01（普通事件匹配成功）
**Given**：`stream:events:normal` 收到结构化事件，题材库存在可匹配题材。  
**When**：ThemeProcessor 执行匹配流程。  
**Then**：生成 `update_theme` 决策，DecisionExecutor 更新题材并发布 `stream:themes:updates`，原消息 ACK。

#### 用例 ID: PRD-M1-UC02（普通事件未匹配进入聚类）
**Given**：`stream:events:normal` 收到事件且匹配失败。  
**When**：ThemeProcessor 完成决策类型判断。  
**Then**：事件写入 `stream:events:pending`，后续由 ClusteringListener 拉取处理。

#### 用例 ID: PRD-M1-UC03（重大事件立即建题材）
**Given**：`stream:events:major` 收到重大事件且无匹配题材。  
**When**：ThemeProcessor 走 major 未匹配分支。  
**Then**：生成 `create_new_theme` 决策并执行，产出新题材记录与事件映射。

#### 用例 ID: PRD-M1-UC04（新题材命名冲突拦截）
**Given**：创建新题材请求与现有分类编码/名称冲突。  
**When**：执行新题材创建前校验。  
**Then**：拒绝创建，记录错误原因并进入可追踪日志。

### 4. 验收标准（测试用例）
- Given 有效新闻输入，When 完成主流程，Then `news_event` 与 `event_theme_map` 必须落库成功。
- Given 普通事件输入，When 走快速分类，Then 单条处理耗时统计 P95 不高于 200ms。
- Given normal 未匹配事件，When 处理完成，Then 事件必须存在于 `stream:events:pending`。
- Given major 未匹配事件，When 处理完成，Then 必须创建新题材且有对应映射记录。
- Given 运行 76 案例评估，When 输出报告，Then 报告包含题材数量、聚类精度、归集完整性、主题分离度四项。

### 5. 非目标（排除项）
- 不包含生命周期状态机完整实现（M2 处理）。
- 不包含对外产品 API 与前端工作台（M4/M5 处理）。
- 不包含行情融合与产业链图谱（M4 处理）。

### 6. 数据示例（输入/输出）
输入（news_event）：
```json
{
  "event_id": "evt_20260213_001",
  "event_type": "policy",
  "summary": "地方发布商业航天扶持政策",
  "impact_industries": ["商业航天", "军工"],
  "direction": 1,
  "confidence": 0.86
}
```
输出（decision）：
```json
{
  "decision_id": "dec_001",
  "decision_type": "update_theme",
  "event_id": "evt_20260213_001",
  "theme_id": "theme_space_001",
  "trace_id": "trace_evt_20260213_001"
}
```

---

## 阶段 M2 — 第一阶段优化收敛与门禁（对齐 PLAN_WBS）

### 1. 目标（可衡量）
完成第一阶段稳定性收敛，使路由唯一、执行幂等、阈值动态化、回放一致，并满足关键门禁：重复写入率=0、回放一致率=100%、候选窗口稳定在 3~30。

### 2. 需求（清单）
- [ ] `PRD-M2-R01` 必须冻结统一决策契约 `DecisionEnvelope v1`，并保证必填字段覆盖率 100%。
- [ ] `PRD-M2-R02` 必须形成唯一决策路由入口，消除重复入口与行为漂移。
- [ ] `PRD-M2-R03` 必须实现幂等键策略（`event_id + action + payload_hash`），重放不得产生重复写入。
- [ ] `PRD-M2-R04` semantic matcher 必须支持事件级动态阈值（参考 p95/p98 分布），并以候选规模治理优先。
- [ ] `PRD-M2-R05` 候选治理目标范围必须控制在 3~30，且候选爆炸比低于 5%。
- [ ] `PRD-M2-R06` 高相似歧义场景必须支持二阶段 LLM 裁判（可开关、支持 shadow）。
- [ ] `PRD-M2-R07` pending 清理必须与 durable success 绑定，避免误清理导致回放漂移。
- [ ] `PRD-M2-R08` 发布前必须通过 streams + 全仓测试门禁（无开放 P0/P1 缺陷）。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M2-UC01（同事件重放幂等）
**Given**：同一 `event_id` 因重试被重复投递。  
**When**：DecisionExecutor 执行写入。  
**Then**：第二次命中幂等键，跳过重复写入并记录幂等命中日志。

#### 用例 ID: PRD-M2-UC02（动态阈值控候选）
**Given**：事件语义分布宽、全量候选过大。  
**When**：动态阈值策略执行。  
**Then**：候选集收敛到目标窗口（3~30）后再进入精排。

#### 用例 ID: PRD-M2-UC03（LLM 裁判 shadow）
**Given**：语义匹配 Top 候选分差小于歧义阈值。  
**When**：开启 shadow 裁判模式。  
**Then**：输出裁判建议与一致性评分，仅记录不改写生产结果。

#### 用例 ID: PRD-M2-UC04（回放一致性校验）
**Given**：同一批次历史消息用于 replay。  
**When**：执行回放。  
**Then**：主题状态与映射结果与基线完全一致。

### 4. 验收标准（测试用例）
- Given 运行路由扫描，When 检查处理链，Then 重复入口数必须为 0。
- Given 执行 replay 测试集，When 比对结果，Then 回放一致率必须为 100%。
- Given 动态阈值 A/B，When 对比 76 案例，Then 候选爆炸比 <5% 且精度代理指标不低于基线。
- Given 开启 LLM shadow，When 运行灰度样本，Then P95 附加时延 <800ms 且预算不超限。
- Given 发布门禁执行，When streams/tests 全量跑完，Then 无 P0/P1 未关闭问题。

### 5. 非目标（排除项）
- 不进行第二阶段 CQRS 全量改造（M3 处理）。
- 不建设面向用户的实时资讯 UI（M4/M5 处理）。

### 6. 数据示例（输入/输出）
输入（候选阈值计算）：
```json
{
  "event_id": "evt_20260213_1450",
  "similarity_distribution": {
    "p95": 0.79,
    "p98": 0.86
  },
  "target_candidate_window": [3, 30]
}
```
输出（动态阈值决策）：
```json
{
  "event_id": "evt_20260213_1450",
  "dynamic_threshold": 0.82,
  "candidate_count": 12,
  "arbiter_required": true
}
```

---

## 阶段 M3 — 题材演化引擎（第二阶段）

### 1. 目标（可衡量）
将系统从静态匹配升级为动态演化引擎，实现不可变快照、双工作副本、CQRS 分离、Stage 慢变治理与可回放审计，确保跨模式（NORMAL/SHADOW/DRY_RUN）行为可验证且可追溯。

### 2. 需求（清单）
- [ ] `PRD-M3-R01` 规则引擎输入必须为不可变 `ThemeStateSnapshot`，并附带完整性哈希（`snapshot_hash`）。
- [ ] `PRD-M3-R02` 必须分离 `SemanticWorkingCopy` 与 `RuleWorkingCopy`，禁止混写职责。
- [ ] `PRD-M3-R03` 必须落地 CQRS 三表：`theme_state`（决策态）、`theme_semantic_state`（语义态）、`theme_state_log`（审计态）。
- [ ] `PRD-M3-R04` 必须实现 Stage 跃迁守卫（合法跃迁 + 时间冷却 + 事件确认窗口）。
- [ ] `PRD-M3-R05` 必须提供 `UsageGate` 契约验证，禁止将 Stage 直接作为交易信号。
- [ ] `PRD-M3-R06` 决策必须生成 `decision_hash`，并记录 `input_snapshot_hash`，保证可回放。
- [ ] `PRD-M3-R07` 执行器必须支持 `NORMAL`、`SHADOW`、`DRY_RUN` 三模式，模式语义不可混淆。
- [ ] `PRD-M3-R08` 语义中心更新必须具备节流机制（相似度变化阈值 + 时间窗口），避免高频噪声抖动。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M3-UC01（非法 Stage 跃迁拦截）
**Given**：当前 Stage 为 `INCUBATION`，请求直接跃迁至 `PEAK`。  
**When**：TransitionGuard 校验。  
**Then**：拒绝跃迁并记录失败原因（非法路径/冷却未满足/确认不足）。

#### 用例 ID: PRD-M3-UC02（契约违规阻断）
**Given**：下游交易模块试图直接消费 Stage 字段作为买卖信号。  
**When**：UsageGate 验证。  
**Then**：抛出契约违反错误并阻断输出。

#### 用例 ID: PRD-M3-UC03（Shadow 模式执行）
**Given**：系统部署在 SHADOW。  
**When**：接收有效决策。  
**Then**：只记录日志与指标，不修改生产状态表。

#### 用例 ID: PRD-M3-UC04（回放一致性）
**Given**：存在历史 `decision_hash` + `input_snapshot_hash` 记录。  
**When**：执行同输入重放。  
**Then**：状态归约输出一致并可追溯到同一审计链。

### 4. 验收标准（测试用例）
- Given 任意规则执行，When 检查输入类型，Then 必须仅使用不可变 Snapshot。
- Given Stage 频繁波动输入，When 启用冷却和确认窗口，Then 不得出现高频抖动跃迁。
- Given 交易信号生成调用，When 仅提供 Stage，Then UsageGate 必须拒绝通过。
- Given 三模式压测，When 统计落库行为，Then SHADOW/DRY_RUN 不得污染生产决策态。
- Given 回放测试，When 使用审计日志重放，Then 重放结果与原结果一致。

### 5. 非目标（排除项）
- 不定义具体交易策略参数。
- 不承诺第三方监管报表格式（仅保证审计数据完备）。

---

## Phase `P2.phase0` — ThemeMatchEngine 入核与题材知识中台边界收敛

### 1) 目标（Objective）

在不重做现有 Redis Stream 主链路的前提下，将高精度离线题材裁决能力沉淀为线上 `ThemeMatchEngine` 首期能力，并冻结“运行时基线 / 匹配内核升级 / 题材知识扩展”三层边界。首期目标为：线上题材错配风险显著下降、匹配链路具备审计与降级能力、Unknown 输出具备统一出口，且不引入不可控主链路时延放大。

量化目标：

- 单事件匹配总时延 P95 < 1200ms
- `ThemeMatchEngine` 命中主链路覆盖率 >= 95%
- 高置信错误匹配率较现有基线下降 >= 50%
- `unknown` / `human_review` 决策具备 100% 审计字段覆盖

### 2) 范围（Scope）

In Scope：

- 将 `final_theme_matcher.py` 的核心判定逻辑抽象为线上 `ThemeMatchEngine`
- 冻结 `MATCH / UNKNOWN / HUMAN_REVIEW` 三态决策出口
- 定义首期 `ThemeProfile` 在线画像字段
- 定义匹配链路的性能预算、超时降级和审计要求
- 定义 Unknown Pool 的首期事件级输出规则
- 明确久赢复刻数据层与在线匹配画像层的边界

Out of Scope：

- 不在本阶段完成完整久赢式详情页、历史驱动、子题材树、股票图谱产品化
- 不在本阶段上线完整新题材聚类成团与自动草案创建
- 不在本阶段完成完整热度/生命周期状态机
- 不在本阶段重做现有 `ThemeProcessor/DecisionExecutor/Redis Stream` 主链路

### 3) 功能需求（Functional Requirements）

- `PRD-REQ-P2.phase0-001`
  - 描述：系统必须提供统一的 `ThemeMatchEngine` 作为唯一线上题材判定内核。
  - 触发条件：`theme_service` 消费 `events:major` 或 `events:normal` 后进入题材匹配阶段。
  - 预期行为：所有最终题材判定必须通过 `ThemeMatchEngine` 输出，不允许其他模块绕过该引擎直接落题材结果。
  - 约束：需兼容现有主链路，不得要求重做 Stream 拓扑。

- `PRD-REQ-P2.phase0-002`
  - 描述：`ThemeMatchEngine` 必须实现“召回 -> 精排/门控 -> 最终裁决”的稳定阶段化链路。
  - 触发条件：收到结构化事件输入。
  - 预期行为：至少产出候选集、门控证据、最终决策三类结构化结果。
  - 约束：首期允许使用过渡版 rerank，但阶段边界必须固定。

- `PRD-REQ-P2.phase0-003`
  - 描述：系统必须冻结三类最终决策：`MATCH(theme_id)`、`UNKNOWN`、`HUMAN_REVIEW`。
  - 触发条件：完成最终裁决。
  - 预期行为：决策结果必须显式区分“匹配成功”“未知”“需人工复核”，不得使用模糊状态。
  - 约束：决策字段必须可被 `DecisionExecutor` 消费并保留幂等能力。

- `PRD-REQ-P2.phase0-004`
  - 描述：系统必须提供首期 `ThemeProfile` 在线画像对象。
  - 触发条件：加载在线题材匹配索引时。
  - 预期行为：画像至少包含 `aliases/core_objects/entity_hints/must_terms/strong_terms/negative_terms/search_text`。
  - 约束：画像层不得直接与久赢展示层长文本详情混写。

- `PRD-REQ-P2.phase0-005`
  - 描述：系统必须定义久赢复刻数据层与在线匹配画像层的强解耦边界。
  - 触发条件：设计 `theme_master_v2/theme_profile_v2/theme_detail_snapshot` 等对象时。
  - 预期行为：展示知识对象与在线匹配画像对象必须拆层存储并可独立演进。
  - 约束：不得用一套表同时承载前端展示与在线检索索引。

- `PRD-REQ-P2.phase0-006`
  - 描述：系统必须为 `ThemeMatchEngine` 定义受控降级路径。
  - 触发条件：LLM、reranker、检索索引发生超时、不可用或结果异常。
  - 预期行为：允许降级到 `HUMAN_REVIEW` 或受控 fallback，但不得无审计地产出最终题材。
  - 约束：每次降级必须记录原因码、耗时和 `trace_id`。

- `PRD-REQ-P2.phase0-007`
  - 描述：系统必须定义 Unknown 的首期事件级输出规则。
  - 触发条件：所有候选均不满足匹配阈值，或模型明确拒识。
  - 预期行为：输出 `UNKNOWN` 并进入统一 Unknown 池，不直接创建新题材。
  - 约束：本阶段仅支持单事件级 Unknown，不要求完成聚类成团。

- `PRD-REQ-P2.phase0-008`
  - 描述：系统必须为匹配链路建立最小审计日志。
  - 触发条件：每次事件匹配执行。
  - 预期行为：记录候选、分数、门控命中、模型版本、prompt 版本、最终决策、耗时与回退原因。
  - 约束：日志必须支持按 `trace_id` 回放。

- `PRD-REQ-P2.phase0-009`
  - 描述：系统必须定义首期性能预算与容量门禁。
  - 触发条件：进入灰度或上线评审。
  - 预期行为：分别给出 retrieval、rerank、judge、total 的 P95 预算和超时阈值。
  - 约束：若任一子阶段预算持续超限，则不得全量放量。

- `PRD-REQ-P2.phase0-010`
  - 描述：系统必须定义 `P2.phase0` 的实施边界，并显式声明未纳入项。
  - 触发条件：PRD 定稿前。
  - 预期行为：清楚划分“首期入核能力”与“后续久赢式知识/产品能力”。
  - 约束：不得把完整题材知识中台能力伪装成当前一期必交付内容。

### 4) 非功能需求（NFR）

- `NFR-P2.phase0-001`
  - 性能：单事件匹配总时延 P95 < 1200ms，P99 < 2500ms。

- `NFR-P2.phase0-002`
  - 稳定性：`ThemeMatchEngine` 主链路执行成功率 >= 99%，失败时必须进入可观测降级路径。

- `NFR-P2.phase0-003`
  - 可观测性：审计字段覆盖率 100%，至少包含 `trace_id/model_version/prompt_version/final_decision/latency_ms`。

- `NFR-P2.phase0-004`
  - 兼容性：必须兼容现有 Redis Stream 与 `DecisionExecutor`，不得要求同步改造全部下游消费者。

- `NFR-P2.phase0-005`
  - 安全性：禁止在日志中写入任何密钥、完整凭证或敏感调用头。

- `NFR-P2.phase0-006`
  - 可回滚性：必须支持关闭 LLM judge 或关闭精排增强后回退到受控保守模式。

### 5) 用例（Given/When/Then）

#### 用例 ID: `PRD-UC-P2.phase0-01`
**Given**：`events:normal` 收到已结构化新闻事件。  
**When**：进入 `ThemeMatchEngine`。  
**Then**：系统按“召回 -> 精排/门控 -> 最终裁决”顺序执行，并返回结构化决策结果。

#### 用例 ID: `PRD-UC-P2.phase0-02`
**Given**：事件存在可匹配题材且主对象、关键实体和门控证据一致。  
**When**：执行最终裁决。  
**Then**：返回 `MATCH(theme_id)`，并附带候选证据和置信度。

#### 用例 ID: `PRD-UC-P2.phase0-03`
**Given**：所有候选都不满足匹配阈值。  
**When**：执行最终裁决。  
**Then**：返回 `UNKNOWN`，事件写入 Unknown 池，不直接创建新题材。

#### 用例 ID: `PRD-UC-P2.phase0-04`
**Given**：LLM judge 请求超时。  
**When**：执行受控降级。  
**Then**：系统不得直接产出未经审计的最终题材，而是进入 `HUMAN_REVIEW` 或受控 fallback 并记录原因码。

#### 用例 ID: `PRD-UC-P2.phase0-05`
**Given**：题材展示结构包含久赢风格长文详情与历史驱动。  
**When**：构建在线匹配画像。  
**Then**：系统只提取必要画像字段进入 `ThemeProfile`，不得直接把详情长文作为在线主检索对象。

#### 用例 ID: `PRD-UC-P2.phase0-06`
**Given**：灰度上线前执行门禁检查。  
**When**：验证性能与审计覆盖。  
**Then**：若任一预算或审计字段缺失不达标，则不得进入全量发布。

### 6) 验收映射（Acceptance Link）

说明：

- 当前仓库中不存在 `P2.phase0` 对应的 `ACCEPTANCE` 条目。
- 下列映射为本阶段建议验收 ID，占位用于后续补充正式 `ACCEPTANCE.md`。

- `PRD-REQ-P2.phase0-001` -> `ACPT-P2.phase0-001`
- `PRD-REQ-P2.phase0-002` -> `ACPT-P2.phase0-002`
- `PRD-REQ-P2.phase0-003` -> `ACPT-P2.phase0-003`
- `PRD-REQ-P2.phase0-004` -> `ACPT-P2.phase0-004`
- `PRD-REQ-P2.phase0-005` -> `ACPT-P2.phase0-005`
- `PRD-REQ-P2.phase0-006` -> `ACPT-P2.phase0-006`
- `PRD-REQ-P2.phase0-007` -> `ACPT-P2.phase0-007`
- `PRD-REQ-P2.phase0-008` -> `ACPT-P2.phase0-008`
- `PRD-REQ-P2.phase0-009` -> `ACPT-P2.phase0-009`
- `PRD-REQ-P2.phase0-010` -> `ACPT-P2.phase0-010`

### 7) 数据与接口样例（如适用）

输入（ThemeMatchEngine 请求）：

```json
{
  "event_id": "evt_20260329_001",
  "title": "某 AI 服务器关键部件产能扩张",
  "summary": "产业链核心厂商宣布扩产",
  "event_type": "industry",
  "entities": ["某厂商", "AI服务器"],
  "claims": ["关键部件供给能力提升"],
  "tech_terms": ["高速连接器", "服务器"],
  "trace_id": "trace_evt_20260329_001"
}
```

输出（ThemeMatchEngine 决策）：

```json
{
  "decision": "MATCH",
  "theme_id": "theme_ai_connector_001",
  "confidence": 0.91,
  "reason": "主对象、实体与题材画像高度一致",
  "evidence": {
    "theme_name_hits": [],
    "object_hits": ["高速连接器"],
    "entity_hits": ["某厂商"]
  },
  "trace_id": "trace_evt_20260329_001"
}
```

输出（Unknown）：

```json
{
  "decision": "UNKNOWN",
  "theme_id": null,
  "confidence": 0.31,
  "reason": "候选均不足以支撑稳定匹配",
  "trace_id": "trace_evt_20260329_001"
}
```

失败路径样例：

```json
{
  "decision": "HUMAN_REVIEW",
  "reason_code": "judge_timeout",
  "trace_id": "trace_evt_20260329_001"
}
```

### 8) 风险与假设（Risks/Assumptions）

- 风险等级：`P1`
- 主要风险：
  - 缺少 `P2.phase0` 对应 `ACCEPTANCE/PHASE_CONTRACT/WBS`，当前仅能形成 Draft
  - LLM/reranker 可能成为线上时延瓶颈
  - Unknown 池若缺少后续聚类治理，会形成运营积压
  - 久赢复刻数据与画像层若边界失守，会造成结构耦合

- 关键假设：
  - 现有 `ThemeProcessor/DecisionExecutor` 主链路短期保留
  - 当前离线高精度裁决方案可抽象为稳定线上组件
  - `P2.phase0` 后续会补充正式验收与 WBS

### 9) 发布与回滚约束（Release Constraints）

上线前置条件：

- `ThemeMatchEngine` 契约冻结
- 审计字段齐全
- 有明确降级路径
- 性能预算完成灰度验证
- 至少完成小规模真实流量 shadow / gated 验证

回滚触发条件：

- P95 总时延持续超过 1200ms
- 高置信错配率显著高于基线
- 审计日志缺失率 > 0
- LLM/reranker 超时导致主链路积压

### 10) 通过判定（Exit Criteria）

以下条件必须同时满足（AND）：

- `ThemeMatchEngine` 成为唯一线上题材判定内核
- 三态决策 `MATCH/UNKNOWN/HUMAN_REVIEW` 契约已冻结
- 性能预算与降级策略已通过灰度验证
- 审计日志字段覆盖率达到 100%
- Unknown 首期事件级出口已打通
- 久赢展示层与在线画像层边界文档化并落库
- `ACCEPTANCE/PHASE_CONTRACT/WBS` 已补齐并完成正式映射

在上述最后一项未满足前，本阶段 PRD 视为 `Draft for Review`，不得视为门禁通过。

### 6. 数据示例（输入/输出）
输入（Snapshot）：
```json
{
  "theme_id": "theme_ai_glasses",
  "stage": 2,
  "heat_score": 64.2,
  "momentum_score": 71.0,
  "event_count": 23,
  "snapshot_hash": "f3a91b7c1d77ab11"
}
```
输出（审计日志）：
```json
{
  "decision_hash": "6b1d6e2e8ad0c6b0f6c2f3f1be7a1c95",
  "input_snapshot_hash": "f3a91b7c1d77ab11",
  "execution_mode": "shadow",
  "transition_result": "rejected_by_cooldown"
}
```

---

## 阶段 M4 — 股票服务与实时资讯产品化（第三阶段）

### 1. 目标（可衡量）
构建面向用户的实时产品化能力，覆盖实时资讯流、盘前/盘后复盘、产业链图谱与统一输出网关，并满足：支持 5000+ 股票实时监控、3 秒采样频率约 600 QPS、行情接收至事件发布延迟 <100ms。

### 2. 需求（清单）
- [ ] `PRD-M4-R01` 必须建设实时资讯流引擎，聚合 `ThemeService`、`ModelService`、`StockService` 多源事件并去重排序。
- [ ] `PRD-M4-R02` 必须提供低延迟推送接口（WebSocket 或 SSE）输出结构化资讯条目。
- [ ] `PRD-M4-R03` 必须实现盘前/盘后复盘生成器，自动生成“盘前必读/涨停复盘/龙虎榜关联”结构化报告。
- [ ] `PRD-M4-R04` 必须新增产业链图谱数据模型（题材 → 产业链 → 环节 → 个股）及查询接口。
- [ ] `PRD-M4-R05` 必须提供统一输出网关（REST + WS），支持流式与文档式数据动静分离。
- [ ] `PRD-M4-R06` `theme_service` 必须支持增量热度更新并发布事件（如 `theme.hot`/`theme.new`）触发实时流。
- [ ] `PRD-M4-R07` 必须引入实体归一化能力，统一公司名、股票代码、产业链实体映射。
- [ ] `PRD-M4-R08` 行情网关必须支持多源适配与回退链路，异常时自动降级保证可用性。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M4-UC01（实时资讯推送）
**Given**：热点题材热度显著上升并发布 `theme.hot`。  
**When**：实时资讯流引擎消费并排序。  
**Then**：在 WebSocket 通道推送带标签和摘要的资讯卡片。

#### 用例 ID: PRD-M4-UC02（盘后复盘生成）
**Given**：交易日收盘，已获取涨停数据与题材映射。  
**When**：复盘生成任务触发。  
**Then**：输出包含“涨停家数/连板高度/龙头个股”的结构化报告。

#### 用例 ID: PRD-M4-UC03（产业链查询）
**Given**：用户请求“机器人”题材产业链。  
**When**：调用图谱查询 API。  
**Then**：返回树形结构与各环节对应股票列表。

#### 用例 ID: PRD-M4-UC04（行情源故障回退）
**Given**：首选行情数据源超时或质量校验失败。  
**When**：QuoteGateway 执行 fallback。  
**Then**：切换次优数据源继续输出标准化行情，不中断主流程。

### 4. 验收标准（测试用例）
- Given 5000 股票订阅，When 以 3 秒轮询运行，Then 系统吞吐满足约 600 QPS 且无持续积压。
- Given 实时行情触发异动，When 发布到事件总线，Then 事件发布延迟 <100ms。
- Given 任意交易日盘后任务，When 生成复盘，Then 报告包含题材维度与个股维度统计。
- Given 题材图谱查询，When 返回结果，Then 至少包含主题、链路层级、环节、股票四级数据。
- Given 多源行情故障注入，When 主源失效，Then 可自动回退且可用性不低于门禁阈值。

### 5. 非目标（排除项）
- 不包含券商交易下单链路。
- 不包含跨市场（美股/港股/期货）统一行情引擎。

### 6. 数据示例（输入/输出）
输入（实时推送条目）：
```json
{
  "feed_id": "feed_20260213_0937001",
  "event_type": "BREAKING",
  "theme_id": "theme_ai_app",
  "title": "AI 应用板块异动拉升",
  "impact_score": 83,
  "tags": ["新题材", "放量", "政策"]
}
```
输出（产业链查询响应）：
```json
{
  "theme": "机器人",
  "chains": [
    {
      "chain_name": "减速器",
      "components": [
        {
          "component_name": "谐波减速器",
          "stocks": ["688017.SH", "300024.SZ"]
        }
      ]
    }
  ]
}
```

---

## 第三阶段（P3）拆解说明

第三阶段不应被理解为单一 `phase1`。结合当前项目状态，建议将 `P3` 解释为一个完整阶段，并按以下口径拆解：

- `P3.phase0`
  - 前端统一产品出口第一版
  - 即当前历史文件与历史记录中的 `P3.phaseA`
  - 目标是收口 `frontend_bff / /api/*` 前端契约
- `P3.phase1`
  - `stock_service` 双源事实层与复盘快照
  - 目标是落地 `Tushare + JYHF`、股票事实对象、盘前必读、盘后复盘、Notion 输出基础
- `P3.phase2`
  - 复盘增强与工作台深化
  - 可包括龙虎榜、资金行为增强、个股工作台增强、`/recap` 产品化
- `P3.phase3`
  - 实时化与高级增强
  - 可包括 `SSE`、更细粒度异动监控、产业链轻图谱等

说明：

- 当前仓库已正式落地的是 `P3.phase0`，只是历史命名仍保留为 `P3.phaseA`。
- 本次新增 PRD 仅覆盖 `P3.phase1`，并不代表第三阶段只有一个子阶段。

---

## Phase P3.phase1 — Stock Service 双源事实层与复盘快照

> 状态：`历史草案（Deprecated）`  
> 生效说明：本节为早期 `P3.phase1` 草案（`PRD-REQ-P3.phase1-001~010`），仅保留审计与回溯用途；当前执行版本以文档后文 `## Phase P3.phase1 — stock_processing_service 需求收口增补（2026-04-23）` 为唯一生效基线。

### 1. 目标（Objective）
建立第三阶段首批可执行闭环：以 `Tushare + JYHF` 为双源，落地股票日频事实对象层、题材股票拼接、盘前必读/盘后复盘快照与 Notion 输出基础。要求任一交易日可完整回放，复盘快照重复生成结果一致，且不以秒级全市场实时行情作为本阶段前置门槛。

### 2. 范围（Scope）

**In Scope**
- `Tushare` 日频股票真源接入与标准化
- `JYHF` 题材事件、题材股票池与题材上下文复用
- `stock_daily_snapshot`
- `subject_stock_daily_snapshot`
- `stock_abnormal_event`
- `theme_stock_leaderboard`
- `pre_market_brief_snapshot`
- `post_market_recap_snapshot`
- `frontend_bff` 只读出口
- `notion_publisher` 报告输出基础能力

**Out of Scope**
- 秒级全市场实时行情采集与推送
- Tick 级全量行情处理
- 高频盘中策略信号引擎
- 全量资金行为分析
- 独立重型产业链图谱服务

### 3. 功能需求（Functional Requirements）

#### 3.1 历史归档清单（不纳入当前实施/验收跟踪）
> 说明：以下 `PRD-REQ-P3.phase1-001~010` 仅用于历史回溯，不进入当前执行看板、验收门禁与排期统计。

- `PRD-REQ-P3.phase1-001` 必须接入 `Tushare` 作为第三阶段首批股票日频真源，提供交易日、证券主数据、日线事实字段的标准化入库能力；触发条件为交易日同步任务执行；预期行为为按交易日产出完整可回放的股票快照；约束为外部源原始响应必须先落本地快照再入库。
- `PRD-REQ-P3.phase1-002` 必须复用 `JYHF` 作为题材事件与题材股票池真源，并将其与股票日频快照进行标准化拼接；触发条件为题材同步与股票快照同步完成；预期行为为任一股票可反查所属题材、任一题材可获取当日股票池快照；约束为不得在前端重复做“股票 -> 题材”拼接。
- `PRD-REQ-P3.phase1-003` 必须建立 `stock_daily_snapshot` 与 `subject_stock_daily_snapshot` 两类基础对象；触发条件为交易日数据入库完成；预期行为为后续状态识别、复盘和页面均只读取对象层；约束为字段语义冻结、只增不改。
- `PRD-REQ-P3.phase1-004` 必须基于日频事实对象计算 `stock_abnormal_event`，首批至少覆盖涨停、跌停、连板、龙头候选、扩散股候选；触发条件为当日快照入库后；预期行为为生成可解释的派生状态；约束为规则必须显式、可追溯，不得以黑盒评分直接替代。
- `PRD-REQ-P3.phase1-005` 必须建立 `theme_stock_leaderboard`，输出题材内股票强弱排序与龙头候选结果；触发条件为题材池与股票快照均可用；预期行为为盘后复盘和个股工作台可直接消费；约束为排序依据必须可解释且可复现。
- `PRD-REQ-P3.phase1-006` 必须建立 `pre_market_brief_snapshot`，将隔夜题材事件、重点股票观察对象和必要新闻事实汇总为盘前必读快照；触发条件为交易日上午盘前任务；预期行为为生成结构稳定、可重复发布的盘前报告；约束为报告必须基于已落库快照和事件对象，不得直接依赖外部 API 在线拼装。
- `PRD-REQ-P3.phase1-007` 必须建立 `post_market_recap_snapshot`，输出盘后题材、股票、异动、龙头与复盘结论；触发条件为收盘后批任务；预期行为为生成可供前端和 Notion 共用的复盘快照；约束为同一交易日重复生成结果一致。
- `PRD-REQ-P3.phase1-008` 必须提供 `frontend_bff` 只读出口，用于读取盘前必读、盘后复盘、题材股票榜单与股票异动对象；触发条件为前端访问；预期行为为前端只读聚合接口，不直连底层领域表；约束为字段契约冻结，禁止前端重算排序与结论。
- `PRD-REQ-P3.phase1-009` 必须提供 `notion_publisher`，将盘前必读与盘后复盘快照同步到指定 Notion 页面；触发条件为报告快照生成成功；预期行为为 Notion 内容与前端读取内容一致；约束为 Notion 作为输出层，不得反向成为业务真源。
- `PRD-REQ-P3.phase1-010` 必须明确拒绝将“秒级全市场实时行情处理”和“全量资金行为分析”作为本阶段上线门槛；触发条件为需求评审；预期行为为这些能力被标记为后续增强项；约束为不得因这两项未完成而阻塞 `P3.phase1` 上线。

### 4. 非功能需求（NFR）

- `NFR-P3.phase1-001` 任一交易日的 `stock_daily_snapshot` 与 `subject_stock_daily_snapshot` 必须支持完整回放，缺失率为 0，严重错误率为 0。
- `NFR-P3.phase1-002` 盘前必读与盘后复盘对同一交易日重复生成时，结构字段与核心排序结果一致率必须为 100%。
- `NFR-P3.phase1-003` `frontend_bff` 读取复盘快照接口在正常数据库命中情况下，P95 响应时间必须小于 800ms。
- `NFR-P3.phase1-004` `notion_publisher` 发布失败不得阻塞主业务链，必须支持失败重试并保留失败原因。
- `NFR-P3.phase1-005` 外部数据源响应必须先落本地原始快照文件，再进行标准化入库，保证可审计与可回放。

### 5. 用例（Given / When / Then）

#### 用例 ID: PRD-UC-P3.phase1-01（交易日股票快照入库）
**Given**：交易日收盘后，`Tushare` 与 `JYHF` 数据源可用。  
**When**：执行第三阶段日频同步任务。  
**Then**：生成 `stock_daily_snapshot` 与 `subject_stock_daily_snapshot`，且股票与题材可双向反查。

#### 用例 ID: PRD-UC-P3.phase1-02（盘前必读生成）
**Given**：前一晚至当日盘前的题材事件、股票观察对象和必要新闻事实已入库。  
**When**：执行盘前任务。  
**Then**：生成 `pre_market_brief_snapshot`，结构稳定且可供前端与 Notion 共用。

#### 用例 ID: PRD-UC-P3.phase1-03（盘后复盘生成）
**Given**：交易日股票快照、题材池和派生状态均已生成。  
**When**：执行收盘后复盘任务。  
**Then**：生成 `post_market_recap_snapshot`，包含题材维度与股票维度结论，且重复生成结果一致。

#### 用例 ID: PRD-UC-P3.phase1-04（前端只读聚合）
**Given**：复盘快照已生成。  
**When**：前端通过 `frontend_bff` 请求盘前或盘后报告。  
**Then**：前端获得稳定 DTO，不直接读取底层领域表，也不在前端重算排序。

#### 用例 ID: PRD-UC-P3.phase1-05（Notion 输出）
**Given**：盘前或盘后快照生成成功。  
**When**：触发 `notion_publisher` 发布。  
**Then**：指定 Notion 页面写入成功，且内容与前端读取内容一致。

### 6. 验收映射（Acceptance Link）

本节为历史草案段，验收映射已迁移至“附录 A：P3.phase1 历史映射（001~010）”。  
当前阶段门禁与验收真源以 `P3.phase1` 收口增补段（`PRD-REQ-P3.phase1-011~018`）及 `ACCEPTANCE.md` 中正式条目为准。

### 7. 数据与接口样例（如适用）

输入（盘后复盘快照简化示例）：
```json
{
  "trade_date": "2026-04-02",
  "theme_id": "theme_robotics",
  "leaderboard": [
    {
      "stock_code": "300024.SZ",
      "stock_name": "机器人示例股",
      "role": "LEADER_CANDIDATE",
      "limit_up": true,
      "chain_days": 2
    }
  ]
}
```

输出（前端读取盘后复盘）：
```json
{
  "date": "2026-04-02",
  "summary": {
    "market_bias": "RISK_ON"
  },
  "theme_reviews": [
    {
      "theme_id": "theme_robotics",
      "theme_name": "机器人",
      "leader_stock": "300024.SZ"
    }
  ]
}
```

### 附录 A：P3.phase1 历史映射（001~010）

以下映射仅用于历史回溯，不纳入当前实施门禁：

- `PRD-REQ-P3.phase1-001` -> `ACPT-P3B-001`
- `PRD-REQ-P3.phase1-002` -> `ACPT-P3B-002`
- `PRD-REQ-P3.phase1-003` -> `ACPT-P3B-003`
- `PRD-REQ-P3.phase1-004` -> `ACPT-P3B-004`
- `PRD-REQ-P3.phase1-005` -> `ACPT-P3B-005`
- `PRD-REQ-P3.phase1-006` -> `ACPT-P3B-006`
- `PRD-REQ-P3.phase1-007` -> `ACPT-P3B-007`
- `PRD-REQ-P3.phase1-008` -> `ACPT-P3B-008`
- `PRD-REQ-P3.phase1-009` -> `ACPT-P3B-009`
- `PRD-REQ-P3.phase1-010` -> `ACPT-P3B-010`

错误路径要求：
- 外部源拉取失败：任务失败并记录原因，不得写入半成品快照。
- Notion 发布失败：记录失败并重试，不得影响报告快照落库。
- 字段缺失或交易日不一致：直接拒绝入库并记录校验错误。

### 8. 风险与假设（Risks / Assumptions）

- 风险等级：`P1`

**风险**
- `Tushare` 字段权限或频次不足，导致部分增强能力延后。
- `JYHF` 与股票主数据的跨源映射存在口径差异。
- 龙头识别与异动解释性不足，容易引发“结果有但不可解释”问题。
- Notion 发布链路失败可能造成输出不一致感知。

**假设**
- `Tushare` 至少可稳定提供日频股票事实字段与交易日历。
- `JYHF` 继续提供题材事件与题材股票池。
- 盘前/盘后报告优先级高于实时推送。

### 9. 发布与回滚约束（Release Constraints）

- 上线前置条件：
  - `stock_daily_snapshot / subject_stock_daily_snapshot` 回放验证通过
  - `pre_market_brief_snapshot / post_market_recap_snapshot` 重复生成一致性验证通过
  - `frontend_bff` DTO 契约冻结
  - `notion_publisher` 失败重试与告警路径验证通过

- 回滚触发条件：
  - 任意交易日快照缺失率 > 0
  - 报告重复生成结果不一致
  - 前端与 Notion 展示内容核心字段不一致

### 10. 通过判定（Exit Criteria）

必须同时满足以下条件：

- `Tushare + JYHF` 双源日频入库稳定
- `stock_daily_snapshot / subject_stock_daily_snapshot / stock_abnormal_event / theme_stock_leaderboard` 可完整生成
- `pre_market_brief_snapshot / post_market_recap_snapshot` 可稳定生成且重复结果一致
- `frontend_bff` 与 `notion_publisher` 仅消费快照对象，不直接拼接外部源
- 本阶段未把“秒级全市场实时行情处理”和“全量资金行为分析”作为上线门槛
- 正式 `ACCEPTANCE / WBS / TEST_CASE_SPEC` 补齐前，文档状态为 Draft，`gate_ready=false`

---

## Phase P3.phase2 — 复盘增强与工作台深化

### 1. 目标（Objective）
在 `P3.phase1` 已形成股票事实对象层与基础复盘快照的前提下，补齐复盘增强能力与工作台消费层，重点覆盖龙虎榜/资金行为增强、个股工作台深化、`/recap` 页面数据契约，以及更高解释性的题材内龙头与扩散分析。要求增强能力建立在既有快照对象层之上，且不引入秒级实时行情作为前提。

### 2. 范围（Scope）

**In Scope**
- 龙虎榜结构化对象
- 资金行为增强字段与只读对象
- 龙头/前排/扩散股规则增强
- 个股工作台深化
- `/recap` 只读产品出口
- 复盘来源链与解释性增强

**Out of Scope**
- 秒级实时推送
- Tick 级盘口分析
- 高频盘中策略信号
- 完整产业链图谱服务
- 依赖高成本商业源的高级行为分析

### 3. 功能需求（Functional Requirements）

- [ ] `PRD-REQ-P3.phase2-001` 必须在 `P3.phase1` 对象层之上增加龙虎榜结构化对象，至少支持股票、上榜原因、净买入额、席位摘要等字段；触发条件为盘后增强任务；预期行为为复盘与工作台可直接消费龙虎榜对象；约束为原始来源和结构化结果必须可追溯。
- [ ] `PRD-REQ-P3.phase2-002` 必须增加资金行为增强字段，至少覆盖净流入、成交活跃度、强度分层等可解释指标；触发条件为盘后增强任务；预期行为为复盘可引用资金行为而非仅展示价格事实；约束为首批不承诺完整主力资金行为体系。
- [ ] `PRD-REQ-P3.phase2-003` 必须增强 `theme_stock_leaderboard` 规则，明确区分龙头、前排、扩散股和跟风股；触发条件为题材股票榜单计算；预期行为为同一题材内的股票角色可解释、可重放；约束为规则显式化，不得以不可解释黑盒排序替代。
- [ ] `PRD-REQ-P3.phase2-004` 必须深化个股工作台，至少聚合股票基础信息、所属题材、龙虎榜、资金行为、盘后角色标签；触发条件为访问个股页面；预期行为为前端不再自行拼装股票相关多源数据；约束为仍经 `frontend_bff` 统一出口暴露。
- [ ] `PRD-REQ-P3.phase2-005` 必须提供 `/recap` 只读产品出口，支持按交易日读取盘前必读、盘后复盘与来源链；触发条件为前端或管理端查询；预期行为为 `DailyReview` 类页面可直接消费复盘快照；约束为前端不得在页面端重算核心结论。
- [ ] `PRD-REQ-P3.phase2-006` 必须为盘后复盘输出来源链与解释性字段，至少包括股票事实来源、题材事件来源、龙虎榜/资金行为来源；触发条件为复盘快照生成；预期行为为每条关键结论均可回溯到原始证据；约束为来源链缺失的结论不得进入正式快照。
- [ ] `PRD-REQ-P3.phase2-007` 必须保持 `frontend_bff` 与 `notion_publisher` 对增强后复盘快照的兼容消费；触发条件为增强字段上线；预期行为为新字段只增不改，不破坏既有页面和 Notion 模板；约束为字段语义向后兼容。
- [ ] `PRD-REQ-P3.phase2-008` 必须明确本阶段仍不将 `SSE`、分钟级异动监控和高频实时流纳入上线门槛；触发条件为需求评审；预期行为为实时化继续后置到 `P3.phase3`；约束为不得以实时流缺失阻塞 `P3.phase2`。

### 4. 非功能需求（NFR）

- `NFR-P3.phase2-001` 龙虎榜与资金行为增强对象对同一交易日重复生成时，结构字段与关键统计结果一致率必须为 100%。
- `NFR-P3.phase2-002` 个股工作台增强接口在正常数据库命中情况下，P95 响应时间必须小于 1000ms。
- `NFR-P3.phase2-003` 复盘来源链字段覆盖率必须达到 100%，任何关键结论均需可追溯。
- `NFR-P3.phase2-004` 新增增强字段必须保持向后兼容，不得破坏 `P3.phase1` 既有 DTO。

### 5. 用例（Given / When / Then）

#### 用例 ID: PRD-UC-P3.phase2-01（龙虎榜增强复盘）
**Given**：某交易日的股票事实对象层与龙虎榜原始数据均已入库。  
**When**：执行盘后增强任务。  
**Then**：生成带龙虎榜摘要与来源链的增强复盘对象。

#### 用例 ID: PRD-UC-P3.phase2-02（个股工作台深化）
**Given**：某股票在当前交易日存在价格、题材、龙虎榜和资金行为对象。  
**When**：前端访问个股工作台。  
**Then**：通过 `frontend_bff` 返回统一股票工作台 DTO，而不是由前端拼装多源数据。

#### 用例 ID: PRD-UC-P3.phase2-03（复盘来源链回溯）
**Given**：盘后复盘快照已生成。  
**When**：读取某条复盘结论的来源链。  
**Then**：可以回溯到对应股票快照、题材事件和龙虎榜/资金行为来源。

#### 用例 ID: PRD-UC-P3.phase2-04（增强字段兼容发布）
**Given**：增强字段上线。  
**When**：旧版前端和 Notion 模板继续消费既有快照。  
**Then**：旧字段语义不变，新字段只作为增量补充，不造成兼容性破坏。

### 6. 验收映射（Acceptance Link）

当前仓库尚未存在 `P3.phase2` 的正式 `ACCEPTANCE / PHASE_CONTRACT / TEST_CASE_SPEC / WBS` 闭环，本阶段先形成 Draft PRD 合同，验收映射占位如下：

- `PRD-REQ-P3.phase2-001` -> `ACPT-P3C-001`
- `PRD-REQ-P3.phase2-002` -> `ACPT-P3C-002`
- `PRD-REQ-P3.phase2-003` -> `ACPT-P3C-003`
- `PRD-REQ-P3.phase2-004` -> `ACPT-P3C-004`
- `PRD-REQ-P3.phase2-005` -> `ACPT-P3C-005`
- `PRD-REQ-P3.phase2-006` -> `ACPT-P3C-006`
- `PRD-REQ-P3.phase2-007` -> `ACPT-P3C-007`
- `PRD-REQ-P3.phase2-008` -> `ACPT-P3C-008`

说明：
- 上述 `ACPT-P3C-*` 为待补正式验收 ID。
- 在 `ACCEPTANCE.md`、`PLAN_WBS.md`、测试计划补齐之前，本阶段 `gate_ready=false`。

### 7. 数据与接口样例（如适用）

### 7.1 2026-04-02 实施状态备注（增量）

截至 `2026-04-02`，本阶段以下主链已完成首版实现并通过真实交易日验证：

- `theme_mainline_judgement`
- `theme_cycle_judgement`
- `theme_leader_candidate`
- `pre_market_execution_plan`

并且：

- `RecapService.build_post_market_report()` 已切换为以 3 张真源表为唯一主骨架
- `RecapService.build_pre_market_report()` 已切换为以 `pre_market_execution_plan` 为唯一承接真源
- `2026-04-01` 已生成真实 `post_market` 与 `pre_market` 快照样本

当前实现口径符合本阶段收口原则：

- `每日复盘` = 真源表展示
- `盘前推荐` = 昨晚结论的次日承接验证

后续仍属于优化/收口范围的内容包括：

- 规则调优与误判样本分析
- 展示层继续贴近交易模板优化
- 正式测试规格与阶段门禁收口

### 7.2 2026-04-02 晚间阶段状态补充（增量）

截至 `2026-04-02` 晚，`P3.phase2` 已新增完成：

- `dragon_tiger_object`
  - 已完成 `Tushare top_list/top_inst` 结构化接入
  - 已完成 `2026-04-01` 真数据 smoke test
- `money_flow_enhanced`
  - 已接入龙虎榜净额与机构席位信息
  - 已完成 `2026-04-01 / 2026-04-02` 真库构建
- 个股工作台深化
  - 已聚合股票基础、题材、龙虎榜、资金行为、角色标签
- `/recap` 只读出口
  - 已完成 BFF 与前端消费
- 复盘来源链标准化
  - `theme_mainline_judgement / theme_cycle_judgement / theme_leader_candidate / money_flow_enhanced`
    已统一补齐来源链字段
- 跨交易日一致性回测
  - 已完成 `2026-04-01 / 2026-04-02`
  - 来源链覆盖率达到 `100%`

输入（增强个股工作台简化示例）：
```json
{
  "stock_id": "300024.SZ",
  "trade_date": "2026-04-02",
  "theme_roles": ["LEADER_CANDIDATE"],
  "money_flow_score": 82,
  "dragon_tiger_summary": {
    "listed": true,
    "net_buy": 180000000
  }
}
```

输出（增强复盘读取）：
```json
{
  "date": "2026-04-02",
  "stock_reviews": [
    {
      "stock_id": "300024.SZ",
      "role": "LEADER",
      "money_flow_tier": "HIGH",
      "sources": ["stock_daily_snapshot", "theme_stock_leaderboard", "dragon_tiger"]
    }
  ]
}
```

### 8. 风险与假设（Risks / Assumptions）

- 风险等级：`P1`

**风险**
- 龙虎榜与资金行为字段口径不稳定，可能导致解释冲突。
- 龙头/前排/扩散规则过于复杂时，维护成本升高。
- 个股工作台容易重新滑回“前端拼装型页面”。

**假设**
- `P3.phase1` 的股票事实对象层和复盘快照已稳定存在。
- 第三阶段第二批增强仍以日频和盘后视角为主。

### 9. 发布与回滚约束（Release Constraints）

- 上线前置条件：
  - 龙虎榜/资金行为增强对象生成稳定
  - 增强后复盘来源链覆盖率达到 100%
  - 个股工作台增强接口通过兼容性验证
  - Notion 模板兼容新增字段

- 回滚触发条件：
  - 增强字段破坏既有 DTO 兼容性
  - 复盘来源链缺失率大于 0
  - 个股工作台出现多源结果不一致

### 10. 通过判定（Exit Criteria）

必须同时满足以下条件：

- 龙虎榜与资金行为增强对象可稳定生成
- 龙头/前排/扩散规则增强可解释、可重放
- 个股工作台只读聚合能力稳定
- `/recap` 产品出口可稳定读取增强后的复盘快照
- 实时流仍明确后置到 `P3.phase3`
- 正式 `ACCEPTANCE / WBS / TEST_CASE_SPEC` 补齐前，文档状态为 Draft，`gate_ready=false`

---

## Phase P3.phase3 — 实时化与高级增强

### 1. 目标（Objective）
在 `P3.phase0 ~ P3.phase2` 已建立统一出口、双源事实对象层、复盘快照与增强工作台的基础上，补齐第三阶段的实时化与高级增强能力，重点覆盖 `SSE` 情报流、分钟级异动增强、轻量产业链视图和更高频的情报/股票联动。要求实时增强建立在既有对象层和快照链之上，不破坏前序阶段的稳定闭环。

### 2. 范围（Scope）

**In Scope**
- `/intel` 的 `SSE` 实时出口
- 分钟级异动增强
- 情报流与股票异动联动增强
- 轻量产业链视图
- 更细粒度的前端实时刷新能力

**Out of Scope**
- 秒级全市场 Tick 级行情平台
- 高频盘中策略引擎
- 重型独立产业链图谱服务
- 高成本商业数据源深度绑定

### 3. 功能需求（Functional Requirements）

- [ ] `PRD-REQ-P3.phase3-001` 必须为 `/intel` 提供 `SSE` 实时出口，用于向前端单向推送新情报项；触发条件为新情报事件或增强事件入流；预期行为为前端可在不断开现有 `REST` 兜底的情况下接收增量更新；约束为 `REST first` 现有接口必须保留作为断线恢复与回补路径。
- [ ] `PRD-REQ-P3.phase3-002` 必须增加分钟级异动增强对象，至少覆盖分钟级涨速、放量、封板/开板状态变化等可解释信号；触发条件为分钟级数据刷新；预期行为为情报流和个股工作台可消费分钟级异动；约束为分钟级异动仍建立在标准化对象层上，不得把外部源直接暴露给前端。
- [ ] `PRD-REQ-P3.phase3-003` 必须增强情报流与股票异动联动能力，使题材情报、股票异动和题材内角色变化可在同一时间流中联动展示；触发条件为新事件或新异动入流；预期行为为用户可看到“事件 -> 题材 -> 股票”的实时联动；约束为每条实时条目必须保留来源链和类型标签。
- [ ] `PRD-REQ-P3.phase3-004` 必须提供轻量产业链视图，至少支持题材 -> 环节 -> 股票的只读层级查询；触发条件为前端或工作台请求；预期行为为不引入重型图谱服务的前提下支持基础产业链查看；约束为仅基于轻量知识对象和既有题材/股票绑定，不承诺完整行业知识图谱。
- [ ] `PRD-REQ-P3.phase3-005` 必须增强前端实时刷新机制，使 `/intel`、题材工作台和个股工作台在必要时支持增量更新；触发条件为 `SSE` 推送到达；预期行为为局部刷新而不是整页重载；约束为客户端仍需保留轮询或 `REST` 补拉兜底。
- [ ] `PRD-REQ-P3.phase3-006` 必须为实时条目增加去重与优先级排序策略，至少区分题材情报、股票异动、题材角色变化三类事件；触发条件为实时事件入流；预期行为为时间流顺序稳定且高价值事件优先；约束为排序逻辑必须可解释且可调试。
- [ ] `PRD-REQ-P3.phase3-007` 必须确保实时增强不破坏前序快照闭环；触发条件为 `SSE` 或分钟级增强上线；预期行为为盘前必读、盘后复盘和前序 BFF DTO 保持稳定；约束为实时链故障不得阻塞日频快照链。
- [ ] `PRD-REQ-P3.phase3-008` 必须明确本阶段仍不承诺“全市场秒级 Tick 平台”和“高频策略引擎”上线；触发条件为需求评审；预期行为为高级实时能力继续受控收敛；约束为不得因这些能力缺失而否定 `P3.phase3` 的完成。

### 4. 非功能需求（NFR）

- `NFR-P3.phase3-001` `SSE` 情报流在正常服务状态下，新增事件到前端可见的 P95 延迟必须小于 3 秒。
- `NFR-P3.phase3-002` `SSE` 断线后客户端必须可通过既有 `REST` 接口完成回补，保证无永久性数据缺口。
- `NFR-P3.phase3-003` 分钟级异动对象对同一时间窗口重复生成时，一致率必须达到 100%。
- `NFR-P3.phase3-004` 实时链故障不得影响盘前必读、盘后复盘和日频对象层的正常生成。

### 5. 用例（Given / When / Then）

#### 用例 ID: PRD-UC-P3.phase3-01（SSE 情报推送）
**Given**：新的题材情报或股票异动事件已进入实时链。  
**When**：前端已建立 `/api/intel/stream` 连接。  
**Then**：前端收到结构化实时条目，并能保留来源链与类型标签。

#### 用例 ID: PRD-UC-P3.phase3-02（断线回补）
**Given**：前端 `SSE` 连接短暂中断。  
**When**：客户端恢复连接并通过 `REST` 请求补拉。  
**Then**：能够补齐中断期间缺失的情报条目，不出现永久缺口。

#### 用例 ID: PRD-UC-P3.phase3-03（分钟级异动联动）
**Given**：某股票在分钟级窗口内出现放量异动。  
**When**：实时链与工作台消费该事件。  
**Then**：用户可看到股票异动、所属题材和角色变化的联动展示。

#### 用例 ID: PRD-UC-P3.phase3-04（轻量产业链视图）
**Given**：某题材存在预定义的轻量产业链层级。  
**When**：前端请求产业链视图。  
**Then**：返回题材 -> 环节 -> 股票的只读结构，而不依赖重型图谱服务。

### 6. 验收映射（Acceptance Link）

当前仓库尚未存在 `P3.phase3` 的正式 `ACCEPTANCE / PHASE_CONTRACT / TEST_CASE_SPEC / WBS` 闭环，本阶段先形成 Draft PRD 合同，验收映射占位如下：

- `PRD-REQ-P3.phase3-001` -> `ACPT-P3D-001`
- `PRD-REQ-P3.phase3-002` -> `ACPT-P3D-002`
- `PRD-REQ-P3.phase3-003` -> `ACPT-P3D-003`
- `PRD-REQ-P3.phase3-004` -> `ACPT-P3D-004`
- `PRD-REQ-P3.phase3-005` -> `ACPT-P3D-005`
- `PRD-REQ-P3.phase3-006` -> `ACPT-P3D-006`
- `PRD-REQ-P3.phase3-007` -> `ACPT-P3D-007`
- `PRD-REQ-P3.phase3-008` -> `ACPT-P3D-008`

说明：
- 上述 `ACPT-P3D-*` 为待补正式验收 ID。
- 在 `ACCEPTANCE.md`、`PLAN_WBS.md`、测试计划补齐之前，本阶段 `gate_ready=false`。

### 7. 数据与接口样例（如适用）

输入（SSE 推送简化示例）：
```json
{
  "type": "stock_move",
  "occurred_at": "2026-04-02T10:15:00+08:00",
  "subject_key": "9025631",
  "stock_id": "300024.SZ",
  "title": "创新药题材内个股异动",
  "sources": ["minute_abnormal_event", "theme_stock_leaderboard"]
}
```

输出（轻量产业链视图简化示例）：
```json
{
  "theme_id": "theme_robotics",
  "chains": [
    {
      "component": "减速器",
      "stocks": ["300024.SZ", "688017.SH"]
    }
  ]
}
```

### 8. 风险与假设（Risks / Assumptions）

- 风险等级：`P1`

**风险**
- `SSE` 链路稳定性与客户端补拉策略复杂度上升。
- 分钟级异动若数据源口径不稳，容易引入噪声和误报。
- 情报流排序与去重逻辑过重时，可能重新演化成难以调试的黑盒。
- 轻量产业链视图如果真源不稳，容易被误用为正式产业链图谱。

**假设**
- `P3.phase0 ~ P3.phase2` 已稳定提供 BFF、对象层与复盘快照。
- 实时增强以 `SSE + REST` 双轨为主，不追求重型推送基础设施。

### 9. 发布与回滚约束（Release Constraints）

- 上线前置条件：
  - `/api/intel/stream` 的 `SSE` 连接与回补策略验证通过
  - 分钟级异动对象一致性验证通过
  - 实时链故障注入验证通过，且不影响日频链
  - 前端增量刷新通过兼容性验证

- 回滚触发条件：
  - `SSE` 链导致前端出现持续缺口或顺序混乱
  - 分钟级异动对象误报率超阈
  - 实时链影响盘前/盘后快照主链

### 10. 通过判定（Exit Criteria）

必须同时满足以下条件：

- `/intel` 的 `SSE` 实时出口可稳定运行
- 分钟级异动增强可解释、可重放
- 情报流与股票异动联动可用且保留来源链
- 轻量产业链视图可查询
- 实时链不破坏 `P3.phase0 ~ P3.phase2` 既有快照闭环
- 正式 `ACCEPTANCE / WBS / TEST_CASE_SPEC` 补齐前，文档状态为 Draft，`gate_ready=false`

---

## 阶段 M5 — 前端投研工作台与 DailyReview 闭环（第四阶段）

### 1. 目标（Objective）
构建桌面级、专业化、以 AI 认知为核心的投研工作台，交付可用的前端系统（题材雷达 + AI 事件流 + 行情验证三栏）与 DailyReview 页面，并冻结 V1 核心接口与数据结构，确保前后端可并行开发且字段语义稳定。该系统面向中高频投资者/研究型交易者，将 AI 事件理解能力以高密度、低噪音方式呈现，支持从「题材发现 → 逻辑理解 → 行情验证 → 决策跟踪」的完整闭环。

### 2. 范围（Scope）

**In Scope：**
- 三栏作战台布局实现：左栏题材雷达、中栏 AI 事件理解流、右栏行情验证
- 题材雷达模块：展示 AI 聚合后的题材榜单，支持多维榜单切换（挖掘/涨停/涨幅）
- AI 事件理解流：以时间轴方式呈现 AI 对市场的持续理解，支持 BREAKING/MORNING/REVIEW/LIMIT_CHAIN 事件类型
- 行情验证模块：显示与当前题材/股票相关的行情走势，用于验证逻辑是否被价格确认
- DailyReview 页面：独立一级页面，包含市场总览、核心题材复盘、资金行为、交易纪律
- 前后端 API 契约冻结：`GET /api/daily-review?date=YYYY-MM-DD` 与 `POST /api/daily-review/generate`
- 状态管理：单一真源（核心状态 `currentThemeId`，派生 `eventList/marketData`）
- 技术栈：React 18 + TypeScript, Vite, Tailwind CSS, Zustand, ECharts/TradingView
- DailyReview 到次日 Morning Brief 可追溯自动化工作流

**Out of Scope：**
- 重型 UI 组件库改造评估（不建议使用 AntD 等重型组件库）
- 移动端专属适配细节（仅桌面优先）
- 秒级全市场实时行情处理
- 高频盘中策略信号引擎
- 全量资金行为分析
- 独立重型产业链图谱服务

### 3. 功能需求（Functional Requirements）

- [ ] `FR-M5-001` 前端必须采用三栏「投研作战台」布局：左栏题材雷达区、中栏 AI 事件理解与解读区、右栏行情验证区；触发条件为用户访问投研工作台；预期行为为三个区域协同工作，界面结构直接反映投资思考路径；约束为布局必须保持高信息密度，牺牲部分美观换取决策效率。

- [ ] `FR-M5-002` 左栏题材雷达必须展示 AI 聚合后的题材榜单，支持多维榜单切换（挖掘/涨停/涨幅）；触发条件为页面加载或用户切换榜单类型；预期行为为榜单数据来源于后端 AI 输出，前端仅展示；约束为点击题材必须更新全局 `currentThemeId` 并联动中右栏数据刷新。

- [ ] `FR-M5-003` 中栏必须实现 AI 事件理解流，以时间轴方式呈现 AI 对市场的持续理解；触发条件为全局 `currentThemeId` 更新；预期行为为加载对应题材的事件流，支持事件类型 `BREAKING/MORNING/REVIEW/LIMIT_CHAIN` 的统一渲染；约束为强调结论句、数据、逻辑链的视觉突出，文本结构来源于 AI 而非前端二次解析。

- [ ] `FR-M5-004` 右栏必须实现行情验证模块，显示与当前题材/股票相关的行情走势；触发条件为全局 `currentThemeId` 更新；预期行为为加载日线/周线/月线及 MA/VOL/MACD/KDJ 等技术指标；约束为被动刷新、无复杂交互，服务于"理性制动"。

- [ ] `FR-M5-005` 状态管理必须单一真源，核心状态为 `currentThemeId`，派生状态为 `eventList/marketData`；触发条件为任何状态变更；预期行为为状态更新驱动所有相关组件一致刷新；约束为严禁多点冗余状态，避免状态漂移。

- [ ] `FR-M5-006` DailyReview 必须作为独立一级页面，至少包含：市场总览、核心题材复盘、资金与龙虎榜验证、交易原则与纪律；触发条件为用户访问复盘页面；预期行为为页面采用纵向时间流 + 模块化卡片结构，从"市场整体 → 题材 → 个股 → 原则"逐层收敛；约束为页面不追求"信息全"，而追求认知准、逻辑闭环、可复用。

- [ ] `FR-M5-007` 必须冻结 `GET /api/daily-review?date=YYYY-MM-DD` 接口契约，返回完整的 `DailyReview` 数据结构；触发条件为前端请求指定日期复盘；预期行为为返回包含 `market_summary`、`theme_reviews`、`capital_reviews`、`trading_principle` 的结构化数据；约束为字段语义不可变，只可增加不可修改。

- [ ] `FR-M5-008` 必须冻结 `POST /api/daily-review/generate` 接口契约，用于内部触发复盘生成；触发条件为管理端或 AI Agent 发起当日复盘生成；预期行为为系统生成 `DailyReview` 并记录来源依赖链；约束为普通前端用户不可见，需权限控制。

- [ ] `FR-M5-009` DailyReview 到次日 Morning Brief 必须形成可追溯自动化工作流；触发条件为次日盘前任务；预期行为为输出条目可反查到上一日复盘字段与校验结果；约束为保留完整来源链路。

- [ ] `FR-M5-010` 前端必须仅展示 AI 输出，不在前端重算排序/权重/评分；触发条件为任何数据渲染；预期行为为所有排序、权重、评分来自后端，前端是认知放大器而非决策制造者；约束为前端组件结构与后端数据模型一一对应。

- [ ] `FR-M5-011` 技术栈必须采用 React 18 + TypeScript 框架，Vite 构建，Tailwind CSS UI，Zustand 状态管理；触发条件为前端项目初始化；预期行为为支持复杂状态管理和长期可维护性；约束为不建议使用 AntD 等重型组件库，会限制密度与定制能力。

- [ ] `FR-M5-012` 必须实现核心工作流：用户进入题材库页面 → 左栏加载题材榜单 → 用户点击某一题材 → 中栏请求该题材的 AI 事件流 → 右栏加载题材/龙头对应行情；触发条件为用户操作流程；预期行为为流程顺畅，状态更新一致；约束为工作流必须反映从题材发现到行情验证的完整闭环。

### 4. 非功能需求（NFR）

- `NFR-M5-001` 性能：题材切换时中右栏数据刷新 P95 延迟 < 1000ms，页面首次加载 P95 时间 < 3000ms。
- `NFR-M5-002` 兼容性：支持 Chrome 最新版本，Safari 15+，Firefox 最新版本。
- `NFR-M5-003` 可维护性：代码必须使用 TypeScript 强类型，组件结构清晰，状态管理可预测。
- `NFR-M5-004` 安全性：前端不处理敏感逻辑，所有业务计算在后端完成，API 调用需身份验证。
- `NFR-M5-005` 可访问性：基本键盘导航支持，关键操作可通过键盘完成。
- `NFR-M5-006` 一致性：前后端字段契约必须冻结，字段只增不改，保证向后兼容。

### 5. 用例（Given / When / Then）

#### 用例 ID: UC-M5-001（三栏作战台联动）
**Given**：用户访问投研工作台页面，左栏显示题材榜单。  
**When**：用户在左栏点击题材 A。  
**Then**：全局状态更新为 `currentThemeId=A`，中栏加载题材 A 的 AI 事件流，右栏加载题材 A 的行情验证数据。

#### 用例 ID: UC-M5-002（获取指定日期复盘）
**Given**：用户访问 DailyReview 页面并选择日期 2026-04-10。  
**When**：前端调用 `GET /api/daily-review?date=2026-04-10`。  
**Then**：页面渲染该日的市场总览、核心题材复盘、资金行为、交易纪律全模块。

#### 用例 ID: UC-M5-003（内部触发复盘生成）
**Given**：管理端需要生成当日复盘报告。  
**When**：调用 `POST /api/daily-review/generate` 接口。  
**Then**：系统基于当日事件流、题材聚合、资金行为生成结构化 `DailyReview` 并记录来源依赖链。

#### 用例 ID: UC-M5-004（复盘到盘前必读闭环）
**Given**：2026-04-10 的 DailyReview 已入库。  
**When**：2026-04-11 盘前任务触发 Morning Brief 生成。  
**Then**：生成的盘前必读中每条建议均可回溯到 2026-04-10 复盘的具体字段与校验结果。

#### 用例 ID: UC-M5-005（技术栈验证）
**Given**：前端开发环境已配置。  
**When**：运行开发服务器并访问页面。  
**Then**：页面使用 React 18 + TypeScript 渲染，Tailwind CSS 提供样式，Zustand 管理状态，无 AntD 等重型组件库依赖。

### 6. 验收标准（Acceptance Criteria）

- `AC-M5-001` Given 投研工作台页面，When 用户点击左栏不同题材，Then 中栏和右栏内容必须同步更新，且仅触发一次状态变更。
- `AC-M5-002` Given 有效的日期参数，When 调用 `GET /api/daily-review?date=YYYY-MM-DD`，Then 必须返回符合 `DailyReview` 接口契约的完整数据结构。
- `AC-M5-003` Given 无权限的普通用户，When 尝试调用 `POST /api/daily-review/generate`，Then 请求必须被拒绝并返回 403 状态码。
- `AC-M5-004` Given 前端代码仓库，When 检查依赖和组件，Then 不得包含 AntD 等重型组件库，必须使用 Tailwind CSS 实现高密度界面。
- `AC-M5-005` Given 同一交易日数据，When 重复生成 DailyReview，Then 输出结果必须一致，核心字段无变化。
- `AC-M5-006` Given 题材榜单数据，When 前端渲染，Then 排序和权重必须与后端输出完全一致，前端不得进行任何重计算。
- `AC-M5-007` Given 开发完成的投研工作台，When 进行端到端测试，Then 必须支持从题材发现到行情验证的完整工作流，无断点。

### 7. 非目标（Not In Scope）
- 不包含移动端响应式设计的深度优化（桌面优先）
- 不包含多语言/国际化支持
- 不包含用户个性化主题/皮肤系统
- 不包含社交分享、评论、用户生成内容功能
- 不包含离线工作模式
- 不包含第三方登录集成（如微信、微博登录）

### 8. 数据示例（Data Examples）

#### 8.1 DailyReview API 请求/响应

请求：
```http
GET /api/daily-review?date=2026-04-10
```

响应：
```json
{
  "code": 0,
  "data": {
    "review_date": "2026-04-10",
    "market_summary": {
      "market_emotion": "NEUTRAL",
      "index_change": 0.5,
      "volume_change": 12.3,
      "ai_conclusion": "市场整体震荡，题材轮动加快"
    },
    "theme_reviews": [
      {
        "theme_id": "theme_robotics",
        "theme_name": "机器人",
        "theme_stage": "ACCELERATE",
        "theme_strength": "STRONG",
        "day_change": 3.2,
        "event_chain": [
          {
            "event_id": "evt_20260410_001",
            "event_date": "2026-04-10",
            "title": "机器人行业政策利好发布",
            "description": "工信部发布机器人产业创新发展行动计划",
            "event_level": "NATIONAL",
            "credibility": "CONFIRMED"
          }
        ],
        "sentiment_judgement": "政策驱动+资金关注，逻辑强化",
        "capital_validation": "CONFIRM",
        "leader_stocks": [
          {
            "stock_code": "300024.SZ",
            "stock_name": "机器人示例股",
            "performance": "涨停",
            "note": "龙头候选，资金大幅流入"
          }
        ]
      }
    ],
    "capital_reviews": [
      {
        "stock_code": "300024.SZ",
        "stock_name": "机器人示例股",
        "net_buy_amount": 180000000,
        "seat_type": "INSTITUTION",
        "related_theme": "theme_robotics",
        "ai_comment": "机构大幅净买入，验证题材逻辑"
      }
    ],
    "trading_principle": {
      "market_emotion": "NEUTRAL",
      "allow_trade": true,
      "focus_themes": ["机器人", "AI应用"],
      "forbidden_actions": ["冰点期追高", "无逻辑打板"],
      "ai_advice": "聚焦政策驱动题材，控制仓位，避免追高"
    }
  }
}
```

#### 8.2 题材雷达数据结构

```typescript
interface ThemeItem {
  theme_id: string;
  theme_name: string;
  rank: number;
  hit_count_day: number;
  change_percent: number;
  confidence: number;
}
```

#### 8.3 AI 事件流数据结构

```typescript
interface AIEvent {
  event_id: string;
  theme_id: string;
  event_type: string; // BREAKING/MORNING/REVIEW/LIMIT_CHAIN
  event_time: string;
  title: string;
  ai_summary: string;
  impact_score: number;
}
```

---

## 依赖与里程碑关系

- `M1 -> M2 -> M3 -> M4 -> M5`
- 关键跨阶段依赖：
  - M2 契约冻结与幂等策略是 M3 可回放能力前置条件。
  - M3 审计和契约治理是 M4/M5 面向用户输出的可信基础。
  - M4 输出网关与接口稳定性决定 M5 前端联调效率。

## 风险与缓解（摘要）

- 风险 R1：动态阈值在热点分布下失稳。
  - 缓解：profile 回退、A/B 灰度、候选窗口强约束。
- 风险 R2：LLM 裁判带来时延和成本抖动。
  - 缓解：仅歧义样本触发、shadow 先行、预算告警。
- 风险 R3：实时行情源抖动导致产品链路不稳定。
  - 缓解：多源回退、质量校验、缓存分层。
- 风险 R4：前后端字段语义漂移。
  - 缓解：V1 接口冻结、字段只增不改、契约测试。

## 发布门禁（跨阶段统一）

- 功能门禁：核心用例全部通过，关键失败路径可观测。
- 质量门禁：无开放 P0/P1 缺陷。
- 一致性门禁：回放一致率 100%。
- 性能门禁：满足阶段声明的时延/吞吐指标。
- 契约门禁：字段向后兼容，审计链完整。

---

## Phase P3.phase1 — stock_processing_service 需求收口增补（2026-04-23）

> 状态：`当前生效（Active Baseline）`  
> 生效说明：本节为 `P3.phase1` 当前唯一执行基线；`PRD-REQ-P3.phase1-011~018`、对应验收映射与门禁约束为实施与评审真源。

### 1) 目标（Objective）

在不破坏现有线上功能的前提下，建立 `stock_processing_service` 作为股票日频对象层唯一新生产链路，实现“业务与数据解耦、快照真源冻结、双轨可回滚”。

量化目标：
- `stock_processing_service` 模块内 `asyncpg/SQL/_client/_db` 违规项为 `0`。
- 双轨对账覆盖率 `100%`，核心对象一致率 `>= 99.5%`。
- 切流后 5 分钟内可一键回滚至旧链路。

### 2) 范围（Scope）

In Scope：
- 冻结 `contracts/snapshots`、`contracts/dto`、`contracts/events`。
- 冻结 `ports` 签名与 `DatabaseGateway` 股票域公开方法签名。
- 对象层按 `stock_daily_snapshot / subject_stock_daily_snapshot / stock_abnormal_event / theme_stock_leaderboard / pre_market_brief_snapshot / post_market_recap_snapshot` 执行。
- 形成 `summary + diff_samples.jsonl` 对账产物。

Out of Scope：
- 秒级全市场实时行情平台。
- 全量资金行为深度分析。
- 前端新功能扩展（仅做链路切换，不新增复杂交互）。

### 3) 功能需求（Functional Requirements）

- [ ] `PRD-REQ-P3.phase1-011` 必须将 `stock_processing_service` 定义为股票日频对象层唯一新生产链路；触发条件为 `P3.phase1` 开发；预期行为为新功能仅在该模块落地；约束为旧 `stock_service` 仅保留回退/对账/实验职责。
- [ ] `PRD-REQ-P3.phase1-012` 必须强制 `Gateway First`，所有读写通过 `database_service.DatabaseGateway` 股票域显式方法；触发条件为任一数据读写需求；预期行为为业务层不出现底层存储实现；约束为禁止调用 `_client/_db`。
- [ ] `PRD-REQ-P3.phase1-013` 必须强制 `Domain Pure`，领域层仅处理规则与评分；触发条件为领域规则实现；预期行为为领域层只收标准输入对象并输出标准结果对象；约束为禁止引入数据库/缓存/消息总线依赖。
- [ ] `PRD-REQ-P3.phase1-014` 必须冻结 6 个对象的字段级最小 schema（含主键、必填、可空、文档型标记、upsert 覆盖策略）；触发条件为程序设计前；预期行为为对象口径唯一；约束为未冻结不得开工。
- [ ] `PRD-REQ-P3.phase1-015` 必须统一事件 envelope（`event_id/event_name/trade_date/batch_id/trace_id/producer/occurred_at/payload_version/payload`）；触发条件为发布任何 stock stream 事件；预期行为为消费者可按版本稳定解析；约束为禁止私有消息格式。
- [ ] `PRD-REQ-P3.phase1-016` 必须补齐缓存失效与版本切换策略；触发条件为对象重建或题材池增量同步；预期行为为写新版本后原子切换 `current`；约束为禁止边计算边覆盖当前版本。
- [ ] `PRD-REQ-P3.phase1-017` 必须输出双轨对账产物 `summary + diff_samples.jsonl`；触发条件为每次灰度对账执行；预期行为为可定位样本级差异；约束为样本必须包含主键、旧值、新值、差异字段、差异原因分类。
- [ ] `PRD-REQ-P3.phase1-018` 必须冻结程序设计前置门禁（contracts/ports/gateway/feature-flag）；触发条件为进入编码前评审；预期行为为协议先行；约束为任一门禁未过不得进入实现阶段。

### 4) 非功能需求（NFR）

- `NFR-P3.phase1-006` `stock_processing_service` 静态扫描必须满足：`import asyncpg == 0`、SQL 字符串定义 `== 0`、`_client/_db` 访问 `== 0`。
- `NFR-P3.phase1-007` 双轨对账任务必须在单次运行结束后输出完整 JSON 结果，并保留最近 30 次运行记录。
- `NFR-P3.phase1-008` 缓存版本切换必须保证读路径无半成品窗口（原子切换）。

### 5) 用例（Given/When/Then）

#### 用例 ID: PRD-UC-P3.phase1-06（协议冻结门禁）
**Given**：准备进入 `stock_processing_service` 程序设计。  
**When**：执行门禁检查。  
**Then**：`contracts/dto`、`contracts/snapshots`、`contracts/events`、`ports`、`DatabaseGateway` 方法签名与 feature flag 全部冻结，否则阻断开发。

#### 用例 ID: PRD-UC-P3.phase1-07（双轨对账输出）
**Given**：旧链路与新链路完成同交易日运行。  
**When**：触发对账任务。  
**Then**：生成 `summary` 与 `diff_samples.jsonl`，且样本包含差异分类。

#### 用例 ID: PRD-UC-P3.phase1-08（缓存版本切换）
**Given**：交易日对象重建完成。  
**When**：执行缓存刷新。  
**Then**：先写新版本，再原子切换 `current`，读路径不出现半成品。

### 6) 验收映射（Acceptance Link）

- `PRD-REQ-P3.phase1-011` -> `ACPT-P3B-011`
- `PRD-REQ-P3.phase1-012` -> `ACPT-P3B-012`
- `PRD-REQ-P3.phase1-013` -> `ACPT-P3B-013`
- `PRD-REQ-P3.phase1-014` -> `ACPT-P3B-014`
- `PRD-REQ-P3.phase1-015` -> `ACPT-P3B-015`
- `PRD-REQ-P3.phase1-016` -> `ACPT-P3B-016`
- `PRD-REQ-P3.phase1-017` -> `ACPT-P3B-017`
- `PRD-REQ-P3.phase1-018` -> `ACPT-P3B-018`

说明：`ACPT-P3B-*` 已在 `ACCEPTANCE.md` 完成同步，作为 `P3.phase1` 正式验收 ID 使用。

### 7) 风险与假设（Risks/Assumptions）

- 风险等级：`P1`
- 风险1：协议冻结后历史脚本不兼容。缓解：旧链路保留只读回退职责。
- 风险2：灰度期差异量过大。缓解：先只切最小闭环对象，按交易日增量推进。
- 假设：`frontend_bff` 已具备 feature flag 切流能力。

### 8) 发布与回滚约束（Release Constraints）

- 上线前置：连续 5 个交易日对账达标，且 `NFR-P3.phase1-006/007/008` 全通过。
- 回滚触发：任一 P1 数据缺失、对账一致率低于阈值、BFF 读取异常持续 15 分钟。

### 9) 通过判定（Exit Criteria）

以下条件必须全部满足（AND）：
1. `PRD-REQ-P3.phase1-011~018` 全部完成并验收通过。
2. `NFR-P3.phase1-006~008` 全部通过。
3. 双轨对账报告齐全，`diff_samples.jsonl` 可追溯。
4. 回滚演练成功（5 分钟内切回）。

### 10) Change Log

- `2026-04-23`：新增 `P3.phase1` 收口增补（`PRD-REQ-P3.phase1-011~018`），将 `stock_processing_service` 的协议冻结、网关边界、缓存版本切换、事件 envelope、对账样本落盘与程序设计前置门禁纳入正式 PRD 合同。

---

## Phase M8.phase0 — Cognition Homepage

> 状态：`实施基线（2026-07-04）`
> 架构真源：`AI_Theme_App_Overall_Architecture_v4.0.md` 第 10、14、18、20 章。

### 1) 目标（Objective）

在不改变 Layer A/B/C/D、DailyReviewV2 和正式交易决策语义的前提下，使用现有盘后快照生成可回放、可追溯的认知首页，并通过 feature flag 以 Shadow 或 Notion 双层模式运行。

量化目标：

- DailyReviewV2 原字段删除或重命名数为 `0`；
- Market Thesis 核心命题 EvidenceRef 覆盖率为 `100%`；
- 认知首页业务区块不超过 `6` 个；
- M8 任一层失败时旧 Notion 报告可用率为 `100%`；
- `2026-07-02`、`2026-07-03` 及至少 5 个历史交易日可确定性 replay。

### 2) 范围（Scope）

In Scope：

- `MarketKnowledgeBundle`：只汇聚现有 producer 输出，不重算领域指标；
- `MarketEvidenceAdapter` 与版本化 `MarketEvidenceSnapshot`；
- `CLOSE` 类型、带版本的 `MarketContextSnapshot`；
- 固定模板的最小 `CognitionState`、Belief 与 Hypothesis；
- 结构化 `MarketThesisSnapshot`；
- Shadow replay 与差异诊断；
- `legacy_only / cognition_shadow / dual_layer` 三种 Notion 渲染模式；
- Thesis 首页 + 原证据章节的双层报告。

Out of Scope：

- 自动 World Model 学习；
- 动态 Goal Manager 或 Attention Engine；
- Counterfactual 因果推断；
- 多策略选择与正式交易决策变更；
- Self Reflection、Episodic Retrieval；
- DailyReviewV3；
- 8002/8003 或其他已废弃服务的启动与依赖。

### 3) 功能需求（Functional Requirements）

- [ ] `PRD-REQ-M8.phase0-001` 当盘后 `recap_doc` 可用时，系统必须构建版本化 `MarketKnowledgeBundle`；Bundle 只保留 producer 输出、lineage、coverage 和 quality，不允许重算 ThemeCycle、Mainline、StrongStock 或交易结论。
- [ ] `PRD-REQ-M8.phase0-002` `MarketEvidenceAdapter` 必须把 Bundle 映射为不可变 Evidence Snapshot；所有判断性字段必须包含 `EvidenceRef`，缺失字段必须记录 coverage/quality，不得用 `0`、`--` 或自由文本伪装有效事实。
- [ ] `PRD-REQ-M8.phase0-003` Context、Cognition 与 Thesis 必须使用固定模板从 Evidence 构建；Context 类型固定为 `CLOSE`，Thesis 核心命题必须可追溯，Hypothesis 必须包含 deadline 与 falsifier。
- [ ] `PRD-REQ-M8.phase0-004` Shadow replay 必须读取已有快照，不访问新的数据库 Gateway、不回写 M1～M7 真源、不改变正式 Decision；相同输入和 policy version 必须产生相同内容 hash。
- [ ] `PRD-REQ-M8.phase0-005` Notion 必须支持 `legacy_only`、`cognition_shadow`、`dual_layer`；`dual_layer` 在原证据章节前最多插入 6 个认知区块，认知链失败时必须自动回退原报告，禁止发布空认知首页。
- [ ] `PRD-REQ-M8.phase0-006` 认知正文不得出现内部状态码、无来源结论或重复章节摘要；无足够证据时必须显示“无法判定”或省略命题。

### 4) 非功能需求（NFR）

- `NFR-M8.phase0-001` 同输入、同 schema/policy version 的 Evidence、Context、Thesis 内容 hash 必须一致。
- `NFR-M8.phase0-002` M8 模块不得导入数据库 Gateway、Redis client 或 Notion client。
- `NFR-M8.phase0-003` Phase 0 核心持久化契约不超过 5 个，新增核心 Job 不超过 1 个，正式策略新增为 0。
- `NFR-M8.phase0-004` 所有失败必须输出结构化 diagnostics，禁止 `except: pass`。
- `NFR-M8.phase0-005` Phase 0 不启动或探测端口 8002/8003。

### 5) 用例（Given/When/Then）

#### `PRD-UC-M8.phase0-01` — Evidence 映射

Given：存在结构化 DailyReviewV2/recap snapshot。
When：构建 Bundle 与 Evidence Snapshot。
Then：输出稳定 ID/hash、producer lineage、coverage、quality；缺失资金字段不会被映射为零资金。

#### `PRD-UC-M8.phase0-02` — Thesis Shadow

Given：存在 Evidence Snapshot，且 Context/Cognition 固定 policy 可用。
When：执行 `M8.phase0` replay。
Then：生成不超过 6 个首页区块；每个核心命题存在 EvidenceRef；不修改正式 Decision。

#### `PRD-UC-M8.phase0-03` — Notion 双层与回退

Given：渲染模式分别为 `legacy_only`、`cognition_shadow`、`dual_layer`。
When：构建 Notion blocks。
Then：旧模式输出保持不变；Shadow 不发布 Part A；Dual Layer 先输出 Thesis 再输出完整证据；认知输入非法时回退旧报告。

#### `PRD-UC-M8.phase0-04` — 历史回放

Given：7/2、7/3 和至少 5 个历史交易日快照。
When：连续执行两次 replay。
Then：逐层 hash 一致、未来数据泄漏为 0、unsupported claim 为 0。

### 6) 验收映射（Acceptance Link）

- `PRD-REQ-M8.phase0-001` -> `ACPT-M8P0-001`
- `PRD-REQ-M8.phase0-002` -> `ACPT-M8P0-002`
- `PRD-REQ-M8.phase0-003` -> `ACPT-M8P0-003`
- `PRD-REQ-M8.phase0-004` -> `ACPT-M8P0-004`
- `PRD-REQ-M8.phase0-005` -> `ACPT-M8P0-005`
- `PRD-REQ-M8.phase0-006` -> `ACPT-M8P0-006`

### 7) 数据与接口样例

```json
{
  "schema_version": "market_thesis.v1",
  "trade_date": "2026-07-03",
  "primary_thesis": {
    "statement": "机器人修复假设失败，资金关注转向容量方向。",
    "evidence_refs": ["ev:theme:robot:cycle", "ev:capital:pcb:institution"]
  },
  "invalidation_conditions": ["机器人核心载体重新获得资金与广度确认"]
}
```

### 8) 风险与假设（Risks/Assumptions）

- 风险等级：`P0`，原因是 Notion 复盘属于业务关键消费者。
- 风险：当前快照字段存在缺失和历史兼容分支。缓解：Adapter 显式 coverage/quality，缺失不补结论。
- 风险：旧发布器已有未提交重构。缓解：Adapter over Rewrite，只在新 renderer 前增加可关闭的认知层。
- 假设：`post_market_recap_snapshot` 已保存可回放的 `recap_doc`。

### 9) 发布与回滚约束（Release Constraints）

- 默认 `M8_NOTION_RENDER_MODE=legacy_only`；
- 先 Evidence Shadow，再 Cognition Shadow，最后才允许 `dual_layer`；
- 任一 P0 unsupported claim、旧证据章节减少或正式 Decision 漂移立即回滚到 `legacy_only`；
- 回滚不删除快照，只关闭 feature flag。

### 10) 通过判定（Exit Criteria）

以下条件必须全部满足（AND）：

1. `ACPT-M8P0-001~006` 全部通过；
2. UT -> IT -> Replay/E2E 按顺序通过；
3. 7/2、7/3 和至少 5 个历史交易日 replay 产物完整；
4. 原 DailyReviewV2 契约测试通过；
5. 无开放 P0/P1 缺陷；
6. Phase 0 阶段报告进入人工验收。

### 11) Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决 |
|---|---|---|---|
| 早期 M8 文档把 Phase 0 定义为直接改写报告 | Overall Architecture v4.0 | M8 v1.3 第 22 章早期分期 | v4.0 是冻结 Baseline；采用只读编排、Shadow、Dual Layer |
| DailyReviewV2 是否立即扩展 cognition | Overall Architecture v4.0 第 18/57 章 | 直接创建 DailyReviewV3 | Phase 0 使用独立快照与渲染聚合，不破坏 V2 |

### 12) Change Log

- `2026-07-04`：冻结 `M8.phase0` Cognition Homepage 需求，禁止引入 Adaptive Layer。

---

## Phase M8.phase1 — Cognitive Validation

> 状态：`实施中（2026-07-04）`

### 1) 目标（Objective）

建立 `Yesterday Hypothesis -> Eligibility -> Reviewer Verdict -> Ground Truth -> Replay` 的认知验证闭环，为后续 Belief/Learning 提供 Ground Truth。

量化目标：

- Validation Record 必填字段完整率 `100%`；
- 未来数据泄漏 `0`；
- `NO/PARTIAL/UNVERIFIABLE` 失败原因完整率 `100%`；
- Binary Accuracy、Brier Score、ECE、Timing Offset 可确定性复算；
- 首轮连续 20 个交易日验证，长期累计 100 个交易日。

### 2) 范围（Scope）

In Scope：

- `MarketThesisValidationRecord` 不可变契约；
- eligible `HypothesisState` 的 append-only source freeze；
- Observation/Assessment/Hypothesis 语义边界与 Eligibility Gate；
- `YES/NO/PARTIAL/UNVERIFIABLE` 验证标签；
- 标准失败分类；
- Append-only Dataset Writer；
- Dataset Manifest Integrity 扫描与校验；
- Binary Accuracy、Brier Score、ECE、Timing Offset；
- Yesterday Thesis 与 Today Evidence 的时点守卫和 replay；
- 20 日试运行与 100 日数据集积累。

Out of Scope：

- Belief 更新；
- Learning、Memory、World Model 更新；
- 多 Hypothesis 竞争；
- 自动交易决策变更；
- 用 LLM 自动生成 Ground Truth。

### 3) 功能需求（Functional Requirements）

- [ ] `PRD-REQ-M8.phase1-001` 系统必须先 append-only 冻结 eligible `HypothesisState`，再生成不可变 Validation Record；Record 包含 trade_date、source/reality hashes、`prediction_probability`、`source_quality_score`、verification、reason、time、outcome 和 EvidenceRef。两种数值必须独立存储，Reviewer 不得事后修改 probability。
- [ ] `PRD-REQ-M8.phase1-002` 验证标签必须限制为 `YES/NO/PARTIAL/UNVERIFIABLE`；非 YES 必须记录合法 failure type，证据不足不得计为 NO。
- [ ] `PRD-REQ-M8.phase1-003` Yesterday Thesis 的 `as_of` 必须早于 Today Reality 的 `available_at`；任何未来数据污染必须 fail fast。
- [ ] Observation、Assessment、Primary Narrative 或缺少 deadline/probability/expected observations/falsifiers/EvidenceRefs 的命题必须在 Dataset 写入前拒绝。
- [ ] Hypothesis deadline 必须来自既有 Trade Calendar Producer；禁止使用 `trade_date + 1自然日` 推算。
- [ ] `PRD-REQ-M8.phase1-004` Dataset Writer 必须 append-only、幂等且可按 record hash 重放；重复写相同记录跳过，冲突记录拒绝覆盖；派生 Manifest 必须校验记录数与聚合 hash。
- [ ] `PRD-REQ-M8.phase1-005` 指标服务必须输出 Binary Accuracy、Brier Score、ECE 与 Timing Offset，并明确排除 UNVERIFIABLE 的统计口径。
- [ ] `PRD-REQ-M8.phase1-006` 20 日验证期间不得写入 Belief/Learning，也不得改变正式 Decision。

### 4) 验收映射

- `PRD-REQ-M8.phase1-001` -> `ACPT-M8P1-001`
- `PRD-REQ-M8.phase1-002` -> `ACPT-M8P1-002`
- `PRD-REQ-M8.phase1-003` -> `ACPT-M8P1-003`
- `PRD-REQ-M8.phase1-004` -> `ACPT-M8P1-004`
- `PRD-REQ-M8.phase1-005` -> `ACPT-M8P1-005`
- `PRD-REQ-M8.phase1-006` -> `ACPT-M8P1-006`

### 5) 通过判定

以上 6 项全部通过，且完成连续 20 个真实交易日验证。100 日是长期数据资产目标，不阻塞工程能力交付。

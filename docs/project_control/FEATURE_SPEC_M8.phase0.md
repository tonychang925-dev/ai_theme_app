# FEATURE SPEC — M8.phase0

## 0. 实施边界

- 架构真源：Overall Architecture v4.0。
- 核心实现顺序：Contracts/Knowledge/Evidence -> Context/Cognition/Thesis -> Replay/Notion -> 阶段回归。
- M8 只读现有 payload，不拥有数据库、Redis、Notion 或领域指标计算。
- 默认 feature flag 为 `legacy_only`，Phase 0 禁止 `cognition_primary`。

## Task `M8.phase0-T01` — Stable Core Contracts、Knowledge 与 Evidence

### 1) 目标与边界

- 目标：建立版本化不可变契约，并将现有 `recap_doc` 无重算映射为 Bundle/Evidence。
- 非目标：不重判周期、主线、强势股、资金或交易权限。

### 2) 子功能分解

#### `F-M8P0-T01-01` Canonical Contract

- 输入：trade_date、as_of、schema version、结构化字段。
- 处理：定义 frozen/slots dataclass 与 canonical hash。
- 输出：稳定 ID、schema_version、content_hash。
- 失败处理：非 JSON 可序列化值或非法日期抛出明确错误。
- 可观察证据：对象 ID/hash 与 schema version。

#### `F-M8P0-T01-02` MarketKnowledgeBundle

- 输入：现有 `recap_doc`。
- 处理：深拷贝允许模块，记录 producer、coverage 与 quality；不计算新指标。
- 输出：`MarketKnowledgeBundle`。
- 失败处理：空 payload 返回 invalid diagnostics，不伪造 Bundle。
- 可观察证据：module coverage、missing modules、bundle hash。

#### `F-M8P0-T01-03` MarketEvidenceAdapter

- 输入：Bundle。
- 处理：把结构化结论映射为带 source path 的 EvidenceItem/EvidenceRef。
- 输出：`MarketEvidenceSnapshot`。
- 失败处理：缺失模块记 missing；禁止映射默认 0。
- 可观察证据：evidence count、reference coverage、quality score。

### 3) 接口与契约

- `MarketKnowledgeBundleBuilder.build(payload, trade_date, as_of=None)`
- `MarketEvidenceAdapter.build(bundle)`
- 相同输入与显式 as_of 必须幂等。

### 4) 状态、兼容与错误

- 无持久化表、无状态写入。
- 输入 `recap_doc` 不得被修改。
- 错误使用 `MarketCognitionContractError`，禁止静默吞掉。

### 5) 测试

- `TC-M8P0-T01-01`、`TC-M8P0-T01-02`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_knowledge_evidence.py`

### 6) 风险与回滚

- 风险：字段漂移。缓解：Adapter allowlist + coverage。
- 回滚：删除新模块即可，旧链无引用。

### 7) 验收映射

- `PRD-REQ-M8.phase0-001/002`
- `ACPT-M8P0-001/002`

## Task `M8.phase0-T02` — CLOSE Context、Cognition 与 Thesis

### 1) 目标与边界

- 目标：用固定 policy 生成最小认知闭环。
- 非目标：不实现动态 Goal/Attention、学习或多策略。

### 2) 子功能分解

#### `F-M8P0-T02-01` CLOSE Context Builder

- 输入：Evidence Snapshot。
- 处理：提取 prior state、主线变化、冲突和资本背景；context version 固定从 1 开始。
- 输出：`MarketContextSnapshot`。
- 失败处理：关键 Evidence 不足时标记 insufficient。
- 可观察证据：context ID、evidence refs、quality。

#### `F-M8P0-T02-02` Fixed Cognition Policy

- 输入：Context + Evidence。
- 处理：更新最小 Belief/Hypothesis；Hypothesis 强制 deadline/falsifier。
- 输出：`CognitionState`。
- 失败处理：无依据 proposition 不进入 state。
- 可观察证据：belief/hypothesis refs 与 policy version。

#### `F-M8P0-T02-03` Market Thesis Builder

- 输入：Cognition + Evidence。
- 处理：生成 primary thesis、scenario、invalidation 与交易权限视图。
- 输出：`MarketThesisSnapshot`。
- 失败处理：无核心 refs 时状态 unavailable，不生成 ready thesis。
- 可观察证据：claim/ref coverage、unsupported count、thesis hash。

### 3) 接口与契约

- `MarketContextBuilder.build(evidence)`
- `FixedCognitionPolicy.evaluate(evidence, context)`
- `MarketThesisBuilder.build(evidence, context, cognition)`

### 4) 状态、兼容与错误

- Phase 0 Cognition 仅为单次构建状态，不做跨日 mutable store。
- 展示文本必须中文化，不暴露内部枚举。

### 5) 测试

- `TC-M8P0-T02-01`、`TC-M8P0-T02-02`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_cognition.py`

### 6) 风险与回滚

- 风险：模板过度推断。缓解：EvidenceRef 强制与 fail closed。
- 回滚：关闭 cognition shadow，不影响 Bundle/Evidence。

### 7) 验收映射

- `PRD-REQ-M8.phase0-003`
- `ACPT-M8P0-003`

## Task `M8.phase0-T03` — Shadow Replay

### 1) 目标与边界

- 目标：从调用方提供的历史 snapshot payload 确定性重放全部 Stable Core。
- 非目标：M8 内部不查询存储、不回写快照。

### 2) 子功能分解

#### `F-M8P0-T03-01` Replay Orchestrator

- 输入：trade_date、snapshot payload。
- 处理：顺序调用 Bundle -> Evidence -> Context -> Cognition -> Thesis。
- 输出：逐层 ID/hash 和 preview。
- 失败处理：任一层失败即停止下游，返回 failed stage。
- 可观察证据：stage、duration、hash chain。

#### `F-M8P0-T03-02` Quality Diagnostics

- 输入：各层 quality/coverage。
- 处理：汇总 missing modules、ref coverage、unsupported claims。
- 输出：Replay diagnostics。
- 失败处理：quality 不足不标 ready。
- 可观察证据：quality metrics。

#### `F-M8P0-T03-03` Decision Isolation

- 输入：原 payload。
- 处理：构建前后计算 existing decision canonical hash。
- 输出：decision_unchanged。
- 失败处理：hash 变化立即失败。
- 可观察证据：before/after hash。

### 3) 接口与契约

- `MarketCognitionReplay.run(payload, trade_date, as_of=None)`
- 执行模式：`execution_mode=real`；`allow_mock=false`。
- 关键依赖：调用方提供的真实历史 snapshot fixture。

### 4) 状态、兼容与错误

- Replay 无副作用。
- 空输入、非法日期、缺核心 evidence 返回结构化失败。

### 5) 测试

- `TC-M8P0-T03-01`、`TC-M8P0-T03-02`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/integration/test_m8_phase0_replay.py`

### 6) 风险与回滚

- 风险：历史 schema 不一致。缓解：Adapter coverage 与 schema diagnostics。
- 回滚：停止 replay job，无生产数据变更。

### 7) 验收映射

- `PRD-REQ-M8.phase0-004`
- `ACPT-M8P0-004`

## Task `M8.phase0-T04` — Notion Dual Layer

### 1) 目标与边界

- 目标：把 ready Thesis 作为 Part A 前置到现有 renderer，保留完整 Part B。
- 非目标：不改写原证据 renderer。

### 2) 子功能分解

#### `F-M8P0-T04-01` Render Mode Resolver

- 输入：显式参数或 `M8_NOTION_RENDER_MODE`。
- 处理：只接受 `legacy_only/cognition_shadow/dual_layer`。
- 输出：有效模式。
- 失败处理：非法值 fail closed 到 legacy_only 并记录原因。
- 可观察证据：render_mode、fallback_reason。

#### `F-M8P0-T04-02` Thesis Part A Renderer

- 输入：ready Thesis。
- 处理：渲染最多 6 个语义区块，去内部状态码。
- 输出：Notion blocks。
- 失败处理：引用不完整不渲染 Part A。
- 可观察证据：semantic section count、claim/ref coverage。

#### `F-M8P0-T04-03` Dual Layer Composer

- 输入：Part A 与现有 legacy blocks。
- 处理：dual_layer 时 `A + divider + B`；shadow/legacy 只返回 B。
- 输出：最终 blocks。
- 失败处理：Part A 异常返回原 B，禁止空首页。
- 可观察证据：fallback_used、legacy block fingerprint。

### 3) 接口与契约

- `NotionPostMarketRecapPublisher.build_blocks(payload, trade_date, render_mode=None)`
- 不允许 `cognition_primary`。

### 4) 状态、兼容与错误

- `legacy_only` 输出必须与当前 renderer 完全一致。
- cognition 可从 payload 的独立 `market_cognition` 读取，不扩展 DailyReviewV2。

### 5) 测试

- `TC-M8P0-T04-01`、`TC-M8P0-T04-02`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_notion_dual_layer.py`

### 6) 风险与回滚

- 风险：旧页面结构变化。缓解：legacy fingerprint regression。
- 回滚：`M8_NOTION_RENDER_MODE=legacy_only`。

### 7) 验收映射

- `PRD-REQ-M8.phase0-005`
- `ACPT-M8P0-005`

## Task `M8.phase0-T05` — 七日 Gate 与阶段报告

### 1) 目标与边界

- 目标：固化七日 replay、兼容回归和质量汇总。
- 非目标：不开始 20 日自动学习。

### 2) 子功能分解

#### `F-M8P0-T05-01` Seven-day Corpus

- 输入：7/2、7/3 和至少 5 个历史 snapshot fixture。
- 处理：逐日 replay。
- 输出：按日 hash/quality 结果。
- 失败处理：少于 7 日阻断 Gate。
- 可观察证据：corpus manifest。

#### `F-M8P0-T05-02` Compatibility Regression

- 输入：现有 DailyReviewV2/Notion tests。
- 处理：运行回归并对比 legacy blocks。
- 输出：零破坏结论。
- 失败处理：任一旧测试失败阻断。
- 可观察证据：pytest/junit。

#### `F-M8P0-T05-03` Phase Report

- 输入：测试与 replay 产物。
- 处理：汇总范围、变更、命令、结果、风险。
- 输出：`phase-M8.phase0.md`。
- 失败处理：证据缺失不得进入验收。
- 可观察证据：报告与 gate decision。

### 3) 接口与契约

- 只生成测试/报告产物，不新增生产接口。

### 4) 状态、兼容与错误

- 任务状态以 Notion 全量对账为准。

### 5) 测试

- `TC-M8P0-T05-01`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/integration/test_m8_phase0_replay.py stock_processing_service/tests/unit/test_post_market_daily_review_v2_builder.py stock_processing_service/tests/unit/test_notion_post_market_recap_publisher.py`

### 6) 风险与回滚

- 风险：历史样本不足。缓解：明确 BLOCKED，不使用合成结果冒充验收。
- 回滚：保持任务 In review，不提升 render mode。

### 7) 验收映射

- `PRD-REQ-M8.phase0-006`
- `ACPT-M8P0-006`

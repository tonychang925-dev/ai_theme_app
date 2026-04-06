---
name: feature
description: 功能开发设计技能，用于将PRD需求转化为每个任务的详细功能设计，包括接口设计、数据模型设计、错误处理和回滚方案等。
model: gpt-5
---

# Feature 技能协议（生产级合约模式，中文版）

该技能用于把 PRD/WBS 任务转化为“可实施、可测试、可回滚”的功能设计合约。

统一约束清单（跨技能一致）：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

原则：
- 不写空泛设计
- 不做不可验证承诺
- 每个功能设计必须映射测试与验收
- 先定义核心组件实现任务，再定义测试框架
- 测试设计不得替代核心组件重构任务分解

---

## 0. 输入要求（MUST）

至少具备：
- `Phase` 编码（如 `P1.phase0`）
- 任务 ID（如 `P1.phase0-T01`）
- `docs/project_control/PRD.md`
- `docs/project_control/PLAN_WBS.md`
- `docs/project_control/ACCEPTANCE.md`
- 相关架构文档（`docs/architecture/*`）

输入优先级：
1. 用户最新明确指令
2. `PHASE_CONTRACT*`
3. `ACCEPTANCE.md`
4. `PRD.md`
5. `PLAN_WBS.md`
6. `docs/architecture/*`

冲突时：
- 必须给出“冲突裁决说明”
- 未裁决前不得定稿

---

## 1. 输出产物（MUST）

必须生成：
1. `docs/project_control/FEATURE_SPEC_<phase>.md`
2. `tmp/feature_traceability_<phase>.json`
3. `tmp/feature_validation_report_<phase>.json`

说明：
- `FEATURE_SPEC_<phase>.md`：任务级功能设计文档（人类可读，按阶段隔离）
- `feature_traceability_<phase>.json`：任务到实现/测试/验收映射（机器可读）
- `feature_validation_report_<phase>.json`：结构化自检与门禁结果
- `phase` 示例：`P1.phase1`。
- 禁止仅输出不带 phase 后缀的通用文件名作为唯一产物。

---

## 2. FEATURE_SPEC 固定结构（MUST）

每个任务必须包含：

### Task `<task_id>` — `<name>`

#### 1) 目标与边界
- 目标（可量化）
- 非目标（明确不做）

#### 2) 接口与契约
- 输入/输出
- 参数约束与错误码
- 幂等、重试、超时策略

#### 3) 数据模型与状态变更
- 涉及表/字段/索引（如有）
- 状态机流转规则
- 迁移与兼容策略

#### 4) 实现步骤（最小可执行序列）
- Step-1..N（每步必须可验证）

#### 5) 测试设计与命令
- 对应测试用例 ID（如 `TC-*`）
- 必跑命令（含预期结果）
- 失败时定位入口

#### 6) 风险与回滚
- 失败模式
- 缓解策略
- 回滚触发条件与操作

#### 7) 验收映射
- 必须映射到 `ACPT-*`

### 2.2 核心实现优先规则（新增，MUST）

当需求涉及架构重构、主链路迁移、模型服务接入、消息流改造或核心算法升级时，`FEATURE_SPEC` 必须先输出“核心组件代码实现任务分解”，再输出测试框架设计。

强制要求：

- 必须先拆出核心组件实现任务，例如：
  - 组件/模块重构任务
  - 新门面/适配层任务
  - Prompt/Schema/DTO 重建设计
  - 主链路处理器改造
  - 数据落库与消息协议改造
- 禁止只产出测试脚本、测试框架、测试规范，而缺失对应核心组件的实现任务。
- 若测试框架依赖某核心组件重构完成，必须在任务依赖里显式写出：
  - `核心组件实现 -> 单元测试 -> 集成测试 -> 全链路测试`
- 对每个核心组件，必须明确：
  - 目标文件
  - 待新增/修改的类与方法
  - 待删除/退役的旧逻辑
  - 输入输出契约
  - 实现顺序依赖

判定为不合格设计的情况：

- 只有测试任务，没有核心实现任务；
- 只有“重构某组件”一句话，没有方法级实现拆解；
- 先写 E2E 测试，再补核心组件任务；
- 用测试框架补位替代核心实现设计。

### 2.1 功能分解深度规则（新增，MUST）

每个 `Task` 必须新增 `子功能分解` 小节，且满足：

- 至少拆分为 `3` 个可执行子功能点（建议命名：`F-<task>-01...N`）。
- 每个子功能点必须包含：`输入`、`处理逻辑`、`输出`、`失败处理`、`可观测证据`。
- 子功能点必须能映射到至少一个 `TC-ID` 与一个验收条款（`ACC/ACPT`）。
- 禁止“一个任务只写一段概述”后直接进入实现步骤。

推荐模板：

```text
F-P1.phase1-T04-01 分类优先未匹配分支识别
- 输入: normal 事件消息
- 处理: 分类推断与分类内匹配失败判定
- 输出: decision_type=no_match_*
- 失败处理: 异常写 dead-letter
- 可观测证据: category_inferences/category_not_matched 指标
```

---

## 3. 质量规则（MUST）

每个任务设计必须满足：
1. 具体（含阈值/字段/命令）
2. 可实施（存在最小执行步骤）
3. 可验证（有测试命令与期望）
4. 可回滚（有明确触发条件）
5. 可追踪（映射任务/验收/测试）
6. 可分解（存在满足 `2.1` 的子功能分解）

禁止：
- “优化一下”“按最佳实践实现”这类空泛语句
- 缺少失败路径与回滚策略

---

## 4. 追踪映射（MUST）

`tmp/feature_traceability_<phase>.json` 必须覆盖：
- `task_id -> requirement_ids -> acceptance_ids -> test_case_ids -> test_commands`

最低完整性：
1. 每个任务至少 1 个 `requirement_id`
2. 每个任务至少 1 个 `acceptance_id`
3. 每个任务至少 1 个 `test_case_id`
4. 每个任务至少 1 条 `test_command`
5. `gaps` 非空时，`gate_ready=false`

---

## 5. 与 dev-orchestrator 联动（MUST）

- `STEP 2` 开始前，必须先确认任务级 feature 设计已存在；
- 任务进入 `In review/done` 前，必须有对应测试文件与执行证据；
- `P0/P1` 任务必须显式要求 `--test-files` 与 diff 校验；
- 阶段末对账需用 `--milestone-id` 全量拉取后本地筛 phase。

### 5.1 核心依赖测试强约束（新增，MUST）

当任务涉及 Redis / 数据库 / AI 大模型 / 关键外部 API 时，`Feature` 设计中“测试设计与命令”必须满足：

- 测试执行模式固定为真实依赖（`execution_mode=real`）。
- 明确禁止 mock/stub/fake/in-memory（`allow_mock=false`）。
- 必须列出 `critical_dependencies`（如 `redis,mysql,llm`）。
- 必须列出可审计证据路径（日志、trace_id、request_id、事务ID）。

禁止：

- 主路径测试失败后自动降级到模拟数据并判定通过；
- 用 mock 成功结果替代核心验收证据；
- 在关键链路未真实验证时将任务写入 `In review/done`。

### 5.2 核心依赖不可用时的状态规则（新增，MUST）

若真实依赖不可达（连接失败/鉴权失败/配额不足/DNS 错误）：

- 任务测试状态必须标记为 `BLOCKED` 或 `FAILED`；
- 结论中必须写明阻断原因与缺失依赖；
- 不允许切换模拟路径继续验收；
- `sync_pm_status.py --update-task ... --status-value "In review|done"` 必须被门禁拒绝。

### 5.3 测试脚本路径与命名规范（新增，MUST）

涉及任务交付的自动化测试脚本必须满足以下可机读规范：

- 单元测试路径：`**/tests/**/test_*.py`
- 集成测试路径：`tests/integration/**/test_*.py`
- 端到端测试路径：`tests/e2e/**/test_*.py`
- 禁止将核心业务测试放入 `tmp/`、`scripts/`、`docs/` 等非测试目录。

命名规则：

- 测试文件名应采用：`test_<task_id_lower>_<tc_id_lower>_<slug>.py`
- 测试函数名应采用：`test_<given>_<when>_<then>`
- 每个测试文件必须至少包含 1 个 `TC-ID` 标记（函数名/参数化 id/注释之一）。

### 5.4 复合需求测试覆盖下限（新增，MUST）

对于多组件/跨边界任务（复合需求），每个 `TC-ID` 至少覆盖：

- 1 条主路径成功场景；
- 1 条关键失败场景；
- 1 条边界/异常输入场景。

若任务涉及幂等/重试/超时/并发语义，测试必须对每一项给出至少 1 条显式断言，不得只断言“返回成功”。

### 5.5 命令与证据绑定（新增，MUST）

- `feature_traceability*.json` 中每个 `task_id` 的 `test_commands` 必须逐项覆盖传入的 `--test-files`。
- `--test-files` 中的每个文件必须出现在当前 `git diff`。
- 必须产出机读证据（pytest 输出 / junit xml / 覆盖率报告），并可追溯到 `task_id + TC-ID`。
- 证据缺失时，任务不得进入 `In review/done`。

### 5.6 集成测试基线复用规则（新增，MUST）

编写集成测试时，必须优先复用现有基线脚本（优先参考 `database_service/scripts/test_theme_processor.py`）：

- 新增测试前，先检查是否可在现有基线文件直接新增 `test_*` 函数。
- 优先复用已有 fixture/helper/断言模式，禁止无理由从零搭建平行测试脚本。
- 默认策略是“增量追加测试函数”，而不是“新建同类测试文件”。

允许新建测试文件仅限以下条件之一：

- 现有文件职责边界不匹配；
- 会引入循环依赖或显著耦合；
- 现有文件规模已超维护阈值（如 >800 行）且已记录拆分理由。

若不满足以上条件仍新建文件，必须判定为设计违规并拒绝定稿。

### 5.7 数据库测试对齐规则（新增，MUST）

当任务测试涉及数据库读写时，Feature 设计必须显式约束：

- 测试数据库默认使用 `stock_data_test`（除非合同/环境文档明确覆盖）。
- 在生成测试设计前，先读取 `docs/architecture/*.sql`，并将测试断言对齐真实 schema 与约束。
- 测试中不得定义“与架构不一致的临时字段/简化表结构”作为主验证依据。
- 必须优先复用项目已有数据库访问层（`PostgresDatabaseManager`/`DatabaseGateway`）与现有测试基线，不得重复造轮子实现自定义数据库代理。
- 若确需偏离上述规则，必须在 `FEATURE_SPEC_<phase>.md` 写明豁免原因与风险评估，否则视为不合格设计。

---

## 6. 标准执行流程（MUST）

1. 读取任务上下文并裁决冲突
2. 生成 `FEATURE_SPEC_<phase>.md` 任务章节
3. 生成 `tmp/feature_traceability_<phase>.json`
4. 生成 `tmp/feature_validation_report_<phase>.json`
5. 执行机读校验（见第 7 节）
6. 仅在 `gate_ready=true` 时允许定稿

---

## 7. 严格机读化规范（MUST）

Schema 真源：
- `docs/project_control/schemas/feature_traceability.schema.json`
- `docs/project_control/schemas/feature_validation_report.schema.json`

校验命令：
```bash
.venv/bin/python scripts/validate_feature_artifacts.py \
  --traceability tmp/feature_traceability_<phase>.json \
  --report tmp/feature_validation_report_<phase>.json \
  --feature-spec docs/project_control/FEATURE_SPEC_<phase>.md \
  --phase P1.phase0
```

返回码：
- `0`：结构合法
- 非 `0`：结构非法，必须修订

---

## 8. 定稿拒绝逻辑（MUST）

任一命中必须拒绝定稿：
- 任务无稳定 ID
- 未映射 `ACPT-*` 或 `TC-*`
- 无测试命令或无预期结果
- 无回滚方案
- `gaps` 非空
- 核心依赖任务未声明 `execution_mode=real` / `allow_mock=false`
- 核心依赖任务缺少 `critical_dependencies` 或证据字段
- 测试文件路径不符合 `5.3` 规范
- 测试命名不符合 `5.3` 规范或缺少 `TC-ID` 标记
- 复合需求任务未满足 `5.4` 场景覆盖下限
- `test_commands` 未覆盖全部 `--test-files` 或缺少机读证据
- 集成测试未按 `5.6` 复用基线脚本且无有效豁免理由
- 未提供 `子功能分解` 小节或子功能点数量 < 3
- 子功能点缺失“输入/输出/失败处理/可观测证据”任一项

---

## 10. 与 dev-orchestrator 门禁对齐（新增，MUST）

生成 Feature 产物后，必须可被以下门禁脚本直接消费并通过：

- `scripts/verify_task_test_gate.py`
- `scripts/verify_behavior_test_quality.py`

若 Feature 规范与门禁脚本检查项不一致，以“更严格者”为准，并立即修订 `feature_traceability*.json` 与 `feature_validation_report*.json`。

---

## 9. 行为纪律（Behavior）

该技能必须：
- 风险优先
- 证据驱动
- 小步推进
- 不做超范围承诺

---

# End of Protocol

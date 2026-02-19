---
name: phase-contract-generator
description: 当用户要求“从现有文档自动提炼阶段执行合同（Execution Contract）”时使用；生成可供 dev-orchestrator 直接执行的 Phase Contract。
model: gpt-5
---

# Phase Contract Generator Protocol（阶段执行合同生成器）

本技能用于：

- 从已有 PRD 文档
- 从 ACCEPTANCE 文档
- 从 ARCH_REVIEW
- 从 PLAN_WBS
- 从 ADR 列表

自动提炼生成“阶段执行合同（Execution Contract）”。

该合同将作为 dev-orchestrator 的唯一输入标准。

本技能不写代码，不修改实现。
只生成结构化执行合同。

统一约束清单（跨技能一致）：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

---

# 0. 输出位置（必须）

生成：

docs/project_control/PHASE_CONTRACT_<phase>.md

例如：
PHASE_CONTRACT_P1.phase0.md

同时必须生成结构化副本（供执行器机器读取）：

tmp/phase_contract_<phase>.json

示例：
tmp/phase_contract_P1.phase0.json

---

# 0.1 输入真源优先级（新增，MUST）

合同提炼时，必须按以下优先级读取并裁决冲突：

1. `docs/project_control/PRD*.md`
2. `docs/project_control/ACCEPTANCE*.md`
3. `docs/project_control/PLAN_WBS*.md`
4. `docs/project_control/ARCH_REVIEW*.md`
5. `docs/adrs/*.md`

冲突处理规则：

- 上位优先级覆盖下位优先级；
- 不允许静默合并冲突；
- 必须在合同中新增“冲突裁决记录（Conflict Resolution）”列出：
  - 冲突项
  - 采用来源
  - 放弃来源
  - 裁决理由

## 0.1.1 PRD 多文件强制读取（新增，MUST）

当存在多个 PRD 文件（例如 `PRD.md` 与 `prd_p1.md`）时：

- 必须全部读取并纳入同一优先级真源集合（`PRD*.md`）；
- 不允许仅选取单个 PRD 文件后直接生成合同；
- 必须在合同 `Source Documents` 中显式列出所有已读取 PRD 文件；
- 若存在 PRD 之间的条款差异，必须写入 `Conflict Resolution`。

未满足以上任一项，合同生成应视为失败（不得输出最终合同）。

---

# 1. 必须包含内容结构

# Phase Execution Contract

## 1. Phase Identity

- Phase Name:
- Phase Code:
- Parent Milestone:
- Risk Level:
- Source Documents:

---

## 2. Phase Objective（可量化）

必须满足：

- 可验证
- 可测量
- 可复现
- 不抽象

---

## 3. Acceptance Targets（门禁条件）

- [ ] 条件1
- [ ] 条件2
- [ ] 条件3

必须是二元可判断项。

---

## 4. Required Commands（必须执行命令）

例如：

- pytest -q
- ruff check .
- mypy .

约束（新增，MUST）：

- Python 命令必须使用 `.venv/bin/python`；
- 必须给出阶段级必跑测试命令（可直接复制）；
- 禁止出现不安全或破坏性命令（如 `eval`、`git reset --hard`）。

---

## 5. Deliverables

- 修改模块
- 新增模块
- 更新测试
- 文档更新

约束（新增，MUST）：

- 每个交付项必须映射到可落地路径（文件/目录）；
- 每个交付项必须可被“存在性或命令结果”验证。

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Mitigation |

建议增强列（SHOULD）：

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |

---

## 7. Rollback Plan

- 回滚方式
- 数据恢复策略
- 兼容性说明

约束（新增，MUST）：

- 必须拆分“代码回滚 / 数据回滚 / 同步补偿回滚”；
- 必须定义触发条件（何时执行回滚）。

---

## 8. Non-Goals

明确本阶段不负责的内容。

约束（新增，SHOULD）：

- 显式列出跨阶段排除项，避免合同范围膨胀。

---

# 2. Scope 控制规则

支持：

scope=system
scope=phase:<phase_name>

如果是 phase 模式：

- 仅提炼该阶段文档
- 自动识别阶段编码（P1, P2 等）
- 不生成跨阶段任务

并且：

- 不跨 phase 引入后续阶段的验收条款或命令。

---

# 2.1 Acceptance-测试映射（新增，MUST）

每个 `Acceptance Target` 必须至少绑定一个可执行验证项：

- `TC-ID`（推荐）
- 或可直接执行的命令 + 明确预期结果

禁止输出“可读但不可验证”的验收条款。

---

# 2.2 状态同步与对账基线（新增，MUST）

合同中必须固化以下标准条款（供执行器直接使用）：

1. 实时状态同步顺序：
- `Doing -> test-evidence -> In review/done -> milestone progress`

2. `P0/P1` 状态门禁：
- 写入 `In review/done` 时必须传 `--test-files`；
- `--test-files` 必须在当前 `git diff` 中可见。

3. 阶段末对账口径：
- 必须用 `--milestone-id` 全量拉取后本地筛 phase；
- 不得仅用 `--task-prefix + --status` 判断完成度。

---

# 2.3 验收一致性门禁（新增，MUST）

对于 `scope=phase:<phase_code>`，必须执行“逐条一致性校验”：

1. 从 `ACCEPTANCE*.md` 提取该 phase 的“验收目标（清单）”；
2. 对比合同中 `## 3. Acceptance Targets`（按条款语义逐条匹配）；
3. 输出一致性报告：
   - `tmp/phase_contract_consistency_<phase>.json`
4. 报告字段至少包括：
   - `phase`
   - `acceptance_source`
   - `contract`
   - `acceptance_target_count`
   - `contract_target_count`
   - `missing_in_contract`
   - `extra_in_contract`
   - `is_consistent`

阻断规则（MUST）：

- 若 `missing_in_contract` 非空：禁止输出最终合同；
- 若 `is_consistent != true`：禁止输出最终合同；
- 若 `acceptance_target_count == 0` 或 `contract_target_count == 0`：禁止输出最终合同；
- 禁止将“0/0”视为一致性通过；当源或合同任一侧为 0 条时，必须判定为失败并提示“验收目标提取失败/合同为空”。
- 只有一致性通过，才允许写入 `docs/project_control/PHASE_CONTRACT_<phase>.md` 终稿。

## 2.3.1 生成顺序强约束（新增，MUST）

生成 phase 合同必须按以下固定顺序执行，禁止跳步：

1. 提取 `ACCEPTANCE*.md` 对应 phase 的验收目标清单（source list）。
2. 若 source list 为空：立即失败并停止（不得继续生成合同）。
3. 基于真源生成合同草稿（仅临时文件，不得覆盖终稿）。
4. 从草稿提取 `## 3. Acceptance Targets`（contract list）。
5. 若 contract list 为空：立即失败并停止（不得覆盖终稿）。
6. 执行一致性比较并生成 `tmp/phase_contract_consistency_<phase>.json`。
7. 仅当 `is_consistent=true` 且 `non_empty_ok=true` 时，才允许覆盖终稿。

建议临时文件路径（SHOULD）：
- `tmp/phase_contract_<phase>.draft.md`

## 2.3.2 失败输出规范（新增，MUST）

当命中阻断规则时，必须输出结构化失败报告：

`tmp/phase_contract_failure_<phase>.json`

至少包含字段：
- `phase`
- `failed_step`
- `reason`
- `acceptance_target_count`
- `contract_target_count`
- `action_required`

失败时禁止写入/覆盖：
- `docs/project_control/PHASE_CONTRACT_<phase>.md`（终稿）

---

# 3. 行为约束

- 不发散
- 不新增需求
- 不改架构
- 仅提炼已有内容

补充（新增）：

- 对不确定项必须显式标注“待确认”，不得自行假设；
- 生成后必须执行“合同自检清单”。

---

# 4. 合同自检清单（新增，MUST）

生成完成后，必须逐项通过：

1. 阶段标识完整（Phase Code/Parent Milestone/Source Documents）。
2. Acceptance 条款全部可二元判定。
3. Required Commands 可复制执行，且命令安全。
4. Deliverables 全部可映射路径。
5. Risk/Rollback/Non-Goals 无缺失。
6. 已输出 `.md + .json` 双格式。
7. 冲突裁决记录（若有冲突）已填写。
8. 引用了统一约束清单：`docs/project_control/EXECUTION_GUARDRAILS.md`。
9. 若存在多个 PRD 文件，已全部纳入 Source Documents 且完成冲突裁决。
10. 已生成并通过 `tmp/phase_contract_consistency_<phase>.json`（`is_consistent=true`）。
11. `acceptance_target_count > 0` 且 `contract_target_count > 0`（禁止空清单合同）。
12. 终稿写入前已通过“草稿->一致性->终稿”原子流程（禁止直接覆盖终稿）。

## 4.1 终稿覆盖保护（新增，MUST）

覆盖 `docs/project_control/PHASE_CONTRACT_<phase>.md` 前必须同时满足：

- `tmp/phase_contract_consistency_<phase>.json` 存在；
- `is_consistent == true`；
- `non_empty_ok == true`；
- `missing_in_contract` 和 `extra_in_contract` 均为空；
- `Source Documents` 已包含所有匹配到的 `PRD*.md`。

任一条件不满足，必须拒绝覆盖终稿。

---

# End of Protocol

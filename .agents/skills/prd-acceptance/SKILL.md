---
name: prd-acceptance
description: 当用户要求“为每个阶段制定验收目标、验收用例、边界条件、失败判定”时使用。
model: gpt-5
---

# 产品验收协议（生产级合约模式，中文版）

该技能用于输出“可执行、可复现、可二元判定”的验收合约。

统一约束清单（跨技能一致）：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

角色定位：
- 产品负责人（验收口径）
- QA 策略专家（验证可执行性）
- 风险控制审核员（失败判定与阻断）

原则：
- 禁止模糊语言
- 禁止主观“按预期工作”
- 验收条款必须可观察、可测试、可重现

---

## 0. 输入要求（MUST）

生成验收规范前，至少需要：
- 里程碑名称与 Phase 编码（如 `P1.phase0`）
- 目标能力与边界
- 关联架构文档（`docs/architecture/*`）
- 关联 PRD / WBS / 合同（若存在）
- 已知约束（性能、基础设施、合规）
- 风险等级（P0/P1/P2）

### 0.1 输入优先级（新增）

1. `PRD`
2. `PHASE_CONTRACT`
3. `PLAN_WBS`
4. `architecture` 说明

冲突时：
- 必须记录“冲突裁决说明”
- 未澄清前不得定稿

---

## 1. 输出产物（MUST）

必须生成：
1. `docs/project_control/ACCEPTANCE.md`
2. `tmp/acceptance_traceability.json`

说明：
- `ACCEPTANCE.md` 负责人类可读合约
- `acceptance_traceability.json` 负责机器可校验映射（目标 -> 用例 -> 命令）

建议同时输出（SHOULD）：
3. `tmp/acceptance_validation_report.json`
4. `tmp/acceptance_gaps.md`

---

## 2. ACCEPTANCE.md 固定结构（MUST）

对每个阶段（Phase）必须包含以下章节：

### Phase `<code>` — `<name>`

#### 1) 目标（Objective）
- 1~3 行，可衡量、不可抽象

#### 2) 验收目标（Acceptance Targets）
- 使用清单格式，全部是二元通过条件
- 每项需有唯一 ID（如 `ACPT-P1P0-001`）

#### 3) 验收用例（Given/When/Then）
- 每条用例必须有 Case ID（如 `ACC-P1P0-01`）
- 必须包含执行命令与期望结果

#### 4) 边界与非目标（Boundary/Non-Goals）
- 明确本阶段不保证内容

#### 5) 数据样例（如适用）
- 输入样例 + 预期输出（JSON/日志/状态变化）

#### 6) 失败判定（Fail Fast Criteria）
- 列出自动拒绝条件（任一命中即 Fail）

#### 7) 可观察性要求（Observability）
- 必需日志字段 / 指标 / 审计记录

#### 8) 变更兼容性说明（Compatibility）
- 向后兼容要求
- 破坏性变更前置条件（如 ADR 批准）

#### 9) 通过判定（Exit Criteria）
- 明确“本阶段通过”所需最小条件集合
- 要求全部条件满足（AND），禁止“任选其一”

---

## 3. 验收条款质量规则（MUST）

每个验收目标必须满足：
1. 具体（Specific）
2. 可验证（Verifiable）
3. 不重叠（Non-overlapping）
4. 可复现（Reproducible）
5. 与本阶段范围一致（In-scope）

禁止：
- “优化体验”“提升稳定性”等无阈值语句
- “大致通过”“基本满足”等模糊表述

---

## 4. 验收-测试映射（新增，MUST）

每条 `Acceptance Target` 必须映射至少一个验证项：
- `ACC-*` 用例
- 或可执行命令（pytest/脚本/接口探测）

并在 `tmp/acceptance_traceability.json` 输出：

```json
{
  "phase": "P1.phase0",
  "generated_at": "2026-02-17T10:45:00Z",
  "traceability": [
    {
      "acceptance_id": "ACPT-P1P0-001",
      "case_ids": ["ACC-P1P0-01"],
      "commands": ["pytest -q database_service/tests/streams/test_phase0_contract_guards.py"],
      "expected": "pass"
    }
  ],
  "gaps": [],
  "gate_ready": true
}
```

门禁规则：
- 存在未映射目标时，`gate_ready=false`
- 未满足映射完整性不得定稿

映射完整性最低标准：
1. 每个 `ACPT-*` 至少 1 个 `ACC-*`
2. 每个 `ACC-*` 至少 1 条可执行命令
3. 每条命令有明确“通过判据”（退出码/日志关键字/状态值）

---

## 5. 失败判定标准（MUST）

以下任一项命中即“阶段未通过”：
- 未处理异常或 traceback
- 非法状态变更/静默行为漂移
- 关键字段缺失或契约不一致
- 性能回归超过阈值（如 >20%）
- 关键验收用例无法重现
- 对账结果与验收声明冲突

不允许“部分通过”。

---

## 6. 跨阶段一致性（MUST）

必须保证：
1. 不回退已通过阶段的约束
2. 不削弱已有合约
3. 向后兼容（除非 ADR 明确允许破坏）
4. 每个验收目标都有验证方法

---

## 7. 与执行器联动条款（新增，MUST）

若验收文档用于 `dev-orchestrator`：
- `P0/P1` 任务进入 `In review/done` 前，必须 `--test-files` + diff 校验；
- 阶段末对账必须使用 `--milestone-id` 全量拉取后本地筛 phase；
- 禁止仅用 `--task-prefix + --status` 作为完成依据。

任务状态流转建议（SHOULD）：
- `Todo -> Doing -> In review -> done`
- 遇阻塞：`Doing -> Blocked -> Doing`
- 评审不通过：`In review -> Doing`
- 每次流转需写入证据（测试结果 / 评审意见 / 阻塞原因）

---

## 10. 标准执行流程（新增，MUST）

1. 读取输入源并做冲突裁决（按 0.1 优先级）
2. 生成 `ACCEPTANCE.md` 初稿（按第 2 节固定结构）
3. 生成 `tmp/acceptance_traceability.json`
4. 执行结构化自检（见第 11 节）
5. 输出 gaps 与修复建议
6. 仅在 `gate_ready=true` 时允许定稿

---

## 11. 自检清单（新增，MUST）

定稿前逐条检查：
1. 是否所有验收目标都有唯一 ID
2. 是否所有用例都有命令与预期
3. 是否所有目标已建立 traceability
4. 是否定义了边界、非目标、失败判定
5. 是否定义了可观察性字段与审计证据
6. 是否存在模糊语言（如“基本可用”“显著提升”）
7. 是否与 Phase Contract / WBS 编号一致

若任一项失败：
- 产出 `tmp/acceptance_gaps.md`
- 拒绝定稿

---

## 12. 快速模板（新增，SHOULD）

`ACCEPTANCE.md` 片段示例：

```markdown
### Phase P1.phase0 — 基础能力落地

#### 2) 验收目标（Acceptance Targets）
- [ACPT-P1P0-001] 关键任务状态可从 Todo 流转至 done，且全程有审计记录。

#### 3) 验收用例（Given/When/Then）
- [ACC-P1P0-01]
  - Given: 存在任务 `P1.phase0-T01`
  - When: 执行 `.venv/bin/python sync_pm_status.py --update-task <task_id> --status-value "done"`
  - Then: 返回成功；Notion 中状态为 `done`；审计日志包含 task_id 与时间戳。
```

`tmp/acceptance_validation_report.json` 建议结构：

```json
{
  "phase": "P1.phase0",
  "checked_at": "2026-02-17T10:45:00Z",
  "checks": [
    { "name": "id_uniqueness", "passed": true },
    { "name": "traceability_complete", "passed": true },
    { "name": "fail_fast_defined", "passed": true }
  ],
  "gate_ready": true
}
```

---

## 13. 常见故障与修复（新增）

1. 症状：目标很多但用例很少  
   原因：未做一一映射  
   修复：补全 `traceability`，禁止多目标共用单一弱用例。

2. 症状：命令可运行但无法判定是否通过  
   原因：缺少明确期望  
   修复：补充退出码、关键字段、状态值断言。

3. 症状：验收通过但上线后回归  
   原因：边界/非目标未声明导致误判  
   修复：强化第 2 节第 4/6/8 项并引入回归用例。

---

## 14. 严格机读化规范（新增，MUST）

为保证跨技能稳定消费，JSON 产物必须带版本并通过 Schema 校验。

### 14.1 强制字段与版本

`tmp/acceptance_traceability.json` 顶层必须包含：
- `schema_version`（固定：`"1.0"`）
- `phase`
- `generated_at`（ISO8601）
- `source_files`（数组）
- `summary`
- `traceability`
- `gaps`
- `gate_ready`

`tmp/acceptance_validation_report.json` 顶层必须包含：
- `schema_version`（固定：`"1.0"`）
- `phase`
- `checked_at`（ISO8601）
- `checks`
- `gate_ready`

### 14.2 枚举与格式约束

- `summary.risk_level` 仅允许：`P0 | P1 | P2`
- `checks[].severity` 仅允许：`info | warn | error`
- `checks[].name` 建议固定词表：`id_uniqueness | traceability_complete | fail_fast_defined | command_assertion_ready | schema_valid`
- `acceptance_id` 必须匹配：`^ACPT-[A-Za-z0-9.-]+-\\d{3}$`
- `case_ids[]` 必须匹配：`^ACC-[A-Za-z0-9.-]+-\\d{2,3}$`

### 14.3 Schema 文件（仓库真源）

必须使用以下文件作为校验基准：
- `docs/project_control/schemas/acceptance_traceability.schema.json`
- `docs/project_control/schemas/acceptance_validation_report.schema.json`

### 14.4 自动校验命令（MUST）

```bash
.venv/bin/python scripts/validate_acceptance_artifacts.py \
  --traceability tmp/acceptance_traceability.json \
  --report tmp/acceptance_validation_report.json \
  --phase P1.phase0
```

规则：
- 返回码 `0`：结构合法，可进入 gate 判断
- 返回码非 `0`：结构非法，必须回到修订阶段

---

## 15. 定稿拒绝逻辑（MUST）

出现以下任一情况必须拒绝定稿并回到澄清：
- 验收目标不明确
- 用例缺失执行命令或预期
- 边界/非目标缺失
- 失败判定缺失
- traceability 有 gaps

---

## 16. 行为纪律（Behavior）

该技能必须：
- 保守
- 风险优先
- 证据驱动
- 不做营销化描述
- 不做超范围承诺

---

# End of Protocol

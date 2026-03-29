---
name: prd-doc
description: 当用户要求“生成、确认、调整需求文档”，并明确需求目标、功能点、验收标准时使用。
model: gpt-5
---

# 产品需求文档协议（生产级合约模式，中文版）

该技能用于生成“可执行、可追踪、可门禁”的 PRD 合约。

统一约束清单（跨技能一致）：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

角色定位：
- 产品负责人（目标与边界）
- 需求工程师（需求结构化）
- 风险控制审核员（冲突与失败判定）

原则：
- 禁止模糊需求
- 禁止不可验证承诺
- 需求必须能映射到验收与测试

---

## 0. 输入要求（MUST）

生成或更新 PRD 前，至少需要：
- Phase 编码（如 `P1.phase0`）与里程碑名称
- 目标能力与业务背景
- 关联文档：`docs/architecture/*`、`PLAN_WBS.md`、`ACCEPTANCE.md`、`PHASE_CONTRACT*`
- 约束：性能/成本/安全/合规/兼容性
- 风险等级：`P0 | P1 | P2`
- 关键干系人决策（若有）

### 0.1 输入优先级（MUST）

1. 用户最新明确指令
2. `PHASE_CONTRACT*`
3. `ACCEPTANCE.md`
4. `PLAN_WBS.md`
5. `docs/architecture/*`

冲突处理：
- 必须记录“冲突裁决说明”
- 冲突未裁决前不得定稿

---

## 1. 输出产物（MUST）

必须生成：
1. `docs/project_control/PRD.md`
2. `tmp/prd_traceability.json`
3. `tmp/prd_validation_report.json`

说明：
- `PRD.md`：人类可读需求合同
- `prd_traceability.json`：需求到验收/测试/WBS 的机器映射
- `prd_validation_report.json`：结构化自检与门禁结果

---

## 2. PRD 固定结构（MUST）

对每个阶段必须包含以下章节：

### Phase `<code>` — `<name>`

#### 1) 目标（Objective）
- 1-3 行，可衡量、可观察
- 必须有量化阈值（时延、成功率、成本、容量等）

#### 2) 范围（Scope）
- In Scope：本阶段交付项
- Out of Scope：本阶段不交付项

#### 3) 功能需求（Functional Requirements）
- 每条需求必须有 ID：`PRD-REQ-<phase>-NNN`
- 每条必须包含：描述、触发条件、预期行为、约束

#### 4) 非功能需求（NFR）
- 性能、稳定性、安全、可观测、兼容性
- 每条必须有可测试阈值

#### 5) 用例（Given/When/Then）
- 每条用例必须有 ID：`PRD-UC-<phase>-NN`
- 每个功能需求至少 1 条用例

#### 6) 验收映射（Acceptance Link）
- 每条需求必须映射 `ACPT-*`（来自 `ACCEPTANCE.md`）
- 无法映射的需求不得进入定稿

#### 7) 数据与接口样例（如适用）
- 请求/响应/事件样例
- 错误码与失败路径

#### 8) 风险与假设（Risks/Assumptions）
- 标注风险等级与缓解措施

#### 9) 发布与回滚约束（Release Constraints）
- 上线前置条件
- 回滚触发条件

#### 10) 通过判定（Exit Criteria）
- 全部条件满足（AND）
- 禁止“满足其一即可”

---

## 3. 质量规则（MUST）

每条需求必须满足：
1. 具体（Specific）
2. 可验证（Verifiable）
3. 可追踪（Traceable）
4. 不冲突（Non-conflicting）
5. 与阶段范围一致（In-scope）

禁止：
- “显著提升”“体验更好”等无阈值表述
- “按预期工作”这类不可判定语句

---

## 4. 需求追踪映射（MUST）

`tmp/prd_traceability.json` 必须覆盖：
- `PRD Requirement -> Use Case -> Acceptance -> Test Case -> WBS Task`

最低完整性：
1. 每个 `PRD-REQ-*` 至少 1 个 `PRD-UC-*`
2. 每个 `PRD-REQ-*` 至少 1 个 `ACPT-*`
3. 每个 `PRD-REQ-*` 至少 1 个 `WBS Task ID`
4. 存在 `gaps` 时，`gate_ready=false`

---

## 5. 变更管理（MUST）

当用户要求“调整 PRD”时：
1. 保留原章节结构与稳定 ID
2. 新增 `Change Log`（日期、变更项、原因、影响）
3. 若影响验收或 WBS，必须同步标记受影响 ID
4. 破坏性变更必须显式标注并提示需要 ADR/审批

---

## 6. 与执行器联动条款（MUST）

若交给 `dev-orchestrator` 执行：
- PRD 中每个 `PRD-REQ-*` 必须能映射到任务 ID；
- P0/P1 需求必须带测试命令或明确测试入口；
- 禁止“先开发后补需求映射”。

---

## 7. 标准执行流程（MUST）

1. 读取输入并做冲突裁决
2. 产出 `PRD.md` 初稿
3. 生成 `tmp/prd_traceability.json`
4. 生成 `tmp/prd_validation_report.json`
5. 运行机读校验（见第 8 节）
6. 仅在 `gate_ready=true` 时定稿

---

## 8. 严格机读化规范（MUST）

Schema 真源文件：
- `docs/project_control/schemas/prd_traceability.schema.json`
- `docs/project_control/schemas/prd_validation_report.schema.json`

校验命令：
```bash
.venv/bin/python scripts/validate_prd_artifacts.py \
  --traceability tmp/prd_traceability.json \
  --report tmp/prd_validation_report.json \
  --phase P1.phase0
```

返回码规则：
- `0`：结构合法，可进入 gate
- 非 `0`：结构非法，必须回到修订

---

## 9. 定稿拒绝逻辑（MUST）

任一命中则拒绝定稿：
- 需求无稳定 ID
- 需求不可验证或无阈值
- 需求未映射验收/WBS/测试
- 存在冲突但无裁决说明
- `gaps` 非空

---

## 10. 行为纪律（Behavior）

该技能必须：
- 保守
- 风险优先
- 证据驱动
- 不做营销化描述
- 不做超范围承诺

---

# End of Protocol

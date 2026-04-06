---
description: 按阶段自动制定计划→实施→验证→报告→门禁→等待验收的受控工程执行器（支持 Notion 同步与任务真源模式）
model: gpt-5
name: dev-orchestrator
generated: 2026-02-15 10:30:00
version: 2.3.4
---

# Development Orchestrator Protocol（生产级中文版）

本技能为"阶段驱动 + 任务真源 + Notion 同步"的严格工程执行协议。

统一约束清单（跨技能一致）：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

**角色定位**：
- 项目经理（PM）
- 架构师（Architect）
- QA负责人（QA Lead）
- 发布控制官（Release Manager）

**默认语言**：**所有输出必须为中文**（命令与代码除外）。

---

# 0. 非协商规则（Hard Rules）

1. **分支规范**：必须在功能分支上工作：`codex/<phase>/<topic>`
   - 示例：`codex/phase-1/user-authentication`

2. **主分支保护**：禁止直接修改 main/master，必须通过 PR/MR 合并。

3. **小步提交原则**：
   - 每次提交必须是可运行的小 diff
   - 禁止一次性跨模块大改
   - 遵循"改动-验证-提交"循环

4. **禁止破坏性操作**：
   - 不得删除数据库 schema
   - 不得批量删除生产数据
   - 不得执行不可逆迁移（必须设计回滚方案）

5. **Python 执行规范**：必须使用 `.venv/bin/python` 执行所有脚本

6. **网络访问失败处理**：
   - 仅允许一次用户授权请求
   - 若用户拒绝，立即进入离线 fallback 模式
   - 生成 `tmp/offline_payload.json` 等待手动同步

7. **阶段结束必须项**：
   - 运行所有验证命令
   - 生成阶段报告：`docs/project_control/reports/phase-XX.md`
   - 输出 Review Checklist
   - 停止执行并等待用户决策（ACCEPT/REWORK/REQUEST CHANGES）

8. **安全执行规则**：
   - 禁止在编排脚本中使用 `eval` 执行测试命令
   - 优先使用 `.venv/bin/python` 读取/解析 JSON，不依赖 `jq` 作为必需前置

9. **执行模式（新增）**：
   - `--mode guarded`：默认模式，关键节点可请求用户确认。
   - `--mode autopilot`：无人值守模式，除“中断白名单”外不得中断，必须自动重试/补偿/续跑直到进入阶段验收等待点（STEP 5.2）。

10. **实现优先于测试框架（新增）**：
   - 当阶段包含核心组件重构时，必须先完成“核心实现任务分解 -> 关键组件编码 -> 单元测试 -> 集成测试”，最后才进入生产级 E2E/测试框架打通。
   - 禁止在核心组件实现任务尚未拆清时，直接以测试框架开发替代主实施路径。

11. **测试分层门禁（新增）**：
   - 必须执行 `UT -> IT -> PT/E2E` 顺序。
   - 若下游依赖组件未通过，上游测试必须标记 `BLOCKED`。
   - 不得跳过 `UT/IT` 直接执行 E2E 并据此推进任务状态到 `In review/done`。

## 0.2 Autopilot 运行参数（新增，MUST）

`--mode autopilot` 时必须启用：

- `--resume <run_id>`（若存在历史 run）
- `--max-retries 5`
- `--retry-backoff 1,2,4,8,16`
- `--auto-reconcile true`
- `--stop-at step5.2`（仅在验收决策点停止）

运行状态文件（MUST）：

- `tmp/runs/<run_id>/state.json`
- `tmp/runs/<run_id>/events.log`
- `tmp/runs/<run_id>/checkpoints/`

`state.json` 最小字段：

```json
{
  "run_id": "20260217_193000",
  "mode": "autopilot",
  "phase": "P1.phase0",
  "current_step": "STEP 2",
  "current_task_id": "P1.phase0-T02",
  "attempt": 2,
  "pending_sync": [],
  "gate_status": "running",
  "updated_at": "2026-02-17T19:30:00Z"
}
```

## 0.3 中断白名单（新增，MUST）

仅以下情况允许中断并等待用户：

1. 合同冲突无法自动裁决（多真源冲突且无优先级结论）
2. 潜在破坏性操作需要人工授权（不可逆迁移/删除）
3. 凭据缺失且自动重试与离线补偿均失败
4. 安全/合规风险触发（超出合同授权范围）

其他错误一律不得中断，必须走自动修复链路。

## 0.1 快速开始（新增）

```bash
# 1) 环境准备
cd ~/Desktop/ai_theme_app
source .venv/bin/activate

# 2) 验证 Notion 连接
.venv/bin/python sync_pm_status.py --fetch-tasks --output tmp/verify_tasks.json

# 3) 启动阶段任务拉取
.venv/bin/python sync_pm_status.py --fetch-tasks --task-prefix "P1.phase0" --status "Todo,Doing,In review" --output tmp/p1_phase0_active.json
```

## 0.4 Autopilot Preflight（新增，MUST）

进入 `STEP 1` 前，`--mode autopilot` 必须完成以下预检（全部通过才继续）：

1. Token 预检（必须）

```bash
.venv/bin/python sync_pm_status.py --verify-token
```

2. 网络/Notion 连通性预检（必须）

```bash
.venv/bin/python sync_pm_status.py \
  --fetch-tasks \
  --task-prefix "P1.phase0" \
  --status "Todo,Doing,In review" \
  --output tmp/preflight_tasks.json
```

本地汇总命令（新增，MUST）：

```bash
.venv/bin/python scripts/run_preflight.py \
  --phase P1.phase0 \
  --run-id <run_id> \
  --verify-log tmp/runs/<run_id>/preflight_verify.log \
  --verify-rc <verify_rc> \
  --tasks-output tmp/runs/<run_id>/preflight_tasks.json \
  --fetch-log tmp/runs/<run_id>/preflight_fetch.log \
  --fetch-rc <fetch_rc>
```

3. 预检失败处理（必须）
- Token 失败：直接进入“凭据错误”分支，停止在线同步尝试并写入 `pending_sync`；
- 网络失败：仅申请一次外网授权，失败则进入离线队列模式；
- 预检未通过时不得进入 `STEP 2`。
- 强制顺序（MUST）：
  1. 顶层执行在线探测 A（单段）：`.venv/bin/python sync_pm_status.py --verify-token > tmp/runs/<run_id>/preflight_verify.log`；
  2. 顶层执行在线探测 B（单段）：`.venv/bin/python sync_pm_status.py --fetch-tasks --task-prefix <phase> --status "Todo,Doing,In review" --output tmp/runs/<run_id>/preflight_tasks.json > tmp/runs/<run_id>/preflight_fetch.log`；
  3. 本地执行 `scripts/run_preflight.py` 汇总 preflight.json（禁止该脚本内部触网）；
  4. 若返回 `require_network_escalation_once=true`，必须立刻执行一次外网授权探测；
  5. 探测成功后重跑 1~3；探测失败才允许进入离线队列模式。
- preflight 硬门禁（MUST）：
  - 重跑 preflight 后，必须立即执行：
    `.venv/bin/python scripts/verify_preflight_gate.py --preflight-json tmp/runs/<run_id>/preflight.json --state-json tmp/runs/<run_id>/state.json --events-log tmp/runs/<run_id>/events.log`
  - 若脚本返回非 0，禁止进入 `STEP 2`。
- 禁止将“外网授权探测”延迟到 `STEP 5.2` 或 `ACCEPT` 后再执行。

preflight 输出中若出现以下字段，视为强制触发一次外网授权：

```text
require_network_escalation_once=true
next_action=request_network_escalation_once
```

一次外网授权探测命令（必须保持在线前缀）：

```bash
.venv/bin/python sync_pm_status.py --verify-token
```

3.1 无人工弹窗执行规范（新增，MUST）
- 所有在线命令必须使用“固定命令前缀”直接执行，优先命中已授权规则；
- 禁止把在线命令包在 `bash -lc` 中再附带多段 `&&` 链接；
- 禁止在命令前内联 `NOTION_TOKEN=...`（会导致前缀不匹配）；
- 应通过运行环境预先注入 token（环境变量或 `.env` 自动加载）；
- 命令执行建议使用 `workdir` 参数，不通过 `cd ... &&` 切换目录。
- 一旦命令不满足“单段前缀”约束，执行器必须拒绝执行并改写为合规形态后重试；
- 允许需要外网授权，但授权请求对应命令也必须保持同一前缀（不得换成 `/bin/bash -lc` 包装）。

示例（推荐）：

```text
.venv/bin/python sync_pm_status.py --fetch-tasks --milestone-id <id> --output <file>
.venv/bin/python sync_pm_status.py --record-decision --milestone-id <id> --decision "ACCEPT"
```

示例（不推荐，容易触发人工授权弹窗）：

```text
/bin/bash -lc "cd ... && NOTION_TOKEN=... .venv/bin/python sync_pm_status.py ... && ..."
```

3.2 固定执行策略（新增，MUST）

适用范围：所有 Notion 在线读写命令（`verify-token/fetch-tasks/update-task/update-milestone-progress/record-decision/create-report/update-report`）。

强制策略：
- 统一前缀：`.venv/bin/python sync_pm_status.py`
- 统一工作目录：通过执行器 `workdir` 设置仓库根目录，不允许 `cd ... &&`
- 统一命令形态：单段命令（不得含 `&&`、`||`、`;`、管道）
- 统一凭据来源：环境变量或 `.env` 自动加载，不允许命令内联 token

执行决策矩阵（必须按序）：
1. 若命令不满足“固定前缀 + 单段命令”，先重写命令形态，再执行。
2. 首次在线失败且错误包含 DNS/超时/连接重置，执行指数退避重试：`1,2,4` 秒。
3. 重试仍失败：写入 `tmp/runs/<run_id>/pending_sync.json` 并继续主流程（不得中断）。
4. 阶段末 `6.4` 必须执行补偿重放；补偿仍失败才允许进入人工介入。
5. 错误为明确凭据无效（401/unauthorized/invalid token）时，不重试网络分支，直接进入凭据错误分支。

标准命令模板（执行器内部）：

```text
cmd: ".venv/bin/python sync_pm_status.py --record-decision --milestone-id <id> --decision ACCEPT --notes <notes>"
workdir: "/Users/admin/Desktop/ai_theme_app"
```

禁止模板（必须拒绝）：

```text
cmd: "cd /repo && export NOTION_TOKEN=... && .venv/bin/python sync_pm_status.py --fetch-tasks ..."
cmd: "/bin/bash -lc '.venv/bin/python sync_pm_status.py ... && .venv/bin/python sync_pm_status.py ...'"
```

4. 预检机读产物（必须）
- 必须生成：`tmp/runs/<run_id>/preflight.json`
- 用于审计、续跑和问题定位。

建议生成模板：

```json
{
  "run_id": "20260217_203000",
  "phase": "P1.phase0",
  "mode": "autopilot",
  "generated_at": "2026-02-17T20:30:00Z",
  "checks": {
    "token_verify": {
      "ok": true,
      "token_fingerprint": "ntn_...B7li",
      "user_type": "bot"
    },
    "network_fetch_tasks": {
      "ok": true,
      "tasks_count": 12
    }
  },
  "gate_ready": true,
  "blocking_issues": []
}
```

建议命令模板（可直接复用，单段前缀）：

```bash
RUN_ID="<run_id>"
mkdir -p "tmp/runs/${RUN_ID}"

# 1) 在线探测 A（单段）
.venv/bin/python sync_pm_status.py --verify-token > "tmp/runs/${RUN_ID}/preflight_verify.log" 2>&1
VERIFY_RC=$?

# 2) 在线探测 B（单段）
.venv/bin/python sync_pm_status.py \
  --fetch-tasks \
  --task-prefix "P1.phase0" \
  --status "Todo,Doing,In review" \
  --output "tmp/runs/${RUN_ID}/preflight_tasks.json" > "tmp/runs/${RUN_ID}/preflight_fetch.log" 2>&1
FETCH_RC=$?

# 3) 本地汇总（不触网）
.venv/bin/python scripts/run_preflight.py \
  --phase "P1.phase0" \
  --run-id "${RUN_ID}" \
  --verify-log "tmp/runs/${RUN_ID}/preflight_verify.log" \
  --verify-rc "${VERIFY_RC}" \
  --tasks-output "tmp/runs/${RUN_ID}/preflight_tasks.json" \
  --fetch-log "tmp/runs/${RUN_ID}/preflight_fetch.log" \
  --fetch-rc "${FETCH_RC}"
```

已落地脚本约束（MUST）：
- `scripts/run_preflight.py` 默认仅做本地聚合，不得在脚本内调用 `sync_pm_status.py`；
- 若使用 `--online-probe` 兼容模式，必须记录事件 `reject_nested_online_command` 并视为违规路径（仅排障临时使用）。

门禁规则（MUST）：
- `checks.token_verify.ok == true`
- `checks.network_fetch_tasks.ok == true`（或明确进入离线模式并记录原因）
- `gate_ready == true` 方可进入 `STEP 1`

Autopilot 启动模板（新增）：

```bash
PHASE_TAG="P1.phase0"
RUN_ID="$(date +%Y%m%d_%H%M%S)"

# 初始化 run 状态目录
mkdir -p "tmp/runs/${RUN_ID}/checkpoints"
echo "${RUN_ID}" > tmp/current_run_id.txt

# 约定：执行器以 autopilot 运行至 STEP 5.2 再停
# （技能调用层需传入：--mode autopilot --max-retries 5 --auto-reconcile true --stop-at step5.2）
```

Autopilot 续跑模板（新增）：

```bash
RUN_ID="$(cat tmp/current_run_id.txt)"

# 约定：执行器读取 tmp/runs/${RUN_ID}/state.json 并从 current_step 继续
# （技能调用层需传入：--mode autopilot --resume "${RUN_ID}"）
```

---

# 1. 任务真源（Source of Truth）

## 1.1 任务来源优先级
必须按以下优先级从**真源**读取任务：

| 优先级 | 来源 | 获取方式 |
|:------:|:------|:------|
| 1 | Notion Milestone 关联 Tasks | 执行 `sync_pm_status.py --fetch-tasks` |
| 2 | 本地计划文件 | `tmp/pm_plan_payload.json` |
| 3 | 显式任务ID列表 | 用户直接提供的 Task ID 列表 |

## 1.2 从 Notion 获取任务列表

# 组合过滤（前缀+状态）
.venv/bin/python sync_pm_status.py --fetch-tasks --task-prefix "P1.phase0" --status "Todo,Doing" --output tmp/p1_phase0_active.json

# 获取指定里程碑下的所有任务
.venv/bin/python sync_pm_status.py --fetch-tasks --milestone-id <milestone_id> --output tmp/tasks.json

# 获取所有待处理任务
.venv/bin/python sync_pm_status.py --fetch-tasks --status "Todo,Doing" --output tmp/active_tasks.json

## 1.3 任务数据格式

tmp/active_tasks.json格式输出如下：

{
  "tasks": [
    {
      "id": "3067bab0-ee1d-8166-b844-ff94f09245ae",
      "name": "用户认证模块开发",
      "status": "Todo",
      "priority": "P0",
      "estimate": 5,
      "dependencies": [],
      "dod_checklist": ["单元测试", "API文档", "代码审查"]
    }
  ],
  "milestone": {
    "id": "3067bab0-ee1d-8184-84a6-d3e06f82506a",
    "name": "Q1 2026 产品发布",
    "phase": "Development"
  }
}

## 1.4 重要规则
禁止重新拆解任务，除非任务真源缺失

必须保持任务与 Notion 的双向同步

必须在执行前验证任务状态的准确性

## 1.5 任务真源预处理（新增）

进入 `STEP 2` 前，必须执行一次真源预处理：

1. 优先从 Notion 拉取当前阶段任务。
2. 若返回 0 任务，必须先做“原因判定”：
   - 是否过滤条件过严（例如仅查 `Todo,Doing`，而任务已是 `done`）；
   - 是否使用了错误过滤维度（建议以 `--milestone-id` 全量拉取再本地筛选 phase）。
3. 仅在确认“真源缺失”后，才允许用本地计划创建任务（`sync_pm_plan.py`），并且必须请求用户确认。
4. 创建后必须重新拉取任务并校验任务 ID 已生成。

推荐命令（无 `jq` 依赖）：

```bash
# A. 先拉取阶段活动任务
.venv/bin/python sync_pm_status.py --fetch-tasks --task-prefix "P1.phase0" --status "Todo,Doing,In review" --output tmp/notion_phase_tasks.json

# B. 若怀疑漏数，拉取里程碑全量作为对账真源
.venv/bin/python sync_pm_status.py --fetch-tasks --milestone-id <milestone_id> --output tmp/milestone_tasks.json
```

## 1.6 任务 ID 缓存（新增）

为避免重复查询，可建立 `tmp/task_id_map.json`。但必须遵循：

- 缓存仅对当前 `run_id` 有效；
- 每次 run 启动后必须先刷新一次；
- 缓存缺失时回退到 Notion 重新拉取；
- 禁止跨 phase 复用旧缓存。

# 2. 阶段执行流程（严格顺序）

## STEP 1 —— 计划（不写代码）

### 1.1 输入分析
阅读架构文档（docs/architecture/）

阅读 ADR（docs/adrs/）

阅读现有测试（tests/）

阅读现有测试用例（docs/project_control/TEST_CASE_SPEC.md）

阅读现有测试计划（docs/project_control/TEST_PLAN_SPEC.md）

获取任务真源（按第1节规则）

### 1.2 计划输出
必须生成以下文档到 tmp/plan/ 目录：

#### 1. WBS 执行子集（wbs_<phase>.md）

执行任务清单：

- [ ] 任务1: 具体实施步骤
- [ ] 任务2: 具体实施步骤

边界约束（MUST）：
- `wbs_<phase>.md` 仅定义“做什么/先后顺序/依赖关系/优先级”；
- 禁止在 `wbs_<phase>.md` 写接口字段、数据表细节、错误码、回滚操作；
- 这些“如何实现”的内容必须在 `STEP 1.8` 的 `feature` 设计中给出。

命名规则（MUST）：
- WBS 文件必须带阶段后缀：`tmp/plan/wbs_<phase>.md`。
- 示例：`tmp/plan/wbs_P1.phase3.md`。
- 禁止只生成无后缀文件 `tmp/plan/wbs.md` 作为阶段真源。

#### 2. 风险列表（risks.md）

风险登记册：

| 风险ID | 描述 | 可能性 | 影响 | 缓解措施 |
|:-------|:-----|:-------|:-----|:---------|
| RISK-001 | 依赖服务不稳定 | 中 | 高 | 增加重试机制 |

#### 3. 变更计划（change_plan.md）

变更文件清单：

| 文件路径 | 变更类型 | diff摘要 | 影响范围 |
|:---------|:---------|:---------|:---------|
| src/auth.py | 修改 | 增加JWT验证 | 所有API |

### 1.3 确认点
若存在架构影响或跨模块改动，必须：

在 change_plan.md 中明确标注

请求用户确认后才能进入STEP 1.5

## STEP 1.5 —— 测试用例与测试脚本预置（先于 STEP 2）
基于 `STEP 1` 输出的 `tmp/plan/wbs_<phase>.md`，调用 `test-case` 技能生成测试用例规范，并在进入 `STEP 2` 循环前预置可执行测试脚本骨架。

### 1.5.1 输入

- `tmp/plan/wbs_<phase>.md`
- `docs/project_control/ACCEPTANCE.md`
- `docs/project_control/PHASE_CONTRACT_*.md`（当前阶段合同）

### 1.5.2 产出

- `docs/project_control/TEST_CASE_SPEC_<phase>.md`
- `tmp/plan/test_traceability_<phase>.json`（任务 -> 用例 -> 验收条款映射）
- 可执行测试脚本（或在既有脚本中新增 `test_*` 用例），并带 `TC-ID` 可追溯标记

### 1.5.3 覆盖规则（MUST）

- 每个 WBS 子任务至少 1 条正向用例。
- 每个高风险任务至少 1 条失败/边界用例。
- 合同关键字段与关键链路必须覆盖（例如 `decision_id,event_id,action,payload_version,trace_id,idempotency_key,payload`）。
- 每条用例必须包含执行命令与预期结果（可直接映射到 pytest/CLI）。

### 1.5.4 进入 STEP 2 的门禁

- 用例覆盖率满足 1.5.3；
- `test_traceability_<phase>.json` 无未映射任务；
- 关键任务（默认 `P0/P1`）对应的可执行测试脚本已预置完成（允许先失败）；
- 若存在缺口，必须先补齐用例/脚本，不得进入 STEP 1.8/STEP 2。

### 1.5.5 标准命令模板（可直接复用）

> 说明：`test-case` 为技能调用，不是独立 CLI。以下模板用于“前置拉取 -> 生成用例 -> 结果校验 -> 可选同步”。

```bash
# 0) 参数约定
PHASE_CODE="P1.phase0"
PHASE_TAG="P1.phase0"
MILESTONE_ID="<milestone_id>"

# 1) 拉取当前阶段任务（供 test-case 设计时引用）
.venv/bin/python sync_pm_status.py \
  --fetch-tasks \
  --task-prefix "${PHASE_CODE}" \
  --output "tmp/${PHASE_TAG}_tasks_for_test_case.json"
```

```text
# 2) 调用 test-case 技能（由执行器完成）
输入：
- tmp/plan/wbs_<phase>.md
- docs/project_control/ACCEPTANCE.md
- docs/project_control/PHASE_CONTRACT_${PHASE_TAG}.md

输出：
- docs/project_control/TEST_CASE_SPEC_${PHASE_TAG}.md
- tmp/plan/test_traceability_${PHASE_TAG}.json
```

```bash
# 3) 产物存在性检查（缺一即阻断）
test -f "docs/project_control/TEST_CASE_SPEC_${PHASE_TAG}.md"
test -f "tmp/plan/test_traceability_${PHASE_TAG}.json"

# 4) 快速结构检查（无用例或无映射即阻断）
rg -n "TC-" "docs/project_control/TEST_CASE_SPEC_${PHASE_TAG}.md"
rg -n "\"phase\"\\s*:\\s*\"${PHASE_TAG}\"|\"traceability\"" "tmp/plan/test_traceability_${PHASE_TAG}.json"
```

```bash
# 5) 可选：将“测试设计已完成”写入任务证据（建议仅对当前执行任务写）
.venv/bin/python sync_pm_status.py \
  --update-task <task_id> \
  --test-evidence "test-case designed: TEST_CASE_SPEC_${PHASE_TAG}.md"
```

```bash
# 6) 阶段末（可选）更新里程碑进度
.venv/bin/python sync_pm_status.py --update-milestone-progress "${MILESTONE_ID}"
```

### 1.5.6 `test_traceability_<phase>.json` 推荐 Schema（统一格式）

```json
{
  "phase": "P1.phase0",
  "generated_at": "2026-02-17T15:30:00",
  "source_files": {
    "wbs": "tmp/plan/wbs_P1.phase0.md",
    "acceptance": "docs/project_control/ACCEPTANCE.md",
    "contract": "docs/project_control/PHASE_CONTRACT_P1.phase0.md",
    "test_case_spec": "docs/project_control/TEST_CASE_SPEC_P1.phase0.md"
  },
  "summary": {
    "wbs_task_count": 0,
    "test_case_count": 0,
    "unmapped_wbs_tasks": 0,
    "unmapped_acceptance_items": 0
  },
  "traceability": [
    {
      "wbs_task_id": "P1.phase0-T01",
      "wbs_task_name": "冻结第一阶段唯一运行时链路与入口清单",
      "risk_level": "P0",
      "acceptance_refs": [
        "ACPT-P1-CHAIN-UNIQUE"
      ],
      "test_cases": [
        {
          "id": "TC-P1P0-001",
          "level": "IT",
          "type": "功能测试",
          "priority": "P0",
          "spec_ref": "docs/project_control/TEST_CASE_SPEC_P1.phase0.md#tc-p1p0-001",
          "command": "pytest -q database_service/tests/streams/test_stream_config.py",
          "expected": "pass"
        }
      ],
      "coverage": {
        "positive": true,
        "negative_or_boundary": true
      }
    }
  ],
  "gaps": [],
  "gate_ready": true
}
```

字段约束（MUST）：

- 顶层字段必须包含：`phase,generated_at,source_files,summary,traceability,gaps,gate_ready`。
- `traceability` 中每个 `wbs_task_id` 必须唯一，且至少绑定 1 条 `test_cases`。
- `risk_level` 为 `P0/P1` 的任务，`coverage.negative_or_boundary` 必须为 `true`。
- `summary.unmapped_wbs_tasks` 或 `summary.unmapped_acceptance_items` > 0 时，`gate_ready` 必须为 `false`。

## STEP 1.8 —— Feature 设计（不写业务代码）
基于 `STEP 1` 的 `wbs_<phase>.md` 与 `STEP 1.5` 的测试映射，调用 `feature` 技能生成任务级实现设计契约，再进入实施。

### 1.8.1 输入

- `tmp/plan/wbs_<phase>.md`
- `tmp/plan/test_traceability_<phase>.json`
- `docs/project_control/PRD.md`
- `docs/project_control/ACCEPTANCE.md`
- `docs/project_control/PHASE_CONTRACT_<phase>.md`

### 1.8.2 产出

- `docs/project_control/FEATURE_SPEC_<phase>.md`
- `tmp/feature_traceability_<phase>.json`
- `tmp/feature_validation_report_<phase>.json`

### 1.8.3 角色边界（防重复，MUST）

- `WBS`：定义任务集合、依赖、顺序（What）
- `feature`：定义接口/数据/错误处理/回滚/测试执行入口（How）
- 若 `wbs_<phase>.md` 出现实现细节，或 `FEATURE_SPEC_<phase>.md` 出现越界任务，必须退回修订。

### 1.8.4 进入 STEP 2 的门禁（MUST）

- `feature_validation_report_<phase>.json` 中 `gate_ready=true`；
- `feature_traceability_<phase>.json` 中每个任务条目使用统一键 `task_id`，且均映射：
  - `requirement_ids`
  - `acceptance_ids`
  - `test_case_ids`
  - `test_commands`
- 不允许存在“在 WBS 内但无 feature 映射”的任务；
- 不允许存在“在 feature 内但不在 WBS 子集”的任务。
- 不允许仅存在通用文件 `FEATURE_SPEC.md` 而缺少阶段文件 `FEATURE_SPEC_<phase>.md`。
- `FEATURE_SPEC_<phase>.md` 标题必须包含当前 phase（例如 `P1.phase1`），否则判定阶段一致性失败。

新增阶段级测试追踪硬门禁（MUST）：

```bash
.venv/bin/python scripts/verify_phase_test_traceability_gate.py \
  --phase "${PHASE_TAG}" \
  --test-traceability "tmp/plan/test_traceability_${PHASE_TAG}.json" \
  --feature-traceability "tmp/feature_traceability_${PHASE_TAG}.json" \
  --tests-root "database_service/tests"
```

规则：
- 每个任务在 `test_traceability` 与 `feature_traceability` 都必须存在映射；
- 两侧都必须包含 `pytest` 命令；
- 禁止 `rg/grep/sed/awk/cat` 作为唯一主测试证据（允许辅助检索）；
- 所有 `TC-ID` 必须能在测试文件中检索到；
- 任一失败，禁止进入 `STEP 2`。

### 1.8.5 标准命令模板（可直接复用）

```text
# 1) 调用 feature 技能（由执行器完成）
输入：
- tmp/plan/wbs_<phase>.md
- tmp/plan/test_traceability_${PHASE_TAG}.json
- docs/project_control/PRD.md
- docs/project_control/ACCEPTANCE.md
- docs/project_control/PHASE_CONTRACT_${PHASE_TAG}.md

输出：
- docs/project_control/FEATURE_SPEC_${PHASE_TAG}.md
- tmp/feature_traceability_${PHASE_TAG}.json
- tmp/feature_validation_report_${PHASE_TAG}.json
```

```bash
# 2) 产物存在性检查（缺一即阻断）
test -f "docs/project_control/FEATURE_SPEC_${PHASE_TAG}.md"
test -f "tmp/feature_traceability_${PHASE_TAG}.json"
test -f "tmp/feature_validation_report_${PHASE_TAG}.json"

# 3) 结构校验（失败即阻断）
.venv/bin/python scripts/validate_feature_artifacts.py \
  --traceability "tmp/feature_traceability_${PHASE_TAG}.json" \
  --report "tmp/feature_validation_report_${PHASE_TAG}.json" \
  --feature-spec "docs/project_control/FEATURE_SPEC_${PHASE_TAG}.md" \
  --phase "${PHASE_TAG}"
```

## STEP 1.x —— 多阶段参数化命令模板（phase1~phase4，可直接复制）

> 说明：以下模板用于快速切换 `P1.phase1 ~ P1.phase4`。  
> 约定：`PHASE_TAG` 与 `PHASE_CODE` 相同（如 `P1.phase1`）。

```bash
# 通用参数
PHASE_TAG="P1.phase1"   # 改为 P1.phase2 / P1.phase3 / P1.phase4
PHASE_CODE="${PHASE_TAG}"
MILESTONE_ID="<milestone_id>"
```

```bash
# A) 拉取阶段任务（真源）
.venv/bin/python sync_pm_status.py \
  --fetch-tasks \
  --task-prefix "${PHASE_CODE}" \
  --status "Todo,Doing,In review" \
  --output "tmp/${PHASE_TAG}_active_tasks.json"
```

```bash
# B) 测试映射与 feature 产物检查
test -f "tmp/plan/test_traceability_${PHASE_TAG}.json"
test -f "tmp/feature_traceability_${PHASE_TAG}.json"
test -f "tmp/feature_validation_report_${PHASE_TAG}.json"

.venv/bin/python scripts/validate_feature_artifacts.py \
  --traceability "tmp/feature_traceability_${PHASE_TAG}.json" \
  --report "tmp/feature_validation_report_${PHASE_TAG}.json" \
  --feature-spec "docs/project_control/FEATURE_SPEC_${PHASE_TAG}.md" \
  --phase "${PHASE_TAG}"
```

```bash
# C) 任务完成后同步（示例）
.venv/bin/python sync_pm_status.py \
  --update-task <task_id> \
  --test-evidence "phase=${PHASE_TAG}; qa-gate passed"

.venv/bin/python sync_pm_status.py \
  --update-task <task_id> \
  --status-value "In review" \
  --test-files "tests/path/test_x.py,tests/path/test_y.py"

.venv/bin/python sync_pm_status.py --update-milestone-progress "${MILESTONE_ID}"
```

分阶段速查（可直接替换）：

```text
phase1: PHASE_TAG=P1.phase1
phase2: PHASE_TAG=P1.phase2
phase3: PHASE_TAG=P1.phase3
phase4: PHASE_TAG=P1.phase4
```

## STEP 2 —— 按任务循环执行（专注执行）
对每一个从真源获取的任务，严格执行以下子步骤：

进入 STEP 2 前置条件（MUST）：
- `test_traceability_<phase>.json` 与 `feature_traceability_<phase>.json` 均已生成；
- 两者对当前任务的 `task_id` 映射均存在；
- 当前任务对应 `TC-ID` 的可执行测试脚本已在仓库就绪（不得等到实现中途才补）；
- 任一映射缺失时，禁止开始任务实现。

Autopilot 追加规则（MUST）：

- 若映射缺失：自动回退到 `STEP 1.5/1.8` 补齐产物并重试，不中断。
- 若校验失败：自动执行 `bugfix/refactor` 最小修复并回到当前任务复验。
- 每次回退必须写入 `tmp/runs/<run_id>/events.log`。

### 2.1 任务开始

更新 Notion 任务状态为 Doing
.venv/bin/python sync_pm_status.py --update-task <task_id> --status-value "Doing"

### 2.2 实施最小改动

仅实现任务要求的最小功能集

保持系统始终可运行（每次改动后可编译/可运行）

遵循 TDD 原则：先写测试，后实现

### 2.2.1 执行期测试规则（MUST）

`STEP 2` 不承担测试准备职责；测试脚本预置必须在 `STEP 1.5` 完成。  
`STEP 2` 只做执行闭环：运行预置测试（先失败/确认失败证据）-> 最小实现 -> 回归验证 -> 证据归档。
若进入 `STEP 2` 时发现当前任务测试脚本未预置，必须立即回退 `STEP 1.5` 补齐，不得继续当前任务实现。

执行顺序（每个任务）：

1. 从 `TEST_CASE_SPEC_<phase>.md` 选择当前任务对应 `TC-ID`。
2. 从 `feature_traceability_<phase>.json` 读取本任务 `test_commands` 与实现约束。
3. 运行预置自动化测试并保留先失败证据（若已通过则记录“预置测试已通过”证据）。
4. 实现最小代码改动使目标测试通过。
5. 运行 `qa-gate` 与本阶段必跑命令。
6. 将通过结果写入 `--test-evidence`。

本地硬门禁（新增，MUST，前置于任何 Notion 状态写入）：

在任务开始实现前，必须先执行以下校验；任一失败立即阻断当前任务，不得继续实现/qa-gate/状态更新：

```bash
.venv/bin/python scripts/verify_task_test_gate.py \
  --task-id <task_id> \
  --traceability tmp/feature_traceability_<phase>.json \
  --test-files "tests/path/test_x.py,tests/path/test_y.py"
```

随后必须执行测试质量门禁（MUST）：

```bash
.venv/bin/python scripts/verify_behavior_test_quality.py \
  --task-id <task_id> \
  --traceability tmp/feature_traceability_<phase>.json \
  --test-files "tests/path/test_x.py,tests/path/test_y.py"
```

要求：
- `--test-files` 必须显式传入，且至少 1 个文件；
- 每个测试文件必须真实存在、出现在当前 `git diff` 中；
- 每个测试文件必须包含 `TC-ID` 可追溯标记（测试名/注释/参数化 id 任一）；
- `feature_traceability_<phase>.json` 的本任务 `test_commands` 必须包含 `pytest`，且覆盖传入的每个 `--test-files`。
- 禁止将 `rg/grep/sed/awk/cat` 结果作为 `P0/P1` 任务主测试证据；允许仅用于辅助定位。
- 禁止“源码/文档字符串断言型伪测试”（只读 `.py/.md` 文本并断言包含关键字）作为 `P0/P1` 的主测试脚本。
- `P0/P1` 每个 `TC-ID` 至少要有 1 个可执行行为测试（输入->执行->结果断言），不得仅有静态契约断言。
- 涉及 Redis/数据库/LLM/关键外部 API 的任务，测试必须走真实依赖链路：`execution_mode=real`、`allow_mock=false`（与 `test-case`/`feature` 技能一致），不得以 mock/stub/fake 结果作为主验收证据。
- 复合需求任务（多组件/跨边界）每个 `TC-ID` 必须至少覆盖：主路径成功、关键失败路径、边界/异常输入三类场景；缺任一类即判定测试质量不足。
- 若任务包含幂等/重试/超时/并发语义，对应测试必须显式断言这些语义（例如 duplicate-skip、retry 上限、timeout fail-fast、并发一致性），不得只断言“返回成功”。
- 必须保留“先测后改”的失败证据：在业务实现改动前，至少一次目标测试执行记录（可为 `FAILED` 或 `XFAIL`），并在任务目录写入可追溯结果文件（如 `tmp/runs/<run_id>/tests_pre_impl_<task_id>.log`）。
- 通过证据必须是可执行测试输出（pytest/junit/覆盖率报告）；不允许用人工描述替代机读结果。
- 集成测试必须优先复用既有基线脚本（优先参考 `database_service/scripts/test_theme_processor.py`）：默认在现有文件新增 `test_*` 函数，禁止无理由新建平行测试脚本。
- 新建集成测试文件仅允许三类豁免：职责边界不匹配、存在循环依赖风险、现有文件超维护阈值（如 >800 行）且已记录拆分理由。
- 若未复用基线脚本且无豁免记录，直接判定 `verify_behavior_test_quality.py` 不通过。
- 涉及数据库的行为测试，默认必须连接 `stock_data_test`（除非合同明确指定其他库），不得误连 `stock_data` 或临时自建库。
- 编写数据库相关测试脚本前，必须先读取并对齐 `docs/architecture/*.sql`（至少包含 `*_schema.sql`），测试断言需符合真实字段/约束（如 `financial_categories`、`theme_master`）。
- 禁止“自造简化表结构 + 自定义临时 gateway”替代项目现有数据库访问层；必须优先复用现有 `PostgresDatabaseManager/DatabaseGateway` 与既有 fixture/helper。
- `tests_pre_impl_<task_id>.log` 的先失败证据必须来自目标 `TC-ID` 的行为断言失败，不得用“依赖不可达/DNS失败”充当业务先失败证据。

门禁规则（MUST）：

- `P0/P1` 任务必须至少新增或更新 1 个自动化测试（pytest/集成测试脚本）。
- 测试脚本需可追溯到 `TC-ID`（测试名、注释或参数化ID中至少一种）。
- 若仅更新业务代码而无对应测试变更，任务状态不得进入 `done`。
- 若测试脚本已新增但未纳入执行命令，任务状态不得进入 `In review/done`。
- `sync_pm_status.py` 对 `P0/P1` 任务在写入 `In review/done` 前会执行 tests 变更门禁；未检测到测试脚本变更将直接失败。
- `P0/P1` 任务在写入 `In review/done` 时必须显式传入 `--test-files`，且这些文件必须出现在当前 git diff 中。
- 上述规则不得仅依赖 `sync_pm_status.py --update-task` 时触发，必须在 STEP 2 本地先行触发一次硬门禁。
- `verify_task_test_gate.py` 与 `verify_behavior_test_quality.py` 任一失败，禁止进入 `qa-gate` 与状态更新。
- `verify_behavior_test_quality.py` 必须对“场景覆盖维度 + 关键语义断言 + 真实依赖约束 + 先失败证据”做综合判定；任一缺失视为不通过。

### 2.2.2 测试先行强制规则（新增，MUST）

每个任务进入实现前，必须完成：

1. 从 `test_traceability_<phase>.json` 定位本任务映射的 `TC-ID`；
2. 从 `feature_traceability_<phase>.json` 定位本任务映射的 `test_commands`；
3. 先新增/更新自动化测试脚本（可追溯到 `TC-ID`）；
4. 再做最小代码实现并使测试通过。

注意：

- 禁止用 `eval` 执行 traceability 中的命令；
- 允许“已有测试本来就通过”的场景，门禁判定依据是“测试脚本已新增/更新且可覆盖本任务改动”，不是机械要求“必须先失败”。

### 2.2.3 覆盖率门禁（新增，SHOULD）

默认要求：

- 覆盖率不得下降（沿用 4.3）；
- `P0/P1` 任务必须证明“新增代码有测试覆盖”。

推荐命令（按仓库目录）：

```bash
.venv/bin/pytest tests/ -v --cov=database_service --cov=theme_service --cov-report=term-missing
```

### 2.3 即时验证

#### 1. 每次改动后必须运行：

**调用 `qa-gate` 技能来执行质量门禁检查**

#### 2. 如果 QA 验证未通过：

**执行 `bugfix` 技能或重构**

然后必须进入“重新验证”子步骤后，再回到 `qa-gate`，禁止跳过复验直接推进任务状态。

#### 2.4 记录测试证据
将验证结果写入 Notion：

- 更新测试证据
.venv/bin/python sync_pm_status.py \
  --update-task <task_id> \
  --test-evidence "tests/test_auth.py::test_jwt_validation PASSED"

### 2.5 任务完成
满足 DoD Checklist 后，必须实时更新任务状态，不得延后到阶段末统一处理。

决策分支（唯一生效）：

- 若需人工验收/评审：状态设为 `In review`
- 若无需人工验收且门禁通过：状态设为 `done`

实时同步顺序（MUST）：

1. 先更新测试证据（必做，P0/P1）  
.venv/bin/python sync_pm_status.py --update-task <task_id> --test-evidence "<text>"

2. 再更新任务状态  
.venv/bin/python sync_pm_status.py --update-task <task_id> --status-value "<In review|done>" --test-files "tests/path/test_x.py,tests/path/test_y.py"

3. 更新里程碑进度  
.venv/bin/python sync_pm_status.py --update-milestone-progress <milestone_id>

时效要求（MUST）：

- 任务满足 DoD 后，60 秒内完成上述 1~3 步。
- 任一步失败，禁止进入下一任务，必须进入重试或离线补偿流程。
- 若状态写入失败并提示缺少 Test Evidence，必须先补写 `--test-evidence` 后重试状态写入；禁止跳过。

失败处理（MUST）：

- 在线失败：最多重试 3 次（指数退避）。
- 仍失败：写入 `tmp/offline_payload.json`，标记 `pending_sync=true`，并输出阻断告警。

Autopilot 失败处理增强（MUST）：

- 在线失败默认重试 5 次（`1,2,4,8,16` 秒）。
- Notion 写入失败不阻断主线实现：写入离线队列并继续下一个子步骤。
- 当前任务完成前必须至少完成一次“补偿回放尝试”。
- 仅在 `STEP 5.2` 前执行最终补偿清零校验。

### 2.5.1 任务状态机（增强版，MUST）

```
Todo -> Doing -> (Blocked <-> Doing) -> (In review | done)
In review -> (done | Doing)
```

状态流转规则：

- `Todo -> Doing`：任务开始；
- `Doing -> Blocked`：出现阻塞；
- `Blocked -> Doing`：阻塞已解除；
- `Doing -> In review`：需人工评审；
- `Doing -> done`：无需评审且门禁全部通过；
- `In review -> done`：评审通过；
- `In review -> Doing`：评审未通过返工。

实现要求：

- 使用 `Blocked` 前，必须确认 Notion `Status` 选项中存在该值；
- 若状态值不存在，禁止写入并改走 `Doing + test-evidence` 标记阻塞原因。

### 2.5.3 指数退避重试（增强，MUST）

对 `sync_pm_status.py` 写操作（更新状态/证据/里程碑）统一采用最多 3 次重试（1s/2s/4s）。

```bash
retry_with_backoff() {
  local max_attempts=3
  local attempt=1
  local wait_s=1
  # 仅允许“参数数组”形式，禁止传入复合 shell 字符串
  # 用法: retry_with_backoff .venv/bin/python sync_pm_status.py --update-task ...
  local -a cmd=("$@")
  while [ $attempt -le $max_attempts ]; do
    if "${cmd[@]}"; then
      return 0
    fi
    sleep $wait_s
    attempt=$((attempt+1))
    wait_s=$((wait_s*2))
  done
  return 1
}
```

### 2.6 In review 与 done 的判定标准

使用 `In review` 的唯一条件：

- 任务需要人工审批（代码评审/业务验收/架构评审）尚未完成。

使用 `done` 的唯一条件：

- DoD 全部满足；
- 本阶段必需验证项通过；
- 无阻断缺陷；
- 不再依赖后续人工审批。

## STEP 3 —— 验证（阶段级）
完成所有任务后，执行完整验证：

### 3.1 完整测试套件

- 运行所有测试
.venv/bin/pytest tests/ -v --cov=src --cov-report=html

- 运行 lint
.venv/bin/flake8 src/ tests/

- 类型检查
.venv/bin/mypy src/

- 构建验证（如有）
.venv/bin/python build.py --verify

### 3.2 验证结果记录

将验证摘要写入临时文件
tmp/validation_summary.json 

{
  "test_summary": {
    "total": 150,
    "passed": 148,
    "failed": 2,
    "skipped": 0,
    "coverage": 87.5
  },
  "lint_summary": {
    "errors": 0,
    "warnings": 3
  },
  "build_status": "success"
}

### 3.3 失败处理规则
验证失败必须修复后才能继续

记录失败原因到 tmp/failures.log

必要时创建新的 Notion 任务跟踪问题

## STEP 4 —— 报告生成

### 4.1 生成阶段报告

调用 `test-reports`，生成测试报告

### 4.2 同步报告到 Notion

- 创建或更新 Phase Report：
.venv/bin/python sync_pm_status.py \
  --create-report \
  --milestone-id <milestone_id> \
  --report-file docs/project_control/reports/phase-XX.md \
  --status-value "Draft"

- 报告状态更新（MUST）：
.venv/bin/python sync_pm_status.py \
  --update-report <report_id> \
  --report-status "<Draft|Submitted|Reviewed|Approved|Rework>"

规则（MUST）：
- `Published` 不是合法状态值，禁止使用。
- 报告文件必须使用可解析章节，至少包含：`## 1. 目标与范围`、`## 2. 变更文件清单`、`## 3. 验证命令与结果`、`## 4. 风险与限制`。
- 未创建报告或报告状态未更新为目标值（推荐 `Approved`）时，不得进入 `STEP 5.2`。

固定执行模板（MUST）：

```bash
# 1) 创建报告（获取 report_id）
.venv/bin/python sync_pm_status.py \
  --create-report \
  --milestone-id <milestone_id> \
  --report-file docs/project_control/reports/phase-<phase>.md \
  --status-value "Draft"

# 2) 更新报告状态到合法终态（推荐 Approved）
.venv/bin/python sync_pm_status.py \
  --update-report <report_id> \
  --report-status "Approved"
```

### 4.3 更新评审关联

#### 如果有评审任务，关联报告
.venv/bin/python sync_pm_status.py \
  --link-report-to-review \
  --report-id <report_id> \
  --review-id <review_id>

## STEP 5 --- 门禁停止与等待验收

### 5.1 输出 Review Checklist

#### 阶段验收清单

#### 功能完整性
- [ ] 所有计划任务已完成
- [ ] 验收目标达成
- [ ] 用户场景验证通过

#### 质量门禁
- [ ] 单元测试通过（148/150）
- [ ] Lint 检查通过（0 errors）
- [ ] 类型检查通过
- [ ] 构建成功

#### 架构合规
- [ ] 无 Schema 破坏性变更
- [ ] 遵循 ADR 决策
- [ ] 向后兼容

#### 文档完备性
- [ ] 代码注释完整
- [ ] API 文档更新
- [ ] 阶段报告生成

#### 可运维性
- [ ] 回滚方案可行
- [ ] 监控指标已添加
- [ ] 日志记录完善

### 5.2 等待用户决策
必须停止执行，等待用户输入以下之一：

决策	含义	后续动作
ACCEPT	验收通过	可进入下一阶段
REWORK	需要返工	返回 STEP 2 修改指定任务
REQUEST CHANGES	需求变更	更新任务真源后重新执行
APPROVED WITH NOTES	有条件通过	记录备注后继续

Autopilot 规则：

- 运行到 `STEP 5.2` 前不得因普通错误中断；
- 在 `STEP 5.2` 必须暂停并等待用户验收决策（这是唯一常规暂停点）；
- 若用户未响应，保持可恢复状态并支持 `--resume <run_id>`。

### 5.3 决策记录

- 将用户决策记录到 Notion
.venv/bin/python sync_pm_status.py \
  --record-decision \
  --milestone-id <milestone_id> \
  --decision "{user_input}" \
  --notes "{user_notes}"

- `ACCEPT` 场景禁止用单一脚本封装在线步骤；必须由执行器顶层逐条执行在线命令（A/C）。

### 5.4 更新项目状态（实时 + 对账补偿）

流程演练（flow-check）规则：

- 仅做技能链路验证时，更新任务状态命令必须增加 `--flow-check`。
- `--flow-check` 默认不改真实任务状态（dry-run），避免污染任务看板。
- 演练 run 结束后，若需要真实落库状态，必须去掉 `--flow-check` 重新执行。

#### 5.4.1 实时更新（主路径，MUST）

每个任务完成时立即执行：

1) 更新测试证据（先执行）  
.venv/bin/python sync_pm_status.py --update-task <task_id> --test-evidence "测试通过"

2) 如果可直接完成 -> done（必须传 test-files）  
.venv/bin/python sync_pm_status.py --update-task <task_id> --status-value "done" --test-files "tests/path/test_x.py,tests/path/test_y.py"

3) 更新里程碑进度  
.venv/bin/python sync_pm_status.py --update-milestone-progress <milestone_id>

- 按阶段过滤更新里程碑进度（推荐用于阶段内核算）
.venv/bin/python sync_pm_status.py --update-milestone-progress <milestone_id> --phase-filter "phase 0"

#### 5.4.2 阶段末对账补偿（兜底，MUST）

1. 找出“DoD已满足但状态非done”的任务并补更新为done。

2. 再次更新里程碑进度。

3. 输出对账报告到 `tmp/reconcile_report.json`。

4. 对账口径必须以 `--milestone-id` 全量拉取为准，再本地筛选 phase 任务；不能仅依赖 `--task-prefix + --status`（避免漏数）。

5. 阶段收口硬校验（MUST）：
- 对当前 phase 的任务集合执行本地筛选；
- 若存在任意任务状态不是 `done`，禁止进入 `STEP 5.2`，必须回到 STEP 2 补齐；
- 若 `--task-prefix` 返回空，不得直接判定“已完成”，必须执行 `--milestone-id` 全量拉取复核。

5.1 无活跃任务分支限制（MUST）：
- 若 `--task-prefix + active-status` 返回 0，不得直接跳过“测试实现规则”进入收口；
- 必须先执行 `scripts/verify_phase_test_traceability_gate.py`；
- 若脚本失败，必须进入 REWORK（修正 traceability 与测试脚本），禁止进入 `STEP 5.2`。

6. 报告同步硬校验（MUST）：
- 必须存在本阶段 report 页面ID；
- 必须完成 `--create-report`；
- 必须完成 `--update-report` 到合法终态（推荐 `Approved`）；
- 任一缺失时，禁止进入 `STEP 5.2`。

7. 进入 `STEP 5.2` 前执行硬校验脚本（MUST）：
```bash
.venv/bin/python scripts/verify_phase_closeout_gate.py \
  --phase-prefix "<phase_prefix>" \
  --tasks-json tmp/<phase_prefix>_milestone_tasks.json \
  --expected-task-ids-json tmp/plan/feature_traceability_<phase_prefix>.json \
  --report-id <report_id> \
  --report-status "Approved"
```
- `--tasks-json` 必须来自 `--milestone-id` 全量拉取；
- `--expected-task-ids-json` 必须来自本阶段 traceability 真源（不得手写临时列表）；
- 脚本返回非 0 时，禁止进入 `STEP 5.2`。

8. 阶段收口固定顺序（MUST）：
1) `--milestone-id` 全量拉取任务到 `tmp/<phase_prefix>_milestone_tasks.json`  
2) `scripts/verify_phase_test_traceability_gate.py`（即使无活跃任务也必须执行）  
3) `--create-report`  
4) `--update-report` 到合法终态（推荐 `Approved`）  
5) `scripts/verify_phase_closeout_gate.py`（含 expected task set 一致性校验）  
6) 仅当 1~5 全通过，才允许进入 `STEP 5.2`

#### 5.4.3 ACCEPT 收尾固定序列（新增，MUST）

目标：避免 `ACCEPT` 后因命令形态不匹配授权前缀而触发外网中断。

规则：
- 在线命令与本地状态命令必须拆分执行，禁止混写在同一复合 shell。
- `sync_pm_status.py` 在线命令必须为单段命令，不得包裹 `if/&&/||/;`、管道、`bash -lc`。
- 在线命令禁止使用命令替换（如 `$(...)`、反引号）；运行参数必须在本地预先解析为字面量字符串后再执行。
- `network_channel=escalated_locked` 时，ACCEPT 在线步骤必须使用 `sync_pm_status.py` 原子命令执行（MUST）：
  - `.venv/bin/python sync_pm_status.py --accept-closeout --milestone-id <id> --decision ACCEPT --notes "<notes>" --output tmp/runs/<run_id>/post_accept_fetch.json --summary-output tmp/runs/<run_id>/accept_online_summary.json`
- 上述命令必须以外网授权模式执行，禁止在已锁定通道上退回普通执行。
- 本地状态落盘必须通过本地脚本执行（不触网）。
- 若本 run 在 preflight 阶段已触发一次外网授权探测（`preflight_escalation_probe`），则 `ACCEPT` 阶段在线步骤 A/C 必须沿用同一外网执行通道；不得回退到受限网络通道。
- 通道锁定规则（MUST）：一旦 run 在任一步骤使用过外网授权通道，`state.json` 必须视为 `network_channel=escalated_locked`；后续所有在线命令（尤其 A/C）都必须使用同一通道执行，直到 run 结束。
- 执行器实现要求（MUST）：`ACCEPT` 阶段 A/C 在线命令必须显式以“外网授权执行模式”调用；禁止默认普通执行后再失败补偿。

固定执行序列（必须按序）：
1. Step A/C（在线，合并）  
   `.venv/bin/python sync_pm_status.py --accept-closeout ... --summary-output tmp/runs/<run_id>/accept_online_summary.json`
2. Step B/D（本地）  
   读取 `accept_online_summary.json` 中 `record_decision_rc/fetch_rc`，再执行：  
   `.venv/bin/python scripts/run_accept_sequence.py --run-id <run_id> --milestone-id <id> --decision ACCEPT --notes "<notes>" --record-decision-rc <0|1> --fetch-rc <0|1>`

本地脚本模板（仅 B/D，不触网）：
.venv/bin/python scripts/run_accept_sequence.py \
  --run-id <run_id> \
  --milestone-id <id> \
  --decision ACCEPT \
  --notes "<notes>" \
  --record-decision-rc <0|1> \
  --fetch-rc <0|1>

复合 shell 拒绝规则（MUST）：
- 若检测到在线命令字符串包含 `&&`、`||`、`;`、`|`、`if `、`bash -lc`，执行器必须拒绝执行该命令，并改写为固定序列后重试。
- 拒绝行为必须记录到 `tmp/runs/<run_id>/events.log`，事件名：`reject_composite_online_command`。
- 每条在线命令执行前必须先跑：
  `.venv/bin/python scripts/verify_online_command_guard.py --cmd "<literal_online_command>"`
- guard 返回非 0 时，禁止执行该在线命令。
- 若检测到任意本地脚本（`scripts/*.py`）内部通过 `subprocess` 间接调用 `sync_pm_status.py`，执行器必须拒绝该脚本路径并改为顶层在线调用；事件名：`reject_nested_online_command`。
- 若检测到 run 已锁定 `network_channel=escalated_locked`，但当前在线命令未走外网授权执行模式，执行器必须拒绝执行；事件名：`reject_channel_downgrade`。
- 若 ACCEPT 阶段未使用 `sync_pm_status.py --accept-closeout`，执行器必须拒绝执行；事件名：`reject_non_atomic_accept_online`.
- 若检测到在线命令包含 `$(...)` 或反引号命令替换，执行器必须拒绝执行并先本地求值后再以字面量重试；事件名：`reject_command_substitution_online`。

### 5.5 自动决策矩阵（新增，MUST）

`--mode autopilot` 下按下表自动处理，不请求人工确认：

| 场景 | 自动动作 | 终止条件 |
| --- | --- | --- |
| 缺少 `test_traceability` | 回退 `STEP 1.5` 生成并重试 | 连续 3 次生成失败 |
| 缺少 `feature_traceability` | 回退 `STEP 1.8` 生成并重试 | 连续 3 次生成失败 |
| `qa-gate` 失败 | 调用 `bugfix/refactor` + 复验循环 | 同一任务复验 5 次失败 |
| Notion 写入失败 | 入离线队列 + 继续执行 + 阶段末补偿 | 阶段末补偿后仍失败 |
| 测试命令失败 | 自动收集日志 + 最小修复 + 重跑 | 达到最大重试次数 |

达到终止条件后，若不在中断白名单内，仍需先产出失败证据包再进入 `STEP 5.2`。

### 5.6 阶段成果包（新增，MUST）

进入 `STEP 5.2` 前，必须自动生成：

- `docs/project_control/reports/phase-<phase>.md`
- `tmp/runs/<run_id>/validation_summary.json`
- `tmp/runs/<run_id>/reconcile_report.json`
- `tmp/runs/<run_id>/gate_decision.json`
- `tmp/runs/<run_id>/pending_sync.json`（若为空也需生成）

`gate_decision.json` 最小字段：

```json
{
  "phase": "P1.phase0",
  "run_id": "20260217_193000",
  "gate_ready": true,
  "blocking_issues": [],
  "generated_at": "2026-02-17T19:45:00Z"
}
```

## 3. Notion 同步规则

## 3.1 ⚠️ 重要说明：两个不同的 status 参数

1. **`--status`**：用于获取任务列表时的状态过滤
   - 示例：`.venv/bin/python sync_pm_status.py --fetch-tasks --status "Todo,Doing"`
   - 说明：可以指定多个状态，用逗号分隔

2. **`--status-value`**：用于更新任务时的状态值
   - 示例：`.venv/bin/python sync_pm_status.py --update-task <task_id> --status-value "Doing"`
   - 说明：只能指定单个状态值

补充：

- `--status` 仅用于查询过滤，不能用于写入；
- 若查询 `done` 结果异常为空，必须回退到 `--milestone-id` 全量拉取后本地筛选校验。

3. 在 Notion 操作中，有两种完全不同的 ID，**绝对不能混用**：

| ID 类型 | 说明 | 示例 | 用途 |
|---------|------|------|------|
| **数据源ID** | 整个数据库的ID | `3047bab0-ee1d-803a-a252-000b9489ab7d` | 用于 `parent={"data_source_id": ...}` 创建页面 |
| **页面ID** | 具体某个页面的ID | `3067bab0-ee1d-8184-84a6-d3e06f82506a` | 用于 `--update-task`、`--milestone-id` 过滤 |
  
  - 方法1：先获取所有里程碑列表
  .venv/bin/python sync_pm_status.py --fetch-tasks --data-source milestones --output tmp/milestones.json

  - 方法2：查看任务的 milestone_id 字段
  .venv/bin/python sync_pm_status.py --fetch-tasks --output tmp/tasks.json

## 3.2 允许的同步脚本
仅允许调用以下本地同步脚本：

脚本用途示例:

- 任务状态/进度/报告同步	
.venv/bin/python sync_pm_status.py --fetch-tasks sync_pm_plan.py	

- 计划同步	
.venv/bin/python sync_pm_plan.py tmp/pm_plan_payload.json
sync_arch_review.py	

- 架构评审同步	
.venv/bin/python sync_arch_review.py tmp/arch_review_payload.json

## 3.3 同步命令汇总

- 获取任务列表:
  - 按任务前缀过滤
    .venv/bin/python sync_pm_status.py --fetch-tasks --task-prefix "P1.phase0" --output tmp/p1_phase0_tasks.json

  - 按里程碑名称过滤
    .venv/bin/python sync_pm_status.py --fetch-tasks --milestone-name "第一阶段" --output tmp/phase1_tasks.json

  - 按阶段过滤
    .venv/bin/python sync_pm_status.py --fetch-tasks --phase "phase 1" --output tmp/phase1_tasks.json

  - 组合过滤（前缀+状态）
    .venv/bin/python sync_pm_status.py --fetch-tasks --task-prefix "P1.phase0" --status "Todo,Doing" --output tmp/p1_phase0_active.json

  - 组合过滤（前缀+状态）
    .venv/bin/python sync_pm_status.py --fetch-tasks --milestone-id <id> --output tmp/tasks.json

- 更新任务状态
.venv/bin/python sync_pm_status.py --update-task <task_id> --status-value <new_status>

- 更新测试证据
.venv/bin/python sync_pm_status.py --update-task <task_id> --test-evidence "<text>"
里程碑操作

- 更新里程碑进度
.venv/bin/python sync_pm_status.py --update-milestone-progress <milestone_id>

- 更新所有里程碑进度
.venv/bin/python sync_pm_status.py --update-all-milestones

- 创建阶段报告
.venv/bin/python sync_pm_status.py --create-report --milestone-id <id> --report-file <path>

- 更新报告状态
.venv/bin/python sync_pm_status.py --update-report <report_id> --report-status <new_status>

## 3.4 重要规则
禁止直接 API 调用 Notion

禁止在代码中嵌入 Token

必须使用虚拟环境的 Python 解释器

必须处理网络失败情况（fallback 模式）

# 4. 工程纪律

## 4.1 编码规范
禁止静默重构（必须单独建任务）

禁止隐式假设（必须文档化）

禁止混合无关优化（一次只做一件事）

必须遵循项目的代码风格

## 4.2 架构纪律
发现架构问题必须建议新增 ADR

重大变更必须先更新架构文档

必须保持向后兼容

## 4.3 测试纪律
新功能必须有单元测试

修复 Bug 必须添加回归测试

测试覆盖率不得下降

# 5. 行为特征
本执行器必须表现为：

- 冷静	不急于完成，按步骤严格执行
- 可追溯	所有决策都有记录，所有操作都可回溯
- 风险优先	先识别风险，再开始执行
- 保守执行	宁可慢，不可错
- 审核驱动	每个阶段结束必须等待审核

Autopilot 补充行为（MUST）：

- 在非白名单错误下持续推进，不中断到用户层；
- 所有自动修复动作必须留痕（events + checkpoints）；
- 仅在 `STEP 5.2` 进入用户验收交互。

# 6. 离线 Fallback 模式
当网络访问失败时：

## 6.1 进入条件
Notion API 连续 3 次超时

用户拒绝授权重试

## 6.2 执行流程
生成离线 payload

- 将所有待同步数据写入本地文件

tmp/offline_payload.json 

{
  "task_updates": [],
  "milestone_updates": [],
  "reports": []
}

继续本地执行

使用本地任务列表继续开发

记录所有需要同步的变更

恢复后同步

- 网络恢复后执行批量同步
.venv/bin/python sync_pm_status.py --batch-sync tmp/offline_payload.json

## 6.3 离线队列管理（新增）

推荐目录结构：

```
tmp/offline/
├── queue/
├── processing/
├── failed/
└── done/
```

规则：

1. 每条离线操作写入独立 JSON，包含 `operation_type,target_id,payload_hash,idempotency_key,created_at`；
2. 消费时先移入 `processing/`，成功移入 `done/`，失败移入 `failed/`；
3. 同一 `idempotency_key` 仅允许处理一次（防重复回放）；
4. 队列回放失败超过阈值时必须阻断并告警。

## 6.4 Autopilot 补偿收口（新增，MUST）

`--mode autopilot` 下必须执行：

1. 每个任务结束后尝试一次离线队列回放；
2. 阶段末执行“全量补偿回放 + 对账”；
3. 将未完成补偿写入 `tmp/runs/<run_id>/pending_sync.json`；
4. 即使存在未补偿项，也要生成阶段成果包并在 `STEP 5.2` 等待验收决策。

# 7. 执行日志与监控（新增）

## 7.1 结构化日志（MUST）

关键动作必须写入结构化日志：

```text
timestamp|level|phase|task_id|action|status|duration|message
```

建议文件：

- `tmp/execution.log`：成功与过程日志
- `tmp/errors.log`：失败日志

## 7.2 进度快照（SHOULD）

每完成一个任务，更新 `tmp/progress_report.json`，至少包含：

- `phase/run_id/timestamp`
- `total/completed/in_progress/blocked`
- `milestone_progress`

# 8. 故障排除（新增）

| 错误 | 可能原因 | 解决方案 |
|------|---------|---------|
| `Could not find page with ID` | 使用了数据源ID而非页面ID | 先 `--fetch-tasks` 获取真实页面ID |
| `--status` vs `--status-value` 混淆 | 参数语义用错 | 查询用 `--status`，更新用 `--status-value` |
| `task-prefix` 查询不到 `done` | 过滤组合/脚本逻辑导致漏数 | 改用 `--milestone-id` 全量拉取后本地筛选 |
| 状态更新为 `Blocked` 失败 | Notion 状态未配置该选项 | 先在 Notion 增加 `Blocked`，或临时使用 `Doing + evidence` |
| `Completed Date is not a property` | 表结构无该字段 | 删除该字段写入逻辑，按现有 schema 更新 |

# 9. 快速参考卡片

## 常用命令速查

- 开始阶段
.venv/bin/python sync_pm_status.py --fetch-tasks --milestone-id <id>

- Autopilot 启动（建议）
  - 约定参数：`--mode autopilot --max-retries 5 --auto-reconcile true --stop-at step5.2`
  - 并创建 run 目录：`tmp/runs/<run_id>/`

- 进入 `STEP 5.2` 前的阶段收口（必须）
  - `.venv/bin/python sync_pm_status.py --fetch-tasks --milestone-id <id> --output tmp/<phase_prefix>_milestone_tasks.json`
  - `.venv/bin/python scripts/verify_phase_test_traceability_gate.py --phase <phase_prefix> --test-traceability tmp/plan/test_traceability_<phase_prefix>.json --feature-traceability tmp/feature_traceability_<phase_prefix>.json --tests-root database_service/tests`
  - `.venv/bin/python sync_pm_status.py --create-report --milestone-id <id> --report-file docs/project_control/reports/phase-<phase>.md --status-value Draft`
  - `.venv/bin/python sync_pm_status.py --update-report <report_id> --report-status Approved`
  - `.venv/bin/python scripts/verify_phase_closeout_gate.py --phase-prefix <phase_prefix> --tasks-json tmp/<phase_prefix>_milestone_tasks.json --report-id <report_id> --report-status Approved`

- Autopilot 续跑（建议）
  - 约定参数：`--mode autopilot --resume <run_id>`

- 处理任务
.venv/bin/python sync_pm_status.py --update-task <id> --status-value "Doing"

- 开发 
.venv/bin/python sync_pm_status.py --update-task <id> --status-value "In review"

- 更新进度
.venv/bin/python sync_pm_status.py --update-milestone-progress <id>

- 生成报告
.venv/bin/python sync_pm_status.py --create-report --milestone-id <id>

- 完成阶段

## 输出 Checklist 并等待用户决策
状态流转图

Todo → Doing → (Blocked) → In review → done
         ↓          ↓
     验证失败    解决阻塞

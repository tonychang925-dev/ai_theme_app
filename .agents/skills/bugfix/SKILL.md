---
name: bugfix
description: 当用户要“修复一个可复现 bug”，并希望给出定位、最小修复与测试验证时使用。
model: gpt-5
---

# Bugfix 协议（外科手术模式｜Surgical Mode）

本技能用于**确定性、最小影响面**地修复一个**可复现**的 Bug。

统一约束清单（跨技能一致）：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

角色定位：
- 调试专家（Debugging Specialist）
- 根因分析师（Root Cause Analyst）
- 稳定性守护者（Stability Guardian）

明确不做：
- 不相关重构（包括“顺手清理”）
- 架构升级与模块重写
- 新功能开发
- 与 Bug 无关的性能优化

核心原则：**只修这个 Bug，不做更多。**

---

## 0. 硬约束（Hard Constraints）

1. **必须在分支上修复**
   - 分支名：`codex/bugfix/<topic>`
   - 禁止直接改 `main/master`

2. **禁止无关改动**
   - 不改命名、不调格式、不做“顺便优化”
   - 任何额外改动必须被明确标记为“非本次修复范围”，并默认不执行

3. **禁止破坏性操作（未经用户批准）**
   - 不允许删除关键数据/表
   - 不允许不可逆迁移
   - 不允许大范围改 schema（除非证明“严格必要”）

4. **先解释根因，再写修复**
   - 未完成根因解释不得进入实现步骤

5. **先给最小 diff 方案，再落地**
   - 先输出“改哪些文件、改哪几行、为什么足够”
   - 若风险较高：必须等待用户明确“继续”后再改

## 0.1 快速开始（新增）

```bash
# 1) 锁定分支
git rev-parse --abbrev-ref HEAD

# 2) 最小复现（示例）
pytest -q -k "<bug_keyword>"

# 3) 修复后验证（示例）
pytest -q
```

---

## 1. STEP 1 — 复现（Reproduction）

必须产出：

1) **复现步骤**
- 从“干净状态”开始（例如：拉分支 / 安装依赖 / 启动服务）
- 以步骤列表形式给出（可复制执行）

2) **复现命令**
- 例如：`pytest -q -k test_xxx` / `python xxx.py` / `npm test`

3) **环境假设**
- OS / Python/Node 版本
- 依赖管理方式（conda/venv/poetry）
- 关键环境变量（不包含 secrets）

4) **证据采集**
- 错误信息（error）
- 堆栈（stack trace）
- 关键日志（logs）
- 触发输入（输入数据/HTTP 请求/消息体/样例新闻等）

**如果无法复现：**
- 必须说明“无法复现的原因假设”（缺输入/版本不一致/依赖差异等）
- 列出需要用户补充的最小信息
- 严禁无证据猜测

## 1.1 复现证据归档（新增，MUST）

每次 bugfix 必须至少保留以下证据（可写入阶段报告或临时文件）：

- 触发输入（最小样本）
- 失败命令与关键错误输出
- 运行环境快照（解释器版本/关键依赖版本）
- 复现成功时间戳

---

## 2. STEP 2 — 根因分析（Root Cause Analysis）

必须明确：

- 涉及文件（file）
- 涉及函数/类（function/class）
- 关键逻辑位置（行号可近似）
- 触发路径的数据流（data flow）
- 为什么会发生（why）

必须给出：

### Bug 类型分类（必选其一）
- 逻辑错误（Logic bug）
- 状态变更/副作用（State mutation bug）
- 并发/竞态（Concurrency bug）
- 边界条件（Boundary condition bug）
- None/空值（Null/None bug）
- Schema / 契约不一致（Schema mismatch）
- 性能阈值触发（Performance threshold issue）

**输出格式要求：**
- 先一句话结论（Root cause one-liner）
- 再展开 3–7 条要点（发生机制、触发条件、受影响面）

## 2.1 严重级别分流（新增，MUST）

- `P0`：阻断核心链路或数据正确性风险，必须优先处理并在修复后立即回归关键路径。
- `P1`：影响主要功能但有可行绕过，修复后需补齐回归测试与风险说明。
- `P2`：非核心或体验问题，可排入常规修复批次，但仍需最小回归验证。

---

## 3. STEP 3 — 最小修复方案（Minimal Fix Plan）

在修改代码之前，必须输出：

### 3.1 Diff 摘要（High-Level）
- 将修改的文件列表
- 预期改动范围（大约几行/哪些函数）
- 为什么这就是“最小改动”
- 为什么不会破坏其他路径（兼容性说明）

### 3.2 回滚策略（Rollback）
- 如何回滚（git revert / 回退提交）
- 若涉及数据变更：如何恢复

### 3.3 风险分级（Risk Level）
- Low / Medium / High
- 并解释依据（影响模块数、是否触及核心数据结构、是否改变 API 行为等）

**若 Risk=High：必须停下等待用户批准再改。**

---

## 4. STEP 4 — 实施（Implementation）

实施规则：

- 只做最小必要修改
- 不扩大行为边界（除非为修复 bug 且有验证）
- 保持抽象边界不被破坏
- 任何“想重构”的发现：只记录为备注，不在本次提交中执行

提交纪律：
- 小提交、可回滚
- 提交信息包含 bug 关键字：`fix: <topic> ...`

### 4.1 变更边界清单（新增，MUST）

实施前后必须明确：

- 本次允许修改的文件列表
- 本次明确禁止触达的模块列表
- 任何超出边界的改动都必须先升级为“新任务”而非并入当前 bugfix

---

## 5. STEP 5 — 验证（Verification）

必须执行并提供证据：

1) **复现步骤再跑一遍**
- 证明 bug 已消失

2) **必跑命令（按仓库实际）**
- 单测：`pytest -q`（或用户指定）
- Lint/Format：`ruff check` / `black --check`（或用户指定）
- 类型检查（如有）：`mypy`
- 集成/冒烟测试（如有）

3) **输出证据格式**
- Commands Run：逐条列出命令
- Key Outputs：只贴关键输出（通过/失败摘要、失败时关键错误段）

**若此前没有回归测试：**
- 必须新增一个**最小回归测试**（Regression test）
- 测试只覆盖本 bug 的触发条件与预期行为

### 5.1 测试门禁增强（新增，MUST）

1. `P0/P1` bugfix 必须有自动化回归测试（新增或更新）。  
2. 回归测试应可追溯到缺陷编号或 `TC-ID`（测试名/注释/参数化 ID 任一）。  
3. 若属于阶段执行任务，进入 `In review/done` 前需满足 `--test-files` + diff 门禁（见 9.1）。

---

## 6. STEP 6 — 回归风险评估（Regression Risk Assessment）

必须输出：

### 6.1 影响面（Impact Surface）
- 可能受影响的模块
- 触及的数据结构/契约
- API 行为是否改变（是/否；若是，说明兼容方案）
- 引入的新边界条件（如有）

### 6.2 风险等级
- Low / Medium / High
- 对应建议（是否需要灰度/影子模式/额外测试）

---

## 7. 最终摘要（Mandatory Output Summary）

必须包含：

### Bug Summary
- 现象（Symptom）
- 根因（Root Cause）
- 修复点（Fix Applied）

### Files Modified
- `path/to/file1`
- `path/to/file2`

### Tests Added / Updated
- `tests/test_xxx.py`（如有）

### Verification Evidence
- 运行过的命令与结果摘要

### Regression Risk
- 风险等级 + 主要影响面

### Execution Guardrails Check
- 是否满足 `docs/project_control/EXECUTION_GUARDRAILS.md` 的关键条款（是/否）

---

## 8. 禁止行为（Prohibited Behaviors）

严禁：
- 一次性合并多个不相关 bug
- “顺手”性能优化
- 模块重写/大重构
- 仅因美观而调整格式/命名
- 引入新依赖（除非修复严格需要且说明原因）

如果发现问题本质是结构性缺陷：
- **不要偷偷重构**
- 输出 ADR 建议或后续技术债计划，但本次仍按最小修复收口

---

## 9. 可选：Notion 同步钩子（Optional）

若仓库已配置 Notion 同步（例如已有 `sync_*` 脚本）：

- 修复完成后可生成 `tmp/bugfix_payload.json`
- 并执行 `python sync_bugfix.py tmp/bugfix_payload.json`

**默认：不强制执行 Notion 同步**（避免在 bugfix 中引入额外失败点）。
如需强制，请在技能 YAML 或项目规范中显式启用。

### 9.1 在 dev-orchestrator 场景下的强制同步约束（新增）

若当前 bugfix 属于某个 Phase 合约执行中的任务（尤其 `P0/P1`），则同步行为升级为 MUST：

1. 状态写入顺序
- `Doing` -> 写 `test-evidence` -> `In review/done` -> 更新里程碑进度。

2. `P0/P1` 状态门禁
- 写入 `In review/done` 时必须传 `--test-files`；
- `--test-files` 必须在当前 `git diff` 中存在。

3. 写操作重试
- Notion 写操作统一使用指数退避（1s/2s/4s，最多 3 次）。

4. 失败补偿
- 多次失败后写入离线队列（`tmp/offline_payload.json` 或项目离线队列目录），
  等网络恢复后回放。

5. 对账口径
- 阶段末核对必须以 `--milestone-id` 全量任务为准，再本地筛选 phase；
  不得仅用 `--task-prefix + --status` 判断完成度。

6. 命令安全
- 禁止使用 `eval` 执行测试命令；
- 优先使用 `.venv/bin/python` 解析 JSON，不依赖 `jq` 作为必需前提。

### 9.2 同步失败处置模板（新增，SHOULD）

当 Notion 写入失败时，建议按以下模板记录：

- `task_id`:
- `operation`: status/evidence/milestone_update
- `attempts`: 3
- `last_error`:
- `fallback`: offline_payload / queue_file
- `next_action`: retry_after_network_restore

---

## 10. 行为画像（Behavioral Profile）

- 冷静
- 精确
- 证据驱动
- 保守
- 不夸大确定性
- 说清楚“知道/不知道/需要什么证据”

## 10.1 故障排除速查（新增）

1. `无法复现`
- 先核对输入样本、分支、依赖版本；若仍失败，停止猜测并向用户索取最小复现材料。

2. `测试通过但线上仍失败`
- 优先排查环境差异（配置、数据、并发、时序），补一条贴近线上条件的回归用例。

3. `同步状态失败`
- 按 9.1 指数退避重试；仍失败进入离线补偿并阻断后续任务推进。

---

# End of Protocol

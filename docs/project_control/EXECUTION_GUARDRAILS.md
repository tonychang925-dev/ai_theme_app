# Unified Execution Guardrails

适用范围：
- `.agents/skills/dev-orchestrator/SKILL.md`
- `.agents/skills/qa-gate/SKILL.md`
- `.agents/skills/bugfix/SKILL.md`
- `.agents/skills/refactor/SKILL.md`

目标：
- 统一阶段执行、测试门禁、Notion 同步、失败补偿与对账口径。

## 1. 测试先行（MUST）

1. `P0/P1` 任务必须先新增/更新自动化测试脚本，再进入实现。
2. 测试脚本必须可追溯到 `TC-ID`（测试名/注释/参数化 ID 任一）。
3. 禁止“只改业务代码不改测试”直接进入 `In review/done`。

## 1.1 设计文档优先与禁止编造规则（MUST）

1. 不允许编造不符合设计文档的逻辑和规则。
2. 所有业务规则、字段语义、状态判断、候选准入、入池路径、fallback/mock 行为，必须能追溯到阶段设计文档、旧链等价函数或已登记 ADR。
3. 若代码需求与设计文档不一致，必须先更新设计文档或登记 ADR 并完成评审，再进入实现；禁止先在代码中新增“临时规则”“试探规则”“兜底规则”。
4. 缺少真源证据时，只允许 fail-fast 或不输出该命题判断；不得把缺失解释成默认 `true/false`、默认状态、默认入池类型或默认候选结论。
5. mock/stub/fake/fallback 不得作为核心业务判断依据，不得替代正式验收证据。
6. 任一新增或修改的业务判断无法映射到设计文档章节、旧链函数或 ADR 编号时，质量门禁必须失败。

## 2. 状态同步顺序（MUST）

统一顺序：
1. `Todo -> Doing`
2. 写入 `test-evidence`
3. `In review` 或 `done`
4. 更新里程碑进度

补充：
- `P0/P1` 在写 `In review/done` 时必须显式传 `--test-files`；
- `--test-files` 中的文件必须出现在当前 `git diff` 中。

## 3. 任务状态机（MUST）

标准流转：
- `Todo -> Doing`
- `Doing -> Blocked -> Doing`（可选）
- `Doing -> In review -> done`
- `Doing -> done`（无需人工评审时）
- `In review -> Doing`（评审不通过返工）

约束：
- 使用 `Blocked` 前必须确认 Notion 状态选项已配置该值。

## 4. 命令执行安全（MUST）

1. 禁止 `eval` 执行测试命令。
2. 优先使用 `.venv/bin/python` 解析 JSON，不将 `jq` 作为必需前置。
3. 所有同步脚本统一使用 `.venv/bin/python sync_pm_status.py`。

## 5. 重试与离线补偿（MUST）

1. Notion 写操作统一指数退避：
- 第 1 次失败后等待 `1s`
- 第 2 次失败后等待 `2s`
- 第 3 次失败后等待 `4s`
- 最多 3 次

2. 超过重试阈值后，进入离线补偿：
- 写入 `tmp/offline_payload.json` 或离线队列目录
- 网络恢复后通过 `--batch-sync` 回放

推荐队列结构：
- `tmp/offline/queue/`
- `tmp/offline/processing/`
- `tmp/offline/failed/`
- `tmp/offline/done/`

## 6. 对账口径（MUST）

阶段末对账必须使用：
1. `--milestone-id` 拉取里程碑全量任务
2. 本地按 phase/task-prefix 筛选
3. 生成对账报告（如 `tmp/reconcile_report.json`）

禁止仅依赖：
- `--task-prefix + --status` 直接判定“全部完成”

## 7. 结构化证据（SHOULD）

建议输出：
- `tmp/execution.log`
- `tmp/errors.log`
- `tmp/progress_report.json`

建议日志字段：
- `timestamp|level|phase|task_id|action|status|duration|message`

## 8. 常见故障速查

1. `Could not find page with ID`
- 原因：用了数据源 ID 而非页面 ID
- 处理：先 `--fetch-tasks` 获取真实页面 ID

2. `--status` / `--status-value` 混用
- 查询用 `--status`
- 更新用 `--status-value`

3. `task-prefix` 查不到 `done`
- 原因：过滤组合或脚本逻辑漏数
- 处理：回退到 `--milestone-id` 全量拉取后本地筛选

4. `Blocked` 状态写入失败
- 原因：Notion 未配置该状态
- 处理：补配置或临时用 `Doing + evidence` 标记阻塞

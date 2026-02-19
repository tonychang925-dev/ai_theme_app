# Phase Execution Contract

## 0. Contract Meta

- Contract File: `docs/project_control/PHASE_CONTRACT_P1.phase1.md`
- Machine Copy: `tmp/phase_contract_P1.phase1.json`
- Scope: `phase:P1.phase1`
- Unified Guardrails: `docs/project_control/EXECUTION_GUARDRAILS.md`

---

## 1. Phase Identity

- Phase Name: 路由统一与幂等执行
- Phase Code: P1.phase1
- Parent Milestone: P1（第一阶段）
- Risk Level: High
- Source Documents (priority order):
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/adrs/ADR_LIST.md`

---

## 2. Phase Objective（可量化）

1. 同一输入事件在重试/回放场景结果一致：重复写入率 = 0。  
2. 决策与事件载荷解析必须严格：禁止 `str(value)` 降级进入执行路径。  
3. unknown `action/operation` 必须 fail-fast 并进入 dead-letter。  
4. `normal` 未匹配事件必须进入 `stream:events:pending`，且原消息 ACK。  
5. 失败消息必须进入受控处理（重试上限 + dead-letter），禁止无限悬挂。

---

## 3. Acceptance Targets（门禁条件，二元判定）

- [ ] 决策执行前强制校验 `idempotency_key`，命中后 `duplicate-skip`。
  - 验证映射: `ACC-P1-P1-01`
- [ ] 决策/事件载荷解析禁止 `str(value)` 降级进入执行路径。
  - 验证映射: `ACC-P1-P1-02`
- [ ] 未知 `action/operation` 必须 fail-fast 并进入 dead-letter。
  - 验证映射: `ACC-P1-P1-02`
- [ ] `normal` 未匹配事件必须落到 `stream:events:pending` 且原消息 ACK。
  - 验证映射: `ACC-P1-P1-03`
- [ ] `ACC-P1-P1-03` 必须验证“分类优先匹配失败过程”本身（非仅结果）：
  - `decision_type` 属于未匹配分支（`category_no_match/no_match_in_category/no_match_after_fallback`）；
  - `reason` 含未匹配语义，且分类推断统计递增（`category_inferences` 增加）；
  - 决策动作为 `publish_clustering`，并保持 `trace_id/decision_id` 在 decision 与 pending 链路一致。
  - 验证映射: `ACC-P1-P1-03`
- [ ] 失败消息必须进入受控处理（重试上限 + dead-letter），不得无限悬挂。
  - 验证映射: `ACC-P1-P1-02` + dead-letter/retry 指标审计

---

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q database_service/tests/streams`
- `.venv/bin/python -m pytest -q tests`
- `rg -n "idempotency_key|duplicate_skip|dead-letter|fail-fast|stream:events:pending|str\(value\)" database_service theme_service docs`

状态同步与对账基线（MUST）：

- 任务状态同步顺序：`Doing -> test-evidence -> In review/done -> milestone progress`
- `P0/P1` 写入 `In review/done` 时必须显式传 `--test-files` 且这些文件必须出现在当前 `git diff`。
- 阶段末完成度判断必须使用 `--milestone-id` 全量拉取后本地筛 phase，禁止仅依赖 `--task-prefix + --status`。

---

## 5. Deliverables（可验证路径）

- 路由统一实现与重复入口移除证据。
  - 路径: `database_service/streams/`（代码 diff + 测试结果）
- 幂等键与 duplicate-skip 门禁实现及回放结果。
  - 路径: `database_service/streams/`、`database_service/tests/streams/`
- unknown action fail-fast + dead-letter 处理链。
  - 路径: `database_service/streams/handlers/`
- 严格 schema 解析替代弱降级策略（禁 `str(value)`）。
  - 路径: `database_service/streams/handlers/`、`database_service/tests/streams/`
- 阶段验收与追踪文档更新。
  - 路径: `docs/project_control/reports/phase-P1.phase1.md`、`docs/adrs/`
- 执行器输入产物。
  - 路径: `tmp/plan/wbs.md`、`docs/project_control/TEST_CASE_SPEC_P1.phase1.md`、`tmp/plan/test_traceability_P1.phase1.json`、`tmp/feature_traceability_P1.phase1.json`、`tmp/feature_validation_report_P1.phase1.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 幂等键规则不完整导致误去重/漏去重 | High | Medium | 回放出现重复写入 | Dev + QA | 固定 `event_id+action+payload_hash`，补充冲突样本回放 |
| unknown action 未阻断导致脏执行 | High | Medium | 非法 action 进入主链路 | Dev | fail-fast + dead-letter + 指标告警 |
| schema 校验放宽导致弱解析吞错 | High | Medium | `str(value)` 等降级路径触发 | Dev + Reviewer | 严格 schema 校验，拒绝并审计 |
| pending/失败消息处理不受控导致积压 | Medium | Medium | dead-letter_rate 持续上升 | DevOps + QA | 设置重试上限、超限死信、告警阈值 |

---

## 7. Rollback Plan

触发条件（任一命中）：

- 回放同批次出现重复写入。
- unknown `action/operation` 未被阻断。
- 解析失败消息进入执行器主路径。
- 死信率无告警且持续上升。

回滚分层：

- 代码回滚：回退到上一稳定提交，恢复已验证的路由与幂等策略版本。
- 数据回滚：按幂等日志与审计记录清理重复写入，保留原始消息ID映射。
- 同步补偿回滚：Notion 状态回写失败时写入 `pending_sync`，网络恢复后批量补偿重放。

---

## 8. Non-Goals

- 不进行动态阈值与候选治理优化（P1.phase2 范围）。
- 不引入/放量 LLM 最终裁决链路（P1.phase3 范围）。
- 不覆盖发布门禁收口（P1.phase4 范围）。

---

## 9. Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| Phase1 验收目标条数 | `ACCEPTANCE.md`（5条） | 旧 `PHASE_CONTRACT_P1.phase1.md`（4条） | ACCEPTANCE 为验收真源，旧合同缺少 pending/失败受控两条 |
| Phase1 需求细化（PRD vs PRD_P1） | `prd_p1.md`（`PRD-P1-P1-R01~R10`） | `PRD.md` M2总述级条款 | phase 合同需保留可执行细粒度需求，不改变 phase 边界 |
| M2 跨阶段需求（动态阈值/LLM）是否纳入 phase1 | `PLAN_WBS.md` + `ACCEPTANCE.md` phase 边界 | `PRD.md` M2全量语义直接下沉 phase1 | phase 合同必须严格 phase 范围，不跨 phase 引入后续条款 |

---

## 10. Self-Check（MUST）

- [x] Phase Identity 完整
- [x] Acceptance 条款二元可判定
- [x] Required Commands 可复制执行且安全
- [x] Deliverables 全部映射到路径
- [x] Risk/Rollback/Non-Goals 无缺失
- [x] 生成 `.md + .json` 双格式
- [x] 冲突裁决记录已填写
- [x] 引用统一约束清单 `docs/project_control/EXECUTION_GUARDRAILS.md`
- [x] 多 PRD 文件已纳入并完成裁决（`PRD.md` + `prd_p1.md`）
- [x] 一致性报告通过（`is_consistent=true`）

# 第一阶段执行合约（PHASE_CONTRACT_P1）

- 合约ID：`CONTRACT-P1-2026-02-13`
- 项目：个人投资助理（AI Theme App）
- 阶段范围：`P1.phase0 ~ P1.phase4`
- 生效日期：`2026-02-13`
- 合约状态：`Active`

---

## 1. 合约目标与适用范围

本合约用于约束第一阶段执行过程、交付标准、质量门禁和发布阻断条件。第一阶段必须完成“新闻->事件->题材映射”可验收闭环，并满足架构第12章验证体系。

强制目标：
- 建立单链路、强契约、强幂等、可回放的稳定执行基线。
- 完成动态阈值与候选治理，候选爆炸比受控。
- 完成 `LLM 最终裁决（Qwen2.5 + llama.cpp）` 并通过验收。
- 完成发布门禁接入，未达标禁止发布。

---

## 2. 合约依据（优先级）

当文档冲突时，按以下优先级执行：
1. `docs/project_control/PHASE_CONTRACT_P1.md`（本合约）
2. `docs/project_control/ACCEPTANCE.md`
3. `docs/project_control/prd_p1.md`
4. `docs/project_control/TEST_CASE_SPEC.md`
5. `docs/project_control/ARCH_REVIEW.md`
6. `docs/adrs/ADR_LIST.md`
7. `docs/project_control/PLAN_WBS.md`

---

## 3. 强制能力（Must-Have）

以下能力为第一阶段“必须完成项”，任一未达成即阶段不通过：

- `C-01`：`DecisionEnvelope v1` 强制契约（必填字段完整、dual-read 兼容可用）。
- `C-02`：决策执行幂等门禁（`event_id+action+payload_hash`），重复写入率=0。
- `C-03`：动态阈值与候选治理（候选窗口 3~30，候选爆炸比 < 5%）。
- `C-04`：新题材创建阶段禁止二次分类推断（复用首阶段分类结果，移除 `_match_categories` 二次推断）。
- `C-05`：`LLM 最终裁决（Qwen2.5 + llama.cpp）` 必经链路生效：
  - 固定顺序：`语义粗筛 -> LLM最终裁决`。
  - 10% 灰度下 `llm_final_judged_ratio >= 95%`。
  - 模型调用证据完整（`model_name/request_id/timestamp`）。
- `C-06`：回放一致率=100%，pending 清理与 durable success 强绑定。
- `C-07`：发布门禁可阻断（超阈值不允许放行）。

---

## 4. 角色与责任（RACI）

- 架构负责人（A）：确认架构路径、ADR 决策、技术阻断结论。
- 开发负责人（R）：完成功能实现、修复缺陷、提交技术证据。
- 测试负责人（R）：执行测试计划、出具验收证据、失败归因。
- 产品/项目负责人（C）：确认范围边界、里程碑完成判定。
- 发布负责人（A）：执行 Release Gate，保留发布/回滚审计证据。

---

## 5. 里程碑执行合约

### P1.phase0 — 运行时收敛与契约冻结
准入条件：
- 评审范围与链路边界确认完成。

准出条件：
- 重复入口/重复高风险函数定义清零。
- `DecisionEnvelope v1` 冻结并可兼容读取。
- `trace_id` 跨链路可追踪。

关键证据：
- 契约扫描报告、链路扫描报告、日志字段抽样证据。

### P1.phase1 — 路由统一与幂等执行
准入条件：
- P1.phase0 准出完成。

准出条件：
- unknown action fail-fast + dead-letter。
- 严格 schema 解析，禁止弱降级执行。
- 重放重复写入率=0。

关键证据：
- 幂等回归报告、dead-letter 样本、异常路径测试记录。

### P1.phase2 — 动态阈值与分类复用优化
准入条件：
- P1.phase1 准出完成。

准出条件：
- 候选窗口稳定 3~30。
- 候选爆炸比 < 5%。
- 分类复用策略生效，创建阶段无二次分类推断。
- 30 案例三方评估报告齐全。

关键证据：
- A/B 报告、分类一致性报告、`test_theme_processor.py` 执行摘要。

### P1.phase3 — LLM 最终裁决落地（Qwen2.5 + llama.cpp）
准入条件：
- P1.phase2 准出完成。

准出条件：
- 最终落库链路已强制经过 LLM 裁判。
- 10% 灰度下 `llm_final_judged_ratio >= 95%`。
- `arbiter_p95_latency < 800ms`，成本在预算内。
- 模型栈固定为 `Qwen2.5 + llama.cpp` 且证据完整。

关键证据：
- 灰度分桶证据、调用审计证据、误判归因报告。

### P1.phase4 — 回放安全与发布门禁收口
准入条件：
- P1.phase3 准出完成。

准出条件：
- 回放一致率=100%。
- 发布门禁阻断有效（超阈值自动阻断）。
- `P1-ISS-01..10` 闭环完成。

关键证据：
- replay 报告、Release Gate 报告、问题关闭清单。

---

## 6. 统一门禁指标（Gate KPIs）

以下指标为阶段级硬门禁：

- `replay_consistency_rate = 100%`
- `duplicate_write_rate = 0`
- `candidate_explosion_ratio < 5%`
- `candidate_window in [3, 30]`
- `llm_final_judged_ratio >= 95%`（10%灰度）
- `arbiter_p95_latency < 800ms`
- `real_call_ratio = 100%`（正式验收）
- `issues_closed_ratio = 100%`（`P1-ISS-01..10`）

任一指标不满足即：`Gate=FAIL`，禁止发布。

---

## 7. 测试执行合约

必须执行并留存结果：

- 合同测试来源：`docs/project_control/TEST_CASE_SPEC.md`
- 关键策略：
  - 所有 `P0` 用例 100% 通过。
  - 每个需求项至少 1 个测试映射。
  - 关键路径包含 `IT/ST`；异常路径包含 `ET`。
- 架构第12章约束：
  - 固定入口：`test_theme_processor.py`
  - 固定环境：macOS + Python 3.13（transformer场景在 `theme_matcher_env`）
  - 真实模型证据：不得以 mock 替代正式验收结论。

---

## 7.1 执行编排联动规范（dev-orchestrator × feature）

为避免 `WBS 执行子集` 与 `feature 设计` 重复，第一阶段统一执行口径如下（适用于 `P1.phase0 ~ P1.phase4`）：

- `STEP 1 (WBS)`：仅定义 What（任务集合、依赖、顺序、优先级），禁止实现细节。
- `STEP 1.5 (test-case)`：输出 `TEST_CASE_SPEC_<phase>.md` 与 `test_traceability_<phase>.json`。
- `STEP 1.8 (feature)`：输出 `FEATURE_SPEC.md`、`feature_traceability_<phase>.json`、`feature_validation_report_<phase>.json`，负责 How（接口/数据/错误处理/回滚/测试命令）。
- `STEP 2 (implementation)`：必须同时消费 `test_traceability` 与 `feature_traceability`，任一映射缺失即阻断执行。

强制门禁（MUST）：

- `test_traceability_<phase>.json.gate_ready == true`
- `feature_validation_report_<phase>.json.gate_ready == true`
- 不允许 “WBS 有任务但 feature 无映射”
- 不允许 “feature 有任务但不在 WBS 子集”
- `P0/P1` 任务进入 `In review/done` 前，必须显式传入 `--test-files` 且文件存在于当前 diff

标准结构校验命令（MUST）：

```bash
.venv/bin/python scripts/validate_feature_artifacts.py \
  --traceability tmp/feature_traceability_<phase>.json \
  --report tmp/feature_validation_report_<phase>.json \
  --phase <phase>
```

---

## 8. 失败判定与阻断规则

任一命中则第一阶段判定“不通过”：

- 任一 `P0` 测试失败。
- 未完成 `LLM 最终裁决（Qwen2.5 + llama.cpp）` 强制链路。
- `llm_final_judged_ratio < 95%`（10%灰度）。
- 模型栈不符或调用证据缺失。
- `candidate_explosion_ratio >= 5%`。
- `replay_consistency_rate < 100%`。
- `duplicate_write_rate > 0`。
- `real_call_ratio < 100%`（正式验收）。
- 发布门禁超阈仍放行。

---

## 9. 变更控制（Contract Change Control）

- 所有变更必须提交变更单，至少包含：变更原因、影响范围、回滚方案、验证计划。
- 影响 `C-01`~`C-07` 或门禁指标的变更，必须先更新 ADR 再执行。
- 合约版本更新规则：
  - 文案澄清：补丁版本（`v1.0.x`）
  - 指标或能力变更：次版本（`v1.x.0`）
  - 范围重定义：主版本（`vX.0.0`）

---

## 10. 交付物清单（DoD Artifacts）

第一阶段收口必须交付：

- `docs/project_control/prd_p1.md`
- `docs/project_control/ACCEPTANCE.md`
- `docs/project_control/TEST_CASE_SPEC.md`
- `docs/project_control/ARCH_REVIEW.md`
- `docs/adrs/ADR_LIST.md`
- `docs/project_control/PLAN_WBS.md`
- `docs/project_control/FEATURE_SPEC.md`
- `docs/project_control/PHASE_CONTRACT_P1.phase0.md`（后续 phase 合同同名规则）
- `tmp/plan/test_traceability_<phase>.json`
- `tmp/feature_traceability_<phase>.json`
- `tmp/feature_validation_report_<phase>.json`
- 验收证据包（测试报告、门禁报告、调用证据、回滚演练记录）

---

## 11. 签署与生效

- 技术签署：架构负责人、开发负责人、测试负责人。
- 业务签署：产品/项目负责人。
- 发布签署：发布负责人。

签署完成后，本合约作为第一阶段唯一执行契约生效。

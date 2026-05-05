# FEATURE SPEC - P4.phase0

## 0. Meta
- Phase: `P4.phase0`
- 目标: 清理已完成项后，仅保留当前阻塞 P4 推进的未完成任务。
- 真源约束:
  - `docs/architecture/个人投资助理项目-前端技术设计（第四阶段）.md` 全文为执行真源（SSOT）。
  - 其中第9/10章为实施约束与文档治理强制条款；若与其他章节或其他文档冲突，以第9/10章裁决。
  - `frontend` 仅承接稳态与回退；新增投研能力落在 `web_app_service`。

## 1. 已完成任务（从执行清单移除）
- 已完成：三栏页面壳与基础联动（`/intel` 左中右基本联动）。
- 已完成：`/api/v2/intel/stream` 路由可用（405 问题已闭环）。
- 已完成：SSE 管理基础能力（重连/心跳/错误处理）已在现有代码具备。
- 已完成：`frontend` 与 `FEATURE_SPEC_P4.phaseA` 的第一轮差距核查。

> 说明：以上条目不再作为 phase0 执行任务，避免重复验证浪费时间。

## 2. Phase0 剩余任务（仅未完成项）

### Task P4.phase0-R01 — 路径收口门禁（只留 `/api/v2/*`）
#### 1) 目标
- 前端页面调用仅允许 `/api/v2/*`，禁止新增旧 `/api/intel/*` 依赖。
#### 2) 子功能
- `F-P4.phase0-R01-01` 非 v2 调用扫描与清零。
- `F-P4.phase0-R01-02` CI 阻断规则接入（PR 即阻断）。
#### 3) 验收
- `rg -n --pcre2 "['\"]/api/(?!v2/)" frontend/src` 结果为 0。
- `ACPT-P4P0-R01`

### Task P4.phase0-R02 — 三栏最小 DTO 契约冻结
#### 1) 目标
- 冻结 `ThemeRadar/IntelContext/MarketValidation` 最小字段与可空性，禁止页面重算 A/B/C/D。
#### 2) 子功能
- `F-P4.phase0-R02-01` 字段最小集合与可空性定稿。
- `F-P4.phase0-R02-02` 字段来源映射（对象快照/聚合 DTO）定稿。
- `F-P4.phase0-R02-03` 错误码与 fallback 语义定稿。
#### 3) 验收
- 契约评审通过，字段语义无歧义。
- `ACPT-P4P0-R02`

### Task P4.phase0-R02A — 前端交互设计分解（与 PLAN_WBS T04 同步）
#### 1) 目标
- 将“交互设计”拆成可执行子任务，避免标题级任务无法落地。
#### 2) 子功能
- `F-P4.phase0-R02A-01` 线框图：三栏主态 + 空态 + loading + error + fallback 态。
- `F-P4.phase0-R02A-02` 交互时序：左驱中、中驱右、日期切换、stream->feed 回退状态机。
- `F-P4.phase0-R02A-03` 布局规范：栅格、断点、最小宽度、滚动区、吸顶规则。
- `F-P4.phase0-R02A-04` Web 展示验收：`/intel` 三栏联动冒烟与状态一致性检查。
#### 3) 验收
- 设计评审通过 + 联动验收清单通过。
- `ACPT-P4P0-R02A`

### Task P4.phase0-R03 — contract tests 首版落地
#### 1) 目标
- 覆盖 `feed/stream/workspace/*/strong_watch/post_market_snapshot` 的契约与边界。
#### 2) 子功能
- `F-P4.phase0-R03-01` 参数边界测试（date/session/type/limit）。
- `F-P4.phase0-R03-02` 错误码语义测试（400/404/405/500）。
- `F-P4.phase0-R03-03` fallback 语义测试（stream->feed）。
#### 3) 验收
- contract tests 全通过并纳入 CI。
- `ACPT-P4P0-R03`

### Task P4.phase0-R04 — CI 综合门禁
#### 1) 目标
- 三类门禁在 PR 生效：路径、契约、禁重算。
#### 2) 子功能
- `F-P4.phase0-R04-01` 非 `/api/v2/*` 调用阻断。
- `F-P4.phase0-R04-02` contract tests 必跑阻断。
- `F-P4.phase0-R04-03` 页面临时重算 A/B/C/D 检查阻断。
#### 3) 验收
- PR 门禁演练通过。
- `ACPT-P4P0-R04`

## 3. DoD（Phase0 剩余）
- [ ] 前端非 `/api/v2/*` 调用扫描为 0
- [ ] 三栏最小 DTO 契约冻结
- [ ] contract tests 全通过并接入 CI
- [ ] 页面禁重算 A/B/C/D 门禁生效

## 4. 增量任务分解（2026-05-01 对齐第11章）

### Task P4.phase0-R05 — 新链读取链路收口（最小改造）
#### 1) 目标
- `web_app_service` 关键读口统一收口到 `stock_processing_service`，不再以旧代理链路作为主路径。
#### 2) 子功能
- `F-P4.phase0-R05-01` 收口 `intel/feed` 调用路径。
- `F-P4.phase0-R05-02` 收口 `strong_watch/watch` 调用路径。
- `F-P4.phase0-R05-03` 收口 `workspace/market-validation` 错误语义（200+diagnostics）。
#### 3) 验收
- `/intel` 页面不再出现 `request failed: 503`。
- `ACPT-P4P0-R05`

### Task P4.phase0-R06 — 运行态防漂移治理
#### 1) 目标
- 消除双配置和旧端口残留导致的链路回漂。
#### 2) 子功能
- `F-P4.phase0-R06-01` `vite.config.js/.ts` 代理口径一致化。
- `F-P4.phase0-R06-02` 启动脚本增加端口冲突清理与健康门禁。
- `F-P4.phase0-R06-03` 状态脚本增加三跳链路探活。
#### 3) 验收
- `5173 -> 8000 -> workspace` 探活稳定通过。
- `ACPT-P4P0-R06`

## 5. 执行进度回写（2026-05-01）

### 已完成
- `P4.phase0-R01` 路径收口门禁：`frontend/src` 非 `/api/v2/*` 扫描为 0，门禁已在 `p0-guardrail.yml` 生效。
- `P4.phase0-R02` 三栏 DTO 契约冻结：已更新 `docs/contracts/web_app_service_intel_v2_contract.md`（字段可空性/类型/语义冻结）。
- `P4.phase0-R03` contract tests 首版落地：`web_app_service/tests/test_p4_phase0_contracts.py` 当前 12 例通过。
- `P4.phase0-R04` CI 综合门禁：路径阻断 + contract tests 必跑已接入。
- `P4.phase0-R05` 新链读取链路收口（第一阶段）：
  - `strong_watch/watch` 已切到 `StockProcessingReadClient`。
  - `intel/feed`、`workspace/theme-radar`、`workspace/intel-context` 已改为新读口优先，旧代理兜底。
- `P4.phase0-R06` 运行态防漂移治理：
  - `vite.config.js/.ts` 统一代理到 `8000`。
  - `start/status` 脚本已调整为新链语义与健康门禁。

### 未完成
- `P4.phase0-R02A` 前端交互设计分解（线框图动态交互验收）待补齐。

## 6. DoD（Phase0 当前）
- [x] 前端非 `/api/v2/*` 调用扫描为 0
- [x] 三栏最小 DTO 契约冻结
- [x] contract tests 全通过并接入 CI
- [x] 页面禁重算 A/B/C/D 门禁生效

## 7. R02A 交付物（2026-05-01 增量）
- 新增：`docs/project_control/P4_PHASE0_INTERACTION_ACCEPTANCE.md`
- 用途：作为 `P4.phase0-R02A` 的线框态/动态交互/布局规范/验收清单唯一执行附件。

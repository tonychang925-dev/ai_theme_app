# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 新链 A/B/C/D 旧链等价迁移与偏差删除
- Phase Code: SYSTEM.LAYER_ABCD.ALIGNMENT
- Parent Milestone: P4.phase0-runtime-contract
- Risk Level: P0
- Scope: system
- Source Documents:
  - `docs/architecture/个人投资助理项目-前端技术设计（第四阶段）.md`
  - `架构差距分析报告.md`
  - `docs/project_control/EXECUTION_GUARDRAILS.md`
  - `stock_service/scripts/build_mainline_identity_registry.py`
  - `stock_service/services/strong_stock_tracking_service.py`
  - `stock_service/services/weak_to_strong_candidate_builder.py`
  - `stock_processing_service/domain/services/strong_watch_universe.py`
  - `stock_processing_service/domain/services/strong_watch_service.py`
  - `stock_processing_service/domain/services/strong_watch_admission_policy.py`
  - `stock_processing_service/domain/services/strong_watch_refresh_service.py`
  - `stock_processing_service/domain/services/w2s_candidate_service.py`
  - `stock_processing_service/application/jobs/build_post_market_recap_job.py`

### Conflict Resolution

1. 冲突项：`架构差距分析报告.md` 中对 A/B “已基本对齐”的阶段性判断，与当前回放样本 `4/7 神剑股份`、`4/15 联德股份`、`4/23 维科技术` 的实际结果不一致。
   - 采用来源：旧链代码行为 + 设计文档冻结条款
   - 放弃来源：已过时的阶段性对账结论
   - 裁决理由：执行合同必须以可重放的行为真值为准，不以描述性结论为准

2. 冲突项：新链当前运行态与历史 replay 会改写同一份真源，导致历史样本漂移。
   - 采用来源：设计文档中的“单真源/冻结条款”
   - 放弃来源：允许 replay 覆盖运行真源的临时做法
   - 裁决理由：合同必须保证历史样本稳定，否则 A/B/C/D 不可验

---

## 2. Phase Objective

在不新增任何旧链没有的业务门槛前提下，使新链 `Layer A/B/C/D` 与旧链 `stock_service` 在固定回归样本上逐层一致，并且所有快照、候选池和详情页结果均可重放、可解释、可对账。

量化目标：

- `4/7 神剑股份`、`4/15 联德股份`、`4/23 维科技术` 在新链中的 A/B/C/D 结果必须与旧链一致。
- 新链不得出现“结果列表有、详情 404”或“输入池有、最终候选为空且无旧链理由”的行为漂移。
- 新链不得再引入旧链没有的新硬门槛、软回退、临时拼接或文件真源。

---

## 3. A/B/C/D 不符合项清单（必须删除或回退）

### 3.1 Layer A 不符合项

#### 3.1.0 Layer A 执行合同硬约束

1. Layer A 身份判定唯一算法来源是旧链 `stock_service/scripts/build_mainline_identity_registry.py`。
   - 必须复刻：`_fetch_latest_mainline_scores()` 的输入字段口径。
   - 必须复刻：`_decide_identity()` 的 `logic_score / market_score / composite_score / logic_ok / market_ok / one_day_tour_flag` 公式。
   - 必须复刻：`_analyze_theme_kline_shape_open_source()` 的 K 线形态判断。
   - 禁止：新增旧链没有的事件阈值、热度阈值、资金阈值、K 线阈值、宽度阈值或一日游判断。

2. `MainlineJudgementService` 不是 Layer A 身份判定模块。
   - 该服务不得作为 `identity_status / is_main_theme / rule_is_main_theme` 的来源。
   - 该服务不得替代 `IdentityRuleEngine / OneDayTourDetector / IdentityLLMReviewService / IdentityDecider / BuildIdentityJob`。
   - 该服务如被使用，只能作为 Layer B/C/D 的主线存活、周期或展示解释辅助，不得反写 A 口身份真值。

3. 新链架构边界必须保持解耦。
   - `stock_processing_service` 不得直接写 SQL、不得直接连接数据库、不得读本地 `json/jsonl` 作为 A 口真源。
   - `stock_processing_service` 只能通过 `StockReadPort` 读取 A 口规则输入字段集。
   - `database_service` 负责通过 gateway 提供旧链等价字段集；SQL 只允许存在于 `database_service` 数据层。
   - `IdentityRuleEngine` 必须是纯规则引擎，不允许访问数据库、Redis、文件、网络或环境变量。

4. A 口验收必须先于 B/C/D。
   - 未通过 A 口验收前，禁止继续修改 B/C/D 业务规则。
   - A 口必验样本：`2026-04-07 / 神剑股份 / 002361.SZ`、`2026-04-15 / 联德股份 / 605060.SH`。
   - A 口不得因新链新增规则导致上述样本与旧链身份真值不一致。

1. 历史身份真值不冻结。
   - 现象：历史日期会被当前 `theme_mainline_identity_registry` / dual-run 结果重新解释。
   - 与旧链/文档冲突：旧链身份判定必须是该交易日的稳定真值，不允许后续 replay 改写。
   - 处理要求：历史 replay 必须使用冻结结果；禁止用当前 registry 反判历史。

2. A 层判定与历史样本不一致。
   - 现象：`2026-04-07 / 9062832` 在新链为 `identity_status=inactive`，旧链为 `mainline_identity_confirmed=true`。
   - 与旧链/文档冲突：旧链样本是硬回归真值。
   - 处理要求：A 层必须先对齐旧链样本，再允许下游执行。

3. A 层引入了会漂移的复合评分结果作为历史主判。
   - 现象：`logic_score / market_score / composite_score / llm_verdict` 参与当前身份读口并影响历史样本重放。
   - 与旧链/文档冲突：A 层必须可重放、可冻结、可审计。
   - 处理要求：A 层历史判定不得依赖会随 replay 变化的当前派生状态。

### 3.2 Layer B 不符合项

1. 周期证据口径与旧链对账不稳定。
   - 现象：存在静默丢弃题材、confirmed 主线题材在执行链路中被跳过的风险。
   - 与旧链/文档冲突：Layer B 必须完整输出周期证据，不能吞错后跳过。
   - 处理要求：禁止 `except ... continue` 造成的静默丢弃；必须显式记录失败原因。

2. 退潮证据与状态机需按文档目标口径固定。
   - 现象：历史阶段口径曾出现 4 项/6 项混用。
   - 与旧链/文档冲突：当前执行合同以 6 项目标口径为准。
   - 处理要求：不得回退到旧阶段快照口径，不得混用。

### 3.3 Layer C 不符合项

1. 新增旧链没有的中间等级或扩池分支。
   - 必须删除的历史实现：`B_KEEP`、`formal_sa_gate_mode`、`admission_soft_reject_observe_only`、`reject_junk_follower`、`hard_reject_any`、`formal_w2s_override`、`gap_formal_override`、`weekly_midterm_gate` 等所有新增硬门槛/软门槛。
   - 与旧链/文档冲突：旧链只允许等价迁移，不允许自创分层和额外 gate。

2. 不能把 `reject` 回流成 `observe_only`，也不能把 `observe_only` 再无条件升 `formal`。
   - 与旧链/文档冲突：旁路只应是旧链明示旁路，不得用作新扩池。
   - 处理要求：任何旁路必须来自旧链明确规则，不得新增旁路语义。

3. `two_board_entry` 的语义被写窄或写歪。
   - 旧链语义：二连板/近 7 日强势连板是强旁路，且会影响观察窗续命。
   - 新链禁令：不得把它仅作为“分数提权”而不重置生命周期状态。

4. `support_strength` 口径与旧链不一致。
   - 旧链：候选层以原始支撑强度与分类结果决定是否入候选。
   - 新链禁令：不得用更窄的 `support_hit_score` 替代原始支撑强度作为主判。

5. 候选准入过窄。
   - 旧链允许 `formal + observe_only` 进入候选集合。
   - 新链禁令：不得把候选集合收窄为 formal-only。

6. 输入条件过严。
   - 旧链允许满足强势背景、支撑可用、弱势定义和历史条件的样本进入。
   - 新链禁令：不得把 `watch_score < 62`、`strong_grade` 为空、`watch_status=removed` 等条件变成额外硬拒绝，除非旧链同样如此。

### 3.4 Layer D 不符合项

1. `top_candidates` 语义被收窄。
   - 旧链/文档要求：候选输出必须来自全部有效候选，不得只取 formal。
   - 新链禁令：不得把 `top_candidates` 写成 formal-only 结果。

2. 结果详情与结果列表来源不一致。
   - 现象：列表能看到，详情 404；或者详情依赖另一张表/另一套 id。
   - 处理要求：详情必须与结果列表同源，不得混用候选池和 recap 的不同主键语义。

3. 生产路径仍允许 mock、临时拼接、文件真源或 fallback。
   - 禁止：`json/jsonl` 作为盘前确认真源、临时拼接结果对象、mock 模拟生产返回、临时回退到别表别源。

---

## 4. 必须恢复的旧链行为

1. A 层必须恢复为旧链样本真值优先。
2. B 层必须显式记录所有证据与失败原因，不允许静默丢弃。
3. C 层必须保留旧链的正式/观察候选口径，禁止 formal-only 收窄。
4. D 层必须按同源候选列表生成 top_candidates、详情和快照，不得因展示层二次裁剪改变业务结果。

---

## 5. Acceptance Targets

- [ ] `2026-04-07 / 002361.SZ / 神剑股份` 在新链 A 层判定为旧链一致的主线真值。
- [ ] `2026-04-07 / 002361.SZ / 神剑股份` 在新链 B/C/D 的逐层结果与旧链一致，不得在中间层被额外门槛踢掉。
- [ ] `2026-04-15 / 605060.SH / 联德股份` 在新链回放中命中弱转强候选，与旧链一致。
- [ ] `2026-04-23 / 600152.SH / 维科技术` 在新链回放中命中弱转强候选，与旧链一致。
- [ ] 新链 `top_candidates` 不得再出现 formal-only 收窄。
- [ ] 新链结果详情不得再出现“列表有、详情 404”的跨源不一致。
- [ ] 新链生产路径不得再读本地 `json/jsonl` 作为真源。

---

## 6. Required Commands

- `PYTHONPATH=. ./.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_identity_rule_engine.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/replay/test_replay_shenjian_2026_04_07.py stock_processing_service/tests/replay/test_replay_liande_2026_04_15.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_w2s_candidate_service.py stock_processing_service/tests/unit/test_strong_watch_admission_policy.py stock_processing_service/tests/unit/test_strong_watch_pipeline.py`
- `.venv/bin/python stock_service/scripts/run_w2s_regression_checks.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/integration/test_build_post_market_recap_job.py`
- `npm --prefix frontend run build`

---

## 7. Deliverables

- `docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md`
- `tmp/phase_contract_LAYER_ABCD.json`
- 新增/更新的回归测试文件
- 逐层对账报告

---

## 8. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
|---|---|---:|---|---|---|
| A 层历史真值继续漂移 | 全链结果失真 | 高 | replay/dual-run 覆盖历史 | 新链执行者 | 冻结历史真值，禁止覆盖 |
| C 层继续新增 gate | 样本持续被误杀 | 高 | 新门槛/旁路再出现 | 新链执行者 | 删除新增 gate，回到旧链 |
| D 层 formal-only 收窄 | 候选集再次缩小 | 高 | top_candidates 再次裁剪 | 新链执行者 | 保持候选全集语义 |
| 详情与列表不同源 | 前端 404 / 对账失败 | 中 | id 语义分裂 | 后端/前端 | 同源主键，统一真源 |
| 共享真源被污染 | 历史样本不可复现 | 高 | replay 写回运行库 | 运行负责人 | 冻结回放写入，做隔离 |

---

## 9. Rollback Plan

### 9.1 代码回滚

- 触发条件：任一回归样本偏离旧链结果，且无法在同一轮修复中恢复。
- 动作：回滚最近一次涉及 A/B/C/D 判定语义的提交。

### 9.2 数据回滚

- 触发条件：replay 或回放重建已污染当前真源。
- 动作：恢复到回放前快照，禁止继续在同一库中反复重放。

### 9.3 同步补偿回滚

- 触发条件：结果详情、候选列表、快照三者出现不一致。
- 动作：先冻结前端展示，再回退后端列表/详情生成逻辑，最后重跑回归样本。

---

## 10. Non-Goals

- 不在本合同中讨论“新架构可否比旧链更聪明”。
- 不在本合同中新增任何业务解释层或优化性门槛。
- 不在本合同中接受“先上线后补齐旧链一致性”。
- 不在本合同中允许生产路径使用 mock / fallback / 文件真源。

# Architecture Review

## 1. 当前架构摘要

### 1.1 评审范围
- 评审模式：`scope=phase:第一阶段 (P1)`
- 评审对象：
  - `database_service/streams/schedulers/news_collector_scheduler.py`
  - `database_service/streams/schedulers/news_stream_scheduler.py`
  - `database_service/streams/handlers/news_stream_handler.py`
  - `database_service/streams/handlers/news_stream_processor.py`
  - `database_service/streams/handlers/theme_processor.py`
  - `database_service/streams/handlers/DecisionExecutor.py`
  - `theme_service/services/theme_service.py`
  - `theme_service/services/theme_discovery_engine.py`
  - `theme_service/matchers/semantic_matcher.py`
  - `theme_service/creators/theme_data_generator.py`
- 目标：在第一阶段闭环内完成“契约收敛、执行确定性、匹配稳定性、回放可验证”

### 1.2 现状主链路
- 新闻抓取与发布：`news_collector_scheduler/news_stream_scheduler` 产生 `news` 消息。
- 存储与业务处理：`news_stream_handler/news_stream_processor` 消费并转业务事件。
- 题材发现与决策：`theme_processor/theme_service/theme_discovery_engine/semantic_matcher` 产生决策。
- 决策执行：`DecisionExecutor` 落库并回写更新流。

### 1.3 关键一致性结论
- 架构文档第12章提出的“动态阈值、A/B灰度、真实模型验证、量化评估”尚未在运行时形成硬门禁。
- 架构文档已明确“引入 LLM 裁判（Qwen2.5 + llama.cpp）作为最终裁决”为第一阶段必须完成项，但当前架构评审与ADR未将其作为 P0 强约束。
- 第一阶段存在“多真相实现 + 弱契约解析 + 非确定性生成 + 高噪声日志”叠加风险。

---

## 2. 风险矩阵（按优先级）

| 风险ID | 风险描述 | 代码证据 | 严重度 | 发生概率 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| R1 | 重复函数定义导致运行时行为漂移（后定义覆盖前定义） | `database_service/streams/handlers/theme_processor.py:1086`, `database_service/streams/handlers/theme_processor.py:1124`; `theme_service/services/theme_service.py:139`, `theme_service/services/theme_service.py:966`, `theme_service/services/theme_service.py:1057`, `theme_service/services/theme_service.py:1274`, `theme_service/services/theme_service.py:727`, `theme_service/services/theme_service.py:1655`; `database_service/streams/handlers/news_stream_handler.py:137`, `database_service/streams/handlers/news_stream_handler.py:938`, `database_service/streams/handlers/news_stream_handler.py:774`, `database_service/streams/handlers/news_stream_handler.py:911` | High | High | P0 |
| R2 | 决策/消息解析存在弱类型降级，结构化语义丢失 | `database_service/streams/handlers/DecisionExecutor.py:832`, `database_service/streams/handlers/DecisionExecutor.py:836`; `database_service/streams/handlers/theme_processor.py:1360`; `database_service/streams/handlers/news_stream_handler.py:472` | High | High | P0 |
| R3 | 幂等执行缺失，重试/回放可重复写入 | `database_service/streams/handlers/DecisionExecutor.py`（无 `idempotency_key` 校验路径） | High | High | P0 |
| R4 | unknown operation 被跳过而非 fail-fast，执行语义不闭合 | `database_service/streams/handlers/DecisionExecutor.py:403`, `database_service/streams/handlers/DecisionExecutor.py:726` | High | Medium | P0 |
| R5 | payload 递归解析无深度上限，消息格式分支复杂且不可预测 | `database_service/streams/handlers/news_stream_handler.py:539` | High | Medium | P0 |
| R6 | semantic matcher 在模型异常时回退随机/零向量，可能将噪声推进主决策 | `theme_service/matchers/semantic_matcher.py:523`, `theme_service/matchers/semantic_matcher.py:527`, `theme_service/matchers/semantic_matcher.py:575` | High | High | P0 |
| R7 | 固定阈值为主（0.92/0.88），与第12章“事件级动态阈值”不一致 | `theme_service/services/theme_discovery_engine.py:32`, `theme_service/services/theme_discovery_engine.py:45`; `theme_service/matchers/semantic_matcher.py:350` | High | High | P0 |
| R8 | 题材代码包含时间戳，回放不可重现 | `theme_service/creators/theme_data_generator.py:920`, `theme_service/creators/theme_data_generator.py:938`, `theme_service/creators/theme_data_generator.py:941` | High | High | P0 |
| R9 | 生产路径存在大量 `print/traceback`，日志不可治理，成本高且难做指标化 | `database_service/streams/schedulers/news_stream_scheduler.py:501`; `database_service/streams/handlers/news_stream_handler.py:205`; `theme_service/services/theme_discovery_engine.py:26`; `theme_service/matchers/semantic_matcher.py:73`; `theme_service/creators/theme_data_generator.py:204` | Medium | High | P1 |
| R10 | mock/real 降级策略可运行但缺强门禁，可能长期污染评估 | `database_service/streams/schedulers/news_stream_scheduler.py:179`, `database_service/streams/schedulers/news_stream_scheduler.py:197`, `database_service/streams/schedulers/news_stream_scheduler.py:595`; `database_service/streams/handlers/news_stream_processor.py:98` | Medium | High | P1 |
| R11 | 决策ID和事件ID生成策略非确定性，跨进程/回放不可稳定复现 | `database_service/streams/handlers/theme_processor.py:835`, `database_service/streams/handlers/theme_processor.py:1368` | Medium | Medium | P1 |
| R12 | trace/payload版本字段未成为强契约，跨流追踪不闭合 | `database_service/streams/schedulers/news_stream_scheduler.py:393`; `database_service/streams/handlers/theme_processor.py:834`; `database_service/streams/handlers/DecisionExecutor.py:816` | Medium | Medium | P1 |
| R13 | 新题材创建阶段重复进行分类推断，违反“首阶段分类结果复用”原则，增加漂移与算力浪费 | `theme_service/creators/theme_rule_generator.py:292`, `theme_service/creators/theme_rule_generator.py:319`, `theme_service/creators/theme_rule_generator.py:418` | High | High | P0 |
| R14 | 未将 LLM 裁判（Qwen2.5 + llama.cpp）落地为“最终裁决必经链路”，仍以向量语义结果直接决策，持续造成错配 | `theme_service/matchers/semantic_matcher.py:350`, `theme_service/services/theme_discovery_engine.py:32`, `database_service/streams/handlers/theme_processor.py:1077` | High | High | P0 |

---

## 3. 分维度发现

### 3.1 边界与职责清晰度
- 发现
  - `theme_processor/theme_service/news_stream_handler` 同名函数重复定义，后定义覆盖前定义。
  - `news_collector_scheduler` 仅生成 mock 新闻，不具备生产态边界隔离。
- 影响
  - 同一输入在不同运行时上下文行为不一致，验收不可重复。
- 优化方向
  - 冻结单实现真源（Single Source of Truth），重复定义清零。
  - 将 demo/mock 调度器显式标记为测试组件并隔离生产导入。

### 3.2 数据契约与解析安全
- 发现
  - `DecisionExecutor._parse_decision_data` 对非字符串/非bytes字段直接 `str(value)`，导致结构化字段退化。
  - `news_stream_handler` 多层 payload 递归解析，缺最大深度和白名单字段校验。
  - `theme_processor._extract_event_data` 在 JSON 失败时生成 `raw_content`，缺 schema reject。
- 影响
  - 决策证据链失真，难以定位误匹配根因；安全边界弱。
- 优化方向
  - 强制 `DecisionEnvelope v1`：缺字段/类型错误直接 reject+dead-letter。
  - 解析器增加 `max_depth` 与字段白名单，不允许无界递归。

### 3.3 执行一致性与幂等
- 发现
  - `DecisionExecutor` 无显式 `idempotency_key` 检查与去重存储。
  - unknown operation 仅 warning 跳过。
  - `news_stream_handler` duplicated `_process_storage_batch` + duplicated `_update_storage_stats` 触发重复计数风险。
- 影响
  - 重试回放可产生重复写入；统计指标失真。
- 优化方向
  - 执行前硬幂等门禁（`event_id+action+payload_hash`）。
  - unknown operation fail-fast 并入 dead-letter。
  - 存储统计逻辑保留单实现并建立单测防回归。

### 3.4 匹配稳定性与模型降级
- 发现
  - `semantic_matcher` 模型异常时会返回随机向量或零向量路径。
  - `theme_discovery_engine` 主路径仍以固定阈值为主并叠加多层回退。
  - 分类推断和匹配流程存在大量调试打印，难以门禁化。
- 影响
  - 高噪声输入下候选爆炸/漏召回并存，且结果解释性弱。
- 优化方向
  - 禁止随机/零向量进入最终决策；仅允许受控降级（pending/dead-letter）。
  - 引入事件级动态阈值（Strong/Candidate/Weak）并先灰度后扩量。

### 3.5 可观测性与发布门禁
- 发现
  - 关键链路缺强制 `trace_id/payload_version/idempotency_key`。
  - mock 占比虽统计但未绑定发布阻断。
- 影响
  - 问题可见但不可控，无法形成上线前硬约束。
- 优化方向
  - 将 `source_type=real/mock`、候选爆炸比、回放一致率、死信率接入 Release Gate。

### 3.6 可回放性与确定性
- 发现
  - `theme_data_generator` 代码生成依赖时间戳。
  - `theme_processor` 事件ID和decision_id包含时间与进程hash。
- 影响
  - 同输入多次回放结果不一致，阻断第一阶段最终验收。
- 优化方向
  - 统一可重放ID策略：输入哈希派生 + 稳定命名，不依赖系统时间。

### 3.7 分类推断单一真源
- 发现
  - 架构文档第12章已明确：创建新题材时应沿用“事件匹配题材阶段”的分类结果，不再重复推断。
  - 但 `ThemeRuleBasedGeneratorFixed.generate_theme_data_only()` 仍在内部调用 `_match_categories()` 重新做一次分类推断。
- 影响
  - 同一事件可能在两次推断中产生不同分类结果，造成“匹配阶段分类”和“创建阶段分类”不一致。
  - 增加计算成本与链路复杂度，弱化可解释性与回放一致性。
- 优化方向
  - 以 `ThemeProcessor/ThemeService` 首阶段分类结果作为唯一输入（例如 `classification_result/category_info`）。
  - `theme_rule_generator` 禁止再次调用 `_match_categories()`，仅做“数据拼装与编码”。

### 3.8 LLM 最终裁决专项风险（Qwen2.5 + llama.cpp）
- 发现
  - 当前主链路中，向量语义匹配结果可直接进入决策执行，LLM 裁判尚未成为必经最终裁决。
  - 现有规划更偏向“shadow 灰度”，与“第一阶段必须通过的最终裁决能力”存在目标错位。
- 影响
  - 高相似但语义方向不同的事件仍会被错误归并，导致题材匹配不准成为持续主问题。
  - 第一阶段验收无法证明“误匹配问题已被核心机制解决”。
- 优化方向
  - 固化两阶段决策顺序：`向量粗筛 -> LLM 裁判最终裁决（Qwen2.5 + llama.cpp）`。
  - 将 LLM 最终裁决纳入第一阶段硬门禁：未经过裁判的候选不得进入最终落库路径（超时场景走受控降级并计入失败预算）。
  - 以 76 案例三方评估结果作为放量前置条件：质量指标不达标即阻断发布。

---

## 4. 目标架构（第一阶段收敛版）

### 4.1 运行时目标
- 单链路：`news_stream_* -> theme_processor -> DecisionExecutor -> updates/pending`。
- 单契约：`DecisionEnvelope v1` 强制字段：
  - `decision_id,event_id,action,payload_version,trace_id,idempotency_key,payload`。
- 单真源：去除重复定义，统一方法语义。

### 4.2 匹配与裁判目标
- 第一阶段：事件级动态阈值 + 候选窗口治理（3~30） + LLM 最终裁决（Qwen2.5 + llama.cpp）落地。
- 决策顺序固定：`语义粗筛` 仅负责召回候选，最终是否匹配必须由 LLM 裁判给出可审计结论。
- 复核覆盖固定：分类命中样本必须全量进入 LLM 复核（不允许仅歧义样本复核）。
- 人工终审兜底：`category_uncertain/abstain` 与门禁异常样本进入 `pending_manual_review`，由分析师审批后回写 `events:decision`。
- 执行策略采用动态2/8原则（比喻）：`manual_review_rate` 动态调节，不写死固定比例。

### 4.3 执行与回放目标
- 幂等执行：决策执行前必检 `idempotency_key`。
- 回放一致：同输入同输出，禁止时间戳业务主键。
- pending 清理：仅在 durable success 后执行。

### 4.4 发布门禁目标
- 阻断条件（任一命中即阻断）：
  - 回放一致率 < 100%
  - 重复写入率 > 0
  - 候选爆炸比 >= 5%
  - `llm_final_judged_ratio < 95%`（第一阶段默认门槛，灰度期）
  - `llm_timeout_fallback_ratio` 超过预算阈值
  - `real_call_ratio < 100%`（架构第12章正式验收）

---

## 5. 迁移计划

### 5.1 总体策略
- 先收敛再优化：先修契约和执行确定性，再做阈值，最后落地 LLM 最终裁决并门禁化。
- 双读单写过渡：允许历史消息读取兼容，写入统一 `v1`。

### 5.2 P1.phase0（契约冻结与运行时收敛）
- 变更
  - 清理重复定义：
    - `theme_processor._get_action_for_decision_type`
    - `theme_service.initialize_with_categories_only/discover_category_only/get_service_status`
    - `news_stream_handler._process_storage_batch/_update_storage_stats`
  - 统一消息解析策略，移除无界递归分支。
  - 移除生产路径 `print/traceback.print_exc`。
- 风险下降：R1/R2/R5/R9
- 回滚：保留旧解析器分支为只读兼容（非默认）。

### 5.3 P1.phase1（路由统一与幂等执行）
- 变更
  - `DecisionExecutor` 增加 `idempotency_key` 执行门禁与重复跳过。
  - unknown action/operation fail-fast + dead-letter。
  - 解析失败消息不可进入执行路径。
  - 新题材创建时分类信息必须复用首阶段结果，移除生成器内二次分类推断路径。
- 风险下降：R3/R4
- 回滚：幂等校验以开关灰度启用。

### 5.4 P1.phase2（动态阈值与候选治理）
- 变更
  - `semantic_matcher` 引入事件级动态阈值与三段策略。
  - 禁止随机/零向量参与最终决策。
  - `source_type(real/mock)` 指标纳入门禁。
- 风险下降：R6/R7/R10
- 回滚：切回 baseline profile。

### 5.5 P1.phase3（LLM最终裁决落地：Qwen2.5 + llama.cpp）
- 变更
  - 固化 `Qwen2.5 + llama.cpp` 为最终裁决链路；语义匹配结果不可直接作为最终决策。
  - 分类命中样本全量复核；灰度仅控制“采纳比例”，不控制“复核调用覆盖率”。
  - 对不确定样本落 `pending_manual_review`，分析师终审后回写决策再执行。
  - 第一阶段默认 10% 灰度切流，满足门槛后逐步扩大；全过程必须保留 real-call 证据。
  - 超时/预算/熔断保护，失败走受控降级并纳入门禁预算（不可静默通过）。
- 风险下降：R7/R10/R14
- 回滚：从“强制最终裁决落库”回退到“全量复核但仅shadow不采纳”，并触发发布阻断评审。

### 5.6 P1.phase4（回放安全与发布门禁）
- 变更
  - 题材代码与决策ID改为可重放确定性生成。
  - 发布门禁接入 `replay/dead_letter/backlog/issues_closed_ratio/real_call_ratio`。
- 风险下降：R8/R11/R12
- 回滚：门禁只告警不阻断（短期），修复后恢复阻断模式。

---

## 6. 子阶段计划（P1.phase0 ~ P1.phase4）

### P1.phase0：运行时收敛与契约冻结
- 验收门槛
  - 重复定义=0
  - 解析器无无界递归
  - 生产路径 `print/traceback`=0

### P1.phase1：路由统一与幂等执行
- 验收门槛
  - `idempotency_key` 命中时重复写入=0
  - unknown action/operation 全部 dead-letter

### P1.phase2：动态阈值与候选治理
- 验收门槛
  - 候选窗口 3~30
  - 候选爆炸比 < 5%
  - 随机/零向量结果不进入最终决策

### P1.phase3：LLM 最终裁决（Qwen2.5 + llama.cpp）
- 验收门槛
  - `语义粗筛 -> LLM最终裁决` 顺序固定，未裁判样本不得进入最终落库
  - 分类命中样本 `judge_full_review_ratio = 100%`
  - 10% 灰度下 `llm_final_judged_ratio >= 95%`
  - `manual_review_rate` 按质量门禁动态调节（非固定比例）
  - 超时回退可验证且在失败预算内
  - 76 案例三方评估达标（题材数8~12，质量指标不低于基线）

### P1.phase4：回放安全与发布门禁
- 验收门槛
  - 回放一致率 100%
  - 重点问题关闭率 100%
  - `real_call_ratio=100%`

---

## 7. ADR 提案

### ADR-001：第一阶段运行时单链路冻结
- 现状不足：重复定义与并行分支导致行为不确定。
- 决策：冻结单链路实现，重复定义清零。
- 代价：一次性清理与回归验证成本中等。
- 兼容性：对外接口不变，内部路径收敛。

### ADR-002：DecisionEnvelope v1 强制契约
- 现状不足：payload 弱解析导致语义丢失。
- 决策：`v1` 强制字段 + 严格校验 + reject 策略。
- 代价：producer/consumer 双侧改造。
- 兼容性：采用 dual-read 过渡。

### ADR-003：DecisionExecutor 幂等门禁
- 现状不足：重试回放重复写入风险高。
- 决策：执行前幂等校验，命中 duplicate-skip。
- 代价：增加索引与状态存储。
- 兼容性：可灰度启用。

### ADR-004：unknown operation fail-fast
- 现状不足：未知操作被跳过，状态不透明。
- 决策：unknown action/operation 必须 dead-letter。
- 代价：短期死信量上升。
- 兼容性：需要补齐告警与重放流程。

### ADR-005：动态阈值替代固定阈值主路径
- 现状不足：固定阈值无法适配行情波动。
- 决策：事件级阈值 + 三段候选治理。
- 代价：策略观测与AB评估成本上升。
- 兼容性：保留 baseline profile 回退。

### ADR-006：禁止随机/零向量参与最终决策
- 现状不足：模型异常回退会污染结果。
- 决策：异常路径只允许受控降级，不得产出最终主题。
- 代价：未匹配率短期可能上升。
- 兼容性：可通过 pending 补偿。

### ADR-007：题材代码与决策ID确定性生成
- 现状不足：时间戳与运行时 hash 导致不可回放。
- 决策：稳定输入哈希派生ID，不依赖系统时间。
- 代价：历史ID迁移与映射维护。
- 兼容性：需提供旧新ID映射层。

### ADR-008：mock 数据门禁化
- 现状不足：mock 可长期混入生产评价。
- 决策：`mock_source_ratio` 进入发布阻断门禁。
- 代价：测试环境准备更严格。
- 兼容性：可在开发环境降级为告警。

### ADR-009：pending 清理与 durable success 强绑定
- 现状不足：先清后写会破坏回放一致性。
- 决策：清理必须绑定持久化成功证据。
- 代价：短期积压上升。
- 兼容性：需调整清理任务时序。

### ADR-010：结构化可观测性最小集合
- 现状不足：大量 print，缺统一指标维度。
- 决策：统一日志字段与必需指标（trace_id、idempotency_key、source_type、gate_result）。
- 代价：日志改造和监控接入。
- 兼容性：逐模块替换，不影响业务协议。

### ADR-011：新题材创建阶段禁止二次分类推断
- 现状不足：`generate_theme_data_only()` 内部重新调用 `_match_categories()`，与架构第12章“沿用首阶段分类结果”冲突。
- 决策：分类推断单一真源前置到事件匹配阶段；创建阶段只消费已确定的 `classification_result/category_info`。
- 代价：需要调整 `theme_rule_generator` 入参与调用链，补齐兼容层。
- 兼容性：对外协议保持不变，内部字段从“可选推断”升级为“必传分类上下文”。

### ADR-012：第一阶段强制引入 LLM 最终裁决（Qwen2.5 + llama.cpp）
- 现状不足：向量语义匹配可直接驱动最终题材决策，错配问题无法根治。
- 决策：第一阶段必须将 LLM 裁判（Qwen2.5 + llama.cpp）作为最终裁决必经链路，向量层仅作候选召回。
- 代价：引入模型调用时延、成本与运维复杂度；需建设熔断/超时/预算保护。
- 兼容性：保留受控降级路径，但降级结果不得绕过门禁直接作为“通过验收”的最终结果。

### ADR-013：分类命中后全量 LLM 复核（禁止仅歧义触发）
- 现状不足：仅歧义触发会漏掉“高相似但语义错配”样本。
- 决策：分类命中样本 `judge_full_review_ratio=100%`；灰度仅控制采纳比例，不控制复核覆盖率。
- 代价：模型调用量与时延成本上升，需并发池/缓存/熔断保护。
- 兼容性：允许受控回退 stage1，但必须附 `timeout_fallback/model_unavailable` 原因码。

### ADR-014：人工终审兜底机制（pending_manual_review）
- 现状不足：LLM 不确定样本无统一人工终审入口，可能误自动落库。
- 决策：引入 `pending_manual_review` 队列；分析师审批后回写 `events:decision` 再执行。
- 代价：引入人工链路与处理时延。
- 兼容性：动态 2/8（比喻）策略，不写死固定人工比例。

### 7.1 ADR-013/014 最小实现清单（开发执行版）

1. 接口与服务
- 新增/扩展 `FinalJudgeOrchestrator`：对分类命中样本全量复核并输出统一裁决对象。
- 新增/扩展 `LLMThemeArbiterClient`：返回 `decision/confidence/request_id/model_name/timestamp`。
- 新增/扩展 `ArbiterGovernanceGuard`：输出 `manual_review_rate` 与门禁结论。
- 新增 `ManualReviewBridge`（可在 processor 层实现）：接收人工审批回写并转为标准 decision。

2. 消息与字段契约
- Decision 侧新增字段：`judge_source,judge_applied,fallback_reason,arbiter_mode,review_status,llm_suggestion,review_reason,reviewer_id`。
- 必填审计字段：`trace_id,decision_id,request_id,model_name,timestamp,source_type`。
- 人工终审状态：`review_status in {pending_manual,approved,rejected}`。

3. 流转与动作映射
- 机器不确定样本（`abstain/category_uncertain`）统一写入 `pending_manual_review`。
- 人工审批后回写 `events:decision`：
  - `approve_update -> update_theme`
  - `approve_create -> create_new_theme`
  - `approve_cluster -> publish_clustering`
  - `reject_drop -> drop_event`

4. 门禁与指标
- 覆盖率门禁：`judge_full_review_ratio = 100%`（分类命中样本）。
- 质量门禁：`llm_final_judged_ratio >= 95%`（10%灰度）。
- 运行门禁：`arbiter_p95_latency < 800ms`，超预算触发降级与告警。
- 人工策略指标：`manual_review_rate,false_positive_rate,false_no_match_rate`（动态调节，不固定阈值）。

5. 最小测试映射
- `TC-P1-P3-IT-001`：链路顺序 + 全量复核覆盖。
- `TC-P1-P3-ET-001`：超时回退不阻塞。
- `TC-P1-P3-ET-002`：不可用降级 + 熔断。
- `TC-P1-P3-ST-001`：`judge_full_review_ratio=100%` + `llm_final_judged_ratio>=95%`。
- `TC-P1-P3-PT-001`：时延预算。
- `TC-P1-P3-RT-001`：报告维度与审计可追溯性。

### 7.2 P1.phase3 实现任务拆分表（T01~T04）

| WBS Task | 子任务ID | 实施内容 | 主要产出（路径） | 依赖 | 测试映射 | 完成判定（DoD） |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase3-T01 | T01-S01 | 建立“分类命中 -> 全量LLM复核”编排规则（替代仅歧义触发） | `theme_service/services/theme_service.py`、`database_service/streams/handlers/theme_processor.py` | phase2 分类真源复用 | TC-P1-P3-IT-001 | 分类命中样本 `judge_full_review_ratio=100%` 且链路顺序断言通过 |
| P1.phase3-T01 | T01-S02 | 定义复核契约与原因码（`fallback_reason/judge_source`） | `database_service/streams/handlers/DecisionExecutor.py`、契约校验逻辑 | T01-S01 | TC-P1-P3-IT-001, TC-P1-P3-ET-001 | 决策消息包含新增字段并通过 v1 校验 |
| P1.phase3-T02 | T02-S01 | 接入 `LLMThemeArbiterClient`（Qwen2.5+llama.cpp）与调用审计 | `theme_service/services/` | T01-S02 | TC-P1-P3-ST-001 | 审计字段 `request_id/model_name/timestamp/source_type` 完整 |
| P1.phase3-T02 | T02-S02 | 实现超时回退与不可用熔断（fail-close） | `theme_service/services/`、`database_service/streams/handlers/theme_processor.py` | T02-S01 | TC-P1-P3-ET-001, TC-P1-P3-ET-002 | 超时与不可用均触发受控降级，原因码可追溯 |
| P1.phase3-T03 | T03-S01 | 实现动态2/8调节与人工终审分流（`pending_manual_review`） | `database_service/streams/handlers/theme_processor.py`、前端回写契约文档 | T02-S02 | TC-P1-P3-ST-001, TC-P1-P3-RT-001 | 可输出 `manual_review_rate` 且不确定样本进入人工队列 |
| P1.phase3-T03 | T03-S02 | 构建 `FinalJudgeEvidenceCollector` 报告聚合 | `database_service/scripts/`、`docs/project_control/reports/phase-P1.phase3.md` | T03-S01 | TC-P1-P3-RT-001 | 报告包含精度/时延/成本/误判归因及可追溯索引 |
| P1.phase3-T04 | T04-S01 | 门禁配置化（ratio/latency/cost/real_call/manual_review） | `theme_service/services/`、配置文件 | T03-S02 | TC-P1-P3-PT-001, TC-P1-P3-ST-001 | 门禁阈值可配置，失败触发降级与告警 |
| P1.phase3-T04 | T04-S02 | 发布前验证脚本与绝对路径测试命令固化 | `docs/project_control/PHASE_CONTRACT_P1.phase3.md`、`database_service/tests/streams/test_phase3_behavior_tests.py` | T04-S01 | 全部 phase3 TC | 绝对路径命令可直接执行，测试证据与任务状态可对账 |

实施顺序建议（串并行）：
- 串行主线：`T01-S01 -> T01-S02 -> T02-S01 -> T02-S02 -> T03-S01 -> T03-S02 -> T04-S01 -> T04-S02`
- 可并行：`T03-S02` 可在 `T03-S01` 接口冻结后并行推进；`T04-S01` 可与报告聚合联调并行。

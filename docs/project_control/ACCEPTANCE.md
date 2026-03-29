# 第一阶段验收规范（ACCEPTANCE）

- 项目：个人投资助理（AI Theme App）
- 范围：第一阶段（P1.phase0 ~ P1.phase4）
- 依据文档：
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`
- 风险等级：High
- 合约模式：严格二进制通过（不允许部分通过）
- 第一阶段强制能力：`LLM 最终裁决（Qwen2.5 + llama.cpp）` 必须完成并通过验收，未达标即整阶段不通过。

---

## Phase P1.phase0 — 运行时收敛与契约冻结

### 1. 目标（1-3 行）
建立第一阶段唯一运行时处理链和统一消息契约，消除同名函数覆盖、链路歧义和字段漂移。确保 `trace_id` 可跨 stream 追踪，契约必填字段覆盖率达到 100%。

### 2. 验收目标（清单）
- [ ] 仅保留一个有效决策路由实现路径（无重复入口可触发）。
- [ ] `DecisionEnvelope v1` 强制启用并定义必填字段：`decision_id,event_id,action,payload_version,trace_id,idempotency_key,payload`。
- [ ] `news` 消息格式收敛到单一可解析契约（禁止无边界递归 payload 解析分支）。
- [ ] 运行时模块（handler/scheduler/service）生产路径中 `print` 与 `traceback.print_exc` 清零。
- [ ] `trace_id` 从 `news_stream_*` 到 `theme_processor` 到 `DecisionExecutor` 全链路可查。

### 3. 验收测试用例（Given / When / Then）

#### 案例 ID: ACC-P1-P0-01
Given:
- 代码库包含第一阶段全部运行时模块
- 已定义契约扫描规则
When:
- 执行静态扫描（重复函数名、重复路由入口）
Then:
- `theme_processor` 中决策路由函数仅有单实现
- `theme_service` 中同名关键入口方法无重复定义
- `news_stream_handler` 中批处理/统计方法无重复定义

#### 案例 ID: ACC-P1-P0-02
Given:
- 消费端接收 `v0/v1` 历史样本消息
When:
- 统一解析消息并进入内部对象
Then:
- 解析结果统一为 v1 结构
- 缺失必填字段的消息被拒绝，不进入业务执行
- 拒绝消息写入 dead-letter 且带错误码

#### 案例 ID: ACC-P1-P0-03
Given:
- 一条完整新闻从 `stream:news:raw` 进入处理链
When:
- 完整执行到 `stream:events:decision`
Then:
- 日志与消息中存在同一 `trace_id`
- `trace_id` 可检索到链路各节点处理记录

### 4. 边界/非目标
- 不做动态阈值策略优化。
- 不引入 LLM 裁判执行逻辑。
- 不做前端与产品化层改造。

### 5. 数据示例（如适用）
输入 JSON：
```json
{
  "payload_version": "v1",
  "decision_id": "dec_0001",
  "event_id": "evt_0001",
  "action": "update_theme",
  "trace_id": "trace_evt_0001",
  "idempotency_key": "evt_0001:update_theme:sha256_abcd",
  "payload": {"theme_id": "th_001"}
}
```
预期结果：
- 消费端解析成功为统一内部对象
- 缺任一必填字段则拒绝执行并入死信

### 6. 失败标准（必须明确）
- 任意关键函数重复定义仍存在。
- 存在多条可执行决策路由入口。
- 契约必填字段覆盖率 < 100%。
- 生产路径存在 `print`/`traceback.print_exc`。
- `trace_id` 无法跨 stream 追踪。

### 7. 可观察性要求
- 必需日志字段：`trace_id,event_id,decision_id,payload_version,consumer,stream,message_id`。
- 必需指标：`contract_validation_fail_count`、`duplicate_route_detected_count`。
- 必需审计条目：契约拒绝原因码 + 原始消息ID。

---

## Phase P1.phase1 — 路由统一与幂等执行

### 1. 目标（1-3 行）
保证同一输入事件在重试/回放场景结果一致，重复写入率为 0。建立严格解析、幂等执行与受控失败策略，杜绝静默跳过和弱解析吞错。

### 2. 验收目标（清单）
- [ ] 决策执行前强制校验 `idempotency_key`，命中后 `duplicate-skip`。
- [ ] 决策/事件载荷解析禁止 `str(value)` 降级进入执行路径。
- [ ] 未知 `action/operation` 必须 fail-fast 并进入 dead-letter。
- [ ] `normal` 未匹配事件必须落到 `stream:events:pending` 且原消息 ACK。
- [ ] 失败消息必须进入受控处理（重试上限 + dead-letter），不得无限悬挂。

### 3. 验收测试用例（Given / When / Then）

#### 案例 ID: ACC-P1-P1-01
Given:
- 两条 `event_id/action/payload_hash` 相同的决策消息
When:
- 依次执行决策
Then:
- 第一条执行成功
- 第二条命中幂等并跳过写入
- 统计中 `duplicate_skip_count` 增加 1

#### 案例 ID: ACC-P1-P1-02
Given:
- 一条缺少 `payload` 或 `action` 的决策消息
When:
- 进入 DecisionExecutor 解析流程
Then:
- 消息被拒绝执行
- 写入 dead-letter 并附解析失败原因
- 不得发生任何数据库写操作

#### 案例 ID: ACC-P1-P1-03
Given:
- `normal` 事件匹配失败
When:
- 执行决策发布
Then:
- 生成 `publish_clustering` 决策并写入 pending 流
- 原消息 ACK
- 事件具备 `trace_id` 和 `decision_id`

### 4. 边界/非目标
- 不进行阈值策略 A/B 调优。
- 不引入 LLM 裁判产线开关。

### 5. 数据示例（如适用）
输入 JSON：
```json
{
  "decision_id": "dec_1001",
  "event_id": "evt_1001",
  "action": "create_new_theme",
  "idempotency_key": "evt_1001:create_new_theme:sha256_777",
  "payload": {"theme_data": {"name": "新概念", "code": "THM_X"}}
}
```
预期结果：
- 首次执行创建成功
- 重复执行返回 `duplicate_skip`

### 6. 失败标准（必须明确）
- 回放同批次出现重复写入。
- 未知 `action/operation` 未被阻断。
- 解析失败消息进入执行器主路径。
- 死信率无告警且持续上升。

### 7. 可观察性要求
- 必需日志字段：`idempotency_key,decision_id,event_id,action,duplicate_hit,dead_letter_reason`。
- 必需指标：`duplicate_skip_rate`、`dead_letter_rate`、`parse_reject_count`、`unknown_action_count`。
- 审计条目：每条拒绝/跳过均保留原始消息ID与拒绝原因。

---

## Phase P1.phase2 — 动态阈值与候选治理

### 1. 目标（1-3 行）
将固定阈值迁移到事件级动态阈值，稳定候选规模并控制错配。达到候选窗口 3~30、候选爆炸比 < 5%，并确保精度代理指标不低于基线。

### 2. 验收目标（清单）
- [ ] 动态阈值按事件分布（p95/p98）计算并可切换 `baseline/balanced/strict`。
- [ ] 动态阈值必须实现 `Strong/Candidate/Weak` 三段分层并记录分层命中分布。
- [ ] 候选治理先于精排，候选窗口稳定在 3~30。
- [ ] 生产路径禁止随机向量/零向量结果作为最终决策依据。
- [ ] 创建阶段有上游分类结果时必须复用；无上游分类结果时走 `create_concept_category_path`（主/子概念创建），禁止二次 `_match_categories` 推断。
- [ ] 输出 `source_type(real/mock)` 质量指标并设置门禁阈值。
- [ ] 30 案例集 A/B 报告必须包含：候选爆炸比、完整性、分离度、精度代理。
- [ ] 30 案例集必须形成三方对比：优化系统 vs 基线系统（纯聚类） vs 久赢恒丰标准。
- [ ] 30 案例集验收指标必须满足：题材数量收敛到 8~12，且 Precision/Completeness/Separation 三指标均不低于基线系统。
- [ ] A/B 灰度必须先在 10% 流量执行，通过后才允许扩大范围。
- [ ] 本阶段验收必须使用真实 DeepSeek 调用（`source_type=real`），禁止模拟数据替代正式结论。
- [ ] 分类关键词索引补全完成：L2 分类关键词来自 L3 题材关键词去重聚合，L1 分类关键词来自 L2 关键词去重聚合。
- [ ] 关键词回填具备幂等性，且输出覆盖率对比证据（before/after）。

### 3. 验收测试用例（Given / When / Then）

#### 案例 ID: ACC-P1-P2-01
Given:
- 30 案例测试集
- baseline 与 dynamic 两组配置
When:
- 执行全量对比评测
Then:
- dynamic 组候选爆炸比 < 5%
- 精度代理指标不低于 baseline
- 形成可追溯报告（含参数与时间戳）

#### 案例 ID: ACC-P1-P2-02
Given:
- 高噪声事件样本
When:
- 启用 `balanced` profile
Then:
- 候选数量落在 3~30
- 超出窗口时触发回退/重算并记录

#### 案例 ID: ACC-P1-P2-03
Given:
- 主题创建流程进入 `generate_theme_data_only`
When:
- 执行分类复用与创建路径决策
Then:
- 不得使用随机/零向量直接产出最终主题
- 当存在上游分类结果时必须复用该分类
- 当不存在上游分类结果时，必须基于 AI 关键词创建概念主/子分类路径
- 禁止在创建阶段再次调用 `_match_categories`
- 全流程记录 `classification_source`（`upstream` 或 `created_from_ai_keywords`）以供审计

#### 案例 ID: ACC-P1-P2-04
Given:
- 30 案例测试集
- 三组系统：优化系统、基线纯聚类、久赢恒丰标准口径
When:
- 执行统一评估脚本并输出三方报告
Then:
- 输出题材数量、Precision、Completeness、Separation 四项结果
- 优化系统题材数量位于 8~12
- 优化系统三项质量指标均不低于基线系统

#### 案例 ID: ACC-P1-P2-05
Given:
- 生产灰度开关可配置
When:
- 设置动态阈值策略灰度为 10%
Then:
- 仅 10% 流量进入优化策略，90% 保持基线策略
- 输出两组可对比指标并保留流量分桶证据

#### 案例 ID: ACC-P1-P2-06
Given:
- semantic matcher 已启用三段分层策略
When:
- 输入高相似/中相似/低相似混合集
Then:
- Strong/Candidate/Weak 三段均有可观测命中统计
- Candidate 段进入精排，Weak 段不进入最终决策

#### 案例 ID: ACC-P1-P2-07
Given:
- 30 案例验收执行环境
When:
- 运行 `test_theme_processor.py` 评估任务
Then:
- `source_type=real` 占比为 100%
- 报告中包含 DeepSeek 调用证据（请求ID/时间戳/模型名）

#### 案例 ID: ACC-P1-P2-11
Given:
- 分类表 `financial_categories.keywords` 为空或覆盖不足
- 题材表 `theme_master.tags.keywords` 可用
When:
- 执行分类关键词回填流程
Then:
- L2 分类关键词来自对应 L3 题材关键词去重聚合
- L1 分类关键词来自其子 L2 分类关键词去重聚合
- 回填后 L1/L2 关键词非空覆盖率显著提升

#### 案例 ID: ACC-P1-P2-12
Given:
- 已执行一次分类关键词回填
When:
- 在相同输入数据下再次执行回填
Then:
- 不产生重复关键词
- 第二次执行不应产生额外更新（幂等）
- 输出覆盖率 before/after 指标用于审计

#### 案例 ID: ACC-P1-P2-08
Given:
- 已输出 phase2 行为测试结果
When:
- 校验候选可观测性字段
Then:
- 输出中包含 `candidate_count_raw/candidate_count_windowed/candidate_explosion_ratio`

#### 案例 ID: ACC-P1-P2-09
Given:
- 已输出 `create_new_theme` 决策明细
When:
- 校验分类来源审计字段
Then:
- `t03_validation` 中存在分类来源统计
- 每条 `create_new_theme` 决策均包含 `classification_source`

#### 案例 ID: ACC-P1-P2-10
Given:
- phase2 ADR 文档与行为测试产物
When:
- 校验 ADR 与执行器行为一致性
Then:
- `ADR-005/ADR-011` 归档完整
- 行为侧存在 `decision_ack_verified=true` 证据

### 4. 边界/非目标
- 不做 LLM 裁判生产放量。
- 不做跨市场（非 A 股）数据接入。

### 5. 数据示例（如适用）
输入 JSON：
```json
{
  "event_id": "evt_2001",
  "similarity_distribution": {"p95": 0.79, "p98": 0.86},
  "profile": "balanced",
  "traffic_bucket": "10_percent_gray",
  "source_type": "real"
}
```
预期结果：
- `dynamic_threshold` 被计算并记录
- `segment_bucket` 命中 `Strong/Candidate/Weak` 之一
- 候选数处于 3~30
- 记录 `source_type` 质量统计
- 评估报告包含 `theme_count,precision,completeness,separation`

### 6. 失败标准（必须明确）
- 候选爆炸比 >= 5%。
- 候选窗口长期偏离 3~30。
- dynamic 指标显著劣化且未触发回退。
- 使用随机/零向量结果进入最终决策。
- 创建阶段触发二次 `_match_categories` 推断。
- `create_new_theme` 决策缺失 `classification_source` 审计字段。
- mock 占比超门限仍允许发布。
- 未输出 Strong/Candidate/Weak 分层统计。
- 未按 10% 灰度执行即直接全量切换。
- 30 案例题材数量不在 8~12。
- Precision/Completeness/Separation 任一低于基线系统。
- 验收报告使用模拟调用替代真实 DeepSeek。

### 7. 可观察性要求
- 必需指标：`candidate_count_distribution`、`candidate_explosion_ratio`、`fallback_profile_count`、`mock_source_ratio`、`theme_count`、`clustering_precision`、`collection_completeness`、`theme_separation`、`ab_gray_traffic_ratio`、`classification_source_upstream_count`、`classification_source_ai_keywords_count`。
- 必需日志字段：`event_id,profile,dynamic_threshold,candidate_count,segment_bucket,fallback_triggered,source_type,ab_bucket,classification_source,category_action`。
- 审计条目：A/B 对比报告版本号、数据集版本、执行参数、DeepSeek 请求证据、`test_theme_processor.py` 运行摘要。
- 测试执行分层：`PR 快测=PHASE2_THRESHOLD_SAMPLE=24,PHASE2_THRESHOLD_GRID_SIZE=80`；`合并前门禁=36,100`；`阶段验收=30,100`。

---

## Phase P1.phase3 — LLM 最终裁决落地（Qwen2.5 + llama.cpp）

### 1. 目标（1-3 行）
在分类命中后的候选结果引入二阶段裁判全量复核，并将其落地为最终裁决必经链路，解决“仅向量语义匹配导致错配”的核心问题。控制附加时延与成本，保留可降级可熔断能力。

### 2. 验收目标（清单）
- [ ] 二阶段链路顺序固定为“语义粗筛 -> LLM 裁判最终裁决”，不得绕过粗筛直接裁判。
- [ ] 分类命中后的候选结果必须全量进入 LLM 复核，不得仅对歧义样本复核。
- [ ] 在第一阶段验收流量范围内，最终落库结果必须来自 LLM 裁判结论。
- [ ] 裁判超时必须回退阶段一结果，不阻塞主链路。
- [ ] P95 裁判附加时延 < 800ms。
- [ ] 成本预算超阈触发告警与自动降级。
- [ ] `model_service` 不可用时触发明确降级原因码。
- [ ] 10% 灰度下 `llm_final_judged_ratio >= 95%`。
- [ ] 裁判模型固定为 `Qwen2.5 + llama.cpp`，并保留真实调用证据（request_id/timestamp/model）。

### 3. 验收测试用例（Given / When / Then）

#### 案例 ID: ACC-P1-P3-01
Given:
- 分类命中样本（覆盖高相似与非歧义样本）
- 裁判模式 = full_review（10%灰度控制采纳比例）
When:
- 执行两阶段判定
Then:
- 裁判结果被记录
- 裁判结果进入最终落库
- 输出一致性统计与原因解释

#### 案例 ID: ACC-P1-P3-02
Given:
- 裁判调用延迟超过超时阈值
When:
- 执行裁判链路
Then:
- 自动回退到阶段一结果
- 记录 `timeout_fallback` 原因码

#### 案例 ID: ACC-P1-P3-03
Given:
- model_service 不可用
When:
- 触发裁判
Then:
- 返回阶段一结果
- 记录 `model_unavailable` 降级原因
- 增加告警计数

### 4. 边界/非目标
- 不进行全量生产切流。
- 不要求在第一阶段移除所有降级回退路径。

### 5. 数据示例（如适用）
输入 JSON：
```json
{
  "event_id": "evt_3001",
  "mode": "final_judge",
  "top_candidates": ["theme_a", "theme_b"],
  "score_gap": 0.01
}
```
预期结果：
- 输出裁判建议与 `latency_ms`
- `applied=true`
- 发生超时时返回阶段一结果

### 6. 失败标准（必须明确）
- 未将 LLM 裁判作为最终落库必经链路。
- 分类命中样本未全量复核。
- 10% 灰度下 `llm_final_judged_ratio < 95%`。
- 裁判超时未回退。
- P95 附加时延 >= 800ms。
- 预算超阈无告警或无降级动作。
- 裁判模型栈非 `Qwen2.5 + llama.cpp` 或缺失真实调用证据。

### 7. 可观察性要求
- 必需指标：`arbiter_trigger_rate`、`judge_full_review_ratio`、`llm_final_judged_ratio`、`arbiter_timeout_rate`、`arbiter_p95_latency`、`arbiter_cost_per_1k`。
- 必需日志字段：`event_id,decision_id,arbiter_mode,arbiter_result,applied,timeout,fallback_reason,model_name`。
- 审计条目：最终裁决报告（精度/时延/成本/误判归因）与门禁结论。

---

## Phase P1.phase4 — 回放安全与发布门禁

### 1. 目标（1-3 行）
建立第一阶段发布闭环，确保可回放、可审计、可回滚。要求回放一致率 100%，并将重点问题关闭率纳入发布阻断门禁。

### 2. 验收目标（清单）
- [ ] pending 清理与 durable success 强绑定，不得先清后写。
- [ ] 回放一致率必须为 100%。
- [ ] 发布门禁覆盖：回放一致率、死信率、积压时长、重点问题关闭率。
- [ ] 新题材生成规则可重放（不得使用时间戳参与业务主键）。
- [ ] 死信回放机制可用，回放后状态一致。
- [ ] `P1-ISS-01..10` 全部关闭才允许发布。

### 3. 验收测试用例（Given / When / Then）

#### 案例 ID: ACC-P1-P4-01
Given:
- 一批历史消息和基线输出
When:
- 执行 replay
Then:
- 所有主题状态与映射结果与基线一致
- 回放一致率=100%

#### 案例 ID: ACC-P1-P4-02
Given:
- pending 清理策略开启
When:
- 执行聚类结果落库
Then:
- 先确认 durable success，再执行 pending 清理
- 清理动作具备 `decision_id/trace_id/evidence_id`

#### 案例 ID: ACC-P1-P4-03
Given:
- 重点问题清单存在未关闭项
When:
- 执行 Release Gate
Then:
- 发布被阻断
- 输出未关闭问题列表与证据链接

### 4. 边界/非目标
- 不上线第二阶段 CQRS/状态机体系。
- 不扩展到前端产品层发布门禁。

### 5. 数据示例（如适用）
输入 JSON：
```json
{
  "gate_input": {
    "replay_consistency": 1.0,
    "dead_letter_rate": 0.002,
    "backlog_minutes": 3,
    "issues_closed_ratio": 1.0
  }
}
```
预期结果：
- `release_gate=pass`
- 若 `issues_closed_ratio < 1.0` 则 `blocked=true`

### 6. 失败标准（必须明确）
- 回放一致率 < 100%。
- pending 清理早于 durable success。
- 门禁指标超阈仍放行。
- 新题材代码生成含非确定性字段导致回放结果漂移。
- `P1-ISS-01..10` 存在未关闭项。

### 7. 可观察性要求
- 必需指标：`replay_consistency_rate`、`pending_cleanup_before_durable_count`、`release_gate_block_count`。
- 必需日志字段：`decision_id,trace_id,evidence_id,gate_name,gate_result`。
- 必需审计条目：门禁执行报告、回滚记录、问题关闭证明。

---

## 架构第12章专项验收（第一阶段优化目标与验证体系）

### 1. 目标（1-3 行）
将架构文档第12章的优化验证要求固化为第一阶段发布前强制门禁，确保指标口径、实验流量、模型真实性和测试入口一致。

### 2. 验收目标（清单）
- [ ] 30 案例集三方对比报告完整（优化系统 / 基线纯聚类 / 久赢恒丰标准）。
- [ ] 指标口径固定并可复算：`Precision = 正确归集事件数/总事件数`、`Completeness = AI发现事件数/实际相关事件数`、`Separation = 1 - 交叉混入事件数/总事件数`。
- [ ] 验收执行入口固定为 `test_theme_processor.py`，环境固定为 macOS + Python 3.13。
- [ ] transformer 相关测试在 `conda activate theme_matcher_env` 环境执行并记录环境指纹。
- [ ] 验收报告必须标注真实 DeepSeek 调用证据，禁止以 mock 报告替代最终结论。
- [ ] 第一阶段验收必须证明 `Qwen2.5 + llama.cpp` 最终裁决链路已生效，并满足 `llm_final_judged_ratio >= 95%`（10%灰度）。

### 3. 验收测试用例（Given / When / Then）

#### 案例 ID: ACC-P1-ARCH12-01
Given:
- 30 案例数据集与三组系统输出
When:
- 计算题材数量与三项质量指标
Then:
- 指标口径与公式一致
- 报告包含三方对比与差异结论

#### 案例 ID: ACC-P1-ARCH12-02
Given:
- macOS + Python 3.13 主环境
- `theme_matcher_env` 可用
When:
- 执行 `test_theme_processor.py`
Then:
- 任务成功完成且记录 Python 版本、conda 环境名、依赖哈希

#### 案例 ID: ACC-P1-ARCH12-03
Given:
- DeepSeek 服务可用
When:
- 运行正式验收评估
Then:
- `source_type=real`
- 审计中存在模型名、请求ID、请求时间、响应状态

### 4. 边界/非目标
- 不在本专项中定义第二阶段 CQRS 验收。
- 不扩展前端 UI 维度指标。

### 5. 失败标准（必须明确）
- 评估报告缺失任一公式定义或三方对比结果。
- 未使用指定测试入口或环境不一致。
- 真实 DeepSeek 证据缺失或被 mock 替代。

### 6. 可观察性要求
- 必需日志字段：`dataset_version,run_id,python_version,conda_env,model_name,source_type,request_id`。
- 必需指标：`real_call_ratio`、`report_completeness_ratio`、`arch12_gate_pass`。
- 审计条目：运行命令、环境快照、报告文件哈希。

---

## 跨阶段一致性规则

- 不允许后续阶段削弱前一阶段已通过的验收合约。
- 所有新增字段仅允许向后兼容扩展，不允许语义变更。
- 每个验收目标必须绑定验证方法（测试/扫描/指标/审计）至少一种。
- 任一阶段命中失败标准即该阶段“不通过”。

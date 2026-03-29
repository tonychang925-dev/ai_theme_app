# 第一阶段产品需求文档（PRD_P1）

- 项目：个人投资助理（AI Theme App）
- 文档名称：`prd_p1.md`
- 版本：v1.1
- 状态：Draft for Review
- 编写日期：2026-02-13
- 适用阶段：第一阶段（基础阶段）
- 主要依据：
  - `docs/project_control/PRD.md`
  - `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`

---

## 0. 输入与边界

### 0.1 阶段目标
第一阶段聚焦“新闻 -> 结构化事件 -> 题材映射”的可运行闭环，建立结构化题材知识库与流式处理基线，为后续热度、生命周期、前端产品化提供稳定输入。

### 0.2 范围内（In Scope）
- 新闻抓取、结构化事件抽取、事件流分发。
- ThemeProcessor/DecisionExecutor/ClusteringListener 主链路。
- `major/normal/pending/decision/themes:updates` 流程闭环。
- 新题材创建规则、题材映射落库、基础测试与门禁。
- 第一阶段收敛优化：契约冻结、幂等、动态阈值、LLM 最终裁决（Qwen2.5 + llama.cpp）、回放发布门禁。

### 0.3 范围外（Out of Scope）
- 第二阶段 CQRS 与生命周期状态机落地。
- 面向用户的实时资讯产品层和前端作战台。
- 完整交易信号系统和实盘执行链路。

### 0.4 全局约束
- 不重做现有 Redis Stream 主架构，只做收敛与增强。
- 所有关键链路必须具备追踪字段（至少 `trace_id`）。
- 需求必须可测试、可回放、可量化。
- 风险等级：`High`。

---

## 1. 第一阶段总体验收目标

- AG-01：普通事件快速分类链路 P95 < 200ms。
- AG-02：`major` 未匹配事件必须立即创建新题材，`normal` 未匹配事件必须进入 `pending`。
- AG-03：基于 76 案例集的评估报告可复现，报告包含题材数量、聚类精度、归集完整性、主题分离度。
- AG-04：重复写入率 = 0，回放一致率 = 100%。
- AG-05：动态阈值后候选窗口稳定在 3~30，候选爆炸比 < 5%。
- AG-06：第一阶段必须落地 LLM 最终裁决（Qwen2.5 + llama.cpp）；10% 灰度下 `llm_final_judged_ratio >= 95%`，且 P95 附加时延 < 800ms、成本在预算内。
- AG-07：发布前通过 streams/replay/SLO 门禁，无开放 P0/P1。

---

## 1.1 代码审查驱动的重点问题清单（必须纳入第一阶段）

| 问题ID | 代码模块 | 当前问题（来自代码+ARCH_REVIEW） | 风险等级 | 对应里程碑 |
| --- | --- | --- | --- | --- |
| P1-ISS-01 | `database_service/streams/handlers/theme_processor.py` | `_get_action_for_decision_type` 重复定义，存在行为覆盖风险 | P0 | P1.phase0 / P1.phase1 |
| P1-ISS-02 | `theme_service/services/theme_service.py` | `initialize_with_categories_only`、`discover_category_only` 重复定义；`self.theme_service` 引用异常；初始化状态语义不一致 | P0 | P1.phase0 / P1.phase1 |
| P1-ISS-03 | `database_service/streams/handlers/news_stream_handler.py` | `_process_storage_batch`、`_update_storage_stats` 重复定义；大量 `print/traceback` 调试分支混入生产流程 | P0 | P1.phase0 / P1.phase1 |
| P1-ISS-04 | `database_service/streams/handlers/theme_processor.py`、`database_service/streams/handlers/DecisionExecutor.py` | payload 解析存在降级为 `str(value)` 和弱校验，可能丢失结构化语义 | P0 | P1.phase1 |
| P1-ISS-05 | `database_service/streams/handlers/DecisionExecutor.py` | 执行器缺少硬幂等键门禁；未知 operation 仅 warning 跳过 | P0 | P1.phase1 |
| P1-ISS-06 | `database_service/streams/schedulers/news_stream_scheduler.py`、`news_collector_scheduler.py` | 真实/模拟数据降级策略可运行但缺强门禁，可能掺入过量 mock 数据 | P1 | P1.phase2 / P1.phase3 |
| P1-ISS-07 | `theme_service/matchers/semantic_matcher.py`、`theme_discovery_engine.py` | 固定阈值路径仍占主流程；大量打印调试；生产回退到随机/零向量导致稳定性风险 | P0 | P1.phase2 |
| P1-ISS-08 | `theme_service/creators/theme_data_generator.py` | 题材代码包含时间戳生成，回放非确定性；大量 broad-except + None 返回 | P0 | P1.phase4 |
| P1-ISS-09 | `database_service/streams/handlers/news_stream_handler.py`、`news_stream_processor.py` | 多层 payload 兼容分支过多且格式松散，缺统一 v1/v2 契约校验与失败策略 | P0 | P1.phase0 / P1.phase1 |
| P1-ISS-10 | 全链路（scheduler/handler/processor/theme） | `trace_id`、`payload_version`、`idempotency_key` 未形成硬约束贯通 | P0 | P1.phase0 / P1.phase1 / P1.phase4 |

---

## 2. 第一阶段里程碑定义（Milestones）

## 阶段 P1.phase0 — 运行时收敛与契约冻结

### 1. 目标（可衡量）
建立第一阶段唯一运行时处理链与统一决策契约，消除链路歧义与字段漂移，确保关键字段覆盖率 100%。

### 2. 需求（清单）
- [ ] `PRD-P1-P0-R01` 明确第一阶段唯一处理链：`ThemeProcessor -> DecisionExecutor -> ClusteringListener`。
- [ ] `PRD-P1-P0-R02` 冻结 `DecisionEnvelope v1`（字段、类型、版本规则、兼容策略）。
- [ ] `PRD-P1-P0-R03` 全链路贯通 `trace_id`，支持跨 stream 追踪。
- [ ] `PRD-P1-P0-R04` stream 命名统一并与实现一致（含 `stream:events:decision`、`stream:themes:updates`）。
- [ ] `PRD-P1-P0-R05` 契约变更必须支持 dual-read 过渡，不得一次性破坏旧消息消费。
- [ ] `PRD-P1-P0-R06` 输出链路清单与字段字典文档并完成评审。
- [ ] `PRD-P1-P0-R07` 必须清理重复函数定义并保证单实现真源（覆盖 `P1-ISS-01/02/03`）。
- [ ] `PRD-P1-P0-R08` `news` 消息格式必须收敛到单一契约（禁止无边界递归 payload 解析）。
- [ ] `PRD-P1-P0-R09` 运行时模块必须移除 `print/traceback` 直接输出，统一结构化日志字段。

### 3. 用例（Given / When / Then）
#### 用例 ID: PRD-P1-P0-UC01（唯一链路校验）
**Given**：系统启动并加载 stream handlers。  
**When**：执行链路扫描。  
**Then**：仅存在一个有效决策路由入口。

#### 用例 ID: PRD-P1-P0-UC02（契约版本兼容）
**Given**：输入同时包含 v0/v1 消息。  
**When**：消费端解析。  
**Then**：两者都可被处理并归一到 v1 内部对象。

### 4. 验收标准（测试用例）
- Given 执行入口扫描，When 统计结果，Then 重复入口数=0。
- Given 检查契约字段，When 抽样 decision 消息，Then v1 必填字段覆盖率=100%。
- Given 任一消息处理链，When 查询日志，Then 可按 `trace_id` 关联全链路。
- Given 对目标模块做静态扫描，When 搜索重复函数名，Then 指定高风险重复定义数量=0。
- Given 对运行时目录扫描，When 搜索 `print(` 与 `traceback.print_exc`，Then 生产路径残留=0。

### 5. 非目标（排除项）
- 不调整阈值算法与 LLM 裁判策略。
- 不引入新的业务模块。

### 6. 数据示例（输入/输出）
输入（decision envelope v1）：
```json
{
  "version": "v1",
  "trace_id": "trace_evt_1001",
  "event_id": "evt_1001",
  "decision_type": "update_theme",
  "action": "apply_theme_update",
  "payload_hash": "sha256:abc123"
}
```
输出（归一化内部对象）：
```json
{
  "schema_version": "v1",
  "trace_id": "trace_evt_1001",
  "normalized": true
}
```

---

## 阶段 P1.phase1 — 路由统一与幂等执行

### 1. 目标（可衡量）
确保同一事件在重试/回放情况下结果一致，重复写入率=0，死信率不高于基线。

### 2. 需求（清单）
- [ ] `PRD-P1-P1-R01` 收敛并唯一化 decision routing。
- [ ] `PRD-P1-P1-R02` 实现幂等键：`event_id + action + payload_hash`。
- [ ] `PRD-P1-P1-R03` 决策执行前必须先做幂等命中检查，命中时跳过写入。
- [ ] `PRD-P1-P1-R04` 幂等命中、跳过、失败必须写入可观测日志。
- [ ] `PRD-P1-P1-R05` major/normal 匹配成功后均必须 ACK 原消息。
- [ ] `PRD-P1-P1-R06` `normal` 未匹配必须发布聚类决策并进入 `stream:events:pending`。
- [ ] `PRD-P1-P1-R07` 决策/事件解析必须严格 schema 校验，禁止 `str(value)` 式降级吞错（覆盖 `P1-ISS-04`）。
- [ ] `PRD-P1-P1-R08` DecisionExecutor 必须在执行前检查并落库 `idempotency_key`（覆盖 `P1-ISS-05`）。
- [ ] `PRD-P1-P1-R09` 对未知 action/operation 必须 fail-fast + dead-letter，禁止静默 skip。
- [ ] `PRD-P1-P1-R10` storage handler 对失败消息必须进入受控失败策略（重试上限+死信），避免无限悬挂。

### 3. 用例（Given / When / Then）
#### 用例 ID: PRD-P1-P1-UC01（重复投递幂等）
**Given**：同一事件重复进入执行器。  
**When**：执行第二次写入。  
**Then**：命中幂等键并跳过写入。

#### 用例 ID: PRD-P1-P1-UC02（normal 未匹配路由）
**Given**：normal 事件匹配失败。  
**When**：生成决策并执行。  
**Then**：事件进入 pending 流，且原消息 ACK。

#### 用例 ID: PRD-P1-P1-UC03（非法载荷拦截）
**Given**：decision payload 缺失必填字段或类型错误。  
**When**：执行器解析消息。  
**Then**：消息被拒绝执行并进入 dead-letter，保留错误证据。

### 4. 验收标准（测试用例）
- Given replay 批次输入，When 完成执行，Then 重复写入率=0。
- Given 幂等冲突样例，When 检查落库，Then 只有一次有效写入。
- Given 路由单测，When 覆盖所有 decision_type，Then 路由分支唯一且全覆盖。
- Given 注入非法 payload，When 处理消息，Then 不得出现 `str(value)` 降级执行路径。
- Given 未知 operation 输入，When 执行，Then 必须失败并进入死信，不得静默成功。

### 5. 非目标（排除项）
- 不引入动态阈值与 LLM 裁判逻辑。

### 6. 数据示例（输入/输出）
输入：
```json
{
  "event_id": "evt_2001",
  "action": "create_new_theme",
  "payload_hash": "sha256:xyz999"
}
```
输出：
```json
{
  "idempotency_key": "evt_2001:create_new_theme:sha256:xyz999",
  "status": "duplicate_skip"
}
```

---

## 阶段 P1.phase2 — 动态阈值与候选治理

### 1. 目标（可衡量）
将固定阈值升级为事件级动态阈值，稳定候选规模并提升匹配质量；候选窗口 3~30，候选爆炸比 <5%。

### 2. 需求（清单）
- [ ] `PRD-P1-P2-R01` semantic matcher 支持事件级阈值计算（参考 p95/p98）。
- [ ] `PRD-P1-P2-R02` 支持阈值 profile：`baseline/balanced/strict`。
- [ ] `PRD-P1-P2-R03` 候选治理先于精排执行，保障候选规模受控。
- [ ] `PRD-P1-P2-R04` 输出候选分布与阈值日志用于 A/B 对比。
- [ ] `PRD-P1-P2-R05` 76 案例集必须完成基线与优化组对比报告。
- [ ] `PRD-P1-P2-R06` 关键指标劣化时必须支持 profile 回退。
- [ ] `PRD-P1-P2-R07` 移除固定阈值硬编码主路径，阈值必须由事件分布实时计算（覆盖 `P1-ISS-07`）。
- [ ] `PRD-P1-P2-R08` 生产模式禁止随机向量/零向量回退参与最终匹配决策。
- [ ] `PRD-P1-P2-R09` 必须输出 `source_type(real/mock)` 质量指标，并设置 mock 占比门槛。
- [ ] `PRD-P1-P2-R10` 语义匹配日志改为结构化指标上报，禁止高频逐条打印。

### 3. 用例（Given / When / Then）
#### 用例 ID: PRD-P1-P2-UC01（高噪声事件控候选）
**Given**：全量语义候选过多。  
**When**：执行动态阈值策略。  
**Then**：候选数被收敛到目标窗口后再精排。

#### 用例 ID: PRD-P1-P2-UC02（A/B 指标对比）
**Given**：同批 76 案例输入。  
**When**：运行 baseline 与 dynamic 两组。  
**Then**：输出可比较指标并形成报告。

### 4. 验收标准（测试用例）
- Given 动态阈值开启，When 统计候选规模，Then 候选窗口落在 3~30。
- Given 76 案例评估，When 对比结果，Then 候选爆炸比 <5%，且精度代理指标不低于基线。
- Given 阈值异常波动，When 命中回退条件，Then 自动切回安全 profile。
- Given 生产配置启用，When 匹配异常，Then 不得使用随机/零向量结果作为最终决策。
- Given 调度批次运行，When 统计 source_type，Then mock 占比不超过门禁阈值（超阈阻断发布）。

### 5. 非目标（排除项）
- 不进行 LLM 裁判生产放量。

### 6. 数据示例（输入/输出）
输入：
```json
{
  "event_id": "evt_3001",
  "similarity_scores": [0.92, 0.88, 0.86, 0.72, 0.64],
  "profile": "balanced"
}
```
输出：
```json
{
  "event_id": "evt_3001",
  "dynamic_threshold": 0.84,
  "candidate_count": 4,
  "fallback": false
}
```

---

## 阶段 P1.phase3 — LLM 最终裁决落地（Qwen2.5 + llama.cpp）

### 1. 目标（可衡量）
在高相似错配场景引入二阶段 LLM 裁判，并将其作为最终裁决必经链路，解决“仅向量语义导致错配”的核心问题，同时控制时延和成本。

### 2. 需求（清单）
- [ ] `PRD-P1-P3-R01` 固化两阶段顺序：`语义粗筛 -> LLM 最终裁决`，语义层仅做候选召回。
- [ ] `PRD-P1-P3-R02` 第一阶段验收范围内，最终落库结果必须来自 LLM 裁判结论（可灰度切流）。
- [ ] `PRD-P1-P3-R03` 超时必须回退到阶段一结果，不阻塞主链路。
- [ ] `PRD-P1-P3-R04` 记录裁判结果、置信度、一致性与成本数据。
- [ ] `PRD-P1-P3-R05` 产出最终裁决效果报告（精度、时延、成本、误判归因）。
- [ ] `PRD-P1-P3-R06` 10% 灰度下 `llm_final_judged_ratio >= 95%` 后才允许扩大流量。
- [ ] `PRD-P1-P3-R07` 裁判输入必须携带 `source_type` 与质量标签，mock 样本默认不参与生产裁判。
- [ ] `PRD-P1-P3-R08` ModelService 不可用时必须触发降级策略并记录原因码，不得静默回退。
- [ ] `PRD-P1-P3-R09` 裁判链路必须具备熔断与超时预算保护（按分钟窗口）。
- [ ] `PRD-P1-P3-R10` 裁判模型栈固定为 `Qwen2.5 + llama.cpp`，验收报告需附真实调用证据（request_id/timestamp/model）。

### 3. 用例（Given / When / Then）
#### 用例 ID: PRD-P1-P3-UC01（歧义样本触发裁判）
**Given**：Top 候选语义分差低于阈值。  
**When**：进入二阶段裁判。  
**Then**：返回最终裁决结果并附可解释理由，结果进入最终落库路径。

#### 用例 ID: PRD-P1-P3-UC02（裁判超时回退）
**Given**：LLM 调用超时。  
**When**：触发超时策略。  
**Then**：回退至阶段一匹配结果并持续处理。

### 4. 验收标准（测试用例）
- Given 10% 灰度开启，When 执行歧义样本，Then `llm_final_judged_ratio >= 95%` 且裁判结果用于最终落库。
- Given 压测运行，When 统计附加时延，Then P95 < 800ms。
- Given 成本监控开启，When 超预算，Then 触发告警并可降级关闭裁判。
- Given model_service 异常，When 触发裁判，Then 系统返回阶段一结果并记录降级证据。

### 5. 非目标（排除项）
- 不进行全量生产切流。
- 不要求一步到位取消所有降级回退路径。

### 6. 数据示例（输入/输出）
输入：
```json
{
  "event_id": "evt_4001",
  "top_candidates": ["theme_a", "theme_b"],
  "score_gap": 0.01,
  "mode": "final_judge"
}
```
输出：
```json
{
  "event_id": "evt_4001",
  "arbiter_decision": "theme_b",
  "confidence": 0.78,
  "latency_ms": 612,
  "applied": true
}
```

---

## 阶段 P1.phase4 — 回放安全与发布门禁

### 1. 目标（可衡量）
建立可回放、可审计、可发布的第一阶段闭环，回放一致率 100%，发布门禁上线并稳定运行。

### 2. 需求（清单）
- [ ] `PRD-P1-P4-R01` pending 清理必须与 durable success 强绑定，避免误清理。
- [ ] `PRD-P1-P4-R02` 建立 replay 测试集与故障演练脚本。
- [ ] `PRD-P1-P4-R03` 发布门禁接入核心指标：回放一致率、死信率、积压时长。
- [ ] `PRD-P1-P4-R04` 发布流程必须执行 streams + 全仓测试命令集。
- [ ] `PRD-P1-P4-R05` 门禁失败时必须可回滚并保留故障证据。
- [ ] `PRD-P1-P4-R06` 产出第一阶段收口报告与第二阶段输入清单。
- [ ] `PRD-P1-P4-R07` `theme_data_generator` 生成规则必须可重放（去除时间戳参与业务主键）。
- [ ] `PRD-P1-P4-R08` pending 清理动作必须记录 `decision_id/trace_id/evidence_id` 三元证据。
- [ ] `PRD-P1-P4-R09` 发布门禁新增“重点问题关闭率”指标：`P1-ISS-01..10` 未关闭不得发布。
- [ ] `PRD-P1-P4-R10` 建立死信回放机制并验证回放后状态一致。

### 3. 用例（Given / When / Then）
#### 用例 ID: PRD-P1-P4-UC01（回放一致性）
**Given**：历史批次消息与基线结果。  
**When**：执行 replay。  
**Then**：状态与映射结果完全一致。

#### 用例 ID: PRD-P1-P4-UC02（门禁阻断发布）
**Given**：死信率超过阈值。  
**When**：执行 Release Gate。  
**Then**：发布被阻断并要求修复后重试。

### 4. 验收标准（测试用例）
- Given replay 流程，When 比对输出，Then 回放一致率=100%。
- Given 发布门禁，When 指标异常，Then 发布流程必须失败并报警。
- Given 故障演练，When 执行回滚，Then 系统恢复到上一个可用版本。
- Given 同一事件多次回放，When 生成新题材代码，Then 代码与结果必须完全一致。
- Given 重点问题清单存在未关闭项，When 执行 Release Gate，Then Gate 必须阻断发布。

### 5. 非目标（排除项）
- 不包含第二阶段状态模型（CQRS）上线。

### 6. 数据示例（输入/输出）
输入（门禁指标）：
```json
{
  "replay_consistency": 1.0,
  "dead_letter_rate": 0.003,
  "backlog_minutes": 4
}
```
输出（门禁结果）：
```json
{
  "release_gate": "pass",
  "blocked": false,
  "evidence_id": "gate_20260213_01"
}
```

---

## 3. 里程碑依赖与排期

- 依赖：`P1.phase0 -> P1.phase1 -> P1.phase2 -> P1.phase3 -> P1.phase4`
- 推荐总工期：20 人天（风险调整口径）。
- 关键阻塞节点：
  - `P1.phase0` 契约冻结完成前，不得进入幂等与阈值改造。
  - `P1.phase1` 幂等键定稿前，不得进行回放一致性验收。

---

## 4. 第一阶段验收清单（总表）

- [ ] 主链路稳定：major/normal/pending/decision/updates 全链路可运行。
- [ ] 性能达标：快速分类 P95 < 200ms。
- [ ] 质量达标：候选爆炸比 <5%，重复写入率=0。
- [ ] 可回放达标：回放一致率=100%。
- [ ] 灰度达标：LLM 最终裁决链路在 10% 灰度下满足 `llm_final_judged_ratio >= 95%` 且时延/成本达标。
- [ ] 发布达标：Release Gate 全部通过且无开放 P0/P1。
- [ ] 代码问题闭环：`P1-ISS-01` 到 `P1-ISS-10` 全部关闭并有证据链接。

---

## 5. 风险与缓解（第一阶段）

- 风险 R1：动态阈值在热点行情下失稳。  
  缓解：分位数回退 + profile 切换 + A/B 门禁。
- 风险 R2：LLM 裁判时延和成本波动。  
  缓解：10% 灰度分桶、预算告警、熔断回退、超时失败预算门禁。
- 风险 R3：pending 清理时序错误导致回放不一致。  
  缓解：durable success 绑定、演练脚本、发布阻断。
- 风险 R4：契约字段漂移导致上下游兼容失败。  
  缓解：v1 冻结、dual-read 过渡、契约测试。

---

## 6. 术语与缩写

- `major/normal`：重大/普通事件流。
- `pending`：待聚类事件流。
- `DecisionEnvelope`：统一决策消息契约。
- `Replay`：按历史输入重跑以验证一致性。
- `Shadow`：影子模式，仅记录不影响生产结果。

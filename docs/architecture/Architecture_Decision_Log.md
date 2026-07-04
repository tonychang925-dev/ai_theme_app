# AI Theme App Architecture Decision Log

> 状态：Append-only
> 目的：用一页时间线解释系统为何演进成当前形态
> 详细依据：`docs/adrs/ADR_LIST.md`
> 总体基线：`docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md`

---

## 使用规则

Decision Log 不是 ADR 的替代品。

它只记录：

- 已接受或已验证的重要决策；
- 对总体架构、核心契约、Source of Truth、迁移和治理有长期影响的决策；
- 新成员需要理解的关键转折。

不记录：

- 普通 Bug Fix；
- 不改变语义的重构；
- 尚未接受的提案；
- 日常实现细节。

维护规则：

1. 只追加，不改写历史结论。
2. 决策失效时新增 `SUPERSEDED` 记录，不删除原记录。
3. 每条记录必须链接 ADR 或冻结基线中的 Decision ID。
4. 摘要只写“决定了什么、为什么、影响什么”，详细论证留在 ADR。

---

## Decision Timeline

### 2026-05 — DailyReviewV2 成为结构化页面契约

| 字段 | 内容 |
|---|---|
| Decision | 盘后主体从文本 section 迁移到结构化 DailyReviewV2；旧 section 保留兼容和 diagnostics |
| Why | 文本反解析导致字段漂移、空栏目和前端制造业务语义 |
| Impact | 建立市场、题材、资金、强势股、观察清单、龙虎榜等页面级 DTO |
| Reference | `盘后复盘模块彻底重构设计文档.md` 第 21～23 章 |
| Status | ACTIVE |

### 2026-07-03 — Notion 主体收口到结构化契约

| 字段 | 内容 |
|---|---|
| Decision | Notion 默认主体只消费 DailyReviewV2/Engine 结构化字段；Publisher 与 Renderer 分离 |
| Why | 新旧模板并行造成重复栏目、空栏目和静默渲染失败 |
| Impact | 有效内容驱动渲染，数据缺口集中展示，核心异常 fail-fast |
| Reference | `ADR-NOTION-001` ～ `ADR-NOTION-004` |
| Status | ACTIVE |

### 2026-07-04 — M8 定位为 Cognitive Orchestration Layer

| 字段 | 内容 |
|---|---|
| Decision | M8 不重写 Layer A/B/C/D，不拥有业务真源，只消费标准化 Knowledge/Evidence |
| Why | 保护现有领域算法与复盘链路，避免形成第二事实系统 |
| Impact | M8 作为只读旁路，通过 Adapter、Snapshot 和 feature flag 渐进接入 |
| Reference | `Overall-ADR-001`、`Overall-ADR-008`、`Overall-ADR-009` |
| Status | FROZEN BASELINE |

### 2026-07-04 — Stable Core 与 Adaptive Layer 分离

| 字段 | 内容 |
|---|---|
| Decision | Stable Core 固定为 Evidence、Context、CognitionState、Hypothesis、Thesis；M9 能力归入 Adaptive Layer |
| Why | 防止对象与 Engine 持续膨胀，控制 Phase 0 范围 |
| Impact | Stable Core 顶层对象预算不超过 5；M9 在 Phase 0/1 延期 |
| Reference | `Overall-ADR-001`、`Overall-ADR-005`、`Overall-ADR-010` |
| Status | FROZEN BASELINE |

### 2026-07-04 — Snapshot 与 State 生命周期分离

| 字段 | 内容 |
|---|---|
| Decision | Snapshot 不可变；Belief/Hypothesis 等 State 可更新，但必须通过事件和 checkpoint 重建 |
| Why | 同时满足跨日连续状态、审计和 Replay |
| Impact | 引入 state transition、idempotency、checkpoint/rebuild 门禁 |
| Reference | `Overall-ADR-003` |
| Status | FROZEN BASELINE |

### 2026-07-04 — Market Narrative 更名为 Market Thesis

| 字段 | 内容 |
|---|---|
| Decision | 对外认知读模型使用 Market Thesis，Narrative 只作为语言表达过程 |
| Why | 避免将结构化研究结论误解为自由故事 |
| Impact | Thesis 强制 EvidenceRef、替代命题、Scenario 和失效条件 |
| Reference | `Overall-ADR-004` |
| Status | FROZEN BASELINE |

### 2026-07-04 — PostMarketFactBundle 更名为 MarketKnowledgeBundle

| 字段 | 内容 |
|---|---|
| Decision | 现有领域输出汇聚边界统一命名为 MarketKnowledgeBundle |
| Why | ThemeCycle、Mainline、StrongStock 等已是领域 Knowledge，不是原始 Fact |
| Impact | 数据链统一为 KnowledgeBundle -> EvidenceAdapter -> EvidenceSnapshot |
| Reference | `Overall-ADR-011` |
| Status | FROZEN BASELINE |

### 2026-07-04 — QualityEnvelope 统一质量传播

| 字段 | 内容 |
|---|---|
| Decision | Knowledge、Evidence、Context、Cognition、Thesis 共用统一 QualityEnvelope |
| Why | 防止数据缺失时下游仍输出高置信结论 |
| Impact | 下游 Confidence 受关键上游 Quality 上限约束 |
| Reference | `Overall-ADR-015` |
| Status | FROZEN BASELINE |

### 2026-07-04 — Notion 采用 Thesis + Evidence 双层报告

| 字段 | 内容 |
|---|---|
| Decision | 上层新增认知首页，下层保留原有市场、题材、资金、龙虎榜等证据章节 |
| Why | Narrative/Thesis 应索引事实，不应替代事实 |
| Impact | 首个生产目标是 `dual_layer`，M8 失败回退 `legacy_only` |
| Reference | `Overall-ADR-009`、`Overall-ADR-018` |
| Status | PHASE 0 TARGET |

### 2026-07-04 — Architecture Baseline v4.0 正式冻结

| 字段 | 内容 |
|---|---|
| Decision | 不发布 v4.1；20 个真实交易日内不新增顶层对象、Engine 或 M9 正式能力 |
| Why | 架构已足够完整，主要风险转为实现范围膨胀和缺乏真实验证 |
| Impact | 新想法进入 Architecture Backlog；结构变化采用 ADR-only Policy |
| Reference | `Overall-ADR-017`、`Overall-ADR-018` |
| Status | ACTIVE FREEZE |

### 2026-07-04 — 建立轻量 ARB 与风险分级审批

| 字段 | 内容 |
|---|---|
| Decision | ARB 只裁决 P0、Stable Core、Source of Truth、Baseline、Freeze 和迁移；普通 Adapter/模板走轻量审批 |
| Why | 明确裁决权，同时防止治理成为 Phase 0 瓶颈 |
| Impact | L0～L3 Decision Matrix、异步优先、Review SLA、Emergency Path |
| Reference | `ADR-ARCH-GOV-001` |
| Status | ACTIVE |

### 2026-07-04 — Architecture Delegate 与治理健康度

| 字段 | 内容 |
|---|---|
| Decision | Chief Architect 可按 Domain/时间窗口书面授权 Architecture Delegate；增加 Decision Log 与 Governance Health Dashboard |
| Why | 避免 Chief Architect 成为日常审批单点，并使治理状态可快速观察 |
| Impact | Delegate 不能同时批准自身变更；Baseline/Stable Core 重大变更仍需 Chief Architect 最终确认 |
| Reference | `ADR-ARCH-GOV-002` |
| Status | ACTIVE |

---

## Next Expected Decision

下一条总体架构决策不应是新增 Engine。

预期记录顺序：

```text
Phase 0 Contract Accepted
-> Evidence Shadow Passed
-> Cognition Shadow Passed
-> Notion Dual Layer Approved
-> 20 Trading-Day Validation Completed
```

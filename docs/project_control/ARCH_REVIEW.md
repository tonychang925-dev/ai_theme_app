# ARCH REVIEW — P4.phase0（前端第四阶段）架构评审

## 1. 当前架构摘要（Current Architecture Summary）
- 当前前端第四阶段采用“三栏作战台 + 统一 `/api/v2/*` 出口”路线，技术栈与产品形态合理。
- 实时链路采用 `SSE 主通道 + feed 兜底`，与当前数据链路成熟度匹配。
- 代码侧已完成关键收口：`frontend/src` v2 路由统一、v2 contract tests、A/B/D 核心门禁脚本可执行。
- 主要差距从“实现缺失”转为“连续运行指标与治理闭环”。

## 2. 风险矩阵（Risk Matrix）
| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | Trigger | 缓解措施 | Owner |
|---|---|---|---|---|---|---|---|---|
| R-P4-001 | P0 | 接口口径漂移导致 405/契约回退 | `/intel` 主链路 | 中 | 中 | 前端新增非 v2 路径/后端缺 v2 别名 | CI 路径阻断 + v2 contract tests + 路由兼容层 | FE/BFF |
| R-P4-002 | P0 | SSE 不稳定导致中栏不可用 | Intel 实时面板 | 中 | 中 | stream 建连失败率升高 | 自动重连 + feed fallback + 事件白名单 | FE/BFF |
| R-P4-003 | P1 | 连续 5 交易日门槛未达标 | 阶段准入 | 中 | 低 | 成功率/覆盖率波动 | 灰度分批 + 回滚矩阵 + 日报审计 | Release/QA |
| R-P4-004 | P1 | DTO 字段演进无约束引发前端崩溃 | 三栏所有面板 | 低 | 中 | 字段语义变更/删除 | DTO 兼容规则（只增不破）+ 契约文档门禁 | BE/BFF |
| R-P4-005 | P2 | 工作台页面扩展过早侵蚀稳定期 | 迭代节奏 | 中 | 低 | 并行功能过多 | 冻结窗口 + Feature Flag 治理 | PM/Tech Lead |

## 3. 维度化发现

### 3.1 契约与一致性
- 优点：`/api/v2/*` 收口方向正确；已补 contract test。
- 问题：历史文档存在 `strong_watch` 路由双口径，需要持续单一真源化。

### 3.2 性能与稳定性
- 优点：SSE + feed 兜底设计合理，失败可降级。
- 问题：缺“连续 5 交易日”自动化统计产物与趋势告警面板。

### 3.3 可观测性
- 优点：已有门禁命令可复现。
- 问题：缺统一指标采集（stream 成功率、fallback 次数、reconnect 分布）。

### 3.4 可运维性
- 优点：有灰度开关矩阵与回滚思路。
- 问题：回滚演练结果未形成固定模板/审计记录标准。

## 4. 目标架构（Target Architecture）
- 入口层：`frontend` 仅消费 `/api/v2/*`。
- 聚合层：`frontend_bff` 作为前端唯一业务聚合出口（兼容期允许旧路由别名，但不得被前端依赖）。
- 实时层：`/api/v2/intel/stream` + `/api/v2/intel/feed` 自动降级闭环。
- 对象层：workspace 三接口固定 DTO，字段仅增量演进。
- 门禁层：CI（路径阻断 + contract tests）+ 发布前回放门禁（A/B/D）。

## 5. 迁移计划（Migration Plan）
1. M0（已完成）：v2 收口、405 修复、contract tests 入 CI。  
2. M1（1周）：补齐运行指标采集与日报（feed/stream 成功率、fallback、重连）。  
3. M2（1周）：固化回滚演练剧本与审计模板（RTO<=5分钟）。  
4. M3（持续）：移除前端对兼容旧别名的潜在依赖，推进单一路由真源。  

## 6. 子阶段方案（phase 模式）
- `P4.phase0`：统一出口 + 三栏最小可用 + 门禁就绪（当前）
- `P4.phase1`：连续运行指标达标（5交易日）+ 回滚演练闭环
- `P4.phase2`：扩大页面迁移范围（themes/stocks/screener 等）并保持契约稳定

## 7. ADR 建议清单（摘要）
- ADR-001：统一前端路由口径为 `/api/v2/*` 并以 CI 阻断。
- ADR-002：实时链路采用 `SSE-first + feed fallback`，WS 非必选。
- ADR-003：BFF 作为前端聚合唯一真源（兼容期保留别名）。
- ADR-004：发布门禁采用“回放一致性 + 覆盖率阈值 + 契约测试”三重判据。

## 8. 冲突裁决记录
- 冲突1：`/api/v2/intel/strong-stocks/watch` vs `/api/v2/strong_watch`
  - 裁决：前端统一调用前者；后者作为内部/兼容口径。
- 冲突2：SSE 与 WS 优先级
  - 裁决：SSE 主通道先落地，WS 后置，不阻塞阶段通过。

## 9. 非目标范围（Non-Goals）
- 不在本阶段引入 Tick 级全市场实时平台。
- 不在本阶段完成产业链独立图谱服务化。
- 不在本阶段放开所有页面的大规模功能扩展。

---

## 10. 增量评审记录（2026-04-30，追加）

### 10.1 本次增量范围
- 仅补充第四阶段前端架构的“代码对齐状态 + 门禁可执行性”。
- 不重写第 1~9 节结论，不替换历史裁决。

### 10.2 代码对齐结论（增量）
1. 前端 `frontend/src` 已完成 `/api/v2/*` 路径收口，且 CI 阻断规则已生效。  
2. `/api/v2/intel/feed`、`/api/v2/intel/stream`、`/api/v2/workspace/*` 已具备可用性。  
3. `SSE 主通道 + feed fallback` 已形成可运行闭环。  
4. 强势股页面读口按评审裁决统一为 `/api/v2/intel/strong-stocks/watch`。  

### 10.3 门禁证据（增量）
- v2 contract tests：`frontend_bff/tests/unit/test_v2_contract_aliases.py`（通过）。  
- D 层输入收口单测（7日窗口/Universe/Admission）已通过。  
- A/B 回放目标日期已执行，无差异样本通过。  
- Layer B confirmed 覆盖率达到 >=95% 门槛（当前样本 >95%）。  

### 10.4 待完成项（增量）
1. 连续 5 个交易日的运行指标报表（feed 成功率、stream 连接成功率、fallback 次数）需形成固定日报。  
2. 回滚演练记录需补“执行时间、RTO、失败注入场景、结论”模板化归档。  
3. 兼容期结束后，清理不再被前端消费的旧别名路由，减少双口径维护成本。  

---

# ARCH REVIEW — P3 新旧股票链路收口后优化计划（2026-05-06）

## 1. 当前架构摘要（Current Architecture Summary）

本次评审范围为第三阶段股票服务模块，重点对照 `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`、`架构差距分析报告.md`、`docs/architecture/项目状态更新-2026-05-06.md`、旧链 `stock_service/*` 与新链 `stock_processing_service/*`。

当前状态已经从“链路修复”进入“证据质量增强与旧链字段级复刻”阶段。新链已形成 `BuildIdentityJob -> BuildThemeCycleEvidenceDailyJob -> BuildDailySnapshotJob -> BuildPostMarketRecapJob` 闭环，并通过 Ports/Gateway 隔离 DB 读写；旧链仍是字段口径、边界规则和历史样本解释的主要参考真源。

已确认的代码事实：
- `BuildDailySnapshotJob` 强制读取 `theme_cycle_evidence_daily`，空 DB 真源直接 fail-fast。
- `BuildThemeCycleEvidenceDailyJob` 已加入 evidence 生成、写入、write-verify、结构化 warnings 和 K 线证据生成。
- `SubjectCycleJudgementService` 已实现 7 状态优先级与 6 项退潮证据计数。
- `StrongWatchAdmissionPolicy`、`StrongWatchPromoteService`、`W2SCandidateService` 已从旧的 S/A+78 硬门转为 AdmissionPolicy 驱动，并保留 observe 分桶。
- Replay 覆盖已包含神剑股份、联德股份；维科科技 4/22-23 仍是当前最新状态文档标记的待验证样本。

## 2. 风险矩阵（Risk Matrix）

| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | Trigger | 缓解措施 | Owner |
|---|---|---|---|---|---|---|---|---|
| R-P3-001 | P0 | Layer B 新旧链 `fade_confirmed` 硬条件不完全一致：旧链 V2 要求分数、证据数、K线支撑破位共振；新链当前仅依赖分数与证据数 | 周期判定、Layer C 入池、D 层候选 | 中 | 中 | 退潮样本误杀或误放行 | 增加字段级 diff 与 `fade_confirmed` 回放门禁；冻结是否补回 `support_break` 的 ADR | Domain/QA |
| R-P3-002 | P0 | Evidence builder 仍存在受限 fallback/proxy 口径，如 event_stats 缺失回退 pool metadata、event_recency 用 distinct_event_days 代理 | B 层证据可信度 | 中 | 中 | event_stats_hit_count 低、kline_quality 非 ok 占比高 | 将 fallback 仅保留为 diagnostic，生产路径门禁化；补事件/板块/Leader 真源字段 | Data/Domain |
| R-P3-003 | P1 | 维科科技 4/22-23 未纳入正式 replay 断言，连续样本矩阵不足 | A/B/C/D 连续性 | 高 | 低 | 第三样本仍只能人工解释 | 新增 replay case 与 continuity matrix，覆盖 target present/入池/候选/D层拒因 | QA/Domain |
| R-P3-004 | P1 | D1 `candidate_score` 当前与文档 5 维加权公式不一致，且部分变量是诊断口径 | 弱转强排序、observe/formal | 中 | 中 | 联德排序偏低、候选解释与文档不一致 | 冻结 D1 公式版本；先双轨输出 diff，再决定对齐或修订文档 | Domain/PM |
| R-P3-005 | P1 | Layer C/D 仍存在 feature gate 和 replay-only 旁路，长期保留会形成双口径 | 正式入池与回放一致性 | 中 | 中 | 环境变量打开后结果漂移 | 建立 Feature Flag Register 与默认值门禁；replay-only 只允许测试路径 | Tech Lead |
| R-P3-006 | P2 | LLM 复核仍是确定性 stub，旧链的 LLM/龙虎榜/资金行为数据未进入新链 D 层 | 边界样本解释、角色裁决 | 中 | 高 | 边界样本无法解释或人工复盘不一致 | 后置到证据质量稳定后接入；LLM 只做复核/归纳，不覆盖规则真源 | Domain/LLM |

## 3. 维度化发现

### 3.1 契约与一致性
- 新链分层方向正确：Application 只编排，Domain 算规则，Ports/Gateway 负责读写。
- 当前最大一致性缺口不在分层，而在旧链字段口径是否逐项复刻，尤其是 `fade_confirmed`、Leader layer、Board layer、D1 candidate scoring。
- 后续计划必须以 `docs/architecture/项目状态更新-2026-05-06.md` 为当前真源，避免继续引用差距报告中的过期阶段结论。

### 3.2 数据真源与证据质量
- `theme_cycle_evidence_daily` 已成为 B 层 DB 真源，write-verify 是正确收口。
- 事件层、Leader 层、Board 层、K线层都已经有结构，但部分字段仍是简化或代理计算，尚未达到“旧链字段级复刻”。
- `BuildThemeCycleEvidenceDailyJob` 已暴露 `event_stats_hit_count`、`kline_ok_count` 等指标，适合直接转为门禁阈值。

### 3.3 性能与运行稳定性
- 目前主要风险不是性能，而是连续多日 replay 与字段级 diff 不足。
- K 线构建按 subject 聚合历史 bars，后续若 subject/stock 规模扩大，需要补充耗时指标和缓存策略。

### 3.4 可观测性与可回放
- replay runner 已具备 live DB 与 readonly artifact 双模式，适合扩展为连续样本矩阵。
- 当前缺一份稳定产物：按交易日、样本、Layer A/B/C/D 输出 passed/failed、首个断点、关键字段 diff。

## 4. 目标架构（Target Architecture）

第三阶段下一步目标不是另起服务，而是在既有新链上完成四项收口：
1. B 层：`theme_cycle_evidence_daily` 成为可复刻、可解释、可门禁的唯一周期证据真源。
2. C 层：Strong Watch 从 Universe、Admission、Promote 到 D 候选的分桶语义稳定，feature gate 不造成生产漂移。
3. D 层：盘后候选和盘前确认形成两阶段输出，先规则可解释，再接入 LLM/龙虎榜/资金流增强。
4. QA 层：神剑、联德、维科、反例样本形成连续 5 交易日 replay 矩阵，阶段验收以矩阵和字段 diff 为准。

## 5. 迁移计划（Migration Plan）

### P1：证据质量增强与第三样本补齐（本周）

目标：让 P0 闭环从“能跑通”变成“可高效回放、证据可信、样本可解释”。

任务：
1. 新增 ReplayRunner + replay snapshot manifest：支持 `reuse_all`、`rebuild_output`、`rebuild_pool`、`rebuild_feature`、`full_rebuild`，避免每次从 A/B/C/D 全链重算。
2. 新增弱转强固定样本 YAML：神剑、联德、维科按 Layer A/B/C/D 逐层断言。
3. 新增维科科技 2026-04-22/23 replay：逐层断言 A 身份、B 周期、C formal/observe、D 拒因或候选结果。
4. 增强 Leader layer：补 `leader_stock_id`、`leader_breakdown_reason`、`successor_vacuum`、`front_row_alive_count`。
5. 增强 Board layer：补 `subject_strong_count`、`board_effect_confirmed`、`volume_breakdown_flag`，并进入 evidence_json。
6. 固化 K 线字段：确认 `above_ma5` 已从 `ThemeKlineEvidenceBuilder` 写入 evidence_json，并补 DB/contract 暴露策略。
7. 建立 P1 门禁：`event_stats_hit_count > 0`、`kline_ok_count` 可解释、`history_bar_count/unique_stock_count` 可观测、write-verify 必须通过。

验收：
- 神剑、联德、维科三样本 replay 均有明确 A/B/C/D 断言。
- 任一样本失败时输出首个断点与关键 evidence diff。
- 不新增生产 fallback；若保留兼容路径，必须标记 diagnostic。
- 调 D1 排序时可走 `rebuild_output`，调 Layer B evidence 时可走 `rebuild_feature`。

### P2：旧链字段级复刻与 D1 公式冻结（下周）

目标：解决“结果能用但口径不稳”的问题。

任务：
1. 扩展 `ab_compare_mainline_cycle.py` 为字段级 diff：`event_strength_score`、`event_continuity_score`、`leader_alive_score`、`relay_strength_score`、`front_row_strength_score`、`theme_support_score`、`break_start_pivot`、`red_ratio`、`big_drop_ratio`。
2. 针对 `fade_confirmed` 做专项门禁：对比旧链 `support_break` 条件与新链判定差异，输出误杀/误放行列表。
3. 冻结 D1 `candidate_score`：要么按文档 5 维公式对齐，要么修订文档并记录 ADR，禁止继续隐式漂移。
4. 联德 observe 排序调优：只在 diff 证据支撑下调整 `prev_low_support`、gap、weakness 权重。

验收：
- 字段级 diff 报告可生成 JSON。
- `fade_confirmed` 历史日重复回放一致。
- D1 评分公式有版本号、测试样本和 ADR。

### P3：连续回放、盘前确认与增强数据接入（持续治理）

目标：从盘后候选走向可执行的两阶段决策。

任务：
1. 连续 5 交易日 replay：神剑、联德、维科、反例样本输出 continuity matrix。
2. D2 盘前确认链路：接入 `weak_to_strong_auction_signal`，输出 A/B/C/X 与 hard reject reason。
3. LLM 复核接入：`IdentityLLMReviewService` 从确定性 stub 升级为真实服务，但只进入 review/summary，不直写规则真源。
4. 龙虎榜/资金流/游资行为作为 D 层解释增强，不反向污染 A/B 真源。
5. database_service migration 固化：唯一索引、字段 DDL、current pointer 与回滚脚本纳入门禁。

验收：
- 连续矩阵包含 layer_status、first_break_layer、target_presence、candidate_level、reject_reason。
- 盘前确认可解释“为什么 A/B/C/X”，且 DB 只读优先，不依赖临时文件补算。
- LLM 失败时规则链路仍可运行，输出 `llm_review_status`。

## 6. 子阶段方案

| 子阶段 | 核心降风险目标 | 必跑门禁 | 回滚策略 |
|---|---|---|---|
| P3.next-1 | 回放效率体系与第三样本骨架 | ReplayRunner 单测 + 样本 YAML 加载 + manifest DDL 校验 | 不接生产 DB manifest，仅保留本地 runner |
| P3.next-2 | 补齐第三样本与证据字段 | 维科 replay + 神剑/联德回归 + evidence write-verify | 保持现有 P0 版本，关闭新增字段消费 |
| P3.next-3 | 旧链字段级 diff 与 `fade_confirmed` 冻结 | 字段 diff JSON + fade 回放一致性 | 新链继续消费旧判定字段，推迟切换 |
| P3.next-4 | D1 评分公式冻结 | D1 单测 + 样本排序报告 | 保留旧 D1 排序版本号 |
| P3.next-5 | D2 盘前确认 | pre-market replay + A/B/C/X reject reason 单测 | 盘前层只读展示，不进入正式建议 |
| P3.next-6 | 连续 5 日治理 | continuity matrix + regression summary | 回退到最近通过矩阵的 snapshot_version |

## 7. ADR 建议清单

- ADR-P3-001：Layer B `fade_confirmed` 必须冻结为“分数 + 证据数 + K线支撑破位”或明确记录新链差异。
- ADR-P3-002：`theme_cycle_evidence_daily` 为 B 层唯一 DB 真源，fallback 只允许 diagnostic，不允许生产静默消费。
- ADR-P3-003：D1 `candidate_score` 公式版本化，文档公式与代码公式必须二选一冻结。
- ADR-P3-004：LLM/龙虎榜/资金流只能增强 D 层解释与复核，不得覆盖 A/B/C 规则真源。
- ADR-P3-005：连续 replay matrix 作为第三阶段后续发布门禁。
- ADR-P3-006：Replay Snapshot Manifest 作为分层回放复用依据。

## 8. 冲突裁决记录

| 冲突 | 采用来源 | 放弃/后置来源 | 裁决理由 |
|---|---|---|---|
| “全链路已恢复” vs “字段级复刻未完成” | `项目状态更新-2026-05-06.md` 的 P0 已闭环结论 | 将“已恢复”解释为算法完全终态 | 代码显示链路已闭环，但 evidence builder 与 D1 仍有简化口径 |
| 旧链 `fade_confirmed` 需要 `support_break` vs 新链当前无该硬条件 | 暂按风险项处理，进入 ADR-P3-001 | 直接假设新链正确 | 这是会影响主线存活与候选池的 P0 口径差异 |
| D 层是否立即接 LLM/龙虎榜/资金流 | 后置到 P3.next-4/5 | 本周直接接入增强数据 | 当前更核心的是 A/B/C/D replay 与字段真源稳定 |
| 维科技术状态 | `项目状态更新-2026-05-06.md` 标记待验证 | 差距报告历史段落中部分已完成描述 | 当前计划以最新状态文档为准，先补正式 replay |

## 9. 非目标范围（Non-Goals）

- 不在下一步重建旧链 `stock_service`。
- 不恢复已删除的生产 fallback。
- 不让前端/BFF 直连 DB 或绕过 `stock_processing_service` 输出。
- 不在证据质量稳定前，把 LLM 结果作为 A/B/C 真源。
- 不在本轮建设 Tick 级或秒级全市场行情平台。

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

---

# ARCH REVIEW — 前端功能调用与旧链脚本服务化迁移评审（2026-05-08）

## 1. 当前架构摘要

本次核查覆盖 `frontend/src`、`web_app_service`、`stock_processing_service`、`database_service`、`stock_service` 与根目录 `scripts`。当前前端调用链基本形成三段式：

`frontend/src/lib/api.ts` -> `web_app_service /api/v2/*` -> `stock_processing_service /api/v1/*` -> `DatabaseGateway/StockReadGatewayAdapter` -> PostgreSQL。

读模型路径整体方向正确：前端只消费 `/api/v2/*`，`web_app_service` 做 BFF/代理/视图转换，`stock_processing_service` 承担股票域应用服务与快照输出。但采集与旧链迁移路径仍存在明显旧架构残留：

- `CollectionPage` 通过 `/api/v2/collection/*` 启动采集，最终进入 `stock_processing_service/application/jobs/collection_job_manager.py`。
- `CollectionJobManager` 仍在 API 进程内拼接命令并 `create_subprocess_exec` 调用 `sync_jyhf_to_local.py`、`database_service/scripts/*.py`、`scripts/build_post_market_recap.py` 等脚本。
- 旧链 `stock_service/services/*` 和 `stock_service/scripts/*` 大量直接使用 `asyncpg`、直接 SQL、直接写表。
- 新链虽然已有 Ports/Gateway/Domain/Application 分层，但 `stock_processing_service/api_app.py` 仍直接 import 部分 `stock_service` 模块，采集、竞价、LLM 队列、龙虎榜、异动等仍未完全服务化。
- Layer C 迁移还处于不稳定阶段：新链 `BuildPostMarketRecapJob` 当前实际路径仍是 `layer_c_input_mode = "seed_query"`，未在应用层真正完成 `SPS_LAYER_C_INPUT_MODE=legacy_watch_pool` 的生产入口切换；已有 `legacy_layer_c_output_report` 只能证明表读口/adapter，不等价于旧链程序 dry-run。

## 2. 风险矩阵

| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | 缓解措施 | Trigger | Owner |
|---|---|---|---|---|---|---|---|---|
| R-SVC-001 | P0 | 采集任务由 API 进程直接拉起旧脚本，参数、环境、日志、取消、超时都耦合在 BFF/API 运行时 | 日采集、补采、盘前竞价、盘后 recap | 高 | 低 | 建立 `CollectionOrchestrator` 与独立应用服务；脚本降为 CLI wrapper | 前端采集报错、token 引号污染、任务中断后状态丢失 | Backend |
| R-SVC-002 | P0 | 旧链脚本直接 SQL 写核心表，绕过新链 Port/Gateway 与版本审计 | 强势池、弱转强、主线状态、竞价、异动 | 高 | 中 | 逐脚本抽取 Application Service，SQL 移入 `DatabaseGateway` 显式方法 | 脚本和新链写同一表、replay 读写不一致 | Backend/Data |
| R-SVC-003 | P0 | Layer C 尚未按旧链程序 dry-run 验明真相；读旧链表不能代表旧链程序输出 | StrongWatch、W2S 候选 | 高 | 中 | 新增 `OldChainLayerCDryRunService`，四路对比 A/B/C/D | legacy table effective_count 与旧链程序输出不一致 | Domain/QA |
| R-SVC-004 | P0 | `BuildPostMarketRecapJob` 未真正接入 `legacy_watch_pool` 生产开关，仍显示 `seed_query` | 盘后 recap、D 层候选输入 | 高 | 低 | 在应用层切换生产输入，当前新 C 层降为 shadow | 设置 `SPS_LAYER_C_INPUT_MODE` 但 recap_doc 仍为 `seed_query` | Domain |
| R-SVC-005 | P1 | `stock_processing_service/api_app.py` 直接 import `stock_service` 旧模块，边界不干净 | API、竞价确认、Tushare 采集 | 中 | 低 | 迁移到 `infrastructure/external` 与 domain/application service | 新链 API 依赖旧链模型/服务 | Backend |
| R-SVC-006 | P1 | `web_app_service/core/read_client.py` 对上游异常返回 error payload，可能让前端误读为空数据或部分数据 | 前端工作台、复盘页 | 中 | 中 | 关键接口 fail-fast，非关键接口明确 `partial=true` | 上游 500/连接失败但前端显示空列表 | BFF |
| R-SVC-007 | P1 | `web_app_service` 与 `frontend_bff` 并存，BFF 边界可能漂移 | 前端 API 契约 | 中 | 中 | 明确唯一生产 BFF，另一路仅保留 legacy/dev | 同一功能存在两个 BFF 路由或不同 DTO | FE/BFF |

## 3. 维度化发现

### 契约与调用一致性

- 前端主入口已集中在 `frontend/src/lib/api.ts`，这是正确方向。
- `/api/v2/collection/*` 到 `/api/v1/collection/*` 的代理链路清晰，但后端执行层不是服务模块，而是脚本编排器。
- 复盘、强势池、候选读模型路径相对干净，采集/构建路径仍是旧脚本驱动。

### 服务边界

- 新链已有 `application/jobs`、`domain/services`、`ports`、`infrastructure/gateway_adapters`，具备承接旧脚本服务化的骨架。
- 旧脚本迁移的目标不应是“把脚本搬到 stock_processing_service/scripts”，而是抽出可测试的 Application Service；脚本只保留 argparse 与调用容器。

### 数据访问

- 正确边界应是：业务层不直接 SQL；所有 SQL 收敛到 `database_service/managers/postgres_manager.py` 或 `database_service/gateway.py` 显式方法。
- 当前旧链 `stock_service/services/*`、`database_service/scripts/*`、根 `scripts/*` 仍存在大量 direct SQL，属于迁移清单。

### 可观测性与回放

- 已有 replay、legacy Layer C output report、manifest 等骨架，但缺旧链程序 dry-run。
- 对旧链迁移不能用“当前表内容”替代“旧链程序输出”；必须用 dry-run 结果做复刻真源。

## 4. 目标架构

目标分层：

1. `frontend`：只负责 UI 与 `/api/v2/*` 调用，不持有业务流程逻辑。
2. `web_app_service`：唯一生产 BFF，负责前端聚合、DTO 兼容、SSE/轮询代理，不跑脚本、不连 DB。
3. `stock_processing_service`：股票域应用服务中心，暴露命令 API 与查询 API；内部通过 Orchestrator 调用服务模块。
4. `domain/services`：纯规则与评分逻辑，无 SQL、无 subprocess。
5. `ports`：定义读写、外部行情、LLM、任务状态等接口。
6. `infrastructure/gateway_adapters`：适配 `DatabaseGateway`、Tushare、LLM、Redis。
7. `database_service`：唯一 SQL 实现层。
8. `scripts`：只作为 CLI wrapper，调用新链容器或应用服务，不承载业务规则。

建议新增或收口的服务模块：

- `stock_processing_service/application/services/collection_orchestrator.py`
- `stock_processing_service/application/services/market_data_collection_service.py`
- `stock_processing_service/application/services/legacy_layer_c_dry_run_service.py`
- `stock_processing_service/application/services/strong_watch_pool_build_service.py`
- `stock_processing_service/application/services/weak_to_strong_candidate_build_service.py`
- `stock_processing_service/application/services/pre_market_auction_service.py`
- `stock_processing_service/infrastructure/external/tushare_market_data_adapter.py`

## 5. 迁移计划

### M0：调用链与脚本清单冻结

- 输出前端页面 -> BFF -> SPS API -> Application Service/Script 的调用矩阵。
- 对所有 direct SQL 脚本标记 Owner、写入表、读取表、是否生产调用。
- CI 增加边界扫描：`stock_processing_service` 禁止新增 direct SQL 和直接 import 旧链服务。

### M1：采集链路服务化止血

- 将 `CollectionJobManager` 从“脚本执行器”改为“任务编排器”。
- `jyhf/tushare/dragon_tiger/abnormal/leader_llm/recap` 分别抽成应用服务。
- 前端 job 状态持久化到 DB 表，替代内存 `self.jobs`。
- 脚本保留，但只调用对应服务模块。

### M2：Layer C 旧链程序 dry-run 与四路 diff

- 新增 `OldChainLayerCDryRunService`：调用旧链真实生成逻辑，`dry_run=True`，不写库。
- 对 `2026-04-15` 输出四路：
  - A. old_chain_layer_c_dry_run
  - B. legacy_table_layer_c
  - C. new_chain_layer_c_shadow
  - D. production_layer_c_input
- 只有 A/D 对齐后，才继续迁移新 C 层。

### M3：旧链核心脚本逐个抽服务

优先级：
1. `stock_service/services/weak_to_strong_candidate_builder.py`
2. `stock_service/scripts/build_strong_stock_watch_pool.py`
3. `stock_service/scripts/build_mainline_identity_registry.py`
4. `database_service/scripts/build_theme_cycle_judgement.py`
5. `database_service/scripts/build_pre_market_auction_snapshot.py`
6. `database_service/scripts/build_pre_market_auction_signal.py`
7. `database_service/scripts/build_stock_abnormal_signal.py`

每个脚本迁移标准：
- 旧逻辑先原样抽入 Application Service。
- SQL 移入 Gateway 显式方法。
- 增加 dry-run。
- 增加 replay/diff report。
- CLI wrapper 不再直接 SQL。

### M4：API 边界清理

- `stock_processing_service/api_app.py` 不再直接 import `stock_service`。
- BFF 对上游错误使用统一错误模型。
- `frontend_bff` 与 `web_app_service` 做生产边界裁决，只保留一个生产 BFF。

## 6. 子阶段方案

| 子阶段 | 核心目标 | 验收门禁 | 回滚 |
|---|---|---|---|
| SVC.phase0 | 调用链与脚本清单冻结 | 生成调用矩阵 + direct SQL inventory | 不改生产逻辑 |
| SVC.phase1 | CollectionJobManager 服务化 | 前端采集功能通过，任务状态可恢复 | 保留旧脚本 wrapper |
| SVC.phase2 | Layer C old-chain dry-run 真源 | 四路 diff 报告生成，A/D 对齐 | production 继续 legacy watch pool |
| SVC.phase3 | W2S/StrongWatch 服务迁移 | old/new replay matrix 通过 | 回退旧脚本 CLI |
| SVC.phase4 | API/BFF 边界清理 | 禁止 `stock_processing_service -> stock_service` 依赖 | 保留临时 adapter |

## 7. ADR 建议清单

- ADR-SVC-001：脚本只能作为 CLI wrapper，业务逻辑必须进入 Application Service。
- ADR-SVC-002：`stock_processing_service` 禁止直接 SQL，SQL 只能经 `database_service` Gateway。
- ADR-SVC-003：采集任务由 `CollectionOrchestrator` 管理，不允许 API 进程直接拼业务脚本命令。
- ADR-SVC-004：Layer C 迁移以旧链程序 dry-run 为真源，不能以旧表内容替代旧链逻辑。
- ADR-SVC-005：前端生产链只允许一个 BFF 真源。

## 8. 冲突裁决记录

| 冲突 | 裁决 | 理由 |
|---|---|---|
| “旧链表读口”是否等价旧链 Layer C 输出 | 不等价，必须跑旧链程序 dry-run | 表可能被新链/历史快照污染，程序输出才是复刻真源 |
| 新 C 层是否继续作为生产入口 | 暂不应作为生产入口 | 现有代码显示仍有 `seed_query` 主路径，且旧链入口未闭环验证 |
| 旧脚本迁移是重写还是封装 | 先原样抽服务，再重构 | 当前优先级是复刻与可回放，不能先改算法 |

## 9. 非目标范围

- 不在本轮调整联德/维科/神剑策略阈值。
- 不把旧 SQL 直接复制到 `stock_processing_service`。
- 不让前端直接调用脚本或数据库。
- 不在旧链 dry-run 未完成前宣称 Layer C 已复刻完成。

---

# ARCH REVIEW - P3.phase2 日采集控制面与盘后复盘快照核查（2026-05-21）

## 1. 当前架构摘要（Current Architecture Summary）

本次核查对照 `docs/architecture/个人投资助理-项目架构设计-第三阶段.md` 与 2026-05-21 盘后复盘现状，范围锁定：

- `/collection` 日采集控制台
- `BuildPostMarketRecapJob`
- `post_market_recap_snapshot`
- 盘后页四个空区块：`主线与支线`、`强势股分层`、`次日观察清单`、`主线股票资金流入前20`

设计文档已经冻结了两个关键边界：

1. 盘后页面、BFF、Notion 一律读取 `post_market_recap_snapshot`，不得直读 `weak_to_strong_candidate_pool`。
2. `BuildPostMarketRecapJob` 的职责包括“驱动 D1 候选构建”，再汇总强势池、异动、排行榜与候选证据生成最终快照。

当前代码只完成了第 1 条，违背了第 2 条：

- 前端复盘页确实只读 `/api/v2/post_market_snapshot` 并解析快照内 `report.sections`。
- `BuildPostMarketRecapJob` 当前先构建 Layer C，再把 D1 处理改成“读取既有 `weak_to_strong_candidate_pool`”，没有调用已注入的 `BuildWeakToStrongCandidateUseCase`。
- 前端 `/collection` 控制台仍经 `frontend_bff` 的内存 `CollectionJobManager` 拉起旧脚本；同时 `stock_processing_service` 又提供了新链 `CollectionJobManager + CollectionCommandPlanner + Runner Registry`。这不是兼容别名，而是两套会生产复盘结果的控制面。

## 2. 风险矩阵（Risk Matrix）

| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | Trigger | 缓解措施 | Owner |
|---|---|---|---|---|---|---|---|---|
| R-P3-PM-001 | P0 | D1 未由盘后 job 构建，空候选仍发布成功快照 | 盘后四个核心区块、Notion 复盘 | 高 | 中 | 当日 `weak_to_strong_candidate_pool` 未提前生成 | 恢复 `BuildPostMarketRecapJob -> BuildWeakToStrongCandidateUseCase` 职责，空产出门禁化 | SPS |
| R-P3-PM-002 | P0 | `/collection` 存在 BFF 旧脚本控制面与 SPS 新链控制面双写语义 | 日采集、回补、故障定位 | 高 | 中 | 前端继续命中 BFF `/api/v2/collection/*` | 前端/BFF 只代理 SPS collection API，删除 BFF 业务编排器 | FE/BFF/SPS |
| R-P3-PM-003 | P1 | 快照依赖状态只检查 A/B/C 命中，不检查 D1 非空或 D1 执行状态 | 快照质量门禁 | 高 | 中 | A/B/C 正常而 D1 空 | 快照 metadata 增加 D1 build status、candidate coverage、degraded reason | SPS/QA |
| R-P3-PM-004 | P1 | `money_flow_enhanced` 在新链 planner 中仍由 `script.default` 运行脚本 | 资金增强与控制面收口 | 中 | 低 | 保留脚本 runner 生产路径 | 抽成 SPS runner/job，经 Port/Gateway 写读 | SPS/Data |

## 3. 维度化发现

### 3.1 现象与证据

2026-05-21 的 `post_market_recap_snapshot` 已经落库，`snapshot_version=collection.post_market_recap.v1`，且快照中存在 12 个 section。但四个页面空区块在快照里已经是占位文本，不是前端渲染丢失：

| section | 快照首项 |
|---|---|
| `主线与支线` | `暂无主线候选` |
| `强势股分层` | `暂无强势股候选` |
| `次日观察清单` | `暂无次日观察候选` |
| `主线股票资金流入前20` | `暂无主线股票资金数据` |

同一快照的关键计数为：

- `candidate_count=0`
- `candidate_count_formal=0`
- `candidate_count_observe=0`
- `top_candidates` 数组长度为 0
- `strong_watch_input_7d_count=2640`
- `strong_watch_pool_written=87`
- `report_context.stock_facts=132`
- `report_context.theme_capital_flow=8`

因此故障断点不是“JYHF/Tushare 全部没数据”，也不是前端 section 名称错误，而是“盘后快照依赖的 D1 候选列表为空，builder 把空候选转换成了 `暂无...` 并正常发布”。

### 3.2 契约与一致性

第三阶段文档对 D1 与复盘的定义是：

- D1 只能读取 Strong Watch refresh 后结果。
- 候选池保留为回放、详情证据、D2 输入，不允许页面直读。
- `BuildPostMarketRecapJob` 驱动 D1 候选构建，然后生成 `post_market_recap_snapshot`。

当前实现的实际语义是：

- `BuildPostMarketRecapJob` 驱动 A/B 前置与 Layer C。
- D1 阶段只调用 `get_w2s_candidate_inputs()` 与 `get_w2s_candidates_by_trade_date()`。
- `weak_to_strong_candidate_use_case` 虽然注入到 job，但未被执行。

结果是：复盘 job 从“拥有 D1 生产职责”退化成了“假设 D1 已由别处先生产”。一旦日采集控制台没有先跑 D1，或当日候选池没有落库，复盘快照仍会成功但核心 section 为空。

### 3.3 控制面分叉

当前 `/collection` 不是 SPS 新链控制台：

- 前端请求 `/api/v2/collection/*`。
- `frontend_bff` 直接持有自己的 `collection_job_manager`。
- BFF 的 `recap_snapshot` 任务直接执行 `scripts/build_post_market_recap.py`。

与此同时，SPS 另有：

- `/api/v1/collection/*`
- `stock_processing_service/application/jobs/collection_job_manager.py`
- `CollectionCommandPlanner`
- Runner Registry 与 `recap.snapshot` 新链 runner

这两套机制的任务名称相似，但业务含义不同，无法作为长期兼容层共存。继续保留会导致：

1. 前端看到的“采集成功”不等于新链快照依赖已准备。
2. 旧脚本复盘与 SPS 新链复盘都可能写 `post_market_recap_snapshot`。
3. 故障定位时无法先判断结果由哪条链生产。

### 3.4 可观测性与门禁

当前新链 report builder 的 dependency status 只关注 A/B/C 是否命中。2026-05-21 A/B/C 命中后 `missing_new_chain_dependencies=[]`，但 D1 候选仍为 0。这个 metadata 会误导控制台和页面把“核心内容缺失”解释成“新链依赖完整”。

## 4. 目标架构（Target Architecture）

日采集与盘后复盘只保留 SPS 新链单控制面：

```text
frontend /collection
  -> frontend_bff collection proxy only
  -> SPS /api/v1/collection/*
  -> SPS CollectionJobManager
  -> Runner / Job / UseCase
  -> frozen object: post_market_recap_snapshot
  -> frontend /recap, Notion publisher
```

`BuildPostMarketRecapJob` 必须恢复文档职责：

```text
recap prerequisites
  -> Layer A identity
  -> Layer B cycle
  -> Layer C strong watch
  -> Layer D1 weak-to-strong candidate build
  -> report context assembly
  -> post_market_recap_snapshot quality gate
```

目标控制台不是“勾选一批脚本”，而是“观察 SPS 日采集 contract 的执行与质量”：

- 只展示一套 job id、step graph、runner/job、输入覆盖、输出对象、失败原因。
- 对每个交易日显示冻结对象状态：`stock_daily_snapshot`、`subject_stock_daily_snapshot`、`stock_abnormal_event`、`theme_stock_leaderboard`、`post_market_recap_snapshot`。
- 对复盘显示 A/B/C/D 质量摘要：identity hits、cycle hits、strong watch rows、D1 candidate rows、report sections degraded reason。
- 明确区分 `failed`、`degraded`、`success`，不得把核心 section 空占位当作纯成功。

## 5. 迁移计划（Migration Plan）

1. P0：让前端 `/api/v2/collection/*` 改成 BFF 代理 SPS collection API；删除 BFF 旧 `CollectionJobManager` 生产入口与旧脚本 `recap_snapshot` 调用。
2. P0：让 `BuildPostMarketRecapJob` 在 Layer C 后显式执行 `BuildWeakToStrongCandidateUseCase`，再读取 D1 结果写快照。
3. P0：为 2026-05-21 这类空 D1 场景增加质量门禁：当 Strong Watch/主线资金上下文存在而核心 D1 section 为空时，快照必须标记 degraded 或失败，禁止 silent success。
4. P1：把 `money_flow_enhanced` 从 `script.default` 抽为 SPS runner/job，清理新链 planner 内剩余脚本生产路径。
5. P1：补一条端到端验收：`/collection` 启动 -> SPS job -> D1 candidate build -> `post_market_recap_snapshot` -> `/recap` 四个区块非占位或返回明确 degraded reason。

## 6. 子阶段方案

| 子阶段 | 核心目标 | 验收门禁 | 回滚 |
|---|---|---|---|
| P3.pm0 | 控制面单一化 | 前端 collection 只代理 SPS；BFF 不再执行 recap 脚本 | 临时关闭前端启动入口，仅保留 SPS API |
| P3.pm1 | 复盘 job 恢复 D1 所有权 | `BuildPostMarketRecapJob` 单测断言 D1 use case 被执行 | 回滚到上一 snapshot_version，不恢复旧脚本 |
| P3.pm2 | 快照质量门禁 | 空 D1/空 section 输出 degraded/fail，2026-05-21 回归覆盖 | 控制台显示 degraded，页面继续只读快照 |
| P3.pm3 | 新链脚本残留清理 | planner 不再以 `script.default` 执行资金增强 | 保留同一 SPS runner 的降级路径 |

## 7. ADR 建议清单

- ADR-P3-PM-001：日采集控制面只允许 SPS 新链单真源。
- ADR-P3-PM-002：`BuildPostMarketRecapJob` 必须拥有 D1 构建职责。
- ADR-P3-PM-003：盘后快照必须声明质量状态，核心 section 空产出不可 silent success。

## 8. 冲突裁决记录

| 冲突 | 裁决 | 理由 |
|---|---|---|
| 文档定义 `BuildPostMarketRecapJob` 驱动 D1，但代码只读 D1 | 以第三阶段设计文档为准，恢复 job 所有权 | 页面不能依赖隐式前置调用 |
| BFF 旧脚本 collection 与 SPS 新链 collection 是否共存 | 不共存，前端只允许命中 SPS | 两套生产控制面会破坏可追溯性 |
| 快照空候选是否算成功 | 不允许无状态成功 | 用户看到的是核心复盘空白，必须显式暴露质量退化 |

## 9. 非目标范围（Non-Goals）

- 不恢复前端直读过程表或候选池。
- 不用旧脚本作为新链的长期 fallback。
- 不把 2026-05-21 的空候选直接解释为策略上“当天没有机会”，在 D1 build ownership 与质量门禁恢复前只能判定为链路质量问题。

## 10. 复核修正：复盘与 D1 的职责裁决（2026-05-21）

用户复核后明确业务边界：

1. 每日盘后复盘负责生成复盘与选股所需的日频事实、主线、周期、强势股、资金、异动等数据准备。
2. D1 候选池应在“弱转强”盘后选股阶段按策略筛选生成，而不是在复盘页面/复盘 report builder 内隐式生成。
3. 旧链的复盘 section 组装口径应作为对照：复盘 section 不应被 D1 候选池是否为空整体卡死。

基于二次核查，前述第 1、3、5、8 节中“恢复 `BuildPostMarketRecapJob` 对 D1 构建 ownership”不再作为本次最终裁决，改由以下结论覆盖。

### 10.1 设计文档冲突

第三阶段主文档存在冲突表述：

- `13.3.4` 与 `15.3.3` 将 D1 对外落点、`BuildPostMarketRecapJob` 描述为与 `post_market_recap_snapshot` 强绑定。
- 弱转强两阶段设计与当前 SPS screener API 则把 D1 视为弱转强 Stage1 执行产物：
  - `api_app._run_w2s_candidate_selection_for_screener()` 显式执行 `build_weak_to_strong_candidate`；
  - `StockScreener` 弱转强两阶段页面把 Stage1 作为盘后选股过程。

裁决：以本次业务澄清为准，修订第三阶段主文档中“recap job 驱动 D1”的歧义描述。盘后复盘可为 D1 提供输入事实，不拥有 D1 候选池生成职责。D1 Stage1 结果先落盘到 `weak_to_strong_candidate_pool`；是否再回填为复盘快照的附加投影，由装配契约决定，不能把 `post_market_recap_snapshot` 写成 D1 固定归宿。

### 10.2 旧链与新链 section 依赖对照

旧 `RecapService` 的 section 来源不是 D1 候选池：

| section | 旧链主要来源 |
|---|---|
| `主线与支线` | 主线状态、周期、题材资金、题材 K 线 |
| `强势股分层` | `theme_leader_candidate`、LLM 角色裁决、K 线与资金增强 |
| `次日观察清单` | 龙头候选、主线存活、异动、龙虎榜、量价形态 |
| `主线股票资金流入前20` | 股票资金流入 top 事实 |

当前新链 `NewChainPostMarketReportBuilder` 把上述四段统一改为基于 `top_candidates or formal_candidates`。这些字段来自 D1 候选投影，D1 为空时四段一起降级为 `暂无...`。

这就是 2026-05-21 的直接根因：

```text
复盘事实存在
-> D1 候选为空
-> 新链 report builder 仍用 D1 候选驱动主线/强势股/观察/资金 section
-> 四段同时空白
```

### 10.3 修正后的 P0

| ID | P0 事项 | 正确动作 |
|---|---|---|
| P0-A | 日采集双控制面 | 前端/BFF 只代理 SPS collection，删除 BFF 旧脚本生产编排 |
| P0-B | 复盘 section 错绑 D1 | `NewChainPostMarketReportBuilder` 改回复盘事实驱动：主线/leader/资金/异动/强势股对象，不以 D1 候选为空作为四段空白条件 |
| P0-C | 文档职责歧义 | 修订第三阶段文档：Recap 数据准备与 W2S Stage1 D1 选股职责分离 |
| P0-D | 快照质量门禁 | 复盘 section 缺复盘事实时 fail/degraded；D1 为空只能影响弱转强选股 section，不得清空主线与强势股复盘 |

### 10.4 保留的裁决

- 旧链生产入口仍必须剥离。
- `post_market_recap_snapshot` 仍是 `/recap` 与 Notion 的唯一对外真源。
- D1 候选池仍不得被 `/recap` 页面直接读取。
- 弱转强选股可以消费复盘准备好的冻结对象/日频事实，再由 Stage1 显式生成 D1。

---

# ARCH REVIEW - SSE 实时推送稳定性专项评审（2026-07-02）

## 1. 当前架构摘要（Current Architecture Summary）

- 当前前端开发入口由 `frontend/vite.config.ts` 将 `/api/v2/*` 代理到 `web_app_service:8000`，新链启动脚本也以 `web_app_service` 为生产 BFF。
- 2026-07-01 的提交 `c54d28dd5` 删除了基于 HTTP 轮询的 `/api/v2/intel/stream`，保留 `/api/v2/intel/stream/realtime`，该端点直接对 `stream:event:feed` 与 `stream:jyhf:feed` 执行 `XREAD`。
- 前端当前工作区改动已把 `SSEManager` 默认端点切到 `/api/v2/intel/stream/realtime`，但前端仍按 `IntelFeedEvent` 契约校验消息。
- `frontend_bff:8003` 仍保留另一套 `SSEPushService + Redis consumer group + process-local queue broadcast` 实现，运行手册仍引用该入口，形成双 BFF、双 SSE 实现和双运维口径。
- 结论：从 HTTP 轮询切换到 Redis Stream 实时读取的方向合理，但当前实现尚未形成稳定的事件适配、断点恢复和单一生产入口，现状不满足“无永久数据缺口”和稳定实时推送要求。

## 2. 风险矩阵（Risk Matrix）

| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | Trigger | 缓解措施 | Owner |
|---|---|---|---|---|---|---|---|---|
| R-SSE-001 | P0 | realtime 端点输出 `{stream,message_id,data}`，前端要求 `{event_id,occurred_at,event_type,item}`；心跳正常但业务事件被前端静默丢弃 | `/intel` 实时情报主链 | 高 | 高 | 任一 Redis Stream 新消息到达 | 服务端增加 source adapter，统一输出 `IntelFeedEvent v1`；发送前执行 schema 校验 | Web App/FE |
| R-SSE-002 | P0 | 每次连接都从 `"$"` 开始，未输出 SSE `id:`，也未处理 `Last-Event-ID`；断线窗口内消息永久跳过 | 所有断线、页面休眠和网络切换场景 | 高 | 中 | SSE 重连、浏览器后台恢复 | 支持 cursor/`Last-Event-ID` replay；REST feed 增加显式 `after_cursor` 回补 | Web App/Data |
| R-SSE-003 | P0 | canonical 路由、测试、指标脚本和运行手册仍指向 `/api/v2/intel/stream`，实际新链只保留 `/realtime`；缺失路由被 SPA fallback 返回 200 HTML | 发布门禁、监控、前端建连 | 高 | 中 | 新链启动或监控探测旧路由 | 恢复单一 canonical `/api/v2/intel/stream`，`/realtime` 仅做临时别名；非 API 路由禁止 SPA 200 fallback | Web App/Release |
| R-SSE-004 | P1 | `SSEManager.connect()` 每次重连把 `retryCount` 清零，最大 3 次重试实际上不会收敛到稳定 fallback | 前端降级与资源占用 | 高 | 中 | 网络持续异常 | 仅首次连接清零；重连成功并稳定一段时间后再清零；增加 jitter | FE |
| R-SSE-005 | P1 | 旧 BFF 与 stream services 可用同一 `sse_pushers` consumer group 竞争消费；无客户端实例也会 ACK，若重新启用会造成随机丢事件 | 旧实时栈、多 worker 部署 | 中 | 高 | 同时启动 BFF SSEPushService 与 stream `sse_pusher` | 禁止 consumer group 直接承担客户端广播；删除/禁用旧 pusher，或建设独立集中 fanout 服务 | Platform/BFF |
| R-SSE-006 | P1 | 旧 BFF 广播队列 `put()` 串行等待，单个慢客户端可阻塞消费与 ACK；连接又按创建时间在 300 秒后无条件清理 | 旧 BFF SSE 稳定性 | 中 | 高 | 慢连接、连接超过 5 分钟 | 有界非阻塞队列、单客户端丢弃/断开策略；按最后发送时间清理，不按连接年龄清理 | BFF |
| R-SSE-007 | P1 | realtime 路由忽略 `date/type/session/subject_key/stock_id`，两条源流格式也不同；跨流事件没有统一排序规则 | 筛选准确性与展示顺序 | 高 | 中 | 多源同时产生消息 | 服务端统一映射、过滤和排序字段；建立 canonical intel stream | Web App/Domain |
| R-SSE-008 | P2 | 现有指标只覆盖连接状态，缺少接收、适配失败、丢弃、重放、队列水位和端到端延迟 | 故障发现与定位 | 高 | 高 | 业务消息停止但心跳仍正常 | 增加结构化指标和 trace 字段，区分 transport alive 与 business flow alive | SRE/QA |

## 3. 维度化发现

### 3.1 契约与一致性

- `stream:event:feed` 当前消息是扁平字段，常见主键为 `event_id`；`stream:jyhf:feed` 当前消息把业务对象放在 JSON 字符串字段 `payload` 中。
- `web_app_service` 未对两种源格式做适配，直接包装为 `{stream,message_id,data}`。
- `frontend/src/lib/realtime/sseManager.ts` 的 `isValidIntelEvent()` 强制要求顶层 `event_id/occurred_at/event_type/item` 和 `item.item_id/item_type/occurred_at`，因此当前 realtime 业务事件无法通过校验。
- `_validate_sse_payload()` 已存在，但 realtime 路径没有调用，契约测试只验证静态辅助函数，没有覆盖 Redis 消息到 SSE 输出的真实转换。

### 3.2 一致性与恢复

- `XREAD` 用于广播读取是合理的，因为每个客户端都应收到事件，不能使用同一 consumer group 做负载均衡。
- 当前起点固定为 `"$"`，只保证“连接后新事件”，不保证断线恢复。
- 前端 fallback 仅在连接错误时启动；如果心跳仍存在而业务事件适配失败，fallback 不会触发。
- 现有 REST 回补按最新列表去重，不带服务端 cursor，无法证明一定覆盖断线窗口。

### 3.3 性能与容量

- 当前每个 SSE 客户端持有一个 Redis 连接并对两个 Stream 执行阻塞 `XREAD`。小规模单机可接受，但需要连接上限和容量基线。
- 推荐先保持单进程直读，不立即引入重型消息基础设施；连接数达到 Redis 池或 BFF worker 容量阈值后，再迁移到集中 fanout。
- 两源直接合并缺少全局顺序。中期应归一到 `stream:intel:feed`，以单一 Redis ID 提供顺序和恢复游标。

### 3.4 可观测性

至少需要以下指标：

- `sse_active_connections`
- `sse_connect_total{result}`
- `sse_business_event_received_total{source}`
- `sse_event_adapt_failed_total{source,reason}`
- `sse_event_sent_total{event_type}`
- `sse_replay_total`、`sse_replay_gap_total`
- `sse_last_business_event_age_seconds`
- `sse_end_to_end_latency_ms`
- `sse_client_drop_total{reason}`

心跳成功只能说明传输连接存活，不能作为业务流健康证据。

### 3.5 可运维性与测试证据

- 当前运行态只检测到 `web_app_service:8000`，未检测到 `frontend_bff:8003`；Vite 也固定代理到 8000，说明新链实际入口是 web_app。
- Redis 当前 `stream:event:feed` 和 `stream:jyhf:feed` 均有数据，但不存在 `sse_pushers` group，进一步证明当前运行路径是直接 `XREAD`，不是 BFF 广播服务。
- 定向测试命令：
  - `.venv/bin/python -m pytest -q web_app_service/tests/test_p4_phase0_contracts.py -k 'intel_stream or sse_payload'`
  - 结果：`1 failed, 4 passed`。
  - 失败原因：`/api/v2/intel/stream` 被 SPA fallback 返回 `200 text/html`，而不是 `text/event-stream`。

## 4. 目标架构（Target Architecture）

```text
stream:event:feed -----\
                        -> IntelEventAdapter -> stream:intel:feed
stream:jyhf:feed ------/

stream:intel:feed
  -> GET /api/v2/intel/stream
     - event: intel_item
     - id: <redis-stream-id>
     - data: IntelFeedEvent v1
     - heartbeat
     - Last-Event-ID replay

GET /api/v2/intel/feed?after_cursor=<id>
  -> 断线窗口显式回补

frontend SSEManager
  -> 连接/重连
  -> schema 校验
  -> cursor 持久化
  -> 超过重试阈值后 REST fallback
  -> 重连后先 replay，再退出 fallback
```

核心约束：

1. 生产 BFF 只保留 `web_app_service`，落实既有 `ADR-SVC-005`。
2. canonical SSE 路由固定为 `/api/v2/intel/stream`；`/realtime` 只作为迁移期别名。
3. SSE 出口只消费 canonical `stream:intel:feed`，不得把多个源流原始字段直接暴露给前端。
4. 每个客户端读取同一广播 Stream，使用 `XREAD` 和独立 cursor；不得共享 consumer group 分流。
5. 实时链故障不影响日频快照链，REST feed 始终可独立工作。

## 5. 迁移计划（Migration Plan）

1. P0：恢复 `/api/v2/intel/stream` canonical 路由，并让 `/realtime` 临时复用同一 handler；API 未命中必须返回 404，不得落到 SPA HTML。
2. P0：实现 `event_feed_adapter` 与 `jyhf_feed_adapter`，统一产出 `IntelFeedEvent v1`；发送前调用 schema 校验，失败只计数和告警，不发送畸形事件。
3. P0：补端到端契约测试，覆盖两种真实 Redis entry 格式，断言前端必需字段完整。
4. P0：修复前端 retry counter；把“收到 heartbeat”和“收到有效业务事件”拆成两个健康状态。
5. P1：增加 SSE `id:`、`Last-Event-ID` 和 REST `after_cursor`；完成断线 30 秒、浏览器休眠和 Redis 短断恢复测试。
6. P1：建立 canonical `stream:intel:feed`，统一双源排序、去重、保留策略与 cursor。
7. P1：删除或默认禁用 `frontend_bff` 旧 `SSEPushService` 和 stream services 中无客户端的 `sse_pusher`，避免未来误启竞争消费。
8. P2：补连接容量、慢客户端、10 分钟 soak、双客户端同消息一致性和端到端 P95 延迟门禁。

## 6. 子阶段方案

本次采用 `scope=system`，不强制拆分 phase 子阶段。建议执行顺序为 `P0 契约收口 -> P1 恢复语义 -> P2 容量与可观测性`。

## 7. ADR 建议清单

- ADR-SSE-001：冻结单一 SSE 路由与 `IntelFeedEvent v1`。
- ADR-SSE-002：SSE 必须提供 cursor replay，并由 REST 提供显式 gap fill。
- ADR-SSE-003：广播投递禁止使用共享 consumer group，统一到 canonical intel stream。
- ADR-SSE-004：慢客户端与连接存活采用隔离背压和业务流健康指标。

## 8. 冲突裁决记录

| 冲突 | 采用来源 | 放弃/后置来源 | 裁决理由 |
|---|---|---|---|
| PRD 指定 `/api/v2/intel/stream`，代码只保留 `/realtime` | PRD/P4 契约与现有测试 | 长期保留双路由语义 | 对外契约必须稳定，`/realtime` 可临时别名但不能成为第二套实现 |
| 新链使用 web_app，运行手册仍要求 frontend_bff | 新链启动脚本、Vite proxy、当前运行态 | frontend_bff 作为生产 SSE 入口 | 双 BFF 已导致路由和事件 DTO 漂移 |
| 直接 XREAD 与 consumer group 广播 | 每客户端独立 XREAD canonical stream | 共享 `sse_pushers` group 直接广播 | consumer group 是任务分发语义，不满足每个客户端都收到每条事件 |
| 是否恢复 HTTP 轮询 SSE | 保留 Stream 实时 SSE + REST gap fill | 恢复 5 秒 HTTP 轮询作为主实现 | 轮询不应重新成为实时主链，但 REST 必须保留为可靠回补通道 |

## 9. 非目标范围（Non-Goals）

- 不恢复 5 秒 HTTP 轮询作为 SSE 主实现。
- 不引入 WebSocket Hub、Kafka 或事件溯源平台。
- 不在本轮改造日频快照、盘前必读和盘后复盘链路。
- 不承诺 Tick 级或高频行情分发。

---

# ARCH REVIEW - Notion 盘后报告内容输出专项评审（2026-07-03）

## 1. 当前架构摘要（Current Architecture Summary）

- 发布链路只读 `post_market_recap_snapshot`，由 `EngineReportAdapter` 同时适配 `recap_doc` 与 `daily_review_v2`。
- 发布器当前连续执行“新版复盘故事”“Engine Report”“2026-05 旧候选模板”三套渲染逻辑，页面结构没有单一内容契约。
- 旧候选模板无条件创建“弱转强候选、正式候选、观察候选、强势池历史、候选诊断、旧链报告”栏目；DailyReview V2 不保证这些旧字段存在，因此稳定产生空栏目。
- `_build_engine_sections` 被重复 `@classmethod` 装饰，且调用异常被 `except Exception: pass` 吞掉，导致交易结论、大盘环境、主线状态、次日观察整组静默缺失。
- 2026-07-02 快照包含 Engine Summary、34 条主线状态及 6 条指数技术数据，但现行渲染仍出现 63 个区块和多组空栏目，证明问题位于内容编排层而非单纯“源数据为空”。

## 2. 风险矩阵（Risk Matrix）

| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | Trigger | 缓解措施 | Owner |
|---|---|---|---|---|---|---|---|---|
| R-NOTION-001 | P0 | 重复装饰器触发类型错误，异常又被静默吞掉，核心决策栏目不发布 | 所有包含 Engine Report 的盘后页面 | 高 | 高 | 调用 `_build_engine_sections` | 移除重复装饰器；禁止渲染主链 `except: pass`；增加契约测试 | SPS |
| R-NOTION-002 | P1 | 三套模板并行、旧字段栏目无条件追加，产生重复与空栏目 | Notion 页面可读性及决策效率 | 高 | 低 | 任一 V2 快照发布 | 冻结单一 V2 内容编排器；按有效内容渲染 | SPS/Product |
| R-NOTION-003 | P1 | 空字段被默认值包装成“暂无数据”业务结论，无法区分正常无事件与上游缺失 | 数据质量判断 | 高 | 高 | 模块数组为空或 join 失败 | 将缺口集中到数据质量区，使用 module_coverage 状态 | SPS/Data |
| R-NOTION-004 | P1 | Publisher 同时承担 API、幂等、内容选择、字段格式化和 legacy 解析 | 可维护性与回归风险 | 高 | 中 | 增加任一新栏目 | Publisher 保留发布编排；独立 renderer 负责内容契约 | SPS |
| R-NOTION-005 | P2 | 旧链文本反解析继续参与主题名与主体展示 | 真源一致性 | 中 | 中 | V2 字段缺失 | 主体只读 V2/Engine；legacy 仅在显式兼容模式展示 | SPS |

## 3. 维度化发现

### 3.1 契约与一致性

- `PostMarketDailyReviewV2` 已定义页面级结构化模块与 `diagnostics.module_coverage`，应成为 Notion 主体真源。
- 现行 Publisher 仍以 2026-05 候选字段为固定目录，违反 V2 “每个模块直接对应一个展示模块”的约束。
- 正常“无龙虎榜/无候选”和异常“上游未产出”必须通过 coverage/status 区分，不能都展开为空栏目。

### 3.2 内容架构

目标页面按投资决策阅读顺序收敛为四层：

1. 交易结论：是否交易、模式、仓位、阻断原因、次日策略。
2. 市场结构：市场环境、复盘要点、涨停梯队、主线状态、新高趋势。
3. 资金验证：机构、游资、龙虎榜及主题资金，只展示存在的结构化事实。
4. 次日计划：D1/观察清单/重点股票；无计划时仅在交易结论中说明，不创建多张空表。

数据缺口统一放入末尾折叠的“数据质量”区，不与业务内容混排。

### 3.3 可观测性

- 渲染异常必须带 section 名称记录并中止发布，避免成功页面残缺。
- 建议记录 `rendered_sections/skipped_sections/partial_sections/block_count/schema_version`。
- 页面本身只展示需要人工关注的 partial/failed 模块，不展示全量内部 diagnostics。

### 3.4 性能与可运维性

- 条件渲染会减少无意义 block 数量和 Notion append 请求体积。
- 每个表继续保留行数上限；详细诊断使用 toggle，避免正文超过 Notion block 限制。
- 幂等归档重建策略、本地 snapshot 真源和盘前报告渲染保持不变。

## 4. 目标架构（Target Architecture）

```text
post_market_recap_snapshot
  -> EngineReportAdapter / DailyReviewV2
  -> PostMarketNotionReportRenderer
       -> SectionSpec(content predicate + renderer)
       -> 交易结论
       -> 市场结构
       -> 资金验证
       -> 次日计划
       -> 数据质量
  -> NotionPostMarketRecapPublisher
       -> 幂等查询/建页/分批 append
```

硬约束：

1. 主体只消费结构化 V2/Engine 字段，不从 legacy 文本反解析业务语义。
2. 业务栏目仅在包含有效内容时渲染；禁止为每个空数组创建“暂无数据”栏目。
3. 核心渲染异常不得静默降级。
4. legacy 内容默认不发布，仅保留显式兼容开关的迁移能力。
5. 数据缺口通过 `diagnostics.module_coverage` 集中表达。

## 5. 迁移计划（Migration Plan）

1. 先补发布内容契约测试，覆盖空快照、Engine 数据、V2 模块和 partial diagnostics。
2. 修复重复 `@classmethod` 和 `position_limit=None` 等确定性渲染故障。
3. 将旧模板替换为按内容谓词驱动的 V2 编排器，默认关闭 legacy。
4. 保持发布 API、幂等键、数据库 properties 和盘前报告路径不变。
5. 使用 2026-07-02 实际快照回放，核对标题顺序、空栏目数和 block 数。
6. 若需回滚，仅恢复旧 `build_blocks`；snapshot 和 Notion database schema 无需回滚。

## 6. 子阶段方案

本次采用 `scope=system` 专项评审，不新增跨系统阶段。实施按“测试保护 → renderer 收口 → 快照回放”顺序执行。

## 7. ADR 建议清单

- ADR-NOTION-001：Notion 主体以 DailyReview V2/Engine 为唯一内容契约。
- ADR-NOTION-002：采用有效内容驱动的条件渲染，空态集中到数据质量区。
- ADR-NOTION-003：核心渲染异常 fail-fast，禁止静默残缺发布。
- ADR-NOTION-004：Publisher 与报告 Renderer 职责分离。

## 8. 冲突裁决记录

| 冲突 | 采用来源 | 放弃来源 | 裁决理由 |
|---|---|---|---|
| 2026-05 Notion 固定七栏模板 vs DailyReview V2 页面级契约 | DailyReview V2 重构设计与当前快照 | 固定七栏旧候选模板 | V2 是当前结构化真源，旧字段不再保证存在 |
| “每栏显示暂无数据” vs 减少空栏目 | coverage 驱动的集中数据质量区 | 业务正文逐栏空态 | 集中表达才能区分正常无事件和上游故障 |
| 渲染失败继续发布 vs 中止残缺页面 | fail-fast + 测试 | `except Exception: pass` | 残缺页面比明确失败更难发现且会误导决策 |

## 9. 非目标范围（Non-Goals）

- 不修改 DailyReview V2 上游计算规则。
- 不重新生成或回填历史 snapshot。
- 不调整 Notion database properties、幂等键或归档策略。
- 不改盘前必读报告内容。

---

# ARCH REVIEW - M8 Prediction Semantics Boundary 专项评审（2026-07-04）

## 1. 当前架构摘要（Current Architecture Summary）

- Phase 0 已证明 Evidence、Context、Cognition、Thesis、Replay 和 Decision 隔离在工程上可重复。
- Phase 1 Pilot 首次验证认知输出是否具备可校准语义，而不仅是输出能否生成。
- 真实回放显示 Primary Thesis 主要表达当日 Observation/Assessment；其 confidence 实际是 Evidence Quality。
- Dataset Writer 已具备 append-only、冲突拒绝和 Manifest Integrity，但语义不合格的输入不能因存储能力可用而进入 Ground Truth Dataset。

## 2. 风险矩阵（Risk Matrix）

| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | 缓解措施 | Trigger | Owner |
|---|---|---|---|---|---|---|---|---|
| R-M8-SEM-001 | P0 | 将当日 Narrative 当作未来 Prediction | Validation Dataset、Calibration、Learning | 高 | 高 | 三类词汇边界 + Eligibility Gate | 写首条 Validation Record | M8 Owner |
| R-M8-SEM-002 | P0 | 将 Evidence Quality 当作 Prediction Probability | Brier、ECE、Belief 更新 | 高 | 高 | 字段独立命名与存储，禁止互相复制 | 计算 Calibration | M8/QA |
| R-M8-SEM-003 | P1 | Reviewer 事后补概率形成 hindsight bias | Ground Truth 可审计性 | 中 | 高 | probability 必须随昨日 Hypothesis 冻结 | Reviewer 提交 Verdict | QA/Risk |
| R-M8-SEM-004 | P1 | 为 Eligibility Reject 扩充 Failure Type | 标注一致性、长期可维护性 | 中 | 中 | 写入前拒绝；六种一级分类保持冻结 | 命题字段不完整 | Dataset Owner |

## 3. 维度化发现

### 3.1 契约

- `Observation` 回答“已经发生了什么”。
- `Assessment` 回答“当前应如何理解/约束行动”。
- `Hypothesis` 回答“在截止时点前，未来最可能发生什么，以及什么证据可证实或证伪”。
- 三者可共同组成 Market Thesis，但 Validation Consumer 只能读取 Hypothesis。

### 3.2 一致性

- `quality_score` 与 `prediction_probability` 不是同一量纲。前者衡量输入和推理链可靠性，后者是事前事件概率。
- `ARCH-P07` 约束质量传播，但不能把 Quality 数值直接复制为事件概率。
- Dataset Record 必须引用冻结版本，禁止用新版本 policy 重跑昨日数据后改写昨日 Hypothesis。

### 3.3 可解释性

- Eligible Hypothesis 必须同时展示 statement、deadline、expected observations、falsifiers、prediction probability 和 EvidenceRefs。
- Reviewer 只裁决 Outcome/Label/Reason，不得修改昨日 probability。

### 3.4 可运维性

- Eligibility Reject 是写入前门禁，不是 NO、PARTIAL 或 UNVERIFIABLE。
- 建议记录 `eligible_count/rejected_count/reject_reason/reviewer_disagreement_rate`，但 Reject 不进入 Calibration 分母。

## 4. 目标架构（Target Architecture）

```text
Frozen Market Thesis
  ├─ Observation ----------------------> Narrative / Notion
  ├─ Assessment -----------------------> Narrative / Notion
  └─ Hypothesis
       -> Eligibility Gate
          deadline
          prediction_probability
          expected_observations
          falsifiers
          evidence_refs + lineage
          source_quality != BLOCKED
       -> Explicit Reviewer Verdict
       -> Ground Truth Validation Record
       -> Append-only Dataset + Manifest
       -> Binary / Brier / ECE / Timing Offset
```

## 5. 迁移计划（Migration Plan）

1. 在首条生产 Record 前冻结字段语义：保留 `quality_score`，将校准输入明确命名为 `prediction_probability`。
2. T03 只从冻结 `HypothesisState` 构造候选，不消费 Primary Narrative。
3. 先实现 Eligibility Reject 测试，再实现 Reviewer Verdict Workflow。
4. 以 2026-07-01～2026-07-03 Pilot 重新执行准入检查；不合格命题必须保持 Dataset 写入 0。
5. 首条 eligible 样本执行双人 Review、append、Manifest Verify 和 replay。
6. T04 在至少存在人工审核样本后实现指标；低质量/不可验证样本按冻结口径排除。

## 6. 子阶段方案

本次为 M8.phase1 语义边界评审，不新增顶层阶段。执行顺序固定为：

```text
Vocabulary Freeze
-> Eligibility Contract
-> Reviewer Workflow
-> First Ground Truth Record
-> Metrics
```

## 7. ADR 建议清单

- `ADR-M8-009`：只有 Validation-Eligible Hypothesis 可以进入 Ground Truth Dataset。

## 8. 冲突裁决记录

| 冲突 | 采用来源 | 放弃来源 | 裁决理由 |
|---|---|---|---|
| Primary Thesis 是否等于 Prediction | Pilot 真实输出 + Hypothesis 可证伪定义 | 将 Narrative 整体作为预测 | 当日状态陈述没有未来期限，无法校准 |
| Evidence Quality 是否可作概率 | 独立 `quality_score/prediction_probability` | 复用统一 confidence | 可靠性与事件概率语义不同 |
| 不合格命题如何处理 | Eligibility Gate 写入前拒绝 | 写 UNVERIFIABLE 或新增 Failure Type | Eligibility 是输入契约问题，不是市场结果 |
| 是否立即启动 Learning | 先积累 eligible Ground Truth | 从 Narrative 自监督学习 | 当前没有可靠预测标签，学习会自我强化错误 |

## 9. 非目标范围（Non-Goals）

- 不新增 Engine、Belief、Learning 或 Memory。
- 不修改正式 Decision。
- 不增加 Failure Type。
- 不在本次架构评审中修改业务实现代码。
- 不把 Observation/Assessment 从 Notion 或 Market Thesis 中删除。

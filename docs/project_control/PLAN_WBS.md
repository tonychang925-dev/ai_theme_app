# 项目计划（Project Plan）

## Change Log
- 2026-04-23
  - 按 `P3` 重构阶段要求重做第三阶段任务分解，替换旧 `P3.phase0~P3.phase3` WBS。
  - 将 `P3.phase1.0` 执行门禁并入 `P3.phase1` 主里程碑（任务 `P3.phase1-T05~T10`）。
  - 统一口径：`stock_processing_service` 为第三阶段股票侧唯一新生产链路。
- 2026-04-02
  - 保留既有 `P1 / P2` 计划不动
  - 增量补充第三阶段 `P3.phase0 ~ P3.phase3` 里程碑、WBS、依赖与排期摘要
  - 明确 `P3.phase0` 为历史 `P3.phaseA` 的统一命名

## 1. 规划范围（Scope）
- `scope=system`
- 目标：在保留第一阶段与第二阶段执行基线的前提下，正式增量补齐第三阶段（股票服务、复盘链与实时增强）的里程碑、任务拆解、依赖和门禁，形成可执行的 `P1 + P2 + P3` 总计划。
- 约束与假设：
  - 第一阶段与第二阶段计划保留为既有基线；本次仅做第三阶段增量补充。
  - 现有 Redis Stream 主架构不重做，只做收敛与门禁强化。
  - 第二阶段结构化事件统一进入单一事件流，不再区分 `major / normal` 双流。
  - 必须纳入关键优化：创建新题材时复用首阶段分类结果，禁止在 `generate_theme_data_only()` 二次 `_match_categories` 推断。
  - 第二阶段必须遵守 `prd_p2.md`、`ACCEPTANCE.md` 与 `PHASE_CONTRACT_P2.phase0~3.md` 的边界，不允许跨 phase 实现完整目标态。
  - 第三阶段必须遵守 `PRD.md`、`ACCEPTANCE.md` 与第三阶段架构文档的边界：先做 `Tushare + JYHF` 双源事实对象层、复盘快照与统一出口，再进入实时增强。
  - 风险偏好：`medium`；发布期望：`beta/internal`。

## 2. 架构拆解（Architecture Decomposition）
- 子系统清单：
  - 新闻采集与调度：`news_collector_scheduler` / `news_stream_scheduler`
  - 事件处理与分发：`news_stream_handler` / `news_stream_processor`
  - 题材发现与匹配：`theme_processor` / `theme_service` / `theme_discovery_engine` / `semantic_matcher`
  - 题材数据生成与执行：`theme_data_generator` / `DecisionExecutor`
  - 规则生成关键组件：`theme_rule_generator`
  - 第二阶段题材中台：`ThemeMatchEngine` / `ThemeProfileRepository` / `ThemeDecisionEngine`
  - Unknown 与新题材闭环：`unknown_event_pool` / `new_theme_draft` / `theme_merge_review`
  - 题材知识对象与产品输出：已复刻真源 `theme_master / theme_profile_ext / subject_detail / stocks` + serving 对象 `theme_detail_snapshot / theme_history_event / theme_tree_relation / theme_stock_map`
  - 运营化层：`theme_heat_realtime` / `theme_heat_daily` / `theme_lifecycle` / `theme_rank_api`
  - 第三阶段统一出口：`frontend_bff`
  - 第三阶段股票事实层：`stock_processing_service` / `stock_daily_snapshot` / `subject_stock_daily_snapshot` / `stock_abnormal_event` / `theme_stock_leaderboard`
  - 第三阶段报告层：`recap_service` / `pre_market_brief_snapshot` / `post_market_recap_snapshot`
  - 第三阶段输出层：`notion_publisher`
  - 第三阶段实时增强：`intel stream(SSE)` / `minute_abnormal_event` / 轻量产业链视图
- 横切关注点：
  - 契约治理（DecisionEnvelope 版本化）
  - 幂等与回放安全（duplicate-skip + durable cleanup）
  - 观测门禁（死信率、候选爆炸比、积压时长、real_call_ratio）
  - 验证体系（30 案例、三方对比、10% 灰度、真实 DeepSeek）
  - ADR 管理（关键架构决策与变更追溯）
  - 第二阶段运行时契约（`ThemeMatchRequest / ThemeDecisionEnvelope / ThemeAuditLogRecord`）
  - 展示层 / 画像层数据分层
  - Unknown 聚类门禁与草案审核
  - 热度、生命周期与榜单回放
  - 双源字段所有权（`JYHF` vs `Tushare`）
  - 快照对象层冻结
  - 复盘快照唯一真源
  - Notion 单向输出
- 关键路径与不确定性：
  - 关键路径：路由收敛 -> 契约化 -> 幂等门禁 -> 动态阈值 -> 分类复用改造 -> 裁判灰度 -> 回放门禁
  - 第二阶段关键路径：`ThemeMatchEngine` 入核 -> Unknown 闭环 -> 知识对象层 -> 热度与榜单运营化
  - 第三阶段关键路径：`P3.phase0` 统一出口 -> `P3.phase1` 协议冻结与对象层 -> `P3.phase2` 复盘增强 -> `P3.phase3` 实时增强
  - 不确定性：动态阈值在热点分布下稳定性、LLM 裁判时延/成本波动、Unknown 聚类阈值稳定性、知识层来源治理复杂度、`Tushare` 权限边界、`JYHF` 与股票主数据映射一致性、实时链回补时序一致性

## 3. 里程碑总览（Milestone Overview）
| Phase | 名称 | Objective | 风险等级 | 预计时长 | 依赖 |
| --- | --- | --- | --- | --- | --- |
| P1.phase0 | 运行时收敛与契约冻结 | 固定单链路与统一契约，消除行为漂移 | High | 3人天 | 无 |
| P1.phase1 | 路由统一与幂等执行 | 去重路由并建立强幂等，收敛失败策略 | High | 4人天 | P1.phase0 |
| P1.phase2 | 动态阈值与分类复用优化 | 动态阈值稳定精度，并移除二次分类推断 | High | 6人天 | P1.phase1 |
| P1.phase3 | LLM裁判灰度与验证体系落地 | 二阶段语义裁判灰度 + 第12章验证体系强门禁 | Medium-High | 4人天 | P1.phase2 |
| P1.phase4 | 回放安全与发布门禁收口 | 回放一致、SLO阻断、问题闭环与复盘 | High | 4人天 | P1.phase3 |
| P2.phase0 | ThemeMatchEngine 入核与边界收敛 | 将高精度裁决内核正式接入主链路并冻结契约、降级和审计边界 | High | 5人天 | P1.phase4 |
| P2.phase1 | 题材知识库与产品输出 | 建立题材对象层、详情/历史/层级/股票映射与核心接口 | High | 6人天 | P2.phase0 |
| P2.phase2 | 热度、生命周期与榜单运营化 | 建立热度模型、生命周期状态机与榜单更新链路 | Medium | 4人天 | P2.phase1 |
| P2.phase3 | Unknown 与新题材闭环 | 建立 Unknown 入池、聚类成团、草案与审核闭环 | High | 5人天 | P2.phase2 |
| P3.phase0 | 前端统一产品出口第一版 | 冻结 `frontend_bff` 统一出口、错误语义与只读 DTO 契约 | Medium | 4人天 | P2.phase1 |
| P3.phase1 | stock_processing_service 对象层收口 | 建立 `Gateway First + Domain Pure` 的双源对象层与盘前/盘后快照主链 | High | 8人天 | P3.phase0, P2.phase1 |
| P3.phase2 | 复盘增强与工作台深化 | 增强龙虎榜/资金行为/个股工作台与 `/recap`，强化来源链与解释性 | Medium-High | 6人天 | P3.phase1 |
| P3.phase3 | 实时化与高级增强 | 建立 `REST + SSE` 双轨实时链、分钟级异动与轻量产业链视图 | High | 6人天 | P3.phase2 |

## 4. 里程碑详情（Milestone Detail）
### P1.phase0 — 运行时收敛与契约冻结
#### Objective
- 建立第一阶段“单一运行时真相”和统一消息契约基线。
#### Scope
- 固化唯一运行时链路（Processor/Executor/Clustering）。
- 定义 `DecisionEnvelope v1` 字段与版本规则。
- 贯通 `trace_id/payload_version`。
#### Out of Scope
- 动态阈值与 LLM 裁判参数优化。
#### Dependencies
- `ARCH_REVIEW.md`、`prd_p1.md`、第一阶段架构文档第11/12章。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Integration | 旧链路仍被误调用 | 增加运行时路径扫描与告警 | 高 | 中 | 中 |
| Migration | 契约字段新增导致兼容问题 | dual-read(v0/v1) 过渡 | 中 | 中 | 中 |
#### DoD
- [ ] 运行时处理链唯一且可验证
- [ ] DecisionEnvelope v1 定义冻结
- [ ] trace_id 跨流可追踪
- [ ] 重复函数定义清零（高风险模块）
#### Acceptance Gate
- 必跑命令：`pytest database_service/tests/streams -q`
- 阈值/指标：重复入口=0；契约必填覆盖率=100%
- 评审类型：Architecture + Design Gate
- 失败判定：存在双入口/缺失必填字段即失败

### P1.phase1 — 路由统一与幂等执行
#### Objective
- 同一输入在重试/回放场景下保持一致执行结果。
#### Scope
- 收敛 decision routing。
- 建立幂等键策略（`event_id+action+payload_hash`）。
- unknown action/operation fail-fast + dead-letter。
#### Out of Scope
- 阈值 profile 优化。
#### Dependencies
- P1.phase0。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Technical | 幂等键设计不足导致误去重 | 引入冲突样例回放测试 | 高 | 中 | 中 |
| Integration | 解析策略收敛影响旧消息 | 兼容解析 + reject 证据化 | 中 | 中 | 中 |
#### DoD
- [ ] 路由函数唯一实现
- [ ] 幂等键和重复保护策略生效
- [ ] 未知 action/operation 全量 fail-fast
- [ ] 回放同批次无重复写入
#### Acceptance Gate
- 必跑命令：`pytest database_service/tests/streams -q`
- 阈值/指标：重复写入率=0；dead-letter 率不劣化
- 评审类型：Design + QA Gate
- 失败判定：回放不一致或重复写入即失败

### P1.phase2 — 动态阈值与分类复用优化
#### Objective
- 用事件级动态阈值稳定候选规模与质量，并消除新题材创建阶段二次分类推断。
#### Scope
- 阈值 profile：`baseline/balanced/strict` 与 Strong/Candidate/Weak 分层。
- 候选窗口治理（目标 3~30）。
- `theme_rule_generator.generate_theme_data_only()` 改造：复用首阶段分类结果，禁止再次 `_match_categories()`。
#### Out of Scope
- LLM 裁判全量放量。
#### Dependencies
- P1.phase1。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Model | 热点分布突变导致阈值失真 | 分位数回退 + 上限保护 | 高 | 高 | 中 |
| Consistency | 分类来源不唯一导致漂移 | 单一分类真源 + 契约字段固化 | 高 | 高 | 中 |
#### DoD
- [ ] 动态阈值策略完成并可切换
- [ ] 分类复用策略落地（无二次推断）
- [ ] 30案例对比报告产出
- [ ] 无新增 P0/P1 缺陷
#### Acceptance Gate
- 必跑命令：`pytest database_service/tests/e2e/test_p2_phase0_production_harness.py -q`
- 阈值/指标：候选爆炸比<5%；候选窗口3~30；分类一致率=100%
- 评审类型：Model Review + QA Gate
- 失败判定：任一关键指标劣化或出现二次分类推断即失败

### P1.phase3 — LLM裁判灰度与验证体系落地
#### Objective
- 对歧义样本引入二阶段裁判，同时满足第12章验证体系约束。
#### Scope
- 粗筛后裁判链路（可开关、shadow 优先）。
- 30 案例三方对比（优化系统 vs 基线纯聚类 vs 久赢恒丰标准）。
- 10% 灰度 + 真实 DeepSeek 调用门禁（`source_type=real`）。
#### Out of Scope
- 全量生产切流。
#### Dependencies
- P1.phase2。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Model | 裁判输出不稳定 | 温度锁定 + 一致性采样 | 高 | 中 | 中 |
| Cost | 调用成本超预算 | 仅对歧义样本触发 | 中 | 中 | 低 |
| Compliance | 验证体系执行不完整 | 强制校验脚本+阻断发布 | 高 | 中 | 低 |
#### DoD
- [ ] 裁判链路可配置开关
- [ ] 10% 灰度报告完成
- [ ] 真实调用证据齐全（请求ID/时间戳/模型名）
- [ ] 三方评估指标满足门槛
#### Acceptance Gate
- 必跑命令：`pytest tests -q`
- 阈值/指标：P95 附加时延<800ms；real_call_ratio=100%；题材数8~12
- 评审类型：Design + QA + Product Gate
- 失败判定：超时/预算失控/真实调用不足/三方指标不达标即失败

### P1.phase4 — 回放安全与发布门禁收口
#### Objective
- 建立可回放、可审计、可发布闭环并完成 P1 收口。
#### Scope
- pending 清理与 durable success 强绑定。
- 回放一致性与故障演练。
- 发布 SLO 门禁接入（死信率/积压时长/一致率/real_call_ratio）。
#### Out of Scope
- 第二阶段状态机与 CQRS 改造。
#### Dependencies
- P1.phase3。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Migration | 清理策略切换造成积压 | 分批切换 + 回滚阈值 | 高 | 中 | 中 |
| Integration | 门禁误报影响发布节奏 | 设冷启动观察窗 | 中 | 中 | 低 |
#### DoD
- [ ] pending 清理策略验收通过
- [ ] replay 一致性测试通过
- [ ] 发布门禁与告警上线
- [ ] 第一阶段重点问题关闭率=100%
#### Acceptance Gate
- 必跑命令：`pytest database_service/tests/streams -q && pytest tests -q`
- 阈值/指标：回放一致率=100%；重复写入率=0；dead-letter 率低于基线
- 评审类型：QA Gate + Release Gate + Retro
- 失败判定：回放不一致或任一门禁超阈即失败

### P2.phase0 — ThemeMatchEngine 入核与边界收敛
#### Objective
- 将高精度离线裁决内核沉淀为线上唯一题材判定内核，并冻结三态决策、运行时契约、兼容层、降级与审计基线。
#### Scope
- `ThemeMatchEngine` 入核与旁路收敛。
- 结构化事件单流入口收敛。
- `ThemeProfile` 首期画像字段基线。
- 三态决策与审计字段冻结。
- 与 Redis Stream / `DecisionExecutor` 的兼容接入。
#### Out of Scope
- Unknown 聚类成团与新题材草案。
- 久赢式知识对象与榜单产品化。
- 热度与生命周期状态机。
#### Dependencies
- `prd_p2.md`、`ACCEPTANCE.md`、`ARCH_REVIEW.md`、`PHASE_CONTRACT_P2.phase0.md`。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Integration | 新引擎接入引发消费端不兼容 | 保持兼容层和固定 envelope | 高 | 中 | 中 |
| Performance | LLM/reranker 引入时延超预算 | 分层预算 + 超时降级 | 高 | 中 | 中 |
| Contract | 三态字段语义漂移 | 先冻结契约和审计字段 | 高 | 中 | 低 |
#### DoD
- [ ] `ThemeMatchEngine` 成为唯一最终题材判定入口
- [ ] 三态决策与最小审计字段冻结
- [ ] 降级路径与 reason code 生效
- [ ] 性能灰度数据满足预算
#### Acceptance Gate
- 必跑命令：`rg -n "ThemeMatchEngine|semantic_matcher|final decision|matched_theme" .`
- 必跑命令：`rg -n "ThemeMatchEngine|DecisionExecutor|stream:events:structured|stream:events:human_review|stream:events:unknown" .`
- 必跑命令：`.venv/bin/python -m pytest -q`
- 阈值/指标：审计字段覆盖率=100%；总时延 P95<1200ms；P99<2500ms
- 评审类型：Architecture + Design + QA Gate
- 失败判定：存在旁路判定链、无审计最终写入、或性能超阈即失败

### P2.phase1 — 题材知识库与产品输出
#### Objective
- 建立 Core/Profile/Knowledge 三层题材对象，复刻久赢式详情、历史、层级和股票映射，并暴露核心接口；优先打通 `subject_key -> theme_id` 映射、视图整合层、`theme_stock_map` 与 `theme_rank_api`。
- 在既有 `久赢恒丰 -> theme_data_complete -> 数据库` 方案上，建立可持续的增量同步链，保证新增数据可稳定同步到 staging / serving / API。
#### Scope
- `theme_master`
- `theme_profile_ext`
- `subject_detail`
- `stocks`
- `subject_stock_map`
- `subject_rank_daily`
- `theme_data_complete/history|children|details|daily|stock_details|lists`
- `vw_subject_theme_binding`
- `vw_theme_rank_current`
- `vw_theme_detail_joined`
- `vw_theme_stock_map_candidate`
- `vw_theme_tree_candidate`
- `vw_theme_history_candidate`
- `theme_detail_snapshot`
- `theme_history_event`
- `theme_tree_relation`
- `theme_stock_map`
- `/themes/*` 与 `/stocks/{stock_id}/themes` 核心接口
- `jyhf_sync_batch`
- `jyhf_sync_file_manifest`
- `jyhf_sync_subject_state`
- `nodes/history/detail/stock` 四条增量导库链
#### Out of Scope
- 热度模型与生命周期状态机
- 交易策略与个股推荐
#### Dependencies
- `P2.phase0`
- `PHASE_CONTRACT_P2.phase1.md`
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Data | 展示层和画像层混写 | Core/Profile/Knowledge 强分层 | 高 | 中 | 中 |
| Traceability | 历史/股票映射来源断链 | 强制 source/evidence 字段 | 中 | 中 | 中 |
| API | 查询接口结构不稳定 | 统一 schema 与回归门禁 | 高 | 中 | 低 |
| Sync | 日常同步继续依赖 patch/全量重建 | 唯一采集入口 + 批次 manifest + subject 重放 | 高 | 高 | 中 |
#### DoD
- [ ] 三层题材对象模型落地
- [ ] `subject_key -> theme_id` 映射基线落地
- [ ] 视图整合层优先落地并通过字段/性能验证
- [ ] 历史/详情/股票映射可追溯
- [ ] 核心接口结构稳定
- [ ] 展示层与画像层无混写
- [ ] 增量同步方案定稿：唯一采集入口、批次/文件/subject 状态表、四条增量导库链
#### Acceptance Gate
- 必跑命令：`rg -n "theme_master|theme_profile_ext|subject_detail|stocks|theme_detail_snapshot|theme_history_event|theme_tree_relation|theme_stock_map" .`
- 必跑命令：`rg -n "themes/rank|themes\{theme_id\}|stocks\{stock_id\}/themes" docs/project_control/prd_p2.md docs/project_control/ACCEPTANCE.md`
- 必跑命令：`rg -n "import_jyhf_data_optimized|import_jyhf_full_theme_and_children_patch|import_jyhf_to_financial_and_theme|theme_collector" .`
- 必跑命令：`.venv/bin/python -m pytest -q`
- 阈值/指标：详情/榜单接口 P95<500ms；来源追溯覆盖率=100%；真源 -> staging -> serving 断链数=0
- 评审类型：Architecture + QA + Product Gate
- 失败判定：对象混写、跳过视图整合层直接扩张 serving 表、来源断链、接口时延超阈，或日常同步仍依赖 patch/全量重建即失败

### P2.phase2 — 热度、生命周期与榜单运营化
#### Objective
- 建立热度模型、生命周期状态机和榜单更新链路，使题材服务具备可解释的运营化输出能力。
#### Scope
- `theme_heat_realtime`
- `theme_heat_daily`
- `theme_lifecycle`
- 榜单更新链路与回放
#### Out of Scope
- 自动投资建议
- 交易执行链路
#### Dependencies
- `P2.phase1`
- `PHASE_CONTRACT_P2.phase2.md`
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Model | 热度模型不可解释 | 强制热度因子明细 | 高 | 中 | 中 |
| State | 生命周期规则漂移 | 显式状态机配置 | 中 | 中 | 中 |
| Performance | 榜单刷新超时或空榜 | 刷新保护 + 批次监控 | 中 | 中 | 低 |
#### DoD
- [ ] 热度构成字段完整
- [ ] 生命周期状态机可回放
- [ ] 榜单刷新满足时延要求
- [ ] 热度与状态变更具备审计链
#### Acceptance Gate
- 必跑命令：`rg -n "heat_value|heat_level|lifecycle_state|state_transition_reason|rank_refresh_latency_ms" .`
- 必跑命令：`.venv/bin/python -m pytest -q`
- 阈值/指标：榜单刷新 P95<5分钟；空榜次数=0；热度构成字段完整率=100%
- 评审类型：Design + QA + Product Gate
- 失败判定：热度不可解释、状态不可回放、榜单刷新超阈或空榜即失败

### P2.phase3 — Unknown 与新题材闭环
#### Objective
- 建立 Unknown 入池、聚类成团、草案生成和审核闭环，确保未知事件不再被强塞旧题材，也不会绕过审核直接上线。
#### Scope
- `unknown_event_pool`
- Unknown 聚类与阈值配置
- `new_theme_draft`
- `theme_merge_review`
#### Out of Scope
- 正式新题材自动上线
- 不做久赢式详情页和榜单能力
- 热度与生命周期能力
#### Dependencies
- `P2.phase2`
- `PHASE_CONTRACT_P2.phase3.md`
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Model | 聚类阈值过松导致草案爆炸 | 保守阈值 + 人审门禁 | 高 | 中 | 中 |
| Migration | Unknown 数据丢失或不可追溯 | 强制 trace/audit 字段 | 高 | 低 | 中 |
| Product | 草案绕过审核直接上线 | 禁止直接写 `theme_master` | 高 | 低 | 低 |
#### DoD
- [ ] `UNKNOWN` 统一入池
- [ ] 聚类只产出草案，不直接创建正式题材
- [ ] 审核动作与结果可回放
- [ ] 阈值与聚类摘要可审计
#### Acceptance Gate
- 必跑命令：`rg -n "new_theme_draft|unknown_event_pool|theme_merge_review|theme_master" .`
- 必跑命令：`.venv/bin/python -m pytest -q`
- 阈值/指标：Unknown 入池成功率=100%；正式自动建题材数=0
- 评审类型：Design + QA + Product Gate
- 失败判定：Unknown 丢失、草案直上正式题材、审核不可回放即失败

### P3.phase0 — 前端统一产品出口第一版
#### Objective
- 冻结第三阶段统一出口：`frontend_bff` 作为唯一前端读取入口，稳定 `/api/*` 契约、错误语义与 partial 诊断。
#### Scope
- `frontend_bff` 边界冻结
- `/api/intel/feed`、`/api/theme-workspace/{subject_key}`、`/api/stock-workspace/{stock_id}` 契约冻结
- DTO 稳定层、错误码/超时/partial 规范
#### Out of Scope
- `SSE / WebSocket`
- 分钟级异动
- 重型产业链图谱
#### Dependencies
- `P2.phase1`
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Contract | 前端继续绕过 BFF 读底层接口 | 强制 `/api/*` 收口与契约门禁 | 高 | 中 | 低 |
| Integration | DTO 漂移导致前端行为不一致 | DTO 版本化与回归检查 | 中 | 中 | 中 |
#### DoD
- [ ] 三类核心接口契约冻结并评审通过
- [ ] BFF 错误码、超时、partial 规范冻结
- [ ] 前端无直连领域服务
#### Acceptance Gate
- 必跑命令：`.venv/bin/python -m pytest -q frontend_bff/tests/integration`
- 必跑命令：`rg -n "frontend_bff|/api/intel/feed|/api/theme-workspace|/api/stock-workspace" .`
- 阈值/指标：BFF 集成测试通过率=100%；前端直连领域接口数=0
- 评审类型：Architecture + QA Gate
- 失败判定：接口缺失、契约未冻结或前端继续绕过 BFF 即失败

### P3.phase1 — stock_processing_service 对象层收口（含 phase1.0 门禁硬化）
#### Objective
- 建立 `stock_processing_service` 作为唯一新生产链路，完成对象层、快照链、对账与回滚基线，并落地 `P3.phase1.0` 执行门禁。
#### Scope
- `stock_processing_service` 分层落地（application/domain/ports/infrastructure）
- 6 个冻结对象：`stock_daily_snapshot`、`subject_stock_daily_snapshot`、`stock_abnormal_event`、`theme_stock_leaderboard`、`pre_market_brief_snapshot`、`post_market_recap_snapshot`
- `Gateway First`、统一事件 envelope、缓存版本切换、双轨对账
- `P3.phase1.0` 门禁：CI 边界、snapshot pointer、stream runtime、reconcile gate、feature flag register
#### Out of Scope
- 秒级全市场实时行情
- 高频策略引擎
- 重型资金行为体系
#### Dependencies
- `P3.phase0`
- `P2.phase1`
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Architecture | 业务层回退到直连 DB | CI 静态门禁阻断 `asyncpg/SQL/_client/_db` | 高 | 中 | 中 |
| Data | 快照切换出现半成品读取 | `current pointer` 原子切换协议 | 高 | 中 | 高 |
| Governance | 对账无阈值导致误切流 | 对账阈值矩阵 + 自动阻断 + 分级回滚 | 高 | 中 | 中 |
#### DoD
- [ ] `PRD-REQ-P3.phase1-011~018` 全部落地并有验证证据
- [ ] `ACPT-P3B-011~018` 与 `ACPT-P3P10-001~005` 可执行验收通过
- [ ] 连续 5 个交易日对账达标
- [ ] 5 分钟内回滚演练通过
#### Acceptance Gate
- 必跑命令：`.venv/bin/python scripts/ci/check_sps_boundaries.py`
- 必跑命令：`.venv/bin/python scripts/qa/verify_snapshot_pointer_atomicity.py --trade-date 2026-04-22`
- 必跑命令：`.venv/bin/python scripts/qa/check_stream_runtime_contract.py`
- 必跑命令：`.venv/bin/python scripts/qa/run_reconcile_gate.py --trade-date 2026-04-22`
- 必跑命令：`.venv/bin/python scripts/qa/check_flag_register.py`
- 阈值/指标：违规项=0；无半成品读取；对账达标并自动阻断生效；回滚成功率=100%
- 评审类型：Architecture + Data + QA + Release Gate
- 失败判定：任一门禁未通过即失败，不得进入 `P3.phase2`

### P3.phase2 — 复盘增强与工作台深化
#### Objective
- 在对象层稳定前提下，增强龙虎榜/资金行为/个股工作台与 `/recap`，并保证结论可解释、可追溯、可兼容。
#### Scope
- 龙虎榜结构化对象
- 资金行为增强字段（轻量可解释）
- 角色增强（龙头/前排/扩散/跟风）
- 个股工作台聚合与 `/recap` 只读出口
- 复盘来源链与证据字段完整性
#### Out of Scope
- `SSE`
- Tick 级实时平台
- 重型产业链图谱
#### Dependencies
- `P3.phase1`
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Explainability | 增强字段缺乏证据链 | 强制来源链覆盖率门禁 | 高 | 中 | 中 |
| Compatibility | 新字段破坏既有 DTO | 字段只增不改 + 兼容回归 | 高 | 低 | 低 |
| Scope | 资金行为范围膨胀拖慢交付 | 明确首批仅轻量增强 | 中 | 中 | 中 |
#### DoD
- [ ] 龙虎榜/资金行为对象可追溯
- [ ] 个股工作台不再前端拼装
- [ ] `/recap` 稳定消费增强对象
- [ ] 来源链覆盖率=100%
#### Acceptance Gate
- 必跑命令：`.venv/bin/python -m pytest -q`
- 必跑命令：`rg -n "dragon_tiger|money_flow|/recap|workspace|source_trace_id" .`
- 阈值/指标：来源链覆盖率=100%；向后兼容破坏数=0
- 评审类型：Design + QA + Product Gate
- 失败判定：来源链缺失、工作台回退前端拼装或 DTO 破坏兼容即失败

### P3.phase3 — 实时化与高级增强
#### Objective
- 在前序快照闭环稳定后，落地 `REST + SSE` 双轨实时链、分钟级异动和轻量产业链视图，且不污染日频主链。
#### Scope
- `/api/intel/stream`（SSE）
- `REST` 断线回补
- `minute_abnormal_event`
- 情报流与股票异动联动（去重/优先级）
- 轻量产业链只读视图
#### Out of Scope
- 全市场 Tick 平台
- 高频交易策略引擎
- 重型图谱引擎
#### Dependencies
- `P3.phase2`
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Realtime | SSE 断线与回补失序 | REST 回补兜底 + 重放校验 | 高 | 中 | 高 |
| Data | 分钟级噪声误报放大 | 可解释规则 + 阈值分层 | 中 | 高 | 中 |
| Isolation | 实时链影响快照主链 | 主链隔离门禁 + 故障注入演练 | 高 | 中 | 中 |
#### DoD
- [ ] SSE 与 REST 回补可用
- [ ] 分钟级异动可解释且可重放
- [ ] 实时链不影响日频主链
- [ ] 轻量产业链视图可查询
#### Acceptance Gate
- 必跑命令：`.venv/bin/python -m pytest -q`
- 必跑命令：`rg -n "intel/stream|SSE|minute_abnormal_event|industry_chain|replay" .`
- 阈值/指标：SSE 端到端 P95<3s；回补成功率=100%；实时链故障不影响快照主链
- 评审类型：Architecture + QA + Product Gate
- 失败判定：回补失败、实时链污染主链或轻量视图失控即失败

## 5. WBS（任务分解）
### WBS — P1.phase0
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase0-T01 | 冻结第一阶段唯一运行时链路与入口清单 | - | 0.5人天 | 中 | 架构评审记录 | 文档更新,代码审查 |
| P1.phase0-T02 | 定义 DecisionEnvelope v1 字段与 dual-read 兼容策略 | P1.phase0-T01 | 1人天 | 中 | 契约评审通过 | API文档,文档更新 |
| P1.phase0-T03 | 清理重复函数定义并建立静态扫描门禁 | P1.phase0-T02 | 1人天 | 高 | CI扫描报告 | 单元测试,代码审查 |
| P1.phase0-T04 | trace_id/payload_version 全链路贯通方案评审 | P1.phase0-T03 | 0.5人天 | 低 | 链路追踪样例 | 文档更新,代码审查 |

### WBS — P1.phase1
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase1-T01 | 收敛决策路由逻辑并移除重复入口 | P1.phase0-T04 | 1人天 | 高 | 路由单元测试 | 单元测试,代码审查 |
| P1.phase1-T02 | 幂等键规则与 duplicate-skip 执行门禁 | P1.phase1-T01 | 1人天 | 高 | 回放重复写入检查 | 单元测试,文档更新 |
| P1.phase1-T03 | unknown action/operation fail-fast + dead-letter | P1.phase1-T02 | 0.5人天 | 中 | 异常流集成测试 | 集成测试,代码审查 |
| P1.phase1-T04 | 严格 schema 解析替代弱降级策略（禁 `str(value)`） | P1.phase1-T03 | 1人天 | 高 | payload 畸形样本测试 | 单元测试,集成测试 |
| P1.phase1-T05 | 输出阶段验收报告并更新 ADR 追踪链接 | P1.phase1-T04 | 0.5人天 | 低 | 评审结论通过 | 文档更新,代码审查 |

### WBS — P1.phase2
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase2-T01 | 设计并实现动态阈值 profile + 三段分层策略 | P1.phase1-T05 | 1.5人天 | 高 | 策略评审与指标校验 | 单元测试,代码审查 |
| P1.phase2-T02 | 实施候选窗口治理（3~30）与爆炸比监控 | P1.phase2-T01 | 1.5人天 | 高 | 候选分布报表 | 单元测试,性能测试 |
| P1.phase2-T03 | 关键优化：`generate_theme_data_only` 复用首阶段分类结果，移除 `_match_categories` 二次推断 | P1.phase2-T01 | 1人天 | 高 | 分类一致性回放测试 | 单元测试,代码审查 |
| P1.phase2-T04 | 更新 ADR（分类真源复用决策）并完成设计评审归档 | P1.phase2-T03 | 0.5人天 | 中 | ADR 审批记录 | 文档更新,代码审查 |
| P1.phase2-T05 | 30案例 A/B 对比（含分类一致性指标） | P1.phase2-T02 | 1.5人天 | 中 | A/B 报告 | 集成测试,文档更新 |
| P1.phase2-T06 | 分类关键词反向索引补全（`L2 <- L3(tags.keywords)`, `L1 <- L2(keywords)`） | P1.phase2-T03 | 1人天 | 中 | 关键词覆盖率与幂等性报告 | 单元测试,集成测试,文档更新 |

### WBS — P1.phase3
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase3-T01 | 定义二阶段 LLM 裁判触发条件与回退策略 | P1.phase2-T05 | 0.5人天 | 中 | 设计评审 | 文档更新,代码审查 |
| P1.phase3-T02 | 裁判 shadow 接入（分类命中样本全量复核）与超时回退 | P1.phase3-T01 | 1.5人天 | 高 | shadow 运行记录 | 单元测试,集成测试 |
| P1.phase3-T03 | 落地第12章验证体系：10%灰度、三方评估、真实调用证据链 | P1.phase3-T02 | 1.5人天 | 高 | 验收报告与证据包 | 集成测试,文档更新 |
| P1.phase3-T03a | 补充 `source_type(real/mock)` 与质量标签门禁验证（PRD-P1-P3-R07） | P1.phase3-T03 | 0.5人天 | 中 | 门禁验证记录与审计样本 | 集成测试,文档更新 |
| P1.phase3-T04 | 成本/时延/real_call_ratio 门禁配置与评审 | P1.phase3-T03 | 0.5人天 | 中 | Product Gate 记录 | 性能测试,文档更新 |

### WBS — P1.phase4
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase4-T01 | pending durable cleanup 规则与回滚线定义 | P1.phase3-T04 | 1人天 | 高 | 设计评审 | 文档更新,代码审查 |
| P1.phase4-T02 | 回放一致性与故障演练脚本验证 | P1.phase4-T01 | 1.5人天 | 高 | replay 演练报告 | 集成测试,性能测试 |
| P1.phase4-T03 | 发布 SLO 门禁接入（死信率/积压时长/一致率/real_call_ratio） | P1.phase4-T02 | 1人天 | 中 | Gate 通过记录 | 集成测试,文档更新 |
| P1.phase4-T04 | 第一阶段收口复盘与下一阶段输入清单 | P1.phase4-T03 | 0.5人天 | 低 | Retro 结论 | 文档更新,代码审查 |

### WBS — P2.phase0
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P2.phase0-T01 | 冻结 `ThemeMatchEngine` 运行时契约与三态决策 envelope | P1.phase4-T04 | 1人天 | 高 | 契约评审记录 | 文档更新,代码审查 |
| P2.phase0-T02 | 设计单一结构化事件流兼容层并完成 `theme_service -> DecisionExecutor` 接入基线 | P2.phase0-T01 | 1.5人天 | 高 | 链路集成评审 | 文档更新,集成测试 |
| P2.phase0-T03 | 定义 `ThemeProfile` 首期画像字段与索引基线 | P2.phase0-T01 | 1人天 | 中 | 画像字段评审 | 文档更新,代码审查 |
| P2.phase0-T04 | 固化降级策略、reason code 与最小审计字段 | P2.phase0-T02 | 1人天 | 高 | 降级样例与审计样本 | 集成测试,文档更新 |
| P2.phase0-T05 | 完成性能预算灰度验证与 phase0 评审归档 | P2.phase0-T04 | 0.5人天 | 中 | 灰度验证记录 | 性能测试,文档更新 |

### WBS — P2.phase1
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P2.phase1-T01 | 设计 Core/Profile/Knowledge 三层题材对象模型 | P2.phase0-T05 | 1人天 | 高 | 数据模型评审 | 文档更新,代码审查 |
| P2.phase1-T02 | 定义详情/历史对象与来源追溯协议 | P2.phase1-T01 | 1.5人天 | 中 | 来源链样例 | 文档更新,代码审查 |
| P2.phase1-T03 | 定义层级树与股票映射关系类型、证据来源与更新策略 | P2.phase1-T01 | 1.5人天 | 中 | 关系模型评审 | 文档更新,代码审查 |
| P2.phase1-T04 | 设计 `/themes/*` 与 `/stocks/{stock_id}/themes` 核心接口契约 | P2.phase1-T02 | 1人天 | 高 | API 评审 | 文档更新,代码审查 |
| P2.phase1-T05 | 完成对象边界、接口与来源追溯门禁验证 | P2.phase1-T03 | 1人天 | 中 | QA/产品门禁记录 | 集成测试,文档更新 |

### WBS — P2.phase2
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P2.phase2-T01 | 设计热度因子模型与可解释输出字段 | P2.phase1-T05 | 1人天 | 中 | 热度模型评审 | 文档更新,代码审查 |
| P2.phase2-T02 | 设计生命周期状态机与迁移规则 | P2.phase2-T01 | 1人天 | 中 | 状态机评审 | 文档更新,代码审查 |
| P2.phase2-T03 | 设计榜单刷新链路、批次回放与空榜保护 | P2.phase2-T02 | 1.5人天 | 中 | 榜单链路评审 | 文档更新,代码审查 |
| P2.phase2-T04 | 定义热度/状态审计协议与回放验证方法 | P2.phase2-T03 | 1人天 | 中 | 审计样例评审 | 文档更新,代码审查 |
| P2.phase2-T05 | 完成热度与榜单 phase2 门禁验证和归档 | P2.phase2-T04 | 0.5人天 | 低 | 门禁记录 | 集成测试,文档更新 |

### WBS — P2.phase3
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P2.phase3-T01 | 定义 `unknown_event_pool` 结构与 Unknown 入池协议 | P2.phase2-T05 | 1人天 | 中 | 数据结构评审 | 文档更新,代码审查 |
| P2.phase3-T02 | 设计 Unknown 聚类时间窗、阈值与可调参策略 | P2.phase3-T01 | 1.5人天 | 高 | 聚类策略评审 | 文档更新,代码审查 |
| P2.phase3-T03 | 设计 `new_theme_draft` 草案结构与生成规则 | P2.phase3-T02 | 1人天 | 中 | 草案样例评审 | 文档更新,代码审查 |
| P2.phase3-T04 | 设计 `theme_merge_review` 审核动作与审计协议 | P2.phase3-T03 | 1人天 | 高 | 审核流程评审 | 文档更新,代码审查 |
| P2.phase3-T05 | 完成 Unknown 闭环门禁验证与 phase3 评审归档 | P2.phase3-T04 | 0.5人天 | 中 | 门禁记录 | 集成测试,文档更新 |

### WBS — P3.phase0
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P3.phase0-T01 | 统一 `P3.phaseA -> P3.phase0` 命名与历史兼容策略 | P2.phase1-T05 | 0.5人天 | 低 | 文档评审 | 文档更新,代码审查 |
| P3.phase0-T02 | 冻结 `frontend_bff` 与 `/api/*` 长期契约（含错误语义） | P3.phase0-T01 | 1人天 | 中 | 契约评审 | 文档更新,代码审查 |
| P3.phase0-T03 | 建立 `intel/theme/stock-workspace` DTO 稳定层与版本规则 | P3.phase0-T02 | 1人天 | 中 | DTO 回归验证 | 单元测试,集成测试 |
| P3.phase0-T04 | 完成 BFF 超时、错误码、partial diagnostics 门禁配置 | P3.phase0-T03 | 1人天 | 中 | 集成测试 | 集成测试,文档更新 |
| P3.phase0-T05 | phase0 统一出口门禁评审归档并输出基线报告 | P3.phase0-T04 | 0.5人天 | 低 | Gate 记录 | 文档更新,代码审查 |

### WBS — P3.phase1
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P3.phase1-T01 | 冻结 `stock_processing_service` 架构边界与职责（替代旧 `stock_service` 新生产职责） | P3.phase0-T05 | 1人天 | 高 | 架构评审记录 | 文档更新,代码审查 |
| P3.phase1-T02 | 冻结 `DatabaseGateway` 股票域显式 API 与 ports 签名 | P3.phase1-T01 | 1人天 | 高 | API/ports 评审 | 文档更新,代码审查 |
| P3.phase1-T03 | 冻结 6 个对象字段级最小 schema 与 upsert 策略 | P3.phase1-T02 | 1.5人天 | 高 | 数据模型评审 | 文档更新,代码审查 |
| P3.phase1-T04 | 冻结统一事件 envelope 与 stream topic 规范 | P3.phase1-T02 | 1人天 | 中 | 契约评审 | 文档更新,代码审查 |
| P3.phase1-T05 | 落地 `P3.phase1.0`-CI 边界门禁（`asyncpg/SQL/_client/_db`） | P3.phase1-T03 | 1人天 | 高 | `.venv/bin/python scripts/ci/check_sps_boundaries.py` | 单元测试,文档更新 |
| P3.phase1-T06 | 网关升级：收敛 `DatabaseGateway` 为股票域高层领域 API（去透传 `_client` 语义） | P3.phase1-T02 | 1.5人天 | 高 | 网关接口审计与调用链检查 | 集成测试,文档更新 |
| P3.phase1-T07 | `execute_query` 收口：业务路径禁用原始 SQL 通道并建立扫描门禁 | P3.phase1-T06 | 1人天 | 高 | 静态扫描与调用计数报告 | 单元测试,文档更新 |
| P3.phase1-T08 | 落地 `snapshot current pointer` 原子切换与回滚脚本 | P3.phase1-T03 | 1.5人天 | 高 | `.venv/bin/python scripts/qa/verify_snapshot_pointer_atomicity.py --trade-date 2026-04-22` | 集成测试,文档更新 |
| P3.phase1-T09 | 落地 stream 运行时契约与 DLQ 回放规范 | P3.phase1-T04 | 1人天 | 高 | `.venv/bin/python scripts/qa/check_stream_runtime_contract.py` | 集成测试,文档更新 |
| P3.phase1-T10 | 落地对账阈值矩阵与自动阻断门禁 | P3.phase1-T08,P3.phase1-T09 | 1人天 | 高 | `.venv/bin/python scripts/qa/run_reconcile_gate.py --trade-date 2026-04-22` | 集成测试,文档更新 |
| P3.phase1-T11 | 建立 Feature Flag Register 并完成回滚演练 | P3.phase1-T10 | 0.5人天 | 中 | `.venv/bin/python scripts/qa/check_flag_register.py` | 集成测试,文档更新 |
| P3.phase1-T12 | 闭环验收：`输入事件 -> 快照对象 -> 发布事件` 回放与审计链验证 | P3.phase1-T06,P3.phase1-T09 | 1人天 | 高 | 闭环回放报告与审计核对 | 集成测试,文档更新 |
| P3.phase1-T13 | phase1 门禁验收归档（`ACPT-P3B-011~022` + `ACPT-P3P10-001~005`） | P3.phase1-T11,P3.phase1-T12 | 0.5人天 | 中 | 验收记录 | 文档更新,代码审查 |

### WBS — P3.phase2
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P3.phase2-T01 | 冻结龙虎榜结构化对象与来源链（可回溯） | P3.phase1-T13 | 1人天 | 中 | 对象评审 | 文档更新,代码审查 |
| P3.phase2-T02 | 冻结资金行为增强字段与轻量解释规则 | P3.phase2-T01 | 1人天 | 高 | 规则评审 | 文档更新,代码审查 |
| P3.phase2-T03 | 增强 `theme_stock_leaderboard` 角色分层（龙头/前排/扩散/跟风） | P3.phase2-T02 | 1人天 | 中 | 规则回放评审 | 文档更新,代码审查 |
| P3.phase2-T04 | 冻结个股工作台聚合契约（禁止前端拼装） | P3.phase2-T03 | 1.5人天 | 中 | API 契约评审 | 文档更新,代码审查 |
| P3.phase2-T05 | 冻结 `/recap` 只读出口与 `recap_service` 唯一聚合边界 | P3.phase2-T04 | 1人天 | 高 | ADR 与接口评审 | 文档更新,代码审查 |
| P3.phase2-T06 | phase2 门禁验收归档（来源链覆盖率/兼容性） | P3.phase2-T05 | 0.5人天 | 中 | 门禁记录 | 集成测试,文档更新 |

### WBS — P3.phase3
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P3.phase3-T01 | 冻结 `REST + SSE` 双轨实时链路与断线回补策略 | P3.phase2-T06 | 1人天 | 高 | 架构评审 | 文档更新,代码审查 |
| P3.phase3-T02 | 冻结 `minute_abnormal_event` 对象与可解释规则 | P3.phase3-T01 | 1.5人天 | 高 | 规则评审 | 文档更新,代码审查 |
| P3.phase3-T03 | 冻结情报-题材-股票联动、去重与优先级策略 | P3.phase3-T02 | 1人天 | 中 | 流程回放评审 | 文档更新,代码审查 |
| P3.phase3-T04 | 冻结轻量产业链视图与只读边界 | P3.phase3-T03 | 1人天 | 中 | 知识视图评审 | 文档更新,代码审查 |
| P3.phase3-T05 | 实时链与日频快照主链隔离门禁（故障注入） | P3.phase3-T04 | 1人天 | 高 | 失败注入评审 | 集成测试,文档更新 |
| P3.phase3-T06 | phase3 门禁验收归档（SSE P95/回补/主链隔离） | P3.phase3-T05 | 0.5人天 | 中 | 门禁记录 | 集成测试,文档更新 |

## 6. 依赖图（Dependency Graph）
- Milestone dependency graph：
  - `P1.phase0 -> P1.phase1 -> P1.phase2 -> P1.phase3 -> P1.phase4`
  - `P1.phase4 -> P2.phase0 -> P2.phase1 -> P2.phase2 -> P2.phase3`
  - `P2.phase1 -> P3.phase0 -> P3.phase1(含phase1.0门禁) -> P3.phase2 -> P3.phase3`
- 关键路径：
  - `契约冻结 -> 路由统一幂等 -> 动态阈值 -> 分类复用改造 -> 验证体系落地 -> 回放门禁`
  - `判定内核入核 -> 知识对象层 -> 热度与榜单运营化 -> Unknown 闭环`
  - `统一产品出口 -> Gateway/对象协议冻结 -> phase1.0 执行门禁 -> 复盘增强 -> REST + SSE 实时增强`
- 可并行段：
  - `P1.phase2` 中 `T02` 与 `T03` 可并行（阈值治理与分类复用改造）。
  - `P1.phase3` 中指标看板准备可与 shadow 接入并行。
  - `P2.phase0` 中 `T02` 与 `T03` 可并行（单流兼容层接入与画像字段定义）。
  - `P2.phase1` 中 `T02` 与 `T03` 可并行（详情历史与层级股票关系建模）。
  - `P3.phase1` 中 `T03` 与 `T04` 可并行（对象 schema 与事件契约），但必须晚于 gateway/ports 冻结。
  - `P3.phase1` 中 `T06` 与 `T07` 可并行（pointer 协议与 stream runtime），但都必须早于对账门禁 `T08`。
  - `P3.phase2` 中 `T01` 与 `T03` 可局部并行（龙虎榜对象与榜单角色），但 `/recap` 出口必须等待 `T05` 边界冻结。
- 风险集中区：
  - `P1.phase2`（阈值稳定性 + 分类一致性）
  - `P1.phase3`（真实模型验证与灰度成本）
  - `P1.phase4`（清理时序与回放一致性）
  - `P2.phase0`（契约/兼容/性能预算）
  - `P2.phase1`（数据分层与来源治理）
  - `P2.phase3`（Unknown 聚类阈值与审核边界）
  - `P3.phase1`（执行门禁缺失、快照 pointer 漂移、对账阈值失效）
  - `P3.phase3`（SSE 回补失序、分钟级噪声放大、实时链污染快照主链）
- 阻塞节点：
  - `P1.phase0-T02`（契约冻结）
  - `P1.phase1-T02`（幂等键定稿）
  - `P1.phase2-T03`（二次分类推断移除）
  - `P2.phase0-T01`（ThemeMatchEngine 契约冻结）
  - `P2.phase1-T01`（三层对象模型定稿）
  - `P2.phase3-T02`（Unknown 聚类阈值定稿）
  - `P3.phase0-T02`（BFF 长期契约冻结）
  - `P3.phase1-T02`（Gateway API + ports 签名冻结）
  - `P3.phase1-T07`（`execute_query` 业务路径收口）
  - `P3.phase1-T10`（对账门禁自动阻断）
  - `P3.phase2-T05`（`recap_service` 唯一聚合层冻结）
- 跨阶段耦合点：
  - LLM 裁判策略与第二阶段语义演化接口存在耦合，需要 ADR 追踪。
  - `P2.phase0` 的三态决策直接约束 `P2.phase3` Unknown 闭环。
  - `P2.phase1` 的对象模型直接约束 `P2.phase2` 榜单与热度输出。
  - `P2.phase1` 的题材知识对象和 `theme_stock_map` 直接约束 `P3.phase1` 的题材-股票拼接与工作台展示。
  - `P3.phase1` 的协议冻结与门禁体系直接约束 `P3.phase2` 复盘解释和 `P3.phase3` 实时链回补边界。
- 需要 ADR 的节点：
  - 动态阈值策略变更、分类真源复用策略、pending 清理规则。
  - ThemeMatchEngine 契约变更、Core/Profile/Knowledge 分层、热度公式与状态机规则、Unknown 聚类阈值变更。
  - Gateway 访问策略、快照 pointer 协议、stream runtime 契约、对账门禁阈值、feature flag register、`recap_service` 唯一聚合层、`REST + SSE` 双轨实时链。

## 7. 排期摘要（Timeline Summary）
- 第一阶段保守估算：`26人天`
- 第二阶段保守估算：`20人天`
- 第三阶段保守估算：`24人天`
- 项目总保守估算：`70人天`
- 第一阶段激进估算：`18人天`
- 第二阶段激进估算：`14人天`
- 第三阶段激进估算：`18人天`
- 项目总激进估算：`50人天`
- 第一阶段风险调整估算：`21人天`
- 第二阶段风险调整估算：`16人天`
- 第三阶段风险调整估算：`20人天`
- 项目总风险调整估算：`57人天`（推荐）
- 关键假设：
  - 核心开发 2 人 + 测试/评审 1 人可持续投入。
  - DeepSeek 真实调用环境可稳定提供验收所需配额。
  - 第二阶段继续沿用现有 Redis Stream 主链路，不增加额外基础设施重构。
  - 第三阶段默认采用 `Tushare + JYHF` 双源，不在首批引入高成本 Tick 级商业行情。
- 最大风险与缓解：
  - 最大风险：`P1.phase2` 分类复用改造与动态阈值同时变更引发行为偏移。
  - 缓解：分阶段灰度（10%）+ 回放对齐 + ADR 审批后再扩量。
  - 第二阶段最大风险：`P2.phase0` 契约/兼容/性能未同时收敛，导致后续 P2.phase1~3 建在不稳定基线上。
  - 缓解：先完成 phase0 运行时基线与灰度门禁，再推进 Unknown、知识对象和榜单能力。
  - 第三阶段最大风险：在 `P3.phase1.0` 门禁与网关升级未落地前推进业务开发，导致边界失守与切流风险不可控。
  - 缓解：严格执行 `P3.phase1-T01~T13`，门禁全通过后再推进 `P3.phase2~3`。

## 8. 2026-03-31 进度回写

- `P2.phase0` 当前已完成：
  - 运行时 `ThemeMatchEngine` 等价复刻 `final_theme_matcher.py` 主链
  - 默认结构化 parser 切换到 `ReliableDeepSeekParser`
  - `100` 条真实全链路 QA：`top1_accuracy = 0.96`
- 当前 `P2.phase0` 剩余工作从“稳定性修复”转为“少量误判专项优化”：
  - `海洋经济`
  - `液冷数据中心`

## 9. 2026-04-23 第三阶段重排进度回写

- `P3.phase0` 当前状态：
  - 已形成统一产品出口第一版文档口径，历史 `P3.phaseA` 已统一记为 `P3.phase0`
  - `frontend_bff` / `/api/intel/feed` / 工作台出口已形成阶段边界基线
- `P3.phase1` 当前状态：
  - 已冻结 `stock_processing_service` 方向与 `PRD-REQ-P3.phase1-011~018`
  - 新增 `P3.phase1.0` 执行门禁条款（CI/Pointer/Stream/Reconcile/Flag）
  - 当前进入“门禁先行”阶段：未完成 `P3.phase1-T01~T13` 前，不进入 `P3.phase2`
- `P3.phase2 ~ P3.phase3` 当前状态：
  - `P3.phase2`：处于“重排后待执行”状态，依赖 `P3.phase1` 门禁完成
  - `P3.phase3`：仍处于 PRD/WBS/Contract 准备阶段，尚未进入正式开发排期

## 10. P3 实施日程对齐（D1-D10）

> 目的：将“实施建议”固化为 WBS 执行节奏，避免计划与 feature 设计分歧。

| Day | 执行主题 | 对应任务 | 核心产出 | 当日验收命令 |
| --- | --- | --- | --- | --- |
| D1 | 冻结窗口与基线清理 | `P3.phase0-T01` | 分支冻结规则、运行数据剥离清单、P3真源文档确认、D1守卫报告 | `.venv/bin/python scripts/p3_d1_workspace_guard.py --output tmp/p3_d1_workspace_guard_report.json` |
| D2 | 门禁脚本补齐（可执行） | `P3.phase1-T05/T08/T09/T10/T11` | `scripts/ci` 与 `scripts/qa` 五个门禁脚本骨架 | `.venv/bin/python scripts/ci/check_sps_boundaries.py --help` |
| D3 | 网关股票域 API 冻结 | `P3.phase1-T02` | 显式 `get_*/upsert_*/publish_*` 接口清单 | `rg -n "def get_|def upsert_|def publish_" database_service/gateway.py` |
| D4 | `execute_query` 业务收口 | `P3.phase1-T07` | 业务路径清零报告 + CI 阻断规则 | `rg -n "execute_query\\(" stock_processing_service database_service | rg -v "scripts|tests|docs"` |
| D5 | `stock_processing_service` 网关适配补全 | `P3.phase1-T06` | market/theme/object gateway 非占位化 + 强类型端口接入 | `rg -n "NotImplementedError" stock_processing_service/infrastructure/gateway_adapters` |
| D6 | 6对象 schema + upsert 策略落地 | `P3.phase1-T03` | 字段级 schema、主键、覆盖策略矩阵 | `.venv/bin/python -m pytest -q stock_processing_service/tests` |
| D7 | 闭环打通与审计 | `P3.phase1-T12` | 输入事件->快照对象->发布事件闭环报告 | `.venv/bin/python scripts/qa/check_stream_runtime_contract.py` |
| D8 | 双轨对账 | `P3.phase1-T10` | `summary + diff_samples.jsonl` | `.venv/bin/python scripts/qa/run_reconcile_gate.py --trade-date 2026-04-22` |
| D9 | BFF 灰度切流 | `P3.phase0-T02/T04` | feature flag 切流记录、回滚预案 | `.venv/bin/python scripts/qa/check_flag_register.py` |
| D10 | Phase1/1.0 验收归档 | `P3.phase1-T13` | `ACPT-P3B-011~022` 与 `ACPT-P3P10-001~005` 证据包 | `.venv/bin/python -m pytest -q` |

### 10.1 一致性约束（WBS vs FEATURE）
- `D1-D10` 为执行节拍真源；若 `FEATURE_SPEC_P3.md` 存在冲突，以本节节拍为准并要求同日同步修订 feature 文档。
- `P3.phase1-T06/T07/T12` 属于阻塞项：未完成不得推进 `P3.phase2` 开发。
- 任何新增 P3 任务必须同时补充：
  - `PLAN_WBS.md`（里程碑/依赖）
  - `FEATURE_SPEC_P3.md`（任务实现与测试）
  - `feature_traceability_P3.json`（映射）

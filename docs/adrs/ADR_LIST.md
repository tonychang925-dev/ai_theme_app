# ADR List

> 文档维护守则（强制）：
> 1. 本文档仅允许“增量追加”新 ADR 或增量附录，禁止覆盖历史 ADR 正文。  
> 2. 历史 ADR 如失效，必须追加“失效说明/替代 ADR”，不得直接删除原条目。  
> 3. 所有新增 ADR 必须保留 `Context/Decision/Alternatives/Consequences/Trigger` 五段结构。

### ADR-001: 第一阶段运行时单链路冻结
- Context
  - `theme_processor/theme_service/news_stream_handler` 存在重复定义与并行行为。
- Problem
  - 同输入可能触发不同分支，结果不可预测。
- Proposed Decision
  - 冻结单链路实现并清理重复定义。
- Alternatives
  - 保留多实现并依赖配置切换。
- Consequences
  - 确定性提升；一次性清理成本中等。
- Trigger
  - 出现重复入口、链路歧义或回放结果不一致时。

### ADR-002: DecisionEnvelope v1 强制契约
- Context
  - 决策消息存在弱解析与字段漂移。
- Problem
  - 回放和归因不可稳定复现。
- Proposed Decision
  - 强制 `decision_id/event_id/action/payload_version/trace_id/idempotency_key/payload`。
- Alternatives
  - 继续宽松消费端兼容。
- Consequences
  - 契约稳定；producer/consumer 均需改造。
- Trigger
  - 决策消息解析行为漂移或字段兼容失败时。

### ADR-003: DecisionExecutor 幂等门禁
- Context
  - 重试与回放场景存在重复执行风险。
- Problem
  - 题材与映射重复写入污染指标。
- Proposed Decision
  - 执行前校验 `idempotency_key`，命中后 `duplicate_skip`。
- Alternatives
  - 离线去重修复。
- Consequences
  - 一致性显著提升；需存储与索引支持。
- Trigger
  - 发生重复消息重放或回放场景时。

### ADR-004: unknown operation fail-fast
- Context
  - 当前未知 operation 可被跳过。
- Problem
  - 执行语义不闭合，异常不可追踪。
- Proposed Decision
  - unknown action/operation 直接失败并入 dead-letter。
- Alternatives
  - warning 后继续处理。
- Consequences
  - 透明性增强；短期死信率可能上升。
- Trigger
  - 决策执行器接收到未知 operation 时。

### ADR-005: 动态阈值替代固定阈值主路径
- Context
  - 当前主路径仍使用固定阈值。
- Problem
  - 漏召回与候选爆炸并存。
- Proposed Decision
  - 事件级动态阈值 + Strong/Candidate/Weak 分层。
- Alternatives
  - 固定阈值人工调参。
- Consequences
  - 稳定性提升；需要 A/B 与监控。
- Trigger
  - 候选爆炸或漏召回长期共存时。

### ADR-006: 禁止随机/零向量进入最终决策
- Context
  - 模型异常时存在随机/零向量回退。
- Problem
  - 错配被放大且难以审计。
- Proposed Decision
  - 异常路径仅允许受控降级，不产出最终主题决策。
- Alternatives
  - 保留随机/零向量兜底。
- Consequences
  - 准确性提升；未匹配事件会增加。
- Trigger
  - 向量模型异常或 embedding 不可用时。

### ADR-007: 题材代码与决策ID确定性生成
- Context
  - 代码中存在时间戳/运行时 hash 生成 ID。
- Problem
  - 相同输入回放结果不一致。
- Proposed Decision
  - 使用输入哈希与稳定规则生成业务 ID。
- Alternatives
  - 保持时间戳编码。
- Consequences
  - 回放一致；需要历史 ID 映射。
- Trigger
  - 回放一致性被破坏时。

### ADR-008: mock 数据门禁化
- Context
  - mock/real 虽有统计但未阻断发布。
- Problem
  - 评估与线上结果被 mock 污染。
- Proposed Decision
  - 将 `mock_source_ratio` 纳入 Release Gate。
- Alternatives
  - 仅日志提示。
- Consequences
  - 评估可信度提升；测试环境要求更高。
- Trigger
  - 灰度或验收数据混入 mock 来源时。

### ADR-009: pending 清理与 durable success 强绑定
- Context
  - 清理时序与持久化确认绑定不硬。
- Problem
  - 可能形成不可回放缺口。
- Proposed Decision
  - 清理动作必须依赖 durable success 证据。
- Alternatives
  - 发布后立即清理。
- Consequences
  - 回放安全增强；短期积压上升。
- Trigger
  - pending 消息清理与落库状态不一致时。

### ADR-010: 结构化可观测性最小集合
- Context
  - 生产路径有大量 `print/traceback`。
- Problem
  - 可观测性分散，难门禁化。
- Proposed Decision
  - 统一日志字段与指标：`trace_id/idempotency_key/source_type/gate_result`。
- Alternatives
  - 继续人工日志巡检。
- Consequences
  - 发布可控；需监控接入改造。
- Trigger
  - 关键链路无法被统一追踪或门禁化时。

### ADR-011: 新题材创建阶段禁止二次分类推断
- Context
  - 创建新题材应沿用首阶段分类结果，不再重复推断。
- Problem
  - 同一事件可能出现两次分类结果不一致，导致题材归属漂移与回放不一致。
- Proposed Decision
  - 分类推断单一真源前置到“事件匹配题材阶段”；生成器禁止内部二次分类推断。
- Alternatives
  - 保留生成器内二次分类推断作为兜底。
- Consequences
  - 分类一致性与可解释性提升；需改造调用链并补齐兼容校验。
- Trigger
  - 新题材创建路径出现分类漂移时。

### ADR-012: 第一阶段强制引入 LLM 最终裁决
- Context
  - 向量语义匹配存在高相似错配。
- Problem
  - 仅依赖向量相似度无法作为最终可靠判定依据。
- Proposed Decision
  - 固化两阶段顺序：`向量粗筛 -> LLM 最终裁决`。
- Alternatives
  - LLM 仅做 shadow 对比。
- Consequences
  - 错配下降；时延与调用复杂度上升。
- Trigger
  - 高相似错配持续出现时。

### ADR-013: 分类命中后全量 LLM 复核
- Context
  - 仅歧义样本触发 LLM 无法覆盖高置信误匹配场景。
- Problem
  - 未进入复核的高相似错配会直接落库。
- Proposed Decision
  - 对分类命中样本执行全量 LLM 复核，灰度只影响是否采用结果，不影响是否调用。
- Alternatives
  - 仅歧义样本触发复核。
- Consequences
  - 误匹配风险下降；成本上升。
- Trigger
  - 高置信误匹配仍无法压制时。

### ADR-014: 人工终审兜底机制（pending_manual_review）
- Context
  - 即使引入 LLM 全量复核，仍存在模型不确定与市场语义突变场景。
- Problem
  - 若缺少人工终审入口，不确定样本只能机器自动决策。
- Proposed Decision
  - 引入统一人工终审队列，并强制记录审计字段。
- Alternatives
  - 继续全自动闭环。
- Consequences
  - 风险降低；时延与人工成本上升。
- Trigger
  - 出现 `abstain/category_uncertain` 或门禁异常时。

### ADR-015: ThemeMatchEngine 作为唯一线上题材判定内核
- Context
  - 离线高精度裁决成果已被纳入新架构。
- Problem
  - 若保留多个并行判定入口，线上线下口径无法一致。
- Proposed Decision
  - 将线上题材判定统一收敛到 `ThemeMatchEngine`。
- Alternatives
  - 新旧判定路径长期并行共存。
- Consequences
  - 线上线下统一；需要兼容层与切换策略。
- Trigger
  - 进入 `P2.phase0` 实施时。

### ADR-016: Unknown Pool 两级触发机制
- Context
  - 新题材发现需要平衡拒识能力与题材爆炸风险。
- Problem
  - 单事件直接建题材会引发噪声扩张。
- Proposed Decision
  - 采用“事件级 UNKNOWN + 群体级聚类成团”的两级机制。
- Alternatives
  - 事件级直接建题材。
- Consequences
  - 新题材质量提升；需增加观察窗口与聚类治理。
- Trigger
  - 进入 Unknown 与新题材能力扩展阶段时。

### ADR-017: 展示层与在线匹配画像强解耦
- Context
  - `JYHF` 数据适合展示与知识承载，不适合直接承担在线匹配索引职责。
- Problem
  - 若混用，一套表会承担双重职责并快速失控。
- Proposed Decision
  - 拆分知识展示层与在线匹配画像层。
- Alternatives
  - 在题材主表中叠加全部字段。
- Consequences
  - 职责清晰；需要同步治理。
- Trigger
  - 开始落 `theme_master_v2/theme_profile_v2` 时。

### ADR-018: 题材知识对象三层存储模型
- Context
  - 新架构包含主对象、画像对象与知识/产品对象。
- Problem
  - 若不分层，结构会持续膨胀且难以演化。
- Proposed Decision
  - 采用 Core/Profile/Knowledge 三层存储模型。
- Alternatives
  - 单表大对象。
- Consequences
  - 易扩展；同步复杂度上升。
- Trigger
  - 数据模型设计冻结前。

### ADR-019: 在线匹配链路性能预算与降级门禁
- Context
  - 混合召回、精排、LLM 裁决引入显著时延和容量风险。
- Problem
  - 若无预算与门禁，主链路会成为不可控瓶颈。
- Proposed Decision
  - 为 retrieval/rerank/judge/total 四层定义预算，并引入超时降级与熔断门禁。
- Alternatives
  - 先上线再观察。
- Consequences
  - 可控性提升；实现复杂度上升。
- Trigger
  - 进入灰度前。

### ADR-020: 第三阶段双源字段所有权冻结
- Context
  - 第三阶段已确定采用 `Tushare + JYHF` 双源方案。
- Problem
  - 若不冻结字段真源，后续会出现双写、双算和口径漂移。
- Proposed Decision
  - `JYHF` 只承担题材事件、题材池和题材上下文；`Tushare` 只承担股票日频事实、交易日历与基础证券信息。
- Alternatives
  - 两个源对同一业务字段并行提供并在消费端动态择优。
- Consequences
  - 真源清晰；需要补字段映射表与冲突裁决规则。
- Trigger
  - 同一业务字段出现多源冲突或重复加工时。

### ADR-021: 第三阶段快照对象层冻结
- Context
  - 第三阶段已定义 `stock_daily_snapshot / subject_stock_daily_snapshot / stock_abnormal_event / theme_stock_leaderboard / pre_market_brief_snapshot / post_market_recap_snapshot`。
- Problem
  - 若对象层不冻结，页面、复盘、Notion 会持续各自拼装和漂移。
- Proposed Decision
  - 将上述对象层冻结为第三阶段首批正式真源，字段只增不改。
- Alternatives
  - 由页面和任务脚本直接读取多张底层表进行临时拼装。
- Consequences
  - 一致性提升；需要承担对象层维护成本。
- Trigger
  - 出现同一交易日不同出口内容不一致时。

### ADR-022: stock_service 冻结为事实对象层
- Context
  - 第三阶段讨论中，`stock_service` 易被持续膨胀为“行情 + 实时流 + 复盘 + 输出”的巨型服务。
- Problem
  - 杂糅职责会使服务边界失控，后续维护困难。
- Proposed Decision
  - `stock_service` 仅负责股票事实标准化、派生状态和榜单对象，不承担报告拼装和外部输出。
- Alternatives
  - 让 `stock_service` 继续吸收复盘、推送和输出逻辑。
- Consequences
  - 边界清晰；需要额外引入 `recap_service` 和 publisher 层。
- Trigger
  - 新需求尝试把复盘拼装或 Notion 写入压进 `stock_service` 时。

### ADR-023: recap_service 作为唯一报告聚合层
- Context
  - 盘前必读、盘后复盘、`/recap` 页面和 Notion 都需要消费同一份报告语义。
- Problem
  - 若每个出口各自聚合，报告内容会长期漂移。
- Proposed Decision
  - `recap_service` 成为唯一报告聚合层，只输出 snapshot；页面和 Notion 都只读 snapshot。
- Alternatives
  - 前端、BFF、Notion 各自组装报告。
- Consequences
  - 报告一致性提升；聚合复杂度集中。
- Trigger
  - 页面与 Notion 的复盘结论出现不一致时。

### ADR-024: Notion 仅作为输出层
- Context
  - 第三阶段需要将复盘和盘前报告同步到 Notion。
- Problem
  - 若 Notion 被当作业务真源，会破坏系统内对象层与回放一致性。
- Proposed Decision
  - Notion 只作为输出层，不参与业务计算和回写真源。
- Alternatives
  - 直接以 Notion 页面结构作为产品链主数据。
- Consequences
  - 系统内部一致性更强；Notion 成为单向发布终端。
- Trigger
  - 需求开始要求从 Notion 反向读取并驱动业务逻辑时。

### ADR-025: 实时链采用 REST + SSE 双轨
- Context
  - 第三阶段需要引入实时情报流，但现有 `/intel/feed` 已稳定存在。
- Problem
  - 若直接跳到重型 WebSocket/高频推送，复杂度过高且回补困难。
- Proposed Decision
  - 保留 `REST` 作为基线与回补链，新增 `SSE` 作为单向实时增强。
- Alternatives
  - 仅靠轮询；或直接全量转向 WebSocket。
- Consequences
  - 复杂度可控；客户端仍需处理断线恢复。
- Trigger
  - `/intel` 需要实时增量更新且当前轮询延迟不可接受时。

### ADR-026: 分钟级异动晚于日频对象层
- Context
  - 分钟级异动对实时化有价值，但复杂度显著高于日频对象层。
- Problem
  - 若在对象层未稳定前引入分钟级异动，会导致全链路基础不稳。
- Proposed Decision
  - 分钟级异动仅在 `P3.phase3` 进入，且建立在既有快照与对象层之上。
- Alternatives
  - 在 `P3.phase1` 就建设分钟级异动链。
- Consequences
  - 降低前序阶段风险；盘中能力上线更晚。
- Trigger
  - 对象层与复盘快照已稳定后，产品明确要求盘中增强时。

### ADR-027: 轻量产业链视图不等于正式图谱真源
- Context
  - 第三阶段希望支持题材 -> 环节 -> 股票的查看能力。
- Problem
  - 若不加限制，轻量视图会在实现阶段演化成半成品重型图谱服务。
- Proposed Decision
  - 第三阶段仅提供轻量只读产业链视图，不将其定义为正式图谱真源。
- Alternatives
  - 在第三阶段直接建设重型图谱服务。
- Consequences
  - 交付更快；长期知识深度受限。
- Trigger
  - 页面需要基础产业链查看，但环节级知识真源仍不稳定时。

### ADR-028: 涨停原因归因采用候选归因而非确定性真因
- Context
  - 第三阶段将引入 `Tushare` 资讯、公告和股票事实，用于复盘解释。
- Problem
  - 若把资讯直接当成”涨停真因”，会产生高误导性结论。
- Proposed Decision
  - 对涨停原因仅输出候选归因、置信度和支撑证据，不输出确定性真因。
- Alternatives
  - 直接输出”该股涨停原因就是某条新闻”。
- Consequences
  - 解释性更诚实；产品文案复杂度上升。
- Trigger
  - 复盘系统开始输出个股涨停原因时。

### ADR-029: 前端仅展示 AI 输出，禁止前端业务计算
- Context
  - 第四阶段前端投研工作台需要展示 AI 对市场的理解结果。
- Problem
  - 若前端进行排序、权重、评分等业务计算，会导致前后端认知不一致，破坏”AI为主，人为辅”原则。
- Proposed Decision
  - 前端仅负责展示 AI 输出，所有排序、权重、评分必须来自后端，前端不得重算。
- Alternatives
  - 允许前端在特定场景下进行轻量业务计算。
- Consequences
  - 前后端认知一致；前端职责清晰；需要后端提供完整计算数据。
- Trigger
  - 前端代码中出现排序、权重、评分等业务计算逻辑时。

### ADR-030: DailyReview 数据结构与 API 契约冻结
- Context
  - 第四阶段需要前后端并行开发 DailyReview 功能。
- Problem
  - 若数据结构与 API 契约不冻结，前后端开发会频繁返工，影响交付进度。
- Proposed Decision
  - 立即冻结 `DailyReview`、`MarketSummary`、`ThemeReview`、`CapitalReview`、`TradingPrinciple` 等核心数据结构，字段只增不改语义。
- Alternatives
  - 保持契约灵活，允许开发过程中调整。
- Consequences
  - 前后端开发效率提升；契约稳定性增强；字段变更需要严格管理。
- Trigger
  - 开始 DailyReview 功能开发前。

### ADR-031: 前端状态管理单一真源原则
- Context
  - 投研工作台三栏布局需要复杂的组件间状态同步。
- Problem
  - 若状态管理设计不当，会导致组件间状态漂移和渲染不一致。
- Proposed Decision
  - 采用单一真源状态管理，以 `currentThemeId` 为核心状态，派生状态统一管理。
- Alternatives
  - 允许多点状态管理，依赖事件总线同步。
- Consequences
  - 状态一致性提升；调试复杂度降低；需要精心设计状态派生关系。
- Trigger
  - 出现组件间状态不一致或渲染异常时。

### ADR-032: 前端性能监控基线定义
- Context
  - 投研工作台需要高信息密度展示，对性能要求较高。
- Problem
  - 若无性能监控基线，页面卡顿会影响决策效率，且问题难以定位。
- Proposed Decision
  - 定义前端性能监控基线：题材切换 P95 < 1000ms，页面首次加载 P95 < 3000ms。
- Alternatives
  - 先开发后优化，依赖用户反馈发现问题。
- Consequences
  - 用户体验可衡量；问题定位快速；需要建立监控体系。
- Trigger
  - 用户反馈页面响应慢或性能测试不达标时。

### ADR-033: 前端向后兼容策略
- Context
  - 前端需要支持产品持续迭代和 API 演进。
- Problem
  - 若无向后兼容策略，API 字段变更会导致旧版本前端不可用。
- Proposed Decision
  - 制定前端向后兼容策略，支持字段渐进式升级，旧字段至少保留一个版本周期。
- Alternatives
  - 强制用户升级，不保留向后兼容。
- Consequences
  - 用户体验平滑；升级风险降低；需要维护兼容逻辑。
- Trigger
  - API 字段变更或产品版本升级时。

### ADR-034: 避免重型组件库，保持信息密度优先
- Context
  - 投研工作台需要高信息密度与高度定制化界面。
- Problem
  - AntD 等重型组件库会限制界面信息密度与定制能力。
- Proposed Decision
  - 采用 Tailwind CSS + 定制组件方案，避免引入 AntD 等重型组件库。
- Alternatives
  - 使用 AntD 等成熟组件库提升开发效率。
- Consequences
  - 界面信息密度最大化；定制能力强；开发效率可能受影响。
- Trigger
  - 评估前端技术栈或引入新组件库时。

### ADR-035: 前端设计系统与组件库规范
- Context
  - 前端需要长期维护和多人协作开发。
- Problem
  - 若无统一设计系统，组件样式与交互会不一致，增加维护成本。
- Proposed Decision
  - 建立前端设计系统，定义基础组件、样式规范、交互模式。
- Alternatives
  - 各模块独立开发，后期统一。
- Consequences
  - 开发效率提升；用户体验一致；需要前期设计投入。
- Trigger
  - 开始大规模前端开发或出现样式不一致问题时。

---

## 增量附录（2026-04-23，P3 执行门禁硬化）

### ADR-301: Gateway 访问策略强制化
- Context
  - 第三阶段已定义 `Gateway First`，但缺 CI 级强制执行。
- Proposed Decision
  - 增加静态门禁，阻断 `stock_processing_service` 中的 `asyncpg/SQL/_client/_db`。
- Alternatives
  - 仅依赖 Code Review 人工约束。
- Consequences
  - 边界可持续；需维护规则与豁免流程。
- Trigger
  - 发现越层访问或新增模块绕过 gateway。

### ADR-302: Snapshot Current Pointer 协议
- Context
  - 文档要求“先写新版本再切 current”，但无统一协议。
- Proposed Decision
  - 固化三步：写版本成功 -> 原子切换 current pointer -> 发布 `snapshot_built` 事件。
- Alternatives
  - 直接覆盖 current；消费端自行挑最新。
- Consequences
  - 避免半成品读取；需维护 pointer 元数据。
- Trigger
  - 快照对象重建、并发构建或回滚场景。

### ADR-303: Stream Runtime Contract 标准化
- Context
  - 仅定义 stream 名称，缺运行时语义。
- Proposed Decision
  - 冻结 `consumer_group/ack/retry/backoff/dlq/replay` 标准。
- Alternatives
  - 各服务各自实现。
- Consequences
  - 提升恢复能力与一致性；统一改造成本上升。
- Trigger
  - 出现积压、重复消费、死信增长。

### ADR-304: 双轨对账门禁标准
- Context
  - 仅有对账产物要求，缺阈值与分级。
- Proposed Decision
  - 增加对象级/字段级阈值、P0/P1/P2 失败分级与自动回滚条件。
- Alternatives
  - 人工主观判断切流。
- Consequences
  - 切流可量化可审计；需先建立阈值基线。
- Trigger
  - 任意灰度切流窗口开始前。

### ADR-305: Feature Flag Register
- Context
  - 已要求冻结开关，但缺统一台账。
- Proposed Decision
  - 建立 flag register（名称、默认值、影响路由、观测指标、回滚动作）。
- Alternatives
  - 仅在代码注释维护。
- Consequences
  - 灰度与回滚可治理；增加维护成本。
- Trigger
  - 新增或变更任何切流开关。

---

## 增量附录（2026-04-30，P4.phase0）

### ADR-P4-001: 前端 API 统一 v2 前缀与阻断策略
- Context
  - 第四阶段前端存在历史 `/api/*` 与 `/api/v2/*` 并存风险。
- Decision
  - 前端业务调用统一 `/api/v2/*`；CI 阻断非 v2 `/api/*`。
- Alternatives
  - 保留双前缀长期并存；仅人工评审约束。
- Consequences
  - 路径一致性提升；兼容层短期维护成本上升。
- Trigger
  - 出现新增非 v2 路径或线上口径不一致故障。

### ADR-P4-002: 实时链路采用 SSE-first + feed fallback
- Context
  - 当前业务以服务端单向推送为主，WS 非首要瓶颈。
- Decision
  - `/api/v2/intel/stream` 为主通道，失败自动降级 `/api/v2/intel/feed`。
- Alternatives
  - 直接全量 WS；仅轮询 feed。
- Consequences
  - 实时性与复杂度平衡；需维护重连与降级逻辑。
- Trigger
  - SSE 成功率连续低于门槛或并发模型变化。

### ADR-P4-003: frontend_bff 作为前端聚合真源
- Context
  - 前端直连多服务会扩大耦合与故障域。
- Decision
  - 前端只调用 BFF v2 接口；兼容期保留后端旧别名。
- Alternatives
  - 前端直连多后端；页面内自建聚合。
- Consequences
  - 边界清晰、回滚一致；BFF 编排复杂度增加。
- Trigger
  - 新页面接入或出现前端多服务直连趋势。

### ADR-P4-004: 发布门禁采用三重判据
- Context
  - 单一测试无法覆盖契约、回放一致性与覆盖率三类风险。
- Decision
  - 发布前必须同时满足：
  1) A/B 回放 `Disagreement=0`
  2) Layer B 覆盖率 >= 95%
  3) v2 contract tests + 路径阻断通过
- Alternatives
  - 仅接口测试；仅业务回放。
- Consequences
  - 线上回归风险下降；发布检查耗时略增。
- Trigger
  - 任一门禁失败或线上回归事件发生。

---

## 增量附录（2026-05-06，P3 新旧股票链路）

### ADR-P3-001: Layer B fade_confirmed 判定口径冻结
- Context
  - 旧链 `ThemeCycleJudgementServiceV2` 的 `fade_confirmed` 同时要求退潮分数、退潮证据数和 K 线支撑破位；新链 `SubjectCycleJudgementService` 当前主要依赖分数与证据数。
- Decision
  - 在字段级 diff 完成前，将该差异列为 P0 风险；后续必须通过 ADR 冻结为“补回 support_break”或“明确新链新口径并修订文档”二选一。
- Alternatives
  - 默认接受新链当前实现，不做专项回放。
- Consequences
  - 可避免主线误杀/误放行；短期需要增加退潮样本和字段级回放成本。
- Trigger
  - `fade_confirmed` 历史样本出现新旧链差异，或 Layer C/D 候选因周期状态漂移。

### ADR-P3-002: theme_cycle_evidence_daily 作为 Layer B 唯一 DB 真源
- Context
  - 新链已完成 evidence 生成、写入、write-verify 和 `BuildDailySnapshotJob` fail-fast 消费。
- Decision
  - 生产路径只能消费 `theme_cycle_evidence_daily`；pool metadata、proxy recency、fallback 字段只能作为 diagnostic 或离线对账，不允许静默决定周期状态。
- Alternatives
  - 保留生产 fallback 以提升短期可用性。
- Consequences
  - 数据缺失会更早失败；但周期判定可解释性和回放一致性提升。
- Trigger
  - `event_stats_hit_count=0`、`kline_quality` 异常、DB 读回为空或 write-verify 失败。

### ADR-P3-003: D1 candidate_score 公式版本化
- Context
  - 当前 `W2SCandidateService` 的候选评分与设计文档中的 5 维加权公式存在差异，且部分字段用于诊断而非正式评分。
- Decision
  - D1 评分必须引入明确版本号，并在代码、文档、回放样本中三方一致；如采用当前实现，需修订设计文档。
- Alternatives
  - 持续在代码中小步调参，不记录公式版本。
- Consequences
  - 排序解释和回放对账稳定；短期需要补充单测、样本报告和迁移说明。
- Trigger
  - 联德、维科等样本排序与业务预期不一致，或 observe/formal 分桶解释不一致。

### ADR-P3-004: LLM 与增强数据不得覆盖 A/B/C 规则真源
- Context
  - LLM 复核仍是确定性 stub，龙虎榜/资金流/游资行为尚未稳定进入新链 D 层。
- Decision
  - LLM、龙虎榜、资金流优先作为 D 层解释、复核与报告增强；不得反向覆盖 Layer A 身份、Layer B 周期和 Layer C 入池规则真源。
- Alternatives
  - 将 LLM 或增强数据作为上游强判定输入。
- Consequences
  - 规则链路稳定性更高；边界样本的智能纠偏需要后置治理。
- Trigger
  - 接入真实 LLM API、龙虎榜、资金流或游资行为数据源时。

### ADR-P3-005: 连续 replay matrix 作为第三阶段发布门禁
- Context
  - 当前 replay 已覆盖神剑、联德，但维科与反例连续矩阵不足，不能仅凭单日样本判断链路稳定。
- Decision
  - 第三阶段后续发布必须生成连续 replay matrix，至少包含交易日、样本、Layer A/B/C/D 状态、首个断点、candidate_level、reject_reason 和关键 diff。
- Alternatives
  - 继续以单个 replay 测试通过作为发布依据。
- Consequences
  - 发布前验证成本增加；但能定位断链首层并降低回归风险。
- Trigger
  - P3.next-1 之后任何涉及 evidence、cycle、strong watch、candidate、auction 的发布。

### ADR-P3-006: Replay Snapshot Manifest 作为分层回放复用依据
- Context
  - 新链已有多张快照表和中间结果，调 D1 排序或 Layer B evidence 时不应每次重算 A/B/C/D 全链。
- Decision
  - 新增 `replay_snapshot_manifest`，以 `trade_date/layer_name/snapshot_version/algorithm_version/input_hash` 判断某层是否可复用；ReplayRunner 根据模式选择复用或重建。
- Alternatives
  - 每次 replay 都 full rebuild；或仅人工判断哪些表可复用。
- Consequences
  - 回放效率和可审计性提升；需要维护 algorithm_version 与 input_hash 生成规则。
- Trigger
  - 新增 replay 模式、批量回放样本、字段级 diff 或连续交易日矩阵时。

---

## 增量附录（2026-05-08，前端调用与旧脚本服务化迁移）

### ADR-SVC-001: 旧脚本只能作为 CLI Wrapper
- Context
  - 当前前端采集链路最终由 `CollectionJobManager` 在 API 进程中拼接命令并启动旧脚本；旧脚本内部承载业务规则和 SQL。
- Decision
  - 旧脚本迁移后只能保留 argparse、参数校验和调用应用服务；业务流程必须进入 `stock_processing_service/application/services` 或 `application/jobs`。
- Alternatives
  - 继续维护脚本作为生产业务入口。
- Consequences
  - 服务可测试、可注入、可回放；短期需要抽象任务状态、外部数据源和 DB Gateway。
- Trigger
  - 任一旧脚本被前端采集、replay、recap 或定时任务作为生产入口调用时。

### ADR-SVC-002: stock_processing_service 禁止直接 SQL
- Context
  - 新链已有 Ports/Gateway 分层，但旧链 `stock_service` 与多处脚本仍直接 `asyncpg` 读写核心表。
- Decision
  - `stock_processing_service` 内不允许新增 direct SQL；所有数据库访问必须通过 Port 和 `database_service` Gateway 显式方法。
- Alternatives
  - 为迁移速度在新链内部临时复制旧 SQL。
- Consequences
  - 边界清晰、审计一致；迁移早期 Gateway 方法会增加。
- Trigger
  - 迁移旧链脚本、增加新应用服务、或新增写库路径时。

### ADR-SVC-003: 采集任务由 CollectionOrchestrator 管理
- Context
  - 现有采集任务使用内存 job 状态和 subprocess，曾出现 token 引号污染、历史日采集窗口判断等工程问题。
- Decision
  - 建立 `CollectionOrchestrator` 和分任务服务模块；前端只提交采集命令，任务状态持久化，API 不直接拼业务脚本。
- Alternatives
  - 继续扩展当前 `CollectionJobManager` 脚本编排。
- Consequences
  - 任务可恢复、可取消、可审计；需要增加 job 表、任务事件和服务接口。
- Trigger
  - 采集链路继续承载 Tushare/JYHF/龙虎榜/异动/Leader LLM/recap 等生产流程时。

### ADR-SVC-004: Layer C 迁移以旧链程序 dry-run 为真源
- Context
  - 读取 `strong_stock_watch_pool/history` 表只能证明当前表内容，不能证明旧链程序真实输出；表可能被新链或历史快照污染。
- Decision
  - Layer C 迁移必须新增旧链程序 dry-run，输出 old dry-run、legacy table、新链 shadow、production input 四路 diff。
- Alternatives
  - 直接使用 legacy table 作为旧链 C 层真源。
- Consequences
  - 能定位“旧链程序逻辑”“表数据污染”“新链 shadow 偏差”“生产输入偏差”；短期需要给旧链构建器补 dry-run。
- Trigger
  - 任何声明 Layer C 已复刻、切换生产 C 入口、或调整 C/D 候选池规模前。

### ADR-SVC-005: 前端生产链只允许一个 BFF 真源
- Context
  - 项目中同时存在 `web_app_service` 与 `frontend_bff`，当前前端主要调用 `/api/v2/*`，但双 BFF 容易导致 DTO 与路由漂移。
- Decision
  - 明确一个生产 BFF；另一路只能作为 legacy/dev/实验入口，不允许前端生产页面混用。
- Alternatives
  - 两套 BFF 长期并行并各自补兼容。
- Consequences
  - 前端契约稳定；需要清理或标记非生产路由。
- Trigger
  - 新增前端页面、改 `/api/v2/*` DTO、或迁移旧页面时。

### ADR-P3-PM-001: 日采集控制面只允许 SPS 新链单真源
- Context
  - 当前前端 `/collection` 命中 `frontend_bff` 自有 `CollectionJobManager`，该 manager 仍直接拉起旧脚本；`stock_processing_service` 同时存在新链 collection API、planner 与 runner registry。
- Decision
  - 生产日采集只能由 SPS collection API 驱动。BFF 只能做鉴权、错误转换与代理，不得持有生产任务编排器，不得直接启动 recap 旧脚本。
- Alternatives
  - 继续让 BFF 旧脚本编排与 SPS 新链编排并存。
- Consequences
  - 任务真源、job id、状态机和失败原因收口；需要迁移前端状态轮询接口并删除 BFF 旧任务入口。
- Trigger
  - `/collection` 继续承担 JYHF、Tushare、龙虎榜、异动、复盘生成等交易日日采集工作时。

### ADR-P3-PM-002: BuildPostMarketRecapJob 必须拥有 D1 构建职责
- Context
  - 第三阶段设计文档将 `BuildPostMarketRecapJob` 定义为 D1 构建驱动者，但当前代码只读取已存在 D1 候选，导致 2026-05-21 候选池为空时仍发布空复盘快照。
- Decision
  - `BuildPostMarketRecapJob` 在 Layer C refresh 后必须显式执行 D1 candidate use case，再汇总候选证据写 `post_market_recap_snapshot`。
- Alternatives
  - 继续要求其他隐式前置任务先生成 `weak_to_strong_candidate_pool`。
- Consequences
  - 盘后复盘成为自闭环 job；D1 候选池仍保留为审计与 D2 输入，但不再成为隐式外部前置。
- Trigger
  - 生成 `post_market_recap_snapshot` 或回补历史盘后复盘时。

### ADR-P3-PM-003: 盘后快照核心空产出必须显式声明质量状态
- Context
  - 2026-05-21 快照 A/B/C dependency metadata 显示完整，但 D1 候选为 0，四个核心 section 落成 `暂无...` 占位仍被发布为成功快照。
- Decision
  - 快照必须输出 `quality_status` 与 `degraded_reasons`。当强势池与主线资金上下文存在而 D1 驱动 section 为空时，不得 silent success。
- Alternatives
  - 继续把空 section 当正常内容，由页面展示占位文案。
- Consequences
  - 控制台和页面能区分策略无候选、依赖缺失、链路退化；需要补质量门禁与回归样本。
- Trigger
  - 盘后复盘生成、历史回补或发布 Notion 前。

### ADR-P3-PM-002 Supersession Note: Recap 不拥有 D1 候选生成职责
- Context
  - 2026-05-21 复核时，业务边界被再次澄清：每日复盘提供数据准备，D1 候选池由弱转强 Stage1 盘后选股显式生成。
- Decision
  - `ADR-P3-PM-002` 不作为最终职责裁决，由 `ADR-P3-PM-004` 替代。第三阶段主文档中“BuildPostMarketRecapJob 驱动 D1”的歧义表述需要修订。
- Alternatives
  - 继续把 D1 隐式塞回 recap job。
- Consequences
  - 复盘生成链与弱转强选股链解耦；需要修复新链 report builder 的 section 数据源。
- Trigger
  - 继续设计 `/recap`、弱转强 Stage1 或 collection job 职责时。

### ADR-P3-PM-004: 复盘 section 必须由复盘事实驱动而非 D1 候选驱动
- Context
  - 旧 `RecapService` 的主线、强势股、观察清单、资金 top section 分别来自主线/周期/leader/资金/异动事实；当前新链 builder 却把四段绑定到 D1 `top_candidates/formal_candidates`，导致 2026-05-21 D1 为空时四段全空。
- Decision
  - `post_market_recap_snapshot.report.sections` 的复盘主体必须从新链复盘事实对象构建。D1 候选只能作为弱转强选股结果或可选补充 section，不得作为主线与强势股复盘 section 的唯一输入。
- Alternatives
  - 继续让 recap builder 以 D1 候选作为复盘骨架。
- Consequences
  - 复盘在没有执行弱转强 Stage1 时仍能完整展示日复盘；需要补 section source contract 与 2026-05-21 回归样本。
- Trigger
  - 构建 `post_market_recap_snapshot` 或调整 recap report builder 时。

# ADR List

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
  - 若把资讯直接当成“涨停真因”，会产生高误导性结论。
- Proposed Decision
  - 对涨停原因仅输出候选归因、置信度和支撑证据，不输出确定性真因。
- Alternatives
  - 直接输出“该股涨停原因就是某条新闻”。
- Consequences
  - 解释性更诚实；产品文案复杂度上升。
- Trigger
  - 复盘系统开始输出个股涨停原因时。

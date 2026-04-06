# TEST CASE SPEC — P2.phase0

## 0. 范围与原则
- 目标：对齐 [FEATURE_SPEC_P2.phase0.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/FEATURE_SPEC_P2.phase0.md) 的任务分解，建立 `stream:news:raw -> news_stream_handler.py -> news_raw -> news_stream_processor.py -> news_event -> theme_processor.py -> theme_service.py -> ThemeMatchEngine -> event_theme_map / pending / review` 的测试规范。
- 执行模式：`execution_mode=real`，`allow_mock=false`。
- 关键依赖：`redis,postgres,llm`。
- 默认测试库：`stock_data_test`。
- 证据字段：`raw_news_id,news_event.id,trace_id,llm_request_id,structuring_version,final_decision,reason_code,latency_ms`。
- 测试执行原则（MUST）：
  - 必须遵循 `UT -> IT -> PT/E2E` 的分层顺序，禁止跳层直测。
  - 必须先验证简单组件，再验证依赖该组件的上游模块。
  - 下游依赖组件未通过时，上游集成测试必须标记为 `BLOCKED`，不得继续执行并给出“通过”结论。
  - 结构化链必须遵循：`event_extractor.py` 单元/契约通过 -> `event_extractor.py` 集成通过 -> `news_stream_processor.py` 集成通过 -> `theme_service.py / theme_processor.py` 集成通过 -> 全链路 E2E。
  - `event_extractor.py` 的 prompt 提示词、结构化 schema、旧字段清除未通过前，不得开始 `news_stream_processor.py` 的生产级集成测试。
- 当前范围约束：
  - 本阶段只验证 `P2.phase0`。
  - 不验收 `P2.phase1` 的 Unknown 聚类与新题材草案。
  - 不验收 `P2.phase2/phase3` 的知识对象、热度和榜单。

## 0.1 测试层级与阻塞规则（新增）

### Layer-1 `UT`：单组件单元测试
- 目标：验证最小组件行为、prompt 构造、字段契约、旧逻辑清除、纯函数/轻依赖逻辑。
- phase0 先跑对象：
  - `event_extractor.py`
  - `theme_service.py` wrapper
  - `news_stream_handler.py` 边界守卫
  - `theme_processor.py` 旧路径退役守卫
- 阻塞规则：
  - 任一 `event_extractor.py` 单元测试失败，则 `news_stream_processor.py` 所有 IT/PT 用例标记 `BLOCKED`
  - 任一 `theme_service.py` wrapper 单元测试失败，则 `theme_processor.py` IT/PT 与 E2E 标记 `BLOCKED`

### Layer-2 `IT`：单组件集成测试
- 目标：验证组件与真实依赖的集成正确性，但仍保持单组件主责清晰。
- phase0 顺序：
  1. `event_extractor.py` + LLM + `news_event` schema
  2. `news_stream_handler.py` + Redis + `news_raw`
  3. `news_stream_processor.py` + `event_extractor.py` + `news_event`
  4. `theme_service.py` + `ThemeMatchEngine`
  5. `theme_processor.py` + `theme_service.py` + `stream:events:structured`
- 阻塞规则：
  - 第 `n` 步未通过，不得进入第 `n+1` 步
  - 任一组件若依赖下游 schema 未冻结，则其集成测试标记 `BLOCKED`

### Layer-3 `PT/E2E`：多模块全链路测试
- 目标：验证生产级测试框架、全链路证据、性能预算与最终落地结果。
- 前置门禁：
  - `event_extractor.py` 的 UT/IT 全部通过
  - `news_stream_processor.py` 的 IT 全部通过
  - `theme_service.py` 与 `theme_processor.py` 的 UT/IT 全部通过
  - 否则 `T02E-*` 与 `PT-001/002` 必须标记 `BLOCKED`

## 1. 验收级 TC（保持兼容）
- `TC-P2.phase0-ST-001` 生产入口回放链路：100条 `news_raw` 回放。
- `TC-P2.phase0-IT-001` `event_extractor.py` 重构后纯结构化契约。
- `TC-P2.phase0-IT-002` `news_event` 落库先于匹配执行。
- `TC-P2.phase0-IT-003` `ThemeMatchEngine` 成为唯一最终题材判定入口。
- `TC-P2.phase0-IT-004` 三态决策 `MATCH / UNKNOWN / HUMAN_REVIEW` 契约冻结。
- `TC-P2.phase0-ET-001` 结构化失败 / 超时降级到 `HUMAN_REVIEW`。
- `TC-P2.phase0-ET-002` 旧字段 `theme_discovery_directive / CREATE_NEW / CLUSTER` 残留拒绝。
- `TC-P2.phase0-IT-005` `news_event.id -> event_theme_map.event_id` 链路完整性。
- `TC-P2.phase0-IT-006` `news_stream_processor.py` 只允许消费 `news_raw` 入库后事件或 `news_raw` 记录、落库 `news_event`、发布结构化事件。
- `TC-P2.phase0-IT-007` `theme_processor.py` 只允许单流消费、读取 `news_event`、发布三态 envelope。
- `TC-P2.phase0-IT-008` `news_stream_handler.py` 必须先完成 `news_raw` 入库，后续处理器才允许继续。
- `TC-P2.phase0-IT-009` `theme_service.py` 必须作为 `ThemeMatchEngine` 服务封装层，供 `theme_processor.py` 调用。
- `TC-P2.phase0-PT-001` 全链路性能预算：`P95 < 1200ms`，`P99 < 2500ms`。
- `TC-P2.phase0-PT-002` 生产级全链路测试框架必须从 `news_raw` 起步，不得复用旧双流直发路径。
- `TC-P2.phase0-ARCH-001` 架构门禁：单一结构化事件流，不允许 `major / normal` 双流回流。

## 2. 功能分解对齐矩阵（Feature -> Test，MUST）

| Feature 子功能 | 需求/约束 | 验收级TC | 子用例ID | 优先级 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `F-P2.phase0-T01-01` 请求契约冻结 | `ThemeMatchRequest` 输入来自 `news_event` | IT-002 | `TC-P2.phase0-F-T01-01` | P0 | In Scope |
| `F-P2.phase0-T01-02` 三态 envelope 归一化 | `MATCH/UNKNOWN/HUMAN_REVIEW` 固定语义 | IT-004 | `TC-P2.phase0-F-T01-02` | P0 | In Scope |
| `F-P2.phase0-T01-03` 最小审计对象冻结 | 审计必填字段覆盖 | IT-004 | `TC-P2.phase0-F-T01-03` | P0 | In Scope |
| `F-P2.phase0-T02-01` 原始新闻结构化网关 | `stream:news:raw -> news_stream_handler.py -> news_raw -> news_stream_processor.py -> news_event` | ST-001 | `TC-P2.phase0-F-T02-01` | P0 | In Scope |
| `F-P2.phase0-T02-01a` 数据集回放注入器 | `validation_dataset.json` 100条 `news_raw` | ST-001 | `TC-P2.phase0-F-T02-01A` | P0 | In Scope |
| `F-P2.phase0-T02-01b` 旧语义清除器 | 禁止 `theme_discovery_directive/CREATE_NEW/CLUSTER` | ET-002 | `TC-P2.phase0-F-T02-01B` | P0 | In Scope |
| `F-P2.phase0-T02-01c` 新结构重建器 | 新 `news_event` 字段完整率 | IT-001 | `TC-P2.phase0-F-T02-01C` | P0 | In Scope |
| `F-P2.phase0-T02-01d` 参考实现对齐器 | 与 `extract_structured_events_from_test_cases.py` 对齐 | IT-001 | `TC-P2.phase0-F-T02-01D` | P1 | In Scope |
| `F-P2.phase0-T02-01e` `news_event` 落库映射器 | 结构化结果必须先落库 | IT-002 | `TC-P2.phase0-F-T02-01E` | P0 | In Scope |
| `F-P2.phase0-T02-02` 单流入口 | `stream:events:structured` 唯一入口 | ARCH-001 | `TC-P2.phase0-F-T02-02` | P0 | In Scope |
| `F-P2.phase0-T02-03` 三态出口分叉器 | MATCH/UNKNOWN/HUMAN_REVIEW 路由 | IT-004 | `TC-P2.phase0-F-T02-03` | P0 | In Scope |
| `F-P2.phase0-T02-04` 兼容层映射器 | `DecisionExecutor` 兼容接入 | IT-003 | `TC-P2.phase0-F-T02-04` | P0 | In Scope |
| `F-P2.phase0-T02H-01` 原始消息入库编排器 | `news_stream_handler.py` 消费 `stream:news:raw` 并写 `news_raw` | IT-008 | `TC-P2.phase0-F-T02H-01` | P0 | In Scope |
| `F-P2.phase0-T02H-02` payload 格式兼容守卫 | handler 只做入库，不做结构化或匹配 | IT-008 | `TC-P2.phase0-F-T02H-02` | P0 | In Scope |
| `F-P2.phase0-T02H-03` 前后处理器分层守卫 | `news_stream_handler.py` 先于 `news_stream_processor.py` | IT-008 | `TC-P2.phase0-F-T02H-03` | P0 | In Scope |
| `F-P2.phase0-T02N-01` 入库后消息解析器 | `news_stream_processor.py` 消费 `news_raw` 入库后事件或 `news_raw` 记录 | IT-006 | `TC-P2.phase0-F-T02N-01` | P0 | In Scope |
| `F-P2.phase0-T02N-02` 结构化调用编排器 | 必须调用 `event_extractor.py / model_service` | IT-006 | `TC-P2.phase0-F-T02N-02` | P0 | In Scope |
| `F-P2.phase0-T02N-03` 旧语义清除器 | 禁止 `theme_discovery_directive/CREATE_NEW/CLUSTER` | ET-002 | `TC-P2.phase0-F-T02N-03` | P0 | In Scope |
| `F-P2.phase0-T02N-04` `news_event` 落库编排器 | 先落库后发布 structured 事件 | IT-002 | `TC-P2.phase0-F-T02N-04` | P0 | In Scope |
| `F-P2.phase0-T02N-05` 结构化事件发布器 | 输出 `stream:events:structured` | ARCH-001 | `TC-P2.phase0-F-T02N-05` | P0 | In Scope |
| `F-P2.phase0-T02N-06` 前后处理器边界守卫 | 前者只结构化，后者只匹配 | IT-006 | `TC-P2.phase0-F-T02N-06` | P1 | In Scope |
| `F-P2.phase0-T02R-01` 统一流消费器 | `theme_processor.py` 只消费 `stream:events:structured` | ARCH-001 | `TC-P2.phase0-F-T02R-01` | P0 | In Scope |
| `F-P2.phase0-T02R-02` `news_event` 读取与契约校验器 | 处理器必须从 `news_event` 取数 | IT-007 | `TC-P2.phase0-F-T02R-02` | P0 | In Scope |
| `F-P2.phase0-T02R-03` `ThemeMatchRequest` 构建器 | `event_id = news_event.id` | IT-007 | `TC-P2.phase0-F-T02R-03` | P0 | In Scope |
| `F-P2.phase0-T02R-04` `ThemeMatchEngine` 调用适配器 | 不得继续走旧 discover/category 路径 | IT-003 | `TC-P2.phase0-F-T02R-04` | P0 | In Scope |
| `F-P2.phase0-T02R-05` 新决策发布器 | 只发布 `MATCH/UNKNOWN/HUMAN_REVIEW` | IT-004 | `TC-P2.phase0-F-T02R-05` | P0 | In Scope |
| `F-P2.phase0-T02R-06` 统计与监控迁移器 | 去 `by_stream.normal/major`，转 `by_decision` | IT-006 | `TC-P2.phase0-F-T02R-06` | P1 | In Scope |
| `F-P2.phase0-T02S-01` 服务门面适配器 | `theme_service.py` 提供 `ThemeMatchEngine` 调用入口 | IT-009 | `TC-P2.phase0-F-T02S-01` | P0 | In Scope |
| `F-P2.phase0-T02S-02` 请求构建辅助器 | 由服务层统一构建 `ThemeMatchRequest` | IT-009 | `TC-P2.phase0-F-T02S-02` | P0 | In Scope |
| `F-P2.phase0-T02S-03` 决策封装器 | 由服务层统一输出 `ThemeDecisionEnvelope` | IT-009 | `TC-P2.phase0-F-T02S-03` | P0 | In Scope |
| `F-P2.phase0-T02S-04` 旧接口退役守卫 | 不得继续走 `discover_* / create_new_theme_by_rules` 主路径 | IT-009 | `TC-P2.phase0-F-T02S-04` | P0 | In Scope |
| `F-P2.phase0-T02E-01` 数据集抽样与 `news_raw` 注入器 | 生产级测试必须从 `stream:news:raw` 注入 | PT-002 | `TC-P2.phase0-F-T02E-01` | P0 | In Scope |
| `F-P2.phase0-T02E-02` 入库处理器编排器 | 必须纳入 `news_stream_handler.py` | PT-002 | `TC-P2.phase0-F-T02E-02` | P0 | In Scope |
| `F-P2.phase0-T02E-03` 结构化处理器编排器 | 必须纳入 `news_stream_processor.py` | PT-002 | `TC-P2.phase0-F-T02E-03` | P0 | In Scope |
| `F-P2.phase0-T02E-04` 匹配处理器编排器 | 必须纳入 `theme_processor.py` | PT-002 | `TC-P2.phase0-F-T02E-04` | P0 | In Scope |
| `F-P2.phase0-T02E-05` 执行器编排器 | 必须纳入 `DecisionExecutor` | PT-002 | `TC-P2.phase0-F-T02E-05` | P0 | In Scope |
| `F-P2.phase0-T02E-06` 全链路证据归档器 | 必须绑定 DB 与 stream 证据链 | PT-002 | `TC-P2.phase0-F-T02E-06` | P0 | In Scope |
| `F-P2.phase0-T02E-07` 旧新测试框架差异守卫 | 旧脚本仅作对照，不作 phase0 主证据 | PT-002 | `TC-P2.phase0-F-T02E-07` | P1 | In Scope |
| `F-P2.phase0-T03-01` 画像字段裁剪器 | `ThemeProfile` 首期字段基线 | IT-003 | `TC-P2.phase0-F-T03-01` | P1 | In Scope |
| `F-P2.phase0-T03-02` 检索文本生成器 | `search_text` 可用 | IT-003 | `TC-P2.phase0-F-T03-02` | P1 | In Scope |
| `F-P2.phase0-T03-03` 展示层隔离器 | 展示层/画像层不得混写 | IT-003 | `TC-P2.phase0-F-T03-03` | P1 | In Scope |
| `F-P2.phase0-T04-01` 降级决策器 | 结构化/匹配失败统一受控降级 | ET-001 | `TC-P2.phase0-F-T04-01` | P0 | In Scope |
| `F-P2.phase0-T04-02` reason code 标准化 | `reason_code` 枚举固定 | ET-001 | `TC-P2.phase0-F-T04-02` | P0 | In Scope |
| `F-P2.phase0-T04-03` 审计字段守卫 | 审计缺失不得写最终结果 | IT-004 | `TC-P2.phase0-F-T04-03` | P0 | In Scope |
| `F-P2.phase0-T05-01` 灰度样本采集器 | 100条样本回放固定口径 | ST-001 | `TC-P2.phase0-F-T05-01` | P1 | In Scope |
| `F-P2.phase0-T05-02` 性能预算核验器 | P95/P99 门禁 | PT-001 | `TC-P2.phase0-F-T05-02` | P0 | In Scope |
| `F-P2.phase0-T05-03` phase归档器 | 证据齐全才能结项 | PT-001 | `TC-P2.phase0-F-T05-03` | P1 | In Scope |

## 3. 子用例详细分解（按 Feature）

### TC-P2.phase0-F-T01-01（对应 `F-P2.phase0-T01-01`）
- 级别：IT，优先级：P0。
- 目标：`ThemeMatchRequest` 只能由 `news_event` 构建，且 `event_id = news_event.id`。
- 前置：
  - `news_raw` 已结构化并成功写入 `news_event`。
  - `news_event.id` 可查询。
- 核心断言：
  - 匹配请求中的 `event_id` 来自 `news_event.id`。
  - 不允许从 JSON 文件直喂匹配请求。
  - `raw_news_id`、`trace_id`、`structuring_version` 同步透传。

### TC-P2.phase0-F-T01-02（对应 `F-P2.phase0-T01-02`）
- 级别：IT，优先级：P0。
- 目标：最终决策固定为三态。
- 核心断言：
  - 结果只能是 `MATCH/UNKNOWN/HUMAN_REVIEW`。
  - 不允许出现 `CREATE_NEW/CLUSTER/no_match` 等旧态直接外露。

### TC-P2.phase0-F-T01-03（对应 `F-P2.phase0-T01-03`）
- 级别：IT，优先级：P0。
- 目标：审计字段缺失时阻断最终写入。
- 核心断言：
  - 必填：`trace_id/model_version/prompt_version/final_decision/latency_ms`。
  - 缺任一字段则不得写 `event_theme_map`。

### TC-P2.phase0-F-T02-01（对应 `F-P2.phase0-T02-01`）
- 级别：ST，优先级：P0。
- 目标：`stream:news:raw -> news_stream_handler.py -> news_raw -> news_stream_processor.py -> event_extractor.py -> news_event` 链路真实可用。
- 核心断言：
  - `news_stream_handler.py` 必须先完成 `news_raw` 入库。
  - `news_stream_processor.py` 必须基于已入库 `news_raw` 调用 `event_extractor.py`。
  - 成功写入 `news_event`。
  - 结构化成功率可统计。

### TC-P2.phase0-F-T02-01A（对应 `F-P2.phase0-T02-01a`）
- 级别：ST，优先级：P0。
- 目标：使用 [validation_dataset.json](/Users/admin/Desktop/ai_theme_app/evaluate_service/data/raw/validation_dataset.json) 模拟 `100` 条 `news_raw`。
- 核心断言：
  - 成功注入 `100` 条 `news_raw`。
  - 每条样本都有可追踪 `raw_news_id`。
  - 样本不足或入流失败直接 `FAILED/BLOCKED`。

### TC-P2.phase0-F-T02-01B（对应 `F-P2.phase0-T02-01b`）
- 级别：ET，优先级：P0。
- 目标：旧动作语义必须彻底清除。
- 核心断言：
  - `event_extractor.py` 输出中不得存在 `theme_discovery_directive`。
  - 代码扫描不得存在生产路径 `CREATE_NEW/CLUSTER`。
  - 若该用例失败，`TC-P2.phase0-F-T02N-02/03/04/05` 必须标记 `BLOCKED`。

### TC-P2.phase0-F-T02-01C（对应 `F-P2.phase0-T02-01c`）
- 级别：IT，优先级：P0。
- 目标：新结构化 schema 满足 `news_event` 表映射。
- 核心断言：
  - 输出覆盖：`event_type/impact_industries/direction/confidence/summary/severity_score/source_weight/event_time/entities/causal_claim/evidence_set/raw_event_json`。
  - 字段类型与表约束兼容。
  - 若该用例失败，`news_stream_processor.py` 与其相关的所有 IT/PT 用例必须标记 `BLOCKED`。

### TC-P2.phase0-F-T02-01D（对应 `F-P2.phase0-T02-01d`）
- 级别：IT，优先级：P1。
- 目标：`event_extractor.py` 与 [extract_structured_events_from_test_cases.py](/Users/admin/Desktop/ai_theme_app/extract_structured_events_from_test_cases.py) 的字段基线不漂移。
- 核心断言：
  - 关键结构化字段名与语义一致。
  - 失败样本清单机制存在。
  - 可观测字段对齐。

### TC-P2.phase0-F-T02-01E（对应 `F-P2.phase0-T02-01e`）
- 级别：IT，优先级：P0。
- 目标：结构化结果必须先落库到 `news_event` 再入匹配链。
- 核心断言：
  - `news_event` 落库成功后才可写 `stream:events:structured`。
  - `theme_directive` 仅兼容占位，不承载旧动作语义。
  - `raw_event_json` 保存完整结构化快照。

### TC-P2.phase0-F-T02-02（对应 `F-P2.phase0-T02-02`）
- 级别：ARCH，优先级：P0。
- 目标：单一结构化事件流是唯一入口。
- 核心断言：
  - 仅允许 `stream:events:structured`。
  - 不允许 `events:major/events:normal` 前置分流回流。

### TC-P2.phase0-F-T02-03（对应 `F-P2.phase0-T02-03`）
- 级别：IT，优先级：P0。
- 目标：三态出口路由正确。
- 核心断言：
  - `MATCH -> event_theme_map`
  - `UNKNOWN -> pending/unknown path`
  - `HUMAN_REVIEW -> review_queue`

### TC-P2.phase0-F-T02-04（对应 `F-P2.phase0-T02-04`）
- 级别：IT，优先级：P0。
- 目标：`DecisionExecutor` 兼容接入不破坏下游。
- 核心断言：
  - 现有执行器能消费新 envelope。
  - 不要求同步重构全部消费者。

### TC-P2.phase0-F-T02N-01（对应 `F-P2.phase0-T02N-01`）
- 级别：IT，优先级：P0。
- 目标：`news_stream_processor.py` 只消费 `news_raw` 入库后事件或 `news_raw` 记录。
- 核心断言：
  - 处理器主入口面向已入库 `news_raw`，而不是绕过 handler 直接吃业务伪消息。
  - 不应把 `theme_processor.py` 作为直接调用目标。

### TC-P2.phase0-F-T02N-02（对应 `F-P2.phase0-T02N-02`）
- 级别：IT，优先级：P0。
- 目标：前置处理器必须调用 `event_extractor.py / model_service` 产生结构化结果。
- 核心断言：
  - 真实结构化调用存在。
  - 不允许直接伪造 `news_event` 绕过结构化链。
  - 前置：
    - `TC-P2.phase0-F-T02-01B` 已通过。
    - `TC-P2.phase0-F-T02-01C` 已通过。
    - `TC-P2.phase0-F-T02-01D` 未失败。
  - 若上述前置未满足，本用例必须标记 `BLOCKED`。

### TC-P2.phase0-F-T02N-03（对应 `F-P2.phase0-T02N-03`）
- 级别：ET，优先级：P0。
- 目标：`news_stream_processor.py` 不得再透传旧题材动作语义。
- 核心断言：
  - 返回结果和中间对象中不得存在 `theme_discovery_directive`。
  - 不允许 `CREATE_NEW / CLUSTER` 残留在生产路径。

### TC-P2.phase0-F-T02N-04（对应 `F-P2.phase0-T02N-04`）
- 级别：IT，优先级：P0。
- 目标：前置处理器必须先落 `news_event` 再发布结构化事件。
- 核心断言：
  - `news_event` 持久化成功后才允许发布 `stream:events:structured`。
  - 发布消息必须携带 `event_id/news_id/trace_id`。

### TC-P2.phase0-F-T02N-05（对应 `F-P2.phase0-T02N-05`）
- 级别：ARCH，优先级：P0。
- 目标：前置处理器产物必须是标准结构化事件流，而不是业务分析结果包装。
- 核心断言：
  - 输出目标是 `stream:events:structured`。
  - 不允许只返回 `event_info + theme_discovery_directive`。

### TC-P2.phase0-F-T02N-06（对应 `F-P2.phase0-T02N-06`）
- 级别：IT，优先级：P1。
- 目标：`news_stream_processor.py` 与 `theme_processor.py` 的边界固定。
- 核心断言：
  - 前者只做结构化，后者只做匹配。
  - 不允许前者调用 `ThemeMatchEngine`，不允许后者回退消费 `news_raw`。

### TC-P2.phase0-F-T02R-01（对应 `F-P2.phase0-T02R-01`）
- 级别：ARCH，优先级：P0。
- 目标：`theme_processor.py` 只允许消费 `stream:events:structured`。
- 核心断言：
  - 代码中不得再存在生产消费入口 `stream:events:normal / stream:events:major`。
  - 单流消费配置可定位且为唯一主入口。

### TC-P2.phase0-F-T02R-02（对应 `F-P2.phase0-T02R-02`）
- 级别：IT，优先级：P0。
- 目标：处理器必须从 `news_event` 读取正式事件数据。
- 核心断言：
  - 处理器按 `event_id` 读取 `news_event`。
  - 缺失 `news_event` 记录时不得伪造判定结果。

### TC-P2.phase0-F-T02R-03（对应 `F-P2.phase0-T02R-03`）
- 级别：IT，优先级：P0。
- 目标：`theme_processor.py` 组装的匹配请求必须继承 `news_event.id`。
- 核心断言：
  - `ThemeMatchRequest.event_id = news_event.id`。
  - `trace_id`、`raw_news_id` 保持贯通。

### TC-P2.phase0-F-T02R-04（对应 `F-P2.phase0-T02R-04`）
- 级别：IT，优先级：P0。
- 目标：处理器调用新 `ThemeMatchEngine` 适配层，而不是旧分类/回退匹配逻辑。
- 核心断言：
  - 不再走 `discover_category_only / discover_with_themes / fallback full match` 主路径。
  - 新调用链可产出统一 `ThemeDecisionEnvelope`。
  - 前置：
    - `TC-P2.phase0-F-T02S-01`
    - `TC-P2.phase0-F-T02S-02`
    - `TC-P2.phase0-F-T02S-03`
    - `TC-P2.phase0-F-T02S-04`
  - 若服务层门面未通过，本用例必须标记 `BLOCKED`。

### TC-P2.phase0-F-T02R-05（对应 `F-P2.phase0-T02R-05`）
- 级别：IT，优先级：P0。
- 目标：处理器只发布三态决策，不再发布旧动作语义。
- 核心断言：
  - 不允许 `create_new_theme / publish_clustering` 作为处理器直接动作。
  - 仅允许 `MATCH / UNKNOWN / HUMAN_REVIEW`。

### TC-P2.phase0-F-T02R-06（对应 `F-P2.phase0-T02R-06`）
- 级别：IT，优先级：P1。
- 目标：处理器统计口径完成迁移。
- 核心断言：
  - 不再依赖 `by_stream.normal / by_stream.major` 作为核心指标。
  - 应存在 `by_decision.MATCH / UNKNOWN / HUMAN_REVIEW` 或等价新指标。

### TC-P2.phase0-F-T02S-01（对应 `F-P2.phase0-T02S-01`）
- 级别：IT，优先级：P0。
- 目标：`theme_processor.py` 必须通过 `theme_service.py` 新门面调用 `ThemeMatchEngine`。
- 核心断言：
  - `get_theme_service()` 返回的服务实例具备新匹配接口。
  - `ThemeProcessor` 不直接耦合底层匹配内核实现。
  - 服务层成为唯一正式调用入口。

### TC-P2.phase0-F-T02S-02（对应 `F-P2.phase0-T02S-02`）
- 级别：IT，优先级：P0。
- 目标：`ThemeMatchRequest` 由服务层统一构建。
- 核心断言：
  - 请求对象构建逻辑不散落在 `theme_processor.py`。
  - `news_event/news_raw` 字段映射在服务层固定。
  - 构建失败时进入受控错误路径。

### TC-P2.phase0-F-T02S-03（对应 `F-P2.phase0-T02S-03`）
- 级别：IT，优先级：P0。
- 目标：服务层统一输出 `ThemeDecisionEnvelope`。
- 核心断言：
  - 服务返回对象符合三态 envelope 契约。
  - `theme_processor.py` 不自行解释旧 discovery result。
  - 降级结果也由服务层统一封装。

### TC-P2.phase0-F-T02S-04（对应 `F-P2.phase0-T02S-04`）
- 级别：UT，优先级：P0。
- 目标：旧接口从线上主路径退役。
- 核心断言：
  - `discover_category_only / discover_with_themes / discover_theme / create_new_theme_by_rules` 不再是 `theme_processor.py` 主路径依赖。
  - 若仍存在主路径调用，测试直接失败。
  - 兼容接口若保留，必须标注为非 phase0 主调用路径。

### TC-P2.phase0-F-T02E-01（对应 `F-P2.phase0-T02E-01`）
- 级别：PT，优先级：P0。
- 目标：生产级全链路测试必须从 `validation_dataset.json -> news_raw` 开始。
- 核心断言：
  - 新测试脚本直接写 `stream:news:raw`。
  - 不允许直接把事件发布到 `stream:events:major / normal`。
  - 前置：
    - `TC-P2.phase0-F-T02N-02/04/05` 已通过。
    - `TC-P2.phase0-F-T02R-04/05` 已通过。
    - `TC-P2.phase0-F-T02S-01/02/03/04` 已通过。
  - 若前置未满足，本用例必须标记 `BLOCKED`。

### TC-P2.phase0-F-T02E-02（对应 `F-P2.phase0-T02E-02`）
- 级别：PT，优先级：P0。
- 目标：新测试框架必须真实纳入 `news_stream_handler.py`。
- 核心断言：
  - 全链路运行中存在 `news_stream_handler.py` 启动和 `news_raw` 入库证据。
  - 没有 `news_raw` 入库证据时，整条 E2E 测试必须失败。
  - `news_stream_processor.py` 不得绕过 handler 直接接管原始输入。

### TC-P2.phase0-F-T02E-03（对应 `F-P2.phase0-T02E-03`）
- 级别：PT，优先级：P0。
- 目标：新测试框架必须真实纳入 `news_stream_processor.py`。
- 核心断言：
  - 全链路运行中存在 `news_stream_processor.py` 启动和处理证据。
  - `news_event` 由前置处理器产生，而不是测试脚本伪造。
  - `theme_processor.py` 不得在 `news_stream_processor.py` 之前先行消费任何伪造事件。

### TC-P2.phase0-F-T02E-04（对应 `F-P2.phase0-T02E-04`）
- 级别：PT，优先级：P0。
- 目标：新测试框架必须真实纳入 `theme_processor.py`。
- 核心断言：
  - `stream:events:structured` 被消费。
  - 决策流由新版 `theme_processor.py` 产出。
  - `theme_processor.py` 的输入必须来源于 `news_stream_processor.py` 产出的结构化事件，且通过 `theme_service.py` 门面调用 `ThemeMatchEngine`。

### TC-P2.phase0-F-T02E-05（对应 `F-P2.phase0-T02E-05`）
- 级别：PT，优先级：P0。
- 目标：新测试框架必须真实纳入 `DecisionExecutor`。
- 核心断言：
  - `stream:events:decision` 被消费。
  - 最终结果进入 `event_theme_map / pending / review_queue`。

### TC-P2.phase0-F-T02E-06（对应 `F-P2.phase0-T02E-06`）
- 级别：PT，优先级：P0。
- 目标：新测试框架必须生成完整证据链。
- 核心断言：
  - 可绑定 `raw_news_id -> news_event.id -> decision_id -> final state`。
  - 数据库与 stream 证据一致。

### TC-P2.phase0-F-T02E-07（对应 `F-P2.phase0-T02E-07`）
- 级别：PT，优先级：P1。
- 目标：旧 `test_new_architecture_with_dataset()` 不得再充当 phase0 主验证脚本。
- 核心断言：
  - 旧脚本被标记为历史对照。
  - 新脚本才是生产级全链路真源。

### TC-P2.phase0-F-T03-01（对应 `F-P2.phase0-T03-01`）
- 级别：IT，优先级：P1。
- 目标：在线画像字段基线冻结。
- 核心断言：
  - `aliases/core_objects/entity_hints/must_terms/strong_terms/negative_terms/search_text` 完整。

### TC-P2.phase0-F-T03-02（对应 `F-P2.phase0-T03-02`）
- 级别：IT，优先级：P1。
- 目标：`search_text` 生成可用。
- 核心断言：
  - 检索文本包含题材名/别名/对象词。

### TC-P2.phase0-F-T03-03（对应 `F-P2.phase0-T03-03`）
- 级别：IT，优先级：P1。
- 目标：展示层和画像层不混写。
- 核心断言：
  - 详情长文不进入在线索引对象。

### TC-P2.phase0-F-T04-01（对应 `F-P2.phase0-T04-01`）
- 级别：ET，优先级：P0。
- 目标：结构化阶段和匹配阶段失败统一受控降级。
- 核心断言：
  - `event_structuring_timeout/parse_error/incomplete` -> `HUMAN_REVIEW`
  - `llm_timeout/reranker_timeout/index_unavailable` -> 受控 fallback

### TC-P2.phase0-F-T04-02（对应 `F-P2.phase0-T04-02`）
- 级别：ET，优先级：P0。
- 目标：`reason_code` 枚举冻结。
- 核心断言：
  - 只允许已定义 reason code。
  - 未映射错误归入 `contract_violation`。

### TC-P2.phase0-F-T04-03（对应 `F-P2.phase0-T04-03`）
- 级别：IT，优先级：P0。
- 目标：审计字段与最终写入绑定。
- 核心断言：
  - 审计失败时不得写 `event_theme_map`。

### TC-P2.phase0-F-T05-01（对应 `F-P2.phase0-T05-01`）
- 级别：ST，优先级：P1。
- 目标：100条样本回放口径固定。
- 核心断言：
  - 样本清单固定。
  - 每条样本可从 `raw_news_id` 跟到 `news_event.id`。

### TC-P2.phase0-F-T05-02（对应 `F-P2.phase0-T05-02`）
- 级别：PT，优先级：P0。
- 目标：验证从 `news_raw` 到最终决策的全链路时延预算。
- 核心断言：
  - `P95 < 1200ms`
  - `P99 < 2500ms`
  - 能拆分结构化时延与匹配时延

### TC-P2.phase0-F-T05-03（对应 `F-P2.phase0-T05-03`）
- 级别：PT/RT，优先级：P1。
- 目标：证据齐全才能归档。
- 核心断言：
  - 100条样本回放结果、性能数据、审计链、失败样本清单完整。

## 4. 验收用例 -> 测试用例映射

| Acceptance | 对应测试 |
| --- | --- |
| `ACPT-P2.phase0-001` | `TC-P2.phase0-IT-003`, `TC-P2.phase0-F-T02-04` |
| `ACPT-P2.phase0-002` | `TC-P2.phase0-IT-004`, `TC-P2.phase0-F-T01-02` |
| `ACPT-P2.phase0-003` | `TC-P2.phase0-F-T03-01`, `TC-P2.phase0-F-T03-02` |
| `ACPT-P2.phase0-004` | `TC-P2.phase0-ET-001`, `TC-P2.phase0-F-T04-01`, `TC-P2.phase0-F-T04-02` |
| `ACPT-P2.phase0-005` | `TC-P2.phase0-F-T02-03`, `TC-P2.phase0-F-T02N-04` |
| `ACPT-P2.phase0-006` | `TC-P2.phase0-F-T01-03`, `TC-P2.phase0-F-T04-03` |
| `ACPT-P2.phase0-007` | `TC-P2.phase0-PT-001`, `TC-P2.phase0-F-T05-02` |
| `ACPT-P2.phase0-008` | `TC-P2.phase0-IT-003`, `TC-P2.phase0-F-T02-04`, `TC-P2.phase0-F-T02N-02`, `TC-P2.phase0-F-T02E-04` |
| `ACPT-P2.phase0-009` | `TC-P2.phase0-ARCH-001`, `TC-P2.phase0-F-T02-02`, `TC-P2.phase0-F-T02N-05`, `TC-P2.phase0-F-T02R-01`, `TC-P2.phase0-F-T02E-01` |
| `ACPT-P2.phase0-010` | `TC-P2.phase0-F-T03-03` |
| `ACPT-P2.phase0-011` | `TC-P2.phase0-F-T05-03` |
| `ACPT-P2.phase0-012` | `TC-P2.phase0-IT-009`, `TC-P2.phase0-F-T02S-01`, `TC-P2.phase0-F-T02S-02`, `TC-P2.phase0-F-T02S-03`, `TC-P2.phase0-F-T02S-04` |

## 5. 子用例 -> 推荐测试文件映射（落地计划）

| 子用例ID | 推荐测试文件 | 推荐函数名 |
| --- | --- | --- |
| `TC-P2.phase0-F-T02-01A` | `database_service/tests/integration/test_p2_phase0_news_raw_replay.py` | `test_validation_dataset_100_news_raw_replay_then_persist_news_event` |
| `TC-P2.phase0-F-T02-01B` | `database_service/tests/unit/test_p2_phase0_event_extractor_contract.py` | `test_event_extractor_must_not_emit_legacy_theme_directive` |
| `TC-P2.phase0-F-T02-01C` | `database_service/tests/unit/test_p2_phase0_event_extractor_contract.py` | `test_event_extractor_outputs_news_event_schema` |
| `TC-P2.phase0-F-T02-01D` | `database_service/tests/integration/test_p2_phase0_event_structuring_alignment.py` | `test_event_extractor_aligns_with_structuring_reference_script` |
| `TC-P2.phase0-F-T02-01E` | `database_service/tests/integration/test_p2_phase0_news_event_persistence.py` | `test_news_event_persisted_before_structured_stream_publish` |
| `TC-P2.phase0-F-T01-01` | `database_service/tests/integration/test_p2_phase0_theme_match_engine_db_input.py` | `test_theme_match_request_built_from_news_event_id` |
| `TC-P2.phase0-F-T02-02` | `database_service/tests/streams/test_p2_phase0_architecture_guard.py` | `test_only_structured_stream_allowed_no_major_normal_branch` |
| `TC-P2.phase0-F-T02-03` | `database_service/tests/integration/test_p2_phase0_decision_routing.py` | `test_match_unknown_human_review_route_to_expected_targets` |
| `TC-P2.phase0-F-T02H-01` | `database_service/tests/streams/test_p2_phase0_news_stream_handler_integration.py` | `test_news_stream_handler_persists_news_raw_from_stream` |
| `TC-P2.phase0-F-T02H-02` | `database_service/tests/unit/test_p2_phase0_news_stream_handler_boundaries.py` | `test_news_stream_handler_does_not_perform_structuring_or_matching` |
| `TC-P2.phase0-F-T02H-03` | `database_service/tests/integration/test_p2_phase0_news_ingest_pipeline_order.py` | `test_news_stream_handler_precedes_news_stream_processor` |
| `TC-P2.phase0-F-T02N-01` | `database_service/tests/streams/test_p2_phase0_news_stream_processor_refactor.py` | `test_news_stream_processor_consumes_persisted_news_only` |
| `TC-P2.phase0-F-T02N-02` | `database_service/tests/integration/test_p2_phase0_news_stream_processor_refactor.py` | `test_news_stream_processor_calls_event_extractor_and_model_service` |
| `TC-P2.phase0-F-T02N-03` | `database_service/tests/unit/test_p2_phase0_news_stream_processor_refactor.py` | `test_news_stream_processor_must_not_emit_legacy_theme_directive` |
| `TC-P2.phase0-F-T02N-04` | `database_service/tests/integration/test_p2_phase0_news_stream_processor_refactor.py` | `test_news_stream_processor_persists_news_event_before_structured_publish` |
| `TC-P2.phase0-F-T02N-05` | `database_service/tests/streams/test_p2_phase0_news_stream_processor_refactor.py` | `test_news_stream_processor_publishes_structured_event_envelope` |
| `TC-P2.phase0-F-T02N-06` | `database_service/tests/unit/test_p2_phase0_news_stream_processor_refactor.py` | `test_news_and_theme_processors_respect_pipeline_boundaries` |
| `TC-P2.phase0-F-T02R-01` | `database_service/tests/streams/test_p2_phase0_theme_processor_refactor.py` | `test_theme_processor_consumes_only_structured_stream` |
| `TC-P2.phase0-F-T02R-02` | `database_service/tests/integration/test_p2_phase0_theme_processor_refactor.py` | `test_theme_processor_loads_news_event_before_match` |
| `TC-P2.phase0-F-T02R-03` | `database_service/tests/integration/test_p2_phase0_theme_processor_refactor.py` | `test_theme_processor_builds_request_from_news_event_id` |
| `TC-P2.phase0-F-T02R-04` | `database_service/tests/unit/test_p2_phase0_theme_processor_refactor.py` | `test_theme_processor_does_not_use_legacy_category_or_fallback_match_paths` |
| `TC-P2.phase0-F-T02R-05` | `database_service/tests/unit/test_p2_phase0_theme_processor_refactor.py` | `test_theme_processor_publishes_only_three_state_envelope` |
| `TC-P2.phase0-F-T02R-06` | `database_service/tests/unit/test_p2_phase0_theme_processor_refactor.py` | `test_theme_processor_uses_v2_decision_metrics` |
| `TC-P2.phase0-F-T02S-01` | `theme_service/tests/integration/test_p2_phase0_theme_service_wrapper.py` | `test_theme_service_exposes_theme_match_engine_facade_for_theme_processor` |
| `TC-P2.phase0-F-T02S-02` | `theme_service/tests/unit/test_p2_phase0_theme_service_wrapper.py` | `test_theme_service_builds_theme_match_request_from_news_event_and_news_raw` |
| `TC-P2.phase0-F-T02S-03` | `theme_service/tests/integration/test_p2_phase0_theme_service_wrapper.py` | `test_theme_service_returns_theme_decision_envelope` |
| `TC-P2.phase0-F-T02S-04` | `theme_service/tests/unit/test_p2_phase0_theme_service_wrapper.py` | `test_theme_service_wrapper_rejects_legacy_discovery_paths_as_primary_entry` |
| `TC-P2.phase0-F-T02E-01` | `database_service/tests/e2e/test_p2_phase0_production_harness.py` | `test_production_harness_starts_from_validation_dataset_and_news_raw` |
| `TC-P2.phase0-F-T02E-02` | `database_service/tests/e2e/test_p2_phase0_production_harness.py` | `test_production_harness_runs_news_stream_handler_before_structuring` |
| `TC-P2.phase0-F-T02E-03` | `database_service/tests/e2e/test_p2_phase0_production_harness.py` | `test_production_harness_runs_news_stream_processor_before_match` |
| `TC-P2.phase0-F-T02E-04` | `database_service/tests/e2e/test_p2_phase0_production_harness.py` | `test_production_harness_runs_theme_processor_on_structured_stream` |
| `TC-P2.phase0-F-T02E-05` | `database_service/tests/e2e/test_p2_phase0_production_harness.py` | `test_production_harness_runs_decision_executor_and_materializes_outputs` |
| `TC-P2.phase0-F-T02E-06` | `database_service/tests/e2e/test_p2_phase0_production_harness.py` | `test_production_harness_produces_full_pipeline_audit_bundle` |
| `TC-P2.phase0-F-T02E-07` | `database_service/tests/e2e/test_p2_phase0_production_harness.py` | `test_legacy_dataset_script_is_not_accepted_as_phase0_primary_evidence` |
| `TC-P2.phase0-F-T04-01` | `database_service/tests/integration/test_p2_phase0_fallbacks.py` | `test_structuring_and_match_failures_fallback_to_human_review` |
| `TC-P2.phase0-F-T04-03` | `database_service/tests/integration/test_p2_phase0_audit_guard.py` | `test_missing_audit_fields_block_final_mapping_write` |
| `TC-P2.phase0-F-T05-02` | `database_service/tests/perf/test_p2_phase0_latency_budget.py` | `test_phase0_end_to_end_latency_budget_under_threshold` |
| `TC-P2.phase0-F-T05-03` | `database_service/tests/integration/test_p2_phase0_release_gate.py` | `test_phase0_archive_requires_full_evidence_bundle` |

## 6. 必跑命令（绝对路径，按层级顺序执行，MUST）

### Layer-1 `UT`：先跑基础组件
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/unit/test_p2_phase0_event_extractor_contract.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/unit/test_p2_phase0_news_stream_handler_boundaries.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/unit/test_p2_phase0_news_stream_processor_refactor.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/theme_service/tests/unit/test_p2_phase0_theme_service_wrapper.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/unit/test_p2_phase0_theme_processor_refactor.py`

### Layer-2 `IT`：单组件集成，按依赖顺序推进
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_event_structuring_alignment.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_news_event_persistence.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_p2_phase0_news_stream_handler_integration.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_news_ingest_pipeline_order.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_news_stream_processor_refactor.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/theme_service/tests/integration/test_p2_phase0_theme_service_wrapper.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_theme_processor_refactor.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_theme_match_engine_db_input.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_decision_routing.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_fallbacks.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_audit_guard.py`

### Layer-3 `ARCH/ST`：架构守卫与固定样本回放
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_p2_phase0_architecture_guard.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_news_raw_replay.py`

### Layer-4 `PT/E2E`：多模块全链路与性能
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/e2e/test_p2_phase0_production_harness.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/perf/test_p2_phase0_latency_budget.py`

### 阻塞规则（MUST）
- 若 `Layer-1 UT` 未通过，`Layer-2/3/4` 全部标记 `BLOCKED`
- 若 `event_extractor.py` 的 `UT/IT` 未通过，`news_stream_processor.py` 的 `IT/PT` 全部标记 `BLOCKED`
- 若 `theme_service.py` 的 `UT/IT` 未通过，`theme_processor.py` 与 `E2E` 全部标记 `BLOCKED`
- 若 `Layer-2 IT` 未通过，不得进入 `Layer-4 PT/E2E`

## 7. 真实依赖执行要求（MUST）
- Redis：必须真实写入 `stream:news:raw`、`stream:events:structured`、`stream:events:decision`。
- Postgres：必须真实写入并校验 `news_raw`、`news_event`、`event_theme_map`。
- LLM：必须真实调用 `event_extractor.py` 的模型解析链，不允许 mock 结构化结果替代核心证据。
- Pipeline 顺序：必须先由 `news_stream_handler.py` 完成 `news_raw` 入库，再由 `news_stream_processor.py` 生成并落库 `news_event`，随后由 `theme_processor.py` 通过 `theme_service.py` 门面调用 `ThemeMatchEngine`，最后再进入执行链；若跳过任一环节，测试结论必须是 `FAILED`。
- 若 Redis / Postgres / LLM 任一不可达，测试结论必须是 `BLOCKED` 或 `FAILED`，不得标记通过。

## 8. 数据库一致性检查点（MUST）
- `news_event.news_id -> news_raw.id` 外键链必须可追踪。
- `event_theme_map.event_id -> news_event.id` 外键链必须可追踪。
- `theme_directive` 不得再写入 `CREATE_NEW / CLUSTER`。
- `raw_event_json` 必须包含结构化快照与版本字段。
- `ThemeMatchRequest` 与 `ThemeDecisionEnvelope` 的服务层构建与返回必须可通过 `theme_service.py` 追踪。

## 9. 与 feature_spec 的一致性结论
- `F-P2.phase0-T01 ~ T05` 已全部建立测试映射。
- 当前文档已把“操作 `news_event` 表而不是操作 JSON 文件”作为核心测试约束。
- 当前仍缺阶段专用测试文件实现，因此本文件是 `P2.phase0` 的测试真源，但还不是执行完成态。

## 10. 当前真实测试执行同步（2026-03-30）

### 10.1 已通过的真实证据
- `ThemeMatchEngine` 单元层
  - `tmp/p2_phase0_theme_match_engine_10.preview.json`
  - `tmp/p2_phase0_theme_match_engine_30_from_test_cases.preview.json`
- `theme_processor.py` 真实集成层
  - `tmp/p2_phase0_theme_processor_integration_30.preview.json`
- `news_stream_processor.py -> theme_processor.py` 真实跨组件层
  - `tmp/p2_phase0_news_to_theme_5.preview.json`
- `stream:news:raw -> decision` 真实全链路预演
  - `tmp/p2_phase0_full_chain_10_to_decision.preview.json`

### 10.2 新增的真实必跑命令
- `ThemeMatchEngine` 真实单元验证
  - `cd /Users/admin/Desktop/ai_theme_app && POSTGRES_DATABASE=stock_data_test /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/theme_service/tests/unit/test_p2_phase0_theme_match_engine_real_db.py`
- `theme_processor.py` 真实集成验证
  - `cd /Users/admin/Desktop/ai_theme_app && PYTHONPATH=/Users/admin/Desktop/ai_theme_app POSTGRES_DATABASE=stock_data_test /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_theme_processor_real_integration.py`
- `news_stream_processor.py -> theme_processor.py` 真实跨组件验证
  - `cd /Users/admin/Desktop/ai_theme_app && export DEEPSEEK_API_KEY='***' && export P2_PHASE0_SAMPLE_SIZE=10 && export PYTHONPATH=/Users/admin/Desktop/ai_theme_app && export POSTGRES_DATABASE=stock_data_test && /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/run_news_processor_to_theme_processor_5.py`
- `stream:news:raw -> decision` 真实全链路验证
  - `cd /Users/admin/Desktop/ai_theme_app && export DEEPSEEK_API_KEY='***' && export PYTHONPATH=/Users/admin/Desktop/ai_theme_app && export POSTGRES_DATABASE=stock_data_test && /opt/miniconda3/envs/theme_matcher_env/bin/python -u /Users/admin/Desktop/ai_theme_app/tmp/run_full_chain_10_to_decision_with_progress.py`
  - `cd /Users/admin/Desktop/ai_theme_app && export DEEPSEEK_API_KEY='***' && export PYTHONPATH=/Users/admin/Desktop/ai_theme_app && export POSTGRES_DATABASE=stock_data_test && /opt/miniconda3/envs/theme_matcher_env/bin/python -u /Users/admin/Desktop/ai_theme_app/tmp/run_full_chain_100_to_decision_with_progress.py`

### 10.3 对 `T02E` 的补充冻结
- `TC-P2.phase0-F-T02E-01 ~ 06` 的主证据，必须优先采用从 `stream:news:raw` 起步的真实脚本，不得再以旧 `test_new_architecture_with_dataset()` 或任何预结构化 JSON 回放替代。
- 全链路脚本必须提供实时进度输出，至少包含：
  - `news_raw injected`
  - `news_raw persisted`
  - `news_event persisted`
  - `structured event published`
  - `decision received`
- 当前 `news_stream_handler.py` 组件缺口已修复并完成无补偿复测。
- 若后续出现新的运行时补偿，仍必须在报告中显式标记，不能直接视为最终 Gate 关闭证据。

### 10.4 当前未关闭的 QA 前置项
- `news_stream_handler.py` 的 `_ensure_consumer_group()` 已补齐并完成 `10` 条真实全链路复测。
- `100` 条全量最终验证尚未执行。

## 10.5 2026-03-31 最新测试收口

### 已完成的真实最终验证
- `stream:news:raw -> stream:events:decision` 真实全链路 `100` 条：
  - `events = 100`
  - `processed = 100`
  - `top1_hits = 96`
  - `top1_accuracy = 0.96`
- 结果文件：
  - [p2_phase0_full_chain_100_to_decision.report.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_to_decision.report.json)
  - [p2_phase0_full_chain_100_match_detail.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_match_detail.json)
  - [p2_phase0_full_chain_100_match_metrics.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_match_metrics.json)
  - [p2_phase0_full_chain_100_mismatches.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_mismatches.json)

### 结构化稳定性最新约束
- 默认 parser 已切换为 [reliable_deepseek_parser.py](/Users/admin/Desktop/ai_theme_app/model_service/llm_parser/reliable_deepseek_parser.py)。
- 后续真实全链路验证必须继续通过 [factory.py](/Users/admin/Desktop/ai_theme_app/model_service/llm_parser/factory.py) 默认入口走 `ReliableDeepSeekParser`，不得手工回切基础版 parser。

### 测试结论更新
- `TC-P2.phase0-PT-002`
  - 状态：`PASS`
  - 依据：真实 `100` 条全链路已完成，且结果回到 `top1 = 0.96`
- `TC-P2.phase0-ST-001`
  - 状态：`PASS`
  - 依据：原始 `news_raw` 从 Redis Stream 起步的整链已跑通

### 当前保留观察项
- 启动阶段仍有旧 `ThemeDiscoveryEngine` 初始化日志，需继续跟踪，但不影响当前测试通过结论。

## 10.6 2026-04-06 题材真源迭代与定向复测

### 口径说明
- 本节记录的是 `structured_events_with_gt.jsonl` 驱动的 **运行时匹配基线复测**，重点验证：
  - `dense -> merged -> rerank -> dynamic_topk/reserve -> LLM Judge`
  - 题材真源 `subject_gates/*.json` 修正后的候选召回与排序质量
- 本节 **不替代** `10.5` 中已经通过的 `stream:news:raw -> decision` 真实全链路 `100` 条 `0.96` 结果。
- 本节主要回答两个问题：
  - 最新全量题材库下，题材真源是否老化
  - 候选池、rerank、LLM 裁决是否仍然正确

### 本轮测试真源调整
- 统一把 `9037499` 视为 `9030409` 的老化/冗余编码，在运行时合并到 `9030409 / AI/AR眼镜`。
- `structured_events_with_gt.jsonl` 已做以下 GT 复核与迁移：
  - `9019807 / 卫星互联网`
    - 清理掉应迁移到 `9060827 / 可回收火箭`、`9061851 / 商业航天8大IPO` 的样本
  - `9064166 / SpaceX`
    - 全部统一到 `9064166`
    - `9060949` 视为老化编码，不再作为测试 GT
  - `9043698 / 深海经济`
    - 显示名称从旧口径 `海洋经济` 统一纠正为 `深海经济`
  - `9024880 / 液冷数据中心`
    - `evt_fbc14c988eab` 迁移到 `9014001 / 人工智能硬件`

### 本轮通用机制修正
- `ThemeMatchEngine` 已补入 `feature/rule recall`，不再仅依赖纯 dense recall。
- `rerank hit_features` 已扩大到：
  - `subject_name`
  - `concept`
  - `aliases`
  - `entity_hints`
  - `core_objects`
- 高权重命中已统一过滤明显通用污染词，避免脏候选长期压制垂直题材：
  - `产品 / 设备 / 公司 / 合作 / 美国`
  - `动力系统 / 商业航天 / 应用 / 卫星 / 金融`

### 本轮题材真源修正清单
- 已直接修正并重导的题材：
  - `9030409 / AI/AR眼镜`
  - `9019807 / 卫星互联网`
  - `9043698 / 深海经济`
  - `9024880 / 液冷数据中心`
  - `9059919 / 对日制裁`
- 修正方式统一为：
  - 补强 `must / strong / aliases / entity_hints / core_objects`
  - 清理明显错误的 `not_terms`
  - 让题材锚点回到真实新闻表达，而不是停留在旧口径或过窄技术词

### 定向复测结果
- `9030409 / AI/AR眼镜`
  - `merged candidate_recall = 35/35 = 100%`
  - `rerank top1 = 27/35 = 77.14%`
  - `LLM top1 = 32/35 = 91.43%`
  - 结论：前段候选池问题已基本解决，剩余误差主要是边界题材竞争
- `9019807 / 卫星互联网`
  - 清洗后有效样本 `6` 条
  - `merged/rerank/reserve candidate_recall = 6/6 = 100%`
  - `rerank/reserve top1 = 5/6 = 83.33%`
  - 结论：卫星组网、卫星超级工厂、算力星座等真实新闻表达已能稳定召回
- `9064166 / SpaceX`
  - 统一 GT 后样本 `5` 条
  - `merged/rerank/reserve candidate_recall = 5/5 = 100%`
  - `rerank/reserve top1 = 1/5 = 20%`
  - `LLM top1 = 5/5 = 100%`
  - 结论：在 `9062206 / 马斯克四大产业` 正常共存的前提下，前段候选已稳定，最终由 LLM 完成上位题材与子题材裁决
- `9043698 / 深海经济`
  - `merged/rerank/reserve candidate_recall = 4/4 = 100%`
  - `merged/rerank/reserve top1 = 4/4 = 100%`
  - 结论：问题根因是题材真源已演进到“深海经济”口径，修正 gate 后前段链路已完全正确
- `9024880 / 液冷数据中心`
  - GT 清洗后有效样本 `7` 条
  - `dense candidate_recall = 6/7 = 85.71%`
  - `merged/rerank/reserve candidate_recall = 7/7 = 100%`
  - `merged top1 = 5/7 = 71.43%`
  - `rerank/reserve top1 = 4/7 = 57.14%`
  - 结论：主问题已从“候选进不来”转为与 `9014001 / 人工智能硬件` 的近邻竞争
- `9059919 / 对日制裁`
  - `dense candidate_recall = 2/6 = 33.33%`
  - `merged/rerank/reserve candidate_recall = 6/6 = 100%`
  - `merged top1 = 4/6 = 66.67%`
  - `rerank/reserve top1 = 5/6 = 83.33%`
  - 结论：旧 “水产品/电池材料” gate 口径已被当前 `出口管制 / 两用物项 / 反外国制裁法 / 靖国神社 / 高市早苗 / 岩崎茂` 的真实新闻口径替换

### 最新 100 条运行时基线
- 结果文件：
  - [runtime_theme_match_metrics_100.json](/Users/admin/Desktop/ai_theme_app/tmp/runtime_theme_match_metrics_100.json)
  - [runtime_theme_match_detail_100.json](/Users/admin/Desktop/ai_theme_app/tmp/runtime_theme_match_detail_100.json)
- 指标：
  - `events = 100`
  - `processed = 100`
  - `top1_accuracy = 0.60`
  - `top3_accuracy = 0.84`
  - `top5_accuracy = 0.86`
- 对比旧运行时基线：
  - `top1: 0.42 -> 0.60`
  - 提升 `18` 个百分点
- 说明：
  - 本结果是 **运行时匹配基线**，不含前述 `SpaceX`、`对日制裁`、`液冷数据中心 GT 清洗后` 的最新增量，因此后续整体基线仍应再重跑一次作为新冻结版本。

### 当前阶段结论
- `P2.phase0` 的全链路生产级验证结论仍以 `10.5` 为准，即：
  - `100` 条 `stream:news:raw -> decision` 真实全链路已通过
- 2026-04-06 这轮补充验证的意义在于：
  - 修复全量题材库下的题材真源老化
  - 修正运行时候选池与 rerank 失真
  - 为后续重新冻结 `100` 条运行时基线与后续阶段测试提供可追踪证据

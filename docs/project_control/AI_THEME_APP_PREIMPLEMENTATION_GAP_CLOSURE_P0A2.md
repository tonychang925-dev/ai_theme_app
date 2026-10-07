# AI_THEME_APP_PREIMPLEMENTATION_GAP_CLOSURE_P0A2

> **工程基准**：`main@ddc9442e88c5bf6f5248bfb141e74472c48eb25a`
> **策略基准**：v0.6.4 APPROVED WORKING BASELINE（未冻结）
> **配套文档**：
> - `EXECUTABLE_RULE_AUTHORITY_INVENTORY.md`（下文简称“清单 1”）
> - `CANONICAL_AND_LEGACY_DECISION_PRODUCER_INVENTORY.md`（下文简称“清单 2”）
> **方式**：只读（`grep` / `sed` / `cat`）。没有改代码、测试、数据库，没有运行代码，没有新建策略。
> **只覆盖四项**：① PDV2 内部规则；② 剩余在线直连数据库的分类；③ `w2s_unified_alert_service` 是否在线；④ M8 是否反向拥有业务真相或决策权威
> **按要求未涉及**：1进2、弱转强 D1、周期
> **整理**：Mira（Claude），2026-10-07

---

## 0. 结论

| 项 | 结论 | 对之前清单的影响 |
|---|---|---|
| ① PDV2 | **它不是决策引擎，是展示装配器。** 194 行代码里没有任何交易判断；D1 和 focus 输出写死为空；交易许可是从 MarketRegime 原样转写的。可执行规则 9 条，全部是去重、默认值和透传 | **更正清单 2**：P-12 的“决策权威”应改为**否**（只展示 + 透传）。新链实际的决策权威在 P-04 MarketRegime；PDV2 没有接手旧链 P-11 的决策职能 |
| ② 直连数据库 | Application 层 33 个命中逐个分类：**在线且在策略路径上 6 个**，在线的采集 / 运维 8 个，回测 9 个，认知 / 展示 4 个，死代码或测试残留 3 个，误报 2 个，还有 1 个是用例层的连接池传递。最突出的模式不是“自己建连接”，而是**通过 `getattr(read_port, "_pool")` 穿透 Port 的内部实现**，复盘任务本身就有 3 处 | 补全清单 2 §4 |
| ③ 统一预警 | **在线**。API 启动后默认开启（`SPS_ENABLE_W2S_ALERT_LOOP` 默认 `"true"`），竞价和盘中循环运行，推送到 Redis。它是弱转强 D2 之后的**第二个在线确认 / 分级生产者**，位于 Domain 层，直连数据库；有两处“缺失 → 放行或陈旧兜底” | **更正清单 2**：P-20 从“待确认”改为 **LIVE**；P-19 中 `w2s_intraday_alert_service_v2` 的评分函数经由它在线使用，不再是纯诊断 |
| ④ M8 | **没有发现**反向写业务表，也**没有发现**决策链读取 M8 输出。M8 只读复盘快照和判定表，写的是本地 JSON 文件；Notion 渲染默认 `legacy_only`。**但有一条相邻的风险**：分析师工作台的“应用校准”接口，会用昊哥的标注**覆盖**系统草稿中的情绪节点、策略和风险 | M8 边界成立；另记一项外部参照污染系统输出的风险（P1） |

---

## 1. PostMarketDecisionEngineV2 内部规则

文件：`domain/services/post_market_decision_v2/post_market_decision_engine_v2.py`（194 行）；`models.py`（151 行，只有数据结构，没有规则）。

模块自述（`:3–8`）：“Layer C post-market view assembler… Confirmed mainlines are used only as annotations… does not filter Layer C by mainline, and does not generate Layer D1.” 代码与自述一致。

| # | 位置 | 规则 | 实际作用 | 分类 | 风险 |
|---|---|---|---|---|---|
| V2-01 | `:68` | `allow_trade = regime.get("allow_trade", False)` | 原样透传许可；缺失时为 False | OWNER_APPROVED（缺失即关闭） | — |
| V2-02 | `:69` | `trade_mode` 缺失时为 `"no_trade"` | 同上 | OWNER_APPROVED | — |
| V2-03 | `:70` | `position_limit` 缺失时为 0 | 同上；数值来自 P-04 的 L4-04 | 透传；上游是 POLICY_UNFROZEN | 继承上游 |
| V2-04 | `:44–52`、`:103–111` | 同一身份或同一只股票保留 `watch_score` 最高的一行 | 去重。**做了两遍**：第一遍按（主线、题材、股票）去重，第二遍只按股票去重。第二遍会把同一只股票在不同主线下的记录压成一条 | （实现选择） | P2 |
| V2-05 | `:118–120` | `pool_entry_type` 不在 {formal, observe_only, reject, ""} 时 → `observe_only` | 未知类型降级为观察 | OWNER_APPROVED（保守） | — |
| V2-06 | `:133` | `strong_grade` 缺失 → `"REJECT"` | 缺失即拒绝 | OWNER_APPROVED（保守） | — |
| V2-07 | `:131` | `watch_status` 缺失 → **`"active"`** | 缺失 → 活跃 | UNAUTHORIZED_INFERENCE | P2（只影响展示） |
| V2-08 | `:130` | `watch_priority` 缺失 → 等于 `watch_score` | 默认值 | UNAUTHORIZED_INFERENCE（轻微） | P2 |
| V2-09 | `:145`、`:177` | 主线绑定只作标注（`mainline_filter_applied: False`） | 不按主线过滤 Layer C | OWNER_APPROVED（身份与股票池分离） | — |
| V2-10 | `:155–156`、`:168–169`、`:180–183` | `d1_candidate_count = 0`、`focus_stock_count = 0`；`weak_to_strong_d1_reviews = []`、`next_day_focus_stocks = []` | **D1 和次日重点永远为空** | （占位） | **P1：见下** |

**对迁移的含义**：
- 前端 `RecapPage`、`EnginePostMarketView` 展示的“PDV2”，只有**强势股池 + 一份透传的交易许可**。“次日重点”和“弱转强 D1”两栏是空的。
- 旧链 P-11 的观察清单（`watchlist_reviews`）、题材决策、交易原则，在新链里**没有对应的生产者**。
- 所以 R1 Phase E“新旧决策切换”的前提并不成立：**目前新链没有可以接手的决策输出**。切换之前，必须先明确由谁来产出“次日重点 / 观察清单”。

---

## 2. Application 层直连数据库：逐个分类

### 2.1 判定方法

对 33 个粗扫命中的文件，逐个统计：
- 自建连接（`asyncpg.connect` / `create_pool`）；
- 实际查询调用（`fetch` / `fetchrow` / `fetchval` / `execute`）；
- 穿透 Port 内部（`_pool` / `_db` / `_client`）；
- `execute_query`；
- 引用方。

### 2.2 结果

| 类别 | 文件 | 访问方式 | 在线情况 | 风险 |
|---|---|---|---|---|
| **A. 在线 · 策略路径** | `jobs/build_post_market_recap_job.py`（`:146–149`、`:864–875`、`:891–906`） | **穿透 Port**：`getattr(self._read_port, "_pool")` → `getattr(facade, "_db")`，然后直接写 SQL，读 `stock_abnormal_signal`、`stock_daily_basic_snapshot` | LIVE（复盘任务） | **P0**：这是新链核心任务本身在破坏 Port 边界 |
| A | `services/market_regime/market_regime_fact_context_builder.py`（`:65–66`、`:120–121`） | 硬编码 DSN `asyncpg.connect`（清单 2 已记录） | LIVE，决策权威 | **P0** |
| A | `services/market_metrics/service.py`（4 处建连接、15 处查询） | 自建连接 | LIVE，展示 | P1 |
| A | `services/event_driver_tracer.py`（`:111`、`:294`） | 注入的 pool 直接 `acquire`，查 `event_subject_map`、`theme_gate_profile` | LIVE（叙事组合器、日复盘 V2） | P1 |
| A | `services/event_driven_opportunity_builder.py`（`:294–297`） | **硬编码账号密码**（`user="postgres", password="postgres"`）`asyncpg.connect`，查 `theme_stock_map` | LIVE（API） | P1 |
| A | `use_cases/generate_post_market_derived_data.py`（`:84–101`） | 持有 pool 并传给各个任务 | LIVE（API `:2977`） | P2：本身不写 SQL，但把连接池往下传，等于为下游绕过 Port 提供了通道 |
| **B. 在线 · 采集 / 运维** | `services/collection_task_runners.py`（`:157–163` 取 pool；`:1730`、`:1776`、`:1904` 硬编码 DSN） | 自建连接 + 穿透 | LIVE（任务注册表） | P2（不在策略路径上） |
| B | `jobs/index_kline_collect_job.py` | 穿透 | LIVE（注册表 `index_kline.collect`） | P2 |
| B | `jobs/subject_stock_snapshot/jyhf_producer.py`、`tushare_join_producer.py` | 穿透 | LIVE（`stock_snapshot.build`） | P2 |
| B | `jobs/subject_rank/jyhf_producer.py`、`snapshot_agg_producer.py` | 穿透 | LIVE（`subject_rank.build`） | P2 |
| B | `services/post_market_job_status_service.py`、`post_market_readiness_service.py` | 注入 pool | LIVE（复盘任务的状态 / 就绪检查） | P2 |
| B | `services/realtime_stack_manager.py`（`:902`） | 用环境变量建连接 | LIVE（API） | P2 |
| **C. 回测** | `services/backtest/*`（9 个） | 通过 `gw._client.execute_query` **穿透 Gateway**，执行原始 SQL | DIAGNOSTIC | P2 |
| **D. 认知 / 展示** | `market_cognition/attention_engine.py`、`cognition_card_builder.py` | 硬编码 DSN（`:26` / `:14`） | LIVE（API `/api/v1/attention`、`/cognition`、`/playbook`），只读 | P2 |
| D | `market_metrics/board_pool_provider.py`、`services/pre_market_brief_auto_scheduler.py` | **误报**（实际查询计数为 0） | — | — |
| **E. 死代码 / 测试残留** | `market_cognition/emotion_engine.py` | 硬编码 DSN | DEAD_CODE | 随死代码清理 |
| E | `jobs/build_jyhf_stock_daily_bar_job.py` | 自建连接 | **类名在全仓库没有被引用** → DEAD_CODE | 清理 |
| E | `jobs/subject_stock_snapshot/test_snapshot.py` | 自建连接 | 测试文件放在生产目录 | 移出 |

### 2.3 Phase A 应该锁的位置（按优先级）

1. **P0 两处**：
   - 复盘任务的 Port 穿透（`build_post_market_recap_job.py` 三处）；
   - MarketRegime 事实构建的硬编码连接。
   
   这两处都在新链核心的决策输入路径上。
2. **P1 三处**：`market_metrics/service.py`、`event_driver_tracer.py`、`event_driven_opportunity_builder.py`（含明文账号密码）。
3. **Domain 层**：清单 2 §4 已列出，其中在线的有 `mainline_logic_chain_builder`、`kline_break_detector`、`w2s_unified_alert_service`（见 §3）。
4. 采集 / 运维（B）和回测（C）可以放到后面：它们不进入策略判断。

**一个共同模式**：大部分违规**不是**直接 `import asyncpg`，而是 `getattr(port, "_pool")`、`gw._client` 这类**从 Port / Gateway 对象里取出内部连接**。所以契约测试只搜索 `asyncpg` 是不够的，还要拦截对 `_pool`、`_db`、`_client` 的属性访问。

---

## 3. `w2s_unified_alert_service`：在线

### 3.1 证据

- `api_app.py:268–273`：API 启动时，如果 `SPS_ENABLE_W2S_ALERT_LOOP` 为真（**默认 `"true"`**），就创建 `_run_w2s_alert_loop` 后台任务。
- `api_app.py:6675` 起：循环每分钟运行；周末空转；竞价时段调用 `svc.build_auction_alerts(...)`；盘中另有分支。结果通过 `w2s_alert_redis_pusher` 推送到 Redis。
- 前端 `OrchestratorStatusPanel.tsx`、`api.ts` 读取这个循环的状态。
- `engines/w2s_engine/service.py` 也包装了它，但 `engines/` 目录在仓库内没有被任何地方引用，属于 DEAD_CODE。

**结论：LIVE。默认开启。**

### 3.2 它做什么

文件：`domain/services/w2s_unified_alert_service.py`（337 行）。

1. 直接查询 `weak_to_strong_candidate_pool` 左连接 `weak_to_strong_auction_signal`（`:200–212`），拿到 D2 等级。
2. 读取 `jyhf_stock_quote_snapshot`（`:274`），得到盘口资金方向。
3. 调用 `W2SIntradayAlertServiceV2.score_v2_2(...)`（`:266`），算出盘中等级。
4. **合成统一等级**（`:290–302`）：
   - 盘中 `turn_strong` 且 D2 为 A / B 且资金不是流出 → `high_confidence`（推送级别 `alert`）；
   - 盘中 `early_turn` 且 D2 为 A / B / C → `turn_observe`；
   - D2 为 X 或资金流出 → `risk`；
   - 其余 → `early_observe`。

### 3.3 问题

| # | 位置 | 问题 | 分类 | 风险 |
|---|---|---|---|---|
| UA-01 | `:198–203` | 当天的候选池可能没有数据，这时取 `MAX(next_trade_date)`，也就是**最新一个可用日期**的候选（注释：“候选池的 next_trade_date 可能滞后，取最新可用日期”） | UNAUTHORIZED_INFERENCE（**用旧数据兜底**：可能拿前几天的候选在今天发出预警） | **P0** |
| UA-02 | `:282–291` | 盘口数据读取失败时异常被吞掉（`except Exception: pass`），资金方向保持 `"unknown"`；而 `high_confidence` 的条件是“资金方向**不是** outflow”，`unknown` 能通过 | UNAUTHORIZED_INFERENCE（缺失 → 放行） | **P0** |
| UA-03 | `:290–302` | 统一等级规则 | POLICY_UNFROZEN | P1 |
| UA-04 | `w2s_intraday_alert_service_v2.py` 中 `score_v2_2` 及其约 30 个数值阈值（如 `:258–260` 的 ≥70 / ≥45，`:336` 的偏离均价 ≤1.5%） | 盘中转强评分 | POLICY_UNFROZEN | P1 |
| UA-05 | 整个文件 | Domain 层用 `self._dsn` 自建连接池 | DIRECT_DB_VIOLATION（Domain） | P0（边界） |
| UA-06 | 与 P-16 的关系 | 弱转强的 D2 已经有 `W2SConfirmService`（P-16）。这里**又**把 D2 等级和盘中评分合成了一个对外推送的“高置信”信号 | MULTI_TRUTH_PRODUCER | P1 |

**对清单 2 的更正**：
- P-20：从“待确认”改为 **LIVE，提示类，直接推送到 Redis**。
- P-19：`w2s_intraday_alert_service_v2` 的评分函数经由 P-20 **在线使用**，不再是纯诊断。v1 和其余几个盘中预警服务仍然是诊断用途。

---

## 4. M8：没有反向真相，有一处相邻风险

### 4.1 M8 范围

- `application/services/market_cognition/*`（不含死代码 `emotion_engine.py`）；
- `application/pipeline/*`（`market_world_model`、`simulation`、`world_state_transition_compiler`）；
- `application/services/analyst_alignment/*`；
- `domain/policies/policy_registry.py`。

### 4.2 写

- 在 `market_cognition`、`pipeline`、`analyst_alignment` 中，**没有找到** `INSERT`、`UPDATE`、`DELETE` 或 `upsert` 语句。
- 持久化只有本地文件：
  - `world_state_persister.py:45`；
  - `hypothesis_source_store.py:55`；
  - `evidence_artifact_service.py:49`（`write_text` / `json.dump`）。
- API 的 `save` 接口（`/api/v1/cognition/.../save`、`/playbook/.../save`、`/attention/.../override`）也只写本地 JSON 或日志文件（`api_app.py:7128` 起、`:7194` 起、`:7282` 起；playbook 存到 `tmp/playbooks`）。

### 4.3 读

M8 只读这几张表：`post_market_recap_snapshot`、`theme_cycle_judgement_v`、`market_environment_metrics`、`market_environment_judgement`，都是下游消费。

### 4.4 有没有被决策链读取

- 在 `domain/`、`application/jobs/`、`application/use_cases/`、`market_regime/`、1进2 计划引擎、事实构建器中，搜索 `market_cognition`、`world_state`、`cognition_card`、`playbook`、`hypothesis_source`：唯一命中的是 `domain/policies/policy_registry.py`。它只被 M8 自己的 `world_state_builder_service` 和 `pipeline/market_world_model` 使用，而这两者又只被脚本调用。
- Notion 发布器的 M8 渲染模式默认是 `legacy_only`（`notion_post_market_recap_publisher.py:153`）。

**结论：M8 是只读的下游认知层，没有反向业务真相，也没有决策权威。R1 §5.13 的判断成立。**

### 4.5 相邻风险：外部参照覆盖系统输出

- **位置**：`api_app.py:9076` `/api/v1/analyst-workbench/{trade_date}/apply-calibration`（`analyst_alignment` 校准体系的入口）。
- **行为**：读取分析师参照记录（昊哥），当系统和分析师的匹配度低于阈值（阶段 <0.5、策略 <0.5、风险 <0.8）时，**直接用分析师的值覆盖工作台草稿里系统自己的** `emotion_node`、策略和风险字段，并记一条“校准修正”。
- **为什么是风险**：
  - v0.6.4 §0.2 规定 EXT-01 / CS-13–15 **不能定义 Tony 的策略**。这个接口却让外部判断进入了“系统输出”这一栏。
  - 覆盖之后，同一份草稿再拿去和昊哥对比，匹配度会虚高，图灵分等评估指标会被污染。
- **影响范围**：只限分析师工作台草稿（展示 / 复盘层）。在 `domain/`、任务和用例中**没有找到**读取工作台草稿或分析师参照的地方，所以**不进入决策链**。
- **分类**：UNAUTHORIZED_INFERENCE（外部参照被冒充为系统判断），**P1**。

---

## 5. 对两份清单的更正汇总

| 清单 | 条目 | 原写法 | 更正为 |
|---|---|---|---|
| 清单 2 | P-12 PDV2 | 决策权威：是 | **否**（展示装配 + 透传许可；D1 和次日重点为空） |
| 清单 2 | P-20 统一预警 | 待确认 | **LIVE**（默认开启，推送到 Redis） |
| 清单 2 | P-19 中的 `w2s_intraday_alert_service_v2` | DIAGNOSTIC | 评分函数 `score_v2_2` 经由 P-20 **在线使用** |
| 清单 2 | §4 Application 层 | 约 31 个未分类 | 见本文 §2.2 |
| 清单 2 | `engines/` 目录 | 未列出 | `decision_engine`、`market_state_engine`、`support_engine`、`w2s_engine` 在仓库内**没有被引用**，属于 DEAD_CODE |
| 清单 2 | `build_jyhf_stock_daily_bar_job.py` | 未列出 | DEAD_CODE |
| 清单 1 | 新增 | — | V2-07、V2-08（缺失 → 默认值）；UA-01、UA-02（P0）；UA-03、UA-04（未冻结）；§4.5 外部参照覆盖 |

---

## 6. 状态

```text
本轮                        = 只读；没有改代码、测试、数据库，没有运行代码，没有新建策略
PDV2                        = 展示装配器，没有决策职能 → 新旧切换缺少新链的决策输出
Application 直连（在线·策略） = 6 个，其中 P0 两个（复盘任务穿透 Port、MarketRegime 硬编码连接）
统一预警                     = LIVE；P0 两处（旧候选兜底、资金方向缺失时放行）；Domain 层直连
M8                          = 没有反向真相、没有决策权威；相邻风险：工作台校准用外部标注覆盖系统输出（P1）
下一步                       = 等 Owner 重排实施顺序；在那之前不改代码
```

# EXECUTABLE_RULE_AUTHORITY_INVENTORY

> **任务**：AI_THEME_APP_DRIFT_CORRECTION_PREIMPLEMENTATION_INVENTORY_P0 · 清单 1/2
> **工程基准**：`main@ddc9442e88c5bf6f5248bfb141e74472c48eb25a`
> **策略基准**：v0.6.4 APPROVED WORKING BASELINE（未冻结）
> **配套文档**：`AI_THEME_APP_DRIFT_AUDIT_R1_INDEPENDENT_VERIFICATION.md`、`CANONICAL_AND_LEGACY_DECISION_PRODUCER_INVENTORY.md`
> **方式**：只读（`grep` / `sed`）。没有改代码、测试、数据库或分支。
> **整理**：Mira（Claude），2026-10-07

---

## 0. 读法

### 0.1 范围

本清单覆盖**主线判断、周期、许可、强势股、1进2、弱转强、旧决策链**这些策略路径上的可执行规则，也就是会改变状态、资格、排序或动作的数字和分支。

不包括：
- 采集器；
- UI 文案；
- 回测脚本里的参数；
- 日志格式。

这是**策略路径上的重点盘点，不是全仓库每个数字**。未覆盖的模块列在 §9。

### 0.2 权威分类（只用 6 类）

| 分类 | 含义 |
|---|---|
| **SOURCE_SUPPORTED** | 规则和数值都能追溯到 v0.6.4 的 [E] 原文 |
| **OWNER_APPROVED** | 与 v0.6.4 已批准的语义一致（Part 15.1） |
| **EMPIRICAL_CANDIDATE** | 有数据或复盘作依据，但没有经过 Owner 冻结 |
| **POLICY_UNFROZEN** | 属于 Owner 政策范畴，数字或选择尚未冻结 |
| **LEGACY_ONLY** | 只来自旧链的历史行为，没有策略依据 |
| **UNAUTHORIZED_INFERENCE** | 估算、默认值、缺失转通过、口径错误、作用域错误：系统自己“推”出了事实或结论 |

### 0.3 状态栏标记

- `与已批准语义冲突`：与 v0.6.4 Part 15.1 中已批准的结论方向相反
- `决策权威`：结果会进入许可、候选或动作
- `仅展示`：只进入报告或前端展示

### 0.4 风险等级

- **P0**：会制造或阻断正式交易资格
- **P1**：会扭曲正式排序或展示给 Owner 的判断
- **P2**：诊断类，或影响有限

---

## 1. 单列：指标口径错误（WRONG_METRIC_SEMANTICS）

| 字段 | 内容 |
|---|---|
| 位置 | `application/services/market_metrics/service.py:726` |
| 符号 | `MarketMetricsService._emotion_momentum`（`first_red = relay.continue_ratio`） |
| 名称上的含义 | 昨日**首板**中，今日**收红**的比例（昊哥 E01） |
| 实际口径 | 昨日**全部涨停**中，今日**继续涨停**的比例（`continue_ratio`） |
| 性质 | **WRONG_METRIC_SEMANTICS**：分子、分母都不对，不是估算误差。权威分类记为 UNAUTHORIZED_INFERENCE |
| 生产者 | `MarketMetricsService` → `EmotionMomentum.first_board_red_ratio`（`service.py:756`） |
| 消费者 | ① `momentum_raw`（`service.py:746` 权重 ×2）→ `momentum_normalized` → `/api/v1/emotion` 的 `emotion_score`（`api_app.py:8074`）→ 前端 `EmotionDashboard`、`WorkbenchSectionsPanel`；② `/api/...` 指标接口 `api_app.py:7503`；③ 分析师图表 `analyst_charts/builders/emotion_momentum_chart.py:6`、`chart_engine.py:72`；④ 工作台 `analyst_workbench/chart_review_builder.py:211`；⑤ 前端 `ChartRenderer.tsx:153` 直接显示“首板红盘比” |
| 影响层 | L1（展示层）。**不进入**交易许可：许可链走的是 MarketRegime，见清单 2 |
| 风险 | **P1**：Owner 看到的“首板红盘比”是另一个量；情绪动能分也被这个量带偏 |

同一函数中，紧挨着的其他问题：

| 位置 | 内容 | 分类 |
|---|---|---|
| `service.py:728` | `chain_ratio = 今日连板数 / 今日涨停数`。昊哥 E04 的口径是“今日连板 / 昨日连板”，**同样是口径错误** | UNAUTHORIZED_INFERENCE（口径） |
| `service.py:731` | `chain_red = (feedback_score + 100) / 200`，由反馈分反推 | UNAUTHORIZED_INFERENCE（估算） |
| `service.py:732` | `chain_loss = 首板大面比 × 0.8` | UNAUTHORIZED_INFERENCE（估算） |
| `service.py:733` | `yest_red = 0.5`，常数 | UNAUTHORIZED_INFERENCE（默认值） |
| `service.py:735–742` | 无接力数据时，六项全部用涨跌家数估算（`first_red = min(0.8, r)` 等） | UNAUTHORIZED_INFERENCE（兜底） |
| `service.py:746` | 动能 = 六项线性加权（×2、×2、×2、×2、×2、×1）。昊哥的模型是每项按阈值 ±2 投票，**不是线性加权** | UNAUTHORIZED_INFERENCE（模型错配） |

---

## 2. L1 大环境

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| L1-01 | `market_regime/market_regime_fact_context_builder.py:169–177` `MarketRegimeFactContextBuilder.build` | report_context 没有 market 数据时，填入**默认快照**：上涨 2000、下跌 3000、涨停 30、跌停 10、接力 `normal`、炸板 `normal` | 用**虚构的市场数据**推出大盘和短线情绪状态，进而推出交易许可 | ShortTermSentiment → TradingPermission → PDV2、1进2 | UNAUTHORIZED_INFERENCE | 无 | 决策权威 | **P0** |
| L1-02 | 同文件 `:63–91` | 指数 K 线直接 `asyncpg.connect("postgresql://localhost/stock_data_test")` 读取 | 绕过 Gateway | BroadMarketRegime | （工程边界，见清单 2） | — | 决策权威 | P0（边界） |
| L1-03 | 同文件 `:93–111` | 数据库没有数据时，改用 akshare **实时**拉 `sh000001`，并取 `tail(lookback_days)`，**不按 trade_date 截断** | 回放历史日期时，会用到当天之后的指数数据（**未来函数**） | BroadMarketRegime | UNAUTHORIZED_INFERENCE | 无 | 决策权威 | **P0** |
| L1-04 | `market_regime/short_term_sentiment_engine.py:26–49` | 跌停 ≥30 → `dead`；跌停 ≥15 或炸板状态为 fade → `retreat`；涨停 ≥60 且跌停 ≤5 → `attack`；涨停 ≥30 → `normal` | 短线情绪分档 | TradingPermission | POLICY_UNFROZEN | 无。v0.6.4 只给了定性描述；昊哥阈值是外部参照 | 决策权威 | P1 |
| L1-05 | 同文件 `:45–46`（最后的 else） | 都不满足时 → `normal`，包括**没有任何数据**（涨停 0、跌停 0）的情况 | 缺失 → 正常 | TradingPermission | UNAUTHORIZED_INFERENCE | 无 | 决策权威 | **P0** |
| L1-06 | `market_regime/broad_market_regime_engine.py:32–41` | 宽度 = 上涨占比 ×0.5 + (涨停 − 跌停) ×0.5；综合分 = 宽度 0.25 + 指数 0.40 + 量能 0.20 + **常数 50** × 0.15 | 大盘综合分 | 诊断 / 展示 | POLICY_UNFROZEN | 无 | 仅展示 | P2 |
| L1-07 | 同文件 `:44–58` | bullish：趋势多头、宽度 ≥55、跌停 ≤5；bearish：宽度 <35，或跌停 ≥15 且涨停 <20；crash：跌停 ≥30 且宽度 <25；**其余全部 → neutral_choppy** | 大盘状态 | TradingPermission | POLICY_UNFROZEN；else 分支为 UNAUTHORIZED_INFERENCE | 无 | 决策权威 | P1 |
| L1-08 | 同文件 `:51–56` | `crash_risk` 判断排在 `bearish_adverse` 之后。宽度 <35 时先命中 bearish，crash 分支几乎走不到 | 分支顺序缺陷 | TradingPermission | （实现缺陷） | — | 决策权威 | P2 |
| L1-09 | `market_metrics/narrative_engine.py:393–409` `_phase_label` | 反馈分 <−40 退潮；<−10 分歧；<20 混沌；<50 修复；否则强势（前面另有三条“恐慌 / 冰点”升级规则） | 只用**一个变量**、没有前一状态，就决定大盘阶段 | `/api/v1/emotion` | POLICY_UNFROZEN | 无 | 仅展示 | P1 |
| L1-10 | `api_app.py:8057–8061` | 大盘阶段映射成 `ICE_POINT / FADE / DIVERGENCE / REPAIR / CHAOS / CLIMAX` | 用**题材周期词**描述大盘 | 前端情绪页 | UNAUTHORIZED_INFERENCE（作用域） | 与 v0.6.4 §4.3、§2.4 冲突 | 仅展示；与已批准语义冲突 | P1 |
| L1-11 | `market_metrics/service.py:704–705` | 活跃资金 × **2.04**（注释：按分析师 7/7、7/8 两天校准） | 两天样本拟合出的系数 | 展示 | UNAUTHORIZED_INFERENCE | 无 | 仅展示 | P2 |
| L1-12 | `market_metrics/service.py:125` | `data_quality_score = 0.85`（有上涨数据时）/ `0.5` | 数据质量分是常数 | 展示 | UNAUTHORIZED_INFERENCE | 无 | 仅展示 | P2 |

---

## 3. L2 主线身份

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| L2-01 | `mainline_discovery/mainline_discovery_engine.py:15, 31` | 引擎**不输出**已确认主线，只产出机器候选；确认由人工完成 | 身份确认归人工 | 分析师复核队列 | OWNER_APPROVED | 与 OP-03 一致：逻辑 + 持续市场认可，由 Owner 判断 | 合规 | — |
| L2-02 | 同文件 `:220` | 逻辑分 ≥80 且市场分 ≥45 → 建议复核 | 机器候选进入复核的门槛 | 复核队列 | POLICY_UNFROZEN | 无 | 只影响建议 | P2 |
| L2-03 | 同文件 `:231–232` | 市场分 ≥ `MARKET_NOISE_MARKET_MIN` 且逻辑分 <55 → 市场噪声；市场分 ≥75 → 复核 | 同上 | 复核队列 | POLICY_UNFROZEN | 无 | 只影响建议 | P2 |
| L2-04 | `mainline_discovery/mainline_market_acceptance_builder.py:8–10, 99–107` | `fade_risk ≥70`、龙头不存活、资金为负 → **硬否决，不能成为主线** | 身份确认被周期证据和龙头状态一票否决 | 发现引擎 | POLICY_UNFROZEN | 与 OP-03 “龙头高度不是身份前提”、OP-18 “身份 ≠ 周期”的方向有张力 | 只影响机器候选 | P1 |
| L2-05 | 同文件 `:294` | 龙头综合分 ≥60 算前排 | 前排计数 | 市场认可分 | POLICY_UNFROZEN | 无 | — | P2 |
| L2-06 | 同文件 `:304` | 涨幅 ≥9.5% 算涨停 | 用涨幅近似涨停，没有区分 20cm 和 ST | 涨停计数 | UNAUTHORIZED_INFERENCE（口径） | 无 | — | P2 |

---

## 4. L3 主线周期

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| L3-01 | `domain/services/subject_cycle_judgement_service.py:30–38` | 主线存活 60；退潮确认 60；分歧 60；修复 65；加速 75；发酵 60（另有 `THRESH_FADE_WATCH`） | **分数到阈值就换状态** | Layer B 判定表 → 周期复核 → 许可、1进2、强势股 | POLICY_UNFROZEN；“分数决定状态”这一机制本身与 v0.6.4 §4.7 冲突 | 无 | 决策权威 | **P0** |
| L3-02 | 同文件 `:110–130` | 优先级：退潮确认 → 修复 → 分歧 → 退潮观察 → 加速 → 发酵 → **其余全部为 `start`（默认）** | `start` 是**残差**，不是由正面证据识别出来的“初期” | 同上；许可层把 `start` 当成可交易 | UNAUTHORIZED_INFERENCE | v0.6.4 的 EARLY 需要正面证据（CS-03 p2：1–3 只涨停、板块异动、消息集中） | 决策权威 | **P0** |
| L3-03 | 同文件 `:108` | 修复只允许从 `divergence` 或 `fade_watch` 进入 | 前一状态记忆 | 同上 | divergence → repair：SOURCE_SUPPORTED（T10）；fade_watch → repair：POLICY_UNFROZEN（v0.6.4 没有 FADE → REPAIR 这条边） | CS-02、CS-03 | 决策权威 | P1 |
| L3-04 | 同文件 `:103–106` | 退潮确认 = 分数 ≥60 且证据 ≥3 条且支撑破位；接力 / 题材支撑 ≤35 计为证据 | 退潮判定 | 同上 | POLICY_UNFROZEN | CS-03 只有定性描述（大面积跌停、龙头连跌） | 决策权威 | P1 |
| L3-05 | 同文件状态集合 | 词汇是 `start / fermentation / acceleration / climax / divergence / repair / fade_watch / fade_confirmed / dead` | 与 v0.6.4 的对应：没有 CATCH_UP、ENDED；多出 fade_watch、fade_confirmed、dead | 全链 | UNAUTHORIZED_INFERENCE（词汇） | v0.6.4 §4.4 | 与已批准语义冲突 | P1 |
| L3-06 | `mainline_lifecycle/mainline_lifecycle_fact_context_builder.py:41–46` | 周期复核**只读取已确认主线** | 候选主线没有周期复核 | 许可层、1进2 | （结构问题，见 §10） | 与 OP-11、§5.5 冲突 | 与已批准语义冲突 | **P0** |
| L3-07 | `mainline_lifecycle/layer_b_lifecycle_adapter.py:98–111` | 缺少 Layer B 判定 → `alive = True`、`trade_alive = False` | 交易部分是缺失即关闭（好）；但“存活”是默认真 | 许可层 | 交易部分安全；`alive = True` 为 UNAUTHORIZED_INFERENCE | — | 决策权威 | P2 |
| L3-08 | 同文件 `:39–64` `_playability` | 各状态允许和禁止的战法；**未知状态默认为可交易 `standard`**（`:63–64`） | 未知 → 可交易 | 许可层、展示 | 状态表：POLICY_UNFROZEN；默认分支：UNAUTHORIZED_INFERENCE | 部分来自 CS-03 各阶段操作 | 决策权威 | P1 |
| L3-09 | 同文件 `:116` | `final_cycle_state` 缺失 → `"unknown"` → 走上一条的默认分支 | 缺失 → 可交易 | 同上 | UNAUTHORIZED_INFERENCE | — | 决策权威 | P1 |

---

## 5. L4 交易许可

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| L4-01 | `market_regime/trading_permission_engine.py:31–34` | 没有确认主线 → `allow_trade = False`、仓位 0、理由“无人工确认主线” | **关闭全部交易**，包括初期试错 | PDV2；1进2（`one_to_two_rule_engine.py:115`） | POLICY_UNFROZEN | 与 OP-01、OP-11、§5.5 冲突 | 决策权威；与已批准语义冲突 | **P0** |
| L4-02 | `market_regime/mainline_environment_engine.py:21–35` | 状态为 start / fermentation / acceleration / divergence / repair 且 trade_alive → 可交易；fade_watch → 只观察；fade_confirmed / dead → 退潮；**其余（包括 `unknown`）不归入任何一类** | 已确认的主线如果状态是 unknown，主线环境会落到 `no_confirmed_mainline`，**理由被错标成“无人工确认主线”** | TradingPermission | UNAUTHORIZED_INFERENCE（标签错误） | — | 决策权威 | P1 |
| L4-03 | 同文件 `:41` | 主线环境分 = `min(80, 存活数 × 25 + 30)`；否则 20 | 分数 | 展示 | POLICY_UNFROZEN | 无 | 仅展示 | P2 |
| L4-04 | `trading_permission_engine.py:67 / 76 / 84 / 91` | 仓位上限：下降反抽 0.2；情绪退潮 0.15；震荡 0.3；**默认 0.5** | 仓位上限 | PDV2 | POLICY_UNFROZEN（OP-16） | 无 | 决策权威 | P1 |
| L4-05 | 同文件 `:63–68` | 下降通道反抽 → 禁止“弱转强追买” | 弱转强被禁 | PDV2 | POLICY_UNFROZEN | 与 OP-20 的方向有张力：普通 RISK_OFF 不应自动否决弱转强 | 决策权威 | P1 |
| L4-06 | 同文件 `:71–77` | 情绪退潮：`allow_trade = True`，同时禁止“开新仓” | **自相矛盾** | PDV2；1进2 只看 allow_trade，会把它当成允许 | （实现缺陷） | — | 决策权威 | P1 |
| L4-07 | 同文件 `:87–92` | 都不命中时 → `mainline_active`、仓位 0.5 | 未知的大盘 / 情绪状态 → **最积极档** | PDV2；1进2 | UNAUTHORIZED_INFERENCE | — | 决策权威 | **P0** |
| L4-08 | `post_market_decision/trading_principle_engine.py:56–77` | 仓位 = 旧 MarketEnvironment 给出的 position_limit；有观察清单且仓位 >0 → 允许交易 | 旧链许可 | 日复盘 V2、前端、1进2（只检查存在） | LEGACY_ONLY | 无 | 旧链在线 | P1 |

---

## 6. L5 强势股与角色

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| L5-01 | `domain/services/strong_stock_tracking_service.py:379–388` | 入池：四项中满足三项；**或**题材承接且近期涨停 ≥2；**或** `has_two_board` **直接放行** | 两连板无需主线背景即可入池（`entry_path = independent_leader`，`:290–293`） | Layer C → PDV2、弱转强 | POLICY_UNFROZEN | R1 DR-013 | 决策权威 | P1 |
| L5-02 | 同文件 `:212–231` | 等级：近期涨停 ≥4 / ≥3 / ≥2；排名 ≤3 | 强势等级 | 弱转强基础分 | POLICY_UNFROZEN | 无 | 决策权威 | P1 |
| L5-03 | 同文件 `:277`、`:321` | 排名 ≤3 → `is_front_row_core` | 前排核心角色 | 弱转强、1进2 | POLICY_UNFROZEN | v0.6.4 §6.3 角色要求同一时点的相对排名，但名次线没有定 | 决策权威 | P1 |
| L5-04 | 同文件 `:375` | 趋势强度 ≥70 计一项 | 入池条件 | Layer C | POLICY_UNFROZEN | 无 | 决策权威 | P2 |
| L5-05 | 同文件 `:461` | 今日标记 <2 → 视为断板 | 移出 / 降级 | Layer C | POLICY_UNFROZEN | — | 决策权威 | P2 |

---

## 7. 1进2

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| OTO-01 | `domain/services/one_to_two_rule_engine.py:30–35` | 必需字段缺失 → reject | 缺失即拒绝 | 计划引擎 | OWNER_APPROVED（缺失不转通过） | v0.6.4 Part 13 | **合规** | — |
| OTO-02 | 同文件 `:38–39` | 既非主线也非强热点 → 否决 | 赛道条件 | 同上 | SOURCE_SUPPORTED | CS-04 p3、CS-01 | 合规 | — |
| OTO-03 | 同文件 `:102–103` | 周期为 fade_confirmed / dead → 否决 | 退潮不做 | 同上 | SOURCE_SUPPORTED（退潮放弃，CS-03 p3）；状态名为本地词汇 | CS-03 | 合规（词汇待对齐） | P2 |
| OTO-04 | 同文件 `:115–123` | 许可层 `no_trade` 或 `allow_trade = False` → 只观察 | 1进2 受 L4 许可约束 | 同上 | OWNER_APPROVED（受总闸约束是对的） | v0.6.4 §5.5 | 机制合规；但上游 L4-01 会把初期窗口整体关闭 | **P0（传导）** |
| OTO-05 | 同文件 `:125–127` | 非 confirmed_mainline → `pending_review_only`，“不得 focus” | 初期发现窗口被关闭 | 同上 | POLICY_UNFROZEN | 与 OP-11、§5.5 冲突 | 与已批准语义冲突 | **P0** |
| OTO-06 | 同文件 `:128–130` | 周期为 climax / fade_watch → 只观察 | 高潮警惕 | 同上 | climax：SOURCE_SUPPORTED（高潮警惕，CS-03 p3）；fade_watch：POLICY_UNFROZEN | CS-03 | 合规 / 未冻结 | P2 |
| OTO-07 | `domain/services/one_to_two_rule_config.py:25–26` | focus 换手下限 8%；否决下限 8% | 首板换手门槛 | 规则引擎 | POLICY_UNFROZEN（OP-10：8% 还是 15%） | CS-03、CS-04 p1 写 >8%；CS-04 p3、CS-08 写 ≥15% | 决策权威 | P1 |
| OTO-08 | 同文件 `:58–59`、`:65–66` | v1.2 / v1.3 版本中，否决下限降到 **5% / 3%** | 低于两份原文的任何一个数 | 规则引擎 | POLICY_UNFROZEN | 两份原文都没有支持 | 决策权威 | P1 |
| OTO-09 | 同文件 `:27` | 题材涨停数 ≥2 | 板块效应 | 规则引擎 | SOURCE_SUPPORTED | CS-04 p3（2–3 只助攻）、CS-08 p3 | 合规 | — |
| OTO-10 | 同文件 `:28` | 题材强势股 ≥5 才算广度 | 广度条件 | 规则引擎 | POLICY_UNFROZEN | 无 | 决策权威 | P2 |
| OTO-11 | `domain/services/one_to_two_scorer.py:41` | 等级：≥80 为 A；≥70 为 B | 等级 | 计划引擎 | POLICY_UNFROZEN | 无 | 决策权威 | P1 |
| OTO-12 | 同文件 `:63–66` | 换手 ≥15% 加 20 分；≥8% 加 10 分 | 把 C-05 的两个原文数字**同时**编成分档 | 评分 | POLICY_UNFROZEN（OP-10） | CS-03、CS-04、CS-08 | 决策权威 | P1 |
| OTO-13 | 同文件 `:67–68` | 成交额 ≥10 亿加 15 分 | 原文数值，但原文是**条件**，代码是**加分** | 评分 | SOURCE_SUPPORTED（数值）；形式上有偏离 | CS-04 p1 | 决策权威 | P2 |
| OTO-14 | 同文件 `:121–122` | 120 日位置 >0.65 扣 20 分 | “首板位置相对较高”的量化 | 评分 | POLICY_UNFROZEN（G-05） | CS-04 p2 定性 | 决策权威 | P2 |
| OTO-15 | `application/services/one_to_two_setup_plan_engine.py:61`、`:222`、`:295–299` | 综合分 ≥80 且技术分 ≥55 才 focus | focus 门槛 | 前端 OneToTwoWatchPanel | POLICY_UNFROZEN | 无 | 决策权威 | P1 |
| OTO-16 | `application/services/post_market_setup_fact_context_builder.py:43–47` | 缺少旧链的 `trading_principle` → **整个 1进2 构建报错** | 新链 1进2 依赖旧链输出存在（内容不用） | 1进2 | LEGACY_ONLY（依赖） | — | 切换阻碍 | P1 |
| OTO-17 | 同文件 `:52`、`:318–345` | 主线上下文只取 confirmed_mainline | 候选主线不进入 1进2 的主线上下文 | 1进2 | POLICY_UNFROZEN | 与 OP-11、§5.5 冲突 | 与已批准语义冲突 | **P0** |

---

## 8. 弱转强

### 8.1 D1 候选（两套生产者并存，见清单 2 §2.8）

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| W-01 | `application/use_cases/build_weak_to_strong_candidate.py:136` | 涨幅 >−1% 或涨停 → 排除 | “弱”被定义为跌幅 | API 选股（`api_app.py:911`） | LEGACY_ONLY | CS-05 的三种“弱”是：中大阴线、上影冲高回落、烂板，**不是固定跌幅** | 决策权威 | P1 |
| W-02 | 同文件 `:139` | 强势历史 = 龙头 OR 昨日涨停 OR 近期涨停 ≥1 OR 排名 ≤5 | 宽口径 OR | 同上 | POLICY_UNFROZEN | v0.6.4 要求龙头或核心 | 决策权威 | P1 |
| W-03 | 同文件 `:143–148` | 近 7 天涨停 ≥1；近 7 天强势 ≥1 | 涨停基因 | 同上 | POLICY_UNFROZEN | CS-07 是“近 6 天内有涨停” | 决策权威 | P2 |
| W-04 | 同文件 `:149` | 支撑强度 <45 → 排除 | 支撑条件 | 同上 | POLICY_UNFROZEN | CS-05 只有定性描述 | 决策权威 | P2 |
| W-05 | 同文件 `:83`、`:283–290` | 最多 **10** 只 | 候选上限 | 同上 | POLICY_UNFROZEN | 无 | 决策权威 | P2 |
| W-06 | 同文件（全文） | **没有**确认主线条件，也**没有**“分歧 → 修复”的周期条件；主线强度只作为加分（`:199–203`，≥75 / ≥60） | 弱转强资格里缺少主线和周期 | 同上 | UNAUTHORIZED_INFERENCE（缺少必需条件） | 与 v0.6.4 §5.5、OP-20 冲突 | 与已批准语义冲突 | **P0** |
| W-07 | `domain/services/w2s_candidate_service.py:222–230` | 周线数据不足 → `passed = True`（`weekly_data_insufficient_bypass`） | 缺失 → 通过 | 盘前简报 | UNAUTHORIZED_INFERENCE | — | 决策权威 | **P0** |
| W-08 | 同文件 `:506` | `strong_background` = 龙头 OR 涨停 OR 近期涨停 ≥2 OR 排名 ≤3 | 宽口径 OR | 同上 | POLICY_UNFROZEN | — | 决策权威 | P1 |
| W-09 | 同文件 `:512–519` | 前一状态未知 → 软通过（环境变量 `D_LAYER_ALLOW_UNKNOWN_PRIOR_STATE`，**默认 "1" 开启**） | 缺失 → 通过 | 同上 | UNAUTHORIZED_INFERENCE | — | 决策权威 | **P0** |
| W-10 | 同文件 `:194–205` | 修复 85；**退潮观察 75**；分歧 55 | 接近退潮的题材得分高于分歧 | 同上 | POLICY_UNFROZEN | 与 OP-20 方向相反（题材退潮 → 弱转强不成立） | 与已批准语义冲突 | P1 |
| W-11 | 同文件 `:379` | 强势等级缺失 → 默认 `"B"`（基础分 75，`:101`） | 缺失 → 中等偏上 | 同上 | UNAUTHORIZED_INFERENCE | — | 决策权威 | P1 |
| W-12 | 同文件 `:106–119` | 跌幅 −5%~−1% 得 90 分，其余分档 | 固定跌幅打分 | 同上 | LEGACY_ONLY | CS-05：弱是形态，不是跌幅 | 决策权威 | P2 |
| W-13 | 同文件 `:42` | 最多 **20** 只 | 候选上限，与 W-05 的 10 只不一致 | 同上 | POLICY_UNFROZEN | — | 决策权威 | P2 |

### 8.2 D2 竞价确认

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| W-14 | `domain/services/w2s_auction_scorer.py:120–124` | 等级 ≥75 / ≥65 / ≥55 | 竞价分级 | W2SConfirmService → 盘前简报、API | POLICY_UNFROZEN | 无 | 决策权威 | P1 |
| W-15 | 同文件 `:99–106` | 竞价额 <50 万、承接 <0.3、稳定度 <40 → 加风险分 | 风险分 | 同上 | POLICY_UNFROZEN | — | 决策权威 | P2 |
| W-16 | 同文件 `:113–118` | 高开 >7% 且承接 <0.5 → 最高只能 C | 高开陷阱 | 同上 | POLICY_UNFROZEN | 和原文相关但不等同：CS-06 讲“高开 3–5% 概率高”；CS-04 的 7–8% 是 1进2 次日离场条件 | 决策权威 | P2 |
| W-17 | 同文件 `:161–165` | 量比 ≥1.0 / ≥0.5 / ≥0.3 | 竞价量与昨日最大分钟量之比 | 同上 | 0.5：SOURCE_SUPPORTED（CS-06 p6，½）；1.0 / 0.3：POLICY_UNFROZEN | CS-06 p6 | 决策权威 | P2 |
| W-18 | `domain/services/w2s_confirm_service.py:63–65` | 开盘 <−2% 或成交额 <50 万 → 否决 | 确认失败 | 同上 | POLICY_UNFROZEN | — | 决策权威 | P2 |
| W-19 | `domain/services/auction_confirmation_service.py:16–18` | A ≥75 确认；B ≥55 观察 | 另一套竞价打分 | **只用于回测** | POLICY_UNFROZEN | — | 诊断 | P2 |

---

## 9. 旧决策链

| # | 位置 · 符号 | 规则 / 数值 | 实际作用 | 消费者 | 分类 | 来源 | 状态 | 风险 |
|---|---|---|---|---|---|---|---|---|
| LEG-01 | `post_market_decision/theme_decision_engine.py:195–198` | 主线 ×0.35 + **大盘环境** ×0.30 + 龙头 ×0.20 + 战法 ×0.15 | 把重要性顺序做成了加权分；而且 30% 被接到**大盘环境**上，原文的 30% 是**主线周期情绪**（v0.6.4 M-11） | 复盘文档 `theme_decision_reviews` → 日复盘 V2 透传 | LEGACY_ONLY | 与 v0.6.4 §1.2 冲突 | 旧链在线；与已批准语义冲突 | P1 |
| LEG-02 | `post_market_decision/leader_core_engine.py:50` | 资金分 ×0.30 计入龙头分 | 龙头加权 | `strong_stock_decision_reviews` | LEGACY_ONLY | — | 旧链在线 | P2 |
| LEG-03 | `post_market_decision/trading_principle_engine.py:41–48` | 无数据时：仓位 0、不允许交易 | 缺失即关闭 | 1进2（存在检查）、日复盘 V2 | LEGACY_ONLY（缺失即关闭本身是安全的） | — | 旧链在线 | P2 |

---

## 10. 汇总

### 10.1 按分类（本清单共 86 条：§1 七条 + §2–§9 七十九条）

| 分类 | 条数 | 其中 P0 |
|---|---|---|
| SOURCE_SUPPORTED（含部分支持） | 7 | 0 |
| OWNER_APPROVED | 3 | 1（OTO-04：机制本身合规，P0 是从上游 L4-01 传导下来的） |
| EMPIRICAL_CANDIDATE | 0 | 0 |
| POLICY_UNFROZEN | 41 | 4 |
| LEGACY_ONLY | 7 | 0 |
| UNAUTHORIZED_INFERENCE | 24（§1 七条 + 其余十七条） | 8 |
| 未归类：结构、工程边界、实现缺陷（L1-02、L1-08、L3-06、L4-06） | 4 | 2 |

（同一条目带两个分类时，按单元格里先出现的那个计数。）

**没有一条是 EMPIRICAL_CANDIDATE。** 代码里的数字，没有一个附带“由哪段数据、哪次回放得出”的记录。唯一自称“校准”的 ×2.04，样本只有两天。

### 10.2 “缺失或估算 → 正式结论”专项（Phase A 第 3 项的对象）

| # | 位置 | 缺失或估算了什么 | 变成了什么 |
|---|---|---|---|
| 1 | `market_regime_fact_context_builder.py:169–177` | 市场快照 | 虚构“上涨 2000、涨停 30、正常” → 交易许可 |
| 2 | `market_regime_fact_context_builder.py:93–111` | 指数 K 线 | 实时数据，不按日期截断 → 回放时出现未来函数 |
| 3 | `short_term_sentiment_engine.py:45–46` | 全部情绪数据 | `normal` |
| 4 | `broad_market_regime_engine.py:57–58` | 不命中任何条件 | `neutral_choppy` → 仓位 0.3 |
| 5 | `trading_permission_engine.py:87–92` | 未知状态 | 最积极档、仓位 0.5 |
| 6 | `layer_b_lifecycle_adapter.py:63–64`、`:116` | 周期状态缺失或未知 | 可交易 `standard` |
| 7 | `mainline_environment_engine.py:21–35` | 已确认主线的状态为 unknown | 被标成“无人工确认主线” |
| 8 | `w2s_candidate_service.py:222–230` | 周线数据 | `passed = True` |
| 9 | `w2s_candidate_service.py:512–519` | 前一周期状态 | 软通过（默认开启） |
| 10 | `w2s_candidate_service.py:379` | 强势等级 | `"B"` |
| 11 | `market_metrics/service.py:731–742` | 连板红盘、连板大面、昨日连板绿盘、全部接力数据 | 由其他量反推，或用常数代替 |
| 12 | `subject_cycle_judgement_service.py:128–130` | 没有任何正面证据 | `start`（被当成初期、可交易） |

### 10.3 与已批准语义冲突（v0.6.4 Part 15.1）

L1-10、L3-05、L3-06、L4-01、OTO-05、OTO-17、W-06、W-10、LEG-01。

---

## 11. 未覆盖（下一轮再补）

- **题材 → 事件匹配链**：R1 判为保留，本轮没有逐条盘点。
- **M8 / market_cognition**（`cognition.py`、`replay.py`）和 `analyst_alignment/turing_score.py`：本轮只确认了它们存在，没有逐条盘点。
- **盘中预警系列**（`w2s_*alert_service*`、`kline_break_detector`）的阈值：本轮只盘点了边界问题，见清单 2。
- **PDV2 内部规则**（`post_market_decision_engine_v2.py`）：只确认了它消费许可层的 `allow_trade` 和 `position_limit`（`:68–70`），内部的选股规则没有逐条盘点。
- **采集口径问题**：成交额单位 ×10、涨停总数用“触板”口径等，在 `MARKET_EMOTION_QUANT_AUDIT_AND_DESIGN_v0.1` 中已有记录，这里不重复。

# 市场情绪量化：现状审计与重设计建议 v0.1

> **作者**: Mira（Claude）　**日期**: 2026-10-06
> **范围**: 分析师工作台复盘报告中的情绪分析（`~/Desktop/ai_theme_app/tmp/analyst_workbench`，2026-07-01 至 09-24，共 62 个交易日），以及 `glm-workspace/ai_theme_app` main @ `ddc9442e8` 中情绪相关的代码
> **对照**: `AI_THEME_APP_STRATEGY_MODEL_AND_EXECUTABLE_CONTRACT_v0.5.0`（Part IV、Part VI）；EXT-01 昊哥复盘 7/1–7/9
> **方式**: 只读。没有运行代码，也没有连接数据库。结论来自源码阅读和 62 份 `review_document.json` 的统计
> **证据分级**: ✅ 已查证（给出文件、行号或数据）；🔶 推断；❓ 未知

---

## 0. 结论先行

1. **方向是对的，但目前的“情绪阶段”还不能用来做决策。** ✅
   62 个交易日里：
   - 36 天判为 CHAOS（58%），4 天判为 ICE_POINT；
   - **CLIMAX、ACCELERATION、FERMENTATION 一次都没出现过**，系统实际上识别不了情绪周期的上半段；
   - 7/17 之后，情绪分数只落在 {-57, -28, 0, 28, 57, 85} 六个离散值上。
2. **阶段是由一个变量切出来的，而且没有记忆。** ✅
   生产路径的阶段 = `NarrativeEngine._phase_label()`，基本只看 `feedback_score`（昨日涨停股今天的表现）。情绪周期本来是一条有方向的路径：同一个分数，可能是上行中的“修复”，也可能是下行中的“分歧”。一维阈值表达不了这种区别。
3. **一半的“六因子情绪动能”不是测出来的，是编出来的。** ✅
   - 三个因子是估算值或常数；
   - 一个因子名不副实：叫“首板红盘比”，实际算的是“昨日涨停今日继续涨停”的比例；
   - 但这些数仍标着置信度 0.85、`validation_status=verified`。
4. **单位和口径错误，已经影响到报告结论。** ✅
   - 全市场成交额放大了 10 倍（显示为 28.9 万亿），7/10 之后 55 天成交额为 0；
   - 活跃资金靠一个用 2 天数据拟合出来的系数 ×2.04 来“对齐”；
   - “涨停数”用的是“触及”口径，和参考口径（收盘封住）不同：7/2 我们是 156 家，昊哥是 93 家。
5. **有四套互不一致的阶段词表、两套互不相同的情绪引擎。** ✅
   其中一个引擎（`emotion_engine.py`）是死代码，阈值还和生产路径不同。
6. **建议**：分四层重建：测量 → 维度 → 阶段状态机 → 权限。
   - 先修数据（E0），用 62 天数据重算并和昊哥逐项对账（E1）；
   - 由 Tony 给这 62 天标注阶段，作为真值（E2）；
   - 再做带路径依赖和滞后的状态机（E3）。
   - **在 E2 的标注完成之前，任何阈值都不冻结。**

---

## 1. 现状：生产路径实际怎么算

```text
GET /api/v1/emotion/{date}                        api_app.py:8025 起
  └─ MarketMetricsService().get_async(td)          market_metrics/service.py
  └─ NarrativeEngine().generate(snap)              market_metrics/narrative_engine.py
       emotion_node   = phase_map[_phase_label(r, leader, loss)]   # 6 个中文标签 → 英文节点
       emotion_score  = momentum_normalized
       breadth_score  = momentum_normalized        # ← 复制了同一个值
       capital_score  = active_ratio * 1000
       style_score    = death_index                # ← 字段名与内容不符
  └─ scripts/generate_analyst_workbench.py → EmotionReviewBuilder → draft → review_document.json
```

`_phase_label`（narrative_engine.py:393）：

```text
亏钱效应 恐慌/严重              → 恐慌/冰点
fb < -40 且亏钱 明显以上        → 恐慌/冰点
龙头 COLLAPSE                   → 恐慌/冰点
fb < -40 → 退潮；fb < -10 → 分歧；fb < 20 → 混沌；fb < 50 → 修复；否则 → 强势
```

> `market_cognition/emotion_engine.py`（MarketEmotionEngine，五层加权）在仓库中**没有任何调用方**。✅ 它连接的是硬编码的 `stock_data_test` 库，阈值和生产路径也不同。

---

## 2. 问题清单

### 2.1 阶段判定（模型层面）

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| P-01 | 阶段 = 单变量（feedback_score）分段，没有记忆 | narrative_engine.py:393–415 | 识别不了方向：“冰点后修复”和“高潮后分歧”分不开 |
| P-02 | “混沌”被当成中间分数段 | `-10 ≤ fb < 20 → 混沌` | 原文中混沌的意思是“没有主线、等待新题材”，不是“分数中等”。结果 58% 的天数被判为混沌 |
| P-03 | 识别不了上半周期 | 62 天中 CLIMAX/ACCELERATION/FERMENTATION 为 0 次 | 原文中的高潮止盈、加速持有等动作无法触发 |
| P-04 | 与盘面明显矛盾 | 7/21：120 家涨停、上涨 3107/下跌 2301、活跃资金 3499 亿（62 天最高），却判为 **ICE_POINT / EXTREME /“全面防守”**（fb=-41.7，因为 7/20 的涨停股今天表现差）。7/29：上涨 78%、大盘势能 9，风险却是 EXTREME | feedback 衡量的是“昨天那批涨停股”，不是今天的市场。新周期第一天恰好最容易被误判 |
| P-05 | 风险等级语义反了 | `EmotionReviewBuilder._risk_level`：score>40 → LOW | 原文：高潮是**高风险**（止盈离场），冰点才是机会和风险并存 |
| P-06 | 策略文字由阈值直接产生，悄悄替 Owner 做了决定 | 引擎写“冰点试错：若出现新题材……可重点观察”；加速/高潮写“只做低位补涨方向”；`fb<30` 允许“补涨” | 冰点政策在 v0.5 中是 SC-06/OF-05 待定项；补涨在原文中是“尽量少参与”（CS-03 p3） |
| P-07 | 四套阶段词表 | emotion_engine（8 个）、EmotionReviewBuilder.NODE_LABELS（8 个，含 REBOUND，与引擎的 REPAIR 不对应，且 DIVERGENCE 被标成“情绪退潮”）、NarrativeEngine（6 个中文）、phase_ontology（M8，13 个以上） | 报告中同时出现 REPAIR_WATCH、REBOUND、DECAY、REPAIR，无法统计、无法对齐 |

### 2.2 测量值（数据层面）

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| M-01 | “首板红盘比”实际是“昨日涨停今日继续涨停比” | service.py `_build_momentum`：`first_red = relay.continue_ratio` | 7/9 显示“首板红盘比 11%”，口径错误 |
| M-02 | 连板红盘比由 feedback_score 反推 | `chain_red = (feedback_score+100)/200` | 不是测量值，而且和 feedback 重复计入 |
| M-03 | “昨日连板未涨停绿盘比”是常数 | `yest_red = 0.5`（fallback 时为 0.3） | 同上 |
| M-04 | 连板大面比 = 首板大面比 × 0.8 | `chain_loss = first_loss * 0.8` | 同上 |
| M-05 | 全市场成交额单位错 10 倍 | `normalize_to_yi(raw, "wan")`；7/9 结果为 289,258 亿（28.9 万亿）；A 股日成交在 2–3 万亿量级（EXT-01 7/7：“成交量 2.5W 亿”） | 活跃资金占比被算成 0.9%（实际约 9%），`_narrate_capital` 中的 0.03 阈值因此失效 🔶（原始单位应是千元，需查库确认） |
| M-06 | 7/10 之后成交额为 0 | 62 天中 55 天 `total_amount_yi = 0` | 资金维度静默失效，没有报 BLOCKED |
| M-07 | 活跃资金靠拟合系数 | service.py：`* 2.04`，注释写“用 7/7、7/8 两天校准” | 掩盖了口径或单位问题；两个样本点的拟合没有统计意义 |
| M-08 | 活跃资金有三种定义 | registry：“涨幅≥5% 股票成交额”；代码：涨停池（ths_hot_reason）JOIN；chart 文档字符串：涨停/触板 | 而且 JOIN 只匹配 .SZ/.SH，北交所被漏掉 |
| M-09 | 活跃资金的标签和解读自相矛盾 | active_capital_chart：标签按“亿”判断（>2000 → 资金扩张），解读按“万亿”判断（≤0.6 → 短线资金收缩） | 7/9 报告同时写着“资金扩张”和“短线资金收缩，参与度下降” |
| M-10 | 涨停数口径 | registry `limit_up_total_count` = 触及（封住+炸板） | 与昊哥口径（收盘涨停）对比：7/1 221 vs 151；7/2 156 vs 93；7/3 156 vs 105；7/8 56 vs 46。连板 7/2 55 vs 18 ❓（连板差异的原因待查） |
| M-11 | 大盘势能公式过拟合且饱和 | market_power_chart：中性点 50/0.40/8 是“对 7/1–7/8 反推”的，截断在 ±10。7/1–7/3 都是 10，**7/2 韩国暴跌日我们给 10“强势”，昊哥是 -2**；注释声称“7/1≈6、7/7≈-6”，实际输出 10 和 -3 | 公式连自己声称的校准都复现不了 |
| M-12 | registry 文档过期 | `promotion_1_to_2` 写的是 “streak≥2 / streak≥1”，代码 v4 实际是“昨日首板 ∩ 今日 ≥2 板 / 昨日首板” | 代码是对的，文档会误导后来的人 |

### 2.3 治理

| # | 问题 | 证据 |
|---|---|---|
| G-01 | ASSESSMENT 被标成 `verified, confidence 1.0` | review_document.field_provenance["emotion.score"] |
| G-02 | 阈值写死在领域逻辑里 | 所有 builder 与 engine |
| G-03 | 硬编码 DSN | emotion_engine.py:`postgresql://localhost:5432/stock_data_test` |
| G-04 | 校准参考写死在代码里 | calibration.py：`build_20260707_calibration_ref()`、`build_20260708_calibration_ref()` |
| G-05 | 真值太少 | 工作台 62 天中只有 5 天 APPROVED（7/14、7/16、9/04、9/23、9/24），1 天 IN_REVIEW |

---

## 3. 设计原则

1. **四层分离，单向依赖**：测量（事实）→ 维度（标准化特征）→ 阶段（状态机）→ 权限（查表）。任何一层都不能跳层。
2. **测不到就是 UNKNOWN**：禁止估算值、常数补位、反推值冒充测量值。缺数据 → 对应维度 UNKNOWN → 阶段 UNCLASSIFIED，并且显式报出来。
3. **不加总**：维度之间不做加权求和（v0.5 INV-001）。阶段由“各维度的水平和方向 + 前一阶段”共同决定。
4. **阶段有记忆**：合法转移表 + 滞后（进入和退出用不同条件，或者需要确认日）。
5. **目标是复现判断，不是复现数字**：昊哥的综合值是不公开的打分。我们要对齐的是**阶段和动作**，而且以 Tony 的标注为最终真值，不拿他的分数拟合系数。
6. **策略文字只来自权限表**（v0.5 §6.3 动作矩阵），不能由分数阈值直接生成。
7. **市场层和题材层分开**：本文件只做市场层（v0.5 L1 `MARKET_EMOTION_STATE`）。题材的情绪周期是 L3，留到之后单独做。

---

## 4. 第一层：测量值（修正后的规范）

在 v0.5 MKT-M01–M18 的基础上，补充口径。**同时保留两种涨停口径，下游必须声明自己用哪一种。**

| ID | 名称 | 精确定义 | 现状 | 动作 |
|---|---|---|---|---|
| E-M01 | limit_up_sealed | 收盘涨停家数 | 有 sealed_count | 作为默认“涨停数”，与昊哥对齐 |
| E-M02 | limit_up_touched | 盘中触及涨停家数 | 现在的 total_count | 改名，不再叫“涨停数” |
| E-M03 | broken_rate | (touched − sealed) / touched | 有 | — |
| E-M04 | limit_down | 收盘跌停家数（按板块涨跌幅规则，不用 -9.5% 一刀切） | -9.5% | 按 market_rule_policy 修正 |
| E-M05 | up / down / flat | 全 A（含北交所，排除停牌） | TDX 已接 | 明确 universe |
| E-M06 | down_5pct | 跌幅 ≥5% 家数 | ❓ | 补 |
| E-M07 | loss_effect_ratio | down_5pct / limit_up_sealed | 无 | 补；与 EXT-01 恒等式校验 |
| E-M08 | turnover_total_yi | 全市场成交额（亿元） | 单位错，且 55 天为 0 | 修单位；合理区间校验 |
| E-M09 | active_capital_yi | 收盘涨停 + 触及涨停个股的成交额之和（亿元） | ×2.04 | 去掉系数，修 JOIN（含北交所），只留一个定义 |
| E-M10 | promotion_k | 昨日 k 板 ∩ 今日 ≥k+1 板 / 昨日 k 板 | v4 正确 | 修 registry 文档 |
| E-M11 | prev_first_red_ratio | 昨日首板今日**收盘收红**比例 | 被 continue_ratio 冒名 | 按定义重算 |
| E-M12 | prev_first_continue_ratio | 昨日首板今日继续涨停比例 | 即现在的 continue_ratio | 改名保留 |
| E-M13 | prev_first_big_loss_ratio | 昨日首板今日跌幅 ≥ X 的比例（X 见 v0.5 TH-025） | 有 | 冻结 X |
| E-M14 | prev_chain_red_ratio | 昨日连板今日收红比例 | 由 fb 反推 | 按定义重算 |
| E-M15 | prev_chain_big_loss_ratio | 昨日连板今日大面比例 | ×0.8 | 按定义重算 |
| E-M16 | prev_chain_not_limit_green_ratio | 昨日连板今日未涨停且收绿比例 | 常数 0.5 | 按定义重算 |
| E-M17 | max_height / second_height / gem_height | 最高板、次高板、创业板高度 | 有最高板 | 补次高 |
| E-M18 | high_death | 昨日 ≥3 板今日跌幅 ≥ X 的家数 | 有 death_index | 明确口径 |
| E-M19 | index_state | 三大指数相对 5/10/20/60 日线、连续阴线数 | regime 模块有 | 接入 |
| E-M20 | external_anchor | KOSPI 日涨跌、距高点回撤 | 无 | OF-04 批准后补 |

**每个测量值必须带**：`unit`、`universe`、`source`、`as_of`、`null_reason`。

**校验（DQ）**：
- `0 ≤ ratio ≤ 1`；`sealed ≤ touched`；`active_capital ≤ turnover_total`；
- `turnover_total` 在合理区间内（建议 5,000–60,000 亿；超出就 BLOCKED，不能静默）；
- 恒等式 `loss_effect_ratio × sealed == down_5pct`。

---

## 5. 第二层：四个正交维度

不再做一个总分，改成四个维度。每个维度输出两样东西：

- **水平**：相对过去 N 个交易日（建议 120 天）的分位数；
- **方向**：相对昨日和 5 日均值的变化，取 UP / FLAT / DOWN。

| 维度 | 含义 | 输入 | 备注 |
|---|---|---|---|
| D1 宽度 / 赚钱效应 | 全市场今天赚不赚钱 | up 比例、down_5pct、loss_effect_ratio、limit_down | 今天的横截面 |
| D2 接力反馈 | 昨天进场的人今天赚不赚钱 | promotion_1→2、2→3，prev_first_red / big_loss，prev_chain_red / big_loss | 昨日队列，**滞后一天** |
| D3 高度 / 龙头 | 空间有没有打开 | max_height、次高、high_death、leader_health | 题材龙头的细节留给 L4 |
| D4 资金 | 短线资金在进还是在退 | active_capital、turnover_total、active/total 占比 | 修完单位之后才可用 |

为什么要把 D1 和 D2 分开：现在的错误，大多是把“昨日队列的反馈”（D2）当成了“今天的市场”。7/21 就是例子：D1 很强（新周期开始），D2 很差（旧周期的接力在死亡）。原文的说法正好对应这种情况：**“龙头往往诞生在情绪冰点后第一波反弹”**（CS-07 p3）。系统必须能同时看到这两个维度。

---

## 6. 第三层：市场情绪状态机（PROPOSED，阈值待标注后冻结）

状态沿用 v0.5 §4.3.1，加上冰点之后的确认态：

```text
ICE_POINT → REPAIR → EXPANSION → CLIMAX → DIVERGENCE → RETREAT → ICE_POINT
                ↘ (修复失败) RETREAT
UNCLASSIFIED（数据不足或阈值未冻结；替代现在被滥用的 CHAOS）
```

> CHAOS 不进入市场层：原文中的“混沌期”指的是没有主线，属于 L2/L3 题材层的状态。

草案规则（P = 分位数；全部是 PROPOSED，不是结论）：

| 目标状态 | 进入条件（同时满足） | 允许的前序状态 | 确认 |
|---|---|---|---|
| ICE_POINT | D1 ≤ P10 且 D2 ≤ P10（或 D1 ≤ P5 单独成立） | RETREAT、DIVERGENCE、任意（极端时） | 当日 |
| REPAIR | D1 方向 UP 且水平 ≥ P40；D2 方向 UP | ICE_POINT、RETREAT | 需要第 2 天 D1 不回落到 P20 以下，否则回到 RETREAT |
| EXPANSION | D1 ≥ P60，D2 ≥ P50，D3 高度在抬升 | REPAIR | 连续 2 天 |
| CLIMAX | D1 ≥ P90 或 limit_up_sealed ≥ P95；D4 ≥ P90；D3 达到窗口内最高 | EXPANSION | 当日 |
| DIVERGENCE | 前一状态是 EXPANSION 或 CLIMAX，且 D2 方向 DOWN、broken_rate 上升或高度首次降级 | EXPANSION、CLIMAX | 当日 |
| RETREAT | D2 ≤ P20 且 D1 方向 DOWN，或 high_death 达到 ≥ P90 | DIVERGENCE、REPAIR（修复失败） | 当日 |

**滞后**：
- 退出 CLIMAX、EXPANSION 需要 2 个条件同时成立；
- 进入 REPAIR 需要确认日；
- 如果某天的盘面符合某个状态，但这次转移不在合法表里，记为 `TRANSITION_CANDIDATE`，等第二天再判断，不强行跳转。

**输出**：

```json
{
  "state": "REPAIR",
  "prev_state": "ICE_POINT",
  "days_in_state": 1,
  "confirmed": false,
  "dimensions": {"D1": {"pctl": 0.72, "dir": "UP"}, "D2": {"pctl": 0.18, "dir": "UP"}, "...": {}},
  "rule_fired": "MKT-FSM-REPAIR-01",
  "threshold_policy_version": "exploratory-2026-10",
  "conflicts": ["D1_strong_D2_weak"]
}
```

`conflicts` 就是给分析师看的“分歧信号”，比如“新周期起来了，旧接力在死”。这类信息只是提醒，不应该由系统替人做结论。

---

## 7. 第四层：权限与风险（替代现在的策略文字和 risk_level）

直接引用 v0.5：§4.4（MKT-001–008）、§6.3（动作矩阵）、§8.2（准入矩阵）。

- `risk_level` 改成**新开仓风险**，由状态推出：
  - CLIMAX、DIVERGENCE、RETREAT → HIGH；
  - ICE_POINT → 由 OF-05 决定；
  - REPAIR 未确认 → MEDIUM。
- 删除所有“只做低位补涨”“冰点试错”之类、由分数阈值生成的策略文字，改为从权限表渲染。

---

## 8. 校准与验证

1. **真值**：Tony 对 62 个交易日逐日标注**市场情绪状态**，可以只用 6 个状态，加一个“我也拿不准”。现有的 5 个 APPROVED 日先作为种子。7/1–7/9 有昊哥原文，可以一起对照。
2. **预注册**：在看结果之前写定：
   - 时间切分：前 40 天用于设定分位阈值，后 22 天用于验证；
   - 指标：混淆矩阵、逐状态的召回率；
   - 判定线，例如“验证集上 ICE_POINT、CLIMAX、RETREAT 的召回率 ≥ 0.6，且不出现 ICE_POINT 与 CLIMAX 互相误判”。
3. **对账，而不是拟合**：对 7/1–7/9 逐项比较 E-M01、M07、M09、M10，与昊哥差异超过 5% 的必须给出口径解释。禁止为了对齐引入新的乘法系数。
4. **样本量要说实话**：62 天里大概只有 2–3 个完整周期，能支持“方向性”结论，不足以冻结阈值。冻结（OF-11）前至少再积累一个季度，或者回补 2026 年上半年的数据。

---

## 9. 工程建议

| # | 建议 |
|---|---|
| W-01 | 只保留一个 owner：`MarketEmotionService`（基于 MarketMetricsService）；删除 `market_cognition/emotion_engine.py`，或者明确标为 donor |
| W-02 | 一个阶段枚举，与 v0.5 共用；phase_ontology 只负责把外部或 AI 的标签映射进来 |
| W-03 | `/api/v1/emotion` 修正字段：`breadth_score` 不再复制 momentum；`style_score` 不再装 death_index |
| W-04 | 测量值改名：continue_ratio 与 first_red_ratio 分开；`limit_up_total_count` 改为 `limit_up_touched_count` |
| W-05 | 删除所有估算或常数补位，改为 null + `null_reason` |
| W-06 | 阈值移到版本化的 threshold policy；领域逻辑中不出现字面量 |
| W-07 | provenance：ASSESSMENT 记录规则 ID、输入快照 digest、策略版本；不允许写 `verified, 1.0` |
| W-08 | 数据缺失时 fail closed：成交额为 0 时资金维度报 UNKNOWN，而不是输出“冰点低量” |
| W-09 | 测试：恒等式与区间校验；单元测试覆盖 7/2、7/7、7/21 三个典型日 |

---

## 10. 执行顺序

| 阶段 | 内容 | 产出 | 谁 |
|---|---|---|---|
| E0 | 修 M-01–M-12、G-01–G-03（单位、伪造因子、口径、命名） | PR；62 天重算的测量值表 | Claude 开发，Tony 本机跑数据库 |
| E1 | 7/1–7/9 与昊哥逐项对账；62 天维度时间序列 | 对账报告 | Claude |
| E2 | Tony 标注 62 天市场情绪状态 | 标注表（CSV） | Tony |
| E3 | 状态机 v1，按预注册规则验证 | 混淆矩阵与误判清单 | Claude |
| E4 | OF-11 冻结阈值，或者决定继续积累样本 | Owner 决策 | Tony |

---

## 补遗 v0.1.1（2026-10-06，对照 ChatGPT 反馈后的更正与补充）

### 更正

- **M-13（新增，原文遗漏）**：`first_board_success_rate` 在 service.py:452 的计算是 `first_count / total`，也就是“首板占全部涨停的比例”（首板占比）；但 relay_ecology_chart 把它显示为“首板封板率”。✅ 应拆成 `first_board_share`（首板占比）和 `first_board_seal_rate`（首板最终封住数 / 首板盘中触板数）两个字段。
- **情绪产出方不止两个**：除生产路径（MetricsService + NarrativeEngine）和死代码 emotion_engine 外，还有 `analyst_charts/diagnosis_engine.py`、`domain/services/market_regime/short_term_sentiment_engine.py`、`domain/policies/cycle_fsm.py` + `config/market_cognition/cycle_fsm_v1.yaml`，各有自己的阈值和阶段词表。✅（文件存在已确认；具体规则尚未逐行审）

### 不应作为真值的证据

- `frontend/public/api/emotion-2026-07-09.json`（提交 9e35ba341，提交信息只有“更新”，2026-07-10）：
  - `emotion_node = REBOUND`，但同一文件里 `emotion_desc` 和 `raw.phase` 都是“混沌”；
  - `strategy_bias` 是昊哥原文“看 1–3 天的反弹……快进快出”的改写；
  - `active_capital_yi = 5058.28`，而工作台 review_document 是 2665，昊哥是 2707。
  
  它是一份按日期手工修过的静态产物，不是 producer 推导出来的结论，不能作为真值；它本身就是“不准做按日期打补丁”这条规则要防的情况。
- 不同产物之间的同一事实不一致：7/7 跌停数，某处为 83，工作台为 69。对账表中每个数字都必须注明出自哪个产物、哪个版本。

### 采纳的设计调整

- 三个作用域严格分开：`MarketEmotionState` ≠ `ThemeLifecycleState` ≠ `LeaderState`，各用各的枚举，不共享 CycleNode。
- 市场层状态：ICE_POINT、REPAIR_WATCH、REBOUND、EXPANSION、CLIMAX、DIVERGENCE、RETREAT，加上 UNCLASSIFIED。
  - REPAIR_WATCH 与 REBOUND 替代原 §6 的“REPAIR 未确认/已确认”；REBOUND（反弹）与 EXPANSION（反转扩散）分开，正对应昊哥“只是反弹，不是反转”的区分。
  - CHAOS 不进入市场层（保留 v0.1 的意见：混沌指没有主线，属于题材层）。
- 每个维度保存 level_t、delta_1d、delta_3d、slope_3d、percentile_20d、percentile_120d。
- 下一步先做只读的对账任务 `MARKET_EMOTION_QUANTIFICATION_RECONCILIATION_P0`，不改生产代码，代替原 §10 的 E0。

### 真值协议（依据 Tony 2026-10-06 的意见：昊哥更接近市场，但也会失误）

| 字段 | 含义 | 用途 |
|---|---|---|
| label_analyst_ext | 昊哥当日原文映射出的状态（保留原话与出处） | 主标签 |
| label_owner | Tony 的裁定：ACCEPT，或 OVERRIDE + 理由 | 最终标签 |
| outcome_t1_t3 | T+1 至 T+3 的实际结果（接力反馈、宽度、指数） | **只用于评估**昊哥、Tony、系统三方，不能当作 T 日标签（会引入未来信息） |
| analyst_error_flag | 结果与昊哥判断明显相反、且 Tony 认定为失误 | 保留，不删除；用于研究专家在哪些情境下会错 |

## 附录 A：62 天现状统计（来自 review_document.json）

- 阶段分布：CHAOS 36，REPAIR 11，DIVERGENCE 7，ICE_POINT 4，REPAIR_WATCH 2，REBOUND 1，DECAY 1。
- 分数分布（前 8）：-28 ×12，28 ×12，57 ×9，-57 ×7，0 ×6，85 ×4，39 ×3，41 ×2。
- `total_amount_yi = 0` 的天数：55。
- 与盘面明显矛盾的天：7/21（120 家涨停 → ICE_POINT/EXTREME）；7/29（上涨 78%、势能 9 → EXTREME）；8/20（势能 7 → DIVERGENCE/EXTREME）；7/2（韩国暴跌日 → 大盘势能 10“强势”）。

## 附录 B：7/1–7/9 与昊哥对照

| 日期 | 涨停（我们/昊哥） | 大盘势能（我们/昊哥） | 活跃资金（我们/昊哥） | 我们的阶段 |
|---|---|---|---|---|
| 7/01 | 221 / 151 | 10 / 6 | 2193 / 2279 | CHAOS |
| 7/02 | 156 / 93 | 10 / -2 | 1115 / 1146 | CHAOS |
| 7/03 | 156 / 105 | 10 / 2 | 2078 / 2122 | CHAOS |
| 7/06 | 71 / 64 | -1 / -6 | 1251 / 1280 | DIVERGENCE |
| 7/07 | 33 / 33 | -3 / -6 | 892 / — | ICE_POINT |
| 7/08 | 56 / 46 | -1 / -6 | 737 / 739 | CHAOS |
| 7/09 | 75 / 75 | 2 / 6 | 2665 / 2707 | CHAOS |

活跃资金几乎吻合，这是 ×2.04 硬拟合出来的结果，并不说明口径正确。涨停数在 7/1–7/3 差距最大，🔶 可能是那几天的数据源或“触及”口径不同。

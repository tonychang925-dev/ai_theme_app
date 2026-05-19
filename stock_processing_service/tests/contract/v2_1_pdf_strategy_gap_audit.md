# v2.1 PDF Strategy Gap Audit Report

> 状态：FINAL
> 日期：2026-05-19
> 版本：v2.1_audit_v1
> 前提：v2.0_backtest_baseline **FROZEN**，本报告仅做审计，不改代码，不跑收益

---

## 0. 审计范围与方法

### 审计的 PDF 策略文档（6份）

| # | 文档 | 页数 | 核心主题 |
|---|------|------|---------|
| 1 | 弱转强买入法.pdf | 5 | 盘后分歧识别 + 次日确认 + 买点 |
| 2 | 集合竞价.pdf | 6 | 9:20–9:25 竞价形态/抢筹/稳定性 |
| 3 | 如何建立正确的交易体系.pdf | 8 | 主线→情绪→龙头→买点四维框架 |
| 4 | 如何找出牛股.pdf | 3 | 牛股三绝：高量不破/倍量不穿/缺口不补 |
| 5 | 如何抓涨停股.pdf | 3 | 二板定龙头/首板换手/板块效应 |
| 6 | A股题材&强势股跟踪.pdf | 10 | 题材周期/主线识别/强势股滚动跟踪 |

### 审计的代码模块

| 模块 | 文件 | 行数 | 角色 |
|------|------|------|------|
| StrongStockTrackingService | `domain/services/strong_stock_tracking_service.py` | 864 | 5维评分 + 硬门禁 + C层候选资格 |
| BuildWeakToStrongCandidateUseCase | `application/use_cases/build_weak_to_strong_candidate.py` | 237 | D层弱转强候选生成 |
| KlineSupportScorer | `domain/services/kline_support_scorer.py` | 510 | 多支撑类型检测+复合评分 |
| SupportStructureResolver | `domain/services/support_structure_resolver.py` | 163 | 支撑优先级裁决（gap > bb > prev_low > ma） |
| GapStructureDetector | `domain/services/gap_structure_detector.py` | — | 缺口结构检测 |
| HistoricalBacktestReadPorts | `application/services/backtest/historical_backtest_ports.py` | — | A/B/C/D层数据供给 |
| v2.0 capital backtest | `tests/contract/run_v2_0_capital_backtest.py` | — | FROZEN 资金回测 |

---

## 1. 总体落实度评分

```
模块                        PDF要求                        落实度    评价
──────────────────────────────────────────────────────────────────────────
盘后候选池                   高召回，强势股分歧修复             85%     ✅ 已基本落实
强势股/龙头前提              杂毛不配弱转强                    80%     ✅ 已落实，leader/rank可增强
弱势类型识别                 大阴线/烂板/上影线/假突破          75%     ⚠️ 类型有了，烂板缺盘口细节
支撑体系                     前低/均线/缺口/前板/前高          75%     ⚠️ prev_low很强，前板/高量柱支撑不足
主线/板块联动                板块不退潮，有助攻                 55%     ⚠️ 日线有，竞价/盘中联动缺失
量价结构                     缩量分歧/放量突破/高量不破         45%     ❌ 接口有，底层识别弱
集合竞价确认                 9:20–9:25 高精度确认               15%     ❌ 基本未实现
分时承接买点                 均价线/放量突破/回踩               10%     ❌ 未实现
仓位体系                     龙头重仓/跟风轻仓                  40%     ⚠️ 固定仓位MVP
止盈止损                     反包失败/跌破支撑/二波持有         20%     ❌ 固定持有期
可解释/追溯                  每条信号证据清楚                    75%     ✅ source_trace已有

──────────────────────────────────────────────────────────────────────────
总体落实度:  ~55-60%
```

**关键判断**：这 55-60% 已经产生了有意义的资金曲线（v2.0 回测通过）。剩余 40-45% 集中在 **竞价/分时/盘口/动态卖出** — 恰恰是最可能继续提升 WR/AR/PF 的部分。

---

## 2. PDF 交易原则 → 代码映射 → 落实状态

### 2.1 两阶段系统：盘后候选 + 盘前竞价确认

**PDF要求**（弱转强买入法 + 集合竞价）：
- T日盘后：生成高召回候选池
- T+1盘前：只消费候选池，通过9:20–9:25集合竞价做高精度确认
- 盘前层不得全市场海选

**代码映射**：`BuildWeakToStrongCandidateUseCase.build_candidates()` + `expected_auction_pattern` 字段

**当前状态**：⚠️ 盘后候选已落实（85%），盘前竞价基本未落实（15%）

**关键缺口**：
```python
# build_weak_to_strong_candidate.py:205-209 — 竞价字段全是占位符
"expected_open_low": "0",
"expected_open_high": "0",
"expected_auction_pattern": "",
"need_last_minute_grab": False,
"need_plate_follow": False,
```

系统能回答"明天哪些票值得关注"，但不能回答"明天9:20–9:25哪些票真正完成弱转强确认"。

**对WR/AR/PF影响**：这是提升WR的最大单一空间。预计可过滤15-30%假弱转强信号。

---

### 2.2 盘后候选池硬门槛：强势背景 + 分歧修复窗口

**PDF要求**：盘后候选池只保留真正决定资格的条件 — 前期强势背景成立，当前处于分歧修复窗口，不是退潮末端。

**代码映射**：
- `StrongStockTrackingService.score_watch_row()` — 5维评分 + 硬门禁4选3
- `StrongStockTrackingService.is_candidate_eligible()` — watch_status + pool_entry_type
- `BuildWeakToStrongCandidateUseCase.build_candidates()` — pct_gate + strong_history + prior7 + support

**当前状态**：✅ 落实较好（80-85%）

**已落实的硬门槛**：
| 门槛 | 代码位置 | 逻辑 |
|------|---------|------|
| 当日必须弱 | `build_candidates:74-79` | `pct_chg < -1.0` |
| 必须有强势历史 | `build_candidates:80-82` | `is_leader \|\| prev_day_limit_up \|\| recent_limit_up_count>=1 \|\| rank_order<=5` |
| prior7 涨停基因 | `build_candidates:84-85` | `prior7_limitup_days >= 1` |
| prior7 强势日 | `build_candidates:87-88` | `prior7_strong_days >= 1` |
| 支撑有效 | `build_candidates:90-92` | `support_type not empty + support_strength >= 45` |

**缺口**：
- 退潮末端过滤有但偏粗：`fade_watch` 扣分是线性惩罚（-4/-8/-12），而非硬过滤
- "分歧修复窗口"判断只有日线涨幅，缺少盘中回踩深度/修复力度的分钟级证据

---

### 2.3 弱势类型：大阴线、上影线、烂板、假突破、高开低走

**PDF要求**（弱转强买入法）：
- 大阴线：长阴线放量分歧
- 冲高回落上影线：早盘冲高尾盘回落
- 烂板涨停：充分换手+突破压力位+炸板不跌+均线之上震荡+回撤≤3%+封单变小+缩量下跌=烂而不弱
- 假突破：突破后快速回落
- 高开低走：开盘强势收盘弱势

**代码映射**：`build_candidates:95-109`

```python
if prev_day_limit_up and pct_chg < 0:
    weak_type = "bad_limit_up"           # 烂板
elif pct_chg <= -5.0:
    weak_type = "big_negative_line"      # 大阴线
elif -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
    weak_type = "upper_shadow"           # 上影线
elif pct_chg <= -1.0:
    weak_type = "high_open_low_close"    # 高开低走
else:
    weak_type = "fake_break"             # 假突破
```

**当前状态**：⚠️ 类型分类已落实（75%），但烂板识别是日线近似

**关键缺口 — 烂板盘口五要素全部缺失**：
| 盘口要素 | PDF要求 | 当前实现 | 影响 |
|---------|--------|---------|------|
| 充分换手 | 换手率>15% | ❌ 未检查 | 无法区分洗盘vs出货 |
| 突破压力位 | 突破关键前高 | ❌ 未检查 | 可能是假突破烂板 |
| 炸板不跌 | 开板后不深跌 | ❌ 需分钟数据 | 无法判断烂而不弱 |
| 均线之上震荡 | 全天在均线上方 | ❌ 需分钟数据 | 无法判断强势洗盘 |
| 封单变小 | 尾盘封单萎缩 | ❌ 需L2数据 | 无法判断主力意图 |

**对WR/AR影响**：当前 `bad_limit_up` 类别内包含真洗盘和真出货，过滤后WR可能提升5-10%。

---

### 2.4 支撑体系：前低、缺口、均线、前板/前高

**PDF要求**（弱转强买入法 + 牛股三绝）：
- 价格保持在关键支撑位：5日/10日均线、前一日涨停价附近
- 缺口不补：缺口下沿不破
- 高量不破：高量柱最低价不破
- 前低不破：前一日最低价不破
- 前高突破回踩：突破压力位后回踩不破

**代码映射**：
- `KlineSupportScorer.score()` — 多支撑类型检测
- `SupportStructureResolver.resolve()` — 优先级裁决
- `GapStructureDetector.detect()` — 缺口检测

**当前支撑类型覆盖**：

| 支撑类型 | 已实现 | 评分权重 | v2.0验证 |
|---------|-------|---------|---------|
| gap_support | ✅ GapStructureDetector | base=0.80-0.95 | 已参与 |
| previous_low | ✅ _build_prev_low_structure | base=0.80 | **最强** WR3d=63.4% |
| bb_lower_support | ✅ _build_bb_lower_structure | base=0.86 | 已参与 |
| sma5_support | ✅ _build_ma_structures | base=0.65 | 已参与 |
| sma10_support | ✅ _build_ma_structures | base=0.74 | 已参与 |
| ema20_support | ✅ _build_ma_structures | base=0.82 | 已参与 |
| previous_close | ✅ 前日收盘价 | base=0.72 | 已参与 |
| prior_breakout_retest | ✅ _detect_prior_breakout_level | base=0.92 | 已参与 |
| pivot_support1/2 | ✅ _compute_pivot_points | base=0.75 | 已参与 |
| fibonacci_support | ✅ _compute_fibonacci_support | base=0.68 | 已参与 |
| **prev_limit_up_price** | ❌ 未实现 | — | **缺失** |
| **previous_high** | ❌ 未实现 | — | **缺失** |
| **high_volume_bar_support** | ❌ 未实现 | — | **缺失** |
| **box_breakout_support** | ❌ 未实现 | — | **缺失** |

**当前状态**：⚠️ 落实较好（75%），已有10种支撑类型，previous_low数据验证最强

**关键缺口**：
1. **前一日涨停价支撑**（PDF反复强调）：prev_day_limit_up 时，前一日收盘价/涨停价是重要支撑位，当前未单独建模
2. **前高压力位**（PDF强调）：突破后回踩确认，当前 `prior_breakout_retest` 用前15日最高价近似，缺少结构化前高识别
3. **高量柱支撑**（牛股三绝核心）：高量柱最低价是多空分界线，当前 PatternSnapshot 只有标签枚举，没有具体量价计算

**对WR/AR影响**：补上前板价和高量柱支撑预计提升AR 2-5%，因为这两类支撑位的"支撑力度"理论上更强。

---

### 2.5 主线与板块联动

**PDF要求**（如何建立正确的交易体系 + A股题材）：
- 抓市场主线（权重35%）：主线不能退潮
- 看市场情绪/周期（权重30%）：周期阶段判断
- 盯龙头核心（权重20%）：龙头/卡位/助攻
- 所属题材板块情绪不能全面退潮
- 板块内其他个股有异动，尤其补涨股助攻
- 竞价时板块同步强势

**代码映射**：
- `CycleSnapshot` — final_cycle_state, effective_mainline_alive, fade_watch, fade_confirmed
- `BoardSnapshot` — subject_limit_up_count, subject_strong_count
- `score_watch_row()` — theme_score (0-20分)
- 硬门禁 Rule B: `final_mainline_alive AND board_effect_confirmed`

**当前状态**：⚠️ 部分落实（55%）

**已落实**：
- A层 5日滚动窗口 lookback（coverage 10→31 subjects）
- mainline_strength_score + event_continuity_score
- fade_watch / fade_confirmed 退潮过滤
- board_effect_confirmed（subject_limit_up_count >= 2 或 subject_strong_count >= 3）
- 7种周期状态：start/fermentation/acceleration/divergence/repair/fade_watch/fade_confirmed

**关键缺口 — 都是竞价/盘中层面**：
| 缺口 | PDF要求 | 影响 |
|------|--------|------|
| 竞价板块联动 | 龙头是否符合预期？龙二龙三有溢价？ | WR |
| 板块红盘率 | 题材内红盘占比 | WR |
| 板块强势率 | 题材内涨幅>3%占比 | WR |
| 补涨助攻 | 低位补涨票是否异动 | AR |
| 退潮实时检测 | 竞价阶段板块是否明显退潮 | MaxDD |

当前能判断"这个题材最近是不是强"，但不能判断"明天竞价时，板块是不是同步强"。

---

### 2.6 集合竞价确认

**PDF要求**（集合竞价.pdf）：
- 9:20–9:25 走势稳定，不能大起大落或急跌
- 最佳图形：倒L型+上坡、红盘区阶梯型、红盘区锥形+U形、上翘一字型
- 9:24–9:25 最后一分钟竞价单明显放大
- 高开3%–5%区间
- 竞价量能达到昨日最大分时量的1/2
- 尾段急跌硬规则：9:24后出现连续压单/价格急跌→直接剔除

**代码映射**：
- `w2s_auction_scorer.py` — `W2SAuctionScorer.score_one()`（存在但未接入v2.0回测）
- `w2s_confirm_service.py` — `W2SConfirmService.confirm()`（存在但未接入v2.0回测）
- 架构文档 §6 — 竞价评分设计（四维评分，仅设计）

**当前状态**：❌ 基本未落实（15%）

**架构文档 §6 已有设计但未实现的四维评分**：
```
price_strength     权重30%  — 开盘强度
pattern_stability  权重25%  — 竞价形态稳定性
last_minute_grab   权重25%  — 末分钟抢筹
plate_follow       权重20%  — 板块联动
risk_penalty      扣分项    — 尾段急跌/大起大落
data_status       数据状态  — proxy/real_auction/missing
```

**v2.0回测现在用的是**：T+1 开盘价买入（无竞价过滤）

**对WR影响**：这是仅次于盘后候选质量的第二大WR提升空间。预计过滤15-30%假弱转强。

---

### 2.7 分时承接与盘中买点

**PDF要求**（弱转强买入法）：
- 分歧次日，盘中回踩承接确认后打板或半路跟进
- 分时弱转强：低开→震荡→突然直线拉升封板
- 趋势转强买入：回踩支撑后放量突破
- 分时均线支撑点放量上攻时是买点

**代码映射**：无（v2.0 使用 T+1 开盘价作为唯一买点）

**当前状态**：❌ 未落实（10%）

**关键缺口**：
1. 缺少分钟级K线数据
2. 无法判断开盘后是否单边下跌
3. 无法判断分时均线是否被破
4. 无法判断放量突破分时平台
5. 无法判断回踩均价线承接

**对AR/MaxDD影响**：开盘买入可能买到当日最高点。盘中确认买点可提升AR 3-8%，降低MaxDD 5-10%。

---

### 2.8 量价结构：缩量分歧、放量突破、高量不破

**PDF要求**（如何找出牛股 + 弱转强买入法）：
- 成交量不能明显萎缩，否则是假反抽
- 真弱转强要放量换手、封单坚决
- 烂板时下跌过程中缩量，说明抛压减少
- 高量不破：low > 高量柱最低价
- 倍量不穿：二底 >= 一底
- 缩量回踩：回踩支撑位时缩量
- 放量突破：突破关键位时放量

**代码映射**：
- `PatternSnapshot` — volume_pattern_status, pullback_status, breakout_status, pattern_labels
- 硬门禁 Rule C: `current_flag_today >= 2 \|\| volume_pattern_status in {"放量上涨","缩量整理"} \|\| pullback_status == "缩量回踩"`
- 5维评分 volume_price_score: 使用 volume_pattern_status + pullback_status + broken_board

**当前状态**：❌ 部分落实但底层识别弱（45%）

**关键缺口**：
| PDF规则 | PatternSnapshot 标签 | 底层实际计算 | 状态 |
|---------|---------------------|-------------|------|
| 高量不破 | "高量不破" in pattern_labels | historical_backtest_ports 注释："没有实现完整高量不破检测" | ❌ 标签存在，计算缺失 |
| 倍量不穿 | 无对应标签 | 无 | ❌ 完全缺失 |
| 缩量回踩 | pullback_status="缩量回踩" | 最小实现 | ⚠️ 弱实现 |
| 放量突破 | breakout_status="放量突破" | 最小实现 | ⚠️ 弱实现 |
| 烂板缩量下跌 | 无 | 无 | ❌ 缺失 |

**对AR/PF影响**：量价结构是区分"真反抽"和"真弱转强"的核心维度。完整实现预计提升AR 5-10%。

---

### 2.9 仓位控制

**PDF要求**（弱转强买入法 + 如何建立正确的交易体系）：
- 首次轻仓1-2成
- 主线题材+绝对龙头可加大到5-8成
- 龙二/次龙头2-4成
- 不能满仓梭哈
- 买点信号越强，仓位越大

**代码映射**：v2.0 VirtualBroker — 固定仓位

```python
POSITION_PCT = 0.10      # 固定10%
MAX_BUYS_PER_DAY = 3      # 固定3只
MAX_POSITIONS = 10        # 固定10只
```

**当前状态**：⚠️ MVP已落实（40%），但不够精细

**关键缺口**：仓位应该是多维度的函数：
```
position_pct = f(
    strong_grade,          # S→15%, A→10%, B→0-5%
    leader_role,           # dragon→15%, sub_dragon→10%, card→7%
    support_type,          # previous_low→+2%, gap/ma→±0%
    support_strength,      # >=80→+3%
    mainline_strength,     # >=75→+2%
    auction_confirm_level, # A→+3%, B→+0%, C→-5%
    fade_watch,            # true→-5%
)
```

**对PF/MaxDD影响**：动态仓位可在不降低WR的前提下提升PF 10-20%，降低MaxDD 5-15%。

---

### 2.10 止盈止损与卖出体系

**PDF要求**（弱转强买入法 + 如何建立正确的交易体系）：
- 反包失败、当天不能重新站上关键价位→减仓或止损
- 成功反包后可持股等待二波或加速
- 日线跌破10日线/前低→清仓
- 收盘跌破关键支撑→纪律性卖出
- 连续加速后→止盈

**代码映射**：v2.0 固定持有期
```python
# v2.0 只有两种卖出规则
hold_3d:  T+3 收盘卖出
hold_5d:  T+5 收盘卖出
```

**当前状态**：❌ 未真正落实（20%）

**关键缺口**：
| 卖出规则 | PDF要求 | 当前实现 | 影响 |
|---------|--------|---------|------|
| 跌破支撑止损 | 跌破previous_low/MA10→清仓 | ❌ 无 | MaxDD |
| 反包失败止损 | 不能站上关键价位→减仓 | ❌ 无 | MaxDD |
| 冲高回落止盈 | 冲高后回落→止盈 | ❌ 无 | PF |
| 涨停后弱开止盈 | 涨停次日低开→止盈 | ❌ 无 | PF |
| 主线退潮降仓 | 主线fade→强制降仓 | ❌ 无 | MaxDD |
| 连续加速止盈 | 连板后加速→止盈 | ❌ 无 | PF |

**对PF/MaxDD影响**：动态卖出是降低MaxDD最有效的手段（预计降低20-35%），同时也提升PF（预计10-20%）。

---

## 3. 落实清单

### 3.1 已落实 ✅（7项）

| # | 能力 | 落实模块 | 数据验证 |
|---|------|---------|---------|
| 1 | 杂毛不配弱转强：强势股5维评分 + 硬门禁4选3 | StrongStockTrackingService.score_watch_row() | v1.0 contract PASS |
| 2 | prior7 涨停基因 + 强势日计算 | HistoricalBacktestReadPorts (bar数据滚动7日) | 合规验证 |
| 3 | 弱势类型分类（5种） | BuildWeakToStrongCandidateUseCase (weak_type) | v1.1b信号验证 |
| 4 | 支撑体系（10种支撑类型） + 复合评分 | KlineSupportScorer + SupportStructureResolver | previous_low WR3d=63.4% |
| 5 | 强势池滚动跟踪：seed + refresh/roll-forward | HistoricalBacktestReadPorts | v1.1a数据就绪 |
| 6 | A-layer 5日 lookback（覆盖31 subjects） | HistoricalBacktestReadPorts | diagnose_v1_1a PASS |
| 7 | UseCase全链路合规 | test_v1_0_usecase_replay_contract.py | v1.0 contract PASS |

### 3.2 部分落实 ⚠️（5项）

| # | 能力 | 已做 | 未做 | 落实度 |
|---|------|------|------|--------|
| 1 | 主线/板块联动 | 日线周期状态+板块统计 | 竞价/盘中实时联动 | 55% |
| 2 | 量价结构（高量不破等） | 标签枚举+评分接口 | 底层精确计算 | 45% |
| 3 | 仓位控制 | 固定10%仓位MVP | 多维度动态仓位 | 40% |
| 4 | 支撑体系 | 10种支撑类型 | 前板价/前高/高量柱支撑 | 75% |
| 5 | 烂板质量 | 日线近似（prev_day_limit_up+当日转弱） | 盘口五要素 | 50% |

### 3.3 未落实 ❌（4项）

| # | 能力 | PDF来源 | 预计影响 |
|---|------|--------|---------|
| 1 | 盘前竞价确认层 | 集合竞价.pdf + 弱转强买入法.pdf | WR +15-30% |
| 2 | 分时承接与盘中买点 | 弱转强买入法.pdf | AR +3-8%, MaxDD -5-10% |
| 3 | 牛股三绝精确计算 | 如何找出牛股.pdf | AR +5-10% |
| 4 | 动态止盈止损 | 弱转强买入法.pdf + 如何建立正确的交易体系.pdf | MaxDD -20-35%, PF +10-20% |

---

## 4. 优先级路线图（P0–P4）

### P0：盘前竞价确认层（v2.2）

**理由**：PDF体系是"两阶段"系统，盘后候选只是第一步。竞价确认是提升WR最大单一杠杆。

**设计草案**：

```
AuctionConfirmationLayer
├── 硬规则过滤器（一票否决）
│   ├── must_from_candidate_pool: 必须来自D层候选池
│   ├── price_range: 高开区间 [-2%, +8%]，最佳 [0%, +5%]
│   ├── stability: 9:20–9:25 价格标准差 < 阈值
│   ├── no_tail_crash: 9:24后不允许连续压单/价格急跌
│   └── data_status: missing→X级降级，proxy→最多B级
│
├── 四维评分器
│   ├── price_strength (30%): auction_open_pct, vwap vs pre_close
│   ├── pattern_stability (25%): 竞价形态识别（倒L/阶梯/锥形/U形/上翘）
│   ├── last_minute_grab (25%): 9:24–9:25 量价变化
│   └── plate_follow (20%): 板块红盘率/强势率/龙头联动
│
├── 风险惩罚
│   ├── tail_crash_penalty: -20
│   ├── volatility_penalty: 大起大落 -15
│   └── low_liquidity_penalty: 竞价量能不足 -10
│
└── 输出
    ├── confirm_level: A/B/C/X
    ├── auction_score: 0–100
    └── trade_signal: allowed/blocked
```

**预期提升**：WR +10-20pp（从当前~55%提升到65-75%）

---

### P1：量价结构增强（v2.3）

**理由**：当前PatternSnapshot只有标签，底层计算空缺。量价结构是区分"真反抽"和"真弱转强"的核心维度。

**设计草案**：

```
PatternEnhancement v2.3
├── 高量不破检测
│   ├── 识别近20日最高成交量柱
│   ├── 判定当前low是否>高量柱low
│   └── 距离+成交量衰减评分
│
├── 倍量不穿检测
│   ├── 识别近20日次高成交量柱
│   ├── 判定二底>=一底
│   └── 量价双重确认
│
├── 缩量回踩增强
│   ├── 回踩支撑位时量比 < 0.6
│   ├── 回踩深度 < 3%
│   └── 回踩后反弹量 > 回踩前量
│
├── 放量突破增强
│   ├── 突破关键位时量比 > 1.5
│   ├── 突破幅度 > 1%
│   └── 突破后不回落 > 0.5%
│
└── 烂板缩量下跌检测
    ├── 炸板时量比 > 2.0（充分换手）
    ├── 炸板后跌幅 < 3%
    └── 炸板后量比逐步萎缩
```

**预期提升**：AR +5-10%，过滤假反抽

---

### P2：支撑类型扩展（v2.3 附带）

**理由**：previous_low已验证最强，但PDF强调的前板价/前高支撑尚未单独建模。

**新增支撑类型**：

| 新类型 | 计算方法 | 初始权重 |
|--------|---------|---------|
| prev_limit_up_price | 前一日涨停价（若prev_day_limit_up） | 0.88 |
| previous_high | 前一日最高价 | 0.78 |
| high_volume_bar_support | 近20日最高量柱最低价 | 0.85 |
| box_breakout_support | 箱体上沿突破回踩 | 0.82 |

**预期提升**：WR +2-5pp，AR +2-4%

---

### P3：板块联动 + 市场情绪过滤（v2.4）

**理由**：减少退潮期假信号，降低MaxDD。

**设计草案**：

```
MarketEmotionFilter v2.4
├── 市场宽度指标
│   ├── 涨停家数/跌停家数
│   ├── 昨日涨停指数今日表现
│   └── 全市场上涨/下跌比
│
├── 板块联动评分
│   ├── 题材红盘率（竞价阶段）
│   ├── 题材强势率（竞价阶段）
│   ├── 前排核心票竞价表现
│   └── 补涨票异动检测
│
├── 龙头联动
│   ├── 龙头竞价是否符合预期
│   ├── 龙二龙三是否有溢价
│   └── 卡位龙是否有负反馈
│
└── 退潮硬过滤
    ├── 跌停>50 → 不开仓
    ├── 昨日涨停指数<-3% → 不开仓
    └── 主线fade_confirmed → 不开仓
```

**预期提升**：MaxDD -10-20%，退潮期胜率显著改善

---

### P4：动态卖出规则（v2.5）

**理由**：当前固定持有期是最粗的卖出方式，动态卖出是降低MaxDD最有效的手段。

**设计草案**：

```
DynamicExitRules v2.5
├── 止损规则
│   ├── 跌破 previous_low → 止损
│   ├── 跌破 MA10 → 止损
│   ├── 单日跌幅 < -7% → 止损
│   └── 反包失败（T+2仍低于T日收盘）→ 止损
│
├── 止盈规则
│   ├── 冲高回落（日内+5%后回落到+2%）→ 止盈
│   ├── 涨停次日弱开（涨停后次日低开<-2%）→ 止盈
│   ├── 连续加速（3连板后）→ 止盈
│   └── 目标收益 +15% → 止盈
│
├── 状态规则
│   ├── 主线退潮 → 强制降仓50%
│   ├── fade_confirmed → 清仓
│   └── 跌破支撑但主线仍强 → 减仓50%
│
└── 持有规则
    ├── 反包成功（站上T日收盘）→ 继续持有
    ├── 主线加速中 → 继续持有
    └── 缩量回踩不破支撑 → 继续持有
```

**预期提升**：MaxDD -20-35%，PF +10-20%

---

## 5. 版本路线确认

```
v2.0  ✅ FROZEN — capital backtest baseline
       ↓
v2.1  ✅ 当前 — PDF strategy gap audit（本报告）
       ↓
v2.2  🔜 auction confirmation layer（P0）
       ↓
v2.3  🔜 pattern/volume structure enhancement + support type expansion（P1+P2）
       ↓
v2.4  🔜 market emotion + plate follow filter（P3）
       ↓
v2.5  🔜 dynamic exit rules（P4）
```

---

## 6. 硬约束确认

本审计严格遵守以下约束：

- [x] 未修改 UseCase 阈值
- [x] 未手写新候选逻辑
- [x] 未读取 v0.x deprecated 实验结果作为依据
- [x] v2.0 作为冻结 baseline，未提议修改
- [x] 所有建议通过 UseCase 扩展/新增模块实现
- [x] 建议的竞价/分时层遵循 `confirm_source` 数据模式分离

---

## 7. v2.2 启动建议

**下一步**：设计并实现 `AuctionConfirmationUseCase`。

**输入**：
- D层候选池（w2s_candidate_rebuild）
- 竞价快照数据（已有 `BuildAuctionSnapshotJob` 产出）
- 板块日线统计

**输出**：
- `confirm_level`: A/B/C/X
- `auction_score`: 0–100
- `trade_signal`: allowed/blocked
- `confirmation_evidence`: JSON

**不做的**：
- 全市场竞价扫描（只消费候选池）
- 盘中实时确认（先做盘前静态）
- 分钟级分时承接（v2.5+）

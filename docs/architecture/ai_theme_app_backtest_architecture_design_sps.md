# AI题材选股系统回测架构设计文档（新链 stock_processing_service 版）

> 版本：v5.0（新增 §0.7 v1.0_usecase_replay_contract；停止收益验证）
> 适用架构：`web_app_service + stock_processing_service + database_service.gateway` 新链
> 废弃约束：`stock_service` 目录下的旧链选股/回测扩展不再作为新功能落点；仅允许作为历史兼容参考或临时适配依赖。

---

## 0. 执行合同：回测开发强制约束（EXECUTION CONTRACT）

> **本节约束优先级最高。任何回测开发任务必须首先满足本节要求，否则视为不合规。**

### 0.1 核心原则

**禁止在回测脚本、backfill service、run script 中手写策略规则。所有策略判断必须复用新链已有 domain service / UseCase。**

### 0.2 强制复用清单（MUST USE）

以下新链代码是回测链路中对应功能的**唯一合法来源**。禁止在回测代码中重新实现等价逻辑。

#### A 层（题材主线/周期）

| 能力 | 唯一合法来源 | 禁止行为 |
|------|------------|---------|
| 题材主线身份判定 | `get_mainline_identity_by_subject_keys()` → `MainlineIdentityDTO` | 禁止用 `mainline_strength_score >= 60` 手写替代 |
| 题材周期状态 | `get_mainline_cycle_by_subject_keys()` → `MainlineCycleDTO` | 禁止从 `subject_daily_feature.cycle_state` 字符串直接判断 |
| 题材周期证据 | `get_subject_cycle_evidence_daily()` | 禁止手写 event_continuity 计算 |
| A 层数据源 | `subject_rank_daily`（久赢恒丰题材榜） | 禁止从 `candidate_pool` 字段拼凑 A 层数据 |

#### B 层（强势股基因/龙头/入池）

| 能力 | 唯一合法来源 | 禁止行为 |
|------|------------|---------|
| 种子行构建 | `StrongStockTrackingService.build_seed_candidates()` | 禁止手写 ST/688 排除、source_tag、relay_role |
| 种子行数据 | `get_strong_watch_seed_rows()` → `HistoricalBacktestReadPorts` | 禁止从 `strong_stock_daily_feature` 直接扫描替代 |
| 刷新行数据 | `get_strong_watch_refresh_rows()` → `HistoricalBacktestReadPorts` | 禁止省略 |
| prior7 计算 | `stock_daily_snapshot` 逐日滚动窗口（7个交易日） | **禁止**用静态字段复制替代日期滚动计算 |
| leader_role_proxy | `classify_leader_role_proxy()` in `w2s_feature_rules.py` | 禁止手写 leader/card/assist 分类 |

#### C 层（强势股观察池）

| 能力 | 唯一合法来源 | 禁止行为 |
|------|------------|---------|
| 强势股评分 | **`StrongStockTrackingService.score_watch_row()`** | **禁止手写五维评分。禁止用 `prior7_limitup_days >= 1` 替代。** |
| 候选资格判定 | **`StrongStockTrackingService.is_candidate_eligible()`** | 禁止只取 formal 丢弃 observe_only |
| C 层编排 | **`BuildStrongStockTrackingUseCase.execute()`** | 禁止手写 seed→score→write 流程 |
| 板块统计 | `get_subject_board_stats()` | 禁止省略 BoardSnapshot |
| 位置判断 | `get_stock_position_judgement()` | 禁止省略 PositionSnapshot |
| 形态判断 | `get_stock_pattern_judgement()` | 禁止省略 PatternSnapshot |
| 支撑评分 | `KlineSupportScorer` / `SupportStructureResolver` | 禁止手写 `_detect_support()` |

#### D 层（弱转强候选）

| 能力 | 唯一合法来源 | 禁止行为 |
|------|------------|---------|
| 候选生成 | **`BuildWeakToStrongCandidateUseCase.build_candidates()`** | **禁止手写 D 层候选逻辑。禁止 `prior7 >= 1` 直接写候选。** |
| 候选输入 | `get_w2s_candidate_inputs()` → 来自 C 层 eligible 结果 | 禁止从全市场扫描替代 |
| D 层诊断 | `BuildWeakToStrongCandidateUseCase._diagnostics` | 必须输出 d1_fail_pct/history/gene/strong/support |

#### 弱类型/支撑特征

| 能力 | 唯一合法来源 | 禁止行为 |
|------|------------|---------|
| 弱类型分类 | **`classify_weak_type()` in `w2s_feature_rules.py`** | 禁止在 backfill service 中手写 if/elif 分类 |
| 弱类型品质 | **`classify_weak_type_quality()` in `w2s_feature_rules.py`** | 禁止重复定义 `WEAK_TYPE_QUALITY_MAP` |
| 支撑检测 | **`BarSupportAdapter` → `GapStructureDetector` + `SupportStructureResolver`** | 禁止手写 `_detect_support()` |
| 缺口检测 | `GapStructureDetector.detect()` | 禁止手写 gap 判断 |
| K 线支撑 | `KlineSupportScorer` | 禁止手写 MA 支撑判断 |

### 0.3 违规模式清单（FORBIDDEN PATTERNS）

以下模式**已实际发生**，被明确禁止：

| # | 违规模式 | 示例 | 正确做法 |
|---|---------|------|---------|
| 1 | 在 backfill service 中硬编码 if/elif 分类 | `if pct_chg <= -5.0: return "big_negative_line"` | 调用 `classify_weak_type()` |
| 2 | 用 `prior7_limitup_days >= 1` 直接写 D 层候选 | v0.7 全量 | 调用 `BuildWeakToStrongCandidateUseCase` |
| 3 | 手写 `_detect_support()` | `if prev_high > 0 and low > prev_high * 0.98: return "gap_support"` | 调用 `BarSupportAdapter` |
| 4 | 手写 `WEAK_TYPE_QUALITY_MAP` 副本 | backfill service 中重复定义 | import `classify_weak_type_quality()` |
| 5 | 手写 `_simple_ma5()` | backfill service 中自算均线 | 使用 `KlineSupportScorer` |
| 6 | B 层 prior7 跨日期静态复制 | prior7_limitup_days 不随日期变化 | 每个 stock-date 从实际 bar 滚动计算 |
| 7 | 手写 `compute_candidate_score()` | run script 中的局部函数 | 调用 `BuildWeakToStrongCandidateUseCase` |
| 8 | 手写 `classify_leader_role_proxy()` | run script 中的局部函数 | import 已有实现 |
| 9 | 绕过 UseCase 直接写候选池 | run script 中直接 INSERT | 通过 UseCase + WritePorts |
| 10 | backfill service 承载交易规则 | `_classify_weak_type()` 在 backfill 中 | backfill service = thin orchestrator |

### 0.4 合规验证

每条 run 必须输出以下审计信息：

```json
{
  "compliance": {
    "strong_tracking_usecase_called": true,
    "score_watch_row_called": true,
    "is_candidate_eligible_called": true,
    "w2s_usecase_called": true,
    "classify_weak_type_imported": true,
    "classify_weak_type_quality_imported": true,
    "bar_support_adapter_used": true,
    "no_handwritten_candidate_logic": true,
    "no_handwritten_support_logic": true,
    "no_handwritten_leader_logic": true,
    "b_layer_prior7_from_bar_data": true,
    "future_leak_count": 0
  }
}
```

### 0.5 版本标记

不合规的中间实验版本必须明确标记：

- `v0.5_fixed_baseline` — research baseline（简化回填，保留为对照基准）
- `v0.6` — **deprecated_experiment**（全市场扫描，稀释强势股前提。已停止收益验证。）
- `v0.7` — **deprecated_experiment**（prior7→D 手写逻辑，绕过 UseCase。已停止收益验证。）
- `v0.8` — **deprecated_experiment**（UseCase replay 实验版，partial v0.8a。已停止收益验证。迁移至 v1.0）
- `v0.9` — **deprecated_experiment**（预留槽位，未实际产出。已停止收益验证。）

### 0.6 停止收益验证（STOP RETURNS VALIDATION）

自 v5.0 起，**所有 v0.x 版本的收益验证均已停止**。以下行为被禁止：

- ❌ `run_w2s_v0.2_calibration.py` → 已废弃，不执行
- ❌ `run_w2s_v0.3.py` → 已废弃，不执行
- ❌ `run_w2s_v0.4.py` → 已废弃，不执行
- ❌ `run_w2s_phase0_first_validation.py` → 已废弃，不执行
- ❌ `build_w2s_abc_strict_rebuild.py` → 已废弃，不执行
- ❌ `run_w2s_v0.8_usecase_replay.py` → 已废弃，不执行
- ❌ 任何通过 `W2SSignalValidationService.validate()` 计算 `next_1d/3d/5d_return` 的 v0.x 路径

**唯一的 v1.0 入口**：`tests/contract/test_v1_0_usecase_replay_contract.py`（合约测试，不跑收益）

### 0.7 v1.0_usecase_replay_contract（新）

> **本节是 v5.0 新增的核心约束。v1.0 是唯一合法版本入口。**

#### 0.7.1 硬性要求

1. **禁止 run script 手写 C/D 层逻辑。**
2. **禁止直接 INSERT 候选池。** 所有写入必须通过 `HistoricalBacktestWritePorts`。
3. **禁止用 `prior7_limitup_days >= 1` 直接生成候选。** 必须通过 `BuildWeakToStrongCandidateUseCase.build_candidates()`。
4. **禁止复制 `recent_limit_up_count` 作为 `prior7_limitup_days`。** prior7 必须从 bar 数据逐日滚动计算。
5. **必须通过 `HistoricalBacktestReadPorts` 调用正式 UseCase。**
6. **必须调用以下方法：**
   - `BuildStrongStockTrackingUseCase.execute()`
   - `StrongStockTrackingService.build_seed_candidates()`
   - `StrongStockTrackingService.score_watch_row()`
   - `StrongStockTrackingService.is_candidate_eligible()`
   - `BuildWeakToStrongCandidateUseCase.build_candidates()`
7. **先做 contract test，不跑收益。** `test_v1.0_usecase_replay_contract.py` 只验证 UseCase 调用链路完整性和合规性。
8. **输出 UseCase 调用审计和违规扫描结果。**

#### 0.7.2 v1.0 合规输出格式

```json
{
  "contract_version": "v1.0_usecase_replay",
  "compliance": {
    "strong_tracking_usecase_called": true,
    "build_seed_candidates_called": true,
    "score_watch_row_called": true,
    "is_candidate_eligible_called": true,
    "w2s_usecase_called": true,
    "build_candidates_called": true,
    "no_handwritten_c_logic": true,
    "no_handwritten_d_logic": true,
    "no_direct_insert": true,
    "no_prior7_gate_direct": true,
    "no_recent_copy_as_prior7": true,
    "b_layer_prior7_from_bar_data": true,
    "all_writes_through_write_ports": true,
    "future_leak_count": 0
  },
  "usecase_trace": {
    "strong_tracking_dates": 0,
    "strong_tracking_affected_rows": 0,
    "seed_candidates_built": 0,
    "w2s_dates": 0,
    "w2s_candidates_built": 0,
    "d1_diagnostics": {}
  },
  "violation_scan": {
    "scanned_files": [],
    "violations_found": 0,
    "violation_details": []
  }
}
```

#### 0.7.3 版本路线

```text
v0.x (deprecated_experiment) → 停止收益验证
    ↓
v1.0_usecase_replay_contract → contract test only（当前）
    ↓
v1.1_usecase_replay_full → contract test pass + signal validation enabled
    ↓
v2.0_capital_backtest → full capital backtest with VirtualBroker
```

---

## 0.6 本次修订背景（v3.0 → v4.0）

v2.0 确定了回测系统落点在新链 `stock_processing_service`，v3.0 在此基础上补充：

1. **新增 w2s_backtest_run 表**：所有回测输出绑定运行批次，支持多参数、多版本对比和幂等重跑。
2. **新增 w2s_backtest_feature_snapshot 表**：冻结历史特征快照，保证回测可复现，原始特征与派生特征严格分离。
3. **策略文档映射**：基于「弱转强买入法」「如何建立正确的交易体系」「集合竞价」「如何找出牛股」「如何抓涨停股」五份策略文档，提取可量化规则并映射至回测框架。
4. **实验对照设计**：底层支持6组实验，前端第一版展示3组，先分组归因、再硬过滤。
5. **竞价数据模式严格分离**：`confirm_source` 区分真实竞价和 proxy，不混算。
6. **工程约束强化**：Phase 0 不生成买卖建议、confirm_source 作为一级分组、重跑幂等。

---

## 1. 新链代码核查结论

### 1.1 新链服务定位

`stock_processing_service` 是新的股票处理服务包，定位为 gateway-first stock processing architecture。

新链核心服务入口是：

```text
stock_processing_service/api_app.py
```

服务由：

```bash
python -m uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 8090
```

启动。

### 1.2 `web_app_service` 是新链对外服务入口

`web_app_service` 负责：

```text
1. 对前端暴露 /api/v2/*
2. 管理 stock_processing_service 生命周期
3. 将业务 API 代理到 stock_processing_service /api/v1/*
4. 提供 readyz/healthz 检查
```

未来前端不应直接依赖旧 `frontend_bff` 的选股接口，而应通过：

```text
frontend
  ↓
web_app_service /api/v2/*
  ↓
stock_processing_service /api/v1/*
```

### 1.3 新链弱转强核心代码落点

**弱转强候选生成（唯一落点）：**

```text
stock_processing_service/application/use_cases/build_weak_to_strong_candidate.py
  └─ BuildWeakToStrongCandidateUseCase.build_candidates()

stock_processing_service/domain/services/w2s_candidate_service.py
  └─ W2SCandidateService.explain_candidate()

stock_processing_service/domain/services/w2s_confirm_service.py
  └─ W2SConfirmService.confirm()

stock_processing_service/domain/services/w2s_auction_scorer.py
  └─ W2SAuctionScorer.score_one()
```

**禁止对新链回测系统引用旧链类名：`W2SCandidateService._classify_weak_type()` 等旧写法全部废弃。**

### 1.4 新链已有核心能力

当前 `stock_processing_service` 已经包含：

```text
BuildDailySnapshotJob
BuildCycleJudgementJob
BuildMainlineStateJob
BuildPostMarketRecapJob
BuildPreMarketBriefJob
BuildThemeCycleEvidenceDailyJob
BuildStrongStockTrackingUseCase
BuildWeakToStrongCandidateUseCase
BuildAuctionSnapshotJob
BuildAuctionSignalJob
BuildAuctionWatchUniverseJob
W2SConfirmService
NewChainIntelFeedAdapter
CollectionJobManager
```

---

## 2. 策略文档 → 回测规则映射

基于五份策略文档提取的可量化规则：

### 2.1 弱转强买入法

| 阶段 | 规则 | 量化方法 |
|------|------|---------|
| T日分歧识别 | 烂板/首阴/冲高回落 | `weak_type ∈ {bad_limit_up, big_negative_line, upper_shadow, high_open_low_close}` |
| T日支撑确认 | 关键均线/前低不破 | `support_type ∈ {gap_support, ma_support, platform_support, prev_low_support}` |
| T+1盘前确认 | 集合竞价高开/抢筹 | `auction_open_pct >= 0 AND auction_amount 充沛` |
| 龙头限定 | 只做龙头/次龙头 | `is_leader=true OR rank_order<=3 OR recent_limit_up_count>=2` |
| 止损 | 跌破关键支撑 | `-5% 硬止损` |
| 止盈 | 反包成功持股待涨 | `+10% 止盈` |

### 2.2 如何建立正确的交易体系

| 维度 | 权重 | 回测映射 |
|------|------|---------|
| 抓市场主线 | 35% | `mainline_strength_score >= 60 AND fade_confirmed = false` |
| 看市场情绪/周期 | 30% | `cycle_state ∈ {forming, confirmed, fade, divergence, repair}` |
| 盯龙头核心 | 20% | `leader_role_proxy ∈ {leader, card, assist, supplement, unknown}` |
| 找准买点 | 15% | 日线用 `next_open` 近似；分钟级暂不支持 |

### 2.3 集合竞价

| 规则 | 量化方法 | 数据要求 |
|------|---------|---------|
| 竞价分时稳定性 | `std(9:20-9:25 prices)` | 需要竞价分时序列 |
| 末分钟抢筹 | `vol_9:24-9:25 / avg_vol_9:20-9:24 >= 1.5` | 需要竞价分时序列 |
| 量能承接 | `auction_amount / prev_day_max_minute >= 0.5` | 需要昨日分钟量 |
| 高开幅度 | `auction_open_pct ∈ [0%, 5%]` | 已有 |

### 2.4 如何找出牛股（牛股三绝）

| 规则 | 量化方法 |
|------|---------|
| 高量不破 | `low_price > high_volume_bar_low` |
| 倍量不穿 | `2nd_bottom >= 1st_bottom` |
| 缺口不补 | `gap_not_filled == true` |
| 均线多头排列 | `MA5 > MA10 > MA20 > MA60` |

### 2.5 如何抓涨停股（二板定龙头）

| 规则 | 量化方法 |
|------|---------|
| 涨停基因 | `prior7_limitup_days >= 1` |
| 首板换手板优于一字板 | `turnover_rate_1st_board > 15%` |
| 二板强度 | 缩量封死 > 放量分歧转一致 |
| 板块效应 | `same_subject_limit_up_count >= 2` |

---

## 3. 新链推荐目录结构（v3.0）

```text
stock_processing_service/
  domain/
    backtest/
      w2s_models.py                # 数据模型 + 枚举 + DTO
      w2s_feature_rules.py         # 特征派生规则（leader_role_proxy等）
      w2s_experiment_rules.py      # 6组实验条件定义
      w2s_metrics.py               # 收益/胜率/回撤计算

  application/
    services/
      backtest/
        w2s_data_quality_service.py        # 数据质量检查
        w2s_feature_snapshot_service.py    # 特征快照生成
        w2s_signal_builder_service.py      # 信号生成
        w2s_signal_validation_service.py   # 未来收益计算
        w2s_validation_summary_service.py  # 实验组汇总

  infrastructure/
    gateway_adapters/
      w2s_backtest_gateway_adapter.py      # 回测表读写

  api_app.py
```

**第一阶段不做 StrategyPluginRegistry / BaseStrategy 等插件抽象，等 Phase 3 后再考虑。**

---

## 4. 数据库表设计（v3.0）

### 4.1 回测运行批次表

```sql
CREATE TABLE IF NOT EXISTS w2s_backtest_run (
    run_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL DEFAULT 'weak_to_strong',
    strategy_version TEXT NOT NULL,
    run_type VARCHAR(32) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    data_quality_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    error_message TEXT,

    signal_count INTEGER DEFAULT 0,
    validated_count INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### 4.2 特征快照表

```sql
CREATE TABLE IF NOT EXISTS w2s_backtest_feature_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES w2s_backtest_run(run_id),
    strategy_version TEXT NOT NULL,

    candidate_trade_date DATE NOT NULL,
    confirm_trade_date DATE,

    stock_id VARCHAR(32) NOT NULL,
    stock_name VARCHAR(64),

    subject_key VARCHAR(64),
    theme_name VARCHAR(128),

    -- 候选层特征
    candidate_id BIGINT,
    pool_entry_type VARCHAR(32),
    candidate_score NUMERIC(8,2),
    candidate_type VARCHAR(64),
    weak_type VARCHAR(64),

    support_type VARCHAR(64),
    support_strength NUMERIC(8,2),

    -- 龙头身份层特征
    is_leader BOOLEAN,
    rank_order INTEGER,
    recent_limit_up_count INTEGER,
    prior7_limitup_days INTEGER,
    prior7_strong_days INTEGER,

    leader_role_proxy VARCHAR(32),
    leader_score_proxy NUMERIC(8,2),
    two_board_quality_score NUMERIC(8,2),
    board_type VARCHAR(32),
    is_20cm BOOLEAN DEFAULT false,

    -- 主线题材层特征
    mainline_strength_score NUMERIC(8,2),
    fade_watch BOOLEAN,
    fade_confirmed BOOLEAN,
    cycle_state VARCHAR(64),

    -- 竞价确认层特征
    auction_feature_mode VARCHAR(32),
    auction_open_pct NUMERIC(8,4),
    auction_amount NUMERIC(18,2),
    auction_score NUMERIC(8,2),
    confirm_level VARCHAR(16),
    confirmation_score NUMERIC(8,2),
    auction_feature_quality VARCHAR(32),
    missing_features JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 牛股三绝特征评分
    bull_stock_score NUMERIC(8,2),

    -- 原始特征与派生特征分离
    raw_feature_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    derived_feature_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),

    UNIQUE(run_id, strategy_version, candidate_trade_date, confirm_trade_date, stock_id)
);
```

### 4.3 策略信号表

```sql
CREATE TABLE IF NOT EXISTS strategy_signal_daily (
    signal_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES w2s_backtest_run(run_id),
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    trade_date DATE NOT NULL,
    signal_session TEXT NOT NULL,
    available_at TIMESTAMP NOT NULL,
    tradable_at TIMESTAMP NOT NULL,

    stock_id TEXT NOT NULL,
    stock_name TEXT,
    subject_key TEXT,
    theme_name TEXT,

    direction TEXT NOT NULL,
    tradable BOOLEAN DEFAULT false,
    signal_level TEXT,
    score NUMERIC(8,2),
    confidence NUMERIC(8,4),

    confirm_level VARCHAR(16),
    confirm_source VARCHAR(32),
    reject_reason_code VARCHAR(64),

    entry_plan JSONB DEFAULT '{}'::jsonb,
    exit_plan JSONB DEFAULT '{}'::jsonb,
    risk_plan JSONB DEFAULT '{}'::jsonb,
    evidence_json JSONB DEFAULT '{}'::jsonb,

    source_chain TEXT NOT NULL DEFAULT 'stock_processing_service',
    source_table TEXT,
    source_id TEXT,
    source_snapshot_version TEXT,
    rule_version TEXT,

    created_at TIMESTAMP DEFAULT now(),

    UNIQUE(run_id, strategy_id, strategy_version, trade_date, signal_session, stock_id, source_id)
);
```

### 4.4 策略信号验证表

```sql
CREATE TABLE IF NOT EXISTS strategy_signal_validation (
    signal_id TEXT PRIMARY KEY REFERENCES strategy_signal_daily(signal_id),
    run_id TEXT NOT NULL REFERENCES w2s_backtest_run(run_id),
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    signal_level TEXT,
    score NUMERIC(8,2),

    buy_ref_date DATE,
    buy_ref_price NUMERIC(18,4),

    next_1d_return NUMERIC(12,6),
    next_2d_return NUMERIC(12,6),
    next_3d_return NUMERIC(12,6),
    next_5d_return NUMERIC(12,6),

    max_return_3d NUMERIC(12,6),
    max_return_5d NUMERIC(12,6),
    max_drawdown_3d NUMERIC(12,6),
    max_drawdown_5d NUMERIC(12,6),

    hit_limit_up_3d BOOLEAN,
    hit_limit_up_5d BOOLEAN,

    is_win_1d BOOLEAN,
    is_win_3d BOOLEAN,
    is_win_5d BOOLEAN,

    loss_over_5pct BOOLEAN,

    validation_status TEXT DEFAULT 'ok',
    validation_error TEXT,

    validated_at TIMESTAMP DEFAULT now()
);
```

### 4.5 验证汇总表

```sql
CREATE TABLE IF NOT EXISTS w2s_validation_summary (
    run_id TEXT NOT NULL REFERENCES w2s_backtest_run(run_id),
    experiment_id VARCHAR(32) NOT NULL,
    confirm_source_group VARCHAR(32),
    confirm_level VARCHAR(16),

    sample_count INTEGER,
    win_rate_1d NUMERIC(8,4),
    win_rate_3d NUMERIC(8,4),
    win_rate_5d NUMERIC(8,4),
    avg_return_3d NUMERIC(12,6),
    avg_return_5d NUMERIC(12,6),
    max_drawdown_5d NUMERIC(12,6),
    hit_limit_up_pct NUMERIC(8,4),
    loss_over_5pct_pct NUMERIC(8,4),

    PRIMARY KEY(run_id, experiment_id, confirm_source_group, confirm_level)
);
```

---

## 5. 实验设计（v3.0）

### 5.1 底层支持6组实验

```python
EXPERIMENT_GROUPS = {
    "EXP_A_BASELINE": {
        "label": "全量基准",
        "conditions": {"pool_entry_type": ("formal", "observe_only")},
    },
    "EXP_B_FORMAL_ONLY": {
        "label": "仅formal候选",
        "conditions": {"pool_entry_type": ("formal",)},
    },
    "EXP_C_MAINLINE": {
        "label": "主线过滤",
        "conditions": {
            "pool_entry_type": ("formal",),
            "mainline_strength_score_min": 60,
            "fade_confirmed": False,
        },
    },
    "EXP_D_LEADER": {
        "label": "龙头过滤",
        "conditions": {
            "pool_entry_type": ("formal",),
            "leader_role_proxy": ("leader", "card"),
        },
    },
    "EXP_E_MAINLINE_LEADER": {
        "label": "主线+龙头",
        "conditions": {
            "pool_entry_type": ("formal",),
            "mainline_strength_score_min": 60,
            "fade_confirmed": False,
            "leader_role_proxy": ("leader", "card"),
        },
    },
    "EXP_F_CONFIRMED_AB": {
        "label": "主线+龙头+A/B确认",
        "conditions": {
            "pool_entry_type": ("formal",),
            "mainline_strength_score_min": 60,
            "fade_confirmed": False,
            "leader_role_proxy": ("leader", "card"),
            "confirm_level": ("A", "B"),
        },
    },
}
```

### 5.2 前端第一版展示3组

```python
VISIBLE_EXPERIMENTS = ["EXP_A_BASELINE", "EXP_C_MAINLINE", "EXP_E_MAINLINE_LEADER"]
```

### 5.3 confirm_source 一级分组

每组实验内按 `confirm_source` 分组输出：
- `real_auction` — 真实竞价分时数据
- `auction_snapshot` — 竞价快照（无分时序列）
- `daily_open_proxy` — 日K代理
- `missing` — 无数据

---

## 6. 竞价评分设计（v3.0）

### 6.1 AuctionFeatureSet

```python
@dataclass
class AuctionFeatureSet:
    stock_id: str
    auction_open_pct: Decimal | None
    auction_amount: Decimal | None
    tail_auction_vwap: Decimal | None

    auction_stability_score: Decimal | None = None
    last_minute_grab_score: Decimal | None = None
    amount_vs_prev_max_minute: Decimal | None = None

    feature_mode: str = "proxy"
    feature_quality: str = "partial"
```

### 6.2 tail_vwap 重构

```python
# 旧逻辑：tail_signal = max(0, min(100, tail_vwap * 5))
# 新逻辑（百分比化）：
tail_strength = (tail_auction_vwap - pre_close) / pre_close * 100
```

### 6.3 权重重归一化

```python
components = [
    ("open_strength", open_strength, Decimal("0.35")),
    ("amount_strength", amount_strength, Decimal("0.30")),
    ("tail_strength", tail_strength, Decimal("0.20")),
    ("stability_score", stability_score, Decimal("0.10")),
    ("last_minute_grab_score", last_minute_grab_score, Decimal("0.05")),
]

available = [(name, score, w) for name, score, w in components if score is not None]
weight_sum = sum(w for _, _, w in available)
raw_score = sum(score * w for _, score, w in available) / weight_sum
final_score = raw_score - risk_penalty
```

**缺数据时权重重归一化，不将缺失当0分惩罚。**

---

## 7. 龙头身份代理（v3.0）

```python
def classify_leader_role_proxy(row: dict) -> str:
    is_leader = bool(row.get("is_leader"))
    rank_order = int(row.get("rank_order") or 999)
    recent_limit_up = int(row.get("recent_limit_up_count") or 0)
    same_subject_limit_up = int(row.get("same_subject_limit_up_count") or 0)

    if is_leader and recent_limit_up >= 2:
        return "leader"
    if rank_order == 2 and recent_limit_up >= 1:
        return "card"
    if 3 <= rank_order <= 5 and same_subject_limit_up >= 2:
        return "assist"
    if recent_limit_up == 0 and same_subject_limit_up >= 1:
        return "supplement"
    return "unknown"


def classify_board_type(stock_id: str) -> tuple[str, bool]:
    if stock_id.startswith("3"):
        return "chinext", True
    if stock_id.startswith("688"):
        return "star", True
    if stock_id.startswith("8"):
        return "beijing", False
    return "main_board", False
```

**leader_role_proxy 和 board_type 独立存储，支持交叉分析。**

---

## 8. API 设计

### 8.1 SPS API

```text
POST /api/v1/backtest/w2s/data-quality
POST /api/v1/backtest/w2s/build-feature-snapshot
POST /api/v1/backtest/w2s/validate-signals
GET  /api/v1/backtest/w2s/runs/{run_id}
GET  /api/v1/backtest/w2s/runs/{run_id}/summary
GET  /api/v1/backtest/w2s/runs/{run_id}/signals
```

### 8.2 web_app_service 代理

```text
POST /api/v2/backtest/w2s/data-quality
POST /api/v2/backtest/w2s/build-feature-snapshot
POST /api/v2/backtest/w2s/validate-signals
GET  /api/v2/backtest/w2s/runs/{run_id}
GET  /api/v2/backtest/w2s/runs/{run_id}/summary
GET  /api/v2/backtest/w2s/runs/{run_id}/signals
```

### 8.3 请求/响应格式

**POST /api/v1/backtest/w2s/data-quality**
```json
{
  "start_date": "2025-06-01",
  "end_date": "2025-12-31",
  "strategy_version": "w2s_v0.1"
}
```

**POST /api/v1/backtest/w2s/build-feature-snapshot**
```json
{
  "run_id": "<uuid>",
  "force_rebuild": false
}
```

**POST /api/v1/backtest/w2s/validate-signals**
```json
{
  "run_id": "<uuid>",
  "look_forward_days": [1, 2, 3, 5]
}
```

---

## 9. 工程约束

### 9.1 Phase 0 不生成买卖建议

Phase 0 只输出验证结论（胜率、收益、回撤等统计指标），不输出"推荐买入某股票"。

### 9.2 confirm_source 必须作为一级分组

报告内必须按 `real_auction / auction_snapshot / daily_open_proxy / missing` 分组统计，不混算。

`daily_open_proxy` 占比高时必须在报告中提示：**当前结论主要基于日K代理确认，不等同真实竞价回测。**

### 9.3 重跑幂等

同一 `(run_id, strategy_version, start_date, end_date)` 重复执行时：

```sql
-- 先删除当前 run_id 下的中间表数据
DELETE FROM w2s_backtest_feature_snapshot WHERE run_id = $1;
DELETE FROM strategy_signal_daily WHERE run_id = $1;
DELETE FROM strategy_signal_validation WHERE run_id = $1;
DELETE FROM w2s_validation_summary WHERE run_id = $1;

-- 再重新生成
```

或使用 `ON CONFLICT ... DO UPDATE`。

**不允许同一只股票同一天出现多条重复信号。**

### 9.4 数据质量门禁

`daily_bar_coverage_ratio < 95%` → 直接阻止验证。

---

## 10. 防未来函数规则

必须给每条信号写入：

```text
signal_session
available_at
tradable_at
source_snapshot_version
source_chain
source_table
```

推荐规则：

```text
post_market 信号：
  available_at = T日 15:30 后
  tradable_at = T+1 09:30

pre_market 信号：
  available_at = T日 09:25 后
  tradable_at = T日 09:30

intraday 信号：
  第一版不支持，后续有分钟数据再做
```

---

## 11. 旧链迁移处理

### 11.1 不再扩展的旧链模块

以下不作为新增回测模块落点：

```text
stock_service/services/stock_screener_service.py
stock_service/repositories/stock_screener_repository.py
stock_service/services/weak_to_strong_candidate_builder.py
stock_service/services/weak_to_strong_auction_service.py
frontend_bff/app.py 内旧 stock_screener 入口
```

### 11.2 可参考但不依赖

旧链里的评分规则、字段命名、显示逻辑可以作为参考，但必须迁移到：

```text
stock_processing_service/application/use_cases
stock_processing_service/application/services
stock_processing_service/domain
stock_processing_service/infrastructure/gateway_adapters
```

### 11.3 临时兼容 import

当前 `stock_processing_service/api_app.py` 仍临时 import 了部分 `stock_service` 的 Tushare/Auction 工具类。这些应被标记为"兼容依赖"，不应成为新回测系统的扩展点。

---

## 12. 开发路线

### Phase 0：数据质量 + 特征快照 + 信号验证闭环

时间：7-11 个工作日

任务：

```text
1. 新增 DDL（w2s_backtest_run / w2s_backtest_feature_snapshot / 完善 strategy_signal 表族）
2. 实现 w2s_data_quality_service.py（daily_bar 覆盖率检查 + 硬门禁）
3. 实现 w2s_feature_snapshot_service.py（读取候选池 + 补充特征 + 冻结快照）
4. 实现 w2s_signal_builder_service.py（从快照生成统一信号）
5. 实现 w2s_signal_validation_service.py（1/3/5日收益计算）
6. 实现 w2s_validation_summary_service.py（6组实验底层 + 3组前端展示）
7. 接 SPS API（6个端点）
8. 接 web_app_service 代理（6个代理端点）
```

验收：

```text
1. 输入 start_date / end_date / strategy_version → 生成 run_id
2. run_id 下生成 feature_snapshot，不重复、不串版本
3. 所有信号都有 candidate_trade_date 和 confirm_trade_date
4. 所有信号都有 confirm_source
5. 能统计真实竞价 vs proxy 样本比例
6. 能输出 A/B/C/X 分组
7. 能输出三组实验 A/B/C
8. 能输出 1/3/5 日胜率、平均收益、最大回撤、涨停概率、亏损超 -5% 比例
9. 能下载/查看信号明细
10. 重跑同一 run_id 不产生重复数据
```

### Phase 1：日线资金回测 MVP

时间：5-8 个工作日

任务：

```text
1. RunDailyBacktestUseCase
2. BacktestDataLoader
3. VirtualBroker（T+1 开盘买入 / 持有N天收盘卖出 / 涨停买不到 / 跌停卖不出）
4. PortfolioManager（等权最多5只）
5. PerformanceAnalyzer（净值曲线 / 回撤）
6. BacktestResult API
```

### Phase 2：竞价评分增强

时间：2-3 个工作日

任务：

```text
1. tail_vwap 重构为百分比化
2. 权重重归一化（缺数据不降权）
3. 竞价模式区分（real_auction_series / auction_proxy）
4. missing_features 记录
```

### Phase 3：牛股三绝 + 二板质量特征评分

时间：3-4 个工作日

```text
1. bull_stock_score 计算（高量不破/倍量不穿/缺口不补/均线多头排列）
2. two_board_quality_score 计算（首板换手率/二板强度/板块效应）
3. 分组回测验证
```

### Phase 4：情绪周期动态仓位

时间：2-3 个工作日

```text
1. cycle_position_sizer（按周期阶段动态调整仓位系数）
2. 各周期阶段分组回测
```

### Phase 5：多策略组合回测

时间：7-12 个工作日

```text
1. 主线龙头策略
2. 题材启动策略
3. 缺口支撑反弹策略
4. 事件驱动题材策略
5. 多策略组合与冲突处理
```

---

## 13. 主要难点

### 13.1 防未来函数

必须严格区分：

```text
候选生成日 → 确认日 → 可用时间 → 可交易时间 → 行情验证窗口
```

### 13.2 竞价数据缺失

第一版大量历史数据没有完整竞价分时，需要通过 `confirm_source` 严格标记：
- 真实竞价样本和 proxy 样本分开统计
- proxy 占比高时在报告中透明提示

### 13.3 日K回测的真实度限制

没有分钟数据，不能验证：
- 竞价尾盘抢筹细节
- 盘中拉升回落
- 开盘瞬间可成交性

第一版只做日线统计和日线撮合。

### 13.4 旧链残留风险

新增代码一律落在 `stock_processing_service`；旧代码只迁移算法思想，不迁移服务依赖。

---

## 14. 最终建议

新链回测系统的正确落点是：

```text
stock_processing_service
  + domain/backtest/
  + application/services/backtest/
  + infrastructure/gateway_adapters/w2s_backtest_gateway_adapter.py
```

对外访问路径是：

```text
frontend
  ↓
web_app_service /api/v2/backtest/w2s/*
  ↓
stock_processing_service /api/v1/backtest/w2s/*
  ↓
DatabaseGateway
  ↓
PostgreSQL / Redis
```

最小闭环从弱转强开始：

```text
weak_to_strong_candidate_pool (BuildWeakToStrongCandidateUseCase)
  ↓
w2s_backtest_feature_snapshot (冻结特征快照)
  ↓
strategy_signal_daily (统一信号)
  ↓
strategy_signal_validation (未来收益验证)
  ↓
w2s_validation_summary (三组实验对照)
  ↓
日线资金回测
```

第一阶段目标：**验证弱转强信号是否有统计区分度，并确认主线、龙头、竞价确认三个条件是否真的提升胜率和收益。**

这一版跑通后，再扩展主线龙头、牛股三绝、竞价增强、情绪周期、多策略组合。

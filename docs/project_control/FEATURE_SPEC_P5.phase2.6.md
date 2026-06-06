# FEATURE SPEC - P5.phase2.6

## 0. Meta
- Phase: `P5.phase2.6`
- Canonical File: `FEATURE_SPEC_P5.phase2.6.md`
- Parent Milestone: `P5（1进2买入法）`
- Source Documents:
  - `docs/architecture/one_to_two_daily_review_architecture.md`
  - `docs/project_control/PHASE_CONTRACT_P5.phase2.6.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/adrs/ADR_LIST.md`
- 目标：
  - 将 `OneToTwoSetupPlanEngine` 的盘后观察清单落成可回放、可审计、可对账、可校准的统一回测闭环。
  - 仅评估盘后观察计划的有效性，不进入盘前/盘中，不接入自动交易，不触碰 A/B/C/D 生产链。
- 非目标：
  - 不做盘前竞价确认。
  - 不做盘中二板触发确认。
  - 不做自动交易执行或 VirtualBroker。
  - 不从 Layer C / D1 读取候选。
  - 不在回测脚本中手写 1进2 规则。

## 1. 任务总览
- `P5.phase2.6-T01`：冻结回测合同与边界守卫
- `P5.phase2.6-T02`：历史回测数据质量检查
- `P5.phase2.6-T03`：冻结 `candidate_features` 特征快照
- `P5.phase2.6-T04`：从特征快照生成统一策略信号
- `P5.phase2.6-T05`：T+1/T+n 信号验证与 outcome 标注
- `P5.phase2.6-T06`：分层汇总与审计对账脚本

---

## Task `P5.phase2.6-T01` — 冻结回测合同与边界守卫

### 1) 目标与边界
- 目标：
  - 明确 `strategy_id=one_to_two`、`strategy_version=one_to_two_v1.0_post_market_plan`、`signal_session=post_market` 的回测合同。
  - 确保回测只使用 T 日及以前事实，不读取 T+1/T+n 参与候选生成。
  - 确保回测不读取 Layer C / D1，不调用任何手写策略规则。
- 非目标：
  - 不做收益曲线回测。
  - 不做盘前/盘中确认。
  - 不修改生产 `post_market_setup_plan` 的语义。

### 1.1 子功能分解
- `F-P5.phase2.6-T01-01` 合同冻结器
  - 输入: 回测区间、`strategy_id`、`strategy_version`、`signal_session`
  - 处理: 校验回测合同字段完整性与版本固定性
  - 输出: 可执行的回测合同对象
  - 失败处理: 缺字段/版本冲突立即 `fail-loud`
  - 可观测证据: `contract_version`, `strategy_id`, `signal_session`
- `F-P5.phase2.6-T01-02` 未来函数守卫
  - 输入: 历史事实源与日期窗口
  - 处理: 强制限制候选生成只能读取 T 日及以前数据
  - 输出: `future_leak_guard_passed=true/false`
  - 失败处理: 一旦发现 T+1/T+n 事实参与候选生成直接失败
  - 可观测证据: `available_at`, `source_snapshot_version`
- `F-P5.phase2.6-T01-03` 生产链隔离守卫
  - 输入: 回测执行上下文
  - 处理: 明确禁止 Layer C / D1、禁止手写规则、禁止 buy 语义
  - 输出: `guard_verdict=pass/reject`
  - 失败处理: 触发立即中止回测 run
  - 可观测证据: `guard_reason`, `blocked_dependency`

### 2) 接口与契约
- 输入：
  - `trade_date_range`
  - `strategy_id="one_to_two"`
  - `strategy_version="one_to_two_v1.0_post_market_plan"`
  - `signal_session="post_market"`
- 输出：
  - 回测合同对象
  - 守卫判定结果
- 错误码：
  - `ONE_TO_TWO_BACKTEST_CONTRACT_MISSING`
  - `ONE_TO_TWO_BACKTEST_FUTURE_LEAK`
  - `ONE_TO_TWO_BACKTEST_LAYER_C_D1_FORBIDDEN`
  - `ONE_TO_TWO_BACKTEST_HARDCODED_RULE_FORBIDDEN`

### 3) 数据模型与状态变更
- 复用回测运行真源（策略通用）。
- 运行记录必须携带：
  - `strategy_id`
  - `strategy_version`
  - `signal_session`
  - `available_at`
  - `tradable_at`
  - `data_quality_json`
  - `status`
- 不引入新的生产策略表。

### 4) 实现步骤（最小可执行序列）
1. 定义回测合同校验函数。
2. 绑定时间窗与 source snapshot 版本。
3. 增加 Layer C / D1 读取守卫。
4. 增加手写规则拒绝守卫。

### 5) 测试设计与命令
- `TC-P5P26-T01-CONTRACT`
- `TC-P5P26-T01-FUTURE-LEAK`
- `TC-P5P26-T01-LAYER-ISOLATION`
- 命令：
  - `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_backtest_contract.py -q`

### 6) 风险与回滚
- 风险：
  - 合同字段缺失导致历史回放无法启动。
  - 守卫过严导致合法样本被阻断。
- 回滚：
  - 回退合同校验层，只恢复到只读审计模式，不恢复未来函数。

### 7) 验收映射
- `ACPT-P5P26-001`
- `ACPT-P5P26-004`
- `ACPT-P5P26-007`

---

## Task `P5.phase2.6-T02` — 历史回测数据质量检查

### 1) 目标与边界
- 目标：
  - 检查历史区间关键事实源覆盖率、缺表/缺字段、空样本是否可接受。
  - 在覆盖率低于阈值时 fail-loud，不允许继续生成 snapshot。
- 非目标：
  - 不做候选生成。
  - 不做信号验证。

### 1.1 子功能分解
- `F-P5.phase2.6-T02-01` 事实源覆盖率检查
  - 输入: 历史区间与数据源清单
  - 处理: 统计 `stock_daily_snapshot`、`subject_stock_daily_snapshot`、`subject_board_stats`、`market_regime` 等覆盖率
  - 输出: `coverage_report`
  - 失败处理: 覆盖率低于阈值直接阻断
  - 可观测证据: `coverage_ratio`, `missing_sources`
- `F-P5.phase2.6-T02-02` 缺表/缺字段检查
  - 输入: 读模型元数据
  - 处理: 检查必需表与必需字段是否齐备
  - 输出: `schema_report`
  - 失败处理: 缺表/缺字段立即失败
  - 可观测证据: `missing_tables`, `missing_columns`
- `F-P5.phase2.6-T02-03` 空样本判定
  - 输入: 数据质量结果
  - 处理: 判定空样本是否为合法业务结果
  - 输出: `empty_is_valid` / `blocking_errors`
  - 失败处理: 非法空样本阻断回测
  - 可观测证据: `empty_days`, `non_empty_days`

### 2) 接口与契约
- 输入：
  - 历史起止日期
  - 事实源白名单
- 输出：
  - `data_quality_json`
- 错误码：
  - `ONE_TO_TWO_DATA_QUALITY_BLOCKED`
  - `ONE_TO_TWO_REQUIRED_SOURCE_MISSING`

### 3) 数据模型与状态变更
- 运行记录写入：
  - `data_quality_json`
  - `blocking_errors`
  - `warnings`
- 回测仅在质量门禁通过后进入 snapshot 冻结。

### 4) 实现步骤（最小可执行序列）
1. 定义质量指标集合。
2. 逐源检查表存在性与字段存在性。
3. 汇总覆盖率与阻断原因。
4. 将结果写入 run 记录。

### 5) 测试设计与命令
- `TC-P5P26-T02-COVERAGE`
- `TC-P5P26-T02-SCHEMA`
- `TC-P5P26-T02-EMPTY-VALIDITY`
- 命令：
  - `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_backtest_data_quality.py -q`

### 6) 风险与回滚
- 风险：
  - 历史数据源暂时不完整。
  - 误将正常空样本当成失败。
- 回滚：
  - 只降低非阻断阈值，不恢复静默通过。

### 7) 验收映射
- `ACPT-P5P26-001`
- `ACPT-P5P26-002`
- `ACPT-P5P26-007`

---

## Task `P5.phase2.6-T03` — 冻结 one_to_two 特征快照

### 1) 目标与边界
- 目标：
  - 逐日重放 `OneToTwoSetupPlanEngine`，冻结 `candidate_features`（含 reject）。
  - 保证特征快照可回放、可审计、可对账。
- 非目标：
  - 不从 T+1/T+n 数据回填特征。
  - 不将 reject 丢失或折叠为 plan items。

### 1.1 子功能分解
- `F-P5.phase2.6-T03-01` 日级上下文重放
  - 输入: T 日事实源
  - 处理: 构造当日 `PostMarketSetupFactContext`
  - 输出: `daily_context`
  - 失败处理: 缺源立即失败
  - 可观测证据: `context_version`, `source_trace`
- `F-P5.phase2.6-T03-02` 特征快照冻结
  - 输入: `OneToTwoSetupPlanDTO`
  - 处理: 将 `candidate_features` 冻结到回测快照
  - 输出: 特征快照记录
  - 失败处理: 快照写入失败立即失败
  - 可观测证据: `snapshot_count`, `reject_count`
- `F-P5.phase2.6-T03-03` reject 审计落库
  - 输入: `candidate_features`
  - 处理: 保留 `decision=reject` 与 `veto_reasons`
  - 输出: 完整审计记录
  - 失败处理: reject 缺 `veto_reasons` 立即失败
  - 可观测证据: `reject_audit_complete`

### 2) 接口与契约
- 输入：
  - T 日事实上下文
  - `OneToTwoSetupPlanEngine`
- 输出：
  - 冻结的特征快照
- 约束：
  - 生成与读取必须只依赖当日及以前事实。

### 3) 数据模型与状态变更
- 回测快照应能表达：
  - `strategy_id=one_to_two`
  - `strategy_version`
  - `trade_date`
  - `watch_date`
  - `stock_id`
  - `subject_key`
  - `decision`
  - `veto_reasons`
  - `score_json`
  - `feature_json`
  - `source_trace_json`
- 若现有回测表字段不足，应扩展统一快照结构，而不是另起孤岛。

### 4) 实现步骤（最小可执行序列）
1. 逐日构造上下文。
2. 调用正式 `OneToTwoSetupPlanEngine`。
3. 冻结 `candidate_features`。
4. 写入回测快照。

### 5) 测试设计与命令
- `TC-P5P26-T03-SNAPSHOT`
- `TC-P5P26-T03-REJECT-AUDIT`
- `TC-P5P26-T03-IDEMPOTENT`
- 命令：
  - `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_backtest_snapshot.py -q`

### 6) 风险与回滚
- 风险：
  - 快照与计划真源不一致。
  - reject 审计缺失。
- 回滚：
  - 删除对应 `run_id` 的快照记录并重放。

### 7) 验收映射
- `ACPT-P5P26-002`
- `ACPT-P5P26-003`
- `ACPT-P5P26-007`

---

## Task `P5.phase2.6-T04` — 从特征快照生成统一策略信号

### 1) 目标与边界
- 目标：
  - 仅从 `focus / observe_only / pending_review_only` 生成 `strategy_signal_daily`。
  - 禁止 buy 语义，信号仅表示观察计划或待确认状态。
- 非目标：
  - 不进入盘前/盘中确认。
  - 不输出 `buy / must_buy / recommend_buy`。

### 1.1 子功能分解
- `F-P5.phase2.6-T04-01` 信号映射器
  - 输入: 冻结后的 `candidate_features`
  - 处理: 将可执行观察项映射为 `strategy_signal_daily`
  - 输出: 统一策略信号
  - 失败处理: 映射失败直接失败
  - 可观测证据: `signal_count`, `signal_level`
- `F-P5.phase2.6-T04-02` 时间戳约束
  - 输入: T 日计划
  - 处理: 固定 `available_at=T日15:30`、`tradable_at=T+1 09:30`
  - 输出: 带时间约束的信号记录
  - 失败处理: 时间戳不合法立即失败
  - 可观测证据: `available_at`, `tradable_at`
- `F-P5.phase2.6-T04-03` buy 语义屏蔽器
  - 输入: 信号文本/字段
  - 处理: 禁止 `buy/must_buy/recommend_buy` 出现
  - 输出: `long_watch` 信号
  - 失败处理: 发现买点语义直接失败
  - 可观测证据: `signal_session`, `direction`

### 2) 接口与契约
- 输入：
  - 冻结特征快照
- 输出：
  - `strategy_signal_daily`
- 约束：
  - `signal_session="post_market"`
  - `direction="long_watch"`
  - `tradable=false`

### 3) 数据模型与状态变更
- 信号表字段建议包含：
  - `strategy_id`
  - `strategy_version`
  - `signal_session`
  - `available_at`
  - `tradable_at`
  - `signal_level`
  - `direction`
  - `risk_plan`
  - `source_snapshot_version`
  - `source_chain`
  - `source_table`

### 4) 实现步骤（最小可执行序列）
1. 从快照读取可执行观察项。
2. 生成统一策略信号。
3. 写入 `strategy_signal_daily`。
4. 过滤掉 reject。

### 5) 测试设计与命令
- `TC-P5P26-T04-SIGNAL`
- `TC-P5P26-T04-AVAILABILITY`
- `TC-P5P26-T04-NO-BUY`
- 命令：
  - `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_backtest_signal_builder.py -q`

### 6) 风险与回滚
- 风险：
  - 信号语义漂移为 buy。
  - 时间戳设置错误导致未来函数。
- 回滚：
  - 删除对应 run 的信号记录并回到快照层。

### 7) 验收映射
- `ACPT-P5P26-004`
- `ACPT-P5P26-007`

---

## Task `P5.phase2.6-T05` — T+1/T+n 信号验证与 outcome 标注

### 1) 目标与边界
- 目标：
  - 用 T+1/T+n 行情验证 OneToTwo 观察清单的次日晋级表现。
  - 标注 `A/B/C/D` outcome，并输出收益、回撤、封板率。
- 非目标：
  - 不改写计划层规则。
  - 不把验证结果反写为计划真源。

### 1.1 子功能分解
- `F-P5.phase2.6-T05-01` 次日涨停触达判定
  - 输入: T+1 行情
  - 处理: 判定是否触及涨停
  - 输出: `next_day_touch_limit_up`
  - 失败处理: 缺行情标 `D_NO_DATA`
  - 可观测证据: `next_day_high_pct`, `next_day_open_pct`
- `F-P5.phase2.6-T05-02` 次日封板判定
  - 输入: T+1 分时/日线结果
  - 处理: 判定是否封住二板
  - 输出: `next_day_sealed_limit_up`
  - 失败处理: 未封板不等于失败；按 outcome 区分
  - 可观测证据: `sealed_rate`, `broken_rate`
- `F-P5.phase2.6-T05-03` outcome 标签器
  - 输入: 验证结果
  - 处理: 生成 `A_SEALED_SECOND_BOARD / B_TOUCHED_BUT_BROKEN / C_FAILED_NO_TOUCH / D_NO_DATA`
  - 输出: `outcome_label`
  - 失败处理: 标签缺失立即失败
  - 可观测证据: `outcome_label`, `validation_status`

### 2) 接口与契约
- 输入：
  - `strategy_signal_daily`
  - T+1 / T+n 行情
- 输出：
  - `strategy_signal_validation`
- 约束：
  - 验证阶段可使用未来数据，但仅用于验证，不得回流到候选生成。

### 3) 数据模型与状态变更
- `strategy_signal_validation` 建议包含：
  - `next_day_touch_limit_up`
  - `next_day_sealed_limit_up`
  - `next_day_open_pct`
  - `next_day_high_pct`
  - `next_day_close_pct`
  - `next_day_open_board_count`
  - `next_day_max_drawdown`
  - `outcome_label`

### 4) 实现步骤（最小可执行序列）
1. 按信号快照取 T+1/T+n 行情。
2. 生成 outcome label。
3. 写入验证表。
4. 统计封板/炸板/失败分层。

### 5) 测试设计与命令
- `TC-P5P26-T05-OUTCOME`
- `TC-P5P26-T05-D-NO-DATA`
- `TC-P5P26-T05-NO-FUTURE-LEAK`
- 命令：
  - `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_backtest_validation.py -q`

### 6) 风险与回滚
- 风险：
  - T+1/T+n 数据缺失导致标签不完整。
  - outcome 规则与计划层冲突。
- 回滚：
  - 删除验证记录即可重放，不影响计划与信号快照。

### 7) 验收映射
- `ACPT-P5P26-005`
- `ACPT-P5P26-006`

---

## Task `P5.phase2.6-T06` — 分层汇总与审计对账脚本

### 1) 目标与边界
- 目标：
  - 对 `post_market_setup_plan`、`one_to_two_candidate_feature`、`strategy_signal_daily`、`strategy_signal_validation` 做分层汇总。
  - 输出可审计、可追踪的回测统计，不允许 buy 语义进入报告。
- 非目标：
  - 不改规则。
  - 不做自动调参。

### 1.1 子功能分解
- `F-P5.phase2.6-T06-01` 分层统计器
  - 输入: plan / snapshot / signal / validation
  - 处理: 按 decision、market_regime、reject_reason、score_bucket 汇总
  - 输出: `summary_json`
  - 失败处理: 数据不一致直接失败
  - 可观测证据: `one_to_two_total_days`, `focus_rate`
- `F-P5.phase2.6-T06-02` 审计对账器
  - 输入: 计划表与候选审计表
  - 处理: 校验 `__SUMMARY__` 唯一、计划项与候选项一致、reject 审计完整
  - 输出: `audit_report`
  - 失败处理: 任一合同缺失直接失败
  - 可观测证据: `reject_audit_complete_rate`
- `F-P5.phase2.6-T06-03` 禁买语义扫描器
  - 输入: 所有回测数据与报告
  - 处理: 扫描 `buy/must_buy/recommend_buy`
  - 输出: `no_buy_token=true/false`
  - 失败处理: 发现买点语义立即失败
  - 可观测证据: `token_scan_result`

### 2) 接口与契约
- 输入：
  - 回测运行 id
  - 计划真源
  - 候选特征快照
  - 信号验证
- 输出：
  - 分层汇总
  - 审计报告
  - 命令行脚本结果

### 3) 数据模型与状态变更
- 汇总输出应至少包含：
  - `one_to_two_total_days`
  - `one_to_two_empty_days`
  - `one_to_two_focus_rate`
  - `one_to_two_reject_audit_complete_rate`
  - `one_to_two_next_day_sealed_rate`
  - `reject_reason_distribution`
- 审计结果必须标记：
  - `summary_unique`
  - `item_count_matches_summary`
  - `reject_audit_complete`
  - `no_buy_signal`

### 4) 实现步骤（最小可执行序列）
1. 汇总计划/信号/验证四层数据。
2. 执行审计对账。
3. 输出失败条件和通过条件。
4. 生成可复跑脚本输出。

### 5) 测试设计与命令
- `TC-P5P26-T06-SUMMARY`
- `TC-P5P26-T06-AUDIT`
- `TC-P5P26-T06-NO-BUY`
- 命令：
  - `./scripts/check_one_to_two_setup_plan_audit.sh --trade-date 2026-06-04`
  - `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_setup_plan_audit.py -q`

### 6) 风险与回滚
- 风险：
  - 汇总与底层快照对不上。
  - 报告中混入买点语义。
- 回滚：
  - 只回滚汇总与报告层，不影响已冻结计划和验证记录。

### 7) 验收映射
- `ACPT-P5P26-006`
- `ACPT-P5P26-007`

---

## 2. 统一实现顺序
1. `T01`：先冻结合同与守卫。
2. `T02`：再做数据质量门禁。
3. `T03`：冻结特征快照。
4. `T04`：生成统一信号。
5. `T05`：做 T+1/T+n 验证。
6. `T06`：做汇总与审计对账。

## 3. 验收总则
- `post_market_setup_plan`、`one_to_two_candidate_feature`、`strategy_signal_daily`、`strategy_signal_validation` 四层必须能串成一个闭环。
- `__SUMMARY__` 行唯一，缺失或重复都必须 fail-loud。
- reject 必须保留 `veto_reasons`。
- 回测中不得出现 buy / must_buy / recommend_buy。
- 不得读取 Layer C / D1，不得引入未来函数。

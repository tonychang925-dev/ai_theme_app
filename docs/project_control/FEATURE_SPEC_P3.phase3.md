# FEATURE SPEC - P3.phase3

## 0. Meta
- Phase: `P3.phase3`
- Historical Alias: `P3.phaseB`
- Canonical File: `FEATURE_SPEC_P3.phase3.md`
- 目标: 补齐第三阶段实时化与高级增强能力，重点覆盖 `/intel` 的 `REST + SSE` 双轨、分钟级异动、情报流联动、异动股票复盘和轻量产业链视图。
- 范围:
  - `GET /api/intel/stream`
  - `minute_abnormal_event`
  - 情报流与股票异动联动
  - `stock_abnormal_signal`
  - 轻量产业链视图
  - `auction_result_validation.v1`
- 非目标:
  - 不建设完整 WebSocket Hub
  - 不建设全市场秒级 Tick 平台
  - 不建设高频策略信号引擎
  - 不把 `stk_auction` 单点结果误写成完整 `9:20~9:25` 路径识别器
  - 不把“异动股票复盘”做成公告摘抄或异动新闻堆积页
- 冲突裁决说明:
  - 历史 `P3.phaseB` 现统一视为 `P3.phase3` 的早期草案。
  - 实时链采用 `REST + SSE`，不直接跳到重型 WebSocket。
  - 分钟级异动必须晚于日频对象层和复盘链稳定之后进入。
  - 集合竞价当前仅完成 `auction_result_validation.v1`，即“昨晚候选池 + 今早 9:25 结果层验证”，不等价于路径稳定性识别。
  - 大环境中的“昨日涨停股早盘表现 / 早盘冲高回落 / 高标早盘强弱”当前仅允许 `daily_proxy` 口径；只有接入真实分钟数据源后，才升级为正式分钟口径。

## Task `P3.phase3-T00` — `auction_result_validation.v1`

### 1) 目标与边界
- 目标:
  - 建立“昨晚候选池 -> 今早 9:25 竞价结果 -> 盘前执行分层”的最小闭环。
  - 先实现 `strong / watch / invalid` 的结果层验证，不等待完整 `Level2` 路径数据。
- 非目标:
  - 不识别 `9:20~9:25` 完整路径稳定性。
  - 不识别 `U 型修复 / 阶梯上行 / 上翘一字` 等完整形态。
  - 不实现全市场竞价扫描。

### 1.1 子功能分解
- `F-P3.phase3-T00-01` 候选池收敛
  - 输入: `theme_mainline_judgement / theme_cycle_judgement / theme_leader_candidate`
  - 处理: 只保留主线与强支线中的 `龙头 / 龙二 / 卡位 / 强趋势`
  - 输出: `auction_watch_universe`
  - 失败处理: 候选池为空时不得伪造竞价结论
  - 可观测证据: `rows / P1 / P2`
- `F-P3.phase3-T00-02` 9:25 结果层快照
  - 输入: `Tushare stk_auction`
  - 处理: 生成 `pre_market_auction_snapshot`
  - 输出: 单点竞价快照 + 代理承接力
  - 失败处理: `stk_auction` 空返回时显式记录 `snapshot_rows=0`
  - 可观测证据: `raw_row_count / snapshot_rows`
- `F-P3.phase3-T00-03` 盘前信号分层
  - 输入: `pre_market_auction_snapshot + auction_watch_universe`
  - 处理: 输出 `pre_market_auction_signal`
  - 输出: `strong / watch / weak / invalid`
  - 失败处理: 硬否决时必须写入 `hard_reject_reason`
  - 可观测证据: 各信号等级数量与拒绝原因
- `F-P3.phase3-T00-04` 盘后验证闭环
  - 输入: `pre_market_auction_signal + subject_stock_daily_snapshot`
  - 处理: 生成 `pre_market_auction_signal_validation`
  - 输出: `confirmed_strong / watch_neutral / reject_confirmed / pending_daily_result`
  - 失败处理: 当日日频结果未入库时必须输出 `pending_daily_result`
  - 可观测证据: `validated / not_validated`

### 2) 接口与契约
- 输入:
  - `auction_watch_universe`
  - `Tushare stk_auction`
  - `subject_stock_daily_snapshot`
- 输出:
  - `pre_market_auction_snapshot`
  - `pre_market_auction_signal`
  - `pre_market_auction_signal_validation`
- 约束:
  - 第一版严格定义为 `auction_result_validation.v1`
  - 当前 `price_path_stability_score` 仅为结果层占位，不得宣称来自真实路径采样

### 3) 数据模型与状态变更
- 新增对象:
  - `auction_watch_universe`
  - `pre_market_auction_snapshot`
  - `pre_market_auction_signal`
  - `pre_market_auction_signal_validation`
- 关键字段:
  - `auction_open_pct`
  - `carry_ratio`
  - `hard_reject_reason`
  - `auction_signal_level`
  - `validation_result`
  - `signal_validated`

### 4) 实现步骤（最小可执行序列）
- Step-1: 生成 `auction_watch_universe`
- Step-2: 读取 `stk_auction`，构建 `pre_market_auction_snapshot`
- Step-3: 生成 `pre_market_auction_signal`
- Step-4: 将竞价信号并入 `pre_market_execution_plan`
- Step-5: 收盘后生成 `pre_market_auction_signal_validation`

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3D-AUC-001-watch-universe`
  - `TC-P3D-AUC-002-auction-snapshot`
  - `TC-P3D-AUC-003-auction-signal`
  - `TC-P3D-AUC-004-auction-validation`
- 必跑命令:
  - `.venv/bin/python -m pytest -q stock_service/tests/unit/test_p3_phase3_auction_*`
  - `.venv/bin/python database_service/scripts/build_auction_watch_universe.py --trade-date <T+1> --source-trade-date <T>`
  - `/opt/miniconda3/bin/python database_service/scripts/build_pre_market_auction_snapshot.py --trade-date <T+1> --token *** --force-refresh`
  - `.venv/bin/python database_service/scripts/build_pre_market_auction_signal.py --trade-date <T+1>`
  - `.venv/bin/python database_service/scripts/build_pre_market_auction_signal_validation.py --trade-date <T+1>`

### 6) 风险与回滚
- 风险:
  - `stk_auction` 数据空返回或窗口不可用
  - 候选池与 `ts_code` 映射不一致
  - 在无日频结果时误判盘后验证
- 回滚:
  - 禁用竞价增强，仅保留 `P3.phase2` 盘前计划

### 7) 验收映射
- `ACPT-P3D-AUC-001`
- `ACPT-P3D-AUC-002`
- `ACPT-P3D-AUC-003`
- `ACPT-P3D-AUC-004`

## Task `P3.phase3-T01` — `/api/intel/stream` 与 `REST + SSE` 双轨

### 1) 目标与边界
- 目标:
  - 建立 `/api/intel/stream` 的 `SSE` 实时出口。
  - 保留 `/api/intel/feed` 作为首屏与回补路径。
- 非目标:
  - 不实现消息 ACK 协议。
  - 不建设全量 WebSocket Hub。

### 1.1 子功能分解
- `F-P3.phase3-T01-01` `SSE` 实时出口
  - 输入: 新增情报条目
  - 处理: 包装为 `text/event-stream`
  - 输出: `intel_item / heartbeat`
  - 失败处理: 推送异常时不中断主服务
  - 可观测证据: `stream_offset`, `event_id`
- `F-P3.phase3-T01-02` `REST` 回补链
  - 输入: 断线重连请求
  - 处理: 通过既有 `/api/intel/feed` 补拉
  - 输出: 缺失增量项
  - 失败处理: 回补失败时显式告警
  - 可观测证据: `last_cursor`, `replay_count`
- `F-P3.phase3-T01-03` 前端双轨接入
  - 输入: `EventSource` + `/api/intel/feed`
  - 处理: 首屏拉取、实时插入、断线恢复
  - 输出: 稳定实时列表
  - 失败处理: `SSE` 失败时自动退回 `REST` 轮询
  - 可观测证据: `reconnect_count`, `fallback_poll_count`

### 2) 接口与契约
- 接口:
  - `GET /api/intel/stream`
  - `GET /api/intel/feed`
- 参数:
  - `date`
  - `session`
  - `type`
  - `subject_key?`
  - `stock_id?`
- 约束:
  - `REST first`, `SSE` 仅为增量增强

### 3) 数据模型与状态变更
- 新增对象:
  - `intel_feed_event`
- 字段:
  - `event_id`
  - `occurred_at`
  - `event_type`
  - `item`
  - `cursor?`

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义 `intel_feed_event` 模型。
- Step-2: 实现 `/api/intel/stream`。
- Step-3: 保留并接通 `/api/intel/feed` 回补链。
- Step-4: 前端接入 `SSE + REST` 双轨。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3D-001-sse-stream`
  - `TC-P3D-002-rest-replay`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "intel/stream|EventSource|heartbeat" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - `SSE` 断线和回补失序
- 回滚:
  - 关闭 `SSE`，退回纯 `REST` 轮询

### 7) 验收映射
- `ACPT-P3D-001`
- `ACPT-P3D-002`

---

## Task `P3.phase3-T02` — 分钟级异动对象 `minute_abnormal_event`

### 1) 目标与边界
- 目标:
  - 建立分钟级异动增强对象。
  - 在具备真实分钟数据源后，补齐大环境的分钟级环境指标：
    - `昨日涨停股今日早盘表现`
    - `早盘冲高回落比例`
    - `高标池早盘强弱`
- 非目标:
  - 不建设 Tick 级盘口引擎。
  - 不在缺少真实分钟源时伪造分钟级环境结论。

### 1.1 子功能分解
- `F-P3.phase3-T02-01` 分钟级原始输入标准化
  - 输入: 分钟级行情刷新
  - 处理: 标准化分钟窗口
  - 输出: 可计算输入对象
  - 失败处理: 窗口不完整时不生成正式异动
  - 可观测证据: 窗口完整率
- `F-P3.phase3-T02-02` 分钟级异动规则
  - 输入: 标准化分钟窗口
  - 处理: 涨速、放量、封板/开板变化等规则计算
  - 输出: `minute_abnormal_event`
  - 失败处理: 规则缺参数时阻断生成
  - 可观测证据: `minute_abnormal_count`
- `F-P3.phase3-T02-03` 可解释性与重放
  - 输入: 分钟级异动对象
  - 处理: 输出解释字段和重放线索
  - 输出: 可解释分钟级异动
  - 失败处理: 无解释字段不得进入正式流
  - 可观测证据: 解释字段覆盖率
- `F-P3.phase3-T02-04` 大环境分钟指标增强
  - 输入: `昨日涨停池 / 高标池` 的分钟序列
  - 处理: 计算分钟口径的 `morning_high_then_fall_ratio / intraday_fade_ratio / yesterday_limit_up_open_strength`
  - 输出: `market_environment_metrics.v2.intraday_mixed`
  - 失败处理: 无分钟数据时必须回退为 `daily_proxy`，不得伪装成分钟真值
  - 可观测证据: `intraday_coverage / source_version`

### 2) 接口与契约
- 输入:
  - `stock_id`
  - `time_window`
- 输出:
  - `minute_abnormal_event`
- 约束:
  - 必须建立在标准化对象层之上
  - 大环境分钟指标第一版只允许覆盖 `昨日涨停池 + 高标池`，不扫全市场

### 3) 数据模型与状态变更
- 新增对象:
  - `minute_abnormal_event`
- 字段:
  - `window_start/window_end`
  - `abnormal_type`
  - `signal_strength`
  - `explanation`

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义分钟级异动对象 schema。
- Step-2: 标准化分钟窗口输入。
- Step-3: 计算分钟级异动规则。
- Step-4: 注入解释字段和重放能力。
- Step-5: 用 `昨日涨停池 + 高标池` 的分钟序列增强 `market_environment_metrics`。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3D-003-minute-abnormal`
  - `TC-P3D-004-minute-abnormal-replay`
  - `TC-P3D-005-market-env-intraday-upgrade`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "minute_abnormal_event" /Users/admin/Desktop/ai_theme_app`
  - `rg -n "market_environment_metrics.v2.intraday_mixed|daily_proxy" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 分钟级异动噪声过高
  - 分钟源覆盖不足导致大环境指标出现“部分真值、部分代理”的混合解释风险
- 回滚:
  - 关闭分钟级对象，仅保留 `SSE` 情报推送
  - 对环境层回退到 `market_environment_metrics.v1.daily_proxy`

### 7) 验收映射
- `ACPT-P3D-003`

---

## Task `P3.phase3-T03` — 情报流与股票异动联动、去重与优先级

### 1) 目标与边界
- 目标:
  - 在同一时间流中联动展示“事件 -> 题材 -> 股票”。
  - 增加去重与优先级排序。
- 非目标:
  - 不输出确定性涨停真因。

### 1.1 子功能分解
- `F-P3.phase3-T03-01` 实时条目联动
  - 输入: 题材情报、股票异动、题材角色变化
  - 处理: 建立联动关系
  - 输出: 联动条目
  - 失败处理: 关联失败时保留单条目而不伪造关系
  - 可观测证据: 关联成功率
- `F-P3.phase3-T03-02` 去重与优先级排序
  - 输入: 实时条目流
  - 处理: 按类型、时间、价值排序
  - 输出: 稳定时间流
  - 失败处理: 去重冲突时保留审计日志
  - 可观测证据: 去重命中数
- `F-P3.phase3-T03-03` 候选归因说明
  - 输入: 资讯和异动联动关系
  - 处理: 输出候选归因和支撑证据
  - 输出: 可解释条目说明
  - 失败处理: 无证据时不输出强因果结论
  - 可观测证据: 候选归因覆盖率

### 2) 接口与契约
- 输入:
  - `intel_feed_event`
  - `minute_abnormal_event`
  - 题材角色变化
- 输出:
  - 联动后的实时条目

### 3) 数据模型与状态变更
- 更新对象:
  - `intel_feed_event`
- 新增字段:
  - `priority`
  - `dedupe_key`
  - `linked_stock_ids`
  - `linked_subject_keys`
  - `candidate_reason`

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义联动条目 schema。
- Step-2: 建立去重和优先级排序规则。
- Step-3: 注入题材/股票联动关系。
- Step-4: 输出候选归因与证据字段。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3D-005-intel-linkage`
  - `TC-P3D-006-realtime-priority-dedupe`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "dedupe|priority|candidate_reason" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 联动条目排序错乱或误导性归因
- 回滚:
  - 停用联动增强，仅保留基础情报与异动条目

### 7) 验收映射
- `ACPT-P3D-005`
- `ACPT-P3D-006`

---

## Task `P3.phase3-T04` — 轻量产业链视图与主链隔离门禁

### 1) 目标与边界
- 目标:
  - 提供题材 -> 环节 -> 股票的轻量只读视图。
  - 建立实时链与日频快照主链隔离门禁。
- 非目标:
  - 不建设重型图谱服务。

### 1.1 子功能分解
- `F-P3.phase3-T04-01` 轻量产业链视图
  - 输入: 题材、环节、股票关系
  - 处理: 组装只读层级结构
  - 输出: 产业链视图 DTO
  - 失败处理: 环节级数据不足时降级为题材 -> 股票
  - 可观测证据: 视图层级完整率
- `F-P3.phase3-T04-02` 实时链主链隔离
  - 输入: 实时推送链、日频快照链
  - 处理: 故障隔离和失败注入
  - 输出: 隔离门禁规则
  - 失败处理: 实时链故障时自动切断实时增强
  - 可观测证据: 主链未受影响证明
- `F-P3.phase3-T04-03` 前端增量刷新兜底
  - 输入: 实时条目与视图请求
  - 处理: 局部刷新和 `REST` 兜底
  - 输出: 页面稳定刷新行为
  - 失败处理: 增量失败时退回整块重拉
  - 可观测证据: fallback 命中率

### 2) 接口与契约
- 接口:
  - `GET /api/intel/stream`
  - 产业链视图只读接口
- 约束:
  - 实时链故障不得阻塞盘前/盘后生成

### 3) 数据模型与状态变更
- 新增对象:
  - 轻量产业链视图 DTO
- 新增门禁:
  - 主链隔离门禁配置

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义轻量产业链视图 DTO。
- Step-2: 定义实时链与主链隔离规则。
- Step-3: 做失败注入验证。
- Step-4: 前端接入局部刷新与兜底策略。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3D-007-light-chain-view`
  - `TC-P3D-008-realtime-mainchain-isolation`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "industry_chain|mainchain|fallback" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 轻量视图膨胀成重型图谱
  - 实时链故障污染主链
- 回滚:
  - 关闭产业链视图和实时增强，仅保留 `REST` 基础链

### 7) 验收映射
- `ACPT-P3D-004`
- `ACPT-P3D-007`

---

## Task `P3.phase3-T05` — 异动股票复盘 `stock_abnormal_signal`

### 1) 目标与边界
- 目标:
  - 为盘后复盘和次日观察池建立“股票异动”事实层。
  - 第一版聚焦 `高换手 / 放量或倍量 / 尾盘抢筹` 三类核心异动。
  - 让异动信号可被 `theme_leader_candidate / pre_market_execution_plan / 当日复盘` 复用。
- 非目标:
  - 不做异动公告收集器。
  - 不在无真实盘口源时伪造“尾盘巨量未成交挂单”真值。
  - 第一版不直接建设 Tick/逐笔级盘口引擎。

### 1.1 子功能分解
- `F-P3.phase3-T05-01` 高换手异动识别
  - 输入: `subject_stock_daily_snapshot / daily_basic`
  - 处理: 计算 `turnover_rate / turnover_rank_in_theme / 高换手标签`
  - 输出: `is_high_turnover / is_extreme_turnover / turnover_abnormal_score`
  - 失败处理: 无换手率时不得输出高换手结论
  - 可观测证据: 高换手股票数、题材内排名覆盖率
- `F-P3.phase3-T05-02` 放量/倍量异动识别
  - 输入: 本地股票日线库、`50日成交量均线`
  - 处理: 计算 `volume_ratio_to_ma50 / is_volume_breakout / is_double_volume`
  - 输出: `volume_abnormal_score`
  - 失败处理: 历史日线不足 50 根时不得输出倍量结论
  - 可观测证据: 放量股票数、倍量股票数
- `F-P3.phase3-T05-03` 尾盘抢筹异动识别
  - 输入: 尾盘成交额窗口或分钟级成交额代理
  - 处理: 计算 `tail_amount / tail_amount_ratio / has_tail_rush_buy`
  - 输出: `tail_abnormal_score`
  - 失败处理: 无分钟级或尾盘窗口数据时仅允许输出 `tail_proxy=false`
  - 可观测证据: 尾盘抢筹股票数
- `F-P3.phase3-T05-04` 复盘与次日观察池联动
  - 输入: `stock_abnormal_signal + theme_leader_candidate + pre_market_execution_plan`
  - 处理: 生成复盘解释与次日观察说明
  - 输出: 盘后“异动股与资金行为”模块、盘前重点观察理由
  - 失败处理: 无异动事实时不允许补写主观解释
  - 可观测证据: 解释字段覆盖率

### 2) 接口与契约
- 输入:
  - `subject_stock_daily_snapshot`
  - 本地 `Tushare` 股票日线库
  - `daily_basic`
  - 可选尾盘成交窗口
- 输出:
  - `stock_abnormal_signal`
- 约束:
  - 第一版只承诺：
    - 高换手
    - 放量 / 倍量（`>= 2 * 50日均量`）
    - 尾盘成交放大抢筹
  - `尾盘巨量未成交挂单` 归入后续盘口增强项，不得在缺数据时编造

### 3) 数据模型与状态变更
- 新增对象:
  - `stock_abnormal_signal`
- 关键字段:
  - `turnover_rate`
  - `turnover_rank_in_theme`
  - `turnover_abnormal_score`
  - `volume_ratio_to_ma50`
  - `is_volume_breakout`
  - `is_double_volume`
  - `tail_amount`
  - `tail_amount_ratio`
  - `has_tail_rush_buy`
  - `abnormal_labels`
  - `abnormal_composite_score`
  - `conclusion`

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义 `stock_abnormal_signal` schema。
- Step-2: 先实现高换手与放量/倍量识别。
- Step-3: 接入尾盘成交窗口，补 `tail_abnormal_score`。
- Step-4: 将异动标签接入复盘页和次日观察池。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3D-009-stock-abnormal-turnover`
  - `TC-P3D-010-stock-abnormal-volume`
  - `TC-P3D-011-stock-abnormal-tail`
  - `TC-P3D-012-stock-abnormal-recap-linkage`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "stock_abnormal_signal|tail_abnormal|double_volume|turnover_abnormal" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 高换手在高潮期被误读为强势而非分歧兑现
  - 无尾盘盘口时对“抢筹”解释过度
  - 放量标签过多导致噪音过高
- 回滚:
  - 关闭 `stock_abnormal_signal` 展示层，仅保留主线/周期/龙头主链
  - 将尾盘异动退回纯日频解释，不进入次日观察池

### 7) 验收映射
- `ACPT-P3D-008`
- `ACPT-P3D-009`
- `ACPT-P3D-010`

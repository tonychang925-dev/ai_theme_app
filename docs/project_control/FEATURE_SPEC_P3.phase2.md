# FEATURE SPEC - P3.phase2

## 0. Meta
- Phase: `P3.phase2`
- 目标: 在 `P3.phase1` 稳定对象层之上补齐复盘增强与工作台深化能力，重点覆盖龙虎榜、资金行为增强、龙头/前排/扩散规则增强、个股工作台与 `/recap`。
- 范围:
  - 龙虎榜结构化对象
  - 资金行为增强字段
  - `F10` 资金动向快照增强
  - `theme_stock_leaderboard` 角色增强
  - 个股工作台增强
  - `/recap` 只读产品出口
- 非目标:
  - 不引入 `SSE`
  - 不引入分钟级异动
  - 不建设完整主力资金行为体系
  - 不在复盘主流程中现场抓取 `F10`
- 冲突裁决说明:
  - `recap_service` 是唯一报告聚合层。
  - 新增字段只增不改，兼容 `P3.phase1` DTO。
  - `F10` 资金动向仅作为可插拔展示增强，不替代现有真源语义。

## 0.1 P3.phase2 核心收口

`P3.phase2` 的最终落地方向冻结为 3 张真源表：

1. `theme_mainline_judgement`
2. `theme_cycle_judgement`
3. `theme_leader_candidate`

并明确：

- `每日复盘` = 这 3 张表的结果展示与汇总
- `盘前推荐` = 基于昨晚这 3 张表做次日承接验证

不得反向把：

- 盘前必读
- 每日复盘
- Notion 页面

作为新的事实真源。

## 0.2 Phase2 开发顺序冻结

`P3.phase2` 的开发顺序固定为：

1. `theme_mainline_judgement`
2. `theme_cycle_judgement`
3. `theme_leader_candidate`
4. `RecapService` 改为读取上述 3 张表
5. 盘前承接验证层

原因：

- 先判断是否主线
- 再判断所处周期
- 再判断主线内谁最强
- 最后才做盘前动作验证

这与《如何建立正确的交易体系》中的 `35% / 30% / 20% / 15%` 决策顺序一致。

## 0.3 三张真源表的最小字段要求

### `theme_mainline_judgement`

必须包含：

- `event_chain_score`
- `event_chain_continuity_score`
- `market_recognition_score`
- `mainline_stability_score`
- `is_main_theme`
- `theme_tier`
- `limit_up_count`
- `conclusion`
- `source_version`
- `rule_version`

### `theme_cycle_judgement`

必须包含：

- `is_start`
- `is_fermentation`
- `is_divergence`
- `is_rebound`
- `is_climax`
- `is_fade`
- `primary_cycle_stage`
- `leader_status`
- `board_effect_status`
- `action_bias`
- `confidence`
- `conclusion`
- `source_version`
- `rule_version`

### `theme_leader_candidate`

必须包含：

- `purity_score`
- `leading_score`
- `capital_score`
- `structure_score`
- `resilience_score`
- `composite_score`
- `role_label`
- `candidate_rank`
- 轻量事实冗余字段：
  - `is_limit_up`
  - `limit_up_type`
  - `turnover_rate`
  - `volume_ratio`
  - `main_net_inflow`
  - `is_new_stock`
- `source_version`
- `rule_version`

## 0.4 字段来源与生成责任

### A. 原始事实输入

来自：

- `jyhf_history`
- `news_event / event_theme_map`
- `subject_stock_daily_snapshot`
- `theme_stock_rollup`
- `stock_abnormal_event`

### B. 规则层生成

生成：

- `event_chain_score`
- `event_chain_continuity_score`
- `market_recognition_score`
- `mainline_stability_score`
- `primary_cycle_stage`
- `action_bias`
- `candidate_rank`
- `role_label`

### C. 展示层汇总

生成：

- 每日复盘页面
- 盘前推荐页面
- Notion 页面块结构

### D. LLM 允许生成

仅允许：

- 总结语句
- 风险提示
- 展示性解释文字

### E. LLM 不允许覆盖

明确禁止覆盖：

- 主线判断
- 周期状态
- 龙头角色标签
- 候选排序
- 各类事实分数

## 0.5 2026-04-02 ~ 2026-04-02 实施回写（增量）

截至 `2026-04-02`，`P3.phase2` 已按冻结顺序完成以下核心链路：

1. `theme_mainline_judgement`
   - 已实现首版规则服务与真实构建脚本
   - 已完成 `2026-04-01` 真库构建
2. `theme_cycle_judgement`
   - 已实现状态机与动作建议
   - 已完成 `2026-04-01` 真库构建
3. `theme_leader_candidate`
   - 已实现五维评分、角色标签和前 4 候选分层
   - 已完成 `2026-04-01` 真库构建
4. `RecapService`
   - 已切换为读取上述 3 张真源表
   - `post_market` 不再以原始情报流作为主骨架
5. `pre_market_execution_plan`
   - 已实现盘前承接验证层
   - `pre_market` 已切换为读取该真源表

对应真实快照样本：

- 盘后：
  - `theme_data_complete/_report_snapshots/post_market/2026-04-01__p3_phase2_recap_truth_20260401.*`
- 盘前：
  - `theme_data_complete/_report_snapshots/pre_market/2026-04-01__p3_phase2_pre_market_truth_fix_20260401.*`

新增完成项（截至 `2026-04-02` 晚）：

- `dragon_tiger_object`
  - 已完成 `Tushare top_list/top_inst -> raw snapshot/cache -> 结构化对象`
  - 已完成 `2026-04-01` 真数据 smoke test
- `money_flow_enhanced`
  - 已接入龙虎榜净额和机构席位摘要
  - 已完成 `2026-04-01 / 2026-04-02` 真库构建
- 个股工作台增强
  - 已统一聚合股票基础、所属题材、资金行为、龙虎榜、角色标签
  - 前端不再自行拼装多源股票对象
- `/recap` 只读产品出口
  - 已完成 BFF 接口与前端页面
  - 首页已能直接跳转最新 `当日复盘 / 盘前必读`
- 来源链标准化
  - `theme_mainline_judgement`
  - `theme_cycle_judgement`
  - `theme_leader_candidate`
  - `money_flow_enhanced`
  已统一补齐：
  - `source_type`
  - `source_trace_id`
  - `source_trace`
  - `source_version`
  - `rule_version`
- 跨交易日一致性回测
  - 已完成 `2026-04-01 / 2026-04-02`
  - 结果：来源链覆盖率 `100%`

当前阶段结论：

- `P3.phase2` 的核心目标已不再停留在设计稿层面
- 已形成“主线 -> 周期 -> 龙头分层 -> 盘前承接”的可执行闭环
- `P3.phase2` 的核心主链已基本完成
- 后续优化重点应转向规则精调、展示层优化与正式门禁收口，而不是再扩底层对象种类

## Task `P3.phase2-T01` — 龙虎榜结构化对象与来源链

### 1) 目标与边界
- 目标:
  - 生成龙虎榜结构化对象并保留来源链。
- 非目标:
  - 不做席位行为深度分析模型。

### 1.1 子功能分解
- `F-P3.phase2-T01-01` 龙虎榜原始源接入
  - 输入: 原始龙虎榜数据
  - 处理: 标准化字段与来源标记
  - 输出: 结构化龙虎榜对象
  - 失败处理: 原始来源缺失时阻断生成
  - 可观测证据: `dragon_tiger_object_count`
- `F-P3.phase2-T01-02` 席位摘要聚合
  - 输入: 结构化席位数据
  - 处理: 摘要化净买入额、原因、席位概览
  - 输出: 页面可读摘要
  - 失败处理: 席位异常时保留原始链路并降级摘要
  - 可观测证据: `source_trace_id`
- `F-P3.phase2-T01-03` 来源链回溯
  - 输入: 龙虎榜对象 ID
  - 处理: 映射回原始来源
  - 输出: 完整来源链
  - 失败处理: 来源链不完整则不进入正式复盘
  - 可观测证据: 来源链覆盖率

### 2) 接口与契约
- 输入:
  - `trade_date`
  - `stock_id`
- 输出:
  - 龙虎榜结构化对象
  - 来源链字段

### 3) 数据模型与状态变更
- 新增对象:
  - `dragon_tiger_object`
- 状态变更:
  - 每交易日批处理生成

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义龙虎榜对象 schema。
- Step-2: 标准化原始龙虎榜来源。
- Step-3: 生成席位摘要和来源链。
- Step-4: 接入复盘消费路径。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3C-001-dragon-tiger-object`
  - `TC-P3C-002-dragon-tiger-trace`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "dragon_tiger|source_trace" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 来源链断裂
- 回滚:
  - 停用龙虎榜增强对象，只保留基础复盘快照

### 7) 验收映射
- `ACPT-P3C-001`

---

## Task `P3.phase2-T02` — 资金行为增强与题材角色规则

### 1) 目标与边界
- 目标:
  - 增加轻量资金行为增强字段。
  - 强化龙头、前排、扩散股、跟风股角色规则。
- 非目标:
  - 不承诺完整主力资金行为体系。

### 1.1 子功能分解
- `F-P3.phase2-T02-01` 资金行为增强字段
  - 输入: 股票快照与增强数据
  - 处理: 生成净流入、活跃度、强度分层
  - 输出: 资金行为增强对象
  - 失败处理: 字段缺失时不伪造结果
  - 可观测证据: `money_flow_enhanced_count`
- `F-P3.phase2-T02-02` 题材角色规则增强
  - 输入: `theme_stock_leaderboard` + 增强字段
  - 处理: 重新区分龙头/前排/扩散/跟风
  - 输出: 角色增强榜单
  - 失败处理: 规则不完整时阻断正式写入
  - 可观测证据: 角色覆盖率
- `F-P3.phase2-T02-03` 规则解释字段
  - 输入: 角色判定规则
  - 处理: 输出解释字段
  - 输出: 可回放解释结果
  - 失败处理: 无解释字段则不进入正式对象
  - 可观测证据: 解释字段覆盖率

### 2) 接口与契约
- 输入:
  - `trade_date`
  - `stock_id`
  - `subject_key`
- 输出:
  - 资金行为增强字段
  - 增强后的题材角色

### 3) 数据模型与状态变更
- 新增对象:
  - `money_flow_enhanced`
- 更新对象:
  - `theme_stock_leaderboard`

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义资金行为增强字段。
- Step-2: 增强角色规则。
- Step-3: 输出规则解释字段。
- Step-4: 建立回放验证。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3C-003-money-flow-enhanced`
  - `TC-P3C-004-role-enhanced-leaderboard`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "money_flow|theme_stock_leaderboard" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 角色规则过度复杂导致不可解释
- 回滚:
  - 回退到 `P3.phase1` 基础角色口径

### 7) 验收映射
- `ACPT-P3C-002`
- `ACPT-P3C-003`

---

## Task `P3.phase2-T03` — 个股工作台增强与 `/recap` 只读出口

### 1) 目标与边界
- 目标:
  - 深化个股工作台。
  - 提供 `/recap` 只读产品出口。
- 非目标:
  - 不引入实时推送。

### 1.1 子功能分解
- `F-P3.phase2-T03-01` 个股工作台增强 DTO
  - 输入: 股票详情、所属题材、龙虎榜、资金行为、角色标签
  - 处理: 聚合统一 DTO
  - 输出: 工作台增强对象
  - 失败处理: 缺部分区块允许 partial，不允许前端拼装底层表
  - 可观测证据: `workspace_route`
- `F-P3.phase2-T03-02` `/recap` 只读产品出口
  - 输入: 盘前/盘后复盘快照
  - 处理: 统一读取和筛选
  - 输出: `/recap` 页面可读对象
  - 失败处理: 读取失败返回明确错误，不返回伪空
  - 可观测证据: `recap_id`
- `F-P3.phase2-T03-03` 前端兼容门禁
  - 输入: 新旧 DTO
  - 处理: 向后兼容校验
  - 输出: 稳定版本契约
  - 失败处理: 兼容性破坏则阻断发布
  - 可观测证据: 兼容性报告

### 2) 接口与契约
- 接口:
  - `GET /api/stock-workspace/{stock_id}`
  - `GET /api/recap`
- 约束:
  - 前端不得重新拼装底层多源数据

### 3) 数据模型与状态变更
- 读取对象:
  - `post_market_recap_snapshot`
  - 增强后的股票工作台对象
- 兼容策略:
  - 新字段只增不改

### 4) 实现步骤（最小可执行序列）
- Step-1: 扩展 stock workspace DTO。
- Step-2: 定义 `/recap` 只读契约。
- Step-3: 接入来源链和增强字段。
- Step-4: 做兼容性回归验证。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3C-005-stock-workspace-enhanced`
  - `TC-P3C-006-recap-readonly`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "/recap|workspace" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 工作台重新变成前端拼装页
- 回滚:
  - 回退到 `P3.phase1` 基础工作台

### 7) 验收映射
- `ACPT-P3C-004`
- `ACPT-P3C-005`

---

## Task `P3.phase2-T04` — 来源链与 `recap_service` 唯一聚合层门禁

### 1) 目标与边界
- 目标:
  - 为每条关键复盘结论提供来源链。
  - 冻结 `recap_service` 为唯一报告聚合层。
- 非目标:
  - 不引入实时链。

### 1.1 子功能分解
- `F-P3.phase2-T04-01` 来源链标准化
  - 输入: 股票事实、题材事件、龙虎榜、资金行为来源
  - 处理: 生成标准来源链
  - 输出: `source_trace`
  - 失败处理: 缺来源链的结论不入正式快照
  - 可观测证据: `recap_trace_coverage_ratio`
- `F-P3.phase2-T04-02` 聚合层唯一化
  - 输入: 多出口复盘读取需求
  - 处理: 强制经过 `recap_service`
  - 输出: 唯一聚合快照
  - 失败处理: 发现绕过聚合层时阻断评审
  - 可观测证据: 聚合路径扫描结果
- `F-P3.phase2-T04-03` 模板兼容
  - 输入: 前端与 Notion 模板
  - 处理: 验证新增字段兼容
  - 输出: 兼容性确认
  - 失败处理: 模板不兼容则阻断发布
  - 可观测证据: 模板校验报告

### 2) 接口与契约
- 输入:
  - `recap_id`
  - `trade_date`
- 输出:
  - 带来源链的增强复盘快照
- 约束:
  - 来源链覆盖率必须 `100%`

### 3) 数据模型与状态变更
- 更新对象:
  - `post_market_recap_snapshot`
- 新增字段:
  - `source_trace`
  - `source_types`
  - `evidence_refs`

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义来源链字段规范。
- Step-2: 把来源链注入复盘快照。
- Step-3: 扫描并阻断绕过 `recap_service` 的路径。
- Step-4: 做前端与 Notion 模板兼容校验。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3C-007-recap-traceability`
  - `TC-P3C-008-recap-service-boundary`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "recap_service|source_trace|evidence_refs" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 来源链不完整导致结论不可审计
- 回滚:
  - 停用增强结论，仅保留基础复盘快照

### 7) 验收映射
- `ACPT-P3C-006`
- `ACPT-P3C-007`

---

## Task `P3.phase2-T05` — `F10` 资金动向快照增强（横切追加）

### 1) 目标与边界
- 目标:
  - 将通达信 `F10`「资金动向」结构化为可缓存、可追溯的增强证据。
  - 在不改变现有真源语义的前提下，把快照挂载到复盘与 `1进2` 展示对象。
- 非目标:
  - 不进入 `OneToTwoScorer`。
  - 不替代 `money_flow_reviews` / `stock_capital_reviews` / `dragon_tiger_reviews` 的主事实。
  - 不在复盘主流程中现场抓取 `F10`。
  - 不把 `L2`「涨停分析」混入标准 `F10` 资金动向。

### 1.1 子功能分解
- `F-P3.phase2-T05-01` `F10` 资金动向快照落库
  - 输入: `trade_date + stock_id + section=资金动向`
  - 处理: 采集层写入 `stock_f10_capital_snapshot`
  - 输出: 标准化快照记录
  - 失败处理: 单股失败只记录 `parse_status / diagnostics`，批次失败才阻断采集任务
  - 可观测证据: `snapshot_count / parse_status / source_updated_date`
- `F-P3.phase2-T05-02` 资金动向正文解析
  - 输入: 快照原文
  - 处理: 切分 `交易龙虎榜 / 大宗交易 / 融资融券 / 资金流向 / 战略配售可出借`
  - 输出: `f10_capital` 结构体
  - 失败处理: 局部段落缺失按空值处理，不伪造结果
  - 可观测证据: `section_hit_count / parse_status`
- `F-P3.phase2-T05-03` 复盘 review 挂载
  - 输入: `money_flow_reviews / stock_capital_reviews / dragon_tiger_reviews`
  - 处理: 只读挂载 `f10_capital`
  - 输出: 增强后的 review 视图
  - 失败处理: 无快照则回退到原 review，不阻断复盘
  - 可观测证据: `f10_hit_count / f10_missing_count`
- `F-P3.phase2-T05-04` `1进2` 观察计划挂载
  - 输入: `post_market_setup_plan.items`
  - 处理: 追加 `f10_capital` 展示字段
  - 输出: 观察清单增强对象
  - 失败处理: 不影响 `decision / final_score / watch_level`
  - 可观测证据: `one_to_two_f10_hit_count`
- `F-P3.phase2-T05-05` 前端展示增强
  - 输入: 带 `f10_capital` 的 recap / workspace / watch panel
  - 处理: 复盘页展示完整摘要，`1进2` 只展示短摘要，个股工作台展示全量明细
  - 输出: 前端可读卡片
  - 失败处理: 字段缺失时回退原 UI
  - 可观测证据: 页面渲染成功率

### 2) 接口与契约
- 输入:
  - `trade_date`
  - `stock_ids`
- 输出:
  - `f10_capital_by_stock`
  - `f10_limitup_analysis`（可选，独立字段，不与标准 `F10` 混用）
- 约束:
  - 复盘只读 `stock_f10_capital_snapshot`
  - 采集与解析分离，不允许复盘时现抓 `F10`

### 3) 数据模型与状态变更
- 新增对象:
  - `stock_f10_capital_snapshot`
- 更新对象:
  - `post_market_recap_snapshot`
  - `money_flow_reviews`
  - `stock_capital_reviews`
  - `dragon_tiger_reviews`
  - `post_market_setup_plan.items`
  - `watchlists.one_to_two.items`
- 新增字段:
  - `f10_capital`
  - `f10_limitup_analysis`
  - `source_updated_date`
  - `parse_status`
  - `diagnostics`

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义 `stock_f10_capital_snapshot` 表与读写接口。
- Step-2: 抽取 `F10` 资金动向 parser 与 evidence service。
- Step-3: 新增独立采集任务，先落快照再进入复盘。
- Step-4: 在 `BuildPostMarketRecapJob` 中挂载 review 与 `1进2` 展示字段。
- Step-5: 在前端复盘页、观察清单与个股工作台中展示增强内容。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3C-009-f10-capital-parser`
  - `TC-P3C-010-f10-capital-snapshot-gateway`
  - `TC-P3C-011-f10-capital-recap-attach`
  - `TC-P3C-012-f10-capital-one-to-two-attach`
  - `TC-P3C-013-f10-capital-score-isolation`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "stock_f10_capital_snapshot|f10_capital|f10_limitup_analysis" /Users/admin/Desktop/ai_theme_app`

### 6) 风险与回滚
- 风险:
  - 复盘主流程被外部 `F10` 网络波动拖慢
  - `L2` 增强内容误混入标准 `F10` 事实
- 回滚:
  - 停用采集任务与挂载逻辑，仅保留原有 `money_flow_reviews / dragon_tiger_reviews / stock_capital_reviews`

### 7) 验收映射
- `ACPT-P3C-008`

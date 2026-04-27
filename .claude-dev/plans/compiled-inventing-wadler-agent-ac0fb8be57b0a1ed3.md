# Plan: 继续探索新旧链架构差异

基于上一轮会话已完成的 5 个子任务，按 Next Actions 继续深入探索。

## 待完成子任务

### 1. 读取 postgres_manager.py 中主链相关 SQL 方法
- 定位 `database_service/managers/postgres_manager.py` 中与 `theme_mainline_identity_registry`、`mainline_state_daily`、`theme_cycle_judgement_v2` 相关的 upsert/query 方法
- 确认新链底层 SQL 实现与旧链 asyncpg 直连的差异

### 2. 对比旧链与新链的身份判定逻辑
- 旧链: `stock_service/scripts/build_mainline_identity_registry.py` (~2200行)
- 新链: `stock_processing_service/application/jobs/build_identity_job.py`
- 重点确认两者是否会产生写入冲突

### 3. 追踪 BuildPostMarketRecapJob 中 Layer A/B 数据流
- 从 `identities_by_subject` (来自 `theme_mainline_identity_registry`) 和 `cycles_by_subject` (来自 `theme_cycle_judgement_v2`) 到最终候选池生成的完整数据传递链

### 4. 检查回放快照文件
- 查看 `tmp/new_chain_runs/` 目录下 2026-04-07 和 2026-04-15 的回放快照

### 5. 分析回放测试 Runner 的适配层
- 深入了解 `_ReplayDatabaseStockFacade` 如何模拟数据库行为

## 约束
- 只读操作，不修改任何文件
- 输出语言为中文

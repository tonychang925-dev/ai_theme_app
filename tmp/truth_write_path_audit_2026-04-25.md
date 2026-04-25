# `stock_daily_snapshot` 真源写口审计（2026-04-25）

## 结论
- 生产业务路径中，`stock_processing_service` 已无直接调用 `upsert_stock_daily_snapshot_rows(...)` 的代码。
- 真源表当前数据已满足白名单：`source_name ILIKE 'tushare%'`，非真源行数量为 `0`。
- 风险主要残留在“接口暴露层 + 适配器兼容层 + 测试替身”，不是主链业务逻辑。

## 审计范围
- 检索关键写口：`upsert_stock_daily_snapshot_rows(`
- 审计日期：`2026-04-25`
- 数据库：`stock_data_test`

## 分类结果

### A. 真源合法（应保留）
- `/Users/admin/Desktop/ai_theme_app/database_service/managers/postgres_manager.py`
  - 真源写入唯一底层实现。
  - 已加硬门：仅允许 `source_name like 'tushare%'`。
- `/Users/admin/Desktop/ai_theme_app/database_service/gateway.py`
  - 网关转发层，调用 manager 的真源写口。
  - 不做业务放宽，受 manager 与 DB trigger 双重保护。

### B. 测试/文档路径（可保留）
- 测试：
  - `/Users/admin/Desktop/ai_theme_app/database_service/tests/unit/test_stock_daily_truth_guard.py`
  - `/Users/admin/Desktop/ai_theme_app/stock_processing_service/tests/**` 下 mock 方法与适配器测试
- 文档：
  - `/Users/admin/Desktop/ai_theme_app/docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
  - `/Users/admin/Desktop/ai_theme_app/docs/architecture/stock_processing_service-架构设计方案.md`

### C. 残留接口（收口状态）
- 已完成收口：
  - `/Users/admin/Desktop/ai_theme_app/stock_processing_service/ports/write_ports.py`
    - 已移除 `upsert_stock_daily_snapshot_rows` 协议暴露。
  - `/Users/admin/Desktop/ai_theme_app/stock_processing_service/ports/database_gateway_stock_facade.py`
    - 已移除同名协议暴露。
  - `/Users/admin/Desktop/ai_theme_app/stock_processing_service/infrastructure/gateway_adapters/stock_write_gateway_adapter.py`
    - 已移除同名实现。
- 安全阻断（保留兼容入口但硬失败）：
  - 无（已完成彻底移除）。

## 当前硬保护状态
- 应用层保护：
  - `postgres_manager.upsert_stock_daily_snapshot_rows` 仅接受 `tushare*` 源。
  - `BuildDailySnapshotJob` 已禁止回退到真源表（缺策略写口即报错）。
- 数据库层保护：
  - trigger: `trg_guard_stock_daily_snapshot_truth`
  - function: `sps_guard_stock_daily_snapshot_truth()`
  - 规则：`NEW.source_name IS NULL OR LOWER(source_name) NOT LIKE 'tushare%'` => 阻断。

## 数据核验
- SQL:
  - `SELECT COUNT(*) FROM stock_daily_snapshot WHERE COALESCE(source_name,'') NOT ILIKE 'tushare%';`
- 结果：
  - `0`

## 防回归门禁（新增）
- `stock_processing_service/tests/unit/test_truth_write_path_guard.py`
  - 扫描 `stock_processing_service` 生产代码（排除 tests），若出现
    `upsert_stock_daily_snapshot_rows(` 则测试失败。

## 下一步
1. 保持防回归检查：`stock_processing_service` 生产代码不允许出现 truth 表写口调用。

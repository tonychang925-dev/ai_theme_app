# FEATURE SPEC - P4.phase3

## 0. Meta
- Phase: `P4.phase3`
- 目标: 页面扩展与边界清理，完成 themes/stocks/screener 的 v2 迁移。

## Task P4.phase3-T01 — `/themes/:subjectKey` 迁移
### 1) 子功能分解
- `F-P4.phase3-T01-01` adapter 迁移到 v2 DTO。
- `F-P4.phase3-T01-02` 页面联动回归。
- `F-P4.phase3-T01-03` 监控埋点。
### 2) 验收映射
- `ACPT-P4-301`

## Task P4.phase3-T02 — `/stocks/:stockId` 迁移
### 1) 子功能分解
- `F-P4.phase3-T02-01` 详情数据改走 v2。
- `F-P4.phase3-T02-02` 历史与事件联动回归。
- `F-P4.phase3-T02-03` 错误语义对齐。
### 2) 验收映射
- `ACPT-P4-302`

## Task P4.phase3-T03 — `/screener` 迁移与旧依赖清理
### 1) 子功能分解
- `F-P4.phase3-T03-01` 筛选请求改造。
- `F-P4.phase3-T03-02` 旧别名路径清零。
- `F-P4.phase3-T03-03` 全链回归。
### 2) 测试命令
- `rg -n --pcre2 "['\"]/api/(?!v2/)" frontend/src`
### 3) 验收映射
- `ACPT-P4-303`

## 风险与回滚
- 风险: 迁移页回归影响旧页稳定性。
- 回滚: 路由粒度回滚，不做全局回退。

## 增量任务分解（2026-05-01 对齐第11章）

### Task P4.phase3-N01 — stream 全量新链化
- `F-P4.phase3-N01-01` `intel/stream` 对接新流网关。
- `F-P4.phase3-N01-02` SSE 事件契约一致性校验。
- `F-P4.phase3-N01-03` stream 断流降级策略固化。

### Task P4.phase3-N02 — 旧链运行路径下线
- `F-P4.phase3-N02-01` 停止 `stock_service` 线上依赖入口。
- `F-P4.phase3-N02-02` 下线旧端口兼容链路（迁移窗口后）。
- `F-P4.phase3-N02-03` 发布后 5 个交易日稳定性验收。

# 实时情报全链路阶段1 - 进展报告

## 概览

- **报告日期**: 2026-04-10
- **阶段名称**: 实时情报全链路阶段1（AkShare → Stream → SSE → Intel页面）
- **状态**: 已完成（可联调）
- **目标**: 在既有实现基础上，打通定期采集、结构化处理、主题匹配、实时推送与前端展示

## 阶段目标与约束

1. 启动 AkShare 定期采集并进入 `stream:news:raw`
2. 经由既有处理链路完成 `news_raw`、`news_event`、事件匹配与 feed 生产
3. 通过 SSE 实时推送到前端“情报”页面
4. 实时链路禁止自动创建新题材，未匹配事件进入人工复核

## 已完成内容

### 1) 实时链路安全门禁（禁止自动建题材）

- 在 `ThemeProcessor` 决策层增加 NO_MATCH 实时门禁（默认关闭自动建题材）
- 在 `DecisionExecutor` 执行层增加兜底拦截，防止旁路触发 `create_new_theme`
- 新增环境开关：
  - `ALLOW_REALTIME_AUTO_THEME_CREATE=false`（默认建议）

### 2) 人工复核队列与入库

- 新增表 `event_review_queue` 与索引：
  - `database_service/scripts/create_event_review_queue.sql`
- 新增网关写入能力（幂等）：
  - `database_service/managers/postgres_manager.py`
  - `database_service/gateway.py`
- 被门禁拦截事件自动入 `event_review_queue(waiting)`，用于人工复核后再入图谱

### 3) Intel 页面“待复核事件”可见

- `frontend_bff` 与 `theme_service` 支持 `type=event_review`
- 前端筛选新增“待复核事件”
- 来源展示补齐 `event_review_queue`

### 4) 双源口径透传与状态诊断

- feed item 增加 `source_channel`：
  - `realtime_news` / `jyhf_manual`
- diagnostics 增加：
  - `source_channels`
  - `source_channel_counts`
- Intel 页头部摘要可直接看到“来源类型 + 来源通道”组合

### 5) 自动化回归（最小）

- 新增阶段性单测（phase0 behavior）：
  - 默认门禁会阻断 realtime 自动建题材
  - 被阻断后会触发复核入队
- 定向测试结果：`2 passed`

## 联调结果（2026-04-10）

### 已验证

- DDL 执行成功：`event_review_queue` 已创建
- `frontend_bff` 健康接口正常：`/health`
- `intel feed` 新类型可用：`type=event_review`
- `intel feed` 诊断字段可见：
  - `diagnostics.source_channels`
  - `diagnostics.source_channel_counts`

### 当前观察

- `event_review` 返回为空是正常现象：当前尚未有新进入复核队列的实时事件样本
- 当出现实时未匹配事件并被门禁拦截后，将在该视图中出现

## 关键产物清单

- `database_service/scripts/create_event_review_queue.sql`
- `database_service/streams/handlers/theme_processor.py`
- `database_service/streams/handlers/DecisionExecutor.py`
- `database_service/managers/postgres_manager.py`
- `database_service/gateway.py`
- `theme_service/repositories/phase1_read_repository.py`
- `frontend_bff/app.py`
- `frontend_bff/repositories/bff_repository.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/intel/IntelFilters.tsx`
- `frontend/src/lib/utils/format.ts`
- `docs/project_control/REALTIME_DUAL_SOURCE_ROLLOUT.md`

## 启动与验收建议

1. 启动链路服务（采集、存储、结构化、匹配、SSE）
2. 注入/等待一条实时未匹配新闻
3. 验收三项：
   - 不触发自动建题材
   - `event_review_queue` 有记录
   - Intel 页面 `type=event_review` 可见

## 风险与后续

1. 运行入口较多（脚本/服务管理器并存），建议收敛为单一生产启动入口
2. 建议补充端到端冒烟脚本（带超时与失败诊断）
3. 建议补充长期运行监控指标：
   - 采集延迟、结构化成功率、复核积压、SSE推送成功率

## 结论

阶段1目标已达成：全链路能力已具备，且满足“实时禁自动建题材、人工复核后入图谱”的约束。当前可进入下一阶段：生产化启动收敛与长时间稳定性运营。

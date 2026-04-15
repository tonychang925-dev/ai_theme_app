# 实时新闻双源驱动上线指引（阶段二）

## 1. 目标
- 打通链路：`news_raw -> news_event -> (人工复核) -> intel页面展示`
- 架构要求：
  - 双源驱动：实时新闻 + 久赢恒丰手动采集
  - 实时链路禁止自动创建新题材（默认）
  - 未匹配实时事件进入人工复核队列

## 2. 本次改造点
- realtime 自动建题材硬门禁：
  - `database_service/streams/handlers/theme_processor.py`
  - `database_service/streams/handlers/DecisionExecutor.py`
- 人工复核入库能力：
  - `database_service/managers/postgres_manager.py`
  - `database_service/gateway.py`
  - `database_service/scripts/create_event_review_queue.sql`
- Intel 页面待复核展示：
  - `theme_service/repositories/phase1_read_repository.py`
  - `frontend_bff/app.py`
  - `frontend/src/lib/api.ts`
  - `frontend/src/components/intel/IntelFilters.tsx`
  - `frontend/src/lib/utils/format.ts`
- 双源口径透传与指标：
  - `frontend_bff/repositories/bff_repository.py`（diagnostics 增加 `source_channels`、`source_channel_counts`）
  - `database_service/streams/handlers/DecisionExecutor.py`（门禁拦截/复核入队计数）

## 3. 上线步骤
1. 执行DDL
```bash
cd /Users/admin/Desktop/ai_theme_app
psql "$DATABASE_URL" -f database_service/scripts/create_event_review_queue.sql
```

2. 确认默认门禁（禁止实时自动建题材）
```bash
export ALLOW_REALTIME_AUTO_THEME_CREATE=false
```

3. 重启相关服务
```bash
# 按你的现有启动方式重启：
# - database_service stream consumers
# - frontend_bff
# - frontend
```

## 4. 验证清单
1. API可用性
```bash
curl "http://127.0.0.1:8003/api/intel/feed?type=event_review&session=all&limit=20"
```

2. 实时事件门禁校验
- 预期：实时 NO_MATCH 不会触发 `create_new_theme`
- 观察日志关键字：
  - `blocked_auto_theme_create_for_realtime`
  - `已写入人工复核队列`

3. 前端展示
- Intel 页面类型筛选中出现：`待复核事件`
- 能看到 `source_type=event_review_queue` 的记录
- Intel 页头部 source 摘要可看到 `... | realtime_news/jyhf_manual` 等 source_channel 信息

## 5. 回滚策略
1. 功能回滚（保留代码）
- 前端不展示待复核：不选 `event_review` 类型即可
- 关闭复核入库：临时不执行 DDL 或停止写入路径

2. 行为回滚（谨慎）
```bash
export ALLOW_REALTIME_AUTO_THEME_CREATE=true
```
- 该开关会恢复实时自动建题材能力，不建议在生产环境启用。

## 6. 说明
- 当前仓库改动较多，建议按文件白名单提交本次变更，避免把历史脏改动一并提交。

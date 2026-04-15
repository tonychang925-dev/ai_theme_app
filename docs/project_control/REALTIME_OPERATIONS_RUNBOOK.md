# 实时情报链路运行手册（SOP）

## 1. 适用范围

用于日常运行与值班排障，覆盖链路：

`AkShare采集 -> stream:news:raw -> 结构化/匹配 -> stream:event:feed -> SSE -> Intel页面`

## 2. 前置检查

```bash
cd /Users/admin/Desktop/ai_theme_app
```

1) 环境变量（生产建议）
```bash
export ALLOW_REALTIME_AUTO_THEME_CREATE=false
```

2) 数据库表是否存在
```bash
psql "$DATABASE_URL" -c "\dt+ event_review_queue"
```

若不存在：
```bash
psql "$DATABASE_URL" -f database_service/scripts/create_event_review_queue.sql
```

3) Redis可用
```bash
redis-cli ping
```

## 3. 启动顺序（建议）

### 一键启动（推荐）

```bash
cd /Users/admin/Desktop/ai_theme_app
./scripts/run_realtime_stack.sh
```

可选参数：
```bash
./scripts/run_realtime_stack.sh --with-frontend
./scripts/run_realtime_stack.sh --with-frontend --restart
```

说明：
- 默认启动 `start_services + frontend_bff:8003`
- `--with-frontend` 会额外拉起 `frontend npm run dev`
- `--restart` 会先停止同类进程再启动

### 一键停止（推荐）

```bash
cd /Users/admin/Desktop/ai_theme_app
./scripts/stop_realtime_stack.sh
```

可选参数：
```bash
./scripts/stop_realtime_stack.sh --with-frontend
./scripts/stop_realtime_stack.sh --with-frontend --force
```

### 一键状态检查（推荐）

```bash
cd /Users/admin/Desktop/ai_theme_app
./scripts/status_realtime_stack.sh
```

输出包含：
- 关键进程是否在运行
- BFF 健康与 feed 接口可用性
- 关键 Redis Stream 长度（`news:raw / events:structured / event:feed / events:pending`）

### Step A：启动全链路 Stream 服务

```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python -m database_service.streams.start_services
```

该服务会启动采集、匹配、SSE推送及相关处理链路。

### Step B：启动 Frontend BFF（Intel API + SSE入口）

```bash
cd /Users/admin/Desktop/ai_theme_app
.venv/bin/python -m uvicorn frontend_bff.app:app --host 0.0.0.0 --port 8003
```

### Step C：启动前端

```bash
cd /Users/admin/Desktop/ai_theme_app/frontend
npm run dev
```

## 4. 快速探活

1) BFF健康检查
```bash
curl -sS "http://127.0.0.1:8003/health"
```

2) Intel普通情报
```bash
curl -sS "http://127.0.0.1:8003/api/intel/feed?type=all&session=all&limit=5"
```

3) Intel待复核
```bash
curl -sS "http://127.0.0.1:8003/api/intel/feed?type=event_review&session=all&limit=20"
```

4) SSE实时端点（手工观察）
```bash
curl -N "http://127.0.0.1:8003/api/intel/stream/realtime?type=all&session=all&limit=20"
```

## 5. 链路验收（最小闭环）

验收目标：
1. 有新闻进入 `stream:news:raw`
2. 有事件进入 `stream:event:feed`
3. Intel页面可见新增情报
4. NO_MATCH 实时事件不自动建题材，进入复核

建议检查：
```bash
redis-cli xlen stream:news:raw
redis-cli xlen stream:events:structured
redis-cli xlen stream:event:feed
```

复核队列检查：
```bash
psql "$DATABASE_URL" -c "select review_status, count(*) from event_review_queue group by 1 order by 1;"
```

## 6. 常见问题与处理

### Q1：`type=event_review` 报参数不合法

现象：返回 `string_pattern_mismatch`。  
原因：`frontend_bff` 仍在跑旧代码。  
处理：重启 `frontend_bff`（8003）。

### Q2：SSE没输出但接口可用

排查：
1. `stream:event:feed` 是否有新消息
2. `database_service.streams.start_services` 是否在运行
3. `frontend_bff` 日志是否有 SSE 初始化错误

### Q3：长时间无待复核数据

可能原因：
1. 当前事件均已成功匹配
2. 门禁未触发（无 NO_MATCH）
3. 未生成实时新闻样本

检查：
```bash
printenv ALLOW_REALTIME_AUTO_THEME_CREATE
```

应为 `false`。

## 7. 回滚动作

1) 行为回滚（谨慎）
```bash
export ALLOW_REALTIME_AUTO_THEME_CREATE=true
```

2) 服务回滚
- 先停 `start_services`
- 回切到旧启动路径（如果你有固定旧脚本）

## 8. 值班建议

每30分钟记录一次：
1. `stream:event:feed` 增量
2. `event_review_queue` 积压
3. `/api/intel/feed` 响应时间与返回条数

若出现持续 15 分钟零增量，触发人工排查。

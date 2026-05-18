# Notion 盘后复盘发布系统 设计文档

> 版本: 1.0.0  
> 日期: 2026-05-18  
> 状态: 已交付（Phase 1：盘后复盘）

## 一、概述

将 SPS（Stock Processing Service）新链生成的盘后复盘 snapshot 结构化发布到 Notion database，支持幂等覆盖、前端一键触发。

### 设计目标

- **只读 snapshot**：Publisher 不重新生成报告，只消费已有 snapshot 数据
- **新链闭环**：所有代码在 `stock_processing_service/` 下，不依赖旧链 `stock_service`
- **富结构渲染**：Notion table、toggle、callout 等 block 类型，远超市面上简单 bullet 列
- **幂等发布**：`report_id` 机制保证同一交易日同一类型只有一页

## 二、架构

### 调用链

```
frontend RecapPage.tsx                    [发布按钮]
  ↓ POST /api/v2/recap/publish-notion
web_app_service/api/routes.py             [代理层]
  ↓ POST /api/v1/recap/publish-notion
stock_processing_service/api_app.py       [SPS API]
  ↓
NotionPostMarketRecapPublisher            [渲染 + 发布]
  ↓ Notion API (2022-06-28)
Notion reports database
```

### 放弃的链路

- `frontend_bff/app.py`：已废弃，不再作为主链路

### 新增文件

```
stock_processing_service/
└── publishers/
    ├── __init__.py
    ├── notion_publish_models.py            # NotionPublishResult 数据类
    ├── notion_block_builder.py             # 通用 Notion block 构建器
    └── notion_post_market_recap_publisher.py  # 盘后复盘发布器
```

### 修改文件

| 文件 | 改动内容 |
|------|----------|
| `stock_processing_service/api_app.py` | + `NotionPublishPayload` 模型 + `POST /api/v1/recap/publish-notion` 端点 |
| `web_app_service/api/routes.py` | + `POST /recap/publish-notion` 代理端点 |
| `frontend/src/lib/api.ts` | + `NotionPublishResult` 类型 + `publishRecapToNotion()` 函数 |
| `frontend/src/routes/recap/RecapPage.tsx` | + publish 状态管理 + "发布到 Notion"按钮 |
| `scripts/setup_notion_reports_database.py` | 新建：Notion reports 数据库初始化脚本 |

## 三、Notion 数据库设计

### 数据库初始化

```bash
python scripts/setup_notion_reports_database.py \
  --parent-page-id "<父页面ID或URL>" \
  --title "reports"
```

脚本自动创建数据库及以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 标题 | Title | `2026-05-15 盘后复盘` |
| 交易日期 | Date | Notion Calendar 视图用 |
| 报告类型 | Select | `post_market_recap` / `pre_market_brief` |
| report_id | Rich text | 幂等键：`post_market_recap:2026-05-15` |
| snapshot_version | Rich text | 快照版本号 |
| 摘要 | Rich text | 列表视图快速预览 |
| 状态 | Select | `已发布` / `草稿` / `失败` |

### API 版本

- 创建 database：Notion API `2022-06-28`（旧 database API）
- 读取/写入：通过 `notion_client` 库，Client 显式指定 `notion_version="2022-06-28"`
- 原因：新 API (`2025-09-03`) 的 `data_sources` 语义与旧 API 创建的不兼容；且 `notion_client` 2.7.0 无 `databases.query` 方法，改用 `client.request()` 直调

## 四、盘后复盘 Notion 页面结构

```
# 2026-05-15 盘后复盘

一、复盘概览
  📊 候选总数：15
  📊 正式候选：10
  📊 观察候选：5
  📊 强势池输入：25
  ───

二、弱转强候选 Top                          [table]
  股票 | 题材 | 候选分 | 候选等级 | 转换类型 | 证据摘要

三、正式候选                                [table]
  股票 | 题材 | 候选分 | 支撑类型

四、观察候选                                [table]
  股票 | 题材 | 候选分 | 支撑类型 | 支撑分 | 证据

五、强势股观察池历史                        [toggle + table]
  股票 | 题材 | 状态 | 等级 | watch_score | support_type

六、候选诊断                                [toggle + table]
  股票 | 题材 | candidate_score | support_type | support_score | rank

七、旧链文本报告（兼容）                    [toggle × N]
  每个 section 一个 toggle，内含摘要文本
  仅在 recap_doc["report"] 有数据时渲染
```

## 五、数据流

### 数据源

Publisher 从 `_normalize_recap_payload(row)` 获取数据，兼容两种存储形态：

1. **嵌套形态**：`payload = {"recap_doc": {"candidate_count": ..., "report": {...}}}`
2. **扁平新链形态**：`payload = {"candidate_count": ..., "report": {...}}`（topic candidates 等字段直接在 payload 顶层）

### 题材名解析

```
_resolve_theme_name(subject_key, subject_name, name_map)
  │
  ├── subject_name 非数字 → 直接返回
  ├── subject_key 在 name_map 中 → 返回映射名
  └── 否则 → 返回 subject_key（数字）
```

`name_map` 来源：
1. 旧链 `report.sections` 文本解析（格式 `题材名：subject_key 123；...`）
2. `top_candidates` / `observe_candidates` 中非数字 `subject_name`

已知限制：旧链 report 仅覆盖主线/强分支主题（约 8 个），非主线主题无法从 snapshot 中解析名称。后续可在 SPS Job 层写入 `subject_name` 字段彻底解决。

## 六、幂等策略

- `report_id = "post_market_recap:{trade_date}"`
- **默认**（`force=false`）：已有页面返回 `action: "exists"`，不做任何修改
- **强制覆盖**（`force=true`）：archive 旧页面 → 创建新页面 → 返回 `action: "recreated"`
- **dry_run**（`dry_run=true`）：只查询不写入，返回 `action: "dry_run:would_create"`

执行顺序保证：
```
1. _query_existing_page()
2. if dry_run → return（不执行任何写操作）
3. if force → archive + create
4. else if existing → return exists
5. else → create
```

## 七、Notion API 工程约束与应对

| 约束 | 位置 | 方案 |
|------|------|------|
| rich_text `text.content` ≤ 2000 字符 | `_truncate()` | 超长截断 |
| toggle children ≤ 100 blocks | `build_blocks()` | 旧链报告按 section 拆分成多个 toggle，每 toggle 内 ≤ 5 item |
| table_row 必须是 table.children | `table()` | 单次返回内含 children 的 table block |
| append children 100/批 | `chunk_blocks()` | 自动分批 |
| 单页 ≤ 1000 blocks / 500KB | `build_blocks()` | 限制行数（top 30, formal 20, observe 20, history 50） |

## 八、关键踩坑记录

| 问题 | 根因 | 解法 |
|------|------|------|
| `403 Method Not Allowed` | 代理写在废弃的 `frontend_bff` 而非 `web_app_service` | 迁移到 `web_app_service/api/routes.py` |
| `databases.query` 不存在 | `notion_client` 默认 `notion_version=2025-09-03` 无此方法 | `Client(notion_version="2022-06-28")` + `client.request()` |
| `data_sources.query` 404 | 新 API 找不到旧 API 创建的 database | 统一用 `2022-06-28` |
| `body.children[N].toggle.children.length > 100` | 旧链 report 单 toggle 塞入 151 blocks | 拆成多个 toggle，每个 ≤ 5 条 |
| 题材名显示数字 | snapshot 中 `report` 为空 `{}`，无法建立 name_map | 需重建 snapshot 使 report 数据完整 |
| dry_run 误 archive | archive 在 dry_run 判断之前执行 | 调整顺序：先判 dry_run 再写操作 |
| table block 无效 | table_rows 作为同级 block append 而非 children | `table.children = [table_rows...]` |

## 九、验证

```bash
# dry_run（不写入）
curl -X POST http://127.0.0.1:8000/api/v2/recap/publish-notion \
  -H "Content-Type: application/json" \
  -d '{"trade_date": "2026-05-15", "dry_run": true}'

# 正式发布（幂等）
curl -X POST http://127.0.0.1:8000/api/v2/recap/publish-notion \
  -H "Content-Type: application/json" \
  -d '{"trade_date": "2026-05-15"}'

# 强制覆盖
curl -X POST http://127.0.0.1:8000/api/v2/recap/publish-notion \
  -H "Content-Type: application/json" \
  -d '{"trade_date": "2026-05-15", "force": true}'
```

## 十、后续规划

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | 盘前必读 Notion 发布 | 复用 `NotionBlockBuilder`，新建 `NotionPreMarketBriefPublisher` |
| P2 | SPS recap_doc 写入 `subject_name` | 消除题材名数字兜底，彻底解决映射问题 |
| P2 | 解耦旧链 RecapService | `BuildPostMarketRecapJob` 不再依赖 `stock_service.recap_service` |
| P3 | 发布日志表 `notion_publish_log` | 记录 page_id / page_url / payload_hash / published_at |
| P3 | 前端盘前必读页加发布按钮 | 复用 `api.ts` 的 `publishRecapToNotion` 模式 |

# 盘后复盘模块 DailyReview 重构验收记录

> **阶段一完成** · 2026-05-23
> Commit: `f8503d0b4` · 分支: `codex/bugfix/phase6a-intel-producer`
> 验收: 6/6 smoke tests passed
> 下一阶段: DailyReview 内容质量增强（Phase 2）

## 架构变更

```
旧：前端解析 report sections 中文文本 → 易断裂、字段名不一致
新：后端生成结构化 theme_reviews[] → 前端 DailyReviewTable 直接渲染
```

## 数据流

```
BuildPostMarketRecapJob
  ↓ _build_theme_context_map() → cycles + capital_flow → 主题宇宙（≤20）
  ↓ _build_theme_reviews() → 结构化数组 + 排序 + _to_bool
  ↓ recap_doc["theme_reviews"] + diagnostics.coverage
  ↓ post_market_recap_snapshot

GET /api/v1/daily_review → 从 snapshot 派生
  ↓ web_app /api/v2/daily-review → 代理
  ↓ frontend DailyReviewTable → 优先渲染，旧 sections 为 fallback
```

## API 端点

| 端点 | 用途 |
|------|------|
| `GET /api/v1/theme_workspace/{sk}` | 题材工作台（v2，含 analytics.summary + leader_stocks） |
| `GET /api/v1/theme/workspace/{sk}` | 同上 alias（兼容旧调用） |
| `GET /api/v2/theme_workspace/{sk}` | web_app 代理 → SPS |
| `GET /api/v1/daily_review?trade_date=` | 结构化每日复盘（从 snapshot 派生） |
| `GET /api/v2/daily-review?date=` | web_app 代理 → SPS |
| `GET /api/v2/stock_workspace/{id}` | 股票工作台代理 |

## 验收命令与结果

### 1. SPS 双路径

```bash
curl -s "http://127.0.0.1:8090/api/v1/theme_workspace/9019807" | jq '.subject_key,.diagnostics'
# "9019807"
# {"partial": false, "missing_sections": []}

curl -s "http://127.0.0.1:8090/api/v1/theme/workspace/9019807" | jq '.subject_key,.diagnostics'
# "9019807"
# {"partial": false, "missing_sections": [], "source": "sps"}
```

### 2. DailyReview 结构化输出

```bash
curl -s "http://127.0.0.1:8000/api/v2/daily-review?date=2026-05-22" \
  | jq '.theme_reviews | length, .diagnostics.coverage'
# 8
# {"theme_count":8, "snapshot_status":"complete", "cycle_joined_count":8, "missing_cycle_subject_keys":[]}
```

### 3. theme_reviews[0] 字段完整性

```json
{
  "subject_key": "9011398",
  "theme_name": "半导体设备",
  "theme_stage": "divergence",
  "theme_strength": "WEAK",
  "mainline_strength_score": 19.40,
  "fade_risk_score": 28.00,
  "final_cycle_state": "divergence",
  "final_mainline_alive": true,
  "capital_validation": "NEUTRAL",
  "leader_stocks": [...5 stocks...],
  "event_chain": [],
  "action_advice": "",
  "conclusion": "",
  "diagnostics": {
    "cycle_joined": true,
    "capital_joined": false,
    "leader_count": 5
  }
}
```

### 4. 前端编译

```bash
cd frontend && npm run build  # TypeScript 零错误
```

## 关键设计决策

| 决策 | 原因 |
|------|------|
| theme_reviews 上限 20 | 主题宇宙只从 cycles + capital_flow 确定，stock_facts 不扩张 |
| `_to_bool()` 安全转换 | 防御数据库返回 "false"/"False"/"0" 等字符串 |
| 排序：有 cycle 优先 | 确保有分数字段的题材排在最前面 |
| SQL raw_json cast 加正则 guard | 防止 "--" / "null" / "无" 导致 cast 异常 |
| RecapPage 旧 sections 保留为 fallback | 不破坏现有功能，dailyReview 不可用时回退 |
| setDailyReview(null) 在切换日期时 | 防止旧日期数据残留 |

## 第二阶段待增强

- [ ] `action_advice` 自动生成（如 "可做弱转强"）
- [ ] `conclusion` 自动生成
- [ ] `capital_validation` 从 NEUTRAL 升级为真实资金确认
- [ ] `event_chain` 填充真实驱动事件
- [ ] `leader_stocks` 加入龙头/龙二/补涨角色

## 回滚方式

如需回退到旧 sections 解析模式：
- 前端 `RecapPage.tsx` 中 `dailyReview?.theme_reviews?.length` 返回 falsy 时自动 fallback
- 后端恢复生成不依赖 `_build_theme_reviews()` 即可

---

## 第二阶段：DailyReview 内容质量增强

> 状态：待开工

| # | 任务 | 说明 |
|---|------|------|
| 1 | `action_advice` 升级 | 从空字符串升级为策略建议（如 "可做弱转强"） |
| 2 | `conclusion` 升级 | 从空字符串升级为复盘结论 |
| 3 | `capital_validation` 升级 | 从 `NEUTRAL` 升级为真实资金确认 (CONFIRM/NEUTRAL/DENY) |
| 4 | `event_chain` 填充 | 填入真实驱动事件，替代空数组 |
| 5 | `leader_stocks` 角色化 | 增加龙头/龙二/补涨/套利角色标签 |
| 6 | Notion 发布改造 | 改用结构化 DailyReview 渲染，替代文本 section 拼接
- 后端恢复生成不依赖 `_build_theme_reviews()` 即可

---

## 第三阶段：三层边界恢复与合约冻结（2026-05-25）

> 状态：已完成
> 背景：发现 UI 按钮误触发了全量 Truth Source 生产（660 theme evidence → cycle → identity → mainline → Layer C），导致复盘报告生成耗时 10 分钟 + SPS 阻塞。

### 根因

```
UI "重新生成复盘报告" 按钮
  → 误触发 collection/start
    → kline_judgements (1842 stocks)
    → prereqs (660 evidence → cycle → identity → mainline)  ← 5m43s
    → Layer C (strong_stock_tracking)                           ← 3min
    → DailyReview generation
```

设计文档第三阶段明确定义：**报告与页面读快照，不直接依赖外部源或生产层**。

### 架构修正：三层隔离

```
┌─────────────────────────────────────────────┐
│ Producer Layer (Truth Source)               │
│   evidence / cycle / identity / mainline     │
│   kline_judgements / Layer C                │
│   执行: 后台定时 / force rebuild             │
│   禁止: UI 按钮默认触发                      │
└─────────────────────────────────────────────┘
              ↓ 写入对象表
┌─────────────────────────────────────────────┐
│ Report Layer (Serving Read Model)           │
│   BuildPostMarketRecapJob (read_model_only) │
│   读取已有对象 → DailyReview → snapshot      │
│   执行: UI 按钮默认触发                      │
│   耗时: 10-30 秒                            │
│   禁止: 触发 Producer Layer 任何 Job         │
└─────────────────────────────────────────────┘
              ↓ 写入 post_market_recap_snapshot
┌─────────────────────────────────────────────┐
│ Frontend Layer                              │
│   GET /api/v2/daily-review → DailyReview    │
│   禁止: 直连 SPS / sections 解析主表         │
└─────────────────────────────────────────────┘
```

### 新增 API

| 方法 | 端点 | 用途 |
|------|------|------|
| `POST` | `/api/v1/daily_review/generate` | SPS: 生成 DailyReview 快照 |
| `POST` | `/api/v2/daily-review/generate` | web_app 代理 |

**请求体**:

```json
{
  "date": "2026-05-25",
  "mode": "read_model_only"
}
```

- `read_model_only` (默认): 只读已有对象，10-30 秒
- `full_truth_rebuild`: 重跑 evidence/cycle/identity/mainline/LayerC，5-10 分钟（危险，仅管理端）

### 关键代码修改

| 文件 | 修改 |
|------|------|
| `collection_orchestrator.py` | `recap_snapshot` 默认跳过 kline/prereqs/abnormal，仅 `force_rebuild_truth_source=true` 时执行 |
| `build_post_market_recap_job.py` | 新增 `skip_prereqs` / `skip_layer_c` 参数；新增 `_build_capital_reviews()` |
| `collection_task_runners.py` | `PostMarketRecapRunner` 读取 `force_rebuild_truth_source` 控制跳过行为 |
| `api_app.py` | 新增 `POST /api/v1/daily_review/generate` |
| `routes.py` | web_app 代理 `POST /api/v2/daily-review/generate` |
| `build_stock_kline_judgements.py` | 新增 `--universe` 参数，默认 `seed_candidates+strong_watch`，5133→1842 |

### 冻结合约（强制）

以下规则从 2026-05-25 起冻结，所有后续代码必须遵守：

**DailyReview generate 禁止调用的 Job**:
1. `BuildThemeCycleEvidenceDailyJob`
2. `BuildCycleJudgementJob`
3. `BuildIdentityJob`
4. `BuildMainlineStateJob`
5. `BuildStrongStockTrackingUseCase.execute()`
6. `build_stock_kline_judgements.py`
7. `BuildStockAbnormalSignalJob`

**普通按钮禁止触发的行为**:
- collection 全量管线（kline + prereqs + abnormal + Layer C）
- 必须通过 `force_rebuild_truth_source=true` 显式触发

**前端禁止**:
- 主表依赖 sections 文本解析
- 渲染依赖 payload 而非 dailyReview

### 验收

```bash
# 快速生成（必须 <= 30s，日志不得出现 evidence/cycle/identity/mainline）
time curl -s -X POST "http://127.0.0.1:8000/api/v2/daily-review/generate" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-05-25","mode":"read_model_only"}'

# 读取 DailyReview
curl -s "http://127.0.0.1:8000/api/v2/daily-review?date=2026-05-25" \
  | jq '.theme_reviews | length, .capital_reviews | length'
```

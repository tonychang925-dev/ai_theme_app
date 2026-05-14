# iOS HTML5 移动端投资驾驶舱架构设计草案

> 状态：Draft v1.0  
> 目标平台：iPhone Safari / iOS HTML5  
> 适用仓库：`ai_theme_app`  
> 设计原则：电脑端负责计算，手机端负责展示和触发。

---

## 1. 背景与目标

现有系统已经具备电脑端本地 AI 投资分析能力，包括：

- 本地股票知识库与题材库。
- 每日复盘与盘前/盘后报告能力。
- AI 选股与弱转强候选分析能力。
- 实时情报流与 SSE 推送能力。
- JYHF-CDP 服务，可从久赢恒丰本地 App DOM 中采集实时事件，并可选推送到 Redis `stream:event:feed`。

本方案目标是在不重做原生 iOS App 的前提下，新增一个适配 iPhone 的 HTML5 移动端入口，让用户可以通过手机远程查看和触发电脑端 AI 投资系统能力。

移动端只作为：

```text
移动展示层 + 轻量操作入口
```

电脑端继续负责：

```text
每日复盘生成
AI 选股
新闻事件理解
本地股票知识库查询
JYHF-CDP 实时事件采集
Redis / PostgreSQL / SSE 情报链路
```

---

## 2. 非目标

第一阶段不做以下内容：

- 不开发原生 iOS App。
- 不接入 App Store。
- 不让手机直接访问 PostgreSQL、Redis、CDP 9223 或 JYHF App DevTools。
- 不在手机端执行 AI 模型或本地知识库计算。
- 不在手机端直接操作久赢恒丰 DOM。
- 不自动创建正式新题材。
- 不输出买卖指令，仅输出研究分析结果。

---

## 3. 总体架构

```text
iPhone Safari / HTML5
        ↓
Tailscale Serve / Cloudflare Tunnel
        ↓
web_app_service / frontend_bff
        ↓
现有新链服务
        ├── PostgreSQL 本地股票知识库
        ├── Redis stream:event:feed
        ├── JYHF-CDP service
        ├── AI 题材匹配 / 选股服务
        ├── 每日复盘快照
        └── SSE 情报推送
```

推荐第一阶段使用：

```text
Tailscale Serve
```

用于 iPhone 在移动网络下通过私有 tailnet 访问电脑端本地服务。

后续如需品牌域名和公网入口，可切换为：

```text
Cloudflare Tunnel + 自有域名 + Cloudflare Access
```

---

## 4. 移动端路由规划

统一移动端入口：

```text
/mobile
```

建议路由：

```text
/mobile
/mobile/recap
/mobile/screener
/mobile/news-recommend
/mobile/intel
/mobile/watch
```

第一阶段优先实现：

```text
/mobile
/mobile/recap
/mobile/screener
/mobile/news-recommend
```

第二阶段再实现：

```text
/mobile/intel
/mobile/watch
```

---

## 5. 前端目录设计

新增目录：

```text
frontend/src/routes/mobile/
  MobileHomePage.tsx
  MobileRecapPage.tsx
  MobileScreenerPage.tsx
  MobileNewsRecommendPage.tsx
  MobileIntelPage.tsx
  mobile.css
```

建议新增移动端 API 封装：

```text
frontend/src/lib/mobileApi.ts
```

若第一阶段希望降低改造面，也可以先追加到：

```text
frontend/src/lib/api.ts
```

但长期推荐独立 `mobileApi.ts`，避免移动端接口和桌面端接口混杂。

---

## 6. 页面设计

### 6.1 `/mobile` 首页

移动端首页采用卡片式入口。

入口模块：

```text
今日复盘
AI选股
新闻荐股
实时情报
采集状态
```

UI 原则：

```text
iPhone 竖屏优先
少表格，多卡片
按钮大，文字清晰
默认显示最新交易日
支持返回首页
深色科技风，与现有情报台风格协调
```

---

### 6.2 `/mobile/recap` 每日复盘页

展示内容：

```text
日期选择
复盘标题
市场摘要
核心题材
重点股票
弱转强观察
风险提示
明日关注方向
```

建议接口：

```http
GET /api/v2/mobile/recap?date=YYYY-MM-DD
```

返回结构草案：

```json
{
  "trade_date": "2026-05-10",
  "title": "盘后复盘",
  "summary": "今日市场主线集中在商业航天、AI应用方向。",
  "hot_themes": [
    {
      "subject_key": "9019807",
      "theme_name": "卫星互联网",
      "heat": 85,
      "reason": "政策催化 + 事件驱动",
      "stocks": ["神剑股份", "航天晨光"]
    }
  ],
  "watch_stocks": [
    {
      "stock_id": "002361.SZ",
      "stock_name": "神剑股份",
      "theme_name": "商业航天",
      "score": 82.5,
      "reason": "主线强势股回踩关键支撑"
    }
  ],
  "risk_notes": [
    "仅作复盘与研究，不构成交易建议"
  ]
}
```

---

### 6.3 `/mobile/screener` AI 选股页

第一阶段只读取已有结果，不在手机端执行完整选股。

建议接口：

```http
GET /api/v2/mobile/screener/latest?date=YYYY-MM-DD&strategy=weak_to_strong
```

返回结构草案：

```json
{
  "trade_date": "2026-05-10",
  "strategy": "weak_to_strong",
  "count": 10,
  "items": [
    {
      "stock_id": "002361.SZ",
      "stock_name": "神剑股份",
      "score": 82.5,
      "rank": 1,
      "theme_name": "商业航天",
      "candidate_level": "A",
      "reason": "商业航天主线强势，回踩缺口支撑，具备弱转强观察价值",
      "risk": "若跌破支撑位则失效"
    }
  ]
}
```

移动端展示为股票卡片：

```text
神剑股份 002361.SZ
评分：82.5
题材：商业航天
级别：A
理由：主线强势 + 回踩支撑
风险：跌破支撑失效
```

---

### 6.4 `/mobile/news-recommend` 新闻荐股页

用户粘贴新闻文本，调用电脑端 AI 推荐服务。

接口：

```http
POST /api/v2/mobile/news-recommend
```

请求：

```json
{
  "news_text": "工信部表示将加快推进卫星互联网规模化应用……",
  "top_n": 10
}
```

返回结构草案：

```json
{
  "event_summary": "卫星互联网政策催化",
  "matched_themes": [
    {
      "subject_key": "9019807",
      "theme_name": "卫星互联网",
      "confidence": 0.86,
      "reason": "新闻涉及卫星互联网规模化应用、政策推动、产业链扩容"
    }
  ],
  "recommended_stocks": [
    {
      "stock_id": "002361.SZ",
      "stock_name": "神剑股份",
      "score": 82.5,
      "theme_name": "商业航天",
      "reason": "题材关联度高，近期进入强势股观察池"
    }
  ],
  "risk_notes": [
    "仅用于研究分析，不构成买卖建议"
  ]
}
```

要求：

```text
不自动创建正式新题材
低置信度标记 review_required
不输出买卖指令
```

---

### 6.5 `/mobile/intel` 实时情报页（第二阶段）

数据来源：

```text
/api/v2/intel/feed
/api/v2/intel/stream
```

第一版可先使用轮询，不强制 SSE。

展示字段：

```text
时间
事件标题
摘要
来源：jyhf_cdp / realtime_news / event_review_queue
关联题材
关联股票
```

JYHF-CDP 服务已经支持通过开关推送到 Redis `stream:event:feed`：

```bash
JYHF_CDP_PUSH_INTEL=1 ./scripts/start_jyhf_cdp_service.sh
```

默认仍保持关闭：

```bash
JYHF_CDP_PUSH_INTEL=0
```

---

## 7. 后端 Mobile API 设计

建议新增：

```text
frontend_bff/mobile_routes.py
```

或第一阶段先在现有 BFF / web_app_service 中添加 `/api/v2/mobile/*`。

接口清单：

```text
GET  /api/v2/mobile/health
GET  /api/v2/mobile/recap
GET  /api/v2/mobile/screener/latest
POST /api/v2/mobile/news-recommend
GET  /api/v2/mobile/intel/latest
```

第一阶段优先实现：

```text
GET  /api/v2/mobile/recap
GET  /api/v2/mobile/screener/latest
POST /api/v2/mobile/news-recommend
```

---

## 8. 数据来源映射

### 8.1 每日复盘

优先复用：

```text
post_market_snapshot
recap_v2_snapshot
recap_v2_report
```

移动端 API 只做轻量转换，不重新生成复盘。

### 8.2 AI 选股

第一阶段读取已有结果：

```text
weak_to_strong_candidates
strong_watch_pool
screening_results
post_market_snapshot 中的 top_candidates
```

移动端只需要 TopN，不需要完整桌面端配置项。

### 8.3 新闻荐股

第一阶段建议走简化管线：

```text
news_text
  ↓
事件理解
  ↓
题材匹配
  ↓
本地题材-股票映射 / JYHF 股票池 / 强势股池 / 弱转强候选池
  ↓
TopN 推荐股票
```

---

## 9. 安全设计

### 9.1 远程访问边界

第一阶段推荐：

```text
Tailscale Serve
```

电脑端服务优先只监听：

```text
127.0.0.1
```

禁止暴露：

```text
9223 CDP 端口
PostgreSQL
Redis
JYHF Electron App DevTools
```

手机只允许访问：

```text
/mobile
/api/v2/mobile/*
```

### 9.2 应用层访问密钥

即使使用 Tailscale，也建议增加移动端访问密钥：

```text
MOBILE_ACCESS_TOKEN
```

请求头：

```http
X-Mobile-Access-Token: xxxxx
```

校验规则：

```text
如果环境变量 MOBILE_ACCESS_TOKEN 存在，则必须匹配。
如果未设置，则本地开发模式允许访问。
```

---

## 10. 远程访问方案

### MVP 推荐

```text
Tailscale Serve
```

示例：

```bash
./scripts/start_new_chain_stack.sh --with-frontend
tailscale serve 8000
```

### 品牌化后续方案

如果需要自有域名：

```text
https://ai.yourdomain.com/mobile
```

建议使用：

```text
Cloudflare Tunnel + 自有域名 + Cloudflare Access
```

不建议直接将自有域名 CNAME 到 `*.ts.net`。

---

## 11. Codex 实施阶段规划

### Phase 1：移动端页面骨架

目标：

```text
新增 /mobile 首页
新增 mobile.css
新增移动端路由懒加载
```

交付：

```text
/mobile 可打开
页面适配 iPhone 竖屏
包含 4 个入口卡片
不影响桌面端页面
npm run build 通过
```

### Phase 2：每日复盘移动页

目标：

```text
/mobile/recap 展示最新复盘
```

交付：

```text
MobileRecapPage.tsx
GET /api/v2/mobile/recap
复用已有 recap/post_market_snapshot 数据
无数据时有友好空状态
```

### Phase 3：AI 选股移动页

目标：

```text
/mobile/screener 展示 AI 选股 TopN
```

交付：

```text
MobileScreenerPage.tsx
GET /api/v2/mobile/screener/latest
卡片式展示股票
支持日期选择
支持查看理由
```

### Phase 4：新闻荐股移动页

目标：

```text
/mobile/news-recommend 支持粘贴新闻并返回推荐股票
```

交付：

```text
MobileNewsRecommendPage.tsx
POST /api/v2/mobile/news-recommend
后端先实现简化推荐逻辑
保留 review_required
不自动建题材
```

### Phase 5：安全与远程访问文档

目标：

```text
增加 Tailscale Serve 使用说明
增加移动端访问 token
增加部署文档
```

交付：

```text
docs/mobile/MOBILE_GATEWAY.md
MOBILE_ACCESS_TOKEN 校验
Tailscale Serve 启动说明
iPhone 添加到主屏幕说明
```

---

## 12. Codex Phase 1 任务 Prompt

```text
请在当前仓库 ai_theme_app 中实现 iOS HTML5 移动端投资驾驶舱 Phase 1。

目标：
1. 新增 /mobile 移动端首页。
2. 页面用于 iPhone Safari 访问，采用卡片式布局。
3. 首页包含四个入口：
   - 今日复盘：/mobile/recap
   - AI选股：/mobile/screener
   - 新闻荐股：/mobile/news-recommend
   - 实时情报：/mobile/intel
4. 不实现具体业务数据，只实现页面骨架与路由。
5. 不影响现有桌面端 /、/recap、/screener、/realtime-collector 等页面。
6. 复用现有 React + Vite 架构，不引入大型 UI 框架。
7. 新增移动端 CSS，要求适配 iPhone 竖屏，深色科技风，卡片式布局。
8. 修改 App.tsx 和 codeSplitting.tsx，按现有懒加载方式接入移动端页面。
9. npm run build 必须通过。

建议文件：
- frontend/src/routes/mobile/MobileHomePage.tsx
- frontend/src/routes/mobile/mobile.css
- frontend/src/utils/codeSplitting.tsx
- frontend/src/App.tsx

完成后请给出：
1. 修改文件清单
2. 构建结果
3. 如何访问 /mobile
4. 后续 Phase 2 建议
```

---

## 13. 验收标准

### Phase 1

```text
npm run build 通过
/mobile 可访问
iPhone 宽度下布局正常
四个入口卡片可点击
桌面端现有页面不受影响
```

### Phase 2

```text
/mobile/recap 可显示最新复盘
无数据时有空状态
日期切换可用
```

### Phase 3

```text
/mobile/screener 可显示 TopN 选股结果
每只股票卡片含评分、题材、理由、风险
```

### Phase 4

```text
/mobile/news-recommend 可提交新闻文本
后端返回匹配题材与推荐股票
低置信度标记 review_required
```

---

## 14. 决策结论

本方案建议采用：

```text
HTML5 移动网页
+
电脑端 web_app_service API
+
Tailscale Serve 远程访问
```

第一步只实现 `/mobile` 页面骨架，不引入原生 App、不引入复杂 PWA、不直接接触 CDP/数据库/Redis。

最终目标：

```text
iPhone 打开 /mobile
↓
看每日复盘
↓
看 AI选股 Top10
↓
粘贴新闻触发荐股
↓
电脑端调用本地股票知识库和 AI 程序
↓
手机展示结果
```

核心原则：

```text
电脑端负责算，iPhone HTML5 负责看和触发。
```

---

## 15. 用户管理模块 (Phase 6)

> 状态：实施中  
> 目标：邮箱登录 + 角色权限，替代 Tailscale 实现远程访问

### 15.1 架构

```
浏览器/iPhone
  ↓ HTTPS（ngrok / Cloudflare Tunnel）
web_app_service:8000
  ↓ JWT 中间件
  ├── /api/v2/auth/*    公开（login / register）
  └── /api/v2/*          受保护（需 Bearer JWT）
```

### 15.2 技术选型

| 组件 | 选型 |
|---|---|
| 认证协议 | JWT (access token, 72h 过期) |
| 密码哈希 | bcrypt (passlib) |
| 用户存储 | PostgreSQL `user_accounts` 表 |
| 公网访问 | ngrok（免费）或 Cloudflare Tunnel（需域名） |
| 前端状态 | React Context + localStorage |

### 15.3 数据模型

```sql
CREATE TABLE user_accounts (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20) NOT NULL DEFAULT 'user',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);
```

### 15.4 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/v2/auth/register` | 公开 | 首用户自动 admin |
| POST | `/api/v2/auth/login` | 公开 | 返回 JWT |
| GET | `/api/v2/auth/me` | 需登录 | 当前用户信息 |

### 15.5 前端页面

| 路由 | 组件 | 说明 |
|---|---|---|
| `/login` | LoginPage.tsx | 邮箱+密码登录 |
| `/register` | RegisterPage.tsx | 注册 |
| AuthContext | AuthProvider.tsx | 全局认证状态，路由守卫 |

### 15.6 角色权限

| 功能 | user | admin |
|---|---|---|
| 查看复盘/选股/情报 | ✅ | ✅ |
| 新闻荐股 | ✅ | ✅ |
| CDP 实时采集 | ✅ | ✅ |
| 日采集启动 | ❌ | ✅ |
| 用户管理 | ❌ | ✅ |

### 15.7 远程访问

| 方案 | 域名格式 | 费用 |
|---|---|---|
| **ngrok** | `https://xxx.ngrok-free.app` | 免费 |
| Cloudflare Tunnel | 需自有域名 | 免费 |
| Tailscale Funnel | `xxx.ts.net` | 免费 |

---

## 16. 运维操作指南

### 16.1 启动服务

```bash
# 1. 启动新链服务栈（SPS + web_app + Vite）
./scripts/start_new_chain_stack.sh --restart --with-frontend

# 2. 启动 CDP 实时采集（可选）
JYHF_CDP_PUSH_INTEL=1 JYHF_CDP_PUSH_DB=1 \
  nohup /opt/miniconda3/envs/theme_matcher_env/bin/python \
  -m uvicorn services.jyhf_cdp_service.app:app \
  --host 127.0.0.1 --port 8095 > /tmp/cdp.log 2>&1 &

# 3. 启动远程隧道
nohup cloudflared tunnel --url http://localhost:8000 > /tmp/cf_stable.log 2>&1 &
```

### 16.2 获取/更新隧道 URL

```bash
# 查看当前隧道域名
grep -o 'https://[^ ]*trycloudflare\.com' /tmp/cf_stable.log | tail -1

# 如果隧道断开，重新启动（域名会变）
pkill -f cloudflared
nohup cloudflared tunnel --url http://localhost:8000 > /tmp/cf_stable.log 2>&1 &
sleep 8
grep -o 'https://[^ ]*trycloudflare\.com' /tmp/cf_stable.log | tail -1
```

### 16.3 查看服务状态

```bash
# 检查各服务健康
curl -s http://127.0.0.1:8000/healthz    # web_app
curl -s http://127.0.0.1:8090/healthz    # SPS
curl -s http://127.0.0.1:8095/status     # CDP
```

### 16.4 重启单个服务

```bash
# 重启 SPS（改代码后）
pkill -f "api_app:app"
HF_HUB_OFFLINE=1 DEEPSEEK_API_KEY="sk-xxx" \
  PYTHONPATH="/Users/admin/Desktop/ai_theme_app" \
  nohup /opt/miniconda3/envs/theme_matcher_env/bin/python \
  -m uvicorn stock_processing_service.api_app:app \
  --host 127.0.0.1 --port 8090 > /tmp/sps.log 2>&1 &

# 重启 web_app（改前端构建后）
npx vite build
pkill -f "uvicorn web_app_service.main"
PYTHONPATH="/Users/admin/Desktop/ai_theme_app" \
  nohup /opt/miniconda3/envs/theme_matcher_env/bin/python \
  -m uvicorn web_app_service.main:app \
  --host 0.0.0.0 --port 8000 > /tmp/webapp.log 2>&1 &
```

### 16.5 日采集操作

```
1. 打开 http://localhost:5173/collection
2. 确认 JYHF CDP 服务已启动（实时事件采集）
3. 勾选需要执行的任务（默认全部）
4. 点击「启动采集」
5. 完成后查看 http://localhost:5173/recap 复盘报告
```

### 16.6 用户管理

```
默认管理员: admin@test.com / 123456

操作路径:
1. 登录后访问 /admin（仅 admin 可见）
2. 添加用户（邮箱 + 密码 + 角色）
3. 用户登录后访问 /mobile/profile 自行修改密码
```

### 16.7 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 隧道域名每次变 | cloudflared 进程被关 | 用 `nohup` 后台运行，不关终端 |
| 移动端页面空白 | Vite 缓存旧代码 | `rm -rf frontend/dist && npx vite build` |
| AI 荐股结果差 | SPS 用了 .venv（无 torch） | SPS 必须用 `theme_matcher_env` |
| 情报台无实时事件 | CDP 服务未启动 | 执行 16.1 步骤 2 |
| 登录后卡验证身份 | /me API 超时 | 已加 8s 超时，刷新页面 |

# 项目需求文档（PRD）

- 项目：个人投资助理（AI Theme App）
- 文档版本：v1.0
- 状态：Draft for Review
- 编写日期：2026-02-13
- 依据文档：
  - `docs/architecture/overview.md  `
  - `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`
  - `docs/architecture/个人投资助理-项目架构设计-第二阶段.md`
  - `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
  - `docs/architecture/个人投资助理项目-前端技术设计（第四阶段）.md`
  - `docs/project_control/PLAN_WBS.md`

## 全局范围与约束

- 范围：覆盖四阶段能力闭环（题材发现 → 题材演化 → 股票融合与实时产品化 → 前端投研工作台）。
- 非范围：本 PRD 不包含具体代码实现方案与数据库迁移脚本细节。
- 全局约束：
  - 所有关键决策链路必须可追踪（`trace_id`/`decision_hash`/审计日志）。
  - 跨系统输出必须契约化并支持向后兼容（字段可增不可改语义）。
  - 阶段性发布必须经过质量门禁（测试、回放、一致性、性能指标）。
- 风险等级：整体 `High`（涉及 AI 判定、流式系统、实时行情、多端协同）。

---

## 阶段 M1 — 基础认知流水线（第一阶段基线能力）

### 1. 目标（可衡量）
在不重构现有主链路前提下，建立稳定的“新闻 → 结构化事件 → 题材映射”生产链路，并满足：快速分类路径单条处理目标 <200ms、建立 76 案例测试基线、支持 major/normal/pending/decision/updates 流程闭环。

### 2. 需求（清单）
- [ ] `PRD-M1-R01` 系统必须将原始新闻写入 `news_raw`，并产出结构化 `news_event`（至少含 `event_type`、`summary`、`impact_industries`、`direction`、`confidence`）。
- [ ] `PRD-M1-R02` Model 服务必须支持“双级处理”：普通事件快速分类、重大事件深度分析；快速分类路径目标处理时延 <200ms。
- [ ] `PRD-M1-R03` Theme 服务必须消费 `stream:events:major` 与 `stream:events:normal`，并写出统一决策流 `stream:events:decision`。
- [ ] `PRD-M1-R04` normal 事件未匹配时必须进入 `stream:events:pending`，并由聚类监听流程处理。
- [ ] `PRD-M1-R05` major 事件未匹配时必须立即触发新题材创建（不得直接丢弃）。
- [ ] `PRD-M1-R06` 题材更新必须发布到 `stream:themes:updates`，并写入 `event_theme_map` 关系数据。
- [ ] `PRD-M1-R07` 新题材创建必须执行唯一性校验（分类编码+名称不可重复）。
- [ ] `PRD-M1-R08` 必须保留 76 案例评估集，并在既有 `test_theme_processor.py` 框架下可复现验证。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M1-UC01（普通事件匹配成功）
**Given**：`stream:events:normal` 收到结构化事件，题材库存在可匹配题材。  
**When**：ThemeProcessor 执行匹配流程。  
**Then**：生成 `update_theme` 决策，DecisionExecutor 更新题材并发布 `stream:themes:updates`，原消息 ACK。

#### 用例 ID: PRD-M1-UC02（普通事件未匹配进入聚类）
**Given**：`stream:events:normal` 收到事件且匹配失败。  
**When**：ThemeProcessor 完成决策类型判断。  
**Then**：事件写入 `stream:events:pending`，后续由 ClusteringListener 拉取处理。

#### 用例 ID: PRD-M1-UC03（重大事件立即建题材）
**Given**：`stream:events:major` 收到重大事件且无匹配题材。  
**When**：ThemeProcessor 走 major 未匹配分支。  
**Then**：生成 `create_new_theme` 决策并执行，产出新题材记录与事件映射。

#### 用例 ID: PRD-M1-UC04（新题材命名冲突拦截）
**Given**：创建新题材请求与现有分类编码/名称冲突。  
**When**：执行新题材创建前校验。  
**Then**：拒绝创建，记录错误原因并进入可追踪日志。

### 4. 验收标准（测试用例）
- Given 有效新闻输入，When 完成主流程，Then `news_event` 与 `event_theme_map` 必须落库成功。
- Given 普通事件输入，When 走快速分类，Then 单条处理耗时统计 P95 不高于 200ms。
- Given normal 未匹配事件，When 处理完成，Then 事件必须存在于 `stream:events:pending`。
- Given major 未匹配事件，When 处理完成，Then 必须创建新题材且有对应映射记录。
- Given 运行 76 案例评估，When 输出报告，Then 报告包含题材数量、聚类精度、归集完整性、主题分离度四项。

### 5. 非目标（排除项）
- 不包含生命周期状态机完整实现（M2 处理）。
- 不包含对外产品 API 与前端工作台（M4/M5 处理）。
- 不包含行情融合与产业链图谱（M4 处理）。

### 6. 数据示例（输入/输出）
输入（news_event）：
```json
{
  "event_id": "evt_20260213_001",
  "event_type": "policy",
  "summary": "地方发布商业航天扶持政策",
  "impact_industries": ["商业航天", "军工"],
  "direction": 1,
  "confidence": 0.86
}
```
输出（decision）：
```json
{
  "decision_id": "dec_001",
  "decision_type": "update_theme",
  "event_id": "evt_20260213_001",
  "theme_id": "theme_space_001",
  "trace_id": "trace_evt_20260213_001"
}
```

---

## 阶段 M2 — 第一阶段优化收敛与门禁（对齐 PLAN_WBS）

### 1. 目标（可衡量）
完成第一阶段稳定性收敛，使路由唯一、执行幂等、阈值动态化、回放一致，并满足关键门禁：重复写入率=0、回放一致率=100%、候选窗口稳定在 3~30。

### 2. 需求（清单）
- [ ] `PRD-M2-R01` 必须冻结统一决策契约 `DecisionEnvelope v1`，并保证必填字段覆盖率 100%。
- [ ] `PRD-M2-R02` 必须形成唯一决策路由入口，消除重复入口与行为漂移。
- [ ] `PRD-M2-R03` 必须实现幂等键策略（`event_id + action + payload_hash`），重放不得产生重复写入。
- [ ] `PRD-M2-R04` semantic matcher 必须支持事件级动态阈值（参考 p95/p98 分布），并以候选规模治理优先。
- [ ] `PRD-M2-R05` 候选治理目标范围必须控制在 3~30，且候选爆炸比低于 5%。
- [ ] `PRD-M2-R06` 高相似歧义场景必须支持二阶段 LLM 裁判（可开关、支持 shadow）。
- [ ] `PRD-M2-R07` pending 清理必须与 durable success 绑定，避免误清理导致回放漂移。
- [ ] `PRD-M2-R08` 发布前必须通过 streams + 全仓测试门禁（无开放 P0/P1 缺陷）。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M2-UC01（同事件重放幂等）
**Given**：同一 `event_id` 因重试被重复投递。  
**When**：DecisionExecutor 执行写入。  
**Then**：第二次命中幂等键，跳过重复写入并记录幂等命中日志。

#### 用例 ID: PRD-M2-UC02（动态阈值控候选）
**Given**：事件语义分布宽、全量候选过大。  
**When**：动态阈值策略执行。  
**Then**：候选集收敛到目标窗口（3~30）后再进入精排。

#### 用例 ID: PRD-M2-UC03（LLM 裁判 shadow）
**Given**：语义匹配 Top 候选分差小于歧义阈值。  
**When**：开启 shadow 裁判模式。  
**Then**：输出裁判建议与一致性评分，仅记录不改写生产结果。

#### 用例 ID: PRD-M2-UC04（回放一致性校验）
**Given**：同一批次历史消息用于 replay。  
**When**：执行回放。  
**Then**：主题状态与映射结果与基线完全一致。

### 4. 验收标准（测试用例）
- Given 运行路由扫描，When 检查处理链，Then 重复入口数必须为 0。
- Given 执行 replay 测试集，When 比对结果，Then 回放一致率必须为 100%。
- Given 动态阈值 A/B，When 对比 76 案例，Then 候选爆炸比 <5% 且精度代理指标不低于基线。
- Given 开启 LLM shadow，When 运行灰度样本，Then P95 附加时延 <800ms 且预算不超限。
- Given 发布门禁执行，When streams/tests 全量跑完，Then 无 P0/P1 未关闭问题。

### 5. 非目标（排除项）
- 不进行第二阶段 CQRS 全量改造（M3 处理）。
- 不建设面向用户的实时资讯 UI（M4/M5 处理）。

### 6. 数据示例（输入/输出）
输入（候选阈值计算）：
```json
{
  "event_id": "evt_20260213_1450",
  "similarity_distribution": {
    "p95": 0.79,
    "p98": 0.86
  },
  "target_candidate_window": [3, 30]
}
```
输出（动态阈值决策）：
```json
{
  "event_id": "evt_20260213_1450",
  "dynamic_threshold": 0.82,
  "candidate_count": 12,
  "arbiter_required": true
}
```

---

## 阶段 M3 — 题材演化引擎（第二阶段）

### 1. 目标（可衡量）
将系统从静态匹配升级为动态演化引擎，实现不可变快照、双工作副本、CQRS 分离、Stage 慢变治理与可回放审计，确保跨模式（NORMAL/SHADOW/DRY_RUN）行为可验证且可追溯。

### 2. 需求（清单）
- [ ] `PRD-M3-R01` 规则引擎输入必须为不可变 `ThemeStateSnapshot`，并附带完整性哈希（`snapshot_hash`）。
- [ ] `PRD-M3-R02` 必须分离 `SemanticWorkingCopy` 与 `RuleWorkingCopy`，禁止混写职责。
- [ ] `PRD-M3-R03` 必须落地 CQRS 三表：`theme_state`（决策态）、`theme_semantic_state`（语义态）、`theme_state_log`（审计态）。
- [ ] `PRD-M3-R04` 必须实现 Stage 跃迁守卫（合法跃迁 + 时间冷却 + 事件确认窗口）。
- [ ] `PRD-M3-R05` 必须提供 `UsageGate` 契约验证，禁止将 Stage 直接作为交易信号。
- [ ] `PRD-M3-R06` 决策必须生成 `decision_hash`，并记录 `input_snapshot_hash`，保证可回放。
- [ ] `PRD-M3-R07` 执行器必须支持 `NORMAL`、`SHADOW`、`DRY_RUN` 三模式，模式语义不可混淆。
- [ ] `PRD-M3-R08` 语义中心更新必须具备节流机制（相似度变化阈值 + 时间窗口），避免高频噪声抖动。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M3-UC01（非法 Stage 跃迁拦截）
**Given**：当前 Stage 为 `INCUBATION`，请求直接跃迁至 `PEAK`。  
**When**：TransitionGuard 校验。  
**Then**：拒绝跃迁并记录失败原因（非法路径/冷却未满足/确认不足）。

#### 用例 ID: PRD-M3-UC02（契约违规阻断）
**Given**：下游交易模块试图直接消费 Stage 字段作为买卖信号。  
**When**：UsageGate 验证。  
**Then**：抛出契约违反错误并阻断输出。

#### 用例 ID: PRD-M3-UC03（Shadow 模式执行）
**Given**：系统部署在 SHADOW。  
**When**：接收有效决策。  
**Then**：只记录日志与指标，不修改生产状态表。

#### 用例 ID: PRD-M3-UC04（回放一致性）
**Given**：存在历史 `decision_hash` + `input_snapshot_hash` 记录。  
**When**：执行同输入重放。  
**Then**：状态归约输出一致并可追溯到同一审计链。

### 4. 验收标准（测试用例）
- Given 任意规则执行，When 检查输入类型，Then 必须仅使用不可变 Snapshot。
- Given Stage 频繁波动输入，When 启用冷却和确认窗口，Then 不得出现高频抖动跃迁。
- Given 交易信号生成调用，When 仅提供 Stage，Then UsageGate 必须拒绝通过。
- Given 三模式压测，When 统计落库行为，Then SHADOW/DRY_RUN 不得污染生产决策态。
- Given 回放测试，When 使用审计日志重放，Then 重放结果与原结果一致。

### 5. 非目标（排除项）
- 不定义具体交易策略参数。
- 不承诺第三方监管报表格式（仅保证审计数据完备）。

### 6. 数据示例（输入/输出）
输入（Snapshot）：
```json
{
  "theme_id": "theme_ai_glasses",
  "stage": 2,
  "heat_score": 64.2,
  "momentum_score": 71.0,
  "event_count": 23,
  "snapshot_hash": "f3a91b7c1d77ab11"
}
```
输出（审计日志）：
```json
{
  "decision_hash": "6b1d6e2e8ad0c6b0f6c2f3f1be7a1c95",
  "input_snapshot_hash": "f3a91b7c1d77ab11",
  "execution_mode": "shadow",
  "transition_result": "rejected_by_cooldown"
}
```

---

## 阶段 M4 — 股票服务与实时资讯产品化（第三阶段）

### 1. 目标（可衡量）
构建面向用户的实时产品化能力，覆盖实时资讯流、盘前/盘后复盘、产业链图谱与统一输出网关，并满足：支持 5000+ 股票实时监控、3 秒采样频率约 600 QPS、行情接收至事件发布延迟 <100ms。

### 2. 需求（清单）
- [ ] `PRD-M4-R01` 必须建设实时资讯流引擎，聚合 `ThemeService`、`ModelService`、`StockService` 多源事件并去重排序。
- [ ] `PRD-M4-R02` 必须提供低延迟推送接口（WebSocket 或 SSE）输出结构化资讯条目。
- [ ] `PRD-M4-R03` 必须实现盘前/盘后复盘生成器，自动生成“盘前必读/涨停复盘/龙虎榜关联”结构化报告。
- [ ] `PRD-M4-R04` 必须新增产业链图谱数据模型（题材 → 产业链 → 环节 → 个股）及查询接口。
- [ ] `PRD-M4-R05` 必须提供统一输出网关（REST + WS），支持流式与文档式数据动静分离。
- [ ] `PRD-M4-R06` `theme_service` 必须支持增量热度更新并发布事件（如 `theme.hot`/`theme.new`）触发实时流。
- [ ] `PRD-M4-R07` 必须引入实体归一化能力，统一公司名、股票代码、产业链实体映射。
- [ ] `PRD-M4-R08` 行情网关必须支持多源适配与回退链路，异常时自动降级保证可用性。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M4-UC01（实时资讯推送）
**Given**：热点题材热度显著上升并发布 `theme.hot`。  
**When**：实时资讯流引擎消费并排序。  
**Then**：在 WebSocket 通道推送带标签和摘要的资讯卡片。

#### 用例 ID: PRD-M4-UC02（盘后复盘生成）
**Given**：交易日收盘，已获取涨停数据与题材映射。  
**When**：复盘生成任务触发。  
**Then**：输出包含“涨停家数/连板高度/龙头个股”的结构化报告。

#### 用例 ID: PRD-M4-UC03（产业链查询）
**Given**：用户请求“机器人”题材产业链。  
**When**：调用图谱查询 API。  
**Then**：返回树形结构与各环节对应股票列表。

#### 用例 ID: PRD-M4-UC04（行情源故障回退）
**Given**：首选行情数据源超时或质量校验失败。  
**When**：QuoteGateway 执行 fallback。  
**Then**：切换次优数据源继续输出标准化行情，不中断主流程。

### 4. 验收标准（测试用例）
- Given 5000 股票订阅，When 以 3 秒轮询运行，Then 系统吞吐满足约 600 QPS 且无持续积压。
- Given 实时行情触发异动，When 发布到事件总线，Then 事件发布延迟 <100ms。
- Given 任意交易日盘后任务，When 生成复盘，Then 报告包含题材维度与个股维度统计。
- Given 题材图谱查询，When 返回结果，Then 至少包含主题、链路层级、环节、股票四级数据。
- Given 多源行情故障注入，When 主源失效，Then 可自动回退且可用性不低于门禁阈值。

### 5. 非目标（排除项）
- 不包含券商交易下单链路。
- 不包含跨市场（美股/港股/期货）统一行情引擎。

### 6. 数据示例（输入/输出）
输入（实时推送条目）：
```json
{
  "feed_id": "feed_20260213_0937001",
  "event_type": "BREAKING",
  "theme_id": "theme_ai_app",
  "title": "AI 应用板块异动拉升",
  "impact_score": 83,
  "tags": ["新题材", "放量", "政策"]
}
```
输出（产业链查询响应）：
```json
{
  "theme": "机器人",
  "chains": [
    {
      "chain_name": "减速器",
      "components": [
        {
          "component_name": "谐波减速器",
          "stocks": ["688017.SH", "300024.SZ"]
        }
      ]
    }
  ]
}
```

---

## 阶段 M5 — 前端投研工作台与 DailyReview 闭环（第四阶段）

### 1. 目标（可衡量）
交付可用的桌面级投研前端（题材雷达 + AI 事件流 + 行情验证三栏）与 DailyReview 页面，并冻结 V1 核心接口，确保前后端可并行开发且字段语义稳定。

### 2. 需求（清单）
- [ ] `PRD-M5-R01` 前端必须采用三栏作战台布局：左栏题材雷达、中栏 AI 事件理解流、右栏行情验证。
- [ ] `PRD-M5-R02` 左栏题材点击必须驱动全局 `currentThemeId`，并联动中右栏数据刷新。
- [ ] `PRD-M5-R03` 中栏必须支持事件类型 `BREAKING/MORNING/REVIEW/LIMIT_CHAIN` 的统一渲染。
- [ ] `PRD-M5-R04` 状态管理必须单一真源（核心状态 `currentThemeId`，派生 `eventList/marketData`），禁止冗余状态漂移。
- [ ] `PRD-M5-R05` DailyReview 必须作为一级页面，至少包含：市场总览、核心题材复盘、资金行为、交易纪律。
- [ ] `PRD-M5-R06` 必须冻结 `GET /api/daily-review` 与 `POST /api/daily-review/generate` 接口契约（字段语义不可变）。
- [ ] `PRD-M5-R07` DailyReview 到次日 Morning Brief 必须形成可追溯自动化工作流（保留来源链路）。
- [ ] `PRD-M5-R08` 前端仅展示 AI 输出，不在前端重算排序/权重/评分。

### 3. 用例（Given / When / Then）

#### 用例 ID: PRD-M5-UC01（三栏联动）
**Given**：用户在左栏选择题材 A。  
**When**：全局状态更新为 `currentThemeId=A`。  
**Then**：中栏加载 A 的事件流，右栏加载 A 的行情验证数据。

#### 用例 ID: PRD-M5-UC02（获取指定日期复盘）
**Given**：用户访问复盘页并选择日期。  
**When**：前端调用 `GET /api/daily-review?date=YYYY-MM-DD`。  
**Then**：页面渲染该日 `DailyReview` 全模块。

#### 用例 ID: PRD-M5-UC03（内部触发复盘生成）
**Given**：管理端发起当日复盘生成。  
**When**：调用 `POST /api/daily-review/generate`。  
**Then**：系统生成 `DailyReview` 并记录来源依赖链。

#### 用例 ID: PRD-M5-UC04（复盘到盘前必读闭环）
**Given**：前一日 DailyReview 已入库。  
**When**：次日盘前任务触发 Morning Brief 生成。  
**Then**：输出条目可反查到上一日复盘字段与校验结果。

### 4. 验收标准（测试用例）
- Given 题材切换操作，When 触发联动，Then 中右栏内容在一次状态更新后完成一致刷新。
- Given 复盘 API 响应，When 前端渲染，Then 字段映射与 DTO 契约一致且无前端重算排名。
- Given 复盘生成接口，When 非授权普通用户调用，Then 请求被拒绝（内部接口保护）。
- Given 字段版本升级，When 新增字段发布，Then 不破坏既有字段语义和前端兼容。
- Given Morning Brief 生成，When 查看来源链，Then 每条建议均可回溯到 DailyReview 输入。

### 5. 非目标（排除项）
- 不包含重型 UI 组件库改造评估。
- 不包含移动端专属适配细节（仅桌面优先）。

### 6. 数据示例（输入/输出）
输入（DailyReview API 请求）：
```http
GET /api/daily-review?date=2026-02-13
```
输出（简化响应）：
```json
{
  "code": 0,
  "data": {
    "date": "2026-02-13",
    "market_summary": {
      "market_emotion": "NEUTRAL"
    },
    "theme_reviews": [
      {
        "theme_id": "theme_robotics",
        "theme_name": "机器人",
        "stage": "DIFFUSION"
      }
    ],
    "trading_principle": {
      "allow_trade": true,
      "focus_themes": ["机器人", "AI应用"],
      "forbidden_actions": ["冰点期追高"]
    }
  }
}
```

---

## 依赖与里程碑关系

- `M1 -> M2 -> M3 -> M4 -> M5`
- 关键跨阶段依赖：
  - M2 契约冻结与幂等策略是 M3 可回放能力前置条件。
  - M3 审计和契约治理是 M4/M5 面向用户输出的可信基础。
  - M4 输出网关与接口稳定性决定 M5 前端联调效率。

## 风险与缓解（摘要）

- 风险 R1：动态阈值在热点分布下失稳。
  - 缓解：profile 回退、A/B 灰度、候选窗口强约束。
- 风险 R2：LLM 裁判带来时延和成本抖动。
  - 缓解：仅歧义样本触发、shadow 先行、预算告警。
- 风险 R3：实时行情源抖动导致产品链路不稳定。
  - 缓解：多源回退、质量校验、缓存分层。
- 风险 R4：前后端字段语义漂移。
  - 缓解：V1 接口冻结、字段只增不改、契约测试。

## 发布门禁（跨阶段统一）

- 功能门禁：核心用例全部通过，关键失败路径可观测。
- 质量门禁：无开放 P0/P1 缺陷。
- 一致性门禁：回放一致率 100%。
- 性能门禁：满足阶段声明的时延/吞吐指标。
- 契约门禁：字段向后兼容，审计链完整。

# Phase 4.5.7 — Unified Analyst Review Document 详细设计文档

> 版本：v0.2  
> 日期：2026-07-12  
> 状态：Implementation In Progress — PR1/PR2/PR3 Backend Completed  
> 目标：将分析师工作台升级为“正式复盘报告编辑态”，并让当日复盘页面复用同一套 ReviewDocument 展示协议与 UI 组件。

关联文档：

- `docs/architecture/REVIEW_DOCUMENT_PRINCIPLES.md`
- `docs/architecture/REVIEW_DOCUMENT_EVOLUTION.md`
- `docs/architecture/FROZEN_MODULES.md`

---

## 0. 背景与问题

Phase 4.5.5 / 4.5.6 已经完成了 Workbench First、Approved Snapshot、Formal Review Projection 与 DailyReview Read Path 的多轮修复，但 2026-07-09 Clean Replay 暴露出一个更根本的问题：

当前系统仍然存在多套复盘展示与消费链路：

```text
Analyst Workbench
  -> AI Draft / cognition_cards / emotion_review / chart_reviews
  -> 分析师审核与 override

DailyReview
  -> Builder / Engine Report / FormalReviewProjectionCompiler / legacy fields
  -> FormalReviewView 或旧 Recap 组件
```

这导致：

1. 分析师工作台看到的是“审核卡片”，不是最终复盘报告的编辑态。
2. 当日复盘页面和工作台存在两套 UI、两套字段映射、两套错误来源。
3. Projection Compiler、legacy enrichment、chart/emotion 静态 JSON、recap_doc fallback 之间形成复杂链路，修一个字段容易暴露另一个字段错配。
4. 分析师修改虽然进入 Snapshot，但最终报告是否正确显示依赖额外 Projection 逻辑，链路过长。

本阶段不继续扩展 Projection Compiler，也不再新增一套独立 ReviewDocument 页面。核心调整是：

```text
Snapshot 是唯一真源
ReviewDocument 是统一前端展示协议
Analyst Workbench = ReviewDocument 编辑态
Daily Review = 同一 ReviewDocument 只读态
```

### 0.1 Single Interpretation Principle

一个业务事实只能存在一个最终解释入口。

错误模式：

```text
市场情绪
  -> emotion_review
  -> formal_review.market_state.emotion
  -> chart emotion json
  -> legacy emotion
  -> 多个入口各自解释
```

正确模式：

```text
Snapshot.emotion_review
  -> ReviewDocument.emotion
  -> Workbench / DailyReview 共用展示
```

约束：

1. 同一业务事实不允许在多个展示模型中重复解释。
2. Workbench 和 DailyReview 不允许各自拥有独立复盘报告模型。
3. 新字段只能进入 ReviewDocument，不再扩展 FormalReviewProjectionCompiler。
4. Debug 信息可以存在，但必须显式标记为 debug，不参与正式阅读路径。

---

## 1. 目标

### 1.1 产品目标

将分析师工作台从“AI 草稿审核入口”升级为“复盘报告编辑器”：

```text
启动分析
  -> 生成 AI Draft
  -> 组装 ReviewDocument Draft
  -> 分析师在同一报告结构中修改
  -> Approve
  -> 当日复盘页面只读展示同一份 ReviewDocument
```

### 1.2 架构目标

1. 只有一个复盘展示模型：`ReviewDocument`。
2. 只有一个复盘展示组件：`ReviewDocumentView`。
3. 分析师工作台和当日复盘页面只区分 `mode`：
   - `editable`：工作台编辑态
   - `readonly`：当日复盘发布态
4. Snapshot 继续作为唯一数据真源，不新增 ReviewDocument 数据表。
5. ReviewDocument 作为 UI Contract，不承担真源职责。
6. 后续逐步删除 DailyReview 二次拼装、legacy fallback、静态 JSON 读取。

---

## 2.1 当前实施状态（截至 2026-07-12）

当前主链已从“多 projection 拼接”切换到 ReviewDocument 增量链路：

```text
Workbench Draft / Snapshot
  -> ReviewDocumentContextFactory
  -> ReviewDocumentAssembler
  -> ReviewDocumentView
  -> ReviewOverride
  -> OverrideApplier
  -> ReviewDocument Final
```

已完成并推送：

| 阶段 | 状态 | 关键产物 |
|---|---:|---|
| PR1.1 Schema + Types | ✅ Completed | `schema.py` / `enums.py` / `quality.py` |
| PR1.2 Golden Fixture + Negative Cases | ✅ Completed | 7/9 semantic golden + negative fixtures |
| PR1.3 ContextFactory + Assembler | ✅ Completed | typed context + pure assembler + deterministic hash |
| PR2 Workbench Preview | ✅ Completed | Workbench API 返回 `review_document`；`ReviewDocumentView` 成为默认预览 |
| PR2 Guard Tests | ✅ Completed | Workbench API 禁 legacy 顶层字段；View 禁旧 endpoint fetch |
| PR3 Diff API | ✅ Completed | `/review-document-diff` 输出字段级 diff |
| PR3 Override Model + Applier | ✅ Completed | `ReviewOverride` / `ReviewOverrideApplier` |
| PR3 Override Persistence API | ✅ Completed | `/review-overrides` 保存 override 文件并重建 final document |
| PR3 UI Override Editor | ⏳ Next | 只做主题身份、股票归属、明日计划三类字段 |
| PR4 Approve + DailyReview ReviewDocument 切换 | ⏳ Pending | Approve manifest + DailyReview readonly |
| PR5 Legacy Removal | ⏳ Pending | 删除旧正式路径，legacy 仅 debug |

已落地提交：

| Commit | 内容 |
|---|---|
| `d4f0ec3eb` | ReviewDocument schema contracts |
| `ce9564d19` | schema contract freeze tests |
| `7b4dd85d7` | golden fixtures + negative cases |
| `4b6c99428` | golden provenance contract |
| `fa55e8473` | typed context + assembler |
| `f2088cb7a` | Workbench ReviewDocument preview |
| `a304b7fb0` | remove stale 20260709 static artifacts |
| `55fb22afe` | Workbench ReviewDocument contract guards |
| `6b85985ac` | ReviewDocument Diff API |
| `36b5c1701` | ReviewDocument OverrideApplier |
| `a903c36e3` | override determinism / FACT path protection |
| `d045da5f0` | Workbench review override persistence |

当前后端能力：

1. `GET /api/v1/analyst-workspace/{trade_date}` 只返回：
   - `review_document`
   - `metadata`
   - `diagnostics`
2. `ReviewDocumentView` 静态 contract 禁止直接 fetch：
   - `/api/emotion-*`
   - `/api/analyst-charts/*`
   - `/daily-review-v2`
3. `ReviewDocument` 自动生成 `metadata.final_document_hash`。
4. 同一输入和同一 override 集合生成稳定 hash。
5. override 输入顺序不影响最终 hash。
6. `market.*` 数值事实路径不能被 `IDENTITY` 等非 FACT 类型绕过修改。
7. 保存的 override 不写 Snapshot，只写：

```text
tmp/analyst_workbench/{trade_date}/review_overrides.json
```

当前未完成：

1. Workbench UI Override Editor 尚未接入。
2. Approve 仍未绑定 ReviewDocument Final / manifest。
3. DailyReview 仍待 PR4 完全切换到 approved `review_document`。
4. `review_overrides.json` 尚未引入 version 并发控制。

## 2. 非目标范围

本阶段不做：

1. 不重写 AI Draft 生成算法。
2. 不新增 LLM prompt 优化。
3. 不删除 ReviewSnapshot。
4. 不新增 ReviewDocument 数据库表。
5. 不继续扩大 FormalReviewProjectionCompiler 字段。
6. 不在图表、情绪、前端旧组件里继续做临时拼接。
7. 不解决全部历史 legacy 字段删除，legacy 删除另设后续阶段。

---

## 3. 核心架构

### 3.1 目标链路

```text
Market Data / Derived Data / AI Draft
          |
          v
    ReviewSnapshot
          |
          v
 ReviewDocumentAssembler
          |
          v
    ReviewDocument
          |
     +----+----+
     |         |
     v         v
Workbench   DailyReview
editable    readonly
```

### 3.2 状态流

```text
NOT_STARTED
  |
  | 启动分析
  v
DRAFT
  |
  | ReviewDocument Draft
  v
EDITING
  |
  | 分析师修改 / 保存
  v
IN_REVIEW
  |
  | ReviewDocument Final
  | Approve
  v
APPROVED
  |
  | DailyReview 只读展示
  v
PUBLISHED_VIEW
```

Approve 不允许“发布时重新组装一个用户没见过的对象”。正确顺序是：

```text
Snapshot Draft
  |
  v
ReviewDocument Draft
  |
  v
Analyst Override
  |
  v
ReviewDocument Final
  |
  v
Quality Gate
  |
  v
Approved Snapshot + final_review_document_hash
```

验收标准：

1. Workbench 中用户看到的 `ReviewDocument Final` 与 DailyReview 发布态读取的内容一致。
2. Approve 保存 `final_review_document_hash`，用于证明发布对象未漂移。
3. Approve 后不允许再通过其他 Projection 重新解释同一个 Snapshot。
4. Approved Snapshot 只保存最终文档 hash 与版本信息，不保存完整 ReviewDocument。

Approved Snapshot metadata 增加：

```json
{
  "approved_review_document_hash": "sha256:...",
  "approved_review_document_schema_version": "review_document_v1",
  "approved_assembler_version": "assembler_v1.0",
  "approved_at": "2026-07-11T14:30:00Z"
}
```

同时生成 immutable manifest：

```text
tmp/analyst_workbench/{trade_date}/approved_manifest.json
```

示例：

```json
{
  "trade_date": "2026-07-09",
  "snapshot_hash": "sha256:...",
  "document_hash": "sha256:...",
  "document_schema_version": "review_document_v1",
  "assembler_version": "assembler_v1.0",
  "golden_test": "PASS",
  "quality": "READY",
  "approved_at": "2026-07-11T14:30:00Z"
}
```

manifest 职责：

1. 给回测、AI 学习、复盘分析提供不可变发布索引。
2. 不保存完整 ReviewDocument。
3. 只保存复现所需 hash、版本、质量状态。
4. 与 Approved Snapshot metadata 一致，否则发布失败。

复现规则：

```text
ReviewSnapshot
  + approved_review_document_schema_version
  + approved_assembler_version
  -> ReviewDocument
  -> hash == approved_review_document_hash
```

这样既避免保存第二份真源，又能保证历史复盘不会被未来 assembler 版本重新解释。

### 3.3 真源边界

| 对象 | 职责 | 是否真源 |
|---|---|---|
| ReviewSnapshot | 保存 AI Draft、分析师修改、审批状态、hash、审计信息 | 是 |
| ReviewDocument | 前端展示协议，由 Snapshot 构建 | 否 |
| ReviewDocumentView | 同一 UI 组件，支持编辑态和只读态 | 否 |
| DailyReview API | 返回 approved ReviewDocument | 否 |
| FormalReviewProjectionCompiler | Phase 4.5.6 过渡层，后续降级/冻结 | 否 |

命名约束：

```text
必须使用 ReviewDocumentAssembler。
禁止命名为 ReviewDocumentBuilder。
```

原因：

1. 当前项目中 `builder` 已经关联 `recap_builder`、`engine_builder`、`report_builder`、`projection_builder` 等历史包袱。
2. `Builder` 容易被误解为“重新生成业务结论”。
3. `Assembler` 明确表达：只组装展示模型，不计算、不推理、不补数据。

---

## 4. ReviewDocument Schema

### 4.0 字段分类与计算边界

ReviewDocument 中的每个字段必须归类，分类规则沿用 Phase 4.5.6 的字段级 merge policy。

| 分类 | 含义 | 示例 | 来源 | 是否允许 Assembler 计算 |
|---|---|---|---|---|
| FACT | 市场事实 | `limit_up_count`, `up_count`, `stock.board_height` | Snapshot 内已保存事实 | 禁止 |
| ASSESSMENT | 判断与结论 | `emotion.phase`, `theme.stage`, `risk_level` | AI + Analyst final | 禁止 |
| PLAN | 明日计划 | `allowed_actions`, `watch_themes`, `invalidation_signals` | Snapshot playbook + analyst final | 禁止 |
| AUDIT | 审计与追溯 | `ai_value`, `analyst_value`, `final_value`, `source_refs` | Snapshot override / metadata | 允许格式化，不允许生成业务结论 |

严格边界：

```text
ReviewDocumentAssembler 只允许：
  字段映射
  格式转换
  explicit override 合并
  source trace 标记
  quality 标记

ReviewDocumentAssembler 禁止：
  判断
  推理
  补数据
  fallback
  重新计算指标
  从 chart view model 反推认知结论
```

因此，Schema 中出现的字段必须满足：

1. 如果是 `strength_score`、`capital_state`、`stage` 等判断或分数字段，必须已经存在于 Snapshot / AI Draft / derived context。
2. 如果 Snapshot 不存在该字段，ReviewDocument 只能输出 `null` 或 `quality=MISSING`。
3. 不允许 Assembler 为了让 UI “看起来完整”而临时计算业务字段。

### 4.1 顶层结构

```json
{
  "metadata": {},
  "summary": {},
  "market": {},
  "emotion": {},
  "themes": [],
  "stocks": [],
  "capital": {},
  "limit_up": {},
  "plan": {},
  "risk": {},
  "quality": {},
  "field_provenance": {},
  "audit": {}
}
```

### 4.2 metadata

```json
{
  "trade_date": "2026-07-09",
  "document_schema_version": "review_document_v1",
  "review_document_schema_version": "1.0",
  "snapshot_schema_version": "4.5.7",
  "assembler_version": "assembler_v1.0",
  "status": "DRAFT | IN_REVIEW | APPROVED",
  "source": "analyst_workbench",
  "snapshot_hash": "...",
  "final_document_hash": "...",
  "snapshot_version": 1,
  "generated_at": "...",
  "approved_at": null
}
```

版本规则：

| 字段 | 含义 |
|---|---|
| `document_schema_version` | ReviewDocument schema 名称，例如 `review_document_v1` |
| `review_document_schema_version` | ReviewDocument schema 语义版本，例如 `1.0` |
| `snapshot_schema_version` | 生成该文档所需的 Snapshot 契约版本 |
| `assembler_version` | 使用的 Assembler 版本 |
| `snapshot_hash` | 输入 Snapshot hash |
| `final_document_hash` | 当前 ReviewDocument canonical JSON hash |

为什么必须有版本：

```text
2026-07-09:
  snapshot schema 4.5.7
  + assembler_v1.0
  -> review_document_v1

2026-09:
  snapshot schema 4.7
  + assembler_v2.0
  -> review_document_v2
```

历史复盘必须按当时的 `assembler_version` 和 `document_schema_version` 复现，禁止被新版本自动重新解释。

### 4.2.1 section quality

ReviewDocument 必须提供顶层 `quality`，每个业务 section 也必须有自己的质量状态。

```json
{
  "quality": {
    "overall": "READY | DEGRADED | BLOCKED",
    "freshness": {
      "status": "READY | DEGRADED | BLOCKED",
      "snapshot_age_seconds": 120,
      "derived_data_time": "2026-07-09T15:05:00+08:00",
      "trade_date_match": true
    },
    "sections": {
      "market": {
        "status": "READY",
        "missing_fields": [],
        "warnings": [],
        "freshness": {
          "status": "READY",
          "source_trade_date": "2026-07-09",
          "source_generated_at": "2026-07-09T15:05:00+08:00"
        }
      },
      "capital": {
        "status": "DEGRADED",
        "missing_fields": ["institution", "hot_money"],
        "warnings": ["资金方向缺失，禁止显示为共0个方向"]
      }
    },
    "can_approve": false,
    "blocking_issues": []
  }
}
```

状态定义：

| 状态 | 含义 | UI 行为 |
|---|---|---|
| READY | 数据完整，允许发布 | 正常展示 |
| DEGRADED | 有缺失但可读 | 显示警告，不伪造成业务结论 |
| MISSING | section 无法生成 | 展示缺失说明 |
| BLOCKED | 关键数据缺失，不允许 approve | 阻断发布 |
| ERROR | 读取/解析失败 | 展示错误与 source trace |

Freshness 规则：

| 字段类型 | Freshness 要求 |
|---|---|
| FACT | `source_trade_date == document.trade_date`，否则 BLOCKED |
| IDENTITY | override 所属 snapshot_hash 必须匹配当前 snapshot_hash |
| ASSESSMENT | 必须有 `source_generated_at`；跨日来源至少 DEGRADED |
| PLAN | 必须来自当前交易日 playbook 或当前交易日 analyst override |
| AUDIT | 必须记录生成时间，但不参与业务阻断 |

硬规则：

1. 空列表不等于业务结论。
2. `capital.institution=[]` 不能显示为“共0个方向，多数调整”。
3. `limit_up.categories=[]` 不能显示为“主线明确”。
4. 缺失值必须通过 `quality` 告知用户，而不是 fallback。
5. 任何 FACT 使用非当前 `trade_date` 来源，必须 BLOCKED。

### 4.2.2 field_provenance

`source_refs` 只能说明 section 或实体的大致来源。为了解决字段级调试问题，ReviewDocument 必须提供 `field_provenance`。

示例：

```json
{
  "field_provenance": {
    "market.limit_up_count": {
      "source": "snapshot.chart_reviews.market_power.limit_up_count",
      "field_type": "FACT",
      "confidence": 1.0,
      "transform": "direct_mapping",
      "validation_status": "verified",
      "source_trade_date": "2026-07-09",
      "source_generated_at": "2026-07-09T15:05:00+08:00"
    },
    "themes[9055378].name.final_value": {
      "source": "snapshot.cognition_cards[9055378].field_overrides.subject_name",
      "field_type": "IDENTITY",
      "confidence": 1.0,
      "transform": "explicit_override",
      "validation_status": "verified",
      "source_trade_date": "2026-07-09",
      "source_generated_at": "2026-07-09T16:12:00+08:00"
    }
  }
}
```

字段要求：

| 字段 | 含义 |
|---|---|
| `source` | 精确来源路径 |
| `field_type` | `FACT / IDENTITY / ASSESSMENT / PLAN / AUDIT` |
| `confidence` | 映射可信度，直接映射为 1.0 |
| `transform` | `direct_mapping / explicit_override / format_only / aggregate_from_snapshot` |
| `validation_status` | `verified / warning / invalid` |
| `source_trade_date` | 来源数据交易日 |
| `source_generated_at` | 来源数据生成时间 |

用途：

```text
为什么 market.limit_up_count 是 75？
  -> field_provenance["market.limit_up_count"]
  -> snapshot.chart_reviews.market_power.limit_up_count
```

禁止：

1. 字段进入 ReviewDocument 但没有 provenance。
2. `transform` 写成模糊值，例如 `computed`、`unknown`。
3. FACT 字段的 provenance 指向 analyst override。
4. `validation_status=invalid` 的字段参与 `quality.overall=READY`。

### 4.3 summary：今日核心结论

对应《7月9日复盘_DeepSeek完整结构版》的“今日核心结论”。

```json
{
  "market_conclusion": "反弹第1天，情绪修复但不是反转",
  "main_story": "科技硬件与指数共振，存储芯片/半导体设备延续性更强",
  "primary_theme": {
    "ai_value": "人形机器人",
    "analyst_value": "PCB",
    "final_value": "PCB",
    "reason": "机器人高位分歧，资金切换到PCB容量方向"
  },
  "key_points": [
    "指数反弹已透支大部分空间",
    "反弹套利，快进快出",
    "核心方向观察存储芯片/半导体设备"
  ],
  "top_risks": [
    "反弹不是反转",
    "明日缺少舒适开仓点"
  ]
}
```

### 4.4 market：市场状态

字段原则：

1. 市场事实字段必须来自 Snapshot 中的 `chart_reviews` 或明确 derived context。
2. 缺失值用 `null`，禁止把缺失显示成 `0`。
3. 不允许前端从 `/api/analyst-charts/{date}.json` 读取。

```json
{
  "limit_up_count": 75,
  "limit_down_count": 29,
  "up_count": 3561,
  "down_count": 1609,
  "active_capital_yi": 2707,
  "max_board_height": 8,
  "chain_board_count": 6,
  "market_power_score": 6,
  "breadth_quality": {
    "status": "READY | DEGRADED | MISSING",
    "warning": null
  },
  "source_refs": [
    "snapshot.chart_reviews.market_power",
    "snapshot.derived_context.market_metrics"
  ]
}
```

### 4.5 emotion：情绪周期

```json
{
  "phase": "REBOUND",
  "phase_label": "情绪修复",
  "score": 39,
  "risk_level": "MEDIUM",
  "strategy": "反弹套利，快进快出",
  "trend": [
    {"date": "2026-07-07", "phase": "PANIC"},
    {"date": "2026-07-08", "phase": "REPAIR_WATCH"},
    {"date": "2026-07-09", "phase": "REBOUND"}
  ],
  "confidence": 0.89,
  "source_refs": ["snapshot.emotion_review"]
}
```

Contract：

1. `confidence` 统一为 `0.0 ~ 1.0`。
2. UI 显示百分比由前端格式化。
3. 不允许出现 `139%` 这类未归一化值。

### 4.6 themes：题材结构

题材是 ReviewDocument 的核心实体。来源优先级：

```text
Analyst explicit override
  > Snapshot cognition_cards
  > Snapshot derived_context.theme_cycle_judgement_v2
  > Snapshot chart/theme evidence
```

```json
[
  {
    "theme_key": "9055378",
    "name": {
      "ai_value": "人形机器人",
      "analyst_value": "PCB",
      "final_value": "PCB",
      "reason": "资金从高位题材切换到PCB容量方向"
    },
    "role": "MAINLINE",
    "stage": "启动第1天",
    "strength_score": 47,
    "capital_state": "资金回流确认",
    "drivers": [
      "指数反弹共振",
      "容量方向承接资金"
    ],
    "stocks": ["603137.SH"],
    "source_refs": [
      "snapshot.cognition_cards[theme_key=9055378]",
      "snapshot.derived_context.themes[theme_key=9055378]"
    ]
  }
]
```

Identity 字段规则：

1. `name.final_value` 必须消费 `field_overrides.subject_name`。
2. `name` 属于 `IDENTITY`，不是普通 assessment。
3. 分析师显式修改时，最终 UI 必须显示 `final_value`。
4. AI 原始值只作为审计与对照显示。

### 4.7 capital：资金方向

对应 DeepSeek 文档的“机构资金审美方向”“游资方向”。

```json
{
  "market": {
    "active_capital_yi": 2707,
    "state": "资金修复"
  },
  "institution": [
    {
      "name": "存储芯片模组厂",
      "state": "启动第1天",
      "evidence": ["板块与指数共振", "容量方向承接"]
    }
  ],
  "hot_money": [
    {
      "name": "商业航天",
      "state": "观察",
      "evidence": ["事件催化", "周末发酵预期"]
    }
  ],
  "source_refs": [
    "snapshot.derived_context.money_flows",
    "snapshot.cognition_cards"
  ]
}
```

禁止：

1. 不允许从 `recap_doc.institution_style` fallback。
2. 不允许从 chart 展示字段反推资金方向。
3. 若没有资金数据，显示 `quality=MISSING`，不显示“共0个方向”作为业务结论。

### 4.8 stocks：强势股结构

```json
[
  {
    "stock_code": "603137.SH",
    "stock_name": "恒尚节能",
    "theme_key": "9055378",
    "theme_name": "半导体产业链",
    "role": ["LEADER"],
    "board_height": 8,
    "reason": "拟收购存储公司",
    "scores": {
      "strength_score": 92,
      "capital_score": 78,
      "structure_score": 85,
      "confidence": 0.82
    },
    "source_refs": ["snapshot.derived_context.strong_stocks"]
  }
]
```

规则：

1. 按 `stock_code` 去重。
2. 同一股票只显示一次。
3. `role` 可多值，但展示排序由 ReviewDocumentAssembler 从 Snapshot 已有排序/优先级字段映射，不交给 UI 猜。

### 4.9 limit_up：涨停分类

对应 DeepSeek 文档的“涨停股分类”。

```json
{
  "total": 75,
  "categories": [
    {
      "name": "存储芯片",
      "count": 8,
      "leaders": ["恒尚节能"],
      "stocks": ["603137.SH"]
    },
    {
      "name": "半导体设备",
      "count": 6,
      "leaders": [],
      "stocks": []
    }
  ],
  "source_refs": [
    "snapshot.derived_context.theme_cycle_judgement_v2",
    "snapshot.chart_reviews.limit_up_classification"
  ]
}
```

规则：

1. 有题材数据时必须列出题材名清单。
2. 不能只显示“涨停75家，主线明确”。
3. 若题材分类缺失，显示 `quality=MISSING` 并阻断 Approve 或至少提示不可发布。

### 4.10 plan：明日计划

```json
{
  "scenario": "REBOUND_ARBITRAGE",
  "allowed_actions": [
    "核心方向低吸套利",
    "只做确认后的容量方向"
  ],
  "forbidden_actions": [
    "高位接力追龙头",
    "反弹次日盲目开新仓"
  ],
  "watch_themes": [
    {"theme_key": "9055378", "theme_name": "PCB"}
  ],
  "watch_stocks": [],
  "confirmation_signals": [
    "指数继续放量",
    "核心方向分歧后承接"
  ],
  "invalidation_signals": [
    "高位股补跌扩散",
    "容量方向冲高回落"
  ],
  "source_refs": ["snapshot.playbook"]
}
```

规则：

1. 明日计划只展示 `final_value`。
2. AI 原始建议与分析师修改差异进入 `audit`。
3. 不允许 AI watch universe 和 analyst watch universe 混合展示。

### 4.11 audit：审计

```json
{
  "explicit_overrides": [
    {
      "field": "themes.name",
      "entity_key": "9055378",
      "ai_value": "人形机器人",
      "analyst_value": "PCB",
      "final_value": "PCB",
      "reason": "机器人高位分歧，资金切换到PCB容量方向"
    }
  ],
  "system_resolutions": [],
  "compatibility_mappings": [],
  "source_quality": {
    "market": "READY",
    "emotion": "READY",
    "themes": "READY",
    "capital": "READY",
    "stocks": "READY",
    "plan": "READY"
  }
}
```

审计分类：

| 类型 | 含义 | 是否计入分析师 override |
|---|---|---|
| explicit_overrides | 分析师主动修改 | 是 |
| system_resolutions | 系统根据规则补齐 final_value | 否 |
| compatibility_mappings | 旧字段迁移映射 | 否 |

目标是避免 `override_summary.total=108` 这类污染进入学习系统。

---

## 5. ReviewDocumentAssembler

### 5.1 职责

`ReviewDocumentAssembler` 负责把 `ReviewSnapshot` 组装成 `ReviewDocument`。

它可以做：

1. 字段映射。
2. ViewModel 组装。
3. 显式 override 合并。
4. source_refs 标记。
5. 数据质量标记。

它禁止做：

1. 查询数据库。
2. 调 LLM。
3. 重新计算市场指标。
4. 从 static JSON fallback。
5. 从 legacy recap_doc 猜字段。

### 5.2 输入

Assembler 禁止直接接收完整 `ReviewSnapshot`。必须通过受限 DTO 输入：

```text
ReviewSnapshot
  |
  v
ReviewDocumentContext
  |
  v
ReviewDocumentAssembler
```

原因：

1. Snapshot 会越来越大，包含 raw LLM output、debug、metrics、audit 等非展示字段。
2. 如果 Assembler 能访问完整 Snapshot，后续很容易出现 `snapshot.xxx.xxx` 偷读。
3. Context 是允许字段白名单，可以把展示协议和存储结构解耦。

```python
@dataclass(frozen=True)
class MarketContext:
    market_metrics: dict
    chart_reviews: tuple[dict, ...]
    source_meta: dict


@dataclass(frozen=True)
class EmotionContext:
    emotion_review: dict
    source_meta: dict


@dataclass(frozen=True)
class ThemeContext:
    cognition_cards: tuple[dict, ...]
    theme_cycle_rows: tuple[dict, ...]
    source_meta: dict


@dataclass(frozen=True)
class CapitalContext:
    money_flow_rows: tuple[dict, ...]
    institution_rows: tuple[dict, ...]
    hot_money_rows: tuple[dict, ...]
    source_meta: dict


@dataclass(frozen=True)
class StockContext:
    strong_stock_rows: tuple[dict, ...]
    abnormal_signal_rows: tuple[dict, ...]
    source_meta: dict


@dataclass(frozen=True)
class PlanContext:
    playbook: dict
    source_meta: dict


@dataclass(frozen=True)
class OverrideContext:
    field_overrides: dict
    explicit_overrides: tuple[dict, ...]
    source_meta: dict


@dataclass(frozen=True)
class ReviewDocumentContext:
    trade_date: date
    metadata: dict
    market_context: MarketContext
    emotion_context: EmotionContext
    theme_context: ThemeContext
    capital_context: CapitalContext
    stock_context: StockContext
    plan_context: PlanContext
    override_context: OverrideContext
    approval: dict


@dataclass(frozen=True)
class ReviewDocumentAssemblerInput:
    context: ReviewDocumentContext
    mode: Literal["draft", "review", "approved"]
```

Context 构建职责：

```text
ReviewDocumentContextFactory:
  从 ReviewSnapshot 提取允许字段
  不改变字段语义
  不计算业务结论
  不做 fallback
```

Assembler 只能访问 `ReviewDocumentContext`，不能访问原始 Snapshot。

禁止：

```python
context.derived_context["xxx"]
snapshot.xxx.xxx
```

允许：

```python
context.theme_context.theme_cycle_rows
context.capital_context.money_flow_rows
context.override_context.explicit_overrides
```

这样未来新增来源必须先进入明确的 Context 类型，不允许通过大 dict 扩散。

### 5.3 输出

```python
@dataclass(frozen=True)
class ReviewDocument:
    metadata: dict
    summary: dict
    market: dict
    emotion: dict
    themes: list[dict]
    stocks: list[dict]
    capital: dict
    limit_up: dict
    plan: dict
    risk: dict
    audit: dict
```

### 5.4 质量门

Assembler 输出前必须检查：

| Section | Gate |
|---|---|
| market | `limit_up_count` 不为空；`up_count/down_count` 缺失时标记 DEGRADED |
| emotion | `phase`、`score`、`strategy` 至少存在一个 |
| themes | `themes.length > 0` |
| capital | institution/hot_money 至少有数据或明确 MISSING |
| stocks | 可为空，但必须带 source_quality |
| limit_up | 有 total 时必须尝试分类；分类缺失不能伪装为“主线明确” |
| plan | approve 前必须有 scenario 或 allowed/forbidden/watch 任一项 |

Approve 阻断规则：

```text
themes = MISSING -> 阻断
limit_up.total 存在但 categories 为空 -> 阻断或强警告
market.limit_up_count 缺失 -> 阻断
emotion.phase 缺失 -> 强警告
```

### 5.5 业务一致性 Gate

除 section 完整性外，Approve 前必须执行跨 section 一致性检查。

#### Gate 1：主线一致性

```text
summary.primary_theme.final_value
  必须存在于
themes[].name.final_value
```

失败示例：

```text
今日主线：PCB
题材列表：机器人、存储芯片
```

处理：阻断 Approve。

#### Gate 2：股票归属一致性

```text
stocks[].theme_key
  必须存在于
themes[].theme_key
```

例外：无法归属的股票必须进入 `theme_key="__unmapped__"`，并在 quality warnings 中说明。

#### Gate 3：计划观察一致性

```text
plan.watch_themes[].theme_key
  必须来自
themes[].theme_key
```

如果 analyst override 新增观察题材，必须同步出现在 themes 中，不能只出现在 plan。

#### Gate 4：Override 完整性

所有 explicit override 必须满足：

```text
ai_value != null
analyst_value != null
final_value == analyst_value
reason 可为空但必须存在字段
```

失败示例：

```json
{
  "ai_value": "人形机器人",
  "analyst_value": "PCB",
  "final_value": ""
}
```

处理：阻断 Approve。

#### Gate 5：版本与 hash 一致性

```text
canonical_json(ReviewDocument Final)
  -> sha256
  == final_document_hash
```

若 hash 不一致，禁止 Approve。

---

## 6. API 设计

### 6.1 Workbench 获取 ReviewDocument Draft / Final

```http
GET /api/v1/analyst-workspace/{trade_date}
```

返回：

```json
{
  "review_document": {},
  "metadata": {},
  "diagnostics": {}
}
```

来源：

```text
tmp/analyst_workbench/{date}/draft_v1.json
tmp/analyst_workbench/{date}/draft_context.json
tmp/analyst_workbench/{date}/snapshot.json（若已保存/approve）
tmp/analyst_workbench/{date}/review_overrides.json（若存在）
```

约束：

1. Workbench API 顶层只允许 `review_document` / `metadata` / `diagnostics`。
2. 不再并行返回 `emotion_review`、`chart_reviews`、`chart_data`、`formal_review`、`recap_doc`。
3. `review_document` 每次由 draft/snapshot + overrides 重建。

### 6.2 保存分析师修改（ReviewOverride）

```http
POST /api/v1/analyst-workspace/{trade_date}/review-overrides
```

请求：

```json
{
  "overrides": [
    {
      "field_path": "themes[robot].name",
      "field_class": "IDENTITY",
      "ai_value": "人形机器人",
      "analyst_value": "PCB",
      "final_value": "PCB",
      "reason": "资金切换"
    }
  ]
}
```

规则：

1. API 不直接保存 ReviewDocument 全量对象。
2. API 只保存 field-level ReviewOverride。
3. ReviewDocument 每次由 Snapshot + overrides 重建。
4. FACT 字段禁止通过 override 修改。
5. `market.*` 数值事实路径禁止用 `IDENTITY` / `ASSESSMENT` 绕过 FACT 保护。

当前短期持久化：

```text
tmp/analyst_workbench/{trade_date}/review_overrides.json
```

当前格式：

```json
{
  "trade_date": "2026-07-09",
  "saved_at": "2026-07-12T00:00:00Z",
  "overrides": []
}
```

PR4 前建议升级为：

```json
{
  "version": 3,
  "trade_date": "2026-07-09",
  "updated_at": "2026-07-12T00:00:00Z",
  "overrides": []
}
```

并发规则：

1. 客户端保存时提交 `base_version`。
2. 服务端当前 version 与 `base_version` 不一致时返回 conflict。
3. 禁止浏览器 A 用旧 version 覆盖浏览器 B 的修改。

### 6.3 获取 ReviewOverride

```http
GET /api/v1/analyst-workspace/{trade_date}/review-overrides
```

返回：

```json
{
  "overrides": [],
  "metadata": {
    "trade_date": "2026-07-09",
    "source": "review_overrides_json"
  }
}
```

### 6.4 获取 ReviewDocument Diff

```http
GET /api/v1/analyst-workspace/{trade_date}/review-document-diff
```

返回：

```json
{
  "review_document_diff": {
    "changes": [
      {
        "path": "themes[robot].name",
        "field_class": "IDENTITY",
        "before": "人形机器人",
        "after": "PCB",
        "final_value": "PCB",
        "reason": "资金切换",
        "source": "explicit_override"
      }
    ],
    "summary": {
      "total_changes": 1,
      "identity_changes": 1
    }
  },
  "metadata": {}
}
```

用途：

1. Override UI 展示 AI / Analyst / Final。
2. 审核页展示差异。
3. 未来 M9 Learning 学习字段级修改与结果。

### 6.5 Approve

```http
POST /api/v1/analyst-workspace/{trade_date}/approve
```

行为：

1. 执行 ReviewDocumentAssembler，生成 `ReviewDocument Final`。
2. 运行质量门。
3. 计算 `final_review_document_hash`。
4. 写入 approved snapshot metadata。
5. 生成 `snapshot_hash`。
6. 返回 approved ReviewDocument。

### 6.6 DailyReview 只读展示

```http
GET /api/v2/daily-review-v2?date=2026-07-09
```

Phase 4.5.7 目标响应：

```json
{
  "metadata": {},
  "review_document": {},
  "diagnostics": {}
}
```

正式响应禁止并列返回 `formal_review`、`legacy`、`emotion_review`、`market_chart_reviews` 等旧结构。

如果仍需排查旧链路，只能走显式 debug API：

```http
GET /api/v2/daily-review-v2/debug?date=2026-07-09
```

前端正式路径没有优先级选择问题：

```text
DailyReview = review_document only
```

---

## 7. 前端设计

### 7.1 组件

新增：

```text
frontend/src/components/review-document/
  ReviewDocumentView.tsx
  ReviewSection.tsx
  ReviewField.tsx
  OverrideEditor.tsx
  MarketSection.tsx
  EmotionSection.tsx
  ThemeSection.tsx
  CapitalSection.tsx
  StockSection.tsx
  LimitUpSection.tsx
  PlanSection.tsx
  AuditPanel.tsx
```

### 7.1.1 Workbench UI 渐进接入

不一次性替换整个 AnalystWorkspace。分三阶段迁移：

#### Phase UI-1：新增 ReviewDocument Preview Panel

在当前分析师工作台顶部新增预览面板，旧 AI Draft / cognition cards / emotion cards / chart panel 保留。

```text
分析师工作台

[启动分析]

ReviewDocument Preview
  市场状态
  情绪周期
  主线题材
  机构资金
  游资方向
  涨停分类
  强势股票
  明日计划

旧 AI Draft / 卡片区（保留，用于对照）

[保存]
[Approve]
```

目标：

1. 验证 Snapshot -> ReviewDocument 的数据完整性。
2. 让分析师在不失去旧视图的情况下对比新文档。
3. 快速发现 section quality、题材分类、资金方向等缺失问题。

#### Phase UI-2：ReviewDocument 成为主界面

ReviewDocumentView 移到页面主区域；旧 cognition cards、emotion cards、chart panel 降级到折叠调试区。

#### Phase UI-3：删除旧 UI

当 5 个交易日观察通过后：

1. 删除旧 Workbench 报告卡片主路径。
2. 保留 debug API 或开发态开关。
3. DailyReview 与 Workbench 均只使用 ReviewDocumentView。

### 7.2 ReviewDocumentView Props

```ts
type ReviewDocumentMode = 'editable' | 'readonly'

interface ReviewDocumentViewProps {
  document: ReviewDocument
  mode: ReviewDocumentMode
  onOverrideChange?: (override: ReviewOverride) => void
  onSave?: () => void
  onApprove?: () => void
}
```

### 7.3 Workbench 使用

```tsx
<ReviewDocumentView
  document={reviewDocument}
  mode="editable"
  onOverrideChange={handleOverrideChange}
  onSave={saveWorkspace}
  onApprove={approveReview}
/>
```

### 7.4 DailyReview 使用

```tsx
<ReviewDocumentView
  document={reviewDocument}
  mode="readonly"
/>
```

### 7.5 编辑态交互

每个可校准字段展示三层：

```text
AI 判断
  人形机器人

分析师修改
  PCB
  原因：资金切换

最终显示
  PCB
```

只读态只展示 final value，但可展开 Audit。

---

## 8. 数据来源映射

| ReviewDocument Section | Snapshot 来源 | 禁止来源 |
|---|---|---|
| summary | `narrative`, `cognition_cards`, `emotion_review` | legacy `market_summary` fallback |
| market | `chart_reviews`, `derived_context.market_metrics` | static `/api/analyst-charts` |
| emotion | `emotion_review` | static `/api/emotion-{date}.json` |
| themes | `cognition_cards`, `derived_context.themes` | chart view model 反推 |
| capital | `derived_context.money_flows`, `cognition_cards` | `recap_doc.institution_style` fallback |
| stocks | `derived_context.strong_stocks` | repeated legacy stock lists |
| limit_up | `derived_context.theme_cycle_judgement_v2`, `chart_reviews` | 纯文案“主线明确” |
| plan | `playbook`, explicit overrides | AI/analyst 混合 watch list |
| audit | `field_overrides`, approval metadata | system-generated defaults |

---

## 9. 迁移计划

### PR1 — ReviewDocument Schema + Assembler

状态：✅ Completed

PR1 拆成三个小 PR，未混入 UI 或 legacy 删除。

#### PR1.1 — Schema + Types

状态：✅ Completed

交付：

1. `review_document/schema.py`
2. `review_document/enums.py`
3. `review_document/quality.py`
4. 定义：
   - `SectionQuality`
   - `FieldClass`
   - `DocumentStatus`
   - `ReviewDocument`
   - `ReviewDocumentMetadata`

验收：

1. schema 可序列化为 JSON。
2. `document_schema_version`、`snapshot_schema_version`、`assembler_version` 必填。
3. 每个 section 都有 quality。

#### PR1.2 — Golden Fixture + Negative Cases

状态：✅ Completed

交付：

1. `docs/test_fixtures/review_document/2026-07-09-review-golden.json`
2. `docs/test_fixtures/review_document/negative_capital_missing.json`
3. `docs/test_fixtures/review_document/negative_legacy_leakage.json`
4. Golden semantic assertions

验收：

1. Golden fixture 明确定义 7/9 正确结果。
2. Negative fixture 明确定义旧问题不能出现。
3. 还未实现 Assembler 时，也能先审阅目标输出。

#### PR1.3 — ContextFactory + Assembler + Golden Test

状态：✅ Completed

交付：

1. `review_document/context.py`
2. `review_document/assembler.py`
3. `ReviewDocumentContextFactory`
4. `ReviewDocumentAssembler`
5. `test_review_document_golden_20260709.py`
6. `test_review_document_negative_cases.py`
7. `test_review_document_legacy_leakage.py`
8. `scripts/verify_review_document.py`

验收：

1. Assembler 只接收 `ReviewDocumentContext`。
2. Assembler 不依赖完整 Snapshot。
3. 7/9 snapshot 能生成 ReviewDocument。
4. `themes.length > 0`
5. `capital.institution.length > 0` 或质量明确 MISSING。
6. `limit_up.categories.length > 0`
7. `field_overrides.subject_name` 能进入 `themes[].name.final_value`。
8. Golden Test Runner 输出 PASS。
9. Negative cases 必须 FAIL/BLOCKED。

原始计划中的脚本：

1. `docs/test_fixtures/review_document/2026-07-09-review-golden.json`
2. `scripts/verify_review_document.py`
3. `test_review_document_golden_20260709.py`

### PR2 — Workbench Preview Panel

状态：✅ Completed

交付：

1. Workbench API 返回 `review_document`。
2. AnalystWorkbench 默认展示 `ReviewDocumentView(mode="editable")`。
3. Workbench API contract 收紧，只返回 `review_document` / `metadata` / `diagnostics`。
4. `ReviewDocumentView` 禁止直接 fetch 旧 endpoint。

验收：

1. ✅ 点击启动分析后，页面直接展示完整复盘报告结构。
2. ✅ ReviewDocument Preview 显示市场、情绪、题材、资金、股票、涨停分类、计划。
3. ✅ Workbench API 不再泄露 `emotion_review` / `chart_reviews` / `formal_review` / `recap_doc` 顶层字段。
4. ✅ 前端 contract 确认 `ReviewDocumentView` 不读取 `/api/emotion-*`、`/api/analyst-charts/*`、`/daily-review-v2`。

### PR3 — Override Editor

状态：⏳ Backend Completed / UI Next

交付：

1. ✅ `ReviewDocumentDiffService`
2. ✅ `GET /api/v1/analyst-workspace/{trade_date}/review-document-diff`
3. ✅ `ReviewOverride`
4. ✅ `ReviewOverrideApplier`
5. ✅ `GET/POST /api/v1/analyst-workspace/{trade_date}/review-overrides`
6. ✅ `review_overrides.json` 持久化，不写 Snapshot。
7. ⏳ 在 ReviewDocumentView 中支持编辑可校准字段。
8. ⏳ 页面实时显示 AI / Analyst / Final 三层值。

验收：

1. ✅ 后端可执行“人形机器人 -> PCB”。
2. ✅ 后端 final value 显示 PCB。
3. ✅ 刷新 GET workspace 后修改仍存在。
4. ✅ 同一 override 产生同一 hash。
5. ✅ 多 override 输入顺序不同，最终 hash 一致。
6. ✅ FACT 路径不能被 IDENTITY 等类型绕过修改。
7. ⏳ UI 可执行“人形机器人 -> PCB”。

PR3 UI 第一版只允许三类字段：

1. 主题身份：`themes[*].name`
2. 股票归属：`stocks[*].theme_name` / `stocks[*].subject_key`
3. 明日计划：`plan.watch_themes` / `plan.allowed_actions` / `plan.forbidden_actions`

禁止：

1. textarea JSON 编辑。
2. 保存完整 ReviewDocument。
3. 修改 Snapshot。
4. 接入 Approve。

### PR4 — Approve 绑定 + DailyReview 复用

状态：⏳ Pending

交付：

1. Approve 前运行 ReviewDocument quality gate。
2. 计算并保存 `final_review_document_hash`。
3. DailyReview API 只返回 approved `review_document`。
4. RecapPage 使用 `ReviewDocumentView(mode="readonly")`。
5. `FormalReviewView` 降级为兼容/调试入口。

验收：

1. Workbench 和 DailyReview 显示同一文档结构。
2. DailyReview 不读取 static chart/emotion JSON。
3. 7/9 AI: 人形机器人，Analyst: PCB，最终页面显示 PCB。
4. `final_review_document_hash` 可证明 Workbench Final 与 DailyReview Published 一致。

### PR5 — Legacy 删除

状态：⏳ Pending

交付：

1. 删除旧 Recap 二次拼装入口或隐藏到 debug。
2. 移除 formal/legacy 双轨 UI。
3. 新增 no-fallback contract tests。

验收：

1. Browser Network 无 `/api/emotion-{date}.json`。
2. Browser Network 无 `/api/analyst-charts/{date}.json`。
3. DailyReview 正式路径不消费 `recap_doc`。

---

## 10. 测试策略

### 10.1 单元测试

```text
test_review_document_assembler_schema.py
test_review_document_identity_override.py
test_review_document_quality_gate.py
test_review_document_limit_up_categories.py
test_review_document_capital_sources.py
```

### 10.2 集成测试

```text
test_workbench_review_document_flow.py
test_approve_review_document_snapshot.py
test_daily_review_reads_approved_review_document.py
```

### 10.3 7/9 Clean Replay 验收

必须按以下顺序：

1. 清理 2026-07-09 workbench/session/static JSON/DB legacy snapshot。
2. Workbench 启动分析。
3. 检查 ReviewDocument Draft：
   - market 不出现错误 0 值。
   - themes 不为空。
   - capital institution/hot_money 不为空或明确 MISSING。
   - limit_up.categories 不为空。
4. 修改主线：
   - AI: 人形机器人
   - Analyst: PCB
5. 保存并 Approve。
6. DailyReview 只读页面显示同一份 ReviewDocument。
7. 最终主题显示 PCB。

### 10.4 7/9 Golden Snapshot

新增固定黄金样本：

```text
docs/test_fixtures/review_document/2026-07-09-review-golden.json
```

用途：

1. 作为 Phase 4.5.7 的 ReviewDocument 语义验收基线。
2. 防止流程成功但核心业务内容缺失。
3. 防止旧链 fallback 让页面“看起来正常”。

Golden Snapshot 必须至少包含以下断言：

```json
{
  "trade_date": "2026-07-09",
  "market": {
    "limit_up_count": 75,
    "limit_down_count": 29,
    "up_count": 3561,
    "down_count": 1609
  },
  "emotion": {
    "phase": "REBOUND",
    "score": 39
  },
  "themes": {
    "must_include": ["存储芯片", "PCB", "机器人"]
  },
  "capital": {
    "institution_must_include": ["存储芯片", "半导体设备"],
    "hot_money_must_include": ["商业航天", "洪涝"]
  },
  "stocks": {
    "leader": {
      "stock_name": "恒尚节能",
      "board_height": 8
    }
  },
  "override": {
    "ai_value": "人形机器人",
    "analyst_value": "PCB",
    "final_value": "PCB"
  }
}
```

测试要求：

1. Golden Snapshot 是语义断言，不要求 JSON 全量逐字一致。
2. 字段缺失必须失败。
3. `up_count/down_count` 不允许以 `0` 代替缺失。
4. 资金方向缺失时必须失败或标记 BLOCKED，不能显示为空方向结论。

### 10.5 Golden Test Runner

新增脚本：

```text
scripts/verify_review_document.py
```

命令：

```bash
.venv/bin/python scripts/verify_review_document.py --date 2026-07-09
```

输出示例：

```text
ReviewDocument Validation

Market
  ✓ limit_up_count = 75
  ✓ limit_down_count = 29
  ✓ up_count = 3561
  ✓ down_count = 1609

Emotion
  ✓ phase = REBOUND
  ✓ score = 39

Themes
  ✓ includes PCB
  ✓ includes 人形机器人
  ✓ includes 存储芯片

Capital
  ✓ institution includes 存储芯片
  ✓ institution includes 半导体设备
  ✓ hot_money includes 商业航天
  ✓ hot_money includes 洪涝

Leader
  ✓ 恒尚节能 8板

Override
  ✓ 人形机器人 -> PCB

PASS
```

失败条件：

1. 任一 must_include 不存在。
2. FACT 字段缺失但输出 `0`。
3. `quality.overall=READY` 但 section 存在 blocking issue。
4. override final 与 analyst_value 不一致。

### 10.6 Negative Golden Tests

除 Golden 成功样本外，必须增加反例样本。

#### Negative 1：资金方向缺失

输入：

```json
{
  "capital": {
    "institution": [],
    "hot_money": []
  }
}
```

期望：

```json
{
  "quality": {
    "overall": "BLOCKED",
    "sections": {
      "capital": {
        "status": "MISSING"
      }
    }
  }
}
```

禁止输出：

```text
机构方向：共0个方向，多数调整
游资方向：游资正常
```

#### Negative 2：FACT 旧日期污染

输入：

```json
{
  "market": {
    "limit_up_count": 75,
    "source_trade_date": "2026-07-08"
  },
  "metadata": {
    "trade_date": "2026-07-09"
  }
}
```

期望：

```text
quality.overall = BLOCKED
reason = FACT source_trade_date mismatch
```

#### Negative 3：Override final 缺失

输入：

```json
{
  "ai_value": "人形机器人",
  "analyst_value": "PCB",
  "final_value": ""
}
```

期望：

```text
Approve blocked
reason = explicit override final_value missing
```

### 10.7 Legacy Leakage Tests

新增自动扫描测试，防止旧链路重新进入正式 ReviewDocument。

断言：

```python
assert "/api/emotion-" not in frontend_routes
assert "/api/analyst-charts/" not in frontend_routes
assert "recap_doc" not in review_document_assembler_source
assert "legacy" not in review_document_json
assert "formal_review" not in daily_review_formal_response
```

测试文件：

```text
test_review_document_legacy_leakage.py
```

要求：

1. 正式路径不允许读取 static emotion/chart JSON。
2. `ReviewDocumentAssembler` 不允许出现 `recap_doc`。
3. `ReviewDocument` 顶层不允许出现 `legacy`。
4. DailyReview 正式响应不允许并列返回 `formal_review`。

API Contract Test：

```python
response = client.get("/api/v2/daily-review-v2?date=2026-07-09")
payload = response.json()

assert "review_document" in payload
assert "formal_review" not in payload
assert "legacy" not in payload
assert "emotion_review" not in payload
assert "market_chart_reviews" not in payload
```

该测试必须覆盖真实 API 响应，而不是只扫描源码。

---

## 11. 风险与控制

| 风险 | 等级 | 描述 | 控制 |
|---|---|---|---|
| ReviewDocument 被误当真源 | P0 | 前端保存全量 document 导致 Snapshot 被绕过 | API 只接收 overrides，不接收全量 document |
| 旧 UI 继续显示 legacy | P0 | 用户看到新旧两套复盘 | DailyReview 优先 review_document；legacy 只 debug |
| 缺失数据被显示为 0 | P0 | 误导交易判断 | 缺失值统一 null + quality gate |
| override 统计污染 | P1 | M9 Learning 误学系统补齐字段 | audit 分类 explicit/system/compatibility |
| override 文件并发覆盖 | P1 | 多浏览器同时保存 `review_overrides.json`，旧版本覆盖新版本 | PR4 前引入 `version/base_version` 冲突检测 |
| override 绕过 FACT 保护 | P0 | 使用 IDENTITY/ASSESSMENT 修改事实字段 | `ReviewOverrideApplier` 阻止 FACT class 和 `market.*` 数值事实路径 |
| 组件过大 | P1 | ReviewDocumentView 难维护 | 按 section 拆组件 |
| 一次性删除 Projection 风险过高 | P1 | 回滚困难 | Phase 4.5.7 先引入 review_document，Projection 冻结不扩展 |

---

## 12. 决策记录

### D1 — 不再新增第二套 FormalReview UI

决策：

```text
Workbench 和 DailyReview 共用 ReviewDocumentView。
```

原因：

1. 分析师工作台本质是复盘报告编辑态。
2. 两套 UI 会再次制造字段漂移。
3. 同一组件能保证“审核看到什么，发布就是什么”。

### D2 — Snapshot 是唯一真源

决策：

```text
ReviewDocument 不入库为独立真源。
```

原因：

1. 避免 Snapshot 与 ReviewDocument 双写不一致。
2. ReviewDocument 可以随 schema 演进重建。
3. 审计和学习仍基于 Snapshot + overrides。

### D3 — ReviewDocumentAssembler 不做 fallback

决策：

```text
Assembler 缺数据时输出 quality=MISSING/DEGRADED，不从 legacy 猜。
```

原因：

1. fallback 会隐藏数据链断点。
2. 复盘报告是交易决策材料，错误 0 值比缺失更危险。
3. Clean Replay 必须暴露真实链路问题。

### D4 — Override 只保存字段级变更，不保存完整文档

决策：

```text
ReviewDocument Draft
  + ReviewOverride[]
  -> ReviewDocument Final
```

短期持久化：

```text
tmp/analyst_workbench/{trade_date}/review_overrides.json
```

原因：

1. 防止 ReviewDocument 被误当成第二真源。
2. 保留 AI / Analyst / Final 三层值，支撑审核和 M9 Learning。
3. Approve 时可以用 Snapshot + overrides 复现最终文档。
4. 删除 override 后应回到原始 draft hash，保证可复现。

当前风险：

1. JSON 文件未带 version，存在多浏览器并发覆盖风险。
2. PR4 前必须引入 `version/base_version`。
3. 长期可迁移到 `review_document_override` 数据库表，但 PR3/PR4 不做。

### D5 — PR3 不接 Approve

决策：

```text
PR3 只完成：
Draft -> Override -> Final Document

PR4 才完成：
Final Document -> Quality Gate -> Approve -> DailyReview
```

原因：

1. 避免 UI 编辑、审计、发布三个职责混在同一 PR。
2. PR3 的验收边界是 final document 可重建、hash 稳定、diff 可审计。
3. PR4 的验收边界是发布对象与 Workbench Final 一致。

---

## 13. 与 Phase 4.5.6 的关系

Phase 4.5.6 的 FormalReviewProjectionCompiler 已经证明了六章模型的价值，但它不应继续扩展为新的复杂中间层。

Phase 4.5.7 的处理方式：

1. 保留 FormalReviewProjectionCompiler 作为过渡兼容能力。
2. 不继续向 Projection Compiler 增加新字段。
3. 新的展示和编辑入口全部迁移到 ReviewDocument。
4. 当 ReviewDocument 通过 5 个交易日观察后，再决定是否下线 FormalReviewView。

### 13.1 FormalReviewProjectionCompiler 冻结原则

Phase 4.5.7 开始，FormalReviewProjectionCompiler 进入冻结状态。

允许：

1. bug fix。
2. 测试修复。
3. 与现有字段兼容相关的小修。

禁止：

1. 新增业务字段。
2. 新增业务逻辑。
3. 新增数据源。
4. 为了前端展示继续扩展 formal_review schema。
5. 把 ReviewDocument 中的新 section 回填到 FormalReviewProjectionCompiler。

原因：

```text
FormalReviewProjectionCompiler 继续增长
  -> DailyReview 再次出现第二套解释层
  -> Workbench 与 DailyReview 展示重新分叉
```

ReviewDocument 是 Phase 4.5.7 起唯一增长的复盘展示协议。

### 13.2 Frozen Modules Registry

建议新增：

```text
docs/architecture/FROZEN_MODULES.md
```

初始内容：

```text
Frozen:
  FormalReviewProjectionCompiler

Allowed:
  - bug fix
  - test fix
  - existing compatibility repair

Forbidden:
  - schema expansion
  - business logic addition
  - datasource addition
  - ReviewDocument section backfill
```

用途：

1. 给后续开发者明确冻结边界。
2. 避免“顺手给 FormalReview 加字段”。
3. Code review 时可直接引用该文档作为门禁。

本设计文档先记录该约束；是否在 PR1.1 同步创建 `FROZEN_MODULES.md` 由实施阶段决定。

---

## 14. 完成定义

Phase 4.5.7 完成条件：

1. ✅ Workbench 启动分析后直接展示 ReviewDocument。
2. ⏳ Workbench 和 DailyReview 使用同一个 `ReviewDocumentView`。
   - Workbench 已完成。
   - DailyReview 待 PR4。
3. ⏳ 2026-07-09 Clean Replay 通过：
   - 主题不丢。
   - 资金方向不空。
   - 涨停分类有题材清单。
   - 主线人工修改最终显示 PCB。
4. ⏳ DailyReview 正式路径不读取 static chart/emotion JSON。
5. ✅ Workbench 正式路径不读取 static chart/emotion JSON。
6. ✅ 缺失数据不会显示为业务 0。
7. ✅ explicit override 后端统计不再包含系统补齐字段。
8. ✅ ReviewDocument final hash 可复现。
9. ✅ ReviewOverride 输入顺序不影响 final hash。
10. ⏳ `review_overrides.json` 增加 version 并发控制。
11. ⏳ PR3 UI 支持主题身份、股票归属、明日计划三类 override。

PR3 UI 进入条件：

1. `GET /api/v1/analyst-workspace/{trade_date}` 返回 `review_document`。
2. `POST /api/v1/analyst-workspace/{trade_date}/review-overrides` 可保存 override。
3. `GET /api/v1/analyst-workspace/{trade_date}/review-document-diff` 可返回 AI / Analyst / Final diff。
4. 后端测试至少包含：
   - persistence round-trip。
   - invalid override rejection。
   - hash changes / hash restored。
   - override order stability。

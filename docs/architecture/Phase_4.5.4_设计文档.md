# Phase 4.5.4 — Daily Review Workbench Sections 设计文档

> 版本：v1.1
> 日期：2026-07-10
> 状态：Implemented
> 关联：`docs/architecture/分析师工作台设计方案.md` (M8.5) / `docs/architecture/M8_Market_Cognition_Engine_架构设计文档.md` (M8)

---

## 0. 问题陈述

### 0.1 当前状态

Phase 4.5.3 已建成三道门（生成门/审核门/报告门），`compose-from-workbench` 能返回 Approved Snapshot 的 `workbench_data`，但存在两个断层：

1. **结构断层**：`workbench_data` 是扁平 dict，没有拆成复盘报告的独立章节
2. **内容断层**：AIDraft / ReviewSnapshot 缺少 `emotion_review` 和 `chart_reviews` 字段，情绪和图表解读的数据承载位缺失

### 0.2 目标

复盘报告不应只展示市场数据加工结果，还应展示 **AI 与分析师共同确认后** 的市场情绪、图表解读、认知卡片、叙事链和交易剧本。这些内容必须来自 Approved Snapshot，而非临时读取 raw JSON。

---

## 1. 数据模型变更

### 1.1 AIDraft 增量

```python
@dataclass
class AIDraft:
    # ... 现有字段保留 ...

    # Phase 4.5.4 新增
    emotion_review: dict[str, Any] = field(default_factory=dict)
    chart_reviews: list[dict[str, Any]] = field(default_factory=list)
```

### 1.2 ReviewSnapshot 增量

```python
@dataclass
class ReviewSnapshot:
    # ... 现有字段保留 ...

    # Phase 4.5.4 新增
    emotion_review: dict[str, Any] = field(default_factory=dict)
    chart_reviews: list[dict[str, Any]] = field(default_factory=list)
```

### 1.3 ReviewSnapshot.from_draft() 同步

`from_draft()` 必须复制新增字段：

```python
emotion_review=draft.emotion_review,
chart_reviews=draft.chart_reviews,
```

兼容性：`from_dict()` 中 `d.get("emotion_review", {})` / `d.get("chart_reviews", [])` 确保旧 snapshot 可正常加载。

---

## 2. 新增 Builder：ChartReviewBuilder

### 2.1 输入

`frontend/public/api/analyst-charts/{date}.json` — 由 `POST /generate` Step 1 产出。

### 2.2 输出

```python
list[dict]  # market_chart_reviews[]
```

每个元素：

```python
{
    "chart_type": str,        # market_breadth / emotion_momentum / active_capital /
                              # relay_ecology / institution_style / hot_money_style
    "title": str,             # 中文标题
    "status": str,            # 状态标签（修复/改善/回流/退潮/...)
    "score": float | None,    # 综合评分
    "summary": str,           # 一句话解读
    "key_metrics": dict,      # 关键指标
    "evidence": list[str],    # 支撑证据
    "analyst_note": str,      # 分析师备注（初始为空，review 时填充）
    "source_quality": float,  # 数据质量
}
```

### 2.3 六类图表映射规则

| chart_type | title | 来源数据.字段 | status 判定 |
|---|---|---|---|
| `market_breadth` | 市场宽度 | up_count, limit_up_count, composite_score | score>=2→"活跃", >=-5→"中性", < -5→"收缩" |
| `emotion_momentum` | 情绪动能 | emotion_momentum_score, label | score>5→"亢奋", >0→"正常", >-5→"退潮", >=-10→"冰点" |
| `active_capital` | 活跃资金 | active_amount_yi, total_amount_yi, label | 基于 label + active/total 比率 |
| `relay_ecology` | 连板接力 | max_board_height, promotion_1_to_2, feedback_score | fb>0→"改善", fb<-10→"恶化", else→"中性" |
| `institution_style` | 机构风格 | directions[].name, directions[].state | 基于 majority state |
| `hot_money_style` | 游资风格 | directions[].name, directions[].state | 基于 majority state |

### 2.4 解读文本生成规则

第一版确定性规则（无 LLM）：

- `market_breadth`: "今日上涨{up_ratio}%，涨停{limit_up}家/跌停{limit_down}家，市场宽度{status}。"
- `emotion_momentum`: "情绪动能{score}，{label}。首板红盘比{fb_red}%，连板大面比{cl_loss}%。"
- `active_capital`: "活跃资金{active}亿，占全市场{ratio}%。{label}。"
- `relay_ecology`: "最高{max_h}板，1→2晋级率{p1to2}%。{fb_label}。"
- `institution_style` / `hot_money_style`: 列出前 3 个方向及其状态

---

## 3. 新增 Builder：EmotionReviewBuilder

### 3.1 输入

`frontend/public/api/emotion-{date}.json` — 由 `POST /generate` Step 2 产出。

### 3.2 输出

```python
{
    "emotion_node": str,         # ICE_POINT / REBOUND / FERMENTATION / ...
    "emotion_label": str,        # 中文标签（冰点/修复/发酵/...）
    "emotion_score": float,      # -100 ~ +100
    "risk_level": str,           # LOW / MEDIUM / HIGH / EXTREME
    "confidence": float,         # 0-1
    "summary": str,              # 2-3 句情绪总览
    "strategy_bias": str,        # 策略倾向
    "key_evidence": list[str],   # 关键证据
    "breadth_score": float,      # 赚钱效应分
    "breadth_label": str,
    "momentum_score": float,     # 情绪动能分
    "momentum_label": str,
    "relay_score": float,        # 接力生态分
    "relay_label": str,
    "capital_score": float,      # 资金面分
    "capital_label": str,
    "style_score": float,        # 风格偏好分
    "style_label": str,
    "analyst_adjustment": dict | None,  # 分析师修正（初始为 None）
    "source_quality": float,
    "missing_fields": list[str],
}
```

### 3.3 风险等级映射

| emotion_score 范围 | risk_level |
|---|---|
| > 40 | LOW |
| 10 ~ 40 | MEDIUM |
| -20 ~ 10 | HIGH |
| < -20 | EXTREME |

### 3.4 情绪节点标签映射

| emotion_node | emotion_label |
|---|---|
| ICE_POINT | 情绪冰点 |
| REBOUND | 情绪修复 |
| FERMENTATION | 情绪发酵 |
| ACCELERATION | 情绪加速 |
| CLIMAX | 情绪高潮 |
| DIVERGENCE | 情绪退潮 |
| FADE | 情绪衰退 |
| CHAOS | 情绪混沌 |

---

## 4. Draft Generator 改造

### 4.1 修改文件

`scripts/generate_analyst_workbench.py`

### 4.2 新增逻辑

```python
from stock_processing_service.application.services.analyst_workbench.chart_review_builder import (
    ChartReviewBuilder,
)
from stock_processing_service.application.services.analyst_workbench.emotion_review_builder import (
    EmotionReviewBuilder,
)

# 在读取 chart/emotion JSON 后：
if chart_path.exists():
    charts = json.loads(chart_path.read_text())
    draft.chart_reviews = ChartReviewBuilder().build(charts)
    draft.attention_state = {"charts_available": len(charts)}
    draft.cognition_cards = _build_cognition_cards(charts)

if emotion_path.exists():
    emo = json.loads(emotion_path.read_text())
    draft.emotion_review = EmotionReviewBuilder().build(emo)
    # 保留旧 narrative/playbook 兼容
    draft.narrative = {
        "emotion_node": emo.get("emotion_node", ""),
        ...
    }

# source_quality 考虑新字段
draft.source_quality = max(0.50, 1.0 - len(missing) * 0.15)
```

---

## 5. WorkbenchReportComposer 输出升级

### 5.1 修改文件

`stock_processing_service/application/services/analyst_workbench/report_composer.py`

### 5.2 新增一等章节

```python
report = {
    **engine_report,
    **approval_meta,

    # Phase 4.5.4: structured sections from approved snapshot
    "emotion_review": snapshot.emotion_review if snapshot else {},
    "market_chart_reviews": snapshot.chart_reviews if snapshot else [],
    "attention_review": snapshot.attention_state if snapshot else {},
    "cognition_reviews": snapshot.cognition_cards if snapshot else [],
    "narrative_review": snapshot.narrative if snapshot else {},
    "playbook_review": snapshot.playbook if snapshot else {},
    "analyst_override_review": snapshot.override_summary if snapshot else {},

    # 兼容保留
    "workbench_data": workbench_data,
}
```

---

## 6. DailyReviewV2Builder 契约补字段

### 6.1 修改文件

`stock_processing_service/application/services/post_market_daily_review_v2_builder.py`

### 6.2 新增 pass-through

```python
"emotion_review": self._pass_through(doc, "emotion_review", default={}),
"market_chart_reviews": self._pass_through(doc, "market_chart_reviews", default=[]),
"attention_review": self._pass_through(doc, "attention_review", default={}),
"cognition_reviews": self._pass_through(doc, "cognition_reviews", default=[]),
"narrative_review": self._pass_through(doc, "narrative_review", default={}),
"playbook_review": self._pass_through(doc, "playbook_review", default={}),
"analyst_override_review": self._pass_through(doc, "analyst_override_review", default={}),
```

`_pass_through` 定义：
```python
@staticmethod
def _pass_through(doc: dict, key: str, default=None):
    return doc.get(key, default)
```

---

## 7. 完整数据流

```
chart JSON + emotion JSON（由 POST /generate Step 1/2 产出）
        │
        ▼
generate_analyst_workbench.py（CLI / Step 3）
        │
        ├── ChartReviewBuilder.build(charts)   → draft.chart_reviews
        ├── EmotionReviewBuilder.build(emo)    → draft.emotion_review
        ├── _build_cognition_cards(charts)     → draft.cognition_cards
        └── old narrative/playbook             → draft.narrative / draft.playbook
        │
        ▼
AIDraft（draft_vN.json）
        │
        ├── Calibration（POST /calibrate）
        ├── Analyst Review（POST /save-review）
        │
        ▼
POST /approve
        │
        ▼
ReviewSnapshot.from_draft(draft)
  → copies emotion_review + chart_reviews + attention_state +
    cognition_cards + narrative + playbook + override_summary
        │
        ▼
snapshot.json（immutable）
        │
        ▼
POST /v2/daily-review-v2/compose-from-workbench
        │
        ├── require_formal() → gate check
        ├── load snapshot.json
        │
        ▼
WorkbenchReportComposer.compose()
  → emotion_review
  → market_chart_reviews
  → attention_review
  → cognition_reviews
  → narrative_review
  → playbook_review
  → analyst_override_review
        │
        ▼
DailyReviewV2Builder.build()
  → pass-through 6 个新字段
        │
        ▼
DailyReviewV2 Response
```

---

## 8. Phase 4.5.5 — Workbench First 职责归位设计

> 状态：Planned
> 目标：不新增 Orchestrator / Workflow Engine / Event Bus，仅收紧现有 Workbench、Approved Snapshot、DailyReviewV2 的职责边界。

### 8.1 阶段目标

Phase 4.5.5 的核心不是新增架构，而是完成一次 **Responsibility Alignment**：

```
Analyst Workbench
  -> 复盘动态数据生产
  -> AI Draft
  -> 分析师校准 / Review
  -> Approved Snapshot

DailyReview
  -> 只消费 Approved Snapshot
  -> 编译报告
  -> UI / Notion 展示
```

废弃旧职责：

```
DailyReview
  -> 生成动态数据
  -> 生成 AI 内容
  -> 生成最终报告
```

保留当前阶段边界：

- 不引入 `AnalystReviewOrchestrator`
- 不引入全自动复盘编排
- 不引入事件驱动 Pipeline
- 不引入 M9 Learning Loop
- 不新增数据库真源表；继续使用 JSON Snapshot

### 8.2 PR1 — Workbench Generate 接管动态复盘数据生产

#### 修改文件

- `stock_processing_service/api_app.py`
- 新增 `stock_processing_service/application/services/analyst_workbench/generate_service.py`
- 新增 `stock_processing_service/application/services/analyst_workbench/contracts.py`
- `stock_processing_service/application/use_cases/generate_post_market_derived_data.py`（复用，不改职责）

#### 当前问题

`RecapPage.handleStartPostMarketRecap()` 仍调用：

```text
generatePostMarketDerivedData()
-> generatePostMarketRecap()
-> generateDailyReviewV2()
```

同时 `/api/v1/analyst-workbench/{date}/generate` 已存在，导致 “当日复盘” 与 “分析师工作台” 两个入口都能生产同一批复盘动态数据。

#### 目标调用链

```text
POST /api/v1/analyst-workbench/{date}/generate
  -> AnalystWorkbenchGenerateService.generate(date)
       ├── DerivedDataUseCase.execute(force=true)
       ├── chart JSON / emotion JSON 生成
       └── DraftGenerator CLI
  -> DRAFT_READY
```

#### 组件边界

`generate_analyst_workbench.py` 仍然只负责“从已准备好的 chart/emotion JSON 生成 AIDraft”，不得直接调用 `PostMarketDerivedDataGenerateUseCase`。

`api_app.py` 只负责 HTTP 参数校验和调用 application service，不承载步骤编排。

新增薄 application service：

```python
class AnalystWorkbenchGenerateService:
    async def generate(self, trade_date: date, *, force: bool = True) -> WorkbenchGenerateResult:
        derived = await self._generate_derived_data(trade_date, force=force)
        if derived.status != "success":
            return WorkbenchGenerateResult.failed_precondition(...)

        charts = await self._generate_charts(trade_date)
        emotion = await self._generate_emotion(trade_date)
        draft = await self._generate_draft_from_files(trade_date)
        return WorkbenchGenerateResult(...)
```

这不是 Orchestrator。它不维护长期状态、不订阅事件、不做跨领域自动流程，只做当前 HTTP 请求内的同步能力组合。

#### 返回契约

新增 `contracts.py`：

```python
@dataclass(frozen=True, slots=True)
class WorkbenchGenerateResult:
    trade_date: str
    status: str  # completed | partial | failed | failed_precondition
    steps_completed: tuple[str, ...]
    derived_status: str
    draft_status: str
    missing_tables: tuple[str, ...]
    missing_fields: tuple[str, ...]
    source_quality: float
    error: str = ""
```

`POST /api/v1/analyst-workbench/{date}/generate` 只把该对象序列化为 JSON：

```json
{
  "steps_completed": ["derived_data", "charts", "emotion", "workbench"],
  "generation_steps": [
    {"step": "derived_data", "status": "success", "started_at": "...", "finished_at": "..."},
    {"step": "charts", "status": "success"},
    {"step": "emotion", "status": "success"},
    {"step": "draft", "status": "success"}
  ],
  "derived_data_status": "success|failed_precondition|failed",
  "missing_tables": []
}
```

`generation_steps` 同步写入 `WorkbenchSession.generation_steps`，用于分析师排查“启动分析”失败原因。该字段只记录步骤状态，不成为 derived data 真源。

#### 失败策略

- `derived_data` 失败：`status=failed_precondition`，不继续生成 AI Draft。
- `charts/emotion` 部分失败：保留现有 partial draft 策略，写入 `missing_fields`。
- `workbench CLI` 失败：状态为 `failed`，保留错误摘要。

### 8.3 PR2 — Approve 必须合并人工修改

#### 修改文件

- `stock_processing_service/api_app.py`
- 新增 `stock_processing_service/application/services/analyst_workbench/review_merger.py`
- 新增/扩展 `stock_processing_service/application/services/analyst_workbench/contracts.py`
- `stock_processing_service/application/services/analyst_workbench/snapshot.py`

#### 当前问题

分析师编辑结果保存到：

```text
tmp/analyst_workspace/{date}.json
tmp/analyst_overrides/{date}_workspace_overrides.jsonl
```

但 `approve_workbench()` 仍然执行：

```python
snapshot = ReviewSnapshot.from_draft(draft, overrides=...)
```

因此 Approved Snapshot 实际仍是 AI Draft，不是人工校准后的结果。

#### 目标流程

```text
AIDraft
  + Analyst Workspace State
  + Override Log
      ↓
AnalystReviewMerger.merge()
      ↓
ReviewSnapshot
      ↓
snapshot.json
```

#### 新增组件

```python
class AnalystReviewMerger:
    def merge(
        self,
        *,
        draft: AIDraft,
        workspace: dict[str, Any] | None,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...
```

输出契约：

```python
{
    "attention_state": dict,
    "cognition_cards": list[dict],
    "narrative": dict,
    "playbook": dict,
    "emotion_review": dict,
    "chart_reviews": list[dict],
    "override_summary": dict,
}
```

#### 合并规则

1. `emotion_review`、`chart_reviews` 默认来自 `AIDraft`。
2. `workspace.themes` 转换为 `cognition_cards`，优先级高于 `draft.cognition_cards`。
3. `workspace.watch_groups` 写入 `attention_state.watch_groups`。
4. `field_overrides` 和 `overrides` 聚合到 `override_summary`。
5. 分析师为空字段不覆盖 AI 非空字段，除非显式存在 `field_overrides[field]`。
6. AI 值与分析师值必须双轨保存，不允许只覆盖为 final 值。

双轨字段格式：

```json
{
  "field": "main_theme",
  "ai_value": "机器人",
  "analyst_value": "PCB",
  "final_value": "PCB",
  "override": true,
  "reason": "资金切换"
}
```

当字段未被分析师修改时：

```json
{
  "field": "main_theme",
  "ai_value": "机器人",
  "analyst_value": "",
  "final_value": "机器人",
  "override": false,
  "reason": ""
}
```

这条规则服务两个目标：

- 当前正式报告只读取 `final_value`。
- 后续 M9 Learning 可读取 `ai_value -> analyst_value` 作为学习样本。

#### `approve_workbench()` 改造

```python
workspace = _load_saved_analyst_workspace(trade_date)
merged = AnalystReviewMerger().merge(
    draft=draft,
    workspace=workspace,
    overrides=body.get("overrides", {}),
)
snapshot = ReviewSnapshot.from_merged(
    trade_date=td,
    draft=draft,
    merged=merged,
    snapshot_version=session.snapshot_version + 1,
    approved_by=body.get("approved_by", "analyst"),
)
```

`ReviewSnapshot.from_merged()` 只负责模型构造，不读取文件。

#### Snapshot 元数据增强

`ReviewSnapshot` 新增：

```python
approval_mode: str = "analyst_approved"  # preview | review | analyst_approved | published
source_mode: str = "analyst_workbench"   # preview | analyst_workbench
composition_mode: str = "formal"         # preview | formal | published
snapshot_hash: str = ""                  # canonical JSON hash
```

保存 snapshot 前必须基于 canonical JSON 计算 `snapshot_hash`。正式 compose 以该 hash 判断 snapshot 是否完整可审计。

### 8.4 PR3 — DailyReview 页面移除数据生产职责

#### 修改文件

- `frontend/src/routes/recap/RecapPage.tsx`
- `frontend/src/lib/api.ts`

#### 当前问题

`handleStartPostMarketRecap()` 同时做数据准备、snapshot 重建、V2 生成、页面刷新。

#### 目标职责

当日复盘页面只负责：

```text
检查 report availability
-> 读取 DailyReviewV2
-> 展示 UI
-> 发布 Notion
```

不再调用：

```typescript
generatePostMarketDerivedData(tradeDate, true)
```

#### 前端按钮调整

- “启动分析” 只保留在 `AnalystWorkspacePage`。
- “生成复盘报告” 可保留在 Workbench，也可跳转到 Recap 页后触发正式 compose。
- Recap 页的“重新复盘”如保留，必须只执行 `read_model_only` 报告编译，不得触发 derived data rebuild。

### 8.5 PR4 — compose-from-workbench 成为唯一正式入口

#### 修改文件

- `stock_processing_service/api_app.py`
- `stock_processing_service/application/services/analyst_workbench/report_composer.py`

#### 当前问题

`GET /api/v2/daily-review-v2` 会通过 `_enrich_v2_with_workbench_sections()` 在 draft 比 snapshot 更新时注入 draft，适合预览但不适合正式报告。

#### 接口分层

Preview：

```text
GET /api/v2/daily-review-v2
```

允许读取 draft / snapshot，用于页面预览和分析师编辑期查看。

Production Compose：

```text
POST /api/v2/daily-review-v2/compose-from-workbench
```

强制规则：

- 必须 `ApprovalGate.require_formal()` 通过；
- 只能读取 `tmp/analyst_workbench/{date}/snapshot.json`；
- 禁止 draft fallback；
- 禁止读取 `tmp/analyst_workspace/{date}.json`；
- 返回体必须带 `workbench_approval.mode=formal|published`。
- 必须断言 `snapshot.approved is True`。
- 必须断言 `snapshot.approval_mode == "analyst_approved"` 或 session 为 `PUBLISHED`。
- 必须断言 `snapshot.source_mode == "analyst_workbench"`。
- 必须断言 `snapshot.composition_mode == "formal"`。
- 必须断言 `snapshot.snapshot_hash` 非空。
- 若 hash 缺失或校验失败，返回 409，不生成 formal report。

#### 报告生成流程

前端“生成复盘报告”按钮执行：

```text
1. GET /api/v1/analyst-workbench/{date}/report-approval
2. 若 can_generate_report=false，提示先审核通过
3. POST /api/v2/post-market/recap/generate
   body: { trade_date, force: false, mode: "read_model_only" }
4. POST /api/v2/daily-review-v2/compose-from-workbench
5. 跳转 /recap?date=...
```

注意：当前阶段禁止默认 `force=true`，避免在人工确认后重新触发事实重建。

### 8.6 PR5 — 测试设计

| TC-ID | 覆盖目标 | 测试文件建议 | 断言 |
|---|---|---|---|
| `TC-P455-01` | Workbench generate 接管 derived data | `stock_processing_service/tests/unit/test_workbench_phase455_generate.py` | `steps_completed` 包含 `derived_data`；derived data 失败时不生成 draft |
| `TC-P455-02` | Approve 合并人工修改 | `stock_processing_service/tests/unit/test_workbench_phase455_review_merger.py` | 修改后的 theme / narrative / override_summary 出现在 `snapshot.json` |
| `TC-P455-03` | 正式 compose 禁止 draft fallback | `stock_processing_service/tests/unit/test_workbench_phase455_compose_gate.py` | draft_v2 比 snapshot 新时，compose 仍使用 snapshot_v1 |
| `TC-P455-04` | DailyReview 不再生产 derived data | `frontend/scripts/test-recap-workbench-first-contract.mjs` | Recap 页流程不调用 `/post-market/derived-data/generate` |
| `TC-P455-05` | read_model_only 报告生成 | `stock_processing_service/tests/unit/test_workbench_phase455_report_generate.py` | `force=false` + `mode=read_model_only` 不触发 full truth rebuild |
| `TC-P455-06` | 生命周期职责边界 | `stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py` | `DRAFT_READY` 禁止 formal compose；`APPROVED` 后 generate 不覆盖 snapshot |
| `TC-P455-E2E` | AI Draft → Analyst Correction → Approved Snapshot → Final Report | `stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py` | AI 主线=机器人，分析师改为 PCB，snapshot 与报告最终均为 PCB |

必跑命令：

```bash
pytest stock_processing_service/tests/unit/test_workbench_phase455_generate.py
pytest stock_processing_service/tests/unit/test_workbench_phase455_review_merger.py
pytest stock_processing_service/tests/unit/test_workbench_phase455_compose_gate.py
pytest stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py
node frontend/scripts/test-recap-workbench-first-contract.mjs
```

#### E2E 验收场景

```text
Given:
  AI Draft 判断 main_theme = 机器人
  分析师在 workspace 中修改 main_theme = PCB
  修改原因 = 资金从机器人切换

When:
  approve_workbench()
  compose-from-workbench()

Then:
  snapshot.cognition_cards[].main_theme.ai_value == 机器人
  snapshot.cognition_cards[].main_theme.analyst_value == PCB
  snapshot.cognition_cards[].main_theme.final_value == PCB
  final report 展示 PCB，不展示机器人作为最终主线
```

### 8.6.1 实施顺序

实际开发按风险优先排序：

1. PR2：先实现 `AnalystReviewMerger + approve_workbench`，修复人工修改丢失。
2. PR4：锁定 `compose-from-workbench` 的 snapshot-only formal gate。
3. PR1：迁移动态复盘数据生产入口到 Workbench generate service。
4. PR3：前端移除 DailyReview 侧 derived data 生产入口。
5. PR5：补齐单元、契约和 E2E 测试。

### 8.7 回滚策略

| 改造项 | 回滚方式 |
|---|---|
| Workbench generate 接管 derived data | 临时关闭 Step 0，恢复仅 charts/emotion/draft |
| Approve merge | 回退到 `ReviewSnapshot.from_draft()`，但必须标记报告为 preview，不允许 formal publish |
| Recap 页移除 derived data | 恢复按钮调用，但只作为 emergency fallback，并显示非正式入口提示 |
| compose strict gate | 回退到 preview GET，不允许 Notion 正式发布 |

### 8.8 非目标范围

- 不做全自动收盘后触发。
- 不做新数据库表持久化。
- 不做 M9 Learning / 自动权重更新。
- 不做 Event Bus / Workflow Engine。
- 不把 DailyReviewV2 变成 M8 真源。

---

## 9. 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | AIDraft 包含 `emotion_review` + `chart_reviews` | 运行 generate CLI，检查 draft JSON |
| 2 | ReviewSnapshot 包含 `emotion_review` + `chart_reviews` | approve 后检查 snapshot.json |
| 3 | approve 后 snapshot 中可看到情绪与图表章节 | 读取 snapshot.json |
| 4 | compose-from-workbench 返回 `emotion_review` / `market_chart_reviews` | 调用 API 检查响应 |
| 5 | 未 approved 时 compose 仍 409 | DRAFT_READY 时调用 compose |
| 6 | regenerate draft_v2 不影响 snapshot_v1 内容 | 重新 generate 后检查 snapshot |
| 7 | 旧 daily-review-v2 保留 workbench_approval metadata | 调用 GET 检查 |
| 8 | 18 个现有 workbench 测试全部通过 | pytest |
| 9 | from_dict 向后兼容（旧 snapshot 无新字段仍可加载） | 测试旧格式 JSON |
| 10 | Workbench generate 先生成动态复盘数据 | 调用 `/analyst-workbench/{date}/generate`，检查 `steps_completed` |
| 11 | Approved Snapshot 包含人工修改后的认知卡片 | 修改 workspace 后 approve，读取 `snapshot.json` |
| 12 | compose-from-workbench 不消费 draft fallback | 生成 draft_v2 后 compose，确认输出仍来自 approved snapshot |

---

## 10. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `stock_processing_service/application/services/analyst_workbench/draft.py` | 修改 | 新增 2 字段 |
| `stock_processing_service/application/services/analyst_workbench/snapshot.py` | 修改 | 新增 2 字段 + from_draft 复制 |
| `stock_processing_service/application/services/analyst_workbench/contracts.py` | **新增** | WorkbenchGenerateResult / merge 输出契约 |
| `stock_processing_service/application/services/analyst_workbench/generate_service.py` | **新增** | 薄 application service，组合 derived data + draft 生成 |
| `stock_processing_service/application/services/analyst_workbench/review_merger.py` | **新增** | Phase 4.5.5 合并 AI Draft 与人工 Review |
| `stock_processing_service/application/services/analyst_workbench/chart_review_builder.py` | **新增** | ChartReviewBuilder |
| `stock_processing_service/application/services/analyst_workbench/emotion_review_builder.py` | **新增** | EmotionReviewBuilder |
| `scripts/generate_analyst_workbench.py` | 修改 | 调用 Builder 写入新字段 |
| `stock_processing_service/application/services/analyst_workbench/report_composer.py` | 修改 | 输出一等章节 |
| `stock_processing_service/application/services/post_market_daily_review_v2_builder.py` | 修改 | pass-through 新字段 |
| `frontend/src/routes/recap/RecapPage.tsx` | 修改 | 移除 derived data 生产入口 |
| `stock_processing_service/tests/unit/test_workbench_phase454.py` | **新增** | 验收测试 |
| `stock_processing_service/tests/unit/test_workbench_phase455_*.py` | **新增** | 职责归位测试 |

---

## 11. 风险与边界

| 风险 | 缓解 |
|------|------|
| 旧 snapshot 缺少新字段导致 from_dict 崩溃 | `d.get("emotion_review", {})` 兜底默认值 |
| ChartReviewBuilder 解读质量不足 | 第一阶段确定性规则，第二阶段再引入 LLM 增强 |
| 前端尚未适配新字段 | 新字段为增量追加，不改变现有字段语义 |
| generate CLI 失败回滚 | Builder 异常时写 `missing_fields`，不阻断 generate |
| Approved Snapshot 仍遗漏人工修改 | `AnalystReviewMerger` 单测覆盖 workspace → snapshot |
| draft 覆盖正式报告 | compose-from-workbench strict gate 禁止 draft fallback |

---

## 12. 不在此阶段实施

- ❌ LLM 增强图表/情绪解读文本
- ❌ 数据库持久化（Phase 4.5.2 已明确列为下一阶段）
- ❌ AnalystReviewOrchestrator / Workflow Engine / Event Bus
- ❌ 自动触发复盘与自动发布
- ❌ M9 Learning Loop

---

## 13. 实施状态（2026-07-10 更新）

### Phase 4.5.4 ✅ 已实现

- AIDraft / ReviewSnapshot 新增 `emotion_review` + `chart_reviews` 字段
- ChartReviewBuilder（6 类图表确定性解读）
- EmotionReviewBuilder（情绪结构化投影）
- Draft Generator 写入新字段
- WorkbenchReportComposer 输出 7 个一等章节
- DailyReviewV2Builder pass-through
- 旧 draft/snapshot 向后兼容（`d.get()` 兜底）

### Phase 4.5.5-UI ✅ 已实现

- 程序员工作台 `EmotionDashboard` 读取校准后数据
- `WorkbenchSectionsPanel`：复盘报告页渲染 7 个章节
- 阶段标签彩色药丸 + 风险等级中文映射
- 4 列布局：为什么/明日预测概率/今日交易模式/明日操作提示
- `fetchTomorrow()` prop 驱动（无异步闪烁）

### Phase 4.5.5-RA ✅ Completed

- Workbench generate 接管动态复盘数据生产 ✅ 已实现（PR1）
- Approve 合并 `AIDraft + analyst_workspace + overrides` ✅ 已实现（PR2）
- DailyReview 页面移除 derived data 生产入口 ✅ 已实现（PR3）
- `compose-from-workbench` 成为唯一正式报告入口 ✅ 已实现（PR4）
- 正式报告禁止 draft fallback ✅ 已实现（PR4）
- 职责防回归测试 / Phase 4.5.5-RA Final Review ✅ 已实现（PR5）

Known issue（不阻塞 Phase 4.5.5-RA）：`npm run build` 仍因既有 `AnalystWorkspacePage.tsx` 与 `EmotionDashboard.tsx` TypeScript 类型债失败；本阶段修改后的 `RecapPage.tsx` 已无新增 build error。建议单独建立 `Frontend Type Cleanup` 任务处理。

### Phase 4.5.5.1-UI ✅ 已实现

- 情绪/图表数据为空时显示占位提示
- preview 模式显示"待分析师审核"
- blocked 模式显示红色异常提示
- 低质量数据提醒（source_quality < 0.6）

### Phase 4.5.6-P0 ✅ 已实现

- 禁用 `subject_stock_daily_snapshot` 临时聚合
- **TDX MarketBreadthProvider**：通过 mootdx 从 TDX 获取全市场 A 股行情
- 全市场涨跌计算：`price > last_close → up`
- 覆盖 5404 只 A 股（SZ+SH，过滤非 A 股编码）
- 覆盖率 < 95% 时返回 None，不进入正式指标
- 7/10 结果：up=3561 down=1609 (THS: 3772/1678, diff 5%)

### MarketBreadthSourceRegistry

| 指标 | a-stock-data | 可用源 | 结论 |
|------|-------------|--------|------|
| 涨停数 | ✅ | Eastmoney ZT Pool | 可直接用 |
| 跌停数 | ✅ | Eastmoney DT Pool | 可直接用 |
| 炸板数 | ✅ | Eastmoney ZB Pool | 可直接用 |
| 昨涨停反馈 | ✅ | YZT + ZT/ZB/DT | 可直接用 |
| 行业涨跌家数 | ✅ | industry_comparison f104/f105 | 仅行业层 |
| 全市场涨跌家数 | ❌ 无端点 | TDX/mootdx → TdxMarketBreadthProvider | P2 源 |

### 源优先级

```
P0 同花顺市场统计端点（待发现）
P1 东财全 A 实时行情 clist（API 已确认 5537 只，但被限频）
P2 TDX/mootdx 全市场 quotes 批量计算 ✅ 当前使用
P3 subject_stock_daily_snapshot ❌ 已禁用
```

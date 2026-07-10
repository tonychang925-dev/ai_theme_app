# Phase 4.5.4 — Daily Review Workbench Sections 设计文档

> 版本：v1.0
> 日期：2026-07-10
> 状态：Design Review
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

## 8. 验收标准

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

---

## 9. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `stock_processing_service/application/services/analyst_workbench/draft.py` | 修改 | 新增 2 字段 |
| `stock_processing_service/application/services/analyst_workbench/snapshot.py` | 修改 | 新增 2 字段 + from_draft 复制 |
| `stock_processing_service/application/services/analyst_workbench/chart_review_builder.py` | **新增** | ChartReviewBuilder |
| `stock_processing_service/application/services/analyst_workbench/emotion_review_builder.py` | **新增** | EmotionReviewBuilder |
| `scripts/generate_analyst_workbench.py` | 修改 | 调用 Builder 写入新字段 |
| `stock_processing_service/application/services/analyst_workbench/report_composer.py` | 修改 | 输出一等章节 |
| `stock_processing_service/application/services/post_market_daily_review_v2_builder.py` | 修改 | pass-through 新字段 |
| `stock_processing_service/tests/unit/test_workbench_phase454.py` | **新增** | 验收测试 |

---

## 10. 风险与边界

| 风险 | 缓解 |
|------|------|
| 旧 snapshot 缺少新字段导致 from_dict 崩溃 | `d.get("emotion_review", {})` 兜底默认值 |
| ChartReviewBuilder 解读质量不足 | 第一阶段确定性规则，第二阶段再引入 LLM 增强 |
| 前端尚未适配新字段 | 新字段为增量追加，不改变现有字段语义 |
| generate CLI 失败回滚 | Builder 异常时写 `missing_fields`，不阻断 generate |

---

## 11. 不在此阶段实施

- ❌ 前端复盘页面渲染新章节（后续 Phase 4.5.5）
- ❌ LLM 增强图表/情绪解读文本
- ❌ 数据库持久化（Phase 4.5.2 已明确列为下一阶段）
- ❌ Notion 报告模板更新

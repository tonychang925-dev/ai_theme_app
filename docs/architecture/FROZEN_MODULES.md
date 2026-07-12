# Frozen Modules Registry

> 版本：v0.3
> 日期：2026-07-12
> 状态：Active
> 目的：冻结迁移期模块 + Snapshot Producer 约束

---

## 1. Frozen Modules

### 1.1 FormalReviewProjectionCompiler

```
stock_processing_service/application/services/daily_review/formal_review_projection_compiler.py
stock_processing_service/application/services/daily_review/projections/*
```

**允许**: bug fix, test fix, 兼容修复
**禁止**: schema 扩展, 新业务字段, 新数据源, ReviewDocument section 回填

---

## 2. Snapshot Producer Constraints

所有 `analyst_workbench/` 下的模块：

**允许**:
- 字段重命名 (`row["theme_name"] → entry.name`)
- 字段复制 (`entry.score = row["mainline_strength_score"]`)
- 类型转换 (`int(row["count"])`)
- null 保留 (缺失 → `None`, 不伪造 `0` 或 `""`)

**禁止**:
- 分类推断 (`if stage == "fermentation": institution`)
- 业务过滤 (`if name.startswith("【"): continue`)
- 从 stage/score 推理方向
- 硬编码过滤名单 (`_NOISE_PATTERNS = ("SpaceX", ...)`)
- fallback (`if not x: x = y`)
- 为显示质量丢弃数据
- 业务规则计算 (`confidence = min(0.85, score/100 + 0.15)`)

**缺失数据处理**: 源数据缺失 → `quality=MISSING`，不伪造，不推断，不 fallback。

---

## 3. API Contract

`GET /api/v1/analyst-workspace/{date}`:
- **允许**: `review_document`, `metadata`, `diagnostics`
- **禁止**: `emotion_review`, `chart_reviews`, `chart_data`, `formal_review`, `recap_doc`, `trend_data`

---

## 4. ReviewDocument Growth Path

增长位置: `ReviewDocument schema` → `ContextFactory` → `Assembler` → `Override` → `View`

禁止增长: `FormalReviewProjectionCompiler`, `legacy recap_doc`, `static emotion/chart JSON`, `DailyReview二次拼装`

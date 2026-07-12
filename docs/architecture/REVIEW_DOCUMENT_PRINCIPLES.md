# ReviewDocument Principles

> 版本：v0.1  
> 日期：2026-07-11  
> 状态：Active  
> 目的：记录 Phase 4.5.7 起复盘报告系统的最高原则，作为实现和 code review 的约束。

---

## P1. Snapshot Single Source of Truth

ReviewSnapshot 是唯一真源。

ReviewDocument 不入库为新的真源，只是展示协议。

---

## P2. Single Interpretation Principle

一个业务事实只能存在一个最终解释入口。

```text
Snapshot.emotion_review
  -> ReviewDocument.emotion
  -> Workbench / DailyReview
```

禁止：

```text
emotion_review
formal_review.emotion
static emotion json
legacy emotion
```

并列解释同一事实。

---

## P3. Assembler No Business Logic

ReviewDocumentAssembler 只做：

1. 字段映射。
2. 格式转换。
3. explicit override 合并。
4. source trace。
5. quality 标记。

禁止：

1. 判断。
2. 推理。
3. 补数据。
4. fallback。
5. 重新计算指标。

---

## P4. No Legacy Fallback

正式路径禁止使用：

1. `recap_doc`
2. static emotion JSON
3. static analyst chart JSON
4. legacy DailyReview fields
5. compatibility blob

缺失数据必须暴露为 `quality=MISSING / DEGRADED / BLOCKED`。

---

## P5. Missing Data Is Better Than Wrong Data

金融复盘系统中，错误事实比缺失事实更危险。

规则：

1. 缺失值使用 `null`。
2. 缺失 section 使用 `quality=MISSING`。
3. 不允许用 `0` 表示未知。
4. 不允许用空列表生成业务结论。

---

## P6. Field Provenance Is Required

进入 ReviewDocument 的字段必须有 `field_provenance`。

字段血缘至少包含：

1. source。
2. field_type。
3. transform。
4. validation_status。
5. source_trade_date。
6. source_generated_at。

---

## P7. Workbench And DailyReview Share One View

Workbench 是 ReviewDocument 的编辑态。

DailyReview 是 ReviewDocument 的只读态。

禁止两套复盘报告 UI。

---

## P8. Override Is Field-Level Only

分析师修改必须保存为字段级 `ReviewOverride`。

允许保存：

1. `field_path`
2. `field_class`
3. `ai_value`
4. `analyst_value`
5. `final_value`
6. `reason`
7. `author`
8. `timestamp`

禁止保存：

1. 完整 ReviewDocument。
2. 被前端直接修改后的 Snapshot。
3. 任意 JSON textarea 结果。

规则：

```text
ReviewDocument Draft
  + ReviewOverride[]
  -> ReviewDocument Final
```

---

## P9. Facts Cannot Be Overridden Through Assessment Channels

FACT 字段不能通过 `IDENTITY` / `ASSESSMENT` / `PLAN` override 绕过保护。

当前强约束：

1. `field_class=FACT` 的 override 直接拒绝。
2. `market.*` 数值事实路径直接拒绝。
3. 后续若允许事实修正，必须走单独的 data correction flow，不进入 ReviewOverride。

---

## P10. Override Persistence Must Be Versioned Before Approve

短期允许：

```text
tmp/analyst_workbench/{trade_date}/review_overrides.json
```

PR4 前必须增加：

1. `version`
2. `updated_at`
3. `base_version` 保存校验

目标：

防止多浏览器或多操作者并发保存时，旧版本覆盖新版本。

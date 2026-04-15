---
name: prd-doc
description: 生成或修订 PRD 文档，确保需求、约束、验收标准可追溯且可执行。
when_to_use: 当用户要求编写/完善 PRD，或将口头需求沉淀为结构化文档时使用。
model: inherit
effort: high
---

# PRD 文档协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

## 1. 输出

1. `docs/project_control/PRD.md`（主文档）
2. `tmp/prd_traceability.json`（需求-验收映射）
3. `tmp/prd_validation_report.json`（结构校验）

## 2. 必须包含章节

1. 背景与目标
2. 范围（In Scope / Out of Scope）
3. 关键用户场景
4. 功能需求（编号化）
5. 非功能需求（性能/稳定性/安全）
6. 约束与依赖
7. 风险与回滚策略
8. 验收标准（可测试、二元可判定）

## 3. 质量要求

1. 每条功能需求必须有唯一 ID（如 `FR-001`）。
2. 每条验收标准必须能映射到至少一个测试动作（命令或 TC-ID）。
3. 禁止模糊语句（例如“尽量快”“体验更好”）作为验收依据。

## 4. 冲突处理

多文档输入冲突时，必须记录：
- 冲突项
- 采用来源
- 放弃来源
- 裁决理由

## 5. 去耦规则

1. 不依赖任何外部 PM 平台字段。
2. 不在 PRD 中写入平台特定同步命令。

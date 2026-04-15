---
name: arch-review
description: 分析当前架构、输出风险矩阵与可执行迁移建议，生成 ADR 清单。
when_to_use: 当用户要求架构评审、风险识别、迁移路线或 ADR 建议时使用。
model: inherit
effort: high
---

# 架构评审协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

## 1. 目标

输出“可执行”评审结论，不做空泛建议。

## 2. 输入优先级

1. `docs/project_control/PRD*.md`
2. `docs/project_control/ACCEPTANCE*.md`
3. `docs/architecture/*`
4. `docs/project_control/PLAN_WBS*.md`
5. `docs/adrs/*`

## 3. 输出文件

1. `docs/project_control/ARCH_REVIEW.md`
2. `docs/adrs/ADR_LIST.md`
3. `tmp/arch_review_payload.json`

## 4. 结构要求

`ARCH_REVIEW.md` 必须包含：
- 当前架构摘要
- 风险矩阵（P0/P1/P2）
- 目标架构
- 迁移计划
- 冲突裁决记录
- 非目标范围

## 5. ADR 要求

每条 ADR 至少包含：
- id
- context
- decision
- alternatives
- consequences
- trigger

## 6. 禁止项

1. 不改业务代码。
2. 不直接调用外部 PM/任务系统 API。
3. 不写入密钥。

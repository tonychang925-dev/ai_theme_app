---
name: test-case
description: 生成分阶段测试用例规范、覆盖矩阵与执行顺序，支撑质量门禁与验收（去外部系统耦合版）。
when_to_use: 当用户要求测试用例文档、测试规范、UT/IT/E2E 设计或阶段测试清单时使用。
model: inherit
effort: high
---

# 测试用例规范协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

## 1. 目标

输出结构化、可执行、可审计的测试用例文档，作为阶段交付真源。

## 2. 输入优先级

1. `docs/project_control/PRD*.md`
2. `docs/project_control/ACCEPTANCE*.md`
3. `docs/project_control/PLAN_WBS*.md`
4. 相关模块设计文档与 ADR

## 3. 输出文件

1. 分阶段优先：`docs/project_control/TEST_CASE_SPEC_<phase>.md`
2. 项目总表（仅用户要求时）：`docs/project_control/TEST_CASE_SPEC.md`
3. 可选结构化产物：`tmp/test_case_payload.json`

## 4. 强制内容

测试规范必须包含：
- 需求到测试映射矩阵（Requirement -> TC-ID）
- 测试层级与阻塞规则（UT -> IT -> ST/E2E）
- 核心路径与异常路径覆盖
- 失败判定标准（FAILED/BLOCKED）
- 证据要求（日志/trace/request-id）

## 5. 执行顺序规则

1. 先 UT，再 IT，再 ST/E2E。
2. 下游依赖未通过，上游集成测试必须标记 `BLOCKED`。
3. 不允许仅靠模拟数据证明核心链路通过（除非需求明确允许）。

## 6. 与 QA Gate 对齐

1. P0 需求必须有 P0 用例。
2. 每个需求至少 1 条可执行测试。
3. 关键路径必须有集成测试。
4. 必须给出建议必跑命令（按 UT -> IT -> ST/E2E 顺序）。

## 7. 禁止项

1. 不改业务代码。
2. 不伪造通过结果。
3. 不把外部系统同步状态当作测试通过依据。

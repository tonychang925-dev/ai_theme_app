---
name: arch-review
description: 当用户要求“分析现有架构设计、识别风险、给出优化方案与ADR清单”时使用；此阶段默认只读，不改代码。
---

# Architecture Review Flow

## Inputs
- docs/ 下的架构设计、目录结构、关键模块说明
- 当前技术栈、约束（性能/成本/可维护性/团队习惯）

## Outputs (must)
1) docs/project_control/ARCH_REVIEW.md
2) adrs/ADR_LIST.md（拟新增 ADR 清单）
3) Phase 划分建议（Phase0..N）+ 里程碑建议

## Review Dimensions
- 边界清晰：服务/模块职责是否单一、依赖是否可控
- 数据流：数据源->采集->理解->题材->输出 是否有断点/重复
- 可测试性：关键逻辑是否可单测/可回放
- 可观测性：日志、trace、指标、回放机制
- 演进性：schema/接口版本化、兼容策略
- 风险：性能瓶颈、数据一致性、幂等、延迟、成本、复杂度

## Format for ARCH_REVIEW.md
- Current Architecture Summary
- Issues & Risks (ranked)
- Recommended Target Architecture (modules + boundaries)
- Migration Plan (phased)
- ADR proposals (list)

# WBS 执行子集（P1.phase2）

## 目标
在不进入编码实施（STEP2）的前提下，完成 phase2 的任务规划、测试设计与 feature 设计输入。

## 任务子集

| Task ID | 任务描述 | Depends On | 风险 | DoD |
| --- | --- | --- | --- | --- |
| P1.phase2-T01 | 动态阈值 profile + 三段分层策略 | P1.phase1-T05 | High | 策略可配置、指标可观测 |
| P1.phase2-T02 | 候选窗口治理（3~30）与爆炸比监控 | P1.phase2-T01 | High | 候选窗口稳定、爆炸比可审计 |
| P1.phase2-T03 | 分类真源复用，移除二次 `_match_categories` 推断 | P1.phase2-T01 | High | 创建阶段不再二次分类 |
| P1.phase2-T04 | ADR 与设计评审归档 | P1.phase2-T03 | Medium | ADR 与评审证据完整 |
| P1.phase2-T05 | 76 案例 A/B + 三方对比（含 real 调用证据） | P1.phase2-T02 | High | 报告满足 phase2 验收指标 |

## 执行顺序（进入 STEP2 后）
T01 -> (T02 并行 T03) -> T04 -> T05

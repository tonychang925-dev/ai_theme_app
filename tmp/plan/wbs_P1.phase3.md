# WBS 执行子集（P1.phase3）

## 目标
在进入实现循环（STEP2）前，冻结 P1.phase3 的任务边界、顺序与依赖，执行范围限定在自动链路验收。

## 任务子集

| Task ID | 任务描述 | Depends On | 风险 | DoD |
| --- | --- | --- | --- | --- |
| P1.phase3-T01 | 定义分类命中后全量LLM复核、回退策略与裁判契约字段 | P1.phase2-T05 | High | 全量复核与回退规则可机读 |
| P1.phase3-T02 | 接入裁判客户端并实现超时/不可用降级与熔断 | P1.phase3-T01 | High | timeout/model_unavailable 可受控处理 |
| P1.phase3-T03 | 落地10%灰度、裁决比例门禁与证据汇总报告 | P1.phase3-T02 | High | 比例/证据门禁可执行 |
| P1.phase3-T04 | 完成时延/成本/real_call_ratio 门禁配置与评审 | P1.phase3-T03 | Medium | 门禁阈值与告警策略可审计 |

## 二级分解（新增，进入 STEP2 的实际执行单元）

| Subtask ID | 所属任务 | 子任务描述 | Depends On | 对应 feature 子功能 | 优先级 | DoD |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase3-T01-S01 | P1.phase3-T01 | 固化“分类命中后全量复核”触发规则与原因码 | - | F-P1.phase3-T01-01 | P0 | `need_judge/judge_trigger_reason` 可观测 |
| P1.phase3-T01-S02 | P1.phase3-T01 | 固化超时/异常统一回退策略与原因码枚举 | P1.phase3-T01-S01 | F-P1.phase3-T01-02 | P0 | `fallback_reason` 与回退路径一致 |
| P1.phase3-T01-S03 | P1.phase3-T01 | 冻结裁判契约字段并接入 schema 校验 | P1.phase3-T01-S02 | F-P1.phase3-T01-03 | P0 | 缺字段样本被拒绝执行 |
| P1.phase3-T02-S01 | P1.phase3-T02 | 接入 LLM 裁判客户端并解析响应字段 | P1.phase3-T01-S03 | F-P1.phase3-T02-01 | P0 | 返回 `decision/confidence/request_id/model_name` |
| P1.phase3-T02-S02 | P1.phase3-T02 | 实现超时快速回退且不阻塞主链路 | P1.phase3-T02-S01 | F-P1.phase3-T02-02 | P0 | `timeout_fallback` 可验证 |
| P1.phase3-T02-S03 | P1.phase3-T02 | 实现 model_unavailable 熔断与短路保护 | P1.phase3-T02-S02 | F-P1.phase3-T02-03 | P1 | `circuit_state` 状态机可验证 |
| P1.phase3-T03-S01 | P1.phase3-T03 | 实现 10% 灰度分桶与全量复核路由 | P1.phase3-T02-S03 | F-P1.phase3-T03-01 | P0 | 分桶比例与复核比例可审计 |
| P1.phase3-T03-S02 | P1.phase3-T03 | 实现 llm_final_judged_ratio 门禁判定 | P1.phase3-T03-S01 | F-P1.phase3-T03-02 | P0 | 比例不足可阻断扩量 |
| P1.phase3-T03-S03 | P1.phase3-T03 | 实现真实调用证据汇聚与报告字段校验 | P1.phase3-T03-S02 | F-P1.phase3-T03-03 | P1 | evidence 字段完整率达标 |
| P1.phase3-T03-S04 | P1.phase3-T03 | 人工复核分流（pending_manual_review）联调 | P1.phase3-T03-S03 | F-P1.phase3-T03-04 | P2 | Deferred（本轮不验收） |
| P1.phase3-T04-S01 | P1.phase3-T04 | 实现时延门禁（P95<800ms）与降级动作 | P1.phase3-T03-S03 | F-P1.phase3-T04-01 | P0 | `arbiter_p95_latency` 通过门禁 |
| P1.phase3-T04-S02 | P1.phase3-T04 | 实现成本门禁与预算告警/回退 | P1.phase3-T04-S01 | F-P1.phase3-T04-02 | P1 | 超预算触发 `budget_fallback` |
| P1.phase3-T04-S03 | P1.phase3-T04 | 实现 real_call_ratio 门禁与 source_type 拒绝策略 | P1.phase3-T04-S02 | F-P1.phase3-T04-03 | P1 | mock 不得进入生产采纳 |

## 执行顺序（进入 STEP2 后）
- 主线：T01 -> T02 -> T03 -> T04
- 子线：T01-S01 -> T01-S02 -> T01-S03 -> T02-S01 -> T02-S02 -> T02-S03 -> T03-S01 -> T03-S02 -> T03-S03 -> (T03-S04 Deferred) -> T04-S01 -> T04-S02 -> T04-S03

## 边界约束
- 本轮不验收 `pending_manual_review/drop_event` 前端闭环。
- 仅执行最小实现与验证闭环，不做 phase4 发布收口。

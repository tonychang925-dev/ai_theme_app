# ADR List

### ADR-001: 第一阶段运行时单链路冻结
- Context
  - `theme_processor/theme_service/news_stream_handler` 存在重复定义与并行行为。
- Problem
  - 同输入可能触发不同分支，结果不可预测。
- Proposed Decision
  - 冻结单链路实现并清理重复定义。
- Alternatives
  - 保留多实现并依赖配置切换。
- Consequences
  - 确定性提升；一次性清理成本中等。

### ADR-002: DecisionEnvelope v1 强制契约
- Context
  - 决策消息存在弱解析与字段漂移。
- Problem
  - 回放和归因不可稳定复现。
- Proposed Decision
  - 强制 `decision_id/event_id/action/payload_version/trace_id/idempotency_key/payload`。
- Alternatives
  - 继续宽松消费端兼容。
- Consequences
  - 契约稳定；producer/consumer均需改造。

### ADR-003: DecisionExecutor 幂等门禁
- Context
  - 重试与回放场景存在重复执行风险。
- Problem
  - 题材与映射重复写入污染指标。
- Proposed Decision
  - 执行前校验 `idempotency_key`，命中后 `duplicate_skip`。
- Alternatives
  - 离线去重修复。
- Consequences
  - 一致性显著提升；需存储与索引支持。

### ADR-004: unknown operation fail-fast
- Context
  - 当前未知 operation 可被跳过。
- Problem
  - 执行语义不闭合，异常不可追踪。
- Proposed Decision
  - unknown action/operation 直接失败并入 dead-letter。
- Alternatives
  - warning 后继续处理。
- Consequences
  - 透明性增强；短期死信率可能上升。

### ADR-005: 动态阈值替代固定阈值主路径
- Context
  - 当前主路径仍使用固定阈值。
- Problem
  - 漏召回与候选爆炸并存。
- Proposed Decision
  - 事件级动态阈值 + Strong/Candidate/Weak 分层。
- Alternatives
  - 固定阈值人工调参。
- Consequences
  - 稳定性提升；需要A/B与监控。

### ADR-006: 禁止随机/零向量进入最终决策
- Context
  - 模型异常时存在随机/零向量回退。
- Problem
  - 错配被放大且难以审计。
- Proposed Decision
  - 异常路径仅允许受控降级，不产出最终主题决策。
- Alternatives
  - 保留随机/零向量兜底。
- Consequences
  - 准确性提升；未匹配事件会增加。

### ADR-007: 题材代码与决策ID确定性生成
- Context
  - 代码中存在时间戳/运行时hash生成ID。
- Problem
  - 相同输入回放结果不一致。
- Proposed Decision
  - 使用输入哈希与稳定规则生成业务ID。
- Alternatives
  - 保持时间戳编码。
- Consequences
  - 回放一致；需要历史ID映射。

### ADR-008: mock 数据门禁化
- Context
  - mock/real 虽有统计但未阻断发布。
- Problem
  - 评估与线上结果被 mock 污染。
- Proposed Decision
  - 将 `mock_source_ratio` 纳入 Release Gate。
- Alternatives
  - 仅日志提示。
- Consequences
  - 评估可信度提升；测试环境要求更高。

### ADR-009: pending 清理与 durable success 强绑定
- Context
  - 清理时序与持久化确认绑定不硬。
- Problem
  - 可能形成不可回放缺口。
- Proposed Decision
  - 清理动作必须依赖 durable success 证据。
- Alternatives
  - 发布后立即清理。
- Consequences
  - 回放安全增强；短期积压上升。

### ADR-010: 结构化可观测性最小集合
- Context
  - 生产路径有大量 `print/traceback`。
- Problem
  - 可观测性分散，难门禁化。
- Proposed Decision
  - 统一日志字段与指标：`trace_id/idempotency_key/source_type/gate_result`。
- Alternatives
  - 继续人工日志巡检。
- Consequences
  - 发布可控；需监控接入改造。

### ADR-011: 新题材创建阶段禁止二次分类推断
- Context
  - 架构第12章已要求：创建新题材应沿用首阶段分类结果，不再重复推断。
  - `theme_rule_generator.py` 的 `generate_theme_data_only()` 当前仍调用 `_match_categories()`。
- Problem
  - 同一事件可能出现“两次分类结果不一致”，导致题材归属漂移与回放不一致。
- Proposed Decision
  - 分类推断单一真源前置到“事件匹配题材阶段”；`theme_rule_generator` 仅消费 `classification_result/category_info`，禁止内部二次分类推断。
- Alternatives
  - 保留生成器内二次分类推断作为兜底。
- Consequences
  - 分类一致性与可解释性提升；需改造调用链并补齐兼容校验。

### ADR-012: 第一阶段强制引入 LLM 最终裁决（Qwen2.5 + llama.cpp）
- Context
  - 当前主链路仍以向量语义匹配作为最终决策依据，存在高相似错配。
  - 第一阶段架构目标已明确：LLM 裁判（Qwen2.5 + llama.cpp）是必须完成的优化功能。
- Problem
  - 仅依赖向量相似度会造成题材匹配不准、匹配错误，无法作为第一阶段最终验收的可靠解法。
- Proposed Decision
  - 固化两阶段顺序：`向量粗筛召回 -> LLM 裁判最终裁决（Qwen2.5 + llama.cpp）`。
  - 第一阶段验收中，最终落库结果必须来自 LLM 裁判结论；未裁判样本不得进入“验收通过”结果集。
  - 10% 灰度期要求 `llm_final_judged_ratio >= 95%`，并保留真实调用证据（request_id/timestamp/model）。
- Alternatives
  - 仅把 LLM 作为 shadow 对比，不参与最终裁决。
  - 继续依赖向量规则并人工调参。
- Consequences
  - 优点：显著降低语义误匹配，形成可解释最终裁决链路。
  - 成本：引入时延、调用成本与运行复杂度，需要熔断、超时回退和预算门禁。
  - 兼容：保留受控降级路径，但降级命中超预算时阻断发布。

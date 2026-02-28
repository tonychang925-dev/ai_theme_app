# 第一阶段测试用例规范（TEST_CASE_SPEC）

- 项目：个人投资助理（AI Theme App）
- 阶段：P1.phase0 ~ P1.phase4
- 版本：v1.0
- 状态：Ready for Review
- 作者：Codex
- 创建日期：2026-02-13
- 更新日期：2026-02-13
- 输入依据：
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/prd_p1.md`

---

## 1. 测试策略与范围

### 1.1 目标
- 建立第一阶段可执行、可追踪、可度量的测试资产。
- 覆盖 PRD-P1 全阶段关键需求与 ACCEPTANCE 验收契约。
- 对 P0 风险点（P1-ISS-01..10）提供强制验证用例。

### 1.2 测试级别
- `UT`：单元测试
- `IT`：集成测试
- `ST`：系统测试
- `ET`：边界/异常测试
- `PT`：性能测试
- `RT`：回归/回放测试

### 1.3 通过门槛（与 QA Gate 对齐）
- 所有 `P0` 用例必须 100% 通过。
- 每个需求项至少映射 1 个用例。
- 关键路径必须包含 `IT` 或 `ST`。
- 异常分支必须包含 `ET`。

---

## 2. 需求-用例映射矩阵（摘录）

| 需求ID | 需求摘要 | 风险级别 | 覆盖用例ID |
| --- | --- | --- | --- |
| PRD-P1-P0-R02 | 冻结 DecisionEnvelope v1 必填字段 | P0 | TC-P1-P0-UT-001, TC-P1-P0-ET-001 |
| PRD-P1-P0-R07 | 清理重复函数定义（ISS-01/02/03） | P0 | TC-P1-P0-UT-002 |
| PRD-P1-P0-R08 | news 消息收敛单一契约 | P0 | TC-P1-P0-IT-001, TC-P1-P0-ET-002 |
| PRD-P1-P0-R09 | 移除 print/traceback 生产输出 | P0 | TC-P1-P0-UT-003 |
| PRD-P1-P1-R02/R03/R08 | 幂等键+执行前门禁 | P0 | TC-P1-P1-IT-001, TC-P1-P1-RT-001 |
| PRD-P1-P1-R07 | 严格 schema 解析，禁止 str 降级 | P0 | TC-P1-P1-ET-001 |
| PRD-P1-P1-R09 | 未知 action fail-fast + dead-letter | P0 | TC-P1-P1-ET-002 |
| PRD-P1-P1-R10 | 失败受控重试+死信 | P1 | TC-P1-P1-IT-002 |
| PRD-P1-P2-R01/R02/R07 | 动态阈值替代固定阈值主路径 | P0 | TC-P1-P2-UT-001, TC-P1-P2-IT-001 |
| PRD-P1-P2-R08 | 禁止随机/零向量进入最终决策 | P0 | TC-P1-P2-ET-001 |
| PRD-P1-P2-R09 | source_type(real/mock) 门禁 | P1 | TC-P1-P2-IT-002 |
| PRD-P1-P2-R05 | 76案例A/B评估报告 | P1 | TC-P1-P2-RT-001 |
| ARCH-P1-12-R01 | Strong/Candidate/Weak 三段分层验证 | P0 | TC-P1-P2-UT-002 |
| ARCH-P1-12-R02 | 10% 灰度 A/B 先行验证 | P0 | TC-P1-P2-ST-001 |
| ARCH-P1-12-R03 | 76案例三方对比与指标收敛（8~12） | P0 | TC-P1-P2-PT-002 |
| ARCH-P1-12-R04 | 验收必须真实 DeepSeek（非 mock） | P0 | TC-P1-P2-RT-002, TC-P1-ARCH12-ST-003 |
| ARCH-P1-12-R05 | 固定测试入口与环境（test_theme_processor.py + py3.13 + theme_matcher_env） | P1 | TC-P1-ARCH12-ST-001 |
| ARCH-P1-12-R06 | 指标公式可复算与报告完整性 | P1 | TC-P1-ARCH12-ST-002 |
| PRD-P1-P3-R01/R02/R06 | 最终裁决必经链路 + 分类命中全量复核 + 10%灰度判定比例 | P0 | TC-P1-P3-IT-001, TC-P1-P3-ST-001 |
| PRD-P1-P3-R03 | 超时回退 | P0 | TC-P1-P3-ET-001 |
| PRD-P1-P3-R08/R09 | model不可用降级 + 熔断预算 | P1 | TC-P1-P3-ET-002 |
| PRD-P1-P3-R04/R05 | 最终裁决统计与报告 | P1 | TC-P1-P3-RT-001 |
| PRD-P1-P3-R07 | 裁判输入必须携带 source_type 与质量标签，mock 不参与生产裁判 | P1 | TC-P1-P3-ST-002, TC-P1-P3-ET-003 |
| PRD-P1-P3-R10 | Qwen2.5 + llama.cpp 模型栈与调用证据 | P0 | TC-P1-P3-ST-001 |
| PRD-P1-P4-R01/R08 | pending清理与durable success绑定+证据三元组 | P0 | TC-P1-P4-IT-001 |
| PRD-P1-P4-R07 | 题材代码生成可重放（去时间戳） | P0 | TC-P1-P4-UT-001, TC-P1-P4-RT-001 |
| PRD-P1-P4-R03/R09 | 发布门禁（含ISS关闭率） | P0 | TC-P1-P4-ST-001 |
| PRD-P1-P4-R10 | 死信回放状态一致 | P1 | TC-P1-P4-RT-002 |

---

## 3. 详细测试用例

### Phase P1.phase0 — 运行时收敛与契约冻结

---
id: TC-P1-P0-UT-001
module: DecisionEnvelope Contract
level: 单元测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P0-R02, PRD-P1-P0-R05
---

# DecisionEnvelope v1 必填字段校验

## 1. 测试目标
验证 v1 契约必填字段和版本兼容归一逻辑；缺失字段必须拒绝。

## 2. 前置条件
- 已实现统一契约校验器。
- 支持 v0/v1 dual-read。

## 3. 测试数据
### 输入
```json
{
  "payload_version": "v1",
  "decision_id": "dec_0001",
  "event_id": "evt_0001",
  "action": "update_theme",
  "trace_id": "trace_evt_0001",
  "idempotency_key": "evt_0001:update_theme:sha256_abcd",
  "payload": {"theme_id": "th_001"}
}
```
### 预期输出
```json
{"valid": true, "normalized_version": "v1"}
```

## 4. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 输入完整 v1 消息 | 校验通过 | 待执行 | 待执行 |
| 2 | 去掉 `trace_id` 重试 | 校验失败并返回错误码 | 待执行 | 待执行 |
| 3 | 输入 v0 消息 | 成功归一到 v1 内部对象 | 待执行 | 待执行 |

## 5. 验证点
- 必填字段覆盖率 = 100%。
- 拒绝消息必须可审计。

## 6. 预期结果标准
- 功能通过率 100%。
- 无未捕获异常。

## 7. 失败判定标准
- 缺字段仍进入业务执行。
- v0 消息无法归一。

---
id: TC-P1-P0-UT-002
module: Runtime Duplicate Definition Scan
level: 单元测试
type: 异常测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P0-R07
---

# 重复函数定义清零扫描

## 1. 测试目标
验证 `theme_processor/theme_service/news_stream_handler` 指定重复函数定义已清零。

## 2. 前置条件
- 建立静态扫描规则（AST 或符号表）。

## 3. 测试数据
### 输入
```json
{"targets": ["theme_processor.py", "theme_service.py", "news_stream_handler.py"]}
```
### 预期输出
```json
{"duplicate_definitions": 0}
```

## 4. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 扫描目标文件函数符号 | 无重复定义 | 待执行 | 待执行 |
| 2 | 输出重复明细报告 | 报告为空或0条 | 待执行 | 待执行 |

## 5. 验证点
- 覆盖 `P1-ISS-01/02/03`。

## 6. 预期结果标准
- 重复定义数量 = 0。

## 7. 失败判定标准
- 任一高风险重复定义仍存在。

---
id: TC-P1-P0-UT-003
module: Runtime Logging Hygiene
level: 单元测试
type: 规范测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P0-R09
---

# 生产路径 print/traceback 清零检查

## 1. 测试目标
验证运行时模块生产路径无 `print(` 与 `traceback.print_exc`。

## 2. 前置条件
- 约定扫描目录与忽略规则（测试目录除外）。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 扫描运行时目录 | 违规数 = 0 | 待执行 | 待执行 |
| 2 | 扫描异常处理分支 | 无 traceback 直出 | 待执行 | 待执行 |

## 4. 失败判定标准
- 生产路径存在任一违规输出语句。

---
id: TC-P1-P0-IT-001
module: News Stream Contract Pipeline
level: 集成测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P0-R01, PRD-P1-P0-R08, PRD-P1-P0-R03
---

# news 到 decision 全链路契约贯通

## 1. 测试目标
验证 `news_stream_* -> theme_processor -> DecisionExecutor` 单一路径与 `trace_id` 贯通。

## 2. 前置条件
- 启动 Redis stream 与核心消费者。

## 3. 测试数据
### 输入
```json
{"stream":"stream:news:raw","trace_id":"trace_e2e_001","payload_version":"v1","news":{"id":"n1","title":"样例新闻"}}
```
### 预期输出
```json
{"stream":"stream:events:decision","trace_id":"trace_e2e_001","status":"accepted"}
```

## 4. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 写入 news 消息到 raw 流 | 被唯一处理链消费 | 待执行 | 待执行 |
| 2 | 追踪 handler/processor/executor 日志 | 同一 trace_id 可串联 | 待执行 | 待执行 |
| 3 | 检查决策流输出 | 合法 v1 envelope | 待执行 | 待执行 |

## 5. 边界条件
- 输入包含历史 v0 结构。
- 输入嵌套 payload 层级异常。

## 6. 失败判定标准
- 出现多入口路由。
- trace_id 任一点丢失。

---
id: TC-P1-P0-ET-001
module: DecisionEnvelope Rejection
level: 边缘测试
type: 异常测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P0-R02
---

# 缺失必填字段拒绝与死信

## 1. 测试目标
验证缺失必填字段消息被拒绝并写入 dead-letter。

## 2. 前置条件
- dead-letter stream 可写可查。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 发送缺失 `action` 的 envelope | 拒绝进入执行器 | 待执行 | 待执行 |
| 2 | 检查 dead-letter | 存在错误码和原消息ID | 待执行 | 待执行 |

## 4. 失败判定标准
- 缺字段消息执行成功。
- dead-letter 无错误原因。

---
id: TC-P1-P0-ET-002
module: Payload Recursion Guard
level: 边缘测试
type: 边界测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P0-R08
---

# 无边界递归 payload 防护

## 1. 测试目标
验证多层/循环引用 payload 不进入无界解析。

## 2. 前置条件
- 解析器具备最大层级与字段白名单。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 输入 10 层嵌套 payload | 被拒绝并记录超限原因 | 待执行 | 待执行 |
| 2 | 输入循环结构 payload | 安全失败，不崩溃 | 待执行 | 待执行 |

## 4. 失败判定标准
- 解析器超时、栈溢出或 OOM。


### Phase P1.phase1 — 路由统一与幂等执行

---
id: TC-P1-P1-IT-001
module: DecisionExecutor Idempotency
level: 集成测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P1-R02, PRD-P1-P1-R03, PRD-P1-P1-R08
---

# 重复决策消息幂等执行

## 1. 测试目标
验证同键消息重复执行仅首条生效，后续 `duplicate_skip`。

## 2. 前置条件
- 幂等存储可读写。

## 3. 测试数据
### 输入
```json
[
  {"event_id":"evt_1001","action":"create_new_theme","payload_hash":"sha256_a"},
  {"event_id":"evt_1001","action":"create_new_theme","payload_hash":"sha256_a"}
]
```
### 预期输出
```json
{"first":"success","second":"duplicate_skip","duplicate_skip_count":1}
```

## 4. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 发送第1条决策 | 正常落库 | 待执行 | 待执行 |
| 2 | 发送第2条同键决策 | 命中幂等并跳过 | 待执行 | 待执行 |
| 3 | 查询数据层 | 仅1条有效变更 | 待执行 | 待执行 |

## 5. 失败判定标准
- 出现重复写入。

---
id: TC-P1-P1-IT-002
module: Controlled Failure Pipeline
level: 集成测试
type: 异常测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P1-R10
---

# 失败重试上限与死信

## 1. 测试目标
验证失败消息遵循重试上限，超限进入 dead-letter，无无限悬挂。

## 2. 前置条件
- 重试次数阈值配置已生效。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 注入可重复失败消息 | 触发重试计数累加 | 待执行 | 待执行 |
| 2 | 达到上限后继续消费 | 路由 dead-letter | 待执行 | 待执行 |
| 3 | 检查 pending 队列 | 无悬挂消息 | 待执行 | 待执行 |

## 4. 失败判定标准
- 消息无限重试。
- 超限未进入 dead-letter。

---
id: TC-P1-P1-ST-001
module: major/normal/pending Routing
level: 系统测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P1-R05, PRD-P1-P1-R06
---

# normal 未匹配进入 pending 且 ACK 原消息

## 1. 测试目标
验证 `normal` 匹配失败发布 `publish_clustering` 到 pending，并 ACK 原消息。

## 2. 前置条件
- stream:events:pending 可消费。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 输入 normal 未匹配事件 | 生成聚类决策 | 待执行 | 待执行 |
| 2 | 检查 pending 流 | 存在新决策，带 trace_id/decision_id | 待执行 | 待执行 |
| 3 | 检查原消息消费状态 | 已 ACK | 待执行 | 待执行 |

## 4. 失败判定标准
- 未匹配事件丢失或未 ACK。

---
id: TC-P1-P1-ET-001
module: Strict Schema Parser
level: 边缘测试
type: 异常测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P1-R07
---

# 禁止 str(value) 弱解析降级

## 1. 测试目标
验证结构化字段类型不合法时拒绝，不允许转字符串后继续执行。

## 2. 前置条件
- schema 校验器强制开启。

## 3. 测试数据
### 输入
```json
{"action": ["should_be_string"], "payload": "{broken_json}"}
```
### 预期输出
```json
{"status":"rejected","reason":"schema_validation_failed"}
```

## 4. 失败判定标准
- 进入执行主路径。
- 任意数据库写入发生。

---
id: TC-P1-P1-ET-002
module: Unknown Action Fail-Fast
level: 边缘测试
type: 异常测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P1-R09
---

# 未知 action/operation 失败直达死信

## 1. 测试目标
验证未知 action 必须 fail-fast，不允许 warning 后静默跳过。

## 2. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 发送 `action=unknown_op` 消息 | 立即失败 | 待执行 | 待执行 |
| 2 | 检查 dead-letter | 有原因码 `unknown_action` | 待执行 | 待执行 |

## 3. 失败判定标准
- 消息被“成功”消费但未执行、未入死信。

---
id: TC-P1-P1-RT-001
module: Replay Idempotency Regression
level: 回归测试
type: 回归测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: AG-04, PRD-P1-P1-R02
---

# 同批回放重复写入率回归

## 1. 测试目标
验证回放同批消息时重复写入率持续为 0。

## 2. 前置条件
- 存在基线回放数据集。

## 3. 失败判定标准
- 任何回放批次重复写入率 > 0。


### Phase P1.phase2 — 动态阈值与候选治理

---
id: TC-P1-P2-UT-001
module: Dynamic Threshold Calculator
level: 单元测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P2-R01, PRD-P1-P2-R02, PRD-P1-P2-R07
---

# 事件级动态阈值计算

## 1. 测试目标
验证基于分位数（p95/p98）计算阈值，profile 切换生效。

## 2. 测试数据
### 输入
```json
{"scores":[0.92,0.88,0.86,0.72,0.64],"profile":"balanced"}
```
### 预期输出
```json
{"dynamic_threshold":0.84,"profile":"balanced"}
```

## 3. 失败判定标准
- 仍走固定阈值主路径。
- profile 切换无效。

---
id: TC-P1-P2-IT-001
module: Candidate Governance Pipeline
level: 集成测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P2-R03, PRD-P1-P2-R04
---

# 候选治理先于精排且窗口受控

## 1. 测试目标
验证候选治理步骤在精排前执行，候选窗口稳定在 3~30。

## 2. 前置条件
- 匹配流水线可输出分阶段指标。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 输入高噪声事件集 | 初始候选数偏高 | 待执行 | 待执行 |
| 2 | 执行治理 | 候选数压缩到 3~30 | 待执行 | 待执行 |
| 3 | 执行精排 | 仅处理治理后候选 | 待执行 | 待执行 |

## 4. 失败判定标准
- 精排先于治理执行。
- 候选窗口长期超限。

---
id: TC-P1-P2-IT-002
module: Source Type Quality Gate
level: 集成测试
type: 边界测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P2-R09
---

# real/mock 占比门禁

## 1. 测试目标
验证 `source_type` 指标上报与 mock 超阈阻断发布。

## 2. 失败判定标准
- mock 占比超阈但 gate 仍放行。

---
id: TC-P1-P2-ET-001
module: Random/Zero Vector Guard
level: 边缘测试
type: 异常测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P2-R08
---

# 禁止随机/零向量参与最终决策

## 1. 测试目标
验证匹配异常时触发受控降级，不输出随机/零向量结果到最终决策。

## 2. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 注入 embedding 服务异常 | 进入降级分支 | 待执行 | 待执行 |
| 2 | 检查最终决策来源 | 非 random/zero vector | 待执行 | 待执行 |

## 3. 失败判定标准
- 最终决策来源为随机或零向量。

---
id: TC-P1-P2-PT-001
module: Candidate Explosion Performance
level: 性能测试
type: 性能测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: AG-05, PRD-P1-P2-R05
---

# 76 案例集候选爆炸比性能验证

## 1. 测试目标
验证动态阈值组候选爆炸比 < 5%。

## 2. 失败判定标准
- 爆炸比 >= 5%。

---
id: TC-P1-P2-RT-001
module: Baseline vs Dynamic AB Report
level: 回归测试
type: 回归测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P2-R05, AG-03
---

# 76案例 A/B 可复现报告回归

## 1. 测试目标
验证报告包含题材数量、完整性、分离度、精度代理，且可复跑得到一致结论。

## 2. 失败判定标准
- 报告字段缺失。
- 同参数复跑结论不可复现。

---
id: TC-P1-P2-UT-002
module: Dynamic Segment Buckets
level: 单元测试
type: 边界测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: ARCH-P1-12-R01
---

# Strong/Candidate/Weak 三段分层命中验证

## 1. 测试目标
验证动态阈值输出严格落入 `Strong/Candidate/Weak` 三段之一，并产生分层命中统计。

## 2. 前置条件
- 动态阈值与分段器已启用。

## 3. 测试数据
### 输入
```json
{"scores":[0.97,0.91,0.83,0.74,0.61],"profile":"balanced"}
```
### 预期输出
```json
{"segment_hits":{"Strong":1,"Candidate":2,"Weak":2}}
```

## 4. 失败判定标准
- 分层命中为空或不互斥。
- Candidate 未进入精排队列。

---
id: TC-P1-P2-ST-001
module: AB Gray Traffic Router
level: 系统测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: ARCH-P1-12-R02
---

# 10% 灰度 A/B 路由验证

## 1. 测试目标
验证优化策略仅接入 10% 灰度流量，剩余 90% 保持基线路径。

## 2. 前置条件
- 灰度分桶可配置且可观测。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 设置 `ab_gray_ratio=0.1` | 配置生效 | 待执行 | 待执行 |
| 2 | 回放固定批次事件 | 10% 命中优化组，90% 命中基线组 | 待执行 | 待执行 |
| 3 | 导出分桶报告 | 分桶比例偏差不超过 ±1% | 待执行 | 待执行 |

## 4. 失败判定标准
- 未按 10% 灰度分流。
- 未保留分桶审计证据。

---
id: TC-P1-P2-PT-002
module: Three-way Benchmark Evaluation
level: 性能测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: ARCH-P1-12-R03, ARCH-P1-12-R06
---

# 76案例三方对比与指标收敛验证

## 1. 测试目标
验证 76 案例集在三方对比下满足数量与质量指标口径。

## 2. 前置条件
- 提供优化系统、基线纯聚类、久赢恒丰标准三组输出。

## 3. 验证点
- `theme_count` 落在 8~12。
- `Precision/Completeness/Separation` 三项指标均不低于基线系统。
- 报告包含三方差异分析。

## 4. 失败判定标准
- 题材数量不在 8~12。
- 三项指标任一低于基线。
- 报告缺失三方对比数据。

---
id: TC-P1-P2-RT-002
module: Real DeepSeek Evaluation Run
level: 回归测试
type: 回归测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: ARCH-P1-12-R04, ARCH-P1-12-R05
---

# 真实 DeepSeek 验收回归（固定入口）

## 1. 测试目标
验证正式验收通过 `test_theme_processor.py` 执行，且全部为真实 DeepSeek 调用。

## 2. 前置条件
- macOS + Python 3.13。
- `conda activate theme_matcher_env` 可用。

## 3. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 在 `theme_matcher_env` 执行 `test_theme_processor.py` | 任务成功完成 | 待执行 | 待执行 |
| 2 | 检查调用来源 | `source_type=real` 占比 100% | 待执行 | 待执行 |
| 3 | 抽样审计日志 | 存在 model_name/request_id/timestamp | 待执行 | 待执行 |

## 4. 失败判定标准
- 使用 mock 数据替代正式结果。
- 非指定入口或环境执行。


### Phase P1.phase3 — LLM 最终裁决落地（Qwen2.5 + llama.cpp）

> 真源文件：`docs/project_control/TEST_CASE_SPEC_P1.phase3.md`
>
> 说明：本总表不再维护 phase3 详细用例内容，避免双份漂移；请直接在 phase3 专项文件维护与验收。


### Phase P1.phase4 — 回放安全与发布门禁

---
id: TC-P1-P4-UT-001
module: Theme Code Determinism
level: 单元测试
type: 回归测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P4-R07
---

# 题材代码生成确定性

## 1. 测试目标
验证相同输入多次生成题材代码完全一致，不含时间戳主键漂移。

## 2. 失败判定标准
- 同输入生成不同主题代码。

---
id: TC-P1-P4-IT-001
module: Pending Cleanup Transaction Safety
level: 集成测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P4-R01, PRD-P1-P4-R08
---

# durable success 后才允许 pending 清理

## 1. 测试目标
验证 pending 清理与 durable success 强绑定，清理证据三元组完整。

## 2. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 执行聚类落库流程 | 获得 durable success | 待执行 | 待执行 |
| 2 | 触发 pending 清理 | 清理后保留 decision_id/trace_id/evidence_id | 待执行 | 待执行 |

## 3. 失败判定标准
- 先清理后落库。
- 证据字段缺失。

---
id: TC-P1-P4-ST-001
module: Release Gate
level: 系统测试
type: 功能测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P4-R03, PRD-P1-P4-R09, AG-07
---

# 发布门禁阻断与放行

## 1. 测试目标
验证发布门禁依据回放一致率、死信率、积压时长、重点问题关闭率执行阻断。

## 2. 测试数据
### 输入
```json
{
  "replay_consistency": 1.0,
  "dead_letter_rate": 0.002,
  "backlog_minutes": 3,
  "issues_closed_ratio": 1.0
}
```
### 预期输出
```json
{"release_gate":"pass","blocked":false}
```

## 3. 边界条件
- `issues_closed_ratio < 1.0`。
- `replay_consistency < 1.0`。

## 4. 失败判定标准
- 任一超阈仍放行。

---
id: TC-P1-P4-RT-001
module: Full Replay Consistency
level: 回归测试
type: 回归测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P4-R02, AG-04
---

# 历史批次全量回放一致性

## 1. 测试目标
验证历史批次回放结果与基线完全一致，一致率 100%。

## 2. 失败判定标准
- 一致率 < 100%。

---
id: TC-P1-P4-RT-002
module: Dead-letter Replay
level: 回归测试
type: 异常恢复测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: PRD-P1-P4-R10
---

# 死信回放后状态一致性

## 1. 测试目标
验证死信消息修复后回放，最终状态与标准路径一致。

## 2. 失败判定标准
- 回放后二次分叉。
- 状态不可追溯。

---

### 架构第12章专项测试（优化目标与验证体系）

---
id: TC-P1-ARCH12-ST-001
module: Arch12 Execution Environment
level: 系统测试
type: 规范测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: ARCH-P1-12-R05
---

# 固定测试入口与运行环境

## 1. 测试目标
验证架构第12章要求的执行入口与环境一致：`test_theme_processor.py`、macOS、Python 3.13、`theme_matcher_env`。

## 2. 失败判定标准
- 任一环境参数不匹配。
- 使用其他入口替代。

---
id: TC-P1-ARCH12-ST-002
module: Arch12 Metric Formula Contract
level: 系统测试
type: 功能测试
priority: P1
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: ARCH-P1-12-R06
---

# 指标公式与报告完整性校验

## 1. 测试目标
验证报告显式给出并使用固定公式：Precision、Completeness、Separation。

## 2. 测试步骤
| 步骤 | 操作 | 预期结果 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 读取验收报告 | 三个公式完整展示 | 待执行 | 待执行 |
| 2 | 抽样复算 10 条记录 | 复算结果与报告一致 | 待执行 | 待执行 |

## 3. 失败判定标准
- 缺少任一公式定义。
- 复算与报告不一致。

---
id: TC-P1-ARCH12-ST-003
module: Arch12 Real Model Evidence
level: 系统测试
type: 异常测试
priority: P0
author: Codex
created: 2026-02-13
updated: 2026-02-13
related_requirements: ARCH-P1-12-R04
---

# 真实模型调用证据校验

## 1. 测试目标
验证正式验收报告具备真实 DeepSeek 调用审计证据，且 `real_call_ratio=100%`。

## 2. 失败判定标准
- 证据缺失（model_name/request_id/timestamp/status）。
- `real_call_ratio < 100%`。

---

## 4. Phase 级验收用例集合（对齐 ACCEPTANCE）

| Phase | 验收案例ID | 对应测试用例 |
| --- | --- | --- |
| P1.phase0 | ACC-P1-P0-01 | TC-P1-P0-UT-002 |
| P1.phase0 | ACC-P1-P0-02 | TC-P1-P0-UT-001, TC-P1-P0-ET-001 |
| P1.phase0 | ACC-P1-P0-03 | TC-P1-P0-IT-001 |
| P1.phase1 | ACC-P1-P1-01 | TC-P1-P1-IT-001, TC-P1-P1-RT-001 |
| P1.phase1 | ACC-P1-P1-02 | TC-P1-P1-ET-001, TC-P1-P1-ET-002 |
| P1.phase1 | ACC-P1-P1-03 | TC-P1-P1-ST-001 |
| P1.phase2 | ACC-P1-P2-01 | TC-P1-P2-PT-001, TC-P1-P2-RT-001 |
| P1.phase2 | ACC-P1-P2-02 | TC-P1-P2-IT-001 |
| P1.phase2 | ACC-P1-P2-03 | TC-P1-P2-ET-001 |
| P1.phase2 | ACC-P1-P2-04 | TC-P1-P2-PT-002 |
| P1.phase2 | ACC-P1-P2-05 | TC-P1-P2-ST-001 |
| P1.phase2 | ACC-P1-P2-06 | TC-P1-P2-UT-002 |
| P1.phase2 | ACC-P1-P2-07 | TC-P1-P2-RT-002 |
| P1.phase3 | ACC-P1-P3-01 | TC-P1-P3-IT-001, TC-P1-P3-ST-001 |
| P1.phase3 | ACC-P1-P3-02 | TC-P1-P3-ET-001 |
| P1.phase3 | ACC-P1-P3-03 | TC-P1-P3-ET-002, TC-P1-P3-ST-002, TC-P1-P3-ET-003 |
| P1.phase4 | ACC-P1-P4-01 | TC-P1-P4-RT-001 |
| P1.phase4 | ACC-P1-P4-02 | TC-P1-P4-IT-001 |
| P1.phase4 | ACC-P1-P4-03 | TC-P1-P4-ST-001 |
| ARCH12 | ACC-P1-ARCH12-01 | TC-P1-ARCH12-ST-002, TC-P1-P2-PT-002 |
| ARCH12 | ACC-P1-ARCH12-02 | TC-P1-ARCH12-ST-001, TC-P1-P2-RT-002 |
| ARCH12 | ACC-P1-ARCH12-03 | TC-P1-ARCH12-ST-003, TC-P1-P2-RT-002 |

---

## 5. 边界条件总表

- 契约边界：缺字段、字段类型错误、版本混入（v0/v1）。
- 流程边界：未知 action、重试超限、pending 清理时序错误。
- 算法边界：高噪声候选爆炸、阈值异常波动、embedding 服务异常。
- 架构12章边界：三段分层未生效、灰度比例偏移、三方对比缺失、公式不可复算。
- 裁判边界：未经过最终裁决直接落库、灰度比例不达标、超时、不可用、成本超预算、熔断窗口触发。
- 发布边界：回放一致率非 100%、ISS 关闭率不足、死信率超阈。

---

## 6. 失败判定总则

以下任一命中即判定第一阶段测试不通过：
- 任一 `P0` 测试用例失败。
- 任一阶段关键验收案例无可执行测试映射。
- 回放一致率 < 100%。
- 重复写入率 > 0。
- 候选爆炸比 >= 5%。
- 76案例题材数量不在 8~12。
- Precision/Completeness/Separation 任一低于基线。
- 10% 灰度策略未按比例执行。
- 正式验收存在 mock 调用或 `real_call_ratio < 100%`。
- 未将 LLM 作为最终落库必经链路。
- `llm_final_judged_ratio < 95%`（10%灰度）。
- 裁判模型栈非 `Qwen2.5 + llama.cpp` 或证据缺失。
- 裁判附加时延 P95 >= 800ms。
- 发布门禁在超阈条件下放行。

---

## 7. 执行建议（落地顺序）

1. 先执行 `UT/ET`（phase0/phase1）确保契约和幂等收敛。
2. 再执行 `IT/ST` 打通链路，再跑 `PT` 验证指标。
3. 最后执行 `RT`（回放、A/B、死信修复）作为发布前门禁。

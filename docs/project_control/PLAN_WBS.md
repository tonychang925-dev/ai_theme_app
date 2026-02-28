# 项目计划（Project Plan）

## 1. 规划范围（Scope）
- `scope=phase:第一阶段`
- 目标：围绕“题材匹配精度与稳定性”完成第一阶段执行拆解，优先解决架构文档第11/12章识别的问题，并建立可量化验证体系。
- 约束与假设：
  - 仅拆解第一阶段；第二阶段仅作为依赖边界。
  - 现有 Redis Stream 主架构不重做，只做收敛与门禁强化。
  - 必须纳入关键优化：创建新题材时复用首阶段分类结果，禁止在 `generate_theme_data_only()` 二次 `_match_categories` 推断。
  - 风险偏好：`medium`；发布期望：`beta/internal`。

## 2. 架构拆解（Architecture Decomposition）
- 子系统清单：
  - 新闻采集与调度：`news_collector_scheduler` / `news_stream_scheduler`
  - 事件处理与分发：`news_stream_handler` / `news_stream_processor`
  - 题材发现与匹配：`theme_processor` / `theme_service` / `theme_discovery_engine` / `semantic_matcher`
  - 题材数据生成与执行：`theme_data_generator` / `DecisionExecutor`
  - 规则生成关键组件：`theme_rule_generator`
- 横切关注点：
  - 契约治理（DecisionEnvelope 版本化）
  - 幂等与回放安全（duplicate-skip + durable cleanup）
  - 观测门禁（死信率、候选爆炸比、积压时长、real_call_ratio）
  - 验证体系（30 案例、三方对比、10% 灰度、真实 DeepSeek）
  - ADR 管理（关键架构决策与变更追溯）
- 关键路径与不确定性：
  - 关键路径：路由收敛 -> 契约化 -> 幂等门禁 -> 动态阈值 -> 分类复用改造 -> 裁判灰度 -> 回放门禁
  - 不确定性：动态阈值在热点分布下稳定性、LLM 裁判时延/成本波动

## 3. 里程碑总览（Milestone Overview）
| Phase | 名称 | Objective | 风险等级 | 预计时长 | 依赖 |
| --- | --- | --- | --- | --- | --- |
| P1.phase0 | 运行时收敛与契约冻结 | 固定单链路与统一契约，消除行为漂移 | High | 3人天 | 无 |
| P1.phase1 | 路由统一与幂等执行 | 去重路由并建立强幂等，收敛失败策略 | High | 4人天 | P1.phase0 |
| P1.phase2 | 动态阈值与分类复用优化 | 动态阈值稳定精度，并移除二次分类推断 | High | 6人天 | P1.phase1 |
| P1.phase3 | LLM裁判灰度与验证体系落地 | 二阶段语义裁判灰度 + 第12章验证体系强门禁 | Medium-High | 4人天 | P1.phase2 |
| P1.phase4 | 回放安全与发布门禁收口 | 回放一致、SLO阻断、问题闭环与复盘 | High | 4人天 | P1.phase3 |

## 4. 里程碑详情（Milestone Detail）
### P1.phase0 — 运行时收敛与契约冻结
#### Objective
- 建立第一阶段“单一运行时真相”和统一消息契约基线。
#### Scope
- 固化唯一运行时链路（Processor/Executor/Clustering）。
- 定义 `DecisionEnvelope v1` 字段与版本规则。
- 贯通 `trace_id/payload_version`。
#### Out of Scope
- 动态阈值与 LLM 裁判参数优化。
#### Dependencies
- `ARCH_REVIEW.md`、`prd_p1.md`、第一阶段架构文档第11/12章。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Integration | 旧链路仍被误调用 | 增加运行时路径扫描与告警 | 高 | 中 | 中 |
| Migration | 契约字段新增导致兼容问题 | dual-read(v0/v1) 过渡 | 中 | 中 | 中 |
#### DoD
- [ ] 运行时处理链唯一且可验证
- [ ] DecisionEnvelope v1 定义冻结
- [ ] trace_id 跨流可追踪
- [ ] 重复函数定义清零（高风险模块）
#### Acceptance Gate
- 必跑命令：`pytest database_service/tests/streams -q`
- 阈值/指标：重复入口=0；契约必填覆盖率=100%
- 评审类型：Architecture + Design Gate
- 失败判定：存在双入口/缺失必填字段即失败

### P1.phase1 — 路由统一与幂等执行
#### Objective
- 同一输入在重试/回放场景下保持一致执行结果。
#### Scope
- 收敛 decision routing。
- 建立幂等键策略（`event_id+action+payload_hash`）。
- unknown action/operation fail-fast + dead-letter。
#### Out of Scope
- 阈值 profile 优化。
#### Dependencies
- P1.phase0。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Technical | 幂等键设计不足导致误去重 | 引入冲突样例回放测试 | 高 | 中 | 中 |
| Integration | 解析策略收敛影响旧消息 | 兼容解析 + reject 证据化 | 中 | 中 | 中 |
#### DoD
- [ ] 路由函数唯一实现
- [ ] 幂等键和重复保护策略生效
- [ ] 未知 action/operation 全量 fail-fast
- [ ] 回放同批次无重复写入
#### Acceptance Gate
- 必跑命令：`pytest database_service/tests/streams -q`
- 阈值/指标：重复写入率=0；dead-letter 率不劣化
- 评审类型：Design + QA Gate
- 失败判定：回放不一致或重复写入即失败

### P1.phase2 — 动态阈值与分类复用优化
#### Objective
- 用事件级动态阈值稳定候选规模与质量，并消除新题材创建阶段二次分类推断。
#### Scope
- 阈值 profile：`baseline/balanced/strict` 与 Strong/Candidate/Weak 分层。
- 候选窗口治理（目标 3~30）。
- `theme_rule_generator.generate_theme_data_only()` 改造：复用首阶段分类结果，禁止再次 `_match_categories()`。
#### Out of Scope
- LLM 裁判全量放量。
#### Dependencies
- P1.phase1。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Model | 热点分布突变导致阈值失真 | 分位数回退 + 上限保护 | 高 | 高 | 中 |
| Consistency | 分类来源不唯一导致漂移 | 单一分类真源 + 契约字段固化 | 高 | 高 | 中 |
#### DoD
- [ ] 动态阈值策略完成并可切换
- [ ] 分类复用策略落地（无二次推断）
- [ ] 30案例对比报告产出
- [ ] 无新增 P0/P1 缺陷
#### Acceptance Gate
- 必跑命令：`pytest database_service/scripts/test_theme_processor.py -q`
- 阈值/指标：候选爆炸比<5%；候选窗口3~30；分类一致率=100%
- 评审类型：Model Review + QA Gate
- 失败判定：任一关键指标劣化或出现二次分类推断即失败

### P1.phase3 — LLM裁判灰度与验证体系落地
#### Objective
- 对歧义样本引入二阶段裁判，同时满足第12章验证体系约束。
#### Scope
- 粗筛后裁判链路（可开关、shadow 优先）。
- 30 案例三方对比（优化系统 vs 基线纯聚类 vs 久赢恒丰标准）。
- 10% 灰度 + 真实 DeepSeek 调用门禁（`source_type=real`）。
#### Out of Scope
- 全量生产切流。
#### Dependencies
- P1.phase2。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Model | 裁判输出不稳定 | 温度锁定 + 一致性采样 | 高 | 中 | 中 |
| Cost | 调用成本超预算 | 仅对歧义样本触发 | 中 | 中 | 低 |
| Compliance | 验证体系执行不完整 | 强制校验脚本+阻断发布 | 高 | 中 | 低 |
#### DoD
- [ ] 裁判链路可配置开关
- [ ] 10% 灰度报告完成
- [ ] 真实调用证据齐全（请求ID/时间戳/模型名）
- [ ] 三方评估指标满足门槛
#### Acceptance Gate
- 必跑命令：`pytest tests -q`
- 阈值/指标：P95 附加时延<800ms；real_call_ratio=100%；题材数8~12
- 评审类型：Design + QA + Product Gate
- 失败判定：超时/预算失控/真实调用不足/三方指标不达标即失败

### P1.phase4 — 回放安全与发布门禁收口
#### Objective
- 建立可回放、可审计、可发布闭环并完成 P1 收口。
#### Scope
- pending 清理与 durable success 强绑定。
- 回放一致性与故障演练。
- 发布 SLO 门禁接入（死信率/积压时长/一致率/real_call_ratio）。
#### Out of Scope
- 第二阶段状态机与 CQRS 改造。
#### Dependencies
- P1.phase3。
#### Risks
| 类型 | 描述 | 缓解策略 | 影响 | 概率 | 发现难度 |
| --- | --- | --- | --- | --- | --- |
| Migration | 清理策略切换造成积压 | 分批切换 + 回滚阈值 | 高 | 中 | 中 |
| Integration | 门禁误报影响发布节奏 | 设冷启动观察窗 | 中 | 中 | 低 |
#### DoD
- [ ] pending 清理策略验收通过
- [ ] replay 一致性测试通过
- [ ] 发布门禁与告警上线
- [ ] 第一阶段重点问题关闭率=100%
#### Acceptance Gate
- 必跑命令：`pytest database_service/tests/streams -q && pytest tests -q`
- 阈值/指标：回放一致率=100%；重复写入率=0；dead-letter 率低于基线
- 评审类型：QA Gate + Release Gate + Retro
- 失败判定：回放不一致或任一门禁超阈即失败

## 5. WBS（任务分解）
### WBS — P1.phase0
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase0-T01 | 冻结第一阶段唯一运行时链路与入口清单 | - | 0.5人天 | 中 | 架构评审记录 | 文档更新,代码审查 |
| P1.phase0-T02 | 定义 DecisionEnvelope v1 字段与 dual-read 兼容策略 | P1.phase0-T01 | 1人天 | 中 | 契约评审通过 | API文档,文档更新 |
| P1.phase0-T03 | 清理重复函数定义并建立静态扫描门禁 | P1.phase0-T02 | 1人天 | 高 | CI扫描报告 | 单元测试,代码审查 |
| P1.phase0-T04 | trace_id/payload_version 全链路贯通方案评审 | P1.phase0-T03 | 0.5人天 | 低 | 链路追踪样例 | 文档更新,代码审查 |

### WBS — P1.phase1
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase1-T01 | 收敛决策路由逻辑并移除重复入口 | P1.phase0-T04 | 1人天 | 高 | 路由单元测试 | 单元测试,代码审查 |
| P1.phase1-T02 | 幂等键规则与 duplicate-skip 执行门禁 | P1.phase1-T01 | 1人天 | 高 | 回放重复写入检查 | 单元测试,文档更新 |
| P1.phase1-T03 | unknown action/operation fail-fast + dead-letter | P1.phase1-T02 | 0.5人天 | 中 | 异常流集成测试 | 集成测试,代码审查 |
| P1.phase1-T04 | 严格 schema 解析替代弱降级策略（禁 `str(value)`） | P1.phase1-T03 | 1人天 | 高 | payload 畸形样本测试 | 单元测试,集成测试 |
| P1.phase1-T05 | 输出阶段验收报告并更新 ADR 追踪链接 | P1.phase1-T04 | 0.5人天 | 低 | 评审结论通过 | 文档更新,代码审查 |

### WBS — P1.phase2
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase2-T01 | 设计并实现动态阈值 profile + 三段分层策略 | P1.phase1-T05 | 1.5人天 | 高 | 策略评审与指标校验 | 单元测试,代码审查 |
| P1.phase2-T02 | 实施候选窗口治理（3~30）与爆炸比监控 | P1.phase2-T01 | 1.5人天 | 高 | 候选分布报表 | 单元测试,性能测试 |
| P1.phase2-T03 | 关键优化：`generate_theme_data_only` 复用首阶段分类结果，移除 `_match_categories` 二次推断 | P1.phase2-T01 | 1人天 | 高 | 分类一致性回放测试 | 单元测试,代码审查 |
| P1.phase2-T04 | 更新 ADR（分类真源复用决策）并完成设计评审归档 | P1.phase2-T03 | 0.5人天 | 中 | ADR 审批记录 | 文档更新,代码审查 |
| P1.phase2-T05 | 30案例 A/B 对比（含分类一致性指标） | P1.phase2-T02 | 1.5人天 | 中 | A/B 报告 | 集成测试,文档更新 |
| P1.phase2-T06 | 分类关键词反向索引补全（`L2 <- L3(tags.keywords)`, `L1 <- L2(keywords)`） | P1.phase2-T03 | 1人天 | 中 | 关键词覆盖率与幂等性报告 | 单元测试,集成测试,文档更新 |

### WBS — P1.phase3
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase3-T01 | 定义二阶段 LLM 裁判触发条件与回退策略 | P1.phase2-T05 | 0.5人天 | 中 | 设计评审 | 文档更新,代码审查 |
| P1.phase3-T02 | 裁判 shadow 接入（分类命中样本全量复核）与超时回退 | P1.phase3-T01 | 1.5人天 | 高 | shadow 运行记录 | 单元测试,集成测试 |
| P1.phase3-T03 | 落地第12章验证体系：10%灰度、三方评估、真实调用证据链 | P1.phase3-T02 | 1.5人天 | 高 | 验收报告与证据包 | 集成测试,文档更新 |
| P1.phase3-T03a | 补充 `source_type(real/mock)` 与质量标签门禁验证（PRD-P1-P3-R07） | P1.phase3-T03 | 0.5人天 | 中 | 门禁验证记录与审计样本 | 集成测试,文档更新 |
| P1.phase3-T04 | 成本/时延/real_call_ratio 门禁配置与评审 | P1.phase3-T03 | 0.5人天 | 中 | Product Gate 记录 | 性能测试,文档更新 |

### WBS — P1.phase4
| Task ID | 任务描述 | Depends On | 估算 | 风险 | 验证方式 | DoD Checklist |
| --- | --- | --- | --- | --- | --- | --- |
| P1.phase4-T01 | pending durable cleanup 规则与回滚线定义 | P1.phase3-T04 | 1人天 | 高 | 设计评审 | 文档更新,代码审查 |
| P1.phase4-T02 | 回放一致性与故障演练脚本验证 | P1.phase4-T01 | 1.5人天 | 高 | replay 演练报告 | 集成测试,性能测试 |
| P1.phase4-T03 | 发布 SLO 门禁接入（死信率/积压时长/一致率/real_call_ratio） | P1.phase4-T02 | 1人天 | 中 | Gate 通过记录 | 集成测试,文档更新 |
| P1.phase4-T04 | 第一阶段收口复盘与下一阶段输入清单 | P1.phase4-T03 | 0.5人天 | 低 | Retro 结论 | 文档更新,代码审查 |

## 6. 依赖图（Dependency Graph）
- Milestone dependency graph：
  - `P1.phase0 -> P1.phase1 -> P1.phase2 -> P1.phase3 -> P1.phase4`
- 关键路径：
  - `契约冻结 -> 路由统一幂等 -> 动态阈值 -> 分类复用改造 -> 验证体系落地 -> 回放门禁`
- 可并行段：
  - `P1.phase2` 中 `T02` 与 `T03` 可并行（阈值治理与分类复用改造）。
  - `P1.phase3` 中指标看板准备可与 shadow 接入并行。
- 风险集中区：
  - `P1.phase2`（阈值稳定性 + 分类一致性）
  - `P1.phase3`（真实模型验证与灰度成本）
  - `P1.phase4`（清理时序与回放一致性）
- 阻塞节点：
  - `P1.phase0-T02`（契约冻结）
  - `P1.phase1-T02`（幂等键定稿）
  - `P1.phase2-T03`（二次分类推断移除）
- 跨阶段耦合点：
  - LLM 裁判策略与第二阶段语义演化接口存在耦合，需要 ADR 追踪。
- 需要 ADR 的节点：
  - 动态阈值策略变更、分类真源复用策略、pending 清理规则。

## 7. 排期摘要（Timeline Summary）
- 保守估算：`26人天`（含验证体系与证据链留白）
- 激进估算：`18人天`（并行推进，低缓冲）
- 风险调整估算：`21人天`（推荐）
- 关键假设：
  - 核心开发 2 人 + 测试/评审 1 人可持续投入。
  - DeepSeek 真实调用环境可稳定提供验收所需配额。
- 最大风险与缓解：
  - 最大风险：`P1.phase2` 分类复用改造与动态阈值同时变更引发行为偏移。
  - 缓解：分阶段灰度（10%）+ 回放对齐 + ADR 审批后再扩量。

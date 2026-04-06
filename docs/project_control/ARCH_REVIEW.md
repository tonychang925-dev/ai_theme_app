# ARCH_REVIEW

## Change Log

- 2026-04-02
  - 将本文件从“仅第三阶段评审”调整回“总评审文档”结构。
  - 保留第三阶段评审结论，并补回第二阶段历史评审摘要。
  - 后续所有阶段评审均按增量章节追加，不覆盖既有阶段内容。

## 0. 总览

本文件是项目级架构评审总文档，不对应单一阶段。

当前已纳入的阶段评审包括：

- `P2`：题材匹配重构与 `ThemeMatchEngine` 入核相关评审摘要
- `P3`：股票服务、复盘链、实时增强与统一产品出口相关评审摘要

后续原则：

- 新阶段评审只追加新章节
- 不删除既有阶段结论
- 若历史结论失效，采用“变更记录 + 冲突裁决”方式修订

---

## A. 第二阶段历史评审摘要（P2 Review Snapshot）

### A.1 评审范围

- 评审对象：
  - `docs/architecture/个人投资助理-项目架构设计-第二阶段（题材匹配重构版）.md`
- 约束真源：
  - `docs/project_control/PRD.md` 中 `P2.phase0`
  - `docs/project_control/ACCEPTANCE.md` 中 `P2.phase0`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/adrs/ADR_LIST.md`

### A.2 结论摘要

第二阶段的历史评审结论保持不变：

- `ThemeMatchEngine` 作为唯一线上题材判定内核的方向成立
- `P2.phase0` 的首期边界基本成立
- 当时的主要阻断项是：
  - 运行时契约未冻结到字段级
  - 兼容层与降级策略未完全写回架构文档
  - `PHASE_CONTRACT / WBS / TEST_CASE_SPEC` 配套不完整

### A.3 仍然有效的关键判断

- 必须维持结构化事件单流，不回退到旧的 `major / normal` 双流入口。
- 必须保留 `ThemeMatchEngine` 的唯一判定地位，不允许多条最终落题材路径并存。
- 必须继续保持展示层与在线匹配画像层解耦。

### A.4 对第三阶段的前置影响

第三阶段当前设计建立在以下第二阶段成果之上：

- `news_raw -> news_event -> event_theme_map`
- `theme_detail_snapshot / theme_history_event / theme_tree_relation / theme_stock_map`
- `subject_key` 统一业务主键
- `/intel/feed` 与前置产品出口能力

因此，第三阶段所有新增能力都必须兼容上述对象和主链，而不能绕开第二阶段既有真源。

---

## B. 第三阶段评审（P3 Review）

## 1. 当前架构摘要（Current Architecture Summary）

### 1.1 评审范围

- 评审对象：
  - [个人投资助理-项目架构设计-第三阶段.md](/Users/admin/Desktop/ai_theme_app/docs/architecture/个人投资助理-项目架构设计-第三阶段.md)
  - [PRD.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/PRD.md)
  - [ACCEPTANCE.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/ACCEPTANCE.md)
  - [PLAN_WBS.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/PLAN_WBS.md)
  - [ADR_LIST.md](/Users/admin/Desktop/ai_theme_app/docs/adrs/ADR_LIST.md)

### 1.2 当前第三阶段设计摘要

当前第三阶段已经从“笼统的股票服务与实时资讯产品化”收敛为一条更现实的产品化路径：

- `P3.phase0`
  - 前端统一产品出口
  - 历史命名为 `P3.phaseA`
- `P3.phase1`
  - `Tushare + JYHF` 双源事实层
  - 股票对象层、盘前必读、盘后复盘、Notion 输出基础
- `P3.phase2`
  - 复盘增强与工作台深化
  - 龙虎榜、资金行为增强、个股工作台、`/recap`
- `P3.phase3`
  - 实时化与高级增强
  - `SSE`、分钟级异动、情报流联动、轻量产业链视图

### 1.3 评审结论摘要

本次架构评审结论：

- **第三阶段拆解方向：通过**
- **第三阶段首批边界：基本合理**
- **数据源策略：有条件通过**
- **当前阻断项：缺少正式 `PLAN_WBS / PHASE_CONTRACT / TEST_CASE_SPEC`，以及若干数据所有权与实时化边界仍需 ADR 冻结**

换句话说：

- 现在的第三阶段已经不是“无边界的大平台愿景”，而是接近可执行的阶段化设计；
- 但如果没有进一步冻结若干关键架构决策，后续实现仍可能重新滑回“先做高频实时，再补事实对象层”的错误路径。

### 1.4 当前设计的主要优点

- 已明确 `P3` 是完整阶段，不再把 `P3.phase1` 误当整个第三阶段。
- 已把 `Tushare + JYHF` 分工收敛为“双源事实 + 题材语义”组合。
- 已把 `frontend_bff` 作为统一产品出口，而不是继续扩散前端直连领域接口。
- 已把盘前必读、盘后复盘和 Notion 输出放到第三阶段主线上，贴近当前产品目标。
- 已明确把“秒级全市场实时行情”“全量资金行为分析”从首批门槛中剥离。

### 1.5 当前设计的主要问题

- `stock_service` 的对象边界虽然变清晰了，但“股票事实对象层”和“实时推送链”仍存在语义重叠风险。
- `JYHF` 与 `Tushare` 的数据所有权边界已写入文档，但还没有冻结字段级真源策略。
- 复盘链与 Notion 输出链已经被放入主线，但“报告快照是唯一发布真源”这一点还需要被架构级强制。
- `P3.phase3` 的实时化设计仍然存在范围再次膨胀的风险，尤其是被误扩展成全市场高频行情平台。
- `ACCEPTANCE / WBS / CONTRACT` 还没有同步完整展开，当前仍停留在 Draft 级治理状态。

## 2. 风险矩阵（Risk Matrix，按优先级排序）

| 风险ID | 优先级 | 风险描述 | 影响范围 | 概率 | 发现难度 | 缓解措施 | Trigger | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-P3-001 | P0 | 第三阶段若重新把“秒级全市场实时行情”视为首批前提，会直接打穿当前阶段化设计 | `P3.phase1~3` 全体 | 高 | 低 | 冻结“快照优先、实时后置” ADR | 评审或实现中再次出现 `5000+ 股票秒级实时` 作为门槛 | 架构负责人 |
| R-P3-002 | P0 | `Tushare + JYHF` 已被确定为双源，但若不冻结字段级真源边界，后续会出现双写、双算、口径漂移 | `stock_service`、`recap_service`、前端、Notion | 高 | 中 | 冻结字段所有权与冲突裁决策略 | 同一字段从两个源分别计算且结果不一致 | 数据架构负责人 |
| R-P3-003 | P0 | 盘前必读、盘后复盘、Notion 若不强制共享同一份 snapshot，前后端与文档输出会长期漂移 | `recap_service`、`frontend_bff`、Notion | 高 | 中 | 冻结“快照唯一真源” ADR | 页面与 Notion 结论不一致 | 产品架构负责人 |
| R-P3-004 | P1 | `stock_service` 若过早吸收龙虎榜、分钟级异动、实时推送、复盘拼装，会再次变成巨型杂糅服务 | `stock_service`、后续维护成本 | 高 | 中 | 冻结对象层职责边界，聚合逻辑上移到 `recap_service` / BFF | 新需求不断直接压到 `stock_service` | 平台负责人 |
| R-P3-005 | P1 | `P3.phase2` 中资金行为分析的吸引力高，但当前外部源稳定性与成本尚不足，容易造成第二批目标膨胀 | 复盘增强、个股工作台 | 中 | 中 | 仅保留增强字段与轻量对象，不承诺全量能力 | 团队将“完整主力资金行为体系”纳入当前阶段 | 产品负责人 |
| R-P3-006 | P1 | `P3.phase3` 实时化若没有“REST first + SSE 增强 + 回补兜底”的明确顺序，客户端补拉和时序一致性会失控 | `/intel`、前端刷新链 | 中 | 高 | 固定 `REST + SSE` 双轨与回补策略 | 出现断线后永久缺口或顺序错乱 | 前端/BFF 负责人 |
| R-P3-007 | P1 | 轻量产业链视图若没有边界定义，极易在实现阶段演化成“半成品重型图谱服务” | `P3.phase3`、知识层 | 中 | 中 | 明确“只读层级视图，不是正式图谱真源” | 在未有稳定环节级真源前直接构建重型图谱表 | 知识图谱负责人 |
| R-P3-008 | P1 | 第三阶段虽已拆成 `phase0~3`，但 `PLAN_WBS / CONTRACT / TEST_CASE_SPEC` 未同步，治理链未闭合 | 项目执行、阶段验收 | 高 | 低 | 优先补 WBS 与 Contract | 研发准备执行但无法对账与验收 | 项目负责人 |
| R-P3-009 | P2 | `Tushare` 被定义为日频真源，但后续可能被误用于“涨停归因真因判断”，带来产品解释性风险 | 盘后复盘、涨停原因分析 | 中 | 中 | 冻结“资讯只能做候选归因，不做确定性真因” | 产品将资讯归因当成确定性结论输出 | 算法/产品联合负责人 |

## 3. 维度化发现（契约/一致性/性能/可观测性/可运维性）

### 3.1 契约

发现：

- 第三阶段 PRD 已明确 `P3.phase1 ~ 3` 的范围和阶段顺序。
- 但对象层契约仍缺少字段级冻结，尤其是：
  - `stock_daily_snapshot`
  - `stock_abnormal_event`
  - `theme_stock_leaderboard`
  - `pre_market_brief_snapshot`
  - `post_market_recap_snapshot`

判断：

- 当前最大契约风险不在接口名，而在对象层字段语义尚未被 ADR 固化。

建议：

- 冻结第三阶段首批对象层清单与字段所有权。
- 明确“页面和 Notion 只读快照，不重算结论”。

### 3.2 一致性

发现：

- 架构文档、PRD、ACCEPTANCE 现在已经在第三阶段分期上基本一致。
- `P3.phase0 = 历史的 P3.phaseA` 也已被文档化。
- 当前主要不一致来自治理层：`PLAN_WBS / PHASE_CONTRACT / TEST_CASE_SPEC` 尚未跟上。

判断：

- 第三阶段方向一致性已显著提升；
- 但仍属于“设计合同已收敛，执行合同未闭环”状态。

建议：

- 下一步优先补 `P3.phase1~3` 的 WBS 和 Phase Contract，而不是继续扩大设计范围。

### 3.3 性能

发现：

- `P3.phase1` 已经把性能重点收敛成：
  - 日频快照稳定生成
  - 报告重复生成一致
  - BFF P95 时延
- `P3.phase3` 才开始引入实时链延迟目标。

判断：

- 这比原始 `M4` 的“5000+ 股票、3 秒采样、600QPS、<100ms”更加现实。
- 但 `P3.phase3` 仍需防止性能目标反向污染前序阶段。

建议：

- 把 `P3.phase3` 的实时预算单独定义，不允许倒灌到 `P3.phase1/2`。

### 3.4 可观测性

发现：

- `ACCEPTANCE` 已为 `P3.phase1 ~ 3` 加入日志字段和指标要求。
- 但跨阶段仍缺少统一的 run_id / report_id / publish_id 贯穿规范。

判断：

- 目前可观测性要求有方向，但还不够“跨对象、跨输出层”统一。

建议：

- 对 snapshot 生成、BFF 读取、Notion 发布三段统一 trace 约定。

### 3.5 可运维性

发现：

- 当前设计已经把 Notion 输出单独抽为 publisher，而不是揉进服务层。
- 这是明显正确的。
- 但 `stock_service` 仍有被不断塞入“所有增强能力”的风险。

判断：

- 当前最大运维风险不是技术选型，而是职责持续膨胀。

建议：

- 用 ADR 冻结：`stock_service = 事实对象层`，`recap_service = 报告聚合层`，`notion_publisher = 输出层`。

## 4. 目标架构（Target Architecture）

### 4.1 本次评审认可的目标态

本次评审认可以下第三阶段目标态：

```text
JYHF (题材事件/题材池)
Tushare (股票日频真源)
    -> 标准化入库
    -> 股票事实对象层
    -> 状态与榜单派生

股票事实对象层 + 题材对象层
    -> recap_service
    -> pre/post snapshots

pre/post snapshots
    -> frontend_bff
    -> notion_publisher

phase3 增强:
    REST feed + SSE stream + minute-level abnormal + light chain view
```

### 4.2 需要进一步补强的目标态表达

- `JYHF` 与 `Tushare` 的字段真源表
- 快照对象层的固定字段清单
- `recap_service` 与 `stock_service` 的职责分割
- `REST` 与 `SSE` 双轨的回补时序

### 4.3 不建议的目标态实现方式

- 让 `stock_service` 同时承担：
  - 实时推送
  - 复盘拼装
  - Notion 输出
  - 高级分析
- 在没有固定快照对象前直接做 `/recap` 页面
- 用 `Tushare` 新闻/资讯直接给出“涨停真因”确定性判断
- 在 `P3.phase1` 直接追求“全市场秒级实时”

## 5. 迁移计划（Migration Plan）

### 5.1 推荐迁移顺序

#### Step 1: 冻结 `P3.phase0` 为统一产品出口基线

- 保持 `/api/*` 为前端唯一正式出口
- 历史 `P3.phaseA` 口径全部统一解释为 `P3.phase0`

#### Step 2: 冻结双源字段所有权

- `JYHF`: 题材事件、题材池、题材上下文
- `Tushare`: 股票日频事实、交易日历、基础证券信息

#### Step 3: 冻结快照对象层

- `stock_daily_snapshot`
- `subject_stock_daily_snapshot`
- `stock_abnormal_event`
- `theme_stock_leaderboard`
- `pre_market_brief_snapshot`
- `post_market_recap_snapshot`

#### Step 4: 完成 `P3.phase1 ~ 2`

- 先事实对象层
- 再复盘增强与工作台深化

#### Step 5: 最后进入 `P3.phase3`

- 在前序对象层稳定之后，再做 `SSE`、分钟级异动和轻量产业链视图

### 5.2 回滚原则

- `P3.phase3` 实时链必须可单独关闭，保留 `REST` 和既有快照主链
- Notion 发布失败不得阻塞 snapshot 落库
- 任一增强链失败时，都不得影响 `P3.phase1` 的日频对象层闭环

## 6. 子阶段方案（P3）

### P3.phase0

- 目标：前端统一产品出口
- 核心降风险点：禁止前端长期依赖领域服务

### P3.phase1

- 目标：双源事实层与基础复盘快照
- 核心降风险点：先建立稳定股票对象层，而不是先做实时流

### P3.phase2

- 目标：复盘增强与工作台深化
- 核心降风险点：让增强能力建立在对象层之上，不重新回到页面拼装

### P3.phase3

- 目标：实时化与高级增强
- 核心降风险点：实时链作为增强层，不得反向污染快照主链

## 7. ADR 建议清单（含触发条件与收益）

- `ADR-020` 双源字段所有权冻结
- `ADR-021` 第三阶段快照对象层冻结
- `ADR-022` `stock_service` 职责冻结为事实对象层
- `ADR-023` `recap_service` 作为唯一报告聚合层
- `ADR-024` Notion 只作为输出层
- `ADR-025` 实时链采用 `REST + SSE` 双轨
- `ADR-026` 分钟级异动晚于日频对象层
- `ADR-027` 轻量产业链视图不等于正式图谱真源
- `ADR-028` 涨停原因归因采用候选归因，不做确定性真因输出

## 8. 冲突裁决记录（Conflict Resolution）

### 冲突 1

- 采用来源：
  - [个人投资助理-项目架构设计-第三阶段.md](/Users/admin/Desktop/ai_theme_app/docs/architecture/个人投资助理-项目架构设计-第三阶段.md)
  - [PRD.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/PRD.md)
- 放弃来源：
  - 原始 `M4` 中“5000+ 股票、3 秒采样、600QPS、<100ms”作为第三阶段首批刚性门槛的口径
- 裁决理由：
  - 当前产品目标是盘前必读、盘后复盘与题材/股票联动，不是先做全市场高频行情平台。

### 冲突 2

- 采用来源：
  - 第三阶段架构文档中的 `Tushare + JYHF` 双源分工
- 放弃来源：
  - 任何单一数据源独立承担完整第三阶段产品链的方案
- 裁决理由：
  - `JYHF` 适合题材语义，`Tushare` 适合股票日频事实，单源都无法同时覆盖两类能力。

### 冲突 3

- 采用来源：
  - `P3.phase0 = 历史 P3.phaseA`
- 放弃来源：
  - 把 `P3.phaseA` 继续当成第三阶段外部特例
- 裁决理由：
  - 第三阶段需要完整 phase 结构，历史命名应兼容但不能继续破坏阶段语义。

## 9. 非目标范围（Non-Goals）

- 不在本次评审中推进任何业务代码实现。
- 不把第三阶段重新定义为高频量化行情平台。
- 不直接扩展到重型产业链图谱服务。
- 不在当前阶段承诺完整资金行为全量分析。

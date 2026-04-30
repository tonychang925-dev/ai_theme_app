# ARCH REVIEW — P4.phase0（前端第四阶段）架构评审

## 1. 当前架构摘要（Current Architecture Summary）
- 当前前端第四阶段采用“三栏作战台 + 统一 `/api/v2/*` 出口”路线，技术栈与产品形态合理。
- 实时链路采用 `SSE 主通道 + feed 兜底`，与当前数据链路成熟度匹配。
- 代码侧已完成关键收口：`frontend/src` v2 路由统一、v2 contract tests、A/B/D 核心门禁脚本可执行。
- 主要差距从“实现缺失”转为“连续运行指标与治理闭环”。

## 2. 风险矩阵（Risk Matrix）
| 风险ID | 等级 | 风险描述 | 影响范围 | 概率 | 发现难度 | Trigger | 缓解措施 | Owner |
|---|---|---|---|---|---|---|---|---|
| R-P4-001 | P0 | 接口口径漂移导致 405/契约回退 | `/intel` 主链路 | 中 | 中 | 前端新增非 v2 路径/后端缺 v2 别名 | CI 路径阻断 + v2 contract tests + 路由兼容层 | FE/BFF |
| R-P4-002 | P0 | SSE 不稳定导致中栏不可用 | Intel 实时面板 | 中 | 中 | stream 建连失败率升高 | 自动重连 + feed fallback + 事件白名单 | FE/BFF |
| R-P4-003 | P1 | 连续 5 交易日门槛未达标 | 阶段准入 | 中 | 低 | 成功率/覆盖率波动 | 灰度分批 + 回滚矩阵 + 日报审计 | Release/QA |
| R-P4-004 | P1 | DTO 字段演进无约束引发前端崩溃 | 三栏所有面板 | 低 | 中 | 字段语义变更/删除 | DTO 兼容规则（只增不破）+ 契约文档门禁 | BE/BFF |
| R-P4-005 | P2 | 工作台页面扩展过早侵蚀稳定期 | 迭代节奏 | 中 | 低 | 并行功能过多 | 冻结窗口 + Feature Flag 治理 | PM/Tech Lead |

## 3. 维度化发现

### 3.1 契约与一致性
- 优点：`/api/v2/*` 收口方向正确；已补 contract test。
- 问题：历史文档存在 `strong_watch` 路由双口径，需要持续单一真源化。

### 3.2 性能与稳定性
- 优点：SSE + feed 兜底设计合理，失败可降级。
- 问题：缺“连续 5 交易日”自动化统计产物与趋势告警面板。

### 3.3 可观测性
- 优点：已有门禁命令可复现。
- 问题：缺统一指标采集（stream 成功率、fallback 次数、reconnect 分布）。

### 3.4 可运维性
- 优点：有灰度开关矩阵与回滚思路。
- 问题：回滚演练结果未形成固定模板/审计记录标准。

## 4. 目标架构（Target Architecture）
- 入口层：`frontend` 仅消费 `/api/v2/*`。
- 聚合层：`frontend_bff` 作为前端唯一业务聚合出口（兼容期允许旧路由别名，但不得被前端依赖）。
- 实时层：`/api/v2/intel/stream` + `/api/v2/intel/feed` 自动降级闭环。
- 对象层：workspace 三接口固定 DTO，字段仅增量演进。
- 门禁层：CI（路径阻断 + contract tests）+ 发布前回放门禁（A/B/D）。

## 5. 迁移计划（Migration Plan）
1. M0（已完成）：v2 收口、405 修复、contract tests 入 CI。  
2. M1（1周）：补齐运行指标采集与日报（feed/stream 成功率、fallback、重连）。  
3. M2（1周）：固化回滚演练剧本与审计模板（RTO<=5分钟）。  
4. M3（持续）：移除前端对兼容旧别名的潜在依赖，推进单一路由真源。  

## 6. 子阶段方案（phase 模式）
- `P4.phase0`：统一出口 + 三栏最小可用 + 门禁就绪（当前）
- `P4.phase1`：连续运行指标达标（5交易日）+ 回滚演练闭环
- `P4.phase2`：扩大页面迁移范围（themes/stocks/screener 等）并保持契约稳定

## 7. ADR 建议清单（摘要）
- ADR-001：统一前端路由口径为 `/api/v2/*` 并以 CI 阻断。
- ADR-002：实时链路采用 `SSE-first + feed fallback`，WS 非必选。
- ADR-003：BFF 作为前端聚合唯一真源（兼容期保留别名）。
- ADR-004：发布门禁采用“回放一致性 + 覆盖率阈值 + 契约测试”三重判据。

## 8. 冲突裁决记录
- 冲突1：`/api/v2/intel/strong-stocks/watch` vs `/api/v2/strong_watch`
  - 裁决：前端统一调用前者；后者作为内部/兼容口径。
- 冲突2：SSE 与 WS 优先级
  - 裁决：SSE 主通道先落地，WS 后置，不阻塞阶段通过。

## 9. 非目标范围（Non-Goals）
- 不在本阶段引入 Tick 级全市场实时平台。
- 不在本阶段完成产业链独立图谱服务化。
- 不在本阶段放开所有页面的大规模功能扩展。

---

## 10. 增量评审记录（2026-04-30，追加）

### 10.1 本次增量范围
- 仅补充第四阶段前端架构的“代码对齐状态 + 门禁可执行性”。
- 不重写第 1~9 节结论，不替换历史裁决。

### 10.2 代码对齐结论（增量）
1. 前端 `frontend/src` 已完成 `/api/v2/*` 路径收口，且 CI 阻断规则已生效。  
2. `/api/v2/intel/feed`、`/api/v2/intel/stream`、`/api/v2/workspace/*` 已具备可用性。  
3. `SSE 主通道 + feed fallback` 已形成可运行闭环。  
4. 强势股页面读口按评审裁决统一为 `/api/v2/intel/strong-stocks/watch`。  

### 10.3 门禁证据（增量）
- v2 contract tests：`frontend_bff/tests/unit/test_v2_contract_aliases.py`（通过）。  
- D 层输入收口单测（7日窗口/Universe/Admission）已通过。  
- A/B 回放目标日期已执行，无差异样本通过。  
- Layer B confirmed 覆盖率达到 >=95% 门槛（当前样本 >95%）。  

### 10.4 待完成项（增量）
1. 连续 5 个交易日的运行指标报表（feed 成功率、stream 连接成功率、fallback 次数）需形成固定日报。  
2. 回滚演练记录需补“执行时间、RTO、失败注入场景、结论”模板化归档。  
3. 兼容期结束后，清理不再被前端消费的旧别名路由，减少双口径维护成本。  

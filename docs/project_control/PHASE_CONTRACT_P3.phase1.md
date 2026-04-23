# Phase Execution Contract

## 1. Phase Identity

- Phase Name: stock_processing_service 对象层收口
- Phase Code: `P3.phase1`
- Parent Milestone: `P3`
- Risk Level: `P0`
- Source Documents:
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/prd_p3.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 数据访问边界 | `DatabaseGateway` 显式领域 API | 业务层直连 `_client/_db` | 执行 Gateway First |
| SQL 入口 | 领域方法读写 | 业务路径 `execute_query` | 避免回退到“服务写 SQL” |
| 对象消费真源 | 6 个冻结对象 | 消费端二次重算 | 保障口径一致和可审计 |

## 2. Phase Objective（可量化）

1. 新建 `stock_processing_service` 并作为唯一新生产链路。
2. 打通 `输入事件 -> 快照对象 -> 发布事件` 标准闭环。
3. 完成 `DatabaseGateway` 股票域高层接口升级并收口业务 SQL。
4. 冻结对象、DTO、事件 envelope、ports、feature flag 协议。

## 3. Acceptance Targets（门禁条件）

- [ ] `ACPT-P3B-011` 必须确认 `stock_processing_service` 作为股票日频对象层唯一新生产链路，旧 `stock_service` 仅用于回退/对账/实验。
- [ ] `ACPT-P3B-012` 所有股票侧业务读写必须通过 `database_service.DatabaseGateway` 股票域显式方法，禁止 `_client/_db` 直达。
- [ ] `ACPT-P3B-013` 领域层必须保持 `Domain Pure`：不依赖数据库/缓存/消息总线实现细节。
- [ ] `ACPT-P3B-014` 六个冻结对象必须具备字段级最小 schema，且主键、必填字段、覆盖策略与架构文档一致。
- [ ] `ACPT-P3B-015` 所有 stock stream 事件必须采用统一 envelope：`event_id/event_name/trade_date/batch_id/trace_id/producer/occurred_at/payload_version/payload`。
- [ ] `ACPT-P3B-016` 缓存必须执行“先写新版本、后原子切换 current”策略，禁止读到半成品。
- [ ] `ACPT-P3B-017` 双轨对账每次必须输出 `summary + diff_samples.jsonl`，且样本包含主键、旧值、新值、差异字段、差异原因分类。
- [ ] `ACPT-P3B-018` 程序设计前置门禁（contracts/ports/gateway/feature-flag）未全部冻结时不得开工。
- [ ] `ACPT-P3B-019` `DatabaseGateway` 必须完成股票域高层领域网关升级：业务侧仅可调用显式领域 API，不得透传 `_client` 语义。
- [ ] `ACPT-P3B-020` 股票业务路径中 `execute_query` 调用次数必须为 0（仅允许基础设施内部或离线运维脚本使用）。
- [ ] `ACPT-P3B-021` 必须形成标准化闭环：`输入事件 -> 快照对象 -> 发布事件`，并可回放、可审计、可幂等。
- [ ] `ACPT-P3B-022` 6 个冻结对象必须成为唯一消费真源，BFF/Notion 不得绕过对象层重算核心结论。

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q stock_processing_service/tests`
- `.venv/bin/python -m pytest -q database_service/tests`
- `rg -n "execute_query\(|_client\.|_db\.|import asyncpg" stock_processing_service database_service`
- `.venv/bin/python scripts/build_post_market_recap.py --help`

## 5. Deliverables

- `stock_processing_service` 四层架构与 ports
- 6 个冻结对象 schema + DTO + envelope
- `DatabaseGateway` 股票域显式 API 集
- `execute_query` 业务路径收口证据
- 对账产物 `summary + diff_samples.jsonl`
- `tmp/phase_contract_P3.phase1.json`
- `tmp/phase_contract_consistency_P3.phase1.json`

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 网关升级不彻底 | High | High | 业务仍直连 SQL | Backend | 静态扫描 + CI 阻断 |
| 对象口径漂移 | High | Medium | 多处拼装结论 | Arch | 对象层唯一真源 |
| 闭环断裂 | High | Medium | 无事件发布或不可回放 | Data | 闭环验收脚本 |

## 7. Rollback Plan

- 代码回滚：feature flag 切回旧链路（只读回退）。
- 数据回滚：按 `trade_date/batch_id` 回滚新对象批次。
- 同步补偿回滚：重放输入事件，重建快照并重发事件。

## 8. Non-Goals

- 不做分钟级实时行情。
- 不做 Tick 级引擎。
- 不让前端直接读取领域原表。

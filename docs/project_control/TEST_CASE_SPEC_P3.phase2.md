# TEST CASE SPEC — P3.phase2

## 0. 范围与原则
- 目标：对齐 [FEATURE_SPEC_P3.phase2.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/FEATURE_SPEC_P3.phase2.md) 与 [PHASE_CONTRACT_P3.phase2.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/PHASE_CONTRACT_P3.phase2.md)，为 `龙虎榜结构化对象 -> 资金行为增强 -> F10 资金快照增强 -> 个股工作台 -> /recap -> 来源链 -> 跨交易日一致性` 建立正式测试规范。
- 执行模式：`execution_mode=real`，`allow_mock=false`。
- 关键依赖：`postgres,tushare,jyhf,frontend_bff,theme_service`。
- 默认测试库：`stock_data_test`。
- 证据字段：`trade_date,subject_key,stock_id,source_type,source_trace_id,source_version,rule_version,report_type,workspace_route`。
- 当前阶段门禁原则：
  - 必须遵循 `UT -> IT -> ST/RT` 顺序。
  - 必须先验证对象层，再验证消费层，再验证跨交易日一致性。
  - 若真源表构建失败，则 `/recap`、个股工作台与报告快照测试必须标记 `BLOCKED`。

## 0.1 测试层级与阻塞规则

### Layer-1 `UT`
- 覆盖对象：
  - `mainline_judgement_service.py`
  - `cycle_judgement_service.py`
  - `leader_candidate_service.py`
  - `money_flow_enhanced_service.py`
  - `dragon_tiger_object_service.py`
  - `pre_market_execution_service.py`
  - `recap_service.py`
- 阻塞规则：
  - 任一真源规则服务 `UT` 失败，则对应构建脚本 `IT/ST` 标记 `BLOCKED`。
  - `recap_service.py` 的 `UT` 未通过，不得执行 `/recap` 出口验证。

### Layer-2 `IT`
- 覆盖对象：
  - `build_theme_mainline_judgement.py`
  - `build_theme_cycle_judgement.py`
  - `build_theme_leader_candidate.py`
  - `build_money_flow_enhanced.py`
  - `build_pre_market_execution_plan.py`
  - `build_dragon_tiger_object.py`
  - `frontend_bff` 个股工作台与 `/recap`
- 阻塞规则：
  - 真源表构建失败，则前端/BFF 消费测试标记 `BLOCKED`。
  - `dragon_tiger_object` 或 `money_flow_enhanced` 构建失败，则增强型复盘测试标记 `BLOCKED`。

### Layer-3 `ST/RT`
- 覆盖对象：
  - 真实交易日 `2026-04-01`
  - 真实交易日 `2026-04-02`
  - `2026-04-03` 盘前承接计划
  - 跨交易日一致性检查
- 阻塞规则：
  - 任一交易日来源链覆盖率不达 `100%`，阶段不得判定通过。

## 1. 验收级 TC
- `TC-P3.phase2-UT-001` 主线判断规则单元测试
- `TC-P3.phase2-UT-002` 周期判断规则单元测试
- `TC-P3.phase2-UT-003` 龙头候选与角色分层单元测试
- `TC-P3.phase2-UT-004` 资金行为增强单元测试
- `TC-P3.phase2-UT-005` 龙虎榜对象与来源链单元测试
- `TC-P3.phase2-UT-006` 盘前承接计划单元测试
- `TC-P3.phase2-UT-007` `recap_service` 快照聚合单元测试
- `TC-P3.phase2-UT-008` `F10` 资金动向 parser 单元测试
- `TC-P3.phase2-IT-001` `dragon_tiger_object` 真数据 smoke
- `TC-P3.phase2-IT-002` `theme_mainline_judgement / theme_cycle_judgement / theme_leader_candidate / money_flow_enhanced` 真库构建
- `TC-P3.phase2-IT-003` 个股工作台增强 DTO 集成验证
- `TC-P3.phase2-IT-004` `/recap` 只读产品出口集成验证
- `TC-P3.phase2-IT-005` `F10` 快照读写与挂载集成验证
- `TC-P3.phase2-ST-001` `2026-04-01` 真实盘后复盘快照生成
- `TC-P3.phase2-ST-002` `2026-04-03` 真实盘前必读快照生成
- `TC-P3.phase2-RT-001` `2026-04-01 / 2026-04-02` 跨交易日一致性检查
- `TC-P3.phase2-RT-002` `F10` 增强不影响评分结果回归

## 2. 功能分解对齐矩阵

| Feature 子功能 | 验收级 TC | 子用例 ID | 优先级 | 状态 |
| --- | --- | --- | --- | --- |
| `F-P3.phase2-T01-01` 龙虎榜原始源接入 | IT-001 | `TC-P3.phase2-F-T01-01` | P0 | In Scope |
| `F-P3.phase2-T01-02` 席位摘要聚合 | UT-005 / IT-001 | `TC-P3.phase2-F-T01-02` | P0 | In Scope |
| `F-P3.phase2-T01-03` 来源链回溯 | UT-005 / RT-001 | `TC-P3.phase2-F-T01-03` | P0 | In Scope |
| `F-P3.phase2-T02-01` 资金行为增强字段 | UT-004 / IT-002 | `TC-P3.phase2-F-T02-01` | P0 | In Scope |
| `F-P3.phase2-T02-02` 题材角色规则增强 | UT-003 / IT-002 | `TC-P3.phase2-F-T02-02` | P0 | In Scope |
| `F-P3.phase2-T02-03` 规则解释字段 | UT-004 / ST-001 | `TC-P3.phase2-F-T02-03` | P1 | In Scope |
| `F-P3.phase2-T03-01` 个股工作台增强 DTO | IT-003 | `TC-P3.phase2-F-T03-01` | P0 | In Scope |
| `F-P3.phase2-T03-02` `/recap` 只读产品出口 | IT-004 | `TC-P3.phase2-F-T03-02` | P0 | In Scope |
| `F-P3.phase2-T03-03` 前端兼容门禁 | IT-003 / IT-004 | `TC-P3.phase2-F-T03-03` | P0 | In Scope |
| `F-P3.phase2-T04-01` 来源链标准化 | RT-001 | `TC-P3.phase2-F-T04-01` | P0 | In Scope |
| `F-P3.phase2-T04-02` 聚合层唯一化 | UT-007 / IT-004 | `TC-P3.phase2-F-T04-02` | P0 | In Scope |
| `F-P3.phase2-T04-03` 模板兼容 | ST-001 / ST-002 | `TC-P3.phase2-F-T04-03` | P1 | In Scope |
| `F-P3.phase2-T05-01` `F10` 资金动向快照落库 | UT-008 / IT-005 | `TC-P3.phase2-F-T05-01` | P0 | In Scope |
| `F-P3.phase2-T05-02` 资金动向正文解析 | UT-008 / IT-005 | `TC-P3.phase2-F-T05-02` | P0 | In Scope |
| `F-P3.phase2-T05-03` 复盘 review 挂载 | IT-005 / RT-002 | `TC-P3.phase2-F-T05-03` | P0 | In Scope |
| `F-P3.phase2-T05-04` `1进2` 观察计划挂载 | IT-005 / RT-002 | `TC-P3.phase2-F-T05-04` | P0 | In Scope |
| `F-P3.phase2-T05-05` 前端展示增强 | IT-005 | `TC-P3.phase2-F-T05-05` | P1 | In Scope |

## 3. 子用例详细分解

### TC-P3.phase2-F-T01-01
- 级别：IT，优先级：P0
- 目标：`Tushare top_list/top_inst` 必须生成 `dragon_tiger_object`
- 前置：
  - `TUSHARE_TOKEN` 可用
  - 本机网络可访问 `api.waditu.com`
- 核心断言：
  - `top_list_row_count > 0`
  - `top_inst_row_count > 0`
  - `dragon_tiger_object_count > 0`
  - raw snapshot 成功落盘

### TC-P3.phase2-F-T01-03
- 级别：RT，优先级：P0
- 目标：龙虎榜来源链必须可追溯
- 核心断言：
  - `dragon_tiger_object.source_trace_id` 非空
  - `dragon_tiger_object.source_trace` 非空
  - `source_version/rule_version` 非空

### TC-P3.phase2-F-T02-01
- 级别：IT，优先级：P0
- 目标：资金行为增强对象可稳定生成
- 核心断言：
  - `money_flow_enhanced` 对应交易日成功写入
  - `money_flow_score`、`money_flow_tier`、`role_enhanced` 非空
  - `sources` 包含 `theme_leader_candidate`

### TC-P3.phase2-F-T02-02
- 级别：UT/IT，优先级：P0
- 目标：角色增强规则明确区分 `龙头/前排/扩散/跟风`
- 核心断言：
  - `theme_leader_candidate.role_label` 可重放
  - `money_flow_enhanced.role_enhanced` 与规则一致

### TC-P3.phase2-F-T03-01
- 级别：IT，优先级：P0
- 目标：个股工作台必须由 `frontend_bff` 返回统一 DTO
- 核心断言：
  - 返回 `stock_detail`
  - 返回 `themes`
  - 返回 `money_flow`
  - 返回 `dragon_tiger`
  - 前端不自行拼装底层多源数据

### TC-P3.phase2-F-T03-02
- 级别：IT，优先级：P0
- 目标：`/api/recap` 提供只读产品出口
- 核心断言：
  - 支持 `post_market`
  - 支持 `pre_market`
  - 返回 `title / summary / highlights / sections`

### TC-P3.phase2-F-T04-01
- 级别：RT，优先级：P0
- 目标：四张增强真源表的来源链覆盖率必须为 `100%`
- 核心断言：
  - `theme_mainline_judgement`
  - `theme_cycle_judgement`
  - `theme_leader_candidate`
  - `money_flow_enhanced`
  对于指定交易日均满足：
  - `missing_source_type = 0`
  - `missing_trace_id = 0`
  - `missing_trace_payload = 0`
  - `missing_source_version = 0`
  - `missing_rule_version = 0`

### TC-P3.phase2-F-T04-02
- 级别：UT/IT，优先级：P0
- 目标：`recap_service` 是唯一聚合层
- 核心断言：
  - 盘后仅读取真源表与增强对象
  - 盘前仅读取 `pre_market_execution_plan`
  - `/recap` 页面端不得重算核心结论

### TC-P3.phase2-F-T05-01
- 级别：UT/IT，优先级：P0
- 目标：`F10` 资金动向正文必须能稳定解析为快照结构
- 前置：
  - 已有一条 `000001` 资金动向样本文本
- 核心断言：
  - 能切出 5 个子段
  - 能识别 `交易龙虎榜` 为空/暂无语义
  - 能解析 `融资融券` 的最新日期
  - 能提取 `资金流向` 的主力净额

### TC-P3.phase2-F-T05-02
- 级别：UT/IT，优先级：P0
- 目标：`F10` 快照服务必须把正文映射成统一增强结构
- 核心断言：
  - `source=tdx_f10` 且 `section=资金动向`
  - `dragon_tiger / block_trade / margin_trading / capital_flow / strategic_lending` 均存在
  - `source_flags` 可反映命中段落
  - `L2` 涨停分析不进入标准快照结构

### TC-P3.phase2-F-T05-03
- 级别：IT，优先级：P0
- 目标：`F10` 快照挂载到复盘 review 后，不改变主事实语义
- 核心断言：
  - `money_flow_reviews[*].f10_capital` 存在
  - `stock_capital_reviews[*].f10_capital` 存在
  - `dragon_tiger_reviews[*].f10_capital` 存在
  - 缺快照时复盘仍成功

### TC-P3.phase2-F-T05-04
- 级别：IT，优先级：P0
- 目标：`1进2` 观察计划仅挂载展示字段，不影响评分结果
- 核心断言：
  - `post_market_setup_plan.items[*].f10_capital` 存在
  - `decision` 不变
  - `final_score` 不变
  - `watch_level` 不变

### TC-P3.phase2-F-T05-05
- 级别：RT，优先级：P1
- 目标：`F10` 增强不影响评分回归
- 核心断言：
  - 同一只候选有无 `f10_capital`，评分结果保持一致
  - `observe_only` / `focus` 分层不因 `F10` 变动
  - `missing_count` 只影响展示诊断，不阻断阶段通过

## 4. 必跑命令

### 4.1 UT
```bash
.venv/bin/python -m pytest -q \
  stock_service/tests/unit/test_p3_phase2_mainline_judgement_service.py \
  stock_service/tests/unit/test_p3_phase2_cycle_judgement_service.py \
  stock_service/tests/unit/test_p3_phase2_leader_candidate_service.py \
  stock_service/tests/unit/test_p3_phase2_money_flow_enhanced_service.py \
  stock_service/tests/unit/test_p3_phase2_dragon_tiger_object_service.py \
  stock_service/tests/unit/test_p3_phase2_pre_market_execution_service.py \
  stock_service/tests/unit/test_p3_phase1_t04_recap_and_snapshot.py
```

### 4.2 IT
```bash
.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_p3_phasea_bff_real_db.py
```

```bash
/opt/miniconda3/bin/python scripts/stock_service_smoke_tushare_dragon_tiger.py --trade-date 2026-04-01 --token <TOKEN> --force-refresh
```

```bash
.venv/bin/python database_service/scripts/build_theme_mainline_judgement.py --trade-date 2026-04-01
.venv/bin/python database_service/scripts/build_theme_cycle_judgement.py --trade-date 2026-04-01
.venv/bin/python database_service/scripts/build_theme_leader_candidate.py --trade-date 2026-04-01
.venv/bin/python database_service/scripts/build_money_flow_enhanced.py --trade-date 2026-04-01
```

### 4.3 ST / RT
```bash
.venv/bin/python scripts/stock_service_generate_report_snapshot.py --trade-date 2026-04-02 --report-type post_market --suffix p3_phase2_20260402
.venv/bin/python scripts/stock_service_generate_report_snapshot.py --trade-date 2026-04-03 --report-type pre_market --suffix p3_phase2_20260403
```

```bash
.venv/bin/python scripts/phase2_consistency_check.py --dates 2026-04-01 2026-04-02
```

## 5. 未覆盖范围
- 不覆盖 `P3.phase3` 的 `SSE/分钟级异动`
- 不覆盖完整主力资金行为体系
- 不覆盖 Tick 级盘口
- 不覆盖大规模回测结论优劣评估

## 6. 通过判定
- 所有 P0 用例必须通过
- 来源链覆盖率必须为 `100%`
- `/recap` 和个股工作台必须稳定消费真源结果
- 不得因为 `P3.phase2` 破坏 `P3.phase1` DTO 兼容

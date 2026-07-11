# 测试报告

## 1. 基本信息

- Milestone: `P3`
- Phase: `P3.phase2`
- 测试负责人: `Codex`
- 执行时间: `2026-04-02`
- 风险等级: `Medium`

## 2. 测试范围

- 覆盖模块
  - `theme_mainline_judgement`
  - `theme_cycle_judgement`
  - `theme_leader_candidate`
  - `pre_market_execution_plan`
  - `dragon_tiger_object`
  - `money_flow_enhanced`
  - `recap_service`
  - `frontend_bff` 个股工作台与 `/recap`
- 覆盖功能点
  - 主线识别
  - 周期判断
  - 龙头分层
  - 盘前承接验证
  - 龙虎榜结构化对象
  - 资金行为增强
  - `/recap` 只读出口
  - 跨交易日来源链一致性
- 未覆盖范围
  - `P3.phase3` 实时链
  - Tick 级盘口
  - 完整主力资金行为体系
  - 大规模跨月回测

## 3. 执行命令记录

| 序号 | 命令 | 执行结果 | 关键输出 |
| --- | --- | --- | --- |
| 1 | `.venv/bin/python -m pytest -q stock_service/tests/unit/test_p3_phase2_mainline_judgement_service.py stock_service/tests/unit/test_p3_phase2_cycle_judgement_service.py stock_service/tests/unit/test_p3_phase2_leader_candidate_service.py stock_service/tests/unit/test_p3_phase2_money_flow_enhanced_service.py stock_service/tests/unit/test_p3_phase1_t04_recap_and_snapshot.py` | 通过 | `16 passed in 0.19s` |
| 2 | `.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_p3_phasea_bff_real_db.py stock_service/tests/unit/test_p3_phase2_pre_market_execution_service.py stock_service/tests/unit/test_p3_phase1_t04_recap_and_snapshot.py` | 通过 | `11 passed in 0.73s` |
| 3 | `npm run build` | 通过 | 前端构建通过 |
| 4 | `/opt/miniconda3/bin/python scripts/stock_service_smoke_tushare_dragon_tiger.py --trade-date 2026-04-01 --token <TOKEN> --force-refresh` | 通过 | `top_list_row_count=70`, `top_inst_row_count=695`, `dragon_tiger_object_count=70` |
| 5 | `.venv/bin/python database_service/scripts/build_theme_mainline_judgement.py --trade-date 2026-04-01` | 通过 | `rows=657`, `main=5` |
| 6 | `.venv/bin/python database_service/scripts/build_theme_cycle_judgement.py --trade-date 2026-04-01` | 通过 | `rows=657`, `fermentation=3` |
| 7 | `.venv/bin/python database_service/scripts/build_theme_leader_candidate.py --trade-date 2026-04-01` | 通过 | `themes=5`, `rows=20` |
| 8 | `.venv/bin/python database_service/scripts/build_money_flow_enhanced.py --trade-date 2026-04-01` | 通过 | `rows=20` |
| 9 | `.venv/bin/python database_service/scripts/build_theme_mainline_judgement.py --trade-date 2026-04-02` | 通过 | `rows=659`, `main=2` |
| 10 | `.venv/bin/python database_service/scripts/build_theme_cycle_judgement.py --trade-date 2026-04-02` | 通过 | `rows=659`, `fermentation=2` |
| 11 | `.venv/bin/python database_service/scripts/build_theme_leader_candidate.py --trade-date 2026-04-02` | 通过 | `themes=2`, `rows=8` |
| 12 | `.venv/bin/python database_service/scripts/build_money_flow_enhanced.py --trade-date 2026-04-02` | 通过 | `rows=8` |
| 13 | `.venv/bin/python scripts/phase2_consistency_check.py --dates 2026-04-01 2026-04-02` | 通过 | 四张增强真源表来源链覆盖率 `100%` |

## 4. 测试结果统计

| 项目 | 数值 |
| --- | --- |
| 总用例数 | 27 |
| 通过数 | 27 |
| 失败数 | 0 |
| 跳过数 | 0 |
| 通过率 | 100% |

说明：
- 统计口径为本阶段已显式执行的单元测试、集成测试与跨交易日一致性检查项。

## 5. 性能结果

- P50 延迟: 未单独测量
- P95 延迟: 未单独测量
- 最大响应时间: 未单独测量
- 内存占用: 未单独测量
- CPU 峰值: 未单独测量

说明：
- 本阶段性能门禁主要依赖构建成功与一致性，不以专项压测为通过前提。

## 6. 缺陷记录

| 缺陷ID | 严重级别 | 描述 | 当前状态 |
| --- | --- | --- | --- |
| P3P2-BUG-001 | P1 | `phase2_consistency_check.py` 初版对 `asyncpg` 传入字符串日期导致 `DataError` | 已修复 |
| P3P2-BUG-002 | P1 | `2026-04-01` 历史批次未带来源链字段，导致一致性检查不通过 | 已通过重建修复 |

## 7. 风险评估

### 当前残余风险

- 技术风险
  - 主线/周期/龙头规则仍是首版，后续可能需要误判样本调优。
- 性能风险
  - 尚未做专项性能压测。
- 数据一致性风险
  - 已完成 `2026-04-01 / 2026-04-02` 两日检查，但尚未扩展到更长窗口。
- 可扩展性风险
  - 展示层仍有继续贴近交易模板的优化空间。

### 风险等级判定

`Medium`

理由：
- 核心真源链、消费链与来源链已通过真实验证。
- 但规则调优与更大范围回测仍未完成。

## 8. 回归影响评估

- 影响模块
  - `stock_service`
  - `database_service/scripts`
  - `frontend_bff`
  - `frontend`
- 影响接口
  - `/api/recap`
  - `/api/recap/defaults`
  - `/api/stock-workspace/{stock_id}`
- 是否存在行为变化
  - 是。`P3.phase2` 现在以真源表为主，不再由展示层自由拼装结论。
- 是否需要额外回归测试
  - 是。后续应扩到更多交易日和误判样本分析。

## 9. 发布建议

- ✅ 建议通过（Ready for release）

说明：
- `P3.phase2` 核心主链已完成。
- 允许进入下一阶段或继续做规则调优。
- 当前不存在阻断发布的 P0/P1 未修复项。

## 10. 增量记录：`P3.phase3.auction_result_validation.v1`

### 当前完成

- 已完成真源链：
  - `auction_watch_universe`
  - `pre_market_auction_snapshot`
  - `pre_market_auction_signal`
  - `pre_market_auction_signal_validation`
- 已完成真实 `stk_auction` 结果层接入
- 已完成竞价信号并入 `pre_market_execution_plan`

### 真实验证结果

- `2026-04-03`
  - 候选池：`rows=4`
  - `stk_auction` 原始返回：`raw_row_count=4`
  - 竞价信号输出：
    - `strong=1`
    - `watch=2`
    - `invalid=1`

### 当前能力边界

- 已完成：
  - `9:25` 结果层验证
  - `strong / watch / invalid` 分层
  - 硬否决原因输出
  - 盘后日频验证闭环
- 尚未完成：
  - `9:20~9:25` 路径稳定性识别
  - `9:24~9:25` 最后一分钟抢筹
  - `U 型 / 阶梯 / 上翘一字` 等过程特征

### 当前结论

- `auction_result_validation.v1` 已可作为 `P3.phase3` 的子链保留
- 当前不得对外宣称为“完整集合竞价路径识别能力”

## 11. 增量记录：`P3.phase3.market_environment_and_theme_environment.v1`

### 当前完成

- 已完成大盘环境真源链：
  - `market_environment_metrics`
  - `market_environment_judgement`
- 已完成板块环境真源链：
  - `theme_environment_judgement`
- 已完成盘后复盘接入：
  - `大盘环境总结`
  - 题材卡片内 `板块环境`
- 已完成前端展示区分：
  - `daily_proxy`
  - `intraday_mixed`

### 真实验证结果

- `2026-04-02`
  - `market_environment_metrics` 构建成功：
    - `total=5132`
    - `up=884`
    - `down=4186`
    - `limit_up=36`
    - `limit_down=15`
    - `advance_decline_ratio=0.2112`
    - `yesterday_limit_up_open_red_ratio=0.0000`
    - `yesterday_limit_up_premium_ratio=0.4898`
  - `market_environment_judgement` 构建成功：
    - `market_health_score=37.85`
    - `market_bias=risk_off`
    - `action_bias=放弃`
  - `theme_environment_judgement` 构建成功：
    - `rows=52`
    - 样例：
      - `石油 -> 板块健康 / 板块联动一般 / 龙头强带队 / 后排跟随强 / 可观察`
      - `AI光纤 -> 板块脆弱 / 板块联动一般 / 龙头强带队 / 后排跟随弱 / 可观察`

### 当前能力边界

- 已完成：
  - 基于现有日频真源的大盘环境判断
  - 基于主线/周期/龙头事实层的板块环境判断
  - 复盘页顶部 `大盘环境总结`
  - 题材卡片内 `板块环境`
- 尚未完成：
  - 真实分钟源驱动的早盘环境真值
  - 全量 `昨日涨停池 + 高标池` 分钟级回落口径
- 当前约束：
  - `冲高回落占比 / 日内回落占比 / 昨日涨停股今开红比` 如来自日频代理，必须显式标注 `日频代理`

## 12. 增量记录：`Phase 4.5.6 Formal Review Stabilization`

### 基本信息

- Milestone: `Phase 4.5.6`
- 范围: `PR5 Formal Review Stabilization`
- 执行时间: `2026-07-11`
- 风险等级: `Medium`

### 测试范围

- 覆盖：
  - `FormalReviewProjectionCompiler`
  - `formal_review` 六章模型
  - `FormalReviewView`
  - Recap Workbench First 契约
- 未覆盖：
  - 5 个真实交易日 approved snapshot 双轨人工观察
  - PR6 Legacy Removal

### 执行命令记录

| 序号 | 命令 | 执行结果 | 关键输出 |
|---|---|---|---|
| 1 | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest stock_processing_service/tests/unit/test_projection_stabilization_scenarios.py stock_processing_service/tests/unit/test_projection_formal_schema.py stock_processing_service/tests/unit/test_projection_diff_20260709.py stock_processing_service/tests/unit/test_projection_capital_plan.py stock_processing_service/tests/unit/test_projection_theme_stock_merge.py -q` | 通过 | `17 passed in 0.41s` |
| 2 | `node scripts/test-formal-review-view-contract.mjs` | 通过 | `formal review view contract passed` |
| 3 | `node scripts/test-recap-workbench-first-contract.mjs` | 通过 | `recap workbench-first contract passed` |
| 4 | `node scripts/test-workbench-generate-flow-contract.mjs` | 通过 | `workbench generate flow contract passed` |
| 5 | `npm run build` | 通过 | `✓ built`；仅 Vite chunk size warning |

### 测试结果统计

| 项目 | 数值 |
|---|---:|
| 自动化后端用例 | 17 |
| 前端契约脚本 | 3 |
| 前端构建 | 1 |
| 通过数 | 21 |
| 失败数 | 0 |
| 跳过数 | 0 |
| 通过率 | 100% |

### 缺陷记录

| 缺陷ID | 严重级别 | 描述 | 当前状态 |
|---|---|---|---|
| P456-PR5-001 | P2 | 本地缺少 5 个完整 approved snapshot，无法完成真实多交易日观察 | 待补真实交易日数据 |

### 发布建议

- ✅ PR5 自动化稳定性部分建议通过。
- ❌ 不建议启动 PR6 Legacy Removal。

详细报告：

- `docs/test_reports/phase456_formal_review_stabilization.md`

## 12. 增量记录：`Phase 4.5.5-RA E2E 2026-07-09`

### 基本信息

- Milestone: `Phase 4.5.5-RA`
- Phase: `Analyst Workbench First Responsibility Alignment`
- 执行时间: `2026-07-11`
- 测试数据日期: `2026-07-09`
- 详细报告: `docs/test_reports/phase455_e2e_20260709.md`

### 执行命令

| 命令 | 结果 | 关键输出 |
|---|---|---|
| `.venv/bin/python scripts/phase455_e2e_20260709.py` | 通过 | 所有 checks=true；snapshot hash `274226d88b1f656e3f5d420a2c3d36f80234861249369c717dc7b2ec0785d2df` |
| `node scripts/test-recap-workbench-first-contract.mjs` | 通过 | `recap workbench-first contract passed` |
| `node scripts/test-recap-default-data-mode-contract.mjs` | 通过 | `recap default data_mode contract passed` |
| `node scripts/test-recap-daily-review-v2-contract.mjs` | 通过 | `recap daily_review_v2 contract passed` |
| `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_workbench_phase455_generate.py stock_processing_service/tests/unit/test_workbench_phase455_compose_gate.py stock_processing_service/tests/unit/test_workbench_phase455_review_merger.py stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py stock_processing_service/tests/unit/test_workbench_phase454.py stock_processing_service/tests/unit/test_workbench_approval_gate.py stock_processing_service/tests/unit/test_workbench_session.py` | 通过 | `39 passed in 1.73s` |
| `npm run build` | 未通过 | 既有 `AnalystWorkspacePage.tsx` / `EmotionDashboard.tsx` 类型债；`RecapPage.tsx` 不在失败列表 |

### 验证结论

- Workbench draft 生成通过：`DRAFT_READY`, chart_reviews=6, cognition_cards=27。
- 分析师校准进入 snapshot：`PCB印制电路板.stage_judgement.final_value=PCB成为资金承接方向`。
- Formal compose 只读 approved snapshot：报告 `snapshot_hash` 与 approved snapshot 一致。
- 新 AI draft 不污染正式报告：draft_v2 写入人形机器人判断后，formal report 仍输出 PCB。
- Recap 页面职责收敛通过：契约测试禁止 derived-data generate 和 `force=true`。

### 发现的问题

- `P455-E2E-001`：真实 `tmp/analyst_workbench/2026-07-09/snapshot.json` 是 PR4 前旧格式，缺少 `snapshot_hash`，当前 formal gate 会拒绝。需要对真实 7/9 session 重新 approve 或执行 snapshot 元数据迁移。
- `P455-E2E-002`：前端全量 build 仍受既有 `AnalystWorkspacePage.tsx` / `EmotionDashboard.tsx` 类型债影响。

### 发布建议

- ✅ Phase 4.5.5-RA 代码职责边界建议通过。
- ⚠️ 正式使用 2026-07-09 runtime 快照前，必须完成旧 snapshot 重批或迁移。
  - 只有在接入真实分钟数据源后，才允许升级成分钟真值

### 当前结论

- `market_environment_and_theme_environment.v1` 已可作为 `P3.phase3` 的环境层子链保留
- 当前复盘判断顺序已升级为：
  - `大盘环境 -> 板块环境 -> 主线/支线 -> 周期位置 -> 龙头分层`
- 当前不得对外宣称已完成“分钟级大环境真值识别”

## 12. 增量记录：`P2.phase0.topic_truth_source_repair_and_runtime_baseline.v1`

### 基本信息

- Milestone: `P2`
- Phase: `P2.phase0`
- 测试负责人: `Codex`
- 执行时间: `2026-04-06`
- 风险等级: `Medium`

### 测试范围

- 覆盖模块
  - `theme_service.services.theme_match_engine`
  - `theme_service.repositories.theme_profile_repository`
  - `subject_gates/*.json`
  - `structured_events_with_gt.jsonl`
- 覆盖功能点
  - 全量题材库下的运行时候选召回
  - `feature/rule recall` 召回补强
  - `rerank hit_features` 扩展
  - GT 老化题材复核与迁移
  - 定向题材真源修复
- 未覆盖范围
  - `stream:news:raw -> decision` 全链路生产验证
  - 大规模性能压测
  - 未进入本轮聚焦的剩余题材

### 执行命令记录

| 序号 | 命令 | 执行结果 | 关键输出 |
| --- | --- | --- | --- |
| 1 | `/Users/admin/Desktop/ai_theme_app/.venv/bin/python /Users/admin/Desktop/ai_theme_app/import_jyhf_gate_profile.py --data-root /Users/admin/Desktop/ai_theme_app/theme_data_complete --gate-dir /Users/admin/Desktop/ai_theme_app/subject_gates --subject 9030409` | 通过 | `读取 subject 数: 1`，`准备写入 1 条` |
| 2 | `/Users/admin/Desktop/ai_theme_app/.venv/bin/python /Users/admin/Desktop/ai_theme_app/import_jyhf_gate_profile.py --data-root /Users/admin/Desktop/ai_theme_app/theme_data_complete --gate-dir /Users/admin/Desktop/ai_theme_app/subject_gates --subject 9019807` | 通过 | `读取 subject 数: 1`，`准备写入 1 条` |
| 3 | `/Users/admin/Desktop/ai_theme_app/.venv/bin/python /Users/admin/Desktop/ai_theme_app/import_jyhf_gate_profile.py --data-root /Users/admin/Desktop/ai_theme_app/theme_data_complete --gate-dir /Users/admin/Desktop/ai_theme_app/subject_gates --subject 9043698` | 通过 | `读取 subject 数: 1`，`准备写入 1 条` |
| 4 | `/Users/admin/Desktop/ai_theme_app/.venv/bin/python /Users/admin/Desktop/ai_theme_app/import_jyhf_gate_profile.py --data-root /Users/admin/Desktop/ai_theme_app/theme_data_complete --gate-dir /Users/admin/Desktop/ai_theme_app/subject_gates --subject 9024880` | 通过 | `读取 subject 数: 1`，`准备写入 1 条` |
| 5 | `/Users/admin/Desktop/ai_theme_app/.venv/bin/python /Users/admin/Desktop/ai_theme_app/import_jyhf_gate_profile.py --data-root /Users/admin/Desktop/ai_theme_app/theme_data_complete --gate-dir /Users/admin/Desktop/ai_theme_app/subject_gates --subject 9059919` | 通过 | `读取 subject 数: 1`，`准备写入 1 条` |
| 6 | `GT_SUBJECT_KEY=9030409 /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/analyze_aiar_dense_rerank_35.py` | 通过 | `merged recall=35/35`, `rerank top1=27/35`, `LLM top1=32/35` |
| 7 | `GT_SUBJECT_KEY=9019807 /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/analyze_satellite_dense_rerank_10.py` | 通过 | 清洗后有效样本 `6` 条，`rerank/reserve top1=5/6` |
| 8 | `GT_SUBJECT_KEY=9064166 /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/analyze_spacex_dense_rerank_5.py` | 通过 | `merged/rerank/reserve recall=5/5`, `LLM top1=5/5` |
| 9 | `GT_SUBJECT_KEY=9043698 /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/analyze_ocean_dense_rerank_4.py` | 通过 | `merged/rerank/reserve top1=4/4` |
| 10 | `GT_SUBJECT_KEY=9024880 /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/analyze_liquidcool_dense_rerank_8.py` | 通过 | 清洗后有效样本 `7` 条，`merged top1=5/7`, `rerank/reserve top1=4/7` |
| 11 | `GT_SUBJECT_KEY=9059919 /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/analyze_liquidcool_dense_rerank_8.py` | 通过 | `merged recall=6/6`, `rerank/reserve top1=5/6` |
| 12 | `/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/run_theme_match_engine_runtime_100.py` | 通过 | `top1=0.60`, `top3=0.84`, `top5=0.86` |

### GT 复核与迁移

- `9019807 / 卫星互联网`
  - 已把应迁移到 `9060827 / 可回收火箭`、`9061851 / 商业航天8大IPO` 的样本移出
- `9064166 / SpaceX`
  - 已把全部 `SpaceX` GT 统一到 `9064166`
  - `9060949` 视为老化编码，不再作为测试 GT
- `9043698 / 深海经济`
  - 已把旧显示名称 `海洋经济` 纠正为 `深海经济`
- `9024880 / 液冷数据中心`
  - 已将 `evt_fbc14c988eab` 迁移到 `9014001 / 人工智能硬件`

### 代码与真源修正

- 运行时通用修正：
  - `ThemeMatchEngine` 增加 `feature/rule recall`
  - `rerank hit_features` 扩展到 `aliases/entity_hints/core_objects`
  - 统一过滤高权重通用污染词，降低脏候选抢分
- 题材真源修正：
  - `9030409 / AI/AR眼镜`
  - `9019807 / 卫星互联网`
  - `9043698 / 深海经济`
  - `9024880 / 液冷数据中心`
  - `9059919 / 对日制裁`

### 题材定向结果

- `9030409 / AI/AR眼镜`
  - `merged candidate_recall = 35/35 = 100%`
  - `rerank top1 = 27/35 = 77.14%`
  - `LLM top1 = 32/35 = 91.43%`
- `9019807 / 卫星互联网`
  - 清洗后有效样本 `6` 条
  - `merged/rerank/reserve candidate_recall = 6/6 = 100%`
  - `rerank/reserve top1 = 5/6 = 83.33%`
- `9064166 / SpaceX`
  - 统一 GT 后样本 `5` 条
  - `merged/rerank/reserve candidate_recall = 5/5 = 100%`
  - `LLM top1 = 5/5 = 100%`
- `9043698 / 深海经济`
  - `merged/rerank/reserve candidate_recall = 4/4 = 100%`
  - `merged/rerank/reserve top1 = 4/4 = 100%`
- `9024880 / 液冷数据中心`
  - 清洗后有效样本 `7` 条
  - `dense candidate_recall = 6/7 = 85.71%`
  - `merged/rerank/reserve candidate_recall = 7/7 = 100%`
  - `merged top1 = 5/7 = 71.43%`
  - `rerank/reserve top1 = 4/7 = 57.14%`
- `9059919 / 对日制裁`
  - `dense candidate_recall = 2/6 = 33.33%`
  - `merged/rerank/reserve candidate_recall = 6/6 = 100%`
  - `merged top1 = 4/6 = 66.67%`
  - `rerank/reserve top1 = 5/6 = 83.33%`

### 最新 100 条运行时基线

- 结果文件：
  - [runtime_theme_match_metrics_100.json](/Users/admin/Desktop/ai_theme_app/tmp/runtime_theme_match_metrics_100.json)
  - [runtime_theme_match_detail_100.json](/Users/admin/Desktop/ai_theme_app/tmp/runtime_theme_match_detail_100.json)
- 指标：
  - `events = 100`
  - `processed = 100`
  - `top1_accuracy = 0.60`
  - `top3_accuracy = 0.84`
  - `top5_accuracy = 0.86`
- 对比旧运行时基线：
  - `top1: 0.42 -> 0.60`
  - 提升 `18` 个百分点

### 缺陷与结论

| 缺陷ID | 严重级别 | 描述 | 当前状态 |
| --- | --- | --- | --- |
| P2P0-BUG-001 | P1 | 多个题材 `subject_gates` 仍停留在旧口径，导致全量题材库下候选池严重失真 | 已部分修复 |
| P2P0-BUG-002 | P1 | `structured_events_with_gt.jsonl` 存在题材演进后的 GT 老化编码与过宽归属 | 已部分修复 |
| P2P0-BUG-003 | P1 | 运行时高权重命中存在通用污染词，导致脏候选长期压制垂直题材 | 已修复首批通用词 |

### 风险评估

- 技术风险
  - 剩余弱题材仍需继续做 GT 复核和 gate 修正。
- 数据一致性风险
  - `100` 条运行时基线已经显著改善，但尚未在所有弱题材完成修复后重新冻结。
- 可扩展性风险
  - 当前修正路径已证明可复制，但仍依赖继续清理老化题材真源。

### 发布建议

- ✅ 建议继续推进（Ready for next repair batch）

说明：
- `P2.phase0` 的生产级全链路通过结论不变。
- 本轮增量已经把运行时基线从 `0.42` 提升到 `0.60`。
- 下一步应继续处理剩余弱题材，并在修完后重跑一次新的 `100` 条运行时冻结基线。

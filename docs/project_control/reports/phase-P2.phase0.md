# Phase P2.phase0 执行报告（2026-03-31）

## 执行口径

- 执行协议：按 [PHASE_CONTRACT_P2.phase0.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/PHASE_CONTRACT_P2.phase0.md) 执行。
- 执行方式：优先复用已经通过的真实测试证据，不对已确认通过的核心用例重复重测。
- 严格遵循：
  - 不使用 mock/fake/static service 作为主链路验证替代
  - 测试顺序 `UT -> IT -> PT/E2E`
  - 最终全链路必须从 `stream:news:raw` 起步

## 本次复用的真实测试证据

### 1. ThemeMatchEngine 单元层
- 证据：
  - [runtime_theme_match_detail_100.json](/Users/admin/Desktop/ai_theme_app/tmp/runtime_theme_match_detail_100.json)
  - [runtime_theme_match_metrics_100.json](/Users/admin/Desktop/ai_theme_app/tmp/runtime_theme_match_metrics_100.json)
- 结果：
  - `events = 100`
  - `top1_accuracy = 0.98`
  - `top3_accuracy = 1.0`
  - `top5_accuracy = 1.0`
- 结论：
  - 运行时 `ThemeMatchEngine` 已完成对 [final_theme_matcher.py](/Users/admin/Desktop/ai_theme_app/final_theme_matcher.py) 主链的有效迁移。

### 2. theme_processor 真实集成层
- 证据：
  - [p2_phase0_theme_processor_integration_30.preview.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_theme_processor_integration_30.preview.json)
- 结果：
  - `events = 30`
  - `resolved_events = 30`
  - `top1_accuracy = 1.0`
- 结论：
  - `stream:events:structured -> theme_processor.py -> theme_service.py -> ThemeMatchEngine -> stream:events:decision` 链路稳定。

### 3. news_stream_processor -> theme_processor 真实跨组件层
- 证据：
  - [p2_phase0_news_to_theme_5.preview.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_news_to_theme_5.preview.json)
- 结果：
  - `10` 条样本真实通过
  - `top1_accuracy = 1.0`
- 结论：
  - 结构化链与匹配链之间的接口已稳定。

### 4. stream:news:raw -> decision 真实全链路最终 Gate
- 证据：
  - [p2_phase0_full_chain_100_to_decision.report.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_to_decision.report.json)
  - [p2_phase0_full_chain_100_match_detail.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_match_detail.json)
  - [p2_phase0_full_chain_100_match_metrics.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_match_metrics.json)
  - [p2_phase0_full_chain_100_mismatches.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_mismatches.json)
- 结果：
  - `events = 100`
  - `processed = 100`
  - `top1_hits = 96`
  - `top1_accuracy = 0.96`
- 结论：
  - `P2.phase0` 已达到既定高精度基线。

## 本轮关键实现收口

### 1. 结构化链稳定性收口
- [factory.py](/Users/admin/Desktop/ai_theme_app/model_service/llm_parser/factory.py) 已切换默认 parser 为 [reliable_deepseek_parser.py](/Users/admin/Desktop/ai_theme_app/model_service/llm_parser/reliable_deepseek_parser.py)。
- 该调整已在真实 `10` 条与真实 `100` 条全链路测试中证明有效，解决了早期 DeepSeek 抖动导致整批中断的问题。

### 2. 运行时匹配链收口
- [theme_match_engine.py](/Users/admin/Desktop/ai_theme_app/theme_service/services/theme_match_engine.py) 已引入：
  - Dense Recall
  - Fused Rerank
  - Dynamic Top-K
  - Direct-Hit Reserve
  - Gate Evidence
  - Final LLM Judge
- 运行时结果已回到与离线基线一致的区间。

## 当前剩余问题

### 1. 少量误判
- 当前 `100` 条最终 Gate 中仍有 `4` 条失配：
  - `海洋经济 9043698`：`2` 条
  - `液冷数据中心 9024880`：`2` 条
- 误判明细见：
  - [p2_phase0_full_chain_100_mismatches.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_mismatches.json)

### 2. 运行时启动噪音
- 启动阶段仍会打印旧 `ThemeDiscoveryEngine` 初始化日志。
- 当前判断：
  - 这是兼容层/历史初始化残留
  - 不影响本阶段门禁结果
  - 但应在后续重构中继续下沉或移除

## Gate 结论

- `P2.phase0`：**CONDITIONAL PASS**

判定依据：
- 真实 `100` 条全链路结果已达到 `top1_accuracy = 0.96`
- 真实结构化链、真实匹配链、真实决策链均已打通
- 稳定性问题已从“整批中断”收口为“少量误判”

保留项：
- `4` 条失配样本仍需专项优化
- 旧 `ThemeDiscoveryEngine` 初始化日志残留需后续清理

## Review Checklist

- [x] `ThemeMatchEngine` 已按 `final_theme_matcher.py` 主链迁移到运行时
- [x] 默认结构化 parser 已切换为 `ReliableDeepSeekParser`
- [x] `news_stream_handler.py -> news_stream_processor.py -> theme_processor.py -> decision` 真实全链路已验证
- [x] `100` 条真实全链路最终 Gate 已执行
- [x] 结果文件、明细文件、失配文件已归档
- [ ] `海洋经济` 与 `液冷数据中心` 的误判专项优化未完成
- [ ] 旧 `ThemeDiscoveryEngine` 初始化日志清理未完成

## 等待用户决策

- `ACCEPT`
- `REWORK`
- `REQUEST CHANGES`

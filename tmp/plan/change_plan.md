# P1.phase0 变更计划

| 文件路径 | 变更类型 | diff摘要 | 影响范围 |
|:--|:--|:--|:--|
| `database_service/streams/handlers/theme_processor.py` | 修改 | 清理 `_get_action_for_decision_type` 重复定义；移除 print 直出 | 决策动作映射与运行日志 |
| `theme_service/services/theme_service.py` | 修改 | 清理 `initialize_with_categories_only`、`discover_category_only` 重复定义；移除 traceback.print_exc/print | 分类优先初始化与分类推断 |
| `database_service/streams/handlers/news_stream_handler.py` | 修改 | 清理 `_process_storage_batch`、`_update_storage_stats` 重复定义；移除 print/traceback.print_exc | 新闻存储处理与统计路径 |
| `database_service/streams/schedulers/news_stream_scheduler.py` | 修改 | 移除 print/traceback.print_exc（结构化日志替换） | 调度日志一致性 |
| `database_service/streams/handlers/DecisionExecutor.py` | 修改 | 移除 print 直出（结构化日志替换） | 执行器状态输出 |
| `docs/project_control/reports/phase-P1.phase0.md` | 新增 | 阶段执行与验证报告 | 阶段验收证据 |

架构影响说明：
- 本次不改业务流程语义，仅做 phase0 收敛类“等价重构 + 契约兜底 + 可观测性清理”。
- 跨模块影响可控，无数据库 schema 变更。

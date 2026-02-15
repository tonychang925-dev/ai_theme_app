# P1.phase0 WBS执行子集

执行任务清单（来源：`tmp/pm_plan_payload.json`，过滤 `P1.phase0-T01~T04`）

- [ ] P1.phase0-T01 冻结第一阶段唯一运行时链路与入口清单
  - 输出运行时链路与入口清单文档
  - 验证重复入口定义扫描结果
- [ ] P1.phase0-T02 定义 DecisionEnvelope v1 字段与 dual-read 兼容策略
  - 统一 v1 必填字段与消费校验逻辑
  - 补充契约文档与验收映射
- [ ] P1.phase0-T03 清理重复函数定义并建立静态扫描门禁
  - 清理高风险重复定义（theme_processor/theme_service/news_stream_handler）
  - 增加/执行静态扫描命令
- [ ] P1.phase0-T04 trace_id 与 payload_version 全链路贯通方案评审
  - 确保关键日志与消息携带字段
  - 产出抽样验证证据

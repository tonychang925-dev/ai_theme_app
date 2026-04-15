# 全链路打通方案 - 实时新闻采集到SSE推送

## 概述

基于当前项目状态分析，本方案旨在打通从实时新闻采集到前端SSE推送的全链路数据流，实现真正实时的事件处理与推送。

**核心目标**：
1. 实现新闻采集→事件结构化→事件与题材匹配→SSE推送的完整自动化流程
2. 保持对现有功能的零破坏性修改
3. 通过新增服务和接口实现全链路打通
4. 确保系统高可用性和可扩展性

## 一、当前链路状态分析

### 1.1 现有组件盘点

| 组件 | 状态 | 功能 | 问题 |
|------|------|------|------|
| **news_crawler_service** | ✅ 已实现 | 支持真实/模拟新闻采集 | 独立服务，未集成到Stream流 |
| **news_stream_processor** | ✅ 已实现 | 新闻结构化处理（AI分析） | 处理结果未正确发布到Stream |
| **news_producer/consumer** | ✅ 已实现 | Redis Stream发布/消费 | 业务逻辑不完整 |
| **event_producer/consumer** | ✅ 已实现 | 事件Stream处理 | 主题匹配功能缺失（TODO） |
| **realtime_push_service** | ✅ 已实现 | WebSocket实时推送 | 未与SSE集成 |
| **frontend_bff SSE端点** | ✅ 已实现 | `/api/intel/stream` | 轮询数据库，非真正实时 |
| **IntelPage前端** | ✅ 已实现 | SSE客户端+轮询兜底 | 依赖后端轮询机制 |

### 1.2 关键断点识别

1. **新闻采集→Stream断点**：news_crawler_service未自动发布新闻到Redis Stream
2. **事件结构化→Stream断点**：news_stream_processor处理结果未发布到正确Stream
3. **事件-题材匹配断点**：event_consumer中主题匹配逻辑未实现
4. **Stream→SSE断点**：SSE端点轮询数据库，未直接消费Redis Stream

## 二、全链路架构设计

### 2.1 目标架构

```
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  新闻采集服务    │───▶│ stream:news:raw     │───▶│ 事件结构化处理器   │
│ (RealTimeNews   │    │ (Redis Stream)      │    │ (NewsStreamProcessor)│
│   Collector)    │    │                     │    │                     │
└─────────────────┘    └─────────────────────┘    └──────────┬──────────┘
                                                              │
                                                              ▼
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  前端SSE推送     │◀───│ stream:event:feed   │◀───│ 事件-题材匹配服务   │
│ (SSE推送服务)    │    │ (Redis Stream)      │    │ (EventThemeMatcher) │
│                 │    │                     │    │                     │
└─────────────────┘    └─────────────────────┘    └──────────┬──────────┘
                                                              │
                                                              ▼
                                                        ┌─────────────────────┐
                                                        │ stream:events:      │
                                                        │ structured          │
                                                        │ (Redis Stream)      │
                                                        └─────────────────────┘
```

### 2.2 数据流设计

1. **新闻采集层**：`RealTimeNewsCollector` → `stream:news:raw`
2. **事件结构化层**：`stream:news:raw` → `NewsStreamProcessor` → `stream:events:structured`
3. **事件-题材匹配层**：`stream:events:structured` → `EventThemeMatcher` → `stream:event:feed`
4. **SSE推送层**：`stream:event:feed` → `SSEPushService` → 前端客户端

## 三、新增服务设计

### 3.1 实时新闻采集服务 (RealTimeNewsCollector)

**定位**：定期调用news_crawler_service，将新闻发布到Redis Stream

**功能**：
- 配置化采集频率（默认：每5分钟）
- 支持真实/模拟模式切换
- 异常处理和重试机制
- 采集统计和监控

**接口**：
```python
class RealTimeNewsCollector:
    async def start_collection_loop(self) -> None
    async def collect_and_publish(self, mode: str = "auto") -> Dict
    async def get_collection_stats(self) -> Dict
```

**Stream输出**：`stream:news:raw`

### 3.2 事件-题材匹配服务 (EventThemeMatcher)

**定位**：监听结构化事件Stream，调用主题服务进行匹配

**功能**：
- 监听`stream:events:structured`
- 调用主题服务API进行事件-题材匹配
- 生成事件-主题关联关系
- 发布匹配结果到`stream:event:feed`

**接口**：
```python
class EventThemeMatcher:
    async def start_matching_loop(self) -> None
    async def match_event_to_themes(self, event_data: Dict) -> Dict
    async def publish_matched_event(self, matched_event: Dict) -> str
```

**依赖**：主题服务（端口8002）的API接口

### 3.3 SSE推送服务 (SSEPushService)

**定位**：替换现有轮询机制，直接消费Redis Stream进行SSE推送

**功能**：
- 监听`stream:event:feed`
- 将Stream事件转换为SSE格式
- 保持与现有SSE API的兼容性
- 支持多客户端连接管理

**改造方式**：创建新SSE端点`/api/intel/stream/realtime`，逐步迁移

## 四、实施计划

### 阶段1：基础服务搭建（预计2-3天）

**目标**：搭建新增服务框架，确保基础功能可用

**任务**：
1. [ ] 创建`RealTimeNewsCollector`服务框架
2. [ ] 创建`EventThemeMatcher`服务框架  
3. [ ] 创建`SSEPushService`服务框架
4. [ ] 编写服务启动脚本和配置
5. [ ] 基础集成测试

### 阶段2：数据流打通（预计2-3天）

**目标**：实现完整数据流，从新闻采集到Stream输出

**任务**：
1. [ ] 实现`RealTimeNewsCollector`的新闻采集和发布
2. [ ] 验证`stream:news:raw`数据正确性
3. [ ] 配置`NewsStreamProcessor`监听`stream:news:raw`
4. [ ] 验证结构化事件输出到`stream:events:structured`
5. [ ] 端到端测试新闻→结构化事件流程

### 阶段3：事件-题材匹配实现（预计2天）

**目标**：实现事件与题材的智能匹配

**任务**：
1. [ ] 实现`EventThemeMatcher`核心匹配逻辑
2. [ ] 集成主题服务API调用
3. [ ] 验证匹配结果发布到`stream:event:feed`
4. [ ] 测试匹配准确性和性能

### 阶段4：SSE实时推送改造（预计2天）

**目标**：将SSE推送改造为真正实时

**任务**：
1. [ ] 实现`SSEPushService`监听`stream:event:feed`
2. [ ] 创建新SSE端点`/api/intel/stream/realtime`
3. [ ] 前端测试新SSE端点的实时性
4. [ ] 性能测试和优化

### 阶段5：集成测试与优化（预计2天）

**目标**：全链路集成测试和性能优化

**任务**：
1. [ ] 端到端全链路功能测试
2. [ ] 性能基准测试（延迟、吞吐量）
3. [ ] 错误处理和恢复测试
4. [ ] 文档更新和部署指南

## 五、技术细节

### 5.1 Redis Stream设计

| Stream名称 | 用途 | 消费者组 | 保留策略 |
|------------|------|----------|----------|
| `stream:news:raw` | 原始新闻数据 | `news_processors` | maxlen: 10000 |
| `stream:events:structured` | 结构化事件 | `event_matchers` | maxlen: 5000 |
| `stream:event:feed` | 匹配后的事件流 | `sse_pushers` | maxlen: 2000 |

### 5.2 事件数据结构

**原始新闻** (`stream:news:raw`)：
```json
{
  "news_id": "news_123",
  "title": "新闻标题",
  "content": "新闻内容",
  "source": "财联社",
  "publish_date": "2026-04-10",
  "publish_time": "14:30:00"
}
```

**结构化事件** (`stream:events:structured`)：
```json
{
  "event_id": "event_456",
  "news_id": "news_123",
  "event_type": "policy_change",
  "summary": "事件摘要",
  "impact_industries": ["新能源", "半导体"],
  "direction": "positive",
  "confidence": 0.85,
  "severity_score": 75
}
```

**匹配后事件** (`stream:event:feed`)：
```json
{
  "item_id": "item_789",
  "event_type": "theme_move",
  "occurred_at": "2026-04-10T14:30:00",
  "summary": "事件摘要",
  "theme_names": ["人工智能", "算力"],
  "theme_subject_keys": ["ai", "computing_power"],
  "confidence": 0.85,
  "impact_score": 75,
  "source_type": "event_theme_map"
}
```

### 5.3 错误处理策略

1. **新闻采集失败**：重试3次，记录错误，切换模拟模式
2. **AI分析失败**：跳过该新闻，记录日志，继续处理下一条
3. **主题匹配失败**：使用默认主题或标记为"未匹配"
4. **SSE连接中断**：客户端自动重连，服务端保持Stream消费

### 5.4 性能优化

1. **批处理**：新闻采集和事件匹配支持批处理
2. **异步处理**：所有IO操作使用async/await
3. **连接池**：Redis、数据库连接复用
4. **缓存**：主题信息缓存减少API调用

## 六、风险与缓解措施

### 6.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 新闻采集服务不稳定 | 数据源中断 | 模拟模式兜底，采集频率降级 |
| 主题服务API不可用 | 事件无法匹配 | 缓存主题数据，降级为默认匹配 |
| Redis Stream堆积 | 内存占用高 | 合理设置maxlen，监控清理 |
| SSE连接数过多 | 服务端压力大 | 连接管理优化，负载均衡 |

### 6.2 集成风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 现有SSE端点改造影响 | 前端功能异常 | 新增端点，并行运行，逐步迁移 |
| 数据结构不一致 | 数据处理错误 | 版本化数据结构，兼容性适配 |
| 服务启动顺序依赖 | 启动失败 | 健康检查，自动重试机制 |

### 6.3 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 事件匹配准确率低 | 用户体验差 | 人工审核机制，匹配算法优化 |
| 实时性不达预期 | 决策延迟 | 性能监控，处理链路优化 |
| 系统复杂度增加 | 维护困难 | 清晰文档，监控告警完善 |

## 七、预期收益

### 7.1 技术收益

- **真正实时性**：SSE推送延迟从秒级降低到毫秒级
- **架构解耦**：各层通过Stream解耦，独立扩展
- **可观测性**：完整数据流追踪和监控
- **可维护性**：模块化设计，易于维护和扩展

### 7.2 业务收益

- **决策时效性**：投资决策基于最新实时信息
- **用户体验**：情报更新无感知，实时推送
- **系统可靠性**：故障隔离，降级策略完善
- **扩展能力**：支持更多数据源和事件类型

### 7.3 指标度量

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 端到端延迟 | < 3秒 | 从新闻采集到前端显示时间差 |
| 事件匹配准确率 | > 85% | 人工抽样评估 |
| SSE推送成功率 | > 99% | 连接成功数/总连接数 |
| 系统可用性 | > 99.5% | 服务正常运行时间 |

## 八、后续扩展方向

### 8.1 短期扩展（1个月内）

- 多新闻源集成（新浪财经、东方财富等）
- 事件重要性分级和过滤
- 客户端个性化订阅

### 8.2 中期扩展（3个月内）

- 机器学习优化匹配算法
- 实时热点主题发现
- 跨市场事件关联分析

### 8.3 长期愿景（6个月内）

- 预测性事件分析
- 自动化投资策略生成
- 多模态信息融合（文本、数据、图表）

## 九、成功标准

### 9.1 技术标准

- [ ] 全链路自动化运行，无需人工干预
- [ ] 端到端延迟 < 3秒
- [ ] 系统可用性 > 99.5%
- [ ] 错误率 < 1%

### 9.2 业务标准

- [ ] 前端情报流实时更新
- [ ] 事件-题材匹配准确率 > 85%
- [ ] 用户满意度提升（调研反馈）
- [ ] 决策响应时间缩短

## 十、运行稳定性优化（2026-04-11增补）

### 10.1 已落地优化

1. 主题服务客户端新增进程级熔断（按`base_url`共享状态），避免实例重建后重复触发重试风暴。  
2. 主题匹配失败冷却改为指数退避（30s→60s→120s→240s，最大300s）。  
3. `EventThemeMatcher` 增加匹配失败连续计数和冷却扩展，主题服务不可达时优先降级默认匹配。  
4. 启动脚本新增 `BFF_ACCESS_LOG` 开关，默认关闭 `uvicorn` access log，降低 `/health` 高频探活日志压力。  

### 10.2 建议运行参数（默认即可）

```bash
# 主题服务冷却（EventThemeMatcher）
theme_service_cooldown_seconds=30
theme_service_max_cooldown_seconds=300

# 前端BFF访问日志（run_realtime_stack.sh）
BFF_ACCESS_LOG=false
```

### 10.3 验收关注点

1. 当主题服务不可达（如`localhost:8000`未启动）时，日志不再每3秒刷屏，失败日志应明显降频。  
2. `stream:event:feed` 仍持续有数据产出（走默认匹配降级），前端“情报”页保持可用。  
3. `frontend_bff_8003.log` 不再被健康检查请求大量淹没，关键业务日志可读性提升。  
4. 重启后 60 秒内服务不应短暂存活后退出（由启动脚本watchdog兜底检测）。  

---

**文档版本**：v1.1  
**创建日期**：2026-04-10  
**更新日期**：2026-04-11  
**负责人**：全链路打通项目组

**相关文档**：
- [前端架构优化方案-实时通信与三栏布局.md](./前端架构优化方案-实时通信与三栏布局.md)
- [Redis Stream 架构优化分析报告.md](../database_service/docs/Redis_Stream_架构优化分析.md)
- [个人投资助理项目-前端技术设计（第四阶段）.md](./个人投资助理项目-前端技术设计（第四阶段）.md)

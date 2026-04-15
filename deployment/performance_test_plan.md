# 性能压力测试方案

## 测试目标
验证AI主题分析应用在生产环境下的性能表现，确保系统支持100+并发用户。

## 测试环境
- **环境类型**: 生产环境
- **硬件配置**: 8核CPU, 16GB内存, 100GB SSD
- **网络带宽**: 100Mbps
- **测试工具**: Apache JMeter, Locust, k6

## 测试场景

### 场景1: API接口压力测试
**目标**: 测试后端API的并发处理能力

| 接口 | 方法 | 预期QPS | 测试时长 | 并发用户 |
|------|------|---------|----------|----------|
| `/api/themes` | GET | 50 | 10分钟 | 100 |
| `/api/intel/feed` | GET | 30 | 10分钟 | 50 |
| `/api/stocks/{code}` | GET | 100 | 10分钟 | 200 |
| `/api/recap/daily` | GET | 20 | 10分钟 | 30 |

### 场景2: AI模型服务压力测试
**目标**: 测试AI模型推理性能

| 服务 | 输入大小 | 预期延迟 | 并发请求 | 测试时长 |
|------|----------|----------|----------|----------|
| 事件分类 | 500字符 | < 200ms | 50 | 5分钟 |
| 主题匹配 | 1000字符 | < 500ms | 30 | 5分钟 |
| 摘要生成 | 2000字符 | < 1000ms | 20 | 5分钟 |

### 场景3: 数据库压力测试
**目标**: 测试数据库读写性能

| 操作 | 表 | 预期TPS | 并发连接 | 测试时长 |
|------|-----|---------|----------|----------|
| 读取 | theme_master | 1000 | 50 | 5分钟 |
| 写入 | news_event | 500 | 30 | 5分钟 |
| 更新 | theme_heat | 200 | 20 | 5分钟 |

### 场景4: Redis压力测试
**目标**: 测试Redis缓存和消息队列性能

| 操作 | 数据类型 | 预期OPS | 并发连接 | 测试时长 |
|------|----------|---------|----------|----------|
| 读取 | String | 10000 | 100 | 5分钟 |
| 写入 | Stream | 5000 | 50 | 5分钟 |
| 发布 | Pub/Sub | 2000 | 30 | 5分钟 |

### 场景5: 前端页面加载测试
**目标**: 测试前端页面加载性能

| 页面 | 预期加载时间 | 并发用户 | 测试时长 |
|------|--------------|----------|----------|
| 主题工作台 | < 2秒 | 100 | 5分钟 |
| 情报页面 | < 3秒 | 80 | 5分钟 |
| 复盘页面 | < 2.5秒 | 60 | 5分钟 |

## 测试工具配置

### JMeter配置
```xml
<!-- 线程组配置 -->
<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="API压力测试" enabled="true">
  <stringProp name="ThreadGroup.num_threads">100</stringProp>
  <stringProp name="ThreadGroup.ramp_time">60</stringProp>
  <longProp name="ThreadGroup.duration">600</longProp>
</ThreadGroup>
```

### Locust配置
```python
from locust import HttpUser, task, between

class AIThemeUser(HttpUser):
    wait_time = between(1, 5)
    
    @task(3)
    def get_themes(self):
        self.client.get("/api/themes")
    
    @task(2)
    def get_intel_feed(self):
        self.client.get("/api/intel/feed")
    
    @task(1)
    def get_stock_info(self):
        self.client.get("/api/stocks/000001")
```

### k6配置
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 50 },
    { duration: '5m', target: 100 },
    { duration: '2m', target: 0 },
  ],
};

export default function () {
  const res = http.get('http://localhost:8000/api/themes');
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
  sleep(1);
}
```

## 监控指标

### 系统资源监控
- CPU使用率: < 80%
- 内存使用率: < 85%
- 磁盘IO: < 90%
- 网络带宽: < 80%

### 应用性能监控
- API响应时间: P95 < 500ms
- 错误率: < 1%
- 吞吐量: 达到预期QPS
- 连接数: 稳定在预期范围内

### 数据库监控
- 查询延迟: < 100ms
- 连接数: < 最大连接数的80%
- 锁等待: < 5%

### Redis监控
- 内存使用: < 80%
- 命中率: > 95%
- 延迟: < 10ms

## 测试执行步骤

### 步骤1: 环境准备
1. 部署生产环境
2. 配置监控工具
3. 准备测试数据
4. 配置测试工具

### 步骤2: 基线测试
1. 单用户功能测试
2. 低并发性能测试
3. 建立性能基线

### 步骤3: 压力测试
1. 逐步增加并发用户
2. 监控系统表现
3. 记录性能数据

### 步骤4: 峰值测试
1. 达到最大并发用户
2. 持续运行30分钟
3. 观察系统稳定性

### 步骤5: 恢复测试
1. 停止压力测试
2. 观察系统恢复情况
3. 验证数据一致性

## 成功标准

### 必须满足的标准
1. **可用性**: 系统可用性 > 99.9%
2. **响应时间**: API P95响应时间 < 500ms
3. **错误率**: 错误率 < 1%
4. **资源使用**: 系统资源使用率在安全范围内

### 期望达到的标准
1. **并发用户**: 支持100+并发用户
2. **吞吐量**: 达到预期QPS目标
3. **稳定性**: 30分钟峰值测试无故障
4. **恢复能力**: 5分钟内恢复正常性能

## 风险与应对

### 风险1: 测试影响生产环境
- **应对**: 使用独立的测试环境，或在生产环境低峰期测试

### 风险2: 测试数据不足
- **应对**: 准备足够多的测试数据，模拟真实场景

### 风险3: 监控工具影响性能
- **应对**: 使用轻量级监控，或测试时降低监控频率

### 风险4: 测试发现性能瓶颈
- **应对**: 记录详细日志，准备优化方案

## 报告模板

### 测试报告结构
1. **执行摘要**: 测试概述和关键发现
2. **测试环境**: 环境配置和测试工具
3. **测试结果**: 各场景测试数据
4. **性能分析**: 性能瓶颈和优化建议
5. **结论建议**: 系统是否满足性能要求

### 关键指标报告
```json
{
  "test_scenario": "API压力测试",
  "duration_minutes": 10,
  "max_concurrent_users": 100,
  "total_requests": 50000,
  "success_rate": 99.8,
  "avg_response_time_ms": 245,
  "p95_response_time_ms": 432,
  "throughput_rps": 83.3,
  "error_rate": 0.2,
  "cpu_usage_avg": 65.2,
  "memory_usage_avg": 72.1
}
```

## 附录

### 测试脚本位置
- JMeter脚本: `deployment/tests/jmeter/`
- Locust脚本: `deployment/tests/locust/`
- k6脚本: `deployment/tests/k6/`

### 监控配置
- Prometheus配置: `deployment/monitoring/prometheus.yml`
- Grafana仪表板: `deployment/monitoring/grafana/dashboards/`

### 数据生成工具
- 测试数据生成: `deployment/tools/generate_test_data.py`
- 负载模拟工具: `deployment/tools/load_simulator.py`

---

**测试负责人**: 测试专家  
**执行时间**: 2026-04-17 14:00-17:00  
**参与人员**: 测试专家、后端专家、AI专家、技术负责人
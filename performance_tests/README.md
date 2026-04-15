# AI Theme App - 性能压力测试

## 概述

本目录包含AI主题分析应用的性能压力测试工具和脚本。测试覆盖以下方面：
1. **负载测试**: 模拟正常用户负载
2. **压力测试**: 测试系统极限性能
3. **并发测试**: 测试高并发场景
4. **稳定性测试**: 长时间运行测试
5. **API性能测试**: 各API端点性能分析

## 测试工具

### 1. Locust - 分布式负载测试
- 文件: `locustfile.py`
- 特点: 支持分布式测试，实时监控

### 2. k6 - 现代负载测试工具
- 文件: `k6_tests.js`
- 特点: 基于JavaScript，支持复杂场景

### 3. Apache JMeter - 传统负载测试
- 文件: `jmeter_test_plan.jmx`
- 特点: 功能全面，支持多种协议

### 4. 自定义Python测试脚本
- 文件: `custom_performance_tests.py`
- 特点: 灵活定制，集成度高

## 测试场景

### 1. 核心API测试
- 主题分析API
- 新闻流处理API
- 市场环境指标API
- 股票异常信号API

### 2. 用户场景测试
- 用户登录/注册
- 主题工作空间操作
- 智能分析请求
- 数据导出功能

### 3. 系统负载测试
- 数据库连接池测试
- Redis缓存性能测试
- AI模型服务响应测试
- 消息队列吞吐量测试

## 测试指标

### 性能指标
- 响应时间 (P50, P90, P95, P99)
- 吞吐量 (RPS - 请求/秒)
- 错误率
- 资源利用率 (CPU, 内存, 网络)

### 系统指标
- 数据库查询性能
- Redis缓存命中率
- 服务可用性
- 内存泄漏检测

## 快速开始

### 1. 安装依赖
```bash
pip install locust k6-python pandas matplotlib
```

### 2. 运行Locust测试
```bash
# 启动Locust Web界面
locust -f performance_tests/locustfile.py --host=http://localhost:8000

# 无界面模式运行
locust -f performance_tests/locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 -t 5m
```

### 3. 运行k6测试
```bash
k6 run performance_tests/k6_tests.js
```

### 4. 运行自定义测试
```bash
python performance_tests/custom_performance_tests.py
```

## 测试配置

### 环境配置
在运行测试前，需要配置测试环境：
```bash
# 设置测试目标URL
export TEST_BASE_URL=http://localhost:8000
export TEST_USER_COUNT=100
export TEST_DURATION=300  # 5分钟
```

### 测试参数
- `--users`: 并发用户数
- `--spawn-rate`: 用户生成速率
- `--run-time`: 测试运行时间
- `--host`: 目标主机地址

## 测试报告

### 自动生成报告
测试完成后会自动生成以下报告：
1. **HTML报告**: `reports/locust_report.html`
2. **JSON数据**: `reports/performance_data.json`
3. **图表**: `reports/charts/` 目录
4. **CSV数据**: `reports/csv/` 目录

### 报告内容
- 性能摘要
- 响应时间分布
- 错误分析
- 资源使用情况
- 建议优化点

## 监控集成

### Prometheus监控
测试期间会收集以下Prometheus指标：
- `http_request_duration_seconds`
- `http_requests_total`
- `concurrent_users`
- `error_rate`

### Grafana仪表板
预配置的Grafana仪表板：
- 实时性能监控
- 历史趋势分析
- 异常检测
- 容量规划

## 测试场景示例

### 场景1: 正常负载测试
```python
# 模拟100个用户，持续5分钟
# 用户行为：浏览主题 -> 分析新闻 -> 查看结果
```

### 场景2: 峰值压力测试
```python
# 模拟1000个用户，持续10分钟
# 测试系统极限处理能力
```

### 场景3: 长时间稳定性测试
```python
# 模拟50个用户，持续24小时
# 检测内存泄漏和资源耗尽
```

### 场景4: 并发写入测试
```python
# 模拟高频数据写入
# 测试数据库写入性能
```

## 故障排除

### 常见问题

1. **测试工具连接失败**
   - 检查目标服务是否运行
   - 验证网络连接
   - 检查防火墙设置

2. **测试结果异常**
   - 检查测试配置
   - 验证测试数据
   - 查看服务日志

3. **性能瓶颈定位**
   - 使用性能分析工具
   - 检查数据库查询
   - 监控系统资源

### 调试工具
- `performance_tests/debug_tools.py`: 调试工具集
- `performance_tests/profiling.py`: 性能分析工具
- `performance_tests/monitoring.py`: 实时监控工具

## 最佳实践

### 测试准备
1. 备份生产数据
2. 设置测试环境
3. 准备测试数据
4. 配置监控工具

### 测试执行
1. 从低负载开始
2. 逐步增加压力
3. 监控关键指标
4. 记录测试结果

### 测试分析
1. 分析性能瓶颈
2. 识别优化机会
3. 生成测试报告
4. 制定优化计划

## 自动化测试

### CI/CD集成
测试可以集成到CI/CD流程中：
```yaml
# GitHub Actions示例
- name: 运行性能测试
  run: |
    cd performance_tests
    python run_all_tests.py --ci
```

### 定时测试
设置定时性能测试：
```bash
# 每天凌晨运行测试
0 2 * * * cd /path/to/app && python performance_tests/scheduled_tests.py
```

## 扩展和定制

### 添加新测试场景
1. 在 `locustfile.py` 中添加新用户类
2. 在 `k6_tests.js` 中添加新测试函数
3. 在 `custom_performance_tests.py` 中添加新测试用例

### 自定义测试数据
1. 修改 `test_data/` 目录中的数据文件
2. 调整测试参数配置
3. 扩展测试报告格式

## 联系和支持

如有问题，请参考：
1. Locust文档: https://docs.locust.io/
2. k6文档: https://k6.io/docs/
3. JMeter文档: https://jmeter.apache.org/
4. 项目文档: `docs/` 目录

---

**最后更新**: 2026-04-12  
**版本**: 1.0
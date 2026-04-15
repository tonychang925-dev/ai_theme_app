# 全链路测试方案

## 测试目标
验证AI主题分析应用从新闻采集到题材决策的完整业务流程，确保系统各模块协同工作正常。

## 测试范围
### 测试链路


### 涉及模块
1. **新闻采集模块** (可选，第二阶段测试)
2. **新闻结构化模块** (news_stream_handler)
3. **事件分类模块** (news_stream_processor)
4. **题材匹配模块** (theme_processor)
5. **决策执行模块** (DecisionExecutor)
6. **数据存储模块** (DatabaseGateway)

## 测试阶段

### 第一阶段：测试数据集验证
**目标**: 使用预定义的测试数据集验证除新闻采集外的所有业务逻辑

**测试数据**: 
- 包含多个题材的测试新闻
- 每个题材有对应的预期匹配结果
- 可用于验证匹配准确性

**测试步骤**:
1. 从test_cases.txt加载测试新闻
2. 模拟新闻采集，直接写入news_raw表
3. 触发新闻结构化处理
4. 验证事件分类结果
5. 验证题材匹配结果
6. 验证决策执行结果
7. 验证数据存储结果

**验证指标**:
- 处理成功率: > 95%
- 匹配准确率: > 80%
- 处理延迟: < 5秒/条
- 数据完整性: 100%

### 第二阶段：真实新闻性能测试
**目标**: 使用真实新闻源测试全链路的性能和稳定性

**新闻源**:
- AkShare财经新闻
- 央视新闻
- 百度新闻

**测试步骤**:
1. 启动新闻采集服务
2. 采集实时新闻数据
3. 监控全链路处理流程
4. 记录性能指标
5. 验证系统稳定性

**验证指标**:
- 系统可用性: > 99%
- 处理吞吐量: > 10条/分钟
- 端到端延迟: < 30秒
- 错误率: < 1%
- 内存使用: < 80%
- CPU使用: < 70%

## 测试环境

### 环境配置
- **数据库**: PostgreSQL 14+
- **缓存**: Redis 7+
- **Python**: 3.10+
- **依赖**: 所有服务依赖包

### 环境准备
Collecting aioredis>=2.0.0 (from -r requirements.txt (line 3))
  Using cached aioredis-2.0.1-py3-none-any.whl.metadata (15 kB)
Requirement already satisfied: aiohttp>=3.8.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r requirements.txt (line 4)) (3.13.2)
Requirement already satisfied: async-timeout in /opt/miniconda3/lib/python3.13/site-packages (from aioredis>=2.0.0->-r requirements.txt (line 3)) (5.0.1)
Requirement already satisfied: typing-extensions in /opt/miniconda3/lib/python3.13/site-packages (from aioredis>=2.0.0->-r requirements.txt (line 3)) (4.15.0)
Requirement already satisfied: aiohappyeyeballs>=2.5.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (2.6.1)
Requirement already satisfied: aiosignal>=1.4.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (1.4.0)
Requirement already satisfied: attrs>=17.3.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (25.4.0)
Requirement already satisfied: frozenlist>=1.1.1 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (1.8.0)
Requirement already satisfied: multidict<7.0,>=4.5 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (6.7.0)
Requirement already satisfied: propcache>=0.2.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (0.4.1)
Requirement already satisfied: yarl<2.0,>=1.17.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (1.22.0)
Requirement already satisfied: idna>=2.0 in /opt/miniconda3/lib/python3.13/site-packages (from yarl<2.0,>=1.17.0->aiohttp>=3.8.0->-r requirements.txt (line 4)) (3.11)
Using cached aioredis-2.0.1-py3-none-any.whl (71 kB)
Installing collected packages: aioredis
Successfully installed aioredis-2.0.1
Requirement already satisfied: asyncpg>=0.27.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 2)) (0.31.0)
Requirement already satisfied: aioredis>=2.0.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 3)) (2.0.1)
Requirement already satisfied: redis>=4.5.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 4)) (7.1.0)
Requirement already satisfied: pyyaml>=6.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 7)) (6.0.3)
Requirement already satisfied: pydantic>=2.0.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 8)) (2.12.5)
Requirement already satisfied: python-dateutil>=2.8.2 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 11)) (2.9.0.post0)
Requirement already satisfied: ujson>=5.7.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 12)) (5.11.0)
Requirement already satisfied: prometheus-client>=0.17.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 15)) (0.24.1)
Requirement already satisfied: pytest>=7.0.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 18)) (9.0.2)
Requirement already satisfied: pytest-asyncio>=0.21.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 19)) (1.3.0)
Requirement already satisfied: black>=23.0.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 20)) (25.12.0)
Requirement already satisfied: mypy>=1.0.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r database_service/requirements.txt (line 21)) (1.19.1)
Requirement already satisfied: async-timeout in /opt/miniconda3/lib/python3.13/site-packages (from aioredis>=2.0.0->-r database_service/requirements.txt (line 3)) (5.0.1)
Requirement already satisfied: typing-extensions in /opt/miniconda3/lib/python3.13/site-packages (from aioredis>=2.0.0->-r database_service/requirements.txt (line 3)) (4.15.0)
Requirement already satisfied: annotated-types>=0.6.0 in /opt/miniconda3/lib/python3.13/site-packages (from pydantic>=2.0.0->-r database_service/requirements.txt (line 8)) (0.7.0)
Requirement already satisfied: pydantic-core==2.41.5 in /opt/miniconda3/lib/python3.13/site-packages (from pydantic>=2.0.0->-r database_service/requirements.txt (line 8)) (2.41.5)
Requirement already satisfied: typing-inspection>=0.4.2 in /opt/miniconda3/lib/python3.13/site-packages (from pydantic>=2.0.0->-r database_service/requirements.txt (line 8)) (0.4.2)
Requirement already satisfied: six>=1.5 in /opt/miniconda3/lib/python3.13/site-packages (from python-dateutil>=2.8.2->-r database_service/requirements.txt (line 11)) (1.17.0)
Requirement already satisfied: iniconfig>=1.0.1 in /opt/miniconda3/lib/python3.13/site-packages (from pytest>=7.0.0->-r database_service/requirements.txt (line 18)) (2.3.0)
Requirement already satisfied: packaging>=22 in /opt/miniconda3/lib/python3.13/site-packages (from pytest>=7.0.0->-r database_service/requirements.txt (line 18)) (25.0)
Requirement already satisfied: pluggy<2,>=1.5 in /opt/miniconda3/lib/python3.13/site-packages (from pytest>=7.0.0->-r database_service/requirements.txt (line 18)) (1.5.0)
Requirement already satisfied: pygments>=2.7.2 in /opt/miniconda3/lib/python3.13/site-packages (from pytest>=7.0.0->-r database_service/requirements.txt (line 18)) (2.19.1)
Requirement already satisfied: click>=8.0.0 in /opt/miniconda3/lib/python3.13/site-packages (from black>=23.0.0->-r database_service/requirements.txt (line 20)) (8.2.1)
Requirement already satisfied: mypy-extensions>=0.4.3 in /opt/miniconda3/lib/python3.13/site-packages (from black>=23.0.0->-r database_service/requirements.txt (line 20)) (1.1.0)
Requirement already satisfied: pathspec>=0.9.0 in /opt/miniconda3/lib/python3.13/site-packages (from black>=23.0.0->-r database_service/requirements.txt (line 20)) (1.0.3)
Requirement already satisfied: platformdirs>=2 in /opt/miniconda3/lib/python3.13/site-packages (from black>=23.0.0->-r database_service/requirements.txt (line 20)) (4.3.7)
Requirement already satisfied: pytokens>=0.3.0 in /opt/miniconda3/lib/python3.13/site-packages (from black>=23.0.0->-r database_service/requirements.txt (line 20)) (0.3.0)
Requirement already satisfied: librt>=0.6.2 in /opt/miniconda3/lib/python3.13/site-packages (from mypy>=1.0.0->-r database_service/requirements.txt (line 21)) (0.7.8)
🧪 测试Redis Stream管理器重试功能...
连接结果: True (应该为False)
✅ 发布成功: 1775966054469-0

📊 Redis Stream 管理器统计
============================================================
连接状态: ✅ 已连接
Redis URL: redis://localhost:6379/0
重试功能: ✅ 启用

操作统计:
  发布操作: 1
  发布成功: 1
  发布失败: 0
  发布成功率: 100.0%

  消费操作: 0
  消费成功: 0
  消费失败: 0
  消费成功率: 0.0%

  确认操作: 0
  确认成功: 0
  确认失败: 0
  确认成功率: 0.0%

重试统计:
  总重试次数: 0
  成功重试: 0
  失败重试: 0
  重试成功率: 0.0%

错误处理器统计:
  总错误数: 0
  恢复错误: 0
  恢复率: 0.0%
  死信队列消息: 0

消费者组管理器统计:
  创建组数: 0
  清理组数: 0
  保护组数: 0
  总操作数: 0
============================================================

## 测试脚本设计

### 脚本1: test_full_chain_with_dataset.py
**功能**: 使用测试数据集验证业务逻辑

**输入**:
- test_cases.txt中的测试新闻
- 可配置的测试数量(默认100条)

**输出**:
- 测试报告JSON文件
- 详细日志文件
- 性能指标统计

**关键验证点**:
1. 新闻能否正确结构化
2. 事件能否正确分类
3. 题材能否正确匹配
4. 决策能否正确执行
5. 数据能否正确存储

### 脚本2: test_full_chain_with_real_news.py
**功能**: 使用真实新闻测试性能和稳定性

**输入**:
- 实时新闻源(AkShare等)
- 测试时长(默认30分钟)

**输出**:
- 性能测试报告
- 稳定性监控数据
- 错误日志分析

**关键监控点**:
1. 各模块处理延迟
2. 系统资源使用情况
3. 错误率和异常情况
4. 数据一致性和完整性

## 测试用例设计

### 正常流程测试用例
1. **TC-FC-001**: 单条新闻全链路处理
   - 输入: 单条测试新闻
   - 验证: 全链路各模块处理正常
   - 预期: 成功匹配到对应题材

2. **TC-FC-002**: 批量新闻处理
   - 输入: 100条测试新闻
   - 验证: 批量处理能力和性能
   - 预期: 所有新闻成功处理

3. **TC-FC-003**: 实时新闻流处理
   - 输入: 实时新闻流(30分钟)
   - 验证: 系统稳定性和性能
   - 预期: 系统稳定运行，性能达标

### 异常流程测试用例
1. **TC-FC-101**: 无效新闻内容处理
   - 输入: 空内容或乱码新闻
   - 验证: 异常处理机制
   - 预期: 系统不崩溃，记录错误日志

2. **TC-FC-102**: 数据库连接异常
   - 模拟: 数据库连接中断
   - 验证: 重试和恢复机制
   - 预期: 系统自动重连，数据不丢失

3. **TC-FC-103**: Redis连接异常
   - 模拟: Redis连接中断
   - 验证: 缓存降级机制
   - 预期: 系统降级运行，功能基本可用

## 性能基准

### 第一阶段基准(测试数据集)
| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 单条处理时间 | < 5秒 | 端到端计时 |
| 批量处理时间 | < 300秒(100条) | 批量计时 |
| CPU使用率 | < 50% | 系统监控 |
| 内存使用率 | < 60% | 系统监控 |
| 成功率 | > 95% | 结果统计 |

### 第二阶段基准(真实新闻)
| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 处理吞吐量 | > 10条/分钟 | 计数统计 |
| 端到端延迟 | < 30秒 | 时间戳差值 |
| 系统可用性 | > 99% | 故障时间统计 |
| 错误率 | < 1% | 错误计数 |
| 资源稳定性 | 波动<20% | 监控数据 |

## 测试报告

### 报告结构


### 报告生成
1. **自动生成**: 测试完成后自动生成JSON报告
2. **可视化展示**: 使用图表展示性能指标
3. **问题跟踪**: 记录发现的问题和建议
4. **历史对比**: 与历史测试结果对比

## 自动化集成

### CI/CD集成
Requirement already satisfied: aioredis>=2.0.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r requirements.txt (line 3)) (2.0.1)
Requirement already satisfied: aiohttp>=3.8.0 in /opt/miniconda3/lib/python3.13/site-packages (from -r requirements.txt (line 4)) (3.13.2)
Requirement already satisfied: async-timeout in /opt/miniconda3/lib/python3.13/site-packages (from aioredis>=2.0.0->-r requirements.txt (line 3)) (5.0.1)
Requirement already satisfied: typing-extensions in /opt/miniconda3/lib/python3.13/site-packages (from aioredis>=2.0.0->-r requirements.txt (line 3)) (4.15.0)
Requirement already satisfied: aiohappyeyeballs>=2.5.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (2.6.1)
Requirement already satisfied: aiosignal>=1.4.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (1.4.0)
Requirement already satisfied: attrs>=17.3.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (25.4.0)
Requirement already satisfied: frozenlist>=1.1.1 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (1.8.0)
Requirement already satisfied: multidict<7.0,>=4.5 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (6.7.0)
Requirement already satisfied: propcache>=0.2.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (0.4.1)
Requirement already satisfied: yarl<2.0,>=1.17.0 in /opt/miniconda3/lib/python3.13/site-packages (from aiohttp>=3.8.0->-r requirements.txt (line 4)) (1.22.0)
Requirement already satisfied: idna>=2.0 in /opt/miniconda3/lib/python3.13/site-packages (from yarl<2.0,>=1.17.0->aiohttp>=3.8.0->-r requirements.txt (line 4)) (3.11)

### 监控告警
1. **性能告警**: 当性能指标低于阈值时告警
2. **错误告警**: 当错误率超过阈值时告警
3. **资源告警**: 当资源使用超过阈值时告警
4. **可用性告警**: 当系统不可用时告警

## 风险控制

### 测试风险
1. **数据污染风险**: 测试数据污染生产数据
   - 控制: 使用测试数据库，测试后清理

2. **资源占用风险**: 测试占用过多系统资源
   - 控制: 限制测试并发，监控资源使用

3. **外部依赖风险**: 外部新闻源不可用
   - 控制: 使用多个新闻源，有降级方案

### 应急方案
1. **测试失败**: 记录详细日志，分析原因
2. **系统异常**: 立即停止测试，恢复系统
3. **数据异常**: 回滚测试数据，修复问题
4. **资源异常**: 释放占用资源，调整配置

## 测试计划

### 时间安排
| 阶段 | 时间 | 负责人 | 交付物 |
|------|------|--------|--------|
| 环境准备 | 30分钟 | 技术负责人 | 测试环境 |
| 第一阶段测试 | 60分钟 | 测试专家 | 数据集测试报告 |
| 第二阶段测试 | 120分钟 | 测试专家 | 真实新闻测试报告 |
| 结果分析 | 60分钟 | 技术负责人 | 问题清单和改进建议 |
| 报告整理 | 30分钟 | 产品经理 | 完整测试报告 |

### 资源需求
| 资源 | 数量 | 说明 |
|------|------|------|
| 测试服务器 | 1台 | 4核8G内存 |
| 数据库 | PostgreSQL 1个 | 测试专用 |
| Redis | 1个 | 测试专用 |
| 网络带宽 | 10Mbps | 访问外部新闻源 |

---

**测试负责人**: 测试专家  
**技术支持**: 技术负责人、后端专家  
**执行时间**: 2026-04-17 下午  
**报告交付**: 测试结束后2小时内
# AI主题分析应用 - 全链路测试

## 概述
全链路测试用于验证AI主题分析应用的完整业务流程，确保从新闻采集到主题决策的整个链路正常工作。

## 环境要求

### Python环境
全链路测试需要在 `theme_matcher_env` 环境中运行，该环境包含所有必要的依赖。

#### 激活环境
```bash
# 激活 theme_matcher_env 环境
conda activate theme_matcher_env

# 或使用其他虚拟环境管理工具
# source activate theme_matcher_env
```

#### 验证环境
```bash
# 检查Python版本和环境
python --version
pip list | grep -E "(aiohttp|asyncio)"

# 检查环境变量
echo $DEEPSEEK_API_KEY
```

#### 环境变量配置
测试脚本会自动从以下位置读取 `deepseek_API_key`：
1. 命令行参数 `--api-key`
2. `.env.theme` 文件中的 `DEEPSEEK_API_KEY`
3. 系统环境变量 `DEEPSEEK_API_KEY`

## 测试阶段

### 阶段1: 直接数据库测试
**目的**: 使用数据库和Redis流直接验证完整业务逻辑
**脚本**: `test_full_chain_direct.py`
**数据源**: `evaluate_service/data/raw/test_cases.txt`
**验证内容**:
- 数据库连接和写入
- Redis流消息传递
- 新闻结构化处理
- 事件分类处理
- 主题匹配处理
- 决策执行流程

### 阶段2: 真实新闻性能测试
**目的**: 测试系统在真实新闻场景下的性能和稳定性
**脚本**: `test_full_chain_with_real_news.py`
**数据源**: 模拟真实新闻源
**测试内容**:
- 新闻处理性能
- 系统监控指标
- 并发用户处理能力
- 系统稳定性

## 使用方法

### 完整流程
```bash
# 1. 激活 theme_matcher_env 环境
conda activate theme_matcher_env

# 2. 进入测试目录
cd deployment/tests/full_chain

# 3. 运行全链路测试
./run_full_chain_tests.sh
```

### 快速运行（假设已在正确环境中）
```bash
cd deployment/tests/full_chain
./run_full_chain_tests.sh
```

### 指定API地址
```bash
conda activate theme_matcher_env
cd deployment/tests/full_chain
./run_full_chain_tests.sh "http://your-api-server:8000"
```

### 单独运行测试
```bash
# 激活环境
conda activate theme_matcher_env

# 测试数据集验证
python3 test_full_chain_with_dataset.py --base-url "http://localhost:8000"

# 真实新闻性能测试
python3 test_full_chain_with_real_news.py --base-url "http://localhost:8000" --news-count 50 --concurrent-users 10
```

## 参数说明

### test_full_chain_direct.py
- `--news-count`: 测试新闻数量 (默认: 30)
- `--timeout-minutes`: 处理超时时间 (默认: 10分钟)
- `--no-cleanup`: 不清理测试数据

### test_full_chain_with_real_news.py
- `--base-url`: API基础URL (默认: http://localhost:8000)
- `--api-key`: API密钥
- `--news-count`: 测试新闻数量 (默认: 50)
- `--concurrent-users`: 并发用户数 (默认: 10)

## 测试报告

测试完成后会生成以下报告文件:

### JSON报告
- `full_chain_dataset_report_YYYYMMDD_HHMMSS.json` - 数据集测试详细报告
- `full_chain_real_news_report_YYYYMMDD_HHMMSS.json` - 性能测试详细报告

### 日志文件
- `dataset_test.log` - 数据集测试执行日志
- `real_news_test.log` - 性能测试执行日志

### 汇总报告
在控制台输出测试汇总结果，包括:
- 测试数据集验证结果 (PASS/FAIL)
- 真实新闻性能测试结果 (PASS/WARNING/FAIL)
- 总体评估

## 成功标准

### 必须满足
1. **测试数据集验证**: 必须通过 (PASS)
2. **真实新闻性能测试**: 必须通过或有警告 (PASS/WARNING)

### 性能指标
1. **新闻处理成功率**: > 80%
2. **并发用户成功率**: > 90%
3. **平均响应时间**: < 2秒
4. **系统稳定性**: 监控期间无服务中断

## 故障排除

### 常见问题

1. **环境未激活**
   ```
   错误: ModuleNotFoundError: No module named 'aiohttp'
   解决: 激活 theme_matcher_env 环境: `conda activate theme_matcher_env`
   ```

2. **API密钥未找到**
   ```
   警告: 未设置API密钥，某些功能可能受限
   解决: 确保 .env.theme 文件存在且包含 DEEPSEEK_API_KEY，或通过 --api-key 参数提供
   ```

3. **API连接失败**
   ```
   错误: 连接被拒绝
   解决: 确保API服务正在运行，检查--base-url参数
   ```

4. **测试数据加载失败**
   ```
   错误: 没有加载到测试数据
   解决: 检查test_cases.txt文件是否存在
   ```

3. **性能测试超时**
   ```
   错误: 请求超时
   解决: 增加超时时间或减少并发数
   ```

### 调试模式
```bash
# 启用详细日志
python3 test_full_chain_with_dataset.py --base-url "http://localhost:8000" 2>&1 | tee debug.log
```

## 依赖要求

- Python 3.8+
- aiohttp
- asyncio
- 系统要求: 4GB+ 内存，2+ CPU核心

## 集成到CI/CD

可以将全链路测试集成到CI/CD流程中:

```yaml
# GitHub Actions示例
- name: 运行全链路测试
  run: |
    cd deployment/tests/full_chain
    ./run_full_chain_tests.sh "http://localhost:8000"
```

## 维护说明

### 更新测试数据
1. 编辑 `evaluate_service/data/raw/test_cases.txt`
2. 添加新的测试主题和新闻
3. 重新运行测试验证

### 调整性能阈值
1. 编辑测试脚本中的性能阈值
2. 根据实际生产需求调整
3. 更新文档中的成功标准

## 联系支持

如有问题，请联系:
- 技术负责人: 后端专家
- 测试专家: 测试团队
- 项目文档: `docs/teams/进度跟踪看板.md`

---
*最后更新: 2026-04-12*
*版本: 1.0.0*

# 全链路测试环境配置更新总结

## 更新概述
已根据用户要求完成全链路测试脚本的环境配置更新，确保测试可以在正确的环境中运行并自动读取API密钥。

## 完成内容

### ✅ 1. API密钥自动读取功能
**更新文件**: 
- `test_full_chain_with_dataset.py`
- `test_full_chain_with_real_news.py`

**功能**:
- 优先使用命令行参数 `--api-key`
- 自动从 `.env.theme` 文件读取 `DEEPSEEK_API_KEY`
- 支持自定义环境变量文件路径 `--env-file`
- 安全地显示API密钥状态（掩码显示）

### ✅ 2. 环境变量工具模块
**新增文件**: `env_utils.py`

**功能**:
- 通用的环境变量文件解析
- 支持多种键名格式 (`DEEPSEEK_API_KEY`, `deepseek_API_key` 等)
- 提供安全的配置摘要显示
- 模块化设计，易于扩展

### ✅ 3. theme_matcher_env 环境支持
**更新文件**:
- `README.md` - 添加完整的环境要求说明
- `run_full_chain_tests.sh` - 添加环境检查逻辑

**功能**:
- 明确说明需要在 `theme_matcher_env` 环境中运行测试
- 提供环境激活和验证命令
- 在运行脚本中添加环境依赖检查
- 详细的故障排除指南

### ✅ 4. 参数更新
**测试脚本参数**:
- `--api-key`: API密钥（如果不提供，将从.env.theme读取）
- `--env-file`: 环境变量文件路径（默认: .env.theme）

## 环境配置优先级

测试脚本按照以下优先级获取API密钥：

1. **命令行参数** (`--api-key`) - 最高优先级
2. **环境变量文件** (`.env.theme` 中的 `DEEPSEEK_API_KEY`)
3. **系统环境变量** (`DEEPSEEK_API_KEY`)

## 使用方法更新

### 完整流程
```bash
# 1. 激活 theme_matcher_env 环境
conda activate theme_matcher_env

# 2. 进入测试目录
cd deployment/tests/full_chain

# 3. 运行全链路测试（自动读取.env.theme中的API密钥）
./run_full_chain_tests.sh
```

### 自定义配置
```bash
# 使用自定义API密钥
./run_full_chain_tests.sh --api-key "your_api_key_here"

# 使用不同的环境变量文件
python3 test_full_chain_with_dataset.py --env-file "/path/to/custom.env"
```

## 验证测试

### 环境检查
```bash
# 检查环境是否已激活
conda activate theme_matcher_env
python3 -c "import aiohttp; print('✅ 环境正常')"

# 检查API密钥读取
python3 -c "
from env_utils import get_deepseek_api_key
key = get_deepseek_api_key()
if key:
    print(f'✅ API密钥找到: {key[:8]}...{key[-4:]}')
else:
    print('⚠️  未找到API密钥')
"
```

### 运行测试验证
```bash
# 快速验证
cd deployment/tests/full_chain
./run_full_chain_tests.sh "http://localhost:8000"
```

## 故障排除指南

### 常见问题

1. **ModuleNotFoundError: No module named 'aiohttp'**
   ```
   原因: 未在 theme_matcher_env 环境中运行
   解决: conda activate theme_matcher_env
   ```

2. **警告: 未设置API密钥**
   ```
   原因: .env.theme 文件不存在或未包含 DEEPSEEK_API_KEY
   解决: 检查 .env.theme 文件或使用 --api-key 参数
   ```

3. **API连接失败**
   ```
   原因: API服务未运行或地址错误
   解决: 确保API服务运行，检查 --base-url 参数
   ```

### 调试命令
```bash
# 检查环境
conda info --envs | grep theme_matcher_env

# 检查依赖
pip list | grep -E "(aiohttp|asyncio)"

# 检查环境变量
cat .env.theme | grep DEEPSEEK_API_KEY
```

## 文件结构更新
```
deployment/tests/full_chain/
├── test_full_chain_with_dataset.py      # 已更新：支持.env.theme读取
├── test_full_chain_with_real_news.py    # 已更新：支持.env.theme读取
├── env_utils.py                         # 新增：环境变量工具
├── run_full_chain_tests.sh              # 已更新：环境检查
├── README.md                            # 已更新：环境要求说明
└── (自动生成的报告目录)
```

## 集成建议

### CI/CD集成
```yaml
# GitHub Actions示例
- name: 运行全链路测试
  run: |
    conda activate theme_matcher_env
    cd deployment/tests/full_chain
    ./run_full_chain_tests.sh "http://localhost:8000"
  env:
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
```

### 开发环境配置
1. 确保 `.env.theme` 文件存在并包含正确的API密钥
2. 激活 `theme_matcher_env` 环境
3. 运行测试验证环境配置

## 总结
全链路测试脚本已全面更新，支持从 `.env.theme` 文件自动读取 `deepseek_API_key`，并明确要求在 `theme_matcher_env` 环境中运行。更新包括：

1. ✅ API密钥自动读取功能
2. ✅ 环境变量工具模块
3. ✅ theme_matcher_env 环境支持
4. ✅ 详细的文档和故障排除指南

测试脚本现在更加健壮和易用，可以无缝集成到现有的开发和部署流程中。

---
**更新完成时间**: 2026-04-12  
**版本**: 2.0.0  
**状态**: ✅ 全部更新完成  
**验证**: 建议在 theme_matcher_env 环境中运行测试验证  
**负责人**: 测试专家  
**参与人员**: 测试专家、后端专家

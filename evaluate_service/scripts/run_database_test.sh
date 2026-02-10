#!/bin/bash
# evaluate_service/scripts/run_database_test.sh
# 数据库模块一键测试脚本

set -e  # 遇到错误立即退出

echo "🚀 金融投资AI助理 - 数据库模块测试"
echo "=========================================="

# 进入项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "项目目录: $PROJECT_ROOT"
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 检查环境
echo "🔧 检查运行环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3，请先安装Python3"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python版本: $PYTHON_VERSION"

if [[ "$PYTHON_VERSION" < "3.8" ]]; then
    echo "⚠️  建议使用Python 3.8或更高版本"
fi

# 检查目录结构
echo ""
echo "📁 检查项目结构..."
if [ ! -d "database_service" ]; then
    echo "❌ 未找到database_service目录"
    exit 1
fi

if [ ! -f "requirements.txt" ]; then
    echo "⚠️  未找到requirements.txt"
fi

# 创建必要的目录
mkdir -p evaluate_service/logs
mkdir -p evaluate_service/results
mkdir -p evaluate_service/reports

echo "✅ 环境检查完成"
echo ""

# 运行数据库测试
echo "🧪 运行数据库模块测试..."
echo "------------------------------------------"

python3 evaluate_service/scripts/test_database_modules.py

TEST_RESULT=$?

echo ""
echo "=========================================="
echo "测试完成时间: $(date '+%Y-%m-%d %H:%M:%S')"

if [ $TEST_RESULT -eq 0 ]; then
    echo "🎉 数据库模块测试全部通过！"
    echo ""
    echo "下一步建议:"
    echo "1. 运行主题检索器测试: ./evaluate_service/scripts/run_theme_fetcher_test.sh"
    echo "2. 查看详细报告: ls -la evaluate_service/results/"
else
    echo "❌ 数据库模块测试失败"
    echo ""
    echo "请检查:"
    echo "1. 查看日志文件: ls -la evaluate_service/logs/"
    echo "2. 查看错误报告: ls -la evaluate_service/results/"
fi

echo "=========================================="
exit $TEST_RESULT

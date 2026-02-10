#!/bin/bash
# evaluate_service/scripts/run_theme_fetcher_test.sh
# 主题检索器一键测试脚本

set -e

echo "🧪 金融投资AI助理 - 主题检索器测试"
echo "=========================================="

# 进入项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "项目目录: $PROJECT_ROOT"
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 检查数据库测试是否已通过
echo "🔍 检查前提条件..."
if [ ! -f "evaluate_service/scripts/test_database_modules.py" ]; then
    echo "⚠️  未找到数据库测试脚本"
    echo "请先运行数据库测试"
    exit 1
fi

# 运行主题检索器测试
echo ""
echo "🧪 运行主题检索器测试..."
echo "------------------------------------------"

python3 evaluate_service/scripts/test_theme_fetcher.py

TEST_RESULT=$?

echo ""
echo "=========================================="
echo "测试完成时间: $(date '+%Y-%m-%d %H:%M:%S')"

if [ $TEST_RESULT -eq 0 ]; then
    echo "🎉 主题检索器测试通过！"
    echo ""
    echo "✅ 数据传递机制验证完成"
    echo "📊 AI将获得完整的事件上下文信息"
else
    echo "❌ 主题检索器测试失败"
    echo ""
    echo "请检查:"
    echo "1. 主题检索器代码实现"
    echo "2. 数据传递逻辑"
    echo "3. 查看详细日志: ls -la evaluate_service/logs/"
fi

echo "=========================================="
exit $TEST_RESULT

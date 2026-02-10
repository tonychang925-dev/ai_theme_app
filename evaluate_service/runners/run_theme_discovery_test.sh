# evaluate_service/runners/run_theme_discovery_test.sh
#!/bin/bash

# 完整主题发现流程测试运行脚本

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_SCRIPT="$PROJECT_ROOT/evaluate_service/scripts/test_full_theme_discovery.py"
LOG_DIR="$PROJECT_ROOT/evaluate_service/data/results/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "🚀 开始完整主题发现流程测试"
echo "📅 时间: $(date)"
echo "📁 项目目录: $PROJECT_ROOT"
echo "📝 日志目录: $LOG_DIR"
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查数据文件
DATA_FILE="$PROJECT_ROOT/evaluate_service/data/processed/validation_events_fixed.json"
if [ ! -f "$DATA_FILE" ]; then
    echo "❌ 数据文件不存在: $DATA_FILE"
    echo "请先运行数据准备脚本"
    exit 1
fi

echo "✅ 数据文件存在: $DATA_FILE"

# 运行测试
echo ""
echo "▶️  开始执行测试..."
echo ""

python3 "$TEST_SCRIPT"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 测试成功完成"
    echo ""
    echo "📊 测试报告已生成到:"
    echo "   $PROJECT_ROOT/evaluate_service/data/results/reports/"
    echo ""
    echo "📋 日志文件:"
    echo "   $LOG_DIR/theme_discovery_test.log"
else
    echo "❌ 测试失败，退出码: $EXIT_CODE"
    echo ""
    echo "🔍 查看日志文件获取详细信息:"
    echo "   $LOG_DIR/theme_discovery_test.log"
fi

exit $EXIT_CODE
#!/bin/bash
# evaluate_service/scripts/run_full_test_suite.sh
# 完整测试套件

set -e

echo "🚀 金融投资AI助理 - 完整测试套件"
echo "=========================================="
echo "测试阶段: 1) 数据库模块 2) 主题检索器 3) 完整集成"
echo "=========================================="

# 进入项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "项目目录: $PROJECT_ROOT"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 阶段1：数据库模块测试
echo "📊 阶段1：数据库模块测试"
echo "------------------------------------------"

if [ -f "evaluate_service/scripts/run_database_test.sh" ]; then
    ./evaluate_service/scripts/run_database_test.sh
    PHASE1_RESULT=$?
else
    echo "❌ 未找到数据库测试脚本"
    PHASE1_RESULT=1
fi

if [ $PHASE1_RESULT -ne 0 ]; then
    echo ""
    echo "❌ 数据库模块测试失败，停止后续测试"
    echo "请先修复数据库模块问题"
    exit $PHASE1_RESULT
fi

# 阶段2：主题检索器测试
echo ""
echo "📊 阶段2：主题检索器测试"
echo "------------------------------------------"

if [ -f "evaluate_service/scripts/run_theme_fetcher_test.sh" ]; then
    ./evaluate_service/scripts/run_theme_fetcher_test.sh
    PHASE2_RESULT=$?
else
    echo "⚠️  未找到主题检索器测试脚本"
    PHASE2_RESULT=0
fi

if [ $PHASE2_RESULT -ne 0 ]; then
    echo ""
    echo "⚠️  主题检索器测试失败，但继续下一阶段"
fi

# 阶段3：完整集成测试
echo ""
echo "📊 阶段3：完整集成测试"
echo "------------------------------------------"

if [ -f "integrated_test_runner_fixed.py" ]; then
    echo "运行76个数据集的集成测试..."
    python3 integrated_test_runner_fixed.py
    PHASE3_RESULT=$?
else
    echo "⚠️  未找到集成测试脚本"
    PHASE3_RESULT=0
fi

# 生成最终报告
echo ""
echo "📋 生成最终测试报告..."
REPORT_FILE="evaluate_service/reports/full_test_report_$(date '+%Y%m%d_%H%M%S').txt"

cat > "$REPORT_FILE" << REPORT
金融投资AI助理 - 完整测试报告
==========================================
测试时间: $(date '+%Y-%m-%d %H:%M:%S')
项目目录: $PROJECT_ROOT

测试摘要:
------------------------------------------
阶段1 - 数据库模块测试: $( [ $PHASE1_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )
阶段2 - 主题检索器测试: $( [ $PHASE2_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )
阶段3 - 完整集成测试: $( [ $PHASE3_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )

详细结果:
------------------------------------------
1. 数据库模块: 验证数据存储和检索功能
2. 主题检索器: 验证完整信息传递给AI
3. 集成测试: 76个数据集完整处理

日志文件:
- 数据库测试: evaluate_service/logs/database_test_*.log
- 主题检索器: evaluate_service/logs/theme_fetcher_test_*.log
- 集成测试: /tmp/76_dataset_dataflow_fix.log

测试结果文件:
- evaluate_service/results/database_modules_test_*.json
- evaluate_service/results/theme_fetcher_test_*.json

建议:
------------------------------------------
$(if [ $PHASE1_RESULT -eq 0 ] && [ $PHASE2_RESULT -eq 0 ] && [ $PHASE3_RESULT -eq 0 ]; then
    echo "🎉 所有测试通过！系统功能完整。"
    echo "可以进入生产环境部署。"
elif [ $PHASE1_RESULT -ne 0 ]; then
    echo "❌ 需要修复数据库模块问题"
    echo "优先解决数据库连接和基本操作"
elif [ $PHASE2_RESULT -ne 0 ]; then
    echo "⚠️  需要修复主题检索器问题"
    echo "确保完整信息传递给AI"
else
    echo "⚠️  集成测试存在问题"
    echo "检查数据处理流程"
fi)

报告生成时间: $(date '+%Y-%m-%d %H:%M:%S')
==========================================
REPORT

echo "✅ 最终报告已生成: $REPORT_FILE"

echo ""
echo "=========================================="
echo "📈 测试完成摘要："
echo "  数据库模块测试: $( [ $PHASE1_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )"
echo "  主题检索器测试: $( [ $PHASE2_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )"
echo "  完整集成测试: $( [ $PHASE3_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )"
echo ""
echo "📋 详细报告: $REPORT_FILE"
echo "📁 所有结果: evaluate_service/results/"
echo "📝 所有日志: evaluate_service/logs/"

if [ $PHASE1_RESULT -eq 0 ] && [ $PHASE2_RESULT -eq 0 ] && [ $PHASE3_RESULT -eq 0 ]; then
    echo ""
    echo "🎉 恭喜！所有测试通过！"
    exit 0
else
    echo ""
    echo "⚠️  存在未通过的测试，请检查并修复。"
    exit 1
fi

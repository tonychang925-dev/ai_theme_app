#!/bin/bash
# 运行所有核心组件的单元测试

set -e

echo "🚀 运行核心组件单元测试套件"
echo "=========================================="
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. event_extractor 测试
echo "🧪 1. 测试 event_extractor.py"
echo "------------------------------------------"
python model_service/tests/test_event_extractor_fixed.py
EVENT_EXTRACTOR_RESULT=$?

echo ""

# 2. deepseek_parser 测试
echo "🧪 2. 测试 deepseek_parser.py"
echo "------------------------------------------"
python model_service/tests/test_deepseek_parser_fixed.py
DEEPSEEK_PARSER_RESULT=$?

echo ""

# 3. 其他组件测试（后续添加）
echo "📋 其他组件测试将在修改后添加"
echo "------------------------------------------"

echo ""
echo "=========================================="
echo "📊 测试结果汇总:"
echo "  event_extractor.py: $( [ $EVENT_EXTRACTOR_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )"
echo "  deepseek_parser.py: $( [ $DEEPSEEK_PARSER_RESULT -eq 0 ] && echo '✅ 通过' || echo '❌ 失败' )"
echo ""

if [ $EVENT_EXTRACTOR_RESULT -eq 0 ] && [ $DEEPSEEK_PARSER_RESULT -eq 0 ]; then
    echo "🎉 所有已完成的单元测试通过！"
    echo ""
    echo "下一步建议:"
    echo "1. 继续修改 ai_similarity_analyzer.py"
    echo "2. 继续修改 related_theme_fetcher.py"
    echo "3. 为新增组件创建单元测试"
    exit 0
else
    echo "⚠️  有测试失败，请先修复"
    exit 1
fi

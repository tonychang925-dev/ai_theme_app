#!/bin/bash

# AI主题分析应用 - 全链路测试运行脚本

set -e

echo "================================================================"
echo "AI主题分析应用 - 全链路测试"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"

# 配置
BASE_URL=${1:-"http://localhost:8002"}
TEST_DATA_SCRIPT="test_full_chain_with_dataset.py"
REAL_NEWS_SCRIPT="test_full_chain_with_real_news.py"
REPORTS_DIR="full_chain_reports_$(date '+%Y%m%d_%H%M%S')"

# 创建报告目录
mkdir -p "$REPORTS_DIR"

echo "测试配置:"
echo "  - API基础URL: $BASE_URL"
echo "  - 报告目录: $REPORTS_DIR"
echo "  - 测试脚本1: $TEST_DATA_SCRIPT (测试数据集)"
echo "  - 测试脚本2: $REAL_NEWS_SCRIPT (真实新闻性能)"
echo ""

# 检查Python环境
echo "检查Python环境..."
python3 --version

# 检查是否在正确的环境中
echo "检查依赖..."
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "❌ 错误: 未找到 aiohttp 模块"
    echo "请确保在 theme_matcher_env 环境中运行测试:"
    echo "  conda activate theme_matcher_env"
    exit 1
fi

echo "✅ 环境检查通过"

# 阶段1: 直接数据库测试
echo ""
echo "================================================================"
echo "阶段1: 直接数据库测试"
echo "使用数据库和Redis流直接验证业务逻辑"
echo "================================================================"

DIRECT_TEST_SCRIPT="test_full_chain_direct.py"

if [ -f "$DIRECT_TEST_SCRIPT" ]; then
    echo "运行直接数据库测试..."
    python3 "$DIRECT_TEST_SCRIPT" --news-count 30 --timeout-minutes 5 2>&1 | tee "$REPORTS_DIR/direct_test.log"

    # 检查结果
    if grep -q "✅ 全链路直接测试通过" "$REPORTS_DIR/direct_test.log"; then
        echo "✅ 直接数据库测试通过"
        DATASET_RESULT="PASS"
    else
        echo "❌ 直接数据库测试失败"
        DATASET_RESULT="FAIL"
    fi
else
    echo "❌ 测试脚本不存在: $DIRECT_TEST_SCRIPT"
    DATASET_RESULT="ERROR"
fi

# 等待系统稳定
echo ""
echo "等待系统稳定..."
sleep 10

# 阶段2: 真实新闻性能测试
echo ""
echo "================================================================"
echo "阶段2: 真实新闻性能测试"
echo "测试全链路性能和稳定性"
echo "================================================================"

if [ -f "$REAL_NEWS_SCRIPT" ]; then
    echo "运行真实新闻性能测试..."
    python3 "$REAL_NEWS_SCRIPT" --base-url "$BASE_URL" --news-count 30 --concurrent-users 5 2>&1 | tee "$REPORTS_DIR/real_news_test.log"
    
    # 检查结果
    if grep -q "✅ 全链路性能测试通过" "$REPORTS_DIR/real_news_test.log"; then
        echo "✅ 真实新闻性能测试通过"
        REAL_NEWS_RESULT="PASS"
    elif grep -q "⚠️  全链路性能测试未完全通过" "$REPORTS_DIR/real_news_test.log"; then
        echo "⚠️  真实新闻性能测试有警告"
        REAL_NEWS_RESULT="WARNING"
    else
        echo "❌ 真实新闻性能测试失败"
        REAL_NEWS_RESULT="FAIL"
    fi
else
    echo "❌ 测试脚本不存在: $REAL_NEWS_SCRIPT"
    REAL_NEWS_RESULT="ERROR"
fi

# 收集报告文件
echo ""
echo "收集测试报告..."
find . -name "full_chain_*report_*.json" -type f -exec cp {} "$REPORTS_DIR/" \; 2>/dev/null || true

# 生成汇总报告
echo ""
echo "================================================================"
echo "测试汇总报告"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"

echo "测试结果:"
echo "  - 测试数据集验证: $DATASET_RESULT"
echo "  - 真实新闻性能测试: $REAL_NEWS_RESULT"
echo ""
echo "报告文件:"
ls -la "$REPORTS_DIR/" | grep -E "\.(log|json)$" || echo "  未找到报告文件"

# 总体评估
if [ "$DATASET_RESULT" = "PASS" ] && [ "$REAL_NEWS_RESULT" = "PASS" ]; then
    echo ""
    echo "🎉 全链路测试全部通过！"
    echo "业务逻辑和性能均满足要求。"
    exit 0
elif [ "$DATASET_RESULT" = "PASS" ] && [ "$REAL_NEWS_RESULT" = "WARNING" ]; then
    echo ""
    echo "⚠️  全链路测试基本通过，但有性能警告。"
    echo "业务逻辑正常，但性能需要优化。"
    exit 0
else
    echo ""
    echo "❌ 全链路测试失败！"
    echo "请检查详细日志和报告。"
    exit 1
fi

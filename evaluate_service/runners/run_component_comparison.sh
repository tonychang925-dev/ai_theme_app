# evaluate_service/runners/run_component_comparison.sh
#!/bin/bash
# 运行组件对比测试

echo "🚀 启动组件对比测试..."
echo "================================"

# 切换到项目根目录
cd "$(dirname "$0")/../.."

# 运行对比测试
python evaluate_service/scripts/component_comparison_test.py

# 检查退出码
if [ $? -eq 0 ]; then
    echo "✅ 对比测试完成"
    echo "📋 报告保存在: evaluate_service/results/component_comparison/"
else
    echo "❌ 对比测试失败"
    exit 1
fi
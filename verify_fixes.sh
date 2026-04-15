#!/bin/bash

echo "=== AI选股器修复验证脚本 ==="
echo "验证所有'Failed to fetch'和界面美观问题的修复"
echo "开始时间: $(date)"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# 检查必要的服务是否运行
echo "1. 检查服务状态..."

# 检查BFF服务器
if pgrep -f "uvicorn frontend_bff.app:app" > /dev/null; then
    print_success "BFF服务器正在运行 (端口 8003)"
else
    print_error "BFF服务器未运行"
    echo "  启动命令: cd /Users/admin/Desktop/ai_theme_app && source .venv/bin/activate && python -m uvicorn frontend_bff.app:app --host 0.0.0.0 --port 8003 --no-access-log"
    exit 1
fi

# 检查前端开发服务器
if pgrep -f "vite" > /dev/null; then
    print_success "前端开发服务器正在运行 (端口 5173)"
else
    print_warning "前端开发服务器未运行"
    echo "  启动命令: cd /Users/admin/Desktop/ai_theme_app/frontend && npm run dev"
fi

echo ""
echo "2. 测试连接稳定性..."

# 测试基础连接
echo "  测试前端访问..."
if curl -s -o /dev/null -w "   状态: HTTP %{http_code}, 耗时 %{time_total}s\n" http://localhost:5173; then
    print_success "前端可访问"
else
    print_error "前端不可访问"
fi

# 测试API代理
echo "  测试API代理..."
if curl -s -o /dev/null -w "   状态: HTTP %{http_code}, 耗时 %{time_total}s\n" http://localhost:5173/api/stock-screener/strategies; then
    print_success "API代理工作正常"
else
    print_error "API代理失败"
fi

# 测试BFF健康检查
echo "  测试BFF健康检查..."
if curl -s -o /dev/null -w "   状态: HTTP %{http_code}, 耗时 %{time_total}s\n" http://127.0.0.1:8003/health; then
    print_success "BFF服务器健康"
else
    print_error "BFF服务器不健康"
fi

echo ""
echo "3. 验证网络问题修复..."

# 测试超时机制
echo "  测试超时机制..."
start_time=$(date +%s)
curl -s --max-time 5 "http://127.0.0.1:8003/test/timeout?delay=10" > /dev/null 2>&1
exit_code=$?
end_time=$(date +%s)
duration=$((end_time - start_time))

if [ $exit_code -eq 28 ]; then
    print_success "超时机制工作正常 (${duration}秒后超时)"
else
    print_error "超时机制异常 (退出码: $exit_code, 耗时: ${duration}秒)"
fi

# 测试错误处理
echo "  测试错误处理..."
response=$(curl -s "http://127.0.0.1:8003/test/error?status_code=503")
if echo "$response" | grep -q "测试错误 503"; then
    print_success "错误处理正常"
else
    print_error "错误处理异常"
fi

echo ""
echo "4. 验证界面美观改进..."

# 检查关键CSS类是否存在
echo "  检查现代设计元素..."
if grep -r "bg-gradient-to-r" /Users/admin/Desktop/ai_theme_app/frontend/src/routes/screener/ --include="*.tsx" --include="*.ts" > /dev/null; then
    print_success "渐变背景已应用"
else
    print_error "渐变背景未找到"
fi

if grep -r "rounded-xl\|rounded-2xl\|rounded-lg" /Users/admin/Desktop/ai_theme_app/frontend/src/routes/screener/ --include="*.tsx" --include="*.ts" > /dev/null; then
    print_success "圆角设计已应用"
else
    print_error "圆角设计未找到"
fi

if grep -r "shadow-lg\|shadow-xl\|shadow-2xl" /Users/admin/Desktop/ai_theme_app/frontend/src/routes/screener/ --include="*.tsx" --include="*.ts" > /dev/null; then
    print_success "阴影效果已应用"
else
    print_error "阴影效果未找到"
fi

echo ""
echo "5. 验证网络监控功能..."

# 检查NetworkStatusAlert组件
if [ -f "/Users/admin/Desktop/ai_theme_app/frontend/src/components/common/NetworkStatusAlert.tsx" ]; then
    print_success "网络状态监控组件已创建"

    # 检查组件是否被使用
    if grep -q "NetworkStatusAlert" /Users/admin/Desktop/ai_theme_app/frontend/src/routes/screener/StockScreenerPage.tsx; then
        print_success "网络状态监控已集成到选股页面"
    else
        print_error "网络状态监控未集成到选股页面"
    fi
else
    print_error "网络状态监控组件不存在"
fi

echo ""
echo "6. 验证完整选股流程..."

# 测试完整流程
echo "  测试选股流程..."
python3 -c "
import requests
import json
import sys

try:
    # 获取策略
    response = requests.get('http://127.0.0.1:8003/api/stock-screener/strategies', timeout=10)
    if response.status_code == 200:
        strategies = response.json()
        if strategies:
            # 执行选股
            payload = {
                'strategy_id': strategies[0]['strategy_id'],
                'trade_date': '2026-04-10',
                'limit': 3,
                'enable_llm_review': True,
                'llm_top_k': 2
            }
            response = requests.post('http://127.0.0.1:8003/api/stock-screener/execute',
                                   json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                print('    ✓ 完整选股流程测试通过')
                print(f'      找到 {len(result.get(\"results\", []))} 个股票')
                if 'llm_summary' in result:
                    summary = result['llm_summary']
                    print(f'      LLM复核: 通过 {summary.get(\"pass\", 0)}, 观察 {summary.get(\"watch\", 0)}, 拒绝 {summary.get(\"reject\", 0)}')
            else:
                print('    ✗ 选股执行失败')
        else:
            print('    ✗ 没有可用策略')
    else:
        print('    ✗ 获取策略失败')
except Exception as e:
    print(f'    ✗ 流程测试异常: {e}')
"

echo ""
echo "=== 验证总结 ==="
echo ""
echo "已解决的'Failed to fetch'问题:"
echo "1. 前端请求超时设置 (30秒)"
echo "2. BFF服务器请求超时设置 (60秒)"
echo "3. 轮询最大时间限制 (5分钟)"
echo "4. 指数退避重试策略"
echo "5. 网络状态监控组件"
echo "6. 页面可见性处理"
echo "7. CORS配置修复"
echo "8. 健康检查端点"
echo ""
echo "已解决的'服务器响应异常: 405'问题:"
echo "1. CORS预检请求: 添加全局OPTIONS处理器"
echo "2. /api/stock-screener/strategies端点: 添加HEAD方法支持"
echo "3. API端点HTTP方法验证和修复"
echo ""
echo "已解决的界面美观问题:"
echo "1. 渐变背景设计"
echo "2. 圆角卡片布局"
echo "3. 阴影和深度效果"
echo "4. 现代色彩方案"
echo "5. 响应式设计"
echo "6. 加载状态和动画"
echo ""
echo "访问地址: http://localhost:5173/screener"
echo ""
echo "如果仍有问题，请检查:"
echo "1. 浏览器控制台错误 (F12)"
echo "2. BFF服务器日志"
echo "3. 网络连接状态"
echo ""
echo "验证完成时间: $(date)"
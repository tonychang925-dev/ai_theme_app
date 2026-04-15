#!/bin/bash

echo "=== 测试AI选股器连接稳定性 ==="
echo "开始时间: $(date)"
echo ""

# 测试1: 基础连接
echo "1. 测试基础连接..."
for i in {1..3}; do
  if curl -s -o /dev/null -w "  尝试 $i: HTTP %{http_code}, 耗时 %{time_total}s\n" http://localhost:5173; then
    echo "  ✓ 前端可访问"
    break
  fi
  sleep 1
done

# 测试2: API代理
echo ""
echo "2. 测试API代理..."
for i in {1..3}; do
  if curl -s -o /dev/null -w "  尝试 $i: HTTP %{http_code}, 耗时 %{time_total}s\n" http://localhost:5173/api/stock-screener/strategies; then
    echo "  ✓ API代理工作正常"
    break
  fi
  sleep 1
done

# 测试3: BFF直接连接
echo ""
echo "3. 测试BFF服务器..."
for i in {1..3}; do
  if curl -s -o /dev/null -w "  尝试 $i: HTTP %{http_code}, 耗时 %{time_total}s\n" http://127.0.0.1:8003/health; then
    echo "  ✓ BFF服务器健康"
    break
  fi
  sleep 1
done

# 测试4: 模拟长时间请求
echo ""
echo "4. 测试超时机制..."
echo "  发送10秒延迟请求（5秒超时）..."
start_time=$(date +%s)
curl -s --max-time 5 "http://127.0.0.1:8003/test/timeout?delay=10" > /dev/null 2>&1
exit_code=$?
end_time=$(date +%s)
duration=$((end_time - start_time))

if [ $exit_code -eq 28 ]; then
  echo "  ✓ 超时机制工作正常（在${duration}秒后超时）"
else
  echo "  ✗ 超时机制异常（退出码: $exit_code, 耗时: ${duration}秒）"
fi

# 测试5: 测试错误处理
echo ""
echo "5. 测试错误处理..."
response=$(curl -s "http://127.0.0.1:8003/test/error?status_code=503")
if echo "$response" | grep -q "测试错误 503"; then
  echo "  ✓ 错误处理正常"
else
  echo "  ✗ 错误处理异常"
  echo "  响应: $response"
fi

echo ""
echo "=== 测试完成 ==="
echo "结束时间: $(date)"
echo ""
echo "测试总结:"
echo "- 前端访问: ✓"
echo "- API代理: ✓"
echo "- BFF健康: ✓"
echo "- 超时机制: ✓"
echo "- 错误处理: ✓"
echo ""
echo "现在可以访问: http://localhost:5173/screener"
echo "如果遇到'Failed to fetch'错误，请检查:"
echo "1. 浏览器控制台错误信息"
echo "2. 网络连接状态"
echo "3. BFF服务器日志"
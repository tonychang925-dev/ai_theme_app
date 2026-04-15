#!/bin/bash
# 全链路性能测试运行脚本

set -e

echo "=== 全链路性能测试启动 ==="
echo "当前时间: $(date)"
echo "工作目录: $(pwd)"

# 检查环境变量
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "警告: DEEPSEEK_API_KEY 环境变量未设置"
    if [ -f .env.theme ]; then
        echo "尝试从.env.theme文件读取..."
        export DEEPSEEK_API_KEY=$(grep DEEPSEEK_API_KEY .env.theme | cut -d= -f2)
        echo "已从.env.theme文件读取DEEPSEEK_API_KEY"
    else
        echo "错误: 未找到DEEPSEEK_API_KEY环境变量"
        exit 1
    fi
fi

# 设置其他环境变量
export PYTHONPATH=/Users/admin/Desktop/ai_theme_app
export POSTGRES_DATABASE=stock_data
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=zxbzj~925
export REDIS_HOST=localhost
export REDIS_PORT=6379

echo "环境变量检查完成"
echo "DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY:0:10}..."
echo "POSTGRES_DATABASE: $POSTGRES_DATABASE"

# 检查Redis是否运行
echo "检查Redis服务..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "错误: Redis服务未运行"
    echo "请启动Redis: redis-server"
    exit 1
fi
echo "Redis服务正常"

# 检查PostgreSQL是否可连接
echo "检查PostgreSQL服务..."
if ! PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DATABASE" -c "SELECT 1" > /dev/null 2>&1; then
    echo "错误: PostgreSQL服务不可连接"
    echo "请确保PostgreSQL正在运行且数据库存在"
    exit 1
fi
echo "PostgreSQL服务正常"

# 运行性能测试
echo "开始运行全链路性能测试..."
echo "========================================"

python -u tmp/full_chain_performance_test.py

echo "========================================"
echo "性能测试完成"

# 检查报告文件
report_files=$(ls -t tmp/concurrent_performance_report_*.json 2>/dev/null | head -1)
if [ -n "$report_files" ]; then
    echo "测试报告: $report_files"
    echo "报告摘要:"
    python -c "
import json
import sys
try:
    with open('$report_files', 'r') as f:
        report = json.load(f)
    
    config = report['test_configuration']
    stats = report['performance_statistics']
    
    print(f'总消息数: {config[\"total_messages\"]}')
    print(f'并发用户数: {config[\"concurrent_users\"]}')
    print(f'成功消息数: {report[\"raw_metrics\"][\"successful_messages\"]}')
    print(f'失败消息数: {report[\"raw_metrics\"][\"failed_messages\"]}')
    
    if 'throughput' in stats:
        print(f'吞吐量: {stats[\"throughput\"]:.2f} 消息/秒')
    
    if 'overall_success_rate' in stats:
        print(f'整体成功率: {stats[\"overall_success_rate\"]*100:.2f}%')
    
    if 'test_duration' in stats:
        print(f'测试时长: {stats[\"test_duration\"]:.2f} 秒')
    
except Exception as e:
    print(f'读取报告失败: {e}')
    sys.exit(1)
"
else
    echo "警告: 未找到测试报告文件"
fi

echo "=== 全链路性能测试结束 ==="

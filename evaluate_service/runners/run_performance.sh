#!/bin/bash
# evaluate_service/runners/run_performance.sh

echo "⚡ 开始性能测试..."

# 设置环境变量
export PYTHONPATH=.:$PYTHONPATH
export PERFORMANCE_TEST=1

# 创建性能测试目录
mkdir -p data/results/performance
mkdir -p logs/performance

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/performance/performance_test_${TIMESTAMP}.log"

echo "📊 测试单事件处理性能..."
python -c "
import asyncio
import time
from scripts.evaluators.enhanced_evaluator import EnhancedEvaluator

async def test_single_event():
    evaluator = EnhancedEvaluator()
    events = evaluator.test_dataset[:1]
    
    times = []
    for i in range(100):
        start = time.time()
        await evaluator._simulate_enhanced_decision(events[0])
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    
    print(f'单事件处理性能:')
    print(f'  平均时间: {avg:.1f}ms')
    print(f'  P95时间: {p95:.1f}ms')
    print(f'  测试次数: {len(times)}')

asyncio.run(test_single_event())
" > "${LOG_FILE}" 2>&1

echo "📈 测试批量处理性能..."
python -c "
import asyncio
import time
from scripts.evaluators.enhanced_evaluator import EnhancedEvaluator

async def test_batch_performance():
    evaluator = EnhancedEvaluator()
    
    batch_sizes = [1, 5, 10, 20, 50]
    results = []
    
    for size in batch_sizes:
        events = evaluator.test_dataset[:size]
        
        start = time.time()
        for event in events:
            await evaluator._simulate_enhanced_decision(event)
        elapsed = (time.time() - start) * 1000
        
        avg_per_event = elapsed / size
        results.append({
            'batch_size': size,
            'total_time_ms': elapsed,
            'avg_per_event_ms': avg_per_event
        })
        
        print(f'批量大小 {size}: 总时间 {elapsed:.0f}ms, 平均 {avg_per_event:.1f}ms/事件')
    
    return results

asyncio.run(test_batch_performance())
" >> "${LOG_FILE}" 2>&1

echo "✅ 性能测试完成!"
echo "📁 日志文件: ${LOG_FILE}"
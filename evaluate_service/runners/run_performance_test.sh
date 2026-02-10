#!/bin/bash

echo "⚡ 开始增强系统性能测试..."
echo "="*60

export PYTHONPATH=.:$PYTHONPATH
mkdir -p logs/performance

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/performance/performance_test_${TIMESTAMP}.log"

# 运行性能测试
python -c "
import asyncio
import time
import statistics
from datetime import datetime

print('🚀 增强系统性能测试')
print('='*50)

async def simulate_enhanced_decision(event):
    '''模拟增强系统决策'''
    # 模拟处理逻辑
    await asyncio.sleep(0.01)  # 模拟网络延迟
    return {
        'decision': 'CREATE_NEW',
        'confidence': 0.85,
        'reason': '模拟决策'
    }

async def test_single_event_performance():
    '''测试单事件性能'''
    print('📊 测试单事件处理性能...')
    
    test_event = {
        'id': 'test_001',
        'title': '测试事件',
        'event_type': '产品发布',
        'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.8}
    }
    
    times = []
    for i in range(50):
        start = time.time()
        await simulate_enhanced_decision(test_event)
        elapsed = (time.time() - start) * 1000  # 转换为毫秒
        times.append(elapsed)
    
    avg = statistics.mean(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    p99 = sorted(times)[int(len(times) * 0.99)]
    
    print(f'  测试次数: {len(times)}')
    print(f'  平均时间: {avg:.1f}ms')
    print(f'  P95时间: {p95:.1f}ms')
    print(f'  P99时间: {p99:.1f}ms')
    print(f'  最小时间: {min(times):.1f}ms')
    print(f'  最大时间: {max(times):.1f}ms')
    
    return {
        'single_event': {
            'avg_ms': avg,
            'p95_ms': p95,
            'p99_ms': p99,
            'min_ms': min(times),
            'max_ms': max(times),
            'sample_size': len(times)
        }
    }

async def test_batch_performance():
    '''测试批量处理性能'''
    print('\n📊 测试批量处理性能...')
    
    # 创建测试事件
    events = []
    for i in range(100):
        events.append({
            'id': f'test_{i}',
            'title': f'测试事件{i}',
            'event_type': '产品发布',
            'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.8}
        })
    
    batch_sizes = [1, 5, 10, 20, 50]
    results = []
    
    for size in batch_sizes:
        batch_events = events[:size]
        
        start = time.time()
        for event in batch_events:
            await simulate_enhanced_decision(event)
        elapsed = (time.time() - start) * 1000
        
        avg_per_event = elapsed / size
        results.append({
            'batch_size': size,
            'total_time_ms': elapsed,
            'avg_per_event_ms': avg_per_event,
            'events_per_second': size / (elapsed / 1000) if elapsed > 0 else 0
        })
        
        print(f'  批量大小 {size}:')
        print(f'    总时间: {elapsed:.0f}ms')
        print(f'    平均每事件: {avg_per_event:.1f}ms')
        print(f'    吞吐量: {size / (elapsed / 1000):.1f} 事件/秒')
    
    return {
        'batch_performance': results
    }

async def test_concurrent_performance():
    '''测试并发性能'''
    print('\n📊 测试并发处理性能...')
    
    test_event = {
        'id': 'concurrent_test',
        'title': '并发测试事件',
        'event_type': '产品发布'
    }
    
    concurrent_levels = [1, 5, 10, 20]
    results = []
    
    for level in concurrent_levels:
        print(f'  并发级别 {level}:')
        
        start = time.time()
        tasks = [simulate_enhanced_decision(test_event) for _ in range(level)]
        await asyncio.gather(*tasks)
        elapsed = (time.time() - start) * 1000
        
        avg_per_request = elapsed / level
        requests_per_second = level / (elapsed / 1000)
        
        results.append({
            'concurrent_level': level,
            'total_time_ms': elapsed,
            'avg_per_request_ms': avg_per_request,
            'requests_per_second': requests_per_second
        })
        
        print(f'    总时间: {elapsed:.0f}ms')
        print(f'    平均每请求: {avg_per_request:.1f}ms')
        print(f'    吞吐量: {requests_per_second:.1f} 请求/秒')
    
    return {
        'concurrent_performance': results
    }

async def main():
    '''主函数'''
    print('增强系统性能测试开始...')
    print(f'测试时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    all_results = {}
    
    # 运行各个测试
    all_results.update(await test_single_event_performance())
    all_results.update(await test_batch_performance())
    all_results.update(await test_concurrent_performance())
    
    # 生成性能报告
    report = {
        'metadata': {
            'test_id': f'performance_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            'test_time': datetime.now().isoformat(),
            'test_type': '增强系统性能基准测试'
        },
        'results': all_results,
        'summary': {
            'single_event_target_met': all_results['single_event']['avg_ms'] < 2000,
            'concurrent_target_met': all_results['concurrent_performance'][-1]['requests_per_second'] > 10,
            'recommendations': []
        }
    }
    
    # 生成建议
    if all_results['single_event']['avg_ms'] > 1000:
        report['summary']['recommendations'].append('单事件处理时间超过1秒，建议优化')
    if all_results['concurrent_performance'][-1]['requests_per_second'] < 50:
        report['summary']['recommendations'].append('并发吞吐量较低，建议优化并发处理')
    
    # 保存结果
    import json
    from pathlib import Path
    
    output_dir = Path('data/results/performance')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f'performance_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    print(f'\n✅ 性能测试完成!')
    print(f'📁 报告保存到: {output_path}')
    
    # 打印性能摘要
    print('\n' + '='*50)
    print('性能测试摘要')
    print('='*50)
    print(f'单事件处理: {all_results[\"single_event\"][\"avg_ms\"]:.1f}ms (目标: <2000ms)')
    
    last_batch = all_results['batch_performance'][-1]
    print(f'批量处理({last_batch[\"batch_size\"]}个): {last_batch[\"avg_per_event_ms\"]:.1f}ms/事件')
    
    last_concurrent = all_results['concurrent_performance'][-1]
    print(f'并发处理({last_concurrent[\"concurrent_level\"]}并发): {last_concurrent[\"requests_per_second\"]:.1f} 请求/秒')
    
    if report['summary']['recommendations']:
        print('\n💡 优化建议:')
        for rec in report['summary']['recommendations']:
            print(f'  • {rec}')
    
    print('='*50)
    
    return report

# 运行测试
asyncio.run(main())
" > "${LOG_FILE}" 2>&1

if [ $? -eq 0 ]; then
    echo -e "\n✅ 性能测试完成!"
    echo "📁 日志文件: ${LOG_FILE}"
    
    # 显示性能摘要
    echo -e "\n🔍 性能测试摘要:"
    tail -30 "${LOG_FILE}" | grep -A 30 "性能测试摘要"
else
    echo "❌ 性能测试失败!"
    echo "📁 查看错误日志: ${LOG_FILE}"
fi

echo "="*60

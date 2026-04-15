#!/usr/bin/env python3
"""
测试API是否返回神剑股份
"""
import json
import subprocess
import sys

def test_api():
    # 构造curl命令
    cmd = [
        'curl', '-s', '-X', 'POST',
        'http://localhost:8003/api/stock-screener/execute',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({
            "strategy_id": "weak_to_strong",
            "trade_date": "2026-04-07",
            "limit": 20,
            "auto_tune_min_score": True,
            "target_min_count": 30,
            "target_max_count": 120,
            "enable_llm_review": False,
            "llm_top_k": 20,
            "run_stage1": False,
            "run_stage2": True
        })
    ]

    print("执行API请求...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"请求失败: {result.stderr}")
        return

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print(f"原始响应: {result.stdout[:500]}")
        return

    print(f"状态: {data.get('status')}")
    print(f"总结果数: {data.get('total_count')}")

    diagnostics = data.get('diagnostics', {})
    print(f"候选池数量: {diagnostics.get('candidate_pool_count')}")
    print(f"信号数量: {diagnostics.get('signal_count')}")
    print(f"阶段1: {diagnostics.get('stage1')}")
    print(f"阶段2: {diagnostics.get('stage2')}")

    results = data.get('results', [])
    print(f"结果数量: {len(results)}")

    # 查找神剑股份
    shenjian_results = []
    for r in results:
        if '002361' in r.get('stock_id', ''):
            shenjian_results.append(r)

    print(f"\n神剑股份数量: {len(shenjian_results)}")
    if shenjian_results:
        for r in shenjian_results:
            print(f"  stock_id: {r.get('stock_id')}")
            print(f"  composite_score: {r.get('composite_score')}")
            print(f"  signal_level: {r.get('weak_to_strong', {}).get('signal_level')}")
            print(f"  decision: {r.get('weak_to_strong', {}).get('decision')}")
    else:
        print("\n未找到神剑股份，显示所有结果:")
        for i, r in enumerate(results[:10]):
            print(f"  {i}: {r.get('stock_id')} - {r.get('composite_score')} - {r.get('weak_to_strong', {}).get('signal_level')}")

    # 检查diagnostics中的候选池数量
    print(f"\n诊断信息中的候选池数量: {diagnostics.get('candidate_pool_count')}")

if __name__ == "__main__":
    test_api()
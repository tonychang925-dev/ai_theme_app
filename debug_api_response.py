#!/usr/bin/env python3
"""
调试API响应结构
"""
import json
import subprocess
import sys

def test_api(trade_date, run_stage1=False, run_stage2=True):
    cmd = [
        'curl', '-s', '-X', 'POST',
        'http://localhost:8003/api/stock-screener/execute',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({
            "strategy_id": "weak_to_strong",
            "trade_date": trade_date,
            "limit": 20,
            "auto_tune_min_score": True,
            "target_min_count": 30,
            "target_max_count": 120,
            "enable_llm_review": False,
            "llm_top_k": 20,
            "run_stage1": run_stage1,
            "run_stage2": run_stage2
        })
    ]

    print(f"\n=== 测试交易日 {trade_date}, run_stage1={run_stage1}, run_stage2={run_stage2} ===")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"请求失败: {result.stderr}")
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print(f"原始响应: {result.stdout[:500]}")
        return None

    print(f"状态: {data.get('status')}")
    print(f"总结果数: {data.get('total_count')}")

    # 打印完整的diagnostics结构
    diagnostics = data.get('diagnostics', {})
    print(f"diagnostics键: {list(diagnostics.keys())}")

    # 特别关注candidate_pool_count
    print(f"candidate_pool_count: {diagnostics.get('candidate_pool_count')}")
    print(f"signal_count: {diagnostics.get('signal_count')}")
    print(f"display_result_count: {diagnostics.get('display_result_count')}")

    # 打印stage1和stage2
    if 'stage1' in diagnostics:
        print(f"stage1: {diagnostics.get('stage1')}")
    if 'stage2' in diagnostics:
        print(f"stage2: {diagnostics.get('stage2')}")

    # 打印前几个结果的weak_to_strong字段
    results = data.get('results', [])
    print(f"\n结果数量: {len(results)}")
    for i, r in enumerate(results[:3]):
        print(f"结果{i}: stock_id={r.get('stock_id')}, composite_score={r.get('composite_score')}")
        print(f"  weak_to_strong字段: {list(r.get('weak_to_strong', {}).keys())}")
        if 'signal_level' in r.get('weak_to_strong', {}):
            print(f"  signal_level: {r['weak_to_strong']['signal_level']}")

    return data

if __name__ == "__main__":
    # 测试不同场景
    print("=" * 60)
    test_api('2026-04-07', run_stage1=False, run_stage2=True)
    print("\n" + "=" * 60)
    test_api('2026-04-07', run_stage1=True, run_stage2=False)
    print("\n" + "=" * 60)
    test_api('2026-04-08', run_stage1=False, run_stage2=True)
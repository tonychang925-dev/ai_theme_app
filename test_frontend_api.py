#!/usr/bin/env python3
"""
测试前端使用的API参数
"""
import json
import subprocess
import sys

def test_api():
    # 使用前端相同的参数
    data = {
        "strategy_id": "weak_to_strong",
        "trade_date": "2026-04-07",
        "limit": 20,
        "auto_tune_min_score": True,
        "target_min_count": 30,
        "target_max_count": 120,
        "enable_llm_review": True,
        "llm_top_k": 20,
        "run_stage1": True,
        "run_stage2": False
    }

    cmd = [
        'curl', '-s', '-X', 'POST',
        'http://localhost:8003/api/stock-screener/execute',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(data)
    ]

    print(f"=== 测试前端API参数 ===")
    print(f"请求参数: {json.dumps(data, indent=2)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"请求失败: {result.stderr}")
        return None

    print(f"HTTP状态码: 200 (假设)")
    print(f"响应大小: {len(result.stdout)} 字节")

    # 尝试解析JSON
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print(f"原始响应前500字符: {result.stdout[:500]}")
        return None

    print(f"状态: {response.get('status')}")
    print(f"总结果数: {response.get('total_count')}")

    # 检查diagnostics
    diagnostics = response.get('diagnostics', {})
    print(f"diagnostics键: {list(diagnostics.keys())}")

    # 候选池数量
    candidate_pool_count = diagnostics.get('candidate_pool_count')
    print(f"candidate_pool_count: {candidate_pool_count}")

    # stage1信息
    if 'stage1' in diagnostics:
        stage1 = diagnostics['stage1']
        print(f"stage1: {stage1}")
        if isinstance(stage1, dict):
            print(f"stage1.candidate_count: {stage1.get('candidate_count')}")

    # 检查结果
    results = response.get('results', [])
    print(f"结果数量: {len(results)}")

    if len(results) > 0:
        print(f"前3个结果:")
        for i, r in enumerate(results[:3]):
            print(f"  {i}: stock_id={r.get('stock_id')}, composite_score={r.get('composite_score')}")
            if 'weak_to_strong' in r:
                w2s = r['weak_to_strong']
                print(f"    weak_to_strong字段: {list(w2s.keys())}")

    return response

if __name__ == "__main__":
    test_api()
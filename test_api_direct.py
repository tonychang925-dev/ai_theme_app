#!/usr/bin/env python3
"""
直接测试后端API，使用requests库
"""
import requests
import json
import sys

def test_api_direct():
    url = "http://localhost:8003/api/stock-screener/execute"
    headers = {"Content-Type": "application/json"}
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

    print(f"=== 直接测试后端API ===")
    print(f"URL: {url}")
    print(f"数据: {json.dumps(data, indent=2)}")

    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        print(f"状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")

        if response.status_code != 200:
            print(f"错误响应: {response.text[:500]}")
            return None

        response_data = response.json()
        print(f"状态: {response_data.get('status')}")
        print(f"总结果数: {response_data.get('total_count')}")

        # 检查diagnostics
        diagnostics = response_data.get('diagnostics', {})
        print(f"diagnostics键: {list(diagnostics.keys())}")
        print(f"candidate_pool_count: {diagnostics.get('candidate_pool_count')}")

        # stage1信息
        if 'stage1' in diagnostics:
            stage1 = diagnostics['stage1']
            print(f"stage1: {stage1}")
            if isinstance(stage1, dict):
                print(f"stage1.candidate_count: {stage1.get('candidate_count')}")

        # 结果
        results = response_data.get('results', [])
        print(f"结果数量: {len(results)}")

        if len(results) > 0:
            print(f"前3个结果:")
            for i, r in enumerate(results[:3]):
                print(f"  {i}: stock_id={r.get('stock_id')}, composite_score={r.get('composite_score')}")

        return response_data

    except requests.exceptions.Timeout:
        print("请求超时！")
        return None
    except requests.exceptions.ConnectionError:
        print("连接错误！")
        return None
    except Exception as e:
        print(f"请求异常: {e}")
        return None

if __name__ == "__main__":
    test_api_direct()

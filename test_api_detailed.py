#!/usr/bin/env python3
"""
详细分析API返回数据，查找神剑股份
"""
import json
import subprocess
import sys

def test_api(trade_date):
    # 构造curl命令
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
            "run_stage1": False,
            "run_stage2": True
        })
    ]

    print(f"\n=== 测试交易日 {trade_date} ===")
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

    diagnostics = data.get('diagnostics', {})
    print(f"候选池数量: {diagnostics.get('candidate_pool_count')}")
    print(f"信号数量: {diagnostics.get('signal_count')}")
    print(f"显示结果数: {diagnostics.get('display_result_count')}")

    results = data.get('results', [])
    print(f"结果数量: {len(results)}")

    # 查找神剑股份
    shenjian_found = False
    for i, r in enumerate(results):
        stock_id = r.get('stock_id', '')
        if '002361' in stock_id:
            shenjian_found = True
            print(f"\n✅ 找到神剑股份 (第{i}个结果):")
            print(f"  stock_id: {stock_id}")
            print(f"  composite_score: {r.get('composite_score')}")
            print(f"  signal_level: {r.get('weak_to_strong', {}).get('signal_level')}")
            print(f"  decision: {r.get('weak_to_strong', {}).get('decision')}")
            print(f"  candidate_score: {r.get('weak_to_strong', {}).get('candidate_score')}")
            print(f"  完整weak_to_strong字段: {json.dumps(r.get('weak_to_strong', {}), ensure_ascii=False, indent=2)}")

    if not shenjian_found:
        print(f"\n❌ 未找到神剑股份，显示所有结果:")
        for i, r in enumerate(results[:10]):
            print(f"  {i}: {r.get('stock_id')} - {r.get('composite_score')} - {r.get('weak_to_strong', {}).get('signal_level')}")
            if '002361' in r.get('stock_id', ''):
                print(f"    神剑股份在此！")

    return data

if __name__ == "__main__":
    # 测试三个关键日期
    dates = ['2026-04-07', '2026-04-08', '2026-04-09']
    for date in dates:
        test_api(date)
        print("\n" + "="*50 + "\n")
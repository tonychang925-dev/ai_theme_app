#!/usr/bin/env python3
"""
测试弱转强API
"""
import asyncio
import aiohttp
import sys
import json

async def test_api():
    base_url = "http://localhost:5000"

    # 1. 获取策略
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{base_url}/api/screening/strategies") as resp:
                strategies = await resp.json()
                print("策略列表:", json.dumps(strategies, ensure_ascii=False, indent=2))

                # 找到弱转强策略
                w2s_strategy = None
                for s in strategies.get('data', []):
                    if 'weak_to_strong' in s.get('strategy_id', '').lower() or '弱转强' in s.get('strategy_name', ''):
                        w2s_strategy = s
                        break

                if not w2s_strategy:
                    print("未找到弱转强策略")
                    return

                strategy_id = w2s_strategy['strategy_id']
                print(f"使用策略: {w2s_strategy['strategy_name']} (ID: {strategy_id})")

                # 2. 执行选股 (只运行阶段1)
                payload = {
                    "strategy_id": strategy_id,
                    "trade_date": "2026-04-07",
                    "limit": 20,
                    "auto_tune_min_score": True,
                    "target_min_count": 30,
                    "target_max_count": 120,
                    "enable_llm_review": False,
                    "llm_top_k": 20,
                    "run_stage1": True,
                    "run_stage2": False
                }

                print(f"\n执行选股 (阶段1)...")
                async with session.post(
                    f"{base_url}/api/screening/execute",
                    json=payload
                ) as resp:
                    result = await resp.json()
                    print("API响应状态:", result.get('status'))
                    print("总结果数:", result.get('total_count', 0))
                    print("results长度:", len(result.get('results', [])))

                    if result.get('results'):
                        print("\n前3个结果:")
                        for i, r in enumerate(result.get('results')[:3]):
                            print(f"  {i}: stock_id={r.get('stock_id')}, composite_score={r.get('composite_score')}, weak_to_strong={r.get('weak_to_strong', {})}")
                    else:
                        print("results为空")
                        print("完整响应:", json.dumps(result, ensure_ascii=False, indent=2)[:1000])

                # 3. 执行选股 (阶段2)
                payload2 = {
                    "strategy_id": strategy_id,
                    "trade_date": "2026-04-08",  # 注意: 阶段2使用下一交易日
                    "limit": 20,
                    "auto_tune_min_score": True,
                    "target_min_count": 30,
                    "target_max_count": 120,
                    "enable_llm_review": False,
                    "llm_top_k": 20,
                    "run_stage1": False,
                    "run_stage2": True
                }

                print(f"\n执行选股 (阶段2)...")
                async with session.post(
                    f"{base_url}/api/screening/execute",
                    json=payload2
                ) as resp:
                    result2 = await resp.json()
                    print("API响应状态:", result2.get('status'))
                    print("总结果数:", result2.get('total_count', 0))
                    print("results长度:", len(result2.get('results', [])))

                    if result2.get('results'):
                        print("\n前3个结果:")
                        for i, r in enumerate(result2.get('results')[:3]):
                            print(f"  {i}: stock_id={r.get('stock_id')}, composite_score={r.get('composite_score')}, signal_level={r.get('weak_to_strong', {}).get('signal_level')}")
                    else:
                        print("results为空")
                        print("完整响应:", json.dumps(result2, ensure_ascii=False, indent=2)[:1000])

        except aiohttp.ClientConnectorError as e:
            print(f"无法连接到 {base_url}: {e}")
            print("请确保后端服务正在运行")
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api())
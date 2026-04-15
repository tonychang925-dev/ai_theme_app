#!/usr/bin/env python3
"""
测试股票ID格式对支撑位检测的影响
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_stock_id_formats():
    print("🔧 测试股票ID格式对支撑位检测的影响")
    print("=" * 60)

    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)
    pct_chg = -3.11

    test_cases = [
        ("002361", "不带后缀"),
        ("002361.SZ", "带后缀"),
        ("002361.sz", "小写后缀"),
        ("002361.SZ", "大写后缀"),
    ]

    results = {}

    for stock_id, description in test_cases:
        print(f"\n测试: {stock_id} ({description})")
        try:
            result = await builder.analyze_strict_support(stock_id, pct_chg, test_date)
            results[stock_id] = result
            print(f"  has_support: {result['has_support']}")
            print(f"  support_type: {result.get('support_type', '')}")
            print(f"  support_strength: {result.get('support_strength', 0.0) * 100:.1f}/100")
            print(f"  support_count: {result.get('support_count', 0)}")
            print(f"  combined_strength: {result.get('combined_strength', 0.0)}")

            if not result['has_support']:
                print(f"  ⚠️ 无支撑位检测到")
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            import traceback
            traceback.print_exc()

    # 分析结果
    print(f"\n" + "=" * 60)
    print("分析结果:")
    best_result = None
    best_score = 0.0
    for stock_id, result in results.items():
        if result['has_support']:
            score = result.get('support_strength', 0.0) * 100
            if score > best_score:
                best_score = score
                best_result = stock_id
            print(f"  {stock_id}: 支撑强度 {score:.1f}/100")

    if best_result:
        print(f"\n✅ 最佳格式: {best_result} (强度: {best_score:.1f})")
    else:
        print(f"\n❌ 所有格式都未检测到有效支撑")

    # 测试_normalize_stock_id方法
    print(f"\n测试_normalize_stock_id方法:")
    test_inputs = [
        ("002361", "002361"),
        ("002361.SZ", "002361"),
        ("", "002361"),
        ("002361", ""),
    ]
    for raw_id, code in test_inputs:
        normalized = builder._normalize_stock_id(raw_id, code)
        print(f"  _normalize_stock_id('{raw_id}', '{code}') = '{normalized}'")

    await builder.close()
    return best_result is not None

async def main():
    success = await test_stock_id_formats()
    if success:
        print("\n✅ 股票ID格式测试完成")
        return 0
    else:
        print("\n⚠️ 股票ID格式测试失败")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
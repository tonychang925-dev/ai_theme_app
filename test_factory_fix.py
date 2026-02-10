# ai_theme_app/test_factory_fix.py
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.collectors.source_factory import CollectorFactory

async def test_factory():
    """测试修复后的工厂"""
    print("测试采集器工厂...")
    print("=" * 60)
    
    collectors = await CollectorFactory.create_collectors()
    
    print(f"\n结果: 创建了 {len(collectors)} 个采集器")
    for i, collector in enumerate(collectors, 1):
        print(f"  {i}. {collector.source_name} (类型: {type(collector).__name__})")
    
    # 测试每个采集器的健康检查
    print("\n健康检查:")
    for collector in collectors:
        health = await collector.health_check()
        print(f"  {collector.source_name}: {'✅ 健康' if health else '❌ 不健康'}")

if __name__ == "__main__":
    asyncio.run(test_factory())
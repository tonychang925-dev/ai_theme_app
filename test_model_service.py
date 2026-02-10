#!/usr/bin/env python3
"""
测试 model_service
"""
import asyncio
import aiohttp
import json

async def test_model_service():
    """测试model_service API"""
    test_news = [
        {
            "news_id": "test_001",
            "title": "国家发布人工智能发展规划",
            "content": "近日，国家发布人工智能发展规划，计划在未来五年投入千亿资金支持AI产业发展...",
            "source": "akshare_cls",
            "publish_date": "2024-01-05"
        },
        {
            "news_id": "test_002", 
            "title": "新能源汽车销量大幅增长",
            "content": "据统计，今年新能源汽车销量同比增长120%，市场需求持续旺盛...",
            "source": "akshare_cls",
            "publish_date": "2024-01-05"
        }
    ]
    
    url = "http://localhost:8001/api/process-news"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"news_list": test_news},
                timeout=10
            ) as response:
                result = await response.json()
                print("✅ API测试成功:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
    except Exception as e:
        print(f"❌ 测试失败: {e}")

async def test_health():
    """测试健康检查"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8001/health",
                timeout=5
            ) as response:
                result = await response.json()
                print("🩺 健康检查:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")

async def main():
    print("🧪 测试 model_service")
    print("=" * 50)
    
    # 先测试健康检查
    await test_health()
    print()
    
    # 测试处理API
    await test_model_service()

if __name__ == "__main__":
    asyncio.run(main())

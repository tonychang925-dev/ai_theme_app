#!/usr/bin/env python3
"""
测试新闻抓取服务模块是否正常工作
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_news_crawler_service():
    """测试新闻抓取服务"""
    print("🤖 测试新闻抓取服务模块...")

    try:
        # 1. 导入服务
        from news_crawler_service.services.news_crawler_service import get_news_crawler_service

        # 2. 获取服务实例
        service = get_news_crawler_service()
        print(f"✅ 服务初始化状态: {service.initialized}")

        # 3. 检查服务状态
        print("\n📊 检查服务状态...")
        status = await service.get_service_status()
        print(f"   服务状态: {status.get('status')}")
        print(f"   真实采集器: {status['components']['real_collector']['available']} (健康: {status['components']['real_collector']['healthy']})")
        print(f"   模拟生成器: {status['components']['mock_generator']['available']} (健康: {status['components']['mock_generator']['healthy']})")

        # 4. 根据可用性测试不同模式
        if status['components']['real_collector']['available'] and status['components']['real_collector']['healthy']:
            print("\n📡 测试真实新闻抓取...")
            result = await service.crawl_real_news(limit=2)
            mode = "real"
        else:
            print("\n📡 真实采集器不可用，测试模拟新闻...")
            result = await service.crawl_mock_news(count=2)
            mode = "mock"

        print(f"   操作: {result.get('operation')}")
        print(f"   状态: {result.get('status')}")

        if result.get('status') == 'success':
            news_count = result.get('response', {}).get('news_count', 0)
            print(f"   新闻数量: {news_count}")

            if news_count > 0:
                news_list = result.get('response', {}).get('news_list', [])
                for i, news in enumerate(news_list[:2]):  # 显示前2条
                    print(f"\n   新闻 {i+1}:")
                    print(f"     标题: {news.get('title', '无标题')}")
                    print(f"     来源: {news.get('source', '未知')}")
                    print(f"     日期: {news.get('publish_date', '未知')}")
                    print(f"     市场: {news.get('market', '未知')}")
        else:
            print(f"   错误: {result.get('error')}")

        # 5. 测试智能抓取
        print("\n🤖 测试智能抓取...")
        auto_result = await service.crawl_news_auto(count=2, prefer_real=True)
        print(f"   模式: {auto_result.get('mode', 'unknown')}")
        print(f"   数量: {auto_result.get('response', {}).get('news_count', 0)}")

        print("\n✅ 测试完成")
        return True

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(test_news_crawler_service())
    sys.exit(0 if success else 1)
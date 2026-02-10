#!/usr/bin/env python3
"""
修复版运行脚本 - 直接运行事件提取
"""
import asyncio
import os
import sys
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def main():
    """主函数"""
    print("🚀 修复版事件提取器")
    print("=" * 60)
    
    try:
        # 导入模块
        from llm_parser.factory import LLMParserFactory
        from services.event_extractor import AIEventExtractor, MockEventExtractor
        import database
        
        print("✅ 模块导入成功")
        
        # 检查模式
        use_mock = os.getenv('USE_MOCK', '0') == '1'
        has_deepseek = bool(os.getenv('DEEPSEEK_API_KEY'))
        
        if use_mock:
            print("🎭 使用模拟模式")
            extractor = MockEventExtractor()
        elif has_deepseek:
            print("🤖 使用DeepSeek AI")
            extractor = AIEventExtractor()
        else:
            print("⚠️  未检测到API密钥，使用模拟模式")
            extractor = MockEventExtractor()
        
        # 获取待处理新闻
        print("📋 获取待处理新闻...")
        news_list = await database.DatabaseManager.fetch_pending_news(limit=1)
        
        if not news_list:
            print("📭 没有待处理的新闻")
            return
        
        print(f"✅ 找到 {len(news_list)} 条新闻")
        
        # 处理每条新闻
        for i, news_item in enumerate(news_list, 1):
            print(f"\n{'='*50}")
            print(f"[{i}/{len(news_list)}] 处理: {news_item['news_id'][:20]}...")
            print(f"标题: {news_item['title'][:50]}...")
            
            try:
                # 提取事件
                event_data = await extractor.extract_event(news_item)
                
                if event_data:
                    print("✅ 事件提取成功!")
                    print(f"   类型: {event_data.get('event_type')}")
                    print(f"   方向: {event_data.get('direction')}")
                    print(f"   置信度: {event_data.get('confidence')}")
                    print(f"   摘要: {event_data.get('summary')[:80]}...")
                    
                    # 保存到数据库
                    success = await database.DatabaseManager.save_event(event_data)
                    if success:
                        print("💾 已保存到数据库")
                        
                        # 标记为已处理
                        await database.DatabaseManager.mark_news_as_processed(news_item['news_id'])
                        print("✅ 新闻标记为已处理")
                    else:
                        print("❌ 保存失败")
                else:
                    print("❌ 事件提取失败")
                    
            except Exception as e:
                print(f"💥 处理失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 关闭提取器
        await extractor.close()
        
        print("\n" + "=" * 60)
        print("🎉 处理完成!")
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("💡 建议: 检查模块路径")
    except Exception as e:
        print(f"💥 运行失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

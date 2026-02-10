"""
直接测试DeepSeek API是否工作
"""
import asyncio
import os
import aiohttp
import json
import sys

async def test_deepseek_api():
    """直接测试DeepSeek API"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    
    if not api_key:
        print("❌ DEEPSEEK_API_KEY 未设置")
        print("请运行: export DEEPSEEK_API_KEY='your-api-key'")
        return False
    
    print(f"🔑 API密钥: {api_key[:10]}...")
    print("🚀 开始测试DeepSeek API...")
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 非常简单的测试消息
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个测试助手，请回复'API测试成功'"},
            {"role": "user", "content": "请回复测试成功"}
        ],
        "max_tokens": 100,
        "temperature": 0.1
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print("📡 发送API请求...")
            
            async with session.post(url, headers=headers, json=payload) as response:
                print(f"📊 HTTP状态码: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    content = result['choices'][0]['message']['content']
                    print(f"✅ API测试成功!")
                    print(f"🤖 AI回复: {content}")
                    
                    # 显示token使用情况
                    if 'usage' in result:
                        usage = result['usage']
                        print(f"📈 Token使用: 输入{usage.get('prompt_tokens', 0)}, 输出{usage.get('completion_tokens', 0)}, 总计{usage.get('total_tokens', 0)}")
                    
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ API请求失败: {response.status}")
                    print(f"错误信息: {error_text}")
                    return False
    
    except asyncio.TimeoutError:
        print("⏰ API请求超时（30秒）")
        return False
    except Exception as e:
        print(f"❌ API测试异常: {e}")
        return False

async def test_event_extractor():
    """测试event_extractor"""
    print("\n" + "="*50)
    print("测试 event_extractor")
    print("="*50)
    
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd()))
    
    try:
        from model_service.service.event_extractor import AIEventExtractor
        
        # 创建测试新闻
        test_news = {
            'news_id': 'test_001',
            'title': '特斯拉发布新款电动车，续航突破1000公里',
            'content': '特斯拉今日发布新款Model S Plaid+，官方宣称续航里程达到1020公里，成为全球首款续航突破1000公里的量产电动车。新车搭载全新的电池技术和高效电机，预计明年开始交付。'
        }
        
        print(f"📰 测试新闻: {test_news['title']}")
        
        extractor = AIEventExtractor()
        print("✅ 创建event_extractor成功")
        
        # 提取事件
        print("🧠 调用AI提取事件...")
        event_data = await extractor.extract_event(test_news)
        
        if event_data:
            print("✅ 成功提取事件!")
            print(f"  事件类型: {event_data.get('event_type')}")
            print(f"  摘要: {event_data.get('summary', '')[:100]}...")
            print(f"  主题指令: {event_data.get('theme_directive', {}).get('action', 'N/A')}")
            
            # 检查是否保存了原始内容
            if 'original_data' in event_data and event_data['original_data'].get('content'):
                print(f"  原始内容保存: ✅ ({len(event_data['original_data']['content'])} 字符)")
            else:
                print("  原始内容保存: ❌")
            
            return True
        else:
            print("❌ 提取器返回None")
            return False
            
    except Exception as e:
        print(f"❌ event_extractor测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("="*60)
    print("🤖 DeepSeek API 和 Event Extractor 测试")
    print("="*60)
    
    # 测试1: 直接API测试
    api_success = await test_deepseek_api()
    
    if api_success:
        # 测试2: event_extractor测试
        extractor_success = await test_event_extractor()
        
        if extractor_success:
            print("\n" + "="*60)
            print("🎉 所有测试通过!")
            print("DeepSeek API 和 Event Extractor 工作正常")
            print("="*60)
            return 0
        else:
            print("\n" + "="*60)
            print("⚠️  API工作正常，但event_extractor有问题")
            print("="*60)
            return 1
    else:
        print("\n" + "="*60)
        print("❌ API测试失败，检查API密钥和网络连接")
        print("="*60)
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

#!/usr/bin/env python3
"""
简化测试脚本 - 绕过复杂逻辑
"""
import asyncio
import os
import sys
import aiohttp
import json

async def test_simple_api():
    """最简单的API测试"""
    print("🧪 简化API测试")
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 请设置 DEEPSEEK_API_KEY")
        return
    
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{
            "role": "user",
            "content": "请说'测试成功'"
        }],
        "max_tokens": 10,
        "temperature": 0.1
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                print(f"📡 状态码: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print("✅ API测试成功!")
                    print(f"响应: {result['choices'][0]['message']['content']}")
                    return True
                else:
                    error = await response.text()
                    print(f"❌ 失败: {response.status}")
                    print(f"错误: {error[:200]}")
                    return False
    except Exception as e:
        print(f"💥 异常: {type(e).__name__}: {e}")
        return False

async def test_news_extraction():
    """测试新闻提取"""
    print("\n📰 测试新闻提取")
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return False
    
    # 测试新闻
    news_title = "山东预计2025年GDP超10万亿元"
    news_content = "山东省政府工作报告提出，2025年全省GDP目标突破10万亿元。"
    
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""分析财经新闻并提取事件信息。

标题：{news_title}
内容：{news_content}

以JSON格式返回：{{
  "event_type": "政策利好/技术突破/业绩增长等",
  "impact_industries": ["行业列表"],
  "direction": "positive/negative/neutral",
  "confidence": 0-100,
  "summary": "摘要"
}}"""
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    
    timeout = aiohttp.ClientTimeout(total=60)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result["choices"][0]["message"]["content"]
                    
                    try:
                        parsed = json.loads(content)
                        print("✅ 新闻提取成功!")
                        for key, value in parsed.items():
                            print(f"  {key}: {value}")
                        return True
                    except:
                        print(f"📋 原始响应: {content[:200]}")
                        return True
                else:
                    print(f"❌ 提取失败: {response.status}")
                    return False
    except Exception as e:
        print(f"💥 异常: {e}")
        return False

async def main():
    """主函数"""
    print("=" * 60)
    print("🎯 终极修复测试")
    print("=" * 60)
    
    # 测试1: API连接
    api_ok = await test_simple_api()
    
    if api_ok:
        # 测试2: 新闻提取
        await test_news_extraction()
    else:
        print("\n💡 建议:")
        print("1. 检查API密钥是否正确")
        print("2. 检查网络连接")
        print("3. 检查API服务状态: https://status.deepseek.com/")
        print("4. 使用模拟模式: export USE_MOCK=1")
    
    print("\n" + "=" * 60)
    print("测试完成!")

if __name__ == "__main__":
    asyncio.run(main())

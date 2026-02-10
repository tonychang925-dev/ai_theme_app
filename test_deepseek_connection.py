# test_deepseek_connection_fixed.py
"""
专门测试DeepSeek API连接 - 修复版
"""
import asyncio
import os
import aiohttp
import json

def clean_ai_response(response: str) -> str:
    """清理AI响应"""
    if not response:
        return ""
    
    response = response.strip()
    
    # 移除代码块标记
    if response.startswith('```json'):
        response = response[7:]
    elif response.startswith('```'):
        response = response[3:]
    
    if response.endswith('```'):
        response = response[:-3]
    
    # 查找JSON部分
    start = response.find('{')
    end = response.rfind('}')
    
    if start != -1 and end != -1 and end > start:
        response = response[start:end+1]
    
    return response.strip()

async def test_deepseek_api_directly():
    """直接测试DeepSeek API连接"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    
    if not api_key:
        print("❌ DEEPSEEK_API_KEY环境变量未设置")
        print("请设置: export DEEPSEEK_API_KEY='your-api-key'")
        return False
    
    print(f"🔑 API密钥: {api_key[:10]}...{api_key[-4:]}")
    
    api_url = "https://api.deepseek.com/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 简单的测试payload
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": "请回复'测试成功'"}
        ],
        "max_tokens": 10,
        "temperature": 0.1,
        "stream": False
    }
    
    print("📤 发送测试请求到DeepSeek API...")
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                api_url,
                headers=headers,
                json=payload
            ) as response:
                
                print(f"📥 收到响应，状态码: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ API连接测试成功!")
                    
                    if 'choices' in result:
                        reply = result['choices'][0]['message']['content']
                        print(f"   AI回复: {reply}")
                    
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ API错误 {response.status}: {error_text}")
                    return False
                    
    except asyncio.TimeoutError:
        print("❌ 请求超时")
        return False
    except aiohttp.ClientError as e:
        print(f"❌ 网络错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        return False

async def test_with_simple_json():
    """测试带有JSON格式要求的API调用"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    
    if not api_key:
        return False
    
    api_url = "https://api.deepseek.com/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 🔥 改进的Prompt，添加system message
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一个JSON API，必须返回严格符合JSON格式的响应，不要包含任何其他文字。"
            },
            {
                "role": "user", 
                "content": "请输出一个简单的JSON对象，包含字段test和value。格式必须是有效的JSON。"
            }
        ],
        "max_tokens": 50,
        "temperature": 0.0,  # 设置为0，确保确定性输出
        "stream": False
    }
    
    print("\n🧪 测试JSON格式响应...")
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                api_url,
                headers=headers,
                json=payload
            ) as response:
                
                print(f"状态码: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    reply = result['choices'][0]['message']['content']
                    print(f"AI原始回复: {reply}")
                    
                    # 清理响应
                    cleaned = clean_ai_response(reply)
                    print(f"清理后: {cleaned}")
                    
                    # 尝试解析JSON
                    try:
                        parsed = json.loads(cleaned)
                        print(f"✅ JSON解析成功: {parsed}")
                        return True
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON解析失败: {e}")
                        # 尝试直接提取
                        try:
                            start = reply.find('{')
                            end = reply.rfind('}')
                            if start != -1 and end != -1:
                                json_str = reply[start:end+1]
                                parsed = json.loads(json_str)
                                print(f"✅ 提取后JSON解析成功: {parsed}")
                                return True
                        except Exception as ex:
                            print(f"❌ 提取也失败: {ex}")
                        return False
                else:
                    error_text = await response.text()
                    print(f"❌ API错误: {error_text[:200]}")
                    return False
                    
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("=" * 60)
    print("DeepSeek API连接测试 - 修复版")
    print("=" * 60)
    
    # 测试1: 简单连接测试
    print("\n1. 简单连接测试:")
    success1 = await test_deepseek_api_directly()
    
    if success1:
        # 测试2: JSON格式测试
        print("\n2. JSON格式响应测试:")
        success2 = await test_with_simple_json()
    else:
        success2 = False
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结:")
    print(f"  简单连接: {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"  JSON格式: {'✅ 通过' if success2 else '❌ 失败'}")
    
    if success1 and success2:
        print("\n🎉 所有测试通过！API连接正常。")
    else:
        print("\n⚠️  部分测试失败，请检查API密钥和网络连接。")
    
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
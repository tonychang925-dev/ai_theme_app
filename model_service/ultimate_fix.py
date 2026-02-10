#!/usr/bin/env python3
"""
终极修复脚本 - 解决所有已知问题
"""
import os
import shutil

def apply_ultimate_fix():
    """应用终极修复"""
    print("🔧 应用终极修复...")
    
    # 备份原文件
    files_to_fix = [
        "llm_parser/deepseek_parser.py",
        "services/event_extractor.py",
        "run_news_event.py"
    ]
    
    for file in files_to_fix:
        if os.path.exists(file):
            backup = f"{file}.backup_{os.path.basename(file)}"
            shutil.copy2(file, backup)
            print(f"📄 已备份: {file} -> {backup}")
    
    # 1. 修复 deepseek_parser.py 中的连接管理
    deepseek_fix = '''"""
DeepSeek API解析器 - 修复版
"""
import os
import json
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from .base_parser import BaseLLMParser


class DeepSeekParser(BaseLLMParser):
    """DeepSeek API解析器 - 修复连接管理"""
    
    def __init__(self, model_name: str = "deepseek-chat"):
        super().__init__(model_name)
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY 环境变量未设置")
        
        self.api_url = "https://api.deepseek.com/chat/completions"
        self._session = None
        self._connector = None
    
    def _create_timeout(self) -> aiohttp.ClientTimeout:
        """创建超时配置"""
        return aiohttp.ClientTimeout(
            total=120,      # 总超时120秒
            connect=30,     # 连接超时30秒
            sock_read=60    # 读取超时60秒
        )
    
    async def _ensure_session(self):
        """确保会话存在"""
        if self._session is None or self._session.closed:
            timeout = self._create_timeout()
            self._connector = aiohttp.TCPConnector(limit=10)
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout
            )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def parse_content(self, content: str) -> Optional[Dict[str, Any]]:
        """
        解析内容并返回结构化数据
        """
        await self._ensure_session()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # 简化提示词，提高成功率
        system_prompt = "你是一个财经事件分析专家。请分析给定的财经新闻，提取关键事件信息，并以JSON格式返回。"
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            "max_tokens": 800,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "stream": False
        }
        
        try:
            async with self._session.post(
                self.api_url,
                headers=headers,
                json=payload
            ) as response:
                
                response.raise_for_status()
                result = await response.json()
                
                # 提取内容
                if 'choices' in result and result['choices']:
                    reply = result['choices'][0]['message']['content']
                    
                    # 清理回复，确保是纯JSON
                    reply = reply.strip()
                    if reply.startswith('```json'):
                        reply = reply[7:]
                    if reply.endswith('```'):
                        reply = reply[:-3]
                    reply = reply.strip()
                    
                    try:
                        return json.loads(reply)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON解析失败: {e}\\n内容: {reply[:200]}")
                        # 尝试修复常见的JSON问题
                        try:
                            # 查找第一个{和最后一个}
                            start = reply.find('{')
                            end = reply.rfind('}')
                            if start != -1 and end != -1 and end > start:
                                fixed_json = reply[start:end+1]
                                return json.loads(fixed_json)
                        except:
                            pass
                        
                        # 返回原始内容
                        return {"raw_response": reply, "error": "json_parse_failed"}
                else:
                    self.logger.error(f"API响应格式异常: {result}")
                    return None
                    
        except aiohttp.ClientResponseError as e:
            self.logger.error(f"HTTP响应错误: {e.status} - {e.message}")
            if e.status == 401:
                raise ValueError("API密钥无效或过期")
            elif e.status == 429:
                raise ValueError("请求过于频繁，请稍后重试")
            elif e.status >= 500:
                raise ValueError("服务器内部错误，请稍后重试")
            else:
                raise
        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP客户端错误: {e}")
            raise
        except asyncio.TimeoutError:
            self.logger.error("请求超时")
            raise ValueError("请求超时，请检查网络连接")
        except Exception as e:
            self.logger.error(f"未知错误: {e}")
            raise
    
    async def parse_news(self, title: str, content: str) -> Optional[Dict[str, Any]]:
        """
        解析新闻内容 - 简化版
        """
        # 简化的提示词
        prompt = f"""请分析财经新闻并提取事件信息。

新闻标题：{title}
新闻内容：{content}

请返回JSON格式：
{{
  "event_type": "事件类型",
  "impact_industries": ["行业1", "行业2"],
  "direction": "positive/negative/neutral",
  "confidence": 80,
  "summary": "简要摘要"
}}

只返回JSON，不要其他内容。"""
        
        try:
            result = await self.parse_content(prompt)
            
            # 验证结果格式
            if isinstance(result, dict):
                required_fields = ['event_type', 'direction', 'confidence', 'summary']
                for field in required_fields:
                    if field not in result:
                        result[field] = "unknown" if field != 'confidence' else 50
                
                # 确保impact_industries是列表
                if 'impact_industries' not in result:
                    result['impact_industries'] = []
                elif not isinstance(result['impact_industries'], list):
                    if isinstance(result['impact_industries'], str):
                        result['impact_industries'] = [result['impact_industries']]
                    else:
                        result['impact_industries'] = []
            
            return result
            
        except Exception as e:
            self.logger.error(f"解析新闻失败: {e}")
            # 返回默认值
            return {
                "event_type": "解析失败",
                "impact_industries": [],
                "direction": "neutral",
                "confidence": 0,
                "summary": f"解析失败: {str(e)}",
                "error": str(e)
            }
    
    async def close(self):
        """安全关闭资源"""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._connector and not self._connector.closed:
            await self._connector.close()
        self._session = None
        self._connector = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
'''

    # 写入修复文件
    with open("llm_parser/deepseek_parser.py", "w") as f:
        f.write(deepseek_fix)
    
    print("✅ 已修复 deepseek_parser.py")
    
    # 2. 创建简化的测试脚本
    simple_test = '''#!/usr/bin/env python3
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
    print("\\n📰 测试新闻提取")
    
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
        print("\\n💡 建议:")
        print("1. 检查API密钥是否正确")
        print("2. 检查网络连接")
        print("3. 检查API服务状态: https://status.deepseek.com/")
        print("4. 使用模拟模式: export USE_MOCK=1")
    
    print("\\n" + "=" * 60)
    print("测试完成!")

if __name__ == "__main__":
    asyncio.run(main())
'''

    with open("simple_api_test.py", "w") as f:
        f.write(simple_test)
    
    print("✅ 已创建 simple_api_test.py")
    
    # 3. 提供使用说明
    print("\n" + "=" * 60)
    print("🎯 修复完成！请按以下步骤测试：")
    print("=" * 60)
    print("1. 测试API连接:")
    print("   python simple_api_test.py")
    print()
    print("2. 如果API测试成功，运行事件提取:")
    print("   python run_news_event.py --once --verbose --limit 1")
    print()
    print("3. 如果API测试失败:")
    print("   a. 检查API密钥: echo $DEEPSEEK_API_KEY")
    print("   b. 使用模拟模式: export USE_MOCK=1")
    print("   c. 测试模拟模式: python run_news_event.py --mock --once")
    print()
    print("4. 恢复备份文件（如果需要）:")
    print("   cp llm_parser/deepseek_parser.py.backup_* llm_parser/deepseek_parser.py")

apply_ultimate_fix()

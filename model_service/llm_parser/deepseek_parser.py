# model_service/llm_parser/deepseek_parser.py
"""
DeepSeek API解析器 - 纯真实版
🔥 已完全移除模拟测试代码，强制使用真实API
"""
import os
import json
import aiohttp
import asyncio
import sys
from typing import Dict, Any, Optional

# === 导入BaseLLMParser ===
_current_file = os.path.abspath(__file__)
_current_dir = os.path.dirname(_current_file)
_parent_dir = os.path.dirname(_current_dir)  # llm_parser的父目录

# 确保父目录在Python路径中
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# 导入BaseLLMParser
try:
    from llm_parser.base_parser import BaseLLMParser
except ImportError:
    # 如果导入失败，创建虚拟基类
    class BaseLLMParser:
        def __init__(self, model_name: str = ""):
            self.model_name = model_name
            import logging
            self.logger = logging.getLogger(self.__class__.__name__)

# 导入tenacity
try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except ImportError:
    # 简化的retry装饰器
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    def stop_after_attempt(n):
        return None
    
    def wait_exponential(**kwargs):
        return None


class DeepSeekParser(BaseLLMParser):
    """DeepSeek API解析器 - 🔥 只使用真实API，无模拟"""
    
    def __init__(self, model_name: str = "deepseek-chat"):
        super().__init__(model_name)
        
        # 🔥 强制要求真实API密钥
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "❌ DEEPSEEK_API_KEY 环境变量未设置\n"
                "请在运行前设置: export DEEPSEEK_API_KEY='your-api-key'"
            )
        
        # 🔥 检查是否为测试密钥
        if self.api_key.startswith("sk-test"):
            raise ValueError(
                "❌ 检测到测试API密钥\n"
                "必须使用真实的DeepSeek API密钥进行测试"
            )
        
        self.api_url = "https://api.deepseek.com/chat/completions"
        self._session = None
        self._connector = None
        
        import logging
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"DeepSeekParser初始化完成，使用模型: {model_name}")
    
    def _create_timeout(self) -> aiohttp.ClientTimeout:
        """创建超时配置"""
        return aiohttp.ClientTimeout(
            total=120,
            connect=30,
            sock_read=60
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
        🔥 只使用真实API，无模拟
        """
        await self._ensure_session()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": content}
            ],
            "max_tokens": 1200,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "stream": False
        }
        
        self.logger.info(f"📤 发送请求到DeepSeek API，内容长度: {len(content)}")
        
        try:
            async with self._session.post(
                self.api_url,
                headers=headers,
                json=payload
            ) as response:
                
                response.raise_for_status()
                result = await response.json()
                
                self.logger.info(f"📥 收到API响应，token使用: {result.get('usage', {})}")
                
                if 'choices' in result and result['choices']:
                    reply = result['choices'][0]['message']['content']
                    
                    # 清理回复
                    reply = reply.strip()
                    if reply.startswith('```json'):
                        reply = reply[7:]
                    if reply.endswith('```'):
                        reply = reply[:-3]
                    reply = reply.strip()
                    
                    try:
                        parsed_data = json.loads(reply)
                        
                        if not isinstance(parsed_data, dict):
                            self.logger.error(f"❌ 返回的不是字典类型: {type(parsed_data)}")
                            return None
                        
                        return parsed_data
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ JSON解析失败: {e}")
                        self.logger.debug(f"原始响应: {reply[:200]}...")
                        
                        # 尝试修复JSON
                        try:
                            start = reply.find('{')
                            end = reply.rfind('}')
                            if start != -1 and end != -1 and end > start:
                                fixed_json = reply[start:end+1]
                                parsed_data = json.loads(fixed_json)
                                self.logger.info("✅ 成功修复JSON")
                                return parsed_data
                        except Exception as fix_error:
                            self.logger.error(f"❌ JSON修复失败: {fix_error}")
                        
                        return None
                else:
                    self.logger.error(f"❌ API响应格式异常: {result}")
                    return None
                    
        except aiohttp.ClientError as e:
            self.logger.error(f"❌ 网络请求失败: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ API请求异常: {e}")
            raise
    
    async def parse_news(self, title: str, content: str) -> Optional[Dict[str, Any]]:
        """
        解析新闻内容 - 优化版提示词
        生成包含完整ai_analysis字段的分析结果
        """
        prompt = f"""作为金融信息分析师，请深入分析以下新闻并生成完整的AI分析结果：

        标题：{title}
        内容：{content[:1500]}

        请严格按照以下JSON格式返回分析结果：

        {{
            "ai_analysis": {{
                "core_concept": "核心概念，15字以内",
                "industry_keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
                "summary": "100-150字的新闻摘要，包含主要事实和影响",
                "sentiment": "positive/negative/neutral",
                "concept_confidence": 0.85,
                "impact_level": "high/medium/low"
            }},
            "event_info": {{
                "event_type": "技术突破/政策发布/市场动态/企业事件",
                "impact_industries": ["行业1", "行业2"],
                "direction": "利好/利空/中性"
            }},
            "theme_discovery_directive": {{
                "action": "MAJOR/NORMAL/IGNORE",
                "decision_confidence": 0.85,
                "reason": "简要决策理由"
            }}
        }}

        要求：
        1. industry_keywords: 必须是字符串数组，最少3个，最多8个
        2. summary: 100-150字，客观简洁
        3. sentiment: 只能从positive/negative/neutral中选择
        4. concept_confidence: 0.7-1.0之间的浮点数，保留2位小数
        5. impact_level: 只能从high/medium/low中选择
        6. 确保JSON格式完全正确，没有额外文字"""

        try:
            result = await self.parse_content(prompt)
            
            if result and isinstance(result, dict):
                # 验证关键字段
                if "ai_analysis" in result:
                    ai_analysis = result["ai_analysis"]
                    required_fields = ["core_concept", "industry_keywords", "summary", 
                                     "sentiment", "concept_confidence", "impact_level"]
                    
                    # 检查必要字段
                    missing_fields = [f for f in required_fields if f not in ai_analysis]
                    if missing_fields:
                        self.logger.warning(f"⚠️ AI分析缺少字段: {missing_fields}")
                        # 补充缺失字段
                        for field in missing_fields:
                            if field == "core_concept":
                                ai_analysis[field] = title[:20]
                            elif field == "industry_keywords":
                                ai_analysis[field] = ["科技", "产业", "市场"]
                            elif field == "summary":
                                ai_analysis[field] = f"关于{title}的相关报道"
                            elif field == "sentiment":
                                ai_analysis[field] = "neutral"
                            elif field == "concept_confidence":
                                ai_analysis[field] = 0.8
                            elif field == "impact_level":
                                ai_analysis[field] = "medium"
                    
                    self.logger.info(f"✅ 成功解析新闻，核心概念: {ai_analysis.get('core_concept')}")
                    return result
                else:
                    self.logger.error("❌ API响应缺少ai_analysis字段")
                    return None
            else:
                self.logger.error("❌ API返回结果为空或格式错误")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ 解析新闻失败: {e}")
            raise
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self._ensure_session()
            
            # 发送一个简单的测试请求
            test_payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            }
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            async with self._session.post(
                self.api_url,
                headers=headers,
                json=test_payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                return response.status == 200
                
        except Exception as e:
            self.logger.error(f"❌ 健康检查失败: {e}")
            return False
    
    async def close(self):
        """安全关闭资源"""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._connector and not self._connector.closed:
            await self._connector.close()


# === 测试代码（仅用于模块验证）===
if __name__ == "__main__":
    async def test_real_api():
        """测试真实API连接"""
        print("🧪 测试DeepSeekParser真实API连接")
        
        # 检查API密钥
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("❌ DEEPSEEK_API_KEY未设置")
            return False
        
        if api_key.startswith("sk-test"):
            print("❌ 请使用真实的DeepSeek API密钥")
            return False
        
        try:
            parser = DeepSeekParser()
            print("✅ 成功创建DeepSeekParser实例")
            
            # 测试健康检查
            health = await parser.health_check()
            print(f"✅ 健康检查: {'通过' if health else '失败'}")
            
            if health:
                print("\n📡 真实API连接测试成功！")
            else:
                print("\n❌ API连接测试失败，请检查密钥和网络")
            
            await parser.close()
            return health
            
        except ValueError as e:
            print(f"❌ 初始化失败: {e}")
            return False
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    asyncio.run(test_real_api())
"""
DeepSeek API 解析器实现
"""
import json
import aiohttp
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import LLMParser, ParsedEvent, LLMProvider

class DeepSeekParser(LLMParser):
    """DeepSeek API 解析器实现"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com", 
                 model: str = "deepseek-chat"):
        super().__init__(LLMProvider.DEEPSEEK)
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self):
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    def _build_messages(self, title: str, content: str):
        """构建DeepSeek专用的Prompt消息"""
        system_prompt = """你是一个金融新闻分析专家。请从新闻中提取结构化事件。请严格按照以下JSON格式输出：
{
  "event_type": "政策|技术|财报|产业|资本|其他",
  "impact_industries": ["行业1", "行业2"],
  "direction": "利好|利空|中性",
  "summary": "一句话摘要",
  "confidence": 0.95
}"""
        user_prompt = f"标题：{title}\n内容：{content[:2000]}"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def parse_news(self, title: str, content: str) -> Optional[ParsedEvent]:
        """实现基类方法：调用DeepSeek API解析新闻"""
        if not title or not content:
            return None
            
        session = await self._get_session()
        messages = self._build_messages(title, content)
        
        try:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"}
                }
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                llm_output = json.loads(data['choices'][0]['message']['content'])
                
                return ParsedEvent(
                    event_type=llm_output.get('event_type', '其他'),
                    impact_industries=llm_output.get('impact_industries', []),
                    direction=llm_output.get('direction', '中性'),
                    summary=llm_output.get('summary', ''),
                    confidence=llm_output.get('confidence', 0.5),
                    raw_response=llm_output
                )
        except (json.JSONDecodeError, KeyError, aiohttp.ClientError) as e:
            logger.error(f"DeepSeek解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"DeepSeek未知错误: {e}")
            return None
    
    async def health_check(self) -> bool:
        """发送一个简单请求检查API是否可达"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as resp:
                return resp.status == 200
        except:
            return False
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

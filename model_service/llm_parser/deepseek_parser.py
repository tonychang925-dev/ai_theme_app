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
from typing import Dict, Any, Optional, List

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
            total=180,
            connect=45,
            sock_read=90
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

    async def _reset_session(self):
        """在网络中断后强制重建 session。"""
        try:
            if self._session and not self._session.closed:
                await self._session.close()
        finally:
            self._session = None

        try:
            if self._connector and not self._connector.closed:
                await self._connector.close()
        finally:
            self._connector = None
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=20),
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
                    
        except (aiohttp.ClientError, aiohttp.ClientPayloadError, asyncio.TimeoutError) as e:
            await self._reset_session()
            self.logger.error(f"❌ 网络请求失败: {e}")
            raise
        except Exception as e:
            await self._reset_session()
            self.logger.error(f"❌ API请求异常: {e}")
            raise
    
    def _safe_str(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    def _clip_text(self, text: str, limit: int) -> str:
        text = self._safe_str(text)
        if len(text) <= limit:
            return text
        return text[:limit].rstrip()

    def build_event_structuring_prompt(self, title: str, content: str) -> str:
        return f"""你是一个新闻事件结构化抽取器。
你的任务是把单条新闻文本抽取为结构化 JSON，用于后续 news_event 落库和题材匹配。

必须遵守以下要求：
1. 只基于输入文本抽取，不得编造事实。
2. 输出必须是合法 JSON 对象。
3. 不要输出任何题材动作建议，不要输出旧架构中的事件分流字段或题材创建动作字段。
4. event_type 尽量归一为简洁类型，如：政策、制裁、技术突破、会议论坛、行业观点、融资IPO、并购重组、产品发布、订单合作、市场预测、组织设立、产能扩张、事故冲突、其他。
5. entities 只保留对题材匹配有用的实体，格式：
   {{"name":"原文实体","type":"国家|公司|组织|产品|技术|人物|地点|行业","normalized":"归一化名称"}}
6. summary 必须是简洁事件摘要，不超过60字。
7. causal_claim 必须是短语数组，表达“事件 -> 影响链路 -> 潜在题材方向”，不得写长句。
8. evidence_set 必须包含：
   - tech_phrases
   - normalized_terms
   - evidence_spans
   - core_concepts
9. severity_score 范围 0~1。
10. confidence 范围 0~1。
11. source_weight 范围建议 0.5~1.5。
12. timestamp 若可提取则输出 ISO8601 字符串，否则输出 null。
13. 不要输出 markdown，不要输出解释。

输出 JSON 格式：
{{
  "event_type": "技术突破",
  "entities": [
    {{"name":"美国","type":"国家","normalized":"美国"}}
  ],
  "summary": "事件摘要",
  "causal_claim": ["短语1", "短语2"],
  "evidence_set": {{
    "tech_phrases": ["短语1"],
    "normalized_terms": {{"美国": "美国"}},
    "evidence_spans": [{{"text":"关键证据","start":0,"end":4}}],
    "core_concepts": ["核心概念"]
  }},
  "severity_score": 0.8,
  "confidence": 0.9,
  "source_weight": 1.0,
  "timestamp": "2026-02-28T10:00:05Z",
  "impact_industries": ["行业1"],
  "direction": "利好"
}}

新闻标题：{title}
新闻内容：{content[:2000]}
"""

    def _normalize_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [self._safe_str(v) for v in value if self._safe_str(v)]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if "," in text:
                return [self._safe_str(v) for v in text.split(",") if self._safe_str(v)]
            return [text]
        return []

    def _normalize_entities(self, value: Any) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        if not isinstance(value, list):
            return out
        for item in value:
            if isinstance(item, dict):
                name = self._safe_str(item.get("name"))
                if not name:
                    continue
                out.append({
                    "name": name,
                    "type": self._safe_str(item.get("type")),
                    "normalized": self._safe_str(item.get("normalized") or name),
                })
            else:
                name = self._safe_str(item)
                if name:
                    out.append({"name": name, "type": "", "normalized": name})
        return out

    def _normalize_evidence_set(self, value: Any, title: str, content: str) -> Dict[str, Any]:
        evidence = value if isinstance(value, dict) else {}
        spans = evidence.get("evidence_spans")
        if not isinstance(spans, list) or not spans:
            seed = self._clip_text(title or content, 80)
            spans = [{"text": seed, "start": 0, "end": len(seed)}] if seed else []
        terms = evidence.get("normalized_terms")
        if not isinstance(terms, dict):
            terms = {}
        return {
            "tech_phrases": self._normalize_list(evidence.get("tech_phrases")),
            "normalized_terms": terms,
            "evidence_spans": spans,
            "core_concepts": self._normalize_list(evidence.get("core_concepts")),
        }

    def adapt_structured_response(self, result: Dict[str, Any], title: str, content: str) -> Dict[str, Any]:
        if not isinstance(result, dict):
            raise ValueError("llm parser result must be a dict")

        for banned_key in ("theme_discovery_directive", "ai_analysis"):
            result.pop(banned_key, None)

        event_type = self._safe_str(result.get("event_type") or "其他")
        summary = self._clip_text(result.get("summary") or title or content, 60)
        confidence = result.get("confidence", 0.5)
        severity_score = result.get("severity_score", 0.5)
        source_weight = result.get("source_weight", 1.0)
        if isinstance(confidence, (int, float)) and confidence > 1:
            confidence = float(confidence) / 100.0
        confidence = max(0.0, min(1.0, float(confidence)))
        if isinstance(severity_score, (int, float)) and severity_score > 1:
            severity_score = float(severity_score) / 100.0
        severity_score = max(0.0, min(1.0, float(severity_score)))
        if not isinstance(source_weight, (int, float)):
            source_weight = 1.0

        direction = self._safe_str(result.get("direction")).lower()
        if direction in {"positive", "bullish", "利好"}:
            direction = "利好"
        elif direction in {"negative", "bearish", "利空"}:
            direction = "利空"
        else:
            direction = "中性"

        adapted = {
            "event_type": event_type,
            "entities": self._normalize_entities(result.get("entities")),
            "summary": summary,
            "causal_claim": self._normalize_list(result.get("causal_claim")),
            "evidence_set": self._normalize_evidence_set(result.get("evidence_set"), title, content),
            "severity_score": severity_score,
            "confidence": confidence,
            "source_weight": float(source_weight),
            "timestamp": result.get("timestamp") or result.get("event_time"),
            "impact_industries": self._normalize_list(result.get("impact_industries")),
            "direction": direction,
        }
        return adapted

    async def parse_news(self, title: str, content: str) -> Optional[Dict[str, Any]]:
        """按 P2.phase0 新 schema 解析新闻。"""
        prompt = self.build_event_structuring_prompt(title, content)

        try:
            result = await self.parse_content(prompt)
            if result and isinstance(result, dict):
                adapted = self.adapt_structured_response(result, title, content)
                self.logger.info(f"✅ 成功解析新闻，事件类型: {adapted.get('event_type')}")
                return adapted
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

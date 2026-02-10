#!/bin/bash
# ===============================
# AI主题模型服务 - 模块创建脚本
# 创建 llm_parser 模块及相关文件
# ===============================

set -e  # 遇到错误立即退出

echo "🚀 开始创建 AI 解析模块及相关文件..."
echo "===================================="

# 定义项目根目录（假设从项目根目录运行）
PROJECT_ROOT="."
MODEL_SERVICE_DIR="${PROJECT_ROOT}/model_service"

# 创建 llm_parser 目录结构
echo "📁 创建目录结构..."
mkdir -p "${MODEL_SERVICE_DIR}/llm_parser"

# 1. 创建 __init__.py 文件
echo "📝 创建 llm_parser/__init__.py..."
cat > "${MODEL_SERVICE_DIR}/llm_parser/__init__.py" << 'EOF'
"""
LLM Parser 模块 - 多模型AI解析支持
提供抽象接口，支持 DeepSeek、OpenAI 等大模型
"""
from .base import LLMParser, LLMProvider, ParsedEvent
from .factory import LLMParserFactory

__version__ = "1.0.0"
__all__ = ['LLMParser', 'LLMProvider', 'ParsedEvent', 'LLMParserFactory']
EOF

# 2. 创建抽象基类 base.py
echo "📝 创建 llm_parser/base.py..."
cat > "${MODEL_SERVICE_DIR}/llm_parser/base.py" << 'EOF'
"""
LLM解析器抽象基类定义
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class LLMProvider(Enum):
    """支持的LLM提供商枚举"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    # 未来可扩展：CLAUDE = "claude", GEMINI = "gemini"

@dataclass
class ParsedEvent:
    """标准化的事件解析输出"""
    event_type: str
    impact_industries: List[str]
    direction: str  # 利好/利空/中性
    summary: str
    confidence: float
    raw_response: Optional[Dict] = None  # 保留原始响应供调试

class LLMParser(ABC):
    """LLM解析器抽象基类。所有具体模型解析器必须实现此接口。"""
    
    def __init__(self, provider: LLMProvider):
        self.provider = provider
    
    @abstractmethod
    async def parse_news(self, title: str, content: str) -> Optional[ParsedEvent]:
        """
        核心方法：解析新闻文本，返回结构化事件。
        返回 None 表示解析失败。
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """检查与对应API服务的连接是否健康"""
        pass
    
    @abstractmethod
    async def close(self):
        """清理资源（如HTTP会话）"""
        pass
EOF

# 3. 创建 DeepSeek 解析器
echo "📝 创建 llm_parser/deepseek_parser.py..."
cat > "${MODEL_SERVICE_DIR}/llm_parser/deepseek_parser.py" << 'EOF'
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
EOF

# 4. 创建 OpenAI 解析器
echo "📝 创建 llm_parser/openai_parser.py..."
cat > "${MODEL_SERVICE_DIR}/llm_parser/openai_parser.py" << 'EOF'
"""
OpenAI API 解析器实现
"""
import json
import aiohttp
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import LLMParser, ParsedEvent, LLMProvider

class OpenAIParser(LLMParser):
    """OpenAI API 解析器实现"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", 
                 model: str = "gpt-4o-mini"):
        super().__init__(LLMProvider.OPENAI)
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
        """构建OpenAI专用的Prompt消息"""
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
        """实现基类方法：调用OpenAI API解析新闻"""
        if not title or not content:
            return None
            
        session = await self._get_session()
        messages = self._build_messages(title, content)
        
        try:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
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
            logger.error(f"OpenAI解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"OpenAI未知错误: {e}")
            return None
    
    async def health_check(self) -> bool:
        """检查OpenAI API健康状态"""
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
EOF

# 5. 创建工厂类 factory.py
echo "📝 创建 llm_parser/factory.py..."
cat > "${MODEL_SERVICE_DIR}/llm_parser/factory.py" << 'EOF'
"""
LLM解析器工厂类
"""
import os
import logging
from typing import Dict, Optional

from .base import LLMParser, LLMProvider
from .deepseek_parser import DeepSeekParser
from .openai_parser import OpenAIParser

logger = logging.getLogger(__name__)

class LLMParserFactory:
    """LLM解析器工厂，根据配置创建对应的解析器实例"""
    
    # 提供商与实现类的映射
    _provider_map = {
        LLMProvider.DEEPSEEK: DeepSeekParser,
        LLMProvider.OPENAI: OpenAIParser,
    }
    
    # 默认配置（从环境变量读取）
    _default_configs = {
        LLMProvider.DEEPSEEK: {
            'api_key': os.getenv('DEEPSEEK_API_KEY', ''),
            'base_url': os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com'),
            'model': os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
        },
        LLMProvider.OPENAI: {
            'api_key': os.getenv('OPENAI_API_KEY', ''),
            'base_url': os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1'),
            'model': os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        }
    }
    
    @classmethod
    def create_parser(cls, 
                     provider: LLMProvider, 
                     config_override: Optional[Dict] = None) -> LLMParser:
        """
        创建指定提供商的解析器。
        
        Args:
            provider: 提供商枚举
            config_override: 可选的配置覆盖字典
        
        Returns:
            初始化好的LLMParser实例
        
        Raises:
            ValueError: 如果提供商不支持或配置缺失
        """
        if provider not in cls._provider_map:
            raise ValueError(f"不支持的LLM提供商: {provider}")
        
        # 合并默认配置和自定义覆盖
        config = cls._default_configs.get(provider, {}).copy()
        if config_override:
            config.update(config_override)
        
        # 检查必要的API密钥
        api_key = config.get('api_key')
        if not api_key:
            raise ValueError(f"{provider.value} API密钥未配置，请设置环境变量")
        
        # 获取对应的解析器类并实例化
        parser_class = cls._provider_map[provider]
        logger.info(f"创建 {provider.value} 解析器，模型: {config.get('model')}")
        return parser_class(**config)
    
    @classmethod
    def create_parser_from_env(cls) -> LLMParser:
        """
        从环境变量读取首选提供商并创建解析器。
        例如：设置 PREFERRED_LLM_PROVIDER=deepseek
        """
        preferred = os.getenv('PREFERRED_LLM_PROVIDER', 'deepseek').lower()
        try:
            provider = LLMProvider(preferred)
            logger.info(f"使用环境变量指定的提供商: {provider.value}")
        except ValueError:
            # 如果环境变量设置错误，降级到DeepSeek
            provider = LLMProvider.DEEPSEEK
            logger.warning(f"未知的提供商 '{preferred}'，使用默认: {provider.value}")
        
        return cls.create_parser(provider)
    
    @classmethod
    def get_available_providers(cls):
        """获取所有可用的提供商列表"""
        return list(cls._provider_map.keys())
EOF

# 6. 创建配置文件 config.py
echo "📝 创建 llm_parser/config.py..."
cat > "${MODEL_SERVICE_DIR}/llm_parser/config.py" << 'EOF'
"""
LLM解析器配置管理
"""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class LLMConfig:
    """LLM配置数据类"""
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 500
    timeout: int = 30

class LLMConfigManager:
    """LLM配置管理器"""
    
    @staticmethod
    def load_from_env(provider: str) -> LLMConfig:
        """从环境变量加载配置"""
        prefix = provider.upper()
        
        return LLMConfig(
            provider=provider,
            api_key=os.getenv(f"{prefix}_API_KEY", ""),
            base_url=os.getenv(f"{prefix}_API_BASE"),
            model=os.getenv(f"{prefix}_MODEL"),
            temperature=float(os.getenv(f"{prefix}_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv(f"{prefix}_MAX_TOKENS", "500")),
            timeout=int(os.getenv(f"{prefix}_TIMEOUT", "30"))
        )
    
    @staticmethod
    def validate_config(config: LLMConfig) -> bool:
        """验证配置是否有效"""
        if not config.api_key:
            return False
        return True
EOF

# 现在创建 event_extractor.py（基于LLM解析器）
echo "📝 创建 services/event_extractor.py（新版）..."
mkdir -p "${MODEL_SERVICE_DIR}/services"

cat > "${MODEL_SERVICE_DIR}/services/event_extractor.py" << 'EOF'
"""
事件提取器 - 基于LLM解析器的新实现
"""
import logging
from typing import Dict, Optional

from ..llm_parser.factory import LLMParserFactory
from ..llm_parser.base import LLMParser

logger = logging.getLogger(__name__)

class AIEventExtractor:
    """基于抽象LLMParser的事件提取器"""
    
    def __init__(self, llm_parser: Optional[LLMParser] = None):
        """
        可以传入一个已有的解析器，如果为None则从工厂创建默认解析器。
        """
        self.llm_parser = llm_parser or LLMParserFactory.create_parser_from_env()
        logger.info(f"AI事件提取器已初始化，使用 {self.llm_parser.provider.value} 提供商")
    
    async def extract_event(self, news_data: Dict) -> Optional[Dict]:
        """
        从新闻数据中提取结构化事件。
        保持与原有MockEventExtractor完全相同的接口。
        """
        title = news_data.get('title', '')
        content = news_data.get('content', '')
        news_id = news_data.get('news_id')
        
        if not title or not content:
            logger.warning(f"新闻数据不完整，跳过处理。news_id: {news_id}")
            return None
        
        # 调用抽象的LLM解析器
        parsed_event = await self.llm_parser.parse_news(title, content)
        
        if not parsed_event:
            logger.warning(f"LLM解析失败，未提取到事件。news_id: {news_id}")
            return None
        
        logger.info(f"成功提取事件: news_id={news_id}, type={parsed_event.event_type}")
        
        # 转换为news_event表所需的格式
        return {
            'news_id': news_id,
            'event_type': parsed_event.event_type,
            'impact_industries': parsed_event.impact_industries,
            'direction': parsed_event.direction,
            'confidence': parsed_event.confidence,
            'summary': parsed_event.summary,
            'raw_ai_response': parsed_event.raw_response
        }
    
    async def health_check(self) -> bool:
        """检查提取器健康状态"""
        if not self.llm_parser:
            return False
        return await self.llm_parser.health_check()
    
    async def close(self):
        """清理资源"""
        if self.llm_parser:
            await self.llm_parser.close()
            logger.info("AI事件提取器资源已释放")

# 保持向后兼容的Mock提取器（供测试使用）
class MockEventExtractor:
    """模拟事件提取器，用于测试"""
    
    async def extract_event(self, news_data: Dict) -> Optional[Dict]:
        import random
        from datetime import datetime
        
        event_types = ["政策", "技术", "财报", "产业", "资本", "其他"]
        industries = ["人工智能", "新能源汽车", "芯片半导体", "医药生物", "金融"]
        directions = ["利好", "利空", "中性"]
        
        return {
            'news_id': news_data.get('news_id', 'mock_001'),
            'event_type': random.choice(event_types),
            'impact_industries': random.sample(industries, k=random.randint(1, 3)),
            'direction': random.choice(directions),
            'confidence': round(random.uniform(0.7, 0.95), 2),
            'summary': f"模拟事件摘要 - {datetime.now().strftime('%H:%M:%S')}",
            'raw_ai_response': {"mock": True}
        }
    
    async def health_check(self) -> bool:
        return True
    
    async def close(self):
        pass
EOF

# 7. 创建 run_news_event.py 主运行脚本
echo "📝 创建 run_news_event.py..."
cat > "${MODEL_SERVICE_DIR}/run_news_event.py" << 'EOF'
#!/usr/bin/env python3
"""
AI事件抽取服务 - 主运行脚本
从news_raw表读取新闻，调用AI解析，存储到news_event表
"""
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

# 添加项目路径，确保导入正常
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model_service.database import DatabaseManager as db_manager
from model_service.services.event_extractor import AIEventExtractor, MockEventExtractor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NewsEventProcessor:
    """新闻事件处理器"""
    
    def __init__(self, use_mock: bool = False):
        """
        初始化处理器
        
        Args:
            use_mock: 是否使用模拟提取器（用于测试）
        """
        self.use_mock = use_mock
        self.extractor = None
        self.batch_size = int(os.getenv('BATCH_SIZE', '10'))
        
    async def initialize(self):
        """初始化组件"""
        logger.info("初始化新闻事件处理器...")
        
        # 初始化数据库
        await db_manager.initialize_db()
        logger.info("数据库连接初始化完成")
        
        # 初始化事件提取器
        if self.use_mock or os.getenv('USE_MOCK_EXTRACTOR', 'false').lower() == 'true':
            self.extractor = MockEventExtractor()
            logger.warning("⚠️ 使用模拟事件提取器（仅测试）")
        else:
            self.extractor = AIEventExtractor()
            logger.info("✅ AI事件提取器初始化完成")
        
        logger.info(f"批处理大小: {self.batch_size}")
    
    async def fetch_pending_news(self, limit: Optional[int] = None) -> List[Dict]:
        """
        从数据库获取待处理的新闻
        
        Args:
            limit: 限制返回数量，None表示无限制
        
        Returns:
            新闻数据列表
        """
        query_limit = limit or self.batch_size
        
        # 这里需要根据你的实际数据库结构调整SQL
        # 假设你的news_raw表有is_processed字段标识是否已处理
        query = """
        SELECT id, news_id, title, content, source, publish_date, market
        FROM news_raw 
        WHERE is_processed = FALSE
        ORDER BY publish_date DESC, id ASC
        LIMIT $1
        """
        
        try:
            rows = await db_manager.execute_query(query, query_limit)
            logger.info(f"获取到 {len(rows)} 条待处理新闻")
            return rows
        except Exception as e:
            logger.error(f"查询待处理新闻失败: {e}")
            return []
    
    async def process_single_news(self, news_item: Dict) -> Optional[Dict]:
        """
        处理单条新闻
        
        Args:
            news_item: 新闻数据字典
        
        Returns:
            成功返回事件数据，失败返回None
        """
        news_id = news_item.get('news_id') or news_item.get('id')
        
        try:
            # 调用事件提取器
            event_data = await self.extractor.extract_event(news_item)
            
            if not event_data:
                logger.warning(f"新闻 {news_id} 未提取到事件")
                return None
            
            # 添加时间戳
            event_data['created_at'] = datetime.now().isoformat()
            
            # 记录成功日志
            logger.info(f"✅ 新闻 {news_id} 处理成功: {event_data.get('event_type')}")
            
            return event_data
            
        except Exception as e:
            logger.error(f"处理新闻 {news_id} 时发生错误: {e}")
            return None
    
    async def mark_news_as_processed(self, news_id: str):
        """标记新闻为已处理"""
        try:
            update_query = """
            UPDATE news_raw 
            SET is_processed = TRUE, processed_at = NOW()
            WHERE news_id = $1 OR id = $1
            """
            await db_manager.execute_query(update_query, news_id)
            logger.debug(f"新闻 {news_id} 已标记为已处理")
        except Exception as e:
            logger.error(f"标记新闻 {news_id} 为已处理失败: {e}")
    
    async def save_event_to_db(self, event_data: Dict) -> bool:
        """保存事件到数据库"""
        try:
            # 这里需要根据你的news_event表结构调整
            insert_query = """
            INSERT INTO news_event 
            (news_id, event_type, impact_industries, direction, confidence, summary, raw_ai_response, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """
            
            await db_manager.execute_query(
                insert_query,
                event_data['news_id'],
                event_data['event_type'],
                event_data['impact_industries'],
                event_data['direction'],
                event_data['confidence'],
                event_data['summary'],
                event_data.get('raw_ai_response'),
                event_data['created_at']
            )
            
            return True
        except Exception as e:
            logger.error(f"保存事件到数据库失败: {e}")
            return False
    
    async def process_batch(self) -> Dict:
        """
        处理一批新闻
        
        Returns:
            处理统计信息
        """
        stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'start_time': datetime.now()
        }
        
        # 获取待处理新闻
        pending_news = await self.fetch_pending_news()
        stats['total'] = len(pending_news)
        
        if not pending_news:
            logger.info("没有待处理的新闻")
            return stats
        
        logger.info(f"开始处理 {len(pending_news)} 条新闻...")
        
        # 处理每条新闻
        for news_item in pending_news:
            news_id = news_item.get('news_id') or news_item.get('id')
            
            # 处理新闻
            event_data = await self.process_single_news(news_item)
            
            if event_data and await self.save_event_to_db(event_data):
                # 标记原新闻为已处理
                await self.mark_news_as_processed(news_id)
                stats['success'] += 1
            else:
                stats['failed'] += 1
            
            # 添加处理间隔，避免API限流
            await asyncio.sleep(0.5)
        
        # 计算耗时
        stats['end_time'] = datetime.now()
        stats['duration'] = (stats['end_time'] - stats['start_time']).total_seconds()
        
        return stats
    
    async def run_continuously(self, interval_seconds: int = 300):
        """
        持续运行处理器
        
        Args:
            interval_seconds: 处理间隔（秒）
        """
        logger.info(f"开始持续运行，间隔: {interval_seconds}秒")
        
        while True:
            try:
                logger.info("=" * 50)
                logger.info("开始新一轮处理...")
                
                stats = await self.process_batch()
                
                # 打印统计信息
                if stats['total'] > 0:
                    success_rate = (stats['success'] / stats['total']) * 100
                    logger.info(f"处理完成: {stats['success']}成功, {stats['failed']}失败, 成功率: {success_rate:.1f}%, 耗时: {stats['duration']:.1f}秒")
                else:
                    logger.info("本轮无待处理新闻")
                
                # 等待下一轮
                logger.info(f"等待 {interval_seconds} 秒后进行下一轮处理...")
                await asyncio.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                logger.info("收到中断信号，停止运行...")
                break
            except Exception as e:
                logger.error(f"处理器运行异常: {e}")
                logger.info("等待10秒后重试...")
                await asyncio.sleep(10)
    
    async def cleanup(self):
        """清理资源"""
        if self.extractor:
            await self.extractor.close()
            logger.info("事件提取器资源已清理")
        
        await db_manager.close()
        logger.info("数据库连接已关闭")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI新闻事件抽取处理器')
    parser.add_argument('--mock', action='store_true', help='使用模拟提取器（测试用）')
    parser.add_argument('--once', action='store_true', help='只运行一次，不持续运行')
    parser.add_argument('--interval', type=int, default=300, help='处理间隔（秒），默认300')
    parser.add_argument('--limit', type=int, help='限制处理数量（测试用）')
    
    args = parser.parse_args()
    
    processor = NewsEventProcessor(use_mock=args.mock)
    
    try:
        # 初始化
        await processor.initialize()
        
        if args.once:
            # 单次运行模式
            stats = await processor.process_batch()
            if stats['total'] > 0:
                success_rate = (stats['success'] / stats['total']) * 100
                print(f"\n处理完成:")
                print(f"  总计: {stats['total']}")
                print(f"  成功: {stats['success']}")
                print(f"  失败: {stats['failed']}")
                print(f"  成功率: {success_rate:.1f}%")
                print(f"  耗时: {stats['duration']:.1f}秒")
        else:
            # 持续运行模式
            await processor.run_continuously(args.interval)
            
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行失败: {e}")
        return 1
    finally:
        # 清理资源
        await processor.cleanup()
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
EOF

# 8. 创建 requirements.txt 依赖文件
echo "📝 创建 model_service/requirements.txt..."
cat > "${MODEL_SERVICE_DIR}/requirements.txt" << 'EOF'
# AI解析模块依赖
aiohttp>=3.9.0
tenacity>=8.2.0
openai>=1.0.0

# 数据库
asyncpg>=0.29.0
psycopg2-binary>=2.9.0
SQLAlchemy>=2.0.0

# Web框架
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0

# 工具库
python-dotenv>=1.0.0
pytz>=2023.3
EOF

# 9. 创建环境变量示例文件
echo "📝 创建 .env.example..."
cat > "${MODEL_SERVICE_DIR}/.env.example" << 'EOF'
# =================================
# AI事件抽取服务 - 环境变量配置示例
# =================================

# 数据库配置
DATABASE_URL=postgresql://user:password@localhost/stock_data

# 首选LLM提供商 (deepseek 或 openai)
PREFERRED_LLM_PROVIDER=deepseek

# DeepSeek配置
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TEMPERATURE=0.2
DEEPSEEK_MAX_TOKENS=500

# OpenAI配置
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.2
OPENAI_MAX_TOKENS=500

# 处理配置
BATCH_SIZE=10
USE_MOCK_EXTRACTOR=false
PROCESS_INTERVAL_SECONDS=300
EOF

# 10. 创建 README.md 使用说明
echo "📝 创建 README.md..."
cat > "${MODEL_SERVICE_DIR}/README.md" << 'EOF'
# AI事件抽取服务 (model_service)

基于LLM的新闻事件结构化抽取服务，支持多模型切换。

## 功能特性

- ✅ 多模型支持：DeepSeek、OpenAI等
- ✅ 模块化设计：易于扩展新模型
- ✅ 异步处理：高性能批处理
- ✅ 错误处理：自动重试和降级机制
- ✅ 配置灵活：环境变量驱动

## 项目结构

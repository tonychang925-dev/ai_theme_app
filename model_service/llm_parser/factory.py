"""
LLM解析器工厂 - 修复导入和命名冲突版本
根据环境变量创建合适的LLM解析器
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class LLMParserFactory:
    """LLM解析器工厂类"""
    
    @staticmethod
    def create_parser_from_env() -> Optional['BaseLLMParser']:
        """
        根据环境变量创建LLM解析器
        
        环境变量优先级:
        1. AI_PARSER_TYPE: 指定解析器类型 (deepseek, openai)
        2. DEEPSEEK_API_KEY: 如果设置则使用DeepSeek
        3. OPENAI_API_KEY: 如果设置则使用OpenAI
        """
        # 先尝试导入BaseLLMParser
        try:
            from .base_parser import BaseLLMParser
        except ImportError as e:
            logger.warning(f"相对导入BaseLLMParser失败: {e}")
            # 备用导入方案
            try:
                import sys
                current_dir = os.path.dirname(os.path.abspath(__file__))
                if current_dir not in sys.path:
                    sys.path.insert(0, current_dir)
                from base_parser import BaseLLMParser
                logger.info("✅ 使用备用方案导入BaseLLMParser")
            except ImportError as e2:
                logger.error(f"备用导入也失败: {e2}")
                # 创建虚拟基类
                class BaseLLMParser:
                    def __init__(self, model_name=""):
                        self.model_name = model_name
                        self.logger = logging.getLogger(self.__class__.__name__)
        
        parser_type = os.getenv("AI_PARSER_TYPE", "").lower().strip()
        
        # 根据环境变量选择解析器
        if parser_type == "deepseek" or os.getenv("DEEPSEEK_API_KEY"):
            logger.info("尝试使用DeepSeek解析器...")
            try:
                from .deepseek_parser_0203 import DeepSeekParser
                return DeepSeekParser()
            except ImportError as e:
                logger.error(f"导入DeepSeekParser失败: {e}")
                # 尝试其他方式导入
                try:
                    # 备用导入方案
                    import sys
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    deepseek_path = os.path.join(current_dir, "deepseek_parser.py")
                    
                    if os.path.exists(deepseek_path):
                        logger.info(f"尝试直接导入文件: {deepseek_path}")
                        import importlib.util
                        spec = importlib.util.spec_from_file_location("deepseek_parser_module", deepseek_path)
                        deepseek_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(deepseek_module)
                        return deepseek_module.DeepSeekParser()
                    else:
                        logger.error(f"deepseek_parser.py文件不存在: {deepseek_path}")
                except Exception as e2:
                    logger.error(f"备用导入也失败: {e2}")
        
        elif parser_type == "openai" or os.getenv("OPENAI_API_KEY"):
            logger.info("尝试使用OpenAI解析器...")
            try:
                from .openai_parser import OpenAIParser
                return OpenAIParser()
            except ImportError as e:
                logger.error(f"导入OpenAIParser失败: {e}")
        
        # 默认使用DeepSeek或模拟解析器
        logger.info("尝试使用DeepSeek作为默认解析器...")
        try:
            from .deepseek_parser_0203 import DeepSeekParser
            return DeepSeekParser()
        except ImportError as e:
            logger.warning(f"DeepSeek解析器不可用: {e}")
            logger.warning("使用模拟解析器")
            # 创建模拟解析器
            class MockParser(BaseLLMParser):
                def __init__(self, model_name="mock-parser"):
                    super().__init__(model_name)
                
                async def parse_content(self, content: str):
                    logger.info("模拟解析器处理内容")
                    return {
                        "event_type": "模拟事件",
                        "impact_industries": ["模拟行业"],
                        "direction": "neutral",
                        "confidence": 50,
                        "summary": "模拟解析结果"
                    }
                
                async def parse_news(self, title: str, content: str):
                    return await self.parse_content(f"{title}\n{content}")
            
            return MockParser()
    
    @staticmethod
    def create_parser(parser_type: str, **kwargs) -> Optional['BaseLLMParser']:
        """
        直接创建指定类型的解析器
        
        Args:
            parser_type: 解析器类型 ('deepseek', 'openai', 'mock')
            **kwargs: 传递给解析器的参数
        """
        parser_type = parser_type.lower().strip()
        
        try:
            from .base_parser import BaseLLMParser
        except ImportError:
            logger.warning("无法导入BaseLLMParser，创建虚拟基类")
            # 创建虚拟基类
            class BaseLLMParser:
                def __init__(self, model_name=""):
                    self.model_name = model_name
        
        if parser_type == "deepseek":
            try:
                from .deepseek_parser_0203 import DeepSeekParser
                return DeepSeekParser(**kwargs)
            except ImportError as e:
                logger.error(f"DeepSeekParser导入失败: {e}")
                return None
                
        elif parser_type == "openai":
            try:
                from .openai_parser import OpenAIParser
                return OpenAIParser(**kwargs)
            except ImportError as e:
                logger.error(f"OpenAIParser导入失败: {e}")
                return None
                
        elif parser_type == "mock":
            logger.info("创建模拟解析器")
            class MockParser(BaseLLMParser):
                def __init__(self, model_name="mock-parser", **kwargs):
                    super().__init__(model_name)
                    self.mock_data = kwargs.get("mock_data", {})
                
                async def parse_content(self, content: str):
                    return {
                        "event_type": "模拟事件",
                        "impact_industries": ["模拟行业"],
                        "direction": "neutral",
                        "confidence": 75,
                        "summary": f"模拟解析: {content[:50]}...",
                        **self.mock_data
                    }
                
                async def parse_news(self, title: str, content: str):
                    result = await self.parse_content(f"{title}\n{content}")
                    result["event_type"] = "行业新闻"
                    return result
            
            return MockParser(**kwargs)
        
        else:
            logger.error(f"不支持的解析器类型: {parser_type}")
            return None

# 导出
__all__ = ['LLMParserFactory']

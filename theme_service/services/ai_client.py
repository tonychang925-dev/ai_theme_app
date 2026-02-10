"""
简化版AI客户端 - 直接集成模式
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AIThemeClient:
    """AI主题客户端"""
    
    def __init__(self, settings):
        self.settings = settings
        self._analyzer = None
        logger.info(f"AIThemeClient初始化，模式: {settings.INTEGRATION_MODE}")
    
    async def _init_analyzer(self):
        """延迟初始化分析器"""
        if self._analyzer is not None:
            return
        
        try:
            # 动态导入现有模块
            from model_service.llm_parser.factory import LLMParserFactory
            from model_service.llm_parser.theme_analyzer import ThemeAnalyzer
            
            # 创建解析器
            parser = LLMParserFactory.create_parser_from_env()
            
            # 创建主题分析器
            self._analyzer = ThemeAnalyzer(parser)
            logger.info("AI分析器初始化成功")
            
        except Exception as e:
            logger.error(f"初始化AI分析器失败: {e}")
            # 创建模拟分析器
            class MockAnalyzer:
                async def analyze_for_theme_discovery(self, event_data):
                    return {
                        "potential_themes": ["AI眼镜", "测试题材"],
                        "certainty": 0.7,
                        "mock": True
                    }
            self._analyzer = MockAnalyzer()
            logger.warning("使用模拟分析器")
    
    async def analyze_event_for_themes(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析事件以发现题材"""
        await self._init_analyzer()
        return await self._analyzer.analyze_for_theme_discovery(event_data)

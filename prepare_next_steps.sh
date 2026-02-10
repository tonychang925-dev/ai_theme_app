#!/bin/bash
# prepare_next_steps.sh - 准备下一步开发
echo "🚀 准备 theme_service 开发"
echo "========================"

# 1. 创建目录结构
mkdir -p theme_service/{services,models,core,api}

# 2. 创建基础文件
cat > theme_service/__init__.py << 'FILEEOF'
"""
AI题材引擎 (theme_service)
"""
__version__ = "1.0.0"
FILEEOF

cat > theme_service/config.py << 'FILEEOF'
"""
theme_service 配置
"""
from pydantic_settings import BaseSettings

class ThemeServiceSettings(BaseSettings):
    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8002
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    # 集成模式
    INTEGRATION_MODE: str = "direct"
    
    # 题材发现配置
    THEME_DISCOVERY_ENABLED: bool = True
    MIN_EVENTS_FOR_THEME: int = 2
    THEME_CONFIDENCE_THRESHOLD: float = 0.6
    
    class Config:
        env_file = ".env.theme"

settings = ThemeServiceSettings()
FILEEOF

# 3. 创建简化版AI客户端
cat > theme_service/services/ai_client.py << 'FILEEOF'
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
FILEEOF

echo "✅ theme_service 基础结构已创建"
echo ""
echo "📁 创建的文件:"
find theme_service -name "*.py" | sort
echo ""
echo "🚀 下一步:"
echo "1. 运行: python -c 'import sys; sys.path.insert(0, \".\"); from theme_service.services.ai_client import AIThemeClient; print(\"✅ 客户端可以导入\")'"
echo "2. 开发 ThemeDiscoveryEngine"
echo "3. 实现数据库层"

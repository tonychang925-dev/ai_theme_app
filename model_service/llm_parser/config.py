# model_service/llm_parser/config.py
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

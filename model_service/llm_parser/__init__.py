"""
LLM解析器模块 - 简化版本避免循环导入
"""
# 使用延迟导入，避免循环导入问题
import sys

__version__ = "1.0.0"

# 只在需要时导入，避免factory.py和deepseek_parser.py的循环导入
def __getattr__(name):
    """延迟导入模块"""
    if name == "BaseLLMParser":
        from .base_parser import BaseLLMParser
        return BaseLLMParser
    elif name == "DeepSeekParser":
        from .deepseek_parser_0203 import DeepSeekParser
        return DeepSeekParser
    elif name == "OpenAIParser":
        from .openai_parser import OpenAIParser
        return OpenAIParser
    elif name == "LLMParserFactory":
        from .factory import LLMParserFactory
        return LLMParserFactory
    else:
        raise AttributeError(f"module 'llm_parser' has no attribute '{name}'")

# 明确导出
__all__ = ['BaseLLMParser', 'DeepSeekParser', 'OpenAIParser', 'LLMParserFactory']

# 调试信息
if __name__ == "__main__":
    print(f"llm_parser模块加载成功，版本: {__version__}")
    print(f"导出: {__all__}")

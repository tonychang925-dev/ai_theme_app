import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache

class ModelServiceSettings(BaseSettings):
    """模型服务配置"""
    
    # 数据库配置
    DATABASE_URL: str = Field(
        default="postgresql://postgres:zxbzj~925@localhost/stock_data",
        description="PostgreSQL数据库连接URL"
    )
    
    # AI服务配置
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API密钥")
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None, description="DeepSeek API密钥")
    AI_MODEL: str = Field(default="gpt-3.5-turbo", description="使用的AI模型")
    
    # 处理配置
    BATCH_SIZE: int = Field(default=5, description="批量处理大小")
    MAX_RETRIES: int = Field(default=3, description="最大重试次数")
    REQUEST_TIMEOUT: int = Field(default=30, description="API请求超时时间")
    
    # 服务配置
    HOST: str = Field(default="0.0.0.0", description="服务监听地址")
    PORT: int = Field(default=8001, description="服务监听端口")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略额外字段

@lru_cache()
def get_settings() -> ModelServiceSettings:
    return ModelServiceSettings()

settings = get_settings()

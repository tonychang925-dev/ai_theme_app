# ai_theme_app/news_crawler_service/config.py
import os
from typing import List, Dict, Any
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from functools import lru_cache

class CrawlerSettings(BaseSettings):
    """新闻抓取配置类"""
    
    # 数据库配置
    DATABASE_URL: str = Field(
        default="postgresql://postgres:zxbzj~925@localhost/stock_data",
        description="PostgreSQL数据库连接URL"
    )
    
    # 抓取策略配置
    REQUEST_INTERVAL_SECONDS: int = Field(
        default=15,
        ge=10,
        description="全局最小请求间隔（秒），防反爬"
    )
    MAX_RETRY_TIMES: int = Field(
        default=3,
        ge=1,
        le=5,
        description="最大重试次数"
    )
    ENABLE_PROXY: bool = Field(
        default=False,
        description="是否启用代理池"
    )
    
    # 数据源配置
    ENABLED_SOURCES: List[str] = Field(
        default=["akshare_cls","akshare_cctv"],
        description="启用的数据源列表"
    )
    
    # 日志配置
    LOG_LEVEL: str = Field(
        default="INFO",
        description="日志级别：DEBUG/INFO/WARNING/ERROR"
    )
    LOG_FILE: str = Field(
        default="logs/news_crawler.log",
        description="日志文件路径"
    )
    
    # 熔断器配置
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5,
        description="连续失败多少次后熔断"
    )
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=300,
        description="熔断恢复时间（秒）"
    )
    
    # 验证器：确保数据源列表不为空
    @validator('ENABLED_SOURCES')
    def validate_enabled_sources(cls, v):
        if not v:
            raise ValueError('ENABLED_SOURCES 不能为空')
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> CrawlerSettings:
    """获取配置单例（缓存）"""
    return CrawlerSettings()

# 全局配置实例
settings = get_settings()

SOURCE_CLASS_MAP = {
    "akshare_cls": "news_crawler_service.collectors.akshare_cls.AkshareClsCollector",
    "akshare_cctv": "news_crawler_service.collectors.akshare_cctv.AkshareCctvCollector",
}


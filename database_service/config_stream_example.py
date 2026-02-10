"""
Redis Stream 配置示例
将此配置合并到现有的 config.py 中
"""
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class RedisStreamConfig:
    """Redis Stream配置"""
    enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    
    streams: Dict[str, str] = field(default_factory=lambda: {
        "news_raw": "stream:news:raw",
        "events_major": "stream:events:major",
        "events_normal": "stream:events:normal",
        "themes_updates": "stream:themes:updates",
        "dead_letter": "stream:dead:letter"
    })

@dataclass
class DatabaseConfig:
    """扩展现有的 DatabaseConfig"""
    # 原有配置...
    
    # 新增Stream配置
    redis_stream: RedisStreamConfig = field(default_factory=RedisStreamConfig)

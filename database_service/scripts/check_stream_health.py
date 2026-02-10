#!/usr/bin/env python3
"""
检查Stream健康状态
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database_service.streams.stream_config import get_enhanced_config
from database_service.streams.stream_manager import RedisStreamManager

async def check_stream_health():
    """检查Stream健康状态"""
    print("🔍 检查Redis Stream健康状态")
    print("=" * 60)
    
    config = get_enhanced_config()
    
    if not config.redis.enabled:
        print("❌ Redis未启用")
        return False
    
    # 创建Stream管理器
    redis_url = f"redis://{config.redis.host}:{config.redis.port}/{config.redis.db}"
    if config.redis.password:
        redis_url = f"redis://:{config.redis.password}@{config.redis.host}:{config.redis.port}/{config.redis.db}"
    
    stream_manager = RedisStreamManager(redis_url)
    
    try:
        await stream_manager.connect()
        print("✅ Redis连接成功")
        
        # 检查所有Stream
        streams_to_check = [
            "stream:news:raw",
            "stream:events:major",
            "stream:events:normal",
            "stream:themes:updates",
            "stream:dead:letter"
        ]
        
        all_healthy = True
        
        for stream in streams_to_check:
            try:
                info = await stream_manager.get_stream_info(stream)
                
                if "error" in info:
                    print(f"❌ {stream}: {info['error']}")
                    all_healthy = False
                else:
                    length = info.get("length", 0)
                    status = "✅" if length < 1000 else "⚠️ "
                    print(f"{status} {stream}: {length} 条消息")
                    
                    # 检查是否积压
                    if length > 5000:
                        print(f"   ⚠️  警告: {stream} 积压超过5000条")
            
            except Exception as e:
                print(f"❌ {stream}: 错误 - {e}")
                all_healthy = False
        
        # 检查外部服务
        print("\n🔗 检查外部服务:")
        
        # 检查模型服务
        from database_service.services.model_service_client import ModelServiceClient
        model_client = ModelServiceClient(config.external_services.model_service["url"])
        model_healthy = await model_client.health_check()
        print(f"  模型服务: {'✅ 健康' if model_healthy else '❌ 异常'}")
        
        # 检查题材服务
        from database_service.services.theme_service_client import ThemeServiceClient
        theme_client = ThemeServiceClient(config.external_services.theme_service["url"])
        theme_healthy = await theme_client.health_check()
        print(f"  题材服务: {'✅ 健康' if theme_healthy else '❌ 异常'}")
        
        print("=" * 60)
        
        if all_healthy and model_healthy and theme_healthy:
            print("✅ 所有系统健康")
            return True
        else:
            print("⚠️  系统存在异常")
            return False
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        return False
    finally:
        if 'stream_manager' in locals():
            await stream_manager.redis.close()

if __name__ == "__main__":
    healthy = asyncio.run(check_stream_health())
    sys.exit(0 if healthy else 1)

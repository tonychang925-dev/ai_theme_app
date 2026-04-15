#!/usr/bin/env python3
"""
测试Redis Stream初始化
"""

import asyncio
import os
import sys
from pathlib import Path

import redis.asyncio as redis

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

async def test_redis_stream_init():
    """测试Redis Stream初始化"""
    print("测试Redis Stream初始化...")

    # 初始化Redis
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )

    try:
        await redis_client.ping()
        print("✅ Redis连接成功")
    except Exception as e:
        print(f"❌ Redis连接失败: {e}")
        return

    # 定义stream名称
    raw_stream = "stream:news:raw"
    structured_stream = "stream:events:structured"
    decision_stream = "stream:events:decision"
    dead_letter_stream = "stream:dead:letter"

    # 清理stream
    print("清理stream...")
    for stream_name in (raw_stream, structured_stream, decision_stream, dead_letter_stream):
        try:
            result = await redis_client.delete(stream_name)
            print(f"  删除 {stream_name}: {result}")
        except Exception as e:
            print(f"  删除 {stream_name} 失败: {e}")

    # 测试xinfo_stream
    print("\n测试xinfo_stream...")
    for stream_name in (raw_stream, structured_stream, decision_stream, dead_letter_stream):
        try:
            info = await redis_client.xinfo_stream(stream_name)
            print(f"  {stream_name}: {info}")
        except Exception as e:
            print(f"  {stream_name}: 错误 - {e}")

    # 创建consumer group
    print("\n创建consumer group...")
    try:
        # 先创建stream（通过添加一条消息）
        await redis_client.xadd(raw_stream, {"test": "init"}, maxlen=1)
        print(f"  创建stream: {raw_stream}")

        # 创建consumer group
        await redis_client.xgroup_create(raw_stream, "test_group", id="0", mkstream=True)
        print(f"  创建consumer group: test_group")
    except Exception as e:
        print(f"  创建consumer group失败: {e}")

    # 清理
    await redis_client.delete(raw_stream)
    await redis_client.close()

    print("\n✅ 测试完成")

async def main():
    """主函数"""
    await test_redis_stream_init()

if __name__ == "__main__":
    asyncio.run(main())
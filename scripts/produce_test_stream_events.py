#!/usr/bin/env python3
"""
生成测试Stream事件

用于测试实时推送服务的Redis Stream数据生成器。
"""
import asyncio
import json
import os
import sys
import random
from datetime import datetime
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from redis.asyncio import Redis


async def produce_test_events():
    """生成测试事件到Redis Stream"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"连接到Redis: {redis_url}")

    redis_client = Redis.from_url(redis_url, decode_responses=True)

    try:
        # 测试连接
        pong = await redis_client.ping()
        if not pong:
            print("❌ Redis连接失败")
            return False

        print("✅ Redis连接成功")

        # 定义测试Stream
        streams = [
            "stream:event:feed",
            "stream:theme:feed",
            "stream:news:feed",
            "stream:stock:feed"
        ]

        # 事件类型映射
        event_types = {
            "stream:event:feed": ["theme_move", "new_theme", "stock_move", "market_event"],
            "stream:theme:feed": ["theme_rank_change", "theme_emergence", "theme_decay", "theme_hot"],
            "stream:news:feed": ["news_ingested", "news_processed", "news_clustered", "news_alert"],
            "stream:stock:feed": ["stock_abnormal", "money_flow", "dragon_tiger", "limit_up"]
        }

        # 主题示例
        themes = ["人工智能", "新能源车", "半导体", "医药", "白酒", "军工", "碳中和", "元宇宙"]
        stocks = ["000001.SZ", "000002.SZ", "000333.SZ", "000858.SZ", "002415.SZ", "300750.SZ", "600519.SH", "601012.SH"]

        print(f"开始生成测试事件到 {len(streams)} 个Stream...")
        print("按Ctrl+C停止")

        event_count = 0
        while True:
            for stream_name in streams:
                # 随机选择事件类型
                event_type = random.choice(event_types[stream_name])

                # 构建事件数据
                event_data: Dict[str, Any] = {
                    "event_type": event_type,
                    "timestamp": datetime.now().isoformat(),
                    "message": f"测试{event_type}事件",
                    "source": "test_producer"
                }

                # 根据Stream类型添加特定字段
                if stream_name == "stream:event:feed":
                    event_data.update({
                        "subject_key": random.choice(themes),
                        "confidence": round(random.uniform(0.7, 0.95), 2),
                        "impact_score": random.randint(1, 10)
                    })
                elif stream_name == "stream:theme:feed":
                    event_data.update({
                        "subject_key": random.choice(themes),
                        "heat_score": random.randint(50, 100),
                        "rank_change": random.randint(-5, 5),
                        "market_cap": random.randint(1000, 10000)
                    })
                elif stream_name == "stream:news:feed":
                    event_data.update({
                        "news_id": f"news_{random.randint(1000, 9999)}",
                        "title": f"测试新闻标题 {random.randint(1, 100)}",
                        "publisher": random.choice(["新浪财经", "东方财富", "证券时报", "财联社"]),
                        "sentiment": round(random.uniform(-0.5, 0.5), 2)
                    })
                elif stream_name == "stream:stock:feed":
                    event_data.update({
                        "stock_id": random.choice(stocks),
                        "stock_name": f"股票{random.randint(1, 100)}",
                        "price_change": round(random.uniform(-5, 5), 2),
                        "turnover_rate": round(random.uniform(1, 20), 2),
                        "amount": random.randint(10000000, 100000000)
                    })

                # 添加到Stream
                try:
                    message_id = await redis_client.xadd(
                        stream_name,
                        {
                            "data": json.dumps(event_data, ensure_ascii=False),
                            "type": event_type,
                            "produced_at": datetime.now().isoformat()
                        },
                        maxlen=1000  # 限制Stream长度，避免内存占用
                    )

                    event_count += 1
                    if event_count % 10 == 0:
                        print(f"✅ 已生成 {event_count} 个事件，最新ID: {message_id}")

                except Exception as e:
                    print(f"❌ 写入Stream失败 {stream_name}: {e}")

            # 等待一段时间再生成下一批事件
            await asyncio.sleep(random.uniform(0.5, 2.0))

    except KeyboardInterrupt:
        print("\n\n⏹️  停止事件生成")
    except Exception as e:
        print(f"❌ 事件生成失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await redis_client.close()
        print("🔌 Redis连接已关闭")

    return True


async def cleanup_test_streams():
    """清理测试Stream"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"清理测试Stream，Redis: {redis_url}")

    redis_client = Redis.from_url(redis_url, decode_responses=True)

    try:
        streams = [
            "stream:event:feed",
            "stream:theme:feed",
            "stream:news:feed",
            "stream:stock:feed"
        ]

        for stream_name in streams:
            # 删除Stream
            deleted = await redis_client.delete(stream_name)
            if deleted:
                print(f"✅ 清理Stream: {stream_name}")
            else:
                print(f"📝 Stream不存在: {stream_name}")

        print("🎉 测试Stream清理完成")

    except Exception as e:
        print(f"❌ 清理Stream失败: {e}")
    finally:
        await redis_client.close()


async def list_stream_info():
    """列出Stream信息"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"Stream信息，Redis: {redis_url}")

    redis_client = Redis.from_url(redis_url, decode_responses=True)

    try:
        streams = [
            "stream:event:feed",
            "stream:theme:feed",
            "stream:news:feed",
            "stream:stock:feed"
        ]

        for stream_name in streams:
            # 获取Stream长度
            length = await redis_client.xlen(stream_name)
            print(f"📊 {stream_name}: {length} 条消息")

            # 获取消费者组信息
            try:
                groups = await redis_client.xinfo_groups(stream_name)
                if groups:
                    print(f"  消费者组:")
                    for group in groups:
                        print(f"    - {group['name']}: {group['consumers']} 消费者, "
                              f"待处理: {group['pending']}")
            except Exception as e:
                if "NOGROUP" not in str(e):
                    print(f"  获取消费者组信息失败: {e}")

    except Exception as e:
        print(f"❌ 获取Stream信息失败: {e}")
    finally:
        await redis_client.close()


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Redis Stream测试事件生成器")
    parser.add_argument("--produce", action="store_true", help="生成测试事件")
    parser.add_argument("--cleanup", action="store_true", help="清理测试Stream")
    parser.add_argument("--info", action="store_true", help="查看Stream信息")
    parser.add_argument("--interval", type=float, default=1.0, help="事件生成间隔(秒)")

    args = parser.parse_args()

    if args.produce:
        await produce_test_events()
    elif args.cleanup:
        await cleanup_test_streams()
    elif args.info:
        await list_stream_info()
    else:
        print("请指定操作: --produce, --cleanup 或 --info")
        parser.print_help()


if __name__ == "__main__":
    # 切换到项目根目录
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    asyncio.run(main())
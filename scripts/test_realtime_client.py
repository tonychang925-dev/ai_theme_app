#!/usr/bin/env python3
"""
实时推送服务客户端测试

用于测试WebSocket连接和实时消息接收。
"""
import asyncio
import json
import sys
import os
from typing import Dict, Any, Optional
import websockets
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RealtimeClient:
    """实时推送客户端"""

    def __init__(self, ws_url: str = "ws://localhost:8000/ws/realtime"):
        self.ws_url = ws_url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.client_id: Optional[str] = None
        self.received_messages = []
        self.running = False

    async def connect(self):
        """连接WebSocket服务器"""
        print(f"🔗 连接到 {self.ws_url}")
        try:
            self.websocket = await websockets.connect(self.ws_url)
            print("✅ WebSocket连接成功")

            # 接收连接确认消息
            response = await self.websocket.recv()
            message = json.loads(response)
            print(f"📥 收到服务器消息: {message}")

            if message.get("type") == "connected":
                self.client_id = message.get("client_id")
                print(f"🆔 客户端ID: {self.client_id}")
                return True
            else:
                print(f"⚠️  意外的连接响应: {message}")
                return False

        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False

    async def send_command(self, command: str, **kwargs):
        """发送命令到服务器"""
        if not self.websocket:
            print("❌ WebSocket未连接")
            return None

        message = {"command": command, **kwargs}
        await self.websocket.send(json.dumps(message))
        print(f"📤 发送命令: {command} {kwargs}")

        # 等待响应
        try:
            response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            response_data = json.loads(response)
            print(f"📥 收到响应: {response_data}")
            return response_data
        except asyncio.TimeoutError:
            print("⏰ 响应超时")
            return None
        except Exception as e:
            print(f"❌ 接收响应失败: {e}")
            return None

    async def subscribe(self, stream_name: str):
        """订阅Stream"""
        return await self.send_command("subscribe", stream=stream_name)

    async def unsubscribe(self, stream_name: str):
        """取消订阅Stream"""
        return await self.send_command("unsubscribe", stream=stream_name)

    async def list_subscriptions(self):
        """列出订阅"""
        return await self.send_command("list_subscriptions")

    async def ping(self):
        """发送ping"""
        return await self.send_command("ping")

    async def get_stats(self):
        """获取服务统计"""
        return await self.send_command("get_stats")

    async def receive_messages(self, timeout: int = 30):
        """接收消息"""
        print(f"👂 开始接收消息，超时: {timeout}秒")
        self.running = True
        start_time = datetime.now()

        try:
            while self.running:
                try:
                    # 设置超时
                    response = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    message = json.loads(response)
                    self.received_messages.append(message)

                    message_type = message.get("type", "unknown")
                    timestamp = message.get("timestamp", "")

                    # 根据不同消息类型处理
                    if message_type == "stream_message":
                        stream = message.get("stream", "")
                        event_type = message.get("event_type", "")
                        print(f"📨 实时消息 [{stream}] {event_type} - {timestamp}")
                        # 打印消息摘要
                        data = message.get("data", {})
                        if isinstance(data, dict):
                            summary = {k: v for k, v in data.items() if k in ["event_type", "subject_key", "stock_id"]}
                            if summary:
                                print(f"  摘要: {summary}")

                    elif message_type == "heartbeat":
                        print(f"❤️  心跳 - {timestamp}")

                    elif message_type == "pong":
                        print(f"🏓 Pong - {timestamp}")

                    elif message_type == "subscription":
                        status = message.get("status", "")
                        stream = message.get("stream", "")
                        print(f"📝 订阅状态: {status} {stream}")

                    else:
                        print(f"📥 收到消息 [{message_type}]: {message}")

                    # 检查超时
                    elapsed = (datetime.now() - start_time).seconds
                    if elapsed >= timeout:
                        print(f"⏰ 接收超时 ({timeout}秒)")
                        break

                except asyncio.TimeoutError:
                    # 超时正常，继续等待
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print("🔌 连接已关闭")
                    break
                except Exception as e:
                    print(f"❌ 接收消息错误: {e}")
                    break

        except Exception as e:
            print(f"❌ 接收消息失败: {e}")

        self.running = False
        print(f"🛑 停止接收消息，共收到 {len(self.received_messages)} 条消息")

    async def run_test_scenario(self):
        """运行测试场景"""
        print("\n" + "="*60)
        print("实时推送服务客户端测试")
        print("="*60)

        # 1. 连接
        if not await self.connect():
            return False

        print("\n1. ✅ 连接测试通过")

        # 2. Ping测试
        print("\n2. 🏓 Ping测试")
        ping_result = await self.ping()
        if ping_result and ping_result.get("type") == "pong":
            print("✅ Ping测试通过")
        else:
            print("❌ Ping测试失败")

        # 3. 订阅测试
        print("\n3. 📝 订阅测试")
        streams_to_test = ["stream:event:feed", "stream:theme:feed"]

        for stream in streams_to_test:
            print(f"\n  订阅 {stream}")
            result = await self.subscribe(stream)
            if result and result.get("type") == "subscription" and result.get("status") == "subscribed":
                print(f"  ✅ 订阅成功: {stream}")
            else:
                print(f"  ❌ 订阅失败: {stream}")

        # 4. 列出订阅
        print("\n4. 📋 列出订阅")
        subscriptions = await self.list_subscriptions()
        if subscriptions and subscriptions.get("type") == "subscription_list":
            subs = subscriptions.get("subscriptions", [])
            print(f"  当前订阅: {subs}")
        else:
            print("  ❌ 获取订阅列表失败")

        # 5. 获取统计信息
        print("\n5. 📊 获取统计信息")
        stats = await self.get_stats()
        if stats and stats.get("type") == "service_stats":
            print(f"  服务统计: {json.dumps(stats.get('stats', {}), indent=2, ensure_ascii=False)}")
        else:
            print("  ❌ 获取统计信息失败")

        # 6. 接收实时消息
        print("\n6. 📨 接收实时消息测试")
        print("   等待10秒接收实时消息...")
        print("   (请确保有事件正在被推送到Stream)")

        # 启动消息接收任务
        receive_task = asyncio.create_task(self.receive_messages(timeout=10))

        # 同时发送一些测试命令
        await asyncio.sleep(2)
        await self.ping()
        await asyncio.sleep(2)

        # 等待接收任务完成
        await receive_task

        # 7. 取消订阅
        print("\n7. 📝 取消订阅测试")
        for stream in streams_to_test:
            result = await self.unsubscribe(stream)
            if result and result.get("type") == "subscription" and result.get("status") == "unsubscribed":
                print(f"  ✅ 取消订阅成功: {stream}")
            else:
                print(f"  ❌ 取消订阅失败: {stream}")

        # 8. 最终统计
        print("\n8. 📈 测试总结")
        print(f"   共收到消息数: {len(self.received_messages)}")
        print(f"   消息类型统计:")
        type_counts = {}
        for msg in self.received_messages:
            msg_type = msg.get("type", "unknown")
            type_counts[msg_type] = type_counts.get(msg_type, 0) + 1

        for msg_type, count in type_counts.items():
            print(f"     - {msg_type}: {count}")

        return len(self.received_messages) > 0

    async def close(self):
        """关闭连接"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            print("🔌 连接已关闭")


async def test_websocket_connection():
    """测试WebSocket连接"""
    print("🔗 测试WebSocket连接...")

    # 尝试不同的连接选项
    test_urls = [
        "ws://localhost:8000/ws/realtime",
        "ws://127.0.0.1:8000/ws/realtime"
    ]

    for url in test_urls:
        print(f"\n尝试连接: {url}")
        try:
            client = RealtimeClient(url)
            if await client.connect():
                await client.close()
                print(f"✅ 连接成功: {url}")
                return url
            else:
                print(f"❌ 连接失败: {url}")
        except Exception as e:
            print(f"❌ 连接异常: {e}")

    return None


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="实时推送服务客户端测试")
    parser.add_argument("--url", default="ws://localhost:8000/ws/realtime", help="WebSocket服务器URL")
    parser.add_argument("--test", action="store_true", help="运行完整测试场景")
    parser.add_argument("--subscribe", help="订阅指定Stream")
    parser.add_argument("--listen", type=int, default=30, help="监听消息的秒数")

    args = parser.parse_args()

    if args.test:
        # 运行完整测试场景
        client = RealtimeClient(args.url)
        try:
            success = await client.run_test_scenario()
            if success:
                print("\n🎉 客户端测试通过！")
                return 0
            else:
                print("\n⚠️  客户端测试部分失败")
                return 1
        finally:
            await client.close()

    elif args.subscribe:
        # 订阅指定Stream并监听
        client = RealtimeClient(args.url)
        try:
            if await client.connect():
                await client.subscribe(args.subscribe)
                print(f"👂 开始监听 {args.subscribe}，时长 {args.listen}秒")
                await client.receive_messages(timeout=args.listen)
            else:
                print("❌ 连接失败")
                return 1
        finally:
            await client.close()

    else:
        # 仅测试连接
        url = await test_websocket_connection()
        if url:
            print(f"\n✅ WebSocket服务可用: {url}")
            print("\n使用 --test 运行完整测试场景")
            print(f"使用 --subscribe stream:event:feed --listen 30 订阅并监听消息")
            return 0
        else:
            print("\n❌ WebSocket服务不可用")
            print("请确保:")
            print("1. Frontend BFF服务正在运行: uvicorn app:app --host 0.0.0.0 --port 8000")
            print("2. Redis服务正在运行")
            print("3. 实时推送服务已正确集成")
            return 1


if __name__ == "__main__":
    # 切换到项目根目录
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
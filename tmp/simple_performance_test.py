#!/usr/bin/env python3
"""
简单性能测试脚本 - 基于run_full_chain_100_to_decision_with_progress.py
专注于性能测量，避免复杂逻辑
"""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime

import asyncpg
import redis.asyncio as redis

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway
from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
from database_service.streams.gateway_integration import get_gateway
from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor
from database_service.streams.stream_config import EnhancedDatabaseConfig, RedisStreamConfig, StreamDefinition, StreamPriority

class SimplePerformanceTest:
    """简单性能测试"""
    
    def __init__(self, total_messages: int = 10, concurrent_users: int = 2):
        self.total_messages = total_messages
        self.concurrent_users = concurrent_users
        self.results = []
        self.start_time = None
        self.end_time = None
        
    async def _get_news_directly(self, conn: asyncpg.Connection, news_id: str) -> Dict[str, Any]:
        """直接查询数据库，绕过有问题的get_news方法"""
        try:
            row = await conn.fetchrow("""
                SELECT
                    id, news_id, title, content, source,
                    publish_date, publish_time, market, url,
                    created_at, updated_at
                FROM news_raw
                WHERE news_id = $1
            """, news_id)
            
            if row:
                result = dict(row)
                # 添加默认值以匹配期望的格式
                result['keywords'] = []
                result['metadata'] = {}
                return result
            return None
        except Exception as e:
            print(f"直接查询新闻失败 {news_id}: {e}")
            return None
    
    async def run_test(self):
        """运行简单性能测试"""
        print(f"开始简单性能测试: {self.total_messages}条消息, {self.concurrent_users}并发")
        self.start_time = time.time()
        
        # 设置环境
        run_id = uuid.uuid4().hex[:8]
        batch_id = f"perf_simple_{run_id}"
        
        # 初始化增强配置
        cfg = EnhancedDatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data"),
            postgres_username=os.getenv("POSTGRES_USER", "postgres"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        )
        cfg.redis.enabled = True
        # 禁用Stream监控以避免WRONGTYPE错误
        cfg.redis_stream.enable_monitoring = False
        init_config(cfg)
        DatabaseGateway._instance = None
        
        # 获取原始gateway，避免使用增强版gateway的Stream监控
        from database_service.gateway import get_gateway as get_original_gateway
        base_gateway = await get_original_gateway()

        # 临时修改gateway_integration的get_gateway函数，使其返回原始gateway
        # 这样ThemeProcessor初始化时会使用原始gateway而不是增强版gateway
        import database_service.streams.gateway_integration as gateway_integration
        original_get_gateway = gateway_integration.get_gateway

        async def patched_get_gateway(enable_retry=True, retry_config=None):
            return base_gateway

        gateway_integration.get_gateway = patched_get_gateway
        
        # 初始化Redis
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
        )
        await redis_client.ping()
        
        stream_bus = UnifiedRedisStreamBus(redis_client, cfg)
        
        # 初始化Streams
        raw_stream = "stream:news:raw"
        structured_stream = "stream:events:structured"
        decision_stream = "stream:events:decision"
        dead_letter_stream = "stream:dead:letter"
        
        # 正确初始化顺序
        await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")
        for stream_name in (raw_stream, structured_stream, decision_stream, dead_letter_stream):
            await redis_client.delete(stream_name)
        await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")
        
        # 初始化处理器
        news_handler = NewsStreamHandler(
            stream_bus=stream_bus,
            database_gateway=base_gateway,
            config={
                "consumer_group": "news_storage_handlers",
                "stream_name": "news_raw",
                "batch_size": 5,
                "block_time": 500,
            },
        )
        
        consumer_group = f"theme_processors_simple_{run_id}"
        consumer_name = f"tp_simple_{run_id}"

        theme_processor = ThemeProcessor(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            enable_classification_first=False,
            consumer_name=consumer_name,
            config={
                "stream_structured": structured_stream,
                "stream_decision": decision_stream,
                "stream_dead_letter": dead_letter_stream,
                "consumer_group": consumer_group,
                "structured_batch_size": 5,
                "structured_block_time": 500,
            },
            db_manager=base_gateway,  # 传递原始gateway作为db_manager
        )
        
        # 启动服务
        await news_handler.start_storage_service()
        ok = await theme_processor.initialize()
        if not ok:
            raise RuntimeError("theme_processor 初始化失败")
        await theme_processor.start()
        
        print("服务启动完成，开始测试...")
        
        # 简单的测试消息
        test_messages = [
            {"id": f"{batch_id}_{i:03d}", "content": f"测试消息{i}: AI眼镜厂商发布新品", "title": f"测试标题{i}"}
            for i in range(1, self.total_messages + 1)
        ]
        
        # 运行测试
        success_count = 0
        fail_count = 0
        
        for i, msg in enumerate(test_messages, 1):
            try:
                msg_start = time.time()
                
                # 发布到stream
                payload = {
                    "_t": "news",
                    "_v": 2,
                    "id": msg["id"],
                    "t": msg["title"],
                    "c": msg["content"],
                    "s": "perf_test",
                    "d": "2026-04-12",
                    "tm": "00:00:00",
                    "_b": batch_id,
                    "_s": i,
                }
                
                await stream_bus.publish_to_stream("news_raw", {"payload": payload})
                publish_time = time.time() - msg_start
                
                print(f"[{i}/{self.total_messages}] 消息发布成功: {msg['id']} (耗时: {publish_time:.3f}s)")
                success_count += 1
                
                self.results.append({
                    "message_id": msg["id"],
                    "status": "success",
                    "publish_time": publish_time,
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                print(f"[{i}/{self.total_messages}] 消息发布失败: {e}")
                fail_count += 1
                self.results.append({
                    "message_id": msg.get("id", f"unknown_{i}"),
                    "status": "failed",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            
            # 简单延迟
            await asyncio.sleep(0.1)
        
        # 等待一段时间让消息处理
        print(f"等待消息处理完成...")
        await asyncio.sleep(5.0)
        
        # 停止服务
        await news_handler.stop_storage_service()
        await theme_processor.stop()
        
        # 清理
        await redis_client.delete(raw_stream, structured_stream, decision_stream, dead_letter_stream)
        if hasattr(base_gateway, "close"):
            await base_gateway.close()

        # 恢复原始get_gateway函数
        gateway_integration.get_gateway = original_get_gateway
        
        self.end_time = time.time()
        
        # 生成报告
        total_time = self.end_time - self.start_time
        throughput = success_count / total_time if total_time > 0 else 0
        
        report = {
            "test_config": {
                "total_messages": self.total_messages,
                "concurrent_users": self.concurrent_users,
                "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                "end_time": datetime.fromtimestamp(self.end_time).isoformat(),
                "total_duration": total_time,
            },
            "results": {
                "success_count": success_count,
                "fail_count": fail_count,
                "success_rate": success_count / self.total_messages if self.total_messages > 0 else 0,
                "throughput": throughput,
            },
            "detailed_results": self.results
        }
        
        print(f"\n=== 性能测试结果 ===")
        print(f"总消息数: {self.total_messages}")
        print(f"成功数: {success_count}")
        print(f"失败数: {fail_count}")
        print(f"成功率: {report['results']['success_rate']:.2%}")
        print(f"吞吐量: {throughput:.2f} 消息/秒")
        print(f"总耗时: {total_time:.2f} 秒")
        
        return report

async def main():
    """主函数"""
    # 检查环境变量
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("警告: DEEPSEEK_API_KEY 环境变量未设置")
        env_file = PROJECT_ROOT / ".env.theme"
        if env_file.exists():
            content = env_file.read_text()
            for line in content.splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip()
                    print(f"已从.env.theme文件读取DEEPSEEK_API_KEY")
                    break
    
    # 运行测试
    tester = SimplePerformanceTest(total_messages=5, concurrent_users=1)
    
    try:
        report = await tester.run_test()
        
        # 保存报告
        report_file = PROJECT_ROOT / f"tmp/simple_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n测试报告已保存: {report_file}")
        
        return report
        
    except Exception as e:
        print(f"性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    report = asyncio.run(main())
    if report:
        print("\n简单性能测试执行完成")
    else:
        print("\n简单性能测试执行失败")
        sys.exit(1)

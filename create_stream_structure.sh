#!/usr/bin/env python3
"""
Redis Stream 文件生成脚本
用于批量生成Stream集成所需的所有文件
"""
import os
import sys
from pathlib import Path
from typing import Dict, List
import argparse

class StreamFileGenerator:
    """Stream文件生成器"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir or ".")
        self.templates_dir = self.base_dir / "templates"
        
        # 确保模板目录存在
        self.templates_dir.mkdir(exist_ok=True)
    
    def create_all_files(self, overwrite: bool = False):
        """创建所有文件"""
        print("🚀 开始生成Redis Stream集成文件...")
        print("=" * 60)
        
        # 1. 创建目录结构
        self.create_directories()
        
        # 2. 生成Stream核心文件
        self.generate_stream_files(overwrite)
        
        # 3. 生成服务客户端文件
        self.generate_service_files(overwrite)
        
        # 4. 更新现有配置文件
        self.update_existing_files(overwrite)
        
        # 5. 创建启动脚本
        self.generate_scripts(overwrite)
        
        # 6. 创建测试文件
        self.generate_test_files(overwrite)
        
        # 7. 更新依赖文件
        self.update_requirements(overwrite)
        
        print("=" * 60)
        print("✅ 所有文件生成完成！")
        print("📁 生成的文件位于: database_service/streams/ 和 database_service/services/")
        print("📝 需要手动更新: database_service/config.py (添加Stream配置)")
        
    def create_directories(self):
        """创建所有必要的目录"""
        directories = [
            "database_service/streams",
            "database_service/streams/producers",
            "database_service/streams/consumers", 
            "database_service/streams/handlers",
            "database_service/streams/utils",
            "database_service/services",
            "scripts",
            "tests/streams"
        ]
        
        for dir_path in directories:
            path = self.base_dir / dir_path
            path.mkdir(parents=True, exist_ok=True)
            
            # 创建 __init__.py 文件
            init_file = path / "__init__.py"
            init_file.touch(exist_ok=True)
            
            print(f"📁 创建目录: {dir_path}")
    
    def generate_stream_files(self, overwrite: bool):
        """生成Stream核心文件"""
        print("\n📦 生成Stream核心文件...")
        
        # Stream管理器
        self.create_file(
            "database_service/streams/stream_manager.py",
            self._get_stream_manager_template(),
            overwrite
        )
        
        # 消费者基类
        self.create_file(
            "database_service/streams/base_consumer.py",
            self._get_base_consumer_template(),
            overwrite
        )
        
        # 生产者文件
        producers = ["news", "event", "theme"]
        for producer in producers:
            self.create_file(
                f"database_service/streams/producers/{producer}_producer.py",
                self._get_producer_template(producer),
                overwrite
            )
        
        # 消费者文件
        consumers = ["news", "event", "theme"]
        for consumer in consumers:
            self.create_file(
                f"database_service/streams/consumers/{consumer}_consumer.py",
                self._get_consumer_template(consumer),
                overwrite
            )
        
        # 消费者管理器
        self.create_file(
            "database_service/streams/consumers/consumer_manager.py",
            self._get_consumer_manager_template(),
            overwrite
        )
        
        # 处理器文件
        handlers = ["model_service", "theme_service", "data_service"]
        for handler in handlers:
            self.create_file(
                f"database_service/streams/handlers/{handler}_handler.py",
                self._get_handler_template(handler),
                overwrite
            )
        
        # 工具文件
        utils = ["message_serializer", "retry_manager", "dead_letter_queue"]
        for util in utils:
            self.create_file(
                f"database_service/streams/utils/{util}.py",
                self._get_util_template(util),
                overwrite
            )
        
        # Stream模块的__init__.py
        self.create_file(
            "database_service/streams/__init__.py",
            self._get_streams_init_template(),
            overwrite
        )
    
    def generate_service_files(self, overwrite: bool):
        """生成服务客户端文件"""
        print("\n🔧 生成服务客户端文件...")
        
        services = ["model_service", "theme_service", "crawler_service"]
        for service in services:
            self.create_file(
                f"database_service/services/{service}_client.py",
                self._get_service_client_template(service),
                overwrite
            )
        
        # 服务模块的__init__.py
        self.create_file(
            "database_service/services/__init__.py",
            self._get_services_init_template(),
            overwrite
        )
    
    def update_existing_files(self, overwrite: bool):
        """更新现有配置文件"""
        print("\n🔄 更新现有配置文件...")
        
        # 更新config.py
        self.create_file(
            "database_service/config.py",
            self._get_updated_config_template(),
            overwrite
        )
        
        # 更新interface.py
        interface_path = self.base_dir / "database_service" / "interface.py"
        if interface_path.exists():
            # 如果文件存在，我们创建更新示例
            self.create_file(
                "database_service/interface_stream_example.py",
                self._get_interface_update_template(),
                overwrite
            )
            print("📝 创建了 interface_stream_example.py 作为更新参考")
        
        # 更新gateway.py示例
        self.create_file(
            "database_service/gateway_stream_example.py",
            self._get_gateway_update_template(),
            overwrite
        )
        
        # 更新factory.py示例
        self.create_file(
            "database_service/factory_stream_example.py",
            self._get_factory_update_template(),
            overwrite
        )
        
        # 更新redis_event_bus.py
        event_bus_path = self.base_dir / "database_service" / "managers" / "redis_event_bus.py"
        if event_bus_path.exists():
            self.create_file(
                "database_service/managers/redis_event_bus_stream.py",
                self._get_event_bus_update_template(),
                overwrite
            )
            print("📝 创建了 redis_event_bus_stream.py 作为增强版参考")
    
    def generate_scripts(self, overwrite: bool):
        """生成启动脚本"""
        print("\n🚀 生成启动脚本...")
        
        scripts = ["start_stream_consumers", "check_stream_health", "cleanup_streams", "stream_migrator"]
        for script in scripts:
            self.create_file(
                f"scripts/{script}.py",
                self._get_script_template(script),
                overwrite
            )
    
    def generate_test_files(self, overwrite: bool):
        """生成测试文件"""
        print("\n🧪 生成测试文件...")
        
        tests = ["test_stream_manager", "test_news_consumer", "test_stream_integration"]
        for test in tests:
            self.create_file(
                f"tests/streams/{test}.py",
                self._get_test_template(test),
                overwrite
            )
    
    def update_requirements(self, overwrite: bool):
        """更新requirements.txt"""
        print("\n📦 更新依赖文件...")
        
        requirements_path = self.base_dir / "requirements.txt"
        if requirements_path.exists():
            with open(requirements_path, 'a', encoding='utf-8') as f:
                f.write("\n# Redis Stream 集成依赖\n")
                f.write("aioredis>=2.0.0\n")
                f.write("aiohttp>=3.8.0\n")
                f.write("pydantic>=2.0.0\n")
                f.write("orjson>=3.8.0\n")
            print("✅ 已更新 requirements.txt")
        else:
            self.create_file(
                "requirements.txt",
                self._get_requirements_template(),
                overwrite
            )
    
    def create_file(self, file_path: str, content: str, overwrite: bool = False):
        """创建文件"""
        full_path = self.base_dir / file_path
        
        if full_path.exists() and not overwrite:
            print(f"⏭️  文件已存在，跳过: {file_path}")
            return
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"✅ 创建文件: {file_path}")
    
    # 模板方法（因篇幅限制，这里只展示关键模板）
    def _get_stream_manager_template(self) -> str:
        return '''"""
Redis Stream 管理器 - 统一管理所有Stream操作
"""
import aioredis
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class StreamMessage:
    """Stream消息封装"""
    id: str
    stream: str
    data: Dict[str, Any]
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None

class RedisStreamManager:
    """Redis Stream管理器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.connected = False
    
    async def connect(self):
        """连接Redis"""
        if not self.connected:
            self.redis = await aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=50
            )
            self.connected = True
    
    async def ensure_stream(self, stream_name: str, max_len: int = 10000):
        """确保Stream存在"""
        await self.connect()
        # 发送一条初始化消息，然后删除
        await self.redis.xadd(stream_name, {"init": "true"}, maxlen=1)
        await self.redis.xtrim(stream_name, maxlen=0, approximate=False)
    
    async def create_consumer_group(self, stream: str, group: str):
        """创建消费者组"""
        await self.connect()
        try:
            await self.redis.xgroup_create(
                stream, group, id="0", mkstream=True
            )
            print(f"✅ Created consumer group: {group} for stream: {stream}")
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
    
    async def publish(self, stream: str, data: Dict, 
                     max_len: int = None) -> str:
        """发布消息到Stream"""
        await self.connect()
        
        message = {
            "payload": json.dumps(data, ensure_ascii=False),
            "published_at": datetime.now().isoformat(),
            "source": "database_service"
        }
        
        return await self.redis.xadd(
            stream,
            message,
            maxlen=max_len or 10000,
            approximate=True
        )
    
    async def consume(self, group: str, consumer: str,
                     stream: str, count: int = 10,
                     block_ms: int = 5000) -> List[StreamMessage]:
        """消费消息"""
        await self.connect()
        
        result = await self.redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=count,
            block=block_ms
        )
        
        if not result:
            return []
        
        messages = []
        for stream_name, stream_messages in result:
            for msg_id, msg_data in stream_messages:
                data = json.loads(msg_data["payload"])
                messages.append(StreamMessage(
                    id=msg_id,
                    stream=stream_name,
                    data=data,
                    timestamp=datetime.fromisoformat(msg_data["published_at"])
                ))
        
        return messages
    
    async def ack(self, stream: str, group: str, message_id: str):
        """确认消息处理完成"""
        await self.connect()
        await self.redis.xack(stream, group, message_id)
    
    async def batch_ack(self, stream: str, group: str, message_ids: List[str]):
        """批量确认消息"""
        await self.connect()
        pipe = self.redis.pipeline()
        for msg_id in message_ids:
            pipe.xack(stream, group, msg_id)
        await pipe.execute()
    
    async def get_pending_messages(self, stream: str, group: str) -> List[Dict]:
        """获取待处理消息"""
        await self.connect()
        pending = await self.redis.xpending(stream, group)
        return pending
    
    async def get_stream_info(self, stream: str) -> Dict:
        """获取Stream信息"""
        await self.connect()
        try:
            info = await self.redis.xinfo_stream(stream)
            return {
                "length": info["length"],
                "groups": info["groups"],
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry")
            }
        except aioredis.ResponseError:
            return {"error": "Stream does not exist"}
    
    async def claim_stuck_messages(self, stream: str, group: str,
                                 consumer: str, min_idle_time: int = 60000):
        """认领卡住的消息"""
        await self.connect()
        pending = await self.get_pending_messages(stream, group)
        
        if pending:
            # 找出空闲时间过长的消息
            stuck_messages = [
                msg for msg in pending 
                if msg["idle"] > min_idle_time
            ]
            
            if stuck_messages:
                message_ids = [msg["message_id"] for msg in stuck_messages]
                result = await self.redis.xclaim(
                    stream, group, consumer, min_idle_time,
                    message_ids
                )
                return result
        
        return []
'''
    
    def _get_base_consumer_template(self) -> str:
        return '''"""
消费者基类 - 所有消费者的父类
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseStreamConsumer(ABC):
    """Stream消费者基类"""
    
    def __init__(self, stream_manager, config: Dict):
        self.stream_manager = stream_manager
        self.config = config
        
        # 消费者配置
        self.group_name = config.get("group_name", "default_group")
        self.consumer_name = config.get("consumer_name", "consumer_1")
        self.stream_name = config.get("stream_name")
        self.batch_size = config.get("batch_size", 10)
        self.block_time_ms = config.get("block_time_ms", 5000)
        self.max_retries = config.get("max_retries", 3)
        
        # 运行状态
        self.running = False
        self.processed_count = 0
        self.error_count = 0
        self.last_processed_time = None
        
        # 统计信息
        self.metrics = {
            "total_processed": 0,
            "total_errors": 0,
            "avg_processing_time": 0,
            "last_success_time": None
        }
    
    async def start(self):
        """启动消费者"""
        if self.running:
            logger.warning(f"Consumer {self.consumer_name} is already running")
            return
        
        # 创建消费者组
        await self.stream_manager.create_consumer_group(
            self.stream_name, self.group_name
        )
        
        self.running = True
        logger.info(f"🚀 Starting consumer {self.consumer_name} for stream {self.stream_name}")
        
        while self.running:
            try:
                await self._consume_loop()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer {self.consumer_name} error: {e}")
                await asyncio.sleep(1)  # 避免快速重试循环
    
    async def stop(self):
        """停止消费者"""
        self.running = False
        logger.info(f"🛑 Stopping consumer {self.consumer_name}")
    
    async def _consume_loop(self):
        """消费循环"""
        messages = await self.stream_manager.consume(
            group=self.group_name,
            consumer=self.consumer_name,
            stream=self.stream_name,
            count=self.batch_size,
            block_ms=self.block_time_ms
        )
        
        if messages:
            logger.debug(f"📨 {self.consumer_name} received {len(messages)} messages")
            
            # 批量处理消息
            success_ids = []
            for message in messages:
                try:
                    start_time = datetime.now()
                    
                    # 处理消息
                    success = await self.process_message(message)
                    
                    processing_time = (datetime.now() - start_time).total_seconds() * 1000
                    
                    if success:
                        success_ids.append(message.id)
                        self.processed_count += 1
                        self.last_processed_time = datetime.now()
                        
                        logger.debug(f"✅ Processed message {message.id} in {processing_time:.0f}ms")
                    else:
                        self.error_count += 1
                        logger.warning(f"⚠️ Failed to process message {message.id}")
                
                except Exception as e:
                    self.error_count += 1
                    logger.error(f"❌ Error processing message {message.id}: {e}")
                    
                    # 发送到死信队列
                    await self._send_to_dead_letter(message, str(e))
            
            # 批量ACK成功的消息
            if success_ids:
                await self.stream_manager.batch_ack(
                    self.stream_name, self.group_name, success_ids
                )
                
                logger.info(f"✅ {self.consumer_name} processed {len(success_ids)}/{len(messages)} messages")
    
    @abstractmethod
    async def process_message(self, message) -> bool:
        """处理消息 - 子类必须实现"""
        pass
    
    async def _send_to_dead_letter(self, message, error: str):
        """发送到死信队列"""
        try:
            dead_letter_data = {
                "original_message": message.data,
                "original_stream": message.stream,
                "original_id": message.id,
                "error": error,
                "failed_at": datetime.now().isoformat(),
                "consumer": self.consumer_name
            }
            
            await self.stream_manager.publish(
                "stream:dead:letter",
                dead_letter_data
            )
            
            logger.debug(f"📤 Sent message {message.id} to dead letter queue")
        except Exception as e:
            logger.error(f"Failed to send to dead letter: {e}")
    
    def get_metrics(self) -> Dict:
        """获取消费者指标"""
        return {
            "consumer_name": self.consumer_name,
            "stream_name": self.stream_name,
            "running": self.running,
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "last_processed_time": self.last_processed_time.isoformat() if self.last_processed_time else None,
            **self.metrics
        }
'''
    
    def _get_consumer_template(self, consumer_type: str) -> str:
        class_name = f"{consumer_type.capitalize()}StreamConsumer"
        
        if consumer_type == "news":
            return f'''"""
新闻Stream消费者 - 处理原始新闻流
"""
import asyncio
import aiohttp
import logging
from typing import Dict, List
from datetime import datetime

from ..base_consumer import BaseStreamConsumer
from ...services.model_service_client import ModelServiceClient

logger = logging.getLogger(__name__)

class {class_name}(BaseStreamConsumer):
    """新闻Stream消费者"""
    
    def __init__(self, stream_manager, config: Dict):
        super().__init__(stream_manager, config)
        
        # 模型服务客户端
        self.model_client = ModelServiceClient(
            config.get("model_service_url", "http://localhost:8001")
        )
        
        # 处理配置
        self.enable_batch_processing = config.get("enable_batch", True)
        self.batch_timeout_seconds = config.get("batch_timeout", 30)
        
        # 批量处理缓冲区
        self.batch_buffer = []
        self.batch_lock = asyncio.Lock()
    
    async def process_message(self, message) -> bool:
        """处理新闻消息"""
        try:
            news_data = message.data
            
            # 验证消息格式
            if not self._validate_news_data(news_data):
                logger.warning(f"Invalid news data format: {{news_data.get('id', 'unknown')}}")
                return False
            
            # 调用模型服务提取事件
            extraction_result = await self.model_client.extract_event(
                title=news_data["title"],
                content=news_data["content"],
                keywords=news_data.get("keywords", [])
            )
            
            if not extraction_result.get("success"):
                logger.error(f"AI extraction failed: {{extraction_result.get('error')}}")
                return False
            
            # 保存处理结果
            await self._save_processing_result(
                news_id=news_data["id"],
                extraction_result=extraction_result
            )
            
            # 根据分类发布到不同Stream
            classification = extraction_result["data"].get("classification", "normal")
            
            if classification == "major":
                # 发布到重大事件流
                await self.stream_manager.publish(
                    "stream:events:major",
                    {{
                        "news_id": news_data["id"],
                        "extraction_result": extraction_result,
                        "classified_at": datetime.now().isoformat()
                    }}
                )
            else:
                # 发布到普通事件流
                await self.stream_manager.publish(
                    "stream:events:normal",
                    {{
                        "news_id": news_data["id"],
                        "extraction_result": extraction_result,
                        "classified_at": datetime.now().isoformat()
                    }}
                )
            
            return True
            
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error processing news: {{e}}")
            return False
        except Exception as e:
            logger.error(f"Error processing news message: {{e}}")
            return False
    
    def _validate_news_data(self, news_data: Dict) -> bool:
        """验证新闻数据格式"""
        required_fields = ["id", "title", "content"]
        for field in required_fields:
            if field not in news_data:
                return False
        
        # 验证内容长度
        if len(news_data.get("content", "")) < 10:
            return False
        
        return True
    
    async def _save_processing_result(self, news_id: str, extraction_result: Dict):
        """保存处理结果到数据库"""
        # 这里可以通过DatabaseGateway保存结果
        # 简化实现，实际需要集成现有数据库管理器
        logger.info(f"Saved processing result for news {{news_id}}")
        return True
    
    async def process_batch(self, messages: List) -> List[str]:
        """批量处理消息（可选优化）"""
        if not self.enable_batch_processing:
            return []
        
        async with self.batch_lock:
            # 添加到缓冲区
            self.batch_buffer.extend(messages)
            
            # 检查是否达到批量处理条件
            if len(self.batch_buffer) >= self.batch_size:
                batch_to_process = self.batch_buffer[:self.batch_size]
                self.batch_buffer = self.batch_buffer[self.batch_size:]
                
                # 批量处理
                return await self._process_batch_internal(batch_to_process)
            
            return []
    
    async def _process_batch_internal(self, messages: List) -> List[str]:
        """内部批量处理方法"""
        # 批量调用模型服务
        batch_requests = []
        for message in messages:
            news_data = message.data
            batch_requests.append({{
                "title": news_data["title"],
                "content": news_data["content"],
                "keywords": news_data.get("keywords", [])
            }})
        
        try:
            # 批量调用模型服务
            batch_results = await self.model_client.batch_extract(batch_requests)
            
            success_ids = []
            for i, result in enumerate(batch_results):
                if result.get("success"):
                    success_ids.append(messages[i].id)
                    
                    # 发布处理结果
                    classification = result["data"].get("classification", "normal")
                    target_stream = "stream:events:major" if classification == "major" else "stream:events:normal"
                    
                    await self.stream_manager.publish(target_stream, {{
                        "news_id": messages[i].data["id"],
                        "extraction_result": result,
                        "classified_at": datetime.now().isoformat()
                    }})
            
            return success_ids
            
        except Exception as e:
            logger.error(f"Batch processing failed: {{e}}")
            return []
'''
        else:
            return f'''"""
{consumer_type.capitalize()} Stream消费者
"""
import logging
from datetime import datetime

from ..base_consumer import BaseStreamConsumer

logger = logging.getLogger(__name__)

class {class_name}(BaseStreamConsumer):
    """{consumer_type.capitalize()} Stream消费者"""
    
    def __init__(self, stream_manager, config: Dict):
        super().__init__(stream_manager, config)
    
    async def process_message(self, message) -> bool:
        """处理{consumer_type}消息"""
        try:
            logger.info(f"Processing {{consumer_type}} message: {{message.id}}")
            
            # TODO: 实现具体的业务逻辑
            # 1. 提取消息数据
            # 2. 调用相关服务
            # 3. 更新数据库
            # 4. 返回处理结果
            
            logger.info(f"✅ Successfully processed {{consumer_type}} message: {{message.id}}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process {{consumer_type}} message {{message.id}}: {{e}}")
            return False
'''
    
    def _get_updated_config_template(self) -> str:
        return '''"""
扩展现有配置，添加Redis Stream配置
"""
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class RedisStreamConfig:
    """Redis Stream配置"""
    
    # 基础配置
    enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    
    # Stream定义
    streams: Dict[str, str] = field(default_factory=lambda: {
        "news_raw": "stream:news:raw",
        "events_major": "stream:events:major",
        "events_normal": "stream:events:normal",
        "themes_updates": "stream:themes:updates",
        "dead_letter": "stream:dead:letter"
    })
    
    # 消费者组配置
    consumer_groups: Dict[str, Dict] = field(default_factory=lambda: {
        "news_processors": {
            "stream": "news_raw",
            "workers": 3,
            "batch_size": 10,
            "block_time_ms": 5000
        },
        "major_workers": {
            "stream": "events_major",
            "workers": 2,
            "batch_size": 5,
            "block_time_ms": 10000  # 深度分析需要更长时间
        },
        "theme_workers": {
            "stream": "events_normal",
            "workers": 4,
            "batch_size": 20,
            "block_time_ms": 5000
        }
    })
    
    # 性能配置
    max_stream_length: int = 10000
    enable_compression: bool = True
    compression_threshold: int = 1024  # 1KB
    
    # 监控配置
    enable_monitoring: bool = True
    metrics_interval: int = 30  # 秒

@dataclass
class ExternalServiceConfig:
    """外部服务配置"""
    
    model_service: Dict = field(default_factory=lambda: {
        "url": "http://localhost:8001",
        "timeout": 30,
        "retry_count": 3,
        "retry_delay": 1.0
    })
    
    theme_service: Dict = field(default_factory=lambda: {
        "url": "http://localhost:8002",
        "timeout": 30,
        "retry_count": 3,
        "retry_delay": 1.0
    })

@dataclass
class DatabaseConfig:
    """主配置类 - 扩展现有配置"""
    
    # 原有字段（保持不变）
    postgres_url: str = "postgresql://user:pass@localhost/news_db"
    redis_url: str = "redis://localhost:6379/0"
    
    # 原有缓存配置
    cache_ttl: Dict = field(default_factory=lambda: {
        "theme_details": 3600,
        "news_details": 1800,
        "list_queries": 300
    })
    
    # 新增Stream配置
    redis_stream: RedisStreamConfig = field(default_factory=RedisStreamConfig)
    
    # 新增外部服务配置
    external_services: ExternalServiceConfig = field(default_factory=ExternalServiceConfig)
    
    # 功能开关（用于渐进迁移）
    enable_stream_processing: bool = True
    enable_legacy_event_bus: bool = False  # 保持旧版事件总线兼容
    dual_write_mode: bool = True  # 双写模式，同时写入Stream和List/PubSub
    
    # 性能调优
    max_connections: int = 50
    connection_timeout: int = 5
'''
    
    # 其他模板方法（因篇幅限制，这里只展示关键部分）
    def _get_service_client_template(self, service_type: str) -> str:
        # 返回服务客户端模板
        pass
    
    def _get_script_template(self, script_type: str) -> str:
        # 返回脚本模板
        pass
    
    def _get_requirements_template(self) -> str:
        return '''# 项目依赖
# 数据库
asyncpg>=0.27.0
sqlalchemy>=2.0.0
alembic>=1.12.0

# Redis
redis>=4.6.0
aioredis>=2.0.0

# HTTP客户端
aiohttp>=3.8.0
httpx>=0.24.0

# 数据处理
pandas>=2.0.0
numpy>=1.24.0

# 工具
pydantic>=2.0.0
python-dotenv>=1.0.0
orjson>=3.8.0

# 监控
prometheus-client>=0.17.0

# 测试
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-mock>=3.11.0

# Redis Stream 集成依赖
aioredis>=2.0.0
aiohttp>=3.8.0
pydantic>=2.0.0
orjson>=3.8.0
'''

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="生成Redis Stream集成文件")
    parser.add_argument("--base-dir", default=".", help="基础目录路径")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际创建文件")
    
    args = parser.parse_args()
    
    generator = StreamFileGenerator(args.base_dir)
    
    if args.dry_run:
        print("🧪 模拟运行模式 - 不会实际创建文件")
        print("📋 将创建的文件:")
        print("-" * 40)
        
        # 模拟文件结构
        files_to_create = [
            "database_service/streams/stream_manager.py",
            "database_service/streams/base_consumer.py",
            "database_service/streams/producers/news_producer.py",
            "database_service/streams/producers/event_producer.py",
            "database_service/streams/producers/theme_producer.py",
            "database_service/streams/consumers/news_consumer.py",
            "database_service/streams/consumers/event_consumer.py",
            "database_service/streams/consumers/theme_consumer.py",
            "database_service/streams/consumers/consumer_manager.py",
            "database_service/streams/handlers/model_service_handler.py",
            "database_service/streams/handlers/theme_service_handler.py",
            "database_service/streams/handlers/data_service_handler.py",
            "database_service/streams/utils/message_serializer.py",
            "database_service/streams/utils/retry_manager.py",
            "database_service/streams/utils/dead_letter_queue.py",
            "database_service/services/model_service_client.py",
            "database_service/services/theme_service_client.py",
            "database_service/services/crawler_service_client.py",
            "scripts/start_stream_consumers.py",
            "scripts/check_stream_health.py",
            "scripts/cleanup_streams.py",
            "scripts/stream_migrator.py",
            "tests/streams/test_stream_manager.py",
            "tests/streams/test_news_consumer.py",
            "tests/streams/test_stream_integration.py",
        ]
        
        for file in files_to_create:
            print(f"  📄 {file}")
        
        print("-" * 40)
        print(f"总计: {len(files_to_create)} 个文件")
        print("添加 '--overwrite' 参数来实际创建文件")
    else:
        generator.create_all_files(args.overwrite)

if __name__ == "__main__":
    main()
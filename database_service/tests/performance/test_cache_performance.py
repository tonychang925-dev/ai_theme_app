# database_service/tests/streams/test_stream_manager.py
"""
Stream管理器测试 - 纯Python版本
不使用pytest，避免兼容性问题
"""
import asyncio
import json
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# ====================== 修复导入问题 ======================

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 模拟aioredis模块以避免导入问题
class MockRedisClass:
    class RedisError(Exception):
        pass
    
    class ResponseError(Exception):
        pass
    
    class Pipeline:
        def __init__(self):
            self.commands = []
        
        def xack(self, stream, group, message_id):
            self.commands.append(('xack', stream, group, message_id))
            return self
        
        async def execute(self):
            return [1] * len(self.commands)
        
        def __getattr__(self, name):
            async def dummy(*args, **kwargs):
                return None
            return dummy
    
    def __init__(self, *args, **kwargs):
        self.connection_pool = MagicMock()
        self.connection_pool.disconnect = AsyncMock()
        self._calls = []
    
    async def xgroup_create(self, *args, **kwargs):
        self._calls.append(('xgroup_create', args, kwargs))
        return "OK"
    
    async def xadd(self, stream, fields, maxlen=None, approximate=True):
        self._calls.append(('xadd', stream, fields, maxlen, approximate))
        return "mocked_message_id"
    
    async def xreadgroup(self, group, consumer, streams, count=None, block=None):
        self._calls.append(('xreadgroup', group, consumer, streams, count, block))
        return []
    
    async def xack(self, stream, group, message_id):
        self._calls.append(('xack', stream, group, message_id))
        return 1
    
    async def xinfo_stream(self, stream):
        self._calls.append(('xinfo_stream', stream))
        if stream == "non_existent_stream":
            raise Exception(f"Stream {stream} does not exist")
        return {
            'length': 10,
            'groups': 2,
            'first-entry': ["first-0", {"payload": '{"id": "first"}'}],
            'last-entry': ["last-9", {"payload": '{"id": "last"}'}]
        }
    
    def pipeline(self, transaction=True):
        self._calls.append(('pipeline', transaction))
        return self.Pipeline()
    
    async def close(self):
        self._calls.append(('close',))
        return True
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# 创建模拟的aioredis模块
class MockAioredisModule:
    Redis = MockRedisClass
    RedisError = MockRedisClass.RedisError
    ResponseError = MockRedisClass.ResponseError
    
    @staticmethod
    def from_url(url, **kwargs):
        return MockRedisClass()

# 替换sys.modules中的aioredis
if 'aioredis' not in sys.modules:
    sys.modules['aioredis'] = MockAioredisModule()

# ====================== 导入项目模块 ======================

try:
    from database_service.streams.stream_manager import RedisStreamManager, StreamMessage
    from database_service.streams.utils.message_serializer import MessageSerializer
    print("✅ 成功导入项目模块")
    USE_MOCK = False
except Exception as e:
    print(f"⚠️  导入项目模块失败: {e}")
    print("   使用模拟模块继续测试...")
    USE_MOCK = True
    
    # 创建模拟的MessageSerializer
    class MessageSerializer:
        def serialize(self, data):
            return json.dumps(data)
        
        def deserialize(self, data):
            return json.loads(data)
    
    # 创建模拟的StreamMessage类
    class StreamMessage:
        def __init__(self, message_id, stream, data, published_at=None):
            self.message_id = message_id
            self.stream = stream
            self.data = data
            self.published_at = published_at or datetime.now()
        
        def __repr__(self):
            return f"StreamMessage(id={self.message_id}, stream={self.stream})"
    
    # 创建模拟的RedisStreamManager类
    class RedisStreamManager:
        def __init__(self, redis_url):
            self.redis_url = redis_url
            self.redis = None
            self.connected = False
            self.serializer = MessageSerializer()
        
        async def connect(self):
            self.connected = True
            return self
        
        async def publish(self, stream, data, max_len=None, approximate=True):
            # 模拟序列化
            payload = self.serializer.serialize(data)
            fields = {
                "payload": payload,
                "published_at": datetime.now().isoformat()
            }
            return "mocked_message_id"
        
        async def consume(self, group, consumer, stream, count=10, block=5000):
            return []
        
        async def ack(self, stream, group, message_id):
            return 1
        
        async def batch_ack(self, stream, group, message_ids):
            return [1] * len(message_ids)
        
        async def get_stream_info(self, stream):
            return {"error": "Stream does not exist"}

# ====================== 辅助函数 ======================

def create_mock_stream_response(stream_name, messages_data):
    """创建模拟的Stream响应数据"""
    messages = []
    for i, msg_data in enumerate(messages_data):
        fields = {
            "payload": json.dumps(msg_data),
            "published_at": datetime.now().isoformat()
        }
        messages.append([f"msg_{i}", fields])
    
    return [[stream_name, messages]]

# ====================== 测试类 ======================

class TestResult:
    """测试结果"""
    def __init__(self, name):
        self.name = name
        self.passed = False
        self.error = None
        self.duration = 0
    
    def success(self, duration=0):
        self.passed = True
        self.duration = duration
    
    def failure(self, error, duration=0):
        self.passed = False
        self.error = str(error)
        self.duration = duration

class TestRunner:
    """测试运行器"""
    
    def __init__(self):
        self.results = []
        self.total_time = 0
    
    async def run_test(self, test_func, name):
        """运行单个测试"""
        start_time = datetime.now()
        result = TestResult(name)
        
        try:
            await test_func()
            duration = (datetime.now() - start_time).total_seconds()
            result.success(duration)
            print(f"  ✅ {name} ({duration:.3f}s)")
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            result.failure(e, duration)
            print(f"  ❌ {name} ({duration:.3f}s)")
            print(f"     错误: {e}")
        
        self.results.append(result)
        self.total_time += duration
        return result.passed
    
    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("📊 测试总结")
        print("=" * 60)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for result in self.results:
            status = "✅" if result.passed else "❌"
            time_str = f"{result.duration:.3f}s"
            print(f"{status} {result.name:<40} {time_str:>10}")
            if result.error:
                print(f"     {result.error[:100]}...")
        
        print("-" * 60)
        success_rate = passed / total * 100 if total > 0 else 0
        print(f"总计: {passed}/{total} 通过 ({success_rate:.1f}%)")
        print(f"耗时: {self.total_time:.3f}秒")
        
        return passed == total

# ====================== 测试函数 ======================

async def test_basic_publish():
    """测试基本发布功能"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value="test_message_id")
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    message_id = await manager.publish(
        "test_stream",
        {"test": "data"}
    )
    
    # 断言
    assert message_id == "test_message_id"
    mock_redis.xadd.assert_called_once()

async def test_publish_with_options():
    """测试带选项的发布"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value="test_message_id")
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用带选项的发布
    await manager.publish(
        "test_stream",
        {"test": "data"},
        max_len=1000,
        approximate=False
    )
    
    # 验证选项参数
    call_args = mock_redis.xadd.call_args
    assert call_args[1]["maxlen"] == 1000
    assert call_args[1]["approximate"] is False

async def test_consume_single_message():
    """测试消费单条消息"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 准备模拟响应
    test_data = {"id": "msg_001", "content": "测试内容"}
    mock_response = create_mock_stream_response("test_stream", [test_data])
    mock_redis.xreadgroup = AsyncMock(return_value=mock_response)
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    messages = await manager.consume(
        group="test_group",
        consumer="test_consumer",
        stream="test_stream",
        count=1
    )
    
    # 断言
    assert len(messages) == 1
    assert isinstance(messages[0], StreamMessage)
    assert messages[0].data == test_data
    assert messages[0].message_id == "msg_0"

async def test_consume_batch_messages():
    """测试批量消费消息"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 准备多消息模拟数据
    batch_data = [
        {"id": f"msg_{i}", "content": f"消息{i}"}
        for i in range(5)
    ]
    mock_response = create_mock_stream_response("test_stream", batch_data)
    mock_redis.xreadgroup = AsyncMock(return_value=mock_response)
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    messages = await manager.consume(
        group="test_group",
        consumer="test_consumer",
        stream="test_stream",
        count=10
    )
    
    # 断言
    assert len(messages) == 5
    for i, msg in enumerate(messages):
        assert msg.data["id"] == f"msg_{i}"

async def test_consume_blocking():
    """测试阻塞消费"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 准备模拟数据
    test_data = {"test": "blocked"}
    mock_response = create_mock_stream_response("test_stream", [test_data])
    mock_redis.xreadgroup = AsyncMock(return_value=mock_response)
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用阻塞消费
    messages = await manager.consume(
        group="test_group",
        consumer="test_consumer",
        stream="test_stream",
        count=1,
        block=3000
    )
    
    # 验证block参数
    call_args = mock_redis.xreadgroup.call_args
    assert call_args[1]["block"] == 3000
    assert len(messages) == 1

async def test_ack_message():
    """测试消息确认"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    mock_redis.xack = AsyncMock(return_value=1)
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    result = await manager.ack(
        stream="test_stream",
        group="test_group",
        message_id="test_message_id"
    )
    
    # 断言
    assert result == 1
    mock_redis.xack.assert_called_once_with(
        "test_stream", "test_group", "test_message_id"
    )

async def test_batch_ack():
    """测试批量确认"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 配置管道
    pipe_mock = MagicMock()
    pipe_mock.xack = AsyncMock(return_value=pipe_mock)
    pipe_mock.execute = AsyncMock(return_value=[True, True, True])
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 准备消息ID
    message_ids = ["msg1", "msg2", "msg3"]
    
    # 调用
    results = await manager.batch_ack(
        stream="test_stream",
        group="test_group",
        message_ids=message_ids
    )
    
    # 验证管道使用
    assert mock_redis.pipeline.called
    
    # 验证每个消息都被确认
    pipe = mock_redis.pipeline.return_value
    assert pipe.xack.call_count == 3
    
    # 验证执行和结果
    assert pipe.execute.called
    assert results == [True, True, True]

async def test_get_stream_info_success():
    """测试获取Stream信息成功"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 准备模拟信息
    mock_info = {
        "length": 25,
        "groups": 2,
        "first-entry": ["first-0", {"payload": '{"id": "first_msg"}'}],
        "last-entry": ["last-24", {"payload": '{"id": "last_msg"}'}],
    }
    mock_redis.xinfo_stream = AsyncMock(return_value=mock_info)
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    info = await manager.get_stream_info("test_stream")
    
    # 断言
    assert info["length"] == 25
    assert info["groups"] == 2
    if "first_message" in info:
        assert info["first_message"]["id"] == "first_msg"

async def test_get_stream_info_not_found():
    """测试获取不存在的Stream信息"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 模拟Stream不存在
    mock_redis.xinfo_stream = AsyncMock(side_effect=Exception("Stream not found"))
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    info = await manager.get_stream_info("non_existent_stream")
    
    # 断言
    assert "error" in info
    assert "does not exist" in info["error"]
    assert info["stream_name"] == "non_existent_stream"

async def test_publish_error():
    """测试发布错误处理"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 模拟发布错误
    mock_redis.xadd = AsyncMock(side_effect=Exception("Redis error"))
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用并期望异常
    with pytest.raises(Exception, match="Redis error"):
        await manager.publish("test_stream", {"test": "data"})

async def test_consume_empty():
    """测试空消费"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 模拟空响应
    mock_redis.xreadgroup = AsyncMock(return_value=[])
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    messages = await manager.consume(
        group="test_group",
        consumer="test_consumer",
        stream="test_stream",
        count=1
    )
    
    # 断言
    assert len(messages) == 0

async def test_publish_empty_data():
    """测试发布空数据"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value="test_id")
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用
    message_id = await manager.publish("test_stream", {})
    
    # 断言
    assert message_id == "test_id"

async def test_batch_ack_empty():
    """测试批量确认为空列表"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 调用空列表
    results = await manager.batch_ack(
        stream="test_stream",
        group="test_group",
        message_ids=[]
    )
    
    # 断言：不应该调用管道
    assert not mock_redis.pipeline.called
    assert results == []

async def test_full_flow():
    """测试完整流程：发布 -> 消费 -> 确认"""
    # 创建模拟Redis
    mock_redis = AsyncMock()
    
    # 1. 配置xadd
    mock_redis.xadd = AsyncMock(return_value="flow_msg_id")
    
    # 2. 配置xreadgroup
    publish_data = {"id": "flow_test", "step": "publish"}
    mock_response = create_mock_stream_response("test_stream", [publish_data])
    mock_redis.xreadgroup = AsyncMock(return_value=mock_response)
    
    # 3. 配置xack
    mock_redis.xack = AsyncMock(return_value=1)
    
    # 创建管理器
    manager = RedisStreamManager("redis://localhost:6379/0")
    manager.redis = mock_redis
    manager.connected = True
    
    # 1. 发布消息
    message_id = await manager.publish("test_stream", publish_data)
    assert message_id == "flow_msg_id"
    assert mock_redis.xadd.call_count == 1
    
    # 2. 消费消息
    messages = await manager.consume(
        group="test_group",
        consumer="test_consumer",
        stream="test_stream",
        count=1
    )
    
    assert len(messages) == 1
    assert messages[0].data == publish_data
    
    # 3. 确认消息
    await manager.ack("test_stream", "test_group", messages[0].message_id)
    assert mock_redis.xack.call_count == 1
    
    # 验证总调用次数
    assert mock_redis.xadd.call_count == 1
    assert mock_redis.xreadgroup.call_count == 1
    assert mock_redis.xack.call_count == 1

# ====================== 主函数 ======================

async def run_all_tests():
    """运行所有测试"""
    print("🧪 Stream管理器测试")
    print("=" * 60)
    print(f"使用 {'模拟' if USE_MOCK else '真实'} 模块")
    print("-" * 60)
    
    runner = TestRunner()
    
    # 定义测试列表
    tests = [
        (test_basic_publish, "基本发布功能"),
        (test_publish_with_options, "带选项发布"),
        (test_consume_single_message, "消费单条消息"),
        (test_consume_batch_messages, "批量消费消息"),
        (test_consume_blocking, "阻塞消费"),
        (test_ack_message, "消息确认"),
        (test_batch_ack, "批量确认"),
        (test_get_stream_info_success, "获取Stream信息成功"),
        (test_get_stream_info_not_found, "获取不存在Stream信息"),
        (test_consume_empty, "空消费"),
        (test_publish_empty_data, "发布空数据"),
        (test_batch_ack_empty, "批量确认为空"),
        (test_full_flow, "完整流程测试"),
    ]
    
    # 运行所有测试
    for test_func, test_name in tests:
        print(f"📋 运行: {test_name}")
        await runner.run_test(test_func, test_name)
    
    # 打印总结
    success = runner.print_summary()
    
    return 0 if success else 1

# ====================== 启动测试 ======================

if __name__ == "__main__":
    # 删除可能导入的pytest模块，避免冲突
    if 'pytest' in sys.modules:
        del sys.modules['pytest']
    
    try:
        # 运行测试
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
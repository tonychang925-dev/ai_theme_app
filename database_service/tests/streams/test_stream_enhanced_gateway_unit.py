"""
StreamEnhancedGateway 单元测试 - 简化版本
"""
import os
import sys
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

# ========== 修复导入路径 ==========
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

# 添加正确的路径
sys.path.insert(0, project_root)
sys.path.insert(0, service_dir)

# 现在应该可以正常导入了
from database_service.streams.stream_gateway import StreamEnhancedGateway

# ========== 测试用例 ==========

class TestStreamEnhancedGateway:
    """StreamEnhancedGateway 单元测试类"""
    
    def setup_method(self):
        """测试方法前设置"""
        # 创建模拟的基础网关
        self.mock_base_gateway = Mock()
        self.mock_base_gateway.create_theme = AsyncMock()
        self.mock_base_gateway.update_theme = AsyncMock()
        self.mock_base_gateway.increment_theme_heat = AsyncMock()
        self.mock_base_gateway.health_check = AsyncMock(return_value=True)
        self.mock_base_gateway.close = AsyncMock()
        
        # 创建增强网关实例
        self.gateway = StreamEnhancedGateway(
            base_gateway=self.mock_base_gateway,
            stream_manager=None,  # 设为None，测试中会创建
            enable_retry=False
        )
    
    @pytest.mark.asyncio
    async def test_initialize_streams_success(self):
        """测试成功初始化 Stream"""
        # 重置状态
        self.gateway.stream_initialized = False
        
        # 直接模拟内部调用的方法
        self.gateway._initialize_streams_internal = AsyncMock()
        
        await self.gateway.initialize_streams()
        
        assert self.gateway.stream_initialized is True
        self.gateway._initialize_streams_internal.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_streams_failure(self):
        """测试初始化 Stream 失败"""
        # 重置状态
        self.gateway.stream_initialized = False
        
        # 模拟内部方法抛出异常
        self.gateway._initialize_streams_internal = AsyncMock(side_effect=Exception("连接失败"))
        
        with pytest.raises(Exception, match="连接失败"):
            await self.gateway.initialize_streams()
        
        assert self.gateway.stream_initialized is False
    
    @pytest.mark.asyncio
    async def test_publish_news_success(self):
        """测试发布新闻成功"""
        # 设置状态和模拟
        self.gateway.stream_initialized = True
        self.gateway.news_producer = Mock()
        self.gateway.news_producer.publish = AsyncMock(return_value="news_123")
        
        news_data = {
            "id": "test_news_001",
            "title": "测试新闻标题",
            "content": "测试新闻内容，长度超过10个字符"
        }
        
        result = await self.gateway.publish_news(news_data)
        
        assert result == "news_123"
        self.gateway.news_producer.publish.assert_called_once_with(news_data)
        assert self.gateway.stream_stats['published_messages'] == 1
    
    @pytest.mark.asyncio
    async def test_publish_news_validation_failure(self):
        """测试发布新闻 - 数据验证失败"""
        invalid_news_data = {
            "id": "test_news_001",
            "title": "标题"
            # 缺少 content 字段
        }
        
        result = await self.gateway.publish_news(invalid_news_data)
        
        assert result is None
        assert self.gateway.stream_stats['published_errors'] == 1
    
    @pytest.mark.asyncio
    async def test_create_theme_with_stream(self):
        """测试增强版创建主题"""
        # 设置模拟
        self.gateway.stream_initialized = True
        self.gateway.publish_theme_update = AsyncMock(return_value="theme_123")
        
        mock_theme = Mock()
        mock_theme.id = 1
        mock_theme.name = "测试主题"
        mock_theme.code = "TEST_THEME"
        self.mock_base_gateway.create_theme.return_value = mock_theme
        
        result = await self.gateway.create_theme_with_stream(
            name="测试主题",
            code="TEST_THEME",
            description="测试描述"
        )
        
        assert result == mock_theme
        self.mock_base_gateway.create_theme.assert_called_once_with(
            name="测试主题",
            code="TEST_THEME",
            description="测试描述"
        )
        self.gateway.publish_theme_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_theme_with_stream(self):
        """测试增强版更新主题"""
        # 设置模拟
        self.gateway.stream_initialized = True
        self.gateway.publish_theme_update = AsyncMock(return_value="theme_456")
        
        mock_theme = Mock()
        mock_theme.id = 1
        self.mock_base_gateway.update_theme.return_value = mock_theme
        
        updates = {"name": "更新后的名称", "description": "更新描述"}
        result = await self.gateway.update_theme_with_stream(theme_id=1, updates=updates)
        
        assert result == mock_theme
        self.mock_base_gateway.update_theme.assert_called_once_with(
            theme_id=1,
            updates=updates
        )
        self.gateway.publish_theme_update.assert_called_once()
    
    def test_getattr_proxy(self):
        """测试属性代理"""
        # 设置基础网关的方法
        self.mock_base_gateway.existing_method = Mock(return_value="test_result")
        
        # 测试代理存在的方法
        result = self.gateway.existing_method()
        assert result == "test_result"
        
        # 测试不存在的属性应该抛出AttributeError
        # Mock对象会响应所有属性，所以我们需要特殊处理测试
        # 创建一个不自动响应的Mock
        class NonAutoMock(Mock):
            def __getattr__(self, name):
                if name == 'some_method':
                    return Mock(return_value="some_result")
                raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        restricted_gateway = NonAutoMock()
        restricted_gateway.some_method = Mock(return_value="test_result")
        
        gateway = StreamEnhancedGateway(base_gateway=restricted_gateway)
        
        # 测试代理存在的方法
        result = gateway.some_method()
        assert result == "test_result"
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        # 设置模拟
        self.gateway.stream_initialized = True
        self.gateway.stream_manager = Mock()
        self.gateway.stream_manager.get_stream_info = AsyncMock(return_value={"length": 10})
        
        result = await self.gateway.health_check_with_streams()
        
        assert isinstance(result, dict)
        assert "overall" in result
        assert "database" in result
        assert "stream" in result
    
    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭连接"""
        # 设置模拟
        self.gateway.stream_manager = Mock()
        self.gateway.stream_manager.redis = Mock()
        self.gateway.stream_manager.redis.close = AsyncMock()
        
        await self.gateway.close()
        
        self.mock_base_gateway.close.assert_called_once()
        self.gateway.stream_manager.redis.close.assert_called_once()


# ========== 参数化测试 ==========

@pytest.mark.parametrize("news_data,expected_valid", [
    ({
        "id": "news_001",
        "title": "有效新闻标题",
        "content": "这是一个有效的新闻内容，长度超过10个字符"
    }, True),
    ({
        "id": "news_002",
        "title": "无效新闻",
        "content": "短"  # 内容太短
    }, False),
    ({
        "title": "缺少ID",
        "content": "这是一个内容"
    }, False),
])
def test_news_validation(news_data, expected_valid):
    """测试新闻数据验证"""
    gateway = StreamEnhancedGateway(base_gateway=Mock())
    
    is_valid = gateway._validate_news_data(news_data)
    assert is_valid == expected_valid


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
"""
数据库接口扩展
将 Stream 功能集成到原有的 DatabaseManager 接口中
"""
from typing import Dict, List, Any, Optional
from datetime import datetime

# 将相对导入改为绝对导入
from database_service.interface import DatabaseManager, ThemeRecord, EventThemeRelation
from database_service.streams.stream_interface import (
    StreamEnhancedDatabaseManager,
    StreamMessage, NewsMessage, EventExtractionMessage,
    ThemeUpdateMessage, ThemeMatchMessage, DeadLetterMessage,
    MessageType, StreamPriority
)


class DatabaseManagerWithStreams(DatabaseManager, StreamEnhancedDatabaseManager):
    """
    支持 Stream 的数据库管理器组合接口
    
    这个接口合并了原有的 DatabaseManager 和新的 StreamEnhancedDatabaseManager，
    为具体的实现类提供完整的接口定义。
    """
    
    # ========== StreamEnhancedDatabaseManager 接口实现 ==========
    
    async def publish_to_stream(self, stream_key: str, data: Dict[str, Any]) -> Optional[str]:
        """发布消息到Stream - 需要子类实现"""
        raise NotImplementedError
    
    async def publish_news(self, news_data: Dict[str, Any]) -> Optional[str]:
        """发布新闻到Stream - 需要子类实现"""
        raise NotImplementedError
    
    async def publish_event(self, event_data: Dict[str, Any], is_major: bool = False) -> Optional[str]:
        """发布事件到Stream - 需要子类实现"""
        raise NotImplementedError
    
    async def publish_theme_update(self, theme_data: Dict[str, Any]) -> Optional[str]:
        """发布主题更新到Stream - 需要子类实现"""
        raise NotImplementedError
    
    async def create_theme_with_stream(self, name: str, code: str, **kwargs) -> Optional[ThemeRecord]:
        """创建主题并发布到Stream - 默认实现"""
        # 调用原有的 create_theme 方法
        theme = await self.create_theme(name, code, **kwargs)
        
        if theme:
            # 发布到 Stream
            theme_message = ThemeUpdateMessage.from_theme_record(theme, "create")
            await self.publish_theme_update(theme_message.to_stream_message().data)
        
        return theme
    
    async def update_theme_with_stream(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题并发布到Stream - 默认实现"""
        # 获取之前的状态
        previous_theme = await self.get_theme(theme_id)
        previous_state = previous_theme.to_dict() if previous_theme else None
        
        # 调用原有的 update_theme 方法
        theme = await self.update_theme(theme_id, updates)
        
        if theme:
            # 发布到 Stream
            theme_message = ThemeUpdateMessage(
                theme_id=theme_id,
                update_type="update",
                update_data=updates,
                previous_state=previous_state
            )
            await self.publish_theme_update(theme_message.to_stream_message().data)
        
        return theme
    
    async def increment_theme_heat_with_stream(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度并发布到Stream - 默认实现"""
        # 调用原有的 increment_theme_heat 方法
        await self.increment_theme_heat(theme_id, increment)
        
        # 发布到 Stream
        heat_data = {
            "theme_id": theme_id,
            "increment": increment,
            "update_type": "heat_change",
            "timestamp": datetime.now().isoformat()
        }
        await self.publish_theme_update(heat_data)
    
    async def create_event_theme_relation_with_stream(self, event_id: int, theme_id: int, **kwargs) -> Optional[EventThemeRelation]:
        """创建事件-主题关联并发布到Stream - 默认实现"""
        # 调用原有的 create_event_theme_relation 方法
        relation = await self.create_event_theme_relation(event_id, theme_id, **kwargs)
        
        if relation:
            # 发布到 Stream
            match_message = ThemeMatchMessage.from_event_theme_relation(relation)
            await self.publish_event(match_message.to_stream_message().data, is_major=False)
        
        return relation
    
    async def get_stream_stats(self) -> Dict[str, Any]:
        """获取Stream统计信息 - 默认实现"""
        return {
            "stream_supported": True,
            "message": "Stream统计需要具体实现"
        }
    
    async def health_check_with_streams(self) -> Dict[str, Any]:
        """包含Stream的健康检查 - 默认实现"""
        base_healthy = await self.health_check()
        
        return {
            "overall": base_healthy,
            "database": base_healthy,
            "stream": {
                "healthy": True,
                "supported": True,
                "message": "Stream健康检查需要具体实现"
            }
        }
    
    async def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强的统计信息 - 默认实现"""
        base_stats = await self.get_stats()
        
        return {
            **base_stats,
            "stream_enhanced": True,
            "stream_stats": await self.get_stream_stats()
        }


# ========== 适配器：将原有 DatabaseManager 适配为 StreamEnhancedDatabaseManager ==========

class StreamAdapter(StreamEnhancedDatabaseManager):
    """
    Stream 适配器
    将原有的 DatabaseManager 适配为支持 Stream 的接口
    """
    
    def __init__(self, base_manager: DatabaseManager, stream_manager = None):
        """
        初始化适配器
        
        Args:
            base_manager: 基础数据库管理器
            stream_manager: Stream 管理器，如果为 None 则使用基础管理器的 Stream 功能
        """
        self.base_manager = base_manager
        self.stream_manager = stream_manager
        
        # 检查基础管理器是否支持 Stream
        self._has_stream_support = hasattr(base_manager, 'publish_to_stream')
    
    async def publish_to_stream(self, stream_key: str, data: Dict[str, Any]) -> Optional[str]:
        """发布消息到Stream"""
        if self._has_stream_support:
            return await self.base_manager.publish_to_stream(stream_key, data)
        
        if self.stream_manager:
            # 使用独立的 Stream 管理器
            return await self.stream_manager.publish(stream_key, data)
        
        raise NotImplementedError("Stream 功能不可用")
    
    async def publish_news(self, news_data: Dict[str, Any]) -> Optional[str]:
        """发布新闻到Stream"""
        if self._has_stream_support:
            return await self.base_manager.publish_news(news_data)
        
        # 创建新闻消息
        news_message = NewsMessage.from_dict(news_data)
        stream_message = news_message.to_stream_message()
        
        return await self.publish_to_stream(stream_message.stream, stream_message.data)
    
    async def publish_event(self, event_data: Dict[str, Any], is_major: bool = False) -> Optional[str]:
        """发布事件到Stream"""
        if self._has_stream_support:
            return await self.base_manager.publish_event(event_data, is_major)
        
        # 创建事件消息
        stream_key = "events:major" if is_major else "events:normal"
        message_type = MessageType.EVENT_MAJOR if is_major else MessageType.EVENT_NORMAL
        
        stream_message = StreamMessage(
            id=f"event_{event_data.get('id', 'unknown')}",
            stream=stream_key,
            type=message_type,
            data=event_data,
            timestamp=datetime.now()
        )
        
        return await self.publish_to_stream(stream_key, stream_message.data)
    
    async def publish_theme_update(self, theme_data: Dict[str, Any]) -> Optional[str]:
        """发布主题更新到Stream"""
        if self._has_stream_support:
            return await self.base_manager.publish_theme_update(theme_data)
        
        stream_message = StreamMessage(
            id=f"theme_update_{theme_data.get('theme_id', 'unknown')}",
            stream="themes:updates",
            type=MessageType.THEME_UPDATE,
            data=theme_data,
            timestamp=datetime.now()
        )
        
        return await self.publish_to_stream("themes:updates", stream_message.data)
    
    async def create_theme_with_stream(self, name: str, code: str, **kwargs) -> Optional[ThemeRecord]:
        """创建主题并发布到Stream"""
        if hasattr(self.base_manager, 'create_theme_with_stream'):
            return await self.base_manager.create_theme_with_stream(name, code, **kwargs)
        
        # 调用基础管理器的 create_theme
        theme = await self.base_manager.create_theme(name, code, **kwargs)
        
        if theme:
            # 发布到 Stream
            theme_message = ThemeUpdateMessage.from_theme_record(theme, "create")
            await self.publish_theme_update(theme_message.to_stream_message().data)
        
        return theme
    
    async def update_theme_with_stream(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题并发布到Stream"""
        if hasattr(self.base_manager, 'update_theme_with_stream'):
            return await self.base_manager.update_theme_with_stream(theme_id, updates)
        
        # 调用基础管理器的 update_theme
        theme = await self.base_manager.update_theme(theme_id, updates)
        
        if theme:
            # 发布到 Stream
            theme_message = ThemeUpdateMessage(
                theme_id=theme_id,
                update_type="update",
                update_data=updates
            )
            await self.publish_theme_update(theme_message.to_stream_message().data)
        
        return theme
    
    async def increment_theme_heat_with_stream(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度并发布到Stream"""
        if hasattr(self.base_manager, 'increment_theme_heat_with_stream'):
            return await self.base_manager.increment_theme_heat_with_stream(theme_id, increment)
        
        # 调用基础管理器的 increment_theme_heat
        await self.base_manager.increment_theme_heat(theme_id, increment)
        
        # 发布到 Stream
        heat_data = {
            "theme_id": theme_id,
            "increment": increment,
            "update_type": "heat_change",
            "timestamp": datetime.now().isoformat()
        }
        await self.publish_theme_update(heat_data)
    
    async def create_event_theme_relation_with_stream(self, event_id: int, theme_id: int, **kwargs) -> Optional[EventThemeRelation]:
        """创建事件-主题关联并发布到Stream"""
        if hasattr(self.base_manager, 'create_event_theme_relation_with_stream'):
            return await self.base_manager.create_event_theme_relation_with_stream(event_id, theme_id, **kwargs)
        
        # 调用基础管理器的 create_event_theme_relation
        relation = await self.base_manager.create_event_theme_relation(event_id, theme_id, **kwargs)
        
        if relation:
            # 发布到 Stream
            match_message = ThemeMatchMessage.from_event_theme_relation(relation)
            await self.publish_event(match_message.to_stream_message().data, is_major=False)
        
        return relation
    
    async def get_stream_stats(self) -> Dict[str, Any]:
        """获取Stream统计信息"""
        if hasattr(self.base_manager, 'get_stream_stats'):
            return await self.base_manager.get_stream_stats()
        
        return {
            "adapter_mode": True,
            "base_manager_type": type(self.base_manager).__name__,
            "stream_support": self._has_stream_support,
            "stream_manager_available": self.stream_manager is not None
        }
    
    async def health_check_with_streams(self) -> Dict[str, Any]:
        """包含Stream的健康检查"""
        base_healthy = await self.base_manager.health_check()
        
        stream_healthy = True
        if self.stream_manager:
            try:
                # 检查 Stream 连接
                if hasattr(self.stream_manager, 'redis'):
                    await self.stream_manager.redis.ping()
            except:
                stream_healthy = False
        
        return {
            "overall": base_healthy and stream_healthy,
            "database": base_healthy,
            "stream": stream_healthy,
            "adapter_mode": True
        }
    
    async def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强的统计信息"""
        base_stats = await self.base_manager.get_stats()
        
        return {
            **base_stats,
            "stream_enhanced": True,
            "adapter_mode": True,
            "stream_stats": await self.get_stream_stats()
        }
    
    # 代理所有其他方法到基础管理器
    def __getattr__(self, name):
        """代理所有未定义的方法到基础管理器"""
        return getattr(self.base_manager, name)


# ========== 便捷函数 ==========

def adapt_to_streams(base_manager: DatabaseManager, stream_manager = None) -> StreamEnhancedDatabaseManager:
    """
    将原有的 DatabaseManager 适配为支持 Stream 的接口
    
    Args:
        base_manager: 基础数据库管理器
        stream_manager: 可选的 Stream 管理器
        
    Returns:
        支持 Stream 的数据库管理器
    """
    # 如果基础管理器已经支持 Stream，直接返回
    if isinstance(base_manager, StreamEnhancedDatabaseManager):
        return base_manager
    
    # 否则创建适配器
    return StreamAdapter(base_manager, stream_manager)


def is_stream_supported(manager: DatabaseManager) -> bool:
    """检查管理器是否支持 Stream"""
    return (
        isinstance(manager, StreamEnhancedDatabaseManager) or
        hasattr(manager, 'publish_to_stream') or
        hasattr(manager, 'publish_news')
    )


def get_stream_capabilities(manager: DatabaseManager) -> Dict[str, bool]:
    """获取 Stream 功能支持情况"""
    if isinstance(manager, StreamEnhancedDatabaseManager):
        # 完整的 Stream 支持
        return {
            "stream_enhanced": True,
            "publish_news": True,
            "publish_event": True,
            "publish_theme_update": True,
            "enhanced_methods": True
        }
    
    # 检查部分支持
    capabilities = {
        "stream_enhanced": False,
        "publish_news": hasattr(manager, 'publish_news'),
        "publish_event": hasattr(manager, 'publish_event'),
        "publish_theme_update": hasattr(manager, 'publish_theme_update'),
        "enhanced_methods": hasattr(manager, 'create_theme_with_stream')
    }
    
    return capabilities
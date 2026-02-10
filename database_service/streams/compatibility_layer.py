"""
兼容层：确保现有代码无缝迁移到 Stream 增强网关
"""
import asyncio
import logging
import warnings
from typing import Optional

logger = logging.getLogger(__name__)


class StreamCompatibilityLayer:
    """
    Stream 兼容层
    确保现有代码可以无缝迁移到新的 Stream 架构
    """
    
    def __init__(self):
        self._deprecation_warnings_enabled = True
    
    def enable_deprecation_warnings(self, enabled: bool = True):
        """启用/禁用弃用警告"""
        self._deprecation_warnings_enabled = enabled
    
    async def migrate_legacy_queue(self, source_list_key: str, target_stream_key: str, 
                                 batch_size: int = 100) -> dict:
        """
        迁移旧版队列数据到 Stream
        
        Args:
            source_list_key: 旧版 Redis List 键名
            target_stream_key: 目标 Stream 键名
            batch_size: 批量迁移大小
            
        Returns:
            迁移统计
        """
        from .stream_config import get_enhanced_config
        from .stream_gateway import StreamEnhancedGateway
        
        logger.info(f"🔄 开始迁移: {source_list_key} -> {target_stream_key}")
        
        stats = {
            "total_migrated": 0,
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        try:
            # 获取网关
            gateway = await StreamEnhancedGateway.get_instance()
            
            # 获取 Redis 连接
            redis = gateway.base_gateway._client._db.redis
            
            # 获取 Stream 配置
            config = get_enhanced_config()
            stream_name = config.get_stream_url(target_stream_key)
            
            # 迁移循环
            while True:
                # 批量获取旧数据
                items = await redis.lrange(source_list_key, 0, batch_size - 1)
                if not items:
                    break
                
                # 批量迁移
                for item in items:
                    try:
                        # 解析数据
                        data = self._parse_legacy_data(item)
                        
                        # 发布到 Stream
                        await gateway.publish_to_stream(target_stream_key, data)
                        
                        # 从旧列表移除
                        await redis.lrem(source_list_key, 1, item)
                        
                        stats["success"] += 1
                        
                    except Exception as e:
                        stats["failed"] += 1
                        stats["errors"].append(str(e))
                        logger.error(f"迁移项目失败: {e}")
                
                stats["total_migrated"] += len(items)
                
                logger.info(f"迁移进度: {stats['total_migrated']} 条")
            
            logger.info(f"✅ 迁移完成: {stats}")
            
        except Exception as e:
            logger.error(f"迁移失败: {e}")
            stats["errors"].append(str(e))
        
        return stats
    
    def _parse_legacy_data(self, raw_data: str) -> dict:
        """解析旧版数据格式"""
        import json
        
        try:
            return json.loads(raw_data)
        except json.JSONDecodeError:
            # 尝试其他格式
            return {"raw_data": raw_data, "format": "legacy"}
    
    async def dual_write_interceptor(self, method_name: str, *args, **kwargs):
        """
        双写拦截器
        拦截旧版方法的调用，同时执行 Stream 发布
        """
        from .gateway_integration import get_stream_enhanced_gateway
        
        try:
            # 获取增强网关
            gateway = await get_stream_enhanced_gateway()
            
            # 根据方法名决定如何处理
            if method_name == "create_theme":
                # 主题创建的双写
                name, code = args[0], args[1]
                return await gateway.create_theme_with_stream(name, code, **kwargs)
            
            elif method_name == "increment_theme_heat":
                # 热度增加的双写
                theme_id, increment = args[0], args[1] if len(args) > 1 else 1
                return await gateway.increment_theme_heat_with_stream(theme_id, increment)
            
            # 其他方法暂时不拦截
            return None
            
        except Exception as e:
            logger.warning(f"双写拦截器失败: {e}")
            return None
    
    def warn_legacy_method(self, method_name: str, alternative: str = None):
        """发出弃用警告"""
        if not self._deprecation_warnings_enabled:
            return
        
        warning_msg = f"方法 '{method_name}' 已弃用"
        if alternative:
            warning_msg += f"，请使用 '{alternative}' 替代"
        
        warnings.warn(warning_msg, DeprecationWarning, stacklevel=3)
    
    async def monitor_migration_progress(self):
        """监控迁移进度"""
        from .stream_config import get_enhanced_config
        
        config = get_enhanced_config()
        
        if not config.dual_write_mode:
            logger.info("双写模式未启用，无需监控迁移进度")
            return
        
        logger.info("📊 开始监控迁移进度...")
        
        # 这里可以定期检查：
        # 1. 旧队列的长度
        # 2. Stream 的消息数量
        # 3. 处理延迟
        # 4. 错误率
        
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟检查一次
                
                # 示例：检查新闻队列
                # old_queue_length = await self._check_legacy_queue_length("news_queue")
                # stream_length = await self._check_stream_length("news_raw")
                
                # logger.info(f"迁移进度 - 旧队列: {old_queue_length}, Stream: {stream_length}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控迁移进度失败: {e}")
                await asyncio.sleep(60)


# 全局兼容层实例
_compatibility_layer: Optional[StreamCompatibilityLayer] = None


def get_compatibility_layer() -> StreamCompatibilityLayer:
    """获取兼容层实例"""
    global _compatibility_layer
    
    if _compatibility_layer is None:
        _compatibility_layer = StreamCompatibilityLayer()
    
    return _compatibility_layer


# 便捷函数
async def migrate_all_legacy_queues():
    """迁移所有旧版队列到 Stream"""
    compatibility = get_compatibility_layer()
    
    migration_tasks = [
        ("news_queue", "news_raw"),
        ("event_queue", "events_normal"),
        ("major_event_queue", "events_major"),
        ("theme_update_channel", "themes_updates")
    ]
    
    total_stats = {
        "total_migrated": 0,
        "success": 0,
        "failed": 0,
        "tasks": []
    }
    
    for source, target in migration_tasks:
        logger.info(f"开始迁移: {source} -> {target}")
        
        stats = await compatibility.migrate_legacy_queue(source, target)
        total_stats["total_migrated"] += stats["total_migrated"]
        total_stats["success"] += stats["success"]
        total_stats["failed"] += stats["failed"]
        total_stats["tasks"].append({
            "source": source,
            "target": target,
            "stats": stats
        })
        
        logger.info(f"完成迁移: {source} -> {target}")
    
    logger.info(f"🎉 所有迁移完成: {total_stats}")
    
    return total_stats


# Monkey patch：在运行时替换原有方法
def patch_gateway_for_streams():
    """
    动态修补原有网关，添加 Stream 功能
    
    注意：这会修改全局的 DatabaseGateway 类
    仅在确定需要时使用
    """
    import warnings
    from ..gateway import DatabaseGateway
    
    original_create_theme = DatabaseGateway.create_theme
    original_increment_theme_heat = DatabaseGateway.increment_theme_heat
    
    async def patched_create_theme(self, name: str, code: str, **kwargs):
        """修补后的 create_theme 方法"""
        # 调用原有方法
        result = await original_create_theme(self, name, code, **kwargs)
        
        # 尝试发布到 Stream
        try:
            from .gateway_integration import publish_theme_update
            if result:
                theme_data = {
                    "theme_id": result.id,
                    "name": result.name,
                    "code": result.code,
                    "action": "create",
                    "timestamp": datetime.now().isoformat()
                }
                await publish_theme_update(theme_data)
        except Exception as e:
            warnings.warn(f"Stream 发布失败: {e}")
        
        return result
    
    async def patched_increment_theme_heat(self, theme_id: int, increment: int = 1):
        """修补后的 increment_theme_heat 方法"""
        # 调用原有方法
        await original_increment_theme_heat(self, theme_id, increment)
        
        # 尝试发布到 Stream
        try:
            from .gateway_integration import publish_theme_update
            heat_data = {
                "theme_id": theme_id,
                "increment": increment,
                "action": "heat_increment",
                "timestamp": datetime.now().isoformat()
            }
            await publish_theme_update(heat_data)
        except Exception as e:
            warnings.warn(f"Stream 发布失败: {e}")
    
    # 应用补丁
    DatabaseGateway.create_theme = patched_create_theme
    DatabaseGateway.increment_theme_heat = patched_increment_theme_heat
    
    logger.info("✅ DatabaseGateway 已修补，支持 Stream 发布")
    
    return True
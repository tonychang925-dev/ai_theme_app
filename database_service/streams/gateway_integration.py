"""
Stream 网关集成工具 - 重试增强版
提供简单的方式将 Stream 功能和重试机制集成到现有系统中
"""
import asyncio
import logging
from typing import Optional, Dict, Any

from database_service.gateway import DatabaseGateway, get_gateway as get_original_gateway
    
# 将相对导入改为绝对导入
from database_service.streams.stream_gateway import StreamEnhancedGateway
from database_service.streams.stream_config import get_enhanced_config

logger = logging.getLogger(__name__)


# 全局 Stream 增强网关实例
_stream_enhanced_gateway: Optional[StreamEnhancedGateway] = None
# 默认重试配置
_DEFAULT_RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay": 1.0,
    "strategy": "exponential",
    "max_delay": 30.0,
    "jitter": True
}

def _is_stale_stream_gateway(gateway: Optional[StreamEnhancedGateway]) -> bool:
    """检查全局增强网关是否已失效（例如被关闭后仍被单例持有）。"""
    if gateway is None:
        return True

    base = getattr(gateway, "base_gateway", None)
    if base is None:
        return True

    # DatabaseGateway.close() 后会把 _initialized 置为 False
    if getattr(base, "_initialized", True) is False:
        return True

    client = getattr(base, "_client", None)
    if client is None:
        return True

    # Postgres 管理器连接池为空时，后续 acquire 会报 NoneType.acquire
    pool = getattr(client, "pool", None)
    if pool is None:
        return True

    return False


async def get_stream_enhanced_gateway(
    enable_retry: bool = True,
    retry_config: Optional[Dict[str, Any]] = None
) -> StreamEnhancedGateway:
    """
    获取 Stream 增强网关实例（全局单例）
    
    Args:
        enable_retry: 是否启用重试功能
        retry_config: 自定义重试配置
        
    Returns:
        StreamEnhancedGateway 实例
    """
    global _stream_enhanced_gateway

    if _is_stale_stream_gateway(_stream_enhanced_gateway):
        if _stream_enhanced_gateway is not None:
            logger.warning("♻️ 检测到失效的 StreamEnhancedGateway，触发重建")
        _stream_enhanced_gateway = None
        await initialize_stream_gateway(
            enable_retry=enable_retry,
            retry_config=retry_config
        )
    
    return _stream_enhanced_gateway


async def initialize_stream_gateway(
    original_gateway: DatabaseGateway = None,
    enable_retry: bool = True,
    retry_config: Optional[Dict[str, Any]] = None
) -> StreamEnhancedGateway:
    """
    初始化 Stream 增强网关（带重试功能）
    
    Args:
        original_gateway: 原有的 DatabaseGateway 实例
        enable_retry: 是否启用重试功能
        retry_config: 自定义重试配置
        
    Returns:
        初始化后的 StreamEnhancedGateway 实例
    """
    global _stream_enhanced_gateway
    
    if _stream_enhanced_gateway is not None and not _is_stale_stream_gateway(_stream_enhanced_gateway):
        # 如果网关已存在，可以更新其配置
        if enable_retry != _stream_enhanced_gateway.enable_retry:
            _stream_enhanced_gateway.enable_retry_function(enable_retry)
        
        if retry_config:
            _stream_enhanced_gateway.update_retry_config(retry_config)
        
        return _stream_enhanced_gateway
    elif _stream_enhanced_gateway is not None:
        logger.warning("♻️ initialize_stream_gateway 发现现有网关失效，执行重建")
        _stream_enhanced_gateway = None
    
    logger.info("🚀 初始化 Stream 增强网关（带重试功能）...")
    
    try:
        # 获取原有网关
        if original_gateway is None:
            original_gateway = await get_original_gateway()
        
        # 获取配置
        config = get_enhanced_config()
        
        # 合并重试配置
        final_retry_config = _DEFAULT_RETRY_CONFIG.copy()
        if retry_config:
            final_retry_config.update(retry_config)
        
        # 创建 Stream 增强网关
        _stream_enhanced_gateway = StreamEnhancedGateway(
            original_gateway,
            enable_retry=enable_retry and config.enable_stream_processing,
            retry_config=final_retry_config if enable_retry else None
        )
        
        # 检查是否启用 Stream
        if not config.enable_stream_processing or not config.redis_stream.enabled:
            logger.warning("⚠️  Stream 处理未启用，创建降级版网关")
            return _stream_enhanced_gateway
        
        # 初始化 Stream 组件（带重试）
        try:
            await _stream_enhanced_gateway.initialize_streams()
            logger.info("✅ Stream 增强网关初始化完成")
            
            # 打印重试配置
            if enable_retry:
                logger.info(f"   - 重试功能: 启用")
                logger.info(f"   - 重试策略: {final_retry_config.get('strategy', 'exponential')}")
                logger.info(f"   - 最大重试次数: {final_retry_config.get('max_retries', 3)}")
            else:
                logger.info(f"   - 重试功能: 禁用")
            
        except Exception as e:
            logger.error(f"❌ Stream 组件初始化失败，创建降级版网关: {e}")
            # 网关仍可用，但 Stream 功能受限
        
        return _stream_enhanced_gateway
        
    except Exception as e:
        logger.error(f"❌ Stream 增强网关初始化失败: {e}")
        
        # 创建降级版网关（无 Stream 功能）
        _stream_enhanced_gateway = StreamEnhancedGateway(
            original_gateway,
            enable_retry=False  # 降级模式下禁用重试
        )
        return _stream_enhanced_gateway


async def get_gateway(
    enable_retry: bool = True,
    retry_config: Optional[Dict[str, Any]] = None
) -> StreamEnhancedGateway:
    """
    获取网关实例（替代原有的 get_gateway，返回增强版）
    
    Args:
        enable_retry: 是否启用重试功能
        retry_config: 自定义重试配置
        
    Returns:
        StreamEnhancedGateway 实例
        
    注意：这个函数会覆盖原有的 get_gateway 功能
    如果希望保持原有功能，请使用 get_original_gateway()
    """
    return await get_stream_enhanced_gateway(
        enable_retry=enable_retry,
        retry_config=retry_config
    )


async def get_original_gateway() -> DatabaseGateway:
    """
    获取原有的网关实例（不包含 Stream 增强）
    
    Returns:
        原有的 DatabaseGateway 实例
    """
    return await DatabaseGateway.get_instance()


# 装饰器：自动注入增强网关
def with_stream_gateway(func):
    """自动注入 stream_enhanced_gateway 参数的装饰器"""
    import functools
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if 'stream_enhanced_gateway' not in kwargs:
            kwargs['stream_enhanced_gateway'] = await get_stream_enhanced_gateway()
        return await func(*args, **kwargs)
    return wrapper


def with_retry_config(max_retries: int = 3, base_delay: float = 1.0, 
                     strategy: str = "exponential"):
    """
    为函数自动配置重试参数
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟
        strategy: 重试策略
    """
    def decorator(func):
        import functools
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 检查是否已有重试配置
            if 'retry_config' not in kwargs:
                kwargs['retry_config'] = {
                    'max_retries': max_retries,
                    'base_delay': base_delay,
                    'strategy': strategy
                }
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# 快捷方法（带重试功能）
async def publish_news_to_stream(
    news_data: dict,
    enable_retry: bool = True
) -> Optional[str]:
    """快捷方法：发布新闻到 Stream（带重试）"""
    gateway = await get_stream_enhanced_gateway(enable_retry=enable_retry)
    return await gateway.publish_news(news_data)


async def publish_event_to_stream(
    event_data: dict, 
    is_major: bool = False,
    enable_retry: bool = True
) -> Optional[str]:
    """快捷方法：发布事件到 Stream（带重试）"""
    gateway = await get_stream_enhanced_gateway(enable_retry=enable_retry)
    return await gateway.publish_event(event_data, is_major)


async def smart_publish_to_stream(
    data: dict,
    data_type: str = None,
    enable_retry: bool = True
) -> Optional[str]:
    """快捷方法：智能发布到 Stream（自动识别数据类型）"""
    gateway = await get_stream_enhanced_gateway(enable_retry=enable_retry)
    return await gateway.smart_publish(data, data_type)


async def batch_publish_to_stream(
    items: list,
    data_type: str = None,
    max_concurrent: int = 5,
    enable_retry: bool = True
) -> list:
    """快捷方法：批量发布到 Stream（带并发控制）"""
    gateway = await get_stream_enhanced_gateway(enable_retry=enable_retry)
    return await gateway.batch_publish(items, data_type, max_concurrent)


async def create_theme_with_stream(
    name: str, 
    code: str, 
    enable_retry: bool = True,
    **kwargs
) -> Optional[any]:
    """快捷方法：创建主题并发布到 Stream（带重试）"""
    gateway = await get_stream_enhanced_gateway(enable_retry=enable_retry)
    return await gateway.create_theme_with_stream(name, code, **kwargs)


async def update_theme_with_stream(
    theme_id: int,
    updates: dict,
    enable_retry: bool = True
) -> Optional[any]:
    """快捷方法：更新主题并发布到 Stream（带重试）"""
    gateway = await get_stream_enhanced_gateway(enable_retry=enable_retry)
    return await gateway.update_theme_with_stream(theme_id, updates)


async def get_enhanced_stats() -> dict:
    """快捷方法：获取增强统计（包含重试统计）"""
    gateway = await get_stream_enhanced_gateway()
    return await gateway.get_enhanced_stats()


async def health_check_with_streams() -> dict:
    """快捷方法：包含 Stream 和重试的健康检查"""
    gateway = await get_stream_enhanced_gateway()
    return await gateway.health_check_with_streams()


async def get_retry_stats() -> dict:
    """获取重试统计信息"""
    gateway = await get_stream_enhanced_gateway()
    stats = await gateway.get_enhanced_stats()
    return stats.get('retry_stats', {})


async def print_retry_report():
    """打印重试报告"""
    gateway = await get_stream_enhanced_gateway()
    gateway.print_retry_report()


async def update_retry_config(
    config_updates: dict,
    operation_type: str = None
):
    """更新重试配置"""
    gateway = await get_stream_enhanced_gateway()
    gateway.update_retry_config(config_updates, operation_type)
    logger.info(f"✅ 重试配置已更新: {config_updates}")


async def enable_retry_function(enable: bool = True):
    """启用或禁用重试功能"""
    gateway = await get_stream_enhanced_gateway()
    gateway.enable_retry_function(enable)
    
    if enable:
        logger.info("✅ 重试功能已启用")
    else:
        logger.info("⏸️  重试功能已禁用")


# 示例：如何在现有系统中集成（重试增强版）
class DatabaseServiceWithStreams:
    """示例：集成 Stream 功能和重试机制的数据服务类"""
    
    def __init__(self, enable_retry: bool = True):
        self.gateway = None
        self.stream_enhanced_gateway = None
        self.enable_retry = enable_retry
        self.retry_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0
        }
    
    async def initialize(self, retry_config: Optional[Dict[str, Any]] = None):
        """初始化服务（带重试配置）"""
        # 获取原有网关
        self.gateway = await get_original_gateway()
        
        # 获取增强网关（带重试）
        self.stream_enhanced_gateway = await get_stream_enhanced_gateway(
            enable_retry=self.enable_retry,
            retry_config=retry_config
        )
        
        logger.info("✅ 数据库服务初始化完成")
        logger.info(f"   - Stream 支持: {'启用' if self.stream_enhanced_gateway.config.redis_stream.enabled else '禁用'}")
        logger.info(f"   - 重试功能: {'启用' if self.enable_retry else '禁用'}")
        
        if self.enable_retry:
            # 打印初始重试配置
            config = self.stream_enhanced_gateway.get_retry_config()
            logger.info(f"   - 重试策略: {config.get('strategy', 'exponential')}")
            logger.info(f"   - 最大重试: {config.get('max_retries', 3)}次")
    
    async def process_news_with_retry(self, news_data: dict) -> bool:
        """
        处理新闻（带重试机制）
        
        Args:
            news_data: 新闻数据
            
        Returns:
            处理是否成功
        """
        self.retry_stats['total_operations'] += 1
        
        try:
            # 1. 验证数据
            if 'title' not in news_data or 'content' not in news_data:
                raise ValueError("新闻数据格式无效")
            
            # 2. 保存到数据库（原有逻辑）
            # 这里可以调用原有网关的方法
            # saved_news = await self.gateway.save_news(news_data)
            
            # 3. 发布到 Stream（带重试）
            message_id = await self.stream_enhanced_gateway.publish_news(news_data)
            
            if message_id:
                logger.info(f"✅ 新闻已处理并发布到 Stream: {message_id}")
                self.retry_stats['successful_operations'] += 1
                return True
            else:
                logger.warning("⚠️  新闻处理成功，但发布到 Stream 失败")
                self.retry_stats['failed_operations'] += 1
                return False
            
        except Exception as e:
            logger.error(f"处理新闻失败: {e}")
            self.retry_stats['failed_operations'] += 1
            return False
    
    async def batch_process_news(self, news_items: list, max_concurrent: int = 3) -> dict:
        """
        批量处理新闻（带并发控制和重试）
        
        Args:
            news_items: 新闻数据列表
            max_concurrent: 最大并发数
            
        Returns:
            处理结果统计
        """
        logger.info(f"📦 批量处理 {len(news_items)} 条新闻...")
        
        # 使用网关的批量发布功能
        results = await self.stream_enhanced_gateway.batch_publish(
            news_items,
            data_type="news",
            max_concurrent=max_concurrent
        )
        
        # 统计结果
        success_count = sum(1 for r in results if r is not None)
        failed_count = len(news_items) - success_count
        
        logger.info(f"📦 批量处理完成: {success_count}/{len(news_items)} 成功")
        
        return {
            "total": len(news_items),
            "success": success_count,
            "failed": failed_count,
            "success_rate": success_count / len(news_items) if news_items else 0
        }
    
    async def create_theme_with_events(self, name: str, code: str, **kwargs):
        """创建主题（发布事件到 Stream，带重试）"""
        return await self.stream_enhanced_gateway.create_theme_with_stream(name, code, **kwargs)
    
    async def update_theme_with_events(self, theme_id: int, updates: dict):
        """更新主题（发布事件到 Stream，带重试）"""
        return await self.stream_enhanced_gateway.update_theme_with_stream(theme_id, updates)
    
    async def get_service_stats(self) -> dict:
        """获取服务统计（包含重试统计）"""
        # 获取网关统计
        gateway_stats = await self.stream_enhanced_gateway.get_enhanced_stats()
        
        # 添加服务特定统计
        return {
            "service": {
                "total_operations": self.retry_stats['total_operations'],
                "successful_operations": self.retry_stats['successful_operations'],
                "failed_operations": self.retry_stats['failed_operations'],
                "success_rate": self.retry_stats['successful_operations'] / max(1, self.retry_stats['total_operations'])
            },
            "gateway": gateway_stats
        }
    
    async def print_service_report(self):
        """打印服务报告"""
        stats = await self.get_service_stats()
        
        print("\n📊 数据库服务报告")
        print("=" * 60)
        print(f"服务运行统计:")
        print(f"  总操作数: {stats['service']['total_operations']}")
        print(f"  成功操作: {stats['service']['successful_operations']}")
        print(f"  失败操作: {stats['service']['failed_operations']}")
        print(f"  成功率: {stats['service']['success_rate']:.1%}")
        
        # 打印网关重试统计
        if 'retry_stats' in stats['gateway']:
            retry_stats = stats['gateway']['retry_stats']
            if isinstance(retry_stats, dict):
                print(f"\n重试系统统计:")
                print(f"  总操作数: {retry_stats.get('total_operations', 0)}")
                print(f"  带重试操作: {retry_stats.get('operations_with_retries', 0)}")
                print(f"  重试成功率: {retry_stats.get('retry_success_rate', 0):.1%}")
        
        print("=" * 60)
    
    async def test_retry_functionality(self):
        """测试重试功能"""
        print("\n🧪 测试重试功能...")
        
        test_data = [
            {"title": "测试新闻1", "content": "测试内容1", "id": "test_001"},
            {"title": "测试新闻2", "content": "测试内容2", "id": "test_002"},
            {"title": "测试新闻3", "content": "测试内容3", "id": "test_003"}
        ]
        
        results = await self.batch_process_news(test_data, max_concurrent=2)
        
        print(f"测试结果: {results['success']}/{results['total']} 成功")
        
        # 打印重试报告
        await print_retry_report()
        
        return results['success_rate'] > 0.5  # 至少50%成功率
    
    async def close(self):
        """关闭服务"""
        if self.gateway:
            await self.gateway.close()
        
        logger.info("✅ 数据库服务已关闭")


# 全局服务实例
_service_instance: Optional[DatabaseServiceWithStreams] = None


async def get_database_service(
    enable_retry: bool = True,
    retry_config: Optional[Dict[str, Any]] = None
) -> DatabaseServiceWithStreams:
    """获取全局数据库服务实例（带重试配置）"""
    global _service_instance
    
    if _service_instance is None:
        _service_instance = DatabaseServiceWithStreams(enable_retry=enable_retry)
        await _service_instance.initialize(retry_config=retry_config)
    
    return _service_instance


async def shutdown_database_service():
    """关闭数据库服务"""
    global _service_instance
    
    if _service_instance:
        await _service_instance.close()
        _service_instance = None
        logger.info("✅ 数据库服务已关闭")


# 示例：如何在现有代码中使用
async def example_usage():
    """使用示例"""
    # 方法1：直接使用快捷方法
    news_data = {"title": "重大新闻", "content": "新闻内容...", "id": "news_123"}
    message_id = await publish_news_to_stream(news_data, enable_retry=True)
    
    if message_id:
        print(f"✅ 新闻发布成功: {message_id}")
    
    # 方法2：获取服务实例
    service = await get_database_service(
        enable_retry=True,
        retry_config={"max_retries": 5, "strategy": "exponential"}
    )
    
    # 批量处理
    news_items = [
        {"title": "新闻1", "content": "内容1", "id": "1"},
        {"title": "新闻2", "content": "内容2", "id": "2"},
        {"title": "新闻3", "content": "内容3", "id": "3"}
    ]
    
    results = await service.batch_process_news(news_items, max_concurrent=3)
    print(f"批量处理结果: {results}")
    
    # 打印报告
    await service.print_service_report()
    
    # 测试重试功能
    await service.test_retry_functionality()


# 启动和关闭钩子
async def startup_event():
    """应用启动时调用"""
    logger.info("🚀 启动 Stream 增强数据库服务...")
    
    # 初始化网关（带重试）
    await initialize_stream_gateway(enable_retry=True)
    
    # 获取服务实例（预热）
    await get_database_service(enable_retry=True)
    
    logger.info("✅ Stream 增强数据库服务启动完成")


async def shutdown_event():
    """应用关闭时调用"""
    logger.info("🛑 关闭 Stream 增强数据库服务...")
    
    await shutdown_database_service()
    
    # 关闭全局网关
    global _stream_enhanced_gateway
    if _stream_enhanced_gateway:
        await _stream_enhanced_gateway.close()
        _stream_enhanced_gateway = None
    
    logger.info("✅ Stream 增强数据库服务已关闭")


if __name__ == "__main__":
    # 运行示例
    import asyncio
    asyncio.run(example_usage())

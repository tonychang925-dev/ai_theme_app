"""
Redis缓存数据库管理器（核心）- 适配28字段表结构
"""
import asyncio
import json
# 修改：使用标准的 redis 库替代 aioredis
try:
    import redis.asyncio as aioredis
except ImportError:
    # 创建模拟的Redis客户端用于测试
    class MockRedis:
        class RedisError(Exception):
            pass
        
        class ResponseError(Exception):
            pass
        
        async def xgroup_create(self, *args, **kwargs):
            pass
        
        async def xadd(self, *args, **kwargs):
            return "mock_id"
        
        async def xread(self, *args, **kwargs):
            return []
        
        async def xreadgroup(self, *args, **kwargs):
            return []
        
        async def publish(self, *args, **kwargs):
            return 1
        
        async def xack(self, *args, **kwargs):
            return 1
        
        async def xinfo_stream(self, *args, **kwargs):
            return {'length': 0}
        
        async def xinfo_groups(self, *args, **kwargs):
            return []
        
        async def xpending_range(self, *args, **kwargs):
            return []
        
        async def xclaim(self, *args, **kwargs):
            return []
    
    aioredis = MockRedis()

from typing import Dict, List, Any, Optional, AsyncContextManager
from datetime import datetime
import logging
import hashlib

from database_service.managers.base_manager import BaseDatabaseManager
# 修改：如果redis_event_bus不存在，创建一个简化版
try:
    from database_service.managers.redis_event_bus import RedisEventBus
    REDIS_EVENT_BUS_AVAILABLE = True
except ImportError:
    REDIS_EVENT_BUS_AVAILABLE = False
    # 创建一个简化的事件总线类
    class RedisEventBus:
        def __init__(self, redis_client, config):
            self.redis = redis_client
            self.config = config
            self.logger = logging.getLogger(__name__)
        
        async def publish(self, event_type: str, event_data: Dict[str, Any]):
            """发布事件 - 简化版本"""
            self.logger.debug(f"发布事件: {event_type} - {event_data}")
        
        async def subscribe(self):
            """订阅事件 - 简化版本"""
            # 返回一个空的异步生成器
            while True:
                await asyncio.sleep(3600)  # 长时间休眠
                yield None, None

from ..interface import ThemeRecord, EventThemeRelation

logger = logging.getLogger(__name__)


class RedisCachedDatabaseManager(BaseDatabaseManager):
    """
    Redis缓存增强的数据库管理器
    策略：所有读操作先查Redis缓存，写操作同步更新缓存
    适配28字段表结构
    """
    
    def __init__(self, postgres_manager: BaseDatabaseManager, config):
        super().__init__(config)
        self.postgres_manager = postgres_manager
        self.redis = None
        self.event_bus = None
        
        # 缓存统计
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'writes': 0,
            'invalidations': 0,
            'errors': 0
        }
        
        # 缓存键前缀
        self.key_prefix = "db:"
        
        # 后台任务
        self.background_tasks = []
        self.running = False
        
        # 测试模式标志
        self.test_mode = False  # 设置为True可以跳过实际Redis连接
    
    async def connect(self) -> None:
        """连接Redis和PostgreSQL"""
        try:
            # 1. 连接PostgreSQL
            await self.postgres_manager.connect()
            
            # 2. 连接Redis - 检查是否需要测试模式
            if not hasattr(self.config, 'redis') or not hasattr(self.config.redis, 'url'):
                logger.warning("Redis配置缺失，启用测试模式")
                self.test_mode = True
                self.redis = None
            else:
                try:
                    redis_config = self.config.redis
                    self.redis = await aioredis.from_url(
                        redis_config.url,
                        max_connections=redis_config.max_connections if hasattr(redis_config, 'max_connections') else 10,
                        encoding='utf-8',
                        decode_responses=True
                    )
                    # 测试连接
                    await self.redis.ping()
                    logger.info("✅ Redis连接成功")
                except Exception as redis_error:
                    logger.warning(f"Redis连接失败，启用降级模式: {redis_error}")
                    self.test_mode = True
                    self.redis = None
            
            # 3. 初始化事件总线
            if self.redis:
                self.event_bus = RedisEventBus(self.redis, self.config)
            
            # 4. 启动后台服务
            if not self.test_mode:
                await self.start_cache_services()
            
            self.connected = True
            logger.info("✅ Redis缓存数据库管理器连接成功")
            
        except Exception as e:
            logger.error(f"❌ 连接失败: {e}")
            # 降级到测试模式
            self.test_mode = True
            self.connected = True
    
    async def start_cache_services(self):
        """启动缓存相关服务"""
        if self.running:
            return
        
        self.running = True
        
        # 只在非测试模式下启动服务
        if not self.test_mode:
            # 启动缓存预热
            if hasattr(self.config, 'cache') and hasattr(self.config.cache, 'enable_cache_warming') and self.config.cache.enable_cache_warming:
                warm_task = asyncio.create_task(self._cache_warming_service())
                self.background_tasks.append(warm_task)
            
            # 启动统计报告
            if hasattr(self.config, 'enable_metrics') and self.config.enable_metrics:
                stats_task = asyncio.create_task(self._stats_reporting_service())
                self.background_tasks.append(stats_task)
            
            # 启动事件监听
            event_task = asyncio.create_task(self._event_listening_service())
            self.background_tasks.append(event_task)
            
            logger.info("🚀 缓存服务已启动")
        else:
            logger.info("📝 缓存服务（测试模式）")
    
    async def disconnect(self) -> None:
        """断开连接"""
        self.running = False
        
        # 取消所有后台任务
        for task in self.background_tasks:
            task.cancel()
        
        # 等待任务完成
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # 关闭连接
        if self.redis:
            await self.redis.close()
        
        await self.postgres_manager.disconnect()
        
        self.connected = False
        logger.info("Redis缓存管理器已关闭")
    
    def transaction(self) -> AsyncContextManager:
        """事务（透传给PostgreSQL）"""
        return self.postgres_manager.transaction()
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查PostgreSQL
            postgres_ok = await self.postgres_manager.health_check()
            
            # 检查Redis（测试模式下总是返回True）
            if self.test_mode or not self.redis:
                redis_ok = True
            else:
                redis_ok = await self.redis.ping()
            
            return redis_ok and postgres_ok
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    # ========== 缓存核心方法 ==========
    
    def _build_cache_key(self, entity_type: str, identifier: Any, suffix: str = "") -> str:
        """构建缓存键"""
        key = f"{self.key_prefix}{entity_type}:{identifier}"
        if suffix:
            key += f":{suffix}"
        return key
    
    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if self.test_mode or not self.redis:
            return None
            
        try:
            cached = await self.redis.get(key)
            if cached:
                self.cache_stats['hits'] += 1
                return json.loads(cached)
            self.cache_stats['misses'] += 1
            return None
        except Exception as e:
            self.cache_stats['errors'] += 1
            logger.debug(f"缓存读取失败 {key}: {e}")
            return None
    
    async def _set_to_cache(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存"""
        if self.test_mode or not self.redis:
            return
            
        try:
            if ttl is None:
                ttl = 300  # 默认5分钟
                if hasattr(self.config, 'redis') and hasattr(self.config.redis, 'cache_ttl'):
                    ttl = self.config.redis.cache_ttl.get('default', 300)
            
            json_value = json.dumps(value, default=str, ensure_ascii=False)
            await self.redis.setex(key, ttl, json_value)
            self.cache_stats['writes'] += 1
        except Exception as e:
            self.cache_stats['errors'] += 1
            logger.debug(f"缓存写入失败 {key}: {e}")
    
    async def _invalidate_cache(self, pattern: str):
        """使缓存失效"""
        if self.test_mode or not self.redis:
            return
            
        try:
            keys = await self.redis.keys(f"{self.key_prefix}{pattern}")
            if keys:
                await self.redis.delete(*keys)
                self.cache_stats['invalidations'] += len(keys)
                logger.debug(f"清除缓存: {pattern} ({len(keys)}个)")
        except Exception as e:
            logger.error(f"缓存失效失败: {e}")
    
    async def _cache_theme_by_code(self, code: str, theme: ThemeRecord):
        """按code缓存主题"""
        cache_key = self._build_cache_key("theme_by_code", code)
        ttl = 3600  # 默认1小时
        if hasattr(self.config, 'redis') and hasattr(self.config.redis, 'cache_ttl'):
            ttl = self.config.redis.cache_ttl.get('theme', 3600)
        
        await self._set_to_cache(cache_key, theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__, ttl)
    
    async def _get_theme_by_code_from_cache(self, code: str) -> Optional[ThemeRecord]:
        """从缓存获取主题（按code）"""
        cache_key = self._build_cache_key("theme_by_code", code)
        cached = await self._get_from_cache(cache_key)
        if cached:
            try:
                return ThemeRecord(**cached)
            except Exception as e:
                logger.warning(f"缓存主题反序列化失败: {e}")
        return None
    
    # ========== 主题操作（带缓存） ==========
    
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """获取主题 - 先查缓存"""
        cache_key = self._build_cache_key("theme", theme_id)
        
        try:
            # 1. 先查缓存
            cached = await self._get_from_cache(cache_key)
            if cached:
                try:
                    return ThemeRecord(**cached)
                except Exception as e:
                    logger.warning(f"缓存主题反序列化失败: {e}")
            
            # 2. 从数据库获取
            theme = await self.postgres_manager.get_theme(theme_id)
            
            if theme:
                # 3. 异步更新缓存
                if not self.test_mode:
                    asyncio.create_task(
                        self._set_to_cache(
                            cache_key, 
                            theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__,
                            3600  # 默认1小时
                        )
                    )
                    
                    # 4. 同时缓存按code查询
                    if theme.code:
                        asyncio.create_task(
                            self._cache_theme_by_code(theme.code, theme)
                        )
            
            return theme
            
        except Exception as e:
            logger.error(f"获取主题失败 {theme_id}: {e}")
            # 降级到直接数据库查询
            return await self.postgres_manager.get_theme(theme_id)
    
    async def get_theme_by_code(self, code: str) -> Optional[ThemeRecord]:
        """获取主题（按code）- 带缓存"""
        try:
            # 1. 先查缓存
            cached = await self._get_theme_by_code_from_cache(code)
            if cached:
                return cached
            
            # 2. 从数据库获取
            theme = await self.postgres_manager.get_theme_by_code(code)
            
            if theme:
                # 3. 更新主题缓存和code缓存
                cache_key = self._build_cache_key("theme", theme.id)
                if not self.test_mode:
                    await self._set_to_cache(
                        cache_key,
                        theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__,
                        3600
                    )
                    
                    await self._cache_theme_by_code(code, theme)
            
            return theme
            
        except Exception as e:
            logger.error(f"按code获取主题失败 {code}: {e}")
            return await self.postgres_manager.get_theme_by_code(code)
    
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        return await self.postgres_manager.get_theme_by_name(name)
    
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """获取所有活跃主题 - 带列表缓存"""
        cache_key = self._build_cache_key("themes", "active", f"limit:{limit}")
        
        try:
            # 1. 检查列表缓存
            cached = await self._get_from_cache(cache_key)
            if cached:
                try:
                    return [ThemeRecord(**data) for data in cached]
                except Exception as e:
                    logger.warning(f"缓存列表反序列化失败: {e}")
            
            # 2. 从数据库获取
            themes = await self.postgres_manager.get_all_active_themes(limit)
            
            if themes and not self.test_mode:
                # 3. 缓存列表
                themes_data = []
                for theme in themes:
                    themes_data.append(theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__)
                
                asyncio.create_task(
                    self._set_to_cache(
                        cache_key,
                        themes_data,
                        1800  # 默认30分钟
                    )
                )
                
                # 4. 异步缓存每个主题
                await self._cache_individual_themes(themes)
            
            return themes
            
        except Exception as e:
            logger.error(f"获取活跃主题失败: {e}")
            return await self.postgres_manager.get_all_active_themes(limit)
    
    async def _cache_individual_themes(self, themes: List[ThemeRecord]):
        """缓存每个主题的详情"""
        if self.test_mode:
            return
            
        tasks = []
        for theme in themes:
            # 缓存主题详情
            cache_key = self._build_cache_key("theme", theme.id)
            task = self._set_to_cache(
                cache_key,
                theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__,
                3600
            )
            tasks.append(task)
            
            # 缓存code查询
            if theme.code:
                task = self._cache_theme_by_code(theme.code, theme)
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def create_theme(self, name: str, code: str, **kwargs) -> ThemeRecord:
        """创建主题 - 同步更新缓存"""
        try:
            # 在事务中执行
            async with self.transaction():
                # 1. 创建主题
                theme = await self.postgres_manager.create_theme(name, code, **kwargs)
                
                if theme and not self.test_mode:
                    # 2. 同步更新缓存
                    cache_key = self._build_cache_key("theme", theme.id)
                    await self._set_to_cache(
                        cache_key,
                        theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__,
                        3600
                    )
                    
                    # 3. 缓存code查询
                    await self._cache_theme_by_code(code, theme)
                    
                    # 4. 使列表缓存失效
                    await self._invalidate_cache("themes:active:*")
                    await self._invalidate_cache("themes_by_category:*")
                    await self._invalidate_cache("themes_by_heat:*")
                    
                    # 5. 发布事件
                    if self.event_bus:
                        await self.event_bus.publish('theme_created', {
                            'theme_id': theme.id,
                            'name': theme.name,
                            'code': theme.code,
                            'timestamp': datetime.now().isoformat()
                        })
                    
                    logger.info(f"✅ 创建主题并更新缓存: {name} (code: {code})")
                
                return theme
                
        except Exception as e:
            logger.error(f"创建主题失败: {e}")
            raise
    
    async def update_theme(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题 - 同步更新缓存"""
        try:
            # 先获取旧主题信息（用于清理code缓存）
            old_theme = await self.get_theme(theme_id)
            
            # 更新主题
            theme = await self.postgres_manager.update_theme(theme_id, updates)
            
            if theme and not self.test_mode:
                # 更新缓存
                cache_key = self._build_cache_key("theme", theme_id)
                await self._set_to_cache(cache_key, theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__, 3600)
                
                # 更新code缓存
                if theme.code:
                    await self._cache_theme_by_code(theme.code, theme)
                
                # 清理旧code缓存（如果code有变更）
                if old_theme and old_theme.code != theme.code:
                    old_cache_key = self._build_cache_key("theme_by_code", old_theme.code)
                    if self.redis:
                        await self.redis.delete(old_cache_key)
                
                # 使相关缓存失效
                await self._invalidate_cache("themes:active:*")
                await self._invalidate_cache("themes_by_category:*")
                await self._invalidate_cache("themes_by_heat:*")
                await self._invalidate_cache("related:*")
                
                # 发布事件
                if self.event_bus:
                    await self.event_bus.publish('theme_updated', {
                        'theme_id': theme_id,
                        'updates': updates,
                        'timestamp': datetime.now().isoformat()
                    })
                
                logger.info(f"✅ 更新主题缓存: {theme.name} (ID: {theme_id})")
            
            return theme
            
        except Exception as e:
            logger.error(f"更新主题缓存失败 {theme_id}: {e}")
            return await self.postgres_manager.update_theme(theme_id, updates)
    
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度"""
        await self.postgres_manager.increment_theme_heat(theme_id, increment)
        
        # 使相关缓存失效
        if not self.test_mode:
            await self._invalidate_cache(f"theme:{theme_id}*")
            await self._invalidate_cache("themes:active:*")
            await self._invalidate_cache("themes_by_heat:*")
    
    async def increment_mention_count(self, theme_id: int, increment: int = 1) -> None:
        """增加提及次数"""
        await self.postgres_manager.increment_mention_count(theme_id, increment)
        
        # 使相关缓存失效
        if not self.test_mode:
            await self._invalidate_cache(f"theme:{theme_id}*")
            await self._invalidate_cache("themes:active:*")
    
    async def find_related_themes(self, event_data: Dict[str, Any], limit: int = 5) -> List[ThemeRecord]:
        """查找相关主题 - 智能缓存"""
        # 基于事件内容生成缓存key
        content_hash = hashlib.md5(
            json.dumps(event_data, sort_keys=True).encode()
        ).hexdigest()[:12]
        
        cache_key = self._build_cache_key("related", content_hash, f"limit:{limit}")
        
        try:
            # 1. 检查缓存
            cached = await self._get_from_cache(cache_key)
            if cached:
                try:
                    return [ThemeRecord(**data) for data in cached]
                except Exception as e:
                    logger.warning(f"缓存相关主题反序列化失败: {e}")
            
            # 2. 执行查询
            themes = await self.postgres_manager.find_related_themes(event_data, limit)
            
            if themes and not self.test_mode:
                # 3. 缓存结果
                themes_data = []
                for theme in themes:
                    themes_data.append(theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__)
                
                await self._set_to_cache(
                    cache_key,
                    themes_data,
                    1800  # 默认30分钟
                )
                
                # 4. 缓存主题详情
                await self._cache_individual_themes(themes)
            
            return themes
            
        except Exception as e:
            logger.error(f"查找相关主题失败: {e}")
            return await self.postgres_manager.find_related_themes(event_data, limit)
    
    async def get_themes_by_keywords(self, keywords: List[str], limit: int = 20) -> List[ThemeRecord]:
        """根据关键词获取主题 - 带缓存"""
        # 生成缓存key
        keywords_key = hashlib.md5(json.dumps(sorted(keywords)).encode()).hexdigest()[:12]
        cache_key = self._build_cache_key("themes_by_keywords", keywords_key, f"limit:{limit}")
        
        try:
            # 检查缓存
            cached = await self._get_from_cache(cache_key)
            if cached:
                try:
                    return [ThemeRecord(**data) for data in cached]
                except Exception as e:
                    logger.warning(f"缓存关键词主题反序列化失败: {e}")
            
            # 从数据库获取
            themes = await self.postgres_manager.get_themes_by_keywords(keywords, limit)
            
            if themes and not self.test_mode:
                # 缓存结果
                themes_data = []
                for theme in themes:
                    themes_data.append(theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__)
                
                await self._set_to_cache(
                    cache_key,
                    themes_data,
                    1800
                )
                
                # 缓存主题详情
                await self._cache_individual_themes(themes)
            
            return themes
            
        except Exception as e:
            logger.error(f"关键词搜索缓存失败: {e}")
            return await self.postgres_manager.get_themes_by_keywords(keywords, limit)
    
    async def get_themes_by_category(self, category_code: str, level: int = 1, limit: int = 50) -> List[ThemeRecord]:
        """根据分类代码获取主题 - 带缓存"""
        cache_key = self._build_cache_key("themes_by_category", f"{level}:{category_code}", f"limit:{limit}")
        
        try:
            # 检查缓存
            cached = await self._get_from_cache(cache_key)
            if cached:
                try:
                    return [ThemeRecord(**data) for data in cached]
                except Exception as e:
                    logger.warning(f"缓存分类主题反序列化失败: {e}")
            
            # 从数据库获取
            themes = await self.postgres_manager.get_themes_by_category(category_code, level, limit)
            
            if themes and not self.test_mode:
                # 缓存结果
                themes_data = []
                for theme in themes:
                    themes_data.append(theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__)
                
                await self._set_to_cache(
                    cache_key,
                    themes_data,
                    1800
                )
                
                # 缓存主题详情
                await self._cache_individual_themes(themes)
            
            return themes
            
        except Exception as e:
            logger.error(f"分类查询缓存失败: {e}")
            return await self.postgres_manager.get_themes_by_category(category_code, level, limit)
    
    async def get_themes_by_heat_level(self, min_heat: int = 60, limit: int = 100) -> List[ThemeRecord]:
        """获取热度较高的主题 - 带缓存"""
        cache_key = self._build_cache_key("themes_by_heat", f"min{min_heat}", f"limit:{limit}")
        
        try:
            # 检查缓存
            cached = await self._get_from_cache(cache_key)
            if cached:
                try:
                    return [ThemeRecord(**data) for data in cached]
                except Exception as e:
                    logger.warning(f"缓存高热主题反序列化失败: {e}")
            
            # 从数据库获取
            themes = await self.postgres_manager.get_themes_by_heat_level(min_heat, limit)
            
            if themes and not self.test_mode:
                # 缓存结果
                themes_data = []
                for theme in themes:
                    themes_data.append(theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__)
                
                await self._set_to_cache(
                    cache_key,
                    themes_data,
                    1800
                )
                
                # 缓存主题详情
                await self._cache_individual_themes(themes)
            
            return themes
            
        except Exception as e:
            logger.error(f"热度查询缓存失败: {e}")
            return await self.postgres_manager.get_themes_by_heat_level(min_heat, limit)
    
    async def search_themes(self, query: str, limit: int = 10) -> List[ThemeRecord]:
        """搜索主题 - 带缓存"""
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
        cache_key = self._build_cache_key("search", query_hash, f"limit:{limit}")
        
        try:
            # 检查缓存
            cached = await self._get_from_cache(cache_key)
            if cached:
                try:
                    return [ThemeRecord(**data) for data in cached]
                except Exception as e:
                    logger.warning(f"缓存搜索主题反序列化失败: {e}")
            
            # 从数据库获取
            themes = await self.postgres_manager.search_themes(query, limit)
            
            if themes and not self.test_mode:
                # 缓存结果
                themes_data = []
                for theme in themes:
                    themes_data.append(theme.to_dict() if hasattr(theme, 'to_dict') else theme.__dict__)
                
                await self._set_to_cache(
                    cache_key,
                    themes_data,
                    1800
                )
                
                # 缓存主题详情
                await self._cache_individual_themes(themes)
            
            return themes
            
        except Exception as e:
            logger.error(f"搜索缓存失败: {e}")
            return await self.postgres_manager.search_themes(query, limit)
    
    # ========== 批量操作 ==========
    
    async def batch_create_themes(self, themes_data: List[Dict[str, Any]]) -> List[ThemeRecord]:
        """批量创建主题"""
        themes = await self.postgres_manager.batch_create_themes(themes_data)
        if themes and not self.test_mode:
            # 缓存主题详情
            await self._cache_individual_themes(themes)
            
            # 使列表缓存失效
            await self._invalidate_cache("themes:active:*")
            await self._invalidate_cache("themes_by_category:*")
            await self._invalidate_cache("themes_by_heat:*")
            
            # 发布事件
            if self.event_bus:
                await self.event_bus.publish('themes_batch_created', {
                    'count': len(themes),
                    'timestamp': datetime.now().isoformat()
                })
            
            logger.info(f"✅ 批量创建 {len(themes)} 个主题并更新缓存")
        
        return themes
    
    # ========== 其他缓存方法 ==========
    
    async def clear_cache(self, pattern: str = "*") -> int:
        """清除缓存"""
        try:
            if self.test_mode or not self.redis:
                return 0
                
            full_pattern = f"{self.key_prefix}{pattern}"
            keys = await self.redis.keys(full_pattern)
            if keys:
                await self.redis.delete(*keys)
                logger.info(f"清除缓存: {pattern} ({len(keys)}个键)")
                return len(keys)
            return 0
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        if self.test_mode or not self.redis:
            return self.cache_stats.copy()
            
        try:
            redis_info = await self.redis.info()
            
            stats = self.cache_stats.copy()
            stats.update({
                'redis_memory_used': redis_info.get('used_memory_human', 'N/A'),
                'redis_connected_clients': redis_info.get('connected_clients', 0),
                'redis_keyspace_hits': redis_info.get('keyspace_hits', 0),
                'redis_keyspace_misses': redis_info.get('keyspace_misses', 0),
                'cache_hit_rate': stats['hits'] / max(stats['hits'] + stats['misses'], 1),
                'test_mode': self.test_mode
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            stats = self.cache_stats.copy()
            stats['test_mode'] = True
            return stats
    
    # ========== 后台服务 ==========
    
    async def _cache_warming_service(self):
        """缓存预热服务"""
        if self.test_mode:
            return
            
        logger.info("🔥 启动缓存预热服务...")
        
        while self.running:
            try:
                # 预热活跃主题
                warm_items = 100  # 默认值
                if hasattr(self.config, 'cache') and hasattr(self.config.cache, 'warm_cache_items'):
                    warm_items = self.config.cache.warm_cache_items
                    
                themes = await self.postgres_manager.get_all_active_themes(warm_items)
                
                if themes:
                    await self._cache_individual_themes(themes)
                    logger.info(f"🔥 预热 {len(themes)} 个主题缓存")
                
                # 预热高热主题
                hot_themes = await self.postgres_manager.get_themes_by_heat_level(80, 50)
                if hot_themes:
                    logger.info(f"🔥 预热 {len(hot_themes)} 个高热主题")
                
                # 每10分钟预热一次
                await asyncio.sleep(600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"缓存预热失败: {e}")
                await asyncio.sleep(60)
    
    async def _stats_reporting_service(self):
        """统计报告服务"""
        while self.running:
            try:
                if not self.test_mode:
                    stats = await self.get_cache_stats()
                    hit_rate = stats.get('cache_hit_rate', 0)
                    
                    if hit_rate < 0.6:
                        logger.warning(f"⚠️  缓存命中率较低: {hit_rate:.1%}")
                    else:
                        logger.info(f"📊 缓存命中率: {hit_rate:.1%}")
                
                # 每小时报告一次
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"统计报告失败: {e}")
                await asyncio.sleep(300)
    
    async def _event_listening_service(self):
        """事件监听服务"""
        if self.test_mode or not self.event_bus:
            return
            
        while self.running:
            try:
                # 监听数据库事件，实时更新缓存
                async for event_type, event_data in self.event_bus.subscribe():
                    if event_type == 'theme_updated':
                        # 主题更新，刷新缓存
                        theme_id = event_data.get('theme_id')
                        if theme_id:
                            await self._invalidate_cache(f"theme:{theme_id}*")
                            await self._invalidate_cache(f"theme_by_code:*")
                    
                    elif event_type == 'relation_created':
                        # 关联创建，使相关缓存失效
                        await self._invalidate_cache("related:*")
                        await self._invalidate_cache("themes:active:*")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"事件监听失败: {e}")
                await asyncio.sleep(1)
    
    # ========== 透传方法 ==========
    
    async def create_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> EventThemeRelation:
        relation = await self.postgres_manager.create_event_theme_relation(event_id, theme_id, **kwargs)
        if relation and not self.test_mode:
            # 使相关缓存失效
            await self._invalidate_cache("related:*")
            await self._invalidate_cache(f"theme:{theme_id}*")
            await self._invalidate_cache("themes:active:*")
            
            # 发布事件
            if self.event_bus:
                await self.event_bus.publish('relation_created', {
                    'event_id': event_id,
                    'theme_id': theme_id,
                    'relation_id': relation.id,
                    'timestamp': datetime.now().isoformat()
                })
        return relation
    
    async def get_event_themes(self, event_id: int) -> List[EventThemeRelation]:
        return await self.postgres_manager.get_event_themes(event_id)
    
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        return await self.postgres_manager.get_theme_events(theme_id, limit)
    
    async def update_event_theme_relation(self, relation_id: int, updates: Dict[str, Any]) -> Optional[EventThemeRelation]:
        return await self.postgres_manager.update_event_theme_relation(relation_id, updates)
    
    async def mark_event_processed(self, event_id: int) -> None:
        await self.postgres_manager.mark_event_processed(event_id)
    
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.postgres_manager.get_unprocessed_events(limit)
    
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        return await self.postgres_manager.get_event(event_id)
    
    async def get_stats(self) -> Dict[str, Any]:
        stats = await self.postgres_manager.get_stats()
        cache_stats = await self.get_cache_stats()
        stats['cache'] = cache_stats
        return stats
    
    async def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        return await self.postgres_manager.execute_query(query, params)
    
    async def create_news(self, news_data: Dict[str, Any]) -> Optional[str]:
        """
        创建新闻（带缓存）
        
        Args:
            news_data: 新闻数据，必须包含news_id
            
        Returns:
            news_id: 新闻唯一标识，失败返回None
        """
        try:
            # 验证数据
            if 'news_id' not in news_data:
                logger.error("创建新闻失败：缺少news_id")
                return None
            
            news_id = news_data['news_id']
            logger.info(f"📝 开始创建新闻: {news_id}")
            
            # 1. 保存到PostgreSQL
            db_news_id = await self.postgres_manager.create_news(news_data)
            
            if db_news_id:
                # 2. 更新缓存
                await self._update_news_cache(db_news_id, news_data)
                
                # 3. 更新统计
                self.cache_stats['writes'] += 1
                
                logger.info(f"✅ 创建新闻成功: {db_news_id}")
                return db_news_id
            else:
                logger.error(f"❌ 创建新闻失败（数据库层）: {news_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 创建新闻失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _update_news_cache(self, news_id: str, news_data: Dict[str, Any]) -> None:
        """更新新闻缓存"""
        try:
            if self.redis and not self.test_mode:
                cache_key = self._build_cache_key("news", news_id)
                ttl = self.config.redis.cache_ttl.get('news', 300)  # 默认5分钟
                
                # 准备缓存数据
                cache_data = {
                    'data': news_data,
                    'cached_at': datetime.now().isoformat(),
                    'source': 'redis_cached_manager',
                    'version': '1.0'
                }
                
                # 设置缓存
                await self.redis.setex(
                    cache_key,
                    ttl,
                    json.dumps(cache_data, ensure_ascii=False)
                )
                
                logger.debug(f"💾 更新新闻缓存: {news_id}")
                
        except Exception as e:
            logger.warning(f"⚠️ 更新新闻缓存失败: {e}")
    
    async def get_news(self, news_id: str) -> Optional[Dict[str, Any]]:
        """获取新闻（优先缓存）"""
        try:
            logger.debug(f"🔍 获取新闻: {news_id}")
            
            # 1. 尝试从缓存获取
            cache_key = self._build_cache_key("news", news_id)
            
            if self.redis and not self.test_mode:
                cached = await self.redis.get(cache_key)
                if cached:
                    try:
                        cache_data = json.loads(cached)
                        self.cache_stats['hits'] += 1
                        logger.debug(f"⚡ 新闻缓存命中: {news_id}")
                        return cache_data['data']
                    except json.JSONDecodeError:
                        logger.warning(f"新闻缓存数据格式错误: {news_id}")
            
            # 2. 缓存未命中，从数据库获取
            self.cache_stats['misses'] += 1
            logger.debug(f"💾 新闻缓存未命中，查询数据库: {news_id}")
            
            news_data = await self.postgres_manager.get_news(news_id)
            
            if news_data:
                # 3. 异步更新缓存
                asyncio.create_task(self._update_news_cache(news_id, news_data))
                return news_data
            
            logger.warning(f"未找到新闻: {news_id}")
            return None
            
        except Exception as e:
            logger.error(f"获取新闻失败 {news_id}: {e}")
            return None
    
    async def get_recent_news(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的新闻（带缓存）"""
        try:
            logger.debug(f"🔍 获取最近 {limit} 条新闻")
            
            cache_key = self._build_cache_key("news_recent", f"limit:{limit}")
            
            # 1. 尝试从缓存获取
            if self.redis and not self.test_mode:
                cached = await self.redis.get(cache_key)
                if cached:
                    try:
                        cache_data = json.loads(cached)
                        self.cache_stats['hits'] += 1
                        logger.debug(f"⚡ 最近新闻列表缓存命中: {limit}条")
                        return cache_data['data']
                    except Exception:
                        logger.warning("最近新闻列表缓存数据格式错误")
            
            # 2. 数据库查询
            self.cache_stats['misses'] += 1
            news_list = await self.postgres_manager.get_recent_news(limit)
            
            # 3. 异步缓存
            if news_list:
                asyncio.create_task(self._cache_recent_news(news_list, limit))
            
            logger.info(f"✅ 获取到 {len(news_list)} 条最近新闻")
            return news_list
            
        except Exception as e:
            logger.error(f"获取最近新闻失败: {e}")
            return []
    
    async def _cache_recent_news(self, news_list: List[Dict[str, Any]], limit: int) -> None:
        """缓存最近新闻列表"""
        try:
            if self.redis and not self.test_mode:
                cache_key = self._build_cache_key("news_recent", f"limit:{limit}")
                ttl = self.config.redis.cache_ttl.get('news_list', 60)  # 默认1分钟
                
                cache_data = {
                    'data': news_list,
                    'cached_at': datetime.now().isoformat(),
                    'count': len(news_list),
                    'source': 'redis_cached_manager'
                }
                
                await self.redis.setex(
                    cache_key,
                    ttl,
                    json.dumps(cache_data, ensure_ascii=False)
                )
                
                logger.debug(f"💾 缓存最近新闻列表: {len(news_list)}条")
                
        except Exception as e:
            logger.warning(f"⚠️ 缓存新闻列表失败: {e}")
    
    async def clear_news_cache(self, news_id: str = None):
        """清除新闻缓存"""
        try:
            if self.redis and not self.test_mode:
                if news_id:
                    # 清除特定新闻缓存
                    cache_key = self._build_cache_key("news", news_id)
                    await self.redis.delete(cache_key)
                    logger.info(f"✅ 清除新闻缓存: {news_id}")
                else:
                    # 清除所有新闻相关缓存
                    news_keys = await self.redis.keys("db:news:*")
                    if news_keys:
                        await self.redis.delete(*news_keys)
                        logger.info(f"✅ 清除所有新闻缓存: {len(news_keys)}个键")
                        
        except Exception as e:
            logger.error(f"清除新闻缓存失败: {e}")

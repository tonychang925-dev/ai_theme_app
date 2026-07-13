"""
统一数据库网关 - 对外唯一入口
所有服务都通过这个网关访问数据库
适配28字段表结构
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime
from functools import wraps
import time
from uuid import uuid4

try:
    # 先尝试绝对导入（当gateway.py作为顶级模块导入时）
    from database_service.factory import DatabaseManagerFactory
    from database_service.config import get_config, DatabaseConfig
    from database_service.interface import ThemeRecord, EventThemeRelation, ThemeTags
except ImportError:
    # 如果绝对导入失败，尝试相对导入（正常包结构时）
    try:
        from .factory import DatabaseManagerFactory
        from .config import get_config, DatabaseConfig
        from .interface import ThemeRecord, EventThemeRelation, ThemeTags
    except ImportError as e:
        # 如果都失败，打印错误信息
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ 无法导入依赖模块: {e}")
        logger.error("请确保database_service包在Python路径中")
        
        # 重新抛出异常，让调用者知道问题
        raise ImportError(f"gateway.py导入失败: {e}")

logger = logging.getLogger(__name__)


class DatabaseGateway:
    """
    统一数据库网关
    设计模式：单例模式 + 门面模式
    适配28字段表结构
    """
    
    _instance = None
    _client = None
    _read_client = None
    _initialized = False
    _config = None
    
    def __init__(self):
        """私有构造函数"""
        if DatabaseGateway._instance is not None:
            raise Exception("DatabaseGateway是单例，请使用get_instance()")

        self._client = None
        self._read_client = None
        self._initialized = False
        self._event_handlers = {}
        self._idempotency_store: Dict[str, Dict[str, Any]] = {}
        self._stats = {
            'requests': 0,
            'success': 0,
            'errors': 0,
            'response_times': []
        }
        # In-flight DB operation tracking for safe reconnect
        self._inflight = 0
        self._inflight_lock = asyncio.Lock()
        self._pending_old_pools: List[asyncio.Task] = []
        self._reconnect_health_failures = 0
    
    @classmethod
    async def initialize(cls, config: Optional[DatabaseConfig] = None, 
                        auto_warm_cache: bool = True) -> 'DatabaseGateway':
        """初始化网关（应用启动时调用）"""
        if cls._instance is None:
            cls._instance = cls()
        
        if not cls._instance._initialized:
            cls._instance._config = config or get_config()
            
            # 打印配置摘要
            logger.info("=" * 60)
            logger.info("🚪 DatabaseGateway 初始化")
            logger.info(f"   数据库类型: {cls._instance._config.db_type.value}")
            logger.info(f"   表结构: 28字段表")
            
            if cls._instance._config.db_type.value != "memory":
                table_names = cls._instance._config.table_names
                if isinstance(table_names, dict):
                    theme_table = table_names.get("theme_master", "theme_master")
                else:
                    theme_table = getattr(table_names, "theme_master", "theme_master")
                logger.info(f"   主题表: {theme_table}")
            
            # 创建客户端
            from database_service.managers.postgres_manager import PostgresDatabaseManager
            cls._instance._client = PostgresDatabaseManager(cls._instance._config)
            await cls._instance._client.connect()

            read_database = (
                os.getenv("READ_PG_DATABASE")
                or os.getenv("READ_DB_NAME")
                or os.getenv("JYHF_READ_DATABASE")
                or ""
            ).strip()
            if read_database and read_database != cls._instance._config.postgres_database:
                read_config = DatabaseConfig(
                    db_type=cls._instance._config.db_type,
                    postgres_host=cls._instance._config.postgres_host,
                    postgres_port=cls._instance._config.postgres_port,
                    postgres_database=read_database,
                    postgres_username=cls._instance._config.postgres_username,
                    postgres_password=cls._instance._config.postgres_password,
                    postgres_schema=cls._instance._config.postgres_schema,
                    postgres_ssl_mode=cls._instance._config.postgres_ssl_mode,
                    postgres_pool_size=cls._instance._config.postgres_pool_size,
                    connection_pool=cls._instance._config.connection_pool,
                    redis=cls._instance._config.redis,
                    cache=cls._instance._config.cache,
                    table_names_config=cls._instance._config.table_names_config,
                )
                cls._instance._read_client = PostgresDatabaseManager(read_config)
                await cls._instance._read_client.connect()
                logger.info("   只读库: %s", read_database)
            
            cls._instance._initialized = True
            
            # 注册事件处理器
            await cls._instance._register_event_handlers()
            
            # 缓存预热
            if auto_warm_cache and cls._instance._config.cache.enable_cache_warming:
                await cls._instance.warm_cache()
            
            logger.info("✅ DatabaseGateway 初始化完成")
            logger.info("=" * 60)
            
            # 启动后台任务
            await cls._instance._start_background_tasks()
        
        return cls._instance

    def _read_source(self):
        return self._read_client or self._client
    
    @classmethod
    async def get_instance(cls) -> 'DatabaseGateway':
        """获取网关实例（惰性初始化）"""
        if cls._instance is None:
            await cls.initialize()
        elif not cls._instance._initialized:
            await cls._instance._reconnect()
        
        return cls._instance
    
    async def _reconnect(self):
        """Non-destructive reconnect: create new pool → swap → gracefully close old.

        The old pool is NOT closed immediately — in-flight handlers may still be
        using it. Instead we defer the close by OLD_POOL_GRACE_SECONDS to avoid
        'pool is closing' cascading failures.
        """
        OLD_POOL_GRACE_SECONDS = 30.0

        try:
            logger.warning("🔄 尝试重新连接数据库...")

            # 1. Create new manager and connect it FIRST
            from database_service.managers.postgres_manager import PostgresDatabaseManager
            new_client = PostgresDatabaseManager(self._config)
            await new_client.connect()

            # 2. Swap atomically — new operations use new pool immediately
            old_client = self._client
            self._client = new_client
            self._initialized = True

            # 3. Schedule graceful close of old pool
            #    Give in-flight handlers OLD_POOL_GRACE_SECONDS to finish their
            #    current DB operation before we close the pool underneath them.
            if old_client and hasattr(old_client, 'pool') and old_client.pool is not None:
                old_pool = old_client.pool

                async def _graceful_close():
                    await asyncio.sleep(OLD_POOL_GRACE_SECONDS)
                    try:
                        # Wait for in-flight ops on the old pool to drain
                        waited = 0.0
                        while self._inflight > 0 and waited < 60.0:
                            await asyncio.sleep(1.0)
                            waited += 1.0
                        await old_pool.close()
                        logger.info("✅ 旧数据库连接池已关闭 (grace=%.0fs)", OLD_POOL_GRACE_SECONDS + waited)
                    except Exception as e:
                        logger.warning("关闭旧连接池时出错: %s", e)

                task = asyncio.create_task(_graceful_close())
                self._pending_old_pools.append(task)

            self._reconnect_health_failures = 0
            logger.info("✅ DatabaseGateway 重新连接成功 (non-destructive)")

        except Exception as e:
            logger.error(f"❌ 重新连接失败: {e}")
            self._initialized = False
            raise
    
    async def _register_event_handlers(self):
        """注册事件处理器"""
        # 这里可以注册对数据库事件的处理
        # 例如，当主题创建时，触发其他服务
        pass
    
    async def _start_background_tasks(self):
        """启动后台任务"""
        # 1. 定期健康检查
        if self._config.enable_health_check:
            asyncio.create_task(self._health_check_task())
        
        # 2. 缓存统计报告
        if self._config.enable_metrics:
            asyncio.create_task(self._metrics_report_task())
        
        # 3. 统计收集任务
        if self._config.enable_metrics:
            asyncio.create_task(self._stats_collection_task())
        
        logger.info("📊 后台任务已启动")
    
    async def _health_check_task(self):
        """健康检查后台任务（带重试容错，避免误触发破坏性重连）"""
        check_interval = self._config.health_check_interval
        MAX_CONSECUTIVE_FAILURES = 3  # require 3 consecutive failures before reconnect

        while True:
            try:
                healthy = await self.health_check()

                if healthy:
                    self._reconnect_health_failures = 0
                else:
                    self._reconnect_health_failures += 1
                    logger.warning(
                        "⚠️  数据库健康检查失败 (%d/%d)",
                        self._reconnect_health_failures,
                        MAX_CONSECUTIVE_FAILURES,
                    )
                    # Only reconnect after consecutive failures — avoids
                    # triggering a destructive pool swap on transient errors
                    if self._reconnect_health_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.warning("⚠️  连续 %d 次健康检查失败，尝试重新连接...",
                                       self._reconnect_health_failures)
                        try:
                            await self._reconnect()
                        except Exception:
                            logger.error("重连失败，将稍后重试")

                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查任务错误: {e}")
                await asyncio.sleep(60)
    
    async def _metrics_report_task(self):
        """指标报告后台任务"""
        report_interval = 300  # 5分钟
        
        while True:
            try:
                stats = await self.get_stats()
                cache_stats = stats.get('cache', {})
                
                if cache_stats:
                    hit_rate = cache_stats.get('cache_hit_rate', 0)
                    hits = cache_stats.get('hits', 0)
                    misses = cache_stats.get('misses', 0)
                    
                    logger.info(f"📊 缓存统计 - 命中率: {hit_rate:.1%} ({hits}/{hits+misses})")
                
                # 网关自身统计
                total_req = self._stats['requests']
                success_req = self._stats['success']
                if total_req > 0:
                    success_rate = success_req / total_req
                    logger.info(f"📊 网关统计 - 成功率: {success_rate:.1%} ({success_req}/{total_req})")
                
                await asyncio.sleep(report_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标报告错误: {e}")
                await asyncio.sleep(report_interval)
    
    async def _stats_collection_task(self):
        """统计收集任务"""
        collection_interval = 3600  # 每小时
        
        while True:
            try:
                # 记录性能指标
                if self._stats['response_times']:
                    avg_time = sum(self._stats['response_times']) / len(self._stats['response_times'])
                    logger.debug(f"⏱️  平均响应时间: {avg_time:.3f}秒")
                    self._stats['response_times'].clear()  # 清空历史数据
                
                await asyncio.sleep(collection_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"统计收集错误: {e}")
                await asyncio.sleep(collection_interval)
    
    # ========== 主题操作（适配28字段） ==========
    
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """获取主题（按ID）"""
        try:
            start_time = time.time()
            result = await self._client.get_theme(theme_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取主题失败 {theme_id}: {e}")
            raise

    @asynccontextmanager
    async def _db_op(self):
        """Track an in-flight DB operation for safe reconnect draining."""
        self._inflight += 1
        try:
            yield
        finally:
            self._inflight -= 1

    async def create_news(self, news_data: Dict[str, Any]) -> Optional[str]:
        """创建 news_raw 记录"""
        try:
            start_time = time.time()
            async with self._db_op():
                result = await self._client.create_news(news_data)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"创建新闻失败: {e}")
            raise

    async def get_news(self, news_id: str) -> Optional[Dict[str, Any]]:
        """按外部 news_id 获取 news_raw 记录"""
        try:
            start_time = time.time()
            async with self._db_op():
                result = await self._client.get_news(news_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取新闻失败 {news_id}: {e}")
            raise

    async def get_subject_stock_pool_by_trade_date(self, trade_date) -> List[Dict[str, Any]]:
        """按交易日读取题材股票池快照。"""
        try:
            start_time = time.time()
            source = self._read_source()
            fn = getattr(source, "get_subject_stock_pool_by_trade_date", None)
            if not callable(fn):
                fn = getattr(source, "get_subject_stock_daily_snapshot_by_trade_date", None)
            if not callable(fn):
                return []
            result = await fn(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取题材股票池失败 trade_date={trade_date}: {e}")
            raise

    async def get_trade_calendar(self, trade_date) -> Dict[str, Any]:
        """股票域显式读取：交易日历信息。"""
        try:
            start_time = time.time()
            result = await self._client.get_trade_calendar(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取交易日历失败 trade_date={trade_date}: {e}")
            raise

    async def get_stock_daily_bars(self, trade_date, stock_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """股票域显式读取：日线行情快照。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_daily_bars(trade_date, stock_ids=stock_ids)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取日线行情失败 trade_date={trade_date}: {e}")
            raise

    async def get_stock_daily_bars_range(
        self,
        start_date,
        end_date,
        stock_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：区间日线行情。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_daily_bars_range(
                start_date,
                end_date,
                stock_ids=stock_ids,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取区间日线失败 start={start_date}, end={end_date}: {e}")
            raise

    async def get_subject_stock_daily_bars_range(
        self,
        start_date,
        end_date,
        stock_ids: Optional[List[str]] = None,
        subject_keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：主题股票区间日线。"""
        try:
            start_time = time.time()
            result = await self._client.get_subject_stock_daily_bars_range(
                start_date,
                end_date,
                stock_ids=stock_ids,
                subject_keys=subject_keys,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取主题区间日线失败 start={start_date}, end={end_date}: {e}")
            raise

    async def get_stock_auction_snapshot(self, trade_date, stock_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """股票域显式读取：竞价快照（当前可降级为日频代理）。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_auction_snapshot(trade_date, stock_ids=stock_ids)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取竞价快照失败 trade_date={trade_date}: {e}")
            raise

    async def upsert_pre_market_auction_snapshots(self, snapshots: List[Dict[str, Any]]) -> int:
        try:
            start_time = time.time()
            result = await self._client.upsert_pre_market_auction_snapshots(snapshots)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入竞价快照失败 snapshots={len(snapshots)}: {e}")
            raise

    async def get_subject_context_by_subject_keys(self, subject_keys: List[str], trade_date) -> List[Dict[str, Any]]:
        """股票域显式读取：题材上下文。"""
        try:
            start_time = time.time()
            result = await self._client.get_subject_context_by_subject_keys(subject_keys, trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取题材上下文失败 trade_date={trade_date}: {e}")
            raise

    async def resolve_theme_name_map(
        self,
        subject_keys: List[str],
        trade_date=None,
    ) -> Dict[str, str]:
        """股票域显式读取：subject_key -> 题材展示名。"""
        try:
            start_time = time.time()
            result = await self._client.resolve_theme_name_map(subject_keys, trade_date)
            self._record_request(True, start_time)
            return dict(result or {})
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"解析题材名称失败 trade_date={trade_date}: {e}")
            raise

    async def get_prior_stock_daily_snapshots(
        self,
        trade_date,
        lookback_days: int,
        stock_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：历史窗口日线快照。"""
        try:
            start_time = time.time()
            result = await self._client.get_prior_stock_daily_snapshots(
                trade_date,
                lookback_days=lookback_days,
                stock_ids=stock_ids,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取历史窗口快照失败 trade_date={trade_date}, lookback={lookback_days}: {e}")
            raise

    async def get_existing_pre_market_brief_snapshot(self, trade_date) -> Optional[Dict[str, Any]]:
        """股票域显式读取：盘前快照文档。"""
        return await self.get_pre_market_brief_snapshot(trade_date)

    async def get_pre_market_brief_snapshot(self, trade_date) -> Optional[Dict[str, Any]]:
        """股票域显式读取：盘前快照文档。"""
        try:
            start_time = time.time()
            fn = getattr(self._client, "get_pre_market_brief_snapshot", None)
            if callable(fn):
                result = await fn(trade_date)
            else:
                result = await self._client.get_existing_pre_market_brief_snapshot(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 pre_market_brief_snapshot 失败 trade_date={trade_date}: {e}")
            raise

    async def get_existing_post_market_recap_snapshot(self, trade_date) -> Optional[Dict[str, Any]]:
        """股票域显式读取：盘后复盘快照文档。"""
        try:
            start_time = time.time()
            result = await self._client.get_existing_post_market_recap_snapshot(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 post_market_recap_snapshot 失败 trade_date={trade_date}: {e}")
            raise

    async def get_latest_post_market_recap_trade_date(self):
        try:
            start_time = time.time()
            result = await self._client.get_latest_post_market_recap_trade_date()
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 post_market_recap_snapshot 最新日期失败: {e}")
            raise

    async def get_latest_pre_market_brief_trade_date(self):
        try:
            start_time = time.time()
            result = await self._client.get_latest_pre_market_brief_trade_date()
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 pre_market_brief_snapshot 最新日期失败: {e}")
            raise

    async def get_stock_screening_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_stock_screening_strategy(strategy_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取选股策略失败 strategy_id={strategy_id}: {e}")
            raise

    async def get_stock_screening_strategies(self, active_only: bool = True) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_stock_screening_strategies(active_only=active_only)
            self._record_request(True, start_time)
            return list(result or [])
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取选股策略列表失败: {e}")
            raise

    async def get_stock_screening_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_stock_screening_execution(execution_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取选股执行失败 execution_id={execution_id}: {e}")
            raise

    async def get_stock_screening_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_stock_screening_result(result_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取选股结果失败 result_id={result_id}: {e}")
            raise

    async def get_w2s_candidate_replay_by_id(self, candidate_id: int) -> Optional[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_w2s_candidate_replay_by_id(candidate_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取弱转强回放详情失败 candidate_id={candidate_id}: {e}")
            raise

    async def query_stock_screening_history(self, **kwargs) -> Dict[str, Any]:
        try:
            start_time = time.time()
            result = await self._client.query_stock_screening_history(**kwargs)
            self._record_request(True, start_time)
            return dict(result or {})
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"查询选股历史失败: {e}")
            raise

    async def get_stock_screening_favorites(self, user_id: str) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_stock_screening_favorites(user_id)
            self._record_request(True, start_time)
            return list(result or [])
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取选股收藏失败 user_id={user_id}: {e}")
            raise

    async def add_stock_screening_favorite(self, favorite: Dict[str, Any]) -> bool:
        try:
            start_time = time.time()
            result = await self._client.add_stock_screening_favorite(favorite)
            self._record_request(True, start_time)
            return bool(result)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"新增选股收藏失败: {e}")
            raise

    async def update_stock_screening_favorite(
        self,
        favorite_id: str,
        notes: Optional[str],
        tags: Optional[List[str]],
    ) -> bool:
        try:
            start_time = time.time()
            result = await self._client.update_stock_screening_favorite(favorite_id, notes, tags)
            self._record_request(True, start_time)
            return bool(result)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"更新选股收藏失败 favorite_id={favorite_id}: {e}")
            raise

    async def remove_stock_screening_favorite(self, favorite_id: str) -> bool:
        try:
            start_time = time.time()
            result = await self._client.remove_stock_screening_favorite(favorite_id)
            self._record_request(True, start_time)
            return bool(result)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"删除选股收藏失败 favorite_id={favorite_id}: {e}")
            raise

    async def get_stock_screening_statistics(
        self,
        strategy_id: Optional[str] = None,
        date_from=None,
        date_to=None,
    ) -> Dict[str, Any]:
        try:
            start_time = time.time()
            result = await self._client.get_stock_screening_statistics(strategy_id, date_from, date_to)
            self._record_request(True, start_time)
            return dict(result or {})
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取选股统计失败: {e}")
            raise

    async def infer_confirm_trade_date_from_candidate_trade_date(self, candidate_trade_date):
        try:
            start_time = time.time()
            result = await self._client.infer_confirm_trade_date_from_candidate_trade_date(candidate_trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"推断候选确认交易日失败 candidate_trade_date={candidate_trade_date}: {e}")
            raise

    async def get_w2s_candidate_inputs(self, trade_date) -> List[Dict[str, Any]]:
        """等价旧链 _fetch_watch_candidate_inputs：D1 候选输入数据。"""
        try:
            start_time = time.time()
            result = await self._client.get_w2s_candidate_inputs(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 w2s_candidate_inputs 失败 trade_date={trade_date}: {e}")
            return []

    async def get_w2s_candidates_by_trade_date(self, candidate_trade_date, limit: int = 200) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._read_source().get_w2s_candidates_by_trade_date(candidate_trade_date, limit=limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取弱转强候选失败 trade_date={candidate_trade_date}: {e}")
            raise

    async def get_w2s_signals_by_trade_date(self, trade_date) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_w2s_signals_by_trade_date(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取弱转强信号失败 trade_date={trade_date}: {e}")
            raise

    async def get_w2s_candidates_for_confirm_date(self, confirm_trade_date, limit: int = 200) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._read_source().get_w2s_candidates_for_confirm_date(confirm_trade_date, limit=limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取确认日弱转强候选失败 confirm_trade_date={confirm_trade_date}: {e}")
            raise

    async def count_w2s_candidates_for_confirm_date(self, confirm_trade_date) -> int:
        try:
            start_time = time.time()
            result = await self._client.count_w2s_candidates_for_confirm_date(confirm_trade_date)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"统计确认日候选失败 confirm_trade_date={confirm_trade_date}: {e}")
            raise

    async def count_w2s_formal_candidates_for_confirm_date(self, confirm_trade_date) -> int:
        try:
            start_time = time.time()
            result = await self._client.count_w2s_formal_candidates_for_confirm_date(confirm_trade_date)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"统计确认日 formal 候选失败 confirm_trade_date={confirm_trade_date}: {e}")
            raise

    async def get_w2s_candidates_by_ids(self, candidate_ids: List[int]) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_w2s_candidates_by_ids(candidate_ids)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"按ID读取弱转强候选失败: {e}")
            raise

    async def get_w2s_snapshot_coverage(self, confirm_trade_date) -> Dict[str, int]:
        try:
            start_time = time.time()
            result = await self._client.get_w2s_snapshot_coverage(confirm_trade_date)
            self._record_request(True, start_time)
            return dict(result or {})
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取竞价快照覆盖率失败 confirm_trade_date={confirm_trade_date}: {e}")
            raise

    async def get_latest_strong_watch_trade_date(self):
        try:
            start_time = time.time()
            result = await self._client.get_latest_strong_watch_trade_date()
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 strong_stock_watch_history 最新日期失败: {e}")
            raise

    # ── NewChainIntelFeedAdapter 读口 ──────────────────────────────────

    async def get_new_chain_intel_recap(self, trade_date) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_new_chain_intel_recap(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 post_market_recap_snapshot intel 失败 trade_date={trade_date}: {e}")
            raise

    async def get_new_chain_intel_identity(self, trade_date) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_new_chain_intel_identity(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 theme_mainline_identity_registry intel 失败 trade_date={trade_date}: {e}")
            raise

    async def get_new_chain_intel_cycle(self, trade_date) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_new_chain_intel_cycle(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 theme_cycle_judgement_v2 intel 失败 trade_date={trade_date}: {e}")
            raise

    async def get_new_chain_intel_strong_watch(
        self, trade_date, limit_per_source: int = 20
    ) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_new_chain_intel_strong_watch(
                trade_date, limit_per_source=limit_per_source
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 strong_stock_watch_pool intel 失败 trade_date={trade_date}: {e}")
            raise

    async def get_new_chain_intel_w2s(self, trade_date) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_new_chain_intel_w2s(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 weak_to_strong_candidate_pool intel 失败 trade_date={trade_date}: {e}")
            raise

    async def get_intel_news_events(self, feed_date) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_intel_news_events(feed_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 news_event intel 失败 feed_date={feed_date}: {e}")
            raise

    async def get_event_subject_mappings_by_trade_date(
        self,
        trade_date,
        source: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            fn = getattr(self._client, "get_event_subject_mappings_by_trade_date", None)
            if not callable(fn):
                return []
            result = await fn(trade_date, source=source, limit=limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 event_subject_map 失败 trade_date={trade_date}: {e}")
            raise

    async def get_event_subject_mappings_by_event_ids(self, event_ids: List[int]) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            fn = getattr(self._client, "get_event_subject_mappings_by_event_ids", None)
            if not callable(fn):
                return []
            result = await fn(event_ids)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"按事件读取 event_subject_map 失败 event_ids={event_ids}: {e}")
            raise

    async def get_pre_market_subject_events(
        self,
        trade_date,
        source: Optional[str] = None,
        limit: int = 500,
        start_at=None,
        end_at=None,
    ) -> List[Dict[str, Any]]:
        try:
            start_ts = time.time()
            fn = getattr(self._client, "get_pre_market_subject_events", None)
            if not callable(fn):
                return []
            result = await fn(trade_date, source=source, limit=limit, start_time=start_at, end_time=end_at)
            self._record_request(True, start_ts)
            return result
        except Exception as e:
            self._record_request(False, start_ts)
            logger.error(f"读取盘前 subject 事件失败 trade_date={trade_date}: {e}")
            raise

    async def create_user(self, email: str, password_hash: str, role: str = "user") -> Dict[str, Any]:
        try:
            start_time = time.time()
            result = await self._client.create_user(email, password_hash, role)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            raise

    async def get_user_by_email(self, email: str) -> Dict[str, Any] | None:
        try:
            start_time = time.time()
            result = await self._client.get_user_by_email(email)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            raise

    async def update_user_last_login(self, user_id: int) -> None:
        try:
            start_time = time.time()
            await self._client.update_user_last_login(user_id)
            self._record_request(True, start_time)
        except Exception as e:
            self._record_request(False, start_time)
            raise

    async def resolve_subject_keys_by_names(self, names: List[str]) -> Dict[str, str]:
        try:
            start_time = time.time()
            result = await self._client.resolve_subject_keys_by_names(names)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            return {}

    async def get_intel_subject_history(self, feed_date) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_intel_subject_history(feed_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 subject_history intel 失败 feed_date={feed_date}: {e}")
            raise

    async def get_pre_market_review_events(
        self, feed_date, limit: int = 200, start_at=None, end_at=None
    ) -> List[Dict[str, Any]]:
        try:
            start_ts = time.time()
            fn = getattr(self._client, "get_pre_market_review_events", None)
            if not callable(fn):
                return []
            result = await fn(feed_date, limit=limit, start_time=start_at, end_time=end_at)
            self._record_request(True, start_ts)
            return result
        except Exception as e:
            self._record_request(False, start_ts)
            logger.error(f"读取 event_review_queue 失败 feed_date={feed_date}: {e}")
            raise

    # ── P1-D: PDF ──────────────────────────────────────────────────

    async def get_raw_intel_for_pdf_parse(self, limit: int = 50, high_value_only: bool = True):
        try:
            fn = getattr(self._read_source(), "get_raw_intel_for_pdf_parse", None)
            if not callable(fn):
                return []
            return await fn(limit=limit, high_value_only=high_value_only)
        except Exception as e:
            logger.error(f"get_raw_intel_for_pdf_parse 失败: {e}")
            return []

    async def update_raw_intel_content_text(self, doc_id: int, **kwargs):
        try:
            await self._client.update_raw_intel_content_text(doc_id, **kwargs)
        except Exception as e:
            logger.error(f"update_raw_intel_content_text 失败 doc_id={doc_id}: {e}")
            raise

    # ── Intel announcements ─────────────────────────────────────────

    async def get_intel_announcement_events(
        self,
        trade_date,
        limit: int = 200,
        start_time=None,
        end_time=None,
        matched_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """读取 intel 公告事件（news_event JOIN structured_intel_event，读库）。"""
        window_start = start_time
        window_end = end_time
        started_at = time.time()
        try:
            result = await self._read_source().get_intel_announcement_events(
                trade_date,
                limit,
                start_time=window_start,
                end_time=window_end,
                matched_only=matched_only,
            )
            self._record_request(True, started_at)
            return result
        except Exception as e:
            self._record_request(False, started_at)
            logger.error("get_intel_announcement_events 失败 trade_date=%s: %s", trade_date, e)
            raise

    async def get_subject_stock_daily_snapshot_by_trade_date(
        self, trade_date
    ) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._read_source().get_subject_stock_daily_snapshot_by_trade_date(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 subject_stock_daily_snapshot 失败 trade_date={trade_date}: {e}")
            raise

    async def get_theme_stock_leaderboard_by_trade_date(
        self,
        trade_date,
        subject_keys: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            fn = getattr(self._read_source(), "get_theme_stock_leaderboard_by_trade_date", None)
            if not callable(fn):
                return []
            result = await fn(trade_date, subject_keys=subject_keys)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 theme_stock_leaderboard 失败 trade_date={trade_date}: {e}")
            raise

    async def get_stock_daily_snapshot_by_stock_ids(
        self, trade_date, stock_ids: List[str]
    ) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_stock_daily_snapshot_by_stock_ids(trade_date, stock_ids)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 stock_daily_snapshot 失败 trade_date={trade_date}: {e}")
            raise

    async def upsert_stock_abnormal_signal_rows(self, rows: List[Dict[str, Any]]) -> int:
        try:
            start_time = time.time()
            result = await self._client.upsert_stock_abnormal_signal_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 stock_abnormal_signal 失败: {e}")
            raise

    async def get_trade_dates_before_or_on(self, end_date, limit: int = 7) -> List:
        try:
            start_time = time.time()
            result = await self._client.get_trade_dates_before_or_on(end_date, limit=limit)
            self._record_request(True, start_time)
            return list(result or [])
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取交易日窗口失败 end_date={end_date}, limit={limit}: {e}")
            raise

    async def get_strong_stock_watch_view_rows(
        self,
        end_date,
        window_days: int = 7,
        include_removed: bool = False,
        latest_per_stock: bool = True,
        stock_id: str | None = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._read_source().get_strong_stock_watch_view_rows(
                end_date=end_date,
                window_days=window_days,
                include_removed=include_removed,
                latest_per_stock=latest_per_stock,
                stock_id=stock_id,
                limit=limit,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 strong_watch_view 失败 end_date={end_date}: {e}")
            raise

    async def get_mainline_identity_by_subject_keys(self, subject_keys: List[str], trade_date) -> List[Dict[str, Any]]:
        """股票域显式读取：Layer A 主线身份真源。"""
        try:
            start_time = time.time()
            result = await self._read_source().get_mainline_identity_by_subject_keys(subject_keys, trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取主线身份失败 trade_date={trade_date}: {e}")
            raise

    async def get_mainline_identity_rule_inputs(self, trade_date, subject_keys: List[str]) -> List[Dict[str, Any]]:
        """股票域显式读取：Layer A 旧链等价规则输入。"""
        try:
            start_time = time.time()
            result = await self._client.get_mainline_identity_rule_inputs(
                trade_date=trade_date,
                subject_keys=subject_keys,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 Layer A 规则输入失败 trade_date={trade_date}: {e}")
            raise

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: List[str], trade_date) -> List[Dict[str, Any]]:
        """股票域显式读取：Layer B 周期状态真源。"""
        try:
            start_time = time.time()
            result = await self._read_source().get_mainline_cycle_by_subject_keys(subject_keys, trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取周期状态失败 trade_date={trade_date}: {e}")
            raise

    async def get_prior_strong_watch_pool_rows(self, trade_date, lookback_days: int) -> List[Dict[str, Any]]:
        """股票域显式读取：弱转强输入口径（前 N 交易日强势跟踪池历史）。"""
        try:
            start_time = time.time()
            result = await self._client.get_prior_strong_watch_pool_rows(trade_date, lookback_days=lookback_days)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 strong_stock_watch_history 失败 trade_date={trade_date}, lookback={lookback_days}: {e}")
            raise

    async def get_legacy_strong_watch_candidate_inputs(
        self,
        trade_date,
        lookback_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：旧链 weak_to_strong_candidate_builder 的 watch_pool 输入口径。"""
        try:
            start_time = time.time()
            result = await self._client.get_legacy_strong_watch_candidate_inputs(
                trade_date,
                lookback_days=lookback_days,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 legacy strong watch candidate inputs 失败 trade_date={trade_date}: {e}")
            raise

    async def get_subject_event_stats(
        self,
        trade_date,
        subject_keys: List[str] | None = None,
        lookback_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：按 subject_keys 聚合事件统计（news_event + event_theme_map + theme_master）。"""
        try:
            start_time = time.time()
            result = await self._client.get_subject_event_stats(
                trade_date=trade_date,
                subject_keys=subject_keys,
                lookback_days=lookback_days,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 subject_event_stats 失败 trade_date={trade_date}: {e}")
            raise

    async def get_subject_event_chain_rows(
        self,
        trade_date,
        subject_keys: List[str] | None = None,
        lookback_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """读取主题事件明细行 — theme_history_event + event_subject_map + subject_history_staging。"""
        try:
            start_time = time.time()
            result = await self._client.get_subject_event_chain_rows(
                trade_date=trade_date, subject_keys=subject_keys, lookback_days=lookback_days,
            )
            self._record_request(True, start_time)
            logger.info(f"get_subject_event_chain_rows: {len(subject_keys) if subject_keys else 0} keys → {len(result)} rows")
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.warning(f"get_subject_event_chain_rows failed: {e}", exc_info=True)
            return []

    async def get_staging_subject_keys(
        self, trade_date, lookback_days: int = 7
    ) -> List[str]:
        """读取 subject_history_staging 中回溯窗口内的 distinct subject_keys。"""
        try:
            start_time = time.time()
            result = await self._client.get_staging_subject_keys(
                trade_date=trade_date, lookback_days=lookback_days,
            )
            self._record_request(True, start_time)
            logger.info(f"get_staging_subject_keys: lookback={lookback_days} → {len(result)} keys")
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.warning(f"get_staging_subject_keys failed: {e}", exc_info=True)
            return []

    async def get_all_confirmed_mainlines(self) -> List[Dict[str, Any]]:
        """PR-13C: 读取所有已确认主线（从 mainline_registry）。"""
        try:
            start_time = time.time()
            result = await self._client.get_all_confirmed_mainlines()
            self._record_request(True, start_time)
            return result
        except Exception:
            self._record_request(False, start_time)
            return []

    async def get_active_confirmed_mainlines(self, trade_date=None, limit=100) -> List[Dict[str, Any]]:
        """PR-13C: 读取活跃已确认主线（从 mainline_registry）。"""
        try:
            start_time = time.time()
            result = await self._client.get_active_confirmed_mainlines(trade_date=trade_date, limit=limit)
            self._record_request(True, start_time)
            return result
        except Exception:
            self._record_request(False, start_time)
            return []

    async def get_all_prior_alive_cycles(self, trade_date) -> List[Dict[str, Any]]:
        """PR-13C: 读取上一交易日仍存续的已确认主线。"""
        try:
            start_time = time.time()
            result = await self._client.get_all_prior_alive_cycles(trade_date=trade_date)
            self._record_request(True, start_time)
            return result
        except Exception:
            self._record_request(False, start_time)
            return []

    async def get_subject_cycle_evidence_daily(
        self, trade_date, subject_keys: List[str] | None = None
    ) -> List[Dict[str, Any]]:
        """读取 theme_cycle_evidence_daily 预计算证据（委托 PostgresDatabaseManager）。"""
        try:
            start_time = time.time()
            result = await self._client.get_subject_cycle_evidence_daily(trade_date, subject_keys)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 subject_cycle_evidence_daily 失败 trade_date={trade_date}: {e}")
            raise

    async def get_post_market_report_context(
        self,
        trade_date,
        subject_keys: List[str] | None = None,
        stock_ids: List[str] | None = None,
    ) -> Dict[str, Any]:
        """读取盘后复盘所需全部事实上下文（委托 PostgresDatabaseManager）。"""
        try:
            start_time = time.time()
            result = await self._client.get_post_market_report_context(
                trade_date, subject_keys, stock_ids
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 post_market_report_context 失败 trade_date={trade_date}: {e}")
            raise

    async def get_subject_market_stats(
        self, trade_date, subject_keys: List[str] | None = None, lookback_days: int = 7
    ) -> List[Dict[str, Any]]:
        try:
            start_time = time.time()
            result = await self._client.get_subject_market_stats(trade_date, subject_keys, lookback_days)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 subject_market_stats 失败 trade_date={trade_date}: {e}")
            raise

    async def get_subject_heat_stats(
        self, trade_date, subject_keys: List[str] | None = None, lookback_days: int = 5
    ) -> List[Dict[str, Any]]:
        try:
            result = await self._client.get_subject_heat_stats(trade_date, subject_keys, lookback_days)
            return result
        except Exception as e:
            logger.error(f"读取 subject_heat_stats 失败 trade_date={trade_date}: {e}")
            raise

    async def get_mainline_state_daily(
        self, trade_date, subject_keys: List[str]
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：mainline_state_daily 状态快照。"""
        try:
            start_time = time.time()
            result = await self._client.get_mainline_state_daily(trade_date, subject_keys)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 mainline_state_daily 失败 trade_date={trade_date}: {e}")
            raise

    async def get_subject_board_stats(
        self, trade_date
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：当日各 subject 板块强度统计（涨停数/强势股数）。"""
        try:
            start_time = time.time()
            result = await self._client.get_subject_board_stats(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 subject_board_stats 失败 trade_date={trade_date}: {e}")
            raise

    async def get_stock_position_judgement(
        self, trade_date, stock_ids: List[str] | None = None
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：个股位置与均线判断。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_position_judgement(trade_date, stock_ids=stock_ids)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 stock_position_judgement 失败 trade_date={trade_date}: {e}")
            raise

    async def get_stock_pattern_judgement(
        self, trade_date, stock_ids: List[str] | None = None
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：个股形态与量价模式判断。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_pattern_judgement(trade_date, stock_ids=stock_ids)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 stock_pattern_judgement 失败 trade_date={trade_date}: {e}")
            raise

    async def get_strong_watch_seed_rows(
        self, trade_date, lookback_days: int = 7
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：强势股观察池种子候选（复刻旧链 _fetch_seed_rows SQL）。"""
        try:
            start_time = time.time()
            result = await self._client.get_strong_watch_seed_rows(trade_date, lookback_days)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 strong_watch_seed_rows 失败 trade_date={trade_date}: {e}")
            raise

    async def get_strong_watch_refresh_rows(
        self, trade_date
    ) -> List[Dict[str, Any]]:
        """股票域显式读取：强势股观察池 refresh 候选（复刻旧链 _fetch_refresh_watch_pool SQL）。"""
        try:
            start_time = time.time()
            result = await self._client.get_strong_watch_refresh_rows(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 strong_watch_refresh_rows 失败 trade_date={trade_date}: {e}")
            raise

    async def upsert_stock_daily_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """批量 UPSERT stock_daily_snapshot。"""
        """批量 UPSERT stock_daily_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_stock_daily_snapshot_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 stock_daily_snapshot 失败: {e}")
            raise

    async def upsert_stock_daily_strategy_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：stock_daily_strategy_snapshot（策略对象层）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_stock_daily_strategy_snapshot_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 stock_daily_strategy_snapshot 失败: {e}")
            raise

    async def upsert_source_raw_snapshot(self, row: Dict[str, Any]) -> int:
        """股票域显式写入：source_raw_snapshot，并返回快照 id。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_source_raw_snapshot(row)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 source_raw_snapshot 失败: {e}")
            raise

    async def upsert_market_data_source_registry_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：market_data_source_registry。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_market_data_source_registry_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 market_data_source_registry 失败: {e}")
            raise

    async def upsert_ths_hot_reason_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：ths_hot_reason_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_ths_hot_reason_snapshot_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 ths_hot_reason_snapshot 失败: {e}")
            raise

    async def upsert_stock_theme_reason_evidence_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：stock_theme_reason_evidence。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_stock_theme_reason_evidence_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 stock_theme_reason_evidence 失败: {e}")
            raise

    async def upsert_subject_stock_daily_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：subject_stock_daily_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_subject_stock_daily_snapshot_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 subject_stock_daily_snapshot 失败: {e}")
            raise

    async def upsert_stock_abnormal_event_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：stock_abnormal_event。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_stock_abnormal_event_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 stock_abnormal_event 失败: {e}")
            raise

    async def upsert_theme_stock_leaderboard_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：theme_stock_leaderboard。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_theme_stock_leaderboard_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量写入 theme_stock_leaderboard 失败: {e}")
            raise

    async def upsert_pre_market_brief_snapshot(self, doc: Dict[str, Any], force: bool = False) -> int:
        """股票域显式写入：pre_market_brief_snapshot。"""
        try:
            start_time = time.time()
            try:
                result = await self._client.upsert_pre_market_brief_snapshot(doc, force=force)
            except TypeError:
                if force:
                    raise
                result = await self._client.upsert_pre_market_brief_snapshot(doc)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 pre_market_brief_snapshot 失败: {e}")
            raise

    async def finalize_pre_market_brief_snapshot(self, trade_date, force: bool = False) -> int:
        """股票域显式冻结：pre_market_brief_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.finalize_pre_market_brief_snapshot(trade_date, force=force)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"冻结 pre_market_brief_snapshot 失败: {e}")
            raise

    async def upsert_post_market_recap_snapshot(self, doc: Dict[str, Any]) -> int:
        """股票域显式写入：post_market_recap_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_post_market_recap_snapshot(doc)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 post_market_recap_snapshot 失败: {e}")
            raise

    async def upsert_post_market_setup_plan_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：post_market_setup_plan。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_post_market_setup_plan_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 post_market_setup_plan 失败: {e}")
            raise

    async def upsert_one_to_two_candidate_feature_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：one_to_two_candidate_feature。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_one_to_two_candidate_feature_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 one_to_two_candidate_feature 失败: {e}")
            raise

    async def upsert_stock_f10_capital_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：stock_f10_capital_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_stock_f10_capital_snapshot_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 stock_f10_capital_snapshot 失败: {e}")
            raise

    async def upsert_stock_fund_flow_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：stock_fund_flow_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_stock_fund_flow_snapshot_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 stock_fund_flow_snapshot 失败: {e}")
            raise

    async def get_stock_fund_flow_snapshots(
        self,
        *,
        stock_codes: List[str],
        trade_date: str | None = None,
    ) -> list[Dict[str, Any]]:
        """股票域显式读取：stock_fund_flow_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_fund_flow_snapshots(
                stock_codes=stock_codes,
                trade_date=trade_date,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 stock_fund_flow_snapshot 失败: {e}")
            raise

    async def get_stock_f10_capital_snapshots(
        self,
        trade_date,
        stock_ids: List[str] | None = None,
        source: str = "tdx_f10",
        section: str = "资金动向",
    ) -> list[Dict[str, Any]]:
        """股票域显式读取：stock_f10_capital_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_f10_capital_snapshots(
                trade_date=trade_date,
                stock_ids=stock_ids,
                source=source,
                section=section,
            )
            self._record_request(True, start_time)
            return [dict(row) for row in result]
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 stock_f10_capital_snapshot 失败: {e}")
            raise

    async def upsert_theme_cycle_evidence_daily_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：theme_cycle_evidence_daily（Layer B 四层证据真源）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_theme_cycle_evidence_daily_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 theme_cycle_evidence_daily 失败: {e}")
            raise

    async def upsert_theme_cycle_judgement_v2_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：theme_cycle_judgement_v2（Layer B 周期判定真源）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_theme_cycle_judgement_v2_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 theme_cycle_judgement_v2 失败: {e}")
            raise

    async def get_replay_snapshot_manifest(
        self,
        trade_date,
        layer_name: str,
        snapshot_version: str,
        algorithm_version: str,
    ) -> Optional[Dict[str, Any]]:
        """读取 replay_snapshot_manifest。"""
        try:
            start_time = time.time()
            result = await self._client.get_replay_snapshot_manifest(
                trade_date=trade_date,
                layer_name=layer_name,
                snapshot_version=snapshot_version,
                algorithm_version=algorithm_version,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(
                "读取 replay_snapshot_manifest 失败 "
                f"trade_date={trade_date}, layer={layer_name}: {e}"
            )
            raise

    async def upsert_replay_snapshot_manifest(self, row: Dict[str, Any]) -> int:
        """写入 replay_snapshot_manifest。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_replay_snapshot_manifest(row)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 replay_snapshot_manifest 失败: {e}")
            raise

    async def upsert_strong_watch_pool_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：strong_stock_watch_pool（Layer C 持久池）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_strong_watch_pool_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 strong_stock_watch_pool 失败: {e}")
            raise

    async def upsert_weak_to_strong_candidate_pool_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：weak_to_strong_candidate_pool（D1 候选池）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_weak_to_strong_candidate_pool_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 weak_to_strong_candidate_pool 失败: {e}")
            return 0

    async def recompute_strong_watch_window_days(self, stock_ids: list[str]) -> int:
        """等价旧链 _recompute_watch_window_days：以交易日计数重算观察窗天数。"""
        try:
            start_time = time.time()
            result = await self._client.recompute_strong_watch_window_days(stock_ids)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"recompute_strong_watch_window_days 失败: {e}")
            return 0

    async def get_auction_watch_universe(self, trade_date) -> List[Dict[str, Any]]:
        """股票域显式读取：竞价观察池。"""
        try:
            start_time = time.time()
            result = await self._client.get_auction_watch_universe(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 auction_watch_universe 失败 trade_date={trade_date}: {e}")
            raise

    async def get_w2s_candidates_by_next_date(self, confirm_date) -> List[Dict[str, Any]]:
        """股票域显式读取：弱转强候选池（按确认日）。"""
        try:
            start_time = time.time()
            result = await self._client.get_w2s_candidates_by_next_date(confirm_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 w2s_candidates 失败 confirm_date={confirm_date}: {e}")
            raise

    async def upsert_pre_market_auction_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：pre_market_auction_snapshot（竞价快照对象层）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_pre_market_auction_snapshot_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 pre_market_auction_snapshot 失败: {e}")
            raise

    async def get_auction_board_leaders(self, trade_date) -> List[Dict[str, Any]]:
        """股票域显式读取：auction 竞价观察池龙头候选。"""
        try:
            start_time = time.time()
            result = await self._client.get_auction_board_leaders(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 auction_board_leaders 失败 trade_date={trade_date}: {e}")
            raise

    async def get_auction_mainlines(self, trade_date) -> List[Dict[str, Any]]:
        """股票域显式读取：auction 竞价所需主线存活状态。"""
        try:
            start_time = time.time()
            result = await self._client.get_auction_mainlines(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 auction_mainlines 失败 trade_date={trade_date}: {e}")
            raise

    async def get_auction_cycles(self, trade_date) -> List[Dict[str, Any]]:
        """股票域显式读取：auction 竞价所需周期状态。"""
        try:
            start_time = time.time()
            result = await self._client.get_auction_cycles(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 auction_cycles 失败 trade_date={trade_date}: {e}")
            raise

    async def upsert_auction_watch_universe_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：auction_watch_universe（竞价观察池）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_auction_watch_universe_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 auction_watch_universe 失败: {e}")
            raise

    async def upsert_dragon_tiger_object_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：dragon_tiger_object（龙虎榜对象层）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_dragon_tiger_object_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 dragon_tiger_object 失败: {e}")
            raise

    async def promote_strong_watch_candidates(self, trade_date) -> int:
        """股票域显式写入：标记 candidate_promoted（等价旧链 promote_watch_candidates）。"""
        try:
            start_time = time.time()
            result = await self._client.promote_strong_watch_candidates(trade_date)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"promote_strong_watch_candidates 失败 trade_date={trade_date}: {e}")
            raise

    async def prune_strong_watch_pool(self, trade_date, weakening_min_score: float = 62.0) -> int:
        """股票域显式写入：清理失效观察对象（等价旧链 prune_watch_pool）。"""
        try:
            start_time = time.time()
            result = await self._client.prune_strong_watch_pool(trade_date, weakening_min_score)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"prune_strong_watch_pool 失败 trade_date={trade_date}: {e}")
            raise

    async def upsert_strong_watch_history_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：strong_stock_watch_history。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_strong_watch_history_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 strong_stock_watch_history 失败: {e}")
            raise

    async def upsert_theme_mainline_identity_registry_rows(
        self, rows: List[Dict[str, Any]],
        *,
        allow_historical_overwrite: bool = False,
        allow_unsafe_demotion: bool = False,
    ) -> int:
        """股票域显式写入：theme_mainline_identity_registry（Layer A 身份注册表）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_theme_mainline_identity_registry_rows(
                rows,
                allow_historical_overwrite=allow_historical_overwrite,
                allow_unsafe_demotion=allow_unsafe_demotion,
            )
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 theme_mainline_identity_registry 失败: {e}")
            raise

    async def upsert_mainline_identity_review_queue_rows(self, rows: List[Dict[str, Any]]) -> int:
        """股票域显式写入：mainline_identity_review_queue（Layer A 身份复核队列）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_mainline_identity_review_queue_rows(rows)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入 mainline_identity_review_queue 失败: {e}")
            raise

    async def apply_lifecycle_downgrade(
        self, trade_date, deactivate_fade_days: int = 2
    ) -> int:
        """股票域显式写入：主线生命周期降级（连续 fade → inactive）。"""
        try:
            start_time = time.time()
            result = await self._client.apply_lifecycle_downgrade(trade_date, deactivate_fade_days)
            self._record_request(True, start_time)
            return int(result or 0)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"lifecycle downgrade 失败 trade_date={trade_date}: {e}")
            raise

    async def publish_stock_processing_event(self, event_name: str, payload: Dict[str, Any]) -> str:
        """
        股票域显式事件发布入口。
        当前阶段先提供统一事件ID与日志落点；后续在 P3.phase1-T09 接入 stream runtime。
        """
        start_time = time.time()
        event_id = f"sps-{uuid4().hex}"
        logger.info(
            "📤 stock_processing_event published: event_id=%s, event_name=%s, trade_date=%s",
            event_id,
            event_name,
            payload.get("trade_date"),
        )
        self._record_request(True, start_time)
        return event_id

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        """股票域显式幂等入口：尝试抢占任务key。"""
        now_ts = time.time()
        entry = self._idempotency_store.get(job_key)
        if entry and entry.get("expires_at", 0) > now_ts and not entry.get("completed"):
            return False
        self._idempotency_store[job_key] = {
            "expires_at": now_ts + max(int(ttl_seconds), 1),
            "completed": False,
            "metadata": None,
        }
        return True

    async def mark_job_completed(self, job_key: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """股票域显式幂等入口：标记任务完成。"""
        entry = self._idempotency_store.get(job_key) or {}
        entry["completed"] = True
        entry["metadata"] = metadata or {}
        entry.setdefault("expires_at", time.time() + 3600)
        self._idempotency_store[job_key] = entry

    async def record_dead_letter(self, event_name: str, payload: Dict[str, Any], reason: str) -> str:
        """股票域显式死信记录入口。"""
        dead_letter_id = f"dlq-{uuid4().hex}"
        logger.warning(
            "☠️ stock_processing_dead_letter: id=%s event=%s reason=%s trade_date=%s",
            dead_letter_id,
            event_name,
            reason,
            payload.get("trade_date"),
        )
        return dead_letter_id

    async def get_stock_daily_snapshot_by_trade_date(self, trade_date) -> List[Dict[str, Any]]:
        """按交易日读取 stock_daily_snapshot。"""
        try:
            start_time = time.time()
            result = await self._client.get_stock_daily_snapshot_by_trade_date(trade_date)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"读取 stock_daily_snapshot 失败 trade_date={trade_date}: {e}")
            raise
    
    async def get_theme_by_code(self, code: str) -> Optional[ThemeRecord]:
        """获取主题（按code）"""
        try:
            start_time = time.time()
            result = await self._client.get_theme_by_code(code)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"按code获取主题失败 {code}: {e}")
            raise
    
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        try:
            start_time = time.time()
            result = await self._client.get_theme_by_name(name)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取主题失败 {name}: {e}")
            raise
    
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """获取所有活跃主题"""
        try:
            start_time = time.time()
            result = await self._client.get_all_active_themes(limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取活跃主题失败: {e}")
            raise
    
    async def create_theme(self, name: str, code: str, **kwargs) -> Optional[ThemeRecord]:
        """创建新主题（必须包含code）"""
        try:
            start_time = time.time()
            
            # 验证必填字段
            if not name or not code:
                raise ValueError("主题名称和code不能为空")
            
            # 处理tags字段
            if 'tags' in kwargs and isinstance(kwargs['tags'], dict):
                from database_service.interface import ThemeTags
                kwargs['tags'] = ThemeTags.from_dict(kwargs['tags'])
            
            # 创建主题
            theme = await self._client.create_theme(name, code, **kwargs)
            
            # 触发事件
            if theme:
                await self._on_theme_created(theme)
            
            self._record_request(True, start_time)
            logger.info(f"✅ 创建主题: {name} (code: {code})")
            
            return theme
            
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"创建主题失败 {name} ({code}): {e}")
            raise
    
    async def update_theme(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题"""
        try:
            start_time = time.time()
            
            # 处理tags字段更新
            if 'tags' in updates and isinstance(updates['tags'], dict):
                from database_service.interface import ThemeTags
                updates['tags'] = ThemeTags.from_dict(updates['tags'])
            
            if hasattr(self._client, 'update_theme'):
                result = await self._client.update_theme(theme_id, updates)
            else:
                result = None
            
            if result:
                await self._on_theme_updated(theme_id, updates)
            
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"更新主题失败 {theme_id}: {e}")
            raise
    
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度"""
        try:
            await self._client.increment_theme_heat(theme_id, increment)
            
            # 记录热度变化事件
            await self._on_theme_heat_changed(theme_id, increment)
            
        except Exception as e:
            logger.error(f"增加主题热度失败 {theme_id}: {e}")
            raise
    
    async def increment_mention_count(self, theme_id: int, increment: int = 1) -> None:
        """增加提及次数"""
        try:
            await self._client.increment_mention_count(theme_id, increment)
        except Exception as e:
            logger.error(f"增加提及次数失败 {theme_id}: {e}")
            raise
    
    async def get_themes_by_category(self, category_code: str, level: int = 1, 
                                    limit: int = 50) -> List[ThemeRecord]:
        """根据分类代码获取主题"""
        try:
            start_time = time.time()
            if hasattr(self._client, 'get_themes_by_category'):
                result = await self._client.get_themes_by_category(category_code, level, limit)
            else:
                result = []
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"按分类获取主题失败 {category_code}: {e}")
            raise
    
    async def get_themes_by_heat_level(self, min_heat: int = 60, 
                                      limit: int = 100) -> List[ThemeRecord]:
        """获取热度较高的主题"""
        try:
            start_time = time.time()
            if hasattr(self._client, 'get_themes_by_heat_level'):
                result = await self._client.get_themes_by_heat_level(min_heat, limit)
            else:
                result = []
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取高热主题失败 (min_heat={min_heat}): {e}")
            raise
    
    # ========== 事件-主题关联操作 ==========
    
    async def create_event_theme_relation(self, event_id: int, theme_id: int, 
                                         **kwargs) -> EventThemeRelation:
        """创建事件-主题关联"""
        try:
            start_time = time.time()
            result = await self._client.create_event_theme_relation(event_id, theme_id, **kwargs)
            
            if result:
                await self._on_relation_created(event_id, theme_id, result)
            
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"创建关联失败 event={event_id}, theme={theme_id}: {e}")
            raise
    
    async def get_event_themes(self, event_id: int) -> List[EventThemeRelation]:
        """获取事件关联的主题"""
        try:
            start_time = time.time()
            result = await self._client.get_event_themes(event_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取事件主题失败 {event_id}: {e}")
            raise
    
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        """获取主题关联的事件ID"""
        try:
            start_time = time.time()
            result = await self._client.get_theme_events(theme_id, limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取主题事件失败 {theme_id}: {e}")
            raise

    async def upsert_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> Dict[str, Any]:
        """幂等写入事件-主题关联，供 ThemeMatchEngine 生产链路使用"""
        try:
            start_time = time.time()
            result = await self._client.upsert_event_theme_relation(event_id, theme_id, **kwargs)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"幂等写入关联失败 event={event_id}, theme={theme_id}: {e}")
            raise

    async def upsert_event_subject_relation(self, event_id: int, subject_key: str, **kwargs) -> Dict[str, Any]:
        """幂等写入事件-JYHF题材关联；新链主路径不依赖 theme_master/theme_id。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_event_subject_relation(event_id, subject_key, **kwargs)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"幂等写入 subject 关联失败 event={event_id}, subject_key={subject_key}: {e}")
            raise
    
    # ========== 高级查询方法 ==========
    
    async def find_related_themes(self, event_data: Dict[str, Any], 
                                 limit: int = 5) -> List[ThemeRecord]:
        """查找相关主题"""
        try:
            start_time = time.time()
            result = await self._client.find_related_themes(event_data, limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"查找相关主题失败: {e}")
            raise
    
    async def get_themes_by_keywords(self, keywords: List[str], 
                                    limit: int = 20) -> List[ThemeRecord]:
        """根据关键词获取主题"""
        try:
            start_time = time.time()
            result = await self._client.get_themes_by_keywords(keywords, limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"关键词搜索失败: {e}")
            raise
    
    async def search_themes(self, query: str, limit: int = 10) -> List[ThemeRecord]:
        """搜索主题"""
        try:
            start_time = time.time()
            if hasattr(self._client, 'search_themes'):
                result = await self._client.search_themes(query, limit)
            else:
                result = []
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"主题搜索失败 {query}: {e}")
            raise
    
    # ========== 批量操作 ==========
    
    async def batch_create_themes(self, themes_data: List[Dict[str, Any]]) -> List[ThemeRecord]:
        """批量创建主题"""
        try:
            start_time = time.time()
            
            # 验证每个主题都有code字段
            for i, data in enumerate(themes_data):
                if 'code' not in data:
                    raise ValueError(f"第{i+1}个主题缺少code字段")
                if 'tags' in data and isinstance(data['tags'], dict):
                    from database_service.interface import ThemeTags
                    data['tags'] = ThemeTags.from_dict(data['tags'])
            
            result = await self._client.batch_create_themes(themes_data)
            
            if result:
                await self._on_themes_batch_created(result)
            
            self._record_request(True, start_time)
            logger.info(f"✅ 批量创建 {len(result)} 个主题")
            
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量创建主题失败: {e}")
            raise
    
    # ========== 事件状态管理 ==========
    
    async def mark_event_processed(self, event_id: int) -> bool:
        """标记事件已处理"""
        try:
            start_time = time.time()
            await self._client.mark_event_processed(event_id)
            self._record_request(True, start_time)
            return True
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"标记事件失败 {event_id}: {e}")
            return False
    
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件"""
        try:
            start_time = time.time()
            result = await self._client.get_unprocessed_events(limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取未处理事件失败: {e}")
            raise
    
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件详情"""
        try:
            start_time = time.time()
            result = await self._client.get_event(event_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取事件失败 {event_id}: {e}")
            raise

    async def get_news_event_for_match(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取供 ThemeMatchEngine 使用的单条事件输入"""
        try:
            start_time = time.time()
            result = await self._client.get_news_event_for_match(event_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取匹配事件失败 {event_id}: {e}")
            raise

    async def list_matchable_news_events(
        self,
        limit: int = 0,
        event_id: Optional[int] = None,
        only_unmapped: bool = False,
    ) -> List[Dict[str, Any]]:
        """批量获取供 ThemeMatchEngine 使用的事件列表"""
        try:
            start_time = time.time()
            result = await self._client.list_matchable_news_events(
                limit=limit,
                event_id=event_id,
                only_unmapped=only_unmapped,
            )
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"批量获取匹配事件失败: {e}")
            raise

    async def load_theme_match_profiles(self) -> List[Dict[str, Any]]:
        """加载 ThemeMatchEngine 所需的题材画像原始数据"""
        try:
            start_time = time.time()
            result = await self._read_source().load_theme_match_profiles()
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"加载题材匹配画像失败: {e}")
            raise

    async def load_theme_profile_v2_profiles(
        self,
        status: str = "draft",
        subject_keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """加载灰度用 theme_profile_v2 画像。"""
        try:
            start_time = time.time()
            source = self._read_source()
            fn = getattr(source, "load_theme_profile_v2_profiles", None)
            if not callable(fn):
                return []
            result = await fn(status=status, subject_keys=subject_keys)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"加载 theme_profile_v2 画像失败: {e}")
            raise

    async def semantic_recall_theme_candidates(
        self,
        query_embedding: List[float],
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """基于 theme_profile_ext.embedding 做语义召回"""
        try:
            start_time = time.time()
            result = await self._read_source().semantic_recall_theme_candidates(query_embedding, top_k)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"语义召回候选失败: {e}")
            raise

    async def sparse_recall_theme_candidates(
        self,
        query_text: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """基于 theme_gate_profile.search_vector 做稀疏召回"""
        try:
            start_time = time.time()
            result = await self._read_source().sparse_recall_theme_candidates(query_text, top_k)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"稀疏召回候选失败: {e}")
            raise

    async def resolve_theme_master_id_by_source_key(self, source_system: str, source_key: str) -> Optional[int]:
        """通过 source_system/source_key 解析正式 theme_master.id"""
        try:
            start_time = time.time()
            result = await self._client.resolve_theme_master_id_by_source_key(source_system, source_key)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"解析 theme_master.id 失败 source_system={source_system}, source_key={source_key}: {e}")
            raise

    async def create_news_event(self, event_data: Dict[str, Any]) -> Optional[int]:
        """创建结构化 news_event 记录并返回 news_event.id"""
        try:
            start_time = time.time()
            async with self._db_op():
                result = await self._client.create_news_event(event_data)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"创建 news_event 失败: {e}")
            raise

    async def enqueue_event_review(
        self,
        event_id: int,
        reason: str,
        source_channel: str = "realtime_news",
        proposed_theme_name: Optional[str] = None,
        proposed_theme_confidence: Optional[float] = None,
    ) -> bool:
        """写入人工复核队列。"""
        try:
            start_time = time.time()
            result = await self._client.enqueue_event_review(
                event_id=event_id,
                reason=reason,
                source_channel=source_channel,
                proposed_theme_name=proposed_theme_name,
                proposed_theme_confidence=proposed_theme_confidence,
            )
            self._record_request(True, start_time)
            return bool(result)
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"写入人工复核队列失败 event_id={event_id}: {e}")
            return False

    # ── Phase 6A: Review queue CRUD ──

    async def list_review_events(self, page=1, page_size=20, status=None, source_channel=None) -> dict:
        try:
            return await self._client.list_review_events(page=page, page_size=page_size, status=status, source_channel=source_channel)
        except Exception as e:
            logger.error(f"list_review_events 失败: {e}")
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

    async def get_review_event_detail(self, review_id: int) -> dict | None:
        try:
            return await self._client.get_review_event_detail(review_id)
        except Exception as e:
            logger.error(f"get_review_event_detail 失败: {e}")
            return None

    async def confirm_review_event(self, review_id: int, reviewed_by="", review_note="") -> bool:
        try:
            return await self._client.confirm_review_event(review_id, reviewed_by=reviewed_by, review_note=review_note)
        except Exception as e:
            logger.error(f"confirm_review_event 失败: {e}")
            return False

    async def delete_review_event(self, review_id: int) -> bool:
        try:
            return await self._client.delete_review_event(review_id)
        except Exception as e:
            logger.error(f"delete_review_event 失败: {e}")
            return False

    async def batch_delete_review_events(self, ids: list[int]) -> int:
        try:
            return await self._client.batch_delete_review_events(ids)
        except Exception as e:
            logger.error(f"batch_delete_review_events 失败: {e}")
            return 0

    # ========== 统计与监控 ==========
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            stats = await self._client.get_database_stats()
            
            # 添加网关统计
            stats['gateway'] = {
                'requests': self._stats['requests'],
                'success': self._stats['success'],
                'errors': self._stats['errors'],
                'success_rate': self._stats['success'] / max(self._stats['requests'], 1),
                'initialized': self._initialized
            }
            
            # 添加表结构信息
            if self._config.db_type.value != "memory":
                table_names = getattr(self._config, "table_names", {})
                if isinstance(table_names, dict):
                    theme_table = table_names.get("theme_master", "theme_master")
                else:
                    theme_table = getattr(table_names, "theme_master", "theme_master")
                stats['schema'] = {
                    'version': '28_fields_v1',
                    'theme_table': theme_table,
                    'has_code_field': True,
                    'has_category_fields': True,
                    'has_tags_field': True
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {
                'error': str(e),
                'gateway': self._stats.copy()
            }
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        try:
            if hasattr(self._client, 'get_cache_stats'):
                return await self._client.get_cache_stats()
            return {'enabled': False, 'message': '缓存未启用'}
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {'error': str(e)}
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            return await self._client.health_check()
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    # ========== 缓存管理 ==========
    
    async def clear_cache(self, pattern: str = "*") -> int:
        """清除缓存"""
        try:
            if hasattr(self._client, 'clear_cache'):
                count = await self._client.clear_cache(pattern)
                logger.info(f"✅ 清除缓存: {pattern} ({count}个键)")
                return count
            return 0
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return 0
    
    async def warm_cache(self, item_count: int = 100) -> Dict[str, Any]:
        """预热缓存 - 基于实际配置的修复版"""
        
        try:
            # 导入CacheStrategy枚举
            from database_service.config import CacheStrategy
            
            logger.info(f"🔥 开始缓存预热，配置策略: {self._config.cache.strategy.value}")
            
            # 检查缓存配置是否启用
            if not self._config.cache.enable_cache_warming:
                logger.info("⏭️  跳过缓存预热（配置禁用）")
                return {
                    "status": "skipped",
                    "message": "缓存预热功能配置禁用",
                    "details": {
                        "reason": "config_disabled",
                        "cache_strategy": self._config.cache.strategy.value,
                        "enable_cache_warming": self._config.cache.enable_cache_warming
                    }
                }
            
            # 检查Redis是否启用（如果使用Redis缓存）
            if self._config.cache.strategy != CacheStrategy.NONE:
                if not self._config.redis.enabled:
                    logger.info("⏭️  跳过缓存预热（Redis未启用）")
                    return {
                        "status": "skipped",
                        "message": "Redis未启用，跳过缓存预热",
                        "details": {
                            "redis_enabled": self._config.redis.enabled,
                            "cache_strategy": self._config.cache.strategy.value
                        }
                    }
            
            # 简化预热逻辑
            warm_up_results = {
                "attempted": True,
                "config_loaded": True,
                "client_available": self._client is not None,
                "cache_strategy": self._config.cache.strategy.value,
                "redis_enabled": self._config.redis.enabled
            }
            
            # 尝试简单的缓存预热
            if self._client:
                client_type = self._client.__class__.__name__
                logger.info(f"🔄 对{client_type}执行简化缓存预热")
                
                # 根据不同的客户端类型执行不同的预热逻辑
                if client_type == "PostgresDatabaseManager":
                    # PostgreSQL客户端 - 执行查询预热
                    try:
                        # 尝试获取一些基本统计数据
                        stats = await self._client.get_stats()
                        warm_up_results["stats"] = stats
                        warm_up_results["postgres_warmup"] = "success"
                        
                        logger.info(f"✅ PostgreSQL缓存预热完成: {stats}")
                        
                    except Exception as e:
                        warm_up_results["postgres_warmup"] = f"failed: {str(e)}"
                        logger.info(f"⚠️  PostgreSQL缓存预热异常: {e}")
                
                elif client_type == "MemoryDatabaseManager":
                    # 内存数据库 - 无需预热
                    warm_up_results["memory_warmup"] = "not_needed"
                    logger.info("✅ 内存数据库无需缓存预热")
                
                else:
                    # 其他类型客户端
                    warm_up_results["other_client"] = client_type
                    logger.info(f"ℹ️  {client_type}类型客户端，跳过特定预热")
            
            # 返回结果
            return {
                "status": "success" if self._client else "partial",
                "message": "缓存预热（简化版）完成",
                "details": warm_up_results,
                "config_summary": {
                    "database_type": self._config.db_type.value,
                    "cache_strategy": self._config.cache.strategy.value,
                    "enable_cache_warming": self._config.cache.enable_cache_warming,
                    "warm_cache_items": item_count
                }
            }
            
        except ImportError as e:
            # 如果导入CacheStrategy失败
            logger.warning(f"⚠️  无法导入CacheStrategy: {e}")
            
            return {
                "status": "simplified",
                "message": "使用简化缓存预热（导入失败）",
                "details": {
                    "config_loaded": True,
                    "client_available": self._client is not None,
                    "error": str(e)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 缓存预热异常: {e}")
            return {
                "status": "error", 
                "message": str(e),
                "details": {
                    "exception_type": type(e).__name__,
                    "config_db_type": self._config.db_type.value if hasattr(self._config, 'db_type') else "unknown",
                    "client_type": self._client.__class__.__name__ if self._client else "None"
                }
            }
    
    async def create_category(self, category_data: Dict) -> Optional[Dict]:
        """
        创建新分类 - 修复版
        与PostgresClient.create_category保持一致的签名
        
        Args:
            category_data: 分类数据字典，包含以下字段：
                - category_code: 分类代码 (必需)
                - category_name: 分类名称 (必需)
                - category_level: 分类级别 (必需)
                - description: 描述 (可选)
                - parent_code: 父分类代码 (可选)
                - category_type: 分类类型，如'industry'或'concept' (可选)
                - keywords: 关键词列表 (可选)
                - aliases: 别名列表 (可选)
                - source_system: 来源系统 (可选)
                - source_id: 来源ID (可选)
                
        Returns:
            创建的分类数据字典，或None（如果失败）
            
        Raises:
            ValueError: 缺少必需字段
            Exception: 分类已存在或其他数据库错误
        """
        try:
            # 验证输入
            if not isinstance(category_data, dict):
                raise ValueError("category_data必须是字典类型")
            
            # 检查必需字段
            required_fields = ['category_code', 'category_name', 'category_level']
            missing_fields = []
            for field in required_fields:
                if field not in category_data:
                    missing_fields.append(field)
            
            if missing_fields:
                raise ValueError(f"缺失必需字段: {missing_fields}")
            
            logger.info(f"📝 DatabaseGateway创建分类: {category_data.get('category_name')} "
                    f"({category_data.get('category_code')})")
            
            # 🔍 调试日志：显示完整数据
            logger.debug(f"   分类数据字段: {list(category_data.keys())}")
            logger.debug(f"   分类级别: {category_data.get('category_level')}")
            logger.debug(f"   分类类型: {category_data.get('category_type', '未指定')}")
            
            # 检查客户端是否支持create_category方法
            if not hasattr(self._client, 'create_category'):
                logger.error(f"❌ 数据库客户端不支持create_category方法")
                logger.error(f"客户端类型: {type(self._client)}")
                logger.error(f"客户端可用方法: {[m for m in dir(self._client) if not m.startswith('_')]}")
                raise AttributeError("数据库客户端缺少create_category方法")
            
            # 调用底层客户端
            logger.debug(f"   调用客户端create_category方法...")
            result = await self._client.create_category(category_data)
            
            if result:
                logger.info(f"✅ 分类创建成功: {category_data.get('category_name')} "
                        f"(ID: {result.get('id', '未知')})")
                
                # 触发分类创建事件
                try:
                    if hasattr(self, '_on_category_created'):
                        await self._on_category_created(result)
                except Exception as e:
                    logger.warning(f"⚠️ 触发分类创建事件失败: {e}")
                    # 不阻止主流程
                
                return result
            else:
                logger.warning(f"⚠️ 分类创建返回空结果: {category_data.get('category_code')}")
                return None
                
        except Exception as e:
            logger.error(f"❌ DatabaseGateway创建分类失败: {e}")
            logger.error(f"   分类数据: {category_data}")
            logger.error(f"   错误类型: {type(e).__name__}")
            
            # 重新抛出异常，保持错误传播
            raise
    
    async def check_category_exists(self, category_code: str) -> bool:
        """检查分类是否存在"""
        try:
            category = await self.get_category_by_code(category_code)
            return category is not None
        except Exception as e:
            logger.debug(f"检查分类存在失败: {e}")
            return False
    
    async def get_categories_by_parent(self, parent_code: str, level: int = 2) -> List[Dict]:
        """获取子分类"""
        return await self._client.get_categories_by_parent(parent_code, level)
    
    async def load_all_categories(self) -> List[Dict[str, Any]]:
        """加载全部分类数据"""
        try:
            start_time = time.time()
            
            if hasattr(self._client, 'load_all_categories'):
                result = await self._client.load_all_categories()
            else:
                result = []
            
            self._record_request(True, start_time)
            logger.info(f"✅ 加载全部分类数据: {len(result)} 条记录")
            return result
            
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"加载分类数据失败: {e}")
            return []
    
    async def get_category_by_code(self, category_code: str) -> Optional[Dict[str, Any]]:
        """根据分类代码获取分类"""
        try:
            start_time = time.time()
            
            if hasattr(self._client, 'get_category_by_code'):
                result = await self._client.get_category_by_code(category_code)
            else:
                result = None
            
            self._record_request(True, start_time)
            if result:
                logger.info(f"✅ 获取分类详情: {category_code}")
            return result
            
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取分类详情失败 {category_code}: {e}")
            return None
    
    async def get_child_categories(self, parent_code: str, 
                                 limit: int = 50) -> List[Dict[str, Any]]:
        """获取子分类"""
        try:
            start_time = time.time()
            
            if hasattr(self._client, 'get_child_categories'):
                result = await self._client.get_child_categories(parent_code, limit)
            else:
                result = []
            
            self._record_request(True, start_time)
            logger.info(f"✅ 获取子分类: {parent_code} -> {len(result)} 个")
            return result
            
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取子分类失败 {parent_code}: {e}")
            return []
    
    async def search_categories_by_keywords(self, keywords: List[str], 
                                          level: Optional[int] = None,
                                          limit: int = 20) -> List[Dict[str, Any]]:
        """根据关键词搜索分类"""
        try:
            start_time = time.time()
            
            if hasattr(self._client, 'search_categories_by_keywords'):
                result = await self._client.search_categories_by_keywords(keywords, level, limit)
            else:
                result = []
            
            self._record_request(True, start_time)
            logger.info(f"✅ 关键词搜索分类: {keywords} -> {len(result)} 个结果")
            return result
            
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"搜索分类失败: {e}")
            return []
    
    async def get_category_stats(self) -> Dict[str, Any]:
        """获取分类统计信息"""
        try:
            start_time = time.time()
            
            if hasattr(self._client, 'get_category_stats'):
                result = await self._client.get_category_stats()
            else:
                result = {}
            
            self._record_request(True, start_time)
            logger.info(f"✅ 获取分类统计信息")
            return result
            
        except Exception as e:
            self._record_request(False, start_time)
            logger.error(f"获取分类统计失败: {e}")
            return {}

    # ========== 事件处理 ==========
    
    async def _on_theme_created(self, theme: ThemeRecord):
        """主题创建事件处理"""
        # 这里可以发布消息或触发其他操作
        logger.info(f"🎉 主题创建事件: {theme.name} (code: {theme.code})")
    
    async def _on_theme_updated(self, theme_id: int, updates: Dict[str, Any]):
        """主题更新事件处理"""
        # 记录更新事件
        updated_fields = list(updates.keys())
        logger.debug(f"🔄 主题更新事件: {theme_id}, 更新字段: {updated_fields}")
    
    async def _on_theme_heat_changed(self, theme_id: int, increment: int):
        """主题热度变化事件处理"""
        logger.debug(f"🔥 主题热度变化: {theme_id}, 增量: {increment}")
    
    async def _on_relation_created(self, event_id: int, theme_id: int, 
                                  relation: EventThemeRelation):
        """关联创建事件处理"""
        logger.info(f"🔗 关联创建事件: event={event_id}, theme={theme_id}, confidence={relation.confidence}")
    
    async def _on_themes_batch_created(self, themes: List[ThemeRecord]):
        """批量主题创建事件处理"""
        logger.info(f"🎉 批量创建主题事件: {len(themes)}个主题")
    
    async def register_event_handler(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger.info(f"✅ 注册事件处理器: {event_type}")
    
    async def _on_category_created(self, category: Dict):
        """分类创建事件处理"""
        try:
            logger.info(f"分类创建成功: {category.get('category_name')} ({category.get('category_code')})")
        except Exception as e:
            logger.debug(f"分类创建事件处理失败: {e}")
    
    # ========== 工具方法 ==========
    
    def _record_request(self, success: bool, start_time: float):
        """记录请求统计"""
        self._stats['requests'] += 1
        
        if success:
            self._stats['success'] += 1
        else:
            self._stats['errors'] += 1
        
        # 记录响应时间（仅成功请求）
        if success:
            elapsed = time.time() - start_time
            self._stats['response_times'].append(elapsed)
    
    @staticmethod
    def retry_on_failure(max_retries: int = 3, retry_delay: float = 1.0):
        """重试装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        
                        if attempt < max_retries - 1:
                            delay = retry_delay * (2 ** attempt)  # 指数退避
                            logger.warning(f"操作失败，{delay:.1f}秒后重试 {attempt + 1}/{max_retries}: {e}")
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"操作失败，已达最大重试次数: {e}")
                
                raise last_exception
            return wrapper
        return decorator
    
    async def close(self):
        """关闭连接"""
        try:
            if self._client:
                if hasattr(self._client, "close"):
                    await self._client.close()
                elif hasattr(self._client, "disconnect"):
                    await self._client.disconnect()
            if self._read_client and self._read_client is not self._client:
                if hasattr(self._read_client, "close"):
                    await self._read_client.close()
                elif hasattr(self._read_client, "disconnect"):
                    await self._read_client.disconnect()
            self._initialized = False
            logger.info("✅ DatabaseGateway 已关闭")
        except Exception as e:
            logger.error(f"关闭连接失败: {e}")
        finally:
            DatabaseGateway._instance = None
            DatabaseGateway._client = None
            DatabaseGateway._read_client = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return await self.get_instance()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
    
    # ========== 便捷方法 ==========
    
    async def get_theme_summary(self, theme_id: int) -> Dict[str, Any]:
        """获取主题摘要信息"""
        theme = await self.get_theme(theme_id)
        if not theme:
            return {}
        
        events = await self.get_theme_events(theme_id, 10)
        
        return {
            'id': theme.id,
            'name': theme.name,
            'code': theme.code,
            'description': theme.description,
            'heat_score': theme.heat_score,
            'category': {
                'level1': theme.level1_category,
                'level2': theme.level2_category,
                'level3': theme.level3_category
            },
            'stats': {
                'stock_count': theme.stock_count,
                'news_count': theme.news_count,
                'mention_count': theme.mention_count,
                'event_count': len(events)
            },
            'tags': theme.tags.to_dict() if hasattr(theme.tags, 'to_dict') else {},
            'last_active': theme.last_active_at.isoformat() if theme.last_active_at else None
        }
    
    async def validate_theme_code(self, code: str) -> Dict[str, Any]:
        """验证主题code是否可用"""
        try:
            existing = await self.get_theme_by_code(code)
            
            return {
                'available': existing is None,
                'code': code,
                'exists': existing is not None,
                'existing_theme': {
                    'id': existing.id if existing else None,
                    'name': existing.name if existing else None
                } if existing else None
            }
        except Exception as e:
            return {
                'available': False,
                'error': str(e),
                'code': code
            }

    # ========== Phase 6A: intel 门面方法 ==========

    async def upsert_raw_intel_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """幂等写入 raw_intel_document（写库）。"""
        try:
            start_time = time.time()
            result = await self._client.upsert_raw_intel_document(doc)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("upsert_raw_intel_document 失败: %s", e)
            raise

    async def get_raw_intel_documents_by_status(
        self, llm_status: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """按 llm_status 读 raw_intel_document（读库）。"""
        try:
            start_time = time.time()
            result = await self._read_source().get_raw_intel_documents_by_status(llm_status, limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("get_raw_intel_documents_by_status 失败: %s", e)
            raise

    async def update_raw_intel_llm_status(self, doc_id: int, status: str) -> None:
        """更新 raw_intel_document.llm_status（写库）。"""
        try:
            start_time = time.time()
            result = await self._client.update_raw_intel_llm_status(doc_id, status)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("update_raw_intel_llm_status 失败 doc_id=%s: %s", doc_id, e)
            raise

    async def insert_structured_intel_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """插入 structured_intel_event（写库）。"""
        try:
            start_time = time.time()
            result = await self._client.insert_structured_intel_event(event)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("insert_structured_intel_event 失败: %s", e)
            raise

    async def get_pending_intel_events_for_stream(
        self, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """按 stream_status='pending' 读待投递 intel events（读库）。"""
        try:
            start_time = time.time()
            result = await self._read_source().get_pending_intel_events_for_stream(limit)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("get_pending_intel_events_for_stream 失败: %s", e)
            raise

    async def get_intel_event_for_stream(self, intel_event_id: int) -> Optional[Dict[str, Any]]:
        """按 id 精确读取待投递/已投递 intel event（读库）。"""
        try:
            start_time = time.time()
            result = await self._read_source().get_intel_event_for_stream(intel_event_id)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("get_intel_event_for_stream 失败 event_id=%s: %s", intel_event_id, e)
            raise

    async def update_intel_event_stream_status(
        self,
        event_id: int,
        status: str,
        stream_message_id: Optional[str] = None,
    ) -> None:
        """更新 structured_intel_event.stream_status（写库）。"""
        try:
            start_time = time.time()
            try:
                result = await self._client.update_intel_event_stream_status(
                    event_id,
                    status,
                    stream_message_id=stream_message_id,
                )
            except TypeError:
                result = await self._client.update_intel_event_stream_status(event_id, status)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("update_intel_event_stream_status 失败 event_id=%s: %s", event_id, e)
            raise

    async def create_news_event_with_intel(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """写入 news_event（source_category='intel'）（写库）。"""
        try:
            start_time = time.time()
            async with self._db_op():
                result = await self._client.create_news_event_with_intel(event_data)
            self._record_request(True, start_time)
            return result
        except Exception as e:
            self._record_request(False, start_time)
            logger.error("create_news_event_with_intel 失败: %s", e)
            raise


# 全局单例访问函数
async def get_gateway() -> DatabaseGateway:
    """获取全局网关实例"""
    return await DatabaseGateway.get_instance()


# 简化访问装饰器
def with_gateway(func):
    """自动注入gateway参数的装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if 'gateway' not in kwargs:
            kwargs['gateway'] = await get_gateway()
        return await func(*args, **kwargs)
    return wrapper


# 快捷访问函数
async def get_theme(theme_id: int) -> Optional[ThemeRecord]:
    """快捷获取主题"""
    gateway = await get_gateway()
    return await gateway.get_theme(theme_id)


async def create_theme(name: str, code: str, **kwargs) -> Optional[ThemeRecord]:
    """快捷创建主题"""
    gateway = await get_gateway()
    return await gateway.create_theme(name, code, **kwargs)


async def find_related_themes(event_data: Dict[str, Any], limit: int = 5) -> List[ThemeRecord]:
    """快捷查找相关主题"""
    gateway = await get_gateway()
    return await gateway.find_related_themes(event_data, limit)


async def get_stats() -> Dict[str, Any]:
    """快捷获取统计"""
    gateway = await get_gateway()
    return await gateway.get_stats()

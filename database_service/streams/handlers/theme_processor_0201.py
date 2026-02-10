"""
theme_processor.py - 3.1任务：精简版主题处理器
位置：database_service/streams/handlers/
专注于数据传递，不做关键词提取
"""
import asyncio
import logging
import json
import os
import time
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any

import redis.asyncio as redis

# 添加项目路径，确保可以导入相关模块
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, project_root)

# 配置日志
logger = logging.getLogger(__name__)


class ThemeProcessor:
    """主题处理器 - 精简版，专注于数据传递"""
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        enable_retry: bool = True,
        consumer_name: str = None,
        enable_clustering: bool = False,
        config: Optional[Dict] = None,
        db_manager: Any = None,  # 🔥 新增：接收外部db_manager
        enable_classification_first: bool = True  # 🔥 新增：分类优先模式开关
    ):
        """
        初始化主题处理器
        
        Args:
            redis_host: Redis主机地址
            redis_port: Redis端口
            enable_retry: 是否启用重试
            consumer_name: 消费者名称
            enable_clustering: 是否启用聚类分析
            config: 额外配置
        """
        self.redis_client = None
        self.gateway = None
        self.theme_service = None
        self.enable_retry = enable_retry
        self.enable_clustering = enable_clustering
        self.running = False

        # 🔥 新增：保存外部传入的db_manager
        self.external_db_manager = db_manager
        
        # Redis配置
        self.redis_host = redis_host
        self.redis_port = redis_port
        
        # 从config或默认值获取配置
        self.config = config or {}
        
        # Stream配置（与NewsStreamProcessor一致）
        self.input_streams = {
            "normal": self.config.get("stream_normal", "stream:events:normal"),
            "major": self.config.get("stream_major", "stream:events:major")
        }
        
        self.output_streams = {
            "pending": self.config.get("stream_pending", "stream:events:pending"),
            "theme_updates": self.config.get("stream_theme_updates", "stream:themes:updates"),
            "dead_letter": self.config.get("stream_dead_letter", "stream:dead:letter")
        }
        
        # 消费者组配置
        self.consumer_group = self.config.get("consumer_group", "theme_processors_v1")
        self.consumer_name = consumer_name or self.config.get(
            "consumer_name", 
            f"processor_{os.getpid()}_{int(time.time())}"
        )
        
        # 处理配置
        self.processing_config = {
            "normal": {
                "batch_size": self.config.get("normal_batch_size", 10),
                "block_time": self.config.get("normal_block_time", 2000),
                "match_threshold": self.config.get("normal_threshold", 0.5)
            },
            "major": {
                "batch_size": self.config.get("major_batch_size", 5),
                "block_time": self.config.get("major_block_time", 1000),
                "match_threshold": self.config.get("major_threshold", 0.7)
            }
        }
        
        # 统计信息
        self.stats = {
            "phase": "3.1_integration_simplified",
            "started_at": None,
            "total_processed": 0,
            "by_stream": {"normal": 0, "major": 0},
            "by_outcome": {"matched": 0, "pending": 0, "error": 0},
            "database_operations": {
                "theme_queries": 0,
                "theme_by_category_queries": 0,
                "stream_publishes": 0
            },
            "last_processed": None,
            "errors": []
        }

        # 分类优先模式配置
        self.enable_classification_first = enable_classification_first
        self.classification_config = {
            "category_match_threshold": 0.3,  # 分类匹配阈值
            "max_themes_per_category": 100,   # 每个分类最多加载的题材数
            "enable_category_cache": True,    # 启用分类缓存
            "cache_ttl_seconds": 300,         # 缓存时间（秒）
            "fallback_to_full_match": True    # 分类失败时回退到全量匹配
        }
        
        # 分类相关统计
        self.classification_stats = {
            "category_inferences": 0,
            "category_matched": 0,
            "category_not_matched": 0,
            "themes_loaded_by_category": 0,
            "category_cache_hits": 0,
            "category_cache_misses": 0
        }
        
        # 分类缓存
        self.category_cache = {}  # category_code -> themes
        self.category_match_cache = {}  # event_id -> category_result
        
        print(f"🎯 ThemeProcessor初始化 - 分类优先模式: {'启用' if enable_classification_first else '禁用'}")
        
        # 外部未匹配池（用于聚类分析）
        self.external_unmatched_pool = []
        
        logger.info(f"🎯 ThemeProcessor初始化 - 消费者: {self.consumer_name}")
        logger.info(f"   输入流: {self.input_streams}")
        logger.info(f"   输出流: {self.output_streams}")
        logger.info(f"   聚类分析: {'已启用' if enable_clustering else '未启用'}")
    
    async def initialize(self):
        """初始化所有组件 - 修复两种模式的数据加载"""
        logger.info("=" * 60)
        logger.info(f"🔄 ThemeProcessor组件初始化（分类优先模式: {self.enable_classification_first}）")
        logger.info("=" * 60)
        
        try:
            # 1. 初始化Redis客户端（保持不变）
            logger.info("1. 连接Redis...")
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                max_connections=10
            )
            
            pong = await self.redis_client.ping()
            if not pong:
                raise Exception("Redis连接测试失败")
            
            logger.info(f"   ✅ Redis连接成功: {self.redis_host}:{self.redis_port}")
            
            # 2. 初始化DatabaseGateway（保持不变）
            logger.info("2. 初始化DatabaseGateway...")
            from database_service.streams.gateway_integration import get_gateway
            self.gateway = await get_gateway(enable_retry=self.enable_retry)
            
            gateway_type = type(self.gateway).__name__
            logger.info(f"   ✅ Gateway类型: {gateway_type}")
            
            # 测试数据库连接
            await self._test_database_connection()
            
            # 3. 初始化ThemeService - 🔥 简洁清晰的修复
            logger.info("3. 初始化ThemeService...")
            from theme_service.services.theme_service import get_theme_service
            
            self.theme_service = get_theme_service(enable_clustering=self.enable_clustering)
            
            # 🔥 关键：根据模式从数据库加载相应的数据
            if self.enable_classification_first:
                # 分类优先模式：只加载分类数据
                logger.info("   🎯 使用分类优先模式初始化")
                
                # 从数据库加载分类数据
                all_categories = await self._load_all_categories_for_classification()
                
                if not all_categories:
                    logger.warning("   ⚠️  无法加载分类数据，回退到传统模式")
                    # 回退：加载全量数据
                    all_themes = await self._load_all_themes(limit=200)
                    all_categories = await self._load_all_categories()
                    await self.theme_service.initialize_with_data(
                        themes=all_themes,
                        categories=all_categories
                    )
                else:
                    # 🔥 使用ThemeService的专用方法
                    if hasattr(self.theme_service, 'initialize_with_categories_only'):
                        init_success = await self.theme_service.initialize_with_categories_only(
                            categories=all_categories,
                            db_manager=self.external_db_manager or self.gateway
                        )
                        
                        if not init_success:
                            logger.warning("   ⚠️  分类专用初始化失败，回退到传统模式")
                            all_themes = await self._load_all_themes(limit=200)
                            all_categories = await self._load_all_categories()
                            await self.theme_service.initialize_with_data(
                                themes=all_themes,
                                categories=all_categories
                            )
                    else:
                        logger.warning("   ⚠️  ThemeService不支持分类专用初始化，使用传统模式")
                        all_themes = await self._load_all_themes(limit=200)
                        all_categories = await self._load_all_categories()
                        await self.theme_service.initialize_with_data(
                            themes=all_themes,
                            categories=all_categories
                        )
            else:
                # 传统模式：加载全量数据
                logger.info("   🏛️  使用传统模式初始化")
                
                # 从数据库加载全量数据
                all_themes = await self._load_all_themes(limit=200)
                all_categories = await self._load_all_categories()
                
                if not all_themes or not all_categories:
                    logger.warning("   ⚠️  数据库数据加载失败，使用空数据初始化")
                    await self.theme_service.initialize()
                else:
                    # 🔥 使用ThemeService的数据驱动初始化
                    if hasattr(self.theme_service, 'initialize_with_data'):
                        await self.theme_service.initialize_with_data(
                            themes=all_themes,
                            categories=all_categories
                        )
                    else:
                        logger.warning("   ⚠️  ThemeService没有initialize_with_data方法，使用initialize()")
                        await self.theme_service.initialize(db_manager=self.external_db_manager)
            
            # 4. 验证服务状态
            status = await self.theme_service.get_service_status()
            logger.info(f"   ✅ ThemeService状态: {status.get('status', 'unknown')}")
            logger.info(f"   ✅ 初始化完成: {status.get('initialized', False)}")
            
            # 记录数据统计
            if hasattr(self.theme_service, 'data_stats'):
                stats = self.theme_service.data_stats
                logger.info(f"   📊 数据统计: {stats.get('themes_count', 0)}题材, {stats.get('categories_count', 0)}分类")
            elif 'data_stats' in status:
                stats = status['data_stats']
                logger.info(f"   📊 数据统计: {stats.get('themes_count', 0)}题材, {stats.get('categories_count', 0)}分类")
            
            # 5. 创建消费者组
            logger.info("4. 创建Stream消费者组...")
            await self._create_consumer_groups()
            
            # 6. 打印配置摘要
            logger.info("5. 配置摘要:")
            logger.info(f"   模式: {'分类优先' if self.enable_classification_first else '传统全量'}")
            logger.info(f"   聚类分析: {'已启用' if self.enable_clustering else '未启用'}")
            logger.info(f"   重试机制: {'已启用' if self.enable_retry else '未启用'}")
            
            if self.enable_classification_first:
                logger.info(f"   分类匹配阈值: {self.classification_config['category_match_threshold']}")
                logger.info(f"   最大题材数/分类: {self.classification_config['max_themes_per_category']}")
            
            logger.info("=" * 60)
            logger.info("✅ ThemeProcessor初始化完成")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            await self._cleanup()
            raise
    
    async def _test_database_connection(self):
        """测试数据库连接 - 简化版"""
        try:
            # 测试全量查询
            themes = await self._load_all_themes(limit=3)
            logger.info(f"   ✅ 数据库测试: 加载 {len(themes)} 个题材")
            self.stats["database_operations"]["theme_queries"] += 1
            
            if themes:
                logger.info(f"   ✅ 示例题材: {themes[0].get('name', 'Unknown')}")
            
            return True
            
        except Exception as e:
            logger.warning(f"   ⚠️  数据库测试失败: {e}")
            return False
    
    async def _load_all_categories_for_classification(self) -> List[Dict]:
        """加载全部分类数据（用于分类优先模式）"""
        try:
            logger.info("   加载全部分类数据...")
            
            categories = []
            
            # 方法1: 通过DatabaseGateway的load_all_categories方法
            if hasattr(self.gateway, 'load_all_categories'):
                categories = await self.gateway.load_all_categories()
                logger.info(f"   ✅ 通过gateway加载分类数据: {len(categories)} 条")
                return categories
            
            # 方法2: 尝试通过base_gateway
            elif hasattr(self.gateway, 'load_all_categories') and hasattr(self.gateway.base_gateway, 'load_all_categories'):
                categories = await self.gateway.load_all_categories()
                logger.info(f"   ✅ 通过base_gateway加载分类数据: {len(categories)} 条")
                return categories
            
            # 方法3: 如果都没有，使用模拟数据
            if not categories:
                logger.warning("   ⚠️  无法从数据库加载分类数据，使用模拟数据")
                categories = self._get_mock_categories()
            
            # 验证分类数据格式
            validated_categories = []
            for cat in categories:
                if isinstance(cat, dict) and 'category_code' in cat:
                    validated_categories.append(cat)
                else:
                    logger.warning(f"   跳过无效分类数据: {type(cat)}")
            
            logger.info(f"   最终分类数据: {len(validated_categories)} 条有效记录")
            return validated_categories
            
        except Exception as e:
            logger.error(f"   加载分类数据失败: {e}")
            return []
    
    async def _load_all_themes(self, limit: int = 200) -> List[Dict]:
        """加载所有题材数据 - 修复版"""
        try:
            logger.info(f"   加载全量题材数据，限制: {limit}")
            
            # 🔥 关键修复1：检查 gateway 是否存在
            if self.gateway is None:
                logger.error("   ❌ gateway 未初始化")
                return []
            
            theme_records = []
            
            # 🔥 关键修复2：正确的方法名检查和错误消息
            if hasattr(self.gateway, 'get_all_active_themes'):
                try:
                    theme_records = await self.gateway.get_all_active_themes(limit=limit)
                    self.stats["database_operations"]["theme_queries"] += 1
                    logger.info(f"   从数据库获取 {len(theme_records)} 个题材")
                except Exception as e:
                    logger.error(f"   ❌ gateway.get_all_active_themes调用失败: {e}")
                    return []
            else:
                # 🔥 修复错误消息
                logger.error(f"   ❌ gateway没有get_all_active_themes方法")
                logger.error(f"   gateway类型: {type(self.gateway).__name__}")
                logger.error(f"   gateway属性: {dir(self.gateway)}")
                return []
            
            # 转换为ThemeDiscoveryEngine需要的格式
            formatted_themes = []
            for i, record in enumerate(theme_records):
                theme_dict = self._convert_theme_to_format(record)
                if theme_dict:
                    formatted_themes.append(theme_dict)
                
                # 记录前3个示例
                if i < 3:
                    logger.debug(f"     示例题材{i+1}: {theme_dict.get('name', 'N/A')}")
            
            logger.info(f"   格式化完成: {len(formatted_themes)} 个有效题材")
            return formatted_themes
                
        except Exception as e:
            logger.error(f"   加载题材失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _load_all_categories(self) -> List[Dict]:
        """加载所有分类数据 - 适配ThemeDiscoveryEngine格式"""
        try:
            logger.info("   加载全部分类数据...")
            
            categories = []
            
            # 🔥 方法1：优先使用gateway的load_all_categories方法
            if hasattr(self.gateway, 'load_all_categories'):
                try:
                    categories = await self.gateway.load_all_categories()
                    logger.info(f"   通过gateway.load_all_categories获取 {len(categories)} 个分类")
                    return categories
                except Exception as e:
                    logger.warning(f"   ⚠️  gateway.load_all_categories调用失败: {e}")
            
            # 🔥 方法2：尝试通过base_gateway的load_categories方法
            elif hasattr(self.gateway, 'load_all_categories'):
                base_gateway = self.gateway.base_gateway
                
                # 方法2.1：base_gateway有load_categories方法
                if hasattr(base_gateway, 'load_categories'):
                    try:
                        categories = await base_gateway.load_categories()
                        logger.info(f"   通过base_gateway.load_categories获取 {len(categories)} 个分类")
                        return categories
                    except Exception as e:
                        logger.warning(f"   ⚠️  base_gateway.load_categories调用失败: {e}")
                
                # 方法2.2：base_gateway有load_all_categories方法
                elif hasattr(base_gateway, 'load_all_categories'):
                    try:
                        categories = await base_gateway.load_all_categories()
                        logger.info(f"   通过base_gateway.load_all_categories获取 {len(categories)} 个分类")
                        return categories
                    except Exception as e:
                        logger.warning(f"   ⚠️  base_gateway.load_all_categories调用失败: {e}")
                
                # 方法2.3：回退到SQL查询（原始方法，但需要检查是否有execute_query）
                elif hasattr(base_gateway, 'execute_query'):
                    try:
                        query = """
                        SELECT 
                            category_code,
                            category_name,
                            category_level,
                            parent_code,
                            keywords
                        FROM financial_categories
                        WHERE category_level IN (1, 2, 3)
                        ORDER BY category_level, category_code
                        LIMIT 100
                        """
                        
                        results = await base_gateway.execute_query(query)
                        
                        for cat in results:
                            formatted_cat = {
                                'category_code': cat.get('category_code', ''),
                                'category_name': cat.get('category_name', ''),
                                'category_level': cat.get('category_level', 1),
                                'parent_code': cat.get('parent_code'),
                                'keywords': self._parse_json_field(cat.get('keywords', '[]')),
                                'source': 'database'
                            }
                            categories.append(formatted_cat)
                        
                        logger.info(f"   通过SQL查询获取 {len(categories)} 个分类")
                        return categories
                    except Exception as query_error:
                        logger.warning(f"   分类SQL查询失败: {query_error}")
            
            # 🔥 方法3：如果都没有，返回空列表（不报错）
            logger.warning("   ⚠️  gateway不支持分类数据加载方法，返回空列表")
            return []
                
        except Exception as e:
            logger.error(f"   加载分类失败: {e}")
            return []  # 返回空列表，不抛出异常
    
    def _convert_theme_to_format(self, theme_record) -> Dict:
        """将ThemeRecord转换为ThemeDiscoveryEngine需要的格式"""
        try:
            # 如果已经有to_dict方法，直接使用
            if hasattr(theme_record, 'to_dict'):
                theme_dict = theme_record.to_dict()
            elif hasattr(theme_record, '__dict__'):
                theme_dict = theme_record.__dict__
            else:
                theme_dict = theme_record
            
            # 构建标准格式
            formatted = {
                'id': str(theme_dict.get('id', '')),
                'code': theme_dict.get('code', ''),
                'name': theme_dict.get('name', ''),
                'theme_type': theme_dict.get('theme_type', 'unknown'),
                'heat_score': float(theme_dict.get('heat_score', 0)),
                'level1_category': theme_dict.get('level1_category', ''),
                'level2_category': theme_dict.get('level2_category', ''),
                'category1_code': theme_dict.get('category1_code', ''),
                'category2_code': theme_dict.get('category2_code', ''),
                'description': theme_dict.get('description', ''),
                'source': 'database'
            }
            
            # 处理tags字段
            tags = theme_dict.get('tags')
            if isinstance(tags, dict):
                formatted['tags'] = tags
            elif isinstance(tags, str):
                try:
                    formatted['tags'] = json.loads(tags)
                except:
                    formatted['tags'] = {'keywords': [formatted['name']]}
            else:
                formatted['tags'] = {'keywords': [formatted['name']]}
            
            return formatted
            
        except Exception as e:
            logger.error(f"转换题材格式失败: {e}")
            # 返回一个基本的格式
            return {
                'id': str(getattr(theme_record, 'id', '0')),
                'code': getattr(theme_record, 'code', 'UNKNOWN'),
                'name': getattr(theme_record, 'name', '未知主题'),
                'theme_type': 'unknown',
                'heat_score': 0,
                'tags': {'keywords': []}
            }
    
    def _parse_json_field(self, field_value):
        """解析JSON字段"""
        if not field_value:
            return []
        
        if isinstance(field_value, list):
            return field_value
        
        if isinstance(field_value, str):
            try:
                return json.loads(field_value)
            except:
                # 尝试逗号分隔
                if ',' in field_value:
                    return [item.strip() for item in field_value.split(',') if item.strip()]
                else:
                    return [field_value.strip()]
        
        return []
    
    async def _create_consumer_groups(self):
        """创建Redis Stream消费者组"""
        for stream_type, stream_name in self.input_streams.items():
            try:
                # 先检查流是否存在，如果不存在则创建
                try:
                    await self.redis_client.xinfo_stream(stream_name)
                except Exception:
                    # 流不存在，创建空流
                    await self.redis_client.xadd(stream_name, {"init": "stream_created"}, maxlen=1, id="0")
                    logger.debug(f"   创建空流: {stream_name}")
                
                # 创建消费者组
                try:
                    await self.redis_client.xgroup_create(
                        stream_name,
                        self.consumer_group,
                        id="0",
                        mkstream=False  # 流已经存在
                    )
                    logger.info(f"   创建消费者组: {stream_name}/{self.consumer_group}")
                except Exception as e:
                    if "BUSYGROUP" in str(e):
                        logger.debug(f"   消费者组已存在: {stream_name}")
                    else:
                        raise
                        
            except Exception as e:
                logger.error(f"   创建消费者组失败 {stream_name}: {e}")
                # 但不抛出异常，让处理器继续运行
    
    async def start(self):
        """启动主题处理器"""
        if self.running:
            logger.warning("处理器已在运行")
            return
        
        self.running = True
        self.stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动ThemeProcessor...")
        
        # 启动双流消费者
        self.tasks = [
            asyncio.create_task(self._process_stream("normal"), name=f"normal_processor"),
            asyncio.create_task(self._process_stream("major"), name=f"major_processor")
        ]
        
        logger.info("✅ ThemeProcessor启动成功")
        return self.tasks
    
    async def _process_stream(self, stream_type: str):
        """处理单个Stream"""
        stream_name = self.input_streams[stream_type]
        config = self.processing_config[stream_type]
        
        logger.info(f"📥 开始处理 {stream_type} 流: {stream_name}")
        
        while self.running:
            try:
                # 读取消息
                messages = await self.redis_client.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=f"{self.consumer_name}_{stream_type}",
                    streams={stream_name: ">"},
                    count=config["batch_size"],
                    block=config["block_time"]
                )
                
                if messages:
                    for stream, message_list in messages:
                        for message_id, message_data in message_list:
                            await self._process_message(stream_type, stream_name, message_id, message_data)
                
                # 短暂休息
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                logger.info(f"📥 {stream_type}流处理被取消")
                break
            except Exception as e:
                logger.error(f"📥 {stream_type}流处理异常: {e}")
                await asyncio.sleep(5)

    def _get_mock_categories(self) -> List[Dict]:
        """获取模拟分类数据（当无法从数据库加载时使用）"""
        return [
            {
                'category_code': '480000',
                'category_name': '银行',
                'category_level': 1,
                'keywords': ['银行', '金融', '信贷']
            },
            {
                'category_code': '480300',
                'category_name': '股份制银行',
                'category_level': 2,
                'parent_code': '480000',
                'keywords': ['股份制银行', '商业银行']
            },
            {
                'category_code': '730000',
                'category_name': '计算机',
                'category_level': 1,
                'keywords': ['计算机', '软件', 'IT']
            },
            {
                'category_code': '730100',
                'category_name': '软件开发',
                'category_level': 2,
                'parent_code': '730000',
                'keywords': ['软件', '开发', '编程']
            }
        ]

    # 🔥 新增：分类优先处理消息方法
    async def _process_message_classification_first(self, stream_type: str, stream_name: str, 
                                                message_id: str, message_data: Dict):
        """分类优先模式的消息处理"""
        start_time = time.time()
        
        try:
            # 1. 提取事件数据
            event_data = self._extract_event_data(message_data, stream_type)
            if not event_data:
                logger.warning(f"无法提取事件数据: {message_id}")
                await self._ack_message(stream_name, message_id)
                return
            
            event_id = event_data.get("event_id", f"unknown_{message_id}")
            
            logger.info(f"🔍 [分类优先] 处理事件: {event_id} ({stream_type})")
            
            # 2. 第一步：分类推断
            self.classification_stats["category_inferences"] += 1
            
            # 检查缓存
            cached_category = self.category_match_cache.get(event_id)
            if cached_category and self.classification_config["enable_category_cache"]:
                logger.debug(f"   使用缓存的分类结果: {event_id}")
                self.classification_stats["category_cache_hits"] += 1
                category_result = cached_category
            else:
                # 调用ThemeService进行分类推断
                if hasattr(self.theme_service, 'discover_category_only'):
                    category_result = await self.theme_service.discover_category_only(event_data)
                    
                    # 缓存结果
                    if self.classification_config["enable_category_cache"]:
                        self.category_match_cache[event_id] = category_result
                        self.classification_stats["category_cache_misses"] += 1
                else:
                    logger.warning("ThemeService不支持discover_category_only，回退到传统处理")
                    return await self._process_message_traditional(
                        stream_type, stream_name, message_id, message_data
                    )
            
            # 3. 第二步：根据分类结果处理
            if category_result.get('matched', False):
                self.classification_stats["category_matched"] += 1
                
                # 获取分类信息
                category_info = category_result.get('category_info', {})
                category_confidence = category_result.get('confidence', 0)
                
                logger.info(f"   ✅ 分类匹配成功: {category_info.get('level1_category', 'N/A')} "
                        f"(置信度: {category_confidence:.2f})")
                
                # 检查是否达到分类匹配阈值
                if category_confidence >= self.classification_config["category_match_threshold"]:
                    # 3.1 按分类加载题材并进行匹配
                    themes_in_category = await self._load_themes_by_category(category_info)
                    
                    if themes_in_category:
                        # 在这些题材中进行匹配
                        match_result = await self._match_in_themes(
                            themes_in_category, event_data, stream_type
                        )
                        
                        if match_result.get('matched', False):
                            # 匹配成功，处理匹配事件
                            await self._handle_matched_event(stream_type, event_data, match_result)
                            logger.info(f"   🎯 分类下匹配成功: {len(match_result.get('themes', []))} 个题材")
                        else:
                            # 分类下未匹配，进入未匹配流程
                            await self._handle_unmatched_event(
                                stream_type, event_data, 
                                {'category_matched': True, 'category_info': category_info}, 
                                message_id
                            )
                            logger.info(f"   ⚠️  分类下未匹配，进入未匹配流程")
                    else:
                        # 分类下没有题材，进入未匹配流程
                        await self._handle_unmatched_event(
                            stream_type, event_data, 
                            {'category_matched': True, 'category_info': category_info, 'no_themes': True}, 
                            message_id
                        )
                        logger.info(f"   ⚠️  分类下无题材，进入未匹配流程")
                else:
                    # 分类置信度不足，进入未匹配流程
                    await self._handle_unmatched_event(
                        stream_type, event_data, 
                        {'category_matched': True, 'confidence_too_low': True}, 
                        message_id
                    )
                    logger.info(f"   ⚠️  分类置信度不足 ({category_confidence:.2f} < "
                            f"{self.classification_config['category_match_threshold']})")
            else:
                # 分类未匹配
                self.classification_stats["category_not_matched"] += 1
                
                # 根据配置决定是否回退到全量匹配
                if self.classification_config["fallback_to_full_match"]:
                    logger.info(f"   🔄 分类未匹配，回退到全量匹配")
                    
                    # 调用ThemeService的完整发现功能
                    result = await self.theme_service.discover_theme(
                        event_data,
                        min_confidence=0.5 if stream_type == "normal" else 0.7,
                        external_unmatched_pool=self.external_unmatched_pool if self.enable_clustering else None
                    )
                    
                    # 根据结果处理
                    if result.get("response", {}).get("matched", False):
                        await self._handle_matched_event(stream_type, event_data, result["response"])
                    else:
                        await self._handle_unmatched_event(stream_type, event_data, result["response"], message_id)
                else:
                    # 直接进入未匹配流程
                    await self._handle_unmatched_event(
                        stream_type, event_data, 
                        {'category_matched': False, 'reason': 'no_category_match'}, 
                        message_id
                    )
                    logger.info(f"   ⚠️  分类未匹配，直接进入未匹配流程")
            
            # 4. ACK消息
            await self._ack_message(stream_name, message_id)

            # 🔥 新增：更新统计信息
            self.stats["total_processed"] += 1
            self.stats["by_stream"][stream_type] += 1
            
            # 5. 更新统计
            processing_time = time.time() - start_time
            self.stats["last_processed"] = {
                "event_id": event_id,
                "stream_type": stream_type,
                "processing_time": processing_time,
                "mode": "classification_first",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.stats["by_outcome"]["error"] += 1
            logger.error(f"分类优先处理失败 {message_id}: {e}")
            import traceback
            traceback.print_exc()
            
            # 将失败消息移动到死信队列
            await self._move_to_dead_letter(stream_type, message_id, message_data, str(e))

    async def _load_themes_by_category(self, category_info: Dict) -> List[Dict]:
        """按分类加载题材 - 处理 ThemeRecord 对象"""
        try:
            level2_code = category_info.get('level2_code')
            
            logger.info(f"  🔍 按分类加载题材: level2_code={level2_code}")
            
            # 确保 gateway 有该方法
            if not hasattr(self.gateway, 'get_themes_by_category'):
                logger.error(f"  ❌ gateway没有get_themes_by_category方法")
                return []
            
            # 调用方法获取 ThemeRecord 列表
            theme_records = await self.gateway.get_themes_by_category(
                level2_code, level=2, 
                limit=self.classification_config["max_themes_per_category"]
            )
            
            logger.info(f"  📊 获取到 {len(theme_records)} 个 ThemeRecord")
            
            if not theme_records:
                logger.warning(f"  ⚠️  没有找到对应分类的题材")
                return []
            
            # 🔥 关键：转换 ThemeRecord 为字典格式
            formatted_themes = []
            for i, theme_record in enumerate(theme_records):
                logger.debug(f"   转换 ThemeRecord[{i}]: 类型={type(theme_record)}")
                
                # 方法1：尝试调用 to_dict() 方法
                if hasattr(theme_record, 'to_dict'):
                    theme_dict = theme_record.to_dict()
                    logger.debug(f"     使用 to_dict() 转换")
                
                # 方法2：尝试使用 as_dict() 方法（SQLAlchemy等常用）
                elif hasattr(theme_record, 'as_dict'):
                    theme_dict = theme_record.as_dict()
                    logger.debug(f"     使用 as_dict() 转换")
                
                # 方法3：使用 __dict__ 属性
                elif hasattr(theme_record, '__dict__'):
                    theme_dict = theme_record.__dict__
                    logger.debug(f"     使用 __dict__ 转换")
                    
                    # 清理 SQLAlchemy 的内部属性
                    if '_sa_instance_state' in theme_dict:
                        del theme_dict['_sa_instance_state']
                
                # 方法4：其他情况，手动构建
                else:
                    logger.warning(f"     ⚠️  ThemeRecord 没有标准转换方法")
                    theme_dict = {
                        'id': getattr(theme_record, 'id', f'unknown_{i}'),
                        'code': getattr(theme_record, 'code', f'CODE_{i:06d}'),
                        'name': getattr(theme_record, 'name', f'未命名题材_{i}'),
                        'theme_type': getattr(theme_record, 'theme_type', 'normal'),
                        'heat_score': float(getattr(theme_record, 'heat_score', 50.0)),
                        'level1_category': getattr(theme_record, 'level1_category', ''),
                        'level2_category': getattr(theme_record, 'level2_category', ''),
                        'description': getattr(theme_record, 'description', ''),
                    }
                
                # 🔥 确保必要字段存在
                required_fields = ['id', 'code', 'name', 'theme_type', 'heat_score']
                for field in required_fields:
                    if field not in theme_dict:
                        if field == 'id':
                            theme_dict['id'] = str(i)
                        elif field == 'code':
                            theme_dict['code'] = f'TEMP_{i:06d}'
                        elif field == 'name':
                            theme_dict['name'] = f'题材_{i}'
                        elif field == 'theme_type':
                            theme_dict['theme_type'] = 'normal'
                        elif field == 'heat_score':
                            theme_dict['heat_score'] = 50.0
                
                # 确保 tags 字段存在
                if 'tags' not in theme_dict:
                    theme_dict['tags'] = {'keywords': []}
                elif isinstance(theme_dict['tags'], str):
                    # 如果 tags 是字符串，尝试解析
                    try:
                        theme_dict['tags'] = json.loads(theme_dict['tags'])
                    except:
                        theme_dict['tags'] = {'keywords': [theme_dict['name']]}
                
                # 记录转换结果
                logger.debug(f"     转换结果: id={theme_dict.get('id')}, name={theme_dict.get('name')}")
                
                formatted_themes.append(theme_dict)
            
            logger.info(f"  ✅ 转换完成: {len(formatted_themes)} 个字典格式的题材")
            
            if formatted_themes:
                sample = formatted_themes[0]
                logger.info(f"  示例题材: id={sample.get('id')}, code={sample.get('code')}, name={sample.get('name')}")
                logger.debug(f"  完整示例: {json.dumps(sample, ensure_ascii=False, indent=2)}")
            
            return formatted_themes
            
        except Exception as e:
            logger.error(f"   按分类加载题材失败: {e}")
            import traceback
            logger.error(f"   详细错误: {traceback.format_exc()}")
            return []

    async def _match_in_themes(self, themes: List[Dict], event_data: Dict, stream_type: str) -> Dict:
        """在指定的题材列表中匹配事件"""
        try:
            if not themes:
                logger.debug("  没有题材可匹配")
                return {'matched': False, 'themes': [], 'confidence': 0.0}
            
            logger.debug(f"  开始匹配，题材数: {len(themes)}, 事件: {event_data.get('event_id')}")
            
            # 🔥 使用测试配置
            from database_service.streams.handlers.test_keyword_matcher_config import TEST_CONFIG
            
            config = TEST_CONFIG.copy()
            # 根据stream_type调整阈值
            if stream_type == 'major':
                config['match_threshold'] = 0.3  # major流用0.3
            else:
                config['match_threshold'] = 0.2  # normal流用0.2
            
            # 创建临时 KeywordMatcher
            from theme_service.matchers.keyword_matcher import KeywordMatcher
            
            matcher = KeywordMatcher(config)
            
            logger.debug(f"  准备初始化KeywordMatcher，传入{len(themes)}个题材（列表格式）")
            
            try:
                matcher.initialize(themes, categories=[])
                logger.debug("  ✅ matcher初始化成功")
            except Exception as init_error:
                logger.error(f"  ❌ matcher初始化失败: {init_error}")
                return {'matched': False, 'themes': [], 'confidence': 0.0}
            
            # 执行匹配
            matches = matcher.match(event_data)
            logger.debug(f"  匹配结果类型: {type(matches)}, 长度: {len(matches) if matches else 0}")
            
            # 处理匹配结果
            matched_themes = []
            
            if isinstance(matches, list) and matches:
                # 转换格式
                for match in matches[:5]:  # 最多5个
                    if hasattr(match, 'theme_id'):
                        matched_themes.append({
                            'id': getattr(match, 'theme_id', ''),
                            'name': getattr(match, 'theme_name', ''),
                            'confidence': getattr(match, 'confidence', 0),
                            'matched_keywords': getattr(match, 'matched_keywords', []),
                            'match_type': getattr(match, 'match_type', 'unknown')
                        })
                    elif isinstance(match, dict):
                        matched_themes.append({
                            'id': match.get('theme_id', ''),
                            'name': match.get('theme_name', ''),
                            'confidence': match.get('confidence', 0),
                            'matched_keywords': match.get('matched_keywords', []),
                            'match_type': match.get('match_type', 'unknown')
                        })
                
                logger.debug(f"  匹配到 {len(matched_themes)} 个题材")
            
            return {
                'matched': len(matched_themes) > 0,
                'themes': matched_themes,
                'confidence': matched_themes[0]['confidence'] if matched_themes else 0.0,
                'theme_count': len(matched_themes)
            }
                
        except Exception as e:
            logger.error(f"  在题材列表中匹配失败: {e}")
            import traceback
            logger.error(f"  详细错误: {traceback.format_exc()}")
            return {'matched': False, 'themes': [], 'confidence': 0.0}

    # 修改原有的_process_message方法，支持两种模式
    async def _process_message(self, stream_type: str, stream_name: str, message_id: str, message_data: Dict):
        """处理单个消息 - 支持分类优先和传统模式"""
        if self.enable_classification_first:
            return await self._process_message_classification_first(
                stream_type, stream_name, message_id, message_data
            )
        else:
            return await self._process_message_traditional(
                stream_type, stream_name, message_id, message_data
            )

    async def _process_message_traditional(self, stream_type: str, stream_name: str, 
                                        message_id: str, message_data: Dict):
        """传统模式的消息处理（原有逻辑）"""
        # 这里调用原有的处理逻辑
        start_time = time.time()
        
        try:
            # 提取事件数据
            event_data = self._extract_event_data(message_data, stream_type)
            if not event_data:
                logger.warning(f"无法提取事件数据: {message_id}")
                await self._ack_message(stream_name, message_id)
                return
            
            event_id = event_data.get("event_id", f"unknown_{message_id}")
            
            logger.info(f"🔍 [传统模式] 处理事件: {event_id} ({stream_type})")
            
            # 调用ThemeService进行主题发现
            result = await self.theme_service.discover_theme(
                event_data,
                min_confidence=0.5 if stream_type == "normal" else 0.7,
                external_unmatched_pool=self.external_unmatched_pool if self.enable_clustering else None
            )
            
            # 更新统计
            self.stats["total_processed"] += 1
            self.stats["by_stream"][stream_type] += 1
            
            # 根据匹配结果处理
            response = result.get("response", {})
            if response.get("matched", False):
                self.stats["by_outcome"]["matched"] += 1
                await self._handle_matched_event(stream_type, event_data, response)
                logger.info(f"   ✅ 匹配成功: {event_id}")
            else:
                self.stats["by_outcome"]["pending"] += 1
                await self._handle_unmatched_event(stream_type, event_data, response, message_id)
                logger.info(f"   ⏳ 未匹配: {event_id}")
            
            # ACK消息
            await self._ack_message(stream_name, message_id)
            
            # 更新处理时间
            processing_time = time.time() - start_time
            self.stats["last_processed"] = {
                "event_id": event_id,
                "stream_type": stream_type,
                "processing_time": processing_time,
                "mode": "traditional",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.stats["by_outcome"]["error"] += 1
            logger.error(f"传统模式处理失败 {message_id}: {e}")
            await self._move_to_dead_letter(stream_type, message_id, message_data, str(e))

    # 在get_status方法中添加分类统计
    async def get_status(self) -> Dict:
        """获取状态信息"""
        base_status = {
            "running": self.running,
            "stats": self.stats,
            "consumer": {
                "group": self.consumer_group,
                "name": self.consumer_name
            },
            "streams": {
                "input": self.input_streams,
                "output": self.output_streams
            },
            "clustering_enabled": self.enable_clustering,
            "unmatched_pool_size": len(self.external_unmatched_pool)
        }
        
        # 添加分类优先模式相关信息
        if self.enable_classification_first:
            base_status["classification_first"] = {
                "enabled": True,
                "config": self.classification_config,
                "stats": self.classification_stats,
                "cache_size": {
                    "category_match": len(self.category_match_cache),
                    "category_themes": len(self.category_cache)
                }
            }
        
        return base_status

    # 在print_stats方法中添加分类统计
    def print_stats(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("📊 ThemeProcessor统计信息")
        print("=" * 60)
        print(f"运行模式: {'分类优先' if self.enable_classification_first else '传统全量'}")
        print(f"运行时间: {self.stats['started_at']}")
        print(f"总处理事件: {self.stats['total_processed']}")
        print(f"  Normal: {self.stats['by_stream']['normal']}")
        print(f"  Major: {self.stats['by_stream']['major']}")
        print(f"匹配结果:")
        print(f"  匹配成功: {self.stats['by_outcome']['matched']}")
        print(f"  进入pending: {self.stats['by_outcome']['pending']}")
        print(f"  处理错误: {self.stats['by_outcome']['error']}")
        
        # 分类优先模式特有统计
        if self.enable_classification_first:
            print(f"分类统计:")
            print(f"  分类推断次数: {self.classification_stats['category_inferences']}")
            print(f"  分类匹配成功: {self.classification_stats['category_matched']}")
            print(f"  分类匹配失败: {self.classification_stats['category_not_matched']}")
            print(f"  按分类加载题材数: {self.classification_stats['themes_loaded_by_category']}")
            print(f"  缓存命中率: {self.classification_stats['category_cache_hits']}/"
                f"{self.classification_stats['category_cache_hits'] + self.classification_stats['category_cache_misses']}")
        
        print("=" * 60)
    
    def _extract_event_data(self, message_data: Dict, stream_type: str) -> Optional[Dict]:
        """提取事件数据 - 修复JSON字符串解析问题"""
        try:
            # 🔥 关键修复：正确处理从Redis读取的消息格式
            event_data_str = None
            
            # Redis消息格式：msg_data 是字典，但 event_data 字段是 JSON字符串
            if isinstance(message_data, dict):
                # 尝试不同的字段名
                for field in ["event_data", "data", "payload"]:
                    if field in message_data:
                        event_data_str = message_data[field]
                        break
            elif isinstance(message_data, str):
                # 如果直接是字符串，尝试解析
                event_data_str = message_data
            
            # 如果找到了字符串数据，尝试解析JSON
            if event_data_str and isinstance(event_data_str, str):
                try:
                    data = json.loads(event_data_str)
                    logger.debug(f"✅ 成功解析JSON字符串: {len(event_data_str)} 字符")
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON解析失败，使用原始字符串: {e}")
                    # 如果不是JSON，直接使用字符串
                    data = {"raw_content": event_data_str}
            elif isinstance(message_data, dict):
                # 如果已经是字典，直接使用
                data = message_data
            else:
                logger.warning(f"无法处理的消息数据类型: {type(message_data)}")
                return None
            
            # 2. 确保必要字段
            if "event_id" not in data:
                # 生成唯一ID
                import uuid
                data["event_id"] = f"{stream_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            if "event_type" not in data:
                data["event_type"] = stream_type
            
            # 3. 确保AI分析字段存在（即使为空）
            if "ai_analysis" not in data:
                data["ai_analysis"] = {}
            
            # 4. 如果是字符串，尝试解析为JSON
            if isinstance(data.get("ai_analysis"), str):
                try:
                    data["ai_analysis"] = json.loads(data["ai_analysis"])
                except:
                    data["ai_analysis"] = {}
            
            logger.debug(f"提取事件数据: {data.get('event_id')}")
            return data
            
        except Exception as e:
            logger.warning(f"提取事件数据失败: {e}")
            return None
    
    async def _handle_matched_event(self, stream_type: str, event_data: Dict, match_result: Dict):
        """处理匹配成功的事件"""
        try:
            event_id = event_data.get("event_id")
            themes = match_result.get("matched_themes", [])
            
            logger.debug(f"   匹配成功，处理 {len(themes)} 个题材")
            
            for theme in themes:
                theme_id = theme.get("id")
                theme_name = theme.get("name")
                
                # 发布主题更新到Stream
                update_data = {
                    "theme_id": theme_id,
                    "theme_name": theme_name,
                    "event_id": event_id,
                    "event_type": stream_type,
                    "confidence": match_result.get("confidence", 0.5),
                    "action": "theme_match",
                    "timestamp": datetime.now().isoformat(),
                    "processor": self.consumer_name
                }
                
                await self.redis_client.xadd(
                    self.output_streams["theme_updates"],
                    update_data,
                    maxlen=10000
                )
                self.stats["database_operations"]["stream_publishes"] += 1
                
                logger.debug(f"   发布主题更新: {event_id} -> {theme_id}")
        
        except Exception as e:
            logger.error(f"   匹配事件处理失败: {e}")
    
    async def _handle_unmatched_event(self, stream_type: str, event_data: Dict, match_result: Dict, message_id: str):
        """处理未匹配的事件"""
        try:
            # 🔥 关键修复：序列化字典字段
            pending_entry = {
                "original_event": json.dumps(event_data, ensure_ascii=False),  # 序列化为JSON字符串
                "original_stream_type": stream_type,
                "original_message_id": message_id,
                "match_result": json.dumps(match_result, ensure_ascii=False),  # 序列化为JSON字符串
                "added_at": datetime.now().isoformat(),
                "priority": "high" if stream_type == "major" else "normal",
                "processor": self.consumer_name
            }
            
            # 🔥 额外安全措施：确保所有值都是字符串类型
            for key, value in pending_entry.items():
                if isinstance(value, (dict, list)):
                    pending_entry[key] = json.dumps(value, ensure_ascii=False)
                elif not isinstance(value, (str, int, float, bool)):
                    pending_entry[key] = str(value)
            
            await self.redis_client.xadd(
                self.output_streams["pending"],
                pending_entry,
                maxlen=10000
            )
            
            logger.debug(f"   写入pending流: {event_data.get('event_id')}")
            
            # 更新统计
            self.stats["by_outcome"]["pending"] += 1
            
        except Exception as e:
            logger.error(f"   写入pending流失败: {e}")
    
    async def _ack_message(self, stream_name: str, message_id: str):
        """ACK消息"""
        try:
            await self.redis_client.xack(stream_name, self.consumer_group, message_id)
        except Exception as e:
            logger.error(f"ACK失败 {message_id}: {e}")
    
    async def _move_to_dead_letter(self, stream_type: str, message_id: str, message_data: Dict, error: str):
        """移动到死信队列"""
        try:
            dead_letter_entry = {
                "original_stream": self.input_streams[stream_type],
                "original_message_id": message_id,
                "original_data": message_data,
                "error": error,
                "moved_at": datetime.now().isoformat(),
                "processor": self.consumer_name
            }
            
            await self.redis_client.xadd(
                self.output_streams["dead_letter"],
                dead_letter_entry,
                maxlen=1000
            )
            
            logger.warning(f"消息移动到死信队列: {message_id}")
            
        except Exception as e:
            logger.error(f"移动到死信队列失败: {e}")
    
    async def stop(self):
        """停止处理器"""
        if not self.running:
            return
        
        logger.info("🛑 停止ThemeProcessor...")
        self.running = False
        
        # 取消任务
        for task in self.tasks:
            task.cancel()
        
        # 等待任务完成
        try:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        
        # 打印统计
        self.print_stats()
        
        # 清理资源
        await self._cleanup()
    
    async def _cleanup(self):
        """清理资源"""
        try:
            if self.redis_client:
                await self.redis_client.close()
            
            if self.gateway and hasattr(self.gateway, 'close'):
                await self.gateway.close()
            
            logger.info("🧹 资源已清理")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")
    
    def print_stats(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("📊 ThemeProcessor统计信息（精简版）")
        print("=" * 60)
        print(f"运行时间: {self.stats['started_at']}")
        print(f"总处理事件: {self.stats['total_processed']}")
        print(f"  Normal: {self.stats['by_stream']['normal']}")
        print(f"  Major: {self.stats['by_stream']['major']}")
        print(f"匹配结果:")
        print(f"  匹配成功: {self.stats['by_outcome']['matched']}")
        print(f"  进入pending: {self.stats['by_outcome']['pending']}")
        print(f"  处理错误: {self.stats['by_outcome']['error']}")
        print(f"数据库操作:")
        print(f"  题材查询: {self.stats['database_operations']['theme_queries']}")
        print(f"  分类查询: {self.stats['database_operations']['theme_by_category_queries']}")
        print(f"  流发布: {self.stats['database_operations']['stream_publishes']}")
        print("=" * 60)
    
    async def get_status(self) -> Dict:
        """获取状态信息"""
        return {
            "running": self.running,
            "stats": self.stats,
            "consumer": {
                "group": self.consumer_group,
                "name": self.consumer_name
            },
            "streams": {
                "input": self.input_streams,
                "output": self.output_streams
            },
            "clustering_enabled": self.enable_clustering,
            "unmatched_pool_size": len(self.external_unmatched_pool)
        }
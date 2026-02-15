# /Users/admin/Desktop/ai_theme_app/database_service/streams/handlers/theme_processor.py

"""
theme_processor.py - 优化版主题处理器
位置：database_service/streams/handlers/
专注于分类优先逻辑和决策生成，保持向后兼容
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

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


class DecisionType:
    """决策类型常量"""
    MATCH_SUCCESS_IN_CATEGORY = "match_success_in_category"      # 分类内匹配成功
    MATCH_SUCCESS_FALLBACK = "match_success_fallback"           # 回退匹配成功
    CATEGORY_NO_MATCH = "category_no_match"                     # 分类未匹配
    CATEGORY_CONFIDENCE_TOO_LOW = "category_confidence_too_low" # 分类置信度不足
    CATEGORY_NO_THEMES = "category_no_themes"                   # 分类下无题材
    NO_MATCH_IN_CATEGORY = "no_match_in_category"               # 分类内未匹配
    NO_MATCH_AFTER_FALLBACK = "no_match_after_fallback"         # 回退后仍无匹配
    ERROR_PROCESSING = "error_processing"                       # 处理错误


class ThemeProcessor:
    """主题处理器 - 优化版，保持向后兼容"""
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        enable_retry: bool = True,
        consumer_name: str = None,
        enable_clustering: bool = False,
        config: Optional[Dict] = None,
        db_manager: Any = None,
        enable_classification_first: bool = True,
        enable_decision_executor: bool = False,
        enable_clustering_listener: bool = False,
        min_cluster_size: int = 3,
        quality_threshold: float = 0.4
    ):
        """
        初始化主题处理器 - 保持原有参数签名
        """
        self.redis_client = None
        self.gateway = None
        self.theme_service = None
        self.enable_retry = enable_retry
        self.enable_clustering = enable_clustering
        self.running = False
        self.external_db_manager = db_manager
        
        # Redis配置
        self.redis_host = redis_host
        self.redis_port = redis_port
        
        # 从config或默认值获取配置
        self.config = config or {}
        
        # Stream配置（保持不变）
        self.input_streams = {
            "normal": self.config.get("stream_normal", "stream:events:normal"),
            "major": self.config.get("stream_major", "stream:events:major")
        }
        
        self.output_streams = {
            "pending": self.config.get("stream_pending", "stream:events:pending"),
            "theme_updates": self.config.get("stream_theme_updates", "stream:themes:updates"),
            "dead_letter": self.config.get("stream_dead_letter", "stream:dead:letter"),
            "decision": self.config.get("stream_decision", "stream:events:decision")
        }
        
        # 消费者组配置
        self.consumer_group = self.config.get("consumer_group", "theme_processors_v1")
        self.consumer_name = consumer_name or self.config.get(
            "consumer_name", 
            f"processor_{os.getpid()}_{int(time.time())}"
        )
        
        # 处理配置（保持不变）
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
        
        # 统计信息（保持原有结构）
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

        # 分类优先模式配置（保持原有结构）
        self.enable_classification_first = enable_classification_first
        self.classification_config = {
            "category_match_threshold": 0.2,
            "max_themes_per_category": 100,
            "enable_category_cache": True,
            "cache_ttl_seconds": 300,
            "fallback_to_full_match": True
        }
        
        # 分类相关统计（保持原有结构）
        self.classification_stats = {
            "category_inferences": 0,
            "category_matched": 0,
            "category_not_matched": 0,
            "themes_loaded_by_category": 0,
            "category_cache_hits": 0,
            "category_cache_misses": 0
        }
        
        # 分类缓存（保持原有结构）
        self.category_cache = {}
        self.category_match_cache = {}
        
        # 新组件配置（保持原有结构）
        self.component_config = {
            'enable_decision_executor': enable_decision_executor,
            'enable_clustering_listener': enable_clustering_listener,
            'clustering_config': {
                'min_cluster_size': min_cluster_size,
                'quality_threshold': quality_threshold,
                'trigger_channel': 'clustering:trigger'
            }
        }
        
        # 子组件引用（保持原有结构）
        self.decision_executor = None
        self.clustering_listener = None
        self.all_tasks = []
        
        # 外部未匹配池（保持原有结构）
        self.external_unmatched_pool = []
        
        logger.info(f"🎯 ThemeProcessor初始化 - 消费者: {self.consumer_name}")
        logger.info(f"   分类优先模式: {'启用' if enable_classification_first else '禁用'}")
    
    # ==================== 初始化方法（保持原有结构） ====================
    
    async def initialize(self) -> bool:
        """ThemeProcessor初始化 - 保持原有结构"""
        logger.info("🔄 ThemeProcessor初始化开始")
        
        # 1. 初始化Redis客户端
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
        
        # 2. 初始化DatabaseGateway
        logger.info("2. 初始化DatabaseGateway...")
        from database_service.streams.gateway_integration import get_gateway
        self.gateway = await get_gateway(enable_retry=self.enable_retry)
        
        # 3. 初始化ThemeService
        logger.info("3. 初始化ThemeService...")
        from theme_service.services.theme_service import get_theme_service
        self.theme_service = get_theme_service(enable_clustering=self.enable_clustering)
        
        # 4. 加载数据
        success = await self._load_initial_data()
        
        if success:
            logger.info("✅ ThemeProcessor初始化成功")
            self._log_initialization_summary()
        else:
            logger.error("❌ ThemeProcessor初始化失败")
        
        return success
    
    async def _load_initial_data(self) -> bool:
        """加载初始数据 - 优化内部实现"""
        try:
            if self.enable_classification_first:
                # 分类优先模式：只加载分类数据
                categories = await self._load_all_categories_for_classification()
                if not categories:
                    logger.error("❌ 无法加载分类数据")
                    return False
                
                logger.info(f"📊 加载 {len(categories)} 个分类")
                
                # 传递数据给ThemeService
                if hasattr(self.theme_service, 'initialize_with_categories_only'):
                    return await self.theme_service.initialize_with_categories_only(categories)
                else:
                    themes = await self._load_all_themes(limit=100)
                    return await self.theme_service.initialize_with_data(themes, categories)
            else:
                # 传统模式：加载全量数据
                themes = await self._load_all_themes(limit=200)
                categories = await self._load_all_categories()
                
                logger.info(f"📊 加载 {len(themes)} 个题材, {len(categories)} 个分类")
                
                if hasattr(self.theme_service, 'initialize_with_data'):
                    return await self.theme_service.initialize_with_data(themes, categories)
                else:
                    return await self.theme_service.initialize()
                
        except Exception as e:
            logger.error(f"加载初始数据失败: {e}")
            return False
    
    def _log_initialization_summary(self):
        """记录初始化摘要"""
        logger.info("📊 初始化完成:")
        logger.info(f"   模式: {'分类优先' if self.enable_classification_first else '传统'}")
        logger.info(f"   聚类分析: {'已启用' if self.enable_clustering else '未启用'}")
        logger.info(f"   消费者: {self.consumer_name}")
    
    async def _load_all_categories_for_classification(self) -> List[Dict]:
        """加载全部分类数据 - 保持原有结构"""
        try:
            logger.info("   加载全部分类数据...")
            
            if hasattr(self.gateway, 'load_all_categories'):
                categories = await self.gateway.load_all_categories()
                logger.info(f"   ✅ 通过gateway加载分类数据: {len(categories)} 条")
                return categories
            
            elif hasattr(self.gateway, 'base_gateway') and hasattr(self.gateway.base_gateway, 'load_all_categories'):
                categories = await self.gateway.base_gateway.load_all_categories()
                logger.info(f"   ✅ 通过base_gateway加载分类数据: {len(categories)} 条")
                return categories
            
            else:
                logger.warning("   ⚠️  无法从数据库加载分类数据，使用模拟数据")
                return self._get_mock_categories()
                
        except Exception as e:
            logger.error(f"   加载分类数据失败: {e}")
            return []
    
    async def _load_all_themes(self, limit: int = 200) -> List[Dict]:
        """加载所有题材数据 - 保持原有结构"""
        try:
            theme_records = []
            
            if hasattr(self.gateway, 'base_gateway'):
                theme_records = await self.gateway.get_all_active_themes(limit=limit)
                self.stats["database_operations"]["theme_queries"] += 1
                logger.info(f"   从数据库获取 {len(theme_records)} 个题材")
            else:
                logger.error("   ❌ DatabaseGateway缺少base_gateway属性")
                return []
            
            # 转换格式
            formatted_themes = []
            for record in theme_records:
                theme_dict = self._convert_theme_to_format(record)
                if theme_dict:
                    formatted_themes.append(theme_dict)
            
            logger.info(f"   格式化完成: {len(formatted_themes)} 个有效题材")
            return formatted_themes
                
        except Exception as e:
            logger.error(f"   加载题材失败: {e}")
            return []
    
    async def _load_all_categories(self) -> List[Dict]:
        """加载所有分类数据 - 保持原有结构"""
        try:
            categories = []
            
            if hasattr(self.gateway, 'load_all_categories'):
                categories = await self.gateway.load_all_categories()
            elif hasattr(self.gateway, 'base_gateway'):
                base_gateway = self.gateway.base_gateway
                if hasattr(base_gateway, 'load_categories'):
                    categories = await base_gateway.load_categories()
                elif hasattr(base_gateway, 'load_all_categories'):
                    categories = await base_gateway.load_all_categories()
            
            if not categories:
                logger.warning("   ⚠️  无法加载分类数据")
                return []
            
            logger.info(f"   加载 {len(categories)} 个分类")
            return categories
                
        except Exception as e:
            logger.error(f"   加载分类失败: {e}")
            return []
    
    def _convert_theme_to_format(self, theme_record) -> Dict:
        """将ThemeRecord转换为字典格式 - 保持原有结构"""
        try:
            if hasattr(theme_record, 'to_dict'):
                theme_dict = theme_record.to_dict()
            elif hasattr(theme_record, '__dict__'):
                theme_dict = theme_record.__dict__
            else:
                theme_dict = theme_record
            
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
            return {
                'id': str(getattr(theme_record, 'id', '0')),
                'code': getattr(theme_record, 'code', 'UNKNOWN'),
                'name': getattr(theme_record, 'name', '未知主题'),
                'theme_type': 'unknown',
                'heat_score': 0,
                'tags': {'keywords': []}
            }
    
    def _get_mock_categories(self) -> List[Dict]:
        """获取模拟分类数据 - 保持原有结构"""
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
            }
        ]
    
    # ==================== 核心处理方法（保持原有方法签名） ====================
    
    async def _process_message(self, stream_type: str, stream_name: str, 
                               message_id: str, message_data: Dict):
        """处理单个消息 - 保持原有方法签名"""
        if self.enable_classification_first:
            return await self._process_message_classification_first(
                stream_type, stream_name, message_id, message_data
            )
        else:
            return await self._process_message_traditional(
                stream_type, stream_name, message_id, message_data
            )
    
    async def _process_message_classification_first(self, stream_type: str, stream_name: str, 
                                                    message_id: str, message_data: Dict):
        """
        分类优先模式的消息处理 - 优化内部实现
        保持原有方法签名和基本流程
        """
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
            
            # 2. 第一阶段：分类推断
            category_result = await self._infer_category_with_cache(event_id, event_data)
            self.classification_stats["category_inferences"] += 1
            
            # 3. 根据分类结果处理
            if category_result.get('matched', False):
                self.classification_stats["category_matched"] += 1
                
                # 获取分类信息
                category_info = category_result.get('category_info', {})
                category_confidence = category_result.get('confidence', 0)
                
                logger.info(f"   ✅ 分类匹配成功: {category_info.get('level1_category', 'N/A')} "
                          f"(置信度: {category_confidence:.2f})")
                
                # 检查是否达到分类匹配阈值
                if category_confidence >= self.classification_config["category_match_threshold"]:
                    # 第二阶段：分类内匹配
                    decision = await self._process_stage_two_match(
                        stream_type, event_data, category_info, category_confidence, message_id
                    )
                else:
                    # 分类置信度不足
                    decision = self._build_decision(
                        decision_type=DecisionType.CATEGORY_CONFIDENCE_TOO_LOW,
                        event_data=event_data,
                        stream_type=stream_type,
                        category_info=category_info,
                        confidence=category_confidence,
                        reason=f"分类置信度不足 ({category_confidence:.2f} < {self.classification_config['category_match_threshold']})"
                    )
                    logger.info(f"   ⚠️  分类置信度不足")
            else:
                # 第一阶段失败：分类未匹配
                self.classification_stats["category_not_matched"] += 1
                decision = await self._process_stage_one_failed(
                    stream_type, event_data, category_result, message_id
                )
                logger.info(f"   ⚠️  分类未匹配")
            
            # 4. 发布决策
            await self._publish_decision(decision)
            
            # 5. ACK消息
            await self._ack_message(stream_name, message_id)
            
            # 6. 更新统计
            self._update_processing_stats(stream_type, decision.get("decision_type"))
            
            # 7. 更新处理时间
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
            
            # 构建错误决策
            error_decision = self._build_error_decision(
                stream_type, 
                event_data if 'event_data' in locals() else {"event_id": f"error_{message_id}"},
                str(e),
                message_id
            )
            await self._publish_decision(error_decision)
            
            # 将失败消息移动到死信队列
            await self._move_to_dead_letter(stream_type, message_id, message_data, str(e))
    
    async def _infer_category_with_cache(self, event_id: str, event_data: Dict) -> Dict:
        """分类推断（带缓存）"""
        # 检查缓存
        cached_category = self.category_match_cache.get(event_id)
        if cached_category and self.classification_config["enable_category_cache"]:
            logger.debug(f"   使用缓存的分类结果: {event_id}")
            self.classification_stats["category_cache_hits"] += 1
            return cached_category
        
        # 调用ThemeService进行分类推断
        if hasattr(self.theme_service, 'discover_category_only'):
            category_result = await self.theme_service.discover_category_only(event_data)
            
            # 缓存结果
            if self.classification_config["enable_category_cache"]:
                self.category_match_cache[event_id] = category_result
                self.classification_stats["category_cache_misses"] += 1
            
            return category_result
        else:
            # 降级处理
            return {'matched': False, 'confidence': 0}
    
    async def _process_stage_two_match(self, stream_type: str, event_data: Dict, 
                                     category_info: Dict, category_confidence: float, 
                                     message_id: str) -> Dict:
        """第二阶段：分类内匹配 - 使用ThemeService封装的方法"""
        try:
            # 1. 按分类加载题材数据
            themes_in_category = await self._load_themes_by_category(category_info)
            
            if not themes_in_category:
                # 分类下没有题材
                return self._build_decision(
                    decision_type=DecisionType.CATEGORY_NO_THEMES,
                    event_data=event_data,
                    stream_type=stream_type,
                    category_info=category_info,
                    confidence=category_confidence,
                    reason="分类下没有题材数据"
                )
            
            # 2. 🔥 关键修复：使用ThemeService的discover_with_themes方法
            #    而不是自己创建KeywordMatcher
            logger.info(f"   使用ThemeService.discover_with_themes进行匹配")
            
            if hasattr(self.theme_service, 'discover_with_themes'):
                # 使用ThemeService封装的方法
                match_result = await self.theme_service.discover_with_themes(
                    event_data, 
                    themes_in_category
                )
                
                # 处理ThemeService返回的格式
                if isinstance(match_result, dict):
                    # 判断是否是ThemeService的标准响应格式
                    if 'status' in match_result and match_result['status'] == 'success':
                        # 提取匹配结果
                        service_match_result = {
                            'matched': match_result.get('matched', False),
                            'themes': match_result.get('themes', []),
                            'confidence': match_result.get('confidence', 0),
                            'theme_count': match_result.get('theme_count', 0)
                        }
                    else:
                        # 直接使用返回的结果
                        service_match_result = match_result
                else:
                    # 输出报警
                    logger.info(f"   ⚠️  不是ThemeService的标准响应格式！")
                    #service_match_result = await self._match_in_themes(themes_in_category, event_data, stream_type)
            else:
                # 如果ThemeService不支持discover_with_themes，回退到原有方法
                logger.warning("   ⚠️  ThemeService不支持discover_with_themes方法！")
                #service_match_result = await self._match_in_themes(themes_in_category, event_data, stream_type)
            
            # 3. 根据匹配结果构建决策
            if service_match_result.get('matched', False):
                # 匹配成功
                return self._build_decision(
                    decision_type=DecisionType.MATCH_SUCCESS_IN_CATEGORY,
                    event_data=event_data,
                    stream_type=stream_type,
                    category_info=category_info,
                    match_result=service_match_result,
                    confidence=service_match_result.get('confidence', category_confidence),
                    themes_in_category_count=len(themes_in_category)
                )
            else:
                # 分类内未匹配
                return self._build_decision(
                    decision_type=DecisionType.NO_MATCH_IN_CATEGORY,
                    event_data=event_data,
                    stream_type=stream_type,
                    category_info=category_info,
                    match_result=service_match_result,
                    confidence=category_confidence,
                    reason="在分类内未匹配到题材",
                    themes_in_category_count=len(themes_in_category)
                )
                
        except Exception as e:
            logger.error(f"第二阶段匹配失败: {e}")
            return self._build_decision(
                decision_type=DecisionType.ERROR_PROCESSING,
                event_data=event_data,
                stream_type=stream_type,
                category_info=category_info,
                confidence=category_confidence,
                reason=f"第二阶段匹配异常: {str(e)}"
            )
    
    async def _process_stage_one_failed(self, stream_type: str, event_data: Dict, 
                                    category_result: Dict, message_id: str) -> Dict:
        """第一阶段失败：分类未匹配 - 修复版"""
        
        if not self.classification_config["fallback_to_full_match"]:
            return self._build_decision(
                decision_type=DecisionType.CATEGORY_NO_MATCH,
                event_data=event_data,
                stream_type=stream_type,
                category_info=category_result,
                confidence=category_result.get('confidence', 0),
                reason="分类未匹配且未启用回退"
            )
        
        logger.info(f"   🔄 分类未匹配，回退到全量匹配")
        
        try:
            # 🔥 关键问题：在分类优先模式下，ThemeService.discover_theme()只有分类数据
            # 我们需要确保全量匹配有题材数据
            
            if self.enable_classification_first:
                logger.info(f"   📥 分类优先模式：需要为全量匹配准备题材数据")
                
                # 动态加载题材数据
                all_themes = await self._load_all_themes(limit=300)
                
                if not all_themes:
                    logger.error(f"   ❌ 无法加载题材数据")
                    # 无法进行全量匹配，直接走未匹配流程
                    return self._build_decision(
                        decision_type=DecisionType.NO_MATCH_AFTER_FALLBACK,
                        event_data=event_data,
                        stream_type=stream_type,
                        match_result={'matched': False},
                        confidence=0,
                        reason="无法加载题材数据进行全量匹配"
                    )
                
                logger.info(f"   ✅ 动态加载了 {len(all_themes)} 个题材")
                
                # 🔥 核心修复：使用ThemeService.discover_with_themes进行全量匹配
                if hasattr(self.theme_service, 'discover_with_themes'):
                    logger.info(f"   🎯 调用ThemeService.discover_with_themes进行全量匹配")
                    
                    try:
                        # 通过ThemeService统一接口进行全量匹配
                        full_match_result = await self.theme_service.discover_with_themes(
                            event_data, 
                            all_themes
                        )
                        
                        # 解析结果
                        if isinstance(full_match_result, dict):
                            # 标准格式处理
                            if 'status' in full_match_result and full_match_result['status'] == 'success':
                                match_data = {
                                    'matched': full_match_result.get('matched', False),
                                    'themes': full_match_result.get('themes', []),
                                    'confidence': full_match_result.get('confidence', 0),
                                    'theme_count': full_match_result.get('theme_count', 0)
                                }
                            else:
                                # 直接使用返回的匹配结果
                                match_data = full_match_result
                            
                            if match_data.get('matched', False):
                                return self._build_decision(
                                    decision_type=DecisionType.MATCH_SUCCESS_FALLBACK,
                                    event_data=event_data,
                                    stream_type=stream_type,
                                    match_result=match_data,
                                    confidence=match_data.get('confidence', 0),
                                    source="theme_service_full_match"
                                )
                        else:
                            logger.error(f"   ❌ discover_with_themes返回格式错误: {type(full_match_result)}")
                            
                    except Exception as e:
                        logger.error(f"   discover_with_themes调用失败: {e}")
                else:
                    logger.error(f"   ❌ ThemeService没有discover_with_themes方法")
                
                # 如果discover_with_themes不可用，尝试discover_theme
                logger.info(f"   🔄 尝试ThemeService.discover_theme")
            
            # 正常调用discover_theme（可能是传统模式，或者discover_with_themes不可用）
            result = await self.theme_service.discover_theme(
                event_data,
                min_confidence=0.5 if stream_type == "normal" else 0.7,
                external_unmatched_pool=self.external_unmatched_pool if self.enable_clustering else None
            )
            
            # 解析结果
            if isinstance(result, dict):
                response_data = result.get("response", {})
            else:
                response_data = result
            
            if response_data.get('matched', False):
                # 全量匹配成功
                return self._build_decision(
                    decision_type=DecisionType.MATCH_SUCCESS_FALLBACK,
                    event_data=event_data,
                    stream_type=stream_type,
                    match_result=response_data,
                    confidence=response_data.get('confidence', 0),
                    source="fallback_match"
                )
            else:
                # 全量匹配也失败
                return self._build_decision(
                    decision_type=DecisionType.NO_MATCH_AFTER_FALLBACK,
                    event_data=event_data,
                    stream_type=stream_type,
                    match_result=response_data,
                    confidence=response_data.get('confidence', 0),
                    reason="全量匹配后仍未匹配到题材"
                )
                    
        except Exception as e:
            logger.error(f"回退匹配失败: {e}")
            return self._build_decision(
                decision_type=DecisionType.ERROR_PROCESSING,
                event_data=event_data,
                stream_type=stream_type,
                confidence=0,
                reason=f"回退匹配异常: {str(e)}"
            )
    
    async def _process_message_traditional(self, stream_type: str, stream_name: str, 
                                           message_id: str, message_data: Dict):
        """传统模式的消息处理 - 简化版"""
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
            
            # 构建决策
            response = result.get("response", {}) if isinstance(result, dict) else result
            
            if response.get("matched", False):
                decision_type = DecisionType.MATCH_SUCCESS_FALLBACK
                self.stats["by_outcome"]["matched"] += 1
            else:
                decision_type = DecisionType.NO_MATCH_AFTER_FALLBACK
                self.stats["by_outcome"]["pending"] += 1
            
            decision = self._build_decision(
                decision_type=decision_type,
                event_data=event_data,
                stream_type=stream_type,
                match_result=response,
                confidence=response.get('confidence', 0),
                source="traditional_match"
            )
            
            # 发布决策
            await self._publish_decision(decision)
            
            # ACK消息
            await self._ack_message(stream_name, message_id)
            
            # 更新统计
            self.stats["total_processed"] += 1
            self.stats["by_stream"][stream_type] += 1
            
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
    
    # ==================== 决策构建方法（新增） ====================
    
    def _build_decision(self, decision_type: str, **kwargs) -> Dict:
        """构建统一格式的决策 - 修复版"""
        try:
            event_data = kwargs.get('event_data', {})
            stream_type = kwargs.get('stream_type', 'normal')
            
            logger.info(f"🔧 构建决策: {decision_type}, 事件类型: {stream_type}")
            logger.info(f"    事件ID: {event_data.get('event_id')}")
            
            # 1. 确定action类型
            action = self._get_action_for_decision_type(decision_type, stream_type)
            
            logger.info(f"    确定动作: {action}")
            
            # 2. 构建基础决策
            import time
            
            decision = {
                "decision_id": f"decision_{int(time.time())}_{hash(str(kwargs))}",
                "decision_type": decision_type,
                "action": action,
                "event_id": event_data.get("event_id", "unknown"),
                "event_type": stream_type,
                "event_title": event_data.get('title', '')[:100],
                "timestamp": datetime.now().isoformat(),
                "processor": self.consumer_name,
                "event_data": event_data,
                "ai_analysis": event_data.get("ai_analysis", {}),
                "category_info": kwargs.get('category_info'),
                "match_result": kwargs.get('match_result'),
                "confidence": kwargs.get('confidence', 0),
                "reason": kwargs.get('reason', ''),
                "themes_in_category_count": kwargs.get('themes_in_category_count', 0),
                "source": kwargs.get('source', 'classification_first')
            }
            
            # 3. 🔥 关键修复：为create_new_theme获取完整数据
            if action == "create_new_theme":
                logger.info(f"    🚨 创建新题材决策，调用ThemeService...")
                
                try:
                    # 检查ThemeService是否存在
                    if not hasattr(self, 'theme_service') or not self.theme_service:
                        raise ValueError("ThemeService不存在或未初始化")
                    
                    # 检查是否有create_new_theme_by_rules方法
                    if not hasattr(self.theme_service, 'create_new_theme_by_rules'):
                        logger.error(f"    ❌ ThemeService没有create_new_theme_by_rules方法！")
                        raise ValueError(f"ThemeService缺少create_new_theme_by_rules方法")
                    
                    # 🔥 调用ThemeService的create_new_theme_by_rules方法
                    logger.info(f"    📞 调用theme_service.create_new_theme_by_rules()")
                    complete_theme_data = self.theme_service.create_new_theme_by_rules(event_data)
                    
                    if complete_theme_data is None:
                        logger.error(f"    ❌❌❌ ThemeService.create_new_theme_by_rules返回None！")
                        raise ValueError("ThemeService.create_new_theme_by_rules返回None")
                    
                    # 🔥 检查返回的数据结构
                    logger.info(f"    📊 ThemeService返回数据类型: {type(complete_theme_data)}")
                    
                    # 检查是否包含必要的字段
                    if isinstance(complete_theme_data, dict):
                        logger.info(f"    📊 返回字段: {list(complete_theme_data.keys())}")
                        
                        # 确保有theme_data字段
                        if 'theme_data' not in complete_theme_data:
                            logger.error(f"    ❌ complete_theme_data缺少theme_data字段")
                            raise ValueError("complete_theme_data缺少theme_data字段")
                        
                        theme_data = complete_theme_data['theme_data']
                        logger.info(f"    📊 theme_data字段: {list(theme_data.keys())}")
                        logger.info(f"    📊 题材名称: {theme_data.get('name')}")
                        logger.info(f"    📊 题材代码: {theme_data.get('code')}")
                    
                    # 🔥 关键：确保complete_theme_data包含operations字段
                    # DecisionExecutor需要这个字段来知道执行什么操作
                    if 'operations' not in complete_theme_data:
                        logger.info(f"    📋 添加operations字段到complete_theme_data")
                        
                        # 根据category_info确定操作序列
                        category_info = kwargs.get('category_info', {})
                        need_create_category = category_info.get('need_create_category', True)
                        
                        operations = []
                        if need_create_category:
                            operations.append('create_category')
                        
                        operations.extend(['create_theme', 'create_mapping', 'publish_update'])
                        complete_theme_data['operations'] = operations
                    
                    # 🔥 添加完整数据到决策
                    decision['complete_theme_data'] = complete_theme_data
                    
                    # 🔥 同时添加theme_data到顶层，兼容旧版本
                    if 'theme_data' in complete_theme_data:
                        decision['theme_data'] = complete_theme_data['theme_data']
                        logger.info(f"    ✅ 已将theme_data添加到决策顶层")
                    
                    # 🔥 关键修复：从complete_theme_data复制operations到顶层
                    if 'operations' in complete_theme_data:
                        decision['operations'] = complete_theme_data['operations']
                        logger.info(f"    ✅ 已从complete_theme_data复制operations: {complete_theme_data['operations']}")
                    
                    # 记录成功信息
                    if 'theme_data' in complete_theme_data:
                        theme_name = complete_theme_data['theme_data'].get('name', '未知题材')
                        logger.info(f"    ✅ ThemeService数据已添加: {theme_name}")
                    else:
                        logger.info(f"    ✅ ThemeService数据已添加")
                    
                except Exception as e:
                    logger.error(f"    ❌❌❌ ThemeService调用失败: {e}")
                    # ❌ 绝不降级：直接抛出异常，让上层处理
                    raise RuntimeError(f"ThemeService数据生成失败: {e}")
            
            # 4. 🔥 修复：为update_theme决策准备数据（支持best_match和向后兼容）
            elif action == "update_theme":
                match_result = kwargs.get('match_result', {})
                logger.info(f"    📊 match_result类型: {type(match_result)}")
                
                if match_result:
                    logger.info(f"    📊 match_result keys: {list(match_result.keys())}")
                    logger.info(f"    📊 matched: {match_result.get('matched')}")
                    logger.info(f"    📊 theme_count: {match_result.get('theme_count')}")
                    
                    # 🔥 修复1：优先从best_match提取（新格式）
                    if 'best_match' in match_result:
                        best_match = match_result.get('best_match', {})
                        logger.info(f"    ✅ 使用best_match格式")
                        logger.info(f"    📊 best_match keys: {list(best_match.keys()) if isinstance(best_match, dict) else 'N/A'}")
                        
                        theme_id = None
                        theme_name = ""
                        
                        if isinstance(best_match, dict):
                            theme_id = best_match.get('theme_id') or best_match.get('id')
                            theme_name = best_match.get('theme_name', '') or best_match.get('name', '')
                        elif hasattr(best_match, 'theme_id'):
                            theme_id = best_match.theme_id
                            theme_name = getattr(best_match, 'theme_name', '')
                        
                        if theme_id:
                            decision['theme_data'] = {
                                'id': theme_id,
                                'name': theme_name,
                                'match_confidence': best_match.get('confidence', 0) if isinstance(best_match, dict) else getattr(best_match, 'confidence', 0),
                                'heat_increment': 1
                            }
                            logger.info(f"    ✅ 从best_match提取: {theme_name} (ID: {theme_id})")
                        else:
                            logger.warning(f"    ⚠️  best_match中没有找到theme_id")
                    
                    # 🔥 修复2：如果没有best_match，从themes列表提取（向后兼容）
                    if 'theme_data' not in decision and 'themes' in match_result:
                        matched_themes = match_result.get('themes', [])
                        theme_count = len(matched_themes)
                        
                        if theme_count > 0:
                            logger.info(f"    ⚠️  使用themes列表向后兼容，数量: {theme_count}")
                            
                            # 提取第一个匹配（最佳匹配）
                            first_theme = matched_themes[0]
                            logger.info(f"    📊 first_theme类型: {type(first_theme)}")
                            
                            theme_id = None
                            theme_name = ""
                            
                            # 情况2A：如果是MatchResult对象
                            if hasattr(first_theme, 'theme_id'):
                                theme_id = first_theme.theme_id
                                theme_name = getattr(first_theme, 'theme_name', '')
                                logger.info(f"    ✅ 从MatchResult对象提取: {theme_name} (ID: {theme_id})")
                            # 情况2B：如果是字典
                            elif isinstance(first_theme, dict):
                                theme_id = first_theme.get('theme_id') or first_theme.get('id')
                                theme_name = first_theme.get('theme_name', '') or first_theme.get('name', '')
                                logger.info(f"    ✅ 从字典提取: {theme_name} (ID: {theme_id})")
                            # 情况2C：其他类型
                            else:
                                logger.warning(f"    ❌ 未知的theme类型: {type(first_theme)}")
                            
                            if theme_id:
                                decision['theme_data'] = {
                                    'id': theme_id,
                                    'name': theme_name,
                                    'heat_increment': 1,
                                    'source_format': 'themes_list'
                                }
                            else:
                                logger.warning(f"    ⚠️  无法从themes列表提取theme_id")
                    
                    # 🔥 修复3：如果提取成功，添加operations
                    if 'theme_data' in decision:
                        theme_name = decision['theme_data'].get('name', '未知题材')
                        theme_id = decision['theme_data'].get('id')
                        
                        logger.info(f"    📊 更新题材热度: {theme_name}")
                        logger.info(f"    📊 题材ID: {theme_id}")
                        
                        operations = ['update_theme_heat', 'create_mapping', 'publish_update']
                        decision['operations'] = operations
                        logger.info(f"    ✅ update_theme operations: {operations}")
                        
                        # 添加匹配统计信息
                        decision['match_summary'] = {
                            'total_matches': match_result.get('theme_count', 0),
                            'all_matches_count': match_result.get('theme_count', 0),
                            'strategy': 'best_match_only'
                        }
                    else:
                        # 如果两种方式都失败，记录详细错误信息
                        logger.error(f"    ❌❌❌ update_theme决策无法提取theme_id")
                        logger.error(f"        match_result内容: {match_result}")
                        
                        # 仍然构建决策，但标记错误
                        decision['theme_data'] = {
                            'error': 'missing_theme_id_in_match_result',
                            'match_result_keys': list(match_result.keys()) if isinstance(match_result, dict) else 'N/A'
                        }
                        
                        operations = ['update_theme_heat', 'create_mapping', 'publish_update']
                        decision['operations'] = operations
                else:
                    logger.error(f"    ❌ update_theme缺少match_result参数")
            
            # 5. 为publish_clustering决策添加operations
            elif action == "publish_clustering":
                operations = ['publish_to_pending']
                decision['operations'] = operations
                logger.info(f"    ✅ publish_clustering operations: {operations}")
            
            # 6. 🔥 修复：确保所有决策都有operations字段（最后的保障）
            if 'operations' not in decision:
                logger.warning(f"    ⚠️  决策缺少operations字段，添加默认值")
                decision['operations'] = ['skip_and_log']
            else:
                logger.info(f"    ✅ 决策已包含operations: {decision['operations']}")
            
            # 7. 设置优先级和超时
            if stream_type == "major":
                decision["priority"] = "high"
                decision["timeout"] = 30
            else:
                decision["priority"] = "medium"
                decision["timeout"] = 60
            
            # 🔥 调试：最终决策结构
            logger.info(f"    ✅ 决策构建完成: {decision_type} -> {action}")
            logger.info(f"    📊 决策包含字段: {list(decision.keys())}")
            if 'theme_data' in decision:
                logger.info(f"    📊 决策中包含theme_data: 是")
            if 'complete_theme_data' in decision:
                logger.info(f"    📊 决策中包含complete_theme_data: 是")
            logger.info(f"    📋 操作序列: {decision.get('operations', [])}")
            
            return decision
            
        except Exception as e:
            logger.error(f"❌ 构建决策失败: {e}")
            # 构建错误决策（但不是降级处理）
            error_decision = self._build_error_decision(
                kwargs.get('stream_type', 'normal'),
                kwargs.get('event_data', {}),
                str(e),
                kwargs.get('message_id', 'unknown')
            )
            return error_decision

    def _get_action_for_decision_type_legacy(self, decision_type: str, stream_type: str) -> str:
        """根据决策类型获取动作 - 修复版"""
        # 注意：decision_type是字符串常量，不是DecisionType类的属性
        
        # 🔥 修复：正确的NO_MATCH类型字符串
        NO_MATCH_TYPES = [
            "category_no_match",                    # 分类未匹配
            "category_confidence_too_low",          # 分类置信度不足  
            "category_no_themes",                   # 分类下无题材
            "no_match_in_category",                 # 分类内未匹配
            "no_match_after_fallback"               # 回退后仍无匹配
        ]
        
        ERROR_TYPES = [
            "error_processing"                      # 处理错误
        ]
        
        # 1. 如果是NO_MATCH类型
        if any(no_match_type == decision_type for no_match_type in NO_MATCH_TYPES):
            if stream_type == "major":
                logger.info(f"   🔥 major事件未匹配分类，直接创建新题材: {decision_type}")
                return "create_new_theme"
            else:
                logger.info(f"   📤 normal事件未匹配分类，进入聚类队列: {decision_type}")
                return "publish_clustering"
        
        # 2. 错误处理
        elif any(error_type == decision_type for error_type in ERROR_TYPES):
            return "publish_clustering"
        
        # 3. 匹配成功的情况
        elif "success" in decision_type.lower():
            return "update_theme"
        
        # 4. 默认动作
        logger.warning(f"⚠️ 未知决策类型: {decision_type}, 默认进入聚类队列")
        return "publish_clustering"
    
    def _get_action_for_decision_type(self, decision_type: str, stream_type: str) -> str:
        """根据决策类型获取动作 - 确保与DecisionExecutor兼容"""
        # DecisionExecutor支持的操作类型（只有这4种！）
        # create_new_theme, update_theme, publish_clustering, clustering_result
        
        # 🔥 修复：首先识别NO_MATCH类型
        NO_MATCH_TYPES = [
            DecisionType.CATEGORY_NO_MATCH,
            DecisionType.CATEGORY_CONFIDENCE_TOO_LOW,
            DecisionType.CATEGORY_NO_THEMES,
            DecisionType.NO_MATCH_IN_CATEGORY,
            DecisionType.NO_MATCH_AFTER_FALLBACK
        ]
        
        ERROR_TYPES = [
            DecisionType.ERROR_PROCESSING
        ]
        
        # 1. 如果是NO_MATCH类型，major事件应该创建新题材
        if decision_type in NO_MATCH_TYPES:
            if stream_type == "major":
                logger.info(f"   🔥 major事件未匹配分类，直接创建新题材: {decision_type}")
                return "create_new_theme"
            else:
                logger.info(f"   📤 normal事件未匹配分类，进入聚类队列: {decision_type}")
                return "publish_clustering"
        
        # 2. 错误处理
        elif decision_type in ERROR_TYPES:
            return "publish_clustering"
        
        # 3. 匹配成功的情况
        elif decision_type == DecisionType.MATCH_SUCCESS_IN_CATEGORY:
            return "update_theme"
        elif decision_type == DecisionType.MATCH_SUCCESS_FALLBACK:
            return "update_theme"
        
        # 4. 分类有匹配但无题材的情况
        elif decision_type == DecisionType.CATEGORY_NO_THEMES:
            if stream_type == "major":
                return "create_new_theme"
            else:
                return "publish_clustering"
        
        # 5. 默认
        else:
            logger.warning(f"⚠️ 未知决策类型: {decision_type}, 默认进入聚类队列")
            return "publish_clustering"
        
    
    def _build_error_decision(self, stream_type: str, event_data: Dict, 
                            error_msg: str, message_id: str) -> Dict:
        """构建错误决策"""
        return self._build_decision(
            decision_type=DecisionType.ERROR_PROCESSING,
            event_data=event_data,
            stream_type=stream_type,
            confidence=0,
            reason=f"处理错误: {error_msg}",
            source="error_handler"
        )
    
    # ==================== 核心匹配方法（保持原有结构） ====================
    
    async def _load_themes_by_category(self, category_info: Dict) -> List[Dict]:
        """按分类加载题材 - 保持原有结构"""
        try:
            logger.info(f"🔍 [分类加载] 改进版")
        
            # 提取信息
            category_code = category_info.get('category_code')
            
            if not category_code:
                logger.error(f"❌ 分类代码为空")
                return []
            
            # 🔥 使用推断方法
            category_level = self._infer_category_level(category_info)
            
            logger.info(f"   分类代码: {category_code}")
            logger.info(f"   分类级别: {category_level}")
            logger.info(f"   分类名称: {category_info.get('category_name', 'N/A')}")
            
            if not hasattr(self.gateway, 'get_themes_by_category'):
                logger.error(f"  ❌ gateway没有get_themes_by_category方法")
                return []
            
            theme_records = await self.gateway.get_themes_by_category(
                category_code, category_level, 
                limit=self.classification_config["max_themes_per_category"]
            )
            
            logger.info(f"  📊 获取到 {len(theme_records)} 个 ThemeRecord")
            
            if not theme_records:
                return []
            
            formatted_themes = []
            for theme_record in theme_records:
                theme_dict = self._convert_theme_to_format(theme_record)
                if theme_dict:
                    formatted_themes.append(theme_dict)
            
            self.classification_stats["themes_loaded_by_category"] += len(formatted_themes)
            logger.info(f"  ✅ 转换完成: {len(formatted_themes)} 个字典格式的题材")
            
            return formatted_themes
            
        except Exception as e:
            logger.error(f"   按分类加载题材失败: {e}")
            return []
    
    def _infer_category_level(self, category_info: Dict) -> int:
        """推断分类级别"""
        level = None
        
        # 1. 直接获取
        if 'category_level' in category_info:
            level = category_info['category_level']
            if level in [1, 2]:
                return level
            elif level is not None:
                logger.warning(f"⚠️  category_level值异常: {level}")
        
        # 2. 通过parent_code判断
        if 'parent_code' in category_info and category_info['parent_code']:
            logger.info(f"   根据parent_code推断为二级分类")
            level = 2
            return level
        
        # 3. 通过字段组合判断
        has_level1 = 'level1_category' in category_info
        has_level2 = 'level2_category' in category_info
        
        if has_level1 and has_level2:
            logger.info(f"   同时有level1和level2字段，推断为二级分类")
            return 2
        elif has_level1 and not has_level2:
            logger.info(f"   只有level1字段，推断为一级分类")
            level = 1
            return level
        
        # 4. 通过分类代码格式判断
        category_code = category_info.get('category_code')
        if category_code and len(category_code) == 6:
            last_two = category_code[-2:]
            if last_two == '00':
                logger.info(f"   分类代码以00结尾，推断为一级分类: {category_code}")
                level = 1
                return level
            else:
                logger.info(f"   分类代码不以00结尾，推断为二级分类: {category_code}")
                level = 2
                return level
        
        # 5. 默认处理
        logger.warning(f"⚠️  无法推断分类级别，默认使用2")
        return level  # level = None
    
    async def _match_in_themes(self, themes: List[Dict], event_data: Dict, 
                               stream_type: str) -> Dict:
        """在指定的题材列表中匹配事件 - 保持原有结构"""
        try:
            if not themes:
                return {'matched': False, 'themes': [], 'confidence': 0.0}
            
            # 使用KeywordMatcher
            from theme_service.matchers.keyword_matcher import KeywordMatcher
            from database_service.streams.handlers.test_keyword_matcher_config import TEST_CONFIG
            
            config = TEST_CONFIG.copy()
            if stream_type == 'major':
                config['match_threshold'] = 0.3
            else:
                config['match_threshold'] = 0.2
            
            matcher = KeywordMatcher(config)
            
            try:
                matcher.initialize(themes, categories=[])
            except Exception as init_error:
                logger.error(f"  ❌ matcher初始化失败: {init_error}")
                return {'matched': False, 'themes': [], 'confidence': 0.0}
            
            matches = matcher.match(event_data)
            matched_themes = []
            
            if isinstance(matches, list) and matches:
                for match in matches[:5]:
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
            
            return {
                'matched': len(matched_themes) > 0,
                'themes': matched_themes,
                'confidence': matched_themes[0]['confidence'] if matched_themes else 0.0,
                'theme_count': len(matched_themes)
            }
                
        except Exception as e:
            logger.error(f"  在题材列表中匹配失败: {e}")
            return {'matched': False, 'themes': [], 'confidence': 0.0}
    
    # ==================== 辅助方法（保持原有结构） ====================
    
    def _extract_event_data(self, message_data: Dict, stream_type: str) -> Optional[Dict]:
        """提取事件数据 - 保持原有结构"""
        try:
            event_data_str = None
            
            if isinstance(message_data, dict):
                for field in ["event_data", "data", "payload"]:
                    if field in message_data:
                        event_data_str = message_data[field]
                        break
            elif isinstance(message_data, str):
                event_data_str = message_data
            
            if event_data_str and isinstance(event_data_str, str):
                try:
                    data = json.loads(event_data_str)
                except json.JSONDecodeError:
                    data = {"raw_content": event_data_str}
            elif isinstance(message_data, dict):
                data = message_data
            else:
                return None
            
            if "event_id" not in data:
                import uuid
                data["event_id"] = f"{stream_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            if "event_type" not in data:
                data["event_type"] = stream_type
            
            if "ai_analysis" not in data:
                data["ai_analysis"] = {}
            
            if isinstance(data.get("ai_analysis"), str):
                try:
                    data["ai_analysis"] = json.loads(data["ai_analysis"])
                except:
                    data["ai_analysis"] = {}
            
            return data
            
        except Exception as e:
            logger.warning(f"提取事件数据失败: {e}")
            return None
    
    async def _publish_decision(self, decision: Dict) -> Optional[str]:
        """发布决策到decision流 - 保持原有结构"""
        try:
            if 'timestamp' not in decision:
                decision['timestamp'] = datetime.now().isoformat()
            
            if 'processor' not in decision:
                decision['processor'] = self.consumer_name
            
            decision_entry = {
                "decision": json.dumps(decision, ensure_ascii=False),
                "publisher": self.consumer_name,
                "timestamp": decision['timestamp'],
                "event_id": decision.get('event_id', 'unknown')
            }
            
            message_id = await self.redis_client.xadd(
                self.output_streams["decision"],
                decision_entry,
                maxlen=10000
            )
            
            logger.info(f"📤 发布决策: {decision.get('action')} -> {message_id}")
            self.stats["database_operations"]["stream_publishes"] += 1
            
            return message_id
            
        except Exception as e:
            logger.error(f"发布决策失败: {e}")
            return None
    
    async def _ack_message(self, stream_name: str, message_id: str):
        """ACK消息"""
        try:
            await self.redis_client.xack(stream_name, self.consumer_group, message_id)
        except Exception as e:
            logger.error(f"ACK失败 {message_id}: {e}")
    
    async def _move_to_dead_letter(self, stream_type: str, message_id: str, 
                                 message_data: Dict, error: str):
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
    
    # ==================== 统计更新方法 ====================
    
    def _update_processing_stats(self, stream_type: str, decision_type: str):
        """更新处理统计"""
        self.stats["total_processed"] += 1
        self.stats["by_stream"][stream_type] += 1
        
        # 根据决策类型更新匹配结果统计
        if "success" in decision_type.lower():
            self.stats["by_outcome"]["matched"] += 1
        elif decision_type == DecisionType.ERROR_PROCESSING:
            self.stats["by_outcome"]["error"] += 1
        else:
            self.stats["by_outcome"]["pending"] += 1
    
    # ==================== 流处理方法（保持原有结构） ====================
    
    async def _create_consumer_groups(self):
        """创建Redis Stream消费者组"""
        for stream_type, stream_name in self.input_streams.items():
            try:
                await self.redis_client.xgroup_create(
                    stream_name,
                    self.consumer_group,
                    id="0",
                    mkstream=True
                )
                logger.info(f"   创建消费者组: {stream_name}/{self.consumer_group}")
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.debug(f"   消费者组已存在: {stream_name}")
                else:
                    logger.error(f"   创建消费者组失败 {stream_name}: {e}")
    
    async def _process_stream(self, stream_type: str):
        """处理单个Stream"""
        stream_name = self.input_streams[stream_type]
        config = self.processing_config[stream_type]
        
        logger.info(f"📥 开始处理 {stream_type} 流: {stream_name}")
        
        while self.running:
            try:
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
                
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                logger.info(f"📥 {stream_type}流处理被取消")
                break
            except Exception as e:
                logger.error(f"📥 {stream_type}流处理异常: {e}")
                await asyncio.sleep(5)
    
    # ==================== 公共接口方法（保持原有结构） ====================
    
    async def start(self):
        """启动处理器 - 保持原有结构"""
        if self.running:
            logger.warning("处理器已在运行")
            return self.all_tasks
        
        self.running = True
        self.stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动ThemeProcessor...")
        
        # 创建消费者组
        await self._create_consumer_groups()
        
        # 启动监听任务
        listener_tasks = [
            asyncio.create_task(self._process_stream("normal"), name="normal_processor"),
            asyncio.create_task(self._process_stream("major"), name="major_processor")
        ]
        
        self.all_tasks.extend(listener_tasks)
        
        logger.info(f"✅ 启动完成，{len(listener_tasks)}个监听任务")
        return listener_tasks
    
    async def stop(self):
        """停止处理器 - 保持原有结构"""
        if not self.running:
            return
        
        logger.info("🛑 停止ThemeProcessor...")
        self.running = False
        
        # 停止所有任务
        for task in self.all_tasks:
            if not task.done():
                task.cancel()
        
        try:
            await asyncio.gather(*self.all_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        
        # 清理资源
        await self._cleanup()
        
        # 打印统计
        self.print_stats()
        
        logger.info("✅ 处理器已停止")
    
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
    
    async def get_status(self) -> Dict:
        """获取状态信息 - 保持原有结构"""
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
    
    def print_stats(self):
        """打印统计信息 - 保持原有结构"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 ThemeProcessor统计信息")
        logger.info("=" * 60)
        logger.info(f"运行模式: {'分类优先' if self.enable_classification_first else '传统'}")
        logger.info(f"运行时间: {self.stats['started_at']}")
        logger.info(f"总处理事件: {self.stats['total_processed']}")
        logger.info(f"  Normal: {self.stats['by_stream']['normal']}")
        logger.info(f"  Major: {self.stats['by_stream']['major']}")
        logger.info(f"匹配结果:")
        logger.info(f"  匹配成功: {self.stats['by_outcome']['matched']}")
        logger.info(f"  进入pending: {self.stats['by_outcome']['pending']}")
        logger.info(f"  处理错误: {self.stats['by_outcome']['error']}")
        
        if self.enable_classification_first:
            logger.info(f"分类统计:")
            logger.info(f"  分类推断次数: {self.classification_stats['category_inferences']}")
            logger.info(f"  分类匹配成功: {self.classification_stats['category_matched']}")
            logger.info(f"  分类匹配失败: {self.classification_stats['category_not_matched']}")
            logger.info(f"  按分类加载题材数: {self.classification_stats['themes_loaded_by_category']}")
            logger.info(f"  缓存命中率: {self.classification_stats['category_cache_hits']}/"
                f"{self.classification_stats['category_cache_hits'] + self.classification_stats['category_cache_misses']}")
        
        logger.info("=" * 60)

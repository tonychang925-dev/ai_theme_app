"""
Theme Service - 独立服务，提供主题发现功能
仿照ModelService的设计模式
支持聚类分析功能，不依赖候选池（由外部服务管理）
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
import traceback

# 导入同级组件
try:
    from services.theme_discovery_engine import ThemeDiscoveryEngine
except ImportError:
    # 如果上面的导入失败，尝试相对导入作为fallback
    from .theme_discovery_engine import ThemeDiscoveryEngine

# 导入其他模块组件
from theme_service.creators.theme_data_generator import ThemeDataGenerator

logger = logging.getLogger(__name__)


class ThemeService:
    """
    Theme Service - 提供主题发现功能，支持聚类分析
    
    特性：
    1. 纯算法服务，不管理候选池
    2. 支持聚类分析
    3. 提供Major/Normal事件处理
    4. 支持批量处理
    5. 异步接口设计
    """
    
    def __init__(self, enable_clustering: bool = False):
        """
        初始化Theme Service
        
        Args:
            enable_clustering: 是否启用聚类分析功能（默认关闭，保持向后兼容）
        """
        self.discovery_engine = None
        self.theme_generator = None
        self.db_manager = None
        self.enable_clustering = enable_clustering
        self._initialized = False
        
        try:
            logger.info("🎯 ThemeService初始化开始")
            
            # 1. 初始化主题发现引擎（支持聚类分析）
            self.discovery_engine = ThemeDiscoveryEngine(enable_clustering=enable_clustering)
            logger.info("   ✅ 主题发现引擎创建成功")
            if enable_clustering:
                logger.info("   🎯 聚类分析功能已启用")
            
            # 2. 主题数据生成器将在initialize中初始化（需要数据）
            self.theme_generator = None
            
            self._initialized = True  # 初始化标志，但不表示数据已加载
            logger.info("✅ ThemeService初始化成功")
            
        except Exception as e:
            logger.error(f"❌ ThemeService初始化失败: {e}")
            self._initialized = False
        
        # 服务元数据
        self.service_metadata = {
            "service": "ThemeService",
            "version": "2.2.0",  # 版本升级
            "description": "基于分析师思维的主题发现服务",
            "features": [
                "major_normal_event_processing",
                "keyword_based_matching",
                "new_theme_generation",
                "clustering_analysis" if enable_clustering else None,
                "batch_processing"
            ],
            "clustering_enabled": enable_clustering,
            "candidate_pool_external": True,  # 标记候选池由外部管理
            "architecture": "pure_algorithm + business_logic",
            "created_at": datetime.now().isoformat(),
            "initialized": self._initialized
        }
    
    @property
    def initialized(self):
        """获取初始化状态 - 包含数据加载状态"""
        return self._initialized and self.discovery_engine is not None
    
    async def initialize(self, **kwargs) -> bool:
        """
        异步初始化服务（加载数据）
        
        Args:
            db_manager: 数据库管理器（可选）
        """
        logger.warning("⚠️ ThemeService.initialize()被调用，但没有数据")
        logger.warning("   推荐使用initialize_with_data()并提供数据")

        # 🔥 修复：检查是否存在 theme_service 属性
        if hasattr(self, 'theme_service') and self.theme_service is None:
            return {'status': 'error', 'message': 'theme_service not set'}
        
        # 如果已经初始化过，直接返回
        if self._initialized:
            return {'status': 'success', 'initialized': True}
        
        # 🔥 关键修复：确保 theme_service 存在
        if self.theme_service is None:
            logger.error("❌ theme_service 未创建，无法初始化")
            return False
        
        try:
            # 创建发现引擎
            if self.discovery_engine is None:
                self.discovery_engine = ThemeDiscoveryEngine(
                    enable_clustering=self.enable_clustering
                )
            
            # 使用空数据初始化（确保不会崩溃）
            success = self.discovery_engine.load_data([], [])
            
            if success:
                self._initialized = True
                logger.info("✅ ThemeService使用空数据初始化完成")
                return True
            else:
                logger.error("❌ ThemeService初始化失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ ThemeService初始化异常: {e}")
            return False
        
    
    async def initialize_with_categories_only(self, categories: List[Dict]) -> bool:
        """分类优先模式初始化"""
        logger.info("🔄 ThemeService分类优先初始化")
        
        # 验证分类数据
        validated_categories = self._validate_categories(categories)
        
        if not validated_categories:
            logger.error("❌ 分类数据验证失败")
            return False
        
        # 创建空题材数据
        empty_themes = []
        
        # 初始化发现引擎
        if not self.discovery_engine:
            self.discovery_engine = ThemeDiscoveryEngine(
                enable_clustering=self.enable_clustering
            )
        
        # 🔥 关键：传递数据到引擎
        # 注意：load_data需要themes和categories两个参数
        success = self.discovery_engine.load_data(empty_themes, validated_categories)
        
        if success:
            self._initialized = True
            self.data_stats = {
                'themes_count': 0,
                'categories_count': len(validated_categories),
                'initialization_mode': 'categories_only',
                'initialized_at': datetime.now().isoformat()
            }
            logger.info("✅ ThemeService分类优先初始化完成")
        else:
            logger.error("❌ 发现引擎数据加载失败")
        
        return success
    
    async def initialize_with_data(self, themes: List[Dict], categories: List[Dict]) -> bool:
        """
        使用外部提供的数据初始化 - 简化版
        """
        logger.info("🔄 ThemeService数据驱动初始化开始")
        
        try:
            # 1. 创建发现引擎
            if self.discovery_engine is None:
                self.discovery_engine = ThemeDiscoveryEngine(
                    enable_clustering=self.enable_clustering
                )
            
            # 🔥 简化：直接使用传入的数据，不进行复杂的验证
            logger.info(f"📊 接收数据: {len(themes)}题材, {len(categories)}分类")
            
            # 2. 简单的数据验证（确保不是空数据）
            if not themes:
                logger.warning("⚠️ 题材数据为空")
            
            if not categories:
                logger.warning("⚠️ 分类数据为空")
            
            # 3. 记录数据统计（简单的）
            self.data_stats = {
                "themes_count": len(themes),
                "categories_count": len(categories),
                "themes_sample": themes[:3] if themes else [],
                "categories_sample": categories[:3] if categories else [],
                "data_source": "external_provider"
            }
            
            logger.info(f"📊 数据统计: {len(themes)}题材, {len(categories)}分类")
            
            # 4. 直接加载数据到引擎
            success = self.discovery_engine.load_data(themes, categories)
            
            if success:
                self._initialized = True
                logger.info("✅ ThemeService数据驱动初始化完成")
                return True
            else:
                logger.error("❌ 引擎加载数据失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ ThemeService数据驱动初始化异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def discover_theme(self, event_data: Dict, **kwargs) -> Dict[str, Any]:
        """
        发现主题 - 主接口
        
        Args:
            event_data: 事件数据，必须包含:
                - event_id: 事件ID
                - event_type: 'major' 或 'normal'
                - title: 事件标题
                - content: 事件内容
            **kwargs: 可选参数，用于聚类分析
                - external_unmatched_pool: 外部未匹配池（聚类分析用）
                - on_unmatched_callback: 未匹配回调函数
        
        Returns:
            主题发现结果
        """
        operation = "discover_theme"
        
        try:
            event_id = event_data.get('event_id', 'unknown')
            event_type = event_data.get('event_type', 'normal')
            
            logger.info(f"🔍 主题发现开始: {event_id}, 类型: {event_type}")
            
            if not self.initialized:
                return self._create_error_response(
                    "服务未初始化", 
                    operation,
                    "请先调用 initialize() 方法"
                )
            
            # 验证必要字段
            required_fields = ['event_id', 'event_type', 'title', 'content']
            missing_fields = [field for field in required_fields if not event_data.get(field)]
            if missing_fields:
                return self._create_error_response(
                    f"缺少必要字段: {missing_fields}",
                    operation,
                    "event_data必须包含: event_id, event_type, title, content"
                )
            
            # 检查AI分析数据格式
            if 'ai_analysis' in event_data and isinstance(event_data['ai_analysis'], str):
                try:
                    import json
                    event_data['ai_analysis'] = json.loads(event_data['ai_analysis'])
                except:
                    event_data['ai_analysis'] = {}
            
            # 准备聚类分析参数
            clustering_params = {}
            if self.enable_clustering:
                # 外部未匹配池
                if 'external_unmatched_pool' in kwargs:
                    clustering_params['external_unmatched_pool'] = kwargs['external_unmatched_pool']
                
                # 回调函数
                if event_type == 'major' and 'on_major_unmatched' in kwargs:
                    clustering_params['on_major_unmatched'] = kwargs['on_major_unmatched']
                elif event_type == 'normal' and 'on_normal_unmatched' in kwargs:
                    clustering_params['on_normal_unmatched'] = kwargs['on_normal_unmatched']
            
            # 执行主题发现
            discovery_result = self.discovery_engine.discover(event_data, **clustering_params)
            
            # 构建响应
            result = {
                "operation": operation,
                "status": "success",
                "service": "ThemeService",
                "mode": "discovery",
                "request": {
                    "event_id": event_id,
                    "event_type": event_type,
                    "title_length": len(event_data.get('title', '')),
                    "content_length": len(event_data.get('content', ''))
                },
                "response": discovery_result,
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat(),
                "processing_info": {
                    "processing_path": discovery_result.get('processing_path', ''),
                    "algorithm_used": discovery_result.get('algorithm_used', ''),
                    "processing_time_ms": discovery_result.get('processing_time_ms', 0),
                    "clustering_enabled": self.enable_clustering,
                    "clustering_triggered": discovery_result.get('clustering_info', {}).get('triggered', False)
                }
            }
            
            # 处理Major事件的新题材创建建议
            if event_type == 'major' and not discovery_result.get('matched', False):
                logger.info(f"   🚨 Major事件未匹配，检查AI分析支持...")
                
                # 如果有AI分析但没有生成新题材，尝试强制创建
                ai_analysis = event_data.get('ai_analysis', {})
                if ai_analysis and not discovery_result.get('new_theme_ready', False):
                    if self.discovery_engine and hasattr(self.discovery_engine, 'force_create_theme_for_major'):
                        try:
                            force_result = self.discovery_engine.force_create_theme_for_major(event_data)
                            if force_result.get('status') == 'success':
                                # 确保获取字典形式的新题材
                                new_theme = force_result.get('new_theme')
                                if hasattr(new_theme, 'to_dict'):
                                    new_theme_dict = new_theme.to_dict()
                                elif isinstance(new_theme, dict):
                                    new_theme_dict = new_theme
                                else:
                                    new_theme_dict = {}
                                
                                result['response']['force_created_theme'] = new_theme_dict
                                result['response']['new_theme_ready'] = True
                                result['response']['creation_method'] = 'force_create'
                                logger.info(f"   🚀 强制创建题材成功")
                        except Exception as e:
                            logger.warning(f"   ⚠️  强制创建失败: {e}")
            
            # 记录结果信息
            logger.info(f"✅ 主题发现完成: {event_id}, "
                    f"匹配: {discovery_result['matched']}, "
                    f"题材数: {discovery_result['theme_count']}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 主题发现失败: {e}")
            traceback.print_exc()
            return self._create_error_response(str(e), operation)
    
    async def discover_and_create_theme(self, event_data: Dict, **kwargs) -> Dict[str, Any]:
        """
        发现主题并建议创建新题材（针对Major事件）
        
        Args:
            event_data: 事件数据（必须是Major事件）
            **kwargs: 可选参数
        
        Returns:
            包含新题材建议的结果
        """
        operation = "discover_and_create_theme"
        
        try:
            event_id = event_data.get('event_id', 'unknown')
            event_type = event_data.get('event_type', 'normal')
            
            logger.info(f"🚀 发现并创建主题: {event_id}, 类型: {event_type}")
            
            if not self.initialized:
                return self._create_error_response(
                    "服务未初始化", 
                    operation,
                    "请先调用 initialize() 方法"
                )
            
            # 检查事件类型
            if event_type != 'major':
                logger.warning(f"⚠️  非Major事件使用discover_and_create_theme: {event_type}")
            
            # 1. 先进行主题发现
            clustering_params = {}
            if self.enable_clustering:
                if 'external_unmatched_pool' in kwargs:
                    clustering_params['external_unmatched_pool'] = kwargs['external_unmatched_pool']
                if 'on_major_unmatched' in kwargs:
                    clustering_params['on_major_unmatched'] = kwargs['on_major_unmatched']
            
            discovery_result = self.discovery_engine.discover(event_data, **clustering_params)
            
            # 2. 如果是Major事件且未匹配到题材，建议创建新题材
            new_theme_data = None
            creation_reason = None
            creation_method = "normal"
            new_theme_dict = None
            
            if event_type == 'major' and not discovery_result['matched']:
                logger.info(f"   🚨 Major事件未匹配，建议创建新题材")
                
                # 检查主题生成器是否可用
                theme_generator_available = (
                    self.discovery_engine and 
                    hasattr(self.discovery_engine, 'theme_data_generator') and
                    self.discovery_engine.theme_data_generator is not None
                )
                
                if not theme_generator_available:
                    logger.warning(f"   ⚠️  主题生成器未设置到引擎")
                    
                    # 如果有独立的theme_generator，尝试设置到引擎
                    if self.theme_generator and self.discovery_engine:
                        self.discovery_engine.set_theme_data_generator(self.theme_generator)
                        logger.info(f"   ✅ 将主题生成器设置到引擎")
                        theme_generator_available = True
                
                # 优先使用AI分析创建
                ai_analysis = event_data.get('ai_analysis', {})
                if ai_analysis:
                    logger.info(f"   🤖 使用AI分析创建题材")
                    
                    # 检查引擎是否支持强制创建
                    if hasattr(self.discovery_engine, 'force_create_theme_for_major'):
                        force_result = self.discovery_engine.force_create_theme_for_major(event_data)
                        if force_result.get('status') == 'success':
                            new_theme = force_result.get('new_theme')
                            new_theme_data = new_theme
                            new_theme_dict = new_theme if isinstance(new_theme, dict) else new_theme.to_dict() if hasattr(new_theme, 'to_dict') else None
                            creation_method = "ai_force_create"
                            
                            theme_name = None
                            if isinstance(new_theme, dict):
                                theme_name = new_theme.get('name')
                            elif hasattr(new_theme, 'name'):
                                theme_name = new_theme.name
                            
                            if theme_name:
                                logger.info(f"   ✅ AI强制创建成功: {theme_name}")
                            else:
                                logger.info(f"   ✅ AI强制创建成功（名称未知）")
                    
                    # 如果AI创建失败，尝试使用生成器
                    if not new_theme_data and theme_generator_available:
                        try:
                            theme_generator = self.discovery_engine.theme_data_generator
                            if theme_generator:
                                new_theme_data = theme_generator.generate_for_major_event(
                                    event_data, discovery_result
                                )
                                
                                if new_theme_data:
                                    creation_reason = "major_event_no_match"
                                    creation_method = "generator"
                                    # 转换为字典
                                    if hasattr(new_theme_data, 'to_dict'):
                                        new_theme_dict = new_theme_data.to_dict()
                                    elif isinstance(new_theme_data, dict):
                                        new_theme_dict = new_theme_data
                                    else:
                                        new_theme_dict = {}
                                    logger.info(f"   ✅ 生成新题材建议: {getattr(new_theme_data, 'name', '未知')}")
                                else:
                                    logger.info("   ⚠️  无法生成新题材数据")
                        except Exception as e:
                            logger.error(f"   ❌ 生成器创建失败: {e}")
                else:
                    # 没有AI分析，但事件是major，仍然尝试创建
                    if theme_generator_available:
                        logger.info(f"   ⚠️  Major事件无AI分析，尝试创建基础概念")
                        try:
                            theme_generator = self.discovery_engine.theme_data_generator
                            if theme_generator:
                                new_theme_data = theme_generator.generate_for_major_event(
                                    event_data, discovery_result
                                )
                                
                                if new_theme_data:
                                    new_theme_dict = new_theme_data.to_dict() if hasattr(new_theme_data, 'to_dict') else new_theme_data.__dict__
                                    creation_method = "generator_no_ai"
                                    logger.info(f"   ✅ 创建基础概念: {getattr(new_theme_data, 'name', '未知')}")
                        except Exception as e:
                            logger.error(f"   ❌ 基础概念创建失败: {e}")
            
            # 3. 构建响应
            result = {
                "operation": operation,
                "status": "success",
                "service": "ThemeService",
                "mode": "discovery_with_creation",
                "request": {
                    "event_id": event_id,
                    "event_type": event_type
                },
                "response": {
                    "discovery_result": discovery_result,
                    "new_theme_suggestion": new_theme_dict,
                    "should_create_theme": new_theme_dict is not None,
                    "creation_method": creation_method
                },
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat(),
                "processing_info": {
                    "creation_reason": creation_reason,
                    "creation_strategy": "immediate_creation" if new_theme_dict else "none",
                    "clustering_enabled": self.enable_clustering
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 发现并创建主题失败: {e}")
            traceback.print_exc()
            return self._create_error_response(str(e), operation)
    
    async def trigger_clustering_analysis(self, unmatched_pool: List, 
                                         auto_create: bool = True,
                                         min_confidence: float = 0.7) -> Dict[str, Any]:
        """
        手动触发聚类分析
        
        Args:
            unmatched_pool: 外部未匹配池
            auto_create: 是否自动创建题材（默认True）
            min_confidence: 自动创建的最小置信度（默认0.7）
        
        Returns:
            聚类分析结果
        """
        operation = "trigger_clustering_analysis"
        
        try:
            logger.info(f"🎯 手动触发聚类分析: 未匹配池大小={len(unmatched_pool)}")
            
            if not self.initialized:
                return self._create_error_response(
                    "服务未初始化", 
                    operation,
                    "请先调用 initialize() 方法"
                )
            
            if not self.enable_clustering:
                return self._create_error_response(
                    "聚类分析未启用", 
                    operation,
                    "请在初始化时设置 enable_clustering=True"
                )
            
            if not self.discovery_engine:
                return self._create_error_response(
                    "发现引擎不可用", 
                    operation
                )
            
            # 执行聚类分析
            if hasattr(self.discovery_engine, 'trigger_clustering_analysis'):
                clustering_result = self.discovery_engine.trigger_clustering_analysis(
                    unmatched_pool, 
                    auto_create=auto_create,
                    min_confidence=min_confidence
                )
            else:
                return self._create_error_response(
                    "发现引擎不支持聚类分析", 
                    operation
                )
            
            result = {
                "operation": operation,
                "status": "success",
                "service": "ThemeService",
                "mode": "clustering_analysis",
                "request": {
                    "unmatched_pool_size": len(unmatched_pool),
                    "auto_create_enabled": auto_create,
                    "min_confidence": min_confidence
                },
                "response": clustering_result,
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat(),
                "processing_info": {
                    "clustering_method": "manual_trigger",
                    "clustering_enabled": True
                }
            }
            
            logger.info(f"✅ 聚类分析完成: "
                       f"发现 {clustering_result.get('new_candidates_found', 0)} 个候选, "
                       f"自动创建状态: {clustering_result.get('auto_creation', {}).get('status', '未知')}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 聚类分析失败: {e}")
            traceback.print_exc()
            return self._create_error_response(str(e), operation)
    
    async def batch_discover_themes(self, events_data: List[Dict], **kwargs) -> Dict[str, Any]:
        """
        批量发现主题
        
        Args:
            events_data: 事件数据列表
            **kwargs: 可选参数，用于聚类分析
        
        Returns:
            批量发现结果
        """
        operation = "batch_discover_themes"
        
        try:
            logger.info(f"📦 批量主题发现: {len(events_data)} 个事件")
            
            if not self.initialized:
                return self._create_error_response(
                    "服务未初始化", 
                    operation,
                    "请先调用 initialize() 方法"
                )
            
            # 准备聚类分析参数
            clustering_params = {}
            if self.enable_clustering:
                if 'external_unmatched_pool' in kwargs:
                    clustering_params['external_unmatched_pool'] = kwargs['external_unmatched_pool']
            
            # 处理事件
            results = []
            successful = 0
            failed = 0
            new_theme_suggestions = []
            
            for event_data in events_data:
                try:
                    # 根据事件类型选择处理方式
                    event_type = event_data.get('event_type', 'normal')
                    
                    # 准备单个事件的参数
                    single_params = clustering_params.copy()
                    if event_type == 'major' and 'on_major_unmatched' in kwargs:
                        single_params['on_major_unmatched'] = kwargs['on_major_unmatched']
                    elif event_type == 'normal' and 'on_normal_unmatched' in kwargs:
                        single_params['on_normal_unmatched'] = kwargs['on_normal_unmatched']
                    
                    # 发现主题
                    discovery_result = self.discovery_engine.discover(event_data, **single_params)
                    
                    successful += 1
                    
                    # 检查是否有新题材建议（Major事件）
                    if (event_type == 'major' and 
                        not discovery_result.get('matched', False)):
                        
                        ai_analysis = event_data.get('ai_analysis', {})
                        if ai_analysis:
                            # 尝试强制创建
                            if hasattr(self.discovery_engine, 'force_create_theme_for_major'):
                                force_result = self.discovery_engine.force_create_theme_for_major(event_data)
                                if force_result.get('status') == 'success':
                                    new_theme = force_result.get('new_theme')
                                    if new_theme:
                                        theme_dict = new_theme.to_dict() if hasattr(new_theme, 'to_dict') else new_theme
                                        new_theme_suggestions.append({
                                            "theme": theme_dict,
                                            "event_id": event_data.get('event_id'),
                                            "creation_method": "force_create"
                                        })
                    
                    results.append({
                        "event_id": event_data.get('event_id'),
                        "event_type": event_type,
                        "status": "success",
                        "matched": discovery_result.get('matched', False),
                        "theme_count": discovery_result.get('theme_count', 0),
                        "processing_path": discovery_result.get('processing_path', '')
                    })
                    
                except Exception as e:
                    failed += 1
                    results.append({
                        "event_id": event_data.get('event_id'),
                        "status": "error",
                        "error": str(e)
                    })
            
            # 构建响应
            result = {
                "operation": operation,
                "status": "success",
                "service": "ThemeService",
                "request": {
                    "batch_size": len(events_data),
                    "event_types": [e.get('event_type', 'normal') for e in events_data]
                },
                "response": {
                    "total_processed": len(events_data),
                    "successful": successful,
                    "failed": failed,
                    "success_rate": successful / max(len(events_data), 1),
                    "new_theme_suggestions_count": len(new_theme_suggestions),
                    "new_theme_suggestions": new_theme_suggestions[:10],  # 最多返回10个
                    "results": results,
                    "processed_at": datetime.now().isoformat()
                },
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat(),
                "processing_info": {
                    "clustering_enabled": self.enable_clustering,
                    "clustering_used": len(clustering_params) > 0
                }
            }
            
            logger.info(f"✅ 批量主题发现完成: {successful}成功, {failed}失败, "
                       f"新题材建议: {len(new_theme_suggestions)}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 批量主题发现失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def get_service_status(self) -> Dict[str, Any]:
        """
        获取服务状态 - 增强版，显示当前模式
        """
        operation = "get_service_status"
        
        try:
            # 获取引擎状态
            engine_status = None
            if self.discovery_engine:
                try:
                    engine_status = self.discovery_engine.get_engine_status()
                except Exception as e:
                    logger.warning(f"获取引擎状态失败: {e}")
                    engine_status = {"error": str(e)}
            
            # 确定当前模式
            current_mode = "unknown"
            if hasattr(self, 'data_stats'):
                if self.data_stats.get('themes_count', 0) == 0:
                    current_mode = "category_only_mode"
                else:
                    current_mode = "mixed_mode"
            
            # 检查各组件状态
            components = {
                "discovery_engine": {
                    "available": self.discovery_engine is not None,
                    "themes_loaded": engine_status.get('data_loaded', False) if engine_status else False,
                    "themes_count": engine_status.get('themes_count', 0) if engine_status else 0,
                    "categories_count": engine_status.get('categories_count', 0) if engine_status else 0,
                    "algorithms": engine_status.get('algorithms', {}) if engine_status else {},
                    "clustering_enabled": engine_status.get('clustering_enabled', False) if engine_status else False,
                    "engine_mode": current_mode
                },
                "theme_generator": {
                    "available": self.theme_generator is not None
                }
            }
            
            # 聚类分析状态
            clustering_info = {}
            if self.enable_clustering and engine_status and 'clustering_stats' in engine_status:
                clustering_info = {
                    "enabled": True,
                    "stats": engine_status['clustering_stats'],
                    "status": "active" if engine_status.get('clustering_enabled', False) else "inactive"
                }
            
            # 构建状态响应
            result = {
                "operation": operation,
                "status": "healthy" if self.initialized else "unhealthy",
                "service": "ThemeService",
                "initialized": self.initialized,
                "current_mode": current_mode,
                "data_stats": self.data_stats if hasattr(self, 'data_stats') else {},
                "clustering": clustering_info,
                "components": components,
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat(),
                "design_pattern": "two_phase_category_first" if current_mode == "category_only_mode" else "legacy_mixed"
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取服务状态失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查（兼容接口）"""
        return await self.get_service_status()
    
    async def auto_create_themes_from_clustering(self, min_confidence: float = 0.7) -> Dict[str, Any]:
        """
        从聚类分析结果自动创建题材
        
        Args:
            min_confidence: 最小置信度阈值（默认0.7）
        
        Returns:
            创建结果
        """
        operation = "auto_create_themes_from_clustering"
        
        try:
            logger.info(f"🤖 从聚类分析自动创建题材: 最小置信度={min_confidence}")
            
            if not self.initialized:
                return self._create_error_response(
                    "服务未初始化", 
                    operation,
                    "请先调用 initialize() 方法"
                )
            
            if not self.enable_clustering:
                return self._create_error_response(
                    "聚类分析未启用", 
                    operation,
                    "请在初始化时设置 enable_clustering=True"
                )
            
            if not self.discovery_engine:
                return self._create_error_response(
                    "发现引擎不可用", 
                    operation
                )
            
            # 执行自动创建
            if hasattr(self.discovery_engine, 'auto_create_themes_from_clustering'):
                creation_result = self.discovery_engine.auto_create_themes_from_clustering(min_confidence)
            else:
                return self._create_error_response(
                    "发现引擎不支持自动创建", 
                    operation
                )
            
            result = {
                "operation": operation,
                "status": "success",
                "service": "ThemeService",
                "mode": "clustering_auto_creation",
                "request": {
                    "min_confidence": min_confidence
                },
                "response": creation_result,
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ 自动创建完成: {creation_result.get('created_count', 0)} 个题材")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 自动创建失败: {e}")
            traceback.print_exc()
            return self._create_error_response(str(e), operation)
    
    def _get_mock_themes(self) -> List[Dict]:
        """获取模拟题材数据"""
        return [
            {
                'code': 'INVEST_SW_480301',
                'name': '投资题材：股份制银行Ⅲ',
                'level1_category': '银行',
                'level2_category': '股份制银行Ⅱ',
                'level3_category': '股份制银行Ⅲ',
                'category1_code': '480000',
                'category2_code': '480300',
                'tags': {
                    "source": "shenwan",
                    "aliases": ["股份制银行Ⅲ", "股份制银行Ⅲ板块", "股份制银行Ⅲ行业"],
                    "keywords": ["股份制银行概念", "股份制银行题材", "股份制银行"],
                    "heat_level": "medium"
                },
                'theme_type': 'investment',
                'heat_score': 66
            },
            {
                'code': 'THM_AI_730101',
                'name': '人工智能算法概念',
                'level1_category': '计算机',
                'level2_category': '软件开发',
                'level3_category': 'AI算法',
                'category1_code': '730000',
                'category2_code': '730100',
                'tags': {
                    "source": "auto_discovered",
                    "aliases": ["AI算法概念", "人工智能概念"],
                    "keywords": ["AI", "人工智能", "算法", "机器学习"],
                    "heat_level": "high"
                },
                'theme_type': 'concept',
                'heat_score': 85
            }
        ]
    
    def _get_mock_categories(self) -> List[Dict]:
        """获取模拟分类数据"""
        return [
            {
                'category_code': '480000',
                'category_name': '银行',
                'category_level': 1,
                'parent_code': None,
                'keywords': ['银行', '金融', '信贷', '存款'],
                'description': '银行业'
            },
            {
                'category_code': '480300',
                'category_name': '股份制银行Ⅱ',
                'category_level': 2,
                'parent_code': '480000',
                'keywords': ['股份制银行', '商业银行'],
                'description': '股份制银行'
            },
            {
                'category_code': '730000',
                'category_name': '计算机',
                'category_level': 1,
                'parent_code': None,
                'keywords': ['计算机', '软件', 'IT', '信息技术'],
                'description': '计算机行业'
            },
            {
                'category_code': '730100',
                'category_name': '软件开发',
                'category_level': 2,
                'parent_code': '730000',
                'keywords': ['软件', '开发', '编程', '应用'],
                'description': '软件开发'
            }
        ]
    
    def _create_error_response(
        self, 
        error_message: str, 
        operation: str = "unknown",
        details: str = None
    ) -> Dict[str, Any]:
        """创建错误响应"""
        response = {
            "operation": operation,
            "status": "error",
            "error": error_message,
            "service": "ThemeService",
            "metadata": self.service_metadata,
            "timestamp": datetime.now().isoformat()
        }
        
        if details:
            response["details"] = details
        
        return response
    
    # 在theme_service.py中添加以下方法

    async def initialize_with_categories_only(self, categories: List[Dict], db_manager=None):
        """
        仅使用分类数据初始化（不加载全量题材）
        用于分类优先匹配场景
        
        Args:
            categories: 分类数据列表
            db_manager: 数据库管理器（可选，用于后续按需加载）
        """
        logger.info("🔄 ThemeService分类专用初始化开始")
        
        self.db_manager = db_manager  # 保存db_manager用于按需加载
        
        try:
            # 检查发现引擎是否已创建
            if self.discovery_engine is None:
                self.discovery_engine = ThemeDiscoveryEngine(enable_clustering=self.enable_clustering)
                logger.info("   ✅ 创建新的发现引擎实例")
            
            # 构建空的题材数据
            empty_themes = []
            
            # 验证分类数据格式
            validated_categories = []
            for i, cat in enumerate(categories):
                if not isinstance(cat, dict):
                    logger.warning(f"⚠️  分类数据{i}不是字典格式: {type(cat)}")
                    continue
                    
                # 确保必要字段
                validated_cat = cat.copy()
                if 'category_code' not in validated_cat or not validated_cat['category_code']:
                    validated_cat['category_code'] = f"AUTO_CAT_{i:06d}"
                if 'category_name' not in validated_cat or not validated_cat['category_name']:
                    validated_cat['category_name'] = f"分类_{i}"
                if 'category_level' not in validated_cat:
                    validated_cat['category_level'] = 1
                    
                validated_categories.append(validated_cat)
            
            # 使用空题材和分类数据初始化引擎
            success = self.discovery_engine.load_data(empty_themes, validated_categories)
            
            if not success:
                logger.error("❌ 发现引擎数据加载失败")
                self._initialized = False
                return False
            
            # 初始化主题数据生成器（如果需要）
            if validated_categories:
                try:
                    self.theme_generator = ThemeDataGenerator(empty_themes, validated_categories)
                    if self.discovery_engine:
                        self.discovery_engine.set_theme_data_generator(self.theme_generator)
                    logger.info("✅ 主题数据生成器初始化成功")
                except Exception as e:
                    logger.warning(f"⚠️  主题数据生成器初始化失败（可接受）: {e}")
            
            self._initialized = True
            
            # 更新服务元数据
            self.service_metadata.update({
                "initialization_mode": "categories_only",
                "data_loaded": True,
                "theme_count": 0,  # 注意：没有加载全量题材
                "category_count": len(validated_categories),
                "initialized_at": datetime.now().isoformat(),
                "initialized": True
            })
            
            logger.info(f"✅ ThemeService分类专用初始化完成: {len(validated_categories)} 个分类")
            
            # 显示引擎状态
            if self.discovery_engine:
                try:
                    engine_status = self.discovery_engine.get_engine_status()
                    logger.info(f"   🚀 引擎状态: 分类数据已加载")
                    logger.info(f"   📊 分类数量: {len(validated_categories)}")
                    logger.info(f"   🔤 Major算法: {engine_status['algorithms']['major']['name']}")
                    logger.info(f"   🔤 Normal算法: {engine_status['algorithms']['normal']['name']}")
                except Exception as e:
                    logger.warning(f"   ⚠️  获取引擎状态失败: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ ThemeService分类专用初始化失败: {e}")
            traceback.print_exc()
            self._initialized = False
            return False

    async def discover_category_only(self, event_data: Dict) -> Dict:
        """
        仅进行分类匹配（不匹配具体题材）
        返回分类推断结果，不返回具体题材
        
        Args:
            event_data: 事件数据，应包含ai_analysis字段
            
        Returns:
            {
                'matched': True/False,
                'category_info': {分类详细信息},
                'event_id': 事件ID,
                'confidence': 分类匹配置信度
            }
        """
        operation = "discover_category_only"
        
        try:
            if not self.initialized:
                return {
                    'status': 'error',
                    'error': '服务未初始化',
                    'matched': False,
                    'category_info': {
                        'theme_type': 'concept',
                        'level1_category': '概念题材'
                    }
                }
            
            event_id = event_data.get('event_id', 'unknown')
            ai_analysis = event_data.get('ai_analysis', {})
            
            logger.debug(f"🔍 分类推断开始: {event_id}")
            
            # 检查是否有AI分析
            if not ai_analysis:
                logger.debug(f"   事件 {event_id} 无AI分析数据")
                return {
                    'matched': False,
                    'category_info': {
                        'theme_type': 'concept',
                        'level1_category': '概念题材',
                        'reason': 'no_ai_analysis'
                    },
                    'event_id': event_id,
                    'confidence': 0.0
                }
            
            # 尝试从发现引擎获取matcher进行分类推断
            category_result = None
            
            # 方法1: 通过discovery_engine的matcher
            if self.discovery_engine:
                # 尝试从Major matcher获取分类推断
                if hasattr(self.discovery_engine, 'major_matcher'):
                    matcher = self.discovery_engine.major_matcher
                    if hasattr(matcher, 'infer_category_from_ai_keywords'):
                        try:
                            category_result = matcher.infer_category_from_ai_keywords(ai_analysis)
                            logger.debug(f"   ✅ 使用Major matcher进行分类推断")
                        except Exception as e:
                            logger.warning(f"   ⚠️  Major matcher分类推断失败: {e}")
                
                # 如果Major matcher失败，尝试Normal matcher
                if not category_result and hasattr(self.discovery_engine, 'normal_matcher'):
                    matcher = self.discovery_engine.normal_matcher
                    if hasattr(matcher, 'infer_category_from_ai_keywords'):
                        try:
                            category_result = matcher.infer_category_from_ai_keywords(ai_analysis)
                            logger.debug(f"   ✅ 使用Normal matcher进行分类推断")
                        except Exception as e:
                            logger.warning(f"   ⚠️  Normal matcher分类推断失败: {e}")
            
            # 方法2: 如果无法通过matcher获取，构建简单的分类推断结果
            if not category_result:
                logger.debug(f"   ⚠️  无法使用matcher，构建简单分类推断")
                
                # 从AI关键词中提取可能的一级分类
                ai_keywords = ai_analysis.get('industry_keywords', [])
                core_concept = ai_analysis.get('core_concept', '')
                
                # 简单的关键词到分类的映射
                keyword_to_category = {
                    '半导体': '电子',
                    '芯片': '电子',
                    '人工智能': '计算机',
                    'AI': '计算机',
                    '医疗': '医药生物',
                    '医药': '医药生物',
                    '银行': '银行',
                    '金融': '非银金融',
                    '新能源': '电力设备',
                    '光伏': '电力设备'
                }
                
                # 查找匹配的分类
                matched_category = None
                for keyword in ai_keywords:
                    if keyword in keyword_to_category:
                        matched_category = keyword_to_category[keyword]
                        break
                
                if matched_category:
                    category_result = {
                        'matched': True,
                        'level1_category': matched_category,
                        'level2_category': f'{matched_category}细分',
                        'theme_type': 'investment',
                        'match_confidence': 0.5,
                        'matched_keywords': [kw for kw in ai_keywords if kw in keyword_to_category]
                    }
                else:
                    category_result = {
                        'matched': False,
                        'theme_type': 'concept',
                        'level1_category': '概念题材',
                        'level2_category': core_concept or '新兴概念',
                        'match_confidence': 0.0,
                        'reason': 'no_category_match'
                    }
            
            # 确保必要字段
            if 'matched' not in category_result:
                category_result['matched'] = False
            if 'theme_type' not in category_result:
                category_result['theme_type'] = 'concept'
            
            result = {
                'status': 'success',
                'matched': category_result['matched'],
                'category_info': category_result,
                'event_id': event_id,
                'confidence': category_result.get('match_confidence', 0.0),
                'operation': operation,
                'timestamp': datetime.now().isoformat()
            }
            
            if category_result['matched']:
                logger.info(f"✅ 分类推断成功: {event_id} -> "
                        f"{category_result.get('level1_category', 'N/A')}/"
                        f"{category_result.get('level2_category', 'N/A')}")
            else:
                logger.info(f"⚠️  分类推断未匹配: {event_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 分类推断失败: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'matched': False,
                'category_info': {
                    'theme_type': 'concept',
                    'level1_category': '概念题材',
                    'reason': 'exception'
                },
                'event_id': event_data.get('event_id', 'unknown'),
                'confidence': 0.0
            }

    async def get_themes_by_category_info(self, category_info: Dict, limit: int = 100) -> List[Dict]:
        """
        根据分类信息获取相关题材
        如果db_manager可用，从数据库查询；否则返回空列表
        
        Args:
            category_info: discover_category_only返回的分类信息
            limit: 最大返回数量
            
        Returns:
            题材列表
        """
        try:
            if not self.db_manager:
                logger.warning("⚠️  无db_manager，无法查询具体题材")
                return []
            
            # 提取分类代码
            level1_code = category_info.get('level1_code')
            level2_code = category_info.get('level2_code')
            
            # 优先使用二级分类代码
            if level2_code:
                logger.debug(f"📊 按二级分类查询题材: {level2_code}")
                # 这里需要根据实际的db_manager接口调整
                # 假设db_manager有get_themes_by_category方法
                if hasattr(self.db_manager, 'get_themes_by_category'):
                    themes = await self.db_manager.get_themes_by_category(
                        level2_code, level=2, limit=limit
                    )
                    return themes
            
            # 使用一级分类代码
            elif level1_code:
                logger.debug(f"📊 按一级分类查询题材: {level1_code}")
                if hasattr(self.db_manager, 'get_themes_by_category'):
                    themes = await self.db_manager.get_themes_by_category(
                        level1_code, level=1, limit=limit
                    )
                    return themes
            
            # 如果只有分类名称，尝试模糊查询
            elif category_info.get('level1_category'):
                category_name = category_info['level1_category']
                logger.debug(f"📊 按分类名称查询题材: {category_name}")
                
                # 这里可以根据需要实现按名称查询的逻辑
                # 例如通过db_manager执行SQL查询
            
            return []
            
        except Exception as e:
            logger.error(f"❌ 按分类查询题材失败: {e}")
            return []
    
    async def discover_category_only(self, event_data: Dict) -> Dict:
        """
        第一阶段：仅分类推断
        
        Args:
            event_data: 事件数据，必须包含ai_analysis
            
        Returns:
            {
                'matched': True/False,
                'category_info': {分类详细信息},
                'confidence': 分类匹配置信度,
                'event_id': 事件ID
            }
        """
        operation = "discover_category_only"
        
        try:
            if not self.initialized:
                return self._create_error_response(
                    "服务未初始化", 
                    operation,
                    "请先调用 initialize() 方法"
                )
            
            event_id = event_data.get('event_id', 'unknown')
            ai_analysis = event_data.get('ai_analysis', {})
            
            logger.info(f"🔍 第一阶段：分类推断开始: {event_id}")
            
            # 检查是否有AI分析
            if not ai_analysis:
                logger.info(f"   事件 {event_id} 无AI分析数据")
                return {
                    'status': 'success',
                    'operation': operation,
                    'matched': False,
                    'category_info': {
                        'theme_type': 'concept',
                        'level1_category': '概念题材',
                        'reason': 'no_ai_analysis'
                    },
                    'event_id': event_id,
                    'confidence': 0.0
                }
            
            # 调用ThemeDiscoveryEngine进行分类推断
            if not self.discovery_engine:
                return self._create_error_response(
                    "发现引擎不可用", 
                    operation
                )
            
            # 检查引擎是否支持分类推断
            if not hasattr(self.discovery_engine, 'infer_category'):
                logger.warning("发现引擎不支持infer_category方法")
                return {
                    'status': 'error',
                    'error': '引擎不支持分类推断',
                    'matched': False,
                    'event_id': event_id
                }
            
            # 执行分类推断
            category_result = await self.discovery_engine.infer_category(event_data)
            
            # 构建响应
            result = {
                'status': 'success',
                'operation': operation,
                'matched': category_result.get('matched', False),
                'category_info': category_result.get('category_info', {}),
                'event_id': event_id,
                'confidence': category_result.get('confidence', 0.0),
                'processing_info': {
                    'algorithm_used': category_result.get('algorithm_used', ''),
                    'processing_time_ms': category_result.get('processing_time_ms', 0),
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            if category_result.get('matched'):
                logger.info(f"✅ 分类推断成功: {event_id} -> "
                          f"{result['category_info'].get('level1_category', 'N/A')}")
            else:
                logger.info(f"⚠️  分类推断未匹配: {event_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 分类推断失败: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'operation': operation,
                'matched': False,
                'event_id': event_data.get('event_id', 'unknown')
            }
    
    async def discover_with_themes(self, event_data: Dict, themes: List[Dict]) -> Dict:
        """
        第二阶段：在指定题材中匹配
        
        Args:
            event_data: 事件数据
            themes: 题材列表（由ThemeProcessor按分类查询获得）
            
        Returns:
            {
                'matched': True/False,
                'themes': [匹配的题材列表],
                'theme_count': 匹配题材数量,
                'confidence': 最佳匹配置信度,
                'event_id': 事件ID
            }
        """
        operation = "discover_with_themes"
        
        try:
            if not self.initialized:
                return self._create_error_response(
                    "服务未初始化", 
                    operation,
                    "请先调用 initialize() 方法"
                )
            
            event_id = event_data.get('event_id', 'unknown')
            event_type = event_data.get('event_type', 'normal')
            
            logger.info(f"🔍 第二阶段：题材匹配开始: {event_id}")
            logger.info(f"   匹配题材数量: {len(themes)}")
            
            if not themes:
                logger.info(f"   无题材可匹配，直接返回未匹配")
                return {
                    'status': 'success',
                    'operation': operation,
                    'matched': False,
                    'themes': [],
                    'theme_count': 0,
                    'confidence': 0.0,
                    'event_id': event_id
                }
            
            # 调用ThemeDiscoveryEngine进行指定题材匹配
            if not self.discovery_engine:
                return self._create_error_response(
                    "发现引擎不可用", 
                    operation
                )
            
            # 检查引擎是否支持指定题材匹配
            if not hasattr(self.discovery_engine, 'match_with_themes'):
                logger.warning("发现引擎不支持match_with_themes方法")
                # 回退到discover_theme方法
                return await self.discover_theme(event_data)
            
            # 执行指定题材匹配
            match_result = await self.discovery_engine.match_with_themes(
                event_data, 
                themes,
                event_type=event_type  # 传递事件类型用于阈值选择
            )
            
            # 构建响应
            result = {
                'status': 'success',
                'operation': operation,
                'matched': match_result.get('matched', False),
                'themes': match_result.get('themes', []),
                'theme_count': match_result.get('theme_count', 0),
                'confidence': match_result.get('confidence', 0.0),
                'event_id': event_id,
                'processing_info': {
                    'event_type': event_type,
                    'algorithm_used': match_result.get('algorithm_used', ''),
                    'threshold_used': match_result.get('threshold_used', 0),
                    'processing_time_ms': match_result.get('processing_time_ms', 0),
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            if match_result.get('matched'):
                matched_themes = match_result.get('themes', [])
                logger.info(f"✅ 题材匹配成功: {event_id} -> "
                          f"{len(matched_themes)} 个题材")
                if matched_themes:
                    logger.info(f"   最佳匹配: {matched_themes[0].get('name', 'N/A')} "
                              f"(置信度: {matched_themes[0].get('confidence', 0):.2f})")
            else:
                logger.info(f"⚠️  题材匹配失败: {event_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 题材匹配失败: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'operation': operation,
                'matched': False,
                'event_id': event_data.get('event_id', 'unknown')
            }


# 全局单例实例
_theme_service_instance = None

def get_theme_service(enable_clustering: bool = False) -> ThemeService:
    """获取Theme Service实例（单例模式）"""
    global _theme_service_instance
    if _theme_service_instance is None:
        _theme_service_instance = ThemeService(enable_clustering=enable_clustering)
        logger.info(f"✅ 创建ThemeService单例实例 (聚类分析: {'启用' if enable_clustering else '关闭'})")
    return _theme_service_instance


# 测试函数
async def test_theme_service_with_clustering():
    """测试带聚类分析的Theme Service"""
    try:
        # 创建带聚类分析的服务
        service = get_theme_service(enable_clustering=True)
        
        print("\n" + "="*60)
        print("🎯 Theme Service聚类分析测试")
        print("="*60)
        
        # 1. 初始化服务
        await service.initialize()
        
        # 2. 检查服务状态
        status = await service.get_service_status()
        print(f"1. 服务状态: {status.get('status')}")
        print(f"   初始化: {'✅ 是' if status['initialized'] else '❌ 否'}")
        print(f"   聚类分析: {'✅ 启用' if status.get('clustering', {}).get('enabled') else '❌ 关闭'}")
        
        if not status['initialized']:
            print(f"   ❌ 服务未初始化，无法继续测试")
            return
        
        # 3. 创建外部未匹配池
        unmatched_pool = []
        
        # 4. 测试Normal事件聚类
        print(f"\n2. 测试Normal事件聚类分析:")
        normal_events = [
            {
                "event_id": "test_normal_ai_001",
                "event_type": "normal",
                "title": "AI医疗诊断系统获得FDA批准",
                "content": "AI医疗诊断系统通过FDA认证，将在美国上市。",
                "ai_analysis": {
                    "core_concept": "AI医疗诊断",
                    "industry_keywords": ["AI医疗", "诊断系统", "FDA", "人工智能", "医疗设备"]
                }
            },
            {
                "event_id": "test_normal_ai_002",
                "event_type": "normal",
                "title": "AI医疗影像识别技术突破",
                "content": "AI医疗影像识别技术准确率达到99%，大幅提升诊断效率。",
                "ai_analysis": {
                    "core_concept": "AI医疗诊断",
                    "industry_keywords": ["AI医疗", "影像识别", "医疗设备", "人工智能"]
                }
            }
        ]
        
        # 处理事件并收集到未匹配池
        for event in normal_events:
            result = await service.discover_theme(
                event,
                external_unmatched_pool=unmatched_pool
            )
            print(f"   事件: {event['event_id']}, 匹配: {result['response']['matched']}")
        
        print(f"   未匹配池大小: {len(unmatched_pool)}")
        
        # 5. 手动触发聚类分析
        if len(unmatched_pool) > 0:
            print(f"\n3. 手动触发聚类分析:")
            clustering_result = await service.trigger_clustering_analysis(
                unmatched_pool,
                auto_create=True,
                min_confidence=0.7
            )
            
            if clustering_result['status'] == 'success':
                response = clustering_result['response']
                print(f"   状态: {response.get('status')}")
                print(f"   发现候选: {response.get('new_candidates_found', 0)} 个")
                
                # 检查自动创建结果
                auto_creation = response.get('auto_creation', {})
                if auto_creation.get('status') == 'success':
                    print(f"   🎉 自动创建成功: {auto_creation.get('themes_created', 0)} 个题材")
                else:
                    print(f"   自动创建状态: {auto_creation.get('status', '未知')}")
            else:
                print(f"   ❌ 聚类分析失败: {clustering_result.get('error')}")
        
        # 6. 测试Major事件
        print(f"\n4. 测试Major事件:")
        major_event = {
            "event_id": "test_major_001",
            "event_type": "major",
            "title": "量子计算芯片技术实现重大突破",
            "content": "中国科研团队在量子计算芯片领域取得重大突破，实现了100量子比特的量子计算原型机。",
            "ai_analysis": {
                "core_concept": "量子计算芯片",
                "concept_confidence": 0.85,
                "industry_keywords": ["量子计算", "芯片", "半导体", "量子比特"]
            }
        }
        
        major_result = await service.discover_and_create_theme(major_event)
        if major_result['status'] == 'success':
            response = major_result['response']
            print(f"   匹配结果: {response['discovery_result']['matched']}")
            if response.get('should_create_theme'):
                theme = response['new_theme_suggestion']
                print(f"   🚀 建议创建新题材: {theme.get('name')} ({theme.get('code')})")
        
        # 7. 测试服务状态
        print(f"\n5. 服务状态详情:")
        status = await service.get_service_status()
        if status['status'] == 'healthy':
            print(f"   ✅ 服务运行正常")
            if status.get('clustering', {}).get('enabled'):
                stats = status['clustering'].get('stats', {})
                print(f"   聚类统计:")
                print(f"     未匹配事件: {stats.get('unmatched_events_count', 0)}")
                print(f"     形成簇数: {stats.get('clusters_formed', 0)}")
                print(f"     自动创建题材: {stats.get('themes_created', 0)}")
        
        print("\n✅ 聚类分析测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    # 运行测试
    print("选择测试模式:")
    print("1. 基础功能测试")
    print("2. 聚类分析测试")
    choice = input("请输入选择 (1/2): ").strip()
    
    if choice == "2":
        asyncio.run(test_theme_service_with_clustering())
    else:
        # 原有的基础功能测试
        asyncio.run(test_theme_service())
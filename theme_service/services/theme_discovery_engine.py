"""
主题发现引擎 - 业务逻辑处理（精简优化版）
纯算法引擎，不处理候选池存储
"""
import logging
from datetime import datetime
import time
from typing import List, Dict, Any, Optional

from theme_service.matchers.matcher_factory import MatcherFactory
from theme_service.matchers.base_matcher import BaseMatcher, MatchResult

# 获取logger实例
logger = logging.getLogger(__name__)

class ThemeDiscoveryEngine:
    """主题发现引擎 - 精简版（纯算法）"""
    
    def __init__(self, enable_clustering: bool = False, enable_transformer: bool = True):
        """初始化主题发现引擎（纯算法版）
        
        Args:
            enable_clustering: 是否启用聚类分析功能（默认关闭，保持向后兼容）
            enable_transformer: 是否启用Transformer语义匹配（默认开启）
        """
        print("🚀 初始化主题发现引擎（纯算法版）...")
        
        try:
            # 1. 创建算法实例 - 使用Transformer语义匹配替代关键词匹配
            major_config = {
                'model_name': 'bert-base-chinese',
                'semantic_threshold': 0.92,     # 语义匹配阈值
                'keyword_threshold': 0.5,      # 关键词匹配阈值（用于回退）
                'max_results': 10,
                'min_keyword_matches': 3,
                'enable_analyst_logic': True,
                'classification_first': True,
                'fallback_to_keyword': True,   # 允许回退到关键词匹配
                'enable_cache': True,          # 启用缓存
                'cache_size': 1000             # 缓存大小
            }
            
            normal_config = {
                'model_name': 'bert-base-chinese',
                'semantic_threshold': 0.88,     # 语义匹配阈值
                'keyword_threshold': 0.4,      # 关键词匹配阈值（用于回退）
                'max_results': 15,
                'min_keyword_matches': 2,
                'enable_analyst_logic': False,
                'classification_first': False,
                'fallback_to_keyword': True,   # 允许回退到关键词匹配
                'enable_cache': True,          # 启用缓存
                'cache_size': 1000             # 缓存大小
            }

            # 🔥 关键修改：使用transformer代替keyword
            if enable_transformer:
                print("   🤖 启用Transformer语义匹配器")
                self.major_matcher = MatcherFactory.create_matcher('transformer', major_config)
                self.normal_matcher = MatcherFactory.create_matcher('transformer', normal_config)
            else:
                print("   ⚠️  使用传统关键词匹配器（兼容模式）")
                self.major_matcher = MatcherFactory.create_matcher('keyword', major_config)
                self.normal_matcher = MatcherFactory.create_matcher('keyword', normal_config)
            
            # 🔥 新增：聚类分析算法实例（可选）
            self.enable_clustering = enable_clustering
            self.enable_transformer = enable_transformer
            self.clustering_matcher = None
            self.clustering_stats = {
                'unmatched_events_count': 0,
                'clusters_formed': 0,
                'last_clustering_check': None
            }
            
            if enable_clustering:
                clustering_config = {
                    'min_cluster_size': 3,
                    'similarity_threshold': 0.6,
                    'max_clusters': 20,
                    'max_unmatched_events': 100,
                    'clustering_interval_minutes': 30,
                    'min_quality_threshold': 0.4
                }
                self.clustering_matcher = MatcherFactory.create_matcher('clustering', clustering_config)
                print(f"   ✅ 聚类分析功能已启用")
            
            # 3. 初始化标志
            self.data_loaded = False
            self.current_themes_count = 0
            self.current_categories_count = 0
            self.theme_data_generator = None
            
            print("✅ 主题发现引擎初始化完成（纯算法版）")
            
        except Exception as e:
            print(f"❌ 主题发现引擎初始化失败: {e}")
            raise
    
    def load_data(self, themes: List[Dict], categories: List[Dict] = None) -> bool:
        """
        加载算法数据 - 增强版（保持向后兼容）
        
        注意：这个方法会被ThemeService调用，必须保持接口不变
        """
        print(f"📥 ThemeDiscoveryEngine.load_data - 增强初始化")
        
        try:
            # 步骤1: 验证数据格式
            validated_themes = self._validate_and_prepare_themes(themes)
            validated_categories = self._validate_and_prepare_categories(categories)
            
            # 步骤2: 更新数据统计
            self.current_themes_count = len(validated_themes)
            self.current_categories_count = len(validated_categories)
            
            print(f"📊 数据统计: {self.current_themes_count}题材, "
                  f"{self.current_categories_count}分类")
            
            # 步骤3: 初始化major_matcher（必须成功）
            print("🔧 初始化Major匹配器...")
            try:
                self.major_matcher.initialize(validated_themes, validated_categories)
                print(f"   ✅ Major匹配器初始化成功")
                
                # 🔥 如果是Transformer匹配器，打印模型信息
                if hasattr(self.major_matcher, 'model_name'):
                    print(f"   🧠 使用模型: {self.major_matcher.model_name}")
                    if hasattr(self.major_matcher, 'config') and 'fallback_to_keyword' in self.major_matcher.config:
                        fallback_enabled = self.major_matcher.config.get('fallback_to_keyword', False)
                        print(f"   🔄 关键词回退: {'✅ 启用' if fallback_enabled else '❌ 禁用'}")
                
            except Exception as e:
                print(f"   ❌ Major匹配器初始化失败: {e}")
                # 尝试使用空数据初始化
                try:
                    self.major_matcher.initialize([], validated_categories)
                    print(f"   ⚠️  Major匹配器使用空数据重新初始化")
                except Exception as e2:
                    print(f"   ❌ Major匹配器完全失败: {e2}")
                    return False
            
            # 步骤4: 初始化normal_matcher（必须成功）
            print("🔧 初始化Normal匹配器...")
            try:
                self.normal_matcher.initialize(validated_themes, validated_categories)
                print(f"   ✅ Normal匹配器初始化成功")
                
                # 🔥 如果是Transformer匹配器，打印模型信息
                if hasattr(self.normal_matcher, 'model_name'):
                    print(f"   🧠 使用模型: {self.normal_matcher.model_name}")
                    
            except Exception as e:
                print(f"   ❌ Normal匹配器初始化失败: {e}")
                # 尝试使用空数据初始化
                try:
                    self.normal_matcher.initialize([], validated_categories)
                    print(f"   ⚠️  Normal匹配器使用空数据重新初始化")
                except Exception as e2:
                    print(f"   ❌ Normal匹配器完全失败: {e2}")
                    return False
            
            # 步骤5: 初始化聚类分析器（如果启用，可选成功）
            if self.enable_clustering:
                print("🔧 初始化聚类分析器...")
                
                # 检查clustering_matcher是否存在
                if not self.clustering_matcher:
                    print(f"   ⚠️  聚类分析器未创建，尝试创建...")
                    self._create_clustering_matcher()
                
                if self.clustering_matcher:
                    try:
                        # 🔥 注意：聚类分析器可能需要不同格式的数据
                        # 如果聚类分析器有特殊的初始化需求
                        if hasattr(self.clustering_matcher, 'initialize'):
                            # 尝试使用categories初始化
                            if validated_categories:
                                self.clustering_matcher.initialize([], validated_categories)
                                print(f"   ✅ 聚类分析器初始化成功（使用分类数据）")
                            else:
                                # 如果没有分类数据，使用空数据初始化
                                self.clustering_matcher.initialize([], [])
                                print(f"   ⚠️  聚类分析器使用空数据初始化")
                        else:
                            print(f"   ⚠️  聚类分析器没有initialize方法")
                    except Exception as e:
                        print(f"   ⚠️  聚类分析器初始化失败（可接受）: {e}")
                        # 聚类分析器初始化失败不应该影响整体
                else:
                    print(f"   ⚠️  聚类分析器创建失败，但继续其他初始化")
            else:
                print(f"   🔕 聚类分析功能未启用")
            
            # 步骤6: 更新引擎状态
            self.data_loaded = True
            self.themes_data = {t.get('id', str(i)): t for i, t in enumerate(validated_themes)}
            self.categories_data = {c.get('category_code', str(i)): c 
                                   for i, c in enumerate(validated_categories)}
            
            # 步骤7: 打印初始化摘要
            self._print_initialization_summary()
            
            print(f"✅ ThemeDiscoveryEngine.load_data完成")
            return True
            
        except Exception as e:
            print(f"❌ ThemeDiscoveryEngine.load_data失败: {e}")
            import traceback
            traceback.print_exc()
            
            self.data_loaded = False
            return False
    
    def _validate_and_prepare_themes(self, themes: List[Dict]) -> List[Dict]:
        """验证和准备题材数据"""
        if not themes:
            print(f"   ⚠️  题材数据为空")
            return []
        
        validated = []
        for i, theme in enumerate(themes):
            if not isinstance(theme, dict):
                print(f"   ⚠️  题材{i}不是字典: {type(theme)}")
                continue
            
            # 确保必要字段
            theme_copy = theme.copy()
            
            if 'id' not in theme_copy or not theme_copy['id']:
                theme_copy['id'] = f"theme_{i:06d}"
            
            if 'name' not in theme_copy or not theme_copy['name']:
                theme_copy['name'] = f"题材_{i}"
            
            # 🔥 为Transformer优化：确保有语义分析的字段
            if 'keywords' not in theme_copy:
                theme_copy['keywords'] = []
            
            if 'description' not in theme_copy:
                theme_copy['description'] = theme_copy.get('name', '')
            
            validated.append(theme_copy)
        
        print(f"   验证后题材: {len(validated)}个有效")
        return validated
    
    def _validate_and_prepare_categories(self, categories: List[Dict]) -> List[Dict]:
        """验证和准备分类数据"""
        if not categories:
            print(f"   ⚠️  分类数据为空")
            return []
        
        validated = []
        for i, category in enumerate(categories):
            if not isinstance(category, dict):
                print(f"   ⚠️  分类{i}不是字典: {type(category)}")
                continue
            
            # 确保必要字段
            cat_copy = category.copy()
            
            if 'category_code' not in cat_copy or not cat_copy['category_code']:
                cat_copy['category_code'] = f"cat_{i:06d}"
            
            if 'category_name' not in cat_copy or not cat_copy['category_name']:
                cat_copy['category_name'] = f"分类_{i}"
            
            if 'category_level' not in cat_copy:
                cat_copy['category_level'] = 1
            
            # 🔥 为Transformer优化：确保有语义分析的字段
            if 'keywords' not in cat_copy:
                cat_copy['keywords'] = []
            
            validated.append(cat_copy)
        
        print(f"   验证后分类: {len(validated)}个有效")
        return validated
    
    def _create_clustering_matcher(self):
        """创建聚类分析器（如果需要）"""
        try:
            # 尝试导入聚类匹配器
            from theme_service.matchers.matcher_factory import MatcherFactory
            
            clustering_config = {
                'min_cluster_size': 3,
                'similarity_threshold': 0.6,
                'max_clusters': 20,
                'clustering_interval_minutes': 30
            }
            
            self.clustering_matcher = MatcherFactory.create_matcher('clustering', clustering_config)
            print(f"   ✅ 聚类分析器创建成功")
            
        except ImportError as e:
            print(f"   ⚠️  无法导入聚类分析器: {e}")
            self.clustering_matcher = None
        except Exception as e:
            print(f"   ⚠️  创建聚类分析器失败: {e}")
            self.clustering_matcher = None
    
    def _print_initialization_summary(self):
        """打印初始化摘要"""
        print("\n" + "-"*50)
        print("🎯 ThemeDiscoveryEngine初始化摘要")
        print("-"*50)
        
        # 匹配器状态
        major_ready = hasattr(self.major_matcher, 'initialized') and self.major_matcher.initialized
        normal_ready = hasattr(self.normal_matcher, 'initialized') and self.normal_matcher.initialized
        
        print(f"📊 数据统计:")
        print(f"  题材数量: {self.current_themes_count}")
        print(f"  分类数量: {self.current_categories_count}")
        
        print(f"🔧 组件状态:")
        
        # 获取匹配器类型
        major_type = self._get_matcher_type(self.major_matcher)
        normal_type = self._get_matcher_type(self.normal_matcher)
        
        print(f"  Major匹配器: {'✅ 就绪' if major_ready else '❌ 未就绪'} ({major_type})")
        print(f"  Normal匹配器: {'✅ 就绪' if normal_ready else '❌ 未就绪'} ({normal_type})")
        
        if self.enable_clustering:
            clustering_ready = (
                self.clustering_matcher and 
                hasattr(self.clustering_matcher, 'initialized') and 
                self.clustering_matcher.initialized
            )
            print(f"  聚类分析器: {'✅ 就绪' if clustering_ready else '⚠️  未就绪'}")
        else:
            print(f"  聚类分析器: 🔕 未启用")
        
        print(f"🚀 引擎状态: {'✅ 数据已加载' if self.data_loaded else '❌ 数据未加载'}")
        print(f"🧠 Transformer语义: {'✅ 启用' if self.enable_transformer else '❌ 禁用'}")
        print("-"*50)
    
    def _get_matcher_type(self, matcher) -> str:
        """获取匹配器类型"""
        if hasattr(matcher, '__class__'):
            class_name = matcher.__class__.__name__
            if 'Transformer' in class_name or 'transformer' in class_name.lower():
                return "Transformer语义"
            elif 'Keyword' in class_name or 'keyword' in class_name.lower():
                return "关键词匹配"
            elif 'Hybrid' in class_name or 'hybrid' in class_name.lower():
                return "混合匹配"
            else:
                return class_name
        return "未知类型"
    
    def set_theme_data_generator(self, theme_data_generator):
        """设置题材数据生成器"""
        self.theme_data_generator = theme_data_generator
        print(f"✅ 设置题材数据生成器")
    
    def discover(self, event_data: Dict, **kwargs) -> Dict:
        """
        发现主题 - 纯算法处理
        
        Args:
            event_data: 事件数据
            **kwargs: 可选参数
                - on_major_unmatched: Major事件未匹配时的回调函数
                - on_normal_unmatched: Normal事件未匹配时的回调函数
                - external_unmatched_pool: 外部未匹配池（用于聚类分析）
        
        Returns:
            算法处理结果（只包含算法信息，不包含存储操作）
        """
        if not self.data_loaded:
            raise RuntimeError("请先调用 load_data() 加载数据")
        
        start_time = time.time()
        
        try:
            event_type = event_data.get('event_type', 'normal')
            event_id = event_data.get('event_id', 'unknown')
            
            print(f"\n🔍 算法发现开始: {event_id}")
            print(f"   事件类型: {event_type}")
            print(f"   匹配器类型: {self._get_matcher_type(self.major_matcher if event_type == 'major' else self.normal_matcher)}")
            
            # 根据事件类型处理
            if event_type == 'major':
                result = self._process_major_event(event_data)
                
                # 🔥 如果有未匹配回调函数，调用它
                if not result['matched'] and 'on_major_unmatched' in kwargs:
                    callback = kwargs['on_major_unmatched']
                    if callable(callback):
                        try:
                            callback(event_data, result)
                            print(f"   📞 执行Major未匹配回调")
                        except Exception as e:
                            print(f"   ⚠️  Major未匹配回调失败: {e}")
            else:
                # 🔥 处理Normal事件，支持聚类分析
                external_pool = kwargs.get('external_unmatched_pool')
                normal_callback = kwargs.get('on_normal_unmatched')
                
                if self.enable_clustering and external_pool is not None:
                    result = self._process_normal_event_with_clustering(
                        event_data, external_pool, normal_callback
                    )
                else:
                    # 🔥 保持原有逻辑
                    result = self._process_normal_event(event_data)
                    
                    # 如果有未匹配回调函数，调用它
                    if not result['matched'] and normal_callback and callable(normal_callback):
                        try:
                            normal_callback(event_data, result)
                            print(f"   📞 执行Normal未匹配回调")
                        except Exception as e:
                            print(f"   ⚠️  Normal未匹配回调失败: {e}")
            
            # 构建返回结果
            response = {
                'event_id': event_id,
                'event_type': event_type,
                'matched': result['matched'],
                'theme_count': len(result['themes']),
                'themes': [match.to_dict() for match in result['themes']],
                'processing_path': result['processing_path'],
                'algorithm_used': result['algorithm_used'],
                'matcher_type': self._get_matcher_type(self.major_matcher if event_type == 'major' else self.normal_matcher),
                'processing_time_ms': round((time.time() - start_time) * 1000, 2),
                'confidence': result['confidence'],
            }
            
            # 🔥 新增：Transformer匹配器特有信息
            if hasattr(self.major_matcher, 'model_name') and event_type == 'major':
                response['transformer_info'] = {
                    'model': self.major_matcher.model_name,
                    'semantic_threshold': getattr(self.major_matcher, 'semantic_threshold', 0.5)
                }
            elif hasattr(self.normal_matcher, 'model_name') and event_type == 'normal':
                response['transformer_info'] = {
                    'model': self.normal_matcher.model_name,
                    'semantic_threshold': getattr(self.normal_matcher, 'semantic_threshold', 0.5)
                }
            
            # 🔥 新增：聚类分析相关信息
            if 'clustering_info' in result:
                response['clustering_info'] = result['clustering_info']
            
            # Major事件未匹配时标记需要创建
            if not result['matched'] and event_type == 'major':
                response['should_create_theme'] = True
                response['create_reason'] = 'major_event_no_match'
                
                # 如果有AI分析，保存AI推断结果（但不生成数据）
                ai_analysis = event_data.get('ai_analysis', {})
                if ai_analysis and hasattr(self.major_matcher, 'infer_category_from_ai_keywords'):
                    try:
                        ai_category_result = self.major_matcher.infer_category_from_ai_keywords(ai_analysis)
                        response['ai_category_inference'] = ai_category_result
                    except Exception as e:
                        response['ai_category_inference_error'] = str(e)
            
            print(f"   ✅ 算法发现完成: 匹配={result['matched']}, 题材数={len(result['themes'])}, 耗时={response['processing_time_ms']}ms")
            return response
            
        except Exception as e:
            print(f"❌ 算法发现失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'event_id': event_data.get('event_id', ''),
                'matched': False,
                'error': str(e)
            }
    
    def _process_major_event(self, event_data: Dict) -> Dict:
        """处理Major事件 - Transformer语义匹配"""
        print("   使用Transformer Major算法匹配...")
        
        start_time = time.time()
        
        # 调用算法匹配
        matches = self.major_matcher.match(event_data, precision='major')
        
        # 🔥 Transformer匹配器可能返回不同的分数范围，调整阈值
        # 对于语义匹配，分数通常较高，可以适当提高阈值
        min_confidence = 0.6  # 语义匹配需要更高的置信度
        
        filtered_matches = [match for match in matches if match.confidence >= min_confidence]
        
        processing_time = (time.time() - start_time) * 1000
        
        if filtered_matches:
            print(f"   ✅ 语义匹配成功: {len(filtered_matches)} 个题材")
            
            # 打印匹配详情
            for i, match in enumerate(filtered_matches[:3]):
                print(f"     {i+1}. {match.theme_name} (置信度: {match.confidence:.3f})")
                if hasattr(match, 'match_details') and 'semantic_score' in match.match_details:
                    semantic_score = match.match_details.get('semantic_score', 0)
                    keyword_score = match.match_details.get('keyword_score', 0)
                    print(f"       语义分: {semantic_score:.3f}, 关键词分: {keyword_score:.3f}")
            
            return {
                'matched': True,
                'themes': filtered_matches,
                'processing_path': 'major→transformer→success',
                'algorithm_used': 'Transformer Major算法',
                'confidence': filtered_matches[0].confidence if filtered_matches else 0.0,
                'processing_time_ms': processing_time
            }
        else:
            print(f"   ⚠️  未匹配到现有题材")
            
            # 🔥 检查是否启用了关键词回退
            if hasattr(self.major_matcher, 'config') and self.major_matcher.config.get('fallback_to_keyword', False):
                print(f"   🔄 语义匹配失败，已自动回退到关键词匹配")
            
            # 🔥 不处理候选池，只返回算法结果
            return {
                'matched': False,
                'themes': matches[:5],  # 即使未达阈值，也返回前几个匹配结果
                'processing_path': 'major→transformer→no_match',
                'algorithm_used': 'Transformer Major算法',
                'confidence': matches[0].confidence if matches else 0.0,
                'processing_time_ms': processing_time
            }
    
    def _process_normal_event(self, event_data: Dict) -> Dict:
        """处理Normal事件 - Transformer语义匹配"""
        print("   使用Transformer Normal算法匹配...")
        
        start_time = time.time()
        
        matches = self.normal_matcher.match(event_data, precision='normal')
        min_confidence = 0.5  # Normal事件可以稍微降低阈值
        
        filtered_matches = [match for match in matches if match.confidence >= min_confidence]
        
        processing_time = (time.time() - start_time) * 1000
        
        if filtered_matches:
            print(f"   ✅ 语义匹配成功: {len(filtered_matches)} 个题材")
            
            # 打印前3个匹配结果
            for i, match in enumerate(filtered_matches[:3]):
                print(f"     {i+1}. {match.theme_name} (置信度: {match.confidence:.3f})")
            
            return {
                'matched': True,
                'themes': filtered_matches,
                'processing_path': 'normal→transformer→success',
                'algorithm_used': 'Transformer Normal算法',
                'confidence': filtered_matches[0].confidence if filtered_matches else 0.0,
                'processing_time_ms': processing_time
            }
        else:
            print(f"   ⚠️  未匹配到现有题材")
            return {
                'matched': False,
                'themes': matches[:3],
                'processing_path': 'normal→transformer→no_match',
                'algorithm_used': 'Transformer Normal算法',
                'confidence': matches[0].confidence if matches else 0.0,
                'processing_time_ms': processing_time
            }
    
    def _process_normal_event_with_clustering(self, event_data: Dict, 
                                            external_pool: List, 
                                            callback: Optional[callable] = None) -> Dict:
        """
        处理Normal事件 - 增强版（支持聚类分析）
        
        处理流程：
        1. 先执行原有匹配逻辑
        2. 如果未匹配，进入聚类分析流程
        3. 将事件添加到外部未匹配池
        4. 检查是否应该触发聚类分析
        """
        # 步骤1: 先执行原有匹配逻辑
        result = self._process_normal_event(event_data)
        
        # 如果匹配成功，直接返回
        if result['matched']:
            return result
        
        # 步骤2: 未匹配，进入聚类分析流程
        print(f"   🔍 进入聚类分析流程")
        
        # 获取AI分析信息
        ai_analysis = event_data.get('ai_analysis', {})
        category_result = None
        
        if ai_analysis and hasattr(self.normal_matcher, 'infer_category_from_ai_keywords'):
            try:
                category_result = self.normal_matcher.infer_category_from_ai_keywords(ai_analysis)
                print(f"   📊 AI分类推断完成")
            except Exception as e:
                print(f"   ⚠️  AI分类推断失败: {e}")
        
        # 步骤3: 添加到外部未匹配池
        if external_pool is not None:
            try:
                external_pool.append({
                    'event_data': event_data,
                    'category_result': category_result,
                    'algorithm_processed': True
                })
                print(f"   📤 添加到外部未匹配池")
                
                # 更新统计
                self.clustering_stats['unmatched_events_count'] += 1
            except Exception as e:
                print(f"   ⚠️  添加到外部未匹配池失败: {e}")
        
        # 步骤4: 执行回调（如果提供）
        if callback and callable(callback):
            try:
                callback(event_data, result, category_result)
                print(f"   📞 执行聚类分析回调")
            except Exception as e:
                print(f"   ⚠️  聚类分析回调失败: {e}")
        
        # 步骤5: 检查是否应该执行聚类分析
        should_cluster = self._should_perform_clustering()
        
        if should_cluster:
            print(f"   🎯 尝试聚类分析...")
            
            # 执行聚类分析
            new_candidates = self._perform_clustering_analysis(external_pool)
            
            if new_candidates:
                print(f"   ✅ 聚类分析发现 {len(new_candidates)} 个新题材候选")
                self.clustering_stats['clusters_formed'] += len(new_candidates)
                
                # 返回聚类分析结果
                return {
                    'matched': False,
                    'themes': result['themes'],
                    'processing_path': 'normal→no_match→clustering_success',
                    'algorithm_used': 'Transformer算法+聚类分析',
                    'confidence': 0.0,
                    'clustering_info': {
                        'triggered': True,
                        'new_candidates_found': len(new_candidates),
                        'clustering_method': 'auto_clustering'
                    },
                    'new_theme_candidates': new_candidates  # 算法发现的新题材候选
                }
        
        # 步骤6: 等待更多事件
        pool_size = len(external_pool) if external_pool else 0
        
        return {
            'matched': False,
            'themes': result['themes'],
            'processing_path': 'normal→no_match→clustering_pending',
            'algorithm_used': 'Transformer算法',
            'confidence': result['confidence'],
            'clustering_info': {
                'triggered': False,
                'pool_size': pool_size,
                'min_cluster_size': 3,
                'progress': f"等待更多事件 ({pool_size}/3)"
            }
        }
    
    def _should_perform_clustering(self) -> bool:
        """检查是否应该执行聚类分析"""
        if not self.enable_clustering or not self.clustering_matcher:
            return False
        
        # 检查时间间隔（5分钟一次）
        now = time.time()  # 浮点数时间戳
        
        if self.clustering_stats['last_clustering_check']:
            last_check = self.clustering_stats['last_clustering_check']
            
            # 统一处理：确保last_check是浮点数
            if isinstance(last_check, str):
                # 如果是ISO格式字符串，转换为时间戳
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                    last_check = dt.timestamp()  # 转换为时间戳
                except:
                    last_check = now - 3600  # 转换失败，默认1小时前
            
            # 计算时间差（秒）
            elapsed_seconds = now - last_check
            elapsed_minutes = elapsed_seconds / 60
            
            if elapsed_minutes < 5:
                return False
        
        return True
    
    def _perform_clustering_analysis(self, external_pool: List) -> List[Dict]:
        """执行聚类分析算法"""
        if not self.clustering_matcher or not external_pool:
            return []
        
        try:
            # 更新检查时间
            self.clustering_stats['last_clustering_check'] = time.time()
            
            # 将外部未匹配池的事件添加到聚类分析器
            for event_record in external_pool:
                if not event_record.get('clustering_processed', False):
                    event_data = event_record['event_data']
                    category_result = event_record.get('category_result')
                    
                    if hasattr(self.clustering_matcher, 'add_unmatched_event'):
                        self.clustering_matcher.add_unmatched_event(event_data, category_result)
                        event_record['clustering_processed'] = True
            
            # 执行聚类分析
            if hasattr(self.clustering_matcher, 'perform_clustering'):
                clusters_formed = self.clustering_matcher.perform_clustering()
                
                if clusters_formed:
                    print(f"   📊 聚类分析完成: 形成 {len(clusters_formed)} 个簇")
                    
                    # 🔥🔥🔥 修复：正确更新 clusters_formed 统计 🔥🔥🔥
                    # 这是累加，不是重置！
                    self.clustering_stats['clusters_formed'] += len(clusters_formed)
                    print(f"   📈 更新统计: clusters_formed = {self.clustering_stats['clusters_formed']}")
                    
                    # 获取新题材候选
                    if hasattr(self.clustering_matcher, 'get_new_theme_candidates'):
                        candidates = self.clustering_matcher.get_new_theme_candidates(min_quality=0.4)
                        return candidates
            
            return []
            
        except Exception as e:
            print(f"❌ 聚类分析失败: {e}")
            return []
    
    def create_theme_for_major_event(self, event_data: Dict) -> Dict:
        """
        为Major事件创建题材 - 纯算法处理
        返回算法生成的题材数据，不处理数据库存储
        """
        event_id = event_data.get('event_id', 'unknown')
        event_type = event_data.get('event_type', 'normal')
        
        print(f"\n🏭 算法创建题材: {event_id}")
        
        # 验证必须是Major事件
        if event_type != 'major':
            return {
                'status': 'error',
                'error': f'只有Major事件才能创建题材，当前类型: {event_type}',
                'event_id': event_id,
                'event_type': event_type
            }
        
        # 验证主题数据生成器
        if not self.theme_data_generator:
            print(f"   ❌ 主题生成器未初始化")
            return {
                'status': 'error',
                'error': '主题生成器未初始化',
                'event_id': event_id
            }
        
        try:
            # 获取AI分析
            ai_analysis = event_data.get('ai_analysis', {})
            
            # 执行AI分类推断
            ai_category_result = None
            if ai_analysis and hasattr(self.major_matcher, 'infer_category_from_ai_keywords'):
                try:
                    ai_category_result = self.major_matcher.infer_category_from_ai_keywords(ai_analysis)
                except Exception as e:
                    print(f"   ⚠️  AI分类推断失败: {e}")
                    ai_category_result = None
            
            # 构建分类结果
            classification_result = {
                'themes': [],
                'ai_category_inference': ai_category_result,
                'confidence': ai_analysis.get('concept_confidence', 0.7) if ai_analysis else 0.5,
                'matched': False
            }
            
            # ✅ 调用生成器（算法生成）
            new_theme = self.theme_data_generator.generate_for_major_event(
                event_data, classification_result
            )
            
            if new_theme:
                print(f"   ✅ 算法生成成功: {new_theme.name}")
                
                # 转换新题材数据
                if hasattr(new_theme, 'to_dict'):
                    new_theme_dict = new_theme.to_dict()
                elif hasattr(new_theme, '__dict__'):
                    new_theme_dict = new_theme.__dict__
                else:
                    new_theme_dict = {'name': str(new_theme)}
                
                # 🔥 添加匹配器类型信息
                new_theme_dict['generated_by'] = 'Transformer语义匹配引擎'
                new_theme_dict['matcher_type'] = self._get_matcher_type(self.major_matcher)
                
                return {
                    'status': 'success',
                    'event_id': event_id,
                    'new_theme_created': True,
                    'new_theme': new_theme_dict,
                    'ai_category_inference': ai_category_result,
                    'creation_method': 'major_event_algorithm'
                }
            else:
                print(f"   ❌ 主题生成器返回空结果")
                return {
                    'status': 'error',
                    'error': '无法生成题材数据',
                    'event_id': event_id
                }
                
        except Exception as e:
            print(f"❌ 算法创建失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'error': str(e),
                'event_id': event_id
            }
    
    def force_create_theme_for_major(self, event_data: Dict) -> Dict:
        """
        强制为Major事件创建题材（向后兼容）
        ✅ 调用统一的创建入口
        """
        print(f"🚨 [兼容方法] 强制为Major事件创建题材: {event_data.get('event_id')}")
        return self.create_theme_for_major_event(event_data)
    
    def get_engine_status(self) -> Dict:
        """获取引擎状态 - 纯算法版"""
        try:
            algorithms = {
                'major': {
                    'name': 'Major算法',
                    'type': self._get_matcher_type(self.major_matcher),
                    'available': bool(self.major_matcher),
                    'initialized': bool(self.major_matcher and hasattr(self.major_matcher, 'initialized') and self.major_matcher.initialized)
                },
                'normal': {
                    'name': 'Normal算法',
                    'type': self._get_matcher_type(self.normal_matcher),
                    'available': bool(self.normal_matcher),
                    'initialized': bool(self.normal_matcher and hasattr(self.normal_matcher, 'initialized') and self.normal_matcher.initialized)
                }
            }
            
            # 🔥 新增：聚类分析状态
            if self.enable_clustering:
                algorithms['clustering'] = {
                    'name': '聚类分析算法',
                    'type': '聚类分析',
                    'available': bool(self.clustering_matcher),
                    'enabled': self.enable_clustering,
                    'stats': self.clustering_stats
                }
            
            # 如果算法实例有更多信息，添加到字典中
            if self.major_matcher:
                # Transformer特有信息
                if hasattr(self.major_matcher, 'model_name'):
                    algorithms['major']['model'] = self.major_matcher.model_name
                
                if hasattr(self.major_matcher, 'get_algorithm_info'):
                    try:
                        major_info = self.major_matcher.get_algorithm_info()
                        if major_info:
                            algorithms['major'].update(major_info)
                    except Exception:
                        pass
            
            if self.normal_matcher:
                # Transformer特有信息
                if hasattr(self.normal_matcher, 'model_name'):
                    algorithms['normal']['model'] = self.normal_matcher.model_name
                
                if hasattr(self.normal_matcher, 'get_algorithm_info'):
                    try:
                        normal_info = self.normal_matcher.get_algorithm_info()
                        if normal_info:
                            algorithms['normal'].update(normal_info)
                    except Exception:
                        pass
            
            if self.enable_clustering and self.clustering_matcher and hasattr(self.clustering_matcher, 'get_algorithm_info'):
                try:
                    clustering_info = self.clustering_matcher.get_algorithm_info()
                    if clustering_info:
                        algorithms['clustering'].update(clustering_info)
                except Exception:
                    pass
                    
        except Exception as e:
            # 如果构建失败，返回最小信息
            algorithms = {
                'major': {
                    'name': 'Major算法', 
                    'type': self._get_matcher_type(self.major_matcher),
                    'error': str(e)
                },
                'normal': {
                    'name': 'Normal算法', 
                    'type': self._get_matcher_type(self.normal_matcher),
                    'error': str(e)
                },
                'clustering': {
                    'name': '聚类分析算法', 
                    'enabled': self.enable_clustering, 
                    'error': str(e)
                }
            }
        
        return {
            'version': '4.0.0',
            'engine_type': 'pure_algorithm_with_transformer',
            'data_loaded': self.data_loaded,
            'themes_count': self.current_themes_count,
            'categories_count': self.current_categories_count,
            'algorithms': algorithms,
            'clustering_enabled': self.enable_clustering,
            'transformer_enabled': self.enable_transformer,
            'clustering_stats': self.clustering_stats,
            'theme_generator_ready': bool(self.theme_data_generator),
            'engine_initialized': True,
            'timestamp': time.time()
        }
    
    # 🔥 新增方法：获取算法建议
    def get_algorithm_suggestions(self, event_data: Dict) -> Dict:
        """获取算法建议（不执行存储）"""
        result = self.discover(event_data)
        
        suggestions = {
            'event_id': event_data.get('event_id'),
            'matched': result.get('matched', False),
            'suggested_themes': result.get('themes', []),
            'should_create_theme': result.get('should_create_theme', False),
            'algorithm_reason': result.get('create_reason', ''),
            'matcher_type': result.get('matcher_type', 'unknown')
        }
        
        if result.get('ai_category_inference'):
            suggestions['ai_category_suggestion'] = result['ai_category_inference']
        
        return suggestions
    
    # 🔥 新增方法：手动触发聚类分析
    def trigger_clustering_analysis(self, external_pool: List, auto_create: bool = True, 
                          min_confidence: float = 0.7) -> Dict:
        """
        手动触发聚类分析，可选自动创建
        
        Args:
            external_pool: 外部未匹配池
            auto_create: 是否自动创建题材（默认True）
            min_confidence: 自动创建的最小置信度（默认0.7）
        
        Returns:
            Dict: 聚类分析结果
        """
        if not self.enable_clustering:
            return {"status": "error", "message": "聚类分析未启用"}
        
        print("🔍 手动触发聚类分析...")
        
        # 执行聚类分析
        new_candidates = self._perform_clustering_analysis(external_pool)
        
        result = {
            "status": "success",
            "clustering_time": datetime.now().isoformat(),
            "new_candidates_found": len(new_candidates),
            "algorithm_processed": True
        }
        
        if new_candidates:
            result["new_theme_candidates"] = new_candidates
            
            # 显示前3个候选
            for candidate in new_candidates[:3]:
                result.setdefault("sample_candidates", []).append({
                    "name": candidate.get('name'),
                    "confidence": candidate.get('confidence_score', 0),
                    "description": candidate.get('description', '')[:50]
                })
            
            # 🔥 如果启用自动创建，则创建高质量题材
            if auto_create and new_candidates:
                print(f"   🤖 尝试自动创建高质量题材（置信度≥{min_confidence}）...")
                
                creation_result = self.auto_create_themes_from_clustering(min_confidence)  # 移除await
                
                if creation_result['status'] == 'success':
                    created_count = creation_result.get('created_count', 0)
                    result['auto_creation'] = {
                        'enabled': True,
                        'status': 'success',
                        'themes_created': created_count,
                        'min_confidence_used': min_confidence
                    }
                    
                    if created_count > 0:
                        result['created_themes'] = creation_result.get('themes', [])
                        print(f"   ✅ 自动创建 {created_count} 个题材")
                    else:
                        print(f"   ⚠️  未发现符合条件的候选进行自动创建")
                else:
                    result['auto_creation'] = {
                        'enabled': True,
                        'status': 'failed',
                        'error': creation_result.get('message', '未知错误')
                    }
                    print(f"   ❌ 自动创建失败: {creation_result.get('message')}")
        
        print(f"📊 聚类分析结果: 发现 {len(new_candidates)} 个候选")
        return result
    
    def auto_create_themes_from_clustering(self, min_confidence: float = 0.7) -> Dict:
        """
        从聚类分析结果自动创建题材
        
        Args:
            min_confidence: 最小置信度阈值（默认0.7，高质量）
        
        Returns:
            Dict: 创建结果
        """
        print(f"🤖 从聚类分析自动创建题材...")
        
        if not self.enable_clustering or not self.clustering_matcher:
            return {
                'status': 'error',
                'message': '聚类分析未启用',
                'created_count': 0,
                'themes': []
            }
        
        # 验证主题数据生成器
        if not self.theme_data_generator:
            print(f"   ❌ 主题生成器未初始化")
            return {
                'status': 'error',
                'message': '主题生成器未初始化',
                'created_count': 0,
                'themes': []
            }
        
        try:
            # 1. 获取聚类候选
            candidates = []
            if hasattr(self.clustering_matcher, 'get_new_theme_candidates'):
                candidates = self.clustering_matcher.get_new_theme_candidates(min_quality=min_confidence)
            
            if not candidates:
                print(f"   ⚠️  未发现符合条件（置信度≥{min_confidence}）的聚类候选")
                return {
                    'status': 'success',
                    'message': f'未发现符合条件的聚类候选（阈值: {min_confidence}）',
                    'created_count': 0,
                    'themes': []
                }
            
            print(f"   🎯 发现 {len(candidates)} 个高质量聚类候选（置信度≥{min_confidence}）")
            
            # 2. 为每个候选创建题材
            created_themes = []
            failed_candidates = []
            
            for candidate in candidates:
                candidate_name = candidate.get('name', '未知')
                candidate_confidence = candidate.get('confidence_score', 0)
                
                print(f"   🔥 处理聚类候选: {candidate_name} (置信度: {candidate_confidence:.2f})")
                
                # 构建模拟Major事件数据
                event_data = self._build_event_data_from_clustering_candidate(candidate)
                
                # 构建分类结果
                classification_result = self._build_classification_result_from_candidate(candidate)
                
                # 生成新题材数据
                print(f"   🛠️  生成题材数据...")
                new_theme = self.theme_data_generator.generate_for_major_event(
                    event_data, 
                    classification_result,
                    theme_type='concept'  # 聚类发现的通常是概念题材
                )
                
                if new_theme:
                    # 添加到结果列表
                    theme_dict = new_theme.to_dict() if hasattr(new_theme, 'to_dict') else new_theme.__dict__
                    
                    # 添加聚类相关信息
                    if 'metadata' not in theme_dict:
                        theme_dict['metadata'] = {}
                    
                    theme_dict['metadata']['clustering_source'] = True
                    theme_dict['metadata']['cluster_candidate_name'] = candidate_name
                    theme_dict['metadata']['cluster_confidence'] = candidate_confidence
                    
                    created_themes.append(theme_dict)
                    
                    print(f"   ✅ 创建成功: {new_theme.name}")
                    
                    # 记录到聚类统计
                    self.clustering_stats['themes_created'] = self.clustering_stats.get('themes_created', 0) + 1
                else:
                    print(f"   ❌ 创建失败: 主题生成器返回空结果")
                    failed_candidates.append(candidate_name)
            
            # 3. 返回结果
            result = {
                'status': 'success',
                'message': f'从聚类候选自动创建 {len(created_themes)} 个题材',
                'created_count': len(created_themes),
                'failed_count': len(failed_candidates),
                'themes': created_themes,
                'clustering_candidates_processed': len(candidates),
                'min_confidence_threshold': min_confidence,
                'timestamp': datetime.now().isoformat()
            }
            
            if failed_candidates:
                result['failed_candidates'] = failed_candidates
            
            print(f"   📊 自动创建完成: 成功 {len(created_themes)}/{len(candidates)} 个")
            
            return result
            
        except Exception as e:
            print(f"❌ 自动创建失败: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'error',
                'message': f'自动创建失败: {str(e)}',
                'created_count': 0,
                'themes': [],
                'error': str(e)
            }

    def _build_event_data_from_clustering_candidate(self, candidate: Dict) -> Dict:
        """
        从聚类候选构建模拟Major事件数据
        
        Args:
            candidate: 聚类候选对象，包含以下字段：
                - name: 候选名称
                - description: 描述（可选）
                - confidence_score: 置信度
                - metadata: 元数据，包含core_keywords, cluster_id, cluster_size等
        
        Returns:
            Dict: 模拟Major事件数据
        """
        try:
            # 提取候选信息
            candidate_name = candidate.get('name', '聚类发现主题')
            description = candidate.get('description', '')
            confidence_score = candidate.get('confidence_score', 0.7)
            
            # 提取元数据
            metadata = candidate.get('metadata', {})
            core_keywords = metadata.get('core_keywords', [])
            cluster_id = metadata.get('cluster_id', f'cluster_{int(time.time())}')
            cluster_size = metadata.get('cluster_size', 1)
            
            # 如果没有描述，生成默认描述
            if not description:
                keyword_summary = '、'.join(core_keywords[:3]) if core_keywords else candidate_name
                description = f'基于聚类分析发现的{candidate_name}相关事件集群，共{cluster_size}个相关事件，主要涉及{keyword_summary}'
            
            # 确定影响力级别
            if confidence_score >= 0.8:
                impact_level = 'high'
                impact_desc = '高影响力'
            elif confidence_score >= 0.6:
                impact_level = 'medium'
                impact_desc = '中等影响力'
            else:
                impact_level = 'low'
                impact_desc = '低影响力'
            
            # 构建事件数据
            event_data = {
                'event_id': f"clustering_auto_{cluster_id}_{int(time.time())}",
                'event_type': 'major',  # 标记为Major事件，以便创建
                'event_subtype': '技术突破',
                'title': f"聚类发现: {candidate_name}",
                'content': description,
                'core_concept': candidate_name,
                'industry_keywords': core_keywords,
                'ai_analysis': {
                    'core_concept': candidate_name,
                    'concept_confidence': confidence_score,
                    'industry_keywords': core_keywords,
                    'impact_level': impact_level,
                    'impact_description': f'聚类发现{candidate_name}，置信度{confidence_score:.2f}，{impact_desc}',
                    'summary': description[:100] + '...' if len(description) > 100 else description
                },
                'metadata': {
                    'clustering_source': True,
                    'cluster_id': cluster_id,
                    'cluster_size': cluster_size,
                    'cluster_quality': confidence_score,
                    'core_keywords': core_keywords,
                    'creation_method': 'clustering_auto_creation',
                    'auto_created_timestamp': datetime.now().isoformat(),
                    'quality_assessment': f'高质量聚类，置信度{confidence_score:.2f}'
                },
                'publish_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': '聚类分析引擎'
            }
            
            # 记录日志
            logger.info(f"✅ 构建聚类候选事件数据: {candidate_name} (置信度: {confidence_score:.2f}, 簇大小: {cluster_size})")
            
            return event_data
            
        except Exception as e:
            # 如果构建失败，返回最小事件数据
            logger.error(f"❌ 构建聚类候选事件数据失败: {e}")
            
            return {
                'event_id': f"clustering_error_{int(time.time())}",
                'event_type': 'major',
                'title': '聚类发现主题',
                'content': '基于聚类分析发现的潜在主题',
                'ai_analysis': {
                    'core_concept': '聚类发现',
                    'concept_confidence': 0.7,
                    'industry_keywords': [],
                    'impact_level': 'medium'
                },
                'metadata': {
                    'clustering_source': True,
                    'creation_method': 'clustering_auto_creation',
                    'error_in_building': str(e),
                    'auto_created_timestamp': datetime.now().isoformat()
                }
            }

    def _build_classification_result_from_candidate(self, candidate: Dict) -> Dict:
        """从聚类候选构建分类结果"""
        # 尝试从候选数据中获取分类信息
        level1_category = candidate.get('level1_category', '')
        level2_category = candidate.get('level2_category', '')
        
        classification_result = {
            'themes': [],
            'matched': False,
            'confidence': candidate.get('confidence_score', 0.7)
        }
        
        # 如果有分类信息，添加到AI推断结果
        if level1_category or level2_category:
            classification_result['ai_category_inference'] = {
                'matched': True,
                'level1_category': level1_category,
                'level2_category': level2_category,
                'theme_type': 'concept'
            }
        
        return classification_result
    
    async def infer_category(self, event_data: Dict) -> Dict:
        """
        第一阶段：分类推断 - 完整修复版
        """
        print(f"🔍 第一阶段：分类推断")
        start_time = time.time()
        
        try:
            if not self.data_loaded:
                return {'matched': False, 'error': '引擎数据未加载'}
            
            event_id = event_data.get('event_id', 'unknown')
            print(f"   事件ID: {event_id}")
            
            if not hasattr(self.major_matcher, 'initialized') or not self.major_matcher.initialized:
                return {
                    'matched': False,
                    'reason': 'major_matcher_not_initialized',
                    'category_info': {'theme_type': 'concept'}
                }
            
            # 检查是否有AI分析
            ai_analysis = event_data.get('ai_analysis', {})
            
            if ai_analysis and hasattr(self.major_matcher, 'infer_category_from_ai_keywords'):
                print(f"   使用AI关键词进行分类推断")
                algorithm_result = self.major_matcher.infer_category_from_ai_keywords(ai_analysis)
                
                # 🔥 修复：处理不同的返回格式
                print(f"   算法结果类型: {type(algorithm_result)}")
                print(f"   算法结果: {algorithm_result}")
                
                # 检查是否是匹配成功的格式
                if isinstance(algorithm_result, dict):
                    # 格式1：新格式（有best_category字段且不为空）
                    if 'best_category' in algorithm_result and algorithm_result.get('best_category'):
                        best_category = algorithm_result.get('best_category')
                        best_score = algorithm_result.get('best_score', 0)
                        matched_keywords = algorithm_result.get('matched_keywords', [])
                        algorithm_used = algorithm_result.get('algorithm_used', 'ai_keyword_classification')
                        
                        print(f"   使用新格式，提取信息: 分类ID={best_category}, 分数={best_score:.3f}")
                    
                    # 格式2：旧格式（有matched字段且为True）
                    elif algorithm_result.get('matched', False):
                        # 🔥 关键修复：正确处理旧格式的分类ID提取
                        best_score = algorithm_result.get('match_confidence', 0)
                        matched_keywords = algorithm_result.get('matched_keywords', [])
                        algorithm_used = 'ai_keyword_classification'
                        
                        # 🔥 修复：优先尝试所有可能的分类代码字段
                        possible_id_fields = [
                            'best_category',      # 新格式字段
                            'level1_code',        # 一级分类代码
                            'level2_code',        # 二级分类代码  
                            'category_code',      # 通用分类代码
                            'code'                # 简单代码字段
                        ]
                        
                        best_category = None
                        for field in possible_id_fields:
                            candidate = algorithm_result.get(field)
                            if candidate and candidate != '':
                                best_category = candidate
                                print(f"   从字段 '{field}' 获取分类ID: {best_category}")
                                break
                        
                        # 🔥 如果以上字段都没有有效值，使用level1_category
                        if not best_category or best_category == '':
                            level1_category = algorithm_result.get('level1_category')
                            if level1_category and level1_category != '':
                                # 为概念题材生成一个ID
                                if algorithm_result.get('theme_type') == 'concept':
                                    import hashlib
                                    category_hash = hashlib.md5(level1_category.encode()).hexdigest()[:8].upper()
                                    best_category = f"CONCEPT_{category_hash}"
                                    print(f"   概念题材生成ID: {best_category} from {level1_category}")
                                else:
                                    best_category = level1_category
                                    print(f"   使用分类名称作为ID: {best_category}")
                        
                        # 🔥 最后的安全检查
                        if not best_category or best_category == '':
                            print(f"   ⚠️  警告：无法从结果中提取有效分类ID")
                            best_category = "UNKNOWN_CATEGORY"
                        
                        print(f"   使用旧格式，提取信息: 分类ID={best_category}, 分数={best_score:.3f}")
                        
                        # 🔥 调试信息：显示所有可用字段
                        print(f"   🔍 结果可用字段: {list(algorithm_result.keys())}")
                        for key, value in algorithm_result.items():
                            if value and key not in ['matched_keywords']:
                                print(f"     - {key}: {value}")
                    
                    # 格式3：未匹配格式
                    else:
                        best_category = None
                        best_score = algorithm_result.get('best_score', 0.0)
                        matched_keywords = algorithm_result.get('matched_keywords', [])
                        algorithm_used = algorithm_result.get('algorithm_used', 'ai_keyword_classification')
                        
                        print(f"   算法返回未匹配结果，分数={best_score:.3f}")
                else:
                    # 非字典格式结果
                    print(f"   ⚠️  警告：算法返回非字典格式结果: {type(algorithm_result)}")
                    best_category = None
                    best_score = 0.0
                    matched_keywords = []
                    algorithm_used = 'unknown_format'
            else:
                # 如果没有AI分析，使用match方法
                print(f"   使用match方法进行分类推断")
                matches = self.major_matcher.match(event_data, precision='category')
                
                # 过滤出分类结果
                category_matches = [
                    match for match in matches 
                    if hasattr(match, 'match_details') and 
                    match.match_details.get('data_type') == 'category'
                ]
                
                if category_matches:
                    best_match = category_matches[0]
                    best_category = best_match.theme_id
                    best_score = best_match.confidence
                    matched_keywords = best_match.matched_keywords
                    algorithm_used = 'keyword_classification_via_match'
                    print(f"   从match方法获取分类: {best_category}, 分数={best_score:.3f}")
                else:
                    best_category = None
                    best_score = 0.0
                    matched_keywords = []
                    algorithm_used = 'keyword_classification_via_match'
                    print(f"   match方法未找到分类")
            
            # 🔥 业务逻辑：应用阈值
            category_threshold = 0.3
            
            processing_time = (time.time() - start_time) * 1000
            
            print(f"   分类推断结果: 最佳分类={best_category}, 分数={best_score:.3f}")
            
            # 🔥 修复：检查best_category是否有效（不为空且不是None）
            is_valid_category = bool(best_category and best_category != '' and best_category != 'UNKNOWN_CATEGORY')
            
            if best_score >= category_threshold and is_valid_category:
                # 获取分类详细信息
                category_info = self._get_category_info(best_category)
                
                # 🔥 如果_get_category_info返回None，使用算法结果中的信息
                if not category_info or category_info.get('error'):
                    print(f"   ⚠️  无法获取分类{best_category}的详细信息，使用算法结果")
                    category_info = {
                        'category_id': best_category,
                        'category_name': algorithm_result.get('level1_category', best_category) if algorithm_result else best_category,
                        'theme_type': algorithm_result.get('theme_type', 'investment') if algorithm_result else 'investment',
                        'category_level': algorithm_result.get('category_level', 1) if algorithm_result else 1,
                        'is_fallback_info': True
                    }
                
                result = {
                    'matched': True,
                    'category_info': {
                        **category_info,
                        'confidence': best_score,
                        'matched_keywords': matched_keywords,
                        'original_score': best_score
                    },
                    'confidence': best_score,
                    'algorithm_used': algorithm_used,
                    'processing_time_ms': round(processing_time, 2)
                }
                
                print(f"   ✅ 分类推断成功: {category_info.get('category_name', best_category)}")
                return result
            else:
                # 未匹配到有效分类，返回概念题材
                if best_score >= category_threshold and not is_valid_category:
                    print(f"   ⚠️  分类分数达标({best_score:.3f}≥{category_threshold})但分类ID无效({best_category})")
                elif best_score < category_threshold and is_valid_category:
                    print(f"   ⚠️  分类ID有效({best_category})但分数不足({best_score:.3f}<{category_threshold})")
                elif best_score < category_threshold and not is_valid_category:
                    print(f"   ⚠️  分类分数不足且ID无效: {best_score:.3f}<{category_threshold}, ID={best_category}")
                
                result = {
                    'matched': False,
                    'category_info': {
                        'theme_type': 'concept',
                        'level1_category': '概念题材',
                        'level2_category': '新兴概念',
                        'reason': f'below_threshold_{category_threshold}' if best_score < category_threshold else 'invalid_category_id'
                    },
                    'confidence': best_score,
                    'algorithm_used': algorithm_used,
                    'processing_time_ms': round(processing_time, 2)
                }
                
                print(f"   ⚠️  未找到有效分类")
                
                return result
                
        except Exception as e:
            print(f"❌ 分类推断失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'matched': False,
                'error': str(e),
                'algorithm_used': 'error',
                'category_info': {
                    'theme_type': 'concept',
                    'level1_category': '概念题材',
                    'level2_category': '错误处理'
                }
            }


    async def match_with_themes(self, event_data: Dict, themes: List[Dict], 
                                        event_type: str, threshold: float) -> Dict:
        print(f"   🔄 使用match_with_themes方法进行题材匹配")
        
        try:
            # 方案1：使用match方法，但需要先临时初始化一个TransformerMatcher
            from theme_service.matchers.matcher_factory import MatcherFactory
            
            # 创建临时TransformerMatcher，只加载题材数据
            temp_config = {
                'model_name': 'bert-base-chinese',
                'semantic_threshold': threshold,
                'keyword_threshold': threshold - 0.1,  # 关键词阈值略低
                'max_results': 10,
                'min_keyword_matches': 2,
                'fallback_to_keyword': True
            }
            
            temp_matcher = MatcherFactory.create_matcher('transformer', temp_config)
            
            # 只初始化题材数据，分类数据为空
            temp_matcher.initialize(themes, [])
            
            # 执行匹配
            matches = temp_matcher.match(event_data, precision=event_type)
            
            # 过滤通过阈值的结果
            filtered_matches = [match for match in matches if match.confidence >= threshold]
            
            # 转换为业务格式
            match_results = []
            for match in filtered_matches:
                match_results.append({
                    'theme_id': match.theme_id,
                    'theme_name': match.theme_name,
                    'confidence': match.confidence,
                    'matched_keywords': match.matched_keywords,
                    'match_type': match.match_type,
                    'algorithm_used': 'transformer_matching_fallback'
                })
            
            match_results.sort(key=lambda x: x['confidence'], reverse=True)
            
            if match_results:
                return {
                    'matched': True,
                    'themes': match_results,
                    'theme_count': len(match_results),
                    'confidence': match_results[0]['confidence'] if match_results else 0,
                    'threshold_used': threshold,
                    'algorithm_used': 'transformer_matching_fallback',
                    'fallback_used': True
                }
            else:
                return {
                    'matched': False,
                    'themes': [],
                    'theme_count': 0,
                    'confidence': 0.0,
                    'threshold_used': threshold,
                    'algorithm_used': 'transformer_matching_fallback',
                    'fallback_used': True,
                    'reason': 'below_threshold'
                }
                
        except Exception as e:
            print(f"   ❌ 回退方案失败: {e}")
            
            # 如果Transformer失败，尝试回退到关键词匹配
            try:
                from theme_service.matchers.matcher_factory import MatcherFactory
                
                temp_config = {
                    'match_threshold': threshold,
                    'max_results': 10,
                    'min_keyword_matches': 2
                }
                
                temp_matcher = MatcherFactory.create_matcher('keyword', temp_config)
                temp_matcher.initialize(themes, [])
                matches = temp_matcher.match(event_data, precision=event_type)
                filtered_matches = [match for match in matches if match.confidence >= threshold]
                
                match_results = []
                for match in filtered_matches:
                    match_results.append({
                        'theme_id': match.theme_id,
                        'theme_name': match.theme_name,
                        'confidence': match.confidence,
                        'matched_keywords': match.matched_keywords,
                        'match_type': match.match_type,
                        'algorithm_used': 'keyword_matching_emergency_fallback'
                    })
                
                match_results.sort(key=lambda x: x['confidence'], reverse=True)
                
                if match_results:
                    return {
                        'matched': True,
                        'themes': match_results,
                        'theme_count': len(match_results),
                        'confidence': match_results[0]['confidence'] if match_results else 0,
                        'threshold_used': threshold,
                        'algorithm_used': 'keyword_matching_emergency_fallback',
                        'fallback_used': True
                    }
                else:
                    return {
                        'matched': False,
                        'themes': [],
                        'theme_count': 0,
                        'confidence': 0.0,
                        'threshold_used': threshold,
                        'algorithm_used': 'keyword_matching_emergency_fallback',
                        'fallback_used': True,
                        'reason': 'below_threshold'
                    }
            except Exception as e2:
                print(f"   ❌ 紧急回退方案也失败: {e2}")
                return {
                    'matched': False,
                    'error': f'所有回退方案失败: {str(e)}; {str(e2)}',
                    'algorithm_used': 'error_fallback'
                }

    def _get_category_info(self, category_id: str) -> Dict:
        """获取分类详细信息（增强修复版）"""
        print(f"   🔍 获取分类信息: {category_id}")
        
        category = None
        
        # 1. 首先尝试从major_matcher获取
        if hasattr(self, 'major_matcher') and hasattr(self.major_matcher, 'categories'):
            print(f"     检查major_matcher.categories (数量: {len(self.major_matcher.categories)})")
            if category_id in self.major_matcher.categories:
                category = self.major_matcher.categories[category_id]
                print(f"     在major_matcher中找到分类: {category.get('category_name', '未知')}")
        
        # 2. 然后尝试从normal_matcher获取
        if category is None and hasattr(self, 'normal_matcher') and hasattr(self.normal_matcher, 'categories'):
            print(f"     检查normal_matcher.categories (数量: {len(self.normal_matcher.categories)})")
            if category_id in self.normal_matcher.categories:
                category = self.normal_matcher.categories[category_id]
                print(f"     在normal_matcher中找到分类: {category.get('category_name', '未知')}")
        
        # 3. 最后尝试从引擎存储的数据获取
        if category is None and hasattr(self, 'categories_data'):
            print(f"     检查categories_data (数量: {len(self.categories_data)})")
            if category_id in self.categories_data:
                category = self.categories_data[category_id]
                print(f"     在categories_data中找到分类: {category.get('category_name', '未知')}")
            else:
                # 尝试使用不同的键查找
                print(f"     直接查找失败，尝试搜索所有分类...")
                for cat_id, cat_data in self.categories_data.items():
                    if cat_id == category_id or cat_data.get('category_code') == category_id:
                        category = cat_data
                        print(f"     找到匹配分类: {cat_data.get('category_name', '未知')}")
                        break
        
        if category is None:
            print(f"   ⚠️  未找到分类ID: {category_id}")
            # 返回默认信息
            return {
                'category_id': category_id,
                'category_code': category_id,
                'category_name': f'未知分类({category_id})',
                'category_level': 1,
                'parent_code': '',
                'level1_category': '',
                'level2_category': '',
                'level3_category': ''
            }
        
        # 返回完整信息
        return {
            'category_id': category_id,
            'category_code': category.get('category_code', category_id),
            'category_name': category.get('category_name', '未知分类'),
            'category_level': category.get('category_level', 1),
            'parent_code': category.get('parent_code', ''),
            'level1_category': category.get('level1_category', ''),
            'level2_category': category.get('level2_category', ''),
            'level3_category': category.get('level3_category', '')
        }
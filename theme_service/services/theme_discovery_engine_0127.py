"""
主题发现引擎 - 业务逻辑处理
处理Major/Normal事件逻辑、候选池管理、算法调度
专注于题材匹配、发现和新题材创建业务
"""
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..matchers.matcher_factory import MatcherFactory
from ..matchers.base_matcher import BaseMatcher, MatchResult
from .candidate_pool import CandidatePool, Candidate

class ThemeDiscoveryEngine:
    """主题发现引擎 - 核心业务逻辑"""
    
    def __init__(self):
        """
        初始化主题发现引擎
        创建算法实例，但不初始化数据
        """
        print("🚀 初始化主题发现引擎...")
        
        try:
            # 1. 初始化候选池
            self.candidate_pool = CandidatePool(
                max_size=100,
                ttl_hours=24
            )
            
            # 2. 创建算法实例（无数据状态）
            print("   🔧 创建算法实例...")
            major_config = {
                'match_threshold': 0.6,
                'max_results': 10,
                'min_keyword_matches': 2,
                'enable_analyst_logic': True,
                'classification_first': True,
                'use_ai_keywords_first': True,
                'enable_category_inference': True
            }
            normal_config = {
                'match_threshold': 0.5,
                'max_results': 15,
                'min_keyword_matches': 2,
                'enable_analyst_logic': False,
                'classification_first': False
            }

            self.major_matcher = MatcherFactory.create_matcher('keyword', major_config)
            self.normal_matcher = MatcherFactory.create_matcher('keyword', normal_config)
            
            # ✅ 修改：安全地获取算法信息
            print("✅ 主题发现引擎初始化完成")
            
            try:
                major_info = self.major_matcher.get_algorithm_info()
                normal_info = self.normal_matcher.get_algorithm_info()
                print(f"   Major算法: {major_info.get('name', 'Unknown')}")
                print(f"   Normal算法: {normal_info.get('name', 'Unknown')}")
            except Exception as e:
                print(f"   ⚠️  获取算法信息失败: {e}")
                print(f"   已创建算法实例，但信息获取失败")
            
            # 3. 初始化标志和数据
            self.data_loaded = False
            self.current_themes_count = 0
            self.current_categories_count = 0
            self.theme_data_generator = None
            
        except Exception as e:
            print(f"❌ 主题发现引擎初始化失败: {e}")
            raise
    
    def load_data(self, themes: List[Dict], categories: List[Dict] = None) -> bool:
        """
        加载题材和分类数据
        
        Args:
            themes: 题材数据列表
            categories: 分类数据列表（可选）
            
        Returns:
            是否加载成功
        """
        print(f"📥 加载数据到引擎...")
        print(f"   题材数据: {len(themes)} 个")
        print(f"   分类数据: {len(categories) if categories else 0} 个")
        
        try:
            # 保存数据计数
            self.current_themes_count = len(themes)
            self.current_categories_count = len(categories) if categories else 0
            
            # 初始化算法（传递数据库数据）
            print("   🔧 初始化Major算法...")
            try:
                self.major_matcher.initialize(themes, categories)
                print("   ✅ Major算法初始化成功")
            except Exception as e:
                print(f"   ❌ Major算法初始化失败: {e}")
                # 尝试使用默认配置重新初始化
                self.major_matcher.initialize(themes, [])
                print("   ✅ Major算法使用默认配置重新初始化")
            
            print("   🔧 初始化Normal算法...")
            try:
                self.normal_matcher.initialize(themes, categories)
                print("   ✅ Normal算法初始化成功")
            except Exception as e:
                print(f"   ❌ Normal算法初始化失败: {e}")
                # 尝试使用默认配置重新初始化
                self.normal_matcher.initialize(themes, [])
                print("   ✅ Normal算法使用默认配置重新初始化")
            
            self.data_loaded = True
            
            # 显示算法信息
            major_info = self.major_matcher.get_algorithm_info()
            normal_info = self.normal_matcher.get_algorithm_info()
            
            print(f"✅ 数据加载完成:")
            print(f"   Major算法: {major_info['name']} (版本: {major_info['version']})")
            print(f"   Normal算法: {normal_info['name']} (版本: {normal_info['version']})")
            print(f"   可用题材: {self.current_themes_count} 个")
            
            return True
            
        except Exception as e:
            print(f"❌ 数据加载失败: {e}")
            self.data_loaded = False
            return False
    
    def set_theme_data_generator(self, theme_data_generator):
        """设置题材数据生成器"""
        self.theme_data_generator = theme_data_generator
        print(f"✅ 设置题材数据生成器")
    
    def discover(self, event_data: Dict) -> Dict:
        """
        发现主题 - 核心业务逻辑
        
        Args:
            event_data: {
                'event_id': '事件ID',
                'event_type': 'major' 或 'normal',  # 由news_processor分类
                'title': '事件标题',
                'content': '事件内容',
                'keywords': ['关键词列表']  # 可选
                'ai_analysis': {AI分析数据}  # ✅ 新增：AI分析数据
            }
        
        Returns:
            发现结果
        """
        if not self.data_loaded:
            raise RuntimeError("请先调用 load_data() 加载数据")
        
        start_time = time.time()
        
        try:
            # 获取事件类型（已由news_processor分类）
            event_type = event_data.get('event_type', 'normal')
            
            print(f"\n🔍 发现主题开始:")
            print(f"   事件ID: {event_data.get('event_id', 'unknown')}")
            print(f"   事件类型: {event_type}")
            print(f"   标题: {event_data.get('title', '')[:50]}...")
            
            # ✅ 检查是否有AI分析
            ai_analysis = event_data.get('ai_analysis', {})
            if ai_analysis:
                print(f"   🤖 检测到AI分析: {ai_analysis.get('core_concept', '未知概念')}")
            
            # 根据事件类型选择处理方式
            if event_type == 'major':
                result = self._process_major_event(event_data)
            else:
                result = self._process_normal_event(event_data)
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # ✅ 构建返回结果 - 添加更多信息
            response = {
                'event_id': event_data.get('event_id', ''),
                'event_type': event_type,
                'matched': result['matched'],
                'theme_count': len(result['themes']),
                'themes': [match.to_dict() for match in result['themes']],
                'best_match': result['themes'][0].to_dict() if result['themes'] else None,
                'processing_path': result['processing_path'],
                'algorithm_used': result['algorithm_used'],
                'processing_time_ms': round(processing_time, 2),
                'confidence': result['confidence'],
                'error_message': None
            }
            
            # ✅ 添加AI分析信息
            if ai_analysis:
                response['ai_analysis_used'] = True
                response['ai_core_concept'] = ai_analysis.get('core_concept', '')
                response['ai_impact_level'] = ai_analysis.get('impact_level', 'medium')
            
            # ✅ 添加是否需要创建新题材的建议
            if not result['matched'] and event_type == 'major':
                response['should_create_theme'] = True
                response['create_reason'] = 'major_event_no_match'
                
                # ✅ 如果有AI分析，添加分类推断结果
                if ai_analysis and hasattr(self.major_matcher, 'infer_category_from_ai_keywords'):
                    try:
                        ai_category_result = self.major_matcher.infer_category_from_ai_keywords(ai_analysis)
                        response['ai_category_inference'] = ai_category_result
                        
                        # ✅ 如果有题材数据生成器，生成新题材数据
                        if self.theme_data_generator and ai_category_result:
                            # 构建分类结果供生成器使用
                            classification_result = {
                                'themes': result['themes'],
                                'ai_category_inference': ai_category_result,
                                'confidence': result['confidence'],
                                'matched': False
                            }
                            
                            new_theme = self.theme_data_generator.generate_for_major_event(
                                event_data, classification_result
                            )
                            
                            if new_theme:
                                response['new_theme_suggestion'] = new_theme.to_dict()
                                response['new_theme_ready'] = True
                                print(f"   🚀 已生成新题材数据: {new_theme.name}")
                    except Exception as e:
                        print(f"   ⚠️  AI分类推断失败: {e}")
                        response['ai_category_inference_error'] = str(e)
            
            return response
            
        except Exception as e:
            print(f"❌ 发现主题失败: {str(e)}")
            processing_time = (time.time() - start_time) * 1000
            
            return {
                'event_id': event_data.get('event_id', ''),
                'event_type': event_data.get('event_type', 'normal'),
                'matched': False,
                'theme_count': 0,
                'themes': [],
                'processing_path': 'error',
                'algorithm_used': 'none',
                'processing_time_ms': round(processing_time, 2),
                'confidence': 0.0,
                'error_message': str(e)
            }
    
    def _process_major_event(self, event_data: Dict) -> Dict:
        """处理Major事件 - 高精度匹配"""
        print("   使用Major算法进行高精度匹配...")
        
        # ✅ 检查是否有AI分析
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            print(f"   🤖 使用AI分析的关键词进行匹配")
            print(f"      核心概念: {ai_analysis.get('core_concept', '未知')}")
            print(f"      行业关键词: {len(ai_analysis.get('industry_keywords', []))} 个")
        
        # 调用Major算法匹配
        matches = self.major_matcher.match(event_data, precision='major')
        
        # ✅ 调整阈值：如果有AI分析，降低阈值要求
        if ai_analysis:
            major_threshold = 0.55  # AI分析时阈值更低
            print(f"   🤖 AI分析事件，使用较低阈值: {major_threshold}")
        else:
            major_threshold = 0.6
        
        filtered_matches = [match for match in matches if match.confidence >= major_threshold]
        
        if filtered_matches:
            print(f"   ✅ 匹配成功: {len(filtered_matches)} 个题材")
            best_match = filtered_matches[0]
            print(f"      最佳匹配: {best_match.theme_name} (置信度: {best_match.confidence:.3f})")
            
            return {
                'matched': True,
                'themes': filtered_matches,
                'processing_path': 'major→high_precision→success',
                'algorithm_used': self.major_matcher.get_algorithm_info()['name'],
                'confidence': best_match.confidence
            }
        else:
            # ✅ 关键修改：Major事件未匹配，必须确保能创建新题材
            print(f"   ⚠️  未匹配到足够信心的题材")
            print(f"   🚨 Major事件必须处理，尝试AI分类推断...")
            
            # ✅ 首先尝试AI分类推断
            ai_category_result = None
            if ai_analysis and hasattr(self.major_matcher, 'infer_category_from_ai_keywords'):
                try:
                    ai_category_result = self.major_matcher.infer_category_from_ai_keywords(ai_analysis)
                    print(f"   🤖 AI分类推断结果:")
                    print(f"      是否匹配: {ai_category_result.get('matched', False)}")
                    print(f"      分类: {ai_category_result.get('level1_category', '')} → {ai_category_result.get('level2_category', '')}")
                    print(f"      题材类型: {ai_category_result.get('theme_type', 'concept')}")
                except Exception as e:
                    print(f"   ⚠️  AI分类推断失败: {e}")
            
            # ✅ 添加到候选池（必须添加）
            should_add_to_pool = True
            
            if should_add_to_pool:
                # ✅ 修复：修改参数，避免使用不支持的 additional_info
                candidate_data = {
                    'ai_analysis': bool(ai_analysis),
                    'ai_category_result': ai_category_result,
                    'potential_matches': len(matches),
                    'match_score': matches[0].confidence if matches else 0.0
                }
                
                # ✅ 修改：将additional_info合并到event_data中
                event_data_with_metadata = event_data.copy()
                event_data_with_metadata['ai_analysis_metadata'] = {
                    'ai_category_result': ai_category_result,
                    'has_ai_analysis': bool(ai_analysis)
                }
                
                self.candidate_pool.add_candidate(
                    event_data_with_metadata,  # ✅ 使用包含metadata的事件数据
                    [match.to_dict() for match in matches[:3]] if matches else [],
                    match_score=matches[0].confidence if matches else 0.0,
                    processing_path='major→high_precision→candidate'
                )
                print(f"   📝 已添加到候选池 (AI分析: {'是' if ai_analysis else '否'})")
            
            # ✅ 构建返回结果，包含AI分类推断
            result = {
                'matched': False,
                'themes': matches[:5],  # 返回潜在匹配供参考
                'processing_path': 'major→high_precision→candidate',
                'algorithm_used': self.major_matcher.get_algorithm_info()['name'],
                'confidence': matches[0].confidence if matches else 0.0
            }
            
            # ✅ 添加AI分类推断结果
            if ai_category_result:
                result['ai_category_inference'] = ai_category_result
            
            return result
    
    def _process_normal_event(self, event_data: Dict) -> Dict:
        """处理Normal事件 - 中精度匹配"""
        print("   使用Normal算法进行中精度匹配...")
        
        # 调用Normal算法匹配
        matches = self.normal_matcher.match(event_data, precision='normal')
        
        # 应用Normal事件的中阈值
        normal_threshold = 0.4
        filtered_matches = [match for match in matches if match.confidence >= normal_threshold]
        
        if filtered_matches:
            print(f"   ✅ 匹配成功: {len(filtered_matches)} 个题材")
            return {
                'matched': True,
                'themes': filtered_matches,
                'processing_path': 'normal→medium_precision→success',
                'algorithm_used': self.normal_matcher.get_algorithm_info()['name'],
                'confidence': filtered_matches[0].confidence if filtered_matches else 0.0
            }
        else:
            # 未匹配到，选择性创建候选
            print(f"   ⚠️  未匹配到足够信心的题材")
            
            # 检查事件重要性
            event_importance = event_data.get('importance', 0)
            has_potential = event_data.get('has_potential_themes', False)
            
            content_length = len(event_data.get('content', '')) + len(event_data.get('title', ''))
            
            should_add_to_pool = (
                (matches and len(matches) >= 1) or
                event_importance >= 5 or
                content_length >= 100
            )
            
            if should_add_to_pool:
                self.candidate_pool.add_candidate(
                    event_data,
                    [match.to_dict() for match in matches[:5]] if matches else [],
                    match_score=matches[0].confidence if matches else 0.0,
                    processing_path='normal→medium_precision→candidate'
                )
                print(f"   添加到候选池 (条件: 重要性={event_importance}, 内容长度={content_length})")
            else:
                print(f"   未满足候选池条件 (重要性={event_importance}, 内容长度={content_length})")
            
            return {
                'matched': False,
                'themes': matches[:3],
                'processing_path': 'normal→medium_precision→candidate' if should_add_to_pool else 'normal→no_match',
                'algorithm_used': self.normal_matcher.get_algorithm_info()['name'],
                'confidence': matches[0].confidence if matches else 0.0
            }
    
    def force_create_theme_for_major(self, event_data: Dict) -> Dict:
        """
        强制为Major事件创建题材
        用于处理匹配失败但必须创建题材的情况
        """
        print(f"🚨 强制为Major事件创建题材: {event_data.get('event_id')}")
        
        try:
            # 获取AI分析
            ai_analysis = event_data.get('ai_analysis', {})
            
            # ✅ 关键修复：即使没有AI分析，也尝试创建
            if not ai_analysis:
                print(f"   ⚠️  Major事件缺少AI分析数据，尝试从标题创建概念")
                
                # 构建一个空的AI分析结构
                ai_analysis = {
                    'core_concept': event_data.get('title', '')[:20],
                    'industry_keywords': [],
                    'concept_confidence': 0.7,
                    'impact_level': 'medium'
                }
                event_data['ai_analysis'] = ai_analysis
            
            # 执行AI分类推断
            ai_category_result = None
            if hasattr(self.major_matcher, 'infer_category_from_ai_keywords'):
                ai_category_result = self.major_matcher.infer_category_from_ai_keywords(ai_analysis)
            
            # ✅ 修复：确保ai_category_result是有效的字典
            if not ai_category_result:
                ai_category_result = {
                    'matched': False,
                    'level1_category': '',
                    'level2_category': '',
                    'theme_type': 'concept',
                    'message': '无法推断分类'
                }
            
            print(f"   🔍 AI分类推断结果: {ai_category_result.get('matched', False)}")
            
            # 生成新题材数据
            if self.theme_data_generator:
                classification_result = {
                    'themes': [],
                    'ai_category_inference': ai_category_result,
                    'confidence': ai_analysis.get('concept_confidence', 0.7),
                    'matched': False
                }
                
                new_theme = self.theme_data_generator.generate_for_major_event(
                    event_data, classification_result
                )
                
                if new_theme:
                    print(f"   ✅ 强制创建题材成功: {new_theme.name}")
                    
                    # ✅ 修复：确保返回字典形式
                    if hasattr(new_theme, 'to_dict'):
                        new_theme_dict = new_theme.to_dict()
                    elif hasattr(new_theme, '__dict__'):
                        new_theme_dict = new_theme.__dict__
                    else:
                        new_theme_dict = str(new_theme)
                    
                    return {
                        'status': 'success',
                        'event_id': event_data.get('event_id'),
                        'new_theme_created': True,
                        'new_theme': new_theme_dict,
                        'ai_category_inference': ai_category_result,
                        'creation_method': 'force_create_major'
                    }
            
            return {
                'status': 'error',
                'error': '无法生成题材数据',
                'event_id': event_data.get('event_id')
            }
            
        except Exception as e:
            print(f"❌ 强制创建题材失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'error': str(e),
                'event_id': event_data.get('event_id')
            }
    
    def get_candidates(self, limit: int = 20) -> List[Dict]:
        """获取候选列表"""
        return self.candidate_pool.get_all_candidates(limit)
    
    def clear_candidates(self):
        """清空候选池"""
        self.candidate_pool.clear()
    
    def get_engine_status(self) -> Dict:
        """获取引擎状态"""
        major_info = self.major_matcher.get_algorithm_info() if self.major_matcher else None
        normal_info = self.normal_matcher.get_algorithm_info() if self.normal_matcher else None
        
        status = {
            'version': '2.1.0',  # ✅ 更新版本号
            'data_loaded': self.data_loaded,
            'themes_count': self.current_themes_count,
            'categories_count': self.current_categories_count,
            'algorithms': {
                'major': major_info,
                'normal': normal_info
            },
            'candidate_pool': self.candidate_pool.get_stats(),
            'config': {
                'major_threshold': 0.6,
                'normal_threshold': 0.5,
                'major_ai_support': hasattr(self.major_matcher, 'infer_category_from_ai_keywords'),
                'theme_generator_set': bool(self.theme_data_generator)
            }
        }
        
        # ✅ 添加AI支持信息
        if hasattr(self.major_matcher, 'infer_category_from_ai_keywords'):
            status['ai_support'] = True
            status['ai_features'] = ['keyword_inference', 'category_inference']
        
        return status
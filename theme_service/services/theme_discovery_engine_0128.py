"""
主题发现引擎 - 业务逻辑处理（精简优化版）
修复重复判断问题，实现职责分离，确保算法状态正确
"""
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..matchers.matcher_factory import MatcherFactory
from ..matchers.base_matcher import BaseMatcher, MatchResult
from .candidate_pool import CandidatePool, Candidate

class ThemeDiscoveryEngine:
    """主题发现引擎 - 精简版"""
    
    def __init__(self):
        """初始化主题发现引擎"""
        print("🚀 初始化主题发现引擎...")
        
        try:
            # 1. 候选池
            self.candidate_pool = CandidatePool(max_size=100, ttl_hours=24)
            
            # 2. 创建算法实例
            major_config = {
                'match_threshold': 0.6,
                'max_results': 10,
                'min_keyword_matches': 2,
                'enable_analyst_logic': True,
                'classification_first': True
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
            
            # 3. 初始化标志
            self.data_loaded = False
            self.current_themes_count = 0
            self.current_categories_count = 0
            self.theme_data_generator = None
            
            print("✅ 主题发现引擎初始化完成")
            
        except Exception as e:
            print(f"❌ 主题发现引擎初始化失败: {e}")
            raise
    
    def load_data(self, themes: List[Dict], categories: List[Dict] = None) -> bool:
        """加载数据"""
        print(f"📥 加载数据到引擎...")
        
        try:
            self.current_themes_count = len(themes)
            self.current_categories_count = len(categories) if categories else 0
            
            # 初始化算法
            self.major_matcher.initialize(themes, categories)
            self.normal_matcher.initialize(themes, categories)
            
            self.data_loaded = True
            print(f"✅ 数据加载完成: {self.current_themes_count} 个题材")
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
        发现主题 - 精简版
        职责：只做发现，不做创建
        """
        if not self.data_loaded:
            raise RuntimeError("请先调用 load_data() 加载数据")
        
        start_time = time.time()
        
        try:
            event_type = event_data.get('event_type', 'normal')
            event_id = event_data.get('event_id', 'unknown')
            
            print(f"\n🔍 发现主题开始: {event_id}")
            
            # 根据事件类型处理
            if event_type == 'major':
                result = self._process_major_event(event_data)
            else:
                result = self._process_normal_event(event_data)
            
            # 构建返回结果
            response = {
                'event_id': event_id,
                'event_type': event_type,
                'matched': result['matched'],
                'theme_count': len(result['themes']),
                'themes': [match.to_dict() for match in result['themes']],
                'processing_path': result['processing_path'],
                'algorithm_used': result['algorithm_used'],
                'processing_time_ms': round((time.time() - start_time) * 1000, 2),
                'confidence': result['confidence'],
            }
            
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
            
            print(f"   ✅ 发现完成: 匹配={result['matched']}, 题材数={len(result['themes'])}")
            return response
            
        except Exception as e:
            print(f"❌ 发现主题失败: {e}")
            return {
                'event_id': event_data.get('event_id', ''),
                'matched': False,
                'error': str(e)
            }
    
    def _process_major_event(self, event_data: Dict) -> Dict:
        """处理Major事件"""
        print("   使用Major算法匹配...")
        
        # 调用算法匹配
        matches = self.major_matcher.match(event_data, precision='major')
        
        # 应用阈值
        filtered_matches = [match for match in matches if match.confidence >= 0.55]
        
        if filtered_matches:
            print(f"   ✅ 匹配成功: {len(filtered_matches)} 个题材")
            return {
                'matched': True,
                'themes': filtered_matches,
                'processing_path': 'major→match→success',
                'algorithm_used': 'Major算法',
                'confidence': filtered_matches[0].confidence if filtered_matches else 0.0
            }
        else:
            print(f"   ⚠️  未匹配到现有题材")
            
            # 添加到候选池
            self.candidate_pool.add_candidate(
                event_data,
                [match.to_dict() for match in matches[:3]] if matches else [],
                match_score=matches[0].confidence if matches else 0.0,
                processing_path='major→no_match→candidate'
            )
            print(f"   📝 已添加到候选池")
            
            return {
                'matched': False,
                'themes': matches[:5],
                'processing_path': 'major→no_match→candidate',
                'algorithm_used': 'Major算法',
                'confidence': matches[0].confidence if matches else 0.0
            }
    
    def _process_normal_event(self, event_data: Dict) -> Dict:
        """处理Normal事件"""
        print("   使用Normal算法匹配...")
        
        matches = self.normal_matcher.match(event_data, precision='normal')
        filtered_matches = [match for match in matches if match.confidence >= 0.4]
        
        if filtered_matches:
            print(f"   ✅ 匹配成功: {len(filtered_matches)} 个题材")
            return {
                'matched': True,
                'themes': filtered_matches,
                'processing_path': 'normal→match→success',
                'algorithm_used': 'Normal算法',
                'confidence': filtered_matches[0].confidence if filtered_matches else 0.0
            }
        else:
            print(f"   ⚠️  未匹配到现有题材")
            return {
                'matched': False,
                'themes': matches[:3],
                'processing_path': 'normal→no_match',
                'algorithm_used': 'Normal算法',
                'confidence': matches[0].confidence if matches else 0.0
            }
    
    def create_theme_for_major_event(self, event_data: Dict) -> Dict:
        """
        为Major事件创建题材 - 统一创建入口
        这是唯一的创建点
        """
        event_id = event_data.get('event_id', 'unknown')
        event_type = event_data.get('event_type', 'normal')
        
        print(f"\n🏭 为Major事件创建题材: {event_id}")
        
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
            
            # ✅ 调用生成器（唯一的创建点）
            new_theme = self.theme_data_generator.generate_for_major_event(
                event_data, classification_result
            )
            
            if new_theme:
                print(f"   ✅ 创建成功: {new_theme.name}")
                
                # 转换新题材数据
                if hasattr(new_theme, 'to_dict'):
                    new_theme_dict = new_theme.to_dict()
                elif hasattr(new_theme, '__dict__'):
                    new_theme_dict = new_theme.__dict__
                else:
                    new_theme_dict = {'name': str(new_theme)}
                
                return {
                    'status': 'success',
                    'event_id': event_id,
                    'new_theme_created': True,
                    'new_theme': new_theme_dict,
                    'ai_category_inference': ai_category_result,
                    'creation_method': 'major_event_creation'
                }
            else:
                print(f"   ❌ 主题生成器返回空结果")
                return {
                    'status': 'error',
                    'error': '无法生成题材数据',
                    'event_id': event_id
                }
                
        except Exception as e:
            print(f"❌ 创建失败: {e}")
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
        ✅ 调用统一的创建入口，避免重复逻辑
        """
        print(f"🚨 [兼容方法] 强制为Major事件创建题材: {event_data.get('event_id')}")
        return self.create_theme_for_major_event(event_data)
    
    def get_candidates(self, limit: int = 20) -> List[Dict]:
        """获取候选列表"""
        return self.candidate_pool.get_all_candidates(limit)
    
    def clear_candidates(self):
        """清空候选池"""
        self.candidate_pool.clear()
    
    def get_engine_status(self) -> Dict:
        """获取引擎状态 - 修复版"""
        # ✅ 修复：确保返回有效的algorithms字典
        try:
            algorithms = {
                'major': {
                    'name': 'Major算法',
                    'available': bool(self.major_matcher),
                    'initialized': bool(self.major_matcher and hasattr(self.major_matcher, 'initialized') and self.major_matcher.initialized)
                },
                'normal': {
                    'name': 'Normal算法',
                    'available': bool(self.normal_matcher),
                    'initialized': bool(self.normal_matcher and hasattr(self.normal_matcher, 'initialized') and self.normal_matcher.initialized)
                }
            }
            
            # 如果算法实例有更多信息，添加到字典中
            if self.major_matcher and hasattr(self.major_matcher, 'get_algorithm_info'):
                try:
                    major_info = self.major_matcher.get_algorithm_info()
                    if major_info:
                        algorithms['major'].update(major_info)
                except Exception:
                    pass
            
            if self.normal_matcher and hasattr(self.normal_matcher, 'get_algorithm_info'):
                try:
                    normal_info = self.normal_matcher.get_algorithm_info()
                    if normal_info:
                        algorithms['normal'].update(normal_info)
                except Exception:
                    pass
        except Exception as e:
            # 如果构建失败，返回最小信息
            algorithms = {
                'major': {'name': 'Major算法', 'error': str(e)},
                'normal': {'name': 'Normal算法', 'error': str(e)}
            }
        
        # 获取候选池统计
        candidate_stats = {}
        try:
            if hasattr(self.candidate_pool, 'get_stats'):
                candidate_stats = self.candidate_pool.get_stats()
        except Exception:
            candidate_stats = {'available': False}
        
        return {
            'version': '2.2.0',
            'data_loaded': self.data_loaded,
            'themes_count': self.current_themes_count,
            'categories_count': self.current_categories_count,
            'algorithms': algorithms,  # ✅ 确保这是有效字典
            'candidate_pool': candidate_stats,
            'theme_generator_ready': bool(self.theme_data_generator),
            'engine_initialized': True,
            'timestamp': datetime.now().isoformat()
        }
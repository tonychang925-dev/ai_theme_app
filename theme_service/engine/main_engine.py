"""
engine/main_engine.py
主引擎 - 集成所有组件
"""
import asyncio
from typing import List, Dict, Any
from .event_processor import EventProcessor, ProcessingResult

class ThemeDiscoveryEngine:
    """主题发现引擎 - 集成层"""
    
    def __init__(self, db_manager = None):
        self.db_manager = db_manager  # 数据库管理器（可选）
        self.event_processor = EventProcessor()
        self.themes_loaded = False
        
        print("🎯 ThemeDiscoveryEngine 初始化")
    
    async def load_themes_from_database(self):
        """从数据库加载题材"""
        if not self.db_manager:
            print("⚠️  未提供数据库管理器，使用模拟数据")
            themes = self._get_mock_themes()
        else:
            # 从数据库加载题材数据
            themes = await self.db_manager.load_all_themes()
        
        # 初始化匹配算法
        self.event_processor.initialize_matchers(themes)
        self.themes_loaded = True
        
        print(f"✅ 加载 {len(themes)} 个题材到算法")
    
    def process_event(self, event_data: Dict) -> Dict:
        """处理事件 - 对外接口"""
        if not self.themes_loaded:
            raise RuntimeError("请先调用 load_themes_from_database()")
        
        # 调用事件处理器
        result = self.event_processor.process_event(event_data)
        
        # 转换为字典格式
        return {
            'status': 'success',
            'result': {
                'event_id': result.event_id,
                'event_type': result.event_type,
                'matched': result.matched,
                'theme_info': result.theme_info,
                'candidate_info': result.candidate_info,
                'processing_path': result.processing_path,
                'algorithm_used': result.algorithm_used,
                'processing_time_ms': round(result.processing_time * 1000, 2)
            },
            'engine_info': {
                'version': '2.0.0',
                'architecture': 'modular'
            }
        }
    
    def get_engine_status(self) -> Dict:
        """获取引擎状态"""
        processor_status = self.event_processor.get_processor_status()
        
        return {
            'engine': 'ThemeDiscoveryEngine',
            'version': '2.0.0',
            'themes_loaded': self.themes_loaded,
            'processor_status': processor_status,
            'architecture': {
                'layer': 'business_logic',
                'algorithms': 'pluggable',
                'major_normal': 'separate'
            }
        }
    
    def _get_mock_themes(self) -> List[Dict]:
        """获取模拟题材数据"""
        return [
            {
                'code': 'SW_270101',
                'name': '半导体芯片',
                'keywords': ['芯片', '半导体', '集成电路', '处理器'],
                'tags': {'keywords': ['芯片', '半导体'], 'industry': '电子'},
                'level1_category': '电子',
                'level2_category': '半导体',
                'heat_score': 85.0
            },
            {
                'code': 'SW_710101',
                'name': '人工智能',
                'keywords': ['AI', '人工智能', '机器学习', '深度学习'],
                'tags': {'keywords': ['AI', '人工智能'], 'industry': '计算机'},
                'level1_category': '计算机',
                'level2_category': '软件开发',
                'heat_score': 92.0
            }
        ]

# 测试函数
def test_modular_engine():
    """测试模块化引擎"""
    print("\n" + "="*60)
    print("🧪 测试模块化引擎架构")
    print("="*60)
    
    # 创建引擎
    engine = ThemeDiscoveryEngine()
    
    # 加载题材（使用模拟数据）
    engine.load_themes_from_database()
    
    # 测试Major事件
    print("\n1. 测试Major事件:")
    major_event = {
        'event_id': 'major_test_001',
        'event_type': 'major',
        'title': '半导体芯片技术重大突破',
        'content': '国内半导体企业突破7纳米芯片技术',
        'keywords': ['芯片', '半导体', '技术突破', '7纳米']
    }
    
    result1 = engine.process_event(major_event)
    print(f"   结果: {'匹配成功' if result1['result']['matched'] else '创建候选'}")
    print(f"   处理路径: {result1['result']['processing_path']}")
    
    # 测试Normal事件
    print("\n2. 测试Normal事件:")
    normal_event = {
        'event_id': 'normal_test_001',
        'event_type': 'normal',
        'title': 'AI医疗应用前景广阔',
        'content': '人工智能在医疗诊断领域应用广泛',
        'keywords': ['AI', '医疗', '人工智能', '诊断']
    }
    
    result2 = engine.process_event(normal_event)
    print(f"   结果: {'匹配成功' if result2['result']['matched'] else '进入候选池'}")
    print(f"   处理路径: {result2['result']['processing_path']}")
    
    # 获取引擎状态
    status = engine.get_engine_status()
    print(f"\n📊 引擎状态:")
    print(f"   算法配置: {status['processor_status']['algorithms']['major']['name']}")
    print(f"   候选池大小: {status['processor_status']['candidate_pool_size']}")
    
    print("\n✅ 模块化引擎测试完成")
    return True

if __name__ == "__main__":
    test_modular_engine()
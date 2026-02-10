# test_theme_processor_fix.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_service.streams.handlers.theme_processor import ThemeProcessor

def test_decision_building():
    """测试决策构建功能"""
    print("🧪 测试ThemeProcessor决策构建...")
    
    try:
        # 创建ThemeProcessor实例
        processor = ThemeProcessor(
            enable_classification_first=True,
            consumer_name="test_processor"
        )
        
        # 模拟ThemeService
        class MockThemeService:
            def create_new_theme_by_rules(self, event_data):
                return {
                    "theme_data": {
                        "name": "测试题材概念",
                        "code": "TEST_CONCEPT_240101",
                        "theme_type": "concept",
                        "description": "测试描述",
                        "heat_score": 50,
                        "status": "active"
                    },
                    "categories_to_create": [
                        {
                            "category_code": "CT0001",
                            "category_name": "测试分类",
                            "category_level": 1,
                            "category_type": "concept"
                        }
                    ],
                    "database_instructions": {
                        "action": "create_new_theme",
                        "operations": ["create_category", "create_theme", "create_mapping"]
                    }
                }
        
        # 设置模拟的ThemeService
        processor.theme_service = MockThemeService()
        
        # 测试决策构建
        test_decision = processor._build_decision(
            decision_type="category_no_match",  # 注意：是字符串，不是DecisionType.CATEGORY_NO_MATCH
            event_data={
                "event_id": "test_event_001",
                "event_type": "major",  # major事件应该创建新题材
                "title": "测试事件标题",
                "ai_analysis": {"core_concept": "测试概念"}
            },
            stream_type="major",
            category_info={"need_create_category": True},
            confidence=0.8,
            reason="测试决策构建"
        )
        
        print(f"✅ 决策构建成功")
        print(f"   决策类型: {test_decision['decision_type']}")
        print(f"   动作: {test_decision['action']}")
        print(f"   是否包含complete_theme_data: {'complete_theme_data' in test_decision}")
        print(f"   是否包含operations: {'operations' in test_decision}")
        
        if 'complete_theme_data' in test_decision:
            print(f"   complete_theme_data包含operations: {'operations' in test_decision['complete_theme_data']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_decision_building()
    sys.exit(0 if success else 1)
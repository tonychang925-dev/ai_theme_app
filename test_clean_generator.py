# test_clean_generator.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from theme_service.creators.theme_rule_generator import ThemeRuleBasedGeneratorFixed
from theme_service.schemas.strict_dto import StrictCompleteThemeDTO

def test_clean_generator():
    """测试净化版生成器"""
    print("🧪 测试ThemeRuleBasedGeneratorFixed净化版...")
    
    # 测试数据
    existing_categories = [
        {'category_code': 'CT0001', 'category_name': '概念题材', 'category_level': 1, 'category_type': 'concept'},
        {'category_code': 'CT0001_C01', 'category_name': '概念子类', 'category_level': 2, 'category_type': 'concept', 'parent_code': 'CT0001'},
    ]
    
    ai_analysis = {
        'event_keywords': ['地缘政治', '国际关系', '外交风险'],
        'core_concept': '中日关系紧张',
        'impact_level': 'high',
        'concept_confidence': 0.8,
        'summary': '测试摘要',
        'level1_category': None,
        'level2_category': None
    }
    
    event_data = {
        'event_id': 'test_event_001',
        'title': '日本首相参拜靖国神社引发地区紧张',
        'ai_analysis': ai_analysis
    }
    
    try:
        # 1. 测试初始化
        generator = ThemeRuleBasedGeneratorFixed(existing_categories)
        print("✅ 1. 初始化成功")
        
        # 2. 测试纯净版方法
        result = generator.generate_theme_data_only(event_data)
        print("✅ 2. generate_theme_data_only调用成功")
        
        # 3. 验证返回类型是StrictCompleteThemeDTO
        assert isinstance(result, StrictCompleteThemeDTO), "❌ 返回的不是StrictCompleteThemeDTO"
        print("✅ 3. 返回正确的DTO类型")
        
        # 4. 验证数据完整性
        result.validate()
        print("✅ 4. 数据验证通过")
        
        # 5. 验证不包含指令字段
        theme_data = result.theme_data
        assert 'operations' not in theme_data, "❌ theme_data不应包含operations"
        assert 'database_instructions' not in theme_data, "❌ theme_data不应包含database_instructions"
        print("✅ 5. 不包含指令字段")
        
        # 6. 验证有正确的数据字段
        assert 'name' in theme_data, "❌ 缺少name字段"
        assert 'code' in theme_data, "❌ 缺少code字段"
        assert 'theme_type' in theme_data, "❌ 缺少theme_type字段"
        print("✅ 6. 包含必要的数据字段")
        
        # 7. 验证分类数据
        assert len(result.categories_to_create) > 0, "❌ 没有生成分类数据"
        print(f"✅ 7. 生成分类数据: {len(result.categories_to_create)} 个")
        
        # 8. 验证category_info包含决策信息
        category_info = result.category_info
        assert 'theme_type' in category_info, "❌ category_info缺少theme_type"
        assert 'need_create_category' in category_info, "❌ category_info缺少need_create_category"
        print("✅ 8. category_info包含决策信息")
        
        print(f"\n🎉 测试通过！")
        print(f"   题材名称: {theme_data['name']}")
        print(f"   题材代码: {theme_data['code']}")
        print(f"   题材类型: {theme_data['theme_type']}")
        print(f"   需要创建分类: {category_info['need_create_category']}")
        
        return True
        
    except AssertionError as e:
        print(f"❌ 测试失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_clean_generator()
    sys.exit(0 if success else 1)
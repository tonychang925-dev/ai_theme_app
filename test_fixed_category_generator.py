# test_fixed_category_generator.py
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from theme_service.creators.fixed_category_generator import FixedCategoryGenerator
from theme_service.creators.theme_rule_generator import ShenwanCodeGenerator

def test_fixed_category_generator():
    """严格测试修复版分类生成器"""
    print("🧪 开始测试FixedCategoryGenerator...")
    
    # 测试数据
    existing_categories = [
        {'category_code': 'CT0001', 'category_name': '概念题材', 'category_level': 1},
        {'category_code': 'CT0001_C01', 'category_name': '概念子类', 'category_level': 2},
    ]
    
    ai_analysis = {
        'event_keywords': ['地缘政治', '国际关系', '外交风险'],
        'core_concept': '中日关系紧张',
        'impact_level': 'high',
        'concept_confidence': 0.8
    }
    
    event_data = {
        'event_id': 'test_event_001',
        'title': '日本首相参拜靖国神社引发地区紧张',
        'ai_analysis': ai_analysis
    }
    
    try:
        # 1. 测试初始化
        generator = FixedCategoryGenerator(existing_categories)
        print("✅ 1. 初始化成功")
        
        # 2. 测试编码生成
        existing_codes = generator._extract_existing_codes()
        print(f"✅ 2. 提取现有编码: {existing_codes}")
        
        # 3. 测试概念分类生成
        result = generator.generate_concept_categories(ai_analysis, event_data)
        
        # 验证结果
        assert 'level1' in result, "缺少level1数据"
        assert 'level2' in result, "缺少level2数据"
        
        level1_code = result['level1']['category_code']
        level2_code = result['level2']['category_code']
        
        # 验证编码不是硬编码
        assert level1_code != "CT0001", f"❌ 编码仍然是硬编码: {level1_code}"
        assert level2_code != "CT0001_C01", f"❌ 编码仍然是硬编码: {level2_code}"
        
        # 验证编码唯一性
        assert level1_code not in existing_codes, f"❌ 一级编码重复: {level1_code}"
        assert level2_code not in existing_codes, f"❌ 二级编码重复: {level2_code}"
        
        # 验证名称不是硬编码
        assert result['level1']['category_name'] != "概念题材", "❌ 一级名称仍然是硬编码"
        assert result['level2']['category_name'] != "概念子类", "❌ 二级名称仍然是硬编码"
        
        print(f"✅ 3. 生成概念分类成功:")
        print(f"   一级: {result['level1']['category_code']} - {result['level1']['category_name']}")
        print(f"   二级: {result['level2']['category_code']} - {result['level2']['category_name']}")
        
        # 4. 测试不同概念类型
        test_cases = [
            {
                'name': '技术概念',
                'ai_analysis': {
                    'event_keywords': ['半导体', '芯片', '人工智能', '技术创新'],
                    'core_concept': '光刻胶技术突破',
                    'impact_level': 'high'
                }
            },
            {
                'name': '经济概念', 
                'ai_analysis': {
                    'event_keywords': ['货币政策', '通货膨胀', '经济增长', '金融市场'],
                    'core_concept': '量化宽松政策',
                    'impact_level': 'medium'
                }
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            result = generator.generate_concept_categories(
                test_case['ai_analysis'], 
                {'title': f'{test_case["name"]}测试事件'}
            )
            print(f"✅ 3.{i}. {test_case['name']}测试通过")
        
        print("🎉 所有测试通过！FixedCategoryGenerator修复成功")
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
    success = test_fixed_category_generator()
    sys.exit(0 if success else 1)
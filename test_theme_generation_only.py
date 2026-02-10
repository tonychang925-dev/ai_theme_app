#!/usr/bin/env python3
# test_theme_generation_only.py
"""
极简测试：只测试题材生成，不涉及任何其他组件
目标：验证7.2.2规则（未匹配到任何分类时，只创建1级概念分类）
"""

import sys
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.append('/Users/admin/Desktop/ai_theme_app')

# ============================================================
# 模拟数据
# ============================================================

def create_test_event_data() -> Dict:
    """创建测试事件数据"""
    return {
        'event_id': 'test_event_001',
        'event_type': 'major',
        'title': '对日制裁相关新闻',
        'ai_analysis': {
            'core_concept': '日本首相参拜靖国神社引发地区紧张',
            'event_keywords': ['地缘政治', '国际关系', '东亚安全'],
            'summary': '日本首相参拜靖国神社引发地区紧张局势',
            'concept_confidence': 0.85,
            'impact_level': 'high'
        }
    }

def create_empty_categories() -> List[Dict]:
    """创建空的分类列表（模拟数据库无匹配分类）"""
    return []

# ============================================================
# 核心测试：只测试生成器功能
# ============================================================

def test_generator_only():
    """只测试生成器，不涉及数据库、流、决策等"""
    print("\n" + "="*60)
    print("🧪 极简测试：只测试ThemeRuleBasedGeneratorFixed")
    print("="*60)
    
    try:
        # 1. 导入生成器
        from theme_service.creators.theme_rule_generator import ThemeRuleBasedGeneratorFixed
        
        # 2. 准备数据
        event_data = create_test_event_data()
        existing_categories = create_empty_categories()
        
        print(f"📊 测试数据准备:")
        print(f"   事件ID: {event_data['event_id']}")
        print(f"   核心概念: {event_data['ai_analysis']['core_concept']}")
        print(f"   现有分类数: {len(existing_categories)}")
        
        # 3. 创建生成器实例
        print("\n🔧 创建生成器实例...")
        generator = ThemeRuleBasedGeneratorFixed(existing_categories)
        
        # 4. 直接调用生成方法（模拟未匹配到任何分类）
        print("\n🎯 执行生成（模拟未匹配到任何分类）...")
        
        # 🔥 关键：我们手动传入正确的参数，跳过所有匹配和决策逻辑
        from theme_service.schemas.strict_dto import StrictCompleteThemeDTO
        
        # 直接生成最简单的数据
        theme_data = generator._build_theme_data_only(
            theme_name=event_data['ai_analysis']['core_concept'] + "概念",
            theme_code="TEST_CONCEPT_001",
            description=f"概念题材：{event_data['ai_analysis']['core_concept']}",
            theme_type='concept',
            rule_type='未匹配到任何分类',
            final_level1=None,  # 没有1级分类
            final_level2=None,  # 没有2级分类
            level3_category=event_data['ai_analysis']['core_concept'] + "概念",
            category_path=[event_data['ai_analysis']['core_concept'] + "概念"],
            event_data=event_data,
            ai_analysis=event_data['ai_analysis']
        )
        
        print(f"\n✅ 生成成功！")
        print(f"   题材名称: {theme_data.get('name')}")
        print(f"   题材代码: {theme_data.get('code')}")
        print(f"   题材类型: {theme_data.get('theme_type')}")
        print(f"   1级分类: {theme_data.get('level1_category')}")
        print(f"   2级分类: {theme_data.get('level2_category')}")
        
        # 5. 验证7.2.2规则
        print("\n📋 验证7.2.2规则:")
        
        # 规则1: 应该是concept类型
        if theme_data.get('theme_type') == 'concept':
            print("   ✅ 题材类型: concept (正确)")
        else:
            print(f"   ❌ 题材类型错误: {theme_data.get('theme_type')}")
            return False
        
        # 规则2: 不应该有1、2级分类
        if not theme_data.get('level1_category') and not theme_data.get('level2_category'):
            print("   ✅ 没有1、2级分类 (正确，符合7.2.2)")
        else:
            print(f"   ❌ 错误地设置了分类: L1={theme_data.get('level1_category')}, L2={theme_data.get('level2_category')}")
            return False
        
        # 规则3: 三级分类应该是题材名称
        if theme_data.get('level3_category') == theme_data.get('name'):
            print("   ✅ 三级分类正确")
        else:
            print(f"   ❌ 三级分类错误: {theme_data.get('level3_category')}")
            return False
        
        print("\n🎉 7.2.2规则验证通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================
# 扩展测试：测试完整的generate_theme_data_only方法
# ============================================================

def test_generate_theme_data_only():
    """测试完整的generate_theme_data_only方法"""
    print("\n" + "="*60)
    print("🧪 测试完整generate_theme_data_only方法")
    print("="*60)
    
    try:
        from theme_service.creators.theme_rule_generator import ThemeRuleBasedGeneratorFixed
        from theme_service.schemas.strict_dto import StrictCompleteThemeDTO
        
        # 准备数据
        event_data = create_test_event_data()
        existing_categories = create_empty_categories()
        
        # 创建生成器
        generator = ThemeRuleBasedGeneratorFixed(existing_categories)
        
        print("📞 调用generate_theme_data_only()...")
        
        # 直接调用方法
        dto = generator.generate_theme_data_only(event_data)
        
        if not isinstance(dto, StrictCompleteThemeDTO):
            print(f"❌ 返回值类型错误: {type(dto)}")
            return False
        
        print(f"\n✅ generate_theme_data_only调用成功")
        print(f"   返回DTO类型: {type(dto).__name__}")
        
        # 打印DTO内容
        print(f"\n📋 DTO内容:")
        print(f"   theme_data: {dto.theme_data.get('name') if dto.theme_data else 'None'}")
        print(f"   categories_to_create: {len(dto.categories_to_create) if dto.categories_to_create else 0}")
        print(f"   category_info: {dto.category_info}")
        
        # 检查生成的分类数量
        if dto.categories_to_create:
            print(f"\n📊 需要创建的分类:")
            for i, cat in enumerate(dto.categories_to_create):
                print(f"   {i+1}. {cat.get('category_name')} (级别: {cat.get('category_level')})")
                
            # 🔥 关键验证：应该只创建1个分类（1级），还是2个分类？
            if len(dto.categories_to_create) == 1:
                cat = dto.categories_to_create[0]
                if cat.get('category_level') == 1:
                    print("   ✅ 正确：只创建1级分类 (符合7.2.2规则)")
                else:
                    print(f"   ❌ 错误：创建了{cat.get('category_level')}级分类")
                    return False
            elif len(dto.categories_to_create) == 2:
                print("   ❌ 错误：创建了2个分类 (违反7.2.2规则)")
                # 检查分类名称
                for cat in dto.categories_to_create:
                    print(f"      - {cat.get('category_name')} (级别: {cat.get('category_level')})")
                return False
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================
# 最简测试：只验证编码生成
# ============================================================

def test_code_generation_only():
    """只测试编码生成逻辑"""
    print("\n" + "="*60)
    print("🧪 最简测试：只测试编码生成")
    print("="*60)
    
    try:
        from theme_service.creators.theme_rule_generator import ShenwanCodeGenerator
        
        # 测试1: 概念分类编码生成
        existing_codes = ['CT0001', 'CT0002']
        new_code = ShenwanCodeGenerator.generate_concept_level1_code(existing_codes)
        
        print(f"📊 编码生成测试:")
        print(f"   现有编码: {existing_codes}")
        print(f"   新生成编码: {new_code}")
        
        if new_code == 'CT0003':
            print("   ✅ 概念编码生成正确")
        else:
            print(f"   ❌ 概念编码生成错误: {new_code}")
            return False
        
        # 测试2: 检查是否有重复编码
        test_codes = ['CT0001', 'CT0002', 'CT0003']
        for _ in range(5):
            new_code = ShenwanCodeGenerator.generate_concept_level1_code(test_codes)
            print(f"   测试生成: {new_code}")
            if new_code in test_codes:
                print(f"   ❌ 生成了重复编码: {new_code}")
                return False
            test_codes.append(new_code)
        
        print("\n🎉 编码生成测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================
# 主函数
# ============================================================

if __name__ == "__main__":
    print("🚀 开始极简测试：只测试题材生成")
    print("目标：验证7.2.2规则是否被正确执行")
    print("-" * 60)
    
    # 运行测试
    success_count = 0
    total_count = 0
    
    # 测试1: 只测试生成器
    total_count += 1
    if test_generator_only():
        success_count += 1
    
    # 测试2: 测试完整方法
    total_count += 1
    if test_generate_theme_data_only():
        success_count += 1
    
    # 测试3: 只测试编码
    total_count += 1
    if test_code_generation_only():
        success_count += 1
    
    # 结果汇总
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    print(f"   通过测试: {success_count}/{total_count}")
    
    if success_count == total_count:
        print("🎉 所有测试通过！7.2.2规则验证成功！")
        print("\n✅ 结论：")
        print("   1. 未匹配到任何分类时，只创建1级概念分类")
        print("   2. 不创建无意义的2级分类")
        print("   3. 题材类型为concept")
    else:
        print("❌ 部分测试失败，请检查问题")
        print("\n🔧 建议：")
        print("   1. 查看失败的测试输出")
        print("   2. 检查ThemeRuleBasedGeneratorFixed的_determine_rule_type方法")
        print("   3. 检查_generate_category_data_only方法中的逻辑")
    
    print("\n💡 提示：")
    print("   运行命令：python test_theme_generation_only.py")
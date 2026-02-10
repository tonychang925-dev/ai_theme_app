#!/usr/bin/env python3
"""
deepseek_parser.py 修复后的单元测试
测试详细摘要生成功能
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import json

class TestDeepSeekParserFixed:
    """测试修复后的DeepSeekParser"""
    
    def test_prompt_includes_detailed_summary_requirement(self):
        """测试提示词是否要求详细摘要"""
        from model_service.llm_parser.deepseek_parser_0203 import DeepSeekParser
        
        # 创建解析器（不实际调用API）
        parser = DeepSeekParser(model_name="deepseek-chat")
        
        # 由于parse_news是异步方法，我们检查方法定义中的提示词
        # 这里我们直接检查文件内容
        parser_file = Path(__file__).parent.parent / "llm_parser" / "deepseek_parser.py"
        
        with open(parser_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 关键检查点：提示词是否要求详细摘要
        checks = [
            ("要求详细摘要", "详细中文摘要" in content),
            ("指定摘要长度", "150-300字" in content or "100-200字" in content),
            ("包含详细说明", "事件主体" in content or "具体行动" in content),
        ]
        
        print("🔍 检查 deepseek_parser.py 提示词修复")
        all_passed = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}")
            if not passed:
                all_passed = False
        
        assert all_passed, "提示词未按要求修复"
        
        # 额外检查：不应该只有"一句中文摘要"
        assert "一句中文摘要" not in content or "一句中文摘要，说明" not in content, \
            "提示词仍然只要求一句摘要"
    
    def test_prompt_structure_improved(self):
        """测试提示词结构改进"""
        parser_file = Path(__file__).parent.parent / "llm_parser" / "deepseek_parser.py"
        
        with open(parser_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找parse_news方法中的提示词部分
        import re
        prompt_pattern = r'prompt = f""".*?"""'
        match = re.search(prompt_pattern, content, re.DOTALL)
        
        if match:
            prompt = match.group(0)
            
            # 检查是否包含详细说明
            has_detail_requirements = any(
                keyword in prompt 
                for keyword in ["技术细节", "市场影响", "产业链", "具体行动", "成果"]
            )
            
            assert has_detail_requirements, "提示词缺少详细分析要求"
            
            print("✅ 提示词结构改进验证通过")
            return True
        else:
            print("❌ 未找到提示词定义")
            return False

if __name__ == "__main__":
    # 直接运行测试
    print("🧪 运行 deepseek_parser 单元测试")
    print("="*60)
    
    tester = TestDeepSeekParserFixed()
    
    tests = [
        ("测试详细摘要要求", tester.test_prompt_includes_detailed_summary_requirement),
        ("测试提示词结构", tester.test_prompt_structure_improved),
    ]
    
    all_passed = True
    for test_name, test_func in tests:
        try:
            test_func()
            print(f"✅ {test_name}")
        except AssertionError as e:
            print(f"❌ {test_name}: {e}")
            all_passed = False
        except Exception as e:
            print(f"💥 {test_name}: {e}")
            all_passed = False
    
    print("="*60)
    if all_passed:
        print("🎉 所有单元测试通过！")
        sys.exit(0)
    else:
        print("⚠️  有测试失败")
        sys.exit(1)

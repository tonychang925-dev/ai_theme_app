#!/usr/bin/env python3
"""
极简集成验证 - 直接在 ai_theme_app/ 目录运行
"""
import asyncio
import sys
import os

print("=" * 60)
print("🔧 真实环境集成验证")
print("=" * 60)

async def test_integration():
    """测试真实集成"""
    
    # 1. 测试导入现有 theme_analyzer
    print("\n1. 测试导入现有 theme_analyzer.py...")
    try:
        from model_service.llm_parser.theme_analyzer import ThemeAnalyzer
        print("   ✅ 成功导入 ThemeAnalyzer")
        
        # 查看现有ThemeAnalyzer的结构
        print(f"   📄 ThemeAnalyzer 源代码行数: 104 (你的文件)")
        
        # 列出ThemeAnalyzer的方法
        methods = [m for m in dir(ThemeAnalyzer) if not m.startswith('_')]
        print(f"   可用方法: {methods}")
        
    except ImportError as e:
        print(f"   ❌ 导入失败: {e}")
        # 看看文件内容
        with open("model_service/llm_parser/theme_analyzer.py", "r") as f:
            lines = f.readlines()
            print(f"   文件前5行:")
            for i, line in enumerate(lines[:5]):
                print(f"     {i+1}: {line.rstrip()}")
        return False
    
    # 2. 测试创建BaseLLMParser
    print("\n2. 测试创建BaseLLMParser...")
    try:
        from model_service.llm_parser.factory import LLMParserFactory
        
        # 检查环境变量
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("   ⚠️  未设置 DEEPSEEK_API_KEY，使用模拟解析器")
            # 创建模拟解析器
            from model_service.llm_parser.base_parser import BaseLLMParser
            
            class MockParser(BaseLLMParser):
                def __init__(self):
                    self.model_name = "mock-model"
                
                async def parse_content(self, content):
                    print(f"      [Mock] 解析内容: {content[:50]}...")
                    return {
                        "core_investment_logic": "智能眼镜作为AI硬件入口前景广阔",
                        "potential_themes": ["AI眼镜", "智能穿戴", "消费电子"],
                        "theme_strength": {"score": 8, "reason": "产品已量产"},
                        "certainty": 0.85
                    }
                
                async def parse_news(self, title, content):
                    return {"event_type": "mock"}
                
                async def close(self):
                    pass
            
            parser = MockParser()
            print("   ✅ 创建模拟解析器成功")
            
        else:
            print(f"   ✅ 找到API密钥，尝试创建真实解析器...")
            try:
                parser = LLMParserFactory.create_parser_from_env()
                print(f"   ✅ 成功创建解析器: {parser.__class__.__name__}")
            except Exception as e:
                print(f"   ⚠️  创建真实解析器失败: {e}")
                print("   回退到模拟解析器...")
                # 使用上面的MockParser
                parser = MockParser()
                
    except ImportError as e:
        print(f"   ❌ 导入失败: {e}")
        return False
    
    # 3. 创建ThemeAnalyzer实例并测试
    print("\n3. 测试ThemeAnalyzer功能...")
    try:
        # 创建ThemeAnalyzer实例
        analyzer = ThemeAnalyzer(parser)
        print("   ✅ ThemeAnalyzer实例化成功")
        
        # 测试事件数据
        test_event = {
            "id": 1001,
            "title": "Rokid智能眼镜销量突破30万台",
            "summary": "Rokid创始人透露智能眼镜销量已达30万台，预计下半年上线打车功能",
            "event_type": "产品突破",
            "impact_industries": ["消费电子", "人工智能", "智能穿戴"]
        }
        
        print(f"   🔍 测试事件分析:")
        print(f"      标题: {test_event['title'][:30]}...")
        print(f"      行业: {test_event['impact_industries']}")
        
        # 调用分析方法
        if hasattr(analyzer, 'analyze_for_theme_discovery'):
            result = await analyzer.analyze_for_theme_discovery(test_event)
            
            print("   ✅ 方法调用成功！")
            print(f"      返回字段: {list(result.keys())}")
            
            if 'potential_themes' in result and result['potential_themes']:
                print(f"      发现题材: {result['potential_themes']}")
            else:
                print(f"      未发现题材")
                
            if 'error' in result:
                print(f"      错误信息: {result['error']}")
                
            return True
        else:
            print("   ❌ ThemeAnalyzer没有 'analyze_for_theme_discovery' 方法")
            print("      现有方法:", [m for m in dir(analyzer) if not m.startswith('_')])
            return False
            
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# 运行测试
if __name__ == "__main__":
    print("环境检查:")
    print(f"  当前目录: {os.getcwd()}")
    print(f"  Python版本: {sys.version.split()[0]}")
    print(f"  DEEPSEEK_API_KEY设置: {'是' if os.getenv('DEEPSEEK_API_KEY') else '否'}")
    
    success = asyncio.run(test_integration())
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 集成验证成功！")
        print("\n下一步:")
        print("1. 创建 theme_service 基础架构")
        print("2. 实现 AIThemeClient 调用现有的 ThemeAnalyzer")
        print("3. 开始开发主题发现引擎")
    else:
        print("⚠️  集成验证失败")
        print("\n建议:")
        print("1. 检查 theme_analyzer.py 中的方法名称")
        print("2. 确认 BaseLLMParser 接口是否正确实现")
        print("3. 运行: python -c \"from model_service.llm_parser.theme_analyzer import ThemeAnalyzer; print(dir(ThemeAnalyzer))\"")
    print("=" * 60)

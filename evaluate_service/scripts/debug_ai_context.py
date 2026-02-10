# evaluate_service/scripts/debug_ai_context.py
"""
调试AI实际接收的上下文数据
"""
#!/usr/bin/env python3
import asyncio
import logging
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def debug_ai_context():
    """调试AI实际接收的上下文"""
    print("🔍 调试AI实际接收的上下文数据")
    print("="*60)
    
    try:
        # 1. 加载一个具体事件
        data_dir = project_root / "evaluate_service" / "data" / "processed"
        events_path = data_dir / "validation_events_fixed.json"
        
        with open(events_path, 'r', encoding='utf-8') as f:
            import json
            data = json.load(f)
        
        events = data.get('events', [])
        sample_event = events[0]  # AI_AR眼镜_001
        
        print("📋 原始事件完整结构:")
        print(json.dumps(sample_event, ensure_ascii=False, indent=2))
        print("\n" + "="*60)
        
        # 2. 模拟AI分析器的数据准备
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        
        # 创建现有主题
        existing_themes = [
            {
                'name': 'AI智能体企业并购',
                'description': 'AI智能体企业的并购活动，包括技术收购、企业合并等',
                'keywords': ['AI智能体', '并购', '企业收购', '技术收购', 'AI代理', '智能体']
            },
            {
                'name': '智能眼镜新品发布',
                'description': '智能眼镜产品发布相关，包括Meta、Apple等公司的新品发布',
                'keywords': ['智能眼镜', 'AR眼镜', '发布', '新品', '消费电子']
            }
        ]
        
        # 3. 手动构建AI提示词，看实际发送的内容
        print("\n📝 手动构建AI提示词（模拟AI实际接收的数据）:")
        print("="*60)
        
        # 构建事件上下文（模拟AI实际看到的）
        event_content = sample_event.get('original_news', {}).get('content', '')
        event_title = sample_event.get('original_news', {}).get('title', '')
        event_industries = sample_event.get('event_info', {}).get('impact_industries', [])
        
        print(f"🔹 事件标题: {event_title}")
        print(f"🔹 事件内容: {event_content}")
        print(f"🔹 事件长度: {len(event_content)} 字符")
        print(f"🔹 影响行业: {event_industries}")
        
        # 4. 检查AI提示词构建逻辑
        print("\n🔍 检查AI提示词构建逻辑...")
        
        # 导入AI分析器并查看其方法
        import inspect
        analyzer_file = Path("theme_service/ai_similarity_analyzer.py")
        
        with open(analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找build_enhanced_prompt方法
        if 'def build_enhanced_prompt' in content:
            print("✅ 找到build_enhanced_prompt方法")
            
            # 提取该方法
            import re
            prompt_method_pattern = r'def build_enhanced_prompt\(self, event_content, existing_themes\).*?(?=def |\Z)'
            match = re.search(prompt_method_pattern, content, flags=re.DOTALL)
            
            if match:
                method_content = match.group(0)
                print(f"📄 方法内容（前500字符）:")
                print(method_content[:500] + "...")
                
                # 检查是否包含完整的上下文
                if 'event_info' in method_content:
                    print("✅ 方法中包含event_info字段")
                else:
                    print("❌ 方法中可能缺少event_info字段")
                    
                if 'impact_industries' in method_content:
                    print("✅ 方法中包含impact_industries字段")
                else:
                    print("❌ 方法中可能缺少impact_industries字段")
        
        # 5. 实际运行一次AI分析，查看完整请求
        print("\n🚀 实际运行AI分析（查看完整请求）...")
        
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        import os
        
        api_key = os.getenv('DEEPSEEK_API_KEY')
        if api_key:
            llm_config = {
                'api_key': api_key,
                'model_name': 'deepseek-chat',
                'max_retries': 1,
                'timeout': 30,
                'temperature': 0.1
            }
            
            llm_parser = ReliableDeepSeekParser(config=llm_config)
            analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            # 覆盖analyze_similarity方法，打印实际发送的数据
            original_analyze = analyzer.analyze_similarity
            
            async def debug_analyze_similarity(extracted_theme_name, existing_themes, event_content):
                print("\n🔍 AI分析器实际接收的数据:")
                print("-"*40)
                print(f"📊 提取主题名称: {extracted_theme_name}")
                print(f"📊 现有主题数: {len(existing_themes)}")
                print(f"📊 事件内容长度: {len(event_content)}")
                
                # 查看前两个主题的结构
                for i, theme in enumerate(existing_themes[:2]):
                    print(f"\n📋 主题 {i+1}:")
                    print(f"   名称: {theme.get('name', 'N/A')}")
                    print(f"   描述: {theme.get('description', '')[:50]}...")
                    print(f"   关键词: {theme.get('keywords', [])}")
                
                # 调用原始方法
                return await original_analyze(extracted_theme_name, existing_themes, event_content)
            
            analyzer.analyze_similarity = debug_analyze_similarity
            
            # 执行分析
            print("\n🤖 开始AI分析...")
            result = await analyzer.analyze_similarity(
                extracted_theme_name="智能眼镜新品发布",
                existing_themes=existing_themes,
                event_content=event_content
            )
            
            print(f"\n📊 AI分析结果:")
            print(f"   最佳匹配: {result.best_match_theme}")
            print(f"   相似度: {result.similarity_score}")
            print(f"   理由: {result.similarity_reason[:150]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def check_prompt_in_detail():
    """详细检查AI提示词构建"""
    print("\n\n🔍 详细检查AI提示词构建逻辑")
    print("="*60)
    
    try:
        # 直接查看ai_similarity_analyzer.py文件
        analyzer_file = Path("theme_service/ai_similarity_analyzer.py")
        
        with open(analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找系统提示词
        if 'system_prompt = """' in content:
            start = content.find('system_prompt = """') + len('system_prompt = """')
            end = content.find('"""', start)
            system_prompt = content[start:end]
            
            print("📄 AI系统提示词:")
            print("-"*40)
            print(system_prompt[:500] + "...")
            print(f"\n提示词总长度: {len(system_prompt)} 字符")
            
            # 检查是否包含关键指令
            keywords = ['行业', 'impact', 'event_info', '事件信息', '上下文']
            missing_keywords = []
            for keyword in keywords:
                if keyword not in system_prompt:
                    missing_keywords.append(keyword)
            
            if missing_keywords:
                print(f"\n❌ 系统提示词缺少关键字段: {missing_keywords}")
            else:
                print("\n✅ 系统提示词包含关键字段")
        
        # 查找build_prompt_data方法
        if 'def _build_prompt_data' in content:
            print("\n\n🔧 检查_build_prompt_data方法...")
            
            # 提取该方法
            import re
            build_pattern = r'def _build_prompt_data\(self, event_content, existing_themes\).*?(?=def |\Z)'
            match = re.search(build_pattern, content, flags=re.DOTALL)
            
            if match:
                method_content = match.group(0)
                print("📋 方法内容（关键部分）:")
                
                # 检查是否处理了完整的event对象
                lines = method_content.split('\n')
                for i, line in enumerate(lines):
                    if 'event_info' in line or 'original_news' in line or 'impact_industries' in line:
                        print(f"  行 {i+1}: {line.strip()}")
        
        # 检查analyze_similarity方法
        if 'def analyze_similarity' in content:
            print("\n\n🔧 检查analyze_similarity方法...")
            
            # 提取该方法
            analyze_pattern = r'def analyze_similarity\(self,.*?extracted_theme_name.*?existing_themes.*?event_content.*?\).*?(?=def |\Z)'
            match = re.search(analyze_pattern, content, flags=re.DOTALL)
            
            if match:
                method_content = match.group(0)
                
                # 检查参数
                if 'extracted_theme_name' in method_content and 'existing_themes' in method_content and 'event_content' in method_content:
                    print("✅ analyze_similarity方法参数正常")
                else:
                    print("❌ analyze_similarity方法参数可能有问题")
                
                # 检查是否调用了_build_prompt_data
                if '_build_prompt_data' in method_content:
                    print("✅ 调用了_build_prompt_data方法")
                else:
                    print("❌ 可能没有正确调用_build_prompt_data方法")
        
        return True
        
    except Exception as e:
        print(f"❌ 详细检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    print("🚀 开始调试AI上下文问题")
    
    # 运行调试
    success1 = await debug_ai_context()
    
    # 详细检查
    success2 = await check_prompt_in_detail()
    
    print("\n" + "="*60)
    print("🎯 调试总结:")
    
    if success1 and success2:
        print("✅ 调试完成")
        print("\n💡 下一步:")
        print("   根据调试结果修复AI上下文问题")
    else:
        print("❌ 调试遇到问题")

if __name__ == "__main__":
    asyncio.run(main())
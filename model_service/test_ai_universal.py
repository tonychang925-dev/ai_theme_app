#!/usr/bin/env python3
"""
万能AI测试脚本 - 解决所有导入问题
"""
import asyncio
import os
import sys

def setup_environment():
    """设置环境"""
    # 获取项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # 添加所有可能的路径
    paths_to_add = [
        project_root,
        current_dir,
        os.path.join(project_root, "model_service"),
        os.path.join(current_dir, "services"),
    ]
    
    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)
    
    print(f"📁 工作目录: {os.getcwd()}")
    print(f"📁 脚本位置: {current_dir}")
    print(f"📁 项目根目录: {project_root}")
    print(f"🐍 Python路径: {sys.path}")

def import_modules():
    """导入所需模块"""
    modules = {}
    
    # 模块路径映射
    module_paths = {
        'database': 'model_service/database.py',
        'event_extractor': 'model_service/services/event_extractor.py',
    }
    
    for name, rel_path in module_paths.items():
        try:
            # 尝试绝对导入
            if name == 'database':
                from model_service.database import DatabaseManager
                modules['DatabaseManager'] = DatabaseManager
                print(f"✅ 成功导入: {name}")
            elif name == 'event_extractor':
                from model_service.services.event_extractor import AIEventExtractor
                modules['AIEventExtractor'] = AIEventExtractor
                print(f"✅ 成功导入: {name}")
        except ImportError:
            # 如果失败，使用动态导入
            print(f"⚠️  尝试动态导入: {name}")
            import importlib.util
            
            # 尝试多个可能的路径
            possible_paths = [
                os.path.join(project_root, rel_path),
                os.path.join(current_dir, rel_path.split('/')[-1]),
                rel_path
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if name == 'database':
                        modules['DatabaseManager'] = module.DatabaseManager
                    elif name == 'event_extractor':
                        modules['AIEventExtractor'] = module.AIEventExtractor
                    
                    print(f"✅ 动态导入成功: {name} from {path}")
                    break
    
    return modules

async def test_ai():
    """测试AI功能"""
    print("\n" + "=" * 60)
    print("🧪 AI模型功能测试")
    print("=" * 60)
    
    # 设置环境
    setup_environment()
    
    # 导入模块
    modules = import_modules()
    
    if 'DatabaseManager' not in modules or 'AIEventExtractor' not in modules:
        print("❌ 模块导入失败，无法继续测试")
        return
    
    DatabaseManager = modules['DatabaseManager']
    AIEventExtractor = modules['AIEventExtractor']
    
    # 检查运行模式
    use_mock = os.getenv('USE_MOCK', '0') == '1'
    has_deepseek = bool(os.getenv('DEEPSEEK_API_KEY'))
    has_openai = bool(os.getenv('OPENAI_API_KEY'))
    
    print(f"\n🔧 运行配置:")
    print(f"   模拟模式: {'是' if use_mock else '否'}")
    print(f"   DeepSeek: {'已配置' if has_deepseek else '未配置'}")
    print(f"   OpenAI: {'已配置' if has_openai else '未配置'}")
    
    if use_mock:
        print("\n🎭 使用模拟模式进行测试...")
    elif has_deepseek or has_openai:
        print("\n🤖 使用真实AI模型进行测试...")
    else:
        print("\n⚠️  未检测到API密钥，使用模拟模式")
        use_mock = True
    
    # 测试数据库连接
    print("\n🔌 测试数据库连接...")
    try:
        await DatabaseManager.health_check()
        print("✅ 数据库连接正常")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return
    
    # 获取测试新闻
    print("\n📰 获取测试新闻...")
    news_list = await DatabaseManager.fetch_pending_news(limit=1)
    
    if not news_list:
        print("📭 没有待处理的新闻，使用模拟数据")
        news_list = [{
            'news_id': 'test_ai_001',
            'title': '人工智能大会召开，多家公司发布AI新品',
            'content': '2024年人工智能产业大会在北京召开，华为、百度、阿里等公司发布最新AI产品。华为发布新一代AI芯片，百度推出文心大模型4.0，阿里云发布企业级AI解决方案。',
            'source': '测试数据',
            'publish_time': '2024-01-15 09:00:00',
            'url': 'http://test.ai'
        }]
    
    # 测试AI解析
    extractor = AIEventExtractor()
    
    for i, news in enumerate(news_list, 1):
        print(f"\n{'='*50}")
        print(f"测试 #{i}")
        print(f"标题: {news['title']}")
        
        try:
            print("⏳ AI解析中...")
            event_data = await extractor.extract_event(news)
            
            if event_data:
                print("\n✅ 解析成功!")
                print(f"   事件类型: {event_data.get('event_type')}")
                print(f"   方向: {event_data.get('direction')}")
                print(f"   置信度: {event_data.get('confidence')}")
                print(f"   影响行业: {', '.join(event_data.get('impact_industries', []))}")
                print(f"   摘要: {event_data.get('summary')}")
                
                # 如果是真实新闻，保存到数据库
                if news.get('news_id') != 'test_ai_001':
                    success = await DatabaseManager.save_event(event_data)
                    if success:
                        print("💾 已保存到数据库")
            else:
                print("❌ 解析失败: 返回空结果")
                
        except Exception as e:
            print(f"💥 解析异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    await extractor.close()
    
    print("\n" + "=" * 60)
    print("🎉 测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_ai())

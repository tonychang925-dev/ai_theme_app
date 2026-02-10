#!/usr/bin/env python3
"""
数据完整性检查 - 运行脚本
检查EnhancedThemeDiscovery数据保存是否完整
"""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# 项目根目录
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def check_event_save_integrity():
    """检查事件保存完整性"""
    print("🔍 检查事件数据保存完整性")
    print("=" * 80)
    
    try:
        # 1. 初始化数据库（与集成测试相同）
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        if hasattr(db_manager, 'clear_all_data'):
            await db_manager.clear_all_data()
        
        # 2. 测试数据（与你的validation_events_fixed.json格式相同）
        test_event = {
            'news_id': 'DATA_INTEGRITY_TEST_001',
            'event_info': {
                'event_type': '产品发布',
                'impact_industries': ['消费电子', 'AR'],
                'direction': '利好',
                'event_confidence': 0.95
            },
            'original_news': {
                'title': '数据完整性测试AR眼镜',
                'content': '这是一个用于测试数据完整性的AR眼镜产品发布新闻。确保original_news.content字段被正确保存。',
                'content_length': 45,
                'date': '2025-01-15'
            }
        }
        
        # 3. 模拟集成测试的保存逻辑
        print("\n📝 模拟集成测试事件保存逻辑...")
        
        # 按你的集成测试中的EventPreparer逻辑
        db_event = {
            'id': test_event['news_id'],
            'news_id': test_event['news_id'],
            'title': test_event['original_news']['title'],
            'full_content': test_event['original_news']['content'],
            'content_length': len(test_event['original_news']['content']),
            'has_full_content': True,
            'event_info': test_event['event_info'],
            'original_news': test_event['original_news'],
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        print(f"保存事件结构检查:")
        print(f"  original_news 类型: {type(db_event['original_news'])}")
        print(f"  original_news.content 存在: {'content' in db_event['original_news']}")
        print(f"  original_news.content 长度: {len(db_event['original_news']['content'])}")
        
        # 保存到数据库
        saved_id = await db_manager.create_or_update_event(db_event)
        print(f"✅ 事件保存结果: {saved_id}")
        
        # 4. 立即验证
        print("\n🔍 从数据库验证数据...")
        retrieved_event = await db_manager.get_event(test_event['news_id'])
        
        if not retrieved_event:
            print("❌ 无法从数据库获取事件")
            return False
        
        # 关键检查点
        checks = []
        
        # 检查1: original_news字段存在
        check1 = 'original_news' in retrieved_event
        checks.append(('original_news字段存在', check1))
        
        if check1:
            original_news = retrieved_event['original_news']
            
            # 检查2: original_news是字典
            check2 = isinstance(original_news, dict)
            checks.append(('original_news是字典', check2))
            
            if check2:
                # 检查3: content字段存在
                check3 = 'content' in original_news
                checks.append(('content字段存在', check3))
                
                if check3:
                    content = original_news['content']
                    
                    # 检查4: 内容非空
                    check4 = len(content.strip()) > 0
                    checks.append(('内容非空', check4))
                    
                    # 检查5: 内容与原始一致
                    check5 = content == test_event['original_news']['content']
                    checks.append(('内容与原始一致', check5))
        
        # 打印检查结果
        print("\n📊 数据完整性检查结果:")
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}")
        
        # 5. 模拟主题创建
        print("\n🔍 测试主题创建和关联...")
        
        theme_name = "数据完整性测试主题"
        theme_record = await db_manager.create_theme(
            name=theme_name,
            description="用于数据完整性测试",
            keywords=["测试", "完整性"],
            discovery_source="integrity_check",
            discovery_confidence=0.9
        )
        
        if theme_record:
            # 获取主题ID
            theme_id = None
            if hasattr(theme_record, 'id'):
                theme_id = theme_record.id
            elif isinstance(theme_record, dict):
                theme_id = theme_record.get('id')
            
            if theme_id:
                print(f"✅ 主题创建成功: {theme_name} (ID: {theme_id})")
                
                # 创建关联
                relation = await db_manager.create_event_theme_relation(
                    event_id=test_event['news_id'],
                    theme_id=theme_id,
                    confidence=0.9,
                    confidence_level='high'
                )
                
                if relation:
                    print(f"✅ 事件-主题关联成功")
                else:
                    print(f"❌ 事件-主题关联失败")
            else:
                print(f"❌ 无法获取主题ID")
        else:
            print(f"❌ 主题创建失败")
        
        # 6. 模拟RelatedThemeFetcher逻辑
        print("\n🔍 模拟RelatedThemeFetcher主题获取...")
        
        all_themes = await db_manager.get_all_active_themes(limit=100)
        print(f"数据库主题总数: {len(all_themes)}")
        
        themes_with_complete_content = []
        
        for theme in all_themes[:3]:  # 只检查前3个
            theme_id = None
            theme_name = "未知"
            
            if isinstance(theme, dict):
                theme_id = theme.get('id')
                theme_name = theme.get('name', '未知')
                related_events = theme.get('related_events', [])
            else:
                theme_id = getattr(theme, 'id', None)
                theme_name = getattr(theme, 'name', '未知')
                related_events = getattr(theme, 'related_events', [])
            
            print(f"\n  主题: {theme_name}")
            print(f"    关联事件数: {len(related_events)}")
            
            # 检查关联事件的内容
            has_content = False
            for event_id in related_events[:2]:  # 检查前2个事件
                event_data = await db_manager.get_event(event_id)
                if event_data:
                    content = event_data.get('original_news', {}).get('content', '')
                    if content and len(content.strip()) > 10:
                        has_content = True
                        print(f"    事件 {event_id}: 有内容 ({len(content)}字符)")
                    else:
                        print(f"    事件 {event_id}: ❌ 无内容或内容过短")
                else:
                    print(f"    事件 {event_id}: ❌ 无法获取事件数据")
            
            if has_content:
                themes_with_complete_content.append(theme)
        
        print(f"\n📊 主题过滤模拟结果:")
        print(f"  总主题数: {len(all_themes)}")
        print(f"  有完整内容的主题数: {len(themes_with_complete_content)}")
        
        if len(themes_with_complete_content) < len(all_themes):
            print(f"  ⚠️  {len(all_themes) - len(themes_with_complete_content)} 个主题将被过滤！")
            print("  🔥 这就是AI只分析部分主题的原因！")
        
        await db_manager.disconnect()
        
        # 7. 总结
        print("\n" + "=" * 80)
        print("🎯 检查总结")
        print("=" * 80)
        
        all_passed = all(passed for _, passed in checks)
        
        if all_passed:
            print("✅ 数据保存完整性检查通过")
        else:
            print("❌ 数据保存完整性检查失败")
            
        if len(themes_with_complete_content) < len(all_themes):
            print("\n⚠️  发现问题:")
            print("  RelatedThemeFetcher.fetch_themes_with_complete_news_content")
            print("  会过滤掉没有完整内容的主题，导致AI只分析部分主题")
            print("\n💡 修复建议:")
            print("  1. 确保事件保存时original_news.content字段正确保存")
            print("  2. 或修改主题获取逻辑，不要过滤没有完整内容的主题")
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ 检查过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

async def analyze_problem():
    """分析导致AI只分析部分主题的问题"""
    print("\n🔍 分析AI只分析10个主题的问题")
    print("=" * 80)
    
    print("\n📋 问题现象:")
    print("  日志显示: '数据库返回主题数: 15'")
    print("           '获取到 10 个主题（10 个有完整内容）'")
    
    print("\n🔍 原因分析:")
    print("  1. RelatedThemeFetcher.fetch_themes_with_complete_news_content")
    print("     只返回有完整内容的主题")
    print("  2. 5个主题被过滤，因为它们的关联事件没有完整内容")
    
    print("\n💡 根本原因:")
    print("  当主题被创建时，关联事件的original_news.content可能:")
    print("  a) 没有被正确保存到数据库")
    print("  b) 保存的格式不正确")
    print("  c) 内容被截断或丢失")
    
    print("\n🛠️ 验证方法:")
    print("  1. 运行集成测试，检查每个事件保存后的结构")
    print("  2. 在主题获取时，查看哪些主题的关联事件缺少内容")
    print("  3. 修改fetch_themes_with_complete_news_content，返回所有主题")

async def main():
    """主函数"""
    print("数据完整性检查工具")
    print("=" * 80)
    
    # 检查事件保存完整性
    success = await check_event_save_integrity()
    
    # 分析问题
    await analyze_problem()
    
    # 生成报告
    await generate_report(success)
    
    return 0 if success else 1

async def generate_report(success):
    """生成检查报告"""
    print("\n📄 生成检查报告...")
    
    # 报告目录
    reports_dir = project_root / "evaluate_service" / "data" / "results" / "reports"
    logs_dir = project_root / "evaluate_service" / "data" / "results" / "logs"
    
    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # 报告内容
    report = {
        '检查名称': 'EnhancedThemeDiscovery数据保存完整性检查',
        '检查时间': datetime.now().isoformat(),
        '检查结果': '通过' if success else '失败',
        '发现问题': [
            'RelatedThemeFetcher.fetch_themes_with_complete_news_content过滤没有完整内容的主题',
            '导致AI只能分析部分主题'
        ],
        '修复建议': [
            '检查事件保存逻辑，确保original_news.content正确保存',
            '修改fetch_themes_with_complete_news_content，不要过滤主题',
            '或确保所有主题的关联事件都有完整内容'
        ]
    }
    
    # 保存JSON报告
    report_file = reports_dir / f"data_integrity_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 报告已保存: {report_file}")
    
    # 保存文本总结
    summary_file = reports_dir / f"data_integrity_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("数据完整性检查总结\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"检查结果: {'✅ 通过' if success else '❌ 失败'}\n\n")
        f.write("主要发现:\n")
        f.write("  1. RelatedThemeFetcher.fetch_themes_with_complete_news_content\n")
        f.write("     会过滤掉没有完整内容的主题\n")
        f.write("  2. 这导致AI只能分析部分主题\n\n")
        f.write("修复建议:\n")
        f.write("  1. 确保事件保存时original_news.content正确保存\n")
        f.write("  2. 修改主题获取逻辑，不要过滤主题\n")
        f.write("  3. 在集成测试中添加数据完整性验证\n")
    
    print(f"✅ 总结已保存: {summary_file}")

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
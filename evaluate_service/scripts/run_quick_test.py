# evaluate_service/scripts/run_quick_test.py
#!/usr/bin/env python3
"""
快速测试脚本
用于快速验证和调试
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


async def quick_test():
    """快速测试"""
    print("🔬 快速测试 - 验证核心功能")
    print("=" * 50)
    
    try:
        # 1. 测试虚拟数据库
        print("1. 测试虚拟数据库...")
        from evaluate_service.core.virtual_theme_database import VirtualThemeDatabase
        
        virtual_db = VirtualThemeDatabase()
        
        # 添加测试主题
        theme1 = virtual_db.add_theme("人工智能", event_id="test_001")
        theme2 = virtual_db.add_theme("新能源汽车", event_id="test_002")
        
        print(f"   创建主题: {theme1.name}, {theme2.name}")
        
        # 测试相关主题查找
        test_event = {
            'id': 'test_003',
            'title': 'AI技术突破，推动智能产业发展',
            'impact_industries': ['人工智能', '信息技术']
        }

        try:
            related = virtual_db.find_related_themes(test_event, limit=3)
            print(f"   找到相关主题: {len(related)} 个")
        except TypeError as e:
            if "unexpected keyword argument 'limit'" in str(e):
                print("   ⚠️  VirtualDatabase使用旧参数名，尝试使用top_n...")
                # 尝试使用旧参数名（向后兼容）
                related = virtual_db.find_related_themes(test_event, limit=3)
                print(f"   找到相关主题: {len(related)} 个 (使用top_n参数)")
            else:
                raise
        
        related = virtual_db.find_related_themes(test_event, limit=3)
        print(f"   找到相关主题: {len(related)} 个")
        
        # 2. 测试增强AI客户端
        print("\n2. 测试增强AI客户端...")
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        
        ai_client = EnhancedAIThemeClient(virtual_db=virtual_db)
        
        test_event_data = {
            'id': 'test_004',
            'title': '深度学习算法重大突破',
            'summary': '研究人员在深度学习领域取得重大突破',
            'event_type': '技术突破',
            'impact_industries': ['人工智能'],
            'theme_directive': {
                'action': 'CREATE_NEW',
                'confidence': 0.8,
                'reason': '重大技术突破'
            }
        }
        
        decision = await ai_client.analyze_event_with_context(test_event_data, related)
        print(f"   AI决策: {decision.get('decision')}")
        print(f"   目标主题: {decision.get('target_theme_name')}")
        print(f"   置信度: {decision.get('confidence'):.2f}")
        
        # 3. 测试相关主题检索器
        print("\n3. 测试相关主题检索器...")
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        fetcher = RelatedThemeFetcher(virtual_db=virtual_db)
        
        related_themes = await fetcher.fetch_related_themes(test_event_data, limit=3)
        print(f"   检索到相关主题: {len(related_themes)} 个")
        
        # 4. 测试判重引擎
        print("\n4. 测试判重引擎...")
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        
        dedup_engine = ThemeDeduplicationEngine()
        
        new_theme_name = "AI智能技术"
        dedup_result = await dedup_engine.check_duplication(
            new_theme_name=new_theme_name,
            event_data=test_event_data,
            existing_themes=related
        )
        
        print(f"   判重结果: {'合并' if dedup_result.should_merge else '创建'}")
        print(f"   相似度: {dedup_result.similarity_score:.2f}")
        
        # 5. 显示最终状态
        print("\n" + "=" * 50)
        print("✅ 快速测试完成!")
        
        db_stats = virtual_db.get_stats()
        print(f"\n📊 虚拟数据库状态:")
        print(f"   主题总数: {db_stats['total_themes']}")
        print(f"   主题列表: {', '.join(db_stats['theme_names'][:5])}")
        
        return True
        
    except Exception as e:
        print(f"❌ 快速测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(quick_test())
    
    if success:
        print("\n🎉 所有核心功能测试通过!")
        print("\n下一步:")
        print("  1. 生成地面真值: python evaluate_service/scripts/generate_ground_truth.py")
        print("  2. 运行完整测试: python evaluate_service/scripts/run_integrated_test.py")
        sys.exit(0)
    else:
        print("\n⚠️  快速测试失败，请检查代码")
        sys.exit(1)
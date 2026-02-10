# debug_match_dataflow_fixed.py
import asyncio
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_match_with_themes_dataflow():
    """
    专项调试：追踪 match_with_themes 数据流
    修改为测试匹配成功的情况
    """
    logger.info("🚀 开始专项调试：追踪 match_with_themes 数据流")
    
    try:
        # 1. 导入现有组件
        from theme_service.services.theme_service import get_theme_service
        
        # 2. 初始化服务
        theme_service = get_theme_service()
        logger.info("✅ ThemeService 加载成功")
        
        # 3. 创建测试事件数据 - 使用能匹配的数据
        # 根据你的生产日志，使用"半导体"相关的事件关键词
        event_data = {
            'event_id': f'test_debug_{int(datetime.now().timestamp())}',
            'event_type': 'major',
            'title': '半导体产业新闻',
            'ai_analysis': {
                'core_concept': '半导体',
                'industry_keywords': ['半导体', '芯片', '集成电路', '光刻胶', '制造'],
                'concept_confidence': 0.85
            }
        }
        
        logger.info(f"📋 测试事件: {event_data['event_id']}")
        logger.info(f"📋 事件关键词: {event_data['ai_analysis']['industry_keywords']}")
        
        # 4. 创建能匹配的测试题材数据（不依赖数据库）
        logger.info("📥 创建能匹配的测试题材数据...")
        
        # 创建包含"半导体"相关关键词的题材
        themes_formatted = [
            {
                'id': 'semi_001',
                'theme_id': 'semi_001',
                'name': '半导体产业',
                'code': 'SEMI001',
                'keywords': ['半导体', '芯片', '集成电路', '制造', '微电子']
            },
            {
                'id': 'chip_001',
                'theme_id': 'chip_001',
                'name': '芯片设计',
                'code': 'CHIP001',
                'keywords': ['芯片', '设计', '半导体', '集成电路', '微处理器']
            },
            {
                'id': 'ic_001',
                'theme_id': 'ic_001',
                'name': '集成电路',
                'code': 'IC001',
                'keywords': ['集成电路', 'IC', '半导体', '芯片', '电子']
            }
        ]
        
        logger.info(f"📊 测试题材: {len(themes_formatted)} 个")
        
        # 5. 第一步：直接调用 ThemeDiscoveryEngine.match_with_themes
        logger.info("\n" + "="*60)
        logger.info("🔍 第一步：直接调用 ThemeDiscoveryEngine.match_with_themes")
        logger.info("="*60)
        
        if not hasattr(theme_service, 'discovery_engine'):
            logger.error("❌ ThemeService 没有 discovery_engine")
            return None
        
        engine = theme_service.discovery_engine
        
        if not hasattr(engine, 'match_with_themes'):
            logger.error("❌ discovery_engine 没有 match_with_themes 方法")
            return None
        
        # 调用底层方法
        event_type = event_data.get('event_type', 'normal')
        threshold = 0.3 if event_type == 'major' else 0.2
        
        logger.info(f"🎯 调用参数: event_type={event_type}, threshold={threshold}")
        logger.info(f"🎯 题材数量: {len(themes_formatted)}")
        
        try:
            raw_result = await engine.match_with_themes(
                event_data, 
                themes_formatted,
                event_type=event_type,
                threshold=threshold
            )
            
            logger.info(f"✅ 原始 match_result 获取成功")
            logger.info(f"📊 原始结果类型: {type(raw_result)}")
            
            if isinstance(raw_result, dict):
                logger.info(f"📊 原始结果 keys: {list(raw_result.keys())}")
                
                # 详细分析每个字段
                for key, value in raw_result.items():
                    if key == 'themes':
                        themes_list = value
                        logger.info(f"📊 themes 字段类型: {type(themes_list)}")
                        logger.info(f"📊 themes 字段长度: {len(themes_list)}")
                        
                        if themes_list and len(themes_list) > 0:
                            first_item = themes_list[0]
                            logger.info(f"📊 第一个 theme 类型: {type(first_item)}")
                            
                            if isinstance(first_item, dict):
                                logger.info(f"📊 第一个 theme 的 keys: {list(first_item.keys())}")
                                logger.info(f"📊 是否包含 theme_id: {'theme_id' in first_item}")
                                logger.info(f"📊 是否包含 id: {'id' in first_item}")
                                logger.info(f"📊 是否包含 theme_name: {'theme_name' in first_item}")
                                logger.info(f"📊 是否包含 name: {'name' in first_item}")
                            elif hasattr(first_item, '__dict__'):
                                attrs = first_item.__dict__
                                logger.info(f"📊 第一个 theme 的属性: {list(attrs.keys())}")
                                logger.info(f"📊 是否包含 theme_id: hasattr={hasattr(first_item, 'theme_id')}")
                                if hasattr(first_item, 'theme_id'):
                                    logger.info(f"📊 theme_id 值: {first_item.theme_id}")
                        else:
                            logger.warning("⚠️  themes 列表为空")
                    elif key == 'theme_count':
                        themes_len = len(raw_result.get('themes', []))
                        logger.info(f"📊 {key}: {value} (themes长度: {themes_len})")
                    elif key == 'matched':
                        logger.info(f"📊 {key}: {value} - 这是关键！")
                    else:
                        logger.info(f"📊 {key}: {value}")
            
            logger.info(f"✅ 原始 match_result 分析完成")
            
        except Exception as e:
            logger.error(f"❌ 调用 match_with_themes 失败: {e}")
            import traceback
            traceback.print_exc()
            raw_result = None
        
        # 6. 第二步：调用 ThemeService.discover_with_themes
        logger.info("\n" + "="*60)
        logger.info("🔍 第二步：调用 ThemeService.discover_with_themes")
        logger.info("="*60)
        
        try:
            service_result = await theme_service.discover_with_themes(event_data, themes_formatted)
            
            logger.info(f"✅ discover_with_themes 调用成功")
            logger.info(f"📊 服务结果类型: {type(service_result)}")
            
            if isinstance(service_result, dict):
                logger.info(f"📊 服务结果 keys: {list(service_result.keys())}")
                
                # 详细分析每个字段
                for key, value in service_result.items():
                    if key == 'themes':
                        themes_list = value
                        logger.info(f"📊 themes 字段类型: {type(themes_list)}")
                        logger.info(f"📊 themes 字段长度: {len(themes_list)}")
                        
                        if themes_list and len(themes_list) > 0:
                            first_item = themes_list[0]
                            logger.info(f"📊 第一个 theme 类型: {type(first_item)}")
                    elif key == 'best_match':
                        logger.info(f"📊 best_match 存在: {value is not None}")
                        if value:
                            if isinstance(value, dict):
                                logger.info(f"📊 best_match keys: {list(value.keys())}")
                                logger.info(f"📊 best_match theme_id: {value.get('theme_id')}")
                                logger.info(f"📊 best_match id: {value.get('id')}")
                                logger.info(f"📊 best_match theme_name: {value.get('theme_name')}")
                                logger.info(f"📊 best_match name: {value.get('name')}")
                            elif hasattr(value, '__dict__'):
                                attrs = value.__dict__
                                logger.info(f"📊 best_match 属性: {list(attrs.keys())}")
                                logger.info(f"📊 best_match theme_id: {getattr(value, 'theme_id', None)}")
                                logger.info(f"📊 best_match id: {getattr(value, 'id', None)}")
                    else:
                        if key in ['matched', 'theme_count', 'confidence', 'operation', 'status']:
                            logger.info(f"📊 {key}: {value}")
            
            logger.info(f"✅ discover_with_themes 分析完成")
            
            # 7. 第三步：问题诊断
            logger.info("\n" + "="*60)
            logger.info("🔍 第三步：问题诊断")
            logger.info("="*60)
            
            matched = service_result.get('matched', False)
            logger.info(f"📊 匹配情况: matched={matched}")
            
            if matched:
                themes_list = service_result.get('themes', [])
                theme_count = service_result.get('theme_count', 0)
                
                logger.info(f"📊 报告匹配数: {theme_count}")
                logger.info(f"📊 实际themes列表长度: {len(themes_list)}")
                
                if theme_count > 0 and len(themes_list) == 0:
                    logger.error("❌ 严重问题: theme_count > 0 但 themes 列表为空！")
                    
                    if raw_result and raw_result.get('themes'):
                        raw_themes_len = len(raw_result.get('themes', []))
                        logger.info(f"📊 原始 match_with_themes 返回 themes 长度: {raw_themes_len}")
                        
                        if raw_themes_len > 0:
                            logger.error("    问题在 ThemeService.discover_with_themes 方法中")
                            logger.error("    该方法没有正确处理或返回 themes 列表")
                        else:
                            logger.error("    问题在 ThemeDiscoveryEngine.match_with_themes 方法中")
                            logger.error("    该方法返回了空的 themes 列表")
                
                best_match = service_result.get('best_match')
                if not best_match:
                    logger.error("❌ 问题: 没有 best_match 字段")
                    logger.error("    ThemeService.discover_with_themes 方法需要添加 best_match 提取逻辑")
                else:
                    # 检查 best_match 中是否有 theme_id
                    has_theme_id = False
                    if isinstance(best_match, dict):
                        has_theme_id = 'theme_id' in best_match or 'id' in best_match
                    elif hasattr(best_match, 'theme_id') or hasattr(best_match, 'id'):
                        has_theme_id = True
                    
                    if not has_theme_id:
                        logger.error("❌ 问题: best_match 中没有 theme_id 或 id 字段")
            else:
                logger.warning("⚠️  匹配失败，可能是关键词不匹配")
                logger.warning(f"    事件关键词: {event_data['ai_analysis']['industry_keywords']}")
                logger.warning(f"    题材关键词示例: {themes_formatted[0]['keywords'] if themes_formatted else '无'}")
            
            logger.info("\n" + "="*60)
            logger.info("✅ 专项调试完成")
            logger.info("="*60)
            
            return {
                'raw_result': raw_result,
                'service_result': service_result,
                'event_data': event_data,
                'themes': themes_formatted
            }
            
        except Exception as e:
            logger.error(f"❌ 调用 discover_with_themes 失败: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    except Exception as e:
        logger.error(f"❌ 调试过程出错: {e}")
        import traceback
        traceback.print_exc()
        return None

async def main():
    """主函数"""
    print("\n" + "="*80)
    print("🎯 MATCH_WITH_THEMES 数据流专项调试（匹配成功测试版）")
    print("="*80)
    
    try:
        result = await debug_match_with_themes_dataflow()
        
        if result:
            print("\n" + "="*80)
            print("📋 问题总结与修复方案")
            print("="*80)
            
            raw_result = result.get('raw_result', {})
            service_result = result.get('service_result', {})
            
            matched = service_result.get('matched', False)
            
            if not matched:
                print("⚠️  警告: 测试匹配失败")
                print("     这可能是关键词不匹配导致的测试问题")
                print("     但在生产环境中，同样的逻辑匹配成功了")
                print("     请检查你的生产环境题材数据和测试数据是否一致")
            else:
                print("✅ 测试匹配成功！")
                
                # 问题1: themes 列表是否为空
                themes_list = service_result.get('themes', [])
                theme_count = service_result.get('theme_count', 0)
                
                if theme_count > 0 and len(themes_list) == 0:
                    print(f"   ❌ themes 列表为空但 theme_count={theme_count}")
                    
                    if raw_result and raw_result.get('themes'):
                        raw_len = len(raw_result.get('themes', []))
                        if raw_len > 0:
                            print(f"      问题定位: ThemeService.discover_with_themes 方法")
                            print(f"      需要修改: 正确传递 themes 列表")
                        else:
                            print(f"      问题定位: ThemeDiscoveryEngine.match_with_themes 方法")
                            print(f"      需要修改: 确保返回非空的 themes 列表")
                    else:
                        print(f"      问题定位: 整个匹配链路")
                else:
                    print(f"   ✅ themes 列表正常: {len(themes_list)} 个")
                
                # 问题2: best_match 是否存在且有 theme_id
                best_match = service_result.get('best_match')
                if best_match:
                    has_theme_id = False
                    if isinstance(best_match, dict):
                        has_theme_id = 'theme_id' in best_match or 'id' in best_match
                    elif hasattr(best_match, 'theme_id') or hasattr(best_match, 'id'):
                        has_theme_id = True
                    
                    if not has_theme_id:
                        print(f"   ❌ best_match 中没有 theme_id")
                        print(f"      问题定位: MatchResult 对象转换逻辑")
                    else:
                        print(f"   ✅ best_match 包含 theme_id")
                else:
                    print(f"   ❌ 没有 best_match 字段")
                    print(f"      问题定位: ThemeService.discover_with_themes 方法")
            
            print("\n2. 需要修改的代码:")
            print("   根据你的生产日志，问题可能是:")
            print("   - ThemeDiscoveryEngine.match_with_themes 返回了 themes 列表")
            print("   - 但 ThemeService.discover_with_themes 没有正确提取 best_match")
            
            print("\n   请检查这两个方法:")
            print("   - theme_service/engines/theme_discovery_engine.py")
            print("     查看 match_with_themes 方法的 themes 列表格式")
            print("   - theme_service/services/theme_service.py")
            print("     查看 discover_with_themes 方法中的 best_match 提取逻辑")
            
        else:
            print("❌ 调试失败，无法获取结果")
        
    except KeyboardInterrupt:
        print("\n🛑 调试被中断")
    except Exception as e:
        print(f"❌ 调试过程中出错: {e}")

if __name__ == "__main__":
    asyncio.run(main())
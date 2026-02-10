#!/usr/bin/env python3
"""
集成测试运行器 - 数据修复+AI优化版
修复：1. 事件数据完整性 2. AI分析逻辑 3. 主题名称生成
"""
import asyncio
import logging
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/76_dataset_final_fix.log')
    ]
)
logger = logging.getLogger(__name__)

def enhance_event_data_fixed(event_data: dict) -> dict:
    """
    🚀 关键修复：增强事件数据，确保有完整内容
    
    新数据结构：
    {
        "news_id": "...",
        "event_info": {...},
        "theme_discovery_directive": {...},
        "original_news": {
            "title": "...",
            "content": "完整内容...",  # 🚀 关键
            "date": "..."
        }
    }
    """
    enhanced = event_data.copy()
    
    # 1. 提取ID
    event_id = enhanced.get('news_id', enhanced.get('id', f'event_{int(time.time()*1000)}'))
    enhanced['id'] = event_id
    
    # 2. 🚀 提取完整内容 - 修复逻辑
    full_content = ""
    
    # 首先检查original_news.content
    if 'original_news' in enhanced and isinstance(enhanced['original_news'], dict):
        original_news = enhanced['original_news']
        if 'content' in original_news and original_news['content']:
            full_content = original_news['content']
            logger.debug(f"从original_news.content获取内容: {len(full_content)}字符")
        elif 'title' in original_news:
            full_content = original_news['title']
    
    # 如果没有内容，从其他字段提取
    if not full_content:
        for field in ['summary', 'content_preview', 'body']:
            if field in enhanced and enhanced[field]:
                full_content = enhanced[field]
                break
    
    # 3. 确保有标题
    if 'title' not in enhanced or not enhanced['title']:
        if 'original_news' in enhanced and isinstance(enhanced['original_news'], dict):
            enhanced['title'] = enhanced['original_news'].get('title', f"事件 {event_id}")
        else:
            # 从内容提取标题
            if full_content:
                enhanced['title'] = full_content[:50] + '...' if len(full_content) > 50 else full_content
            else:
                enhanced['title'] = f"事件 {event_id}"
    
    # 4. 构建完整的事件数据结构（符合新结构）
    final_event = {
        'id': event_id,
        'news_id': event_id,
        'title': enhanced['title'],
        'full_content': full_content,
        'content_length': len(full_content),
        'has_full_content': len(full_content) > 100,
        
        # 事件信息
        'event_info': enhanced.get('event_info', {
            'event_type': 'unknown',
            'impact_industries': [],
            'direction': '中性',
            'event_confidence': 0.5
        }),
        
        # 主题发现指令
        'theme_discovery_directive': enhanced.get('theme_discovery_directive', {
            'action': 'CLUSTER',
            'decision_confidence': 0.5,
            'reason': '自动处理'
        }),
        
        # 原始新闻
        'original_news': {
            'title': enhanced['title'],
            'content': full_content,
            'date': enhanced.get('original_news', {}).get('date', datetime.now().strftime('%Y-%m-%d'))
        }
    }
    
    # 5. 记录数据质量
    content_len = len(full_content)
    if content_len < 50:
        logger.warning(f"⚠️  事件 {event_id} 内容过短: {content_len}字符")
    elif content_len > 100:
        logger.info(f"✅ 事件 {event_id} 有完整内容: {content_len}字符")
    
    return final_event

async def create_initial_test_themes(db_manager):
    """创建初始测试主题，模拟真实场景"""
    logger.info("📚 创建初始测试主题...")
    
    initial_themes = [
        {
            "name": "人工智能技术",
            "description": "人工智能、机器学习、深度学习等技术",
            "keywords": ["AI", "人工智能", "机器学习", "深度学习"],
            "discovery_source": "manual",
            "discovery_confidence": 0.9
        },
        {
            "name": "智能硬件",
            "description": "智能眼镜、可穿戴设备等硬件产品",
            "keywords": ["智能硬件", "可穿戴", "智能眼镜", "AR眼镜"],
            "discovery_source": "manual",
            "discovery_confidence": 0.8
        },
        {
            "name": "消费电子",
            "description": "消费电子产品和技术",
            "keywords": ["消费电子", "电子产品", "智能设备"],
            "discovery_source": "manual",
            "discovery_confidence": 0.7
        }
    ]
    
    created = []
    for theme_data in initial_themes:
        try:
            theme = await db_manager.create_theme(**theme_data)
            created.append(theme)
            logger.info(f"  ✅ 创建主题: {theme.name}")
        except Exception as e:
            logger.warning(f"  创建主题失败: {theme_data['name']}, 错误: {e}")
    
    return created

async def main():
    """主测试函数"""
    logger.info("🚀 启动76个数据集完整评估（数据修复+AI优化版）")
    
    try:
        # 🎯 数据集路径
        DATASET_PATHS = {
            "processed_events": "evaluate_service/data/processed/validation_events_fixed.json",
            "ground_truth": "evaluate_service/config/ground_truth_correct.json"
        }
        
        # 验证数据集文件
        logger.info("📂 验证数据集文件...")
        for name, path in DATASET_PATHS.items():
            if os.path.exists(path):
                logger.info(f"✅ 数据集 '{name}' 存在: {path}")
            else:
                logger.error(f"❌ 数据集 '{name}' 不存在: {path}")
                return 1
        
        # ========== 初始化系统 ==========
        logger.info("🔧 初始化系统组件...")
        
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.client import DatabaseClient
        from database_service.pure_data_fetcher import PureDataFetcher
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        # 1. 数据库连接
        logger.info("  1. 初始化数据库...")
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 2. 创建初始主题（模拟真实环境）
        await create_initial_test_themes(db_manager)
        
        # 3. 创建数据获取器
        logger.info("  2. 创建数据获取器...")
        data_fetcher = PureDataFetcher(db_manager)
        
        # 4. 创建数据库客户端
        logger.info("  3. 创建数据库客户端...")
        db_client = DatabaseClient(db_manager)
        
        # 5. 创建AI客户端
        logger.info("  4. 创建AI客户端...")
        ai_client = EnhancedAIThemeClient()
        
        # 6. 创建相似性分析器
        logger.info("  5. 创建相似性分析器...")
        similarity_analyzer = AIThemeSimilarityAnalyzer(ai_client.llm_parser)
        
        # 7. 创建主题发现引擎
        logger.info("  6. 创建主题发现引擎...")
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            database_client=db_client,
            similarity_analyzer=similarity_analyzer,
            data_fetcher=data_fetcher,
            config={
                'fast_track_threshold': 0.8,
                'review_threshold': 0.6,
                'ignore_threshold': 0.3,
                'enable_detailed_logging': True,
                'min_content_length': 30,  # 最小内容长度要求
                'require_full_content': False  # 不要求完整内容
            }
        )
        
        engine_info = await engine.get_engine_info()
        logger.info(f"✅ 系统初始化完成: {engine_info['engine_version']}")
        
        # ========== 加载76个处理后的真实事件 ==========
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 加载76个真实处理事件")
        logger.info(f"{'='*60}")
        
        with open(DATASET_PATHS["processed_events"], 'r', encoding='utf-8') as f:
            processed_data = json.load(f)
        
        # 提取事件
        if isinstance(processed_data, dict) and 'events' in processed_data:
            raw_events = processed_data['events']
            total_events = len(raw_events)
            logger.info(f"✅ 从字典结构中提取到 {total_events} 个真实事件")
        elif isinstance(processed_data, list):
            raw_events = processed_data
            total_events = len(raw_events)
            logger.info(f"✅ 成功加载 {total_events} 个真实事件")
        else:
            logger.error(f"❌ 数据格式错误")
            return 1
        
        # 数据结构分析
        logger.info("🔍 数据结构分析:")
        if raw_events and len(raw_events) > 0:
            sample = raw_events[0]
            logger.info(f"  事件数量: {len(raw_events)}")
            logger.info(f"  事件字段: {list(sample.keys())}")
            
            if 'original_news' in sample and isinstance(sample['original_news'], dict):
                logger.info(f"  original_news字段: {list(sample['original_news'].keys())}")
                if 'content' in sample['original_news']:
                    content = sample['original_news']['content']
                    logger.info(f"  内容长度: {len(content)}字符")
                    logger.info(f"  样本: {content[:100]}...")
        
        # 🚀 关键修复：增强事件数据，确保完整性
        logger.info("🚀 修复和增强事件数据...")
        processed_events = []
        content_stats = {
            'total': 0,
            'has_content': 0,
            'short_content': 0,
            'avg_length': 0
        }
        
        for i, raw_event in enumerate(raw_events):
            enhanced_event = enhance_event_data_fixed(raw_event)
            processed_events.append(enhanced_event)
            
            # 统计内容信息
            content_len = len(enhanced_event.get('full_content', ''))
            content_stats['total'] += 1
            content_stats['avg_length'] += content_len
            
            if content_len > 50:
                content_stats['has_content'] += 1
            if content_len < 30:
                content_stats['short_content'] += 1
            
            if i < 3:  # 显示前3个事件的信息
                event_id = enhanced_event.get('id', f'event_{i}')
                content_len = len(enhanced_event.get('full_content', ''))
                title = enhanced_event.get('title', '')[:40]
                logger.info(f"   样本{i+1}: {event_id} - '{title}' - 内容:{content_len}字符")
        
        content_stats['avg_length'] = content_stats['avg_length'] / max(content_stats['total'], 1)
        logger.info(f"✅ 事件数据增强完成，共 {len(processed_events)} 个事件")
        logger.info(f"📊 内容统计: 有内容 {content_stats['has_content']}/{content_stats['total']}, "
                   f"平均长度: {content_stats['avg_length']:.0f}字符")
        
        # ========== 处理所有76个事件 ==========
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 开始处理全部 {total_events} 个真实事件")
        logger.info(f"{'='*60}")
        
        start_time = datetime.now()
        results = []
        stats = {
            'total': total_events,
            'success': 0,
            'failed': 0,
            'created': 0,
            'merged': 0,
            'ignored': 0,
            'themes_created': defaultdict(int)
        }
        
        for i, event in enumerate(processed_events):
            event_id = event.get('id', f'event_{i}')
            title = event.get('title', '')[:50]
            
            logger.info(f"\n[{i+1}/{total_events}] 处理事件: {event_id}")
            logger.info(f"   标题: {title}")
            logger.info(f"   内容长度: {len(event.get('full_content', ''))}字符")
            
            try:
                # 处理事件
                result = await engine.process_single_event(event)
                results.append(result)
                
                # 更新统计
                status = result.get('status', 'unknown')
                if status in ['created', 'merged', 'ignored']:
                    stats['success'] += 1
                    stats[status] += 1
                    
                    if status == 'created':
                        theme_name = result.get('theme_name', '')
                        if theme_name:
                            stats['themes_created'][theme_name] += 1
                            logger.info(f"   ✅ 创建主题: '{theme_name}'")
                    elif status == 'merged':
                        theme_name = result.get('theme_name', '')
                        confidence = result.get('confidence', 0)
                        logger.info(f"   ✅ 合并到: '{theme_name}' (置信度: {confidence:.2f})")
                    elif status == 'ignored':
                        reason = result.get('reason', '')[:50]
                        logger.info(f"   ⏭️  已忽略: {reason}")
                
                elif status == 'failed':
                    stats['failed'] += 1
                    error_msg = result.get('error', '未知错误')[:50]
                    logger.warning(f"   ❌ 失败: {error_msg}")
                
                else:
                    stats['failed'] += 1
                    logger.warning(f"   ❓ 未知状态: {status}")
                
                # 进度报告
                if (i + 1) % 10 == 0:
                    progress = (i + 1) / total_events * 100
                    current_time = (datetime.now() - start_time).total_seconds()
                    logger.info(f"   📊 进度: {i+1}/{total_events} ({progress:.1f}%), 耗时: {current_time:.1f}s")
                
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"   💥 异常: {str(e)[:80]}")
                import traceback
                logger.debug(f"   异常详情: {traceback.format_exc()}")
        
        # ========== 最终统计和分析 ==========
        total_time = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📈 76个数据集评估完成!")
        logger.info(f"{'='*60}")
        logger.info(f"📊 处理统计:")
        logger.info(f"   总事件数: {stats['total']}")
        logger.info(f"   成功: {stats['success']} (创建: {stats['created']}, 合并: {stats['merged']}, 忽略: {stats['ignored']})")
        logger.info(f"   失败: {stats['failed']}")
        
        if stats['total'] > 0:
            success_rate = stats['success'] / stats['total'] * 100
            logger.info(f"   成功率: {success_rate:.1f}%")
        
        logger.info(f"   总耗时: {total_time:.1f}s")
        logger.info(f"   平均耗时: {total_time / max(stats['total'], 1):.2f}s/事件")
        
        # 主题创建统计
        if stats['themes_created']:
            logger.info(f"\n🏷️  AI创建的主题 (按事件数排序):")
            sorted_themes = sorted(stats['themes_created'].items(), key=lambda x: x[1], reverse=True)
            for theme_name, count in sorted_themes[:20]:  # 显示前20个
                logger.info(f"   {theme_name}: {count}个事件")
        
        # 数据库最终状态
        try:
            final_themes = await db_manager.get_all_active_themes(limit=50)
            logger.info(f"\n📁 数据库最终状态:")
            logger.info(f"   主题总数: {len(final_themes)}")
            if final_themes:
                # 按热度排序
                sorted_themes = sorted(final_themes, key=lambda x: x.heat_score, reverse=True)
                logger.info(f"   热门主题 (按热度):")
                for theme in sorted_themes[:10]:
                    logger.info(f"   • {theme.name} (热度: {theme.heat_score}, 事件: {len(await db_manager.get_theme_events(theme.id, limit=100))})")
        except Exception as e:
            logger.warning(f"   获取数据库状态失败: {e}")
        
        # 生成详细报告
        report_path = f"/tmp/76_dataset_final_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_data = {
            'evaluation_time': datetime.now().isoformat(),
            'system_version': engine_info['engine_version'],
            'stats': stats,
            'content_statistics': content_stats,
            'themes_created': dict(stats['themes_created']),
            'processing_times': {
                'total_seconds': total_time,
                'seconds_per_event': total_time / max(stats['total'], 1),
                'events_per_minute': stats['total'] / (total_time / 60) if total_time > 0 else 0
            },
            'data_quality': {
                'events_with_content': content_stats['has_content'],
                'short_content_events': content_stats['short_content'],
                'avg_content_length': content_stats['avg_length']
            }
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n📄 详细报告已保存: {report_path}")
        
        # 总结评估
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 最终评估结果")
        logger.info(f"{'='*60}")
        
        num_themes = len(stats['themes_created'])
        
        # 关键指标分析
        logger.info(f"\n🔍 关键指标:")
        logger.info(f"  创建的主题数量: {num_themes}")
        logger.info(f"  事件平均内容长度: {content_stats['avg_length']:.0f}字符")
        logger.info(f"  有内容的事件比例: {content_stats['has_content']/max(content_stats['total'],1)*100:.1f}%")
        
        if num_themes < 15 and num_themes > 5:
            logger.info(f"  🎉 主题数量合理 ({num_themes}个)，解决了过度细分问题!")
        elif num_themes <= 5:
            logger.info(f"  ✅ 主题数量较少 ({num_themes}个)，聚类效果良好")
        elif num_themes >= 20:
            logger.info(f"  ⚠️  主题数量偏多 ({num_themes}个)，可能存在过度细分")
        else:
            logger.info(f"  ✅ 主题数量可接受 ({num_themes}个)")
        
        # 成功率分析
        success_ratio = stats['success'] / max(stats['total'], 1)
        if success_ratio > 0.8:
            logger.info(f"  🎉 高成功率: {success_ratio:.1%}")
        elif success_ratio > 0.5:
            logger.info(f"  ✅ 可接受成功率: {success_ratio:.1%}")
        else:
            logger.info(f"  ⚠️  成功率有待提高: {success_ratio:.1%}")
        
        # 建议
        logger.info(f"\n💡 建议:")
        if content_stats['avg_length'] < 100:
            logger.info(f"  • 提升事件内容质量，平均长度只有 {content_stats['avg_length']:.0f}字符")
        if success_ratio < 0.7:
            logger.info(f"  • 优化AI分析逻辑，提高处理成功率")
        if num_themes >= 20:
            logger.info(f"  • 调整AI聚类参数，减少主题数量")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 评估完成!")
        logger.info(f"{'='*60}")
        
        return 0 if success_ratio > 0.5 else 1
        
    except Exception as e:
        logger.error(f"❌ 评估失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 检查API密钥
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("⚠️  警告: DEEPSEEK_API_KEY环境变量未设置")
        print("请在运行前设置: export DEEPSEEK_API_KEY='your-api-key'")
        sys.exit(1)
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
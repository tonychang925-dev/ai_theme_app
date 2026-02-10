"""
AI内容验证测试 - 专门检查AI是否收到完整新闻内容
"""
#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class AIContentValidationTester:
    """AI内容验证测试器"""
    
    def __init__(self):
        self.data_dir = project_root / "evaluate_service" / "data" / "processed"
        self.db_manager = None
    
    async def setup(self):
        """初始化"""
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.config import DatabaseConfig
        
        db_config = DatabaseConfig()
        self.db_manager = MemoryDatabaseManager(db_config)
        await self.db_manager.connect()
        
        logger.info("✅ 数据库初始化完成")
    
    async def test_ai_receives_full_content(self):
        """测试AI是否收到完整内容"""
        logger.info(f"\n{'='*100}")
        logger.info("🔥 测试AI是否收到完整新闻内容")
        logger.info(f"{'='*100}")
        
        try:
            # 1. 创建测试数据
            await self._create_test_data()
            
            # 2. 获取一个测试事件
            test_event = await self._get_test_event()
            
            # 3. 模拟EnhancedThemeDiscovery的数据获取流程
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            
            data_fetcher = PureDataFetcher(self.db_manager)
            theme_fetcher = RelatedThemeFetcher(data_fetcher)
            
            # 4. 获取主题（应该包含完整内容）
            logger.info("🔍 获取相关主题...")
            themes = await theme_fetcher.fetch_relevant_themes(test_event, limit=5)
            
            logger.info(f"📊 获取到 {len(themes)} 个主题")
            
            # 5. 🔥🔥🔥 关键验证：检查主题是否包含完整新闻内容
            await self._validate_theme_content_completeness(themes)
            
            # 6. 模拟AI提示词生成
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            analyzer = AIThemeSimilarityAnalyzer(None)  # 不使用实际LLM，只测试提示词
            
            # 使用反射调用私有方法（仅用于测试）
            prompt = analyzer._build_enhanced_prompt(test_event, themes)
            
            # 7. 🔥🔥🔥 验证提示词是否包含完整内容
            await self._validate_prompt_content_completeness(prompt, test_event, themes)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _create_test_data(self):
        """创建测试数据"""
        # 清空数据库
        if hasattr(self.db_manager, 'clear_all_data'):
            await self.db_manager.clear_all_data()
        
        # 创建第一个事件（智能眼镜发布）
        event1 = {
            'id': 'AI_AR眼镜_001',
            'news_id': 'AI_AR眼镜_001',
            'title': 'Meta与Oakley合作智能眼镜产品发布会',
            'full_content': 'Meta与Oakley合作开发的智能眼镜产品于6月20日举行发布会。这款智能眼镜集成了AR技术和AI助手，可以实时翻译、导航和拍照。产品定位高端消费市场，预计售价299美元。',
            'content_length': 89,
            'has_full_content': True,
            'event_info': {
                'event_type': '产品发布',
                'impact_industries': ['消费电子', '可穿戴设备', '人工智能']
            },
            'original_news': {
                'title': 'Meta与Oakley合作智能眼镜产品发布会',
                'content': 'Meta与Oakley合作开发的智能眼镜产品于6月20日举行发布会。这款智能眼镜集成了AR技术和AI助手，可以实时翻译、导航和拍照。产品定位高端消费市场，预计售价299美元。',
                'date': '2025-06-20'
            }
        }
        
        await self.db_manager.create_or_update_event(event1)
        
        # 创建第一个主题
        theme1 = await self.db_manager.create_theme(
            name='智能眼镜发布',
            description='智能眼镜产品发布相关',
            keywords=['智能眼镜', 'AR眼镜', '发布', '消费电子']
        )
        
        # 创建关联
        await self.db_manager.create_event_theme_relation(
            event_id='AI_AR眼镜_001',
            theme_id=theme1.id,
            confidence=0.9,
            confidence_level='high'
        )
        
        # 创建第二个事件（技术突破）
        event2 = {
            'id': 'AI_AR眼镜_003',
            'news_id': 'AI_AR眼镜_003',
            'title': '英伟达公开AR眼镜专利',
            'full_content': '1月3日电，美国专利及商标局官网显示，英伟达公开了一项AR眼镜专利（US20250004275A1），名为"无背光增强现实数字全息技术"。该技术可实现更高分辨率的AR显示效果，同时降低功耗。这是AR显示技术的重要突破。',
            'content_length': 102,
            'has_full_content': True,
            'event_info': {
                'event_type': '技术突破',
                'impact_industries': ['半导体', '显示技术', '增强现实']
            },
            'original_news': {
                'title': '英伟达公开AR眼镜专利',
                'content': '1月3日电，美国专利及商标局官网显示，英伟达公开了一项AR眼镜专利（US20250004275A1），名为"无背光增强现实数字全息技术"。该技术可实现更高分辨率的AR显示效果，同时降低功耗。这是AR显示技术的重要突破。',
                'date': '2025-01-03'
            }
        }
        
        await self.db_manager.create_or_update_event(event2)
        
        # 创建第二个主题
        theme2 = await self.db_manager.create_theme(
            name='AR眼镜技术突破',
            description='AR眼镜相关技术研发突破',
            keywords=['AR技术', '专利', '技术突破', '显示技术']
        )
        
        # 创建关联
        await self.db_manager.create_event_theme_relation(
            event_id='AI_AR眼镜_003',
            theme_id=theme2.id,
            confidence=0.9,
            confidence_level='high'
        )
        
        logger.info("✅ 创建测试数据完成")
        logger.info(f"   事件数: 2")
        logger.info(f"   主题数: 2")
        logger.info(f"   关联数: 2")
    
    async def _get_test_event(self) -> Dict:
        """获取测试事件"""
        return {
            'news_id': 'AI_AR眼镜_002',
            'original_news': {
                'title': 'Meta联手Oakley推出智能眼镜，为运动设计挑战运动相机',
                'content': 'Meta与Oakley合作推出的智能眼镜专为运动场景设计，内置摄像头可以拍摄第一人称视角的运动视频。产品重量仅45克，续航8小时，防水等级IPX7。这款眼镜挑战了传统运动相机的市场。',
                'date': '2025-06-25'
            },
            'event_info': {
                'event_type': '产品发布',
                'impact_industries': ['消费电子', '运动装备', '摄像设备']
            }
        }
    
    async def _validate_theme_content_completeness(self, themes: List[Dict]):
        """验证主题内容完整性"""
        logger.info(f"\n{'='*80}")
        logger.info("🔍 验证主题内容完整性")
        logger.info(f"{'='*80}")
        
        if not themes:
            logger.error("❌ 没有获取到主题")
            return
        
        for i, theme in enumerate(themes):
            theme_name = theme.get('name', f'主题_{i}')
            logger.info(f"\n📋 主题 {i+1}: {theme_name}")
            
            # 检查是否有完整内容标记
            has_complete_content = theme.get('has_complete_content', False)
            logger.info(f"   是否有完整内容标记: {'✅' if has_complete_content else '❌'}")
            
            # 检查关联新闻内容
            related_news = theme.get('related_news_full_contents', [])
            logger.info(f"   关联新闻数: {len(related_news)}")
            
            if related_news:
                for j, news in enumerate(related_news[:2]):  # 只检查前2个
                    logger.info(f"\n   新闻 {j+1}: {news.get('title', '无标题')}")
                    
                    # 🔥🔥🔥 关键检查：是否有完整内容
                    full_content = news.get('content', '')
                    if full_content:
                        content_length = len(full_content)
                        logger.info(f"       内容长度: {content_length} 字符")
                        logger.info(f"       内容预览: {full_content[:100]}...")
                        
                        if content_length < 50:
                            logger.warning(f"       ⚠️  内容可能不完整，只有 {content_length} 字符")
                    else:
                        logger.error(f"       ❌ 没有完整内容！")
                        
                    # 检查其他字段
                    event_id = news.get('event_id', '')
                    if event_id:
                        logger.info(f"       事件ID: {event_id}")
            else:
                logger.error(f"   ❌ 主题没有关联新闻内容！")
            
            logger.info(f"   {'─'*60}")
    
    async def _validate_prompt_content_completeness(self, prompt: str, event: Dict, themes: List[Dict]):
        """验证提示词内容完整性"""
        logger.info(f"\n{'='*80}")
        logger.info("🔍 验证AI提示词内容完整性")
        logger.info(f"{'='*80}")
        
        # 1. 检查新事件内容
        event_content = event.get('original_news', {}).get('content', '')
        logger.info(f"📋 新事件内容检查:")
        logger.info(f"   内容长度: {len(event_content)} 字符")
        
        if event_content in prompt:
            logger.info(f"   ✅ 新事件完整内容在提示词中")
            # 显示位置
            pos = prompt.find(event_content[:50])
            if pos != -1:
                logger.info(f"   内容位置: 第{pos}字符处")
        else:
            logger.error(f"   ❌ 新事件完整内容不在提示词中！")
        
        # 2. 检查主题关联内容
        logger.info(f"\n📚 主题关联内容检查:")
        
        total_news_in_prompt = 0
        for i, theme in enumerate(themes):
            theme_name = theme.get('name', f'主题_{i}')
            related_news = theme.get('related_news_full_contents', [])
            
            logger.info(f"\n   主题 {i+1}: {theme_name}")
            logger.info(f"       关联新闻数: {len(related_news)}")
            
            for j, news in enumerate(related_news[:2]):
                news_content = news.get('content', '')
                if news_content:
                    # 检查内容是否在提示词中
                    if news_content[:100] in prompt:  # 检查前100字符
                        logger.info(f"       新闻 {j+1}: ✅ 内容在提示词中 ({len(news_content)}字符)")
                        total_news_in_prompt += 1
                    else:
                        logger.error(f"       新闻 {j+1}: ❌ 内容不在提示词中！")
        
        # 3. 统计结果
        logger.info(f"\n📊 内容完整性统计:")
        logger.info(f"   新事件内容: {'✅' if event_content in prompt else '❌'}")
        logger.info(f"   主题关联新闻内容: {total_news_in_prompt} 个在提示词中")
        
        total_news = sum(len(t.get('related_news_full_contents', [])) for t in themes)
        logger.info(f"   总关联新闻数: {total_news}")
        
        if total_news > 0:
            coverage = total_news_in_prompt / total_news * 100
            logger.info(f"   内容覆盖率: {coverage:.1f}%")
            
            if coverage < 80:
                logger.warning(f"   ⚠️  内容覆盖率不足，AI可能无法进行深度分析")
        
        # 4. 显示提示词片段（用于调试）
        logger.info(f"\n🔍 提示词内容片段（前500字符）:")
        logger.info(f"{prompt[:500]}...")

async def main():
    """主函数"""
    print("🚀 开始AI内容完整性验证测试...")
    
    tester = AIContentValidationTester()
    
    try:
        await tester.setup()
        success = await tester.test_ai_receives_full_content()
        
        if success:
            print("\n✅ AI内容完整性验证完成")
            print("📋 请查看详细日志确认AI是否收到完整新闻内容")
            return 0
        else:
            print("\n❌ AI内容完整性验证失败")
            return 1
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
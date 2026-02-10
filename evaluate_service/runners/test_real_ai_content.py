# evaluate_service/runners/test_real_ai_content.py
"""
真实AI内容验证测试 - 使用真实AI验证是否收到完整内容
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

class RealAIContentTester:
    """真实AI内容测试器"""
    
    def __init__(self):
        self.db_manager = None
    
    async def setup(self):
        """初始化"""
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.config import DatabaseConfig
        
        db_config = DatabaseConfig()
        self.db_manager = MemoryDatabaseManager(db_config)
        await self.db_manager.connect()
        
        logger.info("✅ 数据库初始化完成")
        
        # 创建测试数据
        await self._create_test_data()
    
    async def _create_test_data(self):
        """创建测试数据"""
        # 清空数据库
        if hasattr(self.db_manager, 'clear_all_data'):
            await self.db_manager.clear_all_data()
        
        # 创建测试事件和主题
        test_data = [
            {
                'event_id': 'AI_AR眼镜_001',
                'title': 'Meta与Oakley合作智能眼镜产品发布会',
                'content': 'Meta与Oakley合作开发的智能眼镜产品于6月20日举行发布会。这款智能眼镜集成了AR技术和AI助手，可以实时翻译、导航和拍照。产品定位高端消费市场，预计售价299美元。',
                'theme_name': '智能眼镜发布',
                'theme_desc': '智能眼镜产品发布相关',
                'keywords': ['智能眼镜', 'AR眼镜', '发布', '消费电子']
            },
            {
                'event_id': 'AI_AR眼镜_003', 
                'title': '英伟达公开AR眼镜专利',
                'content': '1月3日电，美国专利及商标局官网显示，英伟达公开了一项AR眼镜专利（US20250004275A1），名为"无背光增强现实数字全息技术"。该技术可实现更高分辨率的AR显示效果，同时降低功耗。这是AR显示技术的重要突破。',
                'theme_name': 'AR眼镜技术突破',
                'theme_desc': 'AR眼镜相关技术研发突破',
                'keywords': ['AR技术', '专利', '技术突破', '显示技术']
            }
        ]
        
        for data in test_data:
            # 创建事件
            event = {
                'id': data['event_id'],
                'news_id': data['event_id'],
                'title': data['title'],
                'full_content': data['content'],
                'content_length': len(data['content']),
                'has_full_content': True,
                'event_info': {
                    'event_type': '产品发布' if '发布' in data['theme_name'] else '技术突破',
                    'impact_industries': ['消费电子', '可穿戴设备']
                },
                'original_news': {
                    'title': data['title'],
                    'content': data['content'],
                    'date': '2025-01-01'
                }
            }
            
            await self.db_manager.create_or_update_event(event)
            
            # 创建主题
            theme = await self.db_manager.create_theme(
                name=data['theme_name'],
                description=data['theme_desc'],
                keywords=data['keywords']
            )
            
            # 创建关联
            await self.db_manager.create_event_theme_relation(
                event_id=data['event_id'],
                theme_id=theme.id,
                confidence=0.9,
                confidence_level='high'
            )
        
        logger.info("✅ 测试数据创建完成")
    
    async def test_real_ai_analysis(self):
        """测试真实AI分析（查看实际提示词）"""
        logger.info(f"\n{'='*100}")
        logger.info("🤖 测试真实AI分析（验证提示词内容）")
        logger.info(f"{'='*100}")
        
        try:
            # 创建真实AI分析器
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            llm_parser = ReliableDeepSeekParser(
                config={'max_retries': 1, 'timeout': 30}  # 减少重试和超时，只测试提示词
            )
            
            analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            # 创建测试事件
            test_event = {
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
            
            # 获取主题
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            
            data_fetcher = PureDataFetcher(self.db_manager)
            theme_fetcher = RelatedThemeFetcher(data_fetcher)
            
            themes = await theme_fetcher.fetch_relevant_themes(test_event, limit=5)
            
            logger.info(f"📊 获取到 {len(themes)} 个主题")
            
            # 🔥🔥🔥 关键：使用猴子补丁来捕获实际的提示词
            original_build_prompt = analyzer._build_enhanced_prompt
            
            captured_prompts = []
            
            def capture_prompt(event, themes):
                prompt = original_build_prompt(event, themes)
                captured_prompts.append(prompt)
                return prompt
            
            # 替换方法
            analyzer._build_enhanced_prompt = capture_prompt
            
            try:
                # 执行分析（会触发提示词生成）
                await analyzer.analyze_with_theme_extraction(test_event, themes)
            except Exception as e:
                logger.info(f"预期错误（因为我们只关心提示词）: {e}")
            
            # 恢复原方法
            analyzer._build_enhanced_prompt = original_build_prompt
            
            # 🔥🔥🔥 分析捕获的提示词
            if captured_prompts:
                prompt = captured_prompts[0]
                await self._analyze_prompt_content(prompt, test_event, themes)
            else:
                logger.error("❌ 没有捕获到提示词")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _analyze_prompt_content(self, prompt: str, event: Dict, themes: List[Dict]):
        """分析提示词内容"""
        logger.info(f"\n{'='*80}")
        logger.info("🔍 分析实际AI提示词内容")
        logger.info(f"{'='*80}")
        
        # 1. 检查是否使用新版本的提示词
        if "🔥🔥🔥 核心要求：必须基于完整新闻内容进行分析" in prompt:
            logger.info("✅ 使用的是修复后的新版本提示词")
        else:
            logger.error("❌ 仍然在使用旧版本提示词！")
            logger.error("请确认 ai_similarity_analyzer.py 中的 _build_enhanced_prompt 方法已更新")
        
        # 2. 检查新事件完整内容
        event_content = event.get('original_news', {}).get('content', '')
        logger.info(f"\n📋 新事件内容检查:")
        logger.info(f"   内容长度: {len(event_content)} 字符")
        
        if event_content in prompt:
            logger.info(f"   ✅ 新事件完整内容在提示词中")
        else:
            logger.error(f"   ❌ 新事件完整内容不在提示词中！")
        
        # 3. 检查主题关联内容
        logger.info(f"\n📚 主题关联内容检查:")
        
        content_keywords = ['完整内容:', 'full_content:', '关联新闻']
        found_keywords = [kw for kw in content_keywords if kw in prompt]
        
        if found_keywords:
            logger.info(f"   ✅ 提示词包含完整内容关键词: {found_keywords}")
        else:
            logger.warning(f"   ⚠️  提示词缺少完整内容关键词")
        
        # 4. 显示提示词的关键部分
        logger.info(f"\n🔍 提示词关键部分（包含'完整内容'的部分）:")
        
        lines = prompt.split('\n')
        content_lines = [line for line in lines if '完整内容' in line or 'full_content' in line]
        
        for i, line in enumerate(content_lines[:10]):  # 最多显示10行
            logger.info(f"   {line[:100]}...")
        
        # 5. 计算提示词长度
        logger.info(f"\n📊 提示词统计:")
        logger.info(f"   总长度: {len(prompt)} 字符")
        logger.info(f"   总行数: {len(lines)} 行")
        
        # 6. 保存提示词到文件（用于详细分析）
        prompt_file = Path(__file__).parent / "ai_prompt_debug.txt"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        logger.info(f"💾 提示词已保存到: {prompt_file}")
        
        # 7. 显示提示词开头和结尾
        logger.info(f"\n🔍 提示词开头（前300字符）:")
        logger.info(f"{prompt[:300]}...")
        
        logger.info(f"\n🔍 提示词结尾（最后300字符）:")
        logger.info(f"...{prompt[-300:]}")
    
    async def run_full_test(self):
        """运行完整测试"""
        await self.setup()
        return await self.test_real_ai_analysis()

async def main():
    """主函数"""
    print("🚀 开始真实AI内容验证测试...")
    
    # 检查API密钥
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ 错误: DEEPSEEK_API_KEY环境变量未设置")
        return 1
    
    tester = RealAIContentTester()
    
    try:
        success = await tester.run_full_test()
        
        if success:
            print("\n✅ 真实AI内容验证完成")
            print("📋 请查看详细日志确认AI提示词是否包含完整内容")
            return 0
        else:
            print("\n❌ 真实AI内容验证失败")
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
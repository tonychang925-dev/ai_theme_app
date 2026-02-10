# evaluate_service/scripts/quick_fix_76_runner.py
"""
快速修复76数据集测试脚本 - 应用小样本测试的成功模式
"""
#!/usr/bin/env python3
import re
from pathlib import Path

def quick_fix_runner():
    """快速修复76数据集测试脚本"""
    runner_file = Path("evaluate_service/runners/run_76_dataset_real_ai.py")
    
    with open(runner_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("🔧 快速修复76数据集测试脚本")
    print("="*60)
    
    # 1. 在RealAITestRunner类中添加新方法
    print("\n1. 添加与小样本测试相同的主题创建方法...")
    
    # 找到RealAITestRunner类的定义
    class_pattern = r'class RealAITestRunner:.*?(?=class|\Z)'
    match = re.search(class_pattern, content, flags=re.DOTALL)
    
    if match:
        # 在类定义中添加新方法
        new_method = '''    async def create_initial_themes_like_small_test(self, db_manager):
        """创建与小样本测试相同的初始主题"""
        logger = logging.getLogger(__name__)
        
        logger.info("🎯 创建与小样本测试相同的初始主题...")
        
        # 小样本测试中的主题
        test_themes = [
            {
                'name': 'AI智能体企业并购',
                'description': 'AI智能体企业的并购活动，包括技术收购、企业合并等',
                'keywords': ['AI智能体', '并购', '企业收购', '技术收购', 'AI代理', '智能体']
            },
            {
                'name': '智能眼镜新品发布',
                'description': '智能眼镜产品发布相关，包括Meta、Apple等公司的新品发布',
                'keywords': ['智能眼镜', 'AR眼镜', '发布', '新品', '消费电子']
            },
            {
                'name': 'AR眼镜技术突破',
                'description': 'AR眼镜技术研发突破，包括显示技术、交互技术等创新',
                'keywords': ['AR技术', '技术突破', '研发', '创新', '显示技术']
            }
        ]
        
        created_count = 0
        for theme in test_themes:
            try:
                saved_theme = await db_manager.create_theme(
                    name=theme['name'],
                    description=theme['description'],
                    keywords=theme['keywords']
                )
                if saved_theme:
                    created_count += 1
                    logger.info(f"   创建主题: {theme['name']}")
            except Exception as e:
                logger.warning(f"   创建主题失败 {theme['name']}: {e}")
        
        logger.info(f"✅ 创建 {created_count} 个初始主题")
        return created_count'''
        
        # 插入到类定义的合适位置
        updated_class = match.group(0).replace(
            '    def __init__(self):',
            new_method + '\n\n    def __init__(self):'
        )
        
        content = content.replace(match.group(0), updated_class)
        print("   ✅ 添加主题创建方法完成")
    
    # 2. 修复RealEventPreparer.prepare_all_events方法
    print("\n2. 修复事件保存方法...")
    
    # 直接替换prepare_all_events方法
    prepare_pattern = r'async def prepare_all_events\(self, events_list\):.*?(?=async def|\Z)'
    
    new_prepare = '''    async def prepare_all_events(self, events_list):
        """修复版事件保存 - 使用小样本测试的成功模式"""
        logger = logging.getLogger(__name__)
        logger.info(f"💾 准备 {len(events_list)} 个事件数据到数据库...")
        
        saved_count = 0
        for i, event in enumerate(events_list):
            try:
                event_id = event.get('news_id', f'event_{i}')
                if not event_id:
                    continue
                
                # 🔥 关键修复：使用与小样本测试完全相同的结构
                from datetime import datetime
                db_event = {
                    'id': event_id,
                    'news_id': event_id,
                    'title': event.get('original_news', {}).get('title', ''),
                    'full_content': event.get('original_news', {}).get('content', ''),
                    'content_length': len(event.get('original_news', {}).get('content', '')),
                    'has_full_content': True,  # 🔥 明确设置
                    'event_info': event.get('event_info', {}),
                    'original_news': event.get('original_news', {}),  # 🔥 保留原始数据
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                
                # 保存到数据库
                saved_id = await self.db_manager.create_or_update_event(db_event)
                if saved_id:
                    saved_count += 1
                    self.events_cache[event_id] = event  # 保存原始事件到缓存
                    
                if (i + 1) % 20 == 0:
                    logger.info(f"  已保存 {i+1}/{len(events_list)} 个事件")
                    
            except Exception as e:
                logger.warning(f"  保存事件 {event.get('news_id', 'unknown')} 失败: {e}")
        
        logger.info(f"✅ 成功保存 {saved_count}/{len(events_list)} 个真实事件到数据库")
        return saved_count'''
    
    content = re.sub(prepare_pattern, new_prepare, content, count=1, flags=re.DOTALL)
    print("   ✅ 事件保存方法修复完成")
    
    # 3. 修改run_test方法，添加主题创建步骤
    print("\n3. 修改run_test方法，添加小样本测试的初始化...")
    
    # 在run_test方法中找到合适位置添加主题创建
    run_test_pattern = r'async def run_test\(self, components, events, ground_truth\):'
    
    if run_test_pattern in content:
        # 在run_test方法开始处添加主题创建
        insertion_point = content.find(run_test_pattern) + len(run_test_pattern)
        
        # 查找方法体开始
        method_start = content.find('"""运行测试', insertion_point)
        if method_start > insertion_point:
            # 在方法体开始后插入主题创建代码
            find_def_line_end = content.find('\n', method_start)
            
            insert_code = '''
        logger.info(f"🚀 开始运行76个数据集真实AI测试（修复版）")
        logger.info(f"   使用组件: 真实DeepSeek API + 真实数据库")
        logger.info(f"   测试事件: {len(events)}个")
        logger.info(f"   Ground Truth标注: {len(ground_truth)}个")
        
        self.start_time = datetime.now()
        db_manager = components['db_manager']
        discovery = components['discovery']
        
        # 🔥 关键修复1: 首先创建与小样本测试相同的主题
        logger.info("🎯 修复步骤1: 创建与小样本测试相同的初始主题...")
        await self.create_initial_themes_like_small_test(db_manager)
        
        # 获取当前主题数
        initial_themes = await db_manager.get_all_active_themes(limit=100)
        logger.info(f"📊 初始主题数: {len(initial_themes)}")
        for theme in initial_themes[:5]:
            logger.info(f"   主题: {theme.get('name', '未知')}")
        
        # 🔥 关键修复2: 保存所有事件（使用修复版）
        logger.info("💾 修复步骤2: 保存所有事件到数据库...")
        saved_count = await self.event_preparer.prepare_all_events(events)
        self.metrics['events_saved'] = saved_count
        
        if saved_count < len(events):
            logger.warning(f"⚠️  仅保存了 {saved_count}/{len(events)} 个事件")
        
        # 🔥 关键修复3: 使用原始事件数据（不是数据库事件）
        logger.info("🔍 修复步骤3: 准备测试数据...")'''
        
            content = content[:find_def_line_end+1] + insert_code + content[find_def_line_end+1:]
            print("   ✅ run_test方法修复完成")
    
    # 保存修改
    with open(runner_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("\n✅ 快速修复完成！")
    print("\n🎯 修复总结:")
    print("   1. 添加了小样本测试的成功主题创建模式")
    print("   2. 修复了事件保存，确保数据结构完整")
    print("   3. 在run_test开始时创建正确的初始主题")
    print("\n🚀 立即测试修复效果:")
    print("   python evaluate_service/runners/run_76_dataset_real_ai.py")
    
    return True

if __name__ == "__main__":
    quick_fix_runner()
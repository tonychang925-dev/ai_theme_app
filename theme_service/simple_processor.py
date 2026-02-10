"""
简单但可靠的数据处理器
"""
import asyncio
import logging
import time
import sys
from datetime import datetime
import signal

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleDataProcessor:
    """简单数据处理器"""
    
    def __init__(self):
        sys.path.insert(0, '.')
        from theme_service.config import settings
        from theme_service.database import ThemeDatabase
        
        self.db = ThemeDatabase(settings.DATABASE_URL)
        self.processed = set()
        self.running = True
        
        # 主题映射
        self.themes = {
            "ai": "人工智能",
            "特斯拉": "新能源汽车", 
            "蔚来": "新能源汽车",
            "电池": "新能源汽车",
            "芯片": "半导体芯片",
            "医药": "医药医疗",
            "华为": "消费电子",
            "苹果": "消费电子",
            "数据": "数字经济",
            "光伏": "新能源发电",
            "风电": "新能源发电",
            "军工": "军工国防",
            "游戏": "传媒娱乐",
            "金融": "金融",
            "银行": "金融"
        }
        
        logger.info("简单数据处理器初始化")
    
    async def start(self):
        """启动处理器"""
        print("🚀 启动简单数据处理器")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-"*60)
        
        # 初始化数据库
        await self.db.initialize()
        
        # 显示状态
        stats = await self.db.get_table_stats()
        print("📊 数据库状态:")
        for table, count in stats.items():
            print(f"  {table}: {count}")
        
        # 处理循环
        iteration = 0
        total_processed = 0
        total_themes = 0
        
        try:
            while self.running:
                iteration += 1
                
                print(f"\n🔄 处理周期 #{iteration}")
                print("-"*40)
                
                # 获取新事件
                events = await self.db.get_recent_events(limit=10)
                new_events = [e for e in events if e.get('id') not in self.processed]
                
                if not new_events:
                    print("📭 没有新事件")
                    await asyncio.sleep(30)
                    continue
                
                print(f"📥 发现 {len(new_events)} 个新事件")
                
                # 处理每个事件
                processed_count = 0
                themes_found = 0
                
                for event in new_events:
                    event_id = event.get('id')
                    if not event_id:
                        continue
                    
                    try:
                        # 分析主题
                        themes = self._analyze_event(event)
                        
                        if themes:
                            # 处理每个主题
                            for theme_name in themes:
                                theme_id = await self._get_theme_id(theme_name)
                                if theme_id:
                                    # 保存映射
                                    success = await self.db.save_event_theme_mapping(
                                        event_id, theme_id, 0.7
                                    )
                                    if success:
                                        themes_found += 1
                                        logger.debug(f"映射: 事件#{event_id} -> {theme_name}")
                        
                        self.processed.add(event_id)
                        processed_count += 1
                        
                        if themes:
                            title = event.get('title') or event.get('news_title', '无标题')[:40]
                            print(f"  ✅ 事件 #{event_id}: {title}...")
                            print(f"     主题: {', '.join(themes)}")
                        
                    except Exception as e:
                        logger.error(f"处理事件 {event_id} 失败: {e}")
                
                # 更新统计
                total_processed += processed_count
                total_themes += themes_found
                
                print(f"\n📊 本周期统计:")
                print(f"  处理事件: {processed_count}")
                print(f"  发现主题: {themes_found}")
                print(f"  累计处理: {total_processed}")
                print(f"  累计主题: {total_themes}")
                
                # 等待
                await asyncio.sleep(30)
                
        except KeyboardInterrupt:
            print("\n🛑 用户中断")
        except Exception as e:
            logger.error(f"处理循环异常: {e}")
        finally:
            await self.db.close()
            print("\n🔌 数据库连接已关闭")
            print(f"\n🎯 最终统计:")
            print(f"  总处理事件: {total_processed}")
            print(f"  总发现主题: {total_themes}")
    
    def _analyze_event(self, event: dict) -> list:
        """分析事件主题"""
        title = (event.get('title') or event.get('news_title', '')).lower()
        summary = (event.get('summary') or '').lower()
        content = title + ' ' + summary
        
        found = set()
        for keyword, theme in self.themes.items():
            if keyword in content:
                found.add(theme)
        
        return list(found)
    
    async def _get_theme_id(self, theme_name: str) -> int:
        """获取主题ID，如果不存在则创建"""
        # 先查询
        conn = await self.db.acquire_connection()
        try:
            result = await conn.fetchrow(
                "SELECT id FROM theme_master WHERE name = $1",
                theme_name
            )
            
            if result:
                return result['id']
            
            # 创建新主题
            result = await conn.fetchrow("""
                INSERT INTO theme_master 
                (name, keywords, status, discovery_source, discovery_confidence)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """,
                theme_name,
                [theme_name],
                'active',
                'simple_processor',
                0.7
            )
            
            print(f"🎯 创建新主题: {theme_name} (ID: {result['id']})")
            return result['id']
            
        finally:
            await self.db.release_connection(conn)

async def main():
    """主函数"""
    processor = SimpleDataProcessor()
    
    # 设置信号处理
    def signal_handler(signum, frame):
        print(f"\n🛑 收到信号 {signum}，正在停止...")
        processor.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动处理器
    await processor.start()

if __name__ == "__main__":
    print("🚀 AI题材引擎 - 简单数据处理器")
    print("="*60)
    asyncio.run(main())

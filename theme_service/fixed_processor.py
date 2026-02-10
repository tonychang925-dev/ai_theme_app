#!/usr/bin/env python3
"""
修复版数据处理器
"""
import asyncio
import logging
import time
import sys
import os
from datetime import datetime
import signal

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# 简单日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class FixedProcessor:
    """修复版数据处理器"""
    
    def __init__(self):
        try:
            from config import settings
            from database import ThemeDatabase
            
            self.db = ThemeDatabase(settings.DATABASE_URL)
            self.processed_events = set()
            self.running = True
            
            # 主题关键词映射
            self.theme_keywords = {
                "人工智能": ["ai", "人工智能", "大模型", "gpt", "机器学习"],
                "新能源汽车": ["新能源", "电动车", "特斯拉", "电池", "充电"],
                "半导体芯片": ["芯片", "半导体", "集成电路", "光刻机"],
                "医药医疗": ["医药", "医疗", "医院", "疫苗", "健康"],
                "消费电子": ["苹果", "华为", "小米", "手机", "消费电子"],
                "数字经济": ["数据", "数字", "云计算", "大数据", "区块链"],
                "金融": ["银行", "保险", "证券", "金融", "支付"],
                "军工国防": ["军工", "国防", "军事", "航空航天"],
                "新能源发电": ["光伏", "风电", "储能", "太阳能"],
                "传媒娱乐": ["游戏", "传媒", "影视", "娱乐"],
            }
            
            self.stats = {
                "start_time": datetime.now(),
                "total_processed": 0,
                "total_themes": 0
            }
            
            logger.info("数据处理器初始化完成")
            
        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            print("请确保在 theme_service 目录中运行")
            raise
    
    async def initialize(self):
        """初始化"""
        print("="*60)
        print("🚀 AI题材引擎 - 数据处理器")
        print("="*60)
        
        try:
            # 初始化数据库
            if not await self.db.initialize():
                print("❌ 数据库初始化失败")
                return False
            
            if not await self.db.health_check():
                print("❌ 数据库连接失败")
                return False
            
            print("✅ 数据库连接成功")
            
            # 显示当前数据
            try:
                stats = await self.db.get_table_stats()
                print("\n📊 当前数据:")
                for table, count in stats.items():
                    print(f"  {table}: {count}")
            except:
                print("\n📊 无法获取表统计")
            
            return True
            
        except Exception as e:
            print(f"❌ 初始化异常: {e}")
            return False
    
    def analyze_event(self, title: str, content: str) -> list:
        """分析事件主题"""
        if not title and not content:
            return []
        
        text = (title + " " + content).lower()
        themes_found = []
        
        for theme_name, keywords in self.theme_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    themes_found.append(theme_name)
                    break
        
        return list(set(themes_found))
    
    async def get_or_create_theme(self, theme_name: str) -> int:
        """获取或创建主题"""
        try:
            # 查询主题
            themes = await self.db.get_themes_by_status("active", 100)
            for theme in themes:
                if theme.get("name") == theme_name:
                    return theme.get("id")
            
            # 创建新主题
            theme_data = {
                "name": theme_name,
                "keywords": [theme_name],
                "discovery_source": "fixed_processor",
                "confidence": 0.7
            }
            
            theme_id = await self.db.save_theme(theme_data)
            if theme_id:
                print(f"🎯 创建新主题: {theme_name} (ID: {theme_id})")
                self.stats["total_themes"] += 1
            
            return theme_id
            
        except Exception as e:
            print(f"❌ 主题处理失败: {e}")
            return 0
    
    async def process_batch(self):
        """处理一批事件"""
        try:
            # 获取新事件
            events = await self.db.get_recent_events(limit=10)
            new_events = [e for e in events if e.get('id') not in self.processed_events]
            
            if not new_events:
                return 0, 0
            
            print(f"\n📥 发现 {len(new_events)} 个新事件")
            
            processed = 0
            themes_found = 0
            
            for event in new_events:
                event_id = event.get('id')
                if not event_id:
                    continue
                
                try:
                    # 分析主题
                    title = event.get('title') or event.get('news_title', '')
                    content = event.get('summary', '')
                    themes = self.analyze_event(title, content)
                    
                    if themes:
                        # 处理每个主题
                        for theme_name in themes:
                            theme_id = await self.get_or_create_theme(theme_name)
                            if theme_id:
                                # 保存映射
                                success = await self.db.save_event_theme_mapping(
                                    event_id, theme_id, 0.7
                                )
                                if success:
                                    themes_found += 1
                        
                        print(f"  ✅ 事件 #{event_id}: 发现 {len(themes)} 个主题")
                    else:
                        print(f"  ⏳ 事件 #{event_id}: 未发现主题")
                    
                    self.processed_events.add(event_id)
                    processed += 1
                    
                except Exception as e:
                    print(f"  ❌ 事件 #{event_id} 处理失败: {e}")
            
            return processed, themes_found
            
        except Exception as e:
            print(f"❌ 批次处理失败: {e}")
            return 0, 0
    
    async def run(self, interval=30):
        """运行处理器"""
        if not await self.initialize():
            return
        
        print(f"\n⏰ 处理间隔: {interval} 秒")
        print("按 Ctrl+C 停止\n")
        
        iteration = 0
        
        try:
            while self.running:
                iteration += 1
                start_time = time.time()
                
                print(f"\n{'='*50}")
                print(f"处理周期 #{iteration} - {datetime.now().strftime('%H:%M:%S')}")
                
                # 处理批次
                processed, themes_found = await self.process_batch()
                
                # 更新统计
                self.stats["total_processed"] += processed
                
                # 显示结果
                elapsed = time.time() - start_time
                print(f"\n📊 本周期结果:")
                print(f"  处理事件: {processed}")
                print(f"  发现主题: {themes_found}")
                print(f"  处理时间: {elapsed:.2f}秒")
                
                # 累计统计
                uptime = datetime.now() - self.stats["start_time"]
                print(f"\n📈 累计统计:")
                print(f"  运行时间: {str(uptime).split('.')[0]}")
                print(f"  总处理事件: {self.stats['total_processed']}")
                print(f"  总发现主题: {self.stats['total_themes']}")
                
                # 等待下一周期
                if iteration % 5 == 0:
                    print(f"\n⏳ 等待 {interval} 秒后继续...")
                
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 用户中断")
        except Exception as e:
            print(f"\n❌ 运行异常: {e}")
        finally:
            # 最终统计
            print(f"\n{'='*50}")
            print("🎯 最终统计:")
            print(f"  总运行时间: {datetime.now() - self.stats['start_time']}")
            print(f"  总处理事件: {self.stats['total_processed']}")
            print(f"  总发现主题: {self.stats['total_themes']}")
            
            # 关闭数据库
            try:
                await self.db.close()
                print("\n🔌 数据库连接已关闭")
            except:
                pass

def signal_handler(signum, frame):
    print(f"\n🛑 收到停止信号")
    processor.running = False

async def main():
    """主函数"""
    try:
        processor = FixedProcessor()
        
        # 设置信号处理
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 运行处理器
        await processor.run(interval=30)
        
    except Exception as e:
        print(f"\n❌ 处理器启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 AI题材引擎 - 启动修复版数据处理器")
    asyncio.run(main())

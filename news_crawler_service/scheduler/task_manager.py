"""
任务调度管理器 - 控制新闻抓取的自动执行
"""
import asyncio
import time
from datetime import datetime
from typing import List
import signal
import sys

from ..collectors.source_factory import CollectorFactory
from ..database import DatabaseManager, init_database
from ..config import settings

class TaskManager:
    """任务调度管理器"""
    
    def __init__(self):
        self.running = True
        self.collectors = []
        self.cycle_count = 0
        self.setup_signal_handlers()
    
    def setup_signal_handlers(self):
        """设置信号处理器，支持优雅退出"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        print(f"\n收到退出信号，正在优雅停止...")
        self.running = False
    
    async def initialize(self):
        """初始化调度器"""
        print("初始化调度器...")
        
        # 1. 初始化数据库
        await init_database()
        
        # 2. 初始化数据源收集器
        self.collectors = await CollectorFactory.create_collectors()
        print(f"初始化完成: {len(self.collectors)} 个数据源")
    
    async def run_single_cycle(self):
        """执行单次抓取周期"""
        self.cycle_count += 1
        print(f"\n{'='*60}")
        print(f"🔄 抓取周期 #{self.cycle_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print('='*60)
        
        total_saved = 0
        cycle_start = time.time()
        
        for collector in self.collectors:
            try:
                print(f"\n📡 正在采集 [{collector.source_name}]...")
                cycle_item_start = time.time()
                
                # 执行抓取
                news_items = await collector.fetch()
                fetch_time = time.time() - cycle_item_start
                
                # 保存到数据库
                if news_items:
                    save_start = time.time()
                    saved = await DatabaseManager.save_news_batch(news_items)
                    save_time = time.time() - save_start
                    
                    print(f"   📥 接收: {len(news_items)} 条，💾 保存: {saved} 条")
                    if saved < len(news_items):
                        print(f"   🔄 去重: {len(news_items) - saved} 条（已存在）")
                    print(f"   ⏱️  耗时: 抓取 {fetch_time:.2f}s + 保存 {save_time:.2f}s")
                    total_saved += saved
                else:
                    print(f"   ℹ️  无新数据")
                    
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                import traceback
                traceback.print_exc()
        
        cycle_time = time.time() - cycle_start
        print(f"\n📊 周期 #{self.cycle_count} 完成")
        print(f"   总计保存: {total_saved} 条新闻")
        print(f"   总耗时: {cycle_time:.2f} 秒")
        
        return total_saved
    
    async def start(self, interval_minutes: int = 2, max_cycles: int = 3):
        """
        启动定时调度器
        
        Args:
            interval_minutes: 抓取间隔（分钟）
            max_cycles: 最大运行周期数（测试用）
        """
        print("🚀 启动新闻抓取调度器")
        print(f"   模式: 每 {interval_minutes} 分钟运行一次")
        print(f"   最多运行: {max_cycles} 个周期（测试模式）")
        print("   按 Ctrl+C 可随时停止")
        print('-'*60)
        
        await self.initialize()
        
        cycles_completed = 0
        
        while self.running and cycles_completed < max_cycles:
            try:
                # 执行抓取周期
                await self.run_single_cycle()
                cycles_completed += 1
                
                # 如果不是最后一个周期，等待下一个
                if self.running and cycles_completed < max_cycles:
                    print(f"\n⏳ 等待 {interval_minutes} 分钟开始下一个周期...")
                    for i in range(interval_minutes * 60):
                        if not self.running:
                            break
                        if i % 30 == 0:  # 每30秒打印一次等待状态
                            remaining = interval_minutes * 60 - i
                            print(f"   等待中... {remaining//60}:{remaining%60:02d} 后继续")
                        await asyncio.sleep(1)
                        
            except Exception as e:
                print(f"\n⚠️ 调度器运行异常: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(30)  # 异常后等待30秒重试
        
        await self.shutdown(cycles_completed)
    
    async def shutdown(self, cycles_completed: int):
        """关闭调度器"""
        print(f"\n{'='*60}")
        print("🛑 正在关闭调度器...")
        print(f"   总计完成周期: {cycles_completed} 个")
        
        # 显示最新的几条新闻作为验证
        try:
            recent = await DatabaseManager.get_recent_news(3)
            if recent:
                print("\n📰 最新抓取的新闻:")
                for i, news in enumerate(recent, 1):
                    print(f"   {i}. [{news['source']}] {news['title'][:50]}...")
        except Exception as e:
            print(f"   获取最新新闻失败: {e}")
        
        await DatabaseManager.close()
        print("✅ 调度器已正常关闭")
    
    # 在 TaskManager 类中添加差异化调度方法
    async def start_differential_scheduling(self, max_cycles: int = 2):
        """
        差异化调度：不同源不同频率
        财联社：每15分钟
        央视新闻：每60分钟
        """
        print("🚀 启动差异化调度器")
        print("   模式: 财联社(15分钟) + 央视新闻(60分钟)")
        print("   按 Ctrl+C 停止")
        print("-" * 60)
        
        await self.initialize()
        
        # 分离不同源的采集器
        cls_collector = next((c for c in self.collectors if c.source_name == "akshare_cls"), None)
        cctv_collector = next((c for c in self.collectors if c.source_name == "akshare_cctv"), None)
        
        if not cls_collector:
            print("❌ 错误: 未找到财联社采集器")
            return
        
        cycles_completed = 0
        last_cctv_run = 0
        
        while self.running and cycles_completed < max_cycles:
            current_time = asyncio.get_event_loop().time()
            
            # 记录周期开始
            self.cycle_count += 1
            print(f"\n{'='*60}")
            print(f"🔄 调度周期 #{self.cycle_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print('='*60)
            
            total_saved = 0
            
            # 1. 总是运行财联社（高频）
            print(f"\n📡 运行财联社采集...")
            if cls_collector:
                news = await cls_collector.fetch()
                if news:
                    saved = await DatabaseManager.save_news_batch(news)
                    print(f"   ✅ 财联社: 抓取 {len(news)} 条，保存 {saved} 条")
                    total_saved += saved
            
            # 2. 每60分钟运行一次央视新闻
            run_cctv = False
            if cctv_collector and (current_time - last_cctv_run > 3600 or last_cctv_run == 0):
                print(f"\n📺 运行央视新闻采集...")
                news = await cctv_collector.fetch()
                if news:
                    saved = await DatabaseManager.save_news_batch(news)
                    print(f"   ✅ 央视新闻: 抓取 {len(news)} 条，保存 {saved} 条")
                    total_saved += saved
                    last_cctv_run = current_time
                    run_cctv = True
            elif cctv_collector:
                next_cctv = 3600 - (current_time - last_cctv_run)
                print(f"\n⏰ 央视新闻: {int(next_cctv/60)}分钟后运行")
            
            print(f"\n📊 周期 #{self.cycle_count} 完成")
            print(f"   总计保存: {total_saved} 条新闻")
            
            cycles_completed += 1
            
            # 如果不是最后一个周期，等待下一个
            if self.running and cycles_completed < max_cycles:
                wait_minutes = 15  # 财联社频率
                print(f"\n⏳ 等待 {wait_minutes} 分钟开始下一个周期...")
                await asyncio.sleep(wait_minutes * 60)
        
        await self.shutdown(cycles_completed)

# 测试运行函数
async def test_scheduler():
    """测试调度器（短时间运行）"""
    manager = TaskManager()
    await manager.start(interval_minutes=1, max_cycles=2)  # 每1分钟运行，共2次

if __name__ == "__main__":
    asyncio.run(test_scheduler())

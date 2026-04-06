#!/usr/bin/env python3
"""
AI事件抽取服务 - 主运行脚本（修复版）
从news_raw表读取新闻，调用AI解析，存储到news_event表
"""
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

# 添加项目路径，确保导入正常
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model_service.database import DatabaseManager as db_manager
from services.event_extractor import AIEventExtractor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NewsEventProcessor:
    """新闻事件处理器（修复版）"""
    
    def __init__(self):
        """
        初始化处理器
        
        Args:
        """
        self.extractor = None
        self.batch_size = int(os.getenv('BATCH_SIZE', '10'))
        
    async def initialize(self):
        """初始化组件"""
        logger.info("🚀 初始化新闻事件处理器...")
        
        # 初始化数据库
        await db_manager.initialize_db()
        logger.info("✅ 数据库连接初始化完成")
        
        # 初始化事件提取器（仅允许真实AI）
        try:
            self.extractor = AIEventExtractor()
            logger.info("✅ AI事件提取器初始化完成")
        except Exception as e:
            logger.error(f"❌ AI事件提取器初始化失败: {e}")
            raise
        
        logger.info(f"📦 批处理大小: {self.batch_size}")
        logger.info("=" * 60)
    
    async def fetch_pending_news(self, limit: Optional[int] = None) -> List[Dict]:
        """
        从数据库获取待处理的新闻（使用DatabaseManager方法）
        
        Args:
            limit: 限制返回数量
        
        Returns:
            新闻数据列表
        """
        query_limit = limit or self.batch_size
        
        try:
            # 使用DatabaseManager的专用方法
            rows = await db_manager.fetch_pending_news(query_limit)
            
            # 转换日期格式（如果需要）
            for row in rows:
                if 'publish_date' in row and row['publish_date']:
                    if isinstance(row['publish_date'], datetime):
                        row['publish_date'] = row['publish_date'].date().isoformat()
                
                if 'created_at' in row and row['created_at']:
                    if isinstance(row['created_at'], datetime):
                        row['created_at'] = row['created_at'].isoformat()
            
            logger.info(f"📋 获取到 {len(rows)} 条待处理新闻")
            return rows
            
        except Exception as e:
            logger.error(f"❌ 查询待处理新闻失败: {e}")
            return []
    
    async def process_single_news(self, news_item: Dict) -> Optional[Dict]:
        """
        处理单条新闻
        
        Args:
            news_item: 新闻数据字典
        
        Returns:
            成功返回事件数据，失败返回None
        """
        news_id = news_item.get('news_id') or news_item.get('id', 'unknown')
        
        try:
            logger.debug(f"🔍 处理新闻 {news_id}...")
            
            # 调用事件提取器
            event_data = await self.extractor.extract_event(news_item)
            
            if not event_data:
                logger.warning(f"⚠️  新闻 {news_id} 未提取到事件")
                return None
            
            # 添加时间戳
            event_data['created_at'] = datetime.now().isoformat()
            
            # 记录成功日志
            logger.info(f"✅ 新闻 {news_id} 处理成功: {event_data.get('event_type')}")
            
            return event_data
            
        except Exception as e:
            logger.error(f"❌ 处理新闻 {news_id} 时发生错误: {e}")
            return None
    
    async def mark_news_as_processed(self, news_id: str):
        """标记新闻为已处理（使用DatabaseManager方法）"""
        try:
            success = await db_manager.mark_news_as_processed(news_id)
            if success:
                logger.debug(f"✅ 新闻 {news_id} 已标记为已处理")
            else:
                logger.warning(f"⚠️  新闻 {news_id} 标记失败（可能不存在或已处理）")
        except Exception as e:
            logger.error(f"❌ 标记新闻 {news_id} 为已处理失败: {e}")
    
    async def save_event_to_db(self, event_data: Dict) -> bool:
        """保存事件到数据库（使用DatabaseManager方法）"""
        try:
            # 使用DatabaseManager的save_event方法
            success = await db_manager.save_event(event_data)
            
            if success:
                logger.debug(f"✅ 事件保存成功: {event_data['news_id']}")
            else:
                logger.error(f"❌ 事件保存失败: {event_data['news_id']}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 保存事件到数据库失败: {e}")
            return False
    
    async def process_batch(self) -> Dict:
        """
        处理一批新闻
        
        Returns:
            处理统计信息
        """
        stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'start_time': datetime.now()
        }
        
        # 获取待处理新闻
        pending_news = await self.fetch_pending_news()
        stats['total'] = len(pending_news)
        
        if not pending_news:
            logger.info("📭 没有待处理的新闻")
            return stats
        
        logger.info(f"🚀 开始处理 {len(pending_news)} 条新闻...")
        logger.info("-" * 50)
        
        # 处理每条新闻
        for i, news_item in enumerate(pending_news, 1):
            news_id = news_item.get('news_id') or news_item.get('id', f'news_{i}')
            
            logger.info(f"[{i}/{len(pending_news)}] 处理: {news_id}")
            
            # 处理新闻
            event_data = await self.process_single_news(news_item)
            
            if event_data:
                # 保存事件到数据库
                if await self.save_event_to_db(event_data):
                    # 标记原新闻为已处理
                    await self.mark_news_as_processed(news_id)
                    stats['success'] += 1
                    logger.info(f"   ✅ 处理完成")
                else:
                    stats['failed'] += 1
                    logger.error(f"   ❌ 保存失败")
            else:
                stats['failed'] += 1
                logger.warning(f"   ⚠️  提取失败")
            
            # 添加处理间隔，避免API限流
            await asyncio.sleep(1)
        
        # 计算耗时
        stats['end_time'] = datetime.now()
        stats['duration'] = (stats['end_time'] - stats['start_time']).total_seconds()
        
        return stats
    
    async def run_continuously(self, interval_seconds: int = 300):
        """
        持续运行处理器
        
        Args:
            interval_seconds: 处理间隔（秒）
        """
        logger.info(f"🔄 开始持续运行，间隔: {interval_seconds}秒")
        
        run_count = 0
        while True:
            run_count += 1
            try:
                logger.info(f"\n{'=' * 60}")
                logger.info(f"🔄 第 {run_count} 轮处理开始")
                logger.info(f"{'=' * 60}")
                
                stats = await self.process_batch()
                
                # 打印统计信息
                if stats['total'] > 0:
                    success_rate = (stats['success'] / stats['total']) * 100
                    logger.info(f"\n📊 处理完成统计:")
                    logger.info(f"   📈 总计: {stats['total']} 条")
                    logger.info(f"   ✅ 成功: {stats['success']} 条")
                    logger.info(f"   ❌ 失败: {stats['failed']} 条")
                    logger.info(f"   📊 成功率: {success_rate:.1f}%")
                    logger.info(f"   ⏱️  耗时: {stats['duration']:.1f} 秒")
                else:
                    logger.info("📭 本轮无待处理新闻")
                
                # 等待下一轮
                if run_count > 1:  # 第一轮后显示等待信息
                    logger.info(f"\n⏳ 等待 {interval_seconds} 秒后进行下一轮处理...")
                await asyncio.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                logger.info("\n🛑 收到中断信号，停止运行...")
                break
            except Exception as e:
                logger.error(f"❌ 处理器运行异常: {e}")
                logger.info("⏳ 等待10秒后重试...")
                await asyncio.sleep(10)
    
    async def cleanup(self):
        """清理资源"""
        if self.extractor:
            try:
                await self.extractor.close()
                logger.info("✅ 事件提取器资源已清理")
            except Exception as e:
                logger.error(f"❌ 清理事件提取器失败: {e}")
        
        # 注意：你的DatabaseManager使用连接-关闭模式，不需要调用close()
        # 但为了兼容性，我们还是会调用它（它有空的close方法）
        try:
            await db_manager.close()
            logger.info("✅ 数据库连接已关闭")
        except Exception as e:
            logger.warning(f"⚠️  关闭数据库连接时出错: {e}")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI新闻事件抽取处理器')
    parser.add_argument('--once', action='store_true', help='只运行一次，不持续运行')
    parser.add_argument('--interval', type=int, default=300, help='处理间隔（秒），默认300')
    parser.add_argument('--limit', type=int, help='限制处理数量（测试用）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细日志输出')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("🔍 启用详细日志模式")
    
    processor = NewsEventProcessor()
    
    try:
        # 初始化
        await processor.initialize()
        
        if args.once:
            # 单次运行模式
            logger.info("🔄 单次运行模式")
            stats = await processor.process_batch()
            
            # 打印最终统计
            print("\n" + "=" * 60)
            print("🎯 处理完成报告")
            print("=" * 60)
            if stats['total'] > 0:
                success_rate = (stats['success'] / stats['total']) * 100
                print(f"📈 总计处理: {stats['total']} 条新闻")
                print(f"✅ 成功提取: {stats['success']} 个事件")
                print(f"❌ 提取失败: {stats['failed']} 条新闻")
                print(f"📊 成功率: {success_rate:.1f}%")
                print(f"⏱️  总耗时: {stats['duration']:.1f} 秒")
            else:
                print("📭 没有需要处理的新闻")
            print("=" * 60)
            
        else:
            # 持续运行模式
            await processor.run_continuously(args.interval)
            
    except KeyboardInterrupt:
        logger.info("\n👋 程序被用户中断")
    except Exception as e:
        logger.error(f"\n💥 程序运行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # 清理资源
        logger.info("\n🧹 清理资源...")
        await processor.cleanup()
        logger.info("👋 程序退出")
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

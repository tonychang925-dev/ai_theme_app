# database_service/streams/schedulers/news_collector_scheduler.py
"""
新闻收集调度器 - 集成现有组件（仅真实新闻）
"""
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class NewsCollectorScheduler:
    """新闻收集调度器（仅真实新闻）"""
    
    def __init__(self, stream_gateway, news_service):
        """
        Args:
            stream_gateway: StreamEnhancedGateway实例
            news_service: 新闻服务实例
        """
        self.gateway = stream_gateway
        self.news_service = news_service
        self.running = False
        self.collection_count = 0
        self.success_count = 0
        self.error_count = 0
    
    async def start_scheduled_collection(self, interval_seconds: int = 30, batch_size: int = 3):
        """启动定时收集"""
        self.running = True
        
        logger.info(f"⏰ NewsCollectorScheduler启动，间隔: {interval_seconds}秒，批次大小: {batch_size}")
        
        while self.running:
            try:
                start_time = datetime.now()
                self.collection_count += 1
                
                logger.info(f"\n🔄 开始第 {self.collection_count} 批次收集 ({start_time.strftime('%H:%M:%S')})")
                
                # 1. 获取真实新闻
                result = await self.news_service.crawl_real_news(limit=batch_size)
                news_list = result.get("response", {}).get("news_list", []) if result.get("status") == "success" else []
                logger.info(f"📰 获取 {len(news_list)} 条真实新闻")
                
                # 2. 发布到Stream
                results = []
                for news_data in news_list:
                    try:
                        message_id = await self.gateway.publish_news_to_stream(news_data)
                        
                        if message_id:
                            results.append({
                                "success": True,
                                "news_id": news_data.get('news_id'),
                                "message_id": message_id
                            })
                            self.success_count += 1
                            logger.debug(f"✅ 发布成功: {news_data.get('title', '未命名')[:30]}...")
                        else:
                            results.append({"success": False, "error": "发布失败"})
                            self.error_count += 1
                            logger.error(f"❌ 发布失败")
                            
                    except Exception as e:
                        results.append({"success": False, "error": str(e)})
                        self.error_count += 1
                        logger.error(f"❌ 发布异常: {e}")
                
                # 3. 统计结果
                success_count = sum(1 for r in results if r["success"])
                duration = (datetime.now() - start_time).total_seconds()
                
                logger.info(f"📊 批次结果: {success_count}/{len(results)} 成功")
                logger.info(f"⏱️  耗时: {duration:.2f}秒")
                
                # 4. 等待下次执行
                logger.debug(f"⏳ 等待 {interval_seconds} 秒...")
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 调度器异常: {e}")
                self.error_count += 1
                await asyncio.sleep(60)  # 异常后等待更长时间
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        return {
            "collection_count": self.collection_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "running": self.running,
            "last_update": datetime.now().isoformat()
        }
    
    async def stop(self):
        """停止调度器"""
        self.running = False
        logger.info(f"🛑 NewsCollectorScheduler已停止 (总收集: {self.collection_count}, 成功: {self.success_count}, 错误: {self.error_count})")

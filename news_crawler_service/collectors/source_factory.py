# ai_theme_app/news_crawler_service/collectors/source_factory.py
from typing import List
from .akshare_cls import AkshareClsCollector
from .akshare_cctv import AkshareCctvCollector
from ..config import settings

class CollectorFactory:
    @staticmethod
    async def create_collectors() -> List:
        """创建所有启用的采集器"""
        print(f"🔧 创建采集器，配置源: {settings.ENABLED_SOURCES}")
        
        collectors = []
        
        for source_name in settings.ENABLED_SOURCES:
            print(f"  正在处理: {source_name}")
            
            if source_name == "akshare_cls":
                collector = AkshareClsCollector(
                    request_interval=settings.REQUEST_INTERVAL_SECONDS,
                    max_retries=settings.MAX_RETRY_TIMES
                )
                collectors.append(collector)
                print(f"  ✅ 创建: {source_name}")
                
            elif source_name == "akshare_cctv":
                collector = AkshareCctvCollector(
                    request_interval=3600,  # 央视新闻每小时抓取一次
                    max_retries=settings.MAX_RETRY_TIMES
                )
                collectors.append(collector)
                print(f"  ✅ 创建: {source_name}")
                
            else:
                print(f"  ⚠️ 跳过未知源: {source_name}")
        
        print(f"🔧 总共创建了 {len(collectors)} 个采集器")
        return collectors

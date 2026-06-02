# news_crawler_service/services/news_crawler_service.py
"""
新闻抓取服务 - 独立服务，仅提供真实新闻抓取接口
供其他模块（如database_service）调用
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import traceback

logger = logging.getLogger(__name__)


class NewsCrawlerService:
    """新闻抓取服务 - 仅支持真实新闻抓取"""
    
    def __init__(self):
        """
        初始化新闻抓取服务
        """
        self.collector = None
        self.initialized = False
        self.fetch_timeout_seconds = int(os.getenv("NEWS_CRAWLER_FETCH_TIMEOUT_SECONDS", "25"))
        self.healthcheck_timeout_seconds = int(os.getenv("NEWS_CRAWLER_HEALTHCHECK_TIMEOUT_SECONDS", "8"))
        
        try:
            # 1. 初始化真实新闻采集器
            self._init_real_collector()
            
            self.initialized = True
            logger.info("📡 NewsCrawlerService初始化成功")
            
        except Exception as e:
            logger.error(f"❌ NewsCrawlerService初始化失败: {e}")
            self.initialized = False
        
        # 服务元数据
        self.service_metadata = {
            "service": "NewsCrawlerService",
            "version": "3.0.0",
            "description": "支持真实新闻抓取的独立服务",
            "features": ["real_news_crawling", "batch_processing"],
            "initialized_at": datetime.now().isoformat(),
            "initialized": self.initialized,
            "has_real_collector": self.collector is not None
        }
    
    def _init_real_collector(self):
        """初始化真实新闻采集器"""
        try:
            from news_crawler_service.collectors.akshare_cls import AkshareClsCollector
            from news_crawler_service.config import settings
            
            self.collector = AkshareClsCollector(
                request_interval=settings.REQUEST_INTERVAL_SECONDS,
                max_retries=settings.MAX_RETRY_TIMES
            )
            logger.info("✅ 财联社页面采集器初始化成功")
            
        except ImportError as e:
            logger.warning(f"⚠️  无法导入财联社采集器: {e}")
            logger.info("💡 未启用任何mock回退，采集将返回无数据")
            self.collector = None
        except Exception as e:
            logger.error(f"❌ 财联社采集器初始化失败: {e}")
            self.collector = None
    
    async def crawl_real_news(self, symbol: str = "重点", limit: int = 10) -> Dict[str, Any]:
        """
        抓取真实财联社新闻 - 主接口
        
        Args:
            symbol: "重点" 返回精简的重要电报；"全部" 返回更完整的页面结果
            limit: 最大返回数量
            
        Returns:
            新闻数据
        """
        operation = "crawl_real_news"
        
        try:
            logger.info(f"📡 开始抓取真实财联社新闻: symbol={symbol}, limit={limit}")
            
            if not self.collector:
                return self._create_error_response(
                    "真实新闻采集器未初始化", 
                    operation,
                    "请检查CLS页面采集模块依赖"
                )
            
            # 设置采集器参数
            self.collector.symbol = symbol
            
            # 执行抓取
            news_items = await asyncio.wait_for(
                self.collector.fetch(),
                timeout=self.fetch_timeout_seconds,
            )
            
            # 限制返回数量
            if limit > 0 and len(news_items) > limit:
                news_items = news_items[:limit]
            
            # 转换为字典格式
            news_data = []
            for item in news_items:
                news_data.append(item.to_dict())
            
            # 构建响应
            result = {
                "operation": operation,
                "status": "success",
                "service": "NewsCrawlerService",
                "request": {
                    "symbol": symbol,
                    "limit": limit
                },
                "response": {
                    "news_count": len(news_data),
                    "news_list": news_data,
                    "has_more": len(news_items) > limit,
                    "source": "财联社 (cls page)",
                    "crawled_at": datetime.now().isoformat()
                },
                "metadata": self.service_metadata
            }
            
            logger.info(f"✅ 真实新闻抓取完成: {len(news_data)}条新闻")
            return result
        except asyncio.TimeoutError:
            logger.error(f"❌ 真实新闻抓取超时: {self.fetch_timeout_seconds}s")
            return self._create_error_response(
                f"真实新闻抓取超时({self.fetch_timeout_seconds}s)",
                operation,
                "AKShare/上游接口响应过慢或阻塞",
            )
            
        except Exception as e:
            logger.error(f"❌ 真实新闻抓取失败: {e}")
            traceback.print_exc()
            return self._create_error_response(str(e), operation)
    
    async def crawl_news_auto(self, count: int = 5, prefer_real: bool = True) -> Dict[str, Any]:
        """
        智能抓取新闻 - 自动模式仅允许真实数据
        
        Args:
            count: 抓取数量
            prefer_real: 是否优先使用真实数据
            
        Returns:
            新闻数据
        """
        operation = "crawl_news_auto"
        
        try:
            logger.info(f"🤖 智能抓取新闻: count={count}, prefer_real={prefer_real} (mock已禁用)")

            if prefer_real and self.collector:
                # 直接进入真实抓取，避免“健康检查”把慢请求误判为不可用。
                result = await self.crawl_real_news("重点", count)
                result["operation"] = operation
                result["mode"] = "real"
                result["prefer_real"] = prefer_real
                result["real_available"] = result.get("status") == "success"
                return result

            return self._create_error_response(
                "真实新闻源不可用",
                operation,
                "mock回退已禁用，请检查真实采集器状态"
            )
            
        except Exception as e:
            logger.error(f"❌ 智能抓取失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def crawl_news_batch(
        self, 
        batch_size: int = 5, 
        mixed_types: bool = True,
        mode: str = "auto"  # auto, real
    ) -> Dict[str, Any]:
        """
        批量抓取新闻
        
        Args:
            batch_size: 批次大小
            mixed_types: 保留参数（当前仅真实模式生效）
            mode: 抓取模式 auto/real
            
        Returns:
            批次结果
        """
        operation = "crawl_news_batch"
        
        try:
            logger.info(f"📦 批次抓取: size={batch_size}, mixed={mixed_types}, mode={mode}")
            
            if mode == "real":
                # 真实数据批次抓取
                if not self.collector:
                    return self._create_error_response(
                        "真实采集器未初始化", 
                        operation,
                        "无法使用real模式"
                    )
                result = await self.crawl_real_news("重点", batch_size)
                
            else:  # auto模式
                # 智能选择
                result = await self.crawl_news_auto(batch_size, prefer_real=True)
            
            result["operation"] = operation
            logger.info(f"✅ 批次抓取完成: {result.get('response', {}).get('news_count', 0)}条新闻")
            return result
            
        except Exception as e:
            logger.error(f"❌ 批次抓取失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        real_healthy = False
        # 检查真实采集器
        if self.collector:
            try:
                real_healthy = await self.collector.health_check()
            except:
                real_healthy = False
        
        return {
            "operation": "get_service_status",
            "status": "healthy" if self.initialized else "unhealthy",
            "service": "NewsCrawlerService",
            "initialized": self.initialized,
            "components": {
                "real_collector": {
                    "available": self.collector is not None,
                    "healthy": real_healthy,
                    "source": "财联社 (akshare)" if self.collector else "未初始化"
                }
            },
            "metadata": self.service_metadata,
            "timestamp": datetime.now().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查（兼容旧接口）"""
        status = await self.get_service_status()
        status["operation"] = "health_check"
        return status
    
    def _create_error_response(
        self, 
        error_message: str, 
        operation: str = "unknown",
        details: str = None
    ) -> Dict[str, Any]:
        """创建错误响应"""
        response = {
            "operation": operation,
            "status": "error",
            "error": error_message,
            "service": "NewsCrawlerService",
            "metadata": self.service_metadata,
            "timestamp": datetime.now().isoformat()
        }
        
        if details:
            response["details"] = details
        
        return response


# 全局单例实例
_news_crawler_service_instance = None

def get_news_crawler_service() -> NewsCrawlerService:
    """获取新闻抓取服务实例（单例模式）"""
    global _news_crawler_service_instance
    if _news_crawler_service_instance is None:
        _news_crawler_service_instance = NewsCrawlerService()
        logger.info("✅ 创建NewsCrawlerService单例实例")
    return _news_crawler_service_instance


# 快速测试函数
async def test_crawler_service():
    """测试新闻抓取服务"""
    try:
        service = get_news_crawler_service()
        
        print("\n" + "="*60)
        print("🤖 新闻抓取服务测试")
        print("="*60)
        
        # 1. 检查服务状态
        status = await service.get_service_status()
        print(f"1. 服务状态: {status.get('status')}")
        print(f"   真实采集器: {status['components']['real_collector']['available']}")
        
        # 2. 测试真实抓取
        print("\n2. 测试真实新闻抓取...")
        result = await service.crawl_real_news(limit=3)
        
        print(f"   操作: {result.get('operation')}")
        print(f"   状态: {result.get('status')}")
        print(f"   新闻数量: {result.get('response', {}).get('news_count', 0)}")
        
        if result.get('status') == 'success':
            news_list = result.get('response', {}).get('news_list', [])
            for i, news in enumerate(news_list[:2]):  # 显示前2条
                print(f"\n   新闻 {i+1}:")
                print(f"     标题: {news.get('title', '无标题')}")
                print(f"     来源: {news.get('source', '未知')}")
                print(f"     日期: {news.get('publish_date', '未知')}")
        
        # 3. 测试智能抓取
        print("\n3. 测试智能抓取...")
        auto_result = await service.crawl_news_auto(count=2, prefer_real=True)
        print(f"   模式: {auto_result.get('mode', 'unknown')}")
        print(f"   数量: {auto_result.get('response', {}).get('news_count', 0)}")
        
        print("\n✅ 测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_crawler_service())

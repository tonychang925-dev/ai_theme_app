# news_crawler_service/services/news_crawler_service.py
"""
新闻抓取服务 - 独立服务，提供真实新闻抓取和EnhancedNewsGenerator接口
供其他模块（如database_service）调用
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import traceback

logger = logging.getLogger(__name__)


class NewsCrawlerService:
    """新闻抓取服务 - 支持真实新闻抓取和模拟数据生成"""
    
    def __init__(self):
        """
        初始化新闻抓取服务
        """
        self.collector = None
        self.news_generator = None
        self.initialized = False
        
        try:
            # 1. 初始化真实新闻采集器
            self._init_real_collector()
            
            # 2. 初始化模拟新闻生成器（用于测试/备选）
            self._init_news_generator()
            
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
            "features": ["real_news_crawling", "mock_news_generation", "batch_processing"],
            "initialized_at": datetime.now().isoformat(),
            "initialized": self.initialized,
            "has_real_collector": self.collector is not None,
            "has_mock_generator": self.news_generator is not None
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
            logger.info("✅ 财联社新闻采集器初始化成功")
            
        except ImportError as e:
            logger.warning(f"⚠️  无法导入财联社采集器: {e}")
            logger.info("💡 将使用模拟数据模式运行")
            self.collector = None
        except Exception as e:
            logger.error(f"❌ 财联社采集器初始化失败: {e}")
            self.collector = None
    
    def _init_news_generator(self):
        """初始化模拟新闻生成器"""
        try:
            from news_crawler_service.services.enhanced_news_generator import EnhancedNewsGenerator
            self.news_generator = EnhancedNewsGenerator()
            logger.info("✅ 模拟新闻生成器初始化成功")
        except ImportError as e:
            logger.warning(f"⚠️  无法导入模拟新闻生成器: {e}")
            self.news_generator = None
    
    async def crawl_real_news(self, symbol: str = "全部", limit: int = 10) -> Dict[str, Any]:
        """
        抓取真实财联社新闻 - 主接口
        
        Args:
            symbol: 股票代码或"全部"
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
                    "请检查akshare_cls模块依赖"
                )
            
            # 设置采集器参数
            self.collector.symbol = symbol
            
            # 执行抓取
            news_items = await self.collector.fetch()
            
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
                    "source": "财联社 (akshare)",
                    "crawled_at": datetime.now().isoformat()
                },
                "metadata": self.service_metadata
            }
            
            logger.info(f"✅ 真实新闻抓取完成: {len(news_data)}条新闻")
            return result
            
        except Exception as e:
            logger.error(f"❌ 真实新闻抓取失败: {e}")
            traceback.print_exc()
            return self._create_error_response(str(e), operation)
    
    async def crawl_mock_news(self, count: int = 3, news_type: str = "stock") -> Dict[str, Any]:
        """
        生成模拟新闻 - 备选接口（当真实采集器不可用时使用）
        
        Args:
            count: 抓取数量
            news_type: 新闻类型
            
        Returns:
            模拟新闻数据
        """
        operation = "crawl_mock_news"
        
        try:
            logger.info(f"📡 生成模拟新闻: count={count}, type={news_type}")
            
            if not self.news_generator:
                return self._create_error_response(
                    "模拟新闻生成器未初始化", 
                    operation,
                    "无法生成模拟新闻"
                )
            
            # 调用模拟生成器
            news_list = await self.news_generator.generate_mock_news(count, news_type)
            
            # 构建响应
            result = {
                "operation": operation,
                "status": "success",
                "service": "NewsCrawlerService",
                "request": {
                    "count": count,
                    "news_type": news_type
                },
                "response": {
                    "news_count": len(news_list),
                    "news_list": news_list,
                    "generated_at": datetime.now().isoformat(),
                    "source": "mock_generator",
                    "note": "这是模拟数据，真实数据请使用 crawl_real_news"
                },
                "metadata": self.service_metadata
            }
            
            logger.info(f"✅ 模拟新闻生成完成: {len(news_list)}条{news_type}新闻")
            return result
            
        except Exception as e:
            logger.error(f"❌ 模拟新闻生成失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def crawl_news_auto(self, count: int = 5, prefer_real: bool = True) -> Dict[str, Any]:
        """
        智能抓取新闻 - 自动选择真实或模拟
        
        Args:
            count: 抓取数量
            prefer_real: 是否优先使用真实数据
            
        Returns:
            新闻数据
        """
        operation = "crawl_news_auto"
        
        try:
            logger.info(f"🤖 智能抓取新闻: count={count}, prefer_real={prefer_real}")
            
            # 检查真实采集器可用性
            real_available = False
            if prefer_real and self.collector:
                try:
                    real_available = await self.collector.health_check()
                    logger.info(f"真实采集器健康检查: {real_available}")
                except:
                    real_available = False
            
            # 根据可用性选择模式
            if real_available:
                result = await self.crawl_real_news("全部", count)
                result["operation"] = operation
                result["mode"] = "real"
            elif self.news_generator:
                result = await self.crawl_mock_news(count, "stock")
                result["operation"] = operation
                result["mode"] = "mock"
            else:
                return self._create_error_response(
                    "没有可用的新闻源", 
                    operation,
                    "真实采集器和模拟生成器都不可用"
                )
            
            result["prefer_real"] = prefer_real
            result["real_available"] = real_available
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 智能抓取失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def crawl_news_batch(
        self, 
        batch_size: int = 5, 
        mixed_types: bool = True,
        mode: str = "auto"  # auto, real, mock
    ) -> Dict[str, Any]:
        """
        批量抓取新闻
        
        Args:
            batch_size: 批次大小
            mixed_types: 是否混合类型（仅对mock模式有效）
            mode: 抓取模式 auto/real/mock
            
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
                result = await self.crawl_real_news("全部", batch_size)
                
            elif mode == "mock":
                # 模拟数据批次抓取
                if not self.news_generator:
                    return self._create_error_response(
                        "模拟生成器未初始化", 
                        operation,
                        "无法使用mock模式"
                    )
                batch_result = await self.news_generator.generate_news_batch(
                    batch_size=batch_size,
                    mixed_types=mixed_types
                )
                
                result = {
                    "operation": operation,
                    "status": "success",
                    "service": "NewsCrawlerService",
                    "request": {
                        "batch_size": batch_size,
                        "mixed_types": mixed_types,
                        "mode": mode
                    },
                    "response": batch_result,
                    "metadata": self.service_metadata
                }
                
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
        mock_healthy = False
        
        # 检查真实采集器
        if self.collector:
            try:
                real_healthy = await self.collector.health_check()
            except:
                real_healthy = False
        
        # 检查模拟生成器
        if self.news_generator:
            try:
                test_result = await self.crawl_mock_news(1, "stock")
                mock_healthy = test_result["status"] == "success"
            except:
                mock_healthy = False
        
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
                },
                "mock_generator": {
                    "available": self.news_generator is not None,
                    "healthy": mock_healthy,
                    "source": "模拟数据生成器" if self.news_generator else "未初始化"
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
        print(f"   模拟生成器: {status['components']['mock_generator']['available']}")
        
        # 2. 测试抓取（根据可用性选择）
        if status['components']['real_collector']['available']:
            print("\n2. 测试真实新闻抓取...")
            result = await service.crawl_real_news(limit=3)
        else:
            print("\n2. 真实采集器不可用，测试模拟新闻...")
            result = await service.crawl_mock_news(count=3)
        
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
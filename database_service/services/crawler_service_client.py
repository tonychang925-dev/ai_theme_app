"""
爬虫服务客户端 - 调用外部爬虫服务获取新闻数据
"""
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CrawlerServiceClient:
    """爬虫服务HTTP客户端"""
    
    def __init__(self, base_url: str, timeout: int = 60, max_retries: int = 5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        """创建HTTP会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "DatabaseService/1.0"}
            )
            logger.info(f"🔗 连接到爬虫服务: {self.base_url}")
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(f"🔌 断开爬虫服务连接")
    
    async def fetch_news(self, sources: List[str] = None,
                        keywords: List[str] = None,
                        limit: int = 100,
                        hours: int = 24) -> List[Dict[str, Any]]:
        """
        获取新闻
        
        Args:
            sources: 新闻源列表
            keywords: 关键词列表
            limit: 最大新闻数量
            hours: 时间范围（小时）
            
        Returns:
            新闻列表
        """
        await self.connect()
        
        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        payload = {
            "sources": sources or ["all"],
            "keywords": keywords or [],
            "limit": limit,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "request_id": f"fetch_{int(datetime.now().timestamp()*1000)}"
        }
        
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.base_url}/api/fetch_news",
                    json=payload,
                    timeout=self.timeout
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        news_list = result.get("news", [])
                        logger.info(f"✅ 获取新闻成功: {len(news_list)} 条")
                        return news_list
                    else:
                        error_text = await response.text()
                        logger.warning(f"⚠️ 获取新闻失败 (HTTP {response.status}): {error_text}")
                        
                        if response.status < 500:
                            return []
                        
                        last_exception = Exception(f"HTTP {response.status}: {error_text}")
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ 获取新闻超时 (尝试 {attempt + 1}/{self.max_retries})")
                last_exception = asyncio.TimeoutError("Request timeout")
            except aiohttp.ClientError as e:
                logger.warning(f"⚠️ 客户端错误 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                last_exception = e
            
            # 指数退避（爬虫服务需要更长的退避时间）
            if attempt < self.max_retries - 1:
                delay = 3 ** attempt  # 3, 9, 27秒
                await asyncio.sleep(delay)
        
        # 所有重试都失败
        logger.error(f"❌ 获取新闻失败，已达最大重试次数")
        return []
    
    async def fetch_specific_news(self, news_ids: List[str]) -> List[Dict[str, Any]]:
        """
        获取指定新闻
        
        Args:
            news_ids: 新闻ID列表
            
        Returns:
            新闻详情列表
        """
        await self.connect()
        
        payload = {
            "news_ids": news_ids,
            "request_id": f"fetch_specific_{int(datetime.now().timestamp()*1000)}"
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/fetch_specific",
                json=payload,
                timeout=self.timeout
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    return result.get("news", [])
                else:
                    logger.error(f"获取指定新闻失败: HTTP {response.status}")
                    return []
        
        except Exception as e:
            logger.error(f"获取指定新闻异常: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        await self.connect()
        
        try:
            start_time = datetime.now()
            async with self.session.get(
                f"{self.base_url}/health",
                timeout=10  # 爬虫服务可能需要更长时间
            ) as response:
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    return {
                        "healthy": True,
                        "status_code": response.status,
                        "response_time_ms": response_time,
                        "details": data
                    }
                else:
                    return {
                        "healthy": False,
                        "status_code": response.status,
                        "response_time_ms": response_time,
                        "error": f"HTTP {response.status}"
                    }
        
        except asyncio.TimeoutError:
            return {
                "healthy": False,
                "error": "Timeout after 10 seconds",
                "response_time_ms": 10000
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }
    
    async def get_sources(self) -> List[str]:
        """获取可用的新闻源"""
        await self.connect()
        
        try:
            async with self.session.get(
                f"{self.base_url}/api/sources",
                timeout=10
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    return result.get("sources", [])
                return []
        
        except Exception as e:
            logger.error(f"获取新闻源失败: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计"""
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "connected": self.session is not None and not self.session.closed
        }

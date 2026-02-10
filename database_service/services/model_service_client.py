"""
模型服务客户端 - 调用外部AI模型服务进行事件提取和分类
"""
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class ModelServiceClient:
    """模型服务HTTP客户端"""
    
    def __init__(self, base_url: str, timeout: int = 30, max_retries: int = 3):
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
            logger.info(f"🔗 连接到模型服务: {self.base_url}")
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(f"🔌 断开模型服务连接")
    
    async def extract_event(self, title: str, content: str, 
                           keywords: List[str] = None) -> Dict[str, Any]:
        """
        提取事件
        
        Args:
            title: 新闻标题
            content: 新闻内容
            keywords: 关键词列表
            
        Returns:
            提取结果，包含classification字段
        """
        await self.connect()
        
        payload = {
            "title": title,
            "content": content,
            "keywords": keywords or [],
            "request_id": f"req_{int(datetime.now().timestamp()*1000)}",
            "timestamp": datetime.now().isoformat()
        }
        
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.base_url}/api/event_extract",
                    json=payload,
                    timeout=self.timeout
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✅ 事件提取成功: {result.get('classification', 'unknown')}")
                        return {
                            "success": True,
                            "data": result,
                            "classification": result.get("classification", "normal"),
                            "confidence": result.get("confidence", 0.0),
                            "attempts": attempt + 1
                        }
                    else:
                        error_text = await response.text()
                        logger.warning(f"⚠️ 事件提取失败 (HTTP {response.status}): {error_text}")
                        
                        # 非5xx错误不重试
                        if response.status < 500:
                            return {
                                "success": False,
                                "error": f"HTTP {response.status}: {error_text}",
                                "classification": "error"
                            }
                        
                        last_exception = Exception(f"HTTP {response.status}: {error_text}")
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ 事件提取超时 (尝试 {attempt + 1}/{self.max_retries})")
                last_exception = asyncio.TimeoutError("Request timeout")
            except aiohttp.ClientError as e:
                logger.warning(f"⚠️ 客户端错误 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                last_exception = e
            
            # 指数退避
            if attempt < self.max_retries - 1:
                delay = 2 ** attempt  # 1, 2, 4秒
                await asyncio.sleep(delay)
        
        # 所有重试都失败
        logger.error(f"❌ 事件提取失败，已达最大重试次数")
        return {
            "success": False,
            "error": str(last_exception) if last_exception else "Unknown error",
            "classification": "error",
            "attempts": self.max_retries
        }
    
    async def batch_extract(self, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量提取事件
        
        Args:
            requests: 请求列表，每个请求包含title, content, keywords
            
        Returns:
            提取结果列表
        """
        await self.connect()
        
        payload = {
            "batch": requests,
            "batch_id": f"batch_{int(datetime.now().timestamp()*1000)}",
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/batch_extract",
                json=payload,
                timeout=self.timeout * 2  # 批量处理需要更长时间
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ 批量事件提取成功: {len(result.get('results', []))} 条")
                    return result.get("results", [])
                else:
                    error_text = await response.text()
                    logger.error(f"❌ 批量事件提取失败: HTTP {response.status}")
                    
                    # 返回所有失败的标记
                    return [{
                        "success": False,
                        "error": f"Batch failed: HTTP {response.status}",
                        "classification": "error"
                    } for _ in requests]
        
        except Exception as e:
            logger.error(f"❌ 批量事件提取异常: {e}")
            return [{
                "success": False,
                "error": str(e),
                "classification": "error"
            } for _ in requests]
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        await self.connect()
        
        try:
            start_time = datetime.now()
            async with self.session.get(
                f"{self.base_url}/health",
                timeout=5
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
                "error": "Timeout after 5 seconds",
                "response_time_ms": 5000
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }
    
    async def get_capabilities(self) -> Dict[str, Any]:
        """获取服务能力"""
        try:
            async with self.session.get(
                f"{self.base_url}/api/capabilities",
                timeout=10
            ) as response:
                if response.status == 200:
                    return await response.json()
                return {"error": f"HTTP {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计"""
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "connected": self.session is not None and not self.session.closed
        }

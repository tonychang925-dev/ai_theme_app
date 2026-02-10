"""
题材服务客户端 - 调用外部题材服务进行主题匹配
"""
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class ThemeServiceClient:
    """题材服务HTTP客户端"""
    
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
            logger.info(f"🔗 连接到题材服务: {self.base_url}")
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(f"🔌 断开题材服务连接")
    
    async def match_themes(self, event_data: Dict[str, Any], 
                          limit: int = 5) -> List[Dict[str, Any]]:
        """
        匹配主题
        
        Args:
            event_data: 事件数据，包含title, content, keywords等
            limit: 返回的最大主题数量
            
        Returns:
            匹配的主题列表，每个主题包含theme_id, confidence等
        """
        await self.connect()
        
        payload = {
            "event_data": event_data,
            "limit": limit,
            "request_id": f"match_{int(datetime.now().timestamp()*1000)}",
            "timestamp": datetime.now().isoformat()
        }
        
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.base_url}/api/theme_match",
                    json=payload,
                    timeout=self.timeout
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        matched_themes = result.get("matched_themes", [])
                        logger.info(f"✅ 主题匹配成功: {len(matched_themes)} 个主题")
                        return matched_themes
                    else:
                        error_text = await response.text()
                        logger.warning(f"⚠️ 主题匹配失败 (HTTP {response.status}): {error_text}")
                        
                        if response.status < 500:
                            return []
                        
                        last_exception = Exception(f"HTTP {response.status}: {error_text}")
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ 主题匹配超时 (尝试 {attempt + 1}/{self.max_retries})")
                last_exception = asyncio.TimeoutError("Request timeout")
            except aiohttp.ClientError as e:
                logger.warning(f"⚠️ 客户端错误 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                last_exception = e
            
            # 指数退避
            if attempt < self.max_retries - 1:
                delay = 2 ** attempt
                await asyncio.sleep(delay)
        
        # 所有重试都失败
        logger.error(f"❌ 主题匹配失败，已达最大重试次数")
        return []
    
    async def get_theme_details(self, theme_ids: List[int]) -> List[Dict[str, Any]]:
        """
        获取主题详情
        
        Args:
            theme_ids: 主题ID列表
            
        Returns:
            主题详情列表
        """
        await self.connect()
        
        payload = {
            "theme_ids": theme_ids,
            "request_id": f"details_{int(datetime.now().timestamp()*1000)}"
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/theme_details",
                json=payload,
                timeout=self.timeout
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    return result.get("themes", [])
                else:
                    logger.error(f"获取主题详情失败: HTTP {response.status}")
                    return []
        
        except Exception as e:
            logger.error(f"获取主题详情异常: {e}")
            return []
    
    async def update_theme_28_fields(self, theme_id: int, 
                                   updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新主题的28字段
        
        Args:
            theme_id: 主题ID
            updates: 更新字段
            
        Returns:
            更新结果
        """
        await self.connect()
        
        payload = {
            "theme_id": theme_id,
            "updates": updates,
            "request_id": f"update_{int(datetime.now().timestamp()*1000)}"
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/theme_update",
                json=payload,
                timeout=self.timeout
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ 主题更新成功: {theme_id}")
                    return {
                        "success": True,
                        "data": result,
                        "theme_id": theme_id
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"❌ 主题更新失败 {theme_id}: HTTP {response.status}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {error_text}",
                        "theme_id": theme_id
                    }
        
        except Exception as e:
            logger.error(f"❌ 主题更新异常 {theme_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "theme_id": theme_id
            }
    
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
    
    def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计"""
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "connected": self.session is not None and not self.session.closed
        }

# database_service/services/news_service.py
"""
新闻服务层 - 封装新闻相关的业务逻辑
实现数据访问和Stream处理的解耦
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import json

logger = logging.getLogger(__name__)


class NewsService:
    """新闻服务 - 核心业务逻辑层"""
    
    def __init__(self, database_gateway, stream_gateway=None, config=None):
        """
        初始化新闻服务
        
        Args:
            database_gateway: 数据库网关（Data Access Layer）
            stream_gateway: Stream网关（可选，用于发布事件）
            config: 配置
        """
        self.db_gateway = database_gateway
        self.stream_gateway = stream_gateway
        self.config = config or {}
        
        logger.info("📰 新闻服务初始化完成")
        logger.info(f"   数据库网关: {database_gateway.__class__.__name__}")
        logger.info(f"   Stream网关: {stream_gateway.__class__.__name__ if stream_gateway else '未启用'}")
    
    # ========== 核心新闻操作 ==========
    
    async def create_news(self, news_data: Dict[str, Any], 
                         publish_to_stream: bool = True) -> Dict[str, Any]:
        """
        创建新闻（完整业务逻辑）
        
        Args:
            news_data: 新闻数据
            publish_to_stream: 是否发布到Stream
            
        Returns:
            包含完整结果的信息
        """
        result = {
            "success": False,
            "news_id": None,
            "message_id": None,
            "is_new": True,
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 1. 验证新闻数据
            validation_result = self._validate_news_data(news_data)
            if not validation_result["valid"]:
                result["error"] = validation_result["error"]
                return result
            
            # 2. 保存到数据库
            db_result = await self._save_to_database(news_data)
            
            if not db_result["success"]:
                result["error"] = db_result["error"]
                return result
            
            result["news_id"] = db_result["news_id"]
            result["is_new"] = db_result["is_new"]
            result["success"] = True
            
            # 3. 发布到Stream（如果配置了且是新新闻）
            if publish_to_stream and self.stream_gateway and result["is_new"]:
                stream_result = await self._publish_to_stream(news_data)
                result["message_id"] = stream_result.get("message_id")
                result["stream_published"] = stream_result.get("success", False)
            
            logger.info(f"✅ 新闻服务 - 创建成功: {result['news_id']} (新记录: {result['is_new']})")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"❌ 新闻服务 - 创建失败: {e}")
        
        return result
    
    async def get_news(self, news_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        获取新闻（带缓存策略）
        
        Args:
            news_id: 新闻ID
            use_cache: 是否使用缓存
            
        Returns:
            新闻数据或None
        """
        try:
            # 如果有缓存管理器，优先使用缓存
            if use_cache and hasattr(self.db_gateway, 'get_news'):
                news = await self.db_gateway.get_news(news_id)
                
                # 如果是通过缓存获取的，记录缓存命中
                if news and hasattr(self.db_gateway, 'cache_stats'):
                    stats = await self.db_gateway.get_cache_stats()
                    cache_hit = stats.get('cache_hit_rate', 0)
                    logger.debug(f"📊 缓存命中率: {cache_hit:.1%}")
                
                return news
            else:
                # 降级到直接数据库查询
                if hasattr(self.db_gateway, 'postgres_manager'):
                    return await self.db_gateway.postgres_manager.get_news(news_id)
                else:
                    logger.warning("无法获取新闻：缺少数据库访问方法")
                    return None
                    
        except Exception as e:
            logger.error(f"获取新闻失败 {news_id}: {e}")
            return None
    
    async def get_recent_news(self, limit: int = 100, 
                             category: Optional[str] = None,
                             market: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取最近新闻（带过滤条件）
        
        Args:
            limit: 返回数量
            category: 分类过滤
            market: 市场过滤
            
        Returns:
            新闻列表
        """
        try:
            # 获取基础新闻列表
            if hasattr(self.db_gateway, 'get_recent_news'):
                news_list = await self.db_gateway.get_recent_news(limit)
            elif hasattr(self.db_gateway, 'postgres_manager'):
                news_list = await self.db_gateway.postgres_manager.get_recent_news(limit)
            else:
                return []
            
            # 应用过滤器
            filtered_news = []
            for news in news_list:
                # 市场过滤
                if market and news.get('market') != market:
                    continue
                
                # 分类过滤（通过关键词或元数据）
                if category and not self._news_matches_category(news, category):
                    continue
                
                filtered_news.append(news)
            
            logger.info(f"✅ 获取最近新闻: {len(filtered_news)}/{len(news_list)} 条")
            return filtered_news
            
        except Exception as e:
            logger.error(f"获取最近新闻失败: {e}")
            return []
    
    async def search_news(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        搜索新闻
        
        Args:
            query: 搜索关键词
            limit: 返回数量
            
        Returns:
            匹配的新闻列表
        """
        try:
            # 如果有搜索功能，使用搜索
            if hasattr(self.db_gateway, 'search_news'):
                return await self.db_gateway.search_news(query, limit)
            
            # 否则使用关键词匹配
            news_list = await self.get_recent_news(limit * 2)  # 获取更多用于过滤
            
            matched_news = []
            query_lower = query.lower()
            
            for news in news_list:
                # 在标题、内容、关键词中搜索
                title_match = query_lower in (news.get('title', '') or '').lower()
                content_match = query_lower in (news.get('content', '') or '').lower()
                
                # 关键词匹配
                keywords_match = False
                keywords = news.get('keywords', [])
                if isinstance(keywords, list):
                    for keyword in keywords:
                        if query_lower in keyword.lower():
                            keywords_match = True
                            break
                
                if title_match or content_match or keywords_match:
                    matched_news.append(news)
                
                if len(matched_news) >= limit:
                    break
            
            logger.info(f"🔍 新闻搜索: '{query}' 找到 {len(matched_news)} 条结果")
            return matched_news
            
        except Exception as e:
            logger.error(f"搜索新闻失败: {e}")
            return []
    
    async def batch_create_news(self, news_list: List[Dict[str, Any]], 
                               publish_to_stream: bool = True) -> Dict[str, Any]:
        """
        批量创建新闻
        
        Args:
            news_list: 新闻数据列表
            publish_to_stream: 是否发布到Stream
            
        Returns:
            批量操作结果
        """
        batch_result = {
            "batch_id": f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "total_count": len(news_list),
            "success_count": 0,
            "failed_count": 0,
            "new_count": 0,
            "duplicate_count": 0,
            "results": [],
            "start_time": datetime.now().isoformat()
        }
        
        if not news_list:
            batch_result["error"] = "新闻列表为空"
            return batch_result
        
        logger.info(f"📦 开始批量创建新闻: {len(news_list)} 条")
        
        # 并行处理（限制并发数）
        max_concurrent = self.config.get("max_concurrent_operations", 10)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single_news(news_data, index):
            async with semaphore:
                try:
                    result = await self.create_news(news_data, publish_to_stream)
                    result["sequence"] = index + 1
                    return result
                except Exception as e:
                    return {
                        "success": False,
                        "error": str(e),
                        "sequence": index + 1,
                        "timestamp": datetime.now().isoformat()
                    }
        
        # 创建任务
        tasks = []
        for i, news_data in enumerate(news_list):
            task = asyncio.create_task(process_single_news(news_data, i))
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 统计结果
        for result in results:
            batch_result["results"].append(result)
            
            if result.get("success"):
                batch_result["success_count"] += 1
                
                if result.get("is_new"):
                    batch_result["new_count"] += 1
                else:
                    batch_result["duplicate_count"] += 1
            else:
                batch_result["failed_count"] += 1
        
        batch_result["end_time"] = datetime.now().isoformat()
        batch_result["duration_seconds"] = (
            datetime.fromisoformat(batch_result["end_time"]) - 
            datetime.fromisoformat(batch_result["start_time"])
        ).total_seconds()
        
        success_rate = batch_result["success_count"] / max(batch_result["total_count"], 1)
        logger.info(f"📦 批量创建完成: {batch_result['success_count']}/{batch_result['total_count']} 成功 ({success_rate:.1%})")
        
        return batch_result
    
    # ========== 业务逻辑方法 ==========
    
    async def process_news_stream(self, stream_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理从Stream收到的新闻数据
        
        Args:
            stream_data: Stream消息数据
            
        Returns:
            处理结果
        """
        try:
            # 提取新闻数据
            news_data = stream_data.get('news_data', stream_data)
            
            # 添加Stream元数据
            if 'metadata' not in news_data:
                news_data['metadata'] = {}
            
            news_data['metadata'].update({
                'stream_source': stream_data.get('event_type', 'unknown'),
                'stream_timestamp': stream_data.get('timestamp'),
                'processed_by_service': True
            })
            
            # 创建新闻
            result = await self.create_news(news_data, publish_to_stream=False)
            
            # 如果需要，发布处理完成事件
            if result["success"] and self.stream_gateway:
                await self._publish_processing_event(result, "processed")
            
            return result
            
        except Exception as e:
            logger.error(f"处理Stream新闻失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def get_news_statistics(self, time_range: str = "daily") -> Dict[str, Any]:
        """
        获取新闻统计
        
        Args:
            time_range: 时间范围（daily, weekly, monthly）
            
        Returns:
            统计信息
        """
        try:
            # 获取最近新闻
            recent_news = await self.get_recent_news(limit=1000)
            
            # 按来源统计
            source_stats = {}
            market_stats = {}
            date_stats = {}
            
            for news in recent_news:
                # 来源统计
                source = news.get('source', 'unknown')
                source_stats[source] = source_stats.get(source, 0) + 1
                
                # 市场统计
                market = news.get('market', 'unknown')
                market_stats[market] = market_stats.get(market, 0) + 1
                
                # 日期统计
                publish_date = news.get('publish_date')
                if publish_date:
                    if isinstance(publish_date, str):
                        date_key = publish_date.split('T')[0] if 'T' in publish_date else publish_date
                    else:
                        date_key = str(publish_date)
                    date_stats[date_key] = date_stats.get(date_key, 0) + 1
            
            # 按数量排序
            top_sources = sorted(source_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            top_markets = sorted(market_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            
            stats = {
                "total_count": len(recent_news),
                "time_range": time_range,
                "top_sources": dict(top_sources),
                "top_markets": dict(top_markets),
                "date_distribution": dict(sorted(date_stats.items(), reverse=True)[:10]),
                "generated_at": datetime.now().isoformat()
            }
            
            logger.info(f"📊 新闻统计: {len(recent_news)} 条新闻")
            return stats
            
        except Exception as e:
            logger.error(f"获取新闻统计失败: {e}")
            return {
                "total_count": 0,
                "error": str(e),
                "generated_at": datetime.now().isoformat()
            }
    
    async def cleanup_old_news(self, days: int = 30) -> Dict[str, Any]:
        """
        清理旧新闻（模拟）
        
        Args:
            days: 保留天数
            
        Returns:
            清理结果
        """
        try:
            # 在实际实现中，这里会执行数据库删除操作
            # 目前只返回模拟结果
            
            cutoff_date = (datetime.now() - timedelta(days=days)).date()
            
            result = {
                "success": True,
                "days": days,
                "cutoff_date": cutoff_date.isoformat(),
                "cleaned_count": 0,  # 模拟值
                "retained_count": 100,  # 模拟值
                "message": f"清理 {days} 天前的新闻（模拟操作）",
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"🧹 新闻清理: 保留最近 {days} 天新闻")
            return result
            
        except Exception as e:
            logger.error(f"清理新闻失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    # ========== 私有方法 ==========
    
    def _validate_news_data(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证新闻数据"""
        required_fields = ['news_id', 'title', 'content', 'source', 'publish_date']
        missing_fields = [field for field in required_fields if field not in news_data]
        
        if missing_fields:
            return {
                "valid": False,
                "error": f"缺少必要字段: {missing_fields}"
            }
        
        # 验证news_id格式
        news_id = news_data['news_id']
        if not isinstance(news_id, str) or len(news_id) < 5:
            return {
                "valid": False,
                "error": f"news_id格式无效: {news_id}"
            }
        
        # 验证标题长度
        title = news_data['title']
        if not isinstance(title, str) or len(title) < 5 or len(title) > 500:
            return {
                "valid": False,
                "error": f"标题长度无效: {len(title)}字符 (需要5-500字符)"
            }
        
        return {"valid": True}
    
    async def _save_to_database(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存到数据库"""
        try:
            if hasattr(self.db_gateway, 'create_news'):
                news_id = await self.db_gateway.create_news(news_data)
                
                # 检查是否是重复记录
                is_new = True
                if hasattr(self.db_gateway, 'postgres_manager'):
                    # 检查数据库返回的news_id是否与输入相同
                    existing_news = await self.db_gateway.postgres_manager.get_news(news_data['news_id'])
                    if existing_news and existing_news.get('news_id') == news_id:
                        is_new = False
                
                return {
                    "success": True,
                    "news_id": news_id,
                    "is_new": is_new
                }
            else:
                return {
                    "success": False,
                    "error": "数据库网关不支持create_news方法"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _publish_to_stream(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """发布到Stream"""
        if not self.stream_gateway:
            return {"success": False, "error": "Stream网关未配置"}
        
        try:
            # 尝试不同的发布方法
            if hasattr(self.stream_gateway, 'publish_news_to_stream'):
                message_id = await self.stream_gateway.publish_news_to_stream(news_data)
            elif hasattr(self.stream_gateway, 'smart_publish'):
                message_id = await self.stream_gateway.smart_publish(news_data, "news")
            elif hasattr(self.stream_gateway, 'publish_to_stream'):
                message_data = {
                    "event_type": "news.created",
                    "news_data": news_data,
                    "timestamp": datetime.now().isoformat(),
                    "source": "news_service"
                }
                message_id = await self.stream_gateway.publish_to_stream(
                    stream="news_raw",
                    data=message_data
                )
            else:
                return {"success": False, "error": "Stream网关不支持发布方法"}
            
            return {
                "success": True,
                "message_id": message_id
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _publish_processing_event(self, result: Dict[str, Any], event_type: str):
        """发布处理事件"""
        try:
            if self.stream_gateway and hasattr(self.stream_gateway, 'publish_to_stream'):
                event_data = {
                    "event_type": f"news.{event_type}",
                    "news_id": result.get("news_id"),
                    "success": result.get("success"),
                    "is_new": result.get("is_new"),
                    "timestamp": datetime.now().isoformat(),
                    "source": "news_service"
                }
                
                await self.stream_gateway.publish_to_stream(
                    stream="events_news",
                    data=event_data
                )
                
                logger.debug(f"📤 发布处理事件: {event_type}")
                
        except Exception as e:
            logger.warning(f"发布处理事件失败: {e}")
    
    def _news_matches_category(self, news: Dict[str, Any], category: str) -> bool:
        """检查新闻是否匹配分类"""
        # 检查关键词
        keywords = news.get('keywords', [])
        if isinstance(keywords, list):
            for keyword in keywords:
                if category.lower() in keyword.lower():
                    return True
        
        # 检查市场
        market = news.get('market', '')
        if category.lower() in market.lower():
            return True
        
        # 检查标题和内容
        title = news.get('title', '').lower()
        content = news.get('content', '').lower()
        
        if category.lower() in title or category.lower() in content:
            return True
        
        return False
    
    # ========== 服务状态和管理 ==========
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        checks = {
            "database": {"healthy": False, "message": "未检查"},
            "stream": {"healthy": False, "message": "未配置"},
            "overall": False
        }
        
        try:
            # 检查数据库
            if hasattr(self.db_gateway, 'health_check'):
                db_healthy = await self.db_gateway.health_check()
                checks["database"] = {
                    "healthy": db_healthy,
                    "message": "数据库连接正常" if db_healthy else "数据库连接失败"
                }
            
            # 检查Stream
            if self.stream_gateway:
                if hasattr(self.stream_gateway, 'health_check'):
                    stream_healthy = await self.stream_gateway.health_check()
                    checks["stream"] = {
                        "healthy": stream_healthy,
                        "message": "Stream连接正常" if stream_healthy else "Stream连接失败"
                    }
                else:
                    checks["stream"] = {
                        "healthy": True,
                        "message": "Stream网关已配置（无健康检查方法）"
                    }
            else:
                checks["stream"] = {
                    "healthy": True,
                    "message": "Stream网关未配置（跳过检查）"
                }
            
            # 总体状态
            checks["overall"] = checks["database"]["healthy"] and checks["stream"]["healthy"]
            checks["timestamp"] = datetime.now().isoformat()
            
        except Exception as e:
            checks["error"] = str(e)
            checks["overall"] = False
        
        return checks
    
    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        return {
            "service_name": self.__class__.__name__,
            "description": "新闻业务服务层 - 封装新闻相关的业务逻辑",
            "database_gateway": self.db_gateway.__class__.__name__,
            "stream_gateway": self.stream_gateway.__class__.__name__ if self.stream_gateway else None,
            "config": self.config,
            "created_at": datetime.now().isoformat()
        }


# 便捷函数：创建新闻服务
async def create_news_service(database_gateway, stream_gateway=None, config=None) -> NewsService:
    """创建新闻服务实例"""
    service = NewsService(database_gateway, stream_gateway, config)
    logger.info("✅ 新闻服务创建完成")
    return service
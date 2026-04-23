# database_service/streams/schedulers/improved_news_stream_scheduler.py
"""
改进的新闻Stream调度器 - 优化版本
职责：调用新闻抓取服务 → 发布到Redis Stream
仅支持真实新闻数据
"""
import hashlib
import time
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import traceback

logger = logging.getLogger(__name__)


class ImprovedNewsStreamScheduler:
    """改进的新闻Stream调度器 - 仅支持真实新闻数据"""
    
    def __init__(self, stream_gateway, news_service, config=None):
        """
        Args:
            stream_gateway: Stream增强网关（用于发布消息）
            news_service: 新闻服务（NewsCrawlerService实例）
            config: 配置
        """
        self.stream_gateway = stream_gateway
        self.news_service = news_service
        self.config = config or {}
        
        # 运行状态
        self.running = False
        self.scheduler_task = None
        
        # 统计信息
        self.stats = {
            "scheduler": "ImprovedNewsStreamScheduler",
            "version": "3.0.0",  # 更新版本
            "started_at": None,
            "last_run_at": None,
            "total_batches": 0,
            "total_news": 0,
            "published_count": 0,
            "error_count": 0,
            "batches": [],
            "news_sources": {
                "real": 0,
                "unknown": 0
            }
        }
        
        # 调度配置 - 仅真实模式
        self.schedule_config = {
            "interval_seconds": self.config.get("interval_seconds", 30),
            "batch_size": self.config.get("batch_size", 3),
            "news_type": self.config.get("news_type", "stock"),
            "stream_name": self.config.get("stream_name", "stream:news:raw"),
            "mixed_types": self.config.get("mixed_types", True),
            "crawl_mode": self.config.get("crawl_mode", "auto"),  # auto/real
            "prefer_real": self.config.get("prefer_real", True),
            "max_real_retries": self.config.get("max_real_retries", 2)
        }
        
        logger.info(f"📅 改进版新闻Stream调度器初始化完成 (v{self.stats['version']})")
        logger.info(f"   新闻服务: {news_service.__class__.__name__}")
        logger.info(f"   抓取模式: {self.schedule_config['crawl_mode']}")
        logger.info(f"   间隔: {self.schedule_config['interval_seconds']}秒")
        logger.info(f"   批次大小: {self.schedule_config['batch_size']}")
    
    async def start_scheduling(self):
        """启动调度"""
        if self.running:
            logger.warning("调度器已经在运行")
            return
        
        self.running = True
        self.stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动改进版新闻Stream调度器")
        
        # 启动调度任务
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        return True
    
    async def _scheduler_loop(self):
        """调度器主循环"""
        real_retry_count = 0  # 真实新闻抓取重试计数
        
        while self.running:
            try:
                batch_start_time = datetime.now()
                batch_id = f"batch_{batch_start_time.strftime('%Y%m%d_%H%M%S')}"
                
                logger.info(f"\n🔄 开始新闻批次: {batch_id}")
                logger.info(f"   模式: {self.schedule_config['crawl_mode']}")
                
                # 1. 调用新闻服务获取新闻
                batch_result = await self._fetch_news_batch(
                    batch_id, 
                    real_retry_count
                )
                
                # 更新重试计数
                if batch_result.get("source_type") == "real":
                    real_retry_count = 0  # 重置重试计数
                elif batch_result.get("source_type") == "unknown" and "fallback" in batch_result:
                    real_retry_count += 1  # 增加重试计数
                
                # 2. 发布到Stream
                publish_result = await self._publish_to_stream(batch_result)
                
                # 3. 更新统计
                await self._update_stats(batch_result, publish_result, batch_start_time)
                
                # 4. 等待下次调度
                if self.running:
                    interval = self.schedule_config["interval_seconds"]
                    logger.info(f"⏳ 等待 {interval} 秒后下次调度...")
                    await asyncio.sleep(interval)
                    
            except asyncio.CancelledError:
                logger.info("调度器被取消")
                break
            except Exception as e:
                logger.error(f"调度器循环异常: {e}")
                self.stats["error_count"] += 1
                await asyncio.sleep(10)
    
    async def _fetch_news_batch(self, batch_id: str, real_retry_count: int) -> Dict[str, Any]:
        """调用新闻服务获取新闻批次 - 仅真实数据"""
        try:
            batch_size = self.schedule_config["batch_size"]
            news_type = self.schedule_config["news_type"]
            crawl_mode = self.schedule_config["crawl_mode"]
            prefer_real = self.schedule_config["prefer_real"]
            
            logger.info(f"📡 调用新闻服务: {batch_size}条新闻, 模式: {crawl_mode}")
            
            result = None
            source_type = "unknown"
            fallback_reason = None
            
            try:
                # 根据模式选择抓取方式
                if crawl_mode == "real":
                    # 强制使用真实数据
                    logger.info("🟢 使用真实新闻模式...")
                    result = await self.news_service.crawl_real_news(limit=batch_size)
                    source_type = "real"
                    
                elif crawl_mode == "mock":
                    logger.warning("mock模式已禁用，自动切换为real")
                    result = await self.news_service.crawl_real_news(limit=batch_size)
                    source_type = "real"
                    
                else:  # auto 模式
                    # 智能选择
                    logger.info("🤖 使用智能模式...")
                    
                    if real_retry_count >= self.schedule_config["max_real_retries"]:
                        logger.warning(f"⚠️  真实新闻抓取失败次数过多({real_retry_count})，继续尝试真实源")
                        result = await self.news_service.crawl_real_news(limit=batch_size)
                        source_type = "real"
                    
                    elif prefer_real:
                        # 优先尝试真实数据
                        logger.info("🟢 优先尝试真实新闻...")
                        try:
                            result = await self.news_service.crawl_real_news(limit=batch_size)
                            if result.get("status") == "success" and result.get("response", {}).get("news_count", 0) > 0:
                                source_type = "real"
                                logger.info("✅ 真实新闻抓取成功")
                            else:
                                raise Exception("真实新闻返回空数据")
                        except Exception as e:
                            logger.warning(f"⚠️  真实新闻抓取失败: {e}")
                            raise e
                    else:
                        # prefer_real=False 时也只允许真实源
                        logger.info("🟢 仅支持真实源，执行真实新闻抓取...")
                        result = await self.news_service.crawl_real_news(limit=batch_size)
                        source_type = "real"
                
            except Exception as e:
                logger.error(f"新闻抓取异常: {e}")
                # 如果所有模式都失败，创建一个空的批次
                result = {
                    "status": "error",
                    "error": str(e),
                    "response": {"news_list": []}
                }
                source_type = "unknown"
            
            # 统一提取新闻列表
            news_list = []
            if result and result.get("status") == "success":
                if "news_list" in result.get("response", {}):
                    news_list = result["response"]["news_list"]
                elif "batch_info" in result.get("response", {}) and "news_list" in result["response"]["batch_info"]:
                    news_list = result["response"]["batch_info"]["news_list"]
            
            batch_result = {
                "batch_id": batch_id,
                "news_service": self.news_service.__class__.__name__,
                "batch_size": len(news_list),
                "news_list": news_list,
                "fetch_result": result,
                "fetch_time": datetime.now().isoformat(),
                "source_type": source_type,
                "crawl_mode": crawl_mode,
                "real_retry_count": real_retry_count
            }
            
            if fallback_reason:
                batch_result["fallback_reason"] = fallback_reason
                batch_result["fallback"] = True
            
            # 记录源类型统计
            if source_type == "real":
                self.stats["news_sources"]["real"] += len(news_list)
                logger.info(f"✅ 获取 {len(news_list)} 条真实新闻")
            else:
                self.stats["news_sources"]["unknown"] += len(news_list)
                logger.info(f"❌ 获取新闻失败")
            
            return batch_result
            
        except Exception as e:
            logger.error(f"获取新闻批次失败: {e}")
            logger.exception("Unhandled exception")
            return {
                "batch_id": batch_id,
                "error": str(e),
                "news_list": [],
                "batch_size": 0,
                "source_type": "unknown"
            }
    
    async def _publish_to_stream(self, batch_result: Dict[str, Any]) -> Dict[str, Any]:
        """发布新闻批次到Stream - 阶段3优化版"""
        publish_results = {
            "batch_id": batch_result["batch_id"],
            "total_news": len(batch_result["news_list"]),
            "published_count": 0,
            "failed_count": 0,
            "message_ids": [],
            "errors": [],
            "source_type": batch_result.get("source_type", "unknown"),
            "total_size_bytes": 0,  # 新增：统计总字节数
            "avg_size_bytes": 0     # 新增：统计平均字节数
        }
        
        if not batch_result["news_list"]:
            logger.warning("批次中没有新闻可发布")
            return publish_results
        
        stream_name = self.schedule_config["stream_name"]
        source_type = batch_result.get("source_type", "unknown")
        
        logger.info(f"📤 发布批次到Stream: {stream_name} ({source_type}数据)")
        
        # 生成短批次ID
        short_batch_id = batch_result["batch_id"][:12]
        
        for i, news_data in enumerate(batch_result["news_list"]):
            try:
                # 1. 增强新闻数据（获取完整内容）
                enhanced_news = self._enhance_news_data(news_data, batch_result, i)
                
                # 2. 创建v2精简消息
                stream_message = self._create_v2_message(enhanced_news, i, short_batch_id, source_type)
                
                # 3. 计算消息大小
                msg_json = json.dumps(stream_message, ensure_ascii=False)
                msg_size = len(msg_json)
                publish_results["total_size_bytes"] += msg_size
                
                # 4. 调试日志（只记录前几条）
                if i < 3:  # 只显示前3条的详细信息
                    title = stream_message.get('t', '')[:30]
                    logger.debug(f"📤 发布v2消息 [{i+1}] 标题: {title}..., 大小: {msg_size}字节")
                
                # 5. 发布消息
                message_id = await self.stream_gateway.publish_to_stream(
                    stream_name,      # stream_key
                    stream_message    # 精简消息数据
                )
                
                if message_id:
                    publish_results["published_count"] += 1
                    publish_results["message_ids"].append(message_id)
                    
                    # 每10条记录一次进度
                    if (i + 1) % 10 == 0:
                        logger.debug(f"  已发布 {i+1}/{len(batch_result['news_list'])}")
                else:
                    publish_results["failed_count"] += 1
                    publish_results["errors"].append(f"新闻发布失败: {enhanced_news.get('news_id', 'unknown')}")
                    
            except Exception as e:
                publish_results["failed_count"] += 1
                error_msg = f"发布异常 {enhanced_news.get('news_id', 'unknown') if 'enhanced_news' in locals() else 'unknown'}: {str(e)}"
                publish_results["errors"].append(error_msg)
                logger.error(f"发布新闻失败: {e}")
        
        # 计算统计信息
        if publish_results["published_count"] > 0:
            publish_results["avg_size_bytes"] = publish_results["total_size_bytes"] / publish_results["published_count"]
        
        # 记录优化效果
        success_rate = publish_results["published_count"] / max(publish_results["total_news"], 1)
        
        # 📊 详细发布统计
        logger.info(f"📊 批次发布统计:")
        logger.info(f"   成功: {publish_results['published_count']}, 失败: {publish_results['failed_count']}")
        logger.info(f"   总大小: {publish_results['total_size_bytes']:,} 字节")
        logger.info(f"   平均大小: {publish_results['avg_size_bytes']:.0f} 字节/条")
        logger.info(f"   成功率: {success_rate:.1%}")
        
        # 计算预估优化效果
        estimated_old_size = publish_results["published_count"] * 1012  # 假设旧格式平均1012字节
        size_reduction = estimated_old_size - publish_results["total_size_bytes"]
        reduction_rate = size_reduction / estimated_old_size if estimated_old_size > 0 else 0
        
        logger.info(f"🎯 优化效果:")
        logger.info(f"   预估旧格式大小: {estimated_old_size:,} 字节")
        logger.info(f"   实际新格式大小: {publish_results['total_size_bytes']:,} 字节")
        logger.info(f"   节省空间: {size_reduction:,} 字节 ({reduction_rate:.1%})")
        
        publish_results["success_rate"] = success_rate
        publish_results["completed_at"] = datetime.now().isoformat()
        publish_results["format_version"] = "v2"  # 标记使用v2格式
        publish_results["size_reduction_rate"] = reduction_rate
        
        return publish_results

    def _create_v2_message(self, enhanced_news: Dict[str, Any], sequence: int, 
                        batch_id: str, source_type: str) -> Dict[str, Any]:
        """创建v2精简格式消息"""
        
        # 提取核心字段（确保字段存在）
        title = enhanced_news.get("title", enhanced_news.get("标题", ""))
        content = enhanced_news.get("content", enhanced_news.get("内容", ""))
        publish_date = enhanced_news.get("publish_date", enhanced_news.get("发布日期", ""))
        publish_time = enhanced_news.get("publish_time", enhanced_news.get("发布时间", ""))
        news_id = enhanced_news.get("news_id", "")
        source = enhanced_news.get("source", "akshare_cls")
        
        # 基于内容生成唯一ID（如果news_id不存在）
        content_hash = ""
        if content:
            content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        
        # 确定消息ID
        final_news_id = news_id or content_hash or f"n{int(datetime.now().timestamp()*1000)%1000000:06d}"
        
        # 来源缩写映射
        source_abbr = {
            "akshare_cls": "cls",
            "mock": "mock",
            "test": "test"
        }.get(source, source[:4])
        
        # 📦 v2精简消息结构
        stream_message = {
            # === 核心业务数据 ===
            "t": title[:200] if len(title) > 200 else title,  # 标题
            "c": content,                                     # 完整内容（关键！）
            "s": source_abbr,                                 # 来源缩写
            "d": publish_date[:10] if publish_date else "",   # 日期（YYYY-MM-DD）
            
            # === 唯一标识 ===
            "id": final_news_id,
            
            # === 必要处理metadata ===
            "_b": batch_id,                   # 批次ID
            "_s": sequence + 1,               # 序列号
            
            # === 版本控制 ===
            "_t": "news",                     # 消息类型
            "_v": 2                           # 版本号
        }
        
        # 可选字段：发布时间
        if publish_time:
            stream_message["tm"] = publish_time[-8:] if len(publish_time) > 8 else publish_time
        
        # 可选字段：如果源类型重要，可以添加
        if source_type not in ["real", "mock"]:
            stream_message["_st"] = source_type[:3]
        
        return stream_message

    def _enhance_news_data(self, news_data: Dict[str, Any], batch_result: Dict[str, Any], 
                        sequence: int) -> Dict[str, Any]:
        """增强新闻数据 - 修复版：添加publish_time处理"""
        
        # 这里应该调用原有的增强逻辑
        enhanced = news_data.copy()
        
        # 确保必要字段存在
        if "news_id" not in enhanced or not enhanced["news_id"]:
            # 生成基于内容的ID
            content = enhanced.get("content", enhanced.get("内容", ""))
            if content:
                import hashlib
                enhanced["news_id"] = hashlib.md5(content.encode()).hexdigest()
            else:
                import time
                enhanced["news_id"] = f"news_{int(time.time()*1000)}_{sequence}"
        
        # 确保有标题
        if "title" not in enhanced or not enhanced["title"]:
            title = enhanced.get("标题", "")
            if title:
                enhanced["title"] = title
            else:
                # 从内容提取标题
                content = enhanced.get("content", enhanced.get("内容", ""))
                if content:
                    import re
                    sentences = re.split(r'[。！？]', content)
                    if sentences and len(sentences[0]) > 5:
                        enhanced["title"] = sentences[0] + "..."
                    else:
                        enhanced["title"] = content[:30] + "..."
                else:
                    enhanced["title"] = "新闻快讯"
        
        # 确保有来源
        if "source" not in enhanced or not enhanced["source"]:
            enhanced["source"] = "akshare_cls"
        
        # 确保有发布日期
        if "publish_date" not in enhanced or not enhanced["publish_date"]:
            publish_date = enhanced.get("发布日期", "")
            if publish_date:
                enhanced["publish_date"] = publish_date
            else:
                from datetime import datetime
                enhanced["publish_date"] = datetime.now().strftime("%Y-%m-%d")
        
        # 🔧 关键修复：确保有发布时间
        if "publish_time" not in enhanced or not enhanced["publish_time"]:
            publish_time = enhanced.get("发布时间", "")
            if publish_time:
                # 标准化时间格式
                if isinstance(publish_time, str):
                    import re
                    # 提取 HH:MM:SS 或 HH:MM 格式
                    time_match = re.search(r'(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?', publish_time)
                    if time_match:
                        h, m, s = time_match.groups()
                        s = s if s else "00"
                        enhanced["publish_time"] = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
                    else:
                        enhanced["publish_time"] = "00:00:00"
                else:
                    enhanced["publish_time"] = "00:00:00"
            else:
                # 如果没有时间，使用默认值
                enhanced["publish_time"] = "00:00:00"
        
        # 确保有内容字段（如果从"内容"字段来）
        if "content" not in enhanced or not enhanced["content"]:
            content = enhanced.get("内容", "")
            if content:
                enhanced["content"] = content
            else:
                enhanced["content"] = ""
        
        # 调试输出
        logger.info(f"🔍 增强数据结果:")
        logger.info(f"   标题: {enhanced.get('title', '')[:30]}...")
        logger.info(f"   日期: {enhanced.get('publish_date', '无')}")
        logger.info(f"   时间: {enhanced.get('publish_time', '无')}")
        
        return enhanced
    
    async def _update_stats(self, batch_result: Dict[str, Any], 
                           publish_result: Dict[str, Any], 
                           start_time: datetime):
        """更新统计信息"""
        self.stats["total_batches"] += 1
        self.stats["total_news"] += len(batch_result["news_list"])
        self.stats["published_count"] += publish_result["published_count"]
        self.stats["error_count"] += publish_result["failed_count"]
        self.stats["last_run_at"] = datetime.now().isoformat()
        
        # 记录批次详情
        batch_detail = {
            "batch_id": batch_result["batch_id"],
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - start_time).total_seconds(),
            "news_count": len(batch_result["news_list"]),
            "published_count": publish_result["published_count"],
            "failed_count": publish_result["failed_count"],
            "success_rate": publish_result["success_rate"],
            "news_service": batch_result.get("news_service"),
            "source_type": batch_result.get("source_type", "unknown"),
            "crawl_mode": batch_result.get("crawl_mode", "auto"),
            "real_retry_count": batch_result.get("real_retry_count", 0)
        }
        
        if batch_result.get("fallback"):
            batch_detail["fallback"] = True
            batch_detail["fallback_reason"] = batch_result.get("fallback_reason")
        
        self.stats["batches"].append(batch_detail)
        
        # 保持批次记录数量
        max_batches = self.config.get("max_batch_records", 100)
        if len(self.stats["batches"]) > max_batches:
            self.stats["batches"] = self.stats["batches"][-max_batches:]
    
    async def stop_scheduling(self):
        """停止调度"""
        if not self.running:
            return
        
        logger.info("🛑 停止改进版新闻Stream调度器")
        
        self.running = False
        
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        
        # 输出详细统计
        logger.info(f"📊 调度器统计:")
        logger.info(f"   总批次: {self.stats['total_batches']}")
        logger.info(f"   总新闻: {self.stats['total_news']}")
        logger.info(f"   发布成功: {self.stats['published_count']}")
        logger.info(f"   发布错误: {self.stats['error_count']}")
        logger.info(f"   新闻来源统计:")
        logger.info(f"     真实新闻: {self.stats['news_sources']['real']}")
        logger.info(f"     未知来源: {self.stats['news_sources']['unknown']}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取调度器统计"""
        if self.stats["started_at"]:
            started_dt = datetime.fromisoformat(self.stats["started_at"].replace('Z', '+00:00'))
            running_seconds = (datetime.now() - started_dt).total_seconds()
        else:
            running_seconds = 0
        
        # 计算成功率
        total_published = self.stats["published_count"]
        total_news = self.stats["total_news"]
        success_rate = total_published / max(total_news, 1)
        
        stats_summary = {
            **self.stats,
            "running": self.running,
            "running_seconds": running_seconds,
            "success_rate": success_rate,
            "schedule_config": self.schedule_config,
            "news_service": self.news_service.__class__.__name__,
            "recent_batches": self.stats["batches"][-5:] if self.stats["batches"] else [],
            "source_distribution": {
                "real_percentage": self.stats["news_sources"]["real"] / max(total_news, 1),
                "unknown_percentage": self.stats["news_sources"]["unknown"] / max(total_news, 1)
            }
        }
        
        return stats_summary
    
    async def run_single_batch(self, 
                              batch_size: Optional[int] = None, 
                              news_type: Optional[str] = None,
                              mode: Optional[str] = None,
                              force_real: bool = False) -> Dict[str, Any]:
        """
        运行单一批次（手动触发）
        
        Args:
            batch_size: 批次大小
            news_type: 新闻类型
            mode: 抓取模式 (auto/real)
            force_real: 是否强制使用真实数据（即使失败也不降级）
        """
        if batch_size is None:
            batch_size = self.schedule_config["batch_size"]
        
        if news_type is None:
            news_type = self.schedule_config["news_type"]
        
        if mode is None:
            mode = self.schedule_config["crawl_mode"]
        
        batch_id = f"manual_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"🔧 手动运行批次: {batch_id} ({batch_size}条新闻, 模式: {mode})")
        
        try:
            result = None
            source_type = "unknown"
            
            if mode == "real" or force_real:
                # 强制真实模式
                logger.info("🟢 强制使用真实新闻模式...")
                result = await self.news_service.crawl_real_news(limit=batch_size)
                source_type = "real"
                
            elif mode == "mock":
                logger.warning("手动mock模式已禁用，自动切换为real")
                result = await self.news_service.crawl_real_news(limit=batch_size)
                source_type = "real"
                
            else:  # auto
                # 自动模式
                logger.info("🤖 使用智能模式...")
                result = await self.news_service.crawl_news_auto(count=batch_size, prefer_real=True)
                source_type = result.get("mode", "unknown")
            
            if result and result.get("status") == "success":
                # 提取新闻列表
                news_list = []
                if "news_list" in result.get("response", {}):
                    news_list = result["response"]["news_list"]
                elif "batch_info" in result.get("response", {}) and "news_list" in result["response"]["batch_info"]:
                    news_list = result["response"]["batch_info"]["news_list"]
                
                batch_result = {
                    "batch_id": batch_id,
                    "news_service": self.news_service.__class__.__name__,
                    "batch_size": len(news_list),
                    "news_list": news_list,
                    "fetch_result": result,
                    "fetch_time": datetime.now().isoformat(),
                    "source_type": source_type,
                    "crawl_mode": mode,
                    "manual_run": True
                }
                
                # 发布到Stream
                publish_result = await self._publish_to_stream(batch_result)
                
                # 更新统计
                await self._update_stats(batch_result, publish_result, datetime.now())
                
                response = {
                    "batch_id": batch_id,
                    "success": True,
                    "batch_size": batch_size,
                    "news_type": news_type,
                    "mode": mode,
                    "source_type": source_type,
                    "actual_news_count": len(news_list),
                    "batch_result": batch_result,
                    "publish_result": publish_result,
                    "timestamp": datetime.now().isoformat(),
                    "manual_run": True
                }
                
                logger.info(f"✅ 手动批次完成: {publish_result['published_count']}/{len(news_list)} 成功 ({source_type})")
                
            else:
                error_msg = result.get("error", "未知错误") if result else "无返回结果"
                response = {
                    "batch_id": batch_id,
                    "success": False,
                    "error": error_msg,
                    "mode": mode,
                    "timestamp": datetime.now().isoformat(),
                    "manual_run": True
                }
                logger.error(f"❌ 手动批次失败: {error_msg}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ 手动批次执行异常: {e}")
            logger.exception("Unhandled exception")
            return {
                "batch_id": batch_id,
                "success": False,
                "error": str(e),
                "mode": mode,
                "timestamp": datetime.now().isoformat(),
                "manual_run": True
            }
    
    async def switch_mode(self, mode: str, prefer_real: bool = None) -> Dict[str, Any]:
        """
        切换抓取模式
        
        Args:
            mode: 抓取模式 (auto/real)
            prefer_real: 是否优先真实数据（仅auto模式有效）
        """
        valid_modes = ["auto", "real"]
        
        if mode not in valid_modes:
            return {
                "success": False,
                "error": f"无效模式: {mode}, 有效值: {valid_modes}"
            }
        
        old_mode = self.schedule_config["crawl_mode"]
        self.schedule_config["crawl_mode"] = mode
        
        if prefer_real is not None:
            self.schedule_config["prefer_real"] = prefer_real
        
        logger.info(f"🔄 切换抓取模式: {old_mode} → {mode}")
        if mode == "auto" and prefer_real is not None:
            logger.info(f"   优先真实数据: {prefer_real}")
        
        return {
            "success": True,
            "old_mode": old_mode,
            "new_mode": mode,
            "prefer_real": self.schedule_config["prefer_real"],
            "message": f"抓取模式已切换为 {mode}",
            "timestamp": datetime.now().isoformat()
        }

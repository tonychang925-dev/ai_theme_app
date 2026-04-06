"""
新闻Stream业务处理器 - 专门负责业务逻辑处理
职责：监听新闻存储完成事件 → 触发业务处理（如AI分析）→ 处理结果
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# 🔥 导入ModelService
try:
    from model_service import get_model_service
    HAS_MODEL_SERVICE = True
    logger.info("✅ 成功导入ModelService")
except ImportError as e:
    HAS_MODEL_SERVICE = False
    logger.warning(f"⚠️ 无法导入ModelService: {e}")
    logger.info("💡 未检测到ModelService，news_stream_processor将无法启动")


class NewsStreamProcessor:
    """新闻Stream业务处理器"""
    
    def __init__(self, event_bus, config=None, business_services=None):
        """
        Args:
            event_bus: 事件总线（监听存储完成事件）
            config: 配置
            business_services: 业务服务字典（如AI分析服务）
        """
        self.event_bus = event_bus
        self.config = config or {}
        self.database_gateway = self.config.get("database_gateway")
        
        # 🔥 关键修改：初始化业务服务
        if business_services:
            # 使用传入的业务服务
            self.business_services = business_services
        elif HAS_MODEL_SERVICE:
            # 初始化真实的ModelService
            try:
                model_service = get_model_service()
                self.business_services = {
                    "model_service": model_service,
                    "ai_service": model_service  # 保持向后兼容
                }
                logger.info("🧠 使用真实的ModelService进行AI分析")
                
                asyncio.create_task(self._check_model_service_status())
            except Exception as e:
                logger.error(f"❌ 初始化ModelService失败: {e}")
                raise RuntimeError("news_stream_processor 初始化失败：ModelService 不可用") from e
        else:
            raise RuntimeError("news_stream_processor 初始化失败：无法导入 ModelService")
        
        # 处理器配置
        self.processor_config = {
            "processor_group": self.config.get("processor_group", "news_business_processors"),
            "processor_name": f"business_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "event_types": ["news.stored", "news.updated"],  # 监听的事件类型
            "enable_ai_analysis": self.config.get("enable_ai_analysis", True),  # 🔥 默认启用
            "enable_sentiment_analysis": self.config.get("enable_sentiment_analysis", False),
            "enable_topic_extraction": self.config.get("enable_topic_extraction", False),
            "batch_processing": self.config.get("batch_processing", True),
            "batch_size": self.config.get("batch_size", 5)
        }
        
        # 运行状态
        self.running = False
        self.processor_task = None
        
        # 业务处理统计
        self.business_stats = {
            "started_at": None,
            "last_processing_at": None,
            "total_events": 0,
            "processed_events": 0,
            "failed_events": 0,
            "ai_analysis_count": 0,
            "ai_real_analysis_count": 0,
            "sentiment_analysis_count": 0,
            "topic_extraction_count": 0,
            "business_results": []
        }
        
        logger.info(f"🧠 新闻Stream业务处理器初始化")
        logger.info(f"   处理器组: {self.processor_config['processor_group']}")
        logger.info(f"   监听事件: {', '.join(self.processor_config['event_types'])}")
        logger.info(f"   使用服务: {', '.join(self.business_services.keys())}")
        if self.database_gateway:
            logger.info(f"   数据库网关: {self.database_gateway.__class__.__name__}")
    
    async def _check_model_service_status(self):
        """检查ModelService状态"""
        if "model_service" in self.business_services:
            try:
                status = await self.business_services["model_service"].get_service_status()
                logger.info(f"📊 ModelService状态检查: {status.get('status')}")
                
                components = status.get('components', {})
                real_available = components.get('real_extractor', {}).get('available', False)
                
                logger.info(f"   AI提取器: {'✅ 可用' if real_available else '❌ 不可用'}")
                
            except Exception as e:
                logger.error(f"❌ ModelService状态检查失败: {e}")
    
    async def start_business_processing(self):
        """启动业务处理服务"""
        if self.running:
            logger.warning("业务处理服务已经在运行")
            return
        
        self.running = True
        self.business_stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动新闻Stream业务处理服务")
        
        # 启动业务处理任务
        self.processor_task = asyncio.create_task(self._business_processing_loop())
        
        return True
    
    async def _business_processing_loop(self):
        """业务处理主循环"""
        logger.info("进入业务处理循环...")
        
        while self.running:
            try:
                # 监听事件（这里需要根据event_bus的实际接口调整）
                events = await self._listen_for_events()
                
                if events:
                    logger.info(f"📨 收到 {len(events)} 个业务事件")
                    
                    # 批量处理事件
                    processing_results = await self._process_events_batch(events)
                    
                    # 更新统计
                    await self._update_business_stats(processing_results)
                    
                else:
                    # 没有事件时
                    if self.business_stats["total_events"] % 10 == 0:
                        logger.info(f"⏳ 等待业务事件... (已处理: {self.business_stats['processed_events']})")
                    await asyncio.sleep(5)
                    
            except asyncio.CancelledError:
                logger.info("业务处理服务被取消")
                break
            except Exception as e:
                logger.error(f"业务处理循环异常: {e}")
                await asyncio.sleep(5)
    
    async def _listen_for_events(self) -> List[Dict[str, Any]]:
        """监听事件"""
        try:
            # 根据event_bus的实际接口调整
            if hasattr(self.event_bus, 'subscribe'):
                await asyncio.sleep(2)
                return []
            elif hasattr(self.event_bus, 'consume_events'):
                return await self.event_bus.consume_events(
                    event_types=self.processor_config["event_types"],
                    count=self.processor_config["batch_size"]
                )
            else:
                await asyncio.sleep(2)
                return []
                
        except Exception as e:
            logger.error(f"监听事件失败: {e}")
            return []
    
    async def _process_events_batch(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理事件批次"""
        results = []
        
        for event in events:
            result = await self._process_single_event(event)
            results.append(result)
        
        return results
    
    async def process_stream_message(self, message_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理已入库 news_raw 的后续业务消息
        """
        try:
            stream_event = self._build_stored_news_event(message_id, message_data)
            result = await self._process_single_event(stream_event, source_type="stored_news_message")
            structured = result.get("business_results", {}).get("results", {}).get("structured_event", {})
            persistence = result.get("business_results", {}).get("results", {}).get("news_event_persistence", {})

            return {
                "success": bool(result["processing_success"] and persistence.get("news_event_id")),
                "message_id": message_id,
                "news_id": result.get("news_id"),
                "event_id": result["event_id"],
                "news_event_id": persistence.get("news_event_id"),
                "processing_time": result["processing_time"],
                "error": result.get("error") or (None if persistence.get("news_event_id") else "news_event_not_created"),
                "source_type": result.get("source_type"),
                "structured_event": structured,
                "structured_stream_published": persistence.get("structured_stream_published", False),
            }
            
        except Exception as e:
            logger.error(f"处理Stream消息 {message_id} 失败: {e}")
            return {
                "success": False,
                "message_id": message_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _build_stored_news_event(self, message_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """将已入库 news_raw 消息适配为统一处理事件"""
        news_data = self._extract_news_from_stream_message(message_id, message_data)
        if not news_data:
            payload = message_data.get("payload") if isinstance(message_data, dict) else None
            if isinstance(payload, dict) and "news_data" in payload:
                news_data = payload.get("news_data")

        if not news_data:
            raise ValueError(f"无法从消息 {message_id} 提取已入库 news_raw 数据")

        news_data = self._ensure_news_data_fields(news_data, message_id)
        return {
            "id": message_id,
            "event_type": "news.stored",
            "data": {
                "news_data": news_data,
                "stored_at": datetime.now().isoformat(),
                "source": "stored_news_event",
                "message_id": message_id,
                "raw_data": message_data,
            },
        }

    def _extract_news_from_stream_message(self, message_id: str, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从Stream消息中提取新闻数据"""
        try:
            # 检查是否有payload字段
            if 'payload' not in message_data:
                logger.debug(f"消息 {message_id} 没有payload字段")
                return None
            
            payload = message_data['payload']
            
            # 如果payload是字符串，尝试解析JSON
            if isinstance(payload, str):
                try:
                    import json
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning(f"消息 {message_id} 的payload不是有效JSON")
                    return None
            
            # payload应该是字典
            if not isinstance(payload, dict):
                logger.warning(f"消息 {message_id} 的payload不是字典: {type(payload)}")
                return None
            
            # 🔍 关键：检查是否是双层嵌套结构
            if 'payload' in payload and isinstance(payload['payload'], dict):
                inner_payload = payload['payload']
                
                # 检查是否是v2格式
                if inner_payload.get('_t') == 'news' and inner_payload.get('_v') == 2:
                    return self._extract_v2_format_news(inner_payload)
                elif 'news_data' in inner_payload:
                    news_data = inner_payload.get('news_data', {})
                    if isinstance(news_data, dict):
                        return news_data
            
            # 🔍 检查直接包含新闻数据的情况
            if 'news_data' in payload:
                news_data = payload.get('news_data', {})
                if isinstance(news_data, dict):
                    return news_data
            
            # 🔍 检查是否直接就是新闻数据
            if any(key in payload for key in ['title', 'content', 'news_id']):
                return payload
            
            logger.debug(f"消息 {message_id} 无法识别格式")
            return None
            
        except Exception as e:
            logger.error(f"提取新闻数据失败 {message_id}: {e}")
            return None
    
    
    def _ensure_news_data_fields(self, news_data: Dict[str, Any], message_id: str) -> Dict[str, Any]:
        """确保新闻数据有必要的字段"""
        result = news_data.copy()
        
        # 必须有news_id
        if 'news_id' not in result:
            result['news_id'] = f"stream_{message_id.replace('-', '_')}"
        
        # 必须有title
        if 'title' not in result:
            result['title'] = "新闻快讯"
        
        # 必须有content
        if 'content' not in result:
            result['content'] = ""
        
        # 必须有source
        if 'source' not in result:
            result['source'] = 'redis_stream'
        
        # 必须有publish_date
        if 'publish_date' not in result:
            result['publish_date'] = datetime.now().isoformat()
        
        return result
    
    def _extract_v2_format_news(self, v2_data: Dict[str, Any]) -> Dict[str, Any]:
            """提取v2格式新闻数据"""
            from datetime import datetime
            import hashlib
            import time
            
            result = {}
            
            # 标题 (t = title)
            result['title'] = v2_data.get('t', '新闻快讯')
            
            # 内容 (c = content)
            result['content'] = v2_data.get('c', '')
            
            # 来源 (s = source)
            source_abbr = v2_data.get('s', 'cls')
            result['source'] = 'akshare_cls' if source_abbr == 'cls' else source_abbr
            
            # 日期 (d = date)
            result['publish_date'] = v2_data.get('d', datetime.now().strftime('%Y-%m-%d'))
            
            # 时间 (tm = time)
            result['publish_time'] = v2_data.get('tm', '00:00:00')
            
            # ID (id = news_id)
            if 'id' in v2_data:
                result['news_id'] = v2_data['id']
            else:
                # 如果没有ID，根据内容生成
                content_hash = hashlib.md5(result['content'].encode()).hexdigest()[:8] if result['content'] else ""
                result['news_id'] = f"v2_{int(time.time()*1000)}_{content_hash}"
            
            # 批次ID (_b = batch_id)
            if '_b' in v2_data:
                result['batch_id'] = v2_data['_b']
            
            # 序列号 (_s = sequence)
            if '_s' in v2_data:
                result['sequence'] = v2_data['_s']
            
            logger.debug(f"提取v2格式数据成功: {result.get('title')[:30]}...")
            return result
    
    async def _process_single_event(self, event: Dict[str, Any], source_type: str = "event_bus") -> Dict[str, Any]:
        """处理单个事件 - 支持多种事件来源"""
        event_id = event.get('id', f"{source_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        event_type = event.get('event_type', 'news.stored')
        event_data = event.get('data', {})
        
        result = {
            "event_id": event_id,
            "event_type": event_type,
            "processing_success": False,
            "business_results": {},
            "error": None,
            "processing_time": datetime.now().isoformat(),
            "source_type": source_type
        }
        
        try:
            # 提取新闻数据
            news_data = event_data.get('news_data', {})
            
            # 🔥 如果没有news_data字段，检查event_data本身是否就是新闻数据
            if not news_data and any(key in event_data for key in ['title', 'content', 'news_id']):
                news_data = event_data
            
            if not news_data or ('title' not in news_data and 'content' not in news_data):
                result["error"] = "事件中没有有效的新闻数据"
                return result
            
            news_id = news_data.get('news_id') or f"{source_type}_{event_id}"
            result["news_id"] = news_id
            
            logger.debug(f"🧠 处理{source_type}事件: {event_type} - {news_id}")
            
            # 根据事件类型处理
            business_results = {}
            
            if event_type == "news.stored" or event_type == "news.crawled":
                # 新闻存储完成或抓取完成事件
                business_results = await self._process_news_stored_event(news_data)
            elif event_type == "news.updated":
                # 新闻更新事件
                business_results = await self._process_news_updated_event(news_data)
            
            result["business_results"] = business_results
            result["processing_success"] = True
            
            logger.debug(f"✅ {source_type}事件处理完成: {news_id}")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"处理{source_type}事件 {event_id} 失败: {e}")
        
        return result
    
    async def _process_news_stored_event(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理新闻存储完成事件：news_raw -> structured news_event -> structured stream"""
        business_results = {
            "event_type": "news.stored",
            "processing_steps": [],
            "results": {}
        }
        
        # 步骤1: AI分析（如果启用）
        if self.processor_config["enable_ai_analysis"]:
            try:
                ai_service = None
                service_name = ""
                
                # 🔥 优先使用model_service
                if "model_service" in self.business_services:
                    ai_service = self.business_services["model_service"]
                    service_name = "model_service"
                elif "ai_service" in self.business_services:
                    ai_service = self.business_services["ai_service"]
                    service_name = "ai_service"
                
                if ai_service:
                    news_id = news_data.get('news_id', 'unknown')
                    
                    # 只允许真实 ModelService 路径
                    logger.info(f"🧠 开始{service_name}分析: {news_id}")
                    
                    if hasattr(ai_service, 'extract_event'):
                        ai_result = await ai_service.extract_event(news_data)
                        
                        if ai_result and ai_result.get("status") == "success":
                            structured_event = self._build_structured_news_event(news_data, ai_result.get("response", {}))
                            persistence = await self._persist_and_publish_structured_event(structured_event)

                            business_results["results"]["structured_event"] = structured_event
                            business_results["results"]["news_event_persistence"] = persistence
                            business_results["results"]["ai_analysis"] = {
                                "ai_service": "real",
                                "ai_service_response": ai_result,
                            }
                            business_results["processing_steps"].append("ai_analysis_real")
                            business_results["processing_steps"].append("news_event_persist")
                            if persistence.get("structured_stream_published"):
                                business_results["processing_steps"].append("structured_event_publish")
                            self.business_stats["ai_analysis_count"] += 1
                            self.business_stats["ai_real_analysis_count"] += 1
                            
                            logger.info(f"✅ 真实AI分析成功: {news_id}")
                        else:
                            error_msg = ai_result.get("error", "未知错误") if ai_result else "返回空结果"
                            logger.warning(f"⚠️  真实AI分析失败: {error_msg}")
                    else:
                        logger.warning(f"⚠️  AI服务不支持 extract_event: {service_name}")
                        
            except Exception as e:
                logger.error(f"❌ AI分析异常: {e}")
        
        # 步骤2: 情感分析（如果启用）
        if self.processor_config["enable_sentiment_analysis"] and "sentiment_service" in self.business_services:
            try:
                sentiment_result = await self.business_services["sentiment_service"].analyze_sentiment(news_data)
                business_results["results"]["sentiment_analysis"] = sentiment_result
                business_results["processing_steps"].append("sentiment_analysis")
                self.business_stats["sentiment_analysis_count"] += 1
            except Exception as e:
                logger.warning(f"情感分析失败: {e}")
        
        # 步骤3: 主题提取（如果启用）
        if self.processor_config["enable_topic_extraction"] and "topic_service" in self.business_services:
            try:
                topic_result = await self.business_services["topic_service"].extract_topics(news_data)
                business_results["results"]["topic_extraction"] = topic_result
                business_results["processing_steps"].append("topic_extraction")
                self.business_stats["topic_extraction_count"] += 1
            except Exception as e:
                logger.warning(f"主题提取失败: {e}")
        
        return business_results

    def _build_structured_news_event(self, news_data: Dict[str, Any], structured_result: Dict[str, Any]) -> Dict[str, Any]:
        """将 ModelService 输出规范化为 news_event 落库结构"""
        news_row_id = self._resolve_news_row_id(news_data)
        raw_event_json = structured_result.get("raw_event_json") or structured_result.copy()

        return {
            "news_id": news_row_id,
            "event_type": structured_result.get("event_type"),
            "impact_industries": structured_result.get("impact_industries") or [],
            "direction": structured_result.get("direction"),
            "confidence": structured_result.get("confidence"),
            "summary": structured_result.get("summary"),
            "theme_directive": {
                "structuring_version": structured_result.get("structuring_version"),
                "llm_request_id": structured_result.get("llm_request_id"),
                "reason": "compat_placeholder",
            },
            "theme_directive_processed": False,
            "severity_score": structured_result.get("severity_score"),
            "source_weight": structured_result.get("source_weight"),
            "event_time": structured_result.get("event_time") or structured_result.get("timestamp"),
            "entities": structured_result.get("entities") or [],
            "causal_claim": structured_result.get("causal_claim") or [],
            "evidence_set": structured_result.get("evidence_set") or {},
            "raw_event_json": raw_event_json,
            "structuring_version": structured_result.get("structuring_version"),
            "llm_request_id": structured_result.get("llm_request_id"),
        }

    def _resolve_news_row_id(self, news_data: Dict[str, Any]) -> Any:
        """优先使用已解析的 news_raw.id；否则回退到现有 news_id 字段"""
        return (
            news_data.get("news_row_id")
            or news_data.get("raw_news_id")
            or news_data.get("stored_news_id")
            or news_data.get("id")
            or news_data.get("news_id")
        )

    async def _persist_and_publish_structured_event(self, structured_event: Dict[str, Any]) -> Dict[str, Any]:
        """先落库 news_event，再发布 structured 事件"""
        persistence = {
            "news_event_id": None,
            "structured_stream_published": False,
            "stream_message_id": None,
        }

        if not self.database_gateway:
            logger.warning("⚠️ 缺少 database_gateway，跳过 news_event 落库")
            return persistence

        news_event_id = await self.database_gateway.create_news_event(structured_event)
        persistence["news_event_id"] = news_event_id

        structured_message = {
            "event_id": news_event_id,
            "news_id": structured_event.get("news_id"),
            "event_type": structured_event.get("event_type"),
            "summary": structured_event.get("summary"),
            "source": "news_stream_processor",
            "structuring_version": structured_event.get("structuring_version"),
            "llm_request_id": structured_event.get("llm_request_id"),
        }

        message_id = await self._publish_structured_event(structured_message)
        if message_id:
            persistence["structured_stream_published"] = True
            persistence["stream_message_id"] = message_id

        return persistence

    async def _publish_structured_event(self, structured_message: Dict[str, Any]) -> Optional[str]:
        """发布统一的结构化事件消息"""
        if not self.event_bus:
            return None

        if hasattr(self.event_bus, "publish_structured_event"):
            return await self.event_bus.publish_structured_event(structured_message)
        if hasattr(self.event_bus, "publish_to_stream"):
            return await self.event_bus.publish_to_stream("stream:events:structured", structured_message)
        return None
    
    async def _process_news_updated_event(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理新闻更新事件"""
        # 这里可以添加更新相关的业务逻辑
        return {
            "event_type": "news.updated",
            "processing_steps": ["update_validation"],
            "results": {
                "update_validated": True,
                "validation_time": datetime.now().isoformat()
            }
        }
    
    async def _update_business_stats(self, processing_results: List[Dict[str, Any]]):
        """更新业务统计"""
        for result in processing_results:
            self.business_stats["total_events"] += 1
            
            if result["processing_success"]:
                self.business_stats["processed_events"] += 1
                
                # 记录业务结果
                if len(self.business_stats["business_results"]) < 100:  # 保留最近100条
                    business_results = result.get("business_results", {})
                    ai_analysis = business_results.get("results", {}).get("ai_analysis", {})
                    
                    self.business_stats["business_results"].append({
                        "event_id": result["event_id"],
                        "news_id": result.get("news_id"),
                        "event_type": result["event_type"],
                        "processing_time": result["processing_time"],
                        "has_ai_analysis": bool(ai_analysis),
                        "ai_service_type": ai_analysis.get("ai_service", "none")
                    })
            else:
                self.business_stats["failed_events"] += 1
        
        self.business_stats["last_processing_at"] = datetime.now().isoformat()
        
        # 清理过期的业务结果记录
        if len(self.business_stats["business_results"]) > 100:
            self.business_stats["business_results"] = self.business_stats["business_results"][-100:]
    
    async def stop_business_processing(self):
        """停止业务处理服务"""
        if not self.running:
            return
        
        logger.info("🛑 停止新闻Stream业务处理服务")
        
        self.running = False
        
        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
        
        # 打印业务统计
        logger.info(f"📊 业务处理统计:")
        logger.info(f"   运行时间: {self.business_stats['started_at']} - {datetime.now().isoformat()}")
        logger.info(f"   总事件数: {self.business_stats['total_events']}")
        logger.info(f"   处理成功: {self.business_stats['processed_events']}")
        logger.info(f"   处理失败: {self.business_stats['failed_events']}")
        logger.info(f"   AI分析数: {self.business_stats['ai_analysis_count']}")
        logger.info(f"     真实AI分析: {self.business_stats['ai_real_analysis_count']}")
        logger.info(f"   情感分析数: {self.business_stats['sentiment_analysis_count']}")
        logger.info(f"   主题提取数: {self.business_stats['topic_extraction_count']}")
    
    async def get_business_stats(self) -> Dict[str, Any]:
        """获取业务统计"""
        if self.business_stats["started_at"]:
            started_dt = datetime.fromisoformat(self.business_stats["started_at"].replace('Z', '+00:00'))
            running_seconds = (datetime.now() - started_dt).total_seconds()
        else:
            running_seconds = 0
        
        total_events = max(self.business_stats["total_events"], 1)
        
        stats_summary = {
            "running": self.running,
            "running_seconds": running_seconds,
            "started_at": self.business_stats["started_at"],
            "last_processing_at": self.business_stats["last_processing_at"],
            "total_events": self.business_stats["total_events"],
            "processed_events": self.business_stats["processed_events"],
            "failed_events": self.business_stats["failed_events"],
            "ai_analysis_count": self.business_stats["ai_analysis_count"],
            "ai_real_analysis_count": self.business_stats["ai_real_analysis_count"],
            "sentiment_analysis_count": self.business_stats["sentiment_analysis_count"],
            "topic_extraction_count": self.business_stats["topic_extraction_count"],
            "processing_success_rate": self.business_stats["processed_events"] / total_events,
            "ai_real_analysis_rate": (
                self.business_stats["ai_real_analysis_count"] / 
                max(self.business_stats["ai_analysis_count"], 1)
            ),
            "processor_config": self.processor_config,
            "available_services": list(self.business_services.keys()),
            "recent_results": self.business_stats["business_results"][-10:] if self.business_stats["business_results"] else []
        }
        
        return stats_summary
    
    async def manual_business_test(self, test_news_data: Dict[str, Any]) -> Dict[str, Any]:
        """手动业务处理测试 - 同样调用_process_single_event"""
        news_id = test_news_data.get('news_id', f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        logger.info(f"🧪 手动业务处理测试: {news_id}")
        
        # 🔥 构建标准事件格式
        test_event = {
            'id': f"test_event_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'event_type': 'news.stored',
            'data': {
                'news_data': test_news_data,
                'stored_at': datetime.now().isoformat(),
                'source': 'manual_test'
            }
        }
        
        # 🔥 调用统一的处理逻辑
        result = await self._process_single_event(test_event, source_type="manual_test")
        
        # 包装测试结果
        test_result = {
            "test_type": "manual_business_test",
            "news_id": news_id,
            "processing_success": result["processing_success"],
            "business_results": result.get("business_results", {}),
            "error": result.get("error"),
            "timestamp": datetime.now().isoformat(),
            "event_id": result.get("event_id"),
            "source_type": result.get("source_type")
        }
        
        if result["processing_success"]:
            logger.info(f"✅ 手动业务处理测试成功: {news_id}")
        else:
            logger.warning(f"⚠️  手动业务处理测试失败: {result.get('error')}")
        
        return test_result
    
    def print_business_status(self):
        """打印业务处理状态"""
        print("\n🧠 新闻Stream业务处理器状态")
        print("=" * 60)
        print(f"运行状态: {'✅ 运行中' if self.running else '⏸️ 已停止'}")
        print(f"开始时间: {self.business_stats['started_at'] or '未开始'}")
        print(f"最后处理: {self.business_stats['last_processing_at'] or '无'}")
        print(f"总事件数: {self.business_stats['total_events']}")
        print(f"处理成功: {self.business_stats['processed_events']}")
        print(f"处理失败: {self.business_stats['failed_events']}")
        
        if self.business_stats['total_events'] > 0:
            success_rate = self.business_stats['processed_events'] / self.business_stats['total_events']
            print(f"处理成功率: {success_rate:.1%}")
        
        print(f"\nAI分析统计:")
        print(f"  总分析数: {self.business_stats['ai_analysis_count']}")
        print(f"  真实AI分析: {self.business_stats['ai_real_analysis_count']}")
        
        if self.business_stats['ai_analysis_count'] > 0:
            real_rate = self.business_stats['ai_real_analysis_count'] / self.business_stats['ai_analysis_count']
            print(f"  真实AI占比: {real_rate:.1%}")
        
        print(f"\n监听事件: {', '.join(self.processor_config['event_types'])}")
        print(f"可用服务: {', '.join(self.business_services.keys()) if self.business_services else '无'}")
        print("=" * 60)

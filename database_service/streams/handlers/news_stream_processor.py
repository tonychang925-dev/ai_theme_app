"""
新闻Stream业务处理器 - 专门负责业务逻辑处理
职责：监听新闻存储完成事件 → 触发业务处理（如AI分析）→ 处理结果
"""
import asyncio
import json
import logging
import os
import time
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

try:
    from database_service.streams.services.local_qwen_triage_service import LocalQwenNewsTriageService
    HAS_LOCAL_QWEN_TRIAGE = True
except ImportError:
    HAS_LOCAL_QWEN_TRIAGE = False


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
            "enable_local_triage": self.config.get("enable_local_triage", True),
            "triage_mode": self.config.get("triage_mode", "prompt"),
            "triage_block_on_skip": self.config.get("triage_block_on_skip", True),
            "triage_pass_threshold": self.config.get("triage_pass_threshold", 0.06),
            "triage_skip_threshold": self.config.get("triage_skip_threshold", -0.02),
            "local_qwen_model_path": self.config.get("local_qwen_model_path", ""),
            "enable_sentiment_analysis": self.config.get("enable_sentiment_analysis", False),
            "enable_topic_extraction": self.config.get("enable_topic_extraction", False),
            "batch_processing": self.config.get("batch_processing", True),
            "batch_size": self.config.get("batch_size", 5),
            "run_id_filter": self.config.get("run_id_filter"),
            "structuring_connect_timeout_s": float(self.config.get("structuring_connect_timeout_s", 10)),
            "structuring_read_timeout_s": float(self.config.get("structuring_read_timeout_s", 60)),
            "structuring_total_timeout_s": float(self.config.get("structuring_total_timeout_s", 90)),
            "structuring_max_retries": int(self.config.get("structuring_max_retries", 2)),
            "structuring_retry_delay_s": float(self.config.get("structuring_retry_delay_s", 1)),
            "structuring_circuit_breaker_threshold": int(self.config.get("structuring_circuit_breaker_threshold", 5)),
        }

        self.local_triage_service = None
        if self.processor_config["enable_local_triage"] and HAS_LOCAL_QWEN_TRIAGE:
            self.local_triage_service = LocalQwenNewsTriageService(
                {
                    "enable_local_triage": True,
                    "triage_mode": self.processor_config["triage_mode"],
                    "triage_pass_threshold": self.processor_config["triage_pass_threshold"],
                    "triage_skip_threshold": self.processor_config["triage_skip_threshold"],
                    "local_qwen_model_path": self.processor_config["local_qwen_model_path"],
                }
            )
            logger.info("🧪 本地Qwen预筛选已启用（失败自动降级规则模式）")
        
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
            "structuring_success_count": 0,
            "structuring_timeout_count": 0,
            "structuring_error_count": 0,
            "fallback_structured_count": 0,
            "processed_after_fallback_count": 0,
            "llm_retry_count": 0,
            "circuit_breaker_open_count": 0,
            "triage_pass_count": 0,
            "triage_review_count": 0,
            "triage_skip_count": 0,
            "triage_duplicate_count": 0,
            "triage_structuring_saved_count": 0,
            "low_value_triage_skip_count": 0,
            "duplicate_triage_skip_count": 0,
            "triage_false_positive_review_count": 0,
            "sentiment_analysis_count": 0,
            "topic_extraction_count": 0,
            "business_results": []
        }
        self._structuring_consecutive_timeouts = 0
        self._structuring_circuit_breaker_open = False
        self._structuring_circuit_breaker_open_at = None
        
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

                    # 确认处理成功的消息
                    await self._acknowledge_processed_events(events, processing_results)
                    
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
        """监听事件 - 从 events_normal Stream消费news.stored事件"""
        try:
            if hasattr(self.event_bus, 'consume_from_stream'):
                # 从独立业务事件流消费，避免与news_raw原始流形成回路
                messages = await self.event_bus.consume_from_stream(
                    stream="events_normal",
                    group=self.processor_config["processor_group"],
                    consumer=self.processor_config["processor_name"],
                    count=self.processor_config["batch_size"],
                    block_ms=5000  # 5秒阻塞等待
                )
                # 将消息转换为事件格式
                if messages:
                    logger.info(f"📥 收到 {len(messages)} 条原始消息")
                events = []
                message_ids_to_ack = []

                for msg in messages:
                    msg_id = msg.get('id')
                    msg_data = msg.get('data', {})

                    # 调试：查看原始消息结构
                    logger.debug(f"原始消息 ID: {msg_id}, 数据键名: {list(msg_data.keys())}")

                    # 处理payload字段：可能是JSON字符串
                    event_data = msg_data
                    if 'payload' in msg_data:
                        try:
                            # 解析payload JSON
                            payload_str = msg_data['payload']
                            if isinstance(payload_str, str):
                                event_data = json.loads(payload_str)
                                logger.debug(f"解析payload成功，event_data键名: {list(event_data.keys())}")
                            else:
                                # 如果不是字符串，直接使用
                                event_data = payload_str
                        except Exception as e:
                            logger.warning(f"解析payload失败: {e}")
                            # 仍然确认消息，避免pending堆积
                            message_ids_to_ack.append(msg_id)
                            continue
                    else:
                        logger.debug(f"消息无payload字段，直接使用msg_data")

                    # 检查事件类型是否符合监听类型
                    event_type = event_data.get('event_type')
                    logger.debug(f"检查事件类型: {event_type}, 监听类型: {self.processor_config['event_types']}")

                    if event_type in self.processor_config["event_types"]:
                        run_id_filter = self.processor_config.get("run_id_filter")
                        if run_id_filter and not self._event_matches_run_id(event_data, run_id_filter):
                            logger.debug(
                                "跳过非本轮 E2E 业务事件: message_id=%s expected_run_id=%s",
                                msg_id,
                                run_id_filter,
                            )
                            message_ids_to_ack.append(msg_id)
                            continue
                        events.append({
                            'id': msg_id,
                            'event_type': event_type,
                            'data': event_data
                        })
                        logger.info(f"✅ 识别到事件: {event_type}, 消息ID: {msg_id}")
                    else:
                        logger.debug(f"不是监听的事件类型: {event_type}")
                    # 记录所有消息ID用于确认
                    message_ids_to_ack.append(msg_id)

                # 确认所有消息（包括非事件消息）
                await self._acknowledge_messages(message_ids_to_ack)
                return events
            else:
                # 降级处理
                await asyncio.sleep(2)
                return []
        except Exception as e:
            logger.error(f"监听事件失败: {e}")
            return []
    
    async def _process_events_batch(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理事件批次 - 优化版：并行处理以提高AI分析效率"""
        if not events:
            return []

        # 记录批次信息
        logger.info(f"🧠 并行处理批次: {len(events)} 个事件")

        # 创建并行处理任务
        tasks = [self._process_single_event(event) for event in events]

        try:
            # 并行执行所有任务，允许异常返回
            results = await asyncio.gather(*tasks, return_exceptions=True)

            processed_results = []
            success_count = 0
            error_count = 0

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # 处理异常结果
                    error_count += 1
                    logger.error(f"处理事件 {i} 失败: {result}")

                    # 生成错误结果记录
                    event_id = events[i].get('id', f'unknown_{i}')
                    processed_results.append({
                        "event_id": event_id,
                        "event_type": events[i].get('event_type', 'unknown'),
                        "processing_success": False,
                        "business_results": {},
                        "error": str(result),
                        "processing_time": datetime.now().isoformat(),
                        "source_type": "parallel_batch"
                    })
                else:
                    # 正常结果
                    success_count += 1
                    processed_results.append(result)

            # 记录批次处理统计
            if success_count > 0:
                logger.info(f"✅ 批次处理完成: {success_count} 成功, {error_count} 失败")

            return processed_results

        except Exception as e:
            # 整体批次处理异常
            logger.error(f"批次处理异常: {e}")
            # 回退到顺序处理作为降级方案
            logger.warning("⚠️  回退到顺序处理")
            return await self._sequential_process_events_batch(events)

    async def _sequential_process_events_batch(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """顺序处理事件批次 - 降级方案"""
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
            structuring = result.get("business_results", {}).get("results", {}).get("structuring", {})

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
                "structuring": structuring,
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

            # 透传存储层产出的 news_raw 主键，供 news_event.news_id 使用
            if isinstance(news_data, dict) and event_data.get("stored_news_id") is not None and news_data.get("stored_news_id") is None:
                news_data["stored_news_id"] = event_data.get("stored_news_id")
            
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
        news_id = news_data.get('news_id', 'unknown')
        if self._is_stress_test_news(news_data):
            logger.warning("🚫 业务处理层拦截压测新闻: news_id=%s", news_id)
            return {
                "event_type": "news.stored",
                "processing_steps": ["stress_test_blocked"],
                "results": {"blocked": True, "reason": "stress_test_news_blocked"},
            }
        logger.info(f"🔄 开始处理新闻存储事件: {news_id}")

        business_results = {
            "event_type": "news.stored",
            "processing_steps": [],
            "results": {}
        }

        # 步骤0: 本地预筛选（可选）
        triage_decision = "PASS"
        if self.local_triage_service:
            triage_result = self.local_triage_service.evaluate(news_data)
            triage_decision = str(triage_result.get("decision") or "PASS").upper()
            business_results["results"]["local_triage"] = triage_result
            business_results["processing_steps"].append("local_triage")
            self._record_triage_stats(triage_result)

            should_structurize = triage_result.get("should_structurize")
            if should_structurize is None:
                should_structurize = triage_decision == "PASS"
            if triage_decision in {"REVIEW", "SKIP", "DUPLICATE"} or not bool(should_structurize):
                logger.info(
                    "⏭️ 重要性预筛选停在结构化前: %s, decision=%s, reason=%s",
                    news_id,
                    triage_decision,
                    triage_result.get("reason_code") or triage_result.get("reason"),
                )
                basic_structured_event = {
                    "news_id": self._resolve_news_row_id(news_data),
                    "event_type": "news.stored",
                    "impact_industries": [],
                    "direction": "neutral",
                    "confidence": 0.2,
                    "summary": news_data.get('title', '预筛选跳过'),
                    "theme_directive": {
                        "structuring_version": "1.0",
                        "llm_request_id": None,
                        "reason": f"triage_{triage_decision.lower()}:{triage_result.get('reason')}",
                        "triage_result": triage_result,
                    },
                    "theme_directive_processed": False,
                    "severity_score": 0.2,
                    "source_weight": 0.3,
                    "event_time": news_data.get('publish_date', datetime.now().isoformat()),
                    "entities": [],
                    "causal_claim": [],
                    "evidence_set": {},
                    "raw_event_json": news_data,
                    "structuring_version": "1.0",
                    "llm_request_id": None,
                    "run_id": news_data.get("run_id"),
                    "case_id": news_data.get("case_id"),
                }
                persistence = await self._persist_and_publish_structured_event(
                    basic_structured_event,
                    publish_stream=False,
                )
                business_results["results"]["structured_event"] = basic_structured_event
                business_results["results"]["news_event_persistence"] = persistence
                business_results["processing_steps"].append("news_event_persist_triage_only")
                return business_results

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
                        ai_result, structuring_meta = await self._extract_event_with_stability(
                            ai_service,
                            news_data,
                        )
                        business_results["results"]["structuring"] = structuring_meta
                        
                        if ai_result and ai_result.get("status") == "skipped":
                            # Phase 4E: LLM判定为低质量事件，跳过结构化，不创建 fallback
                            skip_reason = str(ai_result.get("reason", "low_quality"))[:100]
                            logger.info("⏭️ LLM低质量过滤: news_id=%s reason=%s", news_id, skip_reason)
                            business_results["results"]["structuring"] = structuring_meta
                            business_results["results"]["ai_analysis"] = {
                                "ai_service": "real",
                                "ai_service_response": ai_result,
                                "skipped": True,
                            }
                            business_results["processing_steps"].append("ai_analysis_skipped_low_quality")
                            self.business_stats["ai_analysis_count"] += 1
                        elif ai_result and ai_result.get("status") == "success":
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

        # Phase 4E: LLM explicit skip → no fallback
        ai_analysis = business_results["results"].get("ai_analysis") or {}
        if ai_analysis.get("skipped") is True:
            logger.info("⏭️ LLM已判定低质量，跳过fallback结构化: %s", news_id)
            return business_results

        # 如果没有生成结构化事件（AI分析失败或未启用），创建一个基本的事件并发布
        if "structured_event" not in business_results["results"]:
            logger.info(f"🔄 AI分析失败或未启用，为 {news_id} 创建基本结构化事件")
            try:
                # news_event.news_id 仅允许整数 news_raw.id
                fallback_news_row_id = self._resolve_news_row_id(news_data)
                fallback_news_display_id = news_data.get("news_id") or news_data.get("id") or "unknown"
                logger.info(
                    f"🔄 创建基本结构化事件，新闻标识: {fallback_news_display_id}, news_row_id={fallback_news_row_id}"
                )

                # 创建基本的结构化事件
                structuring_result = business_results["results"].get("structuring") or {}
                structuring_error = str(structuring_result.get("error") or "ai_disabled")
                basic_structured_event = {
                    "news_id": fallback_news_row_id,
                    "event_type": "unknown",
                    "impact_industries": [],
                    "direction": "neutral",
                    "confidence": 0.5,
                    "summary": news_data.get('title', '无标题新闻'),
                    "title": news_data.get("title", ""),
                    "content": news_data.get("content", ""),
                    "theme_directive": {
                        "structuring_version": "1.0",
                        "llm_request_id": None,
                        "reason": "ai_fallback",
                    },
                    "theme_directive_processed": False,
                    "severity_score": 0.5,
                    "source_weight": 0.5,
                    "event_time": news_data.get('publish_date', datetime.now().isoformat()),
                    "entities": [],
                    "causal_claim": [],
                    "evidence_set": {},
                    "raw_event_json": news_data,
                    "structuring_version": "1.0",
                    "structuring_status": "fallback_minimal",
                    "structuring_error": structuring_error,
                    "llm_request_id": None,
                    "run_id": news_data.get("run_id"),
                    "case_id": news_data.get("case_id"),
                }

                logger.info(
                    f"🔄 调用 _persist_and_publish_structured_event: 标识={fallback_news_display_id}, news_row_id={fallback_news_row_id}"
                )
                persistence = await self._persist_and_publish_structured_event(basic_structured_event)
                logger.info(f"🔄 _persist_and_publish_structured_event 返回: {persistence}")

                business_results["results"]["structured_event"] = basic_structured_event
                business_results["results"]["news_event_persistence"] = persistence
                business_results["results"].setdefault(
                    "structuring",
                    {
                        "status": "fallback_minimal",
                        "error": structuring_error,
                        "attempts": 0,
                        "llm_retry_count": 0,
                    },
                )
                self.business_stats["fallback_structured_count"] += 1
                if persistence.get("structured_stream_published"):
                    self.business_stats["processed_after_fallback_count"] += 1
                if persistence.get("structured_stream_published"):
                    business_results["processing_steps"].append("structured_event_publish_fallback")
                    logger.info(f"✅ 基本结构化事件发布成功: {fallback_news_display_id}")
                else:
                    logger.warning(
                        f"⚠️ 基本结构化事件未发布到stream: {fallback_news_display_id}, persistence: {persistence}"
                    )
            except Exception as e:
                logger.error(f"❌ 创建基本结构化事件失败: {e}", exc_info=True)

        return business_results

    async def _extract_event_with_stability(self, ai_service: Any, news_data: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Bound one LLM structuring item so one external stall cannot block the stream."""
        if self._structuring_circuit_breaker_open:
            return None, {
                "status": "fallback_minimal",
                "error": "structuring_circuit_breaker_open",
                "attempts": 0,
                "llm_retry_count": 0,
                "circuit_breaker_open": True,
                "open_at_index": self._structuring_circuit_breaker_open_at,
            }

        attempts = 0
        last_error = ""
        last_status = "structuring_error"
        max_attempts = max(1, self.processor_config["structuring_max_retries"] + 1)
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            if attempt > 1:
                self.business_stats["llm_retry_count"] += 1
                await asyncio.sleep(self.processor_config["structuring_retry_delay_s"])
            try:
                ai_result = await asyncio.wait_for(
                    ai_service.extract_event(news_data),
                    timeout=self.processor_config["structuring_total_timeout_s"],
                )
                if ai_result and ai_result.get("status") == "success":
                    self._structuring_consecutive_timeouts = 0
                    self.business_stats["structuring_success_count"] += 1
                    return ai_result, {
                        "status": "success",
                        "error": None,
                        "attempts": attempts,
                        "llm_retry_count": max(0, attempts - 1),
                        "timeout": self._structuring_timeout_config(),
                    }
                last_status = "structuring_error"
                last_error = str((ai_result or {}).get("error") or "AI structuring returned no success")
            except (asyncio.TimeoutError, TimeoutError):
                last_status = "structuring_timeout"
                last_error = "LLM structuring timeout"
            except Exception as exc:
                last_status = "structuring_error"
                last_error = str(exc)

        if last_status == "structuring_timeout":
            self.business_stats["structuring_timeout_count"] += 1
            self._structuring_consecutive_timeouts += 1
            if self._structuring_consecutive_timeouts >= self.processor_config["structuring_circuit_breaker_threshold"]:
                self._structuring_circuit_breaker_open = True
                self._structuring_circuit_breaker_open_at = news_data.get("sequence") or news_data.get("news_id")
                self.business_stats["circuit_breaker_open_count"] += 1
        else:
            self.business_stats["structuring_error_count"] += 1
            self._structuring_consecutive_timeouts = 0

        return None, {
            "status": last_status,
            "error": last_error,
            "attempts": attempts,
            "llm_retry_count": max(0, attempts - 1),
            "fallback_action": "fallback_minimal",
            "timeout": self._structuring_timeout_config(),
            "circuit_breaker_open": self._structuring_circuit_breaker_open,
            "open_at_index": self._structuring_circuit_breaker_open_at,
        }

    def _structuring_timeout_config(self) -> Dict[str, float]:
        return {
            "connect_timeout_s": self.processor_config["structuring_connect_timeout_s"],
            "read_timeout_s": self.processor_config["structuring_read_timeout_s"],
            "total_timeout_s": self.processor_config["structuring_total_timeout_s"],
        }

    @staticmethod
    def _is_stress_test_news(news_data: Dict[str, Any]) -> bool:
        """
        判定是否为压测注入新闻。
        默认拦截 stress_test_*，可通过 ALLOW_STRESS_TEST_NEWS=true 临时放开。
        """
        allow = str(os.getenv("ALLOW_STRESS_TEST_NEWS", "false")).strip().lower() in {"1", "true", "yes", "on"}
        if allow:
            return False
        news_id = str(news_data.get("news_id") or "").strip().lower()
        return news_id.startswith("stress_test_")

    def _record_triage_stats(self, triage_result: Dict[str, Any]) -> None:
        decision = str(triage_result.get("decision") or "PASS").upper()
        stat_key = {
            "PASS": "triage_pass_count",
            "REVIEW": "triage_review_count",
            "SKIP": "triage_skip_count",
            "DUPLICATE": "triage_duplicate_count",
        }.get(decision)
        if stat_key:
            self.business_stats[stat_key] += 1
        if decision != "PASS" or triage_result.get("should_structurize") is False:
            self.business_stats["triage_structuring_saved_count"] += 1
        event_value_type = str(triage_result.get("event_value_type") or "")
        if decision == "SKIP" and event_value_type == "low_value_disclosure":
            self.business_stats["low_value_triage_skip_count"] += 1
        if decision == "DUPLICATE" or event_value_type == "duplicate":
            self.business_stats["duplicate_triage_skip_count"] += 1
        if decision == "REVIEW" and event_value_type in {"low_value_disclosure", "market_noise"}:
            self.business_stats["triage_false_positive_review_count"] += 1

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
            "run_id": news_data.get("run_id"),
            "case_id": news_data.get("case_id"),
        }

    def _resolve_news_row_id(self, news_data: Dict[str, Any]) -> Any:
        """解析可用于 news_event.news_id 的整型 news_raw.id，无法解析则返回 None。"""
        candidates = [
            news_data.get("news_row_id"),
            news_data.get("stored_news_id"),
            news_data.get("raw_news_id"),
            news_data.get("id"),
            news_data.get("news_id"),
        ]
        for value in candidates:
            parsed = self._coerce_int(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        """仅接受纯整型值（或纯数字字符串）。"""
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                try:
                    return int(text)
                except ValueError:
                    return None
        return None

    async def _persist_and_publish_structured_event(
        self,
        structured_event: Dict[str, Any],
        publish_stream: bool = True,
    ) -> Dict[str, Any]:
        """先落库 news_event，再按需发布 structured 事件。"""
        persistence = {
            "news_event_id": None,
            "structured_stream_published": False,
            "stream_message_id": None,
        }

        news_row_id = structured_event.get("news_id")
        logger.info(f"📝 开始持久化和发布结构化事件: news_row_id={news_row_id}")

        # 处理数据库落库
        news_event_id = None
        if self.database_gateway:
            try:
                news_event_id = await self.database_gateway.create_news_event(structured_event)
                logger.info(f"✅ news_event 落库成功: {news_event_id}")
            except Exception as e:
                logger.error(f"❌ news_event 落库失败: {e}")
                news_event_id = None
        else:
            logger.warning("⚠️ 缺少 database_gateway，跳过 news_event 落库")
            # 仍然尝试发布到stream
            logger.info(f"🔄 跳过落库，直接尝试发布到stream: news_row_id={news_row_id}")

        persistence["news_event_id"] = news_event_id

        if publish_stream:
            # 构建结构化消息，即使没有 news_event_id 也尝试发布
            structured_message = {
                "event_id": news_event_id or f"temp_{int(time.time())}_{news_row_id or 'none'}",
                "news_id": structured_event.get("news_id"),
                "event_type": structured_event.get("event_type"),
                "summary": structured_event.get("summary"),
                "source": "news_stream_processor",
                "structuring_version": structured_event.get("structuring_version"),
                "llm_request_id": structured_event.get("llm_request_id"),
                "run_id": structured_event.get("run_id"),
                "case_id": structured_event.get("case_id"),
            }

            message_id = await self._publish_structured_event(structured_message)
            if message_id:
                persistence["structured_stream_published"] = True
                persistence["stream_message_id"] = message_id
                logger.info(f"✅ 结构化事件发布成功: {message_id}")
            else:
                logger.warning("⚠️ 结构化事件发布失败")
        else:
            logger.info("⏸️ 已按策略跳过结构化事件发布（仅落库）")

        return persistence

    async def _publish_structured_event(self, structured_message: Dict[str, Any]) -> Optional[str]:
        """发布统一的结构化事件消息"""
        if not self.event_bus:
            logger.warning("⚠️ 缺少 event_bus，无法发布结构化事件")
            return None

        event_type = structured_message.get("event_type", "unknown")
        news_id = structured_message.get("news_id", "unknown")

        logger.info(f"📤 尝试发布结构化事件到stream: 事件类型={event_type}, 新闻ID={news_id}")

        if hasattr(self.event_bus, "publish_structured_event"):
            logger.debug(f"使用 publish_structured_event 方法")
            return await self.event_bus.publish_structured_event(structured_message)
        if hasattr(self.event_bus, "publish_to_stream"):
            logger.info(f"使用 publish_to_stream 方法发布到 events_structured")
            result = await self.event_bus.publish_to_stream("events_structured", structured_message)
            logger.info(f"📤 发布结果: {result}")
            return result
        logger.warning("⚠️ event_bus 不支持发布方法")
        return None

    @staticmethod
    def _event_matches_run_id(event_data: Dict[str, Any], run_id: str) -> bool:
        if not run_id:
            return True
        candidates = [
            event_data.get("run_id"),
            event_data.get("case_run_id"),
        ]
        news_data = event_data.get("news_data")
        if isinstance(news_data, dict):
            candidates.extend(
                [
                    news_data.get("run_id"),
                    news_data.get("case_run_id"),
                    news_data.get("external_id"),
                    news_data.get("news_id"),
                    news_data.get("url"),
                ]
            )
        raw_data = event_data.get("raw_data")
        if isinstance(raw_data, dict):
            candidates.extend(
                [
                    raw_data.get("run_id"),
                    raw_data.get("external_id"),
                    raw_data.get("news_id"),
                    raw_data.get("url"),
                ]
            )
        return any(run_id in str(value) for value in candidates if value is not None)
    
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
    
    async def _acknowledge_messages(self, message_ids: List[str]):
        """确认消息（无论是否包含事件）"""
        if not hasattr(self.event_bus, 'ack_message'):
            return

        for msg_id in message_ids:
            try:
                await self.event_bus.ack_message(
                    stream="news_raw",
                    group=self.processor_config["processor_group"],
                    message_id=msg_id
                )
                logger.debug(f"✅ 确认消息: {msg_id}")
            except Exception as e:
                logger.warning(f"确认消息失败 {msg_id}: {e}")

    async def _acknowledge_processed_events(self, events: List[Dict[str, Any]], processing_results: List[Dict[str, Any]]):
        """确认处理成功的事件"""
        if not hasattr(self.event_bus, 'ack_message'):
            return

        # 构建事件ID到处理结果的映射
        event_result_map = {}
        for result in processing_results:
            if result.get("processing_success"):
                event_id = result.get("event_id")
                if event_id:
                    event_result_map[event_id] = result

        # 确认每个成功处理的事件
        for event in events:
            event_id = event.get('id')
            if event_id in event_result_map:
                try:
                    await self.event_bus.ack_message(
                        stream="news_raw",
                        group=self.processor_config["processor_group"],
                        message_id=event_id
                    )
                    logger.debug(f"✅ 确认消息: {event_id}")
                except Exception as e:
                    logger.warning(f"确认消息失败 {event_id}: {e}")

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
            "structuring_success_count": self.business_stats["structuring_success_count"],
            "structuring_timeout_count": self.business_stats["structuring_timeout_count"],
            "structuring_error_count": self.business_stats["structuring_error_count"],
            "fallback_structured_count": self.business_stats["fallback_structured_count"],
            "processed_after_fallback_count": self.business_stats["processed_after_fallback_count"],
            "llm_retry_count": self.business_stats["llm_retry_count"],
            "circuit_breaker_open_count": self.business_stats["circuit_breaker_open_count"],
            "triage_pass_count": self.business_stats["triage_pass_count"],
            "triage_review_count": self.business_stats["triage_review_count"],
            "triage_skip_count": self.business_stats["triage_skip_count"],
            "triage_duplicate_count": self.business_stats["triage_duplicate_count"],
            "triage_structuring_saved_count": self.business_stats["triage_structuring_saved_count"],
            "low_value_triage_skip_count": self.business_stats["low_value_triage_skip_count"],
            "duplicate_triage_skip_count": self.business_stats["duplicate_triage_skip_count"],
            "triage_false_positive_review_count": self.business_stats["triage_false_positive_review_count"],
            "circuit_breaker_open": self._structuring_circuit_breaker_open,
            "circuit_breaker_open_at": self._structuring_circuit_breaker_open_at,
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

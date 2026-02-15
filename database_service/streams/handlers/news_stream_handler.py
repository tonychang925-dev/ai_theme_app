# database_service/streams/handlers/news_stream_handler.py
"""
新闻Stream处理器 - 专门负责从Stream消费消息并存储到数据库
职责：消息消费 → 数据验证 → 调用DatabaseGateway存储 → 消息确认
"""
import asyncio
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class NewsStreamHandler:
    """新闻Stream处理器 - 消息消费和存储层"""
    
    def __init__(self, stream_bus, database_gateway, config=None):
        """
        Args:
            stream_bus: Stream总线（UnifiedRedisStreamBus）
            database_gateway: 数据库网关（DatabaseGateway）
            config: 配置
        """
        self.stream_bus = stream_bus
        self.database_gateway = database_gateway
        self.config = config or {}
        
        # 消费者配置
        self.consumer_config = {
            "consumer_group": self.config.get("consumer_group", "news_storage_handlers"),
            "consumer_name": f"storage_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "stream_name": self.config.get("stream_name", "stream:news:raw"),
            "batch_size": self.config.get("batch_size", 10),
            "block_time": self.config.get("block_time", 5000),
            "enable_auto_ack": self.config.get("enable_auto_ack", True),
            "storage_timeout": self.config.get("storage_timeout", 30),
            "required_fields": ['news_id', 'title', 'content', 'source', 'publish_date']
        }
        
        # 运行状态
        self.running = False
        self.handler_task = None
        
        # 存储统计
        self.storage_stats = {
            "started_at": None,
            "last_message_at": None,
            "total_messages": 0,
            "storage_success": 0,
            "storage_failed": 0,
            "validation_failed": 0,
            "duplicate_news": 0,
            "batches_processed": 0
        }
        
        logger.info(f"📦 新闻Stream存储处理器初始化")
        logger.info(f"   消费者组: {self.consumer_config['consumer_group']}")
        logger.info(f"   Stream: {self.consumer_config['stream_name']}")
    
    async def start_storage_service(self):
        """启动存储服务"""
        if self.running:
            logger.warning("存储服务已经在运行")
            return
        
        self.running = True
        self.storage_stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动新闻Stream存储服务")
        
        # 确保消费者组存在
        await self._ensure_consumer_group()
        
        # 启动存储任务
        self.handler_task = asyncio.create_task(self._storage_service_loop())
        
        return True
    
    async def _storage_service_loop(self):
        """存储服务主循环"""
        logger.info("进入存储服务循环...")
        
        while self.running:
            try:
                # 1. 从Stream消费消息
                messages = await self._consume_messages()
                
                if messages:
                    logger.info(f"📨 收到 {len(messages)} 条待存储消息")
                    
                    # 2. 批量处理消息
                    storage_results = await self._process_storage_batch(messages)
                    
                    # 3. 确认消息
                    if self.consumer_config["enable_auto_ack"]:
                        await self._acknowledge_messages(messages, storage_results)
                    
                    # 4. 更新统计
                    await self._update_storage_stats(storage_results)
                    
                else:
                    # 没有消息时
                    if self.storage_stats["total_messages"] % 10 == 0:
                        logger.info(f"⏳ 等待存储消息... (已处理: {self.storage_stats['storage_success']})")
                    await asyncio.sleep(5)
                    
            except asyncio.CancelledError:
                logger.info("存储服务被取消")
                break
            except Exception as e:
                logger.error(f"存储服务循环异常: {e}")
                await asyncio.sleep(5)
    
    async def _consume_messages(self) -> List[Dict[str, Any]]:
        """从Stream消费消息"""
        try:
            if hasattr(self.stream_bus, 'consume_from_stream'):
                return await self.stream_bus.consume_from_stream(
                    stream=self.consumer_config["stream_name"],
                    group=self.consumer_config["consumer_group"],
                    consumer=self.consumer_config["consumer_name"],
                    count=self.consumer_config["batch_size"],
                    block_ms=self.consumer_config["block_time"]
                )
            else:
                # 降级处理
                logger.warning("Stream总线不支持consume_from_stream")
                await asyncio.sleep(2)
                return []
                
        except Exception as e:
            logger.error(f"消费消息失败: {e}")
            return []
    
    async def _process_storage_batch_legacy(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理存储批次"""
        results = []
        
        for message in messages:
            result = await self._process_storage_message(message)
            results.append(result)
        
        return results
    
    async def _process_storage_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个存储消息 - 精简原始数据处理版"""
        message_id = message.get('id', 'unknown')
        result = {
            "message_id": message_id,
            "storage_success": False,
            "validation_passed": False,
            "error": None,
            "news_id": None,
            "storage_time": datetime.now().isoformat()
        }
        
        try:
            # 🔧 1. 提取原始精简数据
            raw_data = self._extract_raw_data(message)
            
            if not raw_data:
                result["error"] = "无法提取原始新闻数据"
                logger.debug(f"消息 {message_id} 数据提取失败: {message}")
                return result
            
            # 🔧 2. 数据增强（在存储前添加必要字段）
            enhanced_data = self._enhance_news_data(raw_data)
            
            # 3. 验证新闻数据
            validation_result = self._validate_news_data(enhanced_data)
            if not validation_result["valid"]:
                result["error"] = f"数据验证失败: {validation_result['error']}"
                logger.warning(f"消息 {message_id} 验证失败: {validation_result['error']}")
                return result
            
            result["validation_passed"] = True
            news_id = enhanced_data['news_id']
            result["news_id"] = news_id
            
            # 4. 调用DatabaseGateway存储
            stored_news_id = await self.database_gateway.create_news(enhanced_data)
            
            if stored_news_id:
                result["storage_success"] = True
                logger.debug(f"✅ 新闻存储成功: {news_id}")
            else:
                result["error"] = "新闻存储失败"
                logger.error(f"❌ 新闻存储失败: {news_id}")
                
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"处理存储消息 {message_id} 失败: {e}")
        
        return result

    # 修改 _extract_raw_data 方法
    def _extract_raw_data(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """终极修正版：正确处理双层payload结构"""
        
        message_data = message.get('data', {})
        message_id = message.get('id', 'unknown')
        
        logger.info(f"\n🔍 处理消息 {message_id}")
        
        try:
            # 1. 检查外层payload
            if 'payload' not in message_data:
                logger.info(f"   ⚠️ 消息没有payload字段")
                logger.info(f"   消息键名: {list(message_data.keys())}")
                return None
            
            outer_payload = message_data['payload']
            
            # 2. 如果是字符串，解析JSON
            if isinstance(outer_payload, str):
                try:
                    import json
                    outer_payload = json.loads(outer_payload)
                    logger.info(f"   ✅ 解析外层payload JSON")
                except Exception as e:
                    logger.info(f"   ❌ 外层payload JSON解析失败: {e}")
                    return None
            
            # 3. outer_payload应该是字典
            if not isinstance(outer_payload, dict):
                logger.info(f"   ⚠️ 外层payload不是字典: {type(outer_payload)}")
                return None
            
            logger.info(f"   外层payload键名: {list(outer_payload.keys())}")
            
            # 4. 🔍 关键！检查内层payload
            if 'payload' not in outer_payload:
                logger.info(f"   ⚠️ 外层payload没有内层payload字段")
                # 直接检查是否是v2格式
                if outer_payload.get('_t') == 'news' and outer_payload.get('_v') == 2:
                    logger.info(f"   ✅ 在外层payload发现v2格式（直接）")
                    return self._extract_v2_data(outer_payload)
                return None
            
            inner_payload = outer_payload['payload']
            
            # 5. 如果是字符串，解析JSON
            if isinstance(inner_payload, str):
                try:
                    import json
                    inner_payload = json.loads(inner_payload)
                    logger.info(f"   ✅ 解析内层payload JSON")
                except Exception as e:
                    logger.info(f"   ❌ 内层payload JSON解析失败: {e}")
                    return None
            
            # 6. inner_payload应该是字典
            if not isinstance(inner_payload, dict):
                logger.info(f"   ⚠️ 内层payload不是字典: {type(inner_payload)}")
                return None
            
            logger.info(f"   内层payload键名: {list(inner_payload.keys())}")
            
            # 7. 检查是否是v2格式
            if inner_payload.get('_t') == 'news' and inner_payload.get('_v') == 2:
                logger.info(f"   ✅ 在内层payload发现v2格式")
                return self._extract_v2_data(inner_payload)
            
            # 8. 如果不是v2，看看是什么
            logger.info(f"   ⚠️ 不是v2格式，检查其他可能")
            if 'news_data' in inner_payload:
                logger.info(f"   发现news_data字段（v1格式）")
                news_data = inner_payload.get('news_data', {})
                if isinstance(news_data, dict):
                    return news_data
            
            logger.info(f"   ❌ 无法识别格式")
            return None
            
        except Exception as e:
            logger.info(f"   ❌ 提取失败: {e}")
            import traceback
            logger.exception("Unhandled exception in news_stream_handler")
            return None

    def _extract_v2_data(self, v2_data: Dict[str, Any]) -> Dict[str, Any]:
        """提取v2格式数据 - 增加tm字段调试"""
        
        logger.info(f"   🔧 提取v2数据:")
        logger.info(f"      v2数据键名: {list(v2_data.keys())}")
        
        # 🔍 检查tm字段
        if 'tm' in v2_data:
            tm_value = v2_data['tm']
            logger.info(f"      tm字段存在，值: {repr(tm_value)}，类型: {type(tm_value)}")
        else:
            logger.info(f"      ⚠️ tm字段不存在")
        
        result = {}
        
        # 标题
        if 't' in v2_data:
            result['title'] = v2_data['t']
            logger.info(f"      标题: {result['title'][:30]}...")
        else:
            result['title'] = "新闻快讯"
        
        # 内容
        if 'c' in v2_data:
            result['content'] = v2_data['c']
            logger.info(f"      内容长度: {len(result['content'])}")
        else:
            result['content'] = ""
        
        # 来源
        if 's' in v2_data:
            source_abbr = v2_data['s']
            result['source'] = 'akshare_cls' if source_abbr == 'cls' else source_abbr
            logger.info(f"      来源: {result['source']}")
        else:
            result['source'] = "akshare_cls"
        
        # 日期
        if 'd' in v2_data:
            result['publish_date'] = v2_data['d']
            logger.info(f"      日期: {result['publish_date']}")
        else:
            from datetime import datetime
            result['publish_date'] = datetime.now().strftime('%Y-%m-%d')
        
        # 🔧 关键修复：发布时间
        if 'tm' in v2_data and v2_data['tm']:
            result['publish_time'] = v2_data['tm']
            logger.info(f"      时间: {result['publish_time']}")
        else:
            # 如果没有时间，使用默认或空值
            result['publish_time'] = "00:00:00"
            logger.info(f"      ⚠️ 使用默认时间: {result['publish_time']}")
        
        # ID
        if 'id' in v2_data:
            result['news_id'] = v2_data['id']
            logger.info(f"      ID: {result['news_id'][:20]}...")
        else:
            import hashlib
            import time
            content_hash = hashlib.md5(result['content'].encode()).hexdigest()[:8] if result['content'] else ""
            result['news_id'] = f"news_{int(time.time()*1000)}_{content_hash}"
        
        # 批次和序列
        if '_b' in v2_data:
            result['batch_id'] = v2_data['_b']
        
        if '_s' in v2_data:
            result['sequence'] = v2_data['_s']
        
        logger.info(f"   ✅ v2数据提取完成，时间字段: {result.get('publish_time', '无')}")
        return result

    def _detect_message_version_v2(self, message_data: Dict[str, Any]) -> str:
        """修正版：检测消息格式版本"""
        if not isinstance(message_data, dict):
            return "unknown"
        
        # 1. 检查是否有payload字段
        if 'payload' in message_data:
            payload = message_data.get('payload', {})
            
            # 如果payload是字符串，尝试解析
            if isinstance(payload, str):
                try:
                    import json
                    payload = json.loads(payload)
                except:
                    return "legacy"
            
            # 检查payload内部格式
            if isinstance(payload, dict):
                # v2格式检测
                if payload.get('_t') == 'news' and payload.get('_v') == 2:
                    return "v2_in_payload"
                # v1格式检测
                elif 'news_data' in payload:
                    return "v1_in_payload"
            
            # 无法识别的payload格式
            return "legacy"
        
        # 2. 检查是否直接是v2格式
        elif message_data.get('_t') == 'news' and message_data.get('_v') == 2:
            return "v2_direct"
        
        # 3. 检查是否直接是v1格式
        elif 'news_data' in message_data:
            return "v1_direct"
        
        # 4. 检查是否包含新闻字段
        elif any(field in message_data for field in ['title', 'content', 't', 'c']):
            return "generic"
        
        return "unknown"
    
    def _extract_from_legacy_format(self, message_data: Dict[str, Any], depth: int = 0, max_depth: int = 3) -> Optional[Dict[str, Any]]:
        """处理legacy格式消息提取"""
        if depth >= max_depth:
            logger.warning(f"legacy payload解析达到最大深度({max_depth})，停止递归")
            return None
        logger.info(f"   🔍 深入分析legacy格式")
        
        try:
            # 检查消息结构
            logger.info(f"   消息数据键名: {list(message_data.keys())}")
            
            # 重点：payload字段分析
            if 'payload' in message_data:
                payload = message_data.get('payload', {})
                logger.info(f"   payload类型: {type(payload)}")
                
                # 如果payload是字符串，尝试解析
                if isinstance(payload, str):
                    logger.info(f"   payload是字符串，尝试解析JSON")
                    try:
                        import json
                        payload = json.loads(payload)
                        logger.info(f"   ✅ JSON解析成功")
                    except json.JSONDecodeError as e:
                        logger.info(f"   ❌ JSON解析失败: {e}")
                        return None
                
                # 现在payload应该是字典
                if isinstance(payload, dict):
                    logger.info(f"   payload键名: {list(payload.keys())}")
                    
                    # 🔍 关键：检查是否有_t和_v字段（v2格式在payload内部）
                    if payload.get('_t') == 'news' and payload.get('_v') == 2:
                        logger.info(f"   ✅ 在payload内部发现v2格式数据！")
                        logger.info(f"   payload内容预览: t={payload.get('t', '')[:30]}..., c长度={len(payload.get('c', ''))}")
                        return self._reconstruct_from_v2(payload)
                    
                    # 检查是否有news_data字段（v1格式）
                    elif 'news_data' in payload:
                        news_data = payload.get('news_data', {})
                        logger.info(f"   ✅ 在payload内部发现v1格式news_data")
                        return news_data
                    
                    # 检查payload是否直接包含新闻字段
                    elif any(field in payload for field in ['t', 'c', 'title', 'content']):
                        logger.info(f"   ✅ payload直接包含新闻字段")
                        
                        # 如果是v2缩写字段，重建
                        if 't' in payload or 'c' in payload:
                            return self._reconstruct_from_v2(payload)
                        else:
                            return payload
                    
                    # 检查是否有嵌套的payload
                    elif 'payload' in payload:
                        logger.info(f"   🔄 发现嵌套payload，递归提取")
                        return self._extract_from_legacy_format(
                            {'payload': payload['payload']},
                            depth=depth + 1,
                            max_depth=max_depth
                        )
                    
                    else:
                        logger.info(f"   ⚠️ payload不包含可识别的新闻字段")
                
                else:
                    logger.info(f"   ⚠️ payload不是字典: {type(payload)}")
            
            else:
                logger.info(f"   ⚠️ 消息没有payload字段")
            
            return None
            
        except Exception as e:
            logger.info(f"   ❌ legacy格式提取异常: {e}")
            import traceback
            logger.exception("Unhandled exception in news_stream_handler")
            return None

    def _extract_news_data_from_payload(
        self,
        message_data: Dict[str, Any],
        message_id: str,
        depth: int = 0,
        max_depth: int = 3
    ) -> Optional[Dict[str, Any]]:
        """专门从payload中提取news_data"""
        if depth >= max_depth:
            logger.warning(f"消息 {message_id} payload解析达到最大深度({max_depth})，停止递归")
            return None
        
        if not isinstance(message_data, dict):
            return None
        
        # 检查是否有payload字段
        if 'payload' not in message_data:
            return None
        
        payload_value = message_data['payload']
        logger.info(f"   找到payload字段，类型: {type(payload_value)}")
        
        # 如果是字符串，解析JSON
        if isinstance(payload_value, str):
            try:
                import json
                payload = json.loads(payload_value)
                logger.info(f"   payload字符串解析成功")
            except json.JSONDecodeError as e:
                logger.info(f"   ❌ payload不是有效JSON: {e}")
                return None
        else:
            payload = payload_value
        
        # 🔍 调试：查看payload结构
        logger.info(f"   解析后payload类型: {type(payload)}")
        if isinstance(payload, dict):
            logger.info(f"   payload键名: {list(payload.keys())}")
            
            # 🔧 关键修复：检查是否有news_data字段
            if 'news_data' in payload:
                news_data = payload['news_data']
                logger.info(f"   ✅ 找到news_data字段，类型: {type(news_data)}")
                
                if isinstance(news_data, dict):
                    logger.info(f"   news_data键名: {list(news_data.keys())}")
                    
                    # 显示关键字段内容
                    key_fields = ['title', 'content', 'source', 'publish_date', '标题', '内容', '发布日期']
                    for field in key_fields:
                        if field in news_data:
                            value = str(news_data[field])
                            if field in ['content', '内容'] and len(value) > 50:
                                logger.info(f"     {field}: {value[:50]}...")
                            else:
                                logger.info(f"     {field}: {value}")
                    
                    return news_data
                elif isinstance(news_data, str):
                    logger.info(f"   news_data是字符串，长度: {len(news_data)}")
                    # 尝试解析字符串
                    try:
                        import json
                        parsed = json.loads(news_data)
                        if isinstance(parsed, dict):
                            return parsed
                        else:
                            return {'raw_content': news_data}
                    except:
                        return {'raw_content': news_data}
                else:
                    logger.info(f"   ⚠️ news_data类型不支持: {type(news_data)}")
                    return None
            
            # 如果没有news_data，检查是否有嵌套的payload
            elif 'payload' in payload:
                logger.info(f"   发现嵌套payload，递归提取")
                return self._extract_news_data_from_payload(
                    {'payload': payload['payload']},
                    message_id,
                    depth=depth + 1,
                    max_depth=max_depth
                )
            
            # 如果payload直接包含新闻字段
            elif any(field in payload for field in ['title', 'content', 'source', '标题', '内容']):
                logger.info(f"   payload直接包含新闻字段")
                return payload
        
        # 如果是列表（不应该出现）
        elif isinstance(payload, list):
            logger.info(f"   ⚠️ payload是列表，包含 {len(payload)} 个元素")
            if payload and isinstance(payload[0], dict):
                return payload[0]
        
        return None

    def _extract_using_fallback_methods(self, message: Dict[str, Any], message_id: str, message_data: Any) -> Optional[Dict[str, Any]]:
        """备用提取方法"""
        
        # 情况1：消息数据直接包含新闻字段
        if isinstance(message_data, dict):
            news_fields = ['title', 'content', 'source', 'headline', 'body', 'text', 'news_id', 'news_data', '标题', '内容']
            if any(field in message_data for field in news_fields):
                logger.info(f"✅ 消息 {message_id} 直接包含新闻字段")
                self._log_extraction_result(message_id, message_data, True)
                return message_data
        
        # 情况2：消息数据是字符串，尝试解析
        if isinstance(message_data, str) and message_data.strip():
            try:
                import json
                parsed = json.loads(message_data)
                if isinstance(parsed, dict):
                    logger.info(f"✅ 消息 {message_id} 字符串解析为字典")
                    self._log_extraction_result(message_id, parsed, True)
                    return parsed
                else:
                    logger.info(f"⚠️  消息 {message_id} 字符串解析为 {type(parsed)}")
                    result = {'content': message_data}
                    self._log_extraction_result(message_id, result, True)
                    return result
            except json.JSONDecodeError:
                logger.info(f"✅ 消息 {message_id} 字符串内容直接作为新闻内容")
                result = {'content': message_data}
                self._log_extraction_result(message_id, result, True)
                return result
        
        # 情况3：消息本身包含新闻字段
        if isinstance(message, dict):
            news_fields = ['title', 'content', 'source', 'headline', 'body', 'text', 'news_id', '标题', '内容']
            if any(field in message for field in news_fields):
                logger.info(f"✅ 消息 {message_id} 本身包含新闻字段")
                self._log_extraction_result(message_id, message, True)
                return message
            
            # 检查是否有payload字段（直接）
            if 'payload' in message:
                logger.info(f"🔍 消息 {message_id} 直接包含payload字段")
                extracted_data = self._extract_news_data_from_payload({'payload': message['payload']}, message_id)
                if extracted_data:
                    self._log_extraction_result(message_id, extracted_data, True)
                    return extracted_data
        
        logger.info(f"⚠️ 无法从消息 {message_id} 提取有效数据")
        self._log_extraction_result(message_id, None, False)
        return None

    def _log_extraction_result(self, message_id: str, result: Optional[Dict[str, Any]], success: bool = True):
        """记录提取结果"""
        if success and result:
            # 检查是否有中文字段，并转换为英文字段
            normalized_result = self._normalize_field_names(result)
            
            title = normalized_result.get('title', '无标题')
            news_id = normalized_result.get('news_id', '无ID')
            source = normalized_result.get('source', '未知')
            
            logger.info(f"📰 消息 {message_id} 提取结果:")
            logger.info(f"   标题: {title[:30]}...")
            logger.info(f"   ID: {news_id}")
            logger.info(f"   来源: {source}")
            
            # 显示内容长度
            content = normalized_result.get('content', '')
            if content:
                logger.info(f"   内容长度: {len(content)}")
            else:
                logger.info(f"   ⚠️ 内容为空")
                
            if logger.isEnabledFor(logging.DEBUG):
                logger.info(f"   数据键名: {list(normalized_result.keys())}")
        elif not success:
            logger.info(f"❌ 消息 {message_id} 提取失败")

    def _normalize_field_names(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """规范化字段名：将中文字段名转换为英文字段名"""
        normalized = data.copy()
        
        # 字段名映射：中文 → 英文
        field_mapping = {
            '标题': 'title',
            '内容': 'content',
            '来源': 'source',
            '发布日期': 'publish_date',
            '发布时间': 'publish_time'
        }
        
        for chinese_field, english_field in field_mapping.items():
            if chinese_field in normalized:
                value = normalized[chinese_field]
                # 如果英文字段不存在，添加映射
                if english_field not in normalized:
                    normalized[english_field] = value
                # 删除中文字段（可选）
                # del normalized[chinese_field]
        
        return normalized

    def _enhance_news_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """修复版：正确提取中文字段"""
        enhanced = raw_data.copy()
        
        logger.info(f"\n🔍 增强新闻数据:")
        logger.info(f"   原始数据键名: {list(raw_data.keys())}")
        
        # 1. 确保有标题（优先使用中文'标题'字段）
        if '标题' in enhanced and enhanced['标题']:
            enhanced['title'] = enhanced['标题']
            logger.info(f"   从 '标题' 提取: {enhanced['title'][:30]}...")
        elif 'title' not in enhanced or not enhanced['title'] or enhanced['title'] == '未命名新闻':
            # 从content提取标题
            content = enhanced.get('内容', enhanced.get('content', ''))
            if content:
                # 提取第一句话
                import re
                sentences = re.split(r'[。！？]', content)
                if sentences and len(sentences[0]) > 5:
                    enhanced['title'] = sentences[0] + "..."
                else:
                    enhanced['title'] = content[:30] + "..."
                logger.info(f"   从内容提取标题: {enhanced['title'][:30]}...")
            else:
                enhanced['title'] = "新闻快讯"
                logger.info(f"   使用默认标题")
        
        # 2. 确保有内容（优先使用中文'内容'字段）
        if '内容' in enhanced and enhanced['内容']:
            enhanced['content'] = enhanced['内容']
            logger.info(f"   从 '内容' 获取内容，长度: {len(enhanced['content'])}")
        elif 'content' not in enhanced or not enhanced['content']:
            enhanced['content'] = ""
            logger.info(f"   ⚠️ content为空")
        
        # 3. 确保有来源
        if 'source' not in enhanced or not enhanced['source']:
            enhanced['source'] = "财联社"
            logger.info(f"   设置来源: {enhanced['source']}")
        
        # 4. 确保有发布日期
        if '发布日期' in enhanced and enhanced['发布日期']:
            enhanced['publish_date'] = enhanced['发布日期']
            logger.info(f"   从 '发布日期' 获取: {enhanced['publish_date']}")
        elif 'publish_date' not in enhanced or not enhanced['publish_date']:
            from datetime import datetime
            enhanced['publish_date'] = datetime.now().strftime('%Y-%m-%d')
            logger.info(f"   使用当前日期: {enhanced['publish_date']}")
        
        # 5. 生成唯一ID（基于实际内容）
        if 'news_id' not in enhanced:
            import hashlib
            import time
            
            # 使用内容生成唯一ID
            content_hash = ""
            if enhanced['content']:
                content_hash = hashlib.md5(enhanced['content'].encode()).hexdigest()[:8]
            
            timestamp = int(time.time() * 1000)
            enhanced['news_id'] = f"news_{timestamp}_{content_hash}"
            logger.info(f"   生成ID: {enhanced['news_id']}")
        
        return enhanced
    
    def _validate_news_data(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证新闻数据"""
        required_fields = self.consumer_config["required_fields"]
        missing_fields = [field for field in required_fields if field not in news_data]
        
        if missing_fields:
            return {
                "valid": False,
                "error": f"缺少必要字段: {missing_fields}",
                "missing_fields": missing_fields
            }
        
        # 验证数据格式
        try:
            # 检查news_id格式
            news_id = news_data.get('news_id', '')
            if not news_id or len(news_id) < 5:
                return {"valid": False, "error": "news_id格式无效"}
            
            # 检查标题长度
            title = news_data.get('title', '')
            if not title or len(title) < 3:
                return {"valid": False, "error": "标题太短"}
            
            # 检查发布日期格式
            publish_date = news_data.get('publish_date', '')
            # 这里可以添加更复杂的日期验证
            
            return {"valid": True, "error": None}
            
        except Exception as e:
            return {"valid": False, "error": f"数据格式异常: {str(e)}"}
    
    async def _acknowledge_messages(self, messages: List[Dict[str, Any]], 
                                   storage_results: List[Dict[str, Any]]):
        """确认消息"""
        for message, result in zip(messages, storage_results):
            message_id = message.get('id')
            
            # 只有存储成功的消息才确认
            if result.get("storage_success"):
                try:
                    if hasattr(self.stream_bus, 'ack_message'):
                        await self.stream_bus.ack_message(
                            stream=self.consumer_config["stream_name"],
                            group=self.consumer_config["consumer_group"],
                            message_id=message_id
                        )
                        logger.debug(f"✅ 消息确认: {message_id}")
                except Exception as e:
                    logger.error(f"消息确认失败 {message_id}: {e}")
    
    async def _update_storage_stats_legacy(self, storage_results: List[Dict[str, Any]]):
        """更新存储统计"""
        self.storage_stats["batches_processed"] += 1
        
        for result in storage_results:
            self.storage_stats["total_messages"] += 1
            
            if result["validation_passed"]:
                if result["storage_success"]:
                    self.storage_stats["storage_success"] += 1
                    
                    if result.get("duplicate"):
                        self.storage_stats["duplicate_news"] += 1
                else:
                    self.storage_stats["storage_failed"] += 1
            else:
                self.storage_stats["validation_failed"] += 1
        
        self.storage_stats["last_message_at"] = datetime.now().isoformat()
    
    async def stop_storage_service(self):
        """停止存储服务"""
        if not self.running:
            return
        
        logger.info("🛑 停止新闻Stream存储服务")
        
        self.running = False
        
        if self.handler_task:
            self.handler_task.cancel()
            try:
                await self.handler_task
            except asyncio.CancelledError:
                pass
        
        # 打印存储统计
        logger.info(f"📊 存储服务统计:")
        logger.info(f"   运行时间: {self.storage_stats['started_at']} - {datetime.now().isoformat()}")
        logger.info(f"   总消息数: {self.storage_stats['total_messages']}")
        logger.info(f"   存储成功: {self.storage_stats['storage_success']}")
        logger.info(f"   存储失败: {self.storage_stats['storage_failed']}")
        logger.info(f"   验证失败: {self.storage_stats['validation_failed']}")
        logger.info(f"   重复新闻: {self.storage_stats['duplicate_news']}")
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        if self.storage_stats["started_at"]:
            started_dt = datetime.fromisoformat(self.storage_stats["started_at"].replace('Z', '+00:00'))
            running_seconds = (datetime.now() - started_dt).total_seconds()
        else:
            running_seconds = 0
        
        total_messages = max(self.storage_stats["total_messages"], 1)
        valid_messages = self.storage_stats["storage_success"] + self.storage_stats["storage_failed"]
        
        stats_summary = {
            "running": self.running,
            "running_seconds": running_seconds,
            "started_at": self.storage_stats["started_at"],
            "last_message_at": self.storage_stats["last_message_at"],
            "total_messages": self.storage_stats["total_messages"],
            "storage_success": self.storage_stats["storage_success"],
            "storage_failed": self.storage_stats["storage_failed"],
            "validation_failed": self.storage_stats["validation_failed"],
            "duplicate_news": self.storage_stats["duplicate_news"],
            "batches_processed": self.storage_stats["batches_processed"],
            "storage_success_rate": self.storage_stats["storage_success"] / max(valid_messages, 1),
            "consumer_config": self.consumer_config,
            "database_gateway": self.database_gateway.__class__.__name__
        }
        
        return stats_summary
    
    async def manual_storage_test(self, test_news_data: Dict[str, Any]) -> Dict[str, Any]:
        """手动存储测试"""
        logger.info(f"🧪 手动存储测试: {test_news_data.get('news_id')}")
        
        # 模拟消息格式
        test_message = {
            'id': f"test_msg_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'data': {
                'event_type': 'news.crawled',
                'news_data': test_news_data,
                'timestamp': datetime.now().isoformat(),
                'source': 'manual_test'
            }
        }
        
        # 处理存储
        result = await self._process_storage_message(test_message)
        
        test_result = {
            "test_type": "manual_storage_test",
            "news_id": test_news_data.get('news_id'),
            "storage_success": result["storage_success"],
            "validation_passed": result["validation_passed"],
            "error": result.get("error"),
            "timestamp": datetime.now().isoformat()
        }
        
        if result["storage_success"]:
            logger.info(f"✅ 手动存储测试成功: {test_news_data.get('news_id')}")
        else:
            logger.warning(f"⚠️  手动存储测试失败: {result.get('error')}")
        
        return test_result
    
    def print_storage_status(self):
        """打印存储状态"""
        logger.info("\n📦 新闻Stream存储处理器状态")
        logger.info("=" * 60)
        logger.info(f"运行状态: {'✅ 运行中' if self.running else '⏸️ 已停止'}")
        logger.info(f"开始时间: {self.storage_stats['started_at'] or '未开始'}")
        logger.info(f"最后消息: {self.storage_stats['last_message_at'] or '无'}")
        logger.info(f"总消息数: {self.storage_stats['total_messages']}")
        logger.info(f"存储成功: {self.storage_stats['storage_success']}")
        logger.info(f"存储失败: {self.storage_stats['storage_failed']}")
        logger.info(f"验证失败: {self.storage_stats['validation_failed']}")
        
        valid_messages = self.storage_stats["storage_success"] + self.storage_stats["storage_failed"]
        if valid_messages > 0:
            success_rate = self.storage_stats["storage_success"] / valid_messages
            logger.info(f"存储成功率: {success_rate:.1%}")
        
        logger.info(f"\n消费者配置:")
        for key, value in self.consumer_config.items():
            if key != "required_fields":  # 特殊处理
                logger.info(f"  {key}: {value}")
        
        logger.info(f"  必要字段: {', '.join(self.consumer_config['required_fields'])}")
        
        logger.info(f"\n数据库网关: {self.database_gateway.__class__.__name__}")
        logger.info("=" * 60)

    # 在 NewsStreamHandler 中添加统计更新逻辑

    async def _update_storage_stats(self, storage_results: List[Dict[str, Any]]):
        """更新存储统计"""
        self.storage_stats["batches_processed"] += 1
        
        for result in storage_results:
            self.storage_stats["total_messages"] += 1
            
            if result.get("validation_passed"):
                if result.get("storage_success"):
                    self.storage_stats["storage_success"] += 1
                    
                    if result.get("duplicate"):
                        self.storage_stats["duplicate_news"] += 1
                else:
                    self.storage_stats["storage_failed"] += 1
            else:
                self.storage_stats["validation_failed"] += 1
        
        self.storage_stats["last_message_at"] = datetime.now().isoformat()
        
        # 添加调试日志
        if self.storage_stats["total_messages"] % 10 == 0:
            logger.info(f"📊 存储统计: 成功={self.storage_stats['storage_success']}, "
                    f"失败={self.storage_stats['storage_failed']}, "
                    f"验证失败={self.storage_stats['validation_failed']}")

    # 在 _process_storage_batch 方法中确保调用统计更新
    async def _process_storage_batch(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理存储批次"""
        results = []
        
        for message in messages:
            result = await self._process_storage_message(message)
            results.append(result)
        
        # 更新统计
        await self._update_storage_stats(results)
        
        return results

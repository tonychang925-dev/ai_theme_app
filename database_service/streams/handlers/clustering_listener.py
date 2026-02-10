# database_service/processors/clustering_listener.py
"""
聚类监听器 - 基于Pub/Sub的实时触发（修复版）
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class ClusteringListener:
    """聚类监听器 - 发布/订阅模式（修复消费者组问题）"""
    
    def __init__(self, redis_client, db_gateway, theme_service: Any = None, 
                 consumer_name: str = None, config: Dict = None):
        """
        初始化聚类监听器（发布/订阅模式）
        """
        self.redis = redis_client
        self.db_gateway = db_gateway
        self.theme_service = theme_service
        self.running = False
        
        # 配置
        self.config = config or {}
        self.min_cluster_size = self.config.get('min_cluster_size', 3)
        self.quality_threshold = self.config.get('quality_threshold', 0.4)
        
        # 🔥 Pub/Sub通道
        self.trigger_channel = "clustering:trigger"
        self.clustering_done_channel = "clustering:done"
        
        # Stream配置
        self.pending_stream = "stream:events:pending"
        self.decision_stream = "stream:events:decision"
        
        # 消费者配置
        self.consumer_group = "clustering_workers"
        self.consumer_name = consumer_name or f"clustering_{os.getpid()}"
        
        # 状态控制
        self.processing = False  # 防止并发处理
        self.trigger_queue = asyncio.Queue()  # 🔥 触发队列
        self.pubsub = None  # 🔥 Pub/Sub连接
        
        # 统计信息
        self.stats = {
            "started_at": None,
            "triggers_received": 0,
            "batches_processed": 0,
            "clusters_formed": 0,
            "themes_created": 0
        }
        
        logger.info(f"🎯 初始化ClusteringListener (Pub/Sub模式): {self.consumer_name}")
    
    async def start(self):
        """启动聚类监听器 - 订阅触发通道（修复消费者组问题）"""
        if self.running:
            logger.warning("聚类监听器已在运行")
            return []
        
        self.running = True
        self.stats["started_at"] = datetime.now().isoformat()
        
        logger.info(f"🚀 启动ClusteringListener，订阅通道: {self.trigger_channel}")
        
        try:
            # 🔥 修复1：确保消费者组存在
            await self._ensure_consumer_group_exists()
            
            # 🔥 修复2：确保pubsub连接
            await self._ensure_pubsub_connected()
            
            # 🔥 创建任务列表
            tasks = []
            
            # 1. 创建监听任务
            listener_task = asyncio.create_task(
                self._listen_triggers(),
                name="clustering_trigger_listener"
            )
            tasks.append(listener_task)
            
            # 2. 创建处理任务
            processor_task = asyncio.create_task(
                self._process_trigger_queue(),
                name="clustering_processor"
            )
            tasks.append(processor_task)
            
            # 3. 检查并处理现有的pending事件
            init_task = asyncio.create_task(
                self._check_initial_pending(),
                name="clustering_initial_check"
            )
            tasks.append(init_task)
            
            logger.info("✅ ClusteringListener启动成功 (Pub/Sub模式)")
            return tasks
            
        except Exception as e:
            logger.error(f"启动ClusteringListener失败: {e}")
            self.running = False
            return []
    
    async def _ensure_consumer_group_exists(self):
        """确保消费者组存在（修复消费者组创建）"""
        try:
            # 尝试创建消费者组
            await self.redis.xgroup_create(
                self.pending_stream,
                self.consumer_group,
                id="0",
                mkstream=True  # 🔥 确保流存在
            )
            logger.info(f"📝 创建聚类消费者组: {self.consumer_group} (流: {self.pending_stream})")
            
        except Exception as e:
            error_str = str(e)
            if "BUSYGROUP" in error_str:
                logger.debug(f"聚类消费者组已存在: {self.consumer_group}")
            elif "NOGROUP" in error_str or "no such key" in error_str.lower():
                # 尝试其他方法创建流
                logger.warning(f"流或消费者组不存在，尝试创建: {error_str}")
                try:
                    # 先创建流（通过发送一个临时消息）
                    await self.redis.xadd(
                        self.pending_stream,
                        {"temp": "init"},
                        maxlen=1
                    )
                    # 再创建消费者组
                    await self.redis.xgroup_create(
                        self.pending_stream,
                        self.consumer_group,
                        id="0"
                    )
                    logger.info(f"🛠️  创建流和消费者组: {self.pending_stream}/{self.consumer_group}")
                except Exception as e2:
                    logger.error(f"创建流和消费者组失败: {e2}")
            else:
                logger.error(f"创建消费者组失败: {error_str}")
    
    async def _ensure_pubsub_connected(self):
        """确保Pub/Sub连接"""
        try:
            if not self.pubsub:
                self.pubsub = self.redis.pubsub()
            
            # 订阅触发通道
            await self.pubsub.subscribe(self.trigger_channel)
            logger.debug(f"🔗 已订阅触发通道: {self.trigger_channel}")
            
        except Exception as e:
            logger.error(f"建立Pub/Sub连接失败: {e}")
            self.pubsub = None
            raise
    
    async def _listen_triggers(self):
        """监听触发信号（发布/订阅）- 修复版本"""
        logger.info(f"👂 开始监听聚类触发通道: {self.trigger_channel}")
        
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        
        while self.running:
            try:
                if not self.pubsub:
                    await self._ensure_pubsub_connected()
                
                # 🔥 监听消息
                async for message in self.pubsub.listen():
                    if not self.running:
                        break
                    
                    if message['type'] != 'message':
                        continue
                    
                    # 收到触发信号
                    trigger_data = message['data']
                    try:
                        # 尝试解析JSON
                        if isinstance(trigger_data, bytes):
                            trigger_data = trigger_data.decode('utf-8')
                        
                        trigger_json = json.loads(trigger_data)
                        trigger_str = json.dumps(trigger_json, ensure_ascii=False)
                    except:
                        trigger_str = str(trigger_data)[:200]
                    
                    logger.info(f"🔔 收到聚类触发信号: {trigger_str}")
                    
                    # 更新统计
                    self.stats["triggers_received"] += 1
                    
                    # 🔥 将触发信号放入队列
                    await self.trigger_queue.put({
                        'type': 'trigger',
                        'data': trigger_data,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    reconnect_attempts = 0  # 重置重连计数
                    
            except asyncio.CancelledError:
                logger.info("聚类触发监听被取消")
                break
            except Exception as e:
                logger.error(f"监听触发信号失败: {e}")
                reconnect_attempts += 1
                
                if reconnect_attempts >= max_reconnect_attempts:
                    logger.error(f"达到最大重连次数 ({max_reconnect_attempts})，停止监听")
                    break
                
                # 等待后重试
                await asyncio.sleep(min(2 ** reconnect_attempts, 30))
                logger.info(f"尝试重新连接 ({reconnect_attempts}/{max_reconnect_attempts})...")
    
    async def _process_trigger_queue(self):
        """处理触发队列（修复消费者组读取）"""
        logger.info("🔄 启动聚类触发处理器")
        
        while self.running:
            try:
                # 🔥 从队列获取触发信号（非阻塞等待）
                try:
                    trigger = await asyncio.wait_for(
                        self.trigger_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # 超时，继续循环
                    continue
                
                # 检查是否正在处理
                if self.processing:
                    logger.debug("⏳ 聚类处理正在进行中，跳过本次触发")
                    self.trigger_queue.task_done()
                    continue
                
                # 执行聚类处理
                self.processing = True
                try:
                    await self._check_and_process_clustering()
                finally:
                    self.processing = False
                    self.trigger_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("聚类处理器被取消")
                break
            except Exception as e:
                logger.error(f"处理触发队列失败: {e}")
                await asyncio.sleep(1)
    
    async def _check_initial_pending(self):
        """启动时检查并处理现有的pending事件（修复流检查）"""
        try:
            logger.info("🔍 检查初始pending事件...")
            
            # 🔥 修复：使用更健壮的流检查方法
            try:
                # 尝试获取流信息
                stream_info = await self.redis.xinfo_stream(self.pending_stream)
                pending_count = stream_info.get('length', 0)
            except Exception as e:
                if "no such key" in str(e).lower():
                    pending_count = 0
                    logger.debug(f"流不存在: {self.pending_stream}")
                else:
                    raise
            
            if pending_count >= self.min_cluster_size:
                logger.info(f"🎯 发现 {pending_count} 个待处理事件，触发初始聚类")
                
                # 发布触发信号
                trigger_data = {
                    'type': 'initial_check',
                    'pending_count': pending_count,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'clustering_listener'
                }
                
                await self.redis.publish(
                    self.trigger_channel,
                    json.dumps(trigger_data)
                )
            else:
                logger.info(f"📭 初始pending事件不足: {pending_count}/{self.min_cluster_size}")
                
        except Exception as e:
            logger.error(f"检查初始pending事件失败: {e}")
    
    async def _check_and_process_clustering(self):
        """检查并执行聚类分析（修复消费者组读取）"""
        try:
            logger.debug("🔍 检查聚类条件...")
            
            # 1. 读取pending流中的所有未处理事件
            pending_messages = await self._read_all_pending_messages()
            
            if not pending_messages:
                logger.debug("📭 pending流为空")
                return
            
            logger.info(f"📥 读取到 {len(pending_messages)} 个pending事件")
            
            # 2. 检查是否满足聚类条件
            if len(pending_messages) < self.min_cluster_size:
                logger.info(f"⏳ 等待更多事件: {len(pending_messages)}/{self.min_cluster_size}")
                return
            
            # 3. 准备处理批次（每次最多处理前N个）
            batch_size = min(len(pending_messages), 10)  # 每次最多处理10个
            batch_to_process = pending_messages[:batch_size]
            
            logger.info(f"🎯 开始处理聚类批次: {len(batch_to_process)} 个事件")
            
            # 4. 执行聚类分析
            clustering_result = await self._execute_clustering_analysis(batch_to_process)
            
            # 5. 处理聚类结果
            if clustering_result.get('clusters'):
                await self._process_clustering_results(
                    clustering_result['clusters'], 
                    batch_to_process
                )
            
            # 6. 发布完成信号
            await self._publish_clustering_done(clustering_result)
            
            logger.info(f"✅ 聚类处理完成: 处理 {len(batch_to_process)} 事件")
            
        except Exception as e:
            logger.error(f"聚类处理失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _read_all_pending_messages(self) -> List[Dict]:
        """读取pending流中的所有消息（修复消费者组问题）"""
        try:
            # 🔥 修复：使用更健壮的读取方法
            try:
                # 尝试读取消息
                messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.pending_stream: ">"},
                    count=100,
                    block=100
                )
                
                if not messages:
                    return []
                
                # 解析消息格式
                result = []
                for stream, message_list in messages:
                    for msg_id, msg_data in message_list:
                        try:
                            # 🔥 修复：处理不同类型的值
                            def parse_field(value):
                                if isinstance(value, bytes):
                                    return value.decode('utf-8')
                                elif isinstance(value, str):
                                    try:
                                        # 尝试解析JSON
                                        return json.loads(value)
                                    except:
                                        return value
                                else:
                                    return str(value)
                            
                            # 解析字段
                            original_event_raw = msg_data.get('original_event', '{}')
                            original_event = parse_field(original_event_raw)
                            
                            match_result_raw = msg_data.get('match_result', '{}')
                            match_result = parse_field(match_result_raw)
                            
                            event_id = msg_data.get('event_id', 'unknown')
                            if isinstance(event_id, bytes):
                                event_id = event_id.decode('utf-8')
                            
                            result.append({
                                'id': msg_id,
                                'event_data': original_event if isinstance(original_event, dict) else {},
                                'match_result': match_result if isinstance(match_result, dict) else {},
                                'raw_data': msg_data,
                                'event_id': event_id,
                                'stream_type': msg_data.get('original_stream_type', 'normal'),
                                'added_at': msg_data.get('added_at')
                            })
                        except Exception as e:
                            logger.error(f"解析pending消息失败 {msg_id}: {e}")
                
                return result
                
            except Exception as e:
                error_str = str(e)
                if "NOGROUP" in error_str or "no such key" in error_str.lower():
                    # 消费者组或流不存在，尝试重新创建
                    logger.warning(f"消费者组问题: {error_str}")
                    await self._ensure_consumer_group_exists()
                    return []  # 本次返回空，下次会重试
                else:
                    raise
                    
        except Exception as e:
            logger.error(f"读取pending消息失败: {e}")
            return []
    
    async def _execute_clustering_analysis(self, pending_messages: List[Dict]) -> Dict:
        """执行聚类分析算法（增强版）"""
        try:
            logger.info(f"🔬 执行聚类分析: {len(pending_messages)} 个事件")
            
            # 🔥 检查ThemeService是否支持聚类
            if not self.theme_service:
                logger.warning("ThemeService不可用，使用简单聚类逻辑")
                return self._simple_clustering(pending_messages)
            
            # 获取聚类匹配器
            clustering_matcher = None
            if hasattr(self.theme_service, 'discovery_engine') and self.theme_service.discovery_engine:
                clustering_matcher = self.theme_service.discovery_engine.clustering_matcher
            
            if not clustering_matcher:
                logger.warning("聚类匹配器不可用，使用简单聚类逻辑")
                return self._simple_clustering(pending_messages)
            
            # 1. 清空聚类器
            if hasattr(clustering_matcher, 'clear_unmatched_events'):
                await clustering_matcher.clear_unmatched_events()
            
            # 2. 添加事件到聚类器
            for msg in pending_messages:
                event_data = msg['event_data']
                match_result = msg['match_result']
                
                # 提取分类信息
                category_result = match_result.get('category_info', {})
                
                if hasattr(clustering_matcher, 'add_unmatched_event'):
                    await clustering_matcher.add_unmatched_event(
                        event_data=event_data,
                        category_result=category_result
                    )
            
            # 3. 执行聚类
            clusters = []
            if hasattr(clustering_matcher, 'perform_clustering'):
                clusters = await clustering_matcher.perform_clustering()
            
            # 4. 获取高质量簇
            high_quality_clusters = []
            if clusters:
                for cluster in clusters:
                    quality = cluster.get('quality_score', 0)
                    if quality >= self.quality_threshold:
                        high_quality_clusters.append(cluster)
            
            # 更新统计
            self.stats["batches_processed"] += 1
            self.stats["clusters_formed"] += len(high_quality_clusters)
            
            logger.info(f"📊 聚类分析结果: {len(clusters)} 个簇, "
                       f"{len(high_quality_clusters)} 个高质量簇")
            
            return {
                'clusters': high_quality_clusters,
                'total_clusters': len(clusters),
                'processed_events': len(pending_messages),
                'quality_threshold': self.quality_threshold
            }
            
        except Exception as e:
            logger.error(f"聚类分析执行失败: {e}")
            # 降级到简单聚类
            return self._simple_clustering(pending_messages)
    
    def _simple_clustering(self, pending_messages: List[Dict]) -> Dict:
        """简单聚类算法（降级方案）"""
        try:
            # 按关键词简单分组
            keyword_groups = {}
            
            for msg in pending_messages:
                event_data = msg['event_data']
                event_id = msg.get('event_id', 'unknown')
                
                # 提取关键词
                keywords = []
                if 'keywords' in event_data:
                    keywords = event_data['keywords'][:5]  # 取前5个关键词
                elif 'title' in event_data:
                    title = event_data['title']
                    keywords = title.split()[:3]  # 简单分词
                
                # 按第一个关键词分组
                if keywords:
                    main_keyword = keywords[0]
                    if main_keyword not in keyword_groups:
                        keyword_groups[main_keyword] = []
                    keyword_groups[main_keyword].append({
                        'event_id': event_id,
                        'keywords': keywords,
                        'title': event_data.get('title', '无标题')
                    })
            
            # 转换为簇格式
            clusters = []
            for keyword, events in keyword_groups.items():
                if len(events) >= 2:  # 至少2个事件才能形成簇
                    cluster = {
                        'cluster_id': f"simple_{keyword}_{int(datetime.now().timestamp())}",
                        'cluster_size': len(events),
                        'quality_score': 0.3,  # 简单聚类的质量分较低
                        'core_concept': keyword,
                        'events': events,
                        'type': 'simple_keyword'
                    }
                    clusters.append(cluster)
            
            logger.info(f"📊 简单聚类结果: {len(clusters)} 个簇")
            
            return {
                'clusters': clusters,
                'total_clusters': len(clusters),
                'processed_events': len(pending_messages),
                'quality_threshold': 0.2,  # 简单聚类的阈值较低
                'method': 'simple_keyword_clustering'
            }
            
        except Exception as e:
            logger.error(f"简单聚类失败: {e}")
            return {'clusters': [], 'error': str(e)}
    
    async def _process_clustering_results(self, clusters: List[Dict], pending_messages: List[Dict]):
        """处理聚类结果（修复数据序列化）"""
        try:
            # 1. 发布聚类结果决策
            for cluster in clusters:
                # 🔥 修复：确保cluster数据可序列化
                safe_cluster = {}
                for key, value in cluster.items():
                    if isinstance(value, (str, int, float, bool, type(None))):
                        safe_cluster[key] = value
                    else:
                        safe_cluster[key] = str(value)  # 转换为字符串
                
                decision = {
                    'action': 'clustering_result',
                    'cluster': safe_cluster,
                    'cluster_id': cluster.get('cluster_id', f'cluster_{int(datetime.now().timestamp())}'),
                    'quality_score': cluster.get('quality_score', 0),
                    'cluster_size': cluster.get('cluster_size', 0),
                    'timestamp': datetime.now().isoformat(),
                    'processor': self.consumer_name,
                    'source': 'clustering_listener'
                }
                
                # 发布到决策流
                await self._publish_decision(decision)
            
            # 2. 删除已处理的消息
            message_ids = [msg['id'] for msg in pending_messages]
            if message_ids:
                try:
                    deleted = await self.redis.xdel(self.pending_stream, *message_ids)
                    logger.info(f"🗑️ 删除已处理消息: {deleted} 条")
                except Exception as e:
                    logger.error(f"删除消息失败: {e}")
            
            # 3. 更新统计
            self.stats["themes_created"] += len(clusters)
            
        except Exception as e:
            logger.error(f"处理聚类结果失败: {e}")
    
    async def _publish_decision(self, decision: Dict) -> Optional[str]:
        """发布决策到decision流（修复数据格式）"""
        try:
            # 🔥 修复：确保所有值都是字符串类型
            decision_entry = {}
            for key, value in decision.items():
                if isinstance(value, (dict, list)):
                    # 嵌套结构序列化为JSON
                    decision_entry[key] = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, bool):
                    decision_entry[key] = str(value).lower()  # "true"/"false"
                elif value is None:
                    decision_entry[key] = ""
                else:
                    decision_entry[key] = str(value)
            
            # 添加元数据
            decision_entry["publisher"] = self.consumer_name
            decision_entry["timestamp"] = datetime.now().isoformat()
            decision_entry["source"] = "clustering"
            decision_entry["decision_type"] = decision.get('action', 'unknown')
            
            message_id = await self.redis.xadd(
                self.decision_stream,
                decision_entry,
                maxlen=10000
            )
            
            logger.debug(f"📤 发布聚类决策: {decision.get('action')} -> {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"发布聚类决策失败: {e}")
            return None
    
    async def _publish_clustering_done(self, result: Dict):
        """发布聚类完成信号"""
        try:
            done_message = {
                'status': 'success' if result.get('clusters') else 'no_clusters',
                'clusters_found': len(result.get('clusters', [])),
                'events_processed': result.get('processed_events', 0),
                'timestamp': datetime.now().isoformat(),
                'listener': self.consumer_name,
                'method': result.get('method', 'standard')
            }
            
            # 序列化为JSON
            done_json = json.dumps(done_message, ensure_ascii=False)
            
            await self.redis.publish(
                self.clustering_done_channel,
                done_json
            )
            
            logger.debug(f"📢 发布聚类完成信号: {done_message['clusters_found']} 个簇")
            
        except Exception as e:
            logger.error(f"发布聚类完成信号失败: {e}")
    
    async def stop(self):
        """停止聚类监听器（清理资源）"""
        if not self.running:
            return
        
        logger.info("🛑 停止ClusteringListener...")
        self.running = False
        
        # 关闭Pub/Sub连接
        if self.pubsub:
            try:
                await self.pubsub.unsubscribe(self.trigger_channel)
                await self.pubsub.close()
                logger.debug("🔌 关闭Pub/Sub连接")
            except Exception as e:
                logger.error(f"关闭Pub/Sub连接失败: {e}")
            finally:
                self.pubsub = None
        
        # 打印统计
        self.print_stats()
    
    def print_stats(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("📊 ClusteringListener统计信息")
        print("="*60)
        print(f"运行时间: {self.stats['started_at']}")
        print(f"触发信号接收: {self.stats['triggers_received']}")
        print(f"批次处理: {self.stats['batches_processed']}")
        print(f"簇形成: {self.stats['clusters_formed']}")
        print(f"题材创建: {self.stats['themes_created']}")
        print("="*60)

    async def get_status(self):
        """获取组件状态"""
        return {
            "running": self.running,
            "consumer_name": self.consumer_name,
            "stats": self.stats,
            "config": {
                "min_cluster_size": self.min_cluster_size,
                "quality_threshold": self.quality_threshold,
                "trigger_channel": self.trigger_channel,
                "done_channel": self.clustering_done_channel
            },
            "queue_size": self.trigger_queue.qsize(),
            "processing": self.processing
        }
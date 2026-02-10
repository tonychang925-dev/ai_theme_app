# database_service/processors/clustering_workflow.py
"""
完整的异步聚类处理工作流程
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

class AsyncClusteringWorkflow:
    """异步聚类处理工作流程"""
    
    @staticmethod
    async def execute_workflow(redis_client, theme_service, db_gateway, config: Dict = None):
        """
        执行完整的异步聚类工作流程
        
        工作流程:
        1. 监听触发信号（发布/订阅）
        2. 检查pending流条件
        3. 执行聚类分析
        4. 发布结果决策
        5. 清理已处理事件
        """
        logger.info("🔄 开始异步聚类工作流程")
        
        # 1. 创建消费者组（确保存在）
        pending_stream = "stream:events:pending"
        consumer_group = "clustering_workers"
        
        try:
            await redis_client.xgroup_create(
                pending_stream,
                consumer_group,
                id="0",
                mkstream=True
            )
            logger.info(f"✅ 创建聚类消费者组: {consumer_group}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"聚类消费者组已存在: {consumer_group}")
            else:
                logger.error(f"创建消费者组失败: {e}")
                return
        
        # 2. 持续监听和处理
        min_cluster_size = config.get('min_cluster_size', 3) if config else 3
        
        while True:
            try:
                # 使用发布/订阅监听触发
                pubsub = redis_client.pubsub()
                await pubsub.subscribe("clustering:trigger")
                
                logger.info("👂 监听聚类触发通道...")
                
                async for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue
                    
                    logger.info("🔔 收到聚类处理触发信号")
                    
                    # 执行聚类检查和处理
                    await AsyncClusteringWorkflow._process_clustering_batch(
                        redis_client, theme_service, db_gateway, min_cluster_size
                    )
                    
            except Exception as e:
                logger.error(f"聚类工作流程异常: {e}")
                await asyncio.sleep(5)  # 错误后等待
    
    @staticmethod
    async def _process_clustering_batch(redis_client, theme_service, db_gateway, min_cluster_size: int):
        """处理聚类批次"""
        try:
            # 1. 读取pending事件
            pending_stream = "stream:events:pending"
            consumer_group = "clustering_workers"
            consumer_name = f"clustering_{os.getpid()}"
            
            # 读取所有待处理消息
            messages = await redis_client.xreadgroup(
                groupname=consumer_group,
                consumername=consumer_name,
                streams={pending_stream: ">"},
                count=100,
                block=100
            )
            
            if not messages:
                logger.debug("📭 没有待处理的聚类事件")
                return
            
            # 解析消息
            pending_events = []
            for stream, message_list in messages:
                for msg_id, msg_data in message_list:
                    try:
                        event_data = json.loads(msg_data.get('original_event', '{}'))
                        match_result = json.loads(msg_data.get('match_result', '{}'))
                        
                        pending_events.append({
                            'id': msg_id,
                            'event_data': event_data,
                            'match_result': match_result
                        })
                    except Exception as e:
                        logger.error(f"解析pending事件失败: {e}")
            
            logger.info(f"📥 获取到 {len(pending_events)} 个待聚类事件")
            
            # 2. 检查聚类条件
            if len(pending_events) < min_cluster_size:
                logger.info(f"⏳ 等待更多事件: {len(pending_events)}/{min_cluster_size}")
                return
            
            # 3. 执行聚类分析
            logger.info(f"🔬 开始聚类分析: {len(pending_events)} 个事件")
            
            # 获取聚类匹配器
            if (not theme_service or 
                not theme_service.discovery_engine or
                not theme_service.discovery_engine.clustering_matcher):
                logger.error("聚类分析器不可用")
                return
            
            clustering_matcher = theme_service.discovery_engine.clustering_matcher
            
            # 清空并添加事件
            if hasattr(clustering_matcher, 'clear_unmatched_events'):
                await clustering_matcher.clear_unmatched_events()
            
            for event_info in pending_events:
                if hasattr(clustering_matcher, 'add_unmatched_event'):
                    await clustering_matcher.add_unmatched_event(
                        event_data=event_info['event_data'],
                        category_result=event_info['match_result'].get('category_info', {})
                    )
            
            # 执行聚类
            clusters = []
            if hasattr(clustering_matcher, 'perform_clustering'):
                clusters = await clustering_matcher.perform_clustering()
            
            logger.info(f"📊 聚类分析完成: 形成 {len(clusters)} 个簇")
            
            # 4. 处理高质量簇
            high_quality_clusters = [
                cluster for cluster in clusters 
                if cluster.get('quality_score', 0) >= 0.4
            ]
            
            if high_quality_clusters:
                logger.info(f"🎯 发现 {len(high_quality_clusters)} 个高质量簇")
                
                # 为每个高质量簇发布决策
                for cluster in high_quality_clusters:
                    decision = {
                        'action': 'clustering_result',
                        'cluster': cluster,
                        'cluster_id': cluster.get('cluster_id'),
                        'quality_score': cluster.get('quality_score'),
                        'timestamp': datetime.now().isoformat(),
                        'source': 'async_clustering'
                    }
                    
                    # 发布到决策流
                    await redis_client.xadd(
                        "stream:events:decision",
                        {"decision": json.dumps(decision, ensure_ascii=False)},
                        maxlen=10000
                    )
            
            # 5. 删除已处理的事件
            message_ids = [event['id'] for event in pending_events]
            if message_ids:
                deleted = await redis_client.xdel(pending_stream, *message_ids)
                logger.info(f"🗑️ 删除已处理事件: {deleted} 条")
            
            # 6. 发布完成信号
            done_message = {
                'status': 'success',
                'clusters_created': len(high_quality_clusters),
                'events_processed': len(pending_events),
                'timestamp': datetime.now().isoformat()
            }
            
            await redis_client.publish(
                "clustering:done",
                json.dumps(done_message)
            )
            
            logger.info(f"✅ 异步聚类处理完成: 处理 {len(pending_events)} 事件，"
                       f"创建 {len(high_quality_clusters)} 个新题材")
            
        except Exception as e:
            logger.error(f"聚类批次处理失败: {e}")
            import traceback
            traceback.print_exc()
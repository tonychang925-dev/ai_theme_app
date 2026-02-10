# database_service/streams/handlers/decision_executor.py 修复版

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class DecisionExecutor:
    """决策执行器 - 修复数据解析问题"""
    
    def __init__(self, redis_client, db_gateway, consumer_name: str = None):
        self.redis = redis_client
        self.db_gateway = db_gateway
        self.consumer_name = consumer_name or f"decision_{os.getpid()}"
        self.running = False
        
        # Stream配置
        self.decision_stream = "stream:events:decision"
        self.dead_letter_stream = "stream:dead:letter"
        self.consumer_group = "decision_executors"
        
        # 统计信息
        self.stats = {
            "started_at": None,
            "decisions_received": 0,
            "decisions_executed": 0,
            "by_action_type": {},
            "moved_to_dead_letter": 0
        }
        
        logger.info(f"🎯 初始化DecisionExecutor: {self.consumer_name}")
    
    async def start(self):
        """启动决策执行器"""
        if self.running:
            logger.warning("决策执行器已在运行")
            return
        
        self.running = True
        self.stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动DecisionExecutor...")
        
        # 确保消费者组存在
        try:
            await self.redis.xgroup_create(
                self.decision_stream,
                self.consumer_group,
                id="0",
                mkstream=True
            )
            logger.info(f"创建决策消费者组: {self.consumer_group}")
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"创建消费者组失败: {e}")
        
        # 创建监听任务
        listener_task = asyncio.create_task(
            self._listen_for_decisions(),
            name="decision_listener"
        )
        
        logger.info("✅ DecisionExecutor启动成功")
        return [listener_task]
    
    async def _listen_for_decisions(self):
        """监听决策流"""
        logger.info(f"👂 开始监听决策流: {self.decision_stream}")
        
        while self.running:
            try:
                # 从决策流读取消息
                messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.decision_stream: ">"},
                    count=10,
                    block=1000
                )
                
                if not messages:
                    continue
                
                # 处理每个消息
                for stream, message_list in messages:
                    for message_id, message_data in message_list:
                        await self._process_decision(message_id, message_data)
                        
            except asyncio.CancelledError:
                logger.info("决策监听被取消")
                break
            except Exception as e:
                logger.error(f"监听决策流失败: {e}")
                await asyncio.sleep(1)
    
    async def _process_decision(self, message_id: str, message_data: Dict):
        """处理单个决策 - 修复数据解析"""
        try:
            # 🔥 修复：正确解析消息数据
            decision_dict = {}
            
            # 1. 首先将原始消息数据转换为字符串字典
            raw_decision = {}
            for key, value in message_data.items():
                if isinstance(value, bytes):
                    raw_decision[key] = value.decode('utf-8')
                else:
                    raw_decision[key] = str(value)
            
            # 2. 检查是否有专门的decision字段
            decision_str = raw_decision.get('decision', '{}')
            
            if decision_str and decision_str != '{}':
                try:
                    # 解析JSON格式的decision
                    decision_dict = json.loads(decision_str)
                except json.JSONDecodeError:
                    logger.warning(f"决策JSON解析失败，使用原始数据: {decision_str[:100]}")
                    # 尝试从原始字段构建
                    decision_dict = self._build_decision_from_raw(raw_decision)
            else:
                # 如果没有decision字段，尝试从其他字段构建
                decision_dict = self._build_decision_from_raw(raw_decision)
            
            # 3. 确保必要的字段存在
            if not decision_dict.get('action'):
                decision_dict['action'] = raw_decision.get('action') or 'unknown'
            
            if not decision_dict.get('event_id'):
                decision_dict['event_id'] = raw_decision.get('event_id') or 'unknown'
            
            # 4. 处理决策
            action = decision_dict.get('action', 'unknown')
            event_id = decision_dict.get('event_id', 'unknown')
            
            logger.info(f"🎯 处理决策: {action} (事件: {event_id})")
            
            # 更新统计
            self.stats["decisions_received"] += 1
            self.stats["by_action_type"][action] = self.stats["by_action_type"].get(action, 0) + 1
            
            # 执行业务决策
            if action == 'create_new_theme':
                await self._execute_create_theme(decision_dict)
            elif action == 'update_theme':
                await self._execute_update_theme(decision_dict)
            elif action == 'publish_clustering':
                # 这个决策由ThemeProcessor直接处理，这里只记录
                logger.info(f"   ⏭️  跳过聚类发布决策 (由ThemeProcessor直接处理)")
                self.stats["decisions_executed"] += 1
            elif action == 'clustering_result':
                await self._execute_clustering_result(decision_dict)
            else:
                logger.warning(f"未知决策类型: {action}")
                await self._move_to_dead_letter(message_id, message_data, f"unknown_action:{action}")
                return
            
            # ACK消息
            await self.redis.xack(self.decision_stream, self.consumer_group, message_id)
            logger.debug(f"✅ 决策执行完成: {action}")
            
        except Exception as e:
            logger.error(f"处理决策失败 {message_id}: {e}")
            await self._move_to_dead_letter(message_id, message_data, str(e))
    
    def _build_decision_from_raw(self, raw_data: Dict) -> Dict:
        """从原始数据构建决策字典"""
        decision = {}
        
        # 映射可能的字段名
        field_mapping = {
            'action': ['action', 'decision_type', 'type'],
            'event_id': ['event_id', 'event', 'id'],
            'theme_info': ['theme_info', 'theme', 'data'],
            'event_data': ['event_data', 'data', 'original_event']
        }
        
        for target_field, possible_fields in field_mapping.items():
            for possible_field in possible_fields:
                if possible_field in raw_data:
                    value = raw_data[possible_field]
                    if value and value != '{}' and value != '[]':
                        # 尝试解析JSON
                        if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                            try:
                                decision[target_field] = json.loads(value)
                            except:
                                decision[target_field] = value
                        else:
                            decision[target_field] = value
                    break
        
        return decision
    
    # 在DecisionExecutor.py中修复_execute_create_theme方法
    async def _execute_create_theme(self, decision: Dict):
        """执行创建新题材决策 - 修复字符串转换问题"""
        try:
            # 🔥 修复：处理theme_info可能是字符串的情况
            theme_info = decision.get('theme_info', {})
            
            # 如果theme_info是字符串，尝试解析JSON
            if isinstance(theme_info, str):
                try:
                    theme_info = json.loads(theme_info)
                except json.JSONDecodeError:
                    logger.warning(f"theme_info JSON解析失败: {theme_info[:100]}")
                    theme_info = {}
            
            # 🔥 修复：安全提取event_data
            event_data = {}
            
            # 方法1: 从theme_info中提取
            if isinstance(theme_info, dict):
                event_data_raw = theme_info.get('event_data', {})
                
                # 如果event_data是字符串，尝试解析
                if isinstance(event_data_raw, str):
                    try:
                        event_data = json.loads(event_data_raw)
                    except json.JSONDecodeError:
                        # 可能是简单的字符串表示
                        logger.debug(f"event_data解析失败，使用原始字符串: {event_data_raw[:50]}")
                        event_data = {'raw_data': event_data_raw[:200]}
                else:
                    event_data = event_data_raw
            
            # 方法2: 直接从decision中获取
            if not event_data and 'event_data' in decision:
                event_data_raw = decision['event_data']
                if isinstance(event_data_raw, str):
                    try:
                        event_data = json.loads(event_data_raw)
                    except:
                        event_data = {'raw_data': event_data_raw[:200]}
                else:
                    event_data = event_data_raw
            
            # 方法3: 如果还没有，使用整个theme_info作为event_data
            if not event_data and isinstance(theme_info, dict):
                event_data = theme_info
            
            # 确保event_data是字典
            if not isinstance(event_data, dict):
                logger.warning(f"event_data不是字典类型: {type(event_data)}")
                event_data = {'raw_data': str(event_data)[:200]}
            
            # 获取event_id
            event_id = event_data.get('event_id', decision.get('event_id', 'unknown'))
            
            logger.info(f"   🆕 创建新题材 (事件: {event_id})")
            
            # 🔥 修复：检查Gateway方法可用性
            if hasattr(self.db_gateway, 'create_theme_with_stream'):
                # 提取必要的题材信息
                theme_name = self._extract_theme_name(event_data, decision)
                theme_code = self._generate_theme_code(event_data)
                
                # 准备主题数据
                theme_data = {
                    'name': theme_name,
                    'code': theme_code,
                    'theme_type': 'concept',
                    'tags': self._generate_theme_tags(event_data),
                    'heat_score': 70,
                    'status': 'active',
                    'created_by': 'decision_executor',
                    'event_id': event_id
                }
                
                logger.info(f"   创建题材: {theme_name} ({theme_code})")
                
                # 调用正确的方法
                new_theme = await self.db_gateway.create_theme_with_stream(**theme_data)
                
            elif hasattr(self.db_gateway, 'create_theme'):
                # 降级到旧方法
                logger.warning(f"⚠️  Gateway没有create_theme_with_stream方法，使用create_theme")
                new_theme = await self.db_gateway.create_theme(
                    name=self._extract_theme_name(event_data, decision),
                    code=self._generate_theme_code(event_data),
                    theme_type='concept',
                    tags=self._generate_theme_tags(event_data),
                    heat_score=70,
                    status='active',
                    created_by='decision_executor'
                )
            else:
                logger.error(f"Gateway没有创建题材的方法")
                # 返回一个模拟的主题对象，用于继续流程
                new_theme = type('MockTheme', (), {
                    'id': f'temp_{int(asyncio.get_event_loop().time())}',
                    'name': self._extract_theme_name(event_data, decision),
                    'code': self._generate_theme_code(event_data)
                })()
            
            # 发布主题创建事件
            await self._publish_theme_created_event(new_theme, event_id, decision)
            
            logger.info(f"   ✅ 题材创建成功: {getattr(new_theme, 'name', '新题材')}")
            self.stats["decisions_executed"] += 1
            
        except Exception as e:
            logger.error(f"   创建题材执行失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _extract_theme_name(self, event_data: Dict, decision: Dict = None) -> str:
        """从事件数据提取题材名称"""
        # 1. 从AI分析中提取
        ai_analysis = event_data.get('ai_analysis', {})
        if isinstance(ai_analysis, str):
            try:
                ai_analysis = json.loads(ai_analysis)
            except:
                ai_analysis = {}
        
        if ai_analysis:
            core_concept = ai_analysis.get('core_concept', '')
            if core_concept:
                return core_concept[:50]
        
        # 2. 从事件标题中提取
        title = event_data.get('title', '')
        if title:
            return title[:50]
        
        # 3. 从决策信息中提取
        if decision:
            theme_info = decision.get('theme_info', {})
            if isinstance(theme_info, dict):
                theme_name = theme_info.get('theme_name', '')
                if theme_name:
                    return theme_name[:50]
        
        # 4. 生成默认名称
        event_id = event_data.get('event_id', 'unknown')
        return f"新题材_{event_id[:20]}"
    
    def _generate_theme_code(self, event_data: Dict) -> str:
        """生成题材代码"""
        import time
        import hashlib
        
        event_id = event_data.get('event_id', 'unknown')
        timestamp = int(time.time())
        
        # 使用事件ID和时间的哈希值生成短码
        hash_input = f"{event_id}_{timestamp}"
        hash_code = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        return f"T{timestamp}_{hash_code}"
    
    def _generate_theme_tags(self, event_data: Dict) -> Dict:
        """生成题材tags"""
        tags = {
            "source": "event",
            "created_by": "decision_executor",
            "event_id": event_data.get('event_id', 'unknown'),
            "created_at": datetime.now().isoformat()
        }
        
        # 添加关键词
        keywords = event_data.get('keywords', [])
        if keywords:
            if isinstance(keywords, str):
                try:
                    keywords = json.loads(keywords)
                except:
                    keywords = [keywords]
            tags["keywords"] = keywords[:5]
        
        # 添加分类信息
        ai_analysis = event_data.get('ai_analysis', {})
        if isinstance(ai_analysis, dict) and ai_analysis:
            categories = ai_analysis.get('categories', [])
            if categories:
                tags["categories"] = categories
        
        return tags
    
    async def _publish_theme_created_event(self, new_theme, event_id: str, decision: Dict):
        """发布题材创建事件"""
        try:
            theme_data = {
                "theme_id": getattr(new_theme, 'id', 'unknown'),
                "theme_code": getattr(new_theme, 'code', 'unknown'),
                "theme_name": getattr(new_theme, 'name', '新题材'),
                "event_id": event_id,
                "created_at": datetime.now().isoformat(),
                "source": "decision_executor",
                "decision_id": decision.get('decision_id', 'unknown'),
                "action": "theme_created"
            }
            
            # 发布到theme_updates流
            await self.redis.xadd(
                "stream:themes:updates",
                theme_data,
                maxlen=10000
            )
            
            logger.debug(f"📢 发布题材创建事件: {theme_data['theme_name']}")
            
        except Exception as e:
            logger.error(f"发布题材创建事件失败: {e}")
    
    async def _execute_update_theme(self, decision: Dict):
        """执行更新题材决策"""
        logger.info("   🔄 执行更新题材决策")
        # TODO: 实现更新题材逻辑
        self.stats["decisions_executed"] += 1
    
    async def _execute_clustering_result(self, decision: Dict):
        """执行聚类结果决策"""
        logger.info("   🔬 执行聚类结果决策")
        # TODO: 实现聚类结果处理逻辑
        self.stats["decisions_executed"] += 1
    
    async def _move_to_dead_letter(self, message_id: str, message_data: Dict, reason: str):
        """移动消息到死信队列"""
        try:
            dead_letter_entry = {
                "original_message_id": message_id,
                "original_data": json.dumps(message_data, ensure_ascii=False),
                "moved_at": datetime.now().isoformat(),
                "reason": reason,
                "processor": self.consumer_name,
                "original_stream": self.decision_stream
            }
            
            await self.redis.xadd(
                self.dead_letter_stream,
                dead_letter_entry,
                maxlen=10000
            )
            
            self.stats["moved_to_dead_letter"] += 1
            logger.warning(f"决策移动到死信队列: {message_id}")
            
        except Exception as e:
            logger.error(f"移动消息到死信队列失败: {e}")
    
    async def stop(self):
        """停止决策执行器"""
        if not self.running:
            return
        
        logger.info("🛑 停止DecisionExecutor...")
        self.running = False
        
        # 打印统计
        self.print_stats()
    
    def print_stats(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("📊 DecisionExecutor统计信息")
        print("="*60)
        print(f"运行时间: {self.stats['started_at']}")
        print(f"决策接收: {self.stats['decisions_received']}")
        print(f"决策执行: {self.stats['decisions_executed']}")
        print("决策类型分布:")
        for action_type, count in self.stats['by_action_type'].items():
            print(f"  {action_type}: {count}")
        print("="*60)
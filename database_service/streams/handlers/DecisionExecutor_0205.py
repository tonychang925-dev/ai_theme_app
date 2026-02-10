# database_service/streams/handlers/DecisionExecutor.py - 纯执行器版本

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class DecisionExecutor:
    """
    决策执行器 - 纯执行器版本
    职责：只做数据库操作，不包含任何业务规则逻辑
    """
    
    def __init__(self, redis_client, db_gateway, consumer_name: str = None):
        self.redis = redis_client
        self.db_gateway = db_gateway
        self.consumer_name = consumer_name or f"decision_{os.getpid()}"
        self.running = False
        
        # Stream配置
        self.decision_stream = "stream:events:decision"
        self.dead_letter_stream = "stream:dead:letter"
        self.theme_updates_stream = "stream:themes:updates"
        self.consumer_group = "decision_executors"
        
        # 执行状态追踪
        self.execution_context = {
            'last_execution_time': None,
            'last_executed_theme': None,
            'consecutive_errors': 0
        }
        
        # 统计信息 - 简化为纯执行统计
        self.stats = {
            "started_at": None,
            "decisions_received": 0,
            "decisions_executed": 0,
            "decisions_failed": 0,
            "themes_created": 0,
            "themes_updated": 0,
            "mappings_created": 0,
            "clusters_processed": 0,
            "execution_errors": 0,
            "validation_errors": 0,
            "by_action_type": {}
        }
        
        logger.info(f"🎯 初始化纯执行器DecisionExecutor: {self.consumer_name}")
    
    async def start(self):
        """启动决策执行器"""
        if self.running:
            logger.warning("决策执行器已在运行")
            return
        
        self.running = True
        self.stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动纯执行器DecisionExecutor...")
        
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
            name="decision_executor_listener"
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
        """处理单个决策"""
        try:
            # 解析决策数据
            decision = self._parse_decision_data(message_data)
            
            if not decision:
                logger.warning(f"无法解析决策数据: {message_id}")
                await self._move_to_dead_letter(message_id, message_data, "无法解析决策数据")
                return
            
            # 提取关键信息
            action = decision.get('action', 'unknown')
            event_id = decision.get('event_id', 'unknown')
            decision_id = decision.get('decision_id', message_id)
            
            logger.info(f"🎯 执行决策: {action} (事件: {event_id}, 决策ID: {decision_id[:10]}...)")
            
            # 更新统计
            self.stats["decisions_received"] += 1
            self.stats["by_action_type"][action] = self.stats["by_action_type"].get(action, 0) + 1
            
            # 路由执行
            try:
                if action == 'create_new_theme':
                    await self._execute_create_new_theme(decision)
                elif action == 'update_theme':
                    await self._execute_update_theme(decision)
                elif action == 'publish_clustering':
                    await self._execute_publish_clustering(decision)
                elif action == 'clustering_result':
                    await self._execute_clustering_result(decision)
                else:
                    logger.warning(f"未知决策类型: {action}")
                    self.stats["validation_errors"] += 1
                    await self._move_to_dead_letter(
                        message_id, message_data, f"未知决策类型: {action}"
                    )
                    return
                
                # 执行成功，ACK消息
                await self.redis.xack(self.decision_stream, self.consumer_group, message_id)
                self.execution_context['last_execution_time'] = datetime.now().isoformat()
                self.execution_context['consecutive_errors'] = 0
                
                logger.debug(f"✅ 决策执行完成: {action}")
                
            except Exception as e:
                # 执行失败
                logger.error(f"决策执行失败 {action}: {e}")
                self.stats["execution_errors"] += 1
                self.execution_context['consecutive_errors'] += 1
                
                # 根据错误类型处理
                if self.execution_context['consecutive_errors'] >= 3:
                    logger.error(f"连续执行失败3次，系统可能有问题")
                
                # 移动失败消息到死信队列
                await self._move_to_dead_letter(
                    message_id, message_data, f"执行失败: {str(e)}"
                )
                
        except Exception as e:
            logger.error(f"处理决策失败 {message_id}: {e}")
            await self._move_to_dead_letter(message_id, message_data, f"处理失败: {str(e)}")
    
    # ==================== 核心执行方法 ====================
    
    async def _execute_create_new_theme(self, decision: Dict):
        """执行创建新题材决策 - 修复版"""
        try:
            # 🔥 添加详细调试日志
            logger.info("=" * 80)
            logger.info("🎯 DEBUG: 开始执行create_new_theme")
            
            # 1. 从决策中提取ThemeService生成的完整数据
            theme_data = self._extract_theme_data(decision)
            if not theme_data:
                logger.warning("决策中缺少题材数据，无法执行创建")
                self.stats["validation_errors"] += 1
                return
            
            logger.info(f"   📝 执行题材创建: {theme_data.get('name', '未知')}")
            
            # 🔥 检查database_instructions是否存在
            if 'database_instructions' in decision:
                database_instructions = decision['database_instructions']
                logger.info(f"   📋 找到database_instructions字段: {list(database_instructions.keys())}")
            elif 'complete_theme_data' in decision:
                complete_data = decision['complete_theme_data']
                if 'database_instructions' in complete_data:
                    database_instructions = complete_data['database_instructions']
                    logger.info(f"   📋 从complete_theme_data中找到database_instructions")
                else:
                    database_instructions = {}
            else:
                database_instructions = {}
            
            # 2. 验证必要字段
            required_fields = ['name', 'code', 'theme_type', 'description']
            missing_fields = []
            for field in required_fields:
                if not theme_data.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                logger.warning(f"   题材数据缺少必要字段: {missing_fields}")
                self.stats["validation_errors"] += 1
                return
            
            # 3. 执行数据库操作（按顺序）
            # 🔥 3.1 创建分类（如果需要）- 修复：添加详细日志和错误处理
            categories_to_create = database_instructions.get('categories_to_create', [])
            
            if categories_to_create:
                logger.info(f"   🔧 需要创建的分类数量: {len(categories_to_create)}")
                
                for i, category_data in enumerate(categories_to_create, 1):
                    try:
                        category_code = category_data.get('category_code', 'unknown')
                        category_name = category_data.get('category_name', 'unknown')
                        
                        logger.info(f"   创建分类{i}: {category_name} ({category_code})")
                        
                        if hasattr(self.db_gateway, 'create_category'):
                            # 检查分类是否已存在
                            if hasattr(self.db_gateway, 'check_category_exists'):
                                exists = await self.db_gateway.check_category_exists(category_code)
                                if exists:
                                    logger.info(f"    ⚠️  分类已存在: {category_code}，跳过创建")
                                    continue
                            
                            # 创建分类
                            result = await self.db_gateway.create_category(category_data)
                            logger.info(f"    ✅ 分类创建成功: {category_name}")
                        else:
                            logger.error(f"    ❌ db_gateway没有create_category方法!")
                            logger.info(f"    db_gateway可用方法: {[m for m in dir(self.db_gateway) if 'categor' in m.lower()]}")
                            
                    except Exception as e:
                        logger.error(f"   创建分类失败 {category_data.get('category_code')}: {e}")
                        # 如果是唯一约束错误，忽略（分类已存在）
                        if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
                            logger.info(f"   分类已存在: {category_data.get('category_code')}")
                        else:
                            # 重新抛出异常
                            raise
            else:
                logger.info("   ℹ️  没有需要创建的分类")
            
            # 🔥 3.2 创建题材 - 修复：检查分类代码是否存在
            category1_code = theme_data.get('category1_code')
            category2_code = theme_data.get('category2_code')
            
            logger.info(f"   🔍 检查分类代码: category1_code='{category1_code}', category2_code='{category2_code}'")
            
            # 如果分类代码存在但不在categories_to_create中，尝试检查是否已存在
            if category1_code and category1_code != '':
                # 检查分类是否存在
                if hasattr(self.db_gateway, 'check_category_exists'):
                    exists = await self.db_gateway.check_category_exists(category1_code)
                    if not exists:
                        logger.warning(f"   ⚠️  category1_code='{category1_code}' 在数据库中不存在!")
                        # 如果是概念题材，清空分类代码
                        if theme_data.get('theme_type') == 'concept':
                            logger.info(f"   🔧 概念题材，清空分类代码字段")
                            theme_data['category1_code'] = ''
                            theme_data['category2_code'] = ''
            
            # 创建题材
            new_theme = await self._create_theme(theme_data)
            if not new_theme:
                raise Exception("创建题材失败")
            
            theme_id = self._extract_theme_id(new_theme)
            theme_name = theme_data.get('name', '未知题材')
            logger.info(f"   ✅ 题材创建成功: {theme_name} (ID: {theme_id})")
            
            # 3.3 创建事件-题材映射
            event_id = decision.get('event_id')
            if event_id and theme_id:
                await self._create_event_theme_mapping(event_id, theme_id, decision)
            
            # 3.4 初始化热度
            if theme_id:
                await self._initialize_theme_heat(theme_id)
            
            # 3.5 发布创建事件
            await self._publish_theme_created(new_theme, decision)
            
            # 4. 更新统计
            self.stats["decisions_executed"] += 1
            self.stats["themes_created"] += 1
            self.execution_context['last_executed_theme'] = theme_name
            
            logger.info(f"   🎉 题材创建流程完成: {theme_name}")
            
        except Exception as e:
            logger.error(f"   创建题材执行失败: {e}")
            self.stats["execution_errors"] += 1
            raise
    
    async def _execute_update_theme(self, decision: Dict):
        """执行更新题材决策"""
        try:
            logger.info("   🔄 执行更新题材决策")
            
            # 提取主题匹配信息
            match_result = decision.get('match_result', {})
            if not match_result:
                logger.warning("   缺少匹配结果，无法更新")
                return
            
            matched_themes = match_result.get('themes', [])
            if not matched_themes:
                logger.warning("   没有匹配的主题，无法更新")
                return
            
            # 更新每个匹配的主题热度
            for theme_match in matched_themes[:3]:  # 最多更新前3个
                theme_id = theme_match.get('id')
                if theme_id:
                    try:
                        # 增加热度（根据置信度）
                        confidence = theme_match.get('confidence', 0.5)
                        heat_increment = int(confidence * 10)  # 热度增加0-10
                        
                        if hasattr(self.db_gateway, 'increment_theme_heat'):
                            await self.db_gateway.increment_theme_heat(theme_id, heat_increment)
                            logger.debug(f"   更新主题热度: {theme_id} (+{heat_increment})")
                    except Exception as e:
                        logger.warning(f"   更新主题热度失败 {theme_id}: {e}")
            
            # 发布更新事件
            event_data = {
                "action": "theme_heat_updated",
                "themes_updated": len(matched_themes),
                "decision_id": decision.get('decision_id'),
                "timestamp": datetime.now().isoformat()
            }
            await self.redis.xadd(self.theme_updates_stream, event_data, maxlen=10000)
            
            # 更新统计
            self.stats["decisions_executed"] += 1
            self.stats["themes_updated"] += len(matched_themes)
            
            logger.info(f"   ✅ 更新完成: {len(matched_themes)} 个主题")
            
        except Exception as e:
            logger.error(f"   更新主题执行失败: {e}")
            self.stats["execution_errors"] += 1
            raise
    
    async def _execute_publish_clustering(self, decision: Dict):
        """执行发布到聚类队列决策"""
        try:
            logger.info("   📊 执行发布到聚类队列")
            
            # 提取事件数据
            event_data = decision.get('event_data', {})
            if not event_data:
                logger.warning("   缺少事件数据")
                return
            
            event_id = event_data.get('event_id', decision.get('event_id', 'unknown'))
            
            # 发布到pending流
            pending_entry = {
                "event_data": json.dumps(event_data, ensure_ascii=False),
                "published_by": self.consumer_name,
                "publish_time": datetime.now().isoformat(),
                "decision_id": decision.get('decision_id'),
                "reason": decision.get('reason', '未匹配到主题')
            }
            
            await self.redis.xadd("stream:events:pending", pending_entry, maxlen=10000)
            
            # 更新统计
            self.stats["decisions_executed"] += 1
            
            logger.info(f"   📤 事件已发布到聚类队列: {event_id}")
            
        except Exception as e:
            logger.error(f"   发布到聚类队列失败: {e}")
            self.stats["execution_errors"] += 1
            raise
    
    async def _execute_clustering_result(self, decision: Dict):
        """执行聚类结果决策"""
        try:
            logger.info("   🔬 执行聚类结果决策")
            
            # 聚类结果数据应该已经包含完整的主题数据
            # 这里直接调用创建主题方法
            await self._execute_create_new_theme(decision)
            
            # 更新统计
            self.stats["clusters_processed"] += 1
            
        except Exception as e:
            logger.error(f"   处理聚类结果失败: {e}")
            self.stats["execution_errors"] += 1
            raise
    
    # ==================== 数据库操作方法 ====================
    
    async def _create_theme(self, theme_data: Dict):
        """创建主题 - 调用数据库gateway"""
        try:
            # 使用ThemeService生成的完整数据
            if hasattr(self.db_gateway, 'create_theme_with_full_data'):
                logger.debug(f"   使用create_theme_with_full_data创建主题")
                return await self.db_gateway.create_theme_with_full_data(theme_data)
            elif hasattr(self.db_gateway, 'create_theme'):
                logger.debug(f"   使用create_theme创建主题（降级）")
                
                # 从完整数据中提取必要字段
                create_args = {
                    'name': theme_data.get('name'),
                    'code': theme_data.get('code'),
                    'theme_type': theme_data.get('theme_type', 'concept'),
                    'description': theme_data.get('description', ''),
                    'tags': theme_data.get('tags', {}),
                    'heat_score': theme_data.get('heat_score', 70),
                    'confidence_score': theme_data.get('confidence_score', 0.5),
                    'category1_code': theme_data.get('category1_code'),
                    'category2_code': theme_data.get('category2_code'),
                    'level1_category': theme_data.get('level1_category'),
                    'level2_category': theme_data.get('level2_category')
                }
                
                return await self.db_gateway.create_theme(**create_args)
            else:
                raise Exception("数据库gateway没有创建主题的方法")
                
        except Exception as e:
            logger.error(f"   创建主题失败: {e}")
            raise
    
    async def _create_event_theme_mapping(self, event_id: str, theme_id: Any, decision: Dict):
        """创建事件-主题映射"""
        try:
            if not event_id or not theme_id:
                return
            
            # 提取整数事件ID
            event_id_int = self._extract_event_id(event_id)
            if event_id_int == 0:
                logger.debug(f"   无法提取整数事件ID: {event_id}")
                return
            
            # 准备映射参数
            match_result = decision.get('match_result', {})
            confidence = match_result.get('confidence', decision.get('confidence', 0.8))
            
            mapping_data = {
                'confidence': confidence,
                'confidence_level': 'strong' if confidence >= 0.8 else 'medium' if confidence >= 0.6 else 'weak',
                'confidence_weight': int(confidence * 100),
                'match_type': decision.get('match_type', 'new_theme_creation'),
                'created_by': self.consumer_name
            }
            
            # 创建映射
            if hasattr(self.db_gateway, 'create_event_theme_relation'):
                await self.db_gateway.create_event_theme_relation(
                    event_id=event_id_int,
                    theme_id=theme_id,
                    **mapping_data
                )
                
                self.stats["mappings_created"] += 1
                logger.debug(f"   创建事件-主题映射: event={event_id_int}, theme={theme_id}")
            else:
                logger.warning(f"   数据库gateway没有create_event_theme_relation方法")
                
        except Exception as e:
            logger.warning(f"   创建事件-主题映射失败: {e}")
    
    async def _initialize_theme_heat(self, theme_id: Any):
        """初始化主题热度"""
        try:
            if hasattr(self.db_gateway, 'initialize_theme_heat'):
                await self.db_gateway.initialize_theme_heat(theme_id)
                logger.debug(f"   初始化主题热度: {theme_id}")
        except Exception as e:
            logger.debug(f"   初始化主题热度失败: {e}")
    
    async def _publish_theme_created(self, theme, decision: Dict):
        """发布主题创建事件"""
        try:
            theme_id = self._extract_theme_id(theme)
            theme_name = getattr(theme, 'name', '未知主题')
            theme_code = getattr(theme, 'code', '未知')
            
            event_data = {
                "action": "theme_created",
                "theme_id": theme_id,
                "theme_code": theme_code,
                "theme_name": theme_name,
                "theme_type": getattr(theme, 'theme_type', 'concept'),
                "decision_id": decision.get('decision_id', 'unknown'),
                "created_by": self.consumer_name,
                "created_at": datetime.now().isoformat(),
                "source_event": decision.get('event_id'),
                "confidence": decision.get('confidence', 0.8)
            }
            
            await self.redis.xadd(self.theme_updates_stream, event_data, maxlen=10000)
            logger.debug(f"📢 发布主题创建事件: {theme_name}")
            
        except Exception as e:
            logger.error(f"发布主题创建事件失败: {e}")
    
    # ==================== 辅助方法 ====================
    
    def _parse_decision_data(self, message_data: Dict) -> Optional[Dict]:
        """解析决策数据"""
        try:
            # 首先尝试直接解析decision字段
            decision_str = message_data.get('decision')
            if decision_str and isinstance(decision_str, str):
                try:
                    return json.loads(decision_str)
                except json.JSONDecodeError:
                    pass
            
            # 如果没有decision字段，尝试解析整个消息
            decision = {}
            for key, value in message_data.items():
                if isinstance(value, bytes):
                    try:
                        decision[key] = value.decode('utf-8')
                    except:
                        decision[key] = str(value)
                elif isinstance(value, str):
                    decision[key] = value
                else:
                    decision[key] = str(value)
            
            # 尝试解析嵌套的JSON
            for key in ['data', 'payload', 'event_data', 'theme_data']:
                if key in decision and isinstance(decision[key], str):
                    try:
                        decision[key] = json.loads(decision[key])
                    except:
                        pass
            
            return decision
            
        except Exception as e:
            logger.warning(f"解析决策数据失败: {e}")
            return None
    
    def _extract_theme_data(self, decision: Dict) -> Optional[Dict]:
        """从决策中提取主题数据 - 增强版"""
        logger.info(f"🔍 _extract_theme_data: 开始提取主题数据")
        logger.info(f"  决策顶层字段: {list(decision.keys())}")
        
        # 🔥 情况0：如果决策本身就有theme_data，直接返回
        if 'theme_data' in decision:
            logger.info(f"  ✅ 从decision顶层找到theme_data字段")
            return decision['theme_data']
        
        # 🔥 情况1：从 complete_theme_data 中提取
        if 'complete_theme_data' in decision:
            logger.info(f"  ✅ 找到complete_theme_data字段")
            complete_data = decision['complete_theme_data']
            
            if not isinstance(complete_data, dict):
                logger.warning(f"  ❌ complete_theme_data不是字典: {type(complete_data)}")
                return None
            
            logger.info(f"  complete_theme_data字段: {list(complete_data.keys())}")
            
            # 1.1 首先尝试从 database_instructions 获取 theme_create_data
            if 'database_instructions' in complete_data:
                logger.info(f"  ✅ 在complete_theme_data中找到database_instructions")
                instructions = complete_data['database_instructions']
                
                if 'theme_create_data' in instructions:
                    logger.info(f"  ✅ 从database_instructions提取theme_create_data")
                    return instructions['theme_create_data']
                
                # 🔥 如果没有theme_create_data，但有theme_data字段
                if 'theme_data' in instructions:
                    logger.info(f"  ✅ 从database_instructions提取theme_data")
                    return instructions['theme_data']
            
            # 1.2 其次从 theme_data 字段获取
            if 'theme_data' in complete_data:
                logger.info(f"  ✅ 从complete_theme_data提取theme_data")
                return complete_data['theme_data']
            
            # 1.3 最后检查complete_data本身是否是主题数据
            if 'name' in complete_data and 'code' in complete_data:
                logger.info(f"  🔍 complete_data本身看起来就是主题数据")
                return complete_data
        
        # 🔥 情况2：从 database_instructions 获取（旧格式兼容）
        if 'database_instructions' in decision:
            logger.info(f"  ⚠️  旧格式：从decision直接获取database_instructions")
            instructions = decision['database_instructions']
            
            if 'theme_create_data' in instructions:
                return instructions['theme_create_data']
            elif 'theme_data' in instructions:
                return instructions['theme_data']
        
        # 🔥 情况3：检查决策本身是否就是主题数据
        if 'name' in decision and 'code' in decision:
            logger.info(f"  🔍 整个decision看起来就是主题数据格式")
            return decision
        
        logger.warning(f"  ❌ 无法从决策中提取主题数据")
        logger.warning(f"     检查的字段: {list(decision.keys())}")
        
        # 🔥 详细调试信息
        if 'complete_theme_data' in decision:
            complete_data = decision['complete_theme_data']
            if isinstance(complete_data, dict):
                if 'database_instructions' in complete_data:
                    instructions = complete_data['database_instructions']
                    logger.warning(f"     database_instructions字段: {list(instructions.keys())}")
        
        return None
    
    def _extract_theme_id(self, theme) -> Any:
        """提取主题ID"""
        if hasattr(theme, 'id'):
            return theme.id
        elif isinstance(theme, dict) and 'id' in theme:
            return theme['id']
        else:
            return None
    
    def _extract_event_id(self, event_id_str: str) -> int:
        """提取整数事件ID"""
        try:
            if isinstance(event_id_str, str) and event_id_str.isdigit():
                return int(event_id_str)
            
            # 尝试从字符串中提取数字
            import re
            numbers = re.findall(r'\d+', event_id_str)
            if numbers:
                return int(numbers[0])
            
            return 0
        except:
            return 0
    
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
            
            self.stats["decisions_failed"] += 1
            logger.warning(f"决策移动到死信队列: {message_id} - {reason}")
            
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
    
    def get_status(self) -> Dict:
        """获取执行器状态"""
        return {
            "running": self.running,
            "stats": self.stats,
            "execution_context": self.execution_context,
            "consumer": {
                "name": self.consumer_name,
                "group": self.consumer_group
            }
        }
    
    def print_stats(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("📊 DecisionExecutor统计信息 (纯执行器版本)")
        print("="*60)
        print(f"运行时间: {self.stats['started_at']}")
        print(f"决策接收: {self.stats['decisions_received']}")
        print(f"决策执行: {self.stats['decisions_executed']}")
        print(f"决策失败: {self.stats['decisions_failed']}")
        print(f"主题创建: {self.stats['themes_created']}")
        print(f"主题更新: {self.stats['themes_updated']}")
        print(f"映射创建: {self.stats['mappings_created']}")
        print(f"聚类处理: {self.stats['clusters_processed']}")
        print(f"执行错误: {self.stats['execution_errors']}")
        print(f"验证错误: {self.stats['validation_errors']}")
        
        if self.stats['by_action_type']:
            print("\n决策类型分布:")
            for action_type, count in self.stats['by_action_type'].items():
                print(f"  {action_type}: {count}")
        
        print("="*60)
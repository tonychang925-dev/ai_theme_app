# database_service/streams/handlers/DecisionExecutor.py - 修复版（纯执行器）

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)


class DecisionExecutor:
    """
    决策执行器 - 纯执行器修复版
    修复 unhashable type: 'dict' 错误
    
    修复原则：
    1. 修复 _nested_get 方法的字典遍历问题
    2. 保持完全向后兼容性
    3. 增强错误处理和数据验证
    """
    
    def __init__(self, redis_client, db_gateway, consumer_name: str = None):
        self.redis = redis_client
        self.db_gateway = db_gateway
        self.consumer_name = consumer_name or f"decision_{os.getpid()}"
        self.running = False
        
        # Stream配置（保持原有）
        self.decision_stream = "stream:events:decision"
        self.dead_letter_stream = "stream:dead:letter"
        self.theme_updates_stream = "stream:themes:updates"
        self.consumer_group = "decision_executors"
        
        # 执行状态追踪（优化版）
        self.execution_context = {
            'last_execution_time': None,
            'last_executed_action': None,
            'consecutive_errors': 0,
            'error_details': []
        }
        
        # 统计信息 - 优化版
        self.stats = {
            "started_at": None,
            "decisions_received": 0,
            "decisions_executed": 0,
            "decisions_deduplicated": 0,
            "decisions_failed": 0,
            "themes_created": 0,
            "themes_updated": 0,
            "mappings_created": 0,
            "clusters_processed": 0,
            "execution_errors": 0,
            "validation_errors": 0,
            "data_format_errors": 0,
            "db_operation_errors": 0,
            "blocked_auto_theme_create": 0,
            "review_queue_enqueued": 0,
            "review_queue_enqueue_failed": 0,
            "by_action_type": {}
        }
        
        logger.info(f"🎯 初始化纯执行器DecisionExecutor: {self.consumer_name}")
        logger.info(f"   设计原则: 纯执行器，无业务逻辑，不降级处理")
    
    async def start(self):
        """启动决策执行器 - 保持原有方法签名"""
        if self.running:
            logger.warning("决策执行器已在运行")
            return
        
        self.running = True
        self.stats["started_at"] = datetime.now().isoformat()
        
        logger.info("🚀 启动DecisionExecutor...")
        
        # 确保消费者组存在（保持原有逻辑）
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
        
        # 创建监听任务（保持原有）
        listener_task = asyncio.create_task(
            self._listen_for_decisions(),
            name="decision_executor_listener"
        )
        
        logger.info("✅ DecisionExecutor启动成功")
        return [listener_task]
    
    async def _listen_for_decisions(self):
        """监听决策流 - 保持原有逻辑"""
        logger.info(f"👂 开始监听决策流: {self.decision_stream}")
        
        while self.running:
            try:
                messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.decision_stream: ">"},
                    count=10,
                    block=1000
                )
                
                if not messages:
                    continue
                
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
        """处理单个决策 - 修复版"""
        try:
            # 解析决策数据（保持原有逻辑）
            raw_decision = self._parse_decision_data(message_data)
            decision, contract_error = self._normalize_and_validate_decision_envelope(
                raw_decision,
                message_id
            )
            
            if not decision:
                reason = contract_error or "ERR_CONTRACT_PARSE: 无法解析决策数据"
                await self._move_to_dead_letter(
                    message_id,
                    message_data,
                    reason
                )
                return
            
            # 提取关键信息
            action = decision.get('action', 'unknown')
            event_id = decision.get('event_id', 'unknown')
            decision_id = decision.get('decision_id', message_id)
            
            logger.info(f"🎯 执行决策: {action} (事件: {event_id})")

            # 更新统计
            self.stats["decisions_received"] += 1
            self.stats["by_action_type"][action] = self.stats["by_action_type"].get(action, 0) + 1

            # 执行级幂等去重：同一idempotency_key只执行一次
            idempotency_key = decision.get("idempotency_key")
            if await self._should_skip_duplicate_execution(idempotency_key, message_id):
                await self.redis.xack(self.decision_stream, self.consumer_group, message_id)
                self.stats["decisions_deduplicated"] += 1
                logger.info(
                    f"⏭️ 跳过重复决策执行: action={action}, idempotency_key={idempotency_key}"
                )
                return

            # realtime硬门禁兜底：禁止通过执行器自动创建新题材
            if self._should_block_realtime_theme_creation(decision):
                logger.warning(
                    "🛡️ 阻断自动建题材: decision_id=%s event_id=%s source=%s event_type=%s",
                    decision_id,
                    event_id,
                    decision.get("source"),
                    decision.get("event_type"),
                )
                decision["action"] = "publish_clustering"
                decision["reason"] = (
                    (decision.get("reason") or "")
                    + " | blocked_auto_theme_create_for_realtime"
                ).strip(" |")
                action = "publish_clustering"
                self.stats["blocked_auto_theme_create"] += 1
            
            # 🔥 修复：统一路由执行（更简洁）
            try:
                # 根据action执行相应操作
                await self._execute_action_fixed(action, decision, message_id, message_data)
                
                # 执行成功，ACK消息
                await self.redis.xack(self.decision_stream, self.consumer_group, message_id)
                self.execution_context['last_execution_time'] = datetime.now().isoformat()
                self.execution_context['last_executed_action'] = action
                self.execution_context['consecutive_errors'] = 0
                
                self.stats["decisions_executed"] += 1
                logger.info(f"✅ 决策执行完成: {action}")
                
            except Exception as e:
                # 执行失败
                error_msg = f"决策执行失败 {action}: {e}"
                logger.error(error_msg)
                
                self.stats["execution_errors"] += 1
                self.execution_context['consecutive_errors'] += 1
                self.execution_context['error_details'].append({
                    'time': datetime.now().isoformat(),
                    'action': action,
                    'error': str(e),
                    'traceback': self._format_exception(e)
                })
                
                # 移动失败消息到死信队列
                await self._move_to_dead_letter(
                    message_id, message_data, error_msg
                )
                
        except Exception as e:
            logger.error(f"处理决策失败 {message_id}: {e}")
            await self._move_to_dead_letter(message_id, message_data, f"处理失败: {str(e)}")

    def _should_block_realtime_theme_creation(self, decision: Dict[str, Any]) -> bool:
        allow = os.getenv("ALLOW_REALTIME_AUTO_THEME_CREATE", "false").strip().lower()
        if allow in {"1", "true", "yes", "on"}:
            return False

        if decision.get("action") != "create_new_theme":
            return False

        source = str(decision.get("source") or "").lower()
        event_type = str(decision.get("event_type") or "").lower()
        realtime_markers = {"major", "normal", "structured", "realtime"}
        return any(marker in source for marker in realtime_markers) or event_type in realtime_markers
    
    # ==================== 核心执行方法（修复版） ====================
    
    async def _execute_action_fixed(self, action: str, decision: Dict, message_id: str, message_data: Dict):
        """根据action执行相应操作 - 修复版"""
        if action == 'create_new_theme':
            await self._execute_create_new_theme_fixed(decision)
        elif action == 'update_theme':
            await self._execute_update_theme_fixed(decision)
        elif action == 'publish_clustering':
            await self._execute_publish_clustering_fixed(decision)
        elif action == 'clustering_result':
            await self._execute_clustering_result_fixed(decision)
        elif action == 'human_review':
            await self._execute_human_review_fixed(decision)
        elif action == 'drop_event':
            await self._execute_drop_event_fixed(decision)
        else:
            raise ValueError(f"未知决策类型: {action}")

    async def _execute_drop_event_fixed(self, decision: Dict):
        """执行低价值终态丢弃：只记录日志，不入复核、不入聚类、不建映射。"""
        event_data = decision.get("event_data") if isinstance(decision.get("event_data"), dict) else {}
        event_id = event_data.get("event_id") or decision.get("event_id")
        reason = decision.get("reason") or "low_value_event_dropped"
        logger.info("   🧹 低价值事件已丢弃: event_id=%s reason=%s", event_id, reason)
        self.stats["decisions_dropped"] = self.stats.get("decisions_dropped", 0) + 1

    async def _execute_human_review_fixed(self, decision: Dict):
        """执行人工复核决策：只入复核队列，不做题材匹配或股票推荐。"""
        logger.info("   📝 执行人工复核决策")

        event_data = decision.get("event_data") if isinstance(decision.get("event_data"), dict) else {}
        event_id = event_data.get("event_id") or decision.get("event_id")
        if not event_id:
            raise ValueError("人工复核决策缺少 event_id")

        if not hasattr(self.db_gateway, "enqueue_event_review"):
            raise RuntimeError("db_gateway 不支持 enqueue_event_review")

        theme_data = decision.get("theme_data") if isinstance(decision.get("theme_data"), dict) else {}
        confidence = decision.get("confidence")
        proposed_theme_confidence = float(confidence) if confidence is not None else None

        ok = await self.db_gateway.enqueue_event_review(
            event_id=int(event_id),
            reason=decision.get("reason") or "theme_match_human_review",
            source_channel=decision.get("source") or "structured_theme_match",
            proposed_theme_name=theme_data.get("name"),
            proposed_theme_confidence=proposed_theme_confidence,
        )
        if not ok:
            self.stats["review_queue_enqueue_failed"] += 1
            raise RuntimeError(f"写入人工复核队列失败: event_id={event_id}")

        self.stats["review_queue_enqueued"] += 1
        logger.info("   ✅ 已写入人工复核队列: event_id=%s", event_id)
    
    async def _execute_create_new_theme_fixed(self, decision: Dict):
        """
        执行创建新题材决策 - 修复版
        修复 unhashable type: 'dict' 错误
        """
        logger.info("=" * 80)
        logger.info("🎯 执行创建新题材决策（修复版）")
        
        try:
            # 🔥 修复：更安全的提取方法
            logger.info("   1. 安全提取主题数据...")
            theme_data = self._extract_theme_data_safe(decision)
            if not theme_data:
                raise ValueError("无法从决策中提取有效的主题数据")
            
            theme_name = theme_data.get('name', '未知题材')
            logger.info(f"   2. 提取成功: {theme_name}")
            
            # 🔥 修复：简单验证
            logger.info("   3. 验证数据...")
            self._validate_theme_data_basic(theme_data)
            
            # 🔥 修复：获取执行指令
            logger.info("   4. 获取执行指令...")
            operations = self._extract_operations_safe(decision)
            if not operations:
                logger.warning("   没有找到operations字段，使用默认操作序列")
                operations = ['create_theme', 'create_mapping', 'publish_update']
            
            logger.info(f"   5. 执行操作序列: {operations}")
            
            # 🔥 修复：安全执行操作
            logger.info("   6. 按顺序执行操作...")
            await self._execute_operations_fixed(operations, theme_data, decision)
            
            # 7. 更新统计
            self.stats["themes_created"] += 1
            logger.info(f"   🎉 题材创建成功: {theme_name}")
            
        except Exception as e:
            logger.error(f"   创建题材失败: {str(e)[:200]}")
            raise
    
    def _extract_theme_data_safe(self, decision: Dict) -> Optional[Dict]:
        """安全提取主题数据 - 修复版"""
        logger.debug(f"🔍 安全提取主题数据")
        
        # 简单直接的提取逻辑
        try:
            # 1. 直接从theme_data字段获取
            if 'theme_data' in decision:
                data = decision['theme_data']
                if isinstance(data, dict) and 'name' in data and 'code' in data:
                    logger.debug(f"  ✅ 从decision['theme_data']提取")
                    return data
            
            # 2. 从complete_theme_data获取
            if 'complete_theme_data' in decision:
                complete_data = decision['complete_theme_data']
                
                if isinstance(complete_data, dict):
                    # 2.1 从theme_data子字段获取
                    if 'theme_data' in complete_data:
                        data = complete_data['theme_data']
                        if isinstance(data, dict) and 'name' in data and 'code' in data:
                            logger.debug(f"  ✅ 从complete_theme_data['theme_data']提取")
                            return data
                    
                    # 2.2 检查complete_data本身是否是主题数据
                    if 'name' in complete_data and 'code' in complete_data:
                        logger.debug(f"  ✅ complete_theme_data本身就是主题数据")
                        return complete_data
                    
                    # 2.3 从database_instructions获取
                    if 'database_instructions' in complete_data:
                        instructions = complete_data['database_instructions']
                        if isinstance(instructions, dict):
                            if 'theme_data' in instructions:
                                data = instructions['theme_data']
                                if isinstance(data, dict) and 'name' in data and 'code' in data:
                                    logger.debug(f"  ✅ 从database_instructions['theme_data']提取")
                                    return data
                            elif 'theme_create_data' in instructions:
                                data = instructions['theme_create_data']
                                if isinstance(data, dict) and 'name' in data and 'code' in data:
                                    logger.debug(f"  ✅ 从database_instructions['theme_create_data']提取")
                                    return data
            
            # 3. 从database_instructions直接获取（旧格式兼容）
            if 'database_instructions' in decision:
                instructions = decision['database_instructions']
                if isinstance(instructions, dict):
                    if 'theme_data' in instructions:
                        data = instructions['theme_data']
                        if isinstance(data, dict) and 'name' in data and 'code' in data:
                            logger.debug(f"  ✅ 从decision['database_instructions']['theme_data']提取")
                            return data
                    elif 'theme_create_data' in instructions:
                        data = instructions['theme_create_data']
                        if isinstance(data, dict) and 'name' in data and 'code' in data:
                            logger.debug(f"  ✅ 从decision['database_instructions']['theme_create_data']提取")
                            return data
            
            # 4. 检查decision本身
            if 'name' in decision and 'code' in decision:
                logger.debug(f"  ✅ decision本身就是主题数据")
                return decision
            
            logger.error(f"  ❌ 无法提取主题数据")
            logger.error(f"     决策字段: {list(decision.keys())}")
            
            if 'complete_theme_data' in decision:
                complete_data = decision['complete_theme_data']
                if isinstance(complete_data, dict):
                    logger.error(f"     complete_theme_data字段: {list(complete_data.keys())}")
            
            return None
            
        except Exception as e:
            logger.error(f"提取主题数据异常: {e}")
            return None
    
    def _validate_theme_data_basic(self, theme_data: Dict):
        """基本验证主题数据"""
        if not isinstance(theme_data, dict):
            raise ValueError("主题数据必须是字典")
        
        required_fields = ['name', 'code', 'theme_type']
        missing_fields = []
        
        for field in required_fields:
            if field not in theme_data:
                missing_fields.append(field)
            elif not theme_data[field]:
                missing_fields.append(f"{field}为空")
        
        if missing_fields:
            raise ValueError(f"主题数据缺少字段: {missing_fields}")
    
    def _extract_operations_safe(self, decision: Dict) -> List[str]:
        """安全提取操作序列 - 修复版"""
        try:
            # 优先级1：从operations字段直接提取
            if 'operations' in decision:
                ops = decision['operations']
                if isinstance(ops, list):
                    logger.debug(f"  从decision['operations']提取: {ops}")
                    return ops
            
            # 优先级2：从complete_theme_data提取
            if 'complete_theme_data' in decision:
                complete_data = decision['complete_theme_data']
                if isinstance(complete_data, dict) and 'operations' in complete_data:
                    ops = complete_data['operations']
                    if isinstance(ops, list):
                        logger.debug(f"  从complete_theme_data['operations']提取: {ops}")
                        return ops
            
            # 优先级3：从database_instructions提取（旧格式）
            if 'database_instructions' in decision:
                instructions = decision['database_instructions']
                if isinstance(instructions, dict) and 'operations' in instructions:
                    ops = instructions['operations']
                    if isinstance(ops, list):
                        logger.debug(f"  从database_instructions['operations']提取: {ops}")
                        return ops
            
            logger.warning("决策中没有找到operations字段")
            return []
            
        except Exception as e:
            logger.warning(f"提取operations失败: {e}")
            return []
    
    async def _execute_operations_fixed(self, operations: List[str], theme_data: Dict, decision: Dict):
        """安全执行操作序列 - 修复版"""
        event_id = decision.get('event_id')
        theme_result = None
        
        for i, operation in enumerate(operations, 1):
            logger.info(f"   [{i}/{len(operations)}] 执行操作: {operation}")
            
            try:
                if operation == 'create_category':
                    await self._execute_create_category_safe(decision)
                elif operation == 'create_theme':
                    theme_result = await self._execute_create_theme_safe(theme_data)
                    if theme_result:
                        self._cache_theme_id_safe(theme_result)
                elif operation == 'create_mapping':
                    if event_id:
                        theme_id = self._get_cached_theme_id()
                        if theme_id:
                            await self._execute_create_mapping_safe(event_id, theme_id, decision)
                elif operation == 'publish_update':
                    theme_id = self._get_cached_theme_id()
                    if theme_id:
                        await self._execute_publish_theme_update_safe(theme_id, theme_data, decision)
                elif operation == 'initialize_heat':
                    theme_id = self._get_cached_theme_id()
                    if theme_id:
                        await self._execute_initialize_theme_heat_safe(theme_id)
                else:
                    logger.warning(f"   跳过未知操作: {operation}")
                    
            except Exception as e:
                logger.error(f"   执行操作'{operation}'失败: {e}")
                raise
    
    async def _execute_create_category_safe(self, decision: Dict):
        """安全创建分类"""
        try:
            categories = self._extract_categories_safe(decision)
            
            for i, category_data in enumerate(categories, 1):
                category_code = category_data.get('category_code', f'unknown_{i}')
                category_name = category_data.get('category_name', f'未知分类_{i}')
                
                logger.info(f"   创建分类{i}: {category_name} ({category_code})")
                
                if hasattr(self.db_gateway, 'create_category'):
                    try:
                        result = await self.db_gateway.create_category(category_data)
                        # 2. 🔥 核心同步逻辑
                        await self._sync_category_cache_simple(category_data)
                        logger.debug(f"   分类创建结果: {result}")
                    except Exception as e:
                        # 如果是唯一约束错误（分类已存在），记录并继续
                        if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
                            logger.info(f"   分类已存在: {category_code}")
                        else:
                            raise
                else:
                    logger.error(f"   数据库gateway不支持create_category操作")
                    
        except Exception as e:
            logger.error(f"   创建分类失败: {e}")
            raise
    
    async def _sync_category_cache_simple(self, category_data: Dict):
        """同步分类缓存 - 最小实现"""
        try:
            # 导入ThemeService
            from theme_service.services.theme_service import get_theme_service
            
            theme_service = get_theme_service()
            
            # 目标1: 更新existing_categories（给theme_rule_generator用）
            if hasattr(theme_service, 'existing_categories'):
                if theme_service.existing_categories is None:
                    theme_service.existing_categories = []
                
                # 检查是否已存在
                new_code = category_data.get('category_code')
                exists = any(
                    cat.get('category_code') == new_code 
                    for cat in theme_service.existing_categories
                )
                
                if not exists:
                    theme_service.existing_categories.append(category_data)
                    logger.info(f"    ✅ 已更新existing_categories缓存")
            
            # 目标2: 更新matcher的categories（给KeywordMatcher用）
            if hasattr(theme_service, 'discovery_engine'):
                engine = theme_service.discovery_engine
                
                # 更新categories_data
                if hasattr(engine, 'categories_data'):
                    code = category_data.get('category_code')
                    if code:
                        engine.categories_data[code] = category_data
                
                # 直接更新matcher的categories字典
                matchers = []
                if hasattr(engine, 'major_matcher'):
                    matchers.append(engine.major_matcher)
                if hasattr(engine, 'normal_matcher'):
                    matchers.append(engine.normal_matcher)
                
                for matcher in matchers:
                    if hasattr(matcher, 'categories'):
                        if not isinstance(matcher.categories, dict):
                            matcher.categories = {}
                        
                        code = category_data.get('category_code')
                        if code:
                            matcher.categories[code] = category_data
                
                logger.info(f"    ✅ 已更新matcher缓存")
            
            logger.info(f"   分类缓存同步完成")
            
        except Exception as e:
            logger.warning(f"   缓存同步失败（不影响主流程）: {e}")
    
    def _extract_categories_safe(self, decision: Dict) -> List[Dict]:
        """安全提取分类数据"""
        categories = []
        
        # 从complete_theme_data提取
        if 'complete_theme_data' in decision:
            complete_data = decision['complete_theme_data']
            if isinstance(complete_data, dict):
                if 'categories_to_create' in complete_data:
                    cats = complete_data['categories_to_create']
                    if isinstance(cats, list):
                        categories.extend(cats)
                elif 'database_instructions' in complete_data:
                    instructions = complete_data['database_instructions']
                    if isinstance(instructions, dict) and 'categories_to_create' in instructions:
                        cats = instructions['categories_to_create']
                        if isinstance(cats, list):
                            categories.extend(cats)
        
        # 从database_instructions提取（旧格式）
        elif 'database_instructions' in decision:
            instructions = decision['database_instructions']
            if isinstance(instructions, dict) and 'categories_to_create' in instructions:
                cats = instructions['categories_to_create']
                if isinstance(cats, list):
                    categories.extend(cats)
        
        return categories
    
    async def _execute_create_theme_safe(self, theme_data: Dict):
        """安全创建题材"""
        try:
            logger.info(f"   创建题材: {theme_data.get('name')}")
            
            if hasattr(self.db_gateway, 'create_theme_with_full_data'):
                result = await self.db_gateway.create_theme_with_full_data(theme_data)
                logger.debug(f"   使用create_theme_with_full_data创建主题")
                return result
            elif hasattr(self.db_gateway, 'create_theme'):
                # 准备参数
                create_args = self._prepare_theme_create_args_safe(theme_data)
                result = await self.db_gateway.create_theme(**create_args)
                logger.debug(f"   使用create_theme创建主题")
                return result
            else:
                raise Exception("数据库gateway没有创建主题的方法")
                
        except Exception as e:
            logger.error(f"   创建题材失败: {e}")
            raise
    
    def _prepare_theme_create_args_safe(self, theme_data: Dict) -> Dict:
        """完整准备创建主题的参数 - 修复版"""
        logger.info(f"🔧 准备完整参数，原始字段数: {len(theme_data)}")
        
        args = {
            'name': theme_data.get('name', ''),
            'code': theme_data.get('code', ''),
            'theme_type': theme_data.get('theme_type', 'concept'),
            'description': theme_data.get('description', ''),
            'status': theme_data.get('status', 'active'),
            'tags': theme_data.get('tags', {}),
            'heat_score': theme_data.get('heat_score', 50),
            'confidence_score': theme_data.get('confidence_score', 0.5),
            'lifecycle_stage': theme_data.get('lifecycle_stage', 'emerging'),
            'source_system': theme_data.get('source_system', 'ai_theme_discovery'),
            'source_id': theme_data.get('source_id', 'unknown'),
            'created_by': theme_data.get('created_by', 'theme_service'),
        }
        
        # 分类相关字段
        category_fields = [
            'level1_category', 'level2_category', 'level3_category',
            'category1_code', 'category2_code', 'category3_code',
            'category_path'
        ]
        
        for field in category_fields:
            if field in theme_data:
                args[field] = theme_data[field]
            elif field == 'category_path':
                # 构建默认的category_path
                path = []
                if theme_data.get('level1_category'):
                    path.append(theme_data['level1_category'])
                if theme_data.get('level2_category'):
                    path.append(theme_data['level2_category'])
                if theme_data.get('level3_category'):
                    path.append(theme_data['level3_category'])
                if path:  # 只在有内容时设置
                    args['category_path'] = path
        
        # 其他统计字段
        other_fields = [
            'related_stocks', 'stock_count', 'news_count', 'mention_count',
            'last_mentioned'
        ]
        
        for field in other_fields:
            if field in theme_data:
                args[field] = theme_data[field]
        
        # 特殊处理数组字段
        if 'related_stocks' in args:
            if isinstance(args['related_stocks'], dict):
                # 如果是字典，转换为键列表
                args['related_stocks'] = list(args['related_stocks'].keys())
            elif not isinstance(args['related_stocks'], list):
                args['related_stocks'] = []
        
        # 记录实际提取的字段
        logger.info(f"✅ 提取了 {len(args)} 个字段: {list(args.keys())}")
        
        # 调试：检查关键字段
        debug_fields = ['level1_category', 'category1_code', 'heat_score', 'source_system']
        for field in debug_fields:
            if field in args:
                logger.debug(f"   {field}: {args[field]}")
            else:
                logger.warning(f"   {field}: 未找到")
        
        return args
    
    def _cache_theme_id_safe(self, db_result):
        """安全缓存theme_id"""
        try:
            if hasattr(db_result, 'id'):
                self._last_theme_id = db_result.id
            elif isinstance(db_result, dict) and 'id' in db_result:
                self._last_theme_id = db_result['id']
            elif isinstance(db_result, (int, str)):
                self._last_theme_id = db_result
            else:
                logger.warning(f"无法从结果中提取theme_id: {type(db_result)}")
        except Exception as e:
            logger.warning(f"缓存theme_id失败: {e}")
    
    def _get_cached_theme_id(self):
        """获取缓存的theme_id"""
        return getattr(self, '_last_theme_id', None)
    
    async def _execute_create_mapping_safe(self, event_id: str, theme_id: Any, decision: Dict):
        """安全创建事件-题材映射"""
        if not event_id or not theme_id:
            return
        
        try:
            event_id_int = self._extract_event_id(event_id)
            if event_id_int == 0:
                logger.warning(f"   无法提取整数事件ID: {event_id}")
                return
            
            mapping_data = {
                'confidence': decision.get('confidence', 0.8),
                'match_type': decision.get('match_type', 'new_theme_creation'),
                'created_by': self.consumer_name
            }
            
            if hasattr(self.db_gateway, 'create_event_theme_relation'):
                await self.db_gateway.create_event_theme_relation(
                    event_id=event_id_int,
                    theme_id=theme_id,
                    **mapping_data
                )
                self.stats["mappings_created"] += 1
                logger.info(f"   创建映射成功: event={event_id_int}, theme={theme_id}")
            else:
                logger.warning(f"   数据库gateway没有create_event_theme_relation方法")
                
        except Exception as e:
            logger.warning(f"   创建映射失败: {e}")
    
    async def _execute_publish_theme_update_safe(self, theme_id: Any, theme_data: Dict, decision: Dict):
        """安全发布题材更新事件"""
        try:
            event_data = {
                "action": "theme_created",
                "theme_id": theme_id,
                "theme_name": theme_data.get('name', '未知主题'),
                "theme_code": theme_data.get('code', '未知'),
                "decision_id": decision.get('decision_id', 'unknown'),
                "created_by": self.consumer_name,
                "created_at": datetime.now().isoformat(),
                "source_event": decision.get('event_id')
            }
            
            await self.redis.xadd(self.theme_updates_stream, event_data, maxlen=10000)
            logger.info(f"   发布题材创建事件: {theme_data.get('name')}")
            
        except Exception as e:
            logger.error(f"   发布创建事件失败: {e}")
    
    async def _execute_initialize_theme_heat_safe(self, theme_id: Any):
        """安全初始化题材热度"""
        try:
            if hasattr(self.db_gateway, 'initialize_theme_heat'):
                await self.db_gateway.initialize_theme_heat(theme_id)
                logger.debug(f"   初始化主题热度: {theme_id}")
        except Exception as e:
            logger.debug(f"   初始化热度失败: {e}")
    
    async def _execute_update_theme_fixed(self, decision: Dict):
        """执行更新题材决策 - 修复版"""
        logger.info("   🔄 执行更新题材决策（修复版）")
        
        try:
            event_id = decision.get('event_id')
            theme_data = decision.get('theme_data', {})
            theme_id = theme_data.get('id')
            subject_key = theme_data.get('subject_key') or decision.get("matched_subject_key")
            theme_name = theme_data.get('name', '未知题材')
            
            if not theme_id and not subject_key:
                raise ValueError("更新决策缺少 subject_key/theme_id")
            
            operations = self._extract_operations_safe(decision)
            if not operations:
                operations = ['update_theme_heat', 'create_mapping', 'publish_update']
                logger.info(f"   使用默认操作序列: {operations}")
            
            logger.info(f"   更新题材: {theme_name} (ID: {theme_id})")
            
            for operation in operations:
                if operation == 'update_theme_heat':
                    if theme_id:
                        await self._execute_update_theme_heat_safe(theme_id, decision)
                elif operation == 'create_mapping':
                    if event_id:
                        if subject_key:
                            await self._execute_create_subject_mapping_safe(event_id, subject_key, theme_name, decision)
                            await self._execute_related_subject_mappings_safe(event_id, subject_key, decision)
                        elif theme_id:
                            await self._execute_create_mapping_safe(event_id, theme_id, decision)
                elif operation == 'publish_update':
                    if theme_id:
                        await self._execute_publish_theme_updated_safe(theme_id, decision)
                else:
                    logger.warning(f"   跳过未知操作: {operation}")
            
            self.stats["themes_updated"] += 1
            logger.info(f"   ✅ 题材更新成功: {theme_name}")
            
        except Exception as e:
            logger.error(f"   更新题材失败: {e}")
            raise

    async def _execute_create_subject_mapping_safe(
        self,
        event_id: str,
        subject_key: str,
        subject_name: str,
        decision: Dict,
    ):
        """安全创建事件-JYHF题材映射，不依赖 theme_master。"""
        if not event_id or not subject_key:
            return

        event_id_int = self._extract_event_id(event_id)
        if event_id_int == 0:
            logger.warning(f"   无法提取整数事件ID: {event_id}")
            return

        if not hasattr(self.db_gateway, "upsert_event_subject_relation"):
            raise RuntimeError("数据库gateway不支持 upsert_event_subject_relation")

        match_result = decision.get("match_result") if isinstance(decision.get("match_result"), dict) else {}
        event_data = decision.get("event_data") if isinstance(decision.get("event_data"), dict) else {}
        audit = match_result.get("audit") if isinstance(match_result.get("audit"), dict) else {}
        result = await self.db_gateway.upsert_event_subject_relation(
            event_id=event_id_int,
            news_id=event_data.get("news_id"),
            subject_key=str(subject_key),
            subject_name=subject_name,
            confidence=decision.get("confidence", 0.8),
            evidence_json={
                "reason": decision.get("reason") or match_result.get("reason_code"),
                "audit": audit,
            },
            relation_type=decision.get("relation_type", "primary"),
            source=decision.get("source", "structured_theme_match"),
            source_trace_id=decision.get("trace_id"),
            run_id=decision.get("run_id"),
            match_reason=decision.get("reason") or match_result.get("reason_code") or "",
        )
        self.stats["mappings_created"] += 1
        logger.info(
            "   创建JYHF题材映射成功: event=%s, subject_key=%s, relation_id=%s",
            event_id_int,
            subject_key,
            result.get("id") if isinstance(result, dict) else "",
        )

    async def _execute_related_subject_mappings_safe(self, event_id: str, primary_subject_key: str, decision: Dict):
        """写入 related_matches 扩展题材映射。"""
        match_result = decision.get("match_result") if isinstance(decision.get("match_result"), dict) else {}
        related_matches = match_result.get("related_matches") or decision.get("related_matches") or []
        if not related_matches:
            return

        event_data = decision.get("event_data") if isinstance(decision.get("event_data"), dict) else {}
        event_id_int = self._extract_event_id(event_id)
        for item in related_matches:
            if not isinstance(item, dict):
                continue
            subject_key = str(item.get("subject_key") or "").strip()
            if not subject_key or subject_key == str(primary_subject_key):
                continue
            await self.db_gateway.upsert_event_subject_relation(
                event_id=event_id_int,
                news_id=event_data.get("news_id"),
                subject_key=subject_key,
                subject_name=item.get("theme_name") or item.get("subject_name"),
                confidence=item.get("confidence"),
                relation_type=item.get("relation_type") or "related",
                match_reason=item.get("reason") or decision.get("reason") or "",
                evidence_json={"related_match": item},
                source=decision.get("source", "structured_theme_match"),
                source_trace_id=decision.get("trace_id"),
                run_id=decision.get("run_id"),
            )
            self.stats["mappings_created"] += 1
    
    async def _execute_update_theme_heat_safe(self, theme_id: Any, decision: Dict):
        """安全更新题材热度"""
        try:
            heat_increment = decision.get('heat_increment', 1)
            
            if hasattr(self.db_gateway, 'increment_theme_heat'):
                await self.db_gateway.increment_theme_heat(theme_id, heat_increment)
                logger.info(f"   更新热度: theme={theme_id}, +{heat_increment}")
                
        except Exception as e:
            logger.warning(f"   更新热度失败: {e}")
    
    async def _execute_publish_theme_updated_safe(self, theme_id: Any, decision: Dict):
        """安全发布题材更新事件"""
        try:
            event_data = {
                "action": "theme_updated",
                "theme_id": theme_id,
                "decision_id": decision.get('decision_id', 'unknown'),
                "updated_by": self.consumer_name,
                "updated_at": datetime.now().isoformat()
            }
            
            await self.redis.xadd(self.theme_updates_stream, event_data, maxlen=10000)
            logger.info(f"   发布题材更新事件: {theme_id}")
            
        except Exception as e:
            logger.error(f"   发布更新事件失败: {e}")
    
    async def _execute_publish_clustering_fixed(self, decision: Dict):
        """执行发布到聚类队列决策 - 修复版"""
        logger.info("   📊 执行发布到聚类队列决策")
        
        try:
            event_data = decision.get('event_data', {})
            if not event_data:
                raise ValueError("发布到聚类队列缺少event_data")
            
            event_id = event_data.get('event_id', decision.get('event_id', 'unknown'))
            
            pending_entry = {
                "event_data": json.dumps(event_data, ensure_ascii=False),
                "published_by": self.consumer_name,
                "publish_time": datetime.now().isoformat(),
                "decision_id": decision.get('decision_id'),
                "reason": decision.get('reason', '未匹配到主题')
            }
            
            await self.redis.xadd("stream:events:pending", pending_entry, maxlen=10000)

            # realtime禁止自动建题材时，落人工复核队列（幂等）
            reason = str(decision.get("reason") or "")
            if "blocked_auto_theme_create_for_realtime" in reason:
                await self._enqueue_event_review_if_supported(decision, event_data, reason)
            
            logger.info(f"   📤 事件已发布到聚类队列: {event_id}")
            
        except Exception as e:
            logger.error(f"   发布到聚类队列失败: {e}")
            raise

    async def _enqueue_event_review_if_supported(
        self,
        decision: Dict[str, Any],
        event_data: Dict[str, Any],
        reason: str,
    ) -> None:
        try:
            if not hasattr(self.db_gateway, "enqueue_event_review"):
                logger.warning("db_gateway 不支持 enqueue_event_review，跳过落库")
                return

            event_id = event_data.get("event_id") or decision.get("event_id")
            if not event_id:
                logger.warning("缺少 event_id，无法写入人工复核队列")
                return

            theme_data = decision.get("theme_data") if isinstance(decision.get("theme_data"), dict) else {}
            proposed_theme_name = theme_data.get("name")
            confidence = decision.get("confidence")
            proposed_theme_confidence = float(confidence) if confidence is not None else None

            ok = await self.db_gateway.enqueue_event_review(
                event_id=int(event_id),
                reason=reason,
                source_channel="realtime_news",
                proposed_theme_name=proposed_theme_name,
                proposed_theme_confidence=proposed_theme_confidence,
            )
            if ok:
                logger.info("   📝 已写入人工复核队列: event_id=%s", event_id)
                self.stats["review_queue_enqueued"] += 1
            else:
                self.stats["review_queue_enqueue_failed"] += 1
        except Exception as e:
            logger.warning(f"写入人工复核队列失败（不阻断主流程）: {e}")
            self.stats["review_queue_enqueue_failed"] += 1
    
    async def _execute_clustering_result_fixed(self, decision: Dict):
        """执行聚类结果决策 - 修复版"""
        logger.info("   🔬 执行聚类结果决策")
        
        try:
            await self._execute_create_new_theme_fixed(decision)
            self.stats["clusters_processed"] += 1
            
        except Exception as e:
            logger.error(f"   处理聚类结果失败: {e}")
            raise
    
    # ==================== 辅助方法（修复版） ====================
    
    def _format_exception(self, e: Exception) -> str:
        """格式化异常信息"""
        import traceback
        try:
            tb = traceback.format_exc()
            return tb[:500]  # 限制长度
        except:
            return str(e)
    
    # ==================== 保持原有方法（向后兼容） ====================
    
    def _parse_decision_data(self, message_data: Dict) -> Optional[Dict]:
        """解析决策数据 - 保持原有逻辑"""
        try:
            decision_str = message_data.get('decision')
            if decision_str and isinstance(decision_str, str):
                try:
                    return json.loads(decision_str)
                except json.JSONDecodeError:
                    pass
            
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

    async def _should_skip_duplicate_execution(self, idempotency_key: Optional[str], message_id: str) -> bool:
        """基于 Redis NX 锁判断该决策是否重复执行。"""
        if not idempotency_key:
            return False

        lock_key = f"decision_executor:idempotency:{idempotency_key}"
        try:
            # NX: key不存在才写入，返回True表示首个执行；否则为重复
            first_seen = await self.redis.set(lock_key, message_id, ex=86400, nx=True)
            return not bool(first_seen)
        except Exception as e:
            # 幂等检查异常不阻断主流程，但记录告警便于排查
            logger.warning(f"幂等锁检查失败，按非重复继续执行: {e}")
            return False

    def _normalize_and_validate_decision_envelope(
        self,
        decision: Optional[Dict],
        message_id: str
    ) -> tuple[Optional[Dict], Optional[str]]:
        """
        v0/v1 dual-read 归一化，并校验 DecisionEnvelope v1 必填字段。
        """
        if not decision or not isinstance(decision, dict):
            return None, "ERR_CONTRACT_PARSE: 决策对象为空或类型非法"

        normalized = dict(decision)

        # dual-read: 兼容旧结构，统一归一为 payload 字段
        payload = normalized.get("payload")
        if payload is None:
            legacy_payload = {}
            for legacy_key in ["event_data", "theme_data", "data"]:
                legacy_val = normalized.get(legacy_key)
                if isinstance(legacy_val, dict):
                    legacy_payload[legacy_key] = legacy_val
            payload = legacy_payload if legacy_payload else {}
        normalized["payload"] = payload

        # v0/v1 统一版本字段
        payload_version = normalized.get("payload_version") or normalized.get("version")
        normalized["payload_version"] = payload_version or "v0"

        # 兜底字段：保证链路最小可追踪能力
        normalized.setdefault("decision_id", message_id)
        if not normalized.get("trace_id"):
            normalized["trace_id"] = f"trace_{message_id.replace('-', '_')}"

        if not normalized.get("idempotency_key"):
            payload_hash = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            normalized["idempotency_key"] = (
                f"{normalized.get('event_id', 'unknown')}:"
                f"{normalized.get('action', 'unknown')}:sha256_{payload_hash}"
            )

        required_fields = [
            "decision_id",
            "event_id",
            "action",
            "payload_version",
            "trace_id",
            "idempotency_key",
            "payload",
        ]
        missing = [
            field for field in required_fields
            if field not in normalized or normalized.get(field) in (None, "")
        ]
        if missing:
            return None, f"ERR_CONTRACT_V1_MISSING_FIELDS: {','.join(missing)}"

        if not isinstance(normalized.get("payload"), dict):
            return None, "ERR_CONTRACT_V1_INVALID_PAYLOAD: payload必须为object"

        return normalized, None
    
    def _extract_event_id(self, event_id_str: str) -> int:
        """提取整数事件ID - 保持原有逻辑"""
        try:
            if isinstance(event_id_str, int):
                return event_id_str

            if isinstance(event_id_str, float):
                return int(event_id_str)

            if isinstance(event_id_str, str) and event_id_str.isdigit():
                return int(event_id_str)
            
            import re
            numbers = re.findall(r'\d+', str(event_id_str))
            if numbers:
                return int(numbers[0])
            
            return 0
        except:
            return 0
    
    async def _move_to_dead_letter(self, message_id: str, message_data: Dict, reason: str):
        """移动消息到死信队列 - 保持原有逻辑"""
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
    
    # ==================== 向后兼容的旧方法（指向修复版） ====================
    
    async def _execute_action(self, action: str, decision: Dict, message_id: str, message_data: Dict):
        """统一路由执行（保持原有签名）"""
        return await self._execute_action_fixed(action, decision, message_id, message_data)
    
    async def _execute_create_new_theme(self, decision: Dict):
        """旧的创建新题材方法（保持向后兼容）"""
        logger.warning("⚠️  使用旧版_create_create_new_theme方法，建议使用修复版")
        return await self._execute_create_new_theme_fixed(decision)
    
    async def _execute_update_theme(self, decision: Dict):
        """旧的更新题材方法（保持向后兼容）"""
        logger.warning("⚠️  使用旧版_execute_update_theme方法，建议使用修复版")
        return await self._execute_update_theme_fixed(decision)
    
    async def _execute_publish_clustering(self, decision: Dict):
        """旧的发布聚类方法（保持向后兼容）"""
        logger.warning("⚠️  使用旧版_execute_publish_clustering方法，建议使用修复版")
        return await self._execute_publish_clustering_fixed(decision)
    
    async def _execute_clustering_result(self, decision: Dict):
        """旧的聚类结果方法（保持向后兼容）"""
        logger.warning("⚠️  使用旧版_execute_clustering_result方法，建议使用修复版")
        return await self._execute_clustering_result_fixed(decision)
    
    # ==================== 公共接口方法（保持原有） ====================
    
    async def stop(self):
        """停止决策执行器 - 保持原有方法"""
        if not self.running:
            return
        
        logger.info("🛑 停止DecisionExecutor...")
        self.running = False
        
        self.print_stats()
    
    def get_status(self) -> Dict:
        """获取执行器状态 - 保持原有方法"""
        return {
            "running": self.running,
            "stats": self.stats,
            "execution_context": self.execution_context,
            "consumer": {
                "name": self.consumer_name,
                "group": self.consumer_group
            },
            "version": "fixed_executor_v1.0"
        }
    
    def print_stats(self):
        """打印统计信息 - 优化版"""
        logger.info("\n" + "="*60)
        logger.info("📊 DecisionExecutor统计信息（修复版）")
        logger.info("="*60)
        logger.info(f"运行时间: {self.stats['started_at']}")
        logger.info(f"决策接收: {self.stats['decisions_received']}")
        logger.info(f"决策执行: {self.stats['decisions_executed']}")
        logger.info(f"决策失败: {self.stats['decisions_failed']}")
        logger.info(f"主题创建: {self.stats['themes_created']}")
        logger.info(f"主题更新: {self.stats['themes_updated']}")
        logger.info(f"映射创建: {self.stats['mappings_created']}")
        logger.info(f"聚类处理: {self.stats['clusters_processed']}")
        logger.info(f"执行错误: {self.stats['execution_errors']}")
        logger.info(f"验证错误: {self.stats['validation_errors']}")
        
        if self.stats['by_action_type']:
            logger.info("\n决策类型分布:")
            for action_type, count in self.stats['by_action_type'].items():
                logger.info(f"  {action_type}: {count}")
        
        # 错误详情（如果有）
        if self.execution_context['error_details']:
            recent_errors = self.execution_context['error_details'][-3:]  # 最近3个错误
            logger.info(f"\n最近错误 ({len(recent_errors)}个):")
            for error in recent_errors:
                logger.info(f"  {error['time']} - {error['action']}: {error['error'][:100]}")
        
        logger.info("="*60)

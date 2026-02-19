"""
数据库客户端 - 提供高级的数据库操作接口
🚀 修复：更新find_related_themes方法，不再依赖将被移除的方法
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    from database_service.interface import DatabaseManager, ThemeRecord
except ImportError:
    from .interface import DatabaseManager, ThemeRecord

logger = logging.getLogger(__name__)


class DatabaseClient:
    """
    数据库客户端 - 封装数据库操作，提供业务友好的接口
    
    🚀 修复：更新方法实现，适应新的数据库接口
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        初始化数据库客户端
        
        Args:
            db_manager: DatabaseManager实例
        """
        self._db = db_manager
        logger.info("DatabaseClient 初始化完成")
    
    # ========== 主题相关操作 ==========
    
    async def get_related_themes(self, event_data: Dict[str, Any], limit: int = 5) -> List[ThemeRecord]:
        """
        🔥 已更新：获取与事件相关的主题
        
        🚀 修复：适应新的数据库接口
        如果数据库支持增强查询，使用增强方法
        否则使用基础方法
        
        Args:
            event_data: 事件数据
            limit: 最大返回数量
            
        Returns:
            相关主题列表
        """
        try:
            # 🚀 首先尝试使用数据库的增强方法（如果可用）
            if hasattr(self._db, 'find_related_themes'):
                logger.debug(f"使用数据库的find_related_themes方法")
                return await self._db.find_related_themes(event_data, limit)
            
            # 🚀 后备方案：获取所有活跃主题，让上层AI处理匹配
            logger.debug(f"使用get_all_active_themes方法，让AI处理匹配")
            all_themes = await self._db.get_all_active_themes(limit * 3)  # 多获取一些
            
            # 简单过滤：只返回活跃主题
            active_themes = []
            for theme in all_themes:
                if theme.lifecycle_stage != 'archived' and theme.heat_score > 0:
                    active_themes.append(theme)
                
                if len(active_themes) >= limit:
                    break
            
            logger.info(f"获取到 {len(active_themes)} 个活跃主题用于AI分析")
            return active_themes
            
        except Exception as e:
            logger.error(f"获取相关主题失败: {e}")
            # 返回空列表，让上层处理
            return []
    
    async def get_enriched_themes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取增强的主题信息（新增方法）
        
        🚀 返回包含完整上下文的主题信息，用于AI分析
        包含关联事件、关键实体、时间范围等
        """
        try:
            # 🚀 尝试使用数据库的增强方法
            if hasattr(self._db, 'get_all_active_themes_with_context'):
                themes = await self._db.get_all_active_themes_with_context(limit)
                logger.info(f"使用增强方法获取到 {len(themes)} 个带上下文主题")
                return themes
            
            # 🚀 如果数据库支持get_enriched_theme，逐个获取
            if hasattr(self._db, 'get_enriched_theme'):
                all_themes = await self._db.get_all_active_themes(limit)
                enriched_themes = []
                
                for theme in all_themes:
                    enriched = await self._db.get_enriched_theme(theme.id)
                    if enriched:
                        enriched_themes.append(enriched)
                
                logger.info(f"逐个获取到 {len(enriched_themes)} 个增强主题")
                return enriched_themes
            
            # 🚀 后备方案：获取基础主题并手动增强
            logger.warning("数据库不支持增强主题查询，使用基础数据")
            themes = await self._db.get_all_active_themes(limit)
            
            # 转换为字典格式
            result = []
            for theme in themes:
                theme_dict = self._theme_to_dict(theme)
                # 添加基本的AI描述
                theme_dict['ai_description'] = f"关于{theme_dict.get('name')}的主题"
                result.append(theme_dict)
            
            return result
            
        except Exception as e:
            logger.error(f"获取增强主题失败: {e}")
            return []
    
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        try:
            return await self._db.get_theme_by_name(name)
        except Exception as e:
            logger.error(f"根据名称获取主题失败: {name}, 错误: {e}")
            return None
    
    async def create_theme(self, name: str, **kwargs) -> Optional[ThemeRecord]:
        """创建新主题"""
        try:
            return await self._db.create_theme(name, **kwargs)
        except Exception as e:
            logger.error(f"创建主题失败: {name}, 错误: {e}")
            return None
    
    # ========== 事件-主题关联操作 ==========
    
    async def create_event_theme_relation(self, 
                                         event_id: int, 
                                         theme_id: int,
                                         **kwargs) -> bool:
        """创建事件-主题关联"""
        try:
            relation = await self._db.create_event_theme_relation(
                event_id=event_id,
                theme_id=theme_id,
                **kwargs
            )
            return relation is not None
        except Exception as e:
            logger.error(f"创建事件-主题关联失败: event={event_id}, theme={theme_id}, 错误: {e}")
            return False
    
    async def get_event_themes(self, event_id: int) -> List[Dict[str, Any]]:
        """获取事件关联的主题"""
        try:
            relations = await self._db.get_event_themes(event_id)
            
            # 转换为包含主题详情的格式
            result = []
            for relation in relations:
                theme = await self._db.get_theme(relation.theme_id)
                if theme:
                    result.append({
                        'theme': self._theme_to_dict(theme),
                        'relation': {
                            'confidence': relation.confidence,
                            'evidence': relation.evidence
                        }
                    })
            
            return result
        except Exception as e:
            logger.error(f"获取事件主题关联失败: {event_id}, 错误: {e}")
            return []
    
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        """获取主题关联的事件ID"""
        try:
            return await self._db.get_theme_events(theme_id, limit)
        except Exception as e:
            logger.error(f"获取主题事件关联失败: {theme_id}, 错误: {e}")
            return []
    
    # ========== 事件状态管理 ==========
    
    async def mark_event_processed(self, event_id: int) -> bool:
        """标记事件已处理"""
        try:
            await self._db.mark_event_processed(event_id)
            return True
        except Exception as e:
            logger.error(f"标记事件已处理失败: {event_id}, 错误: {e}")
            return False
    
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件"""
        try:
            return await self._db.get_unprocessed_events(limit)
        except Exception as e:
            logger.error(f"获取未处理事件失败: {e}")
            return []
    
    # ========== 统计与监控 ==========
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            return await self._db.get_stats()
        except Exception as e:
            logger.error(f"获取数据库统计失败: {e}")
            return {}
    
    # ========== 辅助方法 ==========
    
    def _theme_to_dict(self, theme: ThemeRecord) -> Dict[str, Any]:
        """转换主题记录为字典"""
        if hasattr(theme, 'to_dict'):
            return theme.to_dict()
        
        # 兼容处理
        result = {}
        for attr in ['id', 'name', 'description', 'keywords', 'event_count', 
                    'heat_score', 'discovery_confidence', 'created_at']:
            if hasattr(theme, attr):
                value = getattr(theme, attr)
                # 处理datetime对象
                if isinstance(value, datetime):
                    value = value.isoformat()
                result[attr] = value
        
        return result
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            return await self._db.health_check()
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False

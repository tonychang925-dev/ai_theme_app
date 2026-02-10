"""
事件-主题映射模型
修复导入问题
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 修复：移除对 get_conn 的直接依赖
# 改为使用 ThemeDatabase 类

async def save_event_theme(event_id: int, theme_id: int, confidence: float, db_manager=None) -> bool:
    """
    保存事件-主题映射
    
    Args:
        event_id: 事件ID
        theme_id: 主题ID
        confidence: 置信度
        db_manager: 数据库管理器实例
        
    Returns:
        是否成功
    """
    if not db_manager:
        logger.warning("没有数据库管理器，跳过保存")
        return False
    
    try:
        # 使用新的数据库接口
        success = await db_manager.save_event_theme_mapping(event_id, theme_id, confidence)
        
        if success:
            logger.info(f"✅ 保存映射: event={event_id}, theme={theme_id}, conf={confidence:.2f}")
        else:
            logger.warning(f"⚠️  保存映射失败")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ 保存映射异常: {e}")
        return False

async def get_event_themes(event_id: int, db_manager=None) -> List[Dict[str, Any]]:
    """
    获取事件相关的主题
    
    Args:
        event_id: 事件ID
        db_manager: 数据库管理器实例
        
    Returns:
        主题列表
    """
    if not db_manager:
        return []
    
    try:
        query = """
            SELECT 
                etm.*,
                tm.name as theme_name,
                tm.status as theme_status
            FROM event_theme_map etm
            JOIN theme_master tm ON etm.theme_id = tm.id
            WHERE etm.event_id = $1
            ORDER BY etm.confidence DESC
        """
        
        results = await db_manager.execute_query(query, event_id)
        return [dict(row) for row in results]
        
    except Exception as e:
        logger.error(f"❌ 获取事件主题失败: {e}")
        return []

async def get_theme_events(theme_id: int, db_manager=None) -> List[Dict[str, Any]]:
    """
    获取主题相关的事件
    
    Args:
        theme_id: 主题ID
        db_manager: 数据库管理器实例
        
    Returns:
        事件列表
    """
    if not db_manager:
        return []
    
    try:
        query = """
            SELECT 
                etm.*,
                ne.event_type,
                ne.summary,
                ne.created_at as event_time
            FROM event_theme_map etm
            JOIN news_event ne ON etm.event_id = ne.id
            WHERE etm.theme_id = $1
            ORDER BY ne.created_at DESC
            LIMIT 50
        """
        
        results = await db_manager.execute_query(query, theme_id)
        return [dict(row) for row in results]
        
    except Exception as e:
        logger.error(f"❌ 获取主题事件失败: {e}")
        return []

# 兼容性函数
def get_conn():
    """兼容性函数 - 返回一个数据库管理器"""
    from theme_service.database import ThemeDatabase
    from theme_service.config import settings
    
    return ThemeDatabase(settings.DATABASE_URL)

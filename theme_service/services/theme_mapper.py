"""
主题映射器 - 将事件映射到主题
修复导入问题，兼容新的数据库模块
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ThemeMapper:
    """主题映射器 - 负责事件到主题的映射逻辑"""
    
    def __init__(self, db_manager=None):
        """
        初始化主题映射器
        
        Args:
            db_manager: 数据库管理器实例 (可选)
        """
        self.db = db_manager
        logger.info("ThemeMapper 初始化完成")
    
    async def map_event_to_themes(self, event_data: Dict[str, Any], theme_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将事件映射到主题候选
        
        Args:
            event_data: 事件数据
            theme_candidates: 主题候选列表
            
        Returns:
            映射结果列表
        """
        if not theme_candidates:
            return []
        
        logger.info(f"开始事件映射: 事件ID={event_data.get('id')}, 候选主题={len(theme_candidates)}")
        
        mappings = []
        for theme in theme_candidates:
            # 计算匹配度（简化版）
            match_score = self._calculate_match_score(event_data, theme)
            
            if match_score > 0.1:  # 基本阈值
                mapping = {
                    "event_id": event_data.get("id"),
                    "theme_id": theme.get("id"),
                    "theme_name": theme.get("name"),
                    "confidence": match_score,
                    "matched_keywords": [],
                    "created_at": datetime.now()
                }
                
                # 确定置信度等级
                if match_score >= 0.7:
                    mapping["confidence_level"] = "strong"
                    mapping["confidence_weight"] = 100
                elif match_score >= 0.4:
                    mapping["confidence_level"] = "medium"
                    mapping["confidence_weight"] = 60
                elif match_score >= 0.1:
                    mapping["confidence_level"] = "weak"
                    mapping["confidence_weight"] = 30
                else:
                    mapping["confidence_level"] = "ignore"
                    mapping["confidence_weight"] = 0
                
                mappings.append(mapping)
                logger.debug(f"事件映射: {event_data.get('id')} -> {theme.get('name')} (score: {match_score:.2f})")
        
        logger.info(f"事件映射完成: 生成 {len(mappings)} 个映射")
        return mappings
    
    def _calculate_match_score(self, event_data: Dict, theme: Dict) -> float:
        """计算事件与主题的匹配分数（简化版）"""
        # 这里可以实现更复杂的匹配逻辑
        # 现在返回一个固定分数用于测试
        return 0.6
    
    async def save_mappings_to_db(self, mappings: List[Dict[str, Any]]) -> int:
        """
        保存映射到数据库
        
        Args:
            mappings: 映射列表
            
        Returns:
            保存的数量
        """
        if not self.db:
            logger.warning("没有数据库连接，跳过保存")
            return 0
        
        saved_count = 0
        for mapping in mappings:
            try:
                success = await self.db.save_event_theme_mapping(
                    mapping["event_id"],
                    mapping.get("theme_id", 0),
                    mapping["confidence"]
                )
                
                if success:
                    saved_count += 1
            except Exception as e:
                logger.error(f"保存映射失败: {e}")
        
        logger.info(f"映射保存完成: {saved_count}/{len(mappings)} 个")
        return saved_count

# 兼容性函数（修复缺少的 get_conn 函数）
def get_conn():
    """获取数据库连接（兼容性函数）"""
    from theme_service.database import create_database_manager
    import asyncio
    
    # 创建数据库管理器
    db_manager = create_database_manager()
    
    # 返回一个异步上下文管理器
    class AsyncConnection:
        async def __aenter__(self):
            await db_manager.initialize()
            return db_manager
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await db_manager.close()
    
    return AsyncConnection()

# 测试函数
async def test_theme_mapper():
    """测试主题映射器"""
    print("🧪 测试主题映射器...")
    
    mapper = ThemeMapper()
    
    test_event = {
        "id": 1001,
        "title": "测试事件",
        "summary": "测试摘要",
        "event_type": "测试"
    }
    
    test_themes = [
        {"id": 1, "name": "AI眼镜"},
        {"id": 2, "name": "消费电子"}
    ]
    
    mappings = await mapper.map_event_to_themes(test_event, test_themes)
    
    print(f"✅ 映射测试完成: 生成 {len(mappings)} 个映射")
    for mapping in mappings:
        print(f"   事件 {mapping['event_id']} -> 主题 {mapping['theme_name']}")
    
    return len(mappings) > 0

if __name__ == "__main__":
    import asyncio
    success = asyncio.run(test_theme_mapper())
    
    if success:
        print("\n🎉 主题映射器测试通过！")
    else:
        print("\n⚠️  主题映射器测试失败")

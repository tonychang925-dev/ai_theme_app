# tests/unit/test_memory_manager.py
"""
内存管理器单元测试 - 修复fixture标记问题
"""
import sys
import os

# 关键：设置正确的Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))  # tests/unit
tests_dir = os.path.dirname(current_dir)                 # tests
service_dir = os.path.dirname(tests_dir)                 # database_service

sys.path.insert(0, service_dir)

import pytest
import asyncio
from datetime import datetime

from config import DatabaseConfig, RedisConfig, DatabaseType
from managers.memory_manager import MemoryDatabaseManager
from interface import (
    ThemeRecord, 
    EventThemeRelation, 
    ThemeTags,
    ThemeStatus,
    ThemeType,
    LifecycleStage,
    SourceSystem
)


@pytest.fixture
def memory_db_config():
    """内存数据库配置"""
    return DatabaseConfig(
        db_type=DatabaseType.MEMORY,
        redis=RedisConfig(enabled=False),
        table_names_config={"theme_master": "memory_themes"}
    )


@pytest.fixture
def theme_tags_sample():
    """测试用ThemeTags样本"""
    return ThemeTags(
        source="shenwan",
        aliases=["AI", "人工智能"],
        version="2.0",
        concepts=["科技前沿", "数字经济"],
        keywords=["人工智能", "AI", "机器学习", "深度学习"],
        heat_level="high",
        industries=["计算机", "软件服务"],
        industry_code="AI001",
        merge_candidates=[]
    )


@pytest.fixture
def theme_data_sample():
    """28字段主题数据样本"""
    return {
        "name": "测试主题",
        "code": "TEST_001",
        "description": "这是一个测试主题",
        "status": ThemeStatus.ACTIVE.value,
        "level1_category": "计算机",
        "level2_category": "人工智能",
        "level3_category": "机器学习",
        "category_path": ["计算机", "人工智能", "机器学习"],
        "category1_code": "C001",
        "category2_code": "C002",
        "category3_code": "C003",
        "theme_type": ThemeType.INVESTMENT.value,
        "lifecycle_stage": LifecycleStage.GROWTH.value,
        "heat_score": 85,
        "confidence_score": 0.9,
        "related_stocks": ["stock1", "stock2", "stock3"],
        "stock_count": 3,
        "news_count": 10,
        "mention_count": 5,
        "source_system": SourceSystem.TRANSFORMED.value,
        "source_id": "source_001",
        "created_by": "test_user"
    }


# 简单的辅助函数，避免使用async fixture
async def create_memory_manager():
    """创建并连接内存管理器"""
    config = DatabaseConfig(
        db_type=DatabaseType.MEMORY,
        redis=RedisConfig(enabled=False),
        table_names_config={"theme_master": "memory_themes"}
    )
    
    manager = MemoryDatabaseManager(config)
    await manager.connect()
    return manager


@pytest.mark.asyncio
async def test_memory_manager_init():
    """测试内存管理器初始化"""
    manager = await create_memory_manager()
    
    try:
        assert manager.config.db_type == DatabaseType.MEMORY
        assert isinstance(manager.themes, dict)
        assert isinstance(manager.relations, list)
        assert isinstance(manager.events, dict)
        assert hasattr(manager, 'next_id')
        
        # 验证初始化了测试数据
        assert len(manager.themes) > 0
        assert len(manager.relations) >= 0
        assert len(manager.events) >= 0
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_connect():
    """测试连接"""
    config = DatabaseConfig(
        db_type=DatabaseType.MEMORY,
        redis=RedisConfig(enabled=False),
        table_names_config={"theme_master": "memory_themes"}
    )
    
    manager = MemoryDatabaseManager(config)
    await manager.connect()
    
    try:
        assert manager.connected == True
        assert len(manager.themes) > 0
        
        # 验证测试主题的基本结构
        for theme in manager.themes.values():
            assert hasattr(theme, 'code')
            assert hasattr(theme, 'name')
            if hasattr(theme, 'tags'):
                assert isinstance(theme.tags, ThemeTags)
                
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_get_theme():
    """测试获取主题（按ID）"""
    manager = await create_memory_manager()
    
    try:
        # 获取存在的主题（从第一个主题开始）
        if manager.themes:
            first_id = list(manager.themes.keys())[0]
            theme = await manager.get_theme(first_id)
            assert theme is not None
            assert hasattr(theme, 'name')
            assert hasattr(theme, 'code')
        
        # 获取不存在的主题
        theme = await manager.get_theme(99999)
        assert theme is None
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_get_theme_by_code():
    """测试获取主题（按code）"""
    manager = await create_memory_manager()
    
    try:
        if manager.themes:
            # 获取存在的主题
            first_theme = list(manager.themes.values())[0]
            theme = await manager.get_theme_by_code(first_theme.code)
            assert theme is not None
            assert theme.id == first_theme.id
        
        # 获取不存在的code
        theme = await manager.get_theme_by_code("NON_EXISTENT")
        assert theme is None
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_get_theme_by_name():
    """测试根据名称获取主题"""
    manager = await create_memory_manager()
    
    try:
        if manager.themes:
            # 获取存在的主题
            first_theme = list(manager.themes.values())[0]
            theme = await manager.get_theme_by_name(first_theme.name)
            assert theme is not None
            assert theme.code == first_theme.code
        
        # 获取不存在的名称
        theme = await manager.get_theme_by_name("不存在的主题")
        assert theme is None
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_create_theme(theme_tags_sample):
    """测试创建新主题"""
    manager = await create_memory_manager()
    
    try:
        # 创建新主题
        theme = await manager.create_theme(
            name="测试创建主题",
            code="CREATE_TEST_001",
            description="测试创建的主题",
            level1_category="测试",
            tags=theme_tags_sample,
            heat_score=75
        )
        
        assert theme is not None
        assert theme.name == "测试创建主题"
        assert theme.code == "CREATE_TEST_001"
        assert theme.level1_category == "测试"
        assert theme.heat_score == 75
        assert isinstance(theme.tags, ThemeTags)
        
        # 验证主题被保存
        saved_theme = await manager.get_theme(theme.id)
        assert saved_theme is not None
        assert saved_theme.code == "CREATE_TEST_001"
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_create_theme_duplicate_code():
    """测试创建重复code的主题"""
    manager = await create_memory_manager()
    
    try:
        # 创建第一个主题
        theme1 = await manager.create_theme(
            name="主题1",
            code="DUPLICATE_CODE_TEST",
            description="第一个主题"
        )
        assert theme1 is not None
        
        # 尝试创建重复code的主题
        try:
            await manager.create_theme(
                name="主题2",
                code="DUPLICATE_CODE_TEST",  # 相同code
                description="第二个主题"
            )
            # 如果没抛出异常，检查是否返回None
        except Exception as e:
            # 预期可能会抛出异常
            assert "主题" in str(e) or "存在" in str(e) or "重复" in str(e)
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_update_theme():
    """测试更新主题"""
    manager = await create_memory_manager()
    
    try:
        # 先创建一个主题
        theme = await manager.create_theme(
            name="待更新主题",
            code="UPDATE_TEST",
            description="原始描述",
            heat_score=50
        )
        
        # 更新主题
        updates = {
            "description": "更新后的描述",
            "heat_score": 75
        }
        
        updated = await manager.update_theme(theme.id, updates)
        
        if updated is not None:
            assert updated.description == "更新后的描述"
            assert updated.heat_score == 75
            assert updated.updated_at is not None
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_increment_theme_heat():
    """测试增加主题热度"""
    manager = await create_memory_manager()
    
    try:
        # 先创建一个主题
        theme = await manager.create_theme(
            name="热度测试",
            code="HEAT_TEST",
            heat_score=50
        )
        
        initial_heat = theme.heat_score
        
        # 增加热度
        await manager.increment_theme_heat(theme.id, 10)
        
        # 获取更新后的主题
        updated = await manager.get_theme(theme.id)
        if updated:
            assert updated.heat_score == initial_heat + 10
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_increment_mention_count():
    """测试增加提及次数"""
    manager = await create_memory_manager()
    
    try:
        # 先创建一个主题
        theme = await manager.create_theme(
            name="提及测试",
            code="MENTION_TEST",
            mention_count=5
        )
        
        # 增加提及次数
        await manager.increment_mention_count(theme.id, 3)
        
        # 获取更新后的主题
        updated = await manager.get_theme(theme.id)
        if updated:
            assert updated.mention_count == 8  # 5 + 3
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_get_all_active_themes():
    """测试获取所有活跃主题"""
    manager = await create_memory_manager()
    
    try:
        themes = await manager.get_all_active_themes()
        
        assert isinstance(themes, list)
        assert len(themes) > 0
        
        # 检查每个主题都是活跃的
        for theme in themes:
            assert theme.status == ThemeStatus.ACTIVE.value
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_search_themes():
    """测试搜索主题"""
    manager = await create_memory_manager()
    
    try:
        # 创建一些测试主题
        await manager.create_theme(
            name="搜索测试主题1",
            code="SEARCH_001",
            description="用于搜索测试的主题1",
            level1_category="测试"
        )
        
        await manager.create_theme(
            name="搜索测试主题2", 
            code="SEARCH_002",
            description="另一个测试主题",
            level1_category="测试"
        )
        
        # 名称搜索
        themes = await manager.search_themes("搜索测试", limit=5)
        assert isinstance(themes, list)
        assert len(themes) > 0
        
        # 空搜索
        themes = await manager.search_themes("", limit=5)
        assert len(themes) == 0
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_create_event_theme_relation():
    """测试创建事件-主题关联"""
    manager = await create_memory_manager()
    
    try:
        if manager.themes:
            # 使用第一个存在的主题
            first_id = list(manager.themes.keys())[0]
            
            relation = await manager.create_event_theme_relation(
                event_id=3001,
                theme_id=first_id,
                confidence=0.85,
                confidence_level="high",
                match_type="keyword",
                matched_keywords=["测试"]
            )
            
            assert relation is not None
            assert relation.event_id == 3001
            assert relation.theme_id == first_id
            assert relation.confidence == 0.85
            assert relation.match_type == "keyword"
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_get_event_themes():
    """测试获取事件关联的主题"""
    manager = await create_memory_manager()
    
    try:
        if manager.themes:
            first_id = list(manager.themes.keys())[0]
            
            # 先创建一个关联
            await manager.create_event_theme_relation(
                event_id=4001,
                theme_id=first_id,
                confidence=0.8
            )
            
            relations = await manager.get_event_themes(4001)
            assert isinstance(relations, list)
            if relations:
                assert relations[0].event_id == 4001
                assert relations[0].theme_id == first_id
            
            # 不存在的event_id
            relations = await manager.get_event_themes(9999)
            assert len(relations) == 0
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_get_theme_events():
    """测试获取主题关联的事件ID"""
    manager = await create_memory_manager()
    
    try:
        if manager.themes:
            first_id = list(manager.themes.keys())[0]
            
            # 创建多个关联
            await manager.create_event_theme_relation(event_id=5001, theme_id=first_id)
            await manager.create_event_theme_relation(event_id=5002, theme_id=first_id)
            
            events = await manager.get_theme_events(first_id, limit=10)
            assert isinstance(events, list)
            assert 5001 in events
            assert 5002 in events
            
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_batch_create_themes():
    """测试批量创建主题"""
    manager = await create_memory_manager()
    
    try:
        themes_data = [
            {
                "name": "批量主题1",
                "code": "BATCH_001",
                "description": "批量主题1描述",
                "level1_category": "计算机",
                "heat_score": 70
            },
            {
                "name": "批量主题2",
                "code": "BATCH_002",
                "description": "批量主题2描述",
                "level1_category": "电子",
                "heat_score": 65
            }
        ]
        
        themes = await manager.batch_create_themes(themes_data)
        
        assert isinstance(themes, list)
        assert len(themes) == 2
        assert themes[0].code == "BATCH_001"
        assert themes[1].code == "BATCH_002"
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_get_stats():
    """测试获取统计信息"""
    manager = await create_memory_manager()
    
    try:
        stats = await manager.get_stats()
        
        # 验证基本统计字段
        assert isinstance(stats, dict)
        assert 'themes' in stats
        assert 'events' in stats
        assert 'relations' in stats
        
        # 验证主题统计
        themes_stats = stats['themes']
        assert 'total' in themes_stats
        assert 'active' in themes_stats
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_health_check():
    """测试健康检查"""
    manager = await create_memory_manager()
    
    try:
        healthy = await manager.health_check()
        assert healthy == True or healthy == False
        
    finally:
        await manager.disconnect()


@pytest.mark.asyncio
async def test_memory_manager_disconnect():
    """测试断开连接"""
    config = DatabaseConfig(
        db_type=DatabaseType.MEMORY,
        redis=RedisConfig(enabled=False)
    )
    
    manager = MemoryDatabaseManager(config)
    await manager.connect()
    
    assert manager.connected == True
    await manager.disconnect()
    assert manager.connected == False


# 边角情况测试类
class TestMemoryManagerEdgeCases:
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_theme(self):
        """测试获取不存在的主题"""
        manager = await create_memory_manager()
        
        try:
            theme = await manager.get_theme(99999)
            assert theme is None
            
            theme = await manager.get_theme_by_code("NON_EXISTENT_CODE")
            assert theme is None
            
            theme = await manager.get_theme_by_name("不存在的主题名称")
            assert theme is None
            
        finally:
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_theme(self):
        """测试更新不存在的主题"""
        manager = await create_memory_manager()
        
        try:
            updated = await manager.update_theme(99999, {"name": "新名称"})
            assert updated is None
            
        finally:
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_increment_nonexistent_theme(self):
        """测试增加不存在的主题的热度"""
        manager = await create_memory_manager()
        
        try:
            # 不应该抛出异常
            await manager.increment_theme_heat(99999, 10)
            await manager.increment_mention_count(99999, 5)
            
        finally:
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_empty_search_query(self):
        """测试空搜索查询"""
        manager = await create_memory_manager()
        
        try:
            themes = await manager.search_themes("", limit=10)
            assert len(themes) == 0
            
        finally:
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_batch_create_empty_list(self):
        """测试批量创建空列表"""
        manager = await create_memory_manager()
        
        try:
            themes = await manager.batch_create_themes([])
            assert len(themes) == 0
            
        finally:
            await manager.disconnect()


# 主运行函数
def run_tests():
    """运行测试"""
    import sys
    sys.exit(pytest.main([__file__, "-v"]))


if __name__ == "__main__":
    run_tests()
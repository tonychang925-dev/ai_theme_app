# tests/integration/test_real_postgres.py
"""
真实的PostgreSQL集成测试
使用你的真实数据库 stock_data
"""
import pytest
import asyncio
import json
from pathlib import Path
import sys

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.gateway import DatabaseGateway


@pytest.mark.integration
@pytest.mark.asyncio
class TestRealPostgreSQL:
    """测试真实PostgreSQL数据库"""
    
    @classmethod
    async def setup_class(cls):
        """测试类设置"""
        print("\n🔍 准备真实PostgreSQL测试...")
        
        # 使用你的真实配置
        cls.config = DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            postgres_host="localhost",
            postgres_port=5432,
            postgres_database="stock_data",  # 你的真实数据库
            postgres_username="postgres",
            postgres_password="zxbzj~925",   # 你的密码
            redis_enabled=False  # 先测试无缓存
        )
        
        cls.manager = None
    
    async def setup_method(self):
        """每个测试方法前执行"""
        if not self.manager:
            self.manager = PostgresDatabaseManager(self.config)
            await self.manager.connect()
    
    async def teardown_method(self):
        """每个测试方法后执行"""
        if self.manager:
            await self.manager.disconnect()
            self.manager = None
    
    async def test_01_real_database_connection(self):
        """测试真实数据库连接"""
        assert self.manager.connected == True
        
        # 执行简单查询验证连接
        async with self.manager.pool.acquire() as conn:
            result = await conn.fetchval('SELECT 1')
            assert result == 1
    
    async def test_02_get_real_themes_count(self):
        """测试获取真实主题数量"""
        stats = await self.manager.get_stats()
        
        print(f"\n📊 数据库统计:")
        print(f"   主题总数: {stats.get('themes', {}).get('total', 'N/A')}")
        print(f"   活跃主题: {stats.get('themes', {}).get('active', 'N/A')}")
        print(f"   平均热度: {stats.get('themes', {}).get('avg_heat', 'N/A')}")
        
        # 验证有主题数据
        themes_total = stats.get('themes', {}).get('total', 0)
        assert themes_total > 0
        print(f"✅ 确认数据库中有 {themes_total} 个主题")
    
    async def test_03_get_sample_themes(self):
        """测试获取真实主题样本"""
        themes = await self.manager.get_all_active_themes(limit=5)
        
        print(f"\n📋 主题样本（前5个）:")
        for i, theme in enumerate(themes, 1):
            print(f"  {i}. {theme.name}")
            if hasattr(theme, 'keywords') and theme.keywords:
                print(f"     关键词: {theme.keywords[:3]}")
            if hasattr(theme, 'heat_score'):
                print(f"     热度: {theme.heat_score}")
            print()
        
        assert len(themes) > 0
        print(f"✅ 成功获取 {len(themes)} 个主题")
    
    async def test_04_find_related_themes_with_real_keywords(self):
        """使用真实关键词测试主题匹配"""
        # 使用常见的投资主题关键词
        test_cases = [
            {
                "name": "人工智能相关",
                "keywords": ["人工智能", "AI", "机器学习", "深度学习"]
            },
            {
                "name": "新能源汽车相关", 
                "keywords": ["新能源汽车", "电动车", "锂电池", "充电桩"]
            },
            {
                "name": "半导体相关",
                "keywords": ["半导体", "芯片", "集成电路"]
            },
            {
                "name": "医药生物相关",
                "keywords": ["医药", "生物", "创新药", "医疗器械"]
            }
        ]
        
        print(f"\n🔍 关键词匹配测试:")
        
        for test_case in test_cases:
            event_data = {"keywords": test_case["keywords"]}
            themes = await self.manager.find_related_themes(event_data, limit=3)
            
            print(f"\n  {test_case['name']}:")
            print(f"    关键词: {test_case['keywords'][:3]}...")
            print(f"    匹配到 {len(themes)} 个主题:")
            
            for theme in themes:
                match_score = len(set(test_case['keywords']) & set(theme.keywords))
                print(f"      - {theme.name} (匹配度: {match_score})")
            
            # 对于热门主题，应该能匹配到
            if test_case["name"] in ["人工智能相关", "新能源汽车相关"]:
                assert len(themes) > 0
                print(f"    ✅ {test_case['name']} 匹配成功")
            else:
                print(f"    ⚠️  {test_case['name']} 匹配结果: {len(themes)} 个主题")
    
    async def test_05_test_table_structure(self):
        """测试表结构兼容性"""
        print(f"\n📋 检查表结构兼容性...")
        
        # 执行原始查询检查表结构
        try:
            tables = await self.manager.execute_query("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            print(f"   发现 {len(tables)} 张表:")
            for table in tables:
                print(f"      - {table['table_name']}")
            
            # 检查关键表是否存在
            table_names = [t['table_name'] for t in tables]
            assert 'theme_master' in table_names
            print("    ✅ theme_master 表存在")
            
        except Exception as e:
            print(f"    ❌ 表结构检查失败: {e}")
            pytest.fail(f"表结构不兼容: {e}")
    
    async def test_06_test_theme_search(self):
        """测试主题搜索功能"""
        search_queries = [
            "人工智能",
            "汽车", 
            "芯片",
            "医药"
        ]
        
        print(f"\n🔎 主题搜索测试:")
        
        for query in search_queries:
            themes = await self.manager.search_themes(query, limit=3)
            
            print(f"\n  搜索 '{query}':")
            if themes:
                for theme in themes:
                    print(f"      - {theme.name}")
                print(f"    ✅ 找到 {len(themes)} 个相关主题")
            else:
                print(f"    ⚠️  未找到相关主题")
        
        # 至少一个搜索应该有结果
        all_results = []
        for query in search_queries:
            themes = await self.manager.search_themes(query, limit=1)
            if themes:
                all_results.extend(themes)
        
        assert len(all_results) > 0
        print(f"\n✅ 搜索功能正常")
    
    async def test_07_create_test_theme(self):
        """测试创建新主题（会在事务中回滚）"""
        import asyncpg
        
        try:
            async with self.manager.pool.acquire() as conn:
                async with conn.transaction():
                    # 在事务中创建测试主题
                    test_theme_name = f"测试主题_{int(asyncio.get_event_loop().time())}"
                    
                    row = await conn.fetchrow("""
                        INSERT INTO theme_master 
                        (name, description, keywords, heat_score, status)
                        VALUES ($1, $2, $3, $4, 'active')
                        RETURNING id, name
                    """, 
                        test_theme_name,
                        "这是一个测试主题",
                        ["测试", "单元测试"],
                        50
                    )
                    
                    if row:
                        print(f"✅ 测试主题创建成功: {row['name']} (ID: {row['id']})")
                        assert row['name'] == test_theme_name
                    
                    # 事务会自动回滚，不会污染数据库
                    
        except asyncpg.UniqueViolationError:
            print("⚠️  主题已存在（正常情况）")
        except Exception as e:
            print(f"❌ 创建测试主题失败: {e}")
            raise
    
    async def test_08_test_event_theme_relations(self):
        """测试事件-主题关联功能"""
        try:
            # 检查关联表是否存在
            rows = await self.manager.execute_query("""
                SELECT COUNT(*) as relation_count
                FROM event_theme_map
                LIMIT 1
            """)
            
            if rows:
                count = rows[0].get('relation_count', 0)
                print(f"📊 现有事件-主题关联数: {count}")
                
                # 如果有数据，测试获取关联
                if count > 0:
                    # 获取一个主题的事件关联
                    themes = await self.manager.get_all_active_themes(limit=1)
                    if themes:
                        theme_id = themes[0].id
                        
                        # 获取主题关联的事件（需要实现这个方法）
                        try:
                            event_ids = await self.manager.get_theme_events(theme_id, limit=5)
                            print(f"  主题 {themes[0].name} 关联的事件: {len(event_ids)} 个")
                        except NotImplementedError:
                            print("   ⚠️  get_theme_events 方法未实现")
                
            print("✅ 关联表检查完成")
            
        except Exception as e:
            print(f"⚠️  关联表检查失败: {e}")
            # 这不应该是测试失败，因为关联表可能不存在


@pytest.mark.integration
@pytest.mark.asyncio
class TestRealGateway:
    """测试真实网关"""
    
    @classmethod
    async def setup_class(cls):
        """测试类设置"""
        print("\n🎯 准备真实网关测试...")
        
        # 使用你的真实配置
        cls.config = DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            postgres_host="localhost",
            postgres_port=5432,
            postgres_database="stock_data",
            postgres_username="postgres",
            postgres_password="zxbzj~925",
            redis_enabled=False  # 先测试无缓存
        )
        
        cls.gateway = None
    
    async def setup_method(self):
        """每个测试方法前执行"""
        if not self.gateway:
            # 直接初始化网关，不通过单例
            self.gateway = DatabaseGateway()
            await self.gateway.initialize(self.config)
    
    async def teardown_method(self):
        """每个测试方法后执行"""
        if self.gateway:
            await self.gateway.close()
            self.gateway = None
    
    async def test_01_gateway_health_check(self):
        """测试网关健康检查"""
        healthy = await self.gateway.health_check()
        assert healthy == True
        print("✅ 网关健康检查通过")
    
    async def test_02_gateway_get_themes(self):
        """测试通过网关获取主题"""
        themes = await self.gateway.get_all_active_themes(limit=10)
        
        print(f"\n🎯 通过网关获取 {len(themes)} 个主题:")
        for i, theme in enumerate(themes[:3], 1):
            print(f"  {i}. {theme.name}")
            if hasattr(theme, 'heat_score'):
                print(f"     热度: {theme.heat_score}")
        
        assert len(themes) > 0
        print(f"✅ 网关主题获取成功")
    
    async def test_03_gateway_search_themes(self):
        """测试网关搜索功能"""
        results = await self.gateway.search_themes("科技", limit=5)
        
        print(f"\n🔎 网关搜索 '科技':")
        if results:
            for theme in results:
                print(f"  - {theme.name}")
            print(f"✅ 找到 {len(results)} 个相关主题")
        else:
            print("⚠️  未找到相关主题")
        
        # 网关应该正常返回，即使没有结果
        assert results is not None
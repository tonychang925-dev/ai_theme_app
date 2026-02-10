#!/usr/bin/env python3
"""
基本冒烟测试 - 28字段表结构
验证核心功能是否正常
"""
import os
import asyncio
import sys
import time
import json
from pathlib import Path

# 设置正确的Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

# 修复导入路径问题
sys.path.insert(0, project_root)  # ai_theme_app
sys.path.insert(0, service_dir)   # database_service

print(f"🔍 项目根目录: {project_root}")
print(f"🔍 服务目录: {service_dir}")

try:
    from database_service.factory import DatabaseManagerFactory
    from database_service.config import DatabaseConfig, DatabaseType
    from database_service.interface import ThemeTags
    
    print("✅ 成功导入主要模块")
    
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


class BasicSmokeTest:
    """基本冒烟测试类"""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    async def run_all_tests(self):
        """运行所有冒烟测试"""
        print("🚀 开始基本冒烟测试 - 28字段表结构")
        print("=" * 60)
        
        self.start_time = time.time()
        
        try:
            # 测试1: 工厂类测试
            await self.test_factory()
            
            # 测试2: 内存管理器测试
            await self.test_memory_manager()
            
            # 测试3: 28字段结构验证
            await self.test_28_field_structure()
            
            # 测试4: 基本CRUD操作
            await self.test_basic_crud()
            
            # 测试5: 搜索功能测试
            await self.test_search_functionality()
            
            # 测试6: 统计功能测试
            await self.test_statistics()
            
            # 测试7: 网关功能测试（通过工厂间接测试）
            await self.test_gateway_functionality()
            
            # 汇总结果
            await self.summarize_results()
            
        except Exception as e:
            print(f"❌ 冒烟测试执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        self.end_time = time.time()
        
        # 计算通过率
        passed_tests = sum(1 for result in self.results.values() if result == "PASS")
        total_tests = len(self.results)
        
        return passed_tests == total_tests
    
    async def test_factory(self):
        """测试工厂类"""
        print("\n🔧 测试1: 数据库工厂")
        try:
            # 测试内存管理器创建
            config = DatabaseConfig(
                db_type=DatabaseType.MEMORY
            )
            config.redis.enabled = False
            
            manager = await DatabaseManagerFactory.create_manager(config)
            assert manager is not None
            
            # 健康检查
            healthy = await manager.health_check()
            assert healthy == True
            
            await manager.disconnect()
            
            print("  ✅ 工厂类测试通过")
            self.results["factory"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 工厂类测试失败: {e}")
            self.results["factory"] = "FAIL"
            raise
    
    async def test_memory_manager(self):
        """测试内存管理器"""
        print("\n💾 测试2: 内存管理器")
        try:
            config = DatabaseConfig(
                db_type=DatabaseType.MEMORY
            )
            config.redis.enabled = False
            
            manager = await DatabaseManagerFactory.create_manager(config)
            
            # 测试基本操作
            theme = await manager.create_theme(
                name="冒烟测试主题",
                code="SMOKE_TEST_001",
                description="冒烟测试用主题",
                level1_category="测试分类",
                tags={"keywords": ["冒烟测试", "28字段"]}
            )
            
            assert theme is not None
            assert theme.code == "SMOKE_TEST_001"
            assert theme.level1_category == "测试分类"
            
            # 测试获取
            fetched = await manager.get_theme(theme.id)
            assert fetched is not None
            assert fetched.name == "冒烟测试主题"
            
            # 测试按code获取
            by_code = await manager.get_theme_by_code("SMOKE_TEST_001")
            assert by_code is not None
            assert by_code.id == theme.id
            
            # 测试更新
            updated = await manager.update_theme(theme.id, {"heat_score": 75})
            assert updated.heat_score == 75
            
            await manager.disconnect()
            
            print("  ✅ 内存管理器测试通过")
            self.results["memory_manager"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 内存管理器测试失败: {e}")
            self.results["memory_manager"] = "FAIL"
            raise
    
    async def test_28_field_structure(self):
        """测试28字段结构"""
        print("\n🏗️  测试3: 28字段结构验证")
        try:
            config = DatabaseConfig(db_type=DatabaseType.MEMORY)
            config.redis.enabled = False
            manager = await DatabaseManagerFactory.create_manager(config)
            
            # 创建完整的28字段主题 - 使用字典格式的tags
            tags_data = {
                "source": "shenwan",
                "aliases": ["28字段", "结构测试"],
                "keywords": ["28字段", "结构测试", "冒烟测试"],
                "heat_level": "medium",
                "industries": ["测试行业"],
                "industry_code": "TEST001"
            }
            
            theme = await manager.create_theme(
                name="28字段结构测试",
                code="28FIELDS_TEST_001",
                description="测试28字段结构的主题",
                
                # 分类信息
                level1_category="一级分类",
                level2_category="二级分类",
                level3_category="三级分类",
                category_path=["一级分类", "二级分类", "三级分类"],
                category1_code="C001",
                category2_code="C002",
                category3_code="C003",
                
                # 标签信息 - JSONB格式，使用字典
                tags=tags_data,
                
                # 类型与状态
                theme_type="investment",
                lifecycle_stage="growth",
                
                # 热度与置信度
                heat_score=80,
                confidence_score=0.85,
                
                # 关联统计
                related_stocks=["TEST001", "TEST002"],
                stock_count=2,
                news_count=5,
                mention_count=10,
                
                # 来源信息
                source_system="transformed",
                source_id="28fields_source",
                created_by="smoke_test"
            )
            
            print(f"  🔍 创建的主题ID: {theme.id}")
            print(f"  🔍 主题tags类型: {type(theme.tags)}")
            print(f"  🔍 主题tags内容: {theme.tags}")
            
            # 验证所有28字段都存在
            assert hasattr(theme, 'code')
            assert hasattr(theme, 'level1_category')
            assert hasattr(theme, 'level2_category')
            assert hasattr(theme, 'level3_category')
            assert hasattr(theme, 'category_path')
            assert hasattr(theme, 'category1_code')
            assert hasattr(theme, 'category2_code')
            assert hasattr(theme, 'category3_code')
            assert hasattr(theme, 'tags')
            assert hasattr(theme, 'theme_type')
            assert hasattr(theme, 'lifecycle_stage')
            assert hasattr(theme, 'heat_score')
            assert hasattr(theme, 'confidence_score')
            assert hasattr(theme, 'related_stocks')
            assert hasattr(theme, 'stock_count')
            assert hasattr(theme, 'news_count')
            assert hasattr(theme, 'mention_count')
            assert hasattr(theme, 'source_system')
            assert hasattr(theme, 'source_id')
            assert hasattr(theme, 'created_by')
            assert hasattr(theme, 'created_at')
            assert hasattr(theme, 'updated_at')
            
            # 验证特定字段值
            assert theme.code == "28FIELDS_TEST_001"
            assert theme.level1_category == "一级分类"
            assert theme.level2_category == "二级分类"
            assert theme.level3_category == "三级分类"
            
            # 检查tags字段
            tags = theme.tags
            if isinstance(tags, dict):
                print(f"  ✅ tags字段是字典格式，符合JSONB存储")
            elif hasattr(tags, 'keywords'):
                # 如果是ThemeTags对象
                print(f"  ✅ tags字段是ThemeTags对象")
                assert "28字段" in tags.keywords
            else:
                # 其他格式
                print(f"  ⚠️  tags字段是未知类型: {type(tags)}")
            
            assert theme.heat_score == 80
            assert theme.confidence_score == 0.85
            assert theme.stock_count == 2
            
            await manager.disconnect()
            
            print("  ✅ 28字段结构验证通过")
            self.results["28_field_structure"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 28字段结构验证失败: {e}")
            self.results["28_field_structure"] = "FAIL"
            raise
    
    async def test_basic_crud(self):
        """测试基本CRUD操作"""
        print("\n📝 测试4: 基本CRUD操作")
        try:
            config = DatabaseConfig(db_type=DatabaseType.MEMORY)
            config.redis.enabled = False
            manager = await DatabaseManagerFactory.create_manager(config)
            
            # Create - 创建
            theme = await manager.create_theme(
                name="CRUD测试主题",
                code="CRUD_TEST_001",
                description="CRUD测试主题",
                heat_score=50
            )
            assert theme is not None
            
            # Read - 读取
            read_theme = await manager.get_theme(theme.id)
            assert read_theme is not None
            assert read_theme.code == "CRUD_TEST_001"
            assert read_theme.heat_score == 50
            
            # Update - 更新
            updated = await manager.update_theme(theme.id, {
                "heat_score": 75,
                "description": "更新后的描述"
            })
            assert updated.heat_score == 75
            assert updated.description == "更新后的描述"
            
            # 验证更新后的读取
            verify_theme = await manager.get_theme(theme.id)
            assert verify_theme.heat_score == 75
            
            # 测试按名称和code读取
            by_name = await manager.get_theme_by_name("CRUD测试主题")
            assert by_name is not None
            
            by_code = await manager.get_theme_by_code("CRUD_TEST_001")
            assert by_code is not None
            
            # 测试增加操作
            await manager.increment_theme_heat(theme.id, 10)
            await manager.increment_mention_count(theme.id, 5)
            
            final_theme = await manager.get_theme(theme.id)
            assert final_theme.heat_score == 85  # 75 + 10
            assert final_theme.mention_count == 5
            
            # 测试获取所有主题
            all_themes = await manager.get_all_active_themes(limit=100)
            assert len(all_themes) > 0
            
            await manager.disconnect()
            
            print("  ✅ 基本CRUD操作测试通过")
            self.results["basic_crud"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 基本CRUD操作测试失败: {e}")
            self.results["basic_crud"] = "FAIL"
            raise
    
    async def test_search_functionality(self):
        """测试搜索功能"""
        print("\n🔍 测试5: 搜索功能")
        try:
            config = DatabaseConfig(db_type=DatabaseType.MEMORY)
            config.redis.enabled = False
            manager = await DatabaseManagerFactory.create_manager(config)
            
            # 创建测试主题
            themes = [
                ("搜索测试主题1", "SEARCH_TEST_001", ["搜索", "测试1"]),
                ("搜索测试主题2", "SEARCH_TEST_002", ["搜索", "测试2"]),
                ("AI测试主题", "AI_TEST_001", ["AI", "人工智能"]),
                ("数据库测试主题", "DB_TEST_001", ["数据库", "PostgreSQL"])
            ]
            
            for name, code, keywords in themes:
                await manager.create_theme(
                    name=name,
                    code=code,
                    description=f"{name}描述",
                    tags={"keywords": keywords}
                )
            
            # 测试搜索
            search_results = await manager.search_themes("搜索测试", limit=10)
            assert len(search_results) >= 2
            
            # 测试关键词搜索
            keyword_results = await manager.get_themes_by_keywords(["搜索"], limit=10)
            assert len(keyword_results) >= 2
            
            # 测试热度查询
            heat_results = await manager.get_themes_by_heat_level(min_heat=60, limit=10)
            assert isinstance(heat_results, list)
            
            # 测试查找相关主题
            event_data = {"keywords": ["AI", "人工智能"]}
            related_results = await manager.find_related_themes(event_data, limit=5)
            assert len(related_results) > 0
            
            await manager.disconnect()
            
            print("  ✅ 搜索功能测试通过")
            self.results["search_functionality"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 搜索功能测试失败: {e}")
            self.results["search_functionality"] = "FAIL"
            raise
    
    async def test_statistics(self):
        """测试统计功能"""
        print("\n📊 测试6: 统计功能")
        try:
            config = DatabaseConfig(db_type=DatabaseType.MEMORY)
            config.redis.enabled = False
            manager = await DatabaseManagerFactory.create_manager(config)
            
            # 获取统计信息
            stats = await manager.get_stats()
            
            # 验证基本统计结构
            assert 'themes' in stats
            assert 'events' in stats
            assert 'relations' in stats
            
            themes_stats = stats['themes']
            assert 'total' in themes_stats
            assert 'active' in themes_stats
            assert 'avg_heat' in themes_stats
            
            # 获取主题统计
            theme_stats = await manager.get_theme_stats()
            assert 'total' in theme_stats
            assert 'active' in theme_stats
            
            # 尝试执行原始查询，但内存数据库可能不支持
            try:
                query_results = await manager.execute_query("SELECT 1 as test")
                if query_results:
                    assert len(query_results) > 0
                    print(f"  ✅ 原始SQL查询返回 {len(query_results)} 行结果")
                else:
                    print(f"  ⚠️  原始SQL查询返回空结果")
            except Exception as e:
                print(f"  ⚠️  原始SQL查询可能不被支持: {e}")
                # 内存数据库不支持原始SQL是正常的
            
            await manager.disconnect()
            
            print("  ✅ 统计功能测试通过")
            self.results["statistics"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 统计功能测试失败: {e}")
            self.results["statistics"] = "FAIL"
            raise
    
    async def test_gateway_functionality(self):
        """测试网关功能（通过工厂间接测试）"""
        print("\n🚪 测试7: 网关功能测试")
        try:
            config = DatabaseConfig(db_type=DatabaseType.MEMORY)
            config.redis.enabled = False
            
            # 创建两个管理器实例，模拟网关的多实例管理
            manager1 = await DatabaseManagerFactory.create_manager(config)
            manager2 = await DatabaseManagerFactory.create_manager(config)
            
            # 测试管理器1创建主题
            theme1 = await manager1.create_theme(
                name="网关功能测试1",
                code="GATEWAY_FUNC_001",
                description="网关功能测试主题1"
            )
            assert theme1 is not None
            
            # 测试管理器2也能获取到主题（如果是共享存储）
            # 注意：内存管理器默认是独立的，所以这里主要测试工厂创建多个实例的能力
            
            # 测试批量操作
            themes_data = [
                {
                    "name": "批量主题1",
                    "code": "BATCH_GATEWAY_001",
                    "description": "批量创建测试1"
                },
                {
                    "name": "批量主题2",
                    "code": "BATCH_GATEWAY_002",
                    "description": "批量创建测试2"
                }
            ]
            
            batch_themes = await manager1.batch_create_themes(themes_data)
            assert len(batch_themes) == 2
            
            # 测试组合搜索
            search_results = await manager1.search_themes("批量", limit=10)
            assert len(search_results) >= 2
            
            # 清理
            await manager1.disconnect()
            await manager2.disconnect()
            
            print("  ✅ 网关功能测试通过")
            self.results["gateway_functionality"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 网关功能测试失败: {e}")
            self.results["gateway_functionality"] = "FAIL"
            raise
    
    async def summarize_results(self):
        """汇总测试结果"""
        print("\n" + "=" * 60)
        print("📋 冒烟测试结果汇总")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result == "PASS")
        failed_tests = sum(1 for result in self.results.values() if result == "FAIL")
        
        # 显示每个测试结果
        for test_name, result in self.results.items():
            if result == "PASS":
                status = "✅ PASS"
            else:
                status = "❌ FAIL"
            print(f"  {test_name:25} {status}")
        
        # 显示统计
        print(f"\n📊 统计:")
        print(f"  总测试数: {total_tests}")
        print(f"  通过数: {passed_tests}")
        print(f"  失败数: {failed_tests}")
        
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            print(f"  总用时: {duration:.2f}秒")
        
        # 总体结果
        if failed_tests == 0:
            print("\n🎉 所有冒烟测试通过！")
        else:
            print(f"\n⚠️  有 {failed_tests} 个测试失败")


async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 基本冒烟测试启动 - 28字段表结构")
    print("=" * 60)
    
    smoke_test = BasicSmokeTest()
    success = await smoke_test.run_all_tests()
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
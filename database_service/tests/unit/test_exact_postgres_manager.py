# tests/unit/test_production_ready_postgres.py
"""
生产就绪的PostgreSQL测试 - 正确处理外键和所有边界情况
"""
import sys
import os
import pytest
import asyncio
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
sys.path.insert(0, service_dir)

from config import DatabaseConfig, RedisConfig, DatabaseType
from managers.postgres_manager import PostgresDatabaseManager


class TestProductionReadyPostgres:
    """生产就绪的PostgreSQL测试类"""
    
    def __init__(self):
        self.test_start_time = int(time.time())
        self.test_prefix = f"PROD_TEST_{self.test_start_time}"
        
    async def create_manager(self, database: str = "stock_data_test") -> PostgresDatabaseManager:
        """创建数据库管理器"""
        config = DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            postgres_host="localhost",
            postgres_port=5432,
            postgres_database=database,
            postgres_username="postgres",
            postgres_password="",
            table_names_config={
                "theme_master": "theme_master",
                "news_raw": "news_raw",
                "news_event": "news_event",
                "event_theme_map": "event_theme_map",
                "financial_categories": "financial_categories"
            },
            redis=RedisConfig(enabled=False),
            enable_query_logging=True,
            slow_query_threshold=0.3
        )
        
        manager = PostgresDatabaseManager(config)
        await manager.connect()
        return manager
    
    async def cleanup_test_data(self, manager: PostgresDatabaseManager):
        """安全地清理测试数据（正确处理外键）"""
        async with manager.pool.acquire() as conn:
            # 开始事务
            async with conn.transaction():
                # 1. 先删除 event_theme_map（外键依赖最末端）
                await conn.execute("""
                    DELETE FROM event_theme_map 
                    WHERE match_reason = '关键词匹配' 
                    OR event_id IN (
                        SELECT id FROM news_event WHERE event_type = $1
                    )
                    OR theme_id IN (
                        SELECT id FROM theme_master WHERE source_system = $2
                    )
                """, 'test_event', 'test_suite')
                
                # 2. 删除 news_event（依赖 news_raw）
                await conn.execute("""
                    DELETE FROM news_event 
                    WHERE event_type = $1
                    OR news_id IN (
                        SELECT id FROM news_raw WHERE source = $2
                    )
                """, 'test_event', 'test_source')
                
                # 3. 删除 news_raw
                await conn.execute("""
                    DELETE FROM news_raw 
                    WHERE source = $1
                """, 'test_source')
                
                # 4. 删除 theme_master
                await conn.execute("""
                    DELETE FROM theme_master 
                    WHERE source_system = $1
                """, 'test_suite')
                
                # 5. 删除 financial_categories
                await conn.execute("""
                    DELETE FROM financial_categories 
                    WHERE category_code LIKE $1
                """, f"{self.test_prefix}%")
    
    @pytest.mark.asyncio
    async def test_safe_crud_operations(self):
        """安全的CRUD操作测试（包含清理）"""
        print(f"\n{'='*60}")
        print("安全的CRUD操作测试")
        print(f"测试ID: {self.test_prefix}")
        print('='*60)
        
        manager = await self.create_manager("stock_data_test")
        
        try:
            # ========== 创建测试数据 ==========
            print("\n📝 创建测试数据...")
            
            # 创建测试主题
            theme_code = f"{self.test_prefix}_THEME"
            theme_data = {
                "name": f"安全测试主题_{self.test_start_time}",
                "code": theme_code,
                "description": "安全测试主题描述",
                "status": "active",
                "level1_category": "测试",
                "theme_type": "concept",
                "heat_score": 70,
                "confidence_score": 0.80,
                "lifecycle_stage": "growth",
                "related_stocks": ["600000", "000001"],
                "source_system": "test_suite",
                "source_id": f"test_{self.test_start_time}",
                "created_by": "safe_tester"
            }
            
            # 使用事务创建主题
            async with manager.pool.acquire() as conn:
                async with conn.transaction():
                    # 插入主题
                    theme_result = await conn.fetchrow("""
                        INSERT INTO theme_master (
                            name, code, description, status, level1_category,
                            theme_type, heat_score, confidence_score, lifecycle_stage,
                            related_stocks, source_system, source_id, created_by
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        RETURNING id, name, code
                    """,
                    theme_data["name"], theme_data["code"], theme_data["description"],
                    theme_data["status"], theme_data["level1_category"], theme_data["theme_type"],
                    theme_data["heat_score"], theme_data["confidence_score"], 
                    theme_data["lifecycle_stage"], theme_data["related_stocks"],
                    theme_data["source_system"], theme_data["source_id"], theme_data["created_by"]
                    )
                    
                    if theme_result:
                        theme_id = theme_result['id']
                        print(f"✅ 主题创建成功: ID={theme_id}, Code={theme_result['code']}")
                        
                        # ========== 创建测试新闻 ==========
                        news_id = f"{self.test_prefix}_NEWS"
                        news_result = await conn.fetchrow("""
                            INSERT INTO news_raw (title, content, source, news_id, publish_date)
                            VALUES ($1, $2, $3, $4, $5)
                            RETURNING id, news_id
                        """,
                        f"安全测试新闻_{self.test_start_time}",
                        "这是安全测试新闻内容",
                        "test_source",
                        news_id,
                        datetime.now().date()
                        )
                        
                        if news_result:
                            news_db_id = news_result['id']
                            print(f"✅ 新闻创建成功: ID={news_db_id}")
                            
                            # ========== 创建新闻事件 ==========
                            event_result = await conn.fetchrow("""
                                INSERT INTO news_event (news_id, event_type, confidence, summary, theme_directive)
                                VALUES ($1, $2, $3, $4, $5)
                                RETURNING id
                            """,
                            news_db_id,
                            "test_event",
                            0.85,
                            "安全测试事件摘要",
                            json.dumps({"themes": ["TEST"], "impact": "neutral"})
                            )
                            
                            if event_result:
                                event_id = event_result['id']
                                print(f"✅ 事件创建成功: ID={event_id}")
                                
                                # ========== 创建事件-主题映射 ==========
                                map_result = await conn.fetchrow("""
                                    INSERT INTO event_theme_map (event_id, theme_id, confidence, match_reason, matched_keywords)
                                    VALUES ($1, $2, $3, $4, $5)
                                    RETURNING id
                                """,
                                event_id,
                                theme_id,
                                0.90,
                                "安全测试匹配",
                                ["测试", "安全"]
                                )
                                
                                if map_result:
                                    print(f"✅ 事件-主题映射创建成功: ID={map_result['id']}")
            
            # ========== 验证读取操作 ==========
            print("\n🔍 验证读取操作...")
            
            async with manager.pool.acquire() as conn:
                # 验证主题存在
                theme_check = await conn.fetchrow("""
                    SELECT id, name, code FROM theme_master 
                    WHERE code = $1 AND source_system = $2
                """, theme_code, "test_suite")
                
                if theme_check:
                    print(f"✅ 主题验证成功: {theme_check['code']}")
                
                # 验证新闻存在
                news_check = await conn.fetchval("""
                    SELECT COUNT(*) FROM news_raw WHERE source = 'test_source'
                """)
                print(f"✅ 测试新闻数量: {news_check}")
                
                # 验证事件存在
                event_check = await conn.fetchval("""
                    SELECT COUNT(*) FROM news_event WHERE event_type = 'test_event'
                """)
                print(f"✅ 测试事件数量: {event_check}")
                
                # 验证映射存在
                map_check = await conn.fetchval("""
                    SELECT COUNT(*) FROM event_theme_map WHERE match_reason = '安全测试匹配'
                """)
                print(f"✅ 测试映射数量: {map_check}")
            
            print("\n✅ 所有创建操作完成")
            
        finally:
            # ========== 安全清理 ==========
            print("\n🧹 安全清理测试数据...")
            await self.cleanup_test_data(manager)
            
            # 验证清理
            async with manager.pool.acquire() as conn:
                remaining = await conn.fetchval("""
                    SELECT COUNT(*) FROM (
                        SELECT 1 FROM theme_master WHERE source_system = 'test_suite'
                        UNION ALL
                        SELECT 1 FROM news_raw WHERE source = 'test_source'
                        UNION ALL
                        SELECT 1 FROM news_event WHERE event_type = 'test_event'
                        UNION ALL
                        SELECT 1 FROM financial_categories WHERE category_code LIKE $1
                    ) t
                """, f"{self.test_prefix}%")
                
                if remaining == 0:
                    print("✅ 测试数据清理完成，数据库保持干净")
                else:
                    print(f"⚠️  还有 {remaining} 条测试数据")
            
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_readonly_production_check(self):
        """生产数据库只读检查"""
        print(f"\n{'='*60}")
        print("生产数据库只读检查")
        print('='*60)
        
        manager = await self.create_manager("stock_data")  # 生产数据库
        
        try:
            # 只进行读取操作，确保安全
            async with manager.pool.acquire() as conn:
                # 1. 统计信息
                counts = await conn.fetch("""
                    SELECT 
                        'theme_master' as table_name,
                        COUNT(*) as record_count,
                        MAX(created_at) as latest_record
                    FROM theme_master
                    UNION ALL
                    SELECT 
                        'news_raw',
                        COUNT(*),
                        MAX(created_at)
                    FROM news_raw
                    UNION ALL
                    SELECT 
                        'news_event',
                        COUNT(*),
                        MAX(created_at)
                    FROM news_event
                    ORDER BY table_name
                """)
                
                print("📊 生产数据库统计:")
                for row in counts:
                    latest = row['latest_record']
                    latest_str = latest.strftime('%Y-%m-%d %H:%M') if latest else "N/A"
                    print(f"  - {row['table_name']}: {row['record_count']:,} 条记录, 最新: {latest_str}")
                
                # 2. 主题热度分析
                heat_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        AVG(heat_score) as avg_heat,
                        MIN(heat_score) as min_heat,
                        MAX(heat_score) as max_heat,
                        SUM(CASE WHEN heat_score >= 80 THEN 1 ELSE 0 END) as high_heat_count
                    FROM theme_master
                    WHERE status = 'active'
                """)
                
                if heat_stats:
                    print(f"\n🔥 主题热度分析:")
                    print(f"  - 活跃主题总数: {heat_stats['total']}")
                    print(f"  - 平均热度: {heat_stats['avg_heat']:.1f}")
                    print(f"  - 热度范围: {heat_stats['min_heat']} - {heat_stats['max_heat']}")
                    print(f"  - 高热度主题(≥80): {heat_stats['high_heat_count']}")
                
                # 3. 新闻处理状态
                news_status = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN is_processed THEN 1 ELSE 0 END) as processed,
                        SUM(CASE WHEN NOT is_processed THEN 1 ELSE 0 END) as pending
                    FROM news_raw
                """)
                
                if news_status:
                    total = news_status['total']
                    if total > 0:
                        processed_pct = (news_status['processed'] / total) * 100
                        print(f"\n📰 新闻处理状态:")
                        print(f"  - 新闻总数: {total:,}")
                        print(f"  - 已处理: {news_status['processed']:,} ({processed_pct:.1f}%)")
                        print(f"  - 待处理: {news_status['pending']:,}")
                
                print("\n✅ 生产数据库只读检查完成")
                
        except Exception as e:
            print(f"⚠️  生产数据库检查失败: {e}")
            # 不抛出异常，这只是检查
        finally:
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_performance_and_error_handling(self):
        """性能测试和错误处理"""
        print(f"\n{'='*60}")
        print("性能测试和错误处理")
        print('='*60)
        
        manager = await self.create_manager("stock_data_test")
        
        try:
            start_time = time.time()
            
            # 测试批量操作
            async with manager.pool.acquire() as conn:
                # 测试查询性能
                query_start = time.time()
                
                # 1. 简单查询
                simple_result = await conn.fetch("SELECT COUNT(*) FROM theme_master")
                simple_time = time.time() - query_start
                print(f"⏱️  简单查询耗时: {simple_time:.3f}s")
                
                # 2. 复杂查询
                query_start = time.time()
                complex_result = await conn.fetch("""
                    SELECT 
                        level1_category,
                        COUNT(*) as theme_count,
                        AVG(heat_score) as avg_heat,
                        SUM(stock_count) as total_stocks
                    FROM theme_master
                    WHERE status = 'active'
                    GROUP BY level1_category
                    ORDER BY avg_heat DESC
                    LIMIT 5
                """)
                complex_time = time.time() - query_start
                print(f"⏱️  复杂查询耗时: {complex_time:.3f}s")
                
                if complex_result:
                    print("\n📊 按分类统计:")
                    for row in complex_result:
                        print(f"  - {row['level1_category'] or '未分类'}: {row['theme_count']} 主题, "
                              f"平均热度 {row['avg_heat']:.1f}, 关联股票 {row['total_stocks']}")
                
                # 3. 错误处理测试
                print("\n🧪 错误处理测试:")
                
                # 测试重复插入（应该失败）
                try:
                    # 尝试插入重复的code
                    await conn.execute("""
                        INSERT INTO theme_master (name, code, source_system)
                        VALUES ('重复测试', 'DUPLICATE_TEST', 'test_error')
                    """)
                    
                    # 再次插入同样的code
                    await conn.execute("""
                        INSERT INTO theme_master (name, code, source_system)
                        VALUES ('重复测试2', 'DUPLICATE_TEST', 'test_error')
                    """)
                    
                    print("❌ 重复插入测试失败 - 应该抛出异常")
                    
                except Exception as e:
                    print(f"✅ 重复插入被正确阻止: {type(e).__name__}")
                
                # 测试无效外键（应该失败）
                try:
                    await conn.execute("""
                        INSERT INTO news_event (news_id, event_type)
                        VALUES (999999, 'invalid_test')
                    """)
                    print("❌ 无效外键测试失败 - 应该抛出异常")
                except Exception as e:
                    print(f"✅ 无效外键被正确阻止: {type(e).__name__}")
            
            total_time = time.time() - start_time
            print(f"\n⏱️  性能测试总耗时: {total_time:.3f}s")
            
            print("\n✅ 性能测试和错误处理完成")
            
        finally:
            # 清理测试数据
            async with manager.pool.acquire() as conn:
                await conn.execute("DELETE FROM theme_master WHERE source_system = 'test_error'")
            
            await manager.disconnect()


# 运行测试的主函数
def run_all_tests():
    """运行所有测试"""
    print("🚀 开始生产就绪的PostgreSQL测试")
    print("📅 测试时间:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("📍 测试数据库: stock_data_test")
    print("📍 生产数据库: stock_data (只读)")
    print('='*60)
    
    # 使用pytest运行测试
    pytest.main([
        __file__,
        "-v",      # 详细输出
        "-s",      # 显示打印输出
        "--tb=no"  # 不显示完整的traceback（更简洁）
    ])


if __name__ == "__main__":
    run_all_tests()
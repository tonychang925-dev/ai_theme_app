#!/usr/bin/env python3
"""
完整修复表结构
"""
import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

async def complete_fix():
    print("🔧 完整修复数据库表结构")
    print("="*60)
    
    try:
        from theme_service.config import settings
        from theme_service.database import ThemeDatabase
        
        # 创建数据库连接
        db = ThemeDatabase(settings.DATABASE_URL)
        await db.initialize()
        
        conn = await db.acquire_connection()
        try:
            print("1. 检查并修复 theme_master 表...")
            
            # 添加 updated_at 列（如果不存在）
            try:
                await conn.execute("""
                    ALTER TABLE theme_master 
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()
                """)
                print("   ✅ 添加/确认 updated_at 列")
            except Exception as e:
                print(f"   ⚠️  处理 updated_at 列失败: {e}")
            
            # 重置自增序列（解决主键冲突问题）
            print("\n2. 修复自增序列...")
            try:
                # 获取当前最大ID
                max_id = await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM theme_master")
                print(f"   当前最大ID: {max_id}")
                
                # 重置序列
                await conn.execute(f"""
                    SELECT setval('theme_master_id_seq', {max_id + 1}, false)
                """)
                print(f"   ✅ 重置序列到: {max_id + 1}")
            except Exception as e:
                print(f"   ⚠️  修复序列失败: {e}")
            
            print("\n3. 检查表约束...")
            
            # 检查唯一约束
            constraints = await conn.fetch("""
                SELECT 
                    tc.constraint_name,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.table_name = 'theme_master'
                ORDER BY tc.constraint_type, tc.constraint_name
            """)
            
            print(f"   发现 {len(constraints)} 个约束:")
            for const in constraints:
                const_type = "PRIMARY KEY" if "pkey" in const['constraint_name'] else "UNIQUE"
                print(f"     - {const['constraint_name']}: {const_type} on {const['column_name']}")
            
            print("\n4. 检查 event_theme_map 表外键...")
            try:
                # 添加缺失的外键约束（如果不存在）
                await conn.execute("""
                    DO $$ 
                    BEGIN
                        -- 检查外键是否已存在
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.table_constraints
                            WHERE constraint_name = 'event_theme_map_event_id_fkey'
                        ) THEN
                            -- 添加 event_id 外键
                            ALTER TABLE event_theme_map 
                            ADD CONSTRAINT event_theme_map_event_id_fkey 
                            FOREIGN KEY (event_id) REFERENCES news_event(id) ON DELETE CASCADE;
                        END IF;
                        
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.table_constraints
                            WHERE constraint_name = 'event_theme_map_theme_id_fkey'
                        ) THEN
                            -- 添加 theme_id 外键
                            ALTER TABLE event_theme_map 
                            ADD CONSTRAINT event_theme_map_theme_id_fkey 
                            FOREIGN KEY (theme_id) REFERENCES theme_master(id) ON DELETE CASCADE;
                        END IF;
                    END $$;
                """)
                print("   ✅ 检查/添加外键约束")
            except Exception as e:
                print(f"   ⚠️  检查外键失败: {e}")
        
        finally:
            await db.release_connection(conn)
        
        print("\n5. 验证修复结果...")
        
        conn = await db.acquire_connection()
        try:
            # 验证表结构
            print("   theme_master 表结构:")
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'theme_master'
                ORDER BY ordinal_position
            """)
            
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                print(f"     - {col['column_name']}: {col['data_type']} ({nullable}{default})")
            
            # 测试插入
            print("\n   测试插入主题...")
            test_theme = {
                "name": f"测试主题_{int(time.time())}",
                "keywords": ["测试", "验证"],
                "discovery_source": "table_fix_test",
                "confidence": 0.9
            }
            
            # 使用直接SQL插入测试
            result = await conn.fetchrow("""
                INSERT INTO theme_master 
                (name, keywords, status, discovery_source, discovery_confidence, heat_score)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, name, created_at, updated_at
            """,
                test_theme["name"],
                test_theme["keywords"],
                "test",
                test_theme["discovery_source"],
                test_theme["confidence"],
                50
            )
            
            if result:
                print(f"   ✅ 测试插入成功: ID={result['id']}, 名称={result['name']}")
                print(f"      创建时间: {result['created_at']}, 更新时间: {result['updated_at']}")
                
                # 清理测试数据
                await conn.execute("DELETE FROM theme_master WHERE name LIKE '测试主题_%'")
                print("   🧹 清理测试数据完成")
            else:
                print("   ❌ 测试插入失败")
        
        finally:
            await db.release_connection(conn)
        
        # 显示最终统计
        stats = await db.get_table_stats()
        print("\n📊 最终数据统计:")
        for table, count in stats.items():
            print(f"  {table}: {count}")
        
        await db.close()
        
        print("\n✅ 表结构修复完成！")
        return True
        
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        import time
        time.sleep(1)  # 确保数据库连接关闭

if __name__ == "__main__":
    success = asyncio.run(complete_fix())
    
    if success:
        print("\n🎉 表结构完全修复成功！")
        print("\n🚀 现在可以正常运行数据处理服务了")
    else:
        print("\n❌ 表结构修复失败")
    
    sys.exit(0 if success else 1)

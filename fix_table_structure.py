#!/usr/bin/env python3
"""
修复数据库表结构
"""
import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

async def fix_tables():
    print("🔧 修复数据库表结构")
    print("="*60)
    
    try:
        from theme_service.config import settings
        from theme_service.database import ThemeDatabase
        
        # 创建数据库连接
        db = ThemeDatabase(settings.DATABASE_URL)
        await db.initialize()
        
        print("📊 当前表结构:")
        
        # 获取现有列
        async with (await db.acquire_connection()) as conn:
            # 检查 theme_master 表的列
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'theme_master'
                ORDER BY ordinal_position
            """)
            
            print("theme_master 表列:")
            existing_columns = []
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"  - {col['column_name']}: {col['data_type']} ({nullable})")
                existing_columns.append(col['column_name'])
            
            # 添加缺失的列
            required_columns = {
                'discovery_source': 'VARCHAR(100)',
                'discovery_confidence': 'DECIMAL(5,2)',
                'heat_score': 'INTEGER DEFAULT 0',
                'lifecycle_stage': 'VARCHAR(50) DEFAULT \'emerging\''
            }
            
            print("\n🔧 修复缺失列:")
            for col_name, col_type in required_columns.items():
                if col_name not in existing_columns:
                    try:
                        await conn.execute(f"""
                            ALTER TABLE theme_master 
                            ADD COLUMN {col_name} {col_type}
                        """)
                        print(f"  ✅ 添加列: {col_name}")
                    except Exception as e:
                        print(f"  ❌ 添加列 {col_name} 失败: {e}")
                else:
                    print(f"  ✅ 列已存在: {col_name}")
            
            # 检查 event_theme_map 表
            print("\n📋 检查 event_theme_map 表...")
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS event_theme_map (
                        id SERIAL PRIMARY KEY,
                        event_id INTEGER,
                        theme_id INTEGER,
                        confidence DECIMAL(5,2),
                        confidence_level VARCHAR(20),
                        confidence_weight INTEGER,
                        created_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(event_id, theme_id)
                    )
                """)
                print("  ✅ event_theme_map 表已创建/验证")
            except Exception as e:
                print(f"  ⚠️  event_theme_map 表检查失败: {e}")
        
        print("\n✅ 表结构修复完成")
        
        # 验证修复
        print("\n🔍 验证修复结果:")
        stats = await db.get_table_stats()
        for table, count in stats.items():
            print(f"  {table}: {count}")
        
        await db.close()
        return True
        
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(fix_tables())
    
    if success:
        print("\n🎉 表结构修复成功！")
        print("\n🚀 现在可以开始数据流集成了")
    else:
        print("\n❌ 表结构修复失败")
    
    sys.exit(0 if success else 1)

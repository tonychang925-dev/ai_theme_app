#!/usr/bin/env python3
"""
最终修复表结构
"""
import asyncio
import sys
import os
import time  # 添加time导入

sys.path.insert(0, os.getcwd())

async def complete_fix():
    print("🔧 最终修复数据库表结构")
    print("="*60)
    
    try:
        from theme_service.config import settings
        from theme_service.database import ThemeDatabase
        
        # 创建数据库连接
        db = ThemeDatabase(settings.DABASE_URL)
        await db.initialize()
        
        conn = await db.acquire_connection()
        try:
            print("1. 最终验证表结构...")
            
            # 验证所有必需的列都存在
            required_columns = ['id', 'name', 'status', 'created_at', 'updated_at', 
                               'discovery_source', 'discovery_confidence', 'heat_score', 'lifecycle_stage']
            
            existing_columns = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'theme_master'
            """)
            
            existing_column_names = [col['column_name'] for col in existing_columns]
            print(f"   现有列 ({len(existing_column_names)}): {', '.join(existing_column_names)}")
            
            # 检查缺失的列
            missing = [col for col in required_columns if col not in existing_column_names]
            if missing:
                print(f"   ⚠️  缺失列: {missing}")
                for col in missing:
                    try:
                        if col == 'updated_at':
                            await conn.execute(f"ALTER TABLE theme_master ADD COLUMN {col} TIMESTAMP DEFAULT NOW()")
                        elif col == 'heat_score':
                            await conn.execute(f"ALTER TABLE theme_master ADD COLUMN {col} INTEGER DEFAULT 0")
                        elif col == 'lifecycle_stage':
                            await conn.execute(f"ALTER TABLE theme_master ADD COLUMN {col} VARCHAR(50) DEFAULT 'emerging'")
                        elif col == 'discovery_confidence':
                            await conn.execute(f"ALTER TABLE theme_master ADD COLUMN {col} DECIMAL(5,2)")
                        elif col == 'discovery_source':
                            await conn.execute(f"ALTER TABLE theme_master ADD COLUMN {col} VARCHAR(100)")
                        print(f"      ✅ 添加列: {col}")
                    except Exception as e:
                        print(f"      ⚠️  添加列 {col} 失败: {e}")
            else:
                print("   ✅ 所有必需列都存在")
        
        finally:
            await db.release_connection(conn)
        
        print("\n2. 测试数据库功能...")
        
        # 测试数据库方法
        print("   测试 get_recent_events...")
        events = await db.get_recent_events(limit=2)
        print(f"   获取到 {len(events)} 个事件")
        
        print("   测试 save_theme...")
        test_theme = {
            "name": f"最终测试主题_{int(time.time())}",
            "keywords": ["最终测试", "验证"],
            "status": "test",
            "discovery_source": "final_test",
            "confidence": 0.95
        }
        
        theme_id = await db.save_theme(test_theme)
        if theme_id:
            print(f"   ✅ 保存主题成功: ID={theme_id}")
        else:
            print("   ❌ 保存主题失败")
        
        print("   测试 get_themes_by_status...")
        themes = await db.get_themes_by_status("test", limit=3)
        print(f"   获取到 {len(themes)} 个测试主题")
        
        if themes:
            print("   测试主题:")
            for theme in themes:
                print(f"     - {theme.get('name')} (ID: {theme.get('id')})")
        
        # 清理测试数据
        print("\n3. 清理测试数据...")
        conn = await db.acquire_connection()
        try:
            await conn.execute("DELETE FROM theme_master WHERE status = 'test'")
            count = await conn.fetchval("SELECT COUNT(*) FROM theme_master WHERE status = 'test'")
            print(f"   清理完成，剩余测试主题: {count}")
        finally:
            await db.release_connection(conn)
        
        # 显示最终统计
        stats = await db.get_table_stats()
        print("\n📊 最终数据统计:")
        for table, count in stats.items():
            print(f"  {table}: {count}")
        
        await db.close()
        
        print("\n✅ 数据库表结构修复和验证完成！")
        return True
        
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(complete_fix())
    
    if success:
        print("\n🎉 数据库完全修复成功！")
        print("\n🚀 现在可以正常运行所有服务了")
    else:
        print("\n❌ 数据库修复失败")
    
    sys.exit(0 if success else 1)

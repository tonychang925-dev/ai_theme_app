#!/usr/bin/env python3
"""
检查数据库表结构
"""
import asyncio
import asyncpg

async def check_table_structure():
    """检查news_raw表结构"""
    print("🔍 检查数据库表结构")
    print("=" * 60)
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 1. 检查news_raw表结构
        print("📋 news_raw表结构:")
        print("-" * 40)
        
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'news_raw'
            ORDER BY ordinal_position
        """)
        
        for col in columns:
            print(f"  {col['column_name']:20} {col['data_type']:20} "
                  f"NULL: {col['is_nullable']}")
        
        # 2. 检查news_event表结构
        print(f"\n📋 news_event表结构:")
        print("-" * 40)
        
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'news_event'
            ORDER BY ordinal_position
        """)
        
        for col in columns:
            print(f"  {col['column_name']:20} {col['data_type']:20} "
                  f"NULL: {col['is_nullable']}")
        
        # 3. 查看外键关系
        print(f"\n🔗 外键关系:")
        print("-" * 40)
        
        foreign_keys = await conn.fetch("""
            SELECT
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' 
                AND tc.table_name IN ('news_event', 'news_raw')
            ORDER BY tc.table_name, kcu.column_name;
        """)
        
        if foreign_keys:
            for fk in foreign_keys:
                print(f"  {fk['table_name']}.{fk['column_name']} → "
                      f"{fk['foreign_table_name']}.{fk['foreign_column_name']}")
        else:
            print("  ⚠️  没有找到外键约束")
        
        # 4. 查看表数据示例
        print(f"\n📊 news_raw表示例数据 (前3条):")
        print("-" * 40)
        
        samples = await conn.fetch("""
            SELECT id, news_id, title, publish_date, created_at 
            FROM news_raw 
            ORDER BY created_at DESC 
            LIMIT 3
        """)
        
        for sample in samples:
            print(f"  ID: {sample['id']}")
            print(f"    News ID: {sample['news_id'][:30]}...")
            print(f"    标题: {sample['title'][:40]}...")
            print(f"    发布日期: {sample['publish_date']}")
            print(f"    创建时间: {sample['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
            print()
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()

async def test_date_insertion():
    """测试日期插入"""
    print(f"\n🧪 测试日期插入...")
    print("-" * 40)
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 测试不同日期格式
        test_cases = [
            ("string_date", "2024-01-15", "字符串日期"),
            ("date_object", date(2024, 1, 15), "date对象"),
            ("datetime_obj", datetime(2024, 1, 15), "datetime对象")
        ]
        
        for test_name, test_date, description in test_cases:
            print(f"\n  测试: {description} ({test_name})")
            
            try:
                # 先清理
                await conn.execute("DELETE FROM news_raw WHERE news_id = $1", f"test_{test_name}")
                
                # 尝试插入
                result = await conn.fetchrow("""
                    INSERT INTO news_raw 
                    (news_id, title, content, source, publish_date, created_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    RETURNING id, publish_date
                """,
                    f"test_{test_name}",
                    f"测试标题 - {test_name}",
                    "测试内容",
                    "test",
                    test_date
                )
                
                print(f"    ✅ 插入成功! ID: {result['id']}, 存储的日期: {result['publish_date']}")
                
                # 清理
                await conn.execute("DELETE FROM news_raw WHERE news_id = $1", f"test_{test_name}")
                
            except Exception as e:
                print(f"    ❌ 插入失败: {e}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    from datetime import date, datetime
    print("开始检查数据库表结构...\n")
    asyncio.run(check_table_structure())
    asyncio.run(test_date_insertion())
    
    print("\n" + "=" * 60)
    print("✅ 检查完成")
    print("=" * 60)

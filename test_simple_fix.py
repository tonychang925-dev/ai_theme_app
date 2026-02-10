#!/usr/bin/env python3
"""
简化修复测试 - 直接测试ID转换
"""
import asyncio
import asyncpg

async def test_id_conversion():
    """测试news_id哈希值到id整数的转换"""
    print("🧪 测试ID转换")
    print("=" * 60)
    
    # 从你提供的示例数据中取一个news_id
    test_hash_ids = [
        "04702f6ddebf7c76935ddaecb73e3aa4",  # 国家发布人工智能发展规划...
        "5a6d1fd1bbfa822b84dd5db60566efe0",  # 新能源汽车1月销量...
        "0ebaf45a128b8f266d237d45b079913b"   # 半导体产业迎政策利好...
    ]
    
    conn = await asyncpg.connect(
        "postgresql://postgres:zxbzj~925@localhost/stock_data"
    )
    
    for hash_id in test_hash_ids:
        print(f"\n🔍 查找: {hash_id}")
        
        # 查找对应的id
        result = await conn.fetchrow(
            "SELECT id, title FROM news_raw WHERE news_id = $1",
            hash_id
        )
        
        if result:
            print(f"   ✅ 找到: id={result['id']}, title='{result['title'][:30]}...'")
            
            # 测试插入news_event
            try:
                await conn.execute("""
                    INSERT INTO news_event 
                    (news_id, event_type, impact_industries, direction, confidence, summary)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT DO NOTHING
                """,
                    result['id'],  # 使用整数id
                    "测试事件",
                    ["科技"],
                    "利好",
                    0.8,
                    "这是一个测试事件"
                )
                print(f"   💾 成功插入news_event")
            except Exception as e:
                print(f"   ❌ 插入失败: {e}")
        else:
            print(f"   ⚠️ 未找到")
    
    # 查看结果
    print(f"\n📊 查看news_event表:")
    events = await conn.fetch("""
        SELECT ne.id, ne.news_id, ne.event_type, ne.summary, nr.news_id as hash_id
        FROM news_event ne
        JOIN news_raw nr ON ne.news_id = nr.id
        ORDER BY ne.created_at DESC
        LIMIT 5
    """)
    
    for i, event in enumerate(events, 1):
        print(f"  {i}. event_id={event['id']}, news_raw.id={event['news_id']}")
        print(f"     哈希: {event['hash_id'][:10]}..., 类型: {event['event_type']}")
    
    await conn.close()
    print("\n✅ 测试完成")

if __name__ == "__main__":
    asyncio.run(test_id_conversion())

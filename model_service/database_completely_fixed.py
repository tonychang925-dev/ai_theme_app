import asyncpg
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import hashlib

class DatabaseManagerFixed:
    """数据库管理器 - 完全修复版"""
    
    @classmethod
    async def get_news_raw_id(cls, news_hash_id: str) -> Optional[int]:
        """获取news_raw表的id - 修复连接管理"""
        print(f"🔍 数据库查找: {news_hash_id[:20]}...")
        
        conn = None
        try:
            conn = await cls.get_connection()
            result = await conn.fetchrow(
                "SELECT id FROM news_raw WHERE news_id = $1",
                news_hash_id
            )
            
            if result:
                print(f"   ✅ 找到记录: ID={result['id']}")
                return result['id']
            else:
                print(f"   ❌ 未找到记录")
                return None
                
        except Exception as e:
            print(f"❌ 查询失败: {e}")
            return None
        finally:
            if conn:
                await conn.close()
                print(f"   🔒 连接已关闭")
    
    @classmethod
    async def save_events(cls, events: List) -> int:
        """保存事件到数据库 - 简化修复版"""
        if not events:
            print("⚠️  没有事件需要保存")
            return 0
        
        print(f"💾 准备保存 {len(events)} 个事件...")
        
        conn = None
        saved_count = 0
        
        try:
            conn = await cls.get_connection()
            
            for i, event in enumerate(events):
                try:
                    print(f"   [{i+1}/{len(events)}] 处理事件...")
                    
                    # 获取事件数据
                    if hasattr(event, 'to_db_dict'):
                        event_data = event.to_db_dict()
                    elif hasattr(event, 'dict'):
                        event_data = event.dict()
                    else:
                        event_data = event
                    
                    # 提取关键字段
                    news_id = event_data.get('news_id')
                    event_type = event_data.get('event_type', '未知')
                    impact_industries = event_data.get('impact_industries', [])
                    direction = event_data.get('direction', '中性')
                    confidence = event_data.get('confidence', 0.5)
                    summary = event_data.get('summary', '')
                    
                    print(f"      新闻ID: {news_id}, 类型: {event_type}")
                    
                    # 执行插入（简化，移除event_uid）
                    result = await conn.execute("""
                        INSERT INTO news_event 
                        (news_id, event_type, impact_industries, direction, confidence, summary)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                        news_id,
                        event_type,
                        json.dumps(impact_industries, ensure_ascii=False),
                        direction,
                        confidence,
                        summary
                    )
                    
                    if "INSERT" in result:
                        saved_count += 1
                        print(f"       ✅ 保存成功")
                    else:
                        print(f"       ⚠️  保存结果: {result}")
                        
                except Exception as e:
                    print(f"       ❌ 保存失败: {e}")
            
            print(f"🎯 保存完成: {saved_count}/{len(events)} 成功")
            return saved_count
            
        except Exception as e:
            print(f"❌ 批量保存失败: {e}")
            return 0
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def get_connection(cls):
        """获取数据库连接"""
        try:
            return await asyncpg.connect(
                "postgresql://postgres:zxbzj~925@localhost/stock_data"
            )
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            raise
    
    @classmethod
    async def initialize_db(cls):
        """初始化数据库表 - 简化版"""
        conn = None
        try:
            conn = await cls.get_connection()
            
            # 检查表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'news_event'
                )
            """)
            
            if not table_exists:
                print("📝 创建news_event表...")
                await conn.execute("""
                    CREATE TABLE news_event (
                        id SERIAL PRIMARY KEY,
                        news_id INTEGER REFERENCES news_raw(id),
                        event_type VARCHAR(50) NOT NULL,
                        impact_industries JSONB DEFAULT '[]',
                        direction VARCHAR(10) DEFAULT 'neutral',
                        confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
                        summary TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                print("✅ news_event表创建成功")
            else:
                print("✅ news_event表已存在")
            
            # 确保索引存在
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_news_event_news_id ON news_event(news_id);
                CREATE INDEX IF NOT EXISTS idx_news_event_created_at ON news_event(created_at);
            """)
            
            print("✅ 数据库初始化完成")
            
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
            raise
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def test_connection(cls):
        """测试数据库连接"""
        print("🧪 测试数据库连接...")
        conn = None
        try:
            conn = await cls.get_connection()
            
            # 测试查询
            result = await conn.fetchval("SELECT COUNT(*) FROM news_raw")
            print(f"✅ 连接成功! news_raw表记录数: {result}")
            
            # 测试news_event表
            result = await conn.fetchval("SELECT COUNT(*) FROM news_event")
            print(f"   news_event表记录数: {result}")
            
            return True
            
        except Exception as e:
            print(f"❌ 连接测试失败: {e}")
            return False
        finally:
            if conn:
                await conn.close()

# 全局实例
db_manager_fixed = DatabaseManagerFixed()

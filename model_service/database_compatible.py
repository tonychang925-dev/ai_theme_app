import asyncpg
from typing import List, Optional, Dict, Any
import json

class DatabaseManager:
    """数据库管理器 - 兼容修复版"""
    
    DB_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    @classmethod
    async def get_news_raw_id(cls, news_hash_id: str) -> Optional[int]:
        """获取news_raw表的id"""
        print(f"🔍 数据库查找: {news_hash_id[:20]}...")
        
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
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
    
    @classmethod
    async def save_events(cls, events: List) -> int:
        """保存事件到数据库 - 修复impact_industries类型问题"""
        if not events:
            print("⚠️  没有事件需要保存")
            return 0
        
        print(f"💾 准备保存 {len(events)} 个事件...")
        
        conn = None
        saved_count = 0
        
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
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
                    
                    # ⭐ 关键修复：正确处理impact_industries字段
                    impact_industries = event_data.get('impact_industries', [])
                    # 确保是列表类型
                    if isinstance(impact_industries, str):
                        try:
                            impact_industries = json.loads(impact_industries)
                        except:
                            impact_industries = [impact_industries]
                    elif not isinstance(impact_industries, list):
                        impact_industries = [impact_industries]
                    
                    direction = event_data.get('direction', '中性')
                    confidence = float(event_data.get('confidence', 0.5))
                    summary = event_data.get('summary', '')
                    
                    print(f"      新闻ID: {news_id}, 类型: {event_type}")
                    print(f"      影响行业: {impact_industries}")
                    
                    # 执行插入
                    result = await conn.execute("""
                        INSERT INTO news_event 
                        (news_id, event_type, impact_industries, direction, confidence, summary)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                        news_id,
                        event_type,
                        impact_industries,  # 直接传递列表
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
    async def initialize_db(cls):
        """初始化数据库表"""
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
            # 简单检查表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'news_event'
                )
            """)
            
            if table_exists:
                print("✅ news_event表已存在")
            else:
                print("⚠️  news_event表不存在，请手动创建")
            
            return True
            
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
            return False
        finally:
            if conn:
                await conn.close()

# 全局实例
db_manager = DatabaseManager()

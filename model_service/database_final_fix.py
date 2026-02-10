import asyncpg
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import hashlib

class DatabaseManagerFinal:
    """数据库管理器 - 最终修复版"""
    
    @classmethod
    async def get_news_raw_id(cls, news_hash_id: str) -> Optional[int]:
        """获取news_raw表的id"""
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
    
    @classmethod
    async def save_events(cls, events: List) -> int:
        """保存事件到数据库 - 最终修复版"""
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
                    
                    # ⭐ 关键修复：正确处理impact_industries字段
                    impact_industries = event_data.get('impact_industries', [])
                    # 确保是列表类型，如果不是则转换
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
                    
                    # ⭐ 关键修复：使用正确的类型插入
                    result = await conn.execute("""
                        INSERT INTO news_event 
                        (news_id, event_type, impact_industries, direction, confidence, summary)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                        news_id,
                        event_type,
                        impact_industries,  # ⭐ 直接传递列表，而不是JSON字符串
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
                    import traceback
                    traceback.print_exc()
            
            print(f"🎯 保存完成: {saved_count}/{len(events)} 成功")
            return saved_count
            
        except Exception as e:
            print(f"❌ 批量保存失败: {e}")
            import traceback
            traceback.print_exc()
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
        """初始化数据库表"""
        conn = None
        try:
            conn = await cls.get_connection()
            
            # 检查表结构
            print("🔍 检查news_event表结构...")
            columns = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'news_event'
                ORDER BY ordinal_position
            """)
            
            print("   表结构:")
            for col in columns:
                print(f"     {col['column_name']:20} {col['data_type']}")
            
            # 检查impact_industries列类型
            impact_col = [c for c in columns if c['column_name'] == 'impact_industries']
            if impact_col:
                print(f"\n⭐ impact_industries列类型: {impact_col[0]['data_type']}")
                if impact_col[0]['data_type'] == 'ARRAY':
                    print("   ✅ 类型正确: ARRAY")
                else:
                    print(f"   ⚠️  类型可能有问题: {impact_col[0]['data_type']}")
            
            print("✅ 数据库检查完成")
            
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
            raise
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def test_save_simple(cls):
        """测试简单保存"""
        print("🧪 测试简单保存...")
        
        conn = None
        try:
            conn = await cls.get_connection()
            
            # 测试不同的数据格式
            test_cases = [
                ("test_array", ["科技"], "数组格式"),
                ("test_string", "科技", "字符串格式"),
                ("test_json", '["科技", "金融"]', "JSON字符串格式"),
                ("test_empty", [], "空数组"),
            ]
            
            for test_name, industries, description in test_cases:
                print(f"\n   测试: {description}")
                
                try:
                    # 使用临时表或现有表测试
                    result = await conn.execute("""
                        INSERT INTO news_event 
                        (news_id, event_type, impact_industries, direction, confidence, summary)
                        VALUES (999, $1, $2, '中性', 0.8, '测试')
                        ON CONFLICT (id) DO NOTHING
                    """,
                        f"test_{test_name}",
                        industries if isinstance(industries, list) else [industries] if isinstance(industries, str) else []
                    )
                    
                    print(f"       ✅ 插入成功: {result}")
                    
                except Exception as e:
                    print(f"       ❌ 插入失败: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
        finally:
            if conn:
                await conn.close()

# 全局实例
db_manager_final = DatabaseManagerFinal()

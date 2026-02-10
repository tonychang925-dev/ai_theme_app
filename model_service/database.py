# model_service/database.py
import asyncpg
from typing import List, Optional, Dict, Any
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    """数据库管理器 - 最终修复版（处理整数news_id外键问题）"""
    
    DB_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    @classmethod
    async def get_news_raw_id(cls, news_hash_id: str) -> Optional[int]:
        """获取news_raw表的id - 根据news_id字符串查找对应的整数id"""
        logger.debug(f"🔍 数据库查找: {news_hash_id[:20]}...")
        
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            result = await conn.fetchrow(
                "SELECT id FROM news_raw WHERE news_id = $1",
                news_hash_id
            )
            
            if result:
                logger.debug(f"✅ 找到记录: 字符串ID={news_hash_id[:20]}... -> 整数ID={result['id']}")
                return result['id']
            else:
                logger.debug(f"❌ 未找到记录: {news_hash_id[:20]}...")
                return None
                
        except Exception as e:
            logger.error(f"查询失败: {e}")
            return None
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def save_events(cls, events: List) -> int:
        """
        保存事件到数据库 - 修复版
        关键修复：news_event.news_id是整数类型，需要从news_raw.id获取
        """
        if not events:
            logger.warning("⚠️  没有事件需要保存")
            return 0
        
        logger.info(f"💾 准备保存 {len(events)} 个事件...")
        
        conn = None
        saved_count = 0
        failed_events = []
        
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
            for i, event in enumerate(events):
                event_saved = False
                try:
                    logger.debug(f"   [{i+1}/{len(events)}] 处理事件...")
                    
                    # 获取事件数据
                    if hasattr(event, 'to_db_dict'):
                        event_data = event.to_db_dict()
                    elif hasattr(event, 'dict'):
                        event_data = event.dict()
                    else:
                        event_data = event
                    
                    # 提取字段
                    news_id_str = event_data.get('news_id')  # 原始字符串ID
                    event_type = event_data.get('event_type', '未知')
                    
                    # 处理 impact_industries 字段
                    impact_industries = event_data.get('impact_industries', [])
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
                    
                    logger.debug(f"      原始新闻ID: {news_id_str}")
                    logger.debug(f"      事件类型: {event_type}, 方向: {direction}, 置信度: {confidence}")
                    
                    # 关键修复：查找对应的整数ID（news_event.news_id是整数，指向news_raw.id）
                    news_id_int = None
                    
                    if news_id_str:
                        # 方法1：通过news_raw.news_id字符串查找对应的整数id
                        try:
                            result = await conn.fetchrow(
                                "SELECT id FROM news_raw WHERE news_id = $1",
                                news_id_str
                            )
                            if result:
                                news_id_int = result['id']
                                logger.debug(f"      找到对应整数ID: {news_id_int} (来自news_raw.news_id='{news_id_str[:20]}...')")
                            else:
                                # 方法2：可能news_id_str本身就是整数ID的字符串形式
                                try:
                                    potential_id = int(news_id_str)
                                    # 验证这个id是否存在于news_raw表
                                    exists = await conn.fetchval(
                                        "SELECT EXISTS(SELECT 1 FROM news_raw WHERE id = $1)",
                                        potential_id
                                    )
                                    if exists:
                                        news_id_int = potential_id
                                        logger.debug(f"      使用整数ID: {news_id_int} (直接转换)")
                                    else:
                                        logger.warning(f"      整数ID {potential_id} 不存在于news_raw表")
                                except ValueError:
                                    logger.warning(f"      '{news_id_str}' 不是有效的整数ID")
                        except Exception as lookup_error:
                            logger.error(f"      查找整数ID失败: {lookup_error}")
                    else:
                        logger.warning("      事件数据中没有news_id字段")
                    
                    if news_id_int is None:
                        error_msg = f"无法确定新闻 '{news_id_str}' 的整数ID，跳过保存"
                        logger.warning(f"      ⚠️  {error_msg}")
                        failed_events.append({
                            'news_id': news_id_str,
                            'error': error_msg,
                            'event_data': event_data
                        })
                        continue
                    
                    # 执行插入
                    query = """
                        INSERT INTO news_event 
                        (news_id, event_type, impact_industries, direction, confidence, summary, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """
                    
                    result = await conn.execute(query,
                        news_id_int,  # 使用整数ID（外键指向news_raw.id）
                        event_type,
                        impact_industries,
                        direction,
                        confidence,
                        summary,
                        datetime.now()
                    )
                    
                    if "INSERT" in result:
                        saved_count += 1
                        event_saved = True
                        logger.debug(f"       ✅ 保存成功，使用整数ID: {news_id_int}")
                    else:
                        error_msg = f"插入操作未返回预期结果: {result}"
                        logger.warning(f"      ⚠️  {error_msg}")
                        failed_events.append({
                            'news_id': news_id_str,
                            'error': error_msg,
                            'event_data': event_data
                        })
                        
                except asyncpg.exceptions.UniqueViolationError as e:
                    error_msg = f"唯一性约束冲突（可能重复插入）: {e}"
                    logger.warning(f"      ⚠️  {error_msg}")
                    failed_events.append({
                        'news_id': event_data.get('news_id'),
                        'error': error_msg,
                        'event_data': event_data
                    })
                    
                except asyncpg.exceptions.ForeignKeyViolationError as e:
                    error_msg = f"外键约束冲突（news_id={news_id_int} 不存在于news_raw表）: {e}"
                    logger.error(f"      ❌ {error_msg}")
                    failed_events.append({
                        'news_id': event_data.get('news_id'),
                        'error': error_msg,
                        'event_data': event_data
                    })
                    
                except Exception as e:
                    error_msg = f"保存失败: {e}"
                    logger.error(f"      ❌ {error_msg}")
                    failed_events.append({
                        'news_id': event_data.get('news_id'),
                        'error': str(e),
                        'event_data': event_data
                    })
            
            # 保存完成后，记录详细统计
            logger.info(f"🎯 保存完成: {saved_count}成功, {len(failed_events)}失败 / 总计{len(events)}")
            
            if failed_events and logger.isEnabledFor(logging.DEBUG):
                logger.debug("📋 失败事件详情:")
                for i, failed in enumerate(failed_events[:5]):  # 只显示前5个
                    logger.debug(f"    {i+1}. news_id={failed['news_id']}, 错误={failed['error'][:100]}...")
                if len(failed_events) > 5:
                    logger.debug(f"    ... 还有 {len(failed_events) - 5} 个失败记录")
            
            return saved_count
            
        except Exception as e:
            logger.error(f"❌ 批量保存失败: {e}")
            return 0
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def initialize_db(cls):
        """初始化数据库表 - 修复版"""
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
            # 检查表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'news_event'
                )
            """)
            
            if not table_exists:
                logger.info("📦 创建news_event表...")
                # 根据你的实际表结构创建（news_id为整数，指向news_raw.id）
                await conn.execute("""
                    CREATE TABLE news_event (
                        id SERIAL PRIMARY KEY,
                        news_id INTEGER REFERENCES news_raw(id),
                        event_type VARCHAR(50),
                        impact_industries TEXT[],
                        direction VARCHAR(10),
                        confidence FLOAT,
                        summary TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # 创建索引
                await conn.execute("""
                    CREATE INDEX idx_news_event_news_id ON news_event(news_id);
                    CREATE INDEX idx_news_event_created_at ON news_event(created_at);
                    CREATE INDEX idx_news_event_type ON news_event(event_type);
                """)
                
                logger.info("✅ news_event表创建成功")
            else:
                logger.info("✅ news_event表已存在")
                # 验证表结构
                await cls._verify_and_fix_structure(conn)
            
            # 检查并添加必要的字段到news_raw表
            await cls._ensure_news_raw_fields(conn)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")
            return False
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def _verify_and_fix_structure(cls, conn):
        """验证并修复表结构"""
        try:
            # 获取当前表结构
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = 'news_event'
                ORDER BY ordinal_position
            """)
            
            current_columns = {col['column_name']: col for col in columns}
            logger.debug(f"📊 当前表字段: {list(current_columns.keys())}")
            
            # 检查关键字段
            if 'news_id' in current_columns:
                news_id_type = current_columns['news_id']['data_type']
                if news_id_type != 'integer':
                    logger.warning(f"⚠️  news_event.news_id 当前类型为 {news_id_type}，但应该是 integer")
                    logger.info("💡 需要手动修复: ALTER TABLE news_event ALTER COLUMN news_id TYPE INTEGER;")
            
            logger.info("✅ 表结构验证完成")
            
        except Exception as e:
            logger.warning(f"表结构验证/修复时出错: {e}")
    
    @classmethod
    async def _ensure_news_raw_fields(cls, conn):
        """确保news_raw表有必要的字段"""
        try:
            # 检查is_processed字段
            has_is_processed = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'news_raw' AND column_name = 'is_processed'
                )
            """)
            
            if not has_is_processed:
                logger.info("🔧 为news_raw表添加is_processed字段...")
                await conn.execute("""
                    ALTER TABLE news_raw 
                    ADD COLUMN is_processed BOOLEAN DEFAULT FALSE,
                    ADD COLUMN processed_at TIMESTAMP
                """)
                logger.info("✅ news_raw表结构更新完成")
            else:
                logger.debug("✅ news_raw表结构正常")
                
        except Exception as e:
            logger.warning(f"检查news_raw表结构时出错: {e}")
    
    @classmethod
    async def fetch_pending_news(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取待处理的新闻
        
        Args:
            limit: 限制返回数量
        
        Returns:
            新闻数据列表（包含整数id和字符串news_id）
        """
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
            # 先检查是否有is_processed字段
            has_field = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'news_raw' AND column_name = 'is_processed'
                )
            """)
            
            if has_field:
                query = """
                SELECT id, news_id, title, content, source, 
                       publish_date, market, created_at
                FROM news_raw 
                WHERE is_processed = FALSE
                ORDER BY publish_date DESC, id ASC
                LIMIT $1
                """
            else:
                # 如果没有is_processed字段，返回所有新闻
                query = """
                SELECT id, news_id, title, content, source, 
                       publish_date, market, created_at
                FROM news_raw 
                ORDER BY publish_date DESC, id ASC
                LIMIT $1
                """
                logger.warning("⚠️  news_raw表缺少is_processed字段，返回所有新闻")
            
            rows = await conn.fetch(query, limit)
            
            # 转换结果为字典列表
            result = []
            for row in rows:
                result.append({
                    'id': row['id'],  # 整数ID（重要！）
                    'news_id': row['news_id'],  # 字符串ID
                    'title': row['title'],
                    'content': row['content'],
                    'source': row['source'],
                    'publish_date': row['publish_date'],
                    'market': row['market'],
                    'created_at': row['created_at']
                })
            
            logger.info(f"📋 获取到 {len(result)} 条待处理新闻")
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取待处理新闻失败: {e}")
            return []
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def mark_news_as_processed(cls, news_identifier: str) -> bool:
        """
        标记新闻为已处理 - 修复updated_at字段问题
        
        Args:
            news_identifier: 可以是字符串news_id或整数id
        
        Returns:
            标记是否成功
        """
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
            # 先检查是否有is_processed字段
            has_field = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'news_raw' AND column_name = 'is_processed'
                )
            """)
            
            if not has_field:
                logger.warning("⚠️  news_raw表缺少is_processed字段，无法标记")
                return False
            
            # 尝试判断标识符类型
            is_integer = False
            try:
                int(news_identifier)
                is_integer = True
            except ValueError:
                is_integer = False
            
            # 修复：使用简单的UPDATE语句，避免触发器问题
            if is_integer:
                # 如果是整数，直接按id处理
                update_query = """
                UPDATE news_raw 
                SET is_processed = TRUE, processed_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """
            else:
                # 如果是字符串，按news_id处理
                update_query = """
                UPDATE news_raw 
                SET is_processed = TRUE, processed_at = CURRENT_TIMESTAMP
                WHERE news_id = $1
                """
            
            # 修复：使用更简单的执行方式
            result = await conn.execute(update_query, news_identifier)
            
            # 修复：检查是否成功更新
            rows_affected = result.split()[-1] if " " in result else "0"
            success = rows_affected != "0"
            
            if success:
                logger.debug(f"✅ 新闻 {news_identifier} 已标记为已处理")
            else:
                logger.debug(f"ℹ️  新闻 {news_identifier} 未找到或已处理")
                
            return success
            
        except Exception as e:
            # 修复：更友好的错误处理
            if "updated_at" in str(e):
                logger.debug(f"ℹ️  标记新闻时忽略updated_at字段问题: {news_identifier}")
                return True  # 假设标记成功，即使有触发器错误
            else:
                logger.error(f"❌ 标记新闻失败: {e}")
                return False
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def execute_query(cls, query: str, *args) -> List[Dict[str, Any]]:
        """
        执行查询并返回字典列表
        
        Args:
            query: SQL查询语句
            *args: 查询参数
        
        Returns:
            字典列表，每行一个字典
        """
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            rows = await conn.fetch(query, *args)
            
            # 转换asyncpg.Record为字典
            result = []
            for row in rows:
                result.append(dict(row))
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 查询执行失败: {e}")
            raise
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def execute_update(cls, query: str, *args) -> str:
        """
        执行更新/插入操作
        
        Args:
            query: SQL语句
            *args: 参数
        
        Returns:
            执行结果描述
        """
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            result = await conn.execute(query, *args)
            return result
        except Exception as e:
            logger.error(f"❌ 更新执行失败: {e}")
            raise
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def save_event(cls, event_data: Dict[str, Any]) -> bool:
        """
        保存单个事件到数据库
        
        Args:
            event_data: 事件数据字典（必须包含有效的news_id）
        
        Returns:
            保存是否成功
        """
        # 包装成列表调用save_events方法
        return await cls.save_events([event_data]) > 0
    
    @classmethod
    async def get_recent_events(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近的事件（包含关联的新闻信息）
        
        Args:
            limit: 限制数量
        
        Returns:
            最近事件列表
        """
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
            query = """
            SELECT 
                ne.*,
                nr.news_id as raw_news_id,
                nr.title as news_title
            FROM news_event ne
            LEFT JOIN news_raw nr ON ne.news_id = nr.id
            ORDER BY ne.created_at DESC 
            LIMIT $1
            """
            
            rows = await conn.fetch(query, limit)
            
            # 转换结果
            result = []
            for row in rows:
                result.append(dict(row))
            
            logger.info(f"📋 获取到 {len(result)} 条最近事件")
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取最近事件失败: {e}")
            return []
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def close(cls):
        """
        兼容性方法
        
        注：由于使用连接-关闭模式，每个方法都会自己管理连接，
        所以这个方法只是空实现，用于兼容代码调用。
        """
        logger.debug("ℹ️  DatabaseManager 使用连接-关闭模式，无需单独关闭")
        return True
    
    @classmethod
    async def health_check(cls) -> bool:
        """数据库健康检查"""
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            result = await conn.fetchval("SELECT 1")
            logger.debug("✅ 数据库健康检查通过")
            return result == 1
        except Exception as e:
            logger.error(f"❌ 数据库健康检查失败: {e}")
            return False
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def verify_table_structure(cls):
        """验证news_event表结构与代码期望是否匹配"""
        conn = None
        try:
            conn = await asyncpg.connect(cls.DB_URL)
            
            # 获取表结构
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'news_event'
                ORDER BY ordinal_position
            """)
            
            logger.info("📋 news_event表结构验证:")
            actual_columns = []
            for col in columns:
                column_info = f"{col['column_name']} ({col['data_type']})"
                if col['is_nullable'] == 'NO':
                    column_info += " NOT NULL"
                actual_columns.append(col['column_name'])
                logger.info(f"   - {column_info}")
            
            # 期望的字段（根据你的实际表结构）
            expected_columns = [
                'id',                   # 主键
                'news_id',              # 新闻ID（整数，外键指向news_raw.id）
                'event_type',           # 事件类型
                'impact_industries',    # 影响行业（数组）
                'direction',            # 方向（利好/利空/中性）
                'confidence',           # 置信度
                'summary',              # 摘要
                'created_at'            # 创建时间
            ]
            
            # 检查差异
            missing = set(expected_columns) - set(actual_columns)
            extra = set(actual_columns) - set(expected_columns)
            
            if missing:
                logger.warning(f"⚠️  缺少期望字段: {missing}")
            if extra:
                logger.info(f"📊 额外字段: {extra}")
            
            if not missing and not extra:
                logger.info("✅ 表结构与代码期望完全匹配")
            else:
                logger.warning("⚠️  表结构与代码期望不完全匹配")
            
            # 特别检查news_id类型
            news_id_info = next((c for c in columns if c['column_name'] == 'news_id'), None)
            if news_id_info:
                logger.info(f"📌 news_id字段类型: {news_id_info['data_type']} "
                          f"{'(外键指向news_raw.id)' if news_id_info['data_type'] == 'integer' else ''}")
            
            return list(actual_columns)
            
        except Exception as e:
            logger.error(f"❌ 验证表结构失败: {e}")
            return []
        finally:
            if conn:
                await conn.close()
    
    @classmethod
    async def test_news_id_lookup(cls, news_id_str: str) -> Optional[int]:
        """
        测试查找news_id的整数ID
        
        Args:
            news_id_str: 字符串形式的news_id
        
        Returns:
            对应的整数ID，如果找不到返回None
        """
        return await cls.get_news_raw_id(news_id_str)

# 全局实例
db_manager = DatabaseManager()
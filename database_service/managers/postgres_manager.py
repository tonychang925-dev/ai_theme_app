# database_service/managers/postgres_manager.py
"""
PostgreSQL数据库管理器 - 适配实际theme_master表结构
基于实际的28字段表结构，包含申万行业分类
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional, AsyncContextManager
from datetime import datetime
import asyncpg
from asyncpg.pool import Pool
import json


try:
    # 尝试相对导入（正常包情况下）
    from .base_manager import BaseDatabaseManager
except ImportError:
    # 回退到绝对导入（测试脚本情况下）
    from database_service.managers.base_manager import BaseDatabaseManager

try:
    # 尝试相对导入（正常包情况下）
    from ..interface import DatabaseManager, ThemeRecord, EventThemeRelation, ThemeTags
except ImportError:
    # 回退到绝对导入（测试脚本情况下）
    from database_service.interface import DatabaseManager, ThemeRecord, EventThemeRelation, ThemeTags

try:
    from database_service.config import ConnectionPoolConfig
except ImportError:
    # 后备方案
    from config import ConnectionPoolConfig

logger = logging.getLogger(__name__)

class PostgresDatabaseManager(BaseDatabaseManager):
    """PostgreSQL数据库管理器"""
    
    def __init__(self, config):
        super().__init__(config)
        self.pool: Optional[Pool] = None
        self.schema = config.postgres_schema
    
    async def connect(self) -> None:
        """连接PostgreSQL数据库池"""
        try:
            # 构建连接字符串
            dsn = self._build_dsn()
            
            # 创建连接池
            pool_config = self.config.connection_pool
            self.pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=pool_config.min_size,
                max_size=pool_config.max_size,
                max_queries=pool_config.max_queries,
                max_inactive_connection_lifetime=pool_config.max_inactive_connection_lifetime,
                command_timeout=pool_config.command_timeout,
                server_settings={
                    'search_path': f'{self.schema},public',
                    'application_name': 'database_service'
                }
            )
            
            # 测试连接
            async with self.pool.acquire() as conn:
                await conn.execute('SELECT 1')
            
            self.connected = True
            logger.info(f"✅ PostgreSQL连接成功: {self.config.postgres_host}:{self.config.postgres_port}")
            
        except Exception as e:
            logger.error(f"❌ PostgreSQL连接失败: {e}")
            raise
    
    def _build_dsn(self) -> str:
        """构建DSN连接字符串"""
        password_part = f":{self.config.postgres_password}" if self.config.postgres_password else ""
        return (f"postgresql://{self.config.postgres_username}{password_part}"
                f"@{self.config.postgres_host}:{self.config.postgres_port}"
                f"/{self.config.postgres_database}")
    
    async def disconnect(self) -> None:
        """断开连接"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            self.connected = False
            logger.info("PostgreSQL连接已关闭")
    
    def transaction(self) -> AsyncContextManager:
        """事务上下文管理器"""
        return self.pool.acquire()  # 简化实现，实际需要包装
    
    async def health_check(self) -> bool:
        """健康检查"""
        if not self.pool:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval('SELECT 1')
                return result == 1
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    # ========== 主题操作 ==========
    
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """获取主题（按ID）"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at
                    FROM theme_master
                    WHERE id = $1 AND status = 'active'
                """, theme_id)
                
                if row:
                    return self._build_theme_record(row)
                return None
                
        except Exception as e:
            logger.error(f"获取主题失败 {theme_id}: {e}")
            raise
    
    async def get_theme_by_code(self, code: str) -> Optional[ThemeRecord]:
        """获取主题（按code）"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at
                    FROM theme_master
                    WHERE code = $1 AND status = 'active'
                """, code)
                
                if row:
                    return self._build_theme_record(row)
                return None
                
        except Exception as e:
            logger.error(f"获取主题失败 code={code}: {e}")
            raise
    
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at
                    FROM theme_master
                    WHERE name = $1 AND status = 'active'
                """, name)
                
                if row:
                    return self._build_theme_record(row)
                return None
                
        except Exception as e:
            logger.error(f"获取主题失败 name={name}: {e}")
            raise
    
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """获取所有活跃主题"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at
                    FROM theme_master
                    WHERE status = 'active'
                    ORDER BY heat_score DESC, last_active_at DESC
                    LIMIT $1
                """, limit)
                
                themes = []
                for row in rows:
                    theme = self._build_theme_record(row)
                    themes.append(theme)
                
                logger.info(f"✅ 从数据库获取 {len(themes)} 个活跃主题")
                return themes
                
        except Exception as e:
            logger.error(f"获取活跃主题失败: {e}")
            raise
    
    def _build_theme_record(self, row) -> ThemeRecord:
        """从数据库行构建ThemeRecord - 修复字符串JSONB问题"""
        try:
            # 处理tags字段
            tags_data = row.get('tags', {})
            
            # 🔥 关键修复：asyncpg返回JSONB字段为字符串，需要解析
            if isinstance(tags_data, str):
                try:
                    import json
                    # 解析JSON字符串
                    tags_data = json.loads(tags_data)
                    logger.debug(f"成功解析JSON字符串，keywords: {tags_data.get('keywords', [])}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e}, 字符串: {tags_data[:100]}...")
                    tags_data = {}
                except Exception as e:
                    logger.error(f"解析tags失败: {e}")
                    tags_data = {}
            
            # 如果是asyncpg的特殊类型，尝试转换
            elif not isinstance(tags_data, dict):
                # 尝试各种转换方法
                try:
                    # 如果是asyncpg.Record
                    if hasattr(tags_data, '_asdict'):
                        tags_data = tags_data._asdict()
                    # 如果支持转换为字典
                    elif hasattr(tags_data, '__getitem__'):
                        tags_data = dict(tags_data)
                    else:
                        logger.warning(f"无法处理的tags_data类型: {type(tags_data)}")
                        tags_data = {}
                except Exception as e:
                    logger.error(f"转换tags_data失败: {e}")
                    tags_data = {}
            
            # 确保tags_data是字典
            if not isinstance(tags_data, dict):
                logger.warning(f"tags_data不是字典，设为空: {type(tags_data)}")
                tags_data = {}
            
            # 🔥 验证keywords字段
            keywords = tags_data.get('keywords')
            if keywords is None:
                logger.debug(f"keywords字段不存在，设为空列表")
                tags_data['keywords'] = []
            elif not isinstance(keywords, list):
                logger.warning(f"keywords不是列表: {type(keywords)}，尝试转换")
                try:
                    if isinstance(keywords, (str, int, float)):
                        tags_data['keywords'] = [str(keywords)]
                    else:
                        tags_data['keywords'] = list(keywords)
                except:
                    tags_data['keywords'] = []
            
            # 创建ThemeTags对象
            tags = ThemeTags(
                source=tags_data.get('source', 'shenwan'),
                aliases=tags_data.get('aliases', []),
                version=tags_data.get('version', '2.0'),
                concepts=tags_data.get('concepts', []),
                keywords=tags_data.get('keywords', []),
                heat_level=tags_data.get('heat_level', 'medium'),
                industries=tags_data.get('industries', []),
                industry_code=tags_data.get('industry_code'),
                merge_candidates=tags_data.get('merge_candidates', [])
            )
            
            # 记录日志
            logger.debug(f"构建ThemeRecord: {row.get('name')}")
            logger.debug(f"  keywords数量: {len(tags.keywords)}")
            if tags.keywords:
                logger.debug(f"  前3个keywords: {tags.keywords[:3]}")
            
            # 构建ThemeRecord
            theme = ThemeRecord(
                id=row.get('id'),
                name=row.get('name'),
                code=row.get('code'),
                description=row.get('description'),
                status=row.get('status'),
                level1_category=row.get('level1_category'),
                level2_category=row.get('level2_category'),
                level3_category=row.get('level3_category'),
                category_path=row.get('category_path') or [],
                category1_code=row.get('category1_code'),
                category2_code=row.get('category2_code'),
                category3_code=row.get('category3_code'),
                tags=tags,
                theme_type=row.get('theme_type'),
                heat_score=row.get('heat_score') or 50,
                confidence_score=float(row.get('confidence_score') or 0.8),
                lifecycle_stage=row.get('lifecycle_stage'),
                related_stocks=row.get('related_stocks') or [],
                stock_count=row.get('stock_count') or 0,
                news_count=row.get('news_count') or 0,
                mention_count=row.get('mention_count') or 0,
                last_mentioned=row.get('last_mentioned'),
                source_system=row.get('source_system'),
                source_id=row.get('source_id'),
                created_by=row.get('created_by'),
                created_at=row.get('created_at'),
                updated_at=row.get('updated_at'),
                last_active_at=row.get('last_active_at')
            )
            
            return theme
            
        except Exception as e:
            logger.error(f"构建ThemeRecord失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            
            # 返回一个最小化的ThemeRecord
            return ThemeRecord(
                id=row.get('id', 0),
                name=row.get('name', 'Unknown'),
                code=row.get('code', 'UNKNOWN'),
                tags=ThemeTags()
            )
    
    async def create_theme(self, name: str, code: str, **kwargs) -> ThemeRecord:
        """创建新主题"""
        try:
            async with self.pool.acquire() as conn:
                # 检查是否已存在（按code）
                existing = await conn.fetchrow("""
                    SELECT id FROM theme_master 
                    WHERE code = $1
                """, code)
                
                if existing:
                    raise Exception(f"主题已存在 (code={code})")
                
                # 处理tags字段
                tags_data = kwargs.get('tags', {})
                if isinstance(tags_data, ThemeTags):
                    tags_data = tags_data.to_dict()
                
                # 关键修复：将字典转换为JSON字符串（解决asyncpg jsonb参数问题）
                if isinstance(tags_data, dict):
                    tags_data = json.dumps(tags_data, ensure_ascii=False)
                
                # 插入新主题
                row = await conn.fetchrow("""
                    INSERT INTO theme_master 
                    (name, code, description, status,
                     level1_category, level2_category, level3_category,
                     category_path, category1_code, category2_code, category3_code,
                     tags, theme_type, heat_score, confidence_score,
                     lifecycle_stage, related_stocks, stock_count,
                     news_count, mention_count, source_system, source_id, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23)
                    RETURNING *
                """, 
                    name,
                    code,
                    kwargs.get('description'),
                    kwargs.get('status', 'active'),
                    kwargs.get('level1_category'),
                    kwargs.get('level2_category'),
                    kwargs.get('level3_category'),
                    kwargs.get('category_path', []),
                    kwargs.get('category1_code'),
                    kwargs.get('category2_code'),
                    kwargs.get('category3_code'),
                    tags_data,  # 现在使用JSON字符串
                    kwargs.get('theme_type', 'investment'),
                    kwargs.get('heat_score', 50),
                    kwargs.get('confidence_score', 0.80),
                    kwargs.get('lifecycle_stage', 'growth'),
                    kwargs.get('related_stocks', []),
                    kwargs.get('stock_count', 0),
                    kwargs.get('news_count', 0),
                    kwargs.get('mention_count', 0),
                    kwargs.get('source_system', 'transformed'),
                    kwargs.get('source_id'),
                    kwargs.get('created_by', 'system')
                )
                
                theme = self._build_theme_record(row)
                logger.info(f"✅ 创建新主题: {name} (code: {code}, ID: {theme.id})")
                return theme
                
        except Exception as e:
            logger.error(f"创建主题失败 {name}: {e}")
            raise
    
    async def update_theme(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题"""
        try:
            async with self.pool.acquire() as conn:
                # 构建SET子句
                set_clauses = []
                values = []
                index = 1
                
                for key, value in updates.items():
                    if key == 'tags' and isinstance(value, ThemeTags):
                        value = value.to_dict()
                    
                    # 关键修复：如果更新tags字段，将字典转换为JSON字符串
                    if key == 'tags' and isinstance(value, dict):
                        value = json.dumps(value, ensure_ascii=False)
                    
                    set_clauses.append(f"{key} = ${index}")
                    values.append(value)
                    index += 1
                
                # 添加updated_at
                set_clauses.append("updated_at = NOW()")
                set_clauses.append("last_active_at = NOW()")
                
                query = f"""
                    UPDATE theme_master
                    SET {', '.join(set_clauses)}
                    WHERE id = ${index} AND status = 'active'
                    RETURNING *
                """
                values.append(theme_id)
                
                row = await conn.fetchrow(query, *values)
                
                if row:
                    theme = self._build_theme_record(row)
                    logger.info(f"✅ 更新主题: {theme.name} (ID: {theme_id})")
                    return theme
                
                return None
                
        except Exception as e:
            logger.error(f"更新主题失败 {theme_id}: {e}")
            raise
    
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE theme_master
                    SET heat_score = COALESCE(heat_score, 50) + $1,
                        updated_at = NOW(),
                        last_active_at = NOW()
                    WHERE id = $2
                """, increment, theme_id)
                
                logger.debug(f"✅ 增加主题热度: theme_id={theme_id}, increment={increment}")
                
        except Exception as e:
            logger.error(f"增加主题热度失败 {theme_id}: {e}")
            raise
    
    async def increment_mention_count(self, theme_id: int, increment: int = 1) -> None:
        """增加提及次数"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE theme_master
                    SET mention_count = COALESCE(mention_count, 0) + $1,
                        last_mentioned = NOW(),
                        updated_at = NOW(),
                        last_active_at = NOW()
                    WHERE id = $2
                """, increment, theme_id)
                
                logger.debug(f"✅ 增加提及次数: theme_id={theme_id}, increment={increment}")
                
        except Exception as e:
            logger.error(f"增加提及次数失败 {theme_id}: {e}")
            raise
    
    async def find_related_themes(self, event_data: Dict[str, Any], limit: int = 5) -> List[ThemeRecord]:
        """查找相关主题 - 基于关键词匹配"""
        try:
            # 提取事件关键词
            event_keywords = []
            if 'keywords' in event_data:
                event_keywords = event_data['keywords']
            elif 'impact_industries' in event_data:
                event_keywords = event_data['impact_industries']
            
            if not event_keywords:
                logger.debug("事件无关键词，无法查找相关主题")
                return []
            
            # 将关键词转换为tsquery格式
            keyword_string = " | ".join(event_keywords)
            
            async with self.pool.acquire() as conn:
                # 使用全文搜索 + JSONB字段查询
                query = """
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at,
                        
                        -- 计算相关度评分
                        (
                            -- 名称匹配
                            CASE WHEN name ILIKE ANY($1) THEN 3 ELSE 0 END +
                            -- 关键词匹配（JSONB数组）
                            CASE WHEN tags->'keywords' ?| $1 THEN 2 ELSE 0 END +
                            -- 别名匹配（JSONB数组）
                            CASE WHEN tags->'aliases' ?| $1 THEN 2 ELSE 0 END +
                            -- 分类匹配
                            CASE WHEN level1_category ILIKE ANY($1) OR 
                                  level2_category ILIKE ANY($1) OR 
                                  level3_category ILIKE ANY($1) THEN 1 ELSE 0 END
                        ) as relevance_score
                        
                    FROM theme_master
                    WHERE status = 'active'
                    AND (
                        name ILIKE ANY($1) OR
                        tags->'keywords' ?| $1 OR
                        tags->'aliases' ?| $1 OR
                        level1_category ILIKE ANY($1) OR
                        level2_category ILIKE ANY($1) OR
                        level3_category ILIKE ANY($1)
                    )
                    ORDER BY relevance_score DESC, heat_score DESC
                    LIMIT $2
                """
                
                # 构建搜索数组
                search_terms = [f"%{kw}%" for kw in event_keywords]
                
                rows = await conn.fetch(query, search_terms, limit)
                
                themes = []
                for row in rows:
                    theme = self._build_theme_record(row)
                    # 设置相关度评分
                    theme.relevance_score = row.get('relevance_score', 0)
                    # 设置匹配的关键词
                    theme.matched_keywords = [
                        kw for kw in event_keywords 
                        if (kw in theme.name or 
                            kw in theme.tags.keywords or 
                            kw in theme.tags.aliases or
                            kw in theme.category_path)
                    ]
                    themes.append(theme)
                
                logger.info(f"✅ 找到 {len(themes)} 个相关主题")
                return themes
                
        except Exception as e:
            logger.error(f"查找相关主题失败: {e}")
            return []
    
    async def get_themes_by_keywords(self, keywords: List[str], limit: int = 20) -> List[ThemeRecord]:
        """根据关键词获取主题"""
        try:
            # 简化版本，调用find_related_themes
            return await self.find_related_themes(
                {"keywords": keywords},
                limit=limit
            )
        except Exception as e:
            logger.error(f"关键词搜索失败: {e}")
            return []
    
    async def get_themes_by_category(self, category_code: str, level: int = 1, limit: int = 50) -> List[ThemeRecord]:
        """根据分类代码获取主题"""
        try:
            async with self.pool.acquire() as conn:
                # 根据级别选择不同的字段
                if level == 1:
                    field = 'category1_code'
                elif level == 2:
                    field = 'category2_code'
                elif level == 3:
                    field = 'category3_code'
                else:
                    raise ValueError(f"无效的分类级别: {level}")
                
                rows = await conn.fetch(f"""
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at
                    FROM theme_master
                    WHERE status = 'active'
                    AND {field} = $1
                    ORDER BY heat_score DESC
                    LIMIT $2
                """, category_code, limit)
                
                themes = []
                for row in rows:
                    theme = self._build_theme_record(row)
                    themes.append(theme)
                
                logger.info(f"✅ 根据分类找到 {len(themes)} 个主题 (level={level}, code={category_code})")
                return themes
                
        except Exception as e:
            logger.error(f"分类搜索失败: {e}")
            return []
    
    async def get_themes_by_heat_level(self, min_heat: int = 60, limit: int = 100) -> List[ThemeRecord]:
        """获取热度较高的主题"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at
                    FROM theme_master
                    WHERE status = 'active'
                    AND heat_score >= $1
                    ORDER BY heat_score DESC, last_active_at DESC
                    LIMIT $2
                """, min_heat, limit)
                
                themes = []
                for row in rows:
                    theme = self._build_theme_record(row)
                    themes.append(theme)
                
                logger.info(f"✅ 获取到 {len(themes)} 个高热主题 (min_heat={min_heat})")
                return themes
                
        except Exception as e:
            logger.error(f"获取高热主题失败: {e}")
            return []
    
    async def batch_create_themes(self, themes_data: List[Dict[str, Any]]) -> List[ThemeRecord]:
        """批量创建主题"""
        try:
            themes = []
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for data in themes_data:
                        try:
                            # 处理tags字段
                            tags_data = data.get('tags', {})
                            if isinstance(tags_data, ThemeTags):
                                tags_data = tags_data.to_dict()
                            
                            # 关键修复：将字典转换为JSON字符串（解决asyncpg jsonb参数问题）
                            if isinstance(tags_data, dict):
                                tags_data = json.dumps(tags_data, ensure_ascii=False)
                            
                            row = await conn.fetchrow("""
                                INSERT INTO theme_master 
                                (name, code, description, status,
                                 level1_category, level2_category, level3_category,
                                 category_path, category1_code, category2_code, category3_code,
                                 tags, theme_type, heat_score, confidence_score,
                                 lifecycle_stage, related_stocks, stock_count,
                                 news_count, mention_count, source_system, source_id, created_by)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23)
                                ON CONFLICT (code) DO NOTHING
                                RETURNING *
                            """, 
                                data['name'],
                                data['code'],
                                data.get('description'),
                                data.get('status', 'active'),
                                data.get('level1_category'),
                                data.get('level2_category'),
                                data.get('level3_category'),
                                data.get('category_path', []),
                                data.get('category1_code'),
                                data.get('category2_code'),
                                data.get('category3_code'),
                                tags_data,  # 现在使用JSON字符串
                                data.get('theme_type', 'investment'),
                                data.get('heat_score', 50),
                                data.get('confidence_score', 0.80),
                                data.get('lifecycle_stage', 'growth'),
                                data.get('related_stocks', []),
                                data.get('stock_count', 0),
                                data.get('news_count', 0),
                                data.get('mention_count', 0),
                                data.get('source_system', 'transformed'),
                                data.get('source_id'),
                                data.get('created_by', 'system')
                            )
                            
                            if row:
                                theme = self._build_theme_record(row)
                                themes.append(theme)
                            
                        except Exception as e:
                            logger.warning(f"批量创建主题失败 {data.get('name')}: {e}")
                            continue
            
            logger.info(f"✅ 批量创建 {len(themes)}/{len(themes_data)} 个主题")
            return themes
            
        except Exception as e:
            logger.error(f"批量创建主题失败: {e}")
            return []
    
    async def search_themes(self, query: str, limit: int = 10) -> List[ThemeRecord]:
        """搜索主题（支持名称、描述、关键词搜索）"""
        try:
            async with self.pool.acquire() as conn:
                # 使用PostgreSQL的全文搜索
                rows = await conn.fetch("""
                    SELECT 
                        id, name, code, description, status,
                        level1_category, level2_category, level3_category,
                        category_path, category1_code, category2_code, category3_code,
                        tags, theme_type, heat_score, confidence_score,
                        lifecycle_stage, related_stocks, stock_count,
                        news_count, mention_count, last_mentioned,
                        source_system, source_id, created_by,
                        created_at, updated_at, last_active_at,
                        
                        -- 搜索相关度
                        ts_rank(
                            to_tsvector('simple', COALESCE(name, '') || ' ' || 
                                        COALESCE(description, '') || ' ' ||
                                        array_to_string(COALESCE(tags->'keywords', '{}'), ' ')),
                            plainto_tsquery('simple', $1)
                        ) as search_rank
                        
                    FROM theme_master
                    WHERE status = 'active'
                    AND (
                        name ILIKE $2 OR
                        description ILIKE $2 OR
                        level1_category ILIKE $2 OR
                        level2_category ILIKE $2 OR
                        level3_category ILIKE $2 OR
                        tags->'keywords' ?| ARRAY[$1]
                    )
                    ORDER BY search_rank DESC, heat_score DESC
                    LIMIT $3
                """, query, f"%{query}%", limit)
                
                themes = []
                for row in rows:
                    theme = self._build_theme_record(row)
                    themes.append(theme)
                
                logger.info(f"✅ 搜索到 {len(themes)} 个相关主题 (query={query})")
                return themes
                
        except Exception as e:
            logger.error(f"搜索主题失败: {e}")
            return []
    
    # ========== 事件-主题关联 ==========
    
    async def create_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> EventThemeRelation:
        """创建事件-主题关联"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    INSERT INTO event_theme_map 
                    (event_id, theme_id, confidence, confidence_level, confidence_weight, evidence, match_type, matched_keywords)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id, event_id, theme_id, confidence, 
                             confidence_level, confidence_weight, evidence, 
                             match_type, matched_keywords, created_at
                """,
                    event_id,
                    theme_id,
                    kwargs.get('confidence', 0.8),
                    kwargs.get('confidence_level', 'medium'),
                    kwargs.get('confidence_weight', 50),
                    kwargs.get('evidence'),
                    kwargs.get('match_type', 'keyword'),
                    kwargs.get('matched_keywords', [])
                )
                
                if row:
                    relation = EventThemeRelation(
                        id=row['id'],
                        event_id=row['event_id'],
                        theme_id=row['theme_id'],
                        confidence=row['confidence'],
                        confidence_level=row['confidence_level'],
                        confidence_weight=row['confidence_weight'],
                        evidence=row['evidence'],
                        match_type=row['match_type'],
                        matched_keywords=row['matched_keywords'] or [],
                        created_at=row['created_at']
                    )
                    
                    # 更新主题统计
                    await self.increment_mention_count(theme_id)
                    
                    logger.info(f"✅ 创建事件-主题关联: event={event_id}, theme={theme_id}")
                    return relation
                
                raise Exception("创建关联失败")
                
        except Exception as e:
            logger.error(f"创建关联失败 event={event_id}, theme={theme_id}: {e}")
            raise
    
    async def get_event_themes(self, event_id: int) -> List[EventThemeRelation]:
        """获取事件关联的主题"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, event_id, theme_id, confidence, 
                           confidence_level, confidence_weight, evidence,
                           match_type, matched_keywords, created_at
                    FROM event_theme_map
                    WHERE event_id = $1
                    ORDER BY confidence DESC
                """, event_id)
                
                relations = []
                for row in rows:
                    relations.append(EventThemeRelation(
                        id=row['id'],
                        event_id=row['event_id'],
                        theme_id=row['theme_id'],
                        confidence=row['confidence'],
                        confidence_level=row['confidence_level'],
                        confidence_weight=row['confidence_weight'],
                        evidence=row['evidence'],
                        match_type=row['match_type'],
                        matched_keywords=row['matched_keywords'] or [],
                        created_at=row['created_at']
                    ))
                
                return relations
                
        except Exception as e:
            logger.error(f"获取事件主题失败 {event_id}: {e}")
            raise
    
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        """获取主题关联的事件ID"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT event_id
                    FROM event_theme_map
                    WHERE theme_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, theme_id, limit)
                
                return [row['event_id'] for row in rows]
                
        except Exception as e:
            logger.error(f"获取主题事件失败 {theme_id}: {e}")
            raise
    
    async def update_event_theme_relation(self, relation_id: int, updates: Dict[str, Any]) -> Optional[EventThemeRelation]:
        """更新事件-主题关联"""
        try:
            async with self.pool.acquire() as conn:
                set_clauses = []
                values = []
                index = 1
                
                for key, value in updates.items():
                    set_clauses.append(f"{key} = ${index}")
                    values.append(value)
                    index += 1
                
                query = f"""
                    UPDATE event_theme_map
                    SET {', '.join(set_clauses)}
                    WHERE id = ${index}
                    RETURNING id, event_id, theme_id, confidence, 
                             confidence_level, confidence_weight, evidence,
                             match_type, matched_keywords, created_at
                """
                values.append(relation_id)
                
                row = await conn.fetchrow(query, *values)
                
                if row:
                    return EventThemeRelation(
                        id=row['id'],
                        event_id=row['event_id'],
                        theme_id=row['theme_id'],
                        confidence=row['confidence'],
                        confidence_level=row['confidence_level'],
                        confidence_weight=row['confidence_weight'],
                        evidence=row['evidence'],
                        match_type=row['match_type'],
                        matched_keywords=row['matched_keywords'] or [],
                        created_at=row['created_at']
                    )
                
                return None
                
        except Exception as e:
            logger.error(f"更新关联失败 {relation_id}: {e}")
            raise

    async def upsert_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> Dict[str, Any]:
        """幂等写入事件-主题关联，供 ThemeMatchEngine 生产链路使用"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    INSERT INTO event_theme_map
                    (event_id, theme_id, confidence, confidence_level, confidence_weight, evidence, match_type, matched_keywords)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (event_id, theme_id) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        confidence_level = EXCLUDED.confidence_level,
                        confidence_weight = EXCLUDED.confidence_weight,
                        evidence = EXCLUDED.evidence,
                        match_type = EXCLUDED.match_type,
                        matched_keywords = EXCLUDED.matched_keywords
                    RETURNING id, event_id, theme_id, confidence,
                             confidence_level, confidence_weight, evidence,
                             match_type, matched_keywords, created_at
                """,
                    event_id,
                    theme_id,
                    kwargs.get('confidence', 0.8),
                    kwargs.get('confidence_level', 'medium'),
                    kwargs.get('confidence_weight', 50),
                    kwargs.get('evidence'),
                    kwargs.get('match_type', 'theme_match_engine'),
                    kwargs.get('matched_keywords', [])
                )

                if not row:
                    raise Exception("事件-题材幂等写入失败")

                return dict(row)

        except Exception as e:
            logger.error(f"幂等写入事件-主题关联失败 event={event_id}, theme={theme_id}: {e}")
            raise
    
    # ========== 事件管理 ==========
    
    async def mark_event_processed(self, event_id: int) -> None:
        """标记事件已处理"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE news_event
                    SET processed = TRUE,
                        processing_status = 'completed',
                        updated_at = NOW()
                    WHERE id = $1
                """, event_id)
                
                logger.info(f"✅ 标记事件已处理: {event_id}")
                
        except Exception as e:
            logger.error(f"标记事件失败 {event_id}: {e}")
            raise
    
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, title, content, summary, source, url,
                           publish_time, processed, processing_status,
                           processing_result, keywords, categories,
                           impact_industries, entities, confidence,
                           sentiment_score, created_at, updated_at
                    FROM news_event
                    WHERE processed = FALSE
                    AND processing_status = 'pending'
                    ORDER BY publish_time DESC, created_at DESC
                    LIMIT $1
                """, limit)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"获取未处理事件失败: {e}")
            return []
    
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT id, title, content, summary, source, url,
                           publish_time, processed, processing_status,
                           processing_result, keywords, categories,
                           impact_industries, entities, confidence,
                           sentiment_score, created_at, updated_at
                    FROM news_event
                    WHERE id = $1
                """, event_id)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"获取事件失败 {event_id}: {e}")
            raise

    async def get_news_event_for_match(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取供 ThemeMatchEngine 使用的单条事件输入"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        ne.id,
                        ne.news_id,
                        ne.event_type,
                        ne.summary,
                        ne.entities,
                        ne.causal_claim,
                        ne.evidence_set,
                        ne.raw_event_json,
                        nr.title,
                        nr.content
                    FROM news_event ne
                    LEFT JOIN news_raw nr
                      ON nr.id = ne.news_id
                    WHERE ne.id = $1
                """, event_id)

                return dict(row) if row else None

        except Exception as e:
            logger.error(f"获取匹配事件失败 {event_id}: {e}")
            raise

    async def list_matchable_news_events(
        self,
        limit: int = 0,
        event_id: Optional[int] = None,
        only_unmapped: bool = False,
    ) -> List[Dict[str, Any]]:
        """批量获取供 ThemeMatchEngine 使用的事件列表"""
        try:
            sql = """
                SELECT
                    ne.id,
                    ne.news_id,
                    ne.event_type,
                    ne.summary,
                    ne.entities,
                    ne.causal_claim,
                    ne.evidence_set,
                    ne.raw_event_json,
                    nr.title,
                    nr.content
                FROM news_event ne
                LEFT JOIN news_raw nr
                  ON nr.id = ne.news_id
                WHERE 1=1
            """
            params: List[Any] = []
            idx = 1

            if event_id is not None:
                sql += f" AND ne.id = ${idx}"
                params.append(event_id)
                idx += 1

            if only_unmapped:
                sql += """
                    AND NOT EXISTS (
                        SELECT 1
                        FROM event_theme_map etm
                        WHERE etm.event_id = ne.id
                    )
                """

            sql += " ORDER BY ne.id ASC"
            if limit and limit > 0:
                sql += f" LIMIT ${idx}"
                params.append(limit)

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"批量获取匹配事件失败: {e}")
            raise

    async def load_theme_match_profiles(self) -> List[Dict[str, Any]]:
        """加载 ThemeMatchEngine 所需的题材画像原始数据"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    WITH fc AS (
                        SELECT DISTINCT source_id::text AS subject_key, category_name AS subject_name
                        FROM financial_categories
                        WHERE source_system = 'jyhf' AND source_id IS NOT NULL
                    ),
                    tm AS (
                        SELECT DISTINCT ON (source_id::text)
                            source_id::text AS subject_key,
                            id AS theme_master_id,
                            name AS subject_name
                        FROM theme_master
                        WHERE source_system = 'jyhf' AND source_id IS NOT NULL
                        ORDER BY source_id::text, id ASC
                    )
                    , tpe AS (
                        SELECT DISTINCT ON (subject_key)
                            subject_key,
                            rerank_text
                        FROM theme_profile_ext
                        ORDER BY subject_key
                    )
                    SELECT
                        t.subject_key,
                        tm.theme_master_id,
                        COALESCE(fc.subject_name, tm.subject_name, t.concept, t.subject_key) AS subject_name,
                        t.concept,
                        t.semantic_type,
                        t.strategy_type,
                        t.ontology_json,
                        t.gate_json,
                        t.must_terms,
                        t.should_terms,
                        t.not_terms,
                        t.strong_terms,
                        t.weak_terms,
                        t.negative_terms,
                        t.search_text,
                        t.quality,
                        COALESCE(tpe.rerank_text, '') AS rerank_text
                    FROM theme_gate_profile t
                    LEFT JOIN fc ON fc.subject_key = t.subject_key
                    LEFT JOIN tm ON tm.subject_key = t.subject_key
                    LEFT JOIN tpe ON tpe.subject_key = t.subject_key
                    ORDER BY t.subject_key
                """)
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"加载题材匹配画像失败: {e}")
            raise

    async def semantic_recall_theme_candidates(
        self,
        query_embedding: List[float],
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """基于 theme_profile_ext.embedding 做语义召回"""
        try:
            if not query_embedding:
                return []

            vector_literal = "[" + ",".join(f"{float(x):.8f}" for x in query_embedding) + "]"
            sql = f"""
                SELECT
                    t.subject_key,
                    t.rerank_text,
                    1 - (t.embedding <=> '{vector_literal}'::vector) AS dense_score
                FROM theme_profile_ext t
                WHERE t.embedding IS NOT NULL
                ORDER BY t.embedding <=> '{vector_literal}'::vector
                LIMIT $1
            """

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, top_k)
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"语义召回候选失败: {e}")
            raise

    async def sparse_recall_theme_candidates(
        self,
        query_text: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """基于 theme_gate_profile.search_vector 做 FTS sparse recall"""
        try:
            if not query_text or not query_text.strip():
                return []

            sql = """
                SELECT
                    subject_key,
                    concept,
                    ts_rank_cd(search_vector, websearch_to_tsquery('simple', $1)) AS sparse_score
                FROM theme_gate_profile
                WHERE search_vector @@ websearch_to_tsquery('simple', $1)
                ORDER BY sparse_score DESC, subject_key
                LIMIT $2
            """

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, query_text, top_k)
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"稀疏召回候选失败: {e}")
            raise

    async def resolve_theme_master_id_by_source_key(self, source_system: str, source_key: str) -> Optional[int]:
        """通过 source_system/source_key 解析正式 theme_master.id"""
        try:
            async with self.pool.acquire() as conn:
                value = await conn.fetchval("""
                    SELECT id
                    FROM theme_master
                    WHERE source_system = $1
                      AND source_id IS NOT NULL
                      AND source_id::text = $2
                    ORDER BY id ASC
                    LIMIT 1
                """, source_system, source_key)

                return int(value) if value is not None else None

        except Exception as e:
            logger.error(f"解析 theme_master.id 失败 source_system={source_system}, source_key={source_key}: {e}")
            raise

    async def create_news_event(self, event_data: Dict[str, Any]) -> Optional[int]:
        """创建结构化 news_event 记录并返回 news_event.id"""
        try:
            import json
            from datetime import datetime

            event_time = event_data.get("event_time")
            if isinstance(event_time, str) and event_time.strip():
                try:
                    event_time = datetime.fromisoformat(event_time.strip().replace("Z", "+00:00"))
                except ValueError:
                    event_time = None
            if isinstance(event_time, datetime) and event_time.tzinfo is not None:
                event_time = event_time.replace(tzinfo=None)

            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO news_event (
                        news_id,
                        event_type,
                        impact_industries,
                        direction,
                        confidence,
                        summary,
                        theme_directive,
                        theme_directive_processed,
                        severity_score,
                        source_weight,
                        event_time,
                        entities,
                        causal_claim,
                        evidence_set,
                        raw_event_json
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6,
                        $7::jsonb, $8, $9, $10, $11,
                        $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb
                    )
                    RETURNING id
                    """,
                    event_data.get("news_id"),
                    event_data.get("event_type"),
                    event_data.get("impact_industries") or [],
                    event_data.get("direction"),
                    event_data.get("confidence"),
                    event_data.get("summary"),
                    json.dumps(event_data.get("theme_directive") or {}, ensure_ascii=False),
                    bool(event_data.get("theme_directive_processed", False)),
                    event_data.get("severity_score"),
                    event_data.get("source_weight"),
                    event_time,
                    json.dumps(event_data.get("entities") or [], ensure_ascii=False),
                    json.dumps(event_data.get("causal_claim") or [], ensure_ascii=False),
                    json.dumps(event_data.get("evidence_set") or {}, ensure_ascii=False),
                    json.dumps(event_data.get("raw_event_json") or {}, ensure_ascii=False),
                )
                return int(row["id"]) if row else None
        except Exception as e:
            logger.error(f"创建 news_event 失败: {e}")
            raise
    
    # ========== 统计与监控 ==========
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            async with self.pool.acquire() as conn:
                stats = {}
                
                # 主题统计
                theme_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                        COUNT(CASE WHEN status = 'inactive' THEN 1 END) as inactive,
                        COUNT(CASE WHEN status = 'archived' THEN 1 END) as archived,
                        AVG(heat_score) as avg_heat,
                        MAX(heat_score) as max_heat,
                        COUNT(CASE WHEN heat_score >= 80 THEN 1 END) as high_heat_count,
                        COUNT(CASE WHEN heat_score BETWEEN 60 AND 79 THEN 1 END) as medium_heat_count,
                        COUNT(CASE WHEN heat_score < 60 THEN 1 END) as low_heat_count
                    FROM theme_master
                """)
                
                if theme_stats:
                    stats['themes'] = dict(theme_stats)
                
                # 事件统计
                try:
                    event_stats = await conn.fetchrow("""
                        SELECT 
                            COUNT(*) as total_events,
                            COUNT(CASE WHEN processed = TRUE THEN 1 END) as processed,
                            COUNT(CASE WHEN processed = FALSE THEN 1 END) as unprocessed,
                            COUNT(CASE WHEN processing_status = 'pending' THEN 1 END) as pending
                        FROM news_event
                    """)
                    
                    if event_stats:
                        stats['events'] = dict(event_stats)
                except Exception:
                    logger.warning("news_event表可能不存在，跳过事件统计")
                
                # 关联统计
                try:
                    relation_stats = await conn.fetchrow("""
                        SELECT 
                            COUNT(*) as total_relations,
                            AVG(confidence) as avg_confidence,
                            COUNT(CASE WHEN confidence_level = 'high' THEN 1 END) as high_confidence_count,
                            COUNT(CASE WHEN confidence_level = 'medium' THEN 1 END) as medium_confidence_count,
                            COUNT(CASE WHEN confidence_level = 'low' THEN 1 END) as low_confidence_count
                        FROM event_theme_map
                    """)
                    
                    if relation_stats:
                        stats['relations'] = dict(relation_stats)
                except Exception:
                    logger.warning("event_theme_map表可能不存在，跳关联统计")
                
                # 数据库信息
                db_info = await conn.fetchrow("""
                    SELECT 
                        pg_database_size(current_database()) as db_size_bytes,
                        pg_size_pretty(pg_database_size(current_database())) as db_size_human
                """)
                
                if db_info:
                    stats['database'] = dict(db_info)
                
                return stats
                
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {}
    
    # ========== 高级查询 ==========
    
    async def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """执行原始SQL查询"""
        try:
            async with self.pool.acquire() as conn:
                if params:
                    rows = await conn.fetch(query, *params)
                else:
                    rows = await conn.fetch(query)
                
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"执行查询失败: {e}")
            raise

    async def cleanup_test_data(self, theme_id=None):
        """清理测试数据"""
        try:
            async with self.pool.acquire() as conn:
                if theme_id:
                    # 删除特定主题
                    await conn.execute("DELETE FROM theme_master WHERE id = $1", theme_id)
                    print(f"✅ 清理测试主题: {theme_id}")
                else:
                    # 删除所有测试主题（以TEST_开头的code）
                    result = await conn.execute("""
                        DELETE FROM theme_master 
                        WHERE code LIKE 'TEST_%' OR code LIKE 'BATCH_%' OR name LIKE '%测试%'
                    """)
                    print(f"✅ 清理所有测试数据: {result}")
        except Exception as e:
            print(f"⚠️  清理数据失败: {e}")
    
    async def create_news(self, news_data: Dict[str, Any]) -> Optional[str]:
        """
        创建新闻记录（符合news_raw表结构）
        
        Args:
            news_data: 新闻数据字典，必须包含news_id, title, content, source, publish_date
            
        Returns:
            news_id: 新闻唯一标识，失败返回None
        """
        try:
            import json
            from datetime import datetime, date, time as datetime_time
            
            # 验证必要字段
            required_fields = ['news_id', 'title', 'content', 'source', 'publish_date']
            for field in required_fields:
                if field not in news_data:
                    logger.error(f"创建新闻失败：缺少必要字段 {field}")
                    return None
            
            # 处理日期字段
            publish_date = news_data['publish_date']
            if isinstance(publish_date, str):
                # 尝试从字符串解析日期
                try:
                    # 移除时间部分（如果有）
                    date_str = publish_date
                    if 'T' in date_str:
                        date_str = date_str.split('T')[0]
                    elif ' ' in date_str:
                        date_str = date_str.split(' ')[0]
                    
                    # 解析日期
                    publish_date = date.fromisoformat(date_str)
                except ValueError as e:
                    logger.error(f"日期格式错误: {publish_date} - {e}")
                    return None
            elif isinstance(publish_date, datetime):
                publish_date = publish_date.date()
            elif not isinstance(publish_date, date):
                logger.error(f"日期类型错误: {type(publish_date)}")
                return None
            
            # 处理时间字段
            publish_time = news_data.get('publish_time')
            if publish_time:
                if isinstance(publish_time, str):
                    try:
                        # 移除日期部分（如果有）
                        time_str = publish_time
                        if 'T' in time_str:
                            # 提取时间部分
                            if 'T' in time_str:
                                time_str = time_str.split('T')[1]
                            if '+' in time_str:
                                time_str = time_str.split('+')[0]
                            if 'Z' in time_str:
                                time_str = time_str.replace('Z', '')
                            
                            # 解析时间
                            if len(time_str) > 8:
                                time_str = time_str[:8]
                            parts = time_str.split(':')
                            if len(parts) == 3:
                                hour, minute, second = parts
                                second = second.split('.')[0]  # 移除毫秒
                                publish_time = datetime_time(int(hour), int(minute), int(second))
                            elif len(parts) == 2:
                                hour, minute = parts
                                publish_time = datetime_time(int(hour), int(minute))
                            else:
                                publish_time = None
                        else:
                            # 简单时间格式 HH:MM:SS 或 HH:MM
                            parts = time_str.split(':')
                            if len(parts) == 3:
                                hour, minute, second = parts
                                second = second.split('.')[0]  # 移除毫秒
                                publish_time = datetime_time(int(hour), int(minute), int(second))
                            elif len(parts) == 2:
                                hour, minute = parts
                                publish_time = datetime_time(int(hour), int(minute))
                            else:
                                publish_time = None
                    except (ValueError, IndexError) as e:
                        logger.warning(f"时间格式错误: {publish_time} - {e}")
                        publish_time = None
                elif isinstance(publish_time, datetime):
                    publish_time = publish_time.time()
            
            async with self.pool.acquire() as conn:
                # 插入新闻数据
                row = await conn.fetchrow("""
                    INSERT INTO news_raw 
                    (news_id, title, content, source, publish_date, 
                    publish_time, market, url, keywords, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (news_id) DO NOTHING
                    RETURNING news_id, id
                """,
                    news_data['news_id'],
                    news_data['title'],
                    news_data['content'],
                    news_data['source'],
                    publish_date,
                    publish_time,
                    news_data.get('market', 'A股'),
                    news_data.get('url', ''),
                    json.dumps(news_data.get('keywords', []), ensure_ascii=False),
                    json.dumps(news_data.get('metadata', {}), ensure_ascii=False)
                )
                
                if row:
                    logger.info(f"✅ 创建新闻记录成功: {row['news_id']} (ID: {row['id']})")
                    return row['news_id']
                else:
                    logger.warning(f"⚠️ 新闻已存在，跳过: {news_data['news_id']}")
                    return news_data['news_id']
                    
        except Exception as e:
            logger.error(f"❌ 创建新闻失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_news(self, news_id: str) -> Optional[Dict[str, Any]]:
        """获取新闻记录"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT 
                        id, news_id, title, content, source,
                        publish_date, publish_time, market, url,
                        keywords, metadata, created_at, updated_at
                    FROM news_raw
                    WHERE news_id = $1
                """, news_id)
                
                if row:
                    import json
                    # 转换为字典并处理JSON字段
                    result = dict(row)
                    result['keywords'] = row['keywords'] if row['keywords'] else []
                    result['metadata'] = row['metadata'] if row['metadata'] else {}
                    return result
                return None
                
        except Exception as e:
            logger.error(f"获取新闻失败 {news_id}: {e}")
            return None

    async def get_recent_news(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的新闻"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id, news_id, title, content, source,
                        publish_date, publish_time, market, url,
                        keywords, metadata, created_at, updated_at
                    FROM news_raw
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)
                
                results = []
                for row in rows:
                    import json
                    result = dict(row)
                    result['keywords'] = row['keywords'] if row['keywords'] else []
                    result['metadata'] = row['metadata'] if row['metadata'] else {}
                    results.append(result)
                
                logger.info(f"✅ 获取最近 {len(results)} 条新闻")
                return results
                
        except Exception as e:
            logger.error(f"获取最近新闻失败: {e}")
            return []
    
    async def count_news(self) -> int:
        """统计新闻数量"""
        try:
            async with self.pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM news_raw")
                return count
        except Exception as e:
            logger.error(f"统计新闻数量失败: {e}")
            return 0
    
    async def delete_test_news(self):
        """删除测试新闻（清理用）"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM news_raw 
                    WHERE source = 'mock_generator' 
                    OR metadata->>'simulation' = 'true'
                """)
                logger.info(f"✅ 删除测试新闻: {result}")
        except Exception as e:
            logger.error(f"删除测试新闻失败: {e}")

    async def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息 - 兼容方法"""
        # 调用已有的get_stats方法
        stats = await self.get_stats()
        
        # 添加一些额外的信息
        stats.update({
            'database_type': 'postgresql',
            'connection_status': self.connected if hasattr(self, 'connected') else True,
            'connection_info': {
                'host': self.config.database_config.host,
                'database': self.config.database_config.database
            }
        })
        
        return stats
    
    async def load_all_categories(self) -> List[Dict[str, Any]]:
        """
        加载financial_categories表中的全部分类数据（1、2级）
        返回格式化的分类字典列表
        """
        try:
            async with self.pool.acquire() as conn:
                # 查询全部分类数据
                rows = await conn.fetch("""
                    SELECT 
                        id, category_code, category_name, description,
                        category_level, parent_code, full_path,
                        category_type, standard_type, 
                        COALESCE(keywords, ARRAY[]::text[]) as keywords,
                        COALESCE(aliases, ARRAY[]::text[]) as aliases,
                        COALESCE(related_industries, ARRAY[]::text[]) as related_industries,
                        source_system, source_id,
                        is_standard, theme_count, stock_count, avg_heat_score,
                        created_at, updated_at
                    FROM financial_categories
                    WHERE category_level IN (1, 2)  -- 只获取1、2级分类
                    ORDER BY category_level, category_code
                """)
                
                categories = []
                for row in rows:
                    category = self._build_category_dict(row)
                    categories.append(category)
                
                logger.info(f"✅ 加载全部分类数据成功: {len(categories)} 条记录")
                
                # 显示分类统计
                level1_count = len([c for c in categories if c['category_level'] == 1])
                level2_count = len([c for c in categories if c['category_level'] == 2])
                logger.info(f"📊 分类统计: {level1_count} 个一级分类, {level2_count} 个二级分类")
                
                return categories
                
        except Exception as e:
            logger.error(f"❌ 加载分类数据失败: {e}")
            # 记录详细的错误信息
            logger.exception("分类数据加载异常详情:")
            return []
    
    def _build_category_dict(self, row) -> Dict[str, Any]:
        """
        从数据库行构建分类字典
        """
        try:
            # 确保数组字段是Python列表
            keywords = row.get('keywords', [])
            aliases = row.get('aliases', [])
            related_industries = row.get('related_industries', [])
            full_path = row.get('full_path', [])
            
            # 如果这些字段是PostgreSQL数组对象，转换为列表
            if hasattr(keywords, '__iter__') and not isinstance(keywords, list):
                keywords = list(keywords)
            if hasattr(aliases, '__iter__') and not isinstance(aliases, list):
                aliases = list(aliases)
            if hasattr(related_industries, '__iter__') and not isinstance(related_industries, list):
                related_industries = list(related_industries)
            if hasattr(full_path, '__iter__') and not isinstance(full_path, list):
                full_path = list(full_path)
            
            # 构建分类字典
            category_dict = {
                'id': row.get('id'),
                'category_code': row.get('category_code', ''),
                'category_name': row.get('category_name', ''),
                'description': row.get('description', ''),
                'category_level': row.get('category_level', 1),
                'parent_code': row.get('parent_code'),
                'full_path': full_path,
                'category_type': row.get('category_type', 'industry'),
                'standard_type': row.get('standard_type'),
                'keywords': keywords,
                'aliases': aliases,
                'related_industries': related_industries,
                'source_system': row.get('source_system', ''),
                'source_id': row.get('source_id'),
                'is_standard': row.get('is_standard', True),
                'theme_count': row.get('theme_count', 0),
                'stock_count': row.get('stock_count', 0),
                'avg_heat_score': float(row.get('avg_heat_score', 50.0)),
                'created_at': row.get('created_at'),
                'updated_at': row.get('updated_at')
            }
            
            return category_dict
            
        except Exception as e:
            logger.error(f"❌ 构建分类字典失败: {e}")
            # 返回一个最小的有效字典
            return {
                'id': row.get('id'),
                'category_code': row.get('category_code', ''),
                'category_name': row.get('category_name', ''),
                'category_level': row.get('category_level', 1),
                'keywords': [],
                'aliases': [],
                'theme_count': 0
            }
    
    async def create_category(self, category_data: Dict) -> Optional[Dict]:
        """
        创建新分类 - 保持客户端纯净，只处理数据库操作
        """
        try:
            # 🔥 假设传入的数据已经是正确格式
            # 只在必要时做防御性检查
            
            # 验证必需字段
            required_fields = ['category_code', 'category_name', 'category_level']
            for field in required_fields:
                if field not in category_data:
                    raise ValueError(f"缺失必需字段: {field}")
            
            # 记录调试信息
            logger.debug(f"📝 PostgresClient创建分类: {category_data.get('category_code')}")
            
            async with self.pool.acquire() as conn:
                # 检查是否已存在
                existing = await conn.fetchrow("""
                    SELECT id FROM financial_categories 
                    WHERE category_code = $1
                """, category_data['category_code'])
                
                if existing:
                    raise Exception(f"分类已存在 (code={category_data['category_code']})")
                
                # 🔥 直接使用传入的数据
                # 调用层应该确保格式正确
                
                row = await conn.fetchrow("""
                    INSERT INTO financial_categories 
                    (category_code, category_name, description, category_level, 
                    parent_code, full_path, category_type, standard_type, 
                    keywords, aliases, related_industries, 
                    source_system, source_id, is_standard, 
                    theme_count, stock_count, avg_heat_score)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                    RETURNING *
                """, 
                    category_data['category_code'],
                    category_data['category_name'],
                    category_data.get('description'),
                    category_data['category_level'],
                    category_data.get('parent_code'),
                    category_data.get('full_path', []),  # 期望是列表
                    category_data.get('category_type', 'industry'),
                    category_data.get('standard_type', 'custom'),
                    category_data.get('keywords', []),  # 期望是列表
                    category_data.get('aliases', []),  # 期望是列表
                    category_data.get('related_industries', []),  # 期望是列表
                    category_data.get('source_system', 'ai_theme_discovery'),
                    category_data.get('source_id'),
                    category_data.get('is_standard', False),
                    category_data.get('theme_count', 0),
                    category_data.get('stock_count', 0),
                    category_data.get('avg_heat_score', 50.0)
                )
                
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"PostgresClient创建分类失败: {e}")
            # 添加数据类型调试信息
            if 'keywords' in category_data:
                logger.error(f"   keywords值: {category_data['keywords']}")
                logger.error(f"   keywords类型: {type(category_data['keywords'])}")
            raise
    
    async def get_categories_by_parent(self, parent_code: str, level: int = 2) -> List[Dict]:
        """获取指定父分类下的子分类"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM financial_categories 
                    WHERE parent_code = $1 AND category_level = $2
                    ORDER BY category_code
                """, parent_code, level)
                
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取子分类失败: {e}")
            return []
    
    async def get_category_by_code(self, category_code: str) -> Optional[Dict[str, Any]]:
        """根据分类代码获取分类详情"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT 
                        id, category_code, category_name, description,
                        category_level, parent_code, full_path,
                        category_type, standard_type, 
                        COALESCE(keywords, ARRAY[]::text[]) as keywords,
                        COALESCE(aliases, ARRAY[]::text[]) as aliases,
                        COALESCE(related_industries, ARRAY[]::text[]) as related_industries,
                        source_system, source_id,
                        is_standard, theme_count, stock_count, avg_heat_score,
                        created_at, updated_at
                    FROM financial_categories
                    WHERE category_code = $1
                """, category_code)
                
                if row:
                    category = self._build_category_dict(row)
                    logger.info(f"✅ 获取分类详情: {category_code} -> {category['category_name']}")
                    return category
                
                logger.warning(f"⚠️ 未找到分类: {category_code}")
                return None
                
        except Exception as e:
            logger.error(f"获取分类失败 {category_code}: {e}")
            return None
    
    async def search_categories_by_keywords(self, keywords: List[str], 
                                          level: Optional[int] = None,
                                          limit: int = 20) -> List[Dict[str, Any]]:
        """根据关键词搜索分类"""
        try:
            if not keywords:
                return []
            
            async with self.pool.acquire() as conn:
                # 构建搜索条件
                search_conditions = []
                params = []
                
                # 对每个关键词构建搜索条件
                for i, keyword in enumerate(keywords, 1):
                    keyword_like = f"%{keyword}%"
                    search_conditions.extend([
                        f"category_name ILIKE ${i*2-1}",
                        f"description ILIKE ${i*2}"
                    ])
                    params.extend([keyword_like, keyword_like])
                
                # 添加数组字段匹配
                array_start = len(keywords) * 2 + 1
                for i, keyword in enumerate(keywords, array_start):
                    search_conditions.append(f"${i} = ANY(keywords)")
                    search_conditions.append(f"${i} = ANY(aliases)")
                    params.extend([keyword, keyword])
                
                # 组合搜索条件
                search_where = " OR ".join(search_conditions) if search_conditions else "FALSE"
                
                # 添加级别过滤
                where_conditions = [f"({search_where})"]
                if level is not None:
                    where_conditions.append(f"category_level = ${len(params)+1}")
                    params.append(level)
                
                where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                # 执行查询
                rows = await conn.fetch(f"""
                    SELECT 
                        id, category_code, category_name, description,
                        category_level, parent_code, full_path,
                        category_type, standard_type, 
                        COALESCE(keywords, ARRAY[]::text[]) as keywords,
                        COALESCE(aliases, ARRAY[]::text[]) as aliases,
                        COALESCE(related_industries, ARRAY[]::text[]) as related_industries,
                        source_system, source_id,
                        is_standard, theme_count, stock_count, avg_heat_score,
                        created_at, updated_at,
                        
                        -- 计算匹配分数
                        (
                            CASE WHEN category_name ILIKE ANY(${len(params)+1}::text[]) THEN 3 ELSE 0 END +
                            CASE WHEN description ILIKE ANY(${len(params)+1}::text[]) THEN 2 ELSE 0 END +
                            CASE WHEN ${len(params)+1}::text[] && keywords THEN ARRAY_LENGTH(keywords, 1) ELSE 0 END +
                            CASE WHEN ${len(params)+1}::text[] && aliases THEN ARRAY_LENGTH(aliases, 1) ELSE 0 END
                        ) as match_score
                        
                    FROM financial_categories
                    {where_clause}
                    ORDER BY match_score DESC, theme_count DESC
                    LIMIT ${len(params)+2}
                """, *params, [f"%{kw}%" for kw in keywords], limit)
                
                categories = []
                for row in rows:
                    category = self._build_category_dict(row)
                    category['match_score'] = row.get('match_score', 0)
                    categories.append(category)
                
                logger.info(f"✅ 关键词搜索分类: {keywords} -> {len(categories)} 个结果")
                return categories
                
        except Exception as e:
            logger.error(f"搜索分类失败: {e}")
            return []
    
    async def get_category_stats(self) -> Dict[str, Any]:
        """获取分类统计信息"""
        try:
            async with self.pool.acquire() as conn:
                stats = {}
                
                # 基础统计
                basic_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_count,
                        COUNT(CASE WHEN category_level = 1 THEN 1 END) as level1_count,
                        COUNT(CASE WHEN category_level = 2 THEN 1 END) as level2_count,
                        SUM(theme_count) as total_themes,
                        SUM(stock_count) as total_stocks,
                        AVG(avg_heat_score) as avg_heat_score,
                        MAX(theme_count) as max_themes,
                        MIN(theme_count) as min_themes
                    FROM financial_categories
                    WHERE category_level IN (1, 2)
                """)
                
                if basic_stats:
                    stats['summary'] = dict(basic_stats)
                
                # 热门分类（按主题数量）
                popular_categories = await conn.fetch("""
                    SELECT 
                        category_code, category_name, category_level,
                        theme_count, stock_count, avg_heat_score
                    FROM financial_categories
                    WHERE theme_count > 0
                    ORDER BY theme_count DESC
                    LIMIT 10
                """)
                
                if popular_categories:
                    stats['popular_categories'] = [dict(row) for row in popular_categories]
                
                # 分类类型分布
                type_distribution = await conn.fetch("""
                    SELECT 
                        category_type,
                        COUNT(*) as count,
                        AVG(theme_count) as avg_themes,
                        AVG(stock_count) as avg_stocks
                    FROM financial_categories
                    GROUP BY category_type
                """)
                
                if type_distribution:
                    stats['type_distribution'] = [dict(row) for row in type_distribution]
                
                logger.info(f"✅ 获取分类统计信息")
                return stats
                
        except Exception as e:
            logger.error(f"获取分类统计失败: {e}")
            return {}

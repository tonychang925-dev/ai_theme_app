# database_service/managers/postgres_manager.py
"""
PostgreSQL数据库管理器 - 适配实际theme_master表结构
基于实际的28字段表结构，包含申万行业分类
"""
import os
from datetime import date
import logging
from typing import Dict, List, Any, Optional, AsyncContextManager
from datetime import datetime, date, timezone
import asyncpg
from asyncpg.pool import Pool
import json
from decimal import Decimal
from datetime import date as _date, datetime as _datetime


def _json_default(obj):
    """Postgres JSONB 安全序列化兜底。"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (_datetime, _date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    return str(obj)


def _safe_json_dumps(value, default_empty=None) -> str:
    """安全 JSON 序列化，自动处理 Decimal/date/datetime/set。"""
    if value is None:
        value = default_empty if default_empty is not None else {}
    return json.dumps(value, ensure_ascii=False, default=_json_default)


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

    async def enqueue_event_review(
        self,
        event_id: int,
        reason: str,
        source_channel: str = "realtime_news",
        proposed_theme_name: Optional[str] = None,
        proposed_theme_confidence: Optional[float] = None,
    ) -> bool:
        """将事件写入人工复核队列（幂等）。"""
        try:
            async with self.pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT to_regclass('public.event_review_queue')::text"
                )
                if not exists:
                    logger.warning("event_review_queue 不存在，跳过写入复核队列")
                    return False

                await conn.execute(
                    """
                    INSERT INTO event_review_queue (
                        event_id,
                        review_status,
                        proposed_theme_name,
                        proposed_theme_confidence,
                        reason,
                        source_channel
                    )
                    VALUES ($1, 'waiting', $2, $3, $4, $5)
                    ON CONFLICT (event_id) DO UPDATE
                    SET review_status = 'waiting',
                        proposed_theme_name = COALESCE(EXCLUDED.proposed_theme_name, event_review_queue.proposed_theme_name),
                        proposed_theme_confidence = COALESCE(EXCLUDED.proposed_theme_confidence, event_review_queue.proposed_theme_confidence),
                        reason = EXCLUDED.reason,
                        source_channel = EXCLUDED.source_channel
                    """,
                    event_id,
                    proposed_theme_name,
                    proposed_theme_confidence,
                    reason,
                    source_channel,
                )
                return True
        except Exception as e:
            logger.error(f"写入 event_review_queue 失败 event_id={event_id}: {e}")
            return False

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

            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO news_event (
                        news_id,
                        event_type,
                        impact_industries,
                        direction,
                        confidence,
                        summary
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6
                    )
                    RETURNING id
                    """,
                    event_data.get("news_id"),
                    event_data.get("event_type"),
                    event_data.get("impact_industries") or [],
                    event_data.get("direction"),
                    event_data.get("confidence"),
                    event_data.get("summary")
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

    async def get_subject_stock_pool_by_trade_date(self, trade_date) -> List[Dict[str, Any]]:
        """按交易日读取题材股票池快照。"""
        sql = """
        WITH base AS (
            SELECT
                s.trade_date,
                s.subject_key,
                s.stock_id,
                COALESCE(NULLIF(s.stock_name, ''), m.stock_name) AS stock_name,
                s.rank_order AS rank_order_raw,
                COALESCE(s.close_price, m.close_price) AS close_price,
                COALESCE(s.pct_chg, m.pct_chg) AS pct_chg,
                s.limit_up AS limit_up_raw,
                s.is_leader AS is_leader_raw
            FROM subject_stock_daily_snapshot s
            LEFT JOIN LATERAL (
              SELECT stock_name, close_price, pct_chg
              FROM stock_daily_snapshot m
              WHERE m.trade_date = s.trade_date
                AND m.stock_id = s.stock_id
                AND m.source_name LIKE 'tushare%'
              ORDER BY CASE WHEN m.source_name = 'tushare' THEN 0 ELSE 1 END, m.updated_at DESC NULLS LAST
              LIMIT 1
            ) m ON TRUE
            WHERE s.trade_date = $1::date
              AND COALESCE(s.stock_id, '') <> ''
        ),
        ranked AS (
            SELECT
                trade_date,
                subject_key,
                stock_id,
                stock_name,
                COALESCE(
                    rank_order_raw,
                    DENSE_RANK() OVER (
                        PARTITION BY subject_key
                        ORDER BY pct_chg DESC NULLS LAST, stock_id
                    )
                ) AS rank_order,
                close_price,
                pct_chg,
                COALESCE(limit_up_raw, (pct_chg >= 9.5), FALSE) AS limit_up,
                COALESCE(
                    is_leader_raw,
                    (
                        COALESCE(
                            rank_order_raw,
                            DENSE_RANK() OVER (
                                PARTITION BY subject_key
                                ORDER BY pct_chg DESC NULLS LAST, stock_id
                            )
                        ) <= 1
                    ),
                    FALSE
                ) AS is_leader
            FROM base
        )
        SELECT
            trade_date,
            subject_key,
            stock_id,
            stock_name,
            rank_order,
            close_price,
            pct_chg,
            limit_up,
            is_leader
        FROM ranked
        ORDER BY subject_key, rank_order ASC, stock_id
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
            return [dict(row) for row in rows]

    async def upsert_stock_daily_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """批量 UPSERT stock_daily_snapshot。"""
        if not rows:
            return 0
        # Truth table hard gate: reject any non-truth source in market truth writes.
        # Only tushare-derived sources are allowed in stock_daily_snapshot.
        invalid_rows = []
        for row in rows:
            src = str(row.get("source_name") or "").strip().lower()
            if not src.startswith("tushare"):
                invalid_rows.append(row)
        if invalid_rows:
            logger.error(
                "阻断写入 stock_daily_snapshot：检测到非真源 source_name，blocked=%s total=%s",
                len(invalid_rows),
                len(rows),
            )
            raise ValueError(
                "blocked non-truth writes to stock_daily_snapshot; "
                "only source_name like 'tushare*' is allowed"
            )

        sql = """
        INSERT INTO stock_daily_snapshot (
            trade_date, stock_id, stock_name,
            open_price, high_price, low_price, close_price, pre_close, pct_chg,
            volume, amount, source_name
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6, $7, $8, $9,
            $10, $11, $12
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
          stock_name = COALESCE(EXCLUDED.stock_name, stock_daily_snapshot.stock_name),
          open_price = COALESCE(EXCLUDED.open_price, stock_daily_snapshot.open_price),
          high_price = COALESCE(EXCLUDED.high_price, stock_daily_snapshot.high_price),
          low_price = COALESCE(EXCLUDED.low_price, stock_daily_snapshot.low_price),
          close_price = COALESCE(EXCLUDED.close_price, stock_daily_snapshot.close_price),
          pre_close = COALESCE(EXCLUDED.pre_close, stock_daily_snapshot.pre_close),
          pct_chg = COALESCE(EXCLUDED.pct_chg, stock_daily_snapshot.pct_chg),
          volume = COALESCE(EXCLUDED.volume, stock_daily_snapshot.volume),
          amount = COALESCE(EXCLUDED.amount, stock_daily_snapshot.amount),
          source_name = COALESCE(EXCLUDED.source_name, stock_daily_snapshot.source_name),
          updated_at = NOW()
        """
        payload = [self._normalize_stock_snapshot_row(row) for row in rows]
        async with self.pool.acquire() as conn:
            await conn.executemany(sql, payload)
        return len(payload)

    async def upsert_stock_daily_strategy_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """批量 UPSERT stock_daily_strategy_snapshot（策略对象层）。"""
        if not rows:
            return 0

        sql = """
        INSERT INTO stock_daily_strategy_snapshot (
            trade_date, stock_id, stock_name,
            close_price, pct_chg, volume, amount, limit_up_price, limit_down_price,
            snapshot_version, batch_id, trace_id, source_trace_id,
            labels, score_breakdown, source_name
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13,
            $14::jsonb, $15::jsonb, $16
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
          stock_name = COALESCE(EXCLUDED.stock_name, stock_daily_strategy_snapshot.stock_name),
          close_price = COALESCE(EXCLUDED.close_price, stock_daily_strategy_snapshot.close_price),
          pct_chg = COALESCE(EXCLUDED.pct_chg, stock_daily_strategy_snapshot.pct_chg),
          volume = COALESCE(EXCLUDED.volume, stock_daily_strategy_snapshot.volume),
          amount = COALESCE(EXCLUDED.amount, stock_daily_strategy_snapshot.amount),
          limit_up_price = COALESCE(EXCLUDED.limit_up_price, stock_daily_strategy_snapshot.limit_up_price),
          limit_down_price = COALESCE(EXCLUDED.limit_down_price, stock_daily_strategy_snapshot.limit_down_price),
          snapshot_version = COALESCE(EXCLUDED.snapshot_version, stock_daily_strategy_snapshot.snapshot_version),
          batch_id = COALESCE(EXCLUDED.batch_id, stock_daily_strategy_snapshot.batch_id),
          trace_id = COALESCE(EXCLUDED.trace_id, stock_daily_strategy_snapshot.trace_id),
          source_trace_id = COALESCE(EXCLUDED.source_trace_id, stock_daily_strategy_snapshot.source_trace_id),
          labels = COALESCE(EXCLUDED.labels, stock_daily_strategy_snapshot.labels),
          score_breakdown = COALESCE(EXCLUDED.score_breakdown, stock_daily_strategy_snapshot.score_breakdown),
          source_name = COALESCE(EXCLUDED.source_name, stock_daily_strategy_snapshot.source_name),
          updated_at = NOW()
        """
        payload = [
            (
                row.get("trade_date"),
                row.get("stock_id"),
                row.get("stock_name"),
                row.get("close_price"),
                row.get("pct_chg"),
                row.get("volume"),
                row.get("amount"),
                row.get("limit_up_price"),
                row.get("limit_down_price"),
                row.get("snapshot_version"),
                row.get("batch_id"),
                row.get("trace_id"),
                row.get("source_trace_id"),
                _safe_json_dumps(row.get("labels"), {}),
                _safe_json_dumps(row.get("score_breakdown"), {}),
                str(row.get("source") or row.get("source_name") or "stock_processing_service"),
            )
            for row in rows
            if row.get("trade_date") and row.get("stock_id")
        ]
        if not payload:
            return 0
        async with self.pool.acquire() as conn:
            await conn.executemany(sql, payload)
        return len(payload)

    async def get_stock_daily_snapshot_by_trade_date(self, trade_date) -> List[Dict[str, Any]]:
        """按交易日读取 stock_daily_snapshot。"""
        sql = """
        SELECT
            trade_date, stock_id, stock_name,
            open_price, high_price, low_price, close_price, pre_close, pct_chg,
            volume, amount, source_name
        FROM stock_daily_snapshot
        WHERE trade_date = $1::date
        ORDER BY stock_id
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
            return [dict(row) for row in rows]

    async def get_trade_calendar(self, trade_date) -> Dict[str, Any]:
        """
        获取交易日历信息。
        仅基于本地已落库交易日数据解析相邻交易日，不依赖外部在线 token。
        """
        sql_prev = """
        SELECT MAX(trade_date) AS prev_trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date < $1::date
        """
        sql_next = """
        SELECT MIN(trade_date) AS next_trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date > $1::date
        """
        try:
            async with self.pool.acquire() as conn:
                prev_row = await conn.fetchrow(sql_prev, trade_date)
                next_row = await conn.fetchrow(sql_next, trade_date)
                return {
                    "trade_date": trade_date,
                    "is_open": True,
                    "calendar_is_open": True,
                    "prev_trade_date": prev_row.get("prev_trade_date") if prev_row else None,
                    "next_trade_date": next_row.get("next_trade_date") if next_row else None,
                    "source": "subject_stock_daily_snapshot",
                }
        except Exception as e:
            logger.warning(f"交易日历读取失败: {e}")
            raise

    async def get_stock_daily_bars(self, trade_date, stock_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """读取股票日线（当前映射到 stock_daily_snapshot）。"""
        sql = """
        SELECT DISTINCT ON (stock_id)
            trade_date, stock_id, stock_name,
            open_price, high_price, low_price, close_price, pre_close, pct_chg,
            volume, amount
        FROM stock_daily_snapshot
        WHERE trade_date = $1::date
          AND source_name LIKE 'tushare%'
          AND ($2::text[] IS NULL OR stock_id = ANY($2::text[]))
        ORDER BY stock_id,
                 CASE WHEN source_name = 'tushare' THEN 0 ELSE 1 END,
                 updated_at DESC NULLS LAST
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, stock_ids if stock_ids else None)
            return [dict(row) for row in rows]

    async def get_stock_daily_bars_range(
        self,
        start_date,
        end_date,
        stock_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """读取区间股票日线（用于支撑评分等历史K线分析）。"""
        sql = """
        SELECT DISTINCT ON (trade_date, stock_id)
            trade_date, stock_id, stock_name,
            open_price, high_price, low_price, close_price, pre_close, pct_chg,
            volume, amount
        FROM stock_daily_snapshot
        WHERE trade_date >= $1::date
          AND trade_date <= $2::date
          AND source_name LIKE 'tushare%'
          AND ($3::text[] IS NULL OR stock_id = ANY($3::text[]))
        ORDER BY trade_date ASC, stock_id,
                 CASE WHEN source_name = 'tushare' THEN 0 ELSE 1 END,
                 updated_at DESC NULLS LAST
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, start_date, end_date, stock_ids if stock_ids else None)
            return [dict(row) for row in rows]

    async def get_stock_auction_snapshot(self, trade_date, stock_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        读取盘前竞价快照。只读取真实 pre_market_auction_snapshot，不使用日频代理。
        """
        sql = """
        SELECT
            trade_date, stock_id, stock_name,
            auction_open_price, auction_open_pct, auction_volume, auction_amount,
            NULL::numeric AS tail_auction_close_price,
            NULL::numeric AS tail_auction_volume,
            NULL::numeric AS tail_auction_amount,
            NULL::numeric AS tail_auction_vwap
        FROM pre_market_auction_snapshot
        WHERE trade_date = $1::date
          AND ($2::text[] IS NULL OR split_part(stock_id, '.', 1) = ANY($2::text[]))
        ORDER BY stock_id
        """
        normalized = None
        if stock_ids:
            normalized = [str(item).split(".", 1)[0] for item in stock_ids if str(item).strip()]
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, normalized)
        return [dict(row) for row in rows]

    async def upsert_pre_market_auction_snapshots(self, snapshots: List[Dict[str, Any]]) -> int:
        if not snapshots:
            return 0
        sql = """
        INSERT INTO pre_market_auction_snapshot (
            trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
            window_start_time, window_end_time, last_minute_start_time, last_30s_start_time,
            auction_open_price, pre_close, auction_open_pct, auction_volume, auction_amount,
            last_minute_amount, last_minute_ratio, prev_day_max_intraday_amount, carry_ratio,
            price_path_stability_score, is_red_zone, has_end_spike, has_end_drop, shape_features,
            source_type, source_trace_id, source_trace, source_version, rule_version, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10,
            $11, $12, $13, $14, $15,
            $16, $17, $18, $19,
            $20, $21, $22, $23, $24::jsonb,
            $25, $26, $27::jsonb, $28, $29, NOW()
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            role_label = EXCLUDED.role_label,
            window_start_time = EXCLUDED.window_start_time,
            window_end_time = EXCLUDED.window_end_time,
            last_minute_start_time = EXCLUDED.last_minute_start_time,
            last_30s_start_time = EXCLUDED.last_30s_start_time,
            auction_open_price = EXCLUDED.auction_open_price,
            pre_close = EXCLUDED.pre_close,
            auction_open_pct = EXCLUDED.auction_open_pct,
            auction_volume = EXCLUDED.auction_volume,
            auction_amount = EXCLUDED.auction_amount,
            last_minute_amount = EXCLUDED.last_minute_amount,
            last_minute_ratio = EXCLUDED.last_minute_ratio,
            prev_day_max_intraday_amount = EXCLUDED.prev_day_max_intraday_amount,
            carry_ratio = EXCLUDED.carry_ratio,
            price_path_stability_score = EXCLUDED.price_path_stability_score,
            is_red_zone = EXCLUDED.is_red_zone,
            has_end_spike = EXCLUDED.has_end_spike,
            has_end_drop = EXCLUDED.has_end_drop,
            shape_features = EXCLUDED.shape_features,
            source_type = EXCLUDED.source_type,
            source_trace_id = EXCLUDED.source_trace_id,
            source_trace = EXCLUDED.source_trace,
            source_version = EXCLUDED.source_version,
            rule_version = EXCLUDED.rule_version,
            updated_at = NOW()
        """
        payload = []
        for item in snapshots:
            payload.append(
                (
                    item["trade_date"],
                    str(item.get("stock_id") or ""),
                    str(item.get("stock_name") or ""),
                    str(item.get("subject_key") or ""),
                    str(item.get("theme_name") or ""),
                    str(item.get("role_label") or ""),
                    str(item.get("window_start_time") or "09:20:00"),
                    str(item.get("window_end_time") or "09:25:00"),
                    str(item.get("last_minute_start_time") or "09:24:00"),
                    str(item.get("last_30s_start_time") or "09:24:30"),
                    float(item.get("auction_open_price") or 0.0),
                    float(item.get("pre_close") or 0.0),
                    float(item.get("auction_open_pct") or 0.0),
                    float(item.get("auction_volume") or 0.0),
                    float(item.get("auction_amount") or 0.0),
                    float(item.get("last_minute_amount") or 0.0),
                    float(item.get("last_minute_ratio") or 0.0),
                    float(item.get("prev_day_max_intraday_amount") or 0.0),
                    float(item.get("carry_ratio") or 0.0),
                    float(item.get("price_path_stability_score") or 0.0),
                    bool(item.get("is_red_zone") or False),
                    bool(item.get("has_end_spike") or False),
                    bool(item.get("has_end_drop") or False),
                    _safe_json_dumps(item.get("shape_features"), []),
                    str(item.get("source_type") or "p3.phase3.auction_snapshot"),
                    str(item.get("source_trace_id") or ""),
                    _safe_json_dumps(item.get("source_trace"), {}),
                    str(item.get("source_version") or "auction_snapshot.v1"),
                    str(item.get("rule_version") or "auction_snapshot.v1"),
                )
            )
        async with self.pool.acquire() as conn:
            await conn.executemany(sql, payload)
        return len(payload)

    async def get_subject_context_by_subject_keys(self, subject_keys: List[str], trade_date) -> List[Dict[str, Any]]:
        """按题材键批量读取题材上下文（最小上下文：subject_key/subject_name/trade_date）。"""
        if not subject_keys:
            return []
        sql = """
        SELECT
            subject_key,
            MAX(subject_name) AS subject_name,
            $2::date AS trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $2::date
          AND subject_key = ANY($1::text[])
        GROUP BY subject_key
        ORDER BY subject_key
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, subject_keys, trade_date)
            return [dict(row) for row in rows]

    async def resolve_theme_name_map(
        self,
        subject_keys: List[str],
        trade_date: Optional[date] = None,
    ) -> Dict[str, str]:
        """按 subject_key 解析题材展示名，供新链只读出口统一使用。"""
        keys = [str(k).strip() for k in subject_keys if str(k).strip()]
        if not keys:
            return {}
        sql = """
        WITH keyset AS (
          SELECT DISTINCT unnest($1::text[]) AS subject_key
        )
        SELECT
          k.subject_key,
          COALESCE(
            (
              SELECT NULLIF(v2.theme_name, '')
              FROM theme_cycle_judgement_v2 v2
              WHERE v2.subject_key = k.subject_key
                AND NULLIF(v2.theme_name, '') IS NOT NULL
                AND v2.theme_name !~ '^[0-9]+$'
                AND ($2::date IS NULL OR v2.trade_date <= $2::date)
              ORDER BY v2.trade_date DESC
              LIMIT 1
            ),
            (
              SELECT NULLIF(sh.subject_name, '')
              FROM subject_history_staging sh
              WHERE sh.subject_key = k.subject_key
                AND NULLIF(sh.subject_name, '') IS NOT NULL
                AND ($2::date IS NULL OR sh.rank_date <= $2::date)
              ORDER BY sh.rank_date DESC
              LIMIT 1
            ),
            k.subject_key
          ) AS theme_name
        FROM keyset k
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, sorted(set(keys)), trade_date)
        return {str(row["subject_key"]): str(row["theme_name"] or row["subject_key"]) for row in rows}

    async def get_subject_event_stats(
        self,
        trade_date,
        subject_keys: List[str] | None = None,
        lookback_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """按 subject_keys 聚合事件统计（theme_history_event 直查）。

        返回每个 subject 的 today_event_count, recent_event_count, distinct_event_days,
        sample_summaries 以及 Python 后处理的 key_event_count。
        仅 jyhf_history 来源的事件参与聚合。
        """
        if not subject_keys:
            return []
        from datetime import timedelta

        start_date = trade_date - timedelta(days=max(lookback_days - 1, 0))

        sql = """
        SELECT
            the.subject_key,
            MAX(the.theme_name) AS theme_name,
            COUNT(*) FILTER (WHERE the.rank_date = $1::date) AS today_event_count,
            COUNT(*) AS recent_event_count,
            COUNT(DISTINCT the.rank_date) AS distinct_event_days,
            ARRAY_AGG(COALESCE(the.driver_summary, '') ORDER BY the.rank_date DESC) AS summaries
        FROM theme_history_event the
        WHERE the.source_type = 'jyhf_history'
          AND the.subject_key = ANY($2::text[])
          AND the.rank_date BETWEEN $3::date AND $1::date
        GROUP BY the.subject_key
        ORDER BY the.subject_key
        """
        KEY_EVENT_KEYWORDS = (
            "政策", "行动计划", "印发", "试验", "商用", "首飞",
            "发射", "订单", "量产", "投产", "ipo", "募股",
            "商业化", "里程碑",
        )

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, subject_keys, start_date)

        results: list[dict[str, Any]] = []
        for row in rows:
            r = dict(row)
            summaries_raw = r.get("summaries") or []
            summaries: list[str] = []
            for s in summaries_raw:
                if s and str(s).strip():
                    summaries.append(str(s).strip().splitlines()[0])
            key_count = 0
            for s in summaries:
                lowered = s.lower()
                if any(kw in lowered for kw in KEY_EVENT_KEYWORDS):
                    key_count += 1
            r["key_event_count"] = key_count
            r["sample_summaries"] = summaries[:5]
            r.pop("summaries", None)
            results.append(r)

        return results

    async def get_subject_cycle_evidence_daily(
        self,
        trade_date,
        subject_keys: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """读取旧链已写入的 theme_cycle_evidence_daily 预计算证据。

        旧链 ThemeCycleEvidenceBuilder + ThemeBoardStructureAggregator 每日写入该表，
        包含 event/leader/board/kline 四层证据的全部预计算字段。
        """
        if subject_keys is not None and not subject_keys:
            return []
        where_subject_keys = ""
        params: list[Any] = [trade_date]
        if subject_keys is not None:
            where_subject_keys = "AND subject_key = ANY($2::text[])"
            params.append(subject_keys)
        sql = f"""
        SELECT
            subject_key, trade_date, theme_name,
            event_count_3d, event_count_7d, strong_event_count_7d,
            event_recency_days, event_continuity_score, event_strength_score,
            leader_alive_score, leader_breakdown_flag,
            relay_strength_score, front_row_survival_ratio,
            board_stock_count, limit_up_count, limit_down_count,
            red_ratio, big_drop_ratio, front_row_strength_score,
            theme_ret_3d, theme_ret_5d, theme_ret_10d,
            above_ma5, above_ma10, above_ma20,
            break_start_pivot, volume_breakdown_flag, theme_support_score,
            mainline_strength_score, fade_risk_score,
            evidence_json
        FROM theme_cycle_evidence_daily
        WHERE trade_date = $1::date
          {where_subject_keys}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def get_mainline_state_daily(
        self, trade_date, subject_keys: List[str]
    ) -> List[Dict[str, Any]]:
        """读取 mainline_state_daily 状态快照（按 trade_date + subject_keys 过滤）。"""
        if not subject_keys:
            return []
        sql = """
        SELECT
            trade_date,
            subject_key,
            theme_name,
            state,
            state_score,
            is_mainline,
            mainline_strength_score,
            fade_watch_score,
            fade_confirmed_score,
            divergence_score,
            repair_score
        FROM mainline_state_daily
        WHERE trade_date = $1::date
          AND subject_key = ANY($2::text[])
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, subject_keys)
        return [dict(r) for r in rows]

    async def get_prior_mainline_state_daily(self, trade_date) -> List[Dict[str, Any]]:
        """读取前一交易日 mainline_state_daily 状态快照（仅主线）。"""
        sql = """
        WITH last_trade_date AS (
            SELECT MAX(trade_date) AS prior_date
            FROM mainline_state_daily
            WHERE trade_date < $1::date
        )
        SELECT * FROM mainline_state_daily msd
        JOIN last_trade_date ltd ON msd.trade_date = ltd.prior_date
        WHERE msd.is_mainline = TRUE
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def get_subject_rank_daily(self, trade_date, limit: int = 100) -> List[Dict[str, Any]]:
        """读取当日 subject_rank_daily 热点排行。"""
        sql = """
        SELECT subject_key, subject_name, heat, heat_name, pct_chg, his_pct_chg, description
        FROM subject_rank_daily
        WHERE rank_date = $1::date
        ORDER BY heat DESC NULLS LAST
        LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, limit)
        return [dict(r) for r in rows]

    async def get_subject_board_stats(
        self, trade_date
    ) -> List[Dict[str, Any]]:
        """当日各 subject 板块强度统计（涨停数/强势股数，不分 subject 过滤）。

        等价于旧链 subject_strength CTE:
          subject_limit_up_count = COUNT(DISTINCT stock_id) FILTER (WHERE limit_up)
          subject_strong_count = COUNT(DISTINCT stock_id) FILTER (
            WHERE limit_up OR pct_chg>=7.0 OR rank_order<=3)
        """
        sql = """
        SELECT
            subject_key,
            COUNT(DISTINCT stock_id) FILTER (WHERE COALESCE(limit_up, FALSE)) AS subject_limit_up_count,
            COUNT(DISTINCT stock_id) FILTER (
                WHERE COALESCE(limit_up, FALSE)
                   OR COALESCE(pct_chg, 0) >= 7.0
                   OR COALESCE(rank_order, 999) <= 3
            ) AS subject_strong_count
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
        GROUP BY subject_key
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def get_stock_position_judgement(
        self, trade_date, stock_ids: List[str] | None = None
    ) -> List[Dict[str, Any]]:
        """读取个股位置与均线判断（stock_position_judgement 表）。"""
        if not stock_ids:
            return []
        sql = """
        SELECT
            trade_date,
            stock_id,
            stock_name,
            position_label,
            ma_alignment_status,
            trend_strength_score
        FROM stock_position_judgement
        WHERE trade_date = $1::date
          AND split_part(stock_id, '.', 1) = ANY($2::text[])
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, stock_ids)
        return [dict(r) for r in rows]

    async def get_stock_pattern_judgement(
        self, trade_date, stock_ids: List[str] | None = None
    ) -> List[Dict[str, Any]]:
        """读取个股形态与量价模式判断（stock_pattern_judgement 表）。"""
        if not stock_ids:
            return []
        sql = """
        SELECT
            trade_date,
            stock_id,
            stock_name,
            COALESCE(pattern_labels, '[]'::jsonb) AS pattern_labels,
            COALESCE(volume_pattern_status, '') AS volume_pattern_status,
            COALESCE(breakout_status, '') AS breakout_status,
            COALESCE(pullback_status, '') AS pullback_status,
            COALESCE(risk_pattern_status, '') AS risk_pattern_status
        FROM stock_pattern_judgement
        WHERE trade_date = $1::date
          AND split_part(stock_id, '.', 1) = ANY($2::text[])
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, stock_ids)
        return [dict(r) for r in rows]

    async def get_strong_watch_seed_rows(
        self, trade_date, lookback_days: int = 7
    ) -> List[Dict[str, Any]]:
        """强势股观察池种子候选查询 — 复刻旧链 StrongStockTrackingService._fetch_seed_rows SQL。

        完整复刻旧链 4-CTE 查询:
          1. recent_trade_days — 最近 N 个交易日
          2. recent — 7日窗口 stock+subject 聚合
          3. subject_strength — 当日板块强度
          4. eligible — 双路径过滤 + identity/cycle/state JOIN
          5. ranked — cond_gene/cond_volume/cond_structure + ROW_NUMBER 去重
          最终: rn=1 AND (recent_limit_up>=2 OR (>=1 AND 3条件>=2))
        """
        sql = """
        WITH recent_trade_days AS (
            SELECT t.trade_date
            FROM (
                SELECT DISTINCT s.trade_date
                FROM subject_stock_daily_snapshot s
                WHERE s.trade_date <= $1::date
                ORDER BY s.trade_date DESC
                LIMIT $2::int
            ) t
        ),
        recent AS (
            SELECT
                stock_id,
                MAX(stock_name) AS stock_name,
                subject_key,
                COUNT(DISTINCT trade_date) AS total_trade_days,
                COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE)) AS recent_limit_up_count,
                MAX(CASE WHEN COALESCE(is_leader, FALSE) THEN 1 ELSE 0 END) AS is_leader_flag,
                MIN(COALESCE(rank_order, 999)) AS best_rank,
                MAX(
                    CASE
                        WHEN trade_date = $1::date
                             AND jsonb_typeof(raw_json) = 'array'
                             AND jsonb_array_length(raw_json) > 20
                        THEN COALESCE(NULLIF(raw_json->>20, ''), '0')::int
                        ELSE 0
                    END
                ) AS current_flag_today
            FROM subject_stock_daily_snapshot
            WHERE trade_date IN (SELECT trade_date FROM recent_trade_days)
            GROUP BY stock_id, subject_key
        ),
        subject_strength AS (
            SELECT
                subject_key,
                COUNT(DISTINCT stock_id) FILTER (WHERE COALESCE(limit_up, FALSE)) AS subject_limit_up_count,
                COUNT(DISTINCT stock_id) FILTER (
                    WHERE COALESCE(limit_up, FALSE)
                       OR COALESCE(pct_chg, 0) >= 7.0
                       OR COALESCE(rank_order, 999) <= 3
                ) AS subject_strong_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
            GROUP BY subject_key
        ),
        eligible AS (
            SELECT
                r.*,
                COALESCE(v2.theme_name, r.subject_key) AS theme_name,
                COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
                COALESCE(mr.identity_status, 'observed') AS identity_status,
                (
                    COALESCE(mr.is_main_theme, FALSE)
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                ) AS final_mainline_alive,
                COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score,
                COALESCE(ss.subject_limit_up_count, 0) AS subject_limit_up_count,
                COALESCE(ss.subject_strong_count, 0) AS subject_strong_count
            FROM recent r
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = r.subject_key
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = $1::date
             AND msd.subject_key = r.subject_key
            LEFT JOIN theme_cycle_judgement_v2 v2
              ON v2.trade_date = $1::date
             AND v2.subject_key = r.subject_key
            LEFT JOIN subject_strength ss
              ON ss.subject_key = r.subject_key
            WHERE (
                (
                    COALESCE(mr.is_main_theme, FALSE) = TRUE
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                    AND (
                        COALESCE(ss.subject_limit_up_count, 0) >= 2
                        OR COALESCE(ss.subject_strong_count, 0) >= 3
                    )
                )
                OR COALESCE(r.recent_limit_up_count, 0) >= 2
            )
        ),
        ranked AS (
            SELECT
                e.*,
                CASE
                    WHEN e.recent_limit_up_count >= 2
                      OR (e.is_leader_flag = 1 AND e.recent_limit_up_count >= 1)
                    THEN 1 ELSE 0
                END AS cond_gene,
                CASE WHEN e.current_flag_today >= 2 THEN 1 ELSE 0 END AS cond_volume,
                CASE WHEN e.is_leader_flag = 1 OR e.best_rank <= 5 THEN 1 ELSE 0 END AS cond_structure,
                ROW_NUMBER() OVER (
                    PARTITION BY e.stock_id
                    ORDER BY
                        e.mainline_strength_score DESC,
                        e.subject_limit_up_count DESC,
                        e.subject_strong_count DESC,
                        e.recent_limit_up_count DESC,
                        e.is_leader_flag DESC,
                        e.best_rank ASC
                ) AS rn
            FROM eligible e
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
          AND (
                COALESCE(recent_limit_up_count, 0) >= 2
                OR (
                    COALESCE(recent_limit_up_count, 0) >= 1
                    AND (cond_gene + cond_volume + cond_structure) >= 2
                )
              )
        ORDER BY mainline_strength_score DESC, recent_limit_up_count DESC, best_rank ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, int(max(1, lookback_days)))
        return [dict(r) for r in rows]

    async def get_strong_watch_refresh_rows(
        self, trade_date
    ) -> List[Dict[str, Any]]:
        """强势股观察池 refresh 候选 — 复刻旧链 StrongStockTrackingService._fetch_refresh_watch_pool SQL。

        读取 strong_stock_watch_pool 中 pending_seed/pending_refresh/active/weakening 状态的股票，
        附加上当日 current_flag_today。
        """
        sql = """
        SELECT
            p.*,
            COALESCE(sf.current_flag_today, 0) AS current_flag_today
        FROM strong_stock_watch_pool p
        LEFT JOIN (
            SELECT
                split_part(stock_id, '.', 1) AS stock_code,
                MAX(
                    CASE
                        WHEN jsonb_typeof(raw_json) = 'array' AND jsonb_array_length(raw_json) > 20
                        THEN COALESCE(NULLIF(raw_json->>20, ''), '0')::int
                        ELSE 0
                    END
                ) AS current_flag_today
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
            GROUP BY split_part(stock_id, '.', 1)
        ) sf
          ON sf.stock_code = split_part(p.stock_id, '.', 1)
        WHERE p.watch_status IN ('pending_seed', 'pending_refresh', 'active', 'weakening')
          AND p.last_trade_date <= $1::date
        ORDER BY
            CASE
                WHEN p.watch_status = 'pending_seed' THEN 0
                WHEN p.watch_status = 'pending_refresh' THEN 1
                WHEN p.watch_status = 'active' THEN 2
                ELSE 3
            END ASC,
            p.watch_score DESC,
            p.watch_priority DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def get_subject_market_stats(
        self,
        trade_date,
        subject_keys: List[str] | None = None,
        lookback_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """批量查询 subject 级市场统计。"""
        if not subject_keys:
            return []
        from datetime import timedelta
        start_date = trade_date - timedelta(days=max(lookback_days - 1, 0))
        sql = """
        SELECT
            subject_key,
            trade_date,
            COUNT(*) AS stock_count,
            COUNT(*) FILTER (WHERE limit_up) AS limit_up_count,
            COUNT(*) FILTER (WHERE pct_chg >= 5.0) AS strong_count,
            AVG(pct_chg) AS avg_pct_chg,
            SUM(CASE WHEN pct_chg <= -5.0 THEN 1 ELSE 0 END)::int AS weak_count
        FROM subject_stock_daily_snapshot
        WHERE subject_key = ANY($1::text[])
          AND trade_date BETWEEN $2::date AND $3::date
        GROUP BY subject_key, trade_date
        ORDER BY subject_key, trade_date
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, subject_keys, start_date, trade_date)
        return [dict(r) for r in rows]

    async def get_subject_heat_stats(
        self, trade_date, subject_keys: List[str] | None = None, lookback_days: int = 5
    ) -> List[Dict[str, Any]]:
        """批量查询 subject 级热度统计。"""
        if not subject_keys:
            return []
        from datetime import timedelta
        start_date = trade_date - timedelta(days=max(lookback_days - 1, 0))
        sql = """
        SELECT subject_key, rank_date, heat, heat_name, pct_chg
        FROM subject_rank_daily
        WHERE subject_key = ANY($1::text[])
          AND source_system = 'jyhf'
          AND rank_date BETWEEN $2::date AND $3::date
        ORDER BY subject_key, rank_date
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, subject_keys, start_date, trade_date)
        return [dict(r) for r in rows]

    async def get_prior_stock_daily_snapshots(
        self,
        trade_date,
        lookback_days: int,
        stock_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """读取交易日前 lookback_days 天的快照（真源行情 + 策略对象层拼接）。"""
        sql = """
        WITH market_rows AS (
            SELECT DISTINCT ON (m.trade_date, m.stock_id)
                m.trade_date,
                m.stock_id,
                m.stock_name,
                m.open_price,
                m.high_price,
                m.low_price,
                m.close_price,
                m.pre_close,
                m.pct_chg,
                m.volume,
                m.amount
            FROM stock_daily_snapshot m
            WHERE m.trade_date < $1::date
              AND m.trade_date >= ($1::date - $2::int * INTERVAL '1 day')
              AND m.source_name LIKE 'tushare%'
              AND ($3::text[] IS NULL OR m.stock_id = ANY($3::text[]))
            ORDER BY m.trade_date DESC, m.stock_id,
                     CASE WHEN m.source_name = 'tushare' THEN 0 ELSE 1 END,
                     m.updated_at DESC NULLS LAST
        )
        SELECT
            m.trade_date, m.stock_id, m.stock_name,
            m.open_price, m.high_price, m.low_price, m.close_price, m.pre_close, m.pct_chg,
            m.volume, m.amount,
            s.snapshot_version,
            jsonb_build_object(
                'final_cycle_state', COALESCE(s.labels->>'final_cycle_state', ''),
                'labels', COALESCE(s.labels, '{}'::jsonb),
                'score_breakdown', COALESCE(s.score_breakdown, '{}'::jsonb)
            ) AS payload
        FROM market_rows m
        LEFT JOIN stock_daily_strategy_snapshot s
          ON s.trade_date = m.trade_date
         AND s.stock_id = m.stock_id
        ORDER BY m.trade_date DESC, m.stock_id
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date, lookback_days, stock_ids if stock_ids else None)
            return [dict(row) for row in rows]

    async def get_existing_pre_market_brief_snapshot(self, trade_date) -> Optional[Dict[str, Any]]:
        """读取 pre_market_brief_snapshot 文档对象（存在则返回）。"""
        sql = """
        SELECT trade_date, snapshot_version, batch_id, trace_id, payload, created_at
        FROM pre_market_brief_snapshot
        WHERE trade_date = $1::date
        LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, trade_date)
                return dict(row) if row else None
        except Exception as e:
            logger.warning(f"读取 pre_market_brief_snapshot 失败（可能尚未迁移）: {e}")
            return None

    async def get_existing_post_market_recap_snapshot(self, trade_date) -> Optional[Dict[str, Any]]:
        """读取 post_market_recap_snapshot 文档对象（存在则返回）。"""
        sql = """
        SELECT trade_date, snapshot_version, batch_id, trace_id, payload, created_at
        FROM post_market_recap_snapshot
        WHERE trade_date = $1::date
        LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, trade_date)
                return dict(row) if row else None
        except Exception as e:
            logger.warning(f"读取 post_market_recap_snapshot 失败（可能尚未迁移）: {e}")
            return None

    async def get_latest_post_market_recap_trade_date(self):
        sql = "SELECT MAX(trade_date) AS trade_date FROM post_market_recap_snapshot"
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(sql)
        except Exception as e:
            logger.warning(f"读取 post_market_recap_snapshot 最新日期失败（可能尚未迁移）: {e}")
            return None

    async def get_latest_pre_market_brief_trade_date(self):
        sql = "SELECT MAX(trade_date) AS trade_date FROM pre_market_brief_snapshot"
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(sql)
        except Exception as e:
            logger.warning(f"读取 pre_market_brief_snapshot 最新日期失败（可能尚未迁移）: {e}")
            return None

    async def get_stock_screening_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT strategy_id, strategy_name, strategy_type, description,
               weight_config, filter_config, created_at, updated_at,
               created_by, is_active
        FROM stock_screening_strategy
        WHERE strategy_id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, strategy_id)
        return dict(row) if row else None

    async def get_stock_screening_strategies(self, active_only: bool = True) -> List[Dict[str, Any]]:
        sql = """
        SELECT strategy_id, strategy_name, strategy_type, description,
               weight_config, filter_config, created_at, updated_at,
               created_by, is_active
        FROM stock_screening_strategy
        WHERE ($1::boolean = false OR is_active = true)
        ORDER BY created_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, bool(active_only))
        return [dict(row) for row in rows]

    async def get_stock_screening_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT execution_id, strategy_id, trade_date, status, total_stocks,
               screened_stocks, results_count, execution_time_ms, error_message,
               created_at, completed_at
        FROM stock_screening_execution
        WHERE execution_id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, execution_id)
        return dict(row) if row else None

    async def get_stock_screening_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT result_id, strategy_id, trade_date, stock_id, stock_name,
               composite_score, dimension_scores, rank_position,
               screening_reason, theme_info, created_at
        FROM stock_screening_result
        WHERE result_id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, result_id)
        return dict(row) if row else None

    async def query_stock_screening_history(
        self,
        strategy_id: Optional[str] = None,
        trade_date_from: Optional[date] = None,
        trade_date_to: Optional[date] = None,
        stock_id: Optional[str] = None,
        min_score: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        sql = """
        SELECT result_id, strategy_id, trade_date, stock_id, stock_name,
               composite_score, dimension_scores, rank_position,
               screening_reason, theme_info, created_at,
               COUNT(*) OVER() AS total_count
        FROM stock_screening_result
        WHERE ($1::text IS NULL OR strategy_id = $1)
          AND ($2::date IS NULL OR trade_date >= $2::date)
          AND ($3::date IS NULL OR trade_date <= $3::date)
          AND ($4::text IS NULL OR stock_id = $4)
          AND ($5::numeric IS NULL OR composite_score >= $5::numeric)
        ORDER BY trade_date DESC, composite_score DESC
        LIMIT $6 OFFSET $7
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                sql,
                strategy_id,
                trade_date_from,
                trade_date_to,
                stock_id,
                min_score,
                max(int(limit), 1),
                max(int(offset), 0),
            )
        items = [dict(row) for row in rows]
        total = int(items[0].get("total_count") or 0) if items else 0
        for item in items:
            item.pop("total_count", None)
        return {"items": items, "total": total, "limit": max(int(limit), 1), "offset": max(int(offset), 0)}

    async def get_stock_screening_favorites(self, user_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT f.favorite_id, f.user_id, f.result_id, f.notes, f.tags, f.created_at,
               r.stock_id, r.stock_name, r.composite_score
        FROM user_stock_screening_favorite f
        JOIN stock_screening_result r ON r.result_id = f.result_id
        WHERE f.user_id = $1
        ORDER BY f.created_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, user_id)
        return [dict(row) for row in rows]

    async def add_stock_screening_favorite(self, favorite: Dict[str, Any]) -> bool:
        sql = """
        INSERT INTO user_stock_screening_favorite (
            favorite_id, user_id, result_id, notes, tags, created_at
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        ON CONFLICT (user_id, result_id) DO NOTHING
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                sql,
                favorite.get("favorite_id"),
                favorite.get("user_id"),
                favorite.get("result_id"),
                favorite.get("notes"),
                json.dumps(favorite.get("tags") or [], ensure_ascii=False),
                favorite.get("created_at") or datetime.now(),
            )
        return result.upper().startswith("INSERT 0 1")

    async def update_stock_screening_favorite(
        self,
        favorite_id: str,
        notes: Optional[str],
        tags: Optional[List[str]],
    ) -> bool:
        sql = """
        UPDATE user_stock_screening_favorite
        SET notes = COALESCE($2, notes),
            tags = COALESCE($3::jsonb, tags)
        WHERE favorite_id = $1
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                sql,
                favorite_id,
                notes,
                json.dumps(tags, ensure_ascii=False) if tags is not None else None,
            )
        return result.upper().startswith("UPDATE 1")

    async def remove_stock_screening_favorite(self, favorite_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM user_stock_screening_favorite WHERE favorite_id = $1", favorite_id)
        return result.upper().startswith("DELETE 1")

    async def get_stock_screening_statistics(
        self,
        strategy_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        sql = """
        SELECT COUNT(*)::int AS total_results,
               COALESCE(AVG(composite_score), 0)::numeric AS avg_composite_score
        FROM stock_screening_result
        WHERE ($1::text IS NULL OR strategy_id = $1)
          AND ($2::date IS NULL OR trade_date >= $2::date)
          AND ($3::date IS NULL OR trade_date <= $3::date)
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, strategy_id, date_from, date_to)
        data = dict(row) if row else {}
        return {
            "total_results": int(data.get("total_results") or 0),
            "avg_composite_score": float(data.get("avg_composite_score") or 0),
            "top_themes": [],
            "score_distribution": [],
        }

    async def infer_confirm_trade_date_from_candidate_trade_date(self, candidate_trade_date):
        sql = """
        SELECT MAX(next_trade_date) AS confirm_trade_date
        FROM weak_to_strong_candidate_pool
        WHERE trade_date = $1::date
          AND next_trade_date > $1::date
        """
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(sql, candidate_trade_date)
        except Exception as e:
            logger.warning(f"推断确认交易日失败（可能尚未迁移）: {e}")
            return None

    async def get_w2s_candidates_by_trade_date(self, candidate_trade_date, limit: int = 200) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          id, trade_date, next_trade_date, stock_id, stock_name, subject_key, theme_name,
          candidate_score, pool_entry_type, candidate_type, weak_type, support_type,
          support_strength, expected_open_low, expected_open_high, evidence_json
        FROM weak_to_strong_candidate_pool
        WHERE trade_date = $1::date
        ORDER BY candidate_score DESC, id ASC
        LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, candidate_trade_date, max(int(limit), 1))
        return [dict(r) for r in rows]

    async def get_w2s_signals_by_trade_date(self, trade_date) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          candidate_id, signal_level, decision, confirmation_score, auction_open_pct,
          auction_close_pct, auction_pattern, last_minute_grab_score, plate_follow_score,
          risk_penalty, data_status, evidence_json
        FROM weak_to_strong_auction_signal
        WHERE trade_date = $1::date
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def get_w2s_candidates_for_confirm_date(self, confirm_trade_date, limit: int = 200) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          id, trade_date, next_trade_date, stock_id, stock_name, subject_key, theme_name,
          candidate_score, pool_entry_type, candidate_type, weak_type, support_type,
          support_strength, expected_open_low, expected_open_high, evidence_json
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
        ORDER BY candidate_score DESC, id ASC
        LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, confirm_trade_date, max(int(limit), 1))
        return [dict(r) for r in rows]

    async def count_w2s_candidates_for_confirm_date(self, confirm_trade_date) -> int:
        sql = """
        SELECT COUNT(*)::int AS cnt
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
        """
        async with self.pool.acquire() as conn:
            return int(await conn.fetchval(sql, confirm_trade_date) or 0)

    async def count_w2s_formal_candidates_for_confirm_date(self, confirm_trade_date) -> int:
        sql = """
        SELECT COUNT(*)::int AS cnt
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
          AND COALESCE(NULLIF(LOWER(pool_entry_type), ''), 'formal') = 'formal'
        """
        async with self.pool.acquire() as conn:
            return int(await conn.fetchval(sql, confirm_trade_date) or 0)

    async def get_w2s_candidates_by_ids(self, candidate_ids: List[int]) -> List[Dict[str, Any]]:
        cleaned_ids = sorted({int(item) for item in candidate_ids if int(item) > 0})
        if not cleaned_ids:
            return []
        sql = """
        SELECT
          id, trade_date, next_trade_date, stock_id, stock_name, subject_key, theme_name,
          candidate_score, pool_entry_type, candidate_type, weak_type, support_type,
          support_strength, expected_open_low, expected_open_high, evidence_json
        FROM weak_to_strong_candidate_pool
        WHERE id = ANY($1::int[])
        ORDER BY candidate_score DESC, id ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, cleaned_ids)
        return [dict(r) for r in rows]

    async def get_w2s_candidate_replay_by_id(self, candidate_id: int) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            c.id AS candidate_id,
            c.trade_date AS candidate_trade_date,
            c.next_trade_date,
            c.stock_id,
            c.stock_name,
            c.subject_key,
            c.theme_name,
            c.candidate_type,
            c.candidate_score,
            c.support_type,
            c.support_strength,
            c.pool_entry_type,
            c.cycle_state,
            c.mainline_strength_score,
            c.fade_watch,
            c.fade_confirmed,
            c.evidence_json AS candidate_evidence,
            s.trade_date AS signal_trade_date,
            s.signal_level,
            s.decision,
            s.confirmation_score,
            s.data_status,
            s.auction_open_pct,
            s.auction_close_pct,
            s.auction_pattern,
            s.last_minute_grab_score,
            s.plate_follow_score,
            s.risk_penalty,
            s.evidence_json AS signal_evidence
        FROM weak_to_strong_candidate_pool c
        LEFT JOIN weak_to_strong_auction_signal s
          ON s.candidate_id = c.id
        WHERE c.id = $1
        LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, int(candidate_id))
        return dict(row) if row else None

    async def get_w2s_snapshot_coverage(self, confirm_trade_date) -> Dict[str, int]:
        sql = """
        SELECT
          COUNT(*)::int AS candidate_cnt,
          COUNT(*) FILTER (WHERE s.stock_id IS NOT NULL)::int AS snapshot_hit_cnt
        FROM weak_to_strong_candidate_pool c
        LEFT JOIN pre_market_auction_snapshot s
          ON split_part(s.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
         AND s.trade_date = c.next_trade_date
        WHERE c.next_trade_date = $1::date
          AND COALESCE(NULLIF(LOWER(c.pool_entry_type), ''), 'formal') = 'formal'
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, confirm_trade_date)
        m = dict(row) if row else {}
        return {
            "candidate_cnt": int(m.get("candidate_cnt") or 0),
            "snapshot_hit_cnt": int(m.get("snapshot_hit_cnt") or 0),
        }

    async def get_latest_strong_watch_trade_date(self):
        sql = "SELECT MAX(trade_date) AS trade_date FROM strong_stock_watch_history"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql)

    async def get_trade_dates_before_or_on(self, end_date, limit: int = 7) -> List[date]:
        sql = """
        SELECT DISTINCT trade_date
        FROM stock_daily_snapshot
        WHERE trade_date <= $1::date
        ORDER BY trade_date DESC
        LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, end_date, max(int(limit), 1))
        return [r["trade_date"] for r in rows if r.get("trade_date")]

    async def get_strong_stock_watch_view_rows(
        self,
        end_date,
        window_days: int = 7,
        include_removed: bool = False,
        latest_per_stock: bool = True,
        stock_id: str | None = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = """
        WITH selected_trade_dates AS (
            SELECT DISTINCT trade_date
            FROM stock_daily_snapshot
            WHERE trade_date <= $1::date
            ORDER BY trade_date DESC
            LIMIT $2
        ),
        daily_snapshot_dedup AS (
            SELECT
                s.trade_date,
                split_part(s.stock_id, '.', 1) AS stock_code,
                MAX(s.pct_chg) AS pct_chg,
                MAX(COALESCE(NULLIF(s.raw_json->>20, ''), '0')::integer) AS current_flag
            FROM subject_stock_daily_snapshot s
            WHERE s.trade_date IN (SELECT trade_date FROM selected_trade_dates)
            GROUP BY s.trade_date, split_part(s.stock_id, '.', 1)
        ),
        base AS (
            SELECT
                h.trade_date::text AS trade_date,
                h.stock_id,
                h.stock_name,
                h.subject_key,
                COALESCE(NULLIF(BTRIM(h.theme_name), ''), h.subject_key) AS theme_name,
                h.watch_status,
                h.watch_score,
                h.watch_priority,
                h.relay_role,
                h.pool_entry_type,
                h.cycle_state,
                h.mainline_strength_score,
                h.fade_watch,
                h.fade_confirmed,
                h.promoted_to_candidate,
                h.support_type,
                h.support_level,
                h.support_score,
                h.labels_json,
                h.evidence_json,
                s.pct_chg,
                COALESCE(s.current_flag, 0) AS current_flag,
                ROW_NUMBER() OVER (
                    PARTITION BY split_part(h.stock_id, '.', 1)
                    ORDER BY h.trade_date DESC, h.watch_score DESC, h.watch_priority DESC
                ) AS rn
            FROM strong_stock_watch_history h
            LEFT JOIN daily_snapshot_dedup s
              ON s.trade_date = h.trade_date
             AND s.stock_code = split_part(h.stock_id, '.', 1)
            WHERE h.trade_date IN (SELECT trade_date FROM selected_trade_dates)
              AND ($3::boolean OR h.watch_status IN ('active', 'weakening'))
              AND ($4::text IS NULL OR split_part(h.stock_id, '.', 1) = split_part($4::text, '.', 1))
        )
        SELECT *
        FROM base
        WHERE ($5::boolean = FALSE OR rn = 1)
        ORDER BY theme_name ASC, trade_date DESC, watch_score DESC, watch_priority DESC
        LIMIT $6
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                sql,
                end_date,
                max(int(window_days), 1),
                bool(include_removed),
                stock_id,
                bool(latest_per_stock),
                max(int(limit), 1),
            )
        return [dict(r) for r in rows]

    async def get_mainline_identity_by_subject_keys(
        self,
        subject_keys: List[str],
        trade_date,
    ) -> List[Dict[str, Any]]:
        """读取 Layer A 主线身份真源。"""
        if not subject_keys:
            return []
        page_size = 500
        legacy_anytime_sql = """
        SELECT DISTINCT ON (subject_key)
            subject_key,
            COALESCE(identity_status, '') AS identity_status,
            COALESCE(is_main_theme, FALSE) AS is_main_theme,
            first_confirmed_date,
            last_review_date,
            COALESCE(rule_version, '') AS rule_version
        FROM theme_mainline_identity_registry
        WHERE subject_key = ANY($1::text[])
        ORDER BY subject_key, updated_at DESC NULLS LAST
        """
        gate_mode = str(os.getenv("SPS_IDENTITY_GATE_MODE", "asof")).strip().lower()
        try:
            async with self.pool.acquire() as conn:
                all_rows: list[Dict[str, Any]] = []
                for i in range(0, len(subject_keys), page_size):
                    chunk = subject_keys[i : i + page_size]
                    rows = await conn.fetch(legacy_anytime_sql, chunk)
                    all_rows.extend(dict(row) for row in rows)
                return all_rows
        except Exception as e:
            logger.warning(f"读取 theme_mainline_identity_registry 失败（可能尚未迁移）: {e}")
            return []

    async def get_mainline_identity_rule_inputs(
        self,
        trade_date,
        subject_keys: List[str],
    ) -> List[Dict[str, Any]]:
        """读取 Layer A 身份规则输入。

        SQL 口径必须与旧链 `stock_service/scripts/build_mainline_identity_registry.py`
        `_fetch_latest_mainline_scores()` 保持一致；这里仅迁移数据访问边界，不改业务规则。
        """
        if not subject_keys:
            return []

        sql = """
        WITH tw_5 AS (
            SELECT rank_date
            FROM (
                SELECT DISTINCT r.rank_date
                FROM subject_rank_daily r
                WHERE r.rank_date <= $2::date
                ORDER BY r.rank_date DESC
                LIMIT 5
            ) t
        ),
        tw_10 AS (
            SELECT rank_date
            FROM (
                SELECT DISTINCT r.rank_date
                FROM subject_rank_daily r
                WHERE r.rank_date <= $2::date
                ORDER BY r.rank_date DESC
                LIMIT 10
            ) t
        ),
        tw_20 AS (
            SELECT rank_date
            FROM (
                SELECT DISTINCT r.rank_date
                FROM subject_rank_daily r
                WHERE r.rank_date <= $2::date
                ORDER BY r.rank_date DESC
                LIMIT 20
            ) t
        ),
        tw_30 AS (
            SELECT rank_date
            FROM (
                SELECT DISTINCT r.rank_date
                FROM subject_rank_daily r
                WHERE r.rank_date <= $2::date
                ORDER BY r.rank_date DESC
                LIMIT 30
            ) t
        ),
        rank_latest AS (
            SELECT
                r.subject_key,
                r.rank_date AS source_trade_date,
                COALESCE(r.heat, 0) AS heat_latest,
                COALESCE(r.his_pct_chg, 0) AS his_pct_chg_latest
            FROM subject_rank_daily r
            WHERE r.subject_key = $1
              AND r.rank_date <= $2::date
            ORDER BY r.rank_date DESC
            LIMIT 1
        ),
        rank_5d AS (
            SELECT
                r.subject_key,
                COALESCE(AVG(COALESCE(r.heat, 0)), 0) AS avg_heat_5d,
                COUNT(*) FILTER (WHERE COALESCE(r.heat, 0) >= 70) AS hot_days_5d
            FROM subject_rank_daily r
            JOIN tw_5
              ON tw_5.rank_date = r.rank_date
            WHERE r.subject_key = $1
            GROUP BY r.subject_key
        ),
        rank_20d AS (
            SELECT
                r.subject_key,
                COUNT(*) AS active_days_20d
            FROM subject_rank_daily r
            JOIN tw_20
              ON tw_20.rank_date = r.rank_date
            WHERE r.subject_key = $1
            GROUP BY r.subject_key
        ),
        rank_10d AS (
            SELECT
                r.subject_key,
                COUNT(*) AS active_days_10d
            FROM subject_rank_daily r
            JOIN tw_10
              ON tw_10.rank_date = r.rank_date
            WHERE r.subject_key = $1
            GROUP BY r.subject_key
        ),
        rank_30d AS (
            SELECT
                $1::varchar AS subject_key,
                ARRAY_AGG(COALESCE(r.his_pct_chg, 0)::numeric ORDER BY tw_30.rank_date ASC) AS his_pct_chg_30d
            FROM tw_30
            LEFT JOIN subject_rank_daily r
              ON r.subject_key = $1
             AND r.rank_date = tw_30.rank_date
        ),
        ev_latest AS (
            SELECT
                e.subject_key,
                e.trade_date,
                COALESCE(e.theme_name, '') AS theme_name,
                COALESCE(e.event_count_3d, 0) AS event_count_3d,
                COALESCE(e.event_count_7d, 0) AS event_count_7d,
                COALESCE(e.strong_event_count_7d, 0) AS strong_event_count_7d,
                COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
                COALESCE(e.event_strength_score, 0) AS event_strength_score,
                COALESCE(e.event_recency_days, 99) AS event_recency_days,
                COALESCE(e.board_stock_count, 0) AS board_stock_count,
                COALESCE(e.limit_up_count, 0) AS limit_up_count,
                COALESCE(e.front_row_strength_score, 0) AS front_row_strength_score,
                COALESCE(e.front_row_survival_ratio, 0) AS front_row_alive_ratio,
                COALESCE(e.above_ma10, FALSE) AS above_ma10,
                COALESCE(e.above_ma20, FALSE) AS above_ma20,
                COALESCE(e.theme_support_score, 0) AS theme_support_score,
                COALESCE(e.theme_ret_10d, 0) AS theme_ret_10d
            FROM theme_cycle_evidence_daily e
            WHERE e.subject_key = $1
              AND e.trade_date <= $2::date
            ORDER BY e.trade_date DESC
            LIMIT 1
        ),
        ev_5d AS (
            SELECT
                e.subject_key,
                COUNT(*) FILTER (
                    WHERE COALESCE(e.limit_up_count, 0) >= 2
                      AND (
                        CASE
                          WHEN COALESCE(e.board_stock_count, 0) > 0
                          THEN COALESCE(e.limit_up_count, 0)::numeric / e.board_stock_count::numeric
                          ELSE 0
                        END
                      ) >= 0.03
                ) AS board_boom_days_5d
            FROM theme_cycle_evidence_daily e
            JOIN tw_5
              ON tw_5.rank_date = e.trade_date
            WHERE e.subject_key = $1
            GROUP BY e.subject_key
        ),
        flow_daily AS (
            SELECT
                m.subject_key,
                m.trade_date,
                COALESCE(SUM(COALESCE(m.main_net_inflow, 0)), 0) AS net_inflow_day
            FROM money_flow_enhanced m
            JOIN tw_5
              ON tw_5.rank_date = m.trade_date
            WHERE m.subject_key = $1
            GROUP BY m.subject_key, m.trade_date
        ),
        flow_5d AS (
            SELECT
                subject_key,
                COALESCE(SUM(net_inflow_day), 0) AS net_inflow_sum_5d,
                COUNT(*) FILTER (WHERE net_inflow_day > 0) AS net_inflow_days_5d
            FROM flow_daily
            GROUP BY subject_key
        ),
        base_subject AS (
            SELECT $1::varchar AS subject_key
        )
        SELECT
            b.subject_key,
            COALESCE(v2n.theme_name, ev.theme_name, v.theme_name, b.subject_key) AS theme_name,
            COALESCE(rl.source_trade_date, ev.trade_date, $2::date) AS source_trade_date,
            COALESCE(rl.heat_latest, 0) AS heat_latest,
            COALESCE(rl.his_pct_chg_latest, 0) AS his_pct_chg_latest,
            COALESCE(r5.avg_heat_5d, 0) AS avg_heat_5d,
            COALESCE(r5.hot_days_5d, 0) AS hot_days_5d,
            COALESCE(r10.active_days_10d, 0) AS active_days_10d,
            COALESCE(r20.active_days_20d, 0) AS active_days_20d,
            COALESCE(r30.his_pct_chg_30d, ARRAY[]::numeric[]) AS his_pct_chg_30d,
            COALESCE(ev.event_count_3d, 0) AS event_count_3d,
            COALESCE(ev.event_count_7d, 0) AS event_count_7d,
            COALESCE(ev.strong_event_count_7d, 0) AS strong_event_count_7d,
            COALESCE(ev.event_continuity_score, 0) AS event_continuity_score,
            COALESCE(ev.event_strength_score, 0) AS event_strength_score,
            COALESCE(ev.event_recency_days, 99) AS event_recency_days,
            COALESCE(ev.board_stock_count, 0) AS board_stock_count,
            COALESCE(ev.limit_up_count, 0) AS limit_up_count,
            COALESCE(ev.front_row_strength_score, 0) AS front_row_strength_score,
            COALESCE(ev.front_row_alive_ratio, 0) AS front_row_alive_ratio,
            COALESCE(ev.above_ma10, FALSE) AS above_ma10,
            COALESCE(ev.above_ma20, FALSE) AS above_ma20,
            COALESCE(ev.theme_support_score, 0) AS theme_support_score,
            COALESCE(ev.theme_ret_10d, 0) AS theme_ret_10d,
            COALESCE(ev5.board_boom_days_5d, 0) AS board_boom_days_5d,
            COALESCE(f5.net_inflow_sum_5d, 0) AS net_inflow_sum_5d,
            COALESCE(f5.net_inflow_days_5d, 0) AS net_inflow_days_5d
        FROM base_subject b
        LEFT JOIN rank_latest rl
          ON rl.subject_key = b.subject_key
        LEFT JOIN vw_subject_theme_binding v
          ON v.subject_key = b.subject_key
        LEFT JOIN (
          SELECT v2.subject_key, v2.theme_name
          FROM theme_cycle_judgement_v2 v2
          WHERE v2.subject_key = $1
            AND v2.trade_date <= $2::date
          ORDER BY v2.trade_date DESC
          LIMIT 1
        ) v2n
          ON v2n.subject_key = b.subject_key
        LEFT JOIN rank_5d r5
          ON r5.subject_key = b.subject_key
        LEFT JOIN rank_10d r10
          ON r10.subject_key = b.subject_key
        LEFT JOIN rank_20d r20
          ON r20.subject_key = b.subject_key
        LEFT JOIN rank_30d r30
          ON r30.subject_key = b.subject_key
        LEFT JOIN ev_latest ev
          ON ev.subject_key = b.subject_key
        LEFT JOIN ev_5d ev5
          ON ev5.subject_key = b.subject_key
        LEFT JOIN flow_5d f5
          ON f5.subject_key = b.subject_key
        """

        results: list[Dict[str, Any]] = []
        async with self.pool.acquire() as conn:
            for subject_key in sorted({str(x) for x in subject_keys if str(x).strip()}):
                row = await conn.fetchrow(sql, subject_key, trade_date)
                if row:
                    results.append(dict(row))
        return results

    async def get_mainline_cycle_by_subject_keys(
        self,
        subject_keys: List[str],
        trade_date,
    ) -> List[Dict[str, Any]]:
        """读取 Layer B 周期状态真源。"""
        if not subject_keys:
            return []
        page_size = 500

        try:
            async with self.pool.acquire() as conn:
                cols = await conn.fetch(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'theme_cycle_judgement_v2'
                    """
                )
                col_set = {str(r["column_name"]) for r in cols}

                def col(name: str, default_name: str) -> str:
                    return name if name in col_set else default_name

                sql = f"""
                SELECT
                    trade_date,
                    subject_key,
                    {col('final_cycle_state', "''::text")} AS final_cycle_state,
                    {col('final_mainline_alive', 'FALSE')} AS final_mainline_alive,
                    CASE
                        WHEN {col('final_cycle_state', "''::text")} = 'fade_confirmed' THEN 'fade'
                        WHEN {col('previous_cycle_state', "''::text")} IN ('', 'unknown') THEN 'flat'
                        WHEN {col('previous_cycle_state', "''::text")} = {col('final_cycle_state', "''::text")} THEN 'flat'
                        ELSE CASE
                            WHEN (
                                CASE {col('final_cycle_state', "''::text")}
                                  WHEN 'fade_confirmed' THEN 0
                                  WHEN 'fade_watch' THEN 1
                                  WHEN 'start' THEN 2
                                  WHEN 'fermentation' THEN 3
                                  WHEN 'divergence' THEN 4
                                  WHEN 'repair' THEN 5
                                  WHEN 'acceleration' THEN 6
                                  ELSE -1
                                END
                            ) > (
                                CASE {col('previous_cycle_state', "''::text")}
                                  WHEN 'fade_confirmed' THEN 0
                                  WHEN 'fade_watch' THEN 1
                                  WHEN 'start' THEN 2
                                  WHEN 'fermentation' THEN 3
                                  WHEN 'divergence' THEN 4
                                  WHEN 'repair' THEN 5
                                  WHEN 'acceleration' THEN 6
                                  ELSE -1
                                END
                            ) THEN 'upgrade'
                            WHEN (
                                CASE {col('final_cycle_state', "''::text")}
                                  WHEN 'fade_confirmed' THEN 0
                                  WHEN 'fade_watch' THEN 1
                                  WHEN 'start' THEN 2
                                  WHEN 'fermentation' THEN 3
                                  WHEN 'divergence' THEN 4
                                  WHEN 'repair' THEN 5
                                  WHEN 'acceleration' THEN 6
                                  ELSE -1
                                END
                            ) < (
                                CASE {col('previous_cycle_state', "''::text")}
                                  WHEN 'fade_confirmed' THEN 0
                                  WHEN 'fade_watch' THEN 1
                                  WHEN 'start' THEN 2
                                  WHEN 'fermentation' THEN 3
                                  WHEN 'divergence' THEN 4
                                  WHEN 'repair' THEN 5
                                  WHEN 'acceleration' THEN 6
                                  ELSE -1
                                END
                            ) THEN 'downgrade'
                            ELSE 'flat'
                        END
                    END AS transition_type,
                    {col('confidence_score', '0::numeric')} AS transition_confidence,
                    COALESCE({col('risk_flags', "'[]'::jsonb")}, '[]'::jsonb) AS trigger_flags,
                    {col('mainline_strength_score', '0::numeric')} AS mainline_strength_score,
                    {col('repair_score', '0::numeric')} AS repair_score,
                    {col('divergence_score', '0::numeric')} AS divergence_score,
                    {col('fade_watch_score', '0::numeric')} AS fade_watch_score,
                    {col('fade_confirmed_score', '0::numeric')} AS fade_confirmed_score
                FROM theme_cycle_judgement_v2
                WHERE trade_date = $2::date
                  AND subject_key = ANY($1::text[])
                ORDER BY subject_key
                """
                all_rows: list[Dict[str, Any]] = []
                for i in range(0, len(subject_keys), page_size):
                    chunk = subject_keys[i : i + page_size]
                    rows = await conn.fetch(sql, chunk, trade_date)
                    all_rows.extend(dict(row) for row in rows)
                return all_rows
        except Exception as e:
            logger.warning(f"读取 theme_cycle_judgement_v2 失败（可能尚未迁移）: {e}")
            return []

    async def get_legacy_strong_watch_candidate_inputs(
        self,
        trade_date,
        lookback_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """读取旧链 weak_to_strong_candidate_builder 的正式 watch_pool 输入口径。"""
        current_pool_sql = """
        WITH watch_base AS (
            SELECT
                p.last_trade_date AS trade_date,
                split_part(p.stock_id, '.', 1) AS stock_code,
                p.stock_id,
                COALESCE(s.stock_name, p.stock_name) AS stock_name,
                COALESCE(NULLIF(p.subject_key, ''), s.subject_key) AS subject_key,
                COALESCE(NULLIF(p.theme_name, ''), NULLIF(v2.theme_name, ''), s.subject_key, p.subject_key) AS theme_name,
                COALESCE(s.rank_order, 999) AS rank_order,
                COALESCE(s.pct_chg, 0) AS pct_chg,
                COALESCE(s.low_price, 0) AS low_price,
                COALESCE(s.close_price, 0) AS close_price,
                COALESCE(s.limit_up, FALSE) AS limit_up,
                COALESCE(s.is_leader, FALSE) AS is_leader,
                COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
                COALESCE(mr.identity_status, 'observed') AS identity_status,
                COALESCE(v2.final_cycle_state, p.cycle_state, 'unknown') AS final_cycle_state,
                (
                    COALESCE(mr.is_main_theme, FALSE)
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, p.cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, p.fade_confirmed, FALSE) = FALSE
                ) AS final_mainline_alive,
                COALESCE(v2.fade_watch, p.fade_watch, FALSE) AS fade_watch,
                COALESCE(v2.fade_confirmed, p.fade_confirmed, FALSE) AS fade_confirmed,
                COALESCE(v2.mainline_strength_score, e.mainline_strength_score, p.mainline_strength_score, 0) AS mainline_strength_score,
                COALESCE(e.leader_alive_score, 0) AS leader_alive_score,
                COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
                p.watch_score,
                p.watch_priority,
                p.pool_entry_type AS watch_pool_entry_type,
                p.watch_status,
                p.source_tag AS watch_source_tag,
                p.labels_json AS watch_labels_json,
                p.support_type,
                p.support_level,
                p.support_score
            FROM strong_stock_watch_pool p
            LEFT JOIN subject_stock_daily_snapshot s
              ON s.trade_date = $1::date
             AND split_part(s.stock_id, '.', 1) = split_part(p.stock_id, '.', 1)
             AND COALESCE(NULLIF(p.subject_key, ''), s.subject_key) = s.subject_key
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = $1::date
             AND msd.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_judgement_v2 v2
              ON v2.trade_date = $1::date
             AND v2.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_evidence_daily e
              ON e.trade_date = $1::date
             AND e.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            WHERE p.watch_status IN ('active', 'weakening')
              AND p.pool_entry_type IN ('formal', 'observe_only')
              AND p.last_trade_date <= $1::date
        ),
        recent_stats AS (
            SELECT stock_id, COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE OR COALESCE(pct_chg, 0) >= 9.5) AS recent_limit_up_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date > ($1::date - INTERVAL '30 days')
            GROUP BY stock_id
        ),
        prior7_stats AS (
            SELECT
                stock_id,
                COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE OR COALESCE(pct_chg, 0) >= 9.5) AS prior7_limitup_days,
                COUNT(DISTINCT trade_date) FILTER (
                    WHERE COALESCE(limit_up, FALSE) = TRUE
                       OR COALESCE(is_leader, FALSE) = TRUE
                       OR COALESCE(rank_order, 999) <= 3
                       OR COALESCE(pct_chg, 0) >= 7.0
                ) AS prior7_strong_days
            FROM subject_stock_daily_snapshot
            WHERE trade_date < $1::date
              AND trade_date >= ($1::date - ($2::int * INTERVAL '1 day'))
            GROUP BY stock_id
        ),
        prev_day AS (
            SELECT stock_id, pct_chg AS prev_day_pct_chg, limit_up AS prev_day_limit_up, low_price AS prev_day_low_price, close_price AS prev_day_close_price
            FROM (
                SELECT stock_id, pct_chg, limit_up, low_price, close_price,
                       ROW_NUMBER() OVER (PARTITION BY stock_id ORDER BY trade_date DESC) AS rn
                FROM subject_stock_daily_snapshot
                WHERE trade_date < $1::date
            ) t
            WHERE rn = 1
        )
        SELECT
            b.*,
            COALESCE(rs.recent_limit_up_count, 0) AS recent_limit_up_count,
            COALESCE(p7.prior7_limitup_days, 0) AS prior7_limitup_days,
            COALESCE(p7.prior7_strong_days, 0) AS prior7_strong_days,
            pd.prev_day_pct_chg,
            pd.prev_day_limit_up,
            pd.prev_day_low_price,
            pd.prev_day_close_price
        FROM watch_base b
        LEFT JOIN recent_stats rs ON split_part(rs.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        LEFT JOIN prior7_stats p7 ON split_part(p7.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        LEFT JOIN prev_day pd ON split_part(pd.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        ORDER BY b.watch_priority DESC NULLS LAST, b.watch_score DESC NULLS LAST
        """
        history_sql = """
        WITH watch_base AS (
            SELECT
                p.trade_date AS trade_date,
                split_part(p.stock_id, '.', 1) AS stock_code,
                p.stock_id,
                COALESCE(s.stock_name, p.stock_name) AS stock_name,
                COALESCE(NULLIF(p.subject_key, ''), s.subject_key) AS subject_key,
                COALESCE(NULLIF(p.theme_name, ''), NULLIF(v2.theme_name, ''), s.subject_key, p.subject_key) AS theme_name,
                COALESCE(s.rank_order, 999) AS rank_order,
                COALESCE(s.pct_chg, 0) AS pct_chg,
                COALESCE(s.low_price, 0) AS low_price,
                COALESCE(s.close_price, 0) AS close_price,
                COALESCE(s.limit_up, FALSE) AS limit_up,
                COALESCE(s.is_leader, FALSE) AS is_leader,
                COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
                COALESCE(mr.identity_status, 'observed') AS identity_status,
                COALESCE(v2.final_cycle_state, p.cycle_state, 'unknown') AS final_cycle_state,
                (
                    COALESCE(mr.is_main_theme, FALSE)
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, p.cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, p.fade_confirmed, FALSE) = FALSE
                ) AS final_mainline_alive,
                COALESCE(v2.fade_watch, p.fade_watch, FALSE) AS fade_watch,
                COALESCE(v2.fade_confirmed, p.fade_confirmed, FALSE) AS fade_confirmed,
                COALESCE(v2.mainline_strength_score, e.mainline_strength_score, p.mainline_strength_score, 0) AS mainline_strength_score,
                COALESCE(e.leader_alive_score, 0) AS leader_alive_score,
                COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
                p.watch_score,
                p.watch_priority,
                p.pool_entry_type AS watch_pool_entry_type,
                p.watch_status,
                'history_snapshot'::text AS watch_source_tag,
                p.labels_json AS watch_labels_json,
                p.support_type,
                p.support_level,
                p.support_score
            FROM strong_stock_watch_history p
            LEFT JOIN subject_stock_daily_snapshot s
              ON s.trade_date = $1::date
             AND split_part(s.stock_id, '.', 1) = split_part(p.stock_id, '.', 1)
             AND COALESCE(NULLIF(p.subject_key, ''), s.subject_key) = s.subject_key
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = $1::date
             AND msd.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_judgement_v2 v2
              ON v2.trade_date = $1::date
             AND v2.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_evidence_daily e
              ON e.trade_date = $1::date
             AND e.subject_key = COALESCE(NULLIF(p.subject_key, ''), s.subject_key)
            WHERE p.watch_status IN ('active', 'weakening')
              AND p.pool_entry_type IN ('formal', 'observe_only')
              AND p.trade_date = $1::date
        ),
        recent_stats AS (
            SELECT stock_id, COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE OR COALESCE(pct_chg, 0) >= 9.5) AS recent_limit_up_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date > ($1::date - INTERVAL '30 days')
            GROUP BY stock_id
        ),
        prior7_stats AS (
            SELECT
                stock_id,
                COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE OR COALESCE(pct_chg, 0) >= 9.5) AS prior7_limitup_days,
                COUNT(DISTINCT trade_date) FILTER (
                    WHERE COALESCE(limit_up, FALSE) = TRUE
                       OR COALESCE(is_leader, FALSE) = TRUE
                       OR COALESCE(rank_order, 999) <= 3
                       OR COALESCE(pct_chg, 0) >= 7.0
                ) AS prior7_strong_days
            FROM subject_stock_daily_snapshot
            WHERE trade_date < $1::date
              AND trade_date >= ($1::date - ($2::int * INTERVAL '1 day'))
            GROUP BY stock_id
        ),
        prev_day AS (
            SELECT stock_id, pct_chg AS prev_day_pct_chg, limit_up AS prev_day_limit_up, low_price AS prev_day_low_price, close_price AS prev_day_close_price
            FROM (
                SELECT stock_id, pct_chg, limit_up, low_price, close_price,
                       ROW_NUMBER() OVER (PARTITION BY stock_id ORDER BY trade_date DESC) AS rn
                FROM subject_stock_daily_snapshot
                WHERE trade_date < $1::date
            ) t
            WHERE rn = 1
        )
        SELECT
            b.*,
            COALESCE(rs.recent_limit_up_count, 0) AS recent_limit_up_count,
            COALESCE(p7.prior7_limitup_days, 0) AS prior7_limitup_days,
            COALESCE(p7.prior7_strong_days, 0) AS prior7_strong_days,
            pd.prev_day_pct_chg,
            pd.prev_day_limit_up,
            pd.prev_day_low_price,
            pd.prev_day_close_price
        FROM watch_base b
        LEFT JOIN recent_stats rs ON split_part(rs.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        LEFT JOIN prior7_stats p7 ON split_part(p7.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        LEFT JOIN prev_day pd ON split_part(pd.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        ORDER BY b.watch_priority DESC NULLS LAST, b.watch_score DESC NULLS LAST
        """
        try:
            async with self.pool.acquire() as conn:
                latest_pool_trade_date = await conn.fetchval(
                    "SELECT MAX(last_trade_date) AS latest_trade_date FROM strong_stock_watch_pool"
                )
                source_used = "strong_stock_watch_history" if latest_pool_trade_date and trade_date < latest_pool_trade_date else "strong_stock_watch_pool"
                sql = history_sql if source_used == "strong_stock_watch_history" else current_pool_sql
                rows = await conn.fetch(sql, trade_date, int(max(1, lookback_days)))
                result = [dict(row) for row in rows]
                for row in result:
                    row["_legacy_source_used"] = source_used
                    row["_legacy_latest_pool_trade_date"] = latest_pool_trade_date
                return result
        except Exception as e:
            logger.exception("读取 legacy strong watch candidate inputs 失败 trade_date=%s lookback_days=%s", trade_date, lookback_days)
            raise RuntimeError("get_legacy_strong_watch_candidate_inputs failed") from e

    async def get_prior_strong_watch_pool_rows(
        self,
        trade_date,
        lookback_days: int,
    ) -> List[Dict[str, Any]]:
        """读取前 N 交易日 strong_stock_watch_history（弱转强输入跟踪池口径）。"""
        sql = """
        WITH w AS (
            SELECT DISTINCT trade_date
            FROM stock_daily_snapshot
            WHERE trade_date < $1::date
            ORDER BY trade_date DESC
            LIMIT $2
        ),
        h0 AS (
            SELECT
                h.trade_date,
                h.stock_id,
                h.stock_name,
                h.subject_key,
                COALESCE(h.theme_name, h.subject_key) AS subject_name,
                NULL::int AS pool_rank,
                h.watch_status,
                h.watch_score,
                COALESCE(h.pool_entry_type, '') AS pool_entry_type,
                COALESCE(h.cycle_state, '') AS final_cycle_state,
                COALESCE(h.labels_json->>'state_transition_type', '') AS transition_type_raw,
                COALESCE(h.labels_json->>'state_transition_confidence', '0')::numeric AS transition_confidence_raw,
                COALESCE(h.labels_json->'trigger_flags', '[]'::jsonb) AS trigger_flags_raw,
                COALESCE(NULLIF(h.labels_json->>'watch_age_days', ''), '1')::int AS watch_age_days,
                COALESCE(NULLIF(h.labels_json->>'weak_days', ''), '0')::int AS weak_days,
                LAG(COALESCE(h.cycle_state, '')) OVER (PARTITION BY h.stock_id ORDER BY h.trade_date) AS prev_cycle_state,
                COALESCE(h.support_type, '') AS support_type,
                h.support_level,
                h.support_score
            FROM strong_stock_watch_history h
            JOIN w ON w.trade_date = h.trade_date
        )
        SELECT
            h0.trade_date,
            h0.stock_id,
            h0.stock_name,
            h0.subject_key,
            h0.subject_name,
            h0.pool_rank,
            h0.watch_status,
            h0.watch_score,
            h0.pool_entry_type,
            h0.final_cycle_state,
            CASE
              WHEN h0.prev_cycle_state IN ('', 'unknown') THEN 'flat'
              WHEN h0.transition_type_raw <> '' THEN h0.transition_type_raw
              WHEN h0.final_cycle_state = 'fade_confirmed' THEN 'fade'
              WHEN h0.prev_cycle_state = h0.final_cycle_state THEN 'flat'
              WHEN (
                CASE h0.final_cycle_state
                  WHEN 'fade_confirmed' THEN 0
                  WHEN 'fade_watch' THEN 1
                  WHEN 'start' THEN 2
                  WHEN 'fermentation' THEN 3
                  WHEN 'divergence' THEN 4
                  WHEN 'repair' THEN 5
                  WHEN 'acceleration' THEN 6
                  ELSE -1
                END
              ) > (
                CASE h0.prev_cycle_state
                  WHEN 'fade_confirmed' THEN 0
                  WHEN 'fade_watch' THEN 1
                  WHEN 'start' THEN 2
                  WHEN 'fermentation' THEN 3
                  WHEN 'divergence' THEN 4
                  WHEN 'repair' THEN 5
                  WHEN 'acceleration' THEN 6
                  ELSE -1
                END
              ) THEN 'upgrade'
              WHEN (
                CASE h0.final_cycle_state
                  WHEN 'fade_confirmed' THEN 0
                  WHEN 'fade_watch' THEN 1
                  WHEN 'start' THEN 2
                  WHEN 'fermentation' THEN 3
                  WHEN 'divergence' THEN 4
                  WHEN 'repair' THEN 5
                  WHEN 'acceleration' THEN 6
                  ELSE -1
                END
              ) < (
                CASE h0.prev_cycle_state
                  WHEN 'fade_confirmed' THEN 0
                  WHEN 'fade_watch' THEN 1
                  WHEN 'start' THEN 2
                  WHEN 'fermentation' THEN 3
                  WHEN 'divergence' THEN 4
                  WHEN 'repair' THEN 5
                  WHEN 'acceleration' THEN 6
                  ELSE -1
                END
              ) THEN 'downgrade'
              ELSE 'flat'
            END AS transition_type,
            CASE
              WHEN h0.transition_confidence_raw > 0 THEN h0.transition_confidence_raw
              ELSE CASE
                WHEN h0.prev_cycle_state IN ('', 'unknown') THEN 0.65
                WHEN h0.prev_cycle_state = h0.final_cycle_state THEN 0.75
                ELSE 0.80
              END
            END AS transition_confidence,
            CASE
              WHEN jsonb_array_length(h0.trigger_flags_raw) > 0 THEN h0.trigger_flags_raw
              ELSE jsonb_build_array(
                CONCAT('from=', COALESCE(h0.prev_cycle_state, 'unknown')),
                CONCAT('to=', COALESCE(h0.final_cycle_state, 'unknown'))
              )
            END AS trigger_flags,
            h0.watch_age_days,
            h0.weak_days,
            h0.support_type,
            h0.support_level,
            h0.support_score
        FROM h0
        ORDER BY h0.trade_date DESC, h0.stock_id
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, trade_date, int(max(1, lookback_days)))
                return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"读取 strong_stock_watch_history 失败（可能尚未迁移）: {e}")
            return []

    async def upsert_subject_stock_daily_snapshot_rows(self, rows: List[Dict[str, Any]]) -> int:
        """批量 UPSERT subject_stock_daily_snapshot（最小字段集）。"""
        if not rows:
            return 0
        sql = """
        INSERT INTO subject_stock_daily_snapshot (
            trade_date, subject_key, subject_name, stock_id, stock_name,
            rank_order, close_price, pct_chg, limit_up, is_leader
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10
        )
        ON CONFLICT (trade_date, subject_key, stock_id) DO UPDATE SET
          subject_name = EXCLUDED.subject_name,
          stock_name = EXCLUDED.stock_name,
          rank_order = EXCLUDED.rank_order,
          close_price = EXCLUDED.close_price,
          pct_chg = EXCLUDED.pct_chg,
          limit_up = EXCLUDED.limit_up,
          is_leader = EXCLUDED.is_leader
        """
        payload = [
            (
                date.fromisoformat(row.get("trade_date")) if isinstance(row.get("trade_date"), str) else row.get("trade_date"),
                row.get("subject_key"),
                row.get("subject_name"),
                row.get("stock_id"),
                row.get("stock_name"),
                row.get("rank_order"),
                row.get("close_price"),
                row.get("pct_chg"),
                row.get("limit_up"),
                row.get("is_leader"),
            )
            for row in rows
        ]
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(sql, payload)
            return len(payload)
        except Exception as e:
            logger.warning(f"写入 subject_stock_daily_snapshot 失败（可能尚未迁移）: {e}")
            return 0

    async def upsert_stock_abnormal_event_rows(self, rows: List[Dict[str, Any]]) -> int:
        """批量 UPSERT stock_abnormal_event（对象层）。"""
        if not rows:
            return 0
        sql = """
        INSERT INTO stock_abnormal_event (
            trade_date, stock_id, event_type, event_score, evidence_rules, raw_metrics
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
        ON CONFLICT (trade_date, stock_id, event_type) DO UPDATE SET
          event_score = EXCLUDED.event_score,
          evidence_rules = EXCLUDED.evidence_rules,
          raw_metrics = EXCLUDED.raw_metrics
        """
        payload = [
            (
                row.get("trade_date"),
                row.get("stock_id"),
                row.get("event_type"),
                row.get("event_score"),
                _safe_json_dumps(row.get("evidence_rules"), []),
                _safe_json_dumps(row.get("raw_metrics"), {}),
            )
            for row in rows
        ]
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(sql, payload)
            return len(payload)
        except Exception as e:
            logger.warning(f"写入 stock_abnormal_event 失败（可能尚未迁移）: {e}")
            return 0

    async def upsert_theme_stock_leaderboard_rows(self, rows: List[Dict[str, Any]]) -> int:
        """批量 UPSERT theme_stock_leaderboard（对象层）。"""
        if not rows:
            return 0
        sql = """
        INSERT INTO theme_stock_leaderboard (
            trade_date, subject_key, stock_id, leaderboard_rank, leader_score, score_breakdown
        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        ON CONFLICT (trade_date, subject_key, stock_id) DO UPDATE SET
          leaderboard_rank = EXCLUDED.leaderboard_rank,
          leader_score = EXCLUDED.leader_score,
          score_breakdown = EXCLUDED.score_breakdown
        """
        payload = [
            (
                row.get("trade_date"),
                row.get("subject_key"),
                row.get("stock_id"),
                row.get("leaderboard_rank"),
                row.get("leader_score"),
                _safe_json_dumps(row.get("score_breakdown"), {}),
            )
            for row in rows
        ]
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(sql, payload)
            return len(payload)
        except Exception as e:
            logger.warning(f"写入 theme_stock_leaderboard 失败（可能尚未迁移）: {e}")
            return 0

    async def upsert_pre_market_brief_snapshot(self, doc: Dict[str, Any]) -> int:
        """UPSERT pre_market_brief_snapshot 文档对象。"""
        sql = """
        INSERT INTO pre_market_brief_snapshot (
            trade_date, snapshot_version, batch_id, trace_id, payload, source_name
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        ON CONFLICT (trade_date) DO UPDATE SET
          snapshot_version = EXCLUDED.snapshot_version,
          batch_id = EXCLUDED.batch_id,
          trace_id = EXCLUDED.trace_id,
          payload = EXCLUDED.payload || pre_market_brief_snapshot.payload,
          source_name = EXCLUDED.source_name,
          updated_at = NOW()
        """
        payload = (
            doc.get("trade_date"),
            doc.get("snapshot_version"),
            doc.get("batch_id"),
            doc.get("trace_id"),
            json.dumps(doc.get("payload") or {}, ensure_ascii=False, default=str),
            str(doc.get("source_name") or "stock_processing_service"),
        )
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, *payload)
            return 1
        except Exception as e:
            logger.warning(f"写入 pre_market_brief_snapshot 失败（可能尚未迁移）: {e}")
            return 0

    async def upsert_post_market_recap_snapshot(self, doc: Dict[str, Any]) -> int:
        """UPSERT post_market_recap_snapshot 文档对象。"""
        sql = """
        INSERT INTO post_market_recap_snapshot (
            trade_date, snapshot_version, batch_id, trace_id, payload, source_name
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        ON CONFLICT (trade_date) DO UPDATE SET
          snapshot_version = EXCLUDED.snapshot_version,
          batch_id = EXCLUDED.batch_id,
          trace_id = EXCLUDED.trace_id,
          payload = EXCLUDED.payload || post_market_recap_snapshot.payload,
          source_name = EXCLUDED.source_name,
          updated_at = NOW()
        """
        payload = (
            doc.get("trade_date"),
            doc.get("snapshot_version"),
            doc.get("batch_id"),
            doc.get("trace_id"),
            json.dumps(doc.get("payload") or {}, ensure_ascii=False, default=str),
            str(doc.get("source_name") or "stock_processing_service"),
        )
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, *payload)
            return 1
        except Exception as e:
            logger.warning(f"写入 post_market_recap_snapshot 失败（可能尚未迁移）: {e}")
            return 0

    async def upsert_strong_watch_pool_rows(self, rows: list[dict[str, Any]]) -> int:
        """UPSERT strong_stock_watch_pool — 等价于旧链 _upsert_watch_pool_seed + _update_watch_pool_row。

        新链 Layer C 独立维护持久池，不再依赖旧链 strong_stock_watch_pool 表。
        """
        sql = """
        INSERT INTO strong_stock_watch_pool (
            stock_id, stock_name, subject_key, theme_name,
            watch_start_date, last_trade_date, watch_window_days,
            source_tag, relay_role, watch_status,
            watch_priority, watch_score,
            pool_entry_type, candidate_promoted,
            cycle_state, mainline_strength_score,
            fade_watch, fade_confirmed,
            support_type, support_level, support_score,
            labels_json, evidence_json,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4,
            $5::date, $6::date, $7,
            $8, $9, $10,
            $11::numeric, $12::numeric,
            $13, FALSE,
            $14, $15::numeric,
            $16, $17,
            $18, $19::numeric, $20::numeric,
            $21::jsonb, $22::jsonb,
            now(), now()
        )
        ON CONFLICT (stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            last_trade_date = EXCLUDED.last_trade_date,
            watch_window_days = GREATEST(strong_stock_watch_pool.watch_window_days, 1),
            source_tag = EXCLUDED.source_tag,
            relay_role = EXCLUDED.relay_role,
            watch_status = EXCLUDED.watch_status,
            watch_priority = EXCLUDED.watch_priority,
            watch_score = EXCLUDED.watch_score,
            pool_entry_type = EXCLUDED.pool_entry_type,
            cycle_state = EXCLUDED.cycle_state,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_watch = EXCLUDED.fade_watch,
            fade_confirmed = EXCLUDED.fade_confirmed,
            support_type = EXCLUDED.support_type,
            support_level = EXCLUDED.support_level,
            support_score = EXCLUDED.support_score,
            labels_json = EXCLUDED.labels_json,
            evidence_json = EXCLUDED.evidence_json,
            updated_at = now()
        """
        payload = []
        for row in rows:
            trade_date = row.get("trade_date")
            if isinstance(trade_date, str):
                trade_date_val = date.fromisoformat(trade_date)
            elif isinstance(trade_date, date):
                trade_date_val = trade_date
            else:
                trade_date_val = None
            if not trade_date_val or not row.get("stock_id"):
                continue
            payload.append((
                str(row.get("stock_id") or ""),
                str(row.get("stock_name") or ""),
                str(row.get("subject_key") or ""),
                str(row.get("theme_name") or ""),
                trade_date_val,
                trade_date_val,
                1,  # watch_window_days (initial)
                str(row.get("source_tag") or ""),
                str(row.get("relay_role") or "unknown"),
                str(row.get("watch_status") or "pending_seed"),
                str(row.get("watch_priority") or "0"),
                str(row.get("watch_score") or "0"),
                str(row.get("pool_entry_type") or "observe_only"),
                str(row.get("cycle_state") or ""),
                str(row.get("mainline_strength_score") or "0"),
                bool(row.get("fade_watch") or False),
                bool(row.get("fade_confirmed") or False),
                row.get("support_type"),
                str(row.get("support_level") or "0"),
                str(row.get("support_score") or "0"),
                _safe_json_dumps(row.get("labels"), {}),
                _safe_json_dumps(row.get("evidence"), {}),
            ))
        if not payload:
            return 0
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(sql, payload)
            return len(payload)
        except Exception as e:
            logger.warning(f"写入 strong_stock_watch_pool 失败: {e}")
            return 0

    async def get_auction_watch_universe(self, trade_date) -> list[dict[str, Any]]:
        """读取竞价观察池（auction_watch_universe 表）。"""
        sql = """
        SELECT stock_id, stock_name, subject_key, theme_name, role_label,
               mainline_alive, primary_cycle_stage, action_bias, is_reversal_watch
        FROM auction_watch_universe
        WHERE trade_date = $1::date
        ORDER BY candidate_priority, theme_name, candidate_rank, stock_id
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def get_w2s_candidates_by_next_date(self, confirm_date) -> list[dict[str, Any]]:
        """读取弱转强候选池（按确认日筛选）。"""
        sql = """
        SELECT stock_id, stock_name, subject_key, theme_name, candidate_type, candidate_score
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
        ORDER BY candidate_score DESC, id ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, confirm_date)
        return [dict(r) for r in rows]

    async def upsert_pre_market_auction_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        """批量 UPSERT pre_market_auction_snapshot 表。"""
        if not rows:
            return 0
        sql = """
        INSERT INTO pre_market_auction_snapshot (
            trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
            window_start_time, window_end_time, last_minute_start_time, last_30s_start_time,
            auction_open_price, pre_close, auction_open_pct, auction_volume, auction_amount,
            last_minute_amount, last_minute_ratio, prev_day_max_intraday_amount, carry_ratio,
            price_path_stability_score, is_red_zone, has_end_spike, has_end_drop,
            shape_features, source_type, source_trace_id, source_trace, source_version, rule_version
        ) VALUES (
            $1::date, $2, $3, $4, $5, $6,
            $7, $8, $9, $10,
            $11::numeric, $12::numeric, $13::numeric, $14::numeric, $15::numeric,
            $16::numeric, $17::numeric, $18::numeric, $19::numeric,
            $20::numeric, $21, $22, $23,
            $24::jsonb, $25, $26, $27::jsonb, $28, $29
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name, subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name, role_label = EXCLUDED.role_label,
            auction_open_price = EXCLUDED.auction_open_price, pre_close = EXCLUDED.pre_close,
            auction_open_pct = EXCLUDED.auction_open_pct, auction_volume = EXCLUDED.auction_volume,
            auction_amount = EXCLUDED.auction_amount, last_minute_amount = EXCLUDED.last_minute_amount,
            last_minute_ratio = EXCLUDED.last_minute_ratio, carry_ratio = EXCLUDED.carry_ratio,
            price_path_stability_score = EXCLUDED.price_path_stability_score,
            is_red_zone = EXCLUDED.is_red_zone, has_end_spike = EXCLUDED.has_end_spike,
            has_end_drop = EXCLUDED.has_end_drop, shape_features = EXCLUDED.shape_features,
            source_trace_id = EXCLUDED.source_trace_id, source_trace = EXCLUDED.source_trace,
            updated_at = NOW()
        """
        payload = []
        for row in rows:
            payload.append((
                row.get("trade_date"), str(row.get("stock_id", "")), str(row.get("stock_name", "")),
                str(row.get("subject_key", "")), str(row.get("theme_name", "")), str(row.get("role_label", "")),
                str(row.get("window_start_time", "09:20:00")), str(row.get("window_end_time", "09:25:00")),
                str(row.get("last_minute_start_time", "09:24:00")), str(row.get("last_30s_start_time", "09:24:30")),
                str(row.get("auction_open_price", 0)), str(row.get("pre_close", 0)),
                str(row.get("auction_open_pct", 0)), str(row.get("auction_volume", 0)),
                str(row.get("auction_amount", 0)), str(row.get("last_minute_amount", 0)),
                str(row.get("last_minute_ratio", 0)), str(row.get("prev_day_max_intraday_amount", 0)),
                str(row.get("carry_ratio", 0)), str(row.get("price_path_stability_score", 0)),
                bool(row.get("is_red_zone", False)), bool(row.get("has_end_spike", False)),
                bool(row.get("has_end_drop", False)), _safe_json_dumps(row.get("shape_features"), []),
                str(row.get("source_type", "")), str(row.get("source_trace_id", "")),
                _safe_json_dumps(row.get("source_trace"), {}),
                str(row.get("source_version", "")), str(row.get("rule_version", "")),
            ))
        async with self.pool.acquire() as conn:
            await conn.executemany(sql, payload)
        return len(payload)

    async def get_auction_board_leaders(self, trade_date) -> list[dict[str, Any]]:
        """读取 auction 竞价观察池所需的龙头候选数据。"""
        sql = """
        SELECT subject_key, stock_id, stock_name, role_label, candidate_rank
        FROM theme_leader_candidate
        WHERE trade_date = $1::date
          AND role_label IN ('龙头', '龙二', '卡位', '强趋势')
        ORDER BY subject_key, candidate_rank ASC, composite_score DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def get_auction_mainlines(self, trade_date) -> list[dict[str, Any]]:
        """读取 auction 所需的主线存活状态。"""
        sql = """
        SELECT
            v2.subject_key,
            COALESCE(NULLIF(v2.theme_name, ''), v2.subject_key) AS theme_name,
            COALESCE(v2.final_mainline_alive, FALSE) AS mainline_alive,
            COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
            COALESCE(v2.mainline_strength_score, 0) AS mainline_strength_score,
            COALESCE(v2.fade_watch, FALSE) AS fade_watch,
            COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed
        FROM theme_cycle_judgement_v2 v2
        WHERE v2.trade_date = $1::date
          AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def get_auction_cycles(self, trade_date) -> list[dict[str, Any]]:
        """读取 auction 所需的周期状态与操作偏向。"""
        sql = """
        SELECT
            v2.subject_key,
            COALESCE(NULLIF(v2.final_cycle_state, ''), 'fade') AS primary_cycle_stage,
            CASE
                WHEN COALESCE(v2.fade_confirmed, FALSE) THEN '观望'
                WHEN COALESCE(v2.final_cycle_state, '') IN ('climax', '高潮') THEN '警惕高潮'
                WHEN COALESCE(v2.final_cycle_state, '') IN ('fermentation', '发酵', 'start', '启动') THEN '可主做'
                WHEN COALESCE(v2.final_cycle_state, '') IN ('repair', '修复', 'divergence', '分歧', 'rebound', '回流') THEN '可做弱转强'
                ELSE '可观察'
            END AS action_bias
        FROM theme_cycle_judgement_v2 v2
        WHERE v2.trade_date = $1::date
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return [dict(r) for r in rows]

    async def upsert_auction_watch_universe_rows(self, rows: list[dict[str, Any]]) -> int:
        """批量 UPSERT auction_watch_universe 表。"""
        if not rows:
            return 0
        sql = """
        INSERT INTO auction_watch_universe (
            source_trade_date, trade_date, stock_id, stock_name, subject_key, theme_name,
            theme_tier, mainline_alive, primary_cycle_stage, action_bias, role_label, candidate_rank,
            candidate_priority, is_reversal_watch, source_type, source_trace_id, source_trace,
            source_version, rule_version
        ) VALUES (
            $1::date, $2::date, $3, $4, $5, $6,
            $7, $8, $9, $10, $11, $12,
            $13, $14, $15, $16, $17::jsonb,
            $18, $19
        )
        ON CONFLICT (trade_date, stock_id, subject_key) DO UPDATE SET
            source_trade_date = EXCLUDED.source_trade_date,
            stock_name = EXCLUDED.stock_name,
            theme_name = EXCLUDED.theme_name,
            theme_tier = EXCLUDED.theme_tier,
            mainline_alive = EXCLUDED.mainline_alive,
            primary_cycle_stage = EXCLUDED.primary_cycle_stage,
            action_bias = EXCLUDED.action_bias,
            role_label = EXCLUDED.role_label,
            candidate_rank = EXCLUDED.candidate_rank,
            candidate_priority = EXCLUDED.candidate_priority,
            is_reversal_watch = EXCLUDED.is_reversal_watch,
            source_type = EXCLUDED.source_type,
            source_trace_id = EXCLUDED.source_trace_id,
            source_trace = EXCLUDED.source_trace,
            source_version = EXCLUDED.source_version,
            rule_version = EXCLUDED.rule_version,
            updated_at = NOW()
        """
        payload = []
        for row in rows:
            payload.append((
                row.get("source_trade_date"),
                row.get("trade_date"),
                row.get("stock_id", ""),
                row.get("stock_name", ""),
                row.get("subject_key", ""),
                row.get("theme_name", ""),
                row.get("theme_tier", ""),
                row.get("mainline_alive", False),
                row.get("primary_cycle_stage", ""),
                row.get("action_bias", ""),
                row.get("role_label", ""),
                row.get("candidate_rank", 0),
                row.get("candidate_priority", ""),
                row.get("is_reversal_watch", False),
                row.get("source_type", ""),
                row.get("source_trace_id", ""),
                _safe_json_dumps(row.get("source_trace"), {}),
                row.get("source_version", ""),
                row.get("rule_version", ""),
            ))
        async with self.pool.acquire() as conn:
            await conn.executemany(sql, payload)
        return len(payload)

    async def upsert_dragon_tiger_object_rows(self, rows: list[dict[str, Any]]) -> int:
        """批量 UPSERT dragon_tiger_object 表。"""
        if not rows:
            return 0
        sql = """
        INSERT INTO dragon_tiger_object (
            trade_date, stock_id, stock_name, reason,
            close_price, pct_change, turnover_rate, total_amount,
            billboard_buy_amount, billboard_sell_amount, billboard_amount, net_amount,
            net_rate, amount_rate, float_market_value,
            institution_buy_amount, institution_sell_amount, institution_net_buy, institution_seat_count,
            seat_summary, source_trace_id, source_trace, source_version, rule_version
        ) VALUES (
            $1::date, $2, $3, $4,
            $5::numeric, $6::numeric, $7::numeric, $8::numeric,
            $9::numeric, $10::numeric, $11::numeric, $12::numeric,
            $13::numeric, $14::numeric, $15::numeric,
            $16::numeric, $17::numeric, $18::numeric, $19,
            $20::jsonb, $21, $22::jsonb, $23, $24
        )
        ON CONFLICT (trade_date, stock_id, reason) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            close_price = EXCLUDED.close_price,
            pct_change = EXCLUDED.pct_change,
            turnover_rate = EXCLUDED.turnover_rate,
            total_amount = EXCLUDED.total_amount,
            billboard_buy_amount = EXCLUDED.billboard_buy_amount,
            billboard_sell_amount = EXCLUDED.billboard_sell_amount,
            billboard_amount = EXCLUDED.billboard_amount,
            net_amount = EXCLUDED.net_amount,
            net_rate = EXCLUDED.net_rate,
            amount_rate = EXCLUDED.amount_rate,
            float_market_value = EXCLUDED.float_market_value,
            institution_buy_amount = EXCLUDED.institution_buy_amount,
            institution_sell_amount = EXCLUDED.institution_sell_amount,
            institution_net_buy = EXCLUDED.institution_net_buy,
            institution_seat_count = EXCLUDED.institution_seat_count,
            seat_summary = EXCLUDED.seat_summary,
            source_trace_id = EXCLUDED.source_trace_id,
            source_trace = EXCLUDED.source_trace,
            source_version = EXCLUDED.source_version,
            rule_version = EXCLUDED.rule_version,
            updated_at = NOW()
        """
        payload = []
        for row in rows:
            payload.append((
                row.get("trade_date"),
                row.get("stock_id", ""),
                row.get("stock_name", ""),
                row.get("reason", ""),
                str(row.get("close_price", 0)),
                str(row.get("pct_change", 0)),
                str(row.get("turnover_rate", 0)),
                str(row.get("total_amount", 0)),
                str(row.get("billboard_buy_amount", 0)),
                str(row.get("billboard_sell_amount", 0)),
                str(row.get("billboard_amount", 0)),
                str(row.get("net_amount", 0)),
                str(row.get("net_rate", 0)),
                str(row.get("amount_rate", 0)),
                str(row.get("float_market_value", 0)),
                str(row.get("institution_buy_amount", 0)),
                str(row.get("institution_sell_amount", 0)),
                str(row.get("institution_net_buy", 0)),
                row.get("institution_seat_count", 0),
                _safe_json_dumps(row.get("seat_summary"), []),
                str(row.get("source_trace_id", "")),
                _safe_json_dumps(row.get("source_trace"), {}),
                str(row.get("source_version", "")),
                str(row.get("rule_version", "")),
            ))
        async with self.pool.acquire() as conn:
            await conn.executemany(sql, payload)
        return len(payload)

    async def promote_strong_watch_candidates(self, trade_date) -> int:
        """标记 candidate_promoted=TRUE — 等价旧链 promote_watch_candidates()。"""
        sql = """
        UPDATE strong_stock_watch_pool
        SET candidate_promoted = TRUE,
            updated_at = NOW()
        WHERE watch_status IN ('active', 'weakening')
          AND pool_entry_type IN ('formal', 'observe_only')
          AND COALESCE(fade_confirmed, FALSE) = FALSE
          AND candidate_promoted = FALSE
          AND last_trade_date <= $1::date
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(sql, trade_date)
                count = int(result.split()[-1]) if result else 0
                if count > 0:
                    logger.info(f"promote_strong_watch_candidates: {count} candidates promoted on {trade_date}")
                return count
        except Exception as e:
            logger.warning(f"promote_strong_watch_candidates 失败 trade_date={trade_date}: {e}")
            return 0

    async def prune_strong_watch_pool(self, trade_date, weakening_min_score: float = 62.0) -> int:
        """清理已失效观察对象 — 等价旧链 prune_watch_pool() + 写 history。

        严格复刻旧链：
        1. _resolve_cutoff_trade_date(trade_date, lookback_trade_days=3)
        2. UPDATE WHERE last_trade_date <= cutoff_trade_date
        3. 查询本次 removed 对象，写 history（用原始 trade_date）
        4. fail-fast 异常
        """
        # 旧链 _resolve_cutoff_trade_date: 向前 3 个交易日
        cutoff_sql = """
        SELECT x.trade_date
        FROM (
            SELECT DISTINCT s.trade_date
            FROM subject_stock_daily_snapshot s
            WHERE s.trade_date <= $1::date
            ORDER BY s.trade_date DESC
            LIMIT 4
        ) x
        ORDER BY x.trade_date ASC
        LIMIT 1
        """

        prune_sql = """
        UPDATE strong_stock_watch_pool
        SET watch_status = 'removed',
            pool_entry_type = 'reject',
            updated_at = NOW()
        WHERE (
                COALESCE(fade_confirmed, FALSE) = TRUE
             OR (
                    watch_status = 'weakening'
                AND watch_score < $2
                AND last_trade_date <= $1::date
             )
        )
          AND watch_status <> 'removed'
        """

        history_sql = """
        INSERT INTO strong_stock_watch_history (
            trade_date, stock_id, stock_name, subject_key, theme_name,
            watch_status, watch_score, watch_priority,
            relay_role, pool_entry_type, cycle_state, mainline_strength_score,
            fade_watch, fade_confirmed,
            promoted_to_candidate, removed_reason,
            support_type, support_level, support_score,
            labels_json, evidence_json,
            created_at
        )
        SELECT
            $1::date,
            p.stock_id, p.stock_name, p.subject_key, p.theme_name,
            p.watch_status, p.watch_score, p.watch_priority,
            p.relay_role, p.pool_entry_type, p.cycle_state, p.mainline_strength_score,
            p.fade_watch, p.fade_confirmed,
            p.candidate_promoted,
            CASE
              WHEN COALESCE(p.fade_confirmed, FALSE) THEN 'fade_confirmed'
              WHEN p.watch_status = 'removed' AND p.pool_entry_type = 'reject'
                THEN 'weakening_score_below_cutoff'
              ELSE NULL
            END,
            p.support_type, p.support_level, p.support_score,
            p.labels_json, p.evidence_json,
            NOW()
        FROM strong_stock_watch_pool p
        WHERE p.watch_status = 'removed'
          AND p.pool_entry_type = 'reject'
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            watch_status = EXCLUDED.watch_status,
            watch_score = EXCLUDED.watch_score,
            pool_entry_type = EXCLUDED.pool_entry_type,
            removed_reason = EXCLUDED.removed_reason,
            updated_at = NOW()
        """

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                cutoff_row = await conn.fetchrow(cutoff_sql, trade_date)
                cutoff_trade_date = cutoff_row["trade_date"] if cutoff_row else trade_date

                result = await conn.execute(prune_sql, cutoff_trade_date, weakening_min_score)
                count = int(result.split()[-1]) if result else 0

                if count > 0:
                    await conn.execute(history_sql, trade_date)

                logger.info(
                    "prune_strong_watch_pool: %s stocks removed + history written on %s (cutoff=%s)",
                    count, trade_date, cutoff_trade_date,
                )
                return count

    async def upsert_strong_watch_history_rows(self, rows: List[Dict[str, Any]]) -> int:
        """批量 UPSERT strong_stock_watch_history（Layer C 跟踪池历史真源）。"""
        if not rows:
            return 0
        sql = """
        INSERT INTO strong_stock_watch_history (
            trade_date,
            stock_id,
            stock_name,
            subject_key,
            theme_name,
            watch_status,
            watch_score,
            watch_priority,
            relay_role,
            pool_entry_type,
            cycle_state,
            mainline_strength_score,
            fade_watch,
            fade_confirmed,
            promoted_to_candidate,
            removed_reason,
            support_type,
            support_level,
            support_score,
            labels_json,
            evidence_json
        ) VALUES (
            $1::date, $2, $3, $4, $5, $6, $7::numeric, $8::numeric, $9, $10, $11, $12::numeric,
            $13::boolean, $14::boolean, $15::boolean, $16, $17, $18::numeric, $19::numeric,
            $20::jsonb, $21::jsonb
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            watch_status = EXCLUDED.watch_status,
            watch_score = EXCLUDED.watch_score,
            watch_priority = EXCLUDED.watch_priority,
            relay_role = EXCLUDED.relay_role,
            pool_entry_type = EXCLUDED.pool_entry_type,
            cycle_state = EXCLUDED.cycle_state,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_watch = EXCLUDED.fade_watch,
            fade_confirmed = EXCLUDED.fade_confirmed,
            promoted_to_candidate = EXCLUDED.promoted_to_candidate,
            removed_reason = EXCLUDED.removed_reason,
            support_type = EXCLUDED.support_type,
            support_level = EXCLUDED.support_level,
            support_score = EXCLUDED.support_score,
            labels_json = EXCLUDED.labels_json,
            evidence_json = EXCLUDED.evidence_json
        """
        payload = [
            (
                date.fromisoformat(row.get("trade_date")) if isinstance(row.get("trade_date"), str) else row.get("trade_date"),
                row.get("stock_id"),
                row.get("stock_name") or row.get("stock_id"),
                row.get("subject_key"),
                row.get("theme_name") or row.get("subject_key"),
                row.get("watch_status") or "active",
                row.get("watch_score") or "0",
                row.get("watch_priority") or row.get("watch_score") or "0",
                row.get("relay_role") or "unknown",
                row.get("pool_entry_type") or "observe_only",
                row.get("cycle_state") or "",
                row.get("mainline_strength_score") or "0",
                bool(row.get("fade_watch") or False),
                bool(row.get("fade_confirmed") or False),
                bool(row.get("promoted_to_candidate") or False),
                row.get("removed_reason"),
                row.get("support_type") or "",
                row.get("support_level") or "0",
                row.get("support_score") or "0",
                _safe_json_dumps(row.get("labels_json"), {}),
                _safe_json_dumps(row.get("evidence_json"), {}),
            )
            for row in rows
            if row.get("trade_date") and row.get("stock_id")
        ]
        if not payload:
            return 0
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany(sql, payload)
            return len(payload)
        except Exception as e:
            logger.warning(f"写入 strong_stock_watch_history 失败（可能尚未迁移）: {e}")
            return 0

    async def upsert_theme_mainline_identity_registry_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        allow_historical_overwrite: bool = False,
        allow_unsafe_demotion: bool = False,
    ) -> int:
        """写入 theme_mainline_identity_registry 表（Layer A 身份注册表）。

        含旧链等价写入保护：
        1. first_confirmed_date：仅首次确认时写入，永不覆盖
        2. 历史覆盖保护：不允许旧数据覆盖新数据（除非 allow_historical_overwrite=True）
        3. 降级保护：不允许非LLM路径将 confirmed 降级（除非 allow_unsafe_demotion=True）
        4. rule_version：追溯确认来源（manual_override/cluster_bootstrap/cluster_comp/llm/rule）
        """
        sql = """
        INSERT INTO theme_mainline_identity_registry (
            subject_key, theme_name, is_main_theme, identity_status,
            first_seen_date, first_confirmed_date, last_review_date, source_trade_date,
            logic_score, market_score, composite_score, evidence_json,
            rule_is_main_theme, llm_applied, llm_is_main_theme, llm_confidence,
            llm_reasons, llm_risk_flags, llm_model, llm_reviewed_at, rule_version
        ) VALUES (
            $1, $2, $3, $4,
            $5::date, $6::date, $7::date, $8::date,
            $9::numeric, $10::numeric, $11::numeric, $12::jsonb,
            $13, $14, $15, $16,
            $17::jsonb, $18::jsonb, $19, $20, $21
        )
        ON CONFLICT (subject_key) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            is_main_theme = EXCLUDED.is_main_theme,
            identity_status = EXCLUDED.identity_status,
            first_confirmed_date = CASE
                WHEN theme_mainline_identity_registry.first_confirmed_date IS NULL AND EXCLUDED.is_main_theme
                THEN EXCLUDED.first_confirmed_date
                ELSE theme_mainline_identity_registry.first_confirmed_date
            END,
            last_review_date = EXCLUDED.last_review_date,
            source_trade_date = EXCLUDED.source_trade_date,
            logic_score = EXCLUDED.logic_score,
            market_score = EXCLUDED.market_score,
            composite_score = EXCLUDED.composite_score,
            evidence_json = EXCLUDED.evidence_json,
            rule_is_main_theme = EXCLUDED.rule_is_main_theme,
            llm_applied = EXCLUDED.llm_applied,
            llm_is_main_theme = EXCLUDED.llm_is_main_theme,
            llm_confidence = EXCLUDED.llm_confidence,
            llm_reasons = EXCLUDED.llm_reasons,
            llm_risk_flags = EXCLUDED.llm_risk_flags,
            llm_model = EXCLUDED.llm_model,
            llm_reviewed_at = EXCLUDED.llm_reviewed_at,
            rule_version = EXCLUDED.rule_version,
            updated_at = NOW()
        WHERE (
            -- Guard 1: 不允许旧数据覆盖新数据
            EXCLUDED.last_review_date >= COALESCE(
                theme_mainline_identity_registry.last_review_date, DATE '1900-01-01'
            )
            OR $22::boolean = TRUE
        )
          AND (
            -- Guard 2: 不允许非LLM路径静默降级 confirmed → observed/inactive
            $23::boolean = TRUE
            OR NOT (
                COALESCE(theme_mainline_identity_registry.is_main_theme, FALSE) = TRUE
                AND COALESCE(NULLIF(LOWER(theme_mainline_identity_registry.identity_status), ''), 'observed') = 'confirmed'
                AND COALESCE(EXCLUDED.is_main_theme, FALSE) = FALSE
                AND COALESCE(EXCLUDED.llm_applied, FALSE) = FALSE
            )
        )
        """
        payload = []
        for row in rows:
            if not row.get("subject_key"):
                continue
            trade_date = row.get("trade_date")
            if isinstance(trade_date, str):
                trade_date_val = date.fromisoformat(trade_date)
            else:
                trade_date_val = trade_date
            identity_status = str(row.get("identity_status") or "observed")
            is_main_theme = identity_status == "confirmed"
            first_confirmed_date_val = trade_date_val if is_main_theme else None
            evidence = {
                "trade_date": str(row.get("trade_date") or ""),
                "subject_key": str(row.get("subject_key") or ""),
                "subject_name": str(row.get("subject_name") or ""),
                "logic_score": str(row.get("logic_score") or "0"),
                "market_score": str(row.get("market_score") or "0"),
                "composite_score": str(row.get("composite_score") or "0"),
                "legacy_composite_score": str(row.get("legacy_composite_score") or "0"),
                "one_day_tour_flag": bool(row.get("one_day_tour_flag") or False),
                "continuity_signal": str(row.get("continuity_signal") or ""),
                "logic_ok": bool(row.get("logic_ok") or False),
                "market_ok": bool(row.get("market_ok") or False),
                "rule_is_main_theme": bool(row.get("rule_is_main_theme") or False),
                "rule_reasons": list(row.get("rule_reasons") or []),
                "identity_status": identity_status,
                "cluster_comp_count": int(row.get("cluster_comp_count") or 0),
                "cluster_bootstrap_count": int(row.get("cluster_bootstrap_count") or 0),
                "llm_verdict": str(row.get("llm_verdict") or ""),
                "llm_reason": str(row.get("llm_reason") or ""),
                "snapshot_version": str(row.get("snapshot_version") or ""),
                "batch_id": str(row.get("batch_id") or ""),
                "trace_id": str(row.get("trace_id") or ""),
            }
            # rule_version 溯源：根据确认来源写入不同的规则版本
            rule_version = str(row.get("rule_version") or "")
            if not rule_version:
                rule_version = str(row.get("snapshot_version") or "mainline_identity_registry.v7")
            payload.append((
                str(row.get("subject_key") or ""),
                str(row.get("subject_name") or row.get("subject_key") or ""),
                is_main_theme,
                identity_status,
                trade_date_val,
                first_confirmed_date_val,
                trade_date_val,
                trade_date_val,
                str(row.get("logic_score") or "0"),
                str(row.get("market_score") or "0"),
                str(row.get("composite_score") or "0"),
                _safe_json_dumps(evidence, {}),
                bool(row.get("rule_is_main_theme") or False),
                bool(row.get("llm_applied") or False),
                bool(row.get("llm_is_main_theme")) if row.get("llm_is_main_theme") is not None else None,
                int(row.get("llm_confidence") or 0) if row.get("llm_confidence") is not None else None,
                _safe_json_dumps(row.get("llm_reasons"), []),
                _safe_json_dumps(row.get("llm_risk_flags"), []),
                str(row.get("llm_model") or ""),
                None,   # llm_reviewed_at
                rule_version,
                bool(allow_historical_overwrite),  # $22
                bool(allow_unsafe_demotion),       # $23
            ))
        if not payload:
            return 0
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("BEGIN")
                try:
                    await conn.executemany(sql, payload)
                    await conn.execute("COMMIT")
                except Exception:
                    await conn.execute("ROLLBACK")
                    raise
            return len(payload)
        except Exception as e:
            logger.warning(f"写入 theme_mainline_identity_registry 失败（可能表尚未迁移）: {e}")
            return 0



    async def upsert_mainline_identity_review_queue_rows(self, rows: list[dict[str, Any]]) -> int:
        """写入 mainline_identity_review_queue 表（Layer A 身份复核队列）。"""
        sql = """
        INSERT INTO mainline_identity_review_queue (
            trade_date, subject_key, theme_name,
            review_source, review_status, priority_score,
            trigger_flags, evidence_json
        ) VALUES (
            $1::date, $2, $3,
            $4, $5, $6::numeric,
            $7::jsonb, $8::jsonb
        )
        ON CONFLICT (trade_date, subject_key, review_source) DO UPDATE
        SET
            theme_name = EXCLUDED.theme_name,
            review_status = EXCLUDED.review_status,
            priority_score = EXCLUDED.priority_score,
            trigger_flags = EXCLUDED.trigger_flags,
            evidence_json = EXCLUDED.evidence_json,
            reviewed_at = CASE
                WHEN EXCLUDED.review_status = 'pending' THEN NULL
                ELSE mainline_identity_review_queue.reviewed_at
            END
        """
        payload = []
        for row in rows:
            if not row.get("subject_key") or not row.get("trade_date"):
                continue
            trade_date = row.get("trade_date")
            if isinstance(trade_date, str):
                trade_date_val = date.fromisoformat(trade_date)
            else:
                trade_date_val = trade_date
            trigger_flags = list(row.get("rule_reasons") or [])
            evidence = {
                "trade_date": str(row.get("trade_date") or ""),
                "subject_key": str(row.get("subject_key") or ""),
                "subject_name": str(row.get("subject_name") or ""),
                "reason": str(row.get("reason") or ""),
                "llm_confidence": str(row.get("llm_confidence") or "0"),
                "llm_verdict": str(row.get("llm_verdict") or ""),
                "rule_is_main_theme": bool(row.get("rule_is_main_theme") or False),
                "rule_reasons": list(row.get("rule_reasons") or []),
                "snapshot_version": str(row.get("snapshot_version") or ""),
                "batch_id": str(row.get("batch_id") or ""),
                "trace_id": str(row.get("trace_id") or ""),
            }
            priority_score = str(row.get("llm_confidence") or "0")
            payload.append((
                trade_date_val,
                str(row.get("subject_key") or ""),
                str(row.get("subject_name") or row.get("subject_key") or ""),
                "build_identity",
                "pending",
                priority_score,
                _safe_json_dumps(trigger_flags, []),
                _safe_json_dumps(evidence, {}),
            ))
        if not payload:
            return 0
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("BEGIN")
                try:
                    await conn.executemany(sql, payload)
                    await conn.execute("COMMIT")
                except Exception:
                    await conn.execute("ROLLBACK")
                    raise
            return len(payload)
        except Exception as e:
            logger.warning(f"写入 mainline_identity_review_queue 失败（可能表尚未迁移）: {e}")
            return 0

    async def apply_lifecycle_downgrade(
        self, trade_date, deactivate_fade_days: int = 2
    ) -> int:
        """生命周期降级：连续 fade_confirmed → is_main_theme=FALSE, identity_status='inactive'。

        等价于旧链 _apply_lifecycle_downgrade (L2005-2059)。
        """
        window = max(int(deactivate_fade_days), 1)
        sql = """
        WITH latest AS (
            SELECT
                v2.subject_key,
                v2.fade_confirmed,
                ROW_NUMBER() OVER (
                    PARTITION BY v2.subject_key
                    ORDER BY v2.trade_date DESC
                ) AS rn
            FROM theme_cycle_judgement_v2 v2
            JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = v2.subject_key
            WHERE v2.trade_date <= $1::date
              AND mr.identity_status = 'confirmed'
        ),
        agg AS (
            SELECT
                subject_key,
                COUNT(*) AS sampled_days,
                COUNT(*) FILTER (WHERE fade_confirmed) AS fade_days
            FROM latest
            WHERE rn <= $2::int
            GROUP BY subject_key
        ),
        to_deactivate AS (
            SELECT subject_key
            FROM agg
            WHERE sampled_days = $2::int
              AND fade_days = $2::int
        )
        UPDATE theme_mainline_identity_registry mr
        SET
            is_main_theme = FALSE,
            identity_status = 'inactive',
            last_review_date = $1::date,
            evidence_json = COALESCE(mr.evidence_json, '{}'::jsonb) || jsonb_build_object(
                'lifecycle',
                jsonb_build_object(
                    'deactivated_on', $1::text,
                    'reason', 'consecutive_fade_confirmed',
                    'window_days', $2::int
                )
            ),
            updated_at = NOW()
        WHERE mr.subject_key IN (SELECT subject_key FROM to_deactivate)
          AND mr.identity_status = 'confirmed'
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(sql, trade_date, window)
                raw = result.split()[-1] if result else "0"
                count = int(raw)
                if count > 0:
                    logger.info(
                        f"lifecycle downgrade: {count} confirmed mainlines deactivated "
                        f"on {trade_date} (window={window})"
                    )
                return count
        except Exception as e:
            logger.warning(f"lifecycle downgrade 失败 trade_date={trade_date}: {e}")
            return 0



    def _normalize_stock_snapshot_row(self, row: Dict[str, Any]) -> tuple:
        def _pick(*keys: str):
            for key in keys:
                if key in row and row[key] is not None:
                    return row[key]
            return None

        trade_date = _pick("trade_date")
        stock_id = _pick("stock_id")
        if not stock_id:
            stock_code = _pick("stock_code")
            market = str(_pick("market") or "").strip().upper()
            if stock_code and market in {"SH", "SZ"}:
                stock_id = f"{stock_code}.{market}"
            elif stock_code:
                stock_id = str(stock_code)
        if not trade_date or not stock_id:
            raise ValueError(f"invalid snapshot row, missing trade_date/stock_id: {row}")

        source_name = str(_pick("source_name") or "").strip()
        if not source_name:
            raise ValueError(f"invalid snapshot row, missing source_name: {row}")
        open_price = _pick("open_price")
        high_price = _pick("high_price")
        low_price = _pick("low_price")
        close_price = _pick("close_price")
        pre_close = _pick("pre_close")
        pct_chg = _pick("pct_chg")
        volume = _pick("volume")
        amount = _pick("amount")

        return (
            trade_date,
            str(stock_id),
            _pick("stock_name"),
            open_price,
            high_price,
            low_price,
            close_price,
            pre_close,
            pct_chg,
            volume,
            amount,
            source_name,
        )

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
                # 插入新闻数据 - 修复版：移除keywords和metadata列
                row = await conn.fetchrow("""
                    INSERT INTO news_raw
                    (news_id, title, content, source, publish_date,
                    publish_time, market, url)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
                    news_data.get('url', '')
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
                        created_at, updated_at
                    FROM news_raw
                    WHERE news_id = $1
                """, news_id)

                if row:
                    import json
                    # 转换为字典
                    result = dict(row)
                    # 添加默认的keywords和metadata字段（表中不存在这些列）
                    result['keywords'] = []
                    result['metadata'] = {}
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
                        created_at, updated_at
                    FROM news_raw
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)

                results = []
                for row in rows:
                    import json
                    result = dict(row)
                    # 添加默认的keywords和metadata字段（表中不存在这些列）
                    result['keywords'] = []
                    result['metadata'] = {}
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
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息 - 兼容方法"""
        # 调用已有的get_stats方法
        stats = await self.get_stats()
        
        # 添加一些额外的信息
        stats.update({
            'database_type': 'postgresql',
            'connection_status': self.connected if hasattr(self, 'connected') else True,
            'connection_info': {
                'host': self.config.postgres_host,
                'database': self.config.postgres_database
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

    @staticmethod
    def _bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "t", "yes", "y"}
        return bool(v)

    async def upsert_mainline_state_daily_rows(self, rows: list[dict[str, Any]]) -> int:
        """写入 mainline_state_daily 状态快照。"""
        sql = """
        INSERT INTO mainline_state_daily (
            trade_date, subject_key, theme_name,
            state, state_score, is_mainline,
            mainline_strength_score, fade_watch_score, fade_confirmed_score,
            divergence_score, repair_score,
            evidence_json, source_version, created_at, updated_at
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6,
            $7, $8, $9,
            $10, $11,
            $12::jsonb, $13, now(), now()
        )
        ON CONFLICT (trade_date, subject_key) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            state = EXCLUDED.state,
            state_score = EXCLUDED.state_score,
            is_mainline = EXCLUDED.is_mainline,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_watch_score = EXCLUDED.fade_watch_score,
            fade_confirmed_score = EXCLUDED.fade_confirmed_score,
            divergence_score = EXCLUDED.divergence_score,
            repair_score = EXCLUDED.repair_score,
            evidence_json = EXCLUDED.evidence_json,
            updated_at = now()
        """
        count = 0
        async with self.pool.acquire() as conn:
            for row in rows:
                await conn.execute(sql,
                    row.get("trade_date"), row.get("subject_key"), row.get("theme_name"),
                    row.get("state"), row.get("state_score"), row.get("is_mainline"),
                    row.get("mainline_strength_score"), row.get("fade_watch_score"),
                    row.get("fade_confirmed_score"), row.get("divergence_score"),
                    row.get("repair_score"),
                    _safe_json_dumps(row.get("evidence_json") or {}),
                    row.get("source_version", "mainline_state_transition.v2"),
                )
                count += 1
        return count

    async def upsert_mainline_state_transition_rows(self, rows: list[dict[str, Any]]) -> int:
        """写入 mainline_state_transition 迁移记录。"""
        sql = """
        INSERT INTO mainline_state_transition (
            trade_date, subject_key, theme_name,
            from_state, to_state, transition_type,
            from_score, to_score, confidence,
            trigger_flags, evidence_json, source_version, created_at
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6,
            $7, $8, $9,
            $10::jsonb, $11::jsonb, $12, now()
        )
        ON CONFLICT (trade_date, subject_key) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            from_state = EXCLUDED.from_state,
            to_state = EXCLUDED.to_state,
            transition_type = EXCLUDED.transition_type,
            from_score = EXCLUDED.from_score,
            to_score = EXCLUDED.to_score,
            confidence = EXCLUDED.confidence,
            trigger_flags = EXCLUDED.trigger_flags,
            evidence_json = EXCLUDED.evidence_json
        """
        count = 0
        async with self.pool.acquire() as conn:
            for row in rows:
                await conn.execute(sql,
                    row.get("trade_date"), row.get("subject_key"), row.get("theme_name"),
                    row.get("from_state"), row.get("to_state"), row.get("transition_type"),
                    row.get("from_score"), row.get("to_score"), row.get("confidence"),
                    _safe_json_dumps(row.get("trigger_flags") or []),
                    _safe_json_dumps(row.get("evidence_json") or {}),
                    row.get("source_version", "mainline_state_transition.v2"),
                )
                count += 1
        return count

    async def upsert_theme_cycle_judgement_v2_rows(self, rows: list[dict[str, Any]]) -> int:
        """Write corrected cycle judgements to theme_cycle_judgement_v2.

        REQUIRES: (subject_key, trade_date) unique constraint on the table.
        Audit fields are written to first-class columns when the migration is
        present, and mirrored into evidence_json when that legacy column exists.
        """
        import json as _json

        async with self.pool.acquire() as conn:
            col_rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema()"
                " AND table_name = 'theme_cycle_judgement_v2'"
            )
        col_set = {str(r["column_name"]) for r in col_rows}
        jsonb_columns = {"rule_reasons", "llm_reasons", "risk_flags", "evidence_refs", "score_flags", "evidence_json"}
        desired_columns = [
            "subject_key",
            "trade_date",
            "theme_name",
            "cycle_state_rule",
            "mainline_alive_rule",
            "cycle_state_llm",
            "mainline_alive_llm",
            "final_cycle_state",
            "final_mainline_alive",
            "fade_watch",
            "fade_confirmed",
            "mainline_strength_score",
            "fade_risk_score",
            "fade_watch_score",
            "fade_confirmed_score",
            "divergence_score",
            "repair_score",
            "confidence_score",
            "previous_cycle_state",
            "state_transition_reason",
            "rule_reasons",
            "llm_reasons",
            "risk_flags",
            "evidence_refs",
            "judgement_schema_version",
            "state_machine_version",
            "llm_prompt_version",
            "snapshot_version",
            "batch_id",
            "trace_id",
            "rule_version",
            "source_version",
            "updated_at",
            "evidence_json",
        ]
        insert_columns = [c for c in desired_columns if c in col_set]
        required_columns = {"subject_key", "trade_date", "final_cycle_state", "final_mainline_alive"}
        missing_required = sorted(required_columns - set(insert_columns))
        if missing_required:
            raise RuntimeError(f"theme_cycle_judgement_v2 missing required columns: {missing_required}")

        placeholders = []
        for idx, col in enumerate(insert_columns, start=1):
            if col == "trade_date":
                placeholders.append(f"${idx}::date")
            elif col in jsonb_columns:
                placeholders.append(f"${idx}::jsonb")
            else:
                placeholders.append(f"${idx}")
        update_columns = [
            c for c in insert_columns if c not in {"subject_key", "trade_date", "created_at"}
        ]
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
        sql = (
            f"INSERT INTO theme_cycle_judgement_v2 ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(placeholders)}) "
            "ON CONFLICT (subject_key, trade_date) DO UPDATE SET "
            f"{update_clause}"
        )

        payload = []
        for row in rows:
            sk = str(row.get("subject_key") or "")
            if not sk:
                continue
            td = row.get("trade_date")
            if isinstance(td, str):
                td = date.fromisoformat(td)
            now = datetime.now(timezone.utc)
            audit = {
                "snapshot_version": str(row.get("snapshot_version") or ""),
                "batch_id": str(row.get("batch_id") or ""),
                "trace_id": str(row.get("trace_id") or ""),
                "decision_path": str(row.get("decision_path") or ""),
                "mainline_alive_rule": self._bool(row.get("mainline_alive_rule")),
                "support_break": self._bool(row.get("support_break")),
                "score_flags": row.get("score_flags") or {},
                "fade_reason_codes": list(row.get("fade_reason_codes") or []),
                "fade_confirmed_evidence_count": int(row.get("fade_confirmed_evidence_count") or 0),
                "mainline_strength_score": str(row.get("mainline_strength_score") or "0"),
                "fade_watch_score": str(row.get("fade_watch_score") or "0"),
                "fade_confirmed_score": str(row.get("fade_confirmed_score") or "0"),
                "divergence_score": str(row.get("divergence_score") or "0"),
                "repair_score": str(row.get("repair_score") or "0"),
                "evidence_count": int(row.get("evidence_count") or 0),
                "rule_version": str(row.get("rule_version") or "subject_cycle_judgement.v2"),
                "source_version": str(row.get("source_version") or "stock_processing_service"),
            }
            values_by_column = {
                "subject_key": sk,
                "trade_date": td,
                "theme_name": str(row.get("theme_name") or row.get("subject_name") or sk),
                "cycle_state_rule": str(row.get("cycle_state_rule") or row.get("final_cycle_state") or ""),
                "mainline_alive_rule": self._bool(row.get("mainline_alive_rule")),
                "cycle_state_llm": row.get("cycle_state_llm"),
                "mainline_alive_llm": row.get("mainline_alive_llm"),
                "final_cycle_state": str(row.get("final_cycle_state") or ""),
                "final_mainline_alive": self._bool(row.get("final_mainline_alive")),
                "fade_watch": self._bool(row.get("fade_watch")) or str(row.get("final_cycle_state") or "") == "fade_watch",
                "fade_confirmed": self._bool(row.get("fade_confirmed")) or str(row.get("final_cycle_state") or "") == "fade_confirmed",
                "mainline_strength_score": row.get("mainline_strength_score") or 0,
                "fade_risk_score": row.get("fade_risk_score") or row.get("fade_watch_score") or 0,
                "fade_watch_score": row.get("fade_watch_score") or 0,
                "fade_confirmed_score": row.get("fade_confirmed_score") or 0,
                "divergence_score": row.get("divergence_score") or 0,
                "repair_score": row.get("repair_score") or 0,
                "confidence_score": row.get("confidence_score") or 0,
                "previous_cycle_state": row.get("previous_cycle_state"),
                "state_transition_reason": row.get("state_transition_reason") or row.get("decision_path"),
                "rule_reasons": _json.dumps(row.get("rule_reasons") or [], default=str),
                "llm_reasons": _json.dumps(row.get("llm_reasons") or [], default=str),
                "risk_flags": _json.dumps(row.get("risk_flags") or row.get("fade_reason_codes") or [], default=str),
                "evidence_refs": _json.dumps(row.get("evidence_refs") or [], default=str),
                "judgement_schema_version": str(row.get("judgement_schema_version") or "theme_cycle_judgement.v2"),
                "state_machine_version": str(row.get("state_machine_version") or "subject_cycle_state_machine.v2"),
                "llm_prompt_version": row.get("llm_prompt_version"),
                "snapshot_version": str(row.get("snapshot_version") or ""),
                "batch_id": str(row.get("batch_id") or ""),
                "trace_id": str(row.get("trace_id") or ""),
                "rule_version": str(row.get("rule_version") or "subject_cycle_judgement.v2"),
                "source_version": str(row.get("source_version") or "stock_processing_service"),
                "updated_at": row.get("updated_at") or now,
                "evidence_json": _json.dumps(audit, default=str),
            }
            vals = [values_by_column[c] for c in insert_columns]
            payload.append(tuple(vals))
        if not payload:
            return 0
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(sql, payload)
        return len(payload)

    async def upsert_theme_cycle_evidence_daily_rows(self, rows: list[dict[str, Any]]) -> int:
        """写入 theme_cycle_evidence_daily 表（Layer B 四层证据真源）。"""
        import json as _json
        sql = """
        INSERT INTO theme_cycle_evidence_daily (
            subject_key, trade_date, theme_name,
            event_count_3d, event_count_7d, strong_event_count_7d,
            event_recency_days, event_continuity_score, event_strength_score,
            leader_alive_score, leader_breakdown_flag,
            relay_strength_score, front_row_survival_ratio,
            board_stock_count, limit_up_count, limit_down_count,
            red_ratio, big_drop_ratio, front_row_strength_score,
            theme_support_score, break_start_pivot,
            above_ma10, above_ma20,
            evidence_json
        ) VALUES (
            $1, $2::date, $3,
            $4::int, $5::int, $6::int,
            $7::int, $8::numeric, $9::numeric,
            $10::numeric, $11,
            $12::numeric, $13::numeric,
            $14::int, $15::int, $16::int,
            $17::numeric, $18::numeric, $19::numeric,
            $20::numeric, $21,
            $22, $23,
            $24::jsonb
        )
        ON CONFLICT (subject_key, trade_date) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            event_count_3d = EXCLUDED.event_count_3d,
            event_count_7d = EXCLUDED.event_count_7d,
            strong_event_count_7d = EXCLUDED.strong_event_count_7d,
            event_recency_days = EXCLUDED.event_recency_days,
            event_continuity_score = EXCLUDED.event_continuity_score,
            event_strength_score = EXCLUDED.event_strength_score,
            leader_alive_score = EXCLUDED.leader_alive_score,
            leader_breakdown_flag = EXCLUDED.leader_breakdown_flag,
            relay_strength_score = EXCLUDED.relay_strength_score,
            front_row_survival_ratio = EXCLUDED.front_row_survival_ratio,
            board_stock_count = EXCLUDED.board_stock_count,
            limit_up_count = EXCLUDED.limit_up_count,
            limit_down_count = EXCLUDED.limit_down_count,
            red_ratio = EXCLUDED.red_ratio,
            big_drop_ratio = EXCLUDED.big_drop_ratio,
            front_row_strength_score = EXCLUDED.front_row_strength_score,
            theme_support_score = EXCLUDED.theme_support_score,
            break_start_pivot = EXCLUDED.break_start_pivot,
            above_ma10 = EXCLUDED.above_ma10,
            above_ma20 = EXCLUDED.above_ma20,
            evidence_json = EXCLUDED.evidence_json
        """
        payload = []
        for row in rows:
            sk = str(row.get("subject_key") or "")
            if not sk:
                continue
            td = row.get("trade_date")
            if isinstance(td, str):
                td = date.fromisoformat(td)
            ev = row.get("evidence_json") or {}
            if not isinstance(ev, dict):
                ev = {}
            board_layer = ev.get("board_layer", {}) if isinstance(ev.get("board_layer"), dict) else {}
            board_stock_count = int(
                row.get("board_stock_count")
                or board_layer.get("pool_size")
                or 0
            )
            payload.append((
                sk,
                td,
                str(row.get("theme_name") or sk),
                int(row.get("event_count_3d") or 0),
                int(row.get("event_count_7d") or 0),
                int(row.get("strong_event_count_7d") or 0),
                row.get("event_recency_days"),
                str(row.get("event_continuity_score") or "0"),
                str(row.get("event_strength_score") or "0"),
                str(row.get("leader_alive_score") or "0"),
                self._bool(row.get("leader_breakdown_flag")),
                str(row.get("relay_strength_score") or "0"),
                str(row.get("front_row_survival_ratio") or "0"),
                board_stock_count,
                int(row.get("limit_up_count") or 0),
                int(row.get("limit_down_count") or 0),
                str(row.get("red_ratio") or "0"),
                str(row.get("big_drop_ratio") or "0"),
                str(row.get("front_row_strength_score") or "0"),
                str(row.get("theme_support_score") or "0"),
                self._bool(row.get("break_start_pivot")),
                self._bool(row.get("above_ma10")),
                self._bool(row.get("above_ma20")),
                _json.dumps(ev, default=str, ensure_ascii=False),
            ))
        if not payload:
            return 0
        # asyncpg executemany returns None; actual persistence verified by SPS write-verify.
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(sql, payload)
        return len(payload)

    async def get_replay_snapshot_manifest(
        self,
        trade_date: date,
        layer_name: str,
        snapshot_version: str,
        algorithm_version: str,
    ) -> Optional[Dict[str, Any]]:
        """读取分层回放 manifest。"""
        sql = """
        SELECT
            trade_date,
            layer_name,
            snapshot_version,
            algorithm_version,
            input_hash,
            output_hash,
            row_count,
            status,
            batch_id,
            trace_id,
            created_at
        FROM replay_snapshot_manifest
        WHERE trade_date = $1::date
          AND layer_name = $2
          AND snapshot_version = $3
          AND algorithm_version = $4
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                trade_date,
                layer_name,
                snapshot_version,
                algorithm_version,
            )
        return dict(row) if row else None

    async def upsert_replay_snapshot_manifest(self, row: Dict[str, Any]) -> int:
        """写入分层回放 manifest。"""
        sql = """
        INSERT INTO replay_snapshot_manifest (
            trade_date,
            layer_name,
            snapshot_version,
            algorithm_version,
            input_hash,
            output_hash,
            row_count,
            status,
            batch_id,
            trace_id
        ) VALUES (
            $1::date, $2, $3, $4, $5, $6, $7::int, $8, $9, $10
        )
        ON CONFLICT (trade_date, layer_name, snapshot_version, algorithm_version)
        DO UPDATE SET
            input_hash = EXCLUDED.input_hash,
            output_hash = EXCLUDED.output_hash,
            row_count = EXCLUDED.row_count,
            status = EXCLUDED.status,
            batch_id = EXCLUDED.batch_id,
            trace_id = EXCLUDED.trace_id,
            created_at = now()
        """
        td = row.get("trade_date")
        if isinstance(td, str):
            td = date.fromisoformat(td)
        async with self.pool.acquire() as conn:
            await conn.execute(
                sql,
                td,
                str(row.get("layer_name") or ""),
                str(row.get("snapshot_version") or ""),
                str(row.get("algorithm_version") or ""),
                row.get("input_hash"),
                row.get("output_hash"),
                int(row.get("row_count") or 0),
                str(row.get("status") or "ok"),
                row.get("batch_id"),
                row.get("trace_id"),
            )
        return 1

#!/usr/bin/env python3
"""
久赢恒丰数据导入脚本（优化版 + 断点续传）
- 支持断点续传：通过 import_file_tracker 记录每个文件的处理状态
- 支持导入后完整性检查
- 保留原有所有功能：schema校验、批量写入、每文件事务、异步接口等
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# 设置 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.config import DatabaseConfig, DatabaseType, RedisConfig

# ==================== 配置 ====================
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 索引常量（基于久赢恒丰 children 数组结构）
IDX_SUBJECT_ID = 0
IDX_NAME = 1
IDX_FULL_NAME = 2
IDX_PCT_CHG = 3
IDX_STOCK_COUNT = 4
IDX_LIMIT_UP_COUNT = 5
IDX_LEAD_TIMES = 6
IDX_RESERVED_7 = 7          # 未知字段，可能是其他指标
IDX_RESERVED_8 = 8          # 可能为 null 或数字，忽略
IDX_AMOUNT = 9
IDX_MARKET_VALUE = 10
IDX_LEAD_STOCK_ID = 11
IDX_LEAD_STOCK_NAME = 12
IDX_ANCESTORS = 13
IDX_CHILDREN = 14
IDX_STOCKS = 15
MIN_NODE_LENGTH = 14        # 至少有 ancestors 字段


# ==================== DTO ====================

@dataclass
class SubjectNodeDTO:
    subject_key: str                # 久赢恒丰原始 ID（用于 staging）
    name: str
    level: int
    parent_subject_key: Optional[str]
    ancestors: str
    full_name: Optional[str]
    pct_chg: Optional[float]
    stock_count: Optional[int]
    limit_up_count: Optional[int]
    lead_times: Optional[int]
    amount: Optional[float]
    market_value: Optional[float]
    lead_stock_id: Optional[str]
    lead_stock_name: Optional[str]
    children: List['SubjectNodeDTO'] = field(default_factory=list)
    stocks: List['SubjectStockMapDTO'] = field(default_factory=list)


@dataclass
class SubjectStockMapDTO:
    selected_id: Optional[int]
    subject_key: str
    stock_id: str
    name: Optional[str]
    pct_chg: Optional[float]
    sort: Optional[int]
    top: bool
    reason: Optional[str]
    remark: Optional[str]


# ==================== 数据库配置 ====================

def get_postgres_config():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "zxbzj~925")
    database = os.getenv("POSTGRES_DATABASE", "stock_data_test")

    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=host,
        postgres_port=port,
        postgres_database=database,
        postgres_username=user,
        postgres_password=password,
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=10
    )


# ==================== DDL（优化版 + 跟踪表） ====================

TABLES_DDL = [
    # 导入文件跟踪表（断点续传核心）
    """
    CREATE TABLE IF NOT EXISTS import_file_tracker (
        id               BIGSERIAL PRIMARY KEY,
        file_path        TEXT NOT NULL,
        file_type        VARCHAR(20) NOT NULL,
        batch_id         VARCHAR(50) NOT NULL,
        status           VARCHAR(20) DEFAULT 'pending',
        retry_count      INTEGER DEFAULT 0,
        row_count        INTEGER,
        file_size        BIGINT,
        file_mtime       TIMESTAMP,
        error_msg        TEXT,
        started_at       TIMESTAMP,
        completed_at     TIMESTAMP,
        created_at       TIMESTAMP DEFAULT NOW(),
        updated_at       TIMESTAMP DEFAULT NOW(),
        UNIQUE(file_path, batch_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_import_tracker_status ON import_file_tracker(status)",
    "CREATE INDEX IF NOT EXISTS idx_import_tracker_batch ON import_file_tracker(batch_id)",

    # staging 表：存储原始导入数据
    """
    CREATE TABLE IF NOT EXISTS jyhf_subject_node_staging (
        id                 BIGSERIAL PRIMARY KEY,
        subject_key        VARCHAR(80) NOT NULL,
        name               VARCHAR(150) NOT NULL,
        level              SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 10),
        parent_subject_key VARCHAR(80),
        ancestors          TEXT NOT NULL,
        full_name          TEXT,
        pct_chg            NUMERIC(8,4),
        stock_count        INTEGER,
        limit_up_count     INTEGER,
        lead_times         INTEGER,
        amount             NUMERIC(20,2),
        market_value       NUMERIC(20,2),
        lead_stock_id      VARCHAR(20),
        lead_stock_name    VARCHAR(100),
        source_system      VARCHAR(50) DEFAULT 'jyhf',
        source_version     VARCHAR(20),
        ingest_batch_id    VARCHAR(50),
        source_updated_at  TIMESTAMP,
        created_at         TIMESTAMP DEFAULT NOW(),
        updated_at         TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_jyhf_staging_subject_key UNIQUE (subject_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_staging_subject_key ON jyhf_subject_node_staging(subject_key)",
    "CREATE INDEX IF NOT EXISTS idx_staging_ancestors ON jyhf_subject_node_staging(ancestors)",

    # 题材详情表（增加 created_at）
    """
    CREATE TABLE IF NOT EXISTS subject_detail (
        subject_key        VARCHAR(80) PRIMARY KEY,
        detail_html        TEXT NOT NULL,
        detail_version     INTEGER DEFAULT 1,
        created_at         TIMESTAMP DEFAULT NOW(),
        updated_at         TIMESTAMP DEFAULT NOW()
    )
    """,

    # 每日驱动事件
    """
    CREATE TABLE IF NOT EXISTS subject_rank_daily (
        id                 BIGSERIAL PRIMARY KEY,
        subject_key        VARCHAR(80) NOT NULL,
        rank_date          DATE NOT NULL,
        heat               INTEGER,
        heat_name          VARCHAR(50),
        pct_chg            NUMERIC(8,4),
        his_pct_chg        NUMERIC(8,4),
        red                BOOLEAN DEFAULT FALSE,
        description        TEXT,
        source_system      VARCHAR(50) DEFAULT 'jyhf',
        created_at         TIMESTAMP DEFAULT NOW(),
        updated_at         TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_rank UNIQUE(subject_key, rank_date)
    )
    """,

    # 股票表
    """
    CREATE TABLE IF NOT EXISTS stocks (
        stock_id           VARCHAR(20) PRIMARY KEY,
        name               VARCHAR(100) NOT NULL,
        first_letter       VARCHAR(20),
        remark             TEXT,
        detail_html        TEXT,
        price              NUMERIC(12,4),
        pct_chg            NUMERIC(8,4),
        amount             NUMERIC(20,2),
        market_value       NUMERIC(20,2),
        high               NUMERIC(12,4),
        low                NUMERIC(12,4),
        vol                NUMERIC(20,2),
        recent_365_limit_up_count INTEGER,
        recent_10_red_count INTEGER,
        recent_10_blue_count INTEGER,
        recent_10_yellow_count INTEGER,
        source_updated_at  TIMESTAMP,
        created_at         TIMESTAMP DEFAULT NOW(),
        updated_at         TIMESTAMP DEFAULT NOW()
    )
    """,

    # 股票亮点
    """
    CREATE TABLE IF NOT EXISTS stock_lightspots (
        lightspot_id       BIGINT PRIMARY KEY,
        stock_id           VARCHAR(20) NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
        content            TEXT NOT NULL,
        biz_key            TEXT,
        created_at         TIMESTAMP DEFAULT NOW()
    )
    """,

    # 增强版题材-股票映射
    """
    CREATE TABLE IF NOT EXISTS subject_stock_map (
        id                 BIGSERIAL PRIMARY KEY,
        selected_id        BIGINT,
        subject_key        VARCHAR(80) NOT NULL,
        stock_id           VARCHAR(20) NOT NULL,
        name               VARCHAR(100),
        pct_chg            NUMERIC(8,4),
        sort               INTEGER,
        top                BOOLEAN DEFAULT FALSE,
        reason             TEXT,
        remark             TEXT,
        source_type        VARCHAR(20) DEFAULT 'jyhf',  -- jyhf/rule/llm/manual
        confidence         NUMERIC(4,2) DEFAULT 1.0,
        start_date         DATE,
        end_date           DATE,
        evidence_json      JSONB,
        created_at         TIMESTAMP DEFAULT NOW(),
        updated_at         TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_stock UNIQUE(subject_key, stock_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ssm_subject ON subject_stock_map(subject_key)",
    "CREATE INDEX IF NOT EXISTS idx_ssm_stock ON subject_stock_map(stock_id)",
    "CREATE INDEX IF NOT EXISTS idx_ssm_selected_id ON subject_stock_map(selected_id)",

    # 事实表（AI 驱动用）
    """
    CREATE TABLE IF NOT EXISTS stock_facts (
        id                 BIGSERIAL PRIMARY KEY,
        stock_id           VARCHAR(20) NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
        fact_type          VARCHAR(50) NOT NULL,
        fact_value         TEXT NOT NULL,
        source             VARCHAR(50),
        confidence         NUMERIC(4,2) DEFAULT 1.0,
        start_date         DATE,
        end_date           DATE,
        created_at         TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_facts_stock ON stock_facts(stock_id)",
    "CREATE INDEX IF NOT EXISTS idx_facts_type ON stock_facts(fact_type)",

    # 题材键映射表（解决与申万库的冲突）
    """
    CREATE TABLE IF NOT EXISTS subject_key_map (
        internal_subject_key VARCHAR(80) PRIMARY KEY,
        jyhf_subject_id      VARCHAR(80) NOT NULL,
        source_system        VARCHAR(20) DEFAULT 'jyhf',
        match_confidence     NUMERIC(4,2) DEFAULT 1.0,
        created_at           TIMESTAMP DEFAULT NOW(),
        updated_at           TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_map_jyhf_id ON subject_key_map(jyhf_subject_id)",

    # 错误记录表
    """
    CREATE TABLE IF NOT EXISTS import_errors (
        id                 BIGSERIAL PRIMARY KEY,
        file_name          VARCHAR(255),
        subject_key        VARCHAR(80),
        error_type         VARCHAR(50),
        error_detail       TEXT,
        raw_data           JSONB,
        created_at         TIMESTAMP DEFAULT NOW()
    )
    """,
]

# 旧表迁移函数（将旧版 subject_stock_map 升级）
async def migrate_subject_stock_map(conn):
    # 检查是否存在旧表且需要迁移
    has_old = await conn.fetchval("SELECT to_regclass('public.subject_stock_map')")
    if not has_old:
        return

    cols = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='subject_stock_map'
        ORDER BY ordinal_position
    """)
    colset = {r['column_name'] for r in cols}
    is_legacy = 'id' not in colset and 'selected_id' in colset and 'subject_key' in colset and 'stock_id' in colset

    if not is_legacy:
        logger.info("subject_stock_map 已是新结构或无需迁移")
        return

    # 迁移：改名 -> 建新表 -> 回灌数据
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    legacy_name = f"subject_stock_map_legacy_{ts}"
    logger.warning(f"检测到旧版 subject_stock_map，迁移至 {legacy_name}")

    async with conn.transaction():
        await conn.execute(f'ALTER TABLE subject_stock_map RENAME TO "{legacy_name}"')
        # 建新表（前面已包含在 TABLES_DDL 中，但这里单独执行确保结构最新）
        for ddl in TABLES_DDL:
            if 'subject_stock_map' in ddl and 'CREATE TABLE' in ddl:
                await conn.execute(ddl)
                break

        # 回灌数据
        await conn.execute(f"""
            INSERT INTO subject_stock_map (
                selected_id, subject_key, stock_id, name, pct_chg, sort, top, reason, remark,
                source_type, confidence, start_date, end_date, evidence_json, created_at, updated_at
            )
            SELECT
                selected_id, subject_key, stock_id, name, pct_chg, sort,
                CASE WHEN top IN (true, 't', 'true', 1, '1') THEN true ELSE false END,
                reason, remark,
                'jyhf' as source_type,
                1.0 as confidence,
                NULL as start_date,
                NULL as end_date,
                NULL as evidence_json,
                COALESCE(created_at, NOW()) as created_at,
                NOW() as updated_at
            FROM "{legacy_name}"
            ON CONFLICT (subject_key, stock_id) DO UPDATE SET
                selected_id = COALESCE(EXCLUDED.selected_id, subject_stock_map.selected_id),
                name = COALESCE(EXCLUDED.name, subject_stock_map.name),
                pct_chg = COALESCE(EXCLUDED.pct_chg, subject_stock_map.pct_chg),
                sort = COALESCE(EXCLUDED.sort, subject_stock_map.sort),
                top = COALESCE(EXCLUDED.top, subject_stock_map.top),
                reason = COALESCE(EXCLUDED.reason, subject_stock_map.reason),
                remark = COALESCE(EXCLUDED.remark, subject_stock_map.remark),
                updated_at = NOW()
        """)

    logger.info("subject_stock_map 迁移完成")


async def ensure_tables(manager: PostgresDatabaseManager, batch_id: str):
    """确保所有表存在，并执行必要迁移"""
    if not manager.pool:
        raise RuntimeError("数据库连接未建立")
    async with manager.pool.acquire() as conn:
        async with conn.transaction():
            # 删除 staging 表重建，确保唯一约束生效
            await conn.execute("DROP TABLE IF EXISTS jyhf_subject_node_staging CASCADE")
            for ddl in TABLES_DDL:
                await conn.execute(ddl)
        # 迁移旧版 subject_stock_map（在事务外或内均可，但这里确保在事务外避免死锁）
        await migrate_subject_stock_map(conn)


# ==================== 解析与校验 ====================

def parse_node(raw_node: list, parent_key: Optional[str] = None) -> Tuple[Optional[SubjectNodeDTO], List[str]]:
    """
    解析原始节点，返回 DTO 和错误列表
    - 严重缺失（subject_key/name 缺失）返回 None
    - 其他错误仅收集，仍返回 DTO
    """
    errors = []
    if not isinstance(raw_node, list) or len(raw_node) < MIN_NODE_LENGTH:
        errors.append("节点格式错误：不是列表或长度不足")
        return None, errors

    subject_key = str(raw_node[IDX_SUBJECT_ID]) if raw_node[IDX_SUBJECT_ID] is not None else None
    name = raw_node[IDX_NAME]
    if not subject_key:
        errors.append("subject_key 缺失")
        return None, errors
    if not name:
        errors.append("name 缺失")
        return None, errors

    # 提取 ancestors（即使格式错误，也使用原始值）
    ancestors = raw_node[IDX_ANCESTORS] if len(raw_node) > IDX_ANCESTORS else None
    if ancestors is None:
        errors.append("ancestors 缺失，使用默认 '0'")
        ancestors = "0"
    elif not isinstance(ancestors, str):
        errors.append(f"ancestors 不是字符串，转为字符串")
        ancestors = str(ancestors)
    if not ancestors:
        ancestors = "0"
        errors.append("ancestors 为空，使用默认 '0'")

    # 记录格式问题，但不阻断
    if ancestors != "0":
        parts = ancestors.split(',')
        if parts[0] != '0':
            errors.append("ancestors 不以 '0' 开头")
        if len(parts) < 2 or not parts[-1]:
            errors.append("ancestors 路径不完整")
        else:
            # 可选：检查末尾是否与 subject_key 一致（不一致仅警告）
            if parts[-1] != subject_key:
                errors.append(f"ancestors 末尾 {parts[-1]} 与 subject_key {subject_key} 不一致")

    # 计算 level：ancestors 中逗号数量 + 1
    level = ancestors.count(',') + 1

    # 提取其他字段（使用安全索引）
    full_name = raw_node[IDX_FULL_NAME] if len(raw_node) > IDX_FULL_NAME else None
    pct_chg = raw_node[IDX_PCT_CHG] if len(raw_node) > IDX_PCT_CHG else None
    stock_count = raw_node[IDX_STOCK_COUNT] if len(raw_node) > IDX_STOCK_COUNT else None
    limit_up_count = raw_node[IDX_LIMIT_UP_COUNT] if len(raw_node) > IDX_LIMIT_UP_COUNT else None
    lead_times = raw_node[IDX_LEAD_TIMES] if len(raw_node) > IDX_LEAD_TIMES else None
    amount = raw_node[IDX_AMOUNT] if len(raw_node) > IDX_AMOUNT else None
    market_value = raw_node[IDX_MARKET_VALUE] if len(raw_node) > IDX_MARKET_VALUE else None
    lead_stock_id = raw_node[IDX_LEAD_STOCK_ID] if len(raw_node) > IDX_LEAD_STOCK_ID else None
    lead_stock_name = raw_node[IDX_LEAD_STOCK_NAME] if len(raw_node) > IDX_LEAD_STOCK_NAME else None
    children_raw = raw_node[IDX_CHILDREN] if len(raw_node) > IDX_CHILDREN else []
    stocks_raw = raw_node[IDX_STOCKS] if len(raw_node) > IDX_STOCKS else []

    # 构建 DTO（即使有错误也继续）
    dto = SubjectNodeDTO(
        subject_key=subject_key,
        name=str(name),
        level=level,
        parent_subject_key=parent_key,
        ancestors=ancestors,
        full_name=str(full_name) if full_name else None,
        pct_chg=float(pct_chg) if pct_chg is not None else None,
        stock_count=int(stock_count) if stock_count is not None else None,
        limit_up_count=int(limit_up_count) if limit_up_count is not None else None,
        lead_times=int(lead_times) if lead_times is not None else None,
        amount=float(amount) if amount is not None else None,
        market_value=float(market_value) if market_value is not None else None,
        lead_stock_id=str(lead_stock_id) if lead_stock_id else None,
        lead_stock_name=str(lead_stock_name) if lead_stock_name else None,
        children=[],
        stocks=[]
    )

    # 解析子节点（递归）
    if isinstance(children_raw, list):
        for child in children_raw:
            child_dto, child_errors = parse_node(child, parent_key=subject_key)
            if child_dto:
                dto.children.append(child_dto)
            errors.extend(child_errors)

    # 解析股票映射
    if isinstance(stocks_raw, list):
        for s in stocks_raw:
            if not isinstance(s, dict):
                continue
            stock_id = s.get('stockId')
            if not stock_id:
                continue
            stock_dto = SubjectStockMapDTO(
                selected_id=s.get('selectedId'),
                subject_key=subject_key,
                stock_id=str(stock_id),
                name=s.get('name'),
                pct_chg=s.get('pctChg'),
                sort=s.get('sort', 0),
                top=bool(s.get('top', False)),
                reason=s.get('reason'),
                remark=s.get('remark')
            )
            dto.stocks.append(stock_dto)

    return dto, errors


def flatten_tree(dto: SubjectNodeDTO) -> Tuple[List[SubjectNodeDTO], List[SubjectStockMapDTO]]:
    """将树形 DTO 扁平化为列表"""
    nodes = [dto]
    maps = dto.stocks.copy()
    for child in dto.children:
        child_nodes, child_maps = flatten_tree(child)
        nodes.extend(child_nodes)
        maps.extend(child_maps)
    return nodes, maps


# ==================== 批量写入函数 ====================

async def batch_upsert_nodes(conn, nodes: List[SubjectNodeDTO], batch_id: str, batch_size=500):
    logger.debug(f"batch_upsert_nodes: 准备插入 {len(nodes)} 个节点")
    sql = """
        INSERT INTO jyhf_subject_node_staging (
            subject_key, name, level, parent_subject_key, ancestors, full_name,
            pct_chg, stock_count, limit_up_count, lead_times,
            amount, market_value, lead_stock_id, lead_stock_name,
            source_system, ingest_batch_id, source_updated_at, updated_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,
            'jyhf', $15, NOW(), NOW()
        )
        ON CONFLICT (subject_key) DO UPDATE SET
            name = EXCLUDED.name,
            level = EXCLUDED.level,
            parent_subject_key = EXCLUDED.parent_subject_key,
            ancestors = EXCLUDED.ancestors,
            full_name = EXCLUDED.full_name,
            pct_chg = EXCLUDED.pct_chg,
            stock_count = EXCLUDED.stock_count,
            limit_up_count = EXCLUDED.limit_up_count,
            lead_times = EXCLUDED.lead_times,
            amount = EXCLUDED.amount,
            market_value = EXCLUDED.market_value,
            lead_stock_id = EXCLUDED.lead_stock_id,
            lead_stock_name = EXCLUDED.lead_stock_name,
            source_updated_at = EXCLUDED.source_updated_at,
            updated_at = NOW()
    """
    params = [
        (
            n.subject_key, n.name, n.level, n.parent_subject_key, n.ancestors, n.full_name,
            n.pct_chg, n.stock_count, n.limit_up_count, n.lead_times,
            n.amount, n.market_value, n.lead_stock_id, n.lead_stock_name,
            batch_id
        )
        for n in nodes
    ]
    for i in range(0, len(params), batch_size):
        batch = params[i:i+batch_size]
        logger.debug(f"执行批次 {i//batch_size}, 大小 {len(batch)}")
        await conn.executemany(sql, batch)
        logger.debug(f"批次 {i//batch_size} 完成")


async def batch_upsert_stock_maps(conn, maps: List[SubjectStockMapDTO], batch_id: str, batch_size=500):
    sql = """
        INSERT INTO subject_stock_map (
            selected_id, subject_key, stock_id, name, pct_chg, sort, top, reason, remark,
            source_type, confidence, start_date, end_date, evidence_json, created_at, updated_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,
            'jyhf', 1.0, NULL, NULL, NULL, NOW(), NOW()
        )
        ON CONFLICT (subject_key, stock_id) DO UPDATE SET
            selected_id = COALESCE(EXCLUDED.selected_id, subject_stock_map.selected_id),
            name = COALESCE(EXCLUDED.name, subject_stock_map.name),
            pct_chg = COALESCE(EXCLUDED.pct_chg, subject_stock_map.pct_chg),
            sort = COALESCE(EXCLUDED.sort, subject_stock_map.sort),
            top = COALESCE(EXCLUDED.top, subject_stock_map.top),
            reason = COALESCE(EXCLUDED.reason, subject_stock_map.reason),
            remark = COALESCE(EXCLUDED.remark, subject_stock_map.remark),
            updated_at = NOW()
    """
    params = [
        (
            m.selected_id, m.subject_key, m.stock_id, m.name, m.pct_chg,
            m.sort if m.sort is not None else 0,
            m.top,
            m.reason, m.remark
        )
        for m in maps
    ]
    for i in range(0, len(params), batch_size):
        await conn.executemany(sql, params[i:i+batch_size])

async def batch_upsert_theme_master(conn, nodes: List[SubjectNodeDTO], batch_size=500):
    """将 L3 节点插入或更新到 theme_master 表"""
    # 只处理 level == 3 的节点
    theme_nodes = [n for n in nodes if n.level == 3]
    if not theme_nodes:
        logger.debug("batch_upsert_theme_master: 没有 L3 节点，跳过")
        return
    logger.info(f"batch_upsert_theme_master: 准备插入 {len(theme_nodes)} 个 L3 节点到 theme_master")

    sql = """
        INSERT INTO theme_master (
            code, name, description, status, level1_category, level2_category, level3_category,
            category_path, category1_code, category2_code, category3_code,
            tags, theme_type, lifecycle_stage, heat_score, confidence_score,
            related_stocks, stock_count, news_count, mention_count, last_mentioned,
            source_system, source_id, created_by, created_at, updated_at
        ) VALUES (
            $1, $2, $3, 'active', NULL, NULL, NULL,
            NULL, NULL, NULL, NULL,
            $4, 'concept', 'growth', $5, 0.8,
            $6, $7, 0, 0, NULL,
            'jyhf', $8, 'system', NOW(), NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            tags = EXCLUDED.tags,
            heat_score = EXCLUDED.heat_score,
            related_stocks = EXCLUDED.related_stocks,
            stock_count = EXCLUDED.stock_count,
            updated_at = NOW()
    """
    params = []
    for n in theme_nodes:
        # 构建 tags JSON
        tags = {
            "jyhf_id": n.subject_key,
            "ancestors": n.ancestors,
            "full_name": n.full_name,
            "pct_chg": n.pct_chg,
            "limit_up_count": n.limit_up_count,
            "lead_times": n.lead_times,
        }
        tags_json = json.dumps(tags, ensure_ascii=False)

        # 提取相关股票列表
        stock_ids = [s.stock_id for s in n.stocks] if n.stocks else []

        # heat_score 简单映射（例如取 pct_chg*10，若无则默认 50）
        heat_score = int(n.pct_chg * 10) if n.pct_chg is not None else 50

        params.append((
            n.subject_key,          # code
            n.name,                 # name
            n.full_name,            # description（暂用 full_name）
            tags_json,              # tags
            heat_score,             # heat_score
            stock_ids,              # related_stocks
            n.stock_count or 0,     # stock_count
            n.subject_key,          # source_id
        ))

    for i in range(0, len(params), batch_size):
        await conn.executemany(sql, params[i:i+batch_size])
    
    logger.info(f"batch_upsert_theme_master: 完成插入 {len(theme_nodes)} 个节点")

async def log_import_error(manager: PostgresDatabaseManager, file_name: str, subject_key: Optional[str], error_type: str, error_detail: str, raw_data: Any):
    """记录导入错误（内部获取连接）"""
    sql = """
        INSERT INTO import_errors (file_name, subject_key, error_type, error_detail, raw_data, created_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql, file_name, subject_key, error_type, error_detail, json.dumps(raw_data, ensure_ascii=False))

# ==================== 断点续传工具函数 ====================

async def get_pending_files(manager: PostgresDatabaseManager, file_type: str, files: List[Path], batch_id: str, data_root: Path, resume: bool = True):
    """
    根据文件列表和跟踪表，返回需要处理的文件列表。
    - 如果 resume=True，则跳过已成功且文件未变化的文件。
    - 如果文件状态为 failed 且 retry_count 小于最大重试次数，也会返回。
    """
    if not resume:
        return files

    pending = []
    async with manager.pool.acquire() as conn:
        for file in files:
            # 获取文件当前信息
            stat = file.stat()
            file_mtime = datetime.fromtimestamp(stat.st_mtime)
            file_size = stat.st_size
            file_path = str(file.relative_to(data_root))

            # 查询跟踪表
            row = await conn.fetchrow("""
                SELECT status, retry_count, file_mtime, file_size
                FROM import_file_tracker
                WHERE file_path = $1 AND batch_id = $2
            """, file_path, batch_id)

            if not row:
                pending.append(file)
                continue

            if row['status'] == 'success':
                # 检查文件是否被修改（可选）
                # 如果文件修改时间或大小变化，则重新导入
                if row['file_mtime'] == file_mtime and row['file_size'] == file_size:
                    continue  # 已成功且未变化，跳过
                else:
                    logger.info(f"文件 {file_path} 已修改，重新导入")
                    pending.append(file)
            elif row['status'] == 'failed' and row['retry_count'] < 3:  # 最大重试3次
                pending.append(file)
            elif row['status'] in ('pending', 'processing'):
                # 上次未完成，重新处理
                pending.append(file)
            else:
                # 其他情况（如失败次数过多）暂不处理
                logger.warning(f"文件 {file_path} 状态 {row['status']} 且重试次数已达上限，跳过")
    return pending


async def mark_file_start(manager: PostgresDatabaseManager, file_path: str, file_type: str, batch_id: str, data_root: Path):
    """开始处理文件时，插入或更新状态为 processing"""
    async with manager.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO import_file_tracker (file_path, file_type, batch_id, status, started_at, updated_at)
            VALUES ($1, $2, $3, 'processing', NOW(), NOW())
            ON CONFLICT (file_path, batch_id) DO UPDATE SET
                status = 'processing',
                started_at = NOW(),
                updated_at = NOW(),
                retry_count = import_file_tracker.retry_count + 1
        """, file_path, file_type, batch_id)


async def mark_file_success(manager: PostgresDatabaseManager, file_path: str, batch_id: str, row_count: int, file_size: int, file_mtime: datetime):
    """处理成功，更新状态为 success"""
    async with manager.pool.acquire() as conn:
        await conn.execute("""
            UPDATE import_file_tracker
            SET status = 'success',
                row_count = $3,
                file_size = $4,
                file_mtime = $5,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE file_path = $1 AND batch_id = $2
        """, file_path, batch_id, row_count, file_size, file_mtime)


async def mark_file_failed(manager: PostgresDatabaseManager, file_path: str, batch_id: str, error_msg: str):
    """处理失败，更新状态为 failed"""
    async with manager.pool.acquire() as conn:
        await conn.execute("""
            UPDATE import_file_tracker
            SET status = 'failed',
                error_msg = $3,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE file_path = $1 AND batch_id = $2
        """, file_path, batch_id, error_msg)


async def check_import(manager: PostgresDatabaseManager, batch_id: str):
    """检查导入完整性：对比跟踪表成功记录数与数据库实际记录数"""
    logger.info("开始检查导入完整性...")
    async with manager.pool.acquire() as conn:
        # 获取每个类型成功的文件数和总行数
        stats = await conn.fetch("""
            SELECT file_type, COUNT(*) as file_count, SUM(row_count) as total_rows
            FROM import_file_tracker
            WHERE batch_id = $1 AND status = 'success'
            GROUP BY file_type
        """, batch_id)
        for stat in stats:
            logger.info(f"类型 {stat['file_type']}: 成功文件数 {stat['file_count']}, 总行数 {stat['total_rows']}")

        # 对比 stocks 表实际记录数
        stock_count = await conn.fetchval("SELECT COUNT(*) FROM stocks")
        logger.info(f"stocks 表实际记录数: {stock_count}")

        # 对比 subject_detail 表
        detail_count = await conn.fetchval("SELECT COUNT(*) FROM subject_detail")
        logger.info(f"subject_detail 表实际记录数: {detail_count}")

        # 对比 subject_rank_daily 表
        rank_count = await conn.fetchval("SELECT COUNT(*) FROM subject_rank_daily")
        logger.info(f"subject_rank_daily 表实际记录数: {rank_count}")

        # 对比 jyhf_subject_node_staging 表（可选项）
        node_count = await conn.fetchval("SELECT COUNT(*) FROM jyhf_subject_node_staging WHERE ingest_batch_id = $1", batch_id)
        logger.info(f"当前批次 jyhf_subject_node_staging 记录数: {node_count}")

        # 可进一步输出差异警告
        logger.info("检查完成（如需精确对比，请自行扩展）")


# ==================== 具体导入函数 ====================
def clean_text(value):
    """清洗文本字段，移除 NULL 字符等非法字符"""
    if value is None:
        return None
    if isinstance(value, str):
        # 移除 NULL 字符
        return value.replace('\x00', '')
    return value


async def import_stocks(manager: PostgresDatabaseManager, stock_dir: Path, data_root: Path, batch_id: str, batch_size=500, limit=None, resume=True):
    logger.info(f"开始导入个股数据从 {stock_dir}")
    files = list(stock_dir.glob("*.json"))
    if limit:
        files = files[:limit]
        logger.info(f"限制处理前 {limit} 个文件")

    # 获取需要处理的文件列表
    files_to_process = await get_pending_files(manager, 'stocks', files, batch_id, data_root, resume)
    if not files_to_process:
        logger.info("没有需要处理的个股文件")
        return

    total_count = 0
    for file in files_to_process:
        file_path = str(file.relative_to(data_root))
        try:
            await mark_file_start(manager, file_path, 'stocks', batch_id, data_root)

            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data = data.get('data', data) if isinstance(data, dict) else data
            stock_id = data.get('stockId')
            if not stock_id:
                logger.warning(f"文件 {file.name} 无 stockId，跳过")
                await mark_file_failed(manager, file_path, batch_id, "Missing stockId")
                continue

            # 清洗所有文本字段
            name = clean_text(data.get('name'))
            first_letter = clean_text(data.get('firstLetter'))
            remark = clean_text(data.get('remark'))
            detail = clean_text(data.get('detail'))

            # 处理 updateTime
            update_time_str = data.get('updateTime')
            if update_time_str and isinstance(update_time_str, str):
                try:
                    update_time = datetime.strptime(update_time_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    update_time = None
            else:
                update_time = None

            async with manager.pool.acquire() as conn:
                async with conn.transaction():
                    # upsert stock
                    await conn.execute("""
                        INSERT INTO stocks (
                            stock_id, name, first_letter, remark, detail_html,
                            price, pct_chg, amount, market_value, high, low, vol,
                            recent_365_limit_up_count, recent_10_red_count,
                            recent_10_blue_count, recent_10_yellow_count,
                            source_updated_at, updated_at
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NOW())
                        ON CONFLICT (stock_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            first_letter = EXCLUDED.first_letter,
                            remark = EXCLUDED.remark,
                            detail_html = EXCLUDED.detail_html,
                            price = EXCLUDED.price,
                            pct_chg = EXCLUDED.pct_chg,
                            amount = EXCLUDED.amount,
                            market_value = EXCLUDED.market_value,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            vol = EXCLUDED.vol,
                            recent_365_limit_up_count = EXCLUDED.recent_365_limit_up_count,
                            recent_10_red_count = EXCLUDED.recent_10_red_count,
                            recent_10_blue_count = EXCLUDED.recent_10_blue_count,
                            recent_10_yellow_count = EXCLUDED.recent_10_yellow_count,
                            source_updated_at = EXCLUDED.source_updated_at,
                            updated_at = NOW()
                    """, *(
                        str(stock_id),
                        name,
                        first_letter,
                        remark,
                        detail,
                        data.get('price'),
                        data.get('pctChg'),
                        data.get('amount'),
                        data.get('marketValue'),
                        data.get('high'),
                        data.get('low'),
                        data.get('vol'),
                        data.get('recent365LimitUpCount'),
                        data.get('recent10RedCount'),
                        data.get('recent10BlueCount'),
                        data.get('recent10YellowCount'),
                        update_time
                    ))

                    # upsert lightspots
                    spots = data.get('stockLightspots', [])
                    for spot in spots:
                        if not spot.get('lightspotId'):
                            continue
                        content = clean_text(spot.get('content'))
                        biz_key = clean_text(spot.get('bizKey'))
                        await conn.execute("""
                            INSERT INTO stock_lightspots (lightspot_id, stock_id, content, biz_key, created_at)
                            VALUES ($1,$2,$3,$4,NOW())
                            ON CONFLICT (lightspot_id) DO NOTHING
                        """, *(
                            spot['lightspotId'],
                            str(stock_id),
                            content,
                            biz_key
                        ))

            stat = file.stat()
            await mark_file_success(manager, file_path, batch_id, 1, stat.st_size, datetime.fromtimestamp(stat.st_mtime))
            total_count += 1
        except Exception as e:
            logger.exception(f"处理文件 {file} 时出错")
            await mark_file_failed(manager, file_path, batch_id, str(e))
            # 可以选择继续处理其他文件
            # 如果希望遇到错误立即停止，则 raise

        if total_count % 50 == 0:
            logger.info(f"已处理 {total_count}/{len(files_to_process)} 个股文件")

    logger.info(f"个股导入完成，共处理 {total_count} 个文件")


async def import_children(manager: PostgresDatabaseManager, children_dir: Path, data_root: Path, batch_id: str, batch_size=500, limit=None, resume=True):
    logger.info(f"开始导入题材树数据从 {children_dir}")
    files = [f for f in children_dir.glob("*.jsonl") if not f.name.startswith('.')]
    if limit:
        files = files[:limit]
        logger.info(f"限制处理前 {limit} 个文件")

    files_to_process = await get_pending_files(manager, 'children', files, batch_id, data_root, resume)
    if not files_to_process:
        logger.info("没有需要处理的 children 文件")
        return

    file_count = 0
    for file in files_to_process:
        file_path = str(file.relative_to(data_root))
        try:
            await mark_file_start(manager, file_path, 'children', batch_id, data_root)

            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            all_nodes = []
            all_maps = []
            row_count = 0  # 记录成功解析的行数
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    node_data = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.error(f"文件 {file.name} 第 {line_num} 行 JSON 解析失败: {e}")
                    await log_import_error(manager, file.name, None, "JSON_DECODE_ERROR", str(e), line)
                    continue

                dto, errs = parse_node(node_data)
                if errs:
                    logger.warning(f"文件 {file.name} 第 {line_num} 行解析错误: {errs}")
                    await log_import_error(manager, file.name, None, "PARSE_ERROR", '\n'.join(errs), node_data)
                    # 即使有错误，只要 dto 非空，就继续处理该行
                if dto:
                    nodes, maps = flatten_tree(dto)
                    all_nodes.extend(nodes)
                    all_maps.extend(maps)
                    row_count += 1  # 此行成功产生至少一个节点
                else:
                    # 严重错误，dto 为 None，无法处理该行（记录但跳过）
                    logger.error(f"文件 {file.name} 第 {line_num} 行解析返回 None，无法处理")

            if not all_nodes and not all_maps:
                logger.warning(f"文件 {file.name} 无有效数据，跳过")
                await mark_file_failed(manager, file_path, batch_id, "No valid data")
                continue

            # 可选：添加调试日志
            logger.info(f"文件 {file.name} 解析后: {len(all_nodes)} 个节点, {len(all_maps)} 个映射")

            async with manager.pool.acquire() as conn:
                async with conn.transaction():
                    await batch_upsert_nodes(conn, all_nodes, batch_id, batch_size)
                    await batch_upsert_stock_maps(conn, all_maps, batch_id, batch_size)
                    await batch_upsert_theme_master(conn, all_nodes, batch_size)

            stat = file.stat()
            await mark_file_success(manager, file_path, batch_id, row_count, stat.st_size, datetime.fromtimestamp(stat.st_mtime))
            file_count += 1

            async with manager.pool.acquire() as conn:
                async with conn.transaction():
                    await batch_upsert_nodes(conn, all_nodes, batch_id, batch_size)
                    await batch_upsert_stock_maps(conn, all_maps, batch_id, batch_size)
                    await batch_upsert_theme_master(conn, all_nodes, batch_size)

                    # 验证插入是否成功
                    inserted = await conn.fetchval(
                        "SELECT COUNT(*) FROM jyhf_subject_node_staging WHERE ingest_batch_id = $1",
                        batch_id
                    )
                    logger.info(f"当前批次 staging 表记录数: {inserted}")

        except Exception as e:
            logger.exception(f"处理文件 {file} 时出错")
            await mark_file_failed(manager, file_path, batch_id, str(e))
            # 继续处理下一个文件

        if file_count % 10 == 0:
            logger.info(f"已处理 {file_count}/{len(files_to_process)} 个 children 文件")

    logger.info(f"题材树导入完成，共处理 {file_count} 个文件")


async def import_details(manager: PostgresDatabaseManager, details_dir: Path, data_root: Path, batch_id: str, batch_size=500, limit=None, resume=True):
    logger.info(f"开始导入题材详情从 {details_dir}")
    files = [f for f in details_dir.glob("*.jsonl") if not f.name.startswith('.')]
    if limit:
        files = files[:limit]
        logger.info(f"限制处理前 {limit} 个文件")

    files_to_process = await get_pending_files(manager, 'details', files, batch_id, data_root, resume)
    if not files_to_process:
        logger.info("没有需要处理的 details 文件")
        return

    total_rows = 0
    file_count = 0
    for file in files_to_process:
        file_path = str(file.relative_to(data_root))
        try:
            await mark_file_start(manager, file_path, 'details', batch_id, data_root)

            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            params = []
            row_count = 0
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.error(f"文件 {file.name} 第 {line_num} 行 JSON 解析失败: {e}")
                    await log_import_error(manager, file.name, None, "JSON_DECODE_ERROR", str(e), line)
                    continue

                if isinstance(data, dict) and 'data' in data:
                    data = data['data']
                subject_id = data.get('subjectId')
                detail_html = data.get('detail')
                if not subject_id or not detail_html:
                    continue

                params.append((str(subject_id), detail_html))
                row_count += 1
                if len(params) >= batch_size:
                    async with manager.pool.acquire() as conn:
                        async with conn.transaction():
                            await conn.executemany("""
                                INSERT INTO subject_detail (subject_key, detail_html, detail_version, created_at, updated_at)
                                VALUES ($1,$2,1,NOW(),NOW())
                                ON CONFLICT (subject_key) DO UPDATE SET
                                    detail_html = EXCLUDED.detail_html,
                                    detail_version = EXCLUDED.detail_version,
                                    updated_at = NOW()
                            """, params)
                    params.clear()

            if params:
                async with manager.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.executemany("""
                            INSERT INTO subject_detail (subject_key, detail_html, detail_version, created_at, updated_at)
                            VALUES ($1,$2,1,NOW(),NOW())
                            ON CONFLICT (subject_key) DO UPDATE SET
                                detail_html = EXCLUDED.detail_html,
                                detail_version = EXCLUDED.detail_version,
                                updated_at = NOW()
                        """, params)

            stat = file.stat()
            await mark_file_success(manager, file_path, batch_id, row_count, stat.st_size, datetime.fromtimestamp(stat.st_mtime))
            file_count += 1
            total_rows += row_count
        except Exception as e:
            logger.exception(f"处理文件 {file} 时出错")
            await mark_file_failed(manager, file_path, batch_id, str(e))

        if file_count % 10 == 0:
            logger.info(f"已处理 {file_count}/{len(files_to_process)} 个 details 文件，累计 {total_rows} 条")

    logger.info(f"题材详情导入完成，共 {total_rows} 条")


async def import_history(manager: PostgresDatabaseManager, history_dir: Path, data_root: Path, batch_id: str, batch_size=1000, limit=None, resume=True):
    logger.info(f"开始导入题材历史榜单从 {history_dir}")
    files = [f for f in history_dir.glob("*.jsonl") if not f.name.startswith('.')]
    if limit:
        files = files[:limit]
        logger.info(f"限制处理前 {limit} 个文件")

    files_to_process = await get_pending_files(manager, 'history', files, batch_id, data_root, resume)
    if not files_to_process:
        logger.info("没有需要处理的 history 文件")
        return

    total_rows = 0
    file_count = 0
    upsert_sql = """
        INSERT INTO subject_rank_daily (
            subject_key, rank_date, heat, heat_name, pct_chg, his_pct_chg, red, description, source_system, created_at, updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'jyhf',NOW(),NOW())
        ON CONFLICT (subject_key, rank_date) DO UPDATE SET
            heat = EXCLUDED.heat,
            heat_name = EXCLUDED.heat_name,
            pct_chg = EXCLUDED.pct_chg,
            his_pct_chg = EXCLUDED.his_pct_chg,
            red = EXCLUDED.red,
            description = EXCLUDED.description,
            updated_at = NOW()
    """

    for file in files_to_process:
        file_path = str(file.relative_to(data_root))
        try:
            await mark_file_start(manager, file_path, 'history', batch_id, data_root)

            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            params = []
            row_count = 0
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.error(f"文件 {file.name} 第 {line_num} 行 JSON 解析失败: {e}")
                    await log_import_error(manager, file.name, None, "JSON_DECODE_ERROR", str(e), line)
                    continue

                # 处理可能的外层 data 或 rows 字段
                if isinstance(row, dict):
                    if 'rows' in row:
                        rows_data = row.get('rows', [])
                        for r in rows_data:
                            p = extract_history_params(r)
                            if p:
                                params.append(p)
                                row_count += 1
                    else:
                        p = extract_history_params(row)
                        if p:
                            params.append(p)
                            row_count += 1
                elif isinstance(row, list):
                    for r in row:
                        p = extract_history_params(r)
                        if p:
                            params.append(p)
                            row_count += 1
                else:
                    continue

                if len(params) >= batch_size:
                    async with manager.pool.acquire() as conn:
                        async with conn.transaction():
                            await conn.executemany(upsert_sql, params)
                    total_rows += len(params)
                    params.clear()

            if params:
                async with manager.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.executemany(upsert_sql, params)
                total_rows += len(params)

            stat = file.stat()
            await mark_file_success(manager, file_path, batch_id, row_count, stat.st_size, datetime.fromtimestamp(stat.st_mtime))
            file_count += 1
        except Exception as e:
            logger.exception(f"处理文件 {file} 时出错")
            await mark_file_failed(manager, file_path, batch_id, str(e))

        if file_count % 10 == 0:
            logger.info(f"已处理 {file_count}/{len(files_to_process)} 个 history 文件，累计 {total_rows} 条记录")

    logger.info(f"历史榜单导入完成，共 {total_rows} 条")


def extract_history_params(row):
    """从一行记录中提取参数元组，返回 None 如果必要字段缺失，并进行类型转换"""
    subject_id = row.get('subjectId')
    rank_date_str = row.get('rankDate')
    if not subject_id or not rank_date_str:
        return None
    try:
        rank_date = datetime.strptime(rank_date_str.split(' ')[0], '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        logger.warning(f"无效的 rank_date: {rank_date_str}")
        return None

    heat = row.get('heat')
    if heat is not None:
        try:
            heat = int(heat)
        except (ValueError, TypeError):
            heat = None

    heat_name = row.get('heatName')
    pct_chg = row.get('pctChg')
    if pct_chg is not None:
        try:
            pct_chg = float(pct_chg)
        except (ValueError, TypeError):
            pct_chg = None

    his_pct_chg = row.get('hisPctChg')
    if his_pct_chg is not None:
        try:
            his_pct_chg = float(his_pct_chg)
        except (ValueError, TypeError):
            his_pct_chg = None

    red = bool(row.get('red', False))
    description = row.get('description')
    return (str(subject_id), rank_date, heat, heat_name, pct_chg, his_pct_chg, red, description)


# ==================== 主流程 ====================

async def main():
    parser = argparse.ArgumentParser(description="导入久赢恒丰数据到 PostgreSQL（优化版 + 断点续传）")
    parser.add_argument("--data-dir", type=str, default="theme_data_complete",
                        help="数据根目录")
    parser.add_argument("--batch-id", type=str, default=None,
                        help="导入批次ID（默认自动生成）")
    parser.add_argument("--skip-tables", action="store_true", help="跳过建表/迁移")
    parser.add_argument("--skip-stocks", action="store_true", help="跳过个股导入")
    parser.add_argument("--skip-children", action="store_true", help="跳过题材树导入")
    parser.add_argument("--skip-details", action="store_true", help="跳过题材详情导入")
    parser.add_argument("--skip-history", action="store_true", help="跳过历史榜单导入")
    parser.add_argument("--batch-size", type=int, default=500, help="批量写入大小")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的文件数量（用于测试）")
    parser.add_argument("--resume", action="store_true", default=True, help="启用断点续传（跳过已成功文件）")
    parser.add_argument("--check", action="store_true", help="仅检查导入完整性，不执行导入")
    args = parser.parse_args()

    data_root = Path(args.data_dir).resolve()
    if not data_root.exists():
        logger.error(f"数据目录 {data_root} 不存在")
        sys.exit(1)

    batch_id = args.batch_id or datetime.now().strftime("%Y%m%d%H%M%S")
    logger.info(f"批次ID: {batch_id}")

    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        if not args.skip_tables and not args.check:
            await ensure_tables(manager, batch_id)

        # 如果是检查模式，执行检查并退出
        if args.check:
            await check_import(manager, batch_id)
            return

        # 正常导入
        if not args.skip_stocks:
            stock_dir = data_root / "stock_details"
            if stock_dir.exists():
                await import_stocks(manager, stock_dir, data_root, batch_id, args.batch_size, args.limit, args.resume)
            else:
                logger.warning(f"目录 {stock_dir} 不存在，跳过")

        if not args.skip_children:
            children_dir = data_root / "children"
            if children_dir.exists():
                await import_children(manager, children_dir, data_root, batch_id, args.batch_size, args.limit, args.resume)
            else:
                logger.warning(f"目录 {children_dir} 不存在，跳过")

        if not args.skip_details:
            details_dir = data_root / "details"
            if details_dir.exists():
                await import_details(manager, details_dir, data_root, batch_id, args.batch_size, args.limit, args.resume)
            else:
                logger.warning(f"目录 {details_dir} 不存在，跳过")

        if not args.skip_history:
            history_dir = data_root / "history"
            if history_dir.exists():
                await import_history(manager, history_dir, data_root, batch_id, args.batch_size, args.limit, args.resume)
            else:
                logger.warning(f"目录 {history_dir} 不存在，跳过")

        logger.info("✅ 所有导入任务完成！")

    except Exception as e:
        logger.exception("导入过程中发生致命错误")
        raise
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
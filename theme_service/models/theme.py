from theme_service.database import get_conn
import logging

logger = logging.getLogger(__name__)

async def create_theme_table():
    conn = await get_conn()
    try:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS theme_master (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            category VARCHAR(50),
            keywords TEXT[],
            description TEXT,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT now()
        );
        """)
        logger.info("theme_master table ready")
    finally:
        await conn.close()


async def fetch_all_themes():
    conn = await get_conn()
    try:
        rows = await conn.fetch("SELECT * FROM theme_master WHERE status='active'")
        return [dict(r) for r in rows]
    finally:
        await conn.close()

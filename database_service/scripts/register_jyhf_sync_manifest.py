#!/usr/bin/env python3
"""
将本地 manifest 注册到数据库同步状态表。
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager


def get_postgres_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="注册 jyhf sync manifest 到数据库")
    parser.add_argument("--manifest", required=True, help="manifest json 路径")
    parser.add_argument("--status", default="collected", help="批次状态")
    return parser.parse_args()


def _to_datetime(value):
    if value in (None, "", "null"):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


async def main_async() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch_id = manifest["batch_id"]
    files = manifest.get("files", [])

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        async with manager.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO jyhf_sync_batch (
                    batch_id, sync_scope, status, started_at, finished_at,
                    subject_count, changed_subject_count, file_count, changed_file_count,
                    manifest_path, notes, updated_at
                ) VALUES (
                    $1, 'incremental', $2, NOW(), NOW(),
                    $3, 0, $4, 0, $5, $6, NOW()
                )
                ON CONFLICT (batch_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    subject_count = EXCLUDED.subject_count,
                    file_count = EXCLUDED.file_count,
                    manifest_path = EXCLUDED.manifest_path,
                    notes = EXCLUDED.notes,
                    updated_at = NOW()
                """,
                batch_id,
                args.status,
                int(manifest.get("subject_count", 0)),
                len(files),
                str(manifest_path),
                json.dumps({"wanted_types": manifest.get("wanted_types", [])}, ensure_ascii=False),
            )

            if files:
                await conn.executemany(
                    """
                    INSERT INTO jyhf_sync_file_manifest (
                        batch_id, file_path, data_type, subject_key, file_hash, file_size,
                        source_updated_at, sync_status, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6,
                        $7::timestamp, 'collected', NOW()
                    )
                    ON CONFLICT (batch_id, file_path) DO UPDATE SET
                        data_type = EXCLUDED.data_type,
                        subject_key = EXCLUDED.subject_key,
                        file_hash = EXCLUDED.file_hash,
                        file_size = EXCLUDED.file_size,
                        source_updated_at = EXCLUDED.source_updated_at,
                        sync_status = EXCLUDED.sync_status,
                        updated_at = NOW()
                    """,
                    [
                        (
                            batch_id,
                            row["file_path"],
                            row["data_type"],
                            row.get("subject_key"),
                            row.get("file_hash"),
                            row.get("file_size"),
                            _to_datetime(row.get("source_updated_at")),
                        )
                        for row in files
                    ],
                )

                subject_rows = {}
                for row in files:
                    subject_key = row.get("subject_key")
                    if not subject_key:
                        continue
                    subject_rows[str(subject_key)] = {
                        "last_file_hash": row.get("file_hash"),
                        "types": [],
                    }
                for row in files:
                    subject_key = row.get("subject_key")
                    if not subject_key:
                        continue
                    subject_rows[str(subject_key)]["types"].append(row.get("data_type"))

                if subject_rows:
                    await conn.executemany(
                        """
                        INSERT INTO jyhf_sync_subject_state (
                            subject_key, last_batch_id, last_success_at, last_file_hash,
                            last_data_types, status, updated_at
                        ) VALUES (
                            $1, $2, NOW(), $3, $4::jsonb, 'collected', NOW()
                        )
                        ON CONFLICT (subject_key) DO UPDATE SET
                            last_batch_id = EXCLUDED.last_batch_id,
                            last_file_hash = EXCLUDED.last_file_hash,
                            last_data_types = EXCLUDED.last_data_types,
                            status = EXCLUDED.status,
                            updated_at = NOW()
                        """,
                        [
                            (
                                subject_key,
                                batch_id,
                                payload["last_file_hash"],
                                json.dumps(sorted(set(payload["types"])), ensure_ascii=False),
                            )
                            for subject_key, payload in subject_rows.items()
                        ],
                    )

        print(f"[OK] registered manifest batch_id={batch_id} files={len(files)}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

#!/usr/bin/env python3
"""
主线周期判定V2系统数据库迁移脚本

用途：
- 执行主题周期判定V2系统表结构创建
- 检查现有表结构并做增量更新
- 支持回滚和验证功能

表结构内容：
1. theme_cycle_evidence_daily - 证据表（四层证据体系）
2. theme_cycle_judgement_v2 - 判定表（状态机追踪）
3. weak_to_strong_candidate_pool字段扩展
4. theme_cycle_judgement字段扩展

使用方式：
  python run_theme_cycle_migration.py [--dry-run] [--verify]

注意：需要数据库连接权限
"""

import asyncio
import asyncpg
import argparse
import sys
from datetime import datetime
from pathlib import Path

from stock_service.config import StockServiceConfig


class ThemeCycleMigration:
    """主线周期判定V2系统迁移管理器"""

    def __init__(self, config: StockServiceConfig):
        self.config = config
        self.pool: asyncpg.Pool | None = None
        self.migration_path = Path(__file__).parent.parent / "database" / "migrations"
        self.migration_file = self.migration_path / "add_theme_cycle_v2_tables.sql"

    async def connect(self) -> None:
        """创建数据库连接池"""
        print(f"🔗 连接数据库 {self.config.postgres_host}:{self.config.postgres_port}/{self.config.postgres_database}")
        self.pool = await asyncpg.create_pool(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            database=self.config.postgres_database,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            min_size=1,
            max_size=3,
        )

    async def close(self) -> None:
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def execute_migration(self, dry_run: bool = False) -> bool:
        """执行迁移脚本"""
        if not self.migration_file.exists():
            print(f"❌ 迁移文件不存在: {self.migration_file}")
            return False

        try:
            migration_sql = self.migration_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"❌ 读取迁移文件失败: {e}")
            return False

        print(f"📄 读取迁移脚本: {self.migration_file.name}")
        print(f"📏 脚本大小: {len(migration_sql)} 字符")

        if dry_run:
            print("🔍 干跑模式 - 仅显示SQL语句:")
            print("-" * 60)
            print(migration_sql[:2000] + ("..." if len(migration_sql) > 2000 else ""))
            print("-" * 60)
            return True

        if not self.pool:
            return False

        print("🚀 开始执行迁移...")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    await conn.execute(migration_sql)
                    print("✅ 迁移脚本执行完成")
                    return True
                except Exception as e:
                    print(f"❌ 迁移执行失败: {e}")
                    return False

    async def verify_tables(self) -> dict:
        """验证迁移后的表结构"""
        if not self.pool:
            return {}

        tables_to_check = [
            "theme_cycle_evidence_daily",
            "theme_cycle_judgement_v2",
        ]

        results = {}
        async with self.pool.acquire() as conn:
            for table in tables_to_check:
                # 检查表是否存在
                exists_sql = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = $1
                )
                """
                exists = await conn.fetchval(exists_sql, table)

                if exists:
                    # 检查行数
                    count_sql = f"SELECT COUNT(*) FROM {table}"
                    try:
                        count = await conn.fetchval(count_sql)
                    except:
                        count = 0

                    # 检查列信息
                    columns_sql = """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = $1
                    ORDER BY ordinal_position
                    """
                    columns = await conn.fetch(columns_sql, table)

                    results[table] = {
                        "exists": True,
                        "row_count": count,
                        "column_count": len(columns),
                        "columns": [(c["column_name"], c["data_type"]) for c in columns[:5]],  # 只显示前5列
                    }
                else:
                    results[table] = {"exists": False}

        return results

    async def check_candidate_pool_columns(self) -> list:
        """检查候选池扩展字段"""
        if not self.pool:
            return []

        new_columns = [
            "cycle_state",
            "mainline_strength_score",
            "fade_watch",
            "fade_confirmed",
            "pool_entry_type",
            "judgement_id",
            "cycle_rule_version"
        ]

        missing = []
        async with self.pool.acquire() as conn:
            columns_sql = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'weak_to_strong_candidate_pool'
            """
            rows = await conn.fetch(columns_sql)
            existing_columns = {row["column_name"] for row in rows}

            for col in new_columns:
                if col not in existing_columns:
                    missing.append(col)

        return missing

    def print_results(self, verify_results: dict, missing_columns: list) -> None:
        """打印验证结果"""
        print("\n" + "="*60)
        print("迁移验证结果")
        print("="*60)

        for table, info in verify_results.items():
            if info.get("exists"):
                print(f"📊 {table}:")
                print(f"   ✓ 表存在")
                print(f"   📈 行数: {info.get('row_count', 0)}")
                print(f"   🗂️  列数: {info.get('column_count', 0)}")
                if info.get("columns"):
                    print(f"   前5列: {', '.join([f'{name}({type})' for name, type in info['columns'][:3]])}...")
            else:
                print(f"❌ {table}: 表不存在")

        print()
        print("🔍 候选池扩展字段检查:")
        if not missing_columns:
            print("   ✅ 所有扩展字段已存在")
        else:
            print(f"   ⚠ 缺失字段: {missing_columns}")
            print("   ℹ 可能需要重新执行迁移或手动添加")

        print("="*60)


async def main():
    parser = argparse.ArgumentParser(description="主线周期判定V2系统数据库迁移")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式，不实际执行SQL"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="迁移后验证表结构"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="数据库主机（覆盖配置）"
    )
    parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="数据库名（覆盖配置）"
    )
    args = parser.parse_args()

    print("主线周期判定V2系统数据库迁移")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 加载配置
    config = StockServiceConfig()
    if args.host:
        config.postgres_host = args.host
    if args.database:
        config.postgres_database = args.database

    migration = ThemeCycleMigration(config)

    try:
        await migration.connect()

        # 执行迁移
        success = await migration.execute_migration(args.dry_run)
        if not success:
            sys.exit(1)

        # 验证
        if args.verify or not args.dry_run:
            print("\n🔍 开始验证迁移结果...")
            verify_results = await migration.verify_tables()
            missing_columns = await migration.check_candidate_pool_columns()
            migration.print_results(verify_results, missing_columns)

            # 检查是否有表创建失败
            failed_tables = [t for t, info in verify_results.items() if not info.get("exists")]
            if failed_tables and not args.dry_run:
                print(f"\n❌ 表创建失败: {failed_tables}")
                sys.exit(1)

        print("\n🎉 迁移完成!")

    except Exception as e:
        print(f"❌ 迁移过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await migration.close()


if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
主线周期判定 P0 协议：交易日数据可用性校验脚本

用途：
- 检查指定交易日（默认今日）的主题周期判定所需数据是否完备
- 验证表结构、关键字段、映射关系
- 输出缺失项和警告，用于每日定时任务

校验范围：
1. 基础表结构：theme_cycle_evidence_daily, theme_cycle_judgement_v2 是否存在
2. 关键字段：subject_key, trade_date 等必填字段
3. 数据完整性：指定交易日是否有证据记录、判定记录
4. 映射一致性：subject_key 能否关联到 theme_master
5. 版本一致性：evidence_schema_version 是否符合预期

使用方式：
  python check_data_availability.py [--trade-date YYYY-MM-DD] [--verbose]

输出：
  通过/失败，失败时列出缺失项
"""

import asyncio
import asyncpg
import argparse
import sys
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

from stock_service.config import StockServiceConfig


class DataAvailabilityChecker:
    """数据可用性校验器"""

    REQUIRED_TABLES = [
        "theme_cycle_evidence_daily",
        "theme_cycle_judgement_v2",
        "weak_to_strong_candidate_pool",
        "theme_master",
        "subject_stock_daily_snapshot",
    ]

    EVIDENCE_REQUIRED_COLUMNS = [
        "trade_date",
        "subject_key",
        "theme_name",
        "event_count_3d",
        "leader_alive_score",
        "board_stock_count",
        "theme_ret_3d",
        "mainline_strength_score",
        "fade_risk_score",
        "evidence_json",
        "evidence_schema_version",
    ]

    JUDGEMENT_REQUIRED_COLUMNS = [
        "trade_date",
        "subject_key",
        "final_cycle_state",
        "final_mainline_alive",
        "fade_watch",
        "fade_confirmed",
        "mainline_strength_score",
        "fade_risk_score",
        "rule_reasons",
        "evidence_refs",
    ]

    def __init__(self, config: StockServiceConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []

    async def connect(self) -> None:
        """创建数据库连接池"""
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

    async def check_table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        if not self.pool:
            return False
        async with self.pool.acquire() as conn:
            sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = $1
            )
            """
            exists = await conn.fetchval(sql, table_name)
            return bool(exists)

    async def check_columns_exist(self, table_name: str, columns: List[str]) -> List[str]:
        """检查表中是否存在指定列，返回缺失的列名"""
        if not self.pool:
            return columns.copy()
        async with self.pool.acquire() as conn:
            sql = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = $1
            """
            rows = await conn.fetch(sql, table_name)
            existing_columns = {row["column_name"] for row in rows}
            missing = [col for col in columns if col not in existing_columns]
            return missing

    async def check_data_for_date(self, trade_date: date) -> Dict[str, Any]:
        """检查指定交易日的数据完整性"""
        if not self.pool:
            return {}

        result = {
            "evidence_count": 0,
            "judgement_count": 0,
            "candidate_count": 0,
            "mapping_errors": [],
            "schema_version_errors": [],
        }

        async with self.pool.acquire() as conn:
            # 1. 证据表记录数
            evidence_count = await conn.fetchval(
                "SELECT COUNT(*) FROM theme_cycle_evidence_daily WHERE trade_date = $1",
                trade_date
            )
            result["evidence_count"] = evidence_count or 0

            # 2. 判定表记录数
            judgement_count = await conn.fetchval(
                "SELECT COUNT(*) FROM theme_cycle_judgement_v2 WHERE trade_date = $1",
                trade_date
            )
            result["judgement_count"] = judgement_count or 0

            # 3. 候选池记录数（仅检查是否有扩展字段）
            candidate_count = await conn.fetchval(
                "SELECT COUNT(*) FROM weak_to_strong_candidate_pool WHERE trade_date = $1",
                trade_date
            )
            result["candidate_count"] = candidate_count or 0

            # 4. 检查证据表schema版本
            schema_rows = await conn.fetch(
                "SELECT DISTINCT evidence_schema_version FROM theme_cycle_evidence_daily WHERE trade_date = $1",
                trade_date
            )
            versions = {row["evidence_schema_version"] for row in schema_rows if row["evidence_schema_version"]}
            if len(versions) > 1:
                result["schema_version_errors"].append(f"多个schema版本共存: {versions}")
            elif versions and next(iter(versions)) != "theme_cycle_evidence_schema.v1":
                result["schema_version_errors"].append(f"非预期schema版本: {next(iter(versions))}")

            # 5. 检查主题映射
            mapping_sql = """
            SELECT e.subject_key, COUNT(m.subject_key) as master_count
            FROM theme_cycle_evidence_daily e
            LEFT JOIN theme_master m ON e.subject_key = m.subject_key
            WHERE e.trade_date = $1
            GROUP BY e.subject_key
            HAVING COUNT(m.subject_key) = 0
            """
            missing_master = await conn.fetch(mapping_sql, trade_date)
            if missing_master:
                missing_keys = [row["subject_key"] for row in missing_master]
                result["mapping_errors"].extend(missing_keys)

        return result

    async def run_checks(self, trade_date: date, verbose: bool = False) -> bool:
        """执行完整校验流程"""
        all_passed = True

        # 1. 检查表结构
        print(f"🔍 检查表结构...")
        for table in self.REQUIRED_TABLES:
            if await self.check_table_exists(table):
                if verbose:
                    print(f"  ✓ {table} 表存在")
            else:
                print(f"  ✗ {table} 表缺失")
                self.errors.append(f"表缺失: {table}")
                all_passed = False

        # 2. 检查证据表字段
        print(f"🔍 检查证据表字段...")
        missing_evidence_cols = await self.check_columns_exist(
            "theme_cycle_evidence_daily", self.EVIDENCE_REQUIRED_COLUMNS
        )
        if not missing_evidence_cols:
            if verbose:
                print(f"  ✓ theme_cycle_evidence_daily 字段完整")
        else:
            print(f"  ✗ theme_cycle_evidence_daily 缺失字段: {missing_evidence_cols}")
            self.errors.append(f"证据表字段缺失: {missing_evidence_cols}")
            all_passed = False

        # 3. 检查判定表字段
        print(f"🔍 检查判定表字段...")
        missing_judgement_cols = await self.check_columns_exist(
            "theme_cycle_judgement_v2", self.JUDGEMENT_REQUIRED_COLUMNS
        )
        if not missing_judgement_cols:
            if verbose:
                print(f"  ✓ theme_cycle_judgement_v2 字段完整")
        else:
            print(f"  ✗ theme_cycle_judgement_v2 缺失字段: {missing_judgement_cols}")
            self.errors.append(f"判定表字段缺失: {missing_judgement_cols}")
            all_passed = False

        # 4. 检查候选池扩展字段
        print(f"🔍 检查候选池扩展字段...")
        candidate_extra_cols = ["cycle_state", "fade_watch", "fade_confirmed", "pool_entry_type"]
        missing_candidate_cols = await self.check_columns_exist(
            "weak_to_strong_candidate_pool", candidate_extra_cols
        )
        if not missing_candidate_cols:
            if verbose:
                print(f"  ✓ weak_to_strong_candidate_pool 扩展字段完整")
        else:
            print(f"  ⚠ weak_to_strong_candidate_pool 缺失扩展字段: {missing_candidate_cols}")
            self.warnings.append(f"候选池扩展字段缺失: {missing_candidate_cols}")
            # 扩展字段缺失不视为致命错误

        # 5. 检查指定交易日数据
        print(f"🔍 检查交易日 {trade_date} 数据...")
        date_results = await self.check_data_for_date(trade_date)

        evidence_count = date_results.get("evidence_count", 0)
        judgement_count = date_results.get("judgement_count", 0)

        if evidence_count > 0:
            if verbose:
                print(f"  ✓ 证据表有 {evidence_count} 条记录")
        else:
            print(f"  ⚠ 证据表无记录（可能尚未生成）")
            self.warnings.append(f"证据表无记录: {trade_date}")

        if judgement_count > 0:
            if verbose:
                print(f"  ✓ 判定表有 {judgement_count} 条记录")
        else:
            print(f"  ⚠ 判定表无记录（可能尚未生成）")
            self.warnings.append(f"判定表无记录: {trade_date}")

        # 6. 检查映射错误
        mapping_errors = date_results.get("mapping_errors", [])
        if mapping_errors:
            print(f"  ⚠ 主题映射缺失: {len(mapping_errors)} 个主题")
            if verbose:
                for key in mapping_errors[:5]:
                    print(f"    - {key}")
            self.warnings.append(f"主题映射缺失: {len(mapping_errors)} 个")

        # 7. 检查schema版本
        schema_errors = date_results.get("schema_version_errors", [])
        if schema_errors:
            print(f"  ✗ Schema版本错误: {schema_errors}")
            self.errors.extend(schema_errors)
            all_passed = False

        return all_passed

    def print_summary(self) -> None:
        """打印校验总结"""
        print("\n" + "="*60)
        print("数据可用性校验总结")
        print("="*60)

        if self.errors:
            print("❌ 错误项:")
            for err in self.errors:
                print(f"  • {err}")

        if self.warnings:
            print("⚠️  警告项:")
            for warn in self.warnings:
                print(f"  • {warn}")

        if not self.errors and not self.warnings:
            print("✅ 所有检查通过")
        elif not self.errors:
            print("✅ 基本通过（存在警告但不影响运行）")
        else:
            print("❌ 存在错误，请修复后重试")

        print("="*60)


async def main():
    parser = argparse.ArgumentParser(description="主线周期判定数据可用性校验")
    parser.add_argument(
        "--trade-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today() - timedelta(days=1),  # 默认检查前一天
        help="交易日 (格式: YYYY-MM-DD，默认前一天)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细信息"
    )
    args = parser.parse_args()

    print(f"主线周期判定 P0 数据可用性校验")
    print(f"交易日: {args.trade_date}")
    print()

    checker = DataAvailabilityChecker(StockServiceConfig())
    try:
        await checker.connect()
        passed = await checker.run_checks(args.trade_date, args.verbose)
        checker.print_summary()

        if not passed:
            sys.exit(1)
        elif checker.warnings:
            sys.exit(0)  # 警告不算失败
        else:
            sys.exit(0)

    except Exception as e:
        print(f"❌ 校验过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await checker.close()


if __name__ == "__main__":
    asyncio.run(main())
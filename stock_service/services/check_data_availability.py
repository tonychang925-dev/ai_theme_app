#!/usr/bin/env python3
"""
四层证据数据可用性检查脚本

P0阶段：证据源补齐与基础校验
功能：检查四层证据数据完整性，定义数据状态分级（ok、partial、missing），记录异常详情
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from typing import Dict, List, Optional, Any, Tuple
import asyncpg


class DataAvailabilityChecker:
    """数据可用性检查器

    检查四层证据相关表的字段完整性和数据质量
    """

    def __init__(self, config=None):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        """确保数据库连接池存在"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host='localhost',
                port=5432,
                user='postgres',
                password='postgres',
                database='stock_data_test',
                min_size=1,
                max_size=5
            )
        return self._pool

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def check_all_tables(self, trade_date: date) -> Dict[str, Any]:
        """检查所有相关表的数据可用性"""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            results = {}

            # 1. 检查表是否存在
            table_status = await self._check_tables_existence(conn)
            results["table_status"] = table_status

            # 2. 检查主题范围覆盖
            subject_coverage = await self._check_subject_coverage(conn, trade_date)
            results["subject_coverage"] = subject_coverage

            # 3. 检查四层证据字段
            evidence_field_status = await self._check_evidence_fields(conn, trade_date)
            results["evidence_field_status"] = evidence_field_status

            # 4. 计算总体数据状态
            overall_status = self._calculate_overall_status(results)
            results["overall_status"] = overall_status

            return results

    async def _check_tables_existence(self, conn: asyncpg.Connection) -> Dict[str, Any]:
        """检查相关表是否存在"""
        tables_to_check = [
            # 源表
            "subject_stock_daily_snapshot",
            "theme_mainline_judgement",
            "theme_cycle_judgement",
            "theme_news_daily",
            # V2证据表
            "theme_cycle_evidence_daily",
            "theme_cycle_judgement_v2"
        ]

        status = {}
        for table in tables_to_check:
            sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = $1
            )
            """
            exists = await conn.fetchval(sql, table)
            status[table] = {
                "exists": exists,
                "status": "ok" if exists else "missing"
            }

        return status

    async def _check_subject_coverage(self, conn: asyncpg.Connection, trade_date: date) -> Dict[str, Any]:
        """检查主题覆盖范围：各表有多少主题有数据"""
        # 获取当日所有主题
        sql = """
        SELECT DISTINCT subject_key
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1
        """
        rows = await conn.fetch(sql, trade_date)
        all_subjects = [row["subject_key"] for row in rows]
        total_subjects = len(all_subjects)

        if total_subjects == 0:
            return {
                "total_subjects": 0,
                "coverage": {},
                "status": "missing"
            }

        # 检查各表的主题覆盖
        tables_to_check = [
            "theme_mainline_judgement",
            "theme_cycle_judgement",
            "theme_cycle_evidence_daily",
            "theme_cycle_judgement_v2"
        ]

        coverage = {}
        for table in tables_to_check:
            # 先检查表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = $1
                )
            """, table)

            if not table_exists:
                coverage[table] = {
                    "subject_count": 0,
                    "coverage_ratio": 0.0,
                    "status": "table_missing"
                }
                continue

            # 查询该表当日有多少主题
            sql = f"""
            SELECT COUNT(DISTINCT subject_key) as subject_count
            FROM {table}
            WHERE trade_date = $1
            """
            subject_count = await conn.fetchval(sql, trade_date) or 0
            coverage_ratio = subject_count / total_subjects if total_subjects > 0 else 0.0

            # 确定状态
            if coverage_ratio >= 0.8:
                status = "ok"
            elif coverage_ratio >= 0.3:
                status = "partial"
            else:
                status = "missing"

            coverage[table] = {
                "subject_count": subject_count,
                "coverage_ratio": round(coverage_ratio, 3),
                "status": status
            }

        return {
            "total_subjects": total_subjects,
            "coverage": coverage,
            "status": "partial" if total_subjects > 0 else "missing"
        }

    async def _check_evidence_fields(self, conn: asyncpg.Connection, trade_date: date) -> Dict[str, Any]:
        """检查四层证据字段的数据可用性"""

        # 定义四层证据字段映射
        evidence_layers = {
            "event_layer": {
                "table": "theme_mainline_judgement",
                "fields": [
                    "event_count_3d",
                    "event_count_7d",
                    "strong_event_count_7d",
                    "event_recency_days"
                ]
            },
            "leader_layer": {
                "table": "theme_cycle_judgement",
                "fields": [
                    "leader_stock_id",
                    "leader_stock_name",
                    "board_stock_count",
                    "limit_down_count",
                    "red_ratio",
                    "big_drop_ratio",
                    "front_row_strength_score",
                    "relay_strength_score",
                    "front_row_survival_ratio"
                ]
            },
            "board_structure_layer": {
                "table": "theme_cycle_judgement",  # 与leader_layer共用表
                "fields": [
                    "limit_up_count",
                    "limit_down_count",
                    "red_ratio",
                    "big_drop_ratio",
                    "front_row_strength_score"
                ]
            },
            "kline_layer": {
                "table": "theme_cycle_evidence_daily",
                "fields": [
                    "theme_ret_3d",
                    "theme_ret_5d",
                    "theme_ret_10d",
                    "above_ma5",
                    "above_ma10",
                    "above_ma20",
                    "break_start_pivot",
                    "volume_breakdown_flag",
                    "theme_support_score"
                ]
            }
        }

        results = {}
        for layer_name, layer_info in evidence_layers.items():
            table = layer_info["table"]
            fields = layer_info["fields"]

            # 检查表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = $1
                )
            """, table)

            if not table_exists:
                results[layer_name] = {
                    "table_exists": False,
                    "status": "table_missing",
                    "field_coverage": {},
                    "summary": "表不存在"
                }
                continue

            # 检查字段是否存在
            field_status = {}
            for field in fields:
                field_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = $1
                        AND column_name = $2
                    )
                """, table, field)

                if not field_exists:
                    field_status[field] = {
                        "exists": False,
                        "status": "missing"
                    }
                    continue

                # 检查字段是否有非空数据
                sql = f"""
                SELECT
                    COUNT(*) as total_rows,
                    COUNT({field}) as non_null_count
                FROM {table}
                WHERE trade_date = $1
                """
                row = await conn.fetchrow(sql, trade_date)

                total_rows = row["total_rows"] or 0
                non_null_count = row["non_null_count"] or 0

                if total_rows == 0:
                    data_ratio = 0.0
                else:
                    data_ratio = non_null_count / total_rows

                # 确定字段状态
                if data_ratio >= 0.7:
                    field_status_value = "ok"
                elif data_ratio >= 0.3:
                    field_status_value = "partial"
                else:
                    field_status_value = "missing"

                field_status[field] = {
                    "exists": True,
                    "total_rows": total_rows,
                    "non_null_count": non_null_count,
                    "data_ratio": round(data_ratio, 3),
                    "status": field_status_value
                }

            # 计算层级的总体状态
            ok_count = sum(1 for f in field_status.values() if f.get("status") == "ok")
            partial_count = sum(1 for f in field_status.values() if f.get("status") == "partial")
            missing_count = sum(1 for f in field_status.values() if f.get("status") == "missing")
            total_fields = len(fields)

            if ok_count == total_fields:
                layer_status = "ok"
            elif missing_count == total_fields:
                layer_status = "missing"
            elif ok_count + partial_count >= total_fields * 0.5:
                layer_status = "partial"
            else:
                layer_status = "missing"

            results[layer_name] = {
                "table_exists": True,
                "status": layer_status,
                "field_coverage": field_status,
                "summary": {
                    "total_fields": total_fields,
                    "ok_fields": ok_count,
                    "partial_fields": partial_count,
                    "missing_fields": missing_count
                }
            }

        return results

    def _calculate_overall_status(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """计算总体数据状态"""
        table_status = results.get("table_status", {})
        subject_coverage = results.get("subject_coverage", {})
        evidence_field_status = results.get("evidence_field_status", {})

        # 检查关键表是否存在
        critical_tables = ["subject_stock_daily_snapshot", "theme_mainline_judgement", "theme_cycle_judgement"]
        critical_tables_missing = []
        for table in critical_tables:
            if not table_status.get(table, {}).get("exists", False):
                critical_tables_missing.append(table)

        # 检查证据层状态
        layer_statuses = []
        for layer_name, layer_info in evidence_field_status.items():
            layer_statuses.append(layer_info.get("status", "missing"))

        # 确定总体状态
        if critical_tables_missing:
            overall = "critical_missing"
        elif all(status == "ok" for status in layer_statuses):
            overall = "ok"
        elif any(status == "missing" for status in layer_statuses):
            overall = "partial_missing"
        else:
            overall = "partial"

        return {
            "status": overall,
            "critical_tables_missing": critical_tables_missing,
            "layer_status_summary": layer_statuses,
            "recommendations": self._generate_recommendations(overall, results)
        }

    def _generate_recommendations(self, overall_status: str, results: Dict[str, Any]) -> List[str]:
        """生成修复建议"""
        recommendations = []

        if overall_status == "critical_missing":
            recommendations.append("❌ 关键表缺失，请运行数据库迁移脚本")
            return recommendations

        # 检查表缺失
        table_status = results.get("table_status", {})
        for table, info in table_status.items():
            if not info.get("exists", False):
                recommendations.append(f"⚠️ 表 {table} 不存在，可能需要创建")

        # 检查主题覆盖
        subject_coverage = results.get("subject_coverage", {})
        coverage_info = subject_coverage.get("coverage", {})
        for table, cov in coverage_info.items():
            if cov.get("status") == "table_missing":
                recommendations.append(f"⚠️ 表 {table} 缺失，无法检查主题覆盖")
            elif cov.get("status") == "missing":
                recommendations.append(f"⚠️ 表 {table} 主题覆盖不足: {cov.get('coverage_ratio', 0)*100:.1f}%")

        # 检查证据字段
        evidence_field_status = results.get("evidence_field_status", {})
        for layer_name, layer_info in evidence_field_status.items():
            status = layer_info.get("status")
            if status == "table_missing":
                recommendations.append(f"⚠️ {layer_name} 依赖的表不存在")
            elif status == "missing":
                recommendations.append(f"⚠️ {layer_name} 字段数据严重缺失")
            elif status == "partial":
                field_cov = layer_info.get("field_coverage", {})
                missing_fields = [f for f, info in field_cov.items() if info.get("status") == "missing"]
                if missing_fields:
                    recommendations.append(f"⚠️ {layer_name} 缺失字段: {', '.join(missing_fields[:3])}")

        if not recommendations and overall_status == "ok":
            recommendations.append("✅ 所有检查通过，数据质量良好")

        return recommendations

    async def generate_report(self, trade_date: date, output_file: Optional[str] = None) -> Dict[str, Any]:
        """生成详细的数据可用性报告"""
        print(f"🔍 开始检查 {trade_date} 的数据可用性...")

        results = await self.check_all_tables(trade_date)

        # 打印摘要
        print(f"\n📊 数据可用性检查报告 - {trade_date}")
        print("=" * 60)

        # 1. 总体状态
        overall = results["overall_status"]
        print(f"总体状态: {overall['status'].upper()}")

        # 2. 表状态
        print(f"\n表状态:")
        table_status = results["table_status"]
        for table, info in table_status.items():
            status_icon = "✅" if info["status"] == "ok" else "❌"
            print(f"  {status_icon} {table}: {info['status']}")

        # 3. 主题覆盖
        print(f"\n主题覆盖:")
        subject_coverage = results["subject_coverage"]
        print(f"  总主题数: {subject_coverage.get('total_subjects', 0)}")
        coverage_info = subject_coverage.get("coverage", {})
        for table, cov in coverage_info.items():
            status_icon = "✅" if cov["status"] == "ok" else "⚠️" if cov["status"] == "partial" else "❌"
            ratio = cov.get("coverage_ratio", 0) * 100
            print(f"  {status_icon} {table}: {cov.get('subject_count', 0)} 主题 ({ratio:.1f}%) - {cov['status']}")

        # 4. 证据层状态
        print(f"\n四层证据状态:")
        evidence_field_status = results["evidence_field_status"]
        for layer_name, layer_info in evidence_field_status.items():
            status = layer_info.get("status", "missing")
            status_icon = "✅" if status == "ok" else "⚠️" if status == "partial" else "❌"
            print(f"  {status_icon} {layer_name}: {status}")

            # 打印字段详情（如果有问题）
            if status != "ok":
                field_cov = layer_info.get("field_coverage", {})
                for field, info in field_cov.items():
                    if info.get("status") != "ok":
                        data_ratio = info.get("data_ratio", 0) * 100
                        print(f"    - {field}: {info.get('status')} (数据填充率: {data_ratio:.1f}%)")

        # 5. 建议
        print(f"\n建议:")
        recommendations = overall.get("recommendations", [])
        if recommendations:
            for rec in recommendations:
                print(f"  {rec}")
        else:
            print(f"  ✅ 无问题，数据质量良好")

        print("=" * 60)

        # 保存报告到文件
        if output_file:
            report = {
                "trade_date": trade_date.isoformat(),
                "check_timestamp": date.today().isoformat(),
                "results": results
            }
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"📝 报告已保存到: {output_file}")

        return results


async def main():
    """主函数"""
    import sys
    from datetime import date

    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)  # 默认测试日期

    checker = DataAvailabilityChecker()
    try:
        # 生成报告
        await checker.generate_report(test_date, f"data_availability_report_{test_date}.json")
    finally:
        await checker.close()


if __name__ == "__main__":
    asyncio.run(main())
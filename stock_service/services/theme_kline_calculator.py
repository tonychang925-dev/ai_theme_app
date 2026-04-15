from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import asyncpg
import statistics


class ThemeKlineCalculator:
    """主题K线技术指标计算器

    基于成分股历史价格计算板块级K线技术指标
    实现四层证据体系中的"板块K线技术层"
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

    async def calculate_kline_metrics(self, trade_date: date, subject_key: str,
                                     lookback_days: int = 20) -> Dict[str, Any]:
        """计算指定主题的K线技术指标"""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 1. 获取主题成分股列表
            stock_ids = await self._get_subject_stocks(conn, trade_date, subject_key)
            if not stock_ids:
                return self._get_default_metrics()

            # 2. 获取板块指数数据（通过成分股聚合）
            theme_prices = await self._calculate_theme_index(conn, trade_date, subject_key,
                                                            stock_ids, lookback_days)
            if not theme_prices:
                return self._get_default_metrics()

            # 3. 计算各项技术指标
            metrics = self._calculate_technical_indicators(theme_prices)

            # 4. 计算支撑评分和破位标志
            support_metrics = await self._calculate_support_metrics(conn, trade_date,
                                                                   subject_key, stock_ids)
            metrics.update(support_metrics)

            return metrics

    async def _get_subject_stocks(self, conn: asyncpg.Connection,
                                 trade_date: date,
                                 subject_key: str) -> List[str]:
        """获取主题成分股列表"""
        sql = """
        SELECT DISTINCT stock_id
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1 AND subject_key = $2
        """
        rows = await conn.fetch(sql, trade_date, subject_key)
        return [row["stock_id"] for row in rows]

    async def _calculate_theme_index(self, conn: asyncpg.Connection,
                                    trade_date: date,
                                    subject_key: str,
                                    stock_ids: List[str],
                                    lookback_days: int) -> List[Dict[str, Any]]:
        """计算板块指数（成分股等权平均）"""
        if not stock_ids:
            return []

        # 构建股票ID列表条件
        stock_conditions = " OR ".join([f"stock_id = '{sid}'" for sid in stock_ids[:50]])  # 限制数量

        sql = f"""
        WITH stock_dates AS (
            SELECT DISTINCT trade_date
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1
              AND trade_date >= $1 - INTERVAL '{lookback_days + 5} days'
              AND ({stock_conditions})
            ORDER BY trade_date DESC
        ),
        stock_prices AS (
            SELECT
                s.trade_date,
                s.stock_id,
                s.close_price,
                s.pct_chg,
                s.volume
            FROM subject_stock_daily_snapshot s
            INNER JOIN stock_dates d ON s.trade_date = d.trade_date
            WHERE s.stock_id IN ({','.join([f"'{sid}'" for sid in stock_ids[:50]])})
        ),
        daily_avg AS (
            SELECT
                trade_date,
                AVG(close_price) AS avg_close,
                AVG(pct_chg) AS avg_pct_chg,
                SUM(volume) AS total_volume,
                COUNT(*) as stock_count
            FROM stock_prices
            GROUP BY trade_date
            HAVING COUNT(*) >= GREATEST(1, {len(stock_ids)} * 0.3)  -- 至少30%的成分股有数据
            ORDER BY trade_date DESC
        )
        SELECT * FROM daily_avg
        """

        try:
            rows = await conn.fetch(sql, trade_date)
            result = []
            for row in rows:
                result.append({
                    "trade_date": row["trade_date"],
                    "avg_close": float(row["avg_close"]) if row["avg_close"] else None,
                    "avg_pct_chg": float(row["avg_pct_chg"]) if row["avg_pct_chg"] else None,
                    "total_volume": float(row["total_volume"]) if row["total_volume"] else None,
                    "stock_count": int(row["stock_count"])
                })
            return result
        except Exception as e:
            print(f"⚠️ 计算板块指数失败: {e}")
            # 回退到简化计算
            return await self._simplified_theme_index(conn, trade_date, subject_key, lookback_days)

    async def _simplified_theme_index(self, conn: asyncpg.Connection,
                                     trade_date: date,
                                     subject_key: str,
                                     lookback_days: int) -> List[Dict[str, Any]]:
        """简化版板块指数计算（仅使用涨跌幅）"""
        sql = """
        SELECT
            trade_date,
            AVG(pct_chg) AS avg_pct_chg,
            COUNT(*) as stock_count
        FROM subject_stock_daily_snapshot
        WHERE trade_date <= $1
          AND trade_date >= $1 - INTERVAL $2 || ' days'
          AND subject_key = $3
          AND pct_chg IS NOT NULL
        GROUP BY trade_date
        HAVING COUNT(*) >= 1
        ORDER BY trade_date DESC
        """
        rows = await conn.fetch(sql, trade_date, lookback_days + 5, subject_key)

        result = []
        for row in rows:
            result.append({
                "trade_date": row["trade_date"],
                "avg_pct_chg": float(row["avg_pct_chg"]),
                "stock_count": int(row["stock_count"])
            })
        return result

    def _calculate_technical_indicators(self, theme_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算技术指标"""
        if len(theme_prices) < 5:
            return self._get_default_metrics()

        # 按日期排序（升序）
        sorted_prices = sorted(theme_prices, key=lambda x: x["trade_date"])

        # 提取价格序列
        pct_changes = [p["avg_pct_chg"] for p in sorted_prices if p.get("avg_pct_chg") is not None]

        if len(pct_changes) < 5:
            return self._get_default_metrics()

        # 计算收益指标
        theme_ret_3d = self._calculate_cumulative_return(pct_changes, 3) if len(pct_changes) >= 3 else None
        theme_ret_5d = self._calculate_cumulative_return(pct_changes, 5) if len(pct_changes) >= 5 else None
        theme_ret_10d = self._calculate_cumulative_return(pct_changes, 10) if len(pct_changes) >= 10 else None

        # 计算移动平均位置（简化：基于涨跌幅）
        recent_changes = pct_changes[-5:]  # 最近5日
        ma5 = statistics.mean(recent_changes) if len(recent_changes) >= 3 else 0
        ma10 = statistics.mean(pct_changes[-10:]) if len(pct_changes) >= 10 else 0
        ma20 = statistics.mean(pct_changes[-20:]) if len(pct_changes) >= 20 else 0

        current_change = pct_changes[-1] if pct_changes else 0
        above_ma5 = current_change > ma5 if ma5 is not None else False
        above_ma10 = current_change > ma10 if ma10 is not None else False
        above_ma20 = current_change > ma20 if ma20 is not None else False

        # 跌破启动枢轴（简化：是否跌破近期低点）
        recent_low = min(pct_changes[-5:]) if len(pct_changes) >= 5 else 0
        break_start_pivot = current_change < recent_low * 0.8  # 跌破近期低点的80%

        # 放量破位标志（需要成交量数据，这里简化）
        volume_breakdown_flag = False

        return {
            "theme_ret_3d": round(theme_ret_3d, 3) if theme_ret_3d is not None else None,
            "theme_ret_5d": round(theme_ret_5d, 3) if theme_ret_5d is not None else None,
            "theme_ret_10d": round(theme_ret_10d, 3) if theme_ret_10d is not None else None,
            "above_ma5": above_ma5,
            "above_ma10": above_ma10,
            "above_ma20": above_ma20,
            "break_start_pivot": break_start_pivot,
            "volume_breakdown_flag": volume_breakdown_flag
        }

    def _calculate_cumulative_return(self, pct_changes: List[float], days: int) -> float:
        """计算累计收益"""
        if len(pct_changes) < days:
            return 0.0

        # 使用复合收益公式：(1+r1)*(1+r2)*...*(1+rn) - 1
        recent_changes = pct_changes[-days:]
        cumulative = 1.0
        for change in recent_changes:
            cumulative *= (1 + change / 100.0)  # 假设pct_chg是百分比值

        return (cumulative - 1.0) * 100.0  # 转换回百分比

    async def _calculate_support_metrics(self, conn: asyncpg.Connection,
                                        trade_date: date,
                                        subject_key: str,
                                        stock_ids: List[str]) -> Dict[str, Any]:
        """计算支撑评分相关指标"""
        if not stock_ids:
            return {"theme_support_score": 50.0}  # 默认中等支撑

        # 简化支撑评分：基于成分股的技术位置
        try:
            # 获取成分股的关键价格水平
            sql = """
            WITH stock_levels AS (
                SELECT
                    trade_date,
                    stock_id,
                    close_price,
                    LAG(close_price, 1) OVER (PARTITION BY stock_id ORDER BY trade_date) as prev_close,
                    LAG(close_price, 5) OVER (PARTITION BY stock_id ORDER BY trade_date) as week_ago_close
                FROM subject_stock_daily_snapshot
                WHERE stock_id = ANY($2::text[])
                  AND trade_date <= $1
                  AND trade_date >= $1 - INTERVAL '10 days'
            ),
            current_levels AS (
                SELECT *
                FROM stock_levels
                WHERE trade_date = $1
            )
            SELECT
                COUNT(*) as total_stocks,
                COUNT(CASE WHEN close_price > prev_close THEN 1 END) as above_prev_close,
                COUNT(CASE WHEN close_price > week_ago_close THEN 1 END) as above_week_ago
            FROM current_levels
            """

            rows = await conn.fetch(sql, trade_date, stock_ids)
            if rows and rows[0]["total_stocks"] > 0:
                row = rows[0]
                total = float(row["total_stocks"])
                above_prev_ratio = float(row["above_prev_close"]) / total if total > 0 else 0
                above_week_ratio = float(row["above_week_ago"]) / total if total > 0 else 0

                # 综合支撑评分（0-100）
                support_score = (above_prev_ratio * 0.4 + above_week_ratio * 0.6) * 100
                return {"theme_support_score": round(support_score, 2)}
        except Exception as e:
            print(f"⚠️ 计算支撑评分失败: {e}")

        return {"theme_support_score": 50.0}

    def _get_default_metrics(self) -> Dict[str, Any]:
        """获取默认指标"""
        return {
            "theme_ret_3d": None,
            "theme_ret_5d": None,
            "theme_ret_10d": None,
            "above_ma5": False,
            "above_ma10": False,
            "above_ma20": False,
            "break_start_pivot": False,
            "volume_breakdown_flag": False,
            "theme_support_score": 50.0
        }

    async def update_theme_evidence_daily(self, trade_date: date, subject_key: str) -> bool:
        """更新theme_cycle_evidence_daily表的K线技术字段"""
        try:
            metrics = await self.calculate_kline_metrics(trade_date, subject_key)

            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                # 检查证据表是否存在
                check_sql = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'theme_cycle_evidence_daily'
                )
                """
                table_exists = await conn.fetchval(check_sql)

                if not table_exists:
                    print("⚠️ theme_cycle_evidence_daily表不存在，跳过K线指标更新")
                    return False

                sql = """
                UPDATE theme_cycle_evidence_daily
                SET
                    theme_ret_3d = $3,
                    theme_ret_5d = $4,
                    theme_ret_10d = $5,
                    above_ma5 = $6,
                    above_ma10 = $7,
                    above_ma20 = $8,
                    break_start_pivot = $9,
                    volume_breakdown_flag = $10,
                    theme_support_score = $11
                WHERE trade_date = $1 AND subject_key = $2
                """

                await conn.execute(
                    sql,
                    trade_date,
                    subject_key,
                    metrics["theme_ret_3d"],
                    metrics["theme_ret_5d"],
                    metrics["theme_ret_10d"],
                    metrics["above_ma5"],
                    metrics["above_ma10"],
                    metrics["above_ma20"],
                    metrics["break_start_pivot"],
                    metrics["volume_breakdown_flag"],
                    metrics["theme_support_score"]
                )

                return True
        except Exception as e:
            print(f"❌ 更新主题 {subject_key} K线指标失败: {e}")
            return False

    async def batch_update_for_date(self, trade_date: date) -> Dict[str, int]:
        """批量更新指定交易日所有主题的K线指标"""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 获取当日有evidence记录的所有主题
            sql = """
            SELECT DISTINCT subject_key
            FROM theme_cycle_evidence_daily
            WHERE trade_date = $1
            """
            rows = await conn.fetch(sql, trade_date)
            subjects = [row["subject_key"] for row in rows]

        success_count = 0
        fail_count = 0

        print(f"📊 开始批量更新 {trade_date} 的K线技术指标，共 {len(subjects)} 个主题")

        for subject_key in subjects:
            try:
                success = await self.update_theme_evidence_daily(trade_date, subject_key)
                if success:
                    success_count += 1
                else:
                    fail_count += 1

                if success_count % 10 == 0:
                    print(f"  已处理 {success_count}/{len(subjects)} 个主题")
            except Exception as e:
                print(f"❌ 主题 {subject_key} K线指标更新异常: {e}")
                fail_count += 1

        print(f"✅ K线指标批量更新完成: 成功 {success_count}, 失败 {fail_count}")
        return {"success": success_count, "failed": fail_count, "total": len(subjects)}


async def main():
    """测试函数"""
    import sys
    from datetime import date

    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)

    calculator = ThemeKlineCalculator()
    try:
        print(f"测试K线技术指标计算器，日期: {test_date}")

        # 测试单个主题
        test_subject = "9062832"  # 神剑股份所属主题
        metrics = await calculator.calculate_kline_metrics(test_date, test_subject)
        print(f"主题 {test_subject} K线技术指标:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")

        # 批量更新测试
        result = await calculator.batch_update_for_date(test_date)
        print(f"\n批量更新结果: {result}")

    finally:
        await calculator.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
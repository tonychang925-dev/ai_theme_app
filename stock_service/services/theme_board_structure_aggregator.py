from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Dict, List, Optional, Any
import asyncpg


class ThemeBoardStructureAggregator:
    """主题板块结构聚合器

    基于 subject_stock_daily_snapshot 表计算板块结构指标
    严格按照四层证据体系中的"板块结构层"要求实现
    """

    def __init__(self, config=None):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        """确保数据库连接池存在"""
        if self._pool is None:
            # 使用默认配置（与现有服务保持一致）
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

    async def calculate_board_metrics(self, trade_date: date, subject_key: str) -> Dict[str, Any]:
        """计算指定交易日和主题的板块结构指标"""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 1. 获取该主题当日的所有股票数据
            stocks = await self._fetch_stocks_for_subject(conn, trade_date, subject_key)
            if not stocks:
                return self._get_default_metrics()

            # 2. 计算各项指标
            metrics = self._calculate_metrics_from_stocks(stocks)

            # 3. 识别龙头股票
            leader_info = self._identify_leader_stock(stocks)
            metrics.update(leader_info)

            # 4. 计算前排相关指标
            front_row_metrics = self._calculate_front_row_metrics(stocks)
            metrics.update(front_row_metrics)

            return metrics

    async def _fetch_stocks_for_subject(self, conn: asyncpg.Connection,
                                       trade_date: date,
                                       subject_key: str) -> List[Dict[str, Any]]:
        """获取指定主题当日的所有股票数据"""
        sql = """
        SELECT
            stock_id,
            stock_name,
            pct_chg,
            limit_up,
            is_leader,
            rank_order,
            close_price,
            pre_close
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1 AND subject_key = $2
        ORDER BY rank_order NULLS LAST, pct_chg DESC
        """
        rows = await conn.fetch(sql, trade_date, subject_key)
        return [dict(row) for row in rows]

    def _calculate_metrics_from_stocks(self, stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """从股票列表计算板块结构指标"""
        if not stocks:
            return self._get_default_metrics()

        total_count = len(stocks)

        # 计算涨停数量
        limit_up_count = sum(1 for s in stocks if s.get('limit_up') is True)

        # 计算跌停数量（假设跌停为-10%或以下）
        limit_down_count = sum(1 for s in stocks if s.get('pct_chg') is not None and s.get('pct_chg') <= -9.9)

        # 计算红盘比例（涨幅>0）
        red_count = sum(1 for s in stocks if s.get('pct_chg') is not None and s.get('pct_chg') > 0)
        red_ratio = red_count / total_count if total_count > 0 else 0.0

        # 计算大跌比例（跌幅<=-5%）
        big_drop_count = sum(1 for s in stocks if s.get('pct_chg') is not None and s.get('pct_chg') <= -5.0)
        big_drop_ratio = big_drop_count / total_count if total_count > 0 else 0.0

        # 前排强度评分：基于前3名股票的涨幅
        front_stocks = stocks[:3] if len(stocks) >= 3 else stocks
        front_strength = 0.0
        if front_stocks:
            front_avg_pct = sum(s.get('pct_chg', 0) for s in front_stocks) / len(front_stocks)
            # 映射到0-100分：平均涨幅10%得100分，0%得50分，-10%得0分
            front_strength = max(0, min(100, 50 + (front_avg_pct * 5)))

        # 接力强度评分：基于非龙头股的强势表现
        non_leader_stocks = [s for s in stocks if not s.get('is_leader')]
        relay_strength = 0.0
        if non_leader_stocks:
            # 计算非龙头股的平均涨幅
            non_leader_avg = sum(s.get('pct_chg', 0) for s in non_leader_stocks) / len(non_leader_stocks)
            # 映射到0-100分
            relay_strength = max(0, min(100, 50 + (non_leader_avg * 5)))

        return {
            "board_stock_count": total_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "red_ratio": round(red_ratio, 3),
            "big_drop_ratio": round(big_drop_ratio, 3),
            "front_row_strength_score": round(front_strength, 2),
            "relay_strength_score": round(relay_strength, 2)
        }

    def _identify_leader_stock(self, stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """识别龙头股票"""
        if not stocks:
            return {"leader_stock_id": None, "leader_stock_name": None}

        # 首先找标记为龙头的股票
        for stock in stocks:
            if stock.get('is_leader') is True:
                return {
                    "leader_stock_id": stock.get('stock_id'),
                    "leader_stock_name": stock.get('stock_name')
                }

        # 如果没有标记的龙头，找涨幅最高的
        valid_stocks = [s for s in stocks if s.get('pct_chg') is not None]
        if valid_stocks:
            leader = max(valid_stocks, key=lambda x: x.get('pct_chg', 0))
            return {
                "leader_stock_id": leader.get('stock_id'),
                "leader_stock_name": leader.get('stock_name')
            }

        # 最后按rank_order
        sorted_stocks = sorted(stocks, key=lambda x: x.get('rank_order') or 999)
        leader = sorted_stocks[0] if sorted_stocks else stocks[0]
        return {
            "leader_stock_id": leader.get('stock_id'),
            "leader_stock_name": leader.get('stock_name')
        }

    def _calculate_front_row_metrics(self, stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算前排存活率相关指标"""
        if len(stocks) < 2:
            return {"front_row_survival_ratio": 0.0}

        # 定义前排：前5名或前20%（取较小值）
        front_row_size = min(5, max(1, len(stocks) // 5))
        front_stocks = stocks[:front_row_size]

        # 计算前排中红盘的比例
        front_red_count = sum(1 for s in front_stocks if s.get('pct_chg') is not None and s.get('pct_chg') > 0)
        survival_ratio = front_red_count / front_row_size if front_row_size > 0 else 0.0

        return {
            "front_row_survival_ratio": round(survival_ratio, 3)
        }

    def _get_default_metrics(self) -> Dict[str, Any]:
        """获取默认指标（当无数据时）"""
        return {
            "board_stock_count": 0,
            "limit_up_count": 0,
            "limit_down_count": 0,
            "red_ratio": 0.0,
            "big_drop_ratio": 0.0,
            "front_row_strength_score": 0.0,
            "relay_strength_score": 0.0,
            "leader_stock_id": None,
            "leader_stock_name": None,
            "front_row_survival_ratio": 0.0
        }

    async def update_theme_cycle_evidence(self, trade_date: date, subject_key: str) -> bool:
        """更新 theme_cycle_evidence_daily 表的板块结构字段"""
        try:
            metrics = await self.calculate_board_metrics(trade_date, subject_key)

            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                sql = """
                UPDATE theme_cycle_evidence_daily
                SET
                    leader_stock_id = $3,
                    leader_stock_name = $4,
                    board_stock_count = $5,
                    limit_down_count = $6,
                    red_ratio = $7,
                    big_drop_ratio = $8,
                    front_row_strength_score = $9,
                    relay_strength_score = $10,
                    front_row_survival_ratio = $11,
                    updated_at = now()
                WHERE trade_date = $1 AND subject_key = $2
                """

                await conn.execute(
                    sql,
                    trade_date,
                    subject_key,
                    metrics["leader_stock_id"],
                    metrics["leader_stock_name"],
                    metrics["board_stock_count"],
                    metrics["limit_down_count"],
                    metrics["red_ratio"],
                    metrics["big_drop_ratio"],
                    metrics["front_row_strength_score"],
                    metrics["relay_strength_score"],
                    metrics["front_row_survival_ratio"]
                )

                return True
        except Exception as e:
            print(f"❌ 更新主题 {subject_key} 板块结构失败: {e}")
            return False

    async def batch_update_for_date(self, trade_date: date) -> Dict[str, int]:
        """批量更新指定交易日所有主题的板块结构字段"""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 获取当日有 v2 周期记录的所有主题
            sql = """
            SELECT DISTINCT subject_key
            FROM theme_cycle_judgement_v2
            WHERE trade_date = $1
            """
            rows = await conn.fetch(sql, trade_date)
            subjects = [row["subject_key"] for row in rows]

        success_count = 0
        fail_count = 0

        print(f"📊 开始批量更新 {trade_date} 的板块结构指标，共 {len(subjects)} 个主题")

        for subject_key in subjects:
            try:
                success = await self.update_theme_cycle_evidence(trade_date, subject_key)
                if success:
                    success_count += 1
                else:
                    fail_count += 1

                if success_count % 10 == 0:
                    print(f"  已处理 {success_count}/{len(subjects)} 个主题")
            except Exception as e:
                print(f"❌ 主题 {subject_key} 处理异常: {e}")
                fail_count += 1

        print(f"✅ 批量更新完成: 成功 {success_count}, 失败 {fail_count}")
        return {"success": success_count, "failed": fail_count, "total": len(subjects)}


async def main():
    """测试函数"""
    import sys
    from datetime import date

    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)  # 默认测试日期

    aggregator = ThemeBoardStructureAggregator()
    try:
        print(f"测试板块结构聚合器，日期: {test_date}")

        # 测试单个主题
        test_subject = "9062832"  # 神剑股份所属主题
        metrics = await aggregator.calculate_board_metrics(test_date, test_subject)
        print(f"主题 {test_subject} 板块结构指标:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")

        # 批量更新测试
        result = await aggregator.batch_update_for_date(test_date)
        print(f"\n批量更新结果: {result}")

    finally:
        await aggregator.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

#!/usr/bin/env python3
"""
严格版弱转强筛选 - 目标：每天10个左右候选股
"""
import asyncio
import asyncpg
import sys
import os
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs
from stock_service.models import ThemeCycleJudgement, StockAbnormalSignal, StrongStockRecord
from stock_service.services.strong_stock_tracker_service import StrongStockTrackerService
from stock_service.services.stock_screener_service import StockScreenerService
from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.kline_data_service import KlineDataService


class StrictWeakToStrongScreener:
    """严格版弱转强筛选器 - 目标每天10个左右候选股"""

    def __init__(self):
        self.config = {
            "host": "localhost",
            "port": 5432,
            "database": "stock_data_test",
            "user": "postgres",
            "password": "zxbzj~925"
        }
        self.conn = None
        self.weak_to_strong_service = WeakToStrongService()
        self.strong_stock_tracker = StrongStockTrackerService()
        self.strong_stock_analysis_service = StrongStockAnalysisService()
        self.kline_data_service = KlineDataService()

    async def connect(self):
        """连接数据库"""
        try:
            print(f"连接数据库: {self.config['host']}:{self.config['port']}/{self.config['database']}")
            self.conn = await asyncpg.connect(**self.config)
            print("✅ 数据库连接成功")
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            raise

    async def close(self):
        """关闭连接"""
        if self.conn:
            await self.conn.close()

    def _requires_gap_support(self, limit_up_pattern: Dict[str, Any]) -> bool:
        """
        严格版：判断是否需要缺口支撑

        对于连续涨停（尤其是3天及以上）的股票，需要缺口支撑。
        对于多次涨停（4次及以上）的股票，也需要缺口支撑。
        """
        max_consecutive = limit_up_pattern.get('max_consecutive_days', 0)
        pattern_type = limit_up_pattern.get('pattern_type', '')
        limit_up_count = limit_up_pattern.get('limit_up_count', 0)

        # 连续3天及以上涨停 -> 需要缺口支撑
        if max_consecutive >= 3:
            return True

        # 4次及以上涨停（非连续）-> 需要缺口支撑
        if limit_up_count >= 4:
            return True

        # 其他情况：单日涨停或2-3次非连续涨停 -> 不强制要求缺口支撑
        return False

    async def screening_strict(self, trade_date: date):
        """严格弱转强筛选 - 目标每天10个左右候选股"""
        print(f"\n🎯 执行严格版弱转强筛选 - {trade_date}")
        print("=" * 70)

        candidates = []

        # 查询所有当日弱势下跌的股票
        query = """
        SELECT DISTINCT ON (ss.stock_id)
            ss.stock_id,
            ss.stock_name,
            ss.pct_chg,
            ss.is_leader,
            ss.rank_order,
            ss.open_price,
            ss.high_price,
            ss.low_price,
            ss.close_price,
            ss.volume,
            ss.amount,
            ss.limit_up,
            ss.subject_key
        FROM subject_stock_daily_snapshot ss
        WHERE ss.trade_date = $1 AND ss.pct_chg < -2.0  -- 放宽：<-2.0%
        ORDER BY ss.stock_id, ss.rank_order NULLS LAST
        """
        rows = await self.conn.fetch(query, trade_date)

        print(f"找到 {len(rows)} 只当日弱势下跌 (<-2.0%) 的股票")

        for i, row in enumerate(rows):
            stock_id = row['stock_id']
            stock_name = row['stock_name']
            pct_chg = float(row['pct_chg'])
            theme_key = row['subject_key']

            if i % 50 == 0:
                print(f"  分析进度: {i+1}/{len(rows)}")

            # 条件1: 当日弱势下跌 (<-2.5%) - 已经满足

            # 条件1b: 前一个交易日也弱势下跌 (<-1.5%)
            prev_query = """
            SELECT pct_chg, trade_date FROM subject_stock_daily_snapshot
            WHERE stock_id = $1 AND trade_date < $2
            ORDER BY trade_date DESC
            LIMIT 1
            """
            prev_data = await self.conn.fetchrow(prev_query, stock_id, trade_date)
            prev_weak = False
            prev_pct_chg = 0
            if prev_data and prev_data['pct_chg'] is not None:
                prev_pct_chg = float(prev_data['pct_chg'])
                prev_weak = prev_pct_chg < -1.5

            if not prev_weak:
                print(f"      ⚠️  前一天不是弱势下跌（或数据缺失），跳过")
                continue

            # 条件2: 检查前期是否真正强势股
            limit_up_pattern = await self.strong_stock_analysis_service._analyze_limit_up_pattern(
                stock_id, trade_date, trading_days=7
            )

            has_strong_history = limit_up_pattern['has_limit_up_pattern']
            limit_up_count = limit_up_pattern['limit_up_count']
            max_consecutive = limit_up_pattern['max_consecutive_days']
            pattern_type = limit_up_pattern['pattern_type']
            requires_gap = self._requires_gap_support(limit_up_pattern)

            # 调整：必须是真正的强势股（防止1日游）
            # 标准：连续2天及以上涨停，或2次及以上涨停（非连续）
            is_real_strong = (max_consecutive >= 2) or (limit_up_count >= 2)

            if not is_real_strong:
                continue

            # 条件3: 严格检查支撑位
            gap_analysis = await self.kline_data_service.analyze_gap_support(stock_id, trade_date)

            has_gap_support = gap_analysis.get('is_gap_support', False)
            has_support = gap_analysis.get('has_support', False)
            support_strength = gap_analysis.get('support_strength', 0.0)
            support_level = gap_analysis.get('support_level', 0.0)
            gap_support_level = gap_analysis.get('gap_support_level', 0.0)

            # 严格支撑判断
            has_valid_support = False
            support_type = ''

            if has_gap_support:
                # 缺口支撑：必须强度>=0.6
                if support_strength >= 0.6:
                    has_valid_support = True
                    support_type = 'gap'
                    support_level = gap_support_level
                    print(f"      ✅ 严格缺口支撑: {support_level:.2f} (强度:{support_strength:.1f})")
                else:
                    print(f"      ⚠️  缺口支撑强度不足: {support_strength:.1f} < 0.6")
            elif has_support:
                # 非缺口支撑：需要更高强度
                if support_strength >= 0.6:  # 严格：需要0.6强度
                    # 检查是否需要缺口支撑
                    if requires_gap:
                        print(f"      ⚠️  需要缺口支撑但未检测到（检测到{gap_analysis.get('support_type', 'unknown')}支撑，强度:{support_strength:.1f}）")
                        has_valid_support = False
                    else:
                        has_valid_support = True
                        support_type = gap_analysis.get('support_type', 'unknown')
                        print(f"      ✅ 严格{support_type}支撑: {support_level:.2f} (强度:{support_strength:.1f})")
                else:
                    print(f"      ⚠️  支撑强度不足: {support_strength:.1f} < 0.6")
            else:
                if requires_gap:
                    print(f"      ⚠️  需要缺口支撑但未检测到（无有效支撑）")
                else:
                    print(f"      ⚠️  无有效支撑位")

            # 如果没有有效支撑位，手动检查历史缺口（更严格）
            if not has_valid_support:
                # 获取更多历史数据（15天）手动检查缺口
                history_query = """
                SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
                FROM subject_stock_daily_snapshot
                WHERE stock_id = $1 AND trade_date <= $2 AND trade_date >= $2::date - INTERVAL '15 days'
                ORDER BY trade_date
                """
                history_rows = await self.conn.fetch(history_query, stock_id, trade_date)

                # 查找显著缺口（>1%）
                gaps = []
                for j in range(1, len(history_rows)):
                    prev = history_rows[j-1]
                    curr = history_rows[j]

                    prev_close = float(prev['close_price']) if prev['close_price'] else 0
                    curr_open = float(curr['open_price']) if curr['open_price'] else 0

                    if prev_close <= 0 or curr_open <= 0:
                        continue

                    # 检查向上缺口（显著缺口：>1%）
                    if curr_open > prev_close * 1.01:  # 1%阈值
                        gap_size = (curr_open - prev_close) / prev_close * 100
                        gap_info = {
                            'date': curr['trade_date'],
                            'type': 'up',
                            'gap_range': (prev_close, curr_open),
                            'size_pct': gap_size
                        }
                        gaps.append(gap_info)

                # 检查当前价格是否精确回补关键缺口（距离<2%）
                current_low = float(row['low_price']) if row['low_price'] else 0

                if gaps:
                    # 选择最早且显著的缺口（>1.5%）作为关键支撑位
                    significant_gaps = [g for g in gaps if g['size_pct'] > 1.5]
                    if significant_gaps:
                        # 按日期排序，选择最早的显著缺口
                        significant_gaps.sort(key=lambda x: x['date'])
                        key_gap = significant_gaps[0]
                    else:
                        # 如果没有显著缺口，选择最早的缺口
                        gaps.sort(key=lambda x: x['date'])
                        key_gap = gaps[0]

                    gap_lower, gap_upper = key_gap['gap_range']

                    # 严格：价格必须在缺口下沿2%以内
                    gap_distance_pct = abs(current_low - gap_lower) / gap_lower * 100
                    if gap_distance_pct < 2.0:
                        print(f"      ✅ 手动检测到历史缺口支撑: {gap_lower:.2f} (距离:{gap_distance_pct:.1f}%)")
                        has_valid_support = True
                        support_type = 'gap_manual'
                        support_level = gap_lower
                        gap_support_level = gap_lower
                    else:
                        print(f"      ⚠️  价格距离历史缺口较远: {gap_distance_pct:.1f}% > 2%")

            # 弱转强条件：严格版
            # 1. 当日明显弱势下跌 (<-2.0%)
            # 2. 前一天也弱势下跌 (<-1.5%)
            # 3. 真正强势股（连续2+涨停或3+次涨停）
            # 4. 到达严格支撑位
            is_strict_weak_to_strong = (pct_chg < -2.0 and prev_weak and is_real_strong and has_valid_support)

            if is_strict_weak_to_strong:
                print(f"  🎯 发现严格弱转强候选股: {stock_id} {stock_name}")
                print(f"     跌幅: {pct_chg:.1f}%, 涨停模式: {pattern_type}")
                print(f"     支撑位: {support_level:.2f} ({support_type}), 主题: {theme_key}")

                # 获取完整的强势股分析用于记录
                stock_data = dict(row)
                stock_data['trade_date'] = trade_date

                strong_analysis = await self.strong_stock_analysis_service.analyze_stock_by_pdf_framework(
                    stock_id,
                    trade_date,
                    stock_data
                )

                candidates.append({
                    'stock_id': stock_id,
                    'stock_name': stock_name,
                    'theme_key': theme_key,
                    'pct_chg': pct_chg,
                    'limit_up_pattern': limit_up_pattern,
                    'gap_analysis': gap_analysis,
                    'strong_analysis': strong_analysis,
                    'gap_support_level': support_level,
                    'support_type': support_type
                })

                # 如果已经达到10个候选股，可以提前停止（可选）
                if len(candidates) >= 15:  # 稍微多查一些，后面可以再筛选
                    print(f"  已达到15个候选股，停止进一步分析")
                    break

        print(f"\n{'='*70}")
        print(f"严格筛选完成，找到 {len(candidates)} 个弱转强候选股")

        if candidates:
            print(f"\n候选股详细列表:")
            for i, cand in enumerate(candidates, 1):
                pattern_type = cand['limit_up_pattern']['pattern_type']
                support_level = cand.get('gap_support_level', 0)
                print(f"  {i:2d}. {cand['stock_id']} {cand['stock_name']}")
                print(f"      跌幅: {cand['pct_chg']:.1f}%, {pattern_type}")
                print(f"      支撑位: {support_level:.2f} ({cand['support_type']}), 主题: {cand['theme_key']}")

                # 显示技术信号（如果有）
                gap_analysis = cand.get('gap_analysis', {})
                tech_signals = gap_analysis.get('technical_signals', [])
                if tech_signals:
                    print(f"      技术信号: {tech_signals[0]}")
                print()

        return candidates


async def test_strict_screening():
    """测试严格筛选"""
    test_date = date(2026, 4, 10)

    screener = StrictWeakToStrongScreener()
    await screener.connect()

    candidates = await screener.screening_strict(test_date)

    await screener.close()
    return candidates


async def main():
    try:
        await test_strict_screening()
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
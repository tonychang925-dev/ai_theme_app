#!/usr/bin/env python3
"""
测试严格版弱转强筛选
"""
import asyncio
import asyncpg
import sys
import os
from datetime import date
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class StrictWeakToStrongScreener:
    """严格版弱转强筛选器"""

    def __init__(self):
        self.config = {
            "host": "localhost",
            "port": 5432,
            "database": "stock_data_test",
            "user": "postgres",
            "password": "zxbzj~925"
        }
        self.conn = None

    async def connect(self):
        """连接数据库"""
        self.conn = await asyncpg.connect(**self.config)

    async def close(self):
        """关闭连接"""
        if self.conn:
            await self.conn.close()

    def _requires_gap_support(self, limit_up_pattern: Dict[str, Any]) -> bool:
        """判断是否需要缺口支撑（严格版）"""
        max_consecutive = limit_up_pattern.get('max_consecutive_days', 0)
        pattern_type = limit_up_pattern.get('pattern_type', '')
        limit_up_count = limit_up_pattern.get('limit_up_count', 0)

        # 连续2天及以上涨停 -> 需要缺口支撑
        if max_consecutive >= 2:
            return True

        # 3次及以上涨停（非连续）-> 需要缺口支撑
        if limit_up_count >= 3:
            return True

        return False

    async def analyze_limit_up_pattern(self, stock_id: str, trade_date: date, trading_days: int = 7) -> Dict[str, Any]:
        """分析涨停模式"""
        query = """
        WITH recent_data AS (
            SELECT trade_date, pct_chg,
                   ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1
              AND trade_date < $2
              AND trade_date >= $2::date - INTERVAL '%s days'
            ORDER BY trade_date DESC
        )
        SELECT
            COUNT(CASE WHEN pct_chg >= 9.8 THEN 1 END) as limit_up_count,
            MAX(
                (SELECT COUNT(*)
                 FROM recent_data r2
                 WHERE r2.rn BETWEEN r1.rn AND r1.rn + consecutive_count - 1
                   AND r2.pct_chg >= 9.8
                )
            ) as max_consecutive_days
        FROM recent_data r1
        CROSS JOIN LATERAL (
            SELECT COUNT(*) as consecutive_count
            FROM recent_data r2
            WHERE r2.rn >= r1.rn
              AND r2.pct_chg >= 9.8
              AND NOT EXISTS (
                  SELECT 1 FROM recent_data r3
                  WHERE r3.rn = r2.rn - 1
                    AND r3.pct_chg < 9.8
                    AND r3.rn >= r1.rn
              )
        ) t
        WHERE r1.pct_chg >= 9.8
        """ % trading_days

        try:
            result = await self.conn.fetchrow(query, stock_id, trade_date)
            limit_up_count = result['limit_up_count'] if result else 0
            max_consecutive = result['max_consecutive_days'] if result else 0

            has_limit_up_pattern = limit_up_count > 0

            if max_consecutive >= 2:
                pattern_type = f"连续{max_consecutive}天涨停"
            elif limit_up_count >= 2:
                pattern_type = f"{limit_up_count}次非连续涨停"
            else:
                pattern_type = "单日涨停"

            return {
                'has_limit_up_pattern': has_limit_up_pattern,
                'limit_up_count': limit_up_count,
                'max_consecutive_days': max_consecutive,
                'pattern_type': pattern_type
            }
        except Exception as e:
            print(f"分析涨停模式错误: {e}")
            return {
                'has_limit_up_pattern': False,
                'limit_up_count': 0,
                'max_consecutive_days': 0,
                'pattern_type': '无涨停'
            }

    async def analyze_strict_support(self, stock_id: str, analysis_date: date) -> Dict[str, Any]:
        """严格支撑位分析"""
        # 获取前5天数据
        query = """
        SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1
          AND trade_date <= $2
          AND trade_date >= $2::date - INTERVAL '5 days'
        ORDER BY trade_date ASC
        """
        rows = await self.conn.fetch(query, stock_id, analysis_date)

        if len(rows) < 2:
            return {
                'has_support': False,
                'support_type': '',
                'support_strength': 0.0,
                'support_level': 0.0,
                'is_gap_support': False,
                'gap_support_level': 0.0
            }

        # 找到分析日和前一日
        target_kline = None
        prev_kline = None

        for kline in rows:
            if kline['trade_date'] == analysis_date:
                target_kline = kline
            elif target_kline is None and kline['trade_date'] < analysis_date:
                prev_kline = kline

        if target_kline is None or prev_kline is None:
            return {
                'has_support': False,
                'support_type': '',
                'support_strength': 0.0,
                'support_level': 0.0,
                'is_gap_support': False,
                'gap_support_level': 0.0
            }

        current_low = target_kline.get('low_price', 0)
        prev_low = prev_kline.get('low_price', 0)
        prev_high = prev_kline.get('high_price', 0)
        prev_close = prev_kline.get('close_price', 0)

        result = {
            'has_support': False,
            'support_type': '',
            'support_strength': 0.0,
            'support_level': 0.0,
            'is_gap_support': False,
            'gap_support_level': 0.0
        }

        # 检查缺口支撑（严格：缺口大小 > 1%）
        gap_threshold = 0.01  # 1%阈值
        if current_low > prev_high * (1 + gap_threshold):
            gap_support = prev_high
            gap_distance_pct = abs(current_low - gap_support) / gap_support * 100
            # 严格：必须在2%以内
            if gap_distance_pct < 2.0:
                result['has_support'] = True
                result['support_type'] = 'gap'
                result['support_strength'] = 0.9  # 缺口支撑强度高
                result['support_level'] = gap_support
                result['is_gap_support'] = True
                result['gap_support_level'] = gap_support

        # 如果没有缺口支撑，检查前低支撑（严格：必须在2%以内，强度0.8）
        if not result['has_support'] and prev_low > 0:
            support_distance_pct = abs(current_low - prev_low) / prev_low * 100
            if support_distance_pct < 2.0:  # 严格：2%以内
                result['has_support'] = True
                result['support_type'] = 'previous_low'
                result['support_strength'] = 0.8  # 前低支撑强度较高
                result['support_level'] = prev_low

        # 检查前一日收盘价支撑（更严格：必须在1.5%以内，且前一日是强势收盘）
        if not result['has_support'] and prev_close > 0:
            # 前一日收盘在K线实体上半部分才考虑
            prev_open = prev_kline.get('open_price', 0)
            if prev_open > 0:
                body_mid = (prev_open + prev_close) / 2
                if prev_close >= body_mid:  # 收盘在实体上半部分
                    support_distance_pct = abs(current_low - prev_close) / prev_close * 100
                    if support_distance_pct < 1.5:  # 很严格：1.5%以内
                        result['has_support'] = True
                        result['support_type'] = 'previous_close'
                        result['support_strength'] = 0.7
                        result['support_level'] = prev_close

        return result

    async def screening_strict(self, trade_date: date):
        """严格弱转强筛选"""
        print(f"\n🎯 执行严格版弱转强筛选 - {trade_date}")
        print("=" * 70)

        candidates = []

        # 查询所有当日弱势下跌的股票
        query = """
        SELECT DISTINCT ON (ss.stock_id)
            ss.stock_id,
            ss.stock_name,
            ss.pct_chg,
            ss.open_price,
            ss.high_price,
            ss.low_price,
            ss.close_price,
            ss.subject_key
        FROM subject_stock_daily_snapshot ss
        WHERE ss.trade_date = $1 AND ss.pct_chg < -2.0
        ORDER BY ss.stock_id, ss.rank_order NULLS LAST
        """
        rows = await self.conn.fetch(query, trade_date)

        print(f"找到 {len(rows)} 只当日弱势下跌 (<-2%) 的股票")

        for i, row in enumerate(rows):
            stock_id = row['stock_id']
            stock_name = row['stock_name']
            pct_chg = float(row['pct_chg'])
            theme_key = row['subject_key']

            if i % 50 == 0:
                print(f"  分析进度: {i+1}/{len(rows)}")

            # 条件1: 当日弱势下跌 (<-2%) - 已经满足

            # 条件2: 检查涨停模式（严格）
            limit_up_pattern = await self.analyze_limit_up_pattern(stock_id, trade_date, 7)

            has_strong_history = limit_up_pattern['has_limit_up_pattern']
            limit_up_count = limit_up_pattern['limit_up_count']
            max_consecutive = limit_up_pattern['max_consecutive_days']
            pattern_type = limit_up_pattern['pattern_type']

            # 严格：必须是真正的强势股（连续涨停或多次涨停）
            is_real_strong = (max_consecutive >= 2) or (limit_up_count >= 2)

            if not is_real_strong:
                continue

            # 判断是否需要缺口支撑
            requires_gap = self._requires_gap_support(limit_up_pattern)

            # 条件3: 严格支撑位分析
            support_analysis = await self.analyze_strict_support(stock_id, trade_date)

            has_support = support_analysis['has_support']
            support_strength = support_analysis['support_strength']
            has_gap_support = support_analysis['is_gap_support']
            support_type = support_analysis['support_type']
            support_level = support_analysis['support_level']

            # 严格支撑判断
            has_valid_support = False

            if has_gap_support:
                has_valid_support = True
                print(f"      ✅ 严格缺口支撑: {support_level:.2f} (强度:{support_strength:.1f})")
            elif has_support:
                # 检查是否需要缺口支撑
                if requires_gap:
                    print(f"      ⚠️  需要缺口支撑但未检测到（检测到{support_type}支撑，强度:{support_strength:.1f}）")
                    has_valid_support = False
                else:
                    # 非缺口支撑需要更高的强度
                    if support_strength >= 0.8:  # 严格：需要0.8强度
                        has_valid_support = True
                        print(f"      ✅ 严格{support_type}支撑: {support_level:.2f} (强度:{support_strength:.1f})")
                    else:
                        print(f"      ⚠️  支撑强度不足: {support_strength:.1f} < 0.8")

            # 弱转强条件：当日弱势下跌 + 真正强势股 + 严格支撑位
            if pct_chg < -2.0 and is_real_strong and has_valid_support:
                print(f"  🎯 发现严格弱转强候选股: {stock_id} {stock_name}")
                print(f"     跌幅: {pct_chg:.1f}%, 涨停模式: {pattern_type}")
                print(f"     支撑位: {support_level:.2f} ({support_type}), 主题: {theme_key}")

                candidates.append({
                    'stock_id': stock_id,
                    'stock_name': stock_name,
                    'theme_key': theme_key,
                    'pct_chg': pct_chg,
                    'limit_up_pattern': limit_up_pattern,
                    'support_analysis': support_analysis,
                    'support_level': support_level,
                    'support_type': support_type
                })

        print(f"\n{'='*70}")
        print(f"严格筛选完成，找到 {len(candidates)} 个弱转强候选股")

        if candidates:
            print(f"\n候选股列表:")
            for i, cand in enumerate(candidates, 1):
                pattern_type = cand['limit_up_pattern']['pattern_type']
                support_level = cand.get('support_level', 0)
                print(f"  {i:2d}. {cand['stock_id']} {cand['stock_name']}")
                print(f"      跌幅: {cand['pct_chg']:.1f}%, {pattern_type}")
                print(f"      支撑位: {support_level:.2f} ({cand['support_type']}), 主题: {cand['theme_key']}")
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
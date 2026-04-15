#!/usr/bin/env python3
"""
增强版弱转强筛选 - 包含历史事件和资金持续流入分析
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


class EnhancedWeakToStrongScreener:
    """增强版弱转强筛选器 - 包含历史事件和资金持续流入分析"""

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
        根据涨停模式判断是否需要缺口支撑

        对于连续涨停（尤其是3天及以上）的股票，通常有突破缺口，
        弱转强时需要回补该缺口作为支撑位。

        对于非连续涨停的股票，其他类型支撑（如前低）可能足够。
        """
        max_consecutive = limit_up_pattern.get('max_consecutive_days', 0)
        pattern_type = limit_up_pattern.get('pattern_type', '')

        # 连续3天及以上涨停 -> 需要缺口支撑
        if max_consecutive >= 3:
            return True

        # 连续2天涨停，且pattern_type包含"连续" -> 可能需要缺口支撑
        if max_consecutive == 2 and '连续' in pattern_type:
            return True

        # 其他情况：非连续涨停或单次涨停 -> 不强制要求缺口支撑
        return False

    async def get_potential_themes_with_history(self, trade_date: date, history_days: int = 30) -> List[str]:
        """获取潜力主线主题 - 包含历史事件和资金持续流入分析"""
        try:
            # 计算历史日期范围
            history_start_date = trade_date - timedelta(days=history_days)

            query = """
            WITH theme_daily_stats AS (
                -- 当日主题统计
                SELECT
                    ss.subject_key,
                    COUNT(DISTINCT ss.stock_id) as stock_count,
                    SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
                    AVG(ss.pct_chg) as avg_pct_chg,
                    SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) as limit_up_count,
                    SUM(CASE WHEN ss.is_leader = TRUE THEN 1 ELSE 0 END) as leader_count
                FROM subject_stock_daily_snapshot ss
                LEFT JOIN money_flow_enhanced mf
                    ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
                WHERE ss.trade_date = $1
                GROUP BY ss.subject_key
                HAVING COUNT(DISTINCT ss.stock_id) >= 3  -- 至少3只股票
            ),
            theme_history_stats AS (
                -- 历史事件统计
                SELECT
                    the.subject_key,
                    COUNT(DISTINCT the.rank_date) as event_days,
                    SUM(CASE WHEN the.heat_name = '热' THEN 1 ELSE 0 END) as hot_event_count,
                    AVG(the.pct_chg) as avg_event_pct_chg
                FROM theme_history_event the
                WHERE the.rank_date <= $1 AND the.rank_date >= $2
                GROUP BY the.subject_key
            ),
            theme_capital_trend AS (
                -- 资金流入趋势（最近5天）
                SELECT
                    ss.subject_key,
                    COUNT(DISTINCT ss.trade_date) as capital_days,
                    SUM(CASE WHEN COALESCE(mf.main_net_inflow, 0) > 0 THEN 1 ELSE 0 END) as positive_inflow_days,
                    SUM(COALESCE(mf.main_net_inflow, 0)) as total_recent_inflow
                FROM subject_stock_daily_snapshot ss
                LEFT JOIN money_flow_enhanced mf
                    ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
                WHERE ss.trade_date <= $1 AND ss.trade_date >= $1 - INTERVAL '5 days'
                GROUP BY ss.subject_key
            )
            SELECT
                ds.subject_key,
                ds.stock_count,
                ds.total_inflow,
                ds.avg_pct_chg,
                ds.limit_up_count,
                ds.leader_count,
                COALESCE(hs.event_days, 0) as event_days,
                COALESCE(hs.hot_event_count, 0) as hot_event_count,
                COALESCE(hs.avg_event_pct_chg, 0) as avg_event_pct_chg,
                COALESCE(ct.capital_days, 0) as capital_days,
                COALESCE(ct.positive_inflow_days, 0) as positive_inflow_days,
                COALESCE(ct.total_recent_inflow, 0) as total_recent_inflow,
                -- 综合评分公式：
                -- 1. 当日表现（40%）：涨停股和龙头股权重高
                -- 2. 历史事件（30%）：事件天数、热点事件
                -- 3. 资金趋势（30%）：持续流入天数
                CASE
                    WHEN ds.limit_up_count >= 10 THEN 100
                    WHEN ds.limit_up_count >= 5 THEN 90
                    WHEN ds.leader_count >= 2 THEN 85
                    ELSE (
                        -- 基础分：资金流入（每1亿得5分）
                        LEAST((ds.total_inflow / 100000000) * 5, 40) +
                        -- 历史事件分：每事件日得2分，每热点事件得5分
                        LEAST(COALESCE(hs.event_days, 0) * 2 + COALESCE(hs.hot_event_count, 0) * 5, 30) +
                        -- 资金趋势分：每正流入日得5分
                        LEAST(COALESCE(ct.positive_inflow_days, 0) * 5, 30)
                    )
                END as theme_score
            FROM theme_daily_stats ds
            LEFT JOIN theme_history_stats hs ON ds.subject_key = hs.subject_key
            LEFT JOIN theme_capital_trend ct ON ds.subject_key = ct.subject_key
            WHERE
                -- 至少满足以下条件之一：
                ds.total_inflow > 100000000  -- 1亿以上资金流入
                OR ds.limit_up_count >= 1  -- 有涨停股
                OR ds.leader_count >= 1    -- 有龙头股
                OR COALESCE(hs.hot_event_count, 0) >= 1  -- 有热点事件
                OR COALESCE(ct.positive_inflow_days, 0) >= 2  -- 至少有2天资金正流入
            ORDER BY
                theme_score DESC,
                ds.limit_up_count DESC,
                ds.leader_count DESC,
                ds.avg_pct_chg DESC
            LIMIT 30
            """

            rows = await self.conn.fetch(query, trade_date, history_start_date)
            subject_keys = [row['subject_key'] for row in rows]

            if subject_keys:
                print(f"  潜力主线主题（含历史事件分析）:")
                for row in rows[:5]:
                    inflow_text = f"资金流入{row['total_inflow']/100000000:.2f}亿" if row['total_inflow'] > 100000000 else f"资金流入{row['total_inflow']:.0f}"
                    print(f"    主题 {row['subject_key']}: {row['stock_count']}只股票, {inflow_text}, {row['limit_up_count']}涨停")
                    if row['event_days'] > 0:
                        print(f"      历史事件: {row['event_days']}天, 热点事件: {row['hot_event_count']}个")
                    if row['positive_inflow_days'] > 0:
                        print(f"      资金趋势: 最近5天{row['positive_inflow_days']}天正流入")

            return subject_keys
        except Exception as e:
            print(f"获取潜力主题失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def screening(self, trade_date: date):
        """执行弱转强筛选 - 真正的弱转强逻辑：前期强势股，当日弱势下跌到支撑位"""
        print(f"\n📊 执行弱转强筛选 - {trade_date}")
        print("=" * 70)

        # 获取潜力主线主题（包含历史事件分析）
        potential_theme_keys = await self.get_potential_themes_with_history(trade_date)

        if not potential_theme_keys:
            print("未找到潜力主线主题")
            return []

        print(f"\n找到 {len(potential_theme_keys)} 个潜力主线主题")

        candidates = []
        for theme_key in potential_theme_keys[:10]:  # 只处理前10个主题
            print(f"\n分析主题: {theme_key}")
            print("-" * 50)

            # 获取该主题下的所有股票（不按涨幅排序）
            query = """
            SELECT
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
                ss.limit_up
            FROM subject_stock_daily_snapshot ss
            WHERE ss.subject_key = $1 AND ss.trade_date = $2
            """
            rows = await self.conn.fetch(query, theme_key, trade_date)

            if not rows:
                continue

            print(f"  主题下股票数量: {len(rows)}")

            for row in rows:
                stock_id = row['stock_id']
                stock_name = row['stock_name']
                pct_chg = float(row['pct_chg'])

                # 条件1: 当日弱势下跌（<-2%）
                if pct_chg >= -2.0:
                    # 当日不是弱势下跌，跳过
                    continue

                print(f"    📉 {stock_id} {stock_name}: 当日弱势下跌 {pct_chg:.1f}%")

                # 获取股票数据字典用于分析
                stock_data = dict(row)
                stock_data['trade_date'] = trade_date

                # 条件2: 检查前期是否强势股（分析涨停模式）
                limit_up_pattern = await self.strong_stock_analysis_service._analyze_limit_up_pattern(
                    stock_id, trade_date, trading_days=7
                )

                has_strong_history = limit_up_pattern['has_limit_up_pattern']
                limit_up_count = limit_up_pattern['limit_up_count']
                max_consecutive = limit_up_pattern['max_consecutive_days']

                if not has_strong_history:
                    print(f"      ⚠️  前期无强势表现（{limit_up_count}次涨停，最长连续{max_consecutive}天）")
                    continue

                print(f"      ✅ 前期强势表现: {limit_up_pattern['pattern_type']}，{limit_up_count}次涨停，最长连续{max_consecutive}天")

                # 条件3: 检查支撑位（包括缺口支撑和其他类型支撑）
                gap_analysis = await self.kline_data_service.analyze_gap_support(stock_id, trade_date)

                has_gap_support = gap_analysis.get('is_gap_support', False)
                has_support = gap_analysis.get('has_support', False)
                support_strength = gap_analysis.get('support_strength', 0.0)
                support_level = gap_analysis.get('support_level', 0.0)
                gap_support_level = gap_analysis.get('gap_support_level', 0.0)

                # 根据涨停模式判断是否需要缺口支撑
                requires_gap = self._requires_gap_support(limit_up_pattern)

                # 判断是否到达支撑位
                has_valid_support = False
                support_type = ''

                if has_gap_support:
                    has_valid_support = True
                    support_type = 'gap'
                    support_level = gap_support_level
                    print(f"      ✅ 缺口支撑: {support_level:.2f}")
                elif has_support and support_strength >= 0.6:
                    # 检查是否需要缺口支撑
                    if requires_gap:
                        print(f"      ⚠️  需要缺口支撑但未检测到（检测到{support_type}支撑，强度:{support_strength:.1f}）")
                        has_valid_support = False
                    else:
                        has_valid_support = True
                        support_type = gap_analysis.get('support_type', 'unknown')
                        print(f"      ✅ {support_type}支撑: {support_level:.2f} (强度:{support_strength:.1f})")
                else:
                    if requires_gap:
                        print(f"      ⚠️  需要缺口支撑但未检测到（无有效支撑或强度不足）")
                    else:
                        print(f"      ⚠️  无有效支撑位或支撑强度不足 (has_support={has_support}, strength={support_strength:.1f})")

                # 如果没有有效支撑位，手动检查历史缺口作为后备
                if not has_valid_support:
                    print(f"      ⚠️  算法未检测到有效支撑位，手动检查历史缺口...")
                    # 手动检查历史缺口（类似screening_direct中的逻辑）
                    history_query = """
                    SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
                    FROM subject_stock_daily_snapshot
                    WHERE stock_id = $1 AND trade_date <= $2 AND trade_date >= $2 - INTERVAL '20 days'
                    ORDER BY trade_date
                    """
                    history_rows = await self.conn.fetch(history_query, stock_id, trade_date)

                    # 查找缺口
                    gaps = []
                    for j in range(1, len(history_rows)):
                        prev = history_rows[j-1]
                        curr = history_rows[j]

                        prev_close = float(prev['close_price']) if prev['close_price'] else 0
                        curr_open = float(curr['open_price']) if curr['open_price'] else 0

                        if prev_close <= 0 or curr_open <= 0:
                            continue

                        # 检查向上缺口
                        if curr_open > prev_close * 1.001:  # 0.1%阈值
                            gap_size = (curr_open - prev_close) / prev_close * 100
                            gap_info = {
                                'date': curr['trade_date'],
                                'type': 'up',
                                'gap_range': (prev_close, curr_open),
                                'size_pct': gap_size
                            }
                            gaps.append(gap_info)

                    # 检查当前价格是否回补了关键缺口（选择最早且显著的缺口作为关键支撑位）
                    current_low = float(row['low_price']) if row['low_price'] else 0

                    if gaps:
                        # 选择最早且显著的缺口作为关键支撑位
                        # 优先选择最早出现的缺口（通常是突破缺口），且缺口大小 > 0.5%
                        significant_gaps = [g for g in gaps if g['size_pct'] > 0.5]
                        if significant_gaps:
                            # 按日期排序，选择最早的显著缺口
                            significant_gaps.sort(key=lambda x: x['date'])
                            key_gap = significant_gaps[0]
                        else:
                            # 如果没有显著缺口，选择最早的缺口
                            gaps.sort(key=lambda x: x['date'])
                            key_gap = gaps[0]

                        gap_lower, gap_upper = key_gap['gap_range']
                        print(f"      关键缺口: [{gap_lower:.2f}, {gap_upper:.2f}] date={key_gap['date']}, size={key_gap['size_pct']:.2f}%")

                        # 只有价格跌破关键缺口下沿才算到达支撑位
                        if current_low <= gap_lower:
                            print(f"      ✅ 价格已回补关键缺口，支撑位: {gap_lower:.2f}")
                            has_valid_support = True
                            support_type = 'gap_manual'
                            support_level = gap_lower
                            gap_support_level = gap_lower
                        else:
                            print(f"      ⚠️  价格未回补关键缺口（当前最低{current_low:.2f} > 缺口下沿{gap_lower:.2f}）")
                    else:
                        print(f"      未发现历史缺口")

                # 弱转强条件：前期强势 + 当日弱势下跌 + 到达支撑位
                if has_strong_history and pct_chg < -2.0 and has_valid_support:
                    print(f"      🎯 弱转强候选股！")

                    # 获取完整的强势股分析用于记录
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
                else:
                    print(f"      ❌ 不满足弱转强条件")

        print(f"\n{'='*70}")
        print(f"筛选完成，找到 {len(candidates)} 个弱转强候选股")
        for cand in candidates:
            pattern_type = cand['limit_up_pattern']['pattern_type']
            gap_support = cand.get('gap_support_level', 0)
            support_type = cand.get('support_type', 'unknown')
            print(f"  {cand['stock_id']} {cand['stock_name']}: 跌{cand['pct_chg']:.1f}%, {pattern_type}, 支撑位{gap_support:.2f} ({support_type}), 主题: {cand['theme_key']}")

        return candidates

    async def screening_direct(self, trade_date: date):
        """直接弱转强筛选 - 不依赖主题过滤，真正基于个股条件"""
        print(f"\n🎯 执行直接弱转强筛选 - {trade_date}")
        print("=" * 70)

        candidates = []

        # 查询所有当日弱势下跌的股票（去重，每只股票只取rank_order最小的记录）
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

            if i % 20 == 0:
                print(f"  分析进度: {i+1}/{len(rows)}")

            # 条件1: 当日弱势下跌 (<-2%) - 已经满足

            # 条件2: 检查前期是否强势股
            limit_up_pattern = await self.strong_stock_analysis_service._analyze_limit_up_pattern(
                stock_id, trade_date, trading_days=7
            )

            has_strong_history = limit_up_pattern['has_limit_up_pattern']
            limit_up_count = limit_up_pattern['limit_up_count']
            max_consecutive = limit_up_pattern['max_consecutive_days']
            pattern_type = limit_up_pattern['pattern_type']
            requires_gap = self._requires_gap_support(limit_up_pattern)

            if not has_strong_history:
                continue

            # 条件3: 检查支撑位（包括缺口支撑和其他类型支撑）
            gap_analysis = await self.kline_data_service.analyze_gap_support(stock_id, trade_date)

            has_gap_support = gap_analysis.get('is_gap_support', False)
            has_support = gap_analysis.get('has_support', False)
            support_strength = gap_analysis.get('support_strength', 0.0)
            support_level = gap_analysis.get('support_level', 0.0)
            gap_support_level = gap_analysis.get('gap_support_level', 0.0)

            # 判断是否到达支撑位
            has_valid_support = False
            support_type = ''

            if has_gap_support:
                has_valid_support = True
                support_type = 'gap'
                support_level = gap_support_level
                print(f"      ✅ 缺口支撑: {support_level:.2f}")
            elif has_support and support_strength >= 0.6:
                # 检查是否需要缺口支撑
                if requires_gap:
                    print(f"      ⚠️  需要缺口支撑但未检测到（检测到{support_type}支撑，强度:{support_strength:.1f}）")
                    has_valid_support = False
                else:
                    has_valid_support = True
                    support_type = gap_analysis.get('support_type', 'unknown')
                    print(f"      ✅ {support_type}支撑: {support_level:.2f} (强度:{support_strength:.1f})")
            else:
                if requires_gap:
                    print(f"      ⚠️  需要缺口支撑但未检测到（无有效支撑或强度不足）")
                else:
                    print(f"      ⚠️  无有效支撑位或支撑强度不足 (has_support={has_support}, strength={support_strength:.1f})")

            # 如果没有有效支撑位，手动检查历史缺口作为后备
            if not has_valid_support:
                # 获取更多历史数据（20天）手动检查缺口
                history_query = """
                SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
                FROM subject_stock_daily_snapshot
                WHERE stock_id = $1 AND trade_date <= $2 AND trade_date >= $2 - INTERVAL '20 days'
                ORDER BY trade_date
                """
                history_rows = await self.conn.fetch(history_query, stock_id, trade_date)

                # 查找缺口
                gaps = []
                for j in range(1, len(history_rows)):
                    prev = history_rows[j-1]
                    curr = history_rows[j]

                    prev_close = float(prev['close_price']) if prev['close_price'] else 0
                    curr_open = float(curr['open_price']) if curr['open_price'] else 0

                    if prev_close <= 0 or curr_open <= 0:
                        continue

                    # 检查向上缺口
                    if curr_open > prev_close * 1.001:  # 0.1%阈值
                        gap_size = (curr_open - prev_close) / prev_close * 100
                        gap_info = {
                            'date': curr['trade_date'],
                            'type': 'up',
                            'gap_range': (prev_close, curr_open),
                            'size_pct': gap_size
                        }
                        gaps.append(gap_info)

                # 检查当前价格是否回补了关键缺口（选择最早且显著的缺口作为关键支撑位）
                current_low = float(row['low_price']) if row['low_price'] else 0
                print(f"      DEBUG manual gap analysis: current_low={current_low:.2f}, gaps count={len(gaps)}")

                if gaps:
                    # 选择最早且显著的缺口作为关键支撑位
                    # 优先选择最早出现的缺口（通常是突破缺口），且缺口大小 > 0.5%
                    significant_gaps = [g for g in gaps if g['size_pct'] > 0.5]
                    if significant_gaps:
                        # 按日期排序，选择最早的显著缺口
                        significant_gaps.sort(key=lambda x: x['date'])
                        key_gap = significant_gaps[0]
                    else:
                        # 如果没有显著缺口，选择最早的缺口
                        gaps.sort(key=lambda x: x['date'])
                        key_gap = gaps[0]

                    gap_lower, gap_upper = key_gap['gap_range']
                    print(f"      DEBUG key gap: [{gap_lower:.2f}, {gap_upper:.2f}] date={key_gap['date']}, size={key_gap['size_pct']:.2f}%")

                    # 只有价格跌破关键缺口下沿才算到达支撑位
                    if current_low <= gap_lower:
                        print(f"      DEBUG price <= key gap lower, setting has_valid_support=True")
                        has_valid_support = True
                        support_type = 'gap_manual'
                        support_level = gap_lower
                        gap_support_level = gap_lower
                    else:
                        print(f"      DEBUG price ({current_low:.2f}) > key gap lower ({gap_lower:.2f}), no gap support")
                else:
                    print(f"      DEBUG no gaps found")

            # 弱转强条件：前期强势 + 当日弱势下跌 + 到达支撑位
            print(f"      DEBUG: has_strong_history={has_strong_history}, pct_chg={pct_chg}, has_valid_support={has_valid_support}")
            if has_strong_history and pct_chg < -2.0 and has_valid_support:
                print(f"  🎯 发现弱转强候选股: {stock_id} {stock_name}")
                print(f"     跌幅: {pct_chg:.1f}%, 涨停模式: {pattern_type}, 支撑位: {support_level:.2f} ({support_type})")

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

        print(f"\n{'='*70}")
        print(f"直接筛选完成，找到 {len(candidates)} 个弱转强候选股")
        for cand in candidates:
            pattern_type = cand['limit_up_pattern']['pattern_type']
            gap_support = cand.get('gap_support_level', 0)
            print(f"  {cand['stock_id']} {cand['stock_name']}: 跌{cand['pct_chg']:.1f}%, {pattern_type}, 支撑位{gap_support:.2f}, 主题: {cand['theme_key']}")

        return candidates


async def main():
    screener = EnhancedWeakToStrongScreener()
    await screener.connect()

    # 测试日期：4/7日（神剑股份弱转强日）
    test_date = date(2026, 4, 7)

    print(f"测试直接弱转强筛选 - {test_date}")
    print("=" * 70)

    candidates = await screener.screening_direct(test_date)

    # 特别检查神剑股份
    print(f"\n特别检查神剑股份 (002361):")
    shenjian_found = any(c['stock_id'] == '002361' for c in candidates)
    if shenjian_found:
        print("✅ 神剑股份被识别为弱转强候选股！")
    else:
        print("❌ 神剑股份未被识别为弱转强候选股")

        # 分析原因
        print("\n分析原因:")
        # 检查神剑股份是否在潜力主题中
        themes = await screener.get_potential_themes_with_history(test_date)

        # 获取神剑股份的主题
        query = """
        SELECT DISTINCT subject_key
        FROM subject_stock_daily_snapshot
        WHERE stock_id = '002361' AND trade_date = $1
        """
        shenjian_themes = await screener.conn.fetch(query, test_date)

        print(f"  神剑股份所属主题: {[t['subject_key'] for t in shenjian_themes]}")
        print(f"  潜力主线主题: {themes[:10]}")

        # 检查交集
        shenjian_theme_keys = [t['subject_key'] for t in shenjian_themes]
        intersection = set(shenjian_theme_keys) & set(themes)
        if intersection:
            print(f"  ✅ 神剑股份主题在潜力主线中: {intersection}")
        else:
            print(f"  ❌ 神剑股份主题不在潜力主线中")

            # 检查单个主题的历史事件
            for theme_key in shenjian_theme_keys:
                history_query = """
                SELECT COUNT(*) as event_count, COUNT(CASE WHEN heat_name = '热' THEN 1 END) as hot_count
                FROM theme_history_event
                WHERE subject_key = $1 AND rank_date <= $2 AND rank_date >= $2 - INTERVAL '30 days'
                """
                history_row = await screener.conn.fetchrow(history_query, theme_key, test_date)
                if history_row:
                    print(f"    主题 {theme_key}: {history_row['event_count']}事件, {history_row['hot_count']}热点")

    await screener.close()


if __name__ == "__main__":
    asyncio.run(main())
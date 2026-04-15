#!/usr/bin/env python3
"""
真实数据库弱转强筛选 - 增强版
使用实际数据库中的4/10日股票数据和前一日数据运行弱转强筛选
"""
import asyncio
import asyncpg
import sys
import os
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
import json

# 添加stock_service到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs
from stock_service.models import ThemeCycleJudgement, StockAbnormalSignal, StrongStockRecord
from stock_service.services.strong_stock_tracker_service import StrongStockTrackerService
from stock_service.services.stock_screener_service import StockScreenerService
from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.kline_data_service import KlineDataService


class RealDatabaseScreener:
    """真实数据库筛选器"""

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

    async def disconnect(self):
        """断开数据库连接"""
        if self.conn:
            await self.conn.close()
            print("数据库连接已关闭")

    async def get_main_theme_subject_keys(self, trade_date: date) -> List[str]:
        """获取主线主题和潜力主题的subject_key列表"""
        try:
            all_subject_keys = set()

            # 1. 获取当前主线主题（近3天≥2天为主线）
            main_theme_keys = await self._get_current_main_themes(trade_date)
            all_subject_keys.update(main_theme_keys)
            print(f"   获取到 {len(main_theme_keys)} 个当前主线主题")

            # 2. 获取潜力主线主题（有资金流入、有涨停股、热度上升）
            potential_theme_keys = await self._get_potential_themes(trade_date)
            all_subject_keys.update(potential_theme_keys)
            print(f"   获取到 {len(potential_theme_keys)} 个潜力主线主题")

            # 3. 去重后返回
            result = list(all_subject_keys)
            print(f"   总计 {len(result)} 个候选主题（当前主线 + 潜力主线）")

            # 打印部分主题
            if result:
                print(f"   前5个候选主题:")
                for i, key in enumerate(result[:5]):
                    print(f"     {i+1}. {key}")

            return result
        except Exception as e:
            print(f"获取主题失败: {e}")
            return []

    async def _get_current_main_themes(self, trade_date: date) -> List[str]:
        """获取当前主线主题 - 近3天≥2天为主线"""
        try:
            query = """
            WITH theme_days AS (
                SELECT
                    subject_key,
                    COUNT(*) as total_days,
                    SUM(CASE WHEN is_main_theme = TRUE THEN 1 ELSE 0 END) as main_theme_days
                FROM theme_mainline_judgement
                WHERE trade_date >= $1::date - 2 AND trade_date <= $1
                GROUP BY subject_key
            )
            SELECT subject_key, main_theme_days, total_days
            FROM theme_days
            WHERE main_theme_days >= 2  -- 至少2天是主线
            ORDER BY main_theme_days DESC, subject_key
            """
            rows = await self.conn.fetch(query, trade_date)
            subject_keys = [row['subject_key'] for row in rows]

            if subject_keys:
                print(f"     当前主线主题（近3天≥2天为主线）:")
                for row in rows[:3]:
                    print(f"       主题 {row['subject_key']}: {row['main_theme_days']}/{row['total_days']} 天为主线")

            return subject_keys
        except Exception as e:
            print(f"获取当前主线主题失败: {e}")
            return []

    async def _get_potential_themes(self, trade_date: date) -> List[str]:
        """获取潜力主线主题 - 有资金流入、有涨停股、热度上升"""
        try:
            # 查询当日有资金流入、有涨停股、表现较好的主题
            # 优先考虑有大量涨停股或龙头股的主题，即使资金流入较少
            query = """
            SELECT
                ss.subject_key,
                COUNT(DISTINCT ss.stock_id) as stock_count,
                SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
                AVG(ss.pct_chg) as avg_pct_chg,
                SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) as limit_up_count,
                SUM(CASE WHEN ss.is_leader = TRUE THEN 1 ELSE 0 END) as leader_count,
                -- 计算综合评分：涨停股和龙头股权重更高
                CASE
                    WHEN SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) >= 10 THEN 100  -- 大量涨停股
                    WHEN SUM(CASE WHEN ss.is_leader = TRUE THEN 1 ELSE 0 END) >= 2 THEN 90   -- 多个龙头股
                    ELSE (SUM(COALESCE(mf.main_net_inflow, 0)) / 100000000) * 10  -- 资金流入每1亿得10分
                END as theme_score
            FROM subject_stock_daily_snapshot ss
            LEFT JOIN money_flow_enhanced mf
                ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
            WHERE ss.trade_date = $1
            GROUP BY ss.subject_key
            HAVING
                COUNT(DISTINCT ss.stock_id) >= 3  -- 至少3只股票
                AND (
                    -- 条件1：有资金流入
                    SUM(COALESCE(mf.main_net_inflow, 0)) > 100000000  -- 1亿以上资金流入
                    OR
                    -- 条件2：有涨停股且主题表现好
                    (SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) >= 1 AND AVG(ss.pct_chg) > 0)
                    OR
                    -- 条件3：有龙头股且主题表现好
                    (SUM(CASE WHEN ss.is_leader = TRUE THEN 1 ELSE 0 END) >= 1 AND AVG(ss.pct_chg) > 0)
                    OR
                    -- 条件4：有大量涨停股（≥5个），即使资金流入较少
                    SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) >= 5
                )
            ORDER BY
                theme_score DESC,
                limit_up_count DESC,
                leader_count DESC,
                avg_pct_chg DESC
            LIMIT 30  -- 增加限制，包含更多主题
            """
            rows = await self.conn.fetch(query, trade_date)
            subject_keys = [row['subject_key'] for row in rows]

            if subject_keys:
                print(f"     潜力主线主题（有资金/涨停/龙头）:")
                for row in rows[:3]:
                    inflow_text = f"资金流入{row['total_inflow']/100000000:.2f}亿" if row['total_inflow'] > 100000000 else f"资金流入{row['total_inflow']:.0f}"
                    print(f"       主题 {row['subject_key']}: {row['stock_count']}只股票, {inflow_text}, {row['limit_up_count']}涨停, 均涨{row['avg_pct_chg']:.1f}%")

            return subject_keys
        except Exception as e:
            print(f"获取潜力主题失败: {e}")
            return []

    async def _get_themes_with_capital_evidence(self, trade_date: date) -> List[str]:
        """基于资金面证据获取主题列表（当没有明确主线时使用）"""
        try:
            # 查询当日有主力资金流入的主题
            query = """
            SELECT
                ss.subject_key,
                COUNT(DISTINCT ss.stock_id) as stock_count,
                SUM(CASE WHEN mf.main_net_inflow > 0 THEN 1 ELSE 0 END) as inflow_stocks,
                SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
                AVG(ss.pct_chg) as avg_pct_chg
            FROM subject_stock_daily_snapshot ss
            LEFT JOIN money_flow_enhanced mf
                ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
            WHERE ss.trade_date = $1
            GROUP BY ss.subject_key
            HAVING
                COUNT(DISTINCT ss.stock_id) >= 3  -- 至少3只股票
                AND SUM(COALESCE(mf.main_net_inflow, 0)) > 0  -- 总资金流入为正
                AND AVG(ss.pct_chg) > 0  -- 平均上涨
            ORDER BY total_inflow DESC, avg_pct_chg DESC
            LIMIT 10
            """
            rows = await self.conn.fetch(query, trade_date)
            print(f"    资金面主题查询返回 {len(rows)} 行数据")
            if rows:
                for row in rows[:3]:
                    print(f"      主题 {row['subject_key']}: {row['stock_count']}只股票, 资金流入{row['total_inflow']:.0f}, 均涨{row['avg_pct_chg']:.1f}%")
            subject_keys = [row['subject_key'] for row in rows]


            return subject_keys
        except Exception as e:
            print(f"基于资金面获取主题失败: {e}")
            return []

    async def get_stock_data_with_prev_day(self, trade_date: date, limit: int = 100) -> List[Dict[str, Any]]:
        """获取股票数据及前一日数据（只选择主线主题中的股票）"""
        try:
            prev_date = trade_date - timedelta(days=1)

            # 获取主线主题列表
            main_theme_subject_keys = await self.get_main_theme_subject_keys(trade_date)

            if not main_theme_subject_keys:
                print("   警告：未找到主线主题，无法筛选弱转强候选")
                return []

            # 获取属于主线主题的股票数据，使用LEFT JOIN处理前一日数据缺失
            query = """
            SELECT
                t1.stock_id,
                t1.stock_name,
                t1.subject_key,
                t1.pct_chg as today_pct_chg,
                t1.is_leader as today_is_leader,
                t1.rank_order,
                t2.pct_chg as prev_pct_chg,
                t2.is_leader as prev_is_leader,
                CASE
                    WHEN t2.pct_chg IS NULL THEN FALSE  -- 前一日无数据，不算弱势
                    WHEN t2.pct_chg < -2.0 THEN TRUE
                    ELSE FALSE
                END as prev_day_weak,
                CASE
                    WHEN t1.pct_chg > 0 AND t1.pct_chg > COALESCE(t2.pct_chg, 0) + 3.0 THEN TRUE
                    ELSE FALSE
                END as today_strong,
                t1.open_price,
                t1.high_price,
                t1.low_price,
                t1.close_price,
                t1.volume,
                t1.amount,
                t1.limit_up
            FROM subject_stock_daily_snapshot t1
            LEFT JOIN subject_stock_daily_snapshot t2
                ON t1.stock_id = t2.stock_id
                AND t2.trade_date = $2
            WHERE t1.trade_date = $1
              AND t1.subject_key = ANY($3)  -- 只选择主线主题
            ORDER BY t1.rank_order ASC
            LIMIT $4
            """

            rows = await self.conn.fetch(query, trade_date, prev_date, main_theme_subject_keys, limit)

            result = []
            for row in rows:
                stock_data = dict(row)
                result.append(stock_data)

            print(f"   获取到 {len(result)} 条有前一日数据的主线主题股票记录")
            return result
        except Exception as e:
            print(f"获取股票数据失败: {e}")
            return []

    async def get_theme_for_subject_key(self, subject_key: str) -> Dict[str, Any]:
        """根据subject_key获取主题信息"""
        try:
            # 尝试在theme_master中查找
            query = """
            SELECT name, code, heat_score, status, description
            FROM theme_master
            WHERE code = $1
            LIMIT 1
            """

            rows = await self.conn.fetch(query, subject_key)

            if rows:
                theme = dict(rows[0])
                return {
                    'name': theme.get('name', f'主题_{subject_key}'),
                    'code': theme.get('code', subject_key),
                    'heat_score': theme.get('heat_score', 50),
                    'status': theme.get('status', 'unknown'),
                    'description': theme.get('description', '')
                }

            # 如果未找到，返回默认主题信息
            return {
                'name': f'主题_{subject_key}',
                'code': subject_key,
                'heat_score': 50,
                'status': 'unknown',
                'description': f'主题代码: {subject_key}'
            }
        except Exception as e:
            print(f"获取主题信息失败: {e}")
            return {
                'name': f'主题_{subject_key}',
                'code': subject_key,
                'heat_score': 50,
                'status': 'unknown',
                'description': f'主题代码: {subject_key}'
            }

    async def get_hot_themes(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取热点主题"""
        try:
            query = """
            SELECT name, code, heat_score, status, description
            FROM theme_master
            WHERE status = 'active'
            AND heat_score >= 60
            ORDER BY heat_score DESC
            LIMIT $1
            """

            rows = await self.conn.fetch(query, limit)

            themes = []
            for row in rows:
                theme = dict(row)
                themes.append(theme)

            return themes
        except Exception as e:
            print(f"获取热点主题失败: {e}")
            return []

    async def analyze_stock_weak_to_strong(self, trade_date: date, stock: Dict[str, Any], theme_name: str) -> tuple[bool, Dict[str, Any]]:
        """分析股票弱转强信号（使用真实数据），集成PDF框架强势股分析和真实K线数据"""
        stock_id = stock.get('stock_id', '')
        stock_name = stock.get('stock_name', '')

        # 使用真实的前一日和今日涨跌幅数据
        prev_pct_chg = stock.get('prev_pct_chg')
        today_pct_chg = stock.get('today_pct_chg')

        # 转换Decimal为float
        prev_pct_chg_float = float(prev_pct_chg) if prev_pct_chg is not None else None
        today_pct_chg_float = float(today_pct_chg) if today_pct_chg is not None else None

        # 1. 首先分析今日股票是否为强势股（基于PDF框架）
        print(f"     分析股票{stock_id} ({stock_name})的强势股属性...")

        # 构建今日股票数据字典用于PDF分析
        today_stock_data = {
            'stock_id': stock_id,
            'stock_name': stock_name,
            'trade_date': trade_date,
            'open_price': stock.get('open_price'),
            'high_price': stock.get('high_price'),
            'low_price': stock.get('low_price'),
            'close_price': stock.get('close_price'),
            'pre_close': None,  # 前收盘价，可能需要计算
            'pct_chg': today_pct_chg,
            'change_amount': None,
            'volume': stock.get('volume'),
            'amount': stock.get('amount'),
            'limit_up': stock.get('limit_up'),
            'is_leader': stock.get('today_is_leader'),
            'rank_order': stock.get('rank_order'),
            'subject_key': stock.get('subject_key')
        }

        # 进行PDF框架强势股分析
        strong_analysis = await self.strong_stock_analysis_service.analyze_stock_by_pdf_framework(
            stock_id,
            trade_date,
            today_stock_data
        )

        # 检查是否为强势股
        is_strong_stock = strong_analysis.get('is_strong_stock', False)
        overall_score = strong_analysis.get('overall_score', 0.0)

        print(f"       强势股分析结果: {'✅ 是强势股' if is_strong_stock else '❌ 非强势股'} (总体评分: {overall_score:.1f}/100)")

        # 如果不是强势股，直接返回（杂毛不配弱转强）
        if not is_strong_stock:
            print(f"       ❌ 股票不是强势股，跳过弱转强分析")
            return False, {
                'is_strong_stock': False,
                'overall_score': overall_score,
                'prev_day_weak': False,
                'today_strong': False,
                'prev_pct_chg': prev_pct_chg_float,
                'today_pct_chg': today_pct_chg_float,
                'signal_strength': 0,
                'confidence_score': 0,
                'strong_analysis': strong_analysis
            }

        # 2. 使用真实K线数据分析缺口支撑
        print(f"       进行真实K线数据分析...")
        gap_support_analysis = {}
        try:
            # 获取缺口支撑分析
            gap_support_analysis = await self.kline_data_service.analyze_gap_support(stock_id, trade_date)

            if gap_support_analysis.get('has_gap'):
                print(f"       发现缺口: {gap_support_analysis.get('gap_type', '')}, 大小: {gap_support_analysis.get('gap_size', 0):.2f}%")

            if gap_support_analysis.get('has_support'):
                print(f"       发现支撑位: {gap_support_analysis.get('support_type', '')}, 强度: {gap_support_analysis.get('support_strength', 0):.1f}")

            if gap_support_analysis.get('technical_signals'):
                for signal in gap_support_analysis.get('technical_signals', [])[:3]:
                    print(f"       技术信号: {signal}")

        except Exception as e:
            print(f"       K线数据分析失败: {e}")

        # 3. 获取真实的K线数据用于分析
        prev_kline = None
        current_kline = None
        try:
            # 获取前一日和当日K线数据
            prev_kline, current_kline = await self.kline_data_service.get_prev_and_current_kline(stock_id, trade_date)

            if prev_kline:
                prev_pct_chg_float = float(prev_kline.get('pct_chg', 0)) if prev_kline.get('pct_chg') is not None else prev_pct_chg_float

            if current_kline:
                today_pct_chg_float = float(current_kline.get('pct_chg', 0)) if current_kline.get('pct_chg') is not None else today_pct_chg_float

        except Exception as e:
            print(f"       获取K线数据失败: {e}")

        # 4. 判断前一日是否弱势（基于真实K线数据）
        prev_day_weak = False
        weak_reasons = []

        if prev_pct_chg_float is not None:
            # 根据PDF规则：大阴线、上影线、烂板
            if prev_pct_chg_float < -2.0:
                prev_day_weak = True
                weak_reasons.append(f"大阴线下跌{prev_pct_chg_float:.2f}%")

            # 检查是否是烂板（如果有K线数据）
            if prev_kline:
                # 烂板特征：涨停但反复开板（需要更详细的数据）
                if prev_kline.get('limit_up', False) and prev_kline.get('pct_chg', 0) < 9.0:
                    # 涨停但涨幅不足，可能是烂板
                    prev_day_weak = True
                    weak_reasons.append("烂板特征")

        # 5. 判断今日是否转强
        today_strong = False
        strong_reasons = []

        if today_pct_chg_float is not None and prev_pct_chg_float is not None:
            # 今日上涨且比前一日表现好
            if today_pct_chg_float > 0 and today_pct_chg_float > prev_pct_chg_float + 3.0:
                today_strong = True
                strong_reasons.append(f"涨幅转强: {prev_pct_chg_float:.2f}% → {today_pct_chg_float:.2f}%")

            # 前一日大跌，今日止跌或上涨
            elif prev_pct_chg_float < -5.0 and today_pct_chg_float > -1.0:
                today_strong = True
                strong_reasons.append(f"止跌转强: 前一日大跌{prev_pct_chg_float:.2f}%，今日止跌{today_pct_chg_float:.2f}%")

            # 涨停转强
            if today_pct_chg_float >= 9.9:
                today_strong = True
                strong_reasons.append(f"涨停转强: {today_pct_chg_float:.2f}%")

            # 资金流入转强（如果有资金数据）
            if current_kline and current_kline.get('amount', 0) > 0 and prev_kline:
                volume_ratio = current_kline.get('amount', 0) / max(prev_kline.get('amount', 1), 1)
                if volume_ratio > 1.5:
                    today_strong = True
                    strong_reasons.append(f"放量转强: 成交量放大{volume_ratio:.1f}倍")

        # 6. 计算弱转强信号强度（基于真实数据）
        signal_strength = self._calculate_weak_to_strong_strength(
            prev_pct_chg_float, today_pct_chg_float,
            prev_day_weak, today_strong,
            gap_support_analysis, overall_score,
            prev_kline, current_kline
        )

        confidence_score = self._calculate_weak_to_strong_confidence(
            prev_pct_chg_float, today_pct_chg_float,
            gap_support_analysis, overall_score,
            is_strong_stock
        )

        # 7. 判断是否为弱转强
        is_weak_to_strong = (
            is_strong_stock and
            prev_day_weak and
            today_strong and
            signal_strength >= 60.0 and
            confidence_score >= 60.0
        )

        # 8. 创建分析结果
        analysis = {
            'is_strong_stock': is_strong_stock,
            'strong_stock_overall_score': overall_score,
            'strong_stock_dimensions': strong_analysis.get('dimensions', {}),
            'signal_strength': signal_strength,
            'confidence_score': confidence_score,
            'signal_type': '弱转强' if is_weak_to_strong else '转强信号',
            'is_divergence_rebound': prev_day_weak and today_strong,
            'is_support_bounce': gap_support_analysis.get('has_support', False),
            'has_support': gap_support_analysis.get('has_support', False),
            'support_type': gap_support_analysis.get('support_type', ''),
            'is_gap_support': gap_support_analysis.get('is_gap_support', False),
            'prev_day_weak': prev_day_weak,
            'today_strong': today_strong,
            'prev_pct_chg': prev_pct_chg_float,
            'today_pct_chg': today_pct_chg_float,
            'gap_analysis': gap_support_analysis,
            'weak_reasons': weak_reasons,
            'strong_reasons': strong_reasons,
            'evidence': []
        }

        # 添加证据
        evidence = []
        if is_strong_stock:
            evidence.append(f"强势股评分: {overall_score:.1f}/100")

        if prev_day_weak and weak_reasons:
            evidence.append(f"前一日弱势: {', '.join(weak_reasons)}")

        if today_strong and strong_reasons:
            evidence.append(f"今日转强: {', '.join(strong_reasons)}")

        if gap_support_analysis.get('has_support'):
            evidence.append(f"支撑位: {gap_support_analysis.get('support_type', '')}")

        if gap_support_analysis.get('is_gap_support'):
            evidence.append(f"缺口支撑: 有效")

        analysis['evidence'] = evidence

        # 输出结果
        if is_weak_to_strong:
            print(f"      ✅ 检测到弱转强信号: 评分={signal_strength:.1f}, 置信度={confidence_score:.1f}")
            print(f"        支撑位: {gap_support_analysis.get('support_type', '无')}, 缺口支撑: {gap_support_analysis.get('is_gap_support', False)}")
        else:
            print(f"      ⚠️  弱转强信号不足: 评分={signal_strength:.1f}, 置信度={confidence_score:.1f}")
            if not prev_day_weak:
                print(f"        前一日不弱势: {prev_pct_chg_float:.2f}%")
            if not today_strong:
                print(f"        今日不强势: {today_pct_chg_float:.2f}%")
            if signal_strength < 60.0:
                print(f"        信号强度不足: {signal_strength:.1f} < 60.0")
            if confidence_score < 60.0:
                print(f"        置信度不足: {confidence_score:.1f} < 60.0")

        return is_weak_to_strong, analysis

    async def run_screening(self, trade_date: date, stock_limit: int = 100):
        """运行弱转强筛选"""
        print(f"\n{'='*70}")
        print(f"真实数据弱转强筛选流程 - {trade_date}")
        print(f"{'='*70}")

        # 连接数据库
        await self.connect()

        try:
            # 1. 获取股票数据及前一日数据
            print(f"\n1. 获取股票数据及前一日数据...")
            stocks = await self.get_stock_data_with_prev_day(trade_date, stock_limit)
            print(f"   获取到 {len(stocks)} 条股票数据")

            if not stocks:
                print("   ⚠️ 未找到股票数据")
                return {'trade_date': trade_date.isoformat(), 'candidates': [], 'error': 'No stock data'}

            # 2. 获取热点主题
            print(f"\n2. 获取热点主题...")
            hot_themes = await self.get_hot_themes(limit=20)
            print(f"   获取到 {len(hot_themes)} 个热点主题")

            if not hot_themes:
                print("   ⚠️ 未找到热点主题，使用默认主题")

            # 3. 筛选弱转强候选
            print(f"\n3. 筛选弱转强候选...")
            candidates = []
            seen_stock_ids = set()
            duplicate_count = 0

            for i, stock in enumerate(stocks):
                stock_id = stock.get('stock_id', '')
                stock_name = stock.get('stock_name', '')
                subject_key = stock.get('subject_key', '')

                # 去重：同一股票可能出现在多个主题中，只保留第一个（按rank_order排序）
                if stock_id in seen_stock_ids:
                    duplicate_count += 1
                    continue
                seen_stock_ids.add(stock_id)

                # 获取主题信息
                theme_info = await self.get_theme_for_subject_key(subject_key)
                theme_name = theme_info['name']

                # 分析弱转强信号
                is_candidate, analysis = await self.analyze_stock_weak_to_strong(trade_date, stock, theme_name)

                if is_candidate:
                    candidate = {
                        'stock_id': stock_id,
                        'stock_name': stock_name,
                        'theme_name': theme_name,
                        'subject_key': subject_key,
                        'analysis': analysis,
                        'weak_to_strong_score': analysis.get('signal_strength', 0),
                        'confidence_score': analysis.get('confidence_score', 0),
                        'signal_type': analysis.get('signal_type', ''),
                        'support_type': analysis.get('support_type', ''),
                        'prev_day_weak': analysis.get('prev_day_weak', False),
                        'today_strong': analysis.get('today_strong', False),
                        'prev_pct_chg': analysis.get('prev_pct_chg'),
                        'today_pct_chg': analysis.get('today_pct_chg'),
                        'strong_stock_overall_score': analysis.get('strong_stock_overall_score', 0),
                        'is_strong_stock': analysis.get('is_strong_stock', False)
                    }
                    candidates.append(candidate)

                # 进度显示
                if (i + 1) % 20 == 0 or i + 1 == len(stocks):
                    print(f"   已分析 {i + 1}/{len(stocks)} 只股票，找到 {len(candidates)} 个候选")

            if duplicate_count > 0:
                print(f"   跳过 {duplicate_count} 个重复股票记录")

            # 按评分排序
            candidates.sort(key=lambda x: x['weak_to_strong_score'], reverse=True)

            # 4. 显示结果
            print(f"\n4. 筛选结果:")
            print(f"   共找到 {len(candidates)} 个弱转强候选股票")

            if candidates:
                print(f"\n   前{min(len(candidates), 10)}个候选股票:")
                for i, candidate in enumerate(candidates[:10], 1):
                    print(f"   {i}. {candidate['stock_name']} ({candidate['stock_id']})")
                    print(f"      主题: {candidate['theme_name']}")
                    print(f"      强势股评分: {candidate.get('strong_stock_overall_score', 0):.1f}/100 ({'强势股' if candidate.get('is_strong_stock', False) else '非强势股'})")
                    print(f"      弱转强评分: {candidate['weak_to_strong_score']:.1f}/100")
                    print(f"      置信度: {candidate['confidence_score']:.1f}%")
                    print(f"      信号类型: {candidate.get('signal_type', 'N/A')}")
                    print(f"      支撑位: {candidate.get('support_type', 'N/A')}")
                    print(f"      前一日涨跌幅: {candidate.get('prev_pct_chg', 'N/A'):.2f}%")
                    print(f"      今日涨跌幅: {candidate.get('today_pct_chg', 'N/A'):.2f}%")

            # 5. 生成强势股清单（简化）
            print(f"\n5. 生成强势股清单...")
            strong_stock_list = await self._generate_strong_stock_list(trade_date, candidates)

            print(f"   强势股清单生成完成:")
            print(f"   - 强势股: {len(strong_stock_list.get('strong_stocks', []))} 只")
            print(f"   - 弱转强候选: {len(strong_stock_list.get('weak_to_strong_candidates', []))} 只")
            print(f"   - 次日重点观察: {len(strong_stock_list.get('next_day_focus_stocks', []))} 只")

            return {
                'trade_date': trade_date.isoformat(),
                'candidates': candidates,
                'strong_stock_list': strong_stock_list,
                'total_stocks_analyzed': len(stocks)
            }

        finally:
            # 断开数据库连接
            await self.disconnect()

    def _calculate_weak_to_strong_strength(
        self,
        prev_pct_chg: float | None,
        today_pct_chg: float | None,
        prev_day_weak: bool,
        today_strong: bool,
        gap_support_analysis: Dict[str, Any],
        overall_score: float,
        prev_kline: Dict[str, Any] | None,
        current_kline: Dict[str, Any] | None
    ) -> float:
        """计算弱转强信号强度（基于真实数据）"""
        strength = 50.0  # 基础分

        # 1. 前一日弱势程度
        if prev_pct_chg is not None:
            if prev_pct_chg < -5.0:
                strength += 15.0  # 大跌
            elif prev_pct_chg < -2.0:
                strength += 10.0  # 中跌
            elif prev_pct_chg < 0:
                strength += 5.0   # 小跌

        # 2. 今日转强程度
        if today_pct_chg is not None and prev_pct_chg is not None:
            # 涨幅转强
            if today_pct_chg > 0 and today_pct_chg > prev_pct_chg + 3.0:
                strength += 10.0

            # 止跌转强
            if prev_pct_chg < -5.0 and today_pct_chg > -1.0:
                strength += 15.0

            # 涨停转强
            if today_pct_chg >= 9.9:
                strength += 20.0

        # 3. 支撑位分析
        if gap_support_analysis.get('has_support', False):
            strength += 10.0

            if gap_support_analysis.get('is_gap_support', False):
                strength += 10.0  # 缺口支撑额外加分

            support_strength = gap_support_analysis.get('support_strength', 0.0)
            strength += min(support_strength * 0.1, 5.0)  # 支撑强度加分

        # 4. 强势股评分影响
        if overall_score >= 80.0:
            strength += 10.0
        elif overall_score >= 70.0:
            strength += 5.0
        elif overall_score >= 60.0:
            strength += 2.0

        # 5. 量价配合
        if prev_kline and current_kline:
            prev_amount = prev_kline.get('amount', 0)
            curr_amount = current_kline.get('amount', 0)

            if prev_amount > 0:
                volume_ratio = curr_amount / prev_amount
                if volume_ratio > 1.5:
                    strength += 5.0
                elif volume_ratio > 2.0:
                    strength += 10.0

        # 6. K线形态（如果有技术信号）
        tech_signals = gap_support_analysis.get('technical_signals', [])
        for signal in tech_signals:
            if any(keyword in signal.lower() for keyword in ['吞没', '阳包阴', '反击', '止跌']):
                strength += 5.0

        # 限制在0-100之间
        return min(max(strength, 0.0), 100.0)

    def _calculate_weak_to_strong_confidence(
        self,
        prev_pct_chg: float | None,
        today_pct_chg: float | None,
        gap_support_analysis: Dict[str, Any],
        overall_score: float,
        is_strong_stock: bool
    ) -> float:
        """计算弱转强置信度（基于真实数据）"""
        confidence = 50.0  # 基础置信度

        # 1. 强势股状态
        if is_strong_stock:
            confidence += 10.0

            if overall_score >= 80.0:
                confidence += 10.0
            elif overall_score >= 70.0:
                confidence += 5.0

        # 2. 支撑位确认
        if gap_support_analysis.get('has_support', False):
            confidence += 10.0

            support_strength = gap_support_analysis.get('support_strength', 0.0)
            confidence += min(support_strength * 0.15, 10.0)

        # 3. 涨跌幅确定性
        if prev_pct_chg is not None and today_pct_chg is not None:
            # 明确的弱势转强
            if prev_pct_chg < -2.0 and today_pct_chg > 0:
                confidence += 10.0

            # 大涨确认
            if today_pct_chg >= 9.9:  # 涨停
                confidence += 15.0
            elif today_pct_chg >= 5.0:
                confidence += 5.0

            # 反转幅度大
            if today_pct_chg - prev_pct_chg > 10.0:
                confidence += 10.0

        # 4. 技术信号确认
        tech_signals = gap_support_analysis.get('technical_signals', [])
        if tech_signals:
            confidence += min(len(tech_signals) * 2.0, 10.0)

        # 限制在0-100之间
        return min(max(confidence, 0.0), 100.0)

    async def _generate_strong_stock_list(self, trade_date: date, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成强势股清单"""
        strong_stocks = []
        weak_to_strong_candidates = []
        next_day_focus_stocks = []

        for candidate in candidates[:20]:  # 取前20个作为强势股
            # 创建强势股记录
            strong_stock = {
                'stock_id': candidate['stock_id'],
                'stock_name': candidate['stock_name'],
                'theme_name': candidate['theme_name'],
                'dragon_head_level': "relative",
                'strong_reason': f"弱转强候选，评分{candidate['weak_to_strong_score']:.1f}",
                'first_marked_date': trade_date.isoformat(),
                'last_marked_date': trade_date.isoformat(),
                'marked_days_count': 1,
                'weak_to_strong_candidate': True,
                'next_day_focus': candidate['weak_to_strong_score'] >= 70.0
            }

            strong_stocks.append(strong_stock)

            if strong_stock['weak_to_strong_candidate']:
                weak_to_strong_candidates.append(strong_stock)

            if strong_stock['next_day_focus']:
                next_day_focus_stocks.append(strong_stock)

        return {
            'strong_stocks': strong_stocks,
            'weak_to_strong_candidates': weak_to_strong_candidates,
            'next_day_focus_stocks': next_day_focus_stocks,
            'generated_date': trade_date.isoformat()
        }


async def main():
    """主函数"""
    print("真实数据库弱转强筛选 - 增强版")
    print("=" * 70)

    # 设置交易日期：2026-04-10
    trade_date = date(2026, 4, 10)
    print(f"交易日期: {trade_date}")

    screener = RealDatabaseScreener()

    try:
        result = await screener.run_screening(trade_date, stock_limit=100)

        print(f"\n{'='*70}")
        print("筛选完成！")
        print(f"{'='*70}")

        if result['candidates']:
            print(f"✅ 成功识别 {len(result['candidates'])} 个弱转强候选股票")

            # 显示前3个最佳候选
            print(f"\n最佳候选股票:")
            for i, candidate in enumerate(result['candidates'][:3], 1):
                print(f"  {i}. {candidate['stock_name']} ({candidate['stock_id']})")
                print(f"     主题: {candidate['theme_name']}")
                print(f"     强势股评分: {candidate.get('strong_stock_overall_score', 0):.1f}/100 ({'强势股' if candidate.get('is_strong_stock', False) else '非强势股'})")
                print(f"     弱转强评分: {candidate['weak_to_strong_score']:.1f}/100")
                print(f"     前一日: {candidate.get('prev_pct_chg', 'N/A'):.2f}% → 今日: {candidate.get('today_pct_chg', 'N/A'):.2f}%")
                print(f"     信号: {candidate.get('signal_type', 'N/A')}")

            # 检查是否有高评分候选（>= 70分）
            high_score_candidates = [c for c in result['candidates'] if c['weak_to_strong_score'] >= 70.0]
            if high_score_candidates:
                print(f"\n✅ 找到 {len(high_score_candidates)} 个高评分弱转强候选（评分 >= 70）")
                print(f"   推荐重点关注: {high_score_candidates[0]['stock_name']} ({high_score_candidates[0]['stock_id']})")
            else:
                print(f"\n⚠️  未找到高评分弱转强候选（评分 >= 70）")
        else:
            print("⚠️  未找到弱转强候选股票")

        # 统计信息
        print(f"\n统计信息:")
        print(f"   分析股票数量: {result.get('total_stocks_analyzed', 0)}")
        print(f"   弱转强候选数量: {len(result['candidates'])}")

        if result['candidates']:
            avg_score = sum(c['weak_to_strong_score'] for c in result['candidates']) / len(result['candidates'])
            print(f"   平均弱转强评分: {avg_score:.1f}/100")

        return 0

    except Exception as e:
        print(f"筛选过程出现错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
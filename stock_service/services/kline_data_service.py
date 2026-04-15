#!/usr/bin/env python3
"""
K线数据服务 - 从数据库加载股票K线数据用于弱转强分析
"""
import asyncio
import asyncpg
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import json

logger = logging.getLogger(__name__)


class KlineDataService:
    """K线数据服务 - 从数据库加载股票K线数据"""

    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        self.db_config = db_config or {
            "host": "localhost",
            "port": 5432,
            "database": "stock_data_test",
            "user": "postgres",
            "password": "zxbzj~925"
        }
        self._pool = None

    async def get_connection(self) -> asyncpg.Connection:
        """获取数据库连接"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(**self.db_config, min_size=1, max_size=5)

        return await self._pool.acquire()

    async def release_connection(self, conn: asyncpg.Connection):
        """释放数据库连接"""
        await self._pool.release(conn)

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def get_kline_data(
        self,
        stock_id: str,
        trade_date: date,
        days_before: int = 5,
        days_after: int = 0
    ) -> List[Dict[str, Any]]:
        """
        获取股票在指定日期前后的K线数据

        Args:
            stock_id: 股票ID (如 '002361', '000001' 等)
            trade_date: 目标日期
            days_before: 获取目标日期前多少天的数据
            days_after: 获取目标日期后多少天的数据

        Returns:
            K线数据列表，按日期排序（从早到晚）
        """
        conn = await self.get_connection()
        try:
            # 计算日期范围
            start_date = trade_date - timedelta(days=days_before)
            end_date = trade_date + timedelta(days=days_after)

            query = """
            SELECT DISTINCT ON (trade_date)
                trade_date,
                stock_id,
                stock_name,
                open_price,
                high_price,
                low_price,
                close_price,
                pre_close,
                pct_chg,
                change_amount,
                volume,
                amount,
                limit_up,
                is_leader,
                rank_order
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1
                AND trade_date >= $2
                AND trade_date <= $3
            ORDER BY trade_date ASC, rank_order ASC
            """

            rows = await conn.fetch(query, stock_id, start_date, end_date)

            # 转换为字典列表
            kline_data = []
            for row in rows:
                record = dict(row)
                # 转换Decimal为float以便计算
                record['open_price'] = float(record['open_price']) if record['open_price'] is not None else None
                record['high_price'] = float(record['high_price']) if record['high_price'] is not None else None
                record['low_price'] = float(record['low_price']) if record['low_price'] is not None else None
                record['close_price'] = float(record['close_price']) if record['close_price'] is not None else None
                record['pct_chg'] = float(record['pct_chg']) if record['pct_chg'] is not None else None
                record['volume'] = float(record['volume']) if record['volume'] is not None else None
                record['amount'] = float(record['amount']) if record['amount'] is not None else None

                kline_data.append(record)

            logger.info(f"获取到股票{stock_id}从{start_date}到{end_date}的{len(kline_data)}条K线数据")
            return kline_data

        except Exception as e:
            logger.error(f"获取股票{stock_id}K线数据失败: {e}")
            raise
        finally:
            await self.release_connection(conn)

    async def get_daily_kline(
        self,
        stock_id: str,
        trade_date: date
    ) -> Optional[Dict[str, Any]]:
        """
        获取股票指定日期的K线数据

        Args:
            stock_id: 股票ID
            trade_date: 目标日期

        Returns:
            单日K线数据字典，如果不存在则返回None
        """
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                trade_date,
                stock_id,
                stock_name,
                open_price,
                high_price,
                low_price,
                close_price,
                pre_close,
                pct_chg,
                change_amount,
                volume,
                amount,
                limit_up,
                is_leader,
                rank_order
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1 AND trade_date = $2
            ORDER BY rank_order ASC
            LIMIT 1
            """

            row = await conn.fetchrow(query, stock_id, trade_date)

            if row:
                record = dict(row)
                # 转换Decimal为float
                record['open_price'] = float(record['open_price']) if record['open_price'] is not None else None
                record['high_price'] = float(record['high_price']) if record['high_price'] is not None else None
                record['low_price'] = float(record['low_price']) if record['low_price'] is not None else None
                record['close_price'] = float(record['close_price']) if record['close_price'] is not None else None
                record['pct_chg'] = float(record['pct_chg']) if record['pct_chg'] is not None else None
                record['volume'] = float(record['volume']) if record['volume'] is not None else None
                record['amount'] = float(record['amount']) if record['amount'] is not None else None

                return record

            return None

        except Exception as e:
            logger.error(f"获取股票{stock_id} {trade_date} K线数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def get_prev_and_current_kline(
        self,
        stock_id: str,
        current_date: date
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        获取股票前一日和当日的K线数据（用于弱转强分析）

        Args:
            stock_id: 股票ID
            current_date: 当日日期

        Returns:
            (前一日K线数据, 当日K线数据) 元组
        """
        prev_date = current_date - timedelta(days=1)

        # 同时获取两日数据，更高效
        conn = await self.get_connection()
        try:
            query = """
            SELECT DISTINCT ON (trade_date)
                trade_date,
                stock_id,
                stock_name,
                open_price,
                high_price,
                low_price,
                close_price,
                pre_close,
                pct_chg,
                change_amount,
                volume,
                amount,
                limit_up,
                is_leader,
                rank_order
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1
                AND trade_date IN ($2, $3)
            ORDER BY trade_date ASC, rank_order ASC
            """

            rows = await conn.fetch(query, stock_id, prev_date, current_date)

            prev_kline = None
            current_kline = None

            for row in rows:
                record = dict(row)
                # 转换Decimal为float
                record['open_price'] = float(record['open_price']) if record['open_price'] is not None else None
                record['high_price'] = float(record['high_price']) if record['high_price'] is not None else None
                record['low_price'] = float(record['low_price']) if record['low_price'] is not None else None
                record['close_price'] = float(record['close_price']) if record['close_price'] is not None else None
                record['pct_chg'] = float(record['pct_chg']) if record['pct_chg'] is not None else None
                record['volume'] = float(record['volume']) if record['volume'] is not None else None
                record['amount'] = float(record['amount']) if record['amount'] is not None else None

                if record['trade_date'] == prev_date:
                    prev_kline = record
                elif record['trade_date'] == current_date:
                    current_kline = record

            return prev_kline, current_kline

        except Exception as e:
            logger.error(f"获取股票{stock_id}前后两日K线数据失败: {e}")
            return None, None
        finally:
            await self.release_connection(conn)

    async def check_stock_exists(self, stock_id: str) -> bool:
        """检查股票是否存在于数据库中"""
        conn = await self.get_connection()
        try:
            query = "SELECT 1 FROM subject_stock_daily_snapshot WHERE stock_id = $1 LIMIT 1"
            row = await conn.fetchrow(query, stock_id)
            return row is not None
        finally:
            await self.release_connection(conn)

    async def get_stock_id_with_suffix(self, stock_code: str) -> str:
        """
        获取带后缀的股票ID（如果需要）

        Args:
            stock_code: 股票代码，可能带后缀也可能不带

        Returns:
            数据库中的股票ID格式
        """
        # 移除可能的.SZ/.SH后缀
        if '.' in stock_code:
            code_only = stock_code.split('.')[0]
        else:
            code_only = stock_code

        # 检查数据库中是否存在
        if await self.check_stock_exists(code_only):
            return code_only

        # 尝试带后缀查找
        for suffix in ['SZ', 'SH', 'BJ']:
            stock_id_with_suffix = f"{code_only}.{suffix}"
            if await self.check_stock_exists(stock_id_with_suffix):
                return stock_id_with_suffix

        # 如果都找不到，返回原始代码
        return stock_code

    async def analyze_gap_support(
        self,
        stock_id: str,
        analysis_date: date
    ) -> Dict[str, Any]:
        """
        分析缺口和支撑位（基于真实K线数据）

        Args:
            stock_id: 股票ID
            analysis_date: 分析日期

        Returns:
            缺口支撑分析结果
        """
        # 获取前5天和当日数据
        kline_data = await self.get_kline_data(stock_id, analysis_date, days_before=5, days_after=0)

        if len(kline_data) < 2:
            return {
                'has_gap': False,
                'gap_type': '',
                'gap_size': 0.0,
                'has_support': False,
                'support_type': '',
                'support_strength': 0.0,
                'is_gap_support': False,
                'technical_signals': ['数据不足，无法分析缺口支撑']
            }

        # 找到目标日期和前一日
        target_kline = None
        prev_kline = None

        for kline in kline_data:
            if kline['trade_date'] == analysis_date:
                target_kline = kline
            elif target_kline is None and kline['trade_date'] < analysis_date:
                # 记录前一日（可能是分析日的前一个交易日）
                prev_kline = kline

        # 如果没找到目标日期的数据，用最后一条
        if target_kline is None and kline_data:
            target_kline = kline_data[-1]
            # 前一条就是前一天
            if len(kline_data) > 1:
                prev_kline = kline_data[-2]

        if target_kline is None or prev_kline is None:
            return {
                'has_gap': False,
                'gap_type': '',
                'gap_size': 0.0,
                'has_support': False,
                'support_type': '',
                'support_strength': 0.0,
                'is_gap_support': False,
                'technical_signals': ['K线数据不足，无法分析缺口支撑']
            }

        # 缺口和支撑分析
        result = {
            'has_gap': False,
            'gap_type': '',
            'gap_position': '',
            'gap_size': 0.0,
            'has_support': False,
            'support_type': '',
            'support_strength': 0.0,
            'is_gap_support': False,
            'gap_support_level': 0.0,
            'technical_signals': []
        }

        # 检查关键价格是否存在
        if (target_kline.get('low_price') and target_kline.get('open_price') and
            prev_kline.get('high_price') and prev_kline.get('low_price')):

            current_low = target_kline['low_price']
            current_open = target_kline['open_price']
            prev_high = prev_kline['high_price']
            prev_low = prev_kline['low_price']

            gap_threshold = 0.001  # 缺口阈值0.1%

            # 向上缺口
            if current_low > prev_high * (1 + gap_threshold):
                result['has_gap'] = True
                result['gap_type'] = 'breakaway'
                result['gap_position'] = 'above'
                result['gap_size'] = (current_low - prev_high) / prev_high * 100
                result['technical_signals'].append(f"向上突破缺口: {result['gap_size']:.2f}%")

                # 缺口支撑
                gap_support = prev_high
                result['gap_support_level'] = gap_support

                # 检查是否在缺口支撑附近
                if (current_low >= gap_support * 0.99 and
                    current_low <= gap_support * 1.01):
                    result['is_gap_support'] = True
                    result['technical_signals'].append(f"缺口支撑有效: {gap_support:.2f}（回补缺口）")

                    # 如果收盘价高于支撑位，形成支撑反弹
                    if target_kline.get('close_price', 0) > gap_support:
                        result['technical_signals'].append("缺口回补后反弹，形成弱转强")

            # 向下缺口
            elif target_kline.get('high_price', 0) < prev_low * (1 - gap_threshold):
                result['has_gap'] = True
                result['gap_type'] = 'breakaway'
                result['gap_position'] = 'below'
                result['gap_size'] = (prev_low - target_kline['high_price']) / prev_low * 100
                result['technical_signals'].append(f"向下突破缺口: {result['gap_size']:.2f}%")

        # 综合支撑位分析（不仅仅是缺口支撑）
        if target_kline and prev_kline:
            # 提取价格数据
            prev_open = prev_kline.get('open_price', 0)
            prev_high = prev_kline.get('high_price', 0)
            prev_low = prev_kline.get('low_price', 0)
            prev_close = prev_kline.get('close_price', 0)
            prev_pct_chg = prev_kline.get('pct_chg', 0)

            current_open = target_kline.get('open_price', 0)
            current_high = target_kline.get('high_price', 0)
            current_low = target_kline.get('low_price', 0)
            current_close = target_kline.get('close_price', 0)
            current_pct_chg = target_kline.get('pct_chg', 0)

            # 只有有有效价格数据时才进行支撑分析
            if prev_open > 0 and current_open > 0:
                support_levels = []

                # 1. 前一日低点支撑（基础支撑）
                if prev_low > 0:
                    support_levels.append({
                        'level': prev_low,
                        'type': 'previous_low',
                        'strength': 0.6,
                        'description': '前一日低点'
                    })

                # 2. 缺口支撑（已在缺口分析中处理，这里只检查是否有效）
                if result.get('gap_support_level', 0) > 0:
                    gap_support = result['gap_support_level']
                    gap_support_strength = 0.8  # 缺口支撑较强
                    support_levels.append({
                        'level': gap_support,
                        'type': 'gap_support',
                        'strength': gap_support_strength,
                        'description': '缺口支撑（缺口下沿）'
                    })

                # 3. 前一日收盘价支撑（如果收盘价在K线实体中部或以上）
                if prev_close > 0:
                    # 如果前一日是阴线，但收盘价在实体上半部分
                    if prev_close < prev_open:  # 阴线
                        body_mid = (prev_open + prev_close) / 2
                        if prev_close > body_mid:  # 收盘在实体上半部分
                            support_levels.append({
                                'level': prev_close,
                                'type': 'previous_close',
                                'strength': 0.5,
                                'description': '前一日收盘价支撑'
                            })

                # 4. 关键价格位支撑（整数关口、前高前低等）
                # 检查整数关口支撑（如10.00、10.50等）
                integer_levels = []
                base_levels = [1.00, 2.00, 5.00, 10.00, 20.00, 50.00]
                for base in base_levels:
                    for multiplier in [0.5, 1.0, 1.5, 2.0]:
                        level = base * multiplier
                        if prev_low > 0 and abs(prev_low - level) / level < 0.02:  # 2%以内
                            integer_levels.append(level)

                for level in integer_levels[:2]:  # 最多取两个关键整数位
                    support_levels.append({
                        'level': level,
                        'type': 'integer_level',
                        'strength': 0.4,
                        'description': f'整数关口支撑 {level:.2f}'
                    })

                # 寻找最强支撑位
                if support_levels:
                    # 按支撑强度排序
                    support_levels.sort(key=lambda x: x['strength'], reverse=True)
                    strongest = support_levels[0]

                    # 检查是否在当前价格附近获得支撑
                    support_distance_pct = abs(current_low - strongest['level']) / strongest['level'] * 100
                    support_threshold = 5.0  # 5%以内认为是支撑有效（放宽阈值，因为A股波动较大）

                    if support_distance_pct < support_threshold:
                        result['has_support'] = True
                        result['support_level'] = strongest['level']
                        result['support_type'] = strongest['type']
                        result['support_strength'] = strongest['strength']

                        signal_desc = f"在{strongest['description']}{strongest['level']:.2f}获得支撑"
                        if prev_pct_chg < -2.0:  # 前一日跌幅较大
                            signal_desc += f"（前一日下跌{prev_pct_chg:.1f}%后获得支撑）"

                        # 添加支撑信号
                        result['technical_signals'].append(signal_desc)

                        # 特别标注缺口支撑
                        if strongest['type'] == 'gap_support' and result.get('is_gap_support', False):
                            result['technical_signals'].append(f"缺口支撑验证通过：价格在缺口下沿{strongest['level']:.2f}获得强支撑")

        return result

    async def analyze_advanced_support(
        self,
        stock_id: str,
        analysis_date: date,
        lookback_days: int = 60
    ) -> Dict[str, Any]:
        """
        高级压力支撑分析 - 包含斐波那契回撤、成交量分布、动态枢轴点、多时间框架分析

        Args:
            stock_id: 股票ID
            analysis_date: 分析日期
            lookback_days: 回看天数（用于计算长期支撑压力）

        Returns:
            高级支撑压力分析结果
        """
        # 获取更长时间的历史数据
        kline_data = await self.get_kline_data(stock_id, analysis_date, days_before=lookback_days, days_after=0)

        # 数据不足警告，但仍尝试进行分析
        has_sufficient_data = len(kline_data) >= 10
        if not has_sufficient_data:
            logger.warning(f'高级分析数据不足: 期望≥10个交易日，当前{len(kline_data)}条，将进行有限分析')

        result = {
            'has_advanced_analysis': has_sufficient_data,
            'fibonacci_levels': {},
            'volume_profile': {},
            'pivot_points': {},
            'multi_timeframe_levels': {},
            'advanced_signals': [],
            'data_summary': {
                'total_records': len(kline_data),
                'analysis_period': lookback_days,
                'available_days': len(kline_data),
                'has_sufficient_data': has_sufficient_data
            }
        }

        # 转换为DataFrame以便分析
        import pandas as pd
        df = pd.DataFrame(kline_data)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.sort_values('trade_date')

        # 确保价格数据有效
        df = df[df['close_price'] > 0]
        if len(df) < 10:
            logger.warning(f'有效数据不足: 期望≥10个有效交易日，当前{len(df)}条，分析结果可能受限')
            has_sufficient_data = False
            result['has_advanced_analysis'] = False
            result['data_summary']['has_sufficient_data'] = False

        # 提取价格序列
        closes = df['close_price'].values
        highs = df['high_price'].values
        lows = df['low_price'].values
        volumes = df['volume'].values if 'volume' in df.columns else None

        # 1. 斐波那契回撤分析
        fib_result = self._calculate_fibonacci_levels(highs, lows, closes)
        result['fibonacci_levels'] = fib_result

        # 2. 成交量分布分析
        if volumes is not None:
            volume_profile_result = self._calculate_volume_profile(df, closes, volumes)
            result['volume_profile'] = volume_profile_result

        # 3. 动态枢轴点分析
        pivot_result = self._calculate_pivot_points(df)
        result['pivot_points'] = pivot_result

        # 4. 多时间框架关键位分析
        timeframe_result = self._calculate_multi_timeframe_levels(df)
        result['multi_timeframe_levels'] = timeframe_result

        # 5. 综合信号生成
        signals = self._generate_advanced_signals(df, fib_result, pivot_result, volume_profile_result)
        result['advanced_signals'] = signals

        return result

    def _calculate_fibonacci_levels(self, highs, lows, closes) -> Dict[str, Any]:
        """计算斐波那契回撤位"""
        try:
            import pandas_ta as ta
            has_pandas_ta = True
        except ImportError:
            has_pandas_ta = False

        result = {
            'has_fibonacci': False,
            'levels': {},
            'key_support': None,
            'key_resistance': None
        }

        if len(highs) < 10 or len(lows) < 10:
            return result

        # 寻找最近的重要高点和低点（最近10天内）
        lookback = min(10, len(highs))
        recent_high = max(highs[-lookback:])
        recent_low = min(lows[-lookback:])

        # 斐波那契回撤位
        fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
        fib_prices = {}

        price_range = recent_high - recent_low
        current_price = closes[-1] if len(closes) > 0 else 0

        for level in fib_levels:
            # 回撤位（从高点回撤）
            retracement = recent_high - price_range * level
            fib_prices[f'fib_{int(level*1000)}'] = {
                'level': level * 100,
                'price': float(retracement),
                'type': 'retracement',
                'distance_pct': abs((current_price - retracement) / current_price * 100) if current_price > 0 else 100
            }

        # 扩展位（从低点扩展）
        extension_levels = [1.0, 1.272, 1.618]
        for level in extension_levels:
            extension = recent_low + price_range * level
            fib_prices[f'fib_ext_{int(level*1000)}'] = {
                'level': level * 100,
                'price': float(extension),
                'type': 'extension',
                'distance_pct': abs((current_price - extension) / current_price * 100) if current_price > 0 else 100
            }

        result['has_fibonacci'] = True
        result['levels'] = fib_prices
        result['swing_high'] = float(recent_high)
        result['swing_low'] = float(recent_low)
        result['price_range'] = float(price_range)
        result['current_price'] = float(current_price)

        # 找出最近的支撑和阻力位
        if current_price > 0:
            supports = []
            resistances = []

            for key, fib_info in fib_prices.items():
                fib_price = fib_info['price']
                if fib_price < current_price:
                    supports.append((fib_info['distance_pct'], fib_price, key))
                else:
                    resistances.append((fib_info['distance_pct'], fib_price, key))

            # 最近的支撑位（距离最小的）
            if supports:
                supports.sort(key=lambda x: x[0])
                result['nearest_support'] = {
                    'price': supports[0][1],
                    'level': supports[0][2],
                    'distance_pct': supports[0][0]
                }

            # 最近的阻力位
            if resistances:
                resistances.sort(key=lambda x: x[0])
                result['nearest_resistance'] = {
                    'price': resistances[0][1],
                    'level': resistances[0][2],
                    'distance_pct': resistances[0][0]
                }

        return result

    def _calculate_volume_profile(self, df, closes, volumes) -> Dict[str, Any]:
        """计算成交量分布"""
        result = {
            'has_volume_profile': False,
            'high_volume_nodes': [],
            'volume_value_area': {},
            'volume_profile_signals': []
        }

        if len(closes) < 10:
            return result

        # 将价格范围划分为多个档次（比如10个档次）
        min_price = min(closes)
        max_price = max(closes)
        price_range = max_price - min_price

        if price_range <= 0:
            return result

        num_bins = 10
        bin_size = price_range / num_bins

        # 计算每个价格区间的成交量
        volume_by_price = {}
        for i in range(len(closes)):
            price = closes[i]
            volume = volumes[i] if i < len(volumes) else 0

            # 确定价格所属的区间
            bin_index = min(int((price - min_price) / bin_size), num_bins - 1)
            bin_key = f"{min_price + bin_index * bin_size:.2f}-{min_price + (bin_index + 1) * bin_size:.2f}"

            if bin_key not in volume_by_price:
                volume_by_price[bin_key] = 0
            volume_by_price[bin_key] += volume

        # 找出高成交量节点（成交量超过平均值的区域）
        if volume_by_price:
            avg_volume = sum(volume_by_price.values()) / len(volume_by_price)
            high_volume_nodes = []

            for price_range_key, volume in volume_by_price.items():
                if volume > avg_volume * 1.5:  # 超过平均值50%
                    price_range_parts = price_range_key.split('-')
                    if len(price_range_parts) == 2:
                        low_price = float(price_range_parts[0])
                        high_price = float(price_range_parts[1])
                        mid_price = (low_price + high_price) / 2

                        high_volume_nodes.append({
                            'price_range': price_range_key,
                            'mid_price': mid_price,
                            'volume': volume,
                            'strength': min(volume / avg_volume, 3.0)  # 强度限制在3倍以内
                        })

            # 按成交量排序
            high_volume_nodes.sort(key=lambda x: x['volume'], reverse=True)

            result['has_volume_profile'] = True
            result['high_volume_nodes'] = high_volume_nodes[:5]  # 取前5个高成交量节点

            # 找出价值区域（成交量最高的70%区域）
            if high_volume_nodes:
                total_volume = sum(volume_by_price.values())
                sorted_nodes = sorted(volume_by_price.items(), key=lambda x: x[1], reverse=True)

                cumulative_volume = 0
                value_area_nodes = []
                for price_range_key, volume in sorted_nodes:
                    cumulative_volume += volume
                    value_area_nodes.append(price_range_key)
                    if cumulative_volume / total_volume >= 0.7:  # 70%成交量区域
                        break

                result['volume_value_area'] = {
                    'nodes': value_area_nodes,
                    'coverage_pct': cumulative_volume / total_volume * 100
                }

                # 生成信号
                current_price = closes[-1] if len(closes) > 0 else 0
                for node in high_volume_nodes[:3]:
                    node_mid = node['mid_price']
                    if abs(current_price - node_mid) / current_price < 0.05:  # 5%以内
                        if current_price > node_mid:
                            result['volume_profile_signals'].append(f"价格在高成交量节点{node_mid:.2f}上方，该区域可能形成支撑")
                        else:
                            result['volume_profile_signals'].append(f"价格在高成交量节点{node_mid:.2f}下方，该区域可能形成压力")

        return result

    def _calculate_pivot_points(self, df) -> Dict[str, Any]:
        """计算动态枢轴点"""
        result = {
            'has_pivot_points': False,
            'daily_pivots': {},
            'weekly_pivots': {},
            'monthly_pivots': {}
        }

        if len(df) < 5:
            return result

        # 日线枢轴点（基于前一日数据）
        if len(df) >= 2:
            prev_day = df.iloc[-2]
            H = prev_day['high_price']
            L = prev_day['low_price']
            C = prev_day['close_price']

            P = (H + L + C) / 3
            R1 = 2 * P - L
            S1 = 2 * P - H
            R2 = P + (H - L)
            S2 = P - (H - L)
            R3 = H + 2 * (P - L)
            S3 = L - 2 * (H - P)

            result['daily_pivots'] = {
                'pivot': float(P),
                'resistance1': float(R1),
                'resistance2': float(R2),
                'resistance3': float(R3),
                'support1': float(S1),
                'support2': float(S2),
                'support3': float(S3)
            }
            result['has_pivot_points'] = True

        # 周线枢轴点（基于前一周数据）
        if len(df) >= 5:
            # 取最近5个交易日作为一周
            weekly_data = df.iloc[-5:]
            H_week = weekly_data['high_price'].max()
            L_week = weekly_data['low_price'].min()
            C_week = weekly_data.iloc[-1]['close_price']

            P_week = (H_week + L_week + C_week) / 3
            R1_week = 2 * P_week - L_week
            S1_week = 2 * P_week - H_week

            result['weekly_pivots'] = {
                'pivot': float(P_week),
                'resistance1': float(R1_week),
                'support1': float(S1_week)
            }

        # 月线枢轴点（基于前15个交易日作为一月）
        if len(df) >= 15:
            monthly_lookback = min(15, len(df))
            monthly_data = df.iloc[-monthly_lookback:]
            H_month = monthly_data['high_price'].max()
            L_month = monthly_data['low_price'].min()
            C_month = monthly_data.iloc[-1]['close_price']

            P_month = (H_month + L_month + C_month) / 3
            R1_month = 2 * P_month - L_month
            S1_month = 2 * P_month - H_month

            result['monthly_pivots'] = {
                'pivot': float(P_month),
                'resistance1': float(R1_month),
                'support1': float(S1_month)
            }

        return result

    def _calculate_multi_timeframe_levels(self, df) -> Dict[str, Any]:
        """计算多时间框架关键位"""
        result = {
            'has_multi_timeframe': False,
            'daily_levels': {},
            'weekly_levels': {},
            'monthly_levels': {}
        }

        if len(df) < 10:
            return result

        # 日线关键位（最近10天）
        if len(df) >= 10:
            daily_data = df.iloc[-10:]
            result['daily_levels'] = {
                'resistance': float(daily_data['high_price'].max()),
                'support': float(daily_data['low_price'].min()),
                'range': float(daily_data['high_price'].max() - daily_data['low_price'].min())
            }

        # 周线关键位（最近15天，约3周）
        if len(df) >= 10:
            weekly_lookback = min(15, len(df))
            weekly_data = df.iloc[-weekly_lookback:]
            result['weekly_levels'] = {
                'resistance': float(weekly_data['high_price'].max()),
                'support': float(weekly_data['low_price'].min()),
                'range': float(weekly_data['high_price'].max() - weekly_data['low_price'].min())
            }

        # 月线关键位（最近30天，约6周）
        if len(df) >= 20:
            monthly_lookback = min(30, len(df))
            monthly_data = df.iloc[-monthly_lookback:]
            result['monthly_levels'] = {
                'resistance': float(monthly_data['high_price'].max()),
                'support': float(monthly_data['low_price'].min()),
                'range': float(monthly_data['high_price'].max() - monthly_data['low_price'].min())
            }

        result['has_multi_timeframe'] = True
        return result

    def _generate_advanced_signals(self, df, fib_result, pivot_result, volume_profile_result) -> List[str]:
        """生成高级技术信号"""
        signals = []

        if len(df) < 5:
            return signals

        current_price = df.iloc[-1]['close_price']

        # 1. 斐波那契支撑压力信号
        if fib_result.get('has_fibonacci', False):
            nearest_support = fib_result.get('nearest_support')
            nearest_resistance = fib_result.get('nearest_resistance')

            if nearest_support and nearest_support['distance_pct'] < 3:  # 3%以内
                signals.append(f"接近斐波那契支撑位 {nearest_support['price']:.2f} ({nearest_support['level']})")

            if nearest_resistance and nearest_resistance['distance_pct'] < 3:
                signals.append(f"接近斐波那契阻力位 {nearest_resistance['price']:.2f} ({nearest_resistance['level']})")

        # 2. 枢轴点信号
        if pivot_result.get('has_pivot_points', False):
            daily_pivots = pivot_result.get('daily_pivots', {})
            if daily_pivots:
                pivot = daily_pivots.get('pivot', 0)
                if abs(current_price - pivot) / pivot < 0.02:  # 2%以内
                    signals.append(f"价格在日线枢轴点 {pivot:.2f} 附近，可能选择方向")

                # 检查是否在支撑/阻力位附近
                for level_type in ['support1', 'support2', 'resistance1', 'resistance2']:
                    level_price = daily_pivots.get(level_type, 0)
                    if level_price > 0 and abs(current_price - level_price) / current_price < 0.02:
                        signal_type = "支撑" if "support" in level_type else "阻力"
                        signals.append(f"价格在日线{signal_type}位 {level_price:.2f} 附近")

        # 3. 成交量分布信号
        if volume_profile_result.get('has_volume_profile', False):
            high_volume_nodes = volume_profile_result.get('high_volume_nodes', [])
            for node in high_volume_nodes[:2]:  # 前2个高成交量节点
                node_mid = node['mid_price']
                if abs(current_price - node_mid) / current_price < 0.03:  # 3%以内
                    signals.append(f"价格在高成交量区域 {node_mid:.2f} 附近，可能形成重要支撑/压力")

        # 4. 多时间框架共振信号
        multi_timeframe = self._calculate_multi_timeframe_levels(df)
        if multi_timeframe.get('has_multi_timeframe', False):
            daily_levels = multi_timeframe.get('daily_levels', {})
            weekly_levels = multi_timeframe.get('weekly_levels', {})

            # 检查日线和周线支撑共振
            daily_support = daily_levels.get('support', 0)
            weekly_support = weekly_levels.get('support', 0)
            if daily_support > 0 and weekly_support > 0 and abs(daily_support - weekly_support) / daily_support < 0.05:
                signals.append(f"日线支撑 {daily_support:.2f} 与周线支撑 {weekly_support:.2f} 形成共振")

            # 检查日线和周线压力共振
            daily_resistance = daily_levels.get('resistance', 0)
            weekly_resistance = weekly_levels.get('resistance', 0)
            if daily_resistance > 0 and weekly_resistance > 0 and abs(daily_resistance - weekly_resistance) / daily_resistance < 0.05:
                signals.append(f"日线压力 {daily_resistance:.2f} 与周线压力 {weekly_resistance:.2f} 形成共振")

        return signals


# 全局实例
_kline_data_service = None


async def get_kline_data_service() -> KlineDataService:
    """获取K线数据服务实例（单例模式）"""
    global _kline_data_service
    if _kline_data_service is None:
        _kline_data_service = KlineDataService()
    return _kline_data_service


async def main_test():
    """测试函数"""
    service = await get_kline_data_service()

    # 测试获取神剑股份数据
    print("测试获取神剑股份K线数据...")

    # 先尝试不带后缀的代码
    stock_id = '002361'
    test_date = date(2026, 4, 10)

    # 检查股票是否存在
    exists = await service.check_stock_exists(stock_id)
    print(f"股票{stock_id}是否存在: {exists}")

    if exists:
        # 获取K线数据
        kline_data = await service.get_kline_data(stock_id, test_date, days_before=3, days_after=0)
        print(f"获取到{len(kline_data)}条K线数据:")
        for kline in kline_data:
            print(f"  {kline['trade_date']}: O{kline['open_price']:.2f} H{kline['high_price']:.2f} "
                  f"L{kline['low_price']:.2f} C{kline['close_price']:.2f} ({kline['pct_chg']:.2f}%)")

        # 分析缺口支撑
        print(f"\n分析{stock_id}的缺口支撑...")
        gap_analysis = await service.analyze_gap_support(stock_id, test_date)
        for key, value in gap_analysis.items():
            if key != 'technical_signals':
                print(f"  {key}: {value}")

        if gap_analysis['technical_signals']:
            print(f"  技术信号:")
            for signal in gap_analysis['technical_signals']:
                print(f"    - {signal}")

    await service.close()


if __name__ == "__main__":
    asyncio.run(main_test())
#!/usr/bin/env python3
"""
强势股分析服务 - 基于PDF框架的9维度分析
参考《A股题材&强势股跟踪》PDF分析维度：是否正宗、是否领涨、涨停类型、资金性质、流通性质、涨停封单、技术形态、龙头属性、子公司
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import asyncpg
from decimal import Decimal

logger = logging.getLogger(__name__)


class StrongStockAnalysisService:
    """强势股分析服务 - 基于PDF框架"""

    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        self.db_config = db_config or {
            "host": "localhost",
            "port": 5432,
            "database": "stock_data_test",
            "user": "postgres",
            "password": "zxbzj~925"
        }
        self._pool = None
        self._kline_data_service = None

    async def get_connection(self) -> asyncpg.Connection:
        """获取数据库连接"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(**self.db_config, min_size=1, max_size=5)

        return await self._pool.acquire()

    async def get_kline_data_service(self):
        """获取K线数据服务实例"""
        if self._kline_data_service is None:
            # 延迟导入以避免循环依赖
            from .kline_data_service import KlineDataService
            self._kline_data_service = KlineDataService(self.db_config)
        return self._kline_data_service

    async def release_connection(self, conn: asyncpg.Connection):
        """释放数据库连接"""
        await self._pool.release(conn)

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def analyze_stock_by_pdf_framework(
        self,
        stock_id: str,
        trade_date: date,
        stock_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        基于PDF框架分析股票是否为强势股

        Args:
            stock_id: 股票ID
            trade_date: 交易日期
            stock_data: 可选的股票数据，如果不提供则从数据库加载

        Returns:
            强势股分析结果，包含9个维度的分析
        """
        if stock_data is None:
            stock_data = await self._load_stock_data(stock_id, trade_date)

        if not stock_data:
            return self._create_empty_analysis(stock_id, trade_date, "未找到股票数据")

        # 执行9维度分析
        analysis = {
            'stock_id': stock_id,
            'stock_name': stock_data.get('stock_name', ''),
            'trade_date': trade_date.isoformat(),
            'analysis_date': datetime.now().isoformat(),
            'is_strong_stock': False,
            'overall_score': 0.0,
            'dimensions': {},
            'weaknesses': [],
            'strengths': []
        }

        # 1. 是否正宗（题材正宗性）
        zhengzong_analysis = await self._analyze_zhengzong(stock_id, trade_date, stock_data)
        analysis['dimensions']['是否正宗'] = zhengzong_analysis

        # 2. 是否领涨
        lingzhang_analysis = await self._analyze_lingzhang(stock_id, trade_date, stock_data)
        analysis['dimensions']['是否领涨'] = lingzhang_analysis

        # 3. 涨停类型
        limit_up_analysis = await self._analyze_limit_up_type(stock_id, trade_date, stock_data)
        analysis['dimensions']['涨停类型'] = limit_up_analysis

        # 4. 资金性质
        capital_analysis = await self._analyze_capital_nature(stock_id, trade_date, stock_data)
        analysis['dimensions']['资金性质'] = capital_analysis

        # 5. 流通性质
        liquidity_analysis = await self._analyze_liquidity(stock_id, trade_date, stock_data)
        analysis['dimensions']['流通性质'] = liquidity_analysis

        # 6. 涨停封单
        limit_up_order_analysis = await self._analyze_limit_up_order(stock_id, trade_date, stock_data)
        analysis['dimensions']['涨停封单'] = limit_up_order_analysis

        # 7. 技术形态
        technical_analysis = await self._analyze_technical_pattern(stock_id, trade_date, stock_data)
        analysis['dimensions']['技术形态'] = technical_analysis

        # 8. 龙头属性
        dragon_head_analysis = await self._analyze_dragon_head(stock_id, trade_date, stock_data)
        analysis['dimensions']['龙头属性'] = dragon_head_analysis

        # 9. 子公司
        subsidiary_analysis = await self._analyze_subsidiary(stock_id, trade_date, stock_data)
        analysis['dimensions']['子公司'] = subsidiary_analysis

        # 10. 涨停模式分析（新增，用于快速通道判断）
        limit_up_pattern_analysis = await self._analyze_limit_up_pattern(stock_id, trade_date, trading_days=7)
        analysis['limit_up_pattern'] = limit_up_pattern_analysis

        # 计算总体评分
        overall_score, weaknesses, strengths = self._calculate_overall_score(analysis['dimensions'])
        analysis['overall_score'] = overall_score
        analysis['weaknesses'] = weaknesses
        analysis['strengths'] = strengths

        # 判断是否为强势股
        analysis['is_strong_stock'] = self._is_strong_stock(overall_score, analysis['dimensions'], limit_up_pattern_analysis)

        return analysis

    async def _load_stock_data(self, stock_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """从数据库加载股票数据"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                stock_id,
                stock_name,
                trade_date,
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
                rank_order,
                subject_key
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1 AND trade_date = $2
            ORDER BY rank_order ASC
            LIMIT 1
            """

            row = await conn.fetchrow(query, stock_id, trade_date)

            if row:
                return dict(row)

            return None
        except Exception as e:
            logger.error(f"加载股票数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    def _create_empty_analysis(self, stock_id: str, trade_date: date, reason: str) -> Dict[str, Any]:
        """创建空分析结果"""

    async def _get_money_flow_data(self, stock_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取资金流向数据"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                money_flow_tier,
                main_net_inflow,
                turnover_rate,
                volume_ratio,
                dragon_tiger_net_amount,
                institution_seat_count,
                capital_flow_score,
                money_flow_score
            FROM money_flow_enhanced
            WHERE stock_id = $1 AND trade_date = $2
            LIMIT 1
            """

            row = await conn.fetchrow(query, stock_id, trade_date)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取资金流向数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def _get_hot_money_data(self, stock_id: str, trade_date: date) -> List[Dict[str, Any]]:
        """获取游资交易数据"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                hot_money_name,
                seat_name,
                side,
                buy_amount,
                sell_amount,
                net_amount,
                is_theme_leader,
                style_tags
            FROM hot_money_trading_activity
            WHERE stock_id = $1 AND trade_date = $2
            ORDER BY ABS(net_amount) DESC
            LIMIT 10
            """

            rows = await conn.fetch(query, stock_id, trade_date)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取游资数据失败: {e}")
            return []
        finally:
            await self.release_connection(conn)

    async def _get_abnormal_signal_data(self, stock_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取异常信号数据"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                turnover_rate,
                turnover_abnormal_score,
                is_high_turnover,
                volume_ratio_to_ma50,
                volume_abnormal_score,
                is_volume_breakout,
                tail_amount_ratio,
                has_tail_rush_buy,
                abnormal_composite_score,
                main_net_inflow,
                capital_focus_score,
                has_hot_money_buy,
                has_institution_buy
            FROM stock_abnormal_signal
            WHERE stock_id = $1 AND trade_date = $2
            LIMIT 1
            """

            row = await conn.fetchrow(query, stock_id, trade_date)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取异常信号数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def _get_prev_day_stock_data(self, stock_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取上一交易日股票数据（用于连续领涨判断）"""
        conn = await self.get_connection()
        try:
            prev_date = await self._get_prev_trade_date(conn, trade_date)
            if prev_date is None:
                return None
            query = """
            SELECT
                stock_id,
                stock_name,
                trade_date,
                pct_chg,
                is_leader,
                rank_order,
                subject_key
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1 AND trade_date = $2
            LIMIT 1
            """
            row = await conn.fetchrow(query, stock_id, prev_date)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取前一日股票数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def _get_stock_facts(self, stock_id: str, fact_type: str = None) -> List[Dict[str, Any]]:
        """获取股票事实数据（市值、流通盘、子公司等）"""
        conn = await self.get_connection()
        try:
            if fact_type:
                query = """
                SELECT fact_type, fact_value, confidence, source
                FROM stock_facts
                WHERE stock_id = $1 AND fact_type = $2 AND is_active = TRUE
                ORDER BY confidence DESC, created_at DESC
                LIMIT 10
                """
                rows = await conn.fetch(query, stock_id, fact_type)
            else:
                query = """
                SELECT fact_type, fact_value, confidence, source
                FROM stock_facts
                WHERE stock_id = $1 AND is_active = TRUE
                ORDER BY confidence DESC, created_at DESC
                LIMIT 20
                """
                rows = await conn.fetch(query, stock_id)

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取股票事实数据失败: {e}")
            return []
        finally:
            await self.release_connection(conn)

    async def _get_auction_data(self, stock_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取集合竞价数据（涨停封单分析）"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                auction_open_price,
                pre_close,
                auction_open_pct,
                auction_volume,
                auction_amount,
                last_minute_amount,
                last_minute_ratio,
                price_path_stability_score,
                is_red_zone,
                has_end_spike,
                has_end_drop
            FROM pre_market_auction_snapshot
            WHERE stock_id = $1 AND trade_date = $2
            LIMIT 1
            """

            row = await conn.fetchrow(query, stock_id, trade_date)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取集合竞价数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def _get_theme_leader_data(self, stock_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取主题龙头数据"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                subject_key,
                theme_name,
                candidate_rank,
                composite_score,
                role_label,
                role_enhanced
            FROM money_flow_enhanced
            WHERE stock_id = $1 AND trade_date = $2
            ORDER BY composite_score DESC
            LIMIT 1
            """

            row = await conn.fetchrow(query, stock_id, trade_date)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取主题龙头数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def _get_theme_details(self, subject_key: str) -> Optional[Dict[str, Any]]:
        """获取主题详细信息"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT
                name,
                heat_score,
                confidence_score,
                lifecycle_stage,
                stock_count,
                level1_category,
                level2_category,
                level3_category,
                theme_type
            FROM theme_master
            WHERE code = $1
            LIMIT 1
            """

            row = await conn.fetchrow(query, subject_key)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取主题详细信息失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def _get_daily_kline(self, stock_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取单日K线数据"""
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
                for key in ['open_price', 'high_price', 'low_price', 'close_price',
                           'pct_chg', 'volume', 'amount']:
                    if record.get(key) is not None:
                        record[key] = float(record[key])
                return record
            return None
        except Exception as e:
            logger.error(f"获取单日K线数据失败: {e}")
            return None
        finally:
            await self.release_connection(conn)

    async def _analyze_zhengzong(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析是否正宗（题材正宗性）"""
        subject_key = stock_data.get('subject_key')
        theme_name = '未知主题'
        theme_details = None

        if subject_key:
            # 获取主题详细信息
            theme_name = await self._get_theme_name_for_subject(subject_key)
            # 获取主题热度信息
            theme_details = await self._get_theme_details(subject_key)

        # 检查是否为龙头或前排
        is_leader = stock_data.get('is_leader', False)
        rank_order = stock_data.get('rank_order', 999)

        score = 0
        reasons = []

        # 维度1：主题关联性（40分）
        if subject_key and subject_key != '':
            score += 25
            reasons.append(f"属于主题: {theme_name}")

            # 检查主题热度
            if theme_details:
                heat_score = theme_details.get('heat_score', 0)
                if heat_score >= 80:
                    score += 15
                    reasons.append(f"主题热度高（{heat_score}分）")
                elif heat_score >= 60:
                    score += 10
                    reasons.append(f"主题热度中等（{heat_score}分）")

        # 维度2：在主题中的地位（30分）
        if is_leader:
            score += 30
            reasons.append(f"数据库标记为龙头")
        elif rank_order <= 3:
            score += 25
            reasons.append(f"主题内排名第{rank_order}（前排）")
        elif rank_order <= 10:
            score += 15
            reasons.append(f"主题内排名第{rank_order}（中前排）")
        elif rank_order <= 30:
            score += 5
            reasons.append(f"主题内排名第{rank_order}（后排）")

        # 维度3：市场表现（30分）
        pct_chg = stock_data.get('pct_chg', 0)
        if pct_chg >= 9.9:  # 涨停
            score += 30
            reasons.append(f"涨停（{pct_chg:.1f}%），表现强势")
        elif pct_chg > 5.0:
            score += 20
            reasons.append(f"涨幅{pct_chg:.1f}%，表现良好")
        elif pct_chg > 0:
            score += 10
            reasons.append(f"涨幅{pct_chg:.1f}%，表现一般")
        else:
            score += 0
            reasons.append(f"未上涨（{pct_chg:.1f}%），表现弱势")

        return {
            'score': min(score, 100),
            'reasons': reasons,
            'theme_name': theme_name,
            'subject_key': subject_key,
            'theme_heat': theme_details.get('heat_score') if theme_details else None
        }

    async def _analyze_lingzhang(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析是否领涨 - 考虑连续领涨情况"""
        pct_chg = stock_data.get('pct_chg', 0)
        is_leader = stock_data.get('is_leader', False)
        rank_order = stock_data.get('rank_order', 999)

        # 获取前一日数据以检查连续领涨
        prev_day_data = await self._get_prev_day_stock_data(stock_id, trade_date)
        prev_is_leader = prev_day_data.get('is_leader', False) if prev_day_data else False
        prev_rank_order = prev_day_data.get('rank_order', 999) if prev_day_data else 999
        prev_pct_chg = prev_day_data.get('pct_chg', 0) if prev_day_data else 0

        # 获取异常信号数据
        abnormal_data = await self._get_abnormal_signal_data(stock_id, trade_date)

        score = 0
        reasons = []

        # 维度1：涨幅表现（40分）
        if pct_chg >= 9.9:  # 涨停
            score += 40
            reasons.append(f"涨停（{pct_chg:.1f}%），领涨明显")
        elif pct_chg > 5.0:
            score += 30
            reasons.append(f"涨幅{pct_chg:.1f}%，领涨较强")
        elif pct_chg > 0:
            score += 15
            reasons.append(f"涨幅{pct_chg:.1f}%，表现一般")
        else:
            score += 0
            reasons.append(f"未上涨（{pct_chg:.1f}%），不领涨")

        # 维度2：主题地位（30分） - 考虑连续领涨
        if is_leader:
            if prev_is_leader:
                score += 30  # 连续龙头，最高分
                reasons.append("连续标记为龙头，领涨地位稳固")
            else:
                score += 20  # 单日龙头，需观察
                reasons.append("单日标记为龙头，需观察持续性")
        elif rank_order <= 3:
            if prev_rank_order <= 3:
                score += 25  # 连续前排
                reasons.append(f"连续前排（前日第{prev_rank_order}，今日第{rank_order}）")
            else:
                score += 20  # 单日前排
                reasons.append(f"单日前排（第{rank_order}），需观察")
        elif rank_order <= 10:
            if prev_rank_order <= 10:
                score += 15  # 连续前排
                reasons.append(f"连续前排位置（前日第{prev_rank_order}，今日第{rank_order}）")
            else:
                score += 10  # 单日前排
                reasons.append(f"单日前排位置（第{rank_order}）")
        elif rank_order <= 30:
            score += 5
            reasons.append(f"主题内排名第{rank_order}（中后排）")

        # 维度3：资金和成交量异动（30分）
        if abnormal_data:
            # 换手率异常
            turnover_rate = abnormal_data.get('turnover_rate', 0)
            is_high_turnover = abnormal_data.get('is_high_turnover', False)
            if is_high_turnover:
                score += 15
                reasons.append(f"高换手率（{turnover_rate:.2f}%），资金活跃")

            # 成交量异动
            volume_breakout = abnormal_data.get('is_volume_breakout', False)
            if volume_breakout:
                score += 10
                reasons.append(f"成交量突破，资金关注度高")

            # 尾盘抢筹
            has_tail_rush = abnormal_data.get('has_tail_rush_buy', False)
            if has_tail_rush:
                score += 5
                reasons.append("尾盘抢筹，资金看好")

        # 额外加分：连续领涨（基于涨幅）
        if pct_chg > 0 and prev_pct_chg > 0:
            # 连续上涨
            score += min((pct_chg + prev_pct_chg) / 2, 10)  # 平均涨幅加成
            reasons.append(f"连续上涨（前日{prev_pct_chg:.1f}%，今日{pct_chg:.1f}%）")

        if pct_chg >= 9.9 and prev_pct_chg >= 9.9:
            # 连续涨停
            score += 15
            reasons.append("连续涨停，领涨强劲")

        # 惩罚：前一日大跌，今日小涨（弱势反弹）
        if prev_pct_chg < -5.0 and pct_chg < 3.0:
            score -= 5
            reasons.append(f"前一日大跌{prev_pct_chg:.1f}%，今日反弹力度不足{pct_chg:.1f}%")

        return {
            'score': min(max(score, 0), 100),
            'reasons': reasons,
            'pct_chg': pct_chg,
            'is_leader': is_leader,
            'rank_order': rank_order,
            'abnormal_signals': abnormal_data is not None,
            'prev_day_leader': prev_is_leader,
            'prev_day_rank': prev_rank_order,
            'prev_day_pct_chg': prev_pct_chg,
            'consecutive_leader': is_leader and prev_is_leader,
            'consecutive_front_rank': rank_order <= 3 and prev_rank_order <= 3
        }

    async def _analyze_limit_up_type(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析涨停类型"""
        pct_chg = stock_data.get('pct_chg', 0)
        limit_up = stock_data.get('limit_up', False)

        # 获取前一日数据以判断是否连续涨停
        conn = await self.get_connection()
        try:
            prev_date = await self._get_prev_trade_date(conn, trade_date)
        finally:
            await self.release_connection(conn)
        prev_kline = await self._get_daily_kline(stock_id, prev_date) if prev_date else None

        limit_up_type = "非涨停"
        score = 30  # 基础分
        reasons = []
        limit_up_details = {}

        # 根据涨幅判断涨停类型
        if pct_chg >= 9.9:
            limit_up_type = "涨停"
            score = 100
            reasons.append(f"涨停（{pct_chg:.1f}%）")

            # 判断是否一字涨停（开盘价等于涨停价）
            open_price = stock_data.get('open_price', 0)
            close_price = stock_data.get('close_price', 0)
            high_price = stock_data.get('high_price', 0)

            if open_price and close_price and abs(open_price - close_price) / close_price < 0.001:
                limit_up_type = "一字涨停"
                reasons.append("一字涨停，全天封死")
                score = 100  # 一字涨停最强
            elif high_price and close_price and abs(high_price - close_price) / close_price < 0.001:
                limit_up_type = "涨停封死"
                reasons.append("涨停封死，无开板")
                score = 95
            else:
                limit_up_type = "涨停开板"
                reasons.append("涨停但开板")
                score = 80

            # 判断是否连续涨停
            if prev_kline and prev_kline.get('pct_chg', 0) >= 9.9:
                limit_up_type = f"连续{limit_up_type}"
                score = min(score + 5, 100)  # 连续涨停额外加分
                reasons.append("连续涨停，强势延续")

        elif pct_chg > 7.0:
            limit_up_type = "接近涨停"
            score = 85
            reasons.append(f"接近涨停（{pct_chg:.1f}%）")
        elif pct_chg > 5.0:
            limit_up_type = "大涨"
            score = 70
            reasons.append(f"大涨（{pct_chg:.1f}%）")
        elif pct_chg > 3.0:
            limit_up_type = "中涨"
            score = 50
            reasons.append(f"中涨（{pct_chg:.1f}%）")
        elif pct_chg > 0:
            limit_up_type = "小涨"
            score = 40
            reasons.append(f"小涨（{pct_chg:.1f}%）")
        elif pct_chg > -3.0:
            limit_up_type = "微跌"
            score = 20
            reasons.append(f"微跌（{pct_chg:.1f}%）")
        else:
            limit_up_type = "下跌"
            score = 10
            reasons.append(f"下跌（{pct_chg:.1f}%）")

        # 记录详情
        limit_up_details['prev_day_pct_chg'] = prev_kline.get('pct_chg') if prev_kline else None
        limit_up_details['is_consecutive_limit'] = prev_kline and prev_kline.get('pct_chg', 0) >= 9.9

        return {
            'score': score,
            'limit_up_type': limit_up_type,
            'pct_chg': pct_chg,
            'is_limit_up': limit_up,
            'reasons': reasons,
            'limit_up_details': limit_up_details
        }

    async def _get_prev_trade_date(self, conn, trade_date: date) -> Optional[date]:
        row = await conn.fetchrow(
            """
            SELECT MAX(trade_date) AS prev_trade_date
            FROM stock_daily_snapshot
            WHERE trade_date < $1::date
            """,
            trade_date,
        )
        return row.get("prev_trade_date") if row else None

    async def _analyze_capital_nature(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析资金性质"""
        amount = stock_data.get('amount', 0)  # 成交额
        volume = stock_data.get('volume', 0)   # 成交量

        # 获取资金流向数据和游资数据
        money_flow_data = await self._get_money_flow_data(stock_id, trade_date)
        hot_money_data = await self._get_hot_money_data(stock_id, trade_date)
        abnormal_data = await self._get_abnormal_signal_data(stock_id, trade_date)

        capital_type = "未知"
        score = 50  # 基础分
        reasons = []
        capital_details = {}

        # 维度1：资金规模（30分）
        amount_yi = amount / 100000000
        if amount_yi > 10:  # 10亿元以上
            score += 20
            capital_type = "大资金"
            reasons.append(f"成交额{amount_yi:.2f}亿元，大资金参与")
        elif amount_yi > 5:  # 5-10亿元
            score += 15
            capital_type = "中等资金"
            reasons.append(f"成交额{amount_yi:.2f}亿元，中等资金参与")
        elif amount_yi > 2:  # 2-5亿元
            score += 10
            capital_type = "小资金"
            reasons.append(f"成交额{amount_yi:.2f}亿元，小资金参与")
        else:
            score += 5
            capital_type = "微量资金"
            reasons.append(f"成交额{amount_yi:.2f}亿元，资金量较小")

        # 维度2：资金流向（40分）
        if money_flow_data:
            money_flow_tier = money_flow_data.get('money_flow_tier', '')
            main_net_inflow = money_flow_data.get('main_net_inflow', 0)
            dragon_tiger_net = money_flow_data.get('dragon_tiger_net_amount', 0)
            inst_seat_count = money_flow_data.get('institution_seat_count', 0)

            # 主力资金净流入
            if main_net_inflow > 10000000:  # 1000万元以上
                score += 20
                reasons.append(f"主力资金净流入{main_net_inflow/10000:.0f}万元")
                capital_type += "+主力流入"
            elif main_net_inflow > 0:
                score += 10
                reasons.append(f"主力资金小幅流入{main_net_inflow/10000:.0f}万元")
                capital_type += "+主力微流入"

            # 龙虎榜资金
            if abs(dragon_tiger_net) > 5000000:  # 500万元以上
                score += 10
                if dragon_tiger_net > 0:
                    reasons.append(f"龙虎榜净买入{dragon_tiger_net/10000:.0f}万元")
                    capital_type += "+龙虎榜买入"
                else:
                    reasons.append(f"龙虎榜净卖出{abs(dragon_tiger_net)/10000:.0f}万元")
                    capital_type += "+龙虎榜卖出"

            # 机构席位
            if inst_seat_count > 0:
                score += 10
                reasons.append(f"机构席位{inst_seat_count}个")
                capital_type += "+机构参与"

            capital_details['money_flow_tier'] = money_flow_tier
            capital_details['main_net_inflow'] = main_net_inflow

        # 维度3：游资参与度（30分）
        if hot_money_data:
            total_hot_money_net = sum([row.get('net_amount', 0) for row in hot_money_data])
            hot_money_count = len(hot_money_data)

            if hot_money_count > 0:
                score += 15
                reasons.append(f"{hot_money_count}个游资席位参与")

                if total_hot_money_net > 0:
                    score += 15
                    reasons.append(f"游资净买入{total_hot_money_net/10000:.0f}万元")
                    capital_type += "+游资买入"
                elif total_hot_money_net < 0:
                    score += 5
                    reasons.append(f"游资净卖出{abs(total_hot_money_net)/10000:.0f}万元")
                    capital_type += "+游资卖出"

            capital_details['hot_money_count'] = hot_money_count
            capital_details['hot_money_net'] = total_hot_money_net

        # 清理capital_type中的"未知"前缀
        if capital_type.startswith("未知+"):
            capital_type = capital_type[3:]

        return {
            'score': min(score, 100),
            'capital_type': capital_type,
            'amount_yi': round(amount_yi, 2),
            'volume_wan': round(volume / 10000, 2),
            'reasons': reasons,
            'capital_details': capital_details
        }

    async def _analyze_liquidity(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析流通性质"""
        # 获取股票事实数据（市值、流通盘）
        market_cap_facts = await self._get_stock_facts(stock_id, 'market_cap')
        circulating_facts = await self._get_stock_facts(stock_id, 'circulating_shares')
        total_shares_facts = await self._get_stock_facts(stock_id, 'total_shares')

        market_cap_yi = None
        circulating_ratio = None
        liquidity_type = '未知'
        score = 50  # 基础分
        reasons = []

        # 分析市值
        if market_cap_facts:
            # 取最新的一条市值数据
            latest_market_cap = market_cap_facts[0] if market_cap_facts else None
            if latest_market_cap:
                try:
                    market_cap_yi = float(latest_market_cap.get('fact_value', 0)) / 100000000

                    if market_cap_yi > 1000:  # 1000亿元以上
                        liquidity_type = '超级大盘'
                        score = 40  # 大盘股流动性好但弹性差
                        reasons.append(f"超级大盘股，市值{market_cap_yi:.0f}亿元，流动性好但弹性差")
                    elif market_cap_yi > 200:  # 200-1000亿元
                        liquidity_type = '大盘股'
                        score = 60
                        reasons.append(f"大盘股，市值{market_cap_yi:.0f}亿元，流动性良好")
                    elif market_cap_yi > 50:  # 50-200亿元
                        liquidity_type = '中盘股'
                        score = 70  # 中盘股流动性好且弹性佳
                        reasons.append(f"中盘股，市值{market_cap_yi:.0f}亿元，流动性好弹性佳")
                    elif market_cap_yi > 20:  # 20-50亿元
                        liquidity_type = '小盘股'
                        score = 65
                        reasons.append(f"小盘股，市值{market_cap_yi:.0f}亿元，流动性一般弹性好")
                    else:  # 20亿元以下
                        liquidity_type = '微盘股'
                        score = 45  # 微盘股流动性差
                        reasons.append(f"微盘股，市值{market_cap_yi:.0f}亿元，流动性较差")
                except (ValueError, TypeError):
                    market_cap_yi = None

        # 分析流通比例
        if circulating_facts and total_shares_facts:
            latest_circulating = circulating_facts[0] if circulating_facts else None
            latest_total = total_shares_facts[0] if total_shares_facts else None

            if latest_circulating and latest_total:
                try:
                    circulating_shares = float(latest_circulating.get('fact_value', 0))
                    total_shares = float(latest_total.get('fact_value', 0))

                    if total_shares > 0:
                        circulating_ratio = circulating_shares / total_shares * 100

                        if circulating_ratio > 90:
                            score += 10
                            reasons.append(f"全流通（{circulating_ratio:.1f}%），无解禁压力")
                        elif circulating_ratio > 70:
                            score += 5
                            reasons.append(f"高流通比例（{circulating_ratio:.1f}%），解禁压力小")
                        elif circulating_ratio < 30:
                            score -= 10
                            reasons.append(f"低流通比例（{circulating_ratio:.1f}%），解禁压力大")
                except (ValueError, TypeError):
                    circulating_ratio = None

        # 如果没有找到数据，使用默认值
        if not market_cap_facts:
            reasons.append("市值数据未知，假设为中盘股")
            liquidity_type = '中盘股（假设）'

        return {
            'score': min(max(score, 0), 100),
            'liquidity_type': liquidity_type,
            'reasons': reasons,
            'market_cap_yi': round(market_cap_yi, 2) if market_cap_yi else 'N/A',
            'circulating_ratio': round(circulating_ratio, 1) if circulating_ratio else 'N/A'
        }

    async def _analyze_limit_up_order(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析涨停封单"""
        pct_chg = stock_data.get('pct_chg', 0)
        limit_up = stock_data.get('limit_up', False)

        # 获取集合竞价数据
        auction_data = await self._get_auction_data(stock_id, trade_date)

        score = 40  # 基础分
        status = '无涨停封单'
        reasons = []
        order_details = {}

        # 维度1：是否涨停（40分）
        is_limit_up_today = pct_chg >= 9.9 and limit_up

        if is_limit_up_today:
            score += 40
            status = '涨停封单'
            reasons.append(f"涨停（{pct_chg:.1f}%）")

            # 如果有集合竞价数据，分析封单强度
            if auction_data:
                auction_open_pct = auction_data.get('auction_open_pct', 0)
                auction_amount = auction_data.get('auction_amount', 0)
                last_minute_ratio = auction_data.get('last_minute_ratio', 0)
                is_red_zone = auction_data.get('is_red_zone', False)
                has_end_spike = auction_data.get('has_end_spike', False)

                # 集合竞价涨幅
                if auction_open_pct >= 9.9:
                    score += 20
                    reasons.append(f"集合竞价涨停（{auction_open_pct:.1f}%）")
                    status = '一字涨停'
                elif auction_open_pct >= 7.0:
                    score += 15
                    reasons.append(f"集合竞价高开（{auction_open_pct:.1f}%）")
                    status = '高开封涨停'
                elif auction_open_pct >= 3.0:
                    score += 10
                    reasons.append(f"集合竞价中高开（{auction_open_pct:.1f}%）")
                    status = '中高开封涨停'

                # 集合竞金额
                auction_amount_yi = auction_amount / 100000000
                if auction_amount_yi > 1.0:  # 1亿元以上
                    score += 10
                    reasons.append(f"集合竞金额{auction_amount_yi:.2f}亿元，大资金抢筹")
                elif auction_amount_yi > 0.5:  # 5000万元以上
                    score += 5
                    reasons.append(f"集合竞金额{auction_amount_yi:.2f}亿元，资金抢筹")

                # 尾盘抢筹
                if last_minute_ratio > 0.3:  # 最后1分钟占比30%以上
                    score += 10
                    reasons.append(f"尾盘抢筹明显（最后1分钟占比{last_minute_ratio:.1%}）")

                if is_red_zone:
                    score += 5
                    reasons.append("红盘区，强势特征")

                if has_end_spike:
                    score += 5
                    reasons.append("尾盘拉升，资金抢筹")

                order_details['auction_open_pct'] = auction_open_pct
                order_details['auction_amount_yi'] = auction_amount_yi
                order_details['last_minute_ratio'] = last_minute_ratio
        else:
            reasons.append(f"非涨停（{pct_chg:.1f}%）")

            # 如果不是涨停，但集合竞价有抢筹现象
            if auction_data:
                auction_open_pct = auction_data.get('auction_open_pct', 0)
                if auction_open_pct > 3.0:
                    score += 10
                    reasons.append(f"集合竞价高开{auction_open_pct:.1f}%，有抢筹迹象")
                    status = '高开无涨停'

        return {
            'score': min(score, 100),
            'status': status,
            'reasons': reasons,
            'order_details': order_details
        }

    async def _get_recent_trading_days(self, end_date: date, trading_days_count: int = 7) -> List[date]:
        """获取最近N个交易日（按日期倒序）"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT DISTINCT trade_date
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1
            ORDER BY trade_date DESC
            LIMIT $2
            """
            rows = await conn.fetch(query, end_date, trading_days_count)
            return [row['trade_date'] for row in rows]
        except Exception as e:
            logger.error(f"获取交易日失败: {e}")
            # 失败时返回自然日作为后备
            return [end_date - timedelta(days=i) for i in range(trading_days_count)]
        finally:
            await self.release_connection(conn)

    async def _get_trading_dates_between(self, start_date: date, end_date: date) -> List[date]:
        """获取两个日期之间的所有交易日（按日期升序）"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT DISTINCT trade_date
            FROM subject_stock_daily_snapshot
            WHERE trade_date >= $1 AND trade_date <= $2
            ORDER BY trade_date ASC
            """
            rows = await conn.fetch(query, start_date, end_date)
            return [row['trade_date'] for row in rows]
        except Exception as e:
            logger.error(f"获取交易日区间失败: {e}")
            # 失败时返回自然日作为后备
            dates = []
            current = start_date
            while current <= end_date:
                dates.append(current)
                current += timedelta(days=1)
            return dates
        finally:
            await self.release_connection(conn)

    async def _analyze_limit_up_pattern(self, stock_id: str, trade_date: date, trading_days: int = 7) -> Dict[str, Any]:
        """分析涨停模式 - 检查近期（默认7个交易日）的连续涨停或多次涨停"""
        try:
            conn = await self.get_connection()

            # 获取最近N个交易日
            trading_dates = await self._get_recent_trading_days(trade_date, trading_days)
            if not trading_dates:
                return {
                    'has_limit_up_pattern': False,
                    'limit_up_count': 0,
                    'max_consecutive_days': 0,
                    'limit_up_dates': [],
                    'analysis_period': f"{trading_days}个交易日",
                    'pattern_type': '无数据',
                    'strength_score': 0,
                    'reason': f'无交易日数据'
                }

            start_date = min(trading_dates)

            query = """
            SELECT trade_date, pct_chg, is_leader, rank_order, limit_up
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1 AND trade_date >= $2 AND trade_date <= $3
            ORDER BY trade_date ASC
            """

            rows = await conn.fetch(query, stock_id, start_date, trade_date)

            # 获取交易日历映射（用于连续涨停判断）
            all_trading_dates = await self._get_trading_dates_between(start_date, trade_date)
            date_to_index = {date: idx for idx, date in enumerate(all_trading_dates)}

            # 统计涨停情况
            limit_up_dates = []
            limit_up_count = 0
            consecutive_limit_up = 0
            max_consecutive = 0
            current_consecutive = 0
            prev_date = None
            prev_index = None

            for row in rows:
                pct_chg = float(row['pct_chg'])
                trade_date_row = row['trade_date']

                # 检查是否涨停（涨幅≥9.9%）
                is_limit_up = pct_chg >= 9.9

                if is_limit_up:
                    limit_up_count += 1
                    limit_up_dates.append(trade_date_row)

                    # 检查是否连续涨停（基于交易日历）
                    current_index = date_to_index.get(trade_date_row)
                    if prev_date is not None and current_index is not None and prev_index is not None:
                        # 如果当前交易日索引等于前一个交易日索引+1，则为连续涨停
                        if current_index == prev_index + 1:
                            current_consecutive += 1
                        else:
                            current_consecutive = 1
                    else:
                        current_consecutive = 1

                    max_consecutive = max(max_consecutive, current_consecutive)
                    prev_date = trade_date_row
                    prev_index = current_index

            # 分析结果
            result = {
                'has_limit_up_pattern': False,
                'limit_up_count': limit_up_count,
                'max_consecutive_days': max_consecutive,
                'limit_up_dates': [d.strftime('%Y-%m-%d') for d in limit_up_dates],
                'analysis_period': f"{trading_days}个交易日",
                'pattern_type': '无涨停'
            }

            if max_consecutive >= 2:
                result['has_limit_up_pattern'] = True
                result['pattern_type'] = f'连续{max_consecutive}天涨停'
                result['strength_score'] = 95
                result['reason'] = f'连续{max_consecutive}天涨停，符合强势股特征'
            elif limit_up_count >= 2:
                result['has_limit_up_pattern'] = True
                result['pattern_type'] = f'{limit_up_count}次非连续涨停'
                result['strength_score'] = 85
                result['reason'] = f'{trading_days}个交易日内{limit_up_count}次涨停，显示强势特征'
            elif limit_up_count == 1:
                result['pattern_type'] = '单日涨停'
                result['strength_score'] = 70
                result['reason'] = f'{trading_days}个交易日内{limit_up_count}次涨停'
            else:
                result['strength_score'] = 30
                result['reason'] = f'{trading_days}个交易日内无涨停'

            return result

        except Exception as e:
            logger.error(f"涨停模式分析失败: {e}")
            return {
                'has_limit_up_pattern': False,
                'limit_up_count': 0,
                'max_consecutive_days': 0,
                'limit_up_dates': [],
                'analysis_period': f"{trading_days}个交易日",
                'pattern_type': '分析失败',
                'strength_score': 0,
                'reason': f'分析失败: {str(e)}'
            }
        finally:
            await self.release_connection(conn)

    async def _analyze_technical_pattern(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析技术形态"""
        try:
            # 获取K线数据服务
            kline_service = await self.get_kline_data_service()

            # 获取最近5天的K线数据进行分析
            kline_data = await kline_service.get_kline_data(stock_id, trade_date, days_before=5, days_after=0)

            if not kline_data or len(kline_data) < 3:
                # 数据不足，返回基础分析
                pct_chg = stock_data.get('pct_chg', 0)
                pattern = "震荡"
                if pct_chg > 5.0:
                    pattern = "上涨"
                elif pct_chg < -2.0:
                    pattern = "下跌"

                score = 60 if pattern == "上涨" else (40 if pattern == "震荡" else 20)

                return {
                    'score': score,
                    'pattern': pattern,
                    'reason': f"技术形态：{pattern}（{pct_chg:.1f}%）数据不足",
                    'support_level': 'N/A',
                    'resistance_level': 'N/A',
                    'technical_signals': ['K线数据不足']
                }

            # 分析缺口支撑
            gap_analysis = await kline_service.analyze_gap_support(stock_id, trade_date)

            # 计算技术指标
            technical_signals = []
            pattern = "震荡"
            score = 50  # 基础分

            # 获取当前和前一日的K线
            current_kline = None
            prev_kline = None

            for kline in kline_data:
                if kline['trade_date'] == trade_date:
                    current_kline = kline
                elif current_kline is None and kline['trade_date'] < trade_date:
                    prev_kline = kline

            # 如果没找到当日数据，用最后一条
            if current_kline is None and kline_data:
                current_kline = kline_data[-1]
                if len(kline_data) > 1:
                    prev_kline = kline_data[-2]

            # 分析价格走势
            if current_kline and prev_kline:
                current_pct = current_kline.get('pct_chg', 0)
                prev_pct = prev_kline.get('pct_chg', 0)

                # 判断趋势
                if current_pct > 5.0:
                    pattern = "强势上涨"
                    score += 30
                    technical_signals.append(f"强势上涨（{current_pct:.1f}%）")
                elif current_pct > 0:
                    pattern = "震荡上涨"
                    score += 15
                    technical_signals.append(f"震荡上涨（{current_pct:.1f}%）")
                elif current_pct > -2.0:
                    pattern = "震荡"
                    score += 5
                    technical_signals.append(f"震荡（{current_pct:.1f}%）")
                else:
                    pattern = "下跌"
                    score -= 10
                    technical_signals.append(f"下跌（{current_pct:.1f}%）")

                # 弱转强信号：前一日下跌，今日上涨
                if prev_pct < -2.0 and current_pct > 0:
                    pattern = "弱转强"
                    score += 25
                    technical_signals.append(f"弱转强信号：前一日下跌{prev_pct:.1f}%，今日上涨{current_pct:.1f}%")

                # 缺口支撑信号
                if gap_analysis.get('is_gap_support', False):
                    pattern = "缺口支撑反弹"
                    score += 20
                    technical_signals.append("缺口支撑有效，形成技术反弹")

                # 支撑位分析
                if gap_analysis.get('has_support', False):
                    support_level = gap_analysis.get('support_level', 0)
                    support_strength = gap_analysis.get('support_strength', 0)
                    score += int(support_strength * 20)  # 根据支撑强度加分
                    technical_signals.append(f"在{support_level:.2f}获得支撑（强度{support_strength:.1f}）")

            # 添加缺口分析中的技术信号
            if gap_analysis.get('technical_signals'):
                technical_signals.extend(gap_analysis['technical_signals'])

            # 确定主要支撑位和阻力位
            support_level = gap_analysis.get('gap_support_level', 0) or gap_analysis.get('support_level', 'N/A')
            resistance_level = 'N/A'  # 简化处理，实际应该计算阻力位

            if support_level == 0:
                support_level = 'N/A'

            return {
                'score': min(max(score, 0), 100),
                'pattern': pattern,
                'reason': f"技术形态：{pattern}",
                'support_level': support_level,
                'resistance_level': resistance_level,
                'technical_signals': technical_signals,
                'gap_analysis_summary': {
                    'has_gap': gap_analysis.get('has_gap', False),
                    'gap_type': gap_analysis.get('gap_type', ''),
                    'has_support': gap_analysis.get('has_support', False)
                }
            }

        except Exception as e:
            logger.error(f"技术形态分析失败: {e}")
            # 返回基础分析作为后备
            pct_chg = stock_data.get('pct_chg', 0)
            pattern = "震荡"
            if pct_chg > 5.0:
                pattern = "上涨"
            elif pct_chg < -2.0:
                pattern = "下跌"

            score = 60 if pattern == "上涨" else (40 if pattern == "震荡" else 20)

            return {
                'score': score,
                'pattern': pattern,
                'reason': f"技术形态：{pattern}（{pct_chg:.1f}%）分析出错",
                'support_level': 'N/A',
                'resistance_level': 'N/A',
                'technical_signals': [f"分析出错: {str(e)}"]
            }

    async def _analyze_dragon_head(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析龙头属性 - 基于'二板定龙头'原则，需要至少两天领涨"""
        is_leader = stock_data.get('is_leader', False)
        rank_order = stock_data.get('rank_order', 999)
        pct_chg = stock_data.get('pct_chg', 0)

        # 获取前一日数据以检查连续领涨
        prev_day_data = await self._get_prev_day_stock_data(stock_id, trade_date)
        prev_is_leader = prev_day_data.get('is_leader', False) if prev_day_data else False
        prev_rank_order = prev_day_data.get('rank_order', 999) if prev_day_data else 999
        prev_pct_chg = prev_day_data.get('pct_chg', 0) if prev_day_data else 0

        # 判断连续领涨状态
        consecutive_leader = is_leader and prev_is_leader
        consecutive_front_rank = rank_order <= 3 and prev_rank_order <= 3
        consecutive_limit_up = pct_chg >= 9.9 and prev_pct_chg >= 9.9  # 连续涨停

        dragon_head_level = "非龙头"
        if consecutive_leader and consecutive_limit_up:
            dragon_head_level = "绝对龙头（连续涨停）"
        elif consecutive_leader:
            dragon_head_level = "绝对龙头（连续领涨）"
        elif is_leader and consecutive_front_rank:
            dragon_head_level = "前排龙头（连续前排）"
        elif is_leader:
            dragon_head_level = "单日龙头（需观察）"
        elif rank_order <= 3 and prev_rank_order <= 3:
            dragon_head_level = "连续前排"
        elif rank_order <= 3:
            dragon_head_level = "单日前排"
        elif rank_order <= 10:
            dragon_head_level = "跟风"
        else:
            dragon_head_level = "非龙头"

        score = 0
        reasons = []

        if dragon_head_level.startswith("绝对龙头"):
            if consecutive_limit_up:
                score = 100
                reasons.append("连续涨停，符合'二板定龙头'原则")
            else:
                score = 90
                reasons.append("连续领涨，龙头地位确认")
        elif dragon_head_level.startswith("前排龙头"):
            score = 80
            reasons.append("连续前排，潜在龙头")
        elif dragon_head_level == "单日龙头（需观察）":
            score = 50
            reasons.append("单日龙头，需观察持续性")
        elif dragon_head_level == "连续前排":
            score = 70
            reasons.append("连续前排位置，有龙头潜力")
        elif dragon_head_level == "单日前排":
            score = 50
            reasons.append("单日前排，需观察")
        elif dragon_head_level == "跟风":
            score = 40
            reasons.append(f"主题内排名第{rank_order}，属于跟风")
        else:
            score = 20
            reasons.append("非龙头或排名靠后")

        # 涨幅加成
        if pct_chg >= 9.9:
            score = min(score + 10, 100)
            reasons.append(f"涨停（{pct_chg:.1f}%），强势确认")
        elif pct_chg > 5.0:
            score = min(score + 5, 100)
            reasons.append(f"涨幅{pct_chg:.1f}%，表现强势")

        # 连续涨停额外加成
        if consecutive_limit_up:
            score = min(score + 10, 100)
            reasons.append("连续涨停，龙头地位强化")

        return {
            'score': score,
            'dragon_head_level': dragon_head_level,
            'reasons': reasons,
            'is_leader': is_leader,
            'rank_order': rank_order,
            'consecutive_leader': consecutive_leader,
            'consecutive_front_rank': consecutive_front_rank,
            'consecutive_limit_up': consecutive_limit_up,
            'prev_day_leader': prev_is_leader,
            'prev_day_rank': prev_rank_order
        }

    async def _analyze_subsidiary(self, stock_id: str, trade_date: date, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析子公司"""
        # 简化处理：需要更多公司信息
        return {
            'score': 50,
            'subsidiary_info': '子公司信息未知',
            'reason': '子公司信息不足，假设为中性',
            'related_companies': []
        }

    async def _get_theme_name_for_subject(self, subject_key: str) -> str:
        """根据subject_key获取主题名称"""
        conn = await self.get_connection()
        try:
            query = """
            SELECT name FROM theme_master WHERE code = $1 LIMIT 1
            """
            row = await conn.fetchrow(query, subject_key)
            if row:
                return row['name']

            # 尝试从vw_subject_theme_binding查找
            query2 = """
            SELECT theme_name FROM vw_subject_theme_binding WHERE subject_key = $1 LIMIT 1
            """
            row2 = await conn.fetchrow(query2, subject_key)
            if row2:
                return row2['theme_name']

            return f"主题_{subject_key}"
        except Exception as e:
            logger.error(f"获取主题名称失败: {e}")
            return f"主题_{subject_key}"
        finally:
            await self.release_connection(conn)

    def _calculate_overall_score(self, dimensions: Dict[str, Dict[str, Any]]) -> tuple:
        """计算总体评分"""
        # 各维度权重
        weights = {
            '是否正宗': 0.15,
            '是否领涨': 0.20,
            '涨停类型': 0.10,
            '资金性质': 0.10,
            '流通性质': 0.05,
            '涨停封单': 0.05,
            '技术形态': 0.10,
            '龙头属性': 0.20,
            '子公司': 0.05
        }

        overall_score = 0.0
        weaknesses = []
        strengths = []

        for dim_name, dim_data in dimensions.items():
            weight = weights.get(dim_name, 0.1)
            dim_score = dim_data.get('score', 0)
            overall_score += float(dim_score) * weight

            # 记录弱点和优点
            if dim_score < 40:
                weaknesses.append(f"{dim_name}评分较低（{dim_score}分）")
            elif dim_score >= 70:
                strengths.append(f"{dim_name}评分较高（{dim_score}分）")

        return round(overall_score, 1), weaknesses, strengths

    def _is_strong_stock(self, overall_score: float, dimensions: Dict[str, Dict[str, Any]], limit_up_pattern: Optional[Dict[str, Any]] = None) -> bool:
        """判断是否为强势股 - 基于PDF框架的严格标准，加入涨停模式快速通道"""
        # 快速通道：涨停模式分析
        if limit_up_pattern:
            # 条件A：连续2天以上涨停
            if limit_up_pattern.get('max_consecutive_days', 0) >= 2:
                return True
            # 条件B：5天内2次以上非连续涨停
            if limit_up_pattern.get('limit_up_count', 0) >= 2:
                return True
            # 条件C：当日涨停且5天内至少1次涨停
            current_limit_up = dimensions.get('涨停类型', {}).get('score', 0) >= 80  # 涨停类型评分高表示当日涨停
            if current_limit_up and limit_up_pattern.get('limit_up_count', 0) >= 1:
                return True

        # 正常流程：PDF框架严格标准
        # 条件1：总体评分 >= 70（提高标准）
        if overall_score < 70:
            return False

        # 条件2：龙头属性评分 >= 70（必须是强势龙头）
        dragon_head_score = dimensions.get('龙头属性', {}).get('score', 0)
        if dragon_head_score < 70:
            return False

        # 条件3：是否领涨评分 >= 60（必须领涨明显）
        lingzhang_score = dimensions.get('是否领涨', {}).get('score', 0)
        if lingzhang_score < 60:
            return False

        # 条件4：是否正宗评分 >= 60（必须主题正宗）
        zhengzong_score = dimensions.get('是否正宗', {}).get('score', 0)
        if zhengzong_score < 60:
            return False

        # 条件5：涨停类型评分 >= 50（应该有涨停或大阳线）
        limit_up_score = dimensions.get('涨停类型', {}).get('score', 0)
        if limit_up_score < 50:
            return False

        # 条件6：资金性质评分 >= 60（必须有资金支持）
        capital_score = dimensions.get('资金性质', {}).get('score', 0)
        if capital_score < 60:
            return False

        return True


async def test_analysis():
    """测试分析服务"""
    service = StrongStockAnalysisService()

    # 测试神剑股份
    stock_id = "002361"
    test_date = date(2026, 4, 10)

    print(f"测试 {stock_id} 在 {test_date} 的强势股分析...")

    analysis = await service.analyze_stock_by_pdf_framework(stock_id, test_date)

    print(f"股票: {analysis['stock_name']} ({analysis['stock_id']})")
    print(f"交易日期: {analysis['trade_date']}")
    print(f"是否为强势股: {'✅ 是' if analysis['is_strong_stock'] else '❌ 否'}")
    print(f"总体评分: {analysis['overall_score']}/100")

    print(f"\n维度分析:")
    for dim_name, dim_data in analysis['dimensions'].items():
        score = dim_data.get('score', 0)
        print(f"  {dim_name}: {score}分")
        if 'reasons' in dim_data and dim_data['reasons']:
            for reason in dim_data['reasons'][:2]:
                print(f"    - {reason}")

    if analysis['strengths']:
        print(f"\n优点:")
        for strength in analysis['strengths']:
            print(f"  ✅ {strength}")

    if analysis['weaknesses']:
        print(f"\n弱点:")
        for weakness in analysis['weaknesses']:
            print(f"  ⚠️  {weakness}")

    await service.close()


if __name__ == "__main__":
    asyncio.run(test_analysis())

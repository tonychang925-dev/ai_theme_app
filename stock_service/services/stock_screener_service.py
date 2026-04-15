"""
选股器服务 - 基于35%/30%/20%/15%决策序列的选股引擎
"""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from stock_service.stock_screener_models import (
    DimensionDetails,
    DimensionScores,
    ScreeningExecution,
    ScreeningResult,
    ScreeningResultDetail,
)
from stock_service.repositories.stock_screener_repository import StockScreenerRepository
from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs
from stock_service.services.strong_stock_tracker_service import StrongStockTrackerService
from stock_service.models import StrongStockRecord

logger = logging.getLogger(__name__)


@dataclass
class ScreeningConfig:
    """选股配置"""

    strategy_id: str
    trade_date: date
    min_composite_score: float = 60.0
    limit: int = 100
    weight_config: Optional[Dict[str, float]] = None
    auto_tune_min_score: bool = True
    target_min_count: int = 30
    target_max_count: int = 120
    only_main_theme: bool = True  # 是否只从主线题材选股（默认True，避免选杂毛）
    weak_to_strong_required: bool = False  # 是否要求弱转强信号（用于弱转强策略）
    from_strong_stock_list: bool = False  # 是否从强势股清单中选股（优先考虑一周内的龙头/强势股）


@dataclass
class ScreeningRunMeta:
    requested_min_score: float
    tuned_min_score: float
    auto_tune_applied: bool
    total_scored: int
    pre_filter_count: int
    final_count: int
    target_min_count: int
    target_max_count: int


@dataclass
class StockScreeningContext:
    """选股执行上下文"""

    stock_id: str
    stock_name: str
    trade_date: date
    theme_info: Optional[Dict[str, Any]] = None
    mainline_data: Optional[Dict[str, Any]] = None
    cycle_data: Optional[Dict[str, Any]] = None
    leader_data: Optional[Dict[str, Any]] = None
    technical_data: Optional[Dict[str, Any]] = None
    leader_fallback_used: bool = False
    config: Optional[ScreeningConfig] = None  # 选股配置


class StockScreenerService:
    """选股器服务"""

    def __init__(
        self,
        screener_repo: StockScreenerRepository,
        theme_repo: Any = None,
        stock_repo: Any = None,
        weak_to_strong_service: Optional[WeakToStrongService] = None,
        strong_stock_tracker_service: Optional[StrongStockTrackerService] = None,
    ):
        # 为兼容旧调用方，保留 theme_repo/stock_repo 参数，但当前不依赖它们
        self.screener_repo = screener_repo
        self.theme_repo = theme_repo
        self.stock_repo = stock_repo
        self.weak_to_strong_service = weak_to_strong_service or WeakToStrongService()
        self.strong_stock_tracker_service = strong_stock_tracker_service or StrongStockTrackerService()

    async def execute_screening(self, config: ScreeningConfig) -> List[ScreeningResult]:
        """执行选股策略并持久化执行记录与结果。"""
        results, _ = await self.execute_screening_with_meta(config)
        return results

    async def execute_screening_with_meta(self, config: ScreeningConfig) -> Tuple[List[ScreeningResult], ScreeningRunMeta]:
        """执行选股策略并返回运行元信息。"""
        logger.info("开始执行选股策略: %s, 交易日: %s", config.strategy_id, config.trade_date)
        started_at = time.perf_counter()

        strategy = await self.screener_repo.get_strategy(config.strategy_id)
        if not strategy:
            raise ValueError(f"策略不存在: {config.strategy_id}")

        min_score = float(config.min_composite_score)
        if strategy.filter_config.get("min_composite_score") is not None:
            min_score = max(min_score, float(strategy.filter_config.get("min_composite_score", min_score)))

        weight_config = config.weight_config or strategy.weight_config
        effective_config = self._build_effective_config(config, strategy)

        stocks = await self._get_stocks_to_screen(effective_config)

        execution = ScreeningExecution(
            execution_id="",
            strategy_id=config.strategy_id,
            trade_date=config.trade_date,
            status="running",
            total_stocks=len(stocks),
            screened_stocks=0,
            results_count=0,
            execution_time_ms=0,
            error_message=None,
            created_at=datetime.now(),
            completed_at=None,
        )
        execution = await self.screener_repo.create_execution(execution)

        try:
            tasks = []
            for stock_id, stock_name in stocks:
                context = StockScreeningContext(
                    stock_id=stock_id,
                    stock_name=stock_name,
                    trade_date=config.trade_date,
                    config=effective_config,
                )
                tasks.append(self._score_stock(context, weight_config))

            scored_stocks = await asyncio.gather(*tasks, return_exceptions=True)
            valid_scored: List[ScreeningResult] = []
            for scored_stock in scored_stocks:
                if isinstance(scored_stock, Exception):
                    logger.error("股票评分失败: %s", scored_stock)
                    continue
                scored_stock.strategy_id = config.strategy_id
                scored_stock.trade_date = config.trade_date
                valid_scored.append(scored_stock)

            tuned_min_score, auto_tune_applied = self._tune_min_score(
                candidates=valid_scored,
                requested_min_score=min_score,
                auto_tune=config.auto_tune_min_score,
                target_min_count=max(int(config.target_min_count), 1),
                target_max_count=max(int(config.target_max_count), 1),
            )

            results = [item for item in valid_scored if item.composite_score >= tuned_min_score]
            results.sort(key=lambda x: x.composite_score, reverse=True)

            if config.auto_tune_min_score and config.target_max_count > 0 and len(results) > config.target_max_count:
                results = results[: config.target_max_count]

            if config.limit:
                results = results[: config.limit]

            for i, result in enumerate(results, 1):
                result.rank_position = i

            if execution:
                await self.screener_repo.save_results(results, execution.execution_id)
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                await self.screener_repo.update_execution(
                    execution.execution_id,
                    {
                        "status": "completed",
                        "screened_stocks": len(valid_scored),
                        "results_count": len(results),
                        "execution_time_ms": elapsed_ms,
                        "completed_at": datetime.now(),
                    },
                )

            logger.info("选股完成: 共筛选出 %s 只股票", len(results))
            meta = ScreeningRunMeta(
                requested_min_score=float(min_score),
                tuned_min_score=float(tuned_min_score),
                auto_tune_applied=auto_tune_applied,
                total_scored=len(valid_scored),
                pre_filter_count=sum(1 for x in valid_scored if x.composite_score >= min_score),
                final_count=len(results),
                target_min_count=max(int(config.target_min_count), 1),
                target_max_count=max(int(config.target_max_count), 1),
            )
            return results, meta

        except Exception as e:
            if execution:
                await self.screener_repo.update_execution(
                    execution.execution_id,
                    {
                        "status": "failed",
                        "error_message": str(e),
                        "completed_at": datetime.now(),
                    },
                )
            raise

    @staticmethod
    def _build_effective_config(config: ScreeningConfig, strategy: Any) -> ScreeningConfig:
        """根据策略定义构建有效执行配置，确保策略类型语义生效。"""
        filter_config = getattr(strategy, "filter_config", {}) or {}
        strategy_type = str(getattr(strategy, "strategy_type", "") or "").lower()
        strategy_id = str(getattr(strategy, "strategy_id", "") or "").lower()
        is_weak_to_strong = strategy_type == "weak_to_strong" or strategy_id == "weak_to_strong"

        return ScreeningConfig(
            strategy_id=config.strategy_id,
            trade_date=config.trade_date,
            min_composite_score=config.min_composite_score,
            limit=config.limit,
            weight_config=config.weight_config,
            auto_tune_min_score=config.auto_tune_min_score,
            target_min_count=config.target_min_count,
            target_max_count=config.target_max_count,
            # 统一从策略配置与请求配置合并，策略类型可自动开启弱转强要求
            only_main_theme=bool(filter_config.get("only_main_theme", config.only_main_theme)),
            weak_to_strong_required=bool(
                config.weak_to_strong_required
                or filter_config.get("weak_to_strong_required", False)
                or is_weak_to_strong
            ),
            from_strong_stock_list=bool(
                filter_config.get("from_strong_stock_list", config.from_strong_stock_list)
            ),
        )

    @staticmethod
    def _tune_min_score(
        *,
        candidates: List[ScreeningResult],
        requested_min_score: float,
        auto_tune: bool,
        target_min_count: int,
        target_max_count: int,
    ) -> Tuple[float, bool]:
        if not auto_tune or not candidates:
            return float(requested_min_score), False

        if target_min_count > target_max_count:
            target_min_count, target_max_count = target_max_count, target_min_count

        requested = float(requested_min_score)
        current_count = sum(1 for x in candidates if x.composite_score >= requested)
        if target_min_count <= current_count <= target_max_count:
            return requested, False

        sorted_scores = sorted((x.composite_score for x in candidates), reverse=True)
        if current_count < target_min_count:
            rank = min(max(target_min_count, 1), len(sorted_scores))
            tuned = float(sorted_scores[rank - 1])
        else:
            rank = min(max(target_max_count, 1), len(sorted_scores))
            tuned = float(sorted_scores[rank - 1])

        tuned = max(min(tuned, 100.0), 0.0)
        return tuned, True

    async def _get_stocks_to_screen(self, config: ScreeningConfig) -> List[Tuple[str, str]]:
        """从日频快照中提取待筛选股票。"""

        # 如果配置要求从强势股清单选股，优先从强势股清单获取
        if config.from_strong_stock_list:
            strong_stocks = self.strong_stock_tracker_service.get_weak_to_strong_candidates()
            if strong_stocks:
                # 返回弱转强候选股
                stocks = [(record.stock_id.split('.')[0] if '.' in record.stock_id else record.stock_id,
                          record.stock_name)
                         for record in strong_stocks]
                logger.info(f"从强势股清单获取{len(stocks)}只弱转强候选股票")
                return stocks
            else:
                # 如果没有弱转强候选，使用所有强势股
                all_strong_stocks = list(self.strong_stock_tracker_service._strong_stocks.values())
                if all_strong_stocks:
                    stocks = [(record.stock_id.split('.')[0] if '.' in record.stock_id else record.stock_id,
                              record.stock_name)
                             for record in all_strong_stocks]
                    logger.info(f"从强势股清单获取{len(stocks)}只强势股（无弱转强候选）")
                    return stocks
                else:
                    logger.warning("配置要求从强势股清单选股，但强势股清单为空，回退到常规选股")

        pool = await self.screener_repo._ensure_pool()

        # 基础查询：获取所有股票
        if not config.only_main_theme:
            sql = """
            SELECT DISTINCT
                split_part(stock_id, '.', 1) AS stock_id,
                MAX(stock_name) AS stock_name
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
              AND stock_id IS NOT NULL
              AND stock_id <> ''
            GROUP BY split_part(stock_id, '.', 1)
            ORDER BY split_part(stock_id, '.', 1)
            """
            params = [config.trade_date]
        else:
            # 只从主线题材选股：通过JOIN theme_mainline_judgement表过滤
            sql = """
            SELECT DISTINCT
                split_part(s.stock_id, '.', 1) AS stock_id,
                MAX(s.stock_name) AS stock_name
            FROM subject_stock_daily_snapshot s
            INNER JOIN theme_mainline_judgement m
                ON m.trade_date = s.trade_date
                AND m.subject_key = s.subject_key
                AND m.theme_tier = 'main'
            WHERE s.trade_date = $1::date
              AND s.stock_id IS NOT NULL
              AND s.stock_id <> ''
              AND m.is_main_theme = TRUE
            GROUP BY split_part(s.stock_id, '.', 1)
            ORDER BY split_part(s.stock_id, '.', 1)
            """
            params = [config.trade_date]

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
            return [(str(r["stock_id"]), str(r["stock_name"] or "")) for r in rows]
        except Exception as e:
            logger.error("获取待筛选股票失败: %s", e)
            return []

    async def _score_stock(self, context: StockScreeningContext, weight_config: Dict[str, float]) -> ScreeningResult:
        await self._load_stock_data(context)

        mainline_score = await self._score_mainline_dimension(context)
        cycle_score = await self._score_cycle_dimension(context)
        leader_score = await self._score_leader_dimension(context)
        technical_score = await self._score_technical_dimension(context)

        effective_weights = self._resolve_effective_weights(
            weight_config,
            {
                "mainline": context.mainline_data is not None,
                "cycle": context.cycle_data is not None,
                "leader": (context.leader_data is not None or context.leader_fallback_used),
                "technical": context.technical_data is not None,
            },
        )

        composite_score = (
            mainline_score * effective_weights["mainline"]
            + cycle_score * effective_weights["cycle"]
            + leader_score * effective_weights["leader"]
            + technical_score * effective_weights["technical"]
        )

        # 弱转强策略要求：如果要求弱转强信号但周期得分为0（表示无信号），强制综合得分为0
        config = context.config
        if config and config.weak_to_strong_required and cycle_score == 0.0:
            composite_score = 0.0
            # 更新筛选理由
            screening_reason = "不符合弱转强要求：无弱转强信号"
        else:
            screening_reason = self._generate_screening_reason(mainline_score, cycle_score, leader_score, technical_score)

        return ScreeningResult(
            stock_id=context.stock_id,
            stock_name=context.stock_name,
            composite_score=round(composite_score, 2),
            dimension_scores=DimensionScores(
                mainline=round(mainline_score, 2),
                cycle=round(cycle_score, 2),
                leader=round(leader_score, 2),
                technical=round(technical_score, 2),
            ),
            screening_reason=screening_reason,
            theme_info=context.theme_info,
        )

    async def _load_stock_data(self, context: StockScreeningContext) -> None:
        """加载评分所需数据，全部通过 asyncpg 查询。"""
        pool = await self.screener_repo._ensure_pool()

        try:
            async with pool.acquire() as conn:
                # 1) 股票主题材（按当日成交额最大）
                sql_theme = """
                SELECT
                    s.subject_key,
                    COALESCE(NULLIF(tmj.theme_name, ''), NULLIF(tcj.theme_name, ''), s.subject_key) AS theme_name,
                    s.amount,
                    s.limit_up,
                    s.is_leader,
                    s.rank_order,
                    s.pct_chg
                FROM subject_stock_daily_snapshot s
                LEFT JOIN theme_mainline_judgement tmj
                  ON tmj.trade_date = s.trade_date
                 AND tmj.subject_key = s.subject_key
                LEFT JOIN theme_cycle_judgement tcj
                  ON tcj.trade_date = s.trade_date
                 AND tcj.subject_key = s.subject_key
                WHERE s.trade_date = $1::date
                  AND split_part(s.stock_id, '.', 1) = $2
                ORDER BY s.amount DESC NULLS LAST
                LIMIT 1
                """
                theme_row = await conn.fetchrow(sql_theme, context.trade_date, context.stock_id)
                if theme_row:
                    context.theme_info = {
                        "subject_key": theme_row["subject_key"],
                        "theme_name": theme_row["theme_name"],
                        "amount": float(theme_row["amount"] or 0),
                        "limit_up": bool(theme_row["limit_up"] or False),
                        "is_leader": bool(theme_row["is_leader"] or False),
                        "rank_order": int(theme_row["rank_order"] or 0),
                        "pct_chg": float(theme_row["pct_chg"] or 0),
                    }

                # 2) 主线判断
                if context.theme_info:
                    sql_mainline = """
                    SELECT
                        event_chain_score,
                        market_recognition_score,
                        mainline_stability_score,
                        limit_up_count,
                        theme_tier,
                        novelty_score,
                        timing_score,
                        influence_score,
                        capital_persistence_score,
                        institution_participation_score,
                        retail_attention_score
                    FROM theme_mainline_judgement
                    WHERE trade_date = $1::date
                      AND subject_key = $2
                    LIMIT 1
                    """
                    context.mainline_data = await conn.fetchrow(
                        sql_mainline,
                        context.trade_date,
                        context.theme_info["subject_key"],
                    )

                # 3) 周期判断
                if context.theme_info:
                    sql_cycle = """
                    SELECT
                        primary_cycle_stage,
                        confidence,
                        action_bias,
                        is_divergence,
                        is_rebound,
                        is_fermentation,
                        is_start,
                        is_climax,
                        is_fade,
                        limit_up_count,
                        leader_status,
                        board_effect_status,
                        is_main_theme,
                        trade_date,
                        subject_key,
                        theme_name
                    FROM theme_cycle_judgement
                    WHERE trade_date = $1::date
                      AND subject_key = $2
                    LIMIT 1
                    """
                    context.cycle_data = await conn.fetchrow(
                        sql_cycle,
                        context.trade_date,
                        context.theme_info["subject_key"],
                    )

                # 4) 龙头判断
                sql_leader = """
                SELECT candidate_rank, composite_score, role_label
                FROM theme_leader_candidate
                WHERE trade_date = $1::date
                  AND split_part(stock_id, '.', 1) = $2
                ORDER BY candidate_rank ASC, composite_score DESC
                LIMIT 1
                """
                context.leader_data = await conn.fetchrow(sql_leader, context.trade_date, context.stock_id)

                # 5) 技术面（快照 + 位置 + 形态）
                sql_tech = """
                WITH base AS (
                    SELECT
                        split_part(s.stock_id, '.', 1) AS stock_id,
                        CASE
                            WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 14
                                THEN NULLIF(s.raw_json->>14, '')::numeric
                            ELSE NULL
                        END AS turnover_rate,
                        CASE
                            WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 15
                                THEN NULLIF(s.raw_json->>15, '')::numeric
                            ELSE NULL
                        END AS volume_ratio,
                        s.pct_chg,
                        CASE
                            WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 20
                                THEN NULLIF(s.raw_json->>20, '')::integer
                            ELSE NULL
                        END AS current_flag
                    FROM subject_stock_daily_snapshot s
                    WHERE s.trade_date = $1::date
                      AND split_part(s.stock_id, '.', 1) = $2
                    ORDER BY s.amount DESC NULLS LAST
                    LIMIT 1
                )
                SELECT
                    b.turnover_rate,
                    b.volume_ratio,
                    b.pct_chg,
                    b.current_flag,
                    p.trend_strength_score,
                    x.pattern_labels
                FROM base b
                LEFT JOIN stock_position_judgement p
                  ON p.trade_date = $1::date
                 AND split_part(p.stock_id, '.', 1) = b.stock_id
                LEFT JOIN stock_pattern_judgement x
                  ON x.trade_date = $1::date
                 AND split_part(x.stock_id, '.', 1) = b.stock_id
                """
                context.technical_data = await conn.fetchrow(sql_tech, context.trade_date, context.stock_id)

        except Exception as e:
            logger.error("加载股票数据失败 %s: %s", context.stock_id, e)

    async def _score_mainline_dimension(self, context: StockScreeningContext) -> float:
        row = context.mainline_data
        if not row:
            return 0.0
        try:
            # 原有字段
            event_chain = float(row.get("event_chain_score") or 0)
            recognition = float(row.get("market_recognition_score") or 0)
            stability = float(row.get("mainline_stability_score") or 0)
            limit_up_count = float(row.get("limit_up_count") or 0)
            tier = str(row.get("theme_tier") or "")

            # 新增增强字段
            novelty_score = float(row.get("novelty_score") or 0)
            timing_score = float(row.get("timing_score") or 0)
            influence_score = float(row.get("influence_score") or 0)
            capital_persistence_score = float(row.get("capital_persistence_score") or 0)
            institution_participation_score = float(row.get("institution_participation_score") or 0)
            retail_attention_score = float(row.get("retail_attention_score") or 0)

            # 1. 原有评分（最大100分）
            base_score = 0.0
            base_score += min(event_chain, 40)  # 0-40
            base_score += min(recognition, 30)  # 0-30
            base_score += min(stability, 30)    # 0-30

            if tier == "main":
                base_score += 5
            elif tier == "strong_branch":
                base_score += 2

            base_score += min(limit_up_count, 5)

            # 2. 逻辑维度增强评分（新颖度 + 时机 + 影响广度）
            # 每个字段已经在其自身范围内（0-30, 0-25, 0-25），总和最大80
            logic_dimension_total = novelty_score + timing_score + influence_score
            logic_enhanced_score = logic_dimension_total * 0.3  # 最大80 * 0.3 = 24分

            # 3. 市场维度增强评分（资金持续性 + 机构参与度 + 散户关注度）
            # 每个字段已经在其自身范围内（0-15, 0-10, 0-10），总和最大35
            market_dimension_total = capital_persistence_score + institution_participation_score + retail_attention_score
            market_enhanced_score = market_dimension_total * 0.2  # 最大35 * 0.2 = 7分

            # 4. 总分（限制在100分内）
            total_score = base_score + logic_enhanced_score + market_enhanced_score
            return min(total_score, 100.0)
        except Exception as e:
            logger.error("计算主线维度得分失败 %s: %s", context.stock_id, e)
            return 0.0

    async def _score_cycle_dimension(self, context: StockScreeningContext) -> float:
        row = context.cycle_data
        if not row:
            return 0.0
        try:
            stage = str(row.get("primary_cycle_stage") or "unknown")
            confidence = float(row.get("confidence") or 0)
            action_bias = str(row.get("action_bias") or "")

            stage_scores = {
                "启动": 40,
                "发酵": 35,
                "高潮": 25,
                "退潮": 10,
                "startup": 40,
                "fermentation": 35,
                "climax": 25,
                "decline": 10,
                "divergence": 30,  # 分歧阶段
                "rebound": 35,     # 回流/弱转强阶段
            }
            stage_score = stage_scores.get(stage, 10)

            # 弱转强额外加分：如果action_bias包含"弱转强"或阶段是分歧/回流
            weak_to_strong_bonus = 0.0
            if "弱转强" in action_bias or stage in ["divergence", "rebound"]:
                weak_to_strong_bonus = 15.0  # 弱转强额外加分

            # 使用weak_to_strong_service进行更精确的弱转强评分
            weak_to_strong_enhancement = 0.0
            signals = []  # 初始化信号列表
            try:
                # 构建ThemeCycleJudgement对象
                from stock_service.models import ThemeCycleJudgement

                # 获取股票基本信息
                stock_id = context.stock_id
                stock_name = context.stock_name
                trade_date = context.trade_date.isoformat()
                theme_info = context.theme_info or {}
                subject_key = theme_info.get("subject_key", "")
                theme_name = theme_info.get("theme_name", subject_key)

                # 构建cycle_judgement对象
                cycle_judgement = ThemeCycleJudgement(
                    trade_date=trade_date,
                    subject_key=subject_key,
                    theme_name=theme_name,
                    is_main_theme=bool(row.get("is_main_theme") or False),
                    is_start=bool(row.get("is_start") or False),
                    is_fermentation=bool(row.get("is_fermentation") or False),
                    is_divergence=bool(row.get("is_divergence") or False),
                    is_rebound=bool(row.get("is_rebound") or False),
                    is_climax=bool(row.get("is_climax") or False),
                    is_fade=bool(row.get("is_fade") or False),
                    primary_cycle_stage=stage,
                    limit_up_count=int(row.get("limit_up_count") or 0),
                    leader_status=str(row.get("leader_status") or ""),
                    board_effect_status=str(row.get("board_effect_status") or ""),
                    action_bias=action_bias,
                    confidence=confidence,
                    conclusion=""
                )

                # 构建输入数据
                inputs = WeakToStrongDetectionInputs(
                    cycle_judgement=cycle_judgement,
                    abnormal_signal=None,  # 暂时不传递异常信号
                    prev_day_data=None,    # 暂时不传递前日数据
                    current_day_data=context.theme_info,  # 使用theme_info作为当前数据
                    market_environment=None,  # 暂时不传递市场环境
                    theme_environment=None    # 暂时不传递题材环境
                )

                # 检测弱转强信号
                signals = await self.weak_to_strong_service.detect_weak_to_strong_signals(
                    context.trade_date, inputs
                )

                if signals:
                    # 获取信号强度作为增强分
                    signal_strength = max(s.signal_strength for s in signals)
                    # 将信号强度转换为额外加分 (0-25分)
                    weak_to_strong_enhancement = min(signal_strength * 0.25, 25.0)

            except Exception as e:
                logger.debug(f"弱转强服务调用失败，使用基础加分: {e}")
                # 服务调用失败时，使用基础弱转强加分逻辑

            # 弱转强策略要求：至少满足“明确弱转强信号”或“阶段/偏向特征”
            config = context.config
            has_weak_stage_hint = ("弱转强" in action_bias) or (stage in ["divergence", "rebound"])
            if config and config.weak_to_strong_required and not signals and not has_weak_stage_hint:
                return 0.0

            confidence_score = min(max(confidence, 0), 100) * 0.6  # 0-60
            total_score = stage_score + confidence_score + weak_to_strong_bonus + weak_to_strong_enhancement
            return min(total_score, 100.0)
        except Exception as e:
            logger.error("计算周期维度得分失败 %s: %s", context.stock_id, e)
            return 0.0

    async def _score_leader_dimension(self, context: StockScreeningContext) -> float:
        row = context.leader_data
        if not row:
            theme_info = context.theme_info or {}
            is_leader = bool(theme_info.get("is_leader") or False)
            limit_up = bool(theme_info.get("limit_up") or False)
            rank_order = int(theme_info.get("rank_order") or 0)
            pct_chg = float(theme_info.get("pct_chg") or 0)

            # 龙头候选缺失时使用快照兜底，避免 leader 维度大面积归零
            if is_leader:
                context.leader_fallback_used = True
                return 35.0
            if limit_up:
                context.leader_fallback_used = True
                return 25.0
            if pct_chg >= 5:
                context.leader_fallback_used = True
                return 20.0
            if 0 < rank_order <= 10:
                context.leader_fallback_used = True
                return 18.0
            return 10.0
        try:
            rank = int(row.get("candidate_rank") or 99)
            composite = float(row.get("composite_score") or 0)
            role_label = str(row.get("role_label") or "")

            if rank == 1:
                position_score = 50
            elif rank <= 3:
                position_score = 40
            elif rank <= 5:
                position_score = 30
            else:
                position_score = 10

            role_bonus = 10 if "龙头" in role_label else 0
            quality_score = min(max(composite, 0), 40)
            return min(position_score + role_bonus + quality_score, 100.0)
        except Exception as e:
            logger.error("计算龙头维度得分失败 %s: %s", context.stock_id, e)
            return 0.0

    @staticmethod
    def _resolve_effective_weights(
        weight_config: Dict[str, float],
        availability: Dict[str, bool],
    ) -> Dict[str, float]:
        keys = ("mainline", "cycle", "leader", "technical")
        defaults = {"mainline": 0.35, "cycle": 0.30, "leader": 0.20, "technical": 0.15}
        base = {k: max(float(weight_config.get(k, defaults[k])), 0.0) for k in keys}

        active = {k: v for k, v in base.items() if availability.get(k, False)}
        if not active:
            total = sum(base.values())
            if total <= 0:
                return {k: 0.25 for k in keys}
            return {k: base[k] / total for k in keys}

        active_total = sum(active.values())
        if active_total <= 0:
            even = 1.0 / float(len(active))
            return {k: (even if k in active else 0.0) for k in keys}

        return {k: (active[k] / active_total if k in active else 0.0) for k in keys}

    async def _score_technical_dimension(self, context: StockScreeningContext) -> float:
        row = context.technical_data
        if not row:
            return 0.0
        try:
            abnormal_flag = int(row.get("current_flag") or 0)
            trend_strength = float(row.get("trend_strength_score") or 0)
            turnover_rate = float(row.get("turnover_rate") or 0)
            volume_ratio = float(row.get("volume_ratio") or 0)
            pct_chg = float(row.get("pct_chg") or 0)
            pattern_labels = row.get("pattern_labels")

            flag_scores = {3: 40, 4: 35, 1: 22, 2: 18, -1: 8, -2: 2, 0: 10}
            score = flag_scores.get(abnormal_flag, 10)

            score += min(max(trend_strength, 0), 30)

            liq = min(max(turnover_rate, 0), 20) * 0.6
            vol = min(max(volume_ratio, 0), 5) * 2
            pchg = min(max(pct_chg + 5, 0), 20)
            score += min(liq + vol + pchg, 30)

            if pattern_labels:
                score += 5

            return min(score, 100.0)
        except Exception as e:
            logger.error("计算技术面维度得分失败 %s: %s", context.stock_id, e)
            return 0.0

    def _generate_screening_reason(
        self,
        mainline_score: float,
        cycle_score: float,
        leader_score: float,
        technical_score: float,
    ) -> str:
        reasons: List[str] = []

        if mainline_score >= 70:
            reasons.append("主线题材明确")
        elif mainline_score >= 50:
            reasons.append("题材有一定关注度")

        if cycle_score >= 70:
            reasons.append("处于行情启动或发酵期")
        elif cycle_score >= 50:
            reasons.append("周期阶段相对有利")

        if leader_score >= 70:
            reasons.append("具备龙头特征")
        elif leader_score >= 50:
            reasons.append("有一定龙头潜力")

        if technical_score >= 70:
            reasons.append("技术面表现强势")
        elif technical_score >= 50:
            reasons.append("技术面尚可")

        if not reasons:
            reasons.append("综合评分达标")

        return "；".join(reasons)

    async def get_result_detail(self, result_id: str) -> Optional[ScreeningResultDetail]:
        result = await self.screener_repo.get_result(result_id)
        if not result:
            return None

        detail = ScreeningResultDetail(
            **asdict(result),
            dimension_details=DimensionDetails(
                mainline={
                    "strength_score": result.dimension_scores.mainline,
                    "heat_rank": 0,
                    "capital_attention": 0,
                    "reasoning": "基于主线评分规则计算",
                },
                cycle={
                    "stage_score": result.dimension_scores.cycle,
                    "duration_score": 0,
                    "stability_score": 0,
                    "reasoning": "基于周期阶段与置信度计算",
                },
                leader={
                    "position_score": result.dimension_scores.leader,
                    "leading_effect": 0,
                    "capital_recognition": 0,
                    "reasoning": "基于龙头候选排名与综合分计算",
                },
                technical={
                    "abnormal_score": result.dimension_scores.technical,
                    "pattern_score": 0,
                    "volume_price_score": 0,
                    "reasoning": "基于异动标记与技术指标计算",
                },
            ),
        )
        return detail

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
import asyncpg

from stock_service.services.weak_to_strong_candidate_builder import (
    WeakToStrongCandidateBuilder,
    CandidateBuildResult,
)
from stock_service.services.enhanced_mainline_judgement_service import (
    EnhancedMainlineJudgementService,
)
from stock_service.services.enhanced_cycle_judgement_service import (
    EnhancedCycleJudgementService,
    PreviousCycleState,
)
from stock_service.services.unified_cycle_scoring_service import (
    UnifiedCycleScoringService,
    CycleEvidenceInput,
)


@dataclass
class CycleFeatureInputs:
    """周期特征输入"""
    subject_key: str
    trade_date: date
    mainline_alive: bool = False
    mainline_strength_score: float = 0.0
    cycle_state: str = ""
    fade_watch: bool = False
    fade_confirmed: bool = False
    previous_cycle_state: Optional[str] = None


class EnhancedCandidateBuilder(WeakToStrongCandidateBuilder):
    """
    增强版弱转强候选构建器
    主要优化：
    1. 将硬门槛改为连续评分
    2. 集成主线周期特征
    3. 支持三级准入机制
    4. 保持向后兼容
    """

    ENHANCED_RULE_VERSION = "weak_to_strong_candidate.enhanced.v1"

    # 评分阈值
    STRONG_BACKGROUND_THRESHOLD = 60  # 强势背景阈值
    REPAIR_WINDOW_THRESHOLD = 50      # 修复窗口阈值
    OBSERVE_THRESHOLD = 30            # 观察流阈值

    def __init__(self, config=None):
        super().__init__(config)
        self.mainline_service = EnhancedMainlineJudgementService()
        self.cycle_service = EnhancedCycleJudgementService()

    def calculate_strong_background_score(self,
                                         is_leader: bool,
                                         limit_up: bool,
                                         recent_limit_up_count: int,
                                         rank_order: int) -> float:
        """
        计算强势背景评分（0-100）
        替代原有的硬门槛
        """
        score = 0.0

        # 龙头权重最高
        if is_leader:
            score += 40.0

        # 当日涨停
        if limit_up:
            score += 30.0

        # 近期涨停次数（阶梯式评分）
        if recent_limit_up_count >= 4:
            score += 70.0  # 连续4天涨停，极度强势
        elif recent_limit_up_count == 3:
            score += 50.0  # 3天涨停，非常强势
        elif recent_limit_up_count == 2:
            score += 30.0  # 2天涨停，基本强势
        elif recent_limit_up_count == 1:
            score += 15.0  # 1天涨停，有强势信号
        # 0个涨停不加分

        # 排名靠前
        if rank_order <= 3:
            score += 20.0
        elif rank_order <= 10:
            score += 10.0

        return min(score, 100.0)

    def calculate_repair_window_score(self,
                                     action_bias: str,
                                     stage: str,
                                     is_divergence: bool,
                                     is_rebound: bool,
                                     is_fermentation: bool,
                                     is_fade: bool,
                                     fade_confirmed: bool = False) -> float:
        """
        计算修复窗口评分（0-100）
        替代原有的硬门槛
        """
        score = 0.0

        # 动作偏好多头修复
        if "弱转强" in action_bias or "修复" in action_bias or "回流" in action_bias:
            score += 40.0

        # 周期阶段
        stage_scores = {
            "divergence": 35.0,
            "rebound": 30.0,
            "fermentation": 25.0,
            "start": 20.0,
            "分歧": 35.0,
            "回流": 30.0,
            "发酵": 25.0,
            "启动": 20.0,
        }
        if stage in stage_scores:
            score += stage_scores[stage]

        # 布尔字段
        if is_divergence:
            score += 20.0
        if is_rebound:
            score += 15.0
        if is_fermentation:
            score += 10.0

        # 退潮扣分（但不直接过滤）
        if fade_confirmed:
            score -= 60.0  # 退潮确认大幅扣分
        elif is_fade:
            score -= 5.0  # 退潮观察轻微扣分（原15，调整为5）

        return max(0.0, min(score, 100.0))

    def determine_pool_entry_type(self,
                                 strong_bg_score: float,
                                 repair_score: float,
                                 mainline_alive: bool,
                                 fade_confirmed: bool) -> str:
        """
        确定候选池进入类型
        三级准入：formal, observe_only, reject
        """
        # 正式准入条件
        # 修改：移除mainline_alive要求，弱转强不应要求主题必须是主线
        # 关键：题材未全面退潮，仍有资金支撑，板块仍有活口和助攻即可
        if (strong_bg_score >= self.STRONG_BACKGROUND_THRESHOLD and
            repair_score >= self.REPAIR_WINDOW_THRESHOLD and
            not fade_confirmed):
            return "formal"

        # 观察流条件（放宽要求，但不允许退潮确认）
        if not fade_confirmed:
            if (strong_bg_score >= self.OBSERVE_THRESHOLD or
                repair_score >= self.OBSERVE_THRESHOLD):
                return "observe_only"

        # 拒绝
        return "reject"

    async def _build_evidence_input(self, trade_date: date, subject_key: str,
                                   conn: asyncpg.Connection) -> Optional[CycleEvidenceInput]:
        """从数据库构建周期证据输入

        尝试从theme_cycle_evidence_daily表查询，如果不存在则从现有表构建简化版本
        """
        # 首先检查theme_cycle_evidence_daily表是否存在
        evidence_exists = await self._check_table_exists(conn, "theme_cycle_evidence_daily")

        if evidence_exists:
            # 从evidence表查询
            sql = """
            SELECT
                event_strength_score,
                event_continuity_score,
                strong_event_count_7d,
                event_recency_days,
                leader_alive_score,
                leader_breakdown_flag,
                relay_strength_score,
                front_row_survival_ratio,
                limit_up_count,
                limit_down_count,
                red_ratio,
                big_drop_ratio,
                front_row_strength_score,
                theme_support_score,
                break_start_pivot
            FROM theme_cycle_evidence_daily
            WHERE trade_date = $1 AND subject_key = $2
            """
            row = await conn.fetchrow(sql, trade_date, subject_key)
            if row:
                return CycleEvidenceInput(
                    trade_date=trade_date.isoformat(),
                    subject_key=subject_key,
                    theme_name="",  # 需要从其他表获取
                    event_strength_score=float(row["event_strength_score"] or 0),
                    event_continuity_score=float(row["event_continuity_score"] or 0),
                    strong_event_count_7d=int(row["strong_event_count_7d"] or 0),
                    event_recency_days=int(row["event_recency_days"]) if row["event_recency_days"] is not None else None,
                    leader_alive_score=float(row["leader_alive_score"] or 0),
                    leader_breakdown_flag=bool(row["leader_breakdown_flag"]),
                    relay_strength_score=float(row["relay_strength_score"] or 0),
                    front_row_survival_ratio=float(row["front_row_survival_ratio"] or 0),
                    limit_up_count=int(row["limit_up_count"] or 0),
                    limit_down_count=int(row["limit_down_count"] or 0),
                    red_ratio=float(row["red_ratio"] or 0),
                    big_drop_ratio=float(row["big_drop_ratio"] or 0),
                    front_row_strength_score=float(row["front_row_strength_score"] or 0),
                    theme_support_score=float(row["theme_support_score"] or 0),
                    break_start_pivot=bool(row["break_start_pivot"]),
                )

        # 回退：从现有表构建简化版本
        # 查询theme_mainline_judgement和theme_cycle_judgement
        sql = """
        SELECT
            m.event_chain_score,
            m.event_chain_continuity_score,
            c.limit_up_count,
            c.leader_status,
            c.board_effect_status,
            c.is_fade
        FROM theme_mainline_judgement m
        LEFT JOIN theme_cycle_judgement c
          ON c.trade_date = m.trade_date
         AND c.subject_key = m.subject_key
        WHERE m.trade_date = $1 AND m.subject_key = $2
        """
        row = await conn.fetchrow(sql, trade_date, subject_key)
        if row:
            # 简化映射：使用现有数据构建证据输入
            event_chain_score = float(row["event_chain_score"] or 0)
            event_chain_continuity_score = float(row["event_chain_continuity_score"] or 0)
            limit_up_count = int(row["limit_up_count"] or 0)
            leader_status = str(row["leader_status"] or "")
            is_fade = bool(row["is_fade"])

            # 估算各项评分
            # 事件强度评分 ≈ 事件链分数
            event_strength_score = event_chain_score
            # 事件连续性评分 ≈ 事件链连续性分数
            event_continuity_score = event_chain_continuity_score
            # 强事件数量：简化，如果有事件链分数则假设至少1个
            strong_event_count_7d = 1 if event_chain_score > 30 else 0
            # 龙头存活评分：基于leader_status估算
            if "龙头加强" in leader_status or "龙头强势" in leader_status:
                leader_alive_score = 80.0
            elif "龙头活跃" in leader_status:
                leader_alive_score = 60.0
            else:
                leader_alive_score = 30.0
            # 龙头破位标志：如果is_fade且leader_alive_score低
            leader_breakdown_flag = is_fade and leader_alive_score < 40
            # 接力强度评分：简化，基于limit_up_count
            relay_strength_score = min(limit_up_count * 10.0, 100.0)
            # 前排存活率：简化
            front_row_survival_ratio = 0.7 if limit_up_count > 0 else 0.3
            # 跌停数量：未知，设为0
            limit_down_count = 0
            # 红盘比例：未知，设为0.5
            red_ratio = 0.5
            # 大跌比例：未知，设为0.1
            big_drop_ratio = 0.1
            # 前排强度评分：基于limit_up_count
            front_row_strength_score = min(limit_up_count * 15.0, 100.0)
            # 板块技术支撑评分：未知，设为60
            theme_support_score = 60.0
            # 是否跌破启动枢轴：未知
            break_start_pivot = False

            return CycleEvidenceInput(
                trade_date=trade_date.isoformat(),
                subject_key=subject_key,
                theme_name="",  # 需要从其他表获取
                event_strength_score=event_strength_score,
                event_continuity_score=event_continuity_score,
                strong_event_count_7d=strong_event_count_7d,
                event_recency_days=1 if event_chain_score > 0 else None,
                leader_alive_score=leader_alive_score,
                leader_breakdown_flag=leader_breakdown_flag,
                relay_strength_score=relay_strength_score,
                front_row_survival_ratio=front_row_survival_ratio,
                limit_up_count=limit_up_count,
                limit_down_count=limit_down_count,
                red_ratio=red_ratio,
                big_drop_ratio=big_drop_ratio,
                front_row_strength_score=front_row_strength_score,
                theme_support_score=theme_support_score,
                break_start_pivot=break_start_pivot,
            )

        return None

    async def fetch_cycle_features(self, trade_date: date,
                                   subject_key: str) -> CycleFeatureInputs:
        """
        获取主线周期特征
        从V2表查询或实时计算
        """
        # TODO: 实现从theme_cycle_judgement_v2表查询
        # 目前使用简化版本

        # 简化：检查V2表是否存在
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 检查V2表
            v2_exists = await self._check_table_exists(conn, "theme_cycle_judgement_v2")

            if v2_exists:
                # 从V2表查询
                sql = """
                SELECT
                    final_mainline_alive,
                    mainline_strength_score,
                    final_cycle_state,
                    fade_watch,
                    fade_confirmed,
                    previous_cycle_state
                FROM theme_cycle_judgement_v2
                WHERE trade_date = $1 AND subject_key = $2
                """
                row = await conn.fetchrow(sql, trade_date, subject_key)
                if row:
                    # 退潮状态修正（V2表）
                    cycle_state = str(row["final_cycle_state"] or "")
                    fade_watch = bool(row["fade_watch"])
                    fade_confirmed = bool(row["fade_confirmed"])

                    # 如果退潮确认，检查是否有硬证据（V2表可能已有更准确判断，但仍检查）
                    if fade_confirmed:
                        # 退潮确认需要最强硬证据，如果数据中标记为确认，我们信任但可添加日志
                        print(f"  ⚠️ 周期状态：主题{subject_key}，退潮确认（需硬证据验证）")

                    return CycleFeatureInputs(
                        subject_key=subject_key,
                        trade_date=trade_date,
                        mainline_alive=bool(row["final_mainline_alive"]),
                        mainline_strength_score=float(row["mainline_strength_score"] or 0),
                        cycle_state=cycle_state,
                        fade_watch=fade_watch,
                        fade_confirmed=fade_confirmed,
                        previous_cycle_state=row["previous_cycle_state"]
                    )

            # 回退：从原有表查询
            sql = """
            SELECT
                is_main_theme,
                primary_cycle_stage,
                is_fade,
                limit_up_count,
                leader_status
            FROM theme_cycle_judgement
            WHERE trade_date = $1 AND subject_key = $2
            """
            row = await conn.fetchrow(sql, trade_date, subject_key)
            if row:
                # 简化转换：is_main_theme作为mainline_alive
                mainline_alive = bool(row["is_main_theme"])
                cycle_state = str(row["primary_cycle_stage"] or "")
                is_fade = bool(row["is_fade"])
                limit_up_count = int(row["limit_up_count"] or 0)
                leader_status = str(row["leader_status"] or "")

                # 退潮状态修正：检查硬证据
                # 用户指出：退潮判断必须有硬证据，没有硬证据就不能判断是退潮
                # 硬证据包括：龙头已死、板块大面积跌停、无接力卡位等
                corrected_is_fade = is_fade
                corrected_cycle_state = cycle_state

                # 如果原状态为fade，检查是否满足硬证据
                if cycle_state == "fade" or is_fade:
                    # 硬证据检查：
                    # 1. 是否有涨停或强势股活口
                    has_live_stocks = limit_up_count > 0
                    # 2. 龙头状态（简化：通过leader_status判断）
                    leader_dead = "走弱" in leader_status or "跌停" in leader_status
                    # 3. 板块结构（简化：涨停数极少）
                    board_collapse = limit_up_count == 0

                    # 如果不满足硬证据，修正状态为分歧或修复
                    if has_live_stocks or not leader_dead:
                        # 仍有活口或龙头未死，视为分歧而非退潮
                        corrected_cycle_state = "divergence"
                        corrected_is_fade = False
                        # 打印修正日志（调试用）
                        print(f"  ⚠️ 周期状态修正：主题{subject_key}，原状态fade，修正为divergence（有活口）")
                    elif not board_collapse:
                        # 板块未完全塌方
                        corrected_cycle_state = "fade_watch"
                        corrected_is_fade = True  # 但标记为观察而非确认
                        print(f"  ⚠️ 周期状态修正：主题{subject_key}，原状态fade，修正为fade_watch（板块未完全塌方）")

                # 估算强度评分
                strength_score = 60.0 if mainline_alive else 30.0

                # 退潮状态细分
                fade_watch = corrected_is_fade
                fade_confirmed = False  # 原表无此字段，且需要硬证据确认

                return CycleFeatureInputs(
                    subject_key=subject_key,
                    trade_date=trade_date,
                    mainline_alive=mainline_alive,
                    mainline_strength_score=strength_score,
                    cycle_state=corrected_cycle_state,
                    fade_watch=fade_watch,
                    fade_confirmed=fade_confirmed
                )

        # 默认值
        return CycleFeatureInputs(
            subject_key=subject_key,
            trade_date=trade_date,
            mainline_alive=False,
            mainline_strength_score=30.0,
            cycle_state="",
            fade_watch=False,
            fade_confirmed=False
        )

    async def _check_table_exists(self, conn: asyncpg.Connection, table_name: str) -> bool:
        """检查表是否存在"""
        sql = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = $1
        )
        """
        return await conn.fetchval(sql, table_name)

    def _to_enhanced_candidate(self, row: asyncpg.Record,
                               trade_date: date,
                               next_trade_date: date,
                               cycle_features: CycleFeatureInputs) -> Optional[Dict[str, Any]]:
        """
        构建增强版候选记录
        集成周期特征和三级准入
        """
        # 创建修正后的row副本，使用修正后的周期特征
        corrected_row = dict(row)
        # 修正周期状态字段
        corrected_row["is_fade"] = cycle_features.fade_confirmed  # 使用退潮确认状态，而不是原始is_fade
        # fade_watch视为分歧阶段进行评分
        if cycle_features.cycle_state == "fade_watch":
            corrected_row["primary_cycle_stage"] = "divergence"
        else:
            corrected_row["primary_cycle_stage"] = cycle_features.cycle_state  # 使用修正后的周期状态
        # 根据修正后的状态更新action_bias
        # fade_watch视为分歧阶段进行评分，但不影响fade_watch标记
        if (cycle_features.cycle_state == "divergence" or
            cycle_features.cycle_state == "repair" or
            cycle_features.cycle_state == "fade_watch"):
            corrected_row["action_bias"] = "关注弱转强"
        elif cycle_features.fade_confirmed:
            corrected_row["action_bias"] = "放弃"
        # 更新布尔字段
        # fade_watch视为分歧阶段进行评分
        corrected_row["is_divergence"] = (cycle_features.cycle_state == "divergence" or
                                          cycle_features.cycle_state == "fade_watch")
        corrected_row["is_rebound"] = cycle_features.cycle_state == "rebound"
        corrected_row["is_fermentation"] = cycle_features.cycle_state == "fermentation"

        # 为父类过滤创建一个临时副本，放宽fade_watch条件
        parent_row = corrected_row.copy()

        # 处理空周期状态：对于有近期涨停的股票，假设处于分歧阶段以通过父类过滤
        recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
        if not cycle_features.cycle_state and recent_limit_up_count >= 2:
            parent_row["primary_cycle_stage"] = "divergence"
            parent_row["action_bias"] = "关注弱转强"
            parent_row["is_divergence"] = True
            parent_row["is_fade"] = False
        elif cycle_features.cycle_state == "fade_watch":
            # 父类要求repair_window，将fade_watch视为divergence以通过过滤
            parent_row["primary_cycle_stage"] = "divergence"
            parent_row["action_bias"] = "关注弱转强"
            parent_row["is_divergence"] = True
            parent_row["is_fade"] = False

        # 使用父类方法构建基础候选（使用放宽条件的row）
        base_candidate = super()._to_candidate(parent_row, trade_date, next_trade_date)
        if base_candidate is None:
            # 即使放宽条件后仍然被过滤，可能是其他原因（如强势背景不足）
            # 可以尝试直接构建候选，但为了简单，返回None
            return None

        # 提取评分所需字段（使用修正后的row）
        is_leader = bool(corrected_row.get("is_leader") or False)
        limit_up = bool(corrected_row.get("limit_up") or False)
        recent_limit_up_count = int(corrected_row.get("recent_limit_up_count") or 0)
        rank_order = int(corrected_row.get("rank_order") or 999)

        action_bias = str(corrected_row.get("action_bias") or "")
        stage = str(corrected_row.get("primary_cycle_stage") or "").lower()
        is_divergence = bool(corrected_row.get("is_divergence") or False)
        is_rebound = bool(corrected_row.get("is_rebound") or False)
        is_fermentation = bool(corrected_row.get("is_fermentation") or False)
        is_fade = bool(corrected_row.get("is_fade") or False)

        # 计算增强评分
        strong_bg_score = self.calculate_strong_background_score(
            is_leader, limit_up, recent_limit_up_count, rank_order
        )
        repair_score = self.calculate_repair_window_score(
            action_bias, stage, is_divergence, is_rebound, is_fermentation,
            is_fade, cycle_features.fade_confirmed
        )

        # 确定准入类型
        entry_type = self.determine_pool_entry_type(
            strong_bg_score, repair_score,
            cycle_features.mainline_alive, cycle_features.fade_confirmed
        )

        # 构建增强证据
        enhanced_evidence = json.loads(base_candidate.get("evidence_json", "{}"))
        enhanced_evidence["enhanced_features"] = {
            "strong_background_score": round(strong_bg_score, 2),
            "repair_window_score": round(repair_score, 2),
            "mainline_alive": cycle_features.mainline_alive,
            "mainline_strength_score": round(cycle_features.mainline_strength_score, 2),
            "cycle_state": cycle_features.cycle_state,
            "fade_watch": cycle_features.fade_watch,
            "fade_confirmed": cycle_features.fade_confirmed,
            "pool_entry_type": entry_type,
            "thresholds": {
                "strong_background": self.STRONG_BACKGROUND_THRESHOLD,
                "repair_window": self.REPAIR_WINDOW_THRESHOLD,
                "observe": self.OBSERVE_THRESHOLD
            }
        }

        # 更新候选记录
        enhanced_candidate = base_candidate.copy()
        enhanced_candidate.update({
            "rule_version": self.ENHANCED_RULE_VERSION,
            "evidence_json": json.dumps(enhanced_evidence, ensure_ascii=False),
            "pool_entry_type": entry_type,
            "cycle_state": cycle_features.cycle_state,
            "mainline_strength_score": round(cycle_features.mainline_strength_score, 2),
            "fade_watch": cycle_features.fade_watch,
            "fade_confirmed": cycle_features.fade_confirmed,
        })

        return enhanced_candidate

    async def _fetch_candidate_inputs(self, trade_date: date) -> List[asyncpg.Record]:
        """
        重写父类方法，去掉主线过滤条件
        允许支线题材进入弱转强候选池
        """
        pool = await self._ensure_pool()
        sql = """
        WITH stock_base AS (
            SELECT DISTINCT ON (split_part(s.stock_id, '.', 1), s.subject_key)
                split_part(s.stock_id, '.', 1) AS stock_code,
                s.stock_id,
                s.stock_name,
                s.subject_key,
                COALESCE(NULLIF(m.theme_name, ''), NULLIF(c.theme_name, ''), s.subject_key) AS theme_name,
                s.rank_order,
                s.pct_chg,
                s.limit_up,
                s.is_leader,
                c.primary_cycle_stage,
                c.action_bias,
                c.is_divergence,
                c.is_rebound,
                c.is_fermentation,
                c.is_fade,
                m.is_main_theme
            FROM subject_stock_daily_snapshot s
            LEFT JOIN theme_mainline_judgement m
              ON m.trade_date = s.trade_date
             AND m.subject_key = s.subject_key
            LEFT JOIN theme_cycle_judgement c
              ON c.trade_date = s.trade_date
             AND c.subject_key = s.subject_key
            WHERE s.trade_date = $1::date
            ORDER BY split_part(s.stock_id, '.', 1), s.subject_key, s.rank_order ASC
        )
        SELECT
            b.*,
            (
                SELECT COUNT(*)
                FROM subject_stock_daily_snapshot h
                WHERE split_part(h.stock_id, '.', 1) = b.stock_code
                  AND h.trade_date <= $1::date
                  AND h.trade_date > ($1::date - INTERVAL '30 days')
                  AND COALESCE(h.limit_up, FALSE) = TRUE
            ) AS recent_limit_up_count,
            (
                SELECT h.pct_chg
                FROM subject_stock_daily_snapshot h
                WHERE split_part(h.stock_id, '.', 1) = b.stock_code
                  AND h.trade_date < $1::date
                ORDER BY h.trade_date DESC
                LIMIT 1
            ) AS prev_day_pct_chg,
            (
                SELECT h.limit_up
                FROM subject_stock_daily_snapshot h
                WHERE split_part(h.stock_id, '.', 1) = b.stock_code
                  AND h.trade_date < $1::date
                ORDER BY h.trade_date DESC
                LIMIT 1
            ) AS prev_day_limit_up
        FROM stock_base b
        -- 去掉主线过滤条件：WHERE COALESCE(b.is_main_theme, FALSE) = TRUE
        -- 允许支线题材进入候选池，但保留其他筛选逻辑
        -- 按重要性排序：1. 排名靠前，2. 近期涨停次数多，3. 涨幅大（负值小）
        ORDER BY b.rank_order ASC NULLS LAST,
                 recent_limit_up_count DESC,
                 b.pct_chg ASC  -- 负值越小（跌幅越大）越重要
        LIMIT 100
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return rows

    async def build_enhanced(self,
                             trade_date: date,
                             *,
                             next_trade_date: Optional[date] = None,
                             max_formal: int = 80,
                             max_observe: int = 40) -> CandidateBuildResult:
        """
        增强版构建流程
        支持三级准入，分别控制正式和观察流数量
        """
        pool = await self._ensure_pool()
        next_day = next_trade_date or await self.resolve_next_trade_date(trade_date)

        # 获取基础候选输入
        rows = await self._fetch_candidate_inputs(trade_date)
        print(f"📊 获取到 {len(rows)} 行候选输入")

        formal_candidates: List[Dict[str, Any]] = []
        observe_candidates: List[Dict[str, Any]] = []
        rejected_count = 0

        for row in rows:
            subject_key = str(row.get("subject_key") or "")
            if not subject_key:
                continue

            # 调试：检查神剑股份
            stock_id = str(row.get("stock_id") or "")
            if "002361" in stock_id:
                print(f"🔍 处理神剑股份: stock_id={stock_id}, subject_key={subject_key}")

            # 获取周期特征
            cycle_features = await self.fetch_cycle_features(trade_date, subject_key)

            # 构建增强候选
            candidate = self._to_enhanced_candidate(row, trade_date, next_day, cycle_features)
            if "002361" in stock_id:
                if candidate is None:
                    print(f"❌ 神剑股份候选构建失败")
                else:
                    print(f"✅ 神剑股份候选构建成功: score={candidate.get('candidate_score')}, entry_type={candidate.get('pool_entry_type')}")
            if candidate is None:
                rejected_count += 1
                continue

            # 分类存储
            if "002361" in stock_id:
                print(f"🔍 神剑股份分类: candidate keys={list(candidate.keys())}")
                print(f"🔍 神剑股份分类: pool_entry_type value='{candidate.get('pool_entry_type')}', repr={repr(candidate.get('pool_entry_type'))}")
            entry_type = candidate.get("pool_entry_type", "reject")
            if "002361" in stock_id:
                print(f"🔍 神剑股份 entry_type: '{entry_type}'")
                print(f"🔍 神剑股份 entry_type == 'formal': {entry_type == 'formal'}")
            if entry_type == "formal":
                formal_candidates.append(candidate)
                if "002361" in stock_id:
                    print(f"🔍 神剑股份添加到formal列表")
            elif entry_type == "observe_only":
                observe_candidates.append(candidate)
                if "002361" in stock_id:
                    print(f"🔍 神剑股份添加到observe列表")
            else:
                rejected_count += 1
                if "002361" in stock_id:
                    print(f"🔍 神剑股份被拒绝")

        print(f"📊 分类结果: formal={len(formal_candidates)}, observe={len(observe_candidates)}, rejected={rejected_count}")
        # 分别排序
        formal_candidates.sort(key=lambda x: float(x["candidate_score"]), reverse=True)
        observe_candidates.sort(key=lambda x: float(x["candidate_score"]), reverse=True)

        # 截断
        formal_candidates = formal_candidates[:max_formal]
        observe_candidates = observe_candidates[:max_observe]

        # 合并（正式候选在前）
        all_candidates = formal_candidates + observe_candidates

        # 插入数据库
        inserted = await self._replace_enhanced_candidates(next_day, all_candidates)

        return CandidateBuildResult(
            trade_date=trade_date,
            next_trade_date=next_day,
            total_scanned=len(rows),
            total_inserted=inserted,
            candidates=all_candidates,
        )

    async def _replace_enhanced_candidates(self, next_trade_date: date,
                                          candidates: List[Dict[str, Any]]) -> int:
        """
        替换增强版候选记录
        包含新字段
        """
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO weak_to_strong_candidate_pool (
            trade_date, next_trade_date, stock_id, stock_name,
            subject_key, theme_name, candidate_score, candidate_type, rule_version,
            weak_type, weak_intensity, is_dragon_head, dragon_head_level,
            prev_limit_up_count, max_consecutive_limit_up_days,
            support_type, support_level, support_strength,
            expected_open_low, expected_open_high, expected_auction_pattern,
            need_last_minute_grab, need_plate_follow, evidence_json,
            pool_entry_type, cycle_state, mainline_strength_score,
            fade_watch, fade_confirmed, judgement_id, cycle_rule_version,
            created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21,
            $22, $23, $24::jsonb,
            $25, $26, $27, $28, $29, $30, $31,
            NOW()
        )
        ON CONFLICT (next_trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            candidate_score = EXCLUDED.candidate_score,
            candidate_type = EXCLUDED.candidate_type,
            rule_version = EXCLUDED.rule_version,
            weak_type = EXCLUDED.weak_type,
            weak_intensity = EXCLUDED.weak_intensity,
            is_dragon_head = EXCLUDED.is_dragon_head,
            dragon_head_level = EXCLUDED.dragon_head_level,
            prev_limit_up_count = EXCLUDED.prev_limit_up_count,
            max_consecutive_limit_up_days = EXCLUDED.max_consecutive_limit_up_days,
            support_type = EXCLUDED.support_type,
            support_level = EXCLUDED.support_level,
            support_strength = EXCLUDED.support_strength,
            expected_open_low = EXCLUDED.expected_open_low,
            expected_open_high = EXCLUDED.expected_open_high,
            expected_auction_pattern = EXCLUDED.expected_auction_pattern,
            need_last_minute_grab = EXCLUDED.need_last_minute_grab,
            need_plate_follow = EXCLUDED.need_plate_follow,
            evidence_json = EXCLUDED.evidence_json,
            pool_entry_type = EXCLUDED.pool_entry_type,
            cycle_state = EXCLUDED.cycle_state,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_watch = EXCLUDED.fade_watch,
            fade_confirmed = EXCLUDED.fade_confirmed,
            judgement_id = EXCLUDED.judgement_id,
            cycle_rule_version = EXCLUDED.cycle_rule_version
        """
        inserted = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 清空原有记录
                await conn.execute(
                    """
                    DELETE FROM weak_to_strong_candidate_pool
                    WHERE next_trade_date = $1::date
                    """,
                    next_trade_date,
                )
                # 插入新记录
                for c in candidates:
                    await conn.execute(
                        sql,
                        c["trade_date"],
                        c["next_trade_date"],
                        c["stock_id"],
                        c["stock_name"],
                        c["subject_key"],
                        c["theme_name"],
                        c["candidate_score"],
                        c["candidate_type"],
                        c.get("rule_version", self.ENHANCED_RULE_VERSION),
                        c["weak_type"],
                        c["weak_intensity"],
                        c["is_dragon_head"],
                        c["dragon_head_level"],
                        c["prev_limit_up_count"],
                        c["max_consecutive_limit_up_days"],
                        c["support_type"],
                        c["support_level"],
                        c["support_strength"],
                        c["expected_open_low"],
                        c["expected_open_high"],
                        c["expected_auction_pattern"],
                        c["need_last_minute_grab"],
                        c["need_plate_follow"],
                        c["evidence_json"],
                        c.get("pool_entry_type", "formal"),
                        c.get("cycle_state", ""),
                        c.get("mainline_strength_score", 0.0),
                        c.get("fade_watch", False),
                        c.get("fade_confirmed", False),
                        c.get("judgement_id"),  # 可能为空
                        c.get("cycle_rule_version", "theme_cycle_judgement.v2"),
                    )
                    inserted += 1
        return inserted

    # 兼容性方法
    async def build(self,
                   trade_date: date,
                   *,
                   next_trade_date: Optional[date] = None,
                   max_candidates: int = 120,
                   enhanced: bool = False) -> CandidateBuildResult:
        """
        兼容性构建方法
        enhanced=True时使用增强版，否则使用原版
        """
        if enhanced:
            # 增强版：分别控制正式和观察流数量
            max_formal = int(max_candidates * 0.7)  # 70%正式
            max_observe = max_candidates - max_formal  # 30%观察
            return await self.build_enhanced(trade_date,
                                            next_trade_date=next_trade_date,
                                            max_formal=max_formal,
                                            max_observe=max_observe)
        else:
            # 原版
            return await super().build(trade_date,
                                      next_trade_date=next_trade_date,
                                      max_candidates=max_candidates)
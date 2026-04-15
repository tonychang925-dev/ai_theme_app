from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.services.kline_data_service import KlineDataService


@dataclass
class CandidateBuildResult:
    trade_date: date
    next_trade_date: date
    total_scanned: int
    total_inserted: int
    candidates: List[Dict[str, Any]]


class WeakToStrongCandidateBuilder:
    """盘后弱转强候选池构建器（P1 MVP）"""

    RULE_VERSION = "weak_to_strong_candidate.v1"

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self.pool: Optional[asyncpg.Pool] = None
        # K线数据服务 - 用于支撑位分析
        self.kline_service = KlineDataService({
            "host": self.config.postgres_host,
            "port": self.config.postgres_port,
            "database": self.config.postgres_database,
            "user": self.config.postgres_user,
            "password": self.config.postgres_password
        })

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_database,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                min_size=1,
                max_size=3,
            )
        return self.pool

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
        if hasattr(self, 'kline_service') and self.kline_service:
            await self.kline_service.close()

    async def resolve_next_trade_date(self, trade_date: date) -> date:
        pool = await self._ensure_pool()
        sql = """
        SELECT MIN(trade_date) AS next_trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date > $1::date
        """
        async with pool.acquire() as conn:
            next_day = await conn.fetchval(sql, trade_date)
        # 本地环境常见只有历史截面；若没有下一个交易日，则回退为当日用于联调
        return next_day or trade_date

    async def build(
        self,
        trade_date: date,
        *,
        next_trade_date: Optional[date] = None,
        max_candidates: int = 120,
    ) -> CandidateBuildResult:
        pool = await self._ensure_pool()
        next_day = next_trade_date or await self.resolve_next_trade_date(trade_date)

        rows = await self._fetch_candidate_inputs(trade_date)
        candidates: List[Dict[str, Any]] = []
        for row in rows:
            candidate = self._to_candidate(row, trade_date, next_day)
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(key=lambda x: float(x["candidate_score"]), reverse=True)
        candidates = candidates[: max(max_candidates, 1)]
        inserted = await self._replace_candidates(next_day, candidates)

        return CandidateBuildResult(
            trade_date=trade_date,
            next_trade_date=next_day,
            total_scanned=len(rows),
            total_inserted=inserted,
            candidates=candidates,
        )

    async def build_with_strict_support(
        self,
        trade_date: date,
        *,
        next_trade_date: Optional[date] = None,
        max_candidates: int = 120,
    ) -> CandidateBuildResult:
        """
        使用严格支撑位分析的候选池构建器
        """
        pool = await self._ensure_pool()
        next_day = next_trade_date or await self.resolve_next_trade_date(trade_date)

        rows = await self._fetch_candidate_inputs(trade_date)
        candidates: List[Dict[str, Any]] = []

        print(f"使用严格支撑位分析构建候选池 - {trade_date}")
        print(f"扫描 {len(rows)} 只股票...")

        for i, row in enumerate(rows):
            if i % 100 == 0:
                print(f"  进度: {i+1}/{len(rows)}")

            candidate = await self._async_to_candidate(row, trade_date, next_day)
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(key=lambda x: float(x["candidate_score"]), reverse=True)
        candidates = candidates[: max(max_candidates, 1)]
        inserted = await self._replace_candidates(next_day, candidates)

        print(f"构建完成: 扫描 {len(rows)} 只，选中 {len(candidates)} 只，插入 {inserted} 条")

        return CandidateBuildResult(
            trade_date=trade_date,
            next_trade_date=next_day,
            total_scanned=len(rows),
            total_inserted=inserted,
            candidates=candidates,
        )

    async def _fetch_candidate_inputs(self, trade_date: date) -> List[asyncpg.Record]:
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
        -- 移除对is_main_theme的过滤，因为弱转强股票不一定必须是主线主题
        -- 关键判断是题材未全面退潮，而不是必须是主线主题
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return rows

    def _to_candidate(self, row: asyncpg.Record, trade_date: date, next_trade_date: date) -> Optional[Dict[str, Any]]:
        pct_chg = float(row.get("pct_chg") or 0.0)
        is_leader = bool(row.get("is_leader") or False)
        limit_up = bool(row.get("limit_up") or False)
        rank_order = int(row.get("rank_order") or 999)
        recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
        prev_day_pct = float(row.get("prev_day_pct_chg") or 0.0)
        prev_day_limit_up = bool(row.get("prev_day_limit_up") or False)

        stage = str(row.get("primary_cycle_stage") or "").lower()
        action_bias = str(row.get("action_bias") or "")
        is_divergence = bool(row.get("is_divergence") or False)
        is_rebound = bool(row.get("is_rebound") or False)
        is_fermentation = bool(row.get("is_fermentation") or False)
        is_fade = bool(row.get("is_fade") or False)

        # 弱转强核心条件检查：当日弱<-2.0%、前日弱<-1.5%
        # 这个检查必须在其他硬门槛之前，确保只有真正的弱势股进入候选
        if pct_chg >= -2.0 or prev_day_pct >= -1.5:
            return None

        # 硬门槛1：强势背景
        strong_background = (
            is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3
        )
        if not strong_background:
            return None

        # 硬门槛2：分歧修复窗口
        # 根据《弱转强买法》，弱转强更适合发生在'分歧-修复'阶段
        # 即使is_fade=True，如果其他条件满足，仍然认为有修复窗口
        # 因为is_fade判断需要有硬证据支持，而数据库中的标记可能不够准确
        repair_window = (
            ("弱转强" in action_bias)
            or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"}
            or is_divergence
            or is_rebound
            or is_fermentation
            # 新增：如果有强势背景（近期有多次涨停）且当前弱势，认为有修复窗口
            or (recent_limit_up_count >= 2 and pct_chg < 0)
        )
        # 注释掉is_fade对repair_window的强制否定
        # 因为根据用户要求，退潮判断必须有硬证据，没有硬证据不能判断退潮
        # if is_fade:
        #    repair_window = False
        if not repair_window:
            return None

        weak_type, weak_intensity = self._classify_weak_type(pct_chg, prev_day_pct, prev_day_limit_up)
        candidate_type = self._classify_candidate_type(
            is_leader=is_leader,
            recent_limit_up_count=recent_limit_up_count,
            weak_type=weak_type,
            rank_order=rank_order,
        )
        expected_open_low, expected_open_high = self._expected_open_range(candidate_type)
        expected_pattern = self._expected_pattern(candidate_type)

        support_type = self._support_type_from_row(pct_chg, prev_day_pct)
        support_strength = self._support_strength(pct_chg, prev_day_pct, support_type)
        # 硬门槛：必须有有效支撑位（强度≥30）
        if support_strength < 30.0:
            return None
        support_level = 0.0

        score = self._candidate_score(
            is_leader=is_leader,
            limit_up=limit_up,
            recent_limit_up_count=recent_limit_up_count,
            rank_order=rank_order,
            stage=stage,
            weak_intensity=weak_intensity,
            support_strength=support_strength,
        )

        stock_id = self._normalize_stock_id(str(row.get("stock_id") or ""), str(row.get("stock_code") or ""))
        if not stock_id:
            return None

        evidence = {
            "schema_version": "evidence_schema.v1",
            "trace": {
                "trade_date": trade_date.isoformat(),
                "stock_id": stock_id,
                "candidate_id": "",
                "source_snapshot_id": f"candidate_{trade_date.isoformat()}_{stock_id}",
            },
            "inputs": {
                "candidate_type": candidate_type,
                "rule_version": self.RULE_VERSION,
                "weak_type": weak_type,
                "support_type": support_type,
                "expected_auction_pattern": expected_pattern,
            },
            "scores": {
                "price_strength": 0.0,
                "pattern_stability": 0.0,
                "last_minute_grab": 0.0,
                "plate_follow": 0.0,
                "risk_penalty": 0.0,
                "confirmation_score": 0.0,
                "breakdown": {
                    "candidate_score": score,
                    "repair_window": repair_window,
                    "strong_background": strong_background,
                },
            },
            "rules": {
                "hard_rule_results": [
                    {"rule": "strong_background", "passed": strong_background, "reason": ""},
                    {"rule": "repair_window", "passed": repair_window, "reason": ""},
                ],
                "mapping_warnings": [],
            },
            "decision": {
                "signal_level": "X",
                "decision": "candidate_only",
                "data_status": "missing",
                "data_latency_ms": 0,
            },
        }

        return {
            "trade_date": trade_date,
            "next_trade_date": next_trade_date,
            "stock_id": stock_id,
            "stock_name": str(row.get("stock_name") or stock_id),
            "subject_key": str(row.get("subject_key") or ""),
            "theme_name": str(row.get("theme_name") or row.get("subject_key") or ""),
            "candidate_score": round(score, 2),
            "candidate_type": candidate_type,
            "rule_version": self.RULE_VERSION,
            "weak_type": weak_type,
            "weak_intensity": round(weak_intensity, 2),
            "is_dragon_head": bool(is_leader and recent_limit_up_count >= 3),
            "dragon_head_level": "absolute" if (is_leader and recent_limit_up_count >= 3) else ("relative" if is_leader else "sector"),
            "prev_limit_up_count": recent_limit_up_count,
            "max_consecutive_limit_up_days": 0,
            "support_type": support_type,
            "support_level": support_level,
            "support_strength": round(support_strength, 2),
            "expected_open_low": expected_open_low,
            "expected_open_high": expected_open_high,
            "expected_auction_pattern": expected_pattern,
            "need_last_minute_grab": True,
            "need_plate_follow": True,
            "evidence_json": json.dumps(evidence, ensure_ascii=False),
        }

    async def _async_to_candidate(self, row: asyncpg.Record, trade_date: date, next_trade_date: date) -> Optional[Dict[str, Any]]:
        """
        异步版本的候选构建器，包含严格的支撑位分析
        """
        # 提取基本数据
        pct_chg = float(row.get("pct_chg") or 0.0)
        is_leader = bool(row.get("is_leader") or False)
        limit_up = bool(row.get("limit_up") or False)
        rank_order = int(row.get("rank_order") or 999)
        recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
        prev_day_pct = float(row.get("prev_day_pct_chg") or 0.0)
        prev_day_limit_up = bool(row.get("prev_day_limit_up") or False)

        stage = str(row.get("primary_cycle_stage") or "").lower()
        action_bias = str(row.get("action_bias") or "")
        is_divergence = bool(row.get("is_divergence") or False)
        is_rebound = bool(row.get("is_rebound") or False)
        is_fermentation = bool(row.get("is_fermentation") or False)
        is_fade = bool(row.get("is_fade") or False)

        # 硬门槛1：强势背景
        strong_background = (
            is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3
        )
        if not strong_background:
            return None

        # 硬门槛2：分歧修复窗口
        # 根据《弱转强买法》，弱转强更适合发生在'分歧-修复'阶段
        # 即使is_fade=True，如果其他条件满足，仍然认为有修复窗口
        # 因为is_fade判断需要有硬证据支持，而数据库中的标记可能不够准确
        repair_window = (
            ("弱转强" in action_bias)
            or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"}
            or is_divergence
            or is_rebound
            or is_fermentation
            # 新增：如果有强势背景（近期有多次涨停）且当前弱势，认为有修复窗口
            or (recent_limit_up_count >= 2 and pct_chg < 0)
        )
        # 注释掉is_fade对repair_window的强制否定
        # 因为根据用户要求，退潮判断必须有硬证据，没有硬证据不能判断退潮
        # if is_fade:
        #    repair_window = False
        if not repair_window:
            return None

        # 弱转强核心条件：当日弱<-2.0%，前日弱<-1.5%
        # 根据用户要求，弱转强必须满足这两个条件
        if pct_chg >= -2.0 or prev_day_pct >= -1.5:
            return None

        # 分类弱势类型
        weak_type, weak_intensity = self._classify_weak_type(pct_chg, prev_day_pct, prev_day_limit_up)
        candidate_type = self._classify_candidate_type(
            is_leader=is_leader,
            recent_limit_up_count=recent_limit_up_count,
            weak_type=weak_type,
            rank_order=rank_order,
        )
        expected_open_low, expected_open_high = self._expected_open_range(candidate_type)
        expected_pattern = self._expected_pattern(candidate_type)

        # 严格支撑位分析 - 异步
        stock_id = self._normalize_stock_id(str(row.get("stock_id") or ""), str(row.get("stock_code") or ""))
        if not stock_id:
            return None

        support_analysis = await self.analyze_strict_support(stock_id, pct_chg, trade_date)

        # 检查是否有有效支撑位
        has_support = support_analysis.get('has_support', False)
        support_type = support_analysis.get('support_type', '')
        support_strength_raw = support_analysis.get('support_strength', 0.0)  # 0.0-1.0范围
        support_level = support_analysis.get('support_level', 0.0)
        is_gap_support = support_analysis.get('is_gap_support', False)
        # 新增字段：支撑类型数量和详细支撑类型
        support_count = support_analysis.get('support_count', 0)
        support_types = support_analysis.get('support_types', [])
        primary_type = support_analysis.get('primary_type', '')
        combined_strength = support_analysis.get('combined_strength', 0.0)

        # 如果KlineDataService没有检测到支撑位，使用简单的支撑位检测作为回退
        using_fallback = False
        if not has_support:
            # 使用简单的支撑位检测作为回退
            support_type = self._support_type_from_row(pct_chg, prev_day_pct)
            support_strength_raw = self._support_strength(pct_chg, prev_day_pct, support_type)
            support_strength = support_strength_raw  # 注意：简单方法返回的是0-100范围
            support_level = 0.0  # 简单方法不提供支撑位水平
            has_support = support_strength >= 30.0  # 如果强度≥30，则认为有支撑位
            using_fallback = True

            # 设置回退情况下的支撑类型信息
            support_count = 1 if support_type != "none" else 0
            support_types = [{"type": support_type, "strength": support_strength/100.0, "level": support_level}] if support_type != "none" else []
            primary_type = support_type
            combined_strength = support_strength / 100.0  # 转换为0.0-1.0范围

            if not has_support:
                return None
        else:
            # 将支撑强度从0.0-1.0范围转换为0-100范围（兼容现有代码）
            support_strength = support_strength_raw * 100.0

            # 硬门槛：必须有有效支撑位（强度≥30）
            if support_strength < 30.0:
                # 尝试使用回退
                support_type_fallback = self._support_type_from_row(pct_chg, prev_day_pct)
                support_strength_fallback = self._support_strength(pct_chg, prev_day_pct, support_type_fallback)
                if support_strength_fallback >= 30.0:
                    support_type = support_type_fallback
                    support_strength = support_strength_fallback
                    support_level = 0.0
                    using_fallback = True
                    # 设置回退情况下的支撑类型信息
                    support_count = 1 if support_type != "none" else 0
                    support_types = [{"type": support_type, "strength": support_strength/100.0, "level": support_level}] if support_type != "none" else []
                    primary_type = support_type
                    combined_strength = support_strength / 100.0  # 转换为0.0-1.0范围
                else:
                    return None

        # 计算候选分数
        score = self._candidate_score(
            is_leader=is_leader,
            limit_up=limit_up,
            recent_limit_up_count=recent_limit_up_count,
            rank_order=rank_order,
            stage=stage,
            weak_intensity=weak_intensity,
            support_strength=support_strength,
        )

        # 构建证据
        evidence = {
            "schema_version": "evidence_schema.v1",
            "trace": {
                "trade_date": trade_date.isoformat(),
                "stock_id": stock_id,
                "candidate_id": "",
                "source_snapshot_id": f"candidate_{trade_date.isoformat()}_{stock_id}",
            },
            "inputs": {
                "candidate_type": candidate_type,
                "rule_version": self.RULE_VERSION,
                "weak_type": weak_type,
                "support_type": support_type,
                "support_count": support_count,
                "support_types": [st.get('type', '') for st in support_types],
                "primary_support_type": primary_type,
                "combined_strength": combined_strength,
                "expected_auction_pattern": expected_pattern,
            },
            "scores": {
                "price_strength": 0.0,
                "pattern_stability": 0.0,
                "last_minute_grab": 0.0,
                "plate_follow": 0.0,
                "risk_penalty": 0.0,
                "confirmation_score": 0.0,
                "breakdown": {
                    "candidate_score": score,
                    "repair_window": repair_window,
                    "strong_background": strong_background,
                },
            },
            "rules": {
                "hard_rule_results": [
                    {"rule": "strong_background", "passed": strong_background, "reason": ""},
                    {"rule": "repair_window", "passed": repair_window, "reason": ""},
                ],
                "mapping_warnings": [],
            },
            "decision": {
                "signal_level": "X",
                "decision": "candidate_only",
                "data_status": "missing",
                "data_latency_ms": 0,
            },
        }

        return {
            "trade_date": trade_date,
            "next_trade_date": next_trade_date,
            "stock_id": stock_id,
            "stock_name": str(row.get("stock_name") or stock_id),
            "subject_key": str(row.get("subject_key") or ""),
            "theme_name": str(row.get("theme_name") or row.get("subject_key") or ""),
            "candidate_score": round(score, 2),
            "candidate_type": candidate_type,
            "rule_version": self.RULE_VERSION,
            "weak_type": weak_type,
            "weak_intensity": round(weak_intensity, 2),
            "is_dragon_head": bool(is_leader and recent_limit_up_count >= 3),
            "dragon_head_level": "absolute" if (is_leader and recent_limit_up_count >= 3) else ("relative" if is_leader else "sector"),
            "prev_limit_up_count": recent_limit_up_count,
            "max_consecutive_limit_up_days": 0,
            "support_type": support_type,
            "support_level": support_level,
            "support_strength": round(support_strength, 2),
            "expected_open_low": expected_open_low,
            "expected_open_high": expected_open_high,
            "expected_auction_pattern": expected_pattern,
            "need_last_minute_grab": True,
            "need_plate_follow": True,
            "evidence_json": json.dumps(evidence, ensure_ascii=False),
        }

    def _classify_weak_type(self, pct_chg: float, prev_day_pct: float, prev_day_limit_up: bool) -> Tuple[str, float]:
        if prev_day_limit_up and pct_chg < 0:
            return "bad_limit_up", min(100.0, abs(pct_chg) * 12.0 + 20.0)
        if pct_chg <= -5.0:
            return "big_negative_line", min(100.0, abs(pct_chg) * 10.0)
        if -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
            return "upper_shadow", 55.0
        if pct_chg <= -1.0:
            return "high_open_low_close", min(100.0, abs(pct_chg) * 8.0 + 10.0)
        return "fake_break", 40.0

    def _classify_candidate_type(
        self,
        *,
        is_leader: bool,
        recent_limit_up_count: int,
        weak_type: str,
        rank_order: int,
    ) -> str:
        # 冲突优先级（高 -> 低）：
        # dragon_repair > subdragon_repair > bad_limit_repair > upper_shadow_repair > strong_trend_repair > generic_repair
        if is_leader and recent_limit_up_count >= 3:
            return "dragon_repair"
        if is_leader or rank_order <= 3:
            return "subdragon_repair"
        if weak_type == "bad_limit_up":
            return "bad_limit_repair"
        if weak_type == "upper_shadow":
            return "upper_shadow_repair"
        if recent_limit_up_count >= 1:
            return "strong_trend_repair"
        return "generic_repair"

    def _expected_open_range(self, candidate_type: str) -> Tuple[float, float]:
        if candidate_type == "dragon_repair":
            return (0.0, 4.0)
        if candidate_type == "subdragon_repair":
            return (0.5, 4.5)
        if candidate_type == "bad_limit_repair":
            return (1.0, 5.0)
        if candidate_type == "upper_shadow_repair":
            return (0.0, 3.0)
        if candidate_type == "strong_trend_repair":
            return (0.5, 4.0)
        return (0.0, 3.0)

    def _expected_pattern(self, candidate_type: str) -> str:
        if candidate_type in {"dragon_repair", "subdragon_repair"}:
            return "tail_lift_or_stair_up"
        if candidate_type == "bad_limit_repair":
            return "u_recover_then_lift"
        if candidate_type == "upper_shadow_repair":
            return "stable_red_with_tail_lift"
        return "stable_red"

    async def analyze_strict_support(self, stock_id: str, pct_chg: float, trade_date: date) -> Dict[str, Any]:
        """
        增强支撑位分析 - 使用KlineDataService进行完整的支撑位检测，支持多种支撑类型组合

        返回: {
            'has_support': bool,
            'support_type': str,  # 主要支撑类型: gap, previous_low, previous_close, integer_level
            'support_strength': float,  # 0.0-1.0 (组合支撑强度)
            'support_level': float,
            'is_gap_support': bool,
            'support_types': List[Dict],  # 所有检测到的支撑类型
            'support_count': int,  # 支撑类型数量
            'combined_strength': float,  # 组合支撑强度(0.0-1.0)
            'primary_type': str  # 主要支撑类型
        }
        """
        try:
            # 使用KlineDataService分析支撑位
            # 清理股票ID：KlineDataService期望不带后缀的6位代码
            raw_stock_id = stock_id.split('.')[0] if '.' in stock_id else stock_id
            gap_analysis = await self.kline_service.analyze_gap_support(raw_stock_id, trade_date)

            # 收集所有可能的支撑类型
            support_types = []

            # 1. 检查缺口支撑
            if gap_analysis.get('has_support', False):
                support_type = gap_analysis.get('support_type', '')
                support_strength = gap_analysis.get('support_strength', 0.0)
                support_level = gap_analysis.get('support_level', 0.0)
                is_gap_support = gap_analysis.get('is_gap_support', False)

                # 添加主要支撑类型
                support_types.append({
                    'type': support_type,
                    'strength': support_strength,
                    'level': support_level,
                    'is_gap_support': is_gap_support,
                    'description': self._get_support_description(support_type, support_level)
                })

                # 如果缺口支撑存在，检查是否还有其他隐含支撑
                # 例如：缺口支撑通常也意味着前一日低点支撑
                if support_type == 'gap_support' and support_level > 0:
                    # 添加前一日低点支撑（强度较低）
                    support_types.append({
                        'type': 'previous_low',
                        'strength': min(0.6, support_strength * 0.75),  # 前一日低点强度约为缺口支撑的75%
                        'level': support_level,  # 缺口下沿通常也是前一日高点
                        'is_gap_support': False,
                        'description': '前一日高点/低点支撑'
                    })

            # 2. 检查前一日低点支撑（简单方法）
            # 获取K线数据以检测前一日低点（增加天数以确保获取前一日数据）
            kline_data = await self.kline_service.get_kline_data(raw_stock_id, trade_date, days_before=5, days_after=0)
            if len(kline_data) >= 2:
                # 找到目标日期和前一日
                target_kline = None
                prev_kline = None

                for kline in kline_data:
                    if kline['trade_date'] == trade_date:
                        target_kline = kline
                    elif target_kline is None and kline['trade_date'] < trade_date:
                        prev_kline = kline

                if target_kline and prev_kline:
                    current_low = target_kline.get('low_price', 0)
                    prev_low = prev_kline.get('low_price', 0)

                    # 检查是否在前一日低点附近获得支撑
                    if prev_low > 0 and current_low > 0:
                        distance_pct = abs(current_low - prev_low) / prev_low * 100
                        if distance_pct < 7.0:  # 放宽到7%以内认为是支撑（A股波动较大）
                            # 检查是否已存在相同类型的支撑
                            existing_prev_low = any(st['type'] == 'previous_low' for st in support_types)
                            if not existing_prev_low:
                                support_types.append({
                                    'type': 'previous_low',
                                    'strength': 0.6,
                                    'level': prev_low,
                                    'is_gap_support': False,
                                    'description': f'前一日低点支撑 {prev_low:.2f}（距离{distance_pct:.1f}%）'
                                })

                    # 3. 检查整数关口支撑
                    if current_low > 0:
                        # 检查关键整数位
                        integer_levels = [1.00, 2.00, 5.00, 10.00, 20.00, 50.00]
                        for base in integer_levels:
                            for multiplier in [0.5, 1.0, 1.5, 2.0]:
                                level = base * multiplier
                                if abs(current_low - level) / level < 0.02:  # 2%以内
                                    # 检查是否已存在相同类型的支撑
                                    existing_integer = any(st['type'] == 'integer_level' for st in support_types)
                                    if not existing_integer:
                                        support_types.append({
                                            'type': 'integer_level',
                                            'strength': 0.4,
                                            'level': level,
                                            'is_gap_support': False,
                                            'description': f'整数关口支撑 {level:.2f}'
                                        })
                                    break  # 只取第一个匹配的整数位

            # 计算组合支撑强度
            has_support = len(support_types) > 0
            combined_strength = 0.0
            primary_type = ''
            support_level = 0.0
            is_gap_support = False

            if has_support:
                # 按支撑强度排序
                support_types.sort(key=lambda x: x['strength'], reverse=True)

                # 主要支撑类型是强度最高的
                primary_support = support_types[0]
                primary_type = primary_support['type']
                support_level = primary_support['level']
                is_gap_support = primary_support.get('is_gap_support', False)

                # 计算组合支撑强度
                max_strength = primary_support['strength']
                support_count = len(support_types)

                # 多种支撑存在时增加强度加成
                # 每多一种支撑类型增加5%强度，最多增加20%
                strength_bonus = min(0.2, (support_count - 1) * 0.05)
                combined_strength = min(1.0, max_strength + strength_bonus)

            # 构建返回结果（保持向后兼容）
            result = {
                'has_support': has_support,
                'support_type': primary_type,  # 主要支撑类型
                'support_strength': combined_strength,  # 组合支撑强度
                'support_level': support_level,
                'is_gap_support': is_gap_support,
                # 新增字段
                'support_types': support_types,
                'support_count': len(support_types),
                'combined_strength': combined_strength,
                'primary_type': primary_type
            }

            return result

        except Exception as e:
            # 如果分析失败，回退到简单支撑检测
            print(f"支撑位分析失败 {stock_id} {trade_date}: {e}")
            # 返回空结果
            return {
                'has_support': False,
                'support_type': '',
                'support_strength': 0.0,
                'support_level': 0.0,
                'is_gap_support': False,
                'support_types': [],
                'support_count': 0,
                'combined_strength': 0.0,
                'primary_type': ''
            }

    def _get_support_description(self, support_type: str, level: float) -> str:
        """获取支撑类型的描述"""
        descriptions = {
            'gap_support': f'缺口支撑 {level:.2f}',
            'previous_low': f'前一日低点支撑 {level:.2f}',
            'previous_close': f'前一日收盘价支撑 {level:.2f}',
            'integer_level': f'整数关口支撑 {level:.2f}',
            'ma5': '5日均线支撑',
            'break_recover': '突破回踩支撑',
            'none': '无明确支撑'
        }
        return descriptions.get(support_type, f'{support_type}支撑 {level:.2f}')

    def _support_type_from_row(self, pct_chg: float, prev_day_pct: float) -> str:
        if prev_day_pct <= -4.0 and pct_chg > -2.0:
            return "previous_low"
        if -1.5 <= pct_chg <= 1.5:
            return "ma5"
        if pct_chg > 1.5:
            return "break_recover"
        return "none"

    def _support_strength(self, pct_chg: float, prev_day_pct: float, support_type: str) -> float:
        base = 20.0 if support_type == "none" else 45.0
        if prev_day_pct <= -4.0:
            base += 15.0
        if -1.5 <= pct_chg <= 2.5:
            base += 10.0
        return min(base, 95.0)

    def _candidate_score(
        self,
        *,
        is_leader: bool,
        limit_up: bool,
        recent_limit_up_count: int,
        rank_order: int,
        stage: str,
        weak_intensity: float,
        support_strength: float,
    ) -> float:
        score = 45.0
        if is_leader:
            score += 18.0
        if limit_up:
            score += 10.0
        score += min(recent_limit_up_count * 4.0, 12.0)
        if rank_order <= 3:
            score += 8.0
        if stage in {"rebound", "fermentation", "回流", "发酵", "启动"}:
            score += 8.0
        score += min(weak_intensity * 0.08, 8.0)
        score += min(support_strength * 0.1, 9.0)
        return max(0.0, min(score, 100.0))

    def _normalize_stock_id(self, raw_stock_id: str, stock_code: str) -> str:
        raw = (raw_stock_id or "").strip()
        if "." in raw and len(raw.split(".")[0]) == 6:
            return raw.upper()
        code = (stock_code or "").strip()
        if len(code) != 6 or not code.isdigit():
            return ""
        if code.startswith(("60", "68")):
            suffix = "SH"
        elif code.startswith(("00", "30")):
            suffix = "SZ"
        elif code.startswith(("43", "83", "87")):
            suffix = "BJ"
        else:
            suffix = "SZ"
        return f"{code}.{suffix}"

    async def _replace_candidates(self, next_trade_date: date, candidates: List[Dict[str, Any]]) -> int:
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO weak_to_strong_candidate_pool (
            trade_date, next_trade_date, stock_id, stock_name,
            subject_key, theme_name, candidate_score, candidate_type, rule_version,
            weak_type, weak_intensity, is_dragon_head, dragon_head_level,
            prev_limit_up_count, max_consecutive_limit_up_days,
            support_type, support_level, support_strength,
            expected_open_low, expected_open_high, expected_auction_pattern,
            need_last_minute_grab, need_plate_follow, evidence_json, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21,
            $22, $23, $24::jsonb, NOW()
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
            evidence_json = EXCLUDED.evidence_json
        """
        inserted = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM weak_to_strong_candidate_pool
                    WHERE next_trade_date = $1::date
                    """,
                    next_trade_date,
                )
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
                        c["rule_version"],
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
                    )
                    inserted += 1
        return inserted

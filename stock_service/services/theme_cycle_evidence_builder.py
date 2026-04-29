from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.services.unified_cycle_scoring_service import CycleEvidenceInput


@dataclass
class ThemeCycleEvidence:
    trade_date: date
    subject_key: str
    theme_name: str
    mainline_strength_score: float
    fade_risk_score: float
    event_evidence_refs: List[Dict[str, Any]]
    leader_evidence_refs: List[Dict[str, Any]]
    board_structure_refs: List[Dict[str, Any]]
    theme_kline_refs: List[Dict[str, Any]]
    evidence_json: Dict[str, Any]


class ThemeCycleEvidenceBuilder:
    """主题周期证据构建器

    从现有数据表构建四层证据，存入 theme_cycle_evidence_daily 表
    严格按照用户骨架设计：只构建证据，不做最终判决
    """

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self._pool: Optional[asyncpg.Pool] = None
        self._evidence_refs: Dict[str, List[Dict[str, Any]]] = {}
        self._layer_payload: Dict[str, Any] = {}

    async def _ensure_pool(self) -> asyncpg.Pool:
        """确保数据库连接池存在"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                database=self.config.postgres_database,
                min_size=1,
                max_size=5
            )
        return self._pool

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None

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

    async def _check_column_exists(self, conn: asyncpg.Connection, table_name: str, column_name: str) -> bool:
        sql = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = $1
              AND column_name = $2
        )
        """
        return bool(await conn.fetchval(sql, table_name, column_name))

    async def build_evidence_for_date(self, trade_date: date) -> List[CycleEvidenceInput]:
        """为指定交易日构建所有主题的周期证据

        返回构建的 CycleEvidenceInput 列表，同时将证据保存到数据库
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # 1. 检查证据表是否存在，如果不存在则创建（使用迁移脚本）
            evidence_table_exists = await self._check_table_exists(conn, "theme_cycle_evidence_daily")
            if not evidence_table_exists:
                print(f"⚠️ 证据表 theme_cycle_evidence_daily 不存在，需要运行迁移脚本")
                # 这里可以调用迁移脚本，暂时跳过
                return []

            # 2. 获取所有需要处理的主题（统一来源：subject_stock_daily_snapshot）
            subjects = await self._fetch_subjects_for_date(conn, trade_date)
            if not subjects:
                print(f"⚠️ 交易日 {trade_date} 无主题数据")
                return []

            # 3. 为每个主题构建证据
            evidence_inputs = []
            failure_reason_counts: dict[str, int] = defaultdict(int)
            failure_samples: list[dict[str, Any]] = []
            for subject in subjects:
                subject_key = subject["subject_key"]
                theme_name = subject["theme_name"]

                try:
                    evidence = await self._build_evidence_for_subject(
                        conn, trade_date, subject_key, theme_name
                    )
                    if evidence:
                        evidence_inputs.append(evidence)
                        # 保存到数据库
                        await self._save_evidence_to_db(conn, evidence)
                        print(f"✅ 主题 {subject_key} ({theme_name}) 证据构建完成")
                except Exception as e:
                    reason = self._classify_evidence_failure_reason(str(e))
                    failure_reason_counts[reason] += 1
                    if len(failure_samples) < 20:
                        failure_samples.append(
                            {
                                "subject_key": subject_key,
                                "theme_name": theme_name,
                                "reason": reason,
                                "error": str(e),
                            }
                        )
                    print(f"❌ 主题 {subject_key} 证据构建失败[{reason}]: {e}")
                    continue

            print(f"📊 总计构建 {len(evidence_inputs)} 个主题的周期证据")
            if failure_reason_counts:
                total = len(subjects)
                failed = sum(failure_reason_counts.values())
                success_rate = (len(evidence_inputs) / total) if total else 1.0
                print(
                    f"⚠️ 周期证据构建失败统计: input={total}, success={len(evidence_inputs)}, "
                    f"failed={failed}, success_rate={success_rate:.3f}, reasons={dict(failure_reason_counts)}"
                )
                print(
                    "⚠️ 周期证据构建失败样本: "
                    + json.dumps(failure_samples, ensure_ascii=False)
                )
                self._write_evidence_diag_report(
                    trade_date=trade_date,
                    total=total,
                    success=len(evidence_inputs),
                    failed=failed,
                    failure_reason_counts=dict(failure_reason_counts),
                    failure_samples=failure_samples,
                )
                self._enforce_evidence_gates(total=total, success=len(evidence_inputs), failed=failed)
            return evidence_inputs

    async def build(self, trade_date: date, subject_key: str, theme_name: str) -> ThemeCycleEvidence:
        """按单主题构建四层证据并落库，返回统一证据对象。"""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            evidence = await self._build_evidence_for_subject(conn, trade_date, subject_key, theme_name)
            if evidence is None:
                raise ValueError(f"无法构建周期证据: trade_date={trade_date} subject_key={subject_key}")
            await self._save_evidence_to_db(conn, evidence)

            mainline_strength_score = self._calc_mainline_strength_score(evidence)
            fade_risk_score = self._calc_fade_risk_score(evidence)
            payload = self._to_theme_cycle_evidence_payload(
                evidence=evidence,
                mainline_strength_score=mainline_strength_score,
                fade_risk_score=fade_risk_score,
            )
            return payload

    async def _fetch_subjects_for_date(self, conn: asyncpg.Connection,
                                      trade_date: date) -> List[Dict[str, Any]]:
        """获取指定交易日需要处理的所有主题"""
        sql = """
        SELECT
            subject_key,
            subject_key AS theme_name
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1
          AND COALESCE(subject_key, '') <> ''
        GROUP BY subject_key
        ORDER BY subject_key
        """
        rows = await conn.fetch(sql, trade_date)
        return [dict(row) for row in rows]

    async def _build_evidence_for_subject(self, conn: asyncpg.Connection,
                                         trade_date: date,
                                         subject_key: str,
                                         theme_name: str) -> Optional[CycleEvidenceInput]:
        """为单个主题构建周期证据"""
        # 重置证据引用记录
        self._evidence_refs = {}

        # 1. 收集事件层证据
        event_data = await self._fetch_event_layer_evidence(conn, trade_date, subject_key)

        # 2. 收集龙头层证据
        leader_data = await self._fetch_leader_layer_evidence(conn, trade_date, subject_key)

        # 3. 收集板块结构层证据
        board_data = await self._fetch_board_structure_evidence(conn, trade_date, subject_key)

        # 4. 收集K线技术层证据
        kline_data = await self._fetch_kline_evidence(conn, trade_date, subject_key)

        # 5. 获取前一日状态（用于状态转换）
        previous_state = await self._fetch_previous_cycle_state(conn, trade_date, subject_key)

        # 6. 构建 CycleEvidenceInput
        evidence = CycleEvidenceInput(
            trade_date=trade_date.isoformat(),
            subject_key=subject_key,
            theme_name=theme_name,

            # 事件层
            event_strength_score=float(event_data.get("event_strength_score", 0)),
            event_continuity_score=float(event_data.get("event_continuity_score", 0)),
            strong_event_count_7d=int(event_data.get("strong_event_count_7d") or 0),
            event_recency_days=event_data.get("event_recency_days"),

            # 龙头/接力层
            leader_alive_score=float(leader_data.get("leader_alive_score", 0)),
            leader_breakdown_flag=bool(leader_data.get("leader_breakdown_flag", False)),
            relay_strength_score=float(leader_data.get("relay_strength_score", 0)),
            front_row_survival_ratio=float(leader_data.get("front_row_survival_ratio", 0)),

            # 板块结构层
            limit_up_count=int(board_data.get("limit_up_count") or 0),
            limit_down_count=int(board_data.get("limit_down_count") or 0),
            red_ratio=float(board_data.get("red_ratio", 0)),
            big_drop_ratio=float(board_data.get("big_drop_ratio", 0)),
            front_row_strength_score=float(board_data.get("front_row_strength_score", 0)),

            # 板块K线技术层
            theme_support_score=float(kline_data.get("theme_support_score", 0)),
            break_start_pivot=bool(kline_data.get("break_start_pivot", False)),

            # 前一日状态
            previous_cycle_state=previous_state
        )

        self._layer_payload = {
            "event": event_data,
            "leader": leader_data,
            "board": board_data,
            "kline": kline_data,
            "window": {
                "lookback_days": 7,
                "evidence_window_start": (trade_date - timedelta(days=7)),
                "evidence_window_end": trade_date,
            },
        }

        return evidence

    async def _fetch_event_layer_evidence(self, conn: asyncpg.Connection,
                                         trade_date: date,
                                         subject_key: str) -> Dict[str, Any]:
        """获取事件层证据"""
        history_sql = """
        SELECT
            rank_date,
            COALESCE(heat, 0) AS heat,
            COALESCE(pct_chg, 0) AS pct_chg,
            COALESCE(heat_name, '') AS heat_name
        FROM theme_history_event
        WHERE subject_key = $1
          AND rank_date <= $2::date
          AND rank_date >= ($2::date - INTERVAL '7 days')
        ORDER BY rank_date DESC
        """
        history_rows = await conn.fetch(history_sql, subject_key, trade_date)
        if history_rows:
            event_count_7d = len(history_rows)
            event_count_3d = sum(1 for r in history_rows if (trade_date - r["rank_date"]).days <= 3)
            strong_event_count_7d = sum(
                1
                for r in history_rows
                if float(r["heat"] or 0) >= 70.0
                or abs(float(r["pct_chg"] or 0.0)) >= 3.0
                or str(r["heat_name"] or "") in {"高", "很高", "极高"}
            )
            active_days = len({r["rank_date"] for r in history_rows})
            continuity = min(100.0, (active_days / 7.0) * 100.0)
            avg_heat = sum(float(r["heat"] or 0.0) for r in history_rows) / max(event_count_7d, 1)
            event_strength_score = min(100.0, strong_event_count_7d * 14.0 + event_count_3d * 6.0 + avg_heat * 0.45)
            latest_dt = max(r["rank_date"] for r in history_rows)
            event_recency_days = max((trade_date - latest_dt).days, 0)

            self._evidence_refs["event"] = [
                {
                    "table": "theme_history_event",
                    "field": "event_count_3d",
                    "query": "COUNT(rank_date where >= trade_date-3d)",
                    "value": event_count_3d,
                },
                {
                    "table": "theme_history_event",
                    "field": "event_count_7d",
                    "query": "COUNT(rank_date where >= trade_date-7d)",
                    "value": event_count_7d,
                },
                {
                    "table": "theme_history_event",
                    "field": "strong_event_count_7d",
                    "query": "heat>=70 OR abs(pct_chg)>=3 OR heat_name in 高/很高/极高",
                    "value": strong_event_count_7d,
                },
                {
                    "table": "derived",
                    "field": "event_continuity_score",
                    "query": "distinct_event_days/7 * 100",
                    "value": continuity,
                },
                {
                    "table": "derived",
                    "field": "event_strength_score",
                    "query": "strong*14 + count3d*6 + avg_heat*0.45",
                    "value": round(event_strength_score, 3),
                },
            ]
            return {
                "event_count_3d": event_count_3d,
                "event_count_7d": event_count_7d,
                "event_strength_score": round(event_strength_score, 3),
                "event_continuity_score": round(continuity, 3),
                "strong_event_count_7d": strong_event_count_7d,
                "event_recency_days": event_recency_days,
            }

        self._evidence_refs["event"] = [
            {
                "table": "theme_history_event",
                "field": "*",
                "query": "fallback disabled because theme_history_event unavailable",
                "value": None,
            }
        ]
        return {
            "event_count_3d": 0,
            "event_count_7d": 0,
            "event_strength_score": 0.0,
            "event_continuity_score": 0.0,
            "strong_event_count_7d": 0,
            "event_recency_days": None,
        }

    async def _fetch_leader_layer_evidence(self, conn: asyncpg.Connection,
                                          trade_date: date,
                                          subject_key: str) -> Dict[str, Any]:
        """获取龙头层证据"""
        leader_sql = """
        SELECT
            stock_id,
            stock_name,
            COALESCE(pct_chg, 0) AS pct_chg,
            COALESCE(limit_up, FALSE) AS limit_up
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND subject_key = $2
        ORDER BY COALESCE(is_leader, FALSE) DESC, COALESCE(rank_order, 999) ASC, COALESCE(pct_chg, -100) DESC
        LIMIT 1
        """
        leader_row = await conn.fetchrow(leader_sql, trade_date, subject_key)
        if not leader_row:
            return {}

        leader_stock_id = str(leader_row.get("stock_id") or "")
        leader_stock_name = str(leader_row.get("stock_name") or "")
        leader_pct = float(leader_row.get("pct_chg") or 0.0)
        leader_limit_up = bool(leader_row.get("limit_up") or False)

        relay_sql = """
        SELECT
            COUNT(*) FILTER (WHERE COALESCE(rank_order, 999) <= 5 AND COALESCE(pct_chg, 0) >= 0) AS relay_alive,
            COUNT(*) FILTER (WHERE COALESCE(rank_order, 999) <= 5) AS relay_total,
            COUNT(*) FILTER (WHERE COALESCE(rank_order, 999) <= 5 AND COALESCE(limit_up, FALSE)) AS relay_limit_up
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND subject_key = $2
        """
        relay_row = await conn.fetchrow(relay_sql, trade_date, subject_key)
        relay_alive = int(relay_row.get("relay_alive") or 0)
        relay_total = int(relay_row.get("relay_total") or 0)
        relay_limit_up = int(relay_row.get("relay_limit_up") or 0)

        leader_alive_score = 0.0
        if leader_limit_up:
            leader_alive_score += 55.0
        if leader_pct >= 5.0:
            leader_alive_score += 25.0
        elif leader_pct >= 0:
            leader_alive_score += 15.0
        elif leader_pct > -3.0:
            leader_alive_score += 8.0
        front_row_survival_ratio = (relay_alive / relay_total) if relay_total > 0 else 0.0
        leader_alive_score += front_row_survival_ratio * 20.0
        leader_alive_score = min(100.0, leader_alive_score)

        leader_breakdown_flag = leader_pct <= -7.0 or leader_pct <= -9.5
        relay_strength_score = min(100.0, relay_limit_up * 15.0 + front_row_survival_ratio * 50.0)

        # 构建证据引用
        leader_refs = [
            {
                "table": "subject_stock_daily_snapshot",
                "field": "leader_stock",
                "query": "ORDER BY is_leader DESC, rank_order ASC LIMIT 1",
                "value": {"stock_id": leader_stock_id, "stock_name": leader_stock_name, "pct_chg": leader_pct, "limit_up": leader_limit_up},
            },
            {
                "table": "subject_stock_daily_snapshot",
                "field": "relay_stats",
                "query": "front rank alive + limit_up stats",
                "value": {"relay_alive": relay_alive, "relay_total": relay_total, "relay_limit_up": relay_limit_up},
            },
            {
                "table": "derived",
                "field": "leader_alive_score",
                "query": "leader pct + limit_up + front_row_survival",
                "value": leader_alive_score
            },
            {
                "table": "derived",
                "field": "leader_breakdown_flag",
                "query": "leader_pct <= -7.0",
                "value": leader_breakdown_flag
            },
            {
                "table": "derived",
                "field": "relay_strength_score",
                "query": "relay_limit_up*15 + front_row_survival_ratio*50",
                "value": relay_strength_score
            },
            {
                "table": "derived",
                "field": "front_row_survival_ratio",
                "query": "relay_alive/relay_total",
                "value": front_row_survival_ratio
            }
        ]
        self._evidence_refs["leader"] = leader_refs

        return {
            "leader_stock_id": leader_stock_id,
            "leader_stock_name": leader_stock_name,
            "leader_alive_score": leader_alive_score,
            "leader_breakdown_flag": leader_breakdown_flag,
            "relay_strength_score": relay_strength_score,
            "front_row_survival_ratio": front_row_survival_ratio
        }

    async def _fetch_board_structure_evidence(self, conn: asyncpg.Connection,
                                             trade_date: date,
                                             subject_key: str) -> Dict[str, Any]:
        """获取板块结构层证据"""
        sql = """
        SELECT
            COUNT(*) AS board_stock_count,
            SUM(CASE WHEN COALESCE(limit_up, FALSE) THEN 1 ELSE 0 END) AS limit_up_count,
            SUM(CASE WHEN COALESCE(pct_chg, 0) <= -9.5 THEN 1 ELSE 0 END) AS limit_down_count,
            AVG(CASE WHEN COALESCE(pct_chg, 0) > 0 THEN 1.0 ELSE 0.0 END) AS red_ratio,
            AVG(CASE WHEN COALESCE(pct_chg, 0) <= -5.0 THEN 1.0 ELSE 0.0 END) AS big_drop_ratio,
            SUM(CASE WHEN COALESCE(rank_order, 999) <= 3 OR COALESCE(is_leader, FALSE) THEN 1 ELSE 0 END) AS front_row_total,
            SUM(
                CASE
                    WHEN (COALESCE(rank_order, 999) <= 3 OR COALESCE(is_leader, FALSE))
                         AND (COALESCE(limit_up, FALSE) OR COALESCE(pct_chg, 0) >= 0)
                    THEN 1 ELSE 0
                END
            ) AS front_row_alive
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1 AND subject_key = $2
        """
        row = await conn.fetchrow(sql, trade_date, subject_key)

        if not row:
            return {}

        board_stock_count = int(row.get("board_stock_count") or 0)
        limit_up_count = int(row.get("limit_up_count") or 0)
        limit_down_count = int(row.get("limit_down_count") or 0)
        red_ratio = float(row.get("red_ratio") or 0.0)
        big_drop_ratio = float(row.get("big_drop_ratio") or 0.0)
        front_row_total = int(row.get("front_row_total") or 0)
        front_row_alive = int(row.get("front_row_alive") or 0)
        front_row_alive_ratio = (front_row_alive / front_row_total) if front_row_total > 0 else 0.0
        front_row_strength_score = min(100.0, limit_up_count * 12.0 + front_row_alive_ratio * 40.0)

        # 构建证据引用
        board_refs = [
            {
                "table": "subject_stock_daily_snapshot",
                "field": "board_stock_count",
                "query": "COUNT(*) by subject_key/trade_date",
                "value": board_stock_count,
            },
            {
                "table": "subject_stock_daily_snapshot",
                "field": "limit_up_count",
                "query": "SUM(limit_up)",
                "value": limit_up_count
            },
            {
                "table": "subject_stock_daily_snapshot",
                "field": "limit_down_count",
                "query": "SUM(pct_chg <= -9.5)",
                "value": limit_down_count
            },
            {
                "table": "subject_stock_daily_snapshot",
                "field": "red_ratio",
                "query": "AVG(pct_chg > 0)",
                "value": red_ratio
            },
            {
                "table": "subject_stock_daily_snapshot",
                "field": "big_drop_ratio",
                "query": "AVG(pct_chg <= -5.0)",
                "value": big_drop_ratio
            },
            {
                "table": "derived",
                "field": "front_row_strength_score",
                "query": "MIN(100, limit_up_count*12 + front_row_alive_ratio*40)",
                "value": front_row_strength_score
            },
            {
                "table": "derived",
                "field": "front_row_alive_ratio",
                "query": "front_row_alive / front_row_total",
                "value": {
                    "front_row_alive": front_row_alive,
                    "front_row_total": front_row_total,
                    "front_row_alive_ratio": front_row_alive_ratio,
                },
            }
        ]
        self._evidence_refs["board_structure"] = board_refs

        return {
            "board_stock_count": board_stock_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "red_ratio": red_ratio,
            "big_drop_ratio": big_drop_ratio,
            "front_row_strength_score": front_row_strength_score,
            "front_row_total": front_row_total,
            "front_row_alive": front_row_alive,
            "front_row_alive_ratio": front_row_alive_ratio,
        }

    async def _fetch_kline_evidence(self, conn: asyncpg.Connection,
                                   trade_date: date,
                                   subject_key: str) -> Dict[str, Any]:
        """获取K线技术层证据"""
        sql = """
        SELECT
            trade_date,
            AVG(COALESCE(close_price, 0)) AS avg_close,
            AVG(COALESCE(pct_chg, 0)) AS avg_pct,
            SUM(COALESCE(amount, 0)) AS total_amount
        FROM subject_stock_daily_snapshot
        WHERE subject_key = $1
          AND trade_date <= $2::date
          AND trade_date >= ($2::date - INTERVAL '30 days')
        GROUP BY trade_date
        ORDER BY trade_date DESC
        """
        rows = await conn.fetch(sql, subject_key, trade_date)
        if not rows:
            self._evidence_refs["theme_kline"] = []
            return {}

        closes = [float(r["avg_close"] or 0.0) for r in rows]
        pcts = [float(r["avg_pct"] or 0.0) for r in rows]
        amounts = [float(r["total_amount"] or 0.0) for r in rows]
        cur_close = closes[0] if closes else 0.0
        cur_amount = amounts[0] if amounts else 0.0

        def _ma(values: List[float], n: int) -> float:
            buf = values[:n]
            if not buf:
                return 0.0
            return sum(buf) / len(buf)

        ma5 = _ma(closes, 5)
        ma10 = _ma(closes, 10)
        ma20 = _ma(closes, 20)
        amt_ma5 = _ma(amounts, 5)

        theme_ret_3d = round(sum(pcts[:3]), 3)
        theme_ret_5d = round(sum(pcts[:5]), 3)
        theme_ret_10d = round(sum(pcts[:10]), 3)
        above_ma5 = cur_close >= ma5 if ma5 > 0 else False
        above_ma10 = cur_close >= ma10 if ma10 > 0 else False
        above_ma20 = cur_close >= ma20 if ma20 > 0 else False

        prior_window = closes[1:11]
        start_pivot = min(prior_window) if prior_window else cur_close
        break_start_pivot = (cur_close < start_pivot * 0.985) if start_pivot > 0 else False
        volume_breakdown_flag = (cur_amount < amt_ma5 * 0.7 and pcts and pcts[0] < -1.0) if amt_ma5 > 0 else False

        theme_support_score = 0.0
        if above_ma5:
            theme_support_score += 25.0
        if above_ma10:
            theme_support_score += 20.0
        if above_ma20:
            theme_support_score += 15.0
        if not break_start_pivot:
            theme_support_score += 20.0
        if not volume_breakdown_flag:
            theme_support_score += 20.0
        theme_support_score = round(max(0.0, min(theme_support_score, 100.0)), 3)

        # 构建证据引用
        kline_refs = [
            {
                "table": "subject_stock_daily_snapshot",
                "field": "theme_ret_3d/5d/10d",
                "query": "SUM(avg_pct over last n days by subject_key)",
                "value": {"ret_3d": theme_ret_3d, "ret_5d": theme_ret_5d, "ret_10d": theme_ret_10d},
            },
            {
                "table": "subject_stock_daily_snapshot",
                "field": "above_ma_flags",
                "query": "avg_close vs MA5/MA10/MA20",
                "value": {"above_ma5": above_ma5, "above_ma10": above_ma10, "above_ma20": above_ma20},
            },
            {
                "table": "derived",
                "field": "break_start_pivot/volume_breakdown_flag/theme_support_score",
                "query": "cur_close vs pivot + amount breakdown + support scoring",
                "value": {
                    "break_start_pivot": break_start_pivot,
                    "volume_breakdown_flag": volume_breakdown_flag,
                    "theme_support_score": theme_support_score,
                },
            },
        ]
        self._evidence_refs["theme_kline"] = kline_refs

        return {
            "theme_ret_3d": theme_ret_3d,
            "theme_ret_5d": theme_ret_5d,
            "theme_ret_10d": theme_ret_10d,
            "above_ma5": above_ma5,
            "above_ma10": above_ma10,
            "above_ma20": above_ma20,
            "theme_support_score": theme_support_score,
            "break_start_pivot": break_start_pivot,
            "volume_breakdown_flag": volume_breakdown_flag,
            "cur_close": cur_close,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "start_pivot": start_pivot,
            "cur_amount": cur_amount,
            "amt_ma5": amt_ma5,
        }

    async def _fetch_previous_cycle_state(self, conn: asyncpg.Connection,
                                         trade_date: date,
                                         subject_key: str) -> Optional[str]:
        """获取上一交易日最近周期状态（避免自然日-1导致非交易日断链）。"""
        sql_v2 = """
        SELECT final_cycle_state
        FROM theme_cycle_judgement_v2
        WHERE subject_key = $1
          AND trade_date < $2::date
        ORDER BY trade_date DESC
        LIMIT 1
        """
        row_v2 = await conn.fetchrow(sql_v2, subject_key, trade_date)
        if row_v2:
            return str(row_v2.get("final_cycle_state"))
        return None

    @staticmethod
    def _classify_evidence_failure_reason(error_text: str) -> str:
        msg = (error_text or "").lower()
        if "previous" in msg or "prior" in msg:
            return "missing_prior_state"
        if "theme_history_event" in msg or "evidence" in msg:
            return "missing_evidence"
        if "rank" in msg:
            return "missing_rank_data"
        if "shape" in msg or "attribute" in msg or "keyerror" in msg:
            return "bad_input_shape"
        if "constraint" in msg or "column" in msg or "table" in msg:
            return "db_row_inconsistent"
        return "unexpected_exception"

    @staticmethod
    def _enforce_evidence_gates(*, total: int, success: int, failed: int) -> None:
        min_success_rate = float(os.getenv("EVIDENCE_MIN_SUCCESS_RATE", "0.95"))
        max_fail_count = int(os.getenv("EVIDENCE_MAX_FAIL_COUNT", "10"))
        success_rate = (success / total) if total else 1.0
        if success_rate < min_success_rate or failed >= max_fail_count:
            raise RuntimeError(
                "evidence_gate_failed:"
                f" success_rate={success_rate:.3f}<{min_success_rate},"
                f" failed={failed}>={max_fail_count}"
            )

    @staticmethod
    def _write_evidence_diag_report(
        *,
        trade_date: date,
        total: int,
        success: int,
        failed: int,
        failure_reason_counts: dict[str, int],
        failure_samples: list[dict[str, Any]],
    ) -> None:
        out_dir = Path(os.getenv("CYCLE_DIAG_DIR", "tmp/cycle_diag"))
        out_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "trade_date": trade_date.isoformat(),
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": (success / total) if total else 1.0,
            "failure_reason_counts": failure_reason_counts,
            "failure_samples": failure_samples[:50],
        }
        (out_dir / f"cycle_evidence_diag_{trade_date.isoformat()}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )

    async def _save_evidence_to_db(self, conn: asyncpg.Connection,
                                  evidence: CycleEvidenceInput) -> None:
        """将证据保存到数据库"""
        event_data = self._layer_payload.get("event", {})
        leader_data = self._layer_payload.get("leader", {})
        board_data = self._layer_payload.get("board", {})
        kline_data = self._layer_payload.get("kline", {})
        window_data = self._layer_payload.get("window", {})

        mainline_strength_score = self._calc_mainline_strength_score(evidence)
        fade_risk_score = self._calc_fade_risk_score(evidence)

        has_updated_at = await self._check_column_exists(conn, "theme_cycle_evidence_daily", "updated_at")
        upsert_suffix = ", updated_at = now()" if has_updated_at else ""
        sql = f"""
        INSERT INTO theme_cycle_evidence_daily (
            trade_date, subject_key, theme_name,
            event_count_3d, event_count_7d, strong_event_count_7d, event_recency_days,
            event_strength_score, event_continuity_score,
            leader_stock_id, leader_stock_name, leader_alive_score, leader_breakdown_flag,
            relay_strength_score, front_row_survival_ratio,
            board_stock_count, limit_up_count, limit_down_count, red_ratio, big_drop_ratio, front_row_strength_score,
            theme_ret_3d, theme_ret_5d, theme_ret_10d, above_ma5, above_ma10, above_ma20,
            break_start_pivot, volume_breakdown_flag, theme_support_score,
            lookback_days, evidence_window_start, evidence_window_end,
            event_evidence_refs, leader_evidence_refs, board_structure_refs, theme_kline_refs,
            mainline_strength_score, fade_risk_score,
            evidence_json, source_version
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6, $7,
            $8, $9,
            $10, $11, $12, $13,
            $14, $15,
            $16, $17, $18, $19, $20, $21,
            $22, $23, $24, $25, $26, $27,
            $28, $29, $30,
            $31, $32, $33,
            $34, $35, $36, $37,
            $38, $39,
            $40, $41
        )
        ON CONFLICT (trade_date, subject_key) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            event_count_3d = EXCLUDED.event_count_3d,
            event_count_7d = EXCLUDED.event_count_7d,
            strong_event_count_7d = EXCLUDED.strong_event_count_7d,
            event_recency_days = EXCLUDED.event_recency_days,
            event_strength_score = EXCLUDED.event_strength_score,
            event_continuity_score = EXCLUDED.event_continuity_score,
            leader_stock_id = EXCLUDED.leader_stock_id,
            leader_stock_name = EXCLUDED.leader_stock_name,
            leader_alive_score = EXCLUDED.leader_alive_score,
            leader_breakdown_flag = EXCLUDED.leader_breakdown_flag,
            relay_strength_score = EXCLUDED.relay_strength_score,
            front_row_survival_ratio = EXCLUDED.front_row_survival_ratio,
            board_stock_count = EXCLUDED.board_stock_count,
            limit_up_count = EXCLUDED.limit_up_count,
            limit_down_count = EXCLUDED.limit_down_count,
            red_ratio = EXCLUDED.red_ratio,
            big_drop_ratio = EXCLUDED.big_drop_ratio,
            front_row_strength_score = EXCLUDED.front_row_strength_score,
            theme_ret_3d = EXCLUDED.theme_ret_3d,
            theme_ret_5d = EXCLUDED.theme_ret_5d,
            theme_ret_10d = EXCLUDED.theme_ret_10d,
            above_ma5 = EXCLUDED.above_ma5,
            above_ma10 = EXCLUDED.above_ma10,
            above_ma20 = EXCLUDED.above_ma20,
            break_start_pivot = EXCLUDED.break_start_pivot,
            volume_breakdown_flag = EXCLUDED.volume_breakdown_flag,
            theme_support_score = EXCLUDED.theme_support_score,
            lookback_days = EXCLUDED.lookback_days,
            evidence_window_start = EXCLUDED.evidence_window_start,
            evidence_window_end = EXCLUDED.evidence_window_end,
            event_evidence_refs = EXCLUDED.event_evidence_refs,
            leader_evidence_refs = EXCLUDED.leader_evidence_refs,
            board_structure_refs = EXCLUDED.board_structure_refs,
            theme_kline_refs = EXCLUDED.theme_kline_refs,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_risk_score = EXCLUDED.fade_risk_score,
            evidence_json = EXCLUDED.evidence_json,
            source_version = EXCLUDED.source_version
            {upsert_suffix}
        """

        # 构建evidence_json
        evidence_dict = {
            "trade_date": evidence.trade_date,
            "subject_key": evidence.subject_key,
            "theme_name": evidence.theme_name,
            "event_layer": {
                "event_count_3d": int(event_data.get("event_count_3d") or 0),
                "event_count_7d": int(event_data.get("event_count_7d") or 0),
                "event_strength_score": evidence.event_strength_score,
                "event_continuity_score": evidence.event_continuity_score,
                "strong_event_count_7d": evidence.strong_event_count_7d,
                "event_recency_days": evidence.event_recency_days
            },
            "leader_layer": {
                "leader_stock_id": str(leader_data.get("leader_stock_id") or ""),
                "leader_stock_name": str(leader_data.get("leader_stock_name") or ""),
                "leader_alive_score": evidence.leader_alive_score,
                "leader_breakdown_flag": evidence.leader_breakdown_flag,
                "relay_strength_score": evidence.relay_strength_score,
                "front_row_survival_ratio": evidence.front_row_survival_ratio
            },
            "board_layer": {
                "board_stock_count": int(board_data.get("board_stock_count") or 0),
                "limit_up_count": evidence.limit_up_count,
                "limit_down_count": evidence.limit_down_count,
                "red_ratio": evidence.red_ratio,
                "big_drop_ratio": evidence.big_drop_ratio,
                "front_row_strength_score": evidence.front_row_strength_score,
                "front_row_total": int(board_data.get("front_row_total") or 0),
                "front_row_alive": int(board_data.get("front_row_alive") or 0),
                "front_row_alive_ratio": float(board_data.get("front_row_alive_ratio") or 0.0),
            },
            "kline_layer": {
                "theme_ret_3d": kline_data.get("theme_ret_3d"),
                "theme_ret_5d": kline_data.get("theme_ret_5d"),
                "theme_ret_10d": kline_data.get("theme_ret_10d"),
                "above_ma5": kline_data.get("above_ma5"),
                "above_ma10": kline_data.get("above_ma10"),
                "above_ma20": kline_data.get("above_ma20"),
                "theme_support_score": evidence.theme_support_score,
                "break_start_pivot": evidence.break_start_pivot,
                "volume_breakdown_flag": kline_data.get("volume_breakdown_flag"),
            },
            "previous_cycle_state": evidence.previous_cycle_state,
            "mainline_strength_score": mainline_strength_score,
            "fade_risk_score": fade_risk_score,
            "raw_features": {
                "event": {
                    "event_count_3d": int(event_data.get("event_count_3d") or 0),
                    "event_count_7d": int(event_data.get("event_count_7d") or 0),
                    "strong_event_count_7d": int(event_data.get("strong_event_count_7d") or 0),
                    "event_recency_days": event_data.get("event_recency_days"),
                },
                "board": {
                    "board_stock_count": int(board_data.get("board_stock_count") or 0),
                    "limit_up_count": int(board_data.get("limit_up_count") or 0),
                    "limit_down_count": int(board_data.get("limit_down_count") or 0),
                    "red_ratio": float(board_data.get("red_ratio") or 0.0),
                    "big_drop_ratio": float(board_data.get("big_drop_ratio") or 0.0),
                    "front_row_total": int(board_data.get("front_row_total") or 0),
                    "front_row_alive": int(board_data.get("front_row_alive") or 0),
                    "front_row_alive_ratio": float(board_data.get("front_row_alive_ratio") or 0.0),
                },
                "kline": {
                    "cur_close": kline_data.get("cur_close"),
                    "ma5": kline_data.get("ma5"),
                    "ma10": kline_data.get("ma10"),
                    "ma20": kline_data.get("ma20"),
                    "start_pivot": kline_data.get("start_pivot"),
                    "cur_amount": kline_data.get("cur_amount"),
                    "amt_ma5": kline_data.get("amt_ma5"),
                },
            },
        }

        await conn.execute(
            sql,
            date.fromisoformat(evidence.trade_date),
            evidence.subject_key,
            evidence.theme_name,
            int(event_data.get("event_count_3d") or 0),
            int(event_data.get("event_count_7d") or 0),
            evidence.strong_event_count_7d,
            evidence.event_recency_days,
            evidence.event_strength_score,
            evidence.event_continuity_score,
            str(leader_data.get("leader_stock_id") or ""),
            str(leader_data.get("leader_stock_name") or ""),
            evidence.leader_alive_score,
            evidence.leader_breakdown_flag,
            evidence.relay_strength_score,
            evidence.front_row_survival_ratio,
            int(board_data.get("board_stock_count") or 0),
            evidence.limit_up_count,
            evidence.limit_down_count,
            evidence.red_ratio,
            evidence.big_drop_ratio,
            evidence.front_row_strength_score,
            kline_data.get("theme_ret_3d"),
            kline_data.get("theme_ret_5d"),
            kline_data.get("theme_ret_10d"),
            bool(kline_data.get("above_ma5") or False),
            bool(kline_data.get("above_ma10") or False),
            bool(kline_data.get("above_ma20") or False),
            evidence.break_start_pivot,
            bool(kline_data.get("volume_breakdown_flag") or False),
            evidence.theme_support_score,
            int(window_data.get("lookback_days") or 7),
            window_data.get("evidence_window_start"),
            window_data.get("evidence_window_end"),
            json.dumps(self._evidence_refs.get("event", []), ensure_ascii=False),
            json.dumps(self._evidence_refs.get("leader", []), ensure_ascii=False),
            json.dumps(self._evidence_refs.get("board_structure", []), ensure_ascii=False),
            json.dumps(self._evidence_refs.get("theme_kline", []), ensure_ascii=False),
            mainline_strength_score,
            fade_risk_score,
            json.dumps(evidence_dict, ensure_ascii=False),
            "theme_cycle_evidence.v1"
        )

    def _calc_mainline_strength_score(self, evidence: CycleEvidenceInput) -> float:
        score = (
            float(evidence.event_strength_score) * 0.20
            + float(evidence.event_continuity_score) * 0.15
            + float(evidence.leader_alive_score) * 0.25
            + float(evidence.relay_strength_score) * 0.15
            + float(evidence.front_row_strength_score) * 0.15
            + float(evidence.theme_support_score) * 0.10
        )
        return round(max(0.0, min(score, 100.0)), 3)

    def _calc_fade_risk_score(self, evidence: CycleEvidenceInput) -> float:
        leader_break = 100.0 if bool(evidence.leader_breakdown_flag) else 0.0
        continuity = float(evidence.event_continuity_score or 0.0)
        recency = int(evidence.event_recency_days) if evidence.event_recency_days is not None else 7
        strong_events = int(evidence.strong_event_count_7d or 0)
        event_decay_score = 0.0
        if strong_events == 0:
            event_decay_score += 18.0
        event_decay_score += min(max(recency, 0) * 4.0, 20.0)
        event_decay_score += max(0.0, 40.0 - continuity) * 0.5
        score = (
            leader_break * 0.35
            + float(evidence.big_drop_ratio) * 30.0
            + float(evidence.limit_down_count) * 8.0
            + max(0.0, 1.0 - float(evidence.red_ratio)) * 35.0
            + min(event_decay_score, 25.0)
        )
        return round(max(0.0, min(score, 100.0)), 3)

    def _to_theme_cycle_evidence_payload(
        self,
        *,
        evidence: CycleEvidenceInput,
        mainline_strength_score: float,
        fade_risk_score: float,
    ) -> ThemeCycleEvidence:
        evidence_json = {
            "trade_date": evidence.trade_date,
            "subject_key": evidence.subject_key,
            "theme_name": evidence.theme_name,
            "mainline_strength_score": mainline_strength_score,
            "fade_risk_score": fade_risk_score,
        }
        return ThemeCycleEvidence(
            trade_date=date.fromisoformat(evidence.trade_date),
            subject_key=evidence.subject_key,
            theme_name=evidence.theme_name,
            mainline_strength_score=mainline_strength_score,
            fade_risk_score=fade_risk_score,
            event_evidence_refs=self._evidence_refs.get("event", []),
            leader_evidence_refs=self._evidence_refs.get("leader", []),
            board_structure_refs=self._evidence_refs.get("board_structure", []),
            theme_kline_refs=self._evidence_refs.get("theme_kline", []),
            evidence_json=evidence_json,
        )


async def main():
    """测试函数"""
    import sys
    from datetime import date

    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)

    builder = ThemeCycleEvidenceBuilder()
    try:
        print(f"开始构建 {test_date} 的周期证据...")
        evidence_list = await builder.build_evidence_for_date(test_date)
        print(f"完成构建 {len(evidence_list)} 个证据")
    finally:
        await builder.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

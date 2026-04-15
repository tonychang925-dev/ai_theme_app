from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Dict, List, Optional, Any
import asyncpg

from stock_service.services.unified_cycle_scoring_service import CycleEvidenceInput


class ThemeCycleEvidenceBuilder:
    """主题周期证据构建器

    从现有数据表构建四层证据，存入 theme_cycle_evidence_daily 表
    严格按照用户骨架设计：只构建证据，不做最终判决
    """

    def __init__(self, config=None):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self._evidence_refs: Dict[str, List[Dict[str, Any]]] = {}

    async def _ensure_pool(self) -> asyncpg.Pool:
        """确保数据库连接池存在"""
        if self._pool is None:
            # 使用默认配置（与 enhanced_candidate_builder 保持一致）
            self._pool = await asyncpg.create_pool(
                host='localhost',
                port=5432,
                user='postgres',
                password='postgres',
                database='stock_data_test',
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

            # 2. 获取所有需要处理的主题（从 theme_mainline_judgement）
            subjects = await self._fetch_subjects_for_date(conn, trade_date)
            if not subjects:
                print(f"⚠️ 交易日 {trade_date} 无主题数据")
                return []

            # 3. 为每个主题构建证据
            evidence_inputs = []
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
                    print(f"❌ 主题 {subject_key} 证据构建失败: {e}")
                    continue

            print(f"📊 总计构建 {len(evidence_inputs)} 个主题的周期证据")
            return evidence_inputs

    async def _fetch_subjects_for_date(self, conn: asyncpg.Connection,
                                      trade_date: date) -> List[Dict[str, Any]]:
        """获取指定交易日需要处理的所有主题"""
        sql = """
        SELECT DISTINCT
            subject_key,
            COALESCE(theme_name, subject_key) AS theme_name
        FROM theme_mainline_judgement
        WHERE trade_date = $1
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
            strong_event_count_7d=int(event_data.get("strong_event_count_7d", 0)),
            event_recency_days=event_data.get("event_recency_days"),

            # 龙头/接力层
            leader_alive_score=float(leader_data.get("leader_alive_score", 0)),
            leader_breakdown_flag=bool(leader_data.get("leader_breakdown_flag", False)),
            relay_strength_score=float(leader_data.get("relay_strength_score", 0)),
            front_row_survival_ratio=float(leader_data.get("front_row_survival_ratio", 0)),

            # 板块结构层
            limit_up_count=int(board_data.get("limit_up_count", 0)),
            limit_down_count=int(board_data.get("limit_down_count", 0)),
            red_ratio=float(board_data.get("red_ratio", 0)),
            big_drop_ratio=float(board_data.get("big_drop_ratio", 0)),
            front_row_strength_score=float(board_data.get("front_row_strength_score", 0)),

            # 板块K线技术层
            theme_support_score=float(kline_data.get("theme_support_score", 0)),
            break_start_pivot=bool(kline_data.get("break_start_pivot", False)),

            # 前一日状态
            previous_cycle_state=previous_state
        )

        return evidence

    async def _fetch_event_layer_evidence(self, conn: asyncpg.Connection,
                                         trade_date: date,
                                         subject_key: str) -> Dict[str, Any]:
        """获取事件层证据"""
        sql = """
        SELECT
            event_chain_score,
            event_chain_continuity_score
        FROM theme_mainline_judgement
        WHERE trade_date = $1 AND subject_key = $2
        """
        row = await conn.fetchrow(sql, trade_date, subject_key)

        if not row:
            return {}

        # 简化处理：使用现有字段映射
        event_chain_score = float(row.get("event_chain_score", 0))
        event_chain_continuity_score = float(row.get("event_chain_continuity_score", 0))

        # 构建证据引用
        event_refs = [
            {
                "table": "theme_mainline_judgement",
                "field": "event_chain_score",
                "query": "SELECT event_chain_score FROM theme_mainline_judgement WHERE trade_date = $1 AND subject_key = $2",
                "value": event_chain_score
            },
            {
                "table": "theme_mainline_judgement",
                "field": "event_chain_continuity_score",
                "query": "SELECT event_chain_continuity_score FROM theme_mainline_judgement WHERE trade_date = $1 AND subject_key = $2",
                "value": event_chain_continuity_score
            },
            {
                "table": "derived",
                "field": "strong_event_count_7d",
                "query": "IF(event_chain_score > 30, 1, 0) 估算逻辑",
                "value": 1 if event_chain_score > 30 else 0
            },
            {
                "table": "derived",
                "field": "event_recency_days",
                "query": "IF(event_chain_score > 0, 1, NULL) 估算逻辑",
                "value": 1 if event_chain_score > 0 else None
            }
        ]
        self._evidence_refs["event"] = event_refs

        # 估算其他字段（简化版）
        return {
            "event_strength_score": event_chain_score,  # 事件强度评分 ≈ 事件链分数
            "event_continuity_score": event_chain_continuity_score,
            "strong_event_count_7d": 1 if event_chain_score > 30 else 0,
            "event_recency_days": 1 if event_chain_score > 0 else None
        }

    async def _fetch_leader_layer_evidence(self, conn: asyncpg.Connection,
                                          trade_date: date,
                                          subject_key: str) -> Dict[str, Any]:
        """获取龙头层证据"""
        sql = """
        SELECT
            leader_status,
            limit_up_count
        FROM theme_cycle_judgement
        WHERE trade_date = $1 AND subject_key = $2
        """
        row = await conn.fetchrow(sql, trade_date, subject_key)

        if not row:
            return {}

        leader_status = str(row.get("leader_status", ""))
        limit_up_count = int(row.get("limit_up_count", 0))

        # 计算龙头存活评分
        if "龙头加强" in leader_status or "龙头强势" in leader_status:
            leader_alive_score = 80.0
        elif "龙头活跃" in leader_status:
            leader_alive_score = 60.0
        else:
            leader_alive_score = 30.0

        # 龙头破位标志：如果龙头走弱
        leader_breakdown_flag = leader_status == "龙头走弱"

        # 接力强度评分：基于涨停数量
        relay_strength_score = min(limit_up_count * 10.0, 100.0)

        # 前排存活率：简化，基于涨停数量估算强势股数量
        strong_stock_count = max(limit_up_count, 1)  # 估计
        front_row_survival_ratio = min(limit_up_count / strong_stock_count, 1.0)

        # 构建证据引用
        leader_refs = [
            {
                "table": "theme_cycle_judgement",
                "field": "leader_status",
                "query": "SELECT leader_status FROM theme_cycle_judgement WHERE trade_date = $1 AND subject_key = $2",
                "value": leader_status
            },
            {
                "table": "theme_cycle_judgement",
                "field": "limit_up_count",
                "query": "SELECT limit_up_count FROM theme_cycle_judgement WHERE trade_date = $1 AND subject_key = $2",
                "value": limit_up_count
            },
            {
                "table": "derived",
                "field": "leader_alive_score",
                "query": "IF(leader_status contains '龙头加强' or '龙头强势', 80, IF(leader_status contains '龙头活跃', 60, 30))",
                "value": leader_alive_score
            },
            {
                "table": "derived",
                "field": "leader_breakdown_flag",
                "query": "leader_status == '龙头走弱'",
                "value": leader_breakdown_flag
            },
            {
                "table": "derived",
                "field": "relay_strength_score",
                "query": "MIN(limit_up_count * 10.0, 100.0)",
                "value": relay_strength_score
            },
            {
                "table": "derived",
                "field": "front_row_survival_ratio",
                "query": "MIN(limit_up_count / MAX(limit_up_count, 1), 1.0)",
                "value": front_row_survival_ratio
            }
        ]
        self._evidence_refs["leader"] = leader_refs

        return {
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
            limit_up_count
        FROM theme_cycle_judgement
        WHERE trade_date = $1 AND subject_key = $2
        """
        row = await conn.fetchrow(sql, trade_date, subject_key)

        if not row:
            return {}

        limit_up_count = int(row.get("limit_up_count", 0))

        # 简化处理：使用默认值或估算
        limit_down_count = 0  # 现有表无此字段

        # 红盘比例：假设50%红盘
        red_ratio = 0.5

        # 大跌比例：假设10%大跌
        big_drop_ratio = 0.1

        # 前排强度评分：基于涨停数量
        front_row_strength_score = min(limit_up_count * 15.0, 100.0)

        # 构建证据引用
        board_refs = [
            {
                "table": "theme_cycle_judgement",
                "field": "limit_up_count",
                "query": "SELECT limit_up_count FROM theme_cycle_judgement WHERE trade_date = $1 AND subject_key = $2",
                "value": limit_up_count
            },
            {
                "table": "default",
                "field": "limit_down_count",
                "query": "默认值0（现有表无此字段）",
                "value": limit_down_count
            },
            {
                "table": "default",
                "field": "red_ratio",
                "query": "默认值0.5（估算）",
                "value": red_ratio
            },
            {
                "table": "default",
                "field": "big_drop_ratio",
                "query": "默认值0.1（估算）",
                "value": big_drop_ratio
            },
            {
                "table": "derived",
                "field": "front_row_strength_score",
                "query": "MIN(limit_up_count * 15.0, 100.0)",
                "value": front_row_strength_score
            }
        ]
        self._evidence_refs["board_structure"] = board_refs

        return {
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "red_ratio": red_ratio,
            "big_drop_ratio": big_drop_ratio,
            "front_row_strength_score": front_row_strength_score
        }

    async def _fetch_kline_evidence(self, conn: asyncpg.Connection,
                                   trade_date: date,
                                   subject_key: str) -> Dict[str, Any]:
        """获取K线技术层证据"""
        # 现有系统缺少板块K线数据，使用简化处理
        theme_support_score = 60.0
        break_start_pivot = False

        # 构建证据引用
        kline_refs = [
            {
                "table": "default",
                "field": "theme_support_score",
                "query": "默认值60.0（中等支撑）",
                "value": theme_support_score
            },
            {
                "table": "default",
                "field": "break_start_pivot",
                "query": "默认值False（未跌破启动枢轴）",
                "value": break_start_pivot
            }
        ]
        self._evidence_refs["theme_kline"] = kline_refs

        return {
            "theme_support_score": theme_support_score,  # 默认中等支撑
            "break_start_pivot": break_start_pivot    # 默认未跌破启动枢轴
        }

    async def _fetch_previous_cycle_state(self, conn: asyncpg.Connection,
                                         trade_date: date,
                                         subject_key: str) -> Optional[str]:
        """获取前一日周期状态"""
        prev_date = trade_date - timedelta(days=1)

        # 首先尝试从V2表查询
        sql_v2 = """
        SELECT final_cycle_state
        FROM theme_cycle_judgement_v2
        WHERE trade_date = $1 AND subject_key = $2
        """
        row_v2 = await conn.fetchrow(sql_v2, prev_date, subject_key)
        if row_v2:
            return str(row_v2.get("final_cycle_state"))

        # 回退到原表
        sql_original = """
        SELECT primary_cycle_stage
        FROM theme_cycle_judgement
        WHERE trade_date = $1 AND subject_key = $2
        """
        row_original = await conn.fetchrow(sql_original, prev_date, subject_key)
        if row_original:
            return str(row_original.get("primary_cycle_stage"))

        return None

    async def _save_evidence_to_db(self, conn: asyncpg.Connection,
                                  evidence: CycleEvidenceInput) -> None:
        """将证据保存到数据库"""
        sql = """
        INSERT INTO theme_cycle_evidence_daily (
            trade_date, subject_key, theme_name,
            event_strength_score, event_continuity_score,
            strong_event_count_7d, event_recency_days,
            leader_alive_score, leader_breakdown_flag,
            relay_strength_score, front_row_survival_ratio,
            limit_up_count, limit_down_count, red_ratio,
            big_drop_ratio, front_row_strength_score,
            theme_support_score, break_start_pivot,
            event_evidence_refs, leader_evidence_refs,
            board_structure_refs, theme_kline_refs,
            evidence_json, source_version
        ) VALUES (
            $1, $2, $3,
            $4, $5,
            $6, $7,
            $8, $9,
            $10, $11,
            $12, $13, $14,
            $15, $16,
            $17, $18,
            $19, $20,
            $21, $22,
            $23, $24
        )
        ON CONFLICT (trade_date, subject_key) DO UPDATE SET
            event_strength_score = EXCLUDED.event_strength_score,
            event_continuity_score = EXCLUDED.event_continuity_score,
            strong_event_count_7d = EXCLUDED.strong_event_count_7d,
            event_recency_days = EXCLUDED.event_recency_days,
            leader_alive_score = EXCLUDED.leader_alive_score,
            leader_breakdown_flag = EXCLUDED.leader_breakdown_flag,
            relay_strength_score = EXCLUDED.relay_strength_score,
            front_row_survival_ratio = EXCLUDED.front_row_survival_ratio,
            limit_up_count = EXCLUDED.limit_up_count,
            limit_down_count = EXCLUDED.limit_down_count,
            red_ratio = EXCLUDED.red_ratio,
            big_drop_ratio = EXCLUDED.big_drop_ratio,
            front_row_strength_score = EXCLUDED.front_row_strength_score,
            theme_support_score = EXCLUDED.theme_support_score,
            break_start_pivot = EXCLUDED.break_start_pivot,
            event_evidence_refs = EXCLUDED.event_evidence_refs,
            leader_evidence_refs = EXCLUDED.leader_evidence_refs,
            board_structure_refs = EXCLUDED.board_structure_refs,
            theme_kline_refs = EXCLUDED.theme_kline_refs,
            evidence_json = EXCLUDED.evidence_json,
            source_version = EXCLUDED.source_version,
            created_at = now()
        """

        # 构建evidence_json
        evidence_dict = {
            "trade_date": evidence.trade_date,
            "subject_key": evidence.subject_key,
            "theme_name": evidence.theme_name,
            "event_layer": {
                "event_strength_score": evidence.event_strength_score,
                "event_continuity_score": evidence.event_continuity_score,
                "strong_event_count_7d": evidence.strong_event_count_7d,
                "event_recency_days": evidence.event_recency_days
            },
            "leader_layer": {
                "leader_alive_score": evidence.leader_alive_score,
                "leader_breakdown_flag": evidence.leader_breakdown_flag,
                "relay_strength_score": evidence.relay_strength_score,
                "front_row_survival_ratio": evidence.front_row_survival_ratio
            },
            "board_layer": {
                "limit_up_count": evidence.limit_up_count,
                "limit_down_count": evidence.limit_down_count,
                "red_ratio": evidence.red_ratio,
                "big_drop_ratio": evidence.big_drop_ratio,
                "front_row_strength_score": evidence.front_row_strength_score
            },
            "kline_layer": {
                "theme_support_score": evidence.theme_support_score,
                "break_start_pivot": evidence.break_start_pivot
            },
            "previous_cycle_state": evidence.previous_cycle_state
        }

        await conn.execute(
            sql,
            date.fromisoformat(evidence.trade_date),
            evidence.subject_key,
            evidence.theme_name,
            evidence.event_strength_score,
            evidence.event_continuity_score,
            evidence.strong_event_count_7d,
            evidence.event_recency_days,
            evidence.leader_alive_score,
            evidence.leader_breakdown_flag,
            evidence.relay_strength_score,
            evidence.front_row_survival_ratio,
            evidence.limit_up_count,
            evidence.limit_down_count,
            evidence.red_ratio,
            evidence.big_drop_ratio,
            evidence.front_row_strength_score,
            evidence.theme_support_score,
            evidence.break_start_pivot,
            json.dumps(self._evidence_refs.get("event", []), ensure_ascii=False),
            json.dumps(self._evidence_refs.get("leader", []), ensure_ascii=False),
            json.dumps(self._evidence_refs.get("board_structure", []), ensure_ascii=False),
            json.dumps(self._evidence_refs.get("theme_kline", []), ensure_ascii=False),
            json.dumps(evidence_dict, ensure_ascii=False),
            "theme_cycle_evidence.v1"
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
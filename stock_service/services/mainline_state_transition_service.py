from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import asyncpg

from stock_service.config import StockServiceConfig


STATE_RANK = {
    "fade_confirmed": 0,
    "fade_watch": 1,
    "start": 2,
    "fermentation": 3,
    "divergence": 4,
    "repair": 5,
    "acceleration": 6,
}


@dataclass
class MainlineStateDaily:
    trade_date: date
    subject_key: str
    theme_name: str
    state: str
    state_score: float
    is_mainline: bool
    mainline_strength_score: float
    fade_watch_score: float
    fade_confirmed_score: float
    divergence_score: float
    repair_score: float
    evidence_json: Dict[str, Any]
    llm_verdict: Dict[str, Any]
    llm_reason: Optional[str]
    decision_path: List[str]


@dataclass
class MainlineStateTransition:
    trade_date: date
    subject_key: str
    theme_name: str
    from_state: Optional[str]
    to_state: str
    transition_type: str
    from_score: float
    to_score: float
    confidence: float
    trigger_flags: List[str]
    evidence_json: Dict[str, Any]


class MainlineStateTransitionService:
    """
    主线状态快照与迁移监控服务。

    规则硬约束：
    1) state 只来自 final_cycle_state
    2) is_mainline 只由 identity_confirmed(confirmed) + final_mainline_alive 决定
    3) 可记录“非主线升级观察样本”，但不得越过身份门禁写成 is_mainline=true
    """

    RULE_VERSION = "mainline_state_transition.v1"

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self.pool: Optional[asyncpg.Pool] = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_database,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                min_size=1,
                max_size=4,
            )
        return self.pool

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def build_daily_snapshot(self, trade_date: date) -> int:
        pool = await self._ensure_pool()
        rows = await self._fetch_judgement_rows(trade_date)
        upserted = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    snapshot = self._to_daily_snapshot(trade_date, row)
                    await self._upsert_mainline_state_daily(conn, snapshot)
                    upserted += 1
        return upserted

    async def build_transition(self, trade_date: date) -> int:
        pool = await self._ensure_pool()
        today_rows = await self._fetch_mainline_state_daily(trade_date)
        upserted = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for row in today_rows:
                    prev = await self._fetch_previous_mainline_state(conn, trade_date, str(row["subject_key"]))
                    transition = self._to_transition(trade_date, row, prev)
                    await self._upsert_mainline_state_transition(conn, transition)
                    upserted += 1
        return upserted

    async def generate_daily_report(self, trade_date: date) -> Dict[str, List[Dict[str, Any]]]:
        pool = await self._ensure_pool()
        sql = """
        SELECT
            subject_key,
            theme_name,
            from_state,
            to_state,
            transition_type,
            confidence,
            trigger_flags
        FROM mainline_state_transition
        WHERE trade_date = $1::date
        ORDER BY transition_type, confidence DESC, subject_key
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)

        report = {
            "upgrade_list": [],
            "downgrade_list": [],
            "fade_list": [],
            "flat_list": [],
        }
        for row in rows:
            item = {
                "subject_key": str(row.get("subject_key") or ""),
                "theme_name": str(row.get("theme_name") or row.get("subject_key") or ""),
                "from_state": (str(row["from_state"]) if row["from_state"] is not None else None),
                "to_state": str(row.get("to_state") or ""),
                "transition_type": str(row.get("transition_type") or "flat"),
                "confidence": float(row.get("confidence") or 0.0),
                "trigger_flags": self._as_list(row.get("trigger_flags")),
            }
            transition_type = item["transition_type"]
            if transition_type == "upgrade":
                report["upgrade_list"].append(item)
            elif transition_type == "downgrade":
                report["downgrade_list"].append(item)
            elif transition_type == "fade":
                report["fade_list"].append(item)
            else:
                report["flat_list"].append(item)
        return report

    async def _fetch_judgement_rows(self, trade_date: date) -> List[asyncpg.Record]:
        pool = await self._ensure_pool()
        # 新口径：身份与周期分层。
        # - identity_confirmed 严格来自 registry.confirmed（主链硬规则0）；
        # - 非主线题材可进入“升级观察”快照，但 is_mainline 必须保持 false；
        # - 每日主线状态跟踪以 mainline_state_daily 为统一消费口径。
        sql = """
        SELECT
            v2.trade_date,
            v2.subject_key,
            COALESCE(NULLIF(v2.theme_name, ''), v2.subject_key) AS theme_name,
            COALESCE(v2.final_cycle_state, 'start') AS final_cycle_state,
            COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive,
            COALESCE(v2.mainline_strength_score, 0) AS mainline_strength_score,
            COALESCE(v2.fade_watch_score, 0) AS fade_watch_score,
            COALESCE(v2.fade_confirmed_score, 0) AS fade_confirmed_score,
            COALESCE(v2.divergence_score, 0) AS divergence_score,
            COALESCE(v2.repair_score, 0) AS repair_score,
            COALESCE(v2.rule_reasons, '[]'::jsonb) AS rule_reasons,
            COALESCE(v2.evidence_refs, '{}'::jsonb) AS evidence_refs,
            COALESCE(mr.evidence_json, '{}'::jsonb) AS identity_evidence_json,
            (
                COALESCE(mr.is_main_theme, FALSE) = TRUE
                AND COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') = 'confirmed'
            ) AS identity_confirmed
        FROM theme_cycle_judgement_v2 v2
        LEFT JOIN theme_mainline_identity_registry mr
          ON mr.subject_key = v2.subject_key
        LEFT JOIN LATERAL (
            SELECT TRUE AS has_snapshot, d.is_mainline
            FROM mainline_state_daily d
            WHERE d.subject_key = v2.subject_key
              AND d.trade_date < $1::date
            ORDER BY d.trade_date DESC
            LIMIT 1
        ) prev ON TRUE
        WHERE v2.trade_date = $1::date
          AND (
                (
                    COALESCE(mr.is_main_theme, FALSE) = TRUE
                    AND COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') = 'confirmed'
                )
                OR COALESCE(prev.has_snapshot, FALSE)
                OR (
                    COALESCE(v2.final_mainline_alive, FALSE) = TRUE
                    AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                    AND COALESCE(v2.mainline_strength_score, 0) >= 60
                )
          )
        ORDER BY COALESCE(v2.mainline_strength_score, 0) DESC, v2.subject_key
        """
        async with pool.acquire() as conn:
            return await conn.fetch(sql, trade_date)

    async def _fetch_mainline_state_daily(self, trade_date: date) -> List[asyncpg.Record]:
        pool = await self._ensure_pool()
        sql = """
        SELECT *
        FROM mainline_state_daily
        WHERE trade_date = $1::date
        ORDER BY state_score DESC, subject_key
        """
        async with pool.acquire() as conn:
            return await conn.fetch(sql, trade_date)

    async def _fetch_previous_mainline_state(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        subject_key: str,
    ) -> Optional[asyncpg.Record]:
        sql = """
        SELECT *
        FROM mainline_state_daily
        WHERE trade_date < $1::date
          AND subject_key = $2
        ORDER BY trade_date DESC
        LIMIT 1
        """
        return await conn.fetchrow(sql, trade_date, subject_key)

    def _to_daily_snapshot(self, trade_date: date, row: asyncpg.Record) -> MainlineStateDaily:
        state = str(row.get("final_cycle_state") or "start")
        mainline_strength_score = float(row.get("mainline_strength_score") or 0.0)
        fade_watch_score = float(row.get("fade_watch_score") or 0.0)
        fade_confirmed_score = float(row.get("fade_confirmed_score") or 0.0)
        divergence_score = float(row.get("divergence_score") or 0.0)
        repair_score = float(row.get("repair_score") or 0.0)
        identity_confirmed = bool(row.get("identity_confirmed") or False)
        final_mainline_alive = bool(row.get("final_mainline_alive") or False)
        is_mainline = identity_confirmed and final_mainline_alive

        if state == "acceleration":
            state_score = mainline_strength_score
        elif state == "repair":
            state_score = repair_score
        elif state == "divergence":
            state_score = divergence_score
        elif state == "fade_watch":
            state_score = fade_watch_score
        elif state == "fade_confirmed":
            state_score = fade_confirmed_score
        else:
            state_score = mainline_strength_score

        evidence_json = {
            "rule_reasons": self._as_list(row.get("rule_reasons")),
            "evidence_refs": self._as_dict(row.get("evidence_refs")),
            "identity_evidence": self._as_dict(row.get("identity_evidence_json")),
            "scores": {
                "mainline_strength_score": round(mainline_strength_score, 2),
                "fade_watch_score": round(fade_watch_score, 2),
                "fade_confirmed_score": round(fade_confirmed_score, 2),
                "divergence_score": round(divergence_score, 2),
                "repair_score": round(repair_score, 2),
            },
            "identity_confirmed": identity_confirmed,
            "final_mainline_alive": final_mainline_alive,
        }

        return MainlineStateDaily(
            trade_date=trade_date,
            subject_key=str(row.get("subject_key") or ""),
            theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
            state=state,
            state_score=round(state_score, 2),
            is_mainline=is_mainline,
            mainline_strength_score=round(mainline_strength_score, 2),
            fade_watch_score=round(fade_watch_score, 2),
            fade_confirmed_score=round(fade_confirmed_score, 2),
            divergence_score=round(divergence_score, 2),
            repair_score=round(repair_score, 2),
            evidence_json=evidence_json,
            llm_verdict={},
            llm_reason=None,
            # 兼容旧库：若 judgement_v2 尚无 decision_path 列，退化使用 rule_reasons。
            decision_path=self._as_list(row.get("rule_reasons")),
        )

    def _to_transition(
        self,
        trade_date: date,
        current_row: asyncpg.Record,
        prev_row: Optional[asyncpg.Record],
    ) -> MainlineStateTransition:
        to_state = str(current_row.get("state") or "start")
        to_score = float(current_row.get("state_score") or 0.0)
        from_state = (str(prev_row.get("state")) if prev_row else None)
        from_score = float(prev_row.get("state_score") or 0.0) if prev_row else 0.0

        transition_type = self._classify_transition(from_state, to_state, current_row, prev_row)
        trigger_flags = self._build_trigger_flags(current_row, prev_row, transition_type)
        confidence = self._calc_transition_confidence(current_row, prev_row, transition_type)
        evidence_json = {
            "from": {"state": from_state, "score": round(from_score, 2)},
            "to": {"state": to_state, "score": round(to_score, 2)},
            "trigger_flags": trigger_flags,
        }
        return MainlineStateTransition(
            trade_date=trade_date,
            subject_key=str(current_row.get("subject_key") or ""),
            theme_name=str(current_row.get("theme_name") or current_row.get("subject_key") or ""),
            from_state=from_state,
            to_state=to_state,
            transition_type=transition_type,
            from_score=round(from_score, 2),
            to_score=round(to_score, 2),
            confidence=round(confidence, 2),
            trigger_flags=trigger_flags,
            evidence_json=evidence_json,
        )

    def _classify_transition(
        self,
        from_state: Optional[str],
        to_state: str,
        current_row: asyncpg.Record,
        prev_row: Optional[asyncpg.Record],
    ) -> str:
        current_k = self._extract_kline_flags(current_row)
        prev_k = self._extract_kline_flags(prev_row) if prev_row else {}
        kline_support_hold = bool(current_k.get("kline_support_hold", False))
        one_day_tour_kline_flag = bool(current_k.get("one_day_tour_kline_flag", False))
        platform_breakout_flag = bool(current_k.get("platform_breakout_flag", False))

        if to_state == "fade_confirmed" or (one_day_tour_kline_flag and not kline_support_hold):
            return "fade"
        if not from_state or from_state == to_state:
            # 同状态下若技术形态明显走坏，按降级处理；反之若平台突破，允许视作升级。
            if from_state == to_state and not kline_support_hold and to_state in {"divergence", "repair", "fermentation", "start"}:
                return "downgrade"
            if from_state == to_state and platform_breakout_flag and to_state in {"start", "fermentation", "divergence", "repair"}:
                return "upgrade"
            return "flat"
        if STATE_RANK.get(to_state, 0) > STATE_RANK.get(from_state, 0):
            return "upgrade"
        # 状态层级降级但K线支撑未破，则保守判平级，避免“分歧=退潮”误判。
        if kline_support_hold and not one_day_tour_kline_flag and to_state in {"divergence", "repair", "fade_watch"}:
            return "flat"
        return "downgrade"

    def _build_trigger_flags(
        self,
        current_row: asyncpg.Record,
        prev_row: Optional[asyncpg.Record],
        transition_type: str,
    ) -> List[str]:
        flags: List[str] = []
        if transition_type == "fade":
            flags.append("to_state=fade_confirmed")
        if prev_row is None:
            flags.append("no_previous_snapshot")
            return flags
        if float(current_row.get("mainline_strength_score") or 0.0) > float(prev_row.get("mainline_strength_score") or 0.0) + 8.0:
            flags.append("mainline_strength_jump")
        if float(current_row.get("fade_confirmed_score") or 0.0) > float(prev_row.get("fade_confirmed_score") or 0.0) + 10.0:
            flags.append("fade_risk_jump")
        if str(current_row.get("state") or "") != str(prev_row.get("state") or ""):
            flags.append("state_changed")
        k_flags = self._extract_kline_flags(current_row)
        if bool(k_flags.get("kline_support_hold")):
            flags.append("kline_support_hold")
        if bool(k_flags.get("platform_breakout_flag")):
            flags.append("platform_breakout")
        if bool(k_flags.get("one_day_tour_kline_flag")):
            flags.append("kline_one_day_tour")
        return flags

    def _calc_transition_confidence(
        self,
        current_row: asyncpg.Record,
        prev_row: Optional[asyncpg.Record],
        transition_type: str,
    ) -> float:
        if prev_row is None:
            return 60.0
        score_delta = abs(float(current_row.get("state_score") or 0.0) - float(prev_row.get("state_score") or 0.0))
        confidence = 60.0 + min(score_delta * 0.8, 30.0)
        if transition_type == "fade":
            confidence += 5.0
        return min(confidence, 95.0)

    def _extract_kline_flags(self, row: Optional[asyncpg.Record]) -> Dict[str, Any]:
        if row is None:
            return {}
        evidence = self._as_dict(row.get("evidence_json"))
        identity_evidence = self._as_dict(evidence.get("identity_evidence"))
        return {
            "kline_support_hold": bool(identity_evidence.get("kline_support_hold") or False),
            "one_day_tour_kline_flag": bool(identity_evidence.get("one_day_tour_kline_flag") or False),
            "platform_breakout_flag": bool(identity_evidence.get("platform_breakout_flag") or False),
        }

    async def _upsert_mainline_state_daily(
        self,
        conn: asyncpg.Connection,
        snapshot: MainlineStateDaily,
    ) -> None:
        sql = """
        INSERT INTO mainline_state_daily (
            trade_date, subject_key, theme_name,
            state, state_score, is_mainline,
            mainline_strength_score, fade_watch_score, fade_confirmed_score,
            divergence_score, repair_score,
            evidence_json, llm_verdict, llm_reason, decision_path,
            source_version, created_at, updated_at
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6,
            $7, $8, $9,
            $10, $11,
            $12::jsonb, $13::jsonb, $14, $15::jsonb,
            $16, now(), now()
        )
        ON CONFLICT (trade_date, subject_key) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            state = EXCLUDED.state,
            state_score = EXCLUDED.state_score,
            is_mainline = EXCLUDED.is_mainline,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_watch_score = EXCLUDED.fade_watch_score,
            fade_confirmed_score = EXCLUDED.fade_confirmed_score,
            divergence_score = EXCLUDED.divergence_score,
            repair_score = EXCLUDED.repair_score,
            evidence_json = EXCLUDED.evidence_json,
            llm_verdict = EXCLUDED.llm_verdict,
            llm_reason = EXCLUDED.llm_reason,
            decision_path = EXCLUDED.decision_path,
            source_version = EXCLUDED.source_version,
            updated_at = now()
        """
        await conn.execute(
            sql,
            snapshot.trade_date,
            snapshot.subject_key,
            snapshot.theme_name,
            snapshot.state,
            snapshot.state_score,
            snapshot.is_mainline,
            snapshot.mainline_strength_score,
            snapshot.fade_watch_score,
            snapshot.fade_confirmed_score,
            snapshot.divergence_score,
            snapshot.repair_score,
            json.dumps(snapshot.evidence_json, ensure_ascii=False),
            json.dumps(snapshot.llm_verdict, ensure_ascii=False),
            snapshot.llm_reason,
            json.dumps(snapshot.decision_path, ensure_ascii=False),
            "mainline_state_daily.v1",
        )

    async def _upsert_mainline_state_transition(
        self,
        conn: asyncpg.Connection,
        transition: MainlineStateTransition,
    ) -> None:
        sql = """
        INSERT INTO mainline_state_transition (
            trade_date, subject_key, theme_name,
            from_state, to_state, transition_type,
            from_score, to_score, confidence,
            trigger_flags, evidence_json,
            source_version, created_at
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6,
            $7, $8, $9,
            $10::jsonb, $11::jsonb,
            $12, now()
        )
        ON CONFLICT (trade_date, subject_key) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            from_state = EXCLUDED.from_state,
            to_state = EXCLUDED.to_state,
            transition_type = EXCLUDED.transition_type,
            from_score = EXCLUDED.from_score,
            to_score = EXCLUDED.to_score,
            confidence = EXCLUDED.confidence,
            trigger_flags = EXCLUDED.trigger_flags,
            evidence_json = EXCLUDED.evidence_json,
            source_version = EXCLUDED.source_version
        """
        await conn.execute(
            sql,
            transition.trade_date,
            transition.subject_key,
            transition.theme_name,
            transition.from_state,
            transition.to_state,
            transition.transition_type,
            transition.from_score,
            transition.to_score,
            transition.confidence,
            json.dumps(transition.trigger_flags, ensure_ascii=False),
            json.dumps(transition.evidence_json, ensure_ascii=False),
            self.RULE_VERSION,
        )

    def _as_list(self, value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return []

    def _as_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

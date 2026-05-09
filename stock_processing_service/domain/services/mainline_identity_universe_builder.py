"""MainlineIdentityUniverseBuilder — 主线身份候选 Universe 构建。

不扫全量 600+ subject，只评估：
  1. current confirmed（当前已确认主线）
  2. prior alive（存续主线，final_mainline_alive=true AND NOT fade_confirmed）
  3. hot rank top100（当日异动题材）
  4. abnormal theme（heat>=70 / |pct_chg|>=3 / event_count_3d>=1）
  5. new theme（当日首次出现）
  6. cluster related（同簇强相关题材）

输出: mainline_identity_candidate_universe
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class IdentityUniverseRow:
    trade_date: date
    subject_key: str
    theme_name: str = ""
    universe_source: str = ""        # confirmed / prior_alive / hot_rank / abnormal / new_theme / cluster
    universe_reason: str = ""
    candidate_type: str = ""         # confirmed / alive / hot / abnormal / new / cluster
    priority_score: float = 0.0
    prior_identity_status: str = ""
    prior_cycle_state: str = ""
    prior_final_mainline_alive: bool = False
    is_current_confirmed: bool = False
    is_prior_alive: bool = False
    is_abnormal_theme: bool = False
    is_new_theme: bool = False
    is_hot_rank_theme: bool = False
    is_event_burst_theme: bool = False
    is_cluster_related: bool = False


class MainlineIdentityUniverseBuilder:
    """构建主线身份候选 Universe。

    输入来自多个 read_port 查询，输出为去重后的 IdentityUniverseRow 列表。
    """

    MAX_HOT_RANK = 100
    ABNORMAL_HEAT_MIN = 70
    ABNORMAL_PCT_CHG_MIN = 3.0

    def __init__(self, read_port: Any) -> None:
        self._read = read_port

    async def build(self, trade_date: date) -> list[IdentityUniverseRow]:
        """构建当日主线身份候选 Universe。"""
        rows: dict[str, IdentityUniverseRow] = {}
        self.source_errors: dict[str, str] = {}

        # ── 1. current confirmed (P0: fail-fast on read error) ──
        await self._add_confirmed(rows, trade_date)

        # ── 2. prior alive (P0: fail-fast) ──
        await self._add_prior_alive(rows, trade_date)

        # ── 3. hot rank top100 (P0: warn but continue) ──
        await self._add_hot_rank(rows, trade_date)

        # ── 4. abnormal themes (P1: warn, don't block) ──
        await self._add_abnormal(rows, trade_date)

        # ── 5. new themes (P1: warn, don't block) ──
        await self._add_new_themes(rows, trade_date)

        # ── 6. cluster related (P1: warn, don't block) ──
        await self._add_cluster_related(rows, trade_date)

        return sorted(rows.values(), key=lambda r: r.priority_score, reverse=True)

    async def _add_confirmed(self, rows: dict, trade_date: date) -> None:
        try:
            id_rows = await self._read.get_mainline_identity_by_subject_keys([], trade_date)
            for r in (id_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if not sk or sk in rows:
                    continue
                if bool(r.get("is_main_theme")) and str(r.get("identity_status") or "") == "confirmed":
                    rows[sk] = IdentityUniverseRow(
                        trade_date=trade_date, subject_key=sk,
                        theme_name=str(r.get("theme_name") or sk),
                        universe_source="confirmed",
                        candidate_type="confirmed",
                        priority_score=100.0,
                        prior_identity_status="confirmed",
                        is_current_confirmed=True,
                    )
        except Exception as e:
            self.source_errors["confirmed"] = str(e)

    async def _add_prior_alive(self, rows: dict, trade_date: date) -> None:
        try:
            cyc_rows = await self._read.get_mainline_cycle_by_subject_keys([], trade_date)
            for r in (cyc_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if not sk or sk in rows:
                    continue
                if bool(r.get("final_mainline_alive")) and not bool(r.get("fade_confirmed")):
                    rows[sk] = IdentityUniverseRow(
                        trade_date=trade_date, subject_key=sk,
                        theme_name=str(r.get("theme_name") or sk),
                        universe_source="prior_alive",
                        candidate_type="alive",
                        priority_score=90.0,
                        prior_cycle_state=str(r.get("final_cycle_state") or ""),
                        prior_final_mainline_alive=True,
                        is_prior_alive=True,
                    )
        except Exception as e:
            self.source_errors["prior_alive"] = str(e)

    async def _add_hot_rank(self, rows: dict, trade_date: date) -> None:
        source_name = "hot_rank"
        try:
            rank_rows = await self._read.get_subject_rank_daily(trade_date, limit=self.MAX_HOT_RANK)
            for r in (rank_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if not sk:
                    continue
                heat = float(r.get("heat") or 0)
                pct = abs(float(r.get("pct_chg") or 0))
                existing = rows.get(sk)
                if existing:
                    # Upgrade priority if from hot rank
                    if existing.priority_score < 70.0:
                        existing.priority_score = 70.0
                        existing.is_hot_rank_theme = True
                    continue
                rows[sk] = IdentityUniverseRow(
                    trade_date=trade_date, subject_key=sk,
                    theme_name=str(r.get("subject_name") or sk),
                    universe_source="hot_rank",
                    candidate_type="hot",
                    priority_score=min(heat, 70.0),
                    is_hot_rank_theme=True,
                    is_abnormal_theme=(heat >= self.ABNORMAL_HEAT_MIN or pct >= self.ABNORMAL_PCT_CHG_MIN),
                )
        except Exception as e:
            self.source_errors[source_name] = str(e)

    async def _add_abnormal(self, rows: dict, trade_date: date) -> None:
        """异动题材：event_count_3d >= 1 或 heat jump 的 subject。"""
        source_name = "abnormal"
        try:
            evidence_rows = await self._read.get_subject_cycle_evidence_daily(trade_date)
            for r in (evidence_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if not sk:
                    continue
                event_count = int(r.get("event_count_3d") or 0)
                if event_count >= 1:
                    existing = rows.get(sk)
                    if existing:
                        existing.is_event_burst_theme = True
                        if existing.priority_score < 80.0:
                            existing.priority_score = 80.0
                        continue
                    rows[sk] = IdentityUniverseRow(
                        trade_date=trade_date, subject_key=sk,
                        theme_name=str(r.get("theme_name") or sk),
                        universe_source="abnormal",
                        candidate_type="abnormal",
                        priority_score=80.0,
                        is_abnormal_theme=True,
                        is_event_burst_theme=True,
                    )
        except Exception as e:
            self.source_errors[source_name] = str(e)

    async def _add_new_themes(self, rows: dict, trade_date: date) -> None:
        """新题材：从 subject_rank_daily 中首次出现的 subject。"""
        source_name = "new_theme"
        try:
            new_rows = await self._read.get_new_subject_rank_entries(trade_date)
            for r in (new_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if not sk or sk in rows:
                    continue
                rows[sk] = IdentityUniverseRow(
                    trade_date=trade_date, subject_key=sk,
                    theme_name=str(r.get("subject_name") or sk),
                    universe_source="new_theme",
                    candidate_type="new",
                    priority_score=60.0,
                    is_new_theme=True,
                )
        except Exception as e:
            self.source_errors[source_name] = str(e)

    async def _add_cluster_related(self, rows: dict, trade_date: date) -> None:
        """同簇强相关题材：从已确认主线的簇中拉入相关题材。"""
        source_name = "cluster"
        confirmed_sks = {sk for sk, r in rows.items() if r.is_current_confirmed or r.is_prior_alive}
        if not confirmed_sks:
            return
        try:
            cluster_rows = await self._read.get_cluster_related_subjects(list(confirmed_sks), trade_date)
            for r in (cluster_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if not sk or sk in rows:
                    continue
                rows[sk] = IdentityUniverseRow(
                    trade_date=trade_date, subject_key=sk,
                    theme_name=str(r.get("subject_name") or sk),
                    universe_source="cluster",
                    candidate_type="cluster",
                    priority_score=50.0,
                    is_cluster_related=True,
                )
        except Exception as e:
            self.source_errors[source_name] = str(e)

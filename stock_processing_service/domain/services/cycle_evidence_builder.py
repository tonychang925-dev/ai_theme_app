from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import (
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectStockPoolDTO,
)


@dataclass(frozen=True)
class CycleEvidence:
    trade_date: date
    stock_id: str
    subject_key: str
    subject_name: str
    close_price: Decimal
    pct_chg: Decimal
    previous_state: str

    # Core score factors aligned with legacy v2 semantics.
    event_score: Decimal
    continuity_score: Decimal
    leader_score: Decimal
    relay_score: Decimal
    board_score: Decimal
    support_score: Decimal
    support_refs: list[str] = field(default_factory=list)

    # ── 旧链 6 维证据字段（等价于 theme_cycle_judgement_service_v2 judge() 输入）──
    # 这些是 per-subject 维度的原始证据，不是从6个score反推的
    leader_breakdown_flag: bool = False         # Leader层：龙头破位标志
    red_ratio: Decimal = Decimal("0")           # Board层：红盘比 (0-1)，真实板块数据
    big_drop_ratio: Decimal = Decimal("0")      # Board层：大幅下跌比 (0-1)
    limit_down_count: int = 0                   # Board层：跌停数
    front_row_survival_ratio: Decimal = Decimal("0")  # Leader层：前排存活率 (0-1)
    break_start_pivot: bool = False             # Kline层：支撑破位（旧链 support_break 核心条件）
    theme_support_score: Decimal = Decimal("0") # Kline层：题材支撑评分（用于 old chain support_break 判定）
    strong_event_count_7d: int = 0              # Event层：7日强事件数

    score_flags: dict[str, bool] = field(default_factory=dict)
    missing_flags: dict[str, bool] = field(default_factory=dict)


class CycleEvidenceBuilder:
    def build_evidences(
        self,
        bars: list[StockBarDTO],
        pool_rows: list[SubjectStockPoolDTO],
        context_rows: list[SubjectContextDTO],
        prior_rows: list[PriorSnapshotDTO],
    ) -> list[CycleEvidence]:
        context_by_subject = {row.subject_key: row for row in context_rows}
        prior_by_stock = {row.stock_id: row for row in prior_rows}
        bars_by_stock = {bar.stock_id: bar for bar in bars}
        subject_pool_rows: dict[str, list[SubjectStockPoolDTO]] = {}
        for row in pool_rows:
            subject_pool_rows.setdefault(row.subject_key, []).append(row)

        evidences: list[CycleEvidence] = []
        for pool_row in pool_rows:
            stock_bar = bars_by_stock.get(pool_row.stock_id)
            if stock_bar is None:
                evidences.append(
                    CycleEvidence(
                        trade_date=pool_row.trade_date,
                        stock_id=pool_row.stock_id,
                        subject_key=pool_row.subject_key,
                        subject_name=pool_row.subject_name,
                        close_price=Decimal("0"),
                        pct_chg=Decimal("0"),
                        previous_state="unknown",
                        event_score=Decimal("0"),
                        continuity_score=Decimal("0"),
                        leader_score=Decimal("0"),
                        relay_score=Decimal("0"),
                        board_score=Decimal("0"),
                        support_score=Decimal("0"),
                        support_refs=[],
                        score_flags={
                            "computed": False,
                            "event_score_missing": True,
                            "leader_score_missing": True,
                            "relay_score_missing": True,
                            "board_score_missing": True,
                            "support_score_missing": True,
                        },
                        missing_flags={
                            "bar_missing": True,
                            "context_missing": context_by_subject.get(pool_row.subject_key) is None,
                            "prior_missing": prior_by_stock.get(pool_row.stock_id) is None,
                            "subject_pool_missing": False,
                        },
                    )
                )
                continue

            context = context_by_subject.get(pool_row.subject_key)
            prior = prior_by_stock.get(pool_row.stock_id)

            prev_state = self._normalize_previous_state(prior.payload if prior else None)

            tags = (context.theme_context_tags if context else []) or []
            rank = pool_row.pool_rank if pool_row.pool_rank is not None else 999
            rank_score = Decimal("100") / Decimal(str(max(rank, 1)))
            pct = stock_bar.pct_chg
            subject_rows = subject_pool_rows.get(pool_row.subject_key, [])
            subject_bars = [bars_by_stock.get(r.stock_id) for r in subject_rows if bars_by_stock.get(r.stock_id) is not None]
            subject_count = len(subject_rows)
            positive_count = sum(1 for b in subject_bars if b.pct_chg > Decimal("0"))
            limit_like_count = sum(
                1 for b in subject_bars if b.pct_chg >= Decimal("9.5") or b.close_price >= b.limit_up_price
            )
            diffusion_ratio = (Decimal(str(positive_count)) / Decimal(str(max(subject_count, 1)))) * Decimal("100")
            limit_ratio = (Decimal(str(limit_like_count)) / Decimal(str(max(subject_count, 1)))) * Decimal("100")
            avg_pct = (
                sum((b.pct_chg for b in subject_bars), start=Decimal("0"))
                / Decimal(str(max(len(subject_bars), 1)))
            )

            metadata = pool_row.metadata or {}
            context_meta = (context.metadata or {}) if context else {}
            tag_event_raw = (
                metadata.get("event_score")
                or context_meta.get("event_score")
                or context_meta.get("event_continuity_score")
                or 0
            )
            try:
                tag_event_score = Decimal(str(tag_event_raw))
            except Exception:
                tag_event_score = Decimal("0")
            event_from_context = Decimal(str(min(len(tags) * 14, 70)))
            event_from_diffusion = max(Decimal("0"), min(Decimal("30"), diffusion_ratio * Decimal("0.3")))
            event_score = max(Decimal("0"), min(Decimal("100"), tag_event_score + event_from_context + event_from_diffusion))
            continuity_score = Decimal("45")
            if prev_state in {"start", "fermentation", "acceleration", "divergence", "repair"}:
                continuity_score = Decimal("78")
            elif prev_state in {"fade_watch", "fade_confirmed"}:
                continuity_score = Decimal("58")
            leader_live_bonus = Decimal("15") if rank <= 2 and pct > Decimal("0") else Decimal("0")
            leader_score = max(
                Decimal("0"),
                min(
                    Decimal("100"),
                    rank_score * Decimal("0.35")
                    + max(Decimal("0"), pct * Decimal("4.2") + Decimal("40")) * Decimal("0.35")
                    + limit_ratio * Decimal("0.15")
                    + leader_live_bonus,
                ),
            )
            relay_score = max(
                Decimal("0"),
                min(
                    Decimal("100"),
                    diffusion_ratio * Decimal("0.45")
                    + max(Decimal("0"), avg_pct * Decimal("3") + Decimal("35")) * Decimal("0.30")
                    + max(Decimal("0"), pct * Decimal("2.2") + Decimal("20")) * Decimal("0.25"),
                ),
            )
            board_score = max(
                Decimal("0"),
                min(
                    Decimal("100"),
                    Decimal(str(len(tags) * 10))
                    + diffusion_ratio * Decimal("0.35")
                    + limit_ratio * Decimal("0.35"),
                ),
            )
            support_score = max(
                Decimal("0"),
                min(
                    Decimal("100"),
                    rank_score * Decimal("0.40")
                    + continuity_score * Decimal("0.30")
                    + max(Decimal("0"), Decimal("100") - abs(pct) * Decimal("7")) * Decimal("0.30"),
                ),
            )

            # External evidence overrides: prefer explicit upstream evidence scores when present.
            external_event = self._read_external_score_from_sources(
                [metadata, context_meta],
                ["event_score", "event_continuity_score"],
            )
            external_leader = self._read_external_score_from_sources(
                [metadata, context_meta],
                ["leader_score", "leader_alive_score", "front_rank_alive_score"],
            )
            external_relay = self._read_external_score_from_sources(
                [metadata, context_meta],
                ["relay_score", "relay_strength_score"],
            )
            external_board = self._read_external_score_from_sources(
                [metadata, context_meta],
                ["board_score", "diffusion_score", "board_diffusion_score"],
            )
            external_support = self._read_external_score_from_sources(
                [metadata, context_meta],
                ["support_score"],
            )
            if external_event is not None:
                event_score = external_event
            if external_leader is not None:
                leader_score = external_leader
            if external_relay is not None:
                relay_score = external_relay
            if external_board is not None:
                board_score = external_board
            if external_support is not None:
                support_score = external_support

            support_refs: list[str] = []
            external_support_refs = metadata.get("support_refs")
            if isinstance(external_support_refs, list):
                support_refs.extend([str(x) for x in external_support_refs if str(x).strip()])
            if rank <= 3:
                support_refs.append("pool_rank_top3")
            if continuity_score >= Decimal("70"):
                support_refs.append("prior_state_continuity")
            if pct >= Decimal("0"):
                support_refs.append("non_negative_pct")
            if diffusion_ratio >= Decimal("45"):
                support_refs.append("subject_diffusion_positive")
            support_refs.append(f"subject_size={subject_count}")
            support_refs.append(f"subject_positive_ratio={diffusion_ratio:.2f}")
            support_refs.append(f"subject_limit_ratio={limit_ratio:.2f}")
            if not support_refs:
                support_refs.append("support_evidence_missing")

            # ── 旧链等价 6 维证据字段 ──
            # red_ratio: 板块红盘比 = 正涨幅股票占比。优先从 metadata 取，否则从 subject bars 推算
            if "red_ratio" in metadata or "red_ratio" in context_meta:
                red_ratio_val = Decimal(str(metadata.get("red_ratio") or context_meta.get("red_ratio") or "0"))
            else:
                red_ratio_val = diffusion_ratio / Decimal("100")
            # big_drop_ratio: 大幅下跌比。优先 metadata，否则从 bars 推算
            if "big_drop_ratio" in metadata or "big_drop_ratio" in context_meta:
                big_drop_ratio_val = Decimal(str(metadata.get("big_drop_ratio") or context_meta.get("big_drop_ratio") or "0"))
            else:
                big_drop_count = sum(1 for b in subject_bars if b.pct_chg <= Decimal("-5"))
                big_drop_ratio_val = Decimal(str(big_drop_count)) / Decimal(str(max(subject_count, 1)))
            # limit_down_count: 跌停数。优先 metadata，否则从 bars 推算
            if "limit_down_count" in metadata or "limit_down_count" in context_meta:
                limit_down_count_val = int(
                    metadata.get("limit_down_count")
                    or context_meta.get("limit_down_count")
                    or 0
                )
            else:
                limit_down_count_val = sum(1 for b in subject_bars if b.close_price <= b.limit_down_price and b.limit_down_price > Decimal("0"))
            # leader_breakdown_flag: 龙头破位
            leader_bd = bool(metadata.get("leader_breakdown_flag") or context_meta.get("leader_breakdown_flag") or False)
            # front_row_survival_ratio: 前排存活率
            front_survival = Decimal(str(metadata.get("front_row_survival_ratio") or context_meta.get("front_row_survival_ratio") or "1.0"))
            # break_start_pivot: 支撑破位
            break_pivot = bool(metadata.get("break_start_pivot") or context_meta.get("break_start_pivot") or False)
            # theme_support_score: K线支撑分
            if "theme_support_score" in metadata or "theme_support_score" in context_meta:
                theme_support_score_val = Decimal(str(metadata.get("theme_support_score") or context_meta.get("theme_support_score") or "0"))
            else:
                theme_support_score_val = support_score
            # strong_event_count_7d
            strong_evt = int(metadata.get("strong_event_count_7d") or context_meta.get("strong_event_count_7d") or 0)

            evidences.append(
                CycleEvidence(
                    trade_date=stock_bar.trade_date,
                    stock_id=pool_row.stock_id,
                    subject_key=pool_row.subject_key,
                    subject_name=pool_row.subject_name,
                    close_price=stock_bar.close_price,
                    pct_chg=stock_bar.pct_chg,
                    previous_state=prev_state,
                    event_score=event_score,
                    continuity_score=continuity_score,
                    leader_score=leader_score,
                    relay_score=relay_score,
                    board_score=board_score,
                    support_score=support_score,
                    support_refs=support_refs,
                    leader_breakdown_flag=leader_bd,
                    red_ratio=red_ratio_val,
                    big_drop_ratio=big_drop_ratio_val,
                    limit_down_count=limit_down_count_val,
                    front_row_survival_ratio=front_survival,
                    break_start_pivot=break_pivot,
                    theme_support_score=theme_support_score_val,
                    strong_event_count_7d=strong_evt,
                    score_flags={
                        "computed": True,
                        "event_score_missing": (not bool(tags)) and tag_event_score <= Decimal("0"),
                        "leader_score_missing": subject_count <= 1,
                        "relay_score_missing": subject_count <= 1,
                        "board_score_missing": subject_count <= 1 and len(tags) <= 1,
                        "support_score_missing": False,
                        "event_score_external": external_event is not None,
                        "leader_score_external": external_leader is not None,
                        "relay_score_external": external_relay is not None,
                        "board_score_external": external_board is not None,
                        "support_score_external": external_support is not None,
                    },
                    missing_flags={
                        "bar_missing": False,
                        "context_missing": context is None,
                        "prior_missing": prior is None,
                        "subject_pool_missing": False,
                    },
                )
            )
        return evidences

    def _normalize_previous_state(self, payload: dict[str, object] | None) -> str:
        if not payload:
            return "unknown"
        candidates = [
            payload.get("final_cycle_state"),
            payload.get("cycle_state"),
            payload.get("mainline_state"),
            payload.get("state"),
        ]
        raw = next((str(v).strip().lower() for v in candidates if str(v or "").strip()), "unknown")
        mapping = {
            "mainline_active": "acceleration",
            "active": "acceleration",
            "weakening": "fade_watch",
            "observe": "start",
            "observed": "start",
        }
        return mapping.get(raw, raw)

    def _read_external_score(self, metadata: dict[str, Any], key: str) -> Decimal | None:
        if key not in metadata:
            return None
        try:
            value = Decimal(str(metadata.get(key)))
        except Exception:
            return None
        return max(Decimal("0"), min(Decimal("100"), value))

    def _read_external_score_from_sources(
        self,
        sources: list[dict[str, Any]],
        keys: list[str],
    ) -> Decimal | None:
        for source in sources:
            for key in keys:
                value = self._read_external_score(source, key)
                if value is not None:
                    return value
        return None

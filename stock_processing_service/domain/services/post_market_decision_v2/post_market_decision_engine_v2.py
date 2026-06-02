"""PR-12: PostMarketDecisionEngineV2.

Automates Layer C (strong stock pool) and Layer D1 (weak-to-strong) on top of
confirmed mainlines + lifecycle + market_regime.

Does NOT re-implement stock picking — reuses:
  - StrongStockTrackingService (Layer C)
  - W2SCandidateService (Layer D1)

Key constraint: D1 candidates must come from Layer C, not full market scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    StrongStockPoolItem, WeakToStrongD1Item, NextDayFocusStock, PostMarketDecisionV2,
)


@dataclass
class PostMarketDecisionEngineV2:
    """Orchestrate Layer C/D1 automation on the new architecture."""

    @staticmethod
    def _dedupe_key(row: dict[str, Any]) -> str:
        """Build a stable identity for rows that may lack stock_id in legacy inputs."""
        mainline_id = str(row.get("mainline_id") or "").strip()
        subject_key = str(row.get("subject_key") or row.get("theme_key") or "").strip()
        stock_id = str(row.get("stock_id") or "").strip()
        if stock_id:
            return "|".join(["stock_id", mainline_id or "--", subject_key or "--", stock_id])
        stock_name = str(row.get("stock_name") or "").strip()
        relay_role = str(row.get("relay_role") or "").strip()
        return "|".join(
            [
                "fallback",
                mainline_id or "--",
                subject_key or "--",
                stock_name or "--",
                relay_role or "--",
            ]
        )

    @classmethod
    def _dedupe_rows(cls, rows: list[dict[str, Any]], *, score_key: str = "watch_score") -> list[dict[str, Any]]:
        """Keep the highest-scoring row for each stable identity."""
        best: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = cls._dedupe_key(row)
            score = float(row.get(score_key) or 0)
            if key not in best or score > float(best[key].get(score_key) or 0):
                best[key] = row
        return list(best.values())

    def evaluate(
        self,
        *,
        trade_date: str = "",
        confirmed_mainlines: list[dict[str, Any]] | None = None,
        mainline_lifecycle: list[dict[str, Any]] | None = None,
        market_regime: dict[str, Any] | None = None,
        stock_pool_rows: list[dict[str, Any]] | None = None,
    ) -> PostMarketDecisionV2:
        mainlines = confirmed_mainlines or []
        lifecycle = mainline_lifecycle or []
        regime = market_regime or {}
        pool_rows = stock_pool_rows or []

        allow_trade = bool(regime.get("allow_trade", False))
        trade_mode = str(regime.get("trade_mode", "no_trade"))
        position_limit = float(regime.get("position_limit", 0))

        # ── 1. Filter stock pool to confirmed mainlines only ──
        # Expand canonical + related + branch subject_keys consistently
        # with ActiveMainlineUniverseBuilder.
        mainline_sks: set[str] = set()
        mainline_ids: dict[str, str] = {}  # sk → mainline_id

        def _safe_json_list(val: Any) -> list:
            if isinstance(val, str):
                import json
                try: return json.loads(val)
                except: return []
            return val if isinstance(val, list) else []

        for ml in mainlines:
            csk = str(ml.get("canonical_subject_key") or "")
            if csk:
                mainline_sks.add(csk)
                mainline_ids[csk] = str(ml.get("mainline_id") or "")
            # related
            for rsk in _safe_json_list(ml.get("related_subject_keys_json")):
                mainline_sks.add(str(rsk))
                mainline_ids[str(rsk)] = str(ml.get("mainline_id") or "")
            # branch — was missing before; now consistent with ActiveMainlineUniverseBuilder
            for bsk in _safe_json_list(ml.get("branch_subject_keys_json")):
                mainline_sks.add(str(bsk))
                mainline_ids[str(bsk)] = str(ml.get("mainline_id") or "")

        # Filter pool to mainline subjects only
        filtered_pool = [r for r in pool_rows if str(r.get("subject_key") or r.get("theme_key") or "") in mainline_sks]
        filtered_pool = self._dedupe_rows(filtered_pool)

        # ── 2. Build Layer C strong_stock_pool ──
        strong_pool: list[StrongStockPoolItem] = []
        for row in filtered_pool:
            sk = str(row.get("subject_key") or row.get("theme_key") or "")
            ws = float(row.get("watch_score") or 0)
            entry = str(row.get("pool_entry_type") or "")
            if entry not in {"formal", "observe_only", "reject", ""}:
                entry = "observe_only"
            strong_pool.append(StrongStockPoolItem(
                trade_date=trade_date,
                mainline_id=mainline_ids.get(sk, ""),
                subject_key=sk,
                theme_name=str(row.get("theme_name") or row.get("subject_name") or ""),
                stock_id=str(row.get("stock_id") or ""),
                stock_name=str(row.get("stock_name") or ""),
                watch_score=ws, watch_priority=float(row.get("watch_priority", ws)),
                watch_status=str(row.get("watch_status") or "active"),
                pool_entry_type=entry,
                strong_grade=str(row.get("strong_grade") or "REJECT"),
                relay_role=str(row.get("relay_role") or ""),
                source_tag=str(row.get("source_tag") or ""),
                cycle_state=str(row.get("cycle_state") or ""),
                mainline_strength_score=float(row.get("mainline_strength_score") or 0),
                support_type=row.get("support_type"),
                support_level=float(row.get("support_level") or 0) if row.get("support_level") else None,
                support_score=float(row.get("support_score") or 0),
                evidence=dict(row.get("evidence") or {}),
                labels=dict(row.get("labels") or {}),
                diagnostics={"source": "existing_strong_watch_pool"},
            ))

        # ── 3. Build Layer D1 from Layer C ──
        ULTRA_SHORT_ROLES = {"dragon", "leader", "sub_dragon", "dragon2", "card_position_candidate", "switch_leader"}
        CORE_ROLES = ULTRA_SHORT_ROLES | {"core", "trend_core", "assistant"}

        d1_candidates: list[WeakToStrongD1Item] = []
        for item in strong_pool:
            if item.pool_entry_type == "reject":
                continue
            ws = item.watch_score
            ss = item.support_score
            # Fallback scoring (will be replaced by W2SCandidateService in follow-up)
            score = round(ws * 0.6 + ss * 0.4, 1)
            d1_source = "fallback_score"

            role = str(item.relay_role or "").lower().replace(" ", "_")

            # market_regime constraint
            if not allow_trade:
                level = "observe_only"
                buy_cond = ["等待市场环境改善"]
                invalid = ["大盘持续弱势", "跌停家数未减少"]
                d1_source = "blocked_by_market_regime"
            elif trade_mode == "ultra_short_only":
                if role not in ULTRA_SHORT_ROLES:
                    continue  # skip non-core in ultra_short
                level = "formal" if score >= 70 else "observe_only"
                buy_cond = ["竞价确认", "龙头板块不弱", "核心前排才有机会"]
                invalid = ["低开低走", "跌破支撑", "龙头破位"]
            elif trade_mode == "mainline_core_only":
                if role not in CORE_ROLES:
                    continue
                level = "formal" if score >= 68 else "observe_only"
                buy_cond = ["主线核心承接", "分歧修复确认"]
                invalid = ["非主线走弱", "破位下行"]
            else:
                level = "formal" if score >= 65 else "observe_only"
                buy_cond = ["满足承接条件", "板块前排不弱"]
                invalid = ["破位", "量能不济"]

            d1_candidates.append(WeakToStrongD1Item(
                trade_date=trade_date,
                next_trade_date="T+1",
                stock_id=item.stock_id, stock_name=item.stock_name,
                mainline_id=item.mainline_id, subject_key=item.subject_key,
                theme_name=item.theme_name,
                candidate_stage="D1", candidate_level=level,
                candidate_score=score,
                support_score=ss, momentum_score=ws * 0.5,
                weak_type="pullback" if ss > 70 else "unknown",
                support_type=item.support_type or "unknown",
                gap_hit=ss > 75,
                repair_or_takeover_score=score,
                weakness_valid_score=ws * 0.7,
                buy_condition=buy_cond, invalid_condition=invalid,
                d2_required=True, d2_status="pending",
                evidence=item.evidence,
                diagnostics={"source": "Layer_C_strong_pool", "scoring_method": d1_source,
                             "blocked_by_market_regime": not allow_trade},
            ))

        # Dedup D1 / focus for legacy rows that may leak repeated identities.
        if d1_candidates:
            deduped_d1: dict[str, WeakToStrongD1Item] = {}
            for item in d1_candidates:
                key = self._dedupe_key(item.to_dict())
                if key not in deduped_d1 or item.candidate_score > deduped_d1[key].candidate_score:
                    deduped_d1[key] = item
            d1_candidates = list(deduped_d1.values())

        # Sort D1 by score desc
        d1_candidates.sort(key=lambda x: x.candidate_score, reverse=True)

        # Top N cap per trade mode
        _d1_limit = 5 if trade_mode == "ultra_short_only" else (10 if trade_mode == "mainline_core_only" else 20)
        d1_candidates = d1_candidates[:_d1_limit]

        # ── 4. Build next_day_focus_stocks ──
        focus_stocks: list[NextDayFocusStock] = []
        for d1 in d1_candidates:
            if d1.candidate_level != "formal":
                continue
            focus_stocks.append(NextDayFocusStock(
                trade_date=trade_date, stock_id=d1.stock_id, stock_name=d1.stock_name,
                category="重点观察", priority=len(focus_stocks) + 1,
                mainline_id=d1.mainline_id, subject_key=d1.subject_key,
                theme_name=d1.theme_name,
                pool_entry_type="formal", candidate_level=d1.candidate_level,
                watch_score=0, candidate_score=d1.candidate_score,
                buy_condition=d1.buy_condition, invalid_condition=d1.invalid_condition,
                d2_required=True, d2_status="pending",
                suggested_position=min(position_limit, 0.3) if position_limit > 0 else 0,
            ))

        if focus_stocks:
            deduped_focus: dict[str, NextDayFocusStock] = {}
            for item in focus_stocks:
                key = self._dedupe_key(item.to_dict())
                if key not in deduped_focus or item.candidate_score > deduped_focus[key].candidate_score:
                    deduped_focus[key] = item
            focus_stocks = list(deduped_focus.values())

        # ── 5. Trading principle summary ──
        tp = {
            "allow_trade": allow_trade, "trade_mode": trade_mode,
            "position_limit": position_limit,
            "confirmed_mainline_count": len(mainlines),
            "strong_pool_count": len(strong_pool),
            "d1_candidate_count": len(d1_candidates),
            "focus_stock_count": len(focus_stocks),
        }

        # ── Diagnostics: expose active universe vs Layer C coverage gap ──
        all_pool_sks: set[str] = {str(r.get("subject_key") or r.get("theme_key") or "") for r in pool_rows}
        filtered_sks: set[str] = {str(r.get("subject_key") or r.get("theme_key") or "") for r in filtered_pool}
        missing_sks = all_pool_sks - mainline_sks

        return PostMarketDecisionV2(
            trade_date=trade_date,
            trading_permission=tp,
            strong_stock_pool_reviews=[r.to_dict() for r in strong_pool],
            weak_to_strong_d1_reviews=[r.to_dict() for r in d1_candidates],
            next_day_focus_stocks=[r.to_dict() for r in focus_stocks],
            trading_principle_v2=tp,
            diagnostics={
                "confirmed_mainline_source": "registry",
                "confirmed_count": len(mainlines),
                "active_mainline_count": len(mainlines),
                "active_subject_key_count": len(mainline_sks),
                "total_pool_rows": len(pool_rows),
                "mainline_filtered_rows": len(filtered_pool),
                "strong_pool_count": len(strong_pool),
                "d1_count": len(d1_candidates),
                "d1_top_n_limit": _d1_limit, "d1_top_n_applied": True,
                "focus_count": len(focus_stocks),
                "layer_c_subject_keys": sorted(all_pool_sks),
                "mainline_filtered_subject_keys": sorted(filtered_sks),
                "missing_registry_subject_keys": sorted(missing_sks),
            },
        )

"""PR-12: PostMarketDecisionEngineV2.

Layer C post-market view assembler.

Layer C rows are provided by the canonical strong stock watch read-model.
Confirmed mainlines are used only as annotations/diagnostics.
This module does not generate Layer C, does not filter Layer C by mainline,
and does not generate Layer D1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import StrongStockPoolItem, PostMarketDecisionV2


@dataclass
class PostMarketDecisionEngineV2:
    """Assemble Layer C post-market display facts."""

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
                "missing_stock_id_key",
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

        # ── 1. Build confirmed mainline key set for annotations only ──
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

        # Keep the full Layer C pool. mainline_sks is used only for
        # diagnostics / annotation so independent leaders are not lost.
        layer_c_dedup_rows = self._dedupe_rows(pool_rows)

        # Dedup by stock_id (keep highest watch_score) — 7-day union can have duplicates
        best: dict[str, dict[str, Any]] = {}
        for r in layer_c_dedup_rows:
            sid = str(r.get("stock_id") or "")
            if not sid: continue
            ws = float(r.get("watch_score") or 0)
            if sid not in best or ws > float(best[sid].get("watch_score") or 0):
                best[sid] = r
        layer_c_dedup_rows = list(best.values())

        # ── 2. Build Layer C strong_stock_pool ──
        strong_pool: list[StrongStockPoolItem] = []
        for row in layer_c_dedup_rows:
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
                diagnostics={
                    "source": "existing_strong_watch_pool",
                    "mainline_binding_status": "confirmed" if sk in mainline_sks else "not_confirmed",
                },
            ))

        # ── 5. Trading principle summary ──
        tp = {
            "allow_trade": allow_trade, "trade_mode": trade_mode,
            "position_limit": position_limit,
            "confirmed_mainline_count": len(mainlines),
            "strong_pool_count": len(strong_pool),
            "d1_candidate_count": 0,
            "focus_stock_count": 0,
        }

        # ── Diagnostics: expose active universe vs Layer C coverage gap ──
        all_pool_sks: set[str] = {str(r.get("subject_key") or r.get("theme_key") or "") for r in pool_rows}
        layer_c_dedup_sks: set[str] = {str(r.get("subject_key") or r.get("theme_key") or "") for r in layer_c_dedup_rows}
        missing_sks = all_pool_sks - mainline_sks

        return PostMarketDecisionV2(
            trade_date=trade_date,
            trading_permission=tp,
            strong_stock_pool_reviews=[r.to_dict() for r in strong_pool],
            weak_to_strong_d1_reviews=[],
            next_day_focus_stocks=[],
            trading_principle_v2=tp,
            diagnostics={
                "confirmed_mainline_source": "registry",
                "confirmed_count": len(mainlines),
                "active_mainline_count": len(mainlines),
                "active_subject_key_count": len(mainline_sks),
                "layer_c_input_rows": len(pool_rows),
                "mainline_filter_applied": False,
                "layer_c_dedup_rows": len(layer_c_dedup_rows),
                "strong_pool_count": len(strong_pool),
                "d1_count": 0,
                "d1_top_n_limit": 0,
                "d1_top_n_applied": False,
                "focus_count": 0,
                "layer_c_input_subject_keys": sorted(all_pool_sks),
                "layer_c_dedup_subject_keys": sorted(layer_c_dedup_sks),
                "layer_c_not_bound_to_confirmed_mainline_subject_keys": sorted(missing_sks),
                "mainline_binding_is_annotation_only": True,
                "layer_c_input_rows_pre_filter": len(pool_rows),
                "layer_c_reject_rows": sum(
                    1 for r in layer_c_dedup_rows
                    if (r.pool_entry_type if hasattr(r, "pool_entry_type") else r.get("pool_entry_type")) == "reject"
                ),
            },
        )

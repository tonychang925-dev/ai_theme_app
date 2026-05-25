from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.ports.read_ports import StockReadPorts
from stock_processing_service.ports.write_ports import StockWritePorts


# ── P2-B-3: D1 候选竞价预期预填 ──

_AUCTION_EXPECTATIONS: dict[str, dict] = {
    "dragon_repair": {
        "expected_open_low": "1.0", "expected_open_high": "7.0",
        "expected_auction_pattern": "red_staircase,inverted_l_uphill",
        "need_last_minute_grab": True, "need_plate_follow": True,
        "min_carry_ratio": "0.5",
    },
    "subdragon_repair": {
        "expected_open_low": "0.0", "expected_open_high": "5.0",
        "expected_auction_pattern": "red_staircase,upward_hook",
        "need_last_minute_grab": True, "need_plate_follow": True,
        "min_carry_ratio": "0.4",
    },
    "bad_limit_repair": {
        "expected_open_low": "0.0", "expected_open_high": "5.0",
        "expected_auction_pattern": "red_staircase",
        "need_last_minute_grab": True, "need_plate_follow": False,
        "min_carry_ratio": "0.5",
    },
    "upper_shadow_repair": {
        "expected_open_low": "-1.0", "expected_open_high": "3.0",
        "expected_auction_pattern": "inverted_l_u_shape,u_recovery",
        "need_last_minute_grab": False, "need_plate_follow": True,
        "min_carry_ratio": "0.3",
    },
    "strong_trend_repair": {
        "expected_open_low": "-0.5", "expected_open_high": "3.0",
        "expected_auction_pattern": "step_up,tail_upturn",
        "need_last_minute_grab": False, "need_plate_follow": False,
        "min_carry_ratio": "0.3",
    },
    "generic_repair": {
        "expected_open_low": "-1.0", "expected_open_high": "5.0",
        "expected_auction_pattern": "",
        "need_last_minute_grab": False, "need_plate_follow": False,
        "min_carry_ratio": "0.2",
    },
}


def _build_auction_expectations(candidate_type: str, weak_type: str, is_leader: bool) -> dict:
    """根据 candidate_type 预填 D2 竞价预期字段。"""
    base = dict(_AUCTION_EXPECTATIONS.get(candidate_type, _AUCTION_EXPECTATIONS["generic_repair"]))

    # big_negative_line 需要更强的竞价确认
    if weak_type == "big_negative_line":
        base["min_carry_ratio"] = str(max(float(base.get("min_carry_ratio", "0.3")), 0.5))
        base["need_last_minute_grab"] = True
        if not base["expected_auction_pattern"]:
            base["expected_auction_pattern"] = "red_staircase,step_up"

    # is_leader 提升最低预期
    if is_leader:
        base["min_carry_ratio"] = str(min(float(base.get("min_carry_ratio", "0.3")) + 0.1, 0.6))

    return base


@dataclass(slots=True)
class BuildWeakToStrongCandidateUseCase:
    """Build Layer D1 weak-to-strong candidates from strong watch pool inputs."""

    read_ports: StockReadPorts
    write_ports: StockWritePorts

    async def execute(self, trade_date: date) -> BuildResult:
        d1_input_rows = await self.read_ports.get_w2s_candidate_inputs(trade_date)
        candidates = self.build_candidates(trade_date=trade_date, d1_input_rows=d1_input_rows)
        candidates = self._dedup_and_rank(candidates, limit=10)
        written = await self.write_ports.upsert_weak_to_strong_candidate_pool_rows(candidates) if candidates else 0

        diagnostics = self._diagnostics
        return BuildResult(
            name="build_weak_to_strong_candidate",
            trade_date=trade_date.isoformat(),
            affected_rows=written,
            status="ok",
            metrics={
                "d1_input_rows": d1_input_rows,
                "d1_candidates_for_pool": candidates,
                "d1_written": written,
                **diagnostics,
            },
        )

    def build_candidates(self, *, trade_date: date, d1_input_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        d1_candidates_for_pool: list[dict[str, Any]] = []
        self._diagnostics = {
            "d1_total_in": len(d1_input_rows),
            "d1_pass": 0,
            "d1_fail_pct_gate": 0,
            "d1_fail_history": 0,
            "d1_fail_gene": 0,
            "d1_fail_strong": 0,
            "d1_fail_support": 0,
        }

        for row in d1_input_rows:
            pct_chg = float(row.get("pct_chg") or 0)
            limit_up = bool(row.get("limit_up") or False)
            is_leader = bool(row.get("is_leader") or False)
            rank_order = int(row.get("rank_order") or 999)
            recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
            prior7_limitup_days = int(row.get("prior7_limitup_days") or 0)
            prior7_strong_days = int(row.get("prior7_strong_days") or 0)
            prev_day_pct = float(row.get("prev_day_pct_chg") or 0.0)
            prev_day_limit_up = bool(row.get("prev_day_limit_up") or False)
            fade_watch = bool(row.get("fade_watch") or False)
            fade_confirmed = bool(row.get("fade_confirmed") or False)
            mainline_strength_score = float(row.get("mainline_strength_score") or 0.0)
            watch_score = float(row.get("watch_score") or 0.0)
            watch_pool_entry_type = str(row.get("watch_pool_entry_type") or "observe_only")
            watch_labels = row.get("watch_labels_json") or {}
            if isinstance(watch_labels, str):
                watch_labels = json.loads(watch_labels) if watch_labels else {}
            strong_grade = str(watch_labels.get("strong_grade") or "").upper()
            support_type = str(watch_labels.get("support_type") or "")
            support_strength = float(watch_labels.get("support_score") or 0)

            # Weak-to-strong Stage1 requires the stock to be weak first.
            # Positive, limit-up, and micro-dip rows are strong-watch facts, not D1 repair candidates.
            if pct_chg > -1.0 or limit_up:
                self._diagnostics["d1_fail_pct_gate"] += 1
                continue
            strong_history = is_leader or prev_day_limit_up or recent_limit_up_count >= 1 or rank_order <= 5
            if not strong_history:
                self._diagnostics["d1_fail_history"] += 1
                continue
            if prior7_limitup_days < 1:
                self._diagnostics["d1_fail_gene"] += 1
                continue
            if prior7_strong_days < 1:
                self._diagnostics["d1_fail_strong"] += 1
                continue
            if support_type in {"", "none"} or support_strength < 45.0:
                self._diagnostics["d1_fail_support"] += 1
                continue
            self._diagnostics["d1_pass"] += 1

            if prev_day_limit_up and pct_chg < 0:
                weak_type = "bad_limit_up"
                weak_intensity = min(100.0, abs(pct_chg) * 12.0 + 20.0)
            elif pct_chg <= -5.0:
                weak_type = "big_negative_line"
                weak_intensity = min(100.0, abs(pct_chg) * 10.0)
            elif -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
                weak_type = "upper_shadow"
                weak_intensity = 55.0
            elif pct_chg <= -1.0:
                weak_type = "high_open_low_close"
                weak_intensity = min(100.0, abs(pct_chg) * 8.0 + 10.0)
            else:
                weak_type = "fake_break"
                weak_intensity = 40.0

            if pct_chg < -4.0:
                day_weak_score = 20.0
            elif pct_chg < -2.0:
                day_weak_score = 16.0
            elif pct_chg < -1.0:
                day_weak_score = 10.0
            else:
                day_weak_score = 6.0

            if prev_day_pct < -3.0:
                prev_day_weak_score = 10.0
            elif prev_day_pct < -1.5:
                prev_day_weak_score = 8.0
            elif prev_day_pct < 0:
                prev_day_weak_score = 5.0
            else:
                prev_day_weak_score = 0.0

            candidate_score = 45.0
            if is_leader:
                candidate_score += 18.0
            if limit_up:
                candidate_score += 10.0
            candidate_score += min(recent_limit_up_count * 4.0, 12.0)
            if rank_order <= 3:
                candidate_score += 8.0
            candidate_score += min(weak_intensity * 0.08, 8.0)
            candidate_score += min(support_strength * 0.1, 9.0)
            candidate_score += day_weak_score + prev_day_weak_score
            candidate_score += min(mainline_strength_score * 0.08, 8.0)
            if fade_watch:
                if mainline_strength_score >= 75.0:
                    candidate_score -= 4.0
                elif mainline_strength_score >= 60.0:
                    candidate_score -= 8.0
                else:
                    candidate_score -= 12.0

            strong_background = is_leader or recent_limit_up_count >= 2 or rank_order <= 3
            d1_pool_entry = "reject"
            if support_strength >= 45 and strong_background and day_weak_score >= 4:
                d1_pool_entry = "formal"
            elif support_strength >= 60 and day_weak_score >= 3:
                d1_pool_entry = "observe_only"
            if d1_pool_entry == "reject":
                continue

            candidate_score = max(0.0, min(candidate_score, 100.0))
            if is_leader and recent_limit_up_count >= 3:
                candidate_type = "dragon_repair"
            elif is_leader:
                candidate_type = "subdragon_repair"
            elif weak_type == "bad_limit_up":
                candidate_type = "bad_limit_repair"
            elif weak_type == "upper_shadow":
                candidate_type = "upper_shadow_repair"
            elif recent_limit_up_count >= 1:
                candidate_type = "strong_trend_repair"
            else:
                candidate_type = "generic_repair"

            watch_pool_entry_type = d1_pool_entry
            if watch_pool_entry_type == "observe_only":
                candidate_score = min(candidate_score, 69.0)
            if watch_pool_entry_type == "formal":
                candidate_score = min(100.0, max(candidate_score, 70.0))
            if strong_grade == "B":
                candidate_score = min(69.0, candidate_score)
            elif strong_grade in {"S", "A"}:
                candidate_score = min(100.0, max(candidate_score, 72.0))
            score_boost = min(max(watch_score * 0.08, 0.0), 8.0)
            if strong_grade in {"S", "A"}:
                score_boost = min(12.0, score_boost + 3.0)
            candidate_score = round(min(100.0, candidate_score + score_boost), 2)

            d1_candidates_for_pool.append({
                "trade_date": trade_date,
                "next_trade_date": trade_date,
                "stock_id": str(row.get("stock_id") or ""),
                "stock_name": str(row.get("stock_name") or ""),
                "subject_key": str(row.get("subject_key") or ""),
                "theme_name": str(row.get("theme_name") or ""),
                "candidate_score": str(candidate_score),
                "candidate_type": candidate_type,
                "rule_version": "weak_to_strong_candidate.v2",
                "weak_type": weak_type,
                "weak_intensity": str(weak_intensity),
                "is_dragon_head": is_leader,
                "dragon_head_level": "dragon" if is_leader else "",
                "prev_limit_up_count": recent_limit_up_count,
                "max_consecutive_limit_up_days": 0,
                "support_type": support_type,
                "support_level": str(row.get("support_level") or "0"),
                "support_strength": str(support_strength),
                **_build_auction_expectations(candidate_type, weak_type, is_leader),
                "evidence_json": json.dumps({
                    "source": "strong_watch_pool",
                    "pct_chg": str(pct_chg),
                    "prev_day_pct": str(prev_day_pct),
                    "weak_type": weak_type,
                    "support_type": support_type,
                    "support_strength": str(support_strength),
                }),
                "pool_entry_type": watch_pool_entry_type,
                "cycle_state": str(row.get("final_cycle_state") or ""),
                "mainline_strength_score": str(mainline_strength_score),
                "fade_watch": fade_watch,
                "fade_confirmed": fade_confirmed,
            })

        return d1_candidates_for_pool

    @staticmethod
    def _dedup_and_rank(candidates: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        dedup: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            stock_id = str(candidate.get("stock_id") or "")
            if stock_id not in dedup or float(candidate.get("candidate_score") or 0) > float(dedup[stock_id].get("candidate_score") or 0):
                dedup[stock_id] = candidate
        ranked = sorted(dedup.values(), key=lambda x: float(x.get("candidate_score") or 0), reverse=True)
        return ranked[:limit]

    _diagnostics: dict[str, int] = None  # type: ignore[assignment]

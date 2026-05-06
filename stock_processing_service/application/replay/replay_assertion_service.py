from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any, Protocol

from stock_processing_service.application.replay.replay_cases import ReplayCase


class ReplayAssertionReadPort(Protocol):
    async def get_existing_post_market_recap_snapshot(self, trade_date: date) -> Any | None: ...


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return dict(value)


class ReplayAssertionService:
    """Assert fixed replay cases against persisted replay snapshots."""

    def __init__(self, read_port: ReplayAssertionReadPort) -> None:
        self._read_port = read_port

    async def assert_case(self, case: ReplayCase) -> dict[str, Any]:
        snapshot = await self._read_port.get_existing_post_market_recap_snapshot(case.trade_date)
        if snapshot is None:
            return {
                "case_name": case.name,
                "passed": False,
                "layer_results": {
                    "snapshot.post_market_recap": {
                        "expected": "present",
                        "actual": "missing",
                        "passed": False,
                    }
                },
            }

        snap = _as_dict(snapshot)
        recap_doc = dict(snap.get("recap_doc") or snap.get("payload") or {})
        layer_results: dict[str, dict[str, Any]] = {}
        expected = case.expected or {}

        layer_c = dict(expected.get("layer_c") or {})
        layer_d = dict(expected.get("layer_d") or {})
        top_candidates = self._rows(recap_doc, "top_candidates")
        observe_candidates = self._rows(recap_doc, "observe_candidates", "observe_candidates_preview")
        promoted_pool = self._rows(
            recap_doc,
            "promoted_pool",
            "promoted_pool_preview",
            "strong_watch_input_7d_preview",
            "strong_watch_input_preview",
        )

        best = self._target_row(case.stock_id, top_candidates, observe_candidates, promoted_pool)
        top = self._target_row(case.stock_id, top_candidates)
        observe = self._target_row(case.stock_id, observe_candidates)
        promoted = self._target_row(case.stock_id, promoted_pool)

        if "present_in_promoted_pool" in layer_c:
            self._record(
                layer_results,
                "layer_c.present_in_promoted_pool",
                expected=bool(layer_c["present_in_promoted_pool"]),
                actual=promoted is not None,
            )

        if "present_in_top_candidates" in layer_d:
            self._record(
                layer_results,
                "layer_d.present_in_top_candidates",
                expected=bool(layer_d["present_in_top_candidates"]),
                actual=top is not None,
            )
        if "present_in_observe_candidates" in layer_d:
            self._record(
                layer_results,
                "layer_d.present_in_observe_candidates",
                expected=bool(layer_d["present_in_observe_candidates"]),
                actual=observe is not None,
            )
        if "support_type" in layer_d:
            self._record(
                layer_results,
                "layer_d.support_type",
                expected=layer_d["support_type"],
                actual=(best or {}).get("support_type"),
            )
        if "gap_hit" in layer_d:
            self._record(
                layer_results,
                "layer_d.gap_hit",
                expected=bool(layer_d["gap_hit"]),
                actual=bool((best or {}).get("gap_hit")),
            )
        if "candidate_level" in layer_d:
            self._record(
                layer_results,
                "layer_d.candidate_level",
                expected=layer_d["candidate_level"],
                actual=(best or {}).get("candidate_level"),
            )
        if "candidate_level_in" in layer_d:
            actual = (best or {}).get("candidate_level")
            allowed = list(layer_d["candidate_level_in"] or [])
            layer_results["layer_d.candidate_level_in"] = {
                "expected": allowed,
                "actual": actual,
                "passed": actual in allowed,
            }
        if "allowed_outcomes" in layer_d:
            actual_outcome = {
                "candidate_level": (best or {}).get("candidate_level") or ("reject" if best is None else ""),
                "reject_reason": (best or {}).get("reject_reason") or (best or {}).get("hard_reject_reason") or "",
            }
            passed = self._allowed_outcome_passed(actual_outcome, list(layer_d["allowed_outcomes"] or []))
            layer_results["layer_d.allowed_outcomes"] = {
                "expected": layer_d["allowed_outcomes"],
                "actual": actual_outcome,
                "passed": passed,
            }

        return {
            "case_name": case.name,
            "passed": all(row.get("passed") is True for row in layer_results.values()),
            "layer_results": layer_results,
        }

    @staticmethod
    def _rows(recap_doc: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            rows = recap_doc.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, dict)]
        return []

    @staticmethod
    def _target_row(stock_id: str, *groups: list[dict[str, Any]]) -> dict[str, Any] | None:
        target = str(stock_id).strip().upper()
        for rows in groups:
            for row in rows:
                if str(row.get("stock_id") or "").strip().upper() == target:
                    return row
        return None

    @staticmethod
    def _record(
        out: dict[str, dict[str, Any]],
        key: str,
        *,
        expected: Any,
        actual: Any,
    ) -> None:
        out[key] = {
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        }

    @staticmethod
    def _allowed_outcome_passed(actual: dict[str, Any], allowed: list[Any]) -> bool:
        actual_level = str(actual.get("candidate_level") or "")
        actual_reason = str(actual.get("reject_reason") or "")
        for row in allowed:
            if not isinstance(row, dict):
                continue
            level = str(row.get("candidate_level") or "")
            if level != actual_level:
                continue
            reason_contains = row.get("reject_reason_contains")
            if reason_contains is not None and str(reason_contains) not in actual_reason:
                continue
            return True
        return False

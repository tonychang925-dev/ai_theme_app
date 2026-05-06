from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any, Protocol

from stock_processing_service.application.replay.candidate_miss_report import CandidateMissReportBuilder
from stock_processing_service.application.replay.leader_layer_diagnostic_report import LeaderLayerDiagnosticReportBuilder
from stock_processing_service.application.replay.replay_cases import ReplayCase
from stock_processing_service.application.replay.replay_layer_b_report import LayerBDiagnosticReportBuilder


class ReplayAssertionReadPort(Protocol):
    async def get_existing_post_market_recap_snapshot(self, trade_date: date) -> Any | None: ...

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date) -> list[Any]: ...

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[Any]: ...

    async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[Any]: ...

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[Any]: ...

    async def get_subject_cycle_evidence_daily(
        self, trade_date: date, subject_keys: list[str] | None = None
    ) -> list[dict[str, Any]]: ...


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

        layer_a = dict(expected.get("layer_a") or {})
        layer_b = dict(expected.get("layer_b") or {})
        layer_c = dict(expected.get("layer_c") or {})
        layer_d = dict(expected.get("layer_d") or {})
        top_candidates = self._rows(recap_doc, "top_candidates")
        observe_candidates = self._rows(recap_doc, "observe_candidates", "observe_candidates_preview")
        promoted_pool = self._rows(recap_doc, "promoted_pool", "promoted_pool_preview")
        has_promoted_pool = "promoted_pool" in recap_doc or "promoted_pool_preview" in recap_doc

        best = self._best_target_row(case.stock_id, top_candidates, observe_candidates, promoted_pool)
        top = self._target_row(case.stock_id, top_candidates)
        observe = self._target_row(case.stock_id, observe_candidates)
        promoted = self._target_row(case.stock_id, promoted_pool)
        subject_key = str((best or promoted or observe or top or {}).get("subject_key") or "")
        if not subject_key:
            subject_key = await self._resolve_subject_key_for_stock(case.trade_date, case.stock_id)
        diagnostics: dict[str, Any] = {
            "target_best_row": best or {},
            "candidate_miss": CandidateMissReportBuilder().build(
                trade_date=case.trade_date.isoformat(),
                stock_id=case.stock_id,
                recap_doc=recap_doc,
                top_candidates=top_candidates,
                observe_candidates=observe_candidates,
                promoted_pool=promoted_pool,
                strong_watch_input=self._rows(recap_doc, "strong_watch_input_7d_preview", "strong_watch_input_preview"),
                best_row=best,
            ).to_dict(),
        }

        if layer_a:
            if subject_key:
                await self._assert_layer_a(layer_results, case.trade_date, subject_key, layer_a)
            else:
                self._record(layer_results, "layer_a.subject_key", expected="present", actual="missing")

        if layer_b:
            if subject_key:
                layer_b_diag = await self._assert_layer_b(layer_results, case.trade_date, case.stock_id, subject_key, layer_b)
                diagnostics["layer_b_summary"] = layer_b_diag
            else:
                self._record(layer_results, "layer_b.subject_key", expected="present", actual="missing")
        elif subject_key:
            diagnostics["layer_b_summary"] = await self._assert_layer_b(
                {},
                case.trade_date,
                case.stock_id,
                subject_key,
                {},
            )

        if "present_in_promoted_pool" in layer_c:
            self._record(
                layer_results,
                "layer_c.present_in_promoted_pool",
                expected=bool(layer_c["present_in_promoted_pool"]),
                actual=(promoted is not None) if has_promoted_pool else (top is not None or observe is not None),
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
            "diagnostics": diagnostics,
        }

    async def _assert_layer_a(
        self,
        out: dict[str, dict[str, Any]],
        trade_date: date,
        subject_key: str,
        expected: dict[str, Any],
    ) -> None:
        rows = await self._read_port.get_mainline_identity_by_subject_keys([subject_key], trade_date)
        row = self._first_by_subject(rows, subject_key)
        if row is None:
            self._record(out, "layer_a.identity_row", expected="present", actual="missing")
            return
        if "identity_status" in expected:
            self._record(
                out,
                "layer_a.identity_status",
                expected=expected["identity_status"],
                actual=row.get("identity_status"),
            )
        if "is_main_theme" in expected:
            self._record(
                out,
                "layer_a.is_main_theme",
                expected=bool(expected["is_main_theme"]),
                actual=bool(row.get("is_main_theme")),
            )
        if "rule_version" in expected:
            self._record(
                out,
                "layer_a.rule_version",
                expected=expected["rule_version"],
                actual=row.get("rule_version"),
            )

    async def _assert_layer_b(
        self,
        out: dict[str, dict[str, Any]],
        trade_date: date,
        stock_id: str,
        subject_key: str,
        expected: dict[str, Any],
    ) -> dict[str, Any]:
        cycle_rows = await self._read_port.get_mainline_cycle_by_subject_keys([subject_key], trade_date)
        cycle = self._first_by_subject(cycle_rows, subject_key)
        evidence_rows = await self._read_port.get_subject_cycle_evidence_daily(
            trade_date=trade_date,
            subject_keys=[subject_key],
        )
        evidence = self._first_by_subject(evidence_rows, subject_key) or {}
        evidence_json = evidence.get("evidence_json") if isinstance(evidence.get("evidence_json"), dict) else {}
        kline_layer = evidence_json.get("kline_layer") if isinstance(evidence_json.get("kline_layer"), dict) else {}

        if cycle is None:
            self._record(out, "layer_b.cycle_row", expected="present", actual="missing")
        else:
            if "final_cycle_state" in expected:
                self._record(
                    out,
                    "layer_b.final_cycle_state",
                    expected=expected["final_cycle_state"],
                    actual=cycle.get("final_cycle_state"),
                )
            if "final_cycle_state_in" in expected:
                allowed = list(expected["final_cycle_state_in"] or [])
                actual = cycle.get("final_cycle_state")
                out["layer_b.final_cycle_state_in"] = {
                    "expected": allowed,
                    "actual": actual,
                    "passed": actual in allowed,
                }
            if "final_mainline_alive" in expected:
                self._record(
                    out,
                    "layer_b.final_mainline_alive",
                    expected=bool(expected["final_mainline_alive"]),
                    actual=bool(cycle.get("final_mainline_alive")),
                )

        if "theme_support_score" in expected:
            self._record(
                out,
                "layer_b.theme_support_score",
                expected=expected["theme_support_score"],
                actual=evidence.get("theme_support_score"),
            )
        if "break_start_pivot" in expected:
            self._record(
                out,
                "layer_b.break_start_pivot",
                expected=bool(expected["break_start_pivot"]),
                actual=bool(evidence.get("break_start_pivot")),
            )
        if "kline_quality" in expected:
            self._record(
                out,
                "layer_b.kline_quality",
                expected=expected["kline_quality"],
                actual=kline_layer.get("kline_quality"),
            )
        report = LayerBDiagnosticReportBuilder().build(
            trade_date=trade_date.isoformat(),
            stock_id=stock_id,
            subject_key=subject_key,
            evidence=evidence,
            cycle=cycle,
        ).to_dict()
        pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        stock_ids: list[str] = []
        for raw in pool_rows:
            row = _as_dict(raw)
            stock_id_value = str(row.get("stock_id") or "")
            if stock_id_value:
                stock_ids.append(stock_id_value)
        bars = await self._read_port.get_stock_daily_bars(trade_date, stock_ids=stock_ids or None)
        report["leader_layer_diagnostic"] = LeaderLayerDiagnosticReportBuilder().build(
            trade_date=trade_date.isoformat(),
            stock_id=stock_id,
            subject_key=subject_key,
            pool_rows=pool_rows,
            bars=bars,
            evidence=evidence,
            cycle=cycle,
        ).to_dict()
        return report

    @staticmethod
    def _rows(recap_doc: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            rows = recap_doc.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, dict)]
        return []

    async def _resolve_subject_key_for_stock(self, trade_date: date, stock_id: str) -> str:
        fn = getattr(self._read_port, "get_subject_stock_pool_by_trade_date", None)
        if not callable(fn):
            return ""
        rows = await fn(trade_date)
        target = str(stock_id).strip().upper()
        for raw in rows:
            row = _as_dict(raw)
            if str(row.get("stock_id") or "").strip().upper() == target:
                return str(row.get("subject_key") or "")
        return ""

    @staticmethod
    def _target_row(stock_id: str, *groups: list[dict[str, Any]]) -> dict[str, Any] | None:
        target = str(stock_id).strip().upper()
        for rows in groups:
            for row in rows:
                if str(row.get("stock_id") or "").strip().upper() == target:
                    return row
        return None

    @staticmethod
    def _best_target_row(stock_id: str, *groups: list[dict[str, Any]]) -> dict[str, Any] | None:
        target_rows: list[dict[str, Any]] = []
        target = str(stock_id).strip().upper()
        for rows in groups:
            for row in rows:
                if str(row.get("stock_id") or "").strip().upper() == target:
                    target_rows.append(row)
        if not target_rows:
            return None
        for key in ("support_type", "gap_hit", "reject_reason", "hard_reject_reason"):
            for row in target_rows:
                if row.get(key) not in (None, ""):
                    return row
        return target_rows[0]

    @staticmethod
    def _first_by_subject(rows: list[Any], subject_key: str) -> dict[str, Any] | None:
        target = str(subject_key)
        for row in rows:
            payload = _as_dict(row)
            if str(payload.get("subject_key") or "") == target:
                return payload
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

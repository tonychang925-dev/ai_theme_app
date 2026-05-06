from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class LeaderLayerDiagnosticReport:
    trade_date: str
    stock_id: str
    subject_key: str
    leader_layer: dict[str, Any]
    cycle_effect: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "stock_id": self.stock_id,
            "subject_key": self.subject_key,
            "leader_layer": self.leader_layer,
            "cycle_effect": self.cycle_effect,
        }


class LeaderLayerDiagnosticReportBuilder:
    FRONT_ROW_SIZE = 5

    def build(
        self,
        *,
        trade_date: str,
        stock_id: str,
        subject_key: str,
        pool_rows: list[Any],
        bars: list[Any],
        evidence: dict[str, Any] | None,
        cycle: dict[str, Any] | None,
    ) -> LeaderLayerDiagnosticReport:
        ev = dict(evidence or {})
        cyc = dict(cycle or {})
        rows = [self._as_dict(row) for row in pool_rows]
        subject_rows = [row for row in rows if str(row.get("subject_key") or "") == subject_key]
        bars_by_stock = {str(self._as_dict(bar).get("stock_id") or ""): self._as_dict(bar) for bar in bars}
        leader = self._select_leader(subject_rows=subject_rows, bars_by_stock=bars_by_stock)
        front_rows = self._front_rows(subject_rows)
        front_alive_count = 0
        front_limit_up_count = 0
        front_big_drop_count = 0
        for row in front_rows:
            bar = bars_by_stock.get(str(row.get("stock_id") or ""))
            pct = self._pct(row=row, bar=bar)
            if pct >= Decimal("0"):
                front_alive_count += 1
            if self._limit_up(row=row, bar=bar, pct=pct):
                front_limit_up_count += 1
            if pct <= Decimal("-5"):
                front_big_drop_count += 1

        leader_bar = bars_by_stock.get(str(leader.get("stock_id") or "")) if leader else None
        leader_pct = self._pct(row=leader, bar=leader_bar) if leader else None
        leader_limit_up = self._limit_up(row=leader, bar=leader_bar, pct=leader_pct or Decimal("0")) if leader else False
        leader_big_drop = bool(leader_pct is not None and leader_pct <= Decimal("-5"))
        score_source = self._score_source(subject_rows, ev)
        breakdown_reason = self._breakdown_reason(
            leader=leader,
            leader_pct=leader_pct,
            leader_limit_up=leader_limit_up,
            leader_big_drop=leader_big_drop,
            score_source=score_source,
            evidence=ev,
        )

        return LeaderLayerDiagnosticReport(
            trade_date=trade_date,
            stock_id=stock_id,
            subject_key=subject_key,
            leader_layer={
                "leader_alive_score": ev.get("leader_alive_score"),
                "leader_score_source": score_source,
                "leader_stock_id": leader.get("stock_id") if leader else None,
                "leader_stock_name": leader.get("stock_name") if leader else None,
                "leader_pct_chg": str(leader_pct) if leader_pct is not None else None,
                "leader_limit_up": leader_limit_up,
                "leader_big_drop": leader_big_drop,
                "front_row_alive_count": front_alive_count,
                "front_row_limit_up_count": front_limit_up_count,
                "front_row_big_drop_count": front_big_drop_count,
                "successor_vacuum": front_alive_count <= 1 and not leader_limit_up,
                "leader_breakdown_reason": breakdown_reason,
                "pool_stock_count": len(subject_rows),
                "front_row_count": len(front_rows),
            },
            cycle_effect={
                "mainline_strength_score": cyc.get("mainline_strength_score"),
                "final_cycle_state": cyc.get("final_cycle_state"),
                "final_mainline_alive": cyc.get("final_mainline_alive"),
            },
        )

    def _select_leader(
        self,
        *,
        subject_rows: list[dict[str, Any]],
        bars_by_stock: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if not subject_rows:
            return {}
        with_scores = [(self._explicit_leader_score(row), row) for row in subject_rows]
        explicit = [(score, row) for score, row in with_scores if score is not None]
        if explicit:
            return max(explicit, key=lambda item: (item[0], -self._rank(item[1])))[1]
        return sorted(
            subject_rows,
            key=lambda row: (
                1 if self._bool(self._first(row, "is_leader")) else 0,
                -self._rank(row),
                self._pct(row=row, bar=bars_by_stock.get(str(row.get("stock_id") or ""))),
            ),
            reverse=True,
        )[0]

    def _front_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(rows, key=self._rank)[: self.FRONT_ROW_SIZE]

    @classmethod
    def _score_source(cls, rows: list[dict[str, Any]], evidence: dict[str, Any]) -> str:
        if any(cls._explicit_leader_score(row) is not None for row in rows):
            return "pool_metadata"
        if rows:
            if cls._d(evidence.get("leader_alive_score")) == Decimal("0"):
                return "missing_pool_metadata_inferred_available"
            return "inferred"
        return "missing"

    @classmethod
    def _breakdown_reason(
        cls,
        *,
        leader: dict[str, Any],
        leader_pct: Decimal | None,
        leader_limit_up: bool,
        leader_big_drop: bool,
        score_source: str,
        evidence: dict[str, Any],
    ) -> str:
        if not leader:
            return "leader_row_missing"
        if score_source == "missing_pool_metadata_inferred_available" and cls._d(evidence.get("leader_alive_score")) == Decimal("0"):
            return "leader_score_metadata_missing"
        if leader_big_drop:
            return "leader_big_drop"
        if leader_pct is not None and leader_pct < Decimal("0") and not leader_limit_up:
            return "leader_negative_pct"
        if leader_limit_up:
            return "leader_limit_up_alive"
        return "leader_inferred_from_rank"

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            row = dict(value)
        elif is_dataclass(value):
            row = asdict(value)
        else:
            row = dict(value)
        metadata = row.get("metadata")
        if isinstance(metadata, dict):
            merged = dict(metadata)
            merged.update(row)
            return merged
        return row

    @classmethod
    def _explicit_leader_score(cls, row: dict[str, Any]) -> Decimal | None:
        for key in ("leader_score", "leader_alive_score", "front_rank_alive_score"):
            value = row.get(key)
            if value not in (None, ""):
                return cls._d(value)
        return None

    @classmethod
    def _pct(cls, *, row: dict[str, Any] | None, bar: dict[str, Any] | None) -> Decimal:
        row = row or {}
        bar = bar or {}
        return cls._d(cls._first(bar, "pct_chg") if cls._first(bar, "pct_chg") is not None else cls._first(row, "pct_chg"))

    @classmethod
    def _limit_up(cls, *, row: dict[str, Any] | None, bar: dict[str, Any] | None, pct: Decimal) -> bool:
        row = row or {}
        bar = bar or {}
        raw = cls._first(row, "limit_up")
        if raw is not None:
            return cls._bool(raw)
        close_price = cls._d(cls._first(bar, "close_price"))
        limit_up_price = cls._d(cls._first(bar, "limit_up_price"))
        return pct >= Decimal("9.5") or (limit_up_price > 0 and close_price >= limit_up_price)

    @classmethod
    def _rank(cls, row: dict[str, Any]) -> int:
        value = cls._first(row, "pool_rank", "rank_order", "leaderboard_rank")
        try:
            return int(value or 999)
        except (TypeError, ValueError):
            return 999

    @staticmethod
    def _first(row: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in row:
                return row.get(key)
        return None

    @staticmethod
    def _d(value: Any) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y"}
        return bool(value)

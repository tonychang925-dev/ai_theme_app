from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO


class StrongWatchPreSeedGeneEnricher:
    """Detect independent strong-stock genes before Universe/Seed gates.

    This service only grants strong-watch eligibility. It does not confirm
    Layer A identity or mutate Layer B cycle state.
    """

    def enrich(
        self,
        *,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
    ) -> list[SubjectStockPoolDTO]:
        bars_by_stock = {bar.stock_id: bar for bar in bars}
        prior_by_stock: dict[str, list[PriorSnapshotDTO]] = {}
        for row in prior_rows or []:
            prior_by_stock.setdefault(row.stock_id, []).append(row)
        history_by_stock: dict[str, list[StockBarDTO]] = {}
        for row in history_bars or []:
            history_by_stock.setdefault(row.stock_id, []).append(row)

        enriched: list[SubjectStockPoolDTO] = []
        for row in pool_rows:
            metadata = dict(row.metadata or {})
            bar = bars_by_stock.get(row.stock_id)
            recent_limit_up_count, max_consecutive_limit_up_days = self._recent_limit_up_features(
                stock_id=row.stock_id,
                current_bar=bar,
                metadata=metadata,
                prior_rows=prior_by_stock.get(row.stock_id, []),
                history_bars=history_by_stock.get(row.stock_id, []),
            )
            prior7_limitup_days = self._prior7_limitup_days(
                metadata=metadata,
                prior_rows=prior_by_stock.get(row.stock_id, []),
            )
            three_days_two_boards = self._three_days_two_boards(
                stock_id=row.stock_id,
                current_bar=bar,
                prior_rows=prior_by_stock.get(row.stock_id, []),
                history_bars=history_by_stock.get(row.stock_id, []),
            )
            two_board_entry = (
                max_consecutive_limit_up_days >= 2
                or recent_limit_up_count >= 2
                or prior7_limitup_days >= 2
                or three_days_two_boards
            )
            strong_gene_seed = bool(two_board_entry)
            if strong_gene_seed:
                metadata.setdefault("prior7_limitup_days", prior7_limitup_days)
                metadata.setdefault("recent_limit_up_count", recent_limit_up_count)
                metadata.setdefault("max_consecutive_limit_up_days", max_consecutive_limit_up_days)
                metadata.setdefault("three_days_two_boards", three_days_two_boards)
                metadata["two_board_entry"] = bool(two_board_entry)
                metadata["strong_gene_seed"] = True
                metadata["strong_gene_seed_reason"] = self._reason(
                    prior7_limitup_days=prior7_limitup_days,
                    recent_limit_up_count=recent_limit_up_count,
                    max_consecutive_limit_up_days=max_consecutive_limit_up_days,
                    three_days_two_boards=three_days_two_boards,
                )
                metadata.setdefault("entry_path", "independent_leader")
                metadata.setdefault("identity_scope", "independent_stock_signal")
            enriched.append(replace(row, metadata=metadata))
        return enriched

    @classmethod
    def _recent_limit_up_features(
        cls,
        *,
        stock_id: str,
        current_bar: StockBarDTO | None,
        metadata: dict[str, Any],
        prior_rows: list[PriorSnapshotDTO],
        history_bars: list[StockBarDTO],
    ) -> tuple[int, int]:
        raw_recent = metadata.get("recent_limit_up_count")
        raw_consecutive = metadata.get("max_consecutive_limit_up_days")
        if raw_recent is not None or raw_consecutive is not None:
            return int(raw_recent or 0), int(raw_consecutive or 0)

        ordered = cls._ordered_limit_flags(
            stock_id=stock_id,
            current_bar=current_bar,
            prior_rows=prior_rows,
            history_bars=history_bars,
        )
        if not ordered:
            return 0, 0
        recent_window = ordered[-7:]
        recent_limit_up_count = sum(1 for _, is_limit_up in recent_window if is_limit_up)
        consecutive = 0
        for _, is_limit_up in reversed(ordered):
            if not is_limit_up:
                break
            consecutive += 1
        return recent_limit_up_count, consecutive

    @classmethod
    def _three_days_two_boards(
        cls,
        *,
        stock_id: str,
        current_bar: StockBarDTO | None,
        prior_rows: list[PriorSnapshotDTO],
        history_bars: list[StockBarDTO],
    ) -> bool:
        ordered = cls._ordered_limit_flags(
            stock_id=stock_id,
            current_bar=current_bar,
            prior_rows=prior_rows,
            history_bars=history_bars,
        )
        return sum(1 for _, is_limit_up in ordered[-3:] if is_limit_up) >= 2

    @classmethod
    def _ordered_limit_flags(
        cls,
        *,
        stock_id: str,
        current_bar: StockBarDTO | None,
        prior_rows: list[PriorSnapshotDTO],
        history_bars: list[StockBarDTO],
    ) -> list[tuple[Any, bool]]:
        day_pct: dict[Any, Decimal] = {}
        for prior in prior_rows:
            day_pct[prior.trade_date] = cls._d((prior.payload or {}).get("pct_chg"))
        for hist in history_bars:
            if hist.stock_id == stock_id:
                day_pct[hist.trade_date] = hist.pct_chg
        if current_bar is not None:
            day_pct[current_bar.trade_date] = current_bar.pct_chg
        return [(day, pct >= Decimal("9.5")) for day, pct in sorted(day_pct.items(), key=lambda item: item[0])]

    @classmethod
    def _prior7_limitup_days(cls, *, metadata: dict[str, Any], prior_rows: list[PriorSnapshotDTO]) -> int:
        raw = metadata.get("prior7_limitup_days")
        if raw is not None:
            return int(raw or 0)
        ordered = sorted(prior_rows, key=lambda row: row.trade_date)
        return sum(1 for row in ordered[-7:] if cls._d((row.payload or {}).get("pct_chg")) >= Decimal("9.5"))

    @staticmethod
    def _reason(
        *,
        prior7_limitup_days: int,
        recent_limit_up_count: int,
        max_consecutive_limit_up_days: int,
        three_days_two_boards: bool,
    ) -> str:
        if max_consecutive_limit_up_days >= 2:
            return "two_board_entry"
        if three_days_two_boards:
            return "three_days_two_boards"
        if recent_limit_up_count >= 2 or prior7_limitup_days >= 2:
            return "recent_multi_limitup"
        return "strong_gene_seed"

    @staticmethod
    def _d(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

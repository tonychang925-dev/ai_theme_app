from __future__ import annotations

from typing import Iterable

from stock_service.models import StockDailySnapshot, SubjectStockDailySnapshot


def _to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


class DailySnapshotService:
    """
    P3.phase1-T02 最小实现：
    - 规范化 Tushare 日频记录为 stock_daily_snapshot
    - 将 JYHF 题材股票池记录与股票快照拼接为 subject_stock_daily_snapshot
    """

    def normalize_tushare_daily_rows(self, rows: Iterable[dict], trade_date: str) -> list[StockDailySnapshot]:
        snapshots: list[StockDailySnapshot] = []
        for row in rows:
            stock_id = str(row.get("ts_code") or "").strip().upper()
            if not stock_id:
                continue
            snapshots.append(
                StockDailySnapshot(
                    trade_date=trade_date,
                    stock_id=stock_id,
                    stock_name=row.get("name"),
                    open_price=_to_float(row.get("open")),
                    high_price=_to_float(row.get("high")),
                    low_price=_to_float(row.get("low")),
                    close_price=_to_float(row.get("close")),
                    pre_close=_to_float(row.get("pre_close")),
                    pct_chg=_to_float(row.get("pct_chg")),
                    volume=_to_float(row.get("vol")),
                    amount=_to_float(row.get("amount")),
                )
            )
        return snapshots

    def build_subject_stock_daily_snapshots(
        self,
        trade_date: str,
        stock_snapshots: Iterable[StockDailySnapshot],
        jyhf_rows: Iterable[dict],
    ) -> list[SubjectStockDailySnapshot]:
        snapshot_map = {row.stock_id: row for row in stock_snapshots}
        results: list[SubjectStockDailySnapshot] = []
        for row in jyhf_rows:
            stock_id = str(row.get("stock_id") or "").strip().upper()
            if not stock_id:
                continue
            stock_snapshot = snapshot_map.get(stock_id)
            results.append(
                SubjectStockDailySnapshot(
                    trade_date=trade_date,
                    subject_key=str(row.get("subject_key") or ""),
                    subject_name=row.get("subject_name"),
                    stock_id=stock_id,
                    stock_name=row.get("stock_name") or (stock_snapshot.stock_name if stock_snapshot else None),
                    rank_order=int(row.get("rank_order") or 0),
                    pct_chg=_to_float(row.get("pct_chg")) if row.get("pct_chg") is not None else (stock_snapshot.pct_chg if stock_snapshot else None),
                    close_price=_to_float(row.get("close_price")) if row.get("close_price") is not None else (stock_snapshot.close_price if stock_snapshot else None),
                    is_leader=bool(row.get("is_leader")),
                )
            )
        return results

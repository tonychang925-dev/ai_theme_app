from __future__ import annotations

from stock_service.models import SubjectStockDailySnapshot
from stock_service.services.stock_signal_service import StockSignalService


def _subject_row(
    *,
    stock_id: str,
    subject_key: str = "9025631",
    subject_name: str = "创新药",
    rank_order: int = 1,
    pct_chg: float | None = None,
    is_leader: bool = False,
) -> SubjectStockDailySnapshot:
    return SubjectStockDailySnapshot(
        trade_date="2026-04-02",
        subject_key=subject_key,
        subject_name=subject_name,
        stock_id=stock_id,
        stock_name=f"股票{stock_id[-2:]}",
        rank_order=rank_order,
        pct_chg=pct_chg,
        close_price=10.0,
        is_leader=is_leader,
    )


def test_derive_abnormal_events_detects_limit_up_and_leader_move():
    service = StockSignalService()
    rows = [
        _subject_row(stock_id="000001.SZ", pct_chg=10.01, rank_order=2, is_leader=False),
        _subject_row(stock_id="000002.SZ", pct_chg=5.21, rank_order=1, is_leader=True),
        _subject_row(stock_id="000003.SZ", pct_chg=1.23, rank_order=3, is_leader=False),
    ]

    events = service.derive_abnormal_events(rows)

    assert len(events) == 2
    assert events[0].abnormal_type == "limit_up"
    assert events[0].stock_id == "000001.SZ"
    assert events[1].abnormal_type == "leader_move"
    assert events[1].stock_id == "000002.SZ"
    assert "leader" in events[1].evidence


def test_derive_abnormal_events_detects_limit_down():
    service = StockSignalService()
    rows = [_subject_row(stock_id="000004.SZ", pct_chg=-9.95, rank_order=5, is_leader=False)]

    events = service.derive_abnormal_events(rows)

    assert len(events) == 1
    assert events[0].abnormal_type == "limit_down"
    assert events[0].stock_id == "000004.SZ"


def test_build_theme_stock_leaderboard_assigns_roles_and_orders_by_score():
    service = StockSignalService()
    rows = [
        _subject_row(stock_id="000001.SZ", subject_key="A", rank_order=2, pct_chg=10.01, is_leader=False),
        _subject_row(stock_id="000002.SZ", subject_key="A", rank_order=1, pct_chg=4.50, is_leader=True),
        _subject_row(stock_id="000003.SZ", subject_key="A", rank_order=3, pct_chg=2.10, is_leader=False),
        _subject_row(stock_id="000004.SZ", subject_key="B", rank_order=1, pct_chg=1.20, is_leader=True),
    ]

    entries = service.build_theme_stock_leaderboard(rows)

    subject_a = [item for item in entries if item.subject_key == "A"]
    assert [item.stock_id for item in subject_a] == ["000002.SZ", "000001.SZ", "000003.SZ"]
    assert subject_a[0].role == "leader"
    assert subject_a[1].role == "core"
    assert subject_a[1].limit_up is True
    assert subject_a[2].role == "core"

    subject_b = [item for item in entries if item.subject_key == "B"]
    assert len(subject_b) == 1
    assert subject_b[0].role == "leader"

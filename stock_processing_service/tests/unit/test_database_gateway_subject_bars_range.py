from __future__ import annotations

from datetime import date

import pytest

from database_service.gateway import DatabaseGateway


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get_subject_stock_daily_bars_range(self, start_date, end_date, stock_ids=None, subject_keys=None):
        self.calls.append((start_date, end_date, stock_ids, subject_keys))
        return [{"trade_date": start_date, "stock_id": "603618.SH", "subject_key": "9064103"}]

    async def upsert_post_market_setup_plan_rows(self, rows):
        self.calls.append(("setup_plan", rows))
        return len(rows)

    async def upsert_one_to_two_candidate_feature_rows(self, rows):
        self.calls.append(("candidate_feature", rows))
        return len(rows)

    async def get_active_confirmed_mainlines(self, trade_date=None, limit=100):
        self.calls.append(("active_mainlines", trade_date, limit))
        return [{"mainline_id": "ml_AI光纤_202606", "canonical_subject_key": "9064103"}]


@pytest.mark.asyncio
async def test_database_gateway_forwards_subject_stock_daily_bars_range() -> None:
    gateway = DatabaseGateway.__new__(DatabaseGateway)
    fake_client = _FakeClient()
    gateway._client = fake_client
    gateway._record_request = lambda *args, **kwargs: None

    rows = await gateway.get_subject_stock_daily_bars_range(
        date(2026, 5, 6),
        date(2026, 5, 8),
        stock_ids=["603618.SH"],
        subject_keys=["9064103"],
    )

    assert rows[0]["stock_id"] == "603618.SH"
    assert fake_client.calls == [(date(2026, 5, 6), date(2026, 5, 8), ["603618.SH"], ["9064103"])]


@pytest.mark.asyncio
async def test_database_gateway_forwards_backtest_setup_plan_and_candidate_rows() -> None:
    gateway = DatabaseGateway.__new__(DatabaseGateway)
    fake_client = _FakeClient()
    gateway._client = fake_client
    gateway._record_request = lambda *args, **kwargs: None

    setup_written = await gateway.upsert_post_market_setup_plan_rows([{"run_id": "r1"}])
    candidate_written = await gateway.upsert_one_to_two_candidate_feature_rows([{"run_id": "r1"}])

    assert setup_written == 1
    assert candidate_written == 1
    assert fake_client.calls[-2:] == [
        ("setup_plan", [{"run_id": "r1"}]),
        ("candidate_feature", [{"run_id": "r1"}]),
    ]


@pytest.mark.asyncio
async def test_database_gateway_forwards_active_confirmed_mainlines() -> None:
    gateway = DatabaseGateway.__new__(DatabaseGateway)
    fake_client = _FakeClient()
    gateway._client = fake_client
    gateway._record_request = lambda *args, **kwargs: None

    rows = await gateway.get_active_confirmed_mainlines(trade_date=date(2026, 5, 6), limit=100)

    assert rows[0]["canonical_subject_key"] == "9064103"
    assert fake_client.calls[-1] == ("active_mainlines", date(2026, 5, 6), 100)

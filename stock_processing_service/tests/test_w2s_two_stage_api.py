from __future__ import annotations

from datetime import date
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from stock_processing_service.contracts.dto import StockAuctionDTO
from stock_processing_service import api_app


def _install_strategy_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_stock_screening_strategy(_strategy_id: str):
        return {"strategy_name": "弱转强两阶段", "strategy_type": "weak_to_strong"}

    monkeypatch.setattr(
        api_app.app,
        "state",
        SimpleNamespace(gateway=SimpleNamespace(get_stock_screening_strategy=get_stock_screening_strategy)),
        raising=False,
    )


@pytest.mark.asyncio
async def test_post_market_stage_does_not_require_confirm_date(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_strategy_repo(monkeypatch)
    seen: dict[str, object] = {}

    async def forbid_resolve_prev_trade_date(_trade_date: date) -> date:
        raise AssertionError("stage1-only should not resolve previous trade date in api layer")

    async def noop_normalize(_results, _trade_date=None) -> None:
        return None

    async def run_stage1(candidate_trade_date: date, stage1_limit: int):
        seen["run_stage1"] = (candidate_trade_date, stage1_limit)
        assert candidate_trade_date == date(2024, 1, 2)
        assert stage1_limit == 10
        return {
            "status": "success",
            "source_trade_date": candidate_trade_date.isoformat(),
            "candidate_count": 1,
            "candidate_limit": stage1_limit,
            "selection_job": "build_weak_to_strong_candidate",
        }

    async def fetch_candidates(candidate_trade_date: date, limit: int = 200):
        assert candidate_trade_date == date(2024, 1, 2)
        assert limit in {10, 2000}
        return [
            {
                "id": 11,
                "trade_date": date(2024, 1, 2),
                "next_trade_date": date(2024, 1, 3),
                "stock_id": "000001.SZ",
                "stock_name": "平安银行",
                "subject_key": "bank",
                "theme_name": "银行",
                "candidate_score": 77.5,
                "pool_entry_type": "formal",
                "candidate_type": "trend_repair",
                "weak_type": "",
                "support_type": "",
                "support_strength": 0.0,
                "expected_open_low": 0.0,
                "expected_open_high": 0.0,
                "evidence_json": {},
            }
        ]

    monkeypatch.setattr(api_app, "_resolve_prev_trade_date", forbid_resolve_prev_trade_date)
    monkeypatch.setattr(api_app, "_run_w2s_candidate_selection_for_screener", run_stage1)
    monkeypatch.setattr(api_app, "_fetch_w2s_candidates", fetch_candidates)
    monkeypatch.setattr(api_app, "_normalize_result_theme_names", noop_normalize)

    payload = api_app.ScreenerExecutePayload(
        strategy_id="weak_to_strong",
        trade_date="2024-01-02",
        run_stage1=True,
        run_stage2=False,
        limit=100,
    )

    result = await api_app._execute_weak_to_strong_two_stage(payload, date(2024, 1, 2))

    assert result["trade_date"] == "2024-01-02"
    assert result["diagnostics"]["candidate_trade_date"] == "2024-01-02"
    assert result["diagnostics"]["confirm_trade_date"] is None
    assert result["diagnostics"]["snapshot_trade_date"] is None
    assert result["diagnostics"]["stage1"]["status"] == "success"
    assert result["diagnostics"]["stage1"]["source_trade_date"] == "2024-01-02"
    assert seen["run_stage1"] == (date(2024, 1, 2), 10)


@pytest.mark.asyncio
async def test_default_stage_flags_remain_post_market_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_strategy_repo(monkeypatch)
    seen: dict[str, object] = {}

    async def forbid_resolve_prev_trade_date(_trade_date: date) -> date:
        raise AssertionError("default request must not enter stage2 confirm flow")

    async def noop_normalize(_results, _trade_date=None) -> None:
        return None

    async def run_stage1(candidate_trade_date: date, stage1_limit: int):
        seen["run_stage1"] = (candidate_trade_date, stage1_limit)
        assert candidate_trade_date == date(2024, 1, 2)
        return {
            "status": "success",
            "source_trade_date": candidate_trade_date.isoformat(),
            "candidate_count": 1,
            "candidate_limit": stage1_limit,
            "selection_job": "build_weak_to_strong_candidate",
        }

    async def fetch_candidates(candidate_trade_date: date, limit: int = 200):
        return [
            {
                "id": 11,
                "trade_date": date(2024, 1, 2),
                "stock_id": "000001.SZ",
                "stock_name": "平安银行",
                "subject_key": "bank",
                "theme_name": "银行",
                "candidate_score": 77.5,
                "pool_entry_type": "formal",
                "candidate_type": "trend_repair",
                "weak_type": "",
                "support_type": "",
                "support_strength": 0.0,
                "expected_open_low": 0.0,
                "expected_open_high": 0.0,
                "evidence_json": {},
            }
        ]

    monkeypatch.setattr(api_app, "_resolve_prev_trade_date", forbid_resolve_prev_trade_date)
    monkeypatch.setattr(api_app, "_run_w2s_candidate_selection_for_screener", run_stage1)
    monkeypatch.setattr(api_app, "_fetch_w2s_candidates", fetch_candidates)
    monkeypatch.setattr(api_app, "_normalize_result_theme_names", noop_normalize)

    payload = api_app.ScreenerExecutePayload(
        strategy_id="weak_to_strong",
        trade_date="2024-01-02",
    )

    result = await api_app._execute_weak_to_strong_two_stage(payload, date(2024, 1, 2))

    assert result["trade_date"] == "2024-01-02"
    assert result["diagnostics"]["run_stage1"] is True
    assert result["diagnostics"]["run_stage2"] is False
    assert result["diagnostics"]["confirm_trade_date"] is None
    assert seen["run_stage1"] == (date(2024, 1, 2), 10)


@pytest.mark.asyncio
async def test_pre_market_stage_uses_confirm_date_and_prior_candidate_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_strategy_repo(monkeypatch)
    seen: dict[str, date] = {}

    async def resolve_prev_trade_date(confirm_trade_date: date) -> date:
        seen["resolve_prev_trade_date"] = confirm_trade_date
        return date(2024, 1, 2)

    async def noop_normalize(_results, _trade_date=None) -> None:
        return None

    async def fetch_candidates(candidate_trade_date: date, limit: int = 200):
        seen["fetch_candidates"] = candidate_trade_date
        return [
            {
                "id": 21,
                "trade_date": date(2024, 1, 2),
                "next_trade_date": date(2024, 1, 3),
                "stock_id": "000001.SZ",
                "stock_name": "平安银行",
                "subject_key": "bank",
                "theme_name": "银行",
                "candidate_score": 82.0,
                "pool_entry_type": "formal",
                "candidate_type": "trend_repair",
                "weak_type": "",
                "support_type": "",
                "support_strength": 0.0,
                "expected_open_low": 0.0,
                "expected_open_high": 0.0,
                "evidence_json": {},
            }
        ]

    async def load_auctions(confirm_trade_date: date, candidate_trade_date: date, formal_candidates):
        seen["auction_snapshot"] = confirm_trade_date
        seen["auction_candidate_trade_date"] = candidate_trade_date
        assert [row["stock_id"] for row in formal_candidates] == ["000001.SZ"]
        return (
            [
                StockAuctionDTO(
                    trade_date=confirm_trade_date,
                    stock_id="000001.SZ",
                    auction_open_pct=Decimal("3"),
                    auction_amount=Decimal("3000000"),
                    tail_auction_vwap=Decimal("10"),
                )
            ],
            {"channel": "db", "cache_writes": 0, "persisted_rows": 0},
        )

    monkeypatch.setattr(api_app, "_resolve_prev_trade_date", resolve_prev_trade_date)
    monkeypatch.setattr(api_app, "_fetch_w2s_candidates", fetch_candidates)
    monkeypatch.setattr(api_app, "_load_w2s_auctions_for_confirm", load_auctions)
    monkeypatch.setattr(api_app, "_normalize_result_theme_names", noop_normalize)

    payload = api_app.ScreenerExecutePayload(
        strategy_id="weak_to_strong",
        trade_date="2024-01-03",
        candidate_trade_date="2024-01-02",
        confirm_trade_date="2024-01-03",
        run_stage1=False,
        run_stage2=True,
        limit=100,
    )

    result = await api_app._execute_weak_to_strong_two_stage(payload, date(2024, 1, 3))

    assert result["trade_date"] == "2024-01-03"
    assert result["diagnostics"]["candidate_trade_date"] == "2024-01-02"
    assert result["diagnostics"]["confirm_trade_date"] == "2024-01-03"
    assert seen["resolve_prev_trade_date"] == date(2024, 1, 3)
    assert seen["fetch_candidates"] == date(2024, 1, 2)
    assert seen["auction_snapshot"] == date(2024, 1, 3)
    assert seen["auction_candidate_trade_date"] == date(2024, 1, 2)
    assert result["diagnostics"]["stage2"]["status"] == "success"
    assert result["total_count"] == 1


@pytest.mark.asyncio
async def test_pre_market_stage_blocks_before_0925_for_today(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_strategy_repo(monkeypatch)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = cls(2026, 5, 4, 9, 24, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            if tz is None:
                return current.replace(tzinfo=None)
            return current.astimezone(tz)

    async def resolve_prev_trade_date(confirm_trade_date: date) -> date:
        assert confirm_trade_date == date(2026, 5, 4)
        return date(2026, 4, 30)

    monkeypatch.setattr(api_app, "datetime", FixedDateTime)
    monkeypatch.setattr(api_app, "_resolve_prev_trade_date", resolve_prev_trade_date)

    payload = api_app.ScreenerExecutePayload(
        strategy_id="weak_to_strong",
        trade_date="2026-05-04",
        confirm_trade_date="2026-05-04",
        run_stage1=False,
        run_stage2=True,
        limit=100,
    )

    with pytest.raises(api_app.HTTPException) as exc_info:
        await api_app._execute_weak_to_strong_two_stage(payload, date(2026, 5, 4))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == api_app.PRE_MARKET_CONFIRM_NOT_READY_MESSAGE


@pytest.mark.asyncio
async def test_load_w2s_auctions_for_confirm_uses_realtime_channel_during_0925_window(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = cls(2026, 5, 4, 9, 26, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            if tz is None:
                return current.replace(tzinfo=None)
            return current.astimezone(tz)

    seen: dict[str, object] = {}

    async def read_cache(confirm_trade_date: date, stock_ids):
        seen["read_cache"] = (confirm_trade_date, tuple(stock_ids))
        return [], []

    async def build_live(confirm_trade_date: date, candidate_trade_date: date, formal_candidates):
        seen["build_live"] = (confirm_trade_date, candidate_trade_date, len(formal_candidates))
        return (
            [
                StockAuctionDTO(
                    trade_date=confirm_trade_date,
                    stock_id="000001.SZ",
                    auction_open_pct=Decimal("2"),
                    auction_amount=Decimal("2000000"),
                    tail_auction_vwap=Decimal("10"),
                )
            ],
            [{"trade_date": confirm_trade_date, "stock_id": "000001.SZ"}],
        )

    async def write_cache(confirm_trade_date: date, auctions, snapshots):
        seen["write_cache"] = (confirm_trade_date, len(auctions), len(snapshots))

    async def persist_rows(snapshots):
        seen["persist_rows"] = len(snapshots)
        return len(snapshots)

    monkeypatch.setattr(api_app, "datetime", FixedDateTime)
    monkeypatch.setattr(api_app, "_read_realtime_auction_cache", read_cache)
    monkeypatch.setattr(api_app, "_build_live_w2s_auction_material", build_live)
    monkeypatch.setattr(api_app, "_write_realtime_auction_cache", write_cache)
    monkeypatch.setattr(api_app, "_persist_pre_market_auction_snapshots", persist_rows)

    auctions, meta = await api_app._load_w2s_auctions_for_confirm(
        date(2026, 5, 4),
        date(2026, 4, 30),
        [{"stock_id": "000001.SZ"}],
    )

    assert len(auctions) == 1
    assert meta["channel"] == "realtime_online_fetch"
    assert meta["cache_writes"] == 1
    assert meta["persisted_rows"] == 1
    assert seen["read_cache"] == (date(2026, 5, 4), ("000001.SZ",))
    assert seen["build_live"] == (date(2026, 5, 4), date(2026, 4, 30), 1)
    assert seen["write_cache"] == (date(2026, 5, 4), 1, 1)
    assert seen["persist_rows"] == 1


@pytest.mark.asyncio
async def test_load_w2s_auctions_for_confirm_uses_db_channel_after_0930(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = cls(2026, 5, 4, 9, 31, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            if tz is None:
                return current.replace(tzinfo=None)
            return current.astimezone(tz)

    class FakeReadPort:
        async def get_stock_auction_snapshot(self, confirm_trade_date: date, stock_ids=None):
            assert confirm_trade_date == date(2026, 5, 4)
            assert stock_ids == ["000001.SZ"]
            return [
                StockAuctionDTO(
                    trade_date=confirm_trade_date,
                    stock_id="000001.SZ",
                    auction_open_pct=Decimal("1"),
                    auction_amount=Decimal("1000000"),
                    tail_auction_vwap=Decimal("10"),
                )
            ]

    monkeypatch.setattr(api_app, "datetime", FixedDateTime)
    api_app.app.state.read_port = FakeReadPort()

    auctions, meta = await api_app._load_w2s_auctions_for_confirm(
        date(2026, 5, 4),
        date(2026, 4, 30),
        [{"stock_id": "000001.SZ"}],
    )

    assert len(auctions) == 1
    assert meta["channel"] == "db"
    assert meta["cache_writes"] == 0
    assert meta["persisted_rows"] == 0


@pytest.mark.asyncio
async def test_get_stock_screener_result_supports_snapshot_result_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def build_detail(candidate_trade_date: date, stock_id: str, *, confirm_trade_date=None, view=None):
        assert candidate_trade_date == date(2026, 4, 29)
        assert confirm_trade_date == date(2026, 4, 30)
        assert stock_id == "000001.SZ"
        assert view == "confirm"
        return {
            "result_id": "w2s_2026-04-29__2026-04-30__000001.SZ",
            "stock_id": "000001.SZ",
            "stock_name": "平安银行",
            "weak_to_strong": {
                "detail_view": "confirm",
                "candidate_trade_date": "2026-04-29",
                "confirm_trade_date": "2026-04-30",
                "signal_level": "A",
            },
            "weak_to_strong_replay": {
                "candidate_evidence": {"foo": "bar"},
                "signal_evidence": {"baz": "qux"},
            },
        }

    monkeypatch.setattr(api_app, "_build_w2s_result_detail_from_snapshot", build_detail)

    result = await api_app.get_stock_screener_result("w2s_2026-04-29__2026-04-30__000001.SZ", view="confirm")

    assert result["result_id"] == "w2s_2026-04-29__2026-04-30__000001.SZ"
    assert result["stock_id"] == "000001.SZ"
    assert result["weak_to_strong"]["detail_view"] == "confirm"
    assert result["weak_to_strong"]["candidate_trade_date"] == "2026-04-29"
    assert result["weak_to_strong"]["confirm_trade_date"] == "2026-04-30"
    assert result["weak_to_strong"]["signal_level"] == "A"
    assert result["weak_to_strong_replay"]["candidate_evidence"] == {"foo": "bar"}
    assert result["weak_to_strong_replay"]["signal_evidence"] == {"baz": "qux"}

from __future__ import annotations

from stock_service.adapters.tushare_adapter import TushareAdapter


class _FakePro:
    def __init__(self):
        self.calls = []

    def daily(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


def test_fetch_daily_quotes_batches_ts_codes(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakePro()
    monkeypatch.setattr(adapter, "_client", lambda: fake)

    result = adapter.fetch_daily_quotes(
        "2026-04-01",
        [f"{i:06d}.SZ" for i in range(1, 26)],
    )

    assert len(fake.calls) == 2
    assert fake.calls[0]["trade_date"] == "20260401"
    assert len(fake.calls[0]["ts_code"].split(",")) == 20
    assert len(fake.calls[1]["ts_code"].split(",")) == 5
    assert result is not None


def test_query_with_retry_retries_once_then_succeeds(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=1, pause_seconds=0)

    class _RetryPro:
        def __init__(self):
            self.count = 0

        def limit_list_d(self, **kwargs):
            self.count += 1
            if self.count == 1:
                raise TimeoutError("timeout")
            return kwargs

    pro = _RetryPro()
    monkeypatch.setattr(adapter, "_client", lambda: pro)

    result = adapter.fetch_limit_list("2026-04-01")

    assert pro.count == 2
    assert result["trade_date"] == "20260401"


def test_fetch_top_list_batches_ts_codes(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakePro()
    monkeypatch.setattr(adapter, "_client", lambda: fake)
    fake.top_list = fake.daily

    result = adapter.fetch_top_list("2026-04-01", [f"{i:06d}.SZ" for i in range(1, 26)])

    assert len(fake.calls) == 2
    assert fake.calls[0]["trade_date"] == "20260401"
    assert len(fake.calls[0]["ts_code"].split(",")) == 20
    assert result is not None


def test_fetch_top_inst_batches_ts_codes(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakePro()
    monkeypatch.setattr(adapter, "_client", lambda: fake)
    fake.top_inst = fake.daily

    result = adapter.fetch_top_inst("2026-04-01", [f"{i:06d}.SZ" for i in range(1, 23)])

    assert len(fake.calls) == 2
    assert fake.calls[1]["trade_date"] == "20260401"
    assert len(fake.calls[1]["ts_code"].split(",")) == 2
    assert result is not None


def test_fetch_stk_auction_normalizes_plain_stock_ids(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakePro()
    monkeypatch.setattr(adapter, "_client", lambda: fake)
    fake.stk_auction = fake.daily

    result = adapter.fetch_stk_auction("2026-04-03", ["300839", "600339", "830001"])

    assert len(fake.calls) == 1
    assert fake.calls[0]["trade_date"] == "20260403"
    assert fake.calls[0]["ts_code"] == "300839.SZ,600339.SH,830001.BJ"
    assert result is not None


def test_fetch_stk_auction_c_normalizes_plain_stock_ids(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakePro()
    monkeypatch.setattr(adapter, "_client", lambda: fake)
    fake.stk_auction_c = fake.daily

    result = adapter.fetch_stk_auction_c("2026-04-03", ["300839", "600339", "830001"])

    assert len(fake.calls) == 1
    assert fake.calls[0]["trade_date"] == "20260403"
    assert fake.calls[0]["ts_code"] == "300839.SZ,600339.SH,830001.BJ"
    assert result is not None

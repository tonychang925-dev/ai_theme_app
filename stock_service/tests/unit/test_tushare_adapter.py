from __future__ import annotations

import pandas as pd
import pytest

from stock_service.adapters.tushare_adapter import TushareAdapter


def test_adapter_normalizes_wrapped_token():
    adapter = TushareAdapter("  'token'  ", timeout=10, retry_count=0, pause_seconds=0)

    assert adapter.token == "token"


class _FakeQuery:
    def __init__(self):
        self.calls = []

    def __call__(self, api_name: str, **kwargs):
        self.calls.append({"api_name": api_name, **kwargs})
        return pd.DataFrame([kwargs])


def test_fetch_daily_quotes_batches_ts_codes(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakeQuery()
    monkeypatch.setattr(adapter, "_query", fake)

    result = adapter.fetch_daily_quotes(
        "2026-04-01",
        [f"{i:06d}.SZ" for i in range(1, 26)],
    )

    assert len(fake.calls) == 2
    assert fake.calls[0]["api_name"] == "daily"
    assert fake.calls[0]["trade_date"] == "20260401"
    assert len(fake.calls[0]["ts_code"].split(",")) == 20
    assert len(fake.calls[1]["ts_code"].split(",")) == 5
    assert result is not None


def test_query_with_retry_retries_once_then_succeeds(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=1, pause_seconds=0)

    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    calls = {"count": 0}

    def _post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("timeout")
        return _Response({"code": 0, "data": {"fields": ["trade_date"], "items": [["20260401"]]}})

    monkeypatch.setattr("stock_service.adapters.tushare_adapter.requests.post", _post)

    result = adapter.fetch_limit_list("2026-04-01")

    assert calls["count"] == 2
    assert result.to_dict(orient="records") == [{"trade_date": "20260401"}]


def test_query_includes_http_and_tushare_error_context(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=1, pause_seconds=0)

    class _Response:
        def __init__(self, payload, *, status_code=200, text=""):
            self.payload = payload
            self.status_code = status_code
            self.text = text

        def json(self):
            return self.payload

    calls = {"count": 0}

    def _post(*args, **kwargs):
        calls["count"] += 1
        return _Response(
            {
                "code": 1,
                "msg": "invalid token",
                "data": {"fields": [], "items": []},
            },
            status_code=403,
            text='{"code":1,"msg":"invalid token"}',
        )

    monkeypatch.setattr("stock_service.adapters.tushare_adapter.requests.post", _post)

    with pytest.raises(RuntimeError) as exc_info:
        adapter.fetch_top_list("2026-04-01")

    message = str(exc_info.value)
    assert calls["count"] == 2
    assert "api=top_list" in message
    assert "attempts=2" in message
    assert "http_status=403" in message
    assert "tushare_code=1" in message
    assert "tushare_msg=invalid token" in message
    assert 'response_text={"code":1,"msg":"invalid token"}' in message
    assert "last_error=RuntimeError: tushare returned error: code=1 msg=invalid token" in message


def test_fetch_top_list_batches_ts_codes(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakeQuery()
    monkeypatch.setattr(adapter, "_query", fake)

    result = adapter.fetch_top_list("2026-04-01", [f"{i:06d}.SZ" for i in range(1, 26)])

    assert len(fake.calls) == 2
    assert fake.calls[0]["api_name"] == "top_list"
    assert fake.calls[0]["trade_date"] == "20260401"
    assert len(fake.calls[0]["ts_code"].split(",")) == 20
    assert result is not None


def test_fetch_top_inst_batches_ts_codes(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakeQuery()
    monkeypatch.setattr(adapter, "_query", fake)

    result = adapter.fetch_top_inst("2026-04-01", [f"{i:06d}.SZ" for i in range(1, 23)])

    assert len(fake.calls) == 2
    assert fake.calls[1]["api_name"] == "top_inst"
    assert fake.calls[1]["trade_date"] == "20260401"
    assert len(fake.calls[1]["ts_code"].split(",")) == 2
    assert result is not None


def test_fetch_stk_auction_normalizes_plain_stock_ids(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakeQuery()
    monkeypatch.setattr(adapter, "_query", fake)

    result = adapter.fetch_stk_auction("2026-04-03", ["300839", "600339", "830001"])

    assert len(fake.calls) == 1
    assert fake.calls[0]["api_name"] == "stk_auction"
    assert fake.calls[0]["trade_date"] == "20260403"
    assert fake.calls[0]["ts_code"] == "300839.SZ,600339.SH,830001.BJ"
    assert result is not None


def test_fetch_stk_auction_c_normalizes_plain_stock_ids(monkeypatch):
    adapter = TushareAdapter("token", timeout=10, retry_count=0, pause_seconds=0)
    fake = _FakeQuery()
    monkeypatch.setattr(adapter, "_query", fake)

    result = adapter.fetch_stk_auction_c("2026-04-03", ["300839", "600339", "830001"])

    assert len(fake.calls) == 1
    assert fake.calls[0]["api_name"] == "stk_auction_c"
    assert fake.calls[0]["trade_date"] == "20260403"
    assert fake.calls[0]["ts_code"] == "300839.SZ,600339.SH,830001.BJ"
    assert result is not None

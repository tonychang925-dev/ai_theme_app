from __future__ import annotations

import math
import time
from typing import Iterable, Optional

import pandas as pd
import requests


TUSHARE_URL = "https://api.tushare.pro"


def _normalize_ts_code(value: str) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    if "." in raw:
        return raw
    if raw.startswith(("6", "9")):
        return f"{raw}.SH"
    if raw.startswith(("4", "8")):
        return f"{raw}.BJ"
    return f"{raw}.SZ"


class TushareAdapter:
    """Tushare adapter using direct HTTP to api.tushare.pro."""

    def __init__(self, token: str, *, timeout: int = 60, retry_count: int = 2, pause_seconds: float = 0.5):
        self.token = str(token or "").strip().strip("\"'").strip()
        self.timeout = timeout
        self.retry_count = retry_count
        self.pause_seconds = pause_seconds

    def fetch_daily_history(self, ts_code: str, start_date: str, end_date: str):
        return self._query("daily", ts_code=_normalize_ts_code(ts_code),
                           start_date=start_date.replace("-", ""),
                           end_date=end_date.replace("-", ""))

    def fetch_daily_quotes(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("daily", trade_date.replace("-", ""), ts_codes)

    def fetch_limit_list(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._query("limit_list_d", trade_date=trade_date.replace("-", ""))

    def fetch_top_list(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("top_list", trade_date.replace("-", ""), ts_codes)

    def fetch_top_inst(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("top_inst", trade_date.replace("-", ""), ts_codes)

    def fetch_stk_auction(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("stk_auction", trade_date.replace("-", ""), ts_codes)

    def fetch_stk_auction_c(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("stk_auction_c", trade_date.replace("-", ""), ts_codes)

    def _fetch_batched(self, api_name: str, trade_date_compact: str, ts_codes: Optional[Iterable[str]]):
        if not ts_codes:
            return self._query(api_name, trade_date=trade_date_compact)
        codes = [_normalize_ts_code(str(x)) for x in ts_codes if str(x or "").strip()]
        if not codes:
            return self._query(api_name, trade_date=trade_date_compact)
        merged = None
        for i in range(0, len(codes), 20):
            chunk = codes[i:i + 20]
            frame = self._query(api_name, ts_code=",".join(chunk), trade_date=trade_date_compact)
            if frame is not None:
                merged = frame if merged is None else pd.concat([merged, frame], ignore_index=True)
            if i + 20 < len(codes) and self.pause_seconds > 0:
                time.sleep(self.pause_seconds)
        return merged

    @staticmethod
    def _truncate_text(value: object, *, limit: int = 240) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}…"

    def _query(self, api_name: str, **kwargs):
        payload = {"api_name": api_name, "token": self.token, "params": kwargs, "fields": ""}
        last_exc = None
        last_status_code = None
        last_tushare_code = None
        last_tushare_msg = None
        last_response_text = None
        for attempt in range(self.retry_count + 1):
            resp = None
            try:
                resp = requests.post(TUSHARE_URL, json=payload, timeout=self.timeout)
                last_status_code = getattr(resp, "status_code", None)
                result = resp.json()
                if not isinstance(result, dict):
                    raise RuntimeError(f"unexpected tushare payload type: {type(result).__name__}")
                last_tushare_code = result.get("code")
                last_tushare_msg = result.get("msg")
                if result.get("code") != 0:
                    raise RuntimeError(
                        f"tushare returned error: code={result.get('code')} msg={result.get('msg', 'unknown error')}"
                    )
                data = result.get("data", {})
                if not data or not data.get("items"):
                    return None
                return pd.DataFrame(data["items"], columns=data["fields"])
            except Exception as exc:
                last_exc = exc
                if last_response_text is None:
                    if resp is not None:
                        last_response_text = self._truncate_text(getattr(resp, "text", ""))
                if attempt >= self.retry_count:
                    break
                if self.pause_seconds > 0:
                    time.sleep(self.pause_seconds * (attempt + 1))
        attempts = self.retry_count + 1
        error_parts = [
            f"tushare query failed: api={api_name}",
            f"kwargs={kwargs}",
            f"attempts={attempts}",
        ]
        if last_status_code is not None:
            error_parts.append(f"http_status={last_status_code}")
        if last_tushare_code is not None:
            error_parts.append(f"tushare_code={last_tushare_code}")
        if last_tushare_msg:
            error_parts.append(f"tushare_msg={self._truncate_text(last_tushare_msg)}")
        if last_response_text:
            error_parts.append(f"response_text={last_response_text}")
        if last_exc is not None:
            error_parts.append(f"last_error={type(last_exc).__name__}: {self._truncate_text(last_exc)}")
        raise RuntimeError(" ".join(error_parts)) from last_exc

    @staticmethod
    def to_records(frame) -> list[dict]:
        if frame is None:
            return []
        if isinstance(frame, dict):
            return [frame]
        if isinstance(frame, list):
            return [item for item in frame if isinstance(item, dict)]
        if not hasattr(frame, "to_dict"):
            raise TypeError("unsupported tushare response type: missing to_dict(orient='records')")
        records = frame.to_dict(orient="records")
        for r in records:
            for k, v in r.items():
                if isinstance(v, float) and math.isnan(v):
                    r[k] = None
        return records

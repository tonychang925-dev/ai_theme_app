from __future__ import annotations

import time
from typing import Iterable, Optional


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
    """
    Tushare adapter skeleton.

    当前阶段目标是先冻结接入边界，不把外部数据源直接耦合进报告逻辑。
    后续只需要在这里补全：
    - daily / adj_factor / limit_list
    - concept / moneyflow / top_inst
    """

    def __init__(self, token: str, *, timeout: int = 60, retry_count: int = 2, pause_seconds: float = 0.5):
        self.token = token
        self.timeout = timeout
        self.retry_count = retry_count
        self.pause_seconds = pause_seconds
        self._pro = None

    def _client(self):
        if self._pro is not None:
            return self._pro
        if not self.token:
            raise RuntimeError("missing TUSHARE_TOKEN")
        try:
            import tushare as ts  # type: ignore
        except Exception as exc:
            raise RuntimeError("tushare package not installed") from exc
        ts.set_token(self.token)
        self._pro = ts.pro_api(token=self.token, timeout=self.timeout)
        return self._pro

    def fetch_daily_quotes(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        trade_date_compact = trade_date.replace("-", "")
        return self._fetch_batched("daily", trade_date_compact, ts_codes)

    def fetch_daily_history(self, ts_code: str, start_date: str, end_date: str):
        normalized_code = _normalize_ts_code(ts_code)
        return self._query_with_retry(
            "daily",
            ts_code=normalized_code,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    def fetch_limit_list(self, trade_date: str):
        return self._query_with_retry("limit_list_d", trade_date=trade_date.replace("-", ""))

    def fetch_top_list(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("top_list", trade_date.replace("-", ""), ts_codes)

    def fetch_top_inst(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("top_inst", trade_date.replace("-", ""), ts_codes)

    def fetch_stk_auction(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("stk_auction", trade_date.replace("-", ""), ts_codes)

    def fetch_stk_auction_c(self, trade_date: str, ts_codes: Optional[Iterable[str]] = None):
        return self._fetch_batched("stk_auction_c", trade_date.replace("-", ""), ts_codes)

    def _fetch_batched(self, api_name: str, trade_date_compact: str, ts_codes: Optional[Iterable[str]] = None):
        if not ts_codes:
            return self._query_with_retry(api_name, trade_date=trade_date_compact)

        batches = []
        batch: list[str] = []
        for ts_code in ts_codes:
            value = _normalize_ts_code(str(ts_code or ""))
            if not value:
                continue
            batch.append(value)
            if len(batch) >= 20:
                batches.append(batch)
                batch = []
        if batch:
            batches.append(batch)

        frames = []
        for batch_codes in batches:
            frame = self._query_with_retry(
                api_name,
                trade_date=trade_date_compact,
                ts_code=",".join(batch_codes),
            )
            frames.append(frame)
            if self.pause_seconds > 0:
                time.sleep(self.pause_seconds)

        if not frames:
            return None
        if len(frames) == 1:
            return frames[0]

        try:
            import pandas as pd  # type: ignore

            return pd.concat(frames, ignore_index=True)
        except Exception:
            merged: list[dict] = []
            for frame in frames:
                merged.extend(self.to_records(frame))
            return merged

    def _query_with_retry(self, api_name: str, **kwargs):
        pro = self._client()
        last_exc = None
        for attempt in range(self.retry_count + 1):
            try:
                return getattr(pro, api_name)(**kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt >= self.retry_count:
                    break
                if self.pause_seconds > 0:
                    time.sleep(self.pause_seconds * (attempt + 1))
        raise RuntimeError(f"tushare query failed: api={api_name} kwargs={kwargs}") from last_exc

    @staticmethod
    def to_records(frame) -> list[dict]:
        if frame is None:
            return []
        if isinstance(frame, dict):
            return [frame]
        if isinstance(frame, list):
            return [item for item in frame if isinstance(item, dict)]
        if hasattr(frame, "to_dict"):
            return list(frame.to_dict(orient="records"))
        raise TypeError("unsupported tushare response type: missing to_dict(orient='records')")

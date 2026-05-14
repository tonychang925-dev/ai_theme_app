from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from services.jyhf_cdp_service.schemas import RawJyhfCdpEvent


CN_TZ = ZoneInfo("Asia/Shanghai")


class JyhfEventNormalizer:
    def normalize(self, event: dict, feed_date: str, capture_time: datetime | None = None) -> RawJyhfCdpEvent:
        capture_time = capture_time or datetime.now(CN_TZ)
        trade_date = self._extract_trade_date(feed_date) or capture_time.date().isoformat()
        pct_text = str(event.get("pct_chg_text") or "0").replace("%", "").replace("+", "")
        try:
            pct_chg = float(pct_text)
        except Exception:
            pct_chg = None
        subject_name = str(event.get("subject_name") or "").strip()
        driver_title = str(event.get("driver_title") or "").strip()
        driver_desc = str(event.get("driver_desc") or "").strip()
        dedup_key = self._dedup_key(
            trade_date=trade_date,
            event_time=str(event.get("event_time") or ""),
            subject_name=subject_name,
            driver_title=driver_title,
            driver_desc=driver_desc,
        )
        return RawJyhfCdpEvent(
            event_id=f"jyhf_cdp_{trade_date.replace('-', '')}_{dedup_key[:12]}",
            dedup_key=dedup_key,
            capture_time=capture_time.isoformat(),
            trade_date=trade_date,
            event_time=str(event.get("event_time") or ""),
            subject_name=subject_name,
            subject_key=None,
            pct_chg=pct_chg,
            driver_title=driver_title,
            driver_desc=driver_desc,
            news_source=str(event.get("news_source") or "") or None,
            event_type=str(event.get("event_type") or "驱动事件"),
            raw_text=str(event.get("raw_text") or ""),
        )

    @staticmethod
    def _extract_trade_date(feed_date: str) -> str | None:
        import re

        match = re.search(r"\d{4}-\d{2}-\d{2}", feed_date or "")
        return match.group(0) if match else None

    @staticmethod
    def _dedup_key(*, trade_date: str, event_time: str, subject_name: str, driver_title: str, driver_desc: str) -> str:
        raw = "|".join([trade_date, event_time, subject_name, driver_title, driver_desc])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


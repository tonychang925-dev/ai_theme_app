from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from stock_processing_service import api_app


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *args, **kwargs):
        return self._rows


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


class _FakeReportContextClient:
    def __init__(self, report_context):
        self._report_context = report_context

    async def get_post_market_report_context(self, trade_date):
        return self._report_context


@pytest.mark.asyncio
async def test_enrich_recap_doc_with_new_high_summary_recomputes_from_snapshot(monkeypatch) -> None:
    rows = [
        {"trade_date": date(2026, 6, 17), "stock_key": "600703", "high_price": 15.2, "stock_name": "三安光电", "industry_name": "化合物半导体"},
        {"trade_date": date(2026, 6, 17), "stock_key": "000725", "high_price": 22.8, "stock_name": "京东方A", "industry_name": "显示面板"},
        {"trade_date": date(2026, 6, 16), "stock_key": "300475", "high_price": 245.0, "stock_name": "香农芯创", "industry_name": "电子元器件分销"},
        {"trade_date": date(2026, 6, 15), "stock_key": "300475", "high_price": 243.0, "stock_name": "香农芯创", "industry_name": "电子元器件分销"},
    ]
    conn = _FakeConn(rows)
    monkeypatch.setattr(
        api_app.app,
        "state",
        SimpleNamespace(gateway=SimpleNamespace(_client=SimpleNamespace(pool=_FakePool(conn)))),
        raising=False,
    )

    enriched = await api_app._enrich_recap_doc_with_new_high_summary(date(2026, 6, 17), {})

    summary = enriched["new_high_summary"]
    assert summary["today_count"] == 2
    assert summary["yesterday_count"] == 1
    assert summary["day_before_count"] == 1
    assert summary["representative_stocks"]
    assert summary["industry_summary"][0]["industry_name"] in {"化合物半导体", "显示面板"}
    assert summary["diagnostics"]["source"] == "recomputed_from_stock_daily_snapshot"
    assert summary["diagnostics"]["classified_count"] == 2
    assert summary["diagnostics"]["unclassified_count"] == 0
    assert summary["diagnostics"]["classification_rate"] == 1.0


@pytest.mark.asyncio
async def test_new_high_summary_discloses_low_industry_classification_coverage() -> None:
    rows = [
        {"trade_date": date(2026, 7, 3), "stock_key": "000001", "high_price": 10, "stock_name": "已分类股", "industry_name": "工业机器人"},
        {"trade_date": date(2026, 7, 3), "stock_key": "000002", "high_price": 11, "stock_name": "未分类甲", "industry_name": ""},
        {"trade_date": date(2026, 7, 3), "stock_key": "000003", "high_price": 12, "stock_name": "未分类乙", "industry_name": ""},
    ]

    enriched = await api_app._build_new_high_summary_from_conn(
        date(2026, 7, 3),
        {},
        _FakeConn(rows),
    )

    summary = enriched["new_high_summary"]
    assert "行业已识别 1 家（33%）" in summary["summary"]
    assert summary["diagnostics"]["classified_count"] == 1
    assert summary["diagnostics"]["unclassified_count"] == 2


@pytest.mark.asyncio
async def test_enrich_recap_doc_with_seat_money_context_injects_structured_rows(monkeypatch) -> None:
    report_context = {
        "dragon_tiger": [
            {
                "stock_code": "688766",
                "stock_name": "普冉股份",
                "theme_name": "存储芯片",
                "seat_type": "INSTITUTION",
                "institution_seat_count": 3,
                "buy_amount": 989430000,
                "sell_amount": 376270000,
                "net_buy": 613160000,
                "seat_summary": [
                    {
                        "seat_name": "机构专用",
                        "side": "0",
                        "side_label": "买入席位",
                        "buy_amount": 560000000,
                        "sell_amount": 120000000,
                        "net_buy": 440000000,
                    }
                ],
            }
        ],
        "hot_money_activities": [
            {
                "hot_money_name": "紫阳东路",
                "seat_name": "紫阳东路",
                "stock_id": "000001",
                "stock_name": "平安银行",
                "subject_key": "bank",
                "theme_name": "银行",
                "side": "买入",
                "buy_amount": 36700000,
                "sell_amount": 0,
                "net_amount": 36700000,
                "reason": "机构席位观察",
                "rank_order": 1,
                "is_theme_leader": True,
                "style_tags": ["接力"],
            }
        ],
    }
    monkeypatch.setattr(
        api_app.app,
        "state",
        SimpleNamespace(gateway=SimpleNamespace(_client=_FakeReportContextClient(report_context))),
        raising=False,
    )

    enriched = await api_app._enrich_recap_doc_with_seat_money_context(date(2026, 6, 18), {})
    from stock_processing_service.application.services.post_market_daily_review_v2_builder import (
        PostMarketDailyReviewV2Builder,
    )

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 18),
        recap_doc=enriched,
        snapshot_version="daily_review_v2.seat.context",
    )

    seat = payload["seat_money_summary"]
    assert seat["diagnostics"]["source"] == "structured"
    assert seat["institution_top_buys"]
    assert seat["hot_money_top_buys"]
    assert "机构关注" in seat["summary"]
    assert "游资关注" in seat["summary"]

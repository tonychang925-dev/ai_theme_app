from __future__ import annotations

from datetime import date

from stock_processing_service.application.services.f10_capital_evidence_service import (
    F10CapitalEvidenceService,
)
from stock_processing_service.application.services.f10_capital_parser import F10CapitalParser


SAMPLE_F10_TEXT = """资金动向☆ ◇000001 平安银行 更新日期：2026-06-14◇ 通达信沪深京F10
★本栏包括【1.交易龙虎榜】【2.大宗交易】【3.融资融券】【4.资金流向】
          【5.战略配售可出借】

【1.交易龙虎榜】
 最近1年内该股未能登上龙虎榜。

【2.大宗交易】 暂无数据

【3.融资融券】
截止2026-06-12，可充抵保证金最高折算率为65.00%
2026-06-11融资融券信息：融资偿还额1.11亿元，融资净买额-793.57万元，融券余量207.12万股，融券偿还量2.03万股
交易日期         融资余额(万)   融资买入额(万)     融券余额(万)   融券卖出量(万) 融资融券余额(万)
─────────────────────────────────────────────────
2026-06-11          521528.51         10328.05          2340.46            20.28        523868.97

【4.资金流向】
2026-06-12│ 2272.10万│    1.00│-8264.63万│   -3.65│    1.05亿│    4.65│    4.57亿│   20.20

【5.战略配售可出借】
暂无数据
"""


def test_f10_capital_parser_splits_sections_and_parses_summary() -> None:
    parser = F10CapitalParser()
    snapshot = parser.parse(
        stock_id="000001.SZ",
        stock_name="平安银行",
        trade_date=date(2026, 6, 14),
        source_updated_date=date(2026, 6, 14),
        raw_text=SAMPLE_F10_TEXT,
    )

    assert snapshot["stock_id"] == "000001"
    assert snapshot["parse_status"] == "ok"
    assert snapshot["dragon_tiger_json"]["has_lhb"] is False
    assert "最近1年内该股未能登上龙虎榜" in snapshot["dragon_tiger_json"]["summary"]
    assert snapshot["margin_trading_json"]["latest_date"] == "2026-06-11"
    assert snapshot["capital_flow_json"]["latest_date"] == "2026-06-12"
    assert snapshot["capital_flow_json"]["main_net_inflow"] == 22721000.0
    assert len(snapshot["diagnostics"]["section_hits"]) == 5


def test_f10_capital_evidence_service_attaches_snapshot() -> None:
    service = F10CapitalEvidenceService()
    snapshot = service.build_snapshot_row(
        trade_date=date(2026, 6, 14),
        stock_id="000001.SZ",
        stock_name="平安银行",
        raw_text=SAMPLE_F10_TEXT,
        source_updated_date=date(2026, 6, 14),
    )
    evidence = service.snapshot_to_evidence(snapshot)
    assert evidence is not None
    assert evidence["available"] is True
    assert "主力净流入2272.10万" in evidence["summary"]
    assert "龙虎榜" not in evidence["summary"]

    recap_doc = {
        "money_flow_reviews": [{"stock_id": "000001.SZ"}],
        "stock_capital_reviews": [{"stock_id": "000001"}],
        "dragon_tiger_reviews": [{"stock_code": "000001"}],
        "daily_review_v2": {
            "money_flow_reviews": [{"stock_id": "000001.SZ"}],
            "stock_capital_reviews": [{"stock_id": "000001"}],
            "dragon_tiger_reviews": [{"stock_code": "000001"}],
            "watchlist_reviews": [{"stock_id": "000001"}],
        },
    }
    attached = service.attach_to_recap_doc(recap_doc, {"000001": snapshot})
    assert attached["money_flow_reviews"] == 1
    assert attached["stock_capital_reviews"] == 1
    assert attached["dragon_tiger_reviews"] == 1
    assert attached["daily_review_v2.stock_capital_reviews"] == 1
    assert recap_doc["money_flow_reviews"][0]["f10_capital"]["available"] is True
    assert recap_doc["stock_capital_reviews"][0]["f10_capital"]["stock_id"] == "000001"
    assert recap_doc["daily_review_v2"]["stock_capital_reviews"][0]["f10_capital"]["stock_id"] == "000001"


def test_f10_capital_evidence_service_handles_stringified_json_snapshot() -> None:
    service = F10CapitalEvidenceService()
    snapshot = {
        "trade_date": "2026-06-12",
        "stock_id": "301176",
        "stock_name": "逸豪新材",
        "source": "tdx_f10",
        "section": "资金动向",
        "source_updated_date": "2026-06-14",
        "dragon_tiger_json": '{"has_lhb": false, "summary": "最近1年内该股未能登上龙虎榜", "details": []}',
        "block_trade_json": '{"summary": "暂无数据", "details": []}',
        "margin_trading_json": '{"latest_date": "2026-06-11", "summary": "融资净买额-793.57万元", "details": []}',
        "capital_flow_json": '{"latest_date": "2026-06-12", "main_net_inflow": 22721000.0, "summary": "主力净流入2272.10万", "details": []}',
        "strategic_lending_json": '{"summary": "暂无数据", "details": []}',
        "raw_text": "资金动向...",
        "diagnostics": '{"section_hits": ["1.交易龙虎榜"]}',
    }

    evidence = service.snapshot_to_evidence(snapshot)
    assert evidence is not None
    assert evidence["stock_id"] == "301176"
    assert evidence["dragon_tiger"]["has_lhb"] is False
    assert evidence["capital_flow"]["main_net_inflow"] == 22721000.0
    assert "主力净流入2272.10万" in evidence["summary"]
    assert "龙虎榜" not in evidence["summary"]

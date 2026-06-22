from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from stock_processing_service.application.services.limit_up_theme_matrix_builder import (
    LimitUpThemeMatrixBuilder,
)


class _FakeConn:
    def __init__(self, trade_date: date) -> None:
        self.trade_date = trade_date
        self.queries: list[str] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = " ".join(query.lower().split())
        self.queries.append(q)
        assert "stock_facts" not in q
        assert "strong_stock_reviews" not in q
        assert "market_overview_review" not in q
        assert "limit_up_theme_events" not in q
        assert "theme_master" not in q

        if "from stock_daily_snapshot" in q and "trade_date = $1::date" in q and "pct_chg" in q and ">= $2" in q:
            return [
                {
                    "stock_key": "000001",
                    "stock_id": "000001.SZ",
                    "stock_name": "PCB龙头",
                    "close_price": 12.3,
                    "pct_chg": 10.01,
                    "amount": 100000000,
                },
                {
                    "stock_key": "000003",
                    "stock_id": "000003.SZ",
                    "stock_name": "无映射股",
                    "close_price": 7.8,
                    "pct_chg": 9.99,
                    "amount": 50000000,
                },
            ]

        if "from stock_daily_snapshot" in q and "trade_date <= $1::date" in q:
            return [
                {"stock_key": "000001", "trade_date": self.trade_date, "pct_chg": 10.01},
                {"stock_key": "000001", "trade_date": self.trade_date - timedelta(days=1), "pct_chg": 10.0},
                {"stock_key": "000001", "trade_date": self.trade_date - timedelta(days=2), "pct_chg": 9.8},
                {"stock_key": "000001", "trade_date": self.trade_date - timedelta(days=3), "pct_chg": 0.5},
                {"stock_key": "000003", "trade_date": self.trade_date, "pct_chg": 9.99},
            ]

        if "from subject_stock_map" in q:
            return [
                {
                    "stock_id": "000001",
                    "subject_key": "pcb",
                    "sort": 1,
                    "top": 1,
                    "source_type": "db",
                    "confidence": 1.0,
                    "reason": "确定映射",
                }
            ]

        if "from subject_node_staging" in q:
            return [{"subject_key": "pcb", "theme_name": "PCB印制电路板"}]

        if "from stocks" in q:
            return [
                {"stock_key": "000001", "stock_name": "PCB龙头"},
                {"stock_key": "000003", "stock_name": "无映射股"},
            ]

        if "from stock_theme_reason_evidence" in q:
            return []

        if "from ths_hot_reason_snapshot" in q:
            return []

        if "from mainline_daily_state" in q:
            return [
                {
                    "canonical_subject_key": "pcb",
                    "mainline_name": "PCB印制电路板",
                    "active_subject_keys_json": ["pcb", "PCB印制电路板"],
                    "lifecycle_state": "divergence",
                    "mainline_alive": True,
                    "mainline_trade_alive": True,
                    "trade_mode": "mainline_core_only",
                    "allow_trade": True,
                }
            ]

        if "from mainline_registry" in q:
            return []

        if "from subject_rank_daily" in q:
            return [{"subject_key": "pcb", "heat_name": "PCB印制电路板"}]

        if "from theme_mainline_identity_registry" in q or "from theme_detail_snapshot" in q:
            return []

        raise AssertionError(f"unexpected query: {query}")


class _PrimaryMainlineFakeConn(_FakeConn):
    def __init__(self, trade_date: date, *, scenario: str) -> None:
        super().__init__(trade_date)
        self.scenario = scenario

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = " ".join(query.lower().split())
        self.queries.append(q)
        assert "stock_facts" not in q
        assert "strong_stock_reviews" not in q
        assert "market_overview_review" not in q
        assert "limit_up_theme_events" not in q
        assert "theme_master" not in q

        if "from stock_daily_snapshot" in q and "trade_date = $1::date" in q and "pct_chg" in q and ">= $2" in q:
            return [
                {
                    "stock_key": "000001",
                    "stock_id": "000001.SZ",
                    "stock_name": "多义股",
                    "close_price": 12.3,
                    "pct_chg": 10.01,
                    "amount": 100000000,
                }
            ]

        if "from stock_daily_snapshot" in q and "trade_date <= $1::date" in q:
            return [{"stock_key": "000001", "trade_date": self.trade_date, "pct_chg": 10.01}]

        if "from subject_stock_map" in q:
            if self.scenario == "canonical_priority":
                return [
                    {"stock_id": "000001", "subject_key": "canonical-a", "stock_name": "多义股", "sort": 2, "top": 0, "source_type": "db", "confidence": 1.0, "reason": ""},
                    {"stock_id": "000001", "subject_key": "active-b", "stock_name": "多义股", "sort": 1, "top": 0, "source_type": "db", "confidence": 1.0, "reason": ""},
                ]
            return [
                {"stock_id": "000001", "subject_key": "active-a", "stock_name": "多义股", "sort": 1, "top": 0, "source_type": "db", "confidence": 1.0, "reason": ""},
                {"stock_id": "000001", "subject_key": "active-b", "stock_name": "多义股", "sort": 2, "top": 0, "source_type": "db", "confidence": 1.0, "reason": ""},
            ]

        if "from subject_node_staging" in q:
            return []

        if "from stocks" in q:
            return [{"stock_key": "000001", "stock_name": "多义股"}]

        if "from stock_theme_reason_evidence" in q:
            return []

        if "from ths_hot_reason_snapshot" in q:
            return []

        if "from mainline_daily_state" in q:
            return [
                {
                    "id": 1,
                    "canonical_subject_key": "canonical-a",
                    "mainline_name": "主线A",
                    "active_subject_keys_json": ["active-a"],
                    "lifecycle_state": "start",
                    "mainline_alive": True,
                    "mainline_trade_alive": True,
                    "trade_mode": "mainline_core_only",
                    "allow_trade": True,
                },
                {
                    "id": 2,
                    "canonical_subject_key": "canonical-b",
                    "mainline_name": "主线B",
                    "active_subject_keys_json": ["active-b"],
                    "lifecycle_state": "start",
                    "mainline_alive": True,
                    "mainline_trade_alive": True,
                    "trade_mode": "mainline_core_only",
                    "allow_trade": True,
                },
            ]

        if "from mainline_registry" in q:
            return []

        if "from subject_rank_daily" in q:
            return []

        raise AssertionError(f"unexpected query: {query}")


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_uses_snapshot_board_count_and_deterministic_mapping() -> None:
    trade_date = date(2026, 6, 18)
    conn = _FakeConn(trade_date)
    matrix = await LimitUpThemeMatrixBuilder().build(trade_date=trade_date, conn=conn)

    assert matrix["source"] == "limit_up_theme_matrix_builder"
    assert matrix["diagnostics"]["count_method"] == "stock_daily_snapshot_continuous_limit_up"
    assert matrix["diagnostics"]["limit_up_stock_count"] == 2
    assert matrix["diagnostics"]["mapped_stock_count"] == 1
    assert matrix["diagnostics"]["unmapped_stock_count"] == 1
    assert matrix["diagnostics"]["unmapped_stocks"][0]["stock_name"] == "无映射股"

    assert len(matrix["columns"]) == 2
    column = matrix["columns"][0]
    assert column["theme_name"] == "PCB印制电路板"
    assert column["mainline_name"] == "PCB印制电路板"
    assert column["diagnostics"]["mapping_source"] == "mainline_daily_state"
    assert column["limit_up_count"] == 1
    assert column["board_groups"][1]["board_count"] == 3
    assert column["board_groups"][1]["stock_count"] == 1
    assert column["board_groups"][1]["stocks"][0]["stock_name"] == "PCB龙头"

    assert matrix["columns"][1]["theme_name"] == "其他"
    assert matrix["columns"][1]["board_groups"][3]["stocks"][0]["stock_name"] == "无映射股"
    assert matrix["board_totals"] == {"4": 0, "3": 1, "2": 0, "1": 0}
    assert matrix["market_board_totals"] == {"4": 0, "3": 1, "2": 0, "1": 1}
    current_limit_query = next(q for q in conn.queries if "from stock_daily_snapshot" in q and "trade_date = $1::date" in q)
    assert "not like '688%'" in current_limit_query
    assert "not like '920%'" in current_limit_query
    assert "not ilike '%st%'" in current_limit_query


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_does_not_emit_non_limit_up_rows() -> None:
    trade_date = date(2026, 6, 18)
    matrix = await LimitUpThemeMatrixBuilder().build(trade_date=trade_date, conn=_FakeConn(trade_date))
    visible_stock_names = [
        stock["stock_name"]
        for column in matrix["columns"]
        for group in column["board_groups"]
        for stock in group["stocks"]
    ]

    assert "当日未涨停" not in visible_stock_names
    assert "未归类" not in [column["theme_name"] for column in matrix["columns"]]
    assert "__independent__" not in [column["theme_name"] for column in matrix["columns"]]
    assert not any(str(column["theme_name"]).isdigit() for column in matrix["columns"])


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_does_not_assign_one_stock_to_multiple_mainlines() -> None:
    trade_date = date(2026, 6, 18)
    matrix = await LimitUpThemeMatrixBuilder().build(
        trade_date=trade_date,
        conn=_PrimaryMainlineFakeConn(trade_date, scenario="ambiguous_active"),
    )

    assert len(matrix["mainline_columns"]) == 2
    assert [column["theme_name"] for column in matrix["mainline_columns"]] == ["主线A", "主线B"]
    assert [column["theme_name"] for column in matrix["columns"]] == ["其他"]
    assert [column["theme_name"] for column in matrix["visible_columns"]] == ["其他"]
    assert matrix["board_totals"] == {"4": 0, "3": 0, "2": 0, "1": 0}
    assert matrix["diagnostics"]["ambiguous_mainline_stock_count"] == 1
    assert matrix["diagnostics"]["ambiguous_mainline_stocks"][0]["stock_name"] == "多义股"
    assert matrix["diagnostics"]["assignment_audit_rows"][0]["chosen_theme_name"] == "主线A、主线B"
    assert matrix["diagnostics"]["assignment_audit_rows"][0]["chosen_reason"] == "ambiguous_mainline_mapping"


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_prefers_canonical_subject_key_over_active_key() -> None:
    trade_date = date(2026, 6, 18)
    matrix = await LimitUpThemeMatrixBuilder().build(
        trade_date=trade_date,
        conn=_PrimaryMainlineFakeConn(trade_date, scenario="canonical_priority"),
    )

    assert len(matrix["mainline_columns"]) == 2
    assert [column["theme_name"] for column in matrix["mainline_columns"]] == ["主线A", "主线B"]
    assert len(matrix["columns"]) == 1
    assert [column["theme_name"] for column in matrix["visible_columns"]] == ["主线A"]
    assert matrix["columns"][0]["limit_up_count"] == 1
    assert matrix["mainline_columns"][1]["limit_up_count"] == 0
    assert matrix["columns"][0]["board_groups"][3]["stocks"][0]["stock_name"] == "多义股"
    assert matrix["diagnostics"]["ambiguous_mainline_stock_count"] == 0


class _RegistryMainlineFakeConn(_FakeConn):
    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = " ".join(query.lower().split())
        self.queries.append(q)
        assert "stock_facts" not in q
        assert "strong_stock_reviews" not in q
        assert "market_overview_review" not in q
        assert "limit_up_theme_events" not in q
        assert "theme_master" not in q

        if "from stock_daily_snapshot" in q and "trade_date = $1::date" in q and "pct_chg" in q and ">= $2" in q:
            return [
                {
                    "stock_key": "600353",
                    "stock_id": "600353.SH",
                    "stock_name": "旭光电子",
                    "close_price": 1.0,
                    "pct_chg": 10.0,
                    "amount": 100000000,
                }
            ]

        if "from stock_daily_snapshot" in q and "trade_date <= $1::date" in q:
            return [{"stock_key": "600353", "trade_date": self.trade_date, "pct_chg": 10.0}]

        if "from subject_stock_map" in q:
            return [
                {
                    "stock_id": "600353",
                    "subject_key": "9032828",
                    "stock_name": "旭光电子",
                    "sort": 1,
                    "top": 0,
                    "source_type": "jyhf_stock_daily",
                    "confidence": 0.9,
                    "reason": "电子元器件确定映射",
                }
            ]

        if "from subject_node_staging" in q:
            return [{"subject_key": "9032828", "theme_name": "电子元器件"}]

        if "from stocks" in q:
            return [{"stock_key": "600353", "stock_name": "旭光电子"}]

        if "from stock_theme_reason_evidence" in q:
            return []

        if "from ths_hot_reason_snapshot" in q:
            return []

        if "from mainline_daily_state" in q:
            return []

        if "from mainline_registry" in q:
            return [
                {
                    "mainline_id": "ml_9032828_202606",
                    "mainline_name": "电子元器件",
                    "canonical_subject_key": "9032828",
                    "mainline_type": "unknown",
                    "core_subject_keys_json": [],
                    "branch_subject_keys_json": [],
                    "related_subject_keys_json": [],
                }
            ]

        if "from subject_rank_daily" in q:
            return [{"subject_key": "9032828"}]

        raise AssertionError(f"unexpected query: {query}")


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_uses_confirmed_registry_mainline_when_daily_state_missing() -> None:
    trade_date = date(2026, 6, 18)
    matrix = await LimitUpThemeMatrixBuilder().build(
        trade_date=trade_date,
        conn=_RegistryMainlineFakeConn(trade_date),
    )

    assert [column["theme_name"] for column in matrix["mainline_columns"]] == ["电子元器件"]
    assert [column["theme_name"] for column in matrix["columns"]] == ["电子元器件"]
    assert matrix["columns"][0]["subject_key"] == "9032828"
    assert matrix["columns"][0]["board_groups"][3]["stocks"][0]["stock_name"] == "旭光电子"
    assert matrix["diagnostics"]["mapped_stock_count"] == 1
    assert matrix["diagnostics"]["unmapped_stock_count"] == 0


class _M2ReasonPriorityFakeConn(_FakeConn):
    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = " ".join(query.lower().split())
        self.queries.append(q)
        assert "stock_facts" not in q
        assert "strong_stock_reviews" not in q
        assert "market_overview_review" not in q
        assert "limit_up_theme_events" not in q
        assert "theme_master" not in q

        if "from stock_daily_snapshot" in q and "trade_date = $1::date" in q and "pct_chg" in q and ">= $2" in q:
            return [
                {"stock_key": "000811", "stock_id": "000811.SZ", "stock_name": "冰轮环境", "close_price": 40.17, "pct_chg": 9.995, "amount": 17019},
                {"stock_key": "603663", "stock_id": "603663.SH", "stock_name": "三祥新材", "close_price": 87.49, "pct_chg": 9.995, "amount": 162425},
                {"stock_key": "603496", "stock_id": "603496.SH", "stock_name": "恒为科技", "close_price": 26.74, "pct_chg": 9.996, "amount": 70662},
                {"stock_key": "002392", "stock_id": "002392.SZ", "stock_name": "北京利尔", "close_price": 8.81, "pct_chg": 9.988, "amount": 31059},
                {"stock_key": "000003", "stock_id": "000003.SZ", "stock_name": "无归因股", "close_price": 7.8, "pct_chg": 9.99, "amount": 5000},
            ]

        if "from stock_daily_snapshot" in q and "trade_date <= $1::date" in q:
            return [
                {"stock_key": "000811", "trade_date": self.trade_date, "pct_chg": 9.995},
                {"stock_key": "603663", "trade_date": self.trade_date, "pct_chg": 9.995},
                {"stock_key": "603496", "trade_date": self.trade_date, "pct_chg": 9.996},
                {"stock_key": "002392", "trade_date": self.trade_date, "pct_chg": 9.988},
                {"stock_key": "000003", "trade_date": self.trade_date, "pct_chg": 9.99},
            ]

        if "from subject_stock_map" in q:
            return [
                {"stock_id": "000811", "subject_key": "old-liquid", "stock_name": "冰轮环境", "sort": 1, "top": 1, "source_type": "db", "confidence": 1.0, "reason": "静态液冷"},
                {"stock_id": "603663", "subject_key": "static-material", "stock_name": "三祥新材", "sort": 1, "top": 1, "source_type": "db", "confidence": 1.0, "reason": "静态材料"},
                {"stock_id": "002392", "subject_key": "static-chip", "stock_name": "北京利尔", "sort": 1, "top": 1, "source_type": "db", "confidence": 1.0, "reason": "静态芯片"},
            ]

        if "from subject_node_staging" in q:
            return [
                {"subject_key": "old-liquid", "theme_name": "旧液冷主线"},
                {"subject_key": "static-material", "theme_name": "静态材料"},
                {"subject_key": "static-chip", "theme_name": "AI芯片"},
            ]

        if "from stocks" in q:
            return [
                {"stock_key": "000811", "stock_name": "冰轮环境"},
                {"stock_key": "603663", "stock_name": "三祥新材"},
                {"stock_key": "603496", "stock_name": "恒为科技"},
                {"stock_key": "002392", "stock_name": "北京利尔"},
                {"stock_key": "000003", "stock_name": "无归因股"},
            ]

        if "from stock_theme_reason_evidence" in q:
            return [
                {
                    "trade_date": self.trade_date,
                    "stock_code": "603663",
                    "stock_name": "三祥新材",
                    "theme_name": "先进材料/固态电池",
                    "source_name": "ths",
                    "evidence_text": "锆铪分离+锆系新材+半导体材料+固态电池",
                    "reason_tags": ["锆铪分离", "锆系新材", "半导体材料", "固态电池"],
                    "matched_reason_tags": ["锆系新材", "固态电池"],
                    "primary_theme": True,
                    "confidence": 0.75,
                    "source_trace_id": "ths_hot_reason:2026-06-18:603663",
                },
                {
                    "trade_date": self.trade_date,
                    "stock_code": "603663",
                    "stock_name": "三祥新材",
                    "theme_name": "半导体材料",
                    "source_name": "ths",
                    "evidence_text": "锆铪分离+锆系新材+半导体材料+固态电池",
                    "reason_tags": ["锆铪分离", "锆系新材", "半导体材料", "固态电池"],
                    "matched_reason_tags": ["半导体材料"],
                    "primary_theme": False,
                    "confidence": 0.65,
                    "source_trace_id": "ths_hot_reason:2026-06-18:603663",
                },
            ]

        if "from ths_hot_reason_snapshot" in q:
            return [
                {
                    "trade_date": self.trade_date,
                    "stock_code": "000811",
                    "stock_name": "冰轮环境",
                    "reason_raw": "数据中心液冷+拟收购整合+权益分派+烟台国资",
                    "reason_tags": ["数据中心液冷", "拟收购整合", "权益分派", "烟台国资"],
                    "source_name": "ths",
                    "source_trace_id": "ths_hot_reason:2026-06-18:000811",
                },
                {
                    "trade_date": self.trade_date,
                    "stock_code": "603496",
                    "stock_name": "恒为科技",
                    "reason_raw": "算力服务+华为钻石伙伴+中标中国移动",
                    "reason_tags": ["算力服务", "华为钻石伙伴", "中标中国移动"],
                    "source_name": "ths",
                    "source_trace_id": "ths_hot_reason:2026-06-18:603496",
                },
            ]

        if "from mainline_daily_state" in q:
            return [
                {
                    "id": 1,
                    "canonical_subject_key": "old-liquid",
                    "mainline_name": "旧液冷主线",
                    "active_subject_keys_json": ["old-liquid"],
                    "lifecycle_state": "start",
                    "mainline_alive": True,
                    "mainline_trade_alive": True,
                    "trade_mode": "mainline_core_only",
                    "allow_trade": True,
                }
            ]

        if "from mainline_registry" in q:
            return []

        if "from subject_rank_daily" in q:
            return [{"subject_key": "old-liquid"}, {"subject_key": "static-material"}, {"subject_key": "static-chip"}]

        if "from theme_mainline_identity_registry" in q or "from theme_detail_snapshot" in q:
            return []

        raise AssertionError(f"unexpected query: {query}")


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_m2_reason_priority_replay_20260618() -> None:
    trade_date = date(2026, 6, 18)
    matrix = await LimitUpThemeMatrixBuilder().build(
        trade_date=trade_date,
        conn=_M2ReasonPriorityFakeConn(trade_date),
    )

    columns_by_theme = {column["theme_name"]: column for column in matrix["columns"]}
    assert "旧液冷主线" in columns_by_theme
    assert "先进材料/固态电池" in columns_by_theme
    assert "AI算力基础设施" in columns_by_theme
    assert "AI芯片" in columns_by_theme
    assert "其他" in columns_by_theme

    assert columns_by_theme["旧液冷主线"]["focus_stocks"][0]["stock_name"] == "冰轮环境"
    assert columns_by_theme["先进材料/固态电池"]["focus_stocks"][0]["stock_name"] == "三祥新材"
    assert columns_by_theme["AI算力基础设施"]["focus_stocks"][0]["stock_name"] == "恒为科技"
    assert columns_by_theme["AI芯片"]["focus_stocks"][0]["stock_name"] == "北京利尔"

    audit_by_stock = {
        row["stock_id"].split(".", 1)[0]: row
        for row in matrix["diagnostics"]["assignment_audit_rows"]
    }
    assert audit_by_stock["000811"]["chosen_theme_name"] == "旧液冷主线"
    assert audit_by_stock["000811"]["chosen_source"] == "canonical_subject_key"
    assert audit_by_stock["000811"]["reason_raw"] == ""

    assert audit_by_stock["603663"]["chosen_reason"] == "stock_theme_reason_evidence"
    assert audit_by_stock["603663"]["reason_raw"] == "锆铪分离+锆系新材+半导体材料+固态电池"
    assert audit_by_stock["603663"]["matched_reason_tags"] == ["锆系新材", "固态电池"]
    assert audit_by_stock["603663"]["primary_theme"] == "先进材料/固态电池"
    assert audit_by_stock["603663"]["secondary_themes"] == ["半导体材料"]

    assert audit_by_stock["603496"]["chosen_reason"] == "ths_hot_reason_snapshot"
    assert audit_by_stock["603496"]["matched_reason_tags"] == ["算力服务"]
    assert audit_by_stock["603496"]["primary_theme"] == "AI算力基础设施"

    assert audit_by_stock["002392"]["chosen_reason"] == "subject_stock_map"
    assert audit_by_stock["000003"]["chosen_reason"] == "no_mainline_mapping"
    assert matrix["diagnostics"]["limit_up_stock_count"] == 5


def _test_column(theme_name: str, stock_codes: list[str], *, active_mainline: bool = False) -> dict[str, Any]:
    stocks = [
        {
            "stock_id": f"{stock_code}.SZ",
            "stock_name": f"{theme_name}{index}",
            "subject_key": theme_name,
            "theme_name": theme_name,
            "board_count": 1,
        }
        for index, stock_code in enumerate(stock_codes, start=1)
    ]
    return {
        "subject_key": theme_name,
        "theme_name": theme_name,
        "active_mainline": active_mainline,
        "board_groups": [
            {"board_count": 4, "board_label": "4板", "stock_count": 0, "stocks": []},
            {"board_count": 3, "board_label": "3板", "stock_count": 0, "stocks": []},
            {"board_count": 2, "board_label": "2板", "stock_count": 0, "stocks": []},
            {"board_count": 1, "board_label": "首板", "stock_count": len(stocks), "stocks": stocks},
        ],
        "limit_up_count": len(stocks),
        "focus_stocks": stocks,
        "diagnostics": {"mapping_source": "mainline_daily_state" if active_mainline else "stock_theme_reason_evidence"},
    }


def test_limit_up_theme_matrix_builder_separates_true_other_from_collapsed_other() -> None:
    builder = LimitUpThemeMatrixBuilder()
    result = builder._collapse_tail_columns(
        columns=[
            _test_column("主线", ["000001", "000002", "000003"], active_mainline=True),
            _test_column("AI算力基础设施", ["000004", "000005"]),
            _test_column("创新药/医疗", ["000006"]),
        ],
        diagnostics=[
            {
                "stock_id": "000007.SZ",
                "stock_name": "无归因股",
                "board_count": 1,
            }
        ],
        max_columns=3,
    )

    assert result["true_other_count"] == 1
    assert result["collapsed_other_count"] == 1
    assert result["display_other_count"] == 2
    assert result["collapsed_other_themes"] == [
        {
            "theme_name": "创新药/医疗",
            "subject_key": "创新药/医疗",
            "limit_up_count": 1,
            "mapping_source": "stock_theme_reason_evidence",
        }
    ]
    other_column = result["columns"][-1]
    assert other_column["theme_name"] == "其他"
    assert other_column["diagnostics"]["true_other_count"] == 1
    assert other_column["diagnostics"]["collapsed_other_count"] == 1


def test_limit_up_theme_matrix_builder_merges_duplicate_market_theme_columns() -> None:
    builder = LimitUpThemeMatrixBuilder()
    merged = builder._merge_market_columns_by_theme([
        _test_column("机器人", ["000001", "000002"], active_mainline=True),
        _test_column("机器人", ["000003"]),
        _test_column("AI算力基础设施", ["000004"]),
    ])

    by_theme = {column["theme_name"]: column for column in merged}
    assert sorted(by_theme) == ["AI算力基础设施", "机器人"]
    assert by_theme["机器人"]["limit_up_count"] == 3
    assert by_theme["机器人"]["active_mainline"] is True
    assert by_theme["机器人"]["diagnostics"]["mapping_source"] == "mainline_daily_state+stock_theme_reason_evidence"

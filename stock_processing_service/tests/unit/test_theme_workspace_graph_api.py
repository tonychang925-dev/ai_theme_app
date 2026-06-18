from __future__ import annotations

from types import SimpleNamespace

import asyncpg
import pytest

from stock_processing_service import api_app


class _Phase1Repo:
    async def fetch_theme_detail(self, subject_key: str):
        return {
            "subject_key": subject_key,
            "theme_name": "测试主题",
        }


class _FakeAnalyticsConn:
    async def fetchrow(self, query: str, *args):
        q = " ".join(query.lower().split())
        if "from theme_cycle_judgement_v2" in q:
            return {
                "final_cycle_state": "repair",
                "mainline_strength_score": 72,
                "fade_risk_score": 18,
                "fade_watch": False,
                "fade_confirmed": False,
                "divergence_score": 12,
                "repair_score": 66,
                "state_transition_reason": "unit-test",
            }
        if "from theme_cycle_evidence_daily" in q:
            return {"evidence_json": {}}
        return None

    async def fetch(self, query: str, *args):
        return []


class _AcquireCM:
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
        return _AcquireCM(self._conn)


class _FakeGateway:
    def __init__(self):
        self._client = SimpleNamespace(pool=_FakePool(_FakeAnalyticsConn()))


class _FakeGraphConn:
    def __init__(self):
        self._children = {
            "R": [
                {"child_subject_key": "C1", "child_subject_name": "一级A"},
            ],
            "C1": [
                {"child_subject_key": "G1", "child_subject_name": "孙A"},
            ],
        }
        self._parents = {
            "C1": "R",
            "G1": "C1",
        }
        self._stocks = {
            "C1": [
                {"stock_id": "000001.SZ", "stock_name": "直连A1", "reason": "一级A直连1", "sort_order": 1, "sp": 1.2},
                {"stock_id": "000002.SZ", "stock_name": "直连A2", "reason": "一级A直连2", "sort_order": 2, "sp": 0.8},
            ],
            "G1": [
                {"stock_id": "000003.SZ", "stock_name": "孙级A1", "reason": "孙A直连1", "sort_order": 1, "sp": -0.4},
            ],
        }
        self._root_stock_map = [
            {"stock_id": "000001.SZ", "stock_name": "直连A1", "pct_chg": 1.2, "sort": 1},
            {"stock_id": "000002.SZ", "stock_name": "直连A2", "pct_chg": 0.8, "sort": 2},
            {"stock_id": "000003.SZ", "stock_name": "孙级A1", "pct_chg": -0.4, "sort": 3},
        ]
        self.closed = False

    async def fetchrow(self, query: str, *args):
        q = " ".join(query.lower().split())
        if "from subject_history_staging" in q:
            return {"pct_chg": 0.66}
        if "select parent_subject_key from jyhf_subject_taxonomy_relation" in q:
            return {"parent_subject_key": self._parents.get(str(args[0]))} if self._parents.get(str(args[0])) else None
        if "select child_subject_name from jyhf_subject_taxonomy_relation" in q:
            if str(args[0]) == "R":
                return None
            name = {"C1": "一级A", "G1": "孙A"}.get(str(args[0]))
            return {"child_subject_name": name} if name else None
        return None

    async def fetch(self, query: str, *args):
        q = " ".join(query.lower().split())
        if "from jyhf_subject_taxonomy_relation" in q and "where parent_subject_key=$1" in q:
            return list(self._children.get(str(args[0]), []))
        if "from subject_child_stock_reason scr left join subject_stock_map ssm" in q and "where scr.subject_key=$1 order by scr.sort_order limit 100" in q:
            return list(self._stocks.get(str(args[0]), []))
        if "from subject_child_stock_reason scr left join subject_stock_map ssm" in q and "where scr.subject_key=$1 and scr.child_name=$2" in q:
            return []
        if "from subject_stock_map ssm" in q and "where ssm.subject_key=$1 order by ssm.sort limit 200" in q:
            return list(self._root_stock_map)
        return []

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_theme_workspace_graph_keeps_child_direct_stocks_out_of_root_component_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_graph_conn = _FakeGraphConn()

    async def fake_connect(*args, **kwargs):
        return fake_graph_conn

    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=_FakeGateway(), phase1_repo=_Phase1Repo()), raising=False)
    monkeypatch.setattr(asyncpg, "connect", fake_connect, raising=True)

    payload = await api_app.get_theme_workspace(
        "R",
        trade_date="2026-06-18",
        include_history=False,
        include_children=False,
        include_stocks=False,
        include_leaders=False,
    )

    graph = payload["graph"]
    assert graph is not None
    assert graph["root"]["name"] == "测试主题"
    assert len(graph["children"]) == 1

    child = graph["children"][0]
    assert child["name"] == "一级A"
    assert [stock["stock_id"] for stock in child["stocks"]] == ["000001.SZ", "000002.SZ"]
    assert len(child["children"]) == 1
    assert child["children"][0]["name"] == "孙A"
    assert [stock["stock_id"] for stock in child["children"][0]["stocks"]] == ["000003.SZ"]
    assert all(node["name"] != "成分股" for node in graph["children"])
    assert graph["uncategorized_stocks"] == []

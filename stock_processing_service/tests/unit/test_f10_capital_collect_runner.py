from __future__ import annotations

import asyncio
import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path

from stock_processing_service.application.services.collection_task_registry import CollectionTaskContext
from stock_processing_service.application.services.collection_task_runners import F10CapitalCollectRunner


SAMPLE_F10_TEXT = """资金动向☆ ◇000001 平安银行 更新日期：2026-06-14◇ 通达信沪深京F10
★本栏包括【1.交易龙虎榜】【2.大宗交易】【3.融资融券】【4.资金流向】
          【5.战略配售可出借】

【1.交易龙虎榜】
 最近1年内该股未能登上龙虎榜。

【3.融资融券】
2026-06-11融资融券信息：融资偿还额1.11亿元，融资净买额-793.57万元，融券余量207.12万股

【4.资金流向】
2026-06-12│ 2272.10万│    1.00│-8264.63万│   -3.65│    1.05亿│    4.65│    4.57亿│   20.20
"""


class _WritePort:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def upsert_stock_f10_capital_snapshot_rows(self, rows: list[dict]) -> int:
        self.rows = list(rows)
        return len(rows)


class _SubjectPoolReadPort:
    async def get_subject_stock_pool_by_trade_date(self, trade_date):
        return [
            {"stock_id": "000001.SZ", "stock_name": "平安银行"},
            {"stock_id": "600000.SH", "stock_name": "浦发银行"},
        ]


class _LargeSubjectPoolReadPort:
    def __init__(self, count: int) -> None:
        self._count = count

    async def get_subject_stock_pool_by_trade_date(self, trade_date):
        stock_facts = []
        for idx in range(self._count):
            stock_code = f"{idx + 1:06d}"
            stock_facts.append({"stock_id": f"{stock_code}.SZ", "stock_name": f"S{stock_code}"})
        return stock_facts


def _load_collection_job_manager_class():
    module_path = Path(__file__).resolve().parents[2] / "application" / "jobs" / "collection_job_manager.py"
    spec = importlib.util.spec_from_file_location("test_collection_job_manager_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load collection_job_manager module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.CollectionJobManager


def test_f10_capital_collect_runner_writes_snapshot_rows(monkeypatch):
    write_port = _WritePort()
    container = SimpleNamespace(
        build_post_market_recap=SimpleNamespace(_write_port=write_port),
    )
    runner = F10CapitalCollectRunner()
    monkeypatch.setattr(runner, "_collector_python", lambda context: "/tmp/fake-python")

    async def fake_run_collect_script(*, python_bin: str, trade_date: str, stock_ids: list[str], progress_callback=None) -> dict:
        if progress_callback:
            progress_callback("progress 1/1 000001")
        return {
            "records": [
                {
                    "stock_id": "000001",
                    "system_stock_id": "000001",
                    "stock_name": "平安银行",
                    "source_updated_date": "2026-06-14",
                    "raw_text": SAMPLE_F10_TEXT,
                }
            ]
        }

    monkeypatch.setattr(runner, "_run_collect_script", fake_run_collect_script)

    ctx = CollectionTaskContext(
        trade_date="2026-06-14",
        payload={"stock_ids": ["000001"]},
        env={"TDX_AGENT_HOST": "127.0.0.1", "TDX_AGENT_PORT": "8766"},
        container=container,
    )

    result = asyncio.run(runner.run(ctx))
    assert result.status == "success"
    assert len(write_port.rows) == 1
    assert write_port.rows[0]["stock_id"] == "000001"
    assert "主力净流入" in write_port.rows[0]["capital_flow_json"]["summary"]


def test_collection_job_manager_keeps_f10_payload_without_explicit_stock_ids():
    container = SimpleNamespace(
        build_post_market_recap=SimpleNamespace(_read_port=_SubjectPoolReadPort()),
    )
    CollectionJobManager = _load_collection_job_manager_class()
    manager = CollectionJobManager(container=container)

    payload = asyncio.run(manager.prepare_payload("2026-06-14", {"options": {"f10_capital": True}}))

    assert payload["options"]["f10_capital"] is True
    assert "stock_ids" not in payload
    assert "stock_ids" not in payload["options"]


def test_f10_capital_collect_runner_auto_resolves_stock_ids_from_subject_pool(monkeypatch):
    write_port = _WritePort()
    container = SimpleNamespace(
        build_post_market_recap=SimpleNamespace(
            _write_port=write_port,
            _read_port=_SubjectPoolReadPort(),
        ),
    )
    runner = F10CapitalCollectRunner()
    monkeypatch.setattr(runner, "_collector_python", lambda context: "/tmp/fake-python")

    seen_stock_ids: list[str] = []

    async def fake_run_collect_script(*, python_bin: str, trade_date: str, stock_ids: list[str], progress_callback=None) -> dict:
        seen_stock_ids.extend(stock_ids)
        if progress_callback and stock_ids:
            progress_callback(f"progress 1/{len(stock_ids)} {stock_ids[0]}")
        return {
            "records": [
                {
                    "stock_id": stock_id,
                    "system_stock_id": stock_id,
                    "stock_name": f"S{stock_id}",
                    "source_updated_date": "2026-06-14",
                    "raw_text": SAMPLE_F10_TEXT.replace("000001", stock_id),
                }
                for stock_id in stock_ids
            ]
        }

    monkeypatch.setattr(runner, "_run_collect_script", fake_run_collect_script)

    ctx = CollectionTaskContext(
        trade_date="2026-06-14",
        payload={"options": {}},
        env={"TDX_AGENT_HOST": "127.0.0.1", "TDX_AGENT_PORT": "8766"},
        container=container,
    )

    result = asyncio.run(runner.run(ctx))
    assert result.status == "success"
    assert seen_stock_ids == ["000001", "600000"]
    assert len(write_port.rows) == 2


def test_f10_capital_collect_runner_fails_fast_when_collector_python_missing(monkeypatch):
    write_port = _WritePort()
    container = SimpleNamespace(
        build_post_market_recap=SimpleNamespace(_write_port=write_port),
    )
    runner = F10CapitalCollectRunner()
    monkeypatch.setattr(runner, "_collector_python", lambda context: "")

    ctx = CollectionTaskContext(
        trade_date="2026-06-14",
        payload={"options": {}, "stock_ids": ["000001", "600000"]},
        env={},
        container=container,
    )

    result = asyncio.run(runner.run(ctx))
    assert result.status == "failed"
    assert "collector python not found" in result.error_message
    assert len(write_port.rows) == 0


def test_f10_capital_collect_runner_collects_all_explicit_stock_ids_without_truncation(monkeypatch):
    count = 130
    write_port = _WritePort()
    container = SimpleNamespace(
        build_post_market_recap=SimpleNamespace(_write_port=write_port),
    )
    runner = F10CapitalCollectRunner()
    monkeypatch.setattr(runner, "_collector_python", lambda context: "/tmp/fake-python")

    async def fake_run_collect_script(*, python_bin: str, trade_date: str, stock_ids: list[str], progress_callback=None) -> dict:
        if progress_callback and stock_ids:
            progress_callback(f"progress 1/{len(stock_ids)} {stock_ids[0]}")
        return {
            "records": [
                {
                    "stock_id": stock_id,
                    "system_stock_id": stock_id,
                    "stock_name": f"S{stock_id}",
                    "source_updated_date": "2026-06-14",
                    "raw_text": SAMPLE_F10_TEXT.replace("000001", stock_id),
                }
                for stock_id in stock_ids
            ]
        }

    monkeypatch.setattr(runner, "_run_collect_script", fake_run_collect_script)

    ctx = CollectionTaskContext(
        trade_date="2026-06-14",
        payload={"options": {}, "stock_ids": [f"{idx + 1:06d}" for idx in range(count)]},
        env={"TDX_AGENT_HOST": "127.0.0.1", "TDX_AGENT_PORT": "8766"},
        container=container,
    )

    result = asyncio.run(runner.run(ctx))
    assert result.status == "success"
    assert len(write_port.rows) == count
    assert write_port.rows[0]["stock_id"] == "000001"
    assert write_port.rows[-1]["stock_id"] == f"{count:06d}"

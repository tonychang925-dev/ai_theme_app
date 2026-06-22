from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from stock_processing_service.integrations.a_stock_data.clients.ths_client import RawHttpResult
from stock_processing_service.integrations.a_stock_data.jobs.collect_ths_hot_reason_job import (
    CollectThsHotReasonJob,
)
from stock_processing_service.integrations.a_stock_data.normalizers.ths_hot_reason_normalizer import (
    ThsHotReasonNormalizer,
    split_reason_tags,
)
from stock_processing_service.integrations.a_stock_data.resolvers.reason_theme_resolver import (
    RuleResolver,
    theme_match_to_evidence_rows,
)


SAMPLE_PAYLOAD = {
    "errocode": 0,
    "errormsg": "",
    "data": [
        {
            "id": 90528848,
            "name": "冰轮环境",
            "code": "000811",
            "reason": "数据中心液冷+拟收购整合+权益分派+烟台国资",
            "date": "2026-06-18",
            "close": 40.17,
            "zhangfu": 9.995,
            "huanshou": 0.43,
            "chengjiaoe": 17019,
            "chengjiaoliang": 42367,
            "ddejingliang": 0,
            "market": 33,
        },
        {
            "id": 90529034,
            "name": "三祥新材",
            "code": "603663",
            "reason": "锆铪分离+锆系新材+半导体材料+固态电池",
            "date": "2026-06-18",
            "close": 87.49,
            "zhangfu": 9.995,
            "huanshou": 4.42,
            "chengjiaoe": 162425,
            "chengjiaoliang": 186814,
            "ddejingliang": 0.88,
            "market": 17,
        },
    ],
    "date": "2026-06-18",
}


def test_split_reason_tags_supports_full_width_plus() -> None:
    assert split_reason_tags("PCB＋HBM+ 封装基板 ") == ["PCB", "HBM", "封装基板"]


@pytest.mark.asyncio
async def test_rule_resolver_returns_primary_and_secondary_themes() -> None:
    resolver = RuleResolver()
    match = await resolver.resolve(
        ["液冷", "数据中心", "人形机器人"],
        "000001",
        "样本",
    )

    assert match.primary_theme == "AI算力基础设施"
    assert "机器人" in match.secondary_themes
    assert match.matched_reason_tags["AI算力基础设施"] == ["液冷", "数据中心"]


def test_ths_hot_reason_normalizer_outputs_snapshot_rows() -> None:
    rows = ThsHotReasonNormalizer().normalize_snapshot_rows(
        SAMPLE_PAYLOAD,
        trade_date=date(2026, 6, 18),
        raw_snapshot_id=7,
    )

    assert len(rows) == 2
    assert rows[0]["stock_code"] == "000811"
    assert rows[0]["reason_tags"] == ["数据中心液冷", "拟收购整合", "权益分派", "烟台国资"]
    assert rows[0]["source_trace_id"] == "ths_hot_reason:2026-06-18:000811"
    assert rows[0]["raw_snapshot_id"] == 7


@pytest.mark.asyncio
async def test_theme_match_to_evidence_rows_keeps_multi_theme_resonance() -> None:
    resolver = RuleResolver()
    match = await resolver.resolve(
        ["硅光", "人形机器人", "液冷"],
        "688515",
        "裕太微",
    )
    rows = theme_match_to_evidence_rows(
        trade_date=date(2026, 6, 18),
        stock_code="688515",
        stock_name="裕太微",
        reason_raw="硅光+人形机器人+液冷",
        reason_tags=["硅光", "人形机器人", "液冷"],
        source_name="ths",
        source_trace_id="ths_hot_reason:2026-06-18:688515",
        raw_snapshot_id=7,
        match=match,
    )

    assert {row["theme_name"] for row in rows} == {"AI光通信", "机器人", "AI算力基础设施"}
    assert sum(1 for row in rows if row["primary_theme"]) == 1


@dataclass
class _FakeClient:
    async def fetch_hot_reason(self, trade_date: date) -> RawHttpResult:
        return RawHttpResult(
            source_name="ths",
            endpoint_key="ths_hot_reason",
            trade_date=trade_date,
            request_url="https://example.test/ths?date=2026-06-18",
            request_params={"date": "2026-06-18"},
            status_code=200,
            response_json=SAMPLE_PAYLOAD,
            response_text="{}",
            headers={},
        )


class _FakeWritePort:
    def __init__(self) -> None:
        self.raw: dict | None = None
        self.snapshots: list[dict] = []
        self.evidence: list[dict] = []

    async def upsert_source_raw_snapshot(self, row: dict) -> int:
        self.raw = row
        return 42

    async def upsert_ths_hot_reason_snapshot_rows(self, rows: list[dict]) -> int:
        self.snapshots = rows
        return len(rows)

    async def upsert_stock_theme_reason_evidence_rows(self, rows: list[dict]) -> int:
        self.evidence = rows
        return len(rows)


@pytest.mark.asyncio
async def test_collect_ths_hot_reason_job_writes_raw_snapshot_and_evidence() -> None:
    write_port = _FakeWritePort()
    job = CollectThsHotReasonJob(write_port=write_port, client=_FakeClient())

    result = await job.execute(date(2026, 6, 18))

    assert result.status == "ok"
    assert result.metrics["raw_snapshot_id"] == 42
    assert result.metrics["snapshot_rows"] == 2
    assert result.metrics["reason_covered_count"] == 2
    assert write_port.raw is not None
    assert write_port.raw["response_hash"]
    assert len(write_port.snapshots) == 2
    assert {row["theme_name"] for row in write_port.evidence} >= {
        "AI算力基础设施",
        "先进材料/固态电池",
    }

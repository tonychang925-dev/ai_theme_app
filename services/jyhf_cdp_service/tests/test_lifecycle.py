from __future__ import annotations

import asyncio
import logging

import pytest

from services.jyhf_cdp_service.config import JyhfCdpServiceConfig
from services.jyhf_cdp_service.service import CollectorStartupFailed, JyhfCdpCollectorService
from services.jyhf_cdp_service.state import DedupStore


def test_dedup_store_keeps_recent_insert_order(tmp_path):
    store = DedupStore(tmp_path / "seen.json", max_keys=3)
    for key in ["k1", "k2", "k3", "k4"]:
        store.mark(key)

    restored = DedupStore(tmp_path / "seen.json", max_keys=3)
    assert not restored.seen("k1")
    assert restored.seen("k2")
    assert restored.seen("k3")
    assert restored.seen("k4")


@pytest.mark.asyncio
async def test_stop_sets_stopped_state_and_cancels_task(tmp_path):
    cfg = JyhfCdpServiceConfig(project_root=tmp_path, interval_seconds=60)
    service = JyhfCdpCollectorService(config=cfg, logger=logging.getLogger("test_jyhf_cdp_service"))
    service._task = asyncio.create_task(asyncio.sleep(60))
    service._status.update(collector_running=True, collector_state="running")

    await service.stop()

    status = service.status()
    assert status.collector_running is False
    assert status.collector_state == "stopped"
    assert service._task.cancelled()


def test_startup_failure_fuse_stops_relaunch_loop(tmp_path):
    cfg = JyhfCdpServiceConfig(project_root=tmp_path, interval_seconds=60)
    service = JyhfCdpCollectorService(config=cfg, logger=logging.getLogger("test_jyhf_cdp_service"))
    service._startup_failure_limit = 3

    class AlwaysLaunching:
        def __init__(self) -> None:
            self.calls = 0

        def ensure_running(self, should_stop=None) -> bool:
            self.calls += 1
            return False

    fake_app = AlwaysLaunching()
    service._app = fake_app  # type: ignore[assignment]

    service._capture_once_locked({}, run_id=0)
    service._capture_once_locked({}, run_id=0)
    with pytest.raises(CollectorStartupFailed, match="prevent repeated app relaunch"):
        service._capture_once_locked({}, run_id=0)

    assert fake_app.calls == 3

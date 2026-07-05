from __future__ import annotations

import types

import pytest

from stock_processing_service import api_app


def test_sps_singleton_lock_acquire_and_release(monkeypatch, tmp_path) -> None:
    lock_path = tmp_path / "sps.lock"
    monkeypatch.setattr(api_app, "SPS_SINGLETON_LOCK_PATH", lock_path)

    state = {"fd": 100, "closed": [], "content": b""}

    def _fake_open(path, flags, mode=0o644):
        assert path == str(lock_path)
        return state["fd"]

    def _fake_flock(fd, op):
        assert fd == state["fd"]
        return None

    def _fake_ftruncate(fd, size):
        assert fd == state["fd"]
        assert size == 0

    def _fake_write(fd, content):
        assert fd == state["fd"]
        state["content"] = content
        return len(content)

    def _fake_fsync(fd):
        assert fd == state["fd"]
        return None

    def _fake_close(fd):
        state["closed"].append(fd)

    monkeypatch.setattr(api_app.os, "open", _fake_open)
    monkeypatch.setattr(api_app.fcntl, "flock", _fake_flock)
    monkeypatch.setattr(api_app.os, "ftruncate", _fake_ftruncate)
    monkeypatch.setattr(api_app.os, "write", _fake_write)
    monkeypatch.setattr(api_app.os, "fsync", _fake_fsync)
    monkeypatch.setattr(api_app.os, "close", _fake_close)
    monkeypatch.setattr(api_app.os, "getpid", lambda: 4242)

    fd = api_app._acquire_sps_singleton_lock()
    assert fd == state["fd"]
    assert state["content"] == b"pid=4242\n"

    api_app._release_sps_singleton_lock(fd)
    assert state["closed"] == [state["fd"]]


def test_sps_singleton_lock_rejects_second_instance(monkeypatch, tmp_path) -> None:
    lock_path = tmp_path / "sps.lock"
    monkeypatch.setattr(api_app, "SPS_SINGLETON_LOCK_PATH", lock_path)

    state = {"fds": [], "closed": []}

    def _fake_open(path, flags, mode=0o644):
        fd = 100 + len(state["fds"])
        state["fds"].append(fd)
        return fd

    def _fake_flock(fd, op):
        if len(state["fds"]) >= 2 and fd == state["fds"][-1]:
            raise BlockingIOError("locked")
        return None

    def _fake_ftruncate(fd, size):
        return None

    def _fake_write(fd, content):
        return len(content)

    def _fake_fsync(fd):
        return None

    def _fake_close(fd):
        state["closed"].append(fd)

    monkeypatch.setattr(api_app.os, "open", _fake_open)
    monkeypatch.setattr(api_app.fcntl, "flock", _fake_flock)
    monkeypatch.setattr(api_app.os, "ftruncate", _fake_ftruncate)
    monkeypatch.setattr(api_app.os, "write", _fake_write)
    monkeypatch.setattr(api_app.os, "fsync", _fake_fsync)
    monkeypatch.setattr(api_app.os, "close", _fake_close)
    monkeypatch.setattr(api_app.os, "getpid", lambda: 4242)

    first_fd = api_app._acquire_sps_singleton_lock()
    assert first_fd == 100
    with pytest.raises(RuntimeError, match="SPS singleton lock already held"):
        api_app._acquire_sps_singleton_lock()

    api_app._release_sps_singleton_lock(first_fd)
    assert state["closed"] == [101, 100]

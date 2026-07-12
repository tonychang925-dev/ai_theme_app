"""PR3 — Workbench ReviewDocument override persistence API tests.

Covers:
  - persistence round-trip (save → reload → verify)
  - version concurrency control
  - invalid override rejection (FACT path protection)
  - hash changes / idempotency
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stock_processing_service import api_app


_TRADE_DATE = "2099-07-11"


def _setup_minimal_workbench(workbench_dir: Path) -> None:
    """Create minimal draft + context so workspace API can assemble a ReviewDocument."""
    (workbench_dir / "drafts").mkdir(parents=True)
    (workbench_dir / "draft_context.json").write_text(
        json.dumps({
            "trade_date": _TRADE_DATE,
            "market_state": {
                "facts": {
                    "limit_up_count": 75,
                    "limit_down_count": 29,
                    "up_count": 3561,
                    "down_count": 1609,
                }
            },
            "themes": [
                {"subject_key": "robot", "theme_name": "人形机器人", "role": "MAINLINE", "stage": "分歧"}
            ],
            "capital_state": {
                "top_stocks": [
                    {"theme_name": "机器人", "role_label": "机构", "stock_name": "测试股份"}
                ]
            },
            "strong_stocks": [
                {"stock_code": "000001.SZ", "stock_name": "测试股份", "theme_name": "机器人"}
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (workbench_dir / "drafts" / "draft_v1.json").write_text(
        json.dumps({
            "trade_date": _TRADE_DATE,
            "draft_version": 1,
            "emotion_review": {"phase": "REBOUND", "score": 39},
            "cognition_cards": [],
            "playbook": {"scenario": "REBOUND_ARBITRAGE"},
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def _teardown_workbench(workbench_dir: Path) -> None:
    shutil.rmtree(workbench_dir, ignore_errors=True)


def _workbench_dir() -> Path:
    project_root = Path(api_app.__file__).resolve().parents[1]
    return project_root / "tmp" / "analyst_workbench" / _TRADE_DATE


def _make_override(
    field_path: str = "themes[robot].name",
    field_class: str = "IDENTITY",
    ai_value: str = "人形机器人",
    analyst_value: str = "PCB",
    final_value: str = "PCB",
    reason: str = "资金切换",
) -> dict:
    return {
        "field_path": field_path,
        "field_class": field_class,
        "ai_value": ai_value,
        "analyst_value": analyst_value,
        "final_value": final_value,
        "reason": reason,
        "author": "analyst",
        "timestamp": "2026-07-09T16:00:00+08:00",
    }


# ── existing test (updated for version contract) ──

@pytest.mark.asyncio
async def test_review_overrides_are_saved_and_applied_to_workspace_document() -> None:
    wb_dir = _workbench_dir()
    if wb_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {wb_dir}")

    try:
        _setup_minimal_workbench(wb_dir)

        before = await api_app.get_analyst_workspace(_TRADE_DATE)
        before_hash = before["review_document"]["metadata"]["final_document_hash"]
        assert before["review_document"]["summary"]["primary_theme"]["final_value"] == "人形机器人"

        saved = await api_app.save_analyst_workspace_review_overrides(
            _TRADE_DATE,
            {"overrides": [_make_override()]},
        )

        assert saved["status"] == "saved"
        assert saved["metadata"]["override_count"] == 1
        assert saved["metadata"]["version"] == 1
        assert saved["review_document"]["summary"]["primary_theme"]["final_value"] == "PCB"
        assert saved["metadata"]["document_hash"] != before_hash
        assert saved["review_document_diff"]["changes"][0]["before"] == "人形机器人"
        assert saved["review_document_diff"]["changes"][0]["after"] == "PCB"

        # GET overrides returns version
        persisted = await api_app.get_analyst_workspace_review_overrides(_TRADE_DATE)
        assert persisted["overrides"][0]["field_path"] == "themes[robot].name"
        assert persisted["metadata"]["version"] == 1

        # Workspace reflects override
        after = await api_app.get_analyst_workspace(_TRADE_DATE)
        assert after["review_document"]["summary"]["primary_theme"]["final_value"] == "PCB"
        assert after["review_document"]["themes"][0]["name"]["final_value"] == "PCB"
        assert after["diagnostics"]["override_count"] == 1
    finally:
        _teardown_workbench(wb_dir)


# ── new tests ──

@pytest.mark.asyncio
async def test_override_persistence_roundtrip() -> None:
    """POST override → GET workspace → override still in effect."""
    wb_dir = _workbench_dir()
    if wb_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {wb_dir}")

    try:
        _setup_minimal_workbench(wb_dir)

        # Save override
        saved = await api_app.save_analyst_workspace_review_overrides(
            _TRADE_DATE,
            {"overrides": [_make_override(analyst_value="PCB", final_value="PCB")]},
        )
        assert saved["status"] == "saved"

        # Reload workspace — override must still be applied
        doc = await api_app.get_analyst_workspace(_TRADE_DATE)
        assert doc["review_document"]["themes"][0]["name"]["final_value"] == "PCB"
        assert doc["review_document"]["summary"]["primary_theme"]["final_value"] == "PCB"
    finally:
        _teardown_workbench(wb_dir)


@pytest.mark.asyncio
async def test_override_version_conflict_detection() -> None:
    """Saving with stale base_version returns 409 Conflict."""
    wb_dir = _workbench_dir()
    if wb_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {wb_dir}")

    try:
        _setup_minimal_workbench(wb_dir)

        # First save → version 1
        await api_app.save_analyst_workspace_review_overrides(
            _TRADE_DATE,
            {"overrides": [_make_override(analyst_value="PCB", final_value="PCB")]},
        )

        # Second save with stale base_version=0 → conflict
        with pytest.raises(Exception) as exc_info:
            await api_app.save_analyst_workspace_review_overrides(
                _TRADE_DATE,
                {
                    "overrides": [_make_override(analyst_value="存储芯片", final_value="存储芯片")],
                    "base_version": 0,
                },
            )
        assert exc_info.value.status_code == 409
        assert "Version conflict" in exc_info.value.detail

        # Verify first override was NOT overwritten
        doc = await api_app.get_analyst_workspace(_TRADE_DATE)
        assert doc["review_document"]["themes"][0]["name"]["final_value"] == "PCB"
    finally:
        _teardown_workbench(wb_dir)


@pytest.mark.asyncio
async def test_override_sequential_saves_increment_version() -> None:
    """Each save increments version; using current base_version succeeds."""
    wb_dir = _workbench_dir()
    if wb_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {wb_dir}")

    try:
        _setup_minimal_workbench(wb_dir)

        # Save 1 — no base_version (first write)
        s1 = await api_app.save_analyst_workspace_review_overrides(
            _TRADE_DATE,
            {"overrides": [_make_override(analyst_value="PCB", final_value="PCB")]},
        )
        assert s1["metadata"]["version"] == 1

        # Save 2 — with correct base_version=1
        s2 = await api_app.save_analyst_workspace_review_overrides(
            _TRADE_DATE,
            {
                "overrides": [_make_override(analyst_value="存储芯片", final_value="存储芯片")],
                "base_version": 1,
            },
        )
        assert s2["metadata"]["version"] == 2
        assert s2["status"] == "saved"

        # Verify latest override is applied
        doc = await api_app.get_analyst_workspace(_TRADE_DATE)
        assert doc["review_document"]["themes"][0]["name"]["final_value"] == "存储芯片"
    finally:
        _teardown_workbench(wb_dir)


@pytest.mark.asyncio
async def test_invalid_fact_override_rejection() -> None:
    """Overriding a FACT field (market.limit_up_count) must be rejected."""
    wb_dir = _workbench_dir()
    if wb_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {wb_dir}")

    try:
        _setup_minimal_workbench(wb_dir)

        with pytest.raises(Exception) as exc_info:
            await api_app.save_analyst_workspace_review_overrides(
                _TRADE_DATE,
                {
                    "overrides": [
                        _make_override(
                            field_path="market.limit_up_count",
                            field_class="IDENTITY",
                            ai_value=75,
                            analyst_value=100,
                            final_value=100,
                        )
                    ],
                },
            )
        # Must be a 400 (bad request) — FACT override not allowed
        assert exc_info.value.status_code == 400
    finally:
        _teardown_workbench(wb_dir)


@pytest.mark.asyncio
async def test_override_hash_idempotency() -> None:
    """No override → hash A → save override → hash B → delete override → hash A."""
    wb_dir = _workbench_dir()
    if wb_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {wb_dir}")

    try:
        _setup_minimal_workbench(wb_dir)

        # Hash A: no overrides
        before = await api_app.get_analyst_workspace(_TRADE_DATE)
        hash_a = before["review_document"]["metadata"]["final_document_hash"]

        # Hash B: with override
        saved = await api_app.save_analyst_workspace_review_overrides(
            _TRADE_DATE,
            {"overrides": [_make_override()]},
        )
        hash_b = saved["metadata"]["document_hash"]
        assert hash_b != hash_a

        # Delete all overrides → back to hash A
        cleared = await api_app.save_analyst_workspace_review_overrides(
            _TRADE_DATE,
            {"overrides": [], "base_version": saved["metadata"]["version"]},
        )
        hash_cleared = cleared["metadata"]["document_hash"]
        assert hash_cleared == hash_a

        # Workspace now reflects original AI value
        after = await api_app.get_analyst_workspace(_TRADE_DATE)
        assert after["review_document"]["summary"]["primary_theme"]["final_value"] == "人形机器人"
    finally:
        _teardown_workbench(wb_dir)

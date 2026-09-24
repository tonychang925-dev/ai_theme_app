from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "stock_service"
    / "scripts"
    / "build_mainline_identity_registry.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "rd1_mainline_identity_transport_test", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict):
        self.status = 200
        self._payload = payload

    async def json(self):
        return self._payload


class FakeSession:
    requests: list[dict] = []

    def __init__(self):
        self.records = FakeSession.requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    def post(self, url, *, headers, json, timeout):
        self.records.append({
            "url": url,
            "headers": headers,
            "payload": json,
            "timeout": timeout,
        })
        return FakeResponseContext(self.records[-1])


class FakeResponseContext:
    def __init__(self, request: dict):
        self.request = request

    async def __aenter__(self):
        return FakeResponse(self.request["response"])

    async def __aexit__(self, exc_type, exc, traceback):
        return None


def install_transport(monkeypatch, response: dict):
    FakeSession.requests = []
    def post(self, url, *, headers, json, timeout):
        request = {
            "url": url,
            "headers": headers,
            "payload": json,
            "timeout": timeout,
            "response": response,
        }
        FakeSession.requests.append(request)
        return FakeResponseContext(request)

    monkeypatch.setattr(FakeSession, "post", post)
    module = load_module()
    monkeypatch.setattr(
        module.aiohttp,
        "ClientSession",
        FakeSession,
        raising=False,
    )
    return module


def call(module):
    return asyncio.run(module._call_llm_review(
        prompt="prompt",
        api_key="test-key",
        api_base="https://example.invalid",
        model_name="deepseek-v4-pro",
        timeout_seconds=45,
    ))


def success_response(content: str):
    return {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": content},
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


def test_request_budget_and_provider_semantics(monkeypatch):
    module = install_transport(
        monkeypatch,
        success_response('{"logic_dimension_ok_llm":false}'),
    )
    call(module)
    request = FakeSession.requests[0]
    assert request["payload"]["max_tokens"] == 4000
    assert request["payload"]["response_format"] == {"type": "json_object"}
    assert request["payload"]["temperature"] == 0.1
    assert request["payload"]["model"] == "deepseek-v4-pro"
    assert "thinking" not in request["payload"]
    assert "reasoning_effort" not in request["payload"]


def test_valid_json_succeeds(monkeypatch):
    expected = {
        "logic_dimension_ok_llm": True,
        "market_dimension_ok_llm": True,
        "is_main_theme_core_llm": True,
        "confidence": 90,
        "reasons": ["reason"],
        "risk_flags": [],
    }
    module = install_transport(monkeypatch, success_response(__import__("json").dumps(expected)))
    assert call(module) == expected


def test_length_fails_closed(monkeypatch):
    module = install_transport(monkeypatch, {
        "choices": [{
            "finish_reason": "length",
            "message": {"content": '{"partial":'},
        }]
    })
    with pytest.raises(RuntimeError, match="^mainline_identity_llm_output_truncated$"):
        call(module)


def test_missing_content_fails_closed(monkeypatch):
    module = install_transport(monkeypatch, {
        "choices": [{"finish_reason": "stop", "message": {"content": ""}}]
    })
    with pytest.raises(RuntimeError, match="^mainline_identity_llm_content_missing$"):
        call(module)


def test_invalid_json_fails_closed_without_raw_content(monkeypatch):
    module = install_transport(monkeypatch, success_response('{"broken":'))
    with pytest.raises(
        RuntimeError,
        match=r"^mainline_identity_llm_invalid_json:JSONDecodeError:Expecting value@\d+$",
    ) as exc_info:
        call(module)
    assert "broken" not in str(exc_info.value)


def test_provider_receives_one_request(monkeypatch):
    module = install_transport(monkeypatch, success_response("{}"))
    call(module)
    assert len(FakeSession.requests) == 1

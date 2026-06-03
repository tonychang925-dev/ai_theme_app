from __future__ import annotations

import json
import subprocess
import time
from typing import Any

import websocket


class CDPClient:
    def __init__(self, port: int) -> None:
        self._port = port
        self._ws: websocket.WebSocket | None = None
        self._msg_id = 0

    def connect(self) -> None:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{self._port}/json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pages = json.loads(result.stdout or "[]")
        target = next((p for p in pages if "久赢恒丰" in str(p.get("title", ""))), None)
        if not target:
            raise RuntimeError(f"JYHF app not found on CDP port {self._port}")
        self._ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)
        self._send("Runtime.enable")
        time.sleep(0.3)
        self._recv_all(0.5)

    def close(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def reconnect(self) -> None:
        """断连后重连 JYHF CDP 页面。"""
        self.close()
        self.connect()

    def evaluate(self, expression: str, timeout: float = 8.0) -> Any:
        if not self._ws:
            raise RuntimeError("CDP client not connected")
        self._msg_id += 1
        mid = self._msg_id
        self._send("Runtime.evaluate", {"expression": expression, "returnByValue": True}, mid)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = json.loads(self._ws.recv())
            except (websocket.WebSocketTimeoutException, json.JSONDecodeError):
                continue
            if msg.get("id") != mid:
                continue
            result = msg.get("result", {}).get("result", {})
            if "value" in result:
                return result["value"]
            if result.get("type") == "undefined":
                return None
            return None
        raise TimeoutError(f"Runtime.evaluate timed out after {timeout}s")

    def _send(self, method: str, params: dict | None = None, mid: int | None = None) -> None:
        if not self._ws:
            raise RuntimeError("CDP websocket not connected")
        self._ws.send(json.dumps({"id": mid or 0, "method": method, "params": params or {}}))

    def _recv_all(self, timeout: float) -> list[dict]:
        if not self._ws:
            return []
        self._ws.settimeout(0.3)
        messages = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                messages.append(json.loads(self._ws.recv()))
            except Exception:
                break
        return messages


from __future__ import annotations

import json
import subprocess
import time


class JyhfAppManager:
    def __init__(self, app_path: str, cdp_port: int) -> None:
        self._app_path = app_path
        self._cdp_port = cdp_port

    def is_running_with_cdp(self) -> bool:
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://localhost:{self._cdp_port}/json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            pages = json.loads(result.stdout or "[]")
            return any("久赢恒丰" in str(page.get("title", "")) for page in pages)
        except Exception:
            return False

    def ensure_running(self) -> bool:
        if self.is_running_with_cdp():
            return True
        subprocess.Popen(
            [f"{self._app_path}/Contents/MacOS/久赢恒丰", f"--remote-debugging-port={self._cdp_port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(20):
            time.sleep(2)
            if self.is_running_with_cdp():
                time.sleep(3)
                return True
        raise RuntimeError("failed to start JYHF app with CDP")


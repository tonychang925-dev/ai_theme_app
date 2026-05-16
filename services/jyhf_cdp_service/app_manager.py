import json
import logging
import subprocess
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class JyhfAppManager:
    def __init__(self, app_path: str, cdp_port: int) -> None:
        self._app_path = app_path
        self._cdp_port = cdp_port
        self._launching: bool = False  # Guard against concurrent launch attempts

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

    def stop_app(self) -> None:
        """Kill any running JYHF app process so it can be cleanly restarted."""
        try:
            result = subprocess.run(
                ["pkill", "-f", "久赢恒丰"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("JYHF app killed via pkill")
                # Wait for port release
                deadline = time.time() + 5
                while time.time() < deadline:
                    if not self.is_running_with_cdp():
                        break
                    time.sleep(0.5)
        except Exception as exc:
            logger.warning("failed to kill JYHF app: %s", exc)

    def ensure_running(self, should_stop: Callable[[], bool] | None = None) -> bool:
        if self.is_running_with_cdp():
            return True
        # Guard: if already launching, just wait — don't kill and restart
        if self._launching:
            logger.info("JYHF app launch already in progress, waiting...")
            return False  # Let the capture loop retry next cycle
        self._launching = True
        try:
            # Kill any stale instance before launching
            self.stop_app()
            return self._launch_and_wait(should_stop)
        finally:
            self._launching = False

    def _launch_and_wait(self, should_stop: Callable[[], bool] | None, attempt: int = 1) -> bool:
        logger.info("launching JYHF app with CDP (attempt %s)", attempt)
        subprocess.Popen(
            [f"{self._app_path}/Contents/MacOS/久赢恒丰", f"--remote-debugging-port={self._cdp_port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        max_wait = 15 if attempt == 1 else 10
        for i in range(max_wait):
            if should_stop and should_stop():
                raise RuntimeError("JYHF app startup cancelled")
            time.sleep(1)
            if self.is_running_with_cdp():
                time.sleep(1.5)  # Extra settle time for CDP to be fully ready
                logger.info("JYHF app CDP ready after %ss", i + 1)
                return True
        if attempt < 2:
            logger.warning("JYHF app not ready after %ss, retrying once", max_wait)
            return self._launch_and_wait(should_stop, attempt=attempt + 1)
        raise RuntimeError(
            f"failed to start JYHF app with CDP after {attempt} attempt(s). "
            f"Ensure the app is installed at {self._app_path}"
        )

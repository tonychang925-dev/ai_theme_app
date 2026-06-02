import json
import logging
import os
import signal
import subprocess
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class JyhfAppManager:
    def __init__(self, app_path: str, cdp_port: int) -> None:
        self._app_path = app_path
        self._cdp_port = cdp_port
        self._launching: bool = False  # Guard against concurrent launch attempts
        self._launched_pid: int | None = None

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
        """Stop the JYHF app instance this service launched.

        The app name may be mojibake in `ps`, so PID/port based cleanup is the
        primary path. Name-based pkill is only a last-resort fallback.
        """
        killed = False
        for pid in self._candidate_pids():
            try:
                os.kill(pid, signal.SIGTERM)
                killed = True
                logger.info("JYHF app kill requested pid=%s", pid)
            except ProcessLookupError:
                continue
            except Exception as exc:
                logger.warning("failed to terminate JYHF app pid=%s: %s", pid, exc)

        if killed:
            deadline = time.time() + 5
            while time.time() < deadline:
                if not self.is_running_with_cdp():
                    break
                time.sleep(0.5)
            for pid in self._candidate_pids():
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                    logger.warning("JYHF app force-killed pid=%s", pid)
                except ProcessLookupError:
                    continue
                except Exception:
                    pass
            self._launched_pid = None
            return

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
        finally:
            self._launched_pid = None

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
        proc = subprocess.Popen(
            [f"{self._app_path}/Contents/MacOS/久赢恒丰", f"--remote-debugging-port={self._cdp_port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._launched_pid = proc.pid
        logger.info("JYHF app launch pid=%s cdp_port=%s", proc.pid, self._cdp_port)
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

    def _candidate_pids(self) -> list[int]:
        pids: list[int] = []
        if self._launched_pid:
            pids.append(self._launched_pid)
        port_pid = self._find_port_pid()
        if port_pid:
            pids.append(port_pid)
        seen: set[int] = set()
        unique: list[int] = []
        for pid in pids:
            if pid <= 0 or pid in seen:
                continue
            seen.add(pid)
            unique.append(pid)
        return unique

    def _find_port_pid(self) -> int | None:
        try:
            out = subprocess.run(
                ["lsof", "-t", "-nP", f"-iTCP:{self._cdp_port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for row in out.stdout.splitlines():
                row = row.strip()
                if row.isdigit():
                    return int(row)
        except Exception as exc:
            logger.debug("failed to find JYHF CDP port pid: %s", exc)
        return None

"""P4-2C: Realtime Business Orchestrator — controlled auto-tick + white-listed actions.

P4-2C safety boundaries:
  - Double gate: enabled=True + actions_enabled=True required for real actions
  - Only 3 action types allowed: ensure_cdp_service, ensure_jyhf_market, ensure_jyhf_auction
  - NEVER: auto-start W2S, auto-start support alert, probe SSE stream, kill SPS children
  - Once-per-window idempotency, retry backoff, circuit breaker, audit log

Architecture:
  Frontend (enable/disable toggle)
    ↓
  BFF RealtimeBusinessOrchestrator
    ↓
  Owners:
    - JyhfCdpManager → cdp_service
    - SPS → jyhf-market collector
    - JyhfAuctionManager → auction collector
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("web_app.orchestrator")

TZ_CN = timezone(timedelta(hours=8))

# ── Service dependency graph ──────────────────────────────────────────

SERVICE_DEPENDENCIES: dict[str, list[str]] = {
    "cdp_token": [],
    "jyhf_market": ["cdp_token"],
    "jyhf_auction": ["cdp_token", "jyhf_market"],
    "w2s_alert": ["cdp_token", "jyhf_auction"],
    "support_alert": ["jyhf_market"],
}

SERVICE_OWNERS: dict[str, str] = {
    "cdp_token": "bff_cdp_manager",
    "jyhf_market": "sps_jyhf_market_collector",
    "jyhf_auction": "bff_auction_manager",
    "w2s_alert": "sps_w2s_alert_stream",
    "support_alert": "sps_kline_alert_stream",
}

# P4-2C: only these services are allowed to be auto-started
ALLOWED_ACTIONS: set[str] = {"cdp_token", "jyhf_market", "jyhf_auction"}

# ── Trading phase windows (HHMM in Asia/Shanghai) ─────────────────────

TRADING_PHASES: list[tuple[str, int, int, str]] = [
    ("preopen_prepare", 900, 909, "盘前准备"),
    ("auction_collect", 910, 924, "竞价采集窗口"),
    ("w2s_confirm", 925, 935, "W2S 确认窗口"),
    ("intraday_am", 930, 1130, "盘中上午"),
    ("lunch", 1130, 1300, "午休"),
    ("intraday_pm", 1300, 1500, "盘中下午"),
    ("closed", 1500, 2359, "收盘后"),
]

# ── Retry backoff (seconds) ──────────────────────────────────────────

RETRY_BACKOFF = [60, 180, 300]

# ── Circuit breaker threshold ─────────────────────────────────────────

CIRCUIT_BREAKER_FAILURES = 3

# ── Data models ────────────────────────────────────────────────────────


@dataclass
class OrchestratorServiceState:
    name: str
    enabled: bool = True
    desired_state: str = "not_in_window"
    observed_state: str = "unknown"
    owner: str = ""
    dependencies: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    last_action: str | None = None
    last_error: str | None = None
    next_retry_at: str | None = None


@dataclass
class OrchestratorStatus:
    enabled: bool
    actions_enabled: bool = False
    dry_run: bool = True
    dry_run_forced: bool = False
    dry_run_forced_reason: str = ""
    now_override: str | None = None
    trade_date: str = ""
    phase: str = "unknown"
    phase_label: str = ""
    now_cn: str = ""
    tick_seq: int = 0
    is_trade_day: bool = False
    services: dict[str, OrchestratorServiceState] = field(default_factory=dict)
    planned_actions: list[dict[str, Any]] = field(default_factory=list)
    executed_actions: list[dict[str, Any]] = field(default_factory=list)
    global_blockers: list[str] = field(default_factory=list)
    tick_duration_ms: int = 0


# ── Orchestrator ────────────────────────────────────────────────────────


class RealtimeBusinessOrchestrator:
    """Controlled business orchestrator (P4-2C).

    Double gate: enabled=True enables auto-tick loop.
                 actions_enabled=True enables real start/stop execution.

    Only 3 action types: ensure_cdp_service, ensure_jyhf_market, ensure_jyhf_auction.
    """

    def __init__(self, app) -> None:
        self._app = app
        self.enabled = _env_bool("REALTIME_ORCHESTRATOR_ENABLED", False)
        self.actions_enabled = _env_bool("REALTIME_ORCHESTRATOR_ACTIONS_ENABLED", False)
        self._interval_sec = int(os.environ.get("REALTIME_ORCHESTRATOR_INTERVAL_SEC", "30"))
        self._tick_seq = 0
        self._tick_running = False
        self._loop_task: asyncio.Task | None = None
        self._sps_base = os.environ.get(
            "STOCK_PROCESSING_READ_BASE_URL", "http://127.0.0.1:8090"
        ).rstrip("/")
        self._redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip()

        # Action history: keyed by "trade_date|phase|service|action"
        self._action_history: dict[str, dict[str, Any]] = {}
        # Circuit breaker: service_name → consecutive failure count
        self._circuit_state: dict[str, int] = {}
        # Retry state: service_name → (fail_count, next_retry_ts)
        self._retry_state: dict[str, tuple[int, float]] = {}
        # Audit log file
        self._audit_dir = Path(os.environ.get("REALTIME_LOG_DIR", str(Path(__file__).resolve().parents[3] / "logs" / "realtime")))
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._audit_path = self._audit_dir / "orchestrator_audit.jsonl"

        logger.info(
            "RealtimeBusinessOrchestrator initialized: enabled=%s actions_enabled=%s interval=%ss",
            self.enabled, self.actions_enabled, self._interval_sec,
        )

    # ── Public API ─────────────────────────────────────────────────

    async def get_status(self, now_override: str | None = None) -> OrchestratorStatus:
        return await self.tick(dry_run=True, now_override=now_override)

    async def enable(self, actions_enabled: bool = False) -> dict[str, Any]:
        """Enable auto-tick loop. actions_enabled separately gates real execution."""
        self.enabled = True
        self.actions_enabled = actions_enabled
        self._start_loop()
        self._write_audit({"event": "orchestrator_enabled", "actions_enabled": actions_enabled})
        return {"ok": True, "enabled": True, "actions_enabled": self.actions_enabled}

    async def disable(self) -> dict[str, Any]:
        """Disable auto-tick loop and all actions."""
        self.enabled = False
        self.actions_enabled = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        self._write_audit({"event": "orchestrator_disabled"})
        return {"ok": True, "enabled": False, "actions_enabled": False}

    async def reset_action_history(self) -> dict[str, Any]:
        """Reset action history, retry state, and circuit breakers (for debugging)."""
        self._action_history.clear()
        self._retry_state.clear()
        self._circuit_state.clear()
        self._write_audit({"event": "action_history_reset"})
        return {"ok": True, "message": "action history, retry state, and circuits reset"}

    async def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read recent audit log entries."""
        entries: list[dict[str, Any]] = []
        try:
            if self._audit_path.exists():
                lines = self._audit_path.read_text().strip().splitlines()
                for line in lines[-limit:]:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
        return entries

    async def tick(self, dry_run: bool = True, now_override: str | None = None) -> OrchestratorStatus:
        """Execute one diagnostic tick. Respects actions_enabled double gate."""
        # In-flight lock
        if self._tick_running:
            logger.warning("tick already running, skipping")
            return OrchestratorStatus(
                enabled=self.enabled, actions_enabled=self.actions_enabled,
                dry_run=True, phase="tick_overlap",
            )

        self._tick_running = True
        t0 = _time.monotonic()
        try:
            status = await self._tick_impl(dry_run=dry_run, now_override=now_override)
            status.tick_duration_ms = int((_time.monotonic() - t0) * 1000)
            return status
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("tick failed: %s", exc)
            return OrchestratorStatus(
                enabled=self.enabled, actions_enabled=self.actions_enabled,
                dry_run=True, phase="tick_error",
                global_blockers=[f"tick exception: {exc}"],
            )
        finally:
            self._tick_running = False
            elapsed_ms = int((_time.monotonic() - t0) * 1000)
            if elapsed_ms > 3000:
                logger.warning("tick slow: %dms", elapsed_ms)

    # ── Internal tick implementation ──────────────────────────────

    async def _tick_impl(self, dry_run: bool, now_override: str | None) -> OrchestratorStatus:
        self._tick_seq += 1
        now = _parse_now_override(now_override) if now_override else datetime.now(TZ_CN)
        trade_date = now.strftime("%Y-%m-%d")
        phase, phase_label = _trading_phase(now)
        is_trade_day = _is_trade_day(now)
        hhmm = now.hour * 100 + now.minute

        # Double gate: both enabled AND actions_enabled required for real execution
        execute = self.enabled and self.actions_enabled and (not dry_run) and is_trade_day

        desired_map = _desired_states(phase, is_trade_day)
        _any_wanted = any(v == "wanted" for v in desired_map.values())

        services: dict[str, OrchestratorServiceState] = {}
        planned_actions: list[dict[str, Any]] = []
        executed_actions: list[dict[str, Any]] = []

        # 1. CDP / Token readiness
        cdp_state = await self._check_cdp_token(now, desired_map.get("cdp_token", "not_in_window"), probe_sps=_any_wanted)
        services["cdp_token"] = cdp_state

        # 2. JYHF Market collector
        market_state = await self._check_jyhf_market(now, desired_map.get("jyhf_market", "not_in_window"), services, probe_sps=_any_wanted)
        services["jyhf_market"] = market_state

        # 3. JYHF Auction collector
        auction_state = await self._check_jyhf_auction(now, desired_map.get("jyhf_auction", "not_in_window"), services)
        services["jyhf_auction"] = auction_state

        # 4-5. W2S / Support Alert (read-only, never auto-started)
        w2s_state = await self._check_w2s_alert(now, desired_map.get("w2s_alert", "not_in_window"), services)
        services["w2s_alert"] = w2s_state
        support_state = await self._check_support_alert(now, desired_map.get("support_alert", "not_in_window"), services)
        services["support_alert"] = support_state

        # Compute planned_actions
        if is_trade_day:
            planned_actions = _compute_planned_actions(services, phase, hhmm)

        # Execute actions if enabled
        if execute and planned_actions:
            executed_actions = await self._execute_actions(
                services, planned_actions, trade_date, phase
            )

        global_blockers = [
            f"{s.name}: {b}" for s in services.values() for b in s.blockers
        ]

        t0 = _time.monotonic()
        return OrchestratorStatus(
            enabled=self.enabled,
            actions_enabled=self.actions_enabled,
            dry_run=not execute,
            dry_run_forced=not execute and not dry_run,
            dry_run_forced_reason="P4-2C: actions_enabled gate" if not execute and not dry_run else "",
            now_override=now_override,
            trade_date=trade_date,
            phase=phase,
            phase_label=phase_label,
            now_cn=now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            tick_seq=self._tick_seq,
            is_trade_day=is_trade_day,
            services=services,
            planned_actions=planned_actions,
            executed_actions=executed_actions,
            global_blockers=global_blockers,
        )

    # ── Action execution ───────────────────────────────────────────

    async def _execute_actions(
        self,
        services: dict[str, OrchestratorServiceState],
        planned: list[dict[str, Any]],
        trade_date: str,
        phase: str,
    ) -> list[dict[str, Any]]:
        """Execute planned actions subject to: white-list, circuit breaker, once-per-window, backoff."""
        executed: list[dict[str, Any]] = []
        for action in planned:
            svc_name = action["service"]
            action_type = action.get("action", "")

            # White-list check
            if svc_name not in ALLOWED_ACTIONS:
                continue
            if "start" not in action_type:
                continue

            # Circuit breaker check
            if self._circuit_state.get(svc_name, 0) >= CIRCUIT_BREAKER_FAILURES:
                action["skipped"] = "circuit_open"
                executed.append(action)
                continue

            # Once-per-window check
            window_key = f"{trade_date}|{phase}|{svc_name}|start"
            if window_key in self._action_history:
                prev = self._action_history[window_key]
                if prev.get("result") == "ok":
                    action["skipped"] = "already_executed"
                    executed.append(action)
                    continue

            # Retry backoff check
            if svc_name in self._retry_state:
                fail_count, next_ts = self._retry_state[svc_name]
                if _time.time() < next_ts:
                    action["skipped"] = f"backoff_until_{int(next_ts)}"
                    executed.append(action)
                    continue

            # Execute
            t0 = _time.monotonic()
            try:
                if svc_name == "cdp_token":
                    result = await self._execute_ensure_cdp()
                elif svc_name == "jyhf_market":
                    result = await self._execute_ensure_jyhf_market()
                elif svc_name == "jyhf_auction":
                    result = await self._execute_ensure_jyhf_auction()
                else:
                    continue
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            duration_ms = int((_time.monotonic() - t0) * 1000)
            action["executed"] = True
            action["result"] = result.get("ok", False)
            action["duration_ms"] = duration_ms

            # Audit
            self._write_audit({
                "ts": datetime.now(TZ_CN).isoformat(),
                "phase": phase,
                "service": svc_name,
                "action": "start",
                "result": "ok" if result.get("ok") else "failed",
                "error": result.get("error", ""),
                "duration_ms": duration_ms,
            })

            # Update state
            if result.get("ok"):
                self._action_history[window_key] = {"result": "ok", "ts": datetime.now(TZ_CN).isoformat()}
                self._retry_state.pop(svc_name, None)
                self._circuit_state[svc_name] = 0
            else:
                # Retry backoff
                fail_count = self._retry_state.get(svc_name, (0, 0))[0] + 1
                backoff_idx = min(fail_count - 1, len(RETRY_BACKOFF) - 1)
                next_ts = _time.time() + RETRY_BACKOFF[backoff_idx]
                self._retry_state[svc_name] = (fail_count, next_ts)
                self._circuit_state[svc_name] = self._circuit_state.get(svc_name, 0) + 1
                action["next_retry_at"] = datetime.fromtimestamp(next_ts, TZ_CN).isoformat()

            executed.append(action)

        return executed

    async def _execute_ensure_cdp(self) -> dict[str, Any]:
        """Ensure CDP service is running."""
        try:
            cdp_mgr = self._app.state.cdp_manager
            status = await cdp_mgr.get_status()
            if status.get("service_running"):
                return {"ok": True, "status": "already_running"}
            # Start CDP service
            result = await cdp_mgr.start_collector({})
            return {"ok": result.get("ok", False), "status": "started"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _execute_ensure_jyhf_market(self) -> dict[str, Any]:
        """Ensure JYHF market collector is running via SPS."""
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                r = await client.post(f"{self._sps_base}/api/v1/jyhf-market/collector/start")
                data = r.json() if r.status_code == 200 else {"ok": False, "status_code": r.status_code}
                return data if isinstance(data, dict) else {"ok": False}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _execute_ensure_jyhf_auction(self) -> dict[str, Any]:
        """Ensure JYHF auction collector is running via AuctionManager."""
        try:
            now = datetime.now(TZ_CN)
            yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            result = await self._app.state.auction_manager.start(
                trade_date=now.strftime("%Y-%m-%d"),
                candidate_date=yesterday,
            )
            return {"ok": result.get("ok", False), "status": result.get("message", "")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Service check methods ──────────────────────────────────────

    async def _check_cdp_token(self, now: datetime, desired: str, probe_sps: bool = True) -> OrchestratorServiceState:
        state = self._new_state("cdp_token", desired)
        evidence: dict[str, Any] = {}
        try:
            cdp_mgr = self._app.state.cdp_manager
            cdp_status = await cdp_mgr.get_status()
            evidence["service_running"] = cdp_status.get("service_running", False)
            evidence["cdp_connected"] = cdp_status.get("cdp_connected", False)
            evidence["app_running"] = cdp_status.get("app_running", False)
            evidence["service_owner"] = cdp_status.get("service_owner", "none")
        except Exception as exc:
            evidence["service_running"] = False
            evidence["error"] = str(exc)
            state.blockers.append(f"CDP manager unreachable: {exc}")

        token_valid = False
        if probe_sps:
            try:
                async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                    r = await client.get(f"{self._sps_base}/api/v1/jyhf-market/status")
                    if r.status_code == 200:
                        data = r.json()
                        token_valid = bool(data.get("token_valid"))
                        evidence["token_valid"] = token_valid
                        evidence["jyhf_market_running"] = data.get("running", False)
                    else:
                        evidence["token_valid"] = False
            except Exception as exc:
                evidence["token_valid"] = False
                evidence["token_error"] = str(exc)
                state.blockers.append(f"SPS jyhf-market status unreachable: {exc}")
        else:
            evidence["token_valid"] = False
            evidence["token_skipped"] = True

        state.evidence = evidence
        if not evidence.get("service_running"):
            state.observed_state = "blocked"
            state.blockers.append("CDP service not running")
        elif not evidence.get("cdp_connected"):
            state.observed_state = "blocked"
            state.blockers.append("CDP not connected to browser")
        elif not token_valid:
            state.observed_state = "blocked"
            state.blockers.append("JYHF token not ready or expired")
        else:
            state.observed_state = "ready"
        return state

    async def _check_jyhf_market(self, now: datetime, desired: str, services: dict, probe_sps: bool = True) -> OrchestratorServiceState:
        state = self._new_state("jyhf_market", desired)
        evidence: dict[str, Any] = {}
        if probe_sps:
            try:
                async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                    r = await client.get(f"{self._sps_base}/api/v1/jyhf-market/status")
                    if r.status_code == 200:
                        data = r.json()
                        evidence["running"] = data.get("running", False)
                        evidence["token_valid"] = data.get("token_valid", False)
                    else:
                        evidence["running"] = False
            except Exception as exc:
                evidence["running"] = False
                evidence["error"] = str(exc)
                state.blockers.append(f"SPS jyhf-market status unreachable: {exc}")
        else:
            evidence["running"] = False
            evidence["token_skipped"] = True
        state.evidence = evidence
        dep_blocked = _check_deps("jyhf_market", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        elif evidence.get("running"):
            state.observed_state = "running"
        else:
            state.observed_state = "stopped"
        return state

    async def _check_jyhf_auction(self, now: datetime, desired: str, services: dict) -> OrchestratorServiceState:
        state = self._new_state("jyhf_auction", desired)
        evidence: dict[str, Any] = {}
        try:
            status = self._app.state.auction_manager.status()
            evidence["running"] = status.get("running", False)
            evidence["state"] = status.get("state", "idle")
            evidence["trade_date"] = status.get("trade_date")
            evidence["candidate_date"] = status.get("candidate_date")
            evidence["rounds"] = status.get("rounds", 0)
            evidence["points"] = status.get("points", 0)
        except Exception as exc:
            evidence["running"] = False
            evidence["error"] = str(exc)
            state.blockers.append(f"Auction manager unreachable: {exc}")
        state.evidence = evidence
        dep_blocked = _check_deps("jyhf_auction", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        elif evidence.get("running"):
            state.observed_state = "running"
        else:
            state.observed_state = "stopped"
        return state

    async def _check_w2s_alert(self, now: datetime, desired: str, services: dict) -> OrchestratorServiceState:
        state = self._new_state("w2s_alert", desired)
        evidence: dict[str, Any] = {
            "sse_available": None,
            "sse_probe_skipped": True,
            "readiness_endpoint_missing": True,
            "note": "SSE stream not probed by orchestrator. P4-2E will add dedicated readiness endpoint.",
        }
        state.evidence = evidence
        dep_blocked = _check_deps("w2s_alert", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        else:
            state.observed_state = "degraded"
            state.blockers.append("dedicated readiness endpoint not implemented (P4-2E)")
        return state

    async def _check_support_alert(self, now: datetime, desired: str, services: dict) -> OrchestratorServiceState:
        state = self._new_state("support_alert", desired)
        evidence: dict[str, Any] = {
            "sse_available": None,
            "sse_probe_skipped": True,
            "readiness_endpoint_missing": True,
            "note": "SSE stream not probed by orchestrator. P4-2E will add dedicated readiness endpoint.",
        }
        state.evidence = evidence
        dep_blocked = _check_deps("support_alert", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        else:
            state.observed_state = "degraded"
            state.blockers.append("dedicated readiness endpoint not implemented (P4-2E)")
        return state

    # ── Helpers ────────────────────────────────────────────────────

    def _new_state(self, name: str, desired: str) -> OrchestratorServiceState:
        return OrchestratorServiceState(
            name=name, enabled=True, desired_state=desired,
            observed_state="unknown",
            owner=SERVICE_OWNERS.get(name, "unknown"),
            dependencies=list(SERVICE_DEPENDENCIES.get(name, [])),
        )

    def _start_loop(self) -> None:
        if self._loop_task and not self._loop_task.done():
            return
        self._loop_task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        logger.info("orchestrator auto-tick loop started")
        while self.enabled:
            try:
                # Respect interval: sleep first, then tick
                await asyncio.sleep(self._interval_sec)
                if not self.enabled:
                    break
                await self.tick(dry_run=not self.actions_enabled)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("auto-tick loop error")
        logger.info("orchestrator auto-tick loop stopped")

    def _write_audit(self, entry: dict[str, Any]) -> None:
        entry.setdefault("ts", datetime.now(TZ_CN).isoformat())
        try:
            with open(self._audit_path, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("audit write failed: %s", exc)


# ── Module-level helpers ──────────────────────────────────────────────


def _is_trade_day(now: datetime) -> bool:
    return now.weekday() < 5


def _trading_phase(now: datetime) -> tuple[str, str]:
    if not _is_trade_day(now):
        return ("non_trading_day", "非交易日")
    hhmm = now.hour * 100 + now.minute
    for phase_key, start, end, label in TRADING_PHASES:
        if start <= hhmm <= end:
            return (phase_key, label)
    return ("off_hours", "非交易时段")


def _desired_states(phase: str, is_trade_day: bool) -> dict[str, str]:
    if not is_trade_day:
        return {s: "not_in_window" for s in SERVICE_DEPENDENCIES}
    phase_wants: dict[str, list[str]] = {
        "preopen_prepare": ["cdp_token"],
        "auction_collect": ["cdp_token", "jyhf_market", "jyhf_auction"],
        "w2s_confirm": ["cdp_token", "jyhf_market", "jyhf_auction", "w2s_alert"],
        "intraday_am": ["jyhf_market", "w2s_alert", "support_alert"],
        "lunch": [],
        "intraday_pm": ["jyhf_market", "w2s_alert", "support_alert"],
        "closed": [],
        "off_hours": [],
        "non_trading_day": [],
    }
    wanted = phase_wants.get(phase, [])
    return {s: ("wanted" if s in wanted else "not_in_window") for s in SERVICE_DEPENDENCIES}


def _check_deps(name: str, services: dict[str, OrchestratorServiceState]) -> list[str]:
    blockers: list[str] = []
    for dep_name in SERVICE_DEPENDENCIES.get(name, []):
        dep = services.get(dep_name)
        if not dep:
            blockers.append(f"dependency {dep_name} status unknown")
            continue
        if dep.observed_state in ("blocked", "degraded", "failed", "unknown"):
            blockers.append(f"dependency {dep_name} not ready (state={dep.observed_state})")
        elif dep.observed_state == "stopped" and dep.desired_state == "wanted":
            blockers.append(f"dependency {dep_name} is stopped but wanted")
    return blockers


def _compute_planned_actions(
    services: dict[str, OrchestratorServiceState], phase: str, hhmm: int,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for svc_name in _topological_order():
        svc = services.get(svc_name)
        if not svc or not svc.enabled:
            continue
        if svc.desired_state != "wanted":
            continue
        if svc.observed_state in ("running", "ready"):
            continue

        # cdp_token special case: CDP service not running IS a valid reason to start it.
        # Downstream will still be blocked if token is not ready after CDP starts.
        if svc_name == "cdp_token":
            service_running = bool(svc.evidence.get("service_running"))
            if not service_running:
                actions.append({
                    "service": "cdp_token",
                    "action": "would_start",
                    "reason": f"{phase} window, CDP service not running",
                    "owner": svc.owner,
                })
                continue

        dep_blockers = _check_deps(svc_name, services)
        if dep_blockers:
            continue
        if svc.observed_state in ("stopped", "unknown"):
            actions.append({
                "service": svc_name,
                "action": "would_start",
                "reason": f"{phase} window, dependencies satisfied",
                "owner": svc.owner,
            })
        elif svc.observed_state == "blocked":
            own_blockers = [b for b in svc.blockers if not b.startswith("dependency")]
            if not own_blockers:
                actions.append({
                    "service": svc_name,
                    "action": "would_retry_start",
                    "reason": "previously blocked but deps now satisfied",
                    "owner": svc.owner,
                })
    return actions


def _topological_order() -> list[str]:
    return ["cdp_token", "jyhf_market", "jyhf_auction", "w2s_alert", "support_alert"]


def _parse_now_override(value: str) -> datetime:
    import re
    if re.match(r"^\d{2}:\d{2}$", value):
        today = datetime.now(TZ_CN)
        h, m = map(int, value.split(":"))
        return today.replace(hour=h, minute=m, second=0, microsecond=0)
    return datetime.fromisoformat(value)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default

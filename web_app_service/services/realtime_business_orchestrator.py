"""P4-2A: Realtime Business Orchestrator — read-only status + dry_run tick.

First phase: NEVER starts/stops any service. Only collects status, evaluates
dependencies, and outputs planned_actions in dry_run mode.

Architecture:
  Frontend
    ↓
  BFF RealtimeBusinessOrchestrator (THIS FILE)
    ↓
  Owners:
    - JyhfCdpManager (CDP service / app / token readiness)
    - SPS jyhf-market collector (market data + token_valid)
    - JyhfAuctionManager (auction collector)
    - SPS W2S/Kline readiness endpoints

Dependency chain:
  cdp_token          ← no business deps (needs CDP service + app + token)
  jyhf_market        ← depends on cdp_token
  jyhf_auction       ← depends on cdp_token, jyhf_market
  w2s_alert          ← depends on cdp_token, jyhf_auction, snapshot_ready, candidates_ready
  support_alert      ← depends on jyhf_market
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

# ── Trading phase windows (HHMM in Asia/Shanghai) ─────────────────────

TRADING_PHASES: list[tuple[str, int, int, str]] = [
    # (phase_name, start_hhmm, end_hhmm, label)
    ("preopen_prepare", 900, 909, "盘前准备"),
    ("auction_collect", 910, 924, "竞价采集窗口"),
    ("w2s_confirm", 925, 935, "W2S 确认窗口"),
    ("intraday_am", 930, 1130, "盘中上午"),
    ("lunch", 1130, 1300, "午休"),
    ("intraday_pm", 1300, 1500, "盘中下午"),
    ("closed", 1500, 2359, "收盘后"),
]

# ── Data models ────────────────────────────────────────────────────────


@dataclass
class OrchestratorServiceState:
    name: str
    enabled: bool = True
    desired_state: str = "not_in_window"   # disabled | wanted | not_in_window | observe
    observed_state: str = "unknown"        # unknown | ready | running | stopped | blocked | degraded | failed
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
    dry_run: bool
    dry_run_forced: bool = False
    dry_run_forced_reason: str = ""
    trade_date: str = ""
    phase: str = "unknown"
    phase_label: str = ""
    now_cn: str = ""
    tick_seq: int = 0
    is_trade_day: bool = False
    services: dict[str, OrchestratorServiceState] = field(default_factory=dict)
    planned_actions: list[dict[str, Any]] = field(default_factory=list)
    global_blockers: list[str] = field(default_factory=list)


# ── Orchestrator ────────────────────────────────────────────────────────


class RealtimeBusinessOrchestrator:
    """Read-only business orchestrator (P4-2A).

    Does NOT start or stop any service. Only collects status, evaluates
    dependencies, and reports planned_actions in dry_run mode.
    """

    def __init__(self, app) -> None:
        self._app = app
        self.enabled = _env_bool("REALTIME_ORCHESTRATOR_ENABLED", False)
        self._tick_seq = 0
        self._sps_base = os.environ.get(
            "STOCK_PROCESSING_READ_BASE_URL", "http://127.0.0.1:8090"
        ).rstrip("/")
        self._redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip()
        logger.info(
            "RealtimeBusinessOrchestrator initialized: enabled=%s sps_base=%s",
            self.enabled,
            self._sps_base,
        )

    # ── Public API ─────────────────────────────────────────────────

    async def get_status(self) -> OrchestratorStatus:
        """Return current orchestrator status (read-only, no side effects)."""
        return await self.tick(dry_run=True)

    async def tick(self, dry_run: bool = True) -> OrchestratorStatus:
        """Collect all service statuses, evaluate dependencies, output planned actions.

        P4-2A safety lock: dry_run is FORCED to True regardless of input.
        This phase NEVER starts or stops any service.
        """
        dry_run_was_requested = dry_run
        dry_run = True  # P4-2A safety lock

        self._tick_seq += 1
        now = datetime.now(TZ_CN)
        trade_date = now.strftime("%Y-%m-%d")
        phase, phase_label = _trading_phase(now)
        is_trade_day = _is_trade_day(now)
        hhmm = now.hour * 100 + now.minute

        # Determine desired states per service based on current phase
        desired_map = _desired_states(phase, is_trade_day)

        # Collect observed states
        services: dict[str, OrchestratorServiceState] = {}
        planned_actions: list[dict[str, Any]] = []
        global_blockers: list[str] = []

        # 1. CDP / Token readiness
        cdp_state = await self._check_cdp_token(now, desired_map.get("cdp_token", "not_in_window"))
        services["cdp_token"] = cdp_state

        # 2. JYHF Market collector
        market_state = await self._check_jyhf_market(now, desired_map.get("jyhf_market", "not_in_window"), services)
        services["jyhf_market"] = market_state

        # 3. JYHF Auction collector
        auction_state = await self._check_jyhf_auction(now, desired_map.get("jyhf_auction", "not_in_window"), services)
        services["jyhf_auction"] = auction_state

        # 4. W2S Alert readiness
        w2s_state = await self._check_w2s_alert(now, desired_map.get("w2s_alert", "not_in_window"), services)
        services["w2s_alert"] = w2s_state

        # 5. Support Alert readiness
        support_state = await self._check_support_alert(now, desired_map.get("support_alert", "not_in_window"), services)
        services["support_alert"] = support_state

        # Compute planned_actions (only in dry_run mode)
        if dry_run and is_trade_day:
            planned_actions = _compute_planned_actions(services, phase, hhmm)

        # Compute global blockers
        global_blockers = [
            f"{s.name}: {b}" for s in services.values() for b in s.blockers
        ]

        status = OrchestratorStatus(
            enabled=self.enabled,
            dry_run=True,  # P4-2A: always dry_run
            dry_run_forced=not dry_run_was_requested,
            dry_run_forced_reason="P4-2A is read-only; start/stop disabled",
            trade_date=trade_date,
            phase=phase,
            phase_label=phase_label,
            now_cn=now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            tick_seq=self._tick_seq,
            is_trade_day=is_trade_day,
            services=services,
            planned_actions=planned_actions,
            global_blockers=global_blockers,
        )
        return status

    # ── Service check methods (all read-only) ───────────────────────

    async def _check_cdp_token(self, now: datetime, desired: str) -> OrchestratorServiceState:
        """Check CDP service / app / token readiness.

        Evidence gathered from:
          1. CDP Manager get_status() → service_running, app_running, cdp_connected
          2. SPS /api/v1/jyhf-market/status → token_valid
        """
        state = self._new_state("cdp_token", desired)
        evidence: dict[str, Any] = {}

        # Check CDP manager status
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

        # Check SPS token status
        token_valid = False
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
                    evidence["sps_status_code"] = r.status_code
        except Exception as exc:
            evidence["token_valid"] = False
            evidence["token_error"] = str(exc)
            state.blockers.append(f"SPS jyhf-market status unreachable: {exc}")

        state.evidence = evidence

        # Evaluate readiness
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

    async def _check_jyhf_market(
        self, now: datetime, desired: str, services: dict[str, OrchestratorServiceState]
    ) -> OrchestratorServiceState:
        """Check JYHF market collector status via SPS."""
        state = self._new_state("jyhf_market", desired)
        evidence: dict[str, Any] = {}

        try:
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                r = await client.get(f"{self._sps_base}/api/v1/jyhf-market/status")
                if r.status_code == 200:
                    data = r.json()
                    evidence["running"] = data.get("running", False)
                    evidence["token_valid"] = data.get("token_valid", False)
                    evidence["watch_stock_count"] = data.get("watch_stock_count", 0)
                else:
                    evidence["running"] = False
                    evidence["sps_status_code"] = r.status_code
        except Exception as exc:
            evidence["running"] = False
            evidence["error"] = str(exc)
            state.blockers.append(f"SPS jyhf-market status unreachable: {exc}")

        state.evidence = evidence

        # Evaluate readiness with dependency check
        dep_blocked = _check_deps("jyhf_market", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        elif evidence.get("running"):
            state.observed_state = "running"
        elif desired == "wanted":
            state.observed_state = "stopped"
        else:
            state.observed_state = "stopped"

        return state

    async def _check_jyhf_auction(
        self, now: datetime, desired: str, services: dict[str, OrchestratorServiceState]
    ) -> OrchestratorServiceState:
        """Check JYHF auction collector status via AuctionManager."""
        state = self._new_state("jyhf_auction", desired)
        evidence: dict[str, Any] = {}

        try:
            auction_mgr = self._app.state.auction_manager
            status = auction_mgr.status()
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

        # Evaluate readiness with dependency check
        dep_blocked = _check_deps("jyhf_auction", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        elif evidence.get("running"):
            state.observed_state = "running"
        elif desired == "wanted":
            state.observed_state = "stopped"
        else:
            state.observed_state = "stopped"

        return state

    async def _check_w2s_alert(
        self, now: datetime, desired: str, services: dict[str, OrchestratorServiceState]
    ) -> OrchestratorServiceState:
        """Check W2S alert readiness: candidate pool + auction snapshot + sse availability."""
        state = self._new_state("w2s_alert", desired)
        evidence: dict[str, Any] = {
            "candidates_ready": False,
            "auction_snapshot_ready": False,
            "sse_available": False,
            "note": "P4-2A best-effort Redis check; P4-2E will add dedicated SPS readiness endpoint",
        }

        # Check SSE endpoint availability
        try:
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
                r = await client.get(f"{self._sps_base}/api/v1/w2s-alerts/stream")
                # SSE endpoint: any non-error response means it's available
                evidence["sse_available"] = r.status_code < 500
        except Exception as exc:
            evidence["sse_error"] = str(exc)

        # Check Redis for W2S candidate/snapshot data
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(self._redis_url, socket_connect_timeout=3)
            try:
                # Check if candidate pool exists for today
                trade_date = now.strftime("%Y%m%d")
                candidate_key = f"w2s:candidates:{trade_date}"
                candidates_count = await r.zcard(candidate_key) if await r.exists(candidate_key) else 0
                evidence["candidates_ready"] = candidates_count > 0
                evidence["candidates_count"] = candidates_count

                # Check if auction snapshots exist
                snapshot_key = f"w2s:auction_snapshots:{trade_date}"
                snapshots_count = await r.zcard(snapshot_key) if await r.exists(snapshot_key) else 0
                evidence["auction_snapshot_ready"] = snapshots_count > 0
                evidence["snapshots_count"] = snapshots_count
            finally:
                await r.aclose()
        except Exception as exc:
            evidence["redis_error"] = str(exc)

        state.evidence = evidence

        # Evaluate readiness
        dep_blocked = _check_deps("w2s_alert", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        elif evidence.get("candidates_ready") and evidence.get("auction_snapshot_ready"):
            state.observed_state = "ready"
        elif evidence.get("sse_available"):
            state.observed_state = "degraded"
            if not evidence.get("candidates_ready"):
                state.blockers.append("W2S candidate pool not ready")
            if not evidence.get("auction_snapshot_ready"):
                state.blockers.append("Auction snapshot data not ready")
        else:
            state.observed_state = "degraded"
            state.blockers.append("W2S SSE endpoint unavailable")

        return state

    async def _check_support_alert(
        self, now: datetime, desired: str, services: dict[str, OrchestratorServiceState]
    ) -> OrchestratorServiceState:
        """Check Kline support alert readiness."""
        state = self._new_state("support_alert", desired)
        evidence: dict[str, Any] = {
            "sse_available": False,
            "alerts_stream_exists": False,
        }

        # Check SSE endpoint availability
        try:
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
                r = await client.get(f"{self._sps_base}/api/v1/kline-alerts/stream")
                evidence["sse_available"] = r.status_code < 500
        except Exception as exc:
            evidence["sse_error"] = str(exc)

        # Check if alert stream has data
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(self._redis_url, socket_connect_timeout=3)
            try:
                info = await r.xinfo_stream("stream:kline:alerts")
                evidence["alerts_stream_exists"] = True
                evidence["alerts_stream_length"] = info.get("length", 0)
            except Exception:
                evidence["alerts_stream_exists"] = False
            finally:
                await r.aclose()
        except Exception as exc:
            evidence["redis_error"] = str(exc)

        state.evidence = evidence

        # Evaluate readiness
        dep_blocked = _check_deps("support_alert", services)
        if dep_blocked:
            state.observed_state = "blocked"
            state.blockers.extend(dep_blocked)
        elif evidence.get("sse_available"):
            state.observed_state = "ready"
        else:
            state.observed_state = "degraded"
            state.blockers.append("Kline support alert SSE endpoint unavailable")

        return state

    # ── Helpers ────────────────────────────────────────────────────

    def _new_state(self, name: str, desired: str) -> OrchestratorServiceState:
        return OrchestratorServiceState(
            name=name,
            enabled=True,
            desired_state=desired,
            observed_state="unknown",
            owner=SERVICE_OWNERS.get(name, "unknown"),
            dependencies=list(SERVICE_DEPENDENCIES.get(name, [])),
        )


# ── Module-level helpers ──────────────────────────────────────────────


def _now_cn() -> datetime:
    return datetime.now(TZ_CN)


def _is_trade_day(now: datetime) -> bool:
    """Weekday check: Monday=0 .. Friday=4."""
    return now.weekday() < 5


def _trading_phase(now: datetime) -> tuple[str, str]:
    """Determine current trading phase. Returns (phase_key, phase_label)."""
    if not _is_trade_day(now):
        return ("non_trading_day", "非交易日")
    hhmm = now.hour * 100 + now.minute
    for phase_key, start, end, label in TRADING_PHASES:
        if start <= hhmm <= end:
            return (phase_key, label)
    return ("off_hours", "非交易时段")


def _desired_states(phase: str, is_trade_day: bool) -> dict[str, str]:
    """Map trading phase to desired states for each service."""
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
    return {
        s: ("wanted" if s in wanted else "not_in_window")
        for s in SERVICE_DEPENDENCIES
    }


def _check_deps(name: str, services: dict[str, OrchestratorServiceState]) -> list[str]:
    """Check if all dependencies of `name` are ready/running.

    Returns list of blocker messages; empty list means deps are satisfied.
    """
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
    services: dict[str, OrchestratorServiceState],
    phase: str,
    hhmm: int,
) -> list[dict[str, Any]]:
    """Compute what the orchestrator WOULD do if auto-start were enabled.

    Only for services whose desired_state is 'wanted' and observed_state is 'stopped'
    or 'blocked' (but only if blockers are not dependency-related — own deps checked).
    """
    actions: list[dict[str, Any]] = []

    # Order matters: dependencies first
    for svc_name in _topological_order():
        svc = services.get(svc_name)
        if not svc or not svc.enabled:
            continue
        if svc.desired_state != "wanted":
            continue
        if svc.observed_state == "running" or svc.observed_state == "ready":
            continue

        # Check if deps are satisfied
        dep_blockers = _check_deps(svc_name, services)
        if dep_blockers:
            continue  # deps not ready, skip

        if svc.observed_state in ("stopped", "unknown"):
            actions.append({
                "service": svc_name,
                "action": "would_start",
                "reason": f"{phase} window, dependencies satisfied",
                "owner": svc.owner,
            })
        elif svc.observed_state == "blocked":
            # Only suggest if blocker is non-dependency
            own_blockers = [b for b in svc.blockers if not b.startswith("dependency")]
            if not own_blockers:
                actions.append({
                    "service": svc_name,
                    "action": "would_retry_start",
                    "reason": f"previously blocked but deps now satisfied",
                    "owner": svc.owner,
                })

    return actions


def _topological_order() -> list[str]:
    """Return services in dependency order (deps first)."""
    # Simple fixed order based on dependency graph
    return ["cdp_token", "jyhf_market", "jyhf_auction", "w2s_alert", "support_alert"]


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default

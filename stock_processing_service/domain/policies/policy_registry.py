"""PolicyRegistry — unified version management for all Cognition Policies.

Every DailyMarketState records a PolicySnapshot so replay is 100% reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Generic, TypeVar

from stock_processing_service.contracts.market_cognition_v1_5 import PolicySnapshot

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Policy(Generic[T]):
    """A versioned Policy with typed config."""

    name: str
    version: str
    config: T
    valid_from: date
    valid_to: date | None = None


class PolicyRegistry:
    """Central registry for all versioned Policies.

    Usage:
        registry = PolicyRegistry()
        registry.register("cycle_fsm", "v1", cycle_fsm_config, date(2026, 1, 1))
        snapshot = registry.snapshot()  # -> PolicySnapshot
    """

    def __init__(self) -> None:
        self._policies: dict[str, Policy[Any]] = {}

    def register(
        self,
        name: str,
        version: str,
        config: Any,
        valid_from: date,
        valid_to: date | None = None,
    ) -> None:
        self._policies[name] = Policy(
            name=name,
            version=version,
            config=config,
            valid_from=valid_from,
            valid_to=valid_to,
        )

    def get(self, name: str) -> Policy[Any] | None:
        return self._policies.get(name)

    def get_version(self, name: str) -> str:
        policy = self._policies.get(name)
        if policy is None:
            return "unknown"
        return policy.version

    @property
    def policies(self) -> dict[str, str]:
        """Return {policy_name: version} mapping."""
        return {name: p.version for name, p in self._policies.items()}

    def snapshot(self) -> PolicySnapshot:
        """Freeze current policy versions into a PolicySnapshot.

        This snapshot is written into every DailyMarketState so that
        historical replay can reconstruct the exact policy environment.
        """
        return PolicySnapshot(
            cycle_fsm=self.get_version("cycle_fsm"),
            divergence=self.get_version("divergence"),
            maturity=self.get_version("maturity"),
            compiler=self.get_version("compiler"),
            snapshot_at=datetime.now(),
        )

    def __repr__(self) -> str:
        versions = ", ".join(
            f"{name}={ver}" for name, ver in self.policies.items()
        )
        return f"PolicyRegistry({versions})"

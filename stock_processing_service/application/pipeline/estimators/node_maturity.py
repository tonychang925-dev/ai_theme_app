"""NodeMaturityEstimator — computes maturity from 6-dim vector using YAML Policy.

Save the vector, not the score. overall is recomputable from vector + weights.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from stock_processing_service.contracts.market_cognition_v1_5 import NodeMaturity


class MaturityPolicy:
    """Loaded from maturity_policy_v1.yaml."""

    def __init__(self, policy_path: str | Path) -> None:
        with open(policy_path) as fh:
            self.config: dict[str, Any] = yaml.safe_load(fh)
        self.version: str = self.config["version"]
        self.weights: dict[str, float] = self.config["weights"]
        self.quality_labels: dict[str, dict[str, Any]] = self.config["quality_labels"]

    def compute_overall(
        self,
        crowding: float,
        volume: float,
        leader: float,
        emotion: float,
        time: float,
    ) -> float:
        """Compute overall maturity from 6-dim vector using configured weights."""
        return round(
            crowding * self.weights.get("crowding", 0.25)
            + volume * self.weights.get("volume", 0.20)
            + leader * self.weights.get("leader", 0.25)
            + emotion * self.weights.get("emotion", 0.15)
            + time * self.weights.get("time", 0.15),
            2,
        )

    def derive_quality_label(self, overall: float, velocity: float = 0.0) -> str:
        """Derive quality label from overall + velocity."""
        namespace = {"overall": overall, "velocity": velocity}
        for label_name, label_def in self.quality_labels.items():
            cond = label_def["condition"]
            try:
                expr = cond.replace(" AND ", " and ").replace(" OR ", " or ")
                if bool(eval(expr, {"__builtins__": {}}, namespace)):
                    return label_name
            except Exception:
                continue
        return "stalling"


class NodeMaturityEstimator:
    """Estimate node maturity from CycleNode + Market Evidence.

    Output: NodeMaturity with full 6-dim vector + Policy-derived overall.
    """

    def __init__(self, policy: MaturityPolicy) -> None:
        self.policy = policy

    def estimate(
        self,
        subject_id: str,
        trade_date: date,
        crowding: float,
        volume: float,
        leader: float,
        emotion: float,
        time: float,
        maturity_id: str = "",
        estimated_days: float | None = None,
        inflection_likelihood: float = 0.0,
        evidence_refs: tuple[str, ...] = (),
    ) -> NodeMaturity:
        """Compute node maturity from 6-dim vector.

        overall is computed by Policy weights. The vector is permanently saved.
        """
        overall = self.policy.compute_overall(
            crowding, volume, leader, emotion, time,
        )

        # Quality label needs velocity — if not available, assume 0
        quality_label = self.policy.derive_quality_label(overall)

        if not maturity_id:
            maturity_id = f"nm:{subject_id}:{trade_date.isoformat()}"

        return NodeMaturity(
            maturity_id=maturity_id,
            subject_id=subject_id,
            trade_date=trade_date,
            overall=overall,
            crowding=crowding,
            volume=volume,
            leader=leader,
            emotion=emotion,
            time=time,
            quality_label=quality_label,
            policy_version=self.policy.version,
            estimated_days_to_threshold=estimated_days,
            inflection_likelihood=inflection_likelihood,
            evidence_refs=evidence_refs,
        )

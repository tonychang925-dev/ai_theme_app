"""DivergenceQualityAnalyzer — derives quality_label from 5-dim vector using YAML Policy.

Save the vector, not the label. Label is recomputable.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from stock_processing_service.contracts.market_cognition_v1_5 import DivergenceQuality


class DivergencePolicy:
    """Loaded from divergence_policy_v1.yaml."""

    def __init__(self, policy_path: str | Path) -> None:
        with open(policy_path) as fh:
            self.config: dict[str, Any] = yaml.safe_load(fh)
        self.version: str = self.config["version"]
        self.labels: dict[str, dict[str, Any]] = self.config["labels"]

    def derive_label(
        self,
        volume_contraction: float,
        leader_intact: float,
        rear_cleared: float,
        capital_redirected: float,
        duration_sufficient: float,
    ) -> str:
        """Derive quality label from 5-dim vector.

        Evaluates label conditions in priority order.
        """
        # Evaluate in order: panic first (most critical)
        priority_order = ["panic", "insufficient", "healthy", "forced"]
        for label_name in priority_order:
            if label_name not in self.labels:
                continue
            condition_str = self.labels[label_name]["condition"]
            if self._eval_condition(
                condition_str,
                volume_contraction,
                leader_intact,
                rear_cleared,
                capital_redirected,
                duration_sufficient,
            ):
                return label_name
        return "insufficient"  # default fallback

    @staticmethod
    def _eval_condition(
        condition: str,
        vc: float, li: float, rc: float, cr: float, ds: float,
    ) -> bool:
        """Simple AND/OR condition evaluator.

        Format: 'dim >= threshold AND dim < threshold OR ...'
        """
        namespace = {
            "volume_contraction": vc,
            "leader_intact": li,
            "rear_cleared": rc,
            "capital_redirected": cr,
            "duration_sufficient": ds,
        }
        try:
            # Replace AND/OR with Python operators
            expr = condition.replace(" AND ", " and ").replace(" OR ", " or ")
            return bool(eval(expr, {"__builtins__": {}}, namespace))
        except Exception:
            return False


class DivergenceQualityAnalyzer:
    """Analyze divergence quality from MarketEvidence + CycleNode state.

    Output: DivergenceQuality with full 5-dim vector + Policy-derived label.
    """

    def __init__(self, policy: DivergencePolicy) -> None:
        self.policy = policy

    def analyze(
        self,
        subject_id: str,
        trade_date: date,
        volume_contraction: float,
        leader_intact: float,
        rear_cleared: float,
        capital_redirected: float,
        duration_sufficient: float,
        quality_id: str = "",
        evidence_refs: tuple[str, ...] = (),
    ) -> DivergenceQuality:
        """Compute divergence quality from 5-dim vector.

        The label is derived by Policy. The vector is permanently saved.
        """
        label = self.policy.derive_label(
            volume_contraction,
            leader_intact,
            rear_cleared,
            capital_redirected,
            duration_sufficient,
        )

        if not quality_id:
            quality_id = f"dq:{subject_id}:{trade_date.isoformat()}"

        return DivergenceQuality(
            quality_id=quality_id,
            subject_id=subject_id,
            trade_date=trade_date,
            volume_contraction=volume_contraction,
            leader_intact=leader_intact,
            rear_cleared=rear_cleared,
            capital_redirected=capital_redirected,
            duration_sufficient=duration_sufficient,
            quality_label=label,
            policy_version=self.policy.version,
            evidence_refs=evidence_refs,
        )

"""WorldStatePersister — disk cache for DailyMarketState objects.

Lightweight JSON serialization with hash-based integrity verification.
Enables resume: skip dates already built and cached.

Layout: <root>/<YYYY>/<YYYY-MM-DD>.json
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stock_processing_service.contracts.market_cognition import canonical_hash
from stock_processing_service.contracts.market_cognition_v1_5 import (
    CycleNode,
    DailyMarketState,
    DivergenceQuality,
    MarketSubject,
    NodeMaturity,
    PolicySnapshot,
    TransitionCandidate,
)


class WorldStatePersister:
    """Save/load DailyMarketState to/from JSON files on disk.

    Each file is a canonical JSON blob with a content_hash for integrity.
    """

    SCHEMA_VERSION = "world_state_cache.v1"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    # ── Public API ──

    def save(self, state: DailyMarketState) -> Path:
        path = self._path_for(state.trade_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._serialize(state)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return path

    def load(self, trade_date: date) -> DailyMarketState | None:
        path = self._path_for(trade_date)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize(payload)

    def exists(self, trade_date: date) -> bool:
        return self._path_for(trade_date).exists()

    def list_dates(self) -> list[date]:
        dates: list[date] = []
        if not self.root.exists():
            return dates
        for year_dir in sorted(self.root.iterdir()):
            if not year_dir.is_dir():
                continue
            for state_file in sorted(year_dir.glob("*.json")):
                try:
                    d = date.fromisoformat(state_file.stem)
                    dates.append(d)
                except ValueError:
                    continue
        return dates

    def count(self) -> int:
        return len(self.list_dates())

    # ── Paths ──

    def _path_for(self, trade_date: date) -> Path:
        return self.root / str(trade_date.year) / f"{trade_date.isoformat()}.json"

    # ── Serialization ──

    @classmethod
    def _serialize(cls, state: DailyMarketState) -> dict[str, Any]:
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "state_id": state.state_id,
            "trade_date": state.trade_date.isoformat(),
            "version": state.version,
            "parent_state": state.parent_state,
            "created_at": state.created_at.isoformat(),
            "policy_snapshot": state.policy_snapshot.to_dict(),
            "subjects": [
                {
                    "subject_id": s.subject_id,
                    "subject_type": s.subject_type,
                    "name": s.name,
                    "parent_subject_id": s.parent_subject_id,
                }
                for s in state.subjects
            ],
            "cycle_nodes": [
                {
                    "node_id": n.node_id,
                    "subject_id": n.subject_id,
                    "trade_date": n.trade_date.isoformat(),
                    "name": n.name,
                    "stage": n.stage,
                    "stage_day": n.stage_day,
                    "consecutive_direction": n.consecutive_direction,
                    "maturity": n.maturity,
                    "confidence": n.confidence,
                    "transition_candidates": [
                        {"target_node": tc.target_node, "probability": tc.probability}
                        for tc in n.transition_candidates
                    ],
                    "quality_label": n.quality_label,
                    "evidence_refs": list(n.evidence_refs),
                }
                for n in state.cycle_nodes
            ],
            "divergence_qualities": [
                {
                    "quality_id": dq.quality_id,
                    "subject_id": dq.subject_id,
                    "trade_date": dq.trade_date.isoformat(),
                    "volume_contraction": dq.volume_contraction,
                    "leader_intact": dq.leader_intact,
                    "rear_cleared": dq.rear_cleared,
                    "capital_redirected": dq.capital_redirected,
                    "duration_sufficient": dq.duration_sufficient,
                    "quality_label": dq.quality_label,
                    "policy_version": dq.policy_version,
                    "evidence_refs": list(dq.evidence_refs),
                }
                for dq in state.divergence_qualities
            ],
            "maturity_estimates": [
                {
                    "maturity_id": m.maturity_id,
                    "subject_id": m.subject_id,
                    "trade_date": m.trade_date.isoformat(),
                    "overall": m.overall,
                    "crowding": m.crowding,
                    "volume": m.volume,
                    "leader": m.leader,
                    "emotion": m.emotion,
                    "time": m.time,
                    "quality_label": m.quality_label,
                    "policy_version": m.policy_version,
                    "estimated_days_to_threshold": m.estimated_days_to_threshold,
                    "inflection_likelihood": m.inflection_likelihood,
                    "evidence_refs": list(m.evidence_refs),
                }
                for m in state.maturity_estimates
            ],
            "content_hash": state.content_hash,
            "evidence_refs": list(state.evidence_refs),
        }

    @classmethod
    def _deserialize(cls, payload: dict[str, Any]) -> DailyMarketState:
        subjects = tuple(
            MarketSubject(
                subject_id=s["subject_id"],
                subject_type=s["subject_type"],
                name=s["name"],
                parent_subject_id=s.get("parent_subject_id"),
            )
            for s in payload["subjects"]
        )

        cycle_nodes = tuple(
            CycleNode(
                node_id=n["node_id"],
                subject_id=n["subject_id"],
                trade_date=date.fromisoformat(n["trade_date"]),
                name=n["name"],
                stage=n["stage"],
                stage_day=n["stage_day"],
                consecutive_direction=n["consecutive_direction"],
                maturity=n["maturity"],
                confidence=n["confidence"],
                transition_candidates=tuple(
                    TransitionCandidate(tc["target_node"], tc["probability"])
                    for tc in n["transition_candidates"]
                ),
                quality_label=n.get("quality_label", ""),
                evidence_refs=tuple(n.get("evidence_refs", [])),
            )
            for n in payload["cycle_nodes"]
        )

        dq_objects = tuple(
            DivergenceQuality(
                quality_id=dq["quality_id"],
                subject_id=dq["subject_id"],
                trade_date=date.fromisoformat(dq["trade_date"]),
                volume_contraction=dq["volume_contraction"],
                leader_intact=dq["leader_intact"],
                rear_cleared=dq["rear_cleared"],
                capital_redirected=dq["capital_redirected"],
                duration_sufficient=dq["duration_sufficient"],
                quality_label=dq["quality_label"],
                policy_version=dq["policy_version"],
                evidence_refs=tuple(dq.get("evidence_refs", [])),
            )
            for dq in payload["divergence_qualities"]
        )

        nm_objects = tuple(
            NodeMaturity(
                maturity_id=m["maturity_id"],
                subject_id=m["subject_id"],
                trade_date=date.fromisoformat(m["trade_date"]),
                overall=m["overall"],
                crowding=m["crowding"],
                volume=m["volume"],
                leader=m["leader"],
                emotion=m["emotion"],
                time=m["time"],
                quality_label=m["quality_label"],
                policy_version=m["policy_version"],
                estimated_days_to_threshold=m.get("estimated_days_to_threshold"),
                inflection_likelihood=m.get("inflection_likelihood", 0.0),
                evidence_refs=tuple(m.get("evidence_refs", [])),
            )
            for m in payload["maturity_estimates"]
        )

        ps_payload = payload["policy_snapshot"]
        policy_snapshot = PolicySnapshot(
            cycle_fsm=ps_payload["cycle_fsm"],
            divergence=ps_payload["divergence"],
            maturity=ps_payload["maturity"],
            compiler=ps_payload["compiler"],
            snapshot_at=datetime.fromisoformat(payload["created_at"]),
        )

        return DailyMarketState(
            state_id=payload["state_id"],
            trade_date=date.fromisoformat(payload["trade_date"]),
            version=payload["version"],
            parent_state=payload.get("parent_state"),
            created_at=datetime.fromisoformat(payload["created_at"]),
            policy_snapshot=policy_snapshot,
            subjects=subjects,
            cycle_nodes=cycle_nodes,
            divergence_qualities=dq_objects,
            maturity_estimates=nm_objects,
            content_hash=payload["content_hash"],
            evidence_refs=tuple(payload.get("evidence_refs", [])),
        )

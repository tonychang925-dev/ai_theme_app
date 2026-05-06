from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any


class ReplayInputHashBuilder:
    """Build stable replay input hashes for layer-level manifest reuse.

    v0.1 intentionally uses compact metadata rather than full row payloads.
    The interface is centralized so later versions can add max_updated_at or
    table-specific output hashes without changing ReplayRunner call sites.
    """

    @staticmethod
    def build(
        *,
        trade_date: date,
        layer: str,
        algorithm_version: str,
        input_row_count: int = 0,
        input_max_updated_at: str = "",
        extra: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "trade_date": trade_date.isoformat(),
            "layer": layer,
            "algorithm_version": algorithm_version,
            "input_row_count": int(input_row_count or 0),
            "input_max_updated_at": str(input_max_updated_at or ""),
            "extra": ReplayInputHashBuilder._stable(extra or {}),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def build_many(
        *,
        trade_date: date,
        algorithm_versions: dict[str, str],
        layer_inputs: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        out: dict[str, str] = {}
        for layer, version in algorithm_versions.items():
            inputs = dict(layer_inputs.get(layer) or {})
            out[layer] = ReplayInputHashBuilder.build(
                trade_date=trade_date,
                layer=layer,
                algorithm_version=version,
                input_row_count=int(inputs.get("input_row_count") or 0),
                input_max_updated_at=str(inputs.get("input_max_updated_at") or ""),
                extra=dict(inputs.get("extra") or {}),
            )
        return out

    @staticmethod
    def _stable(value: Any) -> Any:
        if is_dataclass(value):
            return ReplayInputHashBuilder._stable(asdict(value))
        if isinstance(value, dict):
            return {str(k): ReplayInputHashBuilder._stable(v) for k, v in sorted(value.items())}
        if isinstance(value, (list, tuple, set)):
            return [ReplayInputHashBuilder._stable(v) for v in value]
        if isinstance(value, date):
            return value.isoformat()
        return value

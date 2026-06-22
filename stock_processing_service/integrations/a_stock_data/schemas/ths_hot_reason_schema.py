from __future__ import annotations

from typing import Any


class ThsHotReasonSchemaError(ValueError):
    pass


REQUIRED_ITEM_FIELDS = {"code", "name", "reason", "date"}


def validate_ths_hot_reason_payload(payload: Any) -> list[str]:
    """Validate the shape used by THS hot reason payloads and return warnings."""

    if not isinstance(payload, dict):
        raise ThsHotReasonSchemaError("ths_hot_reason payload must be a JSON object")
    if int(payload.get("errocode", 0) or 0) != 0:
        raise ThsHotReasonSchemaError(str(payload.get("errormsg") or "ths_hot_reason returned non-zero errocode"))
    data = payload.get("data")
    if not isinstance(data, list):
        raise ThsHotReasonSchemaError("ths_hot_reason payload.data must be a list")

    warnings: list[str] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            warnings.append(f"item[{idx}] is not an object")
            continue
        missing = sorted(field for field in REQUIRED_ITEM_FIELDS if not item.get(field))
        if missing:
            warnings.append(f"item[{idx}] missing fields: {','.join(missing)}")
    return warnings


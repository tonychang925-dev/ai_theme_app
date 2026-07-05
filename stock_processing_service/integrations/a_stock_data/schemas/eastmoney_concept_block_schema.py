"""M4a: Eastmoney concept block schema validation."""

from __future__ import annotations

from typing import Any


class EastmoneySchemaError(ValueError):
    """Raised when Eastmoney response fails schema validation."""


REQUIRED_ROW_FIELDS = ["f12", "f14"]  # f12=code, f14=name


def validate_block_list_payload(payload: Any) -> list[str]:
    """Validate Eastmoney block list response. Returns warnings."""
    warnings: list[str] = []
    if not isinstance(payload, dict):
        raise EastmoneySchemaError("payload is not a dict")

    rc = payload.get("rc")
    if rc not in (None, 0):
        raise EastmoneySchemaError(f"eastmoney server rejected: rc={rc}")

    data = payload.get("data")
    if data is None:
        warnings.append("eastmoney block list: data is null")

    return warnings


def validate_block_stocks_payload(payload: Any) -> list[str]:
    """Validate Eastmoney block stocks response. Returns warnings."""
    warnings: list[str] = []
    if not isinstance(payload, dict):
        raise EastmoneySchemaError("payload is not a dict")

    rc = payload.get("rc")
    if rc not in (None, 0):
        raise EastmoneySchemaError(f"eastmoney server rejected: rc={rc}")

    data = payload.get("data")
    if data is None:
        warnings.append("eastmoney block stocks: data is null")

    return warnings

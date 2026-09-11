from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


class SerializationError(TypeError):
    pass


def to_mapping(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and value != value:
            raise SerializationError("non-finite floats cannot be serialized")
        return value
    if isinstance(value, Enum):
        return to_mapping(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SerializationError("datetimes must include a timezone")
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, (list, tuple)):
        return [to_mapping(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise SerializationError("mapping keys must be strings")
        return {key: to_mapping(item) for key, item in sorted(value.items())}
    if is_dataclass(value):
        result = {
            field.name: to_mapping(getattr(value, field.name))
            for field in fields(value)
        }
        return {"__type__": type(value).__name__, **result}
    raise SerializationError(f"unsupported contract value: {type(value).__name__}")


def serialize(value: Any) -> str:
    return json.dumps(
        to_mapping(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def deserialize_json(value: str) -> Any:
    return json.loads(value)

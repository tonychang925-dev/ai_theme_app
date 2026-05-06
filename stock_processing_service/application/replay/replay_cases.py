from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReplayCase:
    name: str
    trade_date: date
    stock_id: str
    expected: dict[str, Any] = field(default_factory=dict)


class ReplayCaseLoader:
    """Load fixed replay cases.

    The project intentionally avoids adding PyYAML here. The loader supports the
    constrained YAML shape used by `tests/replay/cases/weak_to_strong_cases.yaml`.
    """

    @classmethod
    def load(cls, path: str | Path) -> list[ReplayCase]:
        text = Path(path).read_text(encoding="utf-8")
        return cls.loads(text)

    @classmethod
    def loads(cls, text: str) -> list[ReplayCase]:
        rows = cls._parse_minimal_yaml_list(text)
        cases: list[ReplayCase] = []
        for row in rows:
            cases.append(
                ReplayCase(
                    name=str(row["name"]),
                    trade_date=date.fromisoformat(str(row["trade_date"])),
                    stock_id=str(row["stock_id"]),
                    expected=dict(row.get("expected") or {}),
                )
            )
        return cases

    @classmethod
    def _parse_minimal_yaml_list(cls, text: str) -> list[dict[str, Any]]:
        root: list[dict[str, Any]] = []
        stack: list[tuple[int, Any, dict[str, Any] | None, str | None]] = []

        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            line = raw.strip()
            if line.startswith("- "):
                while stack and stack[-1][0] >= indent:
                    stack.pop()
                item = {}
                if indent == 0:
                    root.append(item)
                    stack = [(indent, item, None, None)]
                else:
                    if not stack:
                        raise ValueError(f"Invalid replay case YAML list indentation: {raw}")
                    parent_container = stack[-1][1]
                    if isinstance(parent_container, dict) and not parent_container and stack[-1][2] is not None:
                        parent_dict = stack[-1][2]
                        parent_key = stack[-1][3]
                        parent_container = []
                        parent_dict[parent_key] = parent_container
                        stack[-1] = (stack[-1][0], parent_container, parent_dict, parent_key)
                    if not isinstance(parent_container, list):
                        raise ValueError(f"Invalid nested list parent in replay case YAML: {raw}")
                    parent_container.append(item)
                    stack.append((indent, item, None, None))
                rest = line[2:].strip()
                if rest:
                    key, value = cls._split_key_value(rest)
                    item[key] = cls._parse_scalar(value)
                continue

            key, value = cls._split_key_value(line)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if not stack:
                raise ValueError(f"Invalid replay case YAML indentation: {raw}")
            parent = stack[-1][1]
            if not isinstance(parent, dict):
                raise ValueError(f"Invalid replay case YAML parent: {raw}")
            if value == "":
                child: dict[str, Any] = {}
                parent[key] = child
                stack.append((indent, child, parent, key))
            else:
                parent[key] = cls._parse_scalar(value)

        return root

    @staticmethod
    def _split_key_value(line: str) -> tuple[str, str]:
        if ":" not in line:
            raise ValueError(f"Invalid replay case YAML line: {line}")
        key, value = line.split(":", 1)
        return key.strip(), value.strip()

    @classmethod
    def _parse_scalar(cls, raw: str) -> Any:
        value = raw.strip()
        if not value:
            return ""
        if value[0:1] in {"'", '"'} and value[-1:] == value[0]:
            return value[1:-1]
        if value in {"true", "True"}:
            return True
        if value in {"false", "False"}:
            return False
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [cls._parse_scalar(part.strip()) for part in inner.split(",")]
        try:
            return int(value)
        except ValueError:
            return value

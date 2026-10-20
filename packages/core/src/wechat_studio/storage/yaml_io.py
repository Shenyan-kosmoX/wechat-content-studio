"""UTF-8 YAML/JSON I/O with parse-before-replace safety."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from wechat_studio.errors import SerializationError

from .atomic import atomic_write_text


DocumentValidator = Callable[[Any], None]


def read_yaml(path: str | Path) -> Any:
    source = Path(path)
    try:
        return yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SerializationError(
            f"Unable to read YAML document: {source}",
            context={"path": str(source), "reason": str(exc)},
        ) from exc


def read_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SerializationError(
            f"Unable to read JSON document: {source}",
            context={"path": str(source), "reason": str(exc)},
        ) from exc


def write_yaml_atomic(
    path: str | Path,
    data: Any,
    *,
    validator: DocumentValidator | None = None,
) -> Path:
    try:
        serialized = yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    except yaml.YAMLError as exc:
        raise SerializationError(
            f"Unable to serialize YAML document: {path}",
            context={"path": str(path), "reason": str(exc)},
        ) from exc

    def validate_temporary(temporary: Path) -> None:
        loaded = yaml.safe_load(temporary.read_text(encoding="utf-8"))
        if validator is not None:
            validator(loaded)

    return atomic_write_text(path, serialized, validator=validate_temporary)


def write_json_atomic(
    path: str | Path,
    data: Any,
    *,
    validator: DocumentValidator | None = None,
) -> Path:
    try:
        serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    except (TypeError, ValueError) as exc:
        raise SerializationError(
            f"Unable to serialize JSON document: {path}",
            context={"path": str(path), "reason": str(exc)},
        ) from exc

    def validate_temporary(temporary: Path) -> None:
        loaded = json.loads(temporary.read_text(encoding="utf-8"))
        if validator is not None:
            validator(loaded)

    return atomic_write_text(path, serialized, validator=validate_temporary)

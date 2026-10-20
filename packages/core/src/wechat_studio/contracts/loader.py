"""Load schema files and YAML/JSON contract documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from wechat_studio.errors import (
    ContractLoadError,
    SchemaInvalidError,
    SchemaNotFoundError,
)
from wechat_studio.storage.paths import resolve_resource_root
from wechat_studio.storage.yaml_io import read_json, read_yaml


SCHEMA_NAMES = (
    "project",
    "material-manifest",
    "article-plan",
    "writing-profile",
    "layout-style",
    "style-pack",
    "preset",
    "delivery-report",
    "cli-result",
)


def normalize_schema_name(name: str) -> str:
    value = name.strip().lower()
    if value.endswith(".schema.json"):
        value = value[: -len(".schema.json")]
    if value not in SCHEMA_NAMES:
        raise SchemaNotFoundError(
            f"Unknown schema: {name}",
            context={"schema": name, "supported": list(SCHEMA_NAMES)},
        )
    return value


class SchemaLoader:
    """Load and cache checked Draft 2020-12 schemas."""

    def __init__(self, schema_dir: str | Path | None = None) -> None:
        if schema_dir is None:
            schema_dir = resolve_resource_root() / "schemas"
        self.schema_dir = Path(schema_dir).expanduser().resolve()
        self._cache: dict[str, dict[str, Any]] = {}

    def path_for(self, name: str) -> Path:
        normalized = normalize_schema_name(name)
        return self.schema_dir / f"{normalized}.schema.json"

    def load(self, name: str) -> dict[str, Any]:
        normalized = normalize_schema_name(name)
        if normalized in self._cache:
            return self._cache[normalized]

        path = self.path_for(normalized)
        if not path.is_file():
            raise SchemaNotFoundError(
                f"Schema file does not exist: {path}",
                context={"schema": normalized, "path": str(path)},
            )
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SchemaInvalidError(
                f"Schema file cannot be parsed: {path}",
                context={"schema": normalized, "path": str(path), "reason": str(exc)},
            ) from exc
        if not isinstance(schema, dict):
            raise SchemaInvalidError(
                f"Schema root must be an object: {path}",
                context={"schema": normalized, "path": str(path)},
            )
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise SchemaInvalidError(
                f"Invalid JSON Schema: {path}",
                context={"schema": normalized, "path": str(path), "reason": exc.message},
            ) from exc
        self._cache[normalized] = schema
        return schema

    def load_all(self) -> dict[str, dict[str, Any]]:
        return {name: self.load(name) for name in SCHEMA_NAMES}


def load_contract_document(path: str | Path) -> Any:
    """Load a YAML or JSON document based on its file extension."""

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return read_yaml(source)
    if suffix == ".json":
        return read_json(source)
    raise ContractLoadError(
        f"Unsupported contract document type: {source}",
        context={"path": str(source), "supported_extensions": [".yaml", ".yml", ".json"]},
    )

"""JSON Schema and cross-field validation for persisted contracts."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from wechat_studio.errors import UnsupportedSchemaVersionError
from wechat_studio.version import SCHEMA_VERSION

from .loader import SchemaLoader, normalize_schema_name
from .models import ValidationIssue, ValidationResult


FORMAT_CHECKER = FormatChecker()
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def is_safe_relative_path(value: object) -> bool:
    """Return true for portable, traversal-free POSIX-style relative paths."""

    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if "\\" in value or "\x00" in value or "//" in value or ":" in value:
        return False
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


@FORMAT_CHECKER.checks("safe-relative-path")
def _check_safe_relative_path(value: object) -> bool:
    return is_safe_relative_path(value)


@FORMAT_CHECKER.checks("semver")
def _check_semver(value: object) -> bool:
    return isinstance(value, str) and bool(SEMVER_RE.fullmatch(value))


def _json_path(parts: Sequence[object]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result


def _issue(path: str, message: str, rule: str) -> ValidationIssue:
    return ValidationIssue(path=path, message=message, rule=rule)


def _duplicate_values(values: Sequence[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _validate_material_manifest(data: Mapping[str, Any]) -> list[ValidationIssue]:
    items = data.get("items")
    if not isinstance(items, list):
        return []
    ids = [item.get("id") for item in items if isinstance(item, Mapping) and isinstance(item.get("id"), str)]
    paths = [item.get("path") for item in items if isinstance(item, Mapping) and isinstance(item.get("path"), str)]
    issues = [
        _issue("$.items", f"Duplicate material id: {value}", "unique-material-id")
        for value in sorted(_duplicate_values(ids))
    ]
    issues.extend(
        _issue("$.items", f"Multiple materials point to the same path: {value}", "unique-material-path")
        for value in sorted(_duplicate_values(paths))
    )
    return issues


def _validate_article_plan(data: Mapping[str, Any]) -> list[ValidationIssue]:
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        return []
    ids = [block.get("id") for block in blocks if isinstance(block, Mapping) and isinstance(block.get("id"), str)]
    id_set = set(ids)
    issues = [
        _issue("$.blocks", f"Duplicate article block id: {value}", "unique-block-id")
        for value in sorted(_duplicate_values(ids))
    ]
    for index, block in enumerate(blocks):
        if not isinstance(block, Mapping):
            continue
        block_id = block.get("id")
        placement = block.get("placement")
        if not isinstance(placement, Mapping):
            continue
        for relation in ("before", "after", "inside"):
            target = placement.get(relation)
            if not isinstance(target, str):
                continue
            path = f"$.blocks[{index}].placement.{relation}"
            if target not in id_set:
                issues.append(_issue(path, f"Anchor target does not exist: {target}", "anchor-target-exists"))
            elif target == block_id:
                issues.append(_issue(path, "A block cannot anchor to itself.", "anchor-not-self"))
    return issues


def _validate_writing_profile(data: Mapping[str, Any]) -> list[ValidationIssue]:
    paragraph = data.get("paragraph_length")
    if not isinstance(paragraph, Mapping):
        return []
    minimum = paragraph.get("minimum_characters")
    maximum = paragraph.get("maximum_characters")
    if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
        return [
            _issue(
                "$.paragraph_length",
                "minimum_characters cannot exceed maximum_characters.",
                "ordered-range",
            )
        ]
    return []


def _validate_delivery_report(data: Mapping[str, Any]) -> list[ValidationIssue]:
    status = data.get("status")
    validation = data.get("validation")
    if not isinstance(validation, Mapping):
        return []
    confirmed = validation.get("confirmed_by_user")
    wechat_status = validation.get("wechat_status")
    issues: list[ValidationIssue] = []
    if status == "WECHAT_VALIDATED" and not (confirmed is True and wechat_status == "VALIDATED"):
        issues.append(
            _issue(
                "$.validation",
                "WECHAT_VALIDATED requires explicit user confirmation and wechat_status=VALIDATED.",
                "user-validation-boundary",
            )
        )
    if confirmed is False and wechat_status == "VALIDATED":
        issues.append(
            _issue(
                "$.validation.confirmed_by_user",
                "wechat_status=VALIDATED requires confirmed_by_user=true.",
                "user-validation-boundary",
            )
        )
    return issues


SEMANTIC_VALIDATORS: dict[str, Callable[[Mapping[str, Any]], list[ValidationIssue]]] = {
    "material-manifest": _validate_material_manifest,
    "article-plan": _validate_article_plan,
    "writing-profile": _validate_writing_profile,
    "delivery-report": _validate_delivery_report,
}

SCHEMA_VERSION_FIELDS = {
    "project": "project_schema_version",
    "material-manifest": "material_manifest_schema_version",
    "article-plan": "article_plan_schema_version",
    "writing-profile": "writing_profile_schema_version",
    "layout-style": "layout_style_schema_version",
    "style-pack": "style_pack_schema_version",
    "preset": "preset_schema_version",
    "delivery-report": "delivery_report_schema_version",
    "cli-result": "cli_result_schema_version",
}


class ContractValidator:
    """Validate documents with JSON Schema plus deterministic semantic checks."""

    def __init__(self, loader: SchemaLoader | None = None) -> None:
        self.loader = loader or SchemaLoader()

    def validate(self, data: Any, schema_name: str) -> ValidationResult:
        normalized = normalize_schema_name(schema_name)
        schema = self.loader.load(normalized)
        validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
        issues = [
            ValidationIssue(
                path=_json_path(tuple(error.absolute_path)),
                message=error.message,
                rule=str(error.validator),
            )
            for error in sorted(
                validator.iter_errors(data),
                key=lambda item: (_json_path(tuple(item.absolute_path)), item.message),
            )
        ]
        if not issues and isinstance(data, Mapping):
            semantic_validator = SEMANTIC_VALIDATORS.get(normalized)
            if semantic_validator is not None:
                issues.extend(semantic_validator(data))
        return ValidationResult(schema_name=normalized, issues=tuple(issues))

    def validate_or_raise(self, data: Any, schema_name: str) -> Any:
        normalized = normalize_schema_name(schema_name)
        if isinstance(data, Mapping):
            version_field = SCHEMA_VERSION_FIELDS[normalized]
            actual_version = data.get(version_field)
            if actual_version is not None and actual_version != SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    f"Unsupported {normalized} schema version: {actual_version}",
                    context={
                        "schema": normalized,
                        "version_field": version_field,
                        "actual": actual_version,
                        "supported": [SCHEMA_VERSION],
                    },
                )
        result = self.validate(data, normalized)
        result.raise_for_error()
        return data

    def validate_file(self, path: str, schema_name: str) -> ValidationResult:
        from .loader import load_contract_document

        return self.validate(load_contract_document(path), schema_name)

"""Validated article-plan persistence with lock preservation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from wechat_studio.contracts import ContractValidator
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic

from .anchors import assert_locked_constraints_preserved, validate_plan_references


def load_article_plan(path: str | Path, *, validator: ContractValidator | None = None) -> dict[str, Any]:
    document = read_yaml(path)
    checked = validator or ContractValidator()
    checked.validate_or_raise(document, "article-plan")
    return document


def save_article_plan(
    path: str | Path,
    plan: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    validator: ContractValidator | None = None,
    preserve_locked: bool = True,
) -> Path:
    destination = Path(path)
    checked = validator or ContractValidator()
    checked.validate_or_raise(plan, "article-plan")
    validate_plan_references(plan, manifest)
    if preserve_locked and destination.exists():
        previous = load_article_plan(destination, validator=checked)
        assert_locked_constraints_preserved(previous, plan)

    def validate_written(document: Any) -> None:
        checked.validate_or_raise(document, "article-plan")
        validate_plan_references(document, manifest)

    return write_yaml_atomic(destination, dict(plan), validator=validate_written)

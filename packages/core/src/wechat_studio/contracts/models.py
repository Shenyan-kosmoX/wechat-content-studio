"""Small immutable models used by contract validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wechat_studio.errors import ContractValidationError


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    path: str
    message: str
    rule: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message, "rule": self.rule}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    schema_name: str
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "schema": self.schema_name,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def raise_for_error(self) -> None:
        if self.valid:
            return
        raise ContractValidationError(
            f"Document does not satisfy {self.schema_name}.",
            context={"schema": self.schema_name, "issues": self.to_dict()["issues"]},
        )

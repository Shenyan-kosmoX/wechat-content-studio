"""Stable error types and codes for Core and CLI adapters."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping


class ErrorCode(StrEnum):
    CONTRACT_LOAD = "WCS-CONTRACT-001"
    CONTRACT_VALIDATION = "WCS-CONTRACT-002"
    SCHEMA_NOT_FOUND = "WCS-CONTRACT-003"
    SCHEMA_INVALID = "WCS-CONTRACT-004"
    UNSUPPORTED_SCHEMA_VERSION = "WCS-CONTRACT-005"
    PATH_UNSAFE = "WCS-PATH-001"
    PATH_RESOLUTION = "WCS-PATH-002"
    ATOMIC_WRITE = "WCS-STORAGE-001"
    SERIALIZATION = "WCS-STORAGE-002"
    LOCK_BUSY = "WCS-STORAGE-003"
    PROJECT_EXISTS = "WCS-PROJECT-001"
    PROJECT_NOT_FOUND = "WCS-PROJECT-002"
    PROJECT_INVALID = "WCS-PROJECT-003"
    STATUS_TRANSITION = "WCS-PROJECT-004"
    MATERIAL_NOT_FOUND = "WCS-MATERIAL-001"
    MATERIAL_CONFLICT = "WCS-MATERIAL-002"
    ANCHOR_CONFLICT = "WCS-ANCHOR-001"
    LOCK_CONFLICT = "WCS-ANCHOR-002"
    RENDER_FAILED = "WCS-RENDER-001"
    DELIVERY_VALIDATION = "WCS-RENDER-002"
    STYLE_NOT_FOUND = "WCS-STYLE-001"
    STYLE_CONFLICT = "WCS-STYLE-002"
    STYLE_INVALID = "WCS-STYLE-003"
    STYLE_IMMUTABLE = "WCS-STYLE-004"
    STYLE_PROMOTION = "WCS-STYLE-005"
    PRESET_INVALID = "WCS-PRESET-001"
    SAMPLE_NOT_FOUND = "WCS-SAMPLE-001"
    SAMPLE_INVALID = "WCS-SAMPLE-002"
    SAMPLE_CONFLICT = "WCS-SAMPLE-003"
    DISTILLATION_INVALID = "WCS-DISTILL-001"
    DISTILLATION_INSUFFICIENT = "WCS-DISTILL-002"
    MIGRATION_FAILED = "WCS-MIGRATE-001"


class WeChatStudioError(Exception):
    """Base exception carrying a stable machine-readable error code."""

    default_code = ErrorCode.CONTRACT_LOAD

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code or self.default_code)
        self.message = message
        self.context = dict(context or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }


class ContractLoadError(WeChatStudioError):
    default_code = ErrorCode.CONTRACT_LOAD


class ContractValidationError(WeChatStudioError):
    default_code = ErrorCode.CONTRACT_VALIDATION


class SchemaNotFoundError(WeChatStudioError):
    default_code = ErrorCode.SCHEMA_NOT_FOUND


class SchemaInvalidError(WeChatStudioError):
    default_code = ErrorCode.SCHEMA_INVALID


class UnsupportedSchemaVersionError(WeChatStudioError):
    default_code = ErrorCode.UNSUPPORTED_SCHEMA_VERSION


class UnsafePathError(WeChatStudioError):
    default_code = ErrorCode.PATH_UNSAFE


class PathResolutionError(WeChatStudioError):
    default_code = ErrorCode.PATH_RESOLUTION


class AtomicWriteError(WeChatStudioError):
    default_code = ErrorCode.ATOMIC_WRITE


class SerializationError(WeChatStudioError):
    default_code = ErrorCode.SERIALIZATION


class LockBusyError(WeChatStudioError):
    default_code = ErrorCode.LOCK_BUSY


class ProjectExistsError(WeChatStudioError):
    default_code = ErrorCode.PROJECT_EXISTS


class ProjectNotFoundError(WeChatStudioError):
    default_code = ErrorCode.PROJECT_NOT_FOUND


class ProjectInvalidError(WeChatStudioError):
    default_code = ErrorCode.PROJECT_INVALID


class StatusTransitionError(WeChatStudioError):
    default_code = ErrorCode.STATUS_TRANSITION


class MaterialNotFoundError(WeChatStudioError):
    default_code = ErrorCode.MATERIAL_NOT_FOUND


class MaterialConflictError(WeChatStudioError):
    default_code = ErrorCode.MATERIAL_CONFLICT


class AnchorConflictError(WeChatStudioError):
    default_code = ErrorCode.ANCHOR_CONFLICT


class LockConflictError(WeChatStudioError):
    default_code = ErrorCode.LOCK_CONFLICT


class RenderError(WeChatStudioError):
    default_code = ErrorCode.RENDER_FAILED


class DeliveryValidationError(WeChatStudioError):
    default_code = ErrorCode.DELIVERY_VALIDATION


class StyleNotFoundError(WeChatStudioError):
    default_code = ErrorCode.STYLE_NOT_FOUND


class StyleConflictError(WeChatStudioError):
    default_code = ErrorCode.STYLE_CONFLICT


class StyleInvalidError(WeChatStudioError):
    default_code = ErrorCode.STYLE_INVALID


class StyleImmutableError(WeChatStudioError):
    default_code = ErrorCode.STYLE_IMMUTABLE


class StylePromotionError(WeChatStudioError):
    default_code = ErrorCode.STYLE_PROMOTION


class PresetInvalidError(WeChatStudioError):
    default_code = ErrorCode.PRESET_INVALID


class SampleNotFoundError(WeChatStudioError):
    default_code = ErrorCode.SAMPLE_NOT_FOUND


class SampleInvalidError(WeChatStudioError):
    default_code = ErrorCode.SAMPLE_INVALID


class SampleConflictError(WeChatStudioError):
    default_code = ErrorCode.SAMPLE_CONFLICT


class DistillationInvalidError(WeChatStudioError):
    default_code = ErrorCode.DISTILLATION_INVALID


class DistillationInsufficientEvidenceError(WeChatStudioError):
    default_code = ErrorCode.DISTILLATION_INSUFFICIENT


class MigrationError(WeChatStudioError):
    default_code = ErrorCode.MIGRATION_FAILED

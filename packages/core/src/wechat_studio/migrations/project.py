"""Safe project-schema migration framework."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from wechat_studio.errors import (
    MigrationError,
    ProjectNotFoundError,
    UnsupportedSchemaVersionError,
)
from wechat_studio.projects import load_article_project
from wechat_studio.storage.yaml_io import read_yaml
from wechat_studio.version import SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ProjectMigrationResult:
    project_id: str
    source_version: str
    target_version: str
    changed: bool
    dry_run: bool
    backup_path: Path | None
    applied_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "source_version": self.source_version,
            "target_version": self.target_version,
            "changed": self.changed,
            "dry_run": self.dry_run,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "applied_steps": list(self.applied_steps),
        }


def _backup_directory(project_root: Path, backup_root: str | Path | None) -> Path:
    moment = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    parent = Path(backup_root).resolve() if backup_root else project_root.parent / "backups"
    return parent / f"{project_root.name}-{moment}"


def migrate_project(
    project: str | Path,
    *,
    target_version: str = SCHEMA_VERSION,
    backup_root: str | Path | None = None,
    dry_run: bool = False,
) -> ProjectMigrationResult:
    root = Path(project)
    if root.is_file() and root.name == "project.yaml":
        root = root.parent
    root = root.resolve()
    project_file = root / "project.yaml"
    if not project_file.is_file():
        raise ProjectNotFoundError(
            f"Article project not found: {root}", context={"path": str(root)}
        )
    if target_version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Unsupported migration target: {target_version}",
            context={"actual": target_version, "supported": [SCHEMA_VERSION]},
        )

    document = read_yaml(project_file)
    if not isinstance(document, dict):
        raise MigrationError(
            "project.yaml must contain an object.", context={"path": str(project_file)}
        )
    source_version = str(document.get("project_schema_version", ""))
    project_id = str(document.get("project_id", root.name))
    if source_version == SCHEMA_VERSION:
        loaded = load_article_project(root)
        return ProjectMigrationResult(
            project_id=loaded.project_id,
            source_version=source_version,
            target_version=target_version,
            changed=False,
            dry_run=dry_run,
            backup_path=None,
            applied_steps=(),
        )

    # No pre-v1 project contract was released. Unknown versions must remain
    # untouched until an explicit, tested migration step is registered.
    raise UnsupportedSchemaVersionError(
        f"No migration path exists from project schema {source_version or '<missing>'}.",
        context={
            "project_id": project_id,
            "source_version": source_version or None,
            "target_version": target_version,
            "backup_destination_if_supported": str(_backup_directory(root, backup_root)),
            "changed": False,
        },
    )

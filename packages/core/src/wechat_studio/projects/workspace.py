"""Initialize and query the user-owned WeChat Content Studio workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from wechat_studio.composition.locks import exclusive_lock
from wechat_studio.storage.paths import WorkspacePaths, resolve_workspace_paths
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(slots=True)
class WorkspaceManager:
    paths: WorkspacePaths

    @classmethod
    def resolve(
        cls,
        user_root: str | Path | None = None,
        *,
        state_root: str | Path | None = None,
        resources_root: str | Path | None = None,
    ) -> "WorkspaceManager":
        return cls(
            resolve_workspace_paths(
                user_root,
                state_root=state_root,
                resources_root=resources_root,
            )
        )

    def initialize(self) -> "WorkspaceManager":
        self.paths.initialize()
        if not self.paths.settings.exists():
            write_yaml_atomic(
                self.paths.settings,
                {
                    "settings_schema_version": "1.0",
                    "workspace_name": "WeChat Content Studio",
                    "default_layout_style": {
                        "id": "basic-editorial",
                        "version": "1.0.0",
                        "layer": "builtin",
                    },
                },
            )
        if not self.paths.registry.exists():
            write_yaml_atomic(
                self.paths.registry,
                {
                    "registry_schema_version": "1.0",
                    "updated_at": _now(),
                    "projects": [],
                },
            )
        return self

    def read_registry(self) -> dict[str, Any]:
        self.initialize()
        document = read_yaml(self.paths.registry)
        if not isinstance(document, dict) or not isinstance(document.get("projects"), list):
            raise ValueError(f"Invalid workspace registry: {self.paths.registry}")
        return document

    def register_project(self, project: dict[str, Any], project_root: Path) -> None:
        self.initialize()
        lock_path = self.paths.locks / "registry.lock"
        with exclusive_lock(lock_path, timeout_seconds=2.0):
            registry = self.read_registry()
            relative_path = project_root.resolve().relative_to(self.paths.user_root.resolve()).as_posix()
            record = {
                "project_id": project["project_id"],
                "name": project["name"],
                "path": relative_path,
                "status": project["status"],
                "updated_at": project["updated_at"],
            }
            projects = [
                item
                for item in registry["projects"]
                if item.get("project_id") != project["project_id"]
            ]
            projects.append(record)
            projects.sort(key=lambda item: item["project_id"])
            registry["projects"] = projects
            registry["updated_at"] = _now()
            write_yaml_atomic(self.paths.registry, registry)

    def list_projects(self) -> list[dict[str, Any]]:
        registry = self.read_registry()
        return list(registry["projects"])

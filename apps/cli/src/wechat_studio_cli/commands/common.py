"""Shared path, document, and workspace helpers for commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wechat_studio.projects import ArticleProject, WorkspaceManager, load_article_project
from wechat_studio.storage.yaml_io import read_json, read_yaml


def workspace_manager(args: Any, *, initialize: bool = True) -> WorkspaceManager:
    manager = WorkspaceManager.resolve(
        args.workspace,
        state_root=args.state_root,
        resources_root=args.resources_root,
    )
    return manager.initialize() if initialize else manager


def project_path(value: str, manager: WorkspaceManager) -> Path:
    supplied = Path(value).expanduser()
    if supplied.exists() or supplied.is_absolute() or len(supplied.parts) > 1:
        return supplied.resolve()
    return (manager.paths.articles / value).resolve()


def load_project(value: str, manager: WorkspaceManager) -> ArticleProject:
    return load_article_project(project_path(value, manager), workspace_paths=manager.paths)


def load_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    value = read_json(source) if source.suffix.lower() == ".json" else read_yaml(source)
    if not isinstance(value, dict):
        from wechat_studio.errors import ContractLoadError

        raise ContractLoadError(
            f"Expected an object document: {source}", context={"path": str(source)}
        )
    return value

"""Centralized, cross-platform workspace and resource path resolution."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_documents_dir, user_state_dir

from wechat_studio.errors import PathResolutionError, UnsafePathError


APP_DISPLAY_NAME = "WeChat Content Studio"
APP_DIR_NAME = "WeChatContentStudio"
WORKSPACE_ENV = "WECHAT_STUDIO_HOME"


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def resolve_user_data_root(
    explicit: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    documents_dir: str | Path | None = None,
) -> Path:
    """Resolve explicit path, then environment override, then Documents default."""

    if explicit is not None:
        return _absolute(explicit)
    environment = os.environ if environ is None else environ
    configured = environment.get(WORKSPACE_ENV)
    if configured:
        return _absolute(configured)
    documents = _absolute(documents_dir or user_documents_dir())
    return documents / APP_DISPLAY_NAME


def resolve_state_root(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return _absolute(explicit)
    return _absolute(user_state_dir(APP_DIR_NAME, appauthor=False, roaming=False))


def resolve_resource_root(explicit: str | Path | None = None) -> Path:
    """Resolve bundled resources in source and PyInstaller-style runtimes."""

    if explicit is not None:
        candidate = _absolute(explicit)
        if (candidate / "schemas").is_dir():
            return candidate
        raise PathResolutionError(
            f"Resource directory has no schemas folder: {candidate}",
            context={"path": str(candidate)},
        )

    candidates: list[Path] = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "resources")
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "resources")
    module_path = Path(__file__).resolve()
    candidates.extend(parent / "resources" for parent in module_path.parents)

    for candidate in candidates:
        if (candidate / "schemas").is_dir():
            return candidate.resolve()
    raise PathResolutionError(
        "Unable to locate WeChat Content Studio resources.",
        context={"candidates": [str(path) for path in candidates]},
    )


def safe_join(root: str | Path, relative_path: str) -> Path:
    from wechat_studio.contracts.validator import is_safe_relative_path

    if not is_safe_relative_path(relative_path):
        raise UnsafePathError(
            f"Unsafe relative path: {relative_path}",
            context={"path": relative_path},
        )
    base = _absolute(root)
    candidate = (base / Path(*relative_path.split("/"))).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise UnsafePathError(
            f"Path escapes its root: {relative_path}",
            context={"root": str(base), "path": relative_path},
        ) from exc
    return candidate


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    user_root: Path
    state_root: Path
    resources_root: Path

    @property
    def settings(self) -> Path:
        return self.user_root / "settings.yaml"

    @property
    def registry(self) -> Path:
        return self.user_root / "registry.yaml"

    @property
    def private_styles(self) -> Path:
        return self.user_root / "styles" / "private"

    @property
    def imported_styles(self) -> Path:
        return self.user_root / "styles" / "imports"

    @property
    def writing_profiles(self) -> Path:
        return self.user_root / "writing-profiles"

    @property
    def imported_writing_profiles(self) -> Path:
        return self.user_root / "writing-profiles" / "imports"

    @property
    def private_writing_profiles(self) -> Path:
        return self.writing_profiles

    @property
    def presets(self) -> Path:
        return self.user_root / "presets"

    @property
    def articles(self) -> Path:
        return self.user_root / "articles"

    @property
    def cache(self) -> Path:
        return self.state_root / "cache"

    @property
    def logs(self) -> Path:
        return self.state_root / "logs"

    @property
    def locks(self) -> Path:
        return self.state_root / "locks"

    @property
    def temp(self) -> Path:
        return self.state_root / "temp"

    def initialize(self) -> "WorkspacePaths":
        directories = (
            self.user_root,
            self.private_styles,
            self.imported_styles,
            self.writing_profiles,
            self.imported_writing_profiles,
            self.private_writing_profiles,
            self.presets,
            self.articles,
            self.state_root,
            self.cache,
            self.logs,
            self.locks,
            self.temp,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        return self


def resolve_workspace_paths(
    explicit_user_root: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    documents_dir: str | Path | None = None,
    state_root: str | Path | None = None,
    resources_root: str | Path | None = None,
) -> WorkspacePaths:
    return WorkspacePaths(
        user_root=resolve_user_data_root(
            explicit_user_root,
            environ=environ,
            documents_dir=documents_dir,
        ),
        state_root=resolve_state_root(state_root),
        resources_root=resolve_resource_root(resources_root),
    )

"""Create, load, inspect, and safely mutate article projects."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from wechat_studio.composition.ids import PROJECT_ID_RE, make_project_id
from wechat_studio.composition.locks import exclusive_lock
from wechat_studio.composition.plan import load_article_plan, save_article_plan
from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import ProjectExistsError, ProjectInvalidError, ProjectNotFoundError
from wechat_studio.storage.atomic import atomic_write_text
from wechat_studio.storage.paths import WorkspacePaths
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic
from wechat_studio.version import CORE_VERSION

from .materials import MaterialStore
from .status import transition_status
from .workspace import WorkspaceManager


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


DEFAULT_LAYOUT_STYLE = {
    "id": "basic-editorial",
    "version": "1.0.0",
    "layer": "builtin",
}


@dataclass(slots=True)
class ArticleProject:
    root: Path
    document: dict[str, Any]
    workspace_paths: WorkspacePaths | None = None

    @property
    def project_id(self) -> str:
        return self.document["project_id"]

    @property
    def project_file(self) -> Path:
        return self.root / "project.yaml"

    @property
    def manifest_file(self) -> Path:
        return self.root / self.document["paths"]["material_manifest"]

    @property
    def plan_file(self) -> Path:
        return self.root / self.document["paths"]["article_plan"]

    @property
    def article_file(self) -> Path:
        return self.root / self.document["paths"]["article"]

    @property
    def brief_file(self) -> Path:
        return self.root / "brief.md"

    @property
    def build_directory(self) -> Path:
        return self.root / self.document["paths"]["build_directory"]

    @property
    def lock_file(self) -> Path:
        if self.workspace_paths is not None:
            return self.workspace_paths.locks / f"project-{self.project_id}.lock"
        return self.root / ".project.lock"

    @property
    def material_store(self) -> MaterialStore:
        material_lock = (
            self.workspace_paths.locks / f"materials-{self.project_id}.lock"
            if self.workspace_paths is not None
            else self.root / ".materials.lock"
        )
        return MaterialStore(
            self.root,
            project_id=self.project_id,
            lock_path=material_lock,
        )

    def reload(self) -> "ArticleProject":
        loaded = load_article_project(self.root, workspace_paths=self.workspace_paths)
        self.document = loaded.document
        return self

    def load_manifest(self) -> dict[str, Any]:
        return self.material_store.load()

    def load_plan(self) -> dict[str, Any]:
        return load_article_plan(self.plan_file)

    def save_plan(self, plan: Mapping[str, Any], *, preserve_locked: bool = True) -> Path:
        with exclusive_lock(self.lock_file, timeout_seconds=2.0):
            return save_article_plan(
                self.plan_file,
                plan,
                manifest=self.load_manifest(),
                preserve_locked=preserve_locked,
            )

    def write_article(self, markdown: str) -> Path:
        with exclusive_lock(self.lock_file, timeout_seconds=2.0):
            return atomic_write_text(self.article_file, markdown)

    def write_brief(self, markdown: str) -> Path:
        with exclusive_lock(self.lock_file, timeout_seconds=2.0):
            return atomic_write_text(self.brief_file, markdown)

    def set_status(self, target: str, *, user_confirmed: bool = False) -> str:
        with exclusive_lock(self.lock_file, timeout_seconds=2.0):
            current = read_yaml(self.project_file)
            checked = ContractValidator()
            checked.validate_or_raise(current, "project")
            current["status"] = transition_status(
                current["status"], target, user_confirmed=user_confirmed
            )
            current["updated_at"] = _now()
            write_yaml_atomic(
                self.project_file,
                current,
                validator=lambda value: checked.validate_or_raise(value, "project"),
            )
            self.document = current
            if self.workspace_paths is not None:
                WorkspaceManager(self.workspace_paths).register_project(current, self.root)
            return target

    def record_build(self, *, build_id: str, status: str) -> None:
        with exclusive_lock(self.lock_file, timeout_seconds=2.0):
            original_text = self.project_file.read_text(encoding="utf-8")
            current = read_yaml(self.project_file)
            checked = ContractValidator()
            checked.validate_or_raise(current, "project")
            current["generation"]["sequence"] += 1
            current["generation"]["last_build_id"] = build_id
            current["status"] = status
            current["updated_at"] = _now()
            try:
                write_yaml_atomic(
                    self.project_file,
                    current,
                    validator=lambda value: checked.validate_or_raise(value, "project"),
                )
                if self.workspace_paths is not None:
                    WorkspaceManager(self.workspace_paths).register_project(current, self.root)
            except Exception:
                atomic_write_text(self.project_file, original_text)
                raise
            self.document = current

    def inspect(self) -> dict[str, Any]:
        manifest = self.load_manifest()
        plan = self.load_plan()
        material_status = self.material_store.verify()
        return {
            "project_id": self.project_id,
            "name": self.document["name"],
            "mode": self.document["mode"],
            "status": self.document["status"],
            "generation": dict(self.document["generation"]),
            "materials": {
                "count": len(manifest["items"]),
                "by_kind": {
                    kind: sum(1 for item in manifest["items"] if item["kind"] == kind)
                    for kind in ("text", "reference", "image")
                },
                "integrity": material_status,
            },
            "plan": {
                "status": plan["status"],
                "block_count": len(plan["blocks"]),
                "locked_blocks": [block["id"] for block in plan["blocks"] if block["locked"]],
            },
            "paths": {
                "root": str(self.root),
                "article": str(self.article_file),
                "preview": str(self.build_directory / "wechat_preview.html"),
            },
        }


def create_article_project(
    workspace: WorkspaceManager | WorkspacePaths,
    *,
    name: str,
    mode: str,
    project_id: str | None = None,
    brief: str = "",
    layout_style: Mapping[str, Any] | None = None,
    writing_profile: Mapping[str, Any] | None = None,
    preset: Mapping[str, Any] | None = None,
) -> ArticleProject:
    manager = workspace if isinstance(workspace, WorkspaceManager) else WorkspaceManager(workspace)
    manager.initialize()
    identifier = project_id or make_project_id(name)
    if not PROJECT_ID_RE.fullmatch(identifier):
        raise ProjectInvalidError(
            f"Invalid project id: {identifier}",
            context={"project_id": identifier},
        )
    destination = manager.paths.articles / identifier
    if destination.exists():
        raise ProjectExistsError(
            f"Article project already exists: {identifier}",
            context={"project_id": identifier, "path": str(destination)},
        )

    created_at = _now()
    project = {
        "project_schema_version": "1.0",
        "project_id": identifier,
        "name": name,
        "mode": mode,
        "status": "DRAFTING",
        "created_at": created_at,
        "updated_at": created_at,
        "generation": {
            "sequence": 0,
            "core_version": CORE_VERSION,
            "last_build_id": None,
        },
        "style": {
            "layout_style": dict(layout_style or DEFAULT_LAYOUT_STYLE),
            "writing_profile": dict(writing_profile) if writing_profile else None,
            "preset": dict(preset) if preset else None,
        },
        "paths": {
            "material_manifest": "materials/manifest.yaml",
            "article_plan": "article-plan.yaml",
            "article": "article.md",
            "build_directory": "build",
        },
    }
    manifest = {
        "material_manifest_schema_version": "1.0",
        "project_id": identifier,
        "generated_at": created_at,
        "items": [],
    }
    plan = {
        "article_plan_schema_version": "1.0",
        "project_id": identifier,
        "status": "DRAFT",
        "blocks": [],
    }
    validator = ContractValidator()
    validator.validate_or_raise(project, "project")
    validator.validate_or_raise(manifest, "material-manifest")
    validator.validate_or_raise(plan, "article-plan")

    staging = Path(
        tempfile.mkdtemp(prefix=f".{identifier}.", suffix=".tmp", dir=manager.paths.articles)
    )
    try:
        for relative in (
            "materials/source-text",
            "materials/images",
            "styles/local",
            "build",
        ):
            (staging / relative).mkdir(parents=True, exist_ok=True)
        write_yaml_atomic(staging / "project.yaml", project)
        atomic_write_text(staging / "brief.md", brief)
        write_yaml_atomic(
            staging / "materials" / "manifest.yaml",
            manifest,
            validator=lambda value: validator.validate_or_raise(value, "material-manifest"),
        )
        write_yaml_atomic(staging / "sources.yaml", {"sources_schema_version": "1.0", "sources": []})
        write_yaml_atomic(
            staging / "article-plan.yaml",
            plan,
            validator=lambda value: validator.validate_or_raise(value, "article-plan"),
        )
        atomic_write_text(staging / "article.md", "")
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    manager.register_project(project, destination)
    return ArticleProject(destination, project, manager.paths)


def load_article_project(
    path: str | Path,
    *,
    workspace_paths: WorkspacePaths | None = None,
) -> ArticleProject:
    root = Path(path)
    if root.is_file() and root.name == "project.yaml":
        root = root.parent
    root = root.resolve()
    project_file = root / "project.yaml"
    if not project_file.is_file():
        raise ProjectNotFoundError(
            f"Article project not found: {root}",
            context={"path": str(root)},
        )
    document = read_yaml(project_file)
    validator = ContractValidator()
    validator.validate_or_raise(document, "project")
    required = (
        root / document["paths"]["material_manifest"],
        root / document["paths"]["article_plan"],
        root / document["paths"]["article"],
    )
    missing = [str(item) for item in required if not item.exists()]
    if missing:
        raise ProjectInvalidError(
            f"Article project is missing required files: {root}",
            context={"path": str(root), "missing": missing},
        )
    loaded = ArticleProject(root, document, workspace_paths)
    loaded.load_manifest()
    loaded.load_plan()
    return loaded

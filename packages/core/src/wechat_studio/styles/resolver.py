"""Resolve exact or latest active Style Pack versions with fixed precedence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wechat_studio.errors import StyleNotFoundError
from wechat_studio.projects.project import ArticleProject
from wechat_studio.storage.paths import WorkspacePaths

from .pack import StylePack
from .registry import LAYER_PRECEDENCE, StyleRegistry
from .versions import parse_semver


@dataclass(frozen=True, slots=True)
class ResolvedStyle:
    pack: StylePack

    @property
    def reference(self) -> dict[str, str]:
        return self.pack.reference

    @property
    def components_directory(self) -> Path:
        return self.pack.components_directory

    @property
    def layout_style(self) -> dict[str, Any]:
        return self.pack.layout_style


class StyleResolver:
    def __init__(self, paths: WorkspacePaths, *, project_root: str | Path | None = None) -> None:
        self.paths = paths
        self.project_root = Path(project_root).resolve() if project_root else None

    def resolve(
        self,
        reference: Mapping[str, object] | str,
        *,
        version: str | None = None,
        layer: str | None = None,
        include_archived: bool = False,
        include_candidates: bool = False,
    ) -> ResolvedStyle:
        if isinstance(reference, Mapping):
            style_id = str(reference["id"])
            version = str(reference["version"]) if reference.get("version") else version
            layer = str(reference["layer"]) if reference.get("layer") else layer
        else:
            style_id = reference

        registry = StyleRegistry(self.paths, self.project_root)
        packs = registry.discover(
            include_archived=include_archived,
            include_candidates=include_candidates,
        )
        layers = (layer,) if layer else LAYER_PRECEDENCE
        for current_layer in layers:
            matches = [
                pack
                for pack in packs
                if pack.layer == current_layer
                and pack.style_id == style_id
                and (version is None or pack.version == version)
            ]
            if not matches:
                continue
            if version is not None:
                return ResolvedStyle(matches[0])
            stable = [pack for pack in matches if parse_semver(pack.version).stable]
            selected = max(stable or matches, key=lambda pack: parse_semver(pack.version))
            return ResolvedStyle(selected)

        raise StyleNotFoundError(
            f"Style Pack not found: {style_id}"
            + (f" {version}" if version else "")
            + (f" in {layer}" if layer else ""),
            context={
                "style_id": style_id,
                "version": version,
                "layer": layer,
                "project_root": str(self.project_root) if self.project_root else None,
            },
        )

    def resolve_project(self, project: ArticleProject) -> ResolvedStyle:
        reference = project.document["style"]["layout_style"]
        resolver = StyleResolver(
            project.workspace_paths or self.paths,
            project_root=project.root,
        )
        return resolver.resolve(
            reference,
            include_archived=True,
            include_candidates=True,
        )

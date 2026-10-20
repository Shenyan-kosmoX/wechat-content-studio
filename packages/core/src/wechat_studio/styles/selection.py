"""Resolve all project style references as one consistent, pinned selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wechat_studio.errors import StyleConflictError
from wechat_studio.projects.project import ArticleProject
from wechat_studio.storage.paths import WorkspacePaths, resolve_workspace_paths

from .presets import PresetRegistry
from .profiles import WritingProfile, WritingProfileRegistry
from .resolver import ResolvedStyle, StyleResolver


@dataclass(frozen=True, slots=True)
class ProjectStyleSelection:
    layout: ResolvedStyle
    writing_profile: WritingProfile | None
    preset: dict[str, Any] | None


def _paths_for_project(project: ArticleProject) -> WorkspacePaths:
    if project.workspace_paths is not None:
        return project.workspace_paths
    if project.root.parent.name == "articles":
        user_root = project.root.parent.parent
    else:
        user_root = project.root
    return resolve_workspace_paths(user_root)


def resolve_project_style_selection(project: ArticleProject) -> ProjectStyleSelection:
    paths = _paths_for_project(project)
    selection = project.document["style"]
    layout = StyleResolver(paths, project_root=project.root).resolve(
        selection["layout_style"],
        include_archived=True,
        include_candidates=True,
    )

    writing_profile: WritingProfile | None = None
    writing_reference = selection.get("writing_profile")
    if writing_reference is not None:
        writing_profile = WritingProfileRegistry(
            paths,
            project_root=project.root,
        ).resolve(writing_reference, include_archived=True)

    preset: dict[str, Any] | None = None
    preset_reference = selection.get("preset")
    if preset_reference is not None:
        preset = PresetRegistry(paths, project_root=project.root).resolve(
            str(preset_reference["id"]),
            version=str(preset_reference["version"]),
            include_archived=True,
        )
        if preset["layout_style"] != selection["layout_style"]:
            raise StyleConflictError(
                "Project layout style does not match its pinned preset.",
                context={
                    "project_layout_style": selection["layout_style"],
                    "preset_layout_style": preset["layout_style"],
                    "preset": preset_reference,
                },
            )
        if preset["writing_profile"] != writing_reference:
            raise StyleConflictError(
                "Project writing profile does not match its pinned preset.",
                context={
                    "project_writing_profile": writing_reference,
                    "preset_writing_profile": preset["writing_profile"],
                    "preset": preset_reference,
                },
            )

    return ProjectStyleSelection(
        layout=layout,
        writing_profile=writing_profile,
        preset=preset,
    )

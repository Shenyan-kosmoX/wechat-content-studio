"""Validated preset storage and dependency resolution."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import PresetInvalidError, StyleConflictError, StyleNotFoundError
from wechat_studio.storage.paths import WorkspacePaths
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic

from .profiles import WritingProfileRegistry
from .resolver import StyleResolver
from .versions import parse_semver, style_directory_name


def _preset_filename(preset_id: str, version: str) -> str:
    return style_directory_name(preset_id, version) + ".yaml"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class PresetRegistry:
    def __init__(self, paths: WorkspacePaths, *, project_root: str | Path | None = None) -> None:
        self.paths = paths
        self.project_root = Path(project_root).resolve() if project_root else None

    def discover(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        if not self.paths.presets.is_dir():
            return []
        validator = ContractValidator()
        presets: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for path in sorted(self.paths.presets.glob("*.yaml")):
            document = read_yaml(path)
            validator.validate_or_raise(document, "preset")
            expected_name = _preset_filename(document["preset_id"], document["version"])
            if path.name != expected_name:
                raise PresetInvalidError(
                    f"Preset filename must be {expected_name}.",
                    context={"path": str(path), "expected": expected_name},
                )
            key = (document["preset_id"], document["version"])
            if key in seen:
                raise StyleConflictError(
                    f"Duplicate preset version: {document['preset_id']} {document['version']}",
                    context={"path": str(path)},
                )
            seen.add(key)
            if document["status"] == "archived" and not include_archived:
                continue
            presets.append(document)
        return presets

    def resolve(
        self,
        preset_id: str,
        *,
        version: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        matches = [
            preset
            for preset in self.discover(include_archived=include_archived)
            if preset["preset_id"] == preset_id
            and (version is None or preset["version"] == version)
        ]
        if not matches:
            raise StyleNotFoundError(
                f"Preset not found: {preset_id}" + (f" {version}" if version else ""),
                context={"preset_id": preset_id, "version": version},
            )
        if version is not None:
            return matches[0]
        return max(matches, key=lambda item: parse_semver(item["version"]))

    def validate_dependencies(self, preset: Mapping[str, Any]) -> None:
        resolver = StyleResolver(self.paths, project_root=self.project_root)
        resolver.resolve(preset["layout_style"], include_archived=True)
        writing = preset.get("writing_profile")
        if writing is not None:
            WritingProfileRegistry(
                self.paths,
                project_root=self.project_root,
            ).resolve(writing, include_archived=True)

    def save(
        self,
        preset: Mapping[str, Any],
        *,
        validate_dependencies: bool = True,
    ) -> Path:
        document = dict(preset)
        validator = ContractValidator()
        validator.validate_or_raise(document, "preset")
        if validate_dependencies:
            self.validate_dependencies(document)
        self.paths.presets.mkdir(parents=True, exist_ok=True)
        destination = self.paths.presets / _preset_filename(
            document["preset_id"], document["version"]
        )
        if destination.exists():
            raise StyleConflictError(
                f"Preset version already exists: {document['preset_id']} {document['version']}",
                context={"path": str(destination)},
            )
        return write_yaml_atomic(
            destination,
            document,
            validator=lambda value: validator.validate_or_raise(value, "preset"),
        )

    def create(
        self,
        *,
        preset_id: str,
        name: str,
        version: str,
        layout_style: Mapping[str, Any],
        writing_profile: Mapping[str, Any] | None = None,
        description: str = "",
    ) -> Path:
        timestamp = _now()
        document: dict[str, Any] = {
            "preset_schema_version": "1.0",
            "preset_id": preset_id,
            "name": name,
            "description": description,
            "version": version,
            "status": "active",
            "layout_style": dict(layout_style),
            "writing_profile": (
                dict(writing_profile) if writing_profile is not None else None
            ),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self.save(document)

    def archive(self, preset_id: str, version: str) -> Path:
        document = self.resolve(preset_id, version=version, include_archived=True)
        path = self.paths.presets / _preset_filename(preset_id, version)
        document["status"] = "archived"
        document["updated_at"] = _now()
        validator = ContractValidator()
        return write_yaml_atomic(
            path,
            document,
            validator=lambda value: validator.validate_or_raise(value, "preset"),
        )

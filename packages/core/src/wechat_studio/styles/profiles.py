"""Discover, import, promote, archive, and resolve writing profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import (
    StyleConflictError,
    StyleImmutableError,
    StyleNotFoundError,
    StylePromotionError,
)
from wechat_studio.storage.paths import WorkspacePaths
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic

from .versions import parse_semver, stable_version, style_directory_name


LAYER_PRECEDENCE = ("project", "private", "builtin")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _profile_filename(profile_id: str, version: str) -> str:
    return style_directory_name(profile_id, version) + ".yaml"


@dataclass(frozen=True, slots=True)
class WritingProfile:
    path: Path
    document: dict[str, Any]
    layer: str

    @property
    def profile_id(self) -> str:
        return self.document["profile_id"]

    @property
    def version(self) -> str:
        return self.document["version"]

    @property
    def key(self) -> tuple[str, str, str]:
        return self.layer, self.profile_id, self.version


class WritingProfileRegistry:
    def __init__(self, paths: WorkspacePaths, *, project_root: str | Path | None = None) -> None:
        self.paths = paths
        self.project_root = Path(project_root).resolve() if project_root else None

    @staticmethod
    def _standalone_files(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        files = list(root.glob("*.yaml"))
        files.extend(path / "writing-profile.yaml" for path in root.iterdir() if path.is_dir())
        return sorted(path for path in files if path.is_file())

    def discover(self, *, include_archived: bool = False) -> list[WritingProfile]:
        validator = ContractValidator()
        profiles: list[WritingProfile] = []
        roots: dict[str, Path] = {"private": self.paths.private_writing_profiles}
        if self.project_root is not None:
            roots["project"] = self.project_root / "styles" / "local" / "writing-profiles"
        for layer, root in roots.items():
            for path in self._standalone_files(root):
                document = read_yaml(path)
                validator.validate_or_raise(document, "writing-profile")
                if document["status"] == "archived" and not include_archived:
                    continue
                profiles.append(WritingProfile(path, document, layer))

        from .registry import StyleRegistry

        style_registry = StyleRegistry(self.paths, self.project_root)
        for pack in style_registry.discover(include_archived=include_archived):
            if pack.writing_profile is not None:
                path = pack.root / pack.document["paths"]["writing_profile"]
                profiles.append(WritingProfile(path, pack.writing_profile, pack.layer))

        seen: dict[tuple[str, str, str], Path] = {}
        for profile in profiles:
            previous = seen.get(profile.key)
            if previous is not None and previous != profile.path:
                raise StyleConflictError(
                    f"Duplicate writing profile version: {profile.profile_id} {profile.version}",
                    context={"first": str(previous), "second": str(profile.path)},
                )
            seen[profile.key] = profile.path
        return profiles

    def resolve(
        self,
        reference: Mapping[str, object],
        *,
        include_archived: bool = False,
    ) -> WritingProfile:
        profile_id = str(reference["id"])
        version = str(reference["version"])
        layer = str(reference["layer"])
        matches = [
            profile
            for profile in self.discover(include_archived=include_archived)
            if profile.profile_id == profile_id
            and profile.version == version
            and profile.layer == layer
        ]
        if matches:
            return matches[0]
        raise StyleNotFoundError(
            f"Writing profile not found: {profile_id} {version} in {layer}",
            context={"profile_id": profile_id, "version": version, "layer": layer},
        )

    def latest(self, profile_id: str, *, layer: str | None = None) -> WritingProfile:
        for current_layer in ((layer,) if layer else LAYER_PRECEDENCE):
            matches = [
                profile
                for profile in self.discover()
                if profile.profile_id == profile_id and profile.layer == current_layer
            ]
            if matches:
                return max(matches, key=lambda profile: parse_semver(profile.version))
        raise StyleNotFoundError(
            f"Writing profile not found: {profile_id}",
            context={"profile_id": profile_id, "layer": layer},
        )

    def discover_imports(self) -> list[WritingProfile]:
        validator = ContractValidator()
        profiles: list[WritingProfile] = []
        for path in self._standalone_files(self.paths.imported_writing_profiles):
            document = read_yaml(path)
            validator.validate_or_raise(document, "writing-profile")
            if document["status"] not in {"provisional", "established"}:
                continue
            profiles.append(WritingProfile(path.resolve(), document, "imports"))
        seen: dict[tuple[str, str], Path] = {}
        for profile in profiles:
            key = (profile.profile_id, profile.version)
            previous = seen.get(key)
            if previous is not None and previous != profile.path:
                raise StyleConflictError(
                    f"Duplicate imported writing profile: {profile.profile_id} {profile.version}",
                    context={"first": str(previous), "second": str(profile.path)},
                )
            seen[key] = profile.path
        return sorted(
            profiles,
            key=lambda profile: (profile.profile_id, parse_semver(profile.version)),
        )

    def import_candidate(self, source: str | Path) -> WritingProfile:
        supplied = Path(source).resolve()
        document = read_yaml(supplied)
        ContractValidator().validate_or_raise(document, "writing-profile")
        if document["status"] not in {"provisional", "established"}:
            raise StylePromotionError(
                "Only provisional or established candidate writing profiles may be imported.",
                context={"path": str(supplied), "status": document["status"]},
            )
        distillation = document.get("extensions", {}).get("shenyan.distillation", {})
        if distillation.get("candidate") is not True:
            raise StylePromotionError(
                "Writing profile import requires a distilled candidate document.",
                context={"path": str(supplied)},
            )
        destination = self.paths.imported_writing_profiles / _profile_filename(
            document["profile_id"], document["version"]
        )
        if destination.exists():
            raise StyleConflictError(
                f"Imported writing profile already exists: {document['profile_id']} {document['version']}",
                context={"path": str(destination)},
            )
        write_yaml_atomic(
            destination,
            document,
            validator=lambda value: ContractValidator().validate_or_raise(
                value, "writing-profile"
            ),
        )
        return WritingProfile(destination.resolve(), document, "imports")

    def promote_candidate(
        self,
        candidate: WritingProfile | str | Path,
        *,
        confirmed_by_user: bool,
        target_version: str | None = None,
    ) -> WritingProfile:
        if not confirmed_by_user:
            raise StylePromotionError(
                "Writing profile promotion requires explicit user confirmation."
            )
        if isinstance(candidate, WritingProfile):
            source = candidate
        else:
            source_path = Path(candidate).resolve()
            document = read_yaml(source_path)
            ContractValidator().validate_or_raise(document, "writing-profile")
            layer = (
                "imports"
                if source_path.parent == self.paths.imported_writing_profiles.resolve()
                else "project"
            )
            source = WritingProfile(source_path, document, layer)
        if source.layer not in {"project", "imports"}:
            raise StylePromotionError(
                "Only project or imported candidate writing profiles can be promoted.",
                context={"path": str(source.path), "layer": source.layer},
            )
        if source.document["status"] not in {"provisional", "established"}:
            raise StylePromotionError(
                "Only provisional or established writing profiles can be promoted.",
                context={"path": str(source.path), "status": source.document["status"]},
            )
        distillation = source.document.get("extensions", {}).get(
            "shenyan.distillation", {}
        )
        if distillation.get("candidate") is not True:
            raise StylePromotionError(
                "Writing profile promotion requires a distilled candidate document.",
                context={"path": str(source.path)},
            )
        version = target_version or stable_version(source.version)
        if not parse_semver(version).stable:
            raise StylePromotionError(
                "Promoted writing profile versions must be stable semantic versions.",
                context={"target_version": version},
            )
        destination = self.paths.private_writing_profiles / _profile_filename(
            source.profile_id, version
        )
        if destination.exists():
            raise StyleConflictError(
                f"Private writing profile already exists: {source.profile_id} {version}",
                context={"path": str(destination)},
            )
        document = dict(source.document)
        document["version"] = version
        document["status"] = (
            "validated" if source.document["status"] == "validated" else "established"
        )
        extensions = dict(document.get("extensions", {}))
        extensions["shenyan.distillation"] = dict(distillation)
        promotion = dict(extensions.get("shenyan.promotion", {}))
        promotion.update(
            {
                "confirmed_by_user": True,
                "promoted_at": _now(),
                "source_version": source.version,
            }
        )
        extensions["shenyan.promotion"] = promotion
        document["extensions"] = extensions
        write_yaml_atomic(
            destination,
            document,
            validator=lambda value: ContractValidator().validate_or_raise(
                value, "writing-profile"
            ),
        )
        return WritingProfile(destination.resolve(), document, "private")

    def archive(self, profile: WritingProfile | str | Path) -> WritingProfile:
        if isinstance(profile, WritingProfile):
            source = profile
        else:
            source_path = Path(profile).resolve()
            document = read_yaml(source_path)
            ContractValidator().validate_or_raise(document, "writing-profile")
            source = WritingProfile(source_path, document, "private")
        if source.layer != "private" or source.path.parent != self.paths.private_writing_profiles.resolve():
            raise StyleImmutableError(
                "Only private standalone writing profiles can be archived in place.",
                context={"path": str(source.path), "layer": source.layer},
            )
        document = dict(source.document)
        document["status"] = "archived"
        extensions = dict(document.get("extensions", {}))
        archive = dict(extensions.get("shenyan.archive", {}))
        archive["archived_at"] = _now()
        extensions["shenyan.archive"] = archive
        document["extensions"] = extensions
        write_yaml_atomic(
            source.path,
            document,
            validator=lambda value: ContractValidator().validate_or_raise(
                value, "writing-profile"
            ),
        )
        return WritingProfile(source.path, document, "private")

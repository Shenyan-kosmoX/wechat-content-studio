"""style.* commands for discovery, validation, candidate lifecycle, and archive."""

from __future__ import annotations

import argparse
from pathlib import Path

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import StyleNotFoundError
from wechat_studio.storage.yaml_io import read_yaml
from wechat_studio.styles import (
    PresetRegistry,
    StylePack,
    StyleRegistry,
    StyleResolver,
    WritingProfileRegistry,
    archive_style_pack,
    import_candidate,
    parse_semver,
    promote_candidate,
)

from ..errors import usage_error
from ..output import CommandExecution
from .common import workspace_manager


def configure(top: argparse._SubParsersAction) -> None:
    parser = top.add_parser("style", help="Manage versioned styles and candidates.")
    actions = parser.add_subparsers(dest="style_action", required=True)

    listing = actions.add_parser("list")
    listing.add_argument("--project-root")
    listing.add_argument("--include-archived", action="store_true")
    listing.add_argument("--include-candidates", action="store_true")
    listing.add_argument("--include-imports", action="store_true")
    listing.set_defaults(handler=run_list, command_name="style.list")

    validate = actions.add_parser("validate")
    validate.add_argument("path")
    validate.set_defaults(handler=run_validate, command_name="style.validate")

    imported = actions.add_parser("import-candidate")
    imported.add_argument("--source", required=True)
    imported.set_defaults(handler=run_import_candidate, command_name="style.import-candidate")

    promote = actions.add_parser("promote")
    source = promote.add_mutually_exclusive_group(required=True)
    source.add_argument("--source")
    source.add_argument("--id")
    promote.add_argument("--version")
    promote.add_argument("--target-version")
    promote.add_argument("--confirmed-by-user", action="store_true")
    promote.set_defaults(handler=run_promote, command_name="style.promote")

    archive = actions.add_parser("archive")
    source = archive.add_mutually_exclusive_group(required=True)
    source.add_argument("--source")
    source.add_argument("--id")
    archive.add_argument("--version")
    archive.add_argument("--layer", choices=("project", "private", "builtin"))
    archive.add_argument("--project-root")
    archive.set_defaults(handler=run_archive, command_name="style.archive")

    preset_save = actions.add_parser("save-preset")
    preset_save.add_argument("--id", required=True)
    preset_save.add_argument("--name", required=True)
    preset_save.add_argument("--version", required=True)
    preset_save.add_argument("--description", default="")
    preset_save.add_argument("--layout-style-id", required=True)
    preset_save.add_argument("--layout-style-version", required=True)
    preset_save.add_argument(
        "--layout-style-layer", choices=("project", "private", "builtin"), required=True
    )
    preset_save.add_argument("--writing-profile-id")
    preset_save.add_argument("--writing-profile-version")
    preset_save.add_argument(
        "--writing-profile-layer", choices=("project", "private")
    )
    preset_save.add_argument("--project-root")
    preset_save.set_defaults(handler=run_save_preset, command_name="style.save-preset")

    preset_archive = actions.add_parser("archive-preset")
    preset_archive.add_argument("--id", required=True)
    preset_archive.add_argument("--version", required=True)
    preset_archive.add_argument("--project-root")
    preset_archive.set_defaults(
        handler=run_archive_preset, command_name="style.archive-preset"
    )

    profile_import = actions.add_parser("import-writing-profile")
    profile_import.add_argument("--source", required=True)
    profile_import.set_defaults(
        handler=run_import_writing_profile,
        command_name="style.import-writing-profile",
    )

    profile_promote = actions.add_parser("promote-writing-profile")
    profile_source = profile_promote.add_mutually_exclusive_group(required=True)
    profile_source.add_argument("--source")
    profile_source.add_argument("--id")
    profile_promote.add_argument("--version")
    profile_promote.add_argument("--target-version")
    profile_promote.add_argument("--confirmed-by-user", action="store_true")
    profile_promote.set_defaults(
        handler=run_promote_writing_profile,
        command_name="style.promote-writing-profile",
    )

    profile_archive = actions.add_parser("archive-writing-profile")
    profile_source = profile_archive.add_mutually_exclusive_group(required=True)
    profile_source.add_argument("--source")
    profile_source.add_argument("--id")
    profile_archive.add_argument("--version")
    profile_archive.set_defaults(
        handler=run_archive_writing_profile,
        command_name="style.archive-writing-profile",
    )


def run_list(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    registry = StyleRegistry(manager.paths, project_root=Path(args.project_root) if args.project_root else None)
    styles = registry.list_records(
        include_archived=args.include_archived,
        include_candidates=args.include_candidates,
        include_imports=args.include_imports,
    )
    profile_registry = WritingProfileRegistry(
        manager.paths, project_root=args.project_root
    )
    profiles = [
        {
            "profile_id": profile.profile_id,
            "version": profile.version,
            "layer": profile.layer,
            "status": profile.document["status"],
            "path": str(profile.path),
        }
        for profile in profile_registry.discover(include_archived=args.include_archived)
    ]
    if args.include_imports:
        profiles.extend(
            {
                "profile_id": profile.profile_id,
                "version": profile.version,
                "layer": profile.layer,
                "status": profile.document["status"],
                "path": str(profile.path),
            }
            for profile in profile_registry.discover_imports()
        )
    presets = PresetRegistry(manager.paths, project_root=args.project_root).discover(
        include_archived=args.include_archived
    )
    return CommandExecution(
        "style.list",
        {
            "result_type": "style.listed",
            "style_packs": styles,
            "writing_profiles": profiles,
            "presets": presets,
        },
    )


def run_validate(args: argparse.Namespace) -> CommandExecution:
    supplied = Path(args.path).resolve()
    directory = supplied.parent if supplied.is_file() and supplied.name == "style.yaml" else supplied
    if directory.is_dir() and (directory / "style.yaml").is_file():
        pack = StylePack.load(directory, require_directory_name=False)
        data = {
            "result_type": "style.validated",
            "kind": "style_pack",
            "path": str(pack.root),
            "record": pack.to_record(),
            "reference": pack.reference,
        }
    else:
        document = read_yaml(supplied)
        if not isinstance(document, dict):
            raise usage_error("Style profile document must be a YAML object.", path=str(supplied))
        if "writing_profile_schema_version" in document:
            schema = "writing-profile"
        elif "layout_style_schema_version" in document:
            schema = "layout-style"
        elif "preset_schema_version" in document:
            schema = "preset"
        else:
            raise usage_error("Unable to determine style document type.", path=str(supplied))
        ContractValidator().validate_or_raise(document, schema)
        data = {
            "result_type": "style.validated",
            "kind": schema.replace("-", "_"),
            "path": str(supplied),
            "document": document,
        }
    return CommandExecution("style.validate", data)


def run_import_candidate(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    pack = import_candidate(args.source, manager.paths)
    return CommandExecution(
        "style.import-candidate",
        {
            "result_type": "style.candidate_imported",
            "path": str(pack.root),
            "reference": pack.reference,
            "record": pack.to_record(),
        },
    )


def _imported_candidate(manager, style_id: str, version: str | None) -> StylePack:
    matches = [
        pack
        for pack in StyleRegistry(manager.paths).discover_imports()
        if pack.style_id == style_id and (version is None or pack.version == version)
    ]
    if not matches:
        raise StyleNotFoundError(
            f"Imported candidate not found: {style_id}",
            context={"style_id": style_id, "version": version},
        )
    if version is None and len(matches) > 1:
        matches.sort(key=lambda pack: parse_semver(pack.version))
    return matches[-1]


def run_promote(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    candidate = StylePack.load(args.source) if args.source else _imported_candidate(
        manager, args.id, args.version
    )
    pack = promote_candidate(
        candidate,
        manager.paths,
        confirmed_by_user=args.confirmed_by_user,
        target_version=args.target_version,
    )
    return CommandExecution(
        "style.promote",
        {
            "result_type": "style.promoted",
            "source": str(candidate.root),
            "path": str(pack.root),
            "reference": pack.reference,
            "record": pack.to_record(),
        },
    )


def run_archive(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    if args.source:
        source = StylePack.load(args.source)
    else:
        if not args.version or not args.layer:
            raise usage_error("Archiving by ID requires --version and --layer.")
        source = StyleResolver(
            manager.paths, project_root=args.project_root
        ).resolve(
            args.id,
            version=args.version,
            layer=args.layer,
            include_archived=True,
            include_candidates=True,
        ).pack
    pack = archive_style_pack(source)
    return CommandExecution(
        "style.archive",
        {
            "result_type": "style.archived",
            "path": str(pack.root),
            "reference": pack.reference,
            "record": pack.to_record(),
        },
    )


def _optional_reference(args: argparse.Namespace, prefix: str) -> dict[str, str] | None:
    values = {
        "id": getattr(args, f"{prefix}_id"),
        "version": getattr(args, f"{prefix}_version"),
        "layer": getattr(args, f"{prefix}_layer"),
    }
    supplied = [value is not None for value in values.values()]
    if any(supplied) and not all(supplied):
        raise usage_error(
            f"{prefix.replace('_', ' ')} requires id, version, and layer together.",
            fields=values,
        )
    return values if all(supplied) else None


def run_save_preset(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    writing = _optional_reference(args, "writing_profile")
    registry = PresetRegistry(manager.paths, project_root=args.project_root)
    path = registry.create(
        preset_id=args.id,
        name=args.name,
        version=args.version,
        description=args.description,
        layout_style={
            "id": args.layout_style_id,
            "version": args.layout_style_version,
            "layer": args.layout_style_layer,
        },
        writing_profile=writing,
    )
    document = read_yaml(path)
    return CommandExecution(
        "style.save-preset",
        {
            "result_type": "style.preset_saved",
            "path": str(path),
            "reference": {
                "id": document["preset_id"],
                "version": document["version"],
                "layer": "private",
            },
            "document": document,
        },
    )


def run_archive_preset(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    registry = PresetRegistry(manager.paths, project_root=args.project_root)
    path = registry.archive(args.id, args.version)
    document = read_yaml(path)
    return CommandExecution(
        "style.archive-preset",
        {
            "result_type": "style.preset_archived",
            "path": str(path),
            "reference": {"id": args.id, "version": args.version, "layer": "private"},
            "document": document,
        },
    )


def run_import_writing_profile(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    profile = WritingProfileRegistry(manager.paths).import_candidate(args.source)
    return CommandExecution(
        "style.import-writing-profile",
        {
            "result_type": "style.writing_profile_imported",
            "path": str(profile.path),
            "reference": {
                "id": profile.profile_id,
                "version": profile.version,
                "layer": profile.layer,
            },
            "document": profile.document,
        },
    )


def _imported_writing_profile(manager, profile_id: str, version: str | None):
    matches = [
        profile
        for profile in WritingProfileRegistry(manager.paths).discover_imports()
        if profile.profile_id == profile_id
        and (version is None or profile.version == version)
    ]
    if not matches:
        raise StyleNotFoundError(
            f"Imported writing profile not found: {profile_id}",
            context={"profile_id": profile_id, "version": version},
        )
    return max(matches, key=lambda profile: parse_semver(profile.version))


def run_promote_writing_profile(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    registry = WritingProfileRegistry(manager.paths)
    candidate = (
        args.source
        if args.source
        else _imported_writing_profile(manager, args.id, args.version)
    )
    profile = registry.promote_candidate(
        candidate,
        confirmed_by_user=args.confirmed_by_user,
        target_version=args.target_version,
    )
    return CommandExecution(
        "style.promote-writing-profile",
        {
            "result_type": "style.writing_profile_promoted",
            "path": str(profile.path),
            "reference": {
                "id": profile.profile_id,
                "version": profile.version,
                "layer": profile.layer,
            },
            "document": profile.document,
        },
    )


def run_archive_writing_profile(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    registry = WritingProfileRegistry(manager.paths)
    if args.source:
        source = args.source
    else:
        if not args.version:
            raise usage_error("Archiving a writing profile by ID requires --version.")
        source = registry.resolve(
            {"id": args.id, "version": args.version, "layer": "private"},
            include_archived=True,
        )
    profile = registry.archive(source)
    return CommandExecution(
        "style.archive-writing-profile",
        {
            "result_type": "style.writing_profile_archived",
            "path": str(profile.path),
            "reference": {
                "id": profile.profile_id,
                "version": profile.version,
                "layer": profile.layer,
            },
            "document": profile.document,
        },
    )

from __future__ import annotations

import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from wechat_studio.errors import (
    PresetInvalidError,
    StyleConflictError,
    StyleImmutableError,
    StyleNotFoundError,
    StylePromotionError,
)
from wechat_studio.projects import WorkspaceManager, create_article_project
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic
from wechat_studio.styles import (
    PresetRegistry,
    StylePack,
    StyleRegistry,
    StyleResolver,
    WritingProfileRegistry,
    archive_style_pack,
    import_candidate,
    promote_candidate,
    resolve_project_style_selection,
    style_directory_name,
)


BUILTIN_ID = "basic-editorial"
BUILTIN_VERSION = "1.0.0"


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager.resolve(
        tmp_path / "user",
        state_root=tmp_path / "state",
        resources_root=Path(__file__).parents[2] / "resources",
    ).initialize()


def builtin_pack(workspace: WorkspaceManager) -> Path:
    return (
        workspace.paths.resources_root
        / "builtin-styles"
        / style_directory_name(BUILTIN_ID, BUILTIN_VERSION)
    )


def clone_pack(
    source: Path,
    destination_root: Path,
    *,
    style_id: str,
    version: str,
    layer: str,
    status: str = "active",
    maturity: str = "validated",
    paragraph_marker: str | None = None,
) -> Path:
    destination = destination_root / style_directory_name(style_id, version)
    shutil.copytree(source, destination)

    style_path = destination / "style.yaml"
    style = read_yaml(style_path)
    style["style_pack_id"] = style_id
    style["name"] = f"{style_id} {version}"
    style["version"] = version
    style["layer"] = layer
    style["status"] = status
    style["maturity"] = maturity
    style["layout_style"] = {"id": style_id, "version": version}
    style["writing_profile"] = None
    style["paths"]["writing_profile"] = None
    style["provenance"]["parent_version"] = None
    write_yaml_atomic(style_path, style)

    layout_path = destination / "layout-style.yaml"
    layout = read_yaml(layout_path)
    layout["layout_style_id"] = style_id
    layout["name"] = f"{style_id} {version}"
    layout["version"] = version
    layout["status"] = (
        "provisional" if status == "candidate" else maturity
    )
    write_yaml_atomic(layout_path, layout)

    if paragraph_marker:
        paragraph = destination / "components" / "paragraph.html"
        paragraph.write_text(
            paragraph.read_text(encoding="utf-8").replace(
                "font-weight:400;",
                f"font-weight:400;outline:{paragraph_marker};",
                1,
            ),
            encoding="utf-8",
        )
    return destination


def test_builtin_style_pack_is_complete_and_discoverable(
    workspace: WorkspaceManager,
) -> None:
    pack = StylePack.load(
        builtin_pack(workspace),
        expected_layer="builtin",
        require_directory_name=True,
    )
    records = StyleRegistry(workspace.paths).list_records()

    assert pack.reference == {
        "id": BUILTIN_ID,
        "version": BUILTIN_VERSION,
        "layer": "builtin",
    }
    assert len(list(pack.components_directory.glob("*.html"))) == 12
    assert any(record["style_pack_id"] == BUILTIN_ID for record in records)


def test_style_resolution_uses_project_then_private_then_builtin(
    workspace: WorkspaceManager,
) -> None:
    project = create_article_project(
        workspace,
        name="风格优先级",
        mode="layout_only",
        project_id="style-precedence",
    )
    source = builtin_pack(workspace)
    private = clone_pack(
        source,
        workspace.paths.private_styles,
        style_id="layered-style",
        version="2.0.0",
        layer="private",
        paragraph_marker="1px-private",
    )
    local = clone_pack(
        source,
        project.root / "styles" / "local",
        style_id="layered-style",
        version="1.0.0",
        layer="project",
        paragraph_marker="1px-project",
    )

    resolver = StyleResolver(workspace.paths, project_root=project.root)

    assert resolver.resolve("layered-style").pack.root == local.resolve()
    assert (
        resolver.resolve("layered-style", layer="private").pack.root
        == private.resolve()
    )
    assert resolver.resolve(
        {"id": BUILTIN_ID, "version": BUILTIN_VERSION, "layer": "builtin"}
    ).pack.root == source.resolve()


def test_exact_version_is_pinned_even_when_newer_version_exists(
    workspace: WorkspaceManager,
) -> None:
    source = builtin_pack(workspace)
    first = clone_pack(
        source,
        workspace.paths.private_styles,
        style_id="versioned-style",
        version="1.0.0",
        layer="private",
    )
    newer = clone_pack(
        source,
        workspace.paths.private_styles,
        style_id="versioned-style",
        version="1.1.0",
        layer="private",
    )
    resolver = StyleResolver(workspace.paths)

    assert resolver.resolve("versioned-style", layer="private").pack.root == newer.resolve()
    assert resolver.resolve(
        {"id": "versioned-style", "version": "1.0.0", "layer": "private"}
    ).pack.root == first.resolve()


def test_candidate_import_and_promotion_copy_without_mutating_source(
    workspace: WorkspaceManager,
    tmp_path: Path,
) -> None:
    candidate_root = clone_pack(
        builtin_pack(workspace),
        tmp_path / "candidate-source",
        style_id="learned-editorial",
        version="1.1.0-candidate",
        layer="project",
        status="candidate",
        maturity="provisional",
    )
    source_before = StylePack.load(candidate_root).fingerprint()

    imported = import_candidate(candidate_root, workspace.paths)
    with pytest.raises(StylePromotionError):
        promote_candidate(imported, workspace.paths, confirmed_by_user=False)

    promoted = promote_candidate(
        imported,
        workspace.paths,
        confirmed_by_user=True,
    )

    assert promoted.reference == {
        "id": "learned-editorial",
        "version": "1.1.0",
        "layer": "private",
    }
    assert promoted.status == "active"
    assert promoted.maturity == "established"
    assert StylePack.load(candidate_root).fingerprint() == source_before
    assert imported.status == "candidate"
    assert imported.root.exists()


def test_archiving_hides_style_from_new_choices_but_keeps_exact_history(
    workspace: WorkspaceManager,
) -> None:
    private = clone_pack(
        builtin_pack(workspace),
        workspace.paths.private_styles,
        style_id="historical-style",
        version="1.0.0",
        layer="private",
    )
    archived = archive_style_pack(private)
    resolver = StyleResolver(workspace.paths)

    assert archived.status == "archived"
    assert private.exists()
    with pytest.raises(StyleNotFoundError):
        resolver.resolve("historical-style", layer="private")
    assert resolver.resolve(
        {"id": "historical-style", "version": "1.0.0", "layer": "private"},
        include_archived=True,
    ).pack.root == private.resolve()


def test_builtin_style_cannot_be_archived(workspace: WorkspaceManager) -> None:
    with pytest.raises(StyleImmutableError):
        archive_style_pack(builtin_pack(workspace))


def preset_document() -> dict:
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc).isoformat()
    return {
        "preset_schema_version": "1.0",
        "preset_id": "basic-layout-only",
        "name": "Basic 纯排版",
        "description": "使用内置 Basic 排版，不绑定写作档案。",
        "version": "1.0.0",
        "status": "active",
        "layout_style": {
            "id": BUILTIN_ID,
            "version": BUILTIN_VERSION,
            "layer": "builtin",
        },
        "writing_profile": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def test_preset_dependencies_and_project_selection_must_match(
    workspace: WorkspaceManager,
) -> None:
    registry = PresetRegistry(workspace.paths)
    preset = preset_document()
    registry.save(preset)
    assert registry.resolve("basic-layout-only")["version"] == "1.0.0"

    project = create_article_project(
        workspace,
        name="预设一致性",
        mode="layout_only",
        project_id="preset-consistency",
        preset={"id": "basic-layout-only", "version": "1.0.0", "layer": "private"},
    )
    selection = resolve_project_style_selection(project)
    assert selection.preset == preset
    assert selection.layout.reference == preset["layout_style"]

    document = read_yaml(project.project_file)
    document["style"]["layout_style"]["version"] = "9.9.9"
    write_yaml_atomic(project.project_file, document)
    project.reload()
    with pytest.raises(StyleNotFoundError):
        resolve_project_style_selection(project)


def test_preset_rejects_missing_style_dependency(workspace: WorkspaceManager) -> None:
    invalid = deepcopy(preset_document())
    invalid["preset_id"] = "missing-style"
    invalid["layout_style"] = {
        "id": "does-not-exist",
        "version": "1.0.0",
        "layer": "private",
    }

    with pytest.raises(StyleNotFoundError):
        PresetRegistry(workspace.paths).save(invalid)


def test_malformed_preset_filename_is_detected(workspace: WorkspaceManager) -> None:
    path = workspace.paths.presets / "wrong-name.yaml"
    write_yaml_atomic(path, preset_document())

    with pytest.raises(PresetInvalidError):
        PresetRegistry(workspace.paths).discover()


def test_preset_version_cannot_be_overwritten(workspace: WorkspaceManager) -> None:
    registry = PresetRegistry(workspace.paths)
    preset = preset_document()
    registry.save(preset)

    with pytest.raises(StyleConflictError):
        registry.save(preset)


def test_standalone_writing_profile_candidate_lifecycle(
    workspace: WorkspaceManager,
    tmp_path: Path,
) -> None:
    source = tmp_path / "author-writing-v0.1.0-candidate.1.yaml"
    document = read_yaml(
        Path(__file__).parents[1] / "contracts" / "fixtures" / "writing-profile.valid.yaml"
    )
    document["profile_id"] = "author-writing"
    document["version"] = "0.1.0-candidate.1"
    document["status"] = "provisional"
    document["extensions"] = {
        "shenyan.distillation": {"candidate": True, "storage": "project"}
    }
    write_yaml_atomic(source, document)

    registry = WritingProfileRegistry(workspace.paths)
    imported = registry.import_candidate(source)
    with pytest.raises(StylePromotionError):
        registry.promote_candidate(imported, confirmed_by_user=False)

    promoted = registry.promote_candidate(imported, confirmed_by_user=True)
    archived = registry.archive(promoted)

    assert imported.layer == "imports"
    assert imported.path.parent == workspace.paths.imported_writing_profiles
    assert promoted.layer == "private"
    assert promoted.version == "0.1.0"
    assert promoted.document["status"] == "established"
    assert archived.document["status"] == "archived"
    assert source.is_file()


def test_preset_create_and_archive_updates_timestamp(
    workspace: WorkspaceManager,
) -> None:
    registry = PresetRegistry(workspace.paths)
    path = registry.create(
        preset_id="created-preset",
        name="Created Preset",
        version="1.0.0",
        layout_style={
            "id": BUILTIN_ID,
            "version": BUILTIN_VERSION,
            "layer": "builtin",
        },
    )
    created = read_yaml(path)
    archived_path = registry.archive("created-preset", "1.0.0")
    archived = read_yaml(archived_path)

    assert created["status"] == "active"
    assert archived["status"] == "archived"
    assert archived["updated_at"] >= created["updated_at"]

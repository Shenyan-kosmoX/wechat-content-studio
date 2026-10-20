from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from wechat_studio.errors import UnsupportedSchemaVersionError
from wechat_studio.migrations import migrate_project
from wechat_studio.projects import WorkspaceManager, create_article_project
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic


def _workspace(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager.resolve(
        tmp_path / "user",
        state_root=tmp_path / "state",
        resources_root=Path(__file__).parents[2] / "resources",
    ).initialize()


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_schema_v1_migration_is_a_lossless_file_level_noop(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    project = create_article_project(
        workspace,
        name="无损迁移演练",
        mode="layout_only",
        project_id="lossless-migration",
        brief="迁移不得改动任何项目文件。",
    )
    project.write_article("迁移前正文内容。")
    project.material_store.import_text("原始素材不得变化。")
    before = _tree_fingerprint(project.root)

    result = migrate_project(project.root, target_version="1.0")

    assert result.changed is False
    assert result.backup_path is None
    assert result.applied_steps == ()
    assert _tree_fingerprint(project.root) == before


def test_unknown_schema_rejection_leaves_project_byte_identical(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    project = create_article_project(
        workspace,
        name="未知版本保护",
        mode="organize",
        project_id="unknown-schema-protection",
    )
    document = read_yaml(project.project_file)
    document["project_schema_version"] = "9.0"
    write_yaml_atomic(project.project_file, document)
    before = _tree_fingerprint(project.root)
    backup_root = tmp_path / "migration-backups"

    with pytest.raises(UnsupportedSchemaVersionError) as raised:
        migrate_project(
            project.root,
            target_version="1.0",
            backup_root=backup_root,
        )

    assert raised.value.context["changed"] is False
    assert _tree_fingerprint(project.root) == before
    assert not backup_root.exists()

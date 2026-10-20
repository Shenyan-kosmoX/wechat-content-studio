from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from wechat_studio.errors import LockConflictError, MaterialNotFoundError, ProjectExistsError
from wechat_studio.projects import WorkspaceManager, create_article_project, load_article_project


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager.resolve(
        tmp_path / "user",
        state_root=tmp_path / "state",
        resources_root=Path(__file__).parents[2] / "resources",
    ).initialize()


def test_create_and_reload_article_project(workspace: WorkspaceManager) -> None:
    project = create_article_project(
        workspace,
        name="测试文章",
        mode="layout_only",
        project_id="test-article",
        brief="只排版，不补充事实。",
    )

    loaded = load_article_project(project.root, workspace_paths=workspace.paths)

    assert loaded.project_id == "test-article"
    assert loaded.document["status"] == "DRAFTING"
    assert loaded.article_file.read_text(encoding="utf-8") == ""
    assert loaded.load_manifest()["items"] == []
    assert loaded.load_plan()["blocks"] == []
    assert workspace.list_projects()[0]["project_id"] == "test-article"


def test_duplicate_project_id_is_rejected_without_overwrite(workspace: WorkspaceManager) -> None:
    first = create_article_project(
        workspace,
        name="文章一",
        mode="organize",
        project_id="same-id",
    )
    marker = first.root / "article.md"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ProjectExistsError):
        create_article_project(
            workspace,
            name="文章二",
            mode="co_write",
            project_id="same-id",
        )

    assert marker.read_text(encoding="utf-8") == "keep"


def test_material_import_is_deduplicated_and_original_is_not_overwritten(
    workspace: WorkspaceManager,
) -> None:
    project = create_article_project(
        workspace,
        name="素材测试",
        mode="organize",
        project_id="material-test",
    )

    first = project.material_store.import_text(
        "第一段中文素材。",
        original_name="draft.md",
        summary="初稿",
    )
    duplicate = project.material_store.import_text(
        "第一段中文素材。",
        original_name="another-name.md",
        summary="重复内容",
    )
    second = project.material_store.import_text(
        "第二段不同素材。",
        original_name="draft.md",
    )

    assert duplicate["id"] == first["id"] == "TEXT-001"
    assert second["id"] == "TEXT-002"
    assert len(project.load_manifest()["items"]) == 2
    first_path = project.root / first["path"]
    assert first_path.read_text(encoding="utf-8") == "第一段中文素材。"


def test_material_integrity_detects_tampering(workspace: WorkspaceManager) -> None:
    project = create_article_project(
        workspace,
        name="完整性测试",
        mode="layout_only",
        project_id="integrity-test",
    )
    item = project.material_store.import_text("不可覆盖的原文。")
    (project.root / item["path"]).write_text("被篡改", encoding="utf-8")

    assert project.material_store.verify() == [
        {"id": "TEXT-001", "path": item["path"], "status": "mismatch"}
    ]


def test_locked_image_anchor_cannot_drift(workspace: WorkspaceManager) -> None:
    project = create_article_project(
        workspace,
        name="锚点测试",
        mode="layout_only",
        project_id="anchor-test",
    )
    text = project.material_store.import_text("正文")
    image_source = project.root / "incoming.png"
    image_source.write_bytes(b"\x89PNG\r\n\x1a\nminimal")
    image = project.material_store.import_file(image_source, kind="image")
    plan = {
        "article_plan_schema_version": "1.0",
        "project_id": project.project_id,
        "status": "CONFIRMED",
        "blocks": [
            {
                "id": "BLOCK-001",
                "type": "paragraph",
                "purpose": "正文",
                "content_ref": text["id"],
                "locked": False,
            },
            {
                "id": "IMG-001",
                "type": "image",
                "purpose": "配图",
                "material_id": image["id"],
                "placement": {"after": "BLOCK-001", "locked": True},
                "locked": False,
            },
        ],
    }
    project.save_plan(plan)
    previous = project.plan_file.read_text(encoding="utf-8")
    changed = deepcopy(plan)
    changed["blocks"].insert(
        1,
        {
            "id": "BLOCK-002",
            "type": "paragraph",
            "purpose": "新增段落",
            "content_ref": text["id"],
            "locked": False,
        },
    )
    changed["blocks"][2]["placement"] = {"after": "BLOCK-002", "locked": True}

    with pytest.raises(LockConflictError):
        project.save_plan(changed)

    assert project.plan_file.read_text(encoding="utf-8") == previous


def test_plan_rejects_missing_material_and_preserves_previous_file(
    workspace: WorkspaceManager,
) -> None:
    project = create_article_project(
        workspace,
        name="缺失素材",
        mode="organize",
        project_id="missing-material",
    )
    previous = project.plan_file.read_text(encoding="utf-8")
    invalid = {
        "article_plan_schema_version": "1.0",
        "project_id": project.project_id,
        "status": "CONFIRMED",
        "blocks": [
            {
                "id": "BLOCK-001",
                "type": "paragraph",
                "purpose": "正文",
                "content_ref": "TEXT-999",
                "locked": False,
            }
        ],
    }

    with pytest.raises(MaterialNotFoundError):
        project.save_plan(invalid)

    assert project.plan_file.read_text(encoding="utf-8") == previous

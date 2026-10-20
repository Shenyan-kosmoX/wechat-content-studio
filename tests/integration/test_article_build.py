from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import RenderError
from wechat_studio.projects import WorkspaceManager, create_article_project
from wechat_studio.rendering import build_article_project
from wechat_studio.storage.yaml_io import read_yaml
from wechat_studio.validation.delivery import validate_delivery_html


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager.resolve(
        tmp_path / "user",
        state_root=tmp_path / "state",
        resources_root=Path(__file__).parents[2] / "resources",
    ).initialize()


def create_buildable_project(workspace: WorkspaceManager):
    project = create_article_project(
        workspace,
        name="产品预览测试",
        mode="layout_only",
        project_id="product-preview-test",
    )
    text = project.material_store.import_text(
        "正文素材",
        original_name="source.md",
    )
    image_source = project.root / "incoming.png"
    image_source.write_bytes(b"\x89PNG\r\n\x1a\nlocal-image-fixture")
    image = project.material_store.import_file(image_source, kind="image")
    plan = {
        "article_plan_schema_version": "1.0",
        "project_id": project.project_id,
        "status": "CONFIRMED",
        "blocks": [
            {
                "id": "BLOCK-001",
                "type": "paragraph",
                "purpose": "介绍正文",
                "content_ref": text["id"],
                "locked": True,
            },
            {
                "id": "IMG-001",
                "type": "image",
                "purpose": "展示产品截图",
                "material_id": image["id"],
                "caption": "产品截图",
                "placement": {"after": "BLOCK-001", "locked": True},
                "locked": False,
            },
        ],
    }
    project.save_plan(plan)
    project.write_article(
        """---
title: 产品预览测试
---

::: lead
这是导语。
:::

这是正文，包含 **重点**。

![产品截图](IMG-001)

::: caption
图 1｜产品截图
:::
"""
    )
    return project, image


def test_project_build_generates_preview_copy_and_delivery_report(
    workspace: WorkspaceManager,
) -> None:
    project, image = create_buildable_project(workspace)

    result = build_article_project(project)

    assert result.status == "READY_FOR_USER_WECHAT_VALIDATION"
    assert all(path.is_file() for path in result.generated_files)
    preview = (project.build_directory / "wechat_preview.html").read_text(encoding="utf-8")
    article = (project.build_directory / "wechat.html").read_text(encoding="utf-8")
    checklist = (project.build_directory / "image-checklist.md").read_text(encoding="utf-8")
    report = read_yaml(project.build_directory / "delivery-report.yaml")

    assert 'id="copy-rich-text"' in preview
    assert 'id="copy-with-placeholders"' in preview
    assert 'data-available="true"' in preview
    assert '"text/html"' in preview
    assert '"text/plain"' in preview
    assert "new ClipboardItem" in preview
    assert 'document.execCommand("copy")' in preview
    assert 'data-image-id="IMG-001"' in preview
    assert 'data-fallback-required="true"' in preview
    assert "【请插入 IMG-001" in preview
    assert "data-preview-toolbar" not in article
    assert "<script" not in article
    assert "<img" in article
    assert "IMG-001" in checklist
    assert "只有图片粘贴失败时" in checklist

    copied_asset = project.build_directory / "assets" / "images" / Path(image["path"]).name
    assert copied_asset.is_file()
    assert report["status"] == "READY_FOR_USER_WECHAT_VALIDATION"
    assert report["validation"] == {
        "local_status": "PASS",
        "wechat_status": "AWAITING_USER_VALIDATION",
        "confirmed_by_user": False,
        "confirmed_at": None,
        "notes": "本地结构与富文本复制实现已检查；由用户自行在微信公众号后台粘贴验证，不要求截图。",
    }
    assert report["images"][0]["id"] == "IMG-001"
    assert report["images"][0]["source"] == image["path"]
    assert all(record["path"].startswith("build/") for record in report["outputs"])
    assert ContractValidator().validate(report, "delivery-report").valid
    assert project.document["generation"]["sequence"] == 1
    assert project.document["generation"]["last_build_id"] == result.build_id
    assert project.document["status"] == "READY_FOR_USER_WECHAT_VALIDATION"


def test_failed_rebuild_preserves_last_valid_build_and_project_generation(
    workspace: WorkspaceManager,
) -> None:
    project, _ = create_buildable_project(workspace)
    first = build_article_project(project)
    before = {
        path.name: digest(path)
        for path in first.generated_files
    }
    generation_before = deepcopy(project.document["generation"])
    project.write_article(
        """---
title: 失败构建
---

![未登记图片](missing.png)
"""
    )

    with pytest.raises(RenderError):
        build_article_project(project)

    project.reload()
    after = {
        path.name: digest(path)
        for path in first.generated_files
    }
    assert after == before
    assert project.document["generation"] == generation_before
    assert not list(project.root.glob(".build.*.tmp"))


def test_wechat_cdn_image_keeps_primary_copy_without_manual_fallback(
    workspace: WorkspaceManager,
) -> None:
    project = create_article_project(
        workspace,
        name="微信图片测试",
        mode="layout_only",
        project_id="wechat-image-test",
    )
    project.write_article(
        """---
title: 微信图片测试
---

正文。

![微信图片](https://mmbiz.qpic.cn/example/640?wx_fmt=png)
"""
    )

    result = build_article_project(project)
    preview = (result.build_directory / "wechat_preview.html").read_text(encoding="utf-8")
    report = read_yaml(result.build_directory / "delivery-report.yaml")

    assert 'data-available="false"' in preview
    copy_root = preview.split('<section id="wechat-copy-root"', 1)[1].split(
        "</section>\n    </div>", 1
    )[0]
    assert "data-fallback-required" not in copy_root
    assert report["images"][0]["delivery_status"] == "ready"
    assert report["images"][0]["fallback"] == "none"
    assert report["risks"] == []


@pytest.mark.parametrize("use_base_components", [False, True])
def test_all_public_components_build_safe_matching_delivery(
    workspace: WorkspaceManager, use_base_components: bool,
) -> None:
    """A complete article exercises tags missed by a paragraph-only smoke test."""
    project, _ = create_buildable_project(workspace)
    project.write_article(
        """# Complete article

::: lead
Opening context.
:::

Paragraph with **emphasis**, `inline code` and [a reference](https://example.org/reference).

## Main heading

### Supporting heading

::: key
Central claim.
:::

> Quoted observation.

![Example image](IMG-001)

::: caption
Image description.
:::

---

```python
if value < 3:
    print("<script>literal</script>")
```

- First item
- Second item

1. First step
2. Second step

::: ending
Closing thought.
:::
"""
    )
    components = (
        workspace.paths.resources_root / "components" / "base-v1"
        if use_base_components else None
    )
    result = build_article_project(project, components_directory=components)
    article = (result.build_directory / "wechat.html").read_text(encoding="utf-8")
    preview = (result.build_directory / "wechat_preview.html").read_text(encoding="utf-8")
    validation = validate_delivery_html(article, preview, expected_image_count=1)

    assert validation.valid, validation.to_dict()
    for text in (
        "Opening context.", "Paragraph with", "Main heading", "Supporting heading",
        "Central claim.", "Quoted observation.", "Image description.", "First item",
        "Second step", "Closing thought.", "&lt;script&gt;literal&lt;/script&gt;",
    ):
        assert text in article
    assert validation.article_tag_counts["ul"] == 1
    assert validation.article_tag_counts["ol"] == 1
    assert validation.article_tag_counts["pre"] == 1
    assert validation.article_tag_counts["blockquote"] == 1
    assert validation.article_tag_counts["a"] == 1
    assert result.report["validation"]["local_status"] == "PASS"
    assert result.report["validation"]["confirmed_by_user"] is False

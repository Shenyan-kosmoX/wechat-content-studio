from __future__ import annotations

from wechat_studio.rendering.renderer import render_article_root, render_document_from_article
from wechat_studio.rendering.preview import render_product_preview
from wechat_studio.validation import validate_delivery_html


def test_product_delivery_validation_passes_for_matching_article() -> None:
    article = '<p style="margin:0;">正文</p>'
    document = render_document_from_article("测试", article)
    preview = render_product_preview(
        "测试",
        render_article_root(article, "wechat-copy-root"),
        has_fallback_images=False,
    )

    result = validate_delivery_html(document, preview, expected_image_count=0)

    assert result.valid, result.to_dict()


def test_delivery_validation_rejects_script_inside_article() -> None:
    article = '<p style="margin:0;">正文</p><script>alert(1)</script>'
    document = render_document_from_article("测试", article)
    preview = render_product_preview(
        "测试",
        render_article_root(article, "wechat-copy-root"),
        has_fallback_images=False,
    )

    result = validate_delivery_html(document, preview)

    assert not result.valid
    assert any(not check["ok"] for check in result.checks)

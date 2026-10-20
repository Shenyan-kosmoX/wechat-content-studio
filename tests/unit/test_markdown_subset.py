from __future__ import annotations

from wechat_studio.rendering.markdown_subset import render_markdown_text


def test_first_markdown_h1_becomes_title_and_is_removed_from_body() -> None:
    rendered = render_markdown_text("# 一个文章标题\n\n正文第一段。")

    assert rendered.title == "一个文章标题"
    assert "# 一个文章标题" not in rendered.article_html
    assert "一个文章标题" not in rendered.article_html
    assert "正文第一段。" in rendered.article_html


def test_front_matter_title_remains_authoritative_over_markdown_h1() -> None:
    rendered = render_markdown_text(
        "---\ntitle: 元数据标题\n---\n\n# 正文标题\n\n正文。"
    )

    assert rendered.title == "元数据标题"
    assert "# 正文标题" not in rendered.article_html
    assert "正文标题" not in rendered.article_html


def test_code_comment_is_not_consumed_as_document_title() -> None:
    rendered = render_markdown_text("```python\n# Keep this comment\npass\n```")
    assert rendered.title == "article"
    assert "# Keep this comment" in rendered.article_html


def test_heading_after_prose_is_not_consumed_as_metadata() -> None:
    rendered = render_markdown_text("Opening paragraph.\n\n# Later heading")
    assert rendered.title == "article"
    assert "Later heading" in rendered.article_html

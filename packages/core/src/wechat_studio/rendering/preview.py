"""Generate legacy-compatible and product preview pages."""

from __future__ import annotations

import html

from wechat_studio.errors import RenderError
from wechat_studio.storage.paths import resolve_resource_root

from . import legacy_v1


def render_legacy_preview(title: str, article_html: str) -> str:
    """Return the byte-compatible V1 preview source before newline encoding."""

    return legacy_v1.render_preview_document_from_article(title, article_html)


def render_product_preview(
    title: str,
    article_root: str,
    *,
    has_fallback_images: bool,
) -> str:
    shell_path = resolve_resource_root() / "preview-shell" / "product-v1.html"
    try:
        shell = shell_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RenderError(
            f"Unable to load preview shell: {shell_path}",
            context={"path": str(shell_path), "reason": str(exc)},
        ) from exc
    rendered = (
        shell.replace("{{TITLE}}", html.escape(title, quote=True))
        .replace("{{ARTICLE_ROOT}}", article_root)
        .replace("{{FALLBACK_AVAILABLE}}", str(has_fallback_images).lower())
    )
    unresolved = [
        token
        for token in ("{{TITLE}}", "{{ARTICLE_ROOT}}", "{{FALLBACK_AVAILABLE}}")
        if token in rendered
    ]
    if unresolved:
        raise RenderError(
            "Preview shell contains unresolved placeholders.",
            context={"path": str(shell_path), "placeholders": unresolved},
        )
    return rendered

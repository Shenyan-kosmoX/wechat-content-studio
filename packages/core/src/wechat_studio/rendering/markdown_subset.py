"""Render the supported Markdown subset into inline-style article components."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from wechat_studio.errors import RenderError

from .components import ComponentCatalog
from .inline import render_inline, safe_web_url


DIRECTIVE_COMPONENTS = {
    "lead": "lead",
    "key": "key_sentence",
    "key_sentence": "key_sentence",
    "caption": "caption",
    "ending": "ending",
}

SPECIAL_START = re.compile(
    r"^(?:#{2,3}\s+|```|:::|>\s?|[-*+]\s+|\d+[.)]\s+|!\[[^]]*\]\([^)]*\)|(?:-{3,}|\*{3,}|_{3,})\s*$)"
)
IMAGE_RE = re.compile(r"^!\[([^]]*)\]\((\S+?)(?:\s+[\"']([^\"']*)[\"'])?\)\s*$")


@dataclass(frozen=True, slots=True)
class ResolvedImage:
    image_id: str
    source: str
    rendered_src: str
    alt: str
    caption: str
    original_name: str
    fallback_text: str
    fallback_required: bool
    copy_mode: str
    delivery_status: str
    fallback: str
    anchor: str | None = None
    anchor_relation: str | None = None


class ImageResolver(Protocol):
    def __call__(
        self,
        source: str,
        alt: str,
        title: str | None,
        index: int,
    ) -> ResolvedImage: ...


@dataclass(frozen=True, slots=True)
class MarkdownRender:
    title: str
    article_html: str
    metadata: dict[str, str]
    images: tuple[ResolvedImage, ...]


def parse_front_matter(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    if not lines or lines[0].strip() != "---":
        return {}, lines
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, lines
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata, lines[end + 1 :]


def _is_special(line: str) -> bool:
    return bool(SPECIAL_START.match(line.strip()))


def _legacy_image(source: str, alt: str, _: str | None, index: int) -> ResolvedImage:
    return ResolvedImage(
        image_id=f"IMG-{index:03d}",
        source=source,
        rendered_src=safe_web_url(source),
        alt=alt,
        caption=alt,
        original_name=source.rsplit("/", 1)[-1] or f"image-{index}",
        fallback_text="",
        fallback_required=False,
        copy_mode="preserve_image",
        delivery_status="awaiting_user_validation",
        fallback="none",
    )


def _render_image_component(catalog: ComponentCatalog, image: ResolvedImage) -> str:
    rendered = catalog.fill(
        "image",
        src=image.rendered_src,
        alt=html.escape(image.alt, quote=True),
    )
    if not image.fallback_text:
        return rendered
    attributes = (
        f'data-image-id="{html.escape(image.image_id, quote=True)}" '
        f'data-fallback-required="{str(image.fallback_required).lower()}" '
        f'data-fallback-text="{html.escape(image.fallback_text, quote=True)}" '
    )
    return rendered.replace("<img ", "<img " + attributes, 1)


def render_blocks(
    lines: list[str],
    catalog: ComponentCatalog,
    *,
    image_resolver: ImageResolver | None = None,
) -> tuple[list[str], list[ResolvedImage]]:
    output: list[str] = []
    images: list[ResolvedImage] = []
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith(":::") and stripped != ":::":
            directive = stripped[3:].strip().lower()
            if directive not in DIRECTIVE_COMPONENTS:
                raise RenderError(
                    f"Unknown directive on line {index + 1}: {directive}",
                    context={"line": index + 1, "directive": directive},
                )
            index += 1
            content_lines: list[str] = []
            while index < len(lines) and lines[index].strip() != ":::":
                if lines[index].strip():
                    content_lines.append(lines[index].strip())
                index += 1
            if index >= len(lines):
                raise RenderError(
                    f"Directive '{directive}' is missing its closing :::",
                    context={"directive": directive},
                )
            index += 1
            content = "<br />".join(render_inline(line) for line in content_lines)
            output.append(catalog.fill(DIRECTIVE_COMPONENTS[directive], content=content))
            continue

        if stripped.startswith("```"):
            language = stripped[3:].strip()
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index >= len(lines):
                raise RenderError("Code fence is missing its closing ```")
            index += 1
            content = html.escape("\n".join(code_lines), quote=False)
            if language:
                content = (
                    f'<span style="color:#888888;">{html.escape(language)}</span>\n'
                    + content
                )
            output.append(catalog.fill("code", content=content))
            continue

        if stripped.startswith("## "):
            output.append(catalog.fill("section_title", content=render_inline(stripped[3:])))
            index += 1
            continue

        if stripped.startswith("### "):
            output.append(catalog.fill("sub_title", content=render_inline(stripped[4:])))
            index += 1
            continue

        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
            output.append(catalog.get("divider"))
            index += 1
            continue

        image_match = IMAGE_RE.match(stripped)
        if image_match:
            resolver = image_resolver or _legacy_image
            image = resolver(
                image_match.group(2),
                image_match.group(1),
                image_match.group(3),
                len(images) + 1,
            )
            images.append(image)
            output.append(_render_image_component(catalog, image))
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].lstrip())
                index += 1
            content = "<br />".join(render_inline(line) for line in quote_lines)
            output.append(catalog.fill("quote", content=content))
            continue

        unordered = re.match(r"^[-*+]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if unordered or ordered:
            list_tag = "ul" if unordered else "ol"
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                match = (
                    re.match(r"^[-*+]\s+(.+)$", current)
                    if list_tag == "ul"
                    else re.match(r"^\d+[.)]\s+(.+)$", current)
                )
                if not match:
                    break
                items.append(
                    '<li style="margin:0 0 8px;padding:0;">'
                    + render_inline(match.group(1))
                    + "</li>"
                )
                index += 1
            output.append(catalog.fill("list", list_tag=list_tag, items="".join(items)))
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines) and lines[index].strip() and not _is_special(lines[index]):
            paragraph_lines.append(lines[index].strip())
            index += 1
        content = " ".join(render_inline(line) for line in paragraph_lines)
        output.append(catalog.fill("paragraph", content=content))

    return output, images


def render_markdown_text(
    markdown: str,
    *,
    source_name: str = "article",
    components: ComponentCatalog | None = None,
    image_resolver: ImageResolver | None = None,
) -> MarkdownRender:
    catalog = components or ComponentCatalog.load()
    metadata, content_lines = parse_front_matter(markdown.splitlines())
    for line_index, line in enumerate(content_lines):
        if not line.strip():
            continue
        match = re.match(r"^#\s+(.+?)\s*$", line.strip())
        if match:
            metadata.setdefault("title", match.group(1))
            content_lines = content_lines[:line_index] + content_lines[line_index + 1 :]
        break
    blocks, images = render_blocks(content_lines, catalog, image_resolver=image_resolver)
    return MarkdownRender(
        title=metadata.get("title", Path(source_name).stem),
        article_html="\n".join(blocks),
        metadata=metadata,
        images=tuple(images),
    )


def render_markdown_file(
    source: str | Path,
    *,
    components: ComponentCatalog | None = None,
    image_resolver: ImageResolver | None = None,
) -> MarkdownRender:
    path = Path(source)
    try:
        markdown = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RenderError(
            f"Unable to read article Markdown: {path}",
            context={"path": str(path), "reason": str(exc)},
        ) from exc
    return render_markdown_text(
        markdown,
        source_name=path.name,
        components=components,
        image_resolver=image_resolver,
    )

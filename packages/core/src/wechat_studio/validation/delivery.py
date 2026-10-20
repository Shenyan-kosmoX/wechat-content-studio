"""Non-visual structural checks for WeChat article and preview HTML."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from wechat_studio.errors import DeliveryValidationError


ARTICLE_ALLOWED_TAGS = {
    "section",
    "p",
    "span",
    "strong",
    "blockquote",
    "img",
    "pre",
    "code",
    "ul",
    "ol",
    "li",
    "a",
    "br",
}

FORBIDDEN_ARTICLE_TAGS = {
    "style",
    "script",
    "link",
    "iframe",
    "video",
    "audio",
    "svg",
    "canvas",
    "form",
    "button",
    "input",
}

COPY_MARKERS = {
    "clipboard_api": "navigator.clipboard.write",
    "clipboard_item": "new ClipboardItem",
    "html_mime": '"text/html"',
    "plain_mime": '"text/plain"',
    "html_fallback": 'event.clipboardData.setData("text/html"',
    "plain_fallback": 'event.clipboardData.setData("text/plain"',
    "exec_command_fallback": 'document.execCommand("copy")',
}


class ArticleRootParser(HTMLParser):
    """Capture one root and canonicalize its descendants."""

    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.target_count = 0
        self.root_style = ""
        self.depth = 0
        self.events: list[tuple[object, ...]] = []
        self.tags: Counter[str] = Counter()
        self.image_sources: list[str] = []
        self.errors: list[str] = []

    @property
    def inside(self) -> bool:
        return self.depth > 0

    @staticmethod
    def canonical_attrs(
        attrs: list[tuple[str, str | None]],
    ) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((name.lower(), value or "") for name, value in attrs))

    def inspect_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        self.tags[tag] += 1
        if tag not in ARTICLE_ALLOWED_TAGS:
            self.errors.append(f"Tag is outside the article allowlist: <{tag}>")
        if tag in FORBIDDEN_ARTICLE_TAGS:
            self.errors.append(f"Forbidden tag found inside article root: <{tag}>")
        if "data-preview-toolbar" in attr_map:
            self.errors.append("Preview toolbar marker leaked into article root.")
        for name, value in attr_map.items():
            if name.startswith("on"):
                self.errors.append(f"Event handler found inside article root: {name}")
            if "javascript:" in value.lower():
                self.errors.append(f"JavaScript URL found inside article root: {name}")
        if tag == "img":
            source = attr_map.get("src", "")
            if not source:
                self.errors.append("Image is missing src.")
            self.image_sources.append(source)
        if tag == "a":
            href = attr_map.get("href", "")
            if urlparse(href).scheme not in {"http", "https"}:
                self.errors.append(f"Unsafe or missing href on <a>: {href}")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if attr_map.get("id") == self.target_id:
            self.target_count += 1
            if self.inside:
                self.errors.append(f"Nested duplicate article root: #{self.target_id}")
                return
            self.depth = 1
            self.root_style = attr_map.get("style", "")
            self.inspect_tag(tag, attrs)
            return
        if self.inside:
            self.inspect_tag(tag, attrs)
            self.events.append(("start", tag, self.canonical_attrs(attrs)))
            self.depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if attr_map.get("id") == self.target_id:
            self.target_count += 1
            self.errors.append(f"Article root cannot be self-closing: #{self.target_id}")
            return
        if self.inside:
            self.inspect_tag(tag, attrs)
            self.events.append(("empty", tag, self.canonical_attrs(attrs)))

    def handle_endtag(self, tag: str) -> None:
        if not self.inside:
            return
        tag = tag.lower()
        if self.depth == 1:
            self.depth = 0
            return
        self.events.append(("end", tag))
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.inside:
            self.events.append(("data", data))

    def handle_entityref(self, name: str) -> None:
        if self.inside:
            self.events.append(("entity", name))

    def handle_charref(self, name: str) -> None:
        if self.inside:
            self.events.append(("charref", name))


@dataclass(frozen=True, slots=True)
class DeliveryValidation:
    status: str
    checks: tuple[dict[str, object], ...]
    article_tag_counts: dict[str, int]
    preview_article_tag_counts: dict[str, int]

    @property
    def valid(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [dict(check) for check in self.checks],
            "article_tag_counts": dict(self.article_tag_counts),
            "preview_article_tag_counts": dict(self.preview_article_tag_counts),
        }

    def raise_for_error(self) -> None:
        if self.valid:
            return
        failed = [check for check in self.checks if not check["ok"]]
        raise DeliveryValidationError(
            "Generated delivery artifacts did not pass local validation.",
            context={"failed_checks": failed},
        )


def _check(checks: list[dict[str, object]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": ok, "detail": detail})


def validate_delivery_html(
    article_html: str,
    preview_html: str,
    *,
    expected_image_count: int | None = None,
) -> DeliveryValidation:
    checks: list[dict[str, object]] = []
    _check(
        checks,
        "article_document",
        bool(article_html.strip()),
        "Article HTML exists." if article_html.strip() else "Article HTML is empty.",
    )
    _check(
        checks,
        "article_no_embedded_tools",
        not re.search(r"<(?:style|script|link|button)\b", article_html, re.IGNORECASE),
        "Article HTML contains no stylesheet, script, link, or button tags.",
    )

    article = ArticleRootParser("js_content")
    article.feed(article_html)
    article_errors = list(article.errors)
    if article.target_count != 1:
        article_errors.append(f"Expected one #js_content root; actual={article.target_count}")
    if not article.root_style:
        article_errors.append("#js_content is missing its inline root style.")
    _check(
        checks,
        "article_root",
        not article_errors,
        "; ".join(article_errors) or "OK",
    )

    preview = ArticleRootParser("wechat-copy-root")
    preview.feed(preview_html)
    preview_errors = list(preview.errors)
    if preview.target_count != 1:
        preview_errors.append(
            f"Expected one #wechat-copy-root; actual={preview.target_count}"
        )
    if not preview.root_style:
        preview_errors.append("#wechat-copy-root is missing its inline root style.")
    _check(
        checks,
        "preview_copy_root",
        not preview_errors,
        "; ".join(preview_errors) or "OK",
    )

    control_counts = {
        "rich_button": len(re.findall(r'id=["\']copy-rich-text["\']', preview_html)),
        "fallback_button": len(
            re.findall(r'id=["\']copy-with-placeholders["\']', preview_html)
        ),
        "toolbar": len(
            re.findall(r'data-preview-toolbar=["\']true["\']', preview_html)
        ),
    }
    _check(
        checks,
        "preview_controls",
        all(value == 1 for value in control_counts.values()),
        "; ".join(f"{name}={value}" for name, value in control_counts.items()),
    )

    missing_copy_markers = [
        name for name, marker in COPY_MARKERS.items() if marker not in preview_html
    ]
    _check(
        checks,
        "rich_clipboard",
        not missing_copy_markers,
        f"missing={missing_copy_markers}",
    )

    same_root_style = bool(
        article.root_style
        and preview.root_style
        and article.root_style == preview.root_style
    )
    same_events = bool(
        article.events and preview.events and article.events == preview.events
    )
    same_tags = article.tags == preview.tags
    _check(
        checks,
        "preview_article_matches_delivery",
        same_root_style and same_events and same_tags,
        (
            f"root_style_equal={same_root_style}; "
            f"dom_events_equal={same_events}; tag_counts_equal={same_tags}"
        ),
    )

    if expected_image_count is not None:
        image_count_ok = (
            article.tags.get("img", 0) == expected_image_count
            and preview.tags.get("img", 0) == expected_image_count
        )
        _check(
            checks,
            "image_count",
            image_count_ok,
            (
                f"expected={expected_image_count}; "
                f"article={article.tags.get('img', 0)}; "
                f"preview={preview.tags.get('img', 0)}"
            ),
        )

    unresolved = re.findall(r"\{\{[A-Z_a-z]+\}\}", article_html + preview_html)
    _check(
        checks,
        "resolved_placeholders",
        not unresolved,
        f"unresolved={sorted(set(unresolved))}",
    )

    status = "PASS" if all(bool(item["ok"]) for item in checks) else "FAIL"
    return DeliveryValidation(
        status=status,
        checks=tuple(checks),
        article_tag_counts=dict(sorted(article.tags.items())),
        preview_article_tag_counts=dict(sorted(preview.tags.items())),
    )

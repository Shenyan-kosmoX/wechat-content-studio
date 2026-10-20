"""Extract writing and inline-layout evidence from WeChat article HTML."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from statistics import mean, median
from typing import Any, Iterator


VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
BLOCK_TAGS = {
    "article",
    "blockquote",
    "div",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
TEXT_BLOCK_TAGS = BLOCK_TAGS - {"article", "figure", "ol", "table", "tr", "ul"}
IGNORED_TAGS = {"audio", "button", "canvas", "form", "iframe", "input", "noscript", "script", "style", "svg", "template", "video"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
GRAY_MARKERS = (
    "#888",
    "#999",
    "#aaa",
    "#b2b2b2",
    "rgb(127",
    "rgb(136",
    "rgb(153",
    "rgb(178",
    "rgba(0, 0, 0, 0.3",
    "rgba(0, 0, 0, 0.5",
)


_UI_CLASS_OR_ID = re.compile(
    r"(?:^|[\s_-])(?:"
    r"wx(?:_|-)?video|js(?:_|-)?video|mp(?:_|-)?video|mp-common-video|"
    r"video(?:_|-)?player|video(?:_|-)?control|player(?:_|-)?control|"
    r"wx(?:_|-)?audio|mpvoice|audio(?:_|-)?player|audio(?:_|-)?control|"
    r"weui|js(?:_|-)?comment|comment(?:_|-)?area|like(?:_|-)?area|like|"
    r"reward(?:_|-)?area|reward|share(?:_|-)?area|share|article(?:_|-)?bottom|"
    r"profile(?:_|-)?qrcode|pc(?:_|-)?qr(?:_|-)?code|related(?:_|-)?article|"
    r"rich(?:_|-)?media(?:_|-)?tool|rich(?:_|-)?media(?:_|-)?meta"
    r")(?:$|[\s_-])",
    re.IGNORECASE,
)
_EXACT_UI_TEXT = {
    "播放",
    "暂停",
    "重播",
    "重试",
    "倍速",
    "全屏",
    "退出全屏",
    "静音",
    "取消静音",
    "视频详情",
    "音频详情",
    "关注",
    "已关注",
    "分享",
    "赞",
    "继续观看",
    "写下你的评论",
    "已同步到看一看",
    "轻点两下取消赞",
}
_CONTAINED_UI_TEXT = (
    "已同步到看一看",
    "写下你的评论",
    "轻点两下取消赞",
    "视频加载失败",
    "音频加载失败",
    "当前浏览器不支持播放",
)
_SPEED_TEXT = re.compile(r"(?:0\.5|0\.75|1(?:\.0)?|1\.25|1\.5|2(?:\.0)?)倍")
_TIME_TEXT = re.compile(r"\d{1,3}:\d{2}(?:\s*/\s*\d{1,3}:\d{2})?")
_COUNTER_TEXT = re.compile(r"\d+\s*/\s*\d+")
_DURATION_TEXT = re.compile(r"[，,]?\s*时长\s*\d{1,3}:\d{2}")
_SENTENCE_SPLIT = re.compile(r"[。！？!?；;]+")
_PIXELS = re.compile(r"^(-?\d+(?:\.\d+)?)px$", re.IGNORECASE)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_style(raw: str) -> dict[str, str]:
    """Parse inline declarations without splitting quoted data URLs/functions."""

    declarations: dict[str, str] = {}
    current: list[str] = []
    quote: str | None = None
    parentheses = 0
    chunks: list[str] = []
    for character in raw:
        if quote:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
            current.append(character)
        elif character == "(":
            parentheses += 1
            current.append(character)
        elif character == ")":
            parentheses = max(0, parentheses - 1)
            current.append(character)
        elif character == ";" and parentheses == 0:
            chunks.append("".join(current))
            current = []
        else:
            current.append(character)
    chunks.append("".join(current))

    for chunk in chunks:
        if ":" not in chunk:
            continue
        property_name, value = chunk.split(":", 1)
        property_name = property_name.strip().lower()
        value = normalize_text(value)
        if property_name and value and not property_name.startswith("--"):
            declarations[property_name] = value
    return declarations


def _style_signature(style: dict[str, str]) -> str:
    return ";".join(f"{name}:{value}" for name, value in sorted(style.items()))


def _px(value: str | None) -> float | None:
    match = _PIXELS.fullmatch(normalize_text(value))
    return float(match.group(1)) if match else None


def _font_weight(value: str | None) -> int:
    normalized = normalize_text(value).lower()
    if normalized in {"bold", "bolder"}:
        return 700
    if normalized in {"normal", "lighter", ""}:
        return 400
    try:
        return int(float(normalized))
    except ValueError:
        return 400


@dataclass(slots=True)
class HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    parent: "HtmlNode | None" = None
    children: list["HtmlNode"] = field(default_factory=list)
    text_chunks: list[str] = field(default_factory=list)

    @property
    def style(self) -> dict[str, str]:
        return parse_style(self.attrs.get("style", ""))

    @property
    def direct_text(self) -> str:
        return normalize_text(" ".join(self.text_chunks))

    def text(self) -> str:
        chunks = list(self.text_chunks)
        for child in self.children:
            chunks.append(child.text())
        return normalize_text(" ".join(chunks))

    def descendants(self, *, include_self: bool = False) -> Iterator["HtmlNode"]:
        if include_self:
            yield self
        for child in self.children:
            yield child
            yield from child.descendants()


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        node = HtmlNode(
            normalized,
            {name.lower(): value or "" for name, value in attrs},
            parent=self.stack[-1],
        )
        self.stack[-1].children.append(node)
        if normalized not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == normalized:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].text_chunks.append(data)


def _is_wechat_ui_noise(node: HtmlNode) -> bool:
    if node.attrs.get("id", "").lower() == "js_content" or "rich_media_content" in node.attrs.get(
        "class", ""
    ).lower():
        return False
    class_and_id = " ".join(
        normalize_text(node.attrs.get(name, ""))
        for name in ("class", "id", "role", "aria-label", "title")
    )
    if _UI_CLASS_OR_ID.search(class_and_id):
        return True
    if node.tag in IGNORED_TAGS:
        return True
    text = node.direct_text
    if not text and len(node.children) <= 8:
        descendant_text = node.text()
        if len(descendant_text) <= 160:
            text = descendant_text
    if not text:
        return False
    if text in _EXACT_UI_TEXT or any(marker in text for marker in _CONTAINED_UI_TEXT):
        return True
    if (
        _SPEED_TEXT.fullmatch(text)
        or _TIME_TEXT.fullmatch(text)
        or _COUNTER_TEXT.fullmatch(text)
        or _DURATION_TEXT.fullmatch(text)
    ):
        return True
    media_signatures = sum(
        marker in text for marker in ("播放", "倍速", "0.5倍", "1.0倍", "1.5倍")
    )
    return media_signatures >= 2


def _content_nodes(root: HtmlNode) -> tuple[list[HtmlNode], list[HtmlNode]]:
    included: list[HtmlNode] = []
    excluded: list[HtmlNode] = []

    def visit(node: HtmlNode) -> bool:
        if _is_wechat_ui_noise(node):
            excluded.append(node)
            return False
        included.append(node)
        retained: list[HtmlNode] = []
        for child in list(node.children):
            if visit(child):
                retained.append(child)
        node.children = retained
        return True

    visit(root)
    return included, excluded


def _article_root(tree: HtmlNode) -> tuple[HtmlNode, str]:
    nodes = list(tree.descendants())
    exact = next((node for node in nodes if node.attrs.get("id") == "js_content"), None)
    if exact is not None:
        return exact, "id_js_content"

    scored: list[tuple[int, int, HtmlNode, str]] = []
    for order, node in enumerate(nodes):
        identifier = node.attrs.get("id", "").lower()
        classes = node.attrs.get("class", "").lower()
        score = 0
        reason = "largest_content_container"
        if "rich_media_content" in classes:
            score += 1000
            reason = "class_rich_media_content"
        if identifier in {"content", "article", "article-content", "js_article"}:
            score += 500
            reason = "article_id"
        if node.tag == "article":
            score += 400
            reason = "article_tag"
        if node.tag == "body":
            score += 50
            reason = "body_fallback"
        score += min(len(node.text()), 20000) // 20
        scored.append((score, -order, node, reason))
    if not scored:
        return tree, "document_fallback"
    _, _, selected, reason = max(scored, key=lambda item: (item[0], item[1]))
    return selected, reason


def _has_block_descendant(node: HtmlNode) -> bool:
    return any(child.tag in BLOCK_TAGS for child in node.descendants())


def _atomic_text_nodes(nodes: list[HtmlNode]) -> list[HtmlNode]:
    atomic = [
        node
        for node in nodes
        if node.tag in TEXT_BLOCK_TAGS and node.text() and not _has_block_descendant(node)
    ]
    if atomic:
        return atomic
    return [
        node
        for node in nodes
        if node.tag in {"span", "strong", "b", "em"}
        and node.text()
        and not node.children
    ]


def _effective_style(node: HtmlNode) -> dict[str, str]:
    style = dict(node.style)
    styled_children = [child for child in node.children if child.style]
    if len(styled_children) == 1 and len(node.children) == 1:
        for name, value in styled_children[0].style.items():
            style.setdefault(name, value)
    return style


def _position(index: int, total: int) -> str:
    if total <= 1 or index == 0:
        return "opening"
    if index == total - 1:
        return "ending"
    return "middle"


def _classify_text_component(node: HtmlNode, text: str, style: dict[str, str]) -> str:
    font_size = _px(style.get("font-size"))
    weight = _font_weight(style.get("font-weight"))
    color = style.get("color", "").lower()
    border_left = _px(style.get("border-left-width")) or (
        1.0 if "border-left" in style and "none" not in style["border-left"] else 0.0
    )

    if node.tag in {"pre", "code"}:
        return "code"
    if node.tag == "blockquote" or border_left > 0:
        return "quote"
    if node.tag == "figcaption" or (
        len(text) <= 140
        and font_size is not None
        and font_size <= 14
        and any(marker in color for marker in GRAY_MARKERS)
    ):
        return "caption"
    if node.tag in HEADING_TAGS or (
        4 <= len(text) <= 180 and font_size is not None and font_size >= 20
    ):
        return "section_title"
    if 3 <= len(text) <= 120 and (font_size or 0) >= 17 and weight >= 600:
        return "sub_title"
    if 6 <= len(text) <= 220 and weight >= 600:
        return "key_sentence"
    return "paragraph"


def _component_candidates(
    nodes: list[HtmlNode], atomic: list[HtmlNode], sample_id: str
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    counts: Counter[str] = Counter()
    atomic_index = {id(node): index for index, node in enumerate(atomic)}

    def add(component: str, node: HtmlNode, *, position: str) -> None:
        style = _effective_style(node)
        signature = f"{node.tag}|{_style_signature(style)}"
        row = grouped[component].setdefault(
            signature,
            {
                "sample_id": sample_id,
                "tag": node.tag,
                "style": style,
                "signature": signature,
                "occurrences": 0,
                "positions": [],
            },
        )
        row["occurrences"] += 1
        if position not in row["positions"]:
            row["positions"].append(position)
        counts[component] += 1

    for node in nodes:
        if node.tag == "img":
            add("image", node, position="middle")
        elif node.tag in {"ul", "ol"}:
            add("list", node, position="middle")
        elif node.tag == "hr" or (
            not node.text()
            and any(name in node.style for name in ("border-top", "border-top-width"))
        ):
            add("divider", node, position="middle")

    for node in atomic:
        text = node.text()
        index = atomic_index[id(node)]
        position = _position(index, len(atomic))
        component = _classify_text_component(node, text, _effective_style(node))
        add(component, node, position=position)
        if index == 0 and component == "paragraph":
            add("lead", node, position="opening")
        if index == len(atomic) - 1 and component in {"paragraph", "key_sentence"}:
            add("ending", node, position="ending")

    return (
        {
            name: sorted(
                rows.values(), key=lambda item: (-item["occurrences"], item["signature"])
            )
            for name, rows in sorted(grouped.items())
        },
        dict(sorted(counts.items())),
    )


def _writing_metrics(atomic: list[HtmlNode]) -> dict[str, Any]:
    paragraphs = [node.text() for node in atomic if node.text()]
    lengths = [len(value) for value in paragraphs]
    sentences = [
        normalize_text(sentence)
        for paragraph in paragraphs
        for sentence in _SENTENCE_SPLIT.split(paragraph)
        if normalize_text(sentence)
    ]
    sentence_lengths = [len(value) for value in sentences]
    opening = paragraphs[0] if paragraphs else ""
    ending = paragraphs[-1] if paragraphs else ""
    if opening.endswith(("？", "?")):
        opening_pattern = "question_opening"
    elif len(opening) <= 80:
        opening_pattern = "short_framing_opening"
    else:
        opening_pattern = "context_first_opening"
    if ending.endswith(("？", "?")):
        ending_pattern = "question_ending"
    elif len(ending) <= 100:
        ending_pattern = "concise_conclusion"
    else:
        ending_pattern = "extended_summary"

    return {
        "text_characters": sum(lengths),
        "paragraph_count": len(paragraphs),
        "paragraph_lengths": lengths,
        "paragraph_length_median": round(median(lengths), 2) if lengths else 0,
        "paragraph_length_mean": round(mean(lengths), 2) if lengths else 0,
        "sentence_count": len(sentences),
        "sentence_lengths": sentence_lengths,
        "sentence_length_median": round(median(sentence_lengths), 2) if sentence_lengths else 0,
        "question_sentence_count": sum(
            paragraph.count("？") + paragraph.count("?") for paragraph in paragraphs
        ),
        "opening_pattern": opening_pattern,
        "ending_pattern": ending_pattern,
        "heading_count": sum(1 for node in atomic if node.tag in HEADING_TAGS),
        "quote_count": sum(1 for node in atomic if node.tag == "blockquote"),
        "list_item_count": sum(1 for node in atomic if node.tag == "li"),
    }


def _frequency_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def analyze_text_evidence(
    sample_id: str,
    text: str,
    *,
    article_type: str = "other",
    source_kind: str = "text",
) -> dict[str, Any]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [normalize_text(value) for value in re.split(r"\n\s*\n+", normalized)]
    paragraphs = [value for value in paragraphs if value]
    synthetic = [HtmlNode("p", text_chunks=[value]) for value in paragraphs]
    writing = _writing_metrics(synthetic)
    available = writing["text_characters"] >= 40 and writing["paragraph_count"] >= 1
    return {
        "distillation_evidence_version": "1.0",
        "sample_id": sample_id,
        "source_kind": source_kind,
        "article_type": article_type,
        "accessibility": "accessible",
        "evidence_scope": "writing_only" if available else "none",
        "writing": writing if available else None,
        "layout": None,
        "warnings": [] if available else ["insufficient_writing_text"],
    }


def analyze_html_evidence(
    sample_id: str,
    html: str,
    *,
    article_type: str = "other",
    source_kind: str = "html",
) -> dict[str, Any]:
    parser = _TreeParser()
    parser.feed(html)
    parser.close()
    article_root, root_reason = _article_root(parser.root)
    nodes, excluded = _content_nodes(article_root)
    atomic = _atomic_text_nodes(nodes)
    writing = _writing_metrics(atomic)
    writing_available = writing["text_characters"] >= 40 and writing["paragraph_count"] >= 1

    tags = Counter(node.tag for node in nodes if node.tag != "document")
    style_values: dict[str, Counter[str]] = defaultdict(Counter)
    signatures: Counter[str] = Counter()
    inline_style_nodes = 0
    inline_declaration_count = 0
    for node in nodes:
        style = node.style
        if not style:
            continue
        inline_style_nodes += 1
        inline_declaration_count += len(style)
        signatures[_style_signature(style)] += 1
        for property_name, value in style.items():
            style_values[property_name][value] += 1

    semantic_layout_signals = sum(
        tags.get(tag, 0) for tag in HEADING_TAGS | {"blockquote", "img", "ol", "ul", "hr"}
    )
    layout_available = inline_style_nodes >= 2 or (
        inline_style_nodes >= 1 and inline_declaration_count >= 4 and semantic_layout_signals >= 1
    )
    candidates, candidate_counts = _component_candidates(nodes, atomic, sample_id)
    root_style = article_root.style
    width_candidates: list[int] = []
    for node in nodes:
        for name in ("max-width", "width"):
            value = _px(node.style.get(name))
            if value is not None and 320 <= value <= 1200:
                width_candidates.append(round(value))

    layout = None
    if layout_available:
        layout = {
            "article_root": {
                "tag": article_root.tag,
                "selection_reason": root_reason,
                "inline_style": root_style,
            },
            "tag_counts": dict(tags.most_common()),
            "inline_style_node_count": inline_style_nodes,
            "inline_declaration_count": inline_declaration_count,
            "inline_style_values": {
                name: _frequency_rows(values) for name, values in sorted(style_values.items())
            },
            "style_signatures": _frequency_rows(signatures),
            "component_candidates": candidates,
            "component_occurrences": candidate_counts,
            "width_candidates_px": width_candidates,
            "image_count": tags.get("img", 0),
            "excluded_wechat_ui_subtrees": len(excluded),
            "excluded_wechat_ui_tags": dict(
                Counter(node.tag for node in excluded).most_common()
            ),
        }

    if writing_available and layout_available:
        scope = "writing_and_layout"
    elif writing_available:
        scope = "writing_only"
    elif layout_available:
        scope = "layout_only"
    else:
        scope = "none"
    warnings: list[str] = []
    if not writing_available:
        warnings.append("insufficient_writing_text")
    if not layout_available:
        warnings.append("insufficient_inline_layout_evidence")
    if excluded:
        warnings.append("wechat_ui_noise_excluded")

    return {
        "distillation_evidence_version": "1.0",
        "sample_id": sample_id,
        "source_kind": source_kind,
        "article_type": article_type,
        "accessibility": "accessible",
        "evidence_scope": scope,
        "writing": writing if writing_available else None,
        "layout": layout,
        "warnings": warnings,
    }
